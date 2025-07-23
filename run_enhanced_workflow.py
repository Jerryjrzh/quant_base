#!/usr/bin/env python3
"""
增强版三阶段交易决策支持系统 - 主控脚本

集成了SQLite数据库的高级工作流系统，提供：
- 数据库驱动的核心观察池管理
- 高级绩效跟踪和分析
- 智能信号生成和验证
- 自适应学习机制

使用示例：
    python run_enhanced_workflow.py                    # 运行完整工作流
    python run_enhanced_workflow.py --phase phase1    # 只运行第一阶段
    python run_enhanced_workflow.py --status          # 查看系统状态
    python run_enhanced_workflow.py --migrate         # 从JSON迁移到数据库
"""

import argparse
import sys
import os
import json
from datetime import datetime
from pathlib import Path

# 添加backend目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from enhanced_workflow_manager import EnhancedWorkflowManager
from stock_pool_manager import StockPoolManager


def print_enhanced_banner():
    """打印增强版系统横幅"""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║            增强版三阶段交易决策支持系统                        ║
║         Enhanced Three-Phase Trading Decision System         ║
╠══════════════════════════════════════════════════════════════╣
║  🚀 Phase 1: 智能深度海选与多目标优化                         ║
║  🎯 Phase 2: 智能信号生成与验证                              ║
║  📊 Phase 3: 智能绩效跟踪与自适应调整                         ║
╠══════════════════════════════════════════════════════════════╣
║  ✨ 新特性: SQLite数据库 | 高级分析 | 自适应学习              ║
╚══════════════════════════════════════════════════════════════╝
"""
    print(banner)


def show_enhanced_status(manager: EnhancedWorkflowManager):
    """显示增强版系统状态"""
    print("\n=== 增强版系统状态 ===")
    
    try:
        status = manager.get_enhanced_status()
        
        # 观察池统计
        pool_stats = status.get('pool_statistics', {})
        print(f"📊 观察池统计:")
        print(f"  总股票数: {pool_stats.get('total_stocks', 0)}")
        print(f"  活跃股票: {pool_stats.get('active_stocks', 0)}")
        print(f"  平均评分: {pool_stats.get('avg_score', 0):.3f}")
        print(f"  平均信任度: {pool_stats.get('avg_credibility', 0):.3f}")
        print(f"  总信号数: {pool_stats.get('total_signals', 0)}")
        print(f"  总成功数: {pool_stats.get('total_successes', 0)}")
        print(f"  整体胜率: {pool_stats.get('overall_win_rate', 0):.1%}")
        
        # 评级分布
        grade_dist = pool_stats.get('grade_distribution', {})
        if grade_dist:
            print(f"  评级分布: {dict(grade_dist)}")
        
        # 最近绩效
        recent_perf = status.get('recent_performance', {})
        print(f"\n📈 最近绩效:")
        print(f"  7天信号数: {recent_perf.get('last_7_days_signals', 0)}")
        print(f"  成功率: {recent_perf.get('success_rate', 0):.1%}")
        print(f"  平均收益: {recent_perf.get('avg_return', 0):.1%}")
        
        # 系统健康
        health = status.get('system_health', {})
        print(f"\n🏥 系统健康:")
        print(f"  数据库状态: {health.get('database_status', 'unknown')}")
        print(f"  磁盘使用: {health.get('disk_usage', 'unknown')}")
        print(f"  内存使用: {health.get('memory_usage', 'unknown')}")
        
        print(f"\n🕒 最后更新: {status.get('last_updated', 'unknown')}")
        
    except Exception as e:
        print(f"❌ 获取状态失败: {e}")


def migrate_from_json(manager: EnhancedWorkflowManager):
    """从JSON文件迁移数据到数据库"""
    print("\n=== 数据迁移 ===")
    
    json_files = [
        'core_stock_pool.json',
        'signal_history.json'
    ]
    
    migrated_count = 0
    
    for json_file in json_files:
        if os.path.exists(json_file):
            try:
                print(f"📁 迁移文件: {json_file}")
                
                if json_file == 'core_stock_pool.json':
                    # 迁移核心观察池
                    if manager.pool_manager.import_from_json(json_file):
                        print(f"  ✅ 核心观察池迁移成功")
                        migrated_count += 1
                    else:
                        print(f"  ❌ 核心观察池迁移失败")
                
                elif json_file == 'signal_history.json':
                    # 迁移信号历史
                    with open(json_file, 'r', encoding='utf-8') as f:
                        signals = json.load(f)
                    
                    signal_count = 0
                    for signal in signals:
                        signal_data = {
                            'stock_code': signal.get('stock_code'),
                            'signal_type': signal.get('action', 'buy'),
                            'confidence': signal.get('confidence', 0.5),
                            'trigger_price': signal.get('current_price'),
                            'signal_date': signal.get('timestamp', datetime.now().isoformat()),
                            'status': signal.get('status', 'pending')
                        }
                        
                        if manager.pool_manager.record_signal(signal_data):
                            signal_count += 1
                    
                    print(f"  ✅ 迁移了 {signal_count} 个信号")
                    migrated_count += 1
                    
            except Exception as e:
                print(f"  ❌ 迁移 {json_file} 失败: {e}")
        else:
            print(f"📁 文件不存在: {json_file}")
    
    print(f"\n📊 迁移完成: {migrated_count}/{len(json_files)} 个文件成功迁移")
    
    # 显示迁移后的状态
    show_enhanced_status(manager)


def export_database_status(manager: EnhancedWorkflowManager):
    """导出数据库状态报告"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'reports/database_status_{timestamp}.json'
        
        status = manager.get_enhanced_status()
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(status, f, indent=2, ensure_ascii=False)
        
        print(f"📄 数据库状态报告已导出: {filename}")
        
    except Exception as e:
        print(f"❌ 导出状态报告失败: {e}")


