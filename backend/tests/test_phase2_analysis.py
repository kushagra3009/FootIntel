"""
Independent statistical & DuckDB verification suite for Phase 2.
Recomputes correlations, OLS slopes, R-squared, club-clustered SEs, 95% CIs,
fixed effects, Steiger z-test, and DuckDB aggregates from scratch to validate outputs.
"""

import json
import unittest
from pathlib import Path
import duckdb
import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "processed" / "footintel.duckdb"
OUT_DIR = PROJECT_ROOT / "data" / "processed" / "analysis_outputs"
CHARTS_DIR = PROJECT_ROOT / "data" / "processed" / "charts"


def independent_cluster_se(x: np.ndarray, y: np.ndarray, clusters: np.ndarray, extra_dof: int = 0):
    """Independent reference implementation of Liang-Zeger cluster-robust OLS."""
    n = len(x)
    X = np.column_stack([np.ones(n), x])
    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    resid = y - X @ beta
    XtX_inv = np.linalg.inv(X.T @ X)
    uniq = np.unique(clusters)
    G = len(uniq)
    meat = sum(np.outer(X[clusters == c].T @ resid[clusters == c], X[clusters == c].T @ resid[clusters == c]) for c in uniq)
    dof = (G / (G - 1)) * ((n - 1) / (n - 2 - extra_dof))
    V = dof * (XtX_inv @ meat @ XtX_inv)
    se = float(np.sqrt(V[1, 1]))
    t_stat = float(beta[1] / se)
    p_val = float(2 * stats.t.sf(abs(t_stat), df=G - 1))
    t_crit = float(stats.t.ppf(0.975, df=G - 1))
    ci = [float(beta[1] - t_crit * se), float(beta[1] + t_crit * se)]
    r2 = float(1 - np.sum(resid ** 2) / np.sum((y - y.mean()) ** 2))
    return float(beta[1]), se, t_stat, p_val, ci, r2


