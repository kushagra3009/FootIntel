"""
Load downloaded CSV files into a DuckDB database.

Creates a persistent DuckDB database at data/processed/footintel.duckdb
with one table per CSV file plus derived views for analysis.
"""

import sys
from pathlib import Path
import duckdb

# Project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
DB_PATH = PROCESSED_DIR / "footintel.duckdb"

# Expected CSV files and their table names
CSV_TABLE_MAP = {
    "appearances.csv": "appearances",
    "clubs.csv": "clubs",
    "competitions.csv": "competitions",
    "games.csv": "games",
    "game_events.csv": "game_events",
    "game_lineups.csv": "game_lineups",
    "player_valuations.csv": "player_valuations",
    "players.csv": "players",
    "transfers.csv": "transfers",
}


def load_csv_to_duckdb(con: duckdb.DuckDBPyConnection, csv_path: Path, table_name: str) -> int:
    """Load a single CSV file into a DuckDB table. Returns row count."""
    print(f"  Loading {csv_path.name} → {table_name} ...")

    # DuckDB's read_csv_auto handles type inference and CSV quirks
    con.execute(f"""
        CREATE OR REPLACE TABLE {table_name} AS
        SELECT * FROM read_csv_auto('{csv_path.as_posix()}', 
            header=true, 
            sample_size=-1,
            ignore_errors=true
        )
    """)

    row_count = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    col_count = len(con.execute(f"DESCRIBE {table_name}").fetchall())
    print(f"  ✓ {table_name}: {row_count:,} rows × {col_count} columns")
    return row_count


def create_analysis_views(con: duckdb.DuckDBPyConnection) -> None:
    """Create derived views useful for our analysis."""

    # View: Club spending per season (aggregated transfers)
    con.execute("""
        CREATE OR REPLACE VIEW v_club_season_spending AS
        SELECT
            t.transfer_season AS season,
            c.name AS club_name,
            c.domestic_competition_id AS league_id,
            COUNT(*) AS num_transfers,
            SUM(CASE WHEN t.transfer_fee > 0 THEN t.transfer_fee ELSE 0 END) AS total_spending,
            AVG(CASE WHEN t.transfer_fee > 0 THEN t.transfer_fee ELSE NULL END) AS avg_fee,
            MAX(t.transfer_fee) AS max_fee
        FROM transfers t
        JOIN clubs c ON CAST(t.to_club_id AS VARCHAR) = CAST(c.club_id AS VARCHAR)
        WHERE t.transfer_fee IS NOT NULL
        GROUP BY t.transfer_season, c.name, c.domestic_competition_id
    """)
    print("  ✓ Created view: v_club_season_spending")

    # View: Club sales per season
    con.execute("""
        CREATE OR REPLACE VIEW v_club_season_sales AS
        SELECT
            t.transfer_season AS season,
            c.name AS club_name,
            c.domestic_competition_id AS league_id,
            COUNT(*) AS num_sales,
            SUM(CASE WHEN t.transfer_fee > 0 THEN t.transfer_fee ELSE 0 END) AS total_income,
            AVG(CASE WHEN t.transfer_fee > 0 THEN t.transfer_fee ELSE NULL END) AS avg_sale_fee
        FROM transfers t
        JOIN clubs c ON CAST(t.from_club_id AS VARCHAR) = CAST(c.club_id AS VARCHAR)
        WHERE t.transfer_fee IS NOT NULL
        GROUP BY t.transfer_season, c.name, c.domestic_competition_id
    """)
    print("  ✓ Created view: v_club_season_sales")

    # View: Net spending per club per season
    con.execute("""
        CREATE OR REPLACE VIEW v_club_net_spend AS
        SELECT
            COALESCE(s.season, sa.season) AS season,
            COALESCE(s.club_name, sa.club_name) AS club_name,
            COALESCE(s.league_id, sa.league_id) AS league_id,
            COALESCE(s.total_spending, 0) AS total_spending,
            COALESCE(sa.total_income, 0) AS total_income,
            COALESCE(s.total_spending, 0) - COALESCE(sa.total_income, 0) AS net_spend,
            COALESCE(s.num_transfers, 0) AS players_bought,
            COALESCE(sa.num_sales, 0) AS players_sold
        FROM v_club_season_spending s
        FULL OUTER JOIN v_club_season_sales sa
            ON s.season = sa.season AND s.club_name = sa.club_name
    """)
    print("  ✓ Created view: v_club_net_spend")

    # View: Top 5 European leagues
    con.execute("""
        CREATE OR REPLACE VIEW v_top5_leagues AS
        SELECT * FROM competitions
        WHERE competition_id IN ('GB1', 'ES1', 'IT1', 'L1', 'FR1')
    """)
    print("  ✓ Created view: v_top5_leagues")


def print_database_summary(con: duckdb.DuckDBPyConnection) -> None:
    """Print a summary of all tables and views in the database."""
    print(f"\n{'=' * 60}")
    print("Database Summary")
    print(f"{'=' * 60}")

    tables = con.execute("""
        SELECT table_name, table_type 
        FROM information_schema.tables 
        WHERE table_schema = 'main'
        ORDER BY table_type, table_name
    """).fetchall()

    for name, ttype in tables:
        count = con.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        label = "TABLE" if ttype == "BASE TABLE" else "VIEW"
        print(f"  [{label:5s}] {name:30s} — {count:>12,} rows")


def load_all() -> None:
    """Main ingestion pipeline: CSV files → DuckDB database."""
    print("=" * 60)
    print("FootIntel — DuckDB Ingestion Pipeline")
    print("=" * 60)

    # Check raw data exists
    missing = [f for f in CSV_TABLE_MAP if not (RAW_DATA_DIR / f).exists()]
    if missing:
        print(f"\n✗ Missing CSV files in {RAW_DATA_DIR}:")
        for f in missing:
            print(f"    - {f}")
        print("\nRun 'python -m ingest.download' first.")
        sys.exit(1)

    # Create processed directory
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # Connect to DuckDB (creates file if it doesn't exist)
    print(f"\nDatabase: {DB_PATH}")
    con = duckdb.connect(str(DB_PATH))

    try:
        # Load each CSV
        print(f"\nLoading {len(CSV_TABLE_MAP)} tables...\n")
        total_rows = 0
        for csv_file, table_name in CSV_TABLE_MAP.items():
            csv_path = RAW_DATA_DIR / csv_file
            total_rows += load_csv_to_duckdb(con, csv_path, table_name)

        print(f"\n  Total: {total_rows:,} rows loaded")

        # Create analysis views
        print("\nCreating analysis views...\n")
        create_analysis_views(con)

        # Print summary
        print_database_summary(con)

    finally:
        con.close()

    print(f"\n✓ Database ready at: {DB_PATH}")
    print(f"  Size: {DB_PATH.stat().st_size / (1024*1024):.1f} MB")


if __name__ == "__main__":
    load_all()
