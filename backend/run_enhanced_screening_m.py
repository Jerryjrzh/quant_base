import threading # 导入threading模块

def analyze_multiple_stocks(stock_codes, use_optimized_params=True, max_workers=None):
    """
    【多进程优化 V2】并行分析多只股票，并对结果处理和I/O进行二次并行/异步优化。
    """
    # 确定工作进程数
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
    
    # 修改点 1：创建一个列表，用于收集需要进行价格评估的A级股票
    a_grade_stocks_to_evaluate = []

    # --- 阶段一：并行进行核心分析 ---
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

                    # 修改点 2：不立即评估A级股票，而是先将其和初步结果存起来
                    if grade == 'A':
                        a_grade_stocks_to_evaluate.append((stock_code, result))
                else:
                    print(f"❌ [{completed_count:>{len(str(total_count))}}/{total_count}] {stock_code}: {result['error']}")
            except Exception as e:
                print(f"❌ [{completed_count:>{len(str(total_count))}}/{total_count}] {stock_code}: 处理任务时发生严重异常 -> {e}")
                results[stock_code] = {'error': f'处理异常: {e}'}

    # --- 阶段二：并行处理A级股票的价格评估 ---
    if a_grade_stocks_to_evaluate:
        print(f"\n🔄 开始并行处理 {len(a_grade_stocks_to_evaluate)} 只A级股票的价格评估...")
        # 使用ThreadPoolExecutor，因为价格评估主要是I/O密集型操作（写文件）
        with ThreadPoolExecutor(max_workers=max(max_workers, 8)) as executor:
            # 提交价格评估任务
            future_to_eval = {
                executor.submit(perform_price_evaluation, stock_code, analysis_result): stock_code
                for stock_code, analysis_result in a_grade_stocks_to_evaluate
            }

            for future in as_completed(future_to_eval):
                stock_code = future_to_eval[future]
                try:
                    price_evaluation_result = future.result()
                    # 将评估结果合并回主结果字典
                    if 'error' not in price_evaluation_result:
                        results[stock_code]['price_evaluation'] = price_evaluation_result
                        print(f"💰 {stock_code} A级股票价格评估完成")
                    else:
                        print(f"❌ {stock_code} A级股票价格评估失败: {price_evaluation_result['error']}")
                except Exception as e:
                    print(f"❌ {stock_code} 处理价格评估时发生严重异常: {e}")

    # --- 阶段三：显示最终结果，并将文件写入操作异步化 ---
    _display_deep_scan_results(results, stock_codes)

    def save_reports_async(final_results, codes):
        """用于在后台线程中保存报告的函数"""
        print("\n✍️ 正在后台保存详细报告和JSON文件...")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = "data/result/ENHANCED_ANALYSIS"
        os.makedirs(output_dir, exist_ok=True)
        
        # 保存详细JSON结果
        output_file = f"{output_dir}/enhanced_analysis_{timestamp}.json"
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(final_results, f, ensure_ascii=False, indent=2, default=str)
            print(f"📄 详细结果已保存到: {output_file}")
        except Exception as e:
            print(f"❌ 保存JSON文件失败: {e}")

        # 生成并保存简化TXT报告
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
        
    # 修改点 3：创建一个后台线程来执行文件保存，避免阻塞主程序
    report_thread = threading.Thread(target=save_reports_async, args=(results, stock_codes))
    report_thread.start()
    
    return results