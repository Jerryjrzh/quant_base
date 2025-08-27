#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A级股票跟踪器
从筛选结果中过滤出深度回测表现为A级的股票，并展示涨幅和回测日期
"""

import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import glob
from typing import List, Dict, Any, Optional
import data_handler

class AGradeStockTracker:
    """A级股票跟踪器"""
    
    def __init__(self):
        self.scan_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        # 修改数据路径到data/result目录
        self.base_dir = os.path.dirname(os.path.dirname(__file__))  # 项目根目录
        self.results_dir = os.path.join(self.base_dir, 'data', 'result')
        self.output_dir = os.path.join(self.base_dir, 'data', 'result')
        
        # 确保输出目录存在
        os.makedirs(self.output_dir, exist_ok=True)
        
        # 搜索结果文件的目录列表
        self.search_dirs = [
            self.results_dir,
            os.path.join(self.base_dir, 'rsi_scan_results'),
            os.path.join(self.base_dir, 'results'),
            os.path.join(self.base_dir, 'demo_results'),
            os.path.join(self.base_dir, 'advanced_results'),
            self.base_dir  # 添加根目录搜索
        ]
    
    def load_all_screening_results(self) -> List[Dict]:
        """加载所有筛选结果"""
        all_results = []
        processed_files = set()
        
        print(f"🔍 搜索筛选结果文件...")
        
        # 搜索所有可能的结果文件
        for search_dir in self.search_dirs:
            if not os.path.exists(search_dir):
                continue
                
            print(f"📂 搜索目录: {search_dir}")
            
            # RSI底部信号结果 (JSON)
            rsi_files = glob.glob(os.path.join(search_dir, 'rsi_bottom_signals_*.json'))
            for file_path in rsi_files:
                if file_path in processed_files:
                    continue
                processed_files.add(file_path)
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            for item in data:
                                item['source_file'] = os.path.basename(file_path)
                                item['source_type'] = 'rsi_bottom'
                                item['source_dir'] = search_dir
                            all_results.extend(data)
                            print(f"  ✅ 加载RSI JSON文件: {os.path.basename(file_path)} ({len(data)}条记录)")
                except Exception as e:
                    print(f"  ⚠️ 读取文件失败 {file_path}: {e}")
            
            # RSI投资分析报告 (TXT)
            rsi_analysis_files = glob.glob(os.path.join(search_dir, 'rsi_investment_analysis_*.txt'))
            for file_path in rsi_analysis_files:
                if file_path in processed_files:
                    continue
                processed_files.add(file_path)
                
                try:
                    txt_results = self._parse_rsi_analysis_txt(file_path)
                    all_results.extend(txt_results)
                    print(f"  ✅ 解析RSI分析报告: {os.path.basename(file_path)} ({len(txt_results)}条A级记录)")
                except Exception as e:
                    print(f"  ⚠️ 解析RSI分析报告失败 {file_path}: {e}")
            
            # RSI底部扫描报告 (TXT)
            rsi_report_files = glob.glob(os.path.join(search_dir, 'rsi_bottom_report_*.txt'))
            for file_path in rsi_report_files:
                if file_path in processed_files:
                    continue
                processed_files.add(file_path)
                
                try:
                    txt_results = self._parse_rsi_report_txt(file_path)
                    all_results.extend(txt_results)
                    print(f"  ✅ 解析RSI扫描报告: {os.path.basename(file_path)} ({len(txt_results)}条记录)")
                except Exception as e:
                    print(f"  ⚠️ 解析RSI扫描报告失败 {file_path}: {e}")
            
            # 精确策略分析报告 (TXT)
            strategy_analysis_files = glob.glob(os.path.join(search_dir, 'precise_strategy_analysis_*.txt'))
            for file_path in strategy_analysis_files:
                if file_path in processed_files:
                    continue
                processed_files.add(file_path)
                
                try:
                    txt_results = self._parse_strategy_analysis_txt(file_path)
                    all_results.extend(txt_results)
                    print(f"  ✅ 解析策略分析报告: {os.path.basename(file_path)} ({len(txt_results)}条记录)")
                except Exception as e:
                    print(f"  ⚠️ 解析策略分析报告失败 {file_path}: {e}")     
       
            # 其他筛选结果
            other_files = glob.glob(os.path.join(search_dir, '*_results_*.json'))
            for file_path in other_files:
                if 'rsi_bottom_signals' in file_path or file_path in processed_files:
                    continue
                processed_files.add(file_path)
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        # 处理不同格式的结果文件
                        if isinstance(data, dict):
                            if 'results' in data:
                                results = data['results']
                            elif 'stocks' in data:
                                results = data['stocks']
                            elif 'signals' in data:
                                results = data['signals']
                            else:
                                continue
                        else:
                            results = data
                        
                        if isinstance(results, list):
                            for item in results:
                                item['source_file'] = os.path.basename(file_path)
                                item['source_type'] = 'general_screening'
                                item['source_dir'] = search_dir
                            all_results.extend(results)
                            print(f"  ✅ 加载其他文件: {os.path.basename(file_path)} ({len(results)}条记录)")
                except Exception as e:
                    print(f"  ⚠️ 读取文件失败 {file_path}: {e}")
        
        print(f"📊 总共加载了 {len(all_results)} 条筛选记录")
        return all_results
    
    def remove_duplicate_stocks(self, results: List[Dict]) -> List[Dict]:
        """去除重复的股票数据，保留最新的记录"""
        print("🔄 正在去除重复股票数据...")
        
        # 按股票代码分组
        stock_groups = {}
        for result in results:
            stock_code = result.get('stock_code')
            if not stock_code:
                continue
                
            if stock_code not in stock_groups:
                stock_groups[stock_code] = []
            stock_groups[stock_code].append(result)
        
        # 对每个股票保留最新的记录
        deduplicated_results = []
        duplicate_count = 0
        
        for stock_code, group in stock_groups.items():
            if len(group) == 1:
                deduplicated_results.append(group[0])
            else:
                # 有重复，选择最新的记录
                duplicate_count += len(group) - 1
                
                # 按日期排序，选择最新的
                sorted_group = sorted(group, key=lambda x: self._extract_timestamp(x), reverse=True)
                best_record = sorted_group[0]
                
                # 合并信息（保留最好的评分等）
                for record in sorted_group[1:]:
                    # 如果其他记录有更好的评分，则更新
                    if record.get('confidence_score', 0) > best_record.get('confidence_score', 0):
                        best_record['confidence_score'] = record['confidence_score']
                    if record.get('comprehensive_score', 0) > best_record.get('comprehensive_score', 0):
                        best_record['comprehensive_score'] = record['comprehensive_score']
                
                # 添加重复信息标记
                best_record['duplicate_sources'] = [r.get('source_file', '') for r in sorted_group]
                best_record['duplicate_count'] = len(group)
                
                deduplicated_results.append(best_record)
        
        print(f"✅ 去重完成: 原始{len(results)}条 → 去重后{len(deduplicated_results)}条 (去除{duplicate_count}条重复)")
        return deduplicated_results
    
    def _extract_timestamp(self, record: Dict) -> str:
        """从记录中提取时间戳用于排序"""
        # 尝试不同的时间字段
        time_fields = ['last_update', 'scan_date', 'analysis_date', 'backtest_date', 'created_time']
        
        for field in time_fields:
            if field in record and record[field]:
                return str(record[field])
        
        # 从文件名中提取时间
        source_file = record.get('source_file', '')
        if source_file:
            import re
            # 匹配 YYYYMMDD_HHMMSS 格式
            timestamp_match = re.search(r'(\d{8}_\d{6})', source_file)
            if timestamp_match:
                return timestamp_match.group(1)
            # 匹配 YYYYMMDD 格式
            date_match = re.search(r'(\d{8})', source_file)
            if date_match:
                return date_match.group(1)
        
        return '19700101_000000'  # 默认最早时间
    
    def _parse_rsi_analysis_txt(self, file_path: str) -> List[Dict]:
        """解析RSI投资分析报告.txt文件"""
        results = []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 提取文件时间戳
        import re
        timestamp_match = re.search(r'(\d{8}_\d{6})', os.path.basename(file_path))
        file_timestamp = timestamp_match.group(1) if timestamp_match else datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 解析A级推荐部分
        a_grade_section = re.search(r'🥇 A级推荐.*?\n(.*?)(?=🥈|$)', content, re.DOTALL)
        if a_grade_section:
            a_grade_text = a_grade_section.group(1)
            
            # 提取每只A级股票的信息
            stock_matches = re.findall(r'(\w+): 置信度([\d.]+)%, RSI6=([\d.]+), 预期收益([\d.]+)%', a_grade_text)
            
            for stock_code, confidence, rsi6, expected_gain in stock_matches:
                results.append({
                    'stock_code': stock_code,
                    'confidence_score': float(confidence) / 100,
                    'current_rsi6': float(rsi6),
                    'avg_rebound_gain': float(expected_gain) / 100,
                    'risk_level': '低',  # A级推荐都是低风险
                    'source_file': os.path.basename(file_path),
                    'source_type': 'rsi_analysis_txt',
                    'scan_date': f"{file_timestamp[:4]}-{file_timestamp[4:6]}-{file_timestamp[6:8]}",
                    'last_update': f"{file_timestamp[:4]}-{file_timestamp[4:6]}-{file_timestamp[6:8]} {file_timestamp[9:11]}:{file_timestamp[11:13]}:{file_timestamp[13:15]}"
                })
        
        return results
    
    def _parse_rsi_report_txt(self, file_path: str) -> List[Dict]:
        """解析RSI底部扫描报告.txt文件"""
        results = []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 提取文件时间戳
        import re
        timestamp_match = re.search(r'(\d{8}_\d{6})', os.path.basename(file_path))
        file_timestamp = timestamp_match.group(1) if timestamp_match else datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 解析详细信号列表
        signal_section = re.search(r'详细信号列表.*?\n(.*?)$', content, re.DOTALL)
        if signal_section:
            signal_text = signal_section.group(1)
            
            # 分割每个股票的信息块
            stock_blocks = re.split(r'\n\s*\d+\.\s+', signal_text)
            
            for block in stock_blocks[1:]:  # 跳过第一个空块
                try:
                    # 提取股票代码
                    stock_match = re.search(r'^(\w+)', block)
                    if not stock_match:
                        continue
                    stock_code = stock_match.group(1)
                    
                    # 提取各种信息
                    price_match = re.search(r'当前价格: ¥([\d.]+)', block)
                    rsi_match = re.search(r'RSI6=([\d.]+)', block)
                    confidence_match = re.search(r'置信度: ([\d.]+)%', block)
                    risk_match = re.search(r'\((低|中|高)风险\)', block)
                    gain_match = re.search(r'平均收益([\d.]+)%', block)
                    
                    if all([price_match, rsi_match, confidence_match]):
                        results.append({
                            'stock_code': stock_code,
                            'current_price': float(price_match.group(1)),
                            'current_rsi6': float(rsi_match.group(1)),
                            'confidence_score': float(confidence_match.group(1)) / 100,
                            'risk_level': risk_match.group(1) if risk_match else '中',
                            'avg_rebound_gain': float(gain_match.group(1)) / 100 if gain_match else 0.1,
                            'source_file': os.path.basename(file_path),
                            'source_type': 'rsi_report_txt',
                            'scan_date': f"{file_timestamp[:4]}-{file_timestamp[4:6]}-{file_timestamp[6:8]}",
                            'last_update': f"{file_timestamp[:4]}-{file_timestamp[4:6]}-{file_timestamp[6:8]} {file_timestamp[9:11]}:{file_timestamp[11:13]}:{file_timestamp[13:15]}"
                        })
                except Exception as e:
                    continue
        
        return results
    
    def _parse_strategy_analysis_txt(self, file_path: str) -> List[Dict]:
        """解析精确策略分析报告.txt文件"""
        results = []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 提取文件时间戳
        import re
        timestamp_match = re.search(r'(\d{8}_\d{6})', os.path.basename(file_path))
        file_timestamp = timestamp_match.group(1) if timestamp_match else datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # 解析核心股票池
        stock_pool_section = re.search(r'🏆 核心股票池.*?\n(.*?)(?=\n\n|$)', content, re.DOTALL)
        if stock_pool_section:
            pool_text = stock_pool_section.group(1)
            
            # 提取每只股票的信息
            stock_matches = re.findall(r'(\w+) ⭐强势度: ([\d.]+)%\s+选入价格: ¥([\d.]+)\s+最大涨幅: ([\d.]+)%', pool_text)
            
            for stock_code, strength, entry_price, max_gain in stock_matches:
                strength_val = float(strength)
                max_gain_val = float(max_gain)
                
                # 根据强势度和最大涨幅判断是否为A级
                if strength_val >= 15.0 and max_gain_val >= 15.0:
                    results.append({
                        'stock_code': stock_code,
                        'entry_price': float(entry_price),
                        'max_gain': max_gain_val / 100,
                        'strength_score': strength_val,
                        'comprehensive_score': min(100, strength_val * 4),  # 转换为百分制
                        'source_file': os.path.basename(file_path),
                        'source_type': 'strategy_analysis_txt',
                        'scan_date': f"{file_timestamp[:4]}-{file_timestamp[4:6]}-{file_timestamp[6:8]}",
                        'last_update': f"{file_timestamp[:4]}-{file_timestamp[4:6]}-{file_timestamp[6:8]} {file_timestamp[9:11]}:{file_timestamp[11:13]}:{file_timestamp[13:15]}"
                    })
        
        return results
    
    def filter_a_grade_stocks(self, all_results: List[Dict]) -> List[Dict]:
        """过滤出A级股票"""
        a_grade_stocks = []
        
        print("🏆 正在筛选A级股票...")
        
        for result in all_results:
            is_a_grade = False
            a_grade_reason = ""
            
            # 检查不同的A级标准
            if result.get('source_type') == 'rsi_bottom':
                # RSI底部筛选的A级标准：高置信度 + 低风险
                confidence = result.get('confidence_score', 0)
                risk_level = result.get('risk_level', '高')
                if confidence >= 0.8 and risk_level == '低':
                    is_a_grade = True
                    a_grade_reason = f"RSI底部A级 (置信度{confidence:.1%}, {risk_level}风险)"
            
            elif result.get('source_type') == 'rsi_analysis_txt':
                # 从RSI分析报告解析的A级股票（已经是A级推荐）
                is_a_grade = True
                confidence = result.get('confidence_score', 0)
                a_grade_reason = f"RSI分析A级推荐 (置信度{confidence:.1%}, 低风险)"
            
            elif result.get('source_type') == 'rsi_report_txt':
                # 从RSI扫描报告解析的高质量股票 - 放宽标准
                confidence = result.get('confidence_score', 0)
                risk_level = result.get('risk_level', '高')
                if confidence >= 0.85 or (confidence >= 0.80 and risk_level in ['低', '中']):
                    is_a_grade = True
                    a_grade_reason = f"RSI扫描A级 (置信度{confidence:.1%}, {risk_level}风险)"
            
            elif result.get('source_type') == 'strategy_analysis_txt':
                # 从策略分析报告解析的高强势股票
                strength = result.get('strength_score', 0)
                max_gain = result.get('max_gain', 0)
                if strength >= 15.0 and max_gain >= 0.15:
                    is_a_grade = True
                    a_grade_reason = f"策略分析A级 (强势度{strength}%, 最大涨幅{max_gain:.1%})"
            
            # 检查其他可能的A级标准
            elif 'grade' in result:
                if result['grade'] == 'A':
                    is_a_grade = True
                    a_grade_reason = "直接标记为A级"
            
            elif 'rating' in result:
                if result['rating'] == 'A':
                    is_a_grade = True
                    a_grade_reason = "评级为A级"
            
            # 综合评分标准
            elif 'comprehensive_score' in result:
                score = result.get('comprehensive_score', 0)
                if score >= 80:  # 假设80分以上为A级
                    is_a_grade = True
                    a_grade_reason = f"综合评分A级 ({score:.1f}分)"
            
            # 自定义A级标准：放宽标准以包含更多优质股票
            elif all(key in result for key in ['confidence_score', 'risk_level']):
                confidence = result.get('confidence_score', 0)
                risk_level = result.get('risk_level', '高')
                expected_gain = result.get('avg_rebound_gain', 0)
                
                # 多种A级标准
                if (confidence >= 0.85) or \
                   (confidence >= 0.80 and risk_level == '低') or \
                   (confidence >= 0.75 and risk_level in ['低', '中'] and expected_gain >= 0.08):
                    is_a_grade = True
                    a_grade_reason = f"综合A级 (置信度{confidence:.1%}, {risk_level}风险, 预期收益{expected_gain:.1%})"
            
            if is_a_grade:
                result['a_grade_reason'] = a_grade_reason
                a_grade_stocks.append(result)
        
        print(f"🥇 筛选出 {len(a_grade_stocks)} 只A级股票")
        return a_grade_stocks    

    def calculate_stock_gains(self, stock_code: str, backtest_date: str) -> Dict[str, float]:
        """计算股票的5日、15日、23日涨幅"""
        try:
            # 获取股票数据
            df = data_handler.get_full_data_with_indicators(stock_code)
            if df is None or len(df) < 50:
                return {'5d_gain': None, '15d_gain': None, '23d_gain': None, 'error': '数据不足'}
            
            # 找到回测日期对应的索引
            df['date'] = pd.to_datetime(df.index)
            backtest_datetime = pd.to_datetime(backtest_date)
            
            # 找到最接近回测日期的交易日
            date_diff = abs(df['date'] - backtest_datetime)
            base_idx = date_diff.idxmin()
            base_idx_pos = df.index.get_loc(base_idx)
            
            if base_idx_pos >= len(df) - 1:
                return {'5d_gain': None, '15d_gain': None, '23d_gain': None, 'error': '回测日期过于接近当前'}
            
            base_price = df.loc[base_idx, 'close']
            gains = {}
            
            # 计算不同周期的涨幅
            for days, key in [(5, '5d_gain'), (15, '15d_gain'), (23, '23d_gain')]:
                target_idx_pos = min(base_idx_pos + days, len(df) - 1)
                target_idx = df.index[target_idx_pos]
                target_price = df.loc[target_idx, 'close']
                
                gain = (target_price - base_price) / base_price
                gains[key] = gain
            
            return gains
            
        except Exception as e:
            return {'5d_gain': None, '15d_gain': None, '23d_gain': None, 'error': str(e)}
    
    def enrich_a_grade_stocks(self, a_grade_stocks: List[Dict]) -> List[Dict]:
        """为A级股票补充涨幅信息"""
        enriched_stocks = []
        
        print("📈 正在计算A级股票的涨幅表现...")
        
        for i, stock in enumerate(a_grade_stocks, 1):
            stock_code = stock.get('stock_code')
            if not stock_code:
                continue
                
            print(f"处理进度 [{i}/{len(a_grade_stocks)}]: {stock_code}")
            
            # 确定回测日期
            backtest_date = self._extract_backtest_date(stock)
            
            # 计算涨幅
            gains = self.calculate_stock_gains(stock_code, backtest_date)
            
            # 合并信息
            enriched_stock = stock.copy()
            enriched_stock.update(gains)
            enriched_stock['backtest_date'] = backtest_date
            
            # 获取当前价格信息
            try:
                df = data_handler.get_full_data_with_indicators(stock_code)
                if df is not None and len(df) > 0:
                    enriched_stock['current_price'] = df.iloc[-1]['close']
                    enriched_stock['current_date'] = df.index[-1].strftime('%Y-%m-%d')
            except:
                pass
            
            enriched_stocks.append(enriched_stock)
        
        return enriched_stocks
    
    def _extract_backtest_date(self, stock: Dict) -> str:
        """从股票记录中提取回测日期"""
        # 尝试不同的日期字段
        date_fields = ['scan_date', 'backtest_date', 'analysis_date', 'last_update']
        
        for field in date_fields:
            if field in stock and stock[field]:
                date_str = stock[field]
                # 处理不同的日期格式
                if isinstance(date_str, str):
                    if len(date_str) >= 10:
                        return date_str[:10]  # 取前10位作为日期
                    return date_str
        
        # 从文件名中提取日期
        source_file = stock.get('source_file', '')
        if source_file:
            import re
            date_match = re.search(r'(\d{8})', source_file)
            if date_match:
                date_str = date_match.group(1)
                return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        
        # 默认使用今天的日期
        return datetime.now().strftime('%Y-%m-%d')
    
    def generate_a_grade_report(self, enriched_stocks: List[Dict]) -> str:
        """生成A级股票跟踪报告"""
        if not enriched_stocks:
            return "未发现A级股票"
        
        report = []
        report.append("=" * 100)
        report.append("A级股票长期跟踪报告")
        report.append("=" * 100)
        report.append(f"生成时间: {self.scan_timestamp}")
        report.append(f"A级股票数量: {len(enriched_stocks)}只")
        report.append("")
        
        # 统计摘要
        report.extend(self._generate_summary_stats(enriched_stocks))
        
        # 详细股票列表
        report.append("📊 A级股票详细表现")
        report.append("-" * 100)
        report.append(f"{'序号':<4} {'股票代码':<12} {'回测日期':<12} {'A级原因':<25} {'5日涨幅':<10} {'15日涨幅':<10} {'23日涨幅':<10} {'当前价格':<10}")
        report.append("-" * 100)
        
        # 按5日涨幅排序
        sorted_stocks = sorted(enriched_stocks, 
                             key=lambda x: x.get('5d_gain', -999), 
                             reverse=True)
        
        for i, stock in enumerate(sorted_stocks, 1):
            stock_code = stock.get('stock_code', 'N/A')
            backtest_date = stock.get('backtest_date', 'N/A')
            a_grade_reason = stock.get('a_grade_reason', 'N/A')[:23]
            
            # 格式化涨幅
            gain_5d = self._format_gain(stock.get('5d_gain'))
            gain_15d = self._format_gain(stock.get('15d_gain'))
            gain_23d = self._format_gain(stock.get('23d_gain'))
            
            current_price = stock.get('current_price', 0)
            price_str = f"¥{current_price:.2f}" if current_price else "N/A"
            
            report.append(f"{i:<4} {stock_code:<12} {backtest_date:<12} {a_grade_reason:<25} {gain_5d:<10} {gain_15d:<10} {gain_23d:<10} {price_str:<10}")
        
        report.append("-" * 100)
        report.append("")
        
        # 表现分析
        report.extend(self._generate_performance_analysis(enriched_stocks))
        
        return "\n".join(report)    

    def _generate_summary_stats(self, stocks: List[Dict]) -> List[str]:
        """生成统计摘要"""
        summary = []
        summary.append("📈 表现统计摘要")
        summary.append("-" * 50)
        
        # 计算各周期的平均涨幅
        for days, key in [(5, '5d_gain'), (15, '15d_gain'), (23, '23d_gain')]:
            gains = [s.get(key) for s in stocks if s.get(key) is not None]
            if gains:
                avg_gain = np.mean(gains)
                positive_count = len([g for g in gains if g > 0])
                win_rate = positive_count / len(gains)
                max_gain = max(gains)
                min_gain = min(gains)
                
                summary.append(f"{days}日表现:")
                summary.append(f"  平均涨幅: {avg_gain:.2%}")
                summary.append(f"  胜率: {win_rate:.1%} ({positive_count}/{len(gains)})")
                summary.append(f"  最大涨幅: {max_gain:.2%}")
                summary.append(f"  最大跌幅: {min_gain:.2%}")
                summary.append("")
        
        # A级原因分布
        reason_counts = {}
        for stock in stocks:
            reason = stock.get('a_grade_reason', '未知')
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        
        summary.append("🏆 A级原因分布:")
        for reason, count in sorted(reason_counts.items(), key=lambda x: x[1], reverse=True):
            summary.append(f"  {reason}: {count}只")
        summary.append("")
        
        # 重复数据统计
        duplicate_stocks = [s for s in stocks if s.get('duplicate_count', 1) > 1]
        if duplicate_stocks:
            summary.append("🔄 重复数据统计:")
            summary.append(f"  有重复记录的股票: {len(duplicate_stocks)}只")
            total_duplicates = sum(s.get('duplicate_count', 1) - 1 for s in duplicate_stocks)
            summary.append(f"  总计去除重复记录: {total_duplicates}条")
            summary.append("")
        
        return summary
    
    def _generate_performance_analysis(self, stocks: List[Dict]) -> List[str]:
        """生成表现分析"""
        analysis = []
        analysis.append("🔍 深度表现分析")
        analysis.append("-" * 50)
        
        # 找出表现最好的股票
        best_5d = max(stocks, key=lambda x: x.get('5d_gain', -999), default=None)
        best_15d = max(stocks, key=lambda x: x.get('15d_gain', -999), default=None)
        best_23d = max(stocks, key=lambda x: x.get('23d_gain', -999), default=None)
        
        if best_5d and best_5d.get('5d_gain'):
            analysis.append(f"🥇 5日最佳表现: {best_5d['stock_code']} (+{best_5d['5d_gain']:.2%})")
        if best_15d and best_15d.get('15d_gain'):
            analysis.append(f"🥇 15日最佳表现: {best_15d['stock_code']} (+{best_15d['15d_gain']:.2%})")
        if best_23d and best_23d.get('23d_gain'):
            analysis.append(f"🥇 23日最佳表现: {best_23d['stock_code']} (+{best_23d['23d_gain']:.2%})")
        
        analysis.append("")
        
        # 找出表现最差的股票
        worst_5d = min(stocks, key=lambda x: x.get('5d_gain', 999), default=None)
        if worst_5d and worst_5d.get('5d_gain') is not None:
            analysis.append(f"⚠️ 5日最差表现: {worst_5d['stock_code']} ({worst_5d['5d_gain']:.2%})")
        
        analysis.append("")
        
        # 一致性分析
        consistent_winners = []
        for stock in stocks:
            gains = [stock.get(f'{d}d_gain') for d in [5, 15, 23]]
            if all(g is not None and g > 0 for g in gains):
                consistent_winners.append(stock)
        
        analysis.append(f"🎯 全周期盈利股票: {len(consistent_winners)}只")
        if consistent_winners:
            analysis.append("   (5日、15日、23日均为正收益)")
            for stock in consistent_winners[:5]:  # 显示前5只
                analysis.append(f"   • {stock['stock_code']}: "
                              f"5日{stock['5d_gain']:.1%}, "
                              f"15日{stock['15d_gain']:.1%}, "
                              f"23日{stock['23d_gain']:.1%}")
        
        analysis.append("")
        
        return analysis
    
    def _format_gain(self, gain: Optional[float]) -> str:
        """格式化涨幅显示"""
        if gain is None:
            return "N/A"
        elif gain >= 0:
            return f"+{gain:.1%}"
        else:
            return f"{gain:.1%}"
    
    def save_report(self, report_content: str) -> str:
        """保存报告到data/result目录"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'a_grade_stock_tracking_report_{timestamp}.txt'
        filepath = os.path.join(self.output_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report_content)
        
        print(f"📄 A级股票跟踪报告已保存: {filepath}")
        return filepath
    
    def export_to_excel(self, enriched_stocks: List[Dict]) -> str:
        """导出到Excel文件"""
        try:
            # 准备数据
            export_data = []
            for stock in enriched_stocks:
                export_data.append({
                    '股票代码': stock.get('stock_code', ''),
                    '回测日期': stock.get('backtest_date', ''),
                    'A级原因': stock.get('a_grade_reason', ''),
                    '5日涨幅': stock.get('5d_gain'),
                    '15日涨幅': stock.get('15d_gain'),
                    '23日涨幅': stock.get('23d_gain'),
                    '当前价格': stock.get('current_price'),
                    '置信度': stock.get('confidence_score'),
                    '风险等级': stock.get('risk_level', ''),
                    '预期收益': stock.get('avg_rebound_gain'),
                    '数据来源': stock.get('source_file', ''),
                    '重复记录数': stock.get('duplicate_count', 1)
                })
            
            df = pd.DataFrame(export_data)
            
            # 格式化百分比列
            for col in ['5日涨幅', '15日涨幅', '23日涨幅', '置信度', '预期收益']:
                if col in df.columns:
                    df[col] = df[col].apply(lambda x: f"{x:.2%}" if pd.notna(x) else "N/A")
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'a_grade_stock_tracking_{timestamp}.xlsx'
            filepath = os.path.join(self.output_dir, filename)
            
            df.to_excel(filepath, index=False, engine='openpyxl')
            print(f"📊 A级股票数据已导出到Excel: {filepath}")
            return filepath
            
        except ImportError:
            print("⚠️ 需要安装 openpyxl 库才能导出Excel文件")
            return ""
        except Exception as e:
            print(f"❌ 导出Excel失败: {e}")
            return ""

