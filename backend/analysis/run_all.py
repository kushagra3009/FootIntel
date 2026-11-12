"""
FootIntel Phase 2 — Statistical Analysis Engine

Analyses:
1. Historical transfer spending trends
2. Domestic league spending vs sporting performance (Top 5)
3. UCL spending vs performance
4. Transfer fee vs estimated market value
5. Club-level estimated value gain analysis
6. Full statistical battery (Pearson, Spearman, regression, R², p-values, CI)
7. Domestic vs UCL comparison

All outputs are saved to data/processed/analysis_outputs/ and charts/.
"""

import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

import json
import numpy as np
import pandas as pd
from scipy import stats
from pathlib import Path

from analysis.utils import (
    get_connection, ensure_dirs, OUTPUT_DIR, CHARTS_DIR,
    TOP5_LEAGUES, transfer_season_to_game_season, game_season_to_transfer_season,
)


def run_analysis_1_historical_trends(con) -> pd.DataFrame:
    """Analysis 1: Historical transfer spending trends across Top 5 leagues."""
    print("\n" + "=" * 70)
    print("ANALYSIS 1: Historical Transfer Spending Trends")
    print("=" * 70)

    df = con.execute("""
        SELECT
            t.transfer_season,
            c.domestic_competition_id AS league_id,
            COUNT(*) AS total_transfers,
            SUM(CASE WHEN t.transfer_fee > 0 THEN 1 ELSE 0 END) AS paid_transfers,
            SUM(CASE WHEN t.transfer_fee > 0 THEN t.transfer_fee ELSE 0 END) AS total_spending,
            AVG(CASE WHEN t.transfer_fee > 0 THEN t.transfer_fee ELSE NULL END) AS avg_fee,
            MEDIAN(CASE WHEN t.transfer_fee > 0 THEN t.transfer_fee ELSE NULL END) AS median_fee,
            MAX(t.transfer_fee) AS max_fee
        FROM transfers t
        JOIN clubs c ON t.to_club_id = c.club_id
        WHERE c.domestic_competition_id IN ('GB1','ES1','IT1','L1','FR1')
          AND t.transfer_season IS NOT NULL
        GROUP BY t.transfer_season, c.domestic_competition_id
        ORDER BY t.transfer_season, c.domestic_competition_id
    """).df()

    # Add game season integer for sorting
    df["game_season"] = df["transfer_season"].apply(transfer_season_to_game_season)
    df["league_name"] = df["league_id"].map(TOP5_LEAGUES)

    # Filter to reliable data range (2012+ has consistent game data)
    df = df[df["game_season"].between(2012, 2025)].copy()
    df = df.sort_values(["game_season", "league_id"]).reset_index(drop=True)

    # Aggregate across all Top 5 leagues per season
    agg = df.groupby(["transfer_season", "game_season"]).agg(
        total_transfers=("total_transfers", "sum"),
        paid_transfers=("paid_transfers", "sum"),
        total_spending=("total_spending", "sum"),
        avg_fee=("avg_fee", "mean"),
    ).reset_index().sort_values("game_season")

    print(f"\nSeasons covered: {df['game_season'].min()}-{df['game_season'].max()}")
    print(f"Rows (league-season): {len(df)}")
    print(f"\nAggregate Top 5 spending by season:")
    for _, r in agg.iterrows():
        print(f"  {r['transfer_season']}: €{r['total_spending']/1e9:.2f}B "
              f"({r['paid_transfers']:.0f} paid transfers, "
              f"avg €{r['avg_fee']/1e6:.1f}M)")

    df.to_csv(OUTPUT_DIR / "01_historical_trends_by_league.csv", index=False)
    agg.to_csv(OUTPUT_DIR / "01_historical_trends_aggregate.csv", index=False)
    print(f"\n✓ Saved to {OUTPUT_DIR / '01_historical_trends_by_league.csv'}")

    return df


def run_analysis_2_domestic_spending_vs_performance(con) -> pd.DataFrame:
    """Analysis 2: Domestic league spending vs sporting performance."""
    print("\n" + "=" * 70)
    print("ANALYSIS 2: Domestic Spending vs Performance (Top 5 Leagues)")
    print("=" * 70)

    # Step 1: Build league standings from game results
    standings = con.execute("""
        WITH home AS (
            SELECT season, competition_id, home_club_id AS club_id,
                COUNT(*) AS mp,
                SUM(CASE WHEN home_club_goals > away_club_goals THEN 3
                         WHEN home_club_goals = away_club_goals THEN 1 ELSE 0 END) AS pts,
                SUM(CASE WHEN home_club_goals > away_club_goals THEN 1 ELSE 0 END) AS w,
                SUM(CASE WHEN home_club_goals = away_club_goals THEN 1 ELSE 0 END) AS d,
                SUM(CASE WHEN home_club_goals < away_club_goals THEN 1 ELSE 0 END) AS l,
                SUM(home_club_goals) AS gf, SUM(away_club_goals) AS ga
            FROM games
            WHERE competition_id IN ('GB1','ES1','IT1','L1','FR1')
              AND home_club_goals IS NOT NULL
            GROUP BY season, competition_id, home_club_id
        ),
        away AS (
            SELECT season, competition_id, away_club_id AS club_id,
                COUNT(*) AS mp,
                SUM(CASE WHEN away_club_goals > home_club_goals THEN 3
                         WHEN away_club_goals = home_club_goals THEN 1 ELSE 0 END) AS pts,
                SUM(CASE WHEN away_club_goals > home_club_goals THEN 1 ELSE 0 END) AS w,
                SUM(CASE WHEN away_club_goals = home_club_goals THEN 1 ELSE 0 END) AS d,
                SUM(CASE WHEN away_club_goals < home_club_goals THEN 1 ELSE 0 END) AS l,
                SUM(away_club_goals) AS gf, SUM(home_club_goals) AS ga
            FROM games
            WHERE competition_id IN ('GB1','ES1','IT1','L1','FR1')
              AND away_club_goals IS NOT NULL
            GROUP BY season, competition_id, away_club_id
        ),
        combined AS (
            SELECT
                COALESCE(h.season, a.season) AS season,
                COALESCE(h.competition_id, a.competition_id) AS league_id,
                COALESCE(h.club_id, a.club_id) AS club_id,
                COALESCE(h.mp,0)+COALESCE(a.mp,0) AS played,
                COALESCE(h.pts,0)+COALESCE(a.pts,0) AS points,
                COALESCE(h.w,0)+COALESCE(a.w,0) AS wins,
                COALESCE(h.d,0)+COALESCE(a.d,0) AS draws,
                COALESCE(h.l,0)+COALESCE(a.l,0) AS losses,
                COALESCE(h.gf,0)+COALESCE(a.gf,0) AS goals_for,
                COALESCE(h.ga,0)+COALESCE(a.ga,0) AS goals_against
            FROM home h
            FULL OUTER JOIN away a
                ON h.season = a.season AND h.competition_id = a.competition_id AND h.club_id = a.club_id
        )
        SELECT *,
            (goals_for - goals_against) AS goal_diff,
            RANK() OVER (PARTITION BY season, league_id ORDER BY points DESC, (goals_for - goals_against) DESC) AS league_position
        FROM combined
        WHERE played >= 10
        ORDER BY season, league_id, league_position
    """).df()

    print(f"Standings rows: {len(standings)}")
    print(f"Seasons: {standings['season'].min()}-{standings['season'].max()}")

    # Step 2: Build club spending per season (transfers INTO the club)
    # transfer_season '22/23' aligns to games.season 2022
    spending = con.execute("""
        SELECT
            t.transfer_season,
            t.to_club_id AS club_id,
            SUM(CASE WHEN t.transfer_fee > 0 THEN t.transfer_fee ELSE 0 END) AS gross_spend,
            SUM(CASE WHEN t.transfer_fee > 0 THEN 1 ELSE 0 END) AS players_bought_paid,
            COUNT(*) AS total_arrivals
        FROM transfers t
        WHERE t.transfer_season IS NOT NULL
        GROUP BY t.transfer_season, t.to_club_id
    """).df()

    spending["game_season"] = spending["transfer_season"].apply(transfer_season_to_game_season)

    # Step 3: Also get sales (transfers FROM the club)
    sales = con.execute("""
        SELECT
            t.transfer_season,
            t.from_club_id AS club_id,
            SUM(CASE WHEN t.transfer_fee > 0 THEN t.transfer_fee ELSE 0 END) AS gross_income,
            SUM(CASE WHEN t.transfer_fee > 0 THEN 1 ELSE 0 END) AS players_sold_paid
        FROM transfers t
        WHERE t.transfer_season IS NOT NULL
        GROUP BY t.transfer_season, t.from_club_id
    """).df()

    sales["game_season"] = sales["transfer_season"].apply(transfer_season_to_game_season)

    # Step 4: Merge standings + spending + sales
    # Join on club_id + season, being careful about types
    merged = standings.merge(
        spending[["club_id", "game_season", "gross_spend", "players_bought_paid", "total_arrivals"]],
        left_on=["club_id", "season"],
        right_on=["club_id", "game_season"],
        how="left"
    )
    merged = merged.merge(
        sales[["club_id", "game_season", "gross_income", "players_sold_paid"]],
        left_on=["club_id", "season"],
        right_on=["club_id", "game_season"],
        how="left",
        suffixes=("", "_sales")
    )

    # Fill NaN spending with 0 (clubs that didn't spend)
    merged["gross_spend"] = merged["gross_spend"].fillna(0)
    merged["gross_income"] = merged["gross_income"].fillna(0)
    merged["net_spend"] = merged["gross_spend"] - merged["gross_income"]
    merged["players_bought_paid"] = merged["players_bought_paid"].fillna(0)

    # Get club names
    clubs = con.execute("SELECT club_id, name FROM clubs").df()
    merged = merged.merge(clubs, on="club_id", how="left")

    # Add league name
    merged["league_name"] = merged["league_id"].map(TOP5_LEAGUES)

    # Filter to seasons with game data (2012-2025)
    merged = merged[merged["season"].between(2012, 2025)].copy()

    # Add transfer_season string
    merged["transfer_season"] = merged["season"].apply(game_season_to_transfer_season)

    # Points per game for normalization
    merged["ppg"] = merged["points"] / merged["played"]

    # Spend per point
    merged["spend_per_point"] = np.where(
        merged["points"] > 0,
        merged["gross_spend"] / merged["points"],
        np.nan
    )

    # Log spending for regression (add 1 to handle zeros)
    merged["log_gross_spend"] = np.log1p(merged["gross_spend"])

    print(f"\nMerged dataset: {len(merged)} club-season observations")
    print(f"  With spending > 0: {(merged['gross_spend'] > 0).sum()}")
    print(f"  Unique clubs: {merged['club_id'].nunique()}")

    # Drop helper columns
    cols_to_keep = [
        "season", "transfer_season", "league_id", "league_name", "club_id", "name",
        "played", "wins", "draws", "losses", "points", "goals_for", "goals_against",
        "goal_diff", "league_position", "ppg",
        "gross_spend", "gross_income", "net_spend",
        "players_bought_paid", "total_arrivals",
        "spend_per_point", "log_gross_spend"
    ]
    merged = merged[[c for c in cols_to_keep if c in merged.columns]].copy()

    merged.to_csv(OUTPUT_DIR / "02_domestic_spending_vs_performance.csv", index=False)
    print(f"✓ Saved to {OUTPUT_DIR / '02_domestic_spending_vs_performance.csv'}")

    return merged


