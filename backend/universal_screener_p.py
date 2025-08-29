# backend/universal_screener.py
"""
【V4.2 - 高性能版】通用股票筛选器 (分析预热器)
通过统一和并行化工作流，解决了深度评分带来的性能瓶颈
"""
import json
import pandas as pd
from typing import List, Optional
from dataclasses import dataclass, asdict
from concurrent.futures import ProcessPoolExecutor, as_completed
import logging
from strategy_manager import strategy_manager
from data_handler import get_full_data_with_indicators
from stock_pool_manager import StockPoolManager
# 核心依赖
from confluence_scorer import confluence_scorer

logger = logging.getLogger(__name__)

@dataclass
class HighQualityResult:
    """【V4.2】高质量筛选结果的数据结构"""
    stock_code: str
    stock_name: str
    date: pd.Timestamp
    signal_type: str
    current_price: float
    # 丰富评分信息
    confluence_score: float
    confidence: float
    market_phase: str
    quality_grade: str

def _unified_screening_worker(args_tuple: tuple) -> Optional[HighQualityResult]:
    """
    【V4.2 核心工作函数 - 统一并行化】
    对单只股票完成从“基础信号发现”到“V4深度评分”的完整流程。
    """
    stock_info, strategy_ids, db_path = args_tuple
    stock_code = stock_info.get('stock_code')
    if not stock_code:
        return None

    try:
        # --- 步骤 1: 加载数据 (仅一次) ---
        pool_manager = StockPoolManager(db_path)
        profile = pool_manager.get_stock_by_code(stock_code)
        stock_name = stock_info.get('stock_name', '')
        if profile:
            stock_name = profile.get('stock_name', stock_name)

        df = get_full_data_with_indicators(stock_code)
        if df is None or len(df) < 50:
            return None

        # --- 步骤 2: 基础策略信号发现 ---
        latest_signal_date = None
        latest_signal_type = None
        
        for strategy_id in strategy_ids:
            strategy_instance = strategy_manager.get_strategy_instance(strategy_id)
            if not strategy_instance: continue

            result = strategy_instance.apply_strategy(df)
            signals = result[0] if isinstance(result, tuple) else result
            
            if signals is None or signals.empty: continue
            
            actual_signals = signals.loc[signals.apply(lambda x: isinstance(x, str) and x != '')]
            if not actual_signals.empty:
                current_signal_date = actual_signals.index.max()
                if pd.notna(current_signal_date) and (df.index.max() - current_signal_date).days <= 3:
                    if latest_signal_date is None or current_signal_date > latest_signal_date:
                        latest_signal_date = current_signal_date
                        latest_signal_type = str(actual_signals.loc[latest_signal_date])
        
        # 如果没有发现近期信号，则提前退出，节省计算资源
        if latest_signal_date is None:
            return None

        # --- 步骤 3: V4.1 深度评分 (仅对有信号的股票) ---
        latest_index = df.index.get_loc(latest_signal_date)
        confluence_result = confluence_scorer.calculate_confluence_score(df, latest_index)

        total_score = confluence_result.get('total_score', 0)
        confidence = confluence_result.get('confidence', 0)
        
        # --- 步骤 4: 过滤低质量信号 ---
        if total_score < 70 or confidence < 0.6:
            return None

        # --- 步骤 5: 构建并返回高质量结果 ---
        grade = 'A' if total_score >= 85 else 'B'
        
        return HighQualityResult(
            stock_code=stock_code,
            stock_name=stock_name,
            date=latest_signal_date,
            signal_type=latest_signal_type,
            current_price=df.loc[latest_signal_date, 'close'],
            confluence_score=total_score,
            confidence=confidence,
            market_phase=confluence_result.get('market_phase', 'unknown'),
            quality_grade=grade
        )
            
    except Exception as e:
        logger.error(f"处理 {stock_code} 时发生错误: {e}")
        return None

class UniversalScreener:
    """
    【V4.2 - 高性能版】通用股票筛选器
    采用统一的并行化工作流，高效执行深度筛选。
    """
    def __init__(self, stock_pool: Optional[List[dict]] = None):
        self.pool_manager = StockPoolManager()
        self.stock_pool = stock_pool or self.pool_manager.get_all_stocks()

    def run_screening(self, strategy_ids: List[str], max_workers: Optional[int] = None) -> List[HighQualityResult]:
        """
        【V4.2 核心流程】运行统一的、完全并行化的股票筛选。
        """
        high_quality_results = []
        total_stocks = len(self.stock_pool)
        
        if not self.stock_pool:
            logger.warning("股票池为空，筛选任务退出。")
            return high_quality_results

        logger.info(f"🚀 V4.2 高性能筛选器启动，策略: {', '.join(strategy_ids)}, "
                    f"股票池数量: {total_stocks}, 最大工作进程数: {max_workers or '自动'}")
        
        tasks = [(stock_info, strategy_ids, self.pool_manager.db_path) for stock_info in self.stock_pool]

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_unified_screening_worker, task): task[0]['stock_code'] for task in tasks}
            
            for i, future in enumerate(as_completed(futures), 1):
                stock_code = futures[future]
                print(f"\r🔍 深度筛选进度 [{i}/{total_stocks}]: {stock_code}", end="", flush=True)
                
                try:
                    # worker返回高质量结果或None
                    worker_result = future.result()
                    if worker_result:
                        high_quality_results.append(worker_result)
                except Exception as e:
                    logger.error(f"处理 {stock_code} 时主进程捕获异常: {e}")

        print(f"\n✅ 筛选完成，共发现 {len(high_quality_results)} 个高质量信号。")

        # 按评分排序
        high_quality_results.sort(key=lambda x: x.confluence_score, reverse=True)
        
        # 打印并更新缓存
        if high_quality_results:
            print("📊 前5名股票评分:")
            for i, result in enumerate(high_quality_results[:5], 1):
                print(f"  {i}. {result.stock_code} ({result.stock_name}): "
                      f"{result.confluence_score:.1f}分 ({result.quality_grade}级), "
                      f"置信度{result.confidence:.1%}, {result.market_phase}阶段")
            
            self._update_strategy_screening_cache(strategy_ids, high_quality_results)
        
        return high_quality_results

    def _update_strategy_screening_cache(self, strategy_ids: List[str], results: List[HighQualityResult]):
        """更新策略筛选缓存"""
        try:
            from strategy_screening_cache import strategy_screening_cache
            
            # 直接使用dataclass转换为dict
            stock_list = [asdict(result) for result in results]
            
            # 为所有相关策略更新缓存
            for strategy_id in strategy_ids:
                strategy_screening_cache.save_screening_results(strategy_id, stock_list)
            
            logger.info(f"📋 {len(strategy_ids)}个策略的筛选结果已更新到缓存 ({len(stock_list)}只股票)")

        except Exception as e:
            logger.error(f"更新策略筛选缓存失败: {e}")