# 环境配置指南

## 🎯 概览

本指南详细介绍了股票筛选与分析平台的环境配置过程，包括系统要求、依赖安装、配置设置和验证测试。

## 💻 系统要求

### 最低配置要求
- **操作系统**: Linux (Ubuntu 18.04+), macOS (10.14+), Windows 10+
- **Python版本**: Python 3.8+
- **内存**: 4GB RAM (推荐8GB+)
- **存储空间**: 10GB可用空间 (数据文件需要额外空间)
- **CPU**: 双核处理器 (推荐四核+)

### 推荐配置
- **操作系统**: Ubuntu 20.04 LTS 或 CentOS 8+
- **Python版本**: Python 3.9 或 3.10
- **内存**: 16GB RAM
- **存储空间**: 50GB SSD
- **CPU**: 8核处理器
- **网络**: 稳定的互联网连接

## 🐍 Python环境配置

### 1. Python安装

#### Ubuntu/Debian
```bash
# 更新包管理器
sudo apt update

# 安装Python 3.9
sudo apt install python3.9 python3.9-dev python3.9-venv

# 安装pip
sudo apt install python3-pip

# 验证安装
python3.9 --version
pip3 --version
```

#### CentOS/RHEL
```bash
# 安装EPEL仓库
sudo yum install epel-release

# 安装Python 3.9
sudo yum install python39 python39-devel python39-pip

# 创建软链接
sudo ln -s /usr/bin/python3.9 /usr/bin/python3
sudo ln -s /usr/bin/pip3.9 /usr/bin/pip3
```

#### macOS
```bash
# 使用Homebrew安装
brew install python@3.9

# 或使用pyenv管理多版本Python
brew install pyenv
pyenv install 3.9.16
pyenv global 3.9.16
```

#### Windows
```powershell
# 使用Chocolatey安装
choco install python --version=3.9.16

# 或从官网下载安装包
# https://www.python.org/downloads/windows/
```

### 2. 虚拟环境创建

```bash
# 创建项目目录
mkdir stock-analysis-platform
cd stock-analysis-platform

# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
# Linux/macOS:
source venv/bin/activate

# Windows:
# venv\Scripts\activate

# 验证虚拟环境
which python
python --version
```

### 3. 依赖包安装

#### 核心依赖安装
```bash
# 升级pip
pip install --upgrade pip

# 安装核心依赖
pip install pandas==1.5.3
pip install numpy==1.24.3
pip install flask==2.3.2
pip install flask-cors==4.0.0
pip install requests==2.31.0
pip install python-dateutil==2.8.2
pip install pytz==2023.3
```

#### 技术分析依赖
```bash
# 技术指标计算
pip install TA-Lib==0.4.25  # 可选，需要编译
pip install talib-binary==0.4.19  # 预编译版本

# 数据处理
pip install scipy==1.10.1
pip install scikit-learn==1.3.0
```

#### 可视化依赖
```bash
# 图表生成
pip install matplotlib==3.7.1
pip install seaborn==0.12.2
pip install plotly==5.15.0

# Web图表
pip install pyecharts==1.9.1
```

#### 数据库依赖
```bash
# SQLite (Python内置)
# 可选的数据库支持
pip install redis==4.6.0  # Redis缓存
pip install pymongo==4.4.1  # MongoDB
```

#### 开发和测试依赖
```bash
# 测试框架
pip install pytest==7.4.0
pip install pytest-cov==4.1.0

# 代码质量
pip install black==23.7.0
pip install flake8==6.0.0
pip install mypy==1.4.1

# 文档生成
pip install sphinx==7.1.2
pip install sphinx-rtd-theme==1.3.0
```

