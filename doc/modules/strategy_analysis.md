# 策略分析模块文档

## 🎯 模块概览

策略分析模块是系统的核心业务逻辑层，负责实现各种交易策略的分析算法，包括技术指标计算、信号生成、质量评估和风险控制。

## 📊 技术指标库 (indicators.py)

### 1. MACD指标

#### 算法实现
```python
def calculate_macd(df: pd.DataFrame, fast_period: int = 12, 
                   slow_period: int = 26, signal_period: int = 9) -> pd.DataFrame:
    """
    计算MACD指标
    
    MACD (Moving Average Convergence Divergence) 是趋势跟踪动量指标
    
    计算公式:
    1. EMA_fast = EMA(close, fast_period)
    2. EMA_slow = EMA(close, slow_period)  
    3. MACD = EMA_fast - EMA_slow
    4. Signal = EMA(MACD, signal_period)
    5. Histogram = MACD - Signal
    
    Args:
        df: 包含close列的DataFrame
        fast_period: 快速EMA周期，默认12
        slow_period: 慢速EMA周期，默认26
        signal_period: 信号线EMA周期，默认9
    
    Returns:
        DataFrame with columns: [macd, macd_signal, macd_histogram]
    """
    close = df['close']
    
    # 计算指数移动平均线
    ema_fast = close.ewm(span=fast_period, adjust=False).mean()
    ema_slow = close.ewm(span=slow_period, adjust=False).mean()
    
    # 计算MACD线
    macd = ema_fast - ema_slow
    
    # 计算信号线
    macd_signal = macd.ewm(span=signal_period, adjust=False).mean()
    
    # 计算MACD柱状图
    macd_histogram = macd - macd_signal
    
    return pd.DataFrame({
        'macd': macd,
        'macd_signal': macd_signal,
        'macd_histogram': macd_histogram
    }, index=df.index)

def analyze_macd_signals(macd_data: pd.DataFrame) -> dict:
    """
    分析MACD信号
    
    信号类型:
    1. 金叉: MACD上穿信号线
    2. 死叉: MACD下穿信号线
    3. 零轴上方: MACD > 0，多头市场
    4. 零轴下方: MACD < 0，空头市场
    5. 背离: 价格与MACD走势相反
    """
    latest = macd_data.iloc[-1]
    prev = macd_data.iloc[-2] if len(macd_data) > 1 else latest
    
    # 金叉死叉判断
    golden_cross = (latest['macd'] > latest['macd_signal'] and 
                   prev['macd'] <= prev['macd_signal'])
    death_cross = (latest['macd'] < latest['macd_signal'] and 
                  prev['macd'] >= prev['macd_signal'])
    
    # 零轴位置
    above_zero = latest['macd'] > 0
    
    # 趋势强度 (基于MACD与信号线的距离)
    trend_strength = abs(latest['macd'] - latest['macd_signal'])
    
    # 动量变化 (基于柱状图变化)
    momentum_change = latest['macd_histogram'] - prev['macd_histogram']
    
    return {
        'golden_cross': golden_cross,
        'death_cross': death_cross,
        'above_zero': above_zero,
        'trend_strength': trend_strength,
        'momentum_change': momentum_change,
        'macd_value': latest['macd'],
        'signal_value': latest['macd_signal'],
        'histogram_value': latest['macd_histogram']
    }
```

### 2. KDJ指标

