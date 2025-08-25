#!/usr/bin/env python3
"""
增强筛选脚本 - 集成参数优化的智能股票分析 (多线程版本)
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

import json
import threading
import queue
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from enhanced_analyzer import EnhancedTradingAnalyzer

def perform_price_evaluation(stock_code, analysis_result):
    """对A级股票进行价格评估"""
    try:
        from trading_advisor import TradingAdvisor
        
        # 获取基础分析数据
        basic = analysis_result.get('basic_analysis', {})
        current_price = basic.get('current_price', 0)
        
        # 获取交易建议数据
        trading = analysis_result.get('trading_advice', {})
        advice = trading.get('advice', {})
        
        price_evaluation = {
            'evaluation_time': datetime.now().isoformat(),
            'stock_code': stock_code,
            'current_price': current_price,
            'grade': 'A',
            'evaluation_details': {}
        }
        
        if 'entry_strategies' in advice and advice['entry_strategies']:
            strategy = advice['entry_strategies'][0]
            price_evaluation['evaluation_details'] = {
                'entry_strategy': strategy.get('strategy', 'N/A'),
                'target_price_1': strategy.get('entry_price_1', 0),
                'target_price_2': strategy.get('entry_price_2', 0),
                'position_allocation': strategy.get('position_allocation', 'N/A'),
                'discount_1': (current_price - strategy.get('entry_price_1', current_price)) / current_price if current_price > 0 else 0,
                'discount_2': (current_price - strategy.get('entry_price_2', current_price)) / current_price if current_price > 0 else 0
            }
        
        if 'risk_management' in advice:
            risk_mgmt = advice['risk_management']
            if 'stop_loss_levels' in risk_mgmt:
                stops = risk_mgmt['stop_loss_levels']
                price_evaluation['evaluation_details']['stop_loss'] = {
                    'conservative': stops.get('conservative', 0),
                    'moderate': stops.get('moderate', 0),
                    'aggressive': stops.get('aggressive', 0),
                    'technical': stops.get('technical', 0)
                }
            
            if 'take_profit_levels' in risk_mgmt:
                profits = risk_mgmt['take_profit_levels']
                price_evaluation['evaluation_details']['take_profit'] = {
                    'conservative': profits.get('conservative', 0),
                    'moderate': profits.get('moderate', 0),
                    'aggressive': profits.get('aggressive', 0)
                }
        
        # 保存A级股票价格评估记录
        save_a_grade_evaluation(price_evaluation)
        
        return price_evaluation
        
    except Exception as e:
        return {'error': f'价格评估失败: {e}'}

def save_a_grade_evaluation(evaluation):
    """保存A级股票价格评估记录"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        eval_dir = "data/result/A_GRADE_EVALUATIONS"
        os.makedirs(eval_dir, exist_ok=True)
        
        # 保存单个股票评估
        stock_file = f"{eval_dir}/{evaluation['stock_code']}_evaluation_{timestamp}.json"
        with open(stock_file, 'w', encoding='utf-8') as f:
            json.dump(evaluation, f, ensure_ascii=False, indent=2)
        
        # 追加到汇总文件
        summary_file = f"{eval_dir}/a_grade_summary_{datetime.now().strftime('%Y%m%d')}.json"
        
        # 读取现有汇总数据
        summary_data = []
        if os.path.exists(summary_file):
            try:
                with open(summary_file, 'r', encoding='utf-8') as f:
                    summary_data = json.load(f)
            except:
                summary_data = []
        
        # 添加新评估
        summary_data.append(evaluation)
        
        # 保存更新的汇总数据
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary_data, f, ensure_ascii=False, indent=2)
        
        print(f"💾 A级股票评估已保存: {stock_file}")
        
    except Exception as e:
        print(f"❌ 保存A级股票评估失败: {e}")

