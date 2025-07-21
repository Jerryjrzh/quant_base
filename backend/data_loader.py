import os
import struct
import pandas as pd
from datetime import datetime

def get_daily_data(file_path):
    """从.day文件读取完整的日线数据"""
    data = []
    record_size = 32
    unpack_format = '<IIIIIfI'
    unpack_size = struct.calcsize(unpack_format)
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(record_size)
            if len(chunk) < record_size: break
            try:
                date, open_p, high_p, low_p, close_p, amount, volume = struct.unpack(unpack_format, chunk[:unpack_size])
                open_p, high_p, low_p, close_p = open_p / 100, high_p / 100, low_p / 100, close_p / 100
                if open_p <= 0: continue
                data.append({
                    'date': datetime.strptime(str(date), '%Y%m%d'), 'open': open_p, 'high': high_p, 
                    'low': low_p, 'close': close_p, 'volume': volume
                })
            except (struct.error, ValueError): continue
    if not data: return None
    return pd.DataFrame(data).sort_values('date').reset_index(drop=True)

def get_5min_data(file_path):
    """从.lc5文件读取5分钟线数据"""
    data = []
    record_size = 32
    # 5分钟线数据格式：日期时间(4字节) + 开高低收(各4字节) + 成交量(4字节) + 成交额(4字节) + 保留字段(8字节)
    unpack_format = '<IIIIIIfI'
    unpack_size = struct.calcsize(unpack_format)
    
    try:
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(record_size)
                if len(chunk) < record_size: 
                    break
                try:
                    # 解析5分钟线数据
                    datetime_int, open_p, high_p, low_p, close_p, volume, amount, reserved = struct.unpack(unpack_format, chunk[:unpack_size])
                    
                    # 价格数据除以100转换为实际价格
                    open_p, high_p, low_p, close_p = open_p / 100, high_p / 100, low_p / 100, close_p / 100
                    
                    # 跳过无效数据
                    if open_p <= 0 or high_p <= 0 or low_p <= 0 or close_p <= 0:
                        continue
                    
                    # 解析日期时间
                    # 格式通常为：YYYYMMDDHHMMSS 或类似格式
                    try:
                        if datetime_int > 99999999:  # 包含时间信息
                            # 假设格式为 YYYYMMDDHHMM
                            date_part = datetime_int // 10000
                            time_part = datetime_int % 10000
                            hour = time_part // 100
                            minute = time_part % 100
                            
                            year = date_part // 10000
                            month = (date_part % 10000) // 100
                            day = date_part % 100
                            
                            dt = datetime(year, month, day, hour, minute)
                        else:
                            # 只有日期信息，默认时间为09:30
                            dt = datetime.strptime(str(datetime_int), '%Y%m%d')
                            dt = dt.replace(hour=9, minute=30)
                    except (ValueError, OverflowError):
                        continue
                    
                    data.append({
                        'datetime': dt,
                        'date': dt.date(),
                        'time': dt.time(),
                        'open': open_p,
                        'high': high_p,
                        'low': low_p,
                        'close': close_p,
                        'volume': volume,
                        'amount': amount
                    })
                    
                except (struct.error, ValueError, OverflowError) as e:
                    continue
                    
    except FileNotFoundError:
        print(f"5分钟线文件不存在: {file_path}")
        return None
    except Exception as e:
        print(f"读取5分钟线数据失败: {e}")
        return None
    
    if not data:
        return None
    
    # 转换为DataFrame并按时间排序
    df = pd.DataFrame(data).sort_values('datetime').reset_index(drop=True)
    return df

def get_multi_timeframe_data(stock_code, base_path=None):
    """获取多周期数据（日线 + 5分钟线）"""
    if base_path is None:
        base_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    
    market = stock_code[:2]
    
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
            result['daily_data'] = get_daily_data(daily_file)
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
