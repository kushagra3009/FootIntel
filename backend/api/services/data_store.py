"""
Shared data-access helpers for querying DuckDB and validated Phase 2 CSV/JSON files.
Uses parameterized DuckDB SQL queries on CSV artifacts so large datasets are filtered,
sorted, and paginated without loading entire tables into Python memory.
"""

from datetime import date, datetime
import json
import math
from pathlib import Path
from typing import Any
import duckdb

from api.dependencies import ServiceUnavailableError, resolve_output_file


def sanitize_value(val: Any) -> Any:
    """Convert dates and non-finite floats into strict JSON-compatible Python types."""
    if val is None:
        return None
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return None
    return val


def sanitize_row(row: dict[str, Any]) -> dict[str, Any]:
    """Sanitize all values in a result dictionary."""
    return {k: sanitize_value(v) for k, v in row.items()}


def load_json_output(filename: str) -> dict[str, Any]:
    """Load and return a validated JSON artifact from data/processed/analysis_outputs."""
    path = resolve_output_file(filename)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        raise ServiceUnavailableError(f"Failed to read {filename}: {exc}") from exc


def build_where_clause(filters: list[tuple[str, Any]]) -> tuple[str, list[Any]]:
    """Build a parameterized SQL WHERE clause from non-empty (condition, param) pairs."""
    clauses: list[str] = []
    params: list[Any] = []
    for cond, val in filters:
        if val is None:
            continue
        clauses.append(cond)
        params.append(val)
    if not clauses:
        return "", []
    return "WHERE " + " AND ".join(clauses), params


def query_csv_rows(
    filename: str,
    filters: list[tuple[str, Any]] | None = None,
    order_by: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    """
    Query a validated Phase 2 CSV file via transient in-memory DuckDB SQL.
    Returns (sanitized_rows, total_matching_count).
    """
    path: Path = resolve_output_file(filename)
    where_sql, params = build_where_clause(filters or [])
    src = f"read_csv_auto('{path.as_posix()}', header=true)"

    with duckdb.connect(":memory:") as mem:
        total = int(
            mem.execute(f"SELECT COUNT(*) FROM {src} {where_sql}", params).fetchone()[0]
        )
        order_sql = f"ORDER BY {order_by}" if order_by else ""
        limit_sql = f"LIMIT {int(limit)} OFFSET {int(offset)}" if limit is not None else ""
        cur = mem.execute(
            f"SELECT * FROM {src} {where_sql} {order_sql} {limit_sql}",
            params,
        )
        cols = [d[0] for d in cur.description]
        rows = [sanitize_row(dict(zip(cols, rec))) for rec in cur.fetchall()]
        return rows, total


def query_csv_agg(filename: str, select_sql: str, filters: list[tuple[str, Any]] | None = None, group_by: str = "", order_by: str = "") -> list[dict[str, Any]]:
    """Run an aggregate SQL query directly on a validated CSV file."""
    path: Path = resolve_output_file(filename)
    where_sql, params = build_where_clause(filters or [])
    src = f"read_csv_auto('{path.as_posix()}', header=true)"
    group_sql = f"GROUP BY {group_by}" if group_by else ""
    order_sql = f"ORDER BY {order_by}" if order_by else ""

    with duckdb.connect(":memory:") as mem:
        cur = mem.execute(
            f"SELECT {select_sql} FROM {src} {where_sql} {group_sql} {order_sql}",
            params,
        )
        cols = [d[0] for d in cur.description]
        return [sanitize_row(dict(zip(cols, rec))) for rec in cur.fetchall()]

