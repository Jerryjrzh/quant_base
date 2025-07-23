#!/usr/bin/env python3
"""
将A_GRADE_EVALUATIONS中的股票添加到核心观察池
"""

import json
import os
from datetime import datetime
from collections import defaultdict

def load_a_grade_stocks():
    """从A_GRADE_EVALUATIONS目录加载所有A级股票"""
    a_grade_dir = "data/result/A_GRADE_EVALUATIONS"
    a_grade_stocks = {}
    
    if not os.path.exists(a_grade_dir):
        print(f"❌ A_GRADE_EVALUATIONS目录不存在: {a_grade_dir}")
        return {}
    
    # 读取汇总文件
    summary_files = [f for f in os.listdir(a_grade_dir) if f.startswith('a_grade_summary_')]
    
    if summary_files:
        # 使用最新的汇总文件
        latest_summary = sorted(summary_files)[-1]
        summary_path = os.path.join(a_grade_dir, latest_summary)
        
        print(f"📊 读取A级股票汇总文件: {latest_summary}")
        
        try:
            with open(summary_path, 'r', encoding='utf-8') as f:
                summary_data = json.load(f)
            
            # 统计每个股票的最新评估
            stock_latest = {}
            for item in summary_data:
                stock_code = item['stock_code']
                eval_time = item['evaluation_time']
                
                if stock_code not in stock_latest or eval_time > stock_latest[stock_code]['evaluation_time']:
                    stock_latest[stock_code] = item
            
            a_grade_stocks = stock_latest
            print(f"✅ 从汇总文件加载了 {len(a_grade_stocks)} 只A级股票")
            
        except Exception as e:
            print(f"❌ 读取汇总文件失败: {e}")
    
    # 如果没有汇总文件，则扫描单个评估文件
    if not a_grade_stocks:
        print("📁 扫描单个评估文件...")
        evaluation_files = [f for f in os.listdir(a_grade_dir) if f.endswith('_evaluation_*.json')]
        
        stock_evaluations = defaultdict(list)
        
        for file_name in evaluation_files:
            try:
                stock_code = file_name.split('_evaluation_')[0]
                file_path = os.path.join(a_grade_dir, file_name)
                
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                if data.get('grade') == 'A':
                    stock_evaluations[stock_code].append(data)
                    
            except Exception as e:
                print(f"⚠️  读取文件 {file_name} 失败: {e}")
        
        # 取每个股票的最新评估
        for stock_code, evaluations in stock_evaluations.items():
            latest_eval = max(evaluations, key=lambda x: x.get('evaluation_time', ''))
            a_grade_stocks[stock_code] = latest_eval
        
        print(f"✅ 从单个文件加载了 {len(a_grade_stocks)} 只A级股票")
    
    return a_grade_stocks