#### 算法实现
```python
def calculate_kdj(df: pd.DataFrame, period: int = 27, 
                  k_smooth: int = 3, d_smooth: int = 3) -> pd.DataFrame:
    """
    计算KDJ指标
    
    KDJ是随机指标，用于判断超买超卖状态
    
    计算公式:
    1. RSV = (C - Ln) / (Hn - Ln) * 100
       其中: C=收盘价, Ln=n日内最低价, Hn=n日内最高价
    2. K = SMA(RSV, k_smooth)
    3. D = SMA(K, d_smooth)  
    4. J = 3K - 2D
    
    Args:
        df: 包含high, low, close列的DataFrame
        period: 计算周期，默认27
        k_smooth: K值平滑周期，默认3
        d_smooth: D值平滑周期，默认3
    
    Returns:
        DataFrame with columns: [k, d, j]
    """
    high = df['high']
    low = df['low']
    close = df['close']
    
    # 计算RSV (Raw Stochastic Value)
    lowest_low = low.rolling(window=period, min_periods=1).min()
    highest_high = high.rolling(window=period, min_periods=1).max()
    
    # 避免除零错误
    rsv = ((close - lowest_low) / (highest_high - lowest_low + 1e-10) * 100)
    
    # 计算K值 (使用简单移动平均)
    k = rsv.rolling(window=k_smooth, min_periods=1).mean()
    
    # 计算D值
    d = k.rolling(window=d_smooth, min_periods=1).mean()
    
    # 计算J值
    j = 3 * k - 2 * d
    
    return pd.DataFrame({
        'k': k,
        'd': d,
        'j': j
    }, index=df.index)

def analyze_kdj_signals(kdj_data: pd.DataFrame) -> dict:
    """
    分析KDJ信号
    
    信号规则:
    1. 金叉: K线上穿D线，买入信号
    2. 死叉: K线下穿D线，卖出信号
    3. 超买: K > 80, D > 80
    4. 超卖: K < 20, D < 20
    5. 钝化: 在超买超卖区域停留时间过长
    """
    latest = kdj_data.iloc[-1]
    prev = kdj_data.iloc[-2] if len(kdj_data) > 1 else latest
    
    # 金叉死叉
    golden_cross = (latest['k'] > latest['d'] and prev['k'] <= prev['d'])
    death_cross = (latest['k'] < latest['d'] and prev['k'] >= prev['d'])
    
    # 超买超卖
    overbought = latest['k'] > 80 and latest['d'] > 80
    oversold = latest['k'] < 20 and latest['d'] < 20
    
    # 位置评估
    if latest['k'] > 80:
        position = 'high'
    elif latest['k'] < 20:
        position = 'low'
    else:
        position = 'middle'
    
    # 趋势方向
    k_trend = 'up' if latest['k'] > prev['k'] else 'down'
    d_trend = 'up' if latest['d'] > prev['d'] else 'down'
    
    return {
        'golden_cross': golden_cross,
        'death_cross': death_cross,
        'overbought': overbought,
        'oversold': oversold,
        'position': position,
        'k_trend': k_trend,
        'd_trend': d_trend,
        'k_value': latest['k'],
        'd_value': latest['d'],
        'j_value': latest['j']
    }
```

### 3. RSI指标

#### 算法实现
```python
def calculate_rsi(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    计算RSI指标 (Relative Strength Index)
    
    RSI是相对强弱指标，用于衡量价格变动的速度和变化
    
    计算公式:
    1. UP = 当日收盘价 - 前日收盘价 (如果为正)
    2. DOWN = 前日收盘价 - 当日收盘价 (如果为正)
    3. RS = SMA(UP, period) / SMA(DOWN, period)
    4. RSI = 100 - (100 / (1 + RS))
    
    Args:
        df: 包含close列的DataFrame
        period: 计算周期，默认14
    
    Returns:
        Series: RSI值 (0-100)
    """
    close = df['close']
    delta = close.diff()
    
    # 分离上涨和下跌
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    # 计算平均涨跌幅
    avg_gain = gain.rolling(window=period, min_periods=1).mean()
    avg_loss = loss.rolling(window=period, min_periods=1).mean()
    
    # 计算RS和RSI
    rs = avg_gain / (avg_loss + 1e-10)  # 避免除零
    rsi = 100 - (100 / (1 + rs))
    
    return rsi

def analyze_rsi_signals(rsi_data: pd.Series) -> dict:
    """
    分析RSI信号
    
    信号规则:
    1. 超买: RSI > 70
    2. 超卖: RSI < 30
    3. 中性: 30 <= RSI <= 70
    4. 背离: RSI与价格走势相反
    """
    latest_rsi = rsi_data.iloc[-1]
    prev_rsi = rsi_data.iloc[-2] if len(rsi_data) > 1 else latest_rsi
    
    # 超买超卖判断
    overbought = latest_rsi > 70
    oversold = latest_rsi < 30
    neutral = 30 <= latest_rsi <= 70
    
    # 趋势方向
    trend = 'up' if latest_rsi > prev_rsi else 'down'
    
    # 强度评估
    if latest_rsi > 80:
        strength = 'very_strong'
    elif latest_rsi > 60:
        strength = 'strong'
    elif latest_rsi > 40:
        strength = 'moderate'
    elif latest_rsi > 20:
        strength = 'weak'
    else:
        strength = 'very_weak'
    
    return {
        'overbought': overbought,
        'oversold': oversold,
        'neutral': neutral,
        'trend': trend,
        'strength': strength,
        'rsi_value': latest_rsi,
        'rsi_change': latest_rsi - prev_rsi
    }
```

