document.addEventListener('DOMContentLoaded', function () {
    // --- DOM元素获取 ---
    const stockSelect = document.getElementById('stock-select');
    const strategySelect = document.getElementById('strategy-select');
    const adjustmentSelect = document.getElementById('adjustment-select');
    const timeframeSelect = document.getElementById('timeframe-select');
    const chartContainer = document.getElementById('chart-container');
    const myChart = echarts.init(chartContainer);
    const refreshBtn = document.getElementById('refresh-btn');
    const forceRefreshBtn = document.getElementById('force-refresh-btn');
    const multiTimeframeBtn = document.getElementById('multi-timeframe-btn');
    const deepScanBtn = document.getElementById('deep-scan-btn');
    const historyBtn = document.getElementById('history-btn');
    const cacheManagerBtn = document.getElementById('cache-manager-btn');
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

    // 策略配置模态框
    const strategyConfigBtn = document.getElementById('strategy-config-btn');
    const strategyConfigModal = document.getElementById('strategy-config-modal');
    const strategyConfigClose = document.getElementById('strategy-config-close');

    // --- 新增：前端核心池缓存 ---
    let corePoolSet = new Set();

    // --- 新增：用于刷新核心池缓存的函数 ---
    async function refreshCorePoolSet() {
        try {
            const response = await fetch('/api/core_pool');
            const data = await response.json();
            if (data.success) {
                corePoolSet = new Set(data.core_pool.map(stock => stock.stock_code));
            }
        } catch (error) {
            console.error('刷新核心池缓存失败:', error);
        }
    }

    // --- 事件监听 ---
    strategySelect.addEventListener('change', () => {
        populateStockList();
        myChart.clear();
        if (advicePanel) advicePanel.style.display = 'none';
        if (backtestContainer) backtestContainer.style.display = 'none';
    });

    stockSelect.addEventListener('change', loadUnifiedStockData);

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

    if (forceRefreshBtn) forceRefreshBtn.addEventListener('click', () => {
        const strategy = strategySelect.value;
        if (!strategy) {
            showNotification('请先选择一个策略', 2000);
            return;
        }
        
        if (!confirm(`确定要强制刷新策略 "${strategy}" 的缓存吗？这将重新筛选所有股票。`)) {
            return;
        }
        
        forceRefreshStrategy(strategy);
    });

    if (adviceRefreshBtn) {
        adviceRefreshBtn.addEventListener('click', () => {
            const stockCode = stockSelect.value;
            if (stockCode) {
                // --- [FIX] ---
                // Call the main unified data loader to ensure data consistency and caching.
                loadUnifiedStockData(); 
                // --- [FIX] ---
            }
        });
    }

    if (deepScanBtn) deepScanBtn.addEventListener('click', runDeepScan);
    if (historyBtn) historyBtn.addEventListener('click', showHistoryModal);
    if (multiTimeframeBtn) multiTimeframeBtn.addEventListener('click', showMultiTimeframeModal);
    if (cacheManagerBtn) cacheManagerBtn.addEventListener('click', showCacheManagerModal);

    // 模态框事件
    if (corePoolBtn) corePoolBtn.addEventListener('click', showCorePoolModal);
    if (corePoolClose) corePoolClose.addEventListener('click', hideCorePoolModal);
    if (historyClose) historyClose.addEventListener('click', hideHistoryModal);
    if (multiTimeframeClose) multiTimeframeClose.addEventListener('click', hideMultiTimeframeModal);
    if (strategyConfigBtn) strategyConfigBtn.addEventListener('click', showStrategyConfigModal);
    if (strategyConfigClose) strategyConfigClose.addEventListener('click', hideStrategyConfigModal);

    // 点击模态框外部关闭
    window.addEventListener('click', (event) => {
        if (event.target === corePoolModal) hideCorePoolModal();
        if (event.target === historyModal) hideHistoryModal();
        if (event.target === multiTimeframeModal) hideMultiTimeframeModal();
        if (event.target === strategyConfigModal) hideStrategyConfigModal();
    });

    // 初始化：延迟加载可用策略，确保configManager已初始化
    setTimeout(() => {
        initializeStrategies();
    }, 100);

    // 持仓管理自动刷新功能已移除，改为点击时自动触发深度扫描


    // --- 主要功能函数 ---

    function populateStockList() {
        const strategy = strategySelect.value;
        if (!strategy) return;

        // 显示加载状态
        stockSelect.innerHTML = '<option value="">加载中...</option>';

        // 使用策略筛选API
        fetch(`/api/strategies/${encodeURIComponent(strategy)}/stocks`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                return response.json();
            })
            .then(data => {
                stockSelect.innerHTML = '<option value="">请选择股票</option>';

                if (data.success && data.data) {
                    const stockList = data.data;
                    
                    // 显示缓存状态
                    const cacheStatus = data.from_cache ? '(缓存)' : '(实时)';
                    console.log(`策略 ${strategy} 数据来源: ${cacheStatus}, 股票数: ${stockList.length}`);
                    
                    if (stockList.length === 0) {
                        stockSelect.innerHTML += `<option disabled>策略 ${strategy} 今日无信号</option>`;
                        return;
                    }
                    
                    stockList.forEach(signal => {
                        const option = document.createElement('option');
                        option.value = signal.stock_code;
                        
                        // 显示股票信息和缓存状态
                        let displayText = `${signal.stock_code}`;
                        if (signal.stock_name && signal.stock_name !== signal.stock_code) {
                            displayText += ` ${signal.stock_name}`;
                        }
                        displayText += ` (${signal.date})`;
                        if (data.from_cache) {
                            displayText += ' 📋';  // 缓存标记
                        }
                        
                        option.textContent = displayText;
                        stockSelect.appendChild(option);
                    });
                    
                    // 在控制台显示缓存状态
                    if (data.from_cache) {
                        showNotification(`策略 ${strategy} 数据来自缓存 (${stockList.length}只股票)`, 2000);
                    }
                } else {
                    throw new Error(data.error || '返回数据格式不正确');
                }
            })
            .catch(error => {
                console.error('Error fetching strategy stocks:', error);
                stockSelect.innerHTML = `<option value="">加载失败: ${error.message}</option>`;
                showNotification(`加载策略 ${strategy} 失败: ${error.message}`, 3000);
            });
    }

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
            // --- 核心修改：调用统一API ---
            console.log(`调用统一API: /api/unified_analysis/${stockCode}?strategy=${encodeURIComponent(strategy)}`);
            const response = await fetch(`/api/unified_analysis/${stockCode}?strategy=${encodeURIComponent(strategy)}`);
            
            if (!response.ok) {
                const errorText = await response.text();
                console.error('API响应错误:', response.status, response.statusText, errorText);
                throw new Error(`API响应失败: ${response.status} ${response.statusText}`);
            }
            
            const result = await response.json();
            console.log('统一API响应:', result);

            if (!result.success) {
                throw new Error(result.error || '未知错误');
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
            if (unifiedData.analysis && unifiedData.analysis.backtest_results) {
                renderBacktestResults(unifiedData.analysis.backtest_results);
            }
            
            // 3. 渲染交易建议 - 修复数据结构匹配
            let tradingAdvice = null;
            if (unifiedData.analysis) {
                // 优先使用enhanced_trading_advice，回退到trading_advice
                tradingAdvice = unifiedData.analysis.enhanced_trading_advice || unifiedData.analysis.trading_advice;
                
                // 如果有enhanced_trading_advice，需要平铺数据以匹配前端期望
                if (unifiedData.analysis.enhanced_trading_advice) {
                    const enhanced = unifiedData.analysis.enhanced_trading_advice;
                    const base = unifiedData.analysis.trading_advice || {};
                    
                    tradingAdvice = {
                        ...base,
                        action: enhanced.enhanced_action || base.action || 'WATCH',
                        confidence: enhanced.confidence_score || base.confidence,
                        analysis_logic: enhanced.reasoning || base.analysis_logic || [],
                        entry_price: enhanced.price_targets?.entry_price || base.entry_price,
                        target_price: enhanced.price_targets?.target_price || base.target_price,
                        stop_price: enhanced.price_targets?.stop_loss_price || base.stop_price,
                        current_price: base.current_price,
                        resistance_level: base.resistance_level,
                        support_level: base.support_level
                    };
                }
            }
            
            if (tradingAdvice) {
                updateAdvicePanel(tradingAdvice);
            } else {
                updateAdvicePanel({ action: 'ERROR', analysis_logic: ['无法获取交易建议数据'] });
            }

            // 显示缓存状态
            if (unifiedData.from_cache) {
                console.log('数据来源：缓存');
            } else {
                console.log('数据来源：实时计算');
            }

        } catch (error) {
            console.error('统一数据加载失败:', error);
            myChart.clear();
            myChart.setOption({
                title: { text: '加载数据失败', subtext: error.message, left: 'center', top: 'center' }
            });
            updateAdvicePanel({ action: 'ERROR', analysis_logic: [error.message] });
        } finally {
            myChart.hideLoading();
        }
    }

    // 保持向后兼容性，将原有的 loadChart 调用重定向到新函数
    function loadChart() {
        loadUnifiedStockData();
    }

    function renderEchart(chartData, stockCode, strategy, stockName) {
        const dates = chartData.kline_data.map(item => item.date);
        const klineData = chartData.kline_data.map(item => [item.open, item.close, item.low, item.high]);
        const volumeData = chartData.kline_data.map(item => item.volume);

        // 技术指标数据 - 完整MA系列
        const ma7Data = chartData.indicator_data.map(item => item.ma7);
        const ma13Data = chartData.indicator_data.map(item => item.ma13);
        const ma30Data = chartData.indicator_data.map(item => item.ma30);
        const ma45Data = chartData.indicator_data.map(item => item.ma45);
        const ma60Data = chartData.indicator_data.map(item => item.ma60);
        const ma90Data = chartData.indicator_data.map(item => item.ma90);
        const ma150Data = chartData.indicator_data.map(item => item.ma150);
        const ma240Data = chartData.indicator_data.map(item => item.ma240);
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
        const defaultShowCount = Math.min(252, totalDataPoints); // 默认显示最近60个交易日
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
            //const padding = Math.max(range * 0.1, 0.01); // 至少10%的边距，最小0.01
            const padding = 0.01; // 至少10%的边距，最小0.01
            macdMin = actualMin - padding;
            macdMax = actualMax + padding;

            // 确保范围不会过小
            //if (Math.abs(macdMax - macdMin) < 0.02) {
            //  const center = (macdMax + macdMin) / 2;
            //macdMin = center - 0.01;
            //macdMax = center + 0.01;
            //}
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
                text: `${stockCode} ${stockName || ''} - ${strategy}策略分析 (${timeframeText})`,
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
                data: ['K线', 'MA7', 'MA13', 'MA30', 'MA45', 'MA60', 'MA90', 'MA150', 'MA240', 'DIF', 'DEA', 'K', 'D', 'J', 'RSI6', 'RSI12', 'RSI24'],
                top: 30,
                textStyle: { fontSize: 10 }
            },

            // 多网格布局：主图、RSI、KDJ、MACD
            grid: [
                { left: '8%', right: '5%', top: '8%', height: '35%' },      // 主图：K线和MA
                { left: '8%', right: '5%', top: '46%', height: '15%' },     // RSI指标
                { left: '8%', right: '5%', top: '64%', height: '15%' },     // KDJ指标
                { left: '8%', right: '5%', top: '82%', height: '15%' }      // MACD指标
            ],
            
            // 多X轴配置
            xAxis: [
                { type: 'category', data: dates, gridIndex: 0, axisLabel: { show: false } },
                { type: 'category', data: dates, gridIndex: 1, axisLabel: { show: false } },
                { type: 'category', data: dates, gridIndex: 2, axisLabel: { show: false } },
                { type: 'category', data: dates, gridIndex: 3, axisLabel: { fontSize: 10 } }
            ],
            
            // 多Y轴配置
            yAxis: [
                { type: 'value', scale: true, gridIndex: 0 },                                    // 主图
                { type: 'value', gridIndex: 1, min: rsiMin, max: rsiMax, axisLabel: { fontSize: 10 } },  // RSI
                { type: 'value', gridIndex: 2, min: kdjMin, max: kdjMax, axisLabel: { fontSize: 10 } },  // KDJ
                { type: 'value', gridIndex: 3, min: macdMin, max: macdMax, axisLabel: { fontSize: 10 } } // MACD
            ],
            
            dataZoom: [
                {
                    type: 'inside',
                    start: startPercent,
                    end: 100,
                    xAxisIndex: [0, 1, 2, 3]
                },
                {
                    show: true,
                    type: 'slider',
                    bottom: '2%',
                    height: 15,
                    start: startPercent,
                    end: 100,
                    xAxisIndex: [0, 1, 2, 3],
                    handleStyle: { color: '#007bff' }
                }
            ],
            series: [
                // 主图：K线和移动平均线
                {
                    name: 'K线',
                    type: 'candlestick',
                    data: klineData,
                    xAxisIndex: 0,
                    yAxisIndex: 0
                },
                {
                    name: 'MA7',
                    type: 'line',
                    data: ma7Data,
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 1, color: '#ff6b6b' },
                    xAxisIndex: 0,
                    yAxisIndex: 0
                },
                {
                    name: 'MA13',
                    type: 'line',
                    data: ma13Data,
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 1, color: '#4ecdc4' },
                    xAxisIndex: 0,
                    yAxisIndex: 0
                },
                {
                    name: 'MA30',
                    type: 'line',
                    data: ma30Data,
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 1, color: '#45b7d1' },
                    xAxisIndex: 0,
                    yAxisIndex: 0
                },
                {
                    name: 'MA45',
                    type: 'line',
                    data: ma45Data,
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 1, color: '#f39c12' },
                    xAxisIndex: 0,
                    yAxisIndex: 0
                },
                {
                    name: 'MA60',
                    type: 'line',
                    data: ma60Data,
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 1, color: '#e74c3c' },
                    xAxisIndex: 0,
                    yAxisIndex: 0
                },
                {
                    name: 'MA90',
                    type: 'line',
                    data: ma90Data,
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 1, color: '#9b59b6' },
                    xAxisIndex: 0,
                    yAxisIndex: 0
                },
                {
                    name: 'MA150',
                    type: 'line',
                    data: ma150Data,
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 1, color: '#2ecc71' },
                    xAxisIndex: 0,
                    yAxisIndex: 0
                },
                {
                    name: 'MA240',
                    type: 'line',
                    data: ma240Data,
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 1, color: '#e67e22' },
                    xAxisIndex: 0,
                    yAxisIndex: 0
                },
                
                // RSI指标
                {
                    name: 'RSI6',
                    type: 'line',
                    data: rsi6Data,
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 1, color: '#ff6b6b' },
                    xAxisIndex: 1,
                    yAxisIndex: 1
                },
                {
                    name: 'RSI12',
                    type: 'line',
                    data: rsi12Data,
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 1, color: '#4ecdc4' },
                    xAxisIndex: 1,
                    yAxisIndex: 1
                },
                {
                    name: 'RSI24',
                    type: 'line',
                    data: rsi24Data,
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 1, color: '#45b7d1' },
                    xAxisIndex: 1,
                    yAxisIndex: 1
                },
                
                // KDJ指标
                {
                    name: 'K',
                    type: 'line',
                    data: kData,
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 1, color: '#ff6b6b' },
                    xAxisIndex: 2,
                    yAxisIndex: 2
                },
                {
                    name: 'D',
                    type: 'line',
                    data: dData,
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 1, color: '#4ecdc4' },
                    xAxisIndex: 2,
                    yAxisIndex: 2
                },
                {
                    name: 'J',
                    type: 'line',
                    data: jData,
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 1, color: '#45b7d1' },
                    xAxisIndex: 2,
                    yAxisIndex: 2
                },
                
                // MACD指标
                {
                    name: 'DIF',
                    type: 'line',
                    data: difData,
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 1, color: '#ff6b6b' },
                    xAxisIndex: 3,
                    yAxisIndex: 3
                },
                {
                    name: 'DEA',
                    type: 'line',
                    data: deaData,
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 1, color: '#4ecdc4' },
                    xAxisIndex: 3,
                    yAxisIndex: 3
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
                    }
                }
            ]
        };

        // 添加信号点 - 修复版本，显示回测成功标记
        if (signalData.length > 0) {
            const signalSeries = {
                name: '交易信号',
                type: 'scatter',
                data: signalData.map(signal => {
                    const dateIndex = dates.indexOf(signal.date);
                    return [dateIndex, signal.price];
                }).filter(point => point[0] >= 0), // 过滤无效的日期索引
                symbol: function(params) {
                    const signal = signalData[params.dataIndex];
                    if (!signal) return 'circle';
                    
                    // 根据回测结果选择不同的符号
                    if (signal.state && signal.state.includes('SUCCESS')) return 'diamond'; // 成功用钻石
                    if (signal.state && signal.state.includes('FAIL')) return 'triangle'; // 失败用三角形
                    return 'circle'; // 待确认用圆形
                },
                symbolSize: function(params) {
                    const signal = signalData[params.dataIndex];
                    if (!signal) return 8;
                    
                    // 成功的信号点更大
                    if (signal.state && signal.state.includes('SUCCESS')) return 15;
                    return 10;
                },
                itemStyle: {
                    color: function (params) {
                        const signal = signalData[params.dataIndex];
                        if (!signal) return '#888888';

                        // 更清晰的颜色区分
                        if (signal.state && signal.state.includes('SUCCESS')) return '#00cc00'; // 绿色表示成功
                        if (signal.state && signal.state.includes('FAIL')) return '#cc0000'; // 红色表示失败
                        return '#ff9900'; // 橙色表示待确认
                    },
                    borderColor: '#ffffff',
                    borderWidth: 2
                },
                emphasis: {
                    itemStyle: {
                        shadowBlur: 15,
                        shadowColor: 'rgba(0, 0, 0, 0.6)'
                    }
                },
                tooltip: {
                    formatter: function (params) {
                        const signal = signalData[params.dataIndex];
                        if (!signal) return '';
                        
                        let statusColor = '#888888';
                        let statusText = signal.state || '待确认';
                        
                        if (signal.state && signal.state.includes('SUCCESS')) {
                            statusColor = '#00cc00';
                            statusText = '✅ 回测成功';
                        } else if (signal.state && signal.state.includes('FAIL')) {
                            statusColor = '#cc0000';
                            statusText = '❌ 回测失败';
                        }
                        
                        return `
                            <div style="text-align: left;">
                                <strong>交易信号</strong><br/>
                                日期: ${signal.date}<br/>
                                价格: ¥${signal.price.toFixed(2)}<br/>
                                状态: <span style="color: ${statusColor}; font-weight: bold;">${statusText}</span>
                                ${signal.profit ? `<br/>收益: <span style="color: ${signal.profit > 0 ? '#00cc00' : '#cc0000'};">${(signal.profit * 100).toFixed(2)}%</span>` : ''}
                            </div>
                        `;
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
    // loadTradingAdvice function removed - now using unified loadUnifiedStockData

    function updateAdvicePanel(advice) {
        // **修复点**: 这是统一的UI更新函数，增加空值检查
        if (!advice || typeof advice !== 'object') {
            advice = { action: 'ERROR', analysis_logic: ['无效的建议数据'] };
        }
        
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
            if (advice.confidence && typeof advice.confidence === 'number') {
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
        if (logicEl) {
            if (advice.analysis_logic && Array.isArray(advice.analysis_logic) && advice.analysis_logic.length > 0) {
                logicEl.innerHTML = advice.analysis_logic.map(logic => `
                    <div class="logic-item">
                        <span class="logic-icon">•</span>
                        <span>${logic}</span>
                    </div>
                `).join('');
            } else {
                logicEl.innerHTML = `
                    <div class="logic-item">
                        <span class="logic-icon">•</span>
                        <span>暂无分析逻辑</span>
                    </div>
                `;
            }
        }
        
        // 显示交易建议面板
        if (advicePanel) {
            advicePanel.style.display = 'block';
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
        const listContainer = document.getElementById('core-pool-list');
        listContainer.innerHTML = '<div style="text-align: center; padding: 2rem; color: #6c757d;">加载核心池分析数据...</div>';

        fetch('/api/core_pool/analysis') // 调用新的API
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    displayCorePoolData(data.core_pool); // 使用新的渲染函数
                } else {
                    throw new Error(data.error);
                }
            })
            .catch(error => {
                console.error('Error loading core pool analysis:', error);
                listContainer.innerHTML = `<p>加载核心池失败: ${error.message}</p>`;
            });
    }

    function displayCorePoolData(pool) {
        const listContainer = document.getElementById('core-pool-list');
        if (!pool || pool.length === 0) {
            listContainer.innerHTML = '<p>核心池为空。</p>';
            return;
        }

        // 表格结构类似持仓扫描
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
                    <td><button onclick="removeFromCorePool('${stock.stock_code}')" style="background: #dc3545; color: white; border: none; padding: 0.3rem 0.8rem; border-radius: 4px; cursor: pointer;">删除</button></td>
                </tr>
            `;
        });
        html += '</tbody></table>';
        listContainer.innerHTML = html;
    }

    // 【新增】点击核心池股票跳转到主图表的辅助函数
    window.viewStockFromCorePool = function(stockCode) {
        // 关闭模态框
        hideCorePoolModal();
        
        // 使用统一的股票选择函数
        selectStockAndShowChart(stockCode);
    };

    // 全局函数，供HTML调用
    window.removeFromCorePool = function (stockCode) {
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

    window.addToCorePool = function () {
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


    // --- 策略配置管理功能 ---
    async function initializeStrategies() {
        try {
            // 等待配置管理器加载完成
            if (typeof configManager !== 'undefined') {
                await configManager.waitForLoad();
                await loadAvailableStrategies();
            } else {
                // 如果配置管理器不可用，使用传统方式
                loadAvailableStrategiesLegacy();
            }
        } catch (error) {
            console.error('初始化策略失败:', error);
            loadAvailableStrategiesLegacy();
        }
    }

    async function loadAvailableStrategies() {
        try {
            // 使用统一配置管理器
            if (typeof configManager !== 'undefined' && configManager.loaded) {
                const strategies = configManager.getEnabledStrategies();
                const strategyList = Object.keys(strategies).map(id => ({
                    id: id,
                    ...strategies[id]
                }));
                populateStrategySelect(strategyList);
                return;
            }
        } catch (error) {
            console.error('使用配置管理器加载策略失败:', error);
        }

        // 回退到API调用
        loadAvailableStrategiesLegacy();
    }

    function loadAvailableStrategiesLegacy() {
        fetch('/api/strategies')
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    populateStrategySelect(data.strategies);
                } else {
                    console.error('加载策略失败:', data.error);
                    strategySelect.innerHTML = '<option value="">加载策略失败</option>';
                }
            })
            .catch(error => {
                console.error('加载策略出错:', error);
                strategySelect.innerHTML = '<option value="">加载策略出错</option>';
            });
    }

    function populateStrategySelect(strategies) {
        strategySelect.innerHTML = '<option value="">请选择策略</option>';

        // 只显示启用且兼容的策略
        const enabledStrategies = strategies.filter(strategy =>
            strategy.enabled !== false && isStrategyCompatible(strategy)
        );

        if (enabledStrategies.length === 0) {
            strategySelect.innerHTML += '<option disabled>暂无可用策略</option>';
            return;
        }

        enabledStrategies.forEach(strategy => {
            const option = document.createElement('option');
            option.value = strategy.id;
            option.textContent = getStrategyDisplayName(strategy);
            strategySelect.appendChild(option);
        });

        // 如果只有一个策略，自动选择
        if (enabledStrategies.length === 1) {
            strategySelect.value = enabledStrategies[0].id;
            populateStockList();
        }
    }

    function showStrategyConfigModal() {
        if (strategyConfigModal) {
            strategyConfigModal.style.display = 'block';
            loadStrategyConfigData();
        }
    }

    function hideStrategyConfigModal() {
        if (strategyConfigModal) {
            strategyConfigModal.style.display = 'none';
        }
    }

    function loadStrategyConfigData() {
        const contentDiv = document.getElementById('strategy-config-content');
        contentDiv.innerHTML = '<div id="strategy-config-loading" style="text-align: center; padding: 2rem; color: #6c757d;">加载中...</div>';

        fetch('/api/strategies')
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    displayStrategyConfigData(data.strategies);
                } else {
                    throw new Error(data.error);
                }
            })
            .catch(error => {
                console.error('加载策略配置失败:', error);
                contentDiv.innerHTML = `<p style="color: #dc3545;">加载策略配置失败: ${error.message}</p>`;
            });
    }

    function displayStrategyConfigData(strategies) {
        const contentDiv = document.getElementById('strategy-config-content');

        if (!strategies || strategies.length === 0) {
            contentDiv.innerHTML = '<p>暂无可用策略。</p>';
            return;
        }

        let html = '';
        strategies.forEach(strategy => {
            const isEnabled = strategy.enabled !== false;
            const config = strategy.config || {};

            html += `
                <div class="strategy-card ${isEnabled ? '' : 'disabled'}" data-strategy-id="${strategy.id}">
                    <div class="strategy-header">
                        <div>
                            <h4 class="strategy-title">${strategy.name}</h4>
                            <span class="strategy-version">v${strategy.version}</span>
                        </div>
                        <div class="strategy-toggle">
                            <span style="font-size: 0.9rem; color: #6c757d;">${isEnabled ? '启用' : '禁用'}</span>
                            <div class="toggle-switch ${isEnabled ? 'active' : ''}" onclick="toggleStrategy('${strategy.id}', ${!isEnabled})">
                                <div class="toggle-slider"></div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="strategy-description">
                        ${strategy.description || '暂无描述'}
                    </div>
                    
                    <div class="strategy-meta">
                        <div class="meta-item">
                            <div class="meta-label">数据长度要求</div>
                            <div class="meta-value">${strategy.required_data_length || 'N/A'} 天</div>
                        </div>
                        <div class="meta-item">
                            <div class="meta-label">风险等级</div>
                            <div class="meta-value">${config.risk_level || 'N/A'}</div>
                        </div>
                        <div class="meta-item">
                            <div class="meta-label">预期信号数</div>
                            <div class="meta-value">${config.expected_signals_per_day || 'N/A'}</div>
                        </div>
                        <div class="meta-item">
                            <div class="meta-label">适用市场</div>
                            <div class="meta-value">${config.suitable_market ? config.suitable_market.join(', ') : 'N/A'}</div>
                        </div>
                    </div>
                    
                    ${config.tags ? `
                        <div class="strategy-tags">
                            ${config.tags.map(tag => `<span class="strategy-tag">${tag}</span>`).join('')}
                        </div>
                    ` : ''}
                    
                    <div class="strategy-actions">
                        <button class="btn-config" onclick="showStrategyDetailConfig('${strategy.id}')">详细配置</button>
                        <button class="btn-test" onclick="testStrategy('${strategy.id}')">测试策略</button>
                    </div>
                </div>
            `;
        });

        contentDiv.innerHTML = html;
    }

    // 全局函数，供HTML调用
    window.toggleStrategy = function (strategyId, enable) {
        fetch(`/api/strategies/${strategyId}/toggle`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled: enable })
        })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // 重新加载策略配置和下拉框
                    loadStrategyConfigData();
                    initializeStrategies();
                    alert(data.message);
                } else {
                    alert(`操作失败: ${data.error}`);
                }
            })
            .catch(error => {
                console.error('切换策略状态失败:', error);
                alert(`操作出错: ${error.message}`);
            });
    };

    window.showStrategyDetailConfig = function (strategyId) {
        alert(`策略 ${strategyId} 的详细配置功能正在开发中...`);
        // TODO: 实现详细配置界面
    };

    window.testStrategy = function (strategyId) {
        alert(`策略 ${strategyId} 的测试功能正在开发中...`);
        // TODO: 实现策略测试功能
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

        // 显示扫描状态
        if (deepScanSection) {
            deepScanSection.innerHTML = `
                <h3>深度扫描进行中...</h3>
                <div style="text-align: center; padding: 2rem;">
                    <div style="display: inline-block; width: 40px; height: 40px; border: 4px solid #f3f3f3; border-top: 4px solid #007bff; border-radius: 50%; animation: spin 1s linear infinite;"></div>
                    <p style="margin-top: 1rem; color: #6c757d;">正在执行深度扫描，请耐心等待...</p>
                </div>
                <style>
                    @keyframes spin {
                        0% { transform: rotate(0deg); }
                        100% { transform: rotate(360deg); }
                    }
                </style>
            `;
            deepScanSection.style.display = 'block';
        }

        fetch('/api/run_deep_scan', { method: 'POST' })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showNotification('深度扫描已启动，正在处理中...', 3000);
                    
                    // 定期检查结果，最多等待5分钟
                    let checkCount = 0;
                    const maxChecks = 60; // 5分钟，每5秒检查一次
                    
                    const checkResults = () => {
                        checkCount++;
                        
                        fetch('/api/deep_scan_results')
                            .then(response => response.json())
                            .then(resultData => {
                                if (!resultData.error && resultData.results && resultData.results.length > 0) {
                                    // 找到结果，立即刷新显示
                                    showNotification('深度扫描完成！', 2000);
                                    loadDeepScanResults();
                                } else if (checkCount < maxChecks) {
                                    // 继续等待
                                    setTimeout(checkResults, 5000);
                                } else {
                                    // 超时
                                    showNotification('扫描超时，请手动刷新查看结果', 3000);
                                    loadDeepScanResults();
                                }
                            })
                            .catch(() => {
                                if (checkCount < maxChecks) {
                                    setTimeout(checkResults, 5000);
                                } else {
                                    loadDeepScanResults();
                                }
                            });
                    };
                    
                    // 5秒后开始检查结果
                    setTimeout(checkResults, 5000);
                    
                } else {
                    showNotification(`启动失败: ${data.error || '未知错误'}`, 3000);
                    if (deepScanSection) {
                        deepScanSection.innerHTML = `<p style="color: #dc3545; text-align: center; padding: 2rem;">启动失败: ${data.error || '未知错误'}</p>`;
                    }
                }
            })
            .catch(error => {
                console.error('Error running deep scan:', error);
                showNotification(`启动出错: ${error.message}`, 3000);
                if (deepScanSection) {
                    deepScanSection.innerHTML = `<p style="color: #dc3545; text-align: center; padding: 2rem;">启动出错: ${error.message}</p>`;
                }
            });
    }

    function loadDeepScanResults() {
        if (!deepScanSection) return;

        // 显示加载状态
        deepScanSection.innerHTML = '<div style="text-align: center; padding: 2rem; color: #6c757d;">正在加载深度扫描结果...</div>';
        deepScanSection.style.display = 'block';

        fetch('/api/deep_scan_results')
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    deepScanSection.innerHTML = `<p>暂无深度扫描结果: ${data.error}</p>`;
                    return;
                }

                const results = data.results || [];
                const summary = data.summary || {};

                let html = `
                    <h3>深度扫描结果 <button onclick="loadDeepScanResults()" style="float: right; padding: 0.3rem 0.8rem; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer;">🔄 刷新</button></h3>
                    <div class="scan-summary" style="margin-bottom: 1rem; padding: 1rem; background: #f8f9fa; border-radius: 8px;">
                        <p>总分析数: ${summary.total_analyzed || 0} | A级股票: ${summary.a_grade_count || 0} | 买入推荐: ${summary.buy_recommendations || 0}</p>
                    </div>
                `;

                if (results.length > 0) {
                    // 按分数排序（确保前端也按分数排序）
                    results.sort((a, b) => (b.score || 0) - (a.score || 0));
                    
                    html += `
                        <table class="scan-results-table">
                            <thead>
                                <tr>
                                    <th>排名</th>
                                    <th>股票代码</th>
                                    <th>股票名称</th>
                                    <th>评分</th>
                                    <th>等级</th>
                                    <th>建议</th>
                                    <th>置信度</th>
                                    <th>当前价格</th>
                                    <th>市场阶段</th>
                                </tr>
                            </thead>
                            <tbody>
                    `;
                    
                    results.slice(0, 30).forEach((result, index) => { // 显示前30个结果
                        const rankClass = index < 5 ? 'top-rank' : index < 10 ? 'good-rank' : '';
                        html += `
                            <tr class="${rankClass}">
                                <td style="font-weight: bold; color: ${index < 5 ? '#dc3545' : index < 10 ? '#fd7e14' : '#6c757d'};">${index + 1}</td>
                                <td><a href="#" class="stock-code-link" data-stock-code="${result.stock_code}" style="color: #007bff; text-decoration: none; cursor: pointer; font-weight: bold;">${result.stock_code}</a></td>
                                <td style="font-size: 0.9em; color: #6c757d;">${result.stock_name || '--'}</td>
                                <td style="font-weight: bold; color: ${result.score >= 85 ? '#28a745' : result.score >= 70 ? '#17a2b8' : '#6c757d'};">${result.score.toFixed(1)}</td>
                                <td><span class="grade-${result.grade.toLowerCase()}" style="font-weight: bold;">${result.grade}</span></td>
                                <td><span class="action-${result.action.toLowerCase()}">${result.action}</span></td>
                                <td>
                                    <div style="display: flex; align-items: center; gap: 5px;">
                                        <div style="width: 30px; height: 4px; background: #e9ecef; border-radius: 2px; overflow: hidden;">
                                            <div style="width: ${(result.confidence * 100)}%; height: 100%; background: linear-gradient(90deg, #dc3545 0%, #ffc107 50%, #28a745 100%);"></div>
                                        </div>
                                        <span style="font-size: 0.8em;">${(result.confidence * 100).toFixed(0)}%</span>
                                    </div>
                                </td>
                                <td>¥${result.current_price.toFixed(2)}</td>
                                <td style="font-size: 0.8em; color: #6c757d;">${result.market_phase || '--'}</td>
                            </tr>
                        `;
                    });
                    html += '</tbody></table>';

                    // 添加样式
                    html += `
                        <style>
                            .scan-results-table .top-rank { background-color: #fff5f5; }
                            .scan-results-table .good-rank { background-color: #fffbf0; }
                            .scan-results-table th { background-color: #f8f9fa; font-weight: 600; }
                            .scan-results-table td, .scan-results-table th { padding: 0.5rem; border-bottom: 1px solid #dee2e6; }
                        </style>
                    `;

                    // 添加点击事件监听器
                    setTimeout(() => {
                        document.querySelectorAll('.stock-code-link').forEach(link => {
                            link.addEventListener('click', function (e) {
                                e.preventDefault();
                                const stockCode = this.getAttribute('data-stock-code');
                                selectStockAndShowChart(stockCode);
                            });
                        });
                    }, 100);
                } else {
                    html += '<p style="text-align: center; color: #6c757d; padding: 2rem;">暂无扫描结果</p>';
                }

                deepScanSection.innerHTML = html;
            })
            .catch(error => {
                console.error('Error loading deep scan results:', error);
                deepScanSection.innerHTML = `<p style="color: #dc3545; text-align: center; padding: 2rem;">加载深度扫描结果失败: ${error.message}</p>`;
            });
    }

    // --- 股票选择和图表显示功能 ---
    function selectStockAndShowChart(stockCode) {
        // 首先检查是否有选择的策略
        const currentStrategy = strategySelect.value;
        
        if (!currentStrategy) {
            // 如果没有选择策略，自动选择一个默认策略
            if (strategySelect.options.length > 1) {
                strategySelect.value = strategySelect.options[1].value; // 选择第一个非空策略
                // 重新加载股票列表
                populateStockList();
            } else {
                alert('请先选择一个策略');
                return;
            }
        }

        // 检查股票是否在当前策略的信号列表中
        const currentOptions = Array.from(stockSelect.options);
        const matchingOption = currentOptions.find(option => option.value === stockCode);

        if (matchingOption) {
            // 如果在当前策略中找到，直接选择
            stockSelect.value = stockCode;
            loadUnifiedStockData();

            // 滚动到图表区域
            chartContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
        } else {
            // 如果不在当前策略中，尝试添加到选择列表并选择
            const option = document.createElement('option');
            option.value = stockCode;
            option.textContent = `${stockCode} (深度扫描)`;
            stockSelect.appendChild(option);

            stockSelect.value = stockCode;
            
            // 强制加载数据，即使不在策略信号列表中
            loadUnifiedStockDataForced(stockCode);

            // 滚动到图表区域
            chartContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });

            // 显示提示信息
            showNotification(`已将 ${stockCode} 添加到选择列表，并加载图表分析。`);
        }
    }

    // 强制加载股票数据的函数（即使不在策略信号列表中）
    async function loadUnifiedStockDataForced(stockCode) {
        const strategy = strategySelect.value || 'RSI_BOTTOM'; // 使用默认策略

        myChart.showLoading();
        // 重置所有信息面板
        backtestContainer.style.display = 'none';
        updateAdvicePanel({ action: 'LOADING' });

        try {
            console.log(`强制调用统一API: /api/unified_analysis/${stockCode}?strategy=${encodeURIComponent(strategy)}`);
            const response = await fetch(`/api/unified_analysis/${stockCode}?strategy=${encodeURIComponent(strategy)}`);
            
            if (!response.ok) {
                const errorText = await response.text();
                console.error('API响应错误:', response.status, response.statusText, errorText);
                throw new Error(`API响应失败: ${response.status} ${response.statusText}`);
            }
            
            const result = await response.json();
            console.log('统一API响应:', result);

            if (!result.success) {
                throw new Error(result.error || '未知错误');
            }

            const unifiedData = result.data;
            
            // 渲染图表
            renderEchart(
                unifiedData.chart_data, 
                stockCode, 
                strategy, 
                unifiedData.stock_name
            );
            
            // 渲染回测结果
            if (unifiedData.analysis && unifiedData.analysis.backtest_results) {
                renderBacktestResults(unifiedData.analysis.backtest_results);
            }
            
            // 渲染交易建议
            let tradingAdvice = null;
            if (unifiedData.analysis) {
                tradingAdvice = unifiedData.analysis.enhanced_trading_advice || unifiedData.analysis.trading_advice;
                
                if (unifiedData.analysis.enhanced_trading_advice) {
                    const enhanced = unifiedData.analysis.enhanced_trading_advice;
                    const base = unifiedData.analysis.trading_advice || {};
                    
                    tradingAdvice = {
                        ...base,
                        action: enhanced.enhanced_action || base.action || 'WATCH',
                        confidence: enhanced.confidence_score || base.confidence,
                        analysis_logic: enhanced.reasoning || base.analysis_logic || [],
                        entry_price: enhanced.price_targets?.entry_price || base.entry_price,
                        target_price: enhanced.price_targets?.target_price || base.target_price,
                        stop_price: enhanced.price_targets?.stop_loss_price || base.stop_price,
                        current_price: base.current_price,
                        resistance_level: base.resistance_level,
                        support_level: base.support_level
                    };
                }
            }
            
            if (tradingAdvice) {
                updateAdvicePanel(tradingAdvice);
            } else {
                updateAdvicePanel({ action: 'ERROR', analysis_logic: ['无法获取交易建议数据'] });
            }

        } catch (error) {
            console.error('强制数据加载失败:', error);
            myChart.clear();
            myChart.setOption({
                title: { text: '加载数据失败', subtext: error.message, left: 'center', top: 'center' }
            });
            updateAdvicePanel({ action: 'ERROR', analysis_logic: [error.message] });
        } finally {
            myChart.hideLoading();
        }
    }

    // 显示通知的辅助函数
    function showNotification(message, duration = 3000) {
        const notification = document.createElement('div');
        notification.textContent = message;
        notification.style.cssText = `
            position: fixed;
            top: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: #28a745;
            color: white;
            padding: 12px 24px;
            border-radius: 8px;
            z-index: 9999;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
            font-size: 14px;
            font-weight: 500;
        `;
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.remove();
        }, duration);
    }

    // --- 缓存管理功能 ---
    function forceRefreshStrategy(strategy) {
        showNotification(`正在强制刷新策略 ${strategy}...`, 1000);
        
        fetch(`/api/cache/strategy_screening/refresh/${encodeURIComponent(strategy)}`, {
            method: 'POST'
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showNotification(`策略 ${strategy} 缓存已刷新 (${data.stock_count}只股票)`, 3000);
                // 重新加载股票列表
                populateStockList();
            } else {
                showNotification(`刷新失败: ${data.error}`, 3000);
            }
        })
        .catch(error => {
            console.error('Force refresh failed:', error);
            showNotification(`刷新失败: ${error.message}`, 3000);
        });
    }

    function showCacheManagerModal() {
        // 创建缓存管理模态框（如果不存在）
        let modal = document.getElementById('cache-manager-modal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'cache-manager-modal';
            modal.className = 'modal';
            modal.innerHTML = `
                <div class="modal-content">
                    <span class="close" onclick="hideCacheManagerModal()">&times;</span>
                    <h2>缓存管理</h2>
                    <div id="cache-stats-content">
                        <p>加载中...</p>
                    </div>
                    <div style="margin-top: 1rem;">
                        <button onclick="clearAllCache()" style="background: #dc3545; color: white; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer; margin-right: 0.5rem;">清理所有缓存</button>
                        <button onclick="clearOldCache()" style="background: #ffc107; color: #212529; border: none; padding: 0.5rem 1rem; border-radius: 4px; cursor: pointer;">清理7天前缓存</button>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);
        }
        
        modal.style.display = 'block';
        loadCacheStats();
    }

    function hideCacheManagerModal() {
        const modal = document.getElementById('cache-manager-modal');
        if (modal) {
            modal.style.display = 'none';
        }
    }

    function loadCacheStats() {
        const content = document.getElementById('cache-stats-content');
        if (!content) return;
        
        content.innerHTML = '<p>加载中...</p>';
        
        fetch('/api/cache/strategy_screening/stats')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const stats = data.stats;
                let html = `
                    <div class="cache-stats-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 1rem;">
                        <div class="stat-card" style="background: #f8f9fa; padding: 1rem; border-radius: 8px; text-align: center;">
                            <h4 style="margin: 0 0 0.5rem 0; color: #495057;">总缓存记录</h4>
                            <div style="font-size: 1.5rem; font-weight: bold; color: #007bff;">${stats.total_records}</div>
                        </div>
                        <div class="stat-card" style="background: #f8f9fa; padding: 1rem; border-radius: 8px; text-align: center;">
                            <h4 style="margin: 0 0 0.5rem 0; color: #495057;">今日记录</h4>
                            <div style="font-size: 1.5rem; font-weight: bold; color: #28a745;">${stats.today_records}</div>
                        </div>
                        <div class="stat-card" style="background: #f8f9fa; padding: 1rem; border-radius: 8px; text-align: center;">
                            <h4 style="margin: 0 0 0.5rem 0; color: #495057;">策略数量</h4>
                            <div style="font-size: 1.5rem; font-weight: bold; color: #17a2b8;">${stats.unique_strategies}</div>
                        </div>
                        <div class="stat-card" style="background: #f8f9fa; padding: 1rem; border-radius: 8px; text-align: center;">
                            <h4 style="margin: 0 0 0.5rem 0; color: #495057;">今日股票总数</h4>
                            <div style="font-size: 1.5rem; font-weight: bold; color: #ffc107;">${stats.today_total_stocks}</div>
                        </div>
                    </div>
                `;
                
                if (stats.recent_records && stats.recent_records.length > 0) {
                    html += `
                        <h4>最近缓存记录</h4>
                        <table style="width: 100%; border-collapse: collapse; margin-top: 0.5rem;">
                            <thead>
                                <tr style="background: #f8f9fa;">
                                    <th style="padding: 0.5rem; text-align: left; border: 1px solid #dee2e6;">策略</th>
                                    <th style="padding: 0.5rem; text-align: left; border: 1px solid #dee2e6;">股票数</th>
                                    <th style="padding: 0.5rem; text-align: left; border: 1px solid #dee2e6;">创建时间</th>
                                </tr>
                            </thead>
                            <tbody>
                    `;
                    
                    stats.recent_records.forEach(record => {
                        const createTime = new Date(record.created_at).toLocaleString();
                        html += `
                            <tr>
                                <td style="padding: 0.5rem; border: 1px solid #dee2e6;">${record.strategy_id}</td>
                                <td style="padding: 0.5rem; border: 1px solid #dee2e6;">${record.stock_count}</td>
                                <td style="padding: 0.5rem; border: 1px solid #dee2e6;">${createTime}</td>
                            </tr>
                        `;
                    });
                    
                    html += '</tbody></table>';
                }
                
                content.innerHTML = html;
            } else {
                content.innerHTML = `<p>加载失败: ${data.error}</p>`;
            }
        })
        .catch(error => {
            console.error('Load cache stats failed:', error);
            content.innerHTML = `<p>加载失败: ${error.message}</p>`;
        });
    }

    function clearAllCache() {
        if (!confirm('确定要清理所有策略筛选缓存吗？这将导致下次选择策略时需要重新筛选。')) {
            return;
        }
        
        fetch('/api/cache/strategy_screening/clear', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({})
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showNotification(`已清理 ${data.deleted_count} 条缓存记录`, 3000);
                loadCacheStats(); // 刷新统计信息
            } else {
                showNotification(`清理失败: ${data.error}`, 3000);
            }
        })
        .catch(error => {
            console.error('Clear cache failed:', error);
            showNotification(`清理失败: ${error.message}`, 3000);
        });
    }

    function clearOldCache() {
        if (!confirm('确定要清理7天前的缓存记录吗？')) {
            return;
        }
        
        fetch('/api/cache/strategy_screening/clear', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                older_than_days: 7
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showNotification(`已清理 ${data.deleted_count} 条过期缓存记录`, 3000);
                loadCacheStats(); // 刷新统计信息
            } else {
                showNotification(`清理失败: ${data.error}`, 3000);
            }
        })
        .catch(error => {
            console.error('Clear old cache failed:', error);
            showNotification(`清理失败: ${error.message}`, 3000);
        });
    }

    // 将函数暴露到全局作用域
    window.hideCacheManagerModal = hideCacheManagerModal;
    window.clearAllCache = clearAllCache;
    window.clearOldCache = clearOldCache;

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
            // 自动触发深度扫描，利用缓存机制提升响应速度
            scanPortfolio();
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
            <table class="portfolio-table" id="portfolio-table">
                <thead>
                    <tr>
                        <th class="sortable" data-column="stock_code">股票代码</th>
                        <th class="sortable" data-column="purchase_price">购买价格</th>
                        <th class="sortable" data-column="quantity">持仓数量</th>
                        <th class="sortable" data-column="purchase_date">购买日期</th>
                        <th class="sortable" data-column="current_price">当前价格</th>
                        <th class="sortable" data-column="profit_loss_pct">盈亏</th>
                        <th class="sortable" data-column="market_value">市值</th>
                        <th class="sortable" data-column="action">操作建议</th>
                        <th class="sortable" data-column="risk_level">风险等级</th>
                        <th class="sortable" data-column="holding_days">持有天数</th>
                        <th>备注</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody id="portfolio-tbody">
        `;

        portfolio.forEach(position => {
            const profitLoss = position.profit_loss_pct || 0;
            const profitClass = profitLoss > 0 ? 'profit-positive' : profitLoss < 0 ? 'profit-negative' : 'profit-neutral';
            const currentPrice = position.current_price || '--';
            const action = position.position_advice?.action || 'UNKNOWN';
            const riskLevel = position.risk_assessment?.risk_level || 'UNKNOWN';
            const marketValue = typeof currentPrice === 'number' ? (currentPrice * position.quantity).toFixed(2) : '--';

            // 计算持有天数
            const purchaseDate = new Date(position.purchase_date);
            const currentDate = new Date();
            const holdingDays = Math.floor((currentDate - purchaseDate) / (1000 * 60 * 60 * 24));

            html += `
                <tr data-stock-code="${position.stock_code}" 
                    data-purchase-price="${position.purchase_price}"
                    data-quantity="${position.quantity}"
                    data-purchase-date="${position.purchase_date}"
                    data-current-price="${typeof currentPrice === 'number' ? currentPrice : 0}"
                    data-profit-loss-pct="${profitLoss}"
                    data-market-value="${typeof currentPrice === 'number' ? currentPrice * position.quantity : 0}"
                    data-action="${action}"
                    data-risk-level="${riskLevel}"
                    data-holding-days="${holdingDays}">
                    <td>
                        <a href="#" class="stock-code-link" onclick="showPositionDetailModal('${position.stock_code}')">${position.stock_code}</a>
                    </td>
                    <td>¥${position.purchase_price.toFixed(2)}</td>
                    <td>${position.quantity}</td>
                    <td>${position.purchase_date}</td>
                    <td>${typeof currentPrice === 'number' ? '¥' + currentPrice.toFixed(2) : currentPrice}</td>
                    <td class="${profitClass}">${profitLoss.toFixed(2)}%</td>
                    <td>${marketValue !== '--' ? '¥' + marketValue : '--'}</td>
                    <td><span class="action-${action.toLowerCase()}">${getActionText(action)}</span></td>
                    <td><span class="risk-${riskLevel.toLowerCase()}">${getRiskText(riskLevel)}</span></td>
                    <td>${holdingDays}天</td>
                    <td>${position.note || '-'}</td>
                    <td>
                        <button onclick="toggleCorePool('${position.stock_code}')" id="core-pool-btn-${position.stock_code}" style="background: #ffc107; color: #212529; border: none; padding: 0.2rem 0.5rem; border-radius: 3px; cursor: pointer; margin-right: 0.3rem; font-size: 11px;">核心池</button>
                        <button onclick="editPosition('${position.stock_code}')" style="background: #007bff; color: white; border: none; padding: 0.2rem 0.5rem; border-radius: 3px; cursor: pointer; margin-right: 0.3rem; font-size: 11px;">编辑</button>
                        <button onclick="removePosition('${position.stock_code}')" style="background: #dc3545; color: white; border: none; padding: 0.2rem 0.5rem; border-radius: 3px; cursor: pointer; font-size: 11px;">删除</button>
                    </td>
                </tr>
            `;
        });

        html += '</tbody></table>';
        content.innerHTML = html;
        
        // 添加排序功能
        setupTableSorting();
        
        // 更新核心池按钮状态
        updateCorePoolButtons();
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

    function removePosition(stockCode) {
        if (confirm(`确定要删除 ${stockCode} 的持仓记录吗？`)) {
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
        }
    }

    function editPosition(stockCode) {
        alert(`编辑 ${stockCode} 持仓功能待实现`);
    }
    
    // 表格排序功能
    let currentSortColumn = null;
    let currentSortDirection = 'asc';
    
    function setupTableSorting() {
        const table = document.getElementById('portfolio-table');
        if (!table) return;
        
        const headers = table.querySelectorAll('th.sortable');
        headers.forEach(header => {
            header.addEventListener('click', () => {
                const column = header.getAttribute('data-column');
                sortTable(column);
            });
        });
    }
    
    function sortTable(column) {
        const table = document.getElementById('portfolio-table');
        const tbody = document.getElementById('portfolio-tbody');
        if (!table || !tbody) return;
        
        // 更新排序方向
        if (currentSortColumn === column) {
            currentSortDirection = currentSortDirection === 'asc' ? 'desc' : 'asc';
        } else {
            currentSortColumn = column;
            currentSortDirection = 'asc';
        }
        
        // 更新表头样式
        const headers = table.querySelectorAll('th.sortable');
        headers.forEach(header => {
            header.classList.remove('sort-asc', 'sort-desc');
            if (header.getAttribute('data-column') === column) {
                header.classList.add(currentSortDirection === 'asc' ? 'sort-asc' : 'sort-desc');
            }
        });
        
        // 获取所有行
        const rows = Array.from(tbody.querySelectorAll('tr'));
        
        // 排序函数
        rows.sort((a, b) => {
            let aValue = a.getAttribute(`data-${column.replace('_', '-')}`);
            let bValue = b.getAttribute(`data-${column.replace('_', '-')}`);
            
            // 处理不同数据类型
            if (column === 'purchase_price' || column === 'current_price' || column === 'profit_loss_pct' || 
                column === 'market_value' || column === 'quantity' || column === 'holding_days') {
                aValue = parseFloat(aValue) || 0;
                bValue = parseFloat(bValue) || 0;
            } else if (column === 'purchase_date') {
                aValue = new Date(aValue);
                bValue = new Date(bValue);
            }
            
            let result = 0;
            if (aValue < bValue) result = -1;
            else if (aValue > bValue) result = 1;
            
            return currentSortDirection === 'asc' ? result : -result;
        });
        
        // 重新插入排序后的行
        rows.forEach(row => tbody.appendChild(row));
    }
    
    // 核心池操作功能
    // --- 核心修改：优化 toggleCorePool 函数 ---
    function toggleCorePool(stockCode) {
        const inCorePool = corePoolSet.has(stockCode);
        if (inCorePool) {
            // 从核心池移除
            if (!confirm(`确定要从核心池移除 ${stockCode} 吗？`)) return;
            fetch(`/api/core_pool?stock_code=${stockCode}`, { method: 'DELETE' })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        alert(`${stockCode} 已从核心池移除`);
                        // 手动更新本地缓存，避免重新请求
                        corePoolSet.delete(stockCode);
                        updateCorePoolButtonStatus(stockCode, false);
                    } else {
                        alert(`移除失败: ${data.error}`);
                    }
                });
        } else {
            // 添加到核心池
            fetch('/api/core_pool', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ stock_code: stockCode, note: '从持仓管理添加' })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert(`${stockCode} 已添加到核心池`);
                    // 手动更新本地缓存
                    corePoolSet.add(stockCode);
                    updateCorePoolButtonStatus(stockCode, true);
                } else {
                    alert(`添加失败: ${data.error}`);
                }
            });
        }
    }
    

    
    // --- 核心修改：优化 updateCorePoolButtons 函数 ---
    async function updateCorePoolButtons() {
        // 1. 先一次性刷新核心池缓存
        await refreshCorePoolSet();

        // 2. 遍历所有持仓行，在本地进行判断
        const rows = document.querySelectorAll('#portfolio-tbody tr, #portfolio-scan-tbody tr');
        rows.forEach(row => {
            const stockCode = row.getAttribute('data-stock-code');
            if (stockCode) {
                const inCorePool = corePoolSet.has(stockCode);
                updateCorePoolButtonStatus(stockCode, inCorePool);
            }
        });
    }
    
    function updateCorePoolButtonStatus(stockCode, inCorePool) {
        const button = document.getElementById(`core-pool-btn-${stockCode}`);
        const scanButton = document.getElementById(`core-pool-scan-btn-${stockCode}`);
        
        [button, scanButton].forEach(btn => {
            if (btn) {
                if (inCorePool) {
                    btn.textContent = '移除';
                    btn.style.background = '#dc3545';
                    btn.style.color = 'white';
                    btn.title = '从核心池移除';
                } else {
                    btn.textContent = '添加';
                    btn.style.background = '#ffc107';
                    btn.style.color = '#212529';
                    btn.title = '添加到核心池';
                }
            }
        });
    }
    
    // 扫描表格排序功能
    let currentScanSortColumn = null;
    let currentScanSortDirection = 'asc';
    
    function setupScanTableSorting() {
        const table = document.getElementById('portfolio-scan-table');
        if (!table) return;
        
        const headers = table.querySelectorAll('th.sortable');
        headers.forEach(header => {
            header.addEventListener('click', () => {
                const column = header.getAttribute('data-column');
                sortScanTable(column);
            });
        });
    }
    
    function sortScanTable(column) {
        const table = document.getElementById('portfolio-scan-table');
        const tbody = document.getElementById('portfolio-scan-tbody');
        if (!table || !tbody) return;
        
        // 更新排序方向
        if (currentScanSortColumn === column) {
            currentScanSortDirection = currentScanSortDirection === 'asc' ? 'desc' : 'asc';
        } else {
            currentScanSortColumn = column;
            currentScanSortDirection = 'asc';
        }
        
        // 更新表头样式
        const headers = table.querySelectorAll('th.sortable');
        headers.forEach(header => {
            header.classList.remove('sort-asc', 'sort-desc');
            if (header.getAttribute('data-column') === column) {
                header.classList.add(currentScanSortDirection === 'asc' ? 'sort-asc' : 'sort-desc');
            }
        });
        
        // 获取所有行
        const rows = Array.from(tbody.querySelectorAll('tr'));
        
        // 排序函数
        rows.sort((a, b) => {
            let aValue = a.getAttribute(`data-${column.replace('_', '-')}`);
            let bValue = b.getAttribute(`data-${column.replace('_', '-')}`);
            
            // 处理不同数据类型
            if (['purchase_price', 'current_price', 'profit_loss_pct', 'confidence', 
                 'support_level', 'resistance_level', 'add_price', 'holding_days'].includes(column)) {
                aValue = parseFloat(aValue) || 0;
                bValue = parseFloat(bValue) || 0;
            } else if (column === 'expected_peak_date') {
                aValue = aValue ? new Date(aValue) : new Date(0);
                bValue = bValue ? new Date(bValue) : new Date(0);
            }
            
            let result = 0;
            if (aValue < bValue) result = -1;
            else if (aValue > bValue) result = 1;
            
            return currentScanSortDirection === 'asc' ? result : -result;
        });
        
        // 重新插入排序后的行
        rows.forEach(row => tbody.appendChild(row));
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
        const scanBtn = document.getElementById('scan-portfolio-btn');
        const content = document.getElementById('portfolio-content');
        
        // 显示加载状态
        content.innerHTML = '<div style="text-align: center; padding: 2rem; color: #6c757d;">正在加载持仓分析数据...</div>';
        
        if (scanBtn) {
            const originalText = scanBtn.textContent;
            scanBtn.textContent = '分析中...';
            scanBtn.disabled = true;
            
            fetch('/api/portfolio/scan', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    scanBtn.textContent = originalText;
                    scanBtn.disabled = false;

                    if (data.success) {
                        displayScanResults(data.results);
                    } else {
                        content.innerHTML = `<div style="color: #dc3545; text-align: center; padding: 2rem;">扫描失败: ${data.error}</div>`;
                    }
                })
                .catch(error => {
                    scanBtn.textContent = originalText;
                    scanBtn.disabled = false;
                    console.error('Error scanning portfolio:', error);
                    content.innerHTML = `<div style="color: #dc3545; text-align: center; padding: 2rem;">扫描出错: ${error.message}</div>`;
                });
        } else {
            // 如果没有扫描按钮（可能是自动触发），直接执行扫描
            fetch('/api/portfolio/scan', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        displayScanResults(data.results);
                    } else {
                        content.innerHTML = `<div style="color: #dc3545; text-align: center; padding: 2rem;">扫描失败: ${data.error}</div>`;
                    }
                })
                .catch(error => {
                    console.error('Error scanning portfolio:', error);
                    content.innerHTML = `<div style="color: #dc3545; text-align: center; padding: 2rem;">扫描出错: ${error.message}</div>`;
                });
        }
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
        
        // 添加缓存状态信息
        if (results.from_cache) {
            html += `
                <div class="cache-info" style="margin: 10px 0; padding: 8px 12px; background: #e7f3ff; border-left: 4px solid #007bff; border-radius: 4px; font-size: 13px;">
                    <span style="color: #007bff;">⚡ ${results.cache_info || '使用缓存数据，响应更快'}</span>
                    ${results.scan_duration ? ` | 原始扫描耗时: ${results.scan_duration}` : ''}
                </div>
            `;
        } else {
            html += `
                <div class="scan-info" style="margin: 10px 0; padding: 8px 12px; background: #f0f9ff; border-left: 4px solid #10b981; border-radius: 4px; font-size: 13px;">
                    <span style="color: #10b981;">🔍 实时扫描完成</span>
                    ${results.scan_duration ? ` | 扫描耗时: ${results.scan_duration}` : ''}
                </div>
            `;
        }

        // 显示详细持仓列表
        if (results.positions && results.positions.length > 0) {
            html += `
                <table class="portfolio-table" id="portfolio-scan-table">
                    <thead>
                        <tr>
                            <th class="sortable" data-column="stock_code">代码/名称</th>
                            <th class="sortable" data-column="sector">板块概念</th>
                            <th class="sortable" data-column="purchase_price">购买价格</th>
                            <th class="sortable" data-column="current_price">当前价格</th>
                            <th class="sortable" data-column="profit_loss_pct">盈亏</th>
                            <th class="sortable" data-column="action">操作建议</th>
                            <th class="sortable" data-column="confidence">置信度</th>
                            <th class="sortable" data-column="risk_level">风险等级</th>
                            <th class="sortable" data-column="support_level">支撑位</th>
                            <th class="sortable" data-column="resistance_level">阻力位</th>
                            <th class="sortable" data-column="add_price">补仓价</th>

                            <th class="sortable" data-column="expected_peak_date">预期到顶</th>
                            <th class="sortable" data-column="holding_days">持有天数</th>
                            <th>操作</th>
                        </tr>
                    </thead>
                    <tbody id="portfolio-scan-tbody">
            `;

            results.positions.forEach(position => {
                if (position.error) {
                    html += `
                        <tr>
                            <td>${position.stock_code}</td>
                            <td colspan="12" style="color: #dc3545;">${position.error}</td>
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

                const expectedPeakDate = position.timing_analysis?.expected_peak_date;
                const holdingDays = position.timing_analysis?.holding_days || 0;

                // 获取支撑阻力位信息
                const supportLevel = position.price_targets?.next_support;
                const resistanceLevel = position.price_targets?.next_resistance;

                // 创建置信度条
                const confidenceBar = `
                    <div style="display: flex; align-items: center; gap: 5px;">
                        <div style="width: 40px; height: 6px; background: #e9ecef; border-radius: 3px; overflow: hidden;">
                            <div style="width: ${confidence * 100}%; height: 100%; background: linear-gradient(90deg, #dc3545 0%, #ffc107 50%, #28a745 100%);"></div>
                        </div>
                        <span style="font-size: 11px;">${(confidence * 100).toFixed(0)}%</span>
                    </div>
                `;

                html += `
                    <tr data-stock-code="${position.stock_code}"
                        data-purchase-price="${position.purchase_price}"
                        data-current-price="${position.current_price}"
                        data-profit-loss-pct="${profitLoss}"
                        data-action="${action}"
                        data-confidence="${confidence}"
                        data-risk-level="${riskLevel}"
                        data-support-level="${supportLevel || 0}"
                        data-resistance-level="${resistanceLevel || 0}"
                        data-add-price="${addPrice || 0}"

                        data-expected-peak-date="${expectedPeakDate || ''}"
                        data-holding-days="${holdingDays}">
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
                        <td><span class="action-${action.toLowerCase()}">${getActionText(action)}</span></td>
                        <td>${confidenceBar}</td>
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

                        <td>${expectedPeakDate || '--'}</td>
                        <td>${holdingDays}天</td>
                        <td>
                            <button onclick="toggleCorePool('${position.stock_code}')" id="core-pool-scan-btn-${position.stock_code}" style="background: #ffc107; color: #212529; border: none; padding: 0.2rem 0.5rem; border-radius: 3px; cursor: pointer; margin-right: 0.3rem; font-size: 11px;">核心池</button>
                            <button onclick="showPositionDetailModal('${position.stock_code}')" style="background: #28a745; color: white; border: none; padding: 0.2rem 0.5rem; border-radius: 3px; cursor: pointer; font-size: 11px;">详情</button>
                        </td>
                    </tr>
                `;
            });

            html += '</tbody></table>';
        }

        content.innerHTML = html;
        
        // 添加排序功能
        setupScanTableSorting();
        
        // 更新核心池按钮状态
        updateCorePoolButtons();
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
    window.editPosition = function (stockCode) {
        // TODO: 实现编辑持仓功能
        alert('编辑功能开发中...');
    };

    window.removePosition = function (stockCode) {
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