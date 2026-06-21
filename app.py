"""
Stock Breakout Monitor — Streamlit UI
"""

import json
import time
from datetime import datetime as dt
from pathlib import Path

import pandas as pd
import streamlit as st

from TvDatafeed import TvDatafeed, Interval
from chart_utils import build_chart, calc_prev_day_poc
from level_calculator import load_level_breakouts as _load_lb, load_levels, get_symbol_levels
from symbols import SYMBOLS
import config

# ── page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Stock Breakout Monitor",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stAppViewContainer"]  { background:#0e1117; }
[data-testid="block-container"]     { padding-top:0.6rem; }
.metric-card {
    background:#161b22; border-radius:8px;
    padding:10px 16px; text-align:center;
}
.tag-breakout { background:#1b3a2f; color:#26a69a;
    border-radius:4px; padding:2px 7px; font-size:12px; font-weight:600; }
.tag-watch    { background:#2a2a1a; color:#ffc107;
    border-radius:4px; padding:2px 7px; font-size:12px; }
.sym-btn { cursor:pointer; }

/* level breakout table */
.lvl-table { width:100%; border-collapse:collapse; font-size:13px; }
.lvl-table th { color:#888; font-weight:500; padding:4px 10px;
    border-bottom:1px solid #222; text-align:left; }
.lvl-table td { padding:5px 10px; border-bottom:1px solid #1a1e2a; }
.lvl-table tr:hover td { background:#161b22; }
.dir-up   { color:#26a69a; font-weight:700; }
.dir-down { color:#ef5350; font-weight:700; }
.lvl-name { background:#1a2035; color:#90caf9; border-radius:3px;
    padding:1px 6px; font-size:11px; font-family:monospace; }
</style>
""", unsafe_allow_html=True)

# ── constants ─────────────────────────────────────────────────────────────────
STATE_FILE    = Path("data/breakout_state.json")
PREV_DAY_DIR  = Path("data")
CHART_FETCH   = 375   # bars to fetch  (375 × 3 min ≈ 3 full trading days)
CHART_DISPLAY = 125   # bars to display (125 × 3 min = 375 min = 1 full day)
TIMEZONE      = config.TIMEZONE

SYM_CLEAN     = [s.replace("NSE:", "") for s in SYMBOLS]   # display names


# ── helpers ───────────────────────────────────────────────────────────────────

@st.cache_resource
def get_tv():
    return TvDatafeed()


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_scan": None, "flagged": {}}


def load_prev_day(symbol: str) -> dict | None:
    today = dt.now(TIMEZONE).date()
    path  = PREV_DAY_DIR / f"prev_day_{today}.json"
    if path.exists():
        try:
            with open(path) as f:
                return json.load(f).get(symbol)
        except Exception:
            pass
    return None


@st.cache_data(ttl=300)
def fetch_chart_data(symbol: str, candles: int = CHART_FETCH):
    tv = get_tv()
    exch, ticker = symbol.split(":", 1)
    try:
        df = tv.get_hist(ticker, exch, Interval.in_3_minute, n_bars=candles)
        if df is not None:
            df = df.drop(columns=["symbol"], errors="ignore").sort_index()
            # TvDatafeed returns naive UTC timestamps — convert to IST
            if df.index.tzinfo is None:
                df.index = df.index.tz_localize("UTC").tz_convert(TIMEZONE)
            else:
                df.index = df.index.tz_convert(TIMEZONE)
        return df
    except Exception as e:
        st.error(f"Failed to fetch data for {symbol}: {e}")
        return None


def pct_html(pct: float) -> str:
    if pct >= 0:
        return f'<span style="color:#26a69a">▲ {pct:+.2f}%</span>'
    return f'<span style="color:#ef5350">▼ {pct:.2f}%</span>'


@st.cache_data(ttl=900)
def load_today_levels(symbol: str) -> dict | None:
    """
    Get trend levels for a symbol.
    1. Fast path: today's JSON written by the background scanner.
    2. Fallback: fetch 15-min candles from TvDatafeed and compute on-the-fly.
    Cached for 15 min so the chart doesn't re-fetch on every page interaction.
    """
    try:
        today = dt.now(TIMEZONE).date()
        tv    = get_tv()
        return get_symbol_levels(tv, symbol, today)
    except Exception:
        return None


def load_level_breakouts_ui() -> list:
    """Load today's level breakout events for the UI (safe — returns [] on error)."""
    try:
        return _load_lb()
    except Exception:
        return []


def render_level_table(events: list):
    """Render the level breakouts as a compact HTML table."""
    if not events:
        st.caption("No level breakouts yet today. Levels are computed after 9:30 AM IST.")
        return

    # newest first
    rows = list(reversed(events))
    html = ['<table class="lvl-table">',
            '<tr><th>Time</th><th>Symbol</th><th>Dir</th>'
            '<th>Level</th><th>Level Price ₹</th><th>LTP ₹</th></tr>']

    for r in rows:
        sym   = r["symbol"].replace("NSE:", "")
        d     = r["direction"]
        arrow = '<span class="dir-up">▲ UP</span>' if d == "UP" else '<span class="dir-down">▼ DOWN</span>'
        lname = f'<span class="lvl-name">{r["level_name"]}</span>'
        html.append(
            f'<tr>'
            f'<td style="color:#888">{r["time"]}</td>'
            f'<td><b style="color:#e0e0e0">{sym}</b></td>'
            f'<td>{arrow}</td>'
            f'<td>{lname}</td>'
            f'<td style="color:#ccc">{r["level_price"]:,.2f}</td>'
            f'<td style="color:#fff;font-weight:600">{r["ltp"]:,.2f}</td>'
            f'</tr>'
        )

    html.append("</table>")
    st.markdown("\n".join(html), unsafe_allow_html=True)


# ── main UI ───────────────────────────────────────────────────────────────────

def main():
    state   = load_state()
    flagged = state.get("flagged", {})
    last_scan = state.get("last_scan") or "Waiting for market hours…"

    # ── top header ─────────────────────────────────────────────────────────────
    h1, h2, h3 = st.columns([3, 1.5, 1.5])
    with h1:
        st.markdown("## 📈 Stock Breakout Monitor")
    with h2:
        st.markdown(
            f'<div class="metric-card"><small>Last Scan</small><br>'
            f'<b style="font-size:13px">{last_scan}</b></div>',
            unsafe_allow_html=True,
        )
    with h3:
        n_flag  = len(flagged)
        n_break = sum(1 for d in flagged.values() if d.get("patterns"))
        st.markdown(
            f'<div class="metric-card"><small>Flagged / Breakouts</small><br>'
            f'<b style="color:#ffc107;font-size:18px">{n_flag}</b>'
            f' &nbsp;/&nbsp; '
            f'<b style="color:#26a69a;font-size:18px">{n_break}</b></div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ── level breakout table ───────────────────────────────────────────────────
    level_events = load_level_breakouts_ui()
    n_lvl = len(level_events)
    lvl_title = (
        f"📊 First-15-min Level Breakouts &nbsp;"
        f'<span style="color:#90caf9;font-size:13px">({n_lvl} today)</span>'
        if n_lvl else
        "📊 First-15-min Level Breakouts"
    )
    with st.expander(lvl_title, expanded=n_lvl > 0):
        if level_events:
            up_count   = sum(1 for e in level_events if e["direction"] == "UP")
            down_count = sum(1 for e in level_events if e["direction"] == "DOWN")
            c1, c2, c3 = st.columns([1, 1, 4])
            with c1:
                st.markdown(
                    f'<div class="metric-card">'
                    f'<small>▲ Upside breaks</small><br>'
                    f'<b style="color:#26a69a;font-size:20px">{up_count}</b></div>',
                    unsafe_allow_html=True,
                )
            with c2:
                st.markdown(
                    f'<div class="metric-card">'
                    f'<small>▼ Downside breaks</small><br>'
                    f'<b style="color:#ef5350;font-size:20px">{down_count}</b></div>',
                    unsafe_allow_html=True,
                )
            with c3:
                st.caption(
                    "Levels: **first_high / first_low** from 9:15–9:30 candle  ·  "
                    "**up1/up2/up3** (+13.06% / +19.58% / +26.11% from first_high)  ·  "
                    "**dn1/dn2/dn3** (−13.06% / −19.58% / −26.11% from first_low)  ·  "
                    "One alert per level per symbol per day"
                )
            st.markdown("<br>", unsafe_allow_html=True)
        render_level_table(level_events)

    st.markdown("---")

    # ── symbol picker (always visible, all 211 symbols) ────────────────────────
    pick_col, info_col = st.columns([2, 3])
    with pick_col:
        st.markdown("#### 🔎 Select any symbol to view chart")
        # group: breakouts first, then flagged, then rest
        breakout_syms = [s for s, d in flagged.items() if d.get("patterns")]
        watching_syms = [s for s in flagged if s not in breakout_syms]
        other_syms    = [s for s in SYMBOLS if s not in flagged]

        options_display = []
        options_map     = {}   # display → full symbol

        if breakout_syms:
            options_display.append("── 🟢 BREAKOUTS ──")
            for s in breakout_syms:
                label = f"🟢  {s.replace('NSE:','')}"
                options_display.append(label)
                options_map[label] = s

        if watching_syms:
            options_display.append("── ⏳ FLAGGED (watching) ──")
            for s in watching_syms:
                label = f"⏳  {s.replace('NSE:','')}"
                options_display.append(label)
                options_map[label] = s

        options_display.append("── ALL SYMBOLS ──")
        for s in other_syms:
            label = s.replace("NSE:", "")
            options_display.append(label)
            options_map[label] = s

        selected_display = st.selectbox(
            "Symbol",
            ["— Choose a symbol —"] + options_display,
            label_visibility="collapsed",
        )

    with info_col:
        if breakout_syms:
            st.markdown("#### 🟢 Active Breakouts")
            cards = st.columns(min(4, len(breakout_syms)))
            for i, sym in enumerate(breakout_syms[:4]):
                d = flagged[sym]
                pnames = " · ".join(p["pattern"] for p in d.get("patterns", []))
                with cards[i]:
                    st.markdown(
                        f'<div class="metric-card">'
                        f'<b style="color:#26a69a">{sym.replace("NSE:","")}</b><br>'
                        f'{pct_html(d.get("decline_pct", 0))}<br>'
                        f'<small style="color:#aaa">{pnames}</small></div>',
                        unsafe_allow_html=True,
                    )
        elif flagged:
            st.markdown("#### ⏳ Flagged — no breakout pattern yet")
            st.caption(
                f"{len(flagged)} stocks are in the -1.00% to -1.15% decline zone. "
                "Scanner checking for breakout patterns."
            )
        else:
            st.markdown("#### ℹ️ Scanner Status")
            st.info(
                "No stocks flagged yet.  \n"
                "The scanner runs **every 5 minutes** between **9:15 – 15:30 IST** "
                "and flags stocks down -1.00% to -1.15% from previous close.",
                icon="🕐",
            )

    st.markdown("---")

    # ── chart section ─────────────────────────────────────────────────────────
    # resolve selected symbol
    chart_sym = None
    if selected_display and selected_display not in (
        "— Choose a symbol —",
        "── 🟢 BREAKOUTS ──",
        "── ⏳ FLAGGED (watching) ──",
        "── ALL SYMBOLS ──",
    ):
        chart_sym = options_map.get(selected_display) or f"NSE:{selected_display}"

    if chart_sym is None:
        st.markdown(
            '<p style="color:#555;text-align:center;padding:40px 0">'
            "Select a symbol above to view the candlestick chart with "
            "EMA 26 · VWAP · Volume Profile</p>",
            unsafe_allow_html=True,
        )
    else:
        sym_clean = chart_sym.replace("NSE:", "")
        sym_data  = flagged.get(chart_sym, {})

        # ── info strip ────────────────────────────────────────────────────────
        st.markdown(f"### 📊 {sym_clean}  ·  3-min  ·  {CHART_DISPLAY} bars (full day)")

        ltp      = sym_data.get("current_price") or sym_data.get("ltp")
        pct      = sym_data.get("decline_pct", 0)
        patterns = sym_data.get("patterns", [])

        prev_data = load_prev_day(chart_sym)
        prev_c    = prev_data.get("close") if prev_data else None
        prev_poc  = calc_prev_day_poc(prev_data)

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("LTP", f"₹{ltp:,.2f}" if ltp else "—")
        with m2:
            if ltp and prev_c:
                st.metric("Change", f"{pct:+.2f}%" if pct else "—", delta_color="inverse")
            else:
                st.metric("Change", "—")
        with m3:
            st.metric("Prev Close", f"₹{prev_c:,.2f}" if prev_c else "—")
        with m4:
            if patterns:
                st.metric("Status", "🟢 BREAKOUT")
            elif chart_sym in flagged:
                st.metric("Status", "⏳ Flagged")
            else:
                st.metric("Status", "📊 Chart only")

        # pattern alerts
        for p in patterns:
            st.success(
                f"**{p['pattern']}** — Breakout level: ₹{p.get('breakout_level', 0):.2f}  "
                f"·  Current: ₹{p.get('current_price', 0):.2f}"
            )

        # ── fetch + render chart ──────────────────────────────────────────────
        with st.spinner(f"Fetching {CHART_FETCH} × 3-min candles for {sym_clean} …"):
            df = fetch_chart_data(chart_sym, CHART_FETCH)

        sym_levels = load_today_levels(chart_sym)   # None if levels not yet computed

        if df is not None and not df.empty:
            # Show only last CHART_DISPLAY bars (= 1 full trading day of 3-min candles)
            df_display = df.iloc[-CHART_DISPLAY:]
            fig = build_chart(df_display, sym_clean, prev_day_poc=prev_poc,
                              trend_levels=sym_levels)
            st.plotly_chart(fig, use_container_width=True, config={
                "displayModeBar": True,
                "displaylogo": False,
                "modeBarButtonsToRemove": ["lasso2d", "select2d"],
            })
        else:
            st.warning(f"No data returned for {sym_clean}. Market may be closed.")

    # ── footer ────────────────────────────────────────────────────────────────
    st.markdown("---")
    fc1, fc2, fc3 = st.columns([1, 1, 4])
    with fc1:
        auto_ref = st.checkbox("Auto-refresh (60s)", value=True, key="auto_refresh")
    with fc2:
        if st.button("🔄 Refresh now"):
            st.cache_data.clear()
            st.rerun()
    with fc3:
        st.caption(
            "Scanner: **-1.15% – -1.00%** decline  ·  "
            "Patterns: Higher High · W-Pattern · Inverted H&S · Swing High  ·  "
            "Chart: EMA 26 · VWAP · Volume Profile (today POC 🟠 · prev-day POC 🟣)"
        )

    if auto_ref:
        time.sleep(60)
        st.cache_data.clear()
        st.rerun()


if __name__ == "__main__":
    main()
