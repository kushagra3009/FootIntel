# FootIntel Methodology, Statistical Framework & Limitations

## 1. Data Source, Coverage Audit & Reproducibility

### 1.1 Upstream Dataset, Attribution & Usage Caveats
- **Source Repository:** [`dcaribou/transfermarkt-datasets`](https://github.com/dcaribou/transfermarkt-datasets) (aggregated from public Transfermarkt records).
- **Upstream Licensing & Source Restrictions:** The `dcaribou/transfermarkt-datasets` repository metadata is marked under the **CC0-1.0 Universal** dedication and provided as-is without warranty. However, because the underlying records and crowdsourced valuations originate from **Transfermarkt** (`transfermarkt.com`), third-party website Terms of Service, trademark notices, and database/intellectual property rules may independently apply to underlying source content. Downstream users should review upstream terms directly before commercial redistribution. FootIntel uses the data strictly for non-commercial analytical and educational research without claims of official financial accounting authority.
- **Ingestion Mirror (`backend/ingest/download.py`):** Downloads 9 gzipped CSV tables from the upstream project's Cloudflare R2 public mirror (`https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data`) and builds a local DuckDB warehouse (`data/processed/footintel.duckdb`) alongside 4 SQL views (`v_club_season_spending`, `v_club_season_sales`, `v_club_net_spend`, `v_top5_leagues`).
- **Snapshot Reproducibility Caveat:** Because `python -m ingest.download` retrieves the live upstream R2 snapshot at execution time, running ingestion on a later date can shift exact row counts, sample sizes, and regression decimal values relative to the snapshot documented below.

**Snapshot Tables Investigated (`data/processed/footintel.duckdb`):**
`transfers` (`175,165`), `games` (`88,958`), `players` (`50,149`), `player_valuations` (`656,301`), `clubs` (`796`), `competitions` (`65`), `appearances` (`1,894,350`), `game_events` (`1,274,469`), and `game_lineups` (`3,179,016`).

**Analysis Window:** `2012/13–2025/26` (`2012-08-10` to `2026-05-24` for Top-5 domestic leagues; `2012-09-18` to `2026-05-06` for UCL, where the `2025/26` Final is not yet in `games`—a pre-2025 sensitivity slice `all_ucl_pre2025_complete_final`, `n = 382`, confirms conclusions hold when excluding `2025/26`).

### 1.2 Survivorship & Historical Coverage Limitation
- **Transfer History Coverage Audit:** `100.0%` of records in `transfers` belong to players with `players.last_season >= 2023` (only `1` row exists for `last_season == 2022` and `0` rows for `last_season <= 2021`).
- **Cohort Implication:** Earlier seasons undercount retired players who exited before the 2023+ scraping cohort. Cross-referencing `appearances` in Top-5 leagues (`2,476–2,721` active players/season) shows active-player transfer coverage grows from **`16.7%` in `2012/13`** (`438 / 2,618`) to **`67.0%` in `2019/20`** (`1,749 / 2,609`) and **`87.6%–100.0%` in `2022/23–2025/26`**. Early-season spending aggregates must therefore be interpreted as **tracked-cohort spending** rather than complete market totals.

---

## 2. Analytical Design & Statistical Methodology

### 2.1 Season Alignment & Sporting Metrics
- **Season Key Harmonization (`backend/analysis/utils.py`):** `games.season = S` (`2022` for 2022/23) maps bidirectionally to `transfers.transfer_season` (`'22/23'`) via `game_season_to_transfer_season` and `transfer_season_to_game_season`.
- **Season-Aligned League Membership:** Domestic league spending trends (Analysis 1) and standings (Analysis 2) derive club league membership per season from `games`, avoiding misattribution from static `clubs.domestic_competition_id`.
- **Normalized Domestic League Metrics (`backend/sql/league_standings.sql`):** Standings are reconstructed from `games` (`played`, `wins`, `draws`, `losses`, `goals_for`, `goals_against`, `points`). Because Bundesliga plays `34` matches, Ligue 1 played `28` matches in `2019/20` and switched to `34` matches in `2023/24`, and England/Spain/Italy play `38` matches, models evaluate:
  - **Points Per Game (`ppg`):** `points / played`.
  - **Normalized Rank (`pos_pct`):** `(n_teams - league_position) / (n_teams - 1)` in `[0, 1]` (`1.0` = 1st place).

### 2.2 Econometric & Sample Filtering Rules (`backend/analysis/run_all.py`)
- **Zero-Spend & Log Scaling (Domestic & UCL):**
  - Positive-spend log regressions use `ln(gross_spend_m)` (`gross_spend > 0`) to avoid the artificial intercept distortion of `log1p(0)` (`n = 1,210` across `166` clubs domestically). Full-sample checks retain zero-spend club-seasons (`n = 1,366`, `176` clubs) using `asinh(gross_spend_m)` OLS (`R² = 0.1867`, `cluster_p = 2.01e-17`), linear `gross_spend_m`, and Spearman rank correlation (`ρ = 0.4559`, `p = 4.57e-71`).
  - **UCL Sample Counts (`456 → 437 → 415`):** `games WHERE competition_id = 'CL'` contains `456` raw `(season, club_id)` appearances; inner-joining `clubs` retains **`437` valid UCL club-season records** saved in `03_ucl_spending_vs_performance.csv` (`258` Top-5, `179` non-Top-5). Analysis `6D` then filters strictly to `(gross_spend > 0) & (ucl_stage_num > 0)`: excluding the **`22` records with `gross_spend == €0`** (`0` have `ucl_stage_num <= 0`) yields **`415` positive-spend UCL observations** (`90` clubs), and **`248` Top-5 UCL positive-spend observations** (`10` zero-spend rows excluded from `258`). All `437` records remain queryable via `/api/v1/ucl`.
- **Club-Clustered Standard Errors:** Because clubs repeat across `2012/13–2025/26` (mean `7.29` observations/club; Breusch-Pagan heteroscedasticity check `p = 2.09e-10`), `cluster_ols` reports Liang-Zeger club-clustered sandwich standard errors with finite-sample `G - 1` `t`-inference alongside naive OLS standard errors.
- **Dependent Correlation Testing (Domestic vs. UCL):** On `248` paired Top-5 UCL spenders observed in both competitions in the same season (`258` total paired Top-5 clubs), **Steiger's (1980) `z`-test** (`steiger_z_test`) finds a statistically significant gap between domestic PPG correlation (`r = 0.1141`) and UCL PPG correlation (`r = 0.2425`, `z = -2.1713, p = 0.0299`), whereas stage progression shows `r = 0.1490` (`z = -0.538, p = 0.5906`). Range restriction among elite UCL qualifiers attenuates both correlations relative to pooled samples.

### 2.3 Correlation vs. Causation & Fixed-Effects Interpretation
- **Between-Club Hierarchy vs. Within-Club Fluctuations:** Pooled OLS (`R² = 0.2076`, `r = 0.4557, n = 1,210`) and Club-Averaged Cross-Sectional OLS (`R² = 0.3861`, `r = 0.6214, n = 166` clubs) reflect strong **between-club associations** (wealthier clubs spend more and earn higher PPG).
- **Fixed-Effects Attenuation:**
  - **Season Fixed Effects (`ppg`):** `R² = 0.2754` (`cluster_p = 2.63e-22`).
  - **Club Fixed Effects (`ppg`):** `within R² = 0.0002` (`slope = 0.003384, cluster_p = 0.7447, n = 1,193`).
  - **Two-Way Fixed Effects (Club + Season):** `within R² = 0.00466` (`slope = 0.02122, cluster_t = 1.9321, cluster_p = 0.0553, n = 1,193, clusters = 149`).
- **Interpretation:** Single-season transfer fluctuations within the same club show near-zero immediate linear association with domestic PPG once club fixed effects are controlled. Pooled associations reflect structural hierarchy, omitted variables (wage bills, commercial revenues, academy quality), and UCL qualification feedback rather than causal treatment effects.

---

## 3. Player Intelligence, Comparison & Valuation Rules

### 3.1 Player Season-Boundary Rules (`backend/api/services/player_service.py`)
Applied in `/api/v1/players/{player_id}` and `/api/v1/players/compare`:
- **Match Appearances:** Strictly filtered by `games.season = S` (`appearances`, `goals`, `assists`, `minutes_played`, `yellow_cards`, `red_cards`, and derived per-appearance rates).
- **Season-Aligned Market Valuation:** Takes the latest `player_valuations` record inside `[S-07-01, (S+1)-06-30]`, falling back explicitly to the latest prior valuation `<= (S+1)-06-30` with a boundary note when none falls inside the season window.
- **Season Transfer Fee vs. Career Paid Fee:** Season transfer fees match `transfers.transfer_season = game_season_to_transfer_season(S)` (or `transfer_date` within `[S-07-01, (S+1)-06-30]` when `transfer_season` is null) and classify `'paid'` (`> €0`), `'free_or_loan'` (`= €0`), and `'undisclosed'` (`NULL`). Prior paid transfer fees are returned separately to avoid cross-season fee misattribution.
- **Non-Fabrication Guarantee:** Metrics absent from `appearances` (`xG`, `xA`, shots, key passes, passing accuracy, tackles, saves, match ratings, and player wages) are never synthesized or imputed.

### 3.2 Transfer-Spell Attribution (`backend/analysis/run_all.py` & `player_service.py`)
Used by Analysis 5 (`05_player_value_gain.csv`, `n = 4,881` Top-5 paid spells) and `/api/v1/players/{player_id}/transfer-spells`:
- **Chronological Bounding `[transfer_date, next_transfer_date)`:** Using `LEAD(transfer_date)` ordered chronologically per player, `player_valuations.date` is bounded strictly from `transfer_date` (inclusive) up to—excluding—`next_transfer_date`, preventing pre-arrival hype or subsequent clubs from contaminating a club spell.
- **Arrival Valuation Resolution:** Uses `transfers.market_value_in_eur` if present, falling back to the latest `player_valuations` record `<= transfer_date`.
- **Valuation Multiples:** Computed exclusively for paid transfers (`transfer_fee > €0`) and named `est_peak_mv_gain`, `peak_mv_to_fee_multiple`, `est_latest_mv_gain`, and `latest_mv_to_fee_multiple` to distinguish estimated valuation changes from financial profit.

### 3.3 Market Valuation Limitations
- **Estimated Market Value ≠ Financial ROI:** Transfermarkt market values are crowdsourced estimates, **not** club accounting book values, realized cash transfer proceeds, or return on investment.
- **Unobserved Financial Terms:** Club wage bills, contract amortization, agent fees, signing bonuses, performance add-ons, and sell-on clauses are absent from the database. Negative latest multiples often reflect player age, contract expiry, or retirement rather than cash trading losses.

---

## 4. Verification & API Schema Reference

- **Automated Verification:** Run `python -m analysis.run_all` and `python -m unittest discover -s tests -v` from `backend/` (`22` tests spanning `test_phase2_analysis.py`, `test_phase3_api.py`, and `test_phase4_1_players.py`, verifying statistics and endpoints directly against `footintel.duckdb`).
- **API Schemas ([`backend/api/schemas.py`](../backend/api/schemas.py)):** Strict Pydantic v2 contracts backing all 15 FastAPI routes (live OpenAPI documentation at `/docs` and `/openapi.json`):
  - *Macro & Econometrics:* `OverviewResponse`, `HistoricalTrendsResponse`, `DomesticPerformanceResponse`, `UCLPerformanceResponse`, `UCLPairedResponse`, `StatisticalResultsResponse`
  - *Market Valuation & Spells:* `MarketValueSummaryResponse`, `MarketValueTransfersResponse`, `PlayerValueGainsResponse`, `PlayerTransferSpellsResponse`
  - *Player Intelligence & Comparison:* `PlayerSearchResponse`, `PlayerDetailResponse`, `PlayerComparisonResponse`
