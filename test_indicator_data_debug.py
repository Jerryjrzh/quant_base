#!/usr/bin/env python3
"""
检查指标数据中的null值问题
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

def check_indicator_data():
    """检查指标数据中的null值"""
    try:
        from app import app
        
        with app.test_client() as client:
            response = client.get('/api/unified_analysis/sh600036')
            
            if response.status_code == 200:
                data = response.get_json()
                
                if data.get('success'):
                    chart_data = data['data']['chart_data']
                    indicator_data = chart_data['indicator_data']
                    
                    print(f"Total indicator data points: {len(indicator_data)}")
                    
                    # Check first few records for null values
                    print("\nFirst 10 records:")
                    for i in range(min(10, len(indicator_data))):
                        record = indicator_data[i]
                        null_keys = [k for k, v in record.items() if v is None]
                        if null_keys:
                            print(f"Record {i}: {record['date']} - NULL keys: {null_keys}")
                        else:
                            print(f"Record {i}: {record['date']} - All values OK")
                    
                    # Check last few records
                    print("\nLast 10 records:")
                    for i in range(max(0, len(indicator_data)-10), len(indicator_data)):
                        record = indicator_data[i]
                        null_keys = [k for k, v in record.items() if v is None]
                        if null_keys:
                            print(f"Record {i}: {record['date']} - NULL keys: {null_keys}")
                        else:
                            print(f"Record {i}: {record['date']} - All values OK")
                    
                    # Count total null values by key
                    print("\nNull value counts by indicator:")
                    keys = ['ma13', 'ma45', 'dif', 'dea', 'macd', 'k', 'd', 'j', 'rsi6', 'rsi12', 'rsi24']
                    for key in keys:
                        null_count = sum(1 for record in indicator_data if record.get(key) is None)
                        print(f"{key}: {null_count} null values")
                        
                else:
                    print(f"API Error: {data.get('error')}")
            else:
                print(f"HTTP Error: {response.status_code}")
                
    except Exception as e:
        import traceback
        print(f"Check failed: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    check_indicator_data()