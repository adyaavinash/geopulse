"""Agent 6 — Sentiment Agent ("Public").

Per Agent_Architecture_Spec.pdf:
  Reads      affected sectors
  Tools      Sentiment model (FinBERT or LLM) + Reddit/social fetcher, GDELT tone
  Data       Public social posts + news tone
  Database   Reads raw social/news store; writes sentiment scores to state
  Workflow   pull recent public text -> score tone per sector -> confirm/contradict
  Status     Wired into the L2 orchestrator (see SentimentAgent below); the
             module-level `run()` below still works standalone exactly as
             before, taking L1's AnomalySignal as input directly.

Run it directly:
    python -m geopulse.l2_orchestration.agents.sentiment_agent \\
        --theme chokepoint_hormuz --score 8.42

Or import `run(signal, sectors)` from other code — its return shape
(SentimentResult) is deliberately close to what state.py's `sentiment` field /
a StateDelta wants. `SentimentAgent` (bottom of this file) is the thin
BaseAgent adapter the orchestrator dispatches; it delegates straight to
`run()` rather than reimplementing anything, so this module's standalone
CLI/tests are untouched by orchestrator wiring.

--------------------------------------------------------------------------
Scoring backend — swappable, per-request design decision
--------------------------------------------------------------------------
Two scorers implement the same `SentimentScorer` protocol:

  Phi4OllamaScorer (intended primary approach) — calls a locally-running
                  Ollama server hosting a small instruction-tuned model
                  (Phi-4 / phi4-mini-family). Regex/keyword scoring has
                  structural failure modes an SLM avoids: negation whose
                  cue word falls outside a fixed lookback window, phrases
                  whose meaning isn't the sum of their words ("sanctions
                  relief" reads negative to a keyword scorer that only
                  knows "sanctions" is bad), and sarcasm/tone that requires
                  actually understanding the sentence. Grounding here has
                  two layers: (1) the input is split into SENTENCES first
                  (sentence_splitter.split_sentences — an abbreviation- and
                  decimal-aware splitter, not naive text.split(".")) and
                  each sentence is scored independently, so a passage that
                  genuinely mixes good and bad news doesn't get flattened
                  into one misleading number before the model even sees it;
                  (2) each per-sentence call is constrained to a fixed
                  candidate-sector list and must attach a supporting quote
                  per judgment, enforced by prompt + reject-on-schema-
                  mismatch rather than by trusting the model. See the
                  Phi4OllamaScorer class docstring for the known remaining
                  limitation (a single sentence with two comma-joined
                  clauses of opposite sentiment isn't further split).

                  This requires Ollama running locally (`ollama serve`) with
                  the model pulled (e.g. `ollama pull phi4-mini`) — that is
                  an external dependency this sandbox cannot install or run
                  (no GPU, no network path to the model registry here), so
                  it cannot be made the hard default from within this
                  sandbox. On a machine with Ollama available, set
                  GEOPULSE_SENTIMENT_BACKEND=phi4_ollama (or pass
                  backend="phi4_ollama" to build_scorer) to use it.

  LexiconScorer   (fallback, zero setup) — a small keyword-weight scorer.
                  No network, no extra dependencies, works in CI/dry_run,
                  and is what `run()` automatically falls back to per-record
                  if a Phi4OllamaScorer call fails outright. Still useful as
                  an always-available baseline and a fast local dev loop,
                  but it is not the recommended path when an LLM backend is
                  available — treat its output as a coarse signal, not a
                  confident read. Its accuracy characteristics (including
                  where it's known to be weak — sarcasm, intra-sentence
                  mixed sentiment) are measured in test_sentiment_agent.py
                  against tests/fixtures/sentiment_labeled_set.json.

Choose the backend via the `backend` param / `GEOPULSE_SENTIMENT_BACKEND` env
var: "lexicon" (current default, for zero-setup standalone runs) or
"phi4_ollama" (recommended once Ollama is available in your environment).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from ...l1_ingestion_detection.models import AnomalySignal, RawRecord
from ...l1_ingestion_detection.settings import THEMES, Settings, get_settings
from ...l1_ingestion_detection.collectors.social_market_collectors import RedditCollector
from ...l1_ingestion_detection.store import SqliteStore, get_store
from ..state import GraphState, StateDelta
from .base_agent import BaseAgent
from .sentence_splitter import split_sentences

logger = logging.getLogger("geopulse.l2.sentiment_agent")

# ---------------------------------------------------------------------------
# Theme -> affected sectors placeholder mapping.
#
# The real version of this belongs to Agent 5 (Transmission Reasoner), which
# derives affected sectors by walking transmission_channels.yaml. The
# orchestrator's SentimentAgent wrapper below prefers those graph-derived
# sectors (state.transmission_chains) when available and only falls back to
# this theme-keyed placeholder for standalone runs where Node 5 hasn't run —
# keep it in sync with config/sector_taxonomy.yaml keys.
# ---------------------------------------------------------------------------
THEME_SECTOR_MAP: dict[str, list[str]] = {
    "chokepoint_hormuz": ["energy", "defense_aerospace", "airlines", "gold", "materials"],
    "chokepoint_suez": ["energy", "materials", "industrials", "consumer_disc"],
    "armed_conflict_escalation": ["defense_aerospace", "energy", "gold"],
    "market_crash": ["consumer_staples", "utilities", "health_care", "gold"],
    "sanctions_exportcontrols": ["semiconductors", "energy", "financials"],
}

DEFAULT_SECTORS = ["energy", "defense_aerospace", "airlines", "financials", "semiconductors"]


def sectors_for_theme(theme: str) -> list[str]:
    return THEME_SECTOR_MAP.get(theme, DEFAULT_SECTORS)


# ---------------------------------------------------------------------------
# Output schema — close to what state.py's `sentiment` field will expect.
# ---------------------------------------------------------------------------

Stance = Literal["confirm", "contradict", "neutral"]


class SectorSentiment(BaseModel):
    sector: str
    mood_score: float = Field(description="-1.0 (very negative) to +1.0 (very positive)")
    stance: Stance = Field(description="does public mood confirm or contradict a negative-shock thesis")
    sample_size: int
    evidence_record_ids: list[str] = Field(default_factory=list)


class SentimentResult(BaseModel):
    """Standalone-run output. Shape mirrors the future StateDelta.sentiment."""

    signal_id: str
    theme: str
    scored_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    backend: str
    sectors: list[SectorSentiment]
    overall_mood_score: float
    overall_stance: Stance
    notes: str = ""


# ---------------------------------------------------------------------------
# Scorer protocol + implementations
# ---------------------------------------------------------------------------

class SentimentScorer(Protocol):
    name: str

    def score_text(self, text: str) -> float:
        """Return a mood score in [-1.0, +1.0]. Higher = more positive."""
        ...


_POSITIVE_WORDS = {
    "restore", "restored", "resolved", "ceasefire", "de-escalate", "de-escalation",
    "reopen", "reopened", "agreement", "deal", "stabilize", "stabilized", "calm",
    "calmed", "easing", "eased", "recover", "recovery", "safe", "relief",
}
_NEGATIVE_WORDS = {
    "attack", "attacked", "strike", "strikes", "war", "invasion", "blockade",
    "seized", "explosion", "missile", "crash", "plunge", "selloff", "panic",
    "escalate", "escalation", "sanctions", "embargo", "collapse", "crisis",
    "closure", "closed", "threat", "casualties", "killed",
}
_NEGATION_WORDS = {"not", "no", "never", "n't", "without", "isn't", "won't", "didn't"}

# Matches word cores with INTERNAL apostrophes and hyphens preserved (so
# contractions like "isn't"/"won't" tokenize as one word for the
# negation-word lookup, and hyphenated terms like "de-escalate" tokenize as
# one word matching the dictionary entries below), but does not glue on
# LEADING or TRAILING apostrophes/quote marks (e.g. scare-quoted
# 'stabilized' should tokenize as "stabilized", not "'stabilized'" — the old
# r"[a-z']+" pattern grabbed the surrounding quote marks too, which then
# failed to match the plain dictionary entry).
_WORD_RE = re.compile(r"[a-z]+(?:['-][a-z]+)*")


class LexiconScorer:
    """Default scorer: fast, dependency-free keyword-weight scoring with a
    simple negation flip (a sentiment word within 4 tokens of a negation word
    has its polarity flipped). Coarse, but predictable and always available.
    The 4-token lookback (rather than 2) is needed to catch negation whose
    cue word sits before a short intervening phrase, e.g. "did *not* lead
    to a ceasefire" — "ceasefire" is 4 tokens after "not"."""

    name = "lexicon"

    def score_text(self, text: str) -> float:
        if not text:
            return 0.0
        tokens = _WORD_RE.findall(text.lower())
        if not tokens:
            return 0.0

        score = 0
        hits = 0
        for i, tok in enumerate(tokens):
            polarity = 0
            if tok in _POSITIVE_WORDS:
                polarity = 1
            elif tok in _NEGATIVE_WORDS:
                polarity = -1
            else:
                continue

            window = tokens[max(0, i - 4): i]
            if any(w in _NEGATION_WORDS for w in window):
                polarity *= -1

            score += polarity
            hits += 1

        if hits == 0:
            return 0.0
        return max(-1.0, min(1.0, score / hits))


