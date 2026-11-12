export interface PaginationMeta {
  total: number;
  limit: number;
  offset: number;
  returned: number;
}

export interface HealthResponse {
  status: string;
  database_connected: boolean;
  database_file: string;
  outputs_available: boolean;
  output_files_count: number;
  tables: Record<string, number>;
}

export interface OverviewKPIs {
  total_transfers_db: number;
  total_games_db: number;
  total_players_db: number;
  total_clubs_db: number;
  total_valuations_db: number;
  top5_paid_transfers_2012_2025: number;
  top5_total_spending_eur_2012_2025: number;
  top5_domestic_observations: number;
  top5_unique_clubs: number;
  ucl_observations: number;
  fee_vs_mv_sample_size: number;
  spell_bounded_valuations_sample: number;
  analysis_window: string;
}

export interface HistoricalAggregateRow {
  transfer_season: string;
  game_season: number;
  total_transfers: number;
  paid_transfers: number;
  total_spending: number;
  weighted_avg_fee_m: number;
  active_top5_players: number;
  covered_top5_players: number;
  pct_active_players_covered: number;
}

export interface KeyFinding {
  topic: string;
  headline: string;
  metric_name: string;
  metric_value: number;
  sample_size: number;
  interpretation_note: string;
}

export interface OverviewResponse {
  project: string;
  research_question: string;
  methodology_disclaimer: string;
  kpis: OverviewKPIs;
  key_findings: KeyFinding[];
  historical_summary: HistoricalAggregateRow[];
  caveats: string[];
}

export interface HistoricalLeagueRow {
  transfer_season: string;
  game_season: number;
  league_id: string;
  league_name: string;
  total_transfers: number;
  paid_transfers: number;
  total_spending: number;
  total_spending_m: number;
  avg_fee: number | null;
  median_fee: number | null;
  max_fee: number | null;
  pct_recent_cohort: number;
}

export interface CoverageWarning {
  severity: string;
  summary: string;
  implication: string;
}

export interface HistoricalTrendsResponse {
  coverage_warning: CoverageWarning;
  aggregate: HistoricalAggregateRow[];
  by_league: HistoricalLeagueRow[];
  pagination: PaginationMeta;
}

export interface OLSStats {
  n: number;
  clusters: number;
  slope: number;
  intercept?: number;
  r_squared?: number;
  within_r_squared?: number;
  naive_se?: number;
  naive_p?: number;
  cluster_se: number;
  cluster_t: number;
  cluster_p: number;
  cluster_95ci?: [number, number];
}

export interface PerLeagueStats {
  n: number;
  clusters: number;
  pearson_r_ppg: number;
  pearson_p_ppg: number;
  spearman_rho_pos: number;
  spearman_p_pos: number;
  r_squared_ppg: number;
  slope_ppg: number;
  cluster_se: number;
  cluster_p: number;
  cluster_95ci: [number, number];
}

export interface DomesticClubSeasonRow {
  season: number;
  transfer_season: string;
  league_id: string;
  league_name: string;
  club_id: number;
  name: string;
  played: number;
  n_teams: number;
  wins: number;
  draws: number;
  losses: number;
  points: number;
  goals_for: number;
  goals_against: number;
  goal_diff: number;
  league_position: number;
  pos_pct: number;
  ppg: number;
  gross_spend: number;
  gross_income: number;
  net_spend: number;
  gross_spend_m: number;
  gross_income_m: number;
  net_spend_m: number;
  players_bought_paid: number;
  total_arrivals: number;
  players_sold_paid: number;
  spend_per_point: number;
  log_gross_spend_m: number | null;
  asinh_gross_spend_m: number;
}

export interface DomesticLeagueSummary {
  league_id: string;
  league_name: string;
  observations: number;
  positive_spend_observations: number;
  avg_gross_spend_m: number;
  avg_ppg: number;
  statistics: PerLeagueStats;
}

