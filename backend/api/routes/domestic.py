"""Domestic league spending vs sporting performance endpoints (Analysis 2)."""

from typing import Literal
from fastapi import APIRouter, HTTPException, Query, status

from api.config import MAX_SEASON, MIN_SEASON
from api.schemas import DomesticPerformanceResponse, ErrorResponse
from api.services.analytics_service import get_domestic_performance

router = APIRouter(prefix="/api/v1/domestic", tags=["Domestic Performance"])

Top5LeagueCode = Literal["GB1", "ES1", "IT1", "L1", "FR1"]
DomesticSortField = Literal[
    "season", "gross_spend_m", "net_spend_m", "points", "ppg", "league_position", "pos_pct"
]
SortOrder = Literal["asc", "desc"]


@router.get(
    "",
    response_model=DomesticPerformanceResponse,
    responses={400: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    summary="Get domestic spending vs league performance",
    description=(
        "Return Top-5 league summaries, pooled & per-league regression/correlation statistics, "
        "and filtered/paginated club-season observations (PPG, league position, gross/net spend)."
    ),
)
def domestic_performance(
    league_id: Top5LeagueCode | None = Query(
        default=None, description="Filter by Top-5 competition ID (GB1, ES1, IT1, L1, FR1)."
    ),
    season: int | None = Query(
        default=None, ge=MIN_SEASON, le=MAX_SEASON, description="Exact game season year (2012-2025)."
    ),
    start_season: int | None = Query(
        default=None, ge=MIN_SEASON, le=MAX_SEASON, description="Minimum game season year."
    ),
    end_season: int | None = Query(
        default=None, ge=MIN_SEASON, le=MAX_SEASON, description="Maximum game season year."
    ),
    club_id: int | None = Query(default=None, ge=1, description="Filter by exact club_id."),
    club_name: str | None = Query(
        default=None, min_length=1, max_length=80, description="Case-insensitive club name substring."
    ),
    positive_spend_only: bool = Query(
        default=False, description="If true, include only observations with gross_spend > 0."
    ),
    min_spend_m: float | None = Query(
        default=None, ge=0.0, description="Minimum gross spend in EUR millions."
    ),
    sort_by: DomesticSortField = Query(default="season", description="Field to sort observations by."),
    sort_order: SortOrder = Query(default="desc", description="Sort direction (asc or desc)."),
    limit: int = Query(default=50, ge=1, le=500, description="Maximum records to return."),
    offset: int = Query(default=0, ge=0, description="Pagination offset."),
) -> DomesticPerformanceResponse:
    if start_season is not None and end_season is not None and start_season > end_season:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_season cannot be greater than end_season.",
        )
    return get_domestic_performance(
        league_id=league_id,
        season=season,
        start_season=start_season,
        end_season=end_season,
        club_id=club_id,
        club_name=club_name,
        positive_spend_only=positive_spend_only,
        min_spend_m=min_spend_m,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )

