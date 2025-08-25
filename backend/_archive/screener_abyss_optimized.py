import os
import glob
import json
import pandas as pd
import numpy as np
from multiprocessing import Pool, cpu_count
from datetime import datetime, timedelta
import logging
import warnings
import struct
warnings.filterwarnings('ignore')

# --- 配置 ---
BASE_PATH = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
MARKETS = ['sh', 'sz', 'bj']
STRATEGY_TO_RUN = 'ABYSS_BOTTOMING_OPTIMIZED'

# --- 路径定义 ---
backend_dir = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.abspath(os.path.join(backend_dir, '..', 'data', 'result'))
CONFIG_FILE = os.path.join(backend_dir, 'abyss_config.json')

# --- 初始化日志 ---
DATE = datetime.now().strftime("%Y%m%d_%H%M")
RESULT_DIR = os.path.join(OUTPUT_PATH, STRATEGY_TO_RUN)
os.makedirs(RESULT_DIR, exist_ok=True)
LOG_FILE = os.path.join(RESULT_DIR, f'log_screener_{DATE}.txt')

# 设置更详细的日志记录
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, 'a', 'utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('abyss_screener')

# --- 加载配置 ---
def load_config():
    """加载策略配置"""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            logger.info(f"成功加载配置文件: {config['strategy_name']} v{config['version']}")
            return config
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")
        # 返回默认配置
        return {
            "core_parameters": {
                "deep_decline_phase": {
                    "long_term_days": 400,
                    "min_drop_percent": 0.40,
                    "price_low_percentile": 0.35
                },
                "volume_analysis": {
                    "volume_shrink_threshold": 0.70,
                    "volume_consistency_threshold": 0.30,
                    "volume_analysis_days": 30
                }
            }
        }

CONFIG = load_config()


def read_day_file(file_path):
    """
    读取通达信.day文件
    """
    try:
        with open(file_path, 'rb') as f:
            data = []
            while True:
                chunk = f.read(32)  # 每条记录32字节
                if len(chunk) < 32:
                    break
                
                # 解析数据结构
                date, open_price, high, low, close, amount, volume, _ = struct.unpack('<IIIIIIII', chunk)
                
                # 转换日期格式
                year = date // 10000
                month = (date % 10000) // 100
                day = date % 100
                
                # 价格需要除以100
                data.append({
                    'date': f"{year:04d}-{month:02d}-{day:02d}",
                    'open': open_price / 100.0,
                    'high': high / 100.0,
                    'low': low / 100.0,
                    'close': close / 100.0,
                    'volume': volume,
                    'amount': amount
                })
        
        if not data:
            return None
            
        # 转换为DataFrame
        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        df.sort_index(inplace=True)
        
        return df
        
    except Exception as e:
        logger.error(f"读取文件失败 {file_path}: {e}")
        return None


