#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
全局配置管理模块
统一管理所有模块的配置项
"""

import os

# 数据路径配置
BASE_PATH = os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc")

# 市场配置
MARKETS = ['sh', 'sz', 'bj']

# 有效股票代码前缀
VALID_PREFIXES = {
    'sh': ['600', '601', '603', '605', '688'],
    'sz': ['000', '001', '002', '003', '300'],
    'bj': ['430', '831', '832', '833', '834', '835', '836', '837', '838', '839'],
    'ds': ['31#', '43#', '48#']
}

# 性能配置
DEFAULT_DATA_LENGTH = 500
MAX_CONCURRENT_STRATEGIES = 5
ENABLE_PARALLEL_PROCESSING = True

# 日志配置
LOG_LEVEL = "INFO"