class TestPhase2Outputs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.con = duckdb.connect(str(DB_PATH), read_only=True)
        with open(OUT_DIR / "06_statistical_results.json") as f:
            cls.stats = json.load(f)
        with open(OUT_DIR / "07_domestic_vs_ucl_comparison.json") as f:
            cls.comp = json.load(f)

    @classmethod
    def tearDownClass(cls):
        cls.con.close()

    def test_01_historical_trends_and_coverage_match_duckdb(self):
        agg = pd.read_csv(OUT_DIR / "01_historical_trends_aggregate.csv")
        self.assertEqual(len(agg), 14)
        self.assertIn("pct_active_players_covered", agg.columns)
        # Verify 2012 and 2023 directly against DuckDB
        for yr, ts in [(2012, "12/13"), (2023, "23/24")]:
            db_spend = self.con.execute(f"""
                WITH top5_yr AS (
                    SELECT DISTINCT home_club_id AS club_id
                    FROM games
                    WHERE competition_id IN ('GB1','ES1','IT1','L1','FR1') AND season = {yr}
                )
                SELECT SUM(CASE WHEN t.transfer_fee > 0 THEN t.transfer_fee ELSE 0 END)
                FROM transfers t
                JOIN top5_yr c ON t.to_club_id = c.club_id
                WHERE t.transfer_season = '{ts}'
            """).fetchone()[0]
            csv_spend = agg.loc[agg["game_season"] == yr, "total_spending"].iloc[0]
            self.assertAlmostEqual(csv_spend, db_spend, places=2)

        cov_2012 = agg.loc[agg["game_season"] == 2012, "pct_active_players_covered"].iloc[0]
        cov_2023 = agg.loc[agg["game_season"] == 2023, "pct_active_players_covered"].iloc[0]
        self.assertLess(cov_2012, 20.0)
        self.assertGreater(cov_2023, 95.0)

    def test_02_domestic_standings_and_6a_6b_6c_calculations(self):
        dom = pd.read_csv(OUT_DIR / "02_domestic_spending_vs_performance.csv")
        self.assertEqual(len(dom), 1366)
        self.assertEqual(dom.duplicated(subset=["club_id", "season"]).sum(), 0)
        self.assertTrue(((dom["pos_pct"] >= 0.0) & (dom["pos_pct"] <= 1.0)).all())

        # Cross-check one club-season standings & spending directly against DuckDB (Man City 2022)
        db_mc = self.con.execute("""
            SELECT
                SUM(CASE WHEN (home_club_id=281 AND home_club_goals>away_club_goals) OR (away_club_id=281 AND away_club_goals>home_club_goals) THEN 3
                         WHEN home_club_goals=away_club_goals THEN 1 ELSE 0 END) AS pts,
                COUNT(*) AS mp
            FROM games
            WHERE competition_id='GB1' AND season=2022 AND (home_club_id=281 OR away_club_id=281)
        """).fetchone()
        row_mc = dom[(dom["club_id"] == 281) & (dom["season"] == 2022)].iloc[0]
        self.assertEqual(int(row_mc["points"]), int(db_mc[0]))
        self.assertEqual(int(row_mc["played"]), int(db_mc[1]))

        # Independently verify 6A: Pearson, Spearman, OLS, Cluster SE, p-val, 95% CI
        sub = dom[dom["gross_spend"] > 0]
        x = np.log(sub["gross_spend"] / 1e6).to_numpy()
        y = sub["ppg"].to_numpy()
        r_ppg, p_ppg = stats.pearsonr(x, y)
        rho_ppg, prho_ppg = stats.spearmanr(sub["gross_spend_m"], y)
        slope, se_c, _, p_c, ci_c, r2 = independent_cluster_se(x, y, sub["club_id"].to_numpy())

        s6a = self.stats["6A_domestic_spend_vs_performance"]
        self.assertAlmostEqual(s6a["pearson_r_log_vs_ppg"], round(r_ppg, 4), places=4)
        self.assertAlmostEqual(s6a["spearman_rho_spend_vs_ppg"], round(rho_ppg, 4), places=4)
        ols = s6a["ols_log_spend_m_to_ppg"]
        self.assertAlmostEqual(ols["slope"], round(slope, 6), places=5)
        self.assertAlmostEqual(ols["cluster_se"], round(se_c, 6), places=5)
        self.assertAlmostEqual(ols["cluster_p"], p_c, places=10)
        self.assertAlmostEqual(ols["r_squared"], round(r2, 4), places=4)
        self.assertAlmostEqual(ols["cluster_95ci"][0], round(ci_c[0], 6), places=5)
        self.assertAlmostEqual(ols["cluster_95ci"][1], round(ci_c[1], 6), places=5)

        # Independently verify 6B: Net spend (€M)
        slope_n, se_n, _, p_n, _, r2_n = independent_cluster_se(
            dom["net_spend_m"].to_numpy(), dom["ppg"].to_numpy(), dom["club_id"].to_numpy()
        )
        ols_net = self.stats["6B_net_spend_vs_performance"]["ols_net_spend_m_to_ppg"]
        self.assertAlmostEqual(ols_net["slope"], round(slope_n, 6), places=5)
        self.assertAlmostEqual(ols_net["cluster_se"], round(se_n, 6), places=5)
        self.assertAlmostEqual(ols_net["r_squared"], round(r2_n, 4), places=4)

        # Independently verify 6C: Ligue 1 & Premier League
        for lid, lname in [("FR1", "Ligue 1"), ("GB1", "Premier League")]:
            s_l = sub[sub["league_id"] == lid]
            r_l, _ = stats.pearsonr(np.log(s_l["gross_spend_m"]), s_l["ppg"])
            self.assertAlmostEqual(self.stats["6C_per_league"][lname]["pearson_r_ppg"], round(r_l, 4), places=4)

    def test_03_ucl_calculations_and_stage_mapping(self):
        ucl = pd.read_csv(OUT_DIR / "03_ucl_spending_vs_performance.csv")
        self.assertEqual(ucl.duplicated(subset=["club_id", "season"]).sum(), 0)
        self.assertEqual(len(ucl), 437)
        self.assertEqual(int((ucl["ucl_stage_num"] == 1.5).sum()), 15)  # 2024 & 2025 intermediate stage dropouts

        ucl_pos = ucl[ucl["gross_spend"] > 0]
        r_stg, _ = stats.pearsonr(np.log(ucl_pos["gross_spend_m"]), ucl_pos["ucl_stage_num"])
        r_ppg, _ = stats.pearsonr(np.log(ucl_pos["gross_spend_m"]), ucl_pos["ucl_ppg"])
        s6d = self.stats["6D_ucl_spend_vs_performance"]["all_ucl_spenders"]
        self.assertAlmostEqual(s6d["stage_pearson_r"], round(r_stg, 4), places=4)
        self.assertAlmostEqual(s6d["ucl_ppg_pearson_r"], round(r_ppg, 4), places=4)

    def test_04_fee_vs_market_value_statistics(self):
        df4 = pd.read_csv(OUT_DIR / "04_fee_vs_market_value.csv")
        self.assertEqual(len(df4), 15829)
        r_val, _ = stats.pearsonr(df4["log_mv"], df4["log_fee"])
        rho_val, _ = stats.spearmanr(df4["mv_at_transfer"], df4["transfer_fee"])
        slope, se_c, _, _, ci_c, r2 = independent_cluster_se(
            df4["log_mv"].to_numpy(), df4["log_fee"].to_numpy(), df4["to_club_id"].to_numpy()
        )
        s6e = self.stats["6E_fee_vs_mv"]
        self.assertAlmostEqual(s6e["pearson_r_log_log"], round(r_val, 4), places=4)
        self.assertAlmostEqual(s6e["spearman_rho"], round(rho_val, 4), places=4)
        self.assertAlmostEqual(s6e["median_fee_to_mv_ratio"], round(float(df4["fee_to_mv_ratio"].median()), 4), places=4)
        self.assertAlmostEqual(s6e["ols_log_mv_to_log_fee"]["slope"], round(slope, 6), places=5)
        self.assertAlmostEqual(s6e["ols_log_mv_to_log_fee"]["r_squared"], round(r2, 4), places=4)
        self.assertAlmostEqual(s6e["ols_log_mv_to_log_fee"]["cluster_se"], round(se_c, 6), places=5)

    def test_05_spell_bounded_valuations_and_canonical_clubs(self):
        pv_df = pd.read_csv(OUT_DIR / "05_player_value_gain.csv")
        summary = pd.read_csv(OUT_DIR / "05_club_value_gain_summary.csv")
        self.assertEqual(summary["club_id"].duplicated().sum(), 0)
        self.assertEqual(len(summary), 175)
        # Ensure misleading "roi" column names were removed
        self.assertNotIn("portfolio_roi", summary.columns)
        self.assertIn("portfolio_peak_mv_multiple", summary.columns)
        self.assertIn("portfolio_latest_mv_multiple", summary.columns)

        # Verify no valuation dates precede transfer_date or reach next_transfer_date for Dortmund (club_id=16)
        bvb_check = self.con.execute("""
            WITH ordered_t AS (
                SELECT player_id, transfer_date, transfer_season, to_club_id, transfer_fee, market_value_in_eur,
                       LEAD(transfer_date) OVER (PARTITION BY player_id ORDER BY transfer_date, transfer_fee DESC) AS next_td
                FROM transfers
                WHERE transfer_date IS NOT NULL
            )
            SELECT COUNT(DISTINCT (ot.player_id || '_' || ot.transfer_date)),
                   SUM(ot.transfer_fee)
            FROM (
                SELECT ot.*, MAX(pv.market_value_in_eur) AS peak_mv
                FROM ordered_t ot
                JOIN player_valuations pv
                  ON ot.player_id = pv.player_id
                 AND ot.to_club_id = pv.current_club_id
                 AND pv.date >= ot.transfer_date
                 AND (ot.next_td IS NULL OR pv.date < ot.next_td)
                WHERE ot.to_club_id = 16
                  AND ot.transfer_fee > 0 AND ot.market_value_in_eur > 0
                  AND CAST(SPLIT_PART(ot.transfer_season, '/', 1) AS INT) BETWEEN 12 AND 24
                GROUP BY ALL
            ) ot
        """).fetchone()
        bvb_row = summary[summary["club_id"] == 16].iloc[0]
        self.assertEqual(int(bvb_row["num_signings"]), int(bvb_check[0]))
        self.assertAlmostEqual(float(bvb_row["total_spent"]), float(bvb_check[1]), places=2)

    def test_06_robustness_fixed_effects_and_cross_section(self):
        dom = pd.read_csv(OUT_DIR / "02_domestic_spending_vs_performance.csv")
        sub = dom[dom["gross_spend"] > 0].copy()
        # Season FE
        x_sfe = (sub["log_gross_spend_m"] - sub.groupby("season")["log_gross_spend_m"].transform("mean")).to_numpy()
        y_sfe = (sub["ppg"] - sub.groupby("season")["ppg"].transform("mean")).to_numpy()
        sl_s, se_s, _, p_s, _, r2_s = independent_cluster_se(
            x_sfe, y_sfe, sub["club_id"].to_numpy(), extra_dof=sub["season"].nunique() - 1
        )
        s6f = self.stats["6F_robustness"]
        self.assertAlmostEqual(s6f["season_fixed_effects_ppg"]["slope"], round(sl_s, 6), places=5)
        self.assertAlmostEqual(s6f["season_fixed_effects_ppg"]["r_squared"], round(r2_s, 4), places=4)
        self.assertAlmostEqual(s6f["season_fixed_effects_ppg"]["cluster_se"], round(se_s, 6), places=5)

        # Club-Averaged Cross Section
        cavg = sub.groupby("club_id", as_index=False).agg(m_sp=("gross_spend_m", "mean"), m_ppg=("ppg", "mean"))
        reg = stats.linregress(np.log(cavg["m_sp"]), cavg["m_ppg"])
        self.assertEqual(s6f["club_averaged_cross_section"]["n_clubs"], len(cavg))
        self.assertAlmostEqual(s6f["club_averaged_cross_section"]["r_squared"], round(reg.rvalue ** 2, 4), places=4)

        # Sub-period 2022-2025
        sub22 = sub[sub["season"] >= 2022]
        sl_22, _, _, _, _, r2_22 = independent_cluster_se(
            sub22["log_gross_spend_m"].to_numpy(), sub22["ppg"].to_numpy(), sub22["club_id"].to_numpy()
        )
        self.assertAlmostEqual(s6f["subperiod_2022_2025"]["slope"], round(sl_22, 6), places=5)
        self.assertAlmostEqual(s6f["subperiod_2022_2025"]["r_squared"], round(r2_22, 4), places=4)

    def test_07_paired_comparison_and_steiger_test(self):
        paired = pd.read_csv(OUT_DIR / "07_domestic_vs_ucl_paired.csv")
        pos = paired[paired["gross_spend"] > 0]
        r12, _ = stats.pearsonr(pos["log_gross_spend_m"], pos["ppg"])
        r13, _ = stats.pearsonr(pos["log_gross_spend_m"], pos["ucl_ppg"])
        r23, _ = stats.pearsonr(pos["ppg"], pos["ucl_ppg"])
        rm2 = (r12 ** 2 + r13 ** 2) / 2.0
        f = min((1.0 - r23) / (2.0 * (1.0 - rm2)), 1.0 / (1.0 - rm2))
        h = (1.0 - f * rm2) / (1.0 - rm2)
        z = (np.arctanh(r12) - np.arctanh(r13)) * np.sqrt((len(pos) - 3) / (2.0 * (1.0 - r23) * h))
        self.assertAlmostEqual(self.comp["spenders_domestic_ppg_r"], round(r12, 4), places=4)
        self.assertAlmostEqual(self.comp["spenders_ucl_ppg_r"], round(r13, 4), places=4)
        self.assertAlmostEqual(self.comp["steiger_z_dom_ppg_vs_ucl_ppg"], round(float(z), 4), places=4)

    def test_08_all_charts_exist(self):
        for cname in [
            "01_spending_trends.png", "02_spending_vs_position.png",
            "03_spending_vs_points_regression.png", "04_ucl_stage_vs_spending.png",
            "05_fee_vs_market_value.png", "06_domestic_vs_ucl_comparison.png",
            "07_correlation_by_league.png",
        ]:
            p = CHARTS_DIR / cname
            self.assertTrue(p.exists() and p.stat().st_size > 10000, f"Chart invalid: {cname}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
