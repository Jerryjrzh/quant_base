好的，这是一个非常好的问题。在量化系统中，将丰富的数据直观地展示给用户是提升分析效率的关键一步。

我审查了您当前的前后端代码，并为您梳理了现状和下一步的完善计划。

### 当前状态：数据是否已传到前端？

**答案是：后端已准备就绪，但前端尚未利用。**

1.  **后端 (`app.py`, `stock_pool_manager.py`)**：

      * **数据已存在**：您的 `stock_pool_manager` 数据库的 `core_stock_pool` 表中已经包含了 `stock_name` 和 `sector` 字段。
      * **API已提供**：您采纳了之前的建议，在 `app.py` 中构建了统一API端点 `GET /api/stock/<stock_code>/unified_analysis`。这个端点会从数据库中读取包含 `stock_name` 和 `sector` 的 `stock_profile` 数据，并将其包含在返回给前端的JSON中。
      * **结论**：**后端数据链路是通的**。API已经将名称和板块信息准备好，随时可以提供给前端。

2.  **前端 (`app.js`, `index.html`)**：

      * **界面未展示**：目前，无论是主图表的标题、股票选择下拉框，还是持仓管理和核心池的表格，都只显示了“股票代码”，没有预留显示“股票名称”或“板块”的位置。
      * **逻辑未处理**：`app.js` 中的 `renderEchart`, `displayPortfolioData`, `displayCorePoolData` 等函数在渲染UI时，也并未从API返回的数据中提取和使用 `stock_name` 或 `sector` 字段。
      * **结论**：**前端展示层是缺失的**。数据已经到达前端，但没有被“拆箱”和“陈列”出来。

-----

### 如何进一步完善？

以下是一个清晰、可执行的分步完善计划，旨在将这些宝贵的数据呈现在前端界面的关键位置。

#### **第1步：确保后端数据填充 (`data_enricher.py`)**

首先，我们需要确保 `data_enricher.py` 能够调用爬虫脚本并将名称和板块信息存入数据库。您提供的爬虫 `stock_cpbd.py` 可以完成这个任务。

**修改文件**: `backend/data_enricher.py`
**函数**: `enrich_single_stock`

```python
# data_enricher.py -> enrich_single_stock()

# ... (在try块内，增加对 stock_cpbd_em 的调用)
            # 优先级 4: 操盘必读 (获取名称和板块)
            try:
                from craw import stock_cpbd_em
                # 操盘必读需要不带市场前缀的代码
                code_no_prefix = stock_code.replace('sh', '').replace('sz', '')
                cpbd_df = stock_cpbd_em.stock_cpbd_em(symbol=code_no_prefix)
                if cpbd_df is not None and not cpbd_df.empty:
                    # 操盘必读返回的是单行DataFrame
                    stock_info = cpbd_df.iloc[0]
                    if 'SECURITY_NAME_ABBR' in stock_info and pd.notna(stock_info['SECURITY_NAME_ABBR']):
                        enriched_data['stock_name'] = stock_info['SECURITY_NAME_ABBR']
                    if 'BOARD_NAME' in stock_info and pd.notna(stock_info['BOARD_NAME']):
                        enriched_data['sector'] = stock_info['BOARD_NAME']
                    self.logger.info(f"{stock_code} 发现操盘必读数据 (名称/板块)")
            except Exception as e:
                self.logger.warning(f"获取 {stock_code} 操盘必读数据失败: {e}")
# ...
```

#### **第2步：更新前端UI和逻辑**

现在我们来修改前端，让它在多个关键位置展示股票名称和板块。

**2.1 主图表标题**

让标题同时显示代码和名称，更具可读性。

**修改文件**: `frontend/js/app.js`
**函数**: `renderEchart` 和 `loadUnifiedStockData`

