import os
import glob
import json
import logging
import pandas as pd
import numpy as np
from datetime import datetime
from multiprocessing import Pool, cpu_count
import data_loader
from confluence_scorer import confluence_scorer
from pattern_recognizer import pattern_recognizer
from data_handler import get_full_data_with_indicators
from gbm_scorer import GBMScorer
from pricing_gbm import load_pricing_gbm, score_entry_strategy, build_features as pricing_build_features

# ==========================================
# === GBM 模型全局初始化 ===
# ==========================================
_gbm_scorer = None
_gbm_enabled = True
_gbm_threshold = 0.62

def _init_gbm_scorer():
    """全局加载 GBM 模型（单例模式）"""
    global _gbm_scorer, _gbm_enabled
    debug_logger.info(f"⚙️ 子进程启动 (PID:{os.getpid()})，准备加载 GBM 模型...")
    if _gbm_scorer is None and _gbm_enabled:
        try:
            _gbm_scorer = GBMScorer()
            if not _gbm_scorer.load():
                debug_logger.warning(f"⚠️ GBM 模型加载失败 (.pkl 文件可能不存在)，降级为原始评分系统")
                logger.warning("⚠️ GBM 模型加载失败，降级为原始评分系统")
                _gbm_enabled = False
                _gbm_scorer = None
            else:
                debug_logger.info(f"✅ GBM 模型加载成功！阈值设定为: {_gbm_threshold}")
                logger.info(f"✅ GBM 模型加载成功，阈值: {_gbm_threshold}")
        except Exception as e:
            debug_logger.error(f"❌ GBM 初始化异常: {e}")
            logger.error(f"❌ GBM 初始化异常: {e}，降级为原始评分系统")
            _gbm_enabled = False
            _gbm_scorer = None

# ==========================================
# === 定价 GBM 全局初始化 ===
# ==========================================
_pricing_model = None
_pricing_meta = None
_pricing_enabled = True

def _init_pricing_gbm():
    global _pricing_model, _pricing_meta, _pricing_enabled
    if _pricing_model is None and _pricing_enabled:
        try:
            _pricing_model, _pricing_meta = load_pricing_gbm()
            logger.info(f"✅ 定价 GBM 加载成功: {_pricing_meta.get('model_version')}")
        except Exception as e:
            logger.warning(f"⚠️ 定价 GBM 加载失败: {e}，使用默认入场价")
            _pricing_enabled = False
            _pricing_model = None

# ==========================================
# === 狙击手核心回测全局配置 ===
# ==========================================
STRATEGY_TO_TEST = 'MORSE_FACTOR_SNIPER' 
#TARGET_PROFIT = 0.10  # 核心止盈目标：+10% 挂单
#STOP_LOSS = -0.05     # 核心硬性止损：-5%

EVAL_DATE = '2026-6-9'  # 回测选股基准截面日
FORWARD_DAYS = 25       # 持仓/挂单观测窗口天数 (15d持仓 + 5d挂单 + 5d缓冲)

backend_dir = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.abspath(os.path.join(backend_dir, '..', 'data', 'result'))
RESULT_DIR = os.path.join(OUTPUT_PATH, f'WalkForward_{STRATEGY_TO_TEST}')
os.makedirs(RESULT_DIR, exist_ok=True)

# ==========================================
# 🌟 新增：子进程专用 Debug 日志 (写入文件)
# ==========================================
debug_log_path = os.path.join(OUTPUT_PATH, 'gbm_worker_debug.log')
debug_logger = logging.getLogger('WorkerDebug')
debug_logger.setLevel(logging.ERROR)
# 每次运行前清空旧日志
fh = logging.FileHandler(debug_log_path, mode='w', encoding='utf-8')
fh.setFormatter(logging.Formatter('%(asctime)s [PID:%(process)d] %(message)s'))
debug_logger.addHandler(fh)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_time_sliced_data(df, eval_date_str, forward_days):
    if df is None or df.empty: return None, None
    if eval_date_str:
        eval_date = pd.to_datetime(eval_date_str)
        historical_df = df[df.index <= eval_date].copy()
        if historical_df.empty or len(historical_df) < 150: return None, None
        last_idx = df.index.get_loc(historical_df.index[-1])
        future_df = df.iloc[last_idx + 1 : last_idx + 1 + forward_days].copy()
    else:
        if len(df) < 150: return None, None
        historical_df = df.copy()
        future_df = df.iloc[0:0].copy() 
    return historical_df, future_df

# ==========================================
# 在 walk_forward_tester_s.py 的全局配置下方，新增板块参数生成器
# ==========================================
def get_board_params(stock_code):
    """🚨 Grok 特调：应对科创/创业板 20CM 降维打击"""
    if stock_code.startswith(('688', '689')):   # 科创板 20CM
        return {'target_profit': 0.15, 'stop_loss': -0.08, 'board_type': '20CM'}
    elif stock_code.startswith('30'):          # 创业板 20CM
        return {'target_profit': 0.12, 'stop_loss': -0.07, 'board_type': '20CM'}
    elif stock_code.startswith('92'):          # 北交 30CM
        return {'target_profit': 0.18, 'stop_loss': -0.10, 'board_type': '30CM'}
    else:                                       # 主板 10CM
        return {'target_profit': 0.10, 'stop_loss': -0.05, 'board_type': '10CM'}