def format_analysis_report(stock_code, analysis):
    """格式化分析报告"""
    if 'error' in analysis:
        return f"❌ {stock_code}: {analysis['error']}"
    
    print("=" * 80)
    print(f"📊 {stock_code} 增强分析报告")
    print("=" * 80)
    
    # 基础信息
    basic = analysis.get('basic_analysis', {})
    if 'error' not in basic:
        print("📈 基础分析:")
        print(f"  当前价格: ¥{basic['current_price']:.2f}")
        print(f"  30天涨跌: {basic['price_change_30d']:+.1%}")
        print(f"  90天涨跌: {basic['price_change_90d']:+.1%}")
        print(f"  年化波动率: {basic['volatility']:.1%}")
        print(f"  趋势方向: {basic['trend_direction']}")
        print(f"  信号数量: {basic['signal_count']}")
        print()
    
    # 参数化分析
    parametric = analysis.get('parametric_analysis', {})
    if 'error' not in parametric:
        print("🔧 参数化分析:")
        using_optimized = parametric.get('using_optimized_params', False)
        print(f"  使用优化参数: {'是' if using_optimized else '否'}")
        
        backtest = parametric.get('backtest_result', {})
        if 'error' not in backtest:
            print(f"  回测交易次数: {backtest.get('total_trades', 0)}")
            print(f"  胜率: {backtest.get('win_rate', 0):.1%}")
            print(f"  平均收益: {backtest.get('avg_pnl', 0):+.2%}")
            print(f"  最大盈利: {backtest.get('max_win', 0):+.2%}")
            print(f"  最大亏损: {backtest.get('max_loss', 0):+.2%}")
            print(f"  盈亏比: {backtest.get('profit_factor', 0):.2f}")
        print()
    
    # 风险评估
    risk = analysis.get('risk_assessment', {})
    if 'error' not in risk:
        print("⚠️ 风险评估:")
        print(f"  风险等级: {risk.get('risk_level', 'unknown').upper()}")
        print(f"  最大回撤: {risk.get('max_drawdown', 0):+.1%}")
        print(f"  信号密度: {risk.get('signal_density', 0):.3f}")
        print(f"  趋势稳定性: {risk.get('trend_stability', 0):.2f}")
        print()
    
    # 综合评分
    score = analysis.get('overall_score', {})
    if 'error' not in score:
        print("🏆 综合评分:")
        print(f"  总分: {score.get('total_score', 0):.1f}/{score.get('max_score', 100)}")
        print(f"  百分比: {score.get('score_percentage', 0):.1%}")
        print(f"  等级: {score.get('grade', 'N/A')}")
        print()
    
    # 投资建议
    recommendation = analysis.get('recommendation', {})
    if 'error' not in recommendation:
        print("💡 投资建议:")
        action = recommendation.get('action', 'UNKNOWN')
        action_colors = {
            'BUY': '🟢',
            'HOLD': '🟡', 
            'WATCH': '🟠',
            'AVOID': '🔴'
        }
        print(f"  操作建议: {action_colors.get(action, '⚪')} {action}")
        print(f"  信心度: {recommendation.get('confidence', 0):.1%}")
        print(f"  理由: {recommendation.get('reason', 'N/A')}")
        print(f"  风险提示: {recommendation.get('risk_warning', 'N/A')}")
        print()
    
    # 交易建议
    trading = analysis.get('trading_advice', {})
    if 'error' not in trading and 'advice' in trading:
        advice = trading['advice']
        if 'error' not in advice and 'entry_strategies' in advice:
            print("🎯 具体交易建议:")
            print(f"  最新信号: {trading.get('latest_signal_state', 'N/A')} ({trading.get('latest_signal_date', 'N/A')})")
            
            strategies = advice.get('entry_strategies', [])
            if strategies:
                strategy = strategies[0]  # 显示第一个策略
                print(f"  入场策略: {strategy.get('strategy', 'N/A')}")
                print(f"  目标价位1: ¥{strategy.get('entry_price_1', 0)}")
                print(f"  目标价位2: ¥{strategy.get('entry_price_2', 0)}")
                print(f"  仓位配置: {strategy.get('position_allocation', 'N/A')}")
            
            risk_mgmt = advice.get('risk_management', {})
            if 'stop_loss_levels' in risk_mgmt:
                stops = risk_mgmt['stop_loss_levels']
                print(f"  建议止损: ¥{stops.get('moderate', 'N/A')}")
            print()
    
    print("=" * 80)

def analyze_single_stock(stock_code, use_optimized_params=True):
    """分析单只股票"""
    print(f"🔍 开始分析股票: {stock_code}")
    
    analyzer = EnhancedTradingAnalyzer()
    result = analyzer.analyze_stock_comprehensive(stock_code, use_optimized_params)
    
    format_analysis_report(stock_code, result)
    
    return result

