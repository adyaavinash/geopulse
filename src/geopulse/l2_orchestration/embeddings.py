"""Text embeddings for the Analogy agent's retrieval — with an offline fallback.

Same philosophy as ``llm.py``: real Azure OpenAI embeddings when configured,
otherwise a deterministic **hashing vectorizer** that needs no network. The
offline embedder is always available (retrieval must work with zero cloud
setup), and because it is a bag-of-hashed-tokens model, events that share
category / commodity / region vocabulary land near each other — good enough to
demonstrate and test the RAG loop. Azure embeddings simply raise the ceiling.

Configure the online path via:
    AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, AZURE_OPENAI_API_VERSION
    GEOPULSE_EMBED_DEPLOYMENT   (e.g. "text-embedding-3-small")
"""

from __future__ import annotations

import hashlib
import os
import re
from functools import lru_cache

import numpy as np

_HASH_DIM = 512
_TOKEN_RE = re.compile(r"[a-z0-9]+")


class Embedder:
    def __init__(self, dim: int = _HASH_DIM) -> None:
        self.dim = dim
        self._endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "")
        self._api_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
        self._api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-06-01")
        self._deployment = os.environ.get("GEOPULSE_EMBED_DEPLOYMENT", "")
        self._client = None

    @property
    def online(self) -> bool:
        return bool(self._endpoint and self._api_key and self._deployment)

    @property
    def mode(self) -> str:
        return "azure" if self.online else "hashing"

    def embed(self, texts: list[str]) -> np.ndarray:
        """Return an (n, d) float32 matrix of L2-normalized row vectors."""
        if self.online:
            try:
                return self._embed_azure(texts)
            except Exception:  # pragma: no cover - network/config failure
                pass  # fall through to the deterministic embedder
        return self._embed_hashing(texts)

    def embed_one(self, text: str) -> np.ndarray:
        return self.embed([text])[0]

    # ------------------------------------------------------------------ #
    # offline: hashing vectorizer (bag of hashed tokens, tf-weighted)
    # ------------------------------------------------------------------ #
    def _embed_hashing(self, texts: list[str]) -> np.ndarray:
        mat = np.zeros((len(texts), self.dim), dtype=np.float32)
        for r, text in enumerate(texts):
            for tok in _TOKEN_RE.findall((text or "").lower()):
                h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
                idx = h % self.dim
                sign = 1.0 if (h >> 8) & 1 else -1.0  # signed hashing reduces collisions
                mat[r, idx] += sign
        return _l2_normalize(mat)

    # ------------------------------------------------------------------ #
    # online: Azure OpenAI embeddings
    # ------------------------------------------------------------------ #
    def _embed_azure(self, texts: list[str]) -> np.ndarray:
        if self._client is None:
            from langchain_openai import AzureOpenAIEmbeddings  # lazy: optional l2 extra

            self._client = AzureOpenAIEmbeddings(
                azure_endpoint=self._endpoint,
                api_key=self._api_key,
                api_version=self._api_version,
                azure_deployment=self._deployment,
            )
        vecs = np.asarray(self._client.embed_documents(list(texts)), dtype=np.float32)
        return _l2_normalize(vecs)


def _l2_normalize(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    return Embedder()
