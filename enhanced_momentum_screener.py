#!/usr/bin/env python3
"""
增强版强势股筛选系统
整合季度回测、强势分析、多周期验证的完整筛选流程
"""

import os
import sys
import json
import argparse
from datetime import datetime
from typing import List, Dict, Optional

# 添加backend路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from momentum_strength_analyzer import MomentumStrengthAnalyzer, MomentumConfig
from multi_timeframe_validator import MultiTimeframeValidator, TimeframeConfig

class EnhancedMomentumScreener:
    """增强版强势股筛选器"""
    
    def __init__(self):
        self.momentum_analyzer = None
        self.timeframe_validator = None
        self.quarterly_backtester = None
        
        # 筛选结果
        self.quarterly_pool = []
        self.momentum_results = []
        self.validation_results = []
        self.final_recommendations = []
    
    def load_quarterly_results(self, quarterly_file: str, min_profit_threshold: float = 0.0) -> List[Dict]:
        """加载季度回测结果中的股票池，并进行盈利筛选"""
        try:
            with open(quarterly_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 提取核心股票池和推荐交易
            if 'strategy' in data and 'core_pool' in data['strategy']:
                core_pool = data['strategy']['core_pool']
                recommended_trades = data['strategy'].get('recommended_trades', [])
                
                print(f"✅ 从季度回测结果加载了 {len(core_pool)} 只股票")
                print(f"   文件: {quarterly_file}")
                
                # 创建交易收益映射
                trade_returns = {}
                for trade in recommended_trades:
                    symbol = trade['symbol']
                    return_rate = trade.get('return_rate', 0)
                    
                    # 如果同一股票有多个交易记录，取最好的收益率
                    if symbol not in trade_returns or return_rate > trade_returns[symbol]:
                        trade_returns[symbol] = return_rate
                
                # 进行盈利筛选
                profitable_stocks = []
                filtered_stocks = []
                
                for stock in core_pool:
                    symbol = stock['symbol']
                    max_gain = stock.get('max_gain', 0)
                    
                    # 获取实际交易收益率，如果没有则使用最大涨幅
                    actual_return = trade_returns.get(symbol, max_gain)
                    
                    stock_info = {
                        'symbol': symbol,
                        'max_gain': max_gain,
                        'actual_return': actual_return,
                        'selection_price': stock.get('selection_price', 0),
                        'weekly_cross_confirmed': stock.get('weekly_cross_confirmed', False)
                    }
                    
                    # 应用盈利筛选条件
                    if actual_return >= min_profit_threshold:
                        profitable_stocks.append(stock_info)
                    else:
                        filtered_stocks.append(stock_info)
                
                # 按实际收益率排序
                profitable_stocks.sort(key=lambda x: x['actual_return'], reverse=True)
                
                print(f"📊 盈利筛选结果:")
                print(f"   原始股票池: {len(core_pool)} 只")
                print(f"   盈利股票: {len(profitable_stocks)} 只 ({len(profitable_stocks)/len(core_pool):.1%})")
                print(f"   亏损/低盈利股票: {len(filtered_stocks)} 只 ({len(filtered_stocks)/len(core_pool):.1%})")
                print(f"   最低盈利要求: {min_profit_threshold:.1%}")
                
                # 显示盈利股票样例
                if profitable_stocks:
                    print(f"\n   📈 盈利股票样例 (按收益率排序):")
                    for i, stock in enumerate(profitable_stocks[:5]):
                        print(f"     {i+1}. {stock['symbol']} - 实际收益: {stock['actual_return']:.2%} "
                              f"最大涨幅: {stock['max_gain']:.2%}")
                    if len(profitable_stocks) > 5:
                        print(f"     ... 还有 {len(profitable_stocks) - 5} 只盈利股票")
                
                # 显示被过滤的股票样例
                if filtered_stocks:
                    print(f"\n   📉 被过滤股票样例:")
                    filtered_stocks.sort(key=lambda x: x['actual_return'])
                    for i, stock in enumerate(filtered_stocks[:3]):
                        print(f"     {i+1}. {stock['symbol']} - 实际收益: {stock['actual_return']:.2%} "
                              f"最大涨幅: {stock['max_gain']:.2%}")
                    if len(filtered_stocks) > 3:
                        print(f"     ... 还有 {len(filtered_stocks) - 3} 只被过滤股票")
                
                return profitable_stocks
            else:
                print(f"❌ 季度回测文件格式不正确")
                return []
                
        except Exception as e:
            print(f"❌ 加载季度回测结果失败: {e}")
            return []
    
    def run_momentum_analysis(self, stock_list: List[str], config: MomentumConfig = None) -> List:
        """运行强势分析"""
        print(f"\n🚀 第一步：强势股分析")
        print("=" * 50)
        
        if config is None:
            config = MomentumConfig(
                strength_threshold=0.95,  # 95%时间在MA之上
                lookback_days=60
            )
        
        self.momentum_analyzer = MomentumStrengthAnalyzer(config)
        
        print(f"📊 分析参数:")
        print(f"   MA周期: {config.ma_periods}")
        print(f"   强势阈值: {config.strength_threshold:.1%}")
        print(f"   回测天数: {config.lookback_days}")
        
        # 执行分析
        results = self.momentum_analyzer.analyze_stock_pool(stock_list)
        
        if results:
            # 统计结果
            strong_count = len([r for r in results if r.strength_rank == '强势'])
            buy_count = len([r for r in results if r.action_signal == '买入'])
            
            print(f"✅ 强势分析完成:")
            print(f"   分析股票: {len(results)} 只")
            print(f"   强势股票: {strong_count} 只 ({strong_count/len(results):.1%})")
            print(f"   买入信号: {buy_count} 只 ({buy_count/len(results):.1%})")
            
            # 显示前5名
            print(f"\n🏆 强势排行榜 (前5名):")
            for i, result in enumerate(results[:5], 1):
                print(f"   {i}. {result.symbol} - 得分: {result.final_score:.1f} "
                      f"强势: {result.overall_strength_score:.2f} 信号: {result.action_signal}")
        
        self.momentum_results = results
        return results
    
    def run_timeframe_validation(self, stock_list: List[str], config: TimeframeConfig = None) -> List:
        """运行多周期验证"""
        print(f"\n🔍 第二步：多周期验证")
        print("=" * 50)
        
        if config is None:
            config = TimeframeConfig(
                daily_period=60,
                weekly_period=20,
                monthly_period=6
            )
        
        self.timeframe_validator = MultiTimeframeValidator(config)
        
        print(f"📊 验证参数:")
        print(f"   日线周期: {config.daily_period} 天")
        print(f"   周线周期: {config.weekly_period} 周")
        print(f"   月线周期: {config.monthly_period} 月")
        
        # 执行验证
        results = self.timeframe_validator.validate_stock_pool(stock_list)
        
        if results:
            # 统计结果
            strong_count = len([r for r in results if r.multi_timeframe_strength >= 70])
            uptrend_count = len([r for r in results if r.overall_trend == '上升'])
            consistent_count = len([r for r in results if r.trend_consistency >= 0.67])
            
            print(f"✅ 多周期验证完成:")
            print(f"   验证股票: {len(results)} 只")
            print(f"   强势股票: {strong_count} 只 ({strong_count/len(results):.1%})")
            print(f"   上升趋势: {uptrend_count} 只 ({uptrend_count/len(results):.1%})")
            print(f"   趋势一致: {consistent_count} 只 ({consistent_count/len(results):.1%})")
            
            # 显示前5名
            print(f"\n🏆 多周期强势排行榜 (前5名):")
            for i, result in enumerate(results[:5], 1):
                print(f"   {i}. {result.symbol} - 强势: {result.multi_timeframe_strength:.1f} "
                      f"趋势: {result.overall_trend} 一致性: {result.trend_consistency:.2f}")
        
        self.validation_results = results
        return results
    
    def generate_final_recommendations(self, min_momentum_score: float = 60, 
                                     min_timeframe_strength: float = 60,
                                     max_recommendations: int = 20) -> List[Dict]:
        """生成最终推荐"""
        print(f"\n⭐ 第三步：生成最终推荐")
        print("=" * 50)
        
        if not self.momentum_results or not self.validation_results:
            print("❌ 缺少分析结果，无法生成推荐")
            return []
        
        # 创建股票映射
        momentum_map = {r.symbol: r for r in self.momentum_results}
        validation_map = {r.symbol: r for r in self.validation_results}
        
        # 找到同时通过两个筛选的股票
        common_symbols = set(momentum_map.keys()) & set(validation_map.keys())
        
        recommendations = []
        
        for symbol in common_symbols:
            momentum_result = momentum_map[symbol]
            validation_result = validation_map[symbol]
            
            # 应用筛选条件
            if (momentum_result.final_score >= min_momentum_score and
                validation_result.multi_timeframe_strength >= min_timeframe_strength and
                momentum_result.action_signal in ['买入', '观望'] and
                validation_result.overall_trend in ['上升', '震荡']):
                
                # 计算综合评分
                comprehensive_score = (
                    momentum_result.final_score * 0.4 +
                    validation_result.multi_timeframe_strength * 0.4 +
                    validation_result.trend_consistency * 100 * 0.2
                )
                
                # 确定推荐等级
                if (momentum_result.final_score >= 80 and 
                    validation_result.multi_timeframe_strength >= 80 and
                    validation_result.trend_consistency >= 0.8):
                    recommendation_level = "强烈推荐"
                elif (momentum_result.final_score >= 70 and 
                      validation_result.multi_timeframe_strength >= 70):
                    recommendation_level = "推荐"
                else:
                    recommendation_level = "关注"
                
                recommendation = {
                    'symbol': symbol,
                    'comprehensive_score': comprehensive_score,
                    'recommendation_level': recommendation_level,
                    
                    # 强势分析结果
                    'momentum_score': momentum_result.final_score,
                    'strength_rank': momentum_result.strength_rank,
                    'action_signal': momentum_result.action_signal,
                    'confidence_level': momentum_result.confidence_level,
                    'risk_level': momentum_result.risk_level,
                    
                    # 多周期验证结果
                    'timeframe_strength': validation_result.multi_timeframe_strength,
                    'overall_trend': validation_result.overall_trend,
                    'trend_consistency': validation_result.trend_consistency,
                    'entry_timing': validation_result.entry_timing,
                    'holding_period': validation_result.holding_period,
                    
                    # 关键价位
                    'key_support': validation_result.key_support,
                    'key_resistance': validation_result.key_resistance,
                    'stop_loss': validation_result.stop_loss,
                    'take_profit': validation_result.take_profit,
                    
                    # 技术指标
                    'rsi_value': momentum_result.rsi_value,
                    'rsi_signal': momentum_result.rsi_signal,
                    'macd_signal': momentum_result.macd_signal,
                    'volume_trend': momentum_result.volume_trend,
                    
                    # MA强势分析
                    'ma_strength_scores': momentum_result.ma_strength_scores,
                    'overall_strength_score': momentum_result.overall_strength_score
                }
                
                recommendations.append(recommendation)
        
        # 按综合评分排序
        recommendations.sort(key=lambda x: x['comprehensive_score'], reverse=True)
        
        # 限制推荐数量
        final_recommendations = recommendations[:max_recommendations]
        
        # 统计结果
        strong_rec = len([r for r in final_recommendations if r['recommendation_level'] == '强烈推荐'])
        normal_rec = len([r for r in final_recommendations if r['recommendation_level'] == '推荐'])
        watch_rec = len([r for r in final_recommendations if r['recommendation_level'] == '关注'])
        
        print(f"✅ 最终推荐生成完成:")
        print(f"   候选股票: {len(common_symbols)} 只")
        print(f"   最终推荐: {len(final_recommendations)} 只")
        print(f"   强烈推荐: {strong_rec} 只")
        print(f"   一般推荐: {normal_rec} 只")
        print(f"   重点关注: {watch_rec} 只")
        
        self.final_recommendations = final_recommendations
        return final_recommendations
    
    def generate_comprehensive_report(self) -> str:
        """生成综合报告"""
        if not self.final_recommendations:
            return "没有最终推荐结果"
        
        report = []
        report.append("=" * 100)
        report.append("🎯 增强版强势股筛选综合报告")
        report.append("=" * 100)
        
        # 筛选流程概述
        report.append(f"\n📋 筛选流程概述:")
        report.append(f"  1️⃣ 季度回测原始池 → 399 只股票")
        report.append(f"  2️⃣ 盈利筛选过滤 → {len(self.quarterly_pool)} 只盈利股票")
        report.append(f"  3️⃣ 强势股分析 → {len(self.momentum_results)} 只有效分析")
        report.append(f"  4️⃣ 多周期验证 → {len(self.validation_results)} 只通过验证")
        report.append(f"  5️⃣ 综合筛选 → {len(self.final_recommendations)} 只最终推荐")
        
        # 推荐等级分布
        level_counts = {}
        for rec in self.final_recommendations:
            level = rec['recommendation_level']
            level_counts[level] = level_counts.get(level, 0) + 1
        
        report.append(f"\n📊 推荐等级分布:")
        for level, count in level_counts.items():
            report.append(f"  {level}: {count} 只")
        
        # 详细推荐列表
        report.append(f"\n🏆 详细推荐列表:")
        report.append("-" * 100)
        report.append(f"{'排名':<4} {'代码':<10} {'推荐等级':<8} {'综合得分':<8} {'强势得分':<8} "
                     f"{'多周期得分':<10} {'趋势':<6} {'操作信号':<8}")
        report.append("-" * 100)
        
        for i, rec in enumerate(self.final_recommendations, 1):
            report.append(f"{i:<4} {rec['symbol']:<10} {rec['recommendation_level']:<8} "
                         f"{rec['comprehensive_score']:<8.1f} {rec['momentum_score']:<8.1f} "
                         f"{rec['timeframe_strength']:<10.1f} {rec['overall_trend']:<6} "
                         f"{rec['action_signal']:<8}")
        
        # 强烈推荐详细分析
        strong_recommendations = [r for r in self.final_recommendations if r['recommendation_level'] == '强烈推荐']
        
        if strong_recommendations:
            report.append(f"\n⭐ 强烈推荐详细分析:")
            report.append("=" * 80)
            
            for i, rec in enumerate(strong_recommendations, 1):
                report.append(f"\n{i}. {rec['symbol']} - 综合得分: {rec['comprehensive_score']:.1f}")
                report.append(f"   📈 技术面分析:")
                report.append(f"     • 强势等级: {rec['strength_rank']}")
                report.append(f"     • 整体强势得分: {rec['overall_strength_score']:.2f}")
                report.append(f"     • RSI: {rec['rsi_value']:.1f} ({rec['rsi_signal']})")
                report.append(f"     • MACD: {rec['macd_signal']}")
                report.append(f"     • 成交量: {rec['volume_trend']}")
                
                report.append(f"   🔍 多周期分析:")
                report.append(f"     • 综合趋势: {rec['overall_trend']}")
                report.append(f"     • 趋势一致性: {rec['trend_consistency']:.2f}")
                report.append(f"     • 多周期强势: {rec['timeframe_strength']:.1f}")
                report.append(f"     • 持有周期: {rec['holding_period']}")
                
                report.append(f"   💰 操作建议:")
                report.append(f"     • 入场时机: {rec['entry_timing']}")
                report.append(f"     • 风险等级: {rec['risk_level']}")
                report.append(f"     • 信心度: {rec['confidence_level']:.2f}")
                
                report.append(f"   📊 关键价位:")
                report.append(f"     • 关键支撑: ¥{rec['key_support']:.2f}")
                report.append(f"     • 关键阻力: ¥{rec['key_resistance']:.2f}")
                report.append(f"     • 建议止损: ¥{rec['stop_loss']:.2f}")
                if rec['take_profit']:
                    tp_str = " ".join([f"¥{tp:.2f}" for tp in rec['take_profit'][:3]])
                    report.append(f"     • 目标价位: {tp_str}")
                
                # MA强势分析
                if rec['ma_strength_scores']:
                    report.append(f"   📈 MA强势分析:")
                    for period, score in rec['ma_strength_scores'].items():
                        report.append(f"     • MA{period}: {score:.2f}")
        
        # 操作策略总结
        report.append(f"\n📋 操作策略总结:")
        report.append("-" * 60)
        report.append(f"  🎯 核心策略:")
        report.append(f"    • 重点关注强势股票，价格很少触及MA13/MA20")
        report.append(f"    • 多周期趋势一致性是关键筛选条件")
        report.append(f"    • 技术指标配合良好的标的优先考虑")
        
        report.append(f"\n  💡 建仓策略:")
        report.append(f"    • 立即买入：在关键支撑位附近分批建仓")
        report.append(f"    • 回调买入：等待回调到支撑位再进场")
        report.append(f"    • 突破买入：等待突破阻力位确认后进场")
        
        report.append(f"\n  ⚠️ 风险控制:")
        report.append(f"    • 严格按照建议止损位设置止损")
        report.append(f"    • 单股仓位不超过总资金的20%")
        report.append(f"    • 根据风险等级调整仓位大小")
        report.append(f"    • 密切关注市场整体趋势变化")
        
        # 市场环境分析
        uptrend_ratio = len([r for r in self.final_recommendations if r['overall_trend'] == '上升']) / len(self.final_recommendations)
        avg_strength = sum(r['comprehensive_score'] for r in self.final_recommendations) / len(self.final_recommendations)
        
        report.append(f"\n🌍 市场环境评估:")
        report.append("-" * 40)
        report.append(f"  • 上升趋势比例: {uptrend_ratio:.1%}")
        report.append(f"  • 平均综合强势: {avg_strength:.1f}")
        
        if uptrend_ratio >= 0.7 and avg_strength >= 70:
            market_sentiment = "强势市场，适合积极操作"
        elif uptrend_ratio >= 0.5 and avg_strength >= 60:
            market_sentiment = "中性市场，谨慎选股"
        else:
            market_sentiment = "弱势市场，以防守为主"
        
        report.append(f"  • 市场判断: {market_sentiment}")
        
        return "\n".join(report)
    
    def save_results(self, output_dir: str = "results"):
        """保存所有结果"""
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 保存最终推荐
        recommendations_file = os.path.join(output_dir, f'final_recommendations_{timestamp}.json')
        with open(recommendations_file, 'w', encoding='utf-8') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'total_recommendations': len(self.final_recommendations),
                'recommendations': self.final_recommendations
            }, f, ensure_ascii=False, indent=2, default=str)
        
        # 保存综合报告
        report = self.generate_comprehensive_report()
        report_file = os.path.join(output_dir, f'comprehensive_report_{timestamp}.txt')
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        
        print(f"\n📄 结果已保存:")
        print(f"   推荐数据: {recommendations_file}")
        print(f"   综合报告: {report_file}")
        
        return recommendations_file, report_file

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='增强版强势股筛选系统')
    parser.add_argument('--quarterly-result', required=True, help='季度回测结果文件')
    parser.add_argument('--min-profit-threshold', type=float, default=0.05, help='最低盈利要求 (默认5%)')
    parser.add_argument('--min-momentum-score', type=float, default=60, help='最低强势得分')
    parser.add_argument('--min-timeframe-strength', type=float, default=60, help='最低多周期强势得分')
    parser.add_argument('--max-recommendations', type=int, default=20, help='最大推荐数量')
    parser.add_argument('--output-dir', default='results', help='输出目录')
    
    args = parser.parse_args()
    
    print("🎯 增强版强势股筛选系统")
    print("=" * 60)
    print(f"📅 分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 创建筛选器
    screener = EnhancedMomentumScreener()
    
    # 加载季度回测结果并进行盈利筛选
    quarterly_pool_info = screener.load_quarterly_results(
        args.quarterly_result, 
        min_profit_threshold=args.min_profit_threshold
    )
    if not quarterly_pool_info:
        print("❌ 无法加载季度股票池，程序退出")
        return
    
    # 提取股票代码列表用于后续分析
    quarterly_pool = [stock['symbol'] for stock in quarterly_pool_info]
    screener.quarterly_pool = quarterly_pool_info
    
    # 第一步：强势股分析
    momentum_results = screener.run_momentum_analysis(quarterly_pool)
    if not momentum_results:
        print("❌ 强势分析失败，程序退出")
        return
    
    # 提取通过强势分析的股票
    qualified_stocks = [r.symbol for r in momentum_results 
                       if r.final_score >= args.min_momentum_score]
    
    if not qualified_stocks:
        print("❌ 没有股票通过强势分析，程序退出")
        return
    
    print(f"\n📊 通过强势分析的股票: {len(qualified_stocks)} 只")
    
    # 第二步：多周期验证
    validation_results = screener.run_timeframe_validation(qualified_stocks)
    if not validation_results:
        print("❌ 多周期验证失败，程序退出")
        return
    
    # 第三步：生成最终推荐
    final_recommendations = screener.generate_final_recommendations(
        min_momentum_score=args.min_momentum_score,
        min_timeframe_strength=args.min_timeframe_strength,
        max_recommendations=args.max_recommendations
    )
    
    if not final_recommendations:
        print("❌ 没有生成最终推荐")
        return
    
    # 显示综合报告
    print("\n" + screener.generate_comprehensive_report())
    
    # 保存结果
    screener.save_results(args.output_dir)
    
    print(f"\n✅ 筛选完成！共推荐 {len(final_recommendations)} 只强势股票")

if __name__ == "__main__":
    main()