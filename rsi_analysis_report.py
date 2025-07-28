#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RSI底部分析报告生成器
基于扫描结果生成详细的投资建议和风险分析
"""

import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
from typing import List, Dict, Any

class RSIAnalysisReportGenerator:
    """RSI分析报告生成器"""
    
    def __init__(self):
        self.report_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    def load_latest_scan_results(self) -> List[Dict]:
        """加载最新的扫描结果"""
        results_dir = 'rsi_scan_results'
        if not os.path.exists(results_dir):
            return []
        
        # 找到最新的JSON文件
        json_files = [f for f in os.listdir(results_dir) if f.startswith('rsi_bottom_signals_') and f.endswith('.json')]
        if not json_files:
            return []
        
        latest_file = sorted(json_files)[-1]
        file_path = os.path.join(results_dir, latest_file)
        
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def generate_investment_analysis(self, signals: List[Dict]) -> str:
        """生成投资分析报告"""
        if not signals:
            return "未发现RSI底部机会"
        
        report = []
        report.append("=" * 80)
        report.append("RSI底部投资机会深度分析报告")
        report.append("=" * 80)
        report.append(f"生成时间: {self.report_timestamp}")
        report.append(f"分析样本: {len(signals)}个RSI底部信号")
        report.append("")
        
        # 1. 执行摘要
        report.extend(self._generate_executive_summary(signals))
        
        # 2. 市场机会分析
        report.extend(self._analyze_market_opportunities(signals))
        
        # 3. 风险评估
        report.extend(self._analyze_risks(signals))
        
        # 4. 投资建议分级
        report.extend(self._generate_investment_recommendations(signals))
        
        # 5. 详细个股分析
        report.extend(self._generate_detailed_stock_analysis(signals))
        
        return "\n".join(report)
    
    def _generate_executive_summary(self, signals: List[Dict]) -> List[str]:
        """生成执行摘要"""
        summary = []
        summary.append("📊 执行摘要")
        summary.append("-" * 40)
        
        # 置信度分析
        high_confidence = [s for s in signals if s['confidence_score'] >= 0.8]
        medium_confidence = [s for s in signals if 0.6 <= s['confidence_score'] < 0.8]
        
        summary.append(f"🎯 高置信度机会 (≥80%): {len(high_confidence)}个")
        summary.append(f"🟡 中等置信度机会 (60-80%): {len(medium_confidence)}个")
        
        # 风险分析
        low_risk = [s for s in signals if s['risk_level'] == '低']
        medium_risk = [s for s in signals if s['risk_level'] == '中']
        
        summary.append(f"🟢 低风险机会: {len(low_risk)}个")
        summary.append(f"🟡 中等风险机会: {len(medium_risk)}个")
        
        # 时机分析
        immediate_opportunities = [s for s in signals if s['predicted_bottom_days'] == 0]
        near_term_opportunities = [s for s in signals if 1 <= s['predicted_bottom_days'] <= 3]
        
        summary.append(f"⚡ 立即入场机会: {len(immediate_opportunities)}个")
        summary.append(f"📅 近期入场机会 (1-3天): {len(near_term_opportunities)}个")
        
        # 收益预期
        avg_expected_gain = np.mean([s['avg_rebound_gain'] for s in signals])
        max_expected_gain = max([s['avg_rebound_gain'] for s in signals])
        
        summary.append(f"💰 平均预期收益: {avg_expected_gain:.1%}")
        summary.append(f"🚀 最高预期收益: {max_expected_gain:.1%}")
        summary.append("")
        
        return summary
    
    def _analyze_market_opportunities(self, signals: List[Dict]) -> List[str]:
        """分析市场机会"""
        analysis = []
        analysis.append("🔍 市场机会分析")
        analysis.append("-" * 40)
        
        # RSI极值分析
        extreme_oversold = [s for s in signals if s['current_rsi6'] <= 10]
        oversold = [s for s in signals if 10 < s['current_rsi6'] <= 20]
        
        analysis.append(f"⭐ RSI6极度超卖 (≤10): {len(extreme_oversold)}个")
        if extreme_oversold:
            analysis.append("   → 这些股票处于历史极值区域，反弹概率较高")
            top_extreme = sorted(extreme_oversold, key=lambda x: x['current_rsi6'])[:3]
            for stock in top_extreme:
                analysis.append(f"     • {stock['stock_code']}: RSI6={stock['current_rsi6']:.1f}, 置信度{stock['confidence_score']:.1%}")
        
        analysis.append(f"📉 RSI6超卖 (10-20): {len(oversold)}个")
        analysis.append("")
        
        # 背离机会分析
        divergence_opportunities = [s for s in signals if s.get('rsi_divergence', False)]
        analysis.append(f"🔄 RSI背离机会: {len(divergence_opportunities)}个")
        if divergence_opportunities:
            analysis.append("   → RSI与价格背离通常预示着趋势反转")
            for stock in divergence_opportunities[:3]:
                analysis.append(f"     • {stock['stock_code']}: 置信度{stock['confidence_score']:.1%}, 预期收益{stock['avg_rebound_gain']:.1%}")
        
        analysis.append("")
        
        # 成交量确认分析
        volume_confirmed = [s for s in signals if s.get('volume_confirmation', False)]
        analysis.append(f"📊 成交量确认机会: {len(volume_confirmed)}个")
        analysis.append("   → 成交量放大确认了底部信号的有效性")
        analysis.append("")
        
        return analysis
    
    def _analyze_risks(self, signals: List[Dict]) -> List[str]:
        """分析风险"""
        risk_analysis = []
        risk_analysis.append("⚠️ 风险评估")
        risk_analysis.append("-" * 40)
        
        # 风险分布
        risk_distribution = {}
        for signal in signals:
            risk_level = signal['risk_level']
            risk_distribution[risk_level] = risk_distribution.get(risk_level, 0) + 1
        
        risk_analysis.append("风险等级分布:")
        for risk_level, count in risk_distribution.items():
            risk_analysis.append(f"  {risk_level}风险: {count}个")
        
        risk_analysis.append("")
        
        # 高风险警告
        high_risk_stocks = [s for s in signals if s['risk_level'] == '高']
        if high_risk_stocks:
            risk_analysis.append("🚨 高风险股票警告:")
            for stock in high_risk_stocks[:5]:  # 显示前5个
                risk_analysis.append(f"  • {stock['stock_code']}: RSI6={stock['current_rsi6']:.1f}, 趋势={stock['price_trend']}")
            risk_analysis.append("  → 建议谨慎操作，严格止损")
        
        risk_analysis.append("")
        
        # 止损建议
        avg_stop_loss_distance = np.mean([
            (s['current_price'] - s['stop_loss_price']) / s['current_price'] 
            for s in signals if s['stop_loss_price'] > 0
        ])
        
        risk_analysis.append(f"📉 平均建议止损距离: {avg_stop_loss_distance:.1%}")
        risk_analysis.append("💡 风险控制建议:")
        risk_analysis.append("  1. 严格执行止损策略")
        risk_analysis.append("  2. 分批建仓，控制单只股票仓位")
        risk_analysis.append("  3. 关注市场整体趋势变化")
        risk_analysis.append("")
        
        return risk_analysis
    
    def _generate_investment_recommendations(self, signals: List[Dict]) -> List[str]:
        """生成投资建议分级"""
        recommendations = []
        recommendations.append("🏆 投资建议分级")
        recommendations.append("-" * 40)
        
        # A级推荐 (高置信度 + 低风险)
        a_grade = [s for s in signals if s['confidence_score'] >= 0.8 and s['risk_level'] == '低']
        recommendations.append(f"🥇 A级推荐 (高置信度+低风险): {len(a_grade)}个")
        if a_grade:
            recommendations.append("   特点: 高成功概率，风险可控，适合积极投资")
            for i, stock in enumerate(sorted(a_grade, key=lambda x: x['confidence_score'], reverse=True)[:5], 1):
                recommendations.append(f"   {i}. {stock['stock_code']}: 置信度{stock['confidence_score']:.1%}, "
                                    f"RSI6={stock['current_rsi6']:.1f}, 预期收益{stock['avg_rebound_gain']:.1%}")
        
        recommendations.append("")
        
        # B级推荐 (高置信度 或 低风险)
        b_grade = [s for s in signals if 
                  (s['confidence_score'] >= 0.7 and s['risk_level'] in ['低', '中']) and
                  s not in a_grade]
        recommendations.append(f"🥈 B级推荐 (高置信度或低风险): {len(b_grade)}个")
        if b_grade:
            recommendations.append("   特点: 较好的风险收益比，适合稳健投资")
            for i, stock in enumerate(sorted(b_grade, key=lambda x: x['confidence_score'], reverse=True)[:3], 1):
                recommendations.append(f"   {i}. {stock['stock_code']}: 置信度{stock['confidence_score']:.1%}, "
                                    f"风险{stock['risk_level']}, 预期收益{stock['avg_rebound_gain']:.1%}")
        
        recommendations.append("")
        
        # C级推荐 (其他)
        c_grade = [s for s in signals if s not in a_grade and s not in b_grade]
        recommendations.append(f"🥉 C级推荐 (观察级别): {len(c_grade)}个")
        recommendations.append("   特点: 需要密切观察，适合小仓位试探")
        
        recommendations.append("")
        
        return recommendations
    
    def _generate_detailed_stock_analysis(self, signals: List[Dict]) -> List[str]:
        """生成详细个股分析"""
        analysis = []
        analysis.append("📈 重点个股详细分析")
        analysis.append("-" * 40)
        
        # 选择前10个最有潜力的股票
        top_stocks = sorted(signals, key=lambda x: x['confidence_score'], reverse=True)[:10]
        
        for i, stock in enumerate(top_stocks, 1):
            analysis.append(f"{i:2d}. {stock['stock_code']} - 综合分析")
            analysis.append(f"    💰 当前价格: ¥{stock['current_price']:.2f}")
            analysis.append(f"    📊 RSI状态: RSI6={stock['current_rsi6']:.1f}, RSI12={stock['current_rsi12']:.1f}, RSI24={stock['current_rsi24']:.1f}")
            
            # 底部预测
            if stock['predicted_bottom_days'] == 0:
                analysis.append(f"    🎯 底部状态: 已到达底部区域")
            else:
                analysis.append(f"    🎯 底部预测: {stock['predicted_bottom_days']}天后到达¥{stock['predicted_bottom_price']:.2f}")
            
            # 投资建议
            analysis.append(f"    📈 投资建议:")
            analysis.append(f"       • 置信度: {stock['confidence_score']:.1%} ({self._get_confidence_level(stock['confidence_score'])})")
            analysis.append(f"       • 风险等级: {stock['risk_level']}")
            analysis.append(f"       • 预期收益: {stock['avg_rebound_gain']:.1%}")
            analysis.append(f"       • 建议止损: ¥{stock['stop_loss_price']:.2f} ({((stock['current_price'] - stock['stop_loss_price']) / stock['current_price']):.1%})")
            
            # 技术面分析
            analysis.append(f"    🔍 技术面:")
            analysis.append(f"       • 价格趋势: {stock['price_trend']}")
            if stock.get('rsi_divergence'):
                analysis.append(f"       • RSI背离: 是 (看涨信号)")
            if stock.get('volume_confirmation'):
                analysis.append(f"       • 成交量确认: 是")
            
            # 历史表现
            analysis.append(f"    📊 历史表现: 准确率{stock['historical_accuracy']:.1%}")
            
            # 操作建议
            analysis.append(f"    💡 操作建议:")
            if stock['predicted_bottom_days'] == 0:
                analysis.append(f"       • 可考虑立即分批建仓")
            else:
                analysis.append(f"       • 建议等待{stock['predicted_bottom_days']}天后再考虑入场")
            
            analysis.append(f"       • 建议仓位: {self._suggest_position_size(stock)}%")
            analysis.append("")
        
        return analysis
    
    def _get_confidence_level(self, confidence: float) -> str:
        """获取置信度等级描述"""
        if confidence >= 0.8:
            return "高"
        elif confidence >= 0.6:
            return "中"
        else:
            return "低"
    
    def _suggest_position_size(self, stock: Dict) -> str:
        """建议仓位大小"""
        confidence = stock['confidence_score']
        risk_level = stock['risk_level']
        
        if confidence >= 0.8 and risk_level == '低':
            return "5-8"
        elif confidence >= 0.7 and risk_level in ['低', '中']:
            return "3-5"
        elif confidence >= 0.6:
            return "2-3"
        else:
            return "1-2"
    
    def save_report(self, report_content: str):
        """保存报告"""
        output_dir = 'rsi_scan_results'
        os.makedirs(output_dir, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'rsi_investment_analysis_{timestamp}.txt'
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report_content)
        
        print(f"📄 投资分析报告已保存: {filepath}")
        return filepath

def main():
    """主函数"""
    print("📊 生成RSI底部投资分析报告...")
    
    generator = RSIAnalysisReportGenerator()
    
    # 加载最新扫描结果
    signals = generator.load_latest_scan_results()
    
    if not signals:
        print("❌ 未找到扫描结果，请先运行 rsi_bottom_scanner.py")
        return
    
    print(f"📈 加载了{len(signals)}个RSI底部信号")
    
    # 生成分析报告
    report = generator.generate_investment_analysis(signals)
    
    # 保存报告
    filepath = generator.save_report(report)
    
    # 显示关键信息
    print("\n🎯 关键投资机会:")
    high_confidence_low_risk = [s for s in signals if s['confidence_score'] >= 0.8 and s['risk_level'] == '低']
    
    if high_confidence_low_risk:
        print("🥇 A级推荐 (高置信度+低风险):")
        for i, stock in enumerate(sorted(high_confidence_low_risk, key=lambda x: x['confidence_score'], reverse=True)[:5], 1):
            print(f"  {i}. {stock['stock_code']}: ¥{stock['current_price']:.2f}, RSI6={stock['current_rsi6']:.1f}, "
                  f"置信度{stock['confidence_score']:.1%}, 预期收益{stock['avg_rebound_gain']:.1%}")
    else:
        print("当前无A级推荐，建议关注B级机会或等待更好时机")
    
    print(f"\n📖 完整分析报告请查看: {filepath}")

if __name__ == "__main__":
    main()