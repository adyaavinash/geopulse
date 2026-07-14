# GeoPulse — Geopolitical Event-Driven Sector Impact Prediction

Given a global shock (Strait of Hormuz closure, Korea market crash), predict
which sectors ride the wave and which face losses — with confidence scores and
cited causal transmission chains. Multi-agent LLM system on Azure free/low-cost
services. **Decision-support / risk triage, not investment advice.**

## Layout (matches the team whiteboard)
- `src/geopulse/l1_ingestion_detection/` — **Person 1, COMPLETE**: collectors
  (GDELT, RSS, Reddit, Polymarket, market data), dedupe, anomaly detection
  (hour-matched z-scores + composite >=2-source gate + cooldown), queue publish.
- `src/geopulse/l2_orchestration/` — **Persons 2 & 3, stubs**: orchestrator hub,
  spoke agents (Analogy RAG / Transmission Reasoner / Sentiment / Quant),
  maker-checker gate, report tool.
- `l3_dashboard/` — **Person 4, stub**: Streamlit surfaces.
- `docs/` — full architecture + per-file implementation notes (v2 = current).
- `tests/fixtures/anomaly_signal.json` — the frozen L1->L2 contract.

## Quickstart (L1)
    python -m venv .venv && source .venv/bin/activate
    pip install -e .
    docker compose up -d           # azurite (queues); postgres for L2+
    cp .env.example .env           # add Reddit creds
    python -m geopulse.l1_ingestion_detection.run_local once
    python -m geopulse.l1_ingestion_detection.run_local loop
    python -m geopulse.l1_ingestion_detection.run_local drain
    pytest tests/

Replay validation (acceptance test):
    python -m geopulse.l1_ingestion_detection.run_local replay \
        --theme chokepoint_hormuz --start 2026-06-20 --days 3
