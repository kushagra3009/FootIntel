"""Transfer fee vs estimated market value and spell-bounded valuation endpoints (Analyses 4 & 5)."""

from typing import Literal
from fastapi import APIRouter, Query

from api.config import MAX_SEASON, MIN_SEASON
from api.schemas import (
    ErrorResponse,
    MarketValueSummaryResponse,
    MarketValueTransfersResponse,
    PlayerValueGainsResponse,
)
from api.services.analytics_service import (
    get_market_value_summary,
    get_market_value_transfers,
    get_player_value_gains,
)

router = APIRouter(prefix="/api/v1/market-value", tags=["Market Value"])

ClubSummarySortField = Literal[
    "total_est_peak_mv_gain",
    "total_est_latest_mv_gain",
    "portfolio_peak_mv_multiple",
    "portfolio_latest_mv_multiple",
    "total_spent",
    "num_signings",
]
TransferSortField = Literal[
    "transfer_fee", "mv_at_transfer", "overpay", "premium_pct", "fee_to_mv_ratio", "game_season"
]
PlayerGainSortField = Literal[
    "est_peak_mv_gain",
    "est_latest_mv_gain",
    "peak_mv_to_fee_multiple",
    "latest_mv_to_fee_multiple",
    "transfer_fee",
    "peak_mv",
    "game_season",
]
SortOrder = Literal["asc", "desc"]


@router.get(
    "/summary",
    response_model=MarketValueSummaryResponse,
    responses={503: {"model": ErrorResponse}},
    summary="Get fee-vs-market-value stats and club valuation summaries",
    description=(
        "Return Analysis 4 aggregate statistics and paginated club-level spell-bounded "
        "estimated market value gains and MV-to-fee multiples (not financial ROI)."
    ),
)
def market_value_summary(
    league_id: str | None = Query(
        default=None, min_length=2, max_length=10, description="Filter clubs by domestic league ID (e.g., GB1, L1)."
    ),
    club_name: str | None = Query(
        default=None, min_length=1, max_length=80, description="Case-insensitive club name substring."
    ),
    min_signings: int | None = Query(
        default=None, ge=1, description="Minimum number of tracked paid signings."
    ),
    sort_by: ClubSummarySortField = Query(
        default="total_est_peak_mv_gain", description="Field to sort club summaries by."
    ),
    sort_order: SortOrder = Query(default="desc", description="Sort direction (asc or desc)."),
    limit: int = Query(default=25, ge=1, le=200, description="Maximum clubs to return."),
    offset: int = Query(default=0, ge=0, description="Pagination offset."),
) -> MarketValueSummaryResponse:
    return get_market_value_summary(
        league_id=league_id,
        club_name=club_name,
        min_signings=min_signings,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/transfers",
    response_model=MarketValueTransfersResponse,
    responses={503: {"model": ErrorResponse}},
    summary="Get transfer fee vs estimated arrival market value records",
    description="Return paginated transfer-level fee vs market value ratios, premiums, and overpay amounts.",
)
def market_value_transfers(
    season: int | None = Query(
        default=None, ge=MIN_SEASON, le=MAX_SEASON, description="Exact game season year (2012-2025)."
    ),
    league_id: str | None = Query(
        default=None, min_length=2, max_length=10, description="Buying club competition ID (e.g., GB1, ES1)."
    ),
    is_top5: bool | None = Query(default=None, description="Filter to Top-5 buying clubs (true/false)."),
    player_name: str | None = Query(
        default=None, min_length=1, max_length=80, description="Case-insensitive player name substring."
    ),
    club_name: str | None = Query(
        default=None, min_length=1, max_length=80, description="Case-insensitive buying club substring."
    ),
    min_fee: float | None = Query(default=None, ge=0.0, description="Minimum transfer fee in EUR."),
    sort_by: TransferSortField = Query(default="transfer_fee", description="Field to sort transfers by."),
    sort_order: SortOrder = Query(default="desc", description="Sort direction (asc or desc)."),
    limit: int = Query(default=50, ge=1, le=250, description="Maximum transfers to return."),
    offset: int = Query(default=0, ge=0, description="Pagination offset."),
) -> MarketValueTransfersResponse:
    return get_market_value_transfers(
        season=season,
        league_id=league_id,
        is_top5=is_top5,
        player_name=player_name,
        club_name=club_name,
        min_fee=min_fee,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/player-gains",
    response_model=PlayerValueGainsResponse,
    responses={503: {"model": ErrorResponse}},
    summary="Get spell-bounded player estimated market value gains",
    description=(
        "Return paginated player transfers with valuation progression strictly bounded to "
        "[transfer_date, next_transfer_date). Measures estimated market value change, not realized cash ROI."
    ),
)
def player_value_gains(
    club_id: int | None = Query(default=None, ge=1, description="Filter by exact buying club_id."),
    club_name: str | None = Query(
        default=None, min_length=1, max_length=80, description="Case-insensitive club name substring."
    ),
    league_id: str | None = Query(
        default=None, min_length=2, max_length=10, description="Top-5 league ID (GB1, ES1, IT1, L1, FR1)."
    ),
    season: int | None = Query(
        default=None, ge=MIN_SEASON, le=2024, description="Transfer game season year (2012-2024)."
    ),
    player_name: str | None = Query(
        default=None, min_length=1, max_length=80, description="Case-insensitive player name substring."
    ),
    sort_by: PlayerGainSortField = Query(
        default="est_peak_mv_gain", description="Field to sort player spell gains by."
    ),
    sort_order: SortOrder = Query(default="desc", description="Sort direction (asc or desc)."),
    limit: int = Query(default=50, ge=1, le=250, description="Maximum records to return."),
    offset: int = Query(default=0, ge=0, description="Pagination offset."),
) -> PlayerValueGainsResponse:
    return get_player_value_gains(
        club_id=club_id,
        club_name=club_name,
        league_id=league_id,
        season=season,
        player_name=player_name,
        sort_by=sort_by,
        sort_order=sort_order,
        limit=limit,
        offset=offset,
    )

