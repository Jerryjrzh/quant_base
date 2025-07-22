#!/usr/bin/env python3
"""
快速启动脚本 - 引导用户完成完整的分析流程
"""

import sys
import os
import subprocess
from datetime import datetime

def print_header(title):
    """打印标题"""
    print(f"\n{'='*60}")
    print(f"🎯 {title}")
    print('='*60)

def print_step(step_num, title):
    """打印步骤"""
    print(f"\n📋 步骤 {step_num}: {title}")
    print('-'*40)

def run_command_interactive(command, description):
    """交互式运行命令"""
    print(f"\n🔄 即将执行: {description}")
    print(f"命令: {command}")
    
    choice = input("\n是否执行此命令? (y/n/s=跳过): ").lower().strip()
    
    if choice == 'n':
        print("❌ 用户取消操作")
        return False
    elif choice == 's':
        print("⏭️ 跳过此步骤")
        return True
    
    try:
        print(f"\n⏳ 正在执行...")
        result = subprocess.run(command, shell=True)
        if result.returncode == 0:
            print(f"✅ {description} 完成")
            return True
        else:
            print(f"❌ {description} 失败")
            return False
    except Exception as e:
        print(f"❌ 执行失败: {e}")
        return False

def guided_workflow():
    """引导式工作流程"""
    print_header("股票交易分析引导式操作流程")
    print("🎯 本脚本将引导你完成从数据验证到交易决策的完整流程")
    print("💡 每个步骤都可以选择执行、跳过或退出")
    
    # 获取用户关注的股票
    print(f"\n📊 请输入你要分析的股票代码（用空格分隔，如: sz300290 sh000001）:")
    user_stocks = input("股票代码: ").strip().lower()
    
    if not user_stocks:
        target_stocks = ['sz300290', 'sh000001', 'sz000001']
        print(f"使用默认股票: {' '.join(target_stocks)}")
    else:
        target_stocks = user_stocks.split()
        print(f"分析目标股票: {' '.join(target_stocks)}")
    
    # 第一阶段：数据验证
    print_step(1, "数据验证与系统检查")
    
    if not run_command_interactive("python validate_all_strategies.py", "系统功能验证"):
        print("⚠️ 系统验证失败，建议检查环境配置")
        if input("是否继续? (y/n): ").lower() != 'y':
            return
    
    # 验证目标股票数据
    print(f"\n🔍 验证目标股票数据...")
    for stock in target_stocks[:2]:  # 只验证前两只
        run_command_interactive(f"python get_trading_advice.py {stock}", f"验证 {stock} 数据")
    
    # 第二阶段：初步筛选
    print_step(2, "初步筛选分析")
    
    run_command_interactive("python run_enhanced_screening.py sample", "样本股票池筛选")
    
    print(f"\n📋 查看筛选结果...")
    print("请查看生成的分析报告，识别高评分股票")
    input("按回车键继续...")
    
    # 第三阶段：深度分析
    print_step(3, "深度分析")
    
    for stock in target_stocks:
        if run_command_interactive(f"python run_enhanced_screening.py {stock}", f"{stock} 深度分析"):
            # 显示分析结果摘要
            try:
                result = subprocess.run(f"python get_trading_advice.py {stock}", 
                                      shell=True, capture_output=True, text=True)
                if result.returncode == 0:
                    print(f"\n📊 {stock} 交易建议摘要:")
                    lines = result.stdout.split('\n')
                    for line in lines:
                        if any(keyword in line for keyword in ['价格:', '信号:', '策略:', '价位']):
                            print(f"  {line}")
            except:
                pass
    
    # 第四阶段：配置对比
    print_step(4, "配置对比分析")
    
    for stock in target_stocks[:2]:  # 限制前两只股票
        run_command_interactive(f"python config_tool.py compare {stock}", f"{stock} 配置对比")
    
    # 第五阶段：参数优化
    print_step(5, "参数优化（可选）")
    
    print("⚠️ 参数优化耗时较长，建议选择1-2只重点股票")
    optimize_choice = input("是否进行参数优化? (y/n): ").lower()
    
    if optimize_choice == 'y':
        optimize_stocks = target_stocks[:2]  # 限制优化股票数量
        for stock in optimize_stocks:
            run_command_interactive(f"python run_optimization.py {stock} win_rate", f"{stock} 参数优化")
    
    # 第六阶段：生成交易计划
    print_step(6, "生成交易计划")
    
    print(f"\n📋 为每只股票生成最终交易建议...")
    trading_plans = []
    
    for stock in target_stocks:
        print(f"\n📊 {stock} 最终交易建议:")
        try:
            result = subprocess.run(f"python get_trading_advice.py {stock}", 
                                  shell=True, capture_output=True, text=True)
            if result.returncode == 0:
                print(result.stdout)
                trading_plans.append(f"{stock}: {result.stdout}")
        except:
            print(f"❌ 获取 {stock} 交易建议失败")
    
    # 生成总结报告
    print_step(7, "生成总结报告")
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    summary_file = f"trading_plan_{timestamp}.txt"
    
    try:
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write(f"交易计划总结报告\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("="*60 + "\n\n")
            
            f.write(f"分析股票: {' '.join(target_stocks)}\n\n")
            
            for plan in trading_plans:
                f.write(plan + "\n" + "-"*40 + "\n")
            
            f.write(f"\n操作建议:\n")
            f.write(f"1. 根据个人风险偏好选择合适的股票\n")
            f.write(f"2. 严格执行止损纪律\n")
            f.write(f"3. 分批建仓，控制仓位\n")
            f.write(f"4. 定期跟踪和调整\n")
        
        print(f"📄 交易计划已保存到: {summary_file}")
        
    except Exception as e:
        print(f"❌ 生成总结报告失败: {e}")
    
    print_header("分析流程完成")
    print("🎉 恭喜！你已完成完整的股票分析流程")
    print(f"📊 分析了 {len(target_stocks)} 只股票")
    print(f"📄 生成了交易计划: {summary_file}")
    print(f"💡 建议定期更新数据并重新分析")

def quick_analysis():
    """快速分析模式"""
    print_header("快速分析模式")
    
    stocks = input("请输入股票代码（用空格分隔）: ").strip().lower().split()
    
    if not stocks:
        print("❌ 未输入股票代码")
        return
    
    for stock in stocks:
        print(f"\n📊 快速分析: {stock}")
        subprocess.run(f"python get_trading_advice.py {stock}", shell=True)

def system_check():
    """系统检查模式"""
    print_header("系统检查模式")
    
    checks = [
        ("python validate_all_strategies.py", "系统功能验证"),
        ("python get_trading_advice.py sh000001", "数据验证"),
        ("python config_tool.py list", "配置检查")
    ]
    
    for command, description in checks:
        print(f"\n🔍 {description}...")
        result = subprocess.run(command, shell=True)
        if result.returncode == 0:
            print(f"✅ {description} 通过")
        else:
            print(f"❌ {description} 失败")

def main():
    """主函数"""
    print("🚀 股票交易分析快速启动工具")
    print("="*50)
    print("选择操作模式:")
    print("1. 引导式完整分析流程")
    print("2. 快速分析模式")
    print("3. 系统检查模式")
    print("4. 查看操作文档")
    
    choice = input("\n请选择 (1-4): ").strip()
    
    if choice == '1':
        guided_workflow()
    elif choice == '2':
        quick_analysis()
    elif choice == '3':
        system_check()
    elif choice == '4':
        print("\n📖 操作文档位置:")
        print("- 完整操作流程: TRADING_ANALYSIS_WORKFLOW.md")
        print("- 交易顾问指南: TRADING_ADVISOR_GUIDE.md")
        print("- 配置使用说明: CONFIG_USAGE.md")
        print("\n💡 建议先阅读 TRADING_ANALYSIS_WORKFLOW.md")
    else:
        print("❌ 无效选择")

if __name__ == "__main__":
    main()