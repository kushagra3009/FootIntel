"""
Service layer implementing business logic for all FootIntel REST endpoints.
Combines live DuckDB metadata queries with validated Phase 2 statistical outputs.
"""

from typing import Any
import duckdb

from api.config import TOP5_LEAGUES, get_db_path, get_output_dir
from api.dependencies import ServiceUnavailableError
from api.schemas import (
    ClubValuationSummaryRow,
    DomesticClubSeasonRow,
    DomesticLeagueSummary,
    DomesticPerformanceResponse,
    FeeVsMVTransferRow,
    HealthResponse,
    HistoricalAggregateRow,
    HistoricalLeagueRow,
    HistoricalTrendsResponse,
    KeyFinding,
    MarketValueSummaryResponse,
    MarketValueTransfersResponse,
    OverviewKPIs,
    OverviewResponse,
    PaginationMeta,
    PairedDomesticUCLRow,
    PlayerValueGainRow,
    PlayerValueGainsResponse,
    StatisticalResultsResponse,
    UCLClubSeasonRow,
    UCLPairedResponse,
    UCLPerformanceResponse,
    UCLStageCount,
)
from api.services.data_store import load_json_output, query_csv_agg, query_csv_rows

CORE_TABLES = [
    "appearances",
    "clubs",
    "competitions",
    "games",
    "player_valuations",
    "players",
    "transfers",
]

COVERAGE_WARNING = {
    "severity": "warning",
    "summary": (
        "100.0% of records in transfers belong to players with last_season >= 2023 "
        "(only 1 transfer row exists for players with last_season == 2022, and 0 for <= 2021)."
    ),
    "implication": (
        "Pre-2022/23 transfer totals undercount retired player cohorts (active Top-5 player "
        "coverage grows from 16.7% in 2012/13 to 87.6%-100.0% in 2022/23-2025/26). Do not "
        "interpret early-season totals as complete market spending."
    ),
}

VALUATION_DISCLAIMER = (
    "Transfermarkt player valuations are crowdsourced market value estimates, NOT realized "
    "transfer sale proceeds, accounting profit, or cash Return on Investment (ROI). "
    "Negative latest multiples can reflect aging, contract run-down, or retirement rather than trading loss."
)

NON_CAUSAL_NOTE = (
    "All regressions and correlations measure observational associations with Liang-Zeger "
    "club-clustered standard errors, NOT causal effects. Pooled cross-sectional R² (0.2076) "
    "captures persistent club hierarchy (omitted wage bills, commercial revenue, reverse causality), "
    "whereas two-way Club+Season Fixed Effects show near-zero within-club variance explained."
)


def _paginate(total: int, limit: int, offset: int, returned: int) -> PaginationMeta:
    return PaginationMeta(total=total, limit=limit, offset=offset, returned=returned)


def get_health_status(con: duckdb.DuckDBPyConnection) -> HealthResponse:
    """Verify DuckDB connectivity, table row counts, and Phase 2 output files."""
    try:
        table_counts: dict[str, int] = {}
        for tbl in CORE_TABLES:
            res = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()
            table_counts[tbl] = int(res[0]) if res else 0
    except Exception as exc:
        raise ServiceUnavailableError(f"Failed querying DuckDB tables: {exc}") from exc

    out_dir = get_output_dir()
    out_files = list(out_dir.glob("*")) if out_dir.exists() else []
    return HealthResponse(
        status="ok",
        database_connected=True,
        database_file=get_db_path().name,
        outputs_available=len(out_files) >= 10,
        output_files_count=len(out_files),
        tables=table_counts,
    )