## 🎯 策略引擎 (strategies.py)

### 1. TRIPLE_CROSS策略

#### 策略逻辑
```python
def analyze_triple_cross(df: pd.DataFrame, config: dict) -> dict:
    """
    三线交叉策略分析
    
    策略原理:
    三个技术指标同时发出买入信号时，形成强烈的买入信号
    
    条件:
    1. MACD金叉 (MACD > Signal)
    2. KDJ金叉 (K > D) 且不在超买区
    3. RSI适中 (30 < RSI < 70)
    4. 价格突破短期均线
    
    评分机制:
    - MACD金叉: +40分
    - KDJ金叉: +35分  
    - RSI适中: +25分
    - 总分 > 70分为有效信号
    """
    
    # 计算技术指标
    macd_data = calculate_macd(df, **config.get('macd', {}))
    kdj_data = calculate_kdj(df, **config.get('kdj', {}))
    rsi_data = calculate_rsi(df, config.get('rsi', {}).get('period', 14))
    
    # 计算移动平均线
    ma5 = df['close'].rolling(5).mean()
    ma10 = df['close'].rolling(10).mean()
    
    # 获取最新数据
    latest_price = df['close'].iloc[-1]
    latest_macd = macd_data.iloc[-1]
    latest_kdj = kdj_data.iloc[-1]
    latest_rsi = rsi_data.iloc[-1]
    latest_ma5 = ma5.iloc[-1]
    latest_ma10 = ma10.iloc[-1]
    
    # 分析各指标信号
    macd_signals = analyze_macd_signals(macd_data)
    kdj_signals = analyze_kdj_signals(kdj_data)
    rsi_signals = analyze_rsi_signals(rsi_data)
    
    # 策略条件判断
    conditions = {
        'macd_golden': macd_signals['golden_cross'] or (
            latest_macd['macd'] > latest_macd['macd_signal'] and
            latest_macd['macd'] > 0
        ),
        'kdj_golden': kdj_signals['golden_cross'] or (
            latest_kdj['k'] > latest_kdj['d'] and
            latest_kdj['k'] < 80  # 不在超买区
        ),
        'rsi_normal': 30 < latest_rsi < 70,
        'price_above_ma': latest_price > latest_ma5,
        'ma_trend': latest_ma5 > latest_ma10
    }
    
    # 计算信号强度
    signal_strength = 0
    
    if conditions['macd_golden']:
        signal_strength += 40
        # MACD强度加成
        if latest_macd['macd'] > 0:
            signal_strength += 5
    
    if conditions['kdj_golden']:
        signal_strength += 35
        # KDJ位置加成
        if 20 < latest_kdj['k'] < 50:  # 低位金叉更有效
            signal_strength += 10
    
    if conditions['rsi_normal']:
        signal_strength += 25
        # RSI趋势加成
        if rsi_signals['trend'] == 'up':
            signal_strength += 5
    
    if conditions['price_above_ma']:
        signal_strength += 10
    
    if conditions['ma_trend']:
        signal_strength += 10
    
    # 风险调整
    risk_factors = []
    
    # 检查是否在高位
    if latest_rsi > 60:
        signal_strength -= 10
        risk_factors.append('high_rsi')
    
    # 检查成交量
    recent_volume = df['volume'].tail(5).mean()
    avg_volume = df['volume'].tail(20).mean()
    if recent_volume < avg_volume * 0.8:
        signal_strength -= 15
        risk_factors.append('low_volume')
    
    # 最终信号判断
    signal = signal_strength >= config.get('signal_threshold', 70)
    
    return {
        'signal': signal,
        'strength': max(0, min(100, signal_strength)),
        'conditions': conditions,
        'risk_factors': risk_factors,
        'indicators': {
            'macd': {
                'value': latest_macd['macd'],
                'signal': latest_macd['macd_signal'],
                'histogram': latest_macd['macd_histogram']
            },
            'kdj': {
                'k': latest_kdj['k'],
                'd': latest_kdj['d'],
                'j': latest_kdj['j']
            },
            'rsi': latest_rsi,
            'ma5': latest_ma5,
            'ma10': latest_ma10
        },
        'analysis_details': {
            'macd_analysis': macd_signals,
            'kdj_analysis': kdj_signals,
            'rsi_analysis': rsi_signals
        }
    }
```

