#!/usr/bin/env python3
"""
增强版强势股筛选系统演示
展示完整的筛选流程和使用方法
"""

import os
import sys
import json
from datetime import datetime

# 添加当前目录到路径
sys.path.append(os.path.dirname(__file__))

from enhanced_momentum_screener import EnhancedMomentumScreener
from backend.momentum_strength_analyzer import MomentumConfig
from backend.multi_timeframe_validator import TimeframeConfig

def demo_basic_screening():
    """基础筛选演示"""
    print("🎯 基础强势股筛选演示")
    print("=" * 50)
    
    # 检查是否有季度回测结果文件
    quarterly_files = [f for f in os.listdir('.') if f.startswith('precise_quarterly_strategy_') and f.endswith('.json')]
    
    if not quarterly_files:
        print("❌ 没有找到季度回测结果文件")
        print("   请先运行季度回测系统生成结果文件")
        return
    
    # 使用最新的季度回测文件
    quarterly_file = sorted(quarterly_files)[-1]
    print(f"📁 使用季度回测文件: {quarterly_file}")
    
    # 创建筛选器
    screener = EnhancedMomentumScreener()
    
    # 加载季度股票池
    quarterly_pool = screener.load_quarterly_results(quarterly_file)
    if not quarterly_pool:
        print("❌ 无法加载季度股票池")
        return
    
    screener.quarterly_pool = quarterly_pool
    
    # 配置参数
    momentum_config = MomentumConfig(
        ma_periods=[13, 20, 34, 55],
        strength_threshold=0.95,  # 95%时间在MA之上
        lookback_days=60
    )
    
    timeframe_config = TimeframeConfig(
        daily_period=60,
        weekly_period=20,
        monthly_period=6
    )
    
    # 执行筛选流程
    print(f"\n🚀 开始筛选流程...")
    
    # 第一步：强势分析
    momentum_results = screener.run_momentum_analysis(quarterly_pool, momentum_config)
    if not momentum_results:
        print("❌ 强势分析失败")
        return
    
    # 筛选出强势股票
    strong_stocks = [r.symbol for r in momentum_results 
                    if r.final_score >= 60 and r.action_signal in ['买入', '观望']]
    
    if not strong_stocks:
        print("❌ 没有股票通过强势分析")
        return
    
    print(f"✅ 通过强势分析: {len(strong_stocks)} 只股票")
    
    # 第二步：多周期验证
    validation_results = screener.run_timeframe_validation(strong_stocks, timeframe_config)
    if not validation_results:
        print("❌ 多周期验证失败")
        return
    
    # 第三步：生成最终推荐
    final_recommendations = screener.generate_final_recommendations(
        min_momentum_score=60,
        min_timeframe_strength=60,
        max_recommendations=15
    )
    
    if final_recommendations:
        print(f"\n🎯 最终推荐结果:")
        print("-" * 60)
        
        for i, rec in enumerate(final_recommendations[:10], 1):
            print(f"{i:2d}. {rec['symbol']} - {rec['recommendation_level']}")
            print(f"    综合得分: {rec['comprehensive_score']:.1f}")
            print(f"    强势得分: {rec['momentum_score']:.1f}")
            print(f"    多周期得分: {rec['timeframe_strength']:.1f}")
            print(f"    操作建议: {rec['entry_timing']}")
            print(f"    风险等级: {rec['risk_level']}")
            print()
        
        # 保存结果
        screener.save_results('demo_results')
        
        print(f"✅ 演示完成！推荐了 {len(final_recommendations)} 只强势股票")
    else:
        print("❌ 没有生成最终推荐")

