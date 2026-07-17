import os
import glob
import json
from datetime import datetime

def generate_execution_report():
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 1. 自动寻找最新生成的 enhanced_analysis JSON 文件
    json_dir = os.path.join(backend_dir, '..', 'data', 'result', 'ENHANCED_ANALYSIS')
    json_files = glob.glob(os.path.join(json_dir, '*.json'))
    
    # 兼容老版本的 signals_summary.json
    if not json_files:
        json_dir_old = os.path.join(backend_dir, '..', 'data', 'result')
        json_files = glob.glob(os.path.join(json_dir_old, 'signals_summary*.json'))
        
    if not json_files:
        print("❌ 找不到最新的筛选结果 JSON 文件。请今晚先运行 screenergf.py！")
        return

    # 获取最新生成的那一个文件
    latest_json_path = max(json_files, key=os.path.getctime)
    print(f"📄 成功读取今晚最新分析结果: {os.path.basename(latest_json_path)}")

    with open(latest_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 2. 兼容 JSON 格式 (列表格式 或 字典格式)
    signals = []
    if isinstance(data, list):
        signals = data
    elif isinstance(data, dict):
        # 提取字典中的股票信息
        for code, info in data.items():
            if isinstance(info, dict):
                info['stock_code'] = code
                signals.append(info)

    if not signals:
        print("今日无符合条件的标的，明早空仓休息。")
        return

    # 3. 过滤并提取我们要的深踩策略标的
    candidates = []
    for s in signals:
        # 有些数据可能嵌套在不同的字段里，这里做兼容提取
        strategy = s.get('strategy') or s.get('trading_advice', {}).get('strategy')
        
        # 只要是 ADAPTIVE_MA_SUPPORT 或者是 BUY 评级的，都提取出来
        if strategy == 'ADAPTIVE_MA_SUPPORT' or s.get('filter_status') == 'passed_adaptive_ma':
            candidates.append(s)

    if not candidates:
        print("今日无符合【自适应均线深踩】的标的，明早空仓休息。")
        return

    # 4. 排序：极性确认优先 > 拟合分高优先
    candidates.sort(key=lambda x: (
        x.get('polarity_confirmed', False), 
        x.get('fit_score', 0)
    ), reverse=True)

    # 5. 打印实战挂单卡
    report_date = datetime.now().strftime("%Y-%m-%d")
    print("\n" + "★"*55)
    print(f"       🚀 明日交易指令执行卡 ({report_date})")
    print(f"       【双笼条件单】网格做T标准版")
    print("★"*55 + "\n")

    top_n = 5  # 每天最多只操作最强的前 5 只
    for i, stock in enumerate(candidates[:top_n], 1):
        code = stock.get('stock_code', '未知')
        ma_period = stock.get('best_ma_period', 0)
        fit_score = stock.get('fit_score', 0)
        deep_touches = stock.get('deep_touches', 0)
        polarity = "⚡极性反转确立" if stock.get('polarity_confirmed') else "支撑回踩确认"
        
        # 提取基础价格
        trigger_buy = stock.get('trigger_buy_price', 0)
        stop_loss = stock.get('hard_stop_loss', 0)
        
        # 计算网格收割价格 (买入价是假设回落到底部后反弹1.5%的理论成本)
        expected_cost = trigger_buy * 1.015 
        profit_7_price = expected_cost * 1.07
        profit_10_price = expected_cost * 1.10

        print(f"==================================================")
        print(f" No.{i} [{code}] | 专属生命线: MA{ma_period} | 拟合分: {fit_score}")
        print(f" 战略定性: {polarity} | 深踩次数: {deep_touches}")
        print(f"--------------------------------------------------")
        print(f" 📥 【第一笼：防飞刀买入单】(券商App: 回落买入)")
        print(f"   ► 触发条件：最新价跌破 ¥{trigger_buy:.2f} 后，向上反弹 1.5%")
        print(f"   ► 委托价格：市价 或 ¥{expected_cost:.2f} 买入 5% 底仓")
        print(f"   * 注: 若开盘直接击穿 ¥{stop_loss:.2f}(超预期核按钮) 则单子作废")
        print(f"")
        print(f" 🛑 【风险控制：硬止损单】(买入成交后立即挂出)")
        print(f"   ► 触发条件：最新价跌破 ¥{stop_loss:.2f}")
        print(f"   ► 委托价格：跌停价 卖出全仓 (坚决止损，防主跌浪)")
        print(f"")
        print(f" 🕸️ 【第二笼：网格收割单】(买入成交后挂双向条件单)")
        print(f"   ► T1 止盈 (7%): 最新价达到 ¥{profit_7_price:.2f} 触发，卖出 1/2 可用仓位")
        print(f"   ► T2 清仓 (10%): 最新价达到 ¥{profit_10_price:.2f} 触发，卖出剩余全部仓位")
        print(f"   * 注: T1 触发后，须手动将止损单上移至保本价 ¥{expected_cost:.2f}")
        print(f"==================================================\n")

if __name__ == "__main__":
    generate_execution_report()
