"""L2 hub — orchestrator-centric hub-and-spoke controller.

Whiteboard contract: consume AnomalySignal -> classify -> plan -> dispatch
spokes (Analogy | Transmission | Sentiment | Quant) -> synthesize draft
verdict -> maker_checker -> report_tool. Log the plan to state for audit.

This is a plain controller (not LangGraph — the whiteboard explicitly leaves
that choice open: "Still implementable on LangGraph... or as a plain async
controller if Person 2 prefers less framework"). Kept synchronous and
sequential rather than dispatching spokes concurrently: SqliteStore's
connection is not thread-safe, and the whole L2 slice is meant to run with
zero extra infrastructure, so correctness here wins over a parallelism this
project's storage layer can't yet safely support.

Dispatch order — and why it isn't the flat "all four in parallel" the
whiteboard sketches:
  1. Analogy       — evidence base other spokes can reference.
  2. Transmission  — the moat: produces the only sectors this run has any
                      cited basis to make a call about. If no channel maps
                      to this event's category, there is nothing to hand a
                      verdict on, so the run stops here (mirrors base_agent's
                      "an agent that cannot cite does not get to assert").
  3. Sentiment     — confirms/contradicts per the graph-derived sectors from
                      step 2 (falls back to its own theme-keyed map only for
                      standalone runs where Transmission hasn't executed).
  4. Quant signals — same graph-derived sectors, same confirm/contradict role.
  5. Maker-checker — the contrarian gate on the synthesized draft.

A flaky sentiment/quant dependency (Reddit, yfinance, a local Ollama call)
degrades to "no delta, noted" rather than aborting the run — the same
fail-open convention agent 6/7 already apply internally to their own network
calls.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path

import yaml

from geopulse.l1_ingestion_detection.models import AnomalySignal
from geopulse.l1_ingestion_detection.settings import Settings
from geopulse.l1_ingestion_detection.store import SqliteStore
from geopulse.l2_orchestration.agents.analogy_agent import AnalogyAgent
from geopulse.l2_orchestration.agents.base_agent import BaseAgent
from geopulse.l2_orchestration.agents.maker_checker import (
    DraftVerdict,
    EvidenceBundle,
    LlmCall,
    SectorCall,
    _default_llm_call,
    run_maker_checker,
)
from geopulse.l2_orchestration.agents.quant_signals_agent import QuantSignalsAgent
from geopulse.l2_orchestration.agents.sentiment_agent import SentimentAgent
from geopulse.l2_orchestration.agents.transmission_reasoner import TransmissionReasoner
from geopulse.l2_orchestration.state import AgentCall, EventContext, GraphState, StateDelta

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TAXONOMY_FILE = "event_taxonomy.yaml"


def _config_dir() -> Path:
    override = os.environ.get("GEOPULSE_CONFIG_DIR")
    return Path(override) if override else _REPO_ROOT / "config"


@lru_cache(maxsize=1)
def _load_taxonomy() -> dict:
    path = _config_dir() / _TAXONOMY_FILE
    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data.get("themes", {})


def classify(signal: AnomalySignal) -> EventContext:
    """Deterministic theme -> category/severity lookup. Absorbs v1's separate
    classifier agent per the whiteboard: this is a taxonomy lookup, not
    something that benefits from an LLM call."""
    entry = _load_taxonomy().get(signal.theme, {})
    return EventContext(
        signal_id=signal.id,
        theme=signal.theme,
        category=entry.get("category", signal.theme),
        severity=int(entry.get("severity_default", 3)),
        query=signal.query,
    )


class Orchestrator:
    """The hub. See module docstring for dispatch order and rationale."""

    def __init__(
        self,
        settings: Settings,
        store: SqliteStore,
        *,
        agents: dict[str, BaseAgent] | None = None,
        checker_llm_call: LlmCall | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        agents = agents or {}
        self.analogy = agents.get("analogy") or AnalogyAgent()
        self.transmission = agents.get("transmission_reasoner") or TransmissionReasoner()
        self.sentiment = agents.get("sentiment") or SentimentAgent(settings=settings, store=store)
        self.quant = agents.get("quant_signals") or QuantSignalsAgent(settings=settings, store=store)
        self._checker_llm_call = checker_llm_call or _default_llm_call

    def invoke(self, inputs: dict | AnomalySignal, config: dict | None = None) -> GraphState:
        signal = inputs["anomaly"] if isinstance(inputs, dict) else inputs
        event = classify(signal)
        state = GraphState(event=event)
        logger.info("Pipeline start: signal=%s theme=%s category=%s", signal.id, event.theme, event.category)

        state.plan.append(AgentCall(agent=self.analogy.name, reason="build the analogical evidence base"))
        state = state.apply(self._safe_run(self.analogy, state))

        state.plan.append(AgentCall(agent=self.transmission.name, reason="walk the causal graph for cited sectors"))
        state = state.apply(self._safe_run(self.transmission, state))

        if not state.transmission_chains:
            logger.warning(
                "No transmission chains for category=%s; nothing to make a cited "
                "call on, skipping downstream spokes and maker-checker", event.category,
            )
            return state

        state.plan.append(AgentCall(agent=self.sentiment.name, reason="confirm/contradict via public mood"))
        state = state.apply(self._safe_run(self.sentiment, state))

        state.plan.append(AgentCall(agent=self.quant.name, reason="confirm/contradict via live market data"))
        state = state.apply(self._safe_run(self.quant, state))

        self._maker_checker_gate(state)
        return state

    # ------------------------------------------------------------------ #
    # synthesis + maker-checker gate
    # ------------------------------------------------------------------ #
    def _maker_checker_gate(self, state: GraphState) -> None:
        draft = _draft_verdict(state)
        evidence = _evidence_bundle(state)
        retry_count = 0

        while True:
            review = run_maker_checker(
                draft, evidence, retry_count=retry_count, llm_call=self._checker_llm_call,
            )
            state.checker_review = review.model_dump(mode="json")

            if review.verdict == "approve":
                state.verdict = draft.model_dump(mode="json")
                return
            if review.verdict == "escalate":
                # Paused for a human — state.verdict stays None, matching the
                # existing function_app.py contract ("verdict is None" means
                # the run is checkpointed pending manual approval).
                logger.warning(
                    "Escalated for human review: event=%s objections=%s",
                    state.event.signal_id, review.objections,
                )
                return

            # "revise": bounded re-plan. A full LLM re-synthesis pass is
            # future work (see maker_checker.py's own wiring notes); this
            # deterministic confidence haircut is enough to let the bounded
            # retry loop actually converge today. run_maker_checker forces
            # verdict="escalate" once retry_count reaches MAX_RETRIES, so
            # this loop is bounded even though it looks unbounded here.
            retry_count += 1
            draft = _revise(draft)

    # ------------------------------------------------------------------ #
    # fail-open dispatch
    # ------------------------------------------------------------------ #
    def _safe_run(self, agent: BaseAgent, state: GraphState) -> StateDelta:
        """A flaky external dependency in one spoke must not take down the
        whole run — degrade to 'no delta' and note it, same convention
        agent 6/7 already use internally for their own network calls."""
        try:
            return agent.run(state)
        except Exception:
            logger.exception("%s failed; continuing without its signal", agent.name)
            return StateDelta(agent=agent.name, notes=f"{agent.name} failed; skipped")


def _draft_verdict(state: GraphState) -> DraftVerdict:
    """Reconcile transmission chains against sentiment/quant stances into
    sector calls. Absorbs v1's synthesis agent — deterministic reconciliation
    over evidence that already went through its own LLM reasoning upstream
    (in transmission_reasoner/analogy), not a fresh LLM creativity pass."""
    sentiment_by_sector = {s["sector"]: s for s in (state.sentiment or {}).get("sectors", [])}
    quant_by_sector = {s["sector"]: s for s in (state.quant_signals or {}).get("sectors", [])}

    calls: list[SectorCall] = []
    for chain in state.transmission_chains:
        confidence = chain.confidence
        sent = sentiment_by_sector.get(chain.sector)
        if sent and sent.get("stance") == "confirm":
            confidence = min(1.0, confidence + 0.05)
        elif sent and sent.get("stance") == "contradict":
            confidence = max(0.0, confidence - 0.1)

        quant = quant_by_sector.get(chain.sector)
        if quant and quant.get("stance") == "confirm":
            confidence = min(1.0, confidence + 0.05)
        elif quant and quant.get("stance") == "contradict":
            confidence = max(0.0, confidence - 0.1)

        cited_analogies = [a.event_id for a in state.analogies if chain.etf in a.measured_returns]
        calls.append(SectorCall(
            sector=chain.sector,
            direction="winner" if chain.direction == "up" else "loser",
            confidence=round(confidence, 3),
            rationale=chain.rationale or chain.mechanism
            or f"{chain.sector} sits on the {chain.direction} side of {chain.channel}",
            cited_transmission_edge=chain.citations[0] if chain.citations else None,
            cited_analogy_ids=cited_analogies,
        ))

    overall = round(sum(c.confidence for c in calls) / len(calls), 3) if calls else 0.0
    return DraftVerdict(
        event_id=state.event.signal_id,
        theme=state.event.theme,
        calls=calls,
        overall_confidence=overall,
    )


def _evidence_bundle(state: GraphState) -> EvidenceBundle:
    """Everything the checker is allowed to read, per maker_checker.py's
    EvidenceBundle contract."""
    quant = state.quant_signals or {}
    quant_by_ticker: dict[str, float] = {}
    if quant.get("vix_pct_move") is not None:
        quant_by_ticker["^VIX"] = quant["vix_pct_move"]
    for s in quant.get("sectors", []):
        if s.get("etf") and s.get("pct_move") is not None:
            quant_by_ticker[s["etf"]] = s["pct_move"]

    sentiment = state.sentiment or {}
    sentiment_by_sector = {
        s["sector"]: s["mood_score"] for s in sentiment.get("sectors", [])
    }

    return EvidenceBundle(
        transmission_chains=[c.mechanism for c in state.transmission_chains if c.mechanism],
        analogies=[
            {
                "id": a.event_id, "event": a.title,
                "similarity": a.similarity, "return_pct": a.measured_returns,
            }
            for a in state.analogies
        ],
        quant_signals=quant_by_ticker,
        sentiment=sentiment_by_sector,
    )


def _revise(draft: DraftVerdict) -> DraftVerdict:
    """Deterministic re-synthesis nudge for a bounded retry: shave confidence
    across every call since the checker found the draft overconfident. A real
    LLM re-synthesis pass informed by the checker's specific objections is
    future work; this keeps the bounded retry loop able to converge today
    rather than re-asking the checker the identical question."""
    revised_calls = [
        c.model_copy(update={"confidence": round(max(0.0, c.confidence - 0.15), 3)})
        for c in draft.calls
    ]
    overall = (
        round(sum(c.confidence for c in revised_calls) / len(revised_calls), 3)
        if revised_calls else 0.0
    )
    return draft.model_copy(update={"calls": revised_calls, "overall_confidence": overall})


def build_graph(settings: Settings, store: SqliteStore) -> Orchestrator:
    """Return an object with .invoke(inputs, config) -> final_state.
    L1's queue trigger already calls this signature."""
    return Orchestrator(settings, store)
