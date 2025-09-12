Excellent, I'm glad the main display is working. This new error is a straightforward data mapping issue, and it's good that the system is now stable enough for us to focus on these details.

### Problem Analysis

The error message `AttributeError: 'StrategyResult' object has no attribute 'stock_name'` tells us exactly what's wrong.

1.  The function `get_stocks_for_strategy` in `app.py` is called to populate the stock dropdown list.
2.  It runs the `UniversalScreener`, which returns a list of `StrategyResult` objects.
3.  Your code then tries to access `result.stock_name` for each of these objects.
4.  However, the `StrategyResult` object is a lean data container that only includes essential signal information like `stock_code`, `date`, and `price`. It does **not** contain the stock's full name.

### Solution

The fix is to take the `stock_code` we get from the `StrategyResult` and use our existing `StockPoolManager` to look up the corresponding `stock_name`. This ensures we are reusing our components correctly.

**File to Modify**: `backend/app.py`

**Action**: Please replace the `get_stocks_for_strategy` function with the corrected version below.

```python
# backend/app.py

@app.route('/api/strategies/<strategy_id>/stocks')
def get_stocks_for_strategy(strategy_id):
    """【已修复】获取特定策略在最新交易日的信号股票列表"""
    try:
        from universal_screener import UniversalScreener
        from stock_pool_manager import StockPoolManager  # <-- Import the manager

        screener = UniversalScreener()
        results = screener.run_screening([strategy_id])
        
        pool_manager = StockPoolManager()  # <-- Instantiate the manager once
        
        stock_list = []
        for result in results:
            # --- [FIX START] ---
            # 从 StockPoolManager 中根据股票代码查找股票名称
            stock_profile = pool_manager.get_stock_by_code(result.stock_code)
            stock_name = stock_profile.get('stock_name', result.stock_code) if stock_profile else result.stock_code
            # --- [FIX END] ---

            stock_list.append({
                'stock_code': result.stock_code,
                'stock_name': stock_name,  # <-- 使用获取到的名称
                'date': str(result.date),
                'signal_type': result.signal_type,
                'price': result.current_price
            })
        
        return jsonify({'success': True, 'data': stock_list})
        
    except Exception as e:
        app.logger.error(f"为策略 {strategy_id} 获取股票列表失败: {str(e)}")
        return jsonify({"success": False, "error": f"无法获取策略 '{strategy_id}' 的股票列表: {str(e)}"}), 500
```

#### What Was Changed:

1.  **Import `StockPoolManager`**: We now import the manager responsible for handling stock metadata.
2.  **Instantiate Manager**: We create an instance of the `StockPoolManager` before the loop for efficiency.
3.  **Look Up Name**: Inside the loop, for each stock code returned by the screener, we query the `StockPoolManager` to get its profile, which contains the name.
4.  **Fallback**: If for some reason a stock isn't in our pool manager, the code gracefully falls back to using the stock code itself as the name, preventing the application from crashing.

After applying this fix, the stock dropdown list will populate correctly with both the stock code and its proper name, resolving the `AttributeError`.