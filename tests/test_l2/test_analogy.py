"""Node 4 — Analogy agent (agentic RAG) tests. All offline (no Azure)."""

from __future__ import annotations

from geopulse.l2_orchestration.agents.analogy_agent import MAX_ROUNDS, AnalogyAgent
from geopulse.l2_orchestration.llm import LLMResponse
from geopulse.l2_orchestration.state import EventContext, GraphState
from geopulse.l2_orchestration.tools.retrieval_tool import RetrievalTool


class FakeLLM:
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


def _event(region="strait_of_hormuz") -> EventContext:
    return EventContext(
        signal_id="x",
        theme="chokepoint_hormuz",
        category="chokepoint_disruption",
        region=region,
        commodities=["crude", "jet_fuel"],
    )


def _state(region="strait_of_hormuz") -> GraphState:
    return GraphState(event=_event(region))


# --------------------------------------------------------------------------- #
# retrieval tool
# --------------------------------------------------------------------------- #
def test_retrieval_ranks_same_category_first():
    r = RetrievalTool.load()
    hits = r.search("hormuz strait crude oil tanker chokepoint closure", k=3)
    assert hits[0].event.id == "hormuz_tanker_2019"
    assert hits[0].event.category == "chokepoint_disruption"


def test_retrieval_category_filter():
    r = RetrievalTool.load()
    hits = r.search("bank crisis credit spreads crash", k=5, category="financial_shock")
    assert hits, "should find financial_shock analogues"
    assert all(h.event.category == "financial_shock" for h in hits)


# --------------------------------------------------------------------------- #
# analogy agent — offline
# --------------------------------------------------------------------------- #
def test_analogy_offline_returns_cited_analogues_with_returns():
    delta = AnalogyAgent(llm=FakeLLM(available=False)).run(_state())
    assert delta.agent == "analogy"
    assert delta.analogies, "should retrieve analogues"

    top = delta.analogies[0]
    assert top.event_id == "hormuz_tanker_2019"
    assert top.measured_returns, "each analogue carries measured sector returns"
    assert top.citation.startswith("knowledge/event_corpus.yaml:")
    assert delta.evidence  # citations roll up


def test_analogy_stops_early_when_sufficient():
    # region matches -> heuristic sufficient on round 1
    delta = AnalogyAgent(llm=FakeLLM(available=False)).run(_state())
    rounds = [ln for ln in delta.notes.split(" | ") if ln.startswith("round")]
    assert len(rounds) == 1


def test_analogy_loops_to_cap_when_never_sufficient():
    # region the corpus never matches -> region coverage always fails -> full cap
    delta = AnalogyAgent(llm=FakeLLM(available=False)).run(_state(region="atlantic"))
    rounds = [ln for ln in delta.notes.split(" | ") if ln.startswith("round")]
    assert len(rounds) == MAX_ROUNDS
    # still returns the best analogues it found rather than nothing
    assert delta.analogies


# --------------------------------------------------------------------------- #
# analogy agent — LLM path (stubbed)
# --------------------------------------------------------------------------- #
def test_analogy_llm_sufficient_stops_and_spends_tokens():
    llm = FakeLLM(available=True, text='{"sufficient": true, "reason": "covered"}')
    delta = AnalogyAgent(llm=llm).run(_state())
    rounds = [ln for ln in delta.notes.split(" | ") if ln.startswith("round")]
    assert len(rounds) == 1
    assert delta.token_spend == 123
    assert llm.calls == 1


def test_analogy_llm_reformulated_query_is_used():
    llm = FakeLLM(
        available=True,
        text='{"sufficient": false, "reason": "thin", "reformulated_query": "CUSTOM_QUERY_XYZ"}',
    )
    delta = AnalogyAgent(llm=llm).run(_state())
    assert "CUSTOM_QUERY_XYZ" in delta.notes          # the LLM's query drove round 2
    rounds = [ln for ln in delta.notes.split(" | ") if ln.startswith("round")]
    assert len(rounds) == MAX_ROUNDS                  # never satisfied -> capped
