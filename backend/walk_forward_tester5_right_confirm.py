import os
import glob
import json
import logging
import pandas as pd
import numpy as np
from datetime import datetime
from multiprocessing import Pool, cpu_count
import data_loader
import talib

from screenergf import apply_adaptive_ma_support_optimized

# ==========================================
# === 评估任务全局配置 ===
# ==========================================
STRATEGY_TO_TEST = 'ADAPTIVE_MA_SUPPORT' 
EVAL_DATE = '2026-4-1'  
FORWARD_DAYS = 7        
TARGET_PROFIT = 0.20   
DECAY_PROFIT = 0.15    

backend_dir = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.abspath(os.path.join(backend_dir, '..', 'data', 'result'))
DATE_STR = datetime.now().strftime("%Y%m%d_%H%M")
RESULT_DIR = os.path.join(OUTPUT_PATH, f'WalkForward_{STRATEGY_TO_TEST}')
os.makedirs(RESULT_DIR, exist_ok=True)

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

def generate_strategy_signals(df, strategy_name):
    current_price = df['close'].iloc[-1]
    if strategy_name == 'ADAPTIVE_MA_SUPPORT':
        signal_series = apply_adaptive_ma_support_optimized(df)
        if signal_series is None or not signal_series.iloc[-1]: 
            return False, 0, 0, {}
        
        ma_val = getattr(signal_series, 'current_ma_val', current_price)
        deep_touches = getattr(signal_series, 'deep_touches', 0)
        is_deep_wash = getattr(signal_series, 'is_deep_wash', False)
        
        # ---------------------------------------------------------
        # 🔬 提取近期微观结构：诊断是否属于“高位断崖暴跌”
        # ---------------------------------------------------------
        # 1. 计算近 5 个交易日内的最高点，评估短期重力势能
        recent_5d_high = df['high'].iloc[-5:].max()
        recent_5d_low = df['low'].iloc[-5:].min()
        short_term_drop = (recent_5d_low - recent_5d_high) / recent_5d_high
        
        # 2. 计算当天的量能状态 (判断抛压是否释放完毕)
        vol_ma13 = df['volume'].rolling(13).mean().iloc[-1]
        curr_vol_ratio = df['volume'].iloc[-1] / vol_ma13 if vol_ma13 > 0 else 1.0

        # ---------------------------------------------------------
        # ⚖️ 基础挂单档位判定
        # ---------------------------------------------------------
        if is_deep_wash or deep_touches > 10:
            trigger_buy = ma_val * 0.96      # 极端深踩单：下浮4%基础接针
            stop_loss = ma_val * 0.88        
        else:
            trigger_buy = ma_val * 1.005     # 临界宽容单：基础常规买点
            stop_loss = ma_val * 0.925       
            
        # ---------------------------------------------------------
        # 🚨 终极补丁：波幅与量能的动态下调机制 (专治sz000631类暴跌)
        # ---------------------------------------------------------
        # 如果短期（5天内）遭遇超过 10% 的极速暴跌，触发动态折价
        if short_term_drop < -0.25: 
            # 基础波动折价：跌得越狠，惯性越大，我们要的安全垫必须越厚
            # 比如跌了 15%，我们额外要求下移 15% * 0.4 = 6% 的接针空间
            volatility_discount = abs(short_term_drop) * 0.4  
            
            # 量能惩罚折价：
            if curr_vol_ratio > 1.2:
                # 放量暴跌说明主力还在疯狂出逃，飞刀极其锋利，额外再往下躲 2.5%
                volatility_discount += 0.015 
            elif curr_vol_ratio < 0.6:
                # 极致缩量说明恐慌盘已经杀不出量了，底部显现，折价可以适当放宽 1%
                volatility_discount -= 0.01  
                
            # 确保至少要有 3% 的额外动态下调
            volatility_discount = max(0.03, volatility_discount) 
            
            # 重新计算极限买入价
            dynamic_trigger = ma_val * (1 - volatility_discount)
            
            # 如果动态计算出的价格比原计划的更低，则采用更低的安全价
            if dynamic_trigger < trigger_buy:
                trigger_buy = dynamic_trigger
                # ⚠️ 极其关键：买入价大幅下调后，止损价必须等比例下移！
                # 统一给买入价下方留出 7.5% 的物理止损空间
                stop_loss = trigger_buy * 0.935

        return (True, trigger_buy, stop_loss, {
            'best_ma': getattr(signal_series, 'best_ma_period', 0),
            'polarity': int(getattr(signal_series, 'polarity_confirmed', False)),
            'fit_score': getattr(signal_series, 'fit_score', 0.0),
            'deep_touches': deep_touches,
            'burst_ratio': getattr(signal_series, 'burst_ratio', 0.0), 
            'is_deep_wash': is_deep_wash,
            'ma_slope': getattr(signal_series, 'ma_slope', 0.0),
            'drop_velocity': getattr(signal_series, 'drop_velocity', 0.0)
        })
    return False, 0, 0, {}

