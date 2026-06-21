"""
DATA SOURCES FOR STOCK BREAKOUT DETECTION SYSTEM
=================================================

Your system needs TWO types of data:

  1. LIVE DATA  → Real-time LTP, High, Low  (from Broker WebSocket/API)
  2. CANDLE DATA → Historical OHLCV bars    (from TradingView or Broker)

Choose ONE broker from below and plug it into breakout_monitor.py
"""

import pandas as pd
from datetime import datetime as dt
import config


# ===========================================================================
# OPTION 1: SHOONYA (FINVASIA) — Most Popular Free Option
# Free API, no brokerage charges, best for algo trading
# pip install NorenRestApiPy
# ===========================================================================

class ShoonyaDataSource:
    """
    Shoonya (Finvasia) - Free API
    Website: https://shoonya.com
    API Docs: https://github.com/Shoonya-Dev/ShoonyaApi-py

    Install: pip install NorenRestApiPy
    """
    def __init__(self):
        # pip install NorenRestApiPy
        from NorenRestApiPy.NorenApi import NorenApi
        self.api = NorenApi(
            host='https://api.shoonya.com/NorenWClient/',
            websocket='wss://api.shoonya.com/NorenWSClient/'
        )
    
    def login(self, userid, password, twofa, vendor_code, api_secret, imei):
        self.api.login(
            userid=userid,
            password=password,
            twoFA=twofa,
            vendor_code=vendor_code,
            api_secret=api_secret,
            imei=imei
        )
    
    def get_candle_data(self, symbol, interval=1, candles=100):
        """
        Fetch OHLCV candle data — replaces tv_data()
        interval: 1, 3, 5, 10, 15, 30, 60, 120, 240 (minutes)
        """
        from datetime import timedelta
        end_time = dt.now()
        start_time = end_time - timedelta(minutes=interval * candles * 2)
        
        ret = self.api.get_time_price_series(
            exchange='NSE',
            token=symbol,      # Use numeric token e.g. '22' for NIFTY
            starttime=start_time.strftime('%d-%m-%Y %H:%M:%S'),
            endtime=end_time.strftime('%d-%m-%Y %H:%M:%S'),
            interval=interval
        )
        
        if not ret:
            return None
        
        df = pd.DataFrame(ret)
        df = df.rename(columns={
            'into': 'open', 'inth': 'high',
            'intl': 'low', 'intc': 'close', 'intv': 'volume'
        })
        df['open']   = df['open'].astype(float)
        df['high']   = df['high'].astype(float)
        df['low']    = df['low'].astype(float)
        df['close']  = df['close'].astype(float)
        df['volume'] = df['volume'].astype(float)
        df.index = pd.to_datetime(df['time'])
        return df.tail(candles)
    
    def get_live_data(self, tokens):
        """
        Get real-time LTP, High, Low for a list of tokens
        Returns dict compatible with breakout_monitor
        """
        live = {}
        for token in tokens:
            quote = self.api.get_quotes(exchange='NSE', token=str(token))
            if quote:
                live[token] = {
                    'LTP':  float(quote.get('lp', 0)),
                    'High': float(quote.get('h',  0)),
                    'Low':  float(quote.get('l',  0)),
                }
        return live
    
    def get_prev_close(self, tokens):
        """Get previous close prices"""
        prev = {}
        for token in tokens:
            quote = self.api.get_quotes(exchange='NSE', token=str(token))
            if quote:
                prev[token] = float(quote.get('c', 0))
        return prev


# ===========================================================================
# OPTION 2: ZERODHA KITE — Most Popular Paid Broker
# Rs. 2000/month for live data
# pip install kiteconnect
# ===========================================================================

