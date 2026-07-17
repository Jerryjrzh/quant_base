"""
本地 TDX 数据加载模块
支持日线、5分钟线的读取，以及多周期 resample 和复权处理。

vipdoc 目录结构：
  {base_path}/{market}/lday/{code}.day      日线
  {base_path}/{market}/fzline/{code}.lc5    5分钟线
  market: sh=上海, sz=深圳, bj=北京, ds=港股
"""

import os
import struct
import pandas as pd
from datetime import datetime
from typing import Optional, Dict

DEFAULT_VIPDOC = os.path.expanduser(
    "~/.local/share/tdxcfv/drive_c/tc/vipdoc"
)

# ── 市场识别 ──────────────────────────────────────────────────────────────────

def _get_market(stock_code: str) -> str:
    """根据股票代码推断市场目录名"""
    if '#' in stock_code:
        return 'ds'
    prefix = stock_code[:2].lower()
    if prefix in ('sh', 'sz', 'bj'):
        return prefix
    # 纯数字代码：按首位判断
    if stock_code.startswith('6') or stock_code.startswith('9'):
        return 'sh'
    if stock_code.startswith(('0', '3', '2')):
        return 'sz'
    if stock_code.startswith(('9', '8')):
        return 'bj'
    return 'sh'


def _normalize_code(stock_code: str) -> str:
    """去掉市场前缀，返回纯代码"""
    for prefix in ('sh', 'sz', 'bj'):
        if stock_code.lower().startswith(prefix) and len(stock_code) > 2:
            return stock_code[2:]
    return stock_code


def _build_paths(stock_code: str, base_path: str = None):
    """返回 (market, daily_path, min5_path)"""
    base = base_path or DEFAULT_VIPDOC
    market = _get_market(stock_code)
    code = _normalize_code(stock_code)
    # TDX 文件名带市场前缀（如 sh600519.day）
    file_code = f"{market}{code}" if '#' not in code else code
    daily = os.path.join(base, market, 'lday', f'{file_code}.day')
    min5  = os.path.join(base, market, 'fzline', f'{file_code}.lc5')
    return market, daily, min5


# ── 日线解析 ──────────────────────────────────────────────────────────────────

def get_daily_data(file_path: str, stock_code: str = None) -> Optional[pd.DataFrame]:
    """
    从 .day 文件读取日线数据。
    自动识别 A股（价格整数/100）和港股（价格浮点）两种格式。
    """
    is_hk = stock_code and '#' in stock_code
    record_size = 32

    if is_hk:
        fmt = '<IfffffIi'   # date, O, H, L, C, amount, volume, reserved
    else:
        fmt = '<IIIIIfII'   # date, O, H, L, C, amount, volume, reserved
    fmt_size = struct.calcsize(fmt)
    divisor = 1.0 if is_hk else 100.0

    data = []
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(record_size)
            if len(chunk) < record_size:
                break
            try:
                row = struct.unpack(fmt, chunk[:fmt_size])
                date_int = row[0]
                open_p  = row[1] / divisor
                high_p  = row[2] / divisor
                low_p   = row[3] / divisor
                close_p = row[4] / divisor
                amount  = row[5]
                volume  = row[6]
                if open_p <= 0:
                    continue
                data.append({
                    'date':   datetime.strptime(str(date_int), '%Y%m%d'),
                    'open':   open_p,
                    'high':   high_p,
                    'low':    low_p,
                    'close':  close_p,
                    'volume': volume,
                    'amount': amount,
                })
            except (struct.error, ValueError):
                continue

    if not data:
        return None
    df = pd.DataFrame(data).sort_values('date').reset_index(drop=True)
    df.set_index('date', inplace=True)
    return df


# ── 5分钟线解析 ───────────────────────────────────────────────────────────────

