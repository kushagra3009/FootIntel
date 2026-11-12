# FootIntel — Does Money Actually Buy Success?

A professional football transfer data science platform investigating the relationship between club spending and competitive success.

## Research Question

> **Does Money Actually Buy Success in Professional Football?**

Using comprehensive transfer data from [Transfermarkt](https://www.transfermarkt.com/) (via [transfermarkt-datasets](https://github.com/dcaribou/transfermarkt-datasets)), we apply statistical analysis and interactive visualization to answer this question rigorously.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Data Processing | Python, Pandas, NumPy, DuckDB, SQL |
| Statistical Analysis | SciPy |
| API | FastAPI |
| Frontend | React, TypeScript, Vite, Recharts |

## Project Structure

```
FootIntel_2/
├── data/              # Raw + processed datasets
├── backend/           # Python data-science engine & API
│   ├── ingest/        # Data download & DuckDB ingestion
│   ├── analysis/      # Statistical analysis modules
│   ├── sql/           # DuckDB SQL queries
│   ├── api/           # FastAPI REST layer
│   └── tests/         # Test suite
├── frontend/          # React + TypeScript + Vite dashboard
└── docs/              # Research methodology & findings
```

## Quick Start

```bash
# Backend
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -m ingest.download
python -m ingest.load_duckdb
uvicorn api.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

## License

MIT
