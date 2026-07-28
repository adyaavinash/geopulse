"""GeoPulse L2 explorer — Analogy (Node 4) → Transmission Reasoner (Node 5).

A dev/demo surface (NOT the production verdict dashboard) that runs the two
upstream agents live so you can watch the agentic RAG retrieve historical
analogues and feed the causal-chain reasoner. House theme applied.

    streamlit run l3_dashboard/transmission_explorer.py
"""

from __future__ import annotations

import random
from pathlib import Path

import streamlit as st
import yaml

import sys
from pathlib import Path
root = Path(__file__).resolve().parents[2]
if str(root / "src") not in sys.path:
    sys.path.insert(0, str(root / "src"))
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

import theme
from geopulse.l2_orchestration.agents.analogy_agent import AnalogyAgent
from geopulse.l2_orchestration.agents.transmission_reasoner import TransmissionReasoner
from geopulse.l2_orchestration.llm import get_llm_client
from geopulse.l2_orchestration.state import EventContext, GraphState
from geopulse.l2_orchestration.tools.graph_tool import get_graph_tool

CONFIG = Path(__file__).resolve().parents[2] / "config"

# Light per-theme enrichment the orchestrator will eventually do itself.
REGION_HINT = {
    "chokepoint_hormuz": "strait_of_hormuz",
    "chokepoint_suez": "suez",
    "armed_conflict_escalation": "middle_east",
    "market_crash": "global",
    "sanctions_exportcontrols": "asia_pacific",
}

st.set_page_config(page_title="GeoPulse · L2 Explorer", layout="wide")
theme.inject()


@st.cache_data
def load_taxonomies():
    themes = yaml.safe_load(open(CONFIG / "event_taxonomy.yaml"))["themes"]
    return themes


themes = load_taxonomies()
graph = get_graph_tool()

theme.render_sidebar()

# --------------------------------------------------------------------------- #
# Sidebar — pick the event (Inject into custom sidebar)
# --------------------------------------------------------------------------- #
st.sidebar.markdown("<br><br>", unsafe_allow_html=True)
st.sidebar.markdown(theme.kicker("Simulate an event"), unsafe_allow_html=True)
theme_key = st.sidebar.selectbox("Theme (what L1 detected)", list(themes.keys()), label_visibility="collapsed")
category = themes[theme_key]["category"]

st.sidebar.markdown("<br>", unsafe_allow_html=True)
severity = st.sidebar.slider("Severity", 1, 5, themes[theme_key]["severity_default"])

st.sidebar.markdown("<br>", unsafe_allow_html=True)
st.sidebar.markdown(
    f"category&nbsp; {theme.badge(category, 'blue')}", unsafe_allow_html=True
)

st.sidebar.markdown("<br><br>", unsafe_allow_html=True)
st.sidebar.markdown("<div class='gp-rule'></div>", unsafe_allow_html=True)
st.sidebar.markdown("<br>", unsafe_allow_html=True)

llm = get_llm_client()
mode = theme.badge("AZURE LLM", "green") if llm.available else theme.badge("OFFLINE", "muted")
st.sidebar.markdown(f"**Reasoning:** {mode}", unsafe_allow_html=True)
if not llm.available:
    st.sidebar.caption(
        "No Azure creds — confidences are graph priors, analogues use the hashing "
        "embedder. Set the Azure env vars for LLM reasoning + real embeddings."
    )
st.sidebar.markdown("<br><br>", unsafe_allow_html=True)

# --------------------------------------------------------------------------- #
# Run Node 4 then Node 5 (Node 5 reads the analogies Node 4 wrote)
# --------------------------------------------------------------------------- #
channels = graph.channels_for_event(category)
commodities = graph.raised_factors(channels[0]) if channels else []
event = EventContext(
    signal_id="explorer",
    theme=theme_key,
    category=category,
    severity=severity,
    region=REGION_HINT.get(theme_key),
    commodities=commodities,
)
state = GraphState(event=event)

