"""Historical transfer spending trends endpoints (Analysis 1)."""

from typing import Literal
from fastapi import APIRouter, HTTPException, Query, status

from api.config import MAX_SEASON, MIN_SEASON
from api.schemas import ErrorResponse, HistoricalTrendsResponse
from api.services.analytics_service import get_historical_trends

router = APIRouter(prefix="/api/v1/trends", tags=["Historical Trends"])

Top5LeagueCode = Literal["GB1", "ES1", "IT1", "L1", "FR1"]


@router.get(
    "",
    response_model=HistoricalTrendsResponse,
    responses={400: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    summary="Get season-aligned historical transfer spending trends",
    description=(
        "Return season-by-season aggregate Top-5 spending and league-level breakdowns with "
        "active-player cohort coverage warnings."
    ),
)
def historical_trends(
    league_id: Top5LeagueCode | None = Query(
        default=None,
        description="Filter league breakdown by Top-5 competition ID (GB1, ES1, IT1, L1, FR1).",
    ),
    start_season: int | None = Query(
        default=None, ge=MIN_SEASON, le=MAX_SEASON,
        description="Minimum game season year (2012-2025).",
    ),
    end_season: int | None = Query(
        default=None, ge=MIN_SEASON, le=MAX_SEASON,
        description="Maximum game season year (2012-2025).",
    ),
    limit: int = Query(default=70, ge=1, le=200, description="Max league-season rows to return."),
    offset: int = Query(default=0, ge=0, description="Pagination offset for league-season rows."),
) -> HistoricalTrendsResponse:
    if start_season is not None and end_season is not None and start_season > end_season:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_season cannot be greater than end_season.",
        )
    return get_historical_trends(
        league_id=league_id,
        start_season=start_season,
        end_season=end_season,
        limit=limit,
        offset=offset,
    )

