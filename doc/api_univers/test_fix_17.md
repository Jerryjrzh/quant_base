好的，您提的问题非常关键，这直指我们系统架构的核心——如何实现“**扫描一次，处处使用**”，从而避免重复计算，真正发挥数据库缓存的威力。

您观察到的现象完全正确：

1.  **每次都重新扫描**：当前每次在前端选择策略，后端都会重新运行一次 `UniversalScreener`，而不是从数据库读取今日已有的扫描结果。
2.  **分析与扫描脱节**：策略扫描（`UniversalScreener`）只找出了有哪些股票符合策略，但并没有立即对这些股票进行深度分析和回测。这导致了只有当您点击某只股票时，后端才开始为它计算深度数据，并且回测面板在那之前也无法显示。

这违背了我们建立统一服务和缓存的初衷。

现在，我们将进行一次**最终的、也是最关键的架构重构**，将“扫描”和“分析”两大流程彻底打通，实现您的目标：**后端执行 `UniversalScreener` 时，就完成所有必要分析并全部存入数据库。**

-----

### 最终架构优化方案

我们将重构 `UniversalScreener`，赋予它新的职责：它不再只是一个简单的“信号发现者”，而是成为一个“**分析预热器**”。当它发现一个信号时，会立即调用我们强大的 `unified_analysis_service`，将该股票的完整分析（包括回测、交易建议、图表数据等）直接生成并存入数据库缓存。

#### 第1步：升级 `UniversalScreener` 为“分析预热器”

**修改文件**：`backend/universal_screener.py`

**请用以下代码替换 `universal_screener.py` 的全部内容。** 这个新版本将在发现信号后，立即调用统一分析服务来预热缓存。

```python
# backend/universal_screener.py

"""
【最终优化版】通用股票筛选器 (已升级为分析预热器)
"""
import pandas as pd
from typing import List, Optional
from dataclasses import dataclass, asdict

from strategy_manager import strategy_manager
from data_handler import get_full_data_with_indicators
# --- 核心修改：导入统一分析服务 ---
from unified_analysis_service import get_or_run_analysis

@dataclass
class StrategyResult:
    stock_code: str
    stock_name: str
    date: pd.Timestamp
    signal_type: str
    current_price: float

class UniversalScreener:
    """
    通用股票筛选器。
    新职责：在发现信号后，立即调用统一分析服务，
    将该股票的完整分析结果预先计算并存入数据库缓存。
    """
    def __init__(self, stock_pool: Optional[List[str]] = None):
        if stock_pool is None:
            from stock_pool_manager import StockPoolManager
            self.stock_pool = StockPoolManager().get_all_stock_codes()
        else:
            self.stock_pool = stock_pool

    def run_screening(self, strategy_ids: List[str]) -> List[StrategyResult]:
        """
        运行筛选过程。
        """
        all_results = []
        total_stocks = len(self.stock_pool)
        
        print(f"🚀 通用筛选器启动，策略: {', '.join(strategy_ids)}, "
              f"股票池数量: {total_stocks}")

        for i, stock_code in enumerate(self.stock_pool):
            print(f"\r🔍 正在扫描: {stock_code} ({i+1}/{total_stocks})", end="")

            try:
                df = get_full_data_with_indicators(stock_code)
                if df is None or len(df) < 50:
                    continue

                for strategy_id in strategy_ids:
                    strategy_instance = strategy_manager.get_strategy_instance(strategy_id)
                    if not strategy_instance:
                        continue
                        
                    signals = strategy_instance.apply_strategy(df)
                    if isinstance(signals, tuple):
                        signals = signals[0]
                    
                    if signals is not None and not signals.empty:
                        latest_signal_date = signals[signals != ''].index.max()
                        if pd.isna(latest_signal_date):
                            continue

                        # 只处理最近3个交易日内的信号
                        if (df.index.max() - latest_signal_date).days <= 3:
                            
                            # --- 核心修改：预热缓存 ---
                            print(f"\n🔥 发现信号: {stock_code} @ {strategy_id}，正在预热缓存...")
                            get_or_run_analysis(stock_code, strategy_id)
                            # --- 缓存预热结束 ---

                            latest_signal_state = signals[latest_signal_date]
                            result = StrategyResult(
                                stock_code=stock_code,
                                stock_name="", # 名称将由API层填充
                                date=latest_signal_date,
                                signal_type=str(latest_signal_state),
                                current_price=df.loc[latest_signal_date, 'close']
                            )
                            all_results.append(result)
                            
            except Exception as e:
                # print(f"\n⚠️ 扫描 {stock_code} 出错: {e}")
                continue
        
        print(f"\n✅ 筛选完成，共发现 {len(all_results)} 个有效信号。")
        return all_results

```

