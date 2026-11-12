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

DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


def get_cors_origins() -> list[str]:
    """Return allowed CORS origins from env or safe local dev defaults."""
    raw = os.getenv("FOOTINTEL_CORS_ORIGINS", "")
    if raw.strip():
        return [o.strip() for o in raw.split(",") if o.strip()]
    return list(DEFAULT_CORS_ORIGINS)


def get_db_path() -> Path:
    """Resolve active DuckDB path (supports test overrides via env)."""
    override = os.getenv("FOOTINTEL_DB_PATH")
    return Path(override) if override else DB_PATH


def get_output_dir() -> Path:
    """Resolve validated Phase 2 outputs directory (supports test overrides via env)."""
    override = os.getenv("FOOTINTEL_OUTPUT_DIR")
    return Path(override) if override else OUTPUT_DIR


__all__ = [
    "API_TITLE",
    "API_VERSION",
    "API_DESCRIPTION",
    "MIN_SEASON",
    "MAX_SEASON",
    "TOP5_LEAGUES",
    "CHARTS_DIR",
    "get_cors_origins",
    "get_db_path",
    "get_output_dir",
]

