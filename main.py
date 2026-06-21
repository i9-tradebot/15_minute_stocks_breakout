"""
Stock Breakout Monitor — TvDatafeed Edition
============================================
Scans all NSE symbols every 5 minutes using TvDatafeed.

Previous-day OHLCV is cached to  data/prev_day_YYYY-MM-DD.json
so restarts within the same day never re-fetch it.
"""

import json
import os
from datetime import datetime as dt, time as dtime
from time import sleep
from pathlib import Path

from TvDatafeed import TvDatafeed, Interval
from breakout_monitor import BreakoutMonitor
from level_calculator import (
    fetch_and_save_levels, load_levels, check_level_breakouts,
    load_level_breakouts, save_level_breakouts, cleanup_old_level_files,
)
from symbols import SYMBOLS
import config

TIMEZONE       = config.TIMEZONE
SCAN_INTERVAL  = 5 * 60
CANDLE_DELAY   = 0.5
WARMUP_CANDLES = config.WARMUP_CANDLES
DATA_DIR       = Path("data")


# ─── JSON cache helpers ──────────────────────────────────────────────────────

def cache_path(date) -> Path:
    """Returns  data/prev_day_YYYY-MM-DD.json  for the given date."""
    DATA_DIR.mkdir(exist_ok=True)
    return DATA_DIR / f"prev_day_{date}.json"


def load_prev_day_cache(date):
    """
    Load cached previous-day OHLCV from JSON if it exists for `date`.
    Returns dict  { 'NSE:RELIANCE': {'open':…,'high':…,'low':…,'close':…,'volume':…}, … }
    or None if not found.
    """
    path = cache_path(date)
    if path.exists():
        with open(path, "r") as f:
            data = json.load(f)
        print(f"[CACHE] Loaded prev-day data from {path.name}  "
              f"({len(data)} symbols — no fetch needed)")
        return data
    return None


def save_prev_day_cache(date, data):
    """
    Save previous-day OHLCV dict to  data/prev_day_YYYY-MM-DD.json
    data: { sym -> {'open','high','low','close','volume'} }
    """
    path = cache_path(date)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[CACHE] Saved prev-day data → {path.name}  ({len(data)} symbols)")


def cleanup_old_caches(keep_date):
    """Delete any prev_day_*.json files that are NOT for keep_date."""
    if not DATA_DIR.exists():
        return
    for p in DATA_DIR.glob("prev_day_*.json"):
        if f"prev_day_{keep_date}.json" not in p.name:
            p.unlink()
            print(f"[CACHE] Removed old cache: {p.name}")


# ─── data fetching ───────────────────────────────────────────────────────────

def parse_sym(full_sym):
    """'NSE:RELIANCE' → ('NSE', 'RELIANCE')"""
    parts = full_sym.split(":")
    return parts[0], parts[1]


def fetch_and_cache_prev_day(tv, symbols, trade_date):
    """
    Fetch 2 daily bars for every symbol, extract yesterday's OHLCV,
    save to JSON, and return the dict.
    Skips symbols that are already in a partial cache (resume on error).
    """
    path = cache_path(trade_date)

    # Support resuming a partial fetch (e.g., after crash mid-way)
    partial = {}
    if path.exists():
        with open(path, "r") as f:
            partial = json.load(f)

    remaining = [s for s in symbols if s not in partial]
    total     = len(symbols)

    if not remaining:
        print(f"[CACHE] All {total} symbols already cached for {trade_date}")
        return partial

    print(f"\n[FETCH] Fetching prev-day OHLCV for {len(remaining)} symbols "
          f"({total - len(remaining)} already cached) …")

    for i, sym in enumerate(remaining, 1):
        exchange, ticker = parse_sym(sym)
        try:
            df = tv.get_hist(ticker, exchange, Interval.in_daily, n_bars=2)
            if df is not None and len(df) >= 2:
                row = df.iloc[-2]          # yesterday's candle
                partial[sym] = {
                    "open"  : round(float(row["open"]),   2),
                    "high"  : round(float(row["high"]),   2),
                    "low"   : round(float(row["low"]),    2),
                    "close" : round(float(row["close"]),  2),
                    "volume": round(float(row["volume"]), 0),
                }
            else:
                print(f"  [WARN] {sym}: insufficient daily data")

            # Save partial progress every 20 symbols so restarts resume cleanly
            if i % 20 == 0:
                save_prev_day_cache(trade_date, partial)
                print(f"  [{i}/{len(remaining)}] partial save done …")

            sleep(CANDLE_DELAY)

        except Exception as e:
            print(f"  [WARN] {sym}: {e}")
            sleep(CANDLE_DELAY)

    save_prev_day_cache(trade_date, partial)
    print(f"[FETCH] Done — {len(partial)}/{total} symbols fetched.\n")
    return partial