def run_analysis_3_ucl_spending_vs_performance(con, domestic_df: pd.DataFrame) -> pd.DataFrame:
    """Analysis 3: UCL spending vs performance."""
    print("\n" + "=" * 70)
    print("ANALYSIS 3: UCL Spending vs Performance")
    print("=" * 70)

    # Get UCL participation and results
    ucl = con.execute("""
        WITH ucl_games AS (
            SELECT
                season,
                home_club_id AS club_id,
                home_club_goals AS gf,
                away_club_goals AS ga,
                CASE WHEN home_club_goals > away_club_goals THEN 'W'
                     WHEN home_club_goals = away_club_goals THEN 'D' ELSE 'L' END AS result,
                round
            FROM games WHERE competition_id = 'CL' AND home_club_goals IS NOT NULL
            UNION ALL
            SELECT
                season,
                away_club_id AS club_id,
                away_club_goals AS gf,
                home_club_goals AS ga,
                CASE WHEN away_club_goals > home_club_goals THEN 'W'
                     WHEN away_club_goals = home_club_goals THEN 'D' ELSE 'L' END AS result,
                round
            FROM games WHERE competition_id = 'CL' AND away_club_goals IS NOT NULL
        )
        SELECT
            season,
            club_id,
            COUNT(*) AS ucl_matches,
            SUM(CASE WHEN result = 'W' THEN 1 ELSE 0 END) AS ucl_wins,
            SUM(CASE WHEN result = 'D' THEN 1 ELSE 0 END) AS ucl_draws,
            SUM(CASE WHEN result = 'L' THEN 1 ELSE 0 END) AS ucl_losses,
            SUM(gf) AS ucl_gf,
            SUM(ga) AS ucl_ga
        FROM ucl_games
        GROUP BY season, club_id
    """).df()

    # Derive UCL "stage reached" from the latest round played
    stage_order = {
        "Group Stage": 1, "Group A": 1, "Group B": 1, "Group C": 1,
        "Group D": 1, "Group E": 1, "Group F": 1, "Group G": 1, "Group H": 1,
        "last 16 1st leg": 2, "last 16 2nd leg": 2,
        "Last 16 1st Leg": 2, "Last 16 2nd Leg": 2,
        "intermediate stage 1st leg": 2, "intermediate stage 2nd leg": 2,
        "Quarter-Finals": 3, "Quarter-Finals 1st leg": 3, "Quarter-Finals 2nd leg": 3,
        "Quarter-Finals 1st Leg": 3, "Quarter-Finals 2nd Leg": 3,
        "Semi-Finals": 4, "Semi-Finals 1st Leg": 4, "Semi-Finals 2nd Leg": 4,
        "Semi-Finals 1st leg": 4, "Semi-Finals 2nd Leg": 4,
        "Final": 5,
    }

    stage_labels = {1: "Group Stage", 2: "Round of 16", 3: "Quarter-Finals", 4: "Semi-Finals", 5: "Final"}

    # Get furthest round per club-season
    rounds = con.execute("""
        SELECT DISTINCT season, home_club_id AS club_id, round FROM games WHERE competition_id = 'CL'
        UNION
        SELECT DISTINCT season, away_club_id AS club_id, round FROM games WHERE competition_id = 'CL'
    """).df()

    rounds["stage_num"] = rounds["round"].map(stage_order).fillna(0)
    furthest = rounds.groupby(["season", "club_id"])["stage_num"].max().reset_index()
    furthest.rename(columns={"stage_num": "ucl_stage_num"}, inplace=True)
    furthest["ucl_stage"] = furthest["ucl_stage_num"].map(stage_labels).fillna("Unknown")

    ucl = ucl.merge(furthest, on=["season", "club_id"], how="left")

    # UCL points proxy (3 for win, 1 for draw) — useful for group stage comparison
    ucl["ucl_points"] = ucl["ucl_wins"] * 3 + ucl["ucl_draws"]

    # Merge with spending data from domestic_df (club_id + season)
    # Only keep spending columns
    spend_cols = domestic_df[["club_id", "season", "gross_spend", "net_spend", "league_id", "league_name", "name"]].drop_duplicates()
    ucl = ucl.merge(spend_cols, on=["club_id", "season"], how="left")

    # Filter to known clubs (in our clubs table)
    ucl = ucl.dropna(subset=["name"])

    # Add transfer_season
    ucl["transfer_season"] = ucl["season"].apply(game_season_to_transfer_season)
    ucl["log_gross_spend"] = np.log1p(ucl["gross_spend"])

    print(f"\nUCL dataset: {len(ucl)} club-season observations")
    print(f"  Seasons: {ucl['season'].min()}-{ucl['season'].max()}")
    print(f"  Unique clubs: {ucl['club_id'].nunique()}")
    print(f"\n  Stage distribution:")
    print(ucl["ucl_stage"].value_counts().to_string())

    ucl.to_csv(OUTPUT_DIR / "03_ucl_spending_vs_performance.csv", index=False)
    print(f"\n✓ Saved to {OUTPUT_DIR / '03_ucl_spending_vs_performance.csv'}")

    return ucl


def run_analysis_4_fee_vs_market_value(con) -> pd.DataFrame:
    """Analysis 4: Transfer fee vs estimated market value at time of transfer."""
    print("\n" + "=" * 70)
    print("ANALYSIS 4: Transfer Fee vs Market Value")
    print("=" * 70)

    df = con.execute("""
        SELECT
            t.player_id,
            t.player_name,
            t.transfer_date,
            t.transfer_season,
            t.from_club_name,
            t.to_club_name,
            t.transfer_fee,
            t.market_value_in_eur AS mv_at_transfer,
            t.to_club_id,
            c.domestic_competition_id AS to_league_id
        FROM transfers t
        LEFT JOIN clubs c ON t.to_club_id = c.club_id
        WHERE t.transfer_fee > 0
          AND t.market_value_in_eur > 0
          AND t.transfer_season IS NOT NULL
    """).df()

    df["game_season"] = df["transfer_season"].apply(transfer_season_to_game_season)
    df = df[df["game_season"].between(2012, 2025)].copy()

    # Fee-to-value ratio
    df["fee_to_mv_ratio"] = df["transfer_fee"] / df["mv_at_transfer"]
    df["premium_pct"] = (df["transfer_fee"] - df["mv_at_transfer"]) / df["mv_at_transfer"] * 100
    df["overpay"] = df["transfer_fee"] - df["mv_at_transfer"]

    # Log versions for regression
    df["log_fee"] = np.log(df["transfer_fee"])
    df["log_mv"] = np.log(df["mv_at_transfer"])

    # Is Top 5 league?
    df["is_top5"] = df["to_league_id"].isin(TOP5_LEAGUES.keys())
    df["league_name"] = df["to_league_id"].map(TOP5_LEAGUES).fillna("Other")

    print(f"\nTransfers with fee AND market value: {len(df)}")
    print(f"  Seasons: {df['game_season'].min()}-{df['game_season'].max()}")
    print(f"\nFee vs MV summary:")
    print(f"  Mean fee:       €{df['transfer_fee'].mean()/1e6:.2f}M")
    print(f"  Mean MV:        €{df['mv_at_transfer'].mean()/1e6:.2f}M")
    print(f"  Mean ratio:     {df['fee_to_mv_ratio'].mean():.2f}")
    print(f"  Median ratio:   {df['fee_to_mv_ratio'].median():.2f}")
    print(f"  % Overpaying:   {(df['fee_to_mv_ratio'] > 1).mean()*100:.1f}%")
    print(f"  % Underpaying:  {(df['fee_to_mv_ratio'] < 1).mean()*100:.1f}%")

    df.to_csv(OUTPUT_DIR / "04_fee_vs_market_value.csv", index=False)
    print(f"\n✓ Saved to {OUTPUT_DIR / '04_fee_vs_market_value.csv'}")

    return df


