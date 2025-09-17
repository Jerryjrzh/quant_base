#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试MA13策略优化效果
基于doc/0917_short中的分析建议进行验证
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.enhanced_ma13_screener import EnhancedMA13Screener
import json
from datetime import datetime
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_optimization_on_target_stocks():
    """
    测试优化后的策略在目标股票上的表现
    重点验证：sh601388, sz002021等在分析文档中提到的股票
    """
    screener = EnhancedMA13Screener()
    
    # 测试股票列表（来自分析文档）
    test_stocks = [
        'sh601388',  # 中国中铁 - Grok分析的重点案例
        'sz002021',  # 中捷资源 - 人工分析的强势股案例
        'sz002796',  # 世嘉科技 - 提到的合格股票
        'sh688291',  # 科创板股票 - 提到的合格股票
        'sz000001',  # 平安银行 - 对照组
        'sh600036',  # 招商银行 - 对照组
    ]
    
    print("=" * 80)
    print("MA13策略优化测试 - 基于doc/0917_short分析建议")
    print("=" * 80)
    
    # 测试两阶段架构
    print("\n【第一阶段：历史形态资格审查】")
    qualified_pool = screener.run_historical_qualification(test_stocks)
    
    print(f"历史资格审查结果：")
    for stock_code, qual_score in qualified_pool.items():
        print(f"  {stock_code}: {qual_score:.1f}分")
    
    if not qualified_pool:
        print("  无股票通过历史资格审查，使用传统模式测试...")
        use_two_stage = False
    else:
        use_two_stage = True
    
    # 测试筛选结果
    print(f"\n【第二阶段：实时择时分析】")
    results = screener.screen_stocks(test_stocks, use_two_stage=use_two_stage)
    
    print(f"筛选结果总数：{len(results)}")
    
    # 详细分析每只股票
    analysis_results = []
    
    for i, result in enumerate(results):
        print(f"\n--- 股票 {i+1}: {result.stock_code} ---")
        print(f"日线阶段: {result.daily_stage}")
        print(f"日线得分: {result.daily_score:.1f}")
        print(f"小时线模型: {result.hourly_model}")
        print(f"小时线得分: {result.hourly_score:.1f}")
        print(f"市场阶段: {result.market_phase}")
        print(f"总分: {result.total_score:.1f}")
        print(f"信心度: {result.confidence:.2f}")
        print(f"合格状态: {'✓' if result.daily_qualified else '✗'}")
        
        if result.recommendation:
            rec = result.recommendation
            print(f"操作建议: {rec.get('action', 'N/A')}")
            print(f"建议仓位: {rec.get('position_size', 0):.1%}")
            print(f"风险收益比: {rec.get('risk_reward_ratio', 0):.2f}")
        
        # 保存详细结果 - 确保JSON可序列化
        analysis_results.append({
            'stock_code': str(result.stock_code),
            'daily_stage': str(result.daily_stage),
            'daily_score': float(result.daily_score),
            'hourly_model': str(result.hourly_model),
            'hourly_score': float(result.hourly_score),
            'market_phase': str(result.market_phase),
            'total_score': float(result.total_score),
            'confidence': float(result.confidence),
            'qualified': bool(result.daily_qualified),
            'recommendation': {k: (float(v) if isinstance(v, (int, float)) else str(v)) 
                             for k, v in (result.recommendation or {}).items()},
            'stage1_qual': float(getattr(result, 'stage1_qualification', 0)) if getattr(result, 'stage1_qualification', None) else None
        })
    
    # 验证关键案例
    print(f"\n【关键案例验证】")
    
    # 验证sh601388（Grok重点分析案例）
    sh601388_result = next((r for r in results if r.stock_code == 'sh601388'), None)
    if sh601388_result:
        print(f"sh601388 (中国中铁) 验证:")
        print(f"  预期: 总分应>=60, 推荐buy_continuation")
        print(f"  实际: 总分={sh601388_result.total_score:.1f}, 推荐={sh601388_result.recommendation.get('action', 'N/A')}")
        print(f"  验证结果: {'✓ 通过' if sh601388_result.total_score >= 60 else '✗ 未达预期'}")
    
    # 验证sz002021（人工分析强势股）
    sz002021_result = next((r for r in results if r.stock_code == 'sz002021'), None)
    if sz002021_result:
        print(f"sz002021 (中捷资源) 验证:")
        print(f"  预期: 应通过历史资格审查，总分较高")
        print(f"  实际: 总分={sz002021_result.total_score:.1f}")
        print(f"  验证结果: {'✓ 通过' if sz002021_result.total_score >= 70 else '✗ 未达预期'}")
    
    # 保存测试结果
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    result_file = f'ma13_optimization_test_{timestamp}.json'
    
    test_summary = {
        'test_time': timestamp,
        'optimization_version': 'v2.0_based_on_0917_short_analysis',
        'test_stocks': test_stocks,
        'qualified_pool': qualified_pool,
        'total_results': len(results),
        'qualified_count': sum(1 for r in results if r.daily_qualified),
        'results': analysis_results,
        'key_validations': {
            'sh601388_passed': bool(sh601388_result.total_score >= 60) if sh601388_result else False,
            'sz002021_passed': bool(sz002021_result.total_score >= 70) if sz002021_result else False,
        }
    }
    
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(test_summary, f, ensure_ascii=False, indent=2)
    
    print(f"\n测试结果已保存至: {result_file}")
    
    # 总结
    print(f"\n【优化效果总结】")
    qualified_count = sum(1 for r in results if r.daily_qualified)
    print(f"合格股票数: {qualified_count}/{len(results)}")
    print(f"合格率: {qualified_count/len(results)*100:.1f}%")
    
    if qualified_count > 0:
        avg_score = sum(r.total_score for r in results if r.daily_qualified) / qualified_count
        print(f"合格股票平均分: {avg_score:.1f}")
    
    return test_summary

def test_single_stock_detailed(stock_code: str = 'sh601388'):
    """
    详细测试单只股票的分析过程
    """
    screener = EnhancedMA13Screener()
    
    print(f"\n{'='*60}")
    print(f"详细分析: {stock_code}")
    print(f"{'='*60}")
    
    # 测试历史资格审查
    print("【历史资格审查】")
    pool = screener.run_historical_qualification([stock_code])
    if stock_code in pool:
        print(f"历史资格得分: {pool[stock_code]:.1f}")
    else:
        print("未通过历史资格审查")
    
    # 详细分析
    print("\n【详细分析过程】")
    result = screener.analyze_single_stock(stock_code, stage1_qual=pool.get(stock_code))
    
    if result:
        print(f"预过滤信息: {result.pre_filter}")
        print(f"日线分析: 阶段={result.daily_stage}, 得分={result.daily_score:.1f}")
        print(f"小时线分析: 模型={result.hourly_model}, 得分={result.hourly_score:.1f}")
        print(f"市场阶段: {result.market_phase}")
        print(f"综合得分: {result.total_score:.1f}")
        print(f"操作建议: {result.recommendation}")
    else:
        print("分析失败")

if __name__ == '__main__':
    try:
        # 运行优化测试
        test_summary = test_optimization_on_target_stocks()
        
        # 详细测试关键股票
        test_single_stock_detailed('sh601388')
        
        print("\n" + "="*80)
        print("测试完成！")
        print("="*80)
        
    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback
        traceback.print_exc()