def generate_strategy_signals_0(df, strategy_name):
    current_price = df['close'].iloc[-1]
    if strategy_name == 'ADAPTIVE_MA_SUPPORT':
        signal_series = apply_adaptive_ma_support_optimized(df)
        if signal_series is None or not signal_series.iloc[-1]: 
            return False, 0, 0, {}
        
        ma_val = getattr(signal_series, 'current_ma_val', current_price)
        deep_touches = getattr(signal_series, 'deep_touches', 0)
        is_deep_wash = getattr(signal_series, 'is_deep_wash', False)
        
        # 🔻【精细化临界执行层】：优化买入触发宽容度，捕获高质量踏空标的
        if is_deep_wash or deep_touches > 14:
            trigger_buy = ma_val * 0.96      # 极端深踩单：下浮4%无悬念接针
            stop_loss = ma_val * 0.88        # 物理底线防线
        else:
            trigger_buy = ma_val * 1.005     # 临界宽容单：主动放宽0.5%滑点空间，杜绝一分钱踏空
            stop_loss = ma_val * 0.925       
            
        return (True, trigger_buy, stop_loss, {
            'best_ma': getattr(signal_series, 'best_ma_period', 0),
            'polarity': int(getattr(signal_series, 'polarity_confirmed', False)),
            'fit_score': getattr(signal_series, 'fit_score', 0.0),
            'deep_touches': deep_touches,
            'burst_ratio': getattr(signal_series, 'burst_ratio', 0.0), 
            'is_deep_wash': is_deep_wash,
            'ma_slope': getattr(signal_series, 'ma_slope', 0.0),
            'drop_velocity': getattr(signal_series, 'drop_velocity', 0.0)
        })
    return False, 0, 0, {}