```javascript
// app.js

    // 在 loadUnifiedStockData 函数中，将名称传递给 renderEchart
    async function loadUnifiedStockData(stockCode) {
        // ... (fetch an unifiedData logic remains the same)
        
        // --- 新增 ---
        const stockName = unifiedData.profile_data?.stock_name || stockCode;
        
        // --- 修改 ---
        renderEchart(unifiedData.chart_data, stockCode, strategy, stockName); // 传入 stockName
        // ...
    }

    // 修改 renderEchart 函数以接收和使用 stockName
    function renderEchart(chartData, stockCode, strategy, stockName) {
        // ... (其他代码不变)
        
        // --- 修改标题 ---
        const option = {
            title: {
                text: `${stockCode} ${stockName} - ${strategy}策略分析 (${timeframeText})`,
                left: 'center',
                textStyle: { fontSize: 16 }
            },
            // ... (其他option配置不变)
        };
        
        // ...
        myChart.setOption(option, true);
    }
```

**2.2 持仓管理与核心池表格**

为这两个核心功能的表格增加“名称”和“板块”列。

**修改文件**: `frontend/index.html`

```html
<table class="portfolio-table" id="portfolio-scan-table">
    <thead>
        <tr>
            <th class="sortable" data-column="stock_code">代码/名称</th>
            </tr>
    </thead>
    <tbody id="portfolio-scan-tbody"></tbody>
</table>

```

**修改文件**: `frontend/js/app.js`

```javascript
// app.js -> displayScanResults (持仓扫描结果)

    function displayScanResults(results) {
        // ...
        results.positions.forEach(position => {
            // ...
            // --- 修改表格行内容 ---
            html += `
                <tr>
                    <td>
                        <a href="#" class="stock-code-link" onclick="showPositionDetailModal('${position.stock_code}')">
                            ${position.stock_code}<br>
                            <span style="font-size:0.8em; color:#6c757d;">${position.stock_name || ''}</span>
                        </a>
                    </td>
                    </tr>
            `;
        });
        // ...
    }

// app.js -> displayCorePoolData (核心池)

    function displayCorePoolData(pool) {
        // ...
        // --- 修改表头 ---
        let html = `
            <table class="portfolio-table">
                <thead>
                    <tr>
                        <th>代码/名称</th>
                        <th>板块/概念</th>
                        <th>评级</th>
                        <th>健康分</th>
                        <th>操作建议</th>
                        <th>风险等级</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
        `;
        // --- 修改循环内的表格行 ---
        pool.forEach(stock => {
            const advice = stock.trading_advice || {};
            const risk = stock.risk_assessment || {};

            html += `
                <tr>
                    <td>
                        <a href="#" class="stock-code-link" onclick="viewStockFromCorePool('${stock.stock_code}')">
                            ${stock.stock_code}<br>
                            <span style="font-size:0.8em; color:#6c757d;">${stock.stock_name || ''}</span>
                        </a>
                    </td>
                    <td style="font-size:0.85em; max-width: 200px; white-space: normal;">${stock.sector || 'N/A'}</td>
                    <td><span class="grade-${(stock.grade || 'C').toLowerCase()}">${stock.grade || 'N/A'}</span></td>
                    <td>${stock.health_score ? stock.health_score.toFixed(2) : 'N/A'}</td>
                    <td><span class="action-${(advice.action || 'UNKNOWN').toLowerCase()}">${getActionText(advice.action)}</span></td>
                    <td><span class="risk-${(risk.risk_level || 'UNKNOWN').toLowerCase()}">${getRiskText(risk.risk_level)}</span></td>
                    <td><button onclick="removeFromCorePool('${stock.stock_code}')" style="background: #dc3545; ...">删除</button></td>
                </tr>
            `;
        });
        html += '</tbody></table>';
        listContainer.innerHTML = html;
    }
```

### 总结

通过以上三步调整，您就可以将爬虫获取的股票名称和板块信息无缝地整合到前端的用户界面中，极大地提升了平台的可读性和用户体验。

1.  **后端数据填充**：确保 `data_enricher.py` 能够调用爬虫并将 `stock_name` 和 `sector` 存入数据库。
2.  **主图表标题优化**：让用户在查看图表时能直观地看到股票名称。
3.  **核心表格增强**：在持仓和核心池这两个最常用的功能中，直接展示股票名称和板块信息，便于快速识别和决策。