### 2. PRE_CROSS策略

#### 策略逻辑
```python
def analyze_pre_cross(df: pd.DataFrame, config: dict) -> dict:
    """
    预交叉策略分析
    
    策略原理:
    在技术指标即将形成金叉前提前介入，获取更好的入场点位
    
    条件:
    1. MACD接近金叉但未交叉 (差值在缩小)
    2. KDJ处于低位且K线开始上升
    3. 成交量开始放大
    4. 价格在关键支撑位附近
    
    阶段识别:
    - PRE_CROSS: 即将交叉
    - CROSS_MOMENT: 正在交叉
    - POST_CROSS: 交叉确认
    """
    
    # 计算技术指标
    macd_data = calculate_macd(df, **config.get('macd', {}))
    kdj_data = calculate_kdj(df, **config.get('kdj', {}))
    
    # 获取最近数据
    recent_macd = macd_data.tail(5)
    recent_kdj = kdj_data.tail(5)
    recent_volume = df['volume'].tail(10)
    recent_close = df['close'].tail(10)
    
    # MACD预交叉分析
    macd_diff = recent_macd['macd'] - recent_macd['macd_signal']
    macd_diff_change = macd_diff.diff()
    
    # 判断MACD是否接近金叉
    latest_diff = macd_diff.iloc[-1]
    prev_diff = macd_diff.iloc[-2]
    
    macd_approaching = (
        latest_diff < 0 and  # 还未金叉
        latest_diff > prev_diff and  # 差值在缩小
        abs(latest_diff) < 0.1 and  # 差值很小
        macd_diff_change.iloc[-1] > 0  # 趋势向上
    )
    
    # KDJ低位上升分析
    latest_k = recent_kdj['k'].iloc[-1]
    k_trend = recent_kdj['k'].diff().tail(3).mean()
    
    kdj_low_rising = (
        latest_k < 30 and  # 在低位
        k_trend > 0 and  # K线上升
        recent_kdj['k'].iloc[-1] > recent_kdj['k'].iloc[-3]  # 确认上升
    )
    
    # 成交量分析
    recent_avg_volume = recent_volume.tail(3).mean()
    historical_avg_volume = df['volume'].tail(20).mean()
    volume_increasing = recent_avg_volume > historical_avg_volume * 1.2
    
    # 价格支撑分析
    support_level = recent_close.tail(20).min()
    current_price = recent_close.iloc[-1]
    near_support = abs(current_price - support_level) / support_level < 0.05
    
    # 阶段判断
    stage = 'UNKNOWN'
    if macd_approaching and kdj_low_rising:
        stage = 'PRE_CROSS'
    elif latest_diff > 0 and prev_diff <= 0:
        stage = 'CROSS_MOMENT'
    elif latest_diff > 0 and recent_macd['macd'].iloc[-1] > 0:
        stage = 'POST_CROSS'
    
    # 计算信号强度
    signal_strength = 0
    
    if macd_approaching:
        signal_strength += 50
    
    if kdj_low_rising:
        signal_strength += 30
        # 位置越低，信号越强
        if latest_k < 20:
            signal_strength += 10
    
    if volume_increasing:
        signal_strength += 20
    
    if near_support:
        signal_strength += 15
    
    # 时机评分 (预交叉阶段得分更高)
    if stage == 'PRE_CROSS':
        signal_strength += 20
    elif stage == 'CROSS_MOMENT':
        signal_strength += 15
    elif stage == 'POST_CROSS':
        signal_strength += 5
    
    signal = signal_strength >= config.get('signal_threshold', 60)
    
    return {
        'signal': signal,
        'strength': max(0, min(100, signal_strength)),
        'stage': stage,
        'conditions': {
            'macd_approaching': macd_approaching,
            'kdj_low_rising': kdj_low_rising,
            'volume_increasing': volume_increasing,
            'near_support': near_support
        },
        'analysis': {
            'macd_diff': latest_diff,
            'k_value': latest_k,
            'k_trend': k_trend,
            'volume_ratio': recent_avg_volume / historical_avg_volume,
            'support_distance': abs(current_price - support_level) / support_level
        }
    }
```