state.apply(AnalogyAgent(llm=llm).run(state))          # Node 4 → state.analogies
delta5 = TransmissionReasoner(llm=llm).run(state)      # Node 5 reads analogies
state.apply(delta5)
chains = state.transmission_chains
analogies = state.analogies

# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #
st.markdown(
    theme.section_header(
        "GeoPulse · L2 Orchestration", "Analogy → Transmission Reasoner",
        "Given a geopolitical shock: retrieve historical analogues with measured returns "
        "(Node 4), then walk the causal graph to sector impacts (Node 5). Every hop cited. "
        "Decision-support, not investment advice."
    ),
    unsafe_allow_html=True,
)

if not chains:
    st.warning(f"No transmission channel is mapped for category **{category}** yet.")
    st.stop()

ups = [c for c in chains if c.direction == "up"]
downs = [c for c in chains if c.direction == "down"]
m1, m2, m3, m4 = st.columns(4)
with m1:
    st.markdown(theme.stat_card("Event", theme_key, category, "blue"), unsafe_allow_html=True)
with m2:
    st.markdown(theme.stat_card("Analogues", str(len(analogies)), "Node 4 retrieval", "muted"), unsafe_allow_html=True)
with m3:
    sector_tone = "green" if len(ups) >= len(downs) else "red"
    st.markdown(
        theme.stat_card("Sectors ↑ / ↓", f"{len(ups)} / {len(downs)}",
                         f"{len(ups)} rising · {len(downs)} falling", sector_tone),
        unsafe_allow_html=True,
    )
with m4:
    st.markdown(theme.stat_card("Cited edges", str(len(delta5.evidence)), "Node 5 reasoning", "amber"), unsafe_allow_html=True)
st.write("")


