#!/usr/bin/env python3
"""
复权配置管理工具
用于配置和测试KDJ等技术指标的复权处理
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

import json
import pandas as pd
from datetime import datetime
from typing import Dict, Any

# 导入相关模块
import data_loader
import indicators
from adjustment_processor import (
    AdjustmentConfig, AdjustmentProcessor, 
    create_adjustment_config, apply_forward_adjustment, 
    apply_backward_adjustment, apply_no_adjustment
)

class AdjustmentConfigManager:
    """复权配置管理器"""
    
    def __init__(self):
        self.config_file = 'adjustment_config.json'
        self.load_config()
    
    def load_config(self):
        """加载配置文件"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
            else:
                self.config = self.get_default_config()
                self.save_config()
        except Exception as e:
            print(f"⚠️ 加载配置失败，使用默认配置: {e}")
            self.config = self.get_default_config()
    
    def save_config(self):
        """保存配置文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"❌ 保存配置失败: {e}")
    
    def get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "global_settings": {
                "default_adjustment_type": "forward",  # forward, backward, none
                "cache_enabled": True,
                "include_dividends": True,
                "include_splits": True
            },
            "indicator_settings": {
                "kdj": {
                    "adjustment_type": "forward",
                    "n_period": 27,
                    "k_period": 3,
                    "d_period": 3,
                    "smoothing_method": "ema"
                },
                "macd": {
                    "adjustment_type": "forward",
                    "fast_period": 12,
                    "slow_period": 26,
                    "signal_period": 9,
                    "price_type": "close"
                },
                "rsi": {
                    "adjustment_type": "forward",
                    "period": 14,
                    "price_type": "close",
                    "smoothing_method": "wilder"
                }
            },
            "stock_specific": {
                # 可以为特定股票设置不同的复权方式
                # "sh000001": {"adjustment_type": "backward"}
            }
        }
    
    def get_adjustment_config(self, indicator: str = None, stock_code: str = None) -> AdjustmentConfig:
        """获取复权配置"""
        # 优先级：股票特定配置 > 指标配置 > 全局配置
        
        adjustment_type = self.config["global_settings"]["default_adjustment_type"]
        
        # 检查指标特定配置
        if indicator and indicator in self.config["indicator_settings"]:
            indicator_config = self.config["indicator_settings"][indicator]
            adjustment_type = indicator_config.get("adjustment_type", adjustment_type)
        
        # 检查股票特定配置
        if stock_code and stock_code in self.config["stock_specific"]:
            stock_config = self.config["stock_specific"][stock_code]
            adjustment_type = stock_config.get("adjustment_type", adjustment_type)
        
        return create_adjustment_config(
            adjustment_type=adjustment_type,
            include_dividends=self.config["global_settings"]["include_dividends"],
            include_splits=self.config["global_settings"]["include_splits"],
            cache_enabled=self.config["global_settings"]["cache_enabled"]
        )
    
    def set_global_adjustment_type(self, adjustment_type: str):
        """设置全局复权类型"""
        if adjustment_type not in ['forward', 'backward', 'none']:
            raise ValueError("复权类型必须是 'forward', 'backward' 或 'none'")
        
        self.config["global_settings"]["default_adjustment_type"] = adjustment_type
        self.save_config()
        print(f"✅ 全局复权类型已设置为: {adjustment_type}")
    
    def set_indicator_adjustment_type(self, indicator: str, adjustment_type: str):
        """设置指标特定的复权类型"""
        if adjustment_type not in ['forward', 'backward', 'none']:
            raise ValueError("复权类型必须是 'forward', 'backward' 或 'none'")
        
        if indicator not in self.config["indicator_settings"]:
            raise ValueError(f"不支持的指标: {indicator}")
        
        self.config["indicator_settings"][indicator]["adjustment_type"] = adjustment_type
        self.save_config()
        print(f"✅ {indicator.upper()}指标复权类型已设置为: {adjustment_type}")
    
    def set_stock_adjustment_type(self, stock_code: str, adjustment_type: str):
        """设置股票特定的复权类型"""
        if adjustment_type not in ['forward', 'backward', 'none']:
            raise ValueError("复权类型必须是 'forward', 'backward' 或 'none'")
        
        if "stock_specific" not in self.config:
            self.config["stock_specific"] = {}
        
        self.config["stock_specific"][stock_code] = {"adjustment_type": adjustment_type}
        self.save_config()
        print(f"✅ 股票{stock_code}复权类型已设置为: {adjustment_type}")
    
    def show_current_config(self):
        """显示当前配置"""
        print("📋 当前复权配置")
        print("=" * 50)
        
        print("🌍 全局设置:")
        global_settings = self.config["global_settings"]
        print(f"  默认复权类型: {global_settings['default_adjustment_type']}")
        print(f"  包含分红调整: {global_settings['include_dividends']}")
        print(f"  包含拆股调整: {global_settings['include_splits']}")
        print(f"  启用缓存: {global_settings['cache_enabled']}")
        
        print("\n📊 指标设置:")
        for indicator, settings in self.config["indicator_settings"].items():
            print(f"  {indicator.upper()}: {settings['adjustment_type']}")
        
        if self.config["stock_specific"]:
            print("\n🏢 股票特定设置:")
            for stock_code, settings in self.config["stock_specific"].items():
                print(f"  {stock_code}: {settings['adjustment_type']}")

def test_adjustment_on_stock(stock_code: str, show_comparison: bool = True):
    """测试复权对指标计算的影响"""
    print(f"🧪 测试复权对股票 {stock_code} 指标计算的影响")
    print("=" * 60)
    
    # 加载数据
    base_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
    market = stock_code[:2]
    file_path = os.path.join(base_path, market, 'lday', f'{stock_code}.day')
    
    if not os.path.exists(file_path):
        print(f"❌ 股票数据文件不存在: {stock_code}")
        return
    
    try:
        # 加载原始数据
        df = data_loader.get_daily_data(file_path)
        if df is None or len(df) < 100:
            print(f"❌ 股票数据不足: {stock_code}")
            return
        
        # 取最近100个交易日进行测试
        df = df.tail(100).copy()
        
        print(f"📊 数据范围: {df.index[0].strftime('%Y-%m-%d')} 到 {df.index[-1].strftime('%Y-%m-%d')}")
        print(f"📈 价格范围: {df['close'].min():.2f} - {df['close'].max():.2f}")
        
        # 测试不同复权方式对KDJ的影响
        results = {}
        
        for adj_type in ['none', 'forward', 'backward']:
            print(f"\n🔄 测试{adj_type}复权...")
            
            # 创建KDJ配置
            kdj_config = indicators.create_kdj_config(adjustment_type=adj_type)
            
            # 计算KDJ
            k, d, j = indicators.calculate_kdj(df, config=kdj_config, stock_code=stock_code)
            
            # 获取最近的值
            latest_k = k.iloc[-1] if not k.empty else 0
            latest_d = d.iloc[-1] if not d.empty else 0
            latest_j = j.iloc[-1] if not j.empty else 0
            
            results[adj_type] = {
                'k': latest_k,
                'd': latest_d,
                'j': latest_j,
                'k_series': k,
                'd_series': d,
                'j_series': j
            }
            
            print(f"  最新KDJ值: K={latest_k:.2f}, D={latest_d:.2f}, J={latest_j:.2f}")
        
        # 显示对比结果
        if show_comparison:
            print(f"\n📊 复权方式对比 (最新值):")
            print("-" * 50)
            print(f"{'复权方式':<10} {'K值':<8} {'D值':<8} {'J值':<8}")
            print("-" * 50)
            
            for adj_type, result in results.items():
                adj_name = {'none': '不复权', 'forward': '前复权', 'backward': '后复权'}[adj_type]
                print(f"{adj_name:<10} {result['k']:<8.2f} {result['d']:<8.2f} {result['j']:<8.2f}")
            
            # 计算差异
            print(f"\n📈 复权影响分析:")
            none_result = results['none']
            forward_result = results['forward']
            backward_result = results['backward']
            
            k_diff_forward = abs(forward_result['k'] - none_result['k'])
            k_diff_backward = abs(backward_result['k'] - none_result['k'])
            
            print(f"  前复权与不复权K值差异: {k_diff_forward:.2f}")
            print(f"  后复权与不复权K值差异: {k_diff_backward:.2f}")
            
            if k_diff_forward > 5 or k_diff_backward > 5:
                print("  ⚠️ 复权对KDJ计算有显著影响，建议选择合适的复权方式")
            else:
                print("  ✅ 复权对KDJ计算影响较小")
        
        return results
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return None

def compare_adjustment_methods():
    """对比不同复权方法的特点"""
    print("📚 复权方法对比说明")
    print("=" * 50)
    
    print("🔸 不复权 (none):")
    print("  - 使用原始价格数据")
    print("  - 保持历史价格的真实性")
    print("  - 除权除息日会出现价格跳跃")
    print("  - 适合短期分析和当前价格判断")
    
    print("\n🔸 前复权 (forward):")
    print("  - 以当前价格为基准，调整历史价格")
    print("  - 保持当前价格不变")
    print("  - 历史价格连续，无跳跃")
    print("  - 适合长期趋势分析和技术指标计算")
    print("  - 推荐用于KDJ、MACD等技术指标")
    
    print("\n🔸 后复权 (backward):")
    print("  - 以历史价格为基准，调整当前价格")
    print("  - 保持历史价格不变")
    print("  - 当前价格可能与市场价格不符")
    print("  - 适合历史回测和长期收益计算")
    
    print("\n💡 建议:")
    print("  - KDJ指标计算：推荐使用前复权")
    print("  - 短期交易：可使用不复权")
    print("  - 长期投资分析：推荐使用前复权")
    print("  - 历史回测：根据需要选择前复权或后复权")

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("复权配置管理工具")
        print("=" * 30)
        print("使用方法:")
        print("  python adjustment_config_tool.py show                    # 显示当前配置")
        print("  python adjustment_config_tool.py set-global <type>      # 设置全局复权类型")
        print("  python adjustment_config_tool.py set-kdj <type>         # 设置KDJ复权类型")
        print("  python adjustment_config_tool.py set-stock <code> <type> # 设置股票复权类型")
        print("  python adjustment_config_tool.py test <stock_code>      # 测试复权影响")
        print("  python adjustment_config_tool.py compare               # 对比复权方法")
        print("")
        print("复权类型: forward(前复权), backward(后复权), none(不复权)")
        print("")
        print("示例:")
        print("  python adjustment_config_tool.py show")
        print("  python adjustment_config_tool.py set-global forward")
        print("  python adjustment_config_tool.py set-kdj forward")
        print("  python adjustment_config_tool.py set-stock sh000001 backward")
        print("  python adjustment_config_tool.py test sh000001")
        print("  python adjustment_config_tool.py compare")
        return
    
    command = sys.argv[1].lower()
    config_manager = AdjustmentConfigManager()
    
    try:
        if command == 'show':
            config_manager.show_current_config()
            
        elif command == 'set-global':
            if len(sys.argv) < 3:
                print("❌ 请提供复权类型")
                return
            adjustment_type = sys.argv[2].lower()
            config_manager.set_global_adjustment_type(adjustment_type)
            
        elif command == 'set-kdj':
            if len(sys.argv) < 3:
                print("❌ 请提供复权类型")
                return
            adjustment_type = sys.argv[2].lower()
            config_manager.set_indicator_adjustment_type('kdj', adjustment_type)
            
        elif command == 'set-macd':
            if len(sys.argv) < 3:
                print("❌ 请提供复权类型")
                return
            adjustment_type = sys.argv[2].lower()
            config_manager.set_indicator_adjustment_type('macd', adjustment_type)
            
        elif command == 'set-rsi':
            if len(sys.argv) < 3:
                print("❌ 请提供复权类型")
                return
            adjustment_type = sys.argv[2].lower()
            config_manager.set_indicator_adjustment_type('rsi', adjustment_type)
            
        elif command == 'set-stock':
            if len(sys.argv) < 4:
                print("❌ 请提供股票代码和复权类型")
                return
            stock_code = sys.argv[2].lower()
            adjustment_type = sys.argv[3].lower()
            config_manager.set_stock_adjustment_type(stock_code, adjustment_type)
            
        elif command == 'test':
            if len(sys.argv) < 3:
                print("❌ 请提供股票代码")
                return
            stock_code = sys.argv[2].lower()
            test_adjustment_on_stock(stock_code)
            
        elif command == 'compare':
            compare_adjustment_methods()
            
        else:
            print(f"❌ 未知命令: {command}")
            
    except Exception as e:
        print(f"❌ 执行失败: {e}")

if __name__ == "__main__":
    main()