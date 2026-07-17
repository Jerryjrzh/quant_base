import os
import json
from datetime import datetime

def generate_execution_report():
    # 假设你的选股结果保存在这里 (根据你实际情况调整路径)
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(backend_dir, '..', 'data', 'result', 'signals_summary.json') # 或者你存放最新筛选结果的地方
    
    # 兼容性查找：如果没有找上面那个，就在当前目录找
    if not os.path.exists(json_path):
        json_path = 'signals_summary.json'
        if not os.path.exists(json_path):
            print(f"❌ 找不到筛选结果文件 {json_path}。请先运行 screenergf.py。")
            return

    with open(json_path, 'r', encoding='utf-8') as f:
        signals = json.load(f)

    if not signals:
        print("今日无符合条件的标的，空仓休息。")
        return

    # 1. 过滤与排序：优先极性转换，其次看深踩次数和拟合分
    # 注意：只选取策略为 ADAPTIVE_MA_SUPPORT 的票
    candidates = [s for s in signals if s.get('strategy') == 'ADAPTIVE_MA_SUPPORT']
    
    # 排序：极性确认优先 > 拟合分高优先 > 深踩次数适中优先
    candidates.sort(key=lambda x: (
        x.get('polarity_confirmed', False), 
        x.get('fit_score', 0)
    ), reverse=True)

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
        
        # 计算网格收割价格
        # 买入价是假设回落到底部后反弹1.5%成交的理论成本
        expected_cost = trigger_buy * 1.015 
        profit_7_price = expected_cost * 1.07
        profit_10_price = expected_cost * 1.10

        print(f"==================================================")
        print(f" No.{i} [{code}] | 专属生命线: MA{ma_period} | 拟合分: {fit_score}")
        print(f" 战略定性: {polarity} | 深踩次数: {deep_touches}")
        print(f"--------------------------------------------------")
        print(f" 📥 【第一笼：防飞刀买入单】(券商App: 回落买入)")
        print(f"   ► 触发条件：价格跌破 ¥{trigger_buy:.2f} 后，向上反弹 1.5%")
        print(f"   ► 委托价格：市价 或 ¥{expected_cost:.2f} 买入 5% 底仓")
        print(f"   * 注: 若开盘价低于 ¥{stop_loss:.2f}(超预期大跌) 则直接放弃该笔交易")
        print(f"")
        print(f" 🛑 【风险控制：硬止损单】(买入成交后立即挂出)")
        print(f"   ► 触发条件：最新价跌破 ¥{stop_loss:.2f}")
        print(f"   ► 委托价格：跌停价 卖出全仓 (坚决止损，防主跌浪)")
        print(f"")
        print(f" 🕸️ 【第二笼：网格收割单】(买入成交后挂出/双向条件单)")
        print(f"   ► T1 止盈 (7%): 最新价达到 ¥{profit_7_price:.2f} 触发，卖出 1/2 可用仓位")
        print(f"   ► T2 清仓 (10%): 最新价达到 ¥{profit_10_price:.2f} 触发，卖出剩余全部仓位")
        print(f"   * 注: T1 触发后，须手动将止损单上移至保本价 ¥{expected_cost:.2f}")
        print(f"==================================================\n")

    print("💡 【纪律提示】")
    print("1. 收盘前半小时若仍处于浮亏且形态破位，不必等跌穿止损线，可提前手动平仓。")
    print("2. 严格控制单只标的底仓在总资金的 5%-10%，切忌重仓单吊。\n")

if __name__ == "__main__":
    generate_execution_report()
