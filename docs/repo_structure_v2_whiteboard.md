# GeoPulse Repository Structure — v2 (whiteboard restructure)

Restructured around the team whiteboard: three numbered layers, an **orchestrator-centric** agent design (hub-and-spoke, not a fixed linear graph), **Postgres + pgvector** as the single store (replacing the Cosmos-first design), a **maker-checker** validation gate in place of the separate contrarian agent + human-review pair, and a **report tool** the orchestrator invokes to publish. Layer ownership matches the four-person split: L1 = Person 1, L2 backbone + upstream agents = Person 2, L2 downstream agents + verdict = Person 3, Postgres/corpus/dashboard = Person 4.

```
geopulse/
├── README.md
├── pyproject.toml
├── .env.example
├── docker-compose.yml               (postgres+pgvector, azurite)
├── Makefile
│
├── .github/workflows/deploy.yml
│
├── infra/
│   ├── main.bicep
│   ├── modules/
│   │   ├── functions.bicep          (L1 runtime)
│   │   ├── postgres.bicep           (Flexible Server B1ms + pgvector)
│   │   ├── storage.bicep            (queue + blob)
│   │   ├── container_app.bicep      (L2 runtime)
│   │   ├── openai.bicep
│   │   └── monitoring.bicep
│   └── parameters/
│       ├── free-tier.bicepparam
│       └── production.bicepparam
│
├── config/
│   ├── settings.py
│   ├── event_taxonomy.yaml
│   ├── sector_taxonomy.yaml
│   ├── transmission_channels.yaml   (graph seed: Regs → cause → effect chains)
│   └── agent_prompts/
│       ├── orchestrator.md
│       ├── analogy.md
│       ├── transmission_reasoner.md
│       ├── sentiment.md
│       ├── quant_signals.md
│       ├── maker_checker.md
│       └── report.md
│
├── src/geopulse/
│   ├── __init__.py
│   │
│   ├── l1_ingestion_detection/      ◄ Person 1 (built & smoke-tested)
│   │   ├── __init__.py
│   │   ├── functions/
│   │   │   ├── function_app.py
│   │   │   └── host.json
│   │   ├── collectors/
│   │   │   ├── base_collector.py
│   │   │   ├── rss_collector.py
│   │   │   ├── gdelt_collector.py
│   │   │   └── social_market_collectors.py
│   │   ├── detection/
│   │   │   ├── dedupe.py
│   │   │   └── anomaly_detector.py
│   │   └── run_local.py
│   │
│   ├── l2_orchestration/            ◄ Persons 2 & 3
│   │   ├── __init__.py
│   │   ├── orchestrator.py          ★ the hub
│   │   ├── state.py
│   │   ├── consumer.py              (queue → orchestrator entry point)
│   │   ├── agents/
│   │   │   ├── base_agent.py
│   │   │   ├── analogy_agent.py         (Person 2 — agentic RAG)
│   │   │   ├── transmission_reasoner.py (Person 2 — causal graph walk)
│   │   │   ├── sentiment_agent.py       (Person 3 — public sentiment)
│   │   │   ├── quant_signals_agent.py   (Person 3 — market data)
│   │   │   └── maker_checker.py         (Person 3 — validation gate)
│   │   ├── tools/
│   │   │   ├── report_tool.py           (Person 3 — renders + publishes)
│   │   │   ├── graph_tool.py            (transmission graph queries)
│   │   │   └── retrieval_tool.py        (pgvector similarity search)
│   │   └── llm.py                   (Azure OpenAI wiring, model tiers, budgets)
│   │
│   ├── knowledge/                   ◄ Person 4
│   │   ├── event_corpus/
│   │   │   ├── corpus_schema.py
│   │   │   ├── loader.py
│   │   │   └── seed_events/*.yaml
│   │   └── causal_graph.py          (loads transmission_channels.yaml → NetworkX)
│   │
│   ├── analysis/                    ◄ Person 4 (+ Person 1 for event studies)
│   │   ├── event_study.py
│   │   ├── abnormal_returns.py
│   │   └── sector_mapping.py
│   │
│   ├── evaluation/                  ◄ Person 4
│   │   ├── backtester.py
│   │   ├── metrics.py
│   │   └── calibration.py
│   │
│   ├── outputs/
│   │   ├── verdict_schema.py        (Person 3 owns — the L2→L3 contract)
│   │   └── alerting.py
│   │
│   └── storage/                     ◄ Person 4
│       ├── store.py                 (interface — unchanged from v1)
│       ├── pg_store.py              ★ Postgres + pgvector (now the default)
│       ├── sqlite_store.py          (local dev fallback, already written)
│       ├── blob_store.py
│       ├── queue_bus.py
│       ├── models.py
│       └── migrations/              (Alembic)
│
├── l3_dashboard/                    ◄ Person 4
│   ├── dashboard.py
│   ├── pages/
│   │   ├── 1_live_events.py
│   │   ├── 2_sector_verdicts.py
│   │   ├── 3_analogies_corpus.py
│   │   └── 4_backtests.py
│   └── components/
│       ├── verdict_table.py
│       └── transmission_chain_viz.py
│
├── scripts/
│   ├── run_pipeline.py
│   ├── replay_historical_event.py
│   ├── seed_event_corpus.py
│   └── run_backtest.py
│
└── tests/
    ├── test_l1/                     (smoke test from Person 1, formalized)
    ├── test_l2/
    ├── test_analysis/
    └── fixtures/
        ├── anomaly_signal.json      (frozen L1→L2 contract)
        └── sector_verdict.json      (frozen L2→L3 contract)
```