def worker(file_path):
    stock_code_full = os.path.basename(file_path).split('.')[0]
    stock_code = stock_code_full.replace('sh', '').replace('sz', '').replace('bj', '')
    if not (stock_code.startswith(('60', '688', '00', '300')) and len(stock_code) == 6): 
        return None

    try:
        df = data_loader.get_daily_data(file_path)
        if df is None: return None
        
        historical_df, future_df = get_time_sliced_data(df, EVAL_DATE, FORWARD_DAYS)
        if historical_df is None: return None
        
        has_signal, trigger_buy, stop_loss, features = generate_strategy_signals(historical_df, STRATEGY_TO_TEST)
        if not has_signal: return None

        # 处理 T+1 预演输出执行卡
        if future_df.empty:
            return {
                'stock_code': stock_code_full, 'eval_date': historical_df.index[-1].strftime('%Y-%m-%d'),
                'entry_date': "", 'exit_date': "", 'future_min_low': 0.0, 'future_max_high': 0.0,
                'strategy': STRATEGY_TO_TEST, 'trade_status': "等待实盘验证(T+1)",
                'final_pnl': 0.0, 'MFE': 0.0, 'MAE': 0.0, 'holding_days': 0, 'entry_slip': 0.0,
                'trigger_buy': trigger_buy, 'stop_loss': stop_loss,
                'fit_score': features.get('fit_score', 0.0), 'best_ma': features.get('best_ma', 0),
                'deep_touches': features.get('deep_touches', 0), 'polarity': features.get('polarity', 0),
                'burst_ratio': features.get('burst_ratio', 0.0), 'is_deep_wash': int(features.get('is_deep_wash', False)),
                'ma_slope': features.get('ma_slope', 0.0), 'drop_velocity': features.get('drop_velocity', 0.0)
            }

        
        future_min_low = future_df['low'].min() if not future_df.empty else 0.0
        future_max_high = future_df['high'].max() if not future_df.empty else 0.0
        
        # =================================================================
        # 🛡️ 引入大盘环境风控 & 动态买点下调 (Beta Shield & Dynamic Entry)
        # =================================================================
        index_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc/sh/lday/sh000001.day")
        df_index = data_loader.get_daily_data(index_path)
        #中证1000 sh000852 sz000852
        trade_status = "未成交"
        entry_price, exit_price, mfe_raw, mae_raw, holding_days = 0.0, 0.0, 0.0, 0.0, 0
        entry_date, exit_date = "", ""
        
        # 🔒 锁死锁：锁死成交当天的真实止损，防止持仓期大盘变化导致止损线漂移
        actual_stop_loss = 0.0 
        pending_days = 0
        
        # 🔑 从特征包中安全安全提取个股专属专属的生命均线元数据
        t0_close = historical_df['close'].iloc[-1]
        ma_val = features.get('current_ma_val', t0_close) if 'features' in locals() else t0_close
        ma_slope = features.get('ma_slope', 0.0) if 'features' in locals() else 0.0
        # 🔒 提取周线级别的极限物理低点防线，建立安全降级
        weekly_floor_low = features.get('weekly_floor_low', historical_df['low'].iloc[-150:].min())
        
        # 📊 初始化前一日K线矩阵，首日使用T+0（选股日）的真实历史数据
        prev_row_data = {
            'close': t0_close,
            'high': historical_df['high'].iloc[-1],
            'low': historical_df['low'].iloc[-1]
        }
        
        for idx, row in future_df.iterrows():
            current_date_str = idx.strftime('%Y-%m-%d')
            pending_days += 1
            
            # ---------------------------------------------------------
            # 大盘状态机解析 (严格对齐你收益最好的经典参数)
            # ---------------------------------------------------------
            market_crash_today = False
            market_peak_dumping = False  
            index_drop = 0.0
            drawdown_from_peak = 0.0
            
            if df_index is not None and idx in df_index.index:
                idx_loc = df_index.index.get_loc(idx)
                if idx_loc > 20: 
                    prev_index_close = df_index.iloc[idx_loc - 1]['close']
                    today_index_close = df_index.iloc[idx_loc]['close']
                    
                    index_drop = (today_index_close - prev_index_close) / prev_index_close
                    
                    # 1. 单日暴跌熔断（防范系统性踩踏）
                    if index_drop < -0.062:
                        market_crash_today = True
                        
                    # 2. 顶点抛售情绪识别
                    recent_7d_high = df_index.iloc[idx_loc-7:idx_loc]['high'].max()
                    drawdown_from_peak = (today_index_close - recent_7d_high) / recent_7d_high
                    
                    if drawdown_from_peak < -0.15 and index_drop < -0.05:
                        market_peak_dumping = True

            # ---------------------------------------------------------
            # 交易执行逻辑：严格采用原版骨架 (基于静态 trigger_buy 和斜率追踪)
            # ---------------------------------------------------------
            if trade_status == "未成交":
                # ⏳ 动态挂单有效期：深水区或高风险环境允许等4天，常规环境2天
                max_pending_days = 7 
                if pending_days > max_pending_days:
                    trade_status = "挂单超时撤销"
                    break
                # 提取微观特征，用于开放绿色通道
                burst_ratio = features.get('burst_ratio', 0.0)
                vol_ratio = row['volume'] / (historical_df['volume'].iloc[-20:].mean() + 1e-9) if len(historical_df) >= 20 else 1.0

                # 📈 均线动态增量追踪：计算T+N天真实的专属均线预期位置
                current_realtime_ma = ma_val * (1 + ma_slope * pending_days)

                # =======================================================
                # 🔄 回归经典：按你收益最好的原版大盘定价矩阵执行
                # =======================================================
                if market_crash_today:
                    # 股灾血筹：指数单日暴跌时，根据跌幅深度动态下劈买卖网
                    dynamic_trigger_buy = weekly_floor_low * 0.98 #trigger_buy * (1 + index_drop * 1.4)
                    dynamic_stop_loss = dynamic_trigger_buy * 0.92
                elif market_peak_dumping:
                    # 顶点抛售期：根据大盘波段回撤比例下调
                    dynamic_trigger_buy = trigger_buy * (1 + drawdown_from_peak / 3)
                    dynamic_stop_loss = stop_loss * (1 + drawdown_from_peak / 2) 
                else:
                    # ✅ 场景 C：常规普通交易日 (核心修正区域)
                    # 动态追踪均线真实位置，解决刻舟求剑
                    current_realtime_ma = ma_val * (1 + ma_slope * pending_days)

                # 🚀 【补丁1：强庄股非对称向上滑点】
                    # 如果该股爆发力极强（比如前期涨超25%），它的洗盘通常很浅
                    # 我们允许买入网格自动向上宽容 1.5%，以免差一毛钱踏空！
                    if burst_ratio > 0.25:
                        # 在原始基准上往上提 1.5%
                        dynamic_trigger_buy = trigger_buy * (1 + ma_slope * pending_days) * 1.015
                    else:
                        # 否则保持原始设定
                        dynamic_trigger_buy = trigger_buy * (1 + ma_slope * pending_days) * 1.00
                    
                    # 止损线保持死板跟随，确保护城河深度
                    dynamic_stop_loss = stop_loss * (1 + ma_slope * pending_days)
                # =======================================================
                # 🚨 仅在常规期注入：前日微观K线形态安全防御 (专杀 sz000631 瀑布杀)
                # =======================================================
                if not market_crash_today and not market_peak_dumping:
                    p_close = prev_row_data['close']
                    p_high = prev_row_data['high']
                    p_low = prev_row_data['low']
                    p_amp = max((p_high - p_low) / p_close, 0.02)
                    
                    # 状态判定：前一日是否为近乎光脚的极速坠落实体大阴线（收盘收在下30%区间，实体大）
                    is_prev_heavy_drop = p_close < p_low + (p_high - p_low) * 0.3
                    
                    if is_prev_heavy_drop and p_amp > 0.045:
                        # 发现危险：个股昨日前行惯性巨大。通过取极小值，强行迫使其买入点向下避让前日振幅的 50%
                        safe_buffer_price = p_close * (1 - p_amp * 0.5)
                        dynamic_trigger_buy = min(dynamic_trigger_buy, safe_buffer_price)
                        # 止损随买点联动下修，防窄幅被扫
                        dynamic_stop_loss = dynamic_trigger_buy * 0.94

                # 🛡️ 严格的撮合条件判定
                if row['open'] <= dynamic_stop_loss: continue
                if row['low'] <= dynamic_trigger_buy:
                    # 🚀 【核心重构：从“盲目接刀”升级为“右侧确立机制”】
                    is_right_side_confirmed = False
                    actual_entry_price = 0.0
                    
                    # 证据 1：日内深V强反转 (单日内完成探底与多头反击)
                    # 跌入买入网后，盘中被强力资金托起超过 1.5%
                    if row['close'] >= row['low'] * 1.015:
                        is_right_side_confirmed = True
                        actual_entry_price = min(dynamic_trigger_buy, row['low'] * 1.015)
                        
                    # 证据 2：底部右侧反包阳线 (结束连阴，右侧起点确立)
                    # 要求：今天收红(收>开)，且收盘价不仅高于昨日收盘，还要有一定实体力度
                    elif row['close'] > row['open'] and row['close'] >= prev_row_data['close']:
                        is_right_side_confirmed = True
                        actual_entry_price = row['close']  # 模拟尾盘确认收阳时打板买入
                        
                    # 证据 3：极致地量双底企稳 (专抓你截图里那种漂亮的缩量双底)
                    # 要求：量能极度萎缩(量比<0.55)，且今天【没有跌破昨天的最低点】，收盘拒绝下杀
                    elif vol_ratio < 0.55 and row['low'] >= prev_row_data['low'] and row['close'] >= row['open'] * 0.995:
                        is_right_side_confirmed = True
                        actual_entry_price = row['close']  # 模拟尾盘确认企稳底分型时买入

                    # 🎯 只有拿到了这三个右侧物理证据的其中之一，才准许成交！
                    if is_right_side_confirmed:  
                        trade_status = "持仓中"
                        entry_date = current_date_str
                        # 确保买入价在合理区间内
                        entry_price = actual_entry_price
                        
                        # 🔒 致命核心：成交瞬间，把这天的止损价硬性锁死！
                        actual_stop_loss = dynamic_stop_loss 
                        
                        # 买入当天如果遭遇极端向下贯穿（比如涨停砸到跌停），直接止损出局
                        extreme_stop = actual_stop_loss * 0.97
                        if row['low'] <= extreme_stop or row['close'] <= actual_stop_loss:
                            trade_status, exit_price, mae_raw, holding_days = "止损出局", row['close'], (row['low'] - entry_price) / entry_price, 1
                            exit_date = current_date_str
                            break
            
            elif trade_status == "持仓中":
                holding_days += 1
                curr_profit = (row['high'] - entry_price) / entry_price
                curr_drawdown = (row['low'] - entry_price) / entry_price
                
                if curr_profit > mfe_raw: mfe_raw = curr_profit
                if curr_drawdown < mae_raw: mae_raw = curr_drawdown
                
                # 常规阶梯止盈
                current_target_profit = TARGET_PROFIT if holding_days <= 8 else DECAY_PROFIT
                if row['high'] >= entry_price * (1 + current_target_profit):
                    trade_status = "止盈成功"
                    exit_date = current_date_str
                    mfe_raw = max(mfe_raw, current_target_profit) 
                    exit_price = entry_price * (1 + current_target_profit)
                    break
                
                # 时间止损
                #if holding_days >= 6 and mfe_raw < 0.02:
                #    trade_status = "时间止损(弱势换股)"
                #    exit_date = current_date_str
                #    exit_price = row['close']
                #    break
                
                # 股灾抢跑机制
                #if market_crash_today and curr_profit > 0:
                #    trade_status = "股灾避险(微利平仓)"
                #    exit_date = current_date_str
                #    exit_price = row['close']
                #    break

                # 锁死后的常规物理止损判定 (使用 actual_stop_loss)
                extreme_stop = actual_stop_loss * 0.97
                if row['low'] <= extreme_stop or row['close'] <= actual_stop_loss: 
                    trade_status, exit_price, exit_date = "止损出局", row['close'], current_date_str
                    break
            
            # 💡 每日收盘后，将今天的数据滚动为“明天的前一日”
            prev_row_data = {
                'close': row['close'],
                'high': row['high'],
                'low': row['low']
            }

        if trade_status == "持仓中":
            exit_price = future_df.iloc[-1]['close']
            trade_status = "持仓到期"
            exit_date = future_df.index[-1].strftime('%Y-%m-%d')

        result = {
            'stock_code': stock_code_full,
            'eval_date': historical_df.index[-1].strftime('%Y-%m-%d'),
            'entry_date': entry_date, 'exit_date': exit_date,
            'future_min_low': future_min_low, 'future_max_high': future_max_high,
            'strategy': STRATEGY_TO_TEST, 'trade_status': trade_status,
            'final_pnl': (exit_price - entry_price)/entry_price if entry_price > 0 else 0.0,
            'MFE': mfe_raw, 'MAE': mae_raw, 'holding_days': holding_days,
            'entry_slip': (entry_price - trigger_buy)/trigger_buy if entry_price > 0 else 0.0,
            'trigger_buy': trigger_buy, 'stop_loss': stop_loss,
            'fit_score': features.get('fit_score', 0.0),
            'best_ma': features.get('best_ma', 0),
            'deep_touches': features.get('deep_touches', 0),
            'polarity': features.get('polarity', 0),
            'burst_ratio': features.get('burst_ratio', 0.0),
            'is_deep_wash': int(features.get('is_deep_wash', False)),
            'ma_slope': features.get('ma_slope', 0.0),
            'drop_velocity': features.get('drop_velocity', 0.0)
        }
        return result
    except Exception as e:
        logger.error(f"Error processing {file_path}: {e}")
        return None

