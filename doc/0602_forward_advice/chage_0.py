def _generate_forward_advice_v4(df: pd.DataFrame, stock_code: str) -> dict:
    """
    【V4.4 优化版】基于最新回测数据驱动的参数调优
    重点解决 distribution + 高位乖离 下的止盈命中率问题
    """
    try:
        latest_index = len(df) - 1
        current_price = float(df.iloc[latest_index]['close'])
        
        # 1. 调用 V4.0 评分系统获取最全面的分析结果
        confluence_result = confluence_scorer.calculate_confluence_score(df, latest_index)
        
        # 2. 调用形态识别器
        pattern_result = pattern_recognizer.recognize_pattern(df, latest_index)

        # 3. 初始化建议
        action = 'HOLD'
        reasons = []
        confidence = confluence_result['confidence']
        quality_grade = 'D'

        # ==========================================
        # 第一阶段：基础特征提取与评分逻辑
        # ==========================================
        market_phase = confluence_result.get('market_phase', 'unknown')
        trend_phase = market_phase
        
        atr = confluence_result.get('phase_analysis', {}).get('atr', current_price * 0.03)
        atr_pct = atr / current_price
        
        from data_handler import get_market_volatility_profile
        market_profile = get_market_volatility_profile(stock_code)
        board_limit = market_profile.get('limit', 0.10)
        board_type = market_profile.get('board_type', '10CM')
        
        is_high_vol = atr_pct > (board_limit * 0.35)

        reasons.append(f"宏观判断：当前处于 {market_phase.upper()} 阶段。")
        if market_phase in ['distribution', 'decline']:
            action = 'AVOID'
            reasons.append("风险提示：市场处于高风险或下跌阶段，建议规避。")
            confidence *= 0.7

        total_score = confluence_result.get('total_score', 0)
        if total_score >= 85:
            quality_grade = 'A'
            action = 'BUY' if action != 'AVOID' else action
            reasons.append(f"核心决策：融合评分 {total_score:.1f} (A级)，技术面高度共振。")
        elif total_score >= 70:
            quality_grade = 'B'
            action = 'BUY' if action != 'AVOID' else action
            reasons.append(f"核心决策：融合评分 {total_score:.1f} (B级)，技术面较为一致。")
        elif total_score >= 55:
            quality_grade = 'C'
            action = 'WATCH' if action != 'AVOID' else action
            reasons.append(f"核心决策：融合评分 {total_score:.1f} (C级)，建议保持观察。")
        else:
            quality_grade = 'D'
            action = 'AVOID'
            reasons.append(f"核心决策：融合评分 {total_score:.1f} (D级)，技术指标不一致，建议规避。")

        pattern_name = pattern_result.get('best_pattern', 'None') if pattern_result.get('has_pattern') else 'None'
        if pattern_result.get('has_pattern'):
            reasons.append(f"形态分析：识别到 {pattern_name} 形态 (置信度: {pattern_result['best_confidence']:.1%})。")
            confidence = (confidence + pattern_result['best_confidence']) / 2

        # ==========================================
        # 第二阶段：多维特征标签构造
        # ==========================================
        latest_ma60 = df.iloc[latest_index].get('ma60')
        bias_pct = (current_price - latest_ma60) / latest_ma60 if pd.notna(latest_ma60) and latest_ma60 != 0 else 0.0
            
        if bias_pct > 0.15:
            bias_tier = "高位极度乖离(>15%)"
        elif bias_pct > 0.05:
            bias_tier = "多头偏离(5%~15%)"
        elif bias_pct < -0.15:
            bias_tier = "深渊超跌(<-15%)"
        elif bias_pct < -0.05:
            bias_tier = "空头偏离(-15%~-5%)"
        else:
            bias_tier = "均值回归(±5%)"

        # ==========================================
        # 第三阶段：自适应网格定价（V4.4 核心优化）
        # ==========================================
        trend_risk_score = {'decline': 1.85, 'distribution': 0.85, 'accumulation': 0.55, 'markup': 0.9}.get(trend_phase, 1.0)
        
        price_targets = _calculate_price_targets(
            df=df, 
            current_price=current_price, 
            atr=atr, 
            trend_phase=trend_phase, 
            board_limit=board_limit
        )
        support_level = price_targets.get('next_support')
        resistance_level = price_targets.get('next_resistance')
        
        # 乖离惩罚
        if bias_pct > 0.15:
            bias_penalty = max(-0.35, bias_pct * -1.6)
        else:
            bias_penalty = max(-0.7, bias_pct * -2.0)

        vol_penalty = 0.20 if is_high_vol else 0.0

        # ----------- 动态入场价 (Entry) -----------
        raw_pullback_mult = trend_risk_score + bias_penalty + vol_penalty
        pullback_multiplier = max(0.25, min(raw_pullback_mult, 2.2))

        MAX_DRAWDOWN_CAP = board_limit * 1.3 
        max_allowed_drawdown = current_price * MAX_DRAWDOWN_CAP
        pullback = min(atr * pullback_multiplier, max_allowed_drawdown)
        dynamic_entry = current_price - pullback
        
        # 支撑位交互
        if support_level:
            supp_distance = (current_price - support_level) / current_price
            if supp_distance < market_profile.get('limit', 0.1):
                if trend_risk_score > 1.0:
                    dynamic_entry = min(dynamic_entry, support_level * 0.97)
                else:
                    dynamic_entry = max(dynamic_entry, support_level + (atr * 0.1))

        # 最终买入价兜底保护
        min_price_floor = current_price * {
            'distribution': 0.78,
            'decline': 0.76,
            'accumulation': 0.72,
            'markup': 0.75
        }.get(trend_phase, 0.75)
        
        entry_price = round(max(min(dynamic_entry, current_price * 0.99), min_price_floor), 2)

        # ----------- 动态止损价 (Stop) -----------
        volatility_ratio = atr / current_price
        stop_mult = 1.2 + (volatility_ratio * 10)
        max_stop_distance = entry_price * (board_limit * 0.8)
        stop_price = round(entry_price - min(atr * stop_mult, max_stop_distance), 2)
        if support_level and support_level < entry_price:
            stop_price = max(stop_price, round(support_level * 0.98, 2))

        # ----------- 动态止盈价 (Target) - V4.4 场景化优化 -----------
        base_target_mult_map = {
            'accumulation': 3.8,
            'markup': 3.2,
            'distribution': 2.1,      # 重点压制
            'decline': 2.8
        }
        base_target_mult = base_target_mult_map.get(trend_phase, 2.8)
        
        risk_deduction = (trend_risk_score - 0.5) * {
            'distribution': 1.9,
            'decline': 1.6,
            'accumulation': 1.1,
            'markup': 1.3
        }.get(trend_phase, 1.4)
        
        bias_adjust = bias_penalty * 0.55
        target_multiplier = max(1.15, base_target_mult - risk_deduction + bias_adjust)
        
        # 高波 + 高风险阶段额外压制
        if is_high_vol:
            target_multiplier *= 0.65
        elif trend_phase in ['distribution', 'decline']:
            target_multiplier *= 0.82
        
        # 板块差异化利润天花板
        MAX_PROFIT_CAP = board_limit * {
            '10CM': 1.55,
            '20CM': 1.35,
            '30CM': 1.25
        }.get(board_type, 1.4)
        
        target_add = min(atr * target_multiplier, entry_price * MAX_PROFIT_CAP)
        target_price = round(entry_price + target_add, 2)

        reasons.append(f"止盈建议：[V4.4场景化] 弹性系数 {target_multiplier:.2f}x ATR，天花板 {MAX_PROFIT_CAP*100:.0f}%")

        # 阻力位严格逃顶
        if resistance_level and entry_price < resistance_level:
            if trend_phase == 'accumulation' and not is_high_vol and bias_pct < 0.08:
                target_price = max(target_price, round(resistance_level * 1.02, 2))
            else:
                target_price = min(target_price, round(resistance_level * 0.97, 2))
                reasons.append(f"风控动作：严格逃顶至阻力下方 ({resistance_level:.2f})")

        # ==========================================
        # 第四阶段：时间风控
        # ==========================================
        if board_type == '10CM':
            reasons.append("⏳ 风控军规：[10CM] T+2 极易诱多A杀，T+3 未达止盈必须强制平仓。")
        else:
            reasons.append("⏳ 风控军规：T+3 时间止损 — 持仓3天未触及止盈强制清仓。")

        return {
            'action': action,
            'confidence': float(confidence),
            'quality_grade': quality_grade,
            'analysis_logic': reasons,
            'current_price': current_price,
            'entry_price': entry_price,
            'target_price': target_price,
            'stop_price': stop_price,
            'resistance_level': resistance_level,
            'support_level': support_level,
            'feature_trend': trend_phase,
            'feature_pattern': pattern_name,
            'feature_bias_val': round(bias_pct, 4),
            'feature_bias_tier': bias_tier,
            'full_confluence_result': confluence_result,
            'time_stop_days': 3,
            'trailing_stop_trigger': 0.05,
        }
    except Exception as e:
        logger.error(f"V4.4交易建议生成失败: {e}")
        import traceback
        traceback.print_exc()
        return {'action': 'ERROR', 'analysis_logic': [f'分析时发生错误: {e}'], 'confidence': 0}