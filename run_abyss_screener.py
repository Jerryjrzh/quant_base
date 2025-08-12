#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
深渊筑底策略筛选器启动脚本
提供简单的命令行界面
"""

import os
import sys
import argparse
from datetime import datetime

def main():
    parser = argparse.ArgumentParser(
        description='深渊筑底策略股票筛选器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python run_abyss_screener.py                    # 使用默认配置运行
  python run_abyss_screener.py --test             # 运行测试模式
  python run_abyss_screener.py --config custom    # 使用自定义配置
  python run_abyss_screener.py --help             # 显示帮助信息

输出文件位置:
  data/result/ABYSS_BOTTOMING_OPTIMIZED/

更多信息请参考: ABYSS_SCREENER_USAGE_GUIDE.md
        """
    )
    
    parser.add_argument(
        '--test', 
        action='store_true',
        help='运行测试模式，验证策略是否正常工作'
    )
    
    parser.add_argument(
        '--config',
        type=str,
        default='default',
        help='配置模式: default, strict, loose'
    )
    
    parser.add_argument(
        '--data-path',
        type=str,
        help='自定义数据路径（覆盖默认配置）'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        help='自定义输出目录'
    )
    
    parser.add_argument(
        '--workers',
        type=int,
        help='并行进程数（默认为CPU核心数）'
    )
    
    args = parser.parse_args()
    
    print("🚀 深渊筑底策略股票筛选器")
    print("=" * 50)
    print(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"运行模式: {'测试模式' if args.test else '生产模式'}")
    print(f"配置模式: {args.config}")
    
    if args.test:
        print("\n📋 运行测试模式...")
        try:
            import subprocess
            result = subprocess.run([sys.executable, 'test_real_abyss_screener.py'], 
                                  capture_output=True, text=True)
            print(result.stdout)
            if result.stderr:
                print("错误信息:", result.stderr)
            
            if result.returncode == 0:
                print("✅ 测试完成，策略工作正常")
                print("📊 现在可以运行生产模式进行实际筛选")
            else:
                print("❌ 测试失败，请检查配置")
                return 1
                
        except Exception as e:
            print(f"❌ 运行测试失败: {e}")
            return 1
    
    else:
        print("\n📊 运行生产模式...")
        
        # 设置环境变量
        if args.data_path:
            os.environ['ABYSS_DATA_PATH'] = args.data_path
            print(f"📁 使用自定义数据路径: {args.data_path}")
        
        if args.output_dir:
            os.environ['ABYSS_OUTPUT_DIR'] = args.output_dir
            print(f"📤 使用自定义输出目录: {args.output_dir}")
        
        if args.workers:
            os.environ['ABYSS_MAX_WORKERS'] = str(args.workers)
            print(f"⚙️ 使用 {args.workers} 个并行进程")
        
        # 检查必要文件
        screener_file = os.path.join('backend', 'screener_abyss_optimized.py')
        config_file = os.path.join('backend', 'abyss_config.json')
        
        if not os.path.exists(screener_file):
            print(f"❌ 找不到筛选器文件: {screener_file}")
            return 1
        
        if not os.path.exists(config_file):
            print(f"❌ 找不到配置文件: {config_file}")
            return 1
        
        print("✅ 文件检查通过")
        print("\n🔍 开始股票筛选...")
        print("=" * 50)
        
        try:
            import subprocess
            result = subprocess.run([sys.executable, screener_file], 
                                  text=True)
            
            if result.returncode == 0:
                print("\n" + "=" * 50)
                print("✅ 筛选完成！")
                print("📄 请查看输出目录中的结果文件:")
                print("  - abyss_signals_*.json (详细信号)")
                print("  - abyss_summary_*.json (汇总报告)")
                print("  - abyss_report_*.txt (可读性报告)")
                print("\n📖 详细使用说明请参考: ABYSS_SCREENER_USAGE_GUIDE.md")
            else:
                print("❌ 筛选过程中出现错误")
                return 1
                
        except KeyboardInterrupt:
            print("\n⏹️ 用户中断筛选过程")
            return 1
        except Exception as e:
            print(f"❌ 运行筛选器失败: {e}")
            return 1
    
    return 0

if __name__ == '__main__':
    sys.exit(main())