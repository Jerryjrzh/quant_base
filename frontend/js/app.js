document.addEventListener('DOMContentLoaded', function () {
    // --- DOM元素获取 ---
    const stockSelect = document.getElementById('stock-select');
    const strategySelect = document.getElementById('strategy-select');
    const adjustmentSelect = document.getElementById('adjustment-select');
    const chartContainer = document.getElementById('chart-container');
    const myChart = echarts.init(chartContainer);
    const refreshBtn = document.getElementById('refresh-btn');
    const multiTimeframeBtn = document.getElementById('multi-timeframe-btn');
    const deepScanBtn = document.getElementById('deep-scan-btn');
    const historyBtn = document.getElementById('history-btn');
    const backtestContainer = document.getElementById('backtest-results');
    
    // 交易建议面板
    const advicePanel = document.getElementById('trading-advice-panel');
    const adviceRefreshBtn = document.getElementById('advice-refresh');
    
    // 深度扫描
    const deepScanSection = document.getElementById('deep-scan-section');
    
    // 模态框
    const corePoolBtn = document.getElementById('core-pool-btn');
    const corePoolModal = document.getElementById('core-pool-modal');
    const corePoolClose = document.getElementById('core-pool-close');
    const historyModal = document.getElementById('history-modal');
    const historyClose = document.getElementById('history-close');
    const multiTimeframeModal = document.getElementById('multi-timeframe-modal');
    const multiTimeframeClose = document.getElementById('multi-timeframe-close');


    // --- 事件监听 ---
    strategySelect.addEventListener('change', () => {
        populateStockList();
        myChart.clear();
        if (advicePanel) advicePanel.style.display = 'none';
        if (backtestContainer) backtestContainer.style.display = 'none';
    });
    
    stockSelect.addEventListener('change', loadChart);
    
    // 复权设置变化时重新加载图表
    if (adjustmentSelect) adjustmentSelect.addEventListener('change', () => {
        if (stockSelect.value) loadChart();
    });
    
    if (refreshBtn) refreshBtn.addEventListener('click', () => {
        populateStockList();
        if (stockSelect.value) loadChart();
    });
    
    if (adviceRefreshBtn) {
        adviceRefreshBtn.addEventListener('click', () => {
            const stockCode = stockSelect.value;
            const strategy = strategySelect.value;
            if (stockCode) {
                loadTradingAdvice(stockCode, strategy);
            }
        });
    }
    
    if (deepScanBtn) deepScanBtn.addEventListener('click', runDeepScan);
    if (historyBtn) historyBtn.addEventListener('click', showHistoryModal);
    if (multiTimeframeBtn) multiTimeframeBtn.addEventListener('click', showMultiTimeframeModal);
    
    // 模态框事件
    if (corePoolBtn) corePoolBtn.addEventListener('click', showCorePoolModal);
    if (corePoolClose) corePoolClose.addEventListener('click', hideCorePoolModal);
    if (historyClose) historyClose.addEventListener('click', hideHistoryModal);
    if (multiTimeframeClose) multiTimeframeClose.addEventListener('click', hideMultiTimeframeModal);
    
    // 点击模态框外部关闭
    window.addEventListener('click', (event) => {
        if (event.target === corePoolModal) hideCorePoolModal();
        if (event.target === historyModal) hideHistoryModal();
        if (event.target === multiTimeframeModal) hideMultiTimeframeModal();
    });


    // --- 主要功能函数 ---

    function populateStockList() {
        const strategy = strategySelect.value;
        fetch(`/api/signals_summary?strategy=${strategy}`)
            .then(response => {
                if (!response.ok) throw new Error(`无法加载信号文件 (策略: ${strategy})`);
                return response.json();
            })
            .then(data => {
                stockSelect.innerHTML = '<option value="">请选择股票</option>';
                if (!data || data.length === 0) {
                    stockSelect.innerHTML += `<option disabled>策略 ${strategy} 今日无信号</option>`;
                    return;
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

    function loadChart() {
        const stockCode = stockSelect.value;
        const strategy = strategySelect.value;
        if (!stockCode) return;

        myChart.showLoading();
        
        // **修复点**: 确保交易建议面板显示并加载数据
        if (advicePanel) {
            advicePanel.style.display = 'block';
            loadTradingAdvice(stockCode, strategy);
        }

        // 获取复权设置
        const adjustmentType = adjustmentSelect ? adjustmentSelect.value : 'forward';
        
        fetch(`/api/analysis/${stockCode}?strategy=${strategy}&adjustment=${adjustmentType}`)
            .then(response => response.json())
            .then(chartData => {
                myChart.hideLoading();
                if (chartData.error) throw new Error(chartData.error);
                if (!chartData.kline_data || !chartData.indicator_data) {
                    throw new Error('返回的数据格式不正确');
                }
                
                // 渲染回测和图表
                renderBacktestResults(chartData.backtest_results);
                renderEchart(chartData, stockCode, strategy);
            })
            .catch(error => {
                myChart.hideLoading();
                console.error('Error fetching chart data:', error);
                myChart.clear();
                // 在图表容器内显示错误，而不是替换它
                myChart.setOption({
                    title: {
                        text: '加载图表数据失败',
                        subtext: error.message,
                        left: 'center',
                        top: 'center'
                    }
                });
            });
    }

    function renderEchart(chartData, stockCode, strategy) {
        const dates = chartData.kline_data.map(item => item.date);
        const klineData = chartData.kline_data.map(item => [item.open, item.close, item.low, item.high]);
        const volumeData = chartData.kline_data.map(item => item.volume);
        
        // 技术指标数据
        const ma13Data = chartData.indicator_data.map(item => item.ma13);
        const ma45Data = chartData.indicator_data.map(item => item.ma45);
        const difData = chartData.indicator_data.map(item => item.dif);
        const deaData = chartData.indicator_data.map(item => item.dea);
        const macdData = chartData.indicator_data.map(item => item.macd);
        const kData = chartData.indicator_data.map(item => item.k);
        const dData = chartData.indicator_data.map(item => item.d);
        const jData = chartData.indicator_data.map(item => item.j);
        const rsi6Data = chartData.indicator_data.map(item => item.rsi6);
        const rsi12Data = chartData.indicator_data.map(item => item.rsi12);
        const rsi24Data = chartData.indicator_data.map(item => item.rsi24);
        
        // 信号点数据
        const signalData = chartData.signal_points || [];
        
        // 计算合理的数据显示范围
        const totalDataPoints = dates.length;
        const defaultShowCount = Math.min(60, totalDataPoints); // 默认显示最近60个交易日
        const startPercent = Math.max(0, ((totalDataPoints - defaultShowCount) / totalDataPoints) * 100);
        
        // 计算各指标的动态范围
        // RSI指标范围计算
        const allRsiValues = [...rsi6Data, ...rsi12Data, ...rsi24Data].filter(val => val !== null && val !== undefined);
        const rsiMin = allRsiValues.length > 0 ? Math.max(0, Math.min(...allRsiValues) - 5) : 0;
        const rsiMax = allRsiValues.length > 0 ? Math.min(100, Math.max(...allRsiValues) + 5) : 100;
        
        // KDJ指标范围计算
        const allKdjValues = [...kData, ...dData, ...jData].filter(val => val !== null && val !== undefined);
        const kdjMin = allKdjValues.length > 0 ? Math.max(0, Math.min(...allKdjValues) - 5) : 0;
        const kdjMax = allKdjValues.length > 0 ? Math.min(100, Math.max(...allKdjValues) + 5) : 100;
        
        // MACD指标范围计算
        const allMacdValues = [...difData, ...deaData, ...macdData].filter(val => val !== null && val !== undefined);
        const macdMin = allMacdValues.length > 0 ? Math.min(...allMacdValues) * 1.2 : -1;
        const macdMax = allMacdValues.length > 0 ? Math.max(...allMacdValues) * 1.2 : 1;

        const option = {
            title: {
                text: `${stockCode} - ${strategy}策略分析`,
                left: 'center',
                textStyle: { fontSize: 16 }
            },
            tooltip: {
                trigger: 'axis',
                axisPointer: { type: 'cross' },
                backgroundColor: 'rgba(50, 50, 50, 0.9)',
                textStyle: { color: '#fff' }
            },
            legend: {
                data: ['K线', 'MA13', 'MA45', 'DIF', 'DEA', 'MACD', 'K', 'D', 'J', 'RSI6', 'RSI12', 'RSI24'],
                top: 30,
                textStyle: { fontSize: 12 }
            },
            grid: [
                { left: '8%', right: '5%', top: '8%', height: '35%' },      // K线和MA
                { left: '8%', right: '5%', top: '46%', height: '15%' },     // RSI指标
                { left: '8%', right: '5%', top: '64%', height: '15%' },     // KDJ指标
                { left: '8%', right: '5%', top: '82%', height: '15%' }      // MACD指标
            ],
            xAxis: [
                { 
                    type: 'category', 
                    data: dates, 
                    gridIndex: 0,
                    axisLabel: { show: false }
                },
                { 
                    type: 'category', 
                    data: dates, 
                    gridIndex: 1,
                    axisLabel: { show: false }
                },
                { 
                    type: 'category', 
                    data: dates, 
                    gridIndex: 2,
                    axisLabel: { show: false }
                },
                { 
                    type: 'category', 
                    data: dates, 
                    gridIndex: 3,
                    axisLabel: { fontSize: 10 }
                }
            ],
            yAxis: [
                { 
                    gridIndex: 0,
                    scale: true,
                    axisLabel: { fontSize: 10 }
                },
                { 
                    gridIndex: 1, 
                    max: rsiMax, 
                    min: rsiMin,
                    axisLabel: { fontSize: 10 },
                    splitLine: { show: true, lineStyle: { color: '#f0f0f0' } }
                },
                { 
                    gridIndex: 2, 
                    max: kdjMax, 
                    min: kdjMin,
                    axisLabel: { fontSize: 10 },
                    splitLine: { show: true, lineStyle: { color: '#f0f0f0' } }
                },
                { 
                    gridIndex: 3,
                    scale: true,
                    min: macdMin,
                    max: macdMax,
                    axisLabel: { fontSize: 10 },
                    splitLine: { show: true, lineStyle: { color: '#f0f0f0' } }
                }
            ],
            dataZoom: [
                { 
                    type: 'inside', 
                    xAxisIndex: [0, 1, 2, 3],
                    start: startPercent,
                    end: 100
                },
                { 
                    show: true, 
                    xAxisIndex: [0, 1, 2, 3], 
                    type: 'slider', 
                    bottom: '0%',
                    height: 20,
                    start: startPercent,
                    end: 100,
                    handleStyle: { color: '#007bff' },
                    textStyle: { fontSize: 10 }
                }
            ],
            series: [
                {
                    name: 'K线',
                    type: 'candlestick',
                    data: klineData,
                    xAxisIndex: 0,
                    yAxisIndex: 0
                },
                {
                    name: 'MA13',
                    type: 'line',
                    data: ma13Data,
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 1 },
                    xAxisIndex: 0,
                    yAxisIndex: 0
                },
                {
                    name: 'MA45',
                    type: 'line',
                    data: ma45Data,
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 1 },
                    xAxisIndex: 0,
                    yAxisIndex: 0
                },
                {
                    name: 'RSI6',
                    type: 'line',
                    data: rsi6Data,
                    smooth: true,
                    symbol: 'none',
                    xAxisIndex: 1,
                    yAxisIndex: 1,
                    lineStyle: { color: '#ff6b6b' }
                },
                {
                    name: 'RSI12',
                    type: 'line',
                    data: rsi12Data,
                    smooth: true,
                    symbol: 'none',
                    xAxisIndex: 1,
                    yAxisIndex: 1,
                    lineStyle: { color: '#4ecdc4' }
                },
                {
                    name: 'RSI24',
                    type: 'line',
                    data: rsi24Data,
                    smooth: true,
                    symbol: 'none',
                    xAxisIndex: 1,
                    yAxisIndex: 1,
                    lineStyle: { color: '#45b7d1' }
                },
                {
                    name: 'K',
                    type: 'line',
                    data: kData,
                    smooth: true,
                    symbol: 'none',
                    xAxisIndex: 2,
                    yAxisIndex: 2,
                    lineStyle: { color: '#f39c12' }
                },
                {
                    name: 'D',
                    type: 'line',
                    data: dData,
                    smooth: true,
                    symbol: 'none',
                    xAxisIndex: 2,
                    yAxisIndex: 2,
                    lineStyle: { color: '#e74c3c' }
                },
                {
                    name: 'J',
                    type: 'line',
                    data: jData,
                    smooth: true,
                    symbol: 'none',
                    xAxisIndex: 2,
                    yAxisIndex: 2,
                    lineStyle: { color: '#9b59b6' }
                },
                {
                    name: 'DIF',
                    type: 'line',
                    data: difData,
                    smooth: true,
                    symbol: 'none',
                    xAxisIndex: 3,
                    yAxisIndex: 3,
                    lineStyle: { color: '#2ecc71' }
                },
                {
                    name: 'DEA',
                    type: 'line',
                    data: deaData,
                    smooth: true,
                    symbol: 'none',
                    xAxisIndex: 3,
                    yAxisIndex: 3,
                    lineStyle: { color: '#e67e22' }
                },
                {
                    name: 'MACD',
                    type: 'bar',
                    data: macdData,
                    xAxisIndex: 3,
                    yAxisIndex: 3,
                    itemStyle: {
                        color: function(params) {
                            return params.value >= 0 ? '#ff6b6b' : '#4ecdc4';
                        }
                    },
                    barWidth: '60%'
                }
            ]
        };
        
        // 添加信号点
        if (signalData.length > 0) {
            const signalSeries = {
                name: '交易信号',
                type: 'scatter',
                data: signalData.map(signal => {
                    const dateIndex = dates.indexOf(signal.date);
                    return [dateIndex, signal.price];
                }),
                symbol: 'triangle',
                symbolSize: 10,
                itemStyle: {
                    color: function(params) {
                        const signal = signalData[params.dataIndex];
                        if (signal.state.includes('SUCCESS')) return '#00ff00';
                        if (signal.state.includes('FAIL')) return '#ff0000';
                        return '#ffff00';
                    }
                },
                xAxisIndex: 0,
                yAxisIndex: 0
            };
            option.series.push(signalSeries);
        }
        
        myChart.setOption(option, true);
    }
    
    function renderBacktestResults(backtest) {
        if (!backtest || !backtestContainer) return;
        
        backtestContainer.style.display = 'block';
        
        // 更新基本统计 - 后端已返回格式化字符串，直接使用
        const totalSignalsEl = document.getElementById('total-signals');
        const winRateEl = document.getElementById('win-rate');
        const avgMaxProfitEl = document.getElementById('avg-max-profit');
        const avgMaxDrawdownEl = document.getElementById('avg-max-drawdown');
        const avgDaysToPeakEl = document.getElementById('avg-days-to-peak');
        
        if (totalSignalsEl) totalSignalsEl.textContent = backtest.total_signals || 0;
        if (winRateEl) winRateEl.textContent = backtest.win_rate || '0%';
        if (avgMaxProfitEl) avgMaxProfitEl.textContent = backtest.avg_max_profit || '0%';
        if (avgMaxDrawdownEl) avgMaxDrawdownEl.textContent = backtest.avg_max_drawdown || '0%';
        if (avgDaysToPeakEl) avgDaysToPeakEl.textContent = backtest.avg_days_to_peak || '0天';
        
        // 更新状态统计 - 后端已返回格式化字符串，直接使用
        if (backtest.state_statistics) {
            const statsContent = document.getElementById('state-stats-content');
            if (statsContent) {
                let html = '<div class="stats-grid">';
                for (const [state, stats] of Object.entries(backtest.state_statistics)) {
                    html += `
                        <div class="stat-item">
                            <h5>${state}</h5>
                            <p>数量: ${stats.count}</p>
                            <p>胜率: ${stats.win_rate}</p>
                            <p>平均收益: ${stats.avg_max_profit}</p>
                            <p>平均回撤: ${stats.avg_max_drawdown}</p>
                            <p>平均天数: ${stats.avg_days_to_peak}</p>
                        </div>
                    `;
                }
                html += '</div>';
                statsContent.innerHTML = html;
            }
        }
    }


    // --- 交易建议功能 (统一版本) ---
    function loadTradingAdvice(stockCode, strategy) {
        // **修复点**: 这是数据加载的核心逻辑
        updateAdvicePanel({ action: 'LOADING' }); // 进入加载状态
        
        // 获取复权设置
        const adjustmentType = adjustmentSelect ? adjustmentSelect.value : 'forward';
        
        fetch(`/api/trading_advice/${stockCode}?strategy=${strategy}&adjustment=${adjustmentType}`)
            .then(response => response.json())
            .then(data => {
                if (data.error) throw new Error(data.error);
                updateAdvicePanel(data);
            })
            .catch(error => {
                console.error('Error loading trading advice:', error);
                updateAdvicePanel({ action: 'ERROR', logic: [error.message] });
            });
    }

    function updateAdvicePanel(advice) {
        // **修复点**: 这是统一的UI更新函数
        const actionEl = document.getElementById('action-recommendation');
        const logicEl = document.getElementById('analysis-logic');

        // 更新操作建议
        if (actionEl) {
            const actionClass = (advice.action || 'loading').toLowerCase();
            actionEl.className = `action-recommendation ${actionClass}`;
            let actionText = '...';
            let confidenceText = '';

            switch (advice.action) {
                case 'BUY': actionText = '🟢 建议买入'; break;
                case 'HOLD': actionText = '🟡 建议持有'; break;
                case 'WATCH': actionText = '🟠 继续观察'; break;
                case 'AVOID': actionText = '🔴 建议回避'; break;
                case 'LOADING': actionText = '🔄 分析中...'; break;
                case 'ERROR': actionText = '❌ 分析失败'; break;
                default: actionText = '❓ 未知状态';
            }
            if (advice.confidence) {
                confidenceText = `置信度: ${(advice.confidence * 100).toFixed(0)}%`;
            }
            actionEl.innerHTML = `<div class="action-text">${actionText}</div><div class="confidence-text">${confidenceText}</div>`;
        }
        
        // 更新价格信息
        const prices = {
            'entry-price': advice.entry_price, 'target-price': advice.target_price,
            'stop-price': advice.stop_price, 'current-price': advice.current_price,
            'resistance-level': advice.resistance_level, 'support-level': advice.support_level
        };
        for (const [id, value] of Object.entries(prices)) {
            const el = document.getElementById(id);
            if (el) {
                el.textContent = typeof value === 'number' ? `¥${value.toFixed(2)}` : '--';
            } else {
                console.warn(`Element with id '${id}' not found`);
            }
        }

        // 更新分析逻辑
        if (logicEl && advice.analysis_logic) {
            logicEl.innerHTML = advice.analysis_logic.map(logic => `
                <div class="logic-item">
                    <span class="logic-icon">•</span>
                    <span>${logic}</span>
                </div>
            `).join('');
        }
    }


    // --- 核心池管理功能 (统一版本) ---
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
                } else {
                    throw new Error(data.error);
                }
            })
            .catch(error => {
                console.error('Error loading core pool:', error);
                document.getElementById('core-pool-list').innerHTML = `<p>加载核心池失败: ${error.message}</p>`;
            });
    }

    function displayCorePoolData(pool) {
        const listContainer = document.getElementById('core-pool-list');
        if (!pool || pool.length === 0) {
            listContainer.innerHTML = '<p>核心池为空。</p>';
            return;
        }
        
        let html = '<table class="scan-results-table"><thead><tr><th>股票代码</th><th>添加时间</th><th>备注</th><th>操作</th></tr></thead><tbody>';
        pool.forEach(stock => {
            html += `
                <tr>
                    <td>${stock.stock_code}</td>
                    <td>${stock.added_time}</td>
                    <td>${stock.note || '-'}</td>
                    <td><button onclick="removeFromCorePool('${stock.stock_code}')" style="background: #dc3545; color: white; border: none; padding: 0.3rem 0.8rem; border-radius: 4px; cursor: pointer;">删除</button></td>
                </tr>
            `;
        });
        html += '</tbody></table>';
        listContainer.innerHTML = html;
    }

    // 全局函数，供HTML调用
    window.removeFromCorePool = function(stockCode) {
        if (!confirm(`确定要从核心池删除 ${stockCode} 吗？`)) return;
        fetch(`/api/core_pool?stock_code=${stockCode}`, { method: 'DELETE' })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert(data.message);
                    loadCorePoolData();
                } else {
                    alert(`删除失败: ${data.error}`);
                }
            })
            .catch(error => alert(`删除出错: ${error.message}`));
    };
    
    window.addToCorePool = function() {
        const stockCode = document.getElementById('new-stock-code').value.trim().toUpperCase();
        const note = document.getElementById('new-stock-note').value.trim();
        
        if (!stockCode) {
            alert('请输入股票代码');
            return;
        }
        
        fetch('/api/core_pool', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ stock_code: stockCode, note: note })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert(data.message);
                document.getElementById('new-stock-code').value = '';
                document.getElementById('new-stock-note').value = '';
                loadCorePoolData();
            } else {
                alert(`添加失败: ${data.error}`);
            }
        })
        .catch(error => alert(`添加出错: ${error.message}`));
    };

    // --- 其他模态框功能 ---
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

    function loadHistoryReports() {
        const strategy = strategySelect.value;
        fetch(`/api/history_reports?strategy=${strategy}`)
            .then(response => response.json())
            .then(data => {
                const content = document.getElementById('history-content');
                if (!data || data.length === 0) {
                    content.innerHTML = '<p>暂无历史报告</p>';
                    return;
                }
                
                let html = '<div class="history-reports">';
                data.forEach(report => {
                    const summary = report.scan_summary || {};
                    html += `
                        <div class="report-item" style="border: 1px solid #ddd; padding: 1rem; margin-bottom: 1rem; border-radius: 8px;">
                            <h4>扫描时间: ${summary.scan_timestamp || '未知'}</h4>
                            <p>扫描股票数: ${summary.total_scanned || 0}</p>
                            <p>信号数量: ${summary.total_signals || 0}</p>
                            <p>策略: ${summary.strategy || strategy}</p>
                        </div>
                    `;
                });
                html += '</div>';
                content.innerHTML = html;
            })
            .catch(error => {
                console.error('Error loading history reports:', error);
                document.getElementById('history-content').innerHTML = `<p>加载失败: ${error.message}</p>`;
            });
    }

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
            document.getElementById('multi-timeframe-content').innerHTML = '<p>请先选择股票</p>';
            return;
        }
        
        document.getElementById('multi-timeframe-content').innerHTML = '<p>加载中...</p>';
        
        fetch(`/api/multi_timeframe/${stockCode}?strategy=${strategy}`)
            .then(response => response.json())
            .then(data => {
                const content = document.getElementById('multi-timeframe-content');
                if (data.error) {
                    content.innerHTML = `<p>分析失败: ${data.error}</p>`;
                    return;
                }
                
                let html = '<div class="multi-timeframe-results">';
                if (data.analysis) {
                    for (const [timeframe, analysis] of Object.entries(data.analysis)) {
                        html += `
                            <div class="timeframe-item" style="border: 1px solid #ddd; padding: 1rem; margin-bottom: 1rem; border-radius: 8px;">
                                <h4>${timeframe} 周期分析</h4>
                                <p>趋势: ${analysis.trend || '未知'}</p>
                                <p>强度: ${analysis.strength || '未知'}</p>
                                <p>建议: ${analysis.recommendation || '未知'}</p>
                            </div>
                        `;
                    }
                }
                html += '</div>';
                content.innerHTML = html;
            })
            .catch(error => {
                console.error('Error loading multi-timeframe analysis:', error);
                document.getElementById('multi-timeframe-content').innerHTML = `<p>加载失败: ${error.message}</p>`;
            });
    }

    // --- 深度扫描功能 ---
    function runDeepScan() {
        if (!confirm('深度扫描需要较长时间，确定要开始吗？')) return;
        
        fetch('/api/run_deep_scan', { method: 'POST' })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert('深度扫描已启动，请稍后查看结果');
                    setTimeout(loadDeepScanResults, 5000); // 5秒后刷新结果
                } else {
                    alert(`启动失败: ${data.error || '未知错误'}`);
                }
            })
            .catch(error => {
                console.error('Error running deep scan:', error);
                alert(`启动出错: ${error.message}`);
            });
    }

    function loadDeepScanResults() {
        if (!deepScanSection) return;
        
        fetch('/api/deep_scan_results')
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    deepScanSection.innerHTML = `<p>暂无深度扫描结果: ${data.error}</p>`;
                    deepScanSection.style.display = 'block';
                    return;
                }
                
                const results = data.results || [];
                const summary = data.summary || {};
                
                let html = `
                    <h3>深度扫描结果</h3>
                    <div class="scan-summary" style="margin-bottom: 1rem; padding: 1rem; background: #f8f9fa; border-radius: 8px;">
                        <p>总分析数: ${summary.total_analyzed || 0} | A级股票: ${summary.a_grade_count || 0} | 买入推荐: ${summary.buy_recommendations || 0}</p>
                    </div>
                `;
                
                if (results.length > 0) {
                    html += '<table class="scan-results-table"><thead><tr><th>股票代码</th><th>评分</th><th>等级</th><th>建议</th><th>置信度</th><th>当前价格</th></tr></thead><tbody>';
                    results.slice(0, 20).forEach(result => { // 只显示前20个结果
                        html += `
                            <tr>
                                <td><a href="#" class="stock-code-link" data-stock-code="${result.stock_code}" style="color: #007bff; text-decoration: none; cursor: pointer;">${result.stock_code}</a></td>
                                <td>${result.score.toFixed(2)}</td>
                                <td><span class="grade-${result.grade.toLowerCase()}">${result.grade}</span></td>
                                <td>${result.action}</td>
                                <td>${(result.confidence * 100).toFixed(0)}%</td>
                                <td>¥${result.current_price.toFixed(2)}</td>
                            </tr>
                        `;
                    });
                    html += '</tbody></table>';
                    
                    // 添加点击事件监听器
                    setTimeout(() => {
                        document.querySelectorAll('.stock-code-link').forEach(link => {
                            link.addEventListener('click', function(e) {
                                e.preventDefault();
                                const stockCode = this.getAttribute('data-stock-code');
                                selectStockAndShowChart(stockCode);
                            });
                        });
                    }, 100);
                } else {
                    html += '<p>暂无扫描结果</p>';
                }
                
                deepScanSection.innerHTML = html;
                deepScanSection.style.display = 'block';
            })
            .catch(error => {
                console.error('Error loading deep scan results:', error);
                deepScanSection.innerHTML = `<p>加载深度扫描结果失败: ${error.message}</p>`;
                deepScanSection.style.display = 'block';
            });
    }
    
    // --- 股票选择和图表显示功能 ---
    function selectStockAndShowChart(stockCode) {
        // 首先检查股票是否在当前策略的信号列表中
        const currentOptions = Array.from(stockSelect.options);
        const matchingOption = currentOptions.find(option => option.value === stockCode);
        
        if (matchingOption) {
            // 如果在当前策略中找到，直接选择
            stockSelect.value = stockCode;
            loadChart();
            
            // 滚动到图表区域
            chartContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
        } else {
            // 如果不在当前策略中，尝试添加到选择列表并选择
            const option = document.createElement('option');
            option.value = stockCode;
            option.textContent = `${stockCode} (深度扫描)`;
            stockSelect.appendChild(option);
            
            stockSelect.value = stockCode;
            loadChart();
            
            // 滚动到图表区域
            chartContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
            
            // 显示提示信息
            setTimeout(() => {
                alert(`已加载 ${stockCode} 的图表分析`);
            }, 500);
        }
    }

    // --- 初始化 ---
    populateStockList();
    loadDeepScanResults(); // 加载深度扫描结果
});