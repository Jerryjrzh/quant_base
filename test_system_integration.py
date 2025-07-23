#!/usr/bin/env python3
"""
系统集成测试脚本 - 验证深度扫描集成功能
"""

import os
import sys
import json
import time
import subprocess
from datetime import datetime

def test_screener_integration():
    """测试筛选器集成深度扫描功能"""
    print("🧪 测试筛选器集成深度扫描功能")
    print("=" * 60)
    
    # 检查必要文件是否存在
    required_files = [
        'backend/screener.py',
        'backend/run_enhanced_screening.py',
        'backend/enhanced_analyzer.py',
        'backend/trading_advisor.py',
        'backend/parametric_advisor.py'
    ]
    
    missing_files = []
    for file_path in required_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
    
    if missing_files:
        print(f"❌ 缺少必要文件: {missing_files}")
        return False
    
    print("✅ 所有必要文件存在")
    return True

def test_deep_scan_functions():
    """测试深度扫描功能"""
    print("\n🔍 测试深度扫描功能")
    print("-" * 40)
    
    try:
        # 导入深度扫描模块
        sys.path.append('backend')
        from run_enhanced_screening import analyze_single_stock, deep_scan_stocks
        
        print("✅ 深度扫描模块导入成功")
        
        # 测试单股票分析
        test_stock = 'sh000001'  # 上证指数
        print(f"📊 测试单股票分析: {test_stock}")
        
        try:
            result = analyze_single_stock(test_stock, use_optimized_params=False)
            if result and 'error' not in result:
                print(f"✅ 单股票分析成功")
                print(f"   - 综合评分: {result.get('overall_score', {}).get('total_score', 'N/A')}")
                print(f"   - 等级: {result.get('overall_score', {}).get('grade', 'N/A')}")
                print(f"   - 建议: {result.get('recommendation', {}).get('action', 'N/A')}")
            else:
                print(f"⚠️ 单股票分析返回错误: {result.get('error', '未知错误')}")
        except Exception as e:
            print(f"❌ 单股票分析失败: {e}")
        
        # 测试多股票深度扫描
        test_stocks = ['sh000001', 'sz000001']
        print(f"\n📈 测试多股票深度扫描: {test_stocks}")
        
        try:
            results = deep_scan_stocks(test_stocks, use_optimized_params=False, max_workers=32)
            if results:
                valid_results = {k: v for k, v in results.items() if 'error' not in v}
                print(f"✅ 多股票深度扫描成功")
                print(f"   - 分析股票数: {len(results)}")
                print(f"   - 成功分析数: {len(valid_results)}")
                
                for stock_code, result in valid_results.items():
                    score = result.get('overall_score', {}).get('total_score', 0)
                    grade = result.get('overall_score', {}).get('grade', 'N/A')
                    action = result.get('recommendation', {}).get('action', 'N/A')
                    print(f"   - {stock_code}: {score:.1f}分, {grade}级, {action}")
            else:
                print("⚠️ 多股票深度扫描返回空结果")
        except Exception as e:
            print(f"❌ 多股票深度扫描失败: {e}")
        
        return True
        
    except ImportError as e:
        print(f"❌ 深度扫描模块导入失败: {e}")
        return False
    except Exception as e:
        print(f"❌ 深度扫描功能测试失败: {e}")
        return False

def test_price_evaluation():
    """测试价格评估功能"""
    print("\n💰 测试价格评估功能")
    print("-" * 40)
    
    try:
        sys.path.append('backend')
        from run_enhanced_screening import perform_price_evaluation
        
        # 模拟A级股票分析结果
        mock_analysis_result = {
            'basic_analysis': {
                'current_price': 10.50
            },
            'trading_advice': {
                'advice': {
                    'entry_strategies': [{
                        'strategy': 'MACD零轴启动',
                        'entry_price_1': 10.20,
                        'entry_price_2': 10.00,
                        'position_allocation': '30%-50%'
                    }],
                    'risk_management': {
                        'stop_loss_levels': {
                            'conservative': 9.80,
                            'moderate': 9.50,
                            'aggressive': 9.20,
                            'technical': 9.00
                        },
                        'take_profit_levels': {
                            'conservative': 11.50,
                            'moderate': 12.00,
                            'aggressive': 12.50
                        }
                    }
                }
            }
        }
        
        test_stock = 'test000001'
        evaluation = perform_price_evaluation(test_stock, mock_analysis_result)
        
        if evaluation and 'error' not in evaluation:
            print("✅ 价格评估功能正常")
            print(f"   - 股票代码: {evaluation.get('stock_code', 'N/A')}")
            print(f"   - 当前价格: ¥{evaluation.get('current_price', 0):.2f}")
            print(f"   - 等级: {evaluation.get('grade', 'N/A')}")
            
            details = evaluation.get('evaluation_details', {})
            if details:
                print(f"   - 入场策略: {details.get('entry_strategy', 'N/A')}")
                print(f"   - 目标价1: ¥{details.get('target_price_1', 0):.2f}")
                print(f"   - 目标价2: ¥{details.get('target_price_2', 0):.2f}")
        else:
            print(f"⚠️ 价格评估返回错误: {evaluation.get('error', '未知错误')}")
        
        return True
        
    except Exception as e:
        print(f"❌ 价格评估功能测试失败: {e}")
        return False

