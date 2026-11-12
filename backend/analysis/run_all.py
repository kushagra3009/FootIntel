"""
FootIntel Phase 2 — Statistical Analysis Engine

Analyses:
1. Historical transfer spending trends (season-aligned Top 5 leagues + coverage check)
2. Domestic league spending vs sporting performance (Top 5 leagues, PPG & normalized rank)
3. UEFA Champions League spending vs performance (All UCL clubs + Top 5 subset, 2024+ format aware)
4. Transfer fee vs estimated market value
5. Club-level estimated value gain analysis (spell-bounded valuations)
6. Full statistical battery (Pearson, Spearman, OLS, club-clustered SEs, CIs, FE & robustness checks)
7. Domestic vs UCL comparison (paired positive-spend & full-sample, Steiger & Fisher z-tests)

All outputs are saved to data/processed/analysis_outputs/ and data/processed/charts/.
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


# ─────────────────────────────────────────────────────────────────────────────
# Econometric Helpers
# ─────────────────────────────────────────────────────────────────────────────

def cluster_ols(df: pd.DataFrame, x_col: str, y_col: str, cluster_col: str = "club_id", extra_dof: int = 0) -> dict:
    """Run OLS with Liang-Zeger club-clustered standard errors (small-sample corrected)."""
    sub = df[[x_col, y_col, cluster_col]].dropna()
    x = sub[x_col].to_numpy(dtype=float)
    y = sub[y_col].to_numpy(dtype=float)
    clusters = sub[cluster_col].to_numpy()

    n = len(x)
    X = np.column_stack([np.ones(n), x])
    k = X.shape[1]
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    resid = y - X @ beta

    ss_tot = np.sum((y - y.mean()) ** 2)
    ss_res = np.sum(resid ** 2)
    r2 = float(1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0

    # Naive OLS SE
    s2 = ss_res / max(n - k - extra_dof, 1)
    XtX_inv = np.linalg.inv(X.T @ X)
    se_naive = float(np.sqrt(s2 * XtX_inv[1, 1]))
    t_naive = float(beta[1] / se_naive) if se_naive > 0 else 0.0
    p_naive = float(2 * stats.t.sf(abs(t_naive), df=max(n - k - extra_dof, 1)))

    # Club-clustered sandwich SE
    uniq = np.unique(clusters)
    G = len(uniq)
    meat = np.zeros((k, k))
    for c in uniq:
        idx = clusters == c
        score = X[idx].T @ resid[idx]
        meat += np.outer(score, score)

    dof_corr = (G / max(G - 1, 1)) * ((n - 1) / max(n - k - extra_dof, 1))
    V_cluster = dof_corr * (XtX_inv @ meat @ XtX_inv)
    se_cluster = float(np.sqrt(V_cluster[1, 1]))
    t_cluster = float(beta[1] / se_cluster) if se_cluster > 0 else 0.0
    p_cluster = float(2 * stats.t.sf(abs(t_cluster), df=max(G - 1, 1)))
    t_crit = float(stats.t.ppf(0.975, df=max(G - 1, 1)))
    ci_cluster = [float(beta[1] - t_crit * se_cluster), float(beta[1] + t_crit * se_cluster)]

    return {
        "n": int(n),
        "clusters": int(G),
        "slope": round(float(beta[1]), 6),
        "intercept": round(float(beta[0]), 6),
        "r_squared": round(r2, 4),
        "naive_se": round(se_naive, 6),
        "naive_p": p_naive,
        "cluster_se": round(se_cluster, 6),
        "cluster_t": round(t_cluster, 4),
        "cluster_p": p_cluster,
        "cluster_95ci": [round(ci_cluster[0], 6), round(ci_cluster[1], 6)],
    }


def steiger_z_test(r12: float, r13: float, r23: float, n: int) -> tuple[float, float]:
    """Steiger's (1980) z-test comparing two dependent correlations sharing one variable (r12 vs r13)."""
    z12 = np.arctanh(np.clip(r12, -0.9999, 0.9999))
    z13 = np.arctanh(np.clip(r13, -0.9999, 0.9999))
    rm2 = (r12 ** 2 + r13 ** 2) / 2.0
    f = min((1.0 - r23) / (2.0 * (1.0 - rm2)), 1.0 / (1.0 - rm2))
    h = (1.0 - f * rm2) / (1.0 - rm2)
    z_stat = (z12 - z13) * np.sqrt((n - 3) / (2.0 * (1.0 - r23) * h))
    p_val = float(2 * (1 - stats.norm.cdf(abs(z_stat))))
    return float(z_stat), p_val


# ─────────────────────────────────────────────────────────────────────────────
# Analysis 1: Historical Transfer Spending Trends
# ─────────────────────────────────────────────────────────────────────────────

def run_analysis_1_historical_trends(con) -> pd.DataFrame:
    """Analysis 1: Season-aligned historical transfer spending trends across Top 5 leagues."""
    print("\n" + "=" * 70)
    print("ANALYSIS 1: Historical Transfer Spending Trends (Season-Aligned)")
    print("=" * 70)

    # Use actual season participation from `games` to avoid attributing Championship/2nd-tier
    # spending to Top-5 leagues via static `clubs.domestic_competition_id`.
    df = con.execute("""
        WITH top5_season_clubs AS (
            SELECT DISTINCT season AS game_season, competition_id AS league_id, home_club_id AS club_id
            FROM games
            WHERE competition_id IN ('GB1','ES1','IT1','L1','FR1')
              AND season BETWEEN 2012 AND 2025
        ),
        transfers_mapped AS (
            SELECT
                t.*,
                p.last_season AS player_last_season,
                CASE WHEN CAST(SPLIT_PART(t.transfer_season, '/', 1) AS INT) >= 90
                     THEN 1900 + CAST(SPLIT_PART(t.transfer_season, '/', 1) AS INT)
                     ELSE 2000 + CAST(SPLIT_PART(t.transfer_season, '/', 1) AS INT) END AS game_season
            FROM transfers t
            LEFT JOIN players p ON t.player_id = p.player_id
            WHERE t.transfer_season IS NOT NULL
        )
        SELECT
            tm.transfer_season,
            tm.game_season,
            sc.league_id,
            COUNT(*) AS total_transfers,
            SUM(CASE WHEN tm.transfer_fee > 0 THEN 1 ELSE 0 END) AS paid_transfers,
            SUM(CASE WHEN tm.transfer_fee > 0 THEN tm.transfer_fee ELSE 0 END) AS total_spending,
            AVG(CASE WHEN tm.transfer_fee > 0 THEN tm.transfer_fee ELSE NULL END) AS avg_fee,
            MEDIAN(CASE WHEN tm.transfer_fee > 0 THEN tm.transfer_fee ELSE NULL END) AS median_fee,
            MAX(tm.transfer_fee) AS max_fee,
            ROUND(100.0 * SUM(CASE WHEN tm.player_last_season >= 2023 THEN 1 ELSE 0 END) / COUNT(*), 1) AS pct_recent_cohort
        FROM transfers_mapped tm
        JOIN top5_season_clubs sc
          ON tm.game_season = sc.game_season
         AND tm.to_club_id = sc.club_id
        GROUP BY tm.transfer_season, tm.game_season, sc.league_id
        ORDER BY tm.game_season, sc.league_id
    """).df()

    df["league_name"] = df["league_id"].map(TOP5_LEAGUES)
    df["total_spending_m"] = df["total_spending"] / 1e6

    # Aggregate across all Top 5 leagues per season (weighted mean fee = total_spending / paid_transfers)
    agg = df.groupby(["transfer_season", "game_season"]).agg(
        total_transfers=("total_transfers", "sum"),
        paid_transfers=("paid_transfers", "sum"),
        total_spending=("total_spending", "sum"),
    ).reset_index().sort_values("game_season")
    agg["weighted_avg_fee_m"] = np.where(
        agg["paid_transfers"] > 0,
        (agg["total_spending"] / agg["paid_transfers"]) / 1e6,
        np.nan,
    )

    print(f"\nSeasons covered: {df['game_season'].min()}-{df['game_season'].max()}")
    print(f"Rows (league-season): {len(df)}")
    print("\nAggregate Top 5 season-aligned spending:")
    for _, r in agg.iterrows():
        print(f"  {r['transfer_season']}: €{r['total_spending']/1e9:.2f}B "
              f"({r['paid_transfers']:.0f} paid transfers, "
              f"weighted avg €{r['weighted_avg_fee_m']:.1f}M)")

    df.to_csv(OUTPUT_DIR / "01_historical_trends_by_league.csv", index=False)
    agg.to_csv(OUTPUT_DIR / "01_historical_trends_aggregate.csv", index=False)
    print(f"\n✓ Saved to {OUTPUT_DIR / '01_historical_trends_by_league.csv'}")

    return df


