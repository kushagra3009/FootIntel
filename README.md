# FootIntel — Does Money Actually Buy Success?

A professional football transfer data science platform investigating the relationship between club transfer spending and competitive success across Europe's Big 5 domestic leagues and the UEFA Champions League, paired with Player Intelligence, Cross-Season Player Comparison, and Transfer Value tools.

## Research Question

> **Does Money Actually Buy Success in Professional Football?**

Using transfer, match, player, and valuation data from [Transfermarkt](https://www.transfermarkt.com/) (via [transfermarkt-datasets](https://github.com/dcaribou/transfermarkt-datasets)), FootIntel builds a reproducible DuckDB analytics engine and exposes validated findings through a modular FastAPI REST backend and React + TypeScript dashboard.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Data Processing | Python 3.13, Pandas, NumPy, DuckDB, SQL |
| Statistical Analysis | SciPy, Matplotlib (Pearson, Spearman, OLS, Liang-Zeger Cluster-Robust SEs, Fixed Effects, Steiger's z-test) |
| REST API | FastAPI, Pydantic v2, Uvicorn |
| Frontend | React 19, TypeScript, Vite, Recharts, Lucide Icons |

## Project Structure

```text
FootIntel_2/
├── .env.example               # Backend environment variable template
├── .gitattributes             # Cross-platform line-ending normalization
├── data/
│   ├── raw/                   # Downloaded Transfermarkt CSV datasets (gitignored)
│   └── processed/
│       ├── footintel.duckdb   # Persistent DuckDB database (gitignored, regenerated via ingest)
│       ├── analysis_outputs/  # Generated Phase 2 CSV & JSON outputs (gitignored, run_all.py)
│       └── charts/            # Generated Phase 2 PNG charts (gitignored, run_all.py)
├── backend/
│   ├── requirements.txt       # Pinned Python dependencies
│   ├── ingest/                # Data download & DuckDB ingestion scripts
│   ├── sql/                   # Standalone exploratory SQL queries
│   ├── analysis/              # Phase 2 statistical engine (utils.py, run_all.py)
│   ├── api/                   # Phase 3 & 4.1 FastAPI REST backend
│   │   ├── main.py            # FastAPI app, CORS, security headers, OpenAPI & error handlers
│   │   ├── config.py          # Path constants, season bounds & env overrides
│   │   ├── dependencies.py    # Read-only DuckDB & artifact dependencies
│   │   ├── schemas.py         # Pydantic v2 response & error models
│   │   ├── services/          # Parameterized DuckDB & analytics query services
│   │   └── routes/            # Modular routers (health, overview, trends, domestic, ucl, market_value, statistics, players)
│   └── tests/                 # Automated Phase 2, Phase 3 & Phase 4.1 suites (22 tests)
├── frontend/                  # Phase 4 & 4.1 React + TypeScript + Vite dashboard
│   ├── .env.example           # Frontend build-time environment variable template
│   ├── src/
│   │   ├── api/               # Typed FastAPI client (client.ts)
│   │   ├── types/             # TypeScript API response contracts (api.ts)
│   │   ├── utils/             # Currency, percent, p-value & league formatters
│   │   ├── styles/            # Dark editorial theme & responsive CSS (theme.css)
│   │   ├── components/common/ # Reusable KpiCard, ChartCard, PlayerPicker, Sidebar, StatePanel
│   │   └── sections/          # 10 dashboard views (Overview, TransferMarket, DomesticPerformance,
│   │                          #   ChampionsLeague, MarketValue, StatisticalInsights,
│   │                          #   PlayerIntelligence, PlayerComparison, TransferValueCalculator, Methodology)
│   └── vite.config.ts
└── docs/                      # Research methodology & documentation
```

## Installation & Environment Setup

### Prerequisites
- Python 3.11+ (verified with Python 3.13)
- Node.js 20+ and npm (verified with Node.js v24.22.1, npm 11.19.1)

### 1. Setup Backend Environment

On **Windows (PowerShell)**:
```powershell
cd backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

On **Linux / macOS**:
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Data Ingestion & Phase 2 Analytical Artifacts

Because raw Transfermarkt CSVs (`~858 MB`), `footintel.duckdb` (`~196 MB`), and generated outputs are excluded from Git, populate them before starting the backend if `data/processed/` is not yet present:

```bash
cd backend
python -m ingest.download
python -m ingest.load_duckdb
python -m analysis.run_all
```

### 3. Environment Variables

Copy [`.env.example`](.env.example) / [`frontend/.env.example`](frontend/.env.example) as needed (`.env` and `.env.*` files are gitignored).

| Variable | Purpose | Default / Requirement |
|----------|---------|-----------------------|
| `FOOTINTEL_CORS_ORIGINS` | Comma-separated allowed CORS origins | `http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000` |
| `FOOTINTEL_DB_PATH` | Override path to `footintel.duckdb` | `data/processed/footintel.duckdb` |
| `FOOTINTEL_OUTPUT_DIR` | Override path to Phase 2 `analysis_outputs` | `data/processed/analysis_outputs` |
| `VITE_API_BASE_URL` | FastAPI base URL for Vite frontend | Defaults to `http://127.0.0.1:8000` in dev; **required in production builds** (e.g. `https://api.example.com` or `/` behind same-origin proxy) |

## Starting the Application

### Backend (FastAPI + Uvicorn)

Local development (with hot reload):
```bash
cd backend
uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

Production-style server startup (no `--reload`):
```bash
cd backend
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Interactive OpenAPI documentation is automatically served at:
- **Swagger UI:** `/docs`
- **ReDoc:** `/redoc`
- **OpenAPI Schema:** `/openapi.json`

### Frontend (React + Vite)

In a second terminal (with the FastAPI backend running):
```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173/` (or `http://localhost:5173/`) in your browser.

Verify TypeScript types and build the production bundle (`VITE_API_BASE_URL` must be set when deploying static assets):
```bash
cd frontend
npm run typecheck
npm run build
```

## Available API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | API metadata and available endpoint map |
| `GET` | `/health` | DuckDB connectivity, core table row counts, and Phase 2 artifact status |
| `GET` | `/api/v1/overview` | Project KPIs, historical summary, key statistical findings, and methodological caveats |
| `GET` | `/api/v1/trends` | Season-aligned Top-5 spending trends, league breakdowns, and pre-2022 cohort coverage warnings |
| `GET` | `/api/v1/domestic` | Domestic Top-5 spending vs PPG/position observations, league summaries, and regression stats |
| `GET` | `/api/v1/ucl` | UEFA Champions League spending, stage progression, UCL PPG, and stage counts |
| `GET` | `/api/v1/ucl/paired` | Paired Top-5 domestic + UCL club-seasons and Steiger z-test comparison |
| `GET` | `/api/v1/market-value/summary` | Transfer fee vs arrival market value stats & club-level spell-bounded valuation summaries |
| `GET` | `/api/v1/market-value/transfers` | Paginated transfer-level fee vs arrival market value rows |
| `GET` | `/api/v1/market-value/player-gains` | Paginated spell-bounded `[transfer_date, next_transfer_date)` player estimated market value gains |
| `GET` | `/api/v1/statistics` | Complete statistical battery: correlations, OLS slopes, R², clustered SEs, Fixed Effects & Steiger z-tests |
| `GET` | `/api/v1/players/search` | Paginated DuckDB player search (`q`, `position`, `nationality`, `min_appearances`, `sort_by`, `limit`, `offset`) |
| `GET` | `/api/v1/players/compare` | Compare two player-season selections (same season, cross-season, or same player across seasons) |
| `GET` | `/api/v1/players/{player_id}` | Complete Player Intelligence profile, `games.season` stats, valuation curve, transfers & club timeline |
| `GET` | `/api/v1/players/{player_id}/transfer-spells` | Spell-bounded valuation metrics and MV-to-fee multiples for Transfer Value Calculator (Mode A) |

### Methodological Notes Reflected in API & UI Responses
1. **Observational Inference:** Cross-sectional OLS (`R² = 0.2076`) captures between-club hierarchy rather than causal returns; two-way fixed effects yield `within R² = 0.00466` (`p = 0.0553`).
2. **Historical Cohort Coverage:** `100.0%` of `transfers` rows belong to players with `last_season >= 2023`; `/api/v1/trends` includes `pct_active_players_covered` per season (`16.7%` in `12/13` vs `87.6%–100.0%` in `22/23–25/26`).
3. **Estimated Market Value ≠ Financial ROI:** `/api/v1/market-value/*`, Player Intelligence, and Value Calculator report Transfermarkt estimated market value gains and MV-to-fee multiples rather than realized sale profit or accounting ROI.
4. **No Fabricated Match Metrics:** Player analytics display only DuckDB metrics (`appearances`, `goals`, `assists`, `minutes_played`, cards, per-appearance rates). Unavailable metrics (`xG`, `xA`, shots, key passes, passing accuracy, match ratings, wages) are explicitly labeled unavailable.

## Running Automated Tests

Run from `backend/`:

```bash
cd backend
python -m unittest discover -s tests -v
```

- `tests/test_phase2_analysis.py` — Independent DuckDB & statistical recomputation suite (8 tests).
- `tests/test_phase3_api.py` — FastAPI endpoint, schema, filter, pagination, CORS, and error-handling suite (8 tests).
- `tests/test_phase4_1_players.py` — Player search, detail, `games.season` comparison, zero-appearance handling, and transfer-spell valuation suite (6 tests).

Total verified test count: **22 backend tests**.

## License

MIT