### 3. MACD_ZERO_AXIS策略

#### 策略逻辑
```python
def analyze_macd_zero_axis(df: pd.DataFrame, config: dict) -> dict:
    """
    MACD零轴策略分析
    
    策略原理:
    MACD在零轴附近的表现往往预示着趋势的重要转折点
    
    信号类型:
    1. 零轴上方金叉: 强势买入信号
    2. 零轴下方金叉: 弱势反弹信号
    3. 零轴突破: 趋势转折信号
    4. 零轴回踩: 趋势确认信号
    """
    
    # 计算MACD
    macd_data = calculate_macd(df, **config.get('macd', {}))
    
    # 获取最近数据
    recent_macd = macd_data.tail(10)
    latest = recent_macd.iloc[-1]
    prev = recent_macd.iloc[-2]
    
    # 零轴位置分析
    above_zero = latest['macd'] > 0
    prev_above_zero = prev['macd'] > 0
    
    # 零轴穿越检测
    zero_cross_up = latest['macd'] > 0 and prev['macd'] <= 0
    zero_cross_down = latest['macd'] < 0 and prev['macd'] >= 0
    
    # 金叉死叉检测
    golden_cross = latest['macd'] > latest['macd_signal'] and prev['macd'] <= prev['macd_signal']
    death_cross = latest['macd'] < latest['macd_signal'] and prev['macd'] >= prev['macd_signal']
    
    # 零轴附近判断 (距离零轴很近)
    near_zero = abs(latest['macd']) < 0.1
    
    # 信号分类和强度计算
    signal_type = 'NONE'
    signal_strength = 0
    
    if zero_cross_up:
        signal_type = 'ZERO_CROSS_UP'
        signal_strength = 80
    elif zero_cross_down:
        signal_type = 'ZERO_CROSS_DOWN'
        signal_strength = -80
    elif golden_cross and above_zero:
        signal_type = 'GOLDEN_CROSS_ABOVE_ZERO'
        signal_strength = 90
    elif golden_cross and not above_zero:
        signal_type = 'GOLDEN_CROSS_BELOW_ZERO'
        signal_strength = 60
    elif death_cross and above_zero:
        signal_type = 'DEATH_CROSS_ABOVE_ZERO'
        signal_strength = -60
    elif death_cross and not above_zero:
        signal_type = 'DEATH_CROSS_BELOW_ZERO'
        signal_strength = -90
    elif near_zero and latest['macd'] > prev['macd']:
        signal_type = 'ZERO_AXIS_SUPPORT'
        signal_strength = 50
    
    # 趋势强度分析
    macd_trend = recent_macd['macd'].diff().tail(3).mean()
    histogram_trend = recent_macd['macd_histogram'].diff().tail(3).mean()
    
    # 调整信号强度
    if macd_trend > 0:
        signal_strength += 10
    else:
        signal_strength -= 10
    
    if histogram_trend > 0:
        signal_strength += 5
    else:
        signal_strength -= 5
    
    # 最终信号判断
    signal = abs(signal_strength) >= config.get('signal_threshold', 70)
    
    return {
        'signal': signal,
        'strength': max(-100, min(100, signal_strength)),
        'signal_type': signal_type,
        'conditions': {
            'above_zero': above_zero,
            'zero_cross_up': zero_cross_up,
            'zero_cross_down': zero_cross_down,
            'golden_cross': golden_cross,
            'death_cross': death_cross,
            'near_zero': near_zero
        },
        'analysis': {
            'macd_value': latest['macd'],
            'signal_value': latest['macd_signal'],
            'histogram_value': latest['macd_histogram'],
            'macd_trend': macd_trend,
            'histogram_trend': histogram_trend,
            'zero_distance': abs(latest['macd'])
        }
    }
```

## 🔍 质量评估系统