# --------------------------------------------------------------------------- #
# Node 4 — historical analogues
# --------------------------------------------------------------------------- #
st.markdown(theme.section_header("Node 4 · Agentic RAG", "Historical Analogues"), unsafe_allow_html=True)
acols = st.columns(min(len(analogies), 4) or 1)
for col, a in zip(acols, analogies):
    with col:
        rets = " ".join(
            theme.badge(f"{k} {v:+.1f}%", "green" if v >= 0 else "red")
            for k, v in list(a.measured_returns.items())[:5]
        )
        st.markdown(
            f"<div class='gp-card'>"
            f"<div class='gp-mono' style='color:{theme.COLORS['muted']};font-size:11px'>"
            f"{a.date} · sim {a.similarity:.2f}</div>"
            f"<div style='font-weight:600;color:{theme.COLORS['ink']};margin:4px 0 8px'>{a.title}</div>"
            f"{theme.badge(a.category, 'blue')} {theme.badge(a.region or 'n/a', 'muted')}"
            f"<div style='margin-top:10px'>{rets}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
st.divider()


# --------------------------------------------------------------------------- #
# Node 5 — sector impact, cross-referenced against the analogues
# --------------------------------------------------------------------------- #
def analogue_evidence(etf: str) -> str:
    """Pull this ETF's measured return from each analogue — the Node 4 → Node 5 link."""
    out = []
    for a in analogies:
        if etf in a.measured_returns:
            v = a.measured_returns[etf]
            out.append(theme.badge(f"{a.event_id.split('_')[0]} {v:+.1f}%",
                                   "green" if v >= 0 else "red"))
    return " ".join(out)


def mock_downstream_signals(c):
    """Sentiment (Node 6), Quant Signals (Node 7), and Maker-Checker (Node 8)
    aren't wired to real state yet (see docs/repo_structure_v2_whiteboard.md —
    only Analogy/Node 4 and Transmission Reasoner/Node 5 are real). Mocked
    here, deterministically per sector so it doesn't reshuffle on every
    Streamlit rerun, but shaped exactly like the whiteboard's spec for each
    node so the demo is honest about what's real vs illustrative."""
    rnd = random.Random(hash(c.sector) % 100000)
    want_up = c.direction == "up"

    tone_score = rnd.uniform(-1, 1)
    if rnd.random() < 0.7:  # mostly agrees with the thesis, not rigged 100%
        tone_score = abs(tone_score) if want_up else -abs(tone_score)
    tone_label = "Bullish" if tone_score > 0.15 else "Bearish" if tone_score < -0.15 else "Mixed"
    tone_tone = "green" if tone_score > 0.15 else "red" if tone_score < -0.15 else "amber"

    quant_delta = rnd.uniform(0.1, 3.4) * (1 if want_up else -1) * (1 if rnd.random() < 0.75 else -1)
    quant_confirms = (quant_delta >= 0) == want_up

    checker_revise = rnd.random() < 0.2
    checker_verdict = "revise" if checker_revise else "approve"

    return {
        "sentiment": {"score": tone_score, "label": tone_label, "tone": tone_tone},
        "quant": {"delta": quant_delta, "confirms": quant_confirms},
        "checker": {"verdict": checker_verdict},
    }


def render_chain(c):
    tone = "green" if c.direction == "up" else "red"
    arrow = "▲" if c.direction == "up" else "▼"
    color = theme.COLORS[tone]
    st.markdown(
        f"<span style='color:{color};font-weight:700;font-size:1.05rem'>{arrow} {c.sector}</span>"
        f" &nbsp; {theme.badge(c.etf, tone)}",
        unsafe_allow_html=True,
    )
    st.progress(c.confidence, text=f"confidence {c.confidence:.0%}")

    sig = mock_downstream_signals(c)
    sentiment, quant, checker = sig["sentiment"], sig["quant"], sig["checker"]

    # ------------------------------------------------------------------ #
    # The 6 agents from the whiteboard, per sector. Analogy + Transmission
    # Reasoner are real (this page runs them live); Sentiment, Quant,
    # Maker-Checker, and Report Tool are mocked — hover each for its
    # per-sector explanation.
    # ------------------------------------------------------------------ #
    top_analogy = max(analogies, key=lambda a: a.similarity) if analogies else None
    analogy_tip = (
        f"Retrieved <b>{len(analogies)}</b> historical analogues for this event category. "
        f"Closest: <b>{top_analogy.title}</b> (sim {top_analogy.similarity:.2f}), "
        f"{c.etf} moved <b>{top_analogy.measured_returns.get(c.etf, 0):+.1f}%</b>."
        if top_analogy else "No analogues retrieved for this category."
    )
    transmission_tip = (
        f"Walked <b>{len(c.hops)}</b> cited graph hop(s) via channel <b>{c.channel}</b>. "
        f"{c.mechanism}"
    )
    sentiment_tip = (
        f"Public tone across news + Reddit chatter for {c.sector}: "
        f"<b>{sentiment['score']:+.2f}</b> ({sentiment['label']}). Cheap-tier model, "
        f"mocked — Node 6 isn't wired to a live feed yet."
    )
    quant_tip = (
        f"{c.etf} is <b>{quant['delta']:+.1f}%</b> today. "
        f"{'Confirms' if quant['confirms'] else 'Contradicts'} the thesis direction. "
        f"Mocked — Node 7 would pull this from yfinance/Alpha Vantage live."
    )
    checker_tip = (
        "Citation present, analogues support direction, confidence proportionate "
        "to evidence — <b>approved</b>."
        if checker["verdict"] == "approve" else
        "Flagged: confidence looked high relative to a single weak analogue and "
        "an unaddressed quant contradiction — sent back for <b>revision</b>."
    )
    report_tip = (
        "Renders the approved verdict to the analyst brief and persists it — "
        "no LLM reasoning of its own, per the whiteboard (Node 9)."
    )

    chips = [
        theme.agent_chip("🔎", "Analogy", "retrieved", "blue", analogy_tip),
        theme.agent_chip("🕸️", "Transmission", "traced", "purple", transmission_tip),
        theme.agent_chip("💬", "Sentiment", sentiment["label"].lower(), sentiment["tone"], sentiment_tip),
        theme.agent_chip("📊", "Quant", "confirms" if quant["confirms"] else "contradicts",
                          "green" if quant["confirms"] else "red", quant_tip),
        theme.agent_chip("⚖️", "Maker-Checker", checker["verdict"],
                          "green" if checker["verdict"] == "approve" else "amber", checker_tip),
        theme.agent_chip("📄", "Report Tool", "published", "muted", report_tip),
    ]
    st.markdown(theme.agent_row(chips), unsafe_allow_html=True)

    confirm_clause = "confirming" if quant["confirms"] else "running against"
    checker_clause = (
        "Maker-Checker approved the call as evidence-proportionate."
        if checker["verdict"] == "approve" else
        "Maker-Checker flagged this for revision — confidence outpaced the evidence gathered."
    )
    st.markdown(
        theme.why_box(
            "Why the model concluded this",
            f"{c.mechanism} Public sentiment reads <b>{sentiment['label'].lower()}</b> "
            f"({sentiment['score']:+.2f}), and {c.etf} is {confirm_clause} the thesis at "
            f"<b>{quant['delta']:+.1f}%</b> today. {checker_clause}",
        ),
        unsafe_allow_html=True,
    )

    ev = analogue_evidence(c.etf)
    if ev:
        st.markdown(
            f"<span class='gp-mono' style='color:{theme.COLORS['muted']};font-size:11px'>"
            f"analogue returns&nbsp;</span>{ev}",
            unsafe_allow_html=True,
        )

    with st.expander("Agent Reasoning & Citations — all 6 nodes"):
        st.markdown("**1. Analogy Agent (Node 4)** — real, retrieved live above")
        st.markdown(f"&nbsp;&nbsp;{analogy_tip}", unsafe_allow_html=True)
        st.markdown("**2. Transmission Reasoner (Node 5)** — real, cited hops")
        for i, h in enumerate(c.hops, 1):
            st.markdown(
                f"&nbsp;&nbsp;{i}. `{h.frm}` —*{h.relation}*→ `{h.to}`  \n"
                f"&nbsp;&nbsp;<span style='color:{theme.COLORS['muted']};font-size:0.8rem'>↳ Citation: {h.citation}</span>",
                unsafe_allow_html=True,
            )
        st.markdown("**3. Sentiment Agent (Node 6)** — mocked")
        st.markdown(f"&nbsp;&nbsp;{sentiment_tip}", unsafe_allow_html=True)
        st.markdown("**4. Quantitative Signals Agent (Node 7)** — mocked")
        st.markdown(f"&nbsp;&nbsp;{quant_tip}", unsafe_allow_html=True)
        st.markdown("**5. Maker-Checker (Node 8)** — mocked")
        st.markdown(f"&nbsp;&nbsp;{checker_tip}", unsafe_allow_html=True)
        st.markdown("**6. Report Tool (Node 9)** — mocked")
        st.markdown(f"&nbsp;&nbsp;{report_tip}", unsafe_allow_html=True)
    st.write("")


st.markdown(theme.section_header("Node 5 · Transmission Reasoner", "Sector Impact"), unsafe_allow_html=True)
left, right = st.columns(2)
with left:
    st.subheader("📈 Likely to rise")
    for c in sorted(ups, key=lambda x: -x.confidence):
        render_chain(c)
with right:
    st.subheader("📉 Likely to fall")
    for c in sorted(downs, key=lambda x: -x.confidence):
        render_chain(c)

st.divider()
with st.expander("Where this data comes from"):
    st.markdown(
        f"""
- **Input event** — `theme={theme_key}` would arrive from **L1** as an `AnomalySignal`
  (`tests/fixtures/anomaly_signal.json`). Here it's simulated from the sidebar.
- **theme → category** — `config/event_taxonomy.yaml`
- **Node 4 corpus** — `config/knowledge/event_corpus.yaml` (retrieved via cosine
  similarity; embedder mode: **{AnalogyAgent(llm=llm).retrieval.embedder.mode}**)
- **category → channel → up/down sectors** — `config/transmission_channels.yaml`
  (channel walked: **{channels}**)
- **sector → ETF** — `config/sector_taxonomy.yaml`
- **mechanism & confidence** — graph priors offline; Azure OpenAI (`llm.py`) when configured.
"""
    )