#### 使用requirements.txt安装
```bash
# 创建requirements.txt文件
cat > requirements.txt << EOF
# 核心依赖
pandas==1.5.3
numpy==1.24.3
flask==2.3.2
flask-cors==4.0.0
requests==2.31.0
python-dateutil==2.8.2
pytz==2023.3

# 技术分析
talib-binary==0.4.19
scipy==1.10.1
scikit-learn==1.3.0

# 可视化
matplotlib==3.7.1
seaborn==0.12.2
plotly==5.15.0
pyecharts==1.9.1

# 缓存
redis==4.6.0

# 开发工具
pytest==7.4.0
pytest-cov==4.1.0
black==23.7.0
flake8==6.0.0
EOF

# 安装所有依赖
pip install -r requirements.txt
```

## 📁 项目结构配置

### 1. 创建项目目录结构

```bash
# 创建主要目录
mkdir -p backend/{data,cache,logs}
mkdir -p frontend/{js,css,images}
mkdir -p data/{vipdoc,result,cache}
mkdir -p reports
mkdir -p tests
mkdir -p doc
mkdir -p config

# 创建子目录
mkdir -p data/vipdoc/{sh,sz,bj}
mkdir -p data/result/{TRIPLE_CROSS,PRE_CROSS,MACD_ZERO_AXIS}
mkdir -p backend/data
mkdir -p logs/{workflow,error,debug}

# 验证目录结构
tree -L 3
```

### 2. 配置文件设置

#### 主配置文件 (config/app_config.json)
```json
{
  "app": {
    "name": "股票筛选与分析平台",
    "version": "1.0.0",
    "debug": false,
    "host": "0.0.0.0",
    "port": 5000
  },
  "data": {
    "vipdoc_path": "data/vipdoc",
    "result_path": "data/result",
    "cache_path": "data/cache",
    "cache_enabled": true,
    "cache_size_limit": 100,
    "cache_ttl": 3600
  },
  "database": {
    "type": "sqlite",
    "path": "stock_pool.db",
    "redis": {
      "host": "localhost",
      "port": 6379,
      "db": 0,
      "password": null
    }
  },
  "logging": {
    "level": "INFO",
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "file": "logs/app.log",
    "max_size_mb": 10,
    "backup_count": 5
  }
}
```

#### 工作流配置文件 (config/workflow_config.json)
```json
{
  "phases": {
    "phase1": {
      "name": "深度海选与参数优化",
      "frequency_hours": 168,
      "enabled": true,
      "optimization": {
        "max_combinations": 100,
        "sample_size": 50,
        "timeout_minutes": 30
      },
      "screening": {
        "min_signal_strength": 70,
        "enable_win_rate_filter": true,
        "parallel_workers": 4,
        "batch_size": 20
      },
      "quality_assessment": {
        "min_quality_score": 70,
        "max_risk_score": 60
      },
      "core_pool": {
        "max_size": 50,
        "min_size": 10
      }
    },
    "phase2": {
      "name": "每日验证与信号触发",
      "frequency_hours": 24,
      "enabled": true,
      "signal_scan": {
        "strategies": ["TRIPLE_CROSS", "PRE_CROSS"],
        "min_confidence": 0.7,
        "enable_t1_check": true
      },
      "signal_verification": {
        "min_quality_threshold": 75,
        "max_risk_threshold": 50
      },
      "notifications": {
        "enabled": true,
        "min_signals": 1
      }
    },
    "phase3": {
      "name": "绩效跟踪与反馈",
      "frequency_hours": 72,
      "enabled": true,
      "performance_analysis": {
        "min_history_days": 30,
        "lookback_days": 90
      },
      "underperformance_criteria": {
        "min_win_rate": 0.4,
        "min_avg_return": 0.02,
        "min_signals": 3
      },
      "pool_adjustment": {
        "max_removals_per_run": 10,
        "replacement_enabled": true
      }
    }
  },
  "strategies": {
    "TRIPLE_CROSS": {
      "enabled": true,
      "macd": {
        "fast_period": 12,
        "slow_period": 26,
        "signal_period": 9
      },
      "kdj": {
        "period": 27,
        "k_smooth": 3,
        "d_smooth": 3
      },
      "rsi": {
        "period": 14
      },
      "signal_threshold": 70
    },
    "PRE_CROSS": {
      "enabled": true,
      "macd": {
        "fast_period": 12,
        "slow_period": 26,
        "signal_period": 9
      },
      "kdj": {
        "period": 27,
        "k_smooth": 3,
        "d_smooth": 3
      },
      "signal_threshold": 60
    }
  }
}
```

