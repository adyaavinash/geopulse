"""Step 3 — RSS collector: the fastest win. No keys, no rate-limit drama.

Besides emitting records, it writes a per-poll article count into the
'rss:volume' series — one leg of the anomaly detector's input.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from time import mktime

import feedparser

from .base_collector import Collector, with_retry
from ..models import RawRecord
from ..settings import Settings

logger = logging.getLogger("geopulse.ingestion.rss")

# Curate ~10 feeds. Wire services first: lowest latency of any free source.
FEEDS: dict[str, str] = {
    "reuters_world": "https://feeds.reuters.com/Reuters/worldNews",
    "reuters_business": "https://feeds.reuters.com/reuters/businessNews",
    "ap_top": "https://feeds.apnews.com/rss/apf-topnews",
    "aljazeera_all": "https://www.aljazeera.com/xml/rss/all.xml",
    "bbc_world": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "ft_home": "https://www.ft.com/rss/home",
    "eia_press": "https://www.eia.gov/rss/press_rss.xml",
    "guardian_world": "https://www.theguardian.com/world/rss",
}


class RssCollector(Collector):
    name = "rss"

    def __init__(self, settings: Settings, feeds: dict[str, str] | None = None):
        super().__init__(settings)
        self.feeds = feeds or FEEDS

    @with_retry()
    def _fetch_feed(self, feed_name: str, url: str) -> list[RawRecord]:
        self._throttle()
        resp = self.client.get(url)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
        records = []
        for entry in parsed.entries:
            published = None
            if getattr(entry, "published_parsed", None):
                published = datetime.fromtimestamp(
                    mktime(entry.published_parsed), tz=timezone.utc
                )
            records.append(RawRecord(
                source=f"rss:{feed_name}",
                source_type="news",
                url=entry.get("link"),
                title=entry.get("title"),
                text=entry.get("summary", "")[:2000],
                published_at=published,
            ))
        return records

    def _fetch_live(self) -> list[RawRecord]:
        out: list[RawRecord] = []
        for feed_name, url in self.feeds.items():
            try:
                out.extend(self._fetch_feed(feed_name, url))
            except Exception:
                # One dead feed must never kill the poll.
                logger.exception("feed failed: %s", feed_name)
        return out