def analyze_single_stock_worker(stock_code, use_optimized_params=True):
    """单只股票分析工作函数（用于多线程）"""
    try:
        analyzer = EnhancedTradingAnalyzer()
        result = analyzer.analyze_stock_comprehensive(stock_code, use_optimized_params)
        return stock_code, result
    except Exception as e:
        return stock_code, {'error': f'分析失败: {e}'}

def analyze_multiple_stocks(stock_codes, use_optimized_params=True, max_workers=32):
    """多线程分析多只股票"""
    return deep_scan_stocks(stock_codes, use_optimized_params, max_workers)

def _deep_scan_stocks_fallback(stock_codes, use_optimized_params=True, max_workers=32):
    """标准多线程分析多只股票（备用方法）"""
    print(f"🚀 多线程批量分析 {len(stock_codes)} 只股票 (线程数: {max_workers})")
    
    results = {}
    completed_count = 0
    
    # 使用线程池执行器
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        future_to_stock = {
            executor.submit(analyze_single_stock_worker, stock_code, use_optimized_params): stock_code 
            for stock_code in stock_codes
        }
        
        # 处理完成的任务
        for future in as_completed(future_to_stock):
            stock_code = future_to_stock[future]
            try:
                stock_code, result = future.result()
                results[stock_code] = result
                completed_count += 1
                
                # 显示进度和结果
                if 'error' not in result:
                    score = result['overall_score']['total_score']
                    grade = result['overall_score']['grade']
                    action = result['recommendation']['action']
                    print(f"✅ [{completed_count}/{len(stock_codes)}] {stock_code}: 评分 {score:.1f}, 等级 {grade}, 建议 {action}")
                    
                    # A级股票自动进行价格评估
                    if grade == 'A':
                        price_evaluation = perform_price_evaluation(stock_code, result)
                        result['price_evaluation'] = price_evaluation
                        print(f"💰 {stock_code} A级股票价格评估完成")
                else:
                    print(f"❌ [{completed_count}/{len(stock_codes)}] {stock_code}: {result['error']}")
                    
            except Exception as e:
                print(f"❌ [{completed_count+1}/{len(stock_codes)}] {stock_code}: 处理异常 {e}")
                results[stock_code] = {'error': f'处理异常: {e}'}
                completed_count += 1
    
    return results

def _display_deep_scan_results(results, stock_codes):
    """显示深度扫描结果统计"""
    valid_results = {k: v for k, v in results.items() if 'error' not in v}
    a_grade_stocks = [k for k, v in valid_results.items() if v.get('overall_score', {}).get('grade') == 'A']
    price_evaluated_stocks = [k for k, v in valid_results.items() if 'price_evaluation' in v]
    buy_recommendations = [k for k, v in valid_results.items() if v.get('recommendation', {}).get('action') == 'BUY']
    
    print(f"\n🎉 深度扫描结果:")
    print(f"📊 深度分析成功: {len(valid_results)}/{len(stock_codes)}")
    print(f"🏆 A级股票发现: {len(a_grade_stocks)}")
    print(f"💰 价格评估完成: {len(price_evaluated_stocks)}")
    print(f"🟢 买入推荐: {len(buy_recommendations)}")
    
    if a_grade_stocks:
        print(f"\n🌟 A级股票列表:")
        for stock_code in a_grade_stocks:
            result = valid_results[stock_code]
            score = result['overall_score']['total_score']
            price = result['basic_analysis']['current_price']
            action = result['recommendation']['action']
            confidence = result['recommendation']['confidence']
            price_eval_mark = " 💰" if 'price_evaluation' in result else ""
            print(f"  🏆 {stock_code}: {score:.1f}分, ¥{price:.2f}, {action} ({confidence:.1%}){price_eval_mark}")