def get_overview_data(con: duckdb.DuckDBPyConnection) -> OverviewResponse:
    """Assemble executive KPIs, historical series, and dynamic statistical findings."""
    try:
        counts = con.execute("""
            SELECT
                (SELECT COUNT(*) FROM transfers),
                (SELECT COUNT(*) FROM games),
                (SELECT COUNT(*) FROM players),
                (SELECT COUNT(*) FROM clubs),
                (SELECT COUNT(*) FROM player_valuations)
        """).fetchone()
    except Exception as exc:
        raise ServiceUnavailableError(f"Database query error: {exc}") from exc

    agg_rows, _ = query_csv_rows("01_historical_trends_aggregate.csv", order_by="game_season ASC")
    stats_json = load_json_output("06_statistical_results.json")
    comp_json = load_json_output("07_domestic_vs_ucl_comparison.json")

    top5_paid_total = sum(int(r["paid_transfers"]) for r in agg_rows)
    top5_spend_total = float(sum(float(r["total_spending"]) for r in agg_rows))

    s6a = stats_json["6A_domestic_spend_vs_performance"]
    s6d_all = stats_json["6D_ucl_spend_vs_performance"]["all_ucl_spenders"]
    s6e = stats_json["6E_fee_vs_mv"]
    s6f = stats_json["6F_robustness"]

    kpis = OverviewKPIs(
        total_transfers_db=int(counts[0]),
        total_games_db=int(counts[1]),
        total_players_db=int(counts[2]),
        total_clubs_db=int(counts[3]),
        total_valuations_db=int(counts[4]),
        top5_paid_transfers_2012_2025=top5_paid_total,
        top5_total_spending_eur_2012_2025=top5_spend_total,
        top5_domestic_observations=int(s6a["n_full_sample"]),
        top5_unique_clubs=int(s6a["full_sample_asinh_ols_ppg"]["clusters"]),
        ucl_observations=int(s6d_all["n"]),
        fee_vs_mv_sample_size=int(s6e["n"]),
        spell_bounded_valuations_sample=4881,
        analysis_window="2012/13-2025/26",
    )

    # Read exact count of spell-bounded valuations dynamically via CSV aggregation
    pv_count_row = query_csv_agg("05_player_value_gain.csv", "COUNT(*) AS cnt")
    kpis.spell_bounded_valuations_sample = int(pv_count_row[0]["cnt"])

    # Read exact total UCL observations from 03_ucl CSV (437 total vs 415 positive spenders)
    ucl_count_row = query_csv_agg("03_ucl_spending_vs_performance.csv", "COUNT(*) AS cnt")
    kpis.ucl_observations = int(ucl_count_row[0]["cnt"])

    findings = [
        KeyFinding(
            topic="Domestic Pooled Association",
            headline="Log gross spending explains ~20.8% of pooled Top-5 PPG variance (non-causal).",
            metric_name="r_squared_log_spend_ppg",
            metric_value=float(s6a["ols_log_spend_m_to_ppg"]["r_squared"]),
            sample_size=int(s6a["n_spenders"]),
            interpretation_note=(
                f"Pearson r={s6a['pearson_r_log_vs_ppg']}, Spearman rho={s6a['spearman_rho_spend_vs_ppg']}, "
                f"cluster-robust p={s6a['ols_log_spend_m_to_ppg']['cluster_p']:.2e}."
            ),
        ),
        KeyFinding(
            topic="Between-Club vs Within-Club Reality Check",
            headline="Two-way fixed effects reduce explained within-club variance below 0.5%.",
            metric_name="two_way_fe_within_r_squared",
            metric_value=float(s6f["two_way_fixed_effects_ppg"]["within_r_squared"]),
            sample_size=int(s6f["two_way_fixed_effects_ppg"]["n"]),
            interpretation_note=(
                f"Club-averaged R²={s6f['club_averaged_cross_section']['r_squared']} vs within-club "
                f"R²={s6f['two_way_fixed_effects_ppg']['within_r_squared']} (p={s6f['two_way_fixed_effects_ppg']['cluster_p']:.4f})."
            ),
        ),
        KeyFinding(
            topic="UEFA Champions League",
            headline="Across all UCL clubs, spending explains 19.0% of UCL PPG variance; narrower among Top-5 clubs.",
            metric_name="ucl_ppg_r_squared_all_spenders",
            metric_value=float(s6d_all["ucl_ppg_ols"]["r_squared"]),
            sample_size=int(s6d_all["n"]),
            interpretation_note=(
                f"UCL PPG r={s6d_all['ucl_ppg_pearson_r']} overall vs "
                f"r={comp_json['spenders_ucl_ppg_r']} among paired Top-5 UCL qualifiers (n={comp_json['n_paired_spenders']})."
            ),
        ),
        KeyFinding(
            topic="Fee vs Market Value",
            headline="Transfer fees track arrival market valuations closely in log-log space.",
            metric_name="fee_vs_mv_log_log_r_squared",
            metric_value=float(s6e["ols_log_mv_to_log_fee"]["r_squared"]),
            sample_size=int(s6e["n"]),
            interpretation_note=(
                f"Median fee/MV ratio={s6e['median_fee_to_mv_ratio']}, underpay={s6e['pct_underpay']}%, "
                f"overpay={s6e['pct_overpay']}%."
            ),
        ),
    ]

    return OverviewResponse(
        project="FootIntel",
        research_question="Does Money Actually Buy Success in Professional Football?",
        methodology_disclaimer=NON_CAUSAL_NOTE,
        kpis=kpis,
        key_findings=findings,
        historical_summary=[HistoricalAggregateRow(**r) for r in agg_rows],
        caveats=[
            COVERAGE_WARNING["summary"] + " " + COVERAGE_WARNING["implication"],
            VALUATION_DISCLAIMER,
            "No club wage bills or commercial revenue figures exist in the dataset.",
            "Zero and undisclosed fees in transfer_fee cannot be cleanly separated from free/loan transfers.",
        ],
    )


