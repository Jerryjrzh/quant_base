#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
股票信息爬虫模块
提供股票基本信息获取功能，包括股票名称、所属板块、行业等信息

Author: Assistant
Date: 2025-08-24
"""

import requests
import json
import time
import random
from typing import Dict, Optional, List, Union
from dataclasses import dataclass
import logging

@dataclass
class StockInfo:
    """股票信息数据类"""
    stock_code: str
    name: str = ""
    sector: str = ""  # 板块
    industry: str = ""  # 行业
    market: str = ""  # 市场（上海A股、深圳A股等）
    market_cap: str = ""  # 市值
    pe_ratio: str = ""  # 市盈率
    pb_ratio: str = ""  # 市净率
    
    def to_dict(self) -> Dict:
        """转换为字典格式"""
        return {
            'stock_code': self.stock_code,
            'name': self.name,
            'sector': self.sector,
            'industry': self.industry,
            'market': self.market,
            'market_cap': self.market_cap,
            'pe_ratio': self.pe_ratio,
            'pb_ratio': self.pb_ratio
        }

class StockInfoCrawler:
    """股票信息爬虫类"""
    
    def __init__(self, cache_file: str = "stock_info_cache.json", cache_expire_hours: int = 24):
        """
        初始化爬虫
        
        Args:
            cache_file: 缓存文件路径
            cache_expire_hours: 缓存过期时间（小时）
        """
        self.cache_file = cache_file
        self.cache_expire_hours = cache_expire_hours
        self.cache = self._load_cache()
        self.session = requests.Session()
        
        # 设置请求头，模拟浏览器访问
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        })
        
        # 配置日志
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
    
    def _load_cache(self) -> Dict:
        """加载缓存"""
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
    
    def _save_cache(self):
        """保存缓存"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.logger.error(f"保存缓存失败: {e}")
    
    def _is_cache_valid(self, cache_data: Dict) -> bool:
        """检查缓存是否有效"""
        if 'timestamp' not in cache_data:
            return False
        
        cache_time = cache_data['timestamp']
        current_time = time.time()
        expire_time = self.cache_expire_hours * 3600
        
        return (current_time - cache_time) < expire_time
    
    def _format_stock_code(self, stock_code: str) -> str:
        """格式化股票代码"""
        # 移除可能的前缀和后缀
        if '.' in stock_code:
            stock_code = stock_code.split('.')[0]
        if '#' in stock_code:
            stock_code = stock_code.replace('#', '')
        
        # 确保是6位数字
        return stock_code.zfill(6) if stock_code.isdigit() else stock_code
    
    def _get_stock_info_from_sina(self, stock_code: str) -> Optional[StockInfo]:
        """
        从新浪财经获取股票信息
        
        Args:
            stock_code: 股票代码（如 000001）
            
        Returns:
            股票信息对象或None
        """
        try:
            # 根据股票代码确定市场前缀
            if stock_code.startswith('6'):
                market_code = f"sh{stock_code}"
                market_name = "上海A股"
            elif stock_code.startswith(('0', '3')):
                market_code = f"sz{stock_code}"
                market_name = "深圳A股"
            else:
                market_code = f"sz{stock_code}"  # 默认深圳
                market_name = "深圳A股"
            
            # 新浪财经API接口
            url = f"http://hq.sinajs.cn/list={market_code}"
            
            response = self.session.get(url, timeout=10)
            response.encoding = 'gbk'  # 新浪财经使用GBK编码
            
            if response.status_code == 200:
                content = response.text.strip()
                if 'var hq_str_' in content:
                    # 解析数据
                    data_str = content.split('="')[1].split('";')[0]
                    if data_str:
                        data_parts = data_str.split(',')
                        if len(data_parts) >= 4:
                            stock_info = StockInfo(
                                stock_code=stock_code,
                                name=data_parts[0] if data_parts[0] else f"股票{stock_code}",
                                market=market_name
                            )
                            return stock_info
        except Exception as e:
            self.logger.warning(f"从新浪财经获取股票 {stock_code} 信息失败: {e}")
        
        return None
    
    def _get_stock_info_from_163(self, stock_code: str) -> Optional[StockInfo]:
        """
        从网易财经获取股票信息
        
        Args:
            stock_code: 股票代码
            
        Returns:
            股票信息对象或None
        """
        try:
            # 根据股票代码确定市场前缀
            if stock_code.startswith('6'):
                market_code = f"0{stock_code}"
                market_name = "上海A股"
            elif stock_code.startswith(('0', '3')):
                market_code = f"1{stock_code}"
                market_name = "深圳A股"
            else:
                market_code = f"1{stock_code}"
                market_name = "深圳A股"
            
            # 网易财经API
            url = f"http://api.money.126.net/data/feed/{market_code}"
            
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                content = response.text.strip()
                # 移除JSONP回调函数包装
                if content.startswith('_ntes_quote_callback('):
                    content = content[21:-2]  # 移除前缀和后缀
                
                data = json.loads(content)
                if market_code in data:
                    stock_data = data[market_code]
                    stock_info = StockInfo(
                        stock_code=stock_code,
                        name=stock_data.get('name', f"股票{stock_code}"),
                        market=market_name,
                        pe_ratio=str(stock_data.get('pe', '')),
                        pb_ratio=str(stock_data.get('pb', ''))
                    )
                    return stock_info
        except Exception as e:
            self.logger.warning(f"从网易财经获取股票 {stock_code} 信息失败: {e}")
        
        return None
    
    def _get_stock_info_from_tencent(self, stock_code: str) -> Optional[StockInfo]:
        """
        从腾讯财经获取股票信息
        
        Args:
            stock_code: 股票代码
            
        Returns:
            股票信息对象或None
        """
        try:
            # 根据股票代码确定市场前缀
            if stock_code.startswith('6'):
                market_code = f"sh{stock_code}"
                market_name = "上海A股"
            elif stock_code.startswith(('0', '3')):
                market_code = f"sz{stock_code}"
                market_name = "深圳A股"
            else:
                market_code = f"sz{stock_code}"
                market_name = "深圳A股"
            
            # 腾讯财经API
            url = f"http://qt.gtimg.cn/q={market_code}"
            
            response = self.session.get(url, timeout=10)
            response.encoding = 'gbk'
            
            if response.status_code == 200:
                content = response.text.strip()
                if content:
                    # 解析腾讯财经返回的数据
                    data_parts = content.split('~')
                    if len(data_parts) >= 2:
                        stock_info = StockInfo(
                            stock_code=stock_code,
                            name=data_parts[1] if len(data_parts) > 1 else f"股票{stock_code}",
                            market=market_name
                        )
                        return stock_info
        except Exception as e:
            self.logger.warning(f"从腾讯财经获取股票 {stock_code} 信息失败: {e}")
        
        return None
    
    def get_stock_info(self, stock_code: str, use_cache: bool = True) -> StockInfo:
        """
        获取股票信息
        
        Args:
            stock_code: 股票代码
            use_cache: 是否使用缓存
            
        Returns:
            股票信息对象
        """
        # 格式化股票代码
        formatted_code = self._format_stock_code(stock_code)
        
        # 检查缓存
        if use_cache and formatted_code in self.cache:
            cache_data = self.cache[formatted_code]
            if self._is_cache_valid(cache_data):
                stock_info = StockInfo(**cache_data['data'])
                self.logger.debug(f"从缓存获取股票信息: {formatted_code}")
                return stock_info
        
        # 尝试从多个数据源获取信息
        stock_info = None
        data_sources = [
            self._get_stock_info_from_sina,
            self._get_stock_info_from_tencent,
            self._get_stock_info_from_163
        ]
        
        for get_info_func in data_sources:
            try:
                stock_info = get_info_func(formatted_code)
                if stock_info and stock_info.name:
                    self.logger.info(f"成功获取股票信息: {formatted_code} - {stock_info.name}")
                    break
                # 添加随机延迟，避免请求过于频繁
                time.sleep(random.uniform(0.5, 1.5))
            except Exception as e:
                self.logger.warning(f"获取股票 {formatted_code} 信息时出错: {e}")
                continue
        
        # 如果所有数据源都失败，创建基本信息
        if not stock_info:
            stock_info = StockInfo(
                stock_code=formatted_code,
                name=f"股票{formatted_code}",
                sector="未知板块",
                industry="未知行业",
                market="A股"
            )
            self.logger.warning(f"无法获取股票 {formatted_code} 的详细信息，使用默认信息")
        
        # 更新缓存
        if use_cache:
            self.cache[formatted_code] = {
                'data': stock_info.to_dict(),
                'timestamp': time.time()
            }
            self._save_cache()
        
        return stock_info
    
    def get_multiple_stock_info(self, stock_codes: List[str], use_cache: bool = True) -> Dict[str, StockInfo]:
        """
        批量获取股票信息
        
        Args:
            stock_codes: 股票代码列表
            use_cache: 是否使用缓存
            
        Returns:
            股票代码到股票信息的映射
        """
        results = {}
        
        for i, stock_code in enumerate(stock_codes):
            try:
                stock_info = self.get_stock_info(stock_code, use_cache)
                results[stock_code] = stock_info
                
                # 每隔几个请求添加延迟，避免被封IP
                if (i + 1) % 5 == 0:
                    time.sleep(random.uniform(1, 3))
                    
            except Exception as e:
                self.logger.error(f"获取股票 {stock_code} 信息失败: {e}")
                # 提供默认信息
                results[stock_code] = StockInfo(
                    stock_code=stock_code,
                    name=f"股票{stock_code}",
                    sector="未知板块",
                    industry="未知行业"
                )
        
        return results
    
    def clear_cache(self):
        """清除缓存"""
        self.cache = {}
        try:
            import os
            if os.path.exists(self.cache_file):
                os.remove(self.cache_file)
            self.logger.info("缓存已清除")
        except Exception as e:
            self.logger.error(f"清除缓存失败: {e}")

