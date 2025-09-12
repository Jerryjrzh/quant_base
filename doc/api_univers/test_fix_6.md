好的，我们来详细审查一下。您观察得非常准确，后端爬虫获取的股票名称、板块等关键信息目前还没有在前端完全展示出来。您提供的截图清晰地指出了需要优化的区域。

这是一个非常典型的从“功能可用”到“体验优秀”的迭代过程。好消息是，根据我们之前的重构，后端的数据链路已经准备好了，我们只需要在前端进行“最后一公里”的开发即可。

以下是具体的修改方案，涵盖了所有需要调整的地方。

-----

### **第1步：后端数据确认 (`data_enricher.py`)**

首先，我们需要确保 `data_enricher.py` 能够稳定地调用爬虫并将名称和板块信息存入数据库。您已经有了爬虫脚本，我们只需确保在丰富器中正确调用即可。

**文件**: `backend/data_enricher.py`
**函数**: `enrich_single_stock`

**确认与建议**：请确保此函数中包含了调用 `stock_cpbd_em` (操盘必读) 或其他能获取股票名称/板块的爬虫的逻辑。如果没有，请添加以下代码块：

```python
# data_enricher.py -> enrich_single_stock()

# ... (在try块内，可以放在获取龙虎榜、分红送配等逻辑之后)
            # 优先级 4: 操盘必读 (获取名称和板块)
            try:
                from craw import stock_cpbd_em
                # 操盘必读需要不带市场前缀的代码
                code_no_prefix = stock_code.replace('sh', '').replace('sz', '')
                cpbd_df = stock_cpbd_em.stock_cpbd_em(symbol=code_no_prefix)
                if cpbd_df is not None and not cpbd_df.empty:
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

-----

### **第2步：前端界面与逻辑修改**

这是本次优化的核心。我们将逐一修改主图表、持仓管理、核心池和持仓详情，让它们都显示更丰富的信息。

#### **2.1 主图表标题优化**

[cite\_start]**目标**：将图表标题从 `sh603192 sh603192 - 策略分析` 优化为 `sh603192 九州药业 - 策略分析` [cite: 1]。

**修改文件**: `frontend/js/app.js`
**函数**: `loadUnifiedStockData` 和 `renderEchart`

```javascript
// app.js

    // 1. 在 loadUnifiedStockData 函数中，将名称传递给 renderEchart
    async function loadUnifiedStockData(stockCode) {
        // ... (fetch 和 unifiedData 的逻辑保持不变)

        // --- 新增：从返回的数据中获取股票名称 ---
        const stockName = unifiedData.profile_data?.stock_name || stockCode;
        
        // --- 修改：将 stockName 传递给渲染函数 ---
        renderEchart(unifiedData.chart_data, stockCode, strategy, stockName);
        
        // ... (其他数据分发逻辑不变)
    }

    // 2. 修改 renderEchart 函数以接收和使用 stockName
    function renderEchart(chartData, stockCode, strategy, stockName) { // 新增 stockName 参数
        // ... (其他代码不变)
        
        // --- 修改标题 ---
        const option = {
            title: {
                // 使用 stockName 替代重复的 stockCode
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

#### **2.2 持仓管理表格增强**

[cite\_start]**目标**：为持仓管理表格增加“股票名称”和“板块/概念”列，并填充数据 [cite: 2]。

**修改文件**: `frontend/index.html`

```html
<table class="portfolio-table" id="portfolio-scan-table">
    <thead>
        <tr>
            <th class="sortable" data-column="stock_code">代码/名称</th>
            <th class="sortable" data-column="sector">板块概念</th> <th class="sortable" data-column="purchase_price">购买价格</th>
            </tr>
    </thead>
    <tbody id="portfolio-scan-tbody"></tbody>
</table>
```

**修改文件**: `frontend/js/app.js`
**函数**: `displayScanResults`

```javascript
// app.js -> displayScanResults (持仓扫描结果)

    function displayScanResults(results) {
        // ... (函数开头的HTML和汇总部分不变)

        results.positions.forEach(position => {
            // ... (其他变量定义不变)

            // --- 修改表格行 (tbody) 的内容 ---
            html += `
                <tr data-stock-code="${position.stock_code}" ...>
                    <td>
                        <a href="#" class="stock-code-link" onclick="showPositionDetailModal('${position.stock_code}')">
                            ${position.stock_code}<br>
                            <span style="font-size:0.8em; color:#6c757d;">${position.stock_name || ''}</span>
                        </a>
                    </td>
                    <td style="font-size:0.85em; max-width: 150px; white-space: normal;">
                        ${position.sector || '--'}
                    </td>
                    <td>¥${position.purchase_price.toFixed(2)}</td>
                    <td>¥${position.current_price.toFixed(2)}</td>
                    <td class="${profitClass}">${profitLoss.toFixed(2)}%</td>
                    </tr>
            `;
        });
        // ... (函数结尾的HTML和事件监听不变)
    }
```

#### **2.3 核心池表格增强**

**目标**：与持仓管理类似，为核心池表格也增加名称和板块信息。

**修改文件**: `frontend/js/app.js`
**函数**: `displayCorePoolData`

```javascript
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
                    <td><button onclick="removeFromCorePool('${stock.stock_code}')" ...>删除</button></td>
                </tr>
            `;
        });
        html += '</tbody></table>';
        listContainer.innerHTML = html;
    }
```

#### **2.4 持仓详情弹窗增强**

[cite\_start]**目标**：在点击持仓后的详情弹窗中，也加入名称和板块信息 [cite: 3]。

**修改文件**: `frontend/js/app.js`
**函数**: `displayPositionDetail`

```javascript
// app.js -> displayPositionDetail

    function displayPositionDetail(analysis) {
        // ... (函数开头的HTML和基本信息部分)
        let html = `
            <div class="position-detail-grid">
                <div class="detail-section">
                    <h4>基本信息</h4>
                    <div class="detail-item">
                        <span class="detail-label">股票代码:</span>
                        <span class="detail-value">${analysis.stock_code}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">股票名称:</span>
                        <span class="detail-value">${analysis.stock_name || '--'}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">所属板块:</span>
                        <span class="detail-value" style="text-align: right;">${analysis.sector || '--'}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">购买价格:</span>
                        <span class="detail-value">¥${analysis.purchase_price.toFixed(2)}</span>
                    </div>
        `;
        // ... (后续的HTML逻辑保持不变)
    }
```

完成以上所有修改后，您的前端界面将能充分利用后端爬取的数据，为用户提供更丰富、更直观的分析体验。