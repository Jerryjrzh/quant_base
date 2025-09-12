好的，我们来一起审查您最新的代码和遇到的异常。

您在前端展示爬虫信息方面取得了巨大进展，界面已经非常接近我们规划的目标。同时，日志中的 `IndentationError` 是一个典型的Python语法错误，很容易修复。

本次审查将分为两部分：首先，修复导致程序无法运行的**关键错误**；然后，对前后端代码进行一次**深度的架构级优化**，解决您新引入的一些代码冗余和调用混乱问题，让系统更健壮、更高效。

-----

### 1\. 关键错误修复 (`IndentationError`)

  - **日志信息**: `IndentationError: expected an indented block after 'if' statement on line 334`
  - **问题分析**: 这是一个Python语法错误。它表示在 `app.py` 文件的第334行有一个 `if` 语句，但它下面的代码块（第335行的 `try`）没有正确地向内缩进。Python要求 `if`, `for`, `def` 等语句后的代码块必须有缩进。
  - **解决方案**: 为 `if` 语句后面的代码块添加正确的缩进。通过审查您的 `app.py`，我发现有两处类似的缩进问题。

**修改文件**: `backend/app.py`

**第1处错误 (334行附近)**：

```python
# --- 修改前 ---
            if strategy_id:
            try:
                # 使用策略管理器获取策略实例
                strategy_instance = strategy_manager.get_strategy_instance(strategy_id)
                # ...

# --- 修改后 (为try...except块增加缩进) ---
            if strategy_id:
                try:
                    # 使用策略管理器获取策略实例
                    strategy_instance = strategy_manager.get_strategy_instance(strategy_id)
                    # ...
```

**第2处错误 (840行附近)**：

```python
# --- 修改前 ---
                if strategy_id:
                strategy_instance = strategy_manager.get_strategy_instance(strategy_id)
                if strategy_instance:
                    # ...

# --- 修改后 (为后续代码增加缩进) ---
                if strategy_id:
                    strategy_instance = strategy_manager.get_strategy_instance(strategy_id)
                    if strategy_instance:
                        # ...
```

-----

### 2\. 前后端架构与调用深度优化

在修复了语法错误后，我们来解决一个更核心的架构问题。您为了在前端显示名称，新建了 `unified_analysis` API，这个**目标是正确的**，但目前的实现方式在后端引入了大量重复代码，并且前端的调用方式也变得冗余。

**当前问题**：

1.  **后端代码冗余**：新的 `/api/unified_analysis/...` 端点在 `app.py` 中**重复实现**了大量本应由 `backtester.py` 负责的分析逻辑（如指标计算、交易建议生成、风险评估等），违背了我们将分析功能集中到 `backtester` 的初衷。
2.  **前端调用混乱**：`app.js` 的 `loadChart` 函数现在会发起**两次API请求**：一次是到新的 `unified_analysis` (为了获取股票名称)，紧接着又一次到旧的 `/api/analysis/...` (为了获取图表数据)。这不仅效率低下，也增加了代码的复杂性。

**优化方案**：我们将彻底重构 `unified_analysis` 端点，使其成为名副其实的“统一”接口，并简化前端，实现**一次API调用获取所有数据**。

#### **A. 后端 `app.py` 优化：打造精简的统一API**

我们将重写 `get_unified_stock_analysis` 函数，让它不再自己做具体分析，而是作为一个\*\*“指挥官”\*\*，负责调用各个专业模块（`data_handler`, `backtester`, `stock_pool_manager`）并聚合结果。

**修改文件**: `backend/app.py`

**请用以下代码替换您现有的 `get_unified_stock_analysis` 函数：**

