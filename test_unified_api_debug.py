#!/usr/bin/env python3
"""
测试统一API的数据结构
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

def test_unified_api():
    """测试统一API的数据结构"""
    try:
        from app import app
        
        # Test the unified API endpoint
        with app.test_client() as client:
            response = client.get('/api/unified_analysis/sh600036')
            
            print(f"HTTP Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.get_json()
                print(f"API Response Structure:")
                print(f"success: {data.get('success')}")
                
                if data.get('success'):
                    result_data = data.get('data', {})
                    print(f"stock_code: {result_data.get('stock_code')}")
                    print(f"stock_name: {result_data.get('stock_name')}")
                    
                    chart_data = result_data.get('chart_data', {})
                    print(f"chart_data keys: {list(chart_data.keys())}")
                    
                    if 'kline_data' in chart_data:
                        kline_data = chart_data['kline_data']
                        print(f"kline_data length: {len(kline_data)}")
                        if kline_data:
                            print(f"kline_data sample: {kline_data[0]}")
                    
                    if 'indicator_data' in chart_data:
                        indicator_data = chart_data['indicator_data']
                        print(f"indicator_data length: {len(indicator_data)}")
                        if indicator_data:
                            print(f"indicator_data sample keys: {list(indicator_data[0].keys())}")
                            # Check for null values
                            sample = indicator_data[0]
                            null_keys = [k for k, v in sample.items() if v is None]
                            if null_keys:
                                print(f"WARNING: Found null values in keys: {null_keys}")
                else:
                    print(f"Error: {data.get('error')}")
            else:
                print(f"HTTP Error: {response.status_code}")
                print(response.get_data(as_text=True))
                
    except Exception as e:
        import traceback
        print(f"Test failed: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    test_unified_api()