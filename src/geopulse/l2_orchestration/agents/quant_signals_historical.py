"""Historical price fetch for backtesting Agent 7 (quant_signals_agent).

This is deliberately a separate module from quant_signals_agent.py: the live
agent only ever needs "latest close" (via L1's MarketDataCollector, which
calls `yfinance.download(period="1d", interval="1h")`), but validating the
agent's accuracy needs full date-ranged OHLC history around real past
events — a different yfinance call shape, so it gets its own thin wrapper
rather than overloading the collector.

Network note: `yfinance.download` needs to reach Yahoo Finance
(query1/query2.finance.yahoo.com), which is NOT on this sandbox's egress
allowlist. This module works on a machine with normal internet access; in
this sandbox, `fetch_history()` will raise/log and return an empty
DataFrame-like result, same failure mode as the live agent already handles.
Everything else in this module (the backtest scoring logic) is pure and
fully testable offline against injected price series — see
tests/test_l2/test_quant_signals_agent.py.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

logger = logging.getLogger("geopulse.l2.quant_signals_historical")


def fetch_history(
    ticker: str, start: str | date, end: str | date
) -> list[tuple[datetime, float]]:
    """Daily close prices for `ticker` between start and end (inclusive-ish;
    yfinance's `end` is exclusive, so callers should pass one day past the
    window they actually want). Returns [] on any failure — network unavailable,
    ticker delisted, empty range — never raises, matching the rest of this
    agent's "degrade to empty, don't crash the pipeline" convention.
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance not installed")
        return []

    try:
        df = yf.download(
            ticker, start=str(start), end=str(end),
            interval="1d", progress=False, auto_adjust=False,
        )
    except Exception:
        logger.exception("historical fetch failed for %s", ticker)
        return []

    if df is None or df.empty:
        logger.warning("no historical data returned for %s (%s to %s)", ticker, start, end)
        return []

    closes = df["Close"]
    # yfinance can return a DataFrame with a MultiIndex column (ticker, field)
    # for some call shapes even with a single ticker; normalize to a Series.
    if hasattr(closes, "columns"):
        closes = closes.iloc[:, 0]

    return [
        (ts.to_pydatetime(), float(val))
        for ts, val in closes.items()
        if val == val  # drop NaN
    ]


def pct_move_over_window(
    ticker: str, event_date: str | date, window_days: int = 5
) -> tuple[float | None, float | None, float | None]:
    """Returns (pct_move, pre_event_close, post_event_close) using the last
    close strictly before event_date as the baseline, and the close
    `window_days` *trading days after and including* event_date as the
    comparison point (event_date itself is trading-day 0, so window_days=5
    means "5 trading days past day 0" -> a [0, +5] event window per the
    project blueprint's Campbell/Lo/MacKinlay-style notation). Simplified to
    a single pre/post pair rather than full cumulative abnormal returns
    (that belongs to analysis/event_study.py, Person 4's territory — this is
    just enough to score confirm/contradict).
    """
    if isinstance(event_date, str):
        event_date = date.fromisoformat(event_date)

    start = event_date - timedelta(days=10)          # baseline lookback
    end = event_date + timedelta(days=window_days + 5)  # padding for weekends/holidays
    history = fetch_history(ticker, start, end)
    if not history:
        return None, None, None

    pre = [v for ts, v in history if ts.date() < event_date]
    post = [(ts, v) for ts, v in history if ts.date() >= event_date]
    if not pre or not post:
        return None, None, None

    pre_close = pre[-1]
    target_idx = min(window_days, len(post) - 1)
    post_close = post[target_idx][1]

    pct_move = round((post_close - pre_close) / pre_close * 100, 2)
    return pct_move, pre_close, post_close
