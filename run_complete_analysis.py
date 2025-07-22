#!/usr/bin/env python3
"""
完整的股票筛选分析流程
适用于数据更新后的全面分析
"""

import sys
import os
import subprocess
from datetime import datetime

def run_command(command, description):
    """运行命令并显示结果"""
    print(f"\n{'='*60}")
    print(f"🔄 {description}")
    print(f"命令: {command}")
    print('='*60)
    
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print(result.stdout)
            print(f"✅ {description} 完成")
        else:
            print(f"❌ {description} 失败")
            print(f"错误信息: {result.stderr}")
        return result.returncode == 0
    except Exception as e:
        print(f"❌ 执行命令失败: {e}")
        return False

def complete_analysis_workflow(target_stocks=None):
    """完整的分析工作流程"""
    print("🚀 启动完整股票筛选分析流程")
    print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    # 默认分析股票列表
    if target_stocks is None:
        target_stocks = ['sz300290', 'sh000001', 'sz000001', 'sh600000', 'sz000002']
    
    print(f"📊 目标股票: {', '.join(target_stocks)}")
    
    # 步骤1: 系统验证
    print(f"\n🔧 步骤1: 系统功能验证")
    if not run_command("python validate_all_strategies.py", "系统功能验证"):
        print("⚠️ 系统验证失败，但继续执行分析")
    
    # 步骤2: 样本股票筛选
    print(f"\n📈 步骤2: 样本股票池筛选")
    run_command("python run_enhanced_screening.py sample", "样本股票池增强筛选")
    
    # 步骤3: 目标股票深度分析
    print(f"\n🎯 步骤3: 目标股票深度分析")
    for i, stock in enumerate(target_stocks, 1):
        print(f"\n--- 分析股票 {i}/{len(target_stocks)}: {stock} ---")
        
        # 基础交易建议
        run_command(f"python get_trading_advice.py {stock}", f"{stock} 基础交易建议")
        
        # 增强分析
        run_command(f"python run_enhanced_screening.py {stock}", f"{stock} 增强分析")
        
        # 配置对比
        run_command(f"python config_tool.py compare {stock}", f"{stock} 配置对比")
    
    # 步骤4: 批量参数优化
    print(f"\n⚙️ 步骤4: 批量参数优化")
    stock_list = ' '.join(target_stocks[:3])  # 限制前3只股票进行优化，避免时间过长
    run_command(f"python run_optimization.py batch {stock_list}", "批量参数优化")
    
    # 步骤5: 传统策略筛选
    print(f"\n📊 步骤5: 传统策略筛选")
    run_command("python backend/screener.py", "MACD零轴启动策略筛选")
    
    # 生成分析报告
    print(f"\n📋 步骤6: 生成分析总结")
    generate_analysis_summary(target_stocks)
    
    print(f"\n🎉 完整分析流程完成!")
    print(f"⏰ 结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)

def generate_analysis_summary(target_stocks):
    """生成分析总结"""
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        summary_file = f"analysis_summary_{timestamp}.txt"
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write(f"股票筛选分析总结报告\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("="*60 + "\n\n")
            
            f.write(f"分析股票列表:\n")
            for i, stock in enumerate(target_stocks, 1):
                f.write(f"  {i}. {stock}\n")
            
            f.write(f"\n执行的分析步骤:\n")
            f.write(f"  1. 系统功能验证\n")
            f.write(f"  2. 样本股票池筛选\n")
            f.write(f"  3. 目标股票深度分析\n")
            f.write(f"  4. 批量参数优化\n")
            f.write(f"  5. 传统策略筛选\n")
            
            f.write(f"\n分析结果文件位置:\n")
            f.write(f"  - 增强分析结果: data/result/ENHANCED_ANALYSIS/\n")
            f.write(f"  - 策略筛选结果: data/result/MACD_ZERO_AXIS/\n")
            f.write(f"  - 参数优化结果: analysis_cache/\n")
            
            f.write(f"\n后续操作建议:\n")
            f.write(f"  1. 查看各股票的综合评分和投资建议\n")
            f.write(f"  2. 关注评分>70分的股票\n")
            f.write(f"  3. 结合个人风险偏好选择合适的配置\n")
            f.write(f"  4. 定期更新数据并重新分析\n")
        
        print(f"📄 分析总结已保存到: {summary_file}")
        
    except Exception as e:
        print(f"❌ 生成分析总结失败: {e}")

def quick_analysis(stock_codes):
    """快速分析模式"""
    print("⚡ 快速分析模式")
    print("="*40)
    
    for stock in stock_codes:
        print(f"\n📊 快速分析: {stock}")
        run_command(f"python get_trading_advice.py {stock}", f"{stock} 交易建议")

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("📋 股票筛选分析工具")
        print("="*40)
        print("使用方法:")
        print("  python run_complete_analysis.py full                    # 完整分析流程")
        print("  python run_complete_analysis.py quick <股票代码>...      # 快速分析")
        print("  python run_complete_analysis.py custom <股票代码>...     # 自定义股票完整分析")
        print("")
        print("示例:")
        print("  python run_complete_analysis.py full")
        print("  python run_complete_analysis.py quick sz300290 sh000001")
        print("  python run_complete_analysis.py custom sz300290 sz000001 sh600000")
        return
    
    mode = sys.argv[1].lower()
    
    if mode == 'full':
        # 完整分析流程
        complete_analysis_workflow()
        
    elif mode == 'quick':
        # 快速分析
        if len(sys.argv) < 3:
            print("❌ 请提供要分析的股票代码")
            return
        stock_codes = [code.lower() for code in sys.argv[2:]]
        quick_analysis(stock_codes)
        
    elif mode == 'custom':
        # 自定义股票完整分析
        if len(sys.argv) < 3:
            print("❌ 请提供要分析的股票代码")
            return
        stock_codes = [code.lower() for code in sys.argv[2:]]
        complete_analysis_workflow(stock_codes)
        
    else:
        print(f"❌ 未知模式: {mode}")

if __name__ == "__main__":
    main()