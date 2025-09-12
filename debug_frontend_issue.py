#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试前端图表显示问题
"""

import sys
import os
sys.path.append('backend')

from unified_analysis_service import get_or_run_analysis
import json

def debug_frontend_data():
    """调试前端数据问题"""
    print("=== 前端数据调试 ===")
    
    # 测试API调用
    stock_code = 'sh600006'
    strategy_id = 'WEEKLY_GOLDEN_CROSS_MA'
    
    print(f"测试: {stock_code} @ {strategy_id}")
    
    try:
        result = get_or_run_analysis(stock_code, strategy_id)
        
        if result.get('success'):
            print("✅ API调用成功")
            
            # 检查数据结构
            data = result['data']
            chart_data = data['chart_data']
            
            print(f"图表数据结构:")
            print(f"  - kline_data: {len(chart_data['kline_data'])} 条")
            print(f"  - indicator_data: {len(chart_data['indicator_data'])} 条")
            print(f"  - signal_points: {len(chart_data['signal_points'])} 条")
            
            # 检查前几条数据
            print(f"\n前3条K线数据:")
            for i, kline in enumerate(chart_data['kline_data'][:3]):
                print(f"  {i+1}: {kline}")
            
            print(f"\n前3条指标数据:")
            for i, indicator in enumerate(chart_data['indicator_data'][:3]):
                print(f"  {i+1}: date={indicator.get('date')}")
                ma_fields = ['ma7', 'ma13', 'ma30', 'ma45', 'ma60', 'ma90', 'ma150', 'ma240']
                for field in ma_fields:
                    value = indicator.get(field)
                    if value is not None:
                        print(f"      {field}: {value}")
                    else:
                        print(f"      {field}: None")
                break  # 只显示第一条的详细信息
            
            # 检查最后几条数据
            print(f"\n最后3条指标数据的MA值:")
            for i, indicator in enumerate(chart_data['indicator_data'][-3:]):
                print(f"  倒数第{3-i}条: date={indicator.get('date')}")
                ma_fields = ['ma7', 'ma13', 'ma30', 'ma45', 'ma60', 'ma90', 'ma150', 'ma240']
                ma_values = []
                for field in ma_fields:
                    value = indicator.get(field)
                    if value is not None:
                        ma_values.append(f"{field}:{value:.2f}")
                    else:
                        ma_values.append(f"{field}:None")
                print(f"      {', '.join(ma_values)}")
            
            # 生成前端测试用的JSON数据
            test_data = {
                'success': True,
                'data': {
                    'stock_code': stock_code,
                    'stock_name': data.get('stock_name', stock_code),
                    'chart_data': {
                        'kline_data': chart_data['kline_data'][-60:],  # 最近60天
                        'indicator_data': chart_data['indicator_data'][-60:],  # 最近60天
                        'signal_points': chart_data['signal_points']
                    }
                }
            }
            
            # 保存测试数据
            with open('frontend_test_data.json', 'w', encoding='utf-8') as f:
                json.dump(test_data, f, ensure_ascii=False, indent=2, default=str)
            
            print(f"\n✅ 测试数据已保存到 frontend_test_data.json")
            print(f"   包含最近60天的数据用于前端测试")
            
        else:
            print(f"❌ API调用失败: {result.get('error')}")
            
    except Exception as e:
        print(f"❌ 调试失败: {e}")
        import traceback
        traceback.print_exc()

def create_simple_test_html():
    """创建简单的测试HTML页面"""
    html_content = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>前端调试测试</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.0/dist/echarts.min.js"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        #chart { width: 100%; height: 500px; border: 1px solid #ddd; }
        .controls { margin: 20px 0; }
        button { margin: 5px; padding: 10px; }
        .log { margin: 10px 0; padding: 10px; background: #f5f5f5; font-family: monospace; white-space: pre-wrap; max-height: 300px; overflow-y: auto; }
    </style>
</head>
<body>
    <h1>前端调试测试</h1>
    
    <div class="controls">
        <button onclick="testLocalData()">测试本地数据</button>
        <button onclick="testAPIData()">测试API数据</button>
        <button onclick="clearChart()">清空图表</button>
    </div>
    
    <div id="chart"></div>
    <div class="log" id="log">等待测试...</div>

    <script>
        const chart = echarts.init(document.getElementById('chart'));
        const logDiv = document.getElementById('log');
        
        function log(message) {
            console.log(message);
            logDiv.textContent += new Date().toLocaleTimeString() + ': ' + message + '\\n';
            logDiv.scrollTop = logDiv.scrollHeight;
        }
        
        async function testLocalData() {
            log('开始测试本地数据...');
            
            try {
                const response = await fetch('./frontend_test_data.json');
                if (!response.ok) {
                    throw new Error('无法加载本地测试数据');
                }
                
                const result = await response.json();
                log('本地数据加载成功');
                
                renderChart(result.data.chart_data, result.data.stock_code, result.data.stock_name);
                
            } catch (error) {
                log(`本地数据测试失败: ${error.message}`);
            }
        }
        
        async function testAPIData() {
            log('开始测试API数据...');
            
            try {
                const response = await fetch('/api/unified_analysis/sh600006?strategy=WEEKLY_GOLDEN_CROSS_MA');
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
                
                const result = await response.json();
                log(`API响应: success=${result.success}`);
                
                if (!result.success) {
                    throw new Error(result.error || '未知错误');
                }
                
                renderChart(result.data.chart_data, result.data.stock_code, result.data.stock_name);
                
            } catch (error) {
                log(`API数据测试失败: ${error.message}`);
            }
        }
        
        function renderChart(chartData, stockCode, stockName) {
            log('开始渲染图表...');
            
            const dates = chartData.kline_data.map(item => item.date);
            const klineData = chartData.kline_data.map(item => [item.open, item.close, item.low, item.high]);
            
            // MA数据
            const ma7Data = chartData.indicator_data.map(item => item.ma7);
            const ma13Data = chartData.indicator_data.map(item => item.ma13);
            const ma30Data = chartData.indicator_data.map(item => item.ma30);
            const ma45Data = chartData.indicator_data.map(item => item.ma45);
            const ma60Data = chartData.indicator_data.map(item => item.ma60);
            const ma90Data = chartData.indicator_data.map(item => item.ma90);
            const ma150Data = chartData.indicator_data.map(item => item.ma150);
            const ma240Data = chartData.indicator_data.map(item => item.ma240);
            
            log(`数据统计:`);
            log(`  日期: ${dates.length} 条`);
            log(`  K线: ${klineData.length} 条`);
            log(`  MA7有效: ${ma7Data.filter(v => v !== null && v !== undefined).length} 条`);
            log(`  MA13有效: ${ma13Data.filter(v => v !== null && v !== undefined).length} 条`);
            log(`  MA240有效: ${ma240Data.filter(v => v !== null && v !== undefined).length} 条`);
            
            const option = {
                title: {
                    text: `${stockCode} ${stockName || ''} - MA指标测试`,
                    left: 'center'
                },
                tooltip: {
                    trigger: 'axis',
                    axisPointer: { type: 'cross' }
                },
                legend: {
                    data: ['K线', 'MA7', 'MA13', 'MA30', 'MA45', 'MA60', 'MA90', 'MA150', 'MA240'],
                    top: 30
                },
                grid: {
                    left: '3%',
                    right: '4%',
                    bottom: '3%',
                    containLabel: true
                },
                xAxis: {
                    type: 'category',
                    data: dates
                },
                yAxis: {
                    type: 'value',
                    scale: true
                },
                dataZoom: [
                    {
                        type: 'inside',
                        start: 70,
                        end: 100
                    },
                    {
                        show: true,
                        type: 'slider',
                        bottom: 10,
                        start: 70,
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
            
            chart.setOption(option, true);
            log('图表渲染完成');
        }
        
        function clearChart() {
            chart.clear();
            logDiv.textContent = '图表已清空\\n';
        }
    </script>
</body>
</html>'''
    
    with open('debug_frontend.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print("✅ 调试页面已创建: debug_frontend.html")

if __name__ == '__main__':
    debug_frontend_data()
    create_simple_test_html()
    print("\n=== 调试完成 ===")
    print("1. 检查 frontend_test_data.json 中的数据")
    print("2. 在浏览器中打开 debug_frontend.html 进行测试")
    print("3. 检查浏览器控制台是否有JavaScript错误")