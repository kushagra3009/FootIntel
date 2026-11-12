"""Executive overview endpoint exposing project KPIs and verified key findings."""

import duckdb
from fastapi import APIRouter, Depends

from api.dependencies import get_db_connection
from api.schemas import ErrorResponse, OverviewResponse
from api.services.analytics_service import get_overview_data

router = APIRouter(prefix="/api/v1/overview", tags=["Overview"])


@router.get(
    "",
    response_model=OverviewResponse,
    responses={503: {"model": ErrorResponse}},
    summary="Get executive overview KPIs and findings",
    description=(
        "Return database-wide counts, Top-5 transfer totals (2012/13-2025/26), "
        "historical trend summary with active-player coverage, and non-causal statistical highlights."
    ),
)
def overview(con: duckdb.DuckDBPyConnection = Depends(get_db_connection)) -> OverviewResponse:
    return get_overview_data(con)

