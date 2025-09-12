您好，我分析了您遇到的前端异常以及相关的后端代码和日志。这是一个在后端发生的`KeyError`，导致服务器返回了 `500 Internal Server Error`，从而使前端请求失败。

### 1\. 问题诊断 🕵️

  - **错误类型**: `KeyError: 'risk_assessment'`
  - **发生位置**: `portfolio_manager.py` 文件的 `scan_all_positions` 函数中。
  - **错误代码**: `if analysis['risk_assessment']['risk_level'] == 'HIGH':`
  - **根本原因**: 程序试图访问字典 `analysis` 中的 `'risk_assessment'` 键，但该键不存在，从而引发了 `KeyError`。变量 `analysis` 是由 `analyze_position_deep` 函数返回的。通过追溯代码，`analyze_position_deep` 函数在组装返回的 `analysis` 字典时，并没有包含 `'risk_assessment'` 这个字段。这很可能是在近期代码重构中，风险评估的逻辑被遗漏或尚未从 `backtester.py` 中正确返回导致的。

-----

### 2\. 解决方案 🛠️

为了解决这个问题，我为您提供一个\*\*“双保险”**方案：一个立即修复程序崩溃的**防御性修改\*\*，和一个彻底解决问题的**根本性修复**。

#### A. 立即修复：增加防御性代码（推荐首先应用）

这可以防止程序因缺少某个键而崩溃，让代码更健壮。

**修改文件**: `backend/portfolio_manager.py`
**函数**: `scan_all_positions`

**修改前**:

```python
                if analysis['risk_assessment']['risk_level'] == 'HIGH':
                    results['summary']['high_risk_count'] += 1
                
                if analysis['position_advice']['action'] in ['REDUCE', 'STOP_LOSS', 'ADD']:
                    results['summary']['action_required_count'] += 1
```

**修改后 (使用 `.get()` 方法安全访问)**:

```python
                # 使用 .get() 安全地访问 risk_assessment，如果不存在则返回一个空字典
                risk_assessment = analysis.get('risk_assessment', {})
                if risk_assessment.get('risk_level') == 'HIGH':
                    results['summary']['high_risk_count'] += 1
                
                # 同样地，安全访问 position_advice
                position_advice = analysis.get('position_advice', {})
                if position_advice.get('action') in ['REDUCE', 'STOP_LOSS', 'ADD']:
                    results['summary']['action_required_count'] += 1
```

**效果**：即使 `analysis` 字典中没有 `'risk_assessment'` 或 `'position_advice'`，程序也不会报错，而是会安全地跳过判断，保证扫描流程能够顺利完成。

-----

#### B. 根本性修复：在 `backtester` 中补全风险评估逻辑

为了让风险等级功能恢复正常，我们需要在 `backtester.py` 的深度分析流程中加入风险评估的计算。幸运的是，您的 `enhanced_analyzer.py` 文件中已经有了一个非常好的 `_assess_risk_profile` 实现，我们可以将其迁移过来。

**第一步：将风险评估逻辑添加到 `backtester.py`**

**修改文件**: `backend/backtester.py`

```python
# backtester.py

# ... (在文件顶部或其他合适位置，添加 _calculate_max_drawdown 辅助函数)
def _calculate_max_drawdown(prices: pd.Series) -> float:
    """计算最大回撤"""
    try:
        peak = prices.expanding(min_periods=1).max()
        drawdown = (prices - peak) / peak
        return float(drawdown.min())
    except Exception:
        return 0.0

def _assess_risk_profile(df: pd.DataFrame) -> Dict:
    """
    评估风险概况 (逻辑源自 enhanced_analyzer.py)
    """
    try:
        returns = df['close'].pct_change().dropna()
        volatility = returns.std() * np.sqrt(252) # 年化波动率
        max_drawdown = _calculate_max_drawdown(df['close'])
        
        # 价格位置（当前价格在最近一年高低点中的位置）
        recent_year = df.tail(252)
        price_position_pct = 0
        if not recent_year.empty:
            min_price = recent_year['low'].min()
            max_price = recent_year['high'].max()
            current_price = df['close'].iloc[-1]
            if (max_price - min_price) > 0:
                price_position_pct = (current_price - min_price) / (max_price - min_price)

        # 综合风险评分 (0-1, 越高风险越大)
        volatility_risk = min(volatility / 0.8, 1.0)    # 波动率风险 (标准化)
        drawdown_risk = min(abs(max_drawdown) / 0.5, 1.0) # 回撤风险 (标准化)
        position_risk = price_position_pct * 0.5       # 价格位置风险
        
        overall_risk = (volatility_risk * 0.4 + drawdown_risk * 0.4 + position_risk * 0.2)
        
        risk_level = 'LOW' if overall_risk < 0.35 else 'MEDIUM' if overall_risk < 0.65 else 'HIGH'
        
        return {
            'volatility': float(volatility),
            'max_drawdown': float(max_drawdown),
            'price_position_pct': float(price_position_pct),
            'overall_risk_score': float(overall_risk),
            'risk_level': risk_level
        }
    except Exception as e:
        return {'error': f'风险评估失败: {str(e)}', 'risk_level': 'UNKNOWN'}

# ... (保留其他函数)

# 第二步：在 get_deep_analysis 中调用风险评估函数

def get_deep_analysis(stock_code: str, df: pd.DataFrame = None) -> dict:
    """
    【统一入口函数】
    对单只股票进行深度回测分析，并生成前瞻性交易建议。
    """
    try:
        # ... (保留数据获取逻辑)

        # 【新增】执行风险评估
        risk_assessment = _assess_risk_profile(df)

        # ... (保留优化系数和生成建议的逻辑)
        backtest_results = _optimize_coefficients_historically(df)
        forward_advice = _generate_forward_advice(df, backtest_results)

        # 【修改】在返回结果中加入风险评估
        analysis_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        return {
            'stock_code': stock_code,
            'analysis_time': analysis_time,
            'current_price': float(df.iloc[-1]['close']),
            'backtest_analysis': backtest_results,
            'trading_advice': forward_advice,
            'risk_assessment': risk_assessment, # <-- 新增此字段
            'from_cache': False
        }
    except Exception as e:
        # ... (保留异常处理)
```

**第三步：在 `portfolio_manager.py` 中确保传递风险评估数据**

**修改文件**: `backend/portfolio_manager.py`
**函数**: `analyze_position_deep`

这个函数现在需要将从 `backtester` 获取到的 `risk_assessment` 添加到返回结果中。

```python
# portfolio_manager.py -> analyze_position_deep

    def analyze_position_deep(self, stock_code: str, purchase_price: float, 
                            purchase_date: str) -> Dict:
        # ... (try块和数据加载逻辑不变)
            
            backtest_analysis_full = self._get_or_generate_backtest_analysis(stock_code, df)
            
            # ... (计算盈亏逻辑不变)

            analysis = {
                # ... (保留原有字段)
                'backtest_analysis': backtest_analysis_full.get('backtest_analysis'),
                'position_advice': backtest_analysis_full.get('trading_advice'),
                'risk_assessment': backtest_analysis_full.get('risk_assessment'), # <-- 新增此行
                
                # ... (保留其他字段)
            }
            
            return analysis
        # ... (except块不变)
```

### 总结

1.  **立即修复**：请先应用 **A方案** 中的防御性修改，这将立刻解决程序崩溃的问题。
2.  **根本修复**：再应用 **B方案** 中的三步修改，这将使风险评估功能恢复，并在您的持仓扫描界面正确显示风险等级。

请使用方案B修复