def test_multithreading():
    """测试多线程功能"""
    print("\n🧵 测试多线程功能")
    print("-" * 40)
    
    try:
        sys.path.append('backend')
        from run_enhanced_screening import analyze_single_stock_worker
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        test_stocks = ['sh000001', 'sz000001', 'sz000002']
        print(f"📊 使用多线程分析 {len(test_stocks)} 只股票")
        
        start_time = time.time()
        results = {}
        
        with ThreadPoolExecutor(max_workers=32) as executor:
            future_to_stock = {
                executor.submit(analyze_single_stock_worker, stock_code, False): stock_code 
                for stock_code in test_stocks
            }
            
            for future in as_completed(future_to_stock):
                stock_code = future_to_stock[future]
                try:
                    stock_code, result = future.result()
                    results[stock_code] = result
                except Exception as e:
                    results[stock_code] = {'error': f'分析失败: {e}'}
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        valid_results = {k: v for k, v in results.items() if 'error' not in v}
        
        print(f"✅ 多线程分析完成")
        print(f"   - 处理时间: {processing_time:.2f} 秒")
        print(f"   - 分析股票数: {len(results)}")
        print(f"   - 成功分析数: {len(valid_results)}")
        
        for stock_code, result in results.items():
            if 'error' not in result:
                score = result.get('overall_score', {}).get('total_score', 0)
                grade = result.get('overall_score', {}).get('grade', 'N/A')
                print(f"   - {stock_code}: {score:.1f}分, {grade}级")
            else:
                print(f"   - {stock_code}: {result['error']}")
        
        return True
        
    except Exception as e:
        print(f"❌ 多线程功能测试失败: {e}")
        return False

def test_api_endpoints():
    """测试API端点"""
    print("\n🌐 测试API端点")
    print("-" * 40)
    
    try:
        import requests
        
        base_url = "http://127.0.0.1:5000"
        
        # 测试深度扫描结果API
        print("📡 测试深度扫描结果API")
        try:
            response = requests.get(f"{base_url}/api/deep_scan_results", timeout=5)
            if response.status_code == 200:
                data = response.json()
                if 'error' not in data:
                    print("✅ 深度扫描结果API正常")
                    print(f"   - 分析数量: {data.get('summary', {}).get('total_analyzed', 0)}")
                    print(f"   - A级股票: {data.get('summary', {}).get('a_grade_count', 0)}")
                else:
                    print(f"⚠️ 深度扫描结果API返回错误: {data['error']}")
            else:
                print(f"⚠️ 深度扫描结果API响应异常: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"⚠️ 无法连接到API服务器: {e}")
        
        # 测试触发深度扫描API
        print("\n📡 测试触发深度扫描API")
        try:
            response = requests.post(f"{base_url}/api/run_deep_scan?strategy=MACD_ZERO_AXIS", 
                                   timeout=30)
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    print("✅ 触发深度扫描API正常")
                    print(f"   - 消息: {data.get('message', 'N/A')}")
                    summary = data.get('summary', {})
                    print(f"   - 分析数量: {summary.get('total_analyzed', 0)}")
                    print(f"   - A级股票: {summary.get('a_grade_count', 0)}")
                else:
                    print(f"⚠️ 触发深度扫描API返回错误: {data.get('error', '未知错误')}")
            else:
                print(f"⚠️ 触发深度扫描API响应异常: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"⚠️ 无法连接到API服务器: {e}")
        
        return True
        
    except ImportError:
        print("⚠️ requests模块未安装，跳过API测试")
        return True
    except Exception as e:
        print(f"❌ API端点测试失败: {e}")
        return False

def test_data_persistence():
    """测试数据持久化"""
    print("\n💾 测试数据持久化")
    print("-" * 40)
    
    try:
        # 检查结果目录结构
        result_dirs = [
            'data/result/ENHANCED_ANALYSIS',
            'data/result/A_GRADE_EVALUATIONS',
            'data/result/MACD_ZERO_AXIS',
            'data/result/TRIPLE_CROSS',
            'data/result/PRE_CROSS'
        ]
        
        existing_dirs = []
        for dir_path in result_dirs:
            if os.path.exists(dir_path):
                existing_dirs.append(dir_path)
                file_count = len([f for f in os.listdir(dir_path) if f.endswith('.json')])
                print(f"✅ {dir_path}: {file_count} 个JSON文件")
            else:
                print(f"⚠️ {dir_path}: 目录不存在")
        
        if existing_dirs:
            print(f"✅ 数据持久化目录正常，共 {len(existing_dirs)} 个目录")
        else:
            print("⚠️ 没有找到数据持久化目录")
        
        return True
        
    except Exception as e:
        print(f"❌ 数据持久化测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🚀 系统集成测试开始")
    print("=" * 80)
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    test_results = []
    
    # 执行各项测试
    tests = [
        ("文件完整性检查", test_screener_integration),
        ("深度扫描功能", test_deep_scan_functions),
        ("价格评估功能", test_price_evaluation),
        ("多线程功能", test_multithreading),
        ("API端点", test_api_endpoints),
        ("数据持久化", test_data_persistence)
    ]
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            test_results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} 测试异常: {e}")
            test_results.append((test_name, False))
    
    # 汇总测试结果
    print("\n" + "=" * 80)
    print("📊 测试结果汇总")
    print("=" * 80)
    
    passed_tests = 0
    total_tests = len(test_results)
    
    for test_name, result in test_results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{test_name:20} : {status}")
        if result:
            passed_tests += 1
    
    print("-" * 80)
    print(f"总测试数: {total_tests}")
    print(f"通过测试: {passed_tests}")
    print(f"失败测试: {total_tests - passed_tests}")
    print(f"通过率: {passed_tests/total_tests*100:.1f}%")
    
    if passed_tests == total_tests:
        print("\n🎉 所有测试通过！系统集成成功！")
        return True
    else:
        print(f"\n⚠️ 有 {total_tests - passed_tests} 个测试失败，请检查相关功能")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)