#!/usr/bin/env python3
"""
三阶段交易决策支持系统 - 主控脚本

这是系统的主入口点，提供简化的命令行接口来运行不同的工作流阶段。

使用示例：
    python run_workflow.py                    # 运行完整工作流
    python run_workflow.py --phase phase1    # 只运行第一阶段
    python run_workflow.py --phase phase2    # 只运行第二阶段
    python run_workflow.py --force           # 强制运行，忽略时间限制
    python run_workflow.py --status          # 查看系统状态
"""

import argparse
import sys
import os
import json
from datetime import datetime
from pathlib import Path

# 导入工作流管理器
from workflow_manager import WorkflowManager


def print_banner():
    """打印系统横幅"""
    banner = """
╔══════════════════════════════════════════════════════════════╗
║                三阶段交易决策支持系统                          ║
║                Three-Phase Trading Decision System           ║
╠══════════════════════════════════════════════════════════════╣
║  Phase 1: 深度海选与参数优化 (Deep Scan & Optimization)      ║
║  Phase 2: 每日验证与信号触发 (Daily Verify & Signal)         ║
║  Phase 3: 绩效跟踪与反馈 (Performance Track & Feedback)      ║
╚══════════════════════════════════════════════════════════════╝
"""
    print(banner)


def show_system_status(manager: WorkflowManager):
    """显示系统状态"""
    print("\n=== 系统状态 ===")
    
    # 获取工作流状态
    state = manager.get_workflow_state()
    
    print(f"总运行次数: {state.get('total_runs', 0)}")
    print(f"第一阶段最后运行: {state.get('phase1_last_run', '从未运行')}")
    print(f"第二阶段最后运行: {state.get('phase2_last_run', '从未运行')}")
    print(f"第三阶段最后运行: {state.get('phase3_last_run', '从未运行')}")
    
    # 检查核心观察池状态
    core_pool = manager._load_core_pool()
    print(f"核心观察池股票数量: {len(core_pool)}")
    
    # 检查各阶段是否应该运行
    print("\n=== 阶段状态 ===")
    for phase in ['phase1', 'phase2', 'phase3']:
        should_run = manager.should_run_phase(phase, state)
        enabled = manager.config[phase]['enabled']
        frequency = manager.config[phase]['frequency_days']
        
        status = "✓ 可运行" if should_run and enabled else "⏸ 等待中"
        if not enabled:
            status = "✗ 已禁用"
        
        print(f"{phase}: {status} (频率: {frequency}天)")
    
    # 显示最近的报告文件
    reports_dir = Path("reports")
    if reports_dir.exists():
        report_files = list(reports_dir.glob("*.json"))
        if report_files:
            latest_report = max(report_files, key=lambda x: x.stat().st_mtime)
            print(f"\n最新报告: {latest_report.name}")


def show_help():
    """显示详细帮助信息"""
    help_text = """
详细使用说明：

1. 基本命令：
   python run_workflow.py                 # 运行完整的三阶段工作流
   python run_workflow.py --status       # 查看系统当前状态
   python run_workflow.py --help         # 显示帮助信息

2. 单独运行各阶段：
   python run_workflow.py --phase phase1 # 深度海选与参数优化
   python run_workflow.py --phase phase2 # 每日验证与信号触发
   python run_workflow.py --phase phase3 # 绩效跟踪与反馈

3. 高级选项：
   --force                               # 强制运行，忽略时间间隔限制
   --dry-run                            # 试运行模式，不执行实际操作
   --config CONFIG_FILE                 # 指定配置文件路径
   --verbose                            # 详细输出模式

4. 配置文件：
   系统使用 workflow_config.json 作为配置文件
   可以通过编辑此文件来调整各阶段的参数和行为

5. 输出文件：
   - workflow.log: 系统运行日志
   - core_stock_pool.json: 核心观察池数据
   - reports/: 每日交易信号报告
   - analysis_cache/: 参数优化缓存

6. 系统要求：
   - Python 3.7+
   - 相关依赖包已安装
   - 有效的股票数据源配置
"""
    print(help_text)


