document.addEventListener('DOMContentLoaded', function() {
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
                    switch(state) {
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
                        { left: '10%', right: '8%', height: '50%' }, { left: '10%', right: '8%', top: '63%', height: '10%' },
                        { left: '10%', right: '8%', top: '76%', height: '10%' }, { left: '10%', right: '8%', top: '89%', height: '10%' }
                    ],
                    xAxis: [
                        { type: 'category', data: dates, scale: true, boundaryGap: false, axisLine: { onZero: false }, splitLine: { show: false }, axisLabel: { show: false } },
                        { type: 'category', data: dates, scale: true, gridIndex: 1, boundaryGap: false, axisLine: { onZero: false }, axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false } },
                        { type: 'category', data: dates, scale: true, gridIndex: 2, boundaryGap: false, axisLine: { onZero: false }, axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false } },
                        { type: 'category', data: dates, scale: true, gridIndex: 3, boundaryGap: false, axisLine: { onZero: false }, axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false } }
                    ],
                    yAxis: [
                        { scale: true, splitArea: { show: true } }, { scale: true, gridIndex: 1, axisLabel: { show: false }, axisLine: { show: false }, axisTick: { show: false }, splitLine: { show: false } },
                        { scale: true, gridIndex: 2, axisLabel: { show: false }, axisLine: { show: false }, axisTick: { show: false }, splitLine: { show: false } },
                        { scale: true, gridIndex: 3, axisLabel: { show: false }, axisLine: { show: false }, axisTick: { show: false }, splitLine: { show: false } }
                    ],
                    dataZoom: [
                        { type: 'inside', xAxisIndex: [0, 1, 2, 3], start: 80, end: 100 },
                        { show: true, type: 'slider', xAxisIndex: [0, 1, 2, 3], top: '97%', start: 80, end: 100 }
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
    
    // 历史报告功能
    historyBtn.addEventListener('click', showHistoryModal);
    refreshBtn.addEventListener('click', refreshData);
    closeModal.addEventListener('click', hideHistoryModal);
    
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
        switch(targetTab) {
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
    
    populateStockList();
});
