#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试修复后的MA13增强筛选器
验证Grok和Gemini评估建议的修改效果

测试重点：
1. 验证日线阈值放宽后的筛选效果
2. 验证小时线数据列名修复
3. 验证后备方案和动量预过滤器
4. 验证市场阶段整合和评分优化

作者：基于Grok和Gemini评估优化
日期：2025-09-17
"""

import sys
import os
import json
from datetime import datetime

# 添加项目路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

try:
    # 添加backend路径到sys.path
    backend_path = os.path.join(current_dir, 'backend')
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)
    
    from enhanced_ma13_screener import EnhancedMA13Screener
    from data_handler import get_full_data_with_indicators
except ImportError as e:
    print(f"导入模块失败: {e}")
    print("请确保在项目根目录下运行此脚本")
    sys.exit(1)

def test_enhanced_ma13_screener():
    """测试增强版MA13筛选器"""
    print("=" * 60)
    print("MA13增强筛选器修复测试")
    print("=" * 60)
    
    # 初始化筛选器
    screener = EnhancedMA13Screener()
    
    # 测试股票列表 - 包含Grok评估中的股票
    test_stocks = [
        'sz002021',  # 中捷资源 - 应该是强势股
        'sz002796',  # 世嘉科技 - 科技股
        'sh601388',  # 中国石油 - 传统股
        'sh688291',  # 科创板股票
        'sz000001',  # 平安银行
        'sz300015',  # 东方雨虹
        'sh600036',  # 招商银行
    ]
    
    print(f"测试股票数量: {len(test_stocks)}")
    print(f"测试股票列表: {test_stocks}")
    print()
    
    # 记录测试结果
    test_results = {
        'test_time': datetime.now().isoformat(),
        'screener_config': {
            'min_daily_score': screener.score_thresholds['min_daily_score'],
            'min_total_score': screener.score_thresholds['min_total_score'],
            'scoring_weights': screener.scoring_weights
        },
        'test_stocks': test_stocks,
        'results': []
    }
    
    # 单股测试
    print("=== 单股详细测试 ===")
    for stock_code in test_stocks:
        print(f"\n--- 测试股票: {stock_code} ---")
        
        try:
            # 测试单股分析
            result = screener.analyze_single_stock(stock_code)
            
            if result:
                print(f"✓ 分析成功")
                print(f"  日线合格: {result.daily_qualified}")
                print(f"  日线阶段: {result.daily_stage}")
                print(f"  日线得分: {result.daily_score:.1f}")
                print(f"  小时线得分: {result.hourly_score:.1f}")
                print(f"  小时线模型: {result.hourly_model}")
                print(f"  市场阶段: {result.market_phase}")
                print(f"  综合得分: {result.total_score:.1f}")
                print(f"  信心度: {result.confidence:.2f}")
                
                # 检查是否符合筛选标准
                qualified = result.total_score >= screener.score_thresholds['min_total_score']
                print(f"  筛选结果: {'✓ 合格' if qualified else '✗ 不合格'}")
                
                if result.recommendation:
                    print(f"  操作建议: {result.recommendation.get('action', 'N/A')}")
                    print(f"  仓位建议: {result.recommendation.get('position_size', 0):.1%}")
                
                # 记录结果
                test_results['results'].append({
                    'stock_code': stock_code,
                    'success': True,
                    'daily_qualified': result.daily_qualified,
                    'daily_score': result.daily_score,
                    'hourly_score': result.hourly_score,
                    'total_score': result.total_score,
                    'qualified': qualified,
                    'confidence': result.confidence,
                    'market_phase': result.market_phase,
                    'recommendation': result.recommendation
                })
                
            else:
                print(f"✗ 分析失败 - 返回None")
                test_results['results'].append({
                    'stock_code': stock_code,
                    'success': False,
                    'error': 'Analysis returned None'
                })
                
        except Exception as e:
            print(f"✗ 分析异常: {e}")
            test_results['results'].append({
                'stock_code': stock_code,
                'success': False,
                'error': str(e)
            })
    
    # 批量筛选测试
    print(f"\n=== 批量筛选测试 ===")
    try:
        qualified_stocks = screener.screen_stocks(test_stocks)
        
        print(f"筛选结果: {len(qualified_stocks)} 只股票符合条件")
        
        if qualified_stocks:
            print("\n符合条件的股票:")
            for i, result in enumerate(qualified_stocks, 1):
                print(f"{i}. {result.stock_code}")
                print(f"   综合得分: {result.total_score:.1f}")
                print(f"   模型: {result.hourly_model}")
                print(f"   操作: {result.recommendation.get('action', 'N/A')}")
        else:
            print("⚠️  没有股票符合筛选条件")
        
        test_results['batch_screening'] = {
            'qualified_count': len(qualified_stocks),
            'qualified_stocks': [r.stock_code for r in qualified_stocks]
        }
        
    except Exception as e:
        print(f"✗ 批量筛选失败: {e}")
        test_results['batch_screening'] = {'error': str(e)}
    
    # 统计分析
    print(f"\n=== 测试统计 ===")
    successful_tests = sum(1 for r in test_results['results'] if r['success'])
    qualified_tests = sum(1 for r in test_results['results'] if r.get('qualified', False))
    
    print(f"成功分析: {successful_tests}/{len(test_stocks)} ({successful_tests/len(test_stocks)*100:.1f}%)")
    print(f"符合条件: {qualified_tests}/{len(test_stocks)} ({qualified_tests/len(test_stocks)*100:.1f}%)")
    
    if successful_tests > 0:
        avg_daily_score = sum(r.get('daily_score', 0) for r in test_results['results'] if r['success']) / successful_tests
        avg_total_score = sum(r.get('total_score', 0) for r in test_results['results'] if r['success']) / successful_tests
        print(f"平均日线得分: {avg_daily_score:.1f}")
        print(f"平均综合得分: {avg_total_score:.1f}")
    
    # 保存测试结果
    result_file = f"ma13_strategy_enhanced_fix_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(test_results, f, ensure_ascii=False, indent=2)
    
    print(f"\n测试结果已保存至: {result_file}")
    
    # 修复效果评估
    print(f"\n=== 修复效果评估 ===")
    
    # 检查是否有股票通过了日线筛选（之前全部失败）
    daily_passed = sum(1 for r in test_results['results'] if r.get('daily_qualified', False))
    if daily_passed > 0:
        print(f"✓ 日线阈值放宽生效: {daily_passed} 只股票通过日线筛选")
    else:
        print("⚠️  日线筛选仍然过严，可能需要进一步调整")
    
    # 检查小时线评分是否不再为0
    hourly_scores = [r.get('hourly_score', 0) for r in test_results['results'] if r['success']]
    non_zero_hourly = sum(1 for score in hourly_scores if score > 0)
    if non_zero_hourly > 0:
        print(f"✓ 小时线数据修复生效: {non_zero_hourly} 只股票获得小时线评分")
    else:
        print("⚠️  小时线评分仍为0，数据问题可能未完全解决")
    
    # 检查是否有股票最终符合筛选条件
    if qualified_tests > 0:
        print(f"✓ 整体修复成功: {qualified_tests} 只股票符合筛选条件")
        print("🎉 MA13筛选器修复验证通过！")
    else:
        print("⚠️  仍无股票符合条件，可能需要进一步优化参数")
    
    return test_results

def test_specific_strong_stocks():
    """专门测试已知的强势股票"""
    print(f"\n=== 强势股专项测试 ===")
    
    # 根据Grok评估，这些应该是强势股
    strong_stocks = ['sz002021', 'sz002796']  # 中捷资源、世嘉科技
    
    screener = EnhancedMA13Screener()
    
    for stock_code in strong_stocks:
        print(f"\n--- 强势股测试: {stock_code} ---")
        
        try:
            # 获取原始数据进行验证
            daily_df = get_full_data_with_indicators(stock_code)
            if daily_df is not None and len(daily_df) > 0:
                recent_data = daily_df.tail(20)
                current_price = recent_data['close'].iloc[-1]
                low_20d = recent_data['low'].min()
                rise_pct = (current_price - low_20d) / low_20d * 100
                
                print(f"  当前价格: {current_price:.2f}")
                print(f"  20日涨幅: {rise_pct:.1f}%")
                
                # 动量预过滤测试
                momentum_pass = screener._momentum_pre_filter(stock_code)
                print(f"  动量预过滤: {'✓ 通过' if momentum_pass else '✗ 未通过'}")
            
            # 完整分析
            result = screener.analyze_single_stock(stock_code)
            if result:
                print(f"  综合得分: {result.total_score:.1f}")
                print(f"  是否合格: {'✓ 是' if result.total_score >= 65 else '✗ 否'}")
            
        except Exception as e:
            print(f"  测试失败: {e}")

if __name__ == "__main__":
    # 运行测试
    test_results = test_enhanced_ma13_screener()
    
    # 运行强势股专项测试
    test_specific_strong_stocks()
    
    print(f"\n{'='*60}")
    print("测试完成！")
    print("请查看测试结果，验证修复效果。")
    print(f"{'='*60}")