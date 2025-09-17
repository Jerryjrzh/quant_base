#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试MA13增强版改进效果
基于doc/0917_short/ma13_enh_grok.md的改进建议进行验证
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.enhanced_ma13_screener import EnhancedMA13Screener
import json
from datetime import datetime
import logging

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_enhanced_improvements():
    """测试增强版改进效果"""
    
    print("=" * 80)
    print("MA13增强版改进效果测试")
    print("=" * 80)
    
    # 初始化筛选器
    screener = EnhancedMA13Screener()
    
    # 测试股票列表（基于Grok分析中提到的股票）
    test_stocks = [
        'sz002021',  # 30.5%涨幅，超跌反弹模型
        'sz002796',  # 60%涨幅，中继确认模型  
        'sh601388',  # 平盘，中继确认
        'sh688291',  # markup阶段检测
        'sz300015',  # 中继确认
        'sh600036',  # 超跌反弹
    ]
    
    print(f"测试股票: {test_stocks}")
    print()
    
    # 执行筛选
    results = screener.screen_stocks(test_stocks)
    
    print(f"筛选结果数量: {len(results)}")
    print()
    
    # 分析结果
    qualified_count = 0
    buy_recommendations = 0
    
    for i, result in enumerate(results):
        print(f"--- 股票 {i+1}: {result.stock_code} ---")
        print(f"日线阶段: {result.daily_stage}")
        print(f"日线得分: {result.daily_score:.1f}")
        print(f"小时线模型: {result.hourly_model}")
        print(f"小时线得分: {result.hourly_score:.1f}")
        print(f"市场阶段: {result.market_phase}")
        print(f"总分: {result.total_score:.1f}")
        print(f"信心度: {result.confidence:.2f}")
        print(f"是否合格: {result.daily_qualified}")
        
        if hasattr(result, 'pre_filter'):
            print(f"预过滤器: 涨幅{result.pre_filter.get('rise_pct', 0):.1f}%, 量比{result.pre_filter.get('vol_ratio', 1.0):.2f}")
        
        if result.recommendation:
            action = result.recommendation.get('action', 'wait')
            position = result.recommendation.get('position_size', 0)
            print(f"操作建议: {action} (仓位: {position*100:.0f}%)")
            
            if action != 'wait':
                buy_recommendations += 1
        
        if result.daily_qualified:
            qualified_count += 1
            
        print()
    
    # 总结改进效果
    print("=" * 80)
    print("改进效果总结")
    print("=" * 80)
    
    print(f"合格股票数量: {qualified_count}/{len(results)} ({qualified_count/len(results)*100:.1f}%)")
    print(f"买入建议数量: {buy_recommendations}/{len(results)} ({buy_recommendations/len(results)*100:.1f}%)")
    
    # 检查关键改进点
    improvements_check = {
        "总分60分门槛": any(r.total_score >= 60 for r in results),
        "markup阶段识别": any(r.market_phase == 'markup' for r in results),
        "动量奖励应用": any(r.total_score > r.daily_score + r.hourly_score for r in results),
        "买入建议生成": buy_recommendations > 0,
        "信心度提升": any(r.confidence > 0.3 for r in results)
    }
    
    print("\n关键改进点检查:")
    for improvement, achieved in improvements_check.items():
        status = "✓" if achieved else "✗"
        print(f"{status} {improvement}: {'已实现' if achieved else '未实现'}")
    
    # 保存详细结果
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'ma13_enhanced_improvements_test_{timestamp}.json'
    
    results_data = []
    for result in results:
        result_dict = {
            'stock_code': result.stock_code,
            'daily_stage': result.daily_stage,
            'daily_score': result.daily_score,
            'hourly_model': result.hourly_model,
            'hourly_score': result.hourly_score,
            'market_phase': result.market_phase,
            'total_score': result.total_score,
            'confidence': result.confidence,
            'qualified': result.daily_qualified,
            'recommendation': result.recommendation,
            'pre_filter': getattr(result, 'pre_filter', {}),
            'hourly_signals': result.hourly_signals
        }
        results_data.append(result_dict)
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump({
            'test_time': timestamp,
            'improvements_check': improvements_check,
            'summary': {
                'total_stocks': len(results),
                'qualified_count': qualified_count,
                'buy_recommendations': buy_recommendations,
                'qualification_rate': qualified_count/len(results)*100,
                'recommendation_rate': buy_recommendations/len(results)*100
            },
            'results': results_data
        }, f, ensure_ascii=False, indent=2)
    
    print(f"\n详细结果已保存至: {filename}")
    
    return results, improvements_check

if __name__ == "__main__":
    try:
        results, improvements = test_enhanced_improvements()
        
        # 如果所有关键改进都实现了，输出成功信息
        if all(improvements.values()):
            print("\n🎉 所有关键改进点都已成功实现！")
        else:
            print(f"\n⚠️  还有 {sum(1 for v in improvements.values() if not v)} 个改进点需要进一步优化")
            
    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback
        traceback.print_exc()