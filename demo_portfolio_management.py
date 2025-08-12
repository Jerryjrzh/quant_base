#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
持仓管理功能演示脚本
展示持仓列表管理的各项功能
"""

import os
import sys
import json
from datetime import datetime, timedelta

# 添加backend目录到路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from portfolio_manager import create_portfolio_manager

def demo_portfolio_management():
    """演示持仓管理功能"""
    print("=" * 60)
    print("持仓管理功能演示")
    print("=" * 60)
    
    # 创建持仓管理器
    portfolio_manager = create_portfolio_manager()
    
    # 1. 添加示例持仓
    print("\n1. 添加示例持仓...")
    sample_positions = [
        {
            'stock_code': 'sz300741',
            'purchase_price': 26.92,
            'quantity': 1000,
            'purchase_date': '2024-01-15',
            'note': '华宝股份 - 香精-食品'
        },
        {
            'stock_code': 'sh600618',
            'purchase_price': 10.30,
            'quantity': 500,
            'purchase_date': '2024-02-20',
            'note': '氯碱化工 - 化工'
        },
        {
            'stock_code': 'sz002021',
            'purchase_price': 2.32,
            'quantity': 300,
            'purchase_date': '2024-03-10',
            'note': '中捷资源 - 资源'
        }
    ]
    
    for position in sample_positions:
        try:
            result = portfolio_manager.add_position(
                position['stock_code'],
                position['purchase_price'],
                position['quantity'],
                position['purchase_date'],
                position['note']
            )
            print(f"✅ 添加持仓成功: {position['stock_code']}")
        except ValueError as e:
            print(f"⚠️  持仓已存在: {position['stock_code']}")
        except Exception as e:
            print(f"❌ 添加持仓失败: {position['stock_code']} - {e}")
    
    # 2. 显示持仓列表
    print("\n2. 当前持仓列表:")
    portfolio = portfolio_manager.load_portfolio()
    if portfolio:
        print(f"{'股票代码':<10} {'购买价格':<10} {'数量':<8} {'购买日期':<12} {'备注':<20}")
        print("-" * 70)
        for position in portfolio:
            print(f"{position['stock_code']:<10} "
                  f"¥{position['purchase_price']:<9.2f} "
                  f"{position['quantity']:<8} "
                  f"{position['purchase_date']:<12} "
                  f"{position['note'][:18]:<20}")
    else:
        print("暂无持仓记录")
    
    # 3. 单个持仓深度分析
    print("\n3. 单个持仓深度分析...")
    if portfolio:
        test_position = portfolio[0]
        print(f"正在分析: {test_position['stock_code']}")
        
        analysis = portfolio_manager.analyze_position_deep(
            test_position['stock_code'],
            test_position['purchase_price'],
            test_position['purchase_date']
        )
        
        if 'error' not in analysis:
            print(f"✅ 分析完成:")
            print(f"   当前价格: ¥{analysis['current_price']:.2f}")
            print(f"   盈亏比例: {analysis['profit_loss_pct']:.2f}%")
            print(f"   操作建议: {analysis['position_advice']['action']}")
            print(f"   置信度: {analysis['position_advice']['confidence']*100:.0f}%")
            print(f"   风险等级: {analysis['risk_assessment']['risk_level']}")
            
            if analysis['position_advice']['reasons']:
                print("   操作理由:")
                for reason in analysis['position_advice']['reasons']:
                    print(f"     • {reason}")
            
            # 时间分析
            timing = analysis.get('timing_analysis', {})
            if timing.get('expected_peak_date'):
                print(f"   预期到顶: {timing['expected_peak_date']}")
                if timing.get('days_to_peak'):
                    print(f"   距离到顶: {timing['days_to_peak']}天")
            
            # 价格目标
            targets = analysis.get('price_targets', {})
            if targets.get('add_position_price'):
                print(f"   建议补仓价: ¥{targets['add_position_price']:.2f}")
            if targets.get('reduce_position_price'):
                print(f"   建议减仓价: ¥{targets['reduce_position_price']:.2f}")
                
        else:
            print(f"❌ 分析失败: {analysis['error']}")
    
    # 4. 全量持仓扫描
    print("\n4. 全量持仓扫描...")
    print("正在扫描所有持仓，请稍候...")
    
    scan_results = portfolio_manager.scan_all_positions()
    
    print(f"✅ 扫描完成!")
    print(f"扫描时间: {scan_results['scan_time']}")
    print(f"总持仓数: {scan_results['total_positions']}")
    
    summary = scan_results['summary']
    print(f"盈利持仓: {summary['profitable_count']}")
    print(f"亏损持仓: {summary['loss_count']}")
    print(f"总盈亏: {summary['total_profit_loss']:.2f}%")
    print(f"高风险持仓: {summary['high_risk_count']}")
    print(f"需要操作: {summary['action_required_count']}")
    
    # 显示详细结果
    print("\n持仓详情:")
    print(f"{'代码':<10} {'当前价':<8} {'盈亏%':<8} {'操作':<8} {'风险':<8} {'补仓价':<8} {'预期到顶':<12}")
    print("-" * 80)
    
    for position in scan_results['positions']:
        if 'error' in position:
            print(f"{position['stock_code']:<10} ERROR: {position['error']}")
            continue
            
        current_price = position.get('current_price', 0)
        profit_loss = position.get('profit_loss_pct', 0)
        action = position.get('position_advice', {}).get('action', 'UNKNOWN')
        risk = position.get('risk_assessment', {}).get('risk_level', 'UNKNOWN')
        add_price = position.get('position_advice', {}).get('add_position_price')
        peak_date = position.get('timing_analysis', {}).get('expected_peak_date')
        peak_date_str = peak_date if peak_date is not None else '--'
        
        print(f"{position['stock_code']:<10} "
              f"¥{current_price:<7.2f} "
              f"{profit_loss:<7.2f}% "
              f"{action:<8} "
              f"{risk:<8} "
              f"{'¥'+str(round(add_price,2)) if add_price else '--':<8} "
              f"{peak_date_str:<12}")
    
    # 5. 保存扫描结果
    print("\n5. 保存扫描结果...")
    result_file = f"portfolio_scan_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    try:
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(scan_results, f, ensure_ascii=False, indent=2)
        print(f"✅ 扫描结果已保存到: {result_file}")
    except Exception as e:
        print(f"❌ 保存失败: {e}")
    
    # 6. 功能总结
    print("\n" + "=" * 60)
    print("持仓管理功能总结:")
    print("=" * 60)
    print("✅ 持仓列表管理 - 支持添加、删除、修改持仓")
    print("✅ 深度分析 - 技术指标、操作建议、风险评估")
    print("✅ 价格目标 - 补仓价、减仓价、止损价")
    print("✅ 时间分析 - 预期到顶日期、持仓周期分析")
    print("✅ 全量扫描 - 批量分析所有持仓")
    print("✅ 操作建议 - 买入、卖出、持有、加仓、减仓")
    print("✅ 风险管理 - 风险等级评估和预警")
    print("✅ 前端界面 - 完整的Web界面支持")
    
    print("\n使用方法:")
    print("1. 启动后端服务: python backend/app.py")
    print("2. 打开浏览器访问: http://127.0.0.1:5000")
    print("3. 点击 '💼 持仓管理' 按钮")
    print("4. 添加持仓、深度扫描、查看详情")
    
    return scan_results

if __name__ == "__main__":
    try:
        results = demo_portfolio_management()
        print(f"\n🎉 演示完成! 共分析了 {results['total_positions']} 个持仓")
    except Exception as e:
        print(f"\n❌ 演示过程中出现错误: {e}")
        import traceback
        traceback.print_exc()