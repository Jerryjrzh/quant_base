# 🌐 API接口文档

## 📋 接口概览

本文档描述了股票筛选与分析平台的完整API接口规范。所有接口遵循RESTful设计原则，支持JSON格式数据交换。

### 🔗 基础信息
- **Base URL**: `http://localhost:5000`
- **Content-Type**: `application/json`
- **字符编码**: `UTF-8`
- **跨域支持**: 已启用CORS

## 📊 策略管理接口

### 1. 获取可用策略列表
```http
GET /api/strategies
```

**响应示例**:
```json
{
  "success": true,
  "strategies": {
    "深渊筑底策略_v2.0": {
      "name": "深渊筑底策略",
      "version": "v2.0",
      "description": "识别底部反转信号的策略",
      "enabled": true,
      "parameters": {
        "rsi_threshold": 30,
        "volume_multiplier": 2.0
      }
    },
    "三重金叉_v1.0": {
      "name": "三重金叉策略", 
      "version": "v1.0",
      "description": "MA13/MA45/MACD三重确认策略",
      "enabled": true,
      "parameters": {
        "ma_short": 13,
        "ma_long": 45
      }
    }
  }
}
```

### 2. 获取策略配置
```http
GET /api/strategies/{strategy_id}/config
```

**路径参数**:
- `strategy_id`: 策略ID (如: "深渊筑底策略_v2.0")

**响应示例**:
```json
{
  "success": true,
  "config": {
    "name": "深渊筑底策略",
    "version": "v2.0",
    "enabled": true,
    "parameters": {
      "rsi_threshold": 30,
      "volume_multiplier": 2.0,
      "price_change_threshold": -0.05
    }
  }
}
```

### 3. 更新策略配置
```http
PUT /api/strategies/{strategy_id}/config
```

**请求体**:
```json
{
  "parameters": {
    "rsi_threshold": 25,
    "volume_multiplier": 1.5
  }
}
```

**响应示例**:
```json
{
  "success": true,
  "message": "策略 深渊筑底策略_v2.0 配置已更新"
}
```

### 4. 启用/禁用策略
```http
POST /api/strategies/{strategy_id}/toggle
```

**请求体**:
```json
{
  "enabled": true
}
```

**响应示例**:
```json
{
  "success": true,
  "message": "策略 深渊筑底策略_v2.0 已启用"
}
```

### 5. 获取策略股票列表 ⭐
```http
GET /api/strategies/{strategy_id}/stocks
```

**核心特性**:
- 优先从数据库缓存读取
- 缓存未命中时触发实时扫描
- 自动预热分析缓存

**响应示例**:
```json
{
  "success": true,
  "data": [
    {
      "stock_code": "sz000001",
      "stock_name": "平安银行",
      "date": "2025-01-19",
      "signal_type": "BUY",
      "price": 12.45
    },
    {
      "stock_code": "sh600036", 
      "stock_name": "招商银行",
      "date": "2025-01-19",
      "signal_type": "STRONG_BUY",
      "price": 45.67
    }
  ]
}
```

## 📈 股票分析接口

### 6. 获取股票技术分析 ⭐
```http
GET /api/analysis/{stock_code}
```

**查询参数**:
- `strategy`: 策略名称 (可选)
- `adjustment`: 复权类型 (`forward`/`backward`/`none`, 默认: `forward`)
- `timeframe`: 时间周期 (`daily`/`weekly`/`monthly`/`5min`/`15min`/`30min`/`60min`, 默认: `daily`)

**示例请求**:
```http
GET /api/analysis/sz000001?strategy=深渊筑底策略_v2.0&adjustment=forward&timeframe=daily
```

**响应示例**:
```json
{
  "kline_data": [
    {
      "date": "2025-01-19",
      "open": 12.30,
      "close": 12.45,
      "low": 12.20,
      "high": 12.50,
      "volume": 1234567
    }
  ],
  "indicator_data": [
    {
      "date": "2025-01-19",
      "ma13": 12.35,
      "ma45": 12.10,
      "dif": 0.05,
      "dea": 0.03,
      "macd": 0.02,
      "k": 65.5,
      "d": 62.3,
      "j": 71.9,
      "rsi6": 55.2,
      "rsi12": 52.8,
      "rsi24": 48.9
    }
  ],
  "signal_points": [
    {
      "date": "2025-01-19",
      "price": 12.45,
      "state": "BUY_SUCCESS",
      "original_state": "BUY"
    }
  ],
  "backtest_results": {
    "total_trades": 15,
    "win_rate": 0.73,
    "total_return": 0.156,
    "max_drawdown": -0.08,
    "sharpe_ratio": 1.25,
    "trades": [...]
  }
}
```

