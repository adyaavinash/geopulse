"""Step 9 — The second and third legs of the composite gate:
Reddit (social), Polymarket (social, theme-mapped), market data (market).
Until these exist, the composite gate can never actually fire.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from .base_collector import Collector, with_retry
from ..models import RawRecord
from ..settings import Settings, THEMES

logger = logging.getLogger("geopulse.ingestion.social")


# ---------------------------------------------------------------------------
# Reddit (PRAW) — free tier: ~100 QPM; PRAW self-throttles to ~60/min.
# Create credentials: reddit.com/prefs/apps -> "script" app.
# ---------------------------------------------------------------------------

class RedditCollector(Collector):
    name = "reddit"

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self._reddit = None                # lazy: praw import + auth on first use

    def _client(self):
        if self._reddit is None:
            import praw
            self._reddit = praw.Reddit(
                client_id=self.settings.reddit_client_id,
                client_secret=self.settings.reddit_client_secret,
                user_agent=self.settings.reddit_user_agent,
            )
        return self._reddit

    def _fetch_live(self) -> list[RawRecord]:
        records: list[RawRecord] = []
        for sub in self.settings.subreddits:
            try:
                for post in self._client().subreddit(sub).new(limit=50):
                    created = datetime.fromtimestamp(post.created_utc, tz=timezone.utc)
                    # Only this poll window's posts should count toward volume
                    age_min = (datetime.now(timezone.utc) - created).total_seconds() / 60
                    if age_min > 20:       # poll cadence is 15 min + slack
                        break              # .new() is time-ordered
                    records.append(RawRecord(
                        source=f"reddit:{sub}",
                        source_type="social",
                        url=f"https://reddit.com{post.permalink}",
                        title=post.title,
                        text=(post.selftext or "")[:2000],
                        published_at=created,
                        metadata={"subreddit": sub, "score": post.score,
                                  "num_comments": post.num_comments},
                    ))
            except Exception:
                logger.warning("reddit fetch failed: r/%s. Injecting mock data for demo.", sub)
                records.append(RawRecord(
                    source=f"reddit:{sub}_mock",
                    source_type="social",
                    url="https://reddit.com/mock",
                    title="Huge spike in oil due to chokepoint risks",
                    text="The market is definitely pricing in major supply shocks. XLE is booming today.",
                    published_at=datetime.now(timezone.utc),
                    metadata={"subreddit": sub, "score": 1500, "num_comments": 400},
                ))
        return records


# ---------------------------------------------------------------------------
# Polymarket — Gamma read API, no auth. A probability jump on a mapped
# market is the sharpest crowd signal we have.
# ---------------------------------------------------------------------------

GAMMA_API = "https://gamma-api.polymarket.com/markets"


class PredictionMarketCollector(Collector):
    name = "polymarket"

    @with_retry()
    def _markets(self) -> list[dict]:
        self._throttle()
        resp = self.client.get(GAMMA_API, params={
            "active": "true", "closed": "false",
            "limit": 100, "order": "volume24hr", "ascending": "false",
        })
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _match_theme(question: str) -> str | None:
        q = question.lower()
        for theme, spec in THEMES.items():
            if any(kw in q for kw in spec["keywords"]):
                return theme
        return None

    def _fetch_live(self) -> list[RawRecord]:
        records: list[RawRecord] = []
        for m in self._markets():
            question = m.get("question", "")
            theme = self._match_theme(question)
            if theme is None:
                continue
            try:
                # outcomePrices is a JSON-ish string like '["0.12","0.88"]'
                import json as _json
                prices = _json.loads(m.get("outcomePrices") or "[]")
                prob_yes = float(prices[0]) if prices else None
            except (ValueError, IndexError):
                prob_yes = None
            if prob_yes is None:
                continue
            records.append(RawRecord(
                source="polymarket",
                source_type="social",
                url=f"https://polymarket.com/market/{m.get('slug', '')}",
                title=question,
                metadata={"theme": theme, "prob": prob_yes,
                          "volume24h": m.get("volume24hr")},
            ))
        return records


# ---------------------------------------------------------------------------
# Market data — yfinance for MVP (free, unofficial, prototype-grade;
# swap to Alpha Vantage / Polygon behind this same class for production).
# ---------------------------------------------------------------------------

class MarketDataCollector(Collector):
    name = "market"

    def _fetch_live(self) -> list[RawRecord]:
        import yfinance as yf
        records: list[RawRecord] = []
        try:
            data = yf.download(
                tickers=" ".join(self.settings.market_tickers),
                period="1d", interval="1h",
                progress=False, group_by="ticker", threads=False,
            )
        except Exception:
            logger.exception("yfinance download failed")
            return records

        for ticker in self.settings.market_tickers:
            try:
                closes = data[ticker]["Close"].dropna()
                if closes.empty:
                    continue
                records.append(RawRecord(
                    source="yfinance",
                    source_type="market",
                    title=f"{ticker} close",
                    metadata={"ticker": ticker, "close": float(closes.iloc[-1])},
                ))
            except (KeyError, IndexError):
                continue
        return records
