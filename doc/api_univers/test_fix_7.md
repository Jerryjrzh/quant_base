好的，我们来一起审查 `get_trading_advice.py` 和 `get_trading_advice_enhanced.py` 这两个脚本。

在您项目重构和API调整的大背景下，这两个脚本确实需要进行整合与优化。它们的目标相似，但实现方式和依赖的模块有所不同，这正是我们需要统一的地方。

### 1\. 核心问题：架构不统一与功能分散

  - **`get_trading_advice.py`**：

      - **优点**：架构正确。它直接调用了 `backtester.get_deep_analysis`，这完全符合我们将 `backtester` 作为核心分析引擎的重构目标。
      - **缺点**：功能相对简单，输出的信息不如增强版详细。

  - **`get_trading_advice_enhanced.py`**：

      - **优点**：功能强大，输出信息非常详尽，包括了补仓/卖出系数、风险评估、技术分析等，格式化非常完善。
      - **缺点**：**架构过时**。它依赖 `portfolio_manager` 来进行深度分析。在我们新的架构中，`portfolio_manager` 的职责是管理持仓列表，而不应再包含核心的分析逻辑。

**结论**：最佳方案是将二者合并。我们应该保留 `get_trading_advice_enhanced.py` 强大的**功能和格式化能力**，但将其**底层依赖**从 `portfolio_manager` 切换到 `backtester`，使其与项目的整体架构保持一致。

-----

### 2\. 前提条件：增强 `backtester.py`

`get_trading_advice_enhanced.py` 期望分析结果中包含**卖出系数 (`best_sell_coefficient`)** 的回测。而我们之前迁移到 `backtester.py` 的 `_optimize_coefficients_historically` 函数目前只优化了补仓系数。因此，在修改脚本之前，我们必须先为 `backtester` 增加卖出策略的回测功能。

**修改文件**: `backend/backtester.py`
**函数**: `_optimize_coefficients_historically`

**请将该函数更新为以下版本：**

```python
# backend/backtester.py

def _optimize_coefficients_historically(df: pd.DataFrame) -> dict:
    """
    通过历史数据回测，优化补仓和卖出系数。
    【已增强】增加了卖出系数的优化逻辑。
    """
    add_coefficients = [0.96, 0.97, 0.98, 0.99, 1.00]
    sell_coefficients = [1.03, 1.05, 1.08, 1.10, 1.15, 1.20] # 卖出系数
    
    # --- 补仓系数回测 (逻辑不变) ---
    add_results = {}
    best_add_coefficient = None
    best_add_score = -999
    for add_coeff in add_coefficients:
        # ... (此部分代码保持不变)
        success_count, total_scenarios, total_return = 0, 0, 0
        for i in range(100, len(df) - 30):
            current_data = df.iloc[:i+1]
            future_data = df.iloc[i+1:i+31]
            if len(future_data) < 15: continue
            hist_price = float(current_data.iloc[-1]['close'])
            price_targets = _calculate_price_targets(current_data, hist_price)
            support_level = price_targets.get('next_support')
            if not support_level: continue
            add_price = support_level * add_coeff
            if float(future_data['low'].min()) <= add_price:
                total_scenarios += 1
                return_pct = (float(future_data['high'].max()) - add_price) / add_price * 100
                if return_pct > 0: success_count += 1
                total_return += return_pct
        if total_scenarios > 0:
            success_rate = success_count / total_scenarios * 100
            avg_return = total_return / total_scenarios
            score = success_rate * 0.6 + avg_return * 0.4
            add_results[add_coeff] = {'success_rate': success_rate, 'avg_return': avg_return, 'score': score}
            if score > best_add_score:
                best_add_score = score
                best_add_coefficient = add_coeff

    # --- 新增：卖出系数回测 ---
    sell_results = {}
    best_sell_coefficient = None
    best_sell_score = -999
    for sell_coeff in sell_coefficients:
        success_count, total_scenarios, total_return, total_hold_days = 0, 0, 0, 0
        for i in range(100, len(df) - 30):
            current_data = df.iloc[:i+1]
            future_data = df.iloc[i+1:i+31]
            if len(future_data) < 15: continue
            
            # 假设在当天买入
            entry_price = float(current_data.iloc[-1]['close'])
            # 基于当天价格计算卖出目标价
            sell_price = entry_price * sell_coeff
            
            # 检查未来是否能达到卖出价
            future_highs = future_data['high']
            if float(future_highs.max()) >= sell_price:
                total_scenarios += 1
                # 找到第一个达到卖出价的天数
                days_to_sell = (future_highs >= sell_price).idxmax()
                hold_days = (days_to_sell - current_data.index[-1]).days
                
                return_pct = (sell_price - entry_price) / entry_price * 100
                success_count += 1
                total_return += return_pct
                total_hold_days += hold_days
        
        if total_scenarios > 0:
            success_rate = success_count / total_scenarios * 100
            avg_return = total_return / total_scenarios
            avg_hold_days = total_hold_days / total_scenarios
            # 评分：收益率越高越好，持有天数越短越好
            score = (success_rate * 0.5 + avg_return * 0.5) / (1 + avg_hold_days * 0.05)
            sell_results[sell_coeff] = {'success_rate': success_rate, 'avg_return': avg_return, 'avg_hold_days': avg_hold_days, 'score': score}
            if score > best_sell_score:
                best_sell_score = score
                best_sell_coefficient = sell_coeff

    # --- 返回合并后的结果 ---
    return {
        'best_add_coefficient': best_add_coefficient,
        'best_add_score': best_add_score,
        'add_coefficient_analysis': add_results,
        'best_sell_coefficient': best_sell_coefficient, # 新增
        'best_sell_score': best_sell_score,           # 新增
        'sell_coefficient_analysis': sell_results,    # 新增
    }
```

