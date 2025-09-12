// 修复前端图表显示问题的脚本

// 检查并修复renderEchart函数
function fixRenderEchart() {
    // 这是修复后的renderEchart函数
    window.renderEchartFixed = function(chartData, stockCode, strategy, stockName) {
        console.log('开始渲染图表...', { stockCode, strategy, stockName });
        console.log('图表数据:', chartData);
        
        if (!chartData || !chartData.kline_data || !chartData.indicator_data) {
            console.error('图表数据不完整:', chartData);
            return;
        }
        
        const dates = chartData.kline_data.map(item => item.date);
        const klineData = chartData.kline_data.map(item => [item.open, item.close, item.low, item.high]);
        
        // 技术指标数据 - 完整MA系列
        const ma7Data = chartData.indicator_data.map(item => item.ma7);
        const ma13Data = chartData.indicator_data.map(item => item.ma13);
        const ma30Data = chartData.indicator_data.map(item => item.ma30);
        const ma45Data = chartData.indicator_data.map(item => item.ma45);
        const ma60Data = chartData.indicator_data.map(item => item.ma60);
        const ma90Data = chartData.indicator_data.map(item => item.ma90);
        const ma150Data = chartData.indicator_data.map(item => item.ma150);
        const ma240Data = chartData.indicator_data.map(item => item.ma240);
        
        // 其他指标数据
        const difData = chartData.indicator_data.map(item => item.dif);
        const deaData = chartData.indicator_data.map(item => item.dea);
        const macdData = chartData.indicator_data.map(item => item.macd);
        const kData = chartData.indicator_data.map(item => item.k);
        const dData = chartData.indicator_data.map(item => item.d);
        const jData = chartData.indicator_data.map(item => item.j);
        const rsi6Data = chartData.indicator_data.map(item => item.rsi6);
        const rsi12Data = chartData.indicator_data.map(item => item.rsi12);
        const rsi24Data = chartData.indicator_data.map(item => item.rsi24);
        
        console.log('数据统计:', {
            dates: dates.length,
            kline: klineData.length,
            ma7Valid: ma7Data.filter(v => v !== null && v !== undefined).length,
            ma13Valid: ma13Data.filter(v => v !== null && v !== undefined).length,
            ma240Valid: ma240Data.filter(v => v !== null && v !== undefined).length
        });
        
        // 计算显示范围
        const totalDataPoints = dates.length;
        const defaultShowCount = Math.min(252, totalDataPoints);
        const startPercent = Math.max(0, ((totalDataPoints - defaultShowCount) / totalDataPoints) * 100);
        
        // 简化的图表配置
        const option = {
            title: {
                text: `${stockCode} ${stockName || ''} - ${strategy}策略分析`,
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
                data: ['K线', 'MA7', 'MA13', 'MA30', 'MA45', 'MA60', 'MA90', 'MA150', 'MA240'],
                top: 30,
                textStyle: { fontSize: 12 }
            },
            grid: {
                left: '3%',
                right: '4%',
                bottom: '15%',
                top: '15%',
                containLabel: true
            },
            xAxis: {
                type: 'category',
                data: dates,
                boundaryGap: false
            },
            yAxis: {
                type: 'value',
                scale: true
            },
            dataZoom: [
                {
                    type: 'inside',
                    start: startPercent,
                    end: 100
                },
                {
                    show: true,
                    type: 'slider',
                    bottom: '5%',
                    height: 20,
                    start: startPercent,
                    end: 100
                }
            ],
            series: [
                {
                    name: 'K线',
                    type: 'candlestick',
                    data: klineData
                },
                {
                    name: 'MA7',
                    type: 'line',
                    data: ma7Data,
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 1, color: '#ff6b6b' }
                },
                {
                    name: 'MA13',
                    type: 'line',
                    data: ma13Data,
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 1, color: '#4ecdc4' }
                },
                {
                    name: 'MA30',
                    type: 'line',
                    data: ma30Data,
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 1, color: '#45b7d1' }
                },
                {
                    name: 'MA45',
                    type: 'line',
                    data: ma45Data,
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 1, color: '#f39c12' }
                },
                {
                    name: 'MA60',
                    type: 'line',
                    data: ma60Data,
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 1, color: '#e74c3c' }
                },
                {
                    name: 'MA90',
                    type: 'line',
                    data: ma90Data,
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 1, color: '#9b59b6' }
                },
                {
                    name: 'MA150',
                    type: 'line',
                    data: ma150Data,
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 1, color: '#2ecc71' }
                },
                {
                    name: 'MA240',
                    type: 'line',
                    data: ma240Data,
                    smooth: true,
                    symbol: 'none',
                    lineStyle: { width: 1, color: '#e67e22' }
                }
            ]
        };
        
        console.log('ECharts配置:', option);
        
        // 获取图表实例
        const chartContainer = document.getElementById('chart-container');
        if (!chartContainer) {
            console.error('找不到chart-container元素');
            return;
        }
        
        // 确保图表实例存在
        if (!window.myChart) {
            console.log('初始化ECharts实例...');
            window.myChart = echarts.init(chartContainer);
        }
        
        // 设置图表选项
        window.myChart.setOption(option, true);
        console.log('图表渲染完成');
    };
}

// 修复loadUnifiedStockData函数中的图表渲染调用
function fixLoadUnifiedStockData() {
    window.loadUnifiedStockDataFixed = async function() {
        const stockSelect = document.getElementById('stock-select');
        const strategySelect = document.getElementById('strategy-select');
        
        const stockCode = stockSelect.value;
        const strategy = strategySelect.value;

        if (!stockCode || !strategy) {
            console.log('股票代码或策略未选择');
            return;
        }

        console.log('开始加载统一股票数据...', { stockCode, strategy });

        // 显示加载状态
        if (window.myChart) {
            window.myChart.showLoading();
        }

        try {
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
            
            // 使用修复后的渲染函数
            window.renderEchartFixed(
                unifiedData.chart_data, 
                stockCode, 
                strategy, 
                unifiedData.stock_name
            );

        } catch (error) {
            console.error('统一数据加载失败:', error);
            if (window.myChart) {
                window.myChart.clear();
                window.myChart.setOption({
                    title: { text: '加载数据失败', subtext: error.message, left: 'center', top: 'center' }
                });
            }
        } finally {
            if (window.myChart) {
                window.myChart.hideLoading();
            }
        }
    };
}

// 初始化修复
function initFix() {
    console.log('初始化前端图表修复...');
    fixRenderEchart();
    fixLoadUnifiedStockData();
    
    // 替换原有的事件监听器
    const stockSelect = document.getElementById('stock-select');
    if (stockSelect) {
        // 移除原有的事件监听器（如果有的话）
        stockSelect.removeEventListener('change', window.loadUnifiedStockData);
        // 添加修复后的事件监听器
        stockSelect.addEventListener('change', window.loadUnifiedStockDataFixed);
        console.log('已替换股票选择事件监听器');
    }
    
    console.log('前端图表修复完成');
}

// 页面加载完成后初始化修复
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initFix);
} else {
    initFix();
}