# Repository Structure — Geopolitical Sector Impact Prediction System ("GeoPulse")

A phased monorepo targeting the **Azure free/low-cost stack**: Azure Functions (collectors + detection, Consumption plan), Azure Storage Queues (messaging), Cosmos DB free tier (records + vectors + corpus), Azure Container Apps (LangGraph runtime, scale-to-zero), Azure OpenAI (the only metered cost), App Service F1 (dashboard). The code stays vendor-portable — storage and messaging sit behind narrow interfaces, so the Postgres/Kafka path remains a config swap, not a rewrite. Phase 1 files are marked **[P1]**. Stack: Python 3.11+, LangGraph, Streamlit.

```
geopulse/
├── README.md
├── pyproject.toml
├── .env.example
├── docker-compose.yml
├── Makefile
│
├── .github/
│   └── workflows/
│       └── deploy.yml
│
├── infra/
│   ├── main.bicep                   [P1]
│   ├── modules/
│   │   ├── functions.bicep          [P1]
│   │   ├── cosmos.bicep             [P1]
│   │   ├── storage.bicep            [P1]
│   │   ├── container_app.bicep
│   │   ├── openai.bicep             [P1]
│   │   └── monitoring.bicep
│   └── parameters/
│       ├── free-tier.bicepparam     [P1]
│       └── production.bicepparam
│
├── config/
│   ├── settings.py                  [P1]
│   ├── event_taxonomy.yaml          [P1]
│   ├── sector_taxonomy.yaml         [P1]
│   ├── transmission_channels.yaml   [P1]
│   └── agent_prompts/
│       ├── event_classifier.md      [P1]
│       ├── historical_analogy.md
│       ├── transmission_reasoner.md [P1]
│       ├── sentiment.md
│       ├── quant_signals.md
│       ├── contrarian.md
│       └── synthesis.md             [P1]
│
├── src/geopulse/
│   ├── __init__.py
│   │
│   ├── functions/
│   │   ├── function_app.py          [P1]
│   │   ├── host.json                [P1]
│   │   └── local.settings.json.example
│   │
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── base_collector.py        [P1]
│   │   ├── gdelt_collector.py       [P1]
│   │   ├── rss_collector.py         [P1]
│   │   ├── reddit_collector.py
│   │   ├── prediction_market_collector.py
│   │   ├── acled_collector.py
│   │   ├── ais_collector.py
│   │   └── market_data_collector.py [P1]
│   │
│   ├── detection/
│   │   ├── __init__.py
│   │   ├── anomaly_detector.py      [P1]
│   │   ├── event_clusterer.py
│   │   └── dedupe.py                [P1]
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── state.py                 [P1]
│   │   ├── graph.py                 [P1]
│   │   ├── event_classifier_agent.py [P1]
│   │   ├── historical_analogy_agent.py
│   │   ├── transmission_agent.py    [P1]
│   │   ├── sentiment_agent.py
│   │   ├── quant_signals_agent.py
│   │   ├── contrarian_agent.py
│   │   └── synthesis_agent.py       [P1]
│   │
│   ├── knowledge/
│   │   ├── __init__.py
│   │   ├── causal_graph.py
│   │   ├── graph_builder.py
│   │   ├── event_corpus/
│   │   │   ├── corpus_schema.py
│   │   │   ├── loader.py
│   │   │   └── seed_events/         (curated YAML/JSON event studies)
│   │   │       ├── 2019_abqaiq_attack.yaml
│   │   │       ├── 1990_kuwait_invasion.yaml
│   │   │       ├── 2022_russia_ukraine.yaml
│   │   │       ├── 2020_covid_crash.yaml
│   │   │       └── ...
│   │   └── rag/
│   │       ├── embedder.py
│   │       ├── retriever.py
│   │       └── vector_store.py
│   │
│   ├── signals/
│   │   ├── __init__.py
│   │   ├── volatility.py
│   │   ├── commodities.py
│   │   ├── freight.py
│   │   ├── credit_fx.py
│   │   └── risk_indices.py
│   │
│   ├── analysis/
│   │   ├── __init__.py
│   │   ├── event_study.py           [P1]
│   │   ├── abnormal_returns.py      [P1]
│   │   └── sector_mapping.py        [P1]
│   │
│   ├── evaluation/
│   │   ├── __init__.py
│   │   ├── backtester.py
│   │   ├── metrics.py               [P1]
│   │   └── calibration.py
│   │
│   ├── outputs/
│   │   ├── __init__.py
│   │   ├── verdict_schema.py        [P1]
│   │   ├── report_generator.py      [P1]
│   │   └── alerting.py
│   │
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── store.py                 [P1]
│   │   ├── cosmos_store.py          [P1]
│   │   ├── blob_store.py
│   │   ├── queue_bus.py             [P1]
│   │   ├── models.py                [P1]
│   │   ├── db.py                    (Postgres alternative)
│   │   └── migrations/              (Postgres only)
│   │
│   └── streaming/                   (Phase 3 — Event Hubs/Kafka upgrade)
│       ├── __init__.py
│       ├── producers.py
│       ├── consumers.py
│       └── topics.py
│
├── app/
│   ├── dashboard.py                 [P1]
│   ├── pages/
│   │   ├── 1_live_events.py
│   │   ├── 2_sector_verdicts.py     [P1]
│   │   ├── 3_historical_analogies.py
│   │   └── 4_backtest_results.py
│   └── components/
│       ├── verdict_table.py
│       └── transmission_chain_viz.py
│
├── scripts/
│   ├── run_pipeline.py              [P1]
│   ├── seed_event_corpus.py
│   ├── run_backtest.py
│   └── replay_historical_event.py   [P1]
│
├── notebooks/
│   ├── 01_gdelt_exploration.ipynb
│   ├── 02_event_study_validation.ipynb
│   └── 03_agent_output_evaluation.ipynb
│
└── tests/
    ├── conftest.py
    ├── test_ingestion/
    ├── test_agents/
    ├── test_analysis/
    └── fixtures/
        ├── sample_gdelt_events.json
        └── sample_verdicts.json
```