def demo_advanced_screening():
    """高级筛选演示"""
    print("\n🔥 高级强势股筛选演示")
    print("=" * 50)
    
    # 更严格的筛选条件
    quarterly_files = [f for f in os.listdir('.') if f.startswith('precise_quarterly_strategy_') and f.endswith('.json')]
    
    if not quarterly_files:
        print("❌ 没有找到季度回测结果文件")
        return
    
    quarterly_file = sorted(quarterly_files)[-1]
    screener = EnhancedMomentumScreener()
    
    # 加载股票池
    quarterly_pool = screener.load_quarterly_results(quarterly_file)
    if not quarterly_pool:
        return
    
    screener.quarterly_pool = quarterly_pool
    
    # 高级配置 - 更严格的筛选条件
    momentum_config = MomentumConfig(
        ma_periods=[5, 13, 20, 34, 55],  # 增加MA5
        strength_threshold=0.98,  # 98%时间在MA之上
        touch_tolerance=0.01,     # 1%触及容忍度
        lookback_days=90          # 更长的回测期
    )
    
    timeframe_config = TimeframeConfig(
        daily_period=90,
        weekly_period=30,
        monthly_period=12,
        daily_strength_threshold=0.85,
        weekly_strength_threshold=0.90,
        monthly_strength_threshold=0.95
    )
    
    print(f"📊 高级筛选参数:")
    print(f"   强势阈值: {momentum_config.strength_threshold:.1%}")
    print(f"   触及容忍度: {momentum_config.touch_tolerance:.1%}")
    print(f"   回测天数: {momentum_config.lookback_days}")
    
    # 执行高级筛选
    momentum_results = screener.run_momentum_analysis(quarterly_pool, momentum_config)
    if not momentum_results:
        return
    
    # 更严格的筛选条件
    elite_stocks = [r.symbol for r in momentum_results 
                   if (r.final_score >= 75 and 
                       r.strength_rank == '强势' and
                       r.action_signal == '买入' and
                       r.confidence_level >= 0.7)]
    
    if not elite_stocks:
        print("❌ 没有股票通过高级筛选")
        # 降低标准重试
        elite_stocks = [r.symbol for r in momentum_results 
                       if r.final_score >= 65 and r.action_signal in ['买入', '观望']]
        print(f"🔄 降低标准后通过筛选: {len(elite_stocks)} 只")
    
    if elite_stocks:
        validation_results = screener.run_timeframe_validation(elite_stocks, timeframe_config)
        
        if validation_results:
            final_recommendations = screener.generate_final_recommendations(
                min_momentum_score=70,
                min_timeframe_strength=70,
                max_recommendations=10
            )
            
            if final_recommendations:
                print(f"\n⭐ 精英推荐 (高级筛选):")
                print("-" * 70)
                
                for i, rec in enumerate(final_recommendations, 1):
                    print(f"{i}. {rec['symbol']} - {rec['recommendation_level']}")
                    print(f"   📊 综合评分: {rec['comprehensive_score']:.1f}")
                    print(f"   🚀 强势等级: {rec['strength_rank']}")
                    print(f"   📈 整体趋势: {rec['overall_trend']}")
                    print(f"   🎯 入场时机: {rec['entry_timing']}")
                    print(f"   ⚠️  风险等级: {rec['risk_level']}")
                    print(f"   💰 关键支撑: ¥{rec['key_support']:.2f}")
                    print(f"   🎪 关键阻力: ¥{rec['key_resistance']:.2f}")
                    print()
                
                # 保存高级筛选结果
                screener.save_results('advanced_results')
                
                print(f"✅ 高级筛选完成！精选了 {len(final_recommendations)} 只顶级强势股")

