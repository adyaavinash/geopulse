"""Node 5 — Transmission Reasoner tests. All offline (no Azure)."""

from __future__ import annotations

from geopulse.l2_orchestration.llm import LLMResponse
from geopulse.l2_orchestration.state import EventContext, GraphState
from geopulse.l2_orchestration.agents.transmission_reasoner import TransmissionReasoner
from geopulse.l2_orchestration.tools.graph_tool import GraphTool


# --------------------------------------------------------------------------- #
# fakes
# --------------------------------------------------------------------------- #
class FakeLLM:
    """Deterministic stand-in for the Azure client."""

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


def _hormuz_event() -> EventContext:
    return EventContext(
        signal_id="04848f4f680744f9",
        theme="chokepoint_hormuz",
        category="chokepoint_disruption",
        severity=5,
        commodities=["crude", "jet_fuel"],
    )


def _state() -> GraphState:
    return GraphState(event=_hormuz_event())


# --------------------------------------------------------------------------- #
# graph_tool
# --------------------------------------------------------------------------- #
def test_channel_mapping():
    g = GraphTool.load()
    assert g.channels_for_event("chokepoint_disruption") == ["oil_supply_shock"]
    assert g.channels_for_event("financial_shock") == ["equity_crash_contagion"]
    assert g.channels_for_event("statecraft") == ["regulatory_sanctions"]
    assert g.channels_for_event("nonexistent_category") == []


def test_walk_produces_cited_hops():
    g = GraphTool.load()
    chains = g.walk("chokepoint_disruption", "oil_supply_shock")
    by_sector = {c.sector: c for c in chains}

    assert by_sector["energy"].direction == "up"
    assert by_sector["airlines"].direction == "down"
    assert by_sector["energy"].etf == "XLE"

    # every hop of every chain carries a provenance citation
    for chain in chains:
        assert chain.hops, "chain must have at least one cited hop"
        assert all(h.citation for h in chain.hops)
    # path is event-category -> channel -> factors -> sector -> etf
    energy_path = [h.to for h in by_sector["energy"].hops]
    assert energy_path[0] == "oil_supply_shock"
    assert energy_path[-1] == "XLE"


# --------------------------------------------------------------------------- #
# transmission_reasoner — offline template path
# --------------------------------------------------------------------------- #
def test_reasoner_offline_produces_cited_chains():
    agent = TransmissionReasoner(llm=FakeLLM(available=False))
    delta = agent.run(_state())

    assert delta.agent == "transmission_reasoner"
    chains = delta.transmission_chains
    assert chains, "should produce chains from the graph even with no LLM"

    by_sector = {c.sector: c for c in chains}
    assert by_sector["energy"].direction == "up"
    assert by_sector["airlines"].direction == "down"

    # every chain has a mechanism narrative and cited evidence
    for c in chains:
        assert c.mechanism
        assert c.citations
    assert delta.evidence, "citations roll up into the evidence log"
    assert delta.token_spend == 0  # no LLM spend offline


def test_reasoner_no_channel_returns_empty():
    event = EventContext(signal_id="x", theme="unknown", category="uncharted")
    delta = TransmissionReasoner(llm=FakeLLM(available=False)).run(GraphState(event=event))
    assert delta.transmission_chains == []


# --------------------------------------------------------------------------- #
# transmission_reasoner — LLM path (stubbed)
# --------------------------------------------------------------------------- #
def test_reasoner_llm_can_drop_and_rescore():
    llm_json = """[
      {"sector": "energy", "keep": true, "confidence": 0.9,
       "mechanism": "Crude supply premium lifts integrated energy.", "rationale": "textbook"},
      {"sector": "materials", "keep": false, "confidence": 0.1,
       "mechanism": "", "rationale": "not exposed to this specific chokepoint"}
    ]"""
    agent = TransmissionReasoner(llm=FakeLLM(available=True, text=llm_json))
    delta = agent.run(_state())
    by_sector = {c.sector: c for c in delta.transmission_chains}

    # dropped sector is gone
    assert "materials" not in by_sector
    # rescored sector took the LLM's confidence + mechanism
    assert by_sector["energy"].confidence == 0.9
    assert "Crude supply premium" in by_sector["energy"].mechanism
    # a sector the LLM omitted is still kept (graph-supported), via template
    assert "defense_aerospace" in by_sector
    assert by_sector["defense_aerospace"].mechanism
    assert delta.token_spend == 123


def test_reasoner_llm_garbage_falls_back_to_template():
    agent = TransmissionReasoner(llm=FakeLLM(available=True, text="sorry, no JSON here"))
    delta = agent.run(_state())
    # unparseable output must not lose the graph-derived chains
    assert {c.sector for c in delta.transmission_chains} >= {"energy", "airlines"}