#### 环境变量配置 (.env)
```bash
# 应用配置
FLASK_APP=backend/app.py
FLASK_ENV=production
FLASK_DEBUG=False

# 数据路径
DATA_PATH=data/vipdoc
RESULT_PATH=data/result
LOG_PATH=logs

# 数据库配置
DATABASE_URL=sqlite:///stock_pool.db
REDIS_URL=redis://localhost:6379/0

# 安全配置
SECRET_KEY=your-secret-key-here
JWT_SECRET_KEY=your-jwt-secret-key

# 外部API配置
STOCK_API_KEY=your-api-key
STOCK_API_URL=https://api.example.com

# 通知配置
EMAIL_SMTP_SERVER=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_USERNAME=your-email@gmail.com
EMAIL_PASSWORD=your-app-password

# 性能配置
MAX_WORKERS=4
CACHE_SIZE=100
TIMEOUT_SECONDS=300
```

## 🔧 系统服务配置

### 1. Systemd服务配置 (Linux)

#### 创建服务文件
```bash
sudo tee /etc/systemd/system/stock-analysis.service << EOF
[Unit]
Description=Stock Analysis Platform
After=network.target

[Service]
Type=simple
User=stockuser
Group=stockuser
WorkingDirectory=/opt/stock-analysis-platform
Environment=PATH=/opt/stock-analysis-platform/venv/bin
ExecStart=/opt/stock-analysis-platform/venv/bin/python backend/app.py
ExecReload=/bin/kill -HUP \$MAINPID
Restart=always
RestartSec=10

# 日志配置
StandardOutput=journal
StandardError=journal
SyslogIdentifier=stock-analysis

# 安全配置
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/opt/stock-analysis-platform

[Install]
WantedBy=multi-user.target
EOF
```

#### 启用和启动服务
```bash
# 重新加载systemd配置
sudo systemctl daemon-reload

# 启用服务
sudo systemctl enable stock-analysis

# 启动服务
sudo systemctl start stock-analysis

# 检查服务状态
sudo systemctl status stock-analysis

# 查看日志
sudo journalctl -u stock-analysis -f
```

### 2. 定时任务配置 (Crontab)

```bash
# 编辑crontab
crontab -e

# 添加定时任务
# 每天早上8点执行工作流
0 8 * * * cd /opt/stock-analysis-platform && /opt/stock-analysis-platform/venv/bin/python run_workflow.py >> logs/cron.log 2>&1

# 每周日凌晨2点执行深度海选
0 2 * * 0 cd /opt/stock-analysis-platform && /opt/stock-analysis-platform/venv/bin/python run_workflow.py --phase phase1 --force >> logs/cron.log 2>&1

# 每小时检查系统健康状态
0 * * * * cd /opt/stock-analysis-platform && /opt/stock-analysis-platform/venv/bin/python -c "from doc.debugging.troubleshooting import system_health_check; system_health_check()" >> logs/health.log 2>&1
```

## 🐳 Docker容器化配置

### 1. Dockerfile

```dockerfile
# 使用官方Python基础镜像
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    wget \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制requirements文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建必要目录
RUN mkdir -p logs data/vipdoc data/result reports cache

# 设置环境变量
ENV FLASK_APP=backend/app.py
ENV FLASK_ENV=production
ENV PYTHONPATH=/app

# 暴露端口
EXPOSE 5000

# 创建非root用户
RUN useradd -m -u 1000 stockuser && \
    chown -R stockuser:stockuser /app
USER stockuser

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# 启动命令
CMD ["python", "backend/app.py"]
```

