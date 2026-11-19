"""
Vercel Serverless Function entrypoint for the FootIntel FastAPI backend.
"""

import os
import sys
from pathlib import Path

# Set up paths so backend modules can be imported
_THIS_DIR = Path(__file__).resolve().parent          # repo_root/api/
_REPO_ROOT = _THIS_DIR.parent                        # repo_root/
_BACKEND_DIR = _REPO_ROOT / "backend"                # repo_root/backend/

if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Clear any root-level 'api' namespace package so 'import api.*' resolves to backend/api
if "api" in sys.modules and getattr(sys.modules["api"], "__file__", None) != str(_BACKEND_DIR / "api" / "__init__.py"):
    del sys.modules["api"]

# Configure Vercel runtime environment
_VERCEL_RUNTIME = os.environ.get("VERCEL", "")
_VERCEL_ENV = os.environ.get("VERCEL_ENV", "")

if _VERCEL_RUNTIME or _VERCEL_ENV:
    _TMP_DATA = Path("/tmp/footintel/data/processed")
    _TMP_DATA.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("FOOTINTEL_DB_PATH", str(_TMP_DATA / "footintel.duckdb"))
    os.environ.setdefault("FOOTINTEL_OUTPUT_DIR", str(_TMP_DATA / "analysis_outputs"))
    os.environ.setdefault("FOOTINTEL_ENV", "production")

    # Safe defaults to the public, verified GitHub Release v1.0.0 assets
    os.environ.setdefault(
        "FOOTINTEL_DB_ASSET_URL",
        "https://github.com/kushagra3009/FootIntel/releases/download/v1.0.0/footintel.duckdb.gz",
    )
    os.environ.setdefault(
        "FOOTINTEL_DB_SHA256",
        "faa87f401347e3aaf88e46c65ca3957c5c2be304398bc236b2f19b71dfd6e63b",
    )
    os.environ.setdefault(
        "FOOTINTEL_OUTPUTS_ASSET_URL",
        "https://github.com/kushagra3009/FootIntel/releases/download/v1.0.0/analysis_outputs.tar.gz",
    )
    os.environ.setdefault(
        "FOOTINTEL_OUTPUTS_SHA256",
        "3c363acdb65885b25ed7dd628337099e633c16f0676a3d7d8f1091f0333a8259",
    )

# Run lazy hydration on cold start, then import app
from api.hydrate import ensure_hydrated_lazy  # noqa: E402

ensure_hydrated_lazy()

from api.main import app  # noqa: E402, F401
