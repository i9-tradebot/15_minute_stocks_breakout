import pytz

TIMEZONE       = pytz.timezone('Asia/Kolkata')
WARMUP_CANDLES = 375   # 375 min = full NSE day (9:15–15:30) of 1-min candles

DECLINE_MIN = -1.15
DECLINE_MAX = -1.00

HIGHER_HIGH_LOOKBACK = 20
W_PATTERN_LOOKBACK   = 30
IHS_PATTERN_LOOKBACK = 40
SWING_LOOKBACK       = 15
