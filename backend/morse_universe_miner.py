import os
import glob
import pandas as pd
import numpy as np
from multiprocessing import Pool, cpu_count
from datetime import datetime
import logging

import data_loader

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'morse_analytics')
os.makedirs(OUTPUT_DIR, exist_ok=True)

log_file = os.path.join(OUTPUT_DIR, f'morse_miner_{datetime.now().strftime("%Y%m%d")}.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'), # 输出到日志文件
        logging.StreamHandler()                          # 依然保留精简的控制台输出
    ]
)
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

def _to_morse_char(open_p, high, low, close, vol, vol_ma20, period='daily') -> str:
    """【基因测序单原子】将任意一根K线瞬间转化为3位莫尔斯电码"""
    # 1. 🎯 动态波动率阈值 (基于时间平方根法则)
    # 日线基准: U(5%), u(1%), D(-4%), d(-1%)
    # 60m基准 (约日线的 1/2): U(2.5%), u(0.5%)
    # 15m基准 (约日线的 1/4): U(1.25%), u(0.25%)
    BODY_THRESHOLDS = {
        'daily': {'U': 0.062,   'u': 0.027,   'D': -0.062,   'd': -0.027},
        '60m':   {'U': 0.009,  'u': 0.0035,  'D': -0.009,   'd': -0.0035},
        '15m':   {'U': 0.0062, 'u': 0.0024, 'D': -0.0062,   'd': -0.0024}
    }
    t = BODY_THRESHOLDS.get(period, BODY_THRESHOLDS['daily'])
    # 实体测序 (使用自适应阈值)
    pct = (close - open_p) / (open_p + 1e-9)
    if pct > t['U']:     body = 'U'
    elif pct > t['u']:   body = 'u'
    elif pct < t['D']:   body = 'D'
    elif pct < t['d']:   body = 'd'
    else:                body = 'X'
    
    # 2. 影线测序
    upper_shadow = high - max(close, open_p)
    lower_shadow = min(close, open_p) - low
    body_size = abs(close - open_p)
    
    if lower_shadow > body_size * 1.2 and lower_shadow > upper_shadow:    shadow = 'B'
    elif upper_shadow > body_size * 1.2 and upper_shadow > lower_shadow:  shadow = 'T'
    elif upper_shadow < body_size * 0.1 and lower_shadow < body_size * 0.1: shadow = 'N'
    else:                                                                 shadow = 'S'
    
    # 3. 🎯 动态量能阈值 (应对日内U型潮汐现象)
    # 越微观的时间，其爆量的振幅越大，地量的深度越深。必须放宽开口，否则全是 H 或 L。
    VOL_THRESHOLDS = {
        'daily': {'H': 1.9, 'L': 0.8},
        '60m':   {'H': 2.2, 'L': 0.6},
        '15m':   {'H': 2.5, 'L': 0.5}  # 15分钟极易受开盘尾盘影响，开口必须放大
    }
    vt = VOL_THRESHOLDS.get(period, VOL_THRESHOLDS['daily'])
    
    # 量能测序 (使用自适应阈值)
    vol_ratio = vol / (vol_ma20 + 1e-9)
    if vol_ratio > vt['H']:   volume = 'H'
    elif vol_ratio < vt['L']: volume = 'L'
    else:                     volume = 'A'
    
    return f"{body}{shadow}{volume}"

