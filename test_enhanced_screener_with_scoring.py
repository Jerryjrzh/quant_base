#!/usr/bin/env python3
"""
【V4.1 增强筛选器测试】
测试集成了汇合评分系统的新筛选器
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from backend.universal_screener import UniversalScreener
from backend.stock_pool_manager import StockPoolManager
import json
from datetime import datetime

def test_enhanced_screener():
    """测试V4.1增强筛选器"""
    print("🚀 开始测试V4.1增强筛选器...")
    
    # 获取小样本股票池进行测试
    pool_manager = StockPoolManager()
    all_stocks = pool_manager.get_all_stocks()
    
    # 选择前20只股票进行测试
    test_stocks = all_stocks[:20] if len(all_stocks) >= 20 else all_stocks
    print(f"📊 测试股票池: {len(test_stocks)} 只股票")
    
    # 创建筛选器实例
    screener = UniversalScreener(stock_pool=test_stocks)
    
    # 运行筛选（使用较少的工作进程避免资源占用）
    strategy_ids = ['macd_zero_axis_strategy']
    results = screener.run_screening(strategy_ids, max_workers=4)
    
    print(f"\n📈 筛选结果统计:")
    print(f"  - 发现信号数量: {len(results)}")
    
    if results:
        print(f"\n🏆 高质量信号详情:")
        for i, result in enumerate(results[:10], 1):  # 显示前10个
            score = getattr(result, 'confluence_score', 0)
            confidence = getattr(result, 'confidence', 0)
            phase = getattr(result, 'market_phase', 'unknown')
            
            print(f"  {i}. {result.stock_code} ({result.stock_name})")
            print(f"     信号类型: {result.signal_type}")
            print(f"     当前价格: ¥{result.current_price:.2f}")
            print(f"     汇合评分: {score:.1f}分")
            print(f"     置信度: {confidence:.1%}")
            print(f"     市场阶段: {phase}")
            print(f"     信号日期: {result.date}")
            print()
    
    # 保存测试结果
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    result_file = f'enhanced_screener_test_results_{timestamp}.json'
    
    # 转换结果为可序列化格式
    serializable_results = []
    for result in results:
        result_dict = {
            'stock_code': result.stock_code,
            'stock_name': result.stock_name,
            'date': str(result.date),
            'signal_type': result.signal_type,
            'current_price': result.current_price,
            'confluence_score': getattr(result, 'confluence_score', 0),
            'confidence': getattr(result, 'confidence', 0),
            'market_phase': getattr(result, 'market_phase', 'unknown')
        }
        serializable_results.append(result_dict)
    
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump({
            'test_time': timestamp,
            'strategy_ids': strategy_ids,
            'test_stocks_count': len(test_stocks),
            'results_count': len(results),
            'results': serializable_results
        }, f, ensure_ascii=False, indent=2)
    
    print(f"📄 测试结果已保存到: {result_file}")
    
    return results

def test_single_stock_deep_analysis():
    """测试单只股票的深度分析"""
    print("\n🔬 测试单只股票深度分析...")
    
    from backend.unified_analysis_service import get_or_run_analysis
    
    # 选择一只测试股票
    test_stock = 'sh600006'  # 东风汽车
    
    print(f"📊 分析股票: {test_stock}")
    
    # 调用统一分析服务
    analysis_result = get_or_run_analysis(test_stock, 'macd_zero_axis_strategy')
    
    if analysis_result.get('success'):
        data = analysis_result['data']
        trading_advice = data['analysis']['trading_advice']
        
        print(f"✅ 分析成功!")
        print(f"  - 股票名称: {data['stock_name']}")
        print(f"  - 当前价格: ¥{data['analysis']['deep_analysis']['current_price']:.2f}")
        print(f"  - 建议操作: {trading_advice['action']}")
        print(f"  - 置信度: {trading_advice['confidence']:.1%}")
        print(f"  - 质量等级: {trading_advice['quality_grade']}")
        
        if 'full_confluence_result' in trading_advice:
            confluence = trading_advice['full_confluence_result']
            print(f"  - 汇合评分: {confluence.get('total_score', 0):.1f}")
            print(f"  - 市场阶段: {confluence.get('market_phase', 'unknown')}")
        
        print(f"  - 分析逻辑:")
        for reason in trading_advice.get('analysis_logic', []):
            print(f"    • {reason}")
    else:
        print(f"❌ 分析失败: {analysis_result.get('error')}")

if __name__ == "__main__":
    try:
        # 测试增强筛选器
        results = test_enhanced_screener()
        
        # 测试单只股票深度分析
        test_single_stock_deep_analysis()
        
        print("\n🎉 所有测试完成!")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()