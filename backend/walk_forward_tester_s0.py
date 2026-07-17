import os
import glob
import json
import logging
import pandas as pd
import numpy as np
from datetime import datetime
from multiprocessing import Pool, cpu_count
import data_loader

# ==========================================
# === 狙击手核心回测全局配置 ===
# ==========================================
STRATEGY_TO_TEST = 'MORSE_FACTOR_SNIPER' 
TARGET_PROFIT = 0.10  # 核心止盈目标：+10% 挂单
STOP_LOSS = -0.05     # 核心硬性止损：-5%

EVAL_DATE = '2026-05-6'  # 回测选股基准截面日
FORWARD_DAYS = 7        # 持仓/挂单观测窗口天数

backend_dir = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.abspath(os.path.join(backend_dir, '..', 'data', 'result'))
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

def worker(file_path):
    stock_code_full = os.path.basename(file_path).split('.')[0]
    stock_code = stock_code_full.replace('sh', '').replace('sz', '').replace('bj', '')
    if not (stock_code.startswith(('60', '688', '00', '300', '92')) and len(stock_code) == 6): 
        return None

    try:
        df_daily = data_loader.get_daily_data(file_path)
        if df_daily is None or df_daily.empty: return None
        
        # 加载微观15分钟线
        df_15m = data_loader.get_min_data(stock_code, period='15m')
        
        # 时空切片
        historical_df, future_df = get_time_sliced_data(df_daily, EVAL_DATE, FORWARD_DAYS)
        if historical_df is None: return None
        
        # 15分钟线切片，绝不偷看未来
        m15_slice = None
        if df_15m is not None and not df_15m.empty:
            if 'datetime' in df_15m.columns: df_15m.index = pd.to_datetime(df_15m['datetime'])
            else: df_15m.index = pd.to_datetime(df_15m.index)
            cutoff = pd.to_datetime(f"{historical_df.index[-1].strftime('%Y-%m-%d')} 15:30:00")
            m15_slice = df_15m[df_15m.index <= cutoff].copy()

        # ---------------------------------------------------------
        # ⚔️ 核心决策大闸对接
        # ---------------------------------------------------------
        if STRATEGY_TO_TEST == 'MORSE_FACTOR_SNIPER':
            from screenergf import apply_morse_sniper_strategy
            res = apply_morse_sniper_strategy(historical_df, df_15m=m15_slice)
        else:
            res = None

        # 🛡️ 恢复并升级防御装甲：若策略返回 None 或 signal 为 False，优雅退出，绝不空转
        if res is None or not res.get('signal'):
            return None

        # 🎯 提取靶向狙击价与特征分数
        trigger_buy = res['trigger_price']
        strategy_score = res.get('score', 65)
        
        # 预估的初始止损/止盈线（用于未成交卡片的记录展示）
        static_take_profit = trigger_buy * (1 + TARGET_PROFIT)
        static_stop_loss = trigger_buy * (1 + STOP_LOSS)
        
        # =================================================================
        # 🧬 必须前置的核心：提取莫尔斯特征基因与昨收价 (供下方撮合与拦截使用)
        # =================================================================
        t0_close = historical_df['close'].iloc[-1]
        
        vol_ma20_d = historical_df['volume'].rolling(20).mean().iloc[-1]
        row_t1 = historical_df.iloc[-1]
        d_pct = (row_t1['close'] - row_t1['open']) / (row_t1['open'] + 1e-9)
        d_vol = row_t1['volume'] / (vol_ma20_d + 1e-9)
        d_lower_shadow = (min(row_t1['close'], row_t1['open']) - row_t1['low']) / (row_t1['open'] + 1e-9)
        
        T1_U = 1 if d_pct > 0.062 else 0
        T1_D = 1 if d_pct < -0.062 else 0
        T1_L = 1 if d_vol < 0.8 else 0
        T1_B = 1 if d_lower_shadow > 0.026 else 0
        
        M15_U, M15_L = 0, 0
        if m15_slice is not None and len(m15_slice) > 20:
            vol_ma20_m15 = m15_slice['volume'].rolling(20).mean().iloc[-1]
            row_m15 = m15_slice.iloc[-1]
            m_pct = (row_m15['close'] - row_m15['open']) / (row_m15['open'] + 1e-9)
            m_vol = row_m15['volume'] / (vol_ma20_m15 + 1e-9)
            M15_U = 1 if m_pct > 0.0062 else 0
            M15_L = 1 if m_vol < 0.5 else 0
            
        morse_features = f"T1_U:{T1_U}|T1_D:{T1_D}|T1_L:{T1_L}|T1_B:{T1_B}|M15_U:{M15_U}|M15_L:{M15_L}"
        # =================================================================

        # 如果没有未来数据，直接输出预演执行卡
        if future_df.empty:
            return {
                'stock_code': stock_code_full, 'eval_date': historical_df.index[-1].strftime('%Y-%m-%d'),
                'entry_date': "", 'exit_date': "", 'future_min_low': 0.0, 'future_max_high': 0.0,
                'strategy': STRATEGY_TO_TEST, 'trade_status': "等待实盘验证(T+1)",
                'final_pnl': 0.0, 'MFE': 0.0, 'MAE': 0.0, 'holding_days': 0, 'entry_slip': 0.0,
                'trigger_buy': trigger_buy, 'stop_loss': static_stop_loss,
                'fit_score': strategy_score, 'ma_slope': 0.0
            }

        future_min_low = future_df['low'].min()
        future_max_high = future_df['high'].max()
        
        # ---------------------------------------------------------
        # 🎯 精密流水线撮合状态机 (无残留均线污染，纯价格空间拦截)
        # ---------------------------------------------------------
        trade_status = "未成交"
        entry_price, exit_price, mfe_raw, mae_raw, holding_days = 0.0, 0.0, 0.0, 0.0, 0
        entry_date, exit_date = "", ""
        pending_days = 0
        
        # 锁死防线：一旦成交，以此线为绝对准则
        actual_take_profit = 0.0
        actual_stop_loss = 0.0
        
        for idx, row in future_df.iterrows():
            current_date_str = idx.strftime('%Y-%m-%d')
            
            # 🚨 新增拦截：防范“核按钮”骗炮
            # 如果昨天尾盘是有 M15_U (抢筹)，今天理应高开。
            # 如果今天不仅没高开，开盘价还跌破了昨收价的 -1.5%（严重不及预期），说明昨尾盘是诱多，直接撤单！
            if 'M15_U:1' in morse_features and row['open'] < t0_close * 0.985:
                trade_status = "弱势低开撤单"
                break
            
            if trade_status == "未成交":
                pending_days += 1
                if pending_days > 4:  # 挂单有效期死限为 4 天，过长则失去时效性
                    trade_status = "挂单超时撤销"
                    break
                
                # 🚨 Grok 级实战防守：低开防线体系 (动态拒绝接刀)
                # 1. 核按钮直接撤单：如果开盘价直接砸破了我们买点的 2.5% 甚至更多，说明势头完全不对。
                if row['open'] < trigger_buy * 0.975:
                    trade_status = "大幅低开(核按钮)撤单"
                    break
                
                # 2. 缩量阴跌防御：正如 Grok 所言，如果昨天尾盘缩量(M15_L:1)，今天还敢低开(哪怕只低开1%)，极大概率是阴跌中继，不买！
                if 'M15_L:1' in morse_features and row['open'] < t0_close * 0.99:
                    trade_status = "缩量弱势低开撤单"
                    break

                # 撮合判定：如果当天最低价刺穿了我们的靶向买入价，宣告成交
                if row['low'] <= trigger_buy:
                    # 极端防守：如果开盘价直接跌破了我们的预设止损线，说明遭遇黑天鹅，放弃挂单
                    if row['open'] <= static_stop_loss:
                        trade_status = "大幅低开放弃"
                        break
                        
                    trade_status = "持仓中"
                    entry_date = current_date_str
                    # 实际成交价取 挂单价 与 当天开盘价 的孰高者（防止跳空低开直接送出溢价）
                    entry_price = min(trigger_buy, row['open'])
                    
                    # 🔒 瞬间锁死该笔交易的绝对生死线，持仓期永不漂移
                    actual_take_profit = entry_price * (1 + TARGET_PROFIT)
                    actual_stop_loss = entry_price * (1 + STOP_LOSS)
                    
                    # 检查买入当天是否遭遇极端长阴线直接击穿止损
                    if row['low'] <= actual_stop_loss or row['close'] <= actual_stop_loss:
                        trade_status = "止损出局"
                        exit_price = row['close']
                        exit_date = current_date_str
                        mae_raw = (row['low'] - entry_price) / entry_price
                        break
                        
            elif trade_status == "持仓中":
                holding_days += 1
                curr_profit = (row['high'] - entry_price) / entry_price
                curr_drawdown = (row['low'] - entry_price) / entry_price
                
                if curr_profit > mfe_raw: mfe_raw = curr_profit
                if curr_drawdown < mae_raw: mae_raw = curr_drawdown
                
                # 1. 止盈挂单拦截：只要当天最高价摸到或越过锁死止盈线，完美止盈
                if row['high'] >= actual_take_profit:
                    trade_status = "止盈成功"
                    exit_price = actual_take_profit
                    exit_date = current_date_str
                    break
                
                # 2. 硬性止损拦截：只要最低价跌破锁死止损线，无条件断腕
                if row['low'] <= actual_stop_loss:
                    trade_status = "止损出局"
                    exit_price = actual_stop_loss
                    exit_date = current_date_str
                    break
                # 🚨 动态止盈方案：时间衰减
                # 头两天冲劲最足，要求 10% 止盈
                # 如果持仓超过 2 天还没摸到 10%，说明股性变弱，止盈线主动降至 7% 跑路
                current_target = TARGET_PROFIT if holding_days <= 2 else 0.07
                actual_take_profit = entry_price * (1 + current_target)
                
                if row['high'] >= actual_take_profit:
                    trade_status = "止盈成功"
                    exit_price = actual_take_profit

        # 观测窗口结束仍未出局的单子，执行到期强制平仓
        if trade_status == "持仓中":
            exit_price = future_df.iloc[-1]['close']
            trade_status = "持仓到期"
            exit_date = future_df.index[-1].strftime('%Y-%m-%d')

        # =================================================================
        # 🧬 新增核心：提取莫尔斯特征基因 与 7 天真实价格轨迹
        # =================================================================
        # 1. 现场重新提取核心 Bit 位，彻底解耦对 screenergf.py 的强依赖
        vol_ma20_d = historical_df['volume'].rolling(20).mean().iloc[-1]
        row_t1 = historical_df.iloc[-1]
        d_pct = (row_t1['close'] - row_t1['open']) / (row_t1['open'] + 1e-9)
        d_vol = row_t1['volume'] / (vol_ma20_d + 1e-9)
        d_lower_shadow = (min(row_t1['close'], row_t1['open']) - row_t1['low']) / (row_t1['open'] + 1e-9)
        
        T1_U = 1 if d_pct > 0.062 else 0
        T1_D = 1 if d_pct < -0.062 else 0
        T1_L = 1 if d_vol < 0.8 else 0
        T1_B = 1 if d_lower_shadow > 0.026 else 0
        
        M15_U, M15_L = 0, 0
        if m15_slice is not None and len(m15_slice) > 20:
            vol_ma20_m15 = m15_slice['volume'].rolling(20).mean().iloc[-1]
            row_m15 = m15_slice.iloc[-1]
            m_pct = (row_m15['close'] - row_m15['open']) / (row_m15['open'] + 1e-9)
            m_vol = row_m15['volume'] / (vol_ma20_m15 + 1e-9)
            M15_U = 1 if m_pct > 0.0062 else 0
            M15_L = 1 if m_vol < 0.5 else 0
            
        morse_features = f"T1_U:{T1_U}|T1_D:{T1_D}|T1_L:{T1_L}|T1_B:{T1_B}|M15_U:{M15_U}|M15_L:{M15_L}"
        

        # 2. 提取未来 7 天的每日最高价/最低价轨迹 (相对于 T0 收盘价的百分比)
        t0_close = historical_df['close'].iloc[-1]
        path_list = []
        for idx, r in future_df.iterrows():
            high_pct = (r['high'] - t0_close) / t0_close * 100
            low_pct = (r['low'] - t0_close) / t0_close * 100
            path_list.append(f"H:{high_pct:+.1f}%/L:{low_pct:+.1f}%")
        future_7d_path = " -> ".join(path_list)

        return {
            'stock_code': stock_code_full,
            'eval_date': historical_df.index[-1].strftime('%Y-%m-%d'),
            'entry_date': entry_date, 'exit_date': exit_date,
            'future_min_low': future_min_low, 'future_max_high': future_max_high,
            'strategy': STRATEGY_TO_TEST, 'trade_status': trade_status,
            'final_pnl': (exit_price - entry_price)/entry_price if entry_price > 0 else 0.0,
            'MFE': mfe_raw, 'MAE': mae_raw, 'holding_days': holding_days,
            'entry_slip': (entry_price - trigger_buy)/trigger_buy if entry_price > 0 else 0.0,
            'trigger_buy': trigger_buy, 'stop_loss': static_stop_loss,
            'fit_score': strategy_score,
            'ma_slope': 0.0,
            'morse_features': morse_features,    # 新增基因特征
            'future_7d_path': future_7d_path     # 新增 7 天涨跌轨迹
        }
    except Exception as e:
        logger.error(f"Error processing {file_path}: {e}")
        return None

