"""Agent 7 — Quantitative Signals Agent ("Data").

Per Agent_Architecture_Spec.pdf:
  Reads      affected tickers
  Tools      Market-data fetcher (yfinance / Alpha Vantage) + indicator calcs
  Data       Prices, VIX, oil futures, freight, FX
  Database   Reads the prices table (or fetches live)
  Workflow   pull live signals -> compare to thesis -> mark confirm/contradict
  Status     Wired into the L2 orchestrator (see QuantSignalsAgent below); the
             module-level `run()` below still works standalone exactly as
             before, taking L1's AnomalySignal as input directly.

Run it directly:
    python -m geopulse.l2_orchestration.agents.quant_signals_agent \\
        --theme chokepoint_hormuz --score 8.42

Or import `run(signal, sectors)` from other code — its return shape
(QuantSignalsResult) is deliberately close to what state.py's `quant_signals`
field wants. `QuantSignalsAgent` (bottom of this file) is the thin BaseAgent
adapter the orchestrator dispatches; it delegates straight to `run()` rather
than reimplementing anything, so this module's standalone CLI/tests are
untouched by orchestrator wiring.

--------------------------------------------------------------------------
Design notes
--------------------------------------------------------------------------
This agent does NOT use an LLM: the spec's workflow ("pull live signals ->
compare to thesis -> mark confirm/contradict") is a numeric comparison, not
a reasoning task, so it stays a deterministic indicator calc — cheap, fast,
and doesn't depend on any model backend being available. It reuses L1's
existing MarketDataCollector (yfinance) and store rather than re-implementing
market data fetching.

Per-sector reality check: each sector maps to an ETF proxy (config/
sector_taxonomy.yaml) and a directional expectation given the event category
(does this kind of shock typically help or hurt this sector — see
config/sector_taxonomy.yaml's beta_prior, and Section D of the project
blueprint on which sectors are defensive vs. high-beta/cyclical). The agent
compares the ETF's actual recent move against that expectation:
  - moved in the expected direction beyond a noise threshold -> "confirm"
  - moved against the expected direction beyond that threshold -> "contradict"
  - otherwise -> "neutral" (too small a move to read either way)
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, Field

from ...l1_ingestion_detection.models import AnomalySignal
from ...l1_ingestion_detection.settings import THEMES, Settings, get_settings
from ...l1_ingestion_detection.collectors.social_market_collectors import MarketDataCollector
from ...l1_ingestion_detection.store import SqliteStore, get_store
from ..state import GraphState, StateDelta
from .base_agent import BaseAgent

logger = logging.getLogger("geopulse.l2.quant_signals_agent")

# ---------------------------------------------------------------------------
# Theme -> affected sectors placeholder mapping.
#
# Same caveat as sentiment_agent.py: this belongs to Agent 5's causal-graph
# walk once it exists. Kept identical here so both standalone agents agree
# on "affected sectors" for the same theme until they're both wired into a
# shared orchestrator state. The orchestrator's QuantSignalsAgent wrapper
# below prefers the graph-derived sectors (state.transmission_chains) and
# only falls back to this map for standalone runs.
# ---------------------------------------------------------------------------
THEME_SECTOR_MAP: dict[str, list[str]] = {
    "chokepoint_hormuz": ["energy", "defense_aerospace", "airlines", "gold", "materials"],
    "chokepoint_suez": ["energy", "materials", "industrials", "consumer_disc"],
    "armed_conflict_escalation": ["defense_aerospace", "energy", "gold"],
    "market_crash": ["consumer_staples", "utilities", "health_care", "gold"],
    "sanctions_exportcontrols": ["semiconductors", "energy", "financials"],
}
DEFAULT_SECTORS = ["energy", "defense_aerospace", "airlines", "financials", "semiconductors"]


def sectors_for_theme(theme: str) -> list[str]:
    return THEME_SECTOR_MAP.get(theme, DEFAULT_SECTORS)


# Sector -> ETF proxy + expected move direction on a *negative* geopolitical
# shock for that theme category (+1 = expected to rise, -1 = expected to
# fall). Mirrors config/sector_taxonomy.yaml's tickers and Section D/F of
# the project blueprint's winners/losers logic. This is a prior, not a
# certainty — the whole point of this agent is to check it against live data.
SECTOR_ETF_MAP: dict[str, dict] = {
    "energy":            {"etf": "XLE",  "expected_direction": +1},
    "defense_aerospace": {"etf": "ITA",  "expected_direction": +1},
    "financials":        {"etf": "XLF",  "expected_direction": -1},
    "airlines":          {"etf": "JETS", "expected_direction": -1},
    "semiconductors":    {"etf": "SMH",  "expected_direction": -1},
    "materials":         {"etf": "XLB",  "expected_direction": -1},
    "industrials":       {"etf": "XLI",  "expected_direction": -1},
    "consumer_staples":  {"etf": "XLP",  "expected_direction": +1},   # defensive
    "consumer_disc":     {"etf": "XLY",  "expected_direction": -1},
    "utilities":         {"etf": "XLU",  "expected_direction": +1},   # defensive
    "health_care":       {"etf": "XLV",  "expected_direction": +1},   # defensive
    "technology":        {"etf": "XLK",  "expected_direction": -1},
    "gold":              {"etf": "GLD",  "expected_direction": +1},   # safe haven
    "gold_miners":       {"etf": "GDX",  "expected_direction": +1},   # safe haven
}

VIX_TICKER = "^VIX"
NOISE_THRESHOLD_PCT = 0.75   # moves smaller than this (in %) are read as "neutral"


# ---------------------------------------------------------------------------
# Output schema — close to what state.py's `quant_signals` field will expect.
# ---------------------------------------------------------------------------

Stance = Literal["confirm", "contradict", "neutral"]


class SectorQuantSignal(BaseModel):
    sector: str
    etf: str
    pct_move: float | None = Field(description="latest observed % move; None if data unavailable")
    expected_direction: int = Field(description="+1 sector expected to rise, -1 expected to fall")
    stance: Stance
    close_price: float | None = None
    baseline_price: float | None = None


class QuantSignalsResult(BaseModel):
    """Standalone-run output. Shape mirrors the future StateDelta.quant_signals."""

    signal_id: str
    theme: str
    scored_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    vix_level: float | None = None
    vix_pct_move: float | None = None
    sectors: list[SectorQuantSignal]
    overall_stance: Stance
    notes: str = ""


# ---------------------------------------------------------------------------
# Agent entry point
# ---------------------------------------------------------------------------

def _latest_and_baseline(
    store: SqliteStore, ticker: str, baseline_hours: int = 24
) -> tuple[float | None, float | None]:
    """Latest stored close for `ticker`, and the earliest close within the
    last `baseline_hours` to diff against. Series key matches what
    MarketDataCollector's records would be stored under if L1's ingestion
    loop is also populating `series` — this agent additionally does its own
    live fetch below so it doesn't depend on that loop having run recently."""
    since = datetime.now(timezone.utc) - timedelta(hours=baseline_hours)
    points = store.get_series(f"market:{ticker}:close", since=since)
    if not points:
        return None, None
    latest = points[-1][1]
    baseline = points[0][1]
    return latest, baseline


