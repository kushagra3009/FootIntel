"""
Utility functions for season format conversion and database access.
"""

import duckdb
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "processed" / "footintel.duckdb"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "analysis_outputs"
CHARTS_DIR = PROJECT_ROOT / "data" / "processed" / "charts"

TOP5_LEAGUES = {
    "GB1": "Premier League",
    "ES1": "LaLiga",
    "IT1": "Serie A",
    "L1": "Bundesliga",
    "FR1": "Ligue 1",
}

# Games table has season as integer (e.g. 2022 = the 2022/23 season)
# Transfers table has transfer_season as string (e.g. '22/23')
# We need bidirectional mapping

def transfer_season_to_game_season(ts: str) -> int | None:
    """Convert '22/23' -> 2022, '99/00' -> 1999, '04/05' -> 2004."""
    if not ts or "/" not in ts:
        return None
    parts = ts.split("/")
    first = int(parts[0])
    # Handle century: 93/94 -> 1993, 04/05 -> 2004
    if first >= 90:
        return 1900 + first
    else:
        return 2000 + first


def game_season_to_transfer_season(gs: int) -> str:
    """Convert 2022 -> '22/23', 1999 -> '99/00'."""
    y1 = gs % 100
    y2 = (gs + 1) % 100
    return f"{y1:02d}/{y2:02d}"


def get_connection(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    """Get a DuckDB connection."""
    return duckdb.connect(str(DB_PATH), read_only=read_only)


def ensure_dirs():
    """Ensure output directories exist."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
