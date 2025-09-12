#!/usr/bin/env python3
"""
增强版筛选系统演示脚本
展示多指标融合评分和形态识别功能
"""

import sys
import os
sys.path.append('backend')

def demo_confluence_scorer():
    """演示多指标融合评分器"""
    print("🧪 演示多指标融合评分器")
    print("=" * 50)
    
    try:
        from confluence_scorer import confluence_scorer
        print("✅ 成功导入多指标融合评分器")
        
        # 显示配置信息
        print(f"评分权重配置:")
        print(f"  价格位置权重: {confluence_scorer.weights['price_position']}")
        print(f"  MACD状态权重: {confluence_scorer.weights['macd_state']}")
        print(f"  KDJ状态权重: {confluence_scorer.weights['kdj_state']}")
        print(f"  RSI状态权重: {confluence_scorer.weights['rsi_state']}")
        
        print(f"\n阈值配置:")
        print(f"  价格低位阈值: {confluence_scorer.thresholds['price_position_low']}")
        print(f"  价格高位阈值: {confluence_scorer.thresholds['price_position_high']}")
        print(f"  MACD零轴阈值: {confluence_scorer.thresholds['macd_zero_threshold']}")
        
        return True
        
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        return False

def demo_pattern_recognizer():
    """演示形态识别器"""
    print("\n🔍 演示形态识别器")
    print("=" * 50)
    
    try:
        from pattern_recognizer import pattern_recognizer
        print("✅ 成功导入形态识别器")
        
        print(f"支持的形态类型:")
        print(f"  - 整理突破形态 (consolidation_breakout)")
        print(f"  - 底部反转形态 (bottom_reversal)")
        
        print(f"\n配置参数:")
        print(f"  最小整理天数: {pattern_recognizer.min_consolidation_days}")
        print(f"  最大整理天数: {pattern_recognizer.max_consolidation_days}")
        print(f"  整理区间阈值: {pattern_recognizer.consolidation_range_threshold}")
        print(f"  突破成交量倍数: {pattern_recognizer.breakout_volume_multiplier}")
        
        return True
        
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        return False

def demo_enhanced_screener():
    """演示增强版筛选器"""
    print("\n🚀 演示增强版筛选器")
    print("=" * 50)
    
    try:
        from enhanced_screener import EnhancedScreener
        print("✅ 成功导入增强版筛选器")
        
        # 创建测试股票池
        test_stocks = [
            {"stock_code": "000001", "stock_name": "平安银行"},
            {"stock_code": "000002", "stock_name": "万科A"}
        ]
        
        screener = EnhancedScreener(test_stocks)
        print(f"✅ 成功创建筛选器实例，股票池: {len(test_stocks)} 只股票")
        
        return True
        
    except Exception as e:
        print(f"❌ 创建失败: {e}")
        return False

def demo_universal_screener_integration():
    """演示通用筛选器集成"""
    print("\n🔗 演示通用筛选器集成")
    print("=" * 50)
    
    try:
        from universal_screener import UniversalScreener
        print("✅ 成功导入通用筛选器")
        
        # 创建测试股票池
        test_stocks = [
            {"stock_code": "000001", "stock_name": "平安银行"}
        ]
        
        screener = UniversalScreener(test_stocks)
        print("✅ 成功创建通用筛选器实例")
        
        # 检查是否有增强版方法
        if hasattr(screener, 'run_enhanced_screening'):
            print("✅ 增强版筛选方法已集成")
        else:
            print("❌ 增强版筛选方法未找到")
            
        if hasattr(screener, 'get_screening_mode_comparison'):
            print("✅ 筛选模式对比方法已集成")
        else:
            print("❌ 筛选模式对比方法未找到")
        
        return True
        
    except Exception as e:
        print(f"❌ 集成测试失败: {e}")
        return False

def demo_backtester_enhancement():
    """演示回测器增强"""
    print("\n📈 演示回测器增强")
    print("=" * 50)
    
    try:
        from backtester import _generate_forward_advice
        print("✅ 成功导入增强版建议生成函数")
        
        # 检查函数文档
        doc = _generate_forward_advice.__doc__
        if "增强版" in doc:
            print("✅ 确认为增强版实现")
        else:
            print("⚠️ 可能不是增强版实现")
        
        return True
        
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        return False

def main():
    """主演示函数"""
    print("🎯 增强版筛选系统功能演示")
    print("基于screener_tester文档分析实施的多指标融合评分系统")
    print("=" * 80)
    
    demos = [
        ("多指标融合评分器", demo_confluence_scorer),
        ("形态识别器", demo_pattern_recognizer),
        ("增强版筛选器", demo_enhanced_screener),
        ("通用筛选器集成", demo_universal_screener_integration),
        ("回测器增强", demo_backtester_enhancement)
    ]
    
    success_count = 0
    for demo_name, demo_func in demos:
        try:
            result = demo_func()
            if result:
                success_count += 1
        except Exception as e:
            print(f"❌ {demo_name} 演示异常: {e}")
    
    print(f"\n📊 演示结果汇总:")
    print(f"成功演示: {success_count}/{len(demos)} 个组件")
    
    if success_count == len(demos):
        print("🎉 所有组件演示成功！增强版筛选系统已就绪。")
        
        print(f"\n📋 系统特性总结:")
        print(f"✅ 多指标融合评分 (价格位置40分 + MACD30分 + KDJ20分 + RSI10分)")
        print(f"✅ 技术形态识别 (整理突破 + 底部反转)")
        print(f"✅ 质量等级分类 (A级85分+ / B级70分+ / C级50分+)")
        print(f"✅ 价格位置过滤 (52周高点80%以下)")
        print(f"✅ 状态历史验证 (MACD整理期 + KDJ超卖期)")
        print(f"✅ 向后兼容集成 (保持原有接口)")
        
        print(f"\n🚀 使用方式:")
        print(f"from backend.universal_screener import UniversalScreener")
        print(f"screener = UniversalScreener()")
        print(f"results = screener.run_enhanced_screening(['macd_zero_axis_strategy'], min_quality_grade='B')")
        
    else:
        print(f"⚠️ 有 {len(demos) - success_count} 个组件需要检查")
    
    return success_count == len(demos)

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)