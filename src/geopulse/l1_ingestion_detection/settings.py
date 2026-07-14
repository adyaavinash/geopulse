"""Step 1 — Settings. Every detection threshold lives here, not in code:
you will tune these constantly during the false-positive-budget phase."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- storage / messaging -------------------------------------------------
    storage_backend: str = "sqlite"                 # sqlite | cosmos
    sqlite_path: str = "geopulse_local.db"
    storage_connection_string: str = "UseDevelopmentStorage=true"  # Azurite default
    anomaly_queue_name: str = "anomaly-events"

    # --- credentials (env / .env / Key Vault refs in Azure) ------------------
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_user_agent: str = "geopulse/0.1 by <your_reddit_username>"
    alpha_vantage_key: str = ""

    # --- collector cadence & scope -------------------------------------------
    dry_run: bool = False                           # collectors read fixtures instead of network
    fixtures_dir: str = "fixtures"
    gdelt_timespan: str = "1h"                      # per-poll article window
    gdelt_max_records: int = 75                     # per theme per poll (API max 250)
    domain_blocklist: list[str] = []                # low-credibility domains to drop
    subreddits: list[str] = ["geopolitics", "wallstreetbets", "stocks"]
    market_tickers: list[str] = [
        "^VIX", "XLE", "ITA", "JETS", "SMH", "XLP", "XLU", "GLD", "DX-Y.NYB", "JPY=X",
    ]

    # --- detection thresholds (THE tuning surface) ----------------------------
    baseline_days: int = 7                          # trailing window for mean/std
    bucket_minutes: int = 15                        # time-series resolution
    z_threshold_news: float = 3.0
    z_threshold_social: float = 3.0
    z_threshold_market: float = 2.5                 # markets are already denoised
    tone_threshold: float = -4.0                    # GDELT avg tone gate (negative = bad news)
    polymarket_prob_jump: float = 0.10              # 10-point probability move
    min_baseline_samples: int = 96                  # refuse to fire on a cold series (1 day)
    composite_window_minutes: int = 60              # spikes must co-occur within this
    composite_min_source_types: int = 2             # THE cost gate
    signal_cooldown_minutes: int = 60               # per-theme suppression after firing

    model_config = {"env_file": ".env", "env_prefix": "GEOPULSE_"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Theme taxonomy -> GDELT query strings + keyword sets used by social/market
# mapping. Keep in sync with config/event_taxonomy.yaml in the full repo.
THEMES: dict[str, dict] = {
    "chokepoint_hormuz": {
        "gdelt_query": '("strait of hormuz" OR hormuz) (closure OR attack OR blockade OR seized OR missile)',
        "keywords": ["hormuz", "strait of hormuz"],
    },
    "chokepoint_suez": {
        "gdelt_query": '("suez canal" OR "red sea" OR "bab el-mandeb") (blocked OR attack OR closure OR houthi)',
        "keywords": ["suez", "red sea", "bab el-mandeb"],
    },
    "armed_conflict_escalation": {
        "gdelt_query": '(airstrike OR invasion OR "military strike" OR mobilization) (oil OR energy OR shipping OR markets)',
        "keywords": ["airstrike", "invasion", "escalation", "mobilization"],
    },
    "market_crash": {
        "gdelt_query": '("circuit breaker" OR "market crash" OR "stocks plunge" OR selloff OR "flash crash")',
        "keywords": ["crash", "circuit breaker", "selloff", "plunge"],
    },
    "sanctions_exportcontrols": {
        "gdelt_query": '(sanctions OR "export controls" OR embargo) (oil OR semiconductor OR bank OR energy)',
        "keywords": ["sanctions", "embargo", "export controls"],
    },
}
