"""GeoPulse house theme — the warm-parchment + amber look shared with the
compliance UI. Import and call ``inject()`` once at the top of any Streamlit
page; use ``COLORS`` and ``badge()`` for consistent accents.

Source of truth for the palette/fonts: the compliance project's regulatory UI
(Space Grotesk / IBM Plex Mono, cream paper, amber accent, semantic
blue/green/red/purple).
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

.stApp { background: var(--page); }
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
[data-testid="stMetricValue"] { font-weight:700; color:var(--ink) !important; }
[data-testid="stMetricLabel"] { color:var(--muted) !important; letter-spacing:.2px; }

/* Mono for code/badges */
code, kbd, .gp-mono { font-family:'IBM Plex Mono', monospace !important; }

/* Sidebar as parchment panel */
[data-testid="stSidebar"] {
  background:var(--paper); border-right:1px solid var(--line);
}

/* Cards: expanders + bordered containers */
[data-testid="stExpander"] {
  background:var(--paper); border:1px solid var(--line) !important;
  border-radius:14px !important; box-shadow:0 1px 3px rgba(0,0,0,.05);
}
[data-testid="stExpander"] summary { font-family:'IBM Plex Mono', monospace; font-size:.82rem; color:var(--text); }

/* Amber progress fill (confidence) */
[data-testid="stProgress"] div div div div { background:var(--amber); }

/* Amber slider track + handle */
[data-testid="stSlider"] [data-baseweb="slider"] div[role="slider"] { background:var(--amber) !important; }
[data-testid="stSlider"] [data-baseweb="slider"] > div > div > div { background:var(--amber) !important; }

/* Dividers a touch warmer */
hr { border-color:var(--line); }

/* Reusable badge/card classes */
.gp-badge {
  font-family:'IBM Plex Mono', monospace; font-size:10px; font-weight:600;
  letter-spacing:.4px; padding:3px 8px; border-radius:7px; display:inline-block;
}
.gp-card {
  background:var(--paper); border:1px solid var(--line); border-radius:16px;
  padding:16px 18px; box-shadow:0 1px 3px rgba(0,0,0,.05); margin-bottom:12px;
}
.gp-kicker {
  font-family:'IBM Plex Mono', monospace; font-size:11px; font-weight:600;
  letter-spacing:1.2px; text-transform:uppercase; color:var(--amber);
}
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