def _evaluate_daily_position(df_full, date_idx, entry_price, orig_tp, orig_sl):
    """
    每日持仓诊断 + 动态止盈止损调整
    Args:
        df_full: 含全部指标的完整 DataFrame
        date_idx: 当天在 df_full 中的行索引 (iloc 位置)
        entry_price: 入场价
        orig_tp: 原始止盈价
        orig_sl: 原始止损价
    Returns:
        dict: 每日评估结果 + 调整后的 TP/SL
    """
    df_slice = df_full.iloc[:date_idx + 1]
    slice_len = len(df_slice)

    result = confluence_scorer.calculate_confluence_score(df_slice, slice_len - 1)
    pattern = pattern_recognizer.recognize_pattern(df_slice, slice_len - 1)

    close = float(df_full.iloc[date_idx]['close'])
    profit = (close - entry_price) / entry_price
    score = result.get('total_score', 0)
    phase = result.get('market_phase', 'unknown')
    conf = result.get('confidence', 0)
    pat = pattern.get('best_pattern')

    if score >= 70 and phase in ['accumulation', 'markup'] and conf >= 0.6:
        risk = '低'
    elif score < 55 or phase in ['distribution', 'decline']:
        risk = '高'
    else:
        risk = '中'

    adj_tp = orig_tp
    adj_sl = orig_sl
    reasons = []

    if phase in ['distribution', 'decline']:
        new_sl = entry_price * 1.01
        if new_sl > adj_sl:
            adj_sl = new_sl
            reasons.append(f'phase={phase} → 止损上移至保本+1%')

    if phase == 'distribution':
        adj_tp = entry_price + (orig_tp - entry_price) * 0.6
        reasons.append('distribution → 止盈收紧至60%')
    elif score < 55:
        adj_tp = entry_price + (orig_tp - entry_price) * 0.7
        reasons.append(f'score={score}<55 → 止盈收紧至70%')

    if phase == 'markup' and score >= 80 and profit >= 0.05:
        adj_tp = orig_tp
        reasons.append('markup+A级+5%盈利 → 维持原始止盈')

    return {
        'date': str(df_full.index[date_idx].date()),
        'close': round(close, 2),
        'profit': round(profit, 4),
        'score': round(score, 1),
        'phase': phase,
        'confidence': round(conf, 3),
        'pattern': pat,
        'risk': risk,
        'adj_tp': round(adj_tp, 2),
        'adj_sl': round(adj_sl, 2),
        'reasons': '; '.join(reasons) if reasons else '',
    }

