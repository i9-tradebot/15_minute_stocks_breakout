"""
Trend Level Calculator
======================
Computes first-15-minute candle levels for all symbols.

Levels saved once per day to:  data/trend_levels_YYYY-MM-DD.json
Breakout events appended to:   data/level_breakouts.json
"""
import json
from datetime import datetime as dt
from pathlib import Path
from time import sleep

import config

TIMEZONE     = config.TIMEZONE
DATA_DIR     = Path("data")
CANDLE_DELAY = 0.5

P1, P2, P3 = 13.06, 19.58, 26.11

LEVEL_NAMES_UP = ["up3"]
LEVEL_NAMES_DN = ["dn3"]


# ── file paths ───────────────────────────────────────────────────────────────

def levels_path(date) -> Path:
    DATA_DIR.mkdir(exist_ok=True)
    return DATA_DIR / f"trend_levels_{date}.json"


def breakouts_path() -> Path:
    DATA_DIR.mkdir(exist_ok=True)
    return DATA_DIR / "level_breakouts.json"


# ── level calculation ────────────────────────────────────────────────────────

def _compute_levels(first_high: float, first_low: float) -> dict:
    midpoint = (first_high + first_low) / 2
    return {
        "first_high": round(first_high, 2),
        "first_low" : round(first_low,  2),
        "midpoint"  : round(midpoint,   2),
        "up1"       : round(first_high * (1 + P1 / 100), 2),
        "up2"       : round(first_high * (1 + P2 / 100), 2),
        "up3"       : round(first_high * (1 + P3 / 100), 2),
        "dn1"       : round(first_low  * (1 - P1 / 100), 2),
        "dn2"       : round(first_low  * (1 - P2 / 100), 2),
        "dn3"       : round(first_low  * (1 - P3 / 100), 2),
    }


# ── load / fetch / save levels ───────────────────────────────────────────────

def load_levels(date) -> dict | None:
    """Return cached levels dict for the given date, or None."""
    path = levels_path(date)
    if path.exists():
        with open(path) as f:
            data = json.load(f)
        if data:
            print(f"[LEVELS] Loaded from {path.name} ({len(data)} symbols)")
            return data
    return None


def fetch_and_save_levels(tv, symbols: list, date) -> dict:
    """
    Fetch the first 15-min candle of today for each symbol,
    compute trend levels, save to JSON, return the full dict.
    Resumes partial fetches safely.
    """
    from TvDatafeed import Interval   # local import to avoid circular

    path = levels_path(date)
    existing: dict = {}
    if path.exists():
        with open(path) as f:
            existing = json.load(f)

    remaining = [s for s in symbols if s not in existing]
    if not remaining:
        print(f"[LEVELS] All {len(symbols)} symbols already have levels for {date}")
        return existing

    print(f"[LEVELS] Fetching 15-min first candle for "
          f"{len(remaining)}/{len(symbols)} symbols …")

    for i, sym in enumerate(remaining, 1):
        exchange, ticker = sym.split(":", 1)
        try:
            # n_bars=30 → ~2 trading days of 15-min bars; enough for fallback
            df = tv.get_hist(ticker, exchange, Interval.in_15_minute, n_bars=30)
            if df is None or df.empty:
                sleep(CANDLE_DELAY)
                continue

            # Convert naive UTC → IST
            if df.index.tzinfo is None:
                df.index = df.index.tz_localize("UTC").tz_convert(TIMEZONE)

            today_candles = df[[ts.date() == date for ts in df.index]]
            if today_candles.empty:
                # Today's data not yet available — fall back to the first candle
                # of the most recent available trading day
                last_date = df.index[-1].date()
                fallback  = df[[ts.date() == last_date for ts in df.index]]
                if fallback.empty:
                    sleep(CANDLE_DELAY)
                    continue
                first = fallback.iloc[0]
                print(f"  [LEVELS] {sym}: no today data — using {last_date} first candle")
            else:
                first = today_candles.iloc[0]

            lvls  = _compute_levels(float(first["high"]), float(first["low"]))
            existing[sym] = lvls

            # Partial save every 20 symbols so restarts resume cleanly
            if i % 20 == 0:
                with open(path, "w") as f:
                    json.dump(existing, f, indent=2)
                print(f"  [{i}/{len(remaining)}] partial save …")

            sleep(CANDLE_DELAY)

        except Exception as e:
            print(f"  [WARN] levels {sym}: {e}")
            sleep(CANDLE_DELAY)

    with open(path, "w") as f:
        json.dump(existing, f, indent=2)
    print(f"[LEVELS] Done — {len(existing)} levels saved → {path.name}")
    return existing


