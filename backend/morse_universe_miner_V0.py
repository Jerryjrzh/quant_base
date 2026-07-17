import os
import glob
import pandas as pd
import numpy as np
from multiprocessing import Pool, cpu_count
from datetime import datetime
import logging

import data_loader

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==========================================
# 📊 全局策略参数配置
# ==========================================
VOLATILITY_THRESHOLD = 0.10   # 触发异动研究的个股单日振幅门槛
LOOKBACK_DAYS = 300           # 扫描的历史日线总长度
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'morse_analytics')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 四大宽基期指现货对应路径（请确保你本地文件存在，这里做兜底保护）
INDEX_PATHS = {
    'IH': os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc/sh/lday/sh000016.day"), # 上证50
    'IF': os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc/sh/lday/sh000300.day"), # 沪深300
    'IC': os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc/sh/lday/sh000905.day"), # 中证500
    'IM': os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc/sh/lday/sh000852.day")  # 中证1000
}

def _to_morse_char(open_p, high, low, close, vol, vol_ma20) -> str:
    """【基因测序单原子】将任意一根K线瞬间转化为3位莫尔斯电码"""
    # 1. 实体测序
    pct = (close - open_p) / (open_p + 1e-9)
    if pct > 0.03:     body = 'U'
    elif pct > 0.005:  body = 'u'
    elif pct < -0.03:  body = 'D'
    elif pct < -0.005: body = 'd'
    else:              body = 'X'
    
    # 2. 影线测序
    upper_shadow = high - max(close, open_p)
    lower_shadow = min(close, open_p) - low
    body_size = abs(close - open_p)
    
    if lower_shadow > body_size * 1.2 and lower_shadow > upper_shadow:    shadow = 'B'
    elif upper_shadow > body_size * 1.2 and upper_shadow > lower_shadow:  shadow = 'T'
    elif upper_shadow < body_size * 0.1 and lower_shadow < body_size * 0.1: shadow = 'N'
    else:                                                                 shadow = 'S'
    
    # 3. 量能测序
    vol_ratio = vol / (vol_ma20 + 1e-9)
    if vol_ratio > 1.8:   volume = 'H'
    elif vol_ratio < 0.6: volume = 'L'
    else:                 volume = 'A'
    
    return f"{body}{shadow}{volume}"

def build_timeframe_morse_string(df, last_date, count=4) -> str:
    """提取指定截止日期前的最后count根K线拼装成莫尔斯链"""
    if df is None or df.empty: return "NODATA"
    
    # 确保是时间索引
    if not isinstance(df.index, pd.DatetimeIndex):
        if 'datetime' in df.columns: df.index = pd.to_datetime(df['datetime'])
        else: df.index = pd.to_datetime(df.index)
        
    sub_df = df[df.index <= pd.to_datetime(last_date)]
    if len(sub_df) < count + 20: return "SHORT"
    
    # 计算20周期滚动均量
    vol_ma = sub_df['volume'].rolling(20, min_periods=1).mean()
    
    codes = []
    for i in range(-count, 0):
        row = sub_df.iloc[i]
        v_ma = vol_ma.iloc[i]
        char = _to_morse_char(row['open'], row['high'], row['low'], row['close'], row['volume'], v_ma)
        codes.append(char)
        
    return "-".join(codes)