class ZerodhaDataSource:
    """
    Zerodha Kite Connect API
    Website: https://kite.trade
    API Docs: https://kite.trade/docs/connect/v3/

    Install: pip install kiteconnect
    """
    def __init__(self, api_key, access_token):
        from kiteconnect import KiteConnect
        self.kite = KiteConnect(api_key=api_key)
        self.kite.set_access_token(access_token)
    
    def get_candle_data(self, symbol, interval=1, candles=100):
        """
        Fetch OHLCV candle data — replaces tv_data()
        symbol format: 'NSE:RELIANCE'
        interval: minute, 3minute, 5minute, 15minute, 30minute, 60minute, day
        """
        from datetime import timedelta
        interval_map = {1: 'minute', 5: '5minute', 15: '15minute', 60: '60minute'}
        kite_interval = interval_map.get(interval, 'minute')
        
        end_date = dt.now()
        start_date = end_date - timedelta(days=3)  # fetch enough days
        
        exchange, tradingsymbol = symbol.split(':')
        
        instruments = self.kite.instruments(exchange)
        token = None
        for inst in instruments:
            if inst['tradingsymbol'] == tradingsymbol:
                token = inst['instrument_token']
                break
        
        if not token:
            return None
        
        data = self.kite.historical_data(token, start_date, end_date, kite_interval)
        df = pd.DataFrame(data)
        df = df.rename(columns={'date': 'datetime'})
        df.index = pd.to_datetime(df['datetime'])
        df = df[['open', 'high', 'low', 'close', 'volume']]
        return df.tail(candles)
    
    def get_live_data(self, tokens):
        """Get real-time LTP, High, Low"""
        quotes = self.kite.quote(tokens)
        live = {}
        for token_str, data in quotes.items():
            token_id = data['instrument_token']
            live[token_id] = {
                'LTP':  data['last_price'],
                'High': data['ohlc']['high'],
                'Low':  data['ohlc']['low'],
            }
        return live
    
    def get_prev_close(self, tokens):
        """Get previous close prices"""
        quotes = self.kite.quote(tokens)
        prev = {}
        for token_str, data in quotes.items():
            token_id = data['instrument_token']
            prev[token_id] = data['ohlc']['close']
        return prev


# ===========================================================================
# OPTION 3: ANGEL ONE (SMARTAPI) — Free API
# pip install smartapi-python
# ===========================================================================

class AngelOneDataSource:
    """
    AngelOne SmartAPI — Free to use
    Website: https://smartapi.angelbroking.com
    API Docs: https://smartapi.angelbroking.com/docs

    Install: pip install smartapi-python
    """
    def __init__(self, api_key, client_id, password, totp_secret):
        import pyotp
        from SmartApi import SmartConnect
        self.obj = SmartConnect(api_key=api_key)
        totp = pyotp.TOTP(totp_secret).now()
        data = self.obj.generateSession(client_id, password, totp)
        self.auth_token = data['data']['jwtToken']
        self.refresh_token = data['data']['refreshToken']
        self.obj.generateToken(self.refresh_token)
    
    def get_candle_data(self, symbol, interval=1, candles=100):
        """
        Fetch OHLCV candle data — replaces tv_data()
        symbol: token number as string e.g. '2885' for RELIANCE
        interval: ONE_MINUTE, FIVE_MINUTE, FIFTEEN_MINUTE, ONE_DAY
        """
        from datetime import timedelta
        interval_map = {
            1: 'ONE_MINUTE', 5: 'FIVE_MINUTE',
            15: 'FIFTEEN_MINUTE', 60: 'ONE_HOUR'
        }
        angel_interval = interval_map.get(interval, 'ONE_MINUTE')
        
        end_time = dt.now()
        start_time = end_time - timedelta(days=5)
        
        params = {
            "exchange": "NSE",
            "symboltoken": symbol,
            "interval": angel_interval,
            "fromdate": start_time.strftime("%Y-%m-%d %H:%M"),
            "todate": end_time.strftime("%Y-%m-%d %H:%M")
        }
        
        res = self.obj.getCandleData(params)
        if not res or not res.get('data'):
            return None
        
        df = pd.DataFrame(res['data'],
                          columns=['datetime', 'open', 'high', 'low', 'close', 'volume'])
        df.index = pd.to_datetime(df['datetime'])
        df = df[['open', 'high', 'low', 'close', 'volume']]
        return df.tail(candles)
    
    def get_live_data(self, tokens):
        """Get real-time LTP, High, Low"""
        live = {}
        for token in tokens:
            quote = self.obj.ltpData("NSE", "", str(token))
            if quote and quote.get('data'):
                d = quote['data']
                live[token] = {
                    'LTP':  d.get('ltp', 0),
                    'High': d.get('high', 0),
                    'Low':  d.get('low', 0),
                }
        return live
    
    def get_prev_close(self, tokens):
        """Get previous close prices"""
        prev = {}
        for token in tokens:
            quote = self.obj.ltpData("NSE", "", str(token))
            if quote and quote.get('data'):
                prev[token] = quote['data'].get('close', 0)
        return prev


# ===========================================================================
# OPTION 4: TRADINGVIEW (tvDatafeed) — Free, No Broker Needed
# Only for candle data, NO live data
# pip install tvDatafeed
# ===========================================================================

