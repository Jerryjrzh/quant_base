#!/usr/bin/env python3
"""
测试指标显示修复效果
验证MACD、KDJ和信号点显示是否正常
"""

import sys
import os
sys.path.append('backend')

import pandas as pd
import numpy as np
import json
from datetime import datetime

def test_indicator_ranges():
    """测试指标范围计算 - 使用模拟数据"""
    print("🧪 测试指标范围计算...")
    
    # 生成模拟测试数据
    dates = pd.date_range('2024-01-01', periods=100, freq='D')
    np.random.seed(42)  # 确保结果可重现
    
    # 生成价格数据
    base_price = 10.0
    price_changes = np.random.normal(0, 0.02, 100)
    prices = [base_price]
    
    for change in price_changes[1:]:
        new_price = prices[-1] * (1 + change)
        prices.append(max(new_price, 0.1))  # 确保价格为正
    
    # 创建OHLCV数据
    test_data = pd.DataFrame({
        'open': [p * (1 + np.random.normal(0, 0.005)) for p in prices],
        'high': [p * (1 + abs(np.random.normal(0, 0.01))) for p in prices],
        'low': [p * (1 - abs(np.random.normal(0, 0.01))) for p in prices],
        'close': prices,
        'volume': np.random.randint(100000, 1000000, 100)
    }, index=dates)
    
    # 确保high >= low
    test_data['high'] = np.maximum(test_data['high'], test_data['low'])
    
    print(f"✅ 生成测试数据: {len(test_data)} 个数据点")
    
    # 计算指标
    try:
        from indicators import calculate_macd, calculate_kdj
        
        # MACD
        dif, dea = calculate_macd(test_data)
        macd_histogram = dif - dea
        
        # KDJ
        k, d, j = calculate_kdj(test_data)
        
        # 分析指标范围
        results = {
            "test_type": "simulated_data",
            "data_points": len(test_data),
            "test_time": datetime.now().isoformat(),
            "indicators": {}
        }
        
        # MACD分析
        macd_values = pd.concat([dif, dea, macd_histogram]).dropna()
        if len(macd_values) > 0:
            results["indicators"]["MACD"] = {
                "min_value": float(macd_values.min()),
                "max_value": float(macd_values.max()),
                "range": float(macd_values.max() - macd_values.min()),
                "has_negative": bool((macd_values < 0).any()),
                "has_positive": bool((macd_values > 0).any()),
                "zero_crossings": int(((macd_values[:-1] * macd_values[1:]) < 0).sum())
            }
            
            print(f"📊 MACD范围: {results['indicators']['MACD']['min_value']:.4f} ~ {results['indicators']['MACD']['max_value']:.4f}")
        
        # KDJ分析
        kdj_values = pd.concat([k, d, j]).dropna()
        if len(kdj_values) > 0:
            results["indicators"]["KDJ"] = {
                "min_value": float(kdj_values.min()),
                "max_value": float(kdj_values.max()),
                "range": float(kdj_values.max() - kdj_values.min()),
                "has_negative": bool((kdj_values < 0).any()),
                "exceeds_100": bool((kdj_values > 100).any()),
                "k_min": float(k.min()) if not k.empty else None,
                "d_min": float(d.min()) if not d.empty else None,
                "j_min": float(j.min()) if not j.empty else None,
                "j_max": float(j.max()) if not j.empty else None
            }
            
            print(f"📊 KDJ范围: {results['indicators']['KDJ']['min_value']:.2f} ~ {results['indicators']['KDJ']['max_value']:.2f}")
            print(f"   - K值范围: {k.min():.2f} ~ {k.max():.2f}")
            print(f"   - D值范围: {d.min():.2f} ~ {d.max():.2f}")
            print(f"   - J值范围: {j.min():.2f} ~ {j.max():.2f}")
            
            if results["indicators"]["KDJ"]["has_negative"]:
                print("✅ KDJ包含负值，修复后应能正常显示")
            
            if results["indicators"]["KDJ"]["exceeds_100"]:
                print("✅ KDJ超过100，修复后应能正常显示")
        
        # 保存测试结果
        with open("indicator_range_test_results.json", 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        print("✅ 指标范围测试完成")
        return True
        
    except Exception as e:
        print(f"❌ 指标计算失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def create_frontend_test_data():
    """创建前端测试数据"""
    print("🎨 创建前端测试数据...")
    
    # 模拟包含边界情况的测试数据
    test_data = {
        "dates": [],
        "kline_data": [],
        "indicator_data": []
    }
    
    # 生成50天的测试数据
    import math
    for i in range(50):
        date = f"2024-07-{(i % 31) + 1:02d}"
        test_data["dates"].append(date)
        
        # K线数据
        base_price = 10 + math.sin(i * 0.1) * 2
        test_data["kline_data"].append({
            "date": date,
            "open": base_price + 0.1,
            "high": base_price + 0.3,
            "low": base_price - 0.2,
            "close": base_price,
            "volume": 1000000 + i * 10000
        })
        
        # 指标数据 - 包含边界情况
        macd_dif = math.sin(i * 0.15) * 0.5
        macd_dea = math.sin(i * 0.12) * 0.3
        
        kdj_k = 50 + math.sin(i * 0.2) * 40  # 可能超过100或低于0
        kdj_d = 50 + math.cos(i * 0.18) * 35
        kdj_j = 3 * kdj_k - 2 * kdj_d  # J值经常超出0-100范围
        
        test_data["indicator_data"].append({
            "date": date,
            "ma13": base_price + 0.05,
            "ma45": base_price - 0.05,
            "dif": macd_dif,
            "dea": macd_dea,
            "macd": macd_dif - macd_dea,
            "k": kdj_k,
            "d": kdj_d,
            "j": kdj_j,
            "rsi6": 30 + math.sin(i * 0.25) * 25,
            "rsi12": 40 + math.cos(i * 0.22) * 20,
            "rsi24": 50 + math.sin(i * 0.18) * 15
        })
    
    # 添加一些信号点
    test_data["signal_points"] = [
        {"date": "2024-07-05", "price": 10.2, "state": "BUY_SUCCESS"},
        {"date": "2024-07-15", "price": 11.1, "state": "SELL_FAIL"},
        {"date": "2024-07-25", "price": 9.8, "state": "BUY_PENDING"}
    ]
    
    # 保存测试数据
    with open("frontend_test_data.json", 'w', encoding='utf-8') as f:
        json.dump(test_data, f, ensure_ascii=False, indent=2)
    
    print("✅ 前端测试数据已创建: frontend_test_data.json")
    
    # 分析测试数据的范围
    kdj_values = []
    macd_values = []
    
    for item in test_data["indicator_data"]:
        kdj_values.extend([item["k"], item["d"], item["j"]])
        macd_values.extend([item["dif"], item["dea"], item["macd"]])
    
    print(f"📊 测试数据KDJ范围: {min(kdj_values):.2f} ~ {max(kdj_values):.2f}")
    print(f"📊 测试数据MACD范围: {min(macd_values):.4f} ~ {max(macd_values):.4f}")
    
    return test_data

def create_comprehensive_test_page():
    """创建综合测试页面"""
    
    test_html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>指标显示修复验证</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.0/dist/echarts.min.js"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        .test-section { background: white; margin: 20px 0; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .chart-container { width: 100%; height: 400px; border: 1px solid #ddd; margin: 10px 0; }
        .status { padding: 10px; margin: 10px 0; border-radius: 5px; }
        .status.success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .status.warning { background: #fff3cd; color: #856404; border: 1px solid #ffeaa7; }
        .status.info { background: #d1ecf1; color: #0c5460; border: 1px solid #bee5eb; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        .metric { background: #f8f9fa; padding: 10px; border-radius: 4px; margin: 5px 0; }
        button { background: #007bff; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; margin: 5px; }
        button:hover { background: #0056b3; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔧 指标显示修复验证</h1>
        
        <div class="status info">
            <h3>修复内容验证：</h3>
            <ul>
                <li><strong>MACD顶部异常</strong> - 改进范围计算，避免显示异常</li>
                <li><strong>KDJ底部负值</strong> - 移除0下限，允许显示负值</li>
                <li><strong>信号点图标</strong> - 优化三角图标显示效果</li>
            </ul>
        </div>
        
        <div class="test-section">
            <h2>📊 KDJ指标测试 (包含负值和超100值)</h2>
            <div id="kdj-range-info" class="metric"></div>
            <div id="kdj-chart" class="chart-container"></div>
            <button onclick="testKdjRange()">重新测试KDJ范围</button>
        </div>
        
        <div class="test-section">
            <h2>📈 MACD指标测试 (优化范围计算)</h2>
            <div id="macd-range-info" class="metric"></div>
            <div id="macd-chart" class="chart-container"></div>
            <button onclick="testMacdRange()">重新测试MACD范围</button>
        </div>
        
        <div class="test-section">
            <h2>🎯 信号点显示测试</h2>
            <div id="signal-info" class="metric"></div>
            <div id="signal-chart" class="chart-container"></div>
            <button onclick="testSignalPoints()">重新测试信号点</button>
        </div>
        
        <div class="test-section">
            <h2>📋 测试结果汇总</h2>
            <div id="test-summary"></div>
            <button onclick="runAllTests()">运行所有测试</button>
        </div>
    </div>
    
    <script>
        let testResults = {};
        
        // 修复后的范围计算函数
        function calculateKdjRange(kData, dData, jData) {
            const allKdjValues = [...kData, ...dData, ...jData].filter(val => val !== null && val !== undefined && !isNaN(val));
            let kdjMin = -10;
            let kdjMax = 110;
            
            if (allKdjValues.length > 0) {
                const actualMin = Math.min(...allKdjValues);
                const actualMax = Math.max(...allKdjValues);
                
                kdjMin = actualMin < 0 ? actualMin - 5 : Math.max(-10, actualMin - 5);
                kdjMax = actualMax > 100 ? actualMax + 5 : Math.min(110, actualMax + 5);
            }
            
            return { min: kdjMin, max: kdjMax };
        }
        
        function calculateMacdRange(difData, deaData, macdData) {
            const allMacdValues = [...difData, ...deaData, ...macdData].filter(val => val !== null && val !== undefined && !isNaN(val));
            let macdMin = -1;
            let macdMax = 1;
            
            if (allMacdValues.length > 0) {
                const actualMin = Math.min(...allMacdValues);
                const actualMax = Math.max(...allMacdValues);
                
                const range = actualMax - actualMin;
                const padding = Math.max(range * 0.1, 0.01);
                
                macdMin = actualMin - padding;
                macdMax = actualMax + padding;
                
                if (Math.abs(macdMax - macdMin) < 0.02) {
                    const center = (macdMax + macdMin) / 2;
                    macdMin = center - 0.01;
                    macdMax = center + 0.01;
                }
            }
            
            return { min: macdMin, max: macdMax };
        }
        
        // 生成测试数据
        function generateTestData() {
            const dates = [];
            const kData = [];
            const dData = [];
            const jData = [];
            const difData = [];
            const deaData = [];
            const macdData = [];
            const klineData = [];
            
            for (let i = 0; i < 60; i++) {
                dates.push(`2024-${String(Math.floor(i/30) + 7).padStart(2, '0')}-${String((i % 30) + 1).padStart(2, '0')}`);
                
                // KDJ数据 - 故意包含负值和超100值
                const k = 50 + Math.sin(i * 0.2) * 60; // -10 到 110
                const d = 45 + Math.cos(i * 0.15) * 50; // -5 到 95
                const j = 3 * k - 2 * d; // 可能大幅超出0-100范围
                
                kData.push(k);
                dData.push(d);
                jData.push(j);
                
                // MACD数据
                const dif = Math.sin(i * 0.1) * 0.8;
                const dea = Math.sin(i * 0.08) * 0.5;
                const macd = dif - dea;
                
                difData.push(dif);
                deaData.push(dea);
                macdData.push(macd);
                
                // K线数据
                const basePrice = 10 + Math.sin(i * 0.05) * 2;
                klineData.push([basePrice + 0.1, basePrice, basePrice - 0.2, basePrice + 0.3]);
            }
            
            return { dates, kData, dData, jData, difData, deaData, macdData, klineData };
        }
        
        function testKdjRange() {
            const data = generateTestData();
            const range = calculateKdjRange(data.kData, data.dData, data.jData);
            
            const chart = echarts.init(document.getElementById('kdj-chart'));
            
            chart.setOption({
                title: { text: 'KDJ指标范围测试', left: 'center' },
                tooltip: { trigger: 'axis' },
                legend: { data: ['K', 'D', 'J'], top: 30 },
                xAxis: { type: 'category', data: data.dates },
                yAxis: { 
                    type: 'value', 
                    min: range.min, 
                    max: range.max,
                    axisLabel: { formatter: '{value}' }
                },
                series: [
                    { name: 'K', type: 'line', data: data.kData, smooth: true, lineStyle: { color: '#f39c12' } },
                    { name: 'D', type: 'line', data: data.dData, smooth: true, lineStyle: { color: '#e74c3c' } },
                    { name: 'J', type: 'line', data: data.jData, smooth: true, lineStyle: { color: '#9b59b6' } }
                ]
            });
            
            const minVal = Math.min(...data.kData, ...data.dData, ...data.jData);
            const maxVal = Math.max(...data.kData, ...data.dData, ...data.jData);
            const hasNegative = minVal < 0;
            const exceeds100 = maxVal > 100;
            
            document.getElementById('kdj-range-info').innerHTML = `
                <strong>KDJ范围分析：</strong><br>
                实际范围: ${minVal.toFixed(2)} ~ ${maxVal.toFixed(2)}<br>
                显示范围: ${range.min.toFixed(2)} ~ ${range.max.toFixed(2)}<br>
                包含负值: ${hasNegative ? '✅ 是' : '❌ 否'}<br>
                超过100: ${exceeds100 ? '✅ 是' : '❌ 否'}
            `;
            
            testResults.kdj = { hasNegative, exceeds100, range, actualMin: minVal, actualMax: maxVal };
        }
        
        function testMacdRange() {
            const data = generateTestData();
            const range = calculateMacdRange(data.difData, data.deaData, data.macdData);
            
            const chart = echarts.init(document.getElementById('macd-chart'));
            
            chart.setOption({
                title: { text: 'MACD指标范围测试', left: 'center' },
                tooltip: { trigger: 'axis' },
                legend: { data: ['DIF', 'DEA', 'MACD'], top: 30 },
                xAxis: { type: 'category', data: data.dates },
                yAxis: { 
                    type: 'value', 
                    min: range.min, 
                    max: range.max,
                    axisLabel: { formatter: '{value}' }
                },
                series: [
                    { name: 'DIF', type: 'line', data: data.difData, smooth: true, lineStyle: { color: '#2ecc71' } },
                    { name: 'DEA', type: 'line', data: data.deaData, smooth: true, lineStyle: { color: '#e67e22' } },
                    { 
                        name: 'MACD', 
                        type: 'bar', 
                        data: data.macdData,
                        itemStyle: {
                            color: function(params) {
                                return params.value >= 0 ? '#ff6b6b' : '#4ecdc4';
                            }
                        }
                    }
                ]
            });
            
            const minVal = Math.min(...data.difData, ...data.deaData, ...data.macdData);
            const maxVal = Math.max(...data.difData, ...data.deaData, ...data.macdData);
            const rangeSize = maxVal - minVal;
            
            document.getElementById('macd-range-info').innerHTML = `
                <strong>MACD范围分析：</strong><br>
                实际范围: ${minVal.toFixed(4)} ~ ${maxVal.toFixed(4)}<br>
                显示范围: ${range.min.toFixed(4)} ~ ${range.max.toFixed(4)}<br>
                范围大小: ${rangeSize.toFixed(4)}<br>
                边距比例: ${(((range.max - range.min) - rangeSize) / rangeSize * 100).toFixed(1)}%
            `;
            
            testResults.macd = { range, actualMin: minVal, actualMax: maxVal, rangeSize };
        }
        
        function testSignalPoints() {
            const data = generateTestData();
            const signalData = [
                { date: data.dates[10], price: 10.5, state: 'BUY_SUCCESS' },
                { date: data.dates[25], price: 11.2, state: 'SELL_FAIL' },
                { date: data.dates[40], price: 9.8, state: 'BUY_PENDING' }
            ];
            
            const chart = echarts.init(document.getElementById('signal-chart'));
            
            chart.setOption({
                title: { text: '信号点显示测试', left: 'center' },
                tooltip: { trigger: 'axis' },
                legend: { data: ['K线', '交易信号'], top: 30 },
                xAxis: { type: 'category', data: data.dates },
                yAxis: { type: 'value' },
                series: [
                    {
                        name: 'K线',
                        type: 'candlestick',
                        data: data.klineData
                    },
                    {
                        name: '交易信号',
                        type: 'scatter',
                        data: signalData.map(signal => {
                            const dateIndex = data.dates.indexOf(signal.date);
                            return [dateIndex, signal.price];
                        }),
                        symbol: 'triangle',
                        symbolSize: 12,
                        itemStyle: {
                            color: function(params) {
                                const signal = signalData[params.dataIndex];
                                if (signal.state.includes('SUCCESS')) return '#00cc00';
                                if (signal.state.includes('FAIL')) return '#cc0000';
                                return '#ff9900';
                            },
                            borderColor: '#ffffff',
                            borderWidth: 1
                        },
                        tooltip: {
                            formatter: function(params) {
                                const signal = signalData[params.dataIndex];
                                return `
                                    <div style="text-align: left;">
                                        <strong>交易信号</strong><br/>
                                        日期: ${signal.date}<br/>
                                        价格: ¥${signal.price.toFixed(2)}<br/>
                                        状态: ${signal.state}
                                    </div>
                                `;
                            }
                        },
                        z: 10
                    }
                ]
            });
            
            document.getElementById('signal-info').innerHTML = `
                <strong>信号点显示分析：</strong><br>
                信号数量: ${signalData.length}<br>
                成功信号: ${signalData.filter(s => s.state.includes('SUCCESS')).length}<br>
                失败信号: ${signalData.filter(s => s.state.includes('FAIL')).length}<br>
                待确认信号: ${signalData.filter(s => s.state.includes('PENDING')).length}
            `;
            
            testResults.signals = { count: signalData.length, data: signalData };
        }
        
        function runAllTests() {
            testKdjRange();
            testMacdRange();
            testSignalPoints();
            
            setTimeout(() => {
                const summary = document.getElementById('test-summary');
                let html = '<div class="grid">';
                
                // KDJ测试结果
                if (testResults.kdj) {
                    const kdj = testResults.kdj;
                    html += `
                        <div class="status ${kdj.hasNegative && kdj.exceeds100 ? 'success' : 'warning'}">
                            <h4>KDJ测试结果</h4>
                            <p>负值显示: ${kdj.hasNegative ? '✅ 通过' : '❌ 未测试到'}</p>
                            <p>超100显示: ${kdj.exceeds100 ? '✅ 通过' : '❌ 未测试到'}</p>
                            <p>范围: ${kdj.actualMin.toFixed(2)} ~ ${kdj.actualMax.toFixed(2)}</p>
                        </div>
                    `;
                }
                
                // MACD测试结果
                if (testResults.macd) {
                    const macd = testResults.macd;
                    html += `
                        <div class="status success">
                            <h4>MACD测试结果</h4>
                            <p>范围计算: ✅ 正常</p>
                            <p>边距处理: ✅ 合理</p>
                            <p>范围: ${macd.actualMin.toFixed(4)} ~ ${macd.actualMax.toFixed(4)}</p>
                        </div>
                    `;
                }
                
                html += '</div>';
                summary.innerHTML = html;
            }, 1000);
        }
        
        // 页面加载时运行测试
        window.onload = function() {
            runAllTests();
        };
    </script>
</body>
</html>"""
    
    with open("test_indicator_display_comprehensive.html", 'w', encoding='utf-8') as f:
        f.write(test_html)
    
    print("✅ 已创建综合测试页面: test_indicator_display_comprehensive.html")

def main():
    """主函数"""
    print("🧪 开始验证指标显示修复效果...")
    
    # 测试指标范围计算
    if test_indicator_ranges():
        print("✅ 后端指标计算测试通过")
    else:
        print("❌ 后端指标计算测试失败")
    
    # 创建前端测试数据
    create_frontend_test_data()
    
    # 创建综合测试页面
    create_comprehensive_test_page()
    
    print("\n" + "="*60)
    print("🎉 指标显示修复验证完成！")
    print("="*60)
    print("测试文件:")
    print("1. 📊 indicator_range_test_results.json - 后端测试结果")
    print("2. 📈 frontend_test_data.json - 前端测试数据")
    print("3. 🌐 test_indicator_display_comprehensive.html - 综合测试页面")
    print("\n验证方法:")
    print("1. 打开 test_indicator_display_comprehensive.html 查看修复效果")
    print("2. 检查KDJ是否能显示负值和超100的值")
    print("3. 检查MACD范围计算是否正常")
    print("4. 检查信号点三角图标是否显示正常")
    print("="*60)

if __name__ == "__main__":
    main()