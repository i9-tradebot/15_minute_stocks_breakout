import pandas as pd
import numpy as np

def find_swing_points(df, window=5):
    """
    Identify swing highs and swing lows in the dataframe
    """
    swing_highs = []
    swing_lows = []
    
    for i in range(window, len(df) - window):
        high_slice = df['high'].iloc[i-window:i+window+1]
        low_slice = df['low'].iloc[i-window:i+window+1]
        
        if df['high'].iloc[i] == high_slice.max():
            swing_highs.append((i, df['high'].iloc[i]))
        
        if df['low'].iloc[i] == low_slice.min():
            swing_lows.append((i, df['low'].iloc[i]))
    
    return swing_highs, swing_lows


def detect_higher_high(df, lookback=20):
    """
    Detect higher high formation (bullish pattern)
    Returns True if recent price breaks above previous swing high
    """
    if len(df) < lookback:
        return False, None
    
    recent_data = df.tail(lookback).copy()
    swing_highs, _ = find_swing_points(recent_data, window=3)
    
    if len(swing_highs) < 2:
        return False, None
    
    for i in range(len(swing_highs) - 1):
        prev_high = swing_highs[i][1]
        curr_high = swing_highs[i + 1][1]
        
        if curr_high > prev_high:
            current_price = df.iloc[-1]['close']
            if current_price >= curr_high:
                return True, {
                    'pattern': 'Higher High',
                    'breakout_level': curr_high,
                    'current_price': current_price
                }
    
    return False, None


def detect_w_pattern(df, lookback=30):
    """
    Detect W-pattern (double bottom) breakout
    Looking for two similar lows with a resistance neckline break
    """
    if len(df) < lookback:
        return False, None
    
    recent_data = df.tail(lookback).copy()
    _, swing_lows = find_swing_points(recent_data, window=3)
    swing_highs, _ = find_swing_points(recent_data, window=3)
    
    if len(swing_lows) < 2 or len(swing_highs) < 1:
        return False, None
    
    for i in range(len(swing_lows) - 1):
        low1_idx, low1_price = swing_lows[i]
        low2_idx, low2_price = swing_lows[i + 1]
        
        price_diff = abs(low1_price - low2_price) / min(low1_price, low2_price)
        
        if price_diff < 0.02:
            highs_between = [h for h in swing_highs if low1_idx < h[0] < low2_idx]
            
            if highs_between:
                neckline = max([h[1] for h in highs_between])
                current_price = df.iloc[-1]['close']
                
                if current_price > neckline:
                    return True, {
                        'pattern': 'W-Pattern Break',
                        'breakout_level': neckline,
                        'current_price': current_price,
                        'lows': [low1_price, low2_price]
                    }
    
    return False, None


def detect_inverse_head_shoulders(df, lookback=40):
    """
    Detect Inverted Head and Shoulders pattern breakout
    Pattern: Low - Lower Low (Head) - Low with neckline resistance break
    """
    if len(df) < lookback:
        return False, None
    
    recent_data = df.tail(lookback).copy()
    _, swing_lows = find_swing_points(recent_data, window=4)
    swing_highs, _ = find_swing_points(recent_data, window=3)
    
    if len(swing_lows) < 3 or len(swing_highs) < 2:
        return False, None
    
    for i in range(len(swing_lows) - 2):
        left_shoulder_idx, left_shoulder = swing_lows[i]
        head_idx, head = swing_lows[i + 1]
        right_shoulder_idx, right_shoulder = swing_lows[i + 2]
        
        if head < left_shoulder and head < right_shoulder:
            shoulder_diff = abs(left_shoulder - right_shoulder) / min(left_shoulder, right_shoulder)
            
            if shoulder_diff < 0.03:
                highs_after_left = [h for h in swing_highs if left_shoulder_idx < h[0] < head_idx]
                highs_after_head = [h for h in swing_highs if head_idx < h[0] < right_shoulder_idx]
                
                if highs_after_left and highs_after_head:
                    neckline = np.mean([highs_after_left[-1][1], highs_after_head[-1][1]])
                    current_price = df.iloc[-1]['close']
                    
                    if current_price > neckline:
                        return True, {
                            'pattern': 'Inverted H&S Break',
                            'breakout_level': neckline,
                            'current_price': current_price,
                            'head': head,
                            'shoulders': [left_shoulder, right_shoulder]
                        }
    
    return False, None


def detect_swing_high_break_before_day_low(df, lookback=15):
    """
    Detect breakout of last swing high before the day's low was made
    This indicates a potential reversal from intraday low
    """
    if len(df) < lookback:
        return False, None
    
    day_low_idx = df['low'].idxmin()
    day_low = df.loc[day_low_idx, 'low']
    
    data_before_low = df.loc[:day_low_idx].tail(lookback)
    
    if len(data_before_low) < 5:
        return False, None
    
    swing_highs, _ = find_swing_points(data_before_low, window=2)
    
    if not swing_highs:
        return False, None
    
    last_swing_high = swing_highs[-1][1]
    current_price = df.iloc[-1]['close']
    
    if current_price > last_swing_high and df.iloc[-1]['close'] > df.iloc[-1]['open']:
        return True, {
            'pattern': 'Swing High Break (Pre-Day Low)',
            'breakout_level': last_swing_high,
            'current_price': current_price,
            'day_low': day_low
        }
    
    return False, None


def check_all_breakout_patterns(df, config):
    """
    Run all pattern detection algorithms and return detected patterns
    """
    patterns_detected = []
    
    hh_detected, hh_info = detect_higher_high(df, config.HIGHER_HIGH_LOOKBACK)
    if hh_detected:
        patterns_detected.append(hh_info)
    
    w_detected, w_info = detect_w_pattern(df, config.W_PATTERN_LOOKBACK)
    if w_detected:
        patterns_detected.append(w_info)
    
    ihs_detected, ihs_info = detect_inverse_head_shoulders(df, config.IHS_PATTERN_LOOKBACK)
    if ihs_detected:
        patterns_detected.append(ihs_info)
    
    swing_detected, swing_info = detect_swing_high_break_before_day_low(df, config.SWING_LOOKBACK)
    if swing_detected:
        patterns_detected.append(swing_info)
    
    return patterns_detected