# 全局实例
_stock_info_crawler = None

def get_stock_info_crawler() -> StockInfoCrawler:
    """获取股票信息爬虫实例（单例模式）"""
    global _stock_info_crawler
    if _stock_info_crawler is None:
        _stock_info_crawler = StockInfoCrawler()
    return _stock_info_crawler

def get_stock_info(stock_code: str, use_cache: bool = True) -> StockInfo:
    """
    获取股票信息的便捷函数
    
    Args:
        stock_code: 股票代码
        use_cache: 是否使用缓存
        
    Returns:
        股票信息对象
    """
    crawler = get_stock_info_crawler()
    return crawler.get_stock_info(stock_code, use_cache)

def get_multiple_stock_info(stock_codes: List[str], use_cache: bool = True) -> Dict[str, StockInfo]:
    """
    批量获取股票信息的便捷函数
    
    Args:
        stock_codes: 股票代码列表
        use_cache: 是否使用缓存
        
    Returns:
        股票代码到股票信息的映射
    """
    crawler = get_stock_info_crawler()
    return crawler.get_multiple_stock_info(stock_codes, use_cache)

if __name__ == "__main__":
    # 测试代码
    test_codes = ["000001", "600000", "300001"]
    
    print("测试股票信息爬虫...")
    crawler = StockInfoCrawler()
    
    for code in test_codes:
        print(f"\n获取股票 {code} 的信息:")
        info = crawler.get_stock_info(code)
        print(f"  股票代码: {info.stock_code}")
        print(f"  股票名称: {info.name}")
        print(f"  所属市场: {info.market}")
        print(f"  板块: {info.sector}")
        print(f"  行业: {info.industry}")
    
    print("\n批量获取股票信息:")
    batch_results = crawler.get_multiple_stock_info(test_codes)
    for code, info in batch_results.items():
        print(f"{code}: {info.name}")