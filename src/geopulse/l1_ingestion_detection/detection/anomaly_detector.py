"""Step 6 — The anomaly detector. The core of Person 1's role.

Pipeline per check():
  1. ingest_records()  — turn the latest batch into time-series points
  2. per-series rolling z-score vs a trailing baseline (time-of-day aware)
  3. threshold breach + (for news) tone gate  -> Spike rows
  4. composite gate: >= N distinct source_types spiking on one theme
     within the composite window                -> AnomalySignal
  5. per-theme cooldown so a sustained story doesn't refire every poll

Every constant is a Settings field: this file is 90% tuning surface.
"""

from __future__ import annotations

import logging
import statistics
from datetime import datetime, timedelta, timezone

from ..models import AnomalySignal, RawRecord, Spike, SourceType
from ..settings import Settings, THEMES
from ..store import SqliteStore

logger = logging.getLogger("geopulse.detection.anomaly")


def bucket(ts: datetime, minutes: int) -> datetime:
    return ts.replace(minute=(ts.minute // minutes) * minutes, second=0, microsecond=0)


class AnomalyDetector:
    def __init__(self, store: SqliteStore, settings: Settings):
        self.store = store
        self.s = settings

    # ------------------------------------------------------------------ ingest

    def ingest_records(self, records: list[RawRecord], source_type: SourceType) -> None:
        """Convert a collector batch into series points. Called by the
        Functions hook right after store.save_records()."""
        now_bucket = bucket(datetime.now(timezone.utc), self.s.bucket_minutes)

        if source_type == "news":
            # GDELT aggregates carry per-theme count + tone; RSS counts globally.
            rss_count = 0
            for r in records:
                if r.metadata.get("is_aggregate"):
                    theme = r.metadata["theme"]
                    self.store.add_series_point(
                        f"news:{theme}:volume", now_bucket, r.metadata["article_count"])
                    self.store.add_series_point(
                        f"news:{theme}:tone", now_bucket, r.metadata["avg_tone"])
                elif r.source.startswith("rss:"):
                    rss_count += 1
            if rss_count:
                self.store.add_series_point("news:_rss:volume", now_bucket, rss_count)

        elif source_type == "social":
            counts: dict[str, int] = {}
            for r in records:
                if r.source.startswith("reddit:"):
                    counts[r.source] = counts.get(r.source, 0) + 1
                elif r.source == "polymarket":
                    # Probability level series per matched theme
                    theme = r.metadata.get("theme", "unmapped")
                    self.store.add_series_point(
                        f"social:polymarket:{theme}:prob", now_bucket,
                        r.metadata.get("prob", 0.0))
            for src, n in counts.items():
                self.store.add_series_point(f"social:{src}:volume", now_bucket, n)

        elif source_type == "market":
            for r in records:
                tkr = r.metadata.get("ticker")
                if tkr:
                    self.store.add_series_point(
                        f"market:{tkr}:close", now_bucket, r.metadata["close"])

    # ------------------------------------------------------------------ z-score

    def _zscore(self, series_key: str) -> float | None:
        """Latest point vs trailing baseline. Time-of-day aware: the baseline
        only uses points from the same hour-of-day (+/-1h) across prior days,
        so the US market open doesn't look like a crisis every afternoon.
        Falls back to the full window when the hour-matched sample is thin."""
        since = datetime.now(timezone.utc) - timedelta(days=self.s.baseline_days)
        points = self.store.get_series(series_key, since)
        if len(points) < self.s.min_baseline_samples // 4:
            return None                    # cold series: refuse to fire

        latest_ts, latest_v = points[-1]
        history = points[:-1]
        hour_matched = [
            v for ts, v in history
            if abs(((ts.hour - latest_ts.hour + 12) % 24) - 12) <= 1
        ]
        baseline = hour_matched if len(hour_matched) >= 12 else [v for _, v in history]
        if len(baseline) < 8:
            return None

        mean = statistics.fmean(baseline)
        std = statistics.pstdev(baseline)
        if std < 1e-9:
            return None                    # flat series: a jump from 0->1 isn't 'infinite sigma'
        return (latest_v - mean) / std

    def _latest(self, series_key: str, minutes_back: int = 90) -> float | None:
        pts = self.store.get_series(
            series_key, datetime.now(timezone.utc) - timedelta(minutes=minutes_back))
        return pts[-1][1] if pts else None

    # ------------------------------------------------------------------ spikes

    def _detect_spikes(self, source_type: SourceType) -> list[Spike]:
        spikes: list[Spike] = []

        if source_type == "news":
            for theme in THEMES:
                z = self._zscore(f"news:{theme}:volume")
                if z is None or z < self.s.z_threshold_news:
                    continue
                tone = self._latest(f"news:{theme}:tone")
                if tone is not None and tone > self.s.tone_threshold:
                    logger.info("volume spike on %s (z=%.1f) but tone %.1f above gate; skipping",
                                theme, z, tone)
                    continue
                spikes.append(Spike(theme=theme, series_key=f"news:{theme}:volume",
                                    source_type="news", z_score=z))

        elif source_type == "social":
            # Reddit volume is theme-agnostic -> a spike supports ANY theme
            # that has its own news spike in the composite window (documented
            # simplification; keyword-mapping posts to themes is the upgrade).
            for sub_series in self._reddit_series_keys():
                z = self._zscore(sub_series)
                if z is not None and z >= self.s.z_threshold_social:
                    for theme in THEMES:
                        spikes.append(Spike(theme=theme, series_key=sub_series,
                                            source_type="social", z_score=z))
            # Polymarket IS theme-mapped: a 10-point probability jump is a spike.
            for theme in THEMES:
                key = f"social:polymarket:{theme}:prob"
                pts = self.store.get_series(
                    key, datetime.now(timezone.utc) - timedelta(minutes=90))
                if len(pts) >= 2 and (pts[-1][1] - pts[0][1]) >= self.s.polymarket_prob_jump:
                    spikes.append(Spike(theme=theme, series_key=key,
                                        source_type="social",
                                        z_score=(pts[-1][1] - pts[0][1]) * 10))

        elif source_type == "market":
            # VIX z-score supports any theme with a co-occurring news spike.
            z = self._zscore("market:^VIX:close")
            if z is not None and z >= self.s.z_threshold_market:
                for theme in THEMES:
                    spikes.append(Spike(theme=theme, series_key="market:^VIX:close",
                                        source_type="market", z_score=z))

        for sp in spikes:
            self.store.save_spike(sp)
        return spikes

    def _reddit_series_keys(self) -> list[str]:
        return [f"social:reddit:{s}:volume" for s in self.s.subreddits]

    # ------------------------------------------------------------------ gate

    def check(self, source_type: SourceType,
              records: list[RawRecord] | None = None) -> AnomalySignal | None:
        """Run after every ingest. Returns at most ONE signal (highest-scoring
        theme) per call — the queue trigger downstream costs real money."""
        if records:
            self.ingest_records(records, source_type)

        self._detect_spikes(source_type)

        best: AnomalySignal | None = None
        for theme in THEMES:
            recent = self.store.recent_spikes(theme, self.s.composite_window_minutes)
            types_present = {sp.source_type for sp in recent}

            # Generic social/market spikes only count when news agrees —
            # otherwise a meme-stock frenzy alone could wake the pipeline.
            if "news" not in types_present:
                continue
            if len(types_present) < self.s.composite_min_source_types:
                continue
            if self.store.recent_signal_exists(theme, self.s.signal_cooldown_minutes):
                logger.info("cooldown active for %s; suppressing", theme)
                continue

            score = max(sp.z_score for sp in recent)
            signal = AnomalySignal(
                theme=theme,
                score=round(score, 2),
                source_types=sorted(types_present),
                window_minutes=self.s.composite_window_minutes,
                contributing_series={sp.series_key: round(sp.z_score, 2) for sp in recent},
            )
            if best is None or signal.score > best.score:
                best = signal

        if best:
            self.store.save_signal(best)   # cooldown bookkeeping
            logger.warning("COMPOSITE GATE FIRED: %s score=%.1f types=%s",
                           best.theme, best.score, best.source_types)
        return best