class AbyssBottomingStrategy:
    """
    深渊筑底策略 - 经过测试验证的优化版本
    """
    
    def __init__(self, config=None):
        if config is None:
            config = CONFIG
        
        # 提取核心参数
        core_params = config.get('core_parameters', {})
        
        self.config = {
            # 深跌筑底参数
            'long_term_days': core_params.get('deep_decline_phase', {}).get('long_term_days', 400),
            'min_drop_percent': core_params.get('deep_decline_phase', {}).get('min_drop_percent', 0.40),
            'price_low_percentile': core_params.get('deep_decline_phase', {}).get('price_low_percentile', 0.35),
            
            # 成交量分析参数
            'volume_shrink_threshold': core_params.get('volume_analysis', {}).get('volume_shrink_threshold', 0.70),
            'volume_consistency_threshold': core_params.get('volume_analysis', {}).get('volume_consistency_threshold', 0.30),
            'volume_analysis_days': core_params.get('volume_analysis', {}).get('volume_analysis_days', 30),
            
            # 其他参数
            'hibernation_days': core_params.get('hibernation_phase', {}).get('hibernation_days', 40),
            'hibernation_volatility_max': core_params.get('hibernation_phase', {}).get('hibernation_volatility_max', 0.40),
            'washout_days': core_params.get('washout_phase', {}).get('washout_days', 15),
            'washout_volume_shrink_ratio': core_params.get('washout_phase', {}).get('washout_volume_shrink_ratio', 0.85),
            'max_rise_from_bottom': core_params.get('liftoff_phase', {}).get('max_rise_from_bottom', 0.18),
            'liftoff_volume_increase_ratio': core_params.get('liftoff_phase', {}).get('liftoff_volume_increase_ratio', 1.15),
        }
        
        logger.info(f"策略初始化完成，参数: {self.config}")
    
    def calculate_technical_indicators(self, df):
        """计算技术指标"""
        try:
            # 移动平均线
            df['ma7'] = df['close'].rolling(window=7).mean()
            df['ma13'] = df['close'].rolling(window=13).mean()
            df['ma30'] = df['close'].rolling(window=30).mean()
            df['ma45'] = df['close'].rolling(window=45).mean()
            
            # RSI指标
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['rsi'] = 100 - (100 / (1 + rs))
            
            # MACD指标
            exp1 = df['close'].ewm(span=12).mean()
            exp2 = df['close'].ewm(span=26).mean()
            df['macd'] = exp1 - exp2
            df['macd_signal'] = df['macd'].ewm(span=9).mean()
            df['macd_histogram'] = df['macd'] - df['macd_signal']
            
            # 成交量移动平均
            df['volume_ma20'] = df['volume'].rolling(window=20).mean()
            df['volume_ma60'] = df['volume'].rolling(window=60).mean()
            
            return df
        except Exception as e:
            logger.error(f"计算技术指标失败: {e}")
            return df
    
    def analyze_volume_shrinkage(self, df):
        """
        分析成交量萎缩情况 - 核心优化逻辑
        """
        try:
            if len(df) < 250:
                return False, "数据不足"
            
            volumes = df['volume'].values
            
            # 1. 计算历史平均成交量（使用前半段数据作为基准）
            historical_volumes = volumes[:len(volumes)//2]
            historical_avg = np.mean(historical_volumes)
            
            # 2. 计算最近成交量
            recent_days = self.config['volume_analysis_days']
            recent_volumes = volumes[-recent_days:]
            recent_avg = np.mean(recent_volumes)
            
            # 3. 计算萎缩比例
            shrink_ratio = recent_avg / historical_avg if historical_avg > 0 else 1.0
            is_volume_shrunk = shrink_ratio <= self.config['volume_shrink_threshold']
            
            # 4. 检查地量的持续性
            threshold_volume = historical_avg * self.config['volume_shrink_threshold']
            low_volume_days = sum(1 for v in recent_volumes if v <= threshold_volume)
            consistency_ratio = low_volume_days / len(recent_volumes)
            is_consistent = consistency_ratio >= self.config['volume_consistency_threshold']
            
            # 5. 额外检查：最近成交量应该明显低于长期中位数
            long_term_median = np.percentile(volumes, 50)
            recent_vs_median = recent_avg / long_term_median if long_term_median > 0 else 1.0
            
            details = {
                'historical_avg': historical_avg,
                'recent_avg': recent_avg,
                'shrink_ratio': shrink_ratio,
                'consistency_ratio': consistency_ratio,
                'long_term_median': long_term_median,
                'recent_vs_median': recent_vs_median,
                'is_volume_shrunk': is_volume_shrunk,
                'is_consistent': is_consistent,
                'threshold_volume': threshold_volume
            }
            
            # 综合判断：成交量萎缩 且 有持续性
            volume_ok = is_volume_shrunk and is_consistent
            
            return volume_ok, details
            
        except Exception as e:
            logger.error(f"成交量分析失败: {e}")
            return False, str(e)
    
    def check_deep_decline_phase(self, df):
        """
        第零阶段：深跌筑底检查 - 经过测试验证的逻辑
        """
        try:
            long_term_days = self.config['long_term_days']
            if len(df) < long_term_days:
                return False, "数据长度不足"
            
            # 获取长期数据
            long_term_data = df.tail(long_term_days)
            long_term_high = long_term_data['high'].max()
            long_term_low = long_term_data['low'].min()
            current_price = df['close'].iloc[-1]
            
            # 1. 检查价格位置
            price_range = long_term_high - long_term_low
            if price_range == 0:
                return False, "价格无波动"
            
            price_position = (current_price - long_term_low) / price_range
            price_position_ok = price_position <= self.config['price_low_percentile']
            
            # 2. 检查下跌幅度
            drop_percent = (long_term_high - current_price) / long_term_high
            drop_percent_ok = drop_percent >= self.config['min_drop_percent']
            
            # 3. 使用优化的成交量分析
            volume_ok, volume_details = self.analyze_volume_shrinkage(df)
            
            # 综合判断
            conditions = {
                'price_position_ok': price_position_ok,
                'drop_percent_ok': drop_percent_ok,
                'volume_ok': volume_ok
            }
            
            all_ok = all(conditions.values())
            
            details = {
                'drop_percent': drop_percent,
                'price_position': price_position,
                'long_term_high': long_term_high,
                'long_term_low': long_term_low,
                'current_price': current_price,
                'conditions': conditions,
                'volume_analysis': volume_details
            }
            
            return all_ok, details
            
        except Exception as e:
            logger.error(f"深跌筑底检查失败: {e}")
            return False, str(e)
    
    def check_hibernation_phase(self, df):
        """第一阶段：横盘蓄势检查"""
        try:
            washout_days = self.config['washout_days']
            hibernation_days = self.config['hibernation_days']
            
            # 获取横盘期数据
            start_idx = -(washout_days + hibernation_days)
            end_idx = -washout_days if washout_days > 0 else len(df)
            hibernation_data = df.iloc[start_idx:end_idx]
            
            if hibernation_data.empty:
                return False, "横盘期数据为空"
            
            # 计算横盘区间
            support_level = hibernation_data['low'].min()
            resistance_level = hibernation_data['high'].max()
            
            # 检查波动率
            volatility = (resistance_level - support_level) / support_level if support_level > 0 else float('inf')
            volatility_ok = volatility <= self.config['hibernation_volatility_max']
            
            # 检查均线收敛
            if 'ma7' in hibernation_data.columns and 'ma30' in hibernation_data.columns:
                ma_values = hibernation_data[['ma7', 'ma13', 'ma30', 'ma45']].iloc[-1]
                ma_range = (ma_values.max() - ma_values.min()) / ma_values.mean()
                ma_convergence_ok = ma_range <= 0.05
            else:
                ma_convergence_ok = True
            
            # 检查成交量稳定性
            avg_volume = hibernation_data['volume'].mean()
            volume_stability = hibernation_data['volume'].std() / avg_volume if avg_volume > 0 else float('inf')
            
            details = {
                'support_level': support_level,
                'resistance_level': resistance_level,
                'volatility': volatility,
                'volatility_ok': volatility_ok,
                'ma_convergence_ok': ma_convergence_ok,
                'avg_volume': avg_volume,
                'volume_stability': volume_stability
            }
            
            return volatility_ok and ma_convergence_ok, details
            
        except Exception as e:
            logger.error(f"横盘蓄势检查失败: {e}")
            return False, str(e)
    
    def check_washout_phase(self, df, hibernation_info):
        """第二阶段：缩量挖坑检查"""
        try:
            washout_days = self.config['washout_days']
            washout_data = df.tail(washout_days)
            
            if washout_data.empty:
                return False, "挖坑期数据为空"
            
            support_level = hibernation_info['support_level']
            hibernation_avg_volume = hibernation_info['avg_volume']
            
            # 检查是否跌破支撑
            washout_low = washout_data['low'].min()
            support_broken = washout_low < support_level * 0.95
            
            # 检查挖坑期的缩量特征
            pit_days = washout_data[washout_data['low'] < support_level]
            if pit_days.empty:
                return False, "无有效挖坑数据"
            
            pit_avg_volume = pit_days['volume'].mean()
            volume_shrink_ratio = pit_avg_volume / hibernation_avg_volume if hibernation_avg_volume > 0 else float('inf')
            volume_shrink_ok = volume_shrink_ratio <= self.config['washout_volume_shrink_ratio']
            
            conditions = {
                'support_broken': support_broken,
                'volume_shrink_ok': volume_shrink_ok
            }
            
            all_ok = all(conditions.values())
            
            details = {
                'washout_low': washout_low,
                'support_break': (support_level - washout_low) / support_level if support_level > 0 else 0,
                'volume_shrink_ratio': volume_shrink_ratio,
                'pit_days_count': len(pit_days),
                'conditions': conditions
            }
            
            return all_ok, details
            
        except Exception as e:
            logger.error(f"缩量挖坑检查失败: {e}")
            return False, str(e)
    
    def check_liftoff_confirmation(self, df, washout_info):
        """第三阶段：确认拉升检查"""
        try:
            washout_low = washout_info['washout_low']
            recent_data = df.tail(3)  # 最近3天
            
            if recent_data.empty:
                return False, "确认期数据不足"
            
            latest = recent_data.iloc[-1]
            prev = recent_data.iloc[-2] if len(recent_data) > 1 else latest
            
            # 条件1：价格企稳回升
            is_price_recovering = (
                latest['close'] > latest['open'] and  # 当日阳线
                latest['close'] > prev['close'] and   # 价格上涨
                latest['low'] >= washout_low * 0.98   # 未创新低
            )
            
            # 条件2：尚未远离坑底
            rise_from_bottom = (latest['close'] - washout_low) / washout_low if washout_low > 0 else 0
            is_near_bottom = rise_from_bottom <= self.config['max_rise_from_bottom']
            
            # 条件3：成交量温和放大
            recent_volumes = df['volume'].tail(10).mean()
            volume_increase = latest['volume'] / recent_volumes if recent_volumes > 0 else 0
            is_volume_confirming = volume_increase >= self.config['liftoff_volume_increase_ratio']
            
            # 条件4：技术指标配合
            rsi_ok = 25 <= latest.get('rsi', 50) <= 60 if 'rsi' in latest else True
            macd_improving = latest.get('macd', 0) > prev.get('macd', 0) if 'macd' in latest else True
            
            conditions = {
                'price_recovering': is_price_recovering,
                'near_bottom': is_near_bottom,
                'volume_confirming': is_volume_confirming,
                'rsi_ok': rsi_ok,
                'macd_improving': macd_improving
            }
            
            conditions_met = sum(conditions.values())
            all_ok = conditions_met >= 3  # 至少满足3个条件
            
            details = {
                'rise_from_bottom': rise_from_bottom,
                'volume_increase': volume_increase,
                'conditions_met': conditions_met,
                'total_conditions': len(conditions),
                'conditions': conditions
            }
            
            return all_ok, details
            
        except Exception as e:
            logger.error(f"拉升确认检查失败: {e}")
            return False, str(e)
    
    def apply_strategy(self, df):
        """
        应用完整的深渊筑底策略
        """
        try:
            if len(df) < self.config['long_term_days']:
                return None, None
            
            # 计算技术指标
            df = self.calculate_technical_indicators(df)
            
            # 第零阶段：深跌筑底检查（必须通过）
            deep_decline_ok, deep_decline_info = self.check_deep_decline_phase(df)
            if not deep_decline_ok:
                return None, None
            
            # 第一阶段：横盘蓄势检查
            hibernation_ok, hibernation_info = self.check_hibernation_phase(df)
            if not hibernation_ok:
                # 如果横盘检查未通过，但深跌检查通过，仍可以作为潜在信号
                signal_series = pd.Series(index=df.index, dtype=object).fillna('')
                signal_series.iloc[-1] = 'POTENTIAL_BUY'
                
                signal_details = {
                    'signal_state': 'DEEP_DECLINE_ONLY',
                    'stage_passed': 1,
                    'deep_decline': deep_decline_info,
                    'hibernation': hibernation_info,
                    'strategy_version': 'optimized_v2.0'
                }
                
                return signal_series, signal_details
            
            # 第二阶段：缩量挖坑检查
            washout_ok, washout_info = self.check_washout_phase(df, hibernation_info)
            if not washout_ok:
                # 前两阶段通过，作为较强信号
                signal_series = pd.Series(index=df.index, dtype=object).fillna('')
                signal_series.iloc[-1] = 'BUY'
                
                signal_details = {
                    'signal_state': 'HIBERNATION_CONFIRMED',
                    'stage_passed': 2,
                    'deep_decline': deep_decline_info,
                    'hibernation': hibernation_info,
                    'washout': washout_info,
                    'strategy_version': 'optimized_v2.0'
                }
                
                return signal_series, signal_details
            
            # 第三阶段：确认拉升检查
            liftoff_ok, liftoff_info = self.check_liftoff_confirmation(df, washout_info)
            
            # 生成最终信号
            signal_series = pd.Series(index=df.index, dtype=object).fillna('')
            
            if liftoff_ok:
                signal_series.iloc[-1] = 'STRONG_BUY'
                signal_state = 'FULL_ABYSS_CONFIRMED'
                stage_passed = 4
            else:
                signal_series.iloc[-1] = 'BUY'
                signal_state = 'WASHOUT_CONFIRMED'
                stage_passed = 3
            
            # 整合所有阶段信息
            signal_details = {
                'signal_state': signal_state,
                'stage_passed': stage_passed,
                'deep_decline': deep_decline_info,
                'hibernation': hibernation_info,
                'washout': washout_info,
                'liftoff': liftoff_info,
                'strategy_version': 'optimized_v2.0'
            }
            
            return signal_series, signal_details
            
        except Exception as e:
            logger.error(f"深渊筑底策略执行失败: {e}")
            return None, None


# 全局策略实例
abyss_strategy = AbyssBottomingStrategy()


def is_valid_stock_code(stock_code, market):
    """检查股票代码是否有效"""
    try:
        # 获取配置中的有效前缀
        valid_prefixes = CONFIG.get('market_filters', {}).get('valid_prefixes', {})
        market_prefixes = valid_prefixes.get(market, [])
        
        if not market_prefixes:
            # 默认前缀
            if market == 'sh':
                market_prefixes = ['600', '601', '603', '605', '688']
            elif market == 'sz':
                market_prefixes = ['000', '001', '002', '003', '300']
            elif market == 'bj':
                market_prefixes = ['430', '831', '832', '833', '834', '835', '836', '837', '838', '839']
        
        stock_code_no_prefix = stock_code.replace(market, '')
        return any(stock_code_no_prefix.startswith(prefix) for prefix in market_prefixes)
        
    except Exception as e:
        logger.error(f"检查股票代码失败 {stock_code}: {e}")
        return False


def worker(args):
    """多进程工作函数"""
    file_path, market = args
    stock_code_full = os.path.basename(file_path).split('.')[0]
    
    # 检查股票代码有效性
    if not is_valid_stock_code(stock_code_full, market):
        return None

    try:
        # 读取股票数据
        df = read_day_file(file_path)
        if df is None or len(df) < abyss_strategy.config['long_term_days']:
            return None

        # 应用策略
        signal_series, details = abyss_strategy.apply_strategy(df)
        
        if signal_series is not None and details is not None:
            # 检查最新一天是否有信号
            latest_signal = signal_series.iloc[-1]
            if latest_signal in ['POTENTIAL_BUY', 'BUY', 'STRONG_BUY']:
                current_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                latest_date = df.index[-1].strftime('%Y-%m-%d')
                
                result = {
                    'stock_code': stock_code_full,
                    'strategy': STRATEGY_TO_RUN,
                    'signal_type': latest_signal,
                    'signal_strength': int(details.get('stage_passed', 1)),
                    'date': latest_date,
                    'scan_timestamp': current_timestamp,
                    'current_price': float(df['close'].iloc[-1]),
                    'signal_details': convert_numpy_types(details)
                }
                
                logger.info(f"发现信号: {stock_code_full} - {latest_signal} (阶段: {details.get('stage_passed', 1)}/4)")
                return result
        
        return None
        
    except Exception as e:
        logger.error(f"处理股票 {stock_code_full} 失败: {e}")
        return None


def convert_numpy_types(obj):
    """递归转换numpy类型为Python原生类型"""
    if isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    else:
        return obj


def generate_summary_report(passed_stocks):
    """生成汇总报告"""
    if not passed_stocks:
        return {
            'scan_summary': {
                'total_signals': 0, 
                'strategy': STRATEGY_TO_RUN,
                'scan_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            },
            'stocks_found': []
        }
    
    # 按信号强度分类
    signal_stats = {}
    for stock in passed_stocks:
        signal_type = stock.get('signal_type', 'UNKNOWN')
        if signal_type not in signal_stats:
            signal_stats[signal_type] = 0
        signal_stats[signal_type] += 1
    
    summary = {
        'scan_summary': {
            'total_signals': len(passed_stocks),
            'scan_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'strategy': STRATEGY_TO_RUN,
            'strategy_version': 'optimized_v2.0',
            'signal_distribution': signal_stats,
            'config_used': abyss_strategy.config
        },
        'stocks_found': passed_stocks
    }
    
    # 转换numpy类型
    summary = convert_numpy_types(summary)
    return summary


def main():
    """主函数"""
    start_time = datetime.now()
    logger.info(f"===== 开始执行深渊筑底策略筛选 =====")
    print(f"🚀 开始执行深渊筑底策略筛选")
    print(f"⏰ 扫描时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📋 策略版本: {CONFIG.get('version', '2.0')} - {CONFIG.get('description', '')}")
    
    # 收集所有股票文件
    all_files = []
    for market in MARKETS:
        path = os.path.join(BASE_PATH, market, 'lday', '*.day')
        files = glob.glob(path)
        if not files:
            logger.warning(f"在路径 {path} 未找到任何文件")
            print(f"⚠️ 警告: 在路径 {path} 未找到任何文件")
        all_files.extend([(f, market) for f in files])
    
    if not all_files:
        logger.error("未能在任何市场目录下找到日线文件，请检查BASE_PATH配置")
        print("❌ 错误: 未能在任何市场目录下找到日线文件，请检查BASE_PATH配置")
        return

    print(f"📊 共找到 {len(all_files)} 个日线文件，开始多进程处理...")
    logger.info(f"开始处理 {len(all_files)} 个股票文件")
    
    # 多进程处理
    try:
        max_workers = CONFIG.get('performance_tuning', {}).get('max_workers', 8)
        with Pool(processes=min(cpu_count(), max_workers)) as pool:
            results = pool.map(worker, all_files)
    except Exception as e:
        logger.error(f"多进程处理失败: {e}")
        print(f"⚠️ 多进程处理失败，降级到单进程: {e}")
        # 降级到单进程处理
        results = list(map(worker, all_files))
    
    # 过滤有效结果
    passed_stocks = [r for r in results if r is not None]
    end_time = datetime.now()
    processing_time = (end_time - start_time).total_seconds()
    
    print(f"📈 筛选完成，发现信号: {len(passed_stocks)} 只股票")
    logger.info(f"筛选完成，发现 {len(passed_stocks)} 个信号")
    
    # 按信号类型统计
    if passed_stocks:
        signal_counts = {}
        for stock in passed_stocks:
            signal_type = stock.get('signal_type', 'UNKNOWN')
            signal_counts[signal_type] = signal_counts.get(signal_type, 0) + 1
        
        print(f"📊 信号分布:")
        for signal_type, count in signal_counts.items():
            print(f"  {signal_type}: {count} 只")
    
    # 保存结果
    output_file = os.path.join(RESULT_DIR, f'abyss_signals_{DATE}.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        # 转换numpy类型后保存
        json_safe_stocks = convert_numpy_types(passed_stocks)
        json.dump(json_safe_stocks, f, ensure_ascii=False, indent=2)
    
    # 生成汇总报告
    summary_report = generate_summary_report(passed_stocks)
    summary_report['scan_summary']['processing_time'] = f"{processing_time:.2f} 秒"
    summary_report['scan_summary']['files_processed'] = len(all_files)
    
    summary_file = os.path.join(RESULT_DIR, f'abyss_summary_{DATE}.json')
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary_report, f, ensure_ascii=False, indent=2)
    
    # 生成可读性报告
    text_report_file = os.path.join(RESULT_DIR, f'abyss_report_{DATE}.txt')
    with open(text_report_file, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("深渊筑底策略筛选报告\n")
        f.write("=" * 80 + "\n")
        f.write(f"扫描时间: {summary_report['scan_summary']['scan_timestamp']}\n")
        f.write(f"策略版本: {summary_report['scan_summary']['strategy_version']}\n")
        f.write(f"处理文件数: {summary_report['scan_summary']['files_processed']}\n")
        f.write(f"处理耗时: {summary_report['scan_summary']['processing_time']}\n")
        f.write(f"发现信号数: {summary_report['scan_summary']['total_signals']}\n\n")
        
        if 'signal_distribution' in summary_report['scan_summary']:
            f.write("信号分布:\n")
            for signal_type, count in summary_report['scan_summary']['signal_distribution'].items():
                f.write(f"  {signal_type}: {count} 只\n")
            f.write("\n")
        
        if passed_stocks:
            f.write("发现信号的股票详情:\n")
            f.write("-" * 80 + "\n")
            for i, stock in enumerate(passed_stocks, 1):
                f.write(f"\n{i:2d}. 股票代码: {stock['stock_code']}\n")
                f.write(f"    信号类型: {stock['signal_type']}\n")
                f.write(f"    信号强度: {stock['signal_strength']}/4 阶段\n")
                f.write(f"    信号日期: {stock['date']}\n")
                f.write(f"    当前价格: {stock['current_price']:.2f}\n")
                
                details = stock.get('signal_details', {})
                if 'deep_decline' in details:
                    deep_info = details['deep_decline']
                    f.write(f"    下跌幅度: {deep_info.get('drop_percent', 0):.2%}\n")
                    f.write(f"    价格位置: {deep_info.get('price_position', 0):.2%}\n")
                    
                    volume_analysis = deep_info.get('volume_analysis', {})
                    if volume_analysis:
                        f.write(f"    成交量萎缩: {volume_analysis.get('shrink_ratio', 0):.2f}\n")
                        f.write(f"    地量持续: {volume_analysis.get('consistency_ratio', 0):.2%}\n")

    print(f"\n📊 筛选完成！")
    print(f"🎯 发现信号: {len(passed_stocks)} 个")
    print(f"⏱️ 处理耗时: {processing_time:.2f} 秒")
    print(f"📄 结果已保存至:")
    print(f"  - 详细信号: {output_file}")
    print(f"  - 汇总报告: {summary_file}")
    print(f"  - 文本报告: {text_report_file}")
    
    logger.info(f"===== 筛选完成！发现 {len(passed_stocks)} 个信号，总耗时: {processing_time:.2f} 秒 =====")


if __name__ == '__main__':
    main()