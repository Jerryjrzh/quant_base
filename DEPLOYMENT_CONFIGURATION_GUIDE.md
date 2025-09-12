# 🚀 部署与配置指南

## 📋 系统要求

### 硬件要求
- **CPU**: 4核心以上 (推荐8核心)
- **内存**: 8GB以上 (推荐16GB)
- **存储**: 50GB可用空间 (SSD推荐)
- **网络**: 稳定的互联网连接

### 软件要求
- **操作系统**: Linux (Ubuntu 20.04+) / Windows 10+ / macOS 10.15+
- **Python**: 3.8+ (推荐3.9+)
- **数据库**: SQLite 3.x (内置)
- **Web服务器**: 内置Flask开发服务器 / Nginx + Gunicorn (生产环境)

## 🛠️ 环境准备

### 1. Python环境安装
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3 python3-pip python3-venv

# CentOS/RHEL
sudo yum install python3 python3-pip

# macOS (使用Homebrew)
brew install python3

# Windows
# 从 https://python.org 下载安装包
```

### 2. 创建虚拟环境
```bash
# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
# Linux/macOS
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### 3. 安装依赖包
```bash
# 安装核心依赖
pip install -r requirements.txt

# 或手动安装主要依赖
pip install flask flask-cors pandas numpy sqlite3 logging pathlib
```

### 4. 创建必要目录
```bash
mkdir -p data/result
mkdir -p config
mkdir -p logs
mkdir -p charts
```

## ⚙️ 配置文件设置

### 1. 统一策略配置 (`config/unified_strategy_config.json`)
```json
{
  "version": "2.0",
  "last_updated": "2025-01-19T10:30:00Z",
  "strategies": {
    "深渊筑底策略_v2.0": {
      "name": "深渊筑底策略",
      "version": "v2.0",
      "enabled": true,
      "description": "识别底部反转信号的策略",
      "parameters": {
        "rsi_threshold": 30,
        "volume_multiplier": 2.0,
        "price_change_threshold": -0.05,
        "confirmation_days": 3
      }
    },
    "三重金叉_v1.0": {
      "name": "三重金叉策略",
      "version": "v1.0", 
      "enabled": true,
      "description": "MA13/MA45/MACD三重确认策略",
      "parameters": {
        "ma_short": 13,
        "ma_long": 45,
        "macd_fast": 12,
        "macd_slow": 26,
        "macd_signal": 9
      }
    }
  },
  "global_settings": {
    "max_concurrent_strategies": 5,
    "default_data_length": 500,
    "enable_parallel_processing": true,
    "log_level": "INFO",
    "cache_expiry_days": 7,
    "run_backtest_after_scan": true
  },
  "market_filters": {
    "valid_prefixes": {
      "sh": ["600", "601", "603", "605", "688"],
      "sz": ["000", "001", "002", "003", "300"],
      "bj": ["430", "831", "832", "833", "834", "835", "836", "837", "838", "839"],
      "ds": ["31#", "43#", "48#"]
    },
    "exclude_st": true,
    "exclude_delisted": true,
    "min_market_cap": 500000000,
    "min_daily_volume": 10000000
  },
  "output_settings": {
    "save_detailed_analysis": true,
    "generate_charts": false,
    "export_formats": ["json", "txt", "csv"],
    "max_signals_per_strategy": 50
  },
  "frontend_settings": {
    "default_timeframe": "daily",
    "default_adjustment": "forward",
    "chart_indicators": ["ma13", "ma45", "macd", "kdj", "rsi"],
    "auto_refresh_interval": 300
  }
}
```

### 2. 数据路径配置 (`backend/config.py`)
```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
基础配置文件
"""

import os
from pathlib import Path

# 基础路径配置
BASE_PATH = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)

# 数据路径
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
RESULT_PATH = os.path.join(DATA_DIR, 'result')
DATABASE_PATH = os.path.join(DATA_DIR, 'quant_analysis.db')

# 配置路径
CONFIG_DIR = os.path.join(PROJECT_ROOT, 'config')
STRATEGY_CONFIG_PATH = os.path.join(CONFIG_DIR, 'unified_strategy_config.json')

# 日志配置
LOG_DIR = os.path.join(PROJECT_ROOT, 'logs')
LOG_LEVEL = 'INFO'

# 市场配置
MARKETS = ['sh', 'sz', 'bj', 'ds']

# 确保目录存在
for directory in [DATA_DIR, RESULT_PATH, CONFIG_DIR, LOG_DIR]:
    os.makedirs(directory, exist_ok=True)
```

