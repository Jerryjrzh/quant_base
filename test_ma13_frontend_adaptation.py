#!/usr/bin/env python3
"""
MA13前端适配测试脚本

测试增强MA13策略的前端适配功能，验证：
1. 增强API接口是否正常工作
2. 两阶段架构是否正确实现
3. 前端数据格式是否兼容
4. 批量扫描功能是否正常
"""

import requests
import json
import time
from datetime import datetime

def test_enhanced_ma13_api():
    """测试增强MA13 API接口"""
    print("=" * 60)
    print("测试增强MA13 API接口")
    print("=" * 60)
    
    base_url = "http://localhost:5000"
    test_stocks = ["002021", "sh601388", "sz000858"]
    
    # 测试单股分析
    print("\n1. 测试单股分析（增强模式）")
    for stock_code in test_stocks:
        print(f"\n测试股票: {stock_code}")
        
        # 测试增强模式
        try:
            response = requests.post(f"{base_url}/api/enhanced_ma13/analyze", 
                json={
                    "stock_code": stock_code,
                    "use_enhanced": True,
                    "use_two_stage": False
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"  ✓ 增强分析成功: {result.get('success', False)}")
                
                if result.get('enhanced_data'):
                    enhanced = result['enhanced_data']
                    print(f"    - 综合得分: {enhanced.get('total_score', 'N/A')}")
                    print(f"    - 市场阶段: {enhanced.get('market_phase', 'N/A')}")
                    print(f"    - 小时线模型: {enhanced.get('hourly_model', 'N/A')}")
                else:
                    print("    - 未返回增强数据")
            else:
                print(f"  ✗ API请求失败: {response.status_code}")
                
        except Exception as e:
            print(f"  ✗ 请求异常: {str(e)}")
        
        # 测试两阶段模式
        try:
            response = requests.post(f"{base_url}/api/enhanced_ma13/analyze", 
                json={
                    "stock_code": stock_code,
                    "use_enhanced": True,
                    "use_two_stage": True
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"  ✓ 两阶段分析成功: {result.get('success', False)}")
                
                if result.get('enhanced_data', {}).get('stage1_qualification'):
                    stage1_qual = result['enhanced_data']['stage1_qualification']
                    print(f"    - 历史资格得分: {stage1_qual}")
                else:
                    print("    - 未返回历史资格数据")
            else:
                print(f"  ✗ 两阶段API请求失败: {response.status_code}")
                
        except Exception as e:
            print(f"  ✗ 两阶段请求异常: {str(e)}")
    
    # 测试批量扫描
    print("\n2. 测试批量扫描（增强模式）")
    try:
        response = requests.post(f"{base_url}/api/enhanced_ma13/batch_scan", 
            json={
                "stock_codes": test_stocks,
                "use_two_stage": False
            },
            timeout=60
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"  ✓ 批量扫描成功: {result.get('success', False)}")
            
            if result.get('summary'):
                summary = result['summary']
                print(f"    - 扫描数量: {summary.get('total_scanned', 0)}")
                print(f"    - 符合条件: {summary.get('qualified_count', 0)}")
                print(f"    - 符合率: {summary.get('qualified_rate', 0):.1f}%")
            
            if result.get('results'):
                print(f"    - 返回结果数: {len(result['results'])}")
                for res in result['results'][:2]:  # 只显示前2个结果
                    enhanced = res.get('enhanced_data', {})
                    print(f"      {res.get('stock_code')}: 得分={enhanced.get('total_score', 'N/A')}")
        else:
            print(f"  ✗ 批量扫描失败: {response.status_code}")
            
    except Exception as e:
        print(f"  ✗ 批量扫描异常: {str(e)}")
    
    # 测试全市场扫描（小规模）
    print("\n3. 测试全市场扫描（增强模式，限制10只）")
    try:
        response = requests.post(f"{base_url}/api/enhanced_ma13/full_market_scan", 
            json={
                "max_stocks": 10,
                "use_two_stage": False
            },
            timeout=120
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"  ✓ 全市场扫描成功: {result.get('success', False)}")
            
            if result.get('scan_stats'):
                stats = result['scan_stats']
                print(f"    - 处理股票: {stats.get('processed_stocks', 0)}")
                print(f"    - 符合条件: {stats.get('qualified_stocks', 0)}")
                
                if stats.get('stage_distribution'):
                    print("    - 阶段分布:")
                    for stage, count in stats['stage_distribution'].items():
                        print(f"      {stage}: {count}只")
        else:
            print(f"  ✗ 全市场扫描失败: {response.status_code}")
            
    except Exception as e:
        print(f"  ✗ 全市场扫描异常: {str(e)}")

def test_frontend_compatibility():
    """测试前端兼容性"""
    print("\n" + "=" * 60)
    print("测试前端数据格式兼容性")
    print("=" * 60)
    
    base_url = "http://localhost:5000"
    test_stock = "002021"
    
    print(f"\n测试股票: {test_stock}")
    
    try:
        # 获取增强分析结果
        response = requests.post(f"{base_url}/api/enhanced_ma13/analyze", 
            json={
                "stock_code": test_stock,
                "use_enhanced": True,
                "use_two_stage": False
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            
            # 检查前端期望的数据结构
            required_fields = [
                'success', 'stock_code', 'analysis_mode', 'message',
                'stage_1', 'stage_2', 'stage_3', 'signals', 'recommendation',
                'key_levels', 'current_data', 'enhanced_data'
            ]
            
            print("\n检查前端期望的数据字段:")
            for field in required_fields:
                if field in result:
                    print(f"  ✓ {field}: 存在")
                else:
                    print(f"  ✗ {field}: 缺失")
            
            # 检查增强数据字段
            if 'enhanced_data' in result:
                enhanced = result['enhanced_data']
                enhanced_fields = [
                    'daily_stage', 'daily_score', 'hourly_model', 'hourly_score',
                    'market_phase', 'total_score', 'confidence'
                ]
                
                print("\n检查增强数据字段:")
                for field in enhanced_fields:
                    if field in enhanced:
                        print(f"  ✓ {field}: {enhanced[field]}")
                    else:
                        print(f"  ✗ {field}: 缺失")
            
            # 检查操作建议字段
            if 'recommendation' in result:
                rec = result['recommendation']
                rec_fields = ['action', 'position_size', 'confidence', 'entry_timing']
                
                print("\n检查操作建议字段:")
                for field in rec_fields:
                    if field in rec:
                        print(f"  ✓ {field}: {rec[field]}")
                    else:
                        print(f"  ✗ {field}: 缺失")
        else:
            print(f"✗ API请求失败: {response.status_code}")
            
    except Exception as e:
        print(f"✗ 兼容性测试异常: {str(e)}")

def test_performance():
    """测试性能"""
    print("\n" + "=" * 60)
    print("测试性能")
    print("=" * 60)
    
    base_url = "http://localhost:5000"
    test_stocks = ["002021", "sh601388", "sz000858", "sz002796", "sh600618"]
    
    # 测试单股分析性能
    print("\n1. 单股分析性能测试")
    start_time = time.time()
    
    for stock_code in test_stocks:
        try:
            response = requests.post(f"{base_url}/api/enhanced_ma13/analyze", 
                json={
                    "stock_code": stock_code,
                    "use_enhanced": True,
                    "use_two_stage": False
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"  ✓ {stock_code}: {result.get('success', False)}")
            else:
                print(f"  ✗ {stock_code}: HTTP {response.status_code}")
                
        except Exception as e:
            print(f"  ✗ {stock_code}: {str(e)}")
    
    end_time = time.time()
    avg_time = (end_time - start_time) / len(test_stocks)
    print(f"\n平均单股分析时间: {avg_time:.2f}秒")
    
    # 测试批量分析性能
    print("\n2. 批量分析性能测试")
    start_time = time.time()
    
    try:
        response = requests.post(f"{base_url}/api/enhanced_ma13/batch_scan", 
            json={
                "stock_codes": test_stocks,
                "use_two_stage": False
            },
            timeout=120
        )
        
        end_time = time.time()
        batch_time = end_time - start_time
        
        if response.status_code == 200:
            result = response.json()
            print(f"  ✓ 批量分析成功: {result.get('success', False)}")
            print(f"  批量分析时间: {batch_time:.2f}秒")
            print(f"  平均每股时间: {batch_time/len(test_stocks):.2f}秒")
        else:
            print(f"  ✗ 批量分析失败: HTTP {response.status_code}")
            
    except Exception as e:
        print(f"  ✗ 批量分析异常: {str(e)}")

def main():
    """主函数"""
    print("MA13前端适配测试")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # 测试API接口
        test_enhanced_ma13_api()
        
        # 测试前端兼容性
        test_frontend_compatibility()
        
        # 测试性能
        test_performance()
        
        print("\n" + "=" * 60)
        print("测试完成")
        print("=" * 60)
        
    except KeyboardInterrupt:
        print("\n测试被用户中断")
    except Exception as e:
        print(f"\n测试过程中出现异常: {str(e)}")

if __name__ == "__main__":
    main()