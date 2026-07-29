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
from geopulse.l1_ingestion_detection.settings import Settings
from geopulse.l1_ingestion_detection.store import SqliteStore
from geopulse.l2_orchestration.orchestrator import Orchestrator

CONFIG = Path(__file__).resolve().parents[2] / "config"

# Light per-theme enrichment the orchestrator will eventually do itself.
REGION_HINT = {
    "chokepoint_hormuz": "strait_of_hormuz",
    "chokepoint_suez": "suez",
    "armed_conflict_escalation": "middle_east",
    "market_crash": "global",
    "sanctions_exportcontrols": "asia_pacific",
}

st.set_page_config(page_title="GeoPulse · Impact Explorer", layout="wide")
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

run_clicked = st.sidebar.button("Run Agentic Pipeline (Live)", use_container_width=True)

st.sidebar.markdown("<br>", unsafe_allow_html=True)
severity = st.sidebar.slider("Severity", 1, 5, themes[theme_key]["severity_default"])

st.sidebar.markdown("<br>", unsafe_allow_html=True)
st.sidebar.markdown(
    f"category&nbsp; {theme.badge(category.replace('_', ' ').title(), 'blue')}", unsafe_allow_html=True
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

settings = Settings()
store = SqliteStore(settings)
orchestrator = Orchestrator(settings, store, agents={
    "analogy": AnalogyAgent(llm=llm),
    "transmission_reasoner": TransmissionReasoner(llm=llm)
})

if run_clicked:
    with st.spinner("Running Agentic Orchestration Pipeline (Nodes 4-8)..."):
        state.apply(orchestrator._safe_run(orchestrator.analogy, state))
        delta5 = orchestrator._safe_run(orchestrator.transmission, state)
        state.apply(delta5)
        
        if state.transmission_chains:
            state.apply(orchestrator._safe_run(orchestrator.sentiment, state))
            state.apply(orchestrator._safe_run(orchestrator.quant, state))
            orchestrator._maker_checker_gate(state)
        
        st.session_state.graph_state = state
        st.session_state.delta5 = delta5
        st.session_state.last_theme = theme_key

if "graph_state" not in st.session_state:
    st.info("Click the **Run Agentic Pipeline (Live)** button in the sidebar to begin.")
    st.stop()

state = st.session_state.graph_state
delta5 = st.session_state.delta5
chains = state.transmission_chains
analogies = state.analogies

# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #
st.markdown(
    theme.section_header(
        "GeoPulse · Orchestration Engine", "Analogy → Transmission Reasoner",
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
    st.markdown(theme.stat_card("Event", theme_key.replace('_', ' ').title(), category.replace('_', ' ').title(), "blue"), unsafe_allow_html=True)
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
            f"{theme.badge(a.category.replace('_', ' ').title(), 'blue')} {theme.badge((a.region or 'n/a').replace('_', ' ').title(), 'muted')}"
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


def get_downstream_signals(state: GraphState, c):
    sector = c.sector
    etf = c.etf
    want_up = c.direction == "up"

    # Sentiment extraction
    sentiment_data = state.sentiment or {}
    sectors_sent = sentiment_data.get("sectors", [])
    sent_dict = next((s for s in sectors_sent if s["sector"] == sector), None)
    if sent_dict:
        tone_score = sent_dict.get("mood_score", 0.0)
        tone_label = "Bullish" if tone_score > 0.15 else "Bearish" if tone_score < -0.15 else "Mixed"
        tone_tone = "green" if tone_score > 0.15 else "red" if tone_score < -0.15 else "amber"
    else:
        tone_score, tone_label, tone_tone = 0.0, "Unknown", "muted"

    # Quant extraction
    quant_data = state.quant_signals or {}
    sectors_quant = quant_data.get("sectors", [])
    quant_dict = next((s for s in sectors_quant if s.get("etf") == etf), None)
    if quant_dict:
        quant_delta = quant_dict.get("pct_move", 0.0)
        quant_confirms = (quant_delta >= 0) == want_up
    else:
        quant_delta, quant_confirms = 0.0, False

    # Maker Checker extraction
    checker_review = state.checker_review or {}
    checker_verdict = checker_review.get("verdict", "pending")
    checker_critique = checker_review.get("critique", "")
    
    verdict_data = state.verdict or {}
    verdict_calls = verdict_data.get("calls", [])
    final_call = next((v for v in verdict_calls if v["sector"] == sector), None)

    return {
        "sentiment": {"score": tone_score, "label": tone_label, "tone": tone_tone},
        "quant": {"delta": quant_delta, "confirms": quant_confirms},
        "checker": {"verdict": checker_verdict, "critique": checker_critique},
        "final_rationale": final_call["rationale"] if final_call else None
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

    sig = get_downstream_signals(state, c)
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
        f"<b>{sentiment['score']:+.2f}</b> ({sentiment['label']}). "
    )
    quant_tip = (
        f"{c.etf} is <b>{quant['delta']:+.1f}%</b> today. "
        f"{'Confirms' if quant['confirms'] else 'Contradicts'} the thesis direction. "
    )
    if checker["critique"]:
        checker_tip = checker["critique"]
    else:
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

    rationale_text = sig["final_rationale"]
    box_title = "Why the model concluded this"
    if not rationale_text:
        if checker["verdict"] == "escalate":
             rationale_text = f"<b>⚠️ ESCALATED BY MAKER-CHECKER (phi4-mini):</b> {checker['critique']}"
             box_title = "Maker-Checker Intercept"
        elif checker["verdict"] == "revise":
             rationale_text = f"<b>⚠️ REVISING:</b> {checker['critique']}"
             box_title = "Maker-Checker Intercept"
        else:
             rationale_text = "Pending review."
             
    st.markdown(
        theme.why_box(
            box_title,
            rationale_text
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
            frm_clean = h.frm.replace('_', ' ').title()
            to_clean = h.to.replace('_', ' ').title()
            source_file = h.citation.split(':')[0] if ':' in h.citation else h.citation
            st.markdown(
                f"&nbsp;&nbsp;{i}. **{frm_clean}** —*{h.relation}*→ **{to_clean}**  \n"
                f"&nbsp;&nbsp;<span style='color:{theme.COLORS['muted']};font-size:0.8rem'>↳ Source: {source_file}</span>",
                unsafe_allow_html=True,
            )
        st.markdown("**3. Sentiment Agent (Node 6)**")
        st.markdown(f"&nbsp;&nbsp;{sentiment_tip}", unsafe_allow_html=True)
        st.markdown("**4. Quantitative Signals Agent (Node 7)**")
        st.markdown(f"&nbsp;&nbsp;{quant_tip}", unsafe_allow_html=True)
        st.markdown("**5. Maker-Checker (Node 8)**")
        st.markdown(f"&nbsp;&nbsp;{checker_tip}", unsafe_allow_html=True)
        st.markdown("**6. Report Tool (Node 9)**")
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