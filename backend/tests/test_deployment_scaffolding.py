"""
Unit tests for STEP 1 deployment scaffolding and pre-start artifact hydration.
Verifies SHA-256 enforcement, corrupt/missing DB rejection, hardened tar.gz
extraction, backup-and-rollback directory replacement, stale temp cleanup,
missing production config fail-fast, local no-op mode, DuckDB config bounds,
and bounded request concurrency without deadlocks.
"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import gzip
import hashlib
from http.client import HTTPMessage
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request
import duckdb

from api import dependencies
from api.config import (
    CORE_TABLES,
    DEFAULT_CORS_ORIGINS,
    REQUIRED_OUTPUT_FILES,
    get_cors_origins,
    get_csv_max_concurrency,
    get_db_max_concurrency,
    get_duckdb_config,
    get_in_memory_duckdb_config,
)
from api.hydrate import (
    HydrationError,
    _StrictHTTPSRedirectHandler,
    _stamp_path_for,
    ensure_hydrated,
    extract_verified_outputs_archive,
    main as hydrate_main,
    replace_directory_with_rollback,
)
from api.main import create_app
from api.services import analytics_service, data_store, player_service

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
REAL_DB_PATH = PROJECT_ROOT / "data" / "processed" / "footintel.duckdb"
REAL_OUT_DIR = PROJECT_ROOT / "data" / "processed" / "analysis_outputs"


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _create_valid_duckdb(path: Path) -> None:
    con = duckdb.connect(str(path))
    try:
        for idx, tbl in enumerate(CORE_TABLES, start=1):
            con.execute(f"CREATE TABLE {tbl} (id INTEGER)")
            con.execute(f"INSERT INTO {tbl} VALUES (?)", [idx])
    finally:
        con.close()


def _sample_output_payload(filename: str, tag: str = "new") -> bytes:
    if filename.endswith(".json"):
        return json.dumps({"tag": tag, "file": filename}).encode("utf-8")
    return f"col_a,col_b\n{tag},1\n".encode("utf-8")


def _build_valid_outputs_tar_gz(tag: str = "new", prefix: str = "analysis_outputs/") -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        if prefix:
            dir_info = tarfile.TarInfo(name=prefix.rstrip("/"))
            dir_info.type = tarfile.DIRTYPE
            dir_info.mode = 0o755
            tar.addfile(dir_info)
        for filename in REQUIRED_OUTPUT_FILES:
            data = _sample_output_payload(filename, tag=tag)
            info = tarfile.TarInfo(name=f"{prefix}{filename}")
            info.size = len(data)
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class _FakeHTTPResponse:
    """File-like context manager simulating a streamed urlopen HTTP response."""

    def __init__(self, payload: bytes, status: int = 200) -> None:
        self.status = status
        self._buf = io.BytesIO(payload)

    def read(self, size: int = -1) -> bytes:
        return self._buf.read(size)

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._buf.close()


class _MockAssetTransport:
    """In-memory URL router mocking api.hydrate.urlopen without sockets."""

    def __init__(self, routes: dict[str, bytes]) -> None:
        self.routes = routes
        self.request_count = 0

    def __call__(self, req, timeout: int = 60):
        self.request_count += 1
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if url not in self.routes:
            raise HTTPError(url, 404, "Not Found", hdrs=None, fp=None)
        return _FakeHTTPResponse(self.routes[url], status=200)


def _clean_hydration_env() -> dict[str, str]:
    keys = [
        "FOOTINTEL_ENV",
        "FOOTINTEL_REQUIRE_HYDRATION",
        "RENDER",
        "FOOTINTEL_CORS_ORIGINS",
        "FOOTINTEL_DB_ASSET_URL",
        "FOOTINTEL_DB_SHA256",
        "FOOTINTEL_OUTPUTS_ASSET_URL",
        "FOOTINTEL_OUTPUTS_SHA256",
        "FOOTINTEL_DB_PATH",
        "FOOTINTEL_OUTPUT_DIR",
    ]
    return {k: v for k, v in os.environ.items() if k not in keys}


class TestDeploymentScaffolding(unittest.TestCase):
    def test_01_local_dev_noop_without_production_flags_or_urls(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = _clean_hydration_env()
            env["FOOTINTEL_DB_PATH"] = str(Path(tmp) / "missing.duckdb")
            env["FOOTINTEL_OUTPUT_DIR"] = str(Path(tmp) / "missing_outputs")
            with patch.dict(os.environ, env, clear=True):
                res = ensure_hydrated()
                self.assertEqual(res.status, "skipped_local")
                self.assertFalse(res.db_hydrated)
                self.assertFalse(res.outputs_hydrated)
                self.assertEqual(hydrate_main(), 0)

    def test_02_missing_production_config_fails_fast(self):
        for prod_key, prod_val in [("FOOTINTEL_ENV", "production"), ("RENDER", "true")]:
            with self.subTest(prod_key=prod_key):
                env = _clean_hydration_env()
                env[prod_key] = prod_val
                env["FOOTINTEL_CORS_ORIGINS"] = "https://footintel.pages.dev"
                with patch.dict(os.environ, env, clear=True):
                    with self.assertRaises(HydrationError) as ctx:
                        ensure_hydrated()
                    self.assertIn("Missing required hydration configuration", str(ctx.exception))
                    self.assertEqual(hydrate_main(), 1)

        # Partial config (URL without SHA-256) also fails even outside production flag
        env = _clean_hydration_env()
        env["FOOTINTEL_DB_ASSET_URL"] = "https://example.com/footintel.duckdb.gz"
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaises(HydrationError):
                ensure_hydrated()

    def test_03_valid_hydration_gzip_db_and_warm_skip_and_stale_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            target_root = tmp_path / "processed"
            target_root.mkdir()

            raw_db = tmp_path / "source.duckdb"
            _create_valid_duckdb(raw_db)
            gz_bytes = gzip.compress(raw_db.read_bytes())
            tar_bytes = _build_valid_outputs_tar_gz(tag="v1")

            db_url = "https://releases.example.test/v1/footintel.duckdb.gz"
            out_url = "https://releases.example.test/v1/analysis_outputs.tar.gz"
            transport = _MockAssetTransport({db_url: gz_bytes, out_url: tar_bytes})

            target_db = target_root / "footintel.duckdb"
            target_out = target_root / "analysis_outputs"

            # Plant stale interrupted .part / .tmp / backup leftovers
            stale_db_part = target_root / "footintel.duckdb.hydrate.99999.part"
            stale_db_part.write_bytes(b"stale partial")
            stale_out_dir = target_root / "analysis_outputs.hydrate.staging.99999"
            stale_out_dir.mkdir()
            (stale_out_dir / "junk.txt").write_text("stale", encoding="utf-8")

            env = _clean_hydration_env()
            env.update(
                {
                    "FOOTINTEL_ENV": "production",
                    "FOOTINTEL_CORS_ORIGINS": "https://footintel.pages.dev",
                    "FOOTINTEL_DB_PATH": str(target_db),
                    "FOOTINTEL_OUTPUT_DIR": str(target_out),
                    "FOOTINTEL_DB_ASSET_URL": db_url,
                    "FOOTINTEL_DB_SHA256": _sha256_bytes(gz_bytes),
                    "FOOTINTEL_OUTPUTS_ASSET_URL": out_url,
                    "FOOTINTEL_OUTPUTS_SHA256": _sha256_bytes(tar_bytes),
                }
            )
            with patch("api.hydrate.urlopen", side_effect=transport), patch.dict(
                os.environ, env, clear=True
            ):
                res = ensure_hydrated()
                self.assertEqual(res.status, "hydrated")
                self.assertTrue(res.db_hydrated)
                self.assertTrue(res.outputs_hydrated)
                self.assertFalse(stale_db_part.exists())
                self.assertFalse(stale_out_dir.exists())
                self.assertTrue(target_db.is_file())
                for fname in REQUIRED_OUTPUT_FILES:
                    self.assertTrue((target_out / fname).is_file())

                self.assertEqual(transport.request_count, 2)

                # Warm rerun verifies existing artifacts locally with zero network requests
                res2 = ensure_hydrated()
                self.assertEqual(res2.status, "verified_existing")
                self.assertFalse(res2.db_hydrated)
                self.assertFalse(res2.outputs_hydrated)
                self.assertEqual(transport.request_count, 2)

    def test_04_checksum_mismatch_and_corrupt_duckdb_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            target_root = tmp_path / "processed"
            target_root.mkdir()

            tar_bytes = _build_valid_outputs_tar_gz(tag="v1")
            bad_db_bytes = b"not a valid duckdb file at all"
            corrupt_gz_bytes = b"\x1f\x8b\x08\x00corrupt-gzip-payload"

            incomplete_db = tmp_path / "incomplete.duckdb"
            con = duckdb.connect(str(incomplete_db))
            con.execute("CREATE TABLE only_one (id INTEGER)")
            con.execute("INSERT INTO only_one VALUES (1)")
            con.close()
            incomplete_bytes = incomplete_db.read_bytes()

            bad_url = "https://releases.example.test/v1/bad.duckdb"
            corrupt_gz_url = "https://releases.example.test/v1/corrupt.duckdb.gz"
            incomplete_url = "https://releases.example.test/v1/incomplete.duckdb"
            missing_url = "https://releases.example.test/v1/missing.duckdb"
            out_url = "https://releases.example.test/v1/analysis_outputs.tar.gz"

            transport = _MockAssetTransport(
                {
                    bad_url: bad_db_bytes,
                    corrupt_gz_url: corrupt_gz_bytes,
                    incomplete_url: incomplete_bytes,
                    out_url: tar_bytes,
                }
            )

            target_db = target_root / "footintel.duckdb"
            target_out = target_root / "analysis_outputs"

            base_env = _clean_hydration_env()
            base_env.update(
                {
                    "FOOTINTEL_ENV": "production",
                    "FOOTINTEL_CORS_ORIGINS": "https://footintel.pages.dev",
                    "FOOTINTEL_DB_PATH": str(target_db),
                    "FOOTINTEL_OUTPUT_DIR": str(target_out),
                    "FOOTINTEL_OUTPUTS_ASSET_URL": out_url,
                    "FOOTINTEL_OUTPUTS_SHA256": _sha256_bytes(tar_bytes),
                }
            )

            with patch("api.hydrate.urlopen", side_effect=transport):
                # 1) Wrong SHA-256
                env = dict(base_env)
                env["FOOTINTEL_DB_ASSET_URL"] = bad_url
                env["FOOTINTEL_DB_SHA256"] = "0" * 64
                with patch.dict(os.environ, env, clear=True):
                    with self.assertRaises(HydrationError) as ctx:
                        ensure_hydrated()
                    self.assertIn("checksum mismatch", str(ctx.exception).lower())
                    self.assertFalse(target_db.exists())

                # 2) Valid SHA-256 of invalid binary -> fails DuckDB verification
                env["FOOTINTEL_DB_SHA256"] = _sha256_bytes(bad_db_bytes)
                with patch.dict(os.environ, env, clear=True):
                    with self.assertRaises(HydrationError) as ctx:
                        ensure_hydrated()
                    self.assertIn("duckdb integrity", str(ctx.exception).lower())
                    self.assertFalse(target_db.exists())

                # 3) Valid SHA-256 of corrupt gzip stream -> fails gzip decompression
                env["FOOTINTEL_DB_ASSET_URL"] = corrupt_gz_url
                env["FOOTINTEL_DB_SHA256"] = _sha256_bytes(corrupt_gz_bytes)
                with patch.dict(os.environ, env, clear=True):
                    with self.assertRaises(HydrationError) as ctx:
                        ensure_hydrated()
                    self.assertIn("gzip", str(ctx.exception).lower())
                    self.assertFalse(target_db.exists())

                # 4) Valid SHA-256 of DuckDB missing CORE_TABLES -> fails table check
                env["FOOTINTEL_DB_ASSET_URL"] = incomplete_url
                env["FOOTINTEL_DB_SHA256"] = _sha256_bytes(incomplete_bytes)
                with patch.dict(os.environ, env, clear=True):
                    with self.assertRaises(HydrationError) as ctx:
                        ensure_hydrated()
                    self.assertIn("missing tables", str(ctx.exception).lower())
                    self.assertFalse(target_db.exists())

                # 5) HTTP 404 download error fails cleanly
                env["FOOTINTEL_DB_ASSET_URL"] = missing_url
                env["FOOTINTEL_DB_SHA256"] = "a" * 64
                with patch.dict(os.environ, env, clear=True):
                    with self.assertRaises(HydrationError) as ctx:
                        ensure_hydrated()
                    self.assertIn("404", str(ctx.exception))
                    self.assertFalse(target_db.exists())

                # Zero leftover temp files in target_root
                self.assertEqual(list(target_root.iterdir()), [])

    def test_05_hardened_tar_gz_rejects_unsafe_archives(self):
        base_files = {
            f: _sample_output_payload(f, tag="safe") for f in REQUIRED_OUTPUT_FILES
        }

        def build_custom_tar(extra_builder) -> bytes:
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz") as tar:
                extra_builder(tar)
            return buf.getvalue()

        def add_all_base(tar: tarfile.TarFile) -> None:
            for name, data in base_files.items():
                info = tarfile.TarInfo(name=name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))

        malicious_cases = []

        # Absolute path
        def add_abs(tar):
            add_all_base(tar)
            info = tarfile.TarInfo(name="/etc/passwd")
            info.size = 4
            tar.addfile(info, io.BytesIO(b"root"))

        malicious_cases.append(("absolute_path", build_custom_tar(add_abs)))

        # Traversal path
        def add_trav(tar):
            add_all_base(tar)
            info = tarfile.TarInfo(name="../evil.csv")
            info.size = 4
            tar.addfile(info, io.BytesIO(b"evil"))

        malicious_cases.append(("traversal", build_custom_tar(add_trav)))

        # Symlink
        def add_sym(tar):
            add_all_base(tar)
            info = tarfile.TarInfo(name="link.csv")
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            tar.addfile(info)

        malicious_cases.append(("symlink", build_custom_tar(add_sym)))

        # Hardlink
        def add_lnk(tar):
            add_all_base(tar)
            info = tarfile.TarInfo(name="hard.csv")
            info.type = tarfile.LNKTYPE
            info.linkname = "01_historical_trends_aggregate.csv"
            tar.addfile(info)

        malicious_cases.append(("hardlink", build_custom_tar(add_lnk)))

        # Unexpected extra file
        def add_unexpected(tar):
            add_all_base(tar)
            info = tarfile.TarInfo(name="unexpected.txt")
            info.size = 3
            tar.addfile(info, io.BytesIO(b"abc"))

        malicious_cases.append(("unexpected_file", build_custom_tar(add_unexpected)))

        # Missing required artifact
        def missing_one(tar):
            for name, data in list(base_files.items())[:-1]:
                info = tarfile.TarInfo(name=name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))

        malicious_cases.append(("missing_required_file", build_custom_tar(missing_one)))

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for label, payload in malicious_cases:
                with self.subTest(case=label):
                    arc = tmp_path / f"{label}.tar.gz"
                    staging = tmp_path / f"staging_{label}"
                    arc.write_bytes(payload)
                    with self.assertRaises(HydrationError):
                        extract_verified_outputs_archive(arc, staging)
                    self.assertFalse(staging.exists())

    def test_06_output_directory_backup_and_rollback_preserves_previous(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target_dir = root / "analysis_outputs"
            staging_dir = root / "analysis_outputs.hydrate.staging.123"
            target_dir.mkdir()
            staging_dir.mkdir()

            for fname in REQUIRED_OUTPUT_FILES:
                (target_dir / fname).write_bytes(_sample_output_payload(fname, tag="old_valid"))
                (staging_dir / fname).write_bytes(_sample_output_payload(fname, tag="new_candidate"))

            orig_replace = os.replace
            call_counter = {"n": 0}

            def failing_second_replace(src, dst):
                call_counter["n"] += 1
                if call_counter["n"] == 2:
                    raise OSError("Simulated disk failure during staging -> target swap")
                return orig_replace(src, dst)

            with patch("api.hydrate.os.replace", side_effect=failing_second_replace):
                with self.assertRaises(HydrationError):
                    replace_directory_with_rollback(staging_dir, target_dir)

            # Previous valid files must remain fully intact via rollback
            self.assertTrue(target_dir.is_dir())
            sentinel = json.loads((target_dir / "06_statistical_results.json").read_text(encoding="utf-8"))
            self.assertEqual(sentinel["tag"], "old_valid")

            # Clean non-failing swap replaces cleanly and removes backup
            replace_directory_with_rollback(staging_dir, target_dir)
            updated = json.loads((target_dir / "06_statistical_results.json").read_text(encoding="utf-8"))
            self.assertEqual(updated["tag"], "new_candidate")
            leftovers = [p for p in root.iterdir() if "backup" in p.name]
            self.assertEqual(leftovers, [])

    def test_07_duckdb_config_and_bounded_concurrent_services(self):
        self.assertTrue(REAL_DB_PATH.is_file(), f"Expected DuckDB at {REAL_DB_PATH}")
        self.assertTrue(REAL_OUT_DIR.is_dir(), f"Expected outputs dir at {REAL_OUT_DIR}")

        db_cfg = get_duckdb_config()
        mem_cfg = get_in_memory_duckdb_config()
        self.assertEqual(db_cfg["threads"], "1")
        self.assertEqual(mem_cfg["threads"], "1")
        self.assertEqual(db_cfg["memory_limit"], "192MB")
        self.assertEqual(mem_cfg["memory_limit"], "64MB")

        max_db = get_db_max_concurrency()
        max_csv = get_csv_max_concurrency()
        self.assertEqual(max_db, 4)
        self.assertEqual(max_csv, 2)

        # Verify actual DuckDB session settings + semaphore saturation & clean release
        with ExitStack() as stack:
            conns = []
            for _ in range(max_db):
                gen = dependencies.get_db_connection()
                con = next(gen)
                stack.callback(lambda g=gen: g.close())
                conns.append(con)

            settings = conns[0].execute(
                "SELECT current_setting('threads'), current_setting('memory_limit')"
            ).fetchone()
            self.assertEqual(settings[0], 1)
            self.assertIn("MiB", str(settings[1]))

            # DB semaphore must be saturated while max_db connections are held
            acquired_extra = dependencies._DB_SEMAPHORE.acquire(blocking=False)
            self.assertFalse(acquired_extra)

        # Semaphore permits must be fully released after connections close
        self.assertTrue(dependencies._DB_SEMAPHORE.acquire(blocking=False))
        dependencies._DB_SEMAPHORE.release()

        # Verify transient CSV :memory: DuckDB settings + semaphore saturation
        with ExitStack() as stack:
            for _ in range(max_csv):
                mem = stack.enter_context(data_store._in_memory_duckdb())
                mem_settings = mem.execute(
                    "SELECT current_setting('threads'), current_setting('memory_limit')"
                ).fetchone()
                self.assertEqual(mem_settings[0], 1)
                self.assertIn("MiB", str(mem_settings[1]))

            self.assertFalse(data_store._CSV_SEMAPHORE.acquire(blocking=False))

        self.assertTrue(data_store._CSV_SEMAPHORE.acquire(blocking=False))
        data_store._CSV_SEMAPHORE.release()

        # Concurrent service execution exercising hierarchical DB -> CSV lock order without deadlock
        def run_workload(idx: int) -> str:
            mode = idx % 4
            if mode == 3:
                rows, total = data_store.query_csv_rows(
                    "01_historical_trends_aggregate.csv", limit=5, offset=0
                )
                self.assertEqual(len(rows), 5)
                self.assertEqual(total, 14)
                return "csv"

            gen = dependencies.get_db_connection()
            con = next(gen)
            try:
                if mode == 0:
                    health = analytics_service.get_health_status(con)
                    self.assertEqual(health.status, "ok")
                    return "health"
                if mode == 1:
                    overview = analytics_service.get_overview_data(con)
                    self.assertEqual(len(overview.historical_summary), 14)
                    return "overview"
                res = player_service.search_players(con, q="Mbapp", limit=5)
                self.assertGreaterEqual(res.pagination.total, 1)
                return "players"
            finally:
                gen.close()

        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(run_workload, range(16)))
        self.assertEqual(len(outcomes), 16)

    def test_08_sha256_stamp_freshness_rehydrates_on_change_and_preserves_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            target_root = tmp_path / "processed"
            target_root.mkdir()

            db_v1 = tmp_path / "db_v1.duckdb"
            _create_valid_duckdb(db_v1)
            db_v1_gz = gzip.compress(db_v1.read_bytes())
            out_v1_tar = _build_valid_outputs_tar_gz(tag="v1")

            db_v2 = tmp_path / "db_v2.duckdb"
            _create_valid_duckdb(db_v2)
            con = duckdb.connect(str(db_v2))
            con.execute("INSERT INTO clubs VALUES (999)")
            con.close()
            db_v2_gz = gzip.compress(db_v2.read_bytes())
            out_v2_tar = _build_valid_outputs_tar_gz(tag="v2")

            db_v1_url = "https://releases.example.test/v1/footintel.duckdb.gz"
            out_v1_url = "https://releases.example.test/v1/analysis_outputs.tar.gz"
            db_v2_url = "https://releases.example.test/v2/footintel.duckdb.gz"
            out_v2_url = "https://releases.example.test/v2/analysis_outputs.tar.gz"

            transport = _MockAssetTransport(
                {
                    db_v1_url: db_v1_gz,
                    out_v1_url: out_v1_tar,
                    db_v2_url: db_v2_gz,
                    out_v2_url: out_v2_tar,
                }
            )

            target_db = target_root / "footintel.duckdb"
            target_out = target_root / "analysis_outputs"
            db_stamp = _stamp_path_for(target_db)
            out_stamp = _stamp_path_for(target_out)

            env = _clean_hydration_env()
            env.update(
                {
                    "FOOTINTEL_ENV": "production",
                    "FOOTINTEL_CORS_ORIGINS": "https://footintel.pages.dev",
                    "FOOTINTEL_DB_PATH": str(target_db),
                    "FOOTINTEL_OUTPUT_DIR": str(target_out),
                    "FOOTINTEL_DB_ASSET_URL": db_v1_url,
                    "FOOTINTEL_DB_SHA256": _sha256_bytes(db_v1_gz),
                    "FOOTINTEL_OUTPUTS_ASSET_URL": out_v1_url,
                    "FOOTINTEL_OUTPUTS_SHA256": _sha256_bytes(out_v1_tar),
                }
            )

            with patch("api.hydrate.urlopen", side_effect=transport):
                with patch.dict(os.environ, env, clear=True):
                    res1 = ensure_hydrated()
                    self.assertEqual(res1.status, "hydrated")
                    self.assertEqual(
                        db_stamp.read_text(encoding="utf-8").strip(),
                        _sha256_bytes(db_v1_gz),
                    )
                    self.assertEqual(
                        out_stamp.read_text(encoding="utf-8").strip(),
                        _sha256_bytes(out_v1_tar),
                    )
                    # Stamp must live outside analysis_outputs/ so output file count stays exact (10)
                    self.assertEqual(len(list(target_out.glob("*"))), len(REQUIRED_OUTPUT_FILES))

                    # Missing DB stamp forces DB rehydration cleanly even when DB exists
                    db_stamp.unlink()
                    res_missing_stamp = ensure_hydrated()
                    self.assertTrue(res_missing_stamp.db_hydrated)
                    self.assertFalse(res_missing_stamp.outputs_hydrated)
                    self.assertEqual(
                        db_stamp.read_text(encoding="utf-8").strip(),
                        _sha256_bytes(db_v1_gz),
                    )

                # Rotate checksums to v2 -> safely rehydrates both DB and outputs
                env_v2 = dict(env)
                env_v2.update(
                    {
                        "FOOTINTEL_DB_ASSET_URL": db_v2_url,
                        "FOOTINTEL_DB_SHA256": _sha256_bytes(db_v2_gz),
                        "FOOTINTEL_OUTPUTS_ASSET_URL": out_v2_url,
                        "FOOTINTEL_OUTPUTS_SHA256": _sha256_bytes(out_v2_tar),
                    }
                )
                with patch.dict(os.environ, env_v2, clear=True):
                    res2 = ensure_hydrated()
                    self.assertEqual(res2.status, "hydrated")
                    self.assertTrue(res2.db_hydrated)
                    self.assertTrue(res2.outputs_hydrated)

                    con_v2 = duckdb.connect(str(target_db), read_only=True)
                    try:
                        self.assertEqual(con_v2.execute("SELECT COUNT(*) FROM clubs").fetchone()[0], 2)
                    finally:
                        con_v2.close()
                    meta = json.loads((target_out / "06_statistical_results.json").read_text(encoding="utf-8"))
                    self.assertEqual(meta["tag"], "v2")
                    self.assertEqual(out_stamp.read_text(encoding="utf-8").strip(), _sha256_bytes(out_v2_tar))

                # Rotate outputs checksum to missing/failing URL -> preserves v2 outputs + v2 stamp
                env_v3_fail = dict(env_v2)
                env_v3_fail["FOOTINTEL_OUTPUTS_ASSET_URL"] = "https://releases.example.test/v3/missing.tar.gz"
                env_v3_fail["FOOTINTEL_OUTPUTS_SHA256"] = "f" * 64
                with patch.dict(os.environ, env_v3_fail, clear=True):
                    with self.assertRaises(HydrationError):
                        ensure_hydrated()
                    meta_after = json.loads((target_out / "06_statistical_results.json").read_text(encoding="utf-8"))
                    self.assertEqual(meta_after["tag"], "v2")
                    self.assertEqual(out_stamp.read_text(encoding="utf-8").strip(), _sha256_bytes(out_v2_tar))

    def test_09_strict_https_redirect_handler_blocks_downgrade(self):
        handler = _StrictHTTPSRedirectHandler()
        orig_req = Request("https://github.com/kushagra3009/FootIntel/releases/download/v1/asset.gz")
        headers = HTTPMessage()
        fp = io.BytesIO(b"")

        # HTTPS -> HTTP redirect must be rejected immediately
        with self.assertRaises(HydrationError) as ctx:
            handler.redirect_request(
                orig_req, fp, 302, "Found", headers, "http://cdn.insecure.example/asset.gz"
            )
        self.assertIn("non-https", str(ctx.exception).lower())

        # HTTPS -> FTP or non-HTTPS scheme must be rejected
        with self.assertRaises(HydrationError):
            handler.redirect_request(
                orig_req, fp, 302, "Found", headers, "ftp://files.example/asset.gz"
            )

        # HTTPS -> HTTPS redirect (e.g. GitHub CDN) must succeed and preserve target URL
        redirected = handler.redirect_request(
            orig_req,
            fp,
            302,
            "Found",
            headers,
            "https://objects.githubusercontent.com/github-production-release-asset/asset.gz",
        )
        self.assertIsNotNone(redirected)
        self.assertTrue(redirected.full_url.startswith("https://objects.githubusercontent.com/"))

    def test_10_production_cors_fail_fast_vs_local_fallback(self):
        # Local dev fallback unchanged when not in production mode
        with patch.dict(os.environ, _clean_hydration_env(), clear=True):
            self.assertEqual(get_cors_origins(), DEFAULT_CORS_ORIGINS)

        # Production modes fail fast when FOOTINTEL_CORS_ORIGINS is missing or blank
        for prod_env in [{"FOOTINTEL_ENV": "production"}, {"RENDER": "true"}]:
            for blank_val in [None, "", "  ,  "]:
                with self.subTest(prod_env=prod_env, blank_val=blank_val):
                    env = _clean_hydration_env()
                    env.update(prod_env)
                    if blank_val is not None:
                        env["FOOTINTEL_CORS_ORIGINS"] = blank_val
                    with patch.dict(os.environ, env, clear=True):
                        with self.assertRaises(ValueError) as ctx:
                            get_cors_origins()
                        self.assertIn("FOOTINTEL_CORS_ORIGINS", str(ctx.exception))
                        with self.assertRaises(ValueError):
                            create_app()
                        with self.assertRaises(HydrationError) as hctx:
                            ensure_hydrated()
                        self.assertIn("FOOTINTEL_CORS_ORIGINS", str(hctx.exception))
                        self.assertEqual(hydrate_main(), 1)

        # Explicit HTTPS origin in production succeeds cleanly
        env_ok = _clean_hydration_env()
        env_ok.update(
            {
                "FOOTINTEL_ENV": "production",
                "FOOTINTEL_CORS_ORIGINS": "https://footintel.pages.dev, https://www.footintel.dev",
            }
        )
        with patch.dict(os.environ, env_ok, clear=True):
            self.assertEqual(
                get_cors_origins(),
                ["https://footintel.pages.dev", "https://www.footintel.dev"],
            )
            app_instance = create_app()
            self.assertIsNotNone(app_instance)

    def test_11_compatible_with_existing_default_config_duckdb_connection(self):
        self.assertTrue(REAL_DB_PATH.is_file(), f"Expected DuckDB at {REAL_DB_PATH}")
        existing_con = duckdb.connect(str(REAL_DB_PATH), read_only=True)
        try:
            gen = dependencies.get_db_connection()
            api_con = next(gen)
            try:
                settings = api_con.execute(
                    "SELECT current_setting('threads'), current_setting('memory_limit')"
                ).fetchone()
                self.assertEqual(settings[0], 1)
                self.assertEqual(str(settings[1]), "183.1 MiB")
                count = api_con.execute("SELECT COUNT(*) FROM transfers").fetchone()[0]
                self.assertGreater(count, 0)
            finally:
                gen.close()
        finally:
            existing_con.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
