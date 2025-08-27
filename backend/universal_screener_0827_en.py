# backend/universal_screener.py

"""
【最终优化版】通用股票筛选器 (已升级为分析预热器)
"""
import json
import pandas as pd
from typing import List, Optional
from dataclasses import dataclass, asdict
from concurrent.futures import ProcessPoolExecutor, as_completed
import logging
from strategy_manager import strategy_manager
from data_handler import get_full_data_with_indicators
# --- 核心修改：导入统一分析服务 ---
from unified_analysis_service import get_or_run_analysis
from stock_pool_manager import StockPoolManager
# --- 新增：导入多指标融合评分系统 ---
from confluence_scorer import confluence_scorer
from pattern_recognizer import pattern_recognizer

logger = logging.getLogger(__name__)
@dataclass
class StrategyResult:
    stock_code: str
    stock_name: str
    date: pd.Timestamp
    signal_type: str
    current_price: float

def _screening_worker_n_process(args_tuple: tuple) -> List[StrategyResult]:
    """
    【多进程工作函数 - 升级版】
    为单只股票运行策略筛选，并引入更精细的信号质量判断。
    """
    stock_info, strategy_ids, db_path = args_tuple
    
    pool_manager = StockPoolManager(db_path)
    
    stock_code = stock_info.get('stock_code')
    if not stock_code:
        return []

    worker_results = []
    
    try:
        # ... (获取 optimized_params 和 stock_name 的逻辑保持不变) ...
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

        df = get_full_data_with_indicators(stock_code, **optimized_params)
        if df is None or len(df) < 50:
            return []

        for strategy_id in strategy_ids:
            strategy_instance = strategy_manager.get_strategy_instance(strategy_id)
            if not strategy_instance:
                continue
            
            # --- 核心修改逻辑从这里开始 ---

            # 1. 获取策略的返回结果
            result = strategy_instance.apply_strategy(df)
            
            # 2. 统一处理策略可能返回的多种格式
            signals = None
            confidence_scores = None # 用于存储置信度
            
            if isinstance(result, tuple) and len(result) == 2:
                # 假设策略返回 (信号, 置信度)，这是最理想的格式
                signals, confidence_scores = result
            elif isinstance(result, pd.Series):
                # 策略只返回了信号
                signals = result
            else:
                # 策略返回了无效格式，跳过
                continue
            
            if signals is None or signals.empty:
                continue

            # 3. 精准筛选出有效的文本信号
            actual_signals = signals.loc[signals.apply(lambda x: isinstance(x, str) and x != '')]

            if not actual_signals.empty:
                latest_signal_date = actual_signals.index.max()
                
                # 4. 增加更严格的过滤条件
                time_window_days = 5  # 将时间窗口放宽到5天，避免错过稍早的信号
                min_confidence_threshold = 0.7 # 设置一个置信度门槛

                # 检查时效性
                is_recent = pd.notna(latest_signal_date) and (df.index.max() - latest_signal_date).days <= time_window_days
                
                # 检查置信度 (如果策略提供了)
                has_high_confidence = True # 默认置信度为高
                if confidence_scores is not None:
                    # 如果策略返回了置信度，则使用它来判断
                    latest_confidence = confidence_scores.get(latest_signal_date, 0)
                    has_high_confidence = latest_confidence >= min_confidence_threshold
                
                # 检查价格有效性
                current_price = df.loc[latest_signal_date, 'close']
                is_price_valid = pd.notna(current_price) and current_price > 0

                # 5. 必须同时满足所有条件，才被认为是高质量信号
                if is_recent and has_high_confidence and is_price_valid:
                    worker_results.append(
                        StrategyResult(
                            stock_code=stock_code,
                            stock_name=stock_name,
                            date=latest_signal_date,
                            signal_type=str(actual_signals.loc[latest_signal_date]),
                            current_price=current_price
                        )
                    )
            # --- 核心修改逻辑结束 ---
            
    except Exception as e:
        logger.error(f"处理 {stock_code} 时发生错误: {e}")
        return []
    
    return worker_results