def load_core_pool():
    """加载当前核心观察池"""
    core_pool_file = "core_stock_pool.json"
    
    if os.path.exists(core_pool_file):
        try:
            with open(core_pool_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ 读取核心观察池失败: {e}")
            return []
    else:
        print("📝 核心观察池文件不存在，将创建新文件")
        return []

def save_core_pool(core_pool):
    """保存核心观察池"""
    core_pool_file = "core_stock_pool.json"
    
    try:
        with open(core_pool_file, 'w', encoding='utf-8') as f:
            json.dump(core_pool, f, ensure_ascii=False, indent=2)
        print(f"✅ 核心观察池已保存到 {core_pool_file}")
        return True
    except Exception as e:
        print(f"❌ 保存核心观察池失败: {e}")
        return False

def convert_a_grade_to_core_format(stock_code, a_grade_data):
    """将A级评估数据转换为核心观察池格式"""
    evaluation_details = a_grade_data.get('evaluation_details', {})
    
    # 计算综合评分 (基于A级评估的特征)
    base_score = 0.85  # A级股票基础分数
    
    # 根据折扣率调整分数
    discount_1 = evaluation_details.get('discount_1', 0)
    discount_2 = evaluation_details.get('discount_2', 0)
    avg_discount = (abs(discount_1) + abs(discount_2)) / 2
    
    # 折扣率越高，分数越高（更有吸引力）
    score_adjustment = min(avg_discount * 2, 0.15)  # 最多增加0.15分
    final_score = base_score + score_adjustment
    
    # 提取参数
    params = {
        "pre_entry_discount": abs(discount_1),
        "moderate_stop": 0.05  # 默认5%止损
    }
    
    # 如果有止损信息，使用moderate止损
    stop_loss = evaluation_details.get('stop_loss', {})
    if 'moderate' in stop_loss and 'current_price' in a_grade_data:
        current_price = a_grade_data['current_price']
        moderate_stop_price = stop_loss['moderate']
        if current_price > 0:
            params["moderate_stop"] = abs(current_price - moderate_stop_price) / current_price
    
    return {
        "stock_code": stock_code,
        "score": final_score,
        "params": params,
        "analysis_date": datetime.now().isoformat(),
        "source": "A_GRADE_EVALUATIONS",
        "grade": "A",
        "current_price": a_grade_data.get('current_price'),
        "entry_strategy": evaluation_details.get('entry_strategy')
    }

def merge_with_core_pool(core_pool, a_grade_stocks):
    """将A级股票合并到核心观察池"""
    # 创建现有股票的索引
    existing_stocks = {item['stock_code']: item for item in core_pool}
    
    added_count = 0
    updated_count = 0
    
    for stock_code, a_grade_data in a_grade_stocks.items():
        core_format_data = convert_a_grade_to_core_format(stock_code, a_grade_data)
        
        if stock_code in existing_stocks:
            # 如果已存在，比较分数，保留更高分数的
            existing_score = existing_stocks[stock_code].get('score', 0)
            new_score = core_format_data['score']
            
            if new_score > existing_score:
                # 更新为A级评估数据
                existing_stocks[stock_code].update(core_format_data)
                updated_count += 1
                print(f"🔄 更新股票 {stock_code}: {existing_score:.3f} -> {new_score:.3f}")
        else:
            # 新增股票
            core_pool.append(core_format_data)
            added_count += 1
            print(f"➕ 新增股票 {stock_code}: {core_format_data['score']:.3f}")
    
    # 按分数排序
    core_pool.sort(key=lambda x: x.get('score', 0), reverse=True)
    
    return added_count, updated_count

def main():
    print("🚀 开始将A_GRADE_EVALUATIONS中的股票添加到核心观察池...")
    print("=" * 60)
    
    # 1. 加载A级股票
    print("📊 步骤1: 加载A级股票评估数据")
    a_grade_stocks = load_a_grade_stocks()
    
    if not a_grade_stocks:
        print("❌ 没有找到A级股票数据")
        return
    
    print(f"✅ 找到 {len(a_grade_stocks)} 只A级股票")
    
    # 显示部分A级股票信息
    print("\n📋 A级股票示例:")
    for i, (stock_code, data) in enumerate(list(a_grade_stocks.items())[:5]):
        price = data.get('current_price', 'N/A')
        strategy = data.get('evaluation_details', {}).get('entry_strategy', 'N/A')
        print(f"   {i+1}. {stock_code} - 价格: {price} - 策略: {strategy}")
    
    if len(a_grade_stocks) > 5:
        print(f"   ... 还有 {len(a_grade_stocks) - 5} 只股票")
    
    # 2. 加载现有核心观察池
    print(f"\n📊 步骤2: 加载现有核心观察池")
    core_pool = load_core_pool()
    original_count = len(core_pool)
    print(f"✅ 现有核心观察池包含 {original_count} 只股票")
    
    # 3. 合并数据
    print(f"\n🔄 步骤3: 合并A级股票到核心观察池")
    added_count, updated_count = merge_with_core_pool(core_pool, a_grade_stocks)
    
    # 4. 保存结果
    print(f"\n💾 步骤4: 保存更新后的核心观察池")
    if save_core_pool(core_pool):
        final_count = len(core_pool)
        print("\n" + "=" * 60)
        print("✅ 操作完成!")
        print(f"📊 统计信息:")
        print(f"   • 原有股票数量: {original_count}")
        print(f"   • 新增股票数量: {added_count}")
        print(f"   • 更新股票数量: {updated_count}")
        print(f"   • 最终股票数量: {final_count}")
        print(f"   • A级股票占比: {len(a_grade_stocks)/final_count*100:.1f}%")
        
        # 显示最高分的几只股票
        print(f"\n🏆 评分最高的前5只股票:")
        for i, stock in enumerate(core_pool[:5]):
            source = stock.get('source', 'legacy')
            grade = stock.get('grade', '')
            grade_info = f" ({grade})" if grade else ""
            print(f"   {i+1}. {stock['stock_code']}{grade_info} - 评分: {stock['score']:.3f} - 来源: {source}")
    else:
        print("❌ 保存失败")

if __name__ == "__main__":
    main()