def demo_custom_screening():
    """自定义筛选演示"""
    print("\n🛠️ 自定义筛选演示")
    print("=" * 50)
    
    # 模拟自定义股票池
    custom_stock_pool = [
        'sh600036', 'sh600519', 'sh600276', 'sh600887', 'sh601318',
        'sz000858', 'sz002415', 'sz300059', 'sz300750', 'sz000002'
    ]
    
    print(f"📋 自定义股票池: {len(custom_stock_pool)} 只股票")
    for i, symbol in enumerate(custom_stock_pool, 1):
        print(f"   {i}. {symbol}")
    
    screener = EnhancedMomentumScreener()
    screener.quarterly_pool = custom_stock_pool
    
    # 自定义配置
    momentum_config = MomentumConfig(
        ma_periods=[10, 20, 30],  # 简化MA周期
        strength_threshold=0.85,   # 适中的强势要求
        lookback_days=45          # 较短的回测期
    )
    
    timeframe_config = TimeframeConfig(
        daily_period=45,
        weekly_period=15,
        monthly_period=4
    )
    
    # 执行自定义筛选
    momentum_results = screener.run_momentum_analysis(custom_stock_pool, momentum_config)
    
    if momentum_results:
        # 显示所有分析结果
        print(f"\n📊 自定义筛选结果:")
        print("-" * 80)
        print(f"{'股票':<10} {'综合得分':<8} {'强势等级':<6} {'操作信号':<6} {'风险等级':<6} {'信心度':<6}")
        print("-" * 80)
        
        for result in momentum_results:
            print(f"{result.symbol:<10} {result.final_score:<8.1f} {result.strength_rank:<6} "
                  f"{result.action_signal:<6} {result.risk_level:<6} {result.confidence_level:<6.2f}")
        
        # 选择表现最好的股票进行多周期验证
        top_stocks = [r.symbol for r in momentum_results[:5]]
        
        if top_stocks:
            validation_results = screener.run_timeframe_validation(top_stocks, timeframe_config)
            
            if validation_results:
                final_recommendations = screener.generate_final_recommendations(
                    min_momentum_score=50,  # 降低门槛
                    min_timeframe_strength=50,
                    max_recommendations=5
                )
                
                if final_recommendations:
                    print(f"\n🎯 自定义推荐:")
                    for i, rec in enumerate(final_recommendations, 1):
                        print(f"{i}. {rec['symbol']} - 综合得分: {rec['comprehensive_score']:.1f}")
                
                screener.save_results('custom_results')

def show_usage_examples():
    """显示使用示例"""
    print("\n📖 使用示例")
    print("=" * 50)
    
    print("1. 基础命令行使用:")
    print("   python enhanced_momentum_screener.py --quarterly-result precise_quarterly_strategy_xxx.json")
    print()
    
    print("2. 自定义参数:")
    print("   python enhanced_momentum_screener.py \\")
    print("     --quarterly-result precise_quarterly_strategy_xxx.json \\")
    print("     --min-momentum-score 70 \\")
    print("     --min-timeframe-strength 70 \\")
    print("     --max-recommendations 10")
    print()
    
    print("3. 单独使用强势分析:")
    print("   python backend/momentum_strength_analyzer.py \\")
    print("     --quarterly-result precise_quarterly_strategy_xxx.json \\")
    print("     --min-score 65 \\")
    print("     --save-report")
    print()
    
    print("4. 单独使用多周期验证:")
    print("   python backend/multi_timeframe_validator.py \\")
    print("     --stock-list precise_quarterly_strategy_xxx.json \\")
    print("     --min-strength 65 \\")
    print("     --save-report")
    print()
    
    print("5. 批量处理多个季度结果:")
    print("   for file in precise_quarterly_strategy_*.json; do")
    print("     python enhanced_momentum_screener.py --quarterly-result \"$file\"")
    print("   done")

def main():
    """主演示函数"""
    print("🎯 增强版强势股筛选系统演示")
    print("=" * 60)
    print(f"📅 演示时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 检查必要文件
    if not os.path.exists('backend'):
        print("❌ 找不到backend目录，请确保在正确的工作目录中运行")
        return
    
    try:
        # 1. 基础筛选演示
        demo_basic_screening()
        
        # 2. 高级筛选演示
        demo_advanced_screening()
        
        # 3. 自定义筛选演示
        demo_custom_screening()
        
        # 4. 显示使用示例
        show_usage_examples()
        
        print(f"\n✅ 所有演示完成！")
        print(f"📁 结果文件保存在以下目录:")
        print(f"   • demo_results/")
        print(f"   • advanced_results/")
        print(f"   • custom_results/")
        
    except Exception as e:
        print(f"❌ 演示过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()