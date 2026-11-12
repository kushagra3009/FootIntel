"""
Phase 4.1 API & DuckDB verification tests for Player Intelligence, Cross-Season Comparison,
and Transfer Spell Valuation endpoints.
"""

import unittest
from pathlib import Path
import duckdb
from fastapi.testclient import TestClient

from api.main import app

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = PROJECT_ROOT / "data" / "processed" / "footintel.duckdb"


class TestPhase41Players(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.con = duckdb.connect(str(DB_PATH), read_only=True)

    @classmethod
    def tearDownClass(cls):
        cls.con.close()

    def test_01_static_routes_registered_and_openapi(self):
        r_openapi = self.client.get("/openapi.json")
        self.assertEqual(r_openapi.status_code, 200)
        paths = r_openapi.json()["paths"]
        self.assertIn("/api/v1/players/search", paths)
        self.assertIn("/api/v1/players/compare", paths)
        self.assertIn("/api/v1/players/{player_id}", paths)
        self.assertIn("/api/v1/players/{player_id}/transfer-spells", paths)

        # Ensure /search and /compare resolve statically instead of hitting int validation for /{player_id}
        r_search = self.client.get("/api/v1/players/search?limit=5")
        self.assertEqual(r_search.status_code, 200)
        r_compare = self.client.get("/api/v1/players/compare?player_a_id=342229&player_b_id=418560")
        self.assertEqual(r_compare.status_code, 200)

    def test_02_player_search_filters_pagination_and_sql_safety(self):
        r = self.client.get("/api/v1/players/search?q=Mbapp&position=Attack&limit=10")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        names = [p["name"] for p in data["players"]]
        self.assertIn("Kylian Mbappé", names)
        self.assertLessEqual(len(data["players"]), 10)
        self.assertIn("Attack", data["available_positions"])

        # Pagination limit enforcement (>50 should reject with 422)
        r_bad_limit = self.client.get("/api/v1/players/search?limit=51")
        self.assertEqual(r_bad_limit.status_code, 422)

        # Parameterized query safety
        r_inj = self.client.get("/api/v1/players/search", params={"q": "'; DROP TABLE players;--"})
        self.assertEqual(r_inj.status_code, 200)
        self.assertEqual(r_inj.json()["players"], [])

        # min_appearances filter check
        r_apps = self.client.get("/api/v1/players/search?q=Haaland&min_appearances=100")
        self.assertEqual(r_apps.status_code, 200)
        for p in r_apps.json()["players"]:
            self.assertGreaterEqual(p["appearance_count"], 100)

    def test_03_player_detail_matches_duckdb_and_fee_statuses(self):
        pid = 342229  # Kylian Mbappé
        r = self.client.get(f"/api/v1/players/{pid}")
        self.assertEqual(r.status_code, 200)
        body = r.json()

        db_totals = self.con.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(goals), 0), COALESCE(SUM(assists), 0), COALESCE(SUM(minutes_played), 0)
            FROM appearances
            WHERE player_id = ?
            """,
            [pid],
        ).fetchone()
        cs = body["career_summary"]
        self.assertTrue(cs["has_appearance_data"])
        self.assertEqual(cs["appearances"], db_totals[0])
        self.assertEqual(cs["goals"], db_totals[1])
        self.assertEqual(cs["assists"], db_totals[2])
        self.assertEqual(cs["minutes_played"], db_totals[3])

        # Verify season-aligned sums equal career totals
        self.assertEqual(sum(s["appearances"] for s in body["season_stats"]), db_totals[0])
        self.assertEqual(sum(s["goals"] for s in body["season_stats"]), db_totals[1])

        # Verify fee_status classification across Mbappé transfers
        fee_statuses = {t["fee_status"] for t in body["transfer_history"]}
        self.assertEqual(fee_statuses, {"paid", "free_or_loan", "undisclosed"})
        self.assertIn("crowdsourced", body["valuation_disclaimer"].lower())

        # Nonexistent player ID -> 404
        r_404 = self.client.get("/api/v1/players/999999999")
        self.assertEqual(r_404.status_code, 404)

    def test_04_zero_appearance_player_explicitly_labeled(self):
        r = self.client.get("/api/v1/players/162")  # Marc Ziegler (0 appearances)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertFalse(body["career_summary"]["has_appearance_data"])
        self.assertEqual(body["career_summary"]["appearances"], 0)
        self.assertIsNone(body["career_summary"]["goals_per_appearance"])
        self.assertEqual(body["season_stats"], [])
        self.assertIn("xG", body["career_summary"]["unavailable_metrics_note"])

    def test_05_player_comparison_modes_and_season_boundaries(self):
        # 1) Same season: Mbappé vs Haaland in games.season = 2023 (23/24)
        r_same = self.client.get(
            "/api/v1/players/compare?player_a_id=342229&player_b_id=418560&season_a=2023&season_b=2023"
        )
        self.assertEqual(r_same.status_code, 200)
        same = r_same.json()
        self.assertEqual(same["comparison_mode"], "same_season")
        self.assertTrue(same["radar_supported"])
        self.assertEqual(len(same["radar_axes"]), 6)

        db_mbappe_23 = self.con.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(a.goals), 0), COALESCE(SUM(a.assists), 0)
            FROM appearances a
            JOIN games g ON a.game_id = g.game_id
            WHERE a.player_id = 342229 AND g.season = 2023
            """
        ).fetchone()
        self.assertEqual(same["player_a"]["metrics"]["appearances"], db_mbappe_23[0])
        self.assertEqual(same["player_a"]["metrics"]["goals"], db_mbappe_23[1])
        self.assertEqual(same["player_a"]["metrics"]["assists"], db_mbappe_23[2])

        # 2) Same player across different seasons: Jude Bellingham 2022 vs 2023
        r_cross = self.client.get(
            "/api/v1/players/compare?player_a_id=581678&player_b_id=581678&season_a=2022&season_b=2023"
        )
        self.assertEqual(r_cross.status_code, 200)
        cross = r_cross.json()
        self.assertEqual(cross["comparison_mode"], "same_player_cross_season")
        self.assertEqual(cross["player_a"]["metrics"]["season_transfer_fee_status"], "no_transfer_in_season")
        self.assertEqual(cross["player_b"]["metrics"]["season_transfer_fee_status"], "paid")
        self.assertAlmostEqual(cross["player_b"]["metrics"]["season_transfer_fee_eur"], 127_000_000.0)

        # 3) Different players & seasons where one lacks appearances -> radar disabled
        r_no_radar = self.client.get(
            "/api/v1/players/compare?player_a_id=342229&player_b_id=162&season_a=2023&season_b=2023"
        )
        self.assertEqual(r_no_radar.status_code, 200)
        nr = r_no_radar.json()
        self.assertFalse(nr["radar_supported"])
        self.assertIsNotNone(nr["radar_unavailable_reason"])
        self.assertEqual(nr["radar_axes"], [])

    def test_06_transfer_spells_calculator_matches_duckdb(self):
        pid = 418560  # Erling Haaland
        r = self.client.get(f"/api/v1/players/{pid}/transfer-spells")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        mancity = next(
            (s for s in body["spells"] if s["to_club_name"] == "Man City" and s["transfer_season"] == "22/23"),
            None,
        )
        self.assertIsNotNone(mancity)
        self.assertEqual(mancity["transfer_fee"], 60_000_000.0)
        self.assertEqual(mancity["peak_mv"], 200_000_000.0)
        self.assertAlmostEqual(mancity["est_peak_mv_gain"], 140_000_000.0)
        self.assertAlmostEqual(mancity["peak_mv_to_fee_multiple"], 200_000_000.0 / 60_000_000.0, places=3)


if __name__ == "__main__":
    unittest.main()
