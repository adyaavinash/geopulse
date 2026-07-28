# quant_signals prompt (versioned; edit without redeploying)

The **Quantitative Signals Agent** ("Data") does not call an LLM — its
workflow ("pull live signals -> compare to thesis -> mark confirm/contradict")
is a numeric comparison against a directional prior, not a reasoning task.
This file exists for documentation parity with the other spokes and to record
the decision rule the deterministic code in `quant_signals_agent.py`
implements, so a reviewer doesn't have to read code to understand the logic.

## Decision rule

For each sector the Transmission Reasoner identified:

1. Look up its ETF proxy and expected move direction on a negative shock
   (`SECTOR_ETF_MAP` — mirrors `config/sector_taxonomy.yaml`'s beta priors).
2. Compare the ETF's actual recent % move (live snapshot, falling back to the
   most recently stored price series) against that expectation.
3. Classify:
   - moved in the expected direction beyond the noise threshold -> `confirm`
   - moved against the expected direction beyond that threshold -> `contradict`
   - too small a move to read either way, or no data -> `neutral`

VIX level/move is reported alongside the per-sector calls as risk-appetite
context, not scored against a per-sector expectation itself.

## Why no LLM

A directional prior is either right or wrong given the data — there is no
ambiguity an LLM's judgment would resolve better than the arithmetic already
does, and keeping this spoke deterministic means it never depends on a model
backend being available.