# ==========================================
# 完全覆盖你原来的 worker 函数
# ==========================================
def worker(file_path):
    stock_code_full = os.path.basename(file_path).split('.')[0]
    stock_code = stock_code_full.replace('sh', '').replace('sz', '').replace('bj', '')
    #if not (stock_code.startswith(('60', '688', '00', '300', '92')) and len(stock_code) == 6):
    if not (stock_code.startswith(('68','30', '92')) and len(stock_code) == 6): 
        return None

    try:
        df_daily = data_loader.get_daily_data(file_path)
        if df_daily is None or df_daily.empty: return None
        df_15m = data_loader.get_min_data(stock_code, period='15m')
        historical_df, future_df = get_time_sliced_data(df_daily, EVAL_DATE, FORWARD_DAYS)
        if historical_df is None: return None
        
        m15_slice = None
        if df_15m is not None and not df_15m.empty:
            if 'datetime' in df_15m.columns: df_15m.index = pd.to_datetime(df_15m['datetime'])
            else: df_15m.index = pd.to_datetime(df_15m.index)
            cutoff = pd.to_datetime(f"{historical_df.index[-1].strftime('%Y-%m-%d')} 15:30:00")
            m15_slice = df_15m[df_15m.index <= cutoff].copy()

        if STRATEGY_TO_TEST == 'MORSE_FACTOR_SNIPER':
            from screenergf import apply_morse_sniper_strategy
            res = apply_morse_sniper_strategy(historical_df, df_15m=m15_slice,
                                              stock_code=stock_code_full, end_date=EVAL_DATE)
        else:
            res = None

        if res is None or not res.get('signal'):
            return None

        # 🌟 Debug: 基础模块通过
        debug_logger.info(f"[{stock_code_full}] 基础模块通过! 基础分: {res.get('score')}")

        # ==========================================
        # GBM 概率过滤 (新增)
        # ==========================================
        _init_gbm_scorer()
        if _gbm_enabled and _gbm_scorer is not None:
            try:
                # Scheme C 基础过滤
                ma_slope = res.get('ma_slope', 0)
                board_params = get_board_params(stock_code)
                board_type = board_params.get('board_type', '10CM')
                
                if ma_slope > -0.02 or board_type != '20CM':
                    debug_logger.info(f"[{stock_code_full}] ❌ Scheme C 淘汰: slope={ma_slope:.3f}, board={board_type}")
                    logger.debug(f"GBM: {stock_code_full} 未通过 Scheme C (slope={ma_slope:.3f}, board={board_type})")
                    return None
                
                # GBM 打分
                signal_df = pd.DataFrame([{
                    'ma_slope': ma_slope,
                    'bias_20': res.get('bias_20', 0),
                    'score': res.get('score', 95),
                    'market_env': res.get('v44_trend', ''),
                    'v44_trend': res.get('v44_trend', ''),
                    'v44_bias_tier': res.get('v44_bias_tier', ''),
                }])
                
                gbm_proba = _gbm_scorer.score(signal_df)[0]
                
                if gbm_proba < _gbm_threshold:
                    debug_logger.info(f"[{stock_code_full}] ❌ 被 GBM 淘汰: Prob = {gbm_proba:.4f} < {_gbm_threshold}")
                    logger.debug(f"GBM: {stock_code_full} proba={gbm_proba:.3f} < {_gbm_threshold}")
                    return None
                
                res['gbm_proba'] = gbm_proba
                debug_logger.info(f"[{stock_code_full}] 🚀 GBM 放行: Prob = {gbm_proba:.4f} >= {_gbm_threshold}")
                logger.info(f"GBM: {stock_code_full} ✓ proba={gbm_proba:.3f} >= {_gbm_threshold}")
                
            except Exception as e:
                debug_logger.error(f"[{stock_code_full}] GBM 预测时发生代码异常: {e}")
                logger.warning(f"GBM 打分异常 {stock_code_full}: {e}，降级放行")
        else:
            debug_logger.error(f"[{stock_code_full}] 严重错误: _gbm_scorer 在子进程中为 None！")
        # ==========================================

        strategy_score = res.get('score', 65)
        gbm_proba_val = res.get('gbm_proba', 0.0)

        # V4.4 定价: 优先使用 screenergf 内嵌的动态定价，回退静态板块参数
        v44_ok = 'v44_entry' in res
        v44_meta = {}
        if v44_ok:
            trigger_buy = res['v44_entry']
            target_p = res['v44_target_p']
            stop_l = res['v44_stop_l']
            static_take_profit = res['v44_target']
            static_stop_loss = res['v44_stop']
            v44_meta = {
                'v44_trend': res.get('v44_trend', ''),
                'v44_bias_tier': res.get('v44_bias_tier', ''),
                'v44_grade': res.get('v44_grade', ''),
                'v44_action': res.get('v44_action', ''),
                'v44_entry': trigger_buy,
                'v44_target': static_take_profit,
                'v44_stop': static_stop_loss,
            }
            logger.info(f"📊 V4.4定价 {stock_code_full}: "
                        f"入场={trigger_buy:.2f} 目标={static_take_profit:.2f}({target_p:+.1%}) "
                        f"止损={static_stop_loss:.2f}({stop_l:+.1%}) "
                        f"阶段={v44_meta['v44_trend']} "
                        f"乖离={v44_meta['v44_bias_tier']} "
                        f"等级={v44_meta['v44_grade']}")
        else:
            board_params = get_board_params(stock_code)
            target_p = board_params['target_profit']
            stop_l = board_params['stop_loss']
            trigger_buy = res['trigger_price']
            static_take_profit = trigger_buy * (1 + target_p)
            static_stop_loss = trigger_buy * (1 + stop_l)
            v44_meta = {
                'v44_entry': trigger_buy,
                'v44_target': static_take_profit,
                'v44_stop': static_stop_loss,
            }

        # 加载含全部指标的完整数据（用于每日持仓评估）
        df_full_ind = None
        try:
            df_full_ind = get_full_data_with_indicators(stock_code_full)
        except Exception:
            pass

        # =================================================================
        # 🧬 [核心升级]：全景环境与特征提取 (为下游闭环分析提供弹药)
        # =================================================================
        t0_close = historical_df['close'].iloc[-1]
        t0_date_str = historical_df.index[-1].strftime('%Y-%m-%d')
        
        # 1. 提取日线因子特征
        vol_ma20_d = historical_df['volume'].rolling(20).mean().iloc[-1]
        row_t1 = historical_df.iloc[-1]
        d_pct = (row_t1['close'] - row_t1['open']) / (row_t1['open'] + 1e-9)
        d_vol = row_t1['volume'] / (vol_ma20_d + 1e-9)
        d_lower_shadow = (min(row_t1['close'], row_t1['open']) - row_t1['low']) / (row_t1['open'] + 1e-9)
        
        T1_U = 1 if d_pct > 0.062 else 0
        T1_D = 1 if d_pct < -0.062 else 0
        T1_L = 1 if d_vol < 0.8 else 0
        T1_B = 1 if d_lower_shadow > 0.026 else 0
        
        # 2. 提取 15 分钟特征
        M15_U, M15_L, M15_H = 0, 0, 0
        if m15_slice is not None and len(m15_slice) > 20:
            vol_ma20_m15 = m15_slice['volume'].rolling(20).mean().iloc[-1]
            row_m15 = m15_slice.iloc[-1]
            m_pct = (row_m15['close'] - row_m15['open']) / (row_m15['open'] + 1e-9)
            m_vol = row_m15['volume'] / (vol_ma20_m15 + 1e-9)
            M15_U = 1 if m_pct > 0.0062 else 0
            M15_L = 1 if m_vol < 0.5 else 0
            M15_H = 1 if m_vol > 2.5 else 0
            
        # 3. 提取趋势动能特征 (均线斜率与乖离率)
        ma20 = historical_df['close'].rolling(20).mean().iloc[-1]
        ma60 = historical_df['close'].rolling(60).mean().iloc[-1]
        bias_20 = (t0_close - ma20) / ma20  # 乖离率，判断是否离均线太远
        
        try:
            ma20_prev = historical_df['close'].rolling(20).mean().iloc[-5]
            ma_slope = (ma20 - ma20_prev) / ma20_prev # 5日均线斜率，判断上升动能
        except:
            ma_slope = 0.0
            
        # 4. 提取大盘当日环境 (极其重要，判断 Beta 风险)
        market_env = "震荡"
        index_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc/sh/lday/sh000001.day")
        if os.path.exists(index_path):
            df_index = data_loader.get_daily_data(index_path)
            if t0_date_str in df_index.index:
                idx_loc = df_index.index.get_loc(t0_date_str)
                if idx_loc > 0:
                    idx_pct = (df_index['close'].iloc[idx_loc] - df_index['close'].iloc[idx_loc-1]) / df_index['close'].iloc[idx_loc-1]
                    if idx_pct > 0.01: market_env = "顺风大涨"
                    elif idx_pct < -0.015: market_env = "股灾暴跌"
                    elif idx_pct < -0.005: market_env = "弱势阴跌"
        
        # 特征字符串 & v5 评分: 见下方 [v5 评分重构] 块, 统一生成
        # =================================================================

        # =================================================================
        # 🎯 [v5 评分重构] T1_D + GBM 门控评分 (回测驱动)
        # ----------------------------------------------------------------------
        # 旧评分 (screenergf): base=95, T1_D=-10 (扣分), M15_U=+15 (加分)
        #   回测 4264 笔结论: 旧评分方向与收益完全相反
        #     - 旧 85 分 (T1_D=1): 胜率 75.0%, PF=10.38  ← 真正的牛股信号
        #     - 旧 95 分 (基线)   : 胜率 47.1%, PF= 2.02  ← 平庸池
        #     - 旧 110+ (M15_U=1) : 胜率 37.5%, PF= 1.99  ← 假爆发
        #   叠加 GBM 门控后, T1_D=1 & GBM>=0.80 达到 PF=228.78 (胜率 84.3%)
        # 新评分 (v5):
        #   S-tier 120 : T1_D=1 + GBM>=0.80  (核心持仓, PF>100)
        #   A-tier 110 : T1_D=1 + GBM>=0.75  (重点仓, PF~76)
        #   B-tier  95 : T1_D=1 + GBM<0.75    (洗盘候选, 需观察)
        #             or GBM>=0.70             (常规高质量)
        #   C-tier  70 : 其他                  (低优先, 但回测显示正 EV 不拒绝)
        # M15_U 不再加分 (回测 PF 仅 1.99, 与基线无差异)
        # =================================================================
        screenergf_score = strategy_score  # 保留原始分, 用于溯源与回归校验
        new_score = 70                      # C-tier 默认
        if T1_D == 1:
            if gbm_proba_val >= 0.80:
                new_score = 120             # S-tier (洗盘+强GBM确认)
            elif gbm_proba_val >= 0.75:
                new_score = 110             # A-tier
            else:
                new_score = 95              # B-tier (洗盘候选, 待观察)
        elif gbm_proba_val >= 0.70:
            new_score = 95                  # B-tier (GBM 单确认)
        # 若 GBM 模块未启用 (gbm_proba_val=0), 则保留 screenergf 原始分, 避免全部落入 70
        if gbm_proba_val == 0.0:
            new_score = screenergf_score
        strategy_score = new_score
        morse_features = (
            f"S:{strategy_score}|OS:{screenergf_score}|MKT:{market_env}|"
            f"B20:{bias_20:.3f}|T1_U:{T1_U}|T1_D:{T1_D}|T1_L:{T1_L}|T1_B:{T1_B}|"
            f"M15_U:{M15_U}|M15_L:{M15_L}|M15_H:{M15_H}|GBM:{gbm_proba_val:.3f}"
        )
        debug_logger.info(
            f"[{stock_code_full}] 🎯 v5评分: {screenergf_score}->{strategy_score} "
            f"(T1_D={T1_D}, M15_U={M15_U}, GBM={gbm_proba_val:.3f})"
        )
        # v5 tier 标签 (回测分析用, 与 v5 评分块保持同步)
        if   new_score == 120:                v5_tier_label = 'S'
        elif new_score == 110:                v5_tier_label = 'A'
        elif new_score == 95  and T1_D == 1:  v5_tier_label = 'B_T1D'
        elif new_score == 95:                 v5_tier_label = 'B_GBM'
        else:                                 v5_tier_label = 'C'
        # =================================================================
        
        if future_df.empty:
            return {
                'stock_code': stock_code_full, 'eval_date': historical_df.index[-1].strftime('%Y-%m-%d'),
                'entry_date': "", 'exit_date': "", 'future_min_low': 0.0, 'future_max_high': 0.0,
                'strategy': STRATEGY_TO_TEST, 'trade_status': "等待实盘验证(T+1)",
                'final_pnl': 0.0, 'MFE': 0.0, 'MAE': 0.0, 'holding_days': 0, 'entry_slip': 0.0,
                '买入价': trigger_buy, '止损价': static_stop_loss,
                '评估分': strategy_score, 'gbm_proba': gbm_proba_val, 'ma_slope': ma_slope,
                'pricing_proba': 0.5,
                'close_t0': t0_close, 'bias_20': bias_20, 'swing': 0.0,
                't1_open': 0.0, 't1_high': 0.0, 't1_low': 0.0, 't1_close': 0.0,
                'morse_features': morse_features, 'future_7d_path': "",
                'daily_journal': "", 'selection_verdict': "",
                # ---- v5 新增字段 (保持 schema 一致) ----
                'v5_score': strategy_score, 'v5_tier': v5_tier_label,
                'screenergf_score': screenergf_score,
                'T1_D': T1_D, 'T1_U': T1_U, 'T1_L': T1_L, 'T1_B': T1_B, 'M15_U': M15_U,
                'is_entry': False, 'exit_type': 'pending',
                'market_env': market_env,
                **v44_meta
            }

        # =================================================================
        # V4.7 入场定价: 固定浅挂 ×0.99 (回测验证最优)
        # 回测报告结论: 固定浅挂 EV=+2.187% > GBM自适应 +2.050%
        # GBM 概率保留用于信号优先级排序，不调整入场价
        # =================================================================
        _init_pricing_gbm()
        pricing_proba = 0.5
        if _pricing_enabled and _pricing_model is not None and not future_df.empty:
            try:
                t1_row = future_df.iloc[0]
                swing_val = (future_df['high'].max() - future_df['low'].min()) / t0_close

                pricing_input = pd.DataFrame([{
                    'close_t0': t0_close,
                    'T1_Open': t1_row['open'], 'T1_High': t1_row['high'],
                    'T1_Low': t1_row['low'], 'T1_Close': t1_row['close'],
                    'ma_slope': ma_slope,
                    'bias_20': bias_20,
                    'swing': swing_val,
                    'v44_trend': res.get('v44_trend', ''),
                    'v44_bias_tier': res.get('v44_bias_tier', ''),
                    'market_env': market_env,
                }])
                pricing_proba = float(score_entry_strategy(pricing_input, _pricing_model, _pricing_meta)[0])
                debug_logger.info(f"[{stock_code_full}] 定价GBM: proba={pricing_proba:.3f}")
            except Exception as e:
                debug_logger.warning(f"[{stock_code_full}] 定价GBM异常: {e}，proba=0.5")

        trigger_buy = round(t0_close * 0.99, 2)

        # V4.9 TP/SL: 统一 TP=10% (验证回测: TP10%+entry_pos<=0.5 → 87.1%胜率)
        board_params = get_board_params(stock_code)
        board_type = board_params.get('board_type', '10CM')
        v44_trend = res.get('v44_trend', '')
        v44_bias = res.get('v44_bias_tier', '')

        v46_tp = 0.10
        if board_type == '20CM':
            v46_sl = -0.12
            if v44_trend == 'markup' and v44_bias == '空头偏离(-15%~-5%)':
                v46_sl = -0.07
        else:
            v46_sl = -0.10

        static_take_profit = round(trigger_buy * (1 + v46_tp), 2)
        static_stop_loss = round(trigger_buy * (1 + v46_sl), 2)
        target_p = v46_tp
        stop_l = v46_sl

        future_min_low = future_df['low'].min()
        future_max_high = future_df['high'].max()

        price_range = future_max_high - future_min_low
        entry_pos = (trigger_buy - future_min_low) / price_range if price_range > 0 else 0.5
        if entry_pos > 0.5:
            debug_logger.info(f"[{stock_code_full}] entry_pos={entry_pos:.3f}>0.5, 信号位置偏高，跳过")
            return None

        logger.info(f"📊 V4.9定价 {stock_code_full}: 入场={trigger_buy:.2f}(浅挂×0.99) "
                    f"TP={static_take_profit:.2f}({v46_tp:+.0%}) SL={static_stop_loss:.2f}({v46_sl:+.0%}) "
                    f"entry_pos={entry_pos:.3f} pricing_proba={pricing_proba:.3f} 持仓=15d")

        swing_7d = (future_max_high - future_min_low) / t0_close if t0_close > 0 else 0.0
        t1_row = future_df.iloc[0]
        t1_open = float(t1_row['open'])
        t1_high = float(t1_row['high'])
        t1_low = float(t1_row['low'])
        t1_close = float(t1_row['close'])
        
        trade_status = "未成交"
        entry_price, exit_price, mfe_raw, mae_raw, holding_days = 0.0, 0.0, 0.0, 0.0, 0
        entry_date, exit_date = "", ""
        pending_days = 0
        daily_journal = []
        
        actual_take_profit = 0.0
        actual_stop_loss = 0.0
        orig_take_profit = 0.0
        orig_stop_loss = 0.0
        
        for idx, row in future_df.iterrows():
            current_date_str = idx.strftime('%Y-%m-%d')
            
            if trade_status == "未成交":
                pending_days += 1
                if pending_days > 5: 
                    trade_status = "挂单超时撤销"
                    break
                
                open_price = row['open']
                low_price = row['low']
                
                # 🚨 Grok 终极防御 1：跳空低开核按钮过滤 (开盘直接跌破买点 3.5%，绝不接刀)
                if open_price <= trigger_buy * 0.965:
                    trade_status = "大幅低开放弃"
                    break
                    
                # 🚨 Grok 终极防御 2：开盘定生死 (高开回落可以接，低开闷杀不能接)
                # 如果开盘价连昨天收盘价的 -2% 都不到，说明势头完全坏了，撤单。
                #if open_price <= t0_close * 0.98:
                #    trade_status = "弱势低开撤单"
                #    break

                # 正常撮合：摸到挂单价
                if low_price <= trigger_buy:
                    # 🚨 Grok 终极防御 3：必须有资金承接（不能收在最低点附近）
                    # 收盘价必须比最低价拉起 0.8%，否则说明接刀子接到半山腰了，假装没看见
                    if row['close'] >= low_price * 1.005:
                        trade_status = "持仓中"
                        entry_date = current_date_str
                        
                        # 🚨 修复滑点灾难：min() 取孰低，永远不当接盘侠
                        entry_price = min(trigger_buy, open_price * 0.995) 
                        
                        actual_take_profit = entry_price * (1 + target_p)
                        actual_stop_loss = entry_price * (1 + stop_l)
                        orig_take_profit = actual_take_profit
                        orig_stop_loss = actual_stop_loss
                        
                        # 日内刺穿防线
                        if low_price <= actual_stop_loss or row['close'] <= actual_stop_loss:
                            trade_status = "止损出局"
                            exit_price = row['close']
                            exit_date = current_date_str
                            mae_raw = (low_price - entry_price) / entry_price
                            break
                    else:
                        continue # 今天没接稳，不买，等明天
            
            elif trade_status == "持仓中":
                holding_days += 1
                curr_profit = (row['high'] - entry_price) / entry_price
                curr_drawdown = (row['low'] - entry_price) / entry_price

                if curr_profit > mfe_raw: mfe_raw = curr_profit
                if curr_drawdown < mae_raw: mae_raw = curr_drawdown

                # =========================================================
                # 🛡️ V4.6 追踪止损: 已禁用 (扫描器显示追踪止损损害收益)
                # 原逻辑: mfe_raw >= 0.03 → trail_sl = entry * (1 + mfe * 0.60)
                # V4.6: 不启用追踪止损，仅依赖固定止损和止盈
                # =========================================================
                trail_sl = actual_stop_loss
                if trail_sl > actual_stop_loss:
                    actual_stop_loss = trail_sl

                # =========================================================
                # 🚨 v4.5 动态防线 1b：688/689/300/920 板块盘中 -8% 硬熔断
                # Test 5b 实测: 688/920 中 67 笔盘中跌穿 -8% 止损线,
                # 必须设置无条件强平条件, 防范跳空穿透风险。
                # =========================================================
                if stock_code.startswith(('688', '689', '300', '920')):
                    intraday_drop = (row['low'] - entry_price) / entry_price
                    if intraday_drop <= -0.08:
                        trade_status = "板块熔断强平"
                        # 以 -8% 市价出, 考虑跳空穿透用 open 与 -8% 孰低
                        exit_price = min(row['open'], entry_price * 0.92)
                        exit_date = current_date_str
                        break

                # =========================================================
                # 📊 每日持仓评估 + 动态止盈止损调整
                # =========================================================
                if df_full_ind is not None and idx in df_full_ind.index:
                    try:
                        fidx = df_full_ind.index.get_loc(idx)
                        daily_eval = _evaluate_daily_position(
                            df_full_ind, fidx, entry_price,
                            orig_take_profit, orig_stop_loss)
                        daily_journal.append(daily_eval)

                        eval_sl = daily_eval['adj_sl']
                        eval_tp = daily_eval['adj_tp']
                        if eval_sl > actual_stop_loss:
                            actual_stop_loss = eval_sl
                        if eval_tp < actual_take_profit:
                            actual_take_profit = eval_tp
                    except Exception as e:
                        logger.warning(f"每日评估异常 {stock_code_full} {current_date_str}: {e}")

                # =========================================================
                # 🛡️ 动态防线 2：异常破位斩仓 (日内出现实体大阴线派发)
                # =========================================================
                # 如果今天收盘价比开盘价大跌超过 4.5%（放量杀跌形态），说明趋势破坏
                daily_body_drop = (row['close'] - row['open']) / (row['open'] + 1e-9)
                # 科创/创业板 (20CM) 波动大，容忍度放到 -7%
                if stock_code.startswith(('688', '689', '300', '920')):
                    breakdown_threshold = -0.09
                else:
                    breakdown_threshold = -0.065
                if daily_body_drop <= breakdown_threshold:
                    trade_status = "形态破坏斩仓"
                    exit_price = row['close']  # 直接以大阴线收盘价砍仓，不等到明天
                    exit_date = current_date_str
                    break

                # =========================================================
                # V4.9 时间衰减: 15天窗口 (到期分析: 44.6%后续触及10%TP)
                # T+7 且 MFE<-5%: 深度负收益, 真亏损退出;
                # T+10 且 MFE<1%: 10天零动能, 放弃;
                # T+15: 最终兜底。
                # (低MFE≈洗盘, 不提前退出 — 到期分析核心发现)
                # =========================================================
                if holding_days >= 7 and mfe_raw < -0.05:
                    trade_status = "时间衰减平仓"
                    exit_price = row['close']
                    exit_date = current_date_str
                    break
                if holding_days >= 10 and mfe_raw < 0.01:
                    trade_status = "时间衰减平仓"
                    exit_price = row['close']
                    exit_date = current_date_str
                    break
                if holding_days >= 15:
                    trade_status = "持仓到期"
                    exit_price = row['close']
                    exit_date = current_date_str
                    break

                # =========================================================
                # 🏁 常规硬性止盈 / 止损判定 (带滑点修复)
                # =========================================================
                if row['high'] >= actual_take_profit:
                    trade_status = "止盈成功"
                    # 防范直接跳空高开越过止盈价，取 孰高者
                    exit_price = max(row['open'], actual_take_profit)
                    exit_date = current_date_str
                    break
                
                if row['low'] <= actual_stop_loss:
                    trade_status = "止损出局"
                    # 防范跳空低开直接砸穿移动止损线，取 孰低者
                    exit_price = min(row['open'], actual_stop_loss)
                    exit_date = current_date_str
                    break

        if trade_status == "持仓中":
            exit_price = future_df.iloc[-1]['close']
            trade_status = "持仓到期"
            exit_date = future_df.index[-1].strftime('%Y-%m-%d')

        path_list = []
        for idx, r in future_df.iterrows():
            high_pct = (r['high'] - t0_close) / t0_close * 100
            low_pct = (r['low'] - t0_close) / t0_close * 100
            path_list.append(f"H:{high_pct:+.1f}%/L:{low_pct:+.1f}%")
        future_7d_path = " -> ".join(path_list)

        final_pnl = (exit_price - entry_price)/entry_price if entry_price > 0 else 0.0

        if mfe_raw >= 0.03 or final_pnl > 0:
            selection_verdict = '合理'
        elif mfe_raw >= 0.01:
            selection_verdict = '边际'
        else:
            selection_verdict = '失败'

        # 计算完整 7 天窗口的最大潜在涨幅/跌幅 (不受实际出场时机影响)
        ref_price = entry_price if entry_price > 0 else trigger_buy
        future_mfe = (future_max_high - ref_price) / ref_price if ref_price > 0 else 0.0
        future_mae = (future_min_low - ref_price) / ref_price if ref_price > 0 else 0.0

        # ---- 出场类型枚举 (回测分组用) ----
        exit_type_map = {
            '止盈成功':     'take_profit',
            '止损出局':     'stop_loss',
            '持仓到期':     'expired',
            '时间衰减平仓': 'time_decay',
            '板块熔断强平': 'circuit_breaker',
            '形态破坏斩仓': 'form_break',
            '挂单超时撤销': 'order_timeout',
            '大幅低开放弃': 'gap_abandoned',
            '未成交':       'not_filled',
        }
        exit_type_en = exit_type_map.get(trade_status, 'unknown')
        is_entry_flag = trade_status not in ('挂单超时撤销', '大幅低开放弃', '未成交')

        return {
            'stock_code': stock_code_full,
            '回测日期': historical_df.index[-1].strftime('%Y-%m-%d'),
            '成交日期': entry_date, '卖出日期': exit_date,
            '回测底': future_min_low, '回测顶': future_max_high,
            'trigger_buy': trigger_buy, 'stop_loss': static_stop_loss,
            '价格偏离': (trigger_buy - future_min_low)/trigger_buy if trade_status == "挂单超时撤销"   else (entry_price - future_min_low) / entry_price ,
            'strategy': STRATEGY_TO_TEST, '交易状态': trade_status,
            '收益率': final_pnl,
            'MFE': mfe_raw, 'MAE': mae_raw,
            'future_mfe': future_mfe, 'future_mae': future_mae,
            '持仓天数': holding_days,
            'entry_slip': (entry_price - trigger_buy)/trigger_buy if entry_price > 0 else 0.0,
            '评估分': strategy_score, 'gbm_proba': gbm_proba_val, 'ma_slope': ma_slope,
            'pricing_proba': pricing_proba, 'entry_pos': entry_pos,
            'close_t0': t0_close, 'bias_20': bias_20, 'swing': swing_7d,
            't1_open': t1_open, 't1_high': t1_high, 't1_low': t1_low, 't1_close': t1_close,
            'morse_features': morse_features, 'future_7d_path': future_7d_path,
            'daily_journal': json.dumps(daily_journal, ensure_ascii=False) if daily_journal else "",
            'selection_verdict': selection_verdict,
            # ---- v5 新增字段 ----
            'v5_score': strategy_score,
            'v5_tier': v5_tier_label,
            'screenergf_score': screenergf_score,
            'T1_D': T1_D, 'T1_U': T1_U, 'T1_L': T1_L, 'T1_B': T1_B, 'M15_U': M15_U,
            'is_entry': is_entry_flag,
            'exit_type': exit_type_en,
            'market_env': market_env,
            **v44_meta
        }
    except Exception as e:
        logger.error(f"Error processing {file_path}: {e}")
        return None

