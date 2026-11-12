"""
Configuration for the FootIntel FastAPI REST Backend.
Reuses validated Phase 1 & Phase 2 path constants from analysis.utils.
"""

import os
from pathlib import Path

from analysis.utils import CHARTS_DIR, DB_PATH, OUTPUT_DIR, TOP5_LEAGUES

API_TITLE = "FootIntel API"
API_VERSION = "1.0.0"
API_DESCRIPTION = (
    "REST API exposing FootIntel's validated DuckDB dataset and Phase 2 statistical "
    "analyses investigating 'Does Money Actually Buy Success in Professional Football?'. "
    "All cross-sectional regressions report observational associations with club-clustered "
    "standard errors; historical transfer totals carry cohort-coverage metadata."
)

MIN_SEASON = 2012
MAX_SEASON = 2025

CORE_TABLES: tuple[str, ...] = (
    "appearances",
    "clubs",
    "competitions",
    "games",
    "player_valuations",
    "players",
    "transfers",
)

REQUIRED_OUTPUT_FILES: tuple[str, ...] = (
    "01_historical_trends_aggregate.csv",
    "01_historical_trends_by_league.csv",
    "02_domestic_spending_vs_performance.csv",
    "03_ucl_spending_vs_performance.csv",
    "04_fee_vs_market_value.csv",
    "05_club_value_gain_summary.csv",
    "05_player_value_gain.csv",
    "06_statistical_results.json",
    "07_domestic_vs_ucl_comparison.json",
    "07_domestic_vs_ucl_paired.csv",
)

DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


def _parse_positive_int(env_name: str, default: int) -> int:
    """Parse a positive integer environment variable with fallback validation."""
    raw = os.getenv(env_name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{env_name} must be a positive integer, got {raw!r}") from exc
    if value < 1:
        raise ValueError(f"{env_name} must be >= 1, got {value}")
    return value


def get_cors_origins() -> list[str]:
    """
    Return allowed CORS origins from env or local dev defaults.
    In production runtime, FOOTINTEL_CORS_ORIGINS must be explicitly configured.
    """
    raw = os.getenv("FOOTINTEL_CORS_ORIGINS", "")
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    if origins:
        return origins
    if is_production_runtime():
        raise ValueError(
            "FOOTINTEL_CORS_ORIGINS must be set and non-empty when running in production mode."
        )
    return list(DEFAULT_CORS_ORIGINS)


def get_db_path() -> Path:
    """Resolve active DuckDB path (supports test overrides via env)."""
    override = os.getenv("FOOTINTEL_DB_PATH")
    return Path(override) if override else DB_PATH


def get_output_dir() -> Path:
    """Resolve validated Phase 2 outputs directory (supports test overrides via env)."""
    override = os.getenv("FOOTINTEL_OUTPUT_DIR")
    return Path(override) if override else OUTPUT_DIR


def get_duckdb_config() -> dict[str, str]:
    """Return DuckDB config bounds for file-backed read-only connections."""
    memory_limit = os.getenv("FOOTINTEL_DUCKDB_MEMORY_LIMIT", "192MB").strip() or "192MB"
    threads = str(_parse_positive_int("FOOTINTEL_DUCKDB_THREADS", 1))
    return {"memory_limit": memory_limit, "threads": threads}


def get_in_memory_duckdb_config() -> dict[str, str]:
    """Return tighter DuckDB config bounds for transient CSV :memory: queries."""
    memory_limit = os.getenv("FOOTINTEL_DUCKDB_CSV_MEMORY_LIMIT", "64MB").strip() or "64MB"
    threads = str(_parse_positive_int("FOOTINTEL_DUCKDB_THREADS", 1))
    return {"memory_limit": memory_limit, "threads": threads}


def get_db_max_concurrency() -> int:
    """Return max concurrent file-backed DuckDB request connections."""
    return _parse_positive_int("FOOTINTEL_DB_MAX_CONCURRENCY", 4)


def get_csv_max_concurrency() -> int:
    """Return max concurrent in-memory DuckDB CSV queries."""
    return _parse_positive_int("FOOTINTEL_CSV_MAX_CONCURRENCY", 2)


def is_production_runtime() -> bool:
    """Return True when production/Render hydration safeguards must be enforced."""
    env_mode = os.getenv("FOOTINTEL_ENV", "").strip().lower()
    require_flag = os.getenv("FOOTINTEL_REQUIRE_HYDRATION", "").strip().lower()
    render_flag = os.getenv("RENDER", "").strip().lower()
    return (
        env_mode == "production"
        or require_flag in {"1", "true", "yes"}
        or render_flag in {"1", "true", "yes"}
    )


def get_hydration_settings() -> dict[str, str]:
    """Return stripped hydration asset URLs and required SHA-256 checksums."""
    return {
        "db_asset_url": os.getenv("FOOTINTEL_DB_ASSET_URL", "").strip(),
        "db_sha256": os.getenv("FOOTINTEL_DB_SHA256", "").strip(),
        "outputs_asset_url": os.getenv("FOOTINTEL_OUTPUTS_ASSET_URL", "").strip(),
        "outputs_sha256": os.getenv("FOOTINTEL_OUTPUTS_SHA256", "").strip(),
    }


__all__ = [
    "API_TITLE",
    "API_VERSION",
    "API_DESCRIPTION",
    "MIN_SEASON",
    "MAX_SEASON",
    "CORE_TABLES",
    "REQUIRED_OUTPUT_FILES",
    "TOP5_LEAGUES",
    "CHARTS_DIR",
    "get_cors_origins",
    "get_db_path",
    "get_output_dir",
    "get_duckdb_config",
    "get_in_memory_duckdb_config",
    "get_db_max_concurrency",
    "get_csv_max_concurrency",
    "is_production_runtime",
    "get_hydration_settings",
]