### 7. 获取交易建议
```http
GET /api/trading_advice/{stock_code}
```

**查询参数**:
- `adjustment`: 复权类型 (默认: `forward`)
- `timeframe`: 时间周期 (默认: `daily`)

**响应示例**:
```json
{
  "action": "BUY",
  "confidence": 0.78,
  "current_price": 12.45,
  "entry_price": 12.32,
  "target_price": 13.70,
  "stop_price": 11.82,
  "resistance_level": 13.80,
  "support_level": 11.90,
  "analysis_logic": [
    "短期均线(MA13: 12.35)位于长期均线(MA45: 12.10)之上，呈多头趋势。",
    "当前价格(12.45)在MA13之上，短期强势。",
    "RSI指标(55.2)处于正常区间。"
  ]
}
```

## 💼 持仓管理接口

### 8. 获取持仓列表
```http
GET /api/portfolio
```

**响应示例**:
```json
{
  "success": true,
  "portfolio": [
    {
      "stock_code": "sz000001",
      "stock_name": "平安银行",
      "purchase_price": 12.00,
      "current_price": 12.45,
      "quantity": 1000,
      "purchase_date": "2025-01-15",
      "profit_loss": 450.0,
      "profit_loss_percent": 0.0375,
      "note": "长期持有"
    }
  ],
  "count": 1
}
```

### 9. 添加持仓
```http
POST /api/portfolio
```

**请求体**:
```json
{
  "stock_code": "sz000001",
  "purchase_price": 12.00,
  "quantity": 1000,
  "purchase_date": "2025-01-15",
  "note": "长期持有"
}
```

**响应示例**:
```json
{
  "success": true,
  "message": "持仓 sz000001 添加成功",
  "position": {
    "stock_code": "sz000001",
    "purchase_price": 12.00,
    "quantity": 1000,
    "purchase_date": "2025-01-15",
    "note": "长期持有"
  }
}
```

### 10. 更新持仓
```http
PUT /api/portfolio
```

**请求体**:
```json
{
  "stock_code": "sz000001",
  "quantity": 1200,
  "note": "加仓后"
}
```

### 11. 删除持仓
```http
DELETE /api/portfolio?stock_code=sz000001
```

### 12. 获取核心池分析 ⭐
```http
GET /api/core_pool/analysis
```

**响应示例**:
```json
{
  "success": true,
  "core_pool": [
    {
      "stock_code": "sz000001",
      "stock_name": "平安银行",
      "grade": "A",
      "weight": 8.5,
      "added_time": "2025-01-15 10:30:00",
      "current_price": 12.45,
      "trading_advice": {
        "action": "HOLD",
        "confidence": 0.75,
        "reasoning": "技术面良好，建议持有"
      },
      "risk_assessment": {
        "risk_level": "中",
        "volatility": 0.25,
        "beta": 1.15
      }
    }
  ]
}
```

## 🏦 核心池管理接口

### 13. 获取核心池
```http
GET /api/core_pool
```

### 14. 添加股票到核心池
```http
POST /api/core_pool
```

**请求体**:
```json
{
  "stock_code": "sz000001",
  "note": "银行龙头股"
}
```

### 15. 从核心池删除股票
```http
DELETE /api/core_pool?stock_code=sz000001
```

## 📊 配置管理接口

### 16. 获取统一配置
```http
GET /api/config/unified
```

**响应示例**:
```json
{
  "success": true,
  "data": {
    "strategies": {...},
    "global_settings": {
      "max_concurrent_strategies": 5,
      "default_data_length": 500,
      "enable_parallel_processing": true
    },
    "market_filters": {
      "valid_prefixes": {
        "sh": ["600", "601", "603", "605", "688"],
        "sz": ["000", "001", "002", "003", "300"]
      }
    },
    "version": "2.0",
    "last_updated": "2025-01-19T10:30:00Z"
  }
}
```

## 📈 历史数据接口