def run_analysis_5_club_value_gain(con) -> pd.DataFrame:
    """Analysis 5: Club-level estimated value gain analysis.
    
    Compares transfer fees paid vs. market value changes for bought players.
    Uses player_valuations table to track value evolution post-transfer.
    """
    print("\n" + "=" * 70)
    print("ANALYSIS 5: Club-Level Value Gain Analysis")
    print("=" * 70)

    # For each transfer with a fee, find the player's market value:
    # 1) At time of arrival (from transfers.market_value_in_eur)
    # 2) Peak value while at the buying club (from player_valuations)
    # 3) Value when they left (next transfer's market_value_in_eur or latest valuation)

    # Get all paid transfers into Top 5 league clubs
    transfers = con.execute("""
        SELECT
            t.player_id,
            t.player_name,
            t.transfer_date,
            t.transfer_season,
            t.to_club_id AS club_id,
            t.to_club_name AS club_name,
            t.transfer_fee,
            t.market_value_in_eur AS mv_at_arrival,
            c.domestic_competition_id AS league_id
        FROM transfers t
        JOIN clubs c ON t.to_club_id = c.club_id
        WHERE t.transfer_fee > 0
          AND t.market_value_in_eur > 0
          AND c.domestic_competition_id IN ('GB1','ES1','IT1','L1','FR1')
          AND t.transfer_date IS NOT NULL
        ORDER BY t.player_id, t.transfer_date
    """).df()

    transfers["game_season"] = transfers["transfer_season"].apply(transfer_season_to_game_season)
    transfers = transfers[transfers["game_season"].between(2012, 2024)].copy()

    # For each transfer, find peak valuation while at the club
    # We approximate "while at club" by checking player_valuations where current_club_id matches
    peak_vals = con.execute("""
        SELECT
            player_id,
            current_club_id AS club_id,
            MAX(market_value_in_eur) AS peak_mv,
            MIN(market_value_in_eur) AS min_mv,
            COUNT(*) AS valuation_count,
            MAX(date) AS last_valuation_date
        FROM player_valuations
        GROUP BY player_id, current_club_id
    """).df()

    # Merge
    merged = transfers.merge(
        peak_vals,
        on=["player_id", "club_id"],
        how="left"
    )

    # Value gain = peak market value - fee paid
    merged = merged.dropna(subset=["peak_mv"])
    merged["value_gain"] = merged["peak_mv"] - merged["transfer_fee"]
    merged["value_gain_pct"] = (merged["peak_mv"] - merged["transfer_fee"]) / merged["transfer_fee"] * 100
    merged["roi"] = merged["peak_mv"] / merged["transfer_fee"]

    print(f"\nTransfers with post-arrival valuations: {len(merged)}")
    print(f"  Unique clubs: {merged['club_id'].nunique()}")

    # Aggregate by club
    club_agg = merged.groupby(["club_id", "club_name", "league_id"]).agg(
        total_spent=("transfer_fee", "sum"),
        total_peak_value=("peak_mv", "sum"),
        num_signings=("player_id", "count"),
        avg_roi=("roi", "mean"),
        median_roi=("roi", "median"),
        total_value_gain=("value_gain", "sum"),
    ).reset_index()

    club_agg["portfolio_roi"] = club_agg["total_peak_value"] / club_agg["total_spent"]
    club_agg["league_name"] = club_agg["league_id"].map(TOP5_LEAGUES)
    club_agg = club_agg.sort_values("total_value_gain", ascending=False)

    print(f"\n  Top 10 clubs by total value gain:")
    for _, r in club_agg.head(10).iterrows():
        print(f"    {r['club_name']:25s} spent €{r['total_spent']/1e6:.0f}M  "
              f"peak value €{r['total_peak_value']/1e6:.0f}M  "
              f"ROI {r['portfolio_roi']:.2f}x  ({r['num_signings']} signings)")

    merged.to_csv(OUTPUT_DIR / "05_player_value_gain.csv", index=False)
    club_agg.to_csv(OUTPUT_DIR / "05_club_value_gain_summary.csv", index=False)
    print(f"\n✓ Saved to {OUTPUT_DIR / '05_*.csv'}")

    return merged