PHI4_SENTIMENT_PROMPT = """You are a financial-news sentiment classifier. You will be given ONE sentence (from a news article or social post) and a fixed list of candidate market sectors.

Candidate sectors: {sectors}

Sentence:
\"\"\"{text}\"\"\"

Task: judge the sentiment this sentence expresses toward each sector it is actually relevant to (ignore sectors it says nothing about). Ground every judgment in a short quoted span from the sentence — do not infer sentiment the sentence doesn't support. Because you are only given one sentence at a time, do not guess at context from outside it.

Respond with ONLY strict JSON, no prose, no markdown fences, in this exact shape:
{{"judgments": [{{"sector": "<one of the candidate sectors>", "polarity": <float from -1.0 to 1.0>, "quote": "<short exact span from the sentence supporting this>"}}]}}

If the sentence is not relevant to any candidate sector, respond with {{"judgments": []}}.
"""


class Phi4OllamaScorer:
    """Opt-in scorer: calls a locally-running Ollama server hosting a small
    instruction-tuned model (recommended: phi4-mini or phi4-mini-instruct).

    Grounding strategy — two layers:
      1. Sentence-level scoring: `score_sectors()` first splits the input
         into sentences (sentence_splitter.split_sentences — an
         abbreviation/decimal-aware splitter, not naive text.split(".")),
         scores EACH sentence independently, then aggregates per sector
         across sentences. This matters because whole-paragraph scoring
         forces one polarity out of text that may genuinely contain two
         (e.g. "Markets calmed after the strike, though officials warn the
         ceasefire is fragile and could collapse" — two sentences of
         different sentiment glued together); scoring sentence-by-sentence
         lets each get its own honest judgment instead of averaging them
         into a mushy, harder-to-defend blend BEFORE the model even sees
         them separately.
      2. Per-sentence prompt constraints: the model is only allowed to judge
         sectors from a fixed candidate list, and must attach a supporting
         quote per judgment — both constraints are enforced by prompt +
         reject-on-schema-mismatch, not by trusting the model.

    Known remaining limitation: a SINGLE sentence that itself contains two
    clauses of opposite sentiment joined by "but"/"while"/a comma (e.g. "The
    attack caused an initial panic, but a swift agreement helped prices
    recover") is NOT further split — see
    test_sentence_splitter.test_comma_joined_clauses_stay_one_sentence. That
    is still the model's judgment call to make within a single sentence, not
    something splitting can resolve; the grounding constraint (quote a
    specific span) at least keeps that judgment anchored to actual text
    rather than a free-floating guess.

    Requires `ollama serve` running locally with the model pulled; this
    sandbox cannot exercise the live HTTP call (no GPU, and the network
    egress allowlist here doesn't include an Ollama endpoint or a model
    registry), so treat the network-calling parts of this class as
    unit-tested-by-contract only until run on a machine that has Ollama
    available. The sentence-splitting and aggregation logic around it,
    however, IS fully tested offline (see test_sentiment_agent.py and
    test_sentence_splitter.py) since it doesn't require the network call.
    """

    name = "phi4_ollama"

    def __init__(self, model: str = "phi4-mini", host: str = "http://localhost:11434"):
        self.model = model
        self.host = host.rstrip("/")
        self._client = None

    def _http(self):
        if self._client is None:
            import httpx
            self._client = httpx.Client(timeout=30)
        return self._client

    def _score_sectors_single_call(self, text: str, sectors: list[str]) -> list[dict]:
        """One grounded LLM call over a single span of text (normally one
        sentence). Returns the raw judgment list [{sector, polarity, quote}],
        already validated against the candidate sector list and requiring a
        non-empty quote. Returns [] on any transport/parse failure — never
        raises, since a flaky local LLM call should not crash agent 6."""
        prompt = PHI4_SENTIMENT_PROMPT.format(sectors=", ".join(sectors), text=text[:1500])
        try:
            resp = self._http().post(
                f"{self.host}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False,
                      "format": "json", "options": {"temperature": 0.0}},
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "")
            parsed = json.loads(raw)
            out = []
            for j in parsed.get("judgments", []):
                sector = j.get("sector")
                quote = j.get("quote")
                polarity = j.get("polarity")
                if sector in sectors and quote and isinstance(polarity, (int, float)):
                    out.append({
                        "sector": sector, "quote": quote,
                        "polarity": max(-1.0, min(1.0, float(polarity))),
                    })
            return out
        except Exception:
            logger.exception("phi4_ollama scoring failed; caller should fall back")
            return []

    def score_sectors(self, text: str, sectors: list[str]) -> dict[str, float]:
        """Grounded, sentence-level call: splits `text` into sentences,
        scores each sentence independently against the candidate sector
        list, and averages per-sector polarity across the sentences that
        judged it relevant. Returns {sector: polarity} for sectors any
        sentence judged relevant; sectors no sentence mentioned are simply
        absent (caller decides how to treat that — see sentiment_agent.run,
        which currently treats "no sentence judged this sector" as no
        signal, not as neutral-with-confidence).

        Returns {} only if EVERY sentence's call failed outright (transport/
        parse error) — the caller (sentiment_agent.run) falls back to
        LexiconScorer for the whole record in that case. A sentence that
        the model judged genuinely irrelevant to every sector is not a
        failure — it just contributes nothing, which is correct."""
        sentences = split_sentences(text)
        if not sentences:
            return {}

        per_sector: dict[str, list[float]] = defaultdict(list)
        any_call_succeeded = False
        for sentence in sentences:
            judgments = self._score_sectors_single_call(sentence, sectors)
            if judgments:
                any_call_succeeded = True
            for j in judgments:
                per_sector[j["sector"]].append(j["polarity"])

        if not any_call_succeeded:
            return {}

        return {
            sector: round(sum(polarities) / len(polarities), 3)
            for sector, polarities in per_sector.items()
        }

    def score_text(self, text: str) -> float:
        """Protocol-compliance shim: scores against no sector context, i.e.
        an unconstrained single-float judgment. Prefer score_sectors() when
        you have a sector list — it's the grounded path this class exists
        for. This method exists only so Phi4OllamaScorer satisfies the same
        SentimentScorer protocol as LexiconScorer for drop-in use."""
        scored = self.score_sectors(text, sectors=["general market"])
        return scored.get("general market", 0.0)