---

## What changed vs. v1, and what to implement

### 1. Orchestrator hub-and-spoke replaces the fixed linear graph

The whiteboard's biggest decision. In v1, LangGraph edges hardcoded the flow (classifier → parallel agents → contrarian → synthesis). In v2, **`orchestrator.py`** is the hub that decides, per event, which agents to invoke, in what order, and whether to loop.

**`orchestrator.py`** — Still implementable *on* LangGraph (a supervisor node with conditional edges back to itself), or as a plain async controller if Person 2 prefers less framework. Responsibilities: consume the `AnomalySignal`, do the event classification itself (absorbing v1's separate classifier agent — the whiteboard has no classifier node), plan the agent sequence, dispatch (Analogy ∥ Transmission ∥ Sentiment ∥ Quant in parallel), synthesize the draft verdict (absorbing v1's synthesis agent), submit the draft to the maker-checker, and on approval invoke the report tool. Enforces the per-run token budget and writes every intermediate state to Postgres for lineage.

**`state.py`** — Same typed shared state as v1 (this contract survives the restructure), minus `contrarian_case`, plus `checker_review: CheckerReview | None` and `plan: list[AgentCall]` (the orchestrator's chosen sequence — logged for auditability, since a dynamic hub is harder to debug than a static graph).

**`consumer.py`** — The L1→L2 seam: KEDA-scaled queue consumer (or MVP queue-trigger Function) that deserializes `AnomalySignal` (the frozen fixture) and hands it to the orchestrator.

### 2. The four spoke agents

**`agents/base_agent.py`** — Common contract: `run(state) -> StateDelta`, prompt loading from `config/agent_prompts/`, model-tier selection via `llm.py`, mandatory evidence citation in outputs.

**`agents/analogy_agent.py`** — The board note "Agentic RAG — til when?" is the open design question: instead of one-shot retrieval, the agent iterates — retrieve analogues → assess sufficiency → reformulate query → retrieve again — until confident or budget-capped. Answer to "til when?": a hard cap (e.g., 3 retrieval rounds or N tokens, whichever first) enforced by the orchestrator, plus a sufficiency self-check ("do retrieved analogues cover this event's category AND region?"). Uses `tools/retrieval_tool.py` against pgvector.

**`agents/transmission_reasoner.py`** — The board's "graph → Regs → cause → etc" note: walks the causal graph loaded from `transmission_channels.yaml` (event → regulation/sanction/commodity → cause → sector effect), via `tools/graph_tool.py`. Every hop cites a graph edge or retrieved source; output is the `TransmissionChain` list.

**`agents/sentiment_agent.py`** — "Public" sentiment: news tone (already in L1's series) + Reddit chatter per affected sector. Cheap model tier.

**`agents/quant_signals_agent.py`** — "Data": pulls the live market snapshot (VIX, futures/ETF proxies, FX, freight) through the store, interprets confirmation/divergence vs. the draft thesis.

### 3. Maker-checker replaces contrarian + human gate

A finance-native control pattern, and honestly a better fit for the audience than "contrarian agent":

**`agents/maker_checker.py`** — The orchestrator (maker) submits the draft verdict; the checker — running on a *different* model deployment with an adversarial prompt — must independently verify: every sector call has a cited transmission chain, the analogues actually support the direction claimed, quant signals don't contradict the narrative, and confidence isn't higher than the evidence warrants. Returns `approve | revise(reasons) | escalate`. On `revise`, the orchestrator re-plans (bounded retries: 2); on `escalate` — high severity or unresolved disagreement — it pauses for a human, which is where v1's `interrupt()` behavior lives now. The checker's objections are stored and surfaced in the report (this preserves v1's "consensus vs. contrarian" novelty — rebranded as maker-checker, it's also a cleaner enterprise pitch line: segregation of duties for AI decisions).

### 4. Report tool replaces the synthesis agent's output half

**`tools/report_tool.py`** — Invoked by the orchestrator only after checker approval: renders the `SectorVerdict` into the Markdown/HTML analyst brief (Jinja2), writes it to Blob, persists the verdict row + full lineage to Postgres, and fires `outputs/alerting.py`. Deliberately a *tool*, not an agent — no LLM creativity in the publishing step.

### 5. Postgres is back (green circle wins)

**`storage/pg_store.py`** — Implements the same `store.py` interface Person 1 already codes against (his SQLite stub remains the local-dev backend — nothing in L1 changes). Tables: `raw_records`, `series`, `spikes`, `signals`, `agent_runs`, `verdicts`, `corpus_embeddings` (pgvector column, cosine index). Alembic migrations in `migrations/`.

**`infra/modules/postgres.bicep`** — Flexible Server B1ms with the pgvector extension allow-listed. Cost note (the one thing lost vs. Cosmos): free for 12 months on a new account, ~$13–15/month after — the whiteboard traded Cosmos's forever-free tier for SQL familiarity + one engine for relational *and* vector. Fair trade for a 4-person team; the interface keeps a path back if anyone regrets it.

### 6. L1 and L3 — minimal change

**L1** is Person 1's existing, smoke-tested package moved under `l1_ingestion_detection/` with collectors and detection grouped — imports change, logic doesn't. The `AnomalySignal` fixture stays the frozen contract.

**L3** is v1's Streamlit app renamed to match the board's layer numbering. The verdict page renders `verdict_schema.py` — including the checker's objections panel — and the dashboard's "approve" action is what resumes an `escalate`d run.

---

## Updated contracts (freeze these three, in this order)

1. **`AnomalySignal`** (L1 → orchestrator) — already frozen, fixture checked in. Unchanged.
2. **`state.py` + `AgentCall`/`StateDelta`** (orchestrator ↔ agents) — Person 2 drafts, Person 3 co-signs, since their agents plug into it.
3. **`SectorVerdict` + `CheckerReview`** (L2 → L3) — Person 3 drafts, Person 4 co-signs, since the dashboard renders it.

## Build order deltas

Person 1: done — just move files and update imports. Person 2: `orchestrator.py` + `state.py` + `llm.py` + the two upstream agents; stub the checker as auto-approve until Person 3 lands. Person 3: `verdict_schema.py` first (Person 4 is blocked on it), then quant/sentiment agents, then `maker_checker.py` + `report_tool.py`. Person 4: `pg_store.py` + migrations first (everyone is blocked on it in prod), then corpus seeding, then dashboard, then backtester.
