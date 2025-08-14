#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试保存结果修复
"""

import sys
import os
import tempfile
import shutil
import numpy as np
import pandas as pd

# 添加backend目录到路径
sys.path.append('backend')

def test_save_results():
    """测试保存结果功能"""
    print("🔍 测试保存结果功能")
    print("=" * 50)
    
    try:
        import universal_screener
        from strategies.base_strategy import StrategyResult
        
        # 创建临时目录
        temp_dir = tempfile.mkdtemp()
        print(f"📁 临时目录: {temp_dir}")
        
        # 创建筛选器实例
        screener = universal_screener.UniversalScreener()
        
        # 创建测试结果（包含numpy数据类型）
        test_results = []
        
        for i in range(3):
            signal_details = {
                'stage_passed': np.int64(i + 1),
                'confidence': np.float64(0.8 + i * 0.05),
                'indicators': {
                    'ma5': np.float64(10.0 + i),
                    'ma20': np.float64(9.5 + i),
                    'volume': np.int64(1000000 + i * 100000)
                },
                'price_history': np.array([10.0 + i, 10.1 + i, 10.2 + i]),
                'timestamp': pd.Timestamp.now()
            }
            
            result = StrategyResult(
                stock_code=f'sh60000{i}',
                strategy_name=f'测试策略{i+1}',
                signal_type='BUY',
                signal_strength=i + 1,
                date='2025-08-14',
                current_price=10.25 + i * 0.1,
                signal_details=signal_details
            )
            
            test_results.append(result)
        
        print(f"📊 创建了 {len(test_results)} 个测试结果")
        
        # 测试保存结果
        saved_files = screener.save_results(test_results, temp_dir)
        
        if saved_files:
            print("✅ 结果保存成功")
            print("📄 保存的文件:")
            for file_type, file_path in saved_files.items():
                file_size = os.path.getsize(file_path)
                print(f"  - {file_type.upper()}: {os.path.basename(file_path)} ({file_size} bytes)")
                
                # 验证JSON文件可以正常读取
                if file_type in ['json', 'summary']:
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            data = f.read()
                            import json
                            parsed = json.loads(data)
                        print(f"    ✅ {file_type.upper()} 文件格式正确")
                    except Exception as e:
                        print(f"    ❌ {file_type.upper()} 文件格式错误: {e}")
                        return False
        else:
            print("❌ 结果保存失败")
            return False
        
        # 清理临时目录
        shutil.rmtree(temp_dir)
        print("🧹 清理临时文件完成")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函数"""
    print("🚀 保存结果修复测试")
    print("=" * 50)
    
    success = test_save_results()
    
    print("\n" + "=" * 50)
    if success:
        print("🎉 保存结果测试通过！JSON序列化问题已修复！")
    else:
        print("❌ 保存结果测试失败")
    
    return success

if __name__ == '__main__':
    main()