def run_analysis_6_statistical_tests(domestic_df: pd.DataFrame, ucl_df: pd.DataFrame,
                                      fee_mv_df: pd.DataFrame) -> dict:
    """Analysis 6: Comprehensive statistical battery."""
    print("\n" + "=" * 70)
    print("ANALYSIS 6: Statistical Tests")
    print("=" * 70)

    results = {}

    # ─── 6A: Domestic spending vs league position ───
    print("\n--- 6A: Gross Spending vs League Position (Domestic) ---")
    # Use all club-season observations with positive spending
    dom = domestic_df[domestic_df["gross_spend"] > 0].copy()

    # Spearman (position is ordinal, lower = better)
    # We invert position so higher = better for intuitive correlation
    dom["inv_position"] = dom["league_position"].max() + 1 - dom["league_position"]

    r_pearson, p_pearson = stats.pearsonr(dom["log_gross_spend"], dom["inv_position"])
    r_spearman, p_spearman = stats.spearmanr(dom["gross_spend"], dom["inv_position"])

    # OLS regression: points ~ log(gross_spend)
    from scipy.stats import linregress
    slope, intercept, r_value, p_value, std_err = linregress(dom["log_gross_spend"], dom["points"])
    r_sq = r_value ** 2

    # 95% CI for slope
    n = len(dom)
    t_crit = stats.t.ppf(0.975, n - 2)
    ci_lower = slope - t_crit * std_err
    ci_upper = slope + t_crit * std_err

    results["6A_domestic_spend_vs_position"] = {
        "n": int(n),
        "pearson_r": round(r_pearson, 4),
        "pearson_p": float(p_pearson),
        "spearman_rho": round(r_spearman, 4),
        "spearman_p": float(p_spearman),
        "regression_slope": round(slope, 4),
        "regression_intercept": round(intercept, 4),
        "regression_r_squared": round(r_sq, 4),
        "regression_p_value": float(p_value),
        "slope_95ci": [round(ci_lower, 4), round(ci_upper, 4)],
        "std_error": round(std_err, 4),
        "description": "log(gross_spend) vs points. Spearman uses gross_spend vs inverted position."
    }

    print(f"  n = {n}")
    print(f"  Pearson r (log_spend vs points) = {r_pearson:.4f}, p = {p_pearson:.2e}")
    print(f"  Spearman ρ (spend vs inv_position) = {r_spearman:.4f}, p = {p_spearman:.2e}")
    print(f"  OLS: points = {slope:.4f} * log_spend + {intercept:.4f}")
    print(f"  R² = {r_sq:.4f}, p = {p_value:.2e}")
    print(f"  95% CI for slope: [{ci_lower:.4f}, {ci_upper:.4f}]")

    # ─── 6B: Net spend vs league position ───
    print("\n--- 6B: Net Spend vs League Position ---")
    dom_net = dom[dom["net_spend"].notna()].copy()

    r_p, p_p = stats.pearsonr(dom_net["net_spend"], dom_net["points"])
    r_s, p_s = stats.spearmanr(dom_net["net_spend"], dom_net["inv_position"])
    sl, intc, rv, pv, se = linregress(dom_net["net_spend"], dom_net["points"])
    ci_l = sl - stats.t.ppf(0.975, len(dom_net)-2) * se
    ci_u = sl + stats.t.ppf(0.975, len(dom_net)-2) * se

    results["6B_net_spend_vs_points"] = {
        "n": int(len(dom_net)),
        "pearson_r": round(r_p, 4),
        "pearson_p": float(p_p),
        "spearman_rho": round(r_s, 4),
        "spearman_p": float(p_s),
        "regression_slope": round(sl, 6),
        "regression_r_squared": round(rv**2, 4),
        "regression_p_value": float(pv),
        "slope_95ci": [round(ci_l, 6), round(ci_u, 6)],
    }

    print(f"  n = {len(dom_net)}")
    print(f"  Pearson r = {r_p:.4f}, p = {p_p:.2e}")
    print(f"  Spearman ρ = {r_s:.4f}, p = {p_s:.2e}")
    print(f"  R² = {rv**2:.4f}")

    # ─── 6C: Per-league analysis ───
    print("\n--- 6C: Per-League Correlations ---")
    league_results = {}
    for lid, lname in TOP5_LEAGUES.items():
        sub = dom[dom["league_id"] == lid]
        if len(sub) < 10:
            continue
        rp, pp = stats.pearsonr(sub["log_gross_spend"], sub["points"])
        rs, ps = stats.spearmanr(sub["gross_spend"], sub["inv_position"])
        sl2, _, rv2, pv2, se2 = linregress(sub["log_gross_spend"], sub["points"])

        league_results[lname] = {
            "n": int(len(sub)),
            "pearson_r": round(rp, 4),
            "pearson_p": float(pp),
            "spearman_rho": round(rs, 4),
            "spearman_p": float(ps),
            "r_squared": round(rv2**2, 4),
        }
        print(f"  {lname:20s} n={len(sub):4d}  r={rp:.3f}  ρ={rs:.3f}  R²={rv2**2:.3f}")

    results["6C_per_league"] = league_results

    # ─── 6D: UCL spending vs stage ───
    print("\n--- 6D: UCL Spending vs Stage Reached ---")
    ucl_valid = ucl_df[(ucl_df["gross_spend"] > 0) & (ucl_df["ucl_stage_num"] > 0)].copy()
    ucl_valid["log_spend"] = np.log1p(ucl_valid["gross_spend"])

    if len(ucl_valid) > 10:
        rp_ucl, pp_ucl = stats.pearsonr(ucl_valid["log_spend"], ucl_valid["ucl_stage_num"])
        rs_ucl, ps_ucl = stats.spearmanr(ucl_valid["gross_spend"], ucl_valid["ucl_stage_num"])
        sl_u, _, rv_u, pv_u, se_u = linregress(ucl_valid["log_spend"], ucl_valid["ucl_stage_num"])

        results["6D_ucl_spend_vs_stage"] = {
            "n": int(len(ucl_valid)),
            "pearson_r": round(rp_ucl, 4),
            "pearson_p": float(pp_ucl),
            "spearman_rho": round(rs_ucl, 4),
            "spearman_p": float(ps_ucl),
            "regression_r_squared": round(rv_u**2, 4),
        }
        print(f"  n = {len(ucl_valid)}")
        print(f"  Pearson r = {rp_ucl:.4f}, p = {pp_ucl:.2e}")
        print(f"  Spearman ρ = {rs_ucl:.4f}, p = {ps_ucl:.2e}")
        print(f"  R² = {rv_u**2:.4f}")

    # ─── 6E: Fee vs Market Value regression ───
    print("\n--- 6E: Transfer Fee vs Market Value ---")
    rp_fm, pp_fm = stats.pearsonr(fee_mv_df["log_fee"], fee_mv_df["log_mv"])
    rs_fm, ps_fm = stats.spearmanr(fee_mv_df["transfer_fee"], fee_mv_df["mv_at_transfer"])
    sl_f, int_f, rv_f, pv_f, se_f = linregress(fee_mv_df["log_mv"], fee_mv_df["log_fee"])
    ci_l_f = sl_f - stats.t.ppf(0.975, len(fee_mv_df)-2) * se_f
    ci_u_f = sl_f + stats.t.ppf(0.975, len(fee_mv_df)-2) * se_f

    results["6E_fee_vs_mv"] = {
        "n": int(len(fee_mv_df)),
        "pearson_r": round(rp_fm, 4),
        "pearson_p": float(pp_fm),
        "spearman_rho": round(rs_fm, 4),
        "spearman_p": float(ps_fm),
        "regression_slope": round(sl_f, 4),
        "regression_intercept": round(int_f, 4),
        "regression_r_squared": round(rv_f**2, 4),
        "slope_95ci": [round(ci_l_f, 4), round(ci_u_f, 4)],
        "description": "log(fee) ~ log(mv). Slope > 1 means fees rise faster than MV."
    }

    print(f"  n = {len(fee_mv_df)}")
    print(f"  Pearson r (log-log) = {rp_fm:.4f}, p = {pp_fm:.2e}")
    print(f"  Spearman ρ = {rs_fm:.4f}, p = {ps_fm:.2e}")
    print(f"  OLS: log(fee) = {sl_f:.4f} * log(mv) + {int_f:.4f}")
    print(f"  R² = {rv_f**2:.4f}")
    print(f"  95% CI for slope: [{ci_l_f:.4f}, {ci_u_f:.4f}]")

    # ─── 6F: Robustness — Clustered standard errors approximation ───
    print("\n--- 6F: Robustness Checks ---")
    # Check for heteroscedasticity with Breusch-Pagan-like test
    # Residuals from domestic regression
    dom["predicted_pts"] = results["6A_domestic_spend_vs_position"]["regression_slope"] * dom["log_gross_spend"] + \
                           results["6A_domestic_spend_vs_position"]["regression_intercept"]
    dom["residuals"] = dom["points"] - dom["predicted_pts"]
    dom["resid_sq"] = dom["residuals"] ** 2

    # Test: regress residuals² on log_spend
    sl_bp, _, rv_bp, pv_bp, _ = linregress(dom["log_gross_spend"], dom["resid_sq"])

    # Within-club correlation: how many repeated obs per club?
    club_counts = dom.groupby("club_id").size()
    avg_obs_per_club = club_counts.mean()
    max_obs_per_club = club_counts.max()

    results["6F_robustness"] = {
        "heteroscedasticity_test_p": float(pv_bp),
        "heteroscedasticity_detected": pv_bp < 0.05,
        "avg_obs_per_club": round(avg_obs_per_club, 1),
        "max_obs_per_club": int(max_obs_per_club),
        "unique_clubs": int(dom["club_id"].nunique()),
        "note": "Repeated club observations mean standard errors may be underestimated. "
                "P-values should be interpreted conservatively."
    }

    print(f"  Heteroscedasticity test p = {pv_bp:.4f} ({'detected' if pv_bp < 0.05 else 'not detected'})")
    print(f"  Avg observations per club: {avg_obs_per_club:.1f}")
    print(f"  Max observations per club: {max_obs_per_club}")
    print(f"  → Repeated measures: p-values may be liberal. Interpret with caution.")

    # Save all results
    with open(OUTPUT_DIR / "06_statistical_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n✓ Saved to {OUTPUT_DIR / '06_statistical_results.json'}")

    return results