def process_stock_morse_universe(file_path):
    """多进程核心单兵：完成个股异动节点的跨时空多周期莫尔斯测序"""
    stock_code_full = os.path.basename(file_path).split('.')[0]
    clean_code = stock_code_full.replace('sh', '').replace('sz', '').replace('bj', '')
    
    try:
        df_daily = data_loader.get_daily_data(file_path)
        if df_daily is None or len(df_daily) < 40: return None
        
        # 截断长周期
        slice_len = min(len(df_daily), LOOKBACK_DAYS)
        df_daily = df_daily.iloc[-slice_len:].copy()
        
        df_daily['prev_close'] = df_daily['close'].shift(1)
        df_daily['amplitude'] = (df_daily['high'] - df_daily['low']) / df_daily['prev_close']
        
        # 寻找异动节点 T 日
        target_indices = np.where(df_daily['amplitude'] > VOLATILITY_THRESHOLD)[0]
        if len(target_indices) == 0: return None
        
        # 只有存在异动节点才按需延迟加载分钟线，保证恐怖的执行速度
        df_60m = data_loader.get_min_data(clean_code, period='60m')
        df_15m = data_loader.get_min_data(clean_code, period='15m')
        
        stock_features = []
        
        for idx in target_indices:
            if idx < 5 or idx >= len(df_daily): continue
            
            t_date = df_daily.index[idx]
            t_minus_1 = df_daily.index[idx - 1]
            t_minus_2 = df_daily.index[idx - 2]
            
            # ---------------------------------------------------------
            # 🎯 新增：提取个股 T-1 日的“趋势位置基因” (位置决定性质！)
            # ---------------------------------------------------------
            t_minus_1_loc = df_daily.index.get_loc(t_minus_1)
            close_t1 = df_daily['close'].iloc[t_minus_1_loc]
            ma20_t1 = df_daily['close'].iloc[max(0, t_minus_1_loc-20):t_minus_1_loc+1].mean()
            ma60_t1 = df_daily['close'].iloc[max(0, t_minus_1_loc-60):t_minus_1_loc+1].mean()
            
            if close_t1 > ma20_t1 and ma20_t1 > ma60_t1:
                stock_position = "📈[多头主升]"
            elif close_t1 < ma20_t1 * 0.93:
                stock_position = "📉[超跌深坑]"
            else:
                stock_position = "➖[震荡洗盘]"

            # 🧬 1. 个股日线莫尔斯码（回溯 T-5 到 T-2，共4天累积日线形态）
            morse_daily = build_timeframe_morse_string(df_daily, t_minus_2, count=4)
            
            # 🧬 2. 个股小时线莫尔斯码（整个 T-1 交易日内的 4 根 60分钟K线形态）
            morse_60m = build_timeframe_morse_string(df_60m, f"{t_minus_1.strftime('%Y-%m-%d')} 15:30:00", count=4)
            
            # 🧬 3. 个股15分钟线莫尔斯码（T-1 交易日最后尾盘半小时的 2 根 15分钟K线微操微观基因）
            morse_15m = build_timeframe_morse_string(df_15m, f"{t_minus_1.strftime('%Y-%m-%d')} 15:30:00", count=2)
            
            if "NODATA" in (morse_daily, morse_60m, morse_15m) or "SHORT" in (morse_daily, morse_60m, morse_15m):
                continue
                
            # 完整拼装个股多周期莫尔斯密码子
            combined_morse_chain = f"D[{morse_daily}]_H60[{morse_60m}]_M15[{morse_15m}]"
            
            # 提取最后两天的日线 (例如从 dSA-uSA-DSA-USA 提取出 DSA-USA)
            daily_last2 = "-".join(morse_daily.split('-')[-2:]) if '-' in morse_daily else morse_daily
            
            # 提取最后一小时和最后15分钟的尾盘动作
            h60_last = morse_60m.split('-')[-1] if '-' in morse_60m else morse_60m
            m15_last = morse_15m.split('-')[-1] if '-' in morse_15m else morse_15m

            # 计算T+1到T+3日的最大反弹期望（用于给复盘筛选做统计依据）
            future_slice = df_daily.iloc[idx + 1: idx + 4]
            max_rebound = 0.0
            if not future_slice.empty:
                max_rebound = (future_slice['high'].max() - df_daily['close'].iloc[idx]) / df_daily['close'].iloc[idx]
            
            stock_features.append({
                'stock_code': stock_code_full,
                'target_date': t_date.strftime('%Y-%m-%d'),
                'combined_morse': combined_morse_chain,
                # 🚨 新增：碎片化特征列（用于降维聚合）
                'daily_last2': daily_last2,
                'h60_last': h60_last,
                'm15_last': m15_last,
                'stock_position': stock_position,
                'max_rebound_3d': round(max_rebound, 4)
            })
            
        return stock_features
    except Exception:
        return None

