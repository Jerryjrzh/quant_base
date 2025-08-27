"""
增强版交易建议模块
将 get_trading_advice_enhanced.py 的核心逻辑封装为可调用的函数
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
from datetime import datetime
#import backtester

def generate_enhanced_advice(df: pd.DataFrame, stock_code: str) -> Dict[str, Any]:
    """
    生成增强版交易建议
    
    Args:
        df: 包含所有指标的Pandas DataFrame
        stock_code: 股票代码
        
    Returns:
        包含增强版建议的字典
    【已优化】现在只依赖传入的df进行计算，不再反向调用backtester
    """
    try:
        # 使用简化的技术分析
        # 不再调用 backtester，直接使用传入的df进行简化分析
        return generate_simplified_advice(df, stock_code)
        
    except Exception as e:
        return {
            'enhanced_action': 'ERROR',
            'confidence_score': 0.0,
            'reasoning': [f"增强分析失败: {str(e)}"],
            'error': str(e)
        }

def generate_simplified_advice(df: pd.DataFrame, stock_code: str) -> Dict[str, Any]:
    """
    生成简化版增强建议（当深度分析不可用时）
    """
    try:
        if len(df) == 0:
            return {
                'enhanced_action': 'ERROR',
                'confidence_score': 0.0,
                'reasoning': ['数据不足'],
                'error': '数据不足'
            }
        
        latest = df.iloc[-1]
        current_price = float(latest.get('close', 0))
        
        # 基于技术指标的简化分析
        confidence = 0.5
        reasoning = []
        action = 'WATCH'
        
        # MA分析
        ma13 = latest.get('ma13')
        ma45 = latest.get('ma45')
        if not pd.isna(ma13) and not pd.isna(ma45):
            if ma13 > ma45:
                reasoning.append("短期均线位于长期均线之上，趋势向好")
                confidence += 0.15
                action = 'BUY'
            else:
                reasoning.append("短期均线位于长期均线之下，趋势偏弱")
                confidence -= 0.1
        
        # RSI分析
        rsi6 = latest.get('rsi6')
        if not pd.isna(rsi6):
            if rsi6 < 30:
                reasoning.append(f"RSI({rsi6:.1f})处于超卖区域，存在反弹机会")
                confidence += 0.2
                action = 'BUY'
            elif rsi6 > 70:
                reasoning.append(f"RSI({rsi6:.1f})处于超买区域，注意回调风险")
                confidence -= 0.15
                if action == 'BUY':
                    action = 'HOLD'
        
        # MACD分析
        dif = latest.get('dif')
        dea = latest.get('dea')
        if not pd.isna(dif) and not pd.isna(dea):
            if dif > dea:
                reasoning.append("MACD金叉，动量向好")
                confidence += 0.1
            else:
                reasoning.append("MACD死叉，动量偏弱")
                confidence -= 0.05
        
        # 确定最终建议
        confidence = max(0.1, min(0.95, confidence))
        enhanced_action = determine_enhanced_action(action, confidence, {})
        
        # 计算简化的价格目标
        price_targets = {
            'current_price': current_price,
            'target_price': current_price * 1.1,
            'stop_loss_price': current_price * 0.95
        }
        
        if len(df) >= 30:
            recent_data = df.tail(30)
            price_targets['resistance_level'] = float(recent_data['high'].max())
            price_targets['support_level'] = float(recent_data['low'].min())
        
        return {
            'enhanced_action': enhanced_action,
            'confidence_score': confidence,
            'reasoning': reasoning,
            'price_targets': price_targets,
            'backtest_summary': {},
            'risk_metrics': {},
            'technical_signals': analyze_technical_signals(df),
            'simplified_mode': True
        }
        
    except Exception as e:
        return {
            'enhanced_action': 'ERROR',
            'confidence_score': 0.0,
            'reasoning': [f"简化分析失败: {str(e)}"],
            'error': str(e)
        }

def calculate_enhanced_confidence(backtest_analysis: Dict, risk_assessment: Dict, 
                                df: pd.DataFrame) -> float:
    """
    基于回测和风险分析计算增强版置信度
    """
    confidence = 0.5  # 基础置信度
    
    # 回测表现加分
    if backtest_analysis:
        best_add_score = backtest_analysis.get('best_add_score', 0)
        best_sell_score = backtest_analysis.get('best_sell_score', 0)
        
        # 回测评分越高，置信度越高
        if best_add_score > 0:
            confidence += min(0.2, best_add_score / 100)
        if best_sell_score > 0:
            confidence += min(0.2, best_sell_score / 100)
    
    # 风险评估调整
    if risk_assessment:
        risk_level = risk_assessment.get('risk_level', 'MEDIUM')
        volatility = risk_assessment.get('volatility', 0.3)
        
        if risk_level == 'LOW':
            confidence += 0.1
        elif risk_level == 'HIGH':
            confidence -= 0.1
        
        # 波动率过高降低置信度
        if volatility > 0.5:
            confidence -= 0.15
    
    # 技术指标确认
    if len(df) > 0:
        latest = df.iloc[-1]
        
        # 多个指标共振加分
        signals_count = 0
        
        # MA趋势确认
        if not pd.isna(latest.get('ma13')) and not pd.isna(latest.get('ma45')):
            if latest['ma13'] > latest['ma45']:
                signals_count += 1
        
        # RSI位置确认
        rsi6 = latest.get('rsi6', 50)
        if not pd.isna(rsi6):
            if 30 < rsi6 < 70:  # 正常区间
                signals_count += 1
            elif rsi6 < 30:  # 超卖
                signals_count += 2
        
        # MACD确认
        dif = latest.get('dif', 0)
        dea = latest.get('dea', 0)
        if not pd.isna(dif) and not pd.isna(dea) and dif > dea:
            signals_count += 1
        
        # 信号数量调整置信度
        confidence += min(0.15, signals_count * 0.03)
    
    return max(0.1, min(0.95, confidence))

def determine_enhanced_action(base_action: str, confidence: float, 
                            backtest_analysis: Dict) -> str:
    """
    基于置信度和回测结果确定增强版操作建议
    """
    if confidence < 0.3:
        return 'AVOID'
    elif confidence < 0.5:
        return 'WATCH'
    elif confidence < 0.7:
        if base_action in ['BUY', 'STRONG_BUY']:
            return 'BUY'
        else:
            return 'HOLD'
    elif confidence < 0.85:
        if base_action in ['BUY', 'STRONG_BUY']:
            return 'STRONG_BUY'
        else:
            return 'BUY'
    else:
        return 'STRONG_BUY'

def generate_reasoning(trading_advice: Dict, backtest_analysis: Dict, 
                      risk_assessment: Dict, df: pd.DataFrame) -> list:
    """
    生成推理逻辑列表
    """
    reasoning = []
    
    # 基础建议原因
    if trading_advice.get('reasons'):
        reasoning.extend(trading_advice['reasons'])
    
    # 回测分析支持
    if backtest_analysis:
        best_add_coeff = backtest_analysis.get('best_add_coefficient')
        best_sell_coeff = backtest_analysis.get('best_sell_coefficient')
        
        if best_add_coeff:
            reasoning.append(f"历史回测显示最优补仓系数为{best_add_coeff}")
        if best_sell_coeff:
            reasoning.append(f"历史回测显示最优卖出系数为{best_sell_coeff}")
    
    # 风险评估
    if risk_assessment:
        risk_level = risk_assessment.get('risk_level', 'MEDIUM')
        reasoning.append(f"风险等级评估为{risk_level}")
    
    # 技术指标分析
    if len(df) > 0:
        latest = df.iloc[-1]
        
        # 趋势分析
        ma13 = latest.get('ma13')
        ma45 = latest.get('ma45')
        if not pd.isna(ma13) and not pd.isna(ma45):
            if ma13 > ma45:
                reasoning.append("短期均线位于长期均线之上，趋势向好")
            else:
                reasoning.append("短期均线位于长期均线之下，趋势偏弱")
        
        # RSI分析
        rsi6 = latest.get('rsi6')
        if not pd.isna(rsi6):
            if rsi6 < 30:
                reasoning.append(f"RSI({rsi6:.1f})处于超卖区域，存在反弹机会")
            elif rsi6 > 70:
                reasoning.append(f"RSI({rsi6:.1f})处于超买区域，注意回调风险")
    
    return reasoning

def calculate_price_targets(current_price: float, backtest_analysis: Dict, 
                          df: pd.DataFrame) -> Dict[str, float]:
    """
    计算价格目标
    """
    if current_price <= 0:
        return {}
    
    targets = {
        'current_price': current_price
    }
    
    # 基于回测分析的目标价
    if backtest_analysis:
        best_sell_coeff = backtest_analysis.get('best_sell_coefficient', 1.1)
        if isinstance(best_sell_coeff, (int, float)) and best_sell_coeff > 1:
            targets['target_price'] = current_price * best_sell_coeff
        
        best_add_coeff = backtest_analysis.get('best_add_coefficient', 0.95)
        if isinstance(best_add_coeff, (int, float)) and best_add_coeff < 1:
            targets['add_position_price'] = current_price * best_add_coeff
    
    # 基于技术分析的支撑阻力
    if len(df) >= 30:
        recent_data = df.tail(30)
        targets['resistance_level'] = float(recent_data['high'].max())
        targets['support_level'] = float(recent_data['low'].min())
    
    # 默认止损价（5%）
    targets['stop_loss_price'] = current_price * 0.95
    
    return targets

def extract_backtest_summary(backtest_analysis: Dict) -> Dict[str, Any]:
    """
    提取回测摘要信息
    """
    if not backtest_analysis:
        return {}
    
    return {
        'best_add_coefficient': backtest_analysis.get('best_add_coefficient'),
        'best_add_score': backtest_analysis.get('best_add_score'),
        'best_sell_coefficient': backtest_analysis.get('best_sell_coefficient'),
        'best_sell_score': backtest_analysis.get('best_sell_score'),
        'has_add_analysis': bool(backtest_analysis.get('add_coefficient_analysis')),
        'has_sell_analysis': bool(backtest_analysis.get('sell_coefficient_analysis'))
    }

def extract_risk_metrics(risk_assessment: Dict) -> Dict[str, Any]:
    """
    提取风险指标
    """
    if not risk_assessment:
        return {}
    
    return {
        'risk_level': risk_assessment.get('risk_level'),
        'volatility': risk_assessment.get('volatility'),
        'max_drawdown': risk_assessment.get('max_drawdown'),
        'sharpe_ratio': risk_assessment.get('sharpe_ratio')
    }

def analyze_technical_signals(df: pd.DataFrame) -> Dict[str, Any]:
    """
    分析技术信号
    """
    if len(df) == 0:
        return {}
    
    latest = df.iloc[-1]
    signals = {}
    
    # 趋势信号
    ma13 = latest.get('ma13')
    ma45 = latest.get('ma45')
    if not pd.isna(ma13) and not pd.isna(ma45):
        signals['trend_signal'] = 'BULLISH' if ma13 > ma45 else 'BEARISH'
    
    # 动量信号
    rsi6 = latest.get('rsi6')
    if not pd.isna(rsi6):
        if rsi6 < 30:
            signals['momentum_signal'] = 'OVERSOLD'
        elif rsi6 > 70:
            signals['momentum_signal'] = 'OVERBOUGHT'
        else:
            signals['momentum_signal'] = 'NEUTRAL'
    
    # MACD信号
    dif = latest.get('dif')
    dea = latest.get('dea')
    if not pd.isna(dif) and not pd.isna(dea):
        signals['macd_signal'] = 'BULLISH' if dif > dea else 'BEARISH'
    
    return signals
