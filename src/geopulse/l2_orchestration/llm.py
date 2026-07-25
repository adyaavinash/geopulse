"""Azure OpenAI wiring — model tiers + budgets, with an offline fallback.

Every agent shares this. Two design points:

* **Tiers.** Agents ask for a *tier* ("cheap" / "reasoning" / "checker"), not a
  model name, so deployments can be swapped per-environment via env vars. The
  maker-checker deliberately runs on a *different* deployment (segregation of
  duties), which is why "checker" is its own tier.
* **Offline fallback.** No Azure creds locally, so ``available`` is False unless
  the env is configured. Callers must check ``available`` and degrade
  gracefully (the Transmission Reasoner falls back to a template narrative over
  the graph skeleton). This keeps the whole L2 slice runnable and testable with
  no cloud dependency; real Azure kicks in the moment the env vars are set.

Configure via environment:
    AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_API_VERSION
    GEOPULSE_LLM_DEPLOYMENT_CHEAP / _REASONING / _CHECKER   (deployment names)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal, Protocol

Tier = Literal["cheap", "reasoning", "checker"]

_DEFAULT_API_VERSION = "2024-06-01"


@dataclass
class LLMResponse:
    text: str
    model: str = ""
    tokens: int = 0
    offline: bool = False


class LLM(Protocol):
    """The surface agents depend on (real client or a test stub)."""

    @property
    def available(self) -> bool: ...

    def complete(
        self, prompt: str, *, tier: Tier = "reasoning", system: str | None = None
    ) -> LLMResponse: ...


class LLMClient:
    """Real Azure OpenAI client. Imports langchain-openai lazily so the offline
    path has no hard dependency on the ``l2`` extra being installed."""

    def __init__(self) -> None:
        self._endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        self._api_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
        self._api_version = os.environ.get("AZURE_OPENAI_API_VERSION", _DEFAULT_API_VERSION)
        self._deployments: dict[str, str] = {
            "cheap": os.environ.get("GEOPULSE_LLM_DEPLOYMENT_CHEAP", ""),
            "reasoning": os.environ.get("GEOPULSE_LLM_DEPLOYMENT_REASONING", ""),
            "checker": os.environ.get("GEOPULSE_LLM_DEPLOYMENT_CHECKER", ""),
        }
        self._clients: dict[str, object] = {}

    @property
    def available(self) -> bool:
        return bool(self._endpoint and self._api_key and self._deployments["reasoning"])

    def _deployment(self, tier: Tier) -> str:
        # Fall back to the reasoning deployment if a tier is not separately set.
        return self._deployments.get(tier) or self._deployments["reasoning"]

    def _model_for(self, tier: Tier):
        deployment = self._deployment(tier)
        if deployment in self._clients:
            return self._clients[deployment]
        from langchain_openai import AzureChatOpenAI  # lazy: optional l2 extra

        model = AzureChatOpenAI(
            azure_endpoint=self._endpoint,
            api_key=self._api_key,
            api_version=self._api_version,
            azure_deployment=deployment,
            temperature=0.2,
        )
        self._clients[deployment] = model
        return model

    def complete(
        self, prompt: str, *, tier: Tier = "reasoning", system: str | None = None
    ) -> LLMResponse:
        if not self.available:
            return LLMResponse(text="", offline=True)
        model = self._model_for(tier)
        messages = []
        if system:
            messages.append(("system", system))
        messages.append(("human", prompt))
        result = model.invoke(messages)
        usage = getattr(result, "usage_metadata", None) or {}
        tokens = usage.get("total_tokens") or _estimate_tokens(prompt, result.content)
        return LLMResponse(
            text=result.content,
            model=self._deployment(tier),
            tokens=tokens,
        )


def _estimate_tokens(*texts: str) -> int:
    return sum(len(t) for t in texts if t) // 4  # ~4 chars/token heuristic


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    return LLMClient()
