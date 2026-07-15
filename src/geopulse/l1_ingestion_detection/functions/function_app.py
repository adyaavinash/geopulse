"""GeoPulse — Azure Functions entry points (Python v2 programming model).

This file is deliberately thin: every trigger is an adapter that parses
trigger metadata, calls into the importable `geopulse` packages, and
persists/enqueues results. No business logic lives here, which keeps the
collectors and detection code unit-testable and portable off Azure.

Free-tier math: the schedules below produce roughly
  GDELT (96/day) + RSS (288/day) + social (96/day) + markets (24/day)
  ≈ 504 executions/day ≈ 15K/month — about 1.5% of the Consumption
  plan's 1M free executions/month.
"""

import json
import logging

import azure.functions as func

from geopulse.l1_ingestion_detection.settings import get_settings
from geopulse.l1_ingestion_detection.detection.anomaly_detector import AnomalyDetector
from geopulse.l1_ingestion_detection.detection.dedupe import Deduplicator
from geopulse.l1_ingestion_detection.collectors.gdelt_collector import GdeltCollector
from geopulse.l1_ingestion_detection.collectors.social_market_collectors import MarketDataCollector
from geopulse.l1_ingestion_detection.collectors.social_market_collectors import PredictionMarketCollector
from geopulse.l1_ingestion_detection.collectors.social_market_collectors import RedditCollector
from geopulse.l1_ingestion_detection.collectors.rss_collector import RssCollector
from geopulse.l1_ingestion_detection.models import AnomalySignal
from geopulse.l1_ingestion_detection.queue_bus import QueueBus
from geopulse.l1_ingestion_detection.store import get_store

logger = logging.getLogger("geopulse.functions")

app = func.FunctionApp()

settings = get_settings()          # env vars / Key Vault refs, cached
store = get_store(settings)        # CosmosStore or PostgresStore per STORAGE_BACKEND
bus = QueueBus(settings)           # wraps the 'anomaly-events' Storage Queue
dedupe = Deduplicator(store)
detector = AnomalyDetector(store, settings)


# ---------------------------------------------------------------------------
# Shared post-ingest hook
# ---------------------------------------------------------------------------

def _ingest_and_detect(collector, source_type: str) -> None:
    """Run one collector, persist deduped records, then check for anomalies.

    Detection runs after *every* ingest, but `check()` only emits a signal
    when the composite trigger fires: >=2 independent source types
    (news / social / market) must spike within the lookback window.
    That composite gate is the cost control for the whole system — it is
    what keeps LLM pipeline invocations rare.
    """
    records = collector.fetch()
    fresh = dedupe.filter_new(records)
    if fresh:
        store.save_records(fresh)
    logger.info("%s: %d fetched, %d new", source_type, len(records), len(fresh))

    # check() already gates on cooldown internally and persists the signal
    # (for future cooldown lookups) before returning it — do not re-check
    # recent_signal_exists here, it would always match the signal just saved.
    signal: AnomalySignal | None = detector.check(source_type=source_type, records=fresh)
    if signal is None:
        return

    bus.publish_anomaly(signal)
    logger.warning(
        "ANOMALY enqueued: theme=%s score=%.2f sources=%s",
        signal.theme, signal.score, signal.source_types,
    )


# ---------------------------------------------------------------------------
# Timer triggers — NCRONTAB format: {second} {minute} {hour} {day} {month} {day-of-week}
# ---------------------------------------------------------------------------

@app.timer_trigger(schedule="0 */15 * * * *", arg_name="timer")   # every 15 min
def poll_gdelt(timer: func.TimerRequest) -> None:
    """GDELT publishes new event/GKG files every 15 minutes — poll on the
    same cadence. Also updates per-theme article-count time series that
    the anomaly detector's rolling z-score reads."""
    if timer.past_due:
        logger.info("poll_gdelt running late; catching up")
    _ingest_and_detect(GdeltCollector(settings), source_type="news")


