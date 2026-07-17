#!/usr/bin/env python3
"""
增强版 Morse 特征价格评估工具 v3.2 - 动态向后计算真实极值 (多进程版)
"""

import sys
import os
import pandas as pd
import traceback
import multiprocessing
import concurrent.futures

sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from backtester import get_deep_analysis
from data_handler import get_market_volatility_profile, get_stock_data_simple

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

def calculate_future_extremes(stock_code: str, start_date: str, lookahead_days: int = 7):
    """
    动态计算指定日期后 N 个交易日内的真实最高价和最低价
    """
    try:
        # 使用简化版数据加载，提升速度
        df_full = get_stock_data_simple(stock_code)
        if df_full is None or df_full.empty:
            return None, None
            
        # 确保日期索引为 datetime 格式
        if not isinstance(df_full.index, pd.DatetimeIndex):
            df_full.index = pd.to_datetime(df_full.index)
            
        target_date = pd.to_datetime(start_date)
        
        # 截取 start_date 之后的数据 (包含 start_date 当天)
        future_data = df_full[df_full.index >= target_date]
        
        if future_data.empty:
            return None, None
            
        # 取未来 N 个交易日
        future_window = future_data.head(lookahead_days)
        
        if len(future_window) == 0:
            return None, None
            
        future_min = float(future_window['low'].min())
        future_max = float(future_window['high'].max())
        
        return future_min, future_max
    except Exception as e:
        print(f"提取未来数据失败 {stock_code}: {e}")
        return None, None

def process_single_row(task_data):
    """
    独立的工作进程函数：处理单条记录，并现场计算未来极值
    """
    idx, row_dict = task_data
    
    # 兼容 Morse 可能的列名
    stock = row_dict.get('stock_code')
    entry_date = row_dict.get('eval_date') 
    
    if not stock or not entry_date:
        return {'status': 'error', 'msg': f"行 {idx} 缺失核心标识字段"}
        
    try:
        # 获取市场特征画像
        market_profile = get_market_volatility_profile(stock)
        board_name = market_profile['board_type']
        
        # 动态截断环境并调用自适应买卖点算法 (获取当时的预测)
        analysis = get_deep_analysis(stock_code=stock, analysis_date=entry_date)
        
        if 'error' in analysis:
            return {'status': 'error', 'msg': f"{stock}: {analysis['error'][:30]}"}
            
        advice = analysis.get('trading_advice', {})
        current_price = float(advice.get('current_price', 0))
        
        # 提取自适应算法生成的买卖预测价
        pred_entry = float(advice.get('entry_price', current_price))
        pred_target = float(advice.get('target_price', current_price * 1.1))
        pred_stop = float(advice.get('stop_price', current_price * 0.95))
        # 2. 🚀 新增：提取【技术结构防线】(支撑与阻力)
        support_level = float(advice.get('support_level', 0)) if advice.get('support_level') else None
        resistance_level = float(advice.get('resistance_level', 0)) if advice.get('resistance_level') else None
        # 👇 核心新增：捕获多维特征标签
        feat_trend = advice.get('feature_trend', 'unknown')
        feat_pattern = advice.get('feature_pattern', 'None')
        feat_bias_tier = advice.get('feature_bias_tier', 'unknown')

        # ==========================================
        # 🚀 核心修复：动态向后拉取真实极值 (设定观察期为 7 天)
        # ==========================================
        LOOKAHEAD_DAYS = 7
        future_min, future_max = calculate_future_extremes(stock, entry_date, LOOKAHEAD_DAYS)
        
        if future_min is None or future_max is None:
             return {'status': 'error', 'msg': f"{stock}: 无法获取 {entry_date} 之后的未来 K 线数据"}

        # ==========================================
        # 📐 差异与偏离度量化
        # ==========================================
        entry_bias_pct = (pred_entry - future_min) / pred_entry if pred_entry > 0 else 0
        target_bias_pct = (future_max - pred_target) / pred_target if pred_target > 0 else 0
        
        entry_hit = (future_min <= pred_entry <= future_max)
        target_hit = (entry_hit and future_max >= pred_target)
        
        total_market_span = (future_max - future_min) / future_min if future_min > 0 else 0
        pred_strategy_span = (pred_target - pred_entry) / pred_entry if pred_entry > 0 else 0

        result = {
            'status': 'success',
            'stock_code': stock,
            'entry_date': entry_date,
            'board_type': board_name,
            # 👇 将特征写入最终结果字典
            'trend_phase': feat_trend,
            'pattern_type': feat_pattern,
            'bias_tier': feat_bias_tier,
            'current_price': current_price,
            'future_min_low': future_min,
            'future_max_high': future_max,
            'pred_entry': pred_entry,
            'pred_target': pred_target,
            'pred_stop': pred_stop,
            'support_level': support_level,      # ⬅️ 新增
            'resistance_level': resistance_level,  # ⬅️ 新增
            'entry_bias_pct': round(entry_bias_pct, 4),
            'target_bias_pct': round(target_bias_pct, 4),
            'entry_hit': entry_hit,
            'target_hit': target_hit,
            'market_span_pct': round(total_market_span, 4),
            'strategy_span_pct': round(pred_strategy_span, 4)
        }
        return result
        
    except Exception as e:
        return {'status': 'error', 'msg': f"{stock}: {str(e)}"}


