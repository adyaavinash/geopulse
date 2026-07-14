"""Formalized L1 smoke test: dedupe collapse, single-source suppression,
composite gate firing, cooldown, and the queue-message contract."""
import os
from datetime import datetime, timedelta, timezone

import pytest

os.environ["GEOPULSE_SQLITE_PATH"] = "/tmp/geopulse_test.db"
os.environ["GEOPULSE_DRY_RUN"] = "true"

from geopulse.l1_ingestion_detection.models import AnomalySignal, RawRecord
from geopulse.l1_ingestion_detection.settings import Settings
from geopulse.l1_ingestion_detection.store import SqliteStore
from geopulse.l1_ingestion_detection.detection.dedupe import Deduplicator, canonicalize_url
from geopulse.l1_ingestion_detection.detection.anomaly_detector import AnomalyDetector, bucket

THEME = "chokepoint_hormuz"


@pytest.fixture()
def env(tmp_path):
    s = Settings(sqlite_path=str(tmp_path / "t.db"))
    store = SqliteStore(s)
    return s, store, Deduplicator(store), AnomalyDetector(store, s)


def _seed_baseline(store, key, days, base, now):
    for i in range(days * 96):
        ts = bucket(now - timedelta(minutes=15 * (days * 96 - i)), 15)
        store.add_series_point(key, ts, base + (i % 3) * 0.5)


def test_url_canonicalization():
    assert canonicalize_url("https://www.reuters.com/x/?utm_source=t&id=1") == \
        "https://reuters.com/x?id=1"


def test_near_duplicate_collapse(env):
    _, store, dd, _ = env
    mk = lambda src, url, extra="": RawRecord(
        source=src, source_type="news", url=url,
        title="Strait of Hormuz closed after strikes on tankers in gulf " + extra)
    fresh = dd.filter_new([mk("rss:a", "https://a.com/1"), mk("rss:b", "https://b.com/2", "today")])
    assert len(fresh) == 1


def test_composite_gate_and_cooldown(env):
    s, store, _, det = env
    now = datetime.now(timezone.utc)
    _seed_baseline(store, f"news:{THEME}:volume", s.baseline_days, 2.0, now)
    _seed_baseline(store, f"news:{THEME}:tone", s.baseline_days, -1.0, now)
    store.add_series_point(f"news:{THEME}:volume", bucket(now, 15), 40.0)
    store.add_series_point(f"news:{THEME}:tone", bucket(now, 15), -6.5)

    assert det.check(source_type="news") is None, "one source type must not fire"

    _seed_baseline(store, "market:^VIX:close", s.baseline_days, 15.0, now)
    store.add_series_point("market:^VIX:close", bucket(now, 15), 24.0)
    sig = det.check(source_type="market")
    assert sig is not None and sig.theme == THEME
    assert set(sig.source_types) == {"news", "market"}

    assert det.check(source_type="market") is None, "cooldown must suppress refire"

    roundtrip = AnomalySignal.model_validate_json(sig.model_dump_json())
    assert roundtrip.id == sig.id
