#!/usr/bin/env python3
"""
三阶段交易决策支持系统 - 快速启动脚本

这个脚本提供了一个简化的入口点，用于快速体验系统功能。
适合初次使用或演示目的。
"""

import os
import sys
import json
from datetime import datetime
from pathlib import Path

def setup_demo_environment():
    """设置演示环境"""
    print("🔧 正在设置演示环境...")
    
    # 创建必要的目录
    dirs = ['analysis_cache', 'reports', 'logs', 'data']
    for dir_name in dirs:
        Path(dir_name).mkdir(exist_ok=True)
    
    # 创建示例核心观察池
    demo_pool = [
        {
            "stock_code": "sh000001",
            "score": 0.85,
            "params": {
                "pre_entry_discount": 0.02,
                "moderate_stop": 0.05
            },
            "analysis_date": datetime.now().isoformat()
        },
        {
            "stock_code": "sz000001", 
            "score": 0.78,
            "params": {
                "pre_entry_discount": 0.015,
                "moderate_stop": 0.04
            },
            "analysis_date": datetime.now().isoformat()
        }
    ]
    
    with open('core_stock_pool.json', 'w', encoding='utf-8') as f:
        json.dump(demo_pool, f, indent=2, ensure_ascii=False)
    
    print("✅ 演示环境设置完成")


def show_demo_menu():
    """显示演示菜单"""
    menu = """
╔══════════════════════════════════════════════════════════════╗
║                    快速启动演示菜单                            ║
╚══════════════════════════════════════════════════════════════╝

请选择要演示的功能：

1. 查看系统状态
2. 运行第一阶段 (深度海选与参数优化) - 演示模式
3. 运行第二阶段 (每日验证与信号触发) - 演示模式  
4. 运行第三阶段 (绩效跟踪与反馈) - 演示模式
5. 运行完整工作流 - 演示模式
6. 查看配置文件
7. 查看帮助信息
0. 退出

注意：演示模式使用模拟数据，不会进行实际的股票分析。
"""
    print(menu)


def demo_phase1():
    """演示第一阶段"""
    print("\n🔍 演示第一阶段：深度海选与参数优化")
    print("-" * 50)
    
    print("正在模拟批量参数优化...")
    print("  ✓ 处理股票: sh000001 - 得分: 0.85")
    print("  ✓ 处理股票: sz000001 - 得分: 0.78") 
    print("  ✓ 处理股票: sz000002 - 得分: 0.65")
    print("  ✗ 处理股票: sz000003 - 得分: 0.45 (低于阈值)")
    
    print("\n筛选结果:")
    print("  - 总处理股票数: 4")
    print("  - 高质量股票数: 3")
    print("  - 平均得分: 0.76")
    print("  - 核心观察池已更新")
    
    print("\n✅ 第一阶段演示完成")


def demo_phase2():
    """演示第二阶段"""
    print("\n📊 演示第二阶段：每日验证与信号触发")
    print("-" * 50)
    
    print("正在验证核心观察池中的股票...")
    print("  ✓ sh000001: 检测到买入信号 (置信度: 0.82)")
    print("  ○ sz000001: 无新信号")
    print("  ✓ sz000002: 检测到卖出信号 (置信度: 0.75)")
    
    print("\n生成的交易信号:")
    print("  1. sh000001 - 买入建议")
    print("     入场价位: 3.25")
    print("     止损位: 3.09")
    print("     止盈位: 3.58")
    print("")
    print("  2. sz000002 - 卖出建议")
    print("     当前价位: 12.80")
    print("     建议卖出价: 12.75")
    
    print("\n✅ 第二阶段演示完成")
    print("📄 交易报告已生成到 reports/ 目录")


def demo_phase3():
    """演示第三阶段"""
    print("\n📈 演示第三阶段：绩效跟踪与反馈")
    print("-" * 50)
    
    print("正在分析历史信号表现...")
    print("  ✓ 更新绩效记录: 15条")
    print("  ✓ sh000001: 近期胜率 75% (历史: 70%) - 信任度提升")
    print("  ✗ sz000003: 近期胜率 30% (历史: 65%) - 信任度下降")
    
    print("\n核心观察池调整:")
    print("  ↑ sh000001: 评级提升 (A → A+)")
    print("  ↓ sz000003: 评级下降 (B → C)")
    print("  ✗ sz000004: 移出观察池 (连续表现不佳)")
    
    print("\n✅ 第三阶段演示完成")


