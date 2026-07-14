"""Step 2 — Base collector: retry/backoff, rate-limit bookkeeping, dry_run.

The dry_run flag is the important design decision: with it, every collector
can run in CI from checked-in fixture files, and the whole detection loop is
testable without a single network call.
"""

from __future__ import annotations

import json
import logging
import random
import time
from abc import ABC, abstractmethod
from pathlib import Path

import httpx

from ..models import RawRecord
from ..settings import Settings

logger = logging.getLogger("geopulse.ingestion")


def with_retry(max_attempts: int = 4, base_delay: float = 1.0):
    """Exponential backoff with jitter. Retries transient HTTP/network errors;
    gives up immediately on 4xx (except 429)."""

    def decorator(fn):
        def wrapper(*args, **kwargs):
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except httpx.HTTPStatusError as e:
                    status = e.response.status_code
                    retryable = status == 429 or status >= 500
                    if not retryable or attempt == max_attempts:
                        raise
                except (httpx.TransportError, TimeoutError):
                    if attempt == max_attempts:
                        raise
                delay = base_delay * (2 ** (attempt - 1)) * (1 + random.random() * 0.3)
                logger.warning("%s attempt %d failed; retrying in %.1fs",
                               fn.__name__, attempt, delay)
                time.sleep(delay)
        return wrapper
    return decorator


class Collector(ABC):
    """All collectors: fetch() -> list[RawRecord], honoring dry_run."""

    name: str = "base"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = httpx.Client(timeout=20, follow_redirects=True,
                                   headers={"User-Agent": "geopulse/0.1"})
        self._last_call: float = 0.0
        self.min_seconds_between_calls: float = 1.0

    # -- rate limiting ---------------------------------------------------------

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self.min_seconds_between_calls:
            time.sleep(self.min_seconds_between_calls - elapsed)
        self._last_call = time.monotonic()

    # -- fixtures / dry-run ------------------------------------------------------

    def _fixture_path(self) -> Path:
        return Path(self.settings.fixtures_dir) / f"{self.name}.json"

    def _load_fixtures(self) -> list[RawRecord]:
        path = self._fixture_path()
        if not path.exists():
            logger.warning("dry_run: no fixture at %s", path)
            return []
        return [RawRecord(**r) for r in json.loads(path.read_text())]

    def save_fixtures(self, records: list[RawRecord]) -> None:
        """Dev helper: run once live, snapshot the result for CI."""
        self._fixture_path().parent.mkdir(parents=True, exist_ok=True)
        self._fixture_path().write_text(
            json.dumps([json.loads(r.model_dump_json()) for r in records], indent=2)
        )

    # -- public API ---------------------------------------------------------------

    def fetch(self) -> list[RawRecord]:
        if self.settings.dry_run:
            return self._load_fixtures()
        return self._fetch_live()

    @abstractmethod
    def _fetch_live(self) -> list[RawRecord]: ...
