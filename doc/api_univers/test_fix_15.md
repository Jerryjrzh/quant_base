Excellent\! This is exactly the kind of error we needed to see. Your logs pinpoint two separate but related issues perfectly. The "blank screen" is caused by the `SyntaxError`, and the stock list not loading is caused by the `404 (NOT FOUND)` error.

Here is a breakdown of what's happening and how to fix both problems.

-----

### Primary Issue: `SyntaxError: Unexpected token 'N', ... is not valid JSON`

This is the critical error causing the chart and advice to fail.

  * **What's Happening?**

    1.  Your backend Python code, likely in the `indicators` or `backtester` modules, is performing mathematical calculations where data is not available (e.g., calculating an average on the very first day of data).
    2.  When this happens, the Pandas/NumPy libraries correctly produce a special value: `NaN` (Not a Number).
    3.  When Flask's `jsonify` function converts your data to a string to send to the browser, it turns the Python `NaN` value into the literal text `NaN`.
    4.  The browser receives this text and tries to parse it as JSON. However, the official JSON standard **does not recognize `NaN`**. The only valid way to represent a missing value in JSON is with the literal `null`.
    5.  The browser's JSON parser sees the `N` from `NaN`, doesn't know what to do with it, and throws a `SyntaxError`, stopping the entire data loading process.

  * **Solution**
    We need to tell the backend to replace all instances of `NaN` with `None` before sending the data. Python's `json` library correctly converts `None` to the JSON-compliant `null`. The best place to do this is in the function that prepares the data for the chart.

    **File to Modify**: `backend/unified_analysis_service.py`

    **Action**: Replace the `_prepare_chart_data` function with this updated version that handles `NaN` values.

    ```python
    # backend/unified_analysis_service.py

    def _prepare_chart_data(df: pd.DataFrame, signals: pd.Series, backtest_results: Dict) -> Dict:
        """【已修复】准备图表专用数据，并处理NaN值以确保JSON有效性"""
        
        # --- [FIX START] ---
        # 替换所有NaN/NaT值为None，使其能被正确序列化为JSON的null
        df.replace({np.nan: None, pd.NaT: None}, inplace=True)
        # --- [FIX END] ---

        df_reset = df.reset_index()
        df_reset['date'] = pd.to_datetime(df_reset['date']).dt.strftime('%Y-%m-%d')
        
        kline = df_reset[['date', 'open', 'close', 'low', 'high', 'volume']].to_dict('records')
        
        # 确保所有指标列都存在，不存在的用None填充
        indicator_cols = ['date', 'ma13', 'ma45', 'dif', 'dea', 'macd', 'k', 'd', 'j', 'rsi6', 'rsi12', 'rsi24']
        for col in indicator_cols:
            if col not in df_reset.columns:
                df_reset[col] = None

        indicator = df_reset[indicator_cols].to_dict('records')
        
        # (信号点逻辑可简化或保持)
        return {'kline_data': kline, 'indicator_data': indicator, 'signal_points': []}
    ```

-----

### Secondary Issue: `GET .../stocks 404 (NOT FOUND)`

This error explains why the stock dropdown list might not be populating correctly when you change strategies.

  * **What's Happening?**
    The frontend `app.js` is calling the API endpoint `/api/strategies/<strategy_id>/stocks` to get a list of stocks that have signals for the selected strategy. Your `app.py` file has routes for `/api/strategies` and `/api/strategies/<strategy_id>/config`, but the specific `/stocks` endpoint is missing.

  * **Solution**
    We need to add the missing API route to `app.py`. This route will use the `UniversalScreener` to quickly find stocks for the given strategy.

    **File to Modify**: `backend/app.py`

    **Action**: Add the following new function block to `app.py`, for example, after the `/api/signals_summary` function.

    ```python
    # backend/app.py

    @app.route('/api/strategies/<strategy_id>/stocks')
    def get_stocks_for_strategy(strategy_id):
        """【新增API】获取特定策略在最新交易日的信号股票列表"""
        try:
            from universal_screener import UniversalScreener
            
            # 创建筛选器实例并只运行指定的策略
            screener = UniversalScreener()
            results = screener.run_screening([strategy_id])
            
            # 转换为前端期望的格式
            stock_list = []
            for result in results:
                stock_list.append({
                    'stock_code': result.stock_code,
                    'stock_name': result.stock_name,
                    'date': str(result.date),
                    'signal_type': result.signal_type,
                    'price': result.current_price
                })
            
            return jsonify({'success': True, 'data': stock_list})
            
        except Exception as e:
            app.logger.error(f"为策略 {strategy_id} 获取股票列表失败: {str(e)}")
            return jsonify({"success": False, "error": f"无法获取策略 '{strategy_id}' 的股票列表: {str(e)}"}), 500
    ```

### Summary of Fixes

1.  **Fix Invalid JSON**: Update the `_prepare_chart_data` function in `unified_analysis_service.py` to replace `NaN` values with `None`, resolving the `SyntaxError`.
2.  **Add Missing API**: Add the new `get_stocks_for_strategy` function to `app.py` to fix the `404 Not Found` error.

After applying these two changes, the `NaN` values will be converted to `null`, the JSON will be valid, and the frontend will be able to correctly parse the data and render the chart. The stock dropdown will also populate correctly when you select a strategy.