def _screening_worker_process(args_tuple: tuple) -> List[StrategyResult]:
    """
    【多进程工作函数】
    为单只股票运行策略筛选，并返回结果。
    这个函数必须是顶层函数，不能是类的方法。
    """
    stock_info, strategy_ids, db_path = args_tuple
    
    pool_manager = StockPoolManager(db_path)
    
    stock_code = stock_info.get('stock_code')
    if not stock_code:
        return []

    worker_results = []
    
    try:
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

        df = get_full_data_with_indicators(stock_code, **optimized_params)
        if df is None or len(df) < 50:
            return []

        for strategy_id in strategy_ids:
            strategy_instance = strategy_manager.get_strategy_instance(strategy_id)
            if not strategy_instance:
                continue
            
            result = strategy_instance.apply_strategy(df)
            
            if isinstance(result, tuple):
                signals, _ = result
            else:
                signals = result
            
            if signals is not None and not signals.empty:
                # --- 这是核心修复逻辑 ---
                # 1. 定义一个“有效信号”是那些值为非空字符串的行
                #    这样可以自动过滤掉 False, 0, np.nan, '' 等无效信号
                actual_signals = signals.loc[signals.apply(lambda x: isinstance(x, str) and x != '')]

                # 2. 只有在确实存在有效信号时，才继续判断
                if not actual_signals.empty:
                    latest_signal_date = actual_signals.index.max()
                    
                    # 3. 检查最新信号是否在3天内
                    if pd.notna(latest_signal_date) and (df.index.max() - latest_signal_date).days <= 3:
                        worker_results.append(
                            StrategyResult(
                                stock_code=stock_code,
                                stock_name=stock_name,
                                date=latest_signal_date,
                                # 从我们筛选出的 actual_signals 中获取信号类型
                                signal_type=str(actual_signals.loc[latest_signal_date]),
                                current_price=df.loc[latest_signal_date, 'close']
                            )
                        )
            
    except Exception as e:
        logger.error(f"处理 {stock_code} 时发生错误: {e}")
        return []
    
    return worker_results

