import pandas as pd
import numpy as np

# 1. 加载数据
df = pd.read_csv("full_calendar_trades.csv")

# 2. 解析 morse_features 提取 Bias 和 形态标签
# 从 'S:95|MKT:震荡|B20:0.079|T1_U:0|T1_L:1...' 中解析
df['Bias'] = df['morse_features'].str.extract(r'B20:([-\d\.]+)').astype(float)
df['Morse_Combo'] = df['morse_features'].apply(lambda x: extract_morse_combo(x)) # 你需要写个正则提取 T1_U, T1_B 等

# 3. 将趋势分类 (Bias 分箱)
conditions = [
    (df['Bias'] < -0.027),
    (df['Bias'] >= -0.027) & (df['Bias'] <= 0.264),
    (df['Bias'] > 0.264)
]
choices = ['1_贴地飞行', '2_趋势中继', '3_高位接力']
df['Trend_Zone'] = np.select(conditions, choices, default='Unknown')

# 4. 生成【趋势 x 形态】共振闭环矩阵
matrix = df.groupby(['Trend_Zone', 'Morse_Combo']).agg(
    Trade_Count=('stock_code', 'count'),
    Win_Rate=('final_pnl', lambda x: (x > 0).mean()),
    Avg_MFE=('MFE', 'mean'),
    Avg_MAE=('MAE', 'mean')
).reset_index()

# 过滤掉样本太少的组合，输出高胜率矩阵
print(matrix[matrix['Trade_Count'] > 50].sort_values(['Trend_Zone', 'Win_Rate'], ascending=[True, False]))