class TradingViewDataSource:
    """
    TradingView via tvDatafeed — FREE historical/candle data
    Website: https://github.com/StreamAlpha/tvdatafeed
    NO live data — combine with a broker for LTP

    Install: pip install tvDatafeed
    """
    def __init__(self, tv_username=None, tv_password=None):
        # Anonymous access works for most NSE symbols
        from tvDatafeed import TvDatafeed, Interval
        self.tv = TvDatafeed(tv_username, tv_password)
        self.Interval = Interval
    
    def get_candle_data(self, symbol, interval=1, candles=100):
        """
        Fetch OHLCV candle data — replaces tv_data()
        symbol format: 'NSE:RELIANCE'  (exchange:symbol)
        """
        interval_map = {
            1: self.Interval.in_1_minute,
            5: self.Interval.in_5_minute,
            15: self.Interval.in_15_minute,
            60: self.Interval.in_1_hour,
        }
        tv_interval = interval_map.get(interval, self.Interval.in_1_minute)
        
        parts = symbol.split(':')
        exchange = parts[0]
        sym = parts[1].replace('NSE:', '')
        
        df = self.tv.get_hist(
            symbol=sym,
            exchange=exchange,
            interval=tv_interval,
            n_bars=candles
        )
        return df


# ===========================================================================
# FULL INTEGRATION EXAMPLE
# ===========================================================================

def run_with_shoonya():
    """
    Full example using Shoonya (recommended — free)
    """
    from breakout_monitor import BreakoutMonitor
    
    ds = ShoonyaDataSource()
    ds.login(
        userid='YOUR_USER_ID',
        password='YOUR_PASSWORD',
        twofa='YOUR_TOTP_OR_DOB',       # e.g. '123456' from authenticator app
        vendor_code='YOUR_VENDOR_CODE',
        api_secret='YOUR_API_SECRET',
        imei='abc1234'
    )
    
    # Your symbol list with their tokens
    symbols    = ["NSE:RELIANCE", "NSE:TCS", "NSE:INFY", "NSE:HDFCBANK"]
    token_list = [2885, 11536, 1594, 1333]    # Shoonya tokens for each symbol
    
    monitor = BreakoutMonitor()
    
    while True:
        live_data  = ds.get_live_data(token_list)
        prev_close = ds.get_prev_close(token_list)
        
        monitor.scan_for_decline_stocks(symbols, token_list, live_data, prev_close)
        
        if monitor.monitored_symbols:
            monitor.check_breakouts(ds.get_candle_data)
        
        monitor.get_summary()
        
        from time import sleep
        sleep(60)


def run_with_zerodha():
    """
    Full example using Zerodha Kite
    """
    from breakout_monitor import BreakoutMonitor
    
    ds = ZerodhaDataSource(
        api_key='YOUR_API_KEY',
        access_token='YOUR_ACCESS_TOKEN'    # generated fresh each day
    )
    
    symbols    = ["NSE:RELIANCE", "NSE:TCS"]
    token_list = [738561, 2953217]           # Kite instrument tokens
    
    monitor = BreakoutMonitor()
    
    live_data  = ds.get_live_data([f"NSE:RELIANCE", "NSE:TCS"])
    prev_close = ds.get_prev_close([f"NSE:RELIANCE", "NSE:TCS"])
    
    monitor.scan_for_decline_stocks(symbols, token_list, live_data, prev_close)
    monitor.check_breakouts(ds.get_candle_data)
    monitor.get_summary()


def run_with_angelone():
    """
    Full example using AngelOne SmartAPI
    """
    from breakout_monitor import BreakoutMonitor
    
    ds = AngelOneDataSource(
        api_key='YOUR_API_KEY',
        client_id='YOUR_CLIENT_ID',
        password='YOUR_PIN',
        totp_secret='YOUR_TOTP_SECRET'
    )
    
    symbols    = ["NSE:RELIANCE", "NSE:TCS"]
    token_list = [2885, 11536]              # Angel token numbers
    
    monitor = BreakoutMonitor()
    
    live_data  = ds.get_live_data(token_list)
    prev_close = ds.get_prev_close(token_list)
    
    monitor.scan_for_decline_stocks(symbols, token_list, live_data, prev_close)
    monitor.check_breakouts(ds.get_candle_data)
    monitor.get_summary()


if __name__ == "__main__":
    print("""
==================================================
  DATA SOURCES FOR STOCK BREAKOUT SYSTEM
==================================================

Choose a broker API to fetch data:

  BROKER          | COST    | LIVE DATA | CANDLE DATA
  ----------------|---------|-----------|-------------
  Shoonya/Finvasia| Free    | YES       | YES         ← Recommended
  AngelOne        | Free    | YES       | YES
  Zerodha Kite    | ₹2000/mo| YES       | YES
  TradingView     | Free    | NO        | YES only

HOW TO START:
  1. Sign up with your chosen broker
  2. Get API credentials from their developer portal
  3. Install the library:
       Shoonya  : pip install NorenRestApiPy
       AngelOne : pip install smartapi-python pyotp
       Zerodha  : pip install kiteconnect
       TradingView: pip install tvDatafeed
  4. Use the matching run_with_*() function above
  5. Plug your real symbols and tokens into the loop

""")
