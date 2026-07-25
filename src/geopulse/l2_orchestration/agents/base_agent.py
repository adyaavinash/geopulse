"""Common contract every spoke agent implements.

Per the whiteboard: ``run(state) -> StateDelta``, prompt loaded from
``config/agent_prompts/<name>.md`` (versioned; editable without a redeploy),
model-tier selection via ``llm.py``, and **mandatory evidence citation** in
outputs — an agent that cannot cite does not get to assert.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path

from geopulse.l2_orchestration.llm import LLM, Tier, get_llm_client
from geopulse.l2_orchestration.state import GraphState, StateDelta

_REPO_ROOT = Path(__file__).resolve().parents[4]
_PROMPT_DIR = _REPO_ROOT / "config" / "agent_prompts"


class BaseAgent(ABC):
    """Base for all L2 spoke agents.

    Subclasses set ``name`` (matches the prompt filename and the plan's
    AgentCall.agent) and ``tier`` (which model class the agent runs on), then
    implement :meth:`run`.
    """

    name: str = "base"
    tier: Tier = "reasoning"

    def __init__(self, llm: LLM | None = None) -> None:
        # Dependency-injected so tests can pass a deterministic stub.
        self.llm: LLM = llm or get_llm_client()

    @abstractmethod
    def run(self, state: GraphState) -> StateDelta:
        """Read the shared state, do the agent's work, return a partial update."""
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # shared helpers
    # ------------------------------------------------------------------ #
    def load_prompt(self) -> str:
        """The versioned prompt for this agent, from config/agent_prompts/."""
        return _read_prompt(self.name)


def _prompt_dir() -> Path:
    override = os.environ.get("GEOPULSE_CONFIG_DIR")
    return Path(override) / "agent_prompts" if override else _PROMPT_DIR


def _read_prompt(name: str) -> str:
    path = _prompt_dir() / f"{name}.md"
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()