def deep_scan_stocks(stock_codes, use_optimized_params=True, max_workers=32):
    """多线程分析多只股票 - 高性能版本 (多股票并行优化)"""
    import multiprocessing
    
    # 强制使用32线程，除非股票数量少于32
    if max_workers is None:
        max_workers = min(32, len(stock_codes))
    else:
        # 确保使用至少32线程，除非股票数量少于32
        max_workers = min(max(32, max_workers), len(stock_codes))
    
    # 计算并行优化的股票数量
    parallel_stocks = min(8, len(stock_codes))
    
    print(f"🚀 多线程批量分析 {len(stock_codes)} 只股票 (线程数: {max_workers}, 并行优化: {parallel_stocks}只)")
    
    # 尝试导入并行优化器
    try:
        try:
            # 先尝试从backend包导入
            from backend.parallel_optimizer import ParallelStockOptimizer
            print("✅ 使用并行股票参数优化器")
            use_parallel_optimizer = True
        except ImportError:
            try:
                # 如果失败，尝试直接导入
                from parallel_optimizer import ParallelStockOptimizer
                print("✅ 使用并行股票参数优化器")
                use_parallel_optimizer = True
            except ImportError:
                # 如果都失败，使用标准优化器
                use_parallel_optimizer = False
                print("⚠️ 并行优化器不可用，使用标准优化")
    except Exception:
        use_parallel_optimizer = False
    
    # 导入性能优化模块
    try:
        # 先尝试从backend包导入
        try:
            from backend.performance_optimizer import BatchProcessor
            print("✅ 使用backend包中的性能优化模块")
        except ImportError:
            # 如果失败，尝试直接导入（当前目录）
            from performance_optimizer import BatchProcessor
            print("✅ 使用当前目录的性能优化模块")
        
        # 使用批量处理器
        batch_processor = BatchProcessor(max_workers=max_workers)
        
        def process_single_stock(stock_code):
            """处理单只股票的包装函数"""
            try:
                # 使用并行优化器时，需要特殊处理
                if use_parallel_optimizer:
                    # 创建分析器但不执行优化
                    analyzer = EnhancedTradingAnalyzer()
                    
                    # 加载数据
                    stock_data = analyzer._load_stock_data(stock_code)
                    if stock_data is None:
                        return {'error': f'无法加载股票数据: {stock_code}'}
                    
                    df, signals = stock_data['df'], stock_data['signals']
                    
                    # 基础分析
                    basic_analysis = analyzer._perform_basic_analysis(df, signals)
                    
                    # 参数化分析会在后面批量执行
                    parametric_analysis = {'message': '参数优化将在批处理中执行'}
                    
                    # 临时结果
                    temp_result = {
                        'stock_code': stock_code,
                        'analysis_date': datetime.now().isoformat(),
                        'basic_analysis': basic_analysis,
                        'parametric_analysis': parametric_analysis,
                        'df': df,
                        'signals': signals,
                        'needs_optimization': True
                    }
                    
                    return temp_result
                else:
                    # 标准处理方式
                    result = analyze_single_stock_worker(stock_code, use_optimized_params)[1]
                    
                    # A级股票自动进行价格评估
                    if ('error' not in result and 
                        result.get('overall_score', {}).get('grade') == 'A'):
                        price_evaluation = perform_price_evaluation(stock_code, result)
                        result['price_evaluation'] = price_evaluation
                        print(f"💰 {stock_code} A级股票价格评估完成")
                    
                    return result
                
            except Exception as e:
                return {'error': f'处理异常: {e}'}
        
        # 使用批量处理器执行
        temp_results = batch_processor.process_stocks_batch(
            stock_codes, 
            process_single_stock, 
            batch_size=min(20, len(stock_codes))
        )
        
        # 如果使用并行优化器，执行批量参数优化
        if use_parallel_optimizer:
            print("\n🔄 开始并行参数优化...")
            
            # 准备需要优化的股票数据
            stocks_to_optimize = []
            for stock_code, result in temp_results.items():
                if 'error' not in result and result.get('needs_optimization', False):
                    stocks_to_optimize.append({
                        'stock_code': stock_code,
                        'df': result['df'],
                        'signals': result['signals']
                    })
            
            if stocks_to_optimize:
                # 创建并行优化器
                optimizer = ParallelStockOptimizer(max_stocks_parallel=parallel_stocks)
                
                # 执行并行优化
                optimization_results = optimizer.optimize_stocks_batch(stocks_to_optimize)
                
                # 处理优化结果
                for stock_code, opt_result in optimization_results.items():
                    if stock_code in temp_results and 'error' not in opt_result:
                        # 创建分析器完成剩余分析
                        analyzer = EnhancedTradingAnalyzer()
                        
                        # 获取临时结果
                        result = temp_results[stock_code]
                        df, signals = result['df'], result['signals']
                        
                        # 创建参数对象
                        from parametric_advisor import TradingParameters, ParametricTradingAdvisor
                        if 'best_parameters' in opt_result and opt_result['best_parameters']:
                            optimized_params = TradingParameters(**opt_result['best_parameters'])
                            
                            # 使用优化参数完成分析
                            advisor = ParametricTradingAdvisor(optimized_params)
                            #print(f"✅ {stock_code}: 使用优化参数")
                            
                            # 执行回测
                            backtest_result = advisor.backtest_parameters(df, signals, 'moderate')
                            
                            # 更新参数化分析结果
                            result['parametric_analysis'] = {
                                'using_optimized_params': True,
                                'parameters': optimized_params.__dict__,
                                'backtest_result': backtest_result,
                                'best_advisor': advisor
                            }
                        else:
                            # 使用默认参数
                            advisor = ParametricTradingAdvisor()
                            print(f"📋 {stock_code}: 使用默认参数")
                            
                            # 执行回测
                            backtest_result = advisor.backtest_parameters(df, signals, 'moderate')
                            
                            # 更新参数化分析结果
                            result['parametric_analysis'] = {
                                'using_optimized_params': False,
                                'parameters': advisor.parameters.__dict__,
                                'backtest_result': backtest_result,
                                'best_advisor': advisor
                            }
                        
                        # 交易建议
                        result['trading_advice'] = analyzer._generate_trading_advice(df, signals, advisor)
                        
                        # 风险评估
                        result['risk_assessment'] = analyzer._assess_risk_profile(df, signals)
                        
                        # 综合评分
                        result['overall_score'] = analyzer._calculate_overall_score(
                            result['basic_analysis'], 
                            result['parametric_analysis'], 
                            result['risk_assessment']
                        )
                        
                        # 生成建议
                        result['recommendation'] = analyzer._generate_recommendation(
                            result['overall_score'], 
                            result['trading_advice']
                        )
                        
                        # 删除临时数据
                        if 'df' in result:
                            del result['df']
                        if 'signals' in result:
                            del result['signals']
                        if 'needs_optimization' in result:
                            del result['needs_optimization']
                        
                        # A级股票自动进行价格评估
                        if result['overall_score']['grade'] == 'A':
                            price_evaluation = perform_price_evaluation(stock_code, result)
                            result['price_evaluation'] = price_evaluation
                            print(f"💰 {stock_code} A级股票价格评估完成")
                        
                        # 显示结果
                        score = result['overall_score']['total_score']
                        grade = result['overall_score']['grade']
                        action = result['recommendation']['action']
                        print(f"✅ {stock_code}: 评分 {score:.1f}, 等级 {grade}, 建议 {action}")
            
            # 最终结果
            results = {}
            for stock_code, result in temp_results.items():
                if 'df' in result:
                    del result['df']
                if 'signals' in result:
                    del result['signals']
                if 'needs_optimization' in result:
                    del result['needs_optimization']
                results[stock_code] = result
        else:
            # 不使用并行优化器，直接使用临时结果
            results = temp_results
        
    except ImportError as e:
        # 如果性能优化模块不可用，使用原始方法
        print(f"⚠️ 性能优化模块导入失败: {e}，使用标准多线程方法")
        results = _deep_scan_stocks_fallback(stock_codes, use_optimized_params, max_workers)
    
    # 统计和显示结果
    _display_deep_scan_results(results, stock_codes)
    
    # 保存详细结果
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    output_file = f"data/result/ENHANCED_ANALYSIS/enhanced_analysis_{timestamp}.json"
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    
    # 生成简化报告
    report_file = f"data/result/ENHANCED_ANALYSIS/enhanced_analysis_{timestamp}.txt"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(f"增强分析报告 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n\n")
        
        # 统计摘要
        valid_results = {k: v for k, v in results.items() if 'error' not in v}
        f.write(f"分析股票总数: {len(stock_codes)}\n")
        f.write(f"成功分析数量: {len(valid_results)}\n")
        f.write(f"失败分析数量: {len(stock_codes) - len(valid_results)}\n\n")
        
        if valid_results:
            # 按评分排序
            sorted_stocks = sorted(
                valid_results.items(),
                key=lambda x: x[1]['overall_score']['total_score'],
                reverse=True
            )
            
            f.write("股票排名 (按综合评分):\n")
            f.write("-" * 50 + "\n")
            
            for i, (stock_code, result) in enumerate(sorted_stocks, 1):
                score = result['overall_score']['total_score']
                grade = result['overall_score']['grade']
                action = result['recommendation']['action']
                confidence = result['recommendation']['confidence']
                
                f.write(f"{i:2d}. {stock_code}: {score:5.1f}分 ({grade}级) - {action} (信心度: {confidence:.1%})\n")
            
            f.write("\n" + "=" * 50 + "\n")
            f.write("推荐买入股票 (评分>=70分):\n")
            f.write("-" * 30 + "\n")
            
            buy_recommendations = [
                (code, result) for code, result in sorted_stocks
                if result['recommendation']['action'] == 'BUY' and result['overall_score']['total_score'] >= 70
            ]
            
            if buy_recommendations:
                for code, result in buy_recommendations:
                    score = result['overall_score']['total_score']
                    basic = result['basic_analysis']
                    f.write(f"{code}: {score:.1f}分, 当前价格: ¥{basic['current_price']:.2f}, ")
                    f.write(f"30天涨跌: {basic['price_change_30d']:+.1%}\n")
            else:
                f.write("暂无符合条件的推荐股票\n")
    
    print(f"\n📄 详细结果已保存到: {output_file}")
    print(f"📄 分析报告已保存到: {report_file}")
    
    return results

