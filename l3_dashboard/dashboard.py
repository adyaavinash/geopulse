"""L3 — Streamlit entry point (Person 4).
Run: streamlit run l3_dashboard/dashboard.py
"""
import streamlit as st
import json
import random
import pandas as pd
from datetime import datetime, timedelta

import theme
from data_sources import render_sources_badge

st.set_page_config(page_title="GeoPulse Command Center", layout="wide", page_icon="🛰️")
theme.inject()
theme.render_sidebar()

# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #
st.markdown(
    f"""
    <div style='display:flex; align-items:flex-start; justify-content:space-between; margin-bottom: 1.4rem;'>
        <div>
            <div class='gp-kicker' style='margin-bottom: 8px;'>Global Operations &nbsp;·&nbsp; {datetime.now().strftime('%A %d %B %Y')}</div>
            <h1 style='margin: 0; padding: 0; font-size: 2.5rem; letter-spacing: -1px; color: {theme.COLORS["ink"]};'>Command Center</h1>
            <div style='color: {theme.COLORS["muted"]}; font-size: 1.1rem; margin-top: 4px;'>Macroeconomic &amp; geopolitical impact analysis engine — event detection to sector-level prediction, end to end.</div>
        </div>
        <div style='text-align:right; padding-top:6px'>
            <div class='gp-mono' style='font-size:12px; color:{theme.COLORS["muted"]}'>{theme.live_dot('green')}ALL AGENTS NOMINAL</div>
            <div class='gp-mono' style='font-size:11px; color:{theme.COLORS["faint"]}; margin-top:4px'>last sync 00:00:0{random.randint(2,9)} ago</div>
        </div>
    </div>
    """, unsafe_allow_html=True
)

# Bloomberg-style scrolling market ticker — sets the "trading floor" register
# for the whole app. Values are illustrative pending live feed wiring.
_TICKER_ITEMS = [
    {"label": "S&P 500", "value": "5,842.10", "delta": "+0.34%", "tone": "green"},
    {"label": "BRENT CRUDE", "value": "84.12", "delta": "+1.8%", "tone": "green"},
    {"label": "VIX", "value": "24.50", "delta": "-1.2", "tone": "red"},
    {"label": "USD/CNY", "value": "7.24", "delta": "+0.09%", "tone": "green"},
    {"label": "10Y YIELD", "value": "4.28%", "delta": "-2bps", "tone": "red"},
    {"label": "GOLD", "value": "2,412", "delta": "+0.6%", "tone": "green"},
    {"label": "STRAIT OF HORMUZ", "value": "RISK: ELEVATED", "delta": "▲", "tone": "amber"},
    {"label": "SEMIS (SOXX)", "value": "-0.8%", "delta": "sanctions watch", "tone": "red"},
]
st.markdown(theme.ticker_tape(_TICKER_ITEMS), unsafe_allow_html=True)

# --------------------------------------------------------------------------- #
# Top row — KPI cards with sparklines instead of flat numbers
# --------------------------------------------------------------------------- #
_agents_trend = [7, 7, 6, 7, 7, 7, 7]
_vix_trend = [27.1, 26.4, 25.8, 26.9, 25.1, 25.7, 24.5]
_anomaly_trend = [4, 6, 5, 8, 7, 9, 12]
_alpha_trend = [1.1, 1.6, 2.0, 2.4, 3.1, 3.6, 4.2]

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(theme.stat_card("Active AI Agents", "7 / 7", "Nominal", "green",
                                 spark_values=_agents_trend, spark_tone="green"), unsafe_allow_html=True)
with c2:
    st.markdown(theme.stat_card("Global VIX Proxy", "24.50", "↓ -1.2 pts (7d)", "green",
                                 spark_values=_vix_trend, spark_tone="red"), unsafe_allow_html=True)
with c3:
    st.markdown(theme.stat_card("Live Anomalies", "12", "↑ +3 today", "red",
                                 spark_values=_anomaly_trend, spark_tone="red", accent=True), unsafe_allow_html=True)
with c4:
    st.markdown(theme.stat_card("Agent Alpha (YTD)", "+4.2%", "vs S&P 500", "green",
                                 spark_values=_alpha_trend, spark_tone="green"), unsafe_allow_html=True)

st.write("")

# --------------------------------------------------------------------------- #
# Timeline — the only control on this page. Per the whiteboard, L1 ingests
# continuously and detects on its own; the operator picks a *window* to
# inspect, not a specific event (event simulation lives on the L2 Explorer
# page instead).
# --------------------------------------------------------------------------- #
st.markdown(
    theme.section_header("Signal Detection", "Ingestion Timeline",
                          "Pick a window to inspect — source activity and detected anomalies "
                          "below both reflect it. L1 ingests continuously; nothing here is a "
                          "hand-picked event."),
    unsafe_allow_html=True,
)
dcol1, dcol2, _ = st.columns([1, 1, 2])
with dcol1:
    start_date = st.date_input("Start Date", datetime.now() - timedelta(days=90))
