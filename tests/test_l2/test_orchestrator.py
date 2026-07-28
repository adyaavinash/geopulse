"""Orchestrator hub tests. All offline (no Azure, no Ollama, no network) —
Analogy/Transmission run for real against the repo's own seed config (same
pattern as test_analogy.py/test_transmission.py); Sentiment/Quant Signals and
the maker-checker's LLM call are injected fakes so this suite tests the
orchestrator's *wiring* (dispatch order, plan logging, fail-open dispatch,
the revise/escalate loop), not agent 6/7's own scoring logic (that's covered
by test_sentiment_agent.py / test_quant_signals_agent.py) or the checker's
own bounded-retry logic (test_maker_checker.py)."""

from __future__ import annotations

from geopulse.l1_ingestion_detection.models import AnomalySignal
from geopulse.l1_ingestion_detection.settings import Settings
from geopulse.l1_ingestion_detection.store import SqliteStore
from geopulse.l2_orchestration.agents.analogy_agent import AnalogyAgent
from geopulse.l2_orchestration.agents.maker_checker import MAX_RETRIES, CheckerReview
from geopulse.l2_orchestration.agents.transmission_reasoner import TransmissionReasoner
from geopulse.l2_orchestration.llm import LLMResponse
from geopulse.l2_orchestration.orchestrator import Orchestrator, build_graph, classify
from geopulse.l2_orchestration.state import StateDelta


# --------------------------------------------------------------------------- #
# fakes
# --------------------------------------------------------------------------- #
class FakeLLM:
    """Same deterministic stand-in used by test_analogy.py / test_transmission.py."""

    def __init__(self, available: bool, text: str = "") -> None:
        self._available = available
        self._text = text
        self.calls = 0

    @property
    def available(self) -> bool:
        return self._available

    def complete(self, prompt, *, tier="reasoning", system=None):
        self.calls += 1
        return LLMResponse(text=self._text, model="fake", tokens=123)


class FakeSpokeAgent:
    """Duck-typed BaseAgent stand-in for Sentiment/Quant Signals — the
    orchestrator only ever calls `.name` and `.run(state)`."""

    def __init__(self, name: str, delta: StateDelta | None = None, error: Exception | None = None):
        self.name = name
        self.tier = "cheap"
        self._delta = delta
        self._error = error
        self.calls = 0

    def run(self, state):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._delta


def _fake_checker(verdict: str):
    def _call(prompt, draft, evidence):
        return CheckerReview(verdict=verdict, critique=f"fake {verdict}", objections=(
            [] if verdict == "approve" else ["fake objection"]
        ))
    return _call


def _hormuz_signal() -> AnomalySignal:
    return AnomalySignal(
        theme="chokepoint_hormuz", score=8.42, source_types=["news", "social"],
        window_minutes=60, is_synthetic=True,
    )


def _sentiment_delta(stance: str = "confirm") -> StateDelta:
    return StateDelta(
        agent="sentiment",
        sentiment={"sectors": [{"sector": "energy", "stance": stance, "mood_score": -0.4}]},
    )


def _quant_delta(stance: str = "confirm") -> StateDelta:
    return StateDelta(
        agent="quant_signals",
        quant_signals={
            "vix_pct_move": 12.0,
            "sectors": [{"sector": "energy", "etf": "XLE", "stance": stance, "pct_move": 3.0}],
        },
    )


def _env(tmp_path) -> tuple[Settings, SqliteStore]:
    settings = Settings(sqlite_path=str(tmp_path / "orchestrator_test.db"), dry_run=True)
    return settings, SqliteStore(settings)


def _orchestrator(tmp_path, *, sentiment=None, quant=None, checker_llm_call=None) -> Orchestrator:
    settings, store = _env(tmp_path)
    agents = {
        "analogy": AnalogyAgent(llm=FakeLLM(available=False)),
        "transmission_reasoner": TransmissionReasoner(llm=FakeLLM(available=False)),
        "sentiment": sentiment or FakeSpokeAgent("sentiment", delta=_sentiment_delta()),
        "quant_signals": quant or FakeSpokeAgent("quant_signals", delta=_quant_delta()),
    }
    return Orchestrator(settings, store, agents=agents, checker_llm_call=checker_llm_call)


# --------------------------------------------------------------------------- #
# classify()
# --------------------------------------------------------------------------- #
def test_classify_looks_up_event_taxonomy():
    event = classify(_hormuz_signal())
    assert event.category == "chokepoint_disruption"
    assert event.severity == 5
    assert event.theme == "chokepoint_hormuz"


def test_classify_unknown_theme_defaults_category_to_theme():
    signal = AnomalySignal(
        theme="totally_unmapped_theme", score=1.0, source_types=["news"],
        window_minutes=60, is_synthetic=True,
    )
    event = classify(signal)
    assert event.category == "totally_unmapped_theme"
    assert event.severity == 3


