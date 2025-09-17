"""
MA13强势回调策略系统集成模块
将新的MA13策略集成到现有的universal_screener和策略管理系统中

功能：
1. 提供统一的策略接口
2. 与现有筛选器集成
3. 支持批量筛选
4. 提供API接口

作者：基于Grok和Gemini评估优化
日期：2025-09-17
"""

import sys
import os
import pandas as pd
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# 添加路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

try:
    from backend.strategies.ma13_callback_strategy import MA13CallbackStrategy
    from backend.data_loader import get_multi_timeframe_data
    from backend.universal_screener import UniversalScreener
except ImportError as e:
    print(f"导入模块失败: {e}")
    # 尝试相对导入
    try:
        from .strategies.ma13_callback_strategy import MA13CallbackStrategy
        from .data_loader import get_multi_timeframe_data
        from .universal_screener import UniversalScreener
    except ImportError:
        raise ImportError("无法导入必要的模块，请检查项目结构")

class MA13StrategyIntegration:
    """MA13策略系统集成类"""
    
    def __init__(self, config_path: str = None):
        """
        初始化集成模块
        
        Args:
            config_path: 配置文件路径
        """
        self.config_path = config_path or 'config/unified_strategy_config.json'
        self.config = self._load_config()
        self.strategy = self._initialize_strategy()
        
    def _load_config(self) -> Dict:
        """加载配置"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                full_config = json.load(f)
            
            # 提取MA13策略配置
            ma13_config = full_config.get('strategies', {}).get('MA13强势回调_v1.0', {})
            if ma13_config:
                return ma13_config.get('config', {})
            else:
                # 使用默认配置
                return {
                    'callback_range': [3, 15],
                    'vol_multiplier': 1.1,
                    'kdj_relay_range': [40, 90],
                    'ma13_tolerance': 0.02,
                    'min_rise_pct': 15,
                    'lookback_days': 60,
                    'hourly_lookback_days': 10
                }
        except Exception as e:
            print(f"加载配置失败，使用默认配置: {e}")
            return {
                'callback_range': [3, 15],
                'vol_multiplier': 1.1,
                'kdj_relay_range': [40, 90],
                'ma13_tolerance': 0.02,
                'min_rise_pct': 15,
                'lookback_days': 60,
                'hourly_lookback_days': 10
            }
    
    def _initialize_strategy(self) -> MA13CallbackStrategy:
        """初始化策略实例"""
        return MA13CallbackStrategy(self.config)
    
    def screen_single_stock(self, stock_code: str) -> Dict:
        """
        筛选单只股票
        
        Args:
            stock_code: 股票代码
        
        Returns:
            Dict: 筛选结果
        """
        try:
            # 获取数据
            multi_data = get_multi_timeframe_data(stock_code)
            
            if not multi_data['data_status']['daily_available']:
                return {
                    'stock_code': stock_code,
                    'status': 'no_data',
                    'signal': None,
                    'message': '无日线数据'
                }
            
            daily_df = multi_data['daily_data']
            
            # 应用策略
            result = self.strategy.apply_strategy(stock_code, daily_df)
            
            # 格式化结果
            return {
                'stock_code': stock_code,
                'status': 'success',
                'signal': result['signal'],
                'strength': result['strength'],
                'model': result['model'],
                'timestamp': datetime.now().isoformat(),
                'details': result['details']
            }
            
        except Exception as e:
            return {
                'stock_code': stock_code,
                'status': 'error',
                'signal': None,
                'message': str(e)
            }
    
    def screen_stock_list(self, stock_codes: List[str], max_workers: int = 4) -> List[Dict]:
        """
        批量筛选股票列表
        
        Args:
            stock_codes: 股票代码列表
            max_workers: 最大并发数
        
        Returns:
            List[Dict]: 筛选结果列表
        """
        results = []
        
        print(f"开始筛选 {len(stock_codes)} 只股票...")
        
        for i, stock_code in enumerate(stock_codes):
            print(f"筛选进度: {i+1}/{len(stock_codes)} - {stock_code}")
            
            result = self.screen_single_stock(stock_code)
            results.append(result)
            
            # 如果有信号，立即输出
            if result['signal']:
                print(f"  ✓ 发现信号: {result['signal']} (强度: {result['strength']})")
        
        return results
    
    def get_signal_stocks(self, results: List[Dict]) -> Dict:
        """
        从筛选结果中提取有信号的股票
        
        Args:
            results: 筛选结果列表
        
        Returns:
            Dict: 按信号类型分组的股票
        """
        signal_stocks = {
            'buy_super_fall': [],
            'buy_relay': [],
            'no_signal': [],
            'errors': []
        }
        
        for result in results:
            if result['status'] == 'error':
                signal_stocks['errors'].append(result)
            elif result['signal'] == 'buy_super_fall':
                signal_stocks['buy_super_fall'].append(result)
            elif result['signal'] == 'buy_relay':
                signal_stocks['buy_relay'].append(result)
            else:
                signal_stocks['no_signal'].append(result)
        
        return signal_stocks
    
    def generate_screening_report(self, results: List[Dict], save_path: str = None) -> Dict:
        """
        生成筛选报告
        
        Args:
            results: 筛选结果
            save_path: 保存路径
        
        Returns:
            Dict: 报告内容
        """
        signal_stocks = self.get_signal_stocks(results)
        
        report = {
            'screening_time': datetime.now().isoformat(),
            'strategy': 'MA13强势回调趋势系统',
            'total_stocks': len(results),
            'summary': {
                'super_fall_signals': len(signal_stocks['buy_super_fall']),
                'relay_signals': len(signal_stocks['buy_relay']),
                'no_signals': len(signal_stocks['no_signal']),
                'errors': len(signal_stocks['errors'])
            },
            'signal_stocks': {
                'super_fall': [
                    {
                        'stock_code': r['stock_code'],
                        'strength': r['strength'],
                        'details': r.get('details', {})
                    } for r in signal_stocks['buy_super_fall']
                ],
                'relay': [
                    {
                        'stock_code': r['stock_code'],
                        'strength': r['strength'],
                        'details': r.get('details', {})
                    } for r in signal_stocks['buy_relay']
                ]
            },
            'config': self.config
        }
        
        # 保存报告
        if save_path is None:
            save_path = f'ma13_screening_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
        
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print(f"筛选报告已保存到: {save_path}")
        return report
    
    def integrate_with_universal_screener(self, stock_pool: List[str] = None) -> Dict:
        """
        与通用筛选器集成
        
        Args:
            stock_pool: 股票池，如果为None则使用默认股票池
        
        Returns:
            Dict: 集成筛选结果
        """
        try:
            # 如果没有指定股票池，使用一个小的测试池
            if stock_pool is None:
                stock_pool = [
                    '002021', '600618', '300739', '000858', '002796',
                    '600036', '000002', '300015', '002415', '600519'
                ]
            
            print(f"使用MA13策略筛选股票池: {len(stock_pool)} 只股票")
            
            # 批量筛选
            results = self.screen_stock_list(stock_pool)
            
            # 生成报告
            report = self.generate_screening_report(results)
            
            # 输出摘要
            summary = report['summary']
            print(f"\n筛选完成！")
            print(f"总股票数: {report['total_stocks']}")
            print(f"超跌反弹信号: {summary['super_fall_signals']}")
            print(f"中继确认信号: {summary['relay_signals']}")
            print(f"无信号: {summary['no_signals']}")
            print(f"错误: {summary['errors']}")
            
            return report
            
        except Exception as e:
            print(f"集成筛选时出错: {e}")
            return {'error': str(e)}

def create_api_interface():
    """创建API接口函数"""
    
    def ma13_screen_api(stock_codes: List[str] = None, config: Dict = None) -> Dict:
        """
        MA13策略API接口
        
        Args:
            stock_codes: 股票代码列表
            config: 策略配置
        
        Returns:
            Dict: API响应
        """
        try:
            # 初始化集成模块
            integration = MA13StrategyIntegration()
            
            # 如果提供了配置，更新策略配置
            if config:
                integration.strategy.config.update(config)
            
            # 执行筛选
            if stock_codes:
                results = integration.screen_stock_list(stock_codes)
            else:
                # 使用默认股票池
                results = integration.integrate_with_universal_screener()
                return results
            
            # 生成报告
            report = integration.generate_screening_report(results)
            
            return {
                'status': 'success',
                'data': report
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': str(e)
            }
    
    return ma13_screen_api

# 测试函数
def test_integration():
    """测试集成功能"""
    print("测试MA13策略系统集成")
    print("=" * 40)
    
    # 初始化集成模块
    integration = MA13StrategyIntegration()
    
    # 测试单股筛选
    print("\n1. 测试单股筛选")
    result = integration.screen_single_stock('002021')
    print(f"002021 筛选结果: {result['signal']} (强度: {result.get('strength', 0)})")
    
    # 测试批量筛选
    print("\n2. 测试批量筛选")
    test_stocks = ['002021', '600618', '300739']
    results = integration.screen_stock_list(test_stocks)
    
    for result in results:
        if result['signal']:
            print(f"{result['stock_code']}: {result['signal']} (强度: {result['strength']})")
    
    # 测试与通用筛选器集成
    print("\n3. 测试系统集成")
    integration.integrate_with_universal_screener()

if __name__ == "__main__":
    test_integration()