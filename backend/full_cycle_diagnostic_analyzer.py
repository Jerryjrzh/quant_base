import os
import pandas as pd
import numpy as np

def main():
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    # 自动定位全周期批量回测产生的总流水数据表
    trades_csv = os.path.abspath(os.path.join(backend_dir, '..', 'data', 'result', 'Calendar_Backtest', 'full_calendar_trades.csv'))
    
    if not os.path.exists(trades_csv):
        print(f"❌ 找不到全周期交易流水文件: {trades_csv}，请确保已运行 calendar_batch_runner.py")
        return

    print("📊 正在载入 16 个月全周期特征矩阵，启动统计学尸检...")
    df = pd.read_csv(trades_csv)
    
    # 定义需要透视的底层原始特征维度
    target_features = ['ma_slope', 'drop_velocity', 'vol_ratio', 'amplitude', 'deep_touches', 'burst_ratio']
    
    # 过滤出我们需要审计的三大出局状态
    statuses = ['止盈成功', '止损出局', '持仓到期']
    
    print("\n" + "="*80)
    print(" 📐 全周期不同出局状态【底层技术特征百分位矩阵分布】")
    print("="*80)
    
    for status in statuses:
        sub_df = df[df['trade_status'] == status]
        if sub_df.empty:
            print(f"\n状态 [{status}]: 暂无样本数据")
            continue
            
        print(f"\n🚩 状态群组: 【{status}】 (样本总数: {len(sub_df)} 笔)")
        print("-" * 80)
        
        # 逐个特征拉出四分位数卡尺
        report_data = []
        for feat in target_features:
            if feat not in sub_df.columns:
                continue
            
            q25 = sub_df[feat].quantile(0.25)
            q50 = sub_df[feat].quantile(0.50)  # 中位数
            q75 = sub_df[feat].quantile(0.75)
            mean_val = sub_df[feat].mean()
            
            report_data.append({
                '特征指标': feat,
                '25%分位线 (低)': f"{q25:+.4f}",
                '50%中位线 (准)': f"{q50:+.4f}",
                '75%分位线 (高)': f"{q75:+.4f}",
                '样本均值': f"{mean_val:+.4f}"
            })
            
        feat_report = pd.DataFrame(report_data)
        print(feat_report.to_string(index=False))
        print("-" * 80)

    # 💡 针对大盘系统性踩踏日的集中归因提示
    print("\n💡 优化调整方向倒推指南：")
    print(" 1. 对比【持仓到期】与【止盈成功】的 drop_velocity 中位数：若到期股的跌速明显更慢，说明属于慢阴跌品种，买入条件需强行收紧跌速阈值。")
    print(" 2. 对比【持仓到期】与流通股性的 amplitude 均值：若到期股振幅普遍偏低，说明放行了低波死水股，必须提高过滤大门。")

if __name__ == '__main__':
    main()
