"""Step 0.5 — Local store stub.

Implements the same interface Person 4's CosmosStore will expose, so
nothing here blocks on them. Swap via settings.storage_backend.

Tables:
  records  — deduped RawRecords (evidence pointers for signals)
  series   — (series_key, bucket_ts, value) time-series the detector reads
  spikes   — individual threshold breaches (composite gate reads these)
  signals  — emitted AnomalySignals (cooldown reads these)
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from .models import AnomalySignal, RawRecord, Spike
from .settings import Settings


class SqliteStore:
    def __init__(self, settings: Settings):
        self.conn = sqlite3.connect(settings.sqlite_path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS records (
                id TEXT PRIMARY KEY, source TEXT, source_type TEXT,
                url TEXT, title TEXT, published_at TEXT, fetched_at TEXT,
                payload TEXT
            );
            CREATE TABLE IF NOT EXISTS series (
                series_key TEXT, bucket_ts TEXT, value REAL,
                PRIMARY KEY (series_key, bucket_ts)
            );
            CREATE TABLE IF NOT EXISTS spikes (
                theme TEXT, series_key TEXT, source_type TEXT,
                z_score REAL, observed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS signals (
                id TEXT PRIMARY KEY, theme TEXT, triggered_at TEXT, payload TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_spikes_theme ON spikes(theme, observed_at);
            """
        )
        self.conn.commit()

    # --- records -------------------------------------------------------------

    def save_records(self, records: list[RawRecord]) -> int:
        rows = [
            (r.id, r.source, r.source_type, r.url, r.title,
             r.published_at.isoformat() if r.published_at else None,
             r.fetched_at.isoformat(), r.model_dump_json())
            for r in records
        ]
        cur = self.conn.executemany(
            "INSERT OR IGNORE INTO records VALUES (?,?,?,?,?,?,?,?)", rows
        )
        self.conn.commit()
        return cur.rowcount

    def known_record_ids(self, ids: list[str]) -> set[str]:
        if not ids:
            return set()
        q = ",".join("?" * len(ids))
        rows = self.conn.execute(
            f"SELECT id FROM records WHERE id IN ({q})", ids
        ).fetchall()
        return {r[0] for r in rows}

    def recent_record_texts(self, since_minutes: int = 120) -> list[tuple[str, str]]:
        """(id, title+text) pairs for near-duplicate checking."""
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=since_minutes)).isoformat()
        rows = self.conn.execute(
            "SELECT id, COALESCE(title,'') || ' ' || COALESCE(json_extract(payload,'$.text'),'') "
            "FROM records WHERE fetched_at > ?", (cutoff,)
        ).fetchall()
        return [(r[0], r[1] or "") for r in rows]

    # --- time series -----------------------------------------------------------

    def add_series_point(self, series_key: str, bucket_ts: datetime, value: float) -> None:
        self.conn.execute(
            "INSERT INTO series VALUES (?,?,?) "
            "ON CONFLICT(series_key, bucket_ts) DO UPDATE SET value=excluded.value",
            (series_key, bucket_ts.isoformat(), value),
        )
        self.conn.commit()

    def get_series(self, series_key: str, since: datetime) -> list[tuple[datetime, float]]:
        rows = self.conn.execute(
            "SELECT bucket_ts, value FROM series WHERE series_key=? AND bucket_ts>=? "
            "ORDER BY bucket_ts", (series_key, since.isoformat()),
        ).fetchall()
        return [(datetime.fromisoformat(ts), v) for ts, v in rows]

    # --- spikes & signals ------------------------------------------------------

    def save_spike(self, spike: Spike) -> None:
        self.conn.execute(
            "INSERT INTO spikes VALUES (?,?,?,?,?)",
            (spike.theme, spike.series_key, spike.source_type,
             spike.z_score, spike.observed_at.isoformat()),
        )
        self.conn.commit()

    def recent_spikes(self, theme: str, within_minutes: int) -> list[Spike]:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=within_minutes)).isoformat()
        rows = self.conn.execute(
            "SELECT theme, series_key, source_type, z_score, observed_at "
            "FROM spikes WHERE theme=? AND observed_at > ?", (theme, cutoff),
        ).fetchall()
        return [
            Spike(theme=t, series_key=k, source_type=st, z_score=z,
                  observed_at=datetime.fromisoformat(o))
            for t, k, st, z, o in rows
        ]

    def save_signal(self, signal: AnomalySignal) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO signals VALUES (?,?,?,?)",
            (signal.id, signal.theme, signal.triggered_at.isoformat(),
             signal.model_dump_json()),
        )
        self.conn.commit()

    def recent_signal_exists(self, theme: str, within_minutes: int) -> bool:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=within_minutes)).isoformat()
        row = self.conn.execute(
            "SELECT 1 FROM signals WHERE theme=? AND triggered_at > ? LIMIT 1",
            (theme, cutoff),
        ).fetchone()
        return row is not None


def get_store(settings: Settings) -> SqliteStore:
    # Person 4 adds: if settings.storage_backend == "cosmos": return CosmosStore(...)
    return SqliteStore(settings)
