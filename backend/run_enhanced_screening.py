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
# 修改点：引入ProcessPoolExecutor和ThreadPoolExecutor
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
import multiprocessing # 修改点：引入multiprocessing模块
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
        
        # 返回股票代码和评估结果以便于映射
        return stock_code, price_evaluation
        
    except Exception as e:
        return stock_code, {'error': f'价格评估失败: {e}'}

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
            except (json.JSONDecodeError, IOError):
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
    """单只股票分析工作函数（用于多线程/多进程）"""
    try:
        analyzer = EnhancedTradingAnalyzer()
        result = analyzer.analyze_stock_comprehensive(stock_code, use_optimized_params)
        return stock_code, result
    except Exception as e:
        return stock_code, {'error': f'分析失败: {e}'}

def analyze_multiple_stocks(stock_codes, use_optimized_params=True, max_workers=None):
    """多线程/多进程分析多只股票"""
    if max_workers is None:
        max_workers = os.cpu_count() or 4
    return deep_scan_stocks(stock_codes, use_optimized_params, max_workers)

def _display_deep_scan_results(results, stock_codes):
    """显示深度扫描结果统计"""
    valid_results = {k: v for k, v in results.items() if 'error' not in v}
    a_grade_stocks = [k for k, v in valid_results.items() if v.get('overall_score', {}).get('grade') == 'A']
    price_evaluated_stocks = [k for k, v in valid_results.items() if 'price_evaluation' in v and 'error' not in v.get('price_evaluation', {})]
    buy_recommendations = [k for k, v in valid_results.items() if v.get('recommendation', {}).get('action') == 'BUY']
    
    print(f"\n🎉 深度扫描结果:")
    print(f"📊 深度分析成功: {len(valid_results)}/{len(stock_codes)}")
    print(f"🏆 A级股票发现: {len(a_grade_stocks)}")
    print(f"💰 价格评估完成: {len(price_evaluated_stocks)}")
    print(f"🟢 买入推荐: {len(buy_recommendations)}")
    
    if a_grade_stocks:
        print(f"\n🌟 A级股票列表:")
        sorted_a_grade = sorted(
            [item for item in valid_results.items() if item[0] in a_grade_stocks],
            key=lambda item: item[1]['overall_score']['total_score'],
            reverse=True
        )
        for stock_code, result in sorted_a_grade:
            score = result['overall_score']['total_score']
            price = result['basic_analysis']['current_price']
            action = result['recommendation']['action']
            confidence = result['recommendation']['confidence']
            price_eval_mark = " 💰" if 'price_evaluation' in result and 'error' not in result.get('price_evaluation', {}) else ""
            print(f"  🏆 {stock_code}: {score:.1f}分, ¥{price:.2f}, {action} ({confidence:.1%}){price_eval_mark}")

def _save_reports_async(results, stock_codes):
    """在后台线程中保存JSON和TXT报告"""
    print("\n后台任务: 开始生成并保存报告...")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 保存详细结果JSON文件
    try:
        output_file = f"data/result/ENHANCED_ANALYSIS/enhanced_analysis_{timestamp}.json"
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)
        print(f"📄 详细结果已保存到: {output_file}")
    except Exception as e:
        print(f"❌ 保存详细JSON报告失败: {e}")

    # 生成并保存简化报告TXT文件
    try:
        report_file = f"data/result/ENHANCED_ANALYSIS/enhanced_analysis_{timestamp}.txt"
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(f"增强分析报告 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")
            
            valid_results = {k: v for k, v in results.items() if 'error' not in v}
            f.write(f"分析股票总数: {len(stock_codes)}\n")
            f.write(f"成功分析数量: {len(valid_results)}\n")
            f.write(f"失败分析数量: {len(stock_codes) - len(valid_results)}\n\n")
            
            if valid_results:
                sorted_stocks = sorted(
                    valid_results.items(),
                    key=lambda item: item[1].get('overall_score', {}).get('total_score', 0),
                    reverse=True
                )
                
                f.write("股票排名 (按综合评分):\n")
                f.write("-" * 50 + "\n")
                
                for i, (stock_code, result) in enumerate(sorted_stocks, 1):
                    score_data = result.get('overall_score', {})
                    rec_data = result.get('recommendation', {})
                    score = score_data.get('total_score', 0)
                    grade = score_data.get('grade', 'N/A')
                    action = rec_data.get('action', 'N/A')
                    confidence = rec_data.get('confidence', 0)
                    f.write(f"{i:2d}. {stock_code}: {score:5.1f}分 ({grade}级) - {action} (信心度: {confidence:.1%})\n")
                
                f.write("\n" + "=" * 50 + "\n")
                f.write("推荐买入股票 (评分>=70分):\n")
                f.write("-" * 30 + "\n")
                
                buy_recommendations = [
                    (code, res) for code, res in sorted_stocks
                    if res.get('recommendation', {}).get('action') == 'BUY' and res.get('overall_score', {}).get('total_score', 0) >= 70
                ]
                
                if buy_recommendations:
                    for code, result in buy_recommendations:
                        score = result['overall_score']['total_score']
                        basic = result['basic_analysis']
                        f.write(f"{code}: {score:.1f}分, 当前价格: ¥{basic['current_price']:.2f}, ")
                        f.write(f"30天涨跌: {basic['price_change_30d']:+.1%}\n")
                else:
                    f.write("暂无符合条件的推荐股票\n")
        print(f"📄 分析报告已保存到: {report_file}")
    except Exception as e:
        print(f"❌ 保存简化TXT报告失败: {e}")

    print("后台任务: 报告保存完成。")

