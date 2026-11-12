"""Health check endpoints verifying DuckDB and Phase 2 output availability."""

import duckdb
from fastapi import APIRouter, Depends

from api.dependencies import get_db_connection
from api.schemas import ErrorResponse, HealthResponse
from api.services.analytics_service import get_health_status

router = APIRouter(tags=["Health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={503: {"model": ErrorResponse}},
    summary="Health check",
    description="Check DuckDB connectivity, table row counts, and availability of Phase 2 analytical artifacts.",
)
def health_check(con: duckdb.DuckDBPyConnection = Depends(get_db_connection)) -> HealthResponse:
    return get_health_status(con)

