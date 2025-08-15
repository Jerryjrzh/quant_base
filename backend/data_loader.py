import os
import struct
import pandas as pd
from datetime import datetime

def get_daily_data(file_path, stock_code=None):
    """
    从.day文件读取完整的日线数据。
    【已合并】能自动识别并解析沪深A股和港股两种不同的文件格式。
    """
    data = []
    record_size = 32

    # --- 核心逻辑：根据股票代码选择解析方案 ---
    is_hk_stock = stock_code and '#' in stock_code
    
    if is_hk_stock:
        # 港股 (.day文件) 格式：价格和成交额为浮点数
        # 格式: 4字节日期(I), 4*4字节OHLC价(f), 4字节成交额(f), 4字节成交量(i), 4字节保留(I)
        unpack_format = '<IfffffIi' # 注意：成交量为有符号整数i，与A股不同
        price_divisor = 1.0  # 价格已经是float，无需除法
    else:
        # 沪深A股 (.day文件) 格式：价格为整数，成交额为浮点数
        # 格式: 5*4字节整数(I)OHLC, 4字节成交额(f), 4字节成交量(I)
        unpack_format = '<IIIIIfI'
        price_divisor = 100.0 # 价格是整数，需要除以100

    unpack_size = struct.calcsize(unpack_format)
    # --- 方案选择结束 ---

    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(record_size)
            if len(chunk) < record_size:
                break
            
            try:
                # 使用选择好的格式进行一次解包
                if is_hk_stock:
                    date, open_p, high_p, low_p, close_p, amount, volume, _reserved = struct.unpack(unpack_format, chunk)
                else:
                    date, open_p, high_p, low_p, close_p, amount, volume = struct.unpack(unpack_format, chunk[:unpack_size])

                # 使用选择好的除数处理价格
                # (对港股来说，除以1.0等于没变)
                open_p /= price_divisor
                high_p /= price_divisor
                low_p /= price_divisor
                close_p /= price_divisor
                
                if open_p <= 0:
                    continue

                data.append({
                    'date': datetime.strptime(str(date), '%Y%m%d'),
                    'open': open_p,
                    'high': high_p,
                    'low': low_p,
                    'close': close_p,
                    'volume': volume,
                    'amount': amount
                })
            except (struct.error, ValueError):
                continue
    
    if not data:
        return None
        
    df = pd.DataFrame(data).sort_values('date').reset_index(drop=True)
    df.set_index('date', inplace=True) # 设置日期为索引，确保是DatetimeIndex
    return df

def get_5min_data(file_path):
    """
    从.lc5文件读取5分钟线数据
    文件格式说明: 每32字节一条记录
    - 2字节: 日期 (ushort), (year - 2004) * 2048 + month * 100 + day
    - 2字节: 时间 (ushort), hour * 60 + minute
    - 4字节: open (float)
    - 4字节: high (float)
    - 4字节: low (float)
    - 4字节: close (float)
    - 4字节: volume (float)
    - 4字节: amount (float)
    - 4字节: (保留)
    """
    data = []
    record_size = 32
    # 定义解包格式：2个unsigned short, 6个float
    unpack_format = '<HHffffff'
    unpack_size = struct.calcsize(unpack_format)

    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(record_size)
            if len(chunk) < record_size:
                break
            try:
                packed_date, packed_time, open_p, high_p, low_p, close_p, volume, amount = struct.unpack(unpack_format, chunk[:unpack_size])

                # 解码日期
                year = packed_date // 2048 + 2004
                month = (packed_date % 2048) // 100
                day = packed_date % 100

                # 解码时间
                hour = packed_time // 60
                minute = packed_time % 60
                
                # 合成datetime对象
                dt = datetime(year, month, day, hour, minute)
                
                if open_p <= 0: continue

                data.append({
                    'datetime': dt,
                    'open': open_p,
                    'high': high_p,
                    'low': low_p,
                    'close': close_p,
                    'volume': volume,
                    'amount': amount
                })
            except (struct.error, ValueError):
                continue
    
    if not data:
        return None
        
    df = pd.DataFrame(data).sort_values('datetime').reset_index(drop=True)
    # 设置datetime为索引，确保是DatetimeIndex
    df.set_index('datetime', inplace=True)
    return df

def get_multi_timeframe_data(stock_code, base_path=None):
    """获取多周期数据（日线 + 5分钟线）"""
    if base_path is None:
        base_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    
    # 根据股票代码确定市场
    if '#' in stock_code:
        market = 'ds'  # 港股
    else:
        market = stock_code[:2]  # A股
    
    # 构建文件路径
    daily_file = os.path.join(base_path, market, 'lday', f'{stock_code}.day')
    min5_file = os.path.join(base_path, market, 'fzline', f'{stock_code}.lc5')
    
    result = {
        'stock_code': stock_code,
        'daily_data': None,
        'min5_data': None,
        'data_status': {
            'daily_available': False,
            'min5_available': False
        }
    }
    
    # 加载日线数据
    if os.path.exists(daily_file):
        try:
            result['daily_data'] = get_daily_data(daily_file, stock_code)
            result['data_status']['daily_available'] = result['daily_data'] is not None
        except Exception as e:
            print(f"加载日线数据失败 {stock_code}: {e}")
    
    # 加载5分钟线数据
    if os.path.exists(min5_file):
        try:
            result['min5_data'] = get_5min_data(min5_file)
            result['data_status']['min5_available'] = result['min5_data'] is not None
        except Exception as e:
            print(f"加载5分钟线数据失败 {stock_code}: {e}")
    
    return result

def resample_5min_to_other_timeframes(df_5min):
    """将5分钟数据重采样为其他时间周期"""
    if df_5min is None or df_5min.empty:
        return {}
    
    # 设置datetime为索引
    df_5min = df_5min.set_index('datetime')
    
    timeframes = {}
    
    try:
        # 15分钟线
        timeframes['15min'] = df_5min.resample('15T').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum',
            'amount': 'sum'
        }).dropna()
        
        # 30分钟线
        timeframes['30min'] = df_5min.resample('30T').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum',
            'amount': 'sum'
        }).dropna()
        
        # 60分钟线
        timeframes['60min'] = df_5min.resample('60T').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum',
            'amount': 'sum'
        }).dropna()
        
        # 重置索引并添加日期时间列
        for tf_name, tf_data in timeframes.items():
            tf_data.reset_index(inplace=True)
            tf_data['date'] = tf_data['datetime'].dt.date
            tf_data['time'] = tf_data['datetime'].dt.time
            
    except Exception as e:
        print(f"重采样数据失败: {e}")
        return {}
    
    return timeframes
