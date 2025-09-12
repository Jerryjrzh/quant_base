Excellent, this is exactly the type of iterative tuning that is required to perfect a complex scoring system. Your analysis is correct—the results are close but still not quite right. The logs show that `sh600702` passed (but barely, due to a very low MACD score) and `sh603366` failed because its price position score was too low and its RSI score was zero.

Based on this, I have identified two final weaknesses in the V2 scoring logic that need to be addressed. We will create a more robust "V3" logic.

### Analysis of V2 Scoring Flaws

1.  **Price Position Scoring is Too Sensitive**: For `sh603366`, the price was at 41.8% of its 52-week high (which is very good), but the 90-day positional score was only `18.46 / 40`. This is because the linear score reduction is too aggressive. A stock consolidating in the middle of its 90-day range is still an excellent candidate and shouldn't be penalized so heavily.
2.  **MACD Scoring is Still Flawed**: For `sh600702`, the MACD score was a mere `3.00 / 30` despite being in a healthy golden cross state above the zero axis. The V2 logic over-emphasized the "histogram flip" event and didn't adequately reward a stable, ongoing positive MACD state.

### V3 Logic: The Solution

I will now provide the updated code for `confluence_scorer.py` and its configuration file, `confluence_scorer_config.yaml`, which implement the V3 logic.

  * **Price Position Score (V3)**: Replaces the harsh linear reduction with a more forgiving **tiered (分层) system**. Stocks in the bottom 40% get full points, those in the 40-60% range get a high score, and so on. This is more aligned with real-world analysis.
  * **MACD Score (V3)**: The logic is rebuilt to better evaluate the *quality and trend* of the golden cross, rewarding strengthening momentum (`current_macd > prev_macd`) instead of just the initial event.

-----

### 1\. Updated Code: `confluence_scorer.py`

Please replace the entire content of your `backend/confluence_scorer.py` file with the code below.