def get_prev_day_data(tv, symbols, trade_date):
    """
    Returns prev-day OHLCV dict.
    Loads from JSON cache if today's file exists, otherwise fetches & saves.
    """
    cached = load_prev_day_cache(trade_date)
    if cached:
        # Fill any symbols missing from cache (new symbols added mid-day)
        missing = [s for s in symbols if s not in cached]
        if missing:
            print(f"[CACHE] {len(missing)} symbols missing from cache — fetching …")
            for sym in missing:
                exchange, ticker = parse_sym(sym)
                try:
                    df = tv.get_hist(ticker, exchange, Interval.in_daily, n_bars=2)
                    if df is not None and len(df) >= 2:
                        row = df.iloc[-2]
                        cached[sym] = {
                            "open"  : round(float(row["open"]),   2),
                            "high"  : round(float(row["high"]),   2),
                            "low"   : round(float(row["low"]),    2),
                            "close" : round(float(row["close"]),  2),
                            "volume": round(float(row["volume"]), 0),
                        }
                    sleep(CANDLE_DELAY)
                except Exception as e:
                    print(f"  [WARN] {sym}: {e}")
                    sleep(CANDLE_DELAY)
            save_prev_day_cache(trade_date, cached)
        return cached

    return fetch_and_cache_prev_day(tv, symbols, trade_date)


def build_prev_close_map(prev_day):
    """Extract just the close price from the full prev-day dict."""
    return {sym: v["close"] for sym, v in prev_day.items()}


def fetch_intraday_data(tv, symbols):
    """
    Fetch 1-min candles (WARMUP_CANDLES bars) for every symbol.
    Returns:
      live_data : { sym -> {"LTP", "High", "Low"} }
      hist_data : { sym -> DataFrame }
    """
    live_data = {}
    hist_data = {}
    today     = dt.now(TIMEZONE).date()

    for sym in symbols:
        exchange, ticker = parse_sym(sym)
        try:
            df = tv.get_hist(ticker, exchange, Interval.in_1_minute,
                             n_bars=WARMUP_CANDLES)
            if df is None or len(df) < 3:
                sleep(CANDLE_DELAY)
                continue

            # TvDatafeed returns naive UTC timestamps — convert to IST
            if df.index.tzinfo is None:
                df.index = df.index.tz_localize("UTC").tz_convert(TIMEZONE)

            df_today = df[df.index.date == today]
            ltp      = float(df.iloc[-1]["close"])
            day_high = float(df_today["high"].max()) if len(df_today) else ltp
            day_low  = float(df_today["low"].min())  if len(df_today) else ltp

            live_data[sym] = {"LTP": ltp, "High": day_high, "Low": day_low}
            hist_data[sym] = df
            sleep(CANDLE_DELAY)

        except Exception as e:
            print(f"  [WARN] intraday {sym}: {e}")
            sleep(CANDLE_DELAY)

    return live_data, hist_data


def market_open():
    now = dt.now(TIMEZONE).time()
    return dtime(9, 15) <= now <= dtime(15, 30)


def save_breakout_state(monitor, scan_time):
    """
    Persist the current breakout state so the Streamlit UI can read it.
    Saves to  data/breakout_state.json
    """
    DATA_DIR.mkdir(exist_ok=True)
    state = {
        "last_scan": scan_time.strftime("%Y-%m-%d %H:%M:%S"),
        "flagged"  : {},
    }
    for sym, d in monitor.flagged_stocks.items():
        entry = {
            "ltp"          : d.get("ltp"),
            "prev_close"   : d.get("prev_close"),
            "decline_pct"  : d.get("decline_pct"),
            "current_price": d.get("current_price"),
            "added_time"   : d["added_time"].strftime("%H:%M:%S"),
            "patterns"     : d.get("patterns", []),
        }
        state["flagged"][sym] = entry

    out_path = DATA_DIR / "breakout_state.json"
    with open(out_path, "w") as f:
        json.dump(state, f, indent=2)
    print(f"[STATE] Saved → {out_path}  ({len(state['flagged'])} flagged)")


