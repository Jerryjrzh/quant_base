document.addEventListener('DOMContentLoaded', function () {
    // --- DOM元素获取 ---
    const stockSelect = document.getElementById('stock-select');
    const strategySelect = document.getElementById('strategy-select');
    const adjustmentSelect = document.getElementById('adjustment-select');
    const timeframeSelect = document.getElementById('timeframe-select');
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
    
    // 周期设置变化时重新加载图表
    if (timeframeSelect) timeframeSelect.addEventListener('change', () => {
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

        // 获取复权设置和周期设置
        const adjustmentType = adjustmentSelect ? adjustmentSelect.value : 'forward';
        const timeframe = timeframeSelect ? timeframeSelect.value : 'daily';
        
        fetch(`/api/analysis/${stockCode}?strategy=${strategy}&adjustment=${adjustmentType}&timeframe=${timeframe}`)
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
        
        // 计算各指标的动态范围 - 修复版本
        // RSI指标范围计算 (0-100范围，适当扩展)
        const allRsiValues = [...rsi6Data, ...rsi12Data, ...rsi24Data].filter(val => val !== null && val !== undefined && !isNaN(val));
        const rsiMin = allRsiValues.length > 0 ? Math.max(0, Math.min(...allRsiValues) - 5) : 0;
        const rsiMax = allRsiValues.length > 0 ? Math.min(100, Math.max(...allRsiValues) + 5) : 100;
        
        // KDJ指标范围计算 - 修复：允许显示负值，不限制下限为0
        const allKdjValues = [...kData, ...dData, ...jData].filter(val => val !== null && val !== undefined && !isNaN(val));
        let kdjMin = -10; // 默认下限，允许显示负值
        let kdjMax = 110;  // 默认上限，允许超过100
        
        if (allKdjValues.length > 0) {
            const actualMin = Math.min(...allKdjValues);
            const actualMax = Math.max(...allKdjValues);
            
            // 动态调整范围，确保负值和超过100的值都能显示
            kdjMin = actualMin < 0 ? actualMin - 5 : Math.max(-10, actualMin - 5);
            kdjMax = actualMax > 100 ? actualMax + 5 : Math.min(110, actualMax + 5);
        }
        
        // MACD指标范围计算 - 修复：改进范围计算，避免顶部异常
        const allMacdValues = [...difData, ...deaData, ...macdData].filter(val => val !== null && val !== undefined && !isNaN(val));
        let macdMin = -1;
        let macdMax = 1;
        
        if (allMacdValues.length > 0) {
            const actualMin = Math.min(...allMacdValues);
            const actualMax = Math.max(...allMacdValues);
            
            // 使用更合理的范围扩展策略
            const range = actualMax - actualMin;
            const padding = Math.max(range * 0.1, 0.01); // 至少10%的边距，最小0.01
            
            macdMin = actualMin - padding;
            macdMax = actualMax + padding;
            
            // 确保范围不会过小
            if (Math.abs(macdMax - macdMin) < 0.02) {
                const center = (macdMax + macdMin) / 2;
                macdMin = center - 0.01;
                macdMax = center + 0.01;
            }
        }

        // 获取当前周期设置用于标题显示
        const timeframe = timeframeSelect ? timeframeSelect.value : 'daily';
        const timeframeText = {
            'daily': '日线',
            'weekly': '周线', 
            'monthly': '月线',
            '5min': '5分钟',
            '10min': '10分钟',
            '15min': '15分钟',
            '30min': '30分钟',
            '60min': '60分钟'
        }[timeframe] || '日线';
        
        const option = {
            title: {
                text: `${stockCode} - ${strategy}策略分析 (${timeframeText})`,
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
            // 添加指标标注
            graphic: [
                {
                    type: 'text',
                    left: '8%',
                    top: '8%',
                    style: {
                        text: 'K线 & MA(13,45)',
                        fontSize: 12,
                        fontWeight: 'bold',
                        fill: '#666'
                    }
                },
                {
                    type: 'text',
                    left: '8%',
                    top: '46%',
                    style: {
                        text: 'RSI(6,12,24)',
                        fontSize: 12,
                        fontWeight: 'bold',
                        fill: '#666'
                    }
                },
                {
                    type: 'text',
                    left: '8%',
                    top: '64%',
                    style: {
                        text: 'KDJ(27,3,3)',
                        fontSize: 12,
                        fontWeight: 'bold',
                        fill: '#666'
                    }
                },
                {
                    type: 'text',
                    left: '8%',
                    top: '82%',
                    style: {
                        text: 'MACD(12,26,9)',
                        fontSize: 12,
                        fontWeight: 'bold',
                        fill: '#666'
                    }
                }
            ],
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
        
        // 添加信号点 - 修复版本
        if (signalData.length > 0) {
            const signalSeries = {
                name: '交易信号',
                type: 'scatter',
                data: signalData.map(signal => {
                    const dateIndex = dates.indexOf(signal.date);
                    return [dateIndex, signal.price];
                }).filter(point => point[0] >= 0), // 过滤无效的日期索引
                symbol: 'triangle',
                symbolSize: 12, // 稍微增大图标
                itemStyle: {
                    color: function(params) {
                        const signal = signalData[params.dataIndex];
                        if (!signal) return '#888888';
                        
                        // 更清晰的颜色区分
                        if (signal.state && signal.state.includes('SUCCESS')) return '#00cc00';
                        if (signal.state && signal.state.includes('FAIL')) return '#cc0000';
                        return '#ff9900'; // 橙色表示待确认
                    },
                    borderColor: '#ffffff',
                    borderWidth: 1
                },
                emphasis: {
                    itemStyle: {
                        shadowBlur: 10,
                        shadowColor: 'rgba(0, 0, 0, 0.5)'
                    }
                },
                tooltip: {
                    formatter: function(params) {
                        const signal = signalData[params.dataIndex];
                        if (!signal) return '';
                        return `
                            <div style="text-align: left;">
                                <strong>交易信号</strong><br/>
                                日期: ${signal.date}<br/>
                                价格: ¥${signal.price.toFixed(2)}<br/>
                                状态: ${signal.state || '待确认'}
                            </div>
                        `;
                    }
                },
                xAxisIndex: 0,
                yAxisIndex: 0,
                z: 10 // 确保信号点在最上层
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
        
        // 获取复权设置和周期设置
        const adjustmentType = adjustmentSelect ? adjustmentSelect.value : 'forward';
        const timeframe = timeframeSelect ? timeframeSelect.value : 'daily';
        
        fetch(`/api/trading_advice/${stockCode}?strategy=${strategy}&adjustment=${adjustmentType}&timeframe=${timeframe}`)
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
        const stockCode = document.getElementById('new-stock-code').value.trim().toLowerCase();
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

    // --- 持仓管理功能 ---
    const portfolioBtn = document.getElementById('portfolio-btn');
    const portfolioModal = document.getElementById('portfolio-modal');
    const portfolioClose = document.getElementById('portfolio-close');
    const addPositionModal = document.getElementById('add-position-modal');
    const addPositionClose = document.getElementById('add-position-close');
    const positionDetailModal = document.getElementById('position-detail-modal');
    const positionDetailClose = document.getElementById('position-detail-close');
    const riskAssessmentModal = document.getElementById('risk-assessment-modal');
    const riskAssessmentClose = document.getElementById('risk-assessment-close');
    
    // 持仓管理事件监听
    if (portfolioBtn) portfolioBtn.addEventListener('click', showPortfolioModal);
    if (portfolioClose) portfolioClose.addEventListener('click', hidePortfolioModal);
    if (addPositionClose) addPositionClose.addEventListener('click', hideAddPositionModal);
    if (positionDetailClose) positionDetailClose.addEventListener('click', hidePositionDetailModal);
    if (riskAssessmentClose) riskAssessmentClose.addEventListener('click', hideRiskAssessmentModal);
    
    // 添加持仓相关事件
    const addPositionBtn = document.getElementById('add-position-btn');
    const scanPortfolioBtn = document.getElementById('scan-portfolio-btn');
    const refreshPortfolioBtn = document.getElementById('refresh-portfolio-btn');
    const cancelAddPositionBtn = document.getElementById('cancel-add-position');
    const addPositionForm = document.getElementById('add-position-form');
    
    if (addPositionBtn) addPositionBtn.addEventListener('click', showAddPositionModal);
    if (scanPortfolioBtn) scanPortfolioBtn.addEventListener('click', scanPortfolio);
    if (refreshPortfolioBtn) refreshPortfolioBtn.addEventListener('click', loadPortfolioData);
    if (cancelAddPositionBtn) cancelAddPositionBtn.addEventListener('click', hideAddPositionModal);
    if (addPositionForm) addPositionForm.addEventListener('submit', handleAddPosition);
    
    // 点击模态框外部关闭
    window.addEventListener('click', (event) => {
        if (event.target === portfolioModal) hidePortfolioModal();
        if (event.target === addPositionModal) hideAddPositionModal();
        if (event.target === positionDetailModal) hidePositionDetailModal();
        if (event.target === riskAssessmentModal) hideRiskAssessmentModal();
    });
    
    function showPortfolioModal() {
        if (portfolioModal) {
            portfolioModal.style.display = 'block';
            loadPortfolioData();
        }
    }
    
    function hidePortfolioModal() {
        if (portfolioModal) {
            portfolioModal.style.display = 'none';
        }
    }
    
    function showAddPositionModal() {
        if (addPositionModal) {
            addPositionModal.style.display = 'block';
            // 设置默认购买日期为今天
            const today = new Date().toISOString().split('T')[0];
            document.getElementById('position-purchase-date').value = today;
        }
    }
    
    function hideAddPositionModal() {
        if (addPositionModal) {
            addPositionModal.style.display = 'none';
            // 清空表单
            document.getElementById('add-position-form').reset();
        }
    }
    
    function showPositionDetailModal(stockCode) {
        if (positionDetailModal) {
            positionDetailModal.style.display = 'block';
            document.getElementById('position-detail-title').textContent = `${stockCode} 持仓详情`;
            loadPositionDetail(stockCode);
        }
    }
    
    function hidePositionDetailModal() {
        if (positionDetailModal) {
            positionDetailModal.style.display = 'none';
        }
    }
    
    function showRiskAssessmentDetail(stockCode, riskLevel) {
        if (riskAssessmentModal) {
            riskAssessmentModal.style.display = 'block';
            document.getElementById('risk-assessment-title').textContent = `${stockCode} 风险评估详情`;
            loadRiskAssessmentDetail(stockCode);
        }
    }
    
    function hideRiskAssessmentModal() {
        if (riskAssessmentModal) {
            riskAssessmentModal.style.display = 'none';
        }
    }
    
    function loadRiskAssessmentDetail(stockCode) {
        const content = document.getElementById('risk-assessment-content');
        content.innerHTML = '<div style="text-align: center; padding: 2rem;">加载中...</div>';
        
        fetch(`/api/portfolio/analysis/${stockCode}`)
            .then(response => response.json())
            .then(data => {
                if (data.success && data.analysis.risk_assessment) {
                    displayRiskAssessmentDetail(data.analysis.risk_assessment, stockCode);
                } else {
                    content.innerHTML = `<p style="color: #dc3545;">加载失败: ${data.error || '无风险评估数据'}</p>`;
                }
            })
            .catch(error => {
                console.error('Error loading risk assessment:', error);
                content.innerHTML = `<p style="color: #dc3545;">加载出错: ${error.message}</p>`;
            });
    }
    
    function displayRiskAssessmentDetail(riskAssessment, stockCode) {
        const content = document.getElementById('risk-assessment-content');
        
        if (!riskAssessment) {
            content.innerHTML = '<p style="color: #dc3545;">无风险评估数据</p>';
            return;
        }
        
        const riskLevel = riskAssessment.risk_level || 'UNKNOWN';
        const riskScore = riskAssessment.risk_score || 0;
        const volatility = riskAssessment.volatility || 0;
        const maxDrawdown = riskAssessment.max_drawdown || 0;
        const pricePositionPct = riskAssessment.price_position_pct || 0;
        const riskFactors = riskAssessment.risk_factors || [];
        
        // 确定风险等级的样式类
        const riskScoreClass = riskLevel.toLowerCase() === 'high' ? 'risk-score-high' : 
                              riskLevel.toLowerCase() === 'medium' ? 'risk-score-medium' : 'risk-score-low';
        
        let html = `
            <div class="risk-detail-grid">
                <div class="risk-detail-section">
                    <h4>风险等级评估</h4>
                    <div class="risk-score-display ${riskScoreClass}">
                        ${getRiskText(riskLevel)}
                        <div style="font-size: 1rem; margin-top: 0.5rem;">
                            风险评分: ${riskScore}/9
                        </div>
                    </div>
                    <div style="text-align: center; color: #6c757d; font-size: 0.9rem;">
                        ${getRiskLevelDescription(riskLevel)}
                    </div>
                </div>
                
                <div class="risk-detail-section">
                    <h4>风险指标</h4>
                    <div style="display: grid; gap: 0.8rem;">
                        <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.5rem; background: white; border-radius: 4px;">
                            <span>年化波动率:</span>
                            <span style="font-weight: 600; color: ${volatility > 40 ? '#dc3545' : volatility > 25 ? '#ffc107' : '#28a745'};">
                                ${volatility.toFixed(2)}%
                            </span>
                        </div>
                        <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.5rem; background: white; border-radius: 4px;">
                            <span>最大回撤:</span>
                            <span style="font-weight: 600; color: ${maxDrawdown > 20 ? '#dc3545' : maxDrawdown > 10 ? '#ffc107' : '#28a745'};">
                                ${maxDrawdown.toFixed(2)}%
                            </span>
                        </div>
                        <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.5rem; background: white; border-radius: 4px;">
                            <span>价格位置:</span>
                            <span style="font-weight: 600; color: ${pricePositionPct > 80 ? '#dc3545' : pricePositionPct < 20 ? '#28a745' : '#6c757d'};">
                                ${pricePositionPct.toFixed(1)}%
                            </span>
                        </div>
                    </div>
                </div>
                
                <div class="risk-detail-section" style="grid-column: 1 / -1;">
                    <h4>风险因素分析</h4>
                    ${riskFactors.length > 0 ? `
                        <ul class="risk-factor-list">
                            ${riskFactors.map(factor => `<li>• ${factor}</li>`).join('')}
                        </ul>
                    ` : '<p style="color: #6c757d; font-style: italic;">暂无具体风险因素分析</p>'}
                </div>
                
                <div class="risk-detail-section" style="grid-column: 1 / -1;">
                    <h4>风险管理建议</h4>
                    <div style="background: white; padding: 1rem; border-radius: 4px; border-left: 4px solid #007bff;">
                        ${getRiskManagementAdvice(riskLevel, volatility, maxDrawdown, pricePositionPct)}
                    </div>
                </div>
            </div>
        `;
        
        content.innerHTML = html;
    }
    
    function getRiskLevelDescription(riskLevel) {
        switch (riskLevel) {
            case 'HIGH':
                return '高风险：建议谨慎操作，密切关注市场变化';
            case 'MEDIUM':
                return '中等风险：适度关注，注意风险控制';
            case 'LOW':
                return '低风险：相对安全，可适当持有';
            default:
                return '风险等级未知';
        }
    }
    
    function getRiskManagementAdvice(riskLevel, volatility, maxDrawdown, pricePosition) {
        let advice = [];
        
        if (riskLevel === 'HIGH') {
            advice.push('• 建议设置较紧的止损位，控制下行风险');
            advice.push('• 考虑分批减仓，降低仓位风险');
            advice.push('• 密切关注市场情绪和技术面变化');
        } else if (riskLevel === 'MEDIUM') {
            advice.push('• 保持适中仓位，避免过度集中');
            advice.push('• 设置合理的止损和止盈位');
            advice.push('• 定期评估持仓风险状况');
        } else {
            advice.push('• 可适当持有，但仍需关注市场变化');
            advice.push('• 考虑在合适时机适度加仓');
            advice.push('• 保持长期投资心态');
        }
        
        if (volatility > 40) {
            advice.push('• 高波动率提示：注意短期价格剧烈波动风险');
        }
        
        if (maxDrawdown > 20) {
            advice.push('• 大幅回撤提示：历史最大回撤较大，需要心理准备');
        }
        
        if (pricePosition > 80) {
            advice.push('• 高位提示：当前价格接近近期高点，注意回调风险');
        } else if (pricePosition < 20) {
            advice.push('• 低位提示：当前价格接近近期低点，可能存在反弹机会');
        }
        
        return advice.join('<br>');
    }
    
    function loadPortfolioData() {
        const content = document.getElementById('portfolio-content');
        const loading = document.getElementById('portfolio-loading');
        
        if (loading) loading.style.display = 'block';
        
        fetch('/api/portfolio')
            .then(response => response.json())
            .then(data => {
                if (loading) loading.style.display = 'none';
                
                if (data.success) {
                    displayPortfolioData(data.portfolio);
                    updatePortfolioSummary(data.portfolio);
                } else {
                    throw new Error(data.error);
                }
            })
            .catch(error => {
                if (loading) loading.style.display = 'none';
                console.error('Error loading portfolio:', error);
                content.innerHTML = `<p style="color: #dc3545;">加载持仓列表失败: ${error.message}</p>`;
            });
    }
    
    function displayPortfolioData(portfolio) {
        const content = document.getElementById('portfolio-content');
        
        if (!portfolio || portfolio.length === 0) {
            content.innerHTML = '<p style="text-align: center; color: #6c757d; padding: 2rem;">暂无持仓记录</p>';
            return;
        }
        
        let html = `
            <table class="portfolio-table">
                <thead>
                    <tr>
                        <th>股票代码</th>
                        <th>购买价格</th>
                        <th>持仓数量</th>
                        <th>购买日期</th>
                        <th>当前价格</th>
                        <th>盈亏</th>
                        <th>操作建议</th>
                        <th>风险等级</th>
                        <th>备注</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
        `;
        
        portfolio.forEach(position => {
            const profitLoss = position.profit_loss_pct || 0;
            const profitClass = profitLoss > 0 ? 'profit-positive' : profitLoss < 0 ? 'profit-negative' : 'profit-neutral';
            const currentPrice = position.current_price || '--';
            const action = position.position_advice?.action || 'UNKNOWN';
            const riskLevel = position.risk_assessment?.risk_level || 'UNKNOWN';
            
            html += `
                <tr>
                    <td>
                        <a href="#" class="stock-code-link" onclick="showPositionDetailModal('${position.stock_code}')">${position.stock_code}</a>
                    </td>
                    <td>¥${position.purchase_price.toFixed(2)}</td>
                    <td>${position.quantity}</td>
                    <td>${position.purchase_date}</td>
                    <td>${typeof currentPrice === 'number' ? '¥' + currentPrice.toFixed(2) : currentPrice}</td>
                    <td class="${profitClass}">${profitLoss.toFixed(2)}%</td>
                    <td><span class="action-${action.toLowerCase()}">${getActionText(action)}</span></td>
                    <td><span class="risk-${riskLevel.toLowerCase()}">${getRiskText(riskLevel)}</span></td>
                    <td>${position.note || '-'}</td>
                    <td>
                        <button onclick="editPosition('${position.stock_code}')" style="background: #007bff; color: white; border: none; padding: 0.2rem 0.5rem; border-radius: 3px; cursor: pointer; margin-right: 0.3rem;">编辑</button>
                        <button onclick="removePosition('${position.stock_code}')" style="background: #dc3545; color: white; border: none; padding: 0.2rem 0.5rem; border-radius: 3px; cursor: pointer;">删除</button>
                    </td>
                </tr>
            `;
        });
        
        html += '</tbody></table>';
        content.innerHTML = html;
    }
    
    function updatePortfolioSummary(portfolio) {
        const summaryEl = document.getElementById('portfolio-summary');
        if (!summaryEl) return;
        
        const totalPositions = portfolio.length;
        const profitableCount = portfolio.filter(p => (p.profit_loss_pct || 0) > 0).length;
        const lossCount = portfolio.filter(p => (p.profit_loss_pct || 0) < 0).length;
        
        summaryEl.innerHTML = `
            总持仓: ${totalPositions} | 
            盈利: <span class="profit-positive">${profitableCount}</span> | 
            亏损: <span class="profit-negative">${lossCount}</span>
        `;
    }
    
    function getActionText(action) {
        const actionMap = {
            'BUY': '买入',
            'SELL': '卖出',
            'HOLD': '持有',
            'WATCH': '观察',
            'ADD': '加仓',
            'REDUCE': '减仓',
            'STOP_LOSS': '止损',
            'UNKNOWN': '未知'
        };
        return actionMap[action] || action;
    }
    
    function getRiskText(risk) {
        const riskMap = {
            'HIGH': '高风险',
            'MEDIUM': '中风险',
            'LOW': '低风险',
            'UNKNOWN': '未知'
        };
        return riskMap[risk] || risk;
    }
    
    function handleAddPosition(event) {
        event.preventDefault();
        
        const formData = new FormData(event.target);
        const positionData = {
            stock_code: document.getElementById('position-stock-code').value.trim().toLowerCase(),
            purchase_price: parseFloat(document.getElementById('position-purchase-price').value),
            quantity: parseInt(document.getElementById('position-quantity').value),
            purchase_date: document.getElementById('position-purchase-date').value,
            note: document.getElementById('position-note').value.trim()
        };
        
        fetch('/api/portfolio', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(positionData)
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert(data.message);
                hideAddPositionModal();
                loadPortfolioData();
            } else {
                alert(`添加失败: ${data.error}`);
            }
        })
        .catch(error => {
            console.error('Error adding position:', error);
            alert(`添加出错: ${error.message}`);
        });
    }
    
    function scanPortfolio() {
        if (!confirm('持仓深度扫描需要较长时间，确定要开始吗？')) return;
        
        const scanBtn = document.getElementById('scan-portfolio-btn');
        const originalText = scanBtn.textContent;
        scanBtn.textContent = '扫描中...';
        scanBtn.disabled = true;
        
        fetch('/api/portfolio/scan', { method: 'POST' })
            .then(response => response.json())
            .then(data => {
                scanBtn.textContent = originalText;
                scanBtn.disabled = false;
                
                if (data.success) {
                    displayScanResults(data.results);
                } else {
                    alert(`扫描失败: ${data.error}`);
                }
            })
            .catch(error => {
                scanBtn.textContent = originalText;
                scanBtn.disabled = false;
                console.error('Error scanning portfolio:', error);
                alert(`扫描出错: ${error.message}`);
            });
    }
    
    function displayScanResults(results) {
        const content = document.getElementById('portfolio-content');
        
        // 显示扫描汇总
        let html = `
            <div class="scan-summary">
                <div class="scan-summary-item">
                    <div class="scan-summary-value">${results.total_positions}</div>
                    <div class="scan-summary-label">总持仓</div>
                </div>
                <div class="scan-summary-item">
                    <div class="scan-summary-value">${results.summary.profitable_count}</div>
                    <div class="scan-summary-label">盈利</div>
                </div>
                <div class="scan-summary-item">
                    <div class="scan-summary-value">${results.summary.loss_count}</div>
                    <div class="scan-summary-label">亏损</div>
                </div>
                <div class="scan-summary-item">
                    <div class="scan-summary-value">${results.summary.total_profit_loss.toFixed(2)}%</div>
                    <div class="scan-summary-label">总盈亏</div>
                </div>
                <div class="scan-summary-item">
                    <div class="scan-summary-value">${results.summary.high_risk_count}</div>
                    <div class="scan-summary-label">高风险</div>
                </div>
                <div class="scan-summary-item">
                    <div class="scan-summary-value">${results.summary.action_required_count}</div>
                    <div class="scan-summary-label">需要操作</div>
                </div>
            </div>
        `;
        
        // 显示详细持仓列表
        if (results.positions && results.positions.length > 0) {
            html += `
                <table class="portfolio-table">
                    <thead>
                        <tr>
                            <th>股票代码</th>
                            <th>购买价格</th>
                            <th>当前价格</th>
                            <th>盈亏</th>
                            <th>操作建议</th>
                            <th>置信度</th>
                            <th>风险等级</th>
                            <th>支撑位</th>
                            <th>阻力位</th>
                            <th>补仓价</th>
                            <th>减仓价</th>
                            <th>预期到顶</th>
                            <th>操作</th>
                        </tr>
                    </thead>
                    <tbody>
            `;
            
            results.positions.forEach(position => {
                if (position.error) {
                    html += `
                        <tr>
                            <td>${position.stock_code}</td>
                            <td colspan="10" style="color: #dc3545;">${position.error}</td>
                        </tr>
                    `;
                    return;
                }
                
                const profitLoss = position.profit_loss_pct || 0;
                const profitClass = profitLoss > 0 ? 'profit-positive' : profitLoss < 0 ? 'profit-negative' : 'profit-neutral';
                const action = position.position_advice?.action || 'UNKNOWN';
                const confidence = position.position_advice?.confidence || 0;
                const riskLevel = position.risk_assessment?.risk_level || 'UNKNOWN';
                const addPrice = position.position_advice?.add_position_price;
                const reducePrice = position.position_advice?.reduce_position_price;
                const expectedPeakDate = position.timing_analysis?.expected_peak_date;
                
                // 获取支撑阻力位信息
                const supportLevel = position.price_targets?.next_support;
                const resistanceLevel = position.price_targets?.next_resistance;
                
                html += `
                    <tr>
                        <td>
                            <a href="#" class="stock-code-link" onclick="showPositionDetailModal('${position.stock_code}')">${position.stock_code}</a>
                        </td>
                        <td>¥${position.purchase_price.toFixed(2)}</td>
                        <td>¥${position.current_price.toFixed(2)}</td>
                        <td class="${profitClass}">${profitLoss.toFixed(2)}%</td>
                        <td><span class="action-${action.toLowerCase()}">${getActionText(action)}</span></td>
                        <td>${(confidence * 100).toFixed(0)}%</td>
                        <td>
                            <span class="risk-${riskLevel.toLowerCase()} risk-clickable" 
                                  onclick="showRiskAssessmentDetail('${position.stock_code}', '${riskLevel}')" 
                                  title="点击查看风险评估详情">
                                ${getRiskText(riskLevel)}
                            </span>
                        </td>
                        <td>${supportLevel ? '¥' + supportLevel.toFixed(2) : '--'}</td>
                        <td>${resistanceLevel ? '¥' + resistanceLevel.toFixed(2) : '--'}</td>
                        <td>${addPrice ? '¥' + addPrice.toFixed(2) : '--'}</td>
                        <td>${reducePrice ? '¥' + reducePrice.toFixed(2) : '--'}</td>
                        <td>${expectedPeakDate || '--'}</td>
                        <td>
                            <button onclick="showPositionDetailModal('${position.stock_code}')" style="background: #28a745; color: white; border: none; padding: 0.2rem 0.5rem; border-radius: 3px; cursor: pointer;">详情</button>
                        </td>
                    </tr>
                `;
            });
            
            html += '</tbody></table>';
        }
        
        content.innerHTML = html;
    }
    
    function loadPositionDetail(stockCode) {
        const content = document.getElementById('position-detail-content');
        content.innerHTML = '<div style="text-align: center; padding: 2rem;">加载中...</div>';
        
        fetch(`/api/portfolio/analysis/${stockCode}`)
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    displayPositionDetail(data.analysis);
                } else {
                    content.innerHTML = `<p style="color: #dc3545;">加载失败: ${data.error}</p>`;
                }
            })
            .catch(error => {
                console.error('Error loading position detail:', error);
                content.innerHTML = `<p style="color: #dc3545;">加载出错: ${error.message}</p>`;
            });
    }
    
    function displayPositionDetail(analysis) {
        const content = document.getElementById('position-detail-content');
        
        if (analysis.error) {
            content.innerHTML = `<p style="color: #dc3545;">${analysis.error}</p>`;
            return;
        }
        
        const profitLoss = analysis.profit_loss_pct || 0;
        const profitClass = profitLoss > 0 ? 'profit-positive' : profitLoss < 0 ? 'profit-negative' : 'profit-neutral';
        
        let html = `
            <div class="position-detail-grid">
                <div class="detail-section">
                    <h4>基本信息</h4>
                    <div class="detail-item">
                        <span class="detail-label">股票代码:</span>
                        <span class="detail-value">${analysis.stock_code}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">购买价格:</span>
                        <span class="detail-value">¥${analysis.purchase_price.toFixed(2)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">当前价格:</span>
                        <span class="detail-value">¥${analysis.current_price.toFixed(2)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">盈亏比例:</span>
                        <span class="detail-value ${profitClass}">${profitLoss.toFixed(2)}%</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">持仓天数:</span>
                        <span class="detail-value">${analysis.timing_analysis?.holding_days || 0}天</span>
                    </div>
                </div>
                
                <div class="detail-section">
                    <h4>操作建议</h4>
                    <div class="detail-item">
                        <span class="detail-label">建议操作:</span>
                        <span class="detail-value action-${analysis.position_advice?.action?.toLowerCase()}">${getActionText(analysis.position_advice?.action)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">置信度:</span>
                        <span class="detail-value">${((analysis.position_advice?.confidence || 0) * 100).toFixed(0)}%</span>
                    </div>
        `;
        
        if (analysis.position_advice?.add_position_price) {
            html += `
                <div class="detail-item">
                    <span class="detail-label">建议补仓价:</span>
                    <span class="detail-value">¥${analysis.position_advice.add_position_price.toFixed(2)}</span>
                </div>
            `;
        }
        
        if (analysis.position_advice?.reduce_position_price) {
            html += `
                <div class="detail-item">
                    <span class="detail-label">建议减仓价:</span>
                    <span class="detail-value">¥${analysis.position_advice.reduce_position_price.toFixed(2)}</span>
                </div>
            `;
        }
        
        if (analysis.position_advice?.stop_loss_price) {
            html += `
                <div class="detail-item">
                    <span class="detail-label">止损价位:</span>
                    <span class="detail-value">¥${analysis.position_advice.stop_loss_price.toFixed(2)}</span>
                </div>
            `;
        }
        
        html += `
                    <div class="advice-reasons">
                        <h5>操作理由:</h5>
                        <ul>
        `;
        
        if (analysis.position_advice?.reasons) {
            analysis.position_advice.reasons.forEach(reason => {
                html += `<li>${reason}</li>`;
            });
        }
        
        html += `
                        </ul>
                    </div>
                </div>
                
                <div class="detail-section">
                    <h4>风险评估</h4>
                    <div class="detail-item">
                        <span class="detail-label">风险等级:</span>
                        <span class="detail-value risk-${analysis.risk_assessment?.risk_level?.toLowerCase()}">${getRiskText(analysis.risk_assessment?.risk_level)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">波动率:</span>
                        <span class="detail-value">${(analysis.risk_assessment?.volatility || 0).toFixed(2)}%</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">最大回撤:</span>
                        <span class="detail-value">${(analysis.risk_assessment?.max_drawdown || 0).toFixed(2)}%</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">价格位置:</span>
                        <span class="detail-value">${(analysis.risk_assessment?.price_position_pct || 0).toFixed(1)}%</span>
                    </div>
                </div>
                
                <div class="detail-section">
                    <h4>价格目标</h4>
                    <div class="detail-item">
                        <span class="detail-label">下一阻力位:</span>
                        <span class="detail-value">${analysis.price_targets?.next_resistance ? '¥' + analysis.price_targets.next_resistance.toFixed(2) : '--'}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">下一支撑位:</span>
                        <span class="detail-value">${analysis.price_targets?.next_support ? '¥' + analysis.price_targets.next_support.toFixed(2) : '--'}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">短期目标:</span>
                        <span class="detail-value">¥${(analysis.price_targets?.short_term_target || 0).toFixed(2)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">中期目标:</span>
                        <span class="detail-value">¥${(analysis.price_targets?.medium_term_target || 0).toFixed(2)}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">止损位:</span>
                        <span class="detail-value">¥${(analysis.price_targets?.stop_loss_level || 0).toFixed(2)}</span>
                    </div>
                </div>
                
                <div class="detail-section">
                    <h4>时间分析</h4>
                    <div class="detail-item">
                        <span class="detail-label">预期到顶日期:</span>
                        <span class="detail-value">${analysis.timing_analysis?.expected_peak_date || '--'}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">距离到顶:</span>
                        <span class="detail-value">${analysis.timing_analysis?.days_to_peak ? analysis.timing_analysis.days_to_peak + '天' : '--'}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">平均周期:</span>
                        <span class="detail-value">${analysis.timing_analysis?.avg_cycle_days ? analysis.timing_analysis.avg_cycle_days + '天' : '--'}</span>
                    </div>
                    <div class="detail-item">
                        <span class="detail-label">时间建议:</span>
                        <span class="detail-value">${analysis.timing_analysis?.timing_advice || '--'}</span>
                    </div>
                </div>
            </div>
        `;
        
        content.innerHTML = html;
    }
    
    // 全局函数，供HTML调用
    window.editPosition = function(stockCode) {
        // TODO: 实现编辑持仓功能
        alert('编辑功能开发中...');
    };
    
    window.removePosition = function(stockCode) {
        if (!confirm(`确定要删除持仓 ${stockCode} 吗？`)) return;
        
        fetch(`/api/portfolio?stock_code=${stockCode}`, { method: 'DELETE' })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert(data.message);
                    loadPortfolioData();
                } else {
                    alert(`删除失败: ${data.error}`);
                }
            })
            .catch(error => {
                console.error('Error removing position:', error);
                alert(`删除出错: ${error.message}`);
            });
    };
    
    window.showPositionDetailModal = showPositionDetailModal;

    // --- 初始化 ---
    populateStockList();
});