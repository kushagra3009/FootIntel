"""UEFA Champions League performance and Domestic-vs-UCL comparison endpoints (Analyses 3 & 7)."""

from typing import Literal
from fastapi import APIRouter, Query

from api.config import MAX_SEASON, MIN_SEASON
from api.schemas import ErrorResponse, UCLPairedResponse, UCLPerformanceResponse
from api.services.analytics_service import get_ucl_paired, get_ucl_performance

router = APIRouter(prefix="/api/v1/ucl", tags=["UEFA Champions League"])

UCLSortField = Literal["season", "gross_spend_m", "ucl_stage_num", "ucl_ppg", "ucl_points"]
SortOrder = Literal["asc", "desc"]


@router.get(
    "",
    response_model=UCLPerformanceResponse,
    responses={503: {"model": ErrorResponse}},
    summary="Get UCL spending, stage progression, and PPG analysis",
    description=(
        "Return UCL spending-vs-performance statistical summaries (all clubs & Top-5 subset), "
        "stage counts, Domestic-vs-UCL comparison metrics, and paginated UCL club-seasons."
    ),
)
def ucl_performance(
    season: int | None = Query(
        default=None, ge=MIN_SEASON, le=MAX_SEASON, description="Exact UCL game season year (2012-2025)."
    ),
    league_id: str | None = Query(
        default=None, min_length=2, max_length=10, description="Domestic competition ID (e.g., GB1, ES1, PT1)."
    ),
    is_top5: bool | None = Query(
        default=None, description="Filter to Top-5 domestic league participants (true/false)."
    ),
    ucl_stage: str | None = Query(
        default=None, min_length=2, max_length=40, description="Exact stage label (e.g., Final, Semi-Finals, Round of 16)."
    ),
    club_id: int | None = Query(default=None, ge=1, description="Filter by exact club_id."),
    club_name: str | None = Query(
        default=None, min_length=1, max_length=80, description="Case-insensitive club name substring."
    ),
    positive_spend_only: bool = Query(
        default=False, description="If true, include only observations with gross_spend > 0."
    ),
    sort_by: UCLSortField = Query(default="season", description="Field to sort UCL observations by."),
    sort_order: SortOrder = Query(default="desc", description="Sort direction (asc or desc)."),
    limit: int = Query(default=50, ge=1, le=500, description="Maximum records to return."),
    offset: int = Query(default=0, ge=0, description="Pagination offset."),
) -> UCLPerformanceResponse:
    return get_ucl_performance(
        season=season,
        league_id=league_id,
        is_top5=is_top5,
        ucl_stage=ucl_stage,
        club_id=club_id,
        club_name=club_name,
        positive_spend_only=positive_spend_only,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/paired",
    response_model=UCLPairedResponse,
    responses={503: {"model": ErrorResponse}},
    summary="Get paired Top-5 domestic vs UCL observations",
    description=(
        "Return club-seasons competing in both a Top-5 domestic league and UCL (n=258 total, "
        "248 positive spenders) alongside Steiger's z-test comparison."
    ),
)
def ucl_paired(
    season: int | None = Query(
        default=None, ge=MIN_SEASON, le=MAX_SEASON, description="Exact season year (2012-2025)."
    ),
    league_name: str | None = Query(
        default=None, min_length=2, max_length=40, description="Exact league name (e.g., Premier League)."
    ),
    club_id: int | None = Query(default=None, ge=1, description="Filter by exact club_id."),
    club_name: str | None = Query(
        default=None, min_length=1, max_length=80, description="Case-insensitive club name substring."
    ),
    positive_spend_only: bool = Query(
        default=False, description="If true, include only observations with gross_spend > 0."
    ),
    limit: int = Query(default=50, ge=1, le=300, description="Maximum records to return."),
    offset: int = Query(default=0, ge=0, description="Pagination offset."),
) -> UCLPairedResponse:
    return get_ucl_paired(
        season=season,
        league_name=league_name,
        club_id=club_id,
        club_name=club_name,
        positive_spend_only=positive_spend_only,
        limit=limit,
        offset=offset,
    )

