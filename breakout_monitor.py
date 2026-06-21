from datetime import datetime as dt
from time import sleep
import pandas as pd
import config
from pattern_detector import check_all_breakout_patterns


class BreakoutMonitor:
    def __init__(self):
        self.monitored_symbols = set()
        self.flagged_stocks    = {}

    def check_price_decline(self, ltp, prev_close):
        if not prev_close or prev_close == 0:
            return False, 0.0
        pct = round((ltp - prev_close) / prev_close * 100, 2)
        return (config.DECLINE_MIN <= pct <= config.DECLINE_MAX), pct

    def add_to_watchlist(self, symbol, ltp, prev_close, pct):
        if symbol not in self.monitored_symbols:
            self.monitored_symbols.add(symbol)
            self.flagged_stocks[symbol] = {
                'added_time' : dt.now(config.TIMEZONE),
                'ltp'        : ltp,
                'prev_close' : prev_close,
                'decline_pct': pct,
                'patterns'   : [],
            }
            print(f"\n{'='*60}")
            print(f"[FLAGGED] {symbol} added to watchlist")
            print(f"  LTP: {ltp}  |  Prev Close: {prev_close}  |  Chg: {pct}%")
            print(f"  Time: {dt.now(config.TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'='*60}")
            return True
        return False

    def scan_for_decline_stocks(self, symbols, live_data, prev_close_map):
        """
        live_data     : { sym -> {"LTP", "High", "Low"} }
        prev_close_map: { sym -> float }
        """
        for sym in symbols:
            d = live_data.get(sym)
            if not d:
                continue
            ltp    = d.get("LTP")
            yclose = prev_close_map.get(sym)
            if not ltp or not yclose:
                continue
            ok, pct = self.check_price_decline(ltp, yclose)
            if ok:
                self.add_to_watchlist(sym, ltp, yclose, pct)

    def check_breakouts(self, hist_data):
        """
        hist_data: { sym -> DataFrame (sorted 1-min OHLCV) }
        """
        if not self.monitored_symbols:
            return
        now = dt.now(config.TIMEZONE)
        print(f"\n[{now.strftime('%H:%M:%S')}] Checking breakouts for "
              f"{len(self.monitored_symbols)} symbols...")

        for sym in list(self.monitored_symbols):
            df = hist_data.get(sym)
            if df is None or len(df) < 3:
                print(f"  {sym} -> NO DATA")
                continue

            hist          = df.drop(columns=['symbol'], errors='ignore').copy().sort_index()
            current_price = hist.iloc[-1]['close']
            patterns      = check_all_breakout_patterns(hist, config)

            if patterns:
                print(f"\n{'*'*60}")
                print(f"[BREAKOUT] {sym}  |  Price: {current_price:.2f}"
                      f"  |  Decline: {self.flagged_stocks[sym]['decline_pct']}%")
                print(f"  Time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
                for p in patterns:
                    print(f"  Pattern : {p['pattern']}")
                    print(f"  Level   : {p['breakout_level']:.2f}  →  "
                          f"Price: {p['current_price']:.2f}")
                    if 'lows'     in p: print(f"  Lows    : {[f'{v:.2f}' for v in p['lows']]}")
                    if 'head'     in p: print(f"  Head    : {p['head']:.2f}")
                    if 'shoulders'in p: print(f"  Shoulders: {[f'{v:.2f}' for v in p['shoulders']]}")
                    if 'day_low'  in p: print(f"  Day Low : {p['day_low']:.2f}")
                print(f"{'*'*60}\n")

                self.flagged_stocks[sym]['patterns']      = patterns
                self.flagged_stocks[sym]['last_check']    = now
                self.flagged_stocks[sym]['current_price'] = current_price
            else:
                print(f"  {sym} -> {current_price:.2f} | no breakout yet")
                self.flagged_stocks[sym]['patterns']      = []
                self.flagged_stocks[sym]['last_check']    = now
                self.flagged_stocks[sym]['current_price'] = current_price

    def get_summary(self):
        print(f"\n{'='*60}")
        print(f"SUMMARY  |  Watching: {len(self.monitored_symbols)}")
        hits = [(s, d) for s, d in self.flagged_stocks.items() if d.get('patterns')]
        print(f"Breakouts Detected: {len(hits)}")
        for sym, d in hits:
            names = [p['pattern'] for p in d['patterns']]
            print(f"  {sym}: {', '.join(names)}")
        print(f"{'='*60}\n")
