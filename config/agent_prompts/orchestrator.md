# orchestrator prompt (versioned; edit without redeploying)

The **Orchestrator** does not call an LLM directly — its two jobs (event
classification and draft-verdict synthesis) are both deterministic
reconciliation over evidence the spoke agents already produced (each of
which did its own LLM reasoning where warranted). This file documents that
logic for reviewers, mirroring the other agents' prompt files.

## Classification (absorbs v1's separate classifier agent)

`theme -> category/severity` is a taxonomy lookup against
`config/event_taxonomy.yaml`, not something an LLM call improves on.

## Dispatch plan

Analogy -> Transmission -> (if the graph produced any chains) Sentiment and
Quant Signals, each logged to `state.plan` as it's dispatched, for audit.
Transmission's graph-derived sectors are what Sentiment/Quant Signals score
against — a sector with no cited transmission chain gets no verdict call,
per the project's evidence-citation rule.

## Draft-verdict synthesis (absorbs v1's synthesis agent)

For each transmission chain: start from its calibrated confidence, nudge it
up/down based on whether Sentiment and Quant Signals confirm or contradict
that sector, and cite the transmission edge (plus any analogies whose
measured returns cover that sector's ETF). This produces the `DraftVerdict`
the maker-checker gate (`maker_checker.md`) then stress-tests.

## Maker-checker loop

`approve` -> publish. `escalate` -> pause for a human. `revise` -> the
orchestrator re-plans with a bounded retry (a deterministic confidence
haircut today; a full LLM re-synthesis pass informed by the checker's
specific objections is future work) before re-submitting, capped at
`maker_checker.MAX_RETRIES` before it is forced to `escalate`.