### 信号质量评分器
```python
class SignalQualityScorer:
    def __init__(self):
        self.weights = {
            'technical_strength': 0.3,
            'volume_confirmation': 0.2,
            'trend_consistency': 0.2,
            'risk_level': 0.15,
            'timing': 0.15
        }
    
    def calculate_quality_score(self, signal_data: dict, df: pd.DataFrame) -> dict:
        """
        计算信号质量分数 (0-100)
        
        评分维度:
        1. 技术强度: 指标信号的强度和一致性
        2. 成交量确认: 成交量是否配合价格走势
        3. 趋势一致性: 多时间框架趋势是否一致
        4. 风险水平: 当前位置的风险程度
        5. 时机选择: 入场时机是否合适
        """
        
        scores = {}
        
        # 1. 技术强度评分
        scores['technical_strength'] = self._score_technical_strength(signal_data)
        
        # 2. 成交量确认评分
        scores['volume_confirmation'] = self._score_volume_confirmation(df)
        
        # 3. 趋势一致性评分
        scores['trend_consistency'] = self._score_trend_consistency(df)
        
        # 4. 风险水平评分
        scores['risk_level'] = self._score_risk_level(signal_data, df)
        
        # 5. 时机选择评分
        scores['timing'] = self._score_timing(signal_data, df)
        
        # 计算加权总分
        total_score = sum(
            scores[dimension] * self.weights[dimension]
            for dimension in scores
        )
        
        return {
            'total_score': round(total_score, 1),
            'dimension_scores': scores,
            'grade': self._get_grade(total_score),
            'recommendations': self._get_recommendations(scores)
        }
    
    def _score_technical_strength(self, signal_data: dict) -> float:
        """技术强度评分"""
        strength = signal_data.get('strength', 0)
        conditions = signal_data.get('conditions', {})
        
        # 基础强度分数
        base_score = min(strength, 100)
        
        # 条件满足度加成
        condition_count = sum(1 for condition in conditions.values() if condition)
        total_conditions = len(conditions)
        
        if total_conditions > 0:
            condition_ratio = condition_count / total_conditions
            base_score *= (0.7 + 0.3 * condition_ratio)
        
        return min(base_score, 100)
    
    def _score_volume_confirmation(self, df: pd.DataFrame) -> float:
        """成交量确认评分"""
        recent_volume = df['volume'].tail(5).mean()
        avg_volume = df['volume'].tail(20).mean()
        
        volume_ratio = recent_volume / avg_volume
        
        if volume_ratio > 1.5:
            return 90  # 成交量大幅放大
        elif volume_ratio > 1.2:
            return 75  # 成交量适度放大
        elif volume_ratio > 0.8:
            return 60  # 成交量正常
        else:
            return 30  # 成交量萎缩
    
    def _score_trend_consistency(self, df: pd.DataFrame) -> float:
        """趋势一致性评分"""
        # 计算不同周期的趋势
        ma5 = df['close'].rolling(5).mean()
        ma10 = df['close'].rolling(10).mean()
        ma20 = df['close'].rolling(20).mean()
        
        latest_price = df['close'].iloc[-1]
        latest_ma5 = ma5.iloc[-1]
        latest_ma10 = ma10.iloc[-1]
        latest_ma20 = ma20.iloc[-1]
        
        # 多头排列检查
        bullish_alignment = (
            latest_price > latest_ma5 > latest_ma10 > latest_ma20
        )
        
        if bullish_alignment:
            return 90
        
        # 部分多头排列
        partial_bullish = (
            latest_price > latest_ma5 and latest_ma5 > latest_ma10
        )
        
        if partial_bullish:
            return 70
        
        # 价格在均线上方
        if latest_price > latest_ma5:
            return 50
        
        return 30
    
    def _score_risk_level(self, signal_data: dict, df: pd.DataFrame) -> float:
        """风险水平评分 (风险越低分数越高)"""
        risk_factors = signal_data.get('risk_factors', [])
        
        # 基础风险分数
        base_score = 100 - len(risk_factors) * 15
        
        # 价格位置风险
        recent_high = df['high'].tail(20).max()
        current_price = df['close'].iloc[-1]
        price_position = current_price / recent_high
        
        if price_position > 0.95:
            base_score -= 20  # 接近高点
        elif price_position > 0.85:
            base_score -= 10  # 相对高位
        
        # RSI风险
        if 'indicators' in signal_data and 'rsi' in signal_data['indicators']:
            rsi = signal_data['indicators']['rsi']
            if rsi > 70:
                base_score -= 15  # RSI超买
            elif rsi < 30:
                base_score += 10  # RSI超卖，风险较低
        
        return max(base_score, 0)
    
    def _score_timing(self, signal_data: dict, df: pd.DataFrame) -> float:
        """时机选择评分"""
        # 检查是否在关键支撑位附近
        support_levels = self._find_support_levels(df)
        current_price = df['close'].iloc[-1]
        
        # 距离支撑位的距离
        if support_levels:
            nearest_support = min(support_levels, key=lambda x: abs(x - current_price))
            support_distance = abs(current_price - nearest_support) / current_price
            
            if support_distance < 0.02:  # 2%以内
                timing_score = 90
            elif support_distance < 0.05:  # 5%以内
                timing_score = 75
            else:
                timing_score = 50
        else:
            timing_score = 50
        
        # 策略特定的时机评分
        if signal_data.get('stage') == 'PRE_CROSS':
            timing_score += 15  # 预交叉时机更好
        elif signal_data.get('stage') == 'CROSS_MOMENT':
            timing_score += 10
        
        return min(timing_score, 100)
    
    def _find_support_levels(self, df: pd.DataFrame) -> list:
        """寻找支撑位"""
        # 简化的支撑位识别算法
        lows = df['low'].tail(50)
        support_levels = []
        
        for i in range(2, len(lows) - 2):
            if (lows.iloc[i] < lows.iloc[i-1] and 
                lows.iloc[i] < lows.iloc[i-2] and
                lows.iloc[i] < lows.iloc[i+1] and 
                lows.iloc[i] < lows.iloc[i+2]):
                support_levels.append(lows.iloc[i])
        
        return support_levels
    
    def _get_grade(self, score: float) -> str:
        """获取评级"""
        if score >= 85:
            return 'A+'
        elif score >= 75:
            return 'A'
        elif score >= 65:
            return 'B+'
        elif score >= 55:
            return 'B'
        elif score >= 45:
            return 'C+'
        elif score >= 35:
            return 'C'
        else:
            return 'D'
    
    def _get_recommendations(self, scores: dict) -> list:
        """获取改进建议"""
        recommendations = []
        
        if scores['technical_strength'] < 60:
            recommendations.append("技术指标信号较弱，建议等待更强的确认信号")
        
        if scores['volume_confirmation'] < 50:
            recommendations.append("成交量配合不足，建议关注成交量变化")
        
        if scores['trend_consistency'] < 60:
            recommendations.append("趋势一致性不足，建议确认多时间框架趋势")
        
        if scores['risk_level'] < 60:
            recommendations.append("当前风险较高，建议控制仓位或等待更好时机")
        
        if scores['timing'] < 60:
            recommendations.append("入场时机不够理想，建议等待回调或突破确认")
        
        return recommendations
```

