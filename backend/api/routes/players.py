"""Phase 4.1 — Player Intelligence, Cross-Season Comparison, and Transfer Spell Valuation Routes."""

from typing import Literal
import duckdb
from fastapi import APIRouter, Depends, Query

from api.config import MAX_SEASON, MIN_SEASON
from api.dependencies import get_db_connection
from api.schemas import (
    ErrorResponse,
    PlayerComparisonResponse,
    PlayerDetailResponse,
    PlayerSearchResponse,
    PlayerTransferSpellsResponse,
)
from api.services.player_service import (
    compare_players,
    get_player_detail,
    get_player_transfer_spells,
    search_players,
)

router = APIRouter(prefix="/api/v1/players", tags=["Players"])

PlayerSortField = Literal[
    "market_value",
    "highest_market_value",
    "name",
    "last_season",
    "appearances",
]


@router.get(
    "/search",
    response_model=PlayerSearchResponse,
    responses={503: {"model": ErrorResponse}},
    summary="Search players by name, position, and nationality",
    description=(
        "Return paginated player search results from DuckDB ordered by valuation, name, "
        "season, or appearance count. Registered statically before /{player_id}."
    ),
)
def players_search(
    q: str | None = Query(
        default=None, min_length=1, max_length=80, description="Case-insensitive player name substring."
    ),
    position: str | None = Query(
        default=None, min_length=2, max_length=30, description="Exact position filter (e.g., Attack, Midfield)."
    ),
    nationality: str | None = Query(
        default=None, min_length=2, max_length=60, description="Case-insensitive citizenship substring."
    ),
    min_appearances: int | None = Query(
        default=None, ge=1, description="Minimum recorded match appearances in DuckDB (2012–2025)."
    ),
    sort_by: PlayerSortField = Query(default="market_value", description="Field to sort search results by."),
    limit: int = Query(default=20, ge=1, le=50, description="Maximum players per page (1–50)."),
    offset: int = Query(default=0, ge=0, description="Pagination offset."),
    con: duckdb.DuckDBPyConnection = Depends(get_db_connection),
) -> PlayerSearchResponse:
    return search_players(
        con=con,
        q=q,
        position=position,
        nationality=nationality,
        min_appearances=min_appearances,
        sort_by=sort_by,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/compare",
    response_model=PlayerComparisonResponse,
    responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    summary="Compare two player-season selections (including same-player cross-season)",
    description=(
        "Compare two players in the same season, across different seasons, or the same player "
        "across different games.season scopes with documented valuation/transfer season boundaries. "
        "Registered statically before /{player_id}."
    ),
)
def players_compare(
    player_a_id: int = Query(..., ge=1, description="DuckDB player_id for Selection A."),
    player_b_id: int = Query(..., ge=1, description="DuckDB player_id for Selection B (may equal player_a_id)."),
    season_a: int | None = Query(
        default=None, ge=MIN_SEASON, le=MAX_SEASON, description="Optional games.season (2012–2025) for Selection A."
    ),
    season_b: int | None = Query(
        default=None, ge=MIN_SEASON, le=MAX_SEASON, description="Optional games.season (2012–2025) for Selection B."
    ),
    con: duckdb.DuckDBPyConnection = Depends(get_db_connection),
) -> PlayerComparisonResponse:
    return compare_players(
        con=con,
        player_a_id=player_a_id,
        player_b_id=player_b_id,
        season_a=season_a,
        season_b=season_b,
    )


@router.get(
    "/{player_id}",
    response_model=PlayerDetailResponse,
    responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    summary="Get complete Player Intelligence profile, performance, valuation, and transfers",
    description=(
        "Return full biographical metadata, season-wise appearance stats (from games.season), "
        "valuation time series, transfer history, and club career timeline for a single player."
    ),
)
def player_detail(
    player_id: int,
    con: duckdb.DuckDBPyConnection = Depends(get_db_connection),
) -> PlayerDetailResponse:
    return get_player_detail(con=con, player_id=player_id)


@router.get(
    "/{player_id}/transfer-spells",
    response_model=PlayerTransferSpellsResponse,
    responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    summary="Get spell-bounded valuation metrics for Transfer Value Calculator (Mode A)",
    description=(
        "Return a player's transfer spells paired with arrival valuation, spell-bounded peak/latest "
        "estimated market values, and MV-to-fee multiples (estimated market value, not financial ROI)."
    ),
)
def player_transfer_spells(
    player_id: int,
    con: duckdb.DuckDBPyConnection = Depends(get_db_connection),
) -> PlayerTransferSpellsResponse:
    return get_player_transfer_spells(con=con, player_id=player_id)