export interface DomesticPerformanceResponse {
  interpretation_note: string;
  regression_summary: {
    '6A_gross_spend': {
      n_spenders: number;
      n_full_sample: number;
      unique_clubs_spenders: number;
      pearson_r_log_vs_ppg: number;
      pearson_p_log_vs_ppg: number;
      pearson_r_log_vs_points: number;
      pearson_p_log_vs_points: number;
      pearson_r_log_vs_pos_pct: number;
      spearman_rho_spend_vs_ppg: number;
      spearman_p_spend_vs_ppg: number;
      spearman_rho_spend_vs_pos_pct: number;
      spearman_p_spend_vs_pos_pct: number;
      ols_log_spend_m_to_ppg: OLSStats;
      ols_log_spend_m_to_points: OLSStats;
      ols_log_spend_m_to_pos_pct: OLSStats;
      full_sample_spearman_rho_ppg: number;
      full_sample_spearman_p_ppg: number;
      full_sample_asinh_ols_ppg: OLSStats;
    };
    '6B_net_spend': {
      n: number;
      pearson_r_ppg: number;
      pearson_p_ppg: number;
      spearman_rho_ppg: number;
      spearman_p_ppg: number;
      ols_net_spend_m_to_ppg: OLSStats;
      ols_net_spend_m_to_points: OLSStats;
    };
  };
  league_summaries: DomesticLeagueSummary[];
  observations: DomesticClubSeasonRow[];
  pagination: PaginationMeta;
}

export interface UCLClubSeasonRow {
  season: number;
  transfer_season: string;
  club_id: number;
  name: string;
  league_id: string;
  league_name: string;
  is_top5: boolean;
  ucl_matches: number;
  ucl_wins: number;
  ucl_draws: number;
  ucl_losses: number;
  ucl_gf: number;
  ucl_ga: number;
  ucl_stage_num: number;
  ucl_stage: string;
  ucl_points: number;
  ucl_ppg: number;
  gross_spend: number;
  gross_income: number;
  net_spend: number;
  gross_spend_m: number;
  net_spend_m: number;
  log_gross_spend_m: number | null;
  asinh_gross_spend_m: number;
}

export interface UCLStageCount {
  ucl_stage: string;
  ucl_stage_num: number;
  count: number;
}

export interface UCLSubsetStats {
  n: number;
  clusters: number;
  stage_pearson_r: number;
  stage_spearman_rho: number;
  stage_spearman_p: number;
  stage_ols: OLSStats;
  ucl_points_pearson_r: number;
  ucl_points_pearson_p: number;
  ucl_ppg_pearson_r: number;
  ucl_ppg_ols: OLSStats;
}

export interface DomesticVsUCLComparison {
  n_paired_total: number;
  n_paired_spenders: number;
  spenders_domestic_ppg_r: number;
  spenders_domestic_ppg_p: number;
  spenders_domestic_points_r: number;
  spenders_ucl_stage_r: number;
  spenders_ucl_stage_p: number;
  spenders_ucl_ppg_r: number;
  spenders_ucl_ppg_p: number;
  spenders_ucl_points_r: number;
  steiger_z_dom_ppg_vs_ucl_stage: number;
  steiger_p_dom_ppg_vs_ucl_stage: number;
  steiger_z_dom_ppg_vs_ucl_ppg: number;
  steiger_p_dom_ppg_vs_ucl_ppg: number;
  full_sample_linear_dom_ppg_r: number;
  full_sample_linear_ucl_stage_r: number;
  recent_2018_2025_n: number;
  recent_2018_2025_dom_ppg_r: number;
  recent_2018_2025_ucl_stage_r: number;
  recent_2018_2025_ucl_ppg_r: number;
}

export interface UCLPerformanceResponse {
  methodology_note: string;
  statistical_summary: {
    all_ucl_spenders: UCLSubsetStats;
    top5_ucl_spenders: UCLSubsetStats;
    all_ucl_pre2025_complete_final: UCLSubsetStats;
  };
  domestic_vs_ucl_comparison: DomesticVsUCLComparison;
  stage_distribution: UCLStageCount[];
  observations: UCLClubSeasonRow[];
  pagination: PaginationMeta;
}

