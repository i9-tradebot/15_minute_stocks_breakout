"""
Chart utilities: EMA, VWAP, Volume Profile, Plotly figure builder
"""
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# ── Indicators ────────────────────────────────────────────────────────────────

def calc_ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def calc_vwap(df: pd.DataFrame) -> pd.Series:
    """VWAP resets each trading day."""
    tp   = (df["high"] + df["low"] + df["close"]) / 3
    tpv  = tp * df["volume"]
    # .normalize() works for both tz-aware and naive DatetimeIndex
    date = df.index.normalize()

    cum_tpv = []
    cum_vol = []
    last_date = None
    running_tpv = 0.0
    running_vol = 0.0

    for i in range(len(df)):
        d = date[i]
        if d != last_date:
            running_tpv = 0.0
            running_vol = 0.0
            last_date   = d
        running_tpv += tpv.iloc[i]
        running_vol += df["volume"].iloc[i]
        cum_tpv.append(running_tpv)
        cum_vol.append(running_vol)

    vwap = pd.Series(
        [t / v if v > 0 else np.nan for t, v in zip(cum_tpv, cum_vol)],
        index=df.index,
    )
    return vwap


def calc_volume_profile(df: pd.DataFrame, bins: int = 60):
    """
    Compute volume profile for df.
    Returns:
        price_levels  : ndarray of bin centres
        volumes       : ndarray of total volume per bin
        poc_price     : float – price of the Point of Control
    """
    lo = df["low"].min()
    hi = df["high"].max()
    if hi <= lo:
        return np.array([lo]), np.array([df["volume"].sum()]), lo

    edges        = np.linspace(lo, hi, bins + 1)
    bin_centres  = (edges[:-1] + edges[1:]) / 2
    bin_width    = edges[1] - edges[0]
    volumes      = np.zeros(bins)

    for _, row in df.iterrows():
        mask = (bin_centres >= row["low"] - bin_width * 0.5) & \
               (bin_centres <= row["high"] + bin_width * 0.5)
        n = mask.sum()
        if n > 0:
            volumes[mask] += row["volume"] / n

    poc_idx   = int(np.argmax(volumes))
    poc_price = float(bin_centres[poc_idx])
    return bin_centres, volumes, poc_price


def calc_prev_day_poc(prev_day_ohlcv: dict) -> float | None:
    """
    Approximate prev-day POC from the prev-day OHLCV stored in JSON cache.
    Uses the close price as a proxy for the POC (actual intraday data not stored).
    Returns the close price to be shown as prev-day POC line.
    """
    if prev_day_ohlcv and "close" in prev_day_ohlcv:
        return float(prev_day_ohlcv["close"])
    return None


# ── Figure builder ────────────────────────────────────────────────────────────