---

## What to implement in each file

### Root level

**`README.md`** — Project overview, architecture diagram (event detection → agent graph → verdict), quickstart (`make setup && make run-replay EVENT=2019_abqaiq_attack`), and the honest positioning statement: decision-support/risk-triage, not alpha generation.

**`pyproject.toml`** — Dependencies: `langgraph`, `langchain-openai` (points at Azure OpenAI endpoints), `azure-cosmos`, `azure-storage-queue`, `azure-storage-blob`, `azure-functions`, `azure-identity`, `yfinance`, `pandas`, `numpy`, `scipy`, `statsmodels`, `praw`, `httpx`, `feedparser`, `streamlit`, `plotly`, `pytest`. Optional extras groups: `[postgres]` (psycopg, pgvector, sqlalchemy, alembic), `[streaming]` (azure-eventhub / confluent-kafka), `[scraping]` (playwright, scrapy).

**`.env.example`** — Template for `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY` (local dev only — deployed code uses managed identity), `COSMOS_ENDPOINT`, `STORAGE_CONNECTION_STRING`, `STORAGE_BACKEND=cosmos`, `REDDIT_CLIENT_ID/SECRET`, `ALPHA_VANTAGE_KEY`, `ACLED_EMAIL/KEY`. Never commit real keys.

**`docker-compose.yml`** — Local dev doubles for the Azure services: `cosmos-emulator` (free local Cosmos), `azurite` (local Blob + Queues), `app`. The `[postgres]` profile swaps in `postgres` with pgvector instead.

**`Makefile`** — Targets: `setup`, `seed-corpus`, `run-pipeline`, `run-replay`, `backtest`, `dashboard`, `test`, `deploy` (wraps `az deployment sub create` with the free-tier parameter file), `func-start` (local Azure Functions runtime).

---

### `.github/workflows/`

**`deploy.yml`** — GitHub Actions pipeline: run tests → deploy Bicep (`infra/main.bicep` with `free-tier.bicepparam`) → publish the Functions package (`func azure functionapp publish`) → build/push the Container Apps image. Uses OIDC federated credentials to Azure (no stored secrets).

---

### `infra/` (Azure free-tier IaC)

**`main.bicep`** — Orchestrates all modules into one resource group. Two parameter files select the tier — this is where "free now, production later" lives as code, not as a rewrite.