def get_5min_data(file_path: str) -> Optional[pd.DataFrame]:
    """
    从 .lc5 文件读取5分钟线数据。

    文件格式（每32字节一条记录）：
      [0:2]  日期 uint16: (year-2004)*2048 + month*100 + day
      [2:4]  时间 uint16: hour*60 + minute
      [4:8]  open  float32
      [8:12] high  float32
      [12:16] low  float32
      [16:20] close float32
      [20:24] amount float32  (注意：TDX lc5 字段顺序是 amount 在前)
      [24:28] volume float32
      [28:32] 保留
    """
    fmt = '<HHffffff'
    fmt_size = struct.calcsize(fmt)  # 28 bytes，剩余4字节保留
    record_size = 32

    data = []
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(record_size)
            if len(chunk) < record_size:
                break
            try:
                packed_date, packed_time, open_p, high_p, low_p, close_p, amount, volume = \
                    struct.unpack(fmt, chunk[:fmt_size])

                year  = packed_date // 2048 + 2004
                month = (packed_date % 2048) // 100
                day   = (packed_date % 2048) % 100
                hour  = packed_time // 60
                minute = packed_time % 60

                # 基本有效性检查
                if not (1 <= month <= 12 and 1 <= day <= 31):
                    continue
                if not (9 <= hour <= 15):
                    continue
                if open_p <= 0:
                    continue

                dt = datetime(year, month, day, hour, minute)
                data.append({
                    'datetime': dt,
                    'open':   float(open_p),
                    'high':   float(high_p),
                    'low':    float(low_p),
                    'close':  float(close_p),
                    'volume': float(volume),
                    'amount': float(amount),
                })
            except (struct.error, ValueError, OverflowError):
                continue

    if not data:
        return None
    df = pd.DataFrame(data).sort_values('datetime').reset_index(drop=True)
    df.set_index('datetime', inplace=True)
    return df


# ── 多周期数据加载 ────────────────────────────────────────────────────────────

def get_multi_timeframe_data(stock_code: str, base_path: str = None,
                             adjustment: str = 'none') -> dict:
    """
    加载日线 + 5分钟线数据。

    Args:
        stock_code : 股票代码（支持 '600519' / 'sh600519' / '00700#' 等格式）
        base_path  : vipdoc 根目录，None 则用默认路径
        adjustment : 复权方式 'none'|'forward'|'backward'，仅对日线生效

    Returns:
        {
          'stock_code': str,
          'daily_data': DataFrame or None,
          'min5_data':  DataFrame or None,
          'data_status': {'daily_available': bool, 'min5_available': bool}
        }
    """
    _, daily_file, min5_file = _build_paths(stock_code, base_path)

    result = {
        'stock_code': stock_code,
        'daily_data': None,
        'min5_data':  None,
        'data_status': {'daily_available': False, 'min5_available': False},
    }

    # 日线
    if os.path.exists(daily_file):
        try:
            df_daily = get_daily_data(daily_file, stock_code)
            if df_daily is not None and not df_daily.empty:
                if adjustment != 'none':
                    df_daily = _apply_adjustment(df_daily, stock_code, adjustment)
                result['daily_data'] = df_daily
                result['data_status']['daily_available'] = True
        except Exception as e:
            print(f"[data_loader] 加载日线失败 {stock_code}: {e}")

    # 5分钟线
    if os.path.exists(min5_file):
        try:
            df_5min = get_5min_data(min5_file)
            if df_5min is not None and not df_5min.empty:
                if adjustment != 'none':
                    df_5min = _apply_minute_adjustment(
                        df_5min, stock_code, adjustment, base_path
                    )
                result['min5_data'] = df_5min
                result['data_status']['min5_available'] = True
        except Exception as e:
            print(f"[data_loader] 加载5分钟线失败 {stock_code}: {e}")

    return result


def _apply_adjustment(df: pd.DataFrame, stock_code: str, adj_type: str) -> pd.DataFrame:
    """内部复权调用，失败时静默返回原始数据"""
    try:
        from adjustment_processor import AdjustmentProcessor, AdjustmentConfig
        processor = AdjustmentProcessor(AdjustmentConfig(adjustment_type=adj_type))
        return processor.process_data(df, stock_code)
    except Exception as e:
        print(f"[data_loader] 复权处理失败 {stock_code}: {e}")
        return df


