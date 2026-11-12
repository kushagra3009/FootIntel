"""
Pydantic v2 response schemas for the FootIntel REST API.
"""

from typing import Any
from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    error: str
    detail: Any
    status_code: int


class PaginationMeta(BaseModel):
    total: int
    limit: int
    offset: int
    returned: int


class HealthResponse(BaseModel):
    status: str
    database_connected: bool
    database_file: str
    outputs_available: bool
    output_files_count: int
    tables: dict[str, int]


class OverviewKPIs(BaseModel):
    total_transfers_db: int
    total_games_db: int
    total_players_db: int
    total_clubs_db: int
    total_valuations_db: int
    top5_paid_transfers_2012_2025: int
    top5_total_spending_eur_2012_2025: float
    top5_domestic_observations: int
    top5_unique_clubs: int
    ucl_observations: int
    fee_vs_mv_sample_size: int
    spell_bounded_valuations_sample: int
    analysis_window: str


class HistoricalAggregateRow(BaseModel):
    transfer_season: str
    game_season: int
    total_transfers: int
    paid_transfers: int
    total_spending: float
    weighted_avg_fee_m: float
    active_top5_players: int
    covered_top5_players: int
    pct_active_players_covered: float


class KeyFinding(BaseModel):
    topic: str
    headline: str
    metric_name: str
    metric_value: float
    sample_size: int
    interpretation_note: str


class OverviewResponse(BaseModel):
    project: str
    research_question: str
    methodology_disclaimer: str
    kpis: OverviewKPIs
    key_findings: list[KeyFinding]
    historical_summary: list[HistoricalAggregateRow]
    caveats: list[str]


class HistoricalLeagueRow(BaseModel):
    transfer_season: str
    game_season: int
    league_id: str
    league_name: str
    total_transfers: int
    paid_transfers: int
    total_spending: float
    total_spending_m: float
    avg_fee: float | None = None
    median_fee: float | None = None
    max_fee: float | None = None
    pct_recent_cohort: float


class HistoricalTrendsResponse(BaseModel):
    coverage_warning: dict[str, Any]
    aggregate: list[HistoricalAggregateRow]
    by_league: list[HistoricalLeagueRow]
    pagination: PaginationMeta


class DomesticClubSeasonRow(BaseModel):
    season: int
    transfer_season: str
    league_id: str
    league_name: str
    club_id: int
    name: str
    played: int
    n_teams: int
    wins: int
    draws: int
    losses: int
    points: int
    goals_for: int
    goals_against: int
    goal_diff: int
    league_position: int
    pos_pct: float
    ppg: float
    gross_spend: float
    gross_income: float
    net_spend: float
    gross_spend_m: float
    gross_income_m: float
    net_spend_m: float
    players_bought_paid: int
    total_arrivals: int
    players_sold_paid: int
    spend_per_point: float
    log_gross_spend_m: float | None = None
    asinh_gross_spend_m: float


class DomesticLeagueSummary(BaseModel):
    league_id: str
    league_name: str
    observations: int
    positive_spend_observations: int
    avg_gross_spend_m: float
    avg_ppg: float
    statistics: dict[str, Any]


class DomesticPerformanceResponse(BaseModel):
    interpretation_note: str
    regression_summary: dict[str, Any]
    league_summaries: list[DomesticLeagueSummary]
    observations: list[DomesticClubSeasonRow]
    pagination: PaginationMeta


class UCLClubSeasonRow(BaseModel):
    season: int
    transfer_season: str
    club_id: int
    name: str
    league_id: str
    league_name: str
    is_top5: bool
    ucl_matches: int
    ucl_wins: int
    ucl_draws: int
    ucl_losses: int
    ucl_gf: int
    ucl_ga: int
    ucl_stage_num: float
    ucl_stage: str
    ucl_points: int
    ucl_ppg: float
    gross_spend: float
    gross_income: float
    net_spend: float
    gross_spend_m: float
    net_spend_m: float
    log_gross_spend_m: float | None = None
    asinh_gross_spend_m: float


class UCLStageCount(BaseModel):
    ucl_stage: str
    ucl_stage_num: float
    count: int


class UCLPerformanceResponse(BaseModel):
    methodology_note: str
    statistical_summary: dict[str, Any]
    domestic_vs_ucl_comparison: dict[str, Any]
    stage_distribution: list[UCLStageCount]
    observations: list[UCLClubSeasonRow]
    pagination: PaginationMeta


class PairedDomesticUCLRow(BaseModel):
    club_id: int
    season: int
    name: str
    league_name: str
    played: int
    points: int
    ppg: float
    league_position: int
    pos_pct: float
    gross_spend: float
    gross_spend_m: float
    net_spend_m: float
    log_gross_spend_m: float | None = None
    ucl_matches: int
    ucl_wins: int
    ucl_stage_num: float
    ucl_stage: str
    ucl_points: int
    ucl_ppg: float


class UCLPairedResponse(BaseModel):
    comparison_summary: dict[str, Any]
    observations: list[PairedDomesticUCLRow]
    pagination: PaginationMeta


class ClubValuationSummaryRow(BaseModel):
    club_id: int
    club_name: str
    league_id: str
    league_name: str
    num_signings: int
    total_spent: float
    total_mv_at_arrival: float
    total_peak_mv: float
    total_latest_mv: float
    avg_peak_mv_multiple: float
    median_peak_mv_multiple: float
    total_est_peak_mv_gain: float
    total_est_latest_mv_gain: float
    portfolio_peak_mv_multiple: float
    portfolio_latest_mv_multiple: float


class MarketValueSummaryResponse(BaseModel):
    valuation_disclaimer: str
    fee_vs_mv_statistics: dict[str, Any]
    club_valuation_summaries: list[ClubValuationSummaryRow]
    pagination: PaginationMeta


class FeeVsMVTransferRow(BaseModel):
    player_id: int
    player_name: str
    transfer_date: str | None = None
    transfer_season: str
    game_season: int
    from_club_name: str | None = None
    to_club_name: str
    to_club_id: int
    to_league_id: str | None = None
    league_name: str
    is_top5: bool
    transfer_fee: float
    mv_at_transfer: float
    fee_to_mv_ratio: float
    premium_pct: float
    overpay: float
    log_fee: float
    log_mv: float


class MarketValueTransfersResponse(BaseModel):
    valuation_disclaimer: str
    transfers: list[FeeVsMVTransferRow]
    pagination: PaginationMeta


class PlayerValueGainRow(BaseModel):
    player_id: int
    player_name: str
    transfer_date: str
    next_transfer_date: str | None = None
    transfer_season: str
    game_season: int
    club_id: int
    club_name: str
    league_id: str
    transfer_fee: float
    mv_at_arrival: float
    peak_mv: float
    min_mv: float
    last_mv_at_club: float
    valuation_count: int
    last_valuation_date: str
    est_peak_mv_gain: float
    est_peak_mv_gain_pct: float
    peak_mv_to_fee_multiple: float
    est_latest_mv_gain: float
    latest_mv_to_fee_multiple: float


class PlayerValueGainsResponse(BaseModel):
    valuation_disclaimer: str
    player_gains: list[PlayerValueGainRow]
    pagination: PaginationMeta


class StatisticalResultsResponse(BaseModel):
    section: str = Field(description="Requested section filter or 'all'")
    methodology_note: str
    statistical_results: dict[str, Any]
    domestic_vs_ucl_comparison: dict[str, Any] | None = None

