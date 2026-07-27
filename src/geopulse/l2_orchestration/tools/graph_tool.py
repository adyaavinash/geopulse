"""Causal-graph traversal — the non-LLM half of the Transmission Reasoner.

Loads the seed graph from ``config/transmission_channels.yaml`` (event-category
-> channel -> raised factors -> sector direction) and the sector->ETF proxies
from ``config/sector_taxonomy.yaml``. Produces *skeleton* TransmissionChains:
the deterministic, fully-cited path for each affected sector. The agent's LLM
call then composes the mechanism narrative and calibrates confidence over these
skeletons — it may not invent sectors the graph does not support.

Deliberately a plain in-memory structure, not NetworkX: the seed graph is a
handful of flat channels, so traversal here is lookups, not pathfinding. The
public surface (``channels_for_event`` / ``walk``) is small enough that swapping
in a real graph engine later is a one-file change if the graph ever grows to
need shortest-path / cycle logic.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

from geopulse.l2_orchestration.state import CitedEdge, Direction, TransmissionChain

# config/ lives at the repo root, not under src/.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_CONFIG_DIR = _REPO_ROOT / "config"

_CHANNELS_FILE = "transmission_channels.yaml"
_SECTORS_FILE = "sector_taxonomy.yaml"


class GraphTool:
    """Read-only view over the seed causal graph."""

    def __init__(self, channels: dict, sectors: dict) -> None:
        self._channels = channels
        # sector_taxonomy.yaml nests under a top-level "sectors:" key.
        self._sectors = sectors.get("sectors", sectors)

    # ------------------------------------------------------------------ #
    # loading
    # ------------------------------------------------------------------ #
    @classmethod
    def load(cls, config_dir: str | os.PathLike | None = None) -> "GraphTool":
        cfg = Path(config_dir) if config_dir else _config_dir()
        channels = _read_yaml(cfg / _CHANNELS_FILE)
        sectors = _read_yaml(cfg / _SECTORS_FILE)
        return cls(channels, sectors)

    # ------------------------------------------------------------------ #
    # queries
    # ------------------------------------------------------------------ #
    def channels_for_event(self, category: str) -> list[str]:
        """Channels whose ``applies_to`` includes this event category, in file
        order (deterministic). A category may fan out to several channels."""
        return [
            name
            for name, ch in self._channels.items()
            if category in (ch.get("applies_to") or [])
        ]

    def sector_etf(self, sector: str) -> str:
        entry = self._sectors.get(sector) or {}
        return entry.get("etf", "")

    def raised_factors(self, channel: str) -> list[str]:
        return list((self._channels.get(channel) or {}).get("raises", []))

    def mechanism(self, channel: str) -> str:
        return (self._channels.get(channel) or {}).get("mechanism", "").strip()

    def walk(self, category: str, channel: str) -> list[TransmissionChain]:
        """Walk one channel into skeleton chains — one per affected sector.

        Each chain's hops trace ``category -> channel -> factors -> sector ->
        etf``, every hop citing the config edge it came from. Mechanism /
        rationale / confidence are left for the agent to fill.
        """
        ch = self._channels.get(channel)
        if ch is None:
            raise KeyError(f"unknown transmission channel: {channel!r}")

        factors = self.raised_factors(channel)
        factors_label = "+".join(factors) if factors else "risk_premium"

        chains: list[TransmissionChain] = []
        for direction, key in (("up", "sectors_up"), ("down", "sectors_down")):
            for sector in ch.get(key, []):
                chains.append(
                    self._skeleton(category, channel, factors_label, key, sector, direction)
                )
        return chains

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #
    def _skeleton(
        self,
        category: str,
        channel: str,
        factors_label: str,
        direction_key: str,
        sector: str,
        direction: Direction,
    ) -> TransmissionChain:
        etf = self.sector_etf(sector)
        hops = [
            CitedEdge(
                frm=category,
                relation="triggers",
                to=channel,
                citation=f"{_CHANNELS_FILE}:{channel}:applies_to",
            ),
            CitedEdge(
                frm=channel,
                relation="raises",
                to=factors_label,
                citation=f"{_CHANNELS_FILE}:{channel}:raises",
            ),
            CitedEdge(
                frm=factors_label,
                relation=direction_key,      # "sectors_up" | "sectors_down"
                to=sector,
                citation=f"{_CHANNELS_FILE}:{channel}:{direction_key}",
            ),
            CitedEdge(
                frm=sector,
                relation="proxy",
                to=etf,
                citation=f"{_SECTORS_FILE}:{sector}:etf",
            ),
        ]
        return TransmissionChain(
            sector=sector,
            etf=etf,
            direction=direction,
            channel=channel,
            hops=hops,
        )


def _config_dir() -> Path:
    override = os.environ.get("GEOPULSE_CONFIG_DIR")
    return Path(override) if override else _DEFAULT_CONFIG_DIR


def _read_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@lru_cache(maxsize=1)
def get_graph_tool() -> GraphTool:
    """Process-wide singleton (config is static within a run)."""
    return GraphTool.load()
