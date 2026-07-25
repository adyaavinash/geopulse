"""Node 5 — Transmission Reasoner (the project's moat).

Walks the causal graph (``event -> commodity/factor -> sector -> company``) for
the classified event, then has the LLM compose the causal narrative and
calibrate confidence *over that skeleton* — constrained to graph-supported
sectors, every hop cited. If no LLM is configured, it degrades to a template
narrative built from the channel mechanism, so the node always produces cited,
traceable chains.

Reads:  state.event (+ state.analogies when Node 4 has run).
Writes: state.transmission_chains (list[TransmissionChain]) via StateDelta.
"""

from __future__ import annotations

import json
import logging

from geopulse.l2_orchestration.agents.base_agent import BaseAgent
from geopulse.l2_orchestration.state import (
    Analogy,
    EventContext,
    GraphState,
    StateDelta,
    TransmissionChain,
)
from geopulse.l2_orchestration.tools.graph_tool import GraphTool, get_graph_tool

logger = logging.getLogger(__name__)

# Deterministic prior when the LLM is offline: strong, direct channels get a
# firmer base than second-order ones. Nudged by event severity (1..5).
_BASE_CONFIDENCE = 0.55


class TransmissionReasoner(BaseAgent):
    name = "transmission_reasoner"
    tier = "reasoning"

    def __init__(self, llm=None, graph: GraphTool | None = None) -> None:
        super().__init__(llm=llm)
        self.graph = graph or get_graph_tool()

    def run(self, state: GraphState) -> StateDelta:
        event = state.event
        channels = self.graph.channels_for_event(event.category)
        if not channels:
            logger.warning("No transmission channel for category=%s", event.category)
            return StateDelta(
                agent=self.name,
                transmission_chains=[],
                notes=f"no channel mapped for category={event.category}",
            )

        # 1. Deterministic skeleton: fully-cited candidate per affected sector.
        skeletons: list[TransmissionChain] = []
        for channel in channels:
            skeletons.extend(self.graph.walk(event.category, channel))

        # 2. Compose the narrative + calibrate confidence.
        token_spend = 0
        if self.llm.available:
            chains, token_spend = self._reason_with_llm(event, state.analogies, skeletons)
        else:
            logger.info("LLM offline — using template transmission narrative")
            chains = [self._template(event, c) for c in skeletons]

        evidence = _unique(cit for chain in chains for cit in chain.citations)
        return StateDelta(
            agent=self.name,
            transmission_chains=chains,
            evidence=evidence,
            token_spend=token_spend,
        )

    # ------------------------------------------------------------------ #
    # LLM path
    # ------------------------------------------------------------------ #
    def _reason_with_llm(
        self,
        event: EventContext,
        analogies: list[Analogy],
        skeletons: list[TransmissionChain],
    ) -> tuple[list[TransmissionChain], int]:
        prompt = self._build_prompt(event, analogies, skeletons)
        resp = self.llm.complete(prompt, tier=self.tier, system=self.load_prompt())
        scored = _parse_scores(resp.text)
        if scored is None:
            logger.warning("Transmission LLM output unparseable — falling back to template")
            return [self._template(event, c) for c in skeletons], resp.tokens

        chains: list[TransmissionChain] = []
        for skel in skeletons:
            entry = scored.get(skel.sector)
            if entry is None:
                # LLM omitted this graph-supported sector: keep it, template narrative.
                chains.append(self._template(event, skel))
                continue
            if entry.get("keep") is False:
                continue  # LLM dropped it with a reason
            skel.mechanism = str(entry.get("mechanism") or "").strip() or self._mechanism_text(skel)
            skel.rationale = str(entry.get("rationale") or "").strip()
            skel.confidence = _clamp(entry.get("confidence", _BASE_CONFIDENCE))
            chains.append(skel)
        return chains, resp.tokens

    def _build_prompt(
        self,
        event: EventContext,
        analogies: list[Analogy],
        skeletons: list[TransmissionChain],
    ) -> str:
        lines = [
            "EVENT:",
            f"  theme={event.theme} category={event.category} severity={event.severity}",
            f"  commodities={event.commodities or '[]'} region={event.region or 'n/a'}",
            "",
            "ANALOGIES:",
        ]
        if analogies:
            for a in analogies:
                lines.append(f"  - {a.title or a.event_id} (sim={a.similarity:.2f}) "
                             f"returns={a.measured_returns}")
        else:
            lines.append("  (none retrieved)")
        lines += ["", "CANDIDATES:"]
        for skel in skeletons:
            path = " -> ".join(f"{h.frm} -[{h.relation}]-> {h.to}" for h in skel.hops)
            lines.append(
                f"  - sector={skel.sector} direction={skel.direction} "
                f"channel={skel.channel}\n      path: {path}"
            )
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    # offline template path
    # ------------------------------------------------------------------ #
    def _template(self, event: EventContext, skel: TransmissionChain) -> TransmissionChain:
        skel.mechanism = self._mechanism_text(skel)
        skel.rationale = (
            f"Graph-derived: {event.category} routes through {skel.channel}; "
            f"{skel.sector} sits on the {skel.direction} side of that channel."
        )
        skel.confidence = _clamp(_BASE_CONFIDENCE + 0.05 * (event.severity - 3))
        return skel

    def _mechanism_text(self, skel: TransmissionChain) -> str:
        base = self.graph.mechanism(skel.channel)
        arrow = "benefits" if skel.direction == "up" else "is pressured"
        return f"{skel.sector} {arrow} via {skel.channel}. {base}".strip()


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _parse_scores(text: str) -> dict[str, dict] | None:
    """Parse the LLM's JSON array into {sector: entry}. Tolerates ```json fences
    and leading/trailing prose. Returns None if nothing parseable is found."""
    if not text:
        return None
    blob = text.strip()
    if "```" in blob:  # strip a fenced code block if present
        parts = blob.split("```")
        blob = max(parts, key=len)
        if blob.lstrip().lower().startswith("json"):
            blob = blob.lstrip()[4:]
    start, end = blob.find("["), blob.rfind("]")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        data = json.loads(blob[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    out: dict[str, dict] = {}
    for item in data:
        if isinstance(item, dict) and "sector" in item:
            out[str(item["sector"])] = item
    return out


def _clamp(value, lo: float = 0.0, hi: float = 1.0) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return _BASE_CONFIDENCE
    return max(lo, min(hi, v))


def _unique(items) -> list[str]:
    seen: dict[str, None] = {}
    for it in items:
        seen.setdefault(it, None)
    return list(seen)
