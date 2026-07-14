"""L2 hub — Person 2's first deliverable.

Whiteboard contract: consume AnomalySignal -> classify -> plan -> dispatch
spokes (Analogy | Transmission | Sentiment | Quant) -> synthesize draft
verdict -> maker_checker -> report_tool. Log the plan to state for audit.
"""
from __future__ import annotations


def build_graph(settings, store):
    """Return an object with .invoke(inputs, config) -> final_state.
    Implement on LangGraph (supervisor pattern) or as a plain async
    controller. L1's queue trigger already calls this signature."""
    raise NotImplementedError(
        "L2 orchestrator not implemented yet — Person 2 starts here. "
        "The L1->L2 contract is tests/fixtures/anomaly_signal.json."
    )
