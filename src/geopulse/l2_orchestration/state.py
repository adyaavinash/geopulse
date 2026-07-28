"""Shared typed state — contract #2 (orchestrator <-> agents).

Per docs/repo_structure_v2_whiteboard.md this is drafted by Person 2 and
co-signed by Person 3 (their agents plug into it). What is defined here is the
*minimum* the two upstream agents (Analogy, Transmission) need; the downstream
fields (sentiment, quant, checker_review, verdict) are declared but left to
Person 3 to flesh out. Marked provisional until that co-sign.

Whiteboard field list for the shared clipboard:
    event, plan, analogies, transmission_chains, sentiment,
    quant_signals, checker_review, verdict, evidence_log, token_spend.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

Direction = Literal["up", "down"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Agent I/O primitives
# --------------------------------------------------------------------------- #
class AgentCall(BaseModel):
    """One entry in the orchestrator's plan — logged for auditability, since a
    dynamic hub is harder to debug than a static graph."""

    agent: str                          # e.g. "transmission_reasoner"
    reason: str = ""                    # why the orchestrator dispatched it
    called_at: datetime = Field(default_factory=_utcnow)


class CitedEdge(BaseModel):
    """One hop in a causal walk. Every hop MUST cite a graph edge (or, later,
    a retrieved source) so the final verdict is traceable rather than asserted."""

    frm: str                            # source node, e.g. "chokepoint_disruption"
    relation: str                       # edge label, e.g. "raises" / "sector_up"
    to: str                             # target node, e.g. "crude" / "energy"
    citation: str                       # provenance, e.g.
    #                                     "transmission_channels.yaml:oil_supply_shock:raises"


# --------------------------------------------------------------------------- #
# Node 5 output — the causal chain (the project's moat)
# --------------------------------------------------------------------------- #
class TransmissionChain(BaseModel):
    """A candidate sector impact with its cited causal path.

    event -> commodity/factor -> sector -> company(etf). The Transmission
    Reasoner emits a list of these; the orchestrator's synthesis reconciles
    them against analogies + quant before they become verdict rows.
    """

    sector: str                         # sector_taxonomy key, e.g. "energy"
    etf: str                            # investable proxy, e.g. "XLE"
    direction: Direction                # "up" | "down"
    channel: str                        # transmission channel walked, e.g. "oil_supply_shock"
    hops: list[CitedEdge] = Field(default_factory=list)  # the traced path (>=1)
    mechanism: str = ""                 # the composed causal narrative
    confidence: float = 0.5             # 0..1, calibrated downstream
    rationale: str = ""                 # LLM's per-sector justification

    @property
    def citations(self) -> list[str]:
        return [hop.citation for hop in self.hops]


# --------------------------------------------------------------------------- #
# Event the reasoner reads (orchestrator produces this from AnomalySignal)
# --------------------------------------------------------------------------- #
class EventContext(BaseModel):
    """The classified event handed to the spoke agents. The orchestrator builds
    it from the frozen AnomalySignal (theme/score) plus its own classification
    (category/commodities/actors). Kept separate from AnomalySignal so L1's
    frozen contract never has to carry L2 enrichment."""

    signal_id: str
    theme: str                          # taxonomy key, e.g. "chokepoint_hormuz"
    category: str                       # event_taxonomy category, e.g. "chokepoint_disruption"
    severity: int = 3                   # 1..5
    region: str | None = None
    commodities: list[str] = Field(default_factory=list)   # e.g. ["crude", "jet_fuel"]
    actors: list[str] = Field(default_factory=list)
    triggered_at: datetime = Field(default_factory=_utcnow)
    query: str | None = None            # set for synthetic/manual triggers


# --------------------------------------------------------------------------- #
# Analogy (Node 4) — declared here so state is typed; body lands with Node 4
# --------------------------------------------------------------------------- #
class Analogy(BaseModel):
    """A past event retrieved by the Analogy agent, with its measured returns.
    Minimal shape so Node 5 can read analogies once Node 4 lands; Person 2
    finalizes it when building Node 4."""

    event_id: str
    title: str = ""
    category: str = ""
    region: str = ""
    date: str = ""
    similarity: float = 0.0
    measured_returns: dict[str, float] = Field(default_factory=dict)  # etf -> % return
    summary: str = ""
    citation: str = ""


# --------------------------------------------------------------------------- #
# What an agent returns; the orchestrator merges deltas into the shared state
# --------------------------------------------------------------------------- #
class StateDelta(BaseModel):
    """The partial update one agent contributes. The orchestrator applies it to
    GraphState. Only the fields an agent owns are set; everything else is None
    and left untouched on merge."""

    agent: str
    analogies: list[Analogy] | None = None
    transmission_chains: list[TransmissionChain] | None = None
    sentiment: dict[str, Any] | None = None
    quant_signals: dict[str, Any] | None = None
    evidence: list[str] = Field(default_factory=list)   # appended to evidence_log
    token_spend: int = 0
    notes: str | None = None


class GraphState(BaseModel):
    """The shared clipboard every agent reads/writes (via StateDelta).

    Downstream fields (sentiment, quant_signals, checker_review, verdict) are
    declared for the contract but owned by Person 3."""

    event: EventContext
    plan: list[AgentCall] = Field(default_factory=list)
    analogies: list[Analogy] = Field(default_factory=list)
    transmission_chains: list[TransmissionChain] = Field(default_factory=list)
    sentiment: dict[str, Any] | None = None
    quant_signals: dict[str, Any] | None = None
    checker_review: dict[str, Any] | None = None      # CheckerReview — Person 3
    verdict: dict[str, Any] | None = None             # SectorVerdict  — Person 3
    evidence_log: list[str] = Field(default_factory=list)
    token_spend: int = 0

    def apply(self, delta: StateDelta) -> "GraphState":
        """Merge an agent's delta in place and return self (for chaining)."""
        if delta.analogies is not None:
            self.analogies = delta.analogies
        if delta.transmission_chains is not None:
            self.transmission_chains = delta.transmission_chains
        if delta.sentiment is not None:
            self.sentiment = delta.sentiment
        if delta.quant_signals is not None:
            self.quant_signals = delta.quant_signals
        if delta.evidence:
            self.evidence_log.extend(delta.evidence)
        self.token_spend += delta.token_spend
        return self

    def get(self, key: str, default: Any = None) -> Any:
        """Dict-like accessor so callers (e.g. the Functions queue trigger in
        l1_ingestion_detection/functions/function_app.py, which does
        ``final_state.get("verdict")``) can treat the returned state like a
        plain result mapping without every caller needing a pydantic import."""
        return getattr(self, key, default)
