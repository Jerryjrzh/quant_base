"""
多时间框架和多策略分析器
针对最近筛选的股票进行深度分析，发现不同策略和时间框架下的机会
"""
import os
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict
import data_loader
import indicators
import strategies
import backtester

class MultiTimeframeAnalyzer:
    def __init__(self):
        self.base_path = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
        self.result_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'result')
        
        # 定义要测试的策略
        self.strategies = {
            'TRIPLE_CROSS': strategies.apply_triple_cross,
            'PRE_CROSS': strategies.apply_pre_cross,
            'MACD_ZERO_AXIS': strategies.apply_macd_zero_axis_strategy
        }
        
        # 定义交叉阶段
        self.cross_stages = ['PRE_CROSS', 'CROSS_MOMENT', 'POST_CROSS', 'BOTTOM_FORMATION']
    
    def load_recent_screening_results(self, days_back=10):
        """加载最近N天的筛选结果"""
        all_results = []
        
        for strategy_name in self.strategies.keys():
            strategy_dir = os.path.join(self.result_path, strategy_name)
            if not os.path.exists(strategy_dir):
                continue
            
            # 查找最近的结果文件
            result_files = []
            for file in os.listdir(strategy_dir):
                if file.startswith('signals_summary') and file.endswith('.json'):
                    file_path = os.path.join(strategy_dir, file)
                    mtime = os.path.getmtime(file_path)
                    result_files.append((file_path, mtime, strategy_name))
            
            # 按时间排序，取最近的几个
            result_files.sort(key=lambda x: x[1], reverse=True)
            
            for file_path, mtime, strategy in result_files[:days_back]:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            for item in data:
                                item['source_strategy'] = strategy
                                item['scan_time'] = datetime.fromtimestamp(mtime)
                            all_results.extend(data)
                except Exception as e:
                    print(f"读取文件 {file_path} 失败: {e}")
        
        return all_results
    
    def analyze_cross_stage_timing(self, stock_code, df):
        """分析不同交叉阶段的最佳入场时机"""
        try:
            # 计算技术指标
            macd_values = indicators.calculate_macd(df)
            dif, dea = macd_values[0], macd_values[1]
            kdj_values = indicators.calculate_kdj(df)
            k, d, j = kdj_values[0], kdj_values[1], kdj_values[2]
            rsi6 = indicators.calculate_rsi(df, 6)
            rsi12 = indicators.calculate_rsi(df, 12)
            
            # 识别所有交叉阶段的时点
            stage_points = self._identify_all_cross_stages(df, dif, dea, k, d, rsi6, rsi12)
            
            # 分析每个阶段的后续表现
            stage_analysis = {}
            for stage_name, points in stage_points.items():
                if not points:
                    continue
                
                performances = []
                for point_idx in points:
                    perf = self._analyze_future_performance(df, point_idx)
                    if perf:
                        perf['stage'] = stage_name
                        perf['entry_date'] = df.iloc[point_idx]['date']
                        performances.append(perf)
                
                if performances:
                    stage_analysis[stage_name] = {
                        'total_occurrences': len(performances),
                        'avg_max_gain': np.mean([p['max_gain'] for p in performances]),
                        'avg_max_loss': np.mean([p['max_loss'] for p in performances]),
                        'avg_days_to_peak': np.mean([p['days_to_peak'] for p in performances if p['days_to_peak'] > 0]),
                        'success_rate': len([p for p in performances if p['max_gain'] > 0.05]) / len(performances),
                        'risk_reward_ratio': self._calculate_risk_reward_ratio(performances),
                        'best_entries': sorted(performances, key=lambda x: x['max_gain'], reverse=True)[:3]
                    }
            
            return stage_analysis
            
        except Exception as e:
            print(f"分析{stock_code}交叉阶段时机失败: {e}")
            return {}
    
    def _identify_all_cross_stages(self, df, dif, dea, k, d, rsi6, rsi12):
        """识别所有交叉阶段的时点"""
        stages = {
            'PRE_CROSS': [],
            'CROSS_MOMENT': [],
            'POST_CROSS': [],
            'BOTTOM_FORMATION': []
        }
        
        for i in range(5, len(df) - 5):  # 留出前后缓冲区
            try:
                # PRE_CROSS: 指标接近但未交叉，且呈现向上趋势
                macd_approaching = (
                    dif.iloc[i] < dea.iloc[i] and  # 尚未金叉
                    dif.iloc[i] - dea.iloc[i] > dif.iloc[i-1] - dea.iloc[i-1] and  # 差值缩小
                    abs(dif.iloc[i] - dea.iloc[i]) < 0.03 and  # 接近交叉
                    dif.iloc[i] > dif.iloc[i-2]  # MACD上升趋势
                )
                
                kdj_approaching = (
                    k.iloc[i] < d.iloc[i] and
                    k.iloc[i] - d.iloc[i] > k.iloc[i-1] - d.iloc[i-1] and
                    abs(k.iloc[i] - d.iloc[i]) < 8 and
                    d.iloc[i] < 50  # 不在高位
                )
                
                if macd_approaching and kdj_approaching:
                    stages['PRE_CROSS'].append(i)
                
                # CROSS_MOMENT: 正在发生交叉
                macd_crossing = (dif.iloc[i-1] <= dea.iloc[i-1] and dif.iloc[i] > dea.iloc[i])
                kdj_crossing = (k.iloc[i-1] <= d.iloc[i-1] and k.iloc[i] > d.iloc[i])
                rsi_crossing = (rsi6.iloc[i-1] <= rsi12.iloc[i-1] and rsi6.iloc[i] > rsi12.iloc[i])
                
                cross_count = sum([macd_crossing, kdj_crossing, rsi_crossing])
                if cross_count >= 2:  # 至少两个指标同时交叉
                    stages['CROSS_MOMENT'].append(i)
                
                # POST_CROSS: 交叉后的确认阶段
                if i >= 3:
                    recent_macd_cross = any(
                        dif.iloc[j-1] <= dea.iloc[j-1] and dif.iloc[j] > dea.iloc[j]
                        for j in range(i-3, i)
                    )
                    
                    macd_maintained = dif.iloc[i] > dea.iloc[i]
                    kdj_maintained = k.iloc[i] > d.iloc[i]
                    
                    if recent_macd_cross and macd_maintained and kdj_maintained:
                        stages['POST_CROSS'].append(i)
                
                # BOTTOM_FORMATION: 多指标同时触底反弹
                macd_bottom = (
                    dif.iloc[i] < -0.05 and  # MACD在负值区域
                    dif.iloc[i] > dif.iloc[i-1] and  # 开始上升
                    dif.iloc[i-1] <= dif.iloc[i-2]  # 前一天是底部
                )
                
                kdj_bottom = (
                    d.iloc[i] < 25 and  # KDJ在低位
                    d.iloc[i] > d.iloc[i-1] and  # 开始上升
                    k.iloc[i] > k.iloc[i-1]  # K值也上升
                )
                
                rsi_bottom = (
                    rsi6.iloc[i] < 35 and  # RSI在低位
                    rsi6.iloc[i] > rsi6.iloc[i-1]  # 开始上升
                )
                
                bottom_signals = sum([macd_bottom, kdj_bottom, rsi_bottom])
                if bottom_signals >= 2:
                    stages['BOTTOM_FORMATION'].append(i)
                    
            except Exception as e:
                continue
        
        return stages
    
    def _analyze_future_performance(self, df, entry_idx, max_days=30):
        """分析入场点后的表现"""
        try:
            if entry_idx >= len(df) - 1:
                return None
            
            entry_price = df.iloc[entry_idx]['close']
            max_gain = 0
            max_loss = 0
            days_to_peak = 0
            days_to_trough = 0
            
            end_idx = min(entry_idx + max_days, len(df))
            
            for i in range(entry_idx + 1, end_idx):
                high_price = df.iloc[i]['high']
                low_price = df.iloc[i]['low']
                
                gain = (high_price - entry_price) / entry_price
                loss = (low_price - entry_price) / entry_price
                
                if gain > max_gain:
                    max_gain = gain
                    days_to_peak = i - entry_idx
                
                if loss < max_loss:
                    max_loss = loss
                    days_to_trough = i - entry_idx
            
            return {
                'max_gain': max_gain,
                'max_loss': max_loss,
                'days_to_peak': days_to_peak,
                'days_to_trough': days_to_trough,
                'entry_price': entry_price,
                'gain_loss_ratio': abs(max_gain / max_loss) if max_loss != 0 else float('inf')
            }
            
        except Exception as e:
            return None
    
    def _calculate_risk_reward_ratio(self, performances):
        """计算风险收益比"""
        try:
            gains = [p['max_gain'] for p in performances if p['max_gain'] > 0]
            losses = [abs(p['max_loss']) for p in performances if p['max_loss'] < 0]
            
            if not gains or not losses:
                return 0
            
            avg_gain = np.mean(gains)
            avg_loss = np.mean(losses)
            
            return avg_gain / avg_loss if avg_loss > 0 else float('inf')
            
        except:
            return 0
    
    def multi_strategy_comparison(self, stock_codes):
        """多策略对比分析"""
        comparison_results = {}
        
        for stock_code in stock_codes:
            print(f"分析 {stock_code} 的多策略表现...")
            
            # 加载股票数据
            df = self._load_stock_data(stock_code)
            if df is None:
                continue
            
            stock_results = {
                'stock_code': stock_code,
                'strategy_performance': {},
                'cross_stage_analysis': {},
                'best_strategy': None,
                'best_stage': None
            }
            
            # 测试每个策略
            for strategy_name, strategy_func in self.strategies.items():
                try:
                    signal_series = strategy_func(df)
                    if signal_series is not None:
                        # 执行回测
                        backtest_result = backtester.run_backtest(df, signal_series)
                        stock_results['strategy_performance'][strategy_name] = backtest_result
                        
                except Exception as e:
                    print(f"  {strategy_name} 策略测试失败: {e}")
                    stock_results['strategy_performance'][strategy_name] = {'error': str(e)}
            
            # 交叉阶段分析
            stage_analysis = self.analyze_cross_stage_timing(stock_code, df)
            stock_results['cross_stage_analysis'] = stage_analysis
            
            # 确定最佳策略和阶段
            best_strategy, best_stage = self._find_best_strategy_and_stage(
                stock_results['strategy_performance'], 
                stage_analysis
            )
            stock_results['best_strategy'] = best_strategy
            stock_results['best_stage'] = best_stage
            
            comparison_results[stock_code] = stock_results
        
        return comparison_results
    
    def _load_stock_data(self, stock_code):
        """加载股票数据"""
        try:
            if stock_code.startswith('sh'):
                market = 'sh'
            elif stock_code.startswith('sz'):
                market = 'sz'
            else:
                return None
            
            file_path = os.path.join(self.base_path, market, 'lday', f'{stock_code}.day')
            return data_loader.get_daily_data(file_path)
            
        except Exception as e:
            print(f"加载{stock_code}数据失败: {e}")
            return None
    
    def _find_best_strategy_and_stage(self, strategy_performance, stage_analysis):
        """找出最佳策略和最佳阶段"""
        best_strategy = None
        best_strategy_score = 0
        
        # 评估策略表现
        for strategy_name, result in strategy_performance.items():
            if 'error' in result or result.get('total_signals', 0) == 0:
                continue
            
            try:
                win_rate = float(result.get('win_rate', '0%').replace('%', ''))
                avg_profit = float(result.get('avg_max_profit', '0%').replace('%', ''))
                
                # 综合评分：胜率 * 0.6 + 收益率 * 0.4
                score = win_rate * 0.6 + avg_profit * 0.4
                
                if score > best_strategy_score:
                    best_strategy_score = score
                    best_strategy = strategy_name
                    
            except:
                continue
        
        # 评估阶段表现
        best_stage = None
        best_stage_score = 0
        
        for stage_name, stage_data in stage_analysis.items():
            success_rate = stage_data.get('success_rate', 0)
            avg_gain = stage_data.get('avg_max_gain', 0)
            risk_reward = stage_data.get('risk_reward_ratio', 0)
            
            # 综合评分：成功率 * 0.4 + 平均收益 * 0.3 + 风险收益比 * 0.3
            score = success_rate * 40 + avg_gain * 30 + min(risk_reward, 5) * 6
            
            if score > best_stage_score:
                best_stage_score = score
                best_stage = stage_name
        
        return best_strategy, best_stage
    
    def generate_comprehensive_report(self, analysis_results):
        """生成综合分析报告"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        
        # 创建输出目录
        output_dir = os.path.join(self.result_path, 'MULTI_TIMEFRAME_ANALYSIS')
        os.makedirs(output_dir, exist_ok=True)
        
        # 生成报告内容
        report = {
            'analysis_timestamp': timestamp,
            'summary': self._generate_summary(analysis_results),
            'strategy_ranking': self._rank_strategies(analysis_results),
            'stage_ranking': self._rank_stages(analysis_results),
            'individual_recommendations': self._generate_individual_recommendations(analysis_results),
            'market_insights': self._generate_market_insights(analysis_results)
        }
        
        # 保存JSON报告
        json_file = os.path.join(output_dir, f'multi_timeframe_analysis_{timestamp}.json')
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=4)
        
        # 保存文本报告
        text_file = os.path.join(output_dir, f'multi_timeframe_analysis_{timestamp}.txt')
        with open(text_file, 'w', encoding='utf-8') as f:
            self._write_comprehensive_text_report(f, report)
        
        return json_file, text_file, report
    
    def _generate_summary(self, analysis_results):
        """生成分析摘要"""
        total_stocks = len(analysis_results)
        strategy_success = defaultdict(list)
        stage_success = defaultdict(list)
        
        for stock_code, result in analysis_results.items():
            # 统计策略成功率
            for strategy, perf in result['strategy_performance'].items():
                if 'error' not in perf and perf.get('total_signals', 0) > 0:
                    win_rate = float(perf.get('win_rate', '0%').replace('%', ''))
                    strategy_success[strategy].append(win_rate)
            
            # 统计阶段成功率
            for stage, data in result['cross_stage_analysis'].items():
                success_rate = data.get('success_rate', 0)
                stage_success[stage].append(success_rate * 100)
        
        return {
            'total_stocks_analyzed': total_stocks,
            'avg_strategy_performance': {
                strategy: np.mean(rates) for strategy, rates in strategy_success.items()
            },
            'avg_stage_performance': {
                stage: np.mean(rates) for stage, rates in stage_success.items()
            }
        }
    
    def _rank_strategies(self, analysis_results):
        """策略排名"""
        strategy_scores = defaultdict(list)
        
        for result in analysis_results.values():
            for strategy, perf in result['strategy_performance'].items():
                if 'error' not in perf and perf.get('total_signals', 0) > 0:
                    try:
                        win_rate = float(perf.get('win_rate', '0%').replace('%', ''))
                        avg_profit = float(perf.get('avg_max_profit', '0%').replace('%', ''))
                        score = win_rate * 0.6 + avg_profit * 0.4
                        strategy_scores[strategy].append(score)
                    except:
                        continue
        
        ranking = []
        for strategy, scores in strategy_scores.items():
            if scores:
                ranking.append({
                    'strategy': strategy,
                    'avg_score': np.mean(scores),
                    'consistency': 1 - (np.std(scores) / np.mean(scores)) if np.mean(scores) > 0 else 0,
                    'sample_size': len(scores)
                })
        
        return sorted(ranking, key=lambda x: x['avg_score'], reverse=True)
    
    def _rank_stages(self, analysis_results):
        """阶段排名"""
        stage_scores = defaultdict(list)
        
        for result in analysis_results.values():
            for stage, data in result['cross_stage_analysis'].items():
                success_rate = data.get('success_rate', 0)
                avg_gain = data.get('avg_max_gain', 0)
                risk_reward = data.get('risk_reward_ratio', 0)
                
                score = success_rate * 40 + avg_gain * 30 + min(risk_reward, 5) * 6
                stage_scores[stage].append(score)
        
        ranking = []
        for stage, scores in stage_scores.items():
            if scores:
                ranking.append({
                    'stage': stage,
                    'avg_score': np.mean(scores),
                    'consistency': 1 - (np.std(scores) / np.mean(scores)) if np.mean(scores) > 0 else 0,
                    'sample_size': len(scores)
                })
        
        return sorted(ranking, key=lambda x: x['avg_score'], reverse=True)
    
    def _generate_individual_recommendations(self, analysis_results):
        """生成个股建议"""
        recommendations = {}
        
        for stock_code, result in analysis_results.items():
            best_strategy = result.get('best_strategy')
            best_stage = result.get('best_stage')
            
            # 获取最佳策略的表现
            strategy_perf = result['strategy_performance'].get(best_strategy, {})
            stage_perf = result['cross_stage_analysis'].get(best_stage, {})
            
            recommendation = "观望"
            confidence = "低"
            
            if strategy_perf and 'error' not in strategy_perf:
                try:
                    win_rate = float(strategy_perf.get('win_rate', '0%').replace('%', ''))
                    avg_profit = float(strategy_perf.get('avg_max_profit', '0%').replace('%', ''))
                    
                    if win_rate >= 60 and avg_profit >= 20:
                        recommendation = "强烈推荐"
                        confidence = "高"
                    elif win_rate >= 50 and avg_profit >= 15:
                        recommendation = "推荐"
                        confidence = "中"
                    elif win_rate >= 40 and avg_profit >= 10:
                        recommendation = "谨慎考虑"
                        confidence = "中"
                except:
                    pass
            
            recommendations[stock_code] = {
                'recommendation': recommendation,
                'confidence': confidence,
                'best_strategy': best_strategy,
                'best_stage': best_stage,
                'strategy_win_rate': strategy_perf.get('win_rate', 'N/A'),
                'strategy_avg_profit': strategy_perf.get('avg_max_profit', 'N/A'),
                'stage_success_rate': f"{stage_perf.get('success_rate', 0):.1%}" if stage_perf else 'N/A'
            }
        
        return recommendations
    
    def _generate_market_insights(self, analysis_results):
        """生成市场洞察"""
        insights = []
        
        # 分析最佳策略分布
        best_strategies = [r.get('best_strategy') for r in analysis_results.values() if r.get('best_strategy')]
        if best_strategies:
            from collections import Counter
            strategy_counter = Counter(best_strategies)
            most_common_strategy = strategy_counter.most_common(1)[0]
            insights.append(f"最受欢迎的策略是 {most_common_strategy[0]}，适用于 {most_common_strategy[1]} 只股票")
        
        # 分析最佳阶段分布
        best_stages = [r.get('best_stage') for r in analysis_results.values() if r.get('best_stage')]
        if best_stages:
            from collections import Counter
            stage_counter = Counter(best_stages)
            most_common_stage = stage_counter.most_common(1)[0]
            insights.append(f"最佳入场阶段是 {most_common_stage[0]}，出现在 {most_common_stage[1]} 只股票中")
        
        return insights
    
    def _write_comprehensive_text_report(self, f, report):
        """写入综合文本报告"""
        f.write("=" * 100 + "\n")
        f.write("多时间框架和多策略综合分析报告\n")
        f.write(f"生成时间: {report['analysis_timestamp']}\n")
        f.write("=" * 100 + "\n\n")
        
        # 分析摘要
        summary = report['summary']
        f.write("📊 分析摘要\n")
        f.write("-" * 50 + "\n")
        f.write(f"分析股票总数: {summary['total_stocks_analyzed']}\n\n")
        
        f.write("策略平均表现:\n")
        for strategy, perf in summary['avg_strategy_performance'].items():
            f.write(f"  {strategy}: {perf:.1f}%\n")
        
        f.write("\n阶段平均表现:\n")
        for stage, perf in summary['avg_stage_performance'].items():
            f.write(f"  {stage}: {perf:.1f}%\n")
        
        # 策略排名
        f.write(f"\n\n🏆 策略排名\n")
        f.write("-" * 50 + "\n")
        for i, strategy in enumerate(report['strategy_ranking'], 1):
            f.write(f"{i}. {strategy['strategy']}\n")
            f.write(f"   综合评分: {strategy['avg_score']:.1f}\n")
            f.write(f"   一致性: {strategy['consistency']:.2f}\n")
            f.write(f"   样本数: {strategy['sample_size']}\n\n")
        
        # 阶段排名
        f.write(f"🎯 最佳入场阶段排名\n")
        f.write("-" * 50 + "\n")
        for i, stage in enumerate(report['stage_ranking'], 1):
            f.write(f"{i}. {stage['stage']}\n")
            f.write(f"   综合评分: {stage['avg_score']:.1f}\n")
            f.write(f"   一致性: {stage['consistency']:.2f}\n")
            f.write(f"   样本数: {stage['sample_size']}\n\n")
        
        # 个股建议
        f.write(f"💡 个股投资建议\n")
        f.write("-" * 50 + "\n")
        for stock_code, rec in report['individual_recommendations'].items():
            f.write(f"{stock_code}: {rec['recommendation']} (置信度: {rec['confidence']})\n")
            f.write(f"   最佳策略: {rec['best_strategy']} (胜率: {rec['strategy_win_rate']})\n")
            f.write(f"   最佳阶段: {rec['best_stage']} (成功率: {rec['stage_success_rate']})\n\n")
        
        # 市场洞察
        f.write(f"🔍 市场洞察\n")
        f.write("-" * 50 + "\n")
        for insight in report['market_insights']:
            f.write(f"• {insight}\n")

def main():
    """主函数"""
    analyzer = MultiTimeframeAnalyzer()
    
    print("=== 多时间框架和多策略分析 ===")
    
    # 1. 加载最近的筛选结果
    print("1. 加载最近10次筛选结果...")
    recent_results = analyzer.load_recent_screening_results(10)
    print(f"   找到 {len(recent_results)} 个历史信号")
    
    # 2. 提取股票代码（去重并取前20个）
    stock_codes = list(set([r['stock_code'] for r in recent_results]))[:20]
    print(f"2. 选择前20个股票进行深度分析...")
    
    # 3. 多策略对比分析
    print("3. 执行多策略对比分析...")
    analysis_results = analyzer.multi_strategy_comparison(stock_codes)
    
    # 4. 生成综合报告
    print("4. 生成综合分析报告...")
    json_file, text_file, report = analyzer.generate_comprehensive_report(analysis_results)
    
    print(f"\n分析完成！")
    print(f"JSON报告: {json_file}")
    print(f"文本报告: {text_file}")
    
    # 5. 显示关键发现
    print(f"\n=== 关键发现 ===")
    if report['strategy_ranking']:
        best_strategy = report['strategy_ranking'][0]
        print(f"最佳策略: {best_strategy['strategy']} (评分: {best_strategy['avg_score']:.1f})")
    
    if report['stage_ranking']:
        best_stage = report['stage_ranking'][0]
        print(f"最佳阶段: {best_stage['stage']} (评分: {best_stage['avg_score']:.1f})")
    
    # 显示推荐股票
    strong_recommendations = [
        stock for stock, rec in report['individual_recommendations'].items()
        if rec['recommendation'] in ['强烈推荐', '推荐']
    ]
    
    if strong_recommendations:
        print(f"推荐关注股票: {', '.join(strong_recommendations[:5])}")

if __name__ == '__main__':
    main()