#### 第2步：改造API，使其优先从缓存读取扫描结果

现在，`UniversalScreener` 会填充我们的数据库。我们需要让前端调用的API `/api/strategies/.../stocks` 变得更“聪明”：它应该**首先检查数据库中今天是否已有扫描结果**，只有在没有的情况下才启动新的扫描。

**修改文件**：`backend/app.py`

**请用以下代码替换 `get_stocks_for_strategy` 函数。**

```python
# backend/app.py

@app.route('/api/strategies/<strategy_id>/stocks')
def get_stocks_for_strategy(strategy_id):
    """
    【最终优化版】获取策略的信号股票列表。
    优先从数据库缓存读取今日分析结果，若无则触发一次扫描与分析。
    """
    try:
        from analysis_cache import analysis_cache
        from stock_pool_manager import StockPoolManager
        
        # 1. 优先从缓存中获取今天已分析过的该策略的股票
        cached_stocks = analysis_cache.get_todays_analysis_by_strategy(strategy_id)
        
        if cached_stocks:
            print(f"⚡️ API缓存命中: 直接从数据库返回策略 '{strategy_id}' 的 {len(cached_stocks)} 个结果。")
            
            # 从缓存数据构建列表
            stock_list = []
            for stock in cached_stocks:
                # 'deep_analysis' 包含了我们需要的所有信息
                analysis_data = json.loads(stock['deep_analysis_result'])
                stock_info = analysis_cache.get_stock_info(stock['stock_code'])
                
                stock_list.append({
                    'stock_code': stock['stock_code'],
                    'stock_name': stock_info.get('stock_name', stock['stock_code']) if stock_info else stock['stock_code'],
                    'date': stock['analysis_date'],
                    'signal_type': 'CACHED', # 标记为来自缓存
                    'price': analysis_data.get('current_price', 0)
                })
            
            return jsonify({'success': True, 'data': stock_list})

        # 2. 如果缓存未命中，则启动一次性的扫描与分析预热
        print(f"⏳ API缓存未命中: 为策略 '{strategy_id}' 启动后台扫描与分析...")
        from universal_screener import UniversalScreener
        
        screener = UniversalScreener()
        results = screener.run_screening([strategy_id]) # 这一步会自动填充缓存
        
        # 3. 从刚完成的扫描结果中构建列表返回给前端
        pool_manager = StockPoolManager()
        stock_list = []
        for result in results:
            stock_profile = pool_manager.get_stock_by_code(result.stock_code)
            stock_name = stock_profile.get('stock_name', result.stock_code) if stock_profile else result.stock_code
            
            stock_list.append({
                'stock_code': result.stock_code,
                'stock_name': stock_name,
                'date': str(result.date),
                'signal_type': result.signal_type,
                'price': result.current_price
            })
        
        return jsonify({'success': True, 'data': stock_list})
        
    except Exception as e:
        app.logger.error(f"为策略 {strategy_id} 获取股票列表失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": f"无法获取策略 '{strategy_id}' 的股票列表: {str(e)}"}), 500
```

**同时，我们需要为 `analysis_cache.py` 添加上面用到的新函数 `get_todays_analysis_by_strategy`。**

**修改文件**：`backend/analysis_cache.py`
**Action**: 在 `AnalysisCache` 类中添加以下新方法。

```python
# backend/analysis_cache.py (在 AnalysisCache 类中添加)

    def get_todays_analysis_by_strategy(self, strategy_id: str) -> list:
        """
        获取指定策略在今天的所有缓存分析结果
        """
        today_str = date.today().strftime('%Y-%m-%d')
        conn = sqlite3.connect(self.db_path)
        # 让返回结果为字典形式
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT stock_code, analysis_date, deep_analysis_result 
            FROM analysis_results 
            WHERE strategy_id=? AND analysis_date=?
        ''', (strategy_id, today_str))
        
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return results
```

-----

### 总结与收益

完成以上三处修改后，您的系统将实现最终的理想工作流程：

1.  **高效的扫描与分析**：当您在前端第一次选择某个策略时，后端会启动一次 `UniversalScreener`。这个过程会**扫描所有股票，并对每一个符合条件的股票，立刻进行完整的深度分析和回测，然后将这些宝贵的结果全部存入数据库**。
2.  **闪电般的响应**：从第二次开始，当您或任何其他用户当天再次选择该策略时，API将直接从数据库中读取所有已预先计算好的结果，并在瞬间返回给前端。
3.  **即时可用的回测数据**：因为所有分析都在第一次扫描时完成了，所以当股票列表加载出来后，您点击任何一只股票，它的回测数据都已经是“准备就绪”的状态，**“回测表现”面板将会被正确加载**。

这套架构完美地解决了您提出的所有问题，将系统的性能和数据一致性提升到了一个新的高度。