# ─────────────────────────────────────────────────────────────────────────────
# Analysis 2: Domestic League Spending vs Sporting Performance
# ─────────────────────────────────────────────────────────────────────────────

def run_analysis_2_domestic_spending_vs_performance(con) -> pd.DataFrame:
    """Analysis 2: Domestic league spending vs sporting performance (Top 5 leagues)."""
    print("\n" + "=" * 70)
    print("ANALYSIS 2: Domestic Spending vs Performance (Top 5 Leagues)")
    print("=" * 70)

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
            RANK() OVER (PARTITION BY season, league_id ORDER BY points DESC, (goals_for - goals_against) DESC) AS league_position,
            COUNT(*) OVER (PARTITION BY season, league_id) AS n_teams
        FROM combined
        WHERE played >= 10
        ORDER BY season, league_id, league_position
    """).df()

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

    merged = standings.merge(
        spending[["club_id", "game_season", "gross_spend", "players_bought_paid", "total_arrivals"]],
        left_on=["club_id", "season"],
        right_on=["club_id", "game_season"],
        how="left",
    ).drop(columns=["game_season"])

    merged = merged.merge(
        sales[["club_id", "game_season", "gross_income", "players_sold_paid"]],
        left_on=["club_id", "season"],
        right_on=["club_id", "game_season"],
        how="left",
    ).drop(columns=["game_season"])

    merged["gross_spend"] = merged["gross_spend"].fillna(0.0)
    merged["gross_income"] = merged["gross_income"].fillna(0.0)
    merged["net_spend"] = merged["gross_spend"] - merged["gross_income"]
    merged["players_bought_paid"] = merged["players_bought_paid"].fillna(0).astype(int)
    merged["total_arrivals"] = merged["total_arrivals"].fillna(0).astype(int)
    merged["players_sold_paid"] = merged["players_sold_paid"].fillna(0).astype(int)

    clubs = con.execute("SELECT club_id, name FROM clubs").df()
    merged = merged.merge(clubs, on="club_id", how="left")
    merged["league_name"] = merged["league_id"].map(TOP5_LEAGUES)
    merged = merged[merged["season"].between(2012, 2025)].copy()
    merged["transfer_season"] = merged["season"].apply(game_season_to_transfer_season)

    # Normalized outcomes (across 18-team vs 20-team leagues & 2019/20 Ligue 1)
    merged["ppg"] = merged["points"] / merged["played"]
    merged["pos_pct"] = (merged["n_teams"] - merged["league_position"]) / (merged["n_teams"] - 1)

    # Spending in € Millions + clean log transforms
    merged["gross_spend_m"] = merged["gross_spend"] / 1e6
    merged["gross_income_m"] = merged["gross_income"] / 1e6
    merged["net_spend_m"] = merged["net_spend"] / 1e6
    merged["log_gross_spend_m"] = np.log(merged["gross_spend_m"].where(merged["gross_spend_m"] > 0))
    merged["asinh_gross_spend_m"] = np.arcsinh(merged["gross_spend_m"])
    merged["log_gross_spend"] = np.log1p(merged["gross_spend"])
    merged["spend_per_point"] = np.where(merged["points"] > 0, merged["gross_spend"] / merged["points"], np.nan)

    cols_to_keep = [
        "season", "transfer_season", "league_id", "league_name", "club_id", "name",
        "played", "n_teams", "wins", "draws", "losses", "points", "goals_for", "goals_against",
        "goal_diff", "league_position", "pos_pct", "ppg",
        "gross_spend", "gross_income", "net_spend",
        "gross_spend_m", "gross_income_m", "net_spend_m",
        "players_bought_paid", "total_arrivals", "players_sold_paid",
        "spend_per_point", "log_gross_spend_m", "asinh_gross_spend_m", "log_gross_spend",
    ]
    merged = merged[cols_to_keep].copy()

    print(f"\nMerged dataset: {len(merged)} club-season observations")
    print(f"  With spending > 0: {(merged['gross_spend'] > 0).sum()}")
    print(f"  Unique clubs: {merged['club_id'].nunique()}")

    merged.to_csv(OUTPUT_DIR / "02_domestic_spending_vs_performance.csv", index=False)
    print(f"✓ Saved to {OUTPUT_DIR / '02_domestic_spending_vs_performance.csv'}")

    return merged


# ─────────────────────────────────────────────────────────────────────────────
# Analysis 3: UCL Spending vs Performance
# ─────────────────────────────────────────────────────────────────────────────

def run_analysis_3_ucl_spending_vs_performance(con) -> pd.DataFrame:
    """Analysis 3: UCL spending vs performance (all matched clubs + Top 5 flag)."""
    print("\n" + "=" * 70)
    print("ANALYSIS 3: UCL Spending vs Performance")
    print("=" * 70)

    ucl = con.execute("""
        WITH ucl_games AS (
            SELECT
                season,
                home_club_id AS club_id,
                home_club_goals AS gf,
                away_club_goals AS ga,
                CASE WHEN home_club_goals > away_club_goals THEN 'W'
                     WHEN home_club_goals = away_club_goals THEN 'D' ELSE 'L' END AS result
            FROM games WHERE competition_id = 'CL' AND home_club_goals IS NOT NULL
            UNION ALL
            SELECT
                season,
                away_club_id AS club_id,
                away_club_goals AS gf,
                home_club_goals AS ga,
                CASE WHEN away_club_goals > home_club_goals THEN 'W'
                     WHEN away_club_goals = home_club_goals THEN 'D' ELSE 'L' END AS result
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

    # Map UCL rounds accurately, including 2024/25+ intermediate knockout playoff stage
    stage_order = {
        "Group Stage": 1.0, "Group A": 1.0, "Group B": 1.0, "Group C": 1.0,
        "Group D": 1.0, "Group E": 1.0, "Group F": 1.0, "Group G": 1.0, "Group H": 1.0,
        "intermediate stage 1st leg": 1.5, "intermediate stage 2nd leg": 1.5,
        "last 16 1st leg": 2.0, "last 16 2nd leg": 2.0,
        "Last 16 1st Leg": 2.0, "Last 16 2nd Leg": 2.0,
        "Quarter-Finals": 3.0, "Quarter-Finals 1st leg": 3.0, "Quarter-Finals 2nd leg": 3.0,
        "Quarter-Finals 1st Leg": 3.0, "Quarter-Finals 2nd Leg": 3.0,
        "Semi-Finals": 4.0, "Semi-Finals 1st Leg": 4.0, "Semi-Finals 2nd Leg": 4.0,
        "Semi-Finals 1st leg": 4.0, "Semi-Finals 2nd Leg": 4.0,
        "Final": 5.0,
    }
    stage_labels = {
        1.0: "Group / League Phase",
        1.5: "Knockout Playoff",
        2.0: "Round of 16",
        3.0: "Quarter-Finals",
        4.0: "Semi-Finals",
        5.0: "Final",
    }

    rounds = con.execute("""
        SELECT DISTINCT season, home_club_id AS club_id, round FROM games WHERE competition_id = 'CL'
        UNION
        SELECT DISTINCT season, away_club_id AS club_id, round FROM games WHERE competition_id = 'CL'
    """).df()

    unmapped = set(rounds["round"].unique()) - set(stage_order.keys())
    if unmapped:
        print(f"  ! Warning: unmapped UCL rounds: {unmapped}")

    rounds["stage_num"] = rounds["round"].map(stage_order).fillna(0.0)
    furthest = rounds.groupby(["season", "club_id"], as_index=False)["stage_num"].max()
    furthest = furthest.rename(columns={"stage_num": "ucl_stage_num"})
    furthest["ucl_stage"] = furthest["ucl_stage_num"].map(stage_labels).fillna("Unknown")

    ucl = ucl.merge(furthest, on=["season", "club_id"], how="left")
    ucl["ucl_points"] = ucl["ucl_wins"] * 3 + ucl["ucl_draws"]
    ucl["ucl_ppg"] = ucl["ucl_points"] / ucl["ucl_matches"]

    # Join ALL transfers directly by (club_id, season) + club info (don't restrict to Top 5 only!)
    spend_sales = con.execute("""
        WITH spend AS (
            SELECT
                CASE WHEN CAST(SPLIT_PART(transfer_season, '/', 1) AS INT) >= 90
                     THEN 1900 + CAST(SPLIT_PART(transfer_season, '/', 1) AS INT)
                     ELSE 2000 + CAST(SPLIT_PART(transfer_season, '/', 1) AS INT) END AS season,
                to_club_id AS club_id,
                SUM(CASE WHEN transfer_fee > 0 THEN transfer_fee ELSE 0 END) AS gross_spend
            FROM transfers
            WHERE transfer_season IS NOT NULL
            GROUP BY 1, 2
        ),
        sales AS (
            SELECT
                CASE WHEN CAST(SPLIT_PART(transfer_season, '/', 1) AS INT) >= 90
                     THEN 1900 + CAST(SPLIT_PART(transfer_season, '/', 1) AS INT)
                     ELSE 2000 + CAST(SPLIT_PART(transfer_season, '/', 1) AS INT) END AS season,
                from_club_id AS club_id,
                SUM(CASE WHEN transfer_fee > 0 THEN transfer_fee ELSE 0 END) AS gross_income
            FROM transfers
            WHERE transfer_season IS NOT NULL
            GROUP BY 1, 2
        ),
        dom_league AS (
            SELECT DISTINCT season, competition_id AS season_league_id, home_club_id AS club_id
            FROM games
            WHERE competition_id IN ('GB1','ES1','IT1','L1','FR1')
        )
        SELECT
            c.club_id,
            c.name,
            c.domestic_competition_id AS club_domestic_league_id,
            dl.season_league_id,
            COALESCE(sp.season, sa.season) AS season,
            COALESCE(sp.gross_spend, 0) AS gross_spend,
            COALESCE(sa.gross_income, 0) AS gross_income
        FROM clubs c
        LEFT JOIN spend sp ON c.club_id = sp.club_id
        LEFT JOIN sales sa ON c.club_id = sa.club_id AND sp.season = sa.season
        LEFT JOIN dom_league dl ON c.club_id = dl.club_id AND COALESCE(sp.season, sa.season) = dl.season
        WHERE COALESCE(sp.season, sa.season) IS NOT NULL
    """).df()

    clubs_info = con.execute("SELECT club_id, name, domestic_competition_id FROM clubs").df()
    ucl = ucl.merge(clubs_info, on="club_id", how="inner")  # 437 / 456 club-seasons with club metadata
    ucl = ucl.merge(
        spend_sales[["club_id", "season", "gross_spend", "gross_income", "season_league_id"]].drop_duplicates(),
        on=["club_id", "season"],
        how="left",
    )

    ucl["gross_spend"] = ucl["gross_spend"].fillna(0.0)
    ucl["gross_income"] = ucl["gross_income"].fillna(0.0)
    ucl["net_spend"] = ucl["gross_spend"] - ucl["gross_income"]
    ucl["gross_spend_m"] = ucl["gross_spend"] / 1e6
    ucl["net_spend_m"] = ucl["net_spend"] / 1e6
    ucl["log_gross_spend_m"] = np.log(ucl["gross_spend_m"].where(ucl["gross_spend_m"] > 0))
    ucl["asinh_gross_spend_m"] = np.arcsinh(ucl["gross_spend_m"])
    ucl["log_gross_spend"] = np.log1p(ucl["gross_spend"])
    ucl["league_id"] = ucl["season_league_id"].fillna(ucl["domestic_competition_id"])
    ucl["is_top5"] = ucl["league_id"].isin(TOP5_LEAGUES.keys())
    ucl["league_name"] = ucl["league_id"].map(TOP5_LEAGUES).fillna(ucl["league_id"])
    ucl["transfer_season"] = ucl["season"].apply(game_season_to_transfer_season)

    print(f"\nUCL dataset (all clubs in clubs table): {len(ucl)} club-season observations")
    print(f"  With spending > 0: {(ucl['gross_spend'] > 0).sum()}")
    print(f"  Top-5 UCL obs: {ucl['is_top5'].sum()} (spend > 0: {((ucl['is_top5']) & (ucl['gross_spend'] > 0)).sum()})")
    print(f"  Non-Top-5 UCL obs: {(~ucl['is_top5']).sum()}")
    print(f"  Seasons: {ucl['season'].min()}-{ucl['season'].max()} (note: 2025 Final not yet played)")
    print(f"  Unique clubs: {ucl['club_id'].nunique()}")
    print("\n  Stage distribution (all clubs):")
    print(ucl["ucl_stage"].value_counts().to_string())

    ucl.to_csv(OUTPUT_DIR / "03_ucl_spending_vs_performance.csv", index=False)
    print(f"\n✓ Saved to {OUTPUT_DIR / '03_ucl_spending_vs_performance.csv'}")

    return ucl


# ─────────────────────────────────────────────────────────────────────────────
# Analysis 4: Transfer Fee vs Estimated Market Value
# ─────────────────────────────────────────────────────────────────────────────

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

    df["fee_to_mv_ratio"] = df["transfer_fee"] / df["mv_at_transfer"]
    df["premium_pct"] = (df["transfer_fee"] - df["mv_at_transfer"]) / df["mv_at_transfer"] * 100
    df["overpay"] = df["transfer_fee"] - df["mv_at_transfer"]
    df["log_fee"] = np.log(df["transfer_fee"])
    df["log_mv"] = np.log(df["mv_at_transfer"])
    df["is_top5"] = df["to_league_id"].isin(TOP5_LEAGUES.keys())
    df["league_name"] = df["to_league_id"].map(TOP5_LEAGUES).fillna("Other")

    p1, p99 = df["fee_to_mv_ratio"].quantile([0.01, 0.99])
    winsor_mean = df["fee_to_mv_ratio"].clip(p1, p99).mean()

    print(f"\nTransfers with fee AND market value: {len(df)}")
    print(f"  Seasons: {df['game_season'].min()}-{df['game_season'].max()}")
    print("\nFee vs MV summary:")
    print(f"  Mean fee:           €{df['transfer_fee'].mean()/1e6:.2f}M (median €{df['transfer_fee'].median()/1e6:.2f}M)")
    print(f"  Mean MV:            €{df['mv_at_transfer'].mean()/1e6:.2f}M (median €{df['mv_at_transfer'].median()/1e6:.2f}M)")
    print(f"  Mean ratio:         {df['fee_to_mv_ratio'].mean():.2f} (1%-99% winsorized: {winsor_mean:.2f})")
    print(f"  Median ratio:       {df['fee_to_mv_ratio'].median():.2f}")
    print(f"  % Overpaying:       {(df['fee_to_mv_ratio'] > 1).mean()*100:.1f}%")
    print(f"  % Exact match:      {(df['fee_to_mv_ratio'] == 1).mean()*100:.1f}%")
    print(f"  % Underpaying:      {(df['fee_to_mv_ratio'] < 1).mean()*100:.1f}%")

    df.to_csv(OUTPUT_DIR / "04_fee_vs_market_value.csv", index=False)
    print(f"\n✓ Saved to {OUTPUT_DIR / '04_fee_vs_market_value.csv'}")

    return df


# ─────────────────────────────────────────────────────────────────────────────
# Analysis 5: Club-Level Estimated Value Gain Analysis (Spell-Bounded)
# ─────────────────────────────────────────────────────────────────────────────

def run_analysis_5_club_value_gain(con) -> pd.DataFrame:
    """Analysis 5: Club-level estimated value gain using spell-bounded valuations.

    Bounds player_valuations strictly to [transfer_date, next_transfer_date)
    to prevent pre-transfer valuations or separate club spells from leaking.
    Computes both peak valuation at club and latest/exit valuation at club.
    """
    print("\n" + "=" * 70)
    print("ANALYSIS 5: Club-Level Value Gain Analysis (Spell-Bounded)")
    print("=" * 70)

    merged = con.execute("""
        WITH ordered_transfers AS (
            SELECT
                t.player_id,
                t.player_name,
                t.transfer_date,
                t.transfer_season,
                t.to_club_id AS club_id,
                c.name AS club_name,
                t.transfer_fee,
                t.market_value_in_eur AS mv_at_arrival,
                c.domestic_competition_id AS league_id,
                LEAD(t.transfer_date) OVER (
                    PARTITION BY t.player_id ORDER BY t.transfer_date, t.transfer_fee DESC
                ) AS next_transfer_date
            FROM transfers t
            JOIN clubs c ON t.to_club_id = c.club_id
            WHERE t.transfer_date IS NOT NULL
        ),
        paid_top5 AS (
            SELECT *,
                CASE WHEN CAST(SPLIT_PART(transfer_season, '/', 1) AS INT) >= 90
                     THEN 1900 + CAST(SPLIT_PART(transfer_season, '/', 1) AS INT)
                     ELSE 2000 + CAST(SPLIT_PART(transfer_season, '/', 1) AS INT) END AS game_season
            FROM ordered_transfers
            WHERE transfer_fee > 0
              AND mv_at_arrival > 0
              AND league_id IN ('GB1','ES1','IT1','L1','FR1')
        )
        SELECT
            p.player_id,
            p.player_name,
            p.transfer_date,
            p.next_transfer_date,
            p.transfer_season,
            p.game_season,
            p.club_id,
            p.club_name,
            p.league_id,
            p.transfer_fee,
            p.mv_at_arrival,
            MAX(pv.market_value_in_eur) AS peak_mv,
            MIN(pv.market_value_in_eur) AS min_mv,
            ARG_MAX(pv.market_value_in_eur, pv.date) AS last_mv_at_club,
            COUNT(pv.date) AS valuation_count,
            MAX(pv.date) AS last_valuation_date
        FROM paid_top5 p
        JOIN player_valuations pv
          ON p.player_id = pv.player_id
         AND p.club_id = pv.current_club_id
         AND pv.date >= p.transfer_date
         AND (p.next_transfer_date IS NULL OR pv.date < p.next_transfer_date)
        WHERE p.game_season BETWEEN 2012 AND 2024
        GROUP BY 1,2,3,4,5,6,7,8,9,10,11
    """).df()

    merged["value_gain"] = merged["peak_mv"] - merged["transfer_fee"]
    merged["value_gain_pct"] = (merged["peak_mv"] - merged["transfer_fee"]) / merged["transfer_fee"] * 100
    merged["roi"] = merged["peak_mv"] / merged["transfer_fee"]
    merged["last_value_gain"] = merged["last_mv_at_club"] - merged["transfer_fee"]
    merged["last_roi"] = merged["last_mv_at_club"] / merged["transfer_fee"]

    print(f"\nTransfers with spell-bounded post-arrival valuations: {len(merged)}")
    print(f"  Unique clubs: {merged['club_id'].nunique()}")

    club_agg = merged.groupby(["club_id", "club_name", "league_id"]).agg(
        total_spent=("transfer_fee", "sum"),
        total_mv_at_arrival=("mv_at_arrival", "sum"),
        total_peak_value=("peak_mv", "sum"),
        total_last_value=("last_mv_at_club", "sum"),
        num_signings=("player_id", "count"),
        avg_roi=("roi", "mean"),
        median_roi=("roi", "median"),
        total_value_gain=("value_gain", "sum"),
        total_last_value_gain=("last_value_gain", "sum"),
    ).reset_index()

    club_agg["portfolio_roi"] = club_agg["total_peak_value"] / club_agg["total_spent"]
    club_agg["portfolio_last_roi"] = club_agg["total_last_value"] / club_agg["total_spent"]
    club_agg["league_name"] = club_agg["league_id"].map(TOP5_LEAGUES)
    club_agg = club_agg.sort_values("total_value_gain", ascending=False)

    print("\n  Top 10 clubs by spell-bounded peak value gain:")
    for _, r in club_agg.head(10).iterrows():
        print(f"    {r['club_name']:22s} spent €{r['total_spent']/1e6:6.0f}M  "
              f"peak €{r['total_peak_value']/1e6:6.0f}M (ROI {r['portfolio_roi']:.2f}x)  "
              f"latest ROI {r['portfolio_last_roi']:.2f}x  ({r['num_signings']} signings)")

    merged.to_csv(OUTPUT_DIR / "05_player_value_gain.csv", index=False)
    club_agg.to_csv(OUTPUT_DIR / "05_club_value_gain_summary.csv", index=False)
    print(f"\n✓ Saved to {OUTPUT_DIR / '05_*.csv'}")

    return merged


# ─────────────────────────────────────────────────────────────────────────────
# Analysis 6: Full Statistical Battery & Robustness Checks
# ─────────────────────────────────────────────────────────────────────────────

def run_analysis_6_statistical_tests(domestic_df: pd.DataFrame, ucl_df: pd.DataFrame,
                                      fee_mv_df: pd.DataFrame) -> dict:
    """Analysis 6: Comprehensive statistical battery with club-clustered SEs and panel FE checks."""
    print("\n" + "=" * 70)
    print("ANALYSIS 6: Statistical Tests & Econometric Robustness")
    print("=" * 70)

    results = {}

    # ─── 6A: Domestic spending vs sporting performance ───
    print("\n--- 6A: Gross Spending vs Sporting Performance (Domestic) ---")
    dom = domestic_df[domestic_df["gross_spend"] > 0].copy()
    dom["inv_position"] = dom["n_teams"] + 1 - dom["league_position"]

    # Exact Pearson & Spearman correlations across all outcome definitions
    r_pts, p_pts = stats.pearsonr(dom["log_gross_spend_m"], dom["points"])
    r_ppg, p_ppg = stats.pearsonr(dom["log_gross_spend_m"], dom["ppg"])
    r_pos_pct, p_pos_pct = stats.pearsonr(dom["log_gross_spend_m"], dom["pos_pct"])
    rho_pos, p_rho_pos = stats.spearmanr(dom["gross_spend_m"], dom["pos_pct"])
    rho_ppg, p_rho_ppg = stats.spearmanr(dom["gross_spend_m"], dom["ppg"])

    ols_ppg = cluster_ols(dom, "log_gross_spend_m", "ppg", "club_id")
    ols_pts = cluster_ols(dom, "log_gross_spend_m", "points", "club_id")
    ols_pos_pct = cluster_ols(dom, "log_gross_spend_m", "pos_pct", "club_id")

    # Full-sample (including 0-spend rows, n=1366) using asinh & Spearman
    rho_full_ppg, p_full_ppg = stats.spearmanr(domestic_df["gross_spend_m"], domestic_df["ppg"])
    ols_full_asinh = cluster_ols(domestic_df, "asinh_gross_spend_m", "ppg", "club_id")

    results["6A_domestic_spend_vs_performance"] = {
        "n_spenders": int(len(dom)),
        "n_full_sample": int(len(domestic_df)),
        "unique_clubs_spenders": int(dom["club_id"].nunique()),
        "pearson_r_log_vs_ppg": round(float(r_ppg), 4),
        "pearson_p_log_vs_ppg": float(p_ppg),
        "pearson_r_log_vs_points": round(float(r_pts), 4),
        "pearson_p_log_vs_points": float(p_pts),
        "pearson_r_log_vs_pos_pct": round(float(r_pos_pct), 4),
        "spearman_rho_spend_vs_ppg": round(float(rho_ppg), 4),
        "spearman_p_spend_vs_ppg": float(p_rho_ppg),
        "spearman_rho_spend_vs_pos_pct": round(float(rho_pos), 4),
        "spearman_p_spend_vs_pos_pct": float(p_rho_pos),
        "ols_log_spend_m_to_ppg": ols_ppg,
        "ols_log_spend_m_to_points": ols_pts,
        "ols_log_spend_m_to_pos_pct": ols_pos_pct,
        "full_sample_spearman_rho_ppg": round(float(rho_full_ppg), 4),
        "full_sample_spearman_p_ppg": float(p_full_ppg),
        "full_sample_asinh_ols_ppg": ols_full_asinh,
    }

    print(f"  Spenders n = {len(dom)} ({dom['club_id'].nunique()} clubs), Full sample n = {len(domestic_df)}")
    print(f"  Pearson r (log_spend_m vs PPG)     = {r_ppg:.4f} (p = {p_ppg:.2e})")
    print(f"  Pearson r (log_spend_m vs points)  = {r_pts:.4f} (p = {p_pts:.2e})")
    print(f"  Spearman ρ (spend vs PPG)          = {rho_ppg:.4f} (p = {p_rho_ppg:.2e})")
    print(f"  Spearman ρ (spend vs pos_pct)      = {rho_pos:.4f} (p = {p_rho_pos:.2e})")
    print(f"  OLS PPG ~ log(spend_m): slope={ols_ppg['slope']:.4f}, R²={ols_ppg['r_squared']:.4f}")
    print(f"    Naive SE={ols_ppg['naive_se']:.4f} (p={ols_ppg['naive_p']:.2e}) vs "
          f"Cluster SE={ols_ppg['cluster_se']:.4f} (p={ols_ppg['cluster_p']:.2e}, 95% CI={ols_ppg['cluster_95ci']})")
    print(f"  OLS Points ~ log(spend_m): slope={ols_pts['slope']:.4f}, R²={ols_pts['r_squared']:.4f}, "
          f"Cluster 95% CI={ols_pts['cluster_95ci']}")
    print(f"  Full-sample (n={len(domestic_df)}) Spearman ρ (spend vs PPG) = {rho_full_ppg:.4f}")

    # ─── 6B: Net spend vs performance (in €M) ───
    print("\n--- 6B: Net Spend (€M) vs Sporting Performance ---")
    r_np, p_np = stats.pearsonr(domestic_df["net_spend_m"], domestic_df["ppg"])
    rho_np, p_rho_np = stats.spearmanr(domestic_df["net_spend_m"], domestic_df["ppg"])
    ols_net_ppg = cluster_ols(domestic_df, "net_spend_m", "ppg", "club_id")
    ols_net_pts = cluster_ols(domestic_df, "net_spend_m", "points", "club_id")

    results["6B_net_spend_vs_performance"] = {
        "n": int(len(domestic_df)),
        "pearson_r_ppg": round(float(r_np), 4),
        "pearson_p_ppg": float(p_np),
        "spearman_rho_ppg": round(float(rho_np), 4),
        "spearman_p_ppg": float(p_rho_np),
        "ols_net_spend_m_to_ppg": ols_net_ppg,
        "ols_net_spend_m_to_points": ols_net_pts,
    }
    print(f"  n = {len(domestic_df)} | Pearson r (net_spend_m vs PPG) = {r_np:.4f}, R² = {ols_net_ppg['r_squared']:.4f}")
    print(f"  OLS PPG ~ net_spend_m: slope={ols_net_ppg['slope']:.5f} per €1M, "
          f"Cluster SE={ols_net_ppg['cluster_se']:.5f}, p={ols_net_ppg['cluster_p']:.2e}, 95% CI={ols_net_ppg['cluster_95ci']}")

    # ─── 6C: Per-league analysis (using normalized PPG & pos_pct) ───
    print("\n--- 6C: Per-League Correlations & Cluster-Robust Regressions ---")
    league_results = {}
    for lid, lname in TOP5_LEAGUES.items():
        sub = dom[dom["league_id"] == lid]
        rp, pp = stats.pearsonr(sub["log_gross_spend_m"], sub["ppg"])
        rs, ps = stats.spearmanr(sub["gross_spend_m"], sub["pos_pct"])
        ols_l = cluster_ols(sub, "log_gross_spend_m", "ppg", "club_id")
        league_results[lname] = {
            "n": int(len(sub)),
            "clusters": int(sub["club_id"].nunique()),
            "pearson_r_ppg": round(float(rp), 4),
            "pearson_p_ppg": float(pp),
            "spearman_rho_pos": round(float(rs), 4),
            "spearman_p_pos": float(ps),
            "r_squared_ppg": ols_l["r_squared"],
            "slope_ppg": ols_l["slope"],
            "cluster_se": ols_l["cluster_se"],
            "cluster_p": ols_l["cluster_p"],
            "cluster_95ci": ols_l["cluster_95ci"],
        }
        print(f"  {lname:16s} n={len(sub):3d} (G={sub['club_id'].nunique():2d})  "
              f"r(PPG)={rp:.3f}  ρ(pos)={rs:.3f}  R²={ols_l['r_squared']:.3f}  "
              f"slope={ols_l['slope']:.3f} CI={ols_l['cluster_95ci']}")

    results["6C_per_league"] = league_results

    # ─── 6D: UCL spending vs performance (All clubs + Top 5 subset) ───
    print("\n--- 6D: UCL Spending vs Performance ---")
    ucl_all_pos = ucl_df[(ucl_df["gross_spend"] > 0) & (ucl_df["ucl_stage_num"] > 0)].copy()
    ucl_top5_pos = ucl_all_pos[ucl_all_pos["is_top5"]].copy()
    ucl_all_pre25 = ucl_all_pos[ucl_all_pos["season"] <= 2024].copy()

    def ucl_metrics(df_u, label):
        r_st, p_st = stats.pearsonr(df_u["log_gross_spend_m"], df_u["ucl_stage_num"])
        rho_st, prho_st = stats.spearmanr(df_u["gross_spend_m"], df_u["ucl_stage_num"])
        r_pts, p_pts = stats.pearsonr(df_u["log_gross_spend_m"], df_u["ucl_points"])
        r_ppg, p_ppg = stats.pearsonr(df_u["log_gross_spend_m"], df_u["ucl_ppg"])
        ols_st = cluster_ols(df_u, "log_gross_spend_m", "ucl_stage_num", "club_id")
        ols_ppg = cluster_ols(df_u, "log_gross_spend_m", "ucl_ppg", "club_id")
        print(f"  [{label}] n={len(df_u)} (G={df_u['club_id'].nunique()}) | "
              f"stage r={r_st:.4f} (ρ={rho_st:.4f}, R²={ols_st['r_squared']:.4f}, cluster p={ols_st['cluster_p']:.3e}) | "
              f"UCL PPG r={r_ppg:.4f} (R²={ols_ppg['r_squared']:.4f}, cluster p={ols_ppg['cluster_p']:.3e})")
        return {
            "n": int(len(df_u)),
            "clusters": int(df_u["club_id"].nunique()),
            "stage_pearson_r": round(float(r_st), 4),
            "stage_spearman_rho": round(float(rho_st), 4),
            "stage_spearman_p": float(prho_st),
            "stage_ols": ols_st,
            "ucl_points_pearson_r": round(float(r_pts), 4),
            "ucl_points_pearson_p": float(p_pts),
            "ucl_ppg_pearson_r": round(float(r_ppg), 4),
            "ucl_ppg_ols": ols_ppg,
        }

    results["6D_ucl_spend_vs_performance"] = {
        "all_ucl_spenders": ucl_metrics(ucl_all_pos, "All UCL spend>0"),
        "top5_ucl_spenders": ucl_metrics(ucl_top5_pos, "Top-5 UCL spend>0"),
        "all_ucl_pre2025_complete_final": ucl_metrics(ucl_all_pre25, "All UCL 2012-2024"),
    }

    # ─── 6E: Fee vs Market Value regression ───
    print("\n--- 6E: Transfer Fee vs Market Value ---")
    rp_fm, pp_fm = stats.pearsonr(fee_mv_df["log_fee"], fee_mv_df["log_mv"])
    rs_fm, ps_fm = stats.spearmanr(fee_mv_df["transfer_fee"], fee_mv_df["mv_at_transfer"])
    ols_fm = cluster_ols(fee_mv_df, "log_mv", "log_fee", "to_club_id")

    results["6E_fee_vs_mv"] = {
        "n": int(len(fee_mv_df)),
        "pearson_r_log_log": round(float(rp_fm), 4),
        "pearson_p": float(pp_fm),
        "spearman_rho": round(float(rs_fm), 4),
        "spearman_p": float(ps_fm),
        "ols_log_mv_to_log_fee": ols_fm,
        "median_fee_to_mv_ratio": round(float(fee_mv_df["fee_to_mv_ratio"].median()), 4),
        "mean_fee_to_mv_ratio": round(float(fee_mv_df["fee_to_mv_ratio"].mean()), 4),
        "pct_overpay": round(float((fee_mv_df["fee_to_mv_ratio"] > 1).mean() * 100), 2),
        "pct_exact_match": round(float((fee_mv_df["fee_to_mv_ratio"] == 1).mean() * 100), 2),
        "pct_underpay": round(float((fee_mv_df["fee_to_mv_ratio"] < 1).mean() * 100), 2),
    }
    print(f"  n = {len(fee_mv_df)} | log-log r = {rp_fm:.4f}, ρ = {rs_fm:.4f}, R² = {ols_fm['r_squared']:.4f}")
    print(f"  slope = {ols_fm['slope']:.4f}, cluster 95% CI = {ols_fm['cluster_95ci']}")

    # ─── 6F: Econometric Robustness Checks ───
    print("\n--- 6F: Econometric Robustness Checks ---")
    # 1. Heteroscedasticity test
    pred_ppg = ols_ppg["slope"] * dom["log_gross_spend_m"] + ols_ppg["intercept"]
    resid_sq = (dom["ppg"] - pred_ppg) ** 2
    _, _, _, pv_bp, _ = stats.linregress(dom["log_gross_spend_m"], resid_sq)

    # 2. Season Fixed Effects (within-season demeaned)
    dom_sfe = dom.copy()
    dom_sfe["x_dm"] = dom_sfe["log_gross_spend_m"] - dom_sfe.groupby("season")["log_gross_spend_m"].transform("mean")
    dom_sfe["y_dm"] = dom_sfe["ppg"] - dom_sfe.groupby("season")["ppg"].transform("mean")
    sfe_res = cluster_ols(dom_sfe, "x_dm", "y_dm", "club_id", extra_dof=dom_sfe["season"].nunique() - 1)

    # 3. Club Fixed Effects (within-club demeaned, clubs >= 2 seasons)
    dom_cfe = dom[dom.groupby("club_id")["season"].transform("count") >= 2].copy()
    dom_cfe["x_dm"] = dom_cfe["log_gross_spend_m"] - dom_cfe.groupby("club_id")["log_gross_spend_m"].transform("mean")
    dom_cfe["y_dm"] = dom_cfe["ppg"] - dom_cfe.groupby("club_id")["ppg"].transform("mean")
    cfe_res = cluster_ols(dom_cfe, "x_dm", "y_dm", "club_id", extra_dof=dom_cfe["club_id"].nunique() - 1)

    # 4. Two-Way Fixed Effects (Club + Season FE)
    X_fe = pd.get_dummies(dom_cfe[["club_id", "season"]].astype(str), drop_first=True, dtype=float)
    X_tw = np.column_stack([np.ones(len(dom_cfe)), dom_cfe["log_gross_spend_m"].to_numpy(), X_fe.to_numpy()])
    y_tw = dom_cfe["ppg"].to_numpy()
    beta_tw = np.linalg.lstsq(X_tw, y_tw, rcond=None)[0]
    resid_tw = y_tw - X_tw @ beta_tw
    Z_fe = np.column_stack([np.ones(len(dom_cfe)), X_fe.to_numpy()])
    x_tilde = dom_cfe["log_gross_spend_m"].to_numpy() - Z_fe @ np.linalg.lstsq(Z_fe, dom_cfe["log_gross_spend_m"].to_numpy(), rcond=None)[0]
    y_tilde = y_tw - Z_fe @ np.linalg.lstsq(Z_fe, y_tw, rcond=None)[0]
    clusters_tw = dom_cfe["club_id"].to_numpy()
    uniq_tw = np.unique(clusters_tw)
    G_tw = len(uniq_tw)
    meat_tw = sum((np.sum(x_tilde[clusters_tw == c] * resid_tw[clusters_tw == c])) ** 2 for c in uniq_tw)
    dof_tw = (G_tw / (G_tw - 1)) * ((len(dom_cfe) - 1) / (len(dom_cfe) - X_tw.shape[1]))
    se_tw = float(np.sqrt(dof_tw * ((1.0 / np.sum(x_tilde ** 2)) ** 2) * meat_tw))
    t_tw = float(beta_tw[1] / se_tw)
    p_tw = float(2 * stats.t.sf(abs(t_tw), df=G_tw - 1))
    within_r2_tw = float(1.0 - np.sum(resid_tw ** 2) / np.sum(y_tilde ** 2))

    # 5. Club-Averaged Cross-Section (1 row per club -> zero repeated observations)
    club_avg = dom.groupby("club_id", as_index=False).agg(
        mean_spend_m=("gross_spend_m", "mean"),
        mean_ppg=("ppg", "mean"),
    )
    club_avg["log_mean_spend_m"] = np.log(club_avg["mean_spend_m"])
    avg_reg = stats.linregress(club_avg["log_mean_spend_m"], club_avg["mean_ppg"])
    t_crit_avg = stats.t.ppf(0.975, len(club_avg) - 2)

    # 6. High-coverage sub-period sensitivity (2018-2025 & 2022-2025)
    sub_2018 = cluster_ols(dom[dom["season"] >= 2018], "log_gross_spend_m", "ppg", "club_id")
    sub_2022 = cluster_ols(dom[dom["season"] >= 2022], "log_gross_spend_m", "ppg", "club_id")

    # 7. Linear vs Log diminishing returns check
    ols_linear = cluster_ols(dom, "gross_spend_m", "ppg", "club_id")

    club_counts = dom.groupby("club_id").size()
    results["6F_robustness"] = {
        "heteroscedasticity_test_p": float(pv_bp),
        "heteroscedasticity_detected": bool(pv_bp < 0.05),
        "avg_obs_per_club": round(float(club_counts.mean()), 2),
        "max_obs_per_club": int(club_counts.max()),
        "unique_clubs": int(dom["club_id"].nunique()),
        "season_fixed_effects_ppg": sfe_res,
        "club_fixed_effects_ppg": cfe_res,
        "two_way_fixed_effects_ppg": {
            "n": int(len(dom_cfe)),
            "clusters": int(G_tw),
            "slope": round(float(beta_tw[1]), 6),
            "cluster_se": round(se_tw, 6),
            "cluster_t": round(t_tw, 4),
            "cluster_p": p_tw,
            "within_r_squared": round(within_r2_tw, 5),
        },
        "club_averaged_cross_section": {
            "n_clubs": int(len(club_avg)),
            "pearson_r": round(float(avg_reg.rvalue), 4),
            "r_squared": round(float(avg_reg.rvalue ** 2), 4),
            "slope": round(float(avg_reg.slope), 4),
            "p_value": float(avg_reg.pvalue),
            "ci_95": [round(float(avg_reg.slope - t_crit_avg * avg_reg.stderr), 4),
                      round(float(avg_reg.slope + t_crit_avg * avg_reg.stderr), 4)],
        },
        "subperiod_2018_2025": sub_2018,
        "subperiod_2022_2025": sub_2022,
        "linear_spend_ols_ppg": ols_linear,
    }

    print(f"  Heteroscedasticity test p = {pv_bp:.2e} (detected={pv_bp < 0.05})")
    print(f"  Season FE (PPG ~ log_spend_m):       slope={sfe_res['slope']:.4f}, R²={sfe_res['r_squared']:.4f}, p={sfe_res['cluster_p']:.2e}")
    print(f"  Club FE (within-club):               slope={cfe_res['slope']:.4f}, R²={cfe_res['r_squared']:.4f}, p={cfe_res['cluster_p']:.4f}")
    print(f"  Two-Way FE (Club+Season):            slope={beta_tw[1]:.4f}, within_R²={within_r2_tw:.4f}, p={p_tw:.4f}")
    print(f"  Club-Averaged Cross-Section (N={len(club_avg)}): r={avg_reg.rvalue:.4f}, R²={avg_reg.rvalue**2:.4f}, p={avg_reg.pvalue:.2e}")
    print(f"  Sub-period 2018-2025 (n={sub_2018['n']}):       R²={sub_2018['r_squared']:.4f}, slope={sub_2018['slope']:.4f}")
    print(f"  Sub-period 2022-2025 (n={sub_2022['n']}):       R²={sub_2022['r_squared']:.4f}, slope={sub_2022['slope']:.4f}")
    print(f"  Linear vs Log R² (PPG):              linear={ols_linear['r_squared']:.4f} vs log={ols_ppg['r_squared']:.4f}")

    with open(OUTPUT_DIR / "06_statistical_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n✓ Saved to {OUTPUT_DIR / '06_statistical_results.json'}")
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Analysis 7: Domestic vs UCL Comparison
# ─────────────────────────────────────────────────────────────────────────────

def run_analysis_7_domestic_vs_ucl_comparison(domestic_df: pd.DataFrame, ucl_df: pd.DataFrame) -> pd.DataFrame:
    """Analysis 7: Paired comparison of Domestic vs UCL money-success relationship."""
    print("\n" + "=" * 70)
    print("ANALYSIS 7: Domestic vs UCL Comparison")
    print("=" * 70)

    comparison = domestic_df[[
        "club_id", "season", "name", "league_name", "played", "points", "ppg",
        "league_position", "pos_pct", "gross_spend", "gross_spend_m", "net_spend_m",
        "log_gross_spend_m", "asinh_gross_spend_m",
    ]].merge(
        ucl_df[[
            "club_id", "season", "ucl_matches", "ucl_wins", "ucl_stage_num",
            "ucl_stage", "ucl_points", "ucl_ppg",
        ]],
        on=["club_id", "season"],
        how="inner",
    )

    # Filter out log1p(0) distortion: primary paired test uses positive spenders (n=248),
    # while sensitivity checks full paired sample (n=258) with asinh & linear spend.
    comp_pos = comparison[comparison["gross_spend"] > 0].copy()
    comp_recent = comp_pos[comp_pos["season"] >= 2018].copy()

    r_dom_ppg, p_dom_ppg = stats.pearsonr(comp_pos["log_gross_spend_m"], comp_pos["ppg"])
    r_dom_pts, p_dom_pts = stats.pearsonr(comp_pos["log_gross_spend_m"], comp_pos["points"])
    r_ucl_stg, p_ucl_stg = stats.pearsonr(comp_pos["log_gross_spend_m"], comp_pos["ucl_stage_num"])
    r_ucl_ppg, p_ucl_ppg = stats.pearsonr(comp_pos["log_gross_spend_m"], comp_pos["ucl_ppg"])
    r_ucl_pts, p_ucl_pts = stats.pearsonr(comp_pos["log_gross_spend_m"], comp_pos["ucl_points"])

    r_outcomes_stg, _ = stats.pearsonr(comp_pos["ppg"], comp_pos["ucl_stage_num"])
    r_outcomes_ppg, _ = stats.pearsonr(comp_pos["ppg"], comp_pos["ucl_ppg"])

    z_stg, p_diff_stg = steiger_z_test(r_dom_ppg, r_ucl_stg, r_outcomes_stg, len(comp_pos))
    z_ppg, p_diff_ppg = steiger_z_test(r_dom_ppg, r_ucl_ppg, r_outcomes_ppg, len(comp_pos))

    # Full-sample (n=258) linear sensitivity
    r_dom_lin, p_dom_lin = stats.pearsonr(comparison["gross_spend_m"], comparison["ppg"])
    r_ucl_lin, p_ucl_lin = stats.pearsonr(comparison["gross_spend_m"], comparison["ucl_stage_num"])

    # Recent high-coverage subset (2018-2025)
    r_rec_dom, p_rec_dom = stats.pearsonr(comp_recent["log_gross_spend_m"], comp_recent["ppg"])
    r_rec_ucl_stg, p_rec_ucl_stg = stats.pearsonr(comp_recent["log_gross_spend_m"], comp_recent["ucl_stage_num"])
    r_rec_ucl_ppg, p_rec_ucl_ppg = stats.pearsonr(comp_recent["log_gross_spend_m"], comp_recent["ucl_ppg"])

    print(f"  Paired Top-5 UCL club-seasons: n = {len(comparison)} (positive spenders: n = {len(comp_pos)})")
    print(f"  [Positive spenders, n={len(comp_pos)}]")
    print(f"    Domestic (log_spend_m vs PPG):       r = {r_dom_ppg:.4f} (p = {p_dom_ppg:.4f})")
    print(f"    UCL      (log_spend_m vs Stage):     r = {r_ucl_stg:.4f} (p = {p_ucl_stg:.4f})")
    print(f"    UCL      (log_spend_m vs UCL PPG):   r = {r_ucl_ppg:.4f} (p = {p_ucl_ppg:.4f})")
    print(f"    Steiger z-test (Dom PPG vs UCL Stg): z = {z_stg:.4f}, p = {p_diff_stg:.4f}")
    print(f"    Steiger z-test (Dom PPG vs UCL PPG): z = {z_ppg:.4f}, p = {p_diff_ppg:.4f}")
    print(f"  [Recent 2018-2025, n={len(comp_recent)}]")
    print(f"    Domestic PPG r = {r_rec_dom:.4f} | UCL Stage r = {r_rec_ucl_stg:.4f} | UCL PPG r = {r_rec_ucl_ppg:.4f}")

    comp_results = {
        "n_paired_total": int(len(comparison)),
        "n_paired_spenders": int(len(comp_pos)),
        "spenders_domestic_ppg_r": round(float(r_dom_ppg), 4),
        "spenders_domestic_ppg_p": float(p_dom_ppg),
        "spenders_domestic_points_r": round(float(r_dom_pts), 4),
        "spenders_ucl_stage_r": round(float(r_ucl_stg), 4),
        "spenders_ucl_stage_p": float(p_ucl_stg),
        "spenders_ucl_ppg_r": round(float(r_ucl_ppg), 4),
        "spenders_ucl_ppg_p": float(p_ucl_ppg),
        "spenders_ucl_points_r": round(float(r_ucl_pts), 4),
        "steiger_z_dom_ppg_vs_ucl_stage": round(z_stg, 4),
        "steiger_p_dom_ppg_vs_ucl_stage": p_diff_stg,
        "steiger_z_dom_ppg_vs_ucl_ppg": round(z_ppg, 4),
        "steiger_p_dom_ppg_vs_ucl_ppg": p_diff_ppg,
        "full_sample_linear_dom_ppg_r": round(float(r_dom_lin), 4),
        "full_sample_linear_ucl_stage_r": round(float(r_ucl_lin), 4),
        "recent_2018_2025_n": int(len(comp_recent)),
        "recent_2018_2025_dom_ppg_r": round(float(r_rec_dom), 4),
        "recent_2018_2025_ucl_stage_r": round(float(r_rec_ucl_stg), 4),
        "recent_2018_2025_ucl_ppg_r": round(float(r_rec_ucl_ppg), 4),
    }

    with open(OUTPUT_DIR / "07_domestic_vs_ucl_comparison.json", "w") as f:
        json.dump(comp_results, f, indent=2, default=str)

    comparison.to_csv(OUTPUT_DIR / "07_domestic_vs_ucl_paired.csv", index=False)
    print(f"\n✓ Saved to {OUTPUT_DIR / '07_domestic_vs_ucl_paired.csv'}")

    return comparison


# ─────────────────────────────────────────────────────────────────────────────
# Chart Generation
# ─────────────────────────────────────────────────────────────────────────────

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

    # ─── Chart 1: Historical spending trends (season-aligned) ───
    print("\n  Generating Chart 1: Historical Spending Trends...")
    fig, ax = plt.subplots(figsize=(14, 7))
    for lid, lname in TOP5_LEAGUES.items():
        sub = trends_df[trends_df["league_id"] == lid].sort_values("game_season")
        ax.plot(sub["game_season"], sub["total_spending"] / 1e9,
                marker="o", label=lname, color=league_colors.get(lname, "gray"),
                linewidth=2, markersize=5)
    ax.axvspan(2012, 2017.5, color="gray", alpha=0.08, label="Lower player-cohort coverage (retired pre-2023)")
    ax.set_xlabel("Season (start year)")
    ax.set_ylabel("Total Transfer Spending (€ Billion)")
    ax.set_title("Season-Aligned Transfer Spending by League (2012–2025)")
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
        ax.scatter(sub["gross_spend_m"], sub["league_position"],
                   alpha=0.35, s=20, color=league_colors.get(lname, "gray"))
        ax.set_title(lname, fontsize=11)
        ax.set_xlabel("Gross Spend (€M)")
        ax.invert_yaxis()
        ax.set_xlim(left=0)
        ax.grid(True, alpha=0.3)
        if i == 0:
            ax.set_ylabel("League Position (1 = champion)")
    fig.suptitle("Transfer Spending vs League Position (Top 5 Leagues, 2012–2025)", fontsize=14, y=1.02)
    plt.tight_layout()
    fig.savefig(CHARTS_DIR / "02_spending_vs_position.png")
    plt.close()

    # ─── Chart 3: Spending vs PPG with log regression ───
    print("  Generating Chart 3: Spending vs Points Per Game (regression)...")
    fig, ax = plt.subplots(figsize=(10, 7))
    for lid, lname in TOP5_LEAGUES.items():
        sub = dom[dom["league_id"] == lid]
        ax.scatter(sub["gross_spend_m"], sub["ppg"],
                   alpha=0.35, s=20, label=lname, color=league_colors.get(lname, "gray"))

    ols_ppg = stat_results["6A_domestic_spend_vs_performance"]["ols_log_spend_m_to_ppg"]
    x_range = np.linspace(dom["log_gross_spend_m"].min(), dom["log_gross_spend_m"].max(), 200)
    ax.plot(np.exp(x_range), ols_ppg["slope"] * x_range + ols_ppg["intercept"],
            color="red", linewidth=2.2, linestyle="--",
            label=f"Log OLS (R²={ols_ppg['r_squared']:.3f}, r={stat_results['6A_domestic_spend_vs_performance']['pearson_r_log_vs_ppg']:.3f})")
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"€{x:g}M"))
    ax.set_xlabel("Gross Transfer Spending (€M, log scale)")
    ax.set_ylabel("Points Per Game (PPG)")
    ax.set_title("Transfer Spending vs Points Per Game (Top 5 Leagues, 2012–2025)")
    ax.legend(loc="lower right", framealpha=0.9)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    fig.savefig(CHARTS_DIR / "03_spending_vs_points_regression.png")
    plt.close()

    # ─── Chart 4: UCL Stage & Points vs Spending (All UCL Clubs) ───
    print("  Generating Chart 4: UCL Performance vs Spending...")
    fig, axes = plt.subplots(1, 2, figsize=(15, 6))
    ucl_pos = ucl_df[(ucl_df["gross_spend"] > 0) & (ucl_df["ucl_stage_num"] > 0)].copy()

    ax = axes[0]
    for is_t5, lbl, col in [(True, "Top-5 League Clubs", "#1a237e"), (False, "Other League Clubs", "#ff8f00")]:
        sub = ucl_pos[ucl_pos["is_top5"] == is_t5]
        ax.scatter(sub["gross_spend_m"], sub["ucl_stage_num"], alpha=0.45, s=28, label=f"{lbl} (n={len(sub)})", color=col)
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"€{x:g}M"))
    ax.set_yticks([1.0, 1.5, 2.0, 3.0, 4.0, 5.0])
    ax.set_yticklabels(["Group", "KO Playoff", "R16", "QF", "SF", "Final"])
    ax.set_xlabel("Gross Spend (€M, log scale)")
    ax.set_ylabel("UCL Stage Reached")
    ax.set_title(f"UCL Stage vs Spending (All Clubs, n={len(ucl_pos)})")
    ax.legend(loc="lower right")
    ax.grid(True, alpha=0.3)

    ax = axes[1]
    for is_t5, lbl, col in [(True, "Top-5 League Clubs", "#1a237e"), (False, "Other League Clubs", "#ff8f00")]:
        sub = ucl_pos[ucl_pos["is_top5"] == is_t5]
        ax.scatter(sub["gross_spend_m"], sub["ucl_ppg"], alpha=0.45, s=28, label=lbl, color=col)
    ucl_ppg_ols = stat_results["6D_ucl_spend_vs_performance"]["all_ucl_spenders"]["ucl_ppg_ols"]
    x_u = np.linspace(ucl_pos["log_gross_spend_m"].min(), ucl_pos["log_gross_spend_m"].max(), 100)
    ax.plot(np.exp(x_u), ucl_ppg_ols["slope"] * x_u + ucl_ppg_ols["intercept"],
            "r--", linewidth=2, label=f"Log OLS (R²={ucl_ppg_ols['r_squared']:.3f})")
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"€{x:g}M"))
    ax.set_xlabel("Gross Spend (€M, log scale)")
    ax.set_ylabel("UCL Points Per Game")
    ax.set_title("UCL PPG vs Spending (All Clubs)")
    ax.legend(loc="lower right")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    fig.savefig(CHARTS_DIR / "04_ucl_stage_vs_spending.png")
    plt.close()

    # ─── Chart 5: Fee vs Market Value ───
    print("  Generating Chart 5: Transfer Fee vs Market Value...")
    fig, ax = plt.subplots(figsize=(10, 8))
    plot_df = fee_mv_df.sample(min(5000, len(fee_mv_df)), random_state=42)
    top5_mask = plot_df["is_top5"]
    ax.scatter(plot_df.loc[~top5_mask, "mv_at_transfer"] / 1e6,
               plot_df.loc[~top5_mask, "transfer_fee"] / 1e6,
               alpha=0.2, s=15, color="gray", label="Other leagues")
    ax.scatter(plot_df.loc[top5_mask, "mv_at_transfer"] / 1e6,
               plot_df.loc[top5_mask, "transfer_fee"] / 1e6,
               alpha=0.3, s=15, color="#2196F3", label="Top 5 leagues")
    max_val = max(plot_df["transfer_fee"].max(), plot_df["mv_at_transfer"].max()) / 1e6
    ax.plot([0, max_val], [0, max_val], "r--", linewidth=1.5, label="Fee = Market Value (1:1)", alpha=0.7)
    ax.set_xlabel("Market Value at Transfer (€M)")
    ax.set_ylabel("Transfer Fee Paid (€M)")
    ax.set_title(f"Transfer Fee vs Estimated Market Value (n={len(fee_mv_df):,}, R²={stat_results['6E_fee_vs_mv']['ols_log_mv_to_log_fee']['r_squared']:.3f})")
    ax.legend(loc="upper left")
    ax.grid(True, alpha=0.3)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    plt.tight_layout()
    fig.savefig(CHARTS_DIR / "05_fee_vs_market_value.png")
    plt.close()

    # ─── Chart 6: Domestic vs UCL comparison (paired positive spenders) ───
    print("  Generating Chart 6: Domestic vs UCL Comparison...")
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    comparison = pd.read_csv(OUTPUT_DIR / "07_domestic_vs_ucl_paired.csv")
    comp_pos = comparison[comparison["gross_spend"] > 0].copy()
    x_plot = np.linspace(comp_pos["log_gross_spend_m"].min(), comp_pos["log_gross_spend_m"].max(), 100)

    ax = axes[0]
    ax.scatter(comp_pos["gross_spend_m"], comp_pos["ppg"], alpha=0.45, s=25, color="#3d195b")
    sl1, int1, rv1, _, _ = stats.linregress(comp_pos["log_gross_spend_m"], comp_pos["ppg"])
    ax.plot(np.exp(x_plot), sl1 * x_plot + int1, "r--", linewidth=2, label=f"r={rv1:.3f}, R²={rv1**2:.3f}")
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"€{x:g}M"))
    ax.set_xlabel("Gross Spend (€M, log scale)")
    ax.set_ylabel("Domestic League PPG")
    ax.set_title(f"Domestic: Spending vs PPG\n(Top-5 UCL spenders, n={len(comp_pos)})")
    ax.legend()
    ax.grid(True, alpha=0.3)

    ax = axes[1]
    ax.scatter(comp_pos["gross_spend_m"], comp_pos["ucl_ppg"], alpha=0.45, s=25, color="#1a237e")
    sl2, int2, rv2, _, _ = stats.linregress(comp_pos["log_gross_spend_m"], comp_pos["ucl_ppg"])
    ax.plot(np.exp(x_plot), sl2 * x_plot + int2, "r--", linewidth=2, label=f"r={rv2:.3f}, R²={rv2**2:.3f}")
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"€{x:g}M"))
    ax.set_xlabel("Gross Spend (€M, log scale)")
    ax.set_ylabel("UCL Points Per Game")
    ax.set_title(f"UCL: Spending vs UCL PPG\n(Same Top-5 UCL spenders, n={len(comp_pos)})")
    ax.legend()
    ax.grid(True, alpha=0.3)

    fig.suptitle("Among Elite Top-5 UCL Clubs, Range Restriction Weakens Both Correlations", fontsize=14, y=1.02)
    plt.tight_layout()
    fig.savefig(CHARTS_DIR / "06_domestic_vs_ucl_comparison.png")
    plt.close()

    # ─── Chart 7: Correlation by League ───
    print("  Generating Chart 7: Spending Correlation by League...")
    fig, ax = plt.subplots(figsize=(10, 6))
    per_l = stat_results["6C_per_league"]
    league_stats = [
        {"league": lname, "r": per_l[lname]["pearson_r_ppg"], "n": per_l[lname]["n"],
         "color": league_colors.get(lname, "gray")}
        for lname in TOP5_LEAGUES.values() if lname in per_l
    ]
    league_stats = sorted(league_stats, key=lambda d: d["r"])
    bars = ax.barh([d["league"] for d in league_stats], [d["r"] for d in league_stats],
                   color=[d["color"] for d in league_stats], edgecolor="white", linewidth=0.5)
    for bar, row in zip(bars, league_stats):
        ax.text(bar.get_width() + 0.01, bar.get_y() + bar.get_height() / 2,
                f"r={row['r']:.3f} (n={row['n']})", va="center", fontsize=10)
    ax.set_xlabel("Pearson Correlation (log gross spend €M vs Points Per Game)")
    ax.set_title("Money-Success Correlation Strength by League (2012–2025)")
    ax.set_xlim(0, max(d["r"] for d in league_stats) * 1.32)
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
        trends_df = run_analysis_1_historical_trends(con)
        domestic_df = run_analysis_2_domestic_spending_vs_performance(con)
        ucl_df = run_analysis_3_ucl_spending_vs_performance(con)
        fee_mv_df = run_analysis_4_fee_vs_market_value(con)
        _ = run_analysis_5_club_value_gain(con)
        stat_results = run_analysis_6_statistical_tests(domestic_df, ucl_df, fee_mv_df)
        _ = run_analysis_7_domestic_vs_ucl_comparison(domestic_df, ucl_df)

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
