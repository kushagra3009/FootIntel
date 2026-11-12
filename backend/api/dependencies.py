"""
FastAPI dependencies for database connections and validated analysis artifacts.
"""

from collections.abc import Generator
import duckdb
from fastapi import HTTPException, status

from api.config import get_db_path, get_output_dir


class ServiceUnavailableError(HTTPException):
    """Raised when DuckDB or required Phase 2 output files are unavailable."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
        )


def get_db_connection() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """Provide a read-only DuckDB connection closed cleanly after the request."""
    db_path = get_db_path()
    if not db_path.exists():
        raise ServiceUnavailableError(
            f"DuckDB database not found at configured path: {db_path.name}"
        )
    con: duckdb.DuckDBPyConnection | None = None
    try:
        con = duckdb.connect(str(db_path), read_only=True)
        yield con
    except HTTPException:
        raise
    except Exception as exc:
        raise ServiceUnavailableError(f"Database connection error: {exc}") from exc
    finally:
        if con is not None:
            con.close()


def resolve_output_file(filename: str):
    """Return path to a validated Phase 2 output file or raise 503."""
    path = get_output_dir() / filename
    if not path.exists():
        raise ServiceUnavailableError(
            f"Validated Phase 2 output file missing: {filename}"
        )
    return path

