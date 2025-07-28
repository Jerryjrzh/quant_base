document.addEventListener('DOMContentLoaded', function () {
    // --- 获取所有需要的DOM元素 ---
    const stockSelect = document.getElementById('stock-select');
    const strategySelect = document.getElementById('strategy-select');
    const chartContainer = document.getElementById('chart-container');
    const myChart = echarts.init(chartContainer);

    // 回测结果元素
    const backtestContainer = document.getElementById('backtest-results');
    const totalSignalsEl = document.getElementById('total-signals');
    const winRateEl = document.getElementById('win-rate');
    const avgMaxProfitEl = document.getElementById('avg-max-profit');
    const avgMaxDrawdownEl = document.getElementById('avg-max-drawdown');
    const avgDaysToPeakEl = document.getElementById('avg-days-to-peak');
    const stateStatsContent = document.getElementById('state-stats-content');
    
    // 多周期分析相关元素
    const multiTimeframeBtn = document.getElementById('multi-timeframe-btn');
    const multiTimeframeModal = document.getElementById('multi-timeframe-modal');
    const multiCloseModal = document.getElementById('multi-close');
    const timeframeSelect = document.getElementById('timeframe-select');

    function populateStockList() {
        const strategy = strategySelect.value;
        fetch(`/api/signals_summary?strategy=${strategy}`)
            .then(response => {
                if (!response.ok) throw new Error(`无法加载信号文件，请先运行 screener.py (策略: ${strategy})`);
                return response.json();
            })
            .then(data => {
                stockSelect.innerHTML = '<option value="">请选择股票</option>';
                if (data.length === 0) {
                    stockSelect.innerHTML = `<option value="">策略 ${strategy} 今日无信号</option>`;
                }
                data.forEach(signal => {
                    const option = document.createElement('option');
                    option.value = signal.stock_code;
                    option.textContent = `${signal.stock_code} (${signal.date})`;
                    stockSelect.appendChild(option);
                });
            })
            .catch(error => {
                console.error('Error fetching signal summary:', error);
                stockSelect.innerHTML = `<option value="">${error.message}</option>`;
            });
    }

    stockSelect.addEventListener('change', loadChart);
    strategySelect.addEventListener('change', () => {
        populateStockList();
        myChart.clear();
        backtestContainer.style.display = 'none';
    });

    function loadChart() {
        const stockCode = stockSelect.value;
        const strategy = strategySelect.value;
        if (!stockCode) return;

        myChart.showLoading();
        backtestContainer.style.display = 'none';
        
        // 显示交易建议面板
        const advicePanel = document.getElementById('trading-advice-panel');
        if (advicePanel) {
            advicePanel.style.display = 'block';
            loadTradingAdvice(stockCode, strategy);
        }

        fetch(`http://127.0.0.1:5000/api/analysis/${stockCode}?strategy=${strategy}`)
            .then(response => response.json())
            .then(chartData => {
                myChart.hideLoading();

                // 检查是否返回了错误信息
                if (chartData.error) {
                    throw new Error(chartData.error);
                }

                // 检查必要的数据是否存在
                if (!chartData.kline_data || !chartData.indicator_data) {
                    throw new Error('数据格式不正确：缺少K线或指标数据');
                }

                const backtest = chartData.backtest_results;
                if (backtest && backtest.total_signals > 0) {
                    // 更新基本统计信息
                    totalSignalsEl.textContent = backtest.total_signals;
                    winRateEl.textContent = backtest.win_rate;
                    avgMaxProfitEl.textContent = backtest.avg_max_profit;
                    avgMaxDrawdownEl.textContent = backtest.avg_max_drawdown || 'N/A';
                    avgDaysToPeakEl.textContent = backtest.avg_days_to_peak;

                    // 更新各状态统计信息
                    if (backtest.state_statistics && stateStatsContent) {
                        let stateStatsHtml = '<div class="state-stats-grid">';

                        for (const [state, stats] of Object.entries(backtest.state_statistics)) {
                            const stateColor = getStateColor(state);
                            stateStatsHtml += `
                                <div class="state-stat-item" style="border-left: 4px solid ${stateColor};">
                                    <div class="state-name">${state} 状态</div>
                                    <div class="state-details">
                                        <span>数量: ${stats.count}</span>
                                        <span>胜率: ${stats.win_rate}</span>
                                        <span>收益: ${stats.avg_max_profit}</span>
                                        <span>回撤: ${stats.avg_max_drawdown}</span>
                                        <span>天数: ${stats.avg_days_to_peak}</span>
                                    </div>
                                </div>
                            `;
                        }

                        stateStatsHtml += '</div>';
                        stateStatsContent.innerHTML = stateStatsHtml;
                    }

                    backtestContainer.style.display = 'block';
                }

                // 辅助函数：获取状态对应的颜色
                function getStateColor(state) {
                    switch (state) {
                        case 'PRE': return '#f5b041';
                        case 'MID': return '#e74c3c';
                        case 'POST': return '#3498db';
                        default: return '#95a5a6';
                    }
                }

                // --- ECharts 渲染逻辑 ---
                const dates = chartData.kline_data.map(item => item.date);
                const kline = chartData.kline_data.map(item => [item.open, item.close, item.low, item.high]);
                const volumes = chartData.kline_data.map((item, idx) => [idx, item.volume, item.open > item.close ? -1 : 1]);
                const macdBar = chartData.indicator_data.map(item => (item.dif && item.dea) ? item.dif - item.dea : null);

                const markPoints = (chartData.signal_points || []).map(p => {
                    let symbol, color, symbolSize = 12;

                    // 安全检查 state 属性
                    const state = p.state || '';
                    const originalState = p.original_state || p.state || '';

                    // 检查是否有成功/失败状态
                    if (state.includes('_SUCCESS')) {
                        symbol = 'circle';
                        color = '#27ae60'; // 绿色表示成功
                        symbolSize = 10;
                    } else if (state.includes('_FAIL')) {
                        // 使用简单的X符号代替复杂的SVG路径
                        symbol = 'path://M14.59,8L12,10.59L9.41,8L8,9.41L10.59,12L8,14.59L9.41,16L12,13.41L14.59,16L16,14.59L13.41,12L16,9.41L14.59,8Z';
                        color = '#2c3e50'; // 黑色表示失败
                        symbolSize = 14;
                    } else {
                        // 原有的状态逻辑
                        switch (originalState) {
                            case 'PRE':
                                symbol = 'circle'; color = '#f5b041'; symbolSize = 8; break;
                            case 'POST':
                                symbol = 'circle'; color = '#3498db'; symbolSize = 8; break;
                            case 'MID':
                            default:
                                symbol = 'arrow'; color = '#e74c3c'; symbolSize = 15; break;
                        }
                    }

                    return {
                        coord: [p.date, p.price * 0.98],
                        symbol: symbol,
                        symbolSize: symbolSize,
                        itemStyle: { color: color }
                    };
                });

                const option = {
                    animation: false,
                    title: { text: `${stockCode} - ${strategy} 策略复盘`, left: 'center' },
                    axisPointer: { link: { xAxisIndex: 'all' }, label: { backgroundColor: '#777' } },
                    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
                    grid: [
                        { left: '10%', right: '8%', height: '45%' }, 
                        { left: '10%', right: '8%', top: '58%', height: '10%' },
                        { left: '10%', right: '8%', top: '71%', height: '10%' }, 
                        { left: '10%', right: '8%', top: '84%', height: '10%' },
                        { left: '10%', right: '8%', top: '97%', height: '10%' }
                    ],
                    xAxis: [
                        { type: 'category', data: dates, scale: true, boundaryGap: false, axisLine: { onZero: false }, splitLine: { show: false }, axisLabel: { show: false } },
                        { type: 'category', data: dates, scale: true, gridIndex: 1, boundaryGap: false, axisLine: { onZero: false }, axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false } },
                        { type: 'category', data: dates, scale: true, gridIndex: 2, boundaryGap: false, axisLine: { onZero: false }, axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false } },
                        { type: 'category', data: dates, scale: true, gridIndex: 3, boundaryGap: false, axisLine: { onZero: false }, axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false } },
                        { type: 'category', data: dates, scale: true, gridIndex: 4, boundaryGap: false, axisLine: { onZero: false }, axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: true } }
                    ],
                    yAxis: [
                        { scale: true, splitArea: { show: true } }, 
                        { scale: true, gridIndex: 1, axisLabel: { show: false }, axisLine: { show: false }, axisTick: { show: false }, splitLine: { show: false } },
                        { scale: true, gridIndex: 2, axisLabel: { show: false }, axisLine: { show: false }, axisTick: { show: false }, splitLine: { show: false } },
                        { scale: true, gridIndex: 3, axisLabel: { show: false }, axisLine: { show: false }, axisTick: { show: false }, splitLine: { show: false } },
                        { 
                            scale: false, 
                            gridIndex: 4, 
                            min: 0, 
                            max: 100, 
                            axisLabel: { show: true, fontSize: 10 }, 
                            axisLine: { show: true }, 
                            axisTick: { show: true }, 
                            splitLine: { show: true, lineStyle: { color: '#ddd', type: 'dashed' } }
                        }
                    ],
                    dataZoom: [
                        { type: 'inside', xAxisIndex: [0, 1, 2, 3, 4], start: 80, end: 100 },
                        { show: true, type: 'slider', xAxisIndex: [0, 1, 2, 3, 4], top: '110%', start: 80, end: 100 }
                    ],
                    series: [
                        { name: 'K线', type: 'candlestick', data: kline, itemStyle: { color: '#ec0000', color0: '#00da3c', borderColor: '#8A0000', borderColor0: '#008F28' }, markPoint: { data: markPoints } },
                        { name: 'MA13', type: 'line', data: chartData.indicator_data.map(i => i.ma13), smooth: true, showSymbol: false, lineStyle: { opacity: 0.8, width: 1 } },
                        { name: 'MA45', type: 'line', data: chartData.indicator_data.map(i => i.ma45), smooth: true, showSymbol: false, lineStyle: { opacity: 0.8, width: 1 } },
                        { name: '成交量', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: volumes, itemStyle: { color: ({ data }) => (data[2] === 1 ? '#ef232a' : '#14b143') } },
                        { name: 'DIF', type: 'line', xAxisIndex: 2, yAxisIndex: 2, data: chartData.indicator_data.map(i => i.dif), smooth: true, showSymbol: false, lineStyle: { width: 1 } },
                        { name: 'DEA', type: 'line', xAxisIndex: 2, yAxisIndex: 2, data: chartData.indicator_data.map(i => i.dea), smooth: true, showSymbol: false, lineStyle: { width: 1 } },
                        { name: 'MACD', type: 'bar', xAxisIndex: 2, yAxisIndex: 2, data: macdBar, itemStyle: { color: ({ data }) => (data >= 0 ? 'red' : 'green') } },
                        { name: 'K', type: 'line', xAxisIndex: 3, yAxisIndex: 3, data: chartData.indicator_data.map(i => i.k), smooth: true, showSymbol: false, lineStyle: { width: 1 } },
                        { name: 'D', type: 'line', xAxisIndex: 3, yAxisIndex: 3, data: chartData.indicator_data.map(i => i.d), smooth: true, showSymbol: false, lineStyle: { width: 1 } },
                        { name: 'J', type: 'line', xAxisIndex: 3, yAxisIndex: 3, data: chartData.indicator_data.map(i => i.j), smooth: true, showSymbol: false, lineStyle: { width: 1 } },
                        { 
                            name: 'RSI6', 
                            type: 'line', 
                            xAxisIndex: 4, 
                            yAxisIndex: 4, 
                            data: chartData.indicator_data.map(i => i.rsi6), 
                            smooth: true, 
                            showSymbol: false, 
                            lineStyle: { width: 2, color: '#ff6b35' }
                        },
                        { 
                            name: 'RSI12', 
                            type: 'line', 
                            xAxisIndex: 4, 
                            yAxisIndex: 4, 
                            data: chartData.indicator_data.map(i => i.rsi12), 
                            smooth: true, 
                            showSymbol: false, 
                            lineStyle: { width: 2, color: '#3498db' }
                        },
                        { 
                            name: 'RSI24', 
                            type: 'line', 
                            xAxisIndex: 4, 
                            yAxisIndex: 4, 
                            data: chartData.indicator_data.map(i => i.rsi24), 
                            smooth: true, 
                            showSymbol: false, 
                            lineStyle: { width: 2, color: '#9b59b6' },
                            markLine: {
                                silent: true,
                                data: [
                                    { yAxis: 20, lineStyle: { color: '#27ae60', type: 'dashed' } },
                                    { yAxis: 50, lineStyle: { color: '#95a5a6', type: 'solid' } },
                                    { yAxis: 80, lineStyle: { color: '#e74c3c', type: 'dashed' } }
                                ]
                            }
                        },
                    ]
                };
                myChart.setOption(option, true);
            })
            .catch(error => {
                myChart.hideLoading();
                console.error('Error fetching chart data:', error);
                chartContainer.innerHTML = '加载图表数据失败，请检查后端服务是否正常运行。';
            });
    }

    // 获取历史报告相关元素
    const historyBtn = document.getElementById('history-btn');
    const refreshBtn = document.getElementById('refresh-btn');
    const historyModal = document.getElementById('history-modal');
    const closeModal = document.querySelector('.close');
    const historyTabs = document.querySelectorAll('.history-tab');
    const historyContents = document.querySelectorAll('.history-content');
    
    // 深度扫描相关元素
    const deepScanSection = document.getElementById('deep-scan-section');
    const refreshDeepScanBtn = document.getElementById('refresh-deep-scan');
    const stockGrid = document.getElementById('stock-grid');
    const totalAnalyzedEl = document.getElementById('total-analyzed');
    const aGradeCountEl = document.getElementById('a-grade-count');
    const priceEvalCountEl = document.getElementById('price-eval-count');
    const buyRecCountEl = document.getElementById('buy-rec-count');
    
    // 深度扫描功能
    const deepScanBtn = document.getElementById('deep-scan-btn');
    if (deepScanBtn) deepScanBtn.addEventListener('click', triggerDeepScan);
    if (refreshDeepScanBtn) refreshDeepScanBtn.addEventListener('click', loadDeepScanResults);
    
    // 页面加载时检查是否有深度扫描结果
    loadDeepScanResults();
    
    // 交易建议面板相关元素和事件
    const adviceRefreshBtn = document.getElementById('advice-refresh');
    if (adviceRefreshBtn) {
        adviceRefreshBtn.addEventListener('click', () => {
            const stockCode = stockSelect.value;
            const strategy = strategySelect.value;
            if (stockCode) {
                loadTradingAdvice(stockCode, strategy);
            }
        });
    }
    
    function loadTradingAdvice(stockCode, strategy) {
        // 显示加载状态
        const actionRecommendation = document.getElementById('action-recommendation');
        const analysisLogic = document.getElementById('analysis-logic');
        
        if (actionRecommendation) {
            actionRecommendation.innerHTML = `
                <div class="action-text">分析中...</div>
                <div class="confidence-text">正在生成交易建议</div>
            `;
        }
        
        if (analysisLogic) {
            analysisLogic.innerHTML = `
                <div class="logic-item">
                    <span class="logic-icon">⏳</span>
                    <span>正在分析技术指标...</span>
                </div>
            `;
        }
        
        fetch(`/api/trading_advice/${stockCode}?strategy=${strategy}`)
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    throw new Error(data.error);
                }
                
                displayTradingAdvice(data);
            })
            .catch(error => {
                console.error('Error loading trading advice:', error);
                
                if (actionRecommendation) {
                    actionRecommendation.innerHTML = `
                        <div class="action-text">分析失败</div>
                        <div class="confidence-text">无法生成交易建议</div>
                    `;
                    actionRecommendation.className = 'action-recommendation avoid';
                }
                
                if (analysisLogic) {
                    analysisLogic.innerHTML = `
                        <div class="logic-item">
                            <span class="logic-icon">❌</span>
                            <span>交易建议加载失败: ${error.message}</span>
                        </div>
                    `;
                }
            });
    }
    
    function displayTradingAdvice(advice) {
        // 更新操作建议
        const actionRecommendation = document.getElementById('action-recommendation');
        if (actionRecommendation) {
            const actionTexts = {
                'BUY': '🟢 建议买入',
                'HOLD': '🟡 建议持有',
                'WATCH': '🟠 观察等待',
                'AVOID': '🔴 建议回避'
            };
            
            const actionText = actionTexts[advice.action] || advice.action;
            const confidencePercent = (advice.confidence * 100).toFixed(0);
            
            actionRecommendation.innerHTML = `
                <div class="action-text">${actionText}</div>
                <div class="confidence-text">置信度: ${confidencePercent}%</div>
            `;
            
            // 设置样式类
            actionRecommendation.className = `action-recommendation ${advice.action.toLowerCase()}`;
        }
        
        // 更新价格信息
        const currentPriceEl = document.getElementById('current-price');
        const entryPriceEl = document.getElementById('entry-price');
        const targetPriceEl = document.getElementById('target-price');
        const stopPriceEl = document.getElementById('stop-price');
        const resistanceLevelEl = document.getElementById('resistance-level');
        const supportLevelEl = document.getElementById('support-level');
        
        if (currentPriceEl) currentPriceEl.textContent = `¥${advice.current_price.toFixed(2)}`;
        if (entryPriceEl) entryPriceEl.textContent = `¥${advice.entry_price.toFixed(2)}`;
        if (targetPriceEl) targetPriceEl.textContent = `¥${advice.target_price.toFixed(2)}`;
        if (stopPriceEl) stopPriceEl.textContent = `¥${advice.stop_price.toFixed(2)}`;
        if (resistanceLevelEl) resistanceLevelEl.textContent = `¥${advice.resistance_level.toFixed(2)}`;
        if (supportLevelEl) supportLevelEl.textContent = `¥${advice.support_level.toFixed(2)}`;
        
        // 计算风险收益比
        const risk = ((advice.current_price - advice.stop_price) / advice.current_price * 100);
        const reward = ((advice.target_price - advice.current_price) / advice.current_price * 100);
        const riskRewardRatio = reward / Math.abs(risk);
        
        const riskPercentEl = document.getElementById('risk-percent');
        const rewardPercentEl = document.getElementById('reward-percent');
        const riskRewardRatioEl = document.getElementById('risk-reward-ratio');
        
        if (riskPercentEl) riskPercentEl.textContent = `${risk.toFixed(1)}%`;
        if (rewardPercentEl) rewardPercentEl.textContent = `+${reward.toFixed(1)}%`;
        if (riskRewardRatioEl) riskRewardRatioEl.textContent = `1:${riskRewardRatio.toFixed(1)}`;
        
        // 更新分析逻辑
        const analysisLogic = document.getElementById('analysis-logic');
        if (analysisLogic && advice.analysis_logic) {
            let logicHtml = '';
            advice.analysis_logic.forEach(logic => {
                logicHtml += `
                    <div class="logic-item">
                        <span class="logic-icon">•</span>
                        <span>${logic}</span>
                    </div>
                `;
            });
            analysisLogic.innerHTML = logicHtml;
        }
    }
    
    function loadDeepScanResults() {
        fetch('/api/deep_scan_results')
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    console.log('深度扫描结果未找到:', data.error);
                    deepScanSection.style.display = 'none';
                    return;
                }
                
                displayDeepScanResults(data);
                deepScanSection.style.display = 'block';
            })
            .catch(error => {
                console.error('Error loading deep scan results:', error);
                deepScanSection.style.display = 'none';
            });
    }
    
    function displayDeepScanResults(data) {
        // 更新统计数据
        if (totalAnalyzedEl) totalAnalyzedEl.textContent = data.summary.total_analyzed;
        if (aGradeCountEl) aGradeCountEl.textContent = data.summary.a_grade_count;
        if (priceEvalCountEl) priceEvalCountEl.textContent = data.summary.price_evaluated_count;
        if (buyRecCountEl) buyRecCountEl.textContent = data.summary.buy_recommendations;
        
        // 显示股票卡片
        displayStockCards(data.results);
    }
    
    function displayStockCards(stocks) {
        if (!stockGrid) return;
        
        if (!stocks || stocks.length === 0) {
            stockGrid.innerHTML = '<p>暂无深度扫描结果</p>';
            return;
        }
        
        let html = '';
        
        stocks.forEach(stock => {
            const gradeClass = `grade-${stock.grade.toLowerCase()}`;
            const cardClass = `stock-card ${gradeClass}`;
            
            // 价格变化颜色
            const priceChangeColor = stock.price_change_30d >= 0 ? '#28a745' : '#dc3545';
            const priceChangeSign = stock.price_change_30d >= 0 ? '+' : '';
            
            // 操作按钮样式
            const actionClass = stock.action.toLowerCase();
            
            html += `
                <div class="${cardClass}">
                    <div class="stock-header">
                        <span class="stock-code">${stock.stock_code}</span>
                        <span class="stock-grade ${gradeClass}">${stock.grade}级</span>
                    </div>
                    
                    <div class="stock-info">
                        <div class="info-item">
                            <span class="info-label">评分:</span>
                            <span class="info-value">${stock.score.toFixed(1)}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">当前价格:</span>
                            <span class="info-value">¥${stock.current_price.toFixed(2)}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">30天涨跌:</span>
                            <span class="info-value" style="color: ${priceChangeColor};">
                                ${priceChangeSign}${(stock.price_change_30d * 100).toFixed(1)}%
                            </span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">波动率:</span>
                            <span class="info-value">${(stock.volatility * 100).toFixed(1)}%</span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">信号数:</span>
                            <span class="info-value">${stock.signal_count}</span>
                        </div>
                        <div class="info-item">
                            <span class="info-label">信心度:</span>
                            <span class="info-value">${(stock.confidence * 100).toFixed(0)}%</span>
                        </div>
                    </div>
                    
                    ${stock.has_price_evaluation ? generatePriceEvaluationHtml(stock.price_evaluation) : ''}
                    
                    <button class="action-button ${actionClass}" onclick="viewStockDetail('${stock.stock_code}')">
                        ${getActionText(stock.action)}
                    </button>
                </div>
            `;
        });
        
        stockGrid.innerHTML = html;
    }
    
    function generatePriceEvaluationHtml(priceEval) {
        if (!priceEval || priceEval.error) {
            return '';
        }
        
        const details = priceEval.evaluation_details || {};
        
        let html = `
            <div class="price-evaluation">
                <div class="price-evaluation-header">
                    💰 价格评估
                </div>
        `;
        
        if (details.entry_strategy) {
            html += `
                <div class="info-item">
                    <span class="info-label">入场策略:</span>
                    <span class="info-value">${details.entry_strategy}</span>
                </div>
            `;
        }
        
        if (details.target_price_1) {
            html += `
                <div class="info-item">
                    <span class="info-label">目标价1:</span>
                    <span class="info-value">¥${details.target_price_1.toFixed(2)}</span>
                </div>
            `;
        }
        
        if (details.target_price_2) {
            html += `
                <div class="info-item">
                    <span class="info-label">目标价2:</span>
                    <span class="info-value">¥${details.target_price_2.toFixed(2)}</span>
                </div>
            `;
        }
        
        if (details.stop_loss && details.stop_loss.moderate) {
            html += `
                <div class="info-item">
                    <span class="info-label">建议止损:</span>
                    <span class="info-value">¥${details.stop_loss.moderate.toFixed(2)}</span>
                </div>
            `;
        }
        
        html += '</div>';
        return html;
    }
    
    function getActionText(action) {
        const actionTexts = {
            'BUY': '🟢 买入',
            'HOLD': '🟡 持有',
            'WATCH': '🟠 观察',
            'AVOID': '🔴 回避'
        };
        return actionTexts[action] || action;
    }
    
    function triggerDeepScan() {
        const strategy = strategySelect.value;
        
        if (!strategy) {
            alert('请先选择一个策略');
            return;
        }
        
        // 显示加载状态
        if (deepScanBtn) {
            deepScanBtn.textContent = '🔄 深度扫描中...';
            deepScanBtn.disabled = true;
        }
        
        // 触发深度扫描
        fetch(`/api/run_deep_scan?strategy=${strategy}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert(`深度扫描完成！\n分析了 ${data.summary.total_requested} 只股票\n成功分析 ${data.summary.total_analyzed} 只\nA级股票 ${data.summary.a_grade_count} 只\n价格评估 ${data.summary.price_evaluated_count} 只\n买入推荐 ${data.summary.buy_recommendations} 只`);
                
                // 重新加载深度扫描结果
                loadDeepScanResults();
            } else {
                alert(`深度扫描失败: ${data.error}`);
            }
        })
        .catch(error => {
            console.error('Error triggering deep scan:', error);
            alert(`深度扫描失败: ${error.message}`);
        })
        .finally(() => {
            // 恢复按钮状态
            if (deepScanBtn) {
                deepScanBtn.textContent = '🔍 深度扫描';
                deepScanBtn.disabled = false;
            }
        });
    }
    
    function viewStockDetail(stockCode) {
        // 切换到该股票的详细分析
        if (stockSelect) {
            // 检查股票是否在选择列表中
            const options = stockSelect.querySelectorAll('option');
            let found = false;
            
            for (let option of options) {
                if (option.value === stockCode) {
                    stockSelect.value = stockCode;
                    found = true;
                    break;
                }
            }
            
            if (found) {
                loadChart();
                // 滚动到图表区域
                chartContainer.scrollIntoView({ behavior: 'smooth' });
            } else {
                alert(`股票 ${stockCode} 不在当前策略的信号列表中，无法查看详细图表`);
            }
        }
    }
    
    // 历史报告功能
    if (historyBtn) historyBtn.addEventListener('click', showHistoryModal);
    if (refreshBtn) refreshBtn.addEventListener('click', refreshData);
    if (closeModal) closeModal.addEventListener('click', hideHistoryModal);
    
    // 标签页切换功能
    document.addEventListener('click', function(e) {
        if (e.target.classList.contains('history-tab')) {
            const tabName = e.target.getAttribute('data-tab');
            const modal = e.target.closest('.modal');
            
            // 移除所有活动状态
            modal.querySelectorAll('.history-tab').forEach(tab => tab.classList.remove('active'));
            modal.querySelectorAll('.history-content').forEach(content => content.classList.remove('active'));
            
            // 激活当前标签
            e.target.classList.add('active');
            const targetContent = modal.querySelector(`#${tabName}-content`);
            if (targetContent) {
                targetContent.classList.add('active');
            }
        }
    });
    
    function showHistoryModal() {
        if (historyModal) {
            historyModal.style.display = 'block';
            loadHistoryReports();
        }
    }
    
    function hideHistoryModal() {
        if (historyModal) {
            historyModal.style.display = 'none';
        }
    }
    
    function refreshData() {
        // 刷新当前页面数据
        populateStockList();
        loadDeepScanResults();
        
        // 如果有选中的股票，重新加载图表
        const stockCode = stockSelect.value;
        if (stockCode) {
            loadChart();
        }
        
        alert('数据已刷新');
    }
    
    function loadHistoryReports() {
        const strategy = strategySelect.value;
        
        fetch(`/api/history_reports?strategy=${strategy}`)
            .then(response => response.json())
            .then(data => {
                if (Array.isArray(data)) {
                    displayHistoryReports(data);
                } else {
                    console.error('Invalid history reports data:', data);
                    document.getElementById('overview-content').innerHTML = 
                        '<p>加载历史报告失败</p>';
                }
            })
            .catch(error => {
                console.error('Error loading history reports:', error);
                document.getElementById('overview-content').innerHTML = 
                    '<p>加载历史报告失败，请检查后端服务。</p>';
            });
    }
    
    function displayHistoryReports(reports) {
        const overviewContent = document.getElementById('overview-content');
        
        if (!reports || reports.length === 0) {
            overviewContent.innerHTML = '<p>暂无历史报告数据</p>';
            return;
        }
        
        let html = `
            <div class="report-summary">
                <h4>历史报告总览</h4>
                <p>共找到 ${reports.length} 个历史报告</p>
            </div>
            <table class="history-table">
                <thead>
                    <tr>
                        <th>扫描时间</th>
                        <th>信号数量</th>
                        <th>平均胜率</th>
                        <th>平均收益</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
        `;
        
        reports.forEach(report => {
            const scanSummary = report.scan_summary || {};
            const timestamp = scanSummary.scan_timestamp || '未知';
            const totalSignals = scanSummary.total_signals || 0;
            const avgWinRate = scanSummary.avg_win_rate || '0%';
            const avgProfitRate = scanSummary.avg_profit_rate || '0%';
            
            html += `
                <tr>
                    <td>${timestamp}</td>
                    <td>${totalSignals}</td>
                    <td>${avgWinRate}</td>
                    <td>${avgProfitRate}</td>
                    <td>
                        <button class="action-button" onclick="viewReportDetail('${report.id}')">
                            查看详情
                        </button>
                    </td>
                </tr>
            `;
        });
        
        html += '</tbody></table>';
        overviewContent.innerHTML = html;
    }
    
    function viewReportDetail(reportId) {
        alert(`查看报告详情功能开发中: ${reportId}`);
    }
    
    // 多周期分析功能
    if (multiTimeframeBtn) multiTimeframeBtn.addEventListener('click', showMultiTimeframeModal);
    if (multiCloseModal) multiCloseModal.addEventListener('click', hideMultiTimeframeModal);
    if (timeframeSelect) timeframeSelect.addEventListener('change', loadTimeframeChart);
    
    // 核心池管理功能
    const corePoolBtn = document.getElementById('core-pool-btn');
    const corePoolModal = document.getElementById('core-pool-modal');
    const corePoolClose = document.getElementById('core-pool-close');
    
    if (corePoolBtn) corePoolBtn.addEventListener('click', showCorePoolModal);
    if (corePoolClose) corePoolClose.addEventListener('click', hideCorePoolModal);
    
    // 核心池管理相关按钮
    const addStockBtn = document.getElementById('add-stock-btn');
    const refreshPoolBtn = document.getElementById('refresh-pool-btn');
    const addStockInput = document.getElementById('add-stock-input');
    
    if (addStockBtn) addStockBtn.addEventListener('click', addStockToCorePool);
    if (refreshPoolBtn) refreshPoolBtn.addEventListener('click', loadCorePoolData);
    if (addStockInput) {
        addStockInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                addStockToCorePool();
            }
        });
    }
    
    // 多周期分析相关函数
    function showMultiTimeframeModal() {
        if (multiTimeframeModal) {
            multiTimeframeModal.style.display = 'block';
            loadMultiTimeframeAnalysis();
        }
    }
    
    function hideMultiTimeframeModal() {
        if (multiTimeframeModal) {
            multiTimeframeModal.style.display = 'none';
        }
    }
    
    function loadMultiTimeframeAnalysis() {
        const stockCode = stockSelect.value;
        const strategy = strategySelect.value;
        
        if (!stockCode) {
            alert('请先选择一个股票');
            return;
        }
        
        // 加载多周期共振分析
        fetch(`/api/multi_timeframe/${stockCode}?strategy=${strategy}`)
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    displayConsensusAnalysis(data.consensus_analysis);
                    displayTimeframeSummary(data.timeframe_summary);
                } else {
                    console.error('Multi-timeframe analysis failed:', data.error);
                    document.getElementById('consensus-summary').innerHTML = 
                        `<p>多周期分析失败: ${data.error}</p>`;
                }
            })
            .catch(error => {
                console.error('Error loading multi-timeframe analysis:', error);
                document.getElementById('consensus-summary').innerHTML = 
                    '<p>加载多周期分析失败，请检查后端服务。</p>';
            });
    }
    
    function displayConsensusAnalysis(consensus) {
        const consensusContainer = document.getElementById('consensus-summary');
        
        if (!consensus) {
            consensusContainer.innerHTML = '<p>暂无共振分析数据</p>';
            return;
        }
        
        const levelColors = {
            'STRONG': '#27ae60',
            'MODERATE': '#f39c12', 
            'WEAK': '#e67e22',
            'NONE': '#95a5a6'
        };
        
        const levelColor = levelColors[consensus.consensus_level] || '#95a5a6';
        
        let html = `
            <div class="consensus-overview">
                <div class="consensus-score">
                    <h5>共振得分</h5>
                    <div class="score-circle" style="border-color: ${levelColor};">
                        <span class="score-value">${(consensus.consensus_score * 100).toFixed(0)}%</span>
                    </div>
                </div>
                <div class="consensus-details">
                    <div class="consensus-item">
                        <span class="label">共振级别:</span>
                        <span class="value" style="color: ${levelColor};">${consensus.consensus_level}</span>
                    </div>
                    <div class="consensus-item">
                        <span class="label">操作建议:</span>
                        <span class="value recommendation-${consensus.recommendation.toLowerCase()}">${consensus.recommendation}</span>
                    </div>
                </div>
            </div>
            
            <div class="timeframe-signals">
                <h5>各周期信号状态</h5>
                <div class="signals-grid">
        `;
        
        for (const [timeframe, signal] of Object.entries(consensus.timeframe_signals)) {
            const strengthPercent = (signal.signal_strength * 100).toFixed(0);
            const weightPercent = (signal.weight * 100).toFixed(0);
            
            html += `
                <div class="signal-item">
                    <div class="timeframe-name">${getTimeframeName(timeframe)}</div>
                    <div class="signal-state">${signal.signal_state}</div>
                    <div class="signal-strength">
                        <div class="strength-bar">
                            <div class="strength-fill" style="width: ${strengthPercent}%; background-color: ${levelColor};"></div>
                        </div>
                        <span class="strength-text">${strengthPercent}% (权重: ${weightPercent}%)</span>
                    </div>
                </div>
            `;
        }
        
        html += '</div></div>';
        consensusContainer.innerHTML = html;
    }
    
    function displayTimeframeSummary(summary) {
        const detailsContainer = document.getElementById('details-table');
        
        if (!summary || !summary.timeframe_details) {
            detailsContainer.innerHTML = '<p>暂无周期详情数据</p>';
            return;
        }
        
        let html = '<table class="history-table">';
        html += '<thead><tr><th>周期</th><th>最新价格</th><th>MA趋势</th><th>MACD趋势</th><th>RSI值</th><th>RSI状态</th><th>成交量比</th></tr></thead>';
        html += '<tbody>';
        
        for (const [timeframe, details] of Object.entries(summary.timeframe_details)) {
            const trendColor = details.ma_trend === 'UP' ? '#27ae60' : '#e74c3c';
            const macdColor = details.macd_trend === 'UP' ? '#27ae60' : '#e74c3c';
            const rsiColor = details.rsi_status === 'OVERBOUGHT' ? '#e74c3c' : 
                             details.rsi_status === 'OVERSOLD' ? '#27ae60' : '#95a5a6';
            
            html += `
                <tr>
                    <td><strong>${getTimeframeName(timeframe)}</strong></td>
                    <td>${details.latest_price.toFixed(2)}</td>
                    <td><span style="color: ${trendColor};">${details.ma_trend}</span></td>
                    <td><span style="color: ${macdColor};">${details.macd_trend}</span></td>
                    <td>${details.rsi_value.toFixed(1)}</td>
                    <td><span style="color: ${rsiColor};">${details.rsi_status}</span></td>
                    <td>${details.volume_ratio.toFixed(2)}x</td>
                </tr>
            `;
        }
        
        html += '</tbody></table>';
        detailsContainer.innerHTML = html;
    }
    
    function loadTimeframeChart() {
        const stockCode = stockSelect.value;
        const timeframe = timeframeSelect.value;
        
        if (!stockCode || !timeframe) return;
        
        fetch(`/api/timeframe_data/${stockCode}?timeframe=${timeframe}&limit=200`)
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    throw new Error(data.error);
                }
                displayTimeframeChart(data, timeframe);
            })
            .catch(error => {
                console.error('Error loading timeframe chart:', error);
                document.getElementById('timeframe-chart').innerHTML = 
                    `<p>加载${timeframe}周期图表失败: ${error.message}</p>`;
            });
    }
    
    function displayTimeframeChart(data, timeframe) {
        const chartContainer = document.getElementById('timeframe-chart');
        chartContainer.innerHTML = '<div id="timeframe-echarts" style="width: 100%; height: 400px;"></div>';
        
        const timeframeChart = echarts.init(document.getElementById('timeframe-echarts'));
        
        const dates = data.data.map(item => {
            return item.datetime || item.date;
        });
        const kline = data.data.map(item => [item.open, item.close, item.low, item.high]);
        const volumes = data.data.map((item, idx) => [idx, item.volume, item.open > item.close ? -1 : 1]);
        
        const option = {
            title: { text: `${data.stock_code} - ${getTimeframeName(timeframe)}周期`, left: 'center' },
            tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
            grid: [
                { left: '10%', right: '8%', height: '60%' },
                { left: '10%', right: '8%', top: '75%', height: '15%' }
            ],
            xAxis: [
                { type: 'category', data: dates, scale: true, boundaryGap: false },
                { type: 'category', data: dates, scale: true, gridIndex: 1, boundaryGap: false }
            ],
            yAxis: [
                { scale: true },
                { scale: true, gridIndex: 1 }
            ],
            dataZoom: [
                { type: 'inside', xAxisIndex: [0, 1], start: 70, end: 100 },
                { show: true, type: 'slider', xAxisIndex: [0, 1], top: '92%', start: 70, end: 100 }
            ],
            series: [
                {
                    name: 'K线',
                    type: 'candlestick',
                    data: kline,
                    itemStyle: {
                        color: '#ec0000',
                        color0: '#00da3c',
                        borderColor: '#8A0000',
                        borderColor0: '#008F28'
                    }
                },
                {
                    name: '成交量',
                    type: 'bar',
                    xAxisIndex: 1,
                    yAxisIndex: 1,
                    data: volumes,
                    itemStyle: {
                        color: ({ data }) => (data[2] === 1 ? '#ef232a' : '#14b143')
                    }
                }
            ]
        };
        
        timeframeChart.setOption(option);
    }
    
    function getTimeframeName(timeframe) {
        const names = {
            'daily': '日线',
            '60min': '60分钟',
            '30min': '30分钟', 
            '15min': '15分钟',
            '5min': '5分钟'
        };
        return names[timeframe] || timeframe;
    }

    // 模态窗口外部点击关闭
    window.addEventListener('click', (event) => {
        if (event.target === historyModal) {
            hideHistoryModal();
        }
    });

    // 标签页切换
    historyTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const targetTab = tab.dataset.tab;
            switchHistoryTab(targetTab);
        });
    });

    function showHistoryModal() {
        historyModal.style.display = 'block';
        loadHistoryReports();
    }

    function hideHistoryModal() {
        historyModal.style.display = 'none';
    }

    function switchHistoryTab(targetTab) {
        // 更新标签页状态
        historyTabs.forEach(tab => {
            tab.classList.remove('active');
            if (tab.dataset.tab === targetTab) {
                tab.classList.add('active');
            }
        });

        // 更新内容显示
        historyContents.forEach(content => {
            content.classList.remove('active');
            if (content.id === `${targetTab}-content`) {
                content.classList.add('active');
            }
        });

        // 加载对应内容
        switch (targetTab) {
            case 'overview':
                loadOverviewData();
                break;
            case 'reports':
                loadHistoryReports();
                break;
            case 'reliability':
                loadReliabilityAnalysis();
                break;
            case 'performance':
                loadPerformanceTracking();
                break;
        }
    }

    function loadHistoryReports() {
        const strategy = strategySelect.value;
        fetch(`/api/history_reports?strategy=${strategy}`)
            .then(response => response.json())
            .then(data => {
                displayHistoryReports(data);
            })
            .catch(error => {
                console.error('Error loading history reports:', error);
                document.getElementById('reports-list').innerHTML =
                    '<p>加载历史报告失败，请检查后端服务。</p>';
            });
    }

    function displayHistoryReports(reports) {
        const reportsContainer = document.getElementById('reports-list');

        if (!reports || reports.length === 0) {
            reportsContainer.innerHTML = '<p>暂无历史报告数据</p>';
            return;
        }

        let html = '<table class="history-table">';
        html += '<thead><tr><th>扫描时间</th><th>信号数量</th><th>平均胜率</th><th>平均收益</th><th>处理时间</th><th>操作</th></tr></thead>';
        html += '<tbody>';

        reports.forEach(report => {
            const summary = report.scan_summary || {};
            html += `
                <tr>
                    <td>${summary.scan_timestamp || 'N/A'}</td>
                    <td>${summary.total_signals || 0}</td>
                    <td>${summary.avg_win_rate || 'N/A'}</td>
                    <td>${summary.avg_profit_rate || 'N/A'}</td>
                    <td>${summary.processing_time || 'N/A'}</td>
                    <td><button onclick="viewReportDetails('${report.id}')">查看详情</button></td>
                </tr>
            `;
        });

        html += '</tbody></table>';
        reportsContainer.innerHTML = html;
    }

    function loadOverviewData() {
        const strategy = strategySelect.value;
        fetch(`/api/strategy_overview?strategy=${strategy}`)
            .then(response => response.json())
            .then(data => {
                displayOverviewStats(data);
            })
            .catch(error => {
                console.error('Error loading overview data:', error);
                document.getElementById('overview-stats').innerHTML =
                    '<p>加载概览数据失败</p>';
            });
    }

    function displayOverviewStats(data) {
        const overviewContainer = document.getElementById('overview-stats');

        if (!data) {
            overviewContainer.innerHTML = '<p>暂无概览数据</p>';
            return;
        }

        let html = `
            <div class="overview-grid">
                <div class="overview-card">
                    <h5>总扫描次数</h5>
                    <p class="overview-number">${data.total_scans || 0}</p>
                </div>
                <div class="overview-card">
                    <h5>累计发现信号</h5>
                    <p class="overview-number">${data.total_signals || 0}</p>
                </div>
                <div class="overview-card">
                    <h5>平均胜率</h5>
                    <p class="overview-number">${data.avg_win_rate || 'N/A'}</p>
                </div>
                <div class="overview-card">
                    <h5>平均收益率</h5>
                    <p class="overview-number">${data.avg_profit_rate || 'N/A'}</p>
                </div>
            </div>
        `;

        overviewContainer.innerHTML = html;
    }

    function loadReliabilityAnalysis() {
        const strategy = strategySelect.value;
        fetch(`/api/reliability_analysis?strategy=${strategy}`)
            .then(response => response.json())
            .then(data => {
                displayReliabilityAnalysis(data);
            })
            .catch(error => {
                console.error('Error loading reliability analysis:', error);
                document.getElementById('reliability-analysis').innerHTML =
                    '<p>加载可靠性分析失败</p>';
            });
    }

    function displayReliabilityAnalysis(data) {
        const reliabilityContainer = document.getElementById('reliability-analysis');

        if (!data || !data.stocks) {
            reliabilityContainer.innerHTML = '<p>暂无可靠性分析数据</p>';
            return;
        }

        let html = '<table class="history-table">';
        html += '<thead><tr><th>股票代码</th><th>历史出现次数</th><th>胜率</th><th>平均收益</th><th>可靠性评级</th><th>最近表现</th></tr></thead>';
        html += '<tbody>';

        data.stocks.forEach(stock => {
            const reliability = getReliabilityLevel(stock.win_rate, stock.appearance_count);
            html += `
                <tr>
                    <td>${stock.stock_code}</td>
                    <td>${stock.appearance_count}</td>
                    <td>${stock.win_rate}</td>
                    <td>${stock.avg_profit}</td>
                    <td><span class="reliability-indicator ${reliability.class}">${reliability.text}</span></td>
                    <td>${stock.recent_performance || 'N/A'}</td>
                </tr>
            `;
        });

        html += '</tbody></table>';
        reliabilityContainer.innerHTML = html;
    }

    function getReliabilityLevel(winRate, appearanceCount) {
        const rate = parseFloat(winRate.replace('%', ''));

        if (rate >= 70 && appearanceCount >= 5) {
            return { class: 'reliability-high', text: '高可靠' };
        } else if (rate >= 50 && appearanceCount >= 3) {
            return { class: 'reliability-medium', text: '中等' };
        } else {
            return { class: 'reliability-low', text: '低可靠' };
        }
    }

    function loadPerformanceTracking() {
        const strategy = strategySelect.value;
        fetch(`/api/performance_tracking?strategy=${strategy}`)
            .then(response => response.json())
            .then(data => {
                displayPerformanceTracking(data);
            })
            .catch(error => {
                console.error('Error loading performance tracking:', error);
                document.getElementById('performance-tracking').innerHTML =
                    '<p>加载表现追踪失败</p>';
            });
    }

    function displayPerformanceTracking(data) {
        const trackingContainer = document.getElementById('performance-tracking');

        if (!data || !data.tracking_results) {
            trackingContainer.innerHTML = '<p>暂无表现追踪数据</p>';
            return;
        }

        let html = '<table class="history-table">';
        html += '<thead><tr><th>筛选日期</th><th>股票代码</th><th>信号状态</th><th>预期收益</th><th>实际收益</th><th>达峰天数</th><th>表现评价</th></tr></thead>';
        html += '<tbody>';

        data.tracking_results.forEach(result => {
            const performance = result.actual_profit >= result.expected_profit ? '超预期' : '低于预期';
            const performanceClass = result.actual_profit >= result.expected_profit ? 'text-success' : 'text-warning';

            html += `
                <tr>
                    <td>${result.scan_date}</td>
                    <td>${result.stock_code}</td>
                    <td>${result.signal_state}</td>
                    <td>${result.expected_profit}</td>
                    <td>${result.actual_profit}</td>
                    <td>${result.days_to_peak}</td>
                    <td><span class="${performanceClass}">${performance}</span></td>
                </tr>
            `;
        });

        html += '</tbody></table>';
        trackingContainer.innerHTML = html;
    }

    function refreshData() {
        // 刷新当前页面数据
        populateStockList();

        // 如果模态窗口打开，也刷新历史数据
        if (historyModal.style.display === 'block') {
            const activeTab = document.querySelector('.history-tab.active');
            if (activeTab) {
                switchHistoryTab(activeTab.dataset.tab);
            }
        }

        // 显示刷新成功提示
        const refreshBtn = document.getElementById('refresh-btn');
        const originalText = refreshBtn.textContent;
        refreshBtn.textContent = '✅ 已刷新';
        refreshBtn.disabled = true;

        setTimeout(() => {
            refreshBtn.textContent = originalText;
            refreshBtn.disabled = false;
        }, 2000);
    }

    // 悬浮图例交互功能
    const legendToggle = document.getElementById('legend-toggle');
    const legendContent = document.getElementById('legend-content');
    
    if (legendToggle && legendContent) {
        legendToggle.addEventListener('click', function() {
            legendContent.classList.toggle('show');
        });
        
        // 点击其他地方关闭图例
        document.addEventListener('click', function(event) {
            if (!event.target.closest('#legend')) {
                legendContent.classList.remove('show');
            }
        });
    }
    
    populateStockList();
});
    
    // 交易建议面板功能
    function loadTradingAdvice(stockCode, strategy) {
        // 显示加载状态
        updateAdvicePanel({
            action: 'LOADING',
            confidence: 0,
            entry_price: '--',
            target_price: '--',
            stop_price: '--',
            current_price: '--',
            analysis_logic: ['正在分析中...'],
            resistance_level: '--',
            support_level: '--'
        });
        
        // 调用交易建议API
        fetch(`/api/trading_advice/${stockCode}?strategy=${strategy}`)
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    throw new Error(data.error);
                }
                updateAdvicePanel(data);
            })
            .catch(error => {
                console.error('Error loading trading advice:', error);
                updateAdvicePanel({
                    action: 'ERROR',
                    confidence: 0,
                    entry_price: '--',
                    target_price: '--',
                    stop_price: '--',
                    current_price: '--',
                    analysis_logic: [`加载失败: ${error.message}`],
                    resistance_level: '--',
                    support_level: '--'
                });
            });
    }
    
    function updateAdvicePanel(advice) {
        // 更新操作建议
        const actionEl = document.getElementById('action-recommendation');
        if (actionEl) {
            const actionClass = advice.action.toLowerCase();
            actionEl.className = `action-recommendation ${actionClass}`;
            
            let actionText = '';
            let confidenceText = `置信度: ${(advice.confidence * 100).toFixed(0)}%`;
            
            switch (advice.action) {
                case 'BUY':
                    actionText = '🟢 建议买入';
                    break;
                case 'HOLD':
                    actionText = '🟡 建议持有';
                    break;
                case 'WATCH':
                    actionText = '🟠 继续观察';
                    break;
                case 'AVOID':
                    actionText = '🔴 建议回避';
                    break;
                case 'LOADING':
                    actionText = '🔄 分析中...';
                    confidenceText = '请稍候';
                    break;
                case 'ERROR':
                    actionText = '❌ 分析失败';
                    confidenceText = '请重试';
                    break;
                default:
                    actionText = '❓ 未知状态';
            }
            
            actionEl.innerHTML = `
                <div class="action-text">${actionText}</div>
                <div class="confidence-text">${confidenceText}</div>
            `;
        }
        
        // 更新价格信息
        const priceElements = {
            'entry-price': advice.entry_price,
            'target-price': advice.target_price,
            'stop-price': advice.stop_price,
            'current-price': advice.current_price
        };
        
        for (const [id, value] of Object.entries(priceElements)) {
            const el = document.getElementById(id);
            if (el) {
                el.textContent = typeof value === 'number' ? `¥${value.toFixed(2)}` : value;
            }
        }
        
        // 计算风险收益比
        if (typeof advice.entry_price === 'number' && 
            typeof advice.target_price === 'number' && 
            typeof advice.stop_price === 'number') {
            
            const risk = advice.entry_price - advice.stop_price;
            const reward = advice.target_price - advice.entry_price;
            const riskPercent = (risk / advice.entry_price * 100).toFixed(1);
            const rewardPercent = (reward / advice.entry_price * 100).toFixed(1);
            const ratio = risk > 0 ? (reward / risk).toFixed(1) : '--';
            
            const riskEl = document.getElementById('risk-percent');
            const rewardEl = document.getElementById('reward-percent');
            const ratioEl = document.getElementById('risk-reward-ratio');
            
            if (riskEl) riskEl.textContent = `-${riskPercent}%`;
            if (rewardEl) rewardEl.textContent = `+${rewardPercent}%`;
            if (ratioEl) ratioEl.textContent = `1:${ratio}`;
        }
        
        // 更新分析逻辑
        const logicEl = document.getElementById('analysis-logic');
        if (logicEl && advice.analysis_logic) {
            let logicHtml = '';
            advice.analysis_logic.forEach(logic => {
                logicHtml += `
                    <div class="logic-item">
                        <span class="logic-icon">•</span>
                        <span>${logic}</span>
                    </div>
                `;
            });
            logicEl.innerHTML = logicHtml;
        }
        
        // 更新关键位置
        const resistanceEl = document.getElementById('resistance-level');
        const supportEl = document.getElementById('support-level');
        
        if (resistanceEl) {
            resistanceEl.textContent = typeof advice.resistance_level === 'number' 
                ? `¥${advice.resistance_level.toFixed(2)}` 
                : advice.resistance_level;
        }
        
        if (supportEl) {
            supportEl.textContent = typeof advice.support_level === 'number' 
                ? `¥${advice.support_level.toFixed(2)}` 
                : advice.support_level;
        }
    }    // 