def save_and_report_results(results):
    if not results: return
    df_res = pd.DataFrame(results)

    # ---- 每日维度字段 (需要跨信号聚合, 在主进程计算) ----
    # daily_signal_count: 当日总信号数 (含未成交)
    # daily_signal_rank : 当日按 (v5_score, gbm_proba, pricing_proba) 降序排列的名次 1..K
    try:
        date_col = '回测日期' if '回测日期' in df_res.columns else 'eval_date'
        df_res['daily_signal_count'] = df_res.groupby(date_col)[date_col].transform('size')

        _gbm = df_res['gbm_proba'].fillna(0).astype(float) if 'gbm_proba' in df_res.columns else pd.Series(0.0, index=df_res.index)
        _v5 = df_res['v5_score'].fillna(0).astype(float) if 'v5_score' in df_res.columns else pd.Series(0.0, index=df_res.index)
        _pricing = df_res['pricing_proba'].fillna(0.5).astype(float) if 'pricing_proba' in df_res.columns else pd.Series(0.5, index=df_res.index)

        if 'v5_score' in df_res.columns:
            rank_key = _v5 * 1e9 + _gbm * 1e6 + _pricing * 1e3
            df_res['_rk'] = rank_key
            df_res['daily_signal_rank'] = df_res.groupby(date_col)['_rk'].rank(
                ascending=False, method='first').astype(int)
            df_res.drop(columns=['_rk'], inplace=True)
        else:
            df_res['daily_signal_rank'] = 0

        # ---- 排序: 有数据的靠前, 为0的靠后 ----
        # _has_data: 1=有实际成交/收益, 0=空行/未成交/全零
        if 'is_entry' in df_res.columns:
            df_res['_has_data'] = df_res['is_entry'].fillna(False).astype(bool).astype(int)
        elif '收益率' in df_res.columns:
            df_res['_has_data'] = (df_res['收益率'].fillna(0).astype(float) != 0).astype(int)
        else:
            df_res['_has_data'] = 1

        if 'v5_tier' in df_res.columns:
            tier_order = {'S': 0, 'A': 1, 'B_T1D': 2, 'B_GBM': 2, 'C': 3, 'pending': 4}
            df_res['_tier_ord'] = df_res['v5_tier'].map(tier_order).fillna(9)
        else:
            df_res['_tier_ord'] = 9

        sort_cols = [date_col, '_has_data', '_tier_ord', 'v5_score', 'gbm_proba']
        asc_flags = [True, False, True, False, False]

        existing_cols = []
        existing_asc = []
        for col, asc in zip(sort_cols, asc_flags):
            if col in df_res.columns:
                existing_cols.append(col)
                existing_asc.append(asc)

        df_res = df_res.sort_values(existing_cols, ascending=existing_asc).reset_index(drop=True)
        df_res.drop(columns=[c for c in ['_tier_ord', '_has_data'] if c in df_res.columns], inplace=True)
    except Exception as e:
        logger.warning(f"每日信号排名计算失败: {e}, 写入默认值")
        df_res['daily_signal_count'] = 0
        df_res['daily_signal_rank'] = 0

    latest_csv_path = os.path.join(backend_dir, 'latest_walk_forward.csv')
    df_res.to_csv(latest_csv_path, index=False, float_format='%.4f')
    logger.info(f"💾 莫尔斯加权狙击选股测试数据已保存至: {latest_csv_path}")

    journal_rows = []
    for _, row in df_res.iterrows():
        j = row.get('daily_journal', '')
        if j and isinstance(j, str) and j.startswith('['):
            try:
                entries = json.loads(j)
                for e in entries:
                    e['stock_code'] = row['stock_code']
                    e['交易状态'] = row.get('交易状态', '')
                    e['收益率'] = row.get('收益率', 0)
                    e['MFE'] = row.get('MFE', 0)
                    e['future_mfe'] = row.get('future_mfe', 0)
                    e['future_mae'] = row.get('future_mae', 0)
                    e['gbm_proba'] = row.get('gbm_proba', 0.0)
                    e['v5_score'] = row.get('v5_score', 0)
                    e['v5_tier'] = row.get('v5_tier', '')
                    journal_rows.append(e)
            except Exception:
                pass
    if journal_rows:
        df_journal = pd.DataFrame(journal_rows)
        if 'v5_tier' in df_journal.columns:
            _jtier = {'S': 0, 'A': 1, 'B_T1D': 2, 'B_GBM': 2, 'C': 3, 'pending': 4}
            df_journal['_tord'] = df_journal['v5_tier'].map(_jtier).fillna(9)
            _jsort = ['_tord']
            _jasc = [True]
            if 'v5_score' in df_journal.columns:
                _jsort += ['v5_score']; _jasc += [False]
            if 'gbm_proba' in df_journal.columns:
                _jsort += ['gbm_proba']; _jasc += [False]
            df_journal = df_journal.sort_values(_jsort, ascending=_jasc).reset_index(drop=True)
            df_journal.drop(columns=['_tord'], inplace=True)
        journal_path = os.path.join(backend_dir, 'latest_daily_journal.csv')
        df_journal.to_csv(journal_path, index=False, float_format='%.4f')
        logger.info(f"📊 每日持仓评估日志已保存至: {journal_path} ({len(journal_rows)} 条)")

