"""Node 4 — Analogy agent (agentic RAG).

Not one-shot retrieval: an iterative loop — retrieve analogues -> assess whether
they cover this event's category AND region -> if not, reformulate the query and
retrieve again -> stop when sufficient or at a hard cap (the whiteboard's
"Agentic RAG — til when?" answered: 3 rounds). Returns past events *with their
measured sector returns*, which is what lets the Transmission Reasoner's
confidences become evidence-backed rather than priors.

Reads:  state.event.
Writes: state.analogies (list[Analogy]) via StateDelta.
"""

from __future__ import annotations

import json
import logging

from geopulse.l2_orchestration.agents.base_agent import BaseAgent
from geopulse.l2_orchestration.state import Analogy, EventContext, GraphState, StateDelta
from geopulse.l2_orchestration.tools.retrieval_tool import (
    Hit,
    RetrievalTool,
    get_retrieval_tool,
)

logger = logging.getLogger(__name__)

MAX_ROUNDS = 3            # the "til when?" cap
TOP_K = 4                 # analogues returned per round
MIN_CATEGORY_HITS = 2     # sufficiency: same-category precedents needed
FINAL_K = 4               # analogues handed downstream


class AnalogyAgent(BaseAgent):
    name = "analogy"
    tier = "cheap"        # sufficiency/reformulation is a light call

    def __init__(self, llm=None, retrieval: RetrievalTool | None = None) -> None:
        super().__init__(llm=llm)
        self.retrieval = retrieval or get_retrieval_tool()

    def run(self, state: GraphState) -> StateDelta:
        event = state.event
        query = _base_query(event)
        category_filter: str | None = None
        accumulated: dict[str, Hit] = {}   # event_id -> best hit
        trace: list[str] = []
        token_spend = 0

        for round_no in range(1, MAX_ROUNDS + 1):
            hits = self.retrieval.search(query, k=TOP_K, category=category_filter)
            for h in hits:
                prev = accumulated.get(h.event.id)
                if prev is None or h.score > prev.score:
                    accumulated[h.event.id] = h
            trace.append(f"round {round_no}: q={query!r} filter={category_filter} "
                         f"-> {[h.event.id for h in hits]}")

            sufficient, reason, new_query, spent = self._assess(
                event, list(accumulated.values())
            )
            token_spend += spent
            trace.append(f"  assess: sufficient={sufficient} ({reason})")
            if sufficient or round_no == MAX_ROUNDS:
                break

            # Reformulate: force category coverage, and broaden the query text.
            category_filter = event.category
            query = new_query or _broaden_query(event, query)

        analogies = _to_analogies(accumulated.values())
        evidence = [a.citation for a in analogies]
        logger.info("Analogy RAG: %d rounds, %d analogues", round_no, len(analogies))
        return StateDelta(
            agent=self.name,
            analogies=analogies,
            evidence=evidence,
            token_spend=token_spend,
            notes=" | ".join(trace),
        )

    # ------------------------------------------------------------------ #
    # sufficiency assessment (LLM when available, heuristic otherwise)
    # ------------------------------------------------------------------ #
    def _assess(
        self, event: EventContext, hits: list[Hit]
    ) -> tuple[bool, str, str | None, int]:
        if self.llm.available:
            return self._assess_llm(event, hits)
        suff, reason = _heuristic_sufficient(event, hits)
        return suff, reason, None, 0

    def _assess_llm(
        self, event: EventContext, hits: list[Hit]
    ) -> tuple[bool, str, str | None, int]:
        prompt = self._build_prompt(event, hits)
        resp = self.llm.complete(prompt, tier=self.tier, system=self.load_prompt())
        parsed = _parse_json_obj(resp.text)
        if parsed is None:
            # Unparseable — fall back to the deterministic check so the loop
            # still terminates sensibly.
            suff, reason = _heuristic_sufficient(event, hits)
            return suff, reason, None, resp.tokens
        return (
            bool(parsed.get("sufficient")),
            str(parsed.get("reason") or ""),
            (str(parsed["reformulated_query"]) if parsed.get("reformulated_query") else None),
            resp.tokens,
        )

    def _build_prompt(self, event: EventContext, hits: list[Hit]) -> str:
        lines = [
            "EVENT:",
            f"  theme={event.theme} category={event.category} "
            f"region={event.region or 'n/a'} commodities={event.commodities or '[]'}",
            "",
            "RETRIEVED:",
        ]
        for h in hits:
            lines.append(
                f"  - {h.event.id} (sim={h.score:.2f}) category={h.event.category} "
                f"region={h.event.region} commodities={h.event.commodities}"
            )
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _base_query(event: EventContext) -> str:
    parts = [event.theme.replace("_", " "), event.category.replace("_", " ")]
    parts += event.commodities
    if event.region:
        parts.append(event.region.replace("_", " "))
    if event.query:
        parts.append(event.query)
    return " ".join(p for p in parts if p)


def _broaden_query(event: EventContext, prev: str) -> str:
    # Add category + commodity emphasis when the LLM offered nothing.
    extra = " ".join(event.commodities + [event.category.replace("_", " ")])
    return f"{prev} {extra}".strip()


def _heuristic_sufficient(event: EventContext, hits: list[Hit]) -> tuple[bool, str]:
    same_cat = [h for h in hits if h.event.category == event.category]
    if len(same_cat) < MIN_CATEGORY_HITS:
        return False, f"only {len(same_cat)} same-category analogue(s)"
    if event.region and not any(h.event.region == event.region for h in same_cat):
        return False, "no region match among category analogues"
    return True, f"{len(same_cat)} same-category analogues, region covered"


def _to_analogies(hits) -> list[Analogy]:
    ranked = sorted(hits, key=lambda h: h.score, reverse=True)[:FINAL_K]
    out = []
    for h in ranked:
        e = h.event
        out.append(
            Analogy(
                event_id=e.id,
                title=e.title,
                category=e.category,
                region=e.region,
                date=e.date,
                similarity=round(h.score, 4),
                measured_returns=e.measured_returns,
                summary=e.summary.strip(),
                citation=e.citation(),
            )
        )
    return out


def _parse_json_obj(text: str) -> dict | None:
    if not text:
        return None
    blob = text.strip()
    if "```" in blob:
        parts = blob.split("```")
        blob = max(parts, key=len)
        if blob.lstrip().lower().startswith("json"):
            blob = blob.lstrip()[4:]
    start, end = blob.find("{"), blob.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        data = json.loads(blob[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None