**`modules/functions.bicep`** — Function App on the **Consumption plan** (1M free executions/month) with timer-trigger app settings (GDELT poll interval, RSS interval) and a system-assigned managed identity for Cosmos/Key Vault access.

**`modules/cosmos.bicep`** — Cosmos DB account with `enableFreeTier: true` (must be set at creation — it can't be enabled later, and only one free-tier account per subscription). NoSQL API, one shared-throughput database capped at 1000 RU/s so it never bills, containers for records/verdicts/corpus, and the vector-indexing policy for the RAG embeddings.

**`modules/storage.bicep`** — One storage account: Blob containers (raw articles, generated reports) + the `anomaly-events` queue. Queues replace Event Hubs at MVP scale for effectively $0.

**`modules/container_app.bicep`** — Container Apps environment with `minReplicas: 0` (scale-to-zero) for the LangGraph runtime, KEDA queue-scaler wired to `anomaly-events` so the agent pipeline wakes only when the detection layer fires. Skippable in week one if you run the graph inside a Function.

**`modules/openai.bicep`** — Azure OpenAI resource with two deployments: a mini-class model (classifier/sentiment) and a frontier model (transmission/synthesis). This is the only meaningfully metered resource — tag it for cost alerts.

**`modules/monitoring.bicep`** — Application Insights (first 5 GB/month ingestion free) + a **budget alert** on the resource group. Azure has no automatic spend cap, so this module is not optional.

**`parameters/free-tier.bicepparam`** — F1 App Service, free-tier Cosmos, Consumption Functions, scale-to-zero Container Apps, mini-model-heavy OpenAI deployments.

**`parameters/production.bicepparam`** — Swaps in Event Hubs, AI Search, provisioned Postgres, and a dedicated Container Apps plan — same templates, different knobs.

---

### `config/`

**`settings.py`** — Pydantic `Settings` class loading env vars: API keys, Cosmos endpoint/database (or Postgres URL — a `STORAGE_BACKEND=cosmos|postgres` switch selects the implementation), storage-account queue/blob connection, Azure OpenAI endpoint + deployment names per agent (mini deployment for sentiment/classification, frontier deployment for transmission/synthesis), token budget caps per pipeline run, polling intervals. Locally reads `.env`; in Azure, values come from Function App settings + Key Vault references via managed identity.

**`event_taxonomy.yaml`** — The event classification schema: categories (chokepoint_disruption, armed_conflict, market_crash, sanctions, coup, natural_disaster...), each with subtypes, CAMEO code mappings for GDELT, and severity tiers. The Event Classifier Agent validates its output against this file.

**`sector_taxonomy.yaml`** — GICS 11 sectors + subsectors, each mapped to ETF proxies (Energy→XLE, Defense→ITA, Airlines→JETS, Semis→SMH, Gold→GLD/GDX...) and representative global tickers. This is the universe every verdict is scored against.

**`transmission_channels.yaml`** — Hand-authored causal priors: e.g., `oil_supply_shock: {raises: [crude, tanker_rates, gold], sectors_up: [energy, defense], sectors_down: [airlines, chemicals, asian_refiners], mechanism: "input cost passthrough / safe haven / escalation premium"}`. This is your MVP's poor-man's knowledge graph — the Transmission Agent grounds its reasoning here before you build Neo4j in Phase 2.

**`agent_prompts/*.md`** — One versioned prompt file per agent, kept out of code so you can iterate without redeploying. Each includes: role definition, required output JSON schema, few-shot examples, and explicit instructions to cite evidence (article IDs, analogue IDs, signal values).

---

### `src/geopulse/functions/` (Azure Functions entry points)

**`function_app.py`** — The thin Azure adapter layer; all real logic stays in the importable packages below so it remains unit-testable and portable. Defines: timer triggers (`@app.timer_trigger`) that call the GDELT collector every 15 min, RSS every 5 min, Reddit/prediction markets every 15 min, market data hourly; a detection function that runs the anomaly check after each ingest and drops an `AnomalySignal` message on the `anomaly-events` queue when the ≥2-source composite trigger fires; and (MVP option) a queue-trigger function that runs the LangGraph pipeline directly, before Container Apps exists. ~15K executions/month against the 1M free grant.

**`host.json`** — Functions host config: queue batch size 1 (one anomaly = one pipeline run), retry policy with exponential backoff, Application Insights sampling settings.

**`local.settings.json.example`** — Local dev template for `func start` (Azurite connection strings, dev Cosmos emulator endpoint).

---

### `src/geopulse/ingestion/`

**`base_collector.py`** — Abstract `Collector` class: `fetch() -> list[RawRecord]`, retry/backoff decorator, rate-limit tracking, standard `RawRecord` dataclass (source, url, timestamp, text, metadata), and a `to_db()` persistence hook. All collectors inherit from this.

**`gdelt_collector.py`** — Poll the GDELT DOC 2.0 API (and/or download 15-min event CSVs). Implement: query builder for themes/locations/CAMEO codes, parsing of the event and GKG formats, tone extraction, and article-count time series per theme (feeds the anomaly detector). Handle GDELT's quirks: dedupe URLs, filter low-credibility domains via a configurable blocklist.

**`rss_collector.py`** — `feedparser`-based polling of a configurable feed list (Reuters, AP, Al Jazeera, FT headlines, EIA/IEA/OPEC press pages). Normalize into `RawRecord`. Cheap, legal, reliable — your MVP's second news leg.

**`reddit_collector.py`** — PRAW-based streaming of configured subreddits (r/geopolitics, r/wallstreetbets, r/stocks). Capture post/comment volume per hour (for anomaly detection) and text (for sentiment). Respect the ~60 req/min practical limit; include a `dry_run` mode with cached fixtures.

**`prediction_market_collector.py`** — Poll Polymarket's read API (no auth) and optionally Kalshi for markets matching event keywords ("Hormuz", "Korea", "recession"). Extract probability time series; a >10-point jump in an hour is an event-confirmation signal.

**`acled_collector.py`** — Authenticated ACLED API client: fetch conflict/protest events by region and date, handle pagination (5,000-row default), map to internal schema. Phase 2.

**`ais_collector.py`** — WebSocket client for AISstream.io scoped to chokepoint bounding boxes (Hormuz, Suez, Malacca). Compute vessel-count and dwell-time baselines; a sharp transit-count drop is a physical confirmation of closure. Phase 2/3.

**`market_data_collector.py`** — yfinance (MVP) / Polygon (later) wrapper fetching OHLCV for all ETF proxies in `sector_taxonomy.yaml`, plus VIX, Brent/WTI futures proxies, DXY, USDJPY, GLD. Provides both live snapshots and historical windows for event studies.

---

### `src/geopulse/detection/`

**`anomaly_detector.py`** — Rolling z-score / EWMA burst detection on time series (GDELT article counts per theme, Reddit post volume, prediction-market prob changes). Emits `AnomalySignal(theme, score, sources, window)` when thresholds are crossed. Composite trigger logic: require ≥2 independent source types to fire before invoking the (expensive) agent pipeline.

**`event_clusterer.py`** — Group related articles into one "event" via embedding similarity + hierarchical clustering (or a simpler TF-IDF + time-window approach for MVP). Prevents 40 articles about the same strike from becoming 40 pipeline runs.

**`dedupe.py`** — URL canonicalization, near-duplicate text detection (MinHash or embedding cosine threshold), circular-reporting collapse (many outlets citing one Reuters wire = one source, not twenty).

---

### `src/geopulse/agents/`

**`state.py`** — The typed LangGraph state: a Pydantic/TypedDict model carrying `event: ClassifiedEvent`, `analogies: list[HistoricalAnalogy]`, `transmission_chains: list[TransmissionChain]`, `sentiment: SentimentReport`, `quant_signals: QuantSnapshot`, `contrarian_case: ContrarianReport`, `verdict: SectorVerdict | None`, plus `evidence_log` (every claim → source ID) and `token_spend`. This file is the contract between all agents — write it first.

**`graph.py`** — LangGraph graph assembly: nodes for each agent, edges defining flow (classifier → [analogy, transmission, sentiment, quant in parallel] → contrarian → synthesis), conditional edges (skip analogy agent if corpus has no match above similarity threshold), a human-in-the-loop `interrupt()` before high-severity alerts publish, checkpointing config, and per-run token budget enforcement.

**`event_classifier_agent.py`** — Takes clustered raw articles → outputs `ClassifiedEvent` (taxonomy category, actors, locations, affected commodities, severity 1–5, confidence). Validates output against `event_taxonomy.yaml`; retries with error feedback on schema violations.

**`historical_analogy_agent.py`** — Embeds the classified event, queries the RAG retriever over the event corpus, and for each retrieved analogue pulls its stored measured sector CARs. Outputs ranked `HistoricalAnalogy` objects with similarity scores and the key disanalogy warnings ("Abqaiq unwound in 2 weeks because supply was restored — check whether this closure is sustained").

**`transmission_agent.py`** — The signature agent. Given the event + `transmission_channels.yaml` (Phase 1) or the Neo4j causal graph (Phase 2), walks event → commodity → supply chain → sector chains and outputs explicit `TransmissionChain` objects: `[hormuz_closure] → [brent +X%] → [jet fuel cost] → [airlines margin compression] → JETS: LOSER, magnitude=high`. Every hop must cite either a graph edge or a retrieved source.

**`sentiment_agent.py`** — Scores news tone + social chatter per affected sector using a cheap model (or FinBERT locally). Outputs per-sector sentiment with volume context. Deliberately low-weight in synthesis — it's a confirmation signal, not a driver.

**`quant_signals_agent.py`** — Pulls the live `QuantSnapshot` from `signals/` modules and interprets it: "VIX +38%, Brent futures in steep backwardation, VLCC rates +60% — market is pricing sustained disruption, consistent with the transmission thesis." Flags divergences (thesis says panic, market is calm → lower confidence).

**`contrarian_agent.py`** — Receives the draft consensus and must argue the opposite: cite the strongest disconfirming analogue, question severity classification, identify which chains break if the event resolves quickly. Outputs `ContrarianReport` with a `materiality` score; if high, the synthesis agent must address each point explicitly and confidence is discounted.

**`synthesis_agent.py`** — Reconciles everything into the final `SectorVerdict`: ranked winners/losers, per-call confidence (anchored to historical analogue hit rates, discounted by contrarian materiality and quant divergence), and the cited narrative. Enforces the output schema in `verdict_schema.py` strictly.

---

### `src/geopulse/knowledge/`

**`causal_graph.py`** — Neo4j (or NetworkX for a lighter start) interface: node types (Event, Commodity, SupplyChain, Sector, Company), edge types (disrupts, raises_price_of, is_input_to, benefits, harms) with mechanism annotations. Query methods: `chains_from_event(event_type) -> list[Path]`.

**`graph_builder.py`** — Populates the graph: loads `transmission_channels.yaml` as seed edges, then optionally runs LLM-assisted extraction over a curated corpus of analyst reports to propose new edges (all human-reviewed before insertion — no auto-committed LLM edges).

**`event_corpus/corpus_schema.py`** — Pydantic schema for a curated event study: event metadata, timeline, per-sector measured CARs over [-1,+1], [-5,+5], [-10,+10] windows, narrative of what happened, what reversed and why, data sources.

**`event_corpus/loader.py`** — Loads/validates seed YAML files, computes embeddings of event descriptions, upserts into the vector store.

**`event_corpus/seed_events/*.yaml`** — The moat. Each file is a hand-curated event study. Start with 8–12: Abqaiq 2019, Kuwait 1990, Russia-Ukraine 2022, COVID crash 2020, 1973 embargo, Suez blockage 2021, Fukushima 2011, 9/11, GFC 2008, dot-com 2000. Populate the CAR figures from your own `event_study.py` runs so numbers are consistent and reproducible.

**`rag/embedder.py`** — Embedding wrapper (OpenAI/Voyage/local sentence-transformers behind one interface).

**`rag/retriever.py`** — Similarity search + metadata filtering (event category, region), returns analogues above threshold with scores.

**`rag/vector_store.py`** — Delegates to `storage/store.py`'s vector methods: Cosmos native vector search on the free-tier path, pgvector on the Postgres path, with Azure AI Search (free F tier: 50 MB, 3 indexes — enough for the whole curated corpus) as the Phase-2 hybrid-search upgrade. Agents never know which backend is live.

---

### `src/geopulse/signals/`

**`volatility.py`** — VIX level + percentile rank + rate of change; per-sector implied vol if you add an options data source later.

**`commodities.py`** — Brent/WTI spot and futures-curve shape (backwardation depth = market's persistence estimate), gold, natural gas (TTF/HH proxies).

**`freight.py`** — Baltic Dry Index and tanker-rate proxies (via ETF proxies like BDRY or scraped indices in MVP; paid feed later).

**`credit_fx.py`** — HYG/LQD spread proxies, EMB for EM stress, DXY, USDJPY, USDCHF safe-haven flow measures.

**`risk_indices.py`** — Fetchers for the Caldara-Iacoviello GPR index and EPU index (both downloadable as CSVs from their official sites); compute current-vs-historical percentile.

---

### `src/geopulse/analysis/`

**`event_study.py`** — Classic event-study engine: given an event date and ticker list, estimate the market model on a pre-event window, compute AR/CAR/CAAR over configurable event windows, with t-stats. Used both to build the seed corpus and to score live predictions after the fact.

**`abnormal_returns.py`** — The return math: market-model regression, mean-adjusted fallback, CAR aggregation, BMP/Boehmer standardized tests.

**`sector_mapping.py`** — Utilities mapping tickers ↔ sectors ↔ ETF proxies from `sector_taxonomy.yaml`; resolves the agents' sector names to backtestable instruments.

---

### `src/geopulse/evaluation/`

**`backtester.py`** — Replay harness: feed a historical event's news (as-of data only — enforce no-lookahead) through the full agent pipeline, capture the verdict, then score it against realized post-event CARs via `event_study.py`. Batch mode over the whole corpus.

**`metrics.py`** — Directional hit rate per sector and overall, Brier score, Brier skill score vs. a naive baseline ("energy up, everything else down" for oil shocks; beta-sorted defensive/cyclical for crashes), mean lead time vs. first market reaction, and cost metrics (tokens/latency per verdict).

**`calibration.py`** — Reliability curves (predicted confidence vs. realized frequency), isotonic/Platt recalibration fitted on backtest results, applied by the synthesis agent at inference time.

---

### `src/geopulse/outputs/`

**`verdict_schema.py`** — The canonical `SectorVerdict` Pydantic model: event summary, per-sector calls `{sector, direction, magnitude, confidence, transmission_chain, evidence_citations}`, contrarian flags, timestamp, model/prompt versions (for reproducibility).

**`report_generator.py`** — Renders a verdict into (a) a Markdown/HTML analyst brief with the full cited narrative and (b) a compact JSON payload for the dashboard/API. Jinja2 templates.

**`alerting.py`** — Severity-gated notification dispatch (Slack webhook/email); high-severity alerts require the human-in-the-loop approval flag from the LangGraph interrupt before sending. Phase 3.

---

### `src/geopulse/storage/`

**`store.py`** — The abstract `Store` interface every other module talks to: `save_record`, `save_verdict`, `get_event`, `vector_upsert`, `vector_search`, `list_verdicts`. Nothing outside this package imports a database client directly — that's what makes the Cosmos↔Postgres swap a one-line config change.

**`cosmos_store.py`** — [P1] The free-tier default implementation: containers `raw_records`, `events`, `verdicts`, `corpus` (partition keys chosen per access pattern, e.g. `/event_id` for verdicts), Cosmos's native vector indexing for embeddings (so RAG needs no separate vector DB), and RU-budget awareness — batch writes and keep provisioned throughput at the shared 1000 RU/s cap so the account never bills.

**`blob_store.py`** — Raw article HTML/JSON archive and rendered report briefs in Blob containers; Cosmos holds metadata + pointers, blobs hold bulk text (keeps you well under the 25 GB Cosmos cap).

**`queue_bus.py`** — [P1] Thin Storage Queues wrapper: `publish_anomaly()`, `receive()`, poison-queue handling. Same narrow interface the Phase-3 `streaming/` package reimplements over Event Hubs — upgrading the message bus later means changing which implementation `settings.py` selects.

**`models.py`** — Pydantic domain models (`RawRecord`, `ClassifiedEvent`, `AnomalySignal`, `SectorVerdict` rows, `BacktestRun`) shared by both store implementations. Every verdict stores full input lineage for auditability.

**`db.py` / `migrations/`** — The Postgres + pgvector alternative implementation of `store.py` (SQLAlchemy + Alembic), for teams that prefer SQL or already run Postgres. Not needed on the free-tier path.

---

### `src/geopulse/streaming/` (Phase 3 — Event Hubs upgrade)

Not needed on the free-tier path — Storage Queues via `storage/queue_bus.py` carry MVP volume for pennies. This package exists for when event volume justifies true streaming (~$11+/month for Event Hubs Basic).

**`topics.py`** — Topic/event-hub definitions and JSON schemas (`raw.news`, `signals.anomalies`, `verdicts.published`).
**`producers.py` / `consumers.py`** — Event Hubs clients (Kafka-protocol compatible, so Confluent/Redpanda remain drop-in alternatives) implementing the same bus interface as `queue_bus.py`; consumer group that triggers the agent graph on anomaly messages.

---

### `app/` (Streamlit dashboard)

**`dashboard.py`** — Entry point, nav, global filters (date, event category).
**`pages/2_sector_verdicts.py`** — [P1] The money page: latest verdict table (sector, direction, confidence), expandable transmission chains, contrarian panel, evidence links.
**`pages/1_live_events.py`** — Anomaly feed and event stream.
**`pages/3_historical_analogies.py`** — Browse the event corpus, view measured CARs per analogue.
**`pages/4_backtest_results.py`** — Hit rates, calibration curves, Brier scores by event category.
**`components/transmission_chain_viz.py`** — Renders a chain as a left-to-right graph (graphviz/plotly) — this visual is your demo's centerpiece.

---

### `scripts/`

**`run_pipeline.py`** — [P1] One-shot CLI: `--query "strait of hormuz"` or `--from-anomaly latest`; runs collectors → detection → agent graph → prints/saves verdict. Your primary dev loop.
**`replay_historical_event.py`** — [P1] Runs the pipeline against a seed event's archived news with an as-of cutoff. This is how you demo *and* validate before any live data plumbing exists.
**`seed_event_corpus.py`** — Runs event studies for each seed YAML, fills in CARs, embeds, loads vector store.
**`run_backtest.py`** — Full corpus backtest → metrics report → updated calibration model.

---

### `tests/`

- **`test_ingestion/`** — Collectors against recorded fixtures (no live API calls in CI); rate-limit/backoff behavior.
- **`test_agents/`** — Schema validity of each agent's output on fixture inputs; graph routing logic (conditional edges, interrupt firing); token-budget enforcement. Use a mocked LLM for determinism plus a small set of live "golden" tests run manually.
- **`test_analysis/`** — Event-study math against hand-computed known results (e.g., verify Abqaiq XLE CAR matches published figures within tolerance).
- **`fixtures/`** — Frozen GDELT samples, sample verdicts, canned market data.

---

## Suggested build order (maps to the phased roadmap)

1. `state.py` → `verdict_schema.py` → taxonomy/config YAMLs (the contracts)
2. `market_data_collector.py` + `event_study.py` + `abnormal_returns.py` (validate the math on Abqaiq — all local, $0)
3. `storage/store.py` + `cosmos_store.py` + `queue_bus.py` (local dev against the free Cosmos emulator + Azurite)
4. `gdelt_collector.py` + `rss_collector.py` + `dedupe.py` + `anomaly_detector.py`, wired into `functions/function_app.py` and run locally with `func start`
5. `event_classifier_agent.py` → `transmission_agent.py` → `synthesis_agent.py` + `graph.py` (3-agent MVP — prompt-develop against GitHub Models' free tier, then point at Azure OpenAI)
6. `replay_historical_event.py` + `metrics.py` — prove the MVP beats the naive baseline
7. `infra/main.bicep` + free-tier modules + `deploy.yml` — first cloud deployment (budget alert included)
8. Everything else (analogy RAG, contrarian, quant/sentiment agents, dashboard pages, Event Hubs streaming) per Phase 2/3.

## Free-tier cost guardrails (bake these into the code, not just the docs)

- Cosmos: `enableFreeTier` at creation, shared 1000 RU/s cap, one free account per subscription.
- Functions: composite anomaly trigger (≥2 source types) is the cost gate — it's what keeps LLM invocations rare.
- LLM: per-run token budget enforced in `graph.py`; mini models for classifier/sentiment; Batch API (50% discount) for backtests.
- `monitoring.bicep` budget alert on day one — Azure has no automatic spend cap.