def deep_scan_stocks(stock_codes, use_optimized_params=True, max_workers=8):
    """
    使用多进程和多线程并行执行股票分析、评估和报告。
    1. 使用 ProcessPoolExecutor 并行执行核心分析。
    2. 使用 ThreadPoolExecutor 并行执行A级股票的价格评估。
    3. 异步执行最终报告的保存。
    """
    results = {}
    
    # --- 核心分析并行化 (Phase 1: Core Analysis with ProcessPoolExecutor) ---
    print(f"🚀 [阶段 1/3] 开始核心分析 {len(stock_codes)} 只股票 (使用 {max_workers} 个进程)...")
    completed_count = 0
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_to_stock = {
            executor.submit(analyze_single_stock_worker, stock, use_optimized_params): stock 
            for stock in stock_codes
        }
        
        for future in as_completed(future_to_stock):
            stock_code = future_to_stock[future]
            completed_count += 1
            try:
                _, result = future.result()
                results[stock_code] = result
                
                if 'error' not in result:
                    grade = result.get('overall_score', {}).get('grade', 'N/A')
                    action = result.get('recommendation', {}).get('action', 'N/A')
                    print(f"  ✅ [{completed_count}/{len(stock_codes)}] 分析完成: {stock_code} (等级: {grade}, 建议: {action})")
                else:
                    print(f"  ❌ [{completed_count}/{len(stock_codes)}] 分析失败: {stock_code} - {result['error']}")
            except Exception as e:
                results[stock_code] = {'error': f'处理未来对象时发生未知异常: {e}'}
                print(f"  💥 [{completed_count}/{len(stock_codes)}] 处理异常: {stock_code} -> {e}")

    # --- A股评估并行化 (Phase 2: A-Grade Evaluation with ThreadPoolExecutor) ---
    print("\n🚀 [阶段 2/3] 核心分析完成. 开始并行评估A级股票...")
    a_grade_stocks_to_evaluate = {
        code: res for code, res in results.items() 
        if 'error' not in res and res.get('overall_score', {}).get('grade') == 'A'
    }

    if not a_grade_stocks_to_evaluate:
        print("  ℹ️ 未发现A级股票，跳过价格评估。")
    else:
        print(f"  发现 {len(a_grade_stocks_to_evaluate)} 只A级股票，开始进行价格评估...")
        # 使用线程池进行I/O密集型的价格评估和文件保存
        with ThreadPoolExecutor(max_workers=min(16, len(a_grade_stocks_to_evaluate) or 1)) as executor:
            future_to_eval = {
                executor.submit(perform_price_evaluation, stock_code, analysis_result): stock_code
                for stock_code, analysis_result in a_grade_stocks_to_evaluate.items()
            }

            for future in as_completed(future_to_eval):
                evaluated_stock_code = future_to_eval[future]
                try:
                    _, price_evaluation = future.result()
                    results[evaluated_stock_code]['price_evaluation'] = price_evaluation
                    if 'error' not in price_evaluation:
                        print(f"    💰 {evaluated_stock_code} A级股票价格评估完成")
                    else:
                        print(f"    ❌ {evaluated_stock_code} A级股票价格评估失败: {price_evaluation['error']}")
                except Exception as e:
                    print(f"    💥 {evaluated_stock_code} 处理价格评估时发生异常: {e}")
                    results[evaluated_stock_code]['price_evaluation'] = {'error': f'评估执行异常: {e}'}

    # --- 报告生成异步化 (Phase 3: Display Results and Async Report Saving) ---
    print("\n🚀 [阶段 3/3] 所有分析和评估完成.")
    
    # 立即向控制台显示结果摘要
    _display_deep_scan_results(results, stock_codes)

    # 启动后台线程以保存文件
    report_thread = threading.Thread(
        target=_save_reports_async, 
        args=(results.copy(), stock_codes) # 传递副本以避免潜在的竞争条件
    )
    report_thread.start()
    
    print("\n✅ 主流程完成. 报告正在后台生成中，您可以安全退出程序。")
    
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
            stock_codes = [code.lower() for code in sys.argv[3:]] if len(sys.argv) > 2 and sys.argv[2] == '--no-optimize' else [code.lower() for code in sys.argv[2:] if code != '--no-optimize']
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
    # 为多进程提供跨平台兼容性支持
    multiprocessing.freeze_support()
    main()