export interface PairedDomesticUCLRow {
  club_id: number;
  season: number;
  name: string;
  league_name: string;
  played: number;
  points: number;
  ppg: number;
  league_position: number;
  pos_pct: number;
  gross_spend: number;
  gross_spend_m: number;
  net_spend_m: number;
  log_gross_spend_m: number | null;
  ucl_matches: number;
  ucl_wins: number;
  ucl_stage_num: number;
  ucl_stage: string;
  ucl_points: number;
  ucl_ppg: number;
}

export interface UCLPairedResponse {
  comparison_summary: DomesticVsUCLComparison;
  observations: PairedDomesticUCLRow[];
  pagination: PaginationMeta;
}

export interface ClubValuationSummaryRow {
  club_id: number;
  club_name: string;
  league_id: string;
  league_name: string;
  num_signings: number;
  total_spent: number;
  total_mv_at_arrival: number;
  total_peak_mv: number;
  total_latest_mv: number;
  avg_peak_mv_multiple: number;
  median_peak_mv_multiple: number;
  total_est_peak_mv_gain: number;
  total_est_latest_mv_gain: number;
  portfolio_peak_mv_multiple: number;
  portfolio_latest_mv_multiple: number;
}

export interface FeeVsMVStatistics {
  n: number;
  pearson_r_log_log: number;
  pearson_p: number;
  spearman_rho: number;
  spearman_p: number;
  ols_log_mv_to_log_fee: OLSStats;
  median_fee_to_mv_ratio: number;
  mean_fee_to_mv_ratio: number;
  pct_overpay: number;
  pct_exact_match: number;
  pct_underpay: number;
}

export interface MarketValueSummaryResponse {
  valuation_disclaimer: string;
  fee_vs_mv_statistics: FeeVsMVStatistics;
  club_valuation_summaries: ClubValuationSummaryRow[];
  pagination: PaginationMeta;
}

export interface FeeVsMVTransferRow {
  player_id: number;
  player_name: string;
  transfer_date: string | null;
  transfer_season: string;
  game_season: number;
  from_club_name: string | null;
  to_club_name: string;
  to_club_id: number;
  to_league_id: string | null;
  league_name: string;
  is_top5: boolean;
  transfer_fee: number;
  mv_at_transfer: number;
  fee_to_mv_ratio: number;
  premium_pct: number;
  overpay: number;
  log_fee: number;
  log_mv: number;
}

export interface MarketValueTransfersResponse {
  valuation_disclaimer: string;
  transfers: FeeVsMVTransferRow[];
  pagination: PaginationMeta;
}

export interface PlayerValueGainRow {
  player_id: number;
  player_name: string;
  transfer_date: string;
  next_transfer_date: string | null;
  transfer_season: string;
  game_season: number;
  club_id: number;
  club_name: string;
  league_id: string;
  transfer_fee: number;
  mv_at_arrival: number;
  peak_mv: number;
  min_mv: number;
  last_mv_at_club: number;
  valuation_count: number;
  last_valuation_date: string;
  est_peak_mv_gain: number;
  est_peak_mv_gain_pct: number;
  peak_mv_to_fee_multiple: number;
  est_latest_mv_gain: number;
  latest_mv_to_fee_multiple: number;
}

export interface PlayerValueGainsResponse {
  valuation_disclaimer: string;
  player_gains: PlayerValueGainRow[];
  pagination: PaginationMeta;
}