```python
#!/usr/bin/env python3
"""
【V3 - 最终优化版】多指标融合评分系统
根据 test_fix_6.md 优化建议进行改进，引入V3评分逻辑
"""

import pandas as pd
import numpy as np
import yaml
import os
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class ConfluenceScorer:
    """
    【V3 - 最终优化版】多指标融合评分器
    V3 优化重点:
    - 价格位置评分改为更稳定的分层模式
    - MACD评分全面重构，评估金叉的质量和趋势
    """
    
    def __init__(self, config_path: str = None):
        if config_path is None:
            base_dir = os.path.dirname(os.path.dirname(__file__))
            config_path = os.path.join(base_dir, 'config', 'confluence_scorer_config.yaml')
        
        self.config_path = config_path
        self._load_config()
    
    def _load_config(self):
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            self.weights = config.get('weights', {})
            self.thresholds = config.get('thresholds', {})
            self.scoring = config.get('scoring', {})
            self.stateful_checks = config.get('stateful_checks', {})
            self.bonus_scores = config.get('bonus_scores', {})
            logger.info(f"✅ V3融合评分器配置加载成功: {self.config_path}")
        except FileNotFoundError:
            logger.warning(f"⚠️ 配置文件不存在，使用V3默认配置: {self.config_path}")
            self._use_default_config()
        except Exception as e:
            logger.error(f"⚠️ 加载配置文件失败，使用V3默认配置: {e}")
            self._use_default_config()
    
    def _use_default_config(self):
        """使用V3默认配置"""
        self.weights = {'price_position': 40, 'macd_state': 30, 'kdj_state': 20, 'rsi_state': 10}
        self.thresholds = {
            'price_position_tiers': { 'tier1': 0.4, 'tier2': 0.6, 'tier3': 0.8 },
            'price_position_scores': { 'tier1': 40, 'tier2': 30, 'tier3': 15 },
            'price_ratio_filter': 0.85, 'macd_zero_threshold': 0.1, 'kdj_low_threshold': 50,
            'kdj_oversold': 20, 'rsi_bullish_low': 50, 'rsi_bullish_high': 75, 'rsi_oversold': 30
        }
        self.scoring = {'min_confluence_score': 70, 'max_possible_score': 110}
        self.stateful_checks = {'lookback_days': 10, 'macd_consolidation_ratio': 0.6, 'kdj_oversold_min_days': 2}
        self.bonus_scores = {'macd_consolidation': 5, 'kdj_oversold_period': 5}
    
    def calculate_price_position_score(self, df: pd.DataFrame, index: int) -> float:
        """【V3 - 已优化】计算价格位置评分 (分层模式)"""
        try:
            window_size = min(90, len(df)); end_pos = index + 1; start_pos = max(0, end_pos - window_size)
            if window_size < 30: return 0
            
            window_data = df.iloc[start_pos:end_pos]
            current_price = df.iloc[index]['close']
            min_price = window_data['low'].min(); max_price = window_data['high'].max()
            if max_price <= min_price: return 0
            
            price_position = (current_price - min_price) / (max_price - min_price)
            
            tiers = self.thresholds.get('price_position_tiers', {'tier1': 0.4, 'tier2': 0.6, 'tier3': 0.8})
            scores = self.thresholds.get('price_position_scores', {'tier1': 40, 'tier2': 30, 'tier3': 15})

            if price_position <= tiers['tier1']: return scores['tier1']
            if price_position <= tiers['tier2']: return scores['tier2']
            if price_position <= tiers['tier3']: return scores['tier3']
            return 0
        except Exception as e:
            logger.warning(f"计算价格位置评分失败: {e}"); return 0
    
    def calculate_macd_state_score(self, df: pd.DataFrame, index: int) -> float:
        """【V3 - 已优化】计算MACD状态评分 (重构逻辑)"""
        try:
            if index < 1: return 0
            current = df.iloc[index]; prev = df.iloc[index-1]
            score = 0
            
            is_golden_cross = current.get('diff', 0) > current.get('dea', 0)
            if not is_golden_cross: return 0 # 金叉是必要条件

            # 1. 基础分: 只要是金叉就有分
            score += self.weights['macd_state'] * 0.4 # 12分
            
            # 2. 状态加分: 柱状线为正
            if current.get('macd', 0) > 0:
                score += self.weights['macd_state'] * 0.2 # 6分
            
            # 3. 趋势加分: 动能增强 (柱状线变长)
            if current.get('macd', 0) > prev.get('macd', 0):
                score += self.weights['macd_state'] * 0.2 # 6分
                
            # 4. 事件加分: 刚刚翻红
            if current.get('macd', 0) > 0 and prev.get('macd', 0) <= 0:
                score += self.weights['macd_state'] * 0.2 # 6分 (可与趋势分叠加)

            return min(score, self.weights['macd_state'])
        except Exception as e:
            logger.warning(f"计算MACD状态评分失败: {e}"); return 0

    # KDJ and RSI scorers are performing well, no changes needed from V2
    def calculate_kdj_state_score(self, df: pd.DataFrame, index: int) -> float:
        try:
            if index < 1: return 0
            current_k = df.iloc[index].get('k', 50); current_d = df.iloc[index].get('d', 50); prev_k = df.iloc[index-1].get('k', 50)
            if not current_k > prev_k: return 0
            score = 0
            if current_k > current_d: score += self.weights['kdj_state'] * 0.5
            if current_k < self.thresholds['kdj_low_threshold']: score += self.weights['kdj_state'] * 0.3
            if current_k > self.thresholds['kdj_oversold']: score += self.weights['kdj_state'] * 0.2
            return min(score, self.weights['kdj_state'])
        except Exception as e:
            logger.warning(f"计算KDJ状态评分失败: {e}"); return 0
    
    def calculate_rsi_state_score(self, df: pd.DataFrame, index: int) -> float:
        try:
            if index < 1: return 0
            current_rsi = df.iloc[index].get('rsi6', 50); prev_rsi = df.iloc[index-1].get('rsi6', 50)
            score = 0
            rsi_bullish_low = self.thresholds.get('rsi_bullish_low', 50); rsi_bullish_high = self.thresholds.get('rsi_bullish_high', 75)
            if rsi_bullish_low <= current_rsi <= rsi_bullish_high:
                score += self.weights['rsi_state'] * 0.7
                if current_rsi > prev_rsi: score += self.weights['rsi_state'] * 0.3
            rsi_oversold = self.thresholds.get('rsi_oversold', 30)
            if prev_rsi <= rsi_oversold and current_rsi > rsi_oversold: score += self.weights['rsi_state'] * 0.5
            return min(score, self.weights['rsi_state'])
        except Exception as e:
            logger.warning(f"计算RSI状态评分失败: {e}"); return 0

    # No changes needed for the rest of the file
    def check_stateful_conditions(self, df: pd.DataFrame, index: int) -> Dict[str, bool]:
        try:
            lookback_days = min(self.stateful_checks.get('lookback_days', 10), index)
            if lookback_days < 5: return {'macd_consolidation': False, 'kdj_oversold_period': False}
            start_pos = index - lookback_days
            window_data = df.iloc[start_pos:index]
            macd_values = window_data.get('macd', pd.Series())
            consolidation_ratio = self.stateful_checks.get('macd_consolidation_ratio', 0.6)
            macd_consolidation = (macd_values <= 0).sum() >= lookback_days * consolidation_ratio
            k_values = window_data.get('k', pd.Series())
            min_oversold_days = self.stateful_checks.get('kdj_oversold_min_days', 2)
            kdj_oversold_period = (k_values <= 30).sum() >= min_oversold_days
            return {'macd_consolidation': macd_consolidation, 'kdj_oversold_period': kdj_oversold_period}
        except Exception as e:
            logger.warning(f"检查状态历史条件失败: {e}"); return {'macd_consolidation': False, 'kdj_oversold_period': False}
    
    def calculate_confluence_score(self, df: pd.DataFrame, index: int) -> Dict:
        try:
            price_score = self.calculate_price_position_score(df, index)
            macd_score = self.calculate_macd_state_score(df, index)
            kdj_score = self.calculate_kdj_state_score(df, index)
            rsi_score = self.calculate_rsi_state_score(df, index)
            stateful_conditions = self.check_stateful_conditions(df, index)
            base_score = price_score + macd_score + kdj_score + rsi_score
            bonus_score = 0
            if stateful_conditions['macd_consolidation']: bonus_score += self.bonus_scores.get('macd_consolidation', 5)
            if stateful_conditions['kdj_oversold_period']: bonus_score += self.bonus_scores.get('kdj_oversold_period', 5)
            total_score = base_score + bonus_score
            max_possible_score = self.scoring.get('max_possible_score', 110)
            confidence = min(total_score / max_possible_score, 1.0)
            min_score_threshold = self.scoring.get('min_confluence_score', 70)
            return {
                'total_score': total_score, 'confidence': confidence,
                'breakdown': {'price_position': price_score, 'macd_state': macd_score, 'kdj_state': kdj_score, 'rsi_state': rsi_score, 'bonus_score': bonus_score},
                'stateful_conditions': stateful_conditions, 'is_high_quality': total_score >= min_score_threshold
            }
        except Exception as e:
            logger.error(f"计算融合评分失败: {e}"); return {'total_score': 0, 'confidence': 0, 'breakdown': {}, 'stateful_conditions': {}, 'is_high_quality': False, 'error': str(e)}
    
    def filter_by_price_position(self, df: pd.DataFrame, index: int) -> Tuple[bool, str]:
        try:
            window_size = min(252, len(df)); end_pos = index + 1; start_pos = max(0, end_pos - window_size)
            if window_size < 30: return True, "数据不足，跳过过滤"
            window_data = df.iloc[start_pos:end_pos]; current_price = df.iloc[index]['close']; rolling_high = window_data['high'].max()
            if rolling_high <= 0: return True, "价格数据异常"
            price_ratio = current_price / rolling_high
            price_filter_threshold = self.thresholds.get('price_ratio_filter', 0.8)
            if price_ratio > price_filter_threshold: return False, f"价格位于52周高点的{price_ratio:.1%}，过高（阈值{price_filter_threshold:.1%}）"
            return True, f"价格位于52周高点的{price_ratio:.1%}，合适"
        except Exception as e:
            logger.warning(f"价格位置过滤失败: {e}"); return True, "过滤器异常，允许通过"

confluence_scorer = ConfluenceScorer()
```