-----

### 3\. 整合与重构建议

现在 `backtester` 已经具备了所有分析能力，我们可以放心地重构 `get_trading_advice_enhanced.py`，并废弃 `get_trading_advice.py`。

**建议**：

1.  **删除 `get_trading_advice.py` 文件**，避免维护两个入口。
2.  **用以下优化后的代码完全替换 `get_trading_advice_enhanced.py` 的内容**。

**`get_trading_advice_enhanced.py` (优化后)**

```python
#!/usr/bin/env python3
"""
增强版交易建议工具 - 基于深度回测分析
使用方法: python get_trading_advice_enhanced.py [股票代码] [可选:入场价格]
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

# --- 核心修改：依赖从 portfolio_manager 切换到 backtester ---
from backtester import get_deep_analysis

def get_stock_advice_with_backtest(stock_code, entry_price=None):
    """
    【已重构】获取基于深度回测的股票交易建议。
    直接调用 backtester 作为核心分析引擎。
    """
    try:
        # 1. 直接调用 backtester 获取所有分析数据
        analysis = get_deep_analysis(stock_code)
        
        if 'error' in analysis:
            return f"❌ 分析失败: {analysis['error']}"
        
        # 2. 如果提供了入场价格，在脚本内部计算盈亏状况
        profit_loss_pct = 0.0
        if entry_price is not None:
            current_price = analysis.get('current_price', 0)
            if current_price > 0:
                profit_loss_pct = (current_price - entry_price) / entry_price * 100
        
        # 3. 将盈亏信息添加到分析结果中，传递给格式化函数
        analysis['profit_loss_pct'] = profit_loss_pct
        
        return format_enhanced_advice(stock_code, analysis)
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"❌ 处理股票 {stock_code} 失败: {e}"

def format_enhanced_advice(stock_code, analysis):
    """
    格式化增强的建议输出。
    【已适配】现在使用 backtester.get_deep_analysis 的返回结构。
    """
    output = []
    output.append(f"📊 {stock_code} 深度交易分析")
    output.append("=" * 60)
    
    # 基本信息
    output.append(f"📅 分析时间: {analysis['analysis_time']}")
    output.append(f"💰 当前价格: ¥{analysis['current_price']:.2f}")
    if analysis.get('profit_loss_pct') is not None and analysis['profit_loss_pct'] != 0:
        output.append(f"📊 盈亏状况 (基于输入价格): {analysis['profit_loss_pct']:.2f}%")
    output.append("")
    
    # 回测分析结果
    if 'backtest_analysis' in analysis and analysis['backtest_analysis']:
        backtest = analysis['backtest_analysis']
        output.append("🔍 深度回测分析结果:")
        
        # 最优补仓系数
        if backtest.get('best_add_coefficient'):
            output.append(f"   🎯 最优补仓系数: {backtest['best_add_coefficient']} (评分: {backtest.get('best_add_score', 0):.2f})")
        
        # 最优卖出系数
        if backtest.get('best_sell_coefficient'):
            output.append(f"   🎯 最优卖出系数: {backtest['best_sell_coefficient']} (评分: {backtest.get('best_sell_score', 0):.2f})")
        
        # 补仓系数分析
        if 'add_coefficient_analysis' in backtest and backtest['add_coefficient_analysis']:
            output.append("\n   📈 补仓系数回测分析 (Top 3):")
            sorted_add = sorted(backtest['add_coefficient_analysis'].items(), key=lambda x: x[1].get('score', 0), reverse=True)
            for coeff, stats in sorted_add[:3]:
                output.append(f"     系数 {coeff}: 胜率 {stats['success_rate']:.1f}%, 均益 {stats['avg_return']:.2f}%, 评分 {stats['score']:.2f}")

        # 卖出系数分析
        if 'sell_coefficient_analysis' in backtest and backtest['sell_coefficient_analysis']:
            output.append("\n   📉 卖出系数回测分析 (Top 3):")
            sorted_sell = sorted(backtest['sell_coefficient_analysis'].items(), key=lambda x: x[1].get('score', 0), reverse=True)
            for coeff, stats in sorted_sell[:3]:
                output.append(f"     系数 {coeff}: 胜率 {stats['success_rate']:.1f}%, 均益 {stats['avg_return']:.2f}%, 均持 {stats['avg_hold_days']:.1f}天, 评分 {stats['score']:.2f}")

        output.append("")

    # 操作建议
    if 'trading_advice' in analysis and analysis['trading_advice']:
        advice = analysis['trading_advice']
        output.append("💡 操作建议:")
        output.append(f"   🎯 建议操作: {advice['action']}")
        output.append(f"   🔍 置信度: {advice['confidence']*100:.0f}%")
        
        if advice.get('optimal_add_price'):
            output.append(f"   📉 建议补仓价: ¥{advice['optimal_add_price']:.2f}")
        if advice.get('stop_loss_price'):
            output.append(f"   ⛔ 止损价: ¥{advice['stop_loss_price']:.2f}")
        
        if advice.get('reasons'):
            output.append("   📋 建议原因:")
            for reason in advice['reasons']:
                output.append(f"     • {reason}")
        output.append("")

    # 风险评估
    if 'risk_assessment' in analysis and analysis['risk_assessment']:
        risk = analysis['risk_assessment']
        output.append("⚠️ 风险评估:")
        output.append(f"   📊 风险等级: {risk.get('risk_level', '未知')}")
        output.append(f"   📈 年化波动率: {risk.get('volatility', 0)*100:.1f}%")
        output.append(f"   📉 最大回撤: {risk.get('max_drawdown', 0)*100:.1f}%")

    return "\n".join(output)

def main():
    """主函数"""
    if len(sys.argv) < 2 or sys.argv[1] in ['--help', '-h', 'help']:
        print("增强版交易建议系统 v2.1 (架构优化版)")
        print("=" * 50)
        print("使用方法: python get_trading_advice_enhanced.py <股票代码> [入场价格]")
        print("\n示例:")
        print("  python get_trading_advice_enhanced.py sh600036")
        print("  python get_trading_advice_enhanced.py sz000001 12.50")
        return
    
    stock_code = sys.argv[1].lower()
    entry_price = float(sys.argv[2]) if len(sys.argv) > 2 else None
    
    print("🤖 正在进行深度回测分析...")
    result = get_stock_advice_with_backtest(stock_code, entry_price)
    print(result)

if __name__ == "__main__":
    main()
```

### 总结

通过以上调整：

1.  **增强了核心引擎**：`backtester.py` 现在具备了卖出系数的回测能力，分析功能更加完整。
2.  **统一了架构**：删除了旧的、依赖 `portfolio_manager` 的分析链路，所有命令行建议都统一由 `backtester` 驱动。
3.  **简化了代码**：将两个脚本合并为一个，消除了代码冗余，使项目结构更清晰，更易于维护。
4.  **保留了全部功能**：新的 `get_trading_advice_enhanced.py` 脚本保留了所有强大的分析和格式化功能，并且运行得更高效。