核心池管理功能
    function showCorePoolModal() {
        if (corePoolModal) {
            corePoolModal.style.display = 'block';
            loadCorePoolData();
        }
    }
    
    function hideCorePoolModal() {
        if (corePoolModal) {
            corePoolModal.style.display = 'none';
        }
    }
    
    function loadCorePoolData() {
        fetch('/api/core_pool')
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    displayCorePoolData(data.core_pool);
                    updateCorePoolStats(data.core_pool);
                } else {
                    console.error('Failed to load core pool:', data.error);
                    document.getElementById('core-pool-list').innerHTML = 
                        `<p>加载核心池数据失败: ${data.error}</p>`;
                }
            })
            .catch(error => {
                console.error('Error loading core pool:', error);
                document.getElementById('core-pool-list').innerHTML = 
                    '<p>加载核心池数据失败，请检查后端服务。</p>';
            });
    }
    
    function displayCorePoolData(corePool) {
        const corePoolList = document.getElementById('core-pool-list');
        
        if (!corePool || corePool.length === 0) {
            corePoolList.innerHTML = '<p>核心池为空，请添加股票。</p>';
            return;
        }
        
        let html = '<div class="stock-grid">';
        
        corePool.forEach(stock => {
            html += `
                <div class="stock-card">
                    <div class="stock-header">
                        <span class="stock-code">${stock.stock_code}</span>
                        <button class="action-button" style="background: #dc3545;" 
                                onclick="removeFromCorePool('${stock.stock_code}')">
                            🗑️ 删除
                        </button>
                    </div>
                    <div class="stock-info">
                        <div class="info-item">
                            <span class="info-label">添加时间:</span>
                            <span class="info-value">${stock.added_time}</span>
                        </div>
                        ${stock.note ? `
                        <div class="info-item">
                            <span class="info-label">备注:</span>
                            <span class="info-value">${stock.note}</span>
                        </div>
                        ` : ''}
                    </div>
                    <button class="action-button" onclick="viewStockDetail('${stock.stock_code}')">
                        📊 查看详情
                    </button>
                </div>
            `;
        });
        
        html += '</div>';
        corePoolList.innerHTML = html;
    }
    
    function updateCorePoolStats(corePool) {
        const totalStocksEl = document.getElementById('total-stocks');
        const aGradeStocksEl = document.getElementById('a-grade-stocks');
        const avgWeightEl = document.getElementById('avg-weight');
        const totalWeightEl = document.getElementById('total-weight');
        
        if (totalStocksEl) totalStocksEl.textContent = corePool.length;
        if (aGradeStocksEl) aGradeStocksEl.textContent = '0'; // 需要实际计算
        if (avgWeightEl) avgWeightEl.textContent = corePool.length > 0 ? (100 / corePool.length).toFixed(1) + '%' : '0%';
        if (totalWeightEl) totalWeightEl.textContent = '100%';
    }
    
    function addStockToCorePool() {
        const stockInput = document.getElementById('add-stock-input');
        const stockCode = stockInput.value.trim().toUpperCase();
        
        if (!stockCode) {
            alert('请输入股票代码');
            return;
        }
        
        // 简单的股票代码格式验证
        if (!/^(SZ|SH)\d{6}$/.test(stockCode)) {
            // 如果用户只输入了6位数字，自动添加前缀
            if (/^\d{6}$/.test(stockCode)) {
                const code = stockCode;
                const prefix = code.startsWith('0') || code.startsWith('3') ? 'SZ' : 'SH';
                stockCode = prefix + code;
            } else {
                alert('股票代码格式不正确，请输入如 000001 或 SZ000001 格式');
                return;
            }
        }
        
        fetch('/api/core_pool', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                stock_code: stockCode,
                note: ''
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert(data.message);
                stockInput.value = '';
                loadCorePoolData(); // 重新加载数据
            } else {
                alert(`添加失败: ${data.error}`);
            }
        })
        .catch(error => {
            console.error('Error adding stock to core pool:', error);
            alert(`添加失败: ${error.message}`);
        });
    }
    
    function removeFromCorePool(stockCode) {
        if (!confirm(`确定要从核心池删除股票 ${stockCode} 吗？`)) {
            return;
        }
        
        fetch(`/api/core_pool?stock_code=${stockCode}`, {
            method: 'DELETE'
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert(data.message);
                loadCorePoolData(); // 重新加载数据
            } else {
                alert(`删除失败: ${data.error}`);
            }
        })
        .catch(error => {
            console.error('Error removing stock from core pool:', error);
            alert(`删除失败: ${error.message}`);
        });
    }
    
    function loadCorePoolData() {
        fetch('/api/core_pool')
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    console.error('Error loading core pool:', data.error);
                    return;
                }
                
                updateCorePoolStats(data.stats);
                displayCorePoolList(data.stocks);
                displayWeightControls(data.stocks);
                displayGradeManagement(data.stocks);
            })
            .catch(error => {
                console.error('Error loading core pool data:', error);
            });
    }
    
    function updateCorePoolStats(stats) {
        const totalStocksEl = document.getElementById('total-stocks');
        const aGradeStocksEl = document.getElementById('a-grade-stocks');
        const avgWeightEl = document.getElementById('avg-weight');
        const totalWeightEl = document.getElementById('total-weight');
        
        if (totalStocksEl) totalStocksEl.textContent = stats.total_stocks || 0;
        if (aGradeStocksEl) aGradeStocksEl.textContent = stats.a_grade_stocks || 0;
        if (avgWeightEl) avgWeightEl.textContent = `${(stats.avg_weight || 0).toFixed(1)}%`;
        if (totalWeightEl) totalWeightEl.textContent = `${(stats.total_weight || 0).toFixed(1)}%`;
    }
    
    function displayCorePoolList(stocks) {
        const listContainer = document.getElementById('core-pool-list');
        if (!listContainer) return;
        
        if (!stocks || stocks.length === 0) {
            listContainer.innerHTML = '<p>核心池暂无股票</p>';
            return;
        }
        
        let html = '<table class="history-table">';
        html += '<thead><tr><th>股票代码</th><th>等级</th><th>权重</th><th>当前价格</th><th>30天涨跌</th><th>操作</th></tr></thead>';
        html += '<tbody>';
        
        stocks.forEach(stock => {
            const gradeClass = `grade-${stock.grade.toLowerCase()}`;
            const priceChangeColor = stock.price_change >= 0 ? '#28a745' : '#dc3545';
            const priceChangeSign = stock.price_change >= 0 ? '+' : '';
            
            html += `
                <tr>
                    <td><strong>${stock.stock_code}</strong></td>
                    <td><span class="stock-grade ${gradeClass}">${stock.grade}</span></td>
                    <td>${stock.weight.toFixed(1)}%</td>
                    <td>¥${stock.current_price.toFixed(2)}</td>
                    <td style="color: ${priceChangeColor};">
                        ${priceChangeSign}${(stock.price_change * 100).toFixed(1)}%
                    </td>
                    <td>
                        <button class="action-button" onclick="removeFromCorePool('${stock.stock_code}')" style="background: #dc3545; font-size: 12px; padding: 4px 8px;">
                            🗑️ 移除
                        </button>
                    </td>
                </tr>
            `;
        });
        
        html += '</tbody></table>';
        listContainer.innerHTML = html;
    }
    
    function displayWeightControls(stocks) {
        const controlsContainer = document.getElementById('weight-controls');
        if (!controlsContainer) return;
        
        if (!stocks || stocks.length === 0) {
            controlsContainer.innerHTML = '<p>暂无股票可调整权重</p>';
            return;
        }
        
        let html = '';
        stocks.forEach(stock => {
            html += `
                <div class="weight-control-item" style="margin-bottom: 20px; padding: 15px; background: #f8f9fa; border-radius: 8px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                        <span style="font-weight: bold;">${stock.stock_code}</span>
                        <span class="weight-display" id="weight-display-${stock.stock_code}">${stock.weight.toFixed(1)}%</span>
                    </div>
                    <input type="range" 
                           id="weight-slider-${stock.stock_code}" 
                           min="0" 
                           max="50" 
                           step="0.5" 
                           value="${stock.weight}" 
                           style="width: 100%;"
                           onchange="updateStockWeight('${stock.stock_code}', this.value)">
                    <div style="display: flex; justify-content: space-between; font-size: 12px; color: #6c757d; margin-top: 5px;">
                        <span>0%</span>
                        <span>25%</span>
                        <span>50%</span>
                    </div>
                </div>
            `;
        });
        
        controlsContainer.innerHTML = html;
    }
    
    function displayGradeManagement(stocks) {
        const managementContainer = document.getElementById('grade-management-list');
        if (!managementContainer) return;
        
        if (!stocks || stocks.length === 0) {
            managementContainer.innerHTML = '<p>暂无股票可管理等级</p>';
            return;
        }
        
        let html = '<table class="history-table">';
        html += '<thead><tr><th>股票代码</th><th>当前等级</th><th>评分</th><th>等级操作</th></tr></thead>';
        html += '<tbody>';
        
        stocks.forEach(stock => {
            const gradeClass = `grade-${stock.grade.toLowerCase()}`;
            
            html += `
                <tr>
                    <td><strong>${stock.stock_code}</strong></td>
                    <td><span class="stock-grade ${gradeClass}">${stock.grade}</span></td>
                    <td>${stock.score ? stock.score.toFixed(1) : 'N/A'}</td>
                    <td>
                        <select onchange="changeStockGrade('${stock.stock_code}', this.value)" style="padding: 4px; margin-right: 5px;">
                            <option value="">选择等级</option>
                            <option value="A" ${stock.grade === 'A' ? 'selected' : ''}>A级</option>
                            <option value="B" ${stock.grade === 'B' ? 'selected' : ''}>B级</option>
                            <option value="C" ${stock.grade === 'C' ? 'selected' : ''}>C级</option>
                            <option value="D" ${stock.grade === 'D' ? 'selected' : ''}>D级</option>
                        </select>
                        <button class="action-button" onclick="demoteStock('${stock.stock_code}')" style="background: #ffc107; color: #212529; font-size: 12px; padding: 4px 8px;">
                            ⬇️ 降级
                        </button>
                    </td>
                </tr>
            `;
        });
        
        html += '</tbody></table>';
        managementContainer.innerHTML = html;
    }
    
    function addStockToCorePool() {
        const input = document.getElementById('add-stock-input');
        const stockCode = input.value.trim();
        
        if (!stockCode) {
            alert('请输入股票代码');
            return;
        }
        
        fetch('/api/core_pool/add', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ stock_code: stockCode })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert(`股票 ${stockCode} 已添加到核心池`);
                input.value = '';
                loadCorePoolData();
            } else {
                alert(`添加失败: ${data.error}`);
            }
        })
        .catch(error => {
            console.error('Error adding stock to core pool:', error);
            alert(`添加失败: ${error.message}`);
        });
    }
    
    function removeFromCorePool(stockCode) {
        if (!confirm(`确定要从核心池中移除 ${stockCode} 吗？`)) {
            return;
        }
        
        fetch('/api/core_pool/remove', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ stock_code: stockCode })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert(`股票 ${stockCode} 已从核心池移除`);
                loadCorePoolData();
            } else {
                alert(`移除失败: ${data.error}`);
            }
        })
        .catch(error => {
            console.error('Error removing stock from core pool:', error);
            alert(`移除失败: ${error.message}`);
        });
    }
    
    function updateStockWeight(stockCode, weight) {
        const displayEl = document.getElementById(`weight-display-${stockCode}`);
        if (displayEl) {
            displayEl.textContent = `${parseFloat(weight).toFixed(1)}%`;
        }
        
        fetch('/api/core_pool/weight', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ 
                stock_code: stockCode, 
                weight: parseFloat(weight) 
            })
        })
        .then(response => response.json())
        .then(data => {
            if (!data.success) {
                console.error('Error updating weight:', data.error);
            }
        })
        .catch(error => {
            console.error('Error updating stock weight:', error);
        });
    }
    
    function changeStockGrade(stockCode, grade) {
        if (!grade) return;
        
        fetch('/api/core_pool/grade', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ 
                stock_code: stockCode, 
                grade: grade 
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert(`股票 ${stockCode} 等级已更新为 ${grade}`);
                loadCorePoolData();
            } else {
                alert(`等级更新失败: ${data.error}`);
            }
        })
        .catch(error => {
            console.error('Error changing stock grade:', error);
            alert(`等级更新失败: ${error.message}`);
        });
    }
    
    function demoteStock(stockCode) {
        if (!confirm(`确定要降级股票 ${stockCode} 吗？`)) {
            return;
        }
        
        fetch('/api/core_pool/demote', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ stock_code: stockCode })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert(`股票 ${stockCode} 已降级`);
                loadCorePoolData();
            } else {
                alert(`降级失败: ${data.error}`);
            }
        })
        .catch(error => {
            console.error('Error demoting stock:', error);
            alert(`降级失败: ${error.message}`);
        });
    }
    
    // 全局函数，供HTML调用
    window.removeFromCorePool = removeFromCorePool;
    window.updateStockWeight = updateStockWeight;
    window.changeStockGrade = changeStockGrade;
    window.demoteStock = demoteStock;    

    // 辅助函数：获取周期名称
    function getTimeframeName(timeframe) {
        const names = {
            'daily': '日线',
            '60min': '60分钟',
            '30min': '30分钟',
            '15min': '15分钟',
            '5min': '5分钟',
            'weekly': '周线',
            'monthly': '月线'
        };
        return names[timeframe] || timeframe;
    }