"""Step 0 — The two frozen contracts.

RawRecord    : what every collector emits.
AnomalySignal: what lands on the 'anomaly-events' queue. Person 2's queue
               trigger deserializes exactly this shape — changing it means
               a coordinated redeploy, so freeze it early and version it.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

SourceType = Literal["news", "social", "market"]

SCHEMA_VERSION = 1


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RawRecord(BaseModel):
    """One normalized item from any collector (article, post, market row)."""

    id: str = ""                      # deterministic: filled from url/text hash
    source: str                      # e.g. "gdelt", "rss:reuters_world", "reddit:geopolitics"
    source_type: SourceType
    url: str | None = None
    title: str | None = None
    text: str | None = None
    published_at: datetime | None = None
    fetched_at: datetime = Field(default_factory=_utcnow)
    metadata: dict = Field(default_factory=dict)   # tone, subreddit, ticker, prob...

    def model_post_init(self, __context) -> None:
        if not self.id:
            basis = (self.url or "") + (self.title or "") + (self.text or "")[:500]
            self.id = hashlib.sha256(basis.encode()).hexdigest()[:24]


class AnomalySignal(BaseModel):
    """The queue message. One signal == one (expensive) agent-pipeline run."""

    schema_version: int = SCHEMA_VERSION
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    theme: str                        # taxonomy key, e.g. "chokepoint_hormuz"
    score: float                      # max z-score across contributing series
    source_types: list[SourceType]    # which of news/social/market spiked
    window_minutes: int               # lookback that the composite gate used
    triggered_at: datetime = Field(default_factory=_utcnow)
    sample_record_ids: list[str] = Field(default_factory=list)  # evidence pointers
    contributing_series: dict[str, float] = Field(default_factory=dict)  # series_key -> z
    is_synthetic: bool = False
    query: str | None = None          # set for synthetic/manual triggers

    @classmethod
    def synthetic(cls, query: str) -> "AnomalySignal":
        """Manual/dev trigger (HTTP endpoint, replay harness)."""
        return cls(
            theme="manual",
            score=0.0,
            source_types=["news"],
            window_minutes=0,
            is_synthetic=True,
            query=query,
        )


class Spike(BaseModel):
    """Internal record of one series exceeding its threshold. The composite
    gate counts distinct source_types of recent Spikes per theme."""

    theme: str
    series_key: str
    source_type: SourceType
    z_score: float
    observed_at: datetime = Field(default_factory=_utcnow)