# --------------------------------------------------------------------------- #
# full pipeline — happy path
# --------------------------------------------------------------------------- #
def test_pipeline_dispatches_all_four_spokes_in_order(tmp_path):
    orch = _orchestrator(tmp_path, checker_llm_call=_fake_checker("approve"))
    state = orch.invoke({"anomaly": _hormuz_signal()})

    assert [c.agent for c in state.plan] == [
        "analogy", "transmission_reasoner", "sentiment", "quant_signals",
    ]
    assert state.transmission_chains, "seed graph should map hormuz -> oil_supply_shock"
    assert state.sentiment is not None
    assert state.quant_signals is not None


def test_pipeline_approve_sets_verdict(tmp_path):
    orch = _orchestrator(tmp_path, checker_llm_call=_fake_checker("approve"))
    state = orch.invoke({"anomaly": _hormuz_signal()})

    assert state.checker_review["verdict"] == "approve"
    assert state.verdict is not None
    assert state.verdict["event_id"] == state.event.signal_id
    assert len(state.verdict["calls"]) == len(state.transmission_chains)


def test_pipeline_accepts_bare_signal_without_dict_wrapper(tmp_path):
    orch = _orchestrator(tmp_path, checker_llm_call=_fake_checker("approve"))
    state = orch.invoke(_hormuz_signal())
    assert state.verdict is not None


# --------------------------------------------------------------------------- #
# no transmission channel -> nothing to call, downstream never dispatched
# --------------------------------------------------------------------------- #
def test_no_channel_skips_downstream_spokes_and_verdict(tmp_path):
    sentiment = FakeSpokeAgent("sentiment", delta=_sentiment_delta())
    quant = FakeSpokeAgent("quant_signals", delta=_quant_delta())
    orch = _orchestrator(tmp_path, sentiment=sentiment, quant=quant,
                          checker_llm_call=_fake_checker("approve"))

    signal = AnomalySignal(
        theme="totally_unmapped_theme", score=1.0, source_types=["news"],
        window_minutes=60, is_synthetic=True,
    )
    state = orch.invoke({"anomaly": signal})

    assert state.transmission_chains == []
    assert state.verdict is None
    assert state.checker_review is None
    assert [c.agent for c in state.plan] == ["analogy", "transmission_reasoner"]
    assert sentiment.calls == 0
    assert quant.calls == 0


# --------------------------------------------------------------------------- #
# revise -> bounded retry -> forced escalate (mirrors test_maker_checker.py)
# --------------------------------------------------------------------------- #
def test_persistent_revise_forces_escalate(tmp_path):
    orch = _orchestrator(tmp_path, checker_llm_call=_fake_checker("revise"))
    state = orch.invoke({"anomaly": _hormuz_signal()})

    assert state.checker_review["verdict"] == "escalate"
    assert state.verdict is None
    assert any("exhausted" in obj for obj in state.checker_review["objections"])
    assert state.checker_review["retry_count"] == MAX_RETRIES


def test_escalate_on_first_review_stops_immediately(tmp_path):
    orch = _orchestrator(tmp_path, checker_llm_call=_fake_checker("escalate"))
    state = orch.invoke({"anomaly": _hormuz_signal()})

    assert state.checker_review["verdict"] == "escalate"
    assert state.checker_review["retry_count"] == 0
    assert state.verdict is None


# --------------------------------------------------------------------------- #
# fail-open dispatch
# --------------------------------------------------------------------------- #
def test_sentiment_failure_does_not_abort_the_run(tmp_path):
    failing_sentiment = FakeSpokeAgent("sentiment", error=RuntimeError("reddit is down"))
    orch = _orchestrator(tmp_path, sentiment=failing_sentiment,
                          checker_llm_call=_fake_checker("approve"))
    state = orch.invoke({"anomaly": _hormuz_signal()})

    # the spoke was attempted (logged to the plan) even though it failed
    assert "sentiment" in [c.agent for c in state.plan]
    assert failing_sentiment.calls == 1
    # its delta never applied -> sentiment stays unset, but the run still
    # reached a verdict via quant + the transmission chains alone
    assert state.sentiment is None
    assert state.quant_signals is not None
    assert state.verdict is not None


# --------------------------------------------------------------------------- #
# build_graph() wiring
# --------------------------------------------------------------------------- #
def test_build_graph_returns_invokable_orchestrator(tmp_path):
    settings, store = _env(tmp_path)
    graph = build_graph(settings, store)
    assert isinstance(graph, Orchestrator)
    assert callable(graph.invoke)
    # default spokes are the real BaseAgent implementations, wired to this
    # orchestrator's own settings/store rather than each grabbing its own
    assert graph.sentiment.settings is settings
    assert graph.sentiment.store is store
    assert graph.quant.settings is settings
    assert graph.quant.store is store


def test_final_state_supports_dict_like_get(tmp_path):
    orch = _orchestrator(tmp_path, checker_llm_call=_fake_checker("approve"))
    state = orch.invoke({"anomaly": _hormuz_signal()})
    # matches function_app.py's `final_state.get("verdict")` queue-trigger contract
    assert state.get("verdict") == state.verdict
    assert state.get("nonexistent_field", "default") == "default"