def cleanup_old_level_files(keep_date):
    """Remove trend_levels_*.json files from previous days."""
    if not DATA_DIR.exists():
        return
    for p in DATA_DIR.glob("trend_levels_*.json"):
        if f"trend_levels_{keep_date}.json" not in p.name:
            p.unlink()
            print(f"[LEVELS] Removed old: {p.name}")


# ── breakout detection ────────────────────────────────────────────────────────

def check_level_breakouts(live_data: dict, levels: dict, triggered: dict) -> list:
    """
    Compare each symbol's LTP against its trend levels.

    Args:
        live_data : { sym -> {"LTP": float, ...} }
        levels    : { sym -> level dict }
        triggered : mutable { sym -> set of level_names already alerted today }

    Returns list of NEW breakout event dicts (empty if none).
    Modifies `triggered` in-place.
    """
    now_str = dt.now(TIMEZONE).strftime("%H:%M:%S")
    new_events = []

    for sym, data in live_data.items():
        ltp = data.get("LTP")
        if ltp is None or sym not in levels:
            continue

        sym_levels   = levels[sym]
        sym_triggered = triggered.setdefault(sym, set())

        for name in LEVEL_NAMES_UP:
            price = sym_levels.get(name)
            if price and name not in sym_triggered and ltp >= price:
                sym_triggered.add(name)
                new_events.append({
                    "symbol"     : sym,
                    "level_name" : name,
                    "level_price": price,
                    "direction"  : "UP",
                    "ltp"        : round(ltp, 2),
                    "time"       : now_str,
                })
                print(f"  [LEVEL ▲] {sym}  {name}={price}  LTP={ltp:.2f}  {now_str}")

        for name in LEVEL_NAMES_DN:
            price = sym_levels.get(name)
            if price and name not in sym_triggered and ltp <= price:
                sym_triggered.add(name)
                new_events.append({
                    "symbol"     : sym,
                    "level_name" : name,
                    "level_price": price,
                    "direction"  : "DOWN",
                    "ltp"        : round(ltp, 2),
                    "time"       : now_str,
                })
                print(f"  [LEVEL ▼] {sym}  {name}={price}  LTP={ltp:.2f}  {now_str}")

    return new_events


# ── persist breakout events ───────────────────────────────────────────────────

def get_symbol_levels(tv, symbol: str, date) -> dict | None:
    """
    Get trend levels for a single symbol.
    1. Fast path: read from today's saved JSON (written by scanner after 9:30 AM).
    2. Fallback: fetch 15-min candles directly and compute on-the-fly.
    """
    from TvDatafeed import Interval

    # Fast path — JSON written by the background scanner
    cached = load_levels(date)
    if cached and symbol in cached:
        return cached[symbol]

    # Fallback: fetch directly from TvDatafeed
    exchange, ticker = symbol.split(":", 1)
    try:
        df = tv.get_hist(ticker, exchange, Interval.in_15_minute, n_bars=30)
        if df is None or df.empty:
            return None

        if df.index.tzinfo is None:
            df.index = df.index.tz_localize("UTC").tz_convert(TIMEZONE)

        today_candles = df[[ts.date() == date for ts in df.index]]
        if today_candles.empty:
            # Fall back to first candle of last available trading day
            last_date = df.index[-1].date()
            fallback  = df[[ts.date() == last_date for ts in df.index]]
            if fallback.empty:
                return None
            first = fallback.iloc[0]
        else:
            first = today_candles.iloc[0]

        return _compute_levels(float(first["high"]), float(first["low"]))
    except Exception:
        return None


def load_level_breakouts() -> list:
    path = breakouts_path()
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return []


def save_level_breakouts(all_events: list):
    path = breakouts_path()
    with open(path, "w") as f:
        json.dump(all_events, f, indent=2)
