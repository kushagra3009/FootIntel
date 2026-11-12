"""
Independent verification tests for Phase 2 statistical analysis outputs.
Cross-checks generated CSVs/JSONs against DuckDB source data and independent SciPy calculations.
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

    def test_all_output_files_and_charts_exist(self):
        expected_outputs = [
            "01_historical_trends_by_league.csv",
            "01_historical_trends_aggregate.csv",
            "02_domestic_spending_vs_performance.csv",
            "03_ucl_spending_vs_performance.csv",
            "04_fee_vs_market_value.csv",
            "05_player_value_gain.csv",
            "05_club_value_gain_summary.csv",
            "06_statistical_results.json",
            "07_domestic_vs_ucl_paired.csv",
            "07_domestic_vs_ucl_comparison.json",
        ]
        for fname in expected_outputs:
            p = OUT_DIR / fname
            self.assertTrue(p.exists() and p.stat().st_size > 0, f"Missing or empty: {fname}")

        expected_charts = [
            "01_spending_trends.png",
            "02_spending_vs_position.png",
            "03_spending_vs_points_regression.png",
            "04_ucl_stage_vs_spending.png",
            "05_fee_vs_market_value.png",
            "06_domestic_vs_ucl_comparison.png",
            "07_correlation_by_league.png",
        ]
        for cname in expected_charts:
            p = CHARTS_DIR / cname
            self.assertTrue(p.exists() and p.stat().st_size > 1000, f"Missing or small chart: {cname}")

    def test_analysis_1_season_aligned_totals_match_duckdb(self):
        agg = pd.read_csv(OUT_DIR / "01_historical_trends_aggregate.csv")
        self.assertEqual(len(agg), 14)
        db_2022 = self.con.execute("""
            WITH top5_2022 AS (
                SELECT DISTINCT home_club_id AS club_id
                FROM games
                WHERE competition_id IN ('GB1','ES1','IT1','L1','FR1') AND season = 2022
            )
            SELECT SUM(CASE WHEN t.transfer_fee > 0 THEN t.transfer_fee ELSE 0 END)
            FROM transfers t
            JOIN top5_2022 c ON t.to_club_id = c.club_id
            WHERE t.transfer_season = '22/23'
        """).fetchone()[0]
        csv_2022 = agg.loc[agg["game_season"] == 2022, "total_spending"].iloc[0]
        self.assertAlmostEqual(csv_2022, db_2022, places=2)

    def test_analysis_2_no_duplicate_club_seasons_and_r_matches(self):
        dom = pd.read_csv(OUT_DIR / "02_domestic_spending_vs_performance.csv")
        self.assertEqual(len(dom), 1366)
        self.assertEqual(dom.duplicated(subset=["club_id", "season"]).sum(), 0)
        sub = dom[dom["gross_spend"] > 0]
        r_ppg, _ = stats.pearsonr(np.log(sub["gross_spend"] / 1e6), sub["ppg"])
        self.assertAlmostEqual(
            self.stats["6A_domestic_spend_vs_performance"]["pearson_r_log_vs_ppg"],
            round(r_ppg, 4),
            places=4,
        )
        self.assertAlmostEqual(
            self.stats["6A_domestic_spend_vs_performance"]["ols_log_spend_m_to_ppg"]["r_squared"],
            round(r_ppg ** 2, 4),
            places=4,
        )

    def test_analysis_3_ucl_no_duplicates(self):
        ucl = pd.read_csv(OUT_DIR / "03_ucl_spending_vs_performance.csv")
        self.assertEqual(ucl.duplicated(subset=["club_id", "season"]).sum(), 0)
        self.assertEqual(len(ucl), 437)
        self.assertEqual(int(ucl["is_top5"].sum()), 258)

    def test_analysis_4_fee_vs_mv(self):
        df4 = pd.read_csv(OUT_DIR / "04_fee_vs_market_value.csv")
        self.assertEqual(len(df4), 15829)
        r_val, _ = stats.pearsonr(df4["log_mv"], df4["log_fee"])
        self.assertAlmostEqual(self.stats["6E_fee_vs_mv"]["pearson_r_log_log"], round(r_val, 4), places=4)

    def test_analysis_5_canonical_clubs_no_splits(self):
        summary = pd.read_csv(OUT_DIR / "05_club_value_gain_summary.csv")
        self.assertEqual(summary["club_id"].duplicated().sum(), 0)
        self.assertEqual(len(summary), summary["club_id"].nunique())

    def test_analysis_7_paired_matches(self):
        paired = pd.read_csv(OUT_DIR / "07_domestic_vs_ucl_paired.csv")
        self.assertEqual(len(paired), 258)
        pos = paired[paired["gross_spend"] > 0]
        self.assertEqual(len(pos), 248)
        r_dom, _ = stats.pearsonr(pos["log_gross_spend_m"], pos["ppg"])
        r_ucl_ppg, _ = stats.pearsonr(pos["log_gross_spend_m"], pos["ucl_ppg"])
        self.assertAlmostEqual(self.comp["spenders_domestic_ppg_r"], round(r_dom, 4), places=4)
        self.assertAlmostEqual(self.comp["spenders_ucl_ppg_r"], round(r_ucl_ppg, 4), places=4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
