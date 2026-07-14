"""Step 4 — GDELT DOC 2.0 collector.

Two calls per theme per poll:
  mode=artlist     -> the matching articles (RawRecords, evidence pointers)
  mode=timelinevol -> normalized article-volume time series (detector input)

Tone comes free on artlist results; we aggregate avg tone per poll into its
own series, because volume-spike + tone-collapse is a far stronger signal
than volume alone.

API notes: free, no key, rolling ~3-month full-text window, JSON format.
Be polite: one query per theme per poll, throttled.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

from .base_collector import Collector, with_retry
from ..models import RawRecord
from ..settings import Settings, THEMES

logger = logging.getLogger("geopulse.ingestion.gdelt")

DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"


class GdeltCollector(Collector):
    name = "gdelt"

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.min_seconds_between_calls = 2.0   # be polite to a free API
        self.blocklist = set(settings.domain_blocklist)

    # -- API calls -----------------------------------------------------------

    @with_retry()
    def _artlist(self, query: str) -> list[dict]:
        self._throttle()
        resp = self.client.get(DOC_API, params={
            "query": query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": self.settings.gdelt_max_records,
            "timespan": self.settings.gdelt_timespan,
            "sort": "datedesc",
        })
        resp.raise_for_status()
        return resp.json().get("articles", [])

    @with_retry()
    def _timeline_volume(self, query: str, timespan: str = "1d") -> list[tuple[datetime, float]]:
        """timelinevol returns article volume as % of all GDELT coverage —
        already normalized against global news volume, which removes the
        'everything spikes when the world is loud' failure mode."""
        self._throttle()
        resp = self.client.get(DOC_API, params={
            "query": query,
            "mode": "timelinevol",
            "format": "json",
            "timespan": timespan,
        })
        resp.raise_for_status()
        series = resp.json().get("timeline", [])
        if not series:
            return []
        points = []
        for p in series[0].get("data", []):
            ts = datetime.strptime(p["date"], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
            points.append((ts, float(p["value"])))
        return points

    # -- collection -------------------------------------------------------------

    def _fetch_live(self) -> list[RawRecord]:
        records: list[RawRecord] = []
        for theme, spec in THEMES.items():
            try:
                articles = self._artlist(spec["gdelt_query"])
            except Exception:
                logger.exception("gdelt artlist failed: %s", theme)
                continue

            tones: list[float] = []
            for a in articles:
                domain = urlparse(a.get("url", "")).netloc.lower()
                if domain in self.blocklist:
                    continue
                tone = _safe_float(a.get("tone"))
                if tone is not None:
                    tones.append(tone)
                records.append(RawRecord(
                    source="gdelt",
                    source_type="news",
                    url=a.get("url"),
                    title=a.get("title"),
                    published_at=_parse_seendate(a.get("seendate")),
                    metadata={
                        "theme": theme,
                        "domain": domain,
                        "tone": tone,
                        "language": a.get("language"),
                        "sourcecountry": a.get("sourcecountry"),
                    },
                ))

            # Per-poll aggregates -> metadata records the caller turns into series
            records.append(RawRecord(
                source="gdelt:aggregate",
                source_type="news",
                title=f"aggregate:{theme}",
                metadata={
                    "theme": theme,
                    "is_aggregate": True,
                    "article_count": len(articles),
                    "avg_tone": (sum(tones) / len(tones)) if tones else 0.0,
                },
            ))
        return records

    def fetch_volume_series(self, theme: str, timespan: str = "1d") -> list[tuple[datetime, float]]:
        """Called by the ingest hook to refresh the detector's primary series.
        Separate from fetch() so the replay harness can request arbitrary
        historical windows."""
        return self._timeline_volume(THEMES[theme]["gdelt_query"], timespan=timespan)


def _parse_seendate(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _safe_float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
