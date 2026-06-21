# Stock Breakout Detection System

A Python-based stock monitoring system that automatically identifies stocks experiencing specific price declines and detects technical breakout patterns for potential long positions.

## Quick Start

### Run the Example
```bash
python breakout_monitor.py
```

### Integration Example
```python
from breakout_monitor import BreakoutMonitor

# Initialize monitor
monitor = BreakoutMonitor()

# Your existing data
symbols = ["NSE:RELIANCE", "NSE:TCS", "NSE:INFY"]
token_list = [token1, token2, token3]
live_data = {token1: {"LTP": 2450, "High": 2500, "Low": 2440}, ...}
prev_close = {token1: 2475, ...}

# Step 1: Scan for decline (adds to watchlist automatically)
monitor.scan_for_decline_stocks(symbols, token_list, live_data, prev_close)

# Step 2: Check breakouts (use your tv_data function)
monitor.check_breakouts(your_tv_data_function)

# Step 3: View summary
monitor.get_summary()
```

## What It Does

### 1. Price Monitoring
- Scans stocks for **-1.00% to -1.15%** decline from previous close
- Automatically adds matching stocks to watchlist
- Tracks: current price, previous close, decline percentage

### 2. Pattern Detection
Monitors for 4 bullish breakout patterns:

- **Higher High**: Price breaks above previous swing high
- **W-Pattern**: Double bottom with neckline resistance break
- **Inverted Head & Shoulders**: Classic reversal pattern breakout
- **Swing High Break**: Break of last swing high before day's low

### 3. Real-time Alerts
```
[BREAKOUT DETECTED] NSE:RELIANCE
  Current Price: 2455.50
  Decline from Prev Close: -1.10%
  Time: 2025-11-23 14:35:22

  Detected Patterns:
    - Higher High
      Breakout Level: 2450.25
      Current Price: 2455.50
```

## Configuration

Edit `config.py` to customize:
- `DECLINE_MIN` / `DECLINE_MAX`: Price decline range
- `WARMUP_CANDLES`: Historical data for analysis (default: 100)
- Pattern lookback periods
- Timezone settings

## Requirements
- Python 3.11+
- pandas, numpy, pytz, requests

## Pattern Details

### Higher High
Identifies upward momentum when price makes successively higher swing highs and breaks above them.

### W-Pattern (Double Bottom)
Two similar lows forming a "W" shape with resistance neckline. Breakout above neckline signals reversal.

### Inverted Head & Shoulders
Left shoulder → Lower head → Right shoulder pattern. Breakout above neckline indicates trend reversal.

### Swing High Break (Pre-Day Low)
Breaks the last swing high that formed before the day's low was made, signaling potential bounce from lows.

## Data Format

Your `tv_data` function should return a DataFrame with:
- Columns: `open`, `high`, `low`, `close`, `volume`
- Index: Datetime
- Sorted chronologically

Your `live_data` should be:
```python
{
    token_id: {
        "LTP": float,  # Last traded price
        "High": float,  # Day high
        "Low": float    # Day low
    }
}
```

## Notes
- System runs continuously when integrated into your trading loop
- Add delays between API calls to avoid rate limiting
- Patterns are detected on 1-minute candles by default
- All times use Asia/Kolkata timezone