with dcol2:
    end_date = st.date_input("End Date", datetime.now())
window_days = max((end_date - start_date).days, 1)

st.write("")

# --------------------------------------------------------------------------- #
# Data Ingestion — every source L1's collectors pull from, per the whiteboard's
# "1 · Ingestion & Detection" node. Volumes are illustrative (mock) pending
# live source-level metrics; they scale with the selected window so the panel
# still feels tied to the timeline above rather than static.
# --------------------------------------------------------------------------- #
st.markdown(
    theme.section_header("Layer 1", "Data Ingestion",
                          "Live source feeds L1's collectors poll — GDELT, wire RSS, Reddit, "
                          "X/Twitter, Polymarket, market data — normalized to one record shape "
                          "before dedupe and anomaly detection."),
    unsafe_allow_html=True,
)


def _mock_source_activity(name: str, daily_rate: int, tone: str):
    """Deterministic-per-source mock volume, scaled by the selected window so
    it tracks the timeline control instead of sitting static."""
    rnd = random.Random(hash(name) % 100000)
    total = int(daily_rate * window_days * rnd.uniform(0.85, 1.15))
    trend = [max(0, int(daily_rate * rnd.uniform(0.6, 1.4))) for _ in range(7)]
    mins_ago = rnd.randint(1, 14)
    return theme.source_card(
        icon=_SOURCE_ICONS[name], name=name,
        count=f"{total:,}", meta=f"last record {mins_ago}m ago · ~{daily_rate}/day",
        tone=tone, spark_values=trend,
    )


_SOURCE_ICONS = {
    "GDELT News": "📰", "RSS Wire": "📡", "Reddit": "👽",
    "X / Twitter": "🐦", "Polymarket": "🎲", "Market Data": "📈",
}
_SOURCES = [
    ("GDELT News", 340, "blue"), ("RSS Wire", 210, "blue"),
    ("Reddit", 480, "amber"), ("X / Twitter", 1250, "amber"),
    ("Polymarket", 60, "purple"), ("Market Data", 24, "green"),
]
src_cols = st.columns(3)
for i, (name, rate, tone) in enumerate(_SOURCES):
    with src_cols[i % 3]:
        st.markdown(_mock_source_activity(name, rate, tone), unsafe_allow_html=True)
        st.write("")

st.caption(
    "Counts are illustrative — L1's real collectors (GDELT DOC API, RSS, PRAW, "
    "Polymarket Gamma API, yfinance) are wired and tested; per-source volume "
    "metrics like these aren't persisted yet. X/Twitter is mocked end-to-end — "
    "not an implemented L1 collector."
)
st.write("")

# Load mock backtest events for timeline
@st.cache_data
def load_events():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    try:
        with open(root / "tests/fixtures/mock_backtest.json", "r") as f:
            data = json.load(f)
            return data.get("events", [])
    except FileNotFoundError:
        return []

events = load_events()

st.markdown(theme.kicker("Anomaly density in selected window"), unsafe_allow_html=True)
if events:
    df = pd.DataFrame(events)
    df['date'] = pd.to_datetime(df['date'])
    mask = (df['date'].dt.date >= start_date) & (df['date'].dt.date <= end_date)
    df_filtered = df.loc[mask]

    if not df_filtered.empty:
        cells = [
            {"title": f"{row['date'].strftime('%Y-%m-%d')}: {row['theme']}", "tone": "red"}
            for _, row in df_filtered.iterrows()
        ]
        st.markdown(theme.heat_strip(cells), unsafe_allow_html=True)
    else:
        st.markdown(theme.heat_strip([]), unsafe_allow_html=True)
else:
    st.markdown(theme.heat_strip([], empty_label="No historical data available."), unsafe_allow_html=True)

st.write("")

# --------------------------------------------------------------------------- #
# Recent Anomalies list with Data Sources (Mentor Fix #2)
# --------------------------------------------------------------------------- #
st.markdown(
    theme.section_header("Latest Detections", "Recent Anomalies",
                          "Most recent L1 signals, cross-referenced against source feeds."),
    unsafe_allow_html=True,
)
if events:
    recent = sorted(events, key=lambda x: x['date'], reverse=True)[:5]
    cols = st.columns(min(len(recent), 5))
    for i, event in enumerate(recent):
        with cols[i]:
            sources_mock = ["gdelt", "reddit", "polymarket"][:i % 3 + 1]  # Mock sources
            logos_html = render_sources_badge(sources_mock)

            st.markdown(
                f"<div class='gp-card'>"
                f"<div class='gp-mono' style='color:{theme.COLORS['muted']};font-size:11px'>"
                f"{event['date']}</div>"
                f"<div style='font-weight:600;color:{theme.COLORS['ink']};margin:4px 0 8px'>"
                f"{event['theme'].replace('_', ' ').title()}</div>"
                f"{theme.badge('DETECTED', 'red')}"
                f"{logos_html}"
                f"</div>",
                unsafe_allow_html=True,
            )
else:
    st.info("No recent anomalies to display.")