@app.timer_trigger(schedule="0 */5 * * * *", arg_name="timer")    # every 5 min
def poll_rss(timer: func.TimerRequest) -> None:
    """Wire headlines (Reuters/AP/Al Jazeera/EIA/OPEC feeds) are the
    lowest-latency free source, so they get the tightest schedule."""
    _ingest_and_detect(RssCollector(settings), source_type="news")


@app.timer_trigger(schedule="0 7,22,37,52 * * * *", arg_name="timer")  # every 15 min, offset
def poll_social(timer: func.TimerRequest) -> None:
    """Reddit + prediction markets. Offset from poll_gdelt so the two
    15-minute jobs never run in the same instant (smoother RU usage on
    the shared 1000 RU/s Cosmos cap)."""
    _ingest_and_detect(RedditCollector(settings), source_type="social")
    _ingest_and_detect(PredictionMarketCollector(settings), source_type="social")


@app.timer_trigger(schedule="0 5 * * * *", arg_name="timer")      # hourly at :05
def poll_markets(timer: func.TimerRequest) -> None:
    """Sector ETFs, VIX, Brent/WTI proxies, DXY, USDJPY, GLD. Hourly is
    enough for the quant-confirmation role; the agent pipeline pulls a
    fresh snapshot itself when it actually runs."""
    _ingest_and_detect(MarketDataCollector(settings), source_type="market")


# ---------------------------------------------------------------------------
# Queue trigger — the MVP agent-pipeline runner
# ---------------------------------------------------------------------------
# Phase 1: the LangGraph pipeline runs right here inside a Function
# (fine while a full run stays under the 10-minute Consumption timeout).
# Phase 2/3: delete this function; the KEDA queue scaler on Container Apps
# consumes the same queue instead. Nothing upstream changes.

@app.queue_trigger(
    arg_name="msg",
    queue_name="anomaly-events",
    connection="STORAGE_CONNECTION_STRING",
)
def run_agent_pipeline(msg: func.QueueMessage) -> None:
    from geopulse.l2_orchestration.orchestrator import build_graph   # lazy: keep timer cold-starts fast

    signal = AnomalySignal.model_validate_json(msg.get_body())
    logger.info("Pipeline start: theme=%s score=%.2f", signal.theme, signal.score)

    graph = build_graph(settings, store)
    final_state = graph.invoke(
        {"anomaly": signal},
        config={
            "configurable": {"thread_id": signal.id},   # checkpoint/resume key
            "recursion_limit": settings.max_graph_steps,
        },
    )

    verdict = final_state.get("verdict")
    if verdict is None:
        # Human-in-the-loop interrupt fired (high severity): state is
        # checkpointed; the dashboard's approve action resumes the graph.
        logger.warning("Pipeline paused for human review: %s", signal.id)
        return

    store.save_verdict(verdict)
    logger.info(
        "Verdict saved: event=%s winners=%s losers=%s",
        verdict.event_id,
        [c.sector for c in verdict.calls if c.direction == "winner"][:3],
        [c.sector for c in verdict.calls if c.direction == "loser"][:3],
    )


# ---------------------------------------------------------------------------
# HTTP trigger — manual/dev entry point
# ---------------------------------------------------------------------------

@app.route(route="trigger", auth_level=func.AuthLevel.FUNCTION, methods=["POST"])
def manual_trigger(req: func.HttpRequest) -> func.HttpResponse:
    """POST /api/trigger {"query": "strait of hormuz"} — bypasses detection
    and drops a synthetic anomaly on the queue. Used by run_pipeline.py,
    demos, and the replay harness."""
    body = req.get_json()
    signal = AnomalySignal.synthetic(query=body["query"])
    bus.publish_anomaly(signal)
    return func.HttpResponse(
        json.dumps({"enqueued": signal.id}),
        status_code=202,
        mimetype="application/json",
    )
