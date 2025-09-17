#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试增强MA13 API
验证优化后的策略是否正常工作
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import requests
import json
from datetime import datetime
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_enhanced_api_direct():
    """
    直接测试增强API模块（不通过Flask）
    """
    print("=" * 60)
    print("直接测试增强MA13筛选器")
    print("=" * 60)
    
    try:
        from backend.enhanced_ma13_screener import enhanced_ma13_screener
        
        # 测试股票列表
        test_stocks = ['sh601388', 'sz002021', 'sz000001']
        
        print(f"测试股票: {test_stocks}")
        
        # 单阶段测试
        print("\n【单阶段模式测试】")
        for stock_code in test_stocks:
            try:
                result = enhanced_ma13_screener.analyze_single_stock(stock_code)
                if result:
                    print(f"{stock_code}: 总分={result.total_score:.1f}, 合格={result.daily_qualified}, 模型={result.hourly_model}")
                else:
                    print(f"{stock_code}: 分析失败")
            except Exception as e:
                print(f"{stock_code}: 错误 - {e}")
        
        # 两阶段测试
        print("\n【两阶段模式测试】")
        qualified_pool = enhanced_ma13_screener.run_historical_qualification(test_stocks)
        print(f"历史资格审查结果: {qualified_pool}")
        
        for stock_code, qual_score in qualified_pool.items():
            try:
                result = enhanced_ma13_screener.analyze_single_stock(stock_code, stage1_qual=qual_score)
                if result:
                    print(f"{stock_code}: 历史={qual_score:.1f}, 总分={result.total_score:.1f}, 合格={result.daily_qualified}")
                else:
                    print(f"{stock_code}: 第二阶段分析失败")
            except Exception as e:
                print(f"{stock_code}: 第二阶段错误 - {e}")
        
        # 批量测试
        print("\n【批量筛选测试】")
        batch_results = enhanced_ma13_screener.screen_stocks(test_stocks, use_two_stage=False)
        print(f"批量筛选结果: {len(batch_results)}只股票")
        for result in batch_results:
            print(f"  {result.stock_code}: {result.total_score:.1f}分, {result.recommendation.get('action', 'wait')}")
        
        return True
        
    except Exception as e:
        print(f"直接测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_api_conversion():
    """
    测试API格式转换
    """
    print("\n" + "=" * 60)
    print("测试API格式转换")
    print("=" * 60)
    
    try:
        from backend.enhanced_ma13_screener import enhanced_ma13_screener
        from backend.enhanced_ma13_api import _convert_enhanced_result_to_api_format
        
        # 获取一个筛选结果
        result = enhanced_ma13_screener.analyze_single_stock('sh601388')
        if result:
            # 转换为API格式
            api_result = _convert_enhanced_result_to_api_format(result, use_two_stage=False)
            
            print("API格式转换成功:")
            print(f"  股票代码: {api_result['stock_code']}")
            print(f"  成功状态: {api_result['success']}")
            print(f"  分析模式: {api_result['analysis_mode']}")
            print(f"  总分: {api_result['enhanced_data']['total_score']:.1f}")
            print(f"  操作建议: {api_result['recommendation']['action']}")
            print(f"  信心度: {api_result['recommendation']['confidence']:.1f}%")
            
            return True
        else:
            print("无法获取筛选结果")
            return False
            
    except Exception as e:
        print(f"API转换测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_flask_api(base_url='http://localhost:5000'):
    """
    测试Flask API接口（需要先启动Flask应用）
    """
    print("\n" + "=" * 60)
    print("测试Flask API接口")
    print("=" * 60)
    
    # 测试单股分析
    print("【测试单股分析】")
    try:
        response = requests.post(f'{base_url}/api/enhanced_ma13/analyze', 
                               json={'stock_code': 'sh601388', 'use_two_stage': False},
                               timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            print(f"单股分析成功: {result['stock_code']}, 成功={result['success']}")
            if result['success']:
                print(f"  总分: {result['enhanced_data']['total_score']:.1f}")
                print(f"  操作建议: {result['recommendation']['action']}")
        else:
            print(f"单股分析失败: HTTP {response.status_code}")
            
    except requests.exceptions.RequestException as e:
        print(f"API请求失败: {e}")
        print("请确保Flask应用正在运行 (python backend/app.py)")
        return False
    
    # 测试批量扫描
    print("\n【测试批量扫描】")
    try:
        response = requests.post(f'{base_url}/api/enhanced_ma13/batch_scan',
                               json={'stock_codes': ['sh601388', 'sz002021', 'sz000001'], 'use_two_stage': False},
                               timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            print(f"批量扫描成功: 扫描{result['summary']['total_scanned']}只, 合格{result['summary']['qualified_count']}只")
            print(f"合格率: {result['summary']['qualified_rate']:.1f}%")
        else:
            print(f"批量扫描失败: HTTP {response.status_code}")
            
    except requests.exceptions.RequestException as e:
        print(f"批量扫描请求失败: {e}")
        return False
    
    return True

def main():
    """
    主测试函数
    """
    print("增强MA13策略API测试")
    print("=" * 60)
    
    # 直接测试
    direct_success = test_enhanced_api_direct()
    
    # API转换测试
    conversion_success = test_api_conversion()
    
    # Flask API测试（可选）
    flask_success = True  # 默认跳过Flask测试
    
    # 询问是否测试Flask API
    try:
        test_flask = input("\n是否测试Flask API接口？(需要先启动Flask应用) [y/N]: ").lower().strip()
        if test_flask in ['y', 'yes']:
            flask_success = test_flask_api()
    except KeyboardInterrupt:
        print("\n测试被用户中断")
    
    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    print(f"直接测试: {'✓ 通过' if direct_success else '✗ 失败'}")
    print(f"API转换: {'✓ 通过' if conversion_success else '✗ 失败'}")
    print(f"Flask API: {'✓ 通过' if flask_success else '✗ 失败'}")
    
    if direct_success and conversion_success:
        print("\n🎉 增强MA13策略核心功能正常！")
        print("可以开始前端适配工作。")
    else:
        print("\n❌ 存在问题需要修复。")
    
    return direct_success and conversion_success

if __name__ == '__main__':
    main()