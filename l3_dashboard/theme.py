"""GeoPulse house theme — the warm-parchment + amber look shared with the
compliance UI. Import and call ``inject()`` once at the top of any Streamlit
page; use ``COLORS`` and ``badge()`` for consistent accents.

Source of truth for the palette/fonts: the compliance project's regulatory UI
(Space Grotesk / IBM Plex Mono, cream paper, amber accent, semantic
blue/green/red/purple).

This module also carries the shared "terminal" component kit (stat cards,
sparklines, SVG line charts, ticker tape, section headers) so every page in
the app reads as one coherent, market-grade product instead of a stack of
ad-hoc HTML blocks.
"""

from __future__ import annotations

import streamlit as st

COLORS = {
    "ink": "#1a1712",
    "text": "#54504a",
    "muted": "#8a8478",
    "faint": "#c3bcae",
    "paper": "#fffdfa",
    "page": "#faf8f4",
    "line": "rgba(0,0,0,.08)",
    "amber": "#cf861b",   # brand accent
    "blue": "#2f7fd6",    # info / active
    "green": "#1f9d63",   # positive / up
    "red": "#e0455a",     # negative / down
    "purple": "#7c5bef",  # orchestrator / secondary
}

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600;700&display=swap');

:root {
  --ink:#1a1712; --text:#54504a; --muted:#8a8478; --faint:#c3bcae;
  --paper:#fffdfa; --page:#faf8f4; --line:rgba(0,0,0,.08);
  --amber:#cf861b; --blue:#2f7fd6; --green:#1f9d63; --red:#e0455a; --purple:#7c5bef;
}

* { scrollbar-width: thin; scrollbar-color: var(--faint) transparent; }
::-webkit-scrollbar { width: 8px; height: 8px; }
::-webkit-scrollbar-thumb { background: var(--faint); border-radius: 8px; }
::-webkit-scrollbar-track { background: transparent; }

.stApp {
  background:
    radial-gradient(1200px 600px at 8% -10%, rgba(207,134,27,.06), transparent 60%),
    radial-gradient(900px 500px at 100% 0%, rgba(124,91,239,.05), transparent 55%),
    var(--page);
}
.block-container { padding-top: 3rem; max-width: 1280px; }
[data-testid="stHeader"] { display: none !important; }

/* Force light-base text colors (belt-and-suspenders if base theme misloads) */
.stApp, .stMarkdown, .stMarkdown p, .stMarkdown li { color: var(--text); }

/* Display type: Space Grotesk for headings + metric numbers */
h1, h2, h3, h4,
[data-testid="stMetricValue"],
[data-testid="stMetricLabel"] {
  font-family:'Space Grotesk', sans-serif !important;
  letter-spacing:-.4px; color:var(--ink) !important;
}
h1 { font-weight:700; }
h3 { font-weight:600; letter-spacing:-.2px; }
[data-testid="stMetricValue"] { font-weight:700; color:var(--ink) !important; }
[data-testid="stMetricLabel"] { color:var(--muted) !important; letter-spacing:.2px; }

/* Mono for code/badges/data */
code, kbd, .gp-mono { font-family:'IBM Plex Mono', monospace !important; }

/* Sidebar as parchment panel */
[data-testid="stSidebar"] {
  background:var(--paper); border-right:1px solid var(--line);
}
[data-testid="stSidebar"] > div { padding-top: 1.4rem; }

/* Cards: expanders + bordered containers */
[data-testid="stExpander"] {
  background:var(--paper); border:1px solid var(--line) !important;
  border-radius:14px !important; box-shadow:0 1px 3px rgba(0,0,0,.05);
}
[data-testid="stExpander"] summary {
  font-family:'IBM Plex Mono', monospace; font-size:.78rem; color:var(--text);
  letter-spacing:.2px;
}

/* Tabs — mono, understated, amber underline on active */
.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid var(--line); }
.stTabs [data-baseweb="tab"] {
  font-family:'IBM Plex Mono', monospace; font-size:.8rem; color:var(--muted);
  padding: 10px 6px;
}
.stTabs [aria-selected="true"] { color: var(--ink) !important; }
.stTabs [data-baseweb="tab-highlight"] { background-color: var(--amber) !important; height:2px; }

