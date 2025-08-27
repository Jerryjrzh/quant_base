#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一股票跟踪器
根据配置化的分级标准，从筛选结果中过滤出不同等级的股票，并展示涨幅和回测日期
消除了A级和B级跟踪器的代码重复，提供统一的、可配置的股票跟踪解决方案
"""

import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import glob
from typing import List, Dict, Any, Optional, Tuple
import data_handler

class UnifiedStockTracker:
    """统一股票跟踪器 - 支持配置化的多级股票筛选"""
    
    def __init__(self, grade_name: str, grading_criteria: Dict[str, Any]):
        """
        初始化统一股票跟踪器
        
        Args:
            grade_name: 等级名称 (如 'A', 'B', 'C')
            grading_criteria: 分级标准配置
        """
        self.grade_name = grade_name
        self.criteria = grading_criteria
        self.scan_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 设置目录路径
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
        
        # 数据缓存
        self._data_cache = {}
    
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
            
            # 搜索各种筛选结果目录
            screening_dirs = [
                'UNIVERSAL_SCREENING',
                'ABYSS_BOTTOMING',
                'MACD_ZERO_AXIS',
                'WEEKLY_GOLDEN_CROSS_MA',
                'MULTI_TIMEFRAME_PULLBACK',
                'VALUE_REVERSAL',
                'EARLY_BREAKOUT'
            ]
            
            for screening_dir in screening_dirs:
                full_screening_path = os.path.join(search_dir, screening_dir)
                if os.path.exists(full_screening_path):
                    self._load_screening_dir_results(full_screening_path, all_results, processed_files)
            
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
                    print(f"  ✅ 解析RSI分析报告: {os.path.basename(file_path)} ({len(txt_results)}条记录)")
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
    
    def _load_screening_dir_results(self, screening_path: str, all_results: List[Dict], processed_files: set):
        """加载特定筛选目录的结果"""
        json_files = glob.glob(os.path.join(screening_path, '*.json'))
        
        for file_path in json_files:
            if file_path in processed_files or 'summary' in os.path.basename(file_path):
                continue
            processed_files.add(file_path)
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    if isinstance(data, list):
                        results = data
                    elif isinstance(data, dict):
                        if 'results' in data:
                            results = data['results']
                        elif 'stocks' in data:
                            results = data['stocks']
                        elif 'signals' in data:
                            results = data['signals']
                        else:
                            continue
                    else:
                        continue
                    
                    if isinstance(results, list):
                        for item in results:
                            item['source_file'] = os.path.basename(file_path)
                            item['source_type'] = os.path.basename(screening_path).lower()
                            item['source_dir'] = screening_path
                        all_results.extend(results)
                        print(f"  ✅ 加载{os.path.basename(screening_path)}文件: {os.path.basename(file_path)} ({len(results)}条记录)")
            except Exception as e:
                print(f"  ⚠️ 读取文件失败 {file_path}: {e}")
    
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
        time_fields = ['scan_timestamp', 'last_update', 'scan_date', 'analysis_date', 'backtest_date', 'created_time', 'date']
        
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
    
    def filter_stocks_by_grade(self, all_results: List[Dict]) -> List[Dict]:
        """根据配置的分级标准过滤股票"""
        graded_stocks = []
        
        print(f"🔍 正在筛选{self.grade_name}级股票...")
        
        for result in all_results:
            is_grade_met, reason = self._check_criteria(result)
            if is_grade_met:
                result[f'{self.grade_name.lower()}_grade_reason'] = reason
                graded_stocks.append(result)
        
        print(f"✅ 筛选出 {len(graded_stocks)} 只{self.grade_name}级股票")
        return graded_stocks
    
    def _check_criteria(self, stock: Dict) -> Tuple[bool, str]:
        """检查股票是否符合分级标准"""
        # 遍历所有规则
        for rule in self.criteria.get('rules', []):
            rule_type = rule.get('type')
            
            if rule_type == 'comprehensive_score':
                score = stock.get('comprehensive_score', 0)
                score_range = rule.get('range', [0, 100])
                if score_range[0] <= score < score_range[1]:
                    return True, self._safe_format(rule.get('reason', ''), score=score)
            
            elif rule_type == 'confidence_and_risk':
                confidence = stock.get('confidence_score', 0)
                risk_level = stock.get('risk_level', '高')
                
                # 检查置信度范围
                if 'confidence_min' in rule:
                    if confidence < rule['confidence_min']:
                        continue
                if 'confidence_range' in rule:
                    conf_range = rule['confidence_range']
                    if not (conf_range[0] <= confidence < conf_range[1]):
                        continue
                
                # 检查风险等级
                if 'risk_levels' in rule:
                    if risk_level not in rule['risk_levels']:
                        continue
                
                return True, self._safe_format(rule.get('reason', ''), confidence=confidence, risk_level=risk_level)
            
            elif rule_type == 'rsi_range':
                rsi = stock.get('current_rsi6', 50)
                rsi_range = rule.get('range', [0, 100])
                confidence = stock.get('confidence_score', 0)
                confidence_min = rule.get('confidence_min', 0)
                
                if rsi_range[0] <= rsi <= rsi_range[1] and confidence >= confidence_min:
                    return True, self._safe_format(rule.get('reason', ''), rsi=rsi, confidence=confidence)
            
            elif rule_type == 'signal_strength':
                signal_strength = stock.get('signal_strength', 0)
                strength_min = rule.get('min', 1)
                confidence = self._calculate_confidence_from_signal(stock)
                confidence_min = rule.get('confidence_min', 0)
                
                if signal_strength >= strength_min and confidence >= confidence_min:
                    return True, self._safe_format(rule.get('reason', ''), strength=signal_strength, confidence=confidence)
            
            elif rule_type == 'source_specific':
                source_type = stock.get('source_type', '')
                if source_type in rule.get('sources', []):
                    # 检查源特定的条件
                    conditions = rule.get('conditions', {})
                    if self._check_source_conditions(stock, conditions):
                        # 准备格式化参数
                        format_params = {
                            'source': source_type,
                            'confidence': stock.get('confidence_score', 0),
                            'strength': stock.get('strength_score', 0),
                            'max_gain': stock.get('max_gain', 0)
                        }
                        return True, self._safe_format(rule.get('reason', ''), **format_params)
            
            elif rule_type == 'direct_grade':
                # 直接标记的等级
                if stock.get('grade') == self.grade_name or stock.get('rating') == self.grade_name:
                    return True, rule.get('reason', f'直接标记为{self.grade_name}级')
        
        return False, ""
    
    def _check_source_conditions(self, stock: Dict, conditions: Dict) -> bool:
        """检查源特定的条件"""
        for key, value in conditions.items():
            if key == 'confidence_min':
                if stock.get('confidence_score', 0) < value:
                    return False
            elif key == 'risk_levels':
                if stock.get('risk_level', '高') not in value:
                    return False
            elif key == 'expected_gain_min':
                if stock.get('avg_rebound_gain', 0) < value:
                    return False
            elif key == 'strength_min':
                if stock.get('strength_score', 0) < value:
                    return False
            elif key == 'max_gain_min':
                if stock.get('max_gain', 0) < value:
                    return False
            elif key == 'signal_strength_min':
                if stock.get('signal_strength', 0) < value:
                    return False
        return True
    
    def _safe_format(self, template: str, **kwargs) -> str:
        """安全的字符串格式化，避免KeyError"""
        try:
            return template.format(**kwargs)
        except KeyError as e:
            # 如果模板中有不存在的占位符，返回原始模板
            print(f"⚠️ 字符串格式化警告: 模板中缺少占位符 {e}")
            return template
        except Exception as e:
            print(f"⚠️ 字符串格式化错误: {e}")
            return template
    
    def _calculate_confidence_from_signal(self, result: Dict) -> float:
        """从信号数据计算置信度"""
        # 如果已有置信度，直接返回
        if 'confidence_score' in result:
            return result['confidence_score']
        
        # 根据信号强度计算置信度
        signal_strength = result.get('signal_strength', 0)
        if signal_strength >= 3:
            return 0.8
        elif signal_strength >= 2:
            return 0.7
        elif signal_strength >= 1:
            return 0.6
        else:
            return 0.5
    
    def calculate_stock_gains(self, stock_code: str, backtest_date: str) -> Dict[str, float]:
        """计算股票的5日、15日、23日涨幅 - 带缓存优化"""
        try:
            # 检查缓存
            if stock_code not in self._data_cache:
                print(f"加载数据: {stock_code}")
                df = data_handler.get_full_data_with_indicators(stock_code)
                if df is None or len(df) < 50:
                    return {'5d_gain': None, '15d_gain': None, '23d_gain': None, 'error': '数据不足'}
                self._data_cache[stock_code] = df
            else:
                df = self._data_cache[stock_code]
            
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
    
    def enrich_stocks(self, graded_stocks: List[Dict]) -> List[Dict]:
        """为分级股票补充涨幅信息"""
        enriched_stocks = []
        
        print(f"📈 正在计算{self.grade_name}级股票的涨幅表现...")
        
        for i, stock in enumerate(graded_stocks, 1):
            stock_code = stock.get('stock_code')
            if not stock_code:
                continue
                
            print(f"处理进度 [{i}/{len(graded_stocks)}]: {stock_code}")
            
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
                if stock_code in self._data_cache:
                    df = self._data_cache[stock_code]
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
        date_fields = ['date', 'scan_date', 'backtest_date', 'analysis_date', 'last_update', 'scan_timestamp']
        
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
    
    def generate_report(self, enriched_stocks: List[Dict]) -> str:
        """生成股票跟踪报告"""
        if not enriched_stocks:
            return f"未发现{self.grade_name}级股票"
        
        report = []
        report.append("=" * 100)
        report.append(f"{self.grade_name}级股票长期跟踪报告")
        report.append("=" * 100)
        report.append(f"生成时间: {self.scan_timestamp}")
        report.append(f"{self.grade_name}级股票数量: {len(enriched_stocks)}只")
        report.append("")
        
        # 分级标准说明
        report.extend(self._generate_criteria_description())
        
        # 统计摘要
        report.extend(self._generate_summary_stats(enriched_stocks))
        
        # 详细股票列表
        report.append(f"📊 {self.grade_name}级股票详细表现")
        report.append("-" * 100)
        report.append(f"{'序号':<4} {'股票代码':<12} {'回测日期':<12} {f'{self.grade_name}级原因':<30} {'5日涨幅':<10} {'15日涨幅':<10} {'23日涨幅':<10} {'当前价格':<10}")
        report.append("-" * 100)
        
        # 按5日涨幅排序
        sorted_stocks = sorted(enriched_stocks, 
                             key=lambda x: x.get('5d_gain') if x.get('5d_gain') is not None else -999, 
                             reverse=True)
        
        for i, stock in enumerate(sorted_stocks, 1):
            stock_code = stock.get('stock_code', 'N/A')
            backtest_date = stock.get('backtest_date', 'N/A')
            grade_reason = stock.get(f'{self.grade_name.lower()}_grade_reason', 'N/A')[:28]
            
            # 格式化涨幅
            gain_5d = self._format_gain(stock.get('5d_gain'))
            gain_15d = self._format_gain(stock.get('15d_gain'))
            gain_23d = self._format_gain(stock.get('23d_gain'))
            
            current_price = stock.get('current_price', 0)
            price_str = f"¥{current_price:.2f}" if current_price else "N/A"
            
            report.append(f"{i:<4} {stock_code:<12} {backtest_date:<12} {grade_reason:<30} {gain_5d:<10} {gain_15d:<10} {gain_23d:<10} {price_str:<10}")
        
        report.append("-" * 100)
        report.append("")
        
        # 表现分析
        report.extend(self._generate_performance_analysis(enriched_stocks))
        
        # 风险提示（如果配置了）
        if 'risk_warning' in self.criteria:
            report.extend(self._generate_risk_warning())
        
        return "\n".join(report)
    
    def _generate_criteria_description(self) -> List[str]:
        """生成分级标准说明"""
        description = []
        description.append(f"📋 {self.grade_name}级筛选标准:")
        
        for rule in self.criteria.get('rules', []):
            rule_type = rule.get('type')
            if rule_type == 'comprehensive_score':
                score_range = rule.get('range', [0, 100])
                description.append(f"  • 综合评分: {score_range[0]} - {score_range[1]}分")
            elif rule_type == 'confidence_and_risk':
                if 'confidence_min' in rule:
                    description.append(f"  • 最低置信度: {rule['confidence_min']:.0%}")
                if 'confidence_range' in rule:
                    conf_range = rule['confidence_range']
                    description.append(f"  • 置信度范围: {conf_range[0]:.0%} - {conf_range[1]:.0%}")
                if 'risk_levels' in rule:
                    description.append(f"  • 风险等级: {', '.join(rule['risk_levels'])}")
        
        description.append("")
        return description
    
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
        
        # 分级原因分布
        reason_counts = {}
        for stock in stocks:
            reason = stock.get(f'{self.grade_name.lower()}_grade_reason', '未知')
            # 提取原因的主要类型
            reason_type = reason.split(f'{self.grade_name}级')[0] + f'{self.grade_name}级' if f'{self.grade_name}级' in reason else reason
            reason_counts[reason_type] = reason_counts.get(reason_type, 0) + 1
        
        summary.append(f"🏆 {self.grade_name}级原因分布:")
        for reason, count in sorted(reason_counts.items(), key=lambda x: x[1], reverse=True):
            summary.append(f"  {reason}: {count}只")
        summary.append("")
        
        # 来源分布
        source_counts = {}
        for stock in stocks:
            source = stock.get('source_type', '未知')
            source_counts[source] = source_counts.get(source, 0) + 1
        
        summary.append("📂 数据来源分布:")
        for source, count in sorted(source_counts.items(), key=lambda x: x[1], reverse=True):
            summary.append(f"  {source}: {count}只")
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
        best_5d = max(stocks, key=lambda x: x.get('5d_gain') if x.get('5d_gain') is not None else -999, default=None)
        best_15d = max(stocks, key=lambda x: x.get('15d_gain') if x.get('15d_gain') is not None else -999, default=None)
        best_23d = max(stocks, key=lambda x: x.get('23d_gain') if x.get('23d_gain') is not None else -999, default=None)
        
        if best_5d and best_5d.get('5d_gain'):
            analysis.append(f"🥇 5日最佳表现: {best_5d['stock_code']} (+{best_5d['5d_gain']:.2%})")
        if best_15d and best_15d.get('15d_gain'):
            analysis.append(f"🥇 15日最佳表现: {best_15d['stock_code']} (+{best_15d['15d_gain']:.2%})")
        if best_23d and best_23d.get('23d_gain'):
            analysis.append(f"🥇 23日最佳表现: {best_23d['stock_code']} (+{best_23d['23d_gain']:.2%})")
        
        analysis.append("")
        
        # 找出表现最差的股票
        worst_5d = min(stocks, key=lambda x: x.get('5d_gain') if x.get('5d_gain') is not None else 999, default=None)
        if worst_5d and worst_5d.get('5d_gain') is not None:
            analysis.append(f"⚠️ 5日最差表现: {worst_5d['stock_code']} ({worst_5d['5d_gain']:.2%})")
        
        analysis.append("")
        
        # 一致性分析
        consistent_winners = []
        consistent_losers = []
        mixed_performance = []
        
        for stock in stocks:
            gains = [stock.get(f'{d}d_gain') for d in [5, 15, 23]]
            valid_gains = [g for g in gains if g is not None]
            
            if len(valid_gains) >= 2:
                if all(g > 0 for g in valid_gains):
                    consistent_winners.append(stock)
                elif all(g < 0 for g in valid_gains):
                    consistent_losers.append(stock)
                else:
                    mixed_performance.append(stock)
        
        analysis.append(f"🎯 全周期盈利股票: {len(consistent_winners)}只")
        if consistent_winners:
            analysis.append("   (所有有效周期均为正收益)")
            for stock in consistent_winners[:5]:  # 显示前5只
                gains_str = []
                for d in [5, 15, 23]:
                    gain = stock.get(f'{d}d_gain')
                    if gain is not None:
                        gains_str.append(f"{d}日{gain:.1%}")
                analysis.append(f"   • {stock['stock_code']}: {', '.join(gains_str)}")
        
        analysis.append("")
        analysis.append(f"⚠️ 全周期亏损股票: {len(consistent_losers)}只")
        analysis.append(f"🔄 混合表现股票: {len(mixed_performance)}只")
        analysis.append("")
        
        # 按来源类型分析表现
        source_performance = {}
        for stock in stocks:
            source = stock.get('source_type', '未知')
            if source not in source_performance:
                source_performance[source] = {'gains': [], 'count': 0}
            
            gain_5d = stock.get('5d_gain')
            if gain_5d is not None:
                source_performance[source]['gains'].append(gain_5d)
            source_performance[source]['count'] += 1
        
        analysis.append("📊 按来源类型表现分析:")
        for source, data in source_performance.items():
            if data['gains']:
                avg_gain = np.mean(data['gains'])
                win_rate = len([g for g in data['gains'] if g > 0]) / len(data['gains'])
                analysis.append(f"  {source}: 平均5日涨幅{avg_gain:.2%}, 胜率{win_rate:.1%} ({data['count']}只)")
        
        analysis.append("")
        
        return analysis
    
    def _generate_risk_warning(self) -> List[str]:
        """生成风险提示"""
        warning = []
        warning.append(f"⚠️ {self.grade_name}级股票投资风险提示")
        warning.append("-" * 50)
        
        risk_warnings = self.criteria.get('risk_warning', [])
        for i, warning_text in enumerate(risk_warnings, 1):
            warning.append(f"{i}. {warning_text}")
        
        warning.append("")
        return warning
    
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
        filename = f'{self.grade_name.lower()}_grade_stock_tracking_report_{timestamp}.txt'
        filepath = os.path.join(self.output_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report_content)
        
        print(f"📄 {self.grade_name}级股票跟踪报告已保存: {filepath}")
        return filepath
    
    def export_to_excel(self, enriched_stocks: List[Dict]) -> str:
        """导出到Excel文件"""
        try:
            import pandas as pd
            
            # 准备数据
            export_data = []
            for stock in enriched_stocks:
                export_data.append({
                    '股票代码': stock.get('stock_code', ''),
                    '回测日期': stock.get('backtest_date', ''),
                    f'{self.grade_name}级原因': stock.get(f'{self.grade_name.lower()}_grade_reason', ''),
                    '5日涨幅': stock.get('5d_gain'),
                    '15日涨幅': stock.get('15d_gain'),
                    '23日涨幅': stock.get('23d_gain'),
                    '当前价格': stock.get('current_price'),
                    '置信度': stock.get('confidence_score'),
                    '风险等级': stock.get('risk_level', ''),
                    '数据来源': stock.get('source_type', ''),
                    '源文件': stock.get('source_file', ''),
                    '重复次数': stock.get('duplicate_count', 1)
                })
            
            if not export_data:
                print(f"⚠️ 没有{self.grade_name}级股票数据可导出")
                return ""
            
            # 创建DataFrame
            df = pd.DataFrame(export_data)
            
            # 保存到Excel
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'{self.grade_name.lower()}_grade_stock_tracking_{timestamp}.xlsx'
            filepath = os.path.join(self.output_dir, filename)
            
            df.to_excel(filepath, index=False, engine='openpyxl')
            print(f"📊 {self.grade_name}级股票数据已导出到Excel: {filepath}")
            return filepath
            
        except ImportError:
            print("⚠️ 需要安装openpyxl库才能导出Excel文件")
            return ""
        except Exception as e:
            print(f"⚠️ 导出Excel失败: {e}")
            return ""
    
    def run_full_analysis(self) -> Dict[str, Any]:
        """运行完整的股票跟踪分析"""
        print(f"🚀 开始{self.grade_name}级股票跟踪分析...")
        
        # 1. 加载所有筛选结果
        all_results = self.load_all_screening_results()
        
        # 2. 去重
        deduplicated_results = self.remove_duplicate_stocks(all_results)
        
        # 3. 按等级筛选
        graded_stocks = self.filter_stocks_by_grade(deduplicated_results)
        
        # 4. 补充涨幅信息
        enriched_stocks = self.enrich_stocks(graded_stocks)
        
        # 5. 生成报告
        report_content = self.generate_report(enriched_stocks)
        
        # 6. 保存报告
        report_path = self.save_report(report_content)
        
        # 7. 导出Excel
        excel_path = self.export_to_excel(enriched_stocks)
        
        print(f"✅ {self.grade_name}级股票跟踪分析完成!")
        print(f"📄 报告文件: {report_path}")
        if excel_path:
            print(f"📊 Excel文件: {excel_path}")
        
        return {
            'grade': self.grade_name,
            'total_stocks': len(enriched_stocks),
            'report_path': report_path,
            'excel_path': excel_path,
            'stocks': enriched_stocks
        }
    
    # 解析方法保持不变，从原始代码复制
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
        signal_section = re.search(r'详细信号列表.*?\n(.*?)(?=\n\n|$)', content, re.DOTALL)
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