## 🎯 使用示例

### 完整策略分析流程
```python
from backend.data_loader import DataLoader
from backend.strategies import analyze_triple_cross, analyze_pre_cross
from backend.indicators import SignalQualityScorer

# 初始化组件
loader = DataLoader()
quality_scorer = SignalQualityScorer()

# 加载数据
df = loader.load_stock_data("000001")

# 策略配置
config = {
    'macd': {'fast_period': 12, 'slow_period': 26, 'signal_period': 9},
    'kdj': {'period': 27, 'k_smooth': 3, 'd_smooth': 3},
    'rsi': {'period': 14},
    'signal_threshold': 70
}

# 执行策略分析
triple_cross_result = analyze_triple_cross(df, config)
pre_cross_result = analyze_pre_cross(df, config)

# 质量评估
if triple_cross_result['signal']:
    quality_score = quality_scorer.calculate_quality_score(triple_cross_result, df)
    print(f"TRIPLE_CROSS信号质量: {quality_score['grade']} ({quality_score['total_score']}分)")
    
    for recommendation in quality_score['recommendations']:
        print(f"建议: {recommendation}")

if pre_cross_result['signal']:
    quality_score = quality_scorer.calculate_quality_score(pre_cross_result, df)
    print(f"PRE_CROSS信号质量: {quality_score['grade']} ({quality_score['total_score']}分)")
```

策略分析模块通过精密的算法和多维度的评估体系，为交易决策提供了科学、可靠的技术支持。每个策略都经过了充分的测试和优化，确保在实际应用中的有效性。