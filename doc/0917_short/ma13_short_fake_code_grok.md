### Confirmation of Hourly Line Interface in quant_base

Based on the repository analysis (as of September 17, 2025), the `quant_base` project supports a multi-timeframe analysis system with 6 cycles ranging from 5 minutes to daily, as described in the architecture docs and scripts like `run_multi_timeframe_analysis.py`. This includes a monitor mode with a `--duration 60` option, which strongly implies potential handling of 60-minute (hourly) intervals. However, there is **no explicit, dedicated hourly K-line data interface** currently implemented. Relevant components include:

- **data_loader.py**: Handles general data fetching (likely daily/weekly via AKShare or Tushare integrations), but lacks specific methods for intraday/hourly K-lines (e.g., no `fetch_60min_kline` function visible).
- **indicators.py**: Computes indicators (MA, MACD, KDJ, RSI) on loaded data, adaptable to hourly but not timeframe-specific.
- **multi_timeframe_*.py** (e.g., `multi_timeframe_signal_generator.py`): Generates composite signals across cycles, potentially extensible to hourly, but current API examples (e.g., `generate_composite_signals`) are timeframe-agnostic and don't reference 60min data explicitly.
- **strategies/**: Base strategies (e.g., `base_strategy.py`) use loaded data for signals, but no hourly confirmation logic.

In summary: The foundation exists for multi-timeframe (including hourly via `--duration 60`), but **no concrete hourly interface** (e.g., for fetching/processing 60min K-lines) is present. This aligns with the "unexpected results" from prior reviews—strategies like golden cross work on daily but miss hourly validations for our MA13 system.

### Pseudo-Code for Required Modifications

To integrate hourly confirmation (steps 4-5 of our MA13 system: 超跌反弹 and 中继确认 models) without dynamic elements or risk controls, focus modifications on:

- **data_loader.py**: Add a simple hourly data fetcher (assuming AKShare/Tushare as backend).
- **indicators.py**: Extend for hourly-compatible calcs (reuse existing MA/MACD/KDJ/RSI funcs with df input).
- **ma13_callback_strategy.py** (new/extend from `base_strategy.py`): Add hourly model checks in `apply_strategy()`.

These changes keep it modular: Load hourly data only if daily passes steps 1-3, then apply models for buy signals. Pseudo-code assumes pandas for data handling and talib for indicators (if integrated).

#### 1. Modification to `data_loader.py` (Add Hourly Fetch Interface)

```python
# Add to data_loader.py: New method for 60min K-line data
import akshare as ak  # Assuming AKShare for A股 data; fallback to tushare if needed
import pandas as pd

class DataLoader:
    # Existing methods (e.g., load_daily_data) unchanged...
  
    def fetch_hourly_kline(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        Fetch 60-minute K-line data for a stock.
        Returns: DF with columns ['date', 'open', 'high', 'low', 'close', 'volume']
        """
        try:
            df = ak.stock_zh_a_hist_min_sina(
                symbol=symbol,
                period="60",  # 60min interval
                start_date=start_date,
                end_date=end_date,
                adjust="qfq"  # Forward-adjusted
            )
            df = df.rename(columns={'day': 'date', 'open': 'open', 'high': 'high', 'low': 'low', 
                                    'close': 'close', 'volume': 'volume'}).sort_values('date')
            df['date'] = pd.to_datetime(df['date'])
            return df
        except Exception as e:
            print(f"Error fetching hourly data for {symbol}: {e}")
            return pd.DataFrame()  # Empty DF on failure
```

#### 2. Modification to `indicators.py` (Hourly-Compatible Indicator Extension)

```python
# Extend existing indicators.py: Add timeframe-agnostic wrappers
import talib
import pandas as pd
import numpy as np

# Existing functions (e.g., calculate_macd(df), calculate_kdj(df)) unchanged...

def get_indicator_position(indicator_value: float, category: str) -> str:
    """
    Classify indicator position relative to thresholds (for models).
    category: 'kdj_j', 'rsi_6', 'macd_dif'
    """
    if category == 'kdj_j':
        if indicator_value < 40:
            return 'oversold'
        elif 40 <= indicator_value <= 90:
            return 'relay'
        else:
            return 'overbought'
    elif category == 'rsi_6':
        if indicator_value > 60:
            return 'strong_support'
        else:
            return 'neutral'
    elif category == 'macd_dif':
        if indicator_value > 0:
            return 'above_zero'
        else:
            return 'below_zero'
    return 'neutral'

# Usage: In strategy, call e.g., get_kdj_position(kdj['J'].iloc[-1], 'kdj_j')
```

#### 3. Modification to `ma13_callback_strategy.py` (Core Strategy with Hourly Models)

```python
# New/extend from backend/strategies/base_strategy.py
from backend.data_loader import DataLoader
from backend.indicators import calculate_ma, calculate_macd, calculate_kdj, calculate_rsi, get_indicator_position
import pandas as pd
import numpy as np

class MA13CallbackStrategy:
    def __init__(self, config: dict):
        self.loader = DataLoader()
        self.config = config  # e.g., {'callback_range': [3,15], 'vol_multiplier': 1.1}
  
    def apply_strategy(self, symbol: str, daily_df: pd.DataFrame) -> dict:
        """
        Full 5-step application; if steps 1-3 pass, load hourly and check models.
        Returns: {'signal': 'buy_relay' or None, 'strength': float}
        """
        # Steps 1-3: Daily trend (existing logic, simplified pseudo)
        ma13 = calculate_ma(daily_df['close'], 13)
        if not self._check_bottom_stable(daily_df) or not self._check_daily_breakout(daily_df):
            return {'signal': None}
      
        callback_pct = ((daily_df['high'].max() - daily_df['close'].iloc[-1]) / daily_df['high'].max()) * 100
        if not (self.config['callback_range'][0] <= callback_pct <= self.config['callback_range'][1]):
            return {'signal': None}
      
        if daily_df['close'].iloc[-1] < ma13.iloc[-1] * 0.98:
            return {'signal': None}  # No MA13 support
      
        # Step 4-5: Load hourly and check models
        hourly_df = self.loader.fetch_hourly_kline(symbol, '20250901', '20250917')  # Recent period
        if hourly_df.empty:
            return {'signal': None}  # Fallback if no data
      
        macd_hour = calculate_macd(hourly_df['close'], 8, 21, 6)
        kdj_hour = calculate_kdj(hourly_df['high'], hourly_df['low'], hourly_df['close'], 27, 3, 3)
        rsi_hour = calculate_rsi(hourly_df['close'], 6)
        vol_ma20 = hourly_df['volume'].rolling(20).mean()
      
        # Model 1: Super Fall Rebound (Step 4)
        if (get_indicator_position(kdj_hour['J'].iloc[-1], 'kdj_j') == 'oversold' and
            macd_hour['DIF'].iloc[-1] > macd_hour['DEA'].iloc[-1] and  # Gold cross
            hourly_df['volume'].iloc[-1] > vol_ma20.iloc[-1] * self.config['vol_multiplier']):
            return {'signal': 'buy_super_fall', 'strength': 0.7}
      
        # Model 2: Relay Confirmation (Step 5)
        elif (get_indicator_position(macd_hour['DIF'].iloc[-1], 'macd_dif') == 'above_zero' and
              macd_hour['DIF'].iloc[-1] > macd_hour['DEA'].iloc[-1] and  # Reject dead cross
              get_indicator_position(kdj_hour['J'].iloc[-1], 'kdj_j') == 'relay' and
              get_indicator_position(rsi_hour.iloc[-1], 'rsi_6') == 'strong_support' and
              hourly_df['volume'].iloc[-1] > vol_ma20.iloc[-1] * self.config['vol_multiplier']):
            return {'signal': 'buy_relay', 'strength': 0.8}
      
        return {'signal': None}
  
    def _check_bottom_stable(self, df: pd.DataFrame) -> bool:
        # Pseudo: Check 60-day box (high-low <20%), MA60 slope >0
        return True  # Placeholder
  
    def _check_daily_breakout(self, df: pd.DataFrame) -> bool:
        # Pseudo: Rise >20%, VOL >1.2x, multi-head MA
        return True  # Placeholder
```

These pseudo-code snippets are self-contained, integrate with existing modules (e.g., via imports), and focus on hourly confirmation without extras. Test by running `apply_strategy` on sample data (e.g., via backtester.py). If needed, extend `unified_strategy_config.json` with hourly params like `"timeframe_60min": true`. This should resolve hourly integration gaps for our strategy.
