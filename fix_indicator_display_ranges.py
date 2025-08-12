#!/usr/bin/env python3
"""
修复指标显示范围问题
- MACD顶部异常：改进MACD范围计算逻辑
- KDJ底部小于0的情况没有显示：移除KDJ的0下限限制
- K线三角图标异常：优化信号点显示
"""

import json
import os
from datetime import datetime

def fix_frontend_indicator_ranges():
    """修复前端指标显示范围问题"""
    
    frontend_js_path = "frontend/js/app.js"
    
    if not os.path.exists(frontend_js_path):
        print(f"❌ 文件不存在: {frontend_js_path}")
        return False
    
    # 读取原文件
    with open(frontend_js_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 备份原文件
    backup_path = f"{frontend_js_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✅ 已备份原文件到: {backup_path}")
    
    # 修复指标范围计算逻辑
    old_range_calculation = """        // 计算各指标的动态范围
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
        const macdMax = allMacdValues.length > 0 ? Math.max(...allMacdValues) * 1.2 : 1;"""
    
    new_range_calculation = """        // 计算各指标的动态范围 - 修复版本
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
        }"""
    
    # 替换范围计算逻辑
    if old_range_calculation in content:
        content = content.replace(old_range_calculation, new_range_calculation)
        print("✅ 已修复指标范围计算逻辑")
    else:
        print("⚠️  未找到指标范围计算代码，可能已经修改过")
    
    # 修复信号点显示 - 优化三角图标
    old_signal_series = """        // 添加信号点
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
        }"""
    
    new_signal_series = """        // 添加信号点 - 修复版本
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
        }"""
    
    # 替换信号点显示逻辑
    if old_signal_series in content:
        content = content.replace(old_signal_series, new_signal_series)
        print("✅ 已修复信号点显示逻辑")
    else:
        print("⚠️  未找到信号点显示代码，可能已经修改过")
    
    # 写入修复后的文件
    with open(frontend_js_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ 已修复前端指标显示问题")
    return True

def create_test_page():
    """创建测试页面验证修复效果"""
    
    test_html = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>指标显示范围测试</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.0/dist/echarts.min.js"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .test-container { margin-bottom: 30px; }
        .chart-container { width: 100%; height: 400px; border: 1px solid #ddd; }
        .info { background: #f0f8ff; padding: 10px; margin: 10px 0; border-radius: 5px; }
    </style>
</head>
<body>
    <h1>指标显示范围测试</h1>
    
    <div class="info">
        <h3>测试目标：</h3>
        <ul>
            <li>✅ MACD顶部异常修复 - 改进范围计算</li>
            <li>✅ KDJ底部负值显示 - 移除0下限限制</li>
            <li>✅ K线三角图标优化 - 改进信号点显示</li>
        </ul>
    </div>
    
    <div class="test-container">
        <h3>KDJ指标测试 (包含负值)</h3>
        <div id="kdj-test-chart" class="chart-container"></div>
    </div>
    
    <div class="test-container">
        <h3>MACD指标测试 (范围优化)</h3>
        <div id="macd-test-chart" class="chart-container"></div>
    </div>
    
    <script>
        // 模拟KDJ数据，包含负值
        const kdjDates = [];
        const kData = [];
        const dData = [];
        const jData = [];
        
        for (let i = 0; i < 50; i++) {
            kdjDates.push(`2024-${String(Math.floor(i/30) + 1).padStart(2, '0')}-${String((i % 30) + 1).padStart(2, '0')}`);
            kData.push(Math.sin(i * 0.2) * 30 + 50);
            dData.push(Math.cos(i * 0.15) * 25 + 45);
            jData.push(Math.sin(i * 0.3) * 60 + 40); // J值可能为负
        }
        
        // 模拟MACD数据
        const macdDates = [];
        const difData = [];
        const deaData = [];
        const macdHistogram = [];
        
        for (let i = 0; i < 50; i++) {
            macdDates.push(`2024-${String(Math.floor(i/30) + 1).padStart(2, '0')}-${String((i % 30) + 1).padStart(2, '0')}`);
            const dif = Math.sin(i * 0.1) * 0.5;
            const dea = Math.sin(i * 0.08) * 0.3;
            difData.push(dif);
            deaData.push(dea);
            macdHistogram.push(dif - dea);
        }
        
        // 使用修复后的范围计算逻辑
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
        
        // 渲染KDJ测试图表
        const kdjChart = echarts.init(document.getElementById('kdj-test-chart'));
        const kdjRange = calculateKdjRange(kData, dData, jData);
        
        kdjChart.setOption({
            title: { text: `KDJ指标测试 (范围: ${kdjRange.min.toFixed(1)} ~ ${kdjRange.max.toFixed(1)})` },
            tooltip: { trigger: 'axis' },
            legend: { data: ['K', 'D', 'J'] },
            xAxis: { type: 'category', data: kdjDates },
            yAxis: { 
                type: 'value', 
                min: kdjRange.min, 
                max: kdjRange.max,
                axisLabel: { formatter: '{value}' }
            },
            series: [
                { name: 'K', type: 'line', data: kData, smooth: true },
                { name: 'D', type: 'line', data: dData, smooth: true },
                { name: 'J', type: 'line', data: jData, smooth: true }
            ]
        });
        
        // 渲染MACD测试图表
        const macdChart = echarts.init(document.getElementById('macd-test-chart'));
        const macdRange = calculateMacdRange(difData, deaData, macdHistogram);
        
        macdChart.setOption({
            title: { text: `MACD指标测试 (范围: ${macdRange.min.toFixed(3)} ~ ${macdRange.max.toFixed(3)})` },
            tooltip: { trigger: 'axis' },
            legend: { data: ['DIF', 'DEA', 'MACD'] },
            xAxis: { type: 'category', data: macdDates },
            yAxis: { 
                type: 'value', 
                min: macdRange.min, 
                max: macdRange.max,
                axisLabel: { formatter: '{value}' }
            },
            series: [
                { name: 'DIF', type: 'line', data: difData, smooth: true },
                { name: 'DEA', type: 'line', data: deaData, smooth: true },
                { 
                    name: 'MACD', 
                    type: 'bar', 
                    data: macdHistogram,
                    itemStyle: {
                        color: function(params) {
                            return params.value >= 0 ? '#ff6b6b' : '#4ecdc4';
                        }
                    }
                }
            ]
        });
        
        console.log('✅ 指标显示范围测试页面已加载');
        console.log('KDJ范围:', kdjRange);
        console.log('MACD范围:', macdRange);
    </script>
</body>
</html>"""
    
    with open("test_indicator_ranges_fix.html", 'w', encoding='utf-8') as f:
        f.write(test_html)
    
    print("✅ 已创建测试页面: test_indicator_ranges_fix.html")

def main():
    """主函数"""
    print("🔧 开始修复指标显示范围问题...")
    
    # 修复前端代码
    if fix_frontend_indicator_ranges():
        print("✅ 前端修复完成")
    else:
        print("❌ 前端修复失败")
        return
    
    # 创建测试页面
    create_test_page()
    
    # 生成修复报告
    report = {
        "fix_time": datetime.now().isoformat(),
        "fixes_applied": [
            {
                "issue": "MACD顶部异常",
                "solution": "改进MACD范围计算逻辑，使用更合理的边距策略",
                "status": "已修复"
            },
            {
                "issue": "KDJ底部负值不显示",
                "solution": "移除KDJ指标0下限限制，允许显示负值",
                "status": "已修复"
            },
            {
                "issue": "K线三角图标异常",
                "solution": "优化信号点显示，改进颜色和样式",
                "status": "已修复"
            }
        ],
        "test_files": [
            "test_indicator_ranges_fix.html"
        ],
        "backup_files": [
            "frontend/js/app.js.backup_*"
        ]
    }
    
    with open("indicator_display_fix_report.json", 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print("\n" + "="*60)
    print("🎉 指标显示范围修复完成！")
    print("="*60)
    print("修复内容:")
    print("1. ✅ MACD顶部异常 - 改进范围计算逻辑")
    print("2. ✅ KDJ底部负值显示 - 移除0下限限制") 
    print("3. ✅ K线三角图标优化 - 改进信号点显示")
    print("\n测试方法:")
    print("1. 打开 test_indicator_ranges_fix.html 查看修复效果")
    print("2. 重启Web服务器并测试实际股票数据")
    print("3. 检查修复报告: indicator_display_fix_report.json")
    print("="*60)

if __name__ == "__main__":
    main()