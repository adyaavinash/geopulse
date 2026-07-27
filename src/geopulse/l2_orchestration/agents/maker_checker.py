"""Maker-Checker (the contrarian) — see docs/repo_structure_v2_whiteboard.md.

Deliberately decoupled from scaffolding that doesn't exist yet in this repo
(agents/base_agent.py, llm.py, a filled-in state.py): the models below stand
in for the shared State contract, and the LLM call is injected so this is
unit-testable without a live model at all (see the test suite's fake llm_call).

The default LLM call runs locally via Ollama (phi4-mini) — no Azure dependency,
no API key, and it satisfies the whiteboard's "run the checker on a different
model deployment than synthesis" independence requirement for free, since
phi4-mini is architecturally unrelated to whatever GPT-family model eventually
handles synthesis/report-writing.

Wiring in later, once L2 scaffolding lands, means:
  - subclass BaseAgent and implement run(state) -> StateDelta, delegating to
    run_maker_checker() with fields pulled off the real State
  - swap _default_llm_call's OLLAMA_HOST/OLLAMA_MODEL constants for llm.py's
    model-tier selection once that exists (or keep calling Ollama directly —
    nothing requires this to become an Azure OpenAI call)
  - align SectorCall/DraftVerdict/EvidenceBundle field names with the real
    state.py once Person 2 drafts it (they're already named to match its
    docstring: analogies, transmission_chains, sentiment, quant_signals)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

import os

PROMPT_PATH = Path(__file__).resolve().parents[4] / "config" / "agent_prompts" / "maker_checker.md"
MAX_RETRIES = 2

OLLAMA_HOST = os.environ.get("GEOPULSE_OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("GEOPULSE_OLLAMA_MODEL", "phi4-mini")
OLLAMA_STRUCTURED_OUTPUT_RETRIES = 2   # separate from MAX_RETRIES (that's orchestrator revise/escalate)


class SectorCall(BaseModel):
    sector: str
    direction: Literal["winner", "loser"]
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    cited_transmission_edge: str | None = None
    cited_analogy_ids: list[str] = Field(default_factory=list)


class DraftVerdict(BaseModel):
    """The maker's work — what the checker reads and critiques."""

    event_id: str
    theme: str
    calls: list[SectorCall]
    overall_confidence: float = Field(ge=0.0, le=1.0)


class EvidenceBundle(BaseModel):
    """Everything else in state the checker is allowed to read."""

    transmission_chains: list[str] = Field(default_factory=list)
    analogies: list[dict] = Field(default_factory=list)          # [{id, event, return_pct, similarity}, ...]
    quant_signals: dict[str, float] = Field(default_factory=dict)  # ticker -> pct change
    sentiment: dict[str, float] = Field(default_factory=dict)      # sector -> score


class CheckerReview(BaseModel):
    verdict: Literal["approve", "revise", "escalate"]
    critique: str
    objections: list[str] = Field(default_factory=list)
    counter_evidence: list[str] = Field(default_factory=list)
    retry_count: int = 0


LlmCall = Callable[[str, DraftVerdict, EvidenceBundle], CheckerReview]


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _default_llm_call(prompt: str, draft: DraftVerdict, evidence: EvidenceBundle) -> CheckerReview:
    """Local Ollama (phi4-mini), no Azure/API-key dependency. Ollama's `format`
    param takes a JSON schema and constrains generation to match it, but small
    models are still less reliable at strict conformance than frontier models —
    don't trust a clean first-pass parse; validate and re-ask on failure."""
    user_msg = (
        f"Draft verdict:\n{draft.model_dump_json(indent=2)}\n\n"
        f"Evidence:\n{evidence.model_dump_json(indent=2)}"
    )
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": user_msg},
    ]
    schema = CheckerReview.model_json_schema()

    last_error: Exception | None = None
    for _ in range(OLLAMA_STRUCTURED_OUTPUT_RETRIES + 1):
        if last_error is not None:
            messages.append({
                "role": "user",
                "content": f"Your previous response failed validation: {last_error}. "
                           f"Return only valid JSON matching the schema exactly.",
            })
        resp = httpx.post(
            f"{OLLAMA_HOST}/api/chat",
            json={"model": OLLAMA_MODEL, "messages": messages, "format": schema, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        content = resp.json()["message"]["content"]
        try:
            return CheckerReview.model_validate_json(content)
        except (ValidationError, json.JSONDecodeError) as e:
            last_error = e
            messages.append({"role": "assistant", "content": content})

    raise RuntimeError(f"{OLLAMA_MODEL} failed to produce a valid CheckerReview after retries: {last_error}")


def run_maker_checker(
    draft: DraftVerdict,
    evidence: EvidenceBundle,
    retry_count: int = 0,
    llm_call: LlmCall = _default_llm_call,
) -> CheckerReview:
    """Critique a draft verdict. Bounded retries: if a 'revise' verdict comes
    back after MAX_RETRIES prior revisions, force 'escalate' instead of
    looping the orchestrator forever — same cost-control instinct as L1's
    composite gate."""
    prompt = load_prompt()
    review = llm_call(prompt, draft, evidence)
    review.retry_count = retry_count

    if review.verdict == "revise" and retry_count >= MAX_RETRIES:
        review.verdict = "escalate"
        review.objections.append(f"exhausted {MAX_RETRIES} revise retries without approval")

    return review
