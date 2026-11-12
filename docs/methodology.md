# FootIntel Methodology & Validation Notes

## Data Source & Coverage
- **Database:** `data/processed/footintel.duckdb` built from `dcaribou/transfermarkt-datasets`.
- **Tables:** `transfers` (175,165 rows), `games` (88,958 rows), `players` (50,149 rows), `player_valuations` (656,301 rows), `clubs` (796 rows), `competitions` (65 rows), `appearances` (1,894,350 rows), `game_events` (1,274,469 rows), `game_lineups` (3,179,016 rows).
- **Season Alignment:** `transfers.transfer_season` (`'22/23'`) maps to `games.season` (`2022`).
- **Known Coverage Constraint:** 100% of records in `transfers` correspond to players with `players.last_season >= 2023`. Early seasons (2012–2017) undercount transfers of players who retired prior to 2023. All core regressions are verified on both `2012–2025` and high-coverage sub-periods (`2018–2025`, `2022–2025`).

## Analytical Design & Safeguards
1. **Season-Aligned League Membership:** Domestic league spending trends (Analysis 1) and standings (Analysis 2) derive club league membership per season from `games`, avoiding misleading attribution from static `clubs.domestic_competition_id`.
2. **Normalized Sporting Metrics:** Because Bundesliga plays 34 matches, Ligue 1 played 28 matches in 2019/20 and switched to 34 matches in 2023/24, and England/Spain/Italy play 38 matches, regressions use Points Per Game (`ppg`) and within-season normalized position percentile (`pos_pct`) alongside raw `points`.
3. **Zero-Spend & Log Scaling:** Positive-spend log regressions use `ln(gross_spend_m)` (`gross_spend > 0`) to avoid the `log1p(0)` artificial leverage gap; full-sample models use `asinh(gross_spend_m)`, linear `gross_spend_m`, and Spearman rank correlation.
4. **Spell-Bounded Valuations:** Club-level value gain (Analysis 5) bounds `player_valuations.date` strictly to `[transfer_date, next_transfer_date)` and groups by canonical `clubs.club_id` / `clubs.name`.
5. **Panel / Repeated Club Observations:** Standard errors are club-clustered (Liang-Zeger sandwich estimator with `G/(G-1)` small-sample adjustment), supplemented by Season Fixed Effects, Club Fixed Effects, Two-Way Fixed Effects, and a 166-club averaged cross-sectional regression.
6. **Reproducibility:** Run `python -m analysis.run_all` and `python -m unittest tests.test_phase2_analysis -v` from `backend/`.