class UniversalScreener:
    """
    通用股票筛选器。
    新职责：在发现信号后，立即调用统一分析服务，
    将该股票的完整分析结果预先计算并存入数据库缓存。
    """
    def __init__(self, stock_pool: Optional[List[dict]] = None):
        self.pool_manager = StockPoolManager()
        if stock_pool is None:
            self.stock_pool = self.pool_manager.get_all_stocks()
        else:
            self.stock_pool = stock_pool
        
        # 初始化增强版筛选器
        from enhanced_screener import EnhancedScreener
        self.enhanced_screener = EnhancedScreener(stock_pool)

    def run_screening(self, strategy_ids: List[str], max_workers: Optional[int] = 31) -> List[StrategyResult]:
        """
        运行多进程股票筛选。
        :param strategy_ids: 待运行的策略ID列表。
        :param max_workers: 最大工作进程数。
        :return: 筛选结果列表。
        """
        all_results = []
        total_stocks = len(self.stock_pool)
        
        if not self.stock_pool:
            logger.warning("股票池为空，筛选任务退出。")
            return all_results

        logger.info(f"🚀 通用筛选器启动，策略: {', '.join(strategy_ids)}, "
                    f"股票池数量: {total_stocks}, 最大工作进程数: {max_workers or '自动'}")
        
        tasks = [(stock_info, strategy_ids, self.pool_manager.db_path) for stock_info in self.stock_pool]

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_screening_worker_n_process, task): task[0]['stock_code'] for task in tasks}
            
            for i, future in enumerate(as_completed(futures), 1):
                stock_code = futures[future]
                print(f"\r🔍 处理进度 [{i}/{total_stocks}]: {stock_code}", end="", flush=True)
                
                try:
                    worker_results = future.result()
                    all_results.extend(worker_results)
                except Exception as e:
                    logger.error(f"处理 {stock_code} 时主进程捕获异常: {e}")
                    continue
        
        print(f"\n✅ 筛选完成，共发现 {len(all_results)} 个有效信号。")
        
        # 更新策略筛选缓存
        self._update_strategy_screening_cache(strategy_ids, all_results)
        
        return all_results
    
    def _update_strategy_screening_cache(self, strategy_ids: List[str], results: List[StrategyResult]):
        """更新策略筛选缓存"""
        try:
            from strategy_screening_cache import strategy_screening_cache
            
            # 按策略分组结果
            strategy_results = {}
            for strategy_id in strategy_ids:
                strategy_results[strategy_id] = []
            
            for result in results:
                # 假设结果中包含策略信息，如果没有则需要修改数据结构
                # 这里简化处理，将结果添加到所有策略中
                for strategy_id in strategy_ids:
                    stock_data = {
                        'stock_code': result.stock_code,
                        'stock_name': result.stock_name,
                        'date': str(result.date),
                        'signal_type': result.signal_type,
                        'price': result.current_price
                    }
                    strategy_results[strategy_id].append(stock_data)
            
            # 保存每个策略的结果到缓存
            for strategy_id, stock_list in strategy_results.items():
                strategy_screening_cache.save_screening_results(strategy_id, stock_list)
                print(f"📋 策略 {strategy_id} 筛选结果已更新到缓存 ({len(stock_list)}只股票)")
                
        except Exception as e:
            logger.error(f"更新策略筛选缓存失败: {e}")
    
    def run_enhanced_screening(self, strategy_ids: List[str], 
                             max_workers: Optional[int] = 31,
                             min_quality_grade: str = 'B') -> List:
        """
        运行增强版筛选，集成多指标融合评分系统
        
        Args:
            strategy_ids: 待运行的策略ID列表
            max_workers: 最大工作进程数
            min_quality_grade: 最低质量等级 ('A', 'B', 'C')
        
        Returns:
            增强版筛选结果列表
        """
        logger.info(f"🚀 启动增强版筛选器，最低质量等级: {min_quality_grade}")
        
        # 调用增强版筛选器
        enhanced_results = self.enhanced_screener.run_enhanced_screening(
            strategy_ids=strategy_ids,
            max_workers=max_workers,
            min_quality_grade=min_quality_grade
        )
        
        # 获取质量统计摘要
        quality_summary = self.enhanced_screener.get_quality_summary(enhanced_results)
        
        logger.info(f"📊 增强版筛选完成:")
        logger.info(f"   总信号数: {quality_summary.get('total_signals', 0)}")
        logger.info(f"   质量分布: {quality_summary.get('quality_distribution', {})}")
        logger.info(f"   平均融合评分: {quality_summary.get('avg_confluence_score', 0):.1f}")
        logger.info(f"   高质量比例: {quality_summary.get('high_quality_ratio', 0):.1f}%")
        
        return enhanced_results
    
    def get_screening_mode_comparison(self, strategy_ids: List[str], 
                                    max_workers: Optional[int] = 31) -> dict:
        """
        对比传统筛选和增强版筛选的结果
        
        Returns:
            包含两种模式结果对比的字典
        """
        logger.info("🔄 开始筛选模式对比测试...")
        
        # 运行传统筛选
        logger.info("运行传统筛选...")
        traditional_results = self.run_screening(strategy_ids, max_workers)
        
        # 运行增强版筛选
        logger.info("运行增强版筛选...")
        enhanced_results = self.run_enhanced_screening(strategy_ids, max_workers, 'C')
        
        # 统计对比
        comparison = {
            'traditional': {
                'count': len(traditional_results),
                'stocks': [r.stock_code for r in traditional_results]
            },
            'enhanced': {
                'count': len(enhanced_results),
                'stocks': [r.stock_code for r in enhanced_results],
                'quality_summary': self.enhanced_screener.get_quality_summary(enhanced_results)
            },
            'overlap': {
                'count': 0,
                'stocks': []
            },
            'enhanced_only': {
                'count': 0,
                'stocks': []
            },
            'traditional_only': {
                'count': 0,
                'stocks': []
            }
        }
        
        # 计算重叠和差异
        traditional_codes = set(r.stock_code for r in traditional_results)
        enhanced_codes = set(r.stock_code for r in enhanced_results)
        
        overlap_codes = traditional_codes & enhanced_codes
        enhanced_only_codes = enhanced_codes - traditional_codes
        traditional_only_codes = traditional_codes - enhanced_codes
        
        comparison['overlap']['count'] = len(overlap_codes)
        comparison['overlap']['stocks'] = list(overlap_codes)
        comparison['enhanced_only']['count'] = len(enhanced_only_codes)
        comparison['enhanced_only']['stocks'] = list(enhanced_only_codes)
        comparison['traditional_only']['count'] = len(traditional_only_codes)
        comparison['traditional_only']['stocks'] = list(traditional_only_codes)
        
        logger.info(f"📊 筛选模式对比结果:")
        logger.info(f"   传统筛选: {comparison['traditional']['count']} 只股票")
        logger.info(f"   增强筛选: {comparison['enhanced']['count']} 只股票")
        logger.info(f"   重叠股票: {comparison['overlap']['count']} 只")
        logger.info(f"   增强版独有: {comparison['enhanced_only']['count']} 只")
        logger.info(f"   传统版独有: {comparison['traditional_only']['count']} 只")
        
        return comparison