### 2. Docker Compose配置

```yaml
version: '3.8'

services:
  stock-analysis:
    build: .
    container_name: stock-analysis-app
    ports:
      - "5000:5000"
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
      - ./reports:/app/reports
      - ./config:/app/config
    environment:
      - FLASK_ENV=production
      - DATABASE_URL=sqlite:///data/stock_pool.db
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis
    restart: unless-stopped
    networks:
      - stock-network

  redis:
    image: redis:7-alpine
    container_name: stock-analysis-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
    restart: unless-stopped
    networks:
      - stock-network

  nginx:
    image: nginx:alpine
    container_name: stock-analysis-nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./frontend:/usr/share/nginx/html
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - stock-analysis
    restart: unless-stopped
    networks:
      - stock-network

volumes:
  redis_data:

networks:
  stock-network:
    driver: bridge
```

### 3. Nginx配置

```nginx
events {
    worker_connections 1024;
}

http {
    upstream stock_app {
        server stock-analysis:5000;
    }

    server {
        listen 80;
        server_name localhost;

        # 静态文件服务
        location / {
            root /usr/share/nginx/html;
            index index.html;
            try_files $uri $uri/ =404;
        }

        # API代理
        location /api/ {
            proxy_pass http://stock_app/;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # WebSocket支持
        location /ws {
            proxy_pass http://stock_app;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }
    }
}
```

## 🔍 环境验证

### 1. 基础环境验证脚本