if __name__ == '__main__':
    vipdoc_base = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    files = glob.glob(os.path.join(vipdoc_base, "sh", "lday", "*.day")) + \
            glob.glob(os.path.join(vipdoc_base, "sz", "lday", "*.day")) + \
            glob.glob(os.path.join(vipdoc_base, "bj", "lday", "*.day")) 
            
    # 🌟 核心修复: 使用 initializer 确保每个子进程独立加载 GBM 模型
    # 避免多进程 spawn 模式下全局变量不继承的问题
    with Pool(processes=cpu_count(), initializer=_init_gbm_scorer) as pool:
        raw_results = pool.map(worker, files)
        
    valid_results = [r for r in raw_results if r is not None]
    
    if valid_results:
        # 按照莫尔斯矩阵的打分高低进行系统优先级降序排列
        valid_results.sort(key=lambda x: (x.get('fit_score', 0), x.get('ma_slope', 0)), reverse=True)
        
        MAX_LIMIT = 1000
        if len(valid_results) > MAX_LIMIT:
            logger.info(f"⚠️ 今日满足强共振个股共 {len(valid_results)} 只，执行机构级 Top {MAX_LIMIT} 容量截断！")
            valid_results[:] = valid_results[:MAX_LIMIT]
            
    save_and_report_results(valid_results)