### 17. 获取历史报告
```http
GET /api/history_reports?strategy=深渊筑底策略_v2.0
```

### 18. 获取深度扫描结果
```http
GET /api/deep_scan_results
```

**响应示例**:
```json
{
  "results": [
    {
      "stock_code": "sz000001",
      "score": 85.5,
      "grade": "A",
      "action": "BUY",
      "confidence": 0.78,
      "current_price": 12.45,
      "price_change_30d": 0.125,
      "volatility": 0.25,
      "signal_count": 3
    }
  ],
  "summary": {
    "total_analyzed": 150,
    "a_grade_count": 12,
    "buy_recommendations": 8
  }
}
```

### 19. 触发深度扫描
```http
POST /api/run_deep_scan
```

## 🔧 兼容性接口

### 20. 获取策略信号摘要 (兼容旧版)
```http
GET /api/signals_summary?strategy=PRE_CROSS
```

**策略映射**:
- `PRE_CROSS` → `临界金叉_v1.0`
- `TRIPLE_CROSS` → `三重金叉_v1.0`
- `MACD_ZERO_AXIS` → `macd零轴启动_v1.0`
- `WEEKLY_GOLDEN_CROSS_MA` → `周线金叉+日线ma_v1.0`
- `ABYSS_BOTTOMING` → `深渊筑底策略_v2.0`

## 🚨 错误处理

### 标准错误响应格式
```json
{
  "success": false,
  "error": "错误描述信息",
  "error_code": "ERROR_CODE",
  "timestamp": "2025-01-19T10:30:00Z"
}
```

### 常见错误码
- `400` - 请求参数错误
- `404` - 资源不存在
- `500` - 服务器内部错误

### 错误示例
```json
{
  "success": false,
  "error": "股票代码格式不正确",
  "error_code": "INVALID_STOCK_CODE"
}
```

## 🔄 缓存机制

### 缓存策略
1. **数据库缓存**: 分析结果持久化存储
2. **智能失效**: 配置变更自动清理相关缓存
3. **预热机制**: 筛选时立即进行深度分析

### 缓存相关响应头
```http
X-Cache-Status: HIT|MISS
X-Cache-Age: 3600
```

## 📊 性能优化

### 响应时间目标
- 缓存命中: < 100ms
- 实时计算: < 5s
- 批量扫描: < 30s

### 并发支持
- 最大并发请求: 50
- 连接池大小: 20
- 请求超时: 30s

## 🔒 安全考虑

### 输入验证
- 股票代码格式验证
- 参数范围检查
- SQL注入防护

### 访问控制
- 跨域请求限制
- 请求频率限制
- 敏感操作日志记录

## 📝 使用示例

### JavaScript 前端调用示例
```javascript
// 获取策略股票列表
async function getStrategyStocks(strategyId) {
  try {
    const response = await fetch(`/api/strategies/${strategyId}/stocks`);
    const data = await response.json();
    
    if (data.success) {
      return data.data;
    } else {
      throw new Error(data.error);
    }
  } catch (error) {
    console.error('获取策略股票失败:', error);
    throw error;
  }
}

// 获取股票分析
async function getStockAnalysis(stockCode, options = {}) {
  const params = new URLSearchParams({
    strategy: options.strategy || '',
    adjustment: options.adjustment || 'forward',
    timeframe: options.timeframe || 'daily'
  });
  
  try {
    const response = await fetch(`/api/analysis/${stockCode}?${params}`);
    const data = await response.json();
    return data;
  } catch (error) {
    console.error('获取股票分析失败:', error);
    throw error;
  }
}
```

### Python 后端调用示例
```python
import requests

class StockAnalysisAPI:
    def __init__(self, base_url="http://localhost:5000"):
        self.base_url = base_url
    
    def get_strategy_stocks(self, strategy_id):
        """获取策略股票列表"""
        url = f"{self.base_url}/api/strategies/{strategy_id}/stocks"
        response = requests.get(url)
        return response.json()
    
    def get_stock_analysis(self, stock_code, **kwargs):
        """获取股票分析"""
        url = f"{self.base_url}/api/analysis/{stock_code}"
        response = requests.get(url, params=kwargs)
        return response.json()
```

---

**API版本**: v2.0  
**最后更新**: 2025-01-19  
**维护者**: 开发团队