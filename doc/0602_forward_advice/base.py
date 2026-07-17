def _generate_forward_advice_v4(df: pd.DataFrame, stock_code: str) -> dict:
    """
    【V4.3 终极核心函数】基于 V4.0 Confluence Scorer 生成高质量、可解释的交易建议
    融入自适应数学网格、动态支撑/阻力过滤、多维特征标签与时间风控体系。
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
        # 提取趋势与市场环境
        market_phase = confluence_result.get('market_phase', 'unknown')
        trend_phase = market_phase  # 统一变量名
        
        # 获取 ATR 及板块信息
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

        alignment = confluence_result.get('alignment_analysis', {})
        if alignment.get('alignment_score', 0) > 5:
            reasons.append(f"历史对齐：价格与指标底部同步性良好 (得分: {alignment['alignment_score']})。")
        
        backtest_val = confluence_result.get('backtest_analysis', {})
        if backtest_val.get('signal_count', 0) > 0:
            reasons.append(f"历史回测：基于对齐信号的历史胜率为 {backtest_val['win_rate']:.1%} (共{backtest_val['signal_count']}次)。")

        # ==========================================
        # 第二阶段：多维特征标签构造 (供深度回测透视使用)
        # ==========================================
        # 乖离率特征 (Bias - 距离MA60的偏离程度)
        latest_ma60 = df.iloc[latest_index].get('ma60')
        if pd.isna(latest_ma60) or latest_ma60 == 0:
            bias_pct = 0.0
        else:
            bias_pct = (current_price - latest_ma60) / latest_ma60
            
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
        # 第三阶段：自适应网格定价与支撑阻力过滤
        # ==========================================
        # 提前计算趋势风险分，用于支撑位过滤
        trend_risk_score = {'decline': 1.85, 'distribution': 0.85, 'accumulation': 0.55, 'markup': 0.9}.get(trend_phase, 1.0)
        
        # 动态计算有效支撑位和阻力位 (调用最新的 V4.3 函数)
        price_targets = _calculate_price_targets(
            df=df, 
            current_price=current_price, 
            atr=atr, 
            trend_phase=trend_phase, 
            board_limit=board_limit
        )
        support_level = price_targets.get('next_support')
        resistance_level = price_targets.get('next_resistance')
        
        # 乖离惩罚：给超跌折扣，超买加深防守。控制在物理极限内。
        #raw_bias_penalty = bias_pct * 2.5 
        #bias_penalty = max(-0.8, min(1.5, raw_bias_penalty))
        if bias_pct > 0.15:
            bias_penalty = max(-0.35, bias_pct * -1.6)
        else:
            bias_penalty = max(-0.7, bias_pct * -2.0)

        # 波动率温和惩罚
        vol_penalty = 0.20 if is_high_vol else 0.0

        # ----------- 动态入场价 (Entry) -----------
        # 核心方程：挂单深度 = 趋势风险 + 乖离惩罚 + 波动惩罚
        raw_pullback_mult = trend_risk_score + bias_penalty + vol_penalty
        pullback_multiplier = max(0.25, min(raw_pullback_mult, 2.2))

        MAX_DRAWDOWN_CAP = board_limit * 1.3 
        MAX_PROFIT_CAP = board_limit * 1.3

        max_allowed_drawdown = current_price * MAX_DRAWDOWN_CAP
        pullback = min(atr * pullback_multiplier, max_allowed_drawdown)
        dynamic_entry = current_price - pullback
        
        supp_distance = (current_price - support_level) / current_price if support_level else 1
        
        # 智能支撑位交互方程
        if support_level and supp_distance < market_profile['limit']:
            if trend_risk_score > 1.0:
                dynamic_entry = min(dynamic_entry, support_level * 0.97)
                reasons.append(f"入场建议：[自适应] 行情偏弱，任由价格击穿支撑位({support_level:.2f})吸筹，限价 ¥{dynamic_entry:.2f}。")
            else:
                dynamic_entry = max(dynamic_entry, support_level + (atr * 0.1))
                reasons.append(f"入场建议：[自适应] 行情强势，依托技术支撑位({support_level:.2f})上方拦截，限价 ¥{dynamic_entry:.2f}。")
        else:
            reasons.append(f"入场建议：[自适应] 依据趋势分({trend_risk_score:.1f})与乖离，自动计算回撤系数 {pullback_multiplier:.1f}x ATR。")

        if pullback_multiplier >= 2.8:
            action = 'AVOID'
            reasons.append("⚠️风险警示：系统测算趋势破位且乖离过大，风险收益比极差，强烈建议规避。")

        #entry_price = round(max(min(dynamic_entry, current_price * 0.99), current_price * (1 - board_limit)), 2)
                # distribution 高位乖离时略微放宽下限保护
        min_price_floor = current_price * 0.78 if (trend_phase == 'distribution' and bias_pct > 0.12) else current_price * 0.75
        entry_price = round(max(min(dynamic_entry, current_price * 0.99), min_price_floor), 2)

        volatility_ratio = atr / current_price # 动态日内波动率评估
        is_high_vol = volatility_ratio > 0.06  
        # ----------- 动态止损价 (Stop) -----------
        stop_mult = 1.2 + (volatility_ratio * 10)  
        max_stop_distance = entry_price * (board_limit * 0.8) 
        
        stop_price = round(entry_price - min(atr * stop_mult, max_stop_distance), 2)  
        if support_level and support_level < entry_price:
            stop_price = max(stop_price, round(support_level * 0.98, 2)) 

        # ----------- 动态止盈价 (Target) -----------
        base_target_mult = 2 - (trend_risk_score - 0.5) * 1.4 - (bias_penalty * 0.3)
        target_multiplier = max(1.2, base_target_mult * (0.7 if is_high_vol else 1.0))
        #base_target_mult = 3.2 - (trend_risk_score - 0.5) * 1.8 - (bias_penalty * 0.6)
        #target_multiplier = max(1.2, base_target_mult * (0.6 if is_high_vol else 1.0))
        
        target_add = min(atr * target_multiplier, entry_price * MAX_PROFIT_CAP)
        target_price = round(entry_price + target_add, 2)
        
        reasons.append(f"止盈建议：[动态弹性] 算法预期弹性系数为 {target_multiplier:.1f}x ATR，最高锁定天花板为 {MAX_PROFIT_CAP*100:.0f}%。")

        if resistance_level and entry_price < resistance_level:
             # Grok 逃顶逻辑融合
             if trend_phase == 'accumulation' and not is_high_vol and bias_pct < 0.08:
                 target_price = max(target_price, round(resistance_level * 1.015, 2))
                 reasons.append(f"风控动作：底部蓄力坚实且未超买，预期突破上行阻力({resistance_level:.2f})。")
             else:
                 target_price = min(target_price, round(resistance_level * 0.975, 2))
                 reasons.append(f"风控动作：历史大数据显示该位置阻力突破胜率极低，严格压低目标至强阻力({resistance_level:.2f})下方逃顶。")

        # ==========================================
        # 第四阶段：引入时间风控 (Time-in-Market Risk)
        # ==========================================
        if board_type == '10CM':
             reasons.append("⏳ 风控军规：[10CM A杀高危区] 历史数据显示该板块 T+1/T+2 极易诱多A杀。若 T+2 冲高未能触及止盈，必须手动下调目标价，利润回撤至 3% 时无条件强制平仓，严禁格局！")
        else:
             reasons.append("⏳ 风控军规：历史大数据表明，当前交易模型的绝对高点均在 T+2 左右出现。严格执行【T+3 时间止损法】：若持仓 3 天仍未触及止盈，无论盈亏，强制清仓释放资金！")
             
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
        logger.error(f"V4.3交易建议生成失败: {e}")
        import traceback; traceback.print_exc()
        return {'action': 'ERROR', 'analysis_logic': [f'分析时发生错误: {e}'], 'confidence': 0}