### 3. 环境变量配置 (`.env`)
```bash
# Flask配置
FLASK_APP=backend/app.py
FLASK_ENV=development
FLASK_DEBUG=1

# 数据库配置
DATABASE_URL=sqlite:///data/quant_analysis.db

# 日志配置
LOG_LEVEL=INFO
LOG_FILE=logs/app.log

# 缓存配置
CACHE_EXPIRY_DAYS=7
ENABLE_CACHE=true

# 性能配置
MAX_WORKERS=8
ENABLE_PARALLEL=true
```

## 🗄️ 数据库初始化

### 1. 自动初始化
系统首次启动时会自动创建SQLite数据库和表结构：

```python
# 数据库会自动创建在 data/quant_analysis.db
# 包含以下表：
# - stock_basic_info: 股票基础信息
# - analysis_results: 分析结果缓存
# - core_stock_pool: 核心股票池 (如果使用)
```

### 2. 手动初始化 (可选)
```python
# 运行初始化脚本
python -c "
from backend.analysis_cache import analysis_cache
from backend.stock_pool_manager import StockPoolManager

# 初始化缓存系统
print('初始化分析缓存...')
cache_stats = analysis_cache.get_cache_stats()
print(f'缓存统计: {cache_stats}')

# 初始化股票池管理器
print('初始化股票池管理器...')
pool_manager = StockPoolManager()
print('数据库初始化完成')
"
```

## 🚀 启动服务

### 1. 开发环境启动
```bash
# 激活虚拟环境
source venv/bin/activate  # Linux/macOS
# 或 venv\Scripts\activate  # Windows

# 启动Flask开发服务器
python backend/app.py

# 或使用Flask命令
export FLASK_APP=backend/app.py
flask run --host=0.0.0.0 --port=5000
```

### 2. 生产环境部署

#### 使用Gunicorn (推荐)
```bash
# 安装Gunicorn
pip install gunicorn

# 启动Gunicorn服务器
gunicorn -w 4 -b 0.0.0.0:5000 backend.app:app

# 或使用配置文件
gunicorn -c gunicorn.conf.py backend.app:app
```

#### Gunicorn配置文件 (`gunicorn.conf.py`)
```python
# Gunicorn配置
bind = "0.0.0.0:5000"
workers = 4
worker_class = "sync"
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 100
timeout = 30
keepalive = 2
preload_app = True

# 日志配置
accesslog = "logs/gunicorn_access.log"
errorlog = "logs/gunicorn_error.log"
loglevel = "info"

# 进程配置
daemon = False
pidfile = "logs/gunicorn.pid"
user = None
group = None
```

#### 使用Nginx反向代理
```nginx
# /etc/nginx/sites-available/stock-analysis
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # 超时配置
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
    }

    # 静态文件服务
    location /static/ {
        alias /path/to/your/project/frontend/;
        expires 1d;
        add_header Cache-Control "public, immutable";
    }

    # 日志配置
    access_log /var/log/nginx/stock-analysis.access.log;
    error_log /var/log/nginx/stock-analysis.error.log;
}
```

## 🔧 系统服务配置

### 1. Systemd服务配置 (Linux)
```ini
# /etc/systemd/system/stock-analysis.service
[Unit]
Description=Stock Analysis Platform
After=network.target

[Service]
Type=exec
User=www-data
Group=www-data
WorkingDirectory=/path/to/your/project
Environment=PATH=/path/to/your/project/venv/bin
ExecStart=/path/to/your/project/venv/bin/gunicorn -c gunicorn.conf.py backend.app:app
ExecReload=/bin/kill -s HUP $MAINPID
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

启动服务：
```bash
sudo systemctl daemon-reload
sudo systemctl enable stock-analysis
sudo systemctl start stock-analysis
sudo systemctl status stock-analysis
```

### 2. Docker部署 (可选)

#### Dockerfile
```dockerfile
FROM python:3.9-slim

WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建必要目录
RUN mkdir -p data/result config logs

# 暴露端口
EXPOSE 5000

# 启动命令
CMD ["gunicorn", "-c", "gunicorn.conf.py", "backend.app:app"]
```

#### docker-compose.yml
```yaml
version: '3.8'

services:
  stock-analysis:
    build: .
    ports:
      - "5000:5000"
    volumes:
      - ./data:/app/data
      - ./config:/app/config
      - ./logs:/app/logs
    environment:
      - FLASK_ENV=production
      - LOG_LEVEL=INFO
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./frontend:/usr/share/nginx/html
    depends_on:
      - stock-analysis
    restart: unless-stopped
```

## 📊 监控与日志

### 1. 日志配置
```python
# backend/app.py 中的日志配置
import logging
from logging.handlers import RotatingFileHandler

