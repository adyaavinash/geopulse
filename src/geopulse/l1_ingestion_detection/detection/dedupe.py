"""Step 5 — Dedupe: three layers, cheapest first.

1. URL canonicalization  — strip tracking params, normalize scheme/host.
2. Exact-ID dedupe       — RawRecord.id is a content hash; store lookup.
3. Near-duplicate text   — shingled Jaccard against recent records, which
                           collapses circular reporting (40 outlets
                           rewriting one Reuters wire == one story).

Without layer 3 the detector fires on syndication, not news.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from ..models import RawRecord
from ..store import SqliteStore

logger = logging.getLogger("geopulse.detection.dedupe")

TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term",
                   "utm_content", "fbclid", "gclid", "ref", "cmpid", "smid"}

_WORD = re.compile(r"[a-z0-9]+")


def canonicalize_url(url: str | None) -> str | None:
    if not url:
        return None
    p = urlparse(url.strip())
    query = urlencode(
        [(k, v) for k, v in parse_qsl(p.query) if k.lower() not in TRACKING_PARAMS]
    )
    return urlunparse((
        p.scheme.lower() or "https",
        p.netloc.lower().removeprefix("www."),
        p.path.rstrip("/"),
        "", query, "",
    ))


def shingles(text: str, k: int = 3) -> set[str]:
    words = _WORD.findall(text.lower())
    return {" ".join(words[i:i + k]) for i in range(max(len(words) - k + 1, 1))}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class Deduplicator:
    def __init__(self, store: SqliteStore, near_dup_threshold: float = 0.6):
        self.store = store
        self.near_dup_threshold = near_dup_threshold

    def filter_new(self, records: list[RawRecord]) -> list[RawRecord]:
        # Layer 1: canonical URLs (also re-derives id off the cleaned URL)
        for r in records:
            if r.url:
                r.url = canonicalize_url(r.url)
                r.id = ""            # force re-hash off canonical basis
                r.model_post_init(None)

        # Layer 2: drop ids we've already stored + intra-batch dupes
        seen_ids = self.store.known_record_ids([r.id for r in records])
        batch_ids: set[str] = set()
        candidates: list[RawRecord] = []
        for r in records:
            if r.id in seen_ids or r.id in batch_ids:
                continue
            batch_ids.add(r.id)
            candidates.append(r)

        # Layer 3: near-duplicate text vs the last 2h (circular reporting).
        # O(new x recent) Jaccard — fine at MVP volume (hundreds x hundreds).
        # Upgrade path when it isn't: MinHash-LSH (datasketch) behind this
        # same method signature.
        recent = [
            (rid, shingles(text)) for rid, text in
            self.store.recent_record_texts(since_minutes=120) if text.strip()
        ]
        fresh: list[RawRecord] = []
        dropped = 0
        for r in candidates:
            if r.metadata.get("is_aggregate"):
                fresh.append(r)
                continue
            body = f"{r.title or ''} {(r.text or '')[:800]}"
            sh = shingles(body)
            duplicate_of = next(
                (rid for rid, rsh in recent if jaccard(sh, rsh) >= self.near_dup_threshold),
                None,
            )
            if duplicate_of:
                dropped += 1
                continue
            recent.append((r.id, sh))     # new stories dedupe against each other too
            fresh.append(r)

        if dropped:
            logger.info("dedupe: dropped %d near-duplicates of %d candidates",
                        dropped, len(candidates))
        return fresh
