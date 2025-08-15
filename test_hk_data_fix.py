#!/usr/bin/env python3
"""
测试港股数据获取修复
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from data_handler import get_full_data_with_indicators, _get_market_from_stock_code

def test_market_detection():
    """测试市场识别功能"""
    print("=== 测试市场识别功能 ===")
    
    test_codes = [
        'sh600006',  # 沪市
        'sz000001',  # 深市
        '31#01772',  # 港股
        '43#00700',  # 港股
    ]
    
    for code in test_codes:
        market = _get_market_from_stock_code(code)
        print(f"股票代码: {code} -> 市场: {market}")

def test_hk_data_loading():
    """测试港股数据加载"""
    print("\n=== 测试港股数据加载 ===")
    
    hk_code = '31#01772'
    print(f"正在测试港股代码: {hk_code}")
    
    try:
        df = get_full_data_with_indicators(hk_code)
        if df is not None:
            print(f"✅ 成功获取数据，共 {len(df)} 条记录")
            print(f"数据时间范围: {df.index[0]} 到 {df.index[-1]}")
            print(f"最新价格: {df.iloc[-1]['close']:.2f}")
            print(f"包含指标: {list(df.columns)}")
        else:
            print("❌ 未能获取数据")
    except Exception as e:
        print(f"❌ 获取数据时出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_market_detection()
    test_hk_data_loading()