#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
持仓监控脚本 - 基于 Walk-Forward 验证的每日评估体系
功能:
1. 读取 portfolio.json 持仓列表
2. 引入中证1000连续 (IM) 评估市场整体风险
3. 对每只持仓执行 confluence_scorer + pattern_recognizer 诊断
4. 动态 TP/SL 调整建议
5. 输出持仓监控报告

用法:
    python3 position_monitor.py              # 扫描全部持仓
    python_monitor.py --stock sh601872       # 扫描单只
"""

import os
import sys
import json
import argparse
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import data_loader
from confluence_scorer import confluence_scorer
from pattern_recognizer import pattern_recognizer
from data_handler import get_full_data_with_indicators
import backtester

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
PORTFOLIO_FILE = os.path.join(BACKEND_DIR, '..', 'data', 'portfolio', 'portfolio.json')

# 四大宽基指数现货路径 (用于市场风险莫尔斯评估)
INDEX_PATHS = {
    'IH': os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc/sh/lday/sh000016.day"),
    'IF': os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc/sh/lday/sh000300.day"),
    'IC': os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc/sh/lday/sh000905.day"),
    'IM': os.path.expanduser("~/.local/share/tdxcfv/drive_c/tc/vipdoc/sh/lday/sh000852.day"),
}


def _to_morse_char(open_p, high, low, close, vol, vol_ma20) -> str:
    """将单根K线转化为3位莫尔斯电码"""
    pct = (close - open_p) / (open_p + 1e-9)
    if pct > 0.03:     body = 'U'
    elif pct > 0.005:  body = 'u'
    elif pct < -0.03:  body = 'D'
    elif pct < -0.005: body = 'd'
    else:              body = 'X'

    upper_shadow = high - max(close, open_p)
    lower_shadow = min(close, open_p) - low
    body_size = abs(close - open_p)

    if lower_shadow > body_size * 1.2 and lower_shadow > upper_shadow:    shadow = 'B'
    elif upper_shadow > body_size * 1.2 and upper_shadow > lower_shadow:  shadow = 'T'
    elif upper_shadow < body_size * 0.1 and lower_shadow < body_size * 0.1: shadow = 'N'
    else:                                                                 shadow = 'S'

    vol_ratio = vol / (vol_ma20 + 1e-9)
    if vol_ratio > 1.8:   volume = 'H'
    elif vol_ratio < 0.6: volume = 'L'
    else:                 volume = 'A'

    return f"{body}{shadow}{volume}"


def assess_market_risk() -> Dict:
    """
    基于四大宽基指数 (IH/IF/IC/IM) 的莫尔斯电码评估市场整体风险
    Returns:
        dict: {
            'morse_chain': str,      # 完整莫尔斯链
            'risk_level': str,        # 风险等级描述
            'im_trend': str,          # IM 趋势判断
            'im_phase': str,          # IM 市场阶段
            'im_score': float,        # IM confluence 评分
            'index_details': dict,    # 各指数详情
        }
    """
    index_dfs = {}
    for name, path in INDEX_PATHS.items():
        if os.path.exists(path):
            df = data_loader.get_daily_data(path)
            if df is not None and len(df) > 30:
                index_dfs[name] = df

    if not index_dfs:
        return {
            'morse_chain': 'NO_DATA',
            'risk_level': '数据缺失',
            'im_trend': '', 'im_phase': '', 'im_score': 0,
            'index_details': {},
        }

    # 构建当日莫尔斯链
    morse_parts = []
    index_details = {}

    for name in ['IH', 'IF', 'IC', 'IM']:
        df = index_dfs.get(name)
        if df is None:
            continue
        loc = len(df) - 1
        if loc < 20:
            continue
        row = df.iloc[loc]
        vol_ma = df['volume'].iloc[max(0, loc-20):loc].mean()
        char = _to_morse_char(
            row['open'], row['high'], row['low'], row['close'],
            row['volume'], vol_ma
        )
        morse_parts.append(f"{name}[{char}]")
        index_details[name] = {
            'close': round(float(row['close']), 2),
            'morse': char,
            'date': str(df.index[loc].date()),
        }

    morse_chain = "-".join(morse_parts)

    # 风险等级判定 (复用 morse_universe_miner 逻辑)
    risk_level = _parse_market_risk(morse_chain)

    # IM 专项分析 (中证1000连续)
    im_analysis = _analyze_index_deep(index_dfs.get('IM'), 'IM')

    return {
        'morse_chain': morse_chain,
        'risk_level': risk_level,
        'im_trend': im_analysis.get('trend', ''),
        'im_phase': im_analysis.get('phase', ''),
        'im_score': im_analysis.get('score', 0),
        'im_close': im_analysis.get('close', 0),
        'index_details': index_details,
    }


def _parse_market_risk(morse_chain: str) -> str:
    """根据莫尔斯链判定市场风险等级"""
    if not isinstance(morse_chain, str) or 'NO_DATA' in morse_chain:
        return '数据缺失'

    if 'IC[D' in morse_chain or 'IM[D' in morse_chain or \
       morse_chain.count('[d') + morse_chain.count('[D') >= 4:
        return '高危 - 建议减仓或空仓'

    if ('IH[U' in morse_chain or 'IH[u' in morse_chain) and \
       ('IM[d' in morse_chain or 'IM[D' in morse_chain):
        return '分化 - 权重护盘中小盘承压，缩减仓位'

    if 'IC[u' in morse_chain or 'IM[u' in morse_chain or \
       'IM[U' in morse_chain or 'IM[XL' in morse_chain:
        return '安全 - 中小盘活跃，可正常操作'

    return '震荡 - 常规应对'


def _analyze_index_deep(df: Optional[pd.DataFrame], name: str) -> Dict:
    """对指数做 confluence_scorer 深度分析"""
    if df is None or len(df) < 100:
        return {}

    try:
        from data_handler import calculate_all_indicators
        df = calculate_all_indicators(df.copy(), f'sh000852')

        idx = len(df) - 1
        result = confluence_scorer.calculate_confluence_score(df, idx)
        phase_result = confluence_scorer.detect_market_phase(df, idx)

        close = float(df.iloc[idx]['close'])
        ma20 = float(df['close'].iloc[max(0, idx-20):idx+1].mean())
        ma60 = float(df['close'].iloc[max(0, idx-60):idx+1].mean()) if idx >= 60 else close

        if close > ma20 and ma20 > ma60:
            trend = '多头排列'
        elif close < ma20 and ma20 < ma60:
            trend = '空头排列'
        else:
            trend = '震荡整理'

        return {
            'score': round(result.get('total_score', 0), 1),
            'phase': result.get('market_phase', 'unknown'),
            'confidence': round(result.get('confidence', 0), 3),
            'trend': trend,
            'close': round(close, 2),
        }
    except Exception as e:
        logger.warning(f"指数 {name} 深度分析异常: {e}")
        return {}


def evaluate_position(stock_code: str, purchase_price: float,
                      purchase_date: str, quantity: int,
                      note: str = '') -> Dict:
    """
    对单只持仓执行完整诊断:
    1. 获取最新数据 + 指标
    2. confluence_scorer + pattern_recognizer 评估
    3. V4.4 动态定价生成 TP/SL
    4. 动态调整建议

    Returns:
        dict: 诊断结果
    """
    try:
        df = get_full_data_with_indicators(stock_code)
        if df is None or len(df) < 100:
            return {'stock_code': stock_code, 'error': '数据不足(< 100天)'}

        idx = len(df) - 1
        close = float(df.iloc[idx]['close'])
        profit = (close - purchase_price) / purchase_price
        holding_days = (datetime.now() - datetime.strptime(purchase_date, '%Y-%m-%d')).days

        # 1. Confluence 评分
        result = confluence_scorer.calculate_confluence_score(df, idx)
        score = result.get('total_score', 0)
        phase = result.get('market_phase', 'unknown')
        conf = result.get('confidence', 0)

        # 2. 形态识别
        pattern = pattern_recognizer.recognize_pattern(df, idx)
        pat = pattern.get('best_pattern')
        has_pattern = pattern.get('has_pattern', False)

        # 3. 风险等级
        if score >= 70 and phase in ['accumulation', 'markup'] and conf >= 0.6:
            risk = '低'
        elif score < 55 or phase in ['distribution', 'decline']:
            risk = '高'
        else:
            risk = '中'

        # 4. V4.4 动态定价 (获取原始 TP/SL)
        v44_advice = None
        orig_tp = None
        orig_sl = None
        try:
            advice = backtester._generate_forward_advice_v4(df, stock_code)
            if advice and advice.get('action') != 'ERROR':
                v44_advice = advice
                orig_tp = advice.get('target_price')
                orig_sl = advice.get('stop_price')
        except Exception:
            pass

        # 5. 动态 TP/SL 调整
        adj_tp = orig_tp
        adj_sl = orig_sl
        reasons = []

        if orig_tp and orig_sl:
            if phase in ['distribution', 'decline']:
                new_sl = purchase_price * 1.01
                if new_sl > adj_sl:
                    adj_sl = new_sl
                    reasons.append(f'phase={phase} -> 止损上移至保本+1%')

            if phase == 'distribution':
                adj_tp = purchase_price + (orig_tp - purchase_price) * 0.6
                reasons.append('distribution -> 止盈收紧至60%')
            elif score < 55:
                adj_tp = purchase_price + (orig_tp - purchase_price) * 0.7
                reasons.append(f'score={score:.0f}<55 -> 止盈收紧至70%')

            if phase == 'markup' and score >= 80 and profit >= 0.05:
                adj_tp = orig_tp
                reasons.append('markup+A级+盈利>=5% -> 维持原始止盈')

        # 6. 均线位置
        ma13 = float(df['close'].iloc[max(0, idx-13):idx+1].mean()) if idx >= 13 else close
        ma20 = float(df['close'].iloc[max(0, idx-20):idx+1].mean()) if idx >= 20 else close

        # 7. 操作建议
        action = _generate_action(
            profit, risk, phase, score, close,
            adj_tp, adj_sl, purchase_price, holding_days
        )

        return {
            'stock_code': stock_code,
            'note': note,
            'purchase_price': purchase_price,
            'quantity': quantity,
            'purchase_date': purchase_date,
            'holding_days': holding_days,
            'close': round(close, 2),
            'profit': round(profit * 100, 2),
            'profit_amount': round((close - purchase_price) * quantity, 2),
            'score': round(score, 1),
            'phase': phase,
            'confidence': round(conf, 3),
            'pattern': pat,
            'has_pattern': has_pattern,
            'risk': risk,
            'ma13': round(ma13, 2),
            'ma20': round(ma20, 2),
            'vs_ma13': round((close - ma13) / ma13 * 100, 2),
            'orig_tp': round(orig_tp, 2) if orig_tp else None,
            'orig_sl': round(orig_sl, 2) if orig_sl else None,
            'adj_tp': round(adj_tp, 2) if adj_tp else None,
            'adj_sl': round(adj_sl, 2) if adj_sl else None,
            'tp_from_close': round((adj_tp - close) / close * 100, 2) if adj_tp else None,
            'sl_from_close': round((adj_sl - close) / close * 100, 2) if adj_sl else None,
            'reasons': '; '.join(reasons) if reasons else '',
            'action': action,
            'v44_grade': v44_advice.get('quality_grade', '') if v44_advice else '',
            'v44_trend': v44_advice.get('feature_trend', '') if v44_advice else '',
        }

    except Exception as e:
        return {'stock_code': stock_code, 'error': f'分析异常: {e}'}


def _generate_action(profit: float, risk: str, phase: str, score: float,
                     close: float, adj_tp: float, adj_sl: float,
                     purchase_price: float, holding_days: int) -> str:
    """生成操作建议"""
    # 硬止损
    if adj_sl and close <= adj_sl:
        return '止损出局 - 已触止损线'

    # 止盈
    if adj_tp and close >= adj_tp:
        return '止盈出局 - 已触止盈线'

    # 高风险 + 亏损
    if risk == '高' and profit < -0.05:
        return '建议止损 - 高风险且亏损>5%'

    # 高风险 + 微利
    if risk == '高' and profit < 0.02 and holding_days > 5:
        return '建议减仓 - 高风险且持仓>5天无明显收益'

    # 中风险 + 亏损扩大
    if risk == '中' and profit < -0.08:
        return '建议减仓 - 中风险且亏损>8%'

    # 低风险 + 上升趋势
    if risk == '低' and phase == 'markup' and score >= 70:
        if profit > 0.05:
            return '持有 - 趋势良好，注意动态止盈'
        return '持有 - 趋势良好，耐心等待'

    # 中风险 + 有利润
    if risk == '中' and profit > 0:
        return '持有观察 - 收紧止损保护利润'

    # 持仓过久
    if holding_days > 15 and abs(profit) < 0.03:
        return '建议减仓 - 持仓>15天无明显方向'

    return '持有观察'


def load_portfolio() -> List[Dict]:
    """读取持仓列表"""
    try:
        with open(PORTFOLIO_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        logger.error(f"读取持仓文件失败: {e}")
        return []


def run_monitor(stock_filter: str = None):
    """
    执行持仓监控扫描

    Args:
        stock_filter: 可选，只扫描指定股票代码
    """
    start_time = datetime.now()
    logger.info("=" * 60)
    logger.info(f"持仓监控扫描启动 - {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # 1. 市场风险评估 (IM 中证1000连续)
    logger.info(">>> 评估市场整体风险 (IH/IF/IC/IM)...")
    market = assess_market_risk()
    _print_market_report(market)

    # 2. 读取持仓列表
    portfolio = load_portfolio()
    if not portfolio:
        logger.error("持仓列表为空，退出")
        return

    if stock_filter:
        portfolio = [p for p in portfolio if p['stock_code'] == stock_filter]
        if not portfolio:
            logger.error(f"未找到持仓: {stock_filter}")
            return

    logger.info(f">>> 共 {len(portfolio)} 只持仓待扫描")

    # 3. 逐只诊断
    results = []
    for i, pos in enumerate(portfolio, 1):
        stock_code = pos['stock_code']
        logger.info(f"[{i}/{len(portfolio)}] 诊断 {stock_code} ({pos.get('note', '')})")

        result = evaluate_position(
            stock_code=stock_code,
            purchase_price=pos['purchase_price'],
            purchase_date=pos['purchase_date'],
            quantity=pos['quantity'],
            note=pos.get('note', ''),
        )
        results.append(result)

    # 4. 输出报告
    _print_position_report(results, market)

    # 5. 保存结果
    _save_report(results, market, start_time)

    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info(f"扫描完成，耗时 {elapsed:.1f} 秒")


def _print_market_report(market: Dict):
    """打印市场风险报告"""
    print("\n" + "=" * 60)
    print("  市场风险评估 (四大宽基指数)")
    print("=" * 60)
    print(f"  莫尔斯链: {market['morse_chain']}")
    print(f"  风险等级: {market['risk_level']}")

    if market.get('im_trend'):
        print(f"\n  IM 中证1000连续:")
        print(f"    收盘: {market.get('im_close', 'N/A')}")
        print(f"    趋势: {market['im_trend']}")
        print(f"    阶段: {market['im_phase']}")
        print(f"    评分: {market['im_score']}")

    details = market.get('index_details', {})
    if details:
        print(f"\n  指数详情:")
        for name in ['IH', 'IF', 'IC', 'IM']:
            d = details.get(name, {})
            if d:
                print(f"    {name}: {d.get('close', 'N/A')} ({d.get('morse', '')}) [{d.get('date', '')}]")
    print()


def _print_position_report(results: List[Dict], market: Dict):
    """打印持仓诊断报告"""
    print("\n" + "=" * 70)
    print("  持仓诊断报告")
    print("=" * 70)

    # 汇总
    total_pnl = sum(r.get('profit_amount', 0) for r in results if 'error' not in r)
    profitable = sum(1 for r in results if r.get('profit', 0) > 0 and 'error' not in r)
    high_risk = sum(1 for r in results if r.get('risk') == '高' and 'error' not in r)
    action_needed = sum(1 for r in results if '止损' in r.get('action', '') or '减仓' in r.get('action', ''))

    print(f"  持仓数: {len(results)} | 盈利: {profitable} | "
          f"高风险: {high_risk} | 需操作: {action_needed}")
    print(f"  浮动盈亏: {total_pnl:+,.2f} 元")
    print()

    # 按风险排序: 高 > 中 > 低
    risk_order = {'高': 0, '中': 1, '低': 2}
    sorted_results = sorted(
        [r for r in results if 'error' not in r],
        key=lambda x: (risk_order.get(x.get('risk', '中'), 1), x.get('profit', 0))
    )
    error_results = [r for r in results if 'error' in r]

    for r in sorted_results:
        risk_icon = {'高': '[!!]', '中': '[! ]', '低': '[OK]'}
        icon = risk_icon.get(r.get('risk', '中'), '[??]')

        print(f"  {icon} {r['stock_code']} ({r.get('note', '')})")
        print(f"      成本={r['purchase_price']} 现价={r['close']} "
              f"盈亏={r['profit']:+.2f}% ({r['profit_amount']:+,.0f}元) "
              f"持仓{r['holding_days']}天")
        print(f"      评分={r['score']:.0f} 阶段={r['phase']} "
              f"置信={r['confidence']:.2f} 形态={r.get('pattern', '-')} "
              f"V4.4={r.get('v44_grade', '-')}")
        print(f"      MA13={r['ma13']} ({r['vs_ma13']:+.1f}%) MA20={r['ma20']}")

        if r.get('adj_tp') and r.get('adj_sl'):
            print(f"      止盈={r['adj_tp']} ({r['tp_from_close']:+.1f}%) "
                  f"止损={r['adj_sl']} ({r['sl_from_close']:+.1f}%)")

        if r.get('reasons'):
            print(f"      调整: {r['reasons']}")

        print(f"      >>> {r['action']}")
        print()

    for r in error_results:
        print(f"  [ERR] {r['stock_code']}: {r['error']}")
        print()


def _save_report(results: List[Dict], market: Dict, start_time: datetime):
    """保存扫描报告"""
    output_dir = os.path.join(BACKEND_DIR, '..', 'data', 'result')
    os.makedirs(output_dir, exist_ok=True)

    # 主报告 CSV
    report_rows = []
    for r in results:
        if 'error' in r:
            report_rows.append({
                'stock_code': r['stock_code'],
                'error': r['error'],
            })
        else:
            report_rows.append({
                'stock_code': r['stock_code'],
                'note': r.get('note', ''),
                'purchase_price': r['purchase_price'],
                'close': r['close'],
                'profit_pct': r['profit'],
                'profit_amount': r['profit_amount'],
                'holding_days': r['holding_days'],
                'score': r['score'],
                'phase': r['phase'],
                'confidence': r['confidence'],
                'pattern': r.get('pattern'),
                'risk': r['risk'],
                'ma13': r['ma13'],
                'ma20': r['ma20'],
                'vs_ma13': r['vs_ma13'],
                'orig_tp': r.get('orig_tp'),
                'orig_sl': r.get('orig_sl'),
                'adj_tp': r.get('adj_tp'),
                'adj_sl': r.get('adj_sl'),
                'tp_from_close': r.get('tp_from_close'),
                'sl_from_close': r.get('sl_from_close'),
                'reasons': r.get('reasons', ''),
                'action': r['action'],
                'v44_grade': r.get('v44_grade', ''),
                'v44_trend': r.get('v44_trend', ''),
            })

    df_report = pd.DataFrame(report_rows)
    csv_path = os.path.join(output_dir, 'position_monitor_report.csv')
    df_report.to_csv(csv_path, index=False, encoding='utf-8-sig', float_format='%.4f')
    logger.info(f"报告已保存: {csv_path}")

    # 市场风险快照
    market_snapshot = {
        'scan_time': start_time.strftime('%Y-%m-%d %H:%M:%S'),
        'market': market,
        'summary': {
            'total_positions': len(results),
            'total_pnl': sum(r.get('profit_amount', 0) for r in results if 'error' not in r),
            'profitable_count': sum(1 for r in results if r.get('profit', 0) > 0 and 'error' not in r),
            'high_risk_count': sum(1 for r in results if r.get('risk') == '高' and 'error' not in r),
            'action_needed_count': sum(1 for r in results if '止损' in r.get('action', '') or '减仓' in r.get('action', '')),
        },
    }
    json_path = os.path.join(output_dir, 'position_monitor_market.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(market_snapshot, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='持仓监控扫描')
    parser.add_argument('--stock', type=str, default=None,
                        help='只扫描指定股票代码 (如 sh601872)')
    args = parser.parse_args()
    run_monitor(stock_filter=args.stock)