/* Amber progress fill (confidence) */
[data-testid="stProgress"] div div div div { background: linear-gradient(90deg, var(--amber), #e0a94a); }

/* Amber slider track + handle */
[data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"] { background:var(--amber) !important; box-shadow:0 0 0 4px rgba(207,134,27,.15) !important; }
[data-testid="stSlider"] [data-baseweb="slider"] > div > div > div { background:var(--amber) !important; }

/* Dataframes / tables — parchment, mono numerics */
[data-testid="stDataFrame"] {
  border:1px solid var(--line); border-radius:12px; overflow:hidden;
}
.gp-table {
  width: 100%; border-collapse: collapse; font-family: 'IBM Plex Mono', monospace; font-size: 13px; text-align: right;
}
.gp-table th { text-align: right; color: var(--muted); border-bottom: 1px solid var(--line); padding: 8px 12px; }
.gp-table td { padding: 8px 12px; color: var(--text); border-bottom: 1px solid var(--line); }

/* Buttons */
.stButton > button, .stDownloadButton > button {
  font-family:'Space Grotesk', sans-serif; font-weight:600;
  border-radius:10px; border:1px solid var(--line); color: var(--ink);
  background: var(--paper); transition: all .15s ease;
}
.stButton > button:hover { border-color: var(--amber); color: var(--amber); }

/* Dividers a touch warmer */
hr { border-color:var(--line); }

/* Reusable badge/card classes */
.gp-badge {
  font-family:'IBM Plex Mono', monospace; font-size:10px; font-weight:600;
  letter-spacing:.4px; padding:3px 8px; border-radius:7px; display:inline-block;
  max-width:100%; white-space:normal; overflow-wrap:normal; word-break:normal; vertical-align:bottom;
}
.gp-card {
  background: rgba(255, 253, 250, 0.85);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(0,0,0,0.06);
  border-radius: 16px;
  padding: 18px 18px;
  min-height: 140px;
  box-shadow: 0 4px 24px rgba(0,0,0,.03), 0 1px 3px rgba(0,0,0,.02);
  margin-bottom: 20px;
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color .2s ease;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.gp-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 32px rgba(0,0,0,.05), 0 2px 6px rgba(0,0,0,.03);
  border-color: rgba(207,134,27,.25);
}
.gp-card.gp-accent { border-left: 3px solid var(--amber); }

.gp-kicker {
  font-family:'IBM Plex Mono', monospace; font-size:11px; font-weight:600;
  letter-spacing:1.2px; text-transform:uppercase; color:var(--amber);
}
.gp-section-head { display:flex; align-items:baseline; justify-content:space-between; margin: 4px 0 14px; }
.gp-section-head .gp-title { font-family:'Space Grotesk',sans-serif; font-weight:700; font-size:1.4rem; color:var(--ink); letter-spacing:-.3px; margin-top:2px;}
.gp-section-head .gp-sub { color:var(--muted); font-size:.85rem; margin-top:2px; }
.gp-rule {
  height:1px; margin: 6px 0 20px;
  background: linear-gradient(90deg, var(--line) 0%, rgba(207,134,27,.35) 40%, var(--line) 100%);
}

.gp-brand {
  font-family: 'Space Grotesk', sans-serif;
  font-weight: 700;
  font-size: 24px;
  letter-spacing: -0.8px;
  background: linear-gradient(135deg, var(--ink) 0%, var(--muted) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
[data-testid="stSidebarNav"] { display: none !important; }

/* Custom Navigation Links */
.gp-nav-link {
  display: flex; align-items: center; gap: 12px; padding: 10px 16px;
  color: var(--text); font-family: 'Space Grotesk', sans-serif; font-weight: 500;
  text-decoration: none; border-radius: 8px; margin-bottom: 4px;
  transition: all 0.2s ease;
}
.gp-nav-link:hover {
  background: rgba(0,0,0,0.03); color: var(--ink);
}
.gp-nav-icon {
  font-size: 18px;
}

/* Live status dot */
.gp-dot {
  display:inline-block; width:7px; height:7px; border-radius:50%;
  margin-right:6px; position:relative; top:-1px;
  animation: gp-pulse 2s infinite;
}
@keyframes gp-pulse {
  0%   { box-shadow: 0 0 0 0 rgba(31,157,99,.45); }
  70%  { box-shadow: 0 0 0 6px rgba(31,157,99,0); }
  100% { box-shadow: 0 0 0 0 rgba(31,157,99,0); }
}

/* Ticker tape */
.gp-ticker-wrap {
  width: 100%; overflow: hidden; background: var(--paper);
  border: 1px solid var(--line); border-radius: 12px;
  padding: 10px 0; margin-bottom: 22px;
  box-shadow: 0 1px 3px rgba(0,0,0,.03);
}
.gp-ticker-track {
  display: flex; width: max-content;
  animation: gp-ticker 38s linear infinite;
}
.gp-ticker-wrap:hover .gp-ticker-track { animation-play-state: paused; }
@keyframes gp-ticker {
  0% { transform: translateX(0); }
  100% { transform: translateX(-50%); }
}
.gp-ticker-item {
  display:flex; align-items:center; gap:8px;
  font-family:'IBM Plex Mono', monospace; font-size:12.5px;
  padding: 0 22px; border-right: 1px solid var(--line); white-space:nowrap;
  color: var(--text);
}
.gp-ticker-item b { color: var(--ink); font-weight:600; }

/* Stat card internals */
.gp-stat-value { font-family:'Space Grotesk',sans-serif; font-size:20px; font-weight:700; color:var(--ink); line-height:1.2; white-space:normal; word-break:normal; overflow-wrap:normal; margin-top: 6px;}
.gp-stat-delta { font-size:12px; font-family:'IBM Plex Mono', monospace; margin-top:8px; white-space: normal; line-height: 1.4; }
.gp-stat-row { display:flex; align-items:center; justify-content:space-between; gap:16px; width: 100%;}
.gp-stat-row > div:first-child { flex: 1 1 auto; min-width: 0; padding-right: 12px; }
.gp-stat-row > div:last-child { flex: 0 0 auto; }

/* Agent chips — hover reveals a per-agent explanation (no JS, pure CSS) */
.gp-agent-row { display:flex; gap:8px; flex-wrap:wrap; margin:12px 0 4px; }
.gp-agent-chip {
  position:relative; display:inline-flex; align-items:center; gap:6px;
  font-family:'IBM Plex Mono', monospace; font-size:11px; font-weight:600;
  letter-spacing:.2px; padding:5px 10px 5px 8px; border-radius:8px; cursor:help;
  border:1px solid; user-select:none;
}
.gp-agent-chip .gp-chip-icon { font-size:12px; line-height:1; }
.gp-agent-chip .gp-tooltip {
  visibility:hidden; opacity:0; position:absolute; bottom:135%; left:50%;
  transform:translateX(-50%) translateY(4px);
  background:var(--ink); color:var(--paper); text-align:left;
  padding:11px 13px; border-radius:10px; width:250px; z-index:80;
  font-family:'Space Grotesk',sans-serif; font-weight:400; font-size:12.5px; line-height:1.5;
  box-shadow:0 12px 32px rgba(0,0,0,.22);
  transition:opacity .15s ease, transform .15s ease, visibility .15s ease;
}
.gp-agent-chip .gp-tooltip b { color:var(--paper); font-weight:700; }
.gp-agent-chip .gp-tooltip::after {
  content:''; position:absolute; top:100%; left:50%; transform:translateX(-50%);
  border:6px solid transparent; border-top-color:var(--ink);
}
.gp-agent-chip:hover .gp-tooltip { visibility:visible; opacity:1; transform:translateX(-50%) translateY(0); }

/* "Why" synthesis callout — the orchestrator's reconciled rationale */
.gp-why-box {
  background: linear-gradient(180deg, rgba(207,134,27,.05), rgba(207,134,27,0));
  border:1px solid rgba(207,134,27,.25); border-left:3px solid var(--amber);
  border-radius:10px; padding:12px 14px; margin:10px 0 4px;
  font-size:13px; color:var(--text); line-height:1.55;
}
.gp-why-box .gp-why-label {
  font-family:'IBM Plex Mono',monospace; font-size:10px; font-weight:700; letter-spacing:.6px;
  text-transform:uppercase; color:var(--amber); display:block; margin-bottom:5px;
}

/* Source ingestion cards */
.gp-source-card {
  background:var(--paper); border:1px solid var(--line); border-radius:14px;
  padding:14px 16px; box-shadow:0 1px 3px rgba(0,0,0,.04);
  display:flex; flex-direction:column; gap:6px; height:100%;
}
.gp-source-head { display:flex; align-items:center; justify-content:space-between; }
.gp-source-name { display:flex; align-items:center; gap:8px; font-family:'Space Grotesk',sans-serif; font-weight:600; font-size:13px; color:var(--ink); }
.gp-source-count { font-family:'Space Grotesk',sans-serif; font-weight:700; font-size:22px; color:var(--ink); }
.gp-source-meta { font-family:'IBM Plex Mono',monospace; font-size:10.5px; color:var(--muted); }
</style>
"""


def inject() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def badge(text: str, tone: str = "amber") -> str:
    """An IBM-Plex-Mono pill in a semantic tone (tone = a COLORS key or hex)."""
    color = COLORS.get(tone, tone)
    return (
        f"<span class='gp-badge' style='color:{color};"
        f"background:{color}14;border:1px solid {color}44'>{text}</span>"
    )


def kicker(text: str) -> str:
    return f"<div class='gp-kicker'>{text}</div>"


def section_header(kicker_text: str, title: str, subtitle: str | None = None, right_html: str = "") -> str:
    """A consistent section header: eyebrow + title (+ optional subtitle / trailing badge)."""
    sub = f"<div class='gp-sub'>{subtitle}</div>" if subtitle else ""
    return (
        f"<div class='gp-section-head'>"
        f"<div><div class='gp-kicker'>{kicker_text}</div>"
        f"<div class='gp-title'>{title}</div>{sub}</div>"
        f"<div>{right_html}</div>"
        f"</div><div class='gp-rule'></div>"
    )


def live_dot(color_key: str = "green") -> str:
    color = COLORS.get(color_key, color_key)
    return f"<span class='gp-dot' style='background:{color}'></span>"


def brand(size: int = 24) -> str:
    return (
        f"<div class='gp-brand' style='font-size: {size}px; margin-bottom: 24px;'>"
        f"<svg width='{size}' height='{size}' viewBox='0 0 24 24' fill='none' stroke='url(#brand-grad)' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'>"
        f"<defs><linearGradient id='brand-grad' x1='0%' y1='0%' x2='100%' y2='100%'><stop offset='0%' stop-color='{COLORS['amber']}' /><stop offset='100%' stop-color='{COLORS['red']}' /></linearGradient></defs>"
        f"<path d='M2 12h4l3-9 5 18 3-9h5'/></svg>"
        f"GeoPulse"
        f"</div>"
    )


def render_sidebar():
    """Renders the custom sidebar with the brand at the top and styled navigation links."""
    st.sidebar.markdown(brand(size=28), unsafe_allow_html=True)
    st.sidebar.markdown(kicker("Navigation"), unsafe_allow_html=True)
    st.sidebar.write("")
    st.sidebar.page_link("dashboard.py", label="Command Center")
    st.sidebar.page_link("pages/1_Transmission_Explorer.py", label="Impact Explorer")
    st.sidebar.page_link("pages/2_Backtest_Simulation.py", label="Backtest Alpha")
    st.sidebar.markdown("<div class='gp-rule'></div>", unsafe_allow_html=True)
    st.sidebar.markdown(
        f"<div class='gp-mono' style='font-size:11px;color:{COLORS['muted']}'>"
        f"{live_dot('green')}SYSTEM NOMINAL &nbsp;·&nbsp; 7/7 agents online</div>",
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# Data-viz primitives — hand-rolled SVG so the app never depends on a
# charting library (Altair/rpds has caused hard crashes in this environment).
# --------------------------------------------------------------------------- #

def sparkline(values: list, tone: str = "amber", width: int = 96, height: int = 32) -> str:
    """A minimal inline SVG sparkline with a soft area fill, for stat cards."""
    if not values or len(values) < 2:
        return ""
    color = COLORS.get(tone, tone)
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    n = len(values)
    pad = 2
    pts = []
    for i, v in enumerate(values):
        x = pad + i * (width - 2 * pad) / (n - 1)
        y = pad + (height - 2 * pad) * (1 - (v - lo) / span)
        pts.append((x, y))
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{pad},{height - pad} " + poly + f" {width - pad},{height - pad}"
    uid = f"spark{abs(hash(tuple(values))) % 100000}"
    return (
        f"<svg width='{width}' height='{height}' viewBox='0 0 {width} {height}' "
        f"xmlns='http://www.w3.org/2000/svg' style='display:block'>"
        f"<defs><linearGradient id='{uid}' x1='0' y1='0' x2='0' y2='1'>"
        f"<stop offset='0%' stop-color='{color}' stop-opacity='0.35'/>"
        f"<stop offset='100%' stop-color='{color}' stop-opacity='0'/></linearGradient></defs>"
        f"<polygon points='{area}' fill='url(#{uid})' stroke='none'/>"
        f"<polyline points='{poly}' fill='none' stroke='{color}' stroke-width='1.8' "
        f"stroke-linecap='round' stroke-linejoin='round'/>"
        f"</svg>"
    )


def stat_card(kicker_text: str, value: str, delta_text: str = "", delta_tone: str = "muted",
              spark_values=None, spark_tone: str | None = None, accent: bool = False) -> str:
    """A KPI card: kicker + big value (+ optional delta) with an optional sparkline."""
    cls = "gp-card gp-accent" if accent else "gp-card"
    delta_color = COLORS.get(delta_tone, delta_tone)
    delta_html = f"<div class='gp-stat-delta' style='color:{delta_color}'>{delta_text}</div>" if delta_text else ""
    spark_html = sparkline(spark_values, spark_tone or delta_tone) if spark_values else ""
    return (
        f"<div class='{cls}' style='margin:0'>"
        f"<div class='gp-kicker'>{kicker_text}</div>"
        f"<div class='gp-stat-row'>"
        f"<div><div class='gp-stat-value'>{value}</div>{delta_html}</div>"
        f"<div>{spark_html}</div>"
        f"</div></div>"
    )


def ticker_tape(items: list) -> str:
    """items: [{'label': 'BRENT', 'value': '84.12', 'delta': '+1.4%', 'tone': 'green'}, ...]
    Renders a Bloomberg-style scrolling ticker, duplicated once for a seamless loop.
    """
    def _chip(it):
        color = COLORS.get(it.get("tone", "muted"), it.get("tone", "muted"))
        return (
            f"<div class='gp-ticker-item'><b>{it['label']}</b>"
            f"<span>{it['value']}</span>"
            f"<span style='color:{color}'>{it.get('delta', '')}</span></div>"
        )
    chips = "".join(_chip(it) for it in items)
    return f"<div class='gp-ticker-wrap'><div class='gp-ticker-track'>{chips}{chips}</div></div>"


def line_chart_svg(x_labels: list, series: dict, width: int = 900, height: int = 320,
                    y_prefix: str = "$", show_legend: bool = True) -> str:
    """A dependency-free stock-style multi-line chart with grid, axis labels,
    gradient area fill under the first series, and a legend.

    series: {"AI Portfolio": {"values": [...], "tone": "amber"}, ...}
    """
    if not series or not x_labels:
        return ""
    all_vals = [v for s in series.values() for v in s["values"]]
    lo, hi = min(all_vals), max(all_vals)
    span = (hi - lo) or 1.0
    pad_l, pad_r, pad_t, pad_b = 56, 20, 20, 34
    plot_w, plot_h = width - pad_l - pad_r, height - pad_t - pad_b
    n = len(x_labels)

    def _x(i):
        return pad_l + (i * plot_w / (n - 1) if n > 1 else 0)

    def _y(v):
        return pad_t + plot_h * (1 - (v - lo) / span)

    # Grid + y-axis labels (5 bands)
    grid, ylabels = [], []
    for k in range(5):
        gy = pad_t + plot_h * k / 4
        val = hi - span * k / 4
        grid.append(f"<line x1='{pad_l}' y1='{gy:.1f}' x2='{width - pad_r}' y2='{gy:.1f}' "
                     f"stroke='{COLORS['line']}' stroke-width='1'/>")
        ylabels.append(f"<text x='{pad_l - 10}' y='{gy + 4:.1f}' text-anchor='end' "
                        f"font-family='IBM Plex Mono, monospace' font-size='10' fill='{COLORS['muted']}'>"
                        f"{y_prefix}{val:,.0f}</text>")

    # x-axis labels — show ~6 evenly spaced ticks
    step = max(1, n // 6)
    xlabels = []
    for i in range(0, n, step):
        xlabels.append(f"<text x='{_x(i):.1f}' y='{height - 10}' text-anchor='middle' "
                        f"font-family='IBM Plex Mono, monospace' font-size='10' fill='{COLORS['muted']}'>"
                        f"{x_labels[i]}</text>")

    parts = ["<defs>"]
    lines, legend = [], []
    for idx, (name, s) in enumerate(series.items()):
        color = COLORS.get(s.get("tone", "amber"), s.get("tone", "amber"))
        uid = f"area{idx}"
        pts = " ".join(f"{_x(i):.1f},{_y(v):.1f}" for i, v in enumerate(s["values"]))
        if idx == 0:
            area_pts = f"{_x(0):.1f},{pad_t + plot_h:.1f} {pts} {_x(n-1):.1f},{pad_t + plot_h:.1f}"
            parts.append(
                f"<linearGradient id='{uid}' x1='0' y1='0' x2='0' y2='1'>"
                f"<stop offset='0%' stop-color='{color}' stop-opacity='0.22'/>"
                f"<stop offset='100%' stop-color='{color}' stop-opacity='0'/></linearGradient>"
            )
            lines.append(f"<polygon points='{area_pts}' fill='url(#{uid})' stroke='none'/>")
        lines.append(
            f"<polyline points='{pts}' fill='none' stroke='{color}' stroke-width='2.4' "
            f"stroke-linecap='round' stroke-linejoin='round'/>"
        )
        lx, ly = _x(n - 1), _y(s["values"][-1])
        lines.append(f"<circle cx='{lx:.1f}' cy='{ly:.1f}' r='3.4' fill='{color}'/>")
        if show_legend:
            legend.append(
                f"<span style='display:inline-flex;align-items:center;gap:6px;margin-right:18px'>"
                f"<span style='width:9px;height:9px;border-radius:50%;background:{color};display:inline-block'></span>"
                f"<span style='font-family:IBM Plex Mono,monospace;font-size:11px;color:{COLORS['text']}'>{name}</span></span>"
            )
    parts.append("</defs>")

    svg = (
        f"<svg width='100%' height='{height}' viewBox='0 0 {width} {height}' "
        f"xmlns='http://www.w3.org/2000/svg' preserveAspectRatio='xMidYMid meet'>"
        + "".join(parts) + "".join(grid) + "".join(ylabels) + "".join(lines) + "".join(xlabels)
        + "</svg>"
    )
    legend_html = f"<div style='margin-top:6px'>{''.join(legend)}</div>" if show_legend else ""
    return f"<div>{svg}{legend_html}</div>"


def agent_chip(icon: str, name: str, status: str, tone: str, tooltip_html: str) -> str:
    """One agent's contribution to a sector call — a compact chip whose hover
    reveals the agent's specific reasoning. tooltip_html may contain <b> tags."""
    color = COLORS.get(tone, tone)
    return (
        f"<span class='gp-agent-chip' style='color:{color};background:{color}12;border-color:{color}40'>"
        f"<span class='gp-chip-icon'>{icon}</span>{name} · {status}"
        f"<span class='gp-tooltip'>{tooltip_html}</span>"
        f"</span>"
    )


def agent_row(chips: list) -> str:
    return f"<div class='gp-agent-row'>{''.join(chips)}</div>"


def why_box(label: str, text: str) -> str:
    """The orchestrator's reconciled, plain-English rationale for one call."""
    return (
        f"<div class='gp-why-box'><span class='gp-why-label'>{label}</span>{text}</div>"
    )


def source_card(icon: str, name: str, count: str, meta: str, tone: str = "amber",
                 spark_values=None) -> str:
    """One ingestion source's activity card (Reddit/Twitter/GDELT/etc.)."""
    spark_html = sparkline(spark_values, tone) if spark_values else ""
    return (
        f"<div class='gp-source-card'>"
        f"<div class='gp-source-head'>"
        f"<div class='gp-source-name'><span style='font-size:16px'>{icon}</span>{name}</div>"
        f"</div>"
        f"<div class='gp-source-count'>{count}</div>"
        f"<div class='gp-source-meta'>{meta}</div>"
        f"{spark_html}"
        f"</div>"
    )


def heat_strip(cells: list, empty_label: str = "No anomalies detected in this window.") -> str:
    """cells: [{'title': tooltip str, 'tone': COLORS key}] — a compact density strip,
    used for the anomaly timeline on the Command Center.
    """
    if not cells:
        return f"<div class='gp-card' style='color:{COLORS['muted']};font-size:13px'>{empty_label}</div>"
    blocks = "".join(
        f"<div title='{c['title']}' style='width:10px;height:26px;border-radius:3px;"
        f"background:{COLORS.get(c.get('tone','red'), c.get('tone','red'))};opacity:0.85;'></div>"
        for c in cells
    )
    return (
        f"<div class='gp-card' style='display:flex; flex-wrap:wrap; gap:4px; "
        f"align-items:center; min-height:70px'>{blocks}"
        f"<div style='margin-left:12px; color:{COLORS['muted']}; font-family:IBM Plex Mono; "
        f"font-size:12px'>{len(cells)} detected events</div></div>"
    )