export interface RobustnessResults {
  heteroscedasticity_test_p: number;
  heteroscedasticity_detected: boolean;
  avg_obs_per_club: number;
  max_obs_per_club: number;
  unique_clubs: number;
  season_fixed_effects_ppg: OLSStats;
  club_fixed_effects_ppg: OLSStats;
  two_way_fixed_effects_ppg: OLSStats;
  club_averaged_cross_section: {
    n_clubs: number;
    pearson_r: number;
    r_squared: number;
    slope: number;
    p_value: number;
    ci_95: [number, number];
  };
  subperiod_2018_2025: OLSStats;
  subperiod_2022_2025: OLSStats;
  linear_spend_ols_ppg: OLSStats;
}

export interface StatisticalResultsResponse {
  section: string;
  methodology_note: string;
  statistical_results: {
    '6A_domestic_spend_vs_performance'?: DomesticPerformanceResponse['regression_summary']['6A_gross_spend'];
    '6B_net_spend_vs_performance'?: DomesticPerformanceResponse['regression_summary']['6B_net_spend'];
    '6C_per_league'?: Record<string, PerLeagueStats>;
    '6D_ucl_spend_vs_performance'?: UCLPerformanceResponse['statistical_summary'];
    '6E_fee_vs_mv'?: FeeVsMVStatistics;
    '6F_robustness'?: RobustnessResults;
  };
  domestic_vs_ucl_comparison: DomesticVsUCLComparison | null;
}

export type NavSectionId =
  | 'overview'
  | 'market'
  | 'domestic'
  | 'ucl'
  | 'value'
  | 'statistics'
  | 'methodology'
  | 'players'
  | 'player-compare'
  | 'calculator';

// ---------------------------------------------------------------------------
// Phase 4.1 — Player Intelligence, Cross-Season Comparison & Calculator
// ---------------------------------------------------------------------------

export interface PlayerSearchItem {
  player_id: number;
  name: string;
  country_of_citizenship: string | null;
  date_of_birth: string | null;
  age: number | null;
  position: string | null;
  sub_position: string | null;
  current_club_id: number | null;
  current_club_name: string | null;
  current_club_domestic_competition_id: string | null;
  market_value_in_eur: number | null;
  highest_market_value_in_eur: number | null;
  last_season: number | null;
  appearance_count: number;
  total_goals: number;
  total_assists: number;
  image_url: string | null;
}

export interface PlayerSearchResponse {
  players: PlayerSearchItem[];
  available_positions: string[];
  pagination: PaginationMeta;
}

export interface PlayerProfile {
  player_id: number;
  name: string;
  first_name: string | null;
  last_name: string | null;
  country_of_citizenship: string | null;
  country_of_birth: string | null;
  city_of_birth: string | null;
  date_of_birth: string | null;
  age: number | null;
  position: string | null;
  sub_position: string | null;
  foot: string | null;
  height_in_cm: number | null;
  contract_expiration_date: string | null;
  current_club_id: number | null;
  current_club_name: string | null;
  current_club_domestic_competition_id: string | null;
  market_value_in_eur: number | null;
  highest_market_value_in_eur: number | null;
  latest_valuation_in_eur: number | null;
  latest_valuation_date: string | null;
  last_season: number | null;
  image_url: string | null;
  url: string | null;
}

export interface PlayerCareerSummary {
  has_appearance_data: boolean;
  has_valuation_data: boolean;
  has_transfer_data: boolean;
  appearances: number;
  goals: number;
  assists: number;
  minutes_played: number;
  yellow_cards: number;
  red_cards: number;
  goals_per_appearance: number | null;
  assists_per_appearance: number | null;
  seasons_with_appearances: number;
  first_appearance_season: number | null;
  last_appearance_season: number | null;
  unavailable_metrics_note: string;
}

export interface PlayerSeasonStatsRow {
  season: number;
  season_label: string;
  appearances: number;
  goals: number;
  assists: number;
  minutes_played: number;
  yellow_cards: number;
  red_cards: number;
  goals_per_appearance: number | null;
  assists_per_appearance: number | null;
  clubs: string[];
  competitions: string[];
}

