"""
Comprehensive REST API integration & validation test suite for FootIntel Phase 3.
Validates every endpoint, schema, filter, pagination, error handling, CORS,
and exact numerical agreement with validated Phase 2 outputs and DuckDB.
"""

import json
import os
import unittest
from pathlib import Path
import duckdb
from fastapi.testclient import TestClient
import pandas as pd

from api.main import app

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "processed" / "footintel.duckdb"
OUT_DIR = PROJECT_ROOT / "data" / "processed" / "analysis_outputs"


class TestPhase3API(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.con = duckdb.connect(str(DB_PATH), read_only=True)
        with open(OUT_DIR / "06_statistical_results.json", encoding="utf-8") as f:
            cls.stats = json.load(f)
        with open(OUT_DIR / "07_domestic_vs_ucl_comparison.json", encoding="utf-8") as f:
            cls.comp = json.load(f)

    @classmethod
    def tearDownClass(cls):
        cls.con.close()

    def test_01_root_docs_and_health(self):
        r_root = self.client.get("/")
        self.assertEqual(r_root.status_code, 200)
        self.assertIn("endpoints", r_root.json())

        r_docs = self.client.get("/docs")
        self.assertEqual(r_docs.status_code, 200)

        r_openapi = self.client.get("/openapi.json")
        self.assertEqual(r_openapi.status_code, 200)
        paths = r_openapi.json()["paths"]
        self.assertIn("/api/v1/overview", paths)
        self.assertIn("/api/v1/statistics", paths)

        r_health = self.client.get("/health")
        self.assertEqual(r_health.status_code, 200)
        h = r_health.json()
        self.assertEqual(h["status"], "ok")
        self.assertTrue(h["database_connected"])
        self.assertTrue(h["outputs_available"])
        db_transfers = self.con.execute("SELECT COUNT(*) FROM transfers").fetchone()[0]
        self.assertEqual(h["tables"]["transfers"], db_transfers)

    def test_02_overview_matches_duckdb_and_phase2(self):
        resp = self.client.get("/api/v1/overview")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["research_question"], "Does Money Actually Buy Success in Professional Football?")
        self.assertIn("observational", data["methodology_disclaimer"].lower())
        kpis = data["kpis"]

        db_transfers = self.con.execute("SELECT COUNT(*) FROM transfers").fetchone()[0]
        db_games = self.con.execute("SELECT COUNT(*) FROM games").fetchone()[0]
        self.assertEqual(kpis["total_transfers_db"], db_transfers)
        self.assertEqual(kpis["total_games_db"], db_games)
        self.assertEqual(kpis["top5_domestic_observations"], self.stats["6A_domestic_spend_vs_performance"]["n_full_sample"])
        self.assertEqual(kpis["fee_vs_mv_sample_size"], self.stats["6E_fee_vs_mv"]["n"])
        self.assertEqual(len(data["historical_summary"]), 14)

    def test_03_historical_trends_filters_pagination_and_warnings(self):
        resp = self.client.get("/api/v1/trends?league_id=GB1&start_season=2018&end_season=2025&limit=5&offset=2")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("last_season >= 2023", data["coverage_warning"]["summary"])
        self.assertEqual(len(data["aggregate"]), 8)
        self.assertEqual(data["pagination"]["total"], 8)
        self.assertEqual(data["pagination"]["returned"], 5)
        self.assertTrue(all(r["league_id"] == "GB1" for r in data["by_league"]))

        agg_csv = pd.read_csv(OUT_DIR / "01_historical_trends_aggregate.csv")
        expected_2023 = float(agg_csv.loc[agg_csv["game_season"] == 2023, "total_spending"].iloc[0])
        actual_2023 = next(r["total_spending"] for r in data["aggregate"] if r["game_season"] == 2023)
        self.assertAlmostEqual(actual_2023, expected_2023, places=2)

    def test_04_domestic_performance_filtering_sorting_and_stats(self):
        resp = self.client.get(
            "/api/v1/domestic?league_id=ES1&season=2022&positive_spend_only=true&sort_by=ppg&sort_order=desc&limit=10"
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(
            data["regression_summary"]["6A_gross_spend"]["ols_log_spend_m_to_ppg"]["r_squared"],
            self.stats["6A_domestic_spend_vs_performance"]["ols_log_spend_m_to_ppg"]["r_squared"],
        )
        self.assertEqual(len(data["league_summaries"]), 5)
        obs = data["observations"]
        self.assertGreater(len(obs), 0)
        self.assertTrue(all(o["league_id"] == "ES1" and o["season"] == 2022 and o["gross_spend"] > 0 for o in obs))
        ppgs = [o["ppg"] for o in obs]
        self.assertEqual(ppgs, sorted(ppgs, reverse=True))

    def test_05_ucl_and_paired_endpoints(self):
        resp = self.client.get("/api/v1/ucl?is_top5=true&ucl_stage=Final&limit=20")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(
            data["statistical_summary"]["all_ucl_spenders"]["ucl_ppg_pearson_r"],
            self.stats["6D_ucl_spend_vs_performance"]["all_ucl_spenders"]["ucl_ppg_pearson_r"],
        )
        self.assertEqual(
            data["domestic_vs_ucl_comparison"]["steiger_p_dom_ppg_vs_ucl_ppg"],
            self.comp["steiger_p_dom_ppg_vs_ucl_ppg"],
        )
        self.assertTrue(all(o["is_top5"] and o["ucl_stage"] == "Final" for o in data["observations"]))

        resp_p = self.client.get("/api/v1/ucl/paired?positive_spend_only=true&limit=10&offset=0")
        self.assertEqual(resp_p.status_code, 200)
        pdata = resp_p.json()
        self.assertEqual(pdata["pagination"]["total"], self.comp["n_paired_spenders"])
        self.assertEqual(pdata["pagination"]["returned"], 10)

    def test_06_market_value_endpoints_and_disclaimers(self):
        resp_sum = self.client.get("/api/v1/market-value/summary?league_id=L1&limit=5")
        self.assertEqual(resp_sum.status_code, 200)
        sdata = resp_sum.json()
        self.assertIn("NOT realized transfer sale proceeds", sdata["valuation_disclaimer"])
        self.assertEqual(
            sdata["fee_vs_mv_statistics"]["pearson_r_log_log"],
            self.stats["6E_fee_vs_mv"]["pearson_r_log_log"],
        )
        club_csv = pd.read_csv(OUT_DIR / "05_club_value_gain_summary.csv")
        bvb_expected = float(club_csv.loc[club_csv["club_id"] == 16, "portfolio_peak_mv_multiple"].iloc[0])
        bvb_actual = next(r["portfolio_peak_mv_multiple"] for r in sdata["club_valuation_summaries"] if r["club_id"] == 16)
        self.assertAlmostEqual(bvb_actual, bvb_expected, places=6)

        resp_tr = self.client.get("/api/v1/market-value/transfers?is_top5=true&limit=5&offset=5")
        self.assertEqual(resp_tr.status_code, 200)
        tdata = resp_tr.json()
        self.assertEqual(tdata["pagination"]["returned"], 5)
        self.assertTrue(all(t["is_top5"] for t in tdata["transfers"]))

        resp_pg = self.client.get("/api/v1/market-value/player-gains?club_id=16&limit=5")
        self.assertEqual(resp_pg.status_code, 200)
        pgdata = resp_pg.json()
        self.assertTrue(all(p["club_id"] == 16 for p in pgdata["player_gains"]))
        self.assertIn("NOT realized", pgdata["valuation_disclaimer"])

    def test_07_statistics_endpoint_and_section_filtering(self):
        resp_all = self.client.get("/api/v1/statistics")
        self.assertEqual(resp_all.status_code, 200)
        all_data = resp_all.json()
        self.assertEqual(
            all_data["statistical_results"]["6F_robustness"]["two_way_fixed_effects_ppg"]["within_r_squared"],
            self.stats["6F_robustness"]["two_way_fixed_effects_ppg"]["within_r_squared"],
        )
        self.assertIsNotNone(all_data["domestic_vs_ucl_comparison"])

        resp_fe = self.client.get("/api/v1/statistics?section=6F")
        self.assertEqual(resp_fe.status_code, 200)
        self.assertEqual(list(resp_fe.json()["statistical_results"].keys()), ["6F_robustness"])

        resp_07 = self.client.get("/api/v1/statistics?section=07")
        self.assertEqual(resp_07.status_code, 200)
        self.assertEqual(resp_07.json()["statistical_results"], {})
        self.assertEqual(
            resp_07.json()["domestic_vs_ucl_comparison"]["n_paired_total"],
            self.comp["n_paired_total"],
        )

    def test_08_validation_errors_cors_and_missing_resources(self):
        # Invalid league code -> 422
        r_bad_league = self.client.get("/api/v1/domestic?league_id=INVALID")
        self.assertEqual(r_bad_league.status_code, 422)
        self.assertEqual(r_bad_league.json()["error"], "validation_error")

        # Invalid season bounds -> 400
        r_bad_range = self.client.get("/api/v1/trends?start_season=2024&end_season=2020")
        self.assertEqual(r_bad_range.status_code, 400)
        self.assertEqual(r_bad_range.json()["error"], "http_error")

        # Invalid statistics section -> 422
        r_bad_sec = self.client.get("/api/v1/statistics?section=9Z")
        self.assertEqual(r_bad_sec.status_code, 422)

        # CORS preflight / header verification
        r_cors = self.client.get("/health", headers={"Origin": "http://localhost:5173"})
        self.assertEqual(r_cors.status_code, 200)
        self.assertEqual(r_cors.headers.get("access-control-allow-origin"), "http://localhost:5173")

        # Missing DuckDB -> 503
        orig_db = os.environ.get("FOOTINTEL_DB_PATH")
        try:
            os.environ["FOOTINTEL_DB_PATH"] = str(PROJECT_ROOT / "data" / "nonexistent.duckdb")
            r_no_db = self.client.get("/health")
            self.assertEqual(r_no_db.status_code, 503)
            self.assertEqual(r_no_db.json()["error"], "http_error")
        finally:
            if orig_db is None:
                os.environ.pop("FOOTINTEL_DB_PATH", None)
            else:
                os.environ["FOOTINTEL_DB_PATH"] = orig_db

        # Missing output directory -> 503
        orig_out = os.environ.get("FOOTINTEL_OUTPUT_DIR")
        try:
            os.environ["FOOTINTEL_OUTPUT_DIR"] = str(PROJECT_ROOT / "data" / "missing_outputs")
            r_no_out = self.client.get("/api/v1/statistics")
            self.assertEqual(r_no_out.status_code, 503)
            self.assertEqual(r_no_out.json()["error"], "http_error")
        finally:
            if orig_out is None:
                os.environ.pop("FOOTINTEL_OUTPUT_DIR", None)
            else:
                os.environ["FOOTINTEL_OUTPUT_DIR"] = orig_out


if __name__ == "__main__":
    unittest.main(verbosity=2)