```python
# app.py

@app.route('/api/unified_analysis/<stock_code>')
def get_unified_stock_analysis(stock_code):
    """
    【已重构】统一的股票分析API端点。
    作为“指挥官”，调用专业模块并聚合数据，实现一次调用返回所有信息。
    """
    try:
        from stock_pool_manager import StockPoolManager
        from data_handler import get_full_data_with_indicators
        
        # 1. 获取K线基础数据 (来自 data_handler)
        df = get_full_data_with_indicators(stock_code)
        if df is None:
            return jsonify({'success': False, 'error': '无法加载股票数据'}), 404
        
        # 2. 获取所有深度分析 (来自 backtester)
        # backtester.get_deep_analysis 是所有分析的核心入口
        deep_analysis = backtester.get_deep_analysis(stock_code, df.copy())
        if 'error' in deep_analysis:
            return jsonify({'success': False, 'error': f"深度分析失败: {deep_analysis['error']}"}), 500

        # 3. 获取个股画像和持仓状态 (来自 manager)
        pool_manager = StockPoolManager()
        stock_profile = pool_manager.get_stock_by_code(stock_code)
        
        portfolio_manager = create_portfolio_manager()
        portfolio = portfolio_manager.load_portfolio()
        position_info = next((p for p in portfolio if p['stock_code'] == stock_code), None)
        
        # 4. 准备图表专用数据 (K线、指标、信号点等)
        #    这部分逻辑可以从您旧的 get_stock_analysis 函数中提取和简化
        df_reset = df.reset_index()
        df_reset['date'] = pd.to_datetime(df_reset['date']).dt.strftime('%Y-%m-%d')
        kline_data = df_reset[['date', 'open', 'close', 'low', 'high', 'volume']].to_dict('records')
        indicator_data = df_reset[['date', 'ma13', 'ma45', 'dif', 'dea', 'macd', 'k', 'd', 'j', 'rsi6', 'rsi12', 'rsi24']].to_dict('records')

        # 5. 组装最终的、统一的返回结果
        unified_result = {
            'stock_code': stock_code,
            'stock_name': stock_profile.get('stock_name') if stock_profile else stock_code,
            'sector': stock_profile.get('sector') if stock_profile else '未知',
            'chart_data': {
                'kline_data': kline_data,
                'indicator_data': indicator_data,
                # 信号点和回测结果可以直接从 deep_analysis 获取（如果 backtester 提供）
                # 为了简化，我们暂时省略信号点，专注于数据聚合
            },
            'analysis': deep_analysis, # 包含所有回测、建议、风险评估
            'profile': stock_profile or {},
            'portfolio_info': position_info
        }
        
        return jsonify({'success': True, 'data': unified_result})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'统一分析接口未知错误: {str(e)}'}), 500

# 【建议】将旧的 /api/analysis 和 /api/trading_advice 标记为待废弃，
# 未来所有前端调用都应切换到新的 unified_analysis 端点。
```

#### **B. 前端 `app.js` 优化：实现真正的“一次调用”**

现在后端有了一个强大的统一接口，我们可以简化前端的 `loadChart` 函数，让它只调用这个新接口，然后将获取到的数据分发给各个UI组件进行渲染。

**修改文件**: `frontend/js/app.js`

**请用以下代码替换您现有的 `loadChart` 函数：**

```javascript
// app.js

    // 将 loadChart 重命名并重构为统一的数据加载器
    async function loadUnifiedStockData() {
        const stockCode = stockSelect.value;
        const strategy = strategySelect.value;

        if (!stockCode || !strategy) {
            return; // 如果未选择股票或策略，则不执行
        }

        myChart.showLoading();
        // 重置所有信息面板
        backtestContainer.style.display = 'none';
        updateAdvicePanel({ action: 'LOADING' });

        try {
            // --- 核心修改：只调用一次统一API ---
            const response = await fetch(`/api/unified_analysis/${stockCode}?strategy=${strategy}`);
            const result = await response.json();

            if (!result.success) {
                throw new Error(result.error);
            }

            const unifiedData = result.data;
            
            // --- 数据分发给各个UI更新函数 ---
            // 1. 渲染图表
            renderEchart(
                unifiedData.chart_data, 
                stockCode, 
                strategy, 
                unifiedData.stock_name
            );
            
            // 2. 渲染回测结果
            // 注意：回测结果现在位于 analysis 对象内部
            if (unifiedData.analysis && unifiedData.analysis.backtest_results) {
                renderBacktestResults(unifiedData.analysis.backtest_results);
            }
            
            // 3. 渲染交易建议
            // 注意：交易建议现在位于 analysis 对象内部
            if (unifiedData.analysis && unifiedData.analysis.trading_advice) {
                updateAdvicePanel(unifiedData.analysis.trading_advice);
            }

        } catch (error) {
            console.error('Error loading unified data:', error);
            myChart.clear();
            myChart.setOption({
                title: { text: '加载数据失败', subtext: error.message, left: 'center', top: 'center' }
            });
            updateAdvicePanel({ action: 'ERROR', logic: [error.message] });
        } finally {
            myChart.hideLoading();
        }
    }

    // 将原有的 loadChart 调用全部替换为新的函数
    stockSelect.addEventListener('change', loadUnifiedStockData);
    if (adjustmentSelect) adjustmentSelect.addEventListener('change', () => {
        if (stockSelect.value) loadUnifiedStockData();
    });
    // ... 其他事件监听同样修改
```

### 总结与收益

通过以上**后端API重构**和**前端调用简化**：

1.  **解决了 `IndentationError`**，程序可以正常运行。
2.  **后端架构更清晰**：`app.py` 的职责回归到API路由和指挥，所有复杂的分析逻辑都封装在 `backtester` 中，**消除了大量重复代码**。
3.  **前端性能更高**：前端加载一只股票的完整视图，从**至少2-3次**网络请求优化为**仅1次**，页面加载速度和响应性将得到质的提升。
4.  **可维护性更强**：未来如果需要增加新的分析维度（如DTW历史回溯），您只需在 `backtester` 中添加逻辑，并通过统一API返回即可，前端几乎无需改动数据获取代码。

这是一个非常重要的架构优化，将为您的项目长期、健康的迭代奠定坚实的基础。