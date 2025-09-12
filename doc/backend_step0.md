### 方案评估确认与下一步行动计划

您好，非常感谢您对调整方案的细致评估，以及对爬虫脚本可用性的专业审查。您的反馈非常有价值，确认了方案大方向的正确性，并为第二阶段的“数据丰富”提供了具体、可行的技术选型和优先级。

**您的评估结论非常清晰：**

1.  **方案可行**：分阶段的迭代路径合理，模块职责划分清晰，数据流符合预期。
2.  **爬虫可用性明确**：您已经识别出哪些数据源稳定可用（如龙虎榜、分红送配），哪些存在风险或需要修复（如涨停原因、操盘必读）。
3.  **优先级确定**：您指出了数据整合的优先级，应首先整合龙虎榜（`stock_lhb_em`）、分红送配（`stock_fhps_em`）等高质量数据。

基于您的确认和评估，我们现在可以从“方案评估”进入到“**具体实施**”阶段。我将按照我们共同确认的路线图，结合您对爬虫脚本的洞察，为您规划出下一步具体的后端调整内容。

-----

### **下一步行动计划：后端模块具体实现**

我们将聚焦于**第一阶段**和**第二阶段**的核心模块开发，因为它们是后续所有功能的基础。

#### **第一步：扩展数据库 (`stock_pool_manager.py`)**

根据您评估的爬虫数据，我们需要在`core_stock_pool`表中添加字段以存储这些丰富的画像信息。

**具体调整内容：**
在您的 `stock_pool_manager.py` 的 `_init_database` 方法中，需要对 `CREATE TABLE` 语句进行扩展，或者通过 `ALTER TABLE` 增加新字段。建议直接修改 `CREATE TABLE` 以保持代码清晰。

**调整后的 `core_stock_pool` 表结构（部分）：**

```python
# stock_pool_manager.py -> _init_database()

# ...
cursor.execute('''
    CREATE TABLE IF NOT EXISTS core_stock_pool (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        stock_code TEXT UNIQUE NOT NULL,
        stock_name TEXT,
        -- ... 保留原有字段 ...
        overall_score REAL NOT NULL,
        grade TEXT NOT NULL,
        
        -- 新增：数据丰富字段 --
        health_score REAL,                     -- 健康分 (由enricher计算)
        sector TEXT,                           -- 所属板块/概念
        eps REAL,                              -- 每股收益 (来自fhps)
        dividend_yield REAL,                   -- 股息率 (来自fhps)
        lhb_history TEXT,                      -- 龙虎榜历史 (JSON格式)
        block_trade_history TEXT,              -- 大宗交易历史 (JSON格式)
        fund_flow_summary TEXT,                -- 资金流向摘要 (JSON格式)
        limit_up_reason TEXT,                  -- 最近涨停原因
        
        -- ... 保留原有字段 ...
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        notes TEXT
    )
''')
# ...
```

#### **第二步：实现数据丰富器 (`data_enricher.py`)**

这是实现您“个股画像”中数据维度的核心。我们将创建一个新的 `data_enricher.py` 模块。

**具体调整内容：**
创建新文件 `backend/data_enricher.py`。

```python
# backend/data_enricher.py

import json
from datetime import datetime, timedelta
# 导入您的爬虫脚本和数据库管理器
from backend.craw import stock_lhb_em, stock_fhps_em, stock_dzjy_em, stock_fund_em
from backend.stock_pool_manager import StockPoolManager

class DataEnricher:
    def __init__(self):
        self.pool_manager = StockPoolManager() # 假设db文件在默认路径

    def enrich_single_stock(self, stock_code: str):
        """为单只股票丰富数据并更新到数据库"""
        print(f"丰富数据: {stock_code}")
        enriched_data = {}
        today_str = datetime.now().strftime('%Y%m%d')
        
        try:
            # 优先级 1: 龙虎榜 (数据价值最高)
            lhb_df = stock_lhb_em.stock_lhb_detail_em(start_date=today_str, end_date=today_str)
            if not lhb_df.empty:
                stock_lhb = lhb_df[lhb_df['代码'] == stock_code]
                if not stock_lhb.empty:
                    enriched_data['lhb_history'] = json.dumps(stock_lhb.to_dict('records'))

            # 优先级 2: 分红送配 (获取财务基本面)
            # 通常按报告期查询，这里假设查询最近的年报
            report_date = str(datetime.now().year - 1) + "1231"
            fhps_df = stock_fhps_em.stock_fhps_em(date=report_date)
            if not fhps_df.empty:
                stock_fhps = fhps_df[fhps_df['代码'] == stock_code]
                if not stock_fhps.empty:
                    enriched_data['eps'] = stock_fhps['每股收益'].iloc[0]
                    enriched_data['dividend_yield'] = stock_fhps['现金分红-股息率'].iloc[0]

            # 优先级 3: 大宗交易
            dzjy_df = stock_dzjy_em.stock_dzjy_mrmx(symbol='A股', start_date=today_str, end_date=today_str)
            if not dzjy_df.empty:
                stock_dzjy = dzjy_df[dzjy_df['证券代码'] == stock_code]
                if not stock_dzjy.empty:
                    enriched_data['block_trade_history'] = json.dumps(stock_dzjy.to_dict('records'))

            # 优先级 4: 资金流向
            fund_df = stock_fund_em.stock_individual_fund_flow_rank(indicator="5日")
            if not fund_df.empty:
                stock_fund = fund_df[fund_df['代码'] == stock_code]
                if not stock_fund.empty:
                    enriched_data['fund_flow_summary'] = json.dumps(stock_fund.to_dict('records'))

            # TODO: 计算健康分 (health_score)
            # health_score = self._calculate_health_score(enriched_data)
            # enriched_data['health_score'] = health_score

            # 更新到数据库
            if enriched_data:
                self.pool_manager.update_stock_profile(stock_code, enriched_data) # 假设有这个更新方法

        except Exception as e:
            print(f"丰富 {stock_code} 数据时出错: {e}")

    def run_enrichment_for_pool(self):
        """为核心池中的所有股票丰富数据"""
        core_pool = self.pool_manager.get_core_pool()
        for stock in core_pool:
            self.enrich_single_stock(stock['stock_code'])

# StockPoolManager 中需要一个更新方法
class StockPoolManager:
    # ...
    def update_stock_profile(self, stock_code: str, data: dict):
        """更新股票画像数据"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            update_fields = ", ".join([f"{key} = ?" for key in data.keys()])
            values = list(data.values())
            values.append(stock_code)
            
            cursor.execute(f'''
                UPDATE core_stock_pool 
                SET {update_fields}, updated_at = ?
                WHERE stock_code = ?
            ''', values)
            conn.commit()
```

