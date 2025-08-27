#!/usr/bin/env python3
"""
增强版股票筛选器
基于screener_tester文档的分析，集成多指标融合评分系统
实现从"信号猎取"到"形态识别"的升级
"""

import json
import pandas as pd
from typing import List, Optional
from dataclasses import dataclass, asdict
from concurrent.futures import ProcessPoolExecutor, as_completed
import logging
from strategy_manager import strategy_manager
from data_handler import get_full_data_with_indicators
from unified_analysis_service import get_or_run_analysis
from stock_pool_manager import StockPoolManager
from confluence_scorer import confluence_scorer
from pattern_recognizer import pattern_recognizer

logger = logging.getLogger(__name__)

@dataclass
class EnhancedStrategyResult:
    """增强版策略结果，包含质量评估信息"""
    stock_code: str
    stock_name: str
    date: pd.Timestamp
    signal_type: str
    current_price: float
    # 新增质量评估字段
    confluence_score: float = 0
    confidence: float = 0
    quality_grade: str = 'C'
    pattern_detected: bool = False
    pattern_type: Optional[str] = None
    price_position_pct: float = 0
    risk_level: str = 'UNKNOWN'

def _enhanced_screening_worker(args_tuple: tuple) -> List[EnhancedStrategyResult]:
    """
    增强版多进程工作函数
    集成多指标融合评分和形态识别
    """
    stock_info, strategy_ids, db_path = args_tuple
    
    pool_manager = StockPoolManager(db_path)
    
    stock_code = stock_info.get('stock_code')
    if not stock_code:
        return []

    worker_results = []
    
    try:
        # 获取股票基本信息和优化参数
        profile = pool_manager.get_stock_by_code(stock_code)
        optimized_params = {}
        stock_name = stock_info.get('stock_name', '')
        if profile:
            stock_name = profile.get('stock_name', stock_name)
            params_json = profile.get('optimized_params')
            if isinstance(params_json, dict):
                optimized_params = params_json
            elif isinstance(params_json, str):
                try:
                    optimized_params = json.loads(params_json)
                except json.JSONDecodeError:
                    pass

        # 获取完整技术指标数据
        df = get_full_data_with_indicators(stock_code, **optimized_params)
        if df is None or len(df) < 50:
            return []

        # 遍历策略
        for strategy_id in strategy_ids:
            strategy_instance = strategy_manager.get_strategy_instance(strategy_id)
            if not strategy_instance:
                continue
            
            # 执行策略
            result = strategy_instance.apply_strategy(df)
            
            # 处理策略返回结果
            if isinstance(result, tuple):
                signals, confidence_scores = result
            else:
                signals = result
                confidence_scores = None
            
            if signals is None or signals.empty:
                continue

            # 筛选有效信号
            actual_signals = signals.loc[signals.apply(lambda x: isinstance(x, str) and x != '')]

            if not actual_signals.empty:
                latest_signal_date = actual_signals.index.max()
                
                # 时效性检查（扩展到5天）
                time_window_days = 5
                is_recent = pd.notna(latest_signal_date) and (df.index.max() - latest_signal_date).days <= time_window_days
                
                if not is_recent:
                    continue
                
                # 获取信号对应的数据索引
                try:
                    signal_index = df.index.get_loc(latest_signal_date)
                except KeyError:
                    continue
                
                # === 核心质量评估流程 ===
                
                # 1. 价格位置快速过滤
                price_filter_passed, price_reason = confluence_scorer.filter_by_price_position(df, signal_index)
                if not price_filter_passed:
                    logger.debug(f"{stock_code} 被价格过滤器排除: {price_reason}")
                    continue
                
                # 2. 多指标融合评分
                confluence_result = confluence_scorer.calculate_confluence_score(df, signal_index)
                
                # 3. 形态识别
                pattern_result = pattern_recognizer.recognize_pattern(df, signal_index)
                
                # 4. 综合质量判断
                min_confluence_score = 70  # 最低融合评分
                min_confidence = 0.7       # 最低置信度
                
                # 检查融合评分
                if confluence_result['total_score'] < min_confluence_score:
                    logger.debug(f"{stock_code} 融合评分不足: {confluence_result['total_score']}")
                    continue
                
                # 检查策略置信度（如果提供）
                strategy_confidence = 1.0  # 默认置信度
                if confidence_scores is not None:
                    strategy_confidence = confidence_scores.get(latest_signal_date, 0)
                    if strategy_confidence < min_confidence:
                        logger.debug(f"{stock_code} 策略置信度不足: {strategy_confidence}")
                        continue
                
                # 5. 检查价格有效性
                current_price = df.loc[latest_signal_date, 'close']
                if not (pd.notna(current_price) and current_price > 0):
                    continue
                
                # 6. 计算价格位置百分比
                window_size = min(90, len(df))
                end_pos = signal_index + 1
                start_pos = max(0, end_pos - window_size)
                window_data = df.iloc[start_pos:end_pos]
                
                min_price = window_data['low'].min()
                max_price = window_data['high'].max()
                price_position_pct = 0
                if max_price > min_price:
                    price_position_pct = (current_price - min_price) / (max_price - min_price)
                
                # 7. 评估风险等级
                risk_level = 'LOW'
                if price_position_pct > 0.7:
                    risk_level = 'HIGH'
                elif price_position_pct > 0.4:
                    risk_level = 'MEDIUM'
                
                # 8. 确定质量等级
                quality_grade = 'C'
                if confluence_result['total_score'] >= 85:
                    quality_grade = 'A'
                elif confluence_result['total_score'] >= 70:
                    quality_grade = 'B'
                
                # 9. 创建增强版结果
                enhanced_result = EnhancedStrategyResult(
                    stock_code=stock_code,
                    stock_name=stock_name,
                    date=latest_signal_date,
                    signal_type=str(actual_signals.loc[latest_signal_date]),
                    current_price=current_price,
                    confluence_score=confluence_result['total_score'],
                    confidence=confluence_result['confidence'],
                    quality_grade=quality_grade,
                    pattern_detected=pattern_result.get('has_pattern', False),
                    pattern_type=pattern_result.get('best_pattern', None),
                    price_position_pct=price_position_pct,
                    risk_level=risk_level
                )
                
                worker_results.append(enhanced_result)
                
                # 10. 记录高质量信号的详细信息
                if quality_grade == 'A':
                    logger.info(f"发现A级信号: {stock_code} {stock_name}, "
                              f"融合评分: {confluence_result['total_score']:.1f}, "
                              f"形态: {pattern_result.get('best_pattern', 'None')}")
            
    except Exception as e:
        logger.error(f"处理 {stock_code} 时发生错误: {e}")
        return []
    
    return worker_results