def validate_enhanced_environment():
    """验证增强版运行环境"""
    errors = []
    warnings = []
    
    # 检查Python版本
    if sys.version_info < (3, 7):
        errors.append("需要Python 3.7或更高版本")
    
    # 检查必要的目录
    required_dirs = ['backend', 'data', 'reports']
    for dir_name in required_dirs:
        if not os.path.exists(dir_name):
            Path(dir_name).mkdir(parents=True, exist_ok=True)
            warnings.append(f"已创建目录: {dir_name}")
    
    # 检查关键文件
    required_files = [
        'backend/stock_pool_manager.py',
        'backend/enhanced_workflow_manager.py'
    ]
    for file_path in required_files:
        if not os.path.exists(file_path):
            errors.append(f"缺少关键文件: {file_path}")
    
    # 检查SQLite支持
    try:
        import sqlite3
        print("✅ SQLite支持: 可用")
    except ImportError:
        errors.append("SQLite支持不可用")
    
    if errors:
        print("❌ 环境验证失败:")
        for error in errors:
            print(f"  - {error}")
        return False
    
    if warnings:
        print("⚠️  环境警告:")
        for warning in warnings:
            print(f"  - {warning}")
    
    print("✅ 增强版环境验证通过")
    return True


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='增强版三阶段交易决策支持系统主控脚本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  %(prog)s                    运行完整增强版工作流
  %(prog)s --phase phase1     只运行第一阶段（智能深度海选）
  %(prog)s --status           查看增强版系统状态
  %(prog)s --migrate          从JSON迁移到数据库
  %(prog)s --export-status    导出数据库状态报告
        """
    )
    
    parser.add_argument('--phase', 
                       choices=['phase1', 'phase2', 'phase3', 'all'], 
                       default='all',
                       help='要执行的阶段 (默认: all)')
    
    parser.add_argument('--config', 
                       default='workflow_config.json',
                       help='配置文件路径 (默认: workflow_config.json)')
    
    parser.add_argument('--database', 
                       default='stock_pool.db',
                       help='数据库文件路径 (默认: stock_pool.db)')
    
    parser.add_argument('--force', 
                       action='store_true',
                       help='强制执行，忽略时间间隔限制')
    
    parser.add_argument('--dry-run', 
                       action='store_true',
                       help='试运行模式，不执行实际操作')
    
    parser.add_argument('--status', 
                       action='store_true',
                       help='显示增强版系统状态')
    
    parser.add_argument('--migrate', 
                       action='store_true',
                       help='从JSON文件迁移数据到数据库')
    
    parser.add_argument('--export-status', 
                       action='store_true',
                       help='导出数据库状态报告')
    
    parser.add_argument('--verbose', '-v', 
                       action='store_true',
                       help='详细输出模式')
    
    parser.add_argument('--no-banner', 
                       action='store_true',
                       help='不显示横幅')
    
    args = parser.parse_args()
    
    # 显示横幅
    if not args.no_banner:
        print_enhanced_banner()
    
    # 验证环境
    if not validate_enhanced_environment():
        sys.exit(1)
    
    try:
        # 初始化增强版工作流管理器
        manager = EnhancedWorkflowManager(args.config, args.database)
        
        # 处理特殊命令
        if args.status:
            show_enhanced_status(manager)
            return
        
        if args.migrate:
            migrate_from_json(manager)
            return
        
        if args.export_status:
            export_database_status(manager)
            return
        
        # 试运行模式
        if args.dry_run:
            print("🔍 试运行模式：将模拟执行但不进行实际操作")
            return
        
        # 确定要执行的阶段
        if args.phase == 'all':
            phases = ['phase1', 'phase2', 'phase3']
            print("📋 将执行完整的增强版三阶段工作流")
        else:
            phases = [args.phase]
            phase_names = {
                'phase1': '智能深度海选与多目标优化',
                'phase2': '智能信号生成与验证', 
                'phase3': '智能绩效跟踪与自适应调整'
            }
            print(f"📋 将执行: {phase_names.get(args.phase, args.phase)}")
        
        # 显示执行前状态
        if args.verbose:
            show_enhanced_status(manager)
        
        print(f"\n🚀 开始执行增强版工作流... ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        
        # 执行工作流
        results = {}
        
        for phase in phases:
            print(f"\n⚡ 执行 {phase}...")
            
            if phase == 'phase1':
                result = manager.run_enhanced_phase1()
            elif phase == 'phase2':
                result = manager.run_enhanced_phase2()
            elif phase == 'phase3':
                result = manager.run_enhanced_phase3()
            else:
                continue
            
            results[phase] = result
        
        # 显示执行结果
        print(f"\n📊 增强版工作流执行完成 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        print("=" * 70)
        
        success_count = 0
        for phase, result in results.items():
            phase_names = {
                'phase1': '智能深度海选与多目标优化',
                'phase2': '智能信号生成与验证',
                'phase3': '智能绩效跟踪与自适应调整'
            }
            phase_name = phase_names.get(phase, phase)
            
            if result.get('success'):
                print(f"✅ {phase_name}: 成功")
                success_count += 1
                
                # 显示详细结果
                if args.verbose:
                    if 'processed_stocks' in result:
                        print(f"   处理股票: {result['processed_stocks']}")
                    if 'high_quality_count' in result:
                        print(f"   高质量股票: {result['high_quality_count']}")
                    if 'signals_generated' in result:
                        print(f"   生成信号: {result['signals_generated']}")
                    if 'avg_confidence' in result:
                        print(f"   平均置信度: {result['avg_confidence']:.3f}")
            else:
                print(f"❌ {phase_name}: 失败")
                if args.verbose:
                    print(f"   错误: {result.get('error', '未知错误')}")
        
        print("=" * 70)
        print(f"总结: {success_count}/{len(results)} 个阶段成功执行")
        
        # 显示执行后状态
        if args.verbose:
            print("\n执行后系统状态:")
            show_enhanced_status(manager)
        
        # 自动导出状态报告
        if success_count > 0:
            export_database_status(manager)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断执行")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 增强版工作流执行失败: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()