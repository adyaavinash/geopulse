"""Accuracy backtest for Agent 7 — Quant Signals Agent.

Answers the question "how do I test accuracy in this agent" the way the
project blueprint's own methodology (Section B.7) proposes: directional hit
rate — for each known historical event, does the agent's confirm/contradict
call on each sector ETF match the *actual* realized move in the days after?

This is NOT a unit test (see tests/test_l2/test_quant_signals_agent.py for
that) — it's a small standalone script because it needs real network access
to yfinance for historical OHLC data, which this sandbox cannot reach
(query1/query2.finance.yahoo.com are not on the egress allowlist here). Run
it on a machine with normal internet access:

    python scripts/backtest_quant_signals.py
    python scripts/backtest_quant_signals.py --window-days 10
    python scripts/backtest_quant_signals.py --event abqaiq_2019

--------------------------------------------------------------------------
Why this is the right way to test THIS agent's accuracy
--------------------------------------------------------------------------
Agent 7 is a deterministic function of (a) a directional prior per sector
(SECTOR_ETF_MAP in quant_signals_agent.py) and (b) an observed price move.
There's no model to grade for "reasoning quality" — the only thing that can
be wrong is the prior itself, or the noise threshold. So "accuracy" here
means: replay real past shocks, get the *actual* sector move that happened,
and check whether the prior's direction matches. This reuses the exact same
`_stance()` function the live agent calls — same decision logic, historical
prices instead of live/stored ones — so a passing backtest is evidence about
the real agent, not a parallel reimplementation.

Caveat inherited from the project blueprint (Section E/Caveats): daily-
frequency geopolitical-signal-to-price transmission is documented as
statistically weak (the CausalAlpha 2026 finding: <5% of forecast-error
variance explained). A single-event backtest like this is a sanity check on
directional priors, not proof of alpha — treat a low hit rate as "the prior
needs revisiting or the event was noisy," and a high hit rate on n=1-2
events as encouraging but not conclusive. Add more events over time (this
script is written so adding one is a single dict entry).
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass

from geopulse.l2_orchestration.agents.quant_signals_agent import (
    SECTOR_ETF_MAP,
    _stance,
)
from geopulse.l2_orchestration.agents.quant_signals_historical import (
    pct_move_over_window,
)


@dataclass
class HistoricalEvent:
    name: str
    event_date: str            # ISO date the shock broke
    theme: str                 # matches settings.THEMES / event_taxonomy.yaml
    sectors: list[str]         # sectors this event is expected to move
    source_note: str           # citation for why this is a verified anchor


# ---------------------------------------------------------------------------
# Verified historical anchors. Start small and grow this list — each entry
# needs an independently-checkable source, per the blueprint's own caution
# about not treating fast-moving/unverified news as settled history.
# ---------------------------------------------------------------------------
EVENTS: dict[str, HistoricalEvent] = {
    "abqaiq_2019": HistoricalEvent(
        name="2019 Abqaiq-Khurais drone attack",
        event_date="2019-09-16",   # first trading day after the Sat Sept 14 attack
        theme="chokepoint_hormuz",  # closest existing theme; Abqaiq isn't a chokepoint
        # closure per se, but it's the project blueprint's own calibration
        # analogue for a Hormuz-style oil-supply shock (see blueprint Section E.4).
        sectors=["energy", "airlines", "gold"],
        source_note=(
            "EIA (eia.gov/todayinenergy/detail.php?id=41413): attack Sat Sept 14 "
            "2019; Brent/WTI's largest single-day increase in a decade on the "
            "first trading day after, Mon Sept 16. Baker Institute: Brent jumped "
            "from ~$60 to ~$69/bbl, then fully unwound within ~2 weeks as Aramco "
            "restored output."
        ),
    ),
}


def run_backtest(event_key: str, window_days: int) -> dict:
    event = EVENTS[event_key]
    proxy_map = {s: SECTOR_ETF_MAP[s] for s in event.sectors if s in SECTOR_ETF_MAP}

    rows = []
    for sector, info in proxy_map.items():
        etf = info["etf"]
        pct_move, pre_close, post_close = pct_move_over_window(
            etf, event.event_date, window_days=window_days
        )
        predicted_stance = _stance(pct_move, info["expected_direction"])
        # Ground truth: did the ETF actually move in the direction the prior
        # expected? This is the same directional check _stance() does — we
        # call it directly rather than re-deriving "correct" separately, so
        # the backtest is checking real data through the real decision fn.
        rows.append({
            "sector": sector,
            "etf": etf,
            "expected_direction": info["expected_direction"],
            "pre_close": pre_close,
            "post_close": post_close,
            "pct_move": pct_move,
            "stance": predicted_stance,
            "hit": predicted_stance == "confirm",
            "data_available": pct_move is not None,
        })

    scored = [r for r in rows if r["data_available"]]
    hit_rate = (sum(r["hit"] for r in scored) / len(scored)) if scored else None

    return {
        "event": event.name,
        "event_date": event.event_date,
        "source_note": event.source_note,
        "window_days": window_days,
        "rows": rows,
        "hit_rate": hit_rate,
        "n_scored": len(scored),
        "n_total": len(rows),
    }


def print_report(result: dict) -> None:
    print(f"\n=== {result['event']} ({result['event_date']}) ===")
    print(f"source: {result['source_note']}")
    print(f"event-study window: [0, +{result['window_days']}] trading days\n")
    print(f"{'sector':<18}{'etf':<6}{'expect':<11}{'pre':<10}{'post':<10}{'%move':<9}{'stance':<12}{'hit'}")
    for r in result["rows"]:
        pre = f"{r['pre_close']:.2f}" if r["pre_close"] is not None else "n/a"
        post = f"{r['post_close']:.2f}" if r["post_close"] is not None else "n/a"
        move = f"{r['pct_move']:+.2f}%" if r["pct_move"] is not None else "n/a"
        expect = "+1 (up)" if r["expected_direction"] > 0 else "-1 (down)"
        hit_str = "-" if not r["data_available"] else ("YES" if r["hit"] else "no")
        print(f"{r['sector']:<18}{r['etf']:<6}{expect:<11}{pre:<10}{post:<10}{move:<9}{r['stance']:<12}{hit_str}")

    if result["hit_rate"] is not None:
        print(f"\nDirectional hit rate: {result['hit_rate']:.0%} "
              f"({result['n_scored']}/{result['n_total']} sectors scored"
              f"{'' if result['n_scored'] == result['n_total'] else ', rest had no data'})")
    else:
        print("\nNo data available — check network access to Yahoo Finance "
              "(query1/query2.finance.yahoo.com) from this machine.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Backtest Agent 7 against real historical events")
    ap.add_argument("--event", choices=list(EVENTS), default=None,
                     help="run one event (default: run all)")
    ap.add_argument("--window-days", type=int, default=5,
                     help="trading days after the event to measure the move over")
    args = ap.parse_args()

    keys = [args.event] if args.event else list(EVENTS)
    for key in keys:
        result = run_backtest(key, args.window_days)
        print_report(result)


if __name__ == "__main__":
    main()
