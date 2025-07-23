    def _generate_performance_report(self, performance_data: Dict) -> None:
        """生成绩效报告"""
        try:
            report_file = f"reports/performance_report_{datetime.now().strftime('%Y%m%d')}.json"
            
            # 创建详细的绩效报告
            report = {
                'report_date': datetime.now().isoformat(),
                'summary': self._generate_performance_summary(performance_data),
                'stock_details': performance_data.get('stock_statistics', {}),
                'recommendations': self._generate_recommendations(performance_data)
            }
            
            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"绩效报告已生成: {report_file}")
            
        except Exception as e:
            self.logger.error(f"生成绩效报告失败: {e}")
    
    def _generate_performance_summary(self, performance_data: Dict) -> Dict:
        """生成绩效摘要"""
        try:
            stock_stats = performance_data.get('stock_statistics', {})
            
            if not stock_stats:
                return {'message': '暂无绩效数据'}
            
            total_stocks = len(stock_stats)
            total_signals = sum(stats.get('total_signals', 0) for stats in stock_stats.values())
            total_closed = sum(stats.get('closed_signals', 0) for stats in stock_stats.values())
            total_winning = sum(stats.get('winning_signals', 0) for stats in stock_stats.values())
            
            overall_win_rate = total_winning / total_closed if total_closed > 0 else 0
            
            # 计算平均收益率
            returns = [stats.get('avg_return', 0) for stats in stock_stats.values() if stats.get('closed_signals', 0) > 0]
            avg_return = sum(returns) / len(returns) if returns else 0
            
            # 找出表现最好和最差的股票
            best_stock = None
            worst_stock = None
            best_performance = -float('inf')
            worst_performance = float('inf')
            
            for stock_code, stats in stock_stats.items():
                if stats.get('closed_signals', 0) >= 3:  # 至少3个信号才参与排名
                    performance_score = (stats.get('win_rate', 0) * 0.6) + (stats.get('avg_return', 0) * 0.4)
                    
                    if performance_score > best_performance:
                        best_performance = performance_score
                        best_stock = stock_code
                    
                    if performance_score < worst_performance:
                        worst_performance = performance_score
                        worst_stock = stock_code
            
            return {
                'total_stocks_tracked': total_stocks,
                'total_signals_generated': total_signals,
                'total_signals_closed': total_closed,
                'overall_win_rate': round(overall_win_rate * 100, 2),
                'average_return': round(avg_return * 100, 2),
                'best_performing_stock': best_stock,
                'worst_performing_stock': worst_stock,
                'active_signals': total_signals - total_closed
            }
            
        except Exception as e:
            self.logger.error(f"生成绩效摘要失败: {e}")
            return {'error': str(e)}
    
    def _generate_recommendations(self, performance_data: Dict) -> List[Dict]:
        """生成改进建议"""
        try:
            recommendations = []
            stock_stats = performance_data.get('stock_statistics', {})
            
            if not stock_stats:
                return [{'type': 'info', 'message': '暂无足够数据生成建议'}]
            
            # 分析整体表现
            total_closed = sum(stats.get('closed_signals', 0) for stats in stock_stats.values())
            total_winning = sum(stats.get('winning_signals', 0) for stats in stock_stats.values())
            overall_win_rate = total_winning / total_closed if total_closed > 0 else 0
            
            # 胜率相关建议
            if overall_win_rate < 0.4:
                recommendations.append({
                    'type': 'warning',
                    'category': 'win_rate',
                    'message': f'整体胜率较低({overall_win_rate:.1%})，建议调整信号筛选标准',
                    'suggestion': '提高信号置信度阈值或优化技术指标参数'
                })
            elif overall_win_rate > 0.7:
                recommendations.append({
                    'type': 'success',
                    'category': 'win_rate',
                    'message': f'整体胜率良好({overall_win_rate:.1%})，系统表现稳定',
                    'suggestion': '可以考虑适当增加核心观察池规模'
                })
            
            # 找出需要关注的股票
            poor_performers = []
            excellent_performers = []
            
            for stock_code, stats in stock_stats.items():
                if stats.get('closed_signals', 0) >= 3:
                    win_rate = stats.get('win_rate', 0)
                    avg_return = stats.get('avg_return', 0)
                    
                    if win_rate < 0.3 or avg_return < -0.05:
                        poor_performers.append(stock_code)
                    elif win_rate > 0.8 and avg_return > 0.05:
                        excellent_performers.append(stock_code)
            
            if poor_performers:
                recommendations.append({
                    'type': 'action',
                    'category': 'stock_management',
                    'message': f'发现{len(poor_performers)}只表现不佳的股票',
                    'suggestion': f'建议从核心池移除: {", ".join(poor_performers[:5])}',
                    'stocks': poor_performers
                })
            
            if excellent_performers:
                recommendations.append({
                    'type': 'opportunity',
                    'category': 'stock_management',
                    'message': f'发现{len(excellent_performers)}只表现优异的股票',
                    'suggestion': f'建议增加关注度: {", ".join(excellent_performers[:5])}',
                    'stocks': excellent_performers
                })
            
            # 信号频率建议
            avg_signals_per_stock = sum(stats.get('total_signals', 0) for stats in stock_stats.values()) / len(stock_stats)
            if avg_signals_per_stock < 2:
                recommendations.append({
                    'type': 'info',
                    'category': 'signal_frequency',
                    'message': '信号生成频率较低，可能错过交易机会',
                    'suggestion': '考虑降低信号置信度阈值或增加技术指标种类'
                })
            elif avg_signals_per_stock > 10:
                recommendations.append({
                    'type': 'warning',
                    'category': 'signal_frequency',
                    'message': '信号生成频率过高，可能存在过度交易',
                    'suggestion': '建议提高信号筛选标准，减少噪音信号'
                })
            
            return recommendations
            
        except Exception as e:
            self.logger.error(f"生成建议失败: {e}")
            return [{'type': 'error', 'message': f'生成建议时出错: {e}'}]


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='三阶段交易决策支持系统工作流管理器')
    
    parser.add_argument('--phase', choices=['phase1', 'phase2', 'phase3', 'all'], 
                       default='all', help='执行的阶段')
    parser.add_argument('--config', default='workflow_config.json', 
                       help='配置文件路径')
    parser.add_argument('--force', action='store_true', 
                       help='强制执行，忽略时间间隔限制')
    parser.add_argument('--dry-run', action='store_true', 
                       help='试运行模式，不执行实际操作')
    
    args = parser.parse_args()
    
    try:
        # 初始化工作流管理器
        manager = WorkflowManager(args.config)
        
        if args.dry_run:
            manager.logger.info("试运行模式：不执行实际操作")
            return
        
        # 确定要执行的阶段
        if args.phase == 'all':
            phases = ['phase1', 'phase2', 'phase3']
        else:
            phases = [args.phase]
        
        # 如果强制执行，临时修改配置
        if args.force:
            for phase in phases:
                manager.config[phase]['frequency_days'] = 0
        
        # 执行工作流
        results = manager.run_workflow(phases)
        
        # 输出结果摘要
        print("\n=== 工作流执行结果 ===")
        for phase, result in results.items():
            if result.get('skipped'):
                print(f"{phase}: 跳过 ({result['reason']})")
            elif result.get('success'):
                print(f"{phase}: 成功")
            else:
                print(f"{phase}: 失败 - {result.get('error', '未知错误')}")
        
    except Exception as e:
        print(f"工作流执行失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()