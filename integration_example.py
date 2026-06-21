"""
Integration Example: How to use BreakoutMonitor with your existing trading system

This shows how to integrate the breakout detection system into your
existing code that fetches live data and TradingView candles.
"""

from datetime import datetime as dt
from time import sleep
from breakout_monitor import BreakoutMonitor
import config


def main_trading_loop():
    """
    Example main loop showing integration with your existing code
    
    Replace the placeholder functions with your actual:
    - get_live_data()
    - get_prev_close()
    - tv_data()
    """
    
    monitor = BreakoutMonitor()
    
    while True:
        curr_time = dt.now(config.TIMEZONE)
        print(f"\n{'='*60}")
        print(f"[{curr_time.strftime('%Y-%m-%d %H:%M:%S')}] Starting scan cycle...")
        print(f"{'='*60}")
        
        symbols = ["NSE:RELIANCE", "NSE:TCS", "NSE:INFY", "NSE:HDFCBANK", "NSE:TATAMOTORS"]
        token_list = [2885, 11536, 1594, 1333, 3456]
        
        live_data = get_live_data(token_list)
        prev_close = get_prev_close(token_list)
        
        monitor.scan_for_decline_stocks(symbols, token_list, live_data, prev_close)
        
        if monitor.monitored_symbols:
            print(f"\n[INFO] Checking {len(monitor.monitored_symbols)} stocks for breakouts...")
            monitor.check_breakouts(tv_data)
        else:
            print("[INFO] No stocks currently flagged for monitoring")
        
        monitor.get_summary()
        
        sleep_duration = 60
        print(f"\n[INFO] Sleeping for {sleep_duration} seconds before next scan...")
        sleep(sleep_duration)


def get_live_data(token_list):
    """
    Replace this with your actual live data fetching function
    
    Should return dict like:
    {
        token_id: {
            "LTP": float,
            "High": float,
            "Low": float
        }
    }
    """
    return {}


def get_prev_close(token_list):
    """
    Replace this with your actual previous close data function
    
    Should return dict like:
    {
        token_id: float  # previous close price
    }
    """
    return {}


def tv_data(symbol, interval, candles):
    """
    Replace this with your actual TradingView data fetching function
    
    Parameters:
        symbol: str - Symbol like "NSE:RELIANCE"
        interval: int - Timeframe in minutes (e.g., 1, 5, 15)
        candles: int - Number of candles to fetch
    
    Should return pandas DataFrame with:
        - Columns: open, high, low, close, volume
        - Index: DatetimeIndex
        - Optional: symbol column (will be dropped automatically)
    
    Example:
        df = tv_data("NSE:RELIANCE", 1, 100)
        # Returns 100 1-minute candles for RELIANCE
    """
    import pandas as pd
    return None


def single_scan_example():
    """
    Example: Single scan instead of continuous loop
    Perfect for testing or scheduled execution
    """
    monitor = BreakoutMonitor()
    
    symbols = ["NSE:RELIANCE", "NSE:TCS"]
    token_list = [2885, 11536]
    
    live_data = get_live_data(token_list)
    prev_close = get_prev_close(token_list)
    
    monitor.scan_for_decline_stocks(symbols, token_list, live_data, prev_close)
    
    if monitor.monitored_symbols:
        monitor.check_breakouts(tv_data)
        monitor.get_summary()
    else:
        print("No stocks meet the decline criteria")


def custom_config_example():
    """
    Example: Using custom configuration
    """
    import config
    
    config.DECLINE_MIN = -1.20
    config.DECLINE_MAX = -0.90
    config.WARMUP_CANDLES = 150
    config.HIGHER_HIGH_LOOKBACK = 25
    
    monitor = BreakoutMonitor()
    
    print(f"Custom Configuration:")
    print(f"  Decline Range: {config.DECLINE_MIN}% to {config.DECLINE_MAX}%")
    print(f"  Warmup Candles: {config.WARMUP_CANDLES}")
    print(f"  Higher High Lookback: {config.HIGHER_HIGH_LOOKBACK}")


if __name__ == "__main__":
    print("INTEGRATION EXAMPLES")
    print("="*60)
    print("\n1. For continuous monitoring, use: main_trading_loop()")
    print("2. For single scan, use: single_scan_example()")
    print("3. For custom config, see: custom_config_example()")
    print("\nReplace placeholder functions with your actual data sources!")