def _fetch_live_snapshot(settings: Settings, tickers: list[str]) -> dict[str, float]:
    """Best-effort live pull via yfinance for the given tickers, independent
    of whatever L1's polling loop has already stored. Returns {ticker: close}
    for whatever resolves; missing tickers are simply absent (no exception)."""
    collector = MarketDataCollector(settings)
    # MarketDataCollector reads settings.market_tickers, so scope it to just
    # the tickers this run needs without mutating the shared Settings object.
    scoped_settings = settings.model_copy(update={"market_tickers": tickers})
    collector.settings = scoped_settings
    try:
        records = collector.fetch()
    except Exception:
        logger.exception("live market fetch failed")
        return {}
    out: dict[str, float] = {}
    for r in records:
        ticker = r.metadata.get("ticker")
        close = r.metadata.get("close")
        if ticker and close is not None:
            out[ticker] = float(close)
    return out


def _store_snapshot(store: SqliteStore, prices: dict[str, float]) -> None:
    now = datetime.now(timezone.utc)
    for ticker, close in prices.items():
        try:
            store.add_series_point(f"market:{ticker}:close", now, close)
        except Exception:
            logger.exception("failed to persist snapshot for %s", ticker)


def _stance(pct_move: float | None, expected_direction: int) -> Stance:
    if pct_move is None or abs(pct_move) < NOISE_THRESHOLD_PCT:
        return "neutral"
    actual_direction = 1 if pct_move > 0 else -1
    return "confirm" if actual_direction == expected_direction else "contradict"