def run_analysis_7_domestic_vs_ucl_comparison(domestic_df: pd.DataFrame,
                                                ucl_df: pd.DataFrame,
                                                stat_results: dict) -> pd.DataFrame:
    """Analysis 7: Compare domestic vs UCL money-success relationship."""
    print("\n" + "=" * 70)
    print("ANALYSIS 7: Domestic vs UCL Comparison")
    print("=" * 70)

    # Get clubs that appear in BOTH domestic and UCL datasets in same season
    dom_keys = set(zip(domestic_df["club_id"], domestic_df["season"]))
    ucl_keys = set(zip(ucl_df["club_id"], ucl_df["season"]))
    both_keys = dom_keys & ucl_keys

    print(f"  Club-seasons in domestic: {len(dom_keys)}")
    print(f"  Club-seasons in UCL: {len(ucl_keys)}")
    print(f"  Club-seasons in BOTH: {len(both_keys)}")

    # Build comparison dataset
    dom_sub = domestic_df[
        domestic_df.apply(lambda r: (r["club_id"], r["season"]) in both_keys, axis=1)
    ].copy()
    ucl_sub = ucl_df[
        ucl_df.apply(lambda r: (r["club_id"], r["season"]) in both_keys, axis=1)
    ].copy()

    # Merge domestic + UCL for same club-season
    comparison = dom_sub[["club_id", "season", "name", "league_name", "gross_spend",
                          "net_spend", "points", "league_position", "log_gross_spend"]].merge(
        ucl_sub[["club_id", "season", "ucl_matches", "ucl_wins", "ucl_stage_num",
                 "ucl_stage", "ucl_points"]],
        on=["club_id", "season"],
        how="inner"
    )

    print(f"\n  Paired observations: {len(comparison)}")

    # Correlations for the paired set
    if len(comparison) > 10:
        # Domestic: spend vs points
        r_dom, p_dom = stats.pearsonr(comparison["log_gross_spend"], comparison["points"])
        # UCL: spend vs stage
        r_ucl, p_ucl = stats.pearsonr(comparison["log_gross_spend"], comparison["ucl_stage_num"])

        # Fisher z-test to compare correlations
        z_dom = np.arctanh(r_dom)
        z_ucl = np.arctanh(r_ucl)
        n = len(comparison)
        se_diff = np.sqrt(2 / (n - 3))
        z_diff = (z_dom - z_ucl) / se_diff
        p_diff = 2 * (1 - stats.norm.cdf(abs(z_diff)))

        print(f"\n  Domestic: r(log_spend, points) = {r_dom:.4f}, p = {p_dom:.2e}")
        print(f"  UCL:      r(log_spend, stage)  = {r_ucl:.4f}, p = {p_ucl:.2e}")
        print(f"  Fisher z-test for difference:   z = {z_diff:.4f}, p = {p_diff:.4f}")
        print(f"  → {'Significantly different' if p_diff < 0.05 else 'Not significantly different'}")

        comp_results = {
            "n_paired": int(n),
            "domestic_r": round(r_dom, 4),
            "domestic_p": float(p_dom),
            "ucl_r": round(r_ucl, 4),
            "ucl_p": float(p_ucl),
            "fisher_z": round(z_diff, 4),
            "fisher_p": float(p_diff),
            "conclusion": "Money correlates more strongly with domestic success than UCL stage reached" if r_dom > r_ucl else "Money correlates more strongly with UCL advancement"
        }

        with open(OUTPUT_DIR / "07_domestic_vs_ucl_comparison.json", "w") as f:
            json.dump(comp_results, f, indent=2, default=str)

    comparison.to_csv(OUTPUT_DIR / "07_domestic_vs_ucl_paired.csv", index=False)
    print(f"\n✓ Saved to {OUTPUT_DIR / '07_domestic_vs_ucl_paired.csv'}")

    return comparison