class EnhancedScreener:
    """
    增强版股票筛选器
    集成多指标融合评分系统和形态识别
    """
    
    def __init__(self, stock_pool: Optional[List[dict]] = None):
        self.pool_manager = StockPoolManager()
        if stock_pool is None:
            self.stock_pool = self.pool_manager.get_all_stocks()
        else:
            self.stock_pool = stock_pool
    
    def run_enhanced_screening(self, strategy_ids: List[str], 
                             max_workers: Optional[int] = 31,
                             min_quality_grade: str = 'B') -> List[EnhancedStrategyResult]:
        """
        运行增强版多进程股票筛选
        
        Args:
            strategy_ids: 待运行的策略ID列表
            max_workers: 最大工作进程数
            min_quality_grade: 最低质量等级 ('A', 'B', 'C')
        
        Returns:
            筛选结果列表，按质量等级排序
        """
        all_results = []
        total_stocks = len(self.stock_pool)
        
        if not self.stock_pool:
            logger.warning("股票池为空，筛选任务退出。")
            return all_results

        logger.info(f"🚀 增强版筛选器启动，策略: {', '.join(strategy_ids)}, "
                   f"股票池数量: {total_stocks}, 最大工作进程数: {max_workers or '自动'}")
        
        tasks = [(stock_info, strategy_ids, self.pool_manager.db_path) for stock_info in self.stock_pool]

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_enhanced_screening_worker, task): task[0]['stock_code'] for task in tasks}
            
            for i, future in enumerate(as_completed(futures), 1):
                stock_code = futures[future]
                print(f"\r🔍 处理进度 [{i}/{total_stocks}]: {stock_code}", end="", flush=True)
                
                try:
                    worker_results = future.result()
                    all_results.extend(worker_results)
                except Exception as e:
                    logger.error(f"处理 {stock_code} 时主进程捕获异常: {e}")
                    continue
        
        print(f"\n✅ 筛选完成，共发现 {len(all_results)} 个信号。")
        
        # 按质量等级过滤
        quality_order = {'A': 3, 'B': 2, 'C': 1}
        min_quality_value = quality_order.get(min_quality_grade, 1)
        
        filtered_results = [
            result for result in all_results 
            if quality_order.get(result.quality_grade, 0) >= min_quality_value
        ]
        
        # 按质量等级和融合评分排序
        filtered_results.sort(key=lambda x: (quality_order.get(x.quality_grade, 0), x.confluence_score), reverse=True)
        
        # 统计信息
        grade_stats = {}
        for result in filtered_results:
            grade = result.quality_grade
            if grade not in grade_stats:
                grade_stats[grade] = 0
            grade_stats[grade] += 1
        
        logger.info(f"📊 质量统计: {grade_stats}")
        
        # 更新策略筛选缓存
        self._update_strategy_screening_cache(strategy_ids, filtered_results)
        
        return filtered_results
    
    def _update_strategy_screening_cache(self, strategy_ids: List[str], results: List[EnhancedStrategyResult]):
        """更新策略筛选缓存"""
        try:
            from strategy_screening_cache import strategy_screening_cache
            
            # 按策略分组结果
            strategy_results = {}
            for strategy_id in strategy_ids:
                strategy_results[strategy_id] = []
            
            for result in results:
                # 将结果添加到所有策略中（简化处理）
                for strategy_id in strategy_ids:
                    stock_data = {
                        'stock_code': result.stock_code,
                        'stock_name': result.stock_name,
                        'date': str(result.date),
                        'signal_type': result.signal_type,
                        'price': result.current_price,
                        'confluence_score': result.confluence_score,
                        'quality_grade': result.quality_grade,
                        'pattern_detected': result.pattern_detected,
                        'pattern_type': result.pattern_type,
                        'risk_level': result.risk_level
                    }
                    strategy_results[strategy_id].append(stock_data)
            
            # 保存每个策略的结果到缓存
            for strategy_id, stock_list in strategy_results.items():
                strategy_screening_cache.save_screening_results(strategy_id, stock_list)
                logger.info(f"📋 策略 {strategy_id} 筛选结果已更新到缓存 ({len(stock_list)}只股票)")
                
        except Exception as e:
            logger.error(f"更新策略筛选缓存失败: {e}")
    
    def get_quality_summary(self, results: List[EnhancedStrategyResult]) -> dict:
        """获取质量统计摘要"""
        if not results:
            return {}
        
        total_count = len(results)
        grade_counts = {'A': 0, 'B': 0, 'C': 0}
        pattern_counts = {}
        risk_counts = {'LOW': 0, 'MEDIUM': 0, 'HIGH': 0}
        
        avg_confluence_score = sum(r.confluence_score for r in results) / total_count
        avg_confidence = sum(r.confidence for r in results) / total_count
        avg_price_position = sum(r.price_position_pct for r in results) / total_count
        
        for result in results:
            # 质量等级统计
            if result.quality_grade in grade_counts:
                grade_counts[result.quality_grade] += 1
            
            # 形态统计
            if result.pattern_detected and result.pattern_type:
                if result.pattern_type not in pattern_counts:
                    pattern_counts[result.pattern_type] = 0
                pattern_counts[result.pattern_type] += 1
            
            # 风险等级统计
            if result.risk_level in risk_counts:
                risk_counts[result.risk_level] += 1
        
        return {
            'total_signals': total_count,
            'quality_distribution': grade_counts,
            'pattern_distribution': pattern_counts,
            'risk_distribution': risk_counts,
            'avg_confluence_score': avg_confluence_score,
            'avg_confidence': avg_confidence,
            'avg_price_position_pct': avg_price_position * 100,
            'high_quality_ratio': grade_counts['A'] / total_count * 100 if total_count > 0 else 0
        }

# 全局实例
enhanced_screener = EnhancedScreener()