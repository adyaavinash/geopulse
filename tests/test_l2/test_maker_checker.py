"""Unit tests for the standalone Maker-Checker plumbing: prompt loading,
model round-trips, and the bounded-retry -> escalate transition. The LLM
call is injected/faked in most tests — this tests our control flow, not an
LLM's judgment (that's an eval-harness concern, not a unit test). One test
at the bottom exercises the real Ollama path and skips if it's unreachable."""
import json
from pathlib import Path

import httpx
import pytest

from geopulse.l2_orchestration.agents.maker_checker import (
    MAX_RETRIES,
    OLLAMA_HOST,
    CheckerReview,
    DraftVerdict,
    EvidenceBundle,
    _default_llm_call,
    load_prompt,
    run_maker_checker,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "draft_verdict_overconfident.json"


def _ollama_reachable() -> bool:
    try:
        httpx.get(f"{OLLAMA_HOST}/api/tags", timeout=2)
        return True
    except httpx.HTTPError:
        return False


def _load_draft() -> DraftVerdict:
    return DraftVerdict.model_validate(json.loads(FIXTURE.read_text()))


def test_prompt_loads_and_has_output_contract():
    prompt = load_prompt()
    assert "approve" in prompt and "revise" in prompt and "escalate" in prompt
    assert "critique" in prompt


def test_draft_and_evidence_round_trip():
    draft = _load_draft()
    assert draft.calls[0].cited_transmission_edge is None
    evidence = EvidenceBundle(quant_signals={"^VIX": 12.0})
    assert evidence.model_dump()["quant_signals"]["^VIX"] == 12.0


def test_approve_passes_through():
    draft = _load_draft()
    evidence = EvidenceBundle()

    def fake_llm(prompt, draft, evidence):
        return CheckerReview(verdict="approve", critique="Evidence checks out.")

    review = run_maker_checker(draft, evidence, retry_count=0, llm_call=fake_llm)
    assert review.verdict == "approve"
    assert review.retry_count == 0


def test_revise_under_retry_cap_stays_revise():
    draft = _load_draft()
    evidence = EvidenceBundle()

    def fake_llm(prompt, draft, evidence):
        return CheckerReview(
            verdict="revise",
            critique="No cited transmission edge for the energy call.",
            objections=["energy call has no cited_transmission_edge despite 0.9 confidence"],
        )

    review = run_maker_checker(draft, evidence, retry_count=MAX_RETRIES - 1, llm_call=fake_llm)
    assert review.verdict == "revise"


def test_revise_past_retry_cap_forces_escalate():
    draft = _load_draft()
    evidence = EvidenceBundle()

    def fake_llm(prompt, draft, evidence):
        return CheckerReview(verdict="revise", critique="Still uncited.", objections=["still uncited"])

    review = run_maker_checker(draft, evidence, retry_count=MAX_RETRIES, llm_call=fake_llm)
    assert review.verdict == "escalate"
    assert any("exhausted" in obj for obj in review.objections)


@pytest.mark.skipif(not _ollama_reachable(), reason="Ollama not running locally")
def test_real_ollama_flags_the_overconfident_draft():
    """Live integration test against phi4-mini. The fixture draft is
    deliberately flawed (0.9 confidence, no citations) — a competent checker
    should not approve it outright."""
    draft = _load_draft()
    evidence = EvidenceBundle(quant_signals={"^VIX": 2.1})

    review = run_maker_checker(draft, evidence, retry_count=0, llm_call=_default_llm_call)

    assert review.verdict in ("revise", "escalate")
    assert review.critique.strip()
    assert review.objections
