#!/usr/bin/env python3
"""
KDJ复权功能集成演示
展示如何在现有交易系统中集成复权处理功能
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

import pandas as pd
import numpy as np
from datetime import datetime
import json

# 导入相关模块
import data_loader
import indicators
from adjustment_config_tool import AdjustmentConfigManager

class EnhancedKDJAnalyzer:
    """增强的KDJ分析器，支持复权处理"""
    
    def __init__(self):
        self.config_manager = AdjustmentConfigManager()
        
    def analyze_stock_with_adjustment(self, stock_code: str, days: int = 100):
        """分析股票的KDJ指标，支持复权处理"""
        print(f"📊 分析股票 {stock_code} 的KDJ指标（复权处理）")
        print("=" * 50)
        
        # 加载数据
        df = self._load_stock_data(stock_code, days)
        if df is None:
            return None
        
        # 获取复权配置
        adjustment_config = self.config_manager.get_adjustment_config('kdj', stock_code)
        
        # 创建KDJ配置
        kdj_config = indicators.create_kdj_config(
            n=27, k_period=3, d_period=3,
            adjustment_type=adjustment_config.adjustment_type
        )
        
        print(f"🔧 使用复权方式: {adjustment_config.adjustment_type}")
        
        # 计算KDJ
        k, d, j = indicators.calculate_kdj(df, config=kdj_config, stock_code=stock_code)
        
        # 分析结果
        analysis = self._analyze_kdj_signals(k, d, j, df)
        
        # 显示结果
        self._display_analysis_results(stock_code, analysis, k, d, j)
        
        return {
            'stock_code': stock_code,
            'adjustment_type': adjustment_config.adjustment_type,
            'kdj_values': {'k': k, 'd': d, 'j': j},
            'analysis': analysis,
            'data_range': (df.index[0], df.index[-1]),
            'price_range': (df['close'].min(), df['close'].max())
        }
    
    def _load_stock_data(self, stock_code: str, days: int):
        """加载股票数据"""
        base_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
        market = stock_code[:2]
        file_path = os.path.join(base_path, market, 'lday', f'{stock_code}.day')
        
        if not os.path.exists(file_path):
            print(f"❌ 股票数据文件不存在: {stock_code}")
            return None
        
        try:
            df = data_loader.get_daily_data(file_path)
            if df is None or len(df) < days:
                print(f"❌ 股票数据不足: {stock_code}")
                return None
            
            return df.tail(days).copy()
            
        except Exception as e:
            print(f"❌ 加载数据失败: {e}")
            return None
    
    def _analyze_kdj_signals(self, k: pd.Series, d: pd.Series, j: pd.Series, df: pd.DataFrame):
        """分析KDJ信号"""
        if k.empty or d.empty or j.empty:
            return {'error': 'KDJ数据为空'}
        
        latest_k = k.iloc[-1]
        latest_d = d.iloc[-1]
        latest_j = j.iloc[-1]
        
        # 判断超买超卖
        if latest_k > 80 and latest_d > 80:
            signal = '超买'
            signal_strength = min((latest_k + latest_d) / 2 - 80, 20) / 20
        elif latest_k < 20 and latest_d < 20:
            signal = '超卖'
            signal_strength = min(20 - (latest_k + latest_d) / 2, 20) / 20
        else:
            signal = '正常'
            signal_strength = 0.5
        
        # 判断金叉死叉
        if len(k) >= 2 and len(d) >= 2:
            k_prev = k.iloc[-2]
            d_prev = d.iloc[-2]
            
            if k_prev <= d_prev and latest_k > latest_d:
                cross_signal = '金叉'
            elif k_prev >= d_prev and latest_k < latest_d:
                cross_signal = '死叉'
            else:
                cross_signal = '无交叉'
        else:
            cross_signal = '数据不足'
        
        # 计算KDJ背离
        price_trend = self._calculate_price_trend(df['close'])
        kdj_trend = self._calculate_kdj_trend(k, d)
        
        if price_trend > 0 and kdj_trend < 0:
            divergence = '顶背离'
        elif price_trend < 0 and kdj_trend > 0:
            divergence = '底背离'
        else:
            divergence = '无背离'
        
        return {
            'latest_values': {'k': latest_k, 'd': latest_d, 'j': latest_j},
            'signal': signal,
            'signal_strength': signal_strength,
            'cross_signal': cross_signal,
            'divergence': divergence,
            'trend_analysis': {
                'price_trend': price_trend,
                'kdj_trend': kdj_trend
            }
        }
    
    def _calculate_price_trend(self, prices: pd.Series, period: int = 10):
        """计算价格趋势"""
        if len(prices) < period:
            return 0
        
        recent_prices = prices.tail(period)
        return (recent_prices.iloc[-1] - recent_prices.iloc[0]) / recent_prices.iloc[0]
    
    def _calculate_kdj_trend(self, k: pd.Series, d: pd.Series, period: int = 10):
        """计算KDJ趋势"""
        if len(k) < period or len(d) < period:
            return 0
        
        recent_k = k.tail(period)
        recent_d = d.tail(period)
        
        k_trend = (recent_k.iloc[-1] - recent_k.iloc[0]) / 100
        d_trend = (recent_d.iloc[-1] - recent_d.iloc[0]) / 100
        
        return (k_trend + d_trend) / 2
    
    def _display_analysis_results(self, stock_code: str, analysis: dict, k: pd.Series, d: pd.Series, j: pd.Series):
        """显示分析结果"""
        if 'error' in analysis:
            print(f"❌ 分析失败: {analysis['error']}")
            return
        
        print(f"\n📈 {stock_code} KDJ分析结果:")
        print("-" * 30)
        
        values = analysis['latest_values']
        print(f"最新KDJ值: K={values['k']:.2f}, D={values['d']:.2f}, J={values['j']:.2f}")
        
        # 信号分析
        signal = analysis['signal']
        strength = analysis['signal_strength']
        
        if signal == '超买':
            print(f"🔴 {signal} (强度: {strength:.1%}) - 考虑减仓")
        elif signal == '超卖':
            print(f"🟢 {signal} (强度: {strength:.1%}) - 考虑加仓")
        else:
            print(f"🟡 {signal} - 观望")
        
        # 交叉信号
        cross = analysis['cross_signal']
        if cross == '金叉':
            print(f"📈 {cross} - 买入信号")
        elif cross == '死叉':
            print(f"📉 {cross} - 卖出信号")
        else:
            print(f"➡️ {cross}")
        
        # 背离分析
        divergence = analysis['divergence']
        if divergence != '无背离':
            print(f"⚠️ {divergence} - 趋势可能反转")
        
        # 趋势分析
        trend = analysis['trend_analysis']
        price_trend = trend['price_trend']
        kdj_trend = trend['kdj_trend']
        
        print(f"\n📊 趋势分析:")
        print(f"  价格趋势: {price_trend:+.2%}")
        print(f"  KDJ趋势: {kdj_trend:+.2%}")
        
        # 给出建议
        self._generate_trading_advice(analysis)
    
    def _generate_trading_advice(self, analysis: dict):
        """生成交易建议"""
        print(f"\n💡 交易建议:")
        
        signal = analysis['signal']
        cross = analysis['cross_signal']
        divergence = analysis['divergence']
        
        advice_score = 0
        advice_reasons = []
        
        # 基于超买超卖
        if signal == '超卖':
            advice_score += 2
            advice_reasons.append("KDJ处于超卖区域")
        elif signal == '超买':
            advice_score -= 2
            advice_reasons.append("KDJ处于超买区域")
        
        # 基于交叉信号
        if cross == '金叉':
            advice_score += 3
            advice_reasons.append("KDJ金叉买入信号")
        elif cross == '死叉':
            advice_score -= 3
            advice_reasons.append("KDJ死叉卖出信号")
        
        # 基于背离
        if divergence == '底背离':
            advice_score += 1
            advice_reasons.append("出现底背离，可能反转向上")
        elif divergence == '顶背离':
            advice_score -= 1
            advice_reasons.append("出现顶背离，可能反转向下")
        
        # 生成建议
        if advice_score >= 3:
            advice = "🟢 建议买入"
        elif advice_score <= -3:
            advice = "🔴 建议卖出"
        elif advice_score > 0:
            advice = "🟡 偏向买入"
        elif advice_score < 0:
            advice = "🟡 偏向卖出"
        else:
            advice = "⚪ 观望等待"
        
        print(f"  {advice} (评分: {advice_score:+d})")
        
        if advice_reasons:
            print("  理由:")
            for reason in advice_reasons:
                print(f"    - {reason}")

def compare_adjustment_methods_on_multiple_stocks():
    """对比多只股票的复权方法效果"""
    print("🔄 对比多只股票的复权方法效果")
    print("=" * 50)
    
    # 测试股票列表
    test_stocks = ['sh000001', 'sz000001', 'sh000002']
    analyzer = EnhancedKDJAnalyzer()
    
    results = {}
    
    for stock_code in test_stocks:
        print(f"\n📊 测试股票: {stock_code}")
        print("-" * 30)
        
        stock_results = {}
        
        # 测试不同复权方式
        for adj_type in ['none', 'forward', 'backward']:
            # 临时设置复权方式
            analyzer.config_manager.set_indicator_adjustment_type('kdj', adj_type)
            
            result = analyzer.analyze_stock_with_adjustment(stock_code, days=50)
            
            if result and 'analysis' in result:
                analysis = result['analysis']
                if 'latest_values' in analysis:
                    stock_results[adj_type] = analysis['latest_values']
        
        results[stock_code] = stock_results
        
        # 显示对比
        if stock_results:
            print(f"\n📊 {stock_code} 复权方式对比:")
            print(f"{'复权方式':<10} {'K值':<8} {'D值':<8} {'J值':<8}")
            print("-" * 40)
            
            adj_names = {'none': '不复权', 'forward': '前复权', 'backward': '后复权'}
            for adj_type, values in stock_results.items():
                print(f"{adj_names[adj_type]:<10} {values['k']:<8.2f} {values['d']:<8.2f} {values['j']:<8.2f}")
    
    # 恢复默认设置
    analyzer.config_manager.set_indicator_adjustment_type('kdj', 'forward')
    
    return results

def main():
    """主演示函数"""
    print("🚀 KDJ复权功能集成演示")
    print("=" * 50)
    
    try:
        # 1. 创建增强的KDJ分析器
        analyzer = EnhancedKDJAnalyzer()
        
        # 2. 分析单只股票
        print("📊 单股票分析演示:")
        result = analyzer.analyze_stock_with_adjustment('sh000001', days=100)
        
        # 3. 对比多只股票的复权效果
        print(f"\n" + "="*60)
        compare_results = compare_adjustment_methods_on_multiple_stocks()
        
        # 4. 显示配置管理功能
        print(f"\n" + "="*60)
        print("⚙️ 配置管理演示:")
        print("当前配置:")
        analyzer.config_manager.show_current_config()
        
        print(f"\n💡 使用说明:")
        print("1. 使用 adjustment_config_tool.py 管理复权配置")
        print("2. 不同股票可以设置不同的复权方式")
        print("3. 系统会自动应用配置进行KDJ计算")
        print("4. 复权处理显著改善了技术指标的连续性")
        
        print(f"\n🎯 集成完成！")
        print("✅ KDJ复权功能已成功集成到交易系统")
        print("✅ 支持灵活的配置管理")
        print("✅ 提供完整的分析和建议功能")
        
    except Exception as e:
        print(f"❌ 演示过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()