def run(
    signal: AnomalySignal,
    sectors: list[str] | None = None,
    settings: Settings | None = None,
    store: SqliteStore | None = None,
) -> QuantSignalsResult:
    """Standalone run: pull a live market snapshot for VIX + this event's
    affected-sector ETF proxies, compare each against a prior directional
    expectation, return a QuantSignalsResult.

    This is also what QuantSignalsAgent.run(state) below delegates to once
    the orchestrator is driving — it passes state's own settings/store (when
    injected) and the sectors state.transmission_chains already derived.
    """
    settings = settings or get_settings()
    store = store or get_store(settings)
    sectors = sectors or sectors_for_theme(signal.theme)

    proxy_map = {s: SECTOR_ETF_MAP[s] for s in sectors if s in SECTOR_ETF_MAP}
    unmapped = [s for s in sectors if s not in SECTOR_ETF_MAP]
    if unmapped:
        logger.warning("no ETF proxy for sectors: %s", unmapped)

    tickers = [VIX_TICKER] + [info["etf"] for info in proxy_map.values()]
    live_prices = _fetch_live_snapshot(settings, tickers)
    if live_prices:
        _store_snapshot(store, live_prices)

    vix_level = live_prices.get(VIX_TICKER)
    vix_latest, vix_baseline = _latest_and_baseline(store, VIX_TICKER)
    vix_level = vix_level if vix_level is not None else vix_latest
    vix_pct_move = None
    if vix_level is not None and vix_baseline:
        vix_pct_move = round((vix_level - vix_baseline) / vix_baseline * 100, 2)

    sector_results: list[SectorQuantSignal] = []
    for sector, info in proxy_map.items():
        etf = info["etf"]
        close = live_prices.get(etf)
        latest, baseline = _latest_and_baseline(store, etf)
        close = close if close is not None else latest
        pct_move = None
        if close is not None and baseline:
            pct_move = round((close - baseline) / baseline * 100, 2)

        sector_results.append(SectorQuantSignal(
            sector=sector, etf=etf, pct_move=pct_move,
            expected_direction=info["expected_direction"],
            stance=_stance(pct_move, info["expected_direction"]),
            close_price=close, baseline_price=baseline,
        ))

    for sector in unmapped:
        sector_results.append(SectorQuantSignal(
            sector=sector, etf="", pct_move=None, expected_direction=0, stance="neutral",
        ))

    confirms = sum(1 for s in sector_results if s.stance == "confirm")
    contradicts = sum(1 for s in sector_results if s.stance == "contradict")
    if confirms > contradicts:
        overall: Stance = "confirm"
    elif contradicts > confirms:
        overall = "contradict"
    else:
        overall = "neutral"

    notes = ""
    if not live_prices and all(s.pct_move is None for s in sector_results) and vix_pct_move is None:
        notes = (
            "Live market fetch returned nothing (network unavailable or yfinance "
            "failed) and no recent series data was already stored; all sector "
            "moves are reported as unavailable/neutral."
        )
    elif not live_prices:
        notes = (
            "Live market fetch unavailable this run; sector moves are computed "
            "from previously stored price series instead of a fresh snapshot."
        )

    return QuantSignalsResult(
        signal_id=signal.id, theme=signal.theme,
        vix_level=vix_level, vix_pct_move=vix_pct_move,
        sectors=sector_results, overall_stance=overall, notes=notes,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    ap = argparse.ArgumentParser(description="Agent 7 — Quantitative Signals Agent (standalone)")
    ap.add_argument("--theme", required=True, choices=list(THEMES))
    ap.add_argument("--score", type=float, default=5.0, help="synthetic AnomalySignal.score")
    ap.add_argument("--sectors", nargs="*", default=None, help="override affected sectors")
    args = ap.parse_args()

    signal = AnomalySignal(
        theme=args.theme, score=args.score, source_types=["market"],
        window_minutes=60, is_synthetic=True,
    )
    result = run(signal, sectors=args.sectors)
    print(result.model_dump_json(indent=2))


# ---------------------------------------------------------------------------
# Orchestrator wiring — thin BaseAgent adapter over run() above.
#
# Deliberately just an adapter, not a rewrite: agent 7's standalone run()/
# main()/tests above are untouched, so its independent CLI usage and backtest
# script keep working exactly as before. This class is the only new surface
# the orchestrator depends on.
# ---------------------------------------------------------------------------

def _signal_from_event(event) -> AnomalySignal:
    return AnomalySignal(
        id=event.signal_id,
        theme=event.theme,
        score=float(event.severity),
        source_types=["market"],
        window_minutes=180,
        is_synthetic=event.query is not None,
        query=event.query,
    )


def _sectors_from_state(state: GraphState) -> list[str] | None:
    """Prefer Node 5's graph-derived sectors over the theme placeholder
    above once the Transmission Reasoner has run — see THEME_SECTOR_MAP's
    docstring note on why this is the intended upgrade path."""
    sectors = sorted({chain.sector for chain in state.transmission_chains})
    return sectors or None


class QuantSignalsAgent(BaseAgent):
    name = "quant_signals"
    tier = "cheap"   # unused: this agent never calls an LLM (see module docstring)

    def __init__(
        self,
        llm=None,
        settings: Settings | None = None,
        store: SqliteStore | None = None,
    ) -> None:
        super().__init__(llm=llm)
        self.settings = settings
        self.store = store

    def run(self, state: GraphState) -> StateDelta:
        signal = _signal_from_event(state.event)
        sectors = _sectors_from_state(state)
        result = run(signal, sectors=sectors, settings=self.settings, store=self.store)
        evidence = [
            f"quant:{s.sector}:{s.etf}:{s.pct_move}"
            for s in result.sectors
            if s.etf and s.pct_move is not None
        ]
        return StateDelta(
            agent=self.name,
            quant_signals=result.model_dump(mode="json"),
            evidence=evidence,
            notes=result.notes,
        )


if __name__ == "__main__":
    main()