def _assess_market_risk(market_morse: str) -> str:
    """
    【大盘莫尔斯风控解析器】
    根据 IH/IF/IC/IM 的莫尔斯字符，直接输出交易指令权重级别。
    比如：'IH[dTA]-IF[XSA]-IC[DNH]-IM[DSA]'
    """
    if not isinstance(market_morse, str):
        return "UNKNOWN"
        
    # 规则 1：极端风险 (空仓/极深打折)
    # 只要代表中小盘赚钱效应的 IC 或 IM 出现了大阴线实体 'D'，或者四个指数全是阴线 'd'
    if 'IC[D' in market_morse or 'IM[D' in market_morse or market_morse.count('[d') + market_morse.count('[D') >= 4:
        return "🚨[高危-建议空仓或-8%深折]"
        
    # 规则 2：二八分化风险 (掩护出货)
    # IH/IF (权重) 是阳线 'U'/'u'，但 IC/IM (中小盘) 是阴线 'D'/'d'
    if ('IH[U' in market_morse or 'IH[u' in market_morse) and ('IM[d' in market_morse or 'IM[D' in market_morse):
        return "⚠️[分化-建议缩减仓位及-4%打折]"
        
    # 规则 3：共振顺风期 (满仓/正常挂单)
    # IC/IM 呈现阳线实体 'U'/'u'，或者地量十字星 'XL' 企稳
    if 'IC[u' in market_morse or 'IM[u' in market_morse or 'IM[U' in market_morse or 'IM[XL' in market_morse:
        return "🟢[安全-顺风满仓0.99挂单]"
        
    # 其他常规震荡市
    return "🟡[震荡-常规应对]"