def validate_morse_prices_parallel(sample_size=0):
    """
    利用进程池并发处理 Morse 特征原始数据
    """
    csv_path = "/home/hypnosis/data/quant_base/data/result/Calendar_Backtest/full_calendar_trades.csv"
    
    try:
        df_csv = pd.read_csv(csv_path)
    except FileNotFoundError:
        csv_path = "data/result/Calendar_Backtest/full_calendar_trades.csv"
        if os.path.exists(csv_path):
            df_csv = pd.read_csv(csv_path)
        else:
            print(f"❌ 无法定位 Morse 原始数据文件: {csv_path}")
            return None

    print(f"✅ 成功加载 Morse 原始交易记录: {len(df_csv)} 条")
    
    if sample_size > 0:
        df_csv = df_csv.sample(n=min(sample_size, len(df_csv)), random_state=42)
        print(f"🔍 随机抽取 {sample_size} 条样本进行价格差异评估...")
    else:
        print(f"🔍 启动全量 {len(df_csv)} 条数据的全周期闭环价格评估...")
    
    tasks = [(idx, row.to_dict()) for idx, row in df_csv.iterrows()]
    results = []
    error_count = 0
    
    max_workers = max(1, multiprocessing.cpu_count() - 1)
    print(f"🚀 启动进程池并发计算 (分配核心数: {max_workers}) ...")
    
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_single_row, task): task for task in tasks}
        
        iterator = concurrent.futures.as_completed(futures)
        if HAS_TQDM:
            iterator = tqdm(iterator, total=len(futures), desc="🔄 处理进度", unit="条")
            
        for future in iterator:
            res = future.result()
            if res is None:
                continue
            if res.get('status') == 'success':
                res.pop('status')
                results.append(res)
            else:
                error_count += 1
                if not HAS_TQDM:
                    print(f"\n⚠️ 任务失败: {res.get('msg')}")

    if not results:
        print("\n⚠️ 未能生成有效评估数据，所有任务均执行失败。")
        return None

    print(f"\n✅ 计算完成！成功 {len(results)} 条，失败 {error_count} 条。")
    result_df = pd.DataFrame(results)
    
    # ==========================================
    # 📊 多板块分类统计引擎
    # ==========================================
    print("\n" + "="*80)
    print("🎯 Morse 原始特征数据 - 多板块价格精准度综合评估报告 (观察期: 7天)")
    print("="*80)
    
    boards = result_df['board_type'].unique()
    
    for board in sorted(boards):
        b_df = result_df[result_df['board_type'] == board]
        total_count = len(b_df)
        
        executed_count = b_df['entry_hit'].sum()
        entry_rate = (executed_count / total_count) * 100
        target_rate = (b_df['target_hit'].sum() / executed_count * 100) if executed_count > 0 else 0
        
        avg_entry_bias = b_df['entry_bias_pct'].mean() * 100
        avg_target_bias = b_df['target_bias_pct'].mean() * 100
        avg_market_span = b_df['market_span_pct'].mean() * 100
        avg_strategy_span = b_df['strategy_span_pct'].mean() * 100
        
        print(f"\n封装板块: 【{board}】 (样本数: {total_count} 条)")
        print(f"  📥 挂单买入成功率 : {entry_rate:.1f}%")
        print(f"  📐 买入价偏离极小值 : {avg_entry_bias:.2f}% (正值: 安全垫; 负值: 挂单过深错过空间)")
        print(f"  --------------------------------------------------")
        print(f"  🎯 触及预测止盈率 : {target_rate:.1f}% (基于已成功买入的样本)")
        print(f"  📐 止盈目标偏离极值 : {avg_target_bias:.2f}% (正值: 利润外溢; 负值: 目标过高未触及)")
        print(f"  --------------------------------------------------")
        print(f"  📈 市场期间真实平均波幅: {avg_market_span:.2f}%")
        print(f"  📉 策略预期规避/锁利波幅: {avg_strategy_span:.2f}%")
    
    print("="*80)
    
    output_path = "/home/hypnosis/data/quant_base/data/result/Calendar_Backtest/morse_price_validation_matrix_v2.csv"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    result_df.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"📊 差异分析全量矩阵已成功导出至: {output_path}")

def main():
    sample_size = 0
    if len(sys.argv) > 1:
        if sys.argv[1] not in ['--help', '-h']:
            try:
                sample_size = int(sys.argv[1])
            except ValueError:
                print("❌ 参数错误，请输入整数样本数（0代表全量数据）")
                return
        else:
            print("使用方法:\n  python validate_sr_levels_1.py [样本数量]\n  (示例: 输入 0 进行全量数据分析)")
            return
            
    validate_morse_prices_parallel(sample_size)

if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
