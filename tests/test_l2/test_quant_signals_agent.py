"""Accuracy/correctness tests for Agent 7 (Quant Signals Agent).

Two things are tested here, both fully offline (no network, no yfinance
calls — those need real internet access; see scripts/backtest_quant_signals.py
for the historical-accuracy backtest that requires it):

1. `_stance()` — the confirm/contradict/neutral decision rule. This is pure
   and total, so every branch is exhaustively testable.
2. `run()` end-to-end against an in-memory SqliteStore seeded with known
   prices (no live fetch — dry_run collectors return nothing, so `run()`
   falls back to the seeded store, letting us assert on exact output).
3. `quant_signals_historical.pct_move_over_window()` — the event-window
   math (pre/post close selection), tested against injected synthetic price
   series via mocking `fetch_history`, so no network is needed.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest

os.environ.setdefault("GEOPULSE_SQLITE_PATH", "/tmp/geopulse_test_l2.db")
os.environ.setdefault("GEOPULSE_DRY_RUN", "true")

from geopulse.l1_ingestion_detection.models import AnomalySignal
from geopulse.l1_ingestion_detection.settings import Settings
from geopulse.l1_ingestion_detection.store import SqliteStore
from geopulse.l2_orchestration.agents import quant_signals_agent as qa
from geopulse.l2_orchestration.agents import quant_signals_historical as qh


# ---------------------------------------------------------------------------
# 1. _stance() — exhaustive branch coverage
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pct_move,expected_direction,want", [
    (3.0, 1, "confirm"),        # moved up as expected -> confirm
    (-3.0, -1, "confirm"),      # moved down as expected -> confirm
    (3.0, -1, "contradict"),    # moved up, expected down -> contradict
    (-3.0, 1, "contradict"),    # moved down, expected up -> contradict
    (0.1, 1, "neutral"),        # tiny move, below noise threshold -> neutral
    (-0.1, -1, "neutral"),
    (None, 1, "neutral"),       # no data -> neutral, never a false confirm/contradict
    (0.75, 1, "confirm"),       # exactly at the noise threshold boundary
    (0.74, 1, "neutral"),       # just under the noise threshold boundary
])
def test_stance_decision_table(pct_move, expected_direction, want):
    assert qa._stance(pct_move, expected_direction) == want


# ---------------------------------------------------------------------------
# 2. run() against a seeded in-memory store (no live network involved)
# ---------------------------------------------------------------------------

@pytest.fixture()
def env(tmp_path):
    # fixtures_dir points at an empty tmp directory (not this package's real
    # fixtures/market.json) so dry_run's fixture-fallback path stays empty
    # for tests that specifically want "no data anywhere" — otherwise a
    # real market.json sitting next to the package would silently supply
    # data these tests assume is absent.
    empty_fixtures = tmp_path / "empty_fixtures"
    empty_fixtures.mkdir()
    s = Settings(sqlite_path=str(tmp_path / "quant_test.db"), dry_run=True,
                 fixtures_dir=str(empty_fixtures))
    store = SqliteStore(s)
    return s, store


def _seed(store, ticker, baseline_price, latest_price, hours_ago=20):
    now = datetime.now(timezone.utc)
    store.add_series_point(f"market:{ticker}:close", now - timedelta(hours=hours_ago), baseline_price)
    store.add_series_point(f"market:{ticker}:close", now, latest_price)


def test_run_confirms_expected_direction(env):
    s, store = env
    _seed(store, "XLE", 80.0, 82.4)    # +3%, energy expects +1 -> confirm
    signal = AnomalySignal(theme="chokepoint_hormuz", score=8.0, source_types=["market"],
                            window_minutes=60, is_synthetic=True)
    result = qa.run(signal, sectors=["energy"], settings=s, store=store)
    energy = next(r for r in result.sectors if r.sector == "energy")
    assert energy.stance == "confirm"
    assert energy.pct_move == pytest.approx(3.0, abs=0.01)


def test_run_contradicts_expected_direction(env):
    s, store = env
    _seed(store, "JETS", 20.0, 20.4)   # +2%, airlines expects -1 -> contradict
    signal = AnomalySignal(theme="chokepoint_hormuz", score=8.0, source_types=["market"],
                            window_minutes=60, is_synthetic=True)
    result = qa.run(signal, sectors=["airlines"], settings=s, store=store)
    airlines = next(r for r in result.sectors if r.sector == "airlines")
    assert airlines.stance == "contradict"


def test_run_handles_no_data_gracefully(env):
    s, store = env  # nothing seeded
    signal = AnomalySignal(theme="chokepoint_hormuz", score=8.0, source_types=["market"],
                            window_minutes=60, is_synthetic=True)
    result = qa.run(signal, sectors=["energy"], settings=s, store=store)
    energy = next(r for r in result.sectors if r.sector == "energy")
    assert energy.stance == "neutral"
    assert energy.pct_move is None
    assert result.notes  # should explain why


def test_run_reports_unmapped_sector_as_neutral(env):
    s, store = env
    signal = AnomalySignal(theme="chokepoint_hormuz", score=8.0, source_types=["market"],
                            window_minutes=60, is_synthetic=True)
    result = qa.run(signal, sectors=["not_a_real_sector"], settings=s, store=store)
    assert result.sectors[0].sector == "not_a_real_sector"
    assert result.sectors[0].stance == "neutral"


def test_overall_stance_ties_to_neutral(env):
    s, store = env
    _seed(store, "XLE", 80.0, 82.4)    # confirm
    _seed(store, "JETS", 20.0, 20.4)   # contradict
    signal = AnomalySignal(theme="chokepoint_hormuz", score=8.0, source_types=["market"],
                            window_minutes=60, is_synthetic=True)
    result = qa.run(signal, sectors=["energy", "airlines"], settings=s, store=store)
    assert result.overall_stance == "neutral"  # 1 confirm + 1 contradict -> tie


# ---------------------------------------------------------------------------
# 3. Historical event-window math (offline, via mocked fetch_history)
# ---------------------------------------------------------------------------

def _synthetic_series(event: date, pre_price: float, ramp_to: float, days_after: int = 10):
    """Weekday-only price series: flat at pre_price before `event`, then
    ramping linearly to `ramp_to` by trading-day-5 after event, then flat."""
    series = []
    d = event - timedelta(days=10)
    while d < event:
        if d.weekday() < 5:
            series.append((datetime.combine(d, datetime.min.time()), pre_price))
        d += timedelta(days=1)

    d = event
    trading_day = 0
    while d <= event + timedelta(days=days_after):
        if d.weekday() < 5:
            price = pre_price + (ramp_to - pre_price) * min(trading_day, 5) / 5
            series.append((datetime.combine(d, datetime.min.time()), price))
            trading_day += 1
        d += timedelta(days=1)
    return series


def test_pct_move_over_window_basic_ramp():
    event = date(2024, 3, 15)  # a Friday
    series = _synthetic_series(event, pre_price=100.0, ramp_to=110.0)
    with patch.object(qh, "fetch_history", return_value=series):
        pct_move, pre, post = qh.pct_move_over_window("FAKE", event, window_days=5)
    assert pre == pytest.approx(100.0)
    assert post == pytest.approx(110.0)
    assert pct_move == pytest.approx(10.0)


def test_pct_move_over_window_zero_days_is_event_day_close():
    event = date(2024, 3, 15)
    series = _synthetic_series(event, pre_price=100.0, ramp_to=110.0)
    with patch.object(qh, "fetch_history", return_value=series):
        pct_move_0, _, post_0 = qh.pct_move_over_window("FAKE", event, window_days=0)
        pct_move_5, _, post_5 = qh.pct_move_over_window("FAKE", event, window_days=5)
    assert post_0 < post_5  # day 0 should be earlier in the ramp than day 5
    assert pct_move_0 < pct_move_5


def test_pct_move_over_window_accepts_iso_string():
    event = date(2019, 9, 16)
    series = _synthetic_series(event, pre_price=60.0, ramp_to=69.0)
    with patch.object(qh, "fetch_history", return_value=series):
        pct_move, pre, post = qh.pct_move_over_window("XLE", "2019-09-16", window_days=1)
    assert pre == pytest.approx(60.0)
    assert pct_move is not None


def test_pct_move_over_window_no_data_returns_nones():
    with patch.object(qh, "fetch_history", return_value=[]):
        pct_move, pre, post = qh.pct_move_over_window("FAKE", date(2024, 1, 1))
    assert (pct_move, pre, post) == (None, None, None)


def test_pct_move_over_window_missing_pre_or_post_returns_nones():
    # Only post-event data, no pre-event baseline
    event = date(2024, 3, 15)
    series = [(datetime.combine(event, datetime.min.time()), 100.0)]
    with patch.object(qh, "fetch_history", return_value=series):
        pct_move, pre, post = qh.pct_move_over_window("FAKE", event)
    assert (pct_move, pre, post) == (None, None, None)