def build_timeframe_morse_string(df, last_date, count=4, period='daily') -> str:
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
        char = _to_morse_char(row['open'], row['high'], row['low'], row['close'], row['volume'], v_ma, period)
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
            morse_daily = build_timeframe_morse_string(df_daily, t_minus_2, count=4, period='daily')
            
            # 🧬 2. 个股小时线莫尔斯码（整个 T-1 交易日内的 4 根 60分钟K线形态）
            morse_60m = build_timeframe_morse_string(df_60m, f"{t_minus_1.strftime('%Y-%m-%d')} 15:30:00", count=4, period='60m')
            
            # 🧬 3. 个股15分钟线莫尔斯码（T-1 交易日最后尾盘半小时的 2 根 15分钟K线微操微观基因）
            morse_15m = build_timeframe_morse_string(df_15m, f"{t_minus_1.strftime('%Y-%m-%d')} 15:30:00", count=2, period='15m')
            
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
    files = glob.glob(os.path.join(vipdoc_base, "sh", "lday", "*.day")) + glob.glob(os.path.join(vipdoc_base, "sz", "lday", "*.day")) + glob.glob(os.path.join(vipdoc_base, "bj", "lday", "*.day"))
    
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
    # 4. 🧬 【基因单体 Bit 位大解剖：寻找暴击因子与毒药因子】
    # =================================================================
    df_universe = pd.DataFrame(final_dataset)
    if df_universe.empty: return

    logger.info("⚔️ 正在执行单体 Bit 位降维解析并输出报告...")

    # 定义双极阈值：大肉 (>28%) vs 哑火/毒药 (<8%)
    df_universe['is_golden'] = (df_universe['max_rebound_3d'] >= 0.28).astype(int)
    df_universe['is_trash'] = (df_universe['max_rebound_3d'] < 0.08).astype(int)

    # 安全过滤：剔除高危大盘样本，保留安全和震荡市，并在多头主升和超跌深坑中寻找
    safe_df = df_universe[
        (df_universe['market_risk_level'].str.contains('安全|震荡', na=False)) &
        (df_universe['stock_position'].str.contains('多头|超跌', na=False))
    ].copy()

    if safe_df.empty:
        logger.warning("⚠️ 安全环境下的有效样本为空，跳过 Bit 位统计。")
        return

    # 🔬 将 K线基因串拆解为 9 个独立 Bit 位
    # 格式示例：daily_last2="USA-XBL" -> T2_Body='U', T2_Shadow='S', T2_Vol='A', T1_Body='X'...
    def extract_bits(row):
        d_last2 = str(row.get('daily_last2', ''))
        m_last = str(row.get('m15_last', ''))
        
        # 初始化占位符
        bits = ['?']*9 
        
        if '-' in d_last2:
            parts = d_last2.split('-')
            if len(parts) >= 2:
                t2, t1 = parts[-2], parts[-1]
                if len(t2) == 3: bits[0:3] = list(t2)
                if len(t1) == 3: bits[3:6] = list(t1)
        
        if len(m_last) == 3:
            bits[6:9] = list(m_last)
            
        return pd.Series(bits)

    # 展开成 9 列特征
    bit_columns = ['T2_实体', 'T2_影线', 'T2_量能', 'T1_实体', 'T1_影线', 'T1_量能', 'M15_实体', 'M15_影线', 'M15_量能']
    safe_df[bit_columns] = safe_df.apply(extract_bits, axis=1)

    bit_report = []
    
    # 遍历 9 个不同的位置，以及它们可能出现的所有字符（U, d, X, B, H, L 等）
    for col in bit_columns:
        for val in safe_df[col].unique():
            if val == '?': continue  # 跳过解析失败的残缺位
            
            # 分离出多头和超跌的独立统计
            for pos in ['📈[多头主升]', '📉[超跌深坑]']:
                subset = safe_df[(safe_df[col] == val) & (safe_df['stock_position'] == pos)]
                count = len(subset)
                
                if count >= 10:  # 只有该单一 Bit 位在历史上出现超过 10 次才具备统计价值
                    golden_rate = subset['is_golden'].mean()
                    trash_rate = subset['is_trash'].mean()
                    
                    bit_report.append({
                        '位置倾向': pos,
                        '基因位': col,
                        '字符值': val,
                        '出现次数': count,
                        '爆发率(>28%)': golden_rate,
                        '哑火率(<8%)': trash_rate,
                        '净暴击分': golden_rate - trash_rate  # 核心指标：越高说明越是真暴利因子，越低说明是毒药
                    })

    # =================================================================
    # 5. 🗄️ 结果落盘与日志静默输出
    # =================================================================
    if bit_report:
        df_report = pd.DataFrame(bit_report)
        
        # 👑 提取最强看多因子 (真金榜)
        bullish_df = df_report.sort_values(by='净暴击分', ascending=False).head(30)
        # ☠️ 提取最强看空/骗炮因子 (排雷榜)
        bearish_df = df_report.sort_values(by='净暴击分', ascending=True).head(30)
        
        date_str = datetime.now().strftime("%Y%m%d_%H%M")
        
        # 将全部详情写入 CSV 供复盘分析，控制台不再乱弹
        full_csv_path = os.path.join(OUTPUT_DIR, f'bitwise_full_report_{date_str}.csv')
        bull_csv_path = os.path.join(OUTPUT_DIR, f'bitwise_BULL_features_{date_str}.csv')
        bear_csv_path = os.path.join(OUTPUT_DIR, f'bitwise_BEAR_features_{date_str}.csv')
        
        df_report.to_csv(full_csv_path, index=False, encoding='utf-8-sig')
        bullish_df.to_csv(bull_csv_path, index=False, encoding='utf-8-sig')
        bearish_df.to_csv(bear_csv_path, index=False, encoding='utf-8-sig')
        
        logger.info(f"🏆 Bit 位独立因子测序完成！")
        logger.info(f"💾 全量 Bit 测序报告已导出至: {full_csv_path}")
        logger.info(f"🚀 最强爆拉 Bit 位榜单(看多): {bull_csv_path}")
        logger.info(f"☠️ 哑火骗炮 Bit 位榜单(排雷): {bear_csv_path}")
        
        # 控制台只打印极简的前 3 个核心因子，保持清爽
        print("\n👑 【净暴击分 Top 3 最强暴利 Bit 位】(详见导出 CSV)")
        print(bullish_df[['位置倾向', '基因位', '字符值', '出现次数', '爆发率(>28%)', '净暴击分']].head(3).to_string(index=False))
        
    else:
        logger.warning("未提取到满足基础出现次数的 Bit 位因子。")

if __name__ == '__main__':
    main()
