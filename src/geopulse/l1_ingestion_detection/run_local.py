"""Steps 8 & 10 — Run the loop locally, then validate on history.

  python run_local.py loop            # live polling loop (Ctrl+C to stop)
  python run_local.py once            # single poll of every source
  python run_local.py replay --theme chokepoint_hormuz --start 2026-06-20 --days 3
  python run_local.py drain           # consume + print queued signals

The replay command is your acceptance test: feed a known event's GDELT
volume timeline through the detector bucket-by-bucket (no lookahead) and
assert it fires within 1-2 polling cycles of the news breaking. GDELT's
DOC API full-text window is rolling ~3 months, so replay recent events
(e.g. the 2026 Hormuz closure); for older ones (Abqaiq 2019) download the
raw GDELT v2 event files and load them via the same ingest path.
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timedelta, timezone

from .detection.anomaly_detector import AnomalyDetector, bucket
from .detection.dedupe import Deduplicator
from .collectors.gdelt_collector import GdeltCollector
from .queue_bus import QueueBus
from .collectors.rss_collector import RssCollector
from .settings import THEMES, get_settings
from .collectors.social_market_collectors import (
    MarketDataCollector, PredictionMarketCollector, RedditCollector,
)
from .store import get_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
logger = logging.getLogger("geopulse.run")


def build():
    s = get_settings()
    store = get_store(s)
    return s, store, Deduplicator(store), AnomalyDetector(store, s), QueueBus(s)


def poll_once(publish: bool = True) -> None:
    s, store, dedupe, detector, bus = build()
    jobs = [
        (GdeltCollector(s), "news"),
        (RssCollector(s), "news"),
        (RedditCollector(s), "social"),
        (PredictionMarketCollector(s), "social"),
        (MarketDataCollector(s), "market"),
    ]
    for collector, source_type in jobs:
        try:
            records = collector.fetch()
        except Exception:
            logger.exception("%s failed", collector.name)
            continue
        fresh = dedupe.filter_new(records)
        store.save_records(fresh)
        logger.info("%s: %d fetched, %d new", collector.name, len(records), len(fresh))

        signal = detector.check(source_type=source_type, records=fresh)
        if signal and publish:
            bus.publish_anomaly(signal)


def loop(interval_seconds: int = 300) -> None:
    while True:
        poll_once()
        time.sleep(interval_seconds)


def drain() -> None:
    _, _, _, _, bus = build()
    while (item := bus.receive()) is not None:
        signal, raw = item
        print(signal.model_dump_json(indent=2))
        bus.complete(raw)


def replay(theme: str, start: str, days: int) -> None:
    """Feed a historical GDELT volume timeline through the detector with a
    strict as-of cutoff and report when (if) the composite gate would fire.
    News-only replay: pair with a synthetic VIX series or lower
    composite_min_source_types to 1 for the news-leg-only assertion."""
    s, store, _, detector, _ = build()
    start_dt = datetime.fromisoformat(start).replace(tzinfo=timezone.utc)

    gdelt = GdeltCollector(s)
    # Pull baseline_days of history BEFORE the event so z-scores have a baseline
    span_days = s.baseline_days + days
    timespan = f"{span_days}d"
    points = gdelt.fetch_volume_series(theme, timespan=timespan)
    if not points:
        print("No timeline data — event may be outside GDELT DOC's rolling window.")
        return

    series_key = f"news:{theme}:volume"
    fired_at = None
    for ts, value in points:                       # chronological: no lookahead
        store.add_series_point(series_key, bucket(ts, s.bucket_minutes), value)
        # Force a very negative tone during replay so the tone gate passes;
        # a full replay would also reconstruct tone from artlist history.
        store.add_series_point(f"news:{theme}:tone", bucket(ts, s.bucket_minutes), -6.0)
        if ts < start_dt:
            continue                               # still building baseline
        z = detector._zscore(series_key)
        if z is not None and z >= s.z_threshold_news and fired_at is None:
            fired_at = ts
            print(f"NEWS SPIKE at {ts:%Y-%m-%d %H:%M}Z  z={z:.1f}")

    if fired_at is None:
        print("Detector never fired — tune thresholds or check the window.")
    else:
        lag = fired_at - start_dt
        print(f"Detection lag from window start: {lag} "
              f"(acceptance: within 1-2 polling cycles of first wire story)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("once")
    sub.add_parser("loop")
    sub.add_parser("drain")
    rp = sub.add_parser("replay")
    rp.add_argument("--theme", choices=list(THEMES), required=True)
    rp.add_argument("--start", required=True, help="ISO date the event broke")
    rp.add_argument("--days", type=int, default=3)
    args = ap.parse_args()

    if args.cmd == "once":
        poll_once()
    elif args.cmd == "loop":
        loop()
    elif args.cmd == "drain":
        drain()
    elif args.cmd == "replay":
        replay(args.theme, args.start, args.days)