def save_and_report_results(results):
    if not results: return
    df_res = pd.DataFrame(results)
    latest_csv_path = os.path.join(backend_dir, 'latest_walk_forward.csv')
    df_res.to_csv(latest_csv_path, index=False, float_format='%.4f')
    logger.info(f"💾 资金截断级 V12 测试数据已保存至: {latest_csv_path}")

if __name__ == '__main__':
    vipdoc_base = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    files = glob.glob(os.path.join(vipdoc_base, "sh", "lday", "*.day")) + glob.glob(os.path.join(vipdoc_base, "sz", "lday", "*.day"))
    with Pool(processes=cpu_count()) as pool:
        raw_results = pool.map(worker, files)
        
    valid_results = [r for r in raw_results if r is not None]
    
    if valid_results:
        # 按照全新矩阵分及多头趋势质量从高到低排序
        valid_results.sort(key=lambda x: (x.get('fit_score', 0), x.get('ma_slope', 0)), reverse=True)
        
        # 强力执行资金限额横向拦截
        MAX_LIMIT = 500
        if len(valid_results) > MAX_LIMIT:
            logger.info(f"⚠️ 今日选股产生 {len(valid_results)} 只，执行机构级 Top {MAX_LIMIT} 资金容量强规整！")
            valid_results[:] = valid_results[:MAX_LIMIT]
            
    save_and_report_results(valid_results)
