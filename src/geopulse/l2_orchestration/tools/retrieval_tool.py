"""Retrieval over the event-study corpus — the non-LLM half of the Analogy agent.

Loads ``config/knowledge/event_corpus.yaml``, embeds each event once (via
``embeddings.py``), and answers cosine-similarity queries. Offline this is an
in-memory NumPy matrix; when Postgres + pgvector are wired (Person 4), the same
``search`` surface points at a ``corpus_embeddings`` table instead — callers do
not change.

Deterministic and citable: every hit carries the corpus id it came from, so the
Analogy agent's output can cite its evidence.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
import yaml

from geopulse.l2_orchestration.embeddings import Embedder, get_embedder

_REPO_ROOT = Path(__file__).resolve().parents[4]
_CORPUS_FILE = "knowledge/event_corpus.yaml"


@dataclass
class CorpusEvent:
    id: str
    title: str
    date: str
    category: str
    region: str
    commodities: list[str]
    summary: str
    window_days: int
    measured_returns: dict[str, float] = field(default_factory=dict)

    def embed_text(self) -> str:
        """The text similarity keys on — category/region/commodities included so
        retrieval reflects event structure, not just prose overlap."""
        return (
            f"{self.title}. category: {self.category}. region: {self.region}. "
            f"commodities: {', '.join(self.commodities)}. {self.summary}"
        )

    def citation(self) -> str:
        return f"{_CORPUS_FILE}:{self.id}"


@dataclass
class Hit:
    score: float
    event: CorpusEvent


class RetrievalTool:
    def __init__(self, events: list[CorpusEvent], embedder: Embedder | None = None) -> None:
        self.events = events
        self.embedder = embedder or get_embedder()
        # Embed the whole corpus once, up front.
        self._matrix = (
            self.embedder.embed([e.embed_text() for e in events])
            if events
            else np.zeros((0, self.embedder.dim), dtype=np.float32)
        )

    @classmethod
    def load(cls, config_dir: str | os.PathLike | None = None,
             embedder: Embedder | None = None) -> "RetrievalTool":
        cfg = Path(config_dir) if config_dir else _config_dir()
        raw = _read_yaml(cfg / _CORPUS_FILE)
        events = [CorpusEvent(**_coerce(e)) for e in raw.get("events", [])]
        return cls(events, embedder=embedder)

    def search(self, query: str, k: int = 4, category: str | None = None) -> list[Hit]:
        """Top-k most similar corpus events. If ``category`` is given, only
        events of that category are considered (used by the agent to tighten a
        reformulated query)."""
        if not self.events:
            return []
        mask = np.array(
            [category is None or e.category == category for e in self.events]
        )
        if not mask.any():
            return []
        qvec = self.embedder.embed_one(query)
        scores = self._matrix @ qvec              # cosine (rows are normalized)
        scores = np.where(mask, scores, -np.inf)  # exclude filtered-out rows
        order = np.argsort(scores)[::-1][:k]
        return [
            Hit(score=float(scores[i]), event=self.events[i])
            for i in order
            if np.isfinite(scores[i])
        ]

    def categories(self) -> set[str]:
        return {e.category for e in self.events}


def _config_dir() -> Path:
    override = os.environ.get("GEOPULSE_CONFIG_DIR")
    return Path(override) if override else _REPO_ROOT / "config"


def _read_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _coerce(entry: dict) -> dict:
    """YAML gives dates as datetime.date; normalize to str for the dataclass."""
    e = dict(entry)
    if "date" in e and not isinstance(e["date"], str):
        e["date"] = str(e["date"])
    return e


@lru_cache(maxsize=1)
def get_retrieval_tool() -> RetrievalTool:
    return RetrievalTool.load()