def build_scorer(backend: str | None = None) -> SentimentScorer:
    backend = backend or os.environ.get("GEOPULSE_SENTIMENT_BACKEND", "lexicon")
    if backend == "phi4_ollama":
        model = os.environ.get("GEOPULSE_SENTIMENT_PHI4_MODEL", "phi4-mini")
        host = os.environ.get("GEOPULSE_SENTIMENT_OLLAMA_HOST", "http://localhost:11434")
        return Phi4OllamaScorer(model=model, host=host)
    return LexiconScorer()


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------

def _gather_text_records(
    store: SqliteStore, theme: str, since_minutes: int = 180
) -> list[tuple[str, str]]:
    """(record_id, text) pairs from recently-stored records. Filters to this
    theme's keywords in title/text since store.py has no theme column yet."""
    keywords = [kw.lower() for kw in THEMES.get(theme, {}).get("keywords", [])]
    all_recent = store.recent_record_texts(since_minutes=since_minutes)
    if not keywords:
        return all_recent
    return [(rid, text) for rid, text in all_recent if any(kw in text.lower() for kw in keywords)]


def _stance_from_score(score: float) -> Stance:
    if score <= -0.15:
        return "confirm"       # negative public mood confirms a negative-shock thesis
    if score >= 0.15:
        return "contradict"    # positive mood pushes back on the thesis
    return "neutral"


