#!/usr/bin/env python3
"""
测试增强版交易建议系统（包含卖出价系数）
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from datetime import datetime
from get_trading_advice_enhanced import get_stock_advice_with_backtest

def test_enhanced_advice():
    """测试增强版交易建议功能"""
    
    # 测试股票列表
    test_stocks = [
        ('sh000001', None),      # 上证指数
        ('sz000001', 12.50),     # 平安银行，指定入场价
        ('sz000002', None),      # 万科A
        ('sh600036', None),      # 招商银行
    ]
    
    print("🚀 开始测试增强版交易建议系统（含卖出价系数）")
    print("=" * 80)
    
    for i, (stock_code, entry_price) in enumerate(test_stocks, 1):
        print(f"\n📊 测试 {i}/{len(test_stocks)}: {stock_code}")
        print("-" * 50)
        
        try:
            result = get_stock_advice_with_backtest(stock_code, entry_price)
            print(result)
            
        except Exception as e:
            print(f"❌ 测试失败: {e}")
        
        print("\n" + "=" * 80)
    
    print("✅ 测试完成")

def test_specific_stock():
    """测试特定股票的深度分析"""
    stock_code = input("请输入股票代码（如 sz000001）: ").strip().lower()
    
    if not stock_code:
        print("❌ 股票代码不能为空")
        return
    
    entry_price_input = input("请输入入场价格（回车使用当前价格）: ").strip()
    entry_price = float(entry_price_input) if entry_price_input else None
    
    print(f"\n🔍 开始分析 {stock_code}...")
    print("=" * 60)
    
    try:
        result = get_stock_advice_with_backtest(stock_code, entry_price)
        print(result)
        
    except Exception as e:
        print(f"❌ 分析失败: {e}")

def main():
    """主函数"""
    print("增强版交易建议系统测试工具")
    print("1. 批量测试多只股票")
    print("2. 测试特定股票")
    print("3. 退出")
    
    choice = input("\n请选择测试模式 (1-3): ").strip()
    
    if choice == '1':
        test_enhanced_advice()
    elif choice == '2':
        test_specific_stock()
    elif choice == '3':
        print("👋 再见！")
    else:
        print("❌ 无效选择")

if __name__ == "__main__":
    main()