def main():
    """主执行函数"""
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(description='通用股票筛选器')
    parser.add_argument('--strategies', '-s', nargs='+', 
                       default=['深渊筑底策略_v2.0', 'MACD零轴启动_v1.0'],
                       help='策略ID列表 (默认: 深渊筑底策略_v2.0 MACD零轴启动_v1.0)')
    parser.add_argument('--workers', '-w', type=int, default=4,
                       help='最大工作进程数 (默认: 4)')
    parser.add_argument('--mode', '-m', choices=['traditional', 'enhanced', 'compare'], 
                       default='enhanced',
                       help='筛选模式 (默认: enhanced)')
    parser.add_argument('--min-grade', '-g', choices=['A', 'B', 'C'], default='B',
                       help='最低质量等级 (默认: B)')
    parser.add_argument('--output', '-o', type=str,
                       help='输出文件路径 (可选)')
    
    args = parser.parse_args()
    
    print("🚀 启动通用股票筛选器")
    print(f"📋 策略列表: {', '.join(args.strategies)}")
    print(f"⚙️ 工作进程数: {args.workers}")
    print(f"🎯 筛选模式: {args.mode}")
    if args.mode == 'enhanced':
        print(f"🏆 最低质量等级: {args.min_grade}")
    print("=" * 60)
    
    try:
        # 初始化筛选器
        screener = UniversalScreener()
        
        if args.mode == 'traditional':
            # 传统筛选模式
            results = screener.run_screening(args.strategies, args.workers)
            
            print(f"\n📊 传统筛选结果:")
            print(f"   发现信号: {len(results)} 个")
            
            if results:
                print(f"\n📋 筛选结果详情:")
                for i, result in enumerate(results[:10], 1):  # 显示前10个结果
                    print(f"   {i}. {result.stock_code} ({result.stock_name})")
                    print(f"      信号: {result.signal_type}")
                    print(f"      日期: {result.date.strftime('%Y-%m-%d')}")
                    print(f"      价格: ¥{result.current_price:.2f}")
                    print()
                
                if len(results) > 10:
                    print(f"   ... 还有 {len(results) - 10} 个结果")
            
        elif args.mode == 'enhanced':
            # 增强筛选模式
            results = screener.run_enhanced_screening(
                args.strategies, args.workers, args.min_grade
            )
            
            print(f"\n📊 增强筛选结果:")
            print(f"   发现信号: {len(results)} 个")
            
            if results:
                # 获取质量统计
                quality_summary = screener.enhanced_screener.get_quality_summary(results)
                print(f"\n📈 质量统计:")
                print(f"   质量分布: {quality_summary.get('quality_distribution', {})}")
                print(f"   平均融合评分: {quality_summary.get('avg_confluence_score', 0):.1f}")
                print(f"   高质量比例: {quality_summary.get('high_quality_ratio', 0):.1f}%")
                
                print(f"\n📋 筛选结果详情 (前10个):")
                for i, result in enumerate(results[:10], 1):
                    print(f"   {i}. {result.stock_code} ({result.stock_name})")
                    print(f"      信号: {result.signal_type}")
                    print(f"      质量等级: {getattr(result, 'quality_grade', 'N/A')}")
                    print(f"      融合评分: {getattr(result, 'confluence_score', 0):.1f}")
                    print(f"      日期: {result.date.strftime('%Y-%m-%d')}")
                    print(f"      价格: ¥{result.current_price:.2f}")
                    print()
                
                if len(results) > 10:
                    print(f"   ... 还有 {len(results) - 10} 个结果")
            
        elif args.mode == 'compare':
            # 对比模式
            comparison = screener.get_screening_mode_comparison(args.strategies, args.workers)
            
            print(f"\n📊 筛选模式对比结果:")
            print(f"   传统筛选: {comparison['traditional']['count']} 只股票")
            print(f"   增强筛选: {comparison['enhanced']['count']} 只股票")
            print(f"   重叠股票: {comparison['overlap']['count']} 只")
            print(f"   增强版独有: {comparison['enhanced_only']['count']} 只")
            print(f"   传统版独有: {comparison['traditional_only']['count']} 只")
            
            if comparison['enhanced_only']['stocks']:
                print(f"\n🆕 增强版独有股票:")
                for stock in comparison['enhanced_only']['stocks'][:5]:
                    print(f"   • {stock}")
                if len(comparison['enhanced_only']['stocks']) > 5:
                    print(f"   ... 还有 {len(comparison['enhanced_only']['stocks']) - 5} 只")
        
        # 保存结果到文件 (如果指定了输出路径)
        if args.output:
            try:
                import json
                from datetime import datetime
                
                output_data = {
                    'timestamp': datetime.now().isoformat(),
                    'mode': args.mode,
                    'strategies': args.strategies,
                    'workers': args.workers,
                    'results': []
                }
                
                if args.mode == 'compare':
                    output_data['comparison'] = comparison
                else:
                    # 将结果转换为可序列化的格式
                    for result in results:
                        result_dict = {
                            'stock_code': result.stock_code,
                            'stock_name': result.stock_name,
                            'date': result.date.isoformat(),
                            'signal_type': result.signal_type,
                            'current_price': result.current_price
                        }
                        
                        # 添加增强筛选的额外字段
                        if hasattr(result, 'quality_grade'):
                            result_dict['quality_grade'] = result.quality_grade
                        if hasattr(result, 'confluence_score'):
                            result_dict['confluence_score'] = result.confluence_score
                        
                        output_data['results'].append(result_dict)
                
                with open(args.output, 'w', encoding='utf-8') as f:
                    json.dump(output_data, f, ensure_ascii=False, indent=2)
                
                print(f"\n💾 结果已保存到: {args.output}")
                
            except Exception as e:
                print(f"⚠️ 保存结果失败: {e}")
        
        print(f"\n✅ 筛选任务完成!")
        return 0
        
    except KeyboardInterrupt:
        print(f"\n⚠️ 用户中断筛选任务")
        return 1
    except Exception as e:
        print(f"\n❌ 筛选任务失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    import sys
    exit_code = main()
    sys.exit(exit_code)