def validate_environment():
    """验证运行环境"""
    errors = []
    
    # 检查Python版本
    if sys.version_info < (3, 7):
        errors.append("需要Python 3.7或更高版本")
    
    # 检查必要的目录
    required_dirs = ['backend', 'data']
    for dir_name in required_dirs:
        if not os.path.exists(dir_name):
            errors.append(f"缺少必要目录: {dir_name}")
    
    # 检查关键文件
    required_files = [
        'backend/parallel_optimizer.py',
        'backend/trading_advisor.py'
    ]
    for file_path in required_files:
        if not os.path.exists(file_path):
            errors.append(f"缺少关键文件: {file_path}")
    
    if errors:
        print("❌ 环境验证失败:")
        for error in errors:
            print(f"  - {error}")
        return False
    
    print("✅ 环境验证通过")
    return True


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='三阶段交易决策支持系统主控脚本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  %(prog)s                    运行完整工作流
  %(prog)s --phase phase1     只运行第一阶段
  %(prog)s --status           查看系统状态
  %(prog)s --help-detailed    显示详细帮助
        """
    )
    
    parser.add_argument('--phase', 
                       choices=['phase1', 'phase2', 'phase3', 'all'], 
                       default='all',
                       help='要执行的阶段 (默认: all)')
    
    parser.add_argument('--config', 
                       default='workflow_config.json',
                       help='配置文件路径 (默认: workflow_config.json)')
    
    parser.add_argument('--force', 
                       action='store_true',
                       help='强制执行，忽略时间间隔限制')
    
    parser.add_argument('--dry-run', 
                       action='store_true',
                       help='试运行模式，不执行实际操作')
    
    parser.add_argument('--status', 
                       action='store_true',
                       help='显示系统状态')
    
    parser.add_argument('--verbose', '-v', 
                       action='store_true',
                       help='详细输出模式')
    
    parser.add_argument('--help-detailed', 
                       action='store_true',
                       help='显示详细帮助信息')
    
    parser.add_argument('--no-banner', 
                       action='store_true',
                       help='不显示横幅')
    
    args = parser.parse_args()
    
    # 显示详细帮助
    if args.help_detailed:
        show_help()
        return
    
    # 显示横幅
    if not args.no_banner:
        print_banner()
    
    # 验证环境
    if not validate_environment():
        sys.exit(1)
    
    try:
        # 初始化工作流管理器
        manager = WorkflowManager(args.config)
        
        # 显示状态
        if args.status:
            show_system_status(manager)
            return
        
        # 试运行模式
        if args.dry_run:
            print("🔍 试运行模式：将模拟执行但不进行实际操作")
            manager.logger.info("试运行模式启动")
        
        # 确定要执行的阶段
        if args.phase == 'all':
            phases = ['phase1', 'phase2', 'phase3']
            print("📋 将执行完整的三阶段工作流")
        else:
            phases = [args.phase]
            phase_names = {
                'phase1': '深度海选与参数优化',
                'phase2': '每日验证与信号触发', 
                'phase3': '绩效跟踪与反馈'
            }
            print(f"📋 将执行: {phase_names.get(args.phase, args.phase)}")
        
        # 强制执行模式
        if args.force:
            print("⚡ 强制执行模式：忽略时间间隔限制")
            for phase in phases:
                manager.config[phase]['frequency_days'] = 0
        
        # 显示执行前状态
        if args.verbose:
            show_system_status(manager)
        
        print(f"\n🚀 开始执行工作流... ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        
        # 执行工作流
        results = manager.run_workflow(phases)
        
        # 显示执行结果
        print(f"\n📊 工作流执行完成 ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
        print("=" * 60)
        
        success_count = 0
        for phase, result in results.items():
            phase_names = {
                'phase1': '深度海选与参数优化',
                'phase2': '每日验证与信号触发',
                'phase3': '绩效跟踪与反馈'
            }
            phase_name = phase_names.get(phase, phase)
            
            if result.get('skipped'):
                print(f"⏸  {phase_name}: 跳过 ({result['reason']})")
            elif result.get('success'):
                print(f"✅ {phase_name}: 成功")
                success_count += 1
                
                # 显示详细结果
                if args.verbose and 'processed_stocks' in result:
                    print(f"   处理股票: {result['processed_stocks']}")
                if args.verbose and 'signals_generated' in result:
                    print(f"   生成信号: {result['signals_generated']}")
            else:
                print(f"❌ {phase_name}: 失败")
                if args.verbose:
                    print(f"   错误: {result.get('error', '未知错误')}")
        
        print("=" * 60)
        print(f"总结: {success_count}/{len(results)} 个阶段成功执行")
        
        # 显示执行后状态
        if args.verbose:
            print("\n执行后系统状态:")
            show_system_status(manager)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断执行")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 工作流执行失败: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()