def generate_charts(domestic_df, ucl_df, fee_mv_df, trends_df, stat_results):
    """Generate publication-quality charts using matplotlib."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker

    plt.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "font.size": 11,
        "axes.titlesize": 14,
        "axes.labelsize": 12,
        "figure.dpi": 150,
        "savefig.dpi": 150,
        "savefig.bbox": "tight",
    })

    league_colors = {
        "Premier League": "#3d195b",
        "LaLiga": "#ee8707",
        "Serie A": "#024494",
        "Bundesliga": "#d20515",
        "Ligue 1": "#091c3e",
    }

    # ─── Chart 1: Historical spending trends ───
    print("\n  Generating Chart 1: Historical Spending Trends...")
    fig, ax = plt.subplots(figsize=(14, 7))

    for lid, lname in TOP5_LEAGUES.items():
        sub = trends_df[trends_df["league_id"] == lid].sort_values("game_season")
        ax.plot(sub["game_season"], sub["total_spending"] / 1e9,
                marker="o", label=lname, color=league_colors.get(lname, "gray"),
                linewidth=2, markersize=5)

    ax.set_xlabel("Season (start year)")
    ax.set_ylabel("Total Transfer Spending (€ Billion)")
    ax.set_title("Historical Transfer Spending by League (2012–2025)")
    ax.legend(loc="upper left", framealpha=0.9)
    ax.grid(True, alpha=0.3)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"€{x:.1f}B"))
    plt.tight_layout()
    fig.savefig(CHARTS_DIR / "01_spending_trends.png")
    plt.close()

    # ─── Chart 2: Spending vs League Position scatter ───
    print("  Generating Chart 2: Spending vs League Position...")
    fig, axes = plt.subplots(1, 5, figsize=(22, 5), sharey=True)

    dom = domestic_df[domestic_df["gross_spend"] > 0].copy()
    for i, (lid, lname) in enumerate(TOP5_LEAGUES.items()):
        ax = axes[i]
        sub = dom[dom["league_id"] == lid]
        ax.scatter(sub["gross_spend"] / 1e6, sub["league_position"],
                   alpha=0.35, s=20, color=league_colors.get(lname, "gray"))
        ax.set_title(lname, fontsize=11)
        ax.set_xlabel("Gross Spend (€M)")
        ax.invert_yaxis()
        ax.set_xlim(left=0)
        ax.grid(True, alpha=0.3)
        if i == 0:
            ax.set_ylabel("League Position (1 = champion)")

    fig.suptitle("Transfer Spending vs League Position (2012–2025)", fontsize=14, y=1.02)
    plt.tight_layout()
    fig.savefig(CHARTS_DIR / "02_spending_vs_position.png")
    plt.close()

    # ─── Chart 3: Spending vs Points with regression ───
    print("  Generating Chart 3: Spending vs Points (regression)...")
    fig, ax = plt.subplots(figsize=(10, 7))

    for lid, lname in TOP5_LEAGUES.items():
        sub = dom[dom["league_id"] == lid]
        ax.scatter(sub["gross_spend"] / 1e6, sub["points"],
                   alpha=0.35, s=20, label=lname, color=league_colors.get(lname, "gray"))

    # Overall regression line
    x_range = np.linspace(dom["log_gross_spend"].min(), dom["log_gross_spend"].max(), 100)
    slope = stat_results["6A_domestic_spend_vs_position"]["regression_slope"]
    intercept = stat_results["6A_domestic_spend_vs_position"]["regression_intercept"]
    r_sq = stat_results["6A_domestic_spend_vs_position"]["regression_r_squared"]
    ax.plot(np.expm1(x_range) / 1e6,
            slope * x_range + intercept,
            color="red", linewidth=2, linestyle="--",
            label=f"OLS (R²={r_sq:.3f})")

    ax.set_xlabel("Gross Transfer Spending (€M)")
    ax.set_ylabel("League Points")
    ax.set_title("Transfer Spending vs League Points (Top 5 Leagues, 2012–2025)")
    ax.legend(loc="lower right", framealpha=0.9)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    fig.savefig(CHARTS_DIR / "03_spending_vs_points_regression.png")
    plt.close()

    # ─── Chart 4: UCL Stage vs Spending ───
    print("  Generating Chart 4: UCL Stage vs Spending...")
    fig, ax = plt.subplots(figsize=(10, 7))

    ucl_valid = ucl_df[(ucl_df["gross_spend"] > 0) & (ucl_df["ucl_stage_num"] > 0)].copy()
    stage_labels = {1: "Group", 2: "R16", 3: "QF", 4: "SF", 5: "Final"}

    for stage_num, stage_label in stage_labels.items():
        sub = ucl_valid[ucl_valid["ucl_stage_num"] == stage_num]
        ax.scatter(sub["gross_spend"] / 1e6,
                   [stage_num] * len(sub),
                   alpha=0.4, s=30, label=f"{stage_label} (n={len(sub)})")

    ax.set_xlabel("Gross Transfer Spending (€M)")
    ax.set_ylabel("UCL Stage Reached")
    ax.set_yticks(list(stage_labels.keys()))
    ax.set_yticklabels(list(stage_labels.values()))
    ax.set_title("Transfer Spending vs UCL Stage Reached (2012–2025)")
    ax.legend(loc="lower right", framealpha=0.9)
    ax.grid(True, alpha=0.3, axis="x")
    plt.tight_layout()
    fig.savefig(CHARTS_DIR / "04_ucl_stage_vs_spending.png")
    plt.close()

    # ─── Chart 5: Fee vs Market Value ───
    print("  Generating Chart 5: Transfer Fee vs Market Value...")
    fig, ax = plt.subplots(figsize=(10, 8))

    # Sample for plotting (too many points otherwise)
    plot_df = fee_mv_df.sample(min(5000, len(fee_mv_df)), random_state=42)

    top5_mask = plot_df["is_top5"]
    ax.scatter(plot_df.loc[~top5_mask, "mv_at_transfer"] / 1e6,
               plot_df.loc[~top5_mask, "transfer_fee"] / 1e6,
               alpha=0.2, s=15, color="gray", label="Other leagues")
    ax.scatter(plot_df.loc[top5_mask, "mv_at_transfer"] / 1e6,
               plot_df.loc[top5_mask, "transfer_fee"] / 1e6,
               alpha=0.3, s=15, color="#2196F3", label="Top 5 leagues")

    # 1:1 line
    max_val = max(plot_df["transfer_fee"].max(), plot_df["mv_at_transfer"].max()) / 1e6
    ax.plot([0, max_val], [0, max_val], "r--", linewidth=1.5, label="Fee = Market Value", alpha=0.7)

    ax.set_xlabel("Market Value at Transfer (€M)")
    ax.set_ylabel("Transfer Fee Paid (€M)")
    ax.set_title("Transfer Fee vs Estimated Market Value")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    plt.tight_layout()
    fig.savefig(CHARTS_DIR / "05_fee_vs_market_value.png")
    plt.close()

    # ─── Chart 6: Domestic vs UCL correlation comparison ───
    print("  Generating Chart 6: Domestic vs UCL Comparison...")
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    # Left: Domestic
    comparison = pd.read_csv(OUTPUT_DIR / "07_domestic_vs_ucl_paired.csv")
    ax = axes[0]
    ax.scatter(comparison["gross_spend"] / 1e6, comparison["points"],
               alpha=0.4, s=25, color="#3d195b")
    # Regression line
    mask = comparison["gross_spend"] > 0
    if mask.sum() > 2:
        sl, intc, rv, _, _ = stats.linregress(
            np.log1p(comparison.loc[mask, "gross_spend"]),
            comparison.loc[mask, "points"]
        )
        x_plot = np.linspace(
            np.log1p(comparison.loc[mask, "gross_spend"].min()),
            np.log1p(comparison.loc[mask, "gross_spend"].max()),
            100
        )
        ax.plot(np.expm1(x_plot) / 1e6, sl * x_plot + intc,
                "r--", linewidth=2, label=f"R²={rv**2:.3f}")
    ax.set_xlabel("Gross Spend (€M)")
    ax.set_ylabel("Domestic League Points")
    ax.set_title("Domestic: Spending vs Points\n(UCL-qualified clubs only)")
    ax.legend()
    ax.grid(True, alpha=0.3)

    # Right: UCL
    ax = axes[1]
    ax.scatter(comparison["gross_spend"] / 1e6, comparison["ucl_stage_num"],
               alpha=0.4, s=25, color="#1a237e")
    if mask.sum() > 2:
        sl2, intc2, rv2, _, _ = stats.linregress(
            np.log1p(comparison.loc[mask, "gross_spend"]),
            comparison.loc[mask, "ucl_stage_num"]
        )
        ax.plot(np.expm1(x_plot) / 1e6, sl2 * x_plot + intc2,
                "r--", linewidth=2, label=f"R²={rv2**2:.3f}")
    ax.set_xlabel("Gross Spend (€M)")
    ax.set_ylabel("UCL Stage Reached")
    ax.set_yticks([1, 2, 3, 4, 5])
    ax.set_yticklabels(["Group", "R16", "QF", "SF", "Final"])
    ax.set_title("UCL: Spending vs Stage Reached\n(same clubs)")
    ax.legend()
    ax.grid(True, alpha=0.3)

    fig.suptitle("Does Money Buy More Success Domestically or in Europe?", fontsize=14, y=1.02)
    plt.tight_layout()
    fig.savefig(CHARTS_DIR / "06_domestic_vs_ucl_comparison.png")
    plt.close()

    # ─── Chart 7: Spending efficiency by league ───
    print("  Generating Chart 7: Spending Efficiency by League...")
    fig, ax = plt.subplots(figsize=(10, 6))

    league_stats = []
    for lid, lname in TOP5_LEAGUES.items():
        sub = dom[dom["league_id"] == lid]
        rp, _ = stats.pearsonr(sub["log_gross_spend"], sub["points"])
        league_stats.append({
            "league": lname,
            "r": rp,
            "n": len(sub),
            "avg_spend": sub["gross_spend"].mean() / 1e6,
            "color": league_colors.get(lname, "gray")
        })

    league_stats_df = pd.DataFrame(league_stats)
    bars = ax.barh(league_stats_df["league"], league_stats_df["r"],
                    color=[r["color"] for r in league_stats],
                    edgecolor="white", linewidth=0.5)

    for bar, row in zip(bars, league_stats):
        ax.text(bar.get_width() + 0.01, bar.get_y() + bar.get_height()/2,
                f'r={row["r"]:.3f} (n={row["n"]})',
                va="center", fontsize=10)

    ax.set_xlabel("Pearson Correlation (log spend vs points)")
    ax.set_title("Money-Success Correlation Strength by League")
    ax.set_xlim(0, ax.get_xlim()[1] * 1.3)
    ax.grid(True, alpha=0.3, axis="x")
    plt.tight_layout()
    fig.savefig(CHARTS_DIR / "07_correlation_by_league.png")
    plt.close()

    print(f"\n✓ All 7 charts saved to {CHARTS_DIR}")


def main():
    """Run the complete Phase 2 analysis pipeline."""
    print("=" * 70)
    print("FootIntel — Phase 2: Statistical Analysis Engine")
    print("=" * 70)

    ensure_dirs()
    con = get_connection(read_only=True)

    try:
        # Analysis 1: Historical trends
        trends_df = run_analysis_1_historical_trends(con)

        # Analysis 2: Domestic spending vs performance
        domestic_df = run_analysis_2_domestic_spending_vs_performance(con)

        # Analysis 3: UCL spending vs performance
        ucl_df = run_analysis_3_ucl_spending_vs_performance(con, domestic_df)

        # Analysis 4: Fee vs market value
        fee_mv_df = run_analysis_4_fee_vs_market_value(con)

        # Analysis 5: Club value gain
        value_gain_df = run_analysis_5_club_value_gain(con)

        # Analysis 6: Statistical tests
        stat_results = run_analysis_6_statistical_tests(domestic_df, ucl_df, fee_mv_df)

        # Analysis 7: Domestic vs UCL comparison
        comparison_df = run_analysis_7_domestic_vs_ucl_comparison(domestic_df, ucl_df, stat_results)

        # Generate charts
        print("\n" + "=" * 70)
        print("Generating Publication-Quality Charts")
        print("=" * 70)
        generate_charts(domestic_df, ucl_df, fee_mv_df, trends_df, stat_results)

    finally:
        con.close()

    print("\n" + "=" * 70)
    print("Phase 2 Complete — All analyses and charts generated.")
    print(f"  Outputs: {OUTPUT_DIR}")
    print(f"  Charts:  {CHARTS_DIR}")
    print("=" * 70)


if __name__ == "__main__":
    main()