def get_sample_stock_codes():
    """获取样本股票代码"""
    return [
        'sh000001',  # 上证指数
        'sz000001',  # 平安银行
        'sh600000',  # 浦发银行
        'sz000002',  # 万科A
        'sh600036',  # 招商银行
        'sz000858',  # 五粮液
        'sh600519',  # 贵州茅台
        'sz000725',  # 京东方A
        'sh600276',  # 恒瑞医药
        'sz002415'   # 海康威视
    ]

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("使用方法:")
        print("  python run_enhanced_screening.py <股票代码>                    # 分析单只股票")
        print("  python run_enhanced_screening.py batch <股票代码1> <股票代码2>...  # 批量分析")
        print("  python run_enhanced_screening.py sample                        # 分析样本股票")
        print("  python run_enhanced_screening.py --no-optimize <股票代码>       # 不使用参数优化")
        print("")
        print("示例:")
        print("  python run_enhanced_screening.py sh000001")
        print("  python run_enhanced_screening.py batch sh000001 sz000001")
        print("  python run_enhanced_screening.py sample")
        print("  python run_enhanced_screening.py --no-optimize sh000001")
        return
    
    use_optimized_params = '--no-optimize' not in sys.argv
    
    if sys.argv[1] == 'sample':
        # 分析样本股票
        stock_codes = get_sample_stock_codes()
        analyze_multiple_stocks(stock_codes, use_optimized_params)
        
    elif sys.argv[1] == 'batch':
        # 批量分析
        if '--no-optimize' in sys.argv:
            stock_codes = [code.lower() for code in sys.argv[2:] if code != '--no-optimize']
        else:
            stock_codes = [code.lower() for code in sys.argv[2:]]
        
        if not stock_codes:
            print("❌ 请提供要分析的股票代码")
            return
        
        analyze_multiple_stocks(stock_codes, use_optimized_params)
        
    else:
        # 单只股票分析
        if '--no-optimize' in sys.argv:
            stock_code = [arg for arg in sys.argv[1:] if arg != '--no-optimize'][0].lower()
        else:
            stock_code = sys.argv[1].lower()
        
        result = analyze_single_stock(stock_code, use_optimized_params)
        
        if 'error' not in result:
            print(f"\n🎉 {stock_code} 分析完成！")
            score = result['overall_score']['total_score']
            grade = result['overall_score']['grade']
            action = result['recommendation']['action']
            print(f"📊 综合评分: {score:.1f}分 ({grade}级)")
            print(f"💡 投资建议: {action}")

if __name__ == "__main__":
    main()