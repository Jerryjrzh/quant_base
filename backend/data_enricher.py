#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据丰富器 - 为股票添加丰富的画像信息

这个模块负责：
- 从多个数据源获取股票的基本面和技术面信息
- 计算健康分数
- 更新股票画像到数据库
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import pandas as pd

# 导入爬虫模块
from craw import stock_lhb_em, stock_fhps_em
from stock_pool_manager import StockPoolManager


class DataEnricher:
    """数据丰富器"""
    
    def __init__(self, db_path: str = "stock_pool.db"):
        """初始化数据丰富器"""
        self.pool_manager = StockPoolManager(db_path)
        self.logger = logging.getLogger(__name__)
        
    def enrich_single_stock(self, stock_code: str) -> bool:
        """为单只股票丰富数据并更新到数据库"""
        self.logger.info(f"开始丰富数据: {stock_code}")
        enriched_data = {}
        today_str = datetime.now().strftime('%Y%m%d')
        
        try:
            # 优先级 1: 龙虎榜数据 (数据价值最高)
            try:
                lhb_df = stock_lhb_em.stock_lhb_detail_em(
                    start_date=today_str, 
                    end_date=today_str
                )
                # --- 增加 `is not None` 判断 ---
                if lhb_df is not None and not lhb_df.empty:
                    stock_lhb = lhb_df[lhb_df['代码'] == stock_code.replace('sh', '').replace('sz', '')]
                    if not stock_lhb.empty:
                        enriched_data['lhb_history'] = json.dumps(
                            stock_lhb.to_dict('records'), 
                            ensure_ascii=False
                        )
                        self.logger.info(f"{stock_code} 发现龙虎榜数据")
            except Exception as e:
                self.logger.warning(f"获取 {stock_code} 龙虎榜数据失败: {e}")

            # 优先级 2: 分红送配数据 (获取财务基本面)
            try:
                # 查询最近的年报数据
                report_date = str(datetime.now().year - 1) + "1231"
                fhps_df = stock_fhps_em.stock_fhps_em(date=report_date)
                if not fhps_df.empty:
                    stock_fhps = fhps_df[fhps_df['代码'] == stock_code.replace('sh', '').replace('sz', '')]
                    if not stock_fhps.empty:
                        row = stock_fhps.iloc[0]
                        if '每股收益' in row and pd.notna(row['每股收益']):
                            enriched_data['eps'] = float(row['每股收益'])
                        if '现金分红-股息率' in row and pd.notna(row['现金分红-股息率']):
                            enriched_data['dividend_yield'] = float(row['现金分红-股息率'])
                        self.logger.info(f"{stock_code} 发现分红送配数据")
            except Exception as e:
                self.logger.warning(f"获取 {stock_code} 分红送配数据失败: {e}")

            # 优先级 3: 涨停原因数据
            try:
                from craw import stock_limitup_reason
                # --- 修正函数调用和逻辑 ---
                reason_df = stock_limitup_reason.stock_limitup_reason(date=today_str.replace('-', ''))
                if not reason_df.empty:
                    stock_reason = reason_df[reason_df['代码'] == stock_code.replace('sh', '').replace('sz', '')]
                    if not stock_reason.empty:
                        reason_text = stock_reason.iloc[0]['原因']
                        enriched_data['limit_up_reason'] = reason_text
                        self.logger.info(f"{stock_code} 发现涨停原因数据")
            except Exception as e:
                self.logger.warning(f"获取 {stock_code} 涨停原因失败: {e}")

            # 优先级 4: 操盘必读 (获取名称和板块)
            try:
                from craw import stock_cpbd_em
                # 操盘必读需要不带市场前缀的代码
                code_no_prefix = stock_code.replace('sh', '').replace('sz', '')
                cpbd_df = stock_cpbd_em.stock_cpbd_em(symbol=code_no_prefix)
                if cpbd_df is not None and not cpbd_df.empty:
                    # 操盘必读返回的是单行DataFrame
                    stock_info = cpbd_df.iloc[0]
                    if 'SECURITY_NAME_ABBR' in stock_info and pd.notna(stock_info['SECURITY_NAME_ABBR']):
                        enriched_data['stock_name'] = stock_info['SECURITY_NAME_ABBR']
                    if 'BOARD_NAME' in stock_info and pd.notna(stock_info['BOARD_NAME']):
                        enriched_data['sector'] = stock_info['BOARD_NAME']
                    self.logger.info(f"{stock_code} 发现操盘必读数据 (名称/板块)")
            except Exception as e:
                self.logger.warning(f"获取 {stock_code} 操盘必读数据失败: {e}")

            # 计算健康分数
            health_score = self._calculate_health_score(enriched_data, stock_code)
            if health_score is not None:
                enriched_data['health_score'] = health_score

            # 更新到数据库
            if enriched_data:
                success = self.pool_manager.update_stock_profile(stock_code, enriched_data)
                if success:
                    self.logger.info(f"成功丰富 {stock_code} 数据，更新了 {len(enriched_data)} 个字段")
                    return True
                else:
                    self.logger.error(f"更新 {stock_code} 数据到数据库失败")
                    return False
            else:
                self.logger.info(f"{stock_code} 未发现新的丰富数据")
                return True

        except Exception as e:
            self.logger.error(f"丰富 {stock_code} 数据时出错: {e}")
            return False

    def run_enrichment_for_pool(self, limit: Optional[int] = None) -> Dict[str, int]:
        """为核心池中的所有股票丰富数据"""
        self.logger.info("开始为核心观察池丰富数据")
        
        core_pool = self.pool_manager.get_core_pool(limit=limit)
        results = {'success': 0, 'failed': 0, 'total': len(core_pool)}
        
        for i, stock in enumerate(core_pool, 1):
            stock_code = stock['stock_code']
            self.logger.info(f"处理进度 [{i}/{len(core_pool)}]: {stock_code}")
            
            if self.enrich_single_stock(stock_code):
                results['success'] += 1
            else:
                results['failed'] += 1
        
        self.logger.info(f"数据丰富完成: 成功 {results['success']}, 失败 {results['failed']}")
        return results

    def _calculate_health_score(self, enriched_data: Dict[str, Any], stock_code: str) -> Optional[float]:
        """
        计算股票健康分数 (0.0 - 1.0)
        
        评分规则：
        - 基础分数: 0.5
        - EPS > 0.5: +0.15, EPS > 0.2: +0.1, EPS > 0: +0.05, EPS <= 0: -0.1
        - 股息率 > 3%: +0.1, 股息率 > 1%: +0.05
        - 近期有龙虎榜机构净买入: +0.2, 一般龙虎榜: +0.05
        - 涨停原因为业绩利好: +0.1, 炒作概念: -0.05
        - 技术面强势: +0.1, 技术面弱势: -0.1
        """
        try:
            score = 0.5  # 基础分数
            
            # 基于EPS调整 (权重: 0.3)
            if 'eps' in enriched_data and enriched_data['eps'] is not None:
                eps = enriched_data['eps']
                if eps > 0.5:
                    score += 0.15
                    self.logger.debug(f"{stock_code} EPS优秀 (+0.15): {eps}")
                elif eps > 0.2:
                    score += 0.1
                    self.logger.debug(f"{stock_code} EPS良好 (+0.1): {eps}")
                elif eps > 0:
                    score += 0.05
                    self.logger.debug(f"{stock_code} EPS正值 (+0.05): {eps}")
                else:
                    score -= 0.1
                    self.logger.debug(f"{stock_code} EPS亏损 (-0.1): {eps}")
            
            # 基于股息率调整 (权重: 0.2)
            if 'dividend_yield' in enriched_data and enriched_data['dividend_yield'] is not None:
                dividend_yield = enriched_data['dividend_yield']
                if dividend_yield > 3:
                    score += 0.1
                    self.logger.debug(f"{stock_code} 高股息率 (+0.1): {dividend_yield}%")
                elif dividend_yield > 1:
                    score += 0.05
                    self.logger.debug(f"{stock_code} 中等股息率 (+0.05): {dividend_yield}%")
            
            # 基于龙虎榜数据调整 (权重: 0.3)
            if 'lhb_history' in enriched_data:
                try:
                    lhb_data = json.loads(enriched_data['lhb_history']) if isinstance(enriched_data['lhb_history'], str) else enriched_data['lhb_history']
                    if lhb_data:
                        # 分析龙虎榜数据质量
                        net_buy_amount = 0
                        for record in lhb_data:
                            if '机构' in str(record.get('营业部名称', '')):
                                net_buy_amount += record.get('净买额', 0)
                        
                        if net_buy_amount > 10000000:  # 机构净买入超过1000万
                            score += 0.2
                            self.logger.debug(f"{stock_code} 机构大额净买入 (+0.2): {net_buy_amount/10000:.0f}万")
                        elif net_buy_amount > 0:
                            score += 0.1
                            self.logger.debug(f"{stock_code} 机构净买入 (+0.1): {net_buy_amount/10000:.0f}万")
                        else:
                            score += 0.05  # 至少有资金关注
                            self.logger.debug(f"{stock_code} 龙虎榜关注 (+0.05)")
                except:
                    score += 0.05  # 解析失败但有龙虎榜数据
            
            # 基于涨停原因调整 (权重: 0.2)
            if 'limit_up_reason' in enriched_data and enriched_data['limit_up_reason']:
                reason = str(enriched_data['limit_up_reason']).lower()
                if any(keyword in reason for keyword in ['业绩', '利好', '重组', '合作', '订单', '中标']):
                    score += 0.1
                    self.logger.debug(f"{stock_code} 基本面利好 (+0.1): {reason[:20]}")
                elif any(keyword in reason for keyword in ['炒作', '概念', '跟风', '传闻']):
                    score -= 0.05
                    self.logger.debug(f"{stock_code} 概念炒作 (-0.05): {reason[:20]}")
            
            # 技术面评估 (基于现有数据)
            try:
                from data_handler import get_full_data_with_indicators
                df = get_full_data_with_indicators(stock_code)
                if df is not None and len(df) > 20:
                    latest = df.iloc[-1]
                    prev = df.iloc[-20]  # 20天前
                    
                    # 价格趋势
                    price_trend = (latest['close'] - prev['close']) / prev['close']
                    if price_trend > 0.1:  # 20天涨幅超过10%
                        score += 0.05
                        self.logger.debug(f"{stock_code} 价格强势 (+0.05): {price_trend:.2%}")
                    elif price_trend < -0.1:  # 20天跌幅超过10%
                        score -= 0.05
                        self.logger.debug(f"{stock_code} 价格弱势 (-0.05): {price_trend:.2%}")
                    
                    # RSI指标
                    if 'rsi6' in latest and pd.notna(latest['rsi6']):
                        rsi = latest['rsi6']
                        if 30 < rsi < 70:  # RSI在合理区间
                            score += 0.02
                        elif rsi > 80:  # 超买
                            score -= 0.03
                        elif rsi < 20:  # 超卖但可能反弹
                            score += 0.01
            except Exception as e:
                self.logger.debug(f"技术面评估失败 {stock_code}: {e}")
            
            # 限制在合理范围内
            final_score = max(0.0, min(1.0, score))
            self.logger.info(f"{stock_code} 健康分数: {final_score:.3f} (基础0.5 -> 最终{final_score:.3f})")
            
            return final_score
            
        except Exception as e:
            self.logger.error(f"计算 {stock_code} 健康分数失败: {e}")
            return None

    def get_enrichment_summary(self) -> Dict[str, Any]:
        """获取数据丰富情况摘要"""
        try:
            core_pool = self.pool_manager.get_core_pool()
            
            summary = {
                'total_stocks': len(core_pool),
                'enriched_stocks': 0,
                'health_score_available': 0,
                'lhb_data_available': 0,
                'financial_data_available': 0,
                'limit_up_reason_available': 0,
                'avg_health_score': 0.0
            }
            
            health_scores = []
            
            for stock in core_pool:
                has_enriched_data = False
                
                if stock.get('health_score') is not None:
                    summary['health_score_available'] += 1
                    health_scores.append(stock['health_score'])
                    has_enriched_data = True
                
                if stock.get('lhb_history'):
                    summary['lhb_data_available'] += 1
                    has_enriched_data = True
                
                if stock.get('eps') is not None or stock.get('dividend_yield') is not None:
                    summary['financial_data_available'] += 1
                    has_enriched_data = True
                
                if stock.get('limit_up_reason'):
                    summary['limit_up_reason_available'] += 1
                    has_enriched_data = True
                
                if has_enriched_data:
                    summary['enriched_stocks'] += 1
            
            if health_scores:
                summary['avg_health_score'] = sum(health_scores) / len(health_scores)
            
            return summary
            
        except Exception as e:
            self.logger.error(f"获取丰富情况摘要失败: {e}")
            return {}


def main():
    """测试函数"""
    import logging
    
    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # 创建数据丰富器
    enricher = DataEnricher()
    
    # 测试单只股票数据丰富
    test_stock = "sz300290"
    print(f"测试丰富股票: {test_stock}")
    success = enricher.enrich_single_stock(test_stock)
    print(f"丰富结果: {'成功' if success else '失败'}")
    
    # 获取丰富情况摘要
    summary = enricher.get_enrichment_summary()
    print(f"丰富情况摘要: {summary}")


if __name__ == "__main__":
    main()