# ─── main loop ───────────────────────────────────────────────────────────────

def run():
    print("=" * 60)
    print("  STOCK BREAKOUT MONITOR  (TvDatafeed + JSON Cache)")
    print(f"  Symbols   : {len(SYMBOLS)}")
    print(f"  Decline   : {config.DECLINE_MIN}% to {config.DECLINE_MAX}%")
    print(f"  Scan every: {SCAN_INTERVAL // 60} minutes")
    print(f"  Cache dir : {DATA_DIR.resolve()}")
    print("=" * 60)

    tv           = TvDatafeed()
    monitor      = BreakoutMonitor()
    today        = dt.now(TIMEZONE).date()

    # ── Step 1: load or fetch previous-day OHLCV ──────────────────────────
    prev_day     = get_prev_day_data(tv, SYMBOLS, today)
    prev_close   = build_prev_close_map(prev_day)
    cleanup_old_caches(today)

    print(f"[INFO] Prev-day close loaded for {len(prev_close)} symbols")

    # ── Level state (reset each day) ──────────────────────────────────────
    levels           = load_levels(today) or {}   # { sym -> level dict }
    level_triggered  = {}                          # { sym -> set of fired level names }
    level_breakouts  = load_level_breakouts()      # cumulative event list (today's file)

    # ── Main loop ──────────────────────────────────────────────────────────
    while True:
        now = dt.now(TIMEZONE)

        # New trading day → refresh everything
        if now.date() != today:
            today            = now.date()
            print(f"\n[INFO] New day ({today}) — refreshing caches …")
            prev_day         = get_prev_day_data(tv, SYMBOLS, today)
            prev_close       = build_prev_close_map(prev_day)
            cleanup_old_caches(today)
            cleanup_old_level_files(today)
            monitor          = BreakoutMonitor()
            levels           = {}
            level_triggered  = {}
            level_breakouts  = []

        if not market_open():
            label = "before open" if now.time() < dtime(9, 15) else "after close"
            print(f"[{now.strftime('%H:%M:%S')}] Market {label} — waiting …")
            sleep(60)
            continue

        print(f"\n{'='*60}")
        print(f"[{now.strftime('%H:%M:%S')}] Scan cycle started …")
        print(f"{'='*60}")

        # ── Step 2: fetch live 1-min data ──────────────────────────────────
        live_data, hist_data = fetch_intraday_data(tv, SYMBOLS)
        print(f"[INFO] Live data for {len(live_data)}/{len(SYMBOLS)} symbols")

        # ── Step 3: fetch 15-min levels once after 9:30 AM ─────────────────
        if not levels and now.time() >= dtime(9, 30):
            print("[LEVELS] First 15-min candle complete — fetching levels …")
            levels = fetch_and_save_levels(tv, SYMBOLS, today)

        # ── Step 4: flag stocks in -1.00% to -1.15% decline ───────────────
        monitor.scan_for_decline_stocks(SYMBOLS, live_data, prev_close)

        # ── Step 5: pattern detection on flagged stocks ────────────────────
        monitor.check_breakouts(hist_data)

        # ── Step 6: check level breakouts (all 211 symbols) ───────────────
        if levels:
            new_events = check_level_breakouts(live_data, levels, level_triggered)
            if new_events:
                level_breakouts.extend(new_events)
                save_level_breakouts(level_breakouts)
                print(f"[LEVELS] {len(new_events)} new level breakout(s) — "
                      f"{len(level_breakouts)} total today")

        # ── Step 7: summary + save state for UI ───────────────────────────
        monitor.get_summary()
        save_breakout_state(monitor, now)

        elapsed = (dt.now(TIMEZONE) - now).total_seconds()
        wait    = max(0, SCAN_INTERVAL - elapsed)
        print(f"[INFO] Scan took {elapsed:.0f}s — next in {wait:.0f}s …\n")
        sleep(wait)


if __name__ == "__main__":
    run()