def main():
    logger.info("🚀 启动[全宇宙莫尔斯电码共振多频挖掘引擎]...")
    
    # 1. 预载入并重构四大指数在历史全截面上的莫尔斯环境码
    logger.info("📊 正在同步测序四大宽基期指现货(IH/IF/IC/IM)环境基因...")
    index_dfs = {name: data_loader.get_daily_data(path) for name, path in INDEX_PATHS.items()}
    
    index_morse_db = {} 
    
    all_dates = index_dfs['IM'].index if index_dfs['IM'] is not None else []
    for t_date in all_dates:
        date_str = t_date.strftime('%Y-%m-%d')
        idx_codes = []
        for name, df in index_dfs.items():
            if df is not None and t_date in df.index:
                loc = df.index.get_loc(t_date)
                if loc > 20:
                    v_ma = df['volume'].iloc[loc-20:loc].mean()
                    row = df.iloc[loc]
                    char = _to_morse_char(row['open'], row['high'], row['low'], row['close'], row['volume'], v_ma)
                    idx_codes.append(f"{name}[{char}]")
        if len(idx_codes) == 4:
            index_morse_db[date_str] = "-".join(idx_codes)

    # 2. 多进程洗全市场个股
    vipdoc_base = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    files = glob.glob(os.path.join(vipdoc_base, "sh", "lday", "*.day")) + glob.glob(os.path.join(vipdoc_base, "sz", "lday", "*.day"))
    
    with Pool(processes=min(cpu_count(), 12)) as pool:
        raw_results = pool.map(process_stock_morse_universe, files)
        
    flat_stock_records = []
    for r in raw_results:
        if r: flat_stock_records.extend(r)
        
    # 3. 🛡️ 【时空拟合大交汇】
    logger.info("⚔️ 正在将个股基因与对应节点的期指环境雷达信号进行时空对齐拟合...")
    final_dataset = []
    for record in flat_stock_records:
        t_date_str = record['target_date']
        if t_date_str in index_morse_db:
            record['index_regime_morse'] = index_morse_db[t_date_str]
            
            # 🎯 新增：解析大盘风险级别
            record['market_risk_level'] = _assess_market_risk(record['index_regime_morse'])
            
            # 完整原始长链兜底保留
            record['system_共振_code'] = f"MARKET_{record['index_regime_morse']} ===> STOCK_{record['combined_morse']}"
            final_dataset.append(record)
            
        # =================================================================
        # 4. 📈 【大数定律重构：模糊特征独立加权统计】
        # =================================================================
        df_universe = pd.DataFrame(final_dataset)
        if df_universe.empty: return

        # 标记暴利单 (>20%) 和 垃圾单 (<5%)
        df_universe['is_golden'] = (df_universe['max_rebound_3d'] >= 0.20).astype(int)
        
        # 🌟 特征工程：将死板的莫尔斯码，翻译为人类视角的“高能独立特征”
        
        # 特征 1：日线 T-2 爆发力 (T-2是否出现大阳线 'U' 且放量 'H' 或平量 'A')
        def has_t2_explosion(daily_last2):
            if not isinstance(daily_last2, str) or '-' not in daily_last2: return 0
            t2 = daily_last2.split('-')[0]
            return 1 if 'U' in t2 and ('H' in t2 or 'A' in t2) else 0

        # 特征 2：日线 T-1 极度缩量洗盘 (T-1是否缩量 'L' 且无大跌 'd'/'X'/'u')
        def has_t1_shrink_wash(daily_last2):
            if not isinstance(daily_last2, str) or '-' not in daily_last2: return 0
            t1 = daily_last2.split('-')[1]
            return 1 if 'L' in t1 and 'D' not in t1 else 0

        # 特征 3：日线 T-1 强力下影线支撑 (T-1是否出现 'B')
        def has_t1_lower_shadow(daily_last2):
            if not isinstance(daily_last2, str) or '-' not in daily_last2: return 0
            t1 = daily_last2.split('-')[1]
            return 1 if 'B' in t1 else 0

        # 特征 4：尾盘 15 分钟地量企稳 (M15 最后一根是否是十字星 'X' 且缩量 'L')
        def has_m15_quiet(m15_last):
            return 1 if isinstance(m15_last, str) and 'X' in m15_last and 'L' in m15_last else 0

        # 将特征应用到数据集
        df_universe['F_T2_Explode'] = df_universe['daily_last2'].apply(has_t2_explosion)
        df_universe['F_T1_Shrink'] = df_universe['daily_last2'].apply(has_t1_shrink_wash)
        df_universe['F_T1_Shadow'] = df_universe['daily_last2'].apply(has_t1_lower_shadow)
        df_universe['F_M15_Quiet'] = df_universe['m15_last'].apply(has_m15_quiet)

        logger.info("⚔️ 正在计算独立因子的基础胜率权重...")
        
        # 定义需要独立统计的特征列表
        features = ['F_T2_Explode', 'F_T1_Shrink', 'F_T1_Shadow', 'F_M15_Quiet']
        
        # 统计每一个独立特征在【大盘安全】+【不同趋势位置】下的有效胜率
        # 剔除高危大盘样本
        safe_df = df_universe[df_universe['market_risk_level'].str.contains('安全|震荡')]
        
        feature_report = []
        for f in features:
            for pos in ['📈[多头主升]', '📉[超跌深坑]']:
                subset = safe_df[(safe_df[f] == 1) & (safe_df['stock_position'] == pos)]
                if len(subset) > 3: # 样本容量足够大
                    win_rate = subset['is_golden'].mean()
                    feature_report.append({
                        '特征名称': f,
                        '趋势位置': pos,
                        '历史触发总数': len(subset),
                        '独立贡献胜率(>20%爆率)': round(win_rate, 4)
                    })
                    
        report_df = pd.DataFrame(feature_report).sort_values(by='独立贡献胜率(>20%爆率)', ascending=False)
        print("\n👑 【独立因子(特征)权重贡献排行榜】")
        print("-" * 80)
        print(report_df.to_string(index=False))

        # =================================================================
        # 终极应用演示：如何在复盘或实盘中“累加得分”？
        # =================================================================
        # 假定我们基于统计结果分配了以下经验权重：
        weights = {'F_T2_Explode': 15, 'F_T1_Shrink': 10, 'F_T1_Shadow': 15, 'F_M15_Quiet': 10}
        
        # 计算全市场每只股票的“特征累加总分”
        df_universe['Total_Score'] = (
            df_universe['F_T2_Explode'] * weights['F_T2_Explode'] +
            df_universe['F_T1_Shrink'] * weights['F_T1_Shrink'] +
            df_universe['F_T1_Shadow'] * weights['F_T1_Shadow'] +
            df_universe['F_M15_Quiet'] * weights['F_M15_Quiet']
        )
        
        # 大盘一票否决乘数
        df_universe['Market_Multiplier'] = df_universe['market_risk_level'].apply(lambda x: 0 if '高危' in x else (0.5 if '分化' in x else 1.0))
        # 趋势位置基础分
        df_universe['Pos_Base_Score'] = df_universe['stock_position'].apply(lambda x: 30 if '多头' in x else (20 if '超跌' in x else 0))
        
        # 🎯 最终实战选股打分体系
        df_universe['FINAL_BUY_SCORE'] = df_universe['Market_Multiplier'] * (df_universe['Pos_Base_Score'] + df_universe['Total_Score'])

        # 打印今日实盘选出的极品 (得分 > 60)
        top_picks = df_universe[df_universe['FINAL_BUY_SCORE'] >= 60].sort_values('FINAL_BUY_SCORE', ascending=False)
        
        logger.info(f"🏆 特征解构与加权评分完成！总计产生 {len(top_picks)} 个高分实战信号。")
        # 可以将 top_picks 导出至 CSV 用于实盘拦截

if __name__ == '__main__':
    main()