```python
#!/usr/bin/env python3
"""
环境验证脚本
"""

import sys
import os
import subprocess
import importlib
import json
from pathlib import Path

def check_python_version():
    """检查Python版本"""
    version = sys.version_info
    print(f"Python版本: {version.major}.{version.minor}.{version.micro}")
    
    if version.major != 3 or version.minor < 8:
        print("❌ Python版本过低，需要Python 3.8+")
        return False
    else:
        print("✅ Python版本符合要求")
        return True

def check_required_packages():
    """检查必需的包"""
    required_packages = [
        'pandas', 'numpy', 'flask', 'requests', 
        'matplotlib', 'scipy', 'sklearn'
    ]
    
    missing_packages = []
    
    for package in required_packages:
        try:
            importlib.import_module(package)
            print(f"✅ {package}: 已安装")
        except ImportError:
            print(f"❌ {package}: 未安装")
            missing_packages.append(package)
    
    return len(missing_packages) == 0, missing_packages

def check_directory_structure():
    """检查目录结构"""
    required_dirs = [
        'backend', 'frontend', 'data', 'data/vipdoc',
        'data/result', 'reports', 'logs', 'config'
    ]
    
    missing_dirs = []
    
    for dir_path in required_dirs:
        if os.path.exists(dir_path):
            print(f"✅ {dir_path}: 存在")
        else:
            print(f"❌ {dir_path}: 不存在")
            missing_dirs.append(dir_path)
    
    return len(missing_dirs) == 0, missing_dirs

def check_config_files():
    """检查配置文件"""
    config_files = [
        'config/app_config.json',
        'config/workflow_config.json'
    ]
    
    missing_configs = []
    
    for config_file in config_files:
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    json.load(f)
                print(f"✅ {config_file}: 存在且格式正确")
            except json.JSONDecodeError:
                print(f"⚠️  {config_file}: 存在但格式错误")
                missing_configs.append(config_file)
        else:
            print(f"❌ {config_file}: 不存在")
            missing_configs.append(config_file)
    
    return len(missing_configs) == 0, missing_configs

def check_data_files():
    """检查数据文件"""
    data_dirs = ['data/vipdoc/sh', 'data/vipdoc/sz', 'data/vipdoc/bj']
    
    total_files = 0
    
    for data_dir in data_dirs:
        if os.path.exists(data_dir):
            day_files = [f for f in os.listdir(data_dir) if f.endswith('.day')]
            total_files += len(day_files)
            print(f"✅ {data_dir}: {len(day_files)} 个.day文件")
        else:
            print(f"❌ {data_dir}: 目录不存在")
    
    return total_files > 0

def check_system_resources():
    """检查系统资源"""
    try:
        import psutil
        
        # 内存检查
        memory = psutil.virtual_memory()
        memory_gb = memory.total / (1024**3)
        print(f"系统内存: {memory_gb:.1f}GB")
        
        if memory_gb < 4:
            print("⚠️  内存可能不足，建议4GB+")
        else:
            print("✅ 内存充足")
        
        # CPU检查
        cpu_count = psutil.cpu_count()
        print(f"CPU核心数: {cpu_count}")
        
        # 磁盘空间检查
        disk = psutil.disk_usage('.')
        disk_free_gb = disk.free / (1024**3)
        print(f"可用磁盘空间: {disk_free_gb:.1f}GB")
        
        if disk_free_gb < 10:
            print("⚠️  磁盘空间不足，建议10GB+")
        else:
            print("✅ 磁盘空间充足")
        
        return True
        
    except ImportError:
        print("⚠️  无法检查系统资源 (psutil未安装)")
        return True

def main():
    """主验证函数"""
    print("🔍 开始环境验证...")
    print("=" * 50)
    
    all_checks_passed = True
    
    # 1. Python版本检查
    print("\n1. Python版本检查")
    if not check_python_version():
        all_checks_passed = False
    
    # 2. 包依赖检查
    print("\n2. 包依赖检查")
    packages_ok, missing_packages = check_required_packages()
    if not packages_ok:
        all_checks_passed = False
        print(f"缺少包: {', '.join(missing_packages)}")
        print("请运行: pip install -r requirements.txt")
    
    # 3. 目录结构检查
    print("\n3. 目录结构检查")
    dirs_ok, missing_dirs = check_directory_structure()
    if not dirs_ok:
        all_checks_passed = False
        print(f"缺少目录: {', '.join(missing_dirs)}")
        print("请运行环境配置脚本创建目录")
    
    # 4. 配置文件检查
    print("\n4. 配置文件检查")
    configs_ok, missing_configs = check_config_files()
    if not configs_ok:
        all_checks_passed = False
        print(f"配置文件问题: {', '.join(missing_configs)}")
    
    # 5. 数据文件检查
    print("\n5. 数据文件检查")
    if not check_data_files():
        print("⚠️  没有找到股票数据文件")
        print("请将vipdoc数据文件放置到data/vipdoc目录")
    
    # 6. 系统资源检查
    print("\n6. 系统资源检查")
    check_system_resources()
    
    # 总结
    print("\n" + "=" * 50)
    if all_checks_passed:
        print("🎉 环境验证通过！系统可以正常运行")
        return 0
    else:
        print("❌ 环境验证失败，请解决上述问题后重试")
        return 1

if __name__ == "__main__":
    sys.exit(main())
```

### 2. 运行验证

```bash
# 运行环境验证脚本
python verify_environment.py

# 如果验证失败，根据提示解决问题
# 然后重新运行验证
```

### 3. 功能测试

```bash
# 测试数据加载
python -c "
from backend.data_loader import DataLoader
loader = DataLoader()
stocks = loader.get_stock_list()
print(f'找到 {len(stocks)} 只股票')
if stocks:
    df = loader.load_stock_data(stocks[0])
    print(f'加载 {stocks[0]} 数据: {len(df)} 条记录')
"

# 测试策略分析
python -c "
from backend.strategies import analyze_triple_cross
from backend.data_loader import DataLoader
loader = DataLoader()
stocks = loader.get_stock_list()
if stocks:
    df = loader.load_stock_data(stocks[0])
    config = {'macd': {'fast_period': 12, 'slow_period': 26, 'signal_period': 9}}
    result = analyze_triple_cross(df, config)
    print(f'策略分析结果: {result}')
"

# 测试Web服务
python backend/app.py &
sleep 5
curl http://localhost:5000/health
kill %1
```