export interface PlayerValuationPoint {
  date: string;
  market_value_in_eur: number;
  current_club_id: number | null;
  current_club_name: string | null;
  competition_id: string | null;
}

export interface PlayerTransferRow {
  transfer_date: string | null;
  transfer_season: string | null;
  game_season: number | null;
  from_club_id: number | null;
  from_club_name: string | null;
  to_club_id: number | null;
  to_club_name: string | null;
  transfer_fee: number | null;
  fee_status: 'paid' | 'free_or_loan' | 'undisclosed' | string;
  market_value_in_eur: number | null;
  is_future_scheduled: boolean;
}

export interface PlayerClubSpellRow {
  club_id: number | null;
  club_name: string;
  competition_id: string | null;
  first_season: number | null;
  last_season: number | null;
  season_span: string;
  appearances: number;
  goals: number;
  assists: number;
  minutes_played: number;
  source: string;
}

export interface PlayerDetailResponse {
  profile: PlayerProfile;
  career_summary: PlayerCareerSummary;
  season_stats: PlayerSeasonStatsRow[];
  market_value_history: PlayerValuationPoint[];
  transfer_history: PlayerTransferRow[];
  club_timeline: PlayerClubSpellRow[];
  valuation_disclaimer: string;
}

export interface PlayerComparisonMetrics {
  scope_type: 'season' | 'career' | string;
  selected_season: number | null;
  selected_season_label: string;
  has_appearance_data: boolean;
  appearances: number;
  goals: number;
  assists: number;
  minutes_played: number;
  yellow_cards: number;
  red_cards: number;
  goals_per_appearance: number | null;
  assists_per_appearance: number | null;
  clubs_in_scope: string[];
  competitions_in_scope: string[];
  market_value_in_eur: number | null;
  market_value_date: string | null;
  market_value_boundary_note: string;
  season_transfer_fee_eur: number | null;
  season_transfer_fee_status: string;
  season_transfer_description: string | null;
  latest_paid_transfer_fee_eur: number | null;
  latest_paid_transfer_season: string | null;
}

export interface PlayerComparisonSide {
  profile: PlayerProfile;
  available_seasons: number[];
  metrics: PlayerComparisonMetrics;
}

export interface PlayerComparisonRadarAxis {
  metric: string;
  unit: string;
  player_a_raw: number;
  player_b_raw: number;
  player_a_score: number;
  player_b_score: number;
}

export interface PlayerComparisonResponse {
  comparison_mode:
    | 'same_season'
    | 'different_seasons'
    | 'same_player_cross_season'
    | 'career'
    | string;
  season_boundary_definition: string;
  player_a: PlayerComparisonSide;
  player_b: PlayerComparisonSide;
  radar_supported: boolean;
  radar_unavailable_reason: string | null;
  radar_axes: PlayerComparisonRadarAxis[];
  unavailable_metrics_note: string;
  valuation_disclaimer: string;
}

export interface TransferSpellCalculatorRow {
  spell_index: number;
  transfer_date: string | null;
  next_transfer_date: string | null;
  transfer_season: string | null;
  game_season: number | null;
  from_club_name: string | null;
  to_club_id: number | null;
  to_club_name: string | null;
  to_league_id: string | null;
  transfer_fee: number | null;
  fee_status: 'paid' | 'free_or_loan' | 'undisclosed' | string;
  mv_at_arrival: number | null;
  mv_at_arrival_source: string | null;
  peak_mv: number | null;
  latest_mv_at_club: number | null;
  valuation_count: number;
  last_valuation_date: string | null;
  est_peak_mv_gain: number | null;
  est_peak_mv_gain_pct: number | null;
  peak_mv_to_fee_multiple: number | null;
  est_latest_mv_gain: number | null;
  latest_mv_to_fee_multiple: number | null;
}

export interface PlayerTransferSpellsResponse {
  profile: PlayerProfile;
  spells: TransferSpellCalculatorRow[];
  methodology_note: string;
  valuation_disclaimer: string;
}