def demo_full_workflow():
    """演示完整工作流"""
    print("\n🚀 演示完整三阶段工作流")
    print("=" * 60)
    
    demo_phase1()
    print("\n" + "="*30)
    demo_phase2() 
    print("\n" + "="*30)
    demo_phase3()
    
    print("\n" + "="*60)
    print("🎉 完整工作流演示完成！")


def show_config():
    """显示配置文件内容"""
    print("\n📋 当前配置文件内容:")
    print("-" * 50)
    
    if os.path.exists('workflow_config.json'):
        with open('workflow_config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        print("第一阶段配置:")
        print(f"  - 启用: {config['phase1']['enabled']}")
        print(f"  - 执行频率: {config['phase1']['frequency_days']}天")
        print(f"  - 最大处理股票数: {config['phase1']['max_stocks']}")
        
        print("\n第二阶段配置:")
        print(f"  - 启用: {config['phase2']['enabled']}")
        print(f"  - 执行频率: {config['phase2']['frequency_days']}天")
        print(f"  - 核心池大小: {config['phase2']['core_pool_size']}")
        
        print("\n第三阶段配置:")
        print(f"  - 启用: {config['phase3']['enabled']}")
        print(f"  - 跟踪天数: {config['phase3']['tracking_days']}")
        print(f"  - 绩效阈值: {config['phase3']['performance_threshold']}")
    else:
        print("❌ 配置文件不存在，请先运行系统初始化")


def show_help():
    """显示帮助信息"""
    help_text = """
📚 系统帮助信息

1. 系统概述:
   这是一个三阶段的交易决策支持系统，旨在通过系统化的方法
   筛选和跟踪高质量的交易机会。

2. 三个阶段说明:
   
   第一阶段 - 深度海选与参数优化:
   • 对大量股票进行参数优化
   • 筛选出高质量的股票池
   • 为每只股票找到最优参数
   
   第二阶段 - 每日验证与信号触发:
   • 对核心观察池进行快速验证
   • 检测新的交易信号
   • 生成具体的交易建议
   
   第三阶段 - 绩效跟踪与反馈:
   • 跟踪信号的实际表现
   • 动态调整核心观察池
   • 持续优化系统效果

3. 文件说明:
   • workflow_config.json: 系统配置文件
   • core_stock_pool.json: 核心观察池数据
   • reports/: 每日交易报告
   • analysis_cache/: 分析结果缓存

4. 实际使用:
   演示完成后，可以使用以下命令运行实际系统:
   python run_workflow.py --status    # 查看状态
   python run_workflow.py --phase phase2  # 运行第二阶段
   python run_workflow.py             # 运行完整工作流
"""
    print(help_text)


def main():
    """主函数"""
    print("🎯 三阶段交易决策支持系统 - 快速启动")
    print("=" * 60)
    
    # 设置演示环境
    setup_demo_environment()
    
    while True:
        show_demo_menu()
        
        try:
            choice = input("\n请输入选项 (0-7): ").strip()
            
            if choice == '0':
                print("\n👋 感谢使用！")
                break
            elif choice == '1':
                # 导入并显示系统状态
                try:
                    from workflow_manager import WorkflowManager
                    manager = WorkflowManager()
                    from run_workflow import show_system_status
                    show_system_status(manager)
                except ImportError:
                    print("\n📊 系统状态 (演示模式)")
                    print("  - 核心观察池: 2只股票")
                    print("  - 最后运行: 演示模式")
                    print("  - 系统状态: 正常")
                    
            elif choice == '2':
                demo_phase1()
            elif choice == '3':
                demo_phase2()
            elif choice == '4':
                demo_phase3()
            elif choice == '5':
                demo_full_workflow()
            elif choice == '6':
                show_config()
            elif choice == '7':
                show_help()
            else:
                print("❌ 无效选项，请重新选择")
                
        except KeyboardInterrupt:
            print("\n\n👋 用户中断，退出程序")
            break
        except Exception as e:
            print(f"\n❌ 发生错误: {e}")
        
        input("\n按回车键继续...")


if __name__ == "__main__":
    main()