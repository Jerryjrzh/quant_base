#!/usr/bin/env python3
"""
交互式报告生成器

这个模块实现了高级的报告生成功能，包括：
- 美化输出格式，支持HTML/PDF导出
- 可视化图表展示信号与建议
- 多格式报告生成
- 邮件/消息推送功能
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import base64
from io import BytesIO

# 添加backend目录到路径
sys.path.append(os.path.dirname(__file__))

from stock_pool_manager import StockPoolManager
from performance_tracker import PerformanceTracker

# 尝试导入可视化库
try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.figure import Figure
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

try:
    from jinja2 import Template, Environment, FileSystemLoader
    HAS_JINJA2 = True
except ImportError:
    HAS_JINJA2 = False


class ReportGenerator:
    """交互式报告生成器"""
    
    def __init__(self, db_path: str = "stock_pool.db", config: Optional[Dict] = None):
        """初始化报告生成器"""
        self.db_path = db_path
        self.pool_manager = StockPoolManager(db_path)
        self.performance_tracker = PerformanceTracker(db_path)
        self.config = config or self._get_default_config()
        self.logger = logging.getLogger(__name__)
        
        # 创建报告目录
        self.reports_dir = Path("reports")
        self.templates_dir = Path("templates")
        self.reports_dir.mkdir(exist_ok=True)
        self.templates_dir.mkdir(exist_ok=True)
        
        # 初始化模板环境
        if HAS_JINJA2:
            self.jinja_env = Environment(loader=FileSystemLoader(str(self.templates_dir)))
        else:
            self.jinja_env = None    

    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "report_formats": ["html", "json", "txt"],
            "chart_settings": {
                "width": 12,
                "height": 8,
                "dpi": 100,
                "style": "seaborn-v0_8"
            },
            "email_settings": {
                "enabled": False,
                "smtp_server": "",
                "smtp_port": 587,
                "username": "",
                "password": "",
                "recipients": []
            },
            "notification_settings": {
                "enabled": False,
                "webhook_url": "",
                "channels": []
            }
        }
    
    def generate_comprehensive_report(self, report_type: str = "html") -> Dict[str, Any]:
        """生成综合报告"""
        try:
            self.logger.info(f"开始生成{report_type}格式的综合报告")
            
            # 收集数据
            report_data = self._collect_report_data()
            
            # 生成图表
            charts = self._generate_charts(report_data) if HAS_MATPLOTLIB else {}
            
            # 根据格式生成报告
            if report_type.lower() == "html":
                result = self._generate_html_report(report_data, charts)
            elif report_type.lower() == "pdf":
                result = self._generate_pdf_report(report_data, charts)
            elif report_type.lower() == "json":
                result = self._generate_json_report(report_data)
            else:
                result = self._generate_text_report(report_data)
            
            self.logger.info(f"综合报告生成完成: {result.get('filename', 'N/A')}")
            return result
            
        except Exception as e:
            self.logger.error(f"生成综合报告失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def generate_signal_report(self, signals: List[Dict], format_type: str = "html") -> Dict[str, Any]:
        """生成信号报告"""
        try:
            self.logger.info(f"生成{len(signals)}个信号的{format_type}报告")
            
            # 处理信号数据
            processed_signals = self._process_signals_for_report(signals)
            
            # 生成信号图表
            signal_charts = self._generate_signal_charts(processed_signals) if HAS_MATPLOTLIB else {}
            
            # 生成报告
            if format_type.lower() == "html":
                result = self._generate_signal_html_report(processed_signals, signal_charts)
            else:
                result = self._generate_signal_json_report(processed_signals)
            
            return result
            
        except Exception as e:
            self.logger.error(f"生成信号报告失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def generate_performance_dashboard(self) -> Dict[str, Any]:
        """生成绩效仪表板"""
        try:
            self.logger.info("生成绩效仪表板")
            
            # 获取绩效数据
            performance_data = self._collect_performance_data()
            
            # 生成仪表板图表
            dashboard_charts = self._generate_dashboard_charts(performance_data) if HAS_MATPLOTLIB else {}
            
            # 生成HTML仪表板
            result = self._generate_dashboard_html(performance_data, dashboard_charts)
            
            return result
            
        except Exception as e:
            self.logger.error(f"生成绩效仪表板失败: {e}")
            return {'success': False, 'error': str(e)}    

    def _collect_report_data(self) -> Dict[str, Any]:
        """收集报告数据"""
        try:
            # 获取观察池统计
            pool_stats = self.pool_manager.get_pool_statistics()
            
            # 获取绩效分析
            performance_analysis = self.performance_tracker.batch_performance_analysis()
            
            # 获取最近信号
            recent_signals = self._get_recent_signals(days=7)
            
            # 获取系统状态
            system_status = self._get_system_status()
            
            return {
                'generation_time': datetime.now().isoformat(),
                'pool_statistics': pool_stats,
                'performance_analysis': performance_analysis,
                'recent_signals': recent_signals,
                'system_status': system_status,
                'summary': self._generate_summary(pool_stats, performance_analysis)
            }
            
        except Exception as e:
            self.logger.error(f"收集报告数据失败: {e}")
            return {}
    
    def _generate_charts(self, report_data: Dict) -> Dict[str, str]:
        """生成图表"""
        if not HAS_MATPLOTLIB:
            return {}
        
        charts = {}
        
        try:
            # 设置图表样式和中文字体
            plt.style.use('default')  # 使用默认样式
            plt.rcParams['font.sans-serif'] = ['Noto Sans CJK JP', 'Noto Sans CJK SC', 'DejaVu Sans', 'Arial Unicode MS', 'sans-serif']
            plt.rcParams['axes.unicode_minus'] = False
            
            # 1. 观察池评级分布饼图
            charts['grade_distribution'] = self._create_grade_distribution_chart(
                report_data.get('pool_statistics', {})
            )
            
            # 2. 绩效趋势图
            charts['performance_trend'] = self._create_performance_trend_chart(
                report_data.get('performance_analysis', {})
            )
            
            # 3. 信号统计柱状图
            charts['signal_statistics'] = self._create_signal_statistics_chart(
                report_data.get('recent_signals', [])
            )
            
            # 4. 风险分布图
            charts['risk_distribution'] = self._create_risk_distribution_chart(
                report_data.get('performance_analysis', {})
            )
            
        except Exception as e:
            self.logger.error(f"生成图表失败: {e}")
        
        return charts
    
    def _create_grade_distribution_chart(self, pool_stats: Dict) -> str:
        """创建评级分布饼图"""
        try:
            grade_dist = pool_stats.get('grade_distribution', {})
            if not grade_dist:
                return ""
            
            fig, ax = plt.subplots(figsize=(8, 6))
            
            labels = list(grade_dist.keys())
            sizes = list(grade_dist.values())
            colors = ['#ff9999', '#66b3ff', '#99ff99', '#ffcc99', '#ff99cc']
            
            wedges, texts, autotexts = ax.pie(sizes, labels=labels, colors=colors[:len(labels)], 
                                            autopct='%1.1f%%', startangle=90)
            
            ax.set_title('股票评级分布', fontsize=14, fontweight='bold')
            
            # 转换为base64字符串
            buffer = BytesIO()
            plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
            buffer.seek(0)
            chart_data = base64.b64encode(buffer.getvalue()).decode()
            plt.close(fig)
            
            return f"data:image/png;base64,{chart_data}"
            
        except Exception as e:
            self.logger.error(f"创建评级分布图失败: {e}")
            return ""
    
    def _create_performance_trend_chart(self, performance_data: Dict) -> str:
        """创建绩效趋势图"""
        try:
            # 模拟绩效趋势数据
            dates = [datetime.now() - timedelta(days=i) for i in range(30, 0, -1)]
            returns = [0.02 + 0.01 * (i % 7 - 3) for i in range(30)]
            
            fig, ax = plt.subplots(figsize=(10, 6))
            
            ax.plot(dates, returns, marker='o', linewidth=2, markersize=4)
            ax.set_title('30天绩效趋势', fontsize=14, fontweight='bold')
            ax.set_xlabel('日期')
            ax.set_ylabel('收益率')
            ax.grid(True, alpha=0.3)
            
            # 格式化x轴日期
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=5))
            plt.xticks(rotation=45)
            
            # 转换为base64字符串
            buffer = BytesIO()
            plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
            buffer.seek(0)
            chart_data = base64.b64encode(buffer.getvalue()).decode()
            plt.close(fig)
            
            return f"data:image/png;base64,{chart_data}"
            
        except Exception as e:
            self.logger.error(f"创建绩效趋势图失败: {e}")
            return ""
    
    def _generate_html_report(self, report_data: Dict, charts: Dict) -> Dict[str, Any]:
        """生成HTML报告"""
        try:
            # 创建HTML模板
            html_template = self._get_html_template()
            
            # 渲染HTML
            html_content = html_template.format(
                title="交易决策支持系统 - 综合报告",
                generation_time=report_data.get('generation_time', ''),
                pool_stats=report_data.get('pool_statistics', {}),
                performance_summary=report_data.get('summary', {}),
                charts=charts,
                recent_signals=report_data.get('recent_signals', [])
            )
            
            # 保存HTML文件
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"reports/comprehensive_report_{timestamp}.html"
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            return {
                'success': True,
                'filename': filename,
                'format': 'html',
                'size': len(html_content)
            }
            
        except Exception as e:
            self.logger.error(f"生成HTML报告失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def _get_html_template(self) -> str:
        """获取HTML模板"""
        return '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
            color: #333;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 2.5em;
            font-weight: 300;
        }}
        .header p {{
            margin: 10px 0 0 0;
            opacity: 0.9;
        }}
        .content {{
            padding: 30px;
        }}
        .section {{
            margin-bottom: 40px;
        }}
        .section h2 {{
            color: #667eea;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
            margin-bottom: 20px;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
            border-left: 4px solid #667eea;
        }}
        .stat-value {{
            font-size: 2em;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 5px;
        }}
        .stat-label {{
            color: #666;
            font-size: 0.9em;
        }}
        .chart-container {{
            text-align: center;
            margin: 20px 0;
        }}
        .chart-container img {{
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .signals-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }}
        .signals-table th,
        .signals-table td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        .signals-table th {{
            background-color: #667eea;
            color: white;
        }}
        .signals-table tr:hover {{
            background-color: #f5f5f5;
        }}
        .signal-buy {{
            color: #28a745;
            font-weight: bold;
        }}
        .signal-sell {{
            color: #dc3545;
            font-weight: bold;
        }}
        .footer {{
            background: #f8f9fa;
            padding: 20px;
            text-align: center;
            color: #666;
            border-top: 1px solid #ddd;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 交易决策支持系统</h1>
            <p>综合分析报告 - {generation_time}</p>
        </div>
        
        <div class="content">
            <div class="section">
                <h2>📈 系统概览</h2>
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-value">{pool_stats[total_stocks]}</div>
                        <div class="stat-label">总股票数</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{pool_stats[active_stocks]}</div>
                        <div class="stat-label">活跃股票</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{pool_stats[total_signals]}</div>
                        <div class="stat-label">总信号数</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{pool_stats[overall_win_rate]:.1%}</div>
                        <div class="stat-label">整体胜率</div>
                    </div>
                </div>
            </div>
            
            <div class="section">
                <h2>📊 数据可视化</h2>
                <div class="chart-container">
                    <h3>股票评级分布</h3>
                    <img src="{charts[grade_distribution]}" alt="评级分布图">
                </div>
                <div class="chart-container">
                    <h3>绩效趋势</h3>
                    <img src="{charts[performance_trend]}" alt="绩效趋势图">
                </div>
            </div>
            
            <div class="section">
                <h2>🎯 最近信号</h2>
                <table class="signals-table">
                    <thead>
                        <tr>
                            <th>股票代码</th>
                            <th>信号类型</th>
                            <th>置信度</th>
                            <th>触发价格</th>
                            <th>时间</th>
                        </tr>
                    </thead>
                    <tbody>
                        <!-- 信号数据将在这里插入 -->
                    </tbody>
                </table>
            </div>
        </div>
        
        <div class="footer">
            <p>© 2025 交易决策支持系统 | 报告生成时间: {generation_time}</p>
        </div>
    </div>
</body>
</html>
        '''
    
    def _get_recent_signals(self, days: int = 7) -> List[Dict]:
        """获取最近的信号"""
        try:
            # 这里应该从数据库查询最近的信号
            # 暂时返回模拟数据
            return [
                {
                    'stock_code': 'sz300290',
                    'signal_type': 'buy',
                    'confidence': 0.85,
                    'trigger_price': 17.5,
                    'signal_date': datetime.now().isoformat()
                }
            ]
        except Exception as e:
            self.logger.error(f"获取最近信号失败: {e}")
            return []
    
    def _get_system_status(self) -> Dict:
        """获取系统状态"""
        return {
            'status': 'healthy',
            'last_update': datetime.now().isoformat(),
            'uptime': '24h',
            'memory_usage': '45%'
        }
    
    def _generate_summary(self, pool_stats: Dict, performance_analysis: Dict) -> Dict:
        """生成摘要"""
        return {
            'total_stocks': pool_stats.get('total_stocks', 0),
            'active_stocks': pool_stats.get('active_stocks', 0),
            'avg_score': pool_stats.get('avg_score', 0),
            'win_rate': pool_stats.get('overall_win_rate', 0)
        }
    
    def _create_signal_statistics_chart(self, signals: List[Dict]) -> str:
        """创建信号统计柱状图"""
        try:
            if not signals:
                return ""
            
            # 统计信号类型
            signal_counts = {}
            for signal in signals:
                signal_type = signal.get('signal_type', 'unknown')
                signal_counts[signal_type] = signal_counts.get(signal_type, 0) + 1
            
            if not signal_counts:
                return ""
            
            fig, ax = plt.subplots(figsize=(8, 6))
            
            types = list(signal_counts.keys())
            counts = list(signal_counts.values())
            colors = ['#28a745' if t == 'buy' else '#dc3545' for t in types]
            
            bars = ax.bar(types, counts, color=colors, alpha=0.7)
            ax.set_title('信号类型统计', fontsize=14, fontweight='bold')
            ax.set_xlabel('信号类型')
            ax.set_ylabel('数量')
            
            # 在柱状图上显示数值
            for bar, count in zip(bars, counts):
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{count}', ha='center', va='bottom')
            
            # 转换为base64字符串
            buffer = BytesIO()
            plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
            buffer.seek(0)
            chart_data = base64.b64encode(buffer.getvalue()).decode()
            plt.close(fig)
            
            return f"data:image/png;base64,{chart_data}"
            
        except Exception as e:
            self.logger.error(f"创建信号统计图失败: {e}")
            return ""
    
    def _create_risk_distribution_chart(self, performance_data: Dict) -> str:
        """创建风险分布图"""
        try:
            # 模拟风险分布数据
            risk_levels = ['LOW', 'MEDIUM', 'HIGH']
            risk_counts = [5, 8, 3]  # 模拟数据
            
            fig, ax = plt.subplots(figsize=(8, 6))
            
            colors = ['#28a745', '#ffc107', '#dc3545']
            bars = ax.bar(risk_levels, risk_counts, color=colors, alpha=0.7)
            
            ax.set_title('风险等级分布', fontsize=14, fontweight='bold')
            ax.set_xlabel('风险等级')
            ax.set_ylabel('股票数量')
            
            # 在柱状图上显示数值
            for bar, count in zip(bars, risk_counts):
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{count}', ha='center', va='bottom')
            
            # 转换为base64字符串
            buffer = BytesIO()
            plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
            buffer.seek(0)
            chart_data = base64.b64encode(buffer.getvalue()).decode()
            plt.close(fig)
            
            return f"data:image/png;base64,{chart_data}"
            
        except Exception as e:
            self.logger.error(f"创建风险分布图失败: {e}")
            return ""
    
    def _generate_json_report(self, report_data: Dict) -> Dict[str, Any]:
        """生成JSON报告"""
        try:
            # 保存JSON文件
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"reports/comprehensive_report_{timestamp}.json"
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, indent=2, ensure_ascii=False, default=str)
            
            return {
                'success': True,
                'filename': filename,
                'format': 'json',
                'size': os.path.getsize(filename)
            }
            
        except Exception as e:
            self.logger.error(f"生成JSON报告失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def _generate_text_report(self, report_data: Dict) -> Dict[str, Any]:
        """生成文本报告"""
        try:
            # 创建文本内容
            lines = []
            lines.append("=" * 60)
            lines.append("交易决策支持系统 - 综合报告")
            lines.append("=" * 60)
            lines.append(f"生成时间: {report_data.get('generation_time', '')}")
            lines.append("")
            
            # 系统概览
            pool_stats = report_data.get('pool_statistics', {})
            lines.append("📈 系统概览")
            lines.append("-" * 30)
            lines.append(f"总股票数: {pool_stats.get('total_stocks', 0)}")
            lines.append(f"活跃股票: {pool_stats.get('active_stocks', 0)}")
            lines.append(f"总信号数: {pool_stats.get('total_signals', 0)}")
            lines.append(f"整体胜率: {pool_stats.get('overall_win_rate', 0):.1%}")
            lines.append("")
            
            # 最近信号
            recent_signals = report_data.get('recent_signals', [])
            lines.append("🎯 最近信号")
            lines.append("-" * 30)
            for signal in recent_signals[:10]:  # 只显示前10个
                lines.append(f"{signal.get('stock_code', '')} - {signal.get('signal_type', '')} - 置信度: {signal.get('confidence', 0):.2f}")
            
            text_content = "\n".join(lines)
            
            # 保存文本文件
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"reports/comprehensive_report_{timestamp}.txt"
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(text_content)
            
            return {
                'success': True,
                'filename': filename,
                'format': 'txt',
                'size': len(text_content)
            }
            
        except Exception as e:
            self.logger.error(f"生成文本报告失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def _process_signals_for_report(self, signals: List[Dict]) -> List[Dict]:
        """处理信号数据用于报告"""
        processed = []
        for signal in signals:
            processed_signal = {
                'stock_code': signal.get('stock_code', ''),
                'signal_type': signal.get('signal_type', ''),
                'confidence': signal.get('confidence', 0),
                'trigger_price': signal.get('trigger_price', 0),
                'signal_date': signal.get('signal_date', datetime.now().isoformat())
            }
            processed.append(processed_signal)
        return processed
    
    def _generate_signal_charts(self, signals: List[Dict]) -> Dict[str, str]:
        """生成信号图表"""
        charts = {}
        try:
            # 信号分布图
            charts['signal_distribution'] = self._create_signal_statistics_chart(signals)
            
            # 置信度分布图
            charts['confidence_distribution'] = self._create_confidence_distribution_chart(signals)
            
        except Exception as e:
            self.logger.error(f"生成信号图表失败: {e}")
        
        return charts
    
    def _create_confidence_distribution_chart(self, signals: List[Dict]) -> str:
        """创建置信度分布图"""
        try:
            if not signals:
                return ""
            
            confidences = [signal.get('confidence', 0) for signal in signals]
            
            fig, ax = plt.subplots(figsize=(8, 6))
            
            ax.hist(confidences, bins=10, alpha=0.7, color='#667eea', edgecolor='black')
            ax.set_title('信号置信度分布', fontsize=14, fontweight='bold')
            ax.set_xlabel('置信度')
            ax.set_ylabel('频次')
            ax.grid(True, alpha=0.3)
            
            # 转换为base64字符串
            buffer = BytesIO()
            plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
            buffer.seek(0)
            chart_data = base64.b64encode(buffer.getvalue()).decode()
            plt.close(fig)
            
            return f"data:image/png;base64,{chart_data}"
            
        except Exception as e:
            self.logger.error(f"创建置信度分布图失败: {e}")
            return ""
    
    def _generate_signal_html_report(self, signals: List[Dict], charts: Dict) -> Dict[str, Any]:
        """生成信号HTML报告"""
        try:
            html_content = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>信号报告</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background: #667eea; color: white; padding: 20px; text-align: center; }}
        .chart {{ text-align: center; margin: 20px 0; }}
        .chart img {{ max-width: 100%; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 10px; border: 1px solid #ddd; text-align: left; }}
        th {{ background: #f5f5f5; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 信号分析报告</h1>
        <p>生成时间: {datetime.now().isoformat()}</p>
    </div>
    
    <div class="chart">
        <h3>信号分布</h3>
        <img src="{charts.get('signal_distribution', '')}" alt="信号分布图">
    </div>
    
    <div class="chart">
        <h3>置信度分布</h3>
        <img src="{charts.get('confidence_distribution', '')}" alt="置信度分布图">
    </div>
    
    <h3>信号详情</h3>
    <table>
        <tr>
            <th>股票代码</th>
            <th>信号类型</th>
            <th>置信度</th>
            <th>触发价格</th>
            <th>时间</th>
        </tr>
"""
            
            for signal in signals:
                html_content += f"""
        <tr>
            <td>{signal.get('stock_code', '')}</td>
            <td>{signal.get('signal_type', '')}</td>
            <td>{signal.get('confidence', 0):.2f}</td>
            <td>{signal.get('trigger_price', 0):.2f}</td>
            <td>{signal.get('signal_date', '')}</td>
        </tr>
"""
            
            html_content += """
    </table>
</body>
</html>
"""
            
            # 保存HTML文件
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"reports/signal_report_{timestamp}.html"
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            return {
                'success': True,
                'filename': filename,
                'format': 'html',
                'size': len(html_content)
            }
            
        except Exception as e:
            self.logger.error(f"生成信号HTML报告失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def _generate_signal_json_report(self, signals: List[Dict]) -> Dict[str, Any]:
        """生成信号JSON报告"""
        try:
            report_data = {
                'generation_time': datetime.now().isoformat(),
                'signal_count': len(signals),
                'signals': signals
            }
            
            # 保存JSON文件
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"reports/signal_report_{timestamp}.json"
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(report_data, f, indent=2, ensure_ascii=False, default=str)
            
            return {
                'success': True,
                'filename': filename,
                'format': 'json',
                'size': os.path.getsize(filename)
            }
            
        except Exception as e:
            self.logger.error(f"生成信号JSON报告失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def _collect_performance_data(self) -> Dict[str, Any]:
        """收集绩效数据"""
        try:
            # 获取绩效分析数据
            performance_analysis = self.performance_tracker.batch_performance_analysis()
            
            # 获取观察池统计
            pool_stats = self.pool_manager.get_pool_statistics()
            
            return {
                'generation_time': datetime.now().isoformat(),
                'performance_analysis': performance_analysis,
                'pool_statistics': pool_stats,
                'system_metrics': {
                    'total_trades': 100,  # 模拟数据
                    'win_rate': 0.65,
                    'avg_return': 0.08,
                    'max_drawdown': -0.15
                }
            }
            
        except Exception as e:
            self.logger.error(f"收集绩效数据失败: {e}")
            return {}
    
    def _generate_dashboard_charts(self, performance_data: Dict) -> Dict[str, str]:
        """生成仪表板图表"""
        charts = {}
        try:
            # 绩效概览图
            charts['performance_overview'] = self._create_performance_overview_chart(performance_data)
            
            # 收益分布图
            charts['return_distribution'] = self._create_return_distribution_chart(performance_data)
            
        except Exception as e:
            self.logger.error(f"生成仪表板图表失败: {e}")
        
        return charts
    
    def _create_performance_overview_chart(self, performance_data: Dict) -> str:
        """创建绩效概览图"""
        try:
            metrics = performance_data.get('system_metrics', {})
            
            fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(12, 8))
            
            # 胜率饼图
            win_rate = metrics.get('win_rate', 0.65)
            ax1.pie([win_rate, 1-win_rate], labels=['胜', '负'], autopct='%1.1f%%', 
                   colors=['#28a745', '#dc3545'])
            ax1.set_title('胜率分布')
            
            # 收益率柱状图
            returns = [0.05, 0.08, -0.02, 0.12, 0.03]  # 模拟数据
            ax2.bar(range(len(returns)), returns, color=['#28a745' if r > 0 else '#dc3545' for r in returns])
            ax2.set_title('近期收益率')
            ax2.set_ylabel('收益率')
            
            # 交易量趋势
            volumes = [50, 65, 45, 80, 70]  # 模拟数据
            ax3.plot(volumes, marker='o')
            ax3.set_title('交易量趋势')
            ax3.set_ylabel('交易量')
            
            # 风险指标
            risk_metrics = ['夏普比率', '最大回撤', '波动率']
            risk_values = [1.2, -0.15, 0.18]
            colors = ['#28a745', '#dc3545', '#ffc107']
            ax4.bar(risk_metrics, risk_values, color=colors)
            ax4.set_title('风险指标')
            
            plt.tight_layout()
            
            # 转换为base64字符串
            buffer = BytesIO()
            plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
            buffer.seek(0)
            chart_data = base64.b64encode(buffer.getvalue()).decode()
            plt.close(fig)
            
            return f"data:image/png;base64,{chart_data}"
            
        except Exception as e:
            self.logger.error(f"创建绩效概览图失败: {e}")
            return ""
    
    def _create_return_distribution_chart(self, performance_data: Dict) -> str:
        """创建收益分布图"""
        try:
            # 模拟收益分布数据
            import numpy as np
            returns = np.random.normal(0.05, 0.15, 1000)  # 模拟正态分布收益
            
            fig, ax = plt.subplots(figsize=(10, 6))
            
            ax.hist(returns, bins=50, alpha=0.7, color='#667eea', edgecolor='black')
            ax.set_title('收益率分布', fontsize=14, fontweight='bold')
            ax.set_xlabel('收益率')
            ax.set_ylabel('频次')
            ax.grid(True, alpha=0.3)
            
            # 添加统计线
            mean_return = np.mean(returns)
            ax.axvline(mean_return, color='red', linestyle='--', label=f'平均收益: {mean_return:.2%}')
            ax.legend()
            
            # 转换为base64字符串
            buffer = BytesIO()
            plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
            buffer.seek(0)
            chart_data = base64.b64encode(buffer.getvalue()).decode()
            plt.close(fig)
            
            return f"data:image/png;base64,{chart_data}"
            
        except Exception as e:
            self.logger.error(f"创建收益分布图失败: {e}")
            return ""
    
    def _generate_dashboard_html(self, performance_data: Dict, charts: Dict) -> Dict[str, Any]:
        """生成仪表板HTML"""
        try:
            metrics = performance_data.get('system_metrics', {})
            
            html_content = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>绩效仪表板</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
        .dashboard {{ max-width: 1200px; margin: 0 auto; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                  color: white; padding: 30px; text-align: center; border-radius: 10px; margin-bottom: 20px; }}
        .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); 
                        gap: 20px; margin-bottom: 30px; }}
        .metric-card {{ background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .metric-value {{ font-size: 2em; font-weight: bold; color: #667eea; }}
        .metric-label {{ color: #666; margin-top: 5px; }}
        .chart-section {{ background: white; padding: 20px; border-radius: 10px; 
                         box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 20px; }}
        .chart-section img {{ max-width: 100%; height: auto; }}
    </style>
</head>
<body>
    <div class="dashboard">
        <div class="header">
            <h1>📊 绩效仪表板</h1>
            <p>实时监控系统表现 - {performance_data.get('generation_time', '')}</p>
        </div>
        
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-value">{metrics.get('total_trades', 0)}</div>
                <div class="metric-label">总交易数</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{metrics.get('win_rate', 0):.1%}</div>
                <div class="metric-label">胜率</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{metrics.get('avg_return', 0):.1%}</div>
                <div class="metric-label">平均收益率</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{metrics.get('max_drawdown', 0):.1%}</div>
                <div class="metric-label">最大回撤</div>
            </div>
        </div>
        
        <div class="chart-section">
            <h3>绩效概览</h3>
            <img src="{charts.get('performance_overview', '')}" alt="绩效概览图">
        </div>
        
        <div class="chart-section">
            <h3>收益分布</h3>
            <img src="{charts.get('return_distribution', '')}" alt="收益分布图">
        </div>
    </div>
</body>
</html>
"""
            
            # 保存HTML文件
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"reports/dashboard_{timestamp}.html"
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            return {
                'success': True,
                'filename': filename,
                'format': 'html',
                'size': len(html_content)
            }
            
        except Exception as e:
            self.logger.error(f"生成仪表板HTML失败: {e}")
            return {'success': False, 'error': str(e)}