#### **第三步：实现个股画像生成器 (`stock_profiler.py`)**

这个模块负责计算个股的最佳技术指标参数。

**具体调整内容：**
创建新文件 `backend/stock_profiler.py`。

```python
# backend/stock_profiler.py
# (此模块实现细节较复杂，此处提供核心框架)

from scipy.optimize import minimize
import data_handler
import indicators
from stock_pool_manager import StockPoolManager

class StockProfiler:
    def __init__(self):
        self.pool_manager = StockPoolManager()

    def _objective_function(self, params, df):
        # 目标函数，计算指标信号与价格低点的平均时间差
        # ... (详细逻辑如上次方案所述) ...
        return average_distance 

    def create_stock_profile(self, stock_code: str):
        """为单只股票找到最优参数并存入数据库"""
        df = data_handler.get_full_data_with_indicators(stock_code)
        if df is None: return

        # 定义参数搜索范围和初始值
        param_bounds = [(5, 20), (5, 20), (5, 20), (21, 50)] # KDJ_n, RSI_p, MACD_f, MACD_s
        initial_guess = [9, 14, 12, 26]

        result = minimize(self._objective_function, initial_guess, args=(df,), bounds=param_bounds)
        
        if result.success:
            optimal_params = {
                'kdj_n': int(result.x[0]), 'rsi_period': int(result.x[1]),
                'macd_fast': int(result.x[2]), 'macd_slow': int(result.x[3]),
                'optimization_error': result.fun
            }
            # 将优化参数存入数据库
            profile_data = {'optimized_params': json.dumps(optimal_params)}
            self.pool_manager.update_stock_profile(stock_code, profile_data)
            print(f"已为 {stock_code} 生成并存储最优参数画像。")
```

#### **第四步：实现历史回测验证 (`universal_screener.py`)**

**具体调整内容：**
对 `universal_screener.py` 进行修改，使其支持历史回测。

```python
# universal_screener.py

class UniversalScreener:
    # ...
    def run_screening(self, selected_strategies: list = None, scan_date_str: str = None):
        """增加 scan_date_str 参数"""
        # ...
        # 将 scan_date_str 传递给多进程工作函数
        process_args = [(file_path, market, enabled_strategies, self.config, scan_date_str) for file_path, market in all_files]
        # ...
    
    def validate_screening_results(self, results: list, scan_date_str: str, validation_days: int = 15):
        """新增验证函数"""
        for result in results:
            df_full = data_handler.get_full_data_with_indicators(result.stock_code)
            if df_full is None: continue

            # 找到信号日期后的 N 个交易日数据
            future_data = df_full.loc[df_full.index > scan_date_str].head(validation_days)
            if not future_data.empty:
                # 附加验证结果到 result.signal_details
                # ...
        return results

def process_single_stock_worker(args):
    file_path, market, enabled_strategies, config_data, scan_date_str = args
    # ...
    df_full = get_full_data_with_indicators(stock_code_full)
    if df_full is None: return []

    # 截取历史数据
    if scan_date_str:
        df = df_full.loc[:scan_date_str]
    else:
        df = df_full
    # ... 后续逻辑使用截取后的 df
```

### 总结与下一步

此方案详细规划了数据库扩展、数据丰富器、画像生成器和历史回测验证的具体实现路径，完全采纳了您的评估意见。

  - **依赖已明确**：新增 `stock_profiler.py`, `data_enricher.py`；需要 `scipy`, `dtw-python` 等库。
  - **模块交互清晰**：各模块通过调用 `stock_pool_manager` 的方法与数据库交互，实现数据共享。
  - **实施路径清晰**：您可以按照**数据库扩展 -\> 数据丰富 -\> 画像生成 -\> 历史回测**的顺序逐步实现。

**请您确认**：这个更具体的实现方案是否符合您的预期？如果确认，您可以开始按照这个蓝图进行编码。在开发过程中，我可以随时为您提供特定函数的完整代码或解决遇到的技术问题。