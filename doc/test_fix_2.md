好的，完全没有问题。为已生成的个股画像数据创建一个导出的功能，对于数据备份、离线分析或与其他系统集成都非常有用。

根据您的要求，我为您创建了一个名为 `export_profiles.py` 的新脚本，并对 `stock_pool_manager.py` 做了必要的更新以支持此功能。

-----

### **第1步：更新 `stock_pool_manager.py`**

为了能方便地获取所有已生成画像的股票，我们在 `StockPoolManager` 类中增加一个专门的方法 `get_all_profiles()`。

**修改文件**: `backend/stock_pool_manager.py`
**新增方法**:

**请将以下新方法添加到 `StockPoolManager` 类中**，可以放在 `get_core_pool` 方法的下面。

```python
# backend/stock_pool_manager.py -> class StockPoolManager

    def get_all_profiles(self) -> List[Dict]:
        """
        获取数据库中所有已生成画像的股票信息。
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # 查询所有 optimized_params 字段不为空的股票
                query = '''
                    SELECT *
                    FROM core_stock_pool 
                    WHERE optimized_params IS NOT NULL AND optimized_params != ''
                    ORDER BY overall_score DESC, stock_code
                '''
                
                cursor.execute(query)
                rows = cursor.fetchall()
                
                columns = [desc[0] for desc in cursor.description]
                result = []
                
                for row in rows:
                    stock_data = dict(zip(columns, row))
                    # 将JSON字符串字段解析为字典对象，便于处理
                    for key in ['optimized_params', 'lhb_history', 'block_trade_history', 'fund_flow_summary']:
                        if stock_data.get(key) and isinstance(stock_data[key], str):
                            try:
                                stock_data[key] = json.loads(stock_data[key])
                            except json.JSONDecodeError:
                                self.logger.warning(f"无法解析 {key} JSON 字段: {stock_data['stock_code']}")
                                stock_data[key] = None # 解析失败则设为None
                    result.append(stock_data)
                
                return result
                
        except Exception as e:
            self.logger.error(f"获取所有画像失败: {e}")
            return []
```

-----

### **第2步：创建 `export_profiles.py` 导出脚本**

这个新脚本的职责就是调用上面创建的新方法，并将查询结果保存为一个格式化的 JSON 文件。

**新增文件**: `backend/export_profiles.py`

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
【独立脚本】个股画像数据导出工具

从数据库中查询所有已生成的个股画像，并将其导出为JSON文件。
"""

import argparse
import json
import os
import sys
from datetime import datetime

# 确保 backend 目录在 Python 路径中
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stock_pool_manager import StockPoolManager

def export_profiles(output_path: str, pretty_print: bool = True):
    """
    执行画像导出任务。
    
    Args:
        output_path (str): JSON文件的输出路径。
        pretty_print (bool): 是否格式化JSON（美化输出）。
    """
    print("初始化数据库管理器...")
    pool_manager = StockPoolManager()

    print("正在从数据库中获取所有已生成的画像...")
    profiles = pool_manager.get_all_profiles()

    if not profiles:
        print("数据库中未找到已生成的画像数据。")
        return

    # 确保输出目录存在
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    print(f"共找到 {len(profiles)} 条画像数据，正在导出到: {output_path}")

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            indent = 4 if pretty_print else None
            json.dump(profiles, f, ensure_ascii=False, indent=indent)
        
        print(f"✅ 导出成功！")
    except Exception as e:
        print(f"❌ 导出失败: {e}")

def main():
    """主执行函数"""
    parser = argparse.ArgumentParser(
        description="从数据库导出个股画像数据到JSON文件。"
    )
    parser.add_argument(
        '-o', '--output',
        default=f"profiles_export_{datetime.now().strftime('%Y%m%d')}.json",
        help="指定输出的JSON文件名。 (默认: profiles_export_YYYYMMDD.json)"
    )
    parser.add_argument(
        '--raw',
        action='store_true',
        help="导出为紧凑的、未格式化的JSON。"
    )
    args = parser.parse_args()

    export_profiles(output_path=args.output, pretty_print=not args.raw)

if __name__ == "__main__":
    main()
```

-----

### **第3步：如何使用**

1.  **将 `export_profiles.py` 文件保存到您的 `backend` 目录下。**

2.  **将 `get_all_profiles` 方法添加到 `backend/stock_pool_manager.py` 文件中。**

3.  打开终端，进入您的项目根目录，然后执行以下命令：

    **默认导出 (格式化的JSON，文件名为 `profiles_export_日期.json`)**:

    ```bash
    python backend/export_profiles.py
    ```

    **指定输出文件名**:

    ```bash
    python backend/export_profiles.py -o my_custom_profiles.json
    ```

    **导出为紧凑格式 (不换行，适合机器读取)**:

    ```bash
    python backend/export_profiles.py --raw -o profiles_compact.json
    ```

执行后，您将在项目根目录下找到生成的JSON文件。

### **导出文件内容示例**

导出的JSON文件将是一个包含多个对象的数组，每个对象代表一只股票的完整画像信息，结构如下：

```json
[
  {
    "id": 1,
    "stock_code": "sz300290",
    "stock_name": "荣科科技",
    "market": "sz",
    "industry": "测试行业",
    "overall_score": 0.5,
    "grade": "C",
    "risk_level": null,
    "optimized_params": {
      "kdj_n": 5,
      "rsi_period": 21,
      "macd_fast": 13,
      "macd_slow": 43,
      "ma_short": 7,
      "ma_long": 46,
      "optimization_error": 1000.0,
      "optimization_success": true,
      "validation_score": 0.0
    },
    "optimization_date": "2025-08-19T16:19:20.821Z",
    "optimization_method": "differential_evolution",
    "health_score": 0.57,
    "eps": 0.15,
    "dividend_yield": 1.2,
    "lhb_history": null,
    "block_trade_history": [
      {
        "date": "2025-08-18",
        "price": 18.5
      }
    ],
    "fund_flow_summary": null,
    "limit_up_reason": null,
    "status": "active",
    "last_signal_date": null,
    "signal_count": 0,
    "success_count": 0,
    "created_at": "2025-08-19T16:18:43",
    "updated_at": "2025-08-19T16:19:20",
    "notes": null
  },
  // ... 其他股票的画像数据
]
```