### 2\. Updated Config: `confluence_scorer_config.yaml`

Please create or update the file `config/confluence_scorer_config.yaml` with the following content. This introduces the new tiered pricing parameters.

```yaml
# 【V3】多指标融合评分系统配置
# 引入了更灵活的价格位置评分标准

# 评分权重配置
weights:
  price_position: 40
  macd_state: 30
  kdj_state: 20
  rsi_state: 10

# 阈值配置
thresholds:
  # V3: 价格位置评分分层标准 (90日区间)
  price_position_tiers:
    tier1: 0.4  # 位置 < 40%
    tier2: 0.6  # 位置 < 60%
    tier3: 0.8  # 位置 < 80%
  
  # V3: 价格位置分层对应的分数
  price_position_scores:
    tier1: 40   # 满分
    tier2: 30   # 优秀
    tier3: 15   # 可接受
  
  # 52周高点快速过滤器阈值 (可适当放宽至85%)
  price_ratio_filter: 0.85
  
  # MACD, KDJ, RSI 阈值
  macd_zero_threshold: 0.1
  kdj_low_threshold: 50
  kdj_oversold: 20
  rsi_bullish_low: 50
  rsi_bullish_high: 75
  rsi_oversold: 30

# 评分标准
scoring:
  min_confluence_score: 70
  max_possible_score: 110

# 历史状态检查配置
stateful_checks:
  lookback_days: 10
  macd_consolidation_ratio: 0.6
  kdj_oversold_min_days: 2
  
# 奖励分配置
bonus_scores:
  macd_consolidation: 5
  kdj_oversold_period: 5
```

### Expected Outcome

After applying these two updates, run your validation commands again.

  * **For `sh603366`**: The `价格位置评分` will now use the tiered system. Since it's in a good position, its score should jump from `18.46` to at least `30`, pushing the total score well above 70.
  * **For `sh600702`**: The `MACD状态评分` will now properly reward its stable golden cross state, jumping from `3.00` to a much healthier score (likely `18-24`), solidifying its PASS status with a higher grade.

These V3 enhancements create a much more nuanced and accurate scoring model that should now correctly identify all of your hand-picked "golden node" examples as high-quality opportunities.