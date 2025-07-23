#!/usr/bin/env python3
"""
集成系统演示脚本 - 展示深度扫描集成到筛选系统的完整流程
"""

import os
import sys
import json
import time
import subprocess
from datetime import datetime

def run_screener_with_deep_scan():
    """运行筛选器并触发深度扫描"""
    print("🚀 启动集成筛选系统演示")
    print("=" * 60)
    
    # 检查数据目录
    if not os.path.exists(os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")):
        print("⚠️ 警告: 未找到通达信数据目录，将使用模拟数据")
        print("   请确保已正确配置BASE_PATH")
    
    print("📊 开始执行筛选...")
    
    # 运行筛选器（这会自动触发深度扫描）
    try:
        result = subprocess.run([
            sys.executable, 'backend/screener.py'
        ], capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            print("✅ 筛选和深度扫描完成")
            print("\n📄 筛选输出:")
            print(result.stdout)
        else:
            print("❌ 筛选过程出现错误:")
            print(result.stderr)
            return False
            
    except subprocess.TimeoutExpired:
        print("⏰ 筛选过程超时（5分钟），可能数据量较大")
        return False
    except Exception as e:
        print(f"❌ 运行筛选器失败: {e}")
        return False
    
    return True

def show_results():
    """显示结果"""
    print("\n📊 查看结果文件...")
    print("-" * 40)
    
    # 检查各种结果文件
    result_dirs = {
        'ENHANCED_ANALYSIS': '深度分析结果',
        'A_GRADE_EVALUATIONS': 'A级股票价格评估',
        'MACD_ZERO_AXIS': 'MACD零轴策略',
        'TRIPLE_CROSS': '三重金叉策略',
        'PRE_CROSS': '临界金叉策略'
    }
    
    for dir_name, description in result_dirs.items():
        dir_path = f'data/result/{dir_name}'
        if os.path.exists(dir_path):
            files = [f for f in os.listdir(dir_path) if f.endswith('.json')]
            if files:
                print(f"✅ {description}: {len(files)} 个文件")
                
                # 显示最新文件的部分内容
                latest_file = max([os.path.join(dir_path, f) for f in files], key=os.path.getctime)
                try:
                    with open(latest_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        
                    if dir_name == 'ENHANCED_ANALYSIS':
                        print(f"   📈 深度分析了 {len(data)} 只股票")
                        a_grade_count = sum(1 for v in data.values() 
                                          if isinstance(v, dict) and 
                                          v.get('overall_score', {}).get('grade') == 'A')
                        print(f"   🏆 发现 {a_grade_count} 只A级股票")
                        
                    elif dir_name == 'A_GRADE_EVALUATIONS':
                        if isinstance(data, list):
                            print(f"   💰 价格评估记录: {len(data)} 条")
                        else:
                            print(f"   💰 单个股票评估: {data.get('stock_code', 'N/A')}")
                            
                except Exception as e:
                    print(f"   ⚠️ 读取文件失败: {e}")
            else:
                print(f"⚪ {description}: 无数据文件")
        else:
            print(f"⚪ {description}: 目录不存在")

def start_web_server():
    """启动Web服务器"""
    print("\n🌐 启动Web服务器...")
    print("-" * 40)
    
    try:
        print("🚀 启动Flask服务器 (http://127.0.0.1:5000)")
        print("💡 提示: 在浏览器中打开上述地址查看前端界面")
        print("🔍 前端功能包括:")
        print("   - 股票筛选结果查看")
        print("   - 深度扫描结果展示")
        print("   - A级股票价格评估")
        print("   - 技术分析图表")
        print("   - 多周期分析")
        print("\n按 Ctrl+C 停止服务器")
        print("-" * 40)
        
        # 启动Flask服务器
        subprocess.run([sys.executable, 'backend/app.py'], cwd='.')
        
    except KeyboardInterrupt:
        print("\n👋 服务器已停止")
    except Exception as e:
        print(f"❌ 启动服务器失败: {e}")

def show_usage_guide():
    """显示使用指南"""
    print("\n📖 系统使用指南")
    print("=" * 60)
    
    print("🔧 1. 配置系统:")
    print("   - 确保通达信数据路径正确配置")
    print("   - 检查 backend/screener.py 中的 BASE_PATH")
    print("   - 选择要运行的策略 (STRATEGY_TO_RUN)")
    
    print("\n📊 2. 运行筛选:")
    print("   - 直接运行: python backend/screener.py")
    print("   - 系统会自动执行初步筛选 + 深度扫描")
    print("   - 多线程处理，提高效率")
    
    print("\n🔍 3. 深度扫描功能:")
    print("   - 自动对筛选出的股票进行深度分析")
    print("   - 生成综合评分和投资建议")
    print("   - A级股票自动进行价格评估")
    print("   - 保存详细分析报告")
    
    print("\n🌐 4. Web界面:")
    print("   - 启动: python backend/app.py")
    print("   - 访问: http://127.0.0.1:5000")
    print("   - 查看筛选结果和深度扫描数据")
    print("   - 手动触发深度扫描")
    
    print("\n📁 5. 结果文件:")
    print("   - data/result/ENHANCED_ANALYSIS/: 深度分析结果")
    print("   - data/result/A_GRADE_EVALUATIONS/: A级股票评估")
    print("   - data/result/[STRATEGY]/: 各策略筛选结果")
    
    print("\n🧪 6. 测试系统:")
    print("   - 运行: python test_system_integration.py")
    print("   - 验证所有功能是否正常")

def main():
    """主函数"""
    print("🎯 集成系统演示")
    print("=" * 80)
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    while True:
        print("\n请选择操作:")
        print("1. 运行完整筛选流程 (筛选 + 深度扫描)")
        print("2. 查看结果文件")
        print("3. 启动Web服务器")
        print("4. 显示使用指南")
        print("5. 退出")
        
        choice = input("\n请输入选择 (1-5): ").strip()
        
        if choice == '1':
            success = run_screener_with_deep_scan()
            if success:
                show_results()
        elif choice == '2':
            show_results()
        elif choice == '3':
            start_web_server()
        elif choice == '4':
            show_usage_guide()
        elif choice == '5':
            print("👋 再见！")
            break
        else:
            print("❌ 无效选择，请重新输入")

if __name__ == "__main__":
    main()