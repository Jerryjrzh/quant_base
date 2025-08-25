#!/usr/bin/env python3
"""
增强筛选脚本 - 集成参数优化的智能股票分析 (多进程V2最终优化版)
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

import json
import threading
import queue
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
import multiprocessing
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
        
        stock_file = f"{eval_dir}/{evaluation['stock_code']}_evaluation_{timestamp}.json"
        with open(stock_file, 'w', encoding='utf-8') as f:
            json.dump(evaluation, f, ensure_ascii=False, indent=2)
        
        summary_file = f"{eval_dir}/a_grade_summary_{datetime.now().strftime('%Y%m%d')}.json"
        
        summary_data = []
        if os.path.exists(summary_file):
            try:
                with open(summary_file, 'r', encoding='utf-8') as f:
                    summary_data = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                summary_data = []
        
        summary_data.append(evaluation)
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary_data, f, ensure_ascii=False, indent=2)
        
    except Exception as e:
        # 在并行工作单元中，最好不要打印，而是通过返回值传递错误
        pass

def format_analysis_report(stock_code, analysis):
    """格式化分析报告"""
    if 'error' in analysis:
        return f"❌ {stock_code}: {analysis['error']}"
    
    print("=" * 80)
    print(f"📊 {stock_code} 增强分析报告")
    print("=" * 80)
    
    basic = analysis.get('basic_analysis', {})
    if 'error' not in basic:
        print("📈 基础分析:")
        print(f"  当前价格: ¥{basic.get('current_price', 0):.2f}")
        print(f"  30天涨跌: {basic.get('price_change_30d', 0):+.1%}")
        print(f"  90天涨跌: {basic.get('price_change_90d', 0):+.1%}")
        print(f"  年化波动率: {basic.get('volatility', 0):.1%}")
        print(f"  趋势方向: {basic.get('trend_direction', 'N/A')}")
        print(f"  信号数量: {basic.get('signal_count', 0)}")
        print()
    
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
    
    risk = analysis.get('risk_assessment', {})
    if 'error' not in risk:
        print("⚠️ 风险评估:")
        print(f"  风险等级: {risk.get('risk_level', 'unknown').upper()}")
        print(f"  最大回撤: {risk.get('max_drawdown', 0):+.1%}")
        print(f"  信号密度: {risk.get('signal_density', 0):.3f}")
        print(f"  趋势稳定性: {risk.get('trend_stability', 0):.2f}")
        print()
    
    score = analysis.get('overall_score', {})
    if 'error' not in score:
        print("🏆 综合评分:")
        print(f"  总分: {score.get('total_score', 0):.1f}/{score.get('max_score', 100)}")
        print(f"  百分比: {score.get('score_percentage', 0):.1%}")
        print(f"  等级: {score.get('grade', 'N/A')}")
        print()
    
    recommendation = analysis.get('recommendation', {})
    if 'error' not in recommendation:
        print("💡 投资建议:")
        action = recommendation.get('action', 'UNKNOWN')
        action_colors = {'BUY': '🟢', 'HOLD': '🟡', 'WATCH': '🟠', 'AVOID': '🔴'}
        print(f"  操作建议: {action_colors.get(action, '⚪')} {action}")
        print(f"  信心度: {recommendation.get('confidence', 0):.1%}")
        print(f"  理由: {recommendation.get('reason', 'N/A')}")
        print(f"  风险提示: {recommendation.get('risk_warning', 'N/A')}")
        print()
    
    trading = analysis.get('trading_advice', {})
    if 'error' not in trading and 'advice' in trading:
        advice = trading['advice']
        if 'error' not in advice and 'entry_strategies' in advice:
            print("🎯 具体交易建议:")
            print(f"  最新信号: {trading.get('latest_signal_state', 'N/A')} ({trading.get('latest_signal_date', 'N/A')})")
            
            strategies = advice.get('entry_strategies', [])
            if strategies:
                strategy = strategies[0]
                print(f"  入场策略: {strategy.get('strategy', 'N/A')}")
                print(f"  目标价位1: ¥{strategy.get('entry_price_1', 0):.2f}")
                print(f"  目标价位2: ¥{strategy.get('entry_price_2', 0):.2f}")
                print(f"  仓位配置: {strategy.get('position_allocation', 'N/A')}")
            
            risk_mgmt = advice.get('risk_management', {})
            if 'stop_loss_levels' in risk_mgmt:
                stops = risk_mgmt['stop_loss_levels']
                print(f"  建议止损: ¥{stops.get('moderate', 'N/A'):.2f}")
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
    """单只股票分析工作函数（用于多进程）"""
    try:
        analyzer = EnhancedTradingAnalyzer()
        result = analyzer.analyze_stock_comprehensive(stock_code, use_optimized_params)
        return stock_code, result
    except Exception as e:
        return stock_code, {'error': f'分析失败: {e}'}

def _display_deep_scan_results(results, stock_codes):
    """显示深度扫描结果统计"""
    valid_results = {k: v for k, v in results.items() if 'error' not in v}
    a_grade_stocks = [k for k, v in valid_results.items() if v.get('overall_score', {}).get('grade') == 'A']
    price_evaluated_stocks = [k for k, v in valid_results.items() if 'price_evaluation' in v and 'error' not in v.get('price_evaluation', {})]
    buy_recommendations = [k for k, v in valid_results.items() if v.get('recommendation', {}).get('action') == 'BUY']
    
    print("\n" + "=" * 80)
    print("🎉 深度扫描结果汇总:")
    print("-" * 80)
    print(f"📊 深度分析成功: {len(valid_results)}/{len(stock_codes)}")
    print(f"🏆 A级股票发现: {len(a_grade_stocks)}")
    print(f"💰 价格评估完成: {len(price_evaluated_stocks)}")
    print(f"🟢 买入推荐: {len(buy_recommendations)}")
    
    if a_grade_stocks:
        print(f"\n🌟 A级股票列表:")
        a_grade_stocks_sorted = sorted(
            [s for s in a_grade_stocks if s in valid_results and valid_results[s].get('overall_score')],
            key=lambda s: valid_results[s]['overall_score'].get('total_score', 0),
            reverse=True
        )
        for stock_code in a_grade_stocks_sorted:
            result = valid_results[stock_code]
            score = result['overall_score']['total_score']
            price = result['basic_analysis']['current_price']
            action = result['recommendation']['action']
            confidence = result['recommendation']['confidence']
            price_eval_mark = " 💰" if stock_code in price_evaluated_stocks else ""
            print(f"  🏆 {stock_code}: {score:.1f}分, ¥{price:.2f}, {action} (信心度: {confidence:.1%}){price_eval_mark}")
    print("=" * 80 + "\n")

def analyze_multiple_stocks(stock_codes, use_optimized_params=True, max_workers=None):
    """
    【多进程V2最终优化版】并行分析多只股票，并对结果处理和I/O进行二次并行/异步优化。
    """
    if max_workers is None:
        try:
            max_workers = os.cpu_count() or 4
        except NotImplementedError:
            max_workers = 4
        print(f"🖥️ 未指定工作进程数，将自动使用所有可用的CPU核心: {max_workers}")
    
    print(f"🚀 启动多进程批量分析 {len(stock_codes)} 只股票 (进程数: {max_workers})")
    
    results = {}
    completed_count = 0
    total_count = len(stock_codes)
    a_grade_stocks_to_evaluate = []

    # 阶段一：使用多进程并行执行CPU密集型的核心分析
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_to_stock = {
            executor.submit(analyze_single_stock_worker, stock_code, use_optimized_params): stock_code 
            for stock_code in stock_codes
        }
        
        for future in as_completed(future_to_stock):
            stock_code = future_to_stock[future]
            completed_count += 1
            try:
                stock_code, result = future.result()
                results[stock_code] = result
                
                if 'error' not in result:
                    score = result.get('overall_score', {}).get('total_score', 0)
                    grade = result.get('overall_score', {}).get('grade', 'N/A')
                    action = result.get('recommendation', {}).get('action', 'N/A')
                    print(f"✅ [{completed_count:>{len(str(total_count))}}/{total_count}] {stock_code}: 评分 {score:.1f} ({grade}级), 建议 {action}")

                    # 收集A级股票以待后续统一处理
                    if grade == 'A':
                        a_grade_stocks_to_evaluate.append((stock_code, result))
                else:
                    print(f"❌ [{completed_count:>{len(str(total_count))}}/{total_count}] {stock_code}: {result['error']}")
            except Exception as e:
                print(f"❌ [{completed_count:>{len(str(total_count))}}/{total_count}] {stock_code}: 处理任务时发生严重异常 -> {e}")
                results[stock_code] = {'error': f'处理异常: {e}'}

    # 阶段二：使用多线程并行处理I/O密集型的A级股票价格评估
    if a_grade_stocks_to_evaluate:
        print(f"\n🔄 开始并行处理 {len(a_grade_stocks_to_evaluate)} 只A级股票的价格评估...")
        with ThreadPoolExecutor(max_workers=max(max_workers, 8)) as executor:
            future_to_eval = {
                executor.submit(perform_price_evaluation, stock_code, analysis_result): stock_code
                for stock_code, analysis_result in a_grade_stocks_to_evaluate
            }

            for future in as_completed(future_to_eval):
                stock_code = future_to_eval[future]
                try:
                    price_evaluation_result = future.result()
                    if 'error' not in price_evaluation_result:
                        results[stock_code]['price_evaluation'] = price_evaluation_result
                        print(f"💰 {stock_code} A级股票价格评估完成")
                    else:
                        print(f"❌ {stock_code} A级股票价格评估失败: {price_evaluation_result['error']}")
                except Exception as e:
                    print(f"❌ {stock_code} 处理价格评估时发生严重异常: {e}")

    # 阶段三：显示最终结果，并异步化文件写入操作
    _display_deep_scan_results(results, stock_codes)

    def save_reports_async(final_results, codes):
        """在后台线程中保存报告的函数"""
        print("\n✍️ 正在后台保存详细报告和JSON文件...")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = "data/result/ENHANCED_ANALYSIS"
        os.makedirs(output_dir, exist_ok=True)
        
        output_file = f"{output_dir}/enhanced_analysis_{timestamp}.json"
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(final_results, f, ensure_ascii=False, indent=2, default=str)
            print(f"📄 详细结果已保存到: {output_file}")
        except Exception as e:
            print(f"❌ 保存JSON文件失败: {e}")

        report_file = f"{output_dir}/enhanced_analysis_report_{timestamp}.txt"
        try:
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(f"增强分析报告 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 80 + "\n\n")
                
                valid_results = {k: v for k, v in final_results.items() if 'error' not in v and v.get('overall_score')}
                f.write(f"分析股票总数: {len(codes)}\n")
                f.write(f"成功分析数量: {len(valid_results)}\n")
                f.write(f"失败分析数量: {len(codes) - len(valid_results)}\n\n")
                
                if valid_results:
                    sorted_stocks = sorted(
                        valid_results.items(),
                        key=lambda x: x[1]['overall_score'].get('total_score', 0),
                        reverse=True
                    )
                    
                    f.write("股票排名 (按综合评分):\n")
                    f.write("-" * 50 + "\n")
                    for i, (stock_code, result) in enumerate(sorted_stocks, 1):
                        score = result['overall_score']['total_score']
                        grade = result['overall_score']['grade']
                        action = result['recommendation']['action']
                        confidence = result['recommendation']['confidence']
                        f.write(f"{i:2d}. {stock_code:<10} | {score:5.1f}分 ({grade}级) | 建议: {action:<5} (信心度: {confidence:.1%})\n")
                    
                    f.write("\n" + "=" * 50 + "\n")
                    f.write("推荐买入股票 (BUY建议 & 评分>=70):\n")
                    f.write("-" * 50 + "\n")
                    
                    buy_recs = [
                        (code, res) for code, res in sorted_stocks
                        if res['recommendation']['action'] == 'BUY' and res['overall_score']['total_score'] >= 70
                    ]
                    
                    if buy_recs:
                        for code, result in buy_recs:
                            score = result['overall_score']['total_score']
                            price = result['basic_analysis']['current_price']
                            change = result['basic_analysis']['price_change_30d']
                            f.write(f"  - {code:<10}: {score:.1f}分, 当前价 ¥{price:<7.2f}, 30日涨跌 {change:+.1%}\n")
                    else:
                        f.write("  暂无符合条件的推荐股票\n")
            print(f"📄 分析报告已保存到: {report_file}")
        except Exception as e:
            print(f"❌ 保存TXT报告失败: {e}")
        
    report_thread = threading.Thread(target=save_reports_async, args=(results, stock_codes))
    report_thread.start()
    
    return results

def get_sample_stock_codes():
    """获取样本股票代码"""
    return [
        'sh000001', 'sz000001', 'sh600000', 'sz000002', 'sh600036', 
        'sz000858', 'sh600519', 'sz000725', 'sh600276', 'sz002415'
    ]

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("使用方法:")
        print("  python run_enhanced_screening.py <股票代码>                    # 分析单只股票")
        print("  python run_enhanced_screening.py batch <股票代码1> <股票代码2>...  # [多进程]批量分析")
        print("  python run_enhanced_screening.py sample                        # [多进程]分析样本股票")
        print("  python run_enhanced_screening.py --no-optimize <股票代码>       # 不使用参数优化")
        print("\n示例:")
        print("  python run_enhanced_screening.py sh600519")
        print("  python run_enhanced_screening.py batch sh600519 sz000858")
        print("  python run_enhanced_screening.py sample")
        return

    start_time = time.time()
    use_optimized_params = '--no-optimize' not in sys.argv
    
    if sys.argv[1] == 'sample':
        stock_codes = get_sample_stock_codes()
        print(f"分析 {len(stock_codes)} 只样本股票...")
        analyze_multiple_stocks(stock_codes, use_optimized_params)
        
    elif sys.argv[1] == 'batch':
        stock_codes = [code.lower() for code in sys.argv[2:] if not code.startswith('--')]
        if not stock_codes:
            print("❌ 'batch'模式需要至少一个股票代码。")
            return
        print(f"批量分析 {len(stock_codes)} 只股票...")
        analyze_multiple_stocks(stock_codes, use_optimized_params)
        
    else:
        stock_code = [arg for arg in sys.argv[1:] if not arg.startswith('--')][0].lower()
        result = analyze_single_stock(stock_code, use_optimized_params)
        if 'error' not in result:
            print(f"\n🎉 {stock_code} 分析完成！")
            score = result['overall_score']['total_score']
            grade = result['overall_score']['grade']
            action = result['recommendation']['action']
            print(f"📊 综合评分: {score:.1f}分 ({grade}级)")
            print(f"💡 投资建议: {action}")

    end_time = time.time()
    print(f"\n⏱️ 主程序耗时: {end_time - start_time:.2f} 秒 (注意: 文件保存可能仍在后台进行)")

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()