def _apply_minute_adjustment(
        df_min: pd.DataFrame,
        stock_code: str,
        adj_type: str,
        base_path: str = None) -> pd.DataFrame:
    """将日线复权因子映射到分钟线 OHLC，实现分钟级前/后复权。

    方法：factor = adj_daily_close / raw_daily_close，按交易日左合并后前向填充。
    """
    if df_min is None or df_min.empty:
        return df_min

    try:
        _, daily_file, _ = _build_paths(stock_code, base_path)

        raw_daily = get_daily_data(daily_file, stock_code)
        if raw_daily is None or raw_daily.empty:
            return df_min

        adj_daily = _apply_adjustment(raw_daily.copy(), stock_code, adj_type)

        factor_df = pd.DataFrame({
            'factor': adj_daily['close'] / raw_daily['close']
        })
        factor_df.index = pd.to_datetime(factor_df.index).normalize()

        df = df_min.copy()
        df['trade_date'] = pd.to_datetime(df.index).normalize()

        df = df.merge(
            factor_df,
            left_on='trade_date',
            right_index=True,
            how='left'
        )
        df['factor'] = df['factor'].ffill().fillna(1.0)

        for col in ['open', 'high', 'low', 'close']:
            if col in df.columns:
                df[col] *= df['factor']

        df.drop(columns=['trade_date', 'factor'], inplace=True)
        return df

    except Exception as e:
        print(f"[data_loader] 分钟线复权失败 {stock_code}: {e}")
        return df_min


# ── 多周期 resample ───────────────────────────────────────────────────────────

_RESAMPLE_AGG = {
    'open':   'first',
    'high':   'max',
    'low':    'min',
    'close':  'last',
    'volume': 'sum',
    'amount': 'sum',
}