def get_historical_trends(
    league_id: str | None = None,
    start_season: int | None = None,
    end_season: int | None = None,
    limit: int = 100,
    offset: int = 0,
) -> HistoricalTrendsResponse:
    """Return aggregate and league-level historical spending trends with coverage metadata."""
    agg_filters = [
        ("game_season >= ?", start_season),
        ("game_season <= ?", end_season),
    ]
    agg_rows, _ = query_csv_rows(
        "01_historical_trends_aggregate.csv",
        filters=agg_filters,
        order_by="game_season ASC",
    )

    league_filters = [
        ("league_id = ?", league_id),
        ("game_season >= ?", start_season),
        ("game_season <= ?", end_season),
    ]
    league_rows, total = query_csv_rows(
        "01_historical_trends_by_league.csv",
        filters=league_filters,
        order_by="game_season ASC, league_id ASC",
        limit=limit,
        offset=offset,
    )

    return HistoricalTrendsResponse(
        coverage_warning=COVERAGE_WARNING,
        aggregate=[HistoricalAggregateRow(**r) for r in agg_rows],
        by_league=[HistoricalLeagueRow(**r) for r in league_rows],
        pagination=_paginate(total, limit, offset, len(league_rows)),
    )


def get_domestic_performance(
    league_id: str | None = None,
    season: int | None = None,
    start_season: int | None = None,
    end_season: int | None = None,
    club_id: int | None = None,
    club_name: str | None = None,
    positive_spend_only: bool = False,
    min_spend_m: float | None = None,
    sort_by: str = "season",
    sort_order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> DomesticPerformanceResponse:
    """Return domestic spending vs league performance data, league summaries, and regression stats."""
    sort_map = {
        "season": "season",
        "gross_spend_m": "gross_spend_m",
        "net_spend_m": "net_spend_m",
        "points": "points",
        "ppg": "ppg",
        "league_position": "league_position",
        "pos_pct": "pos_pct",
    }
    order_col = sort_map[sort_by]
    order_dir = "ASC" if sort_order.lower() == "asc" else "DESC"

    filters: list[tuple[str, Any]] = [
        ("league_id = ?", league_id),
        ("season = ?", season),
        ("season >= ?", start_season),
        ("season <= ?", end_season),
        ("club_id = ?", club_id),
        ("LOWER(name) LIKE ?", f"%{club_name.lower()}%" if club_name else None),
        ("gross_spend > ?", 0 if positive_spend_only else None),
        ("gross_spend_m >= ?", min_spend_m),
    ]
    rows, total = query_csv_rows(
        "02_domestic_spending_vs_performance.csv",
        filters=filters,
        order_by=f"{order_col} {order_dir}, club_id ASC",
        limit=limit,
        offset=offset,
    )

    stats_json = load_json_output("06_statistical_results.json")
    s6c = stats_json["6C_per_league"]
    agg_leagues = query_csv_agg(
        "02_domestic_spending_vs_performance.csv",
        select_sql=(
            "league_id, league_name, COUNT(*) AS obs, "
            "SUM(CASE WHEN gross_spend > 0 THEN 1 ELSE 0 END) AS pos_obs, "
            "AVG(gross_spend_m) AS avg_spend_m, AVG(ppg) AS avg_ppg"
        ),
        group_by="league_id, league_name",
        order_by="league_id ASC",
    )
    league_summaries = [
        DomesticLeagueSummary(
            league_id=r["league_id"],
            league_name=r["league_name"],
            observations=int(r["obs"]),
            positive_spend_observations=int(r["pos_obs"]),
            avg_gross_spend_m=round(float(r["avg_spend_m"]), 3),
            avg_ppg=round(float(r["avg_ppg"]), 4),
            statistics=s6c.get(r["league_name"], {}),
        )
        for r in agg_leagues
    ]

    return DomesticPerformanceResponse(
        interpretation_note=NON_CAUSAL_NOTE,
        regression_summary={
            "6A_gross_spend": stats_json["6A_domestic_spend_vs_performance"],
            "6B_net_spend": stats_json["6B_net_spend_vs_performance"],
        },
        league_summaries=league_summaries,
        observations=[DomesticClubSeasonRow(**r) for r in rows],
        pagination=_paginate(total, limit, offset, len(rows)),
    )


def get_ucl_performance(
    season: int | None = None,
    league_id: str | None = None,
    is_top5: bool | None = None,
    ucl_stage: str | None = None,
    club_id: int | None = None,
    club_name: str | None = None,
    positive_spend_only: bool = False,
    sort_by: str = "season",
    sort_order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> UCLPerformanceResponse:
    """Return UCL spending vs stage/PPG progression and paired domestic comparison."""
    sort_map = {
        "season": "season",
        "gross_spend_m": "gross_spend_m",
        "ucl_stage_num": "ucl_stage_num",
        "ucl_ppg": "ucl_ppg",
        "ucl_points": "ucl_points",
    }
    order_col = sort_map[sort_by]
    order_dir = "ASC" if sort_order.lower() == "asc" else "DESC"

    filters: list[tuple[str, Any]] = [
        ("season = ?", season),
        ("league_id = ?", league_id),
        ("is_top5 = ?", is_top5),
        ("LOWER(ucl_stage) = ?", ucl_stage.lower() if ucl_stage else None),
        ("club_id = ?", club_id),
        ("LOWER(name) LIKE ?", f"%{club_name.lower()}%" if club_name else None),
        ("gross_spend > ?", 0 if positive_spend_only else None),
    ]
    rows, total = query_csv_rows(
        "03_ucl_spending_vs_performance.csv",
        filters=filters,
        order_by=f"{order_col} {order_dir}, club_id ASC",
        limit=limit,
        offset=offset,
    )
    stage_rows = query_csv_agg(
        "03_ucl_spending_vs_performance.csv",
        select_sql="ucl_stage, MAX(ucl_stage_num) AS ucl_stage_num, COUNT(*) AS count",
        filters=filters,
        group_by="ucl_stage",
        order_by="ucl_stage_num ASC",
    )

    stats_json = load_json_output("06_statistical_results.json")
    comp_json = load_json_output("07_domestic_vs_ucl_comparison.json")

    return UCLPerformanceResponse(
        methodology_note=(
            "Includes all 437 UCL club-seasons matched to clubs metadata (2012-2025), "
            "plus a 2012-2024 complete-Final sensitivity check (n=382). Knockout Playoff "
            "(2024+ intermediate stage) is coded as stage 1.5."
        ),
        statistical_summary=stats_json["6D_ucl_spend_vs_performance"],
        domestic_vs_ucl_comparison=comp_json,
        stage_distribution=[UCLStageCount(**r) for r in stage_rows],
        observations=[UCLClubSeasonRow(**r) for r in rows],
        pagination=_paginate(total, limit, offset, len(rows)),
    )


def get_ucl_paired(
    season: int | None = None,
    league_name: str | None = None,
    club_id: int | None = None,
    club_name: str | None = None,
    positive_spend_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> UCLPairedResponse:
    """Return paired Top-5 domestic + UCL club-season observations."""
    filters: list[tuple[str, Any]] = [
        ("season = ?", season),
        ("LOWER(league_name) = ?", league_name.lower() if league_name else None),
        ("club_id = ?", club_id),
        ("LOWER(name) LIKE ?", f"%{club_name.lower()}%" if club_name else None),
        ("gross_spend > ?", 0 if positive_spend_only else None),
    ]
    rows, total = query_csv_rows(
        "07_domestic_vs_ucl_paired.csv",
        filters=filters,
        order_by="season DESC, ucl_stage_num DESC, club_id ASC",
        limit=limit,
        offset=offset,
    )
    comp_json = load_json_output("07_domestic_vs_ucl_comparison.json")
    return UCLPairedResponse(
        comparison_summary=comp_json,
        observations=[PairedDomesticUCLRow(**r) for r in rows],
        pagination=_paginate(total, limit, offset, len(rows)),
    )


def get_market_value_summary(
    league_id: str | None = None,
    club_name: str | None = None,
    min_signings: int | None = None,
    sort_by: str = "total_est_peak_mv_gain",
    sort_order: str = "desc",
    limit: int = 25,
    offset: int = 0,
) -> MarketValueSummaryResponse:
    """Return Analysis 4 fee-vs-MV stats and club-level estimated market value gain summaries."""
    sort_map = {
        "total_est_peak_mv_gain": "total_est_peak_mv_gain",
        "total_est_latest_mv_gain": "total_est_latest_mv_gain",
        "portfolio_peak_mv_multiple": "portfolio_peak_mv_multiple",
        "portfolio_latest_mv_multiple": "portfolio_latest_mv_multiple",
        "total_spent": "total_spent",
        "num_signings": "num_signings",
    }
    order_col = sort_map[sort_by]
    order_dir = "ASC" if sort_order.lower() == "asc" else "DESC"

    filters: list[tuple[str, Any]] = [
        ("league_id = ?", league_id),
        ("LOWER(club_name) LIKE ?", f"%{club_name.lower()}%" if club_name else None),
        ("num_signings >= ?", min_signings),
    ]
    rows, total = query_csv_rows(
        "05_club_value_gain_summary.csv",
        filters=filters,
        order_by=f"{order_col} {order_dir}, club_id ASC",
        limit=limit,
        offset=offset,
    )
    stats_json = load_json_output("06_statistical_results.json")
    return MarketValueSummaryResponse(
        valuation_disclaimer=VALUATION_DISCLAIMER,
        fee_vs_mv_statistics=stats_json["6E_fee_vs_mv"],
        club_valuation_summaries=[ClubValuationSummaryRow(**r) for r in rows],
        pagination=_paginate(total, limit, offset, len(rows)),
    )


def get_market_value_transfers(
    season: int | None = None,
    league_id: str | None = None,
    is_top5: bool | None = None,
    player_name: str | None = None,
    club_name: str | None = None,
    min_fee: float | None = None,
    sort_by: str = "transfer_fee",
    sort_order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> MarketValueTransfersResponse:
    """Return paginated transfer-level fee vs arrival market value observations."""
    sort_map = {
        "transfer_fee": "transfer_fee",
        "mv_at_transfer": "mv_at_transfer",
        "overpay": "overpay",
        "premium_pct": "premium_pct",
        "fee_to_mv_ratio": "fee_to_mv_ratio",
        "game_season": "game_season",
    }
    order_col = sort_map[sort_by]
    order_dir = "ASC" if sort_order.lower() == "asc" else "DESC"

    filters: list[tuple[str, Any]] = [
        ("game_season = ?", season),
        ("to_league_id = ?", league_id),
        ("is_top5 = ?", is_top5),
        ("LOWER(player_name) LIKE ?", f"%{player_name.lower()}%" if player_name else None),
        ("LOWER(to_club_name) LIKE ?", f"%{club_name.lower()}%" if club_name else None),
        ("transfer_fee >= ?", min_fee),
    ]
    rows, total = query_csv_rows(
        "04_fee_vs_market_value.csv",
        filters=filters,
        order_by=f"{order_col} {order_dir}, player_id ASC",
        limit=limit,
        offset=offset,
    )
    return MarketValueTransfersResponse(
        valuation_disclaimer=VALUATION_DISCLAIMER,
        transfers=[FeeVsMVTransferRow(**r) for r in rows],
        pagination=_paginate(total, limit, offset, len(rows)),
    )


def get_player_value_gains(
    club_id: int | None = None,
    club_name: str | None = None,
    league_id: str | None = None,
    season: int | None = None,
    player_name: str | None = None,
    sort_by: str = "est_peak_mv_gain",
    sort_order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> PlayerValueGainsResponse:
    """Return paginated spell-bounded player estimated market value gains."""
    sort_map = {
        "est_peak_mv_gain": "est_peak_mv_gain",
        "est_latest_mv_gain": "est_latest_mv_gain",
        "peak_mv_to_fee_multiple": "peak_mv_to_fee_multiple",
        "latest_mv_to_fee_multiple": "latest_mv_to_fee_multiple",
        "transfer_fee": "transfer_fee",
        "peak_mv": "peak_mv",
        "game_season": "game_season",
    }
    order_col = sort_map[sort_by]
    order_dir = "ASC" if sort_order.lower() == "asc" else "DESC"

    filters: list[tuple[str, Any]] = [
        ("club_id = ?", club_id),
        ("LOWER(club_name) LIKE ?", f"%{club_name.lower()}%" if club_name else None),
        ("league_id = ?", league_id),
        ("game_season = ?", season),
        ("LOWER(player_name) LIKE ?", f"%{player_name.lower()}%" if player_name else None),
    ]
    rows, total = query_csv_rows(
        "05_player_value_gain.csv",
        filters=filters,
        order_by=f"{order_col} {order_dir}, player_id ASC",
        limit=limit,
        offset=offset,
    )
    return PlayerValueGainsResponse(
        valuation_disclaimer=VALUATION_DISCLAIMER,
        player_gains=[PlayerValueGainRow(**r) for r in rows],
        pagination=_paginate(total, limit, offset, len(rows)),
    )


def get_statistical_results(section: str = "all") -> StatisticalResultsResponse:
    """Return validated statistical battery results (6A-6F and 07 comparison)."""
    stats_json = load_json_output("06_statistical_results.json")
    comp_json = load_json_output("07_domestic_vs_ucl_comparison.json")

    section_map = {
        "6A": "6A_domestic_spend_vs_performance",
        "6B": "6B_net_spend_vs_performance",
        "6C": "6C_per_league",
        "6D": "6D_ucl_spend_vs_performance",
        "6E": "6E_fee_vs_mv",
        "6F": "6F_robustness",
    }
    if section == "all":
        return StatisticalResultsResponse(
            section="all",
            methodology_note=NON_CAUSAL_NOTE,
            statistical_results=stats_json,
            domestic_vs_ucl_comparison=comp_json,
        )
    if section == "07":
        return StatisticalResultsResponse(
            section="07",
            methodology_note=NON_CAUSAL_NOTE,
            statistical_results={},
            domestic_vs_ucl_comparison=comp_json,
        )
    key = section_map[section]
    return StatisticalResultsResponse(
        section=section,
        methodology_note=NON_CAUSAL_NOTE,
        statistical_results={key: stats_json[key]},
        domestic_vs_ucl_comparison=None,
    )

