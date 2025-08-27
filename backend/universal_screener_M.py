# backend/universal_screener.py

"""
【最终优化版】通用股票筛选器 (已升级为分析预热器)
"""
import pandas as pd
from typing import List, Optional
from dataclasses import dataclass

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
            print(f"\r🔍 正在扫描: {stock_code} ({i+1}/{total_stocks})", end="", flush=True)

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
                        # 查找最新的非空信号
                        valid_signals = signals[signals != '']
                        if valid_signals.empty:
                            continue
                        
                        latest_signal_date = valid_signals.index.max()
                        if pd.isna(latest_signal_date):
                            continue

                        # 只处理最近3个交易日内的信号
                        if (df.index.max() - latest_signal_date).days <= 3:
                            
                            # --- 核心修改：预热缓存 ---
                            print(f"\n🔥 发现信号: {stock_code} @ {strategy_id}，正在预热缓存...", flush=True)
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
                            
            except Exception:
                # 在大规模扫描时，忽略单个股票的错误，继续执行
                continue
        
        print(f"\n✅ 筛选完成，共发现 {len(all_results)} 个有效信号并已预热缓存。")
        return all_results

# --- [FIX START] 新增独立执行入口 ---
if __name__ == "__main__":
    import sys

    # 检查是否提供了策略ID作为命令行参数
    if len(sys.argv) < 2:
        print("=" * 60)
        print("通用股票筛选器与缓存预热工具")
        print("功能: 扫描整个股票池，为符合指定策略的股票预热数据库缓存。")
        print("=" * 60)
        print("使用方法: python backend/universal_screener.py <strategy_id_1> [strategy_id_2] ...")
        print("\n示例:")
        print("  python backend/universal_screener.py MACD零轴启动_v1.0")
        print("  python backend/universal_screener.py abyss_bottoming_v2.0 周线金叉+日线ma_v1.0")
        sys.exit(1)

    # 从命令行参数获取要运行的策略ID
    strategy_ids_to_run = sys.argv[1:]

    # 创建筛选器实例并运行
    screener = UniversalScreener()
    found_signals = screener.run_screening(strategy_ids_to_run)

    # 打印最终总结
    print("\n" + "=" * 60)
    if found_signals:
        print(f"✅ 独立扫描执行完毕。共为 {len(found_signals)} 个信号预热了缓存:")
        for signal in found_signals:
            print(f"  - {signal.stock_code} (日期: {signal.date.strftime('%Y-%m-%d')})")
    else:
        print("✅ 独立扫描执行完毕，未发现符合条件的信号。")
    print("=" * 60)
# --- [FIX END] ---