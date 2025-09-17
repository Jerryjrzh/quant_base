#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MA13增强筛选器修复验证测试
根据doc/0917_short中的建议进行验证，确保日线可以调试，小时线可以判断并调整验证
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

import json
import logging
from datetime import datetime
from backend.enhanced_ma13_screener import EnhancedMA13Screener

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_enhanced_ma13_screener_fix():
    """测试修复后的MA13增强筛选器"""
    
    print("=" * 80)
    print("MA13增强筛选器修复验证测试")
    print("=" * 80)
    
    # 初始化筛选器
    screener = EnhancedMA13Screener()
    
    # 测试股票列表（包含已知的强势股）
    test_stocks = [
        'sz002021',  # 中捷资源 - 30.5%涨幅
        'sz002796',  # 世嘉科技 - 60%涨幅  
        'sh601388',  # 怡球资源
        'sh688291',  # 科技股
        'sz000001',  # 平安银行
        'sz300015',  # 爱尔眼科
        'sh600036',  # 招商银行
    ]
    
    print(f"测试时间: {datetime.now()}")
    print(f"测试股票: {test_stocks}")
    print(f"筛选器配置:")
    print(f"  - 最低日线分数: {screener.score_thresholds['min_daily_score']}")
    print(f"  - 最低小时线分数: {screener.score_thresholds['min_hourly_score']}")
    print(f"  - 最低总分: {screener.score_thresholds['min_total_score']}")
    print()
    
    # 测试结果收集
    test_results = {
        'test_time': datetime.now().isoformat(),
        'screener_config': {
            'min_daily_score': screener.score_thresholds['min_daily_score'],
            'min_hourly_score': screener.score_thresholds['min_hourly_score'],
            'min_total_score': screener.score_thresholds['min_total_score'],
            'scoring_weights': screener.scoring_weights
        },
        'test_stocks': test_stocks,
        'individual_results': [],
        'batch_screening': {}
    }
    
    # 1. 单股详细分析测试
    print("1. 单股详细分析测试")
    print("-" * 50)
    
    for stock_code in test_stocks:
        try:
            print(f"\n分析股票: {stock_code}")
            
            # 测试动量预过滤器
            momentum_info = screener._momentum_pre_filter(stock_code)
            print(f"  动量预过滤: 通过={momentum_info['pass']}, 涨幅={momentum_info['rise_pct']:.1f}%, 量比={momentum_info['vol_ratio']:.2f}")
            
            if not momentum_info['pass']:
                print(f"  ❌ 未通过动量预过滤，跳过详细分析")
                test_results['individual_results'].append({
                    'stock_code': stock_code,
                    'success': False,
                    'reason': 'momentum_filter_failed',
                    'momentum_info': momentum_info
                })
                continue
            
            # 详细分析
            result = screener.analyze_single_stock(stock_code)
            
            if result:
                print(f"  ✅ 分析成功")
                print(f"    日线阶段: {result.daily_stage}")
                print(f"    日线分数: {result.daily_score:.2f}")
                print(f"    小时线分数: {result.hourly_score:.2f}")
                print(f"    小时线模型: {result.hourly_model}")
                print(f"    市场阶段: {result.market_phase}")
                print(f"    总分: {result.total_score:.2f}")
                print(f"    合格状态: {result.daily_qualified}")
                print(f"    信心度: {result.confidence:.2f}")
                
                # 检查关键修复点
                fixes_validated = []
                
                # 修复1：解耦评分逻辑 - 即使日线分数低也应该有小时线分析
                if result.daily_score < screener.score_thresholds['min_daily_score'] and result.hourly_score > 0:
                    fixes_validated.append("✅ 解耦评分逻辑：日线不合格但仍进行小时线分析")
                elif result.daily_score < screener.score_thresholds['min_daily_score'] and result.hourly_score == 0:
                    fixes_validated.append("❌ 解耦评分逻辑：日线不合格且小时线分析失败")
                
                # 修复2：市场阶段识别
                if result.market_phase and result.market_phase != 'unknown':
                    fixes_validated.append(f"✅ 市场阶段识别：{result.market_phase}")
                else:
                    fixes_validated.append("❌ 市场阶段识别：未识别或为unknown")
                
                # 修复3：总分计算
                if result.total_score > 0:
                    fixes_validated.append(f"✅ 总分计算：{result.total_score:.2f}")
                else:
                    fixes_validated.append("❌ 总分计算：总分为0")
                
                # 修复4：动量奖励整合
                if hasattr(result, 'momentum_info'):
                    fixes_validated.append("✅ 动量信息整合：已整合预过滤器信息")
                else:
                    fixes_validated.append("❌ 动量信息整合：未整合预过滤器信息")
                
                print(f"    修复验证:")
                for fix in fixes_validated:
                    print(f"      {fix}")
                
                test_results['individual_results'].append({
                    'stock_code': stock_code,
                    'success': True,
                    'daily_qualified': result.daily_qualified,
                    'daily_stage': result.daily_stage,
                    'daily_score': result.daily_score,
                    'hourly_score': result.hourly_score,
                    'hourly_model': result.hourly_model,
                    'market_phase': result.market_phase,
                    'total_score': result.total_score,
                    'qualified': result.daily_qualified,
                    'confidence': result.confidence,
                    'momentum_info': momentum_info,
                    'fixes_validated': fixes_validated
                })
            else:
                print(f"  ❌ 分析失败")
                test_results['individual_results'].append({
                    'stock_code': stock_code,
                    'success': False,
                    'reason': 'analysis_failed'
                })
                
        except Exception as e:
            print(f"  ❌ 分析异常: {e}")
            test_results['individual_results'].append({
                'stock_code': stock_code,
                'success': False,
                'reason': f'exception: {str(e)}'
            })
    
    # 2. 批量筛选测试
    print(f"\n\n2. 批量筛选测试")
    print("-" * 50)
    
    try:
        batch_results = screener.screen_stocks(test_stocks)
        
        print(f"批量筛选结果:")
        print(f"  总分析股票数: {len(test_stocks)}")
        print(f"  返回结果数: {len(batch_results)}")
        
        qualified_stocks = [r for r in batch_results if r.total_score >= screener.score_thresholds['min_total_score']]
        print(f"  合格股票数: {len(qualified_stocks)}")
        
        if qualified_stocks:
            print(f"  合格股票列表:")
            for result in qualified_stocks:
                print(f"    {result.stock_code}: 总分={result.total_score:.2f}, 日线={result.daily_score:.2f}, 小时线={result.hourly_score:.2f}")
        else:
            print(f"  ❌ 无合格股票")
            
        # 显示所有结果（包括不合格的）
        print(f"\n  所有分析结果:")
        for result in batch_results:
            status = "✅合格" if result.total_score >= screener.score_thresholds['min_total_score'] else "❌不合格"
            print(f"    {result.stock_code}: {status} 总分={result.total_score:.2f} (日线={result.daily_score:.2f}, 小时线={result.hourly_score:.2f}, 阶段={result.market_phase})")
        
        test_results['batch_screening'] = {
            'total_analyzed': len(test_stocks),
            'results_returned': len(batch_results),
            'qualified_count': len(qualified_stocks),
            'qualified_stocks': [r.stock_code for r in qualified_stocks],
            'all_results': [
                {
                    'stock_code': r.stock_code,
                    'total_score': r.total_score,
                    'daily_score': r.daily_score,
                    'hourly_score': r.hourly_score,
                    'market_phase': r.market_phase,
                    'qualified': r.total_score >= screener.score_thresholds['min_total_score']
                }
                for r in batch_results
            ]
        }
        
    except Exception as e:
        print(f"❌ 批量筛选失败: {e}")
        test_results['batch_screening'] = {
            'error': str(e)
        }
    
    # 3. 修复效果评估
    print(f"\n\n3. 修复效果评估")
    print("-" * 50)
    
    successful_analyses = [r for r in test_results['individual_results'] if r.get('success', False)]
    
    print(f"分析成功率: {len(successful_analyses)}/{len(test_stocks)} ({len(successful_analyses)/len(test_stocks)*100:.1f}%)")
    
    if successful_analyses:
        # 检查关键修复点
        hourly_scores = [r['hourly_score'] for r in successful_analyses]
        non_zero_hourly = [s for s in hourly_scores if s > 0]
        print(f"小时线分析成功率: {len(non_zero_hourly)}/{len(hourly_scores)} ({len(non_zero_hourly)/len(hourly_scores)*100:.1f}%)")
        
        market_phases = [r['market_phase'] for r in successful_analyses if r['market_phase']]
        print(f"市场阶段识别成功率: {len(market_phases)}/{len(successful_analyses)} ({len(market_phases)/len(successful_analyses)*100:.1f}%)")
        
        total_scores = [r['total_score'] for r in successful_analyses]
        non_zero_totals = [s for s in total_scores if s > 0]
        print(f"总分计算成功率: {len(non_zero_totals)}/{len(total_scores)} ({len(non_zero_totals)/len(total_scores)*100:.1f}%)")
        
        qualified_count = len([r for r in successful_analyses if r.get('qualified', False)])
        print(f"合格率: {qualified_count}/{len(successful_analyses)} ({qualified_count/len(successful_analyses)*100:.1f}%)")
        
        # 重点关注sz002796（53.3分）和sz002021的表现
        sz002796_result = next((r for r in successful_analyses if r['stock_code'] == 'sz002796'), None)
        sz002021_result = next((r for r in successful_analyses if r['stock_code'] == 'sz002021'), None)
        
        if sz002796_result:
            print(f"\n重点股票sz002796表现:")
            print(f"  日线分数: {sz002796_result['daily_score']:.2f} (预期>50)")
            print(f"  总分: {sz002796_result['total_score']:.2f} (预期>65)")
            print(f"  合格状态: {sz002796_result['qualified']} (预期True)")
            
        if sz002021_result:
            print(f"\n重点股票sz002021表现:")
            print(f"  日线分数: {sz002021_result['daily_score']:.2f}")
            print(f"  总分: {sz002021_result['total_score']:.2f}")
            print(f"  合格状态: {sz002021_result['qualified']}")
    
    # 保存测试结果
    result_file = f"ma13_enhanced_fix_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(test_results, f, ensure_ascii=False, indent=2)
    
    print(f"\n测试结果已保存到: {result_file}")
    
    # 总结
    print(f"\n\n" + "=" * 80)
    print("修复验证总结")
    print("=" * 80)
    
    if qualified_count > 0:
        print(f"✅ 修复成功！发现 {qualified_count} 只合格股票")
        print("主要改进:")
        print("  - 解耦了日线和小时线评分逻辑")
        print("  - 增强了市场阶段识别")
        print("  - 整合了动量奖励机制")
        print("  - 放宽了积累期判断标准")
    else:
        print("❌ 修复效果有限，仍需进一步调整")
        print("建议:")
        print("  - 检查小时线数据获取问题")
        print("  - 进一步放宽评分标准")
        print("  - 优化动量奖励计算")
    
    return test_results

if __name__ == "__main__":
    test_enhanced_ma13_screener_fix()