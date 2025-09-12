#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试股票画像修复效果

验证KDJ和RSI参数修复是否正确
"""

import os
import sys
import logging

# 添加backend目录到路径
sys.path.append('backend')

def test_indicator_calls():
    """测试指标调用是否正确"""
    print("🧪 测试指标调用修复")
    print("-" * 40)
    
    try:
        import data_handler
        import indicators
        
        # 获取测试数据
        test_stock = "sz300290"
        print(f"获取 {test_stock} 数据...")
        
        df = data_handler.get_full_data_with_indicators(test_stock)
        if df is None or len(df) < 100:
            print(f"❌ {test_stock} 数据不足")
            return False
        
        print(f"✅ 数据长度: {len(df)} 天")
        
        # 测试KDJ调用
        print("\n测试KDJ指标调用...")
        try:
            kdj_k, kdj_d, kdj_j = indicators.calculate_kdj(df, n=9)
            print(f"✅ KDJ调用成功，返回3个值")
            print(f"   K值范围: {kdj_k.min():.2f} ~ {kdj_k.max():.2f}")
            print(f"   D值范围: {kdj_d.min():.2f} ~ {kdj_d.max():.2f}")
            print(f"   J值范围: {kdj_j.min():.2f} ~ {kdj_j.max():.2f}")
        except Exception as e:
            print(f"❌ KDJ调用失败: {e}")
            return False
        
        # 测试RSI调用
        print("\n测试RSI指标调用...")
        try:
            rsi = indicators.calculate_rsi(df, periods=14)
            print(f"✅ RSI调用成功")
            print(f"   RSI范围: {rsi.min():.2f} ~ {rsi.max():.2f}")
        except Exception as e:
            print(f"❌ RSI调用失败: {e}")
            return False
        
        # 测试MACD调用
        print("\n测试MACD指标调用...")
        try:
            macd_line, signal_line = indicators.calculate_macd(df, fast=12, slow=26)
            print(f"✅ MACD调用成功")
            print(f"   MACD范围: {macd_line.min():.4f} ~ {macd_line.max():.4f}")
            print(f"   信号线范围: {signal_line.min():.4f} ~ {signal_line.max():.4f}")
        except Exception as e:
            print(f"❌ MACD调用失败: {e}")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ 测试过程中出错: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_stock_profiler():
    """测试股票画像生成器"""
    print("\n🧪 测试股票画像生成器")
    print("-" * 40)
    
    try:
        from stock_profiler import StockProfiler
        
        # 设置日志
        logging.basicConfig(level=logging.INFO)
        
        profiler = StockProfiler()
        test_stock = "sz300290"
        
        print(f"测试为 {test_stock} 生成画像...")
        
        # 测试单只股票画像生成
        success = profiler.create_stock_profile(test_stock)
        
        if success:
            print("✅ 画像生成成功")
            
            # 获取生成的画像数据
            from stock_pool_manager import StockPoolManager
            pool_manager = StockPoolManager()
            stock_data = pool_manager.get_stock_by_code(test_stock)
            
            if stock_data and stock_data.get('optimized_params'):
                import json
                try:
                    if isinstance(stock_data['optimized_params'], str):
                        params = json.loads(stock_data['optimized_params'])
                    else:
                        params = stock_data['optimized_params']
                    
                    print("📊 优化参数:")
                    for key, value in params.items():
                        if isinstance(value, float):
                            print(f"   {key}: {value:.4f}")
                        else:
                            print(f"   {key}: {value}")
                    
                except Exception as e:
                    print(f"❌ 解析画像数据失败: {e}")
            else:
                print("⚠️ 未找到画像数据")
        else:
            print("❌ 画像生成失败")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ 测试股票画像生成器失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数"""
    print("🚀 股票画像修复效果测试")
    print("=" * 50)
    
    # 测试指标调用
    indicator_test_passed = test_indicator_calls()
    
    # 测试画像生成器
    profiler_test_passed = test_stock_profiler()
    
    print("\n" + "=" * 50)
    print("📋 测试结果汇总:")
    print(f"   指标调用测试: {'✅ 通过' if indicator_test_passed else '❌ 失败'}")
    print(f"   画像生成测试: {'✅ 通过' if profiler_test_passed else '❌ 失败'}")
    
    if indicator_test_passed and profiler_test_passed:
        print("\n🎉 所有测试通过！修复成功！")
        print("现在可以安全地运行股票画像生成脚本了。")
    else:
        print("\n⚠️ 部分测试失败，需要进一步检查。")


if __name__ == "__main__":
    main()