def build_chart(df: pd.DataFrame, symbol: str,
                prev_day_poc: float = None,
                trend_levels: dict = None) -> go.Figure:
    """
    Build interactive Plotly chart:
      Col-1 row-1 : Candlestick + EMA26 + VWAP + prev-day POC dashed line
      Col-1 row-2 : Volume bars
      Col-2 row-1 : Today's Volume Profile (horizontal, price-aligned)
    """
    df = df.copy().sort_index()

    # ── compute indicators ───────────────────────────────────────────────────
    df["ema26"] = calc_ema(df["close"], 26)
    df["vwap"]  = calc_vwap(df)

    today      = df.index[-1].date()
    # .date works for both tz-aware and naive; compare directly
    df_today   = df[[ts.date() == today for ts in df.index]]
    if df_today.empty:
        df_today = df

    price_levels, volumes, today_poc = calc_volume_profile(df_today, bins=60)
    max_vol = float(volumes.max()) if volumes.max() > 0 else 1.0

    # ── colour helpers ───────────────────────────────────────────────────────
    candle_colors = [
        "#26a69a" if c >= o else "#ef5350"
        for c, o in zip(df["close"], df["open"])
    ]

    vp_colors = []
    poc_bin_hw = (price_levels[1] - price_levels[0]) / 2 if len(price_levels) > 1 else 0
    for pl in price_levels:
        if abs(pl - today_poc) <= poc_bin_hw:
            vp_colors.append("#ff9800")            # today POC — amber
        else:
            vp_colors.append("rgba(66,165,245,0.6)")

    # ── subplots ─────────────────────────────────────────────────────────────
    fig = make_subplots(
        rows=2, cols=2,
        column_widths=[0.78, 0.22],
        row_heights=[0.78, 0.22],
        shared_yaxes=True,
        vertical_spacing=0.02,
        horizontal_spacing=0.005,
        subplot_titles=[symbol, "Volume Profile", "", ""],
    )

    # 1. Candlestick
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["open"], high=df["high"],
        low=df["low"],   close=df["close"],
        name="Price",
        increasing_line_color="#26a69a",
        decreasing_line_color="#ef5350",
        showlegend=False,
    ), row=1, col=1)

    # 2. EMA 26
    fig.add_trace(go.Scatter(
        x=df.index, y=df["ema26"],
        name="EMA 26",
        line=dict(color="#ff9800", width=1.6),
        hovertemplate="EMA26: %{y:.2f}<extra></extra>",
    ), row=1, col=1)

    # 3. VWAP
    fig.add_trace(go.Scatter(
        x=df.index, y=df["vwap"],
        name="VWAP",
        line=dict(color="#42a5f5", width=1.6, dash="dot"),
        hovertemplate="VWAP: %{y:.2f}<extra></extra>",
    ), row=1, col=1)

    # 4. Volume bars (bottom-left)
    fig.add_trace(go.Bar(
        x=df.index, y=df["volume"],
        name="Volume",
        marker_color=candle_colors,
        showlegend=False,
        hovertemplate="%{y:,.0f}<extra></extra>",
    ), row=2, col=1)

    # 5. Volume Profile (right side, horizontal)
    fig.add_trace(go.Bar(
        x=volumes,
        y=price_levels,
        orientation="h",
        name="Vol Profile",
        marker_color=vp_colors,
        showlegend=False,
        width=poc_bin_hw * 1.8 if poc_bin_hw > 0 else None,
        hovertemplate="Price: %{y:.2f}<br>Vol: %{x:,.0f}<extra></extra>",
    ), row=1, col=2)

    # 6. Today POC annotation on VP
    fig.add_annotation(
        x=max_vol * 0.98, y=today_poc,
        text=f"POC {today_poc:.1f}",
        showarrow=False,
        font=dict(color="#ff9800", size=9, family="monospace"),
        xanchor="right",
        bgcolor="rgba(14,17,23,0.7)",
        row=1, col=2,
    )

    # 7. Prev-day POC horizontal line across candlestick
    if prev_day_poc is not None:
        fig.add_hline(
            y=prev_day_poc,
            line=dict(color="#ce93d8", width=1.4, dash="dash"),
            annotation_text=f"Prev POC  {prev_day_poc:.1f}",
            annotation_position="top left",
            annotation_font=dict(color="#ce93d8", size=9),
            row=1, col=1,
        )

    # 8. First-15-min trend levels
    if trend_levels:
        # (name, color, width, dash, label, annotation_side)
        _LEVEL_STYLE = [
            ("up3",        "#26a69a", 2.0, "solid", "up3",        "top right"),
            ("up2",        "#80cbc4", 1.3, "dash",  "up2",        "top right"),
            ("up1",        "#b2dfdb", 1.0, "dot",   "up1",        "top right"),
            ("first_high", "#ffd54f", 1.6, "solid", "1st High",   "top left"),
            ("midpoint",   "#78909c", 1.0, "dot",   "Mid",        "top left"),
            ("first_low",  "#ffd54f", 1.6, "solid", "1st Low",    "top left"),
            ("dn1",        "#ffab91", 1.0, "dot",   "dn1",        "bottom right"),
            ("dn2",        "#ff7043", 1.3, "dash",  "dn2",        "bottom right"),
            ("dn3",        "#ef5350", 2.0, "solid", "dn3",        "bottom right"),
        ]
        for name, color, width, dash, label, pos in _LEVEL_STYLE:
            price = trend_levels.get(name)
            if price is None:
                continue
            fig.add_hline(
                y=price,
                line=dict(color=color, width=width, dash=dash),
                annotation_text=f"{label}  {price:.2f}",
                annotation_position=pos,
                annotation_font=dict(color=color, size=9),
                row=1, col=1,
            )

    # ── layout ───────────────────────────────────────────────────────────────
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0e1117",
        plot_bgcolor="#0e1117",
        margin=dict(l=5, r=5, t=38, b=5),
        legend=dict(orientation="h", x=0, y=1.04,
                    font=dict(size=11, color="#ccc")),
        height=660,
        hovermode="x unified",
        xaxis_rangeslider_visible=False,
    )

    fig.update_xaxes(showgrid=False, color="#555", zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor="#1e2130",
                     color="#888", zeroline=False)

    # ── Lock y-axis to actual OHLC range so extreme level lines don't squeeze ─
    # add_hline forces Plotly to auto-scale to include up3/dn3 (±26% from open)
    # which compresses the candlestick area. Fix: pin the range to price data.
    y_lo = float(df["low"].min())
    y_hi = float(df["high"].max())
    pad  = (y_hi - y_lo) * 0.06          # 6% breathing room top & bottom
    fig.update_yaxes(range=[y_lo - pad, y_hi + pad],
                     fixedrange=False,    # user can still zoom out to see far levels
                     row=1, col=1)

    # hide x tick labels on candle row (shared by volume row below)
    fig.update_xaxes(showticklabels=False, row=1, col=1)
    fig.update_xaxes(
        showticklabels=True, row=2, col=1,
        tickformat="%H:%M",       # show HH:MM in IST (index is already IST)
        tickangle=-30,
        nticks=12,
    )
    fig.update_xaxes(showticklabels=False, row=1, col=2)
    fig.update_xaxes(visible=False, row=2, col=2)

    # ensure Plotly uses the timestamps as-is (tz-aware → display local)
    fig.update_layout(xaxis_type="date", xaxis2_type="date")

    return fig