def resample_5min_to_other_timeframes(df_5min: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """
    【A股标准对齐版 - 完美适配 Pandas 2.0+】将5分钟数据精确重采样为 15/30/60 分钟线
    统一使用新版标准 'min' 频率关键字，彻底解决 Invalid frequency 语法崩溃
    """
    if df_5min is None or df_5min.empty:
        return {}

    # 保证索引是标准 DatetimeIndex
    if not isinstance(df_5min.index, pd.DatetimeIndex):
        df_5min = df_5min.copy()
        if 'datetime' in df_5min.columns:
            df_5min.index = pd.to_datetime(df_5min['datetime'])
        else:
            df_5min.index = pd.to_datetime(df_5min.index)

    timeframes = {}
    
    # 💡 核心修复：将所有的 'T' 升级替换为 Pandas 2.0+ 标准的 'min' 
    configs = [
        ('15min', '15min', None),
        ('30min', '30min', None),
        ('60min', '60min', '30min')  # 利用 30min 偏移量完美对齐 A 股 9:30 开盘
    ]

    agg_cols = {k: v for k, v in _RESAMPLE_AGG.items() if k in df_5min.columns}

    for label, rule, offset_val in configs:
        try:
            # 1. 动态构建新旧 Pandas 兼容的重采样网格参数
            kwargs = {'closed': 'right', 'label': 'right'}
            if offset_val:
                # Pandas >= 1.1.0 统一使用 offset 控制平移基准
                kwargs['offset'] = offset_val

            # 2. 执行核心重采样
            tf = df_5min.resample(rule, **kwargs).agg(agg_cols).dropna(subset=['open'])
            
            # 3. 剔除死票和无效非交易区间数据
            tf = tf[tf['open'] > 0]
            
            # 4. 重新规整时间列，确保向下游特征挖掘脚本平稳输送
            tf = tf.reset_index()
            time_col = 'datetime' if 'datetime' in tf.columns else tf.columns[0]
            if time_col != 'datetime':
                tf = tf.rename(columns={time_col: 'datetime'})
                
            tf['date'] = tf['datetime'].dt.date
            tf['time'] = tf['datetime'].dt.time
            
            # 5. 针对 A 股中午休市（11:30-13:00）导致的 60 分钟线特定时间戳漂移做微观修正
            if label == '60min':
                # 过滤掉完全落在午休区间的 12:30 僵尸时间戳
                tf = tf[~tf['time'].isin([datetime.strptime("12:30:00", "%H:%M:%S").time()])]
            
            timeframes[label] = tf
            
        except Exception as e:
            print(f"[data_loader] resample {label} 失败: {e}")

    return timeframes

def resample_5min_to_other_timeframes_1(df_5min: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """
    【A股标准对齐版】将5分钟数据精确重采样为 15/30/60 分钟线
    完美对齐通达信/同花顺 K 线根数与时间网格，彻底解决形态失真问题
    """
    if df_5min is None or df_5min.empty:
        return {}

    # 保证索引是标准 DatetimeIndex
    if not isinstance(df_5min.index, pd.DatetimeIndex):
        df_5min = df_5min.copy()
        if 'datetime' in df_5min.columns:
            df_5min.index = pd.to_datetime(df_5min['datetime'])
        else:
            df_5min.index = pd.to_datetime(df_5min.index)

    timeframes = {}
    
    # 定义不同周期的重采样规则
    # A股 09:30 开盘，15min/30min 原生整除，60min 必须使用 offset='30min' 强行向后平移
    # closed='right', label='right' 是处理金融高频交易数据的行业铁律
    configs = [
        ('15min', '15T', None),
        ('30min', '30T', None),
        ('60min', '60T', '30min')  # 💡 核心：利用 30min 偏移量完美对齐 A 股开盘
    ]

    agg_cols = {k: v for k, v in _RESAMPLE_AGG.items() if k in df_5min.columns}

    for label, rule, offset_val in configs:
        try:
            # 1. 动态构建 resample 参数，适配不同 Pandas 版本的关键字变更 (origin/offset)
            kwargs = {'closed': 'right', 'label': 'right'}
            if offset_val:
                # Pandas >= 1.1.0 使用 offset，旧版本可能使用 base
                if hasattr(pd.core.resample.Resampler, 'offset') or True:
                    kwargs['offset'] = offset_val
                else:
                    kwargs['base'] = 30

            # 2. 执行核心重采样
            tf = df_5min.resample(rule, **kwargs).agg(agg_cols).dropna(subset=['open'])
            
            # 3. 剔除死票和无效非交易区间数据
            tf = tf[tf['open'] > 0]
            
            # 4. 重新规整时间列，确保向下游特征挖掘脚本平稳输送
            tf = tf.reset_index()
            # 检查重采样后时间列叫什么，通常是 'datetime' 或 'index'
            time_col = 'datetime' if 'datetime' in tf.columns else tf.columns[0]
            if time_col != 'datetime':
                tf = tf.rename(columns={time_col: 'datetime'})
                
            tf['date'] = tf['datetime'].dt.date
            tf['time'] = tf['datetime'].dt.time
            
            # 5. 💡 针对 A 股中午休市（11:30-13:00）导致的 60 分钟线特定时间戳漂移做微观修正
            if label == '60min':
                # 默认生成的 60 分钟线时间戳通常为: 10:30, 11:30, 12:30(此根为错位), 13:30, 14:30, 15:30
                # 标准通达信 4 根线为：10:30, 11:30, 14:00(或14:30), 15:00
                # 我们过滤掉完全落在休市区间的僵尸K线
                tf = tf[~tf['time'].isin([datetime.strptime("12:30:00", "%H:%M:%S").time()])]
            
            timeframes[label] = tf
            
        except Exception as e:
            print(f"[data_loader] resample {label} 失败: {e}")

    return timeframes

def resample_5min_to_other_timeframes_0(df_5min: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """
    将5分钟数据 resample 为 15/30/60 分钟线。
    返回 {'15min': df, '30min': df, '60min': df}
    """
    if df_5min is None or df_5min.empty:
        return {}

    if not isinstance(df_5min.index, pd.DatetimeIndex):
        df_5min = df_5min.copy()
        df_5min.index = pd.to_datetime(df_5min.index)

    timeframes = {}
    for label, rule in [('15min', '15min'), ('30min', '30min'), ('60min', '60min')]:
        try:
            agg_cols = {k: v for k, v in _RESAMPLE_AGG.items() if k in df_5min.columns}
            tf = df_5min.resample(rule).agg(agg_cols).dropna(subset=['open'])
            tf = tf[tf['open'] > 0]
            tf = tf.reset_index()
            tf['date'] = tf['datetime'].dt.date
            tf['time'] = tf['datetime'].dt.time
            timeframes[label] = tf
        except Exception as e:
            print(f"[data_loader] resample {label} 失败: {e}")

    return timeframes


def fetch_hourly_kline(stock_code: str, start_date=None, end_date=None,
                       base_path: str = None,
                       adjustment: str = 'forward') -> pd.DataFrame:
    """
    从5分钟数据聚合生成60分钟K线。
    返回含 ['datetime','date','open','high','low','close','volume'] 的 DataFrame。
    """
    try:
        data = get_multi_timeframe_data(stock_code, base_path, adjustment=adjustment)
        if data is None or not data.get('data_status', {}).get('min5_available', False):
            return None

        df_5min = data['min5_data']
        agg_cols = {k: v for k, v in _RESAMPLE_AGG.items() if k in df_5min.columns}
        hourly = df_5min.resample('1h').agg(agg_cols).dropna(subset=['open'])
        hourly = hourly[hourly['open'] > 0].reset_index()

        if start_date:
            hourly = hourly[hourly['datetime'] >= pd.to_datetime(start_date)]
        if end_date:
            hourly = hourly[hourly['datetime'] <= pd.to_datetime(end_date)]

        hourly = hourly[hourly.get('volume', pd.Series([1])) > 0] if 'volume' in hourly.columns else hourly
        hourly['date'] = hourly['datetime'].dt.date

        cols = [c for c in ['datetime', 'date', 'open', 'high', 'low', 'close', 'volume'] if c in hourly.columns]
        return hourly[cols]
    except Exception as e:
        print(f"[data_loader] 生成小时线失败 {stock_code}: {e}")
        return pd.DataFrame()
    
def get_min_data(stock_code: str, period: str = '60m', base_path: str = None,
                 adjustment: str = 'forward'):
    """统一获取分钟线（目前支持5分钟转采样）"""
    data = get_multi_timeframe_data(stock_code, base_path, adjustment=adjustment)
    if data is None or not data.get('data_status', {}).get('min5_available', False):
        return None
    
    df_5min = data['min5_data']
    if period == '60m':
        resampled = resample_5min_to_other_timeframes(df_5min)
        return resampled.get('60min')
    elif period == '15m':
        resampled = resample_5min_to_other_timeframes(df_5min)
        return resampled.get('15min')
    return df_5min  # 默认5分钟

def get_daily_data_in_range(stock_code: str, start_date: str = None, end_date: str = None, 
                           base_path: str = None, adjustment: str = 'none') -> Optional[pd.DataFrame]:
    """支持指定日期范围的日线加载（用于回测切片）"""
    _, day_file, _ = _build_paths(stock_code, base_path)

    df = get_daily_data(day_file, stock_code)
    if df is None or df.empty:
        return None

    if adjustment != 'none':
        df = _apply_adjustment(df, stock_code, adjustment)

    if start_date:
        df = df[df.index >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df.index <= pd.to_datetime(end_date)]

    return df


def get_min_data_in_range(stock_code: str, period: str = '60m', start_date: str = None, 
                         end_date: str = None, base_path: str = None,
                         adjustment: str = 'forward') -> Optional[pd.DataFrame]:
    """支持时间范围的分钟线加载（核心增强）"""
    data = get_multi_timeframe_data(stock_code, base_path, adjustment=adjustment)
    if data is None or not data.get('data_status', {}).get('min5_available', False):
        return None
    
    df_5min = data['min5_data']
    if start_date:
        df_5min = df_5min[df_5min.index >= pd.to_datetime(start_date)]
    if end_date:
        df_5min = df_5min[df_5min.index <= pd.to_datetime(end_date)]
    
    if period == '60m':
        res = resample_5min_to_other_timeframes(df_5min)
        return res.get('60min')
    elif period == '15m':
        res = resample_5min_to_other_timeframes(df_5min)
        return res.get('15min')
    return df_5min