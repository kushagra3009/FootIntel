# FootIntel — Does Money Actually Buy Success?

A professional football transfer data science platform investigating the relationship between club transfer spending and competitive success across Europe's Big 5 domestic leagues and the UEFA Champions League.

## Research Question

> **Does Money Actually Buy Success in Professional Football?**

Using transfer, match, player, and valuation data from [Transfermarkt](https://www.transfermarkt.com/) (via [transfermarkt-datasets](https://github.com/dcaribou/transfermarkt-datasets)), FootIntel builds a reproducible DuckDB analytics engine and exposes validated findings through a modular FastAPI REST backend.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Data Processing | Python 3.13, Pandas, NumPy, DuckDB, SQL |
| Statistical Analysis | SciPy (Pearson, Spearman, OLS, Liang-Zeger Cluster-Robust SEs, Fixed Effects, Steiger's z-test) |
| REST API | FastAPI, Pydantic v2, Uvicorn |
| Frontend *(Phase 4)* | React, TypeScript, Vite, Recharts |

## Project Structure

```text
FootIntel_2/
├── data/
│   ├── raw/                   # Downloaded Transfermarkt CSV datasets
│   └── processed/
│       ├── footintel.duckdb   # Persistent DuckDB database (88,958 games, 175,165 transfers)
│       ├── analysis_outputs/  # Validated Phase 2 CSV & JSON outputs
│       └── charts/            # Publication-quality Phase 2 PNG charts
├── backend/
│   ├── ingest/                # Data download & DuckDB ingestion scripts
│   ├── sql/                   # Standalone exploratory SQL queries
│   ├── analysis/              # Phase 2 statistical engine (utils.py, run_all.py)
│   ├── api/                   # Phase 3 FastAPI REST backend
│   │   ├── main.py            # FastAPI app, CORS, OpenAPI & exception handlers
│   │   ├── config.py          # Path constants, season bounds & env overrides
│   │   ├── dependencies.py    # Read-only DuckDB & artifact dependencies
│   │   ├── schemas.py         # Pydantic v2 response & error models
│   │   ├── services/          # Parameterized DuckDB CSV/DB query layer
│   │   └── routes/            # Modular routers (health, overview, trends, domestic, ucl, market_value, statistics)
│   └── tests/                 # Automated Phase 2 & Phase 3 verification suites
├── frontend/                  # Planned React + TypeScript + Vite dashboard (Phase 4)
└── docs/                      # Research methodology & documentation
```

## Installation & Environment Setup

### Prerequisites
- Python 3.11+ (verified with Python 3.13)
- Node.js 18+ (for future Phase 4 frontend)

### Setup Backend Environment

```powershell
cd backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### Environment Variables (Optional)

| Variable | Purpose | Default |
|----------|---------|---------|
| `FOOTINTEL_CORS_ORIGINS` | Comma-separated allowed CORS origins | `http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000` |
| `FOOTINTEL_DB_PATH` | Override path to `footintel.duckdb` | `data/processed/footintel.duckdb` |
| `FOOTINTEL_OUTPUT_DIR` | Override path to Phase 2 `analysis_outputs` | `data/processed/analysis_outputs` |

### Data Ingestion & Phase 2 Pipeline (Already Included if `data/processed/` is Populated)

```powershell
cd backend
.\venv\Scripts\python -m ingest.download
.\venv\Scripts\python -m ingest.load_duckdb
.\venv\Scripts\python -m analysis.run_all
```

## Starting the FastAPI REST Backend

Run from the `backend/` directory:

```powershell
cd backend
.\venv\Scripts\uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

Interactive OpenAPI documentation is automatically served at:
- **Swagger UI:** `http://127.0.0.1:8000/docs`
- **ReDoc:** `http://127.0.0.1:8000/redoc`
- **OpenAPI Schema:** `http://127.0.0.1:8000/openapi.json`

## Available API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | API metadata and available endpoint map |
| `GET` | `/health` | DuckDB connectivity, core table row counts, and Phase 2 artifact status |
| `GET` | `/api/v1/overview` | Project KPIs, historical summary, key statistical findings, and methodological caveats |
| `GET` | `/api/v1/trends` | Season-aligned Top-5 spending trends, league breakdowns, and pre-2022 cohort coverage warnings (`league_id`, `start_season`, `end_season`, `limit`, `offset`) |
| `GET` | `/api/v1/domestic` | Domestic Top-5 spending vs PPG/position observations, league summaries, and regression stats (`league_id`, `season`, `start_season`, `end_season`, `club_id`, `club_name`, `positive_spend_only`, `min_spend_m`, `sort_by`, `sort_order`, `limit`, `offset`) |
| `GET` | `/api/v1/ucl` | UEFA Champions League spending, stage progression, UCL PPG, and stage counts (`season`, `league_id`, `is_top5`, `ucl_stage`, `club_id`, `club_name`, `positive_spend_only`, `sort_by`, `sort_order`, `limit`, `offset`) |
| `GET` | `/api/v1/ucl/paired` | Paired Top-5 domestic + UCL club-seasons and Steiger z-test comparison (`season`, `league_name`, `club_id`, `club_name`, `positive_spend_only`, `limit`, `offset`) |
| `GET` | `/api/v1/market-value/summary` | Transfer fee vs arrival market value stats & club-level spell-bounded valuation summaries (`league_id`, `club_name`, `min_signings`, `sort_by`, `sort_order`, `limit`, `offset`) |
| `GET` | `/api/v1/market-value/transfers` | Paginated transfer-level fee vs arrival market value rows (`season`, `league_id`, `is_top5`, `player_name`, `club_name`, `min_fee`, `sort_by`, `sort_order`, `limit`, `offset`) |
| `GET` | `/api/v1/market-value/player-gains` | Paginated spell-bounded `[transfer_date, next_transfer_date)` player estimated market value gains (`club_id`, `club_name`, `league_id`, `season`, `player_name`, `sort_by`, `sort_order`, `limit`, `offset`) |
| `GET` | `/api/v1/statistics` | Complete statistical battery: Pearson/Spearman correlations, OLS slopes, R², naive & club-clustered SEs/95% CIs, Season/Club/Two-Way Fixed Effects, and Steiger z-tests (`section=all|6A|6B|6C|6D|6E|6F|07`) |

## Example Requests & Responses

### Check API & Database Health
```bash
curl http://127.0.0.1:8000/health
```
```json
{
  "status": "ok",
  "database_connected": true,
  "database_file": "footintel.duckdb",
  "outputs_available": true,
  "output_files_count": 10,
  "tables": {
    "appearances": 1894350,
    "clubs": 796,
    "competitions": 65,
    "games": 88958,
    "player_valuations": 656301,
    "players": 50149,
    "transfers": 175165
  }
}
```

### Query Domestic Spending vs Performance (LaLiga 2022/23)
```bash
curl "http://127.0.0.1:8000/api/v1/domestic?league_id=ES1&season=2022&positive_spend_only=true&sort_by=ppg&sort_order=desc&limit=2"
```

### Query Fixed-Effects & Robustness Statistics
```bash
curl "http://127.0.0.1:8000/api/v1/statistics?section=6F"
```

### Methodological Notes Reflected in API Responses
1. **Observational Inference:** Cross-sectional OLS (`R² = 0.2076`) captures between-club hierarchy rather than causal returns; two-way fixed effects yield `within R² = 0.00466` (`p = 0.0553`).
2. **Historical Cohort Coverage:** `100.0%` of `transfers` rows belong to players with `last_season >= 2023`; `/api/v1/trends` includes `pct_active_players_covered` per season (`16.7%` in `12/13` vs `87.6%–100.0%` in `22/23–25/26`).
3. **Estimated Market Value ≠ Financial ROI:** `/api/v1/market-value/*` reports Transfermarkt estimated market value gains and MV-to-fee multiples rather than realized sale profit or accounting ROI.

## Running Automated Tests

Run from `backend/`:

```powershell
cd backend
.\venv\Scripts\python -m unittest discover -s tests -v
```

- `tests/test_phase2_analysis.py` — Independent DuckDB & statistical recomputation suite (8 tests).
- `tests/test_phase3_api.py` — FastAPI endpoint, schema, filter, pagination, CORS, and error-handling suite (8 tests).

## License

MIT