def main():
    """主函数"""
    print("🔍 开始筛选和跟踪A级股票...")
    
    tracker = AGradeStockTracker()
    
    # 1. 加载所有筛选结果
    all_results = tracker.load_all_screening_results()
    
    if not all_results:
        print("❌ 未找到任何筛选结果文件")
        return
    
    # 2. 去除重复数据
    deduplicated_results = tracker.remove_duplicate_stocks(all_results)
    
    # 3. 过滤A级股票
    a_grade_stocks = tracker.filter_a_grade_stocks(deduplicated_results)
    
    if not a_grade_stocks:
        print("❌ 未发现A级股票")
        return
    
    # 4. 补充涨幅信息
    enriched_stocks = tracker.enrich_a_grade_stocks(a_grade_stocks)
    
    # 5. 生成报告
    report = tracker.generate_a_grade_report(enriched_stocks)
    
    # 6. 保存报告
    report_file = tracker.save_report(report)
    
    # 7. 导出Excel
    excel_file = tracker.export_to_excel(enriched_stocks)
    
    # 8. 显示关键信息
    print("\n🎯 A级股票跟踪摘要:")
    print(f"📊 总计A级股票: {len(enriched_stocks)}只")
    
    # 显示表现最好的前5只
    valid_stocks = [s for s in enriched_stocks if s.get('5d_gain') is not None]
    if valid_stocks:
        top_performers = sorted(valid_stocks, key=lambda x: x['5d_gain'], reverse=True)[:5]
        print("\n🏆 5日表现最佳的A级股票:")
        for i, stock in enumerate(top_performers, 1):
            print(f"  {i}. {stock['stock_code']}: +{stock['5d_gain']:.2%} "
                  f"(回测日期: {stock.get('backtest_date', 'N/A')})")
    
    print(f"\n📖 详细报告: {report_file}")
    if excel_file:
        print(f"📊 Excel数据: {excel_file}")

if __name__ == "__main__":
    main()