if not app.debug:
    # 文件日志
    file_handler = RotatingFileHandler(
        'logs/app.log', 
        maxBytes=10240000, 
        backupCount=10
    )
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    
    app.logger.setLevel(logging.INFO)
    app.logger.info('Stock Analysis Platform startup')
```

### 2. 性能监控
```python
# 添加性能监控中间件
from time import time
from flask import request

@app.before_request
def before_request():
    request.start_time = time()

@app.after_request
def after_request(response):
    duration = time() - request.start_time
    app.logger.info(f'{request.method} {request.path} - {response.status_code} - {duration:.3f}s')
    return response
```

### 3. 健康检查端点
```python
@app.route('/health')
def health_check():
    """健康检查端点"""
    try:
        # 检查数据库连接
        from backend.analysis_cache import analysis_cache
        stats = analysis_cache.get_cache_stats()
        
        return jsonify({
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'cache_stats': stats,
            'version': '2.0'
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500
```

## 🔒 安全配置

### 1. 防火墙配置
```bash
# Ubuntu/Debian
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable

# CentOS/RHEL
sudo firewall-cmd --permanent --add-service=ssh
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

### 2. SSL/TLS配置 (生产环境)
```nginx
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /path/to/ssl/cert.pem;
    ssl_certificate_key /path/to/ssl/private.key;
    
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512;
    ssl_prefer_server_ciphers off;
    
    # 其他配置...
}

# HTTP重定向到HTTPS
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}
```

## 🔧 维护与备份

### 1. 数据备份脚本
```bash
#!/bin/bash
# backup.sh

BACKUP_DIR="/backup/stock-analysis"
DATE=$(date +%Y%m%d_%H%M%S)

# 创建备份目录
mkdir -p $BACKUP_DIR

# 备份数据库
cp data/quant_analysis.db $BACKUP_DIR/quant_analysis_$DATE.db

# 备份配置文件
cp -r config $BACKUP_DIR/config_$DATE

# 备份日志 (最近7天)
find logs -name "*.log" -mtime -7 -exec cp {} $BACKUP_DIR/ \;

# 压缩备份
tar -czf $BACKUP_DIR/backup_$DATE.tar.gz $BACKUP_DIR/*_$DATE*

# 清理旧备份 (保留30天)
find $BACKUP_DIR -name "backup_*.tar.gz" -mtime +30 -delete

echo "备份完成: $BACKUP_DIR/backup_$DATE.tar.gz"
```

### 2. 定期维护任务
```bash
# 添加到crontab
crontab -e

# 每天凌晨2点备份
0 2 * * * /path/to/backup.sh

# 每周清理过期缓存
0 3 * * 0 python -c "from backend.analysis_cache import analysis_cache; analysis_cache.clear_old_cache(7)"

# 每月重启服务
0 4 1 * * systemctl restart stock-analysis
```

## 🚨 故障排除

### 1. 常见问题

#### 数据库连接错误
```bash
# 检查数据库文件权限
ls -la data/quant_analysis.db
chmod 664 data/quant_analysis.db

# 检查目录权限
chmod 755 data/
```

#### 端口占用
```bash
# 查找占用端口的进程
sudo netstat -tlnp | grep :5000
sudo lsof -i :5000

# 终止进程
sudo kill -9 <PID>
```

#### 内存不足
```bash
# 检查内存使用
free -h
top -p $(pgrep -f "gunicorn")

# 调整worker数量
# 在gunicorn.conf.py中减少workers数量
```

### 2. 日志分析
```bash
# 查看应用日志
tail -f logs/app.log

# 查看错误日志
grep ERROR logs/app.log

# 查看访问日志
tail -f logs/gunicorn_access.log
```

### 3. 性能调优
```bash
# 数据库优化
sqlite3 data/quant_analysis.db "VACUUM;"
sqlite3 data/quant_analysis.db "ANALYZE;"

# 清理缓存
python -c "from backend.analysis_cache import analysis_cache; analysis_cache.clear_old_cache(1)"
```

## 📈 扩展部署

### 1. 负载均衡配置
```nginx
upstream stock_analysis {
    server 127.0.0.1:5000;
    server 127.0.0.1:5001;
    server 127.0.0.1:5002;
}

server {
    listen 80;
    location / {
        proxy_pass http://stock_analysis;
    }
}
```

### 2. 数据库集群 (高级)
```python
# 读写分离配置
DATABASE_CONFIG = {
    'master': 'sqlite:///data/master.db',
    'slaves': [
        'sqlite:///data/slave1.db',
        'sqlite:///data/slave2.db'
    ]
}
```

---

**部署指南版本**: v1.0  
**最后更新**: 2025-01-19  
**维护者**: 开发团队