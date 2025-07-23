#!/usr/bin/env python3
"""
Web仪表板

基于Flask的Web管理界面，提供：
- 实时数据监控仪表板
- 交互式配置管理
- 报告查看和下载
- 系统状态监控
"""

import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path

# 添加backend目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

try:
    from flask import Flask, render_template, jsonify, request, send_file, redirect, url_for
    from flask import Response
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False

from stock_pool_manager import StockPoolManager
from performance_tracker import PerformanceTracker
from report_generator import ReportGenerator
from enhanced_workflow_manager import EnhancedWorkflowManager

# 创建Flask应用
if HAS_FLASK:
    app = Flask(__name__)
    app.secret_key = 'trading_system_secret_key_2025'
else:
    app = None

class WebDashboard:
    """Web仪表板管理器"""
    
    def __init__(self, db_path: str = "stock_pool.db", config_path: str = "workflow_config.json"):
        """初始化Web仪表板"""
        self.db_path = db_path
        self.config_path = config_path
        
        # 初始化组件
        self.pool_manager = StockPoolManager(db_path)
        self.performance_tracker = PerformanceTracker(db_path)
        self.report_generator = ReportGenerator(db_path)
        self.workflow_manager = EnhancedWorkflowManager(config_path, db_path)
        
        self.logger = logging.getLogger(__name__)
        
        # 创建必要目录
        Path("templates").mkdir(exist_ok=True)
        Path("static").mkdir(exist_ok=True)
        
        # 创建HTML模板
        self._create_templates()
    
    def _create_templates(self):
        """创建HTML模板"""
        # 创建主页模板
        main_template = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>交易决策支持系统 - 控制台</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #f5f7fa;
            color: #333;
        }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 1rem 2rem;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .header h1 {
            font-size: 1.8rem;
            font-weight: 300;
        }
        .container {
            max-width: 1200px;
            margin: 2rem auto;
            padding: 0 1rem;
        }
        .dashboard-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }
        .card {
            background: white;
            border-radius: 8px;
            padding: 1.5rem;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            border-left: 4px solid #667eea;
        }
        .card h3 {
            color: #667eea;
            margin-bottom: 1rem;
            font-size: 1.2rem;
        }
        .stat-row {
            display: flex;
            justify-content: space-between;
            margin-bottom: 0.5rem;
        }
        .stat-value {
            font-weight: bold;
            color: #333;
        }
        .btn {
            background: #667eea;
            color: white;
            border: none;
            padding: 0.5rem 1rem;
            border-radius: 4px;
            cursor: pointer;
            text-decoration: none;
            display: inline-block;
            margin: 0.25rem;
        }
        .btn:hover {
            background: #5a6fd8;
        }
        .btn-success { background: #28a745; }
        .btn-warning { background: #ffc107; color: #333; }
        .btn-danger { background: #dc3545; }
        .status-indicator {
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            margin-right: 0.5rem;
        }
        .status-healthy { background: #28a745; }
        .status-warning { background: #ffc107; }
        .status-error { background: #dc3545; }
        .actions {
            text-align: center;
            margin: 2rem 0;
        }
        .log-container {
            background: #2d3748;
            color: #e2e8f0;
            padding: 1rem;
            border-radius: 8px;
            font-family: 'Courier New', monospace;
            font-size: 0.9rem;
            max-height: 300px;
            overflow-y: auto;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 交易决策支持系统控制台</h1>
    </div>
    
    <div class="container">
        <div class="dashboard-grid">
            <div class="card">
                <h3>📈 系统状态</h3>
                <div class="stat-row">
                    <span>系统状态:</span>
                    <span><span class="status-indicator status-healthy"></span>运行正常</span>
                </div>
                <div class="stat-row">
                    <span>最后更新:</span>
                    <span class="stat-value" id="last-update">{{ last_update }}</span>
                </div>
                <div class="stat-row">
                    <span>运行时间:</span>
                    <span class="stat-value">{{ uptime }}</span>
                </div>
            </div>
            
            <div class="card">
                <h3>🎯 观察池统计</h3>
                <div class="stat-row">
                    <span>总股票数:</span>
                    <span class="stat-value">{{ pool_stats.total_stocks }}</span>
                </div>
                <div class="stat-row">
                    <span>活跃股票:</span>
                    <span class="stat-value">{{ pool_stats.active_stocks }}</span>
                </div>
                <div class="stat-row">
                    <span>平均评分:</span>
                    <span class="stat-value">{{ "%.3f"|format(pool_stats.avg_score) }}</span>
                </div>
                <div class="stat-row">
                    <span>整体胜率:</span>
                    <span class="stat-value">{{ "%.1f%%"|format(pool_stats.overall_win_rate * 100) }}</span>
                </div>
            </div>
            
            <div class="card">
                <h3>📊 信号统计</h3>
                <div class="stat-row">
                    <span>总信号数:</span>
                    <span class="stat-value">{{ pool_stats.total_signals }}</span>
                </div>
                <div class="stat-row">
                    <span>成功信号:</span>
                    <span class="stat-value">{{ pool_stats.total_successes }}</span>
                </div>
                <div class="stat-row">
                    <span>最近7天:</span>
                    <span class="stat-value">{{ pool_stats.recent_signals }}</span>
                </div>
            </div>
        </div>
        
        <div class="actions">
            <h3>🎮 系统操作</h3>
            <a href="/run-workflow" class="btn btn-success">运行完整工作流</a>
            <a href="/run-phase1" class="btn">运行第一阶段</a>
            <a href="/run-phase2" class="btn">运行第二阶段</a>
            <a href="/run-phase3" class="btn">运行第三阶段</a>
            <a href="/generate-report" class="btn btn-warning">生成报告</a>
            <a href="/view-logs" class="btn">查看日志</a>
        </div>
        
        <div class="card">
            <h3>📋 最近活动</h3>
            <div class="log-container" id="activity-log">
                <div>{{ current_time }} - 系统启动</div>
                <div>{{ current_time }} - 数据库连接正常</div>
                <div>{{ current_time }} - 所有模块加载完成</div>
            </div>
        </div>
    </div>
    
    <script>
        // 自动刷新数据
        setInterval(function() {
            fetch('/api/status')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('last-update').textContent = data.last_update;
                    // 更新其他数据...
                });
        }, 30000); // 每30秒刷新一次
    </script>
</body>
</html>
        '''
        
        with open('templates/index.html', 'w', encoding='utf-8') as f:
            f.write(main_template)
    
    def get_dashboard_data(self):
        """获取仪表板数据"""
        try:
            pool_stats = self.pool_manager.get_pool_statistics()
            
            return {
                'pool_stats': pool_stats,
                'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'uptime': '运行中',
                'current_time': datetime.now().strftime('%H:%M:%S')
            }
        except Exception as e:
            self.logger.error(f"获取仪表板数据失败: {e}")
            return {
                'pool_stats': {},
                'last_update': 'N/A',
                'uptime': 'N/A',
                'current_time': datetime.now().strftime('%H:%M:%S')
            }


# Flask路由定义
if HAS_FLASK and app:
    
    dashboard = WebDashboard()
    
    @app.route('/')
    def index():
        """主页"""
        try:
            data = dashboard.get_dashboard_data()
            return render_template('index.html', **data)
        except Exception as e:
            return f"Error: {e}", 500
    
    @app.route('/api/status')
    def api_status():
        """API状态接口"""
        try:
            data = dashboard.get_dashboard_data()
            return jsonify(data)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/run-workflow')
    def run_workflow():
        """运行完整工作流"""
        try:
            # 执行工作流
            results = dashboard.workflow_manager.run_enhanced_phase1()
            if results.get('success'):
                results2 = dashboard.workflow_manager.run_enhanced_phase2()
                if results2.get('success'):
                    results3 = dashboard.workflow_manager.run_enhanced_phase3()
                    
                    return jsonify({
                        'success': True,
                        'message': '工作流执行完成',
                        'results': {
                            'phase1': results,
                            'phase2': results2,
                            'phase3': results3
                        }
                    })
            
            return jsonify({'success': False, 'error': '工作流执行失败'})
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})
    
    @app.route('/run-phase<int:phase>')
    def run_phase(phase):
        """运行指定阶段"""
        try:
            if phase == 1:
                result = dashboard.workflow_manager.run_enhanced_phase1()
            elif phase == 2:
                result = dashboard.workflow_manager.run_enhanced_phase2()
            elif phase == 3:
                result = dashboard.workflow_manager.run_enhanced_phase3()
            else:
                return jsonify({'success': False, 'error': '无效的阶段号'})
            
            return jsonify(result)
            
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})
    
    @app.route('/generate-report')
    def generate_report():
        """生成报告"""
        try:
            result = dashboard.report_generator.generate_comprehensive_report('html')
            if result.get('success'):
                return jsonify({
                    'success': True,
                    'message': '报告生成成功',
                    'filename': result.get('filename')
                })
            else:
                return jsonify({'success': False, 'error': result.get('error')})
                
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})
    
    @app.route('/view-logs')
    def view_logs():
        """查看日志"""
        try:
            log_files = ['enhanced_workflow.log', 'workflow.log']
            logs = []
            
            for log_file in log_files:
                if os.path.exists(log_file):
                    with open(log_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        logs.extend(lines[-50:])  # 最近50行
            
            return '<pre>' + ''.join(logs) + '</pre>'
            
        except Exception as e:
            return f"Error reading logs: {e}"
    
    @app.route('/api/pool-stats')
    def api_pool_stats():
        """观察池统计API"""
        try:
            stats = dashboard.pool_manager.get_pool_statistics()
            return jsonify(stats)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    
    @app.route('/api/recent-signals')
    def api_recent_signals():
        """最近信号API"""
        try:
            # 这里应该从数据库获取最近的信号
            signals = []  # 暂时返回空列表
            return jsonify(signals)
        except Exception as e:
            return jsonify({'error': str(e)}), 500


def main():
    """主函数"""
    if not HAS_FLASK:
        print("❌ Flask未安装，无法启动Web界面")
        print("请安装Flask: pip install flask")
        return
    
    print("🚀 启动交易决策支持系统Web控制台...")
    print("📊 访问地址: http://localhost:5000")
    print("🔧 按Ctrl+C停止服务")
    
    try:
        app.run(host='0.0.0.0', port=5000, debug=True)
    except KeyboardInterrupt:
        print("\n👋 Web控制台已停止")
    except Exception as e:
        print(f"❌ 启动失败: {e}")


if __name__ == "__main__":
    main()