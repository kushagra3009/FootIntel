"""
FastAPI dependencies for database connections and validated analysis artifacts.
"""

from collections.abc import Generator
import threading
import duckdb
from fastapi import HTTPException, status

from api.config import (
    get_db_max_concurrency,
    get_db_path,
    get_duckdb_config,
    get_output_dir,
)

_DB_CONCURRENCY_TIMEOUT_SECONDS = 30.0
_DB_SEMAPHORE = threading.BoundedSemaphore(get_db_max_concurrency())


class ServiceUnavailableError(HTTPException):
    """Raised when DuckDB or required Phase 2 output files are unavailable."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=detail,
        )


def get_db_connection() -> Generator[duckdb.DuckDBPyConnection, None, None]:
    """Provide a bounded, read-only DuckDB connection closed cleanly after the request."""
    db_path = get_db_path()
    if not db_path.exists():
        raise ServiceUnavailableError(
            f"DuckDB database not found at configured path: {db_path.name}"
        )
    if not _DB_SEMAPHORE.acquire(timeout=_DB_CONCURRENCY_TIMEOUT_SECONDS):
        raise ServiceUnavailableError(
            "Database concurrency limit reached; please retry shortly."
        )
    con: duckdb.DuckDBPyConnection | None = None
    try:
        try:
            con = duckdb.connect(str(db_path), read_only=True)
            cfg = get_duckdb_config()
            mem_limit = cfg.get("memory_limit", "192MB")
            if "'" in mem_limit or ";" in mem_limit:
                raise ValueError(f"Invalid DuckDB memory_limit: {mem_limit!r}")
            threads = int(cfg.get("threads", "1"))
            con.execute(f"SET memory_limit = '{mem_limit}'")
            con.execute(f"SET threads = {threads}")
        except HTTPException:
            raise
        except Exception as exc:
            raise ServiceUnavailableError(f"Database connection error: {exc}") from exc
        yield con
    finally:
        if con is not None:
            con.close()
        _DB_SEMAPHORE.release()


def resolve_output_file(filename: str):
    """Return path to a validated Phase 2 output file or raise 503."""
    path = get_output_dir() / filename
    if not path.exists():
        raise ServiceUnavailableError(
            f"Validated Phase 2 output file missing: {filename}"
        )
    return path

