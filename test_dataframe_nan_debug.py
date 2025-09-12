#!/usr/bin/env python3
"""
检查DataFrame中的NaN值问题
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

def check_dataframe_nan():
    """检查DataFrame中的NaN值"""
    try:
        from data_handler import get_full_data_with_indicators
        import pandas as pd
        import numpy as np
        
        stock_code = 'sh600036'
        df = get_full_data_with_indicators(stock_code)
        
        if df is None:
            print("Failed to get data")
            return
            
        print(f"DataFrame shape: {df.shape}")
        print(f"DataFrame columns: {list(df.columns)}")
        
        # Check for NaN values
        print("\nNaN value counts by column:")
        for col in df.columns:
            nan_count = df[col].isna().sum()
            if nan_count > 0:
                print(f"{col}: {nan_count} NaN values")
        
        # Check the data types
        print("\nData types:")
        print(df.dtypes)
        
        # Check the last few rows
        print("\nLast 5 rows:")
        print(df.tail())
        
        # Test the conversion process
        print("\nTesting conversion process...")
        df_reset = df.reset_index()
        df_reset['date'] = pd.to_datetime(df_reset['date']).dt.strftime('%Y-%m-%d')
        
        # Check for any inf values
        print("\nChecking for infinite values:")
        for col in ['ma13', 'ma45', 'dif', 'dea', 'macd', 'k', 'd', 'j', 'rsi6', 'rsi12', 'rsi24']:
            if col in df_reset.columns:
                inf_count = np.isinf(df_reset[col]).sum()
                if inf_count > 0:
                    print(f"{col}: {inf_count} infinite values")
        
        # Test the to_dict conversion
        try:
            indicator_data = df_reset[['date', 'ma13', 'ma45', 'dif', 'dea', 'macd', 'k', 'd', 'j', 'rsi6', 'rsi12', 'rsi24']].to_dict('records')
            print(f"\nSuccessfully converted to dict. Length: {len(indicator_data)}")
            
            # Check first record
            if indicator_data:
                first_record = indicator_data[0]
                print(f"First record: {first_record}")
                
                # Check for any None values in first record
                none_keys = [k for k, v in first_record.items() if v is None]
                if none_keys:
                    print(f"None values in first record: {none_keys}")
                    
        except Exception as e:
            print(f"Error in to_dict conversion: {e}")
            
    except Exception as e:
        import traceback
        print(f"Check failed: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    check_dataframe_nan()