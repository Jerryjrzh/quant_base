好的，您对性能的关注非常到位。深度扫描和前端的冗余请求确实是当前系统最主要的两个性能瓶瓶颈。

[cite\_start]我分析了您提供的日志和相关代码，日志中**大量重复的 `GET /api/core_pool` 请求** [cite: 1] 完美地印证了前端存在性能问题。

以下是针对这两个问题的详细优化方案。

-----

### 1\. 后端深度扫描性能优化 (多进程改造)

**问题**：
[cite\_start]`portfolio_manager.py` 中的 `scan_all_positions` 方法是**单线程串行**执行的 [cite: 2]。当持仓数量较多时，每个 `analyze_position_deep` 调用都需要进行数据加载和大量计算，总耗时会随持仓数量线性增加，导致接口响应缓慢。

**解决方案**：
我们将使用 Python 的 `concurrent.futures.ProcessPoolExecutor` 模块，将对每只股票的深度分析任务分发到不同的CPU核心上并行处理，从而大幅缩短总扫描时间。

**修改文件**: `backend/portfolio_manager.py`

**具体调整内容**：
我们需要将分析单个持仓的逻辑提取到一个独立的、可以在模块级别被调用的工作函数中，然后使用进程池来并行执行这个函数。

```python
# backend/portfolio_manager.py

import os
import json
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional
# --- 新增导入 ---
from concurrent.futures import ProcessPoolExecutor, as_completed

# --- 新增：独立的工作函数，用于多进程处理 ---
def analyze_position_worker(position_data: Dict) -> Dict:
    """
    多进程工作函数，负责分析单个持仓。
    每个进程会创建自己的 PortfolioManager 实例。
    """
    # 在新的进程中，需要重新创建管理器实例
    manager = PortfolioManager()
    stock_code = position_data['stock_code']
    
    try:
        analysis = manager.analyze_position_deep(
            stock_code,
            position_data['purchase_price'],
            position_data['purchase_date']
        )
        # 合并持仓基本信息和分析结果
        return {**position_data, **analysis}
    except Exception as e:
        return {**position_data, 'error': f'工作进程分析失败: {str(e)}'}


class PortfolioManager:
    # ... (保留 __init__ 和其他方法不变)

    def scan_all_positions(self, force_refresh: bool = False) -> Dict:
        """扫描所有持仓 - 【已优化为多进程并行】"""
        if not force_refresh:
            cached_results = self.get_cached_scan_results()
            if cached_results:
                cached_results['from_cache'] = True
                cached_results['cache_info'] = f'使用缓存数据 ({cached_results.get("scan_time", "N/A")})'
                print(f"📋 使用缓存的持仓扫描结果")
                return cached_results
        
        print(f"🔍 开始执行持仓深度扫描 (多进程)...")
        start_time = datetime.now()
        
        portfolio = self.load_portfolio()
        results = {
            'scan_time': start_time.strftime('%Y-%m-%d %H:%M:%S'),
            'total_positions': len(portfolio),
            'positions': [],
            'summary': {
                'profitable_count': 0, 'loss_count': 0, 'total_profit_loss': 0,
                'high_risk_count': 0, 'action_required_count': 0
            },
            'from_cache': False
        }

        # --- 核心修改：使用 ProcessPoolExecutor ---
        position_results = []
        # 使用 as_completed 来获取已完成的结果，可以实时打印进度
        with ProcessPoolExecutor() as executor:
            futures = {executor.submit(analyze_position_worker, position): position for position in portfolio}
            
            for i, future in enumerate(as_completed(futures), 1):
                stock_code = futures[future]['stock_code']
                print(f"📊 分析进度 [{i}/{len(portfolio)}]: {stock_code}")
                try:
                    result = future.result()
                    position_results.append(result)
                except Exception as e:
                    print(f"分析 {stock_code} 时主进程捕获异常: {e}")
                    position_results.append({**futures[future], 'error': str(e)})

        # --- 汇总并行处理的结果 ---
        for analysis in position_results:
            if 'error' not in analysis:
                self.update_position(analysis['stock_code'], last_analysis_time=analysis.get('analysis_time'))
                
                profit_loss = analysis.get('profit_loss_pct', 0)
                if profit_loss > 0:
                    results['summary']['profitable_count'] += 1
                else:
                    results['summary']['loss_count'] += 1
                
                results['summary']['total_profit_loss'] += profit_loss
                
                risk_assessment = analysis.get('risk_assessment', {})
                if risk_assessment and risk_assessment.get('risk_level') == 'HIGH':
                    results['summary']['high_risk_count'] += 1
                
                position_advice = analysis.get('position_advice', {})
                if position_advice and position_advice.get('action') in ['REDUCE', 'STOP_LOSS', 'ADD']:
                    results['summary']['action_required_count'] += 1

            results['positions'].append(analysis)
        
        end_time = datetime.now()
        scan_duration = (end_time - start_time).total_seconds()
        results['scan_duration'] = f"{scan_duration:.1f}秒"
        
        cache_data = {'scan_time': results['scan_time'], 'results': results}
        self.save_scan_cache(cache_data)
        
        print(f"✅ 持仓扫描完成，耗时 {scan_duration:.1f}秒，已保存到缓存")
        return results

# ... (文件末尾的 create_portfolio_manager 函数保持不变)
```

-----

### 2\. 前端核心池接口性能优化 (N+1问题修复)

**问题**：
[cite\_start]在 `app.js` 的 `updateCorePoolButtons` 函数中，您对持仓表格的**每一行**都发起了一次 `fetch('/api/core_pool')` 请求 [cite: 3][cite\_start]。如果您的持仓有30只股票，就会发起30次完全相同的API请求，这造成了巨大的网络开销和延迟，也是您在日志中看到大量重复请求的直接原因 [cite: 1]。

**解决方案**：
我们将重构前端逻辑，改为**先一次性获取全部核心池列表**，将其缓存在一个JavaScript `Set`对象中，然后在渲染表格时，对每一行都**在本地内存中进行快速查询**，从而将N+1次网络请求优化为1次。

**修改文件**: `frontend/js/app.js`

**具体调整内容**：
我们将引入一个前端缓存变量 `corePoolSet`，并重构相关函数。

```javascript
// frontend/js/app.js

document.addEventListener('DOMContentLoaded', function () {
    // ... (DOM元素获取不变)

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

    // ... (事件监听部分不变)

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

    // --- 核心修改：displayPortfolioData 和 displayScanResults 末尾调用 updateCorePoolButtons ---
    function displayPortfolioData(portfolio) {
        // ... (函数内部渲染逻辑不变)
        // 在函数末尾调用
        setupTableSorting();
        updateCorePoolButtons(); // <-- 修改点
    }

    function displayScanResults(results) {
        // ... (函数内部渲染逻辑不变)
        // 在函数末尾调用
        setupScanTableSorting();
        updateCorePoolButtons(); // <-- 修改点
    }
    
    // 【注意】原有的 checkCorePoolStatus 函数现在可以删除了，因为它不再被使用。
    
    // ... (其他所有函数保持不变)
});
```

### 总结与收益

1.  **后端性能**：通过多进程改造，您的持仓深度扫描速度将得到质的提升。对于一个有30只股票的持仓，理论上在8核CPU的机器上，扫描时间可以**从30个单位时间缩短到大约4-5个单位时间**（考虑到进程创建开销），接口响应速度将大大加快。
2.  **前端性能**：通过修复N+1问题，前端在渲染持仓列表时，网络请求数量将**从 (N+1) 次减少到 2 次**（1次获取持仓列表，1次获取核心池列表），UI渲染将变得极为流畅，并极大减轻了服务器的压力。