def run(
    signal: AnomalySignal,
    sectors: list[str] | None = None,
    settings: Settings | None = None,
    store: SqliteStore | None = None,
    scorer: SentimentScorer | None = None,
) -> SentimentResult:
    """Standalone run: pull recent public text for this theme, score mood,
    aggregate per sector (every sector gets the same theme-level mood today,
    since per-sector text attribution needs agent 5's causal graph — refine
    once that exists), return a SentimentResult.

    This is also what SentimentAgent.run(state) below delegates to once the
    orchestrator is driving — it passes state's own settings/store (when
    injected) and the sectors state.transmission_chains already derived.
    """
    settings = settings or get_settings()
    store = store or get_store(settings)
    scorer = scorer or build_scorer()
    sectors = sectors or sectors_for_theme(signal.theme)

    # Best-effort: pull a fresh page of Reddit posts for this poll so a
    # standalone run has something to score even if the store is cold.
    try:
        fresh = RedditCollector(settings).fetch()
        if fresh:
            store.save_records(fresh)
    except Exception:
        logger.exception("reddit fetch failed during standalone sentiment run")

    records = _gather_text_records(store, signal.theme)
    if not records:
        logger.warning("no recent text found for theme=%s; scoring as neutral", signal.theme)

    per_record_scores: list[tuple[str, float]] = []
    if isinstance(scorer, Phi4OllamaScorer):
        # Grounded per-sector path: batch score against the real sector list.
        sector_scores: dict[str, list[float]] = defaultdict(list)
        sector_evidence: dict[str, list[str]] = defaultdict(list)
        for rid, text in records:
            judged = scorer.score_sectors(text, sectors)
            if not judged:
                # transport/parse failure or nothing relevant -> lexicon fallback for this record
                fallback = LexiconScorer().score_text(text)
                per_record_scores.append((rid, fallback))
                continue
            for sector, polarity in judged.items():
                sector_scores[sector].append(polarity)
                sector_evidence[sector].append(rid)
            per_record_scores.append((rid, sum(judged.values()) / len(judged)))

        sector_results = []
        for sector in sectors:
            scores = sector_scores.get(sector, [])
            mood = sum(scores) / len(scores) if scores else 0.0
            sector_results.append(SectorSentiment(
                sector=sector, mood_score=round(mood, 3),
                stance=_stance_from_score(mood), sample_size=len(scores),
                evidence_record_ids=sector_evidence.get(sector, [])[:10],
            ))
    else:
        for rid, text in records:
            per_record_scores.append((rid, scorer.score_text(text)))
        theme_mood = (
            sum(s for _, s in per_record_scores) / len(per_record_scores)
            if per_record_scores else 0.0
        )
        evidence_ids = [rid for rid, _ in per_record_scores[:10]]
        sector_results = [
            SectorSentiment(
                sector=sector, mood_score=round(theme_mood, 3),
                stance=_stance_from_score(theme_mood),
                sample_size=len(per_record_scores),
                evidence_record_ids=evidence_ids,
            )
            for sector in sectors
        ]

    overall = (
        sum(s.mood_score for s in sector_results) / len(sector_results)
        if sector_results else 0.0
    )
    return SentimentResult(
        signal_id=signal.id,
        theme=signal.theme,
        backend=scorer.name,
        sectors=sector_results,
        overall_mood_score=round(overall, 3),
        overall_stance=_stance_from_score(overall),
        notes=(
            "No recent text found for this theme; scored neutral by default."
            if not records else ""
        ),
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    ap = argparse.ArgumentParser(description="Agent 6 — Sentiment Agent (standalone)")
    ap.add_argument("--theme", required=True, choices=list(THEMES))
    ap.add_argument("--score", type=float, default=5.0, help="synthetic AnomalySignal.score")
    ap.add_argument("--sectors", nargs="*", default=None, help="override affected sectors")
    ap.add_argument("--backend", choices=["lexicon", "phi4_ollama"], default=None)
    args = ap.parse_args()

    signal = AnomalySignal(
        theme=args.theme, score=args.score, source_types=["news"],
        window_minutes=60, is_synthetic=True,
    )
    result = run(signal, sectors=args.sectors, scorer=build_scorer(args.backend))
    print(result.model_dump_json(indent=2))


# ---------------------------------------------------------------------------
# Orchestrator wiring — thin BaseAgent adapter over run() above.
#
# Deliberately just an adapter, not a rewrite: agent 6's standalone run()/
# main()/scorers/tests above are untouched, so its independent CLI usage and
# accuracy tests keep working exactly as before. This class is the only new
# surface the orchestrator depends on.
# ---------------------------------------------------------------------------

def _signal_from_event(event) -> AnomalySignal:
    return AnomalySignal(
        id=event.signal_id,
        theme=event.theme,
        score=float(event.severity),
        source_types=["news"],
        window_minutes=180,
        is_synthetic=event.query is not None,
        query=event.query,
    )


def _sectors_from_state(state: GraphState) -> list[str] | None:
    """Prefer Node 5's graph-derived sectors over the theme placeholder
    above once the Transmission Reasoner has run — see THEME_SECTOR_MAP's
    docstring note on why this is the intended upgrade path."""
    sectors = sorted({chain.sector for chain in state.transmission_chains})
    return sectors or None


class SentimentAgent(BaseAgent):
    name = "sentiment"
    tier = "cheap"

    def __init__(
        self,
        llm=None,
        settings: Settings | None = None,
        store: SqliteStore | None = None,
        scorer: SentimentScorer | None = None,
    ) -> None:
        super().__init__(llm=llm)
        self.settings = settings
        self.store = store
        self.scorer = scorer

    def run(self, state: GraphState) -> StateDelta:
        signal = _signal_from_event(state.event)
        sectors = _sectors_from_state(state)
        result = run(
            signal,
            sectors=sectors,
            settings=self.settings,
            store=self.store,
            scorer=self.scorer,
        )
        evidence = [
            f"sentiment:{sector.sector}:{rid}"
            for sector in result.sectors
            for rid in sector.evidence_record_ids
        ]
        return StateDelta(
            agent=self.name,
            sentiment=result.model_dump(mode="json"),
            evidence=evidence,
            notes=result.notes,
        )


if __name__ == "__main__":
    main()