def save_and_report_results(results):
    if not results: return
    df_res = pd.DataFrame(results)
    latest_csv_path = os.path.join(backend_dir, 'latest_walk_forward.csv')
    df_res.to_csv(latest_csv_path, index=False, float_format='%.4f')
    logger.info(f"💾 莫尔斯加权狙击选股测试数据已保存至: {latest_csv_path}")

if __name__ == '__main__':
    vipdoc_base = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    files = glob.glob(os.path.join(vipdoc_base, "sh", "lday", "*.day")) + \
            glob.glob(os.path.join(vipdoc_base, "sz", "lday", "*.day")) + \
            glob.glob(os.path.join(vipdoc_base, "bj", "lday", "*.day")) 
            
    with Pool(processes=cpu_count()) as pool:
        raw_results = pool.map(worker, files)
        
    valid_results = [r for r in raw_results if r is not None]
    
    if valid_results:
        # 按照莫尔斯矩阵的打分高低进行系统优先级降序排列
        valid_results.sort(key=lambda x: (x.get('fit_score', 0), x.get('ma_slope', 0)), reverse=True)
        
        MAX_LIMIT = 500
        if len(valid_results) > MAX_LIMIT:
            logger.info(f"⚠️ 今日满足强共振个股共 {len(valid_results)} 只，执行机构级 Top {MAX_LIMIT} 容量截断！")
            valid_results[:] = valid_results[:MAX_LIMIT]
            
    save_and_report_results(valid_results)