## 🚀 快速启动脚本

### 一键环境配置脚本

```bash
#!/bin/bash
# setup_environment.sh - 一键环境配置脚本

set -e

echo "🚀 开始配置股票分析平台环境..."

# 检查Python版本
python_version=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
required_version="3.8"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "❌ Python版本过低: $python_version，需要3.8+"
    exit 1
fi

echo "✅ Python版本检查通过: $python_version"

# 创建虚拟环境
if [ ! -d "venv" ]; then
    echo "📦 创建虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
source venv/bin/activate

# 升级pip
echo "⬆️  升级pip..."
pip install --upgrade pip

# 安装依赖
echo "📚 安装依赖包..."
pip install -r requirements.txt

# 创建目录结构
echo "📁 创建目录结构..."
mkdir -p backend/{data,cache,logs}
mkdir -p frontend/{js,css,images}
mkdir -p data/{vipdoc,result,cache}
mkdir -p data/vipdoc/{sh,sz,bj}
mkdir -p data/result/{TRIPLE_CROSS,PRE_CROSS,MACD_ZERO_AXIS}
mkdir -p reports
mkdir -p tests
mkdir -p doc
mkdir -p config
mkdir -p logs/{workflow,error,debug}

# 创建配置文件
echo "⚙️  创建配置文件..."
if [ ! -f "config/app_config.json" ]; then
    cat > config/app_config.json << 'EOF'
{
  "app": {
    "name": "股票筛选与分析平台",
    "version": "1.0.0",
    "debug": false,
    "host": "0.0.0.0",
    "port": 5000
  },
  "data": {
    "vipdoc_path": "data/vipdoc",
    "result_path": "data/result",
    "cache_enabled": true,
    "cache_size_limit": 100
  },
  "logging": {
    "level": "INFO",
    "file": "logs/app.log"
  }
}
EOF
fi

if [ ! -f "config/workflow_config.json" ]; then
    cat > config/workflow_config.json << 'EOF'
{
  "phases": {
    "phase1": {
      "frequency_hours": 168,
      "screening": {
        "min_signal_strength": 70,
        "parallel_workers": 4
      }
    },
    "phase2": {
      "frequency_hours": 24,
      "signal_scan": {
        "strategies": ["TRIPLE_CROSS", "PRE_CROSS"]
      }
    },
    "phase3": {
      "frequency_hours": 72
    }
  }
}
EOF
fi

# 创建启动脚本
echo "🎬 创建启动脚本..."
cat > start.sh << 'EOF'
#!/bin/bash
source venv/bin/activate
export FLASK_APP=backend/app.py
export PYTHONPATH=$(pwd)
python backend/app.py
EOF
chmod +x start.sh

# 运行环境验证
echo "🔍 运行环境验证..."
python verify_environment.py

echo "🎉 环境配置完成！"
echo ""
echo "📋 下一步操作:"
echo "1. 将股票数据文件放置到 data/vipdoc/ 目录"
echo "2. 运行 ./start.sh 启动服务"
echo "3. 访问 http://localhost:5000 查看Web界面"
echo ""
echo "🔧 常用命令:"
echo "  启动服务: ./start.sh"
echo "  运行工作流: python run_workflow.py"
echo "  系统检查: python verify_environment.py"
```

### 使用方法

```bash
# 下载或创建配置脚本
chmod +x setup_environment.sh

# 运行一键配置
./setup_environment.sh

# 启动服务
./start.sh
```

通过这个详细的环境配置指南，用户可以快速搭建完整的股票分析平台运行环境，无论是开发环境还是生产环境都能得到很好的支持。