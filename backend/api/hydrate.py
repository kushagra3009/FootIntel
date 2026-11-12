"""
Idempotent pre-start artifact hydrator for FootIntel production deployments.

Fetches prebuilt DuckDB and Phase 2 analytical artifacts from immutable GitHub
Release assets before Uvicorn binds the HTTP port. Enforces mandatory SHA-256
verification, hardened tar.gz extraction, DuckDB core-table validation, stale
temporary file cleanup, and backup-and-rollback directory replacement.

Local development and tests with no production flags and no asset URLs set exit
immediately as a clean no-op without touching the network or disk.
"""

from __future__ import annotations

from dataclasses import dataclass
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tarfile
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener
import duckdb

from api.config import (
    CORE_TABLES,
    REQUIRED_OUTPUT_FILES,
    get_cors_origins,
    get_db_path,
    get_duckdb_config,
    get_hydration_settings,
    get_output_dir,
    is_production_runtime,
)

CHUNK_SIZE = 1024 * 1024
HTTP_TIMEOUT_SECONDS = 60
MAX_DB_ASSET_BYTES = 512 * 1024 * 1024
MAX_DB_DECOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_OUTPUTS_ARCHIVE_BYTES = 32 * 1024 * 1024
MAX_OUTPUT_MEMBER_BYTES = 16 * 1024 * 1024
MAX_OUTPUTS_TOTAL_BYTES = 32 * 1024 * 1024
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_REQUIRED_OUTPUT_SET = frozenset(REQUIRED_OUTPUT_FILES)


class HydrationError(RuntimeError):
    """Raised when production startup hydration configuration or verification fails."""


@dataclass(frozen=True)
class HydrationResult:
    status: str
    db_hydrated: bool
    outputs_hydrated: bool


class _StrictHTTPSRedirectHandler(HTTPRedirectHandler):
    """Reject HTTP redirects that downgrade an HTTPS download to a non-HTTPS URL."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        orig_scheme = urlparse(req.full_url).scheme.lower()
        resolved = urljoin(req.full_url, newurl)
        target_scheme = urlparse(resolved).scheme.lower()
        if orig_scheme == "https" and target_scheme != "https":
            raise HydrationError(
                f"Blocked insecure redirect from HTTPS to non-HTTPS URL: {resolved!r}"
            )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_HTTPS_OPENER = build_opener(_StrictHTTPSRedirectHandler())


def urlopen(req: Request, timeout: int = HTTP_TIMEOUT_SECONDS):
    """Open asset URLs through the strict HTTPS-only redirect opener."""
    return _HTTPS_OPENER.open(req, timeout=timeout)


def _log(msg: str) -> None:
    print(f"[hydrate] {msg}", file=sys.stderr, flush=True)


def _stamp_path_for(target_path: Path) -> Path:
    """Return hidden sibling stamp path recording the verified asset SHA-256."""
    return target_path.parent / f".{target_path.name}.sha256"


def _read_sha256_stamp(stamp_path: Path) -> str | None:
    if not stamp_path.is_file():
        return None
    try:
        value = stamp_path.read_text(encoding="utf-8").strip().lower()
    except OSError:
        return None
    return value if _SHA256_RE.fullmatch(value) else None


def _write_sha256_stamp(stamp_path: Path, expected_sha256: str) -> None:
    stamp_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_stamp = stamp_path.parent / f".{stamp_path.name}.tmp.{os.getpid()}"
    try:
        tmp_stamp.write_text(f"{expected_sha256.lower()}\n", encoding="utf-8")
        os.replace(tmp_stamp, stamp_path)
    finally:
        tmp_stamp.unlink(missing_ok=True)


def _validate_sha256_format(name: str, digest: str) -> str:
    if not _SHA256_RE.fullmatch(digest):
        raise HydrationError(
            f"{name} must be a valid 64-character hexadecimal SHA-256 digest."
        )
    return digest.lower()


def _validate_asset_url(name: str, url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme == "https" and parsed.netloc:
        return url
    if parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
        return url
    raise HydrationError(
        f"{name} must use https:// (or loopback http:// for local tests), got {url!r}."
    )


def _cleanup_stale_paths(parent_dir: Path, prefix: str) -> None:
    """Remove stale .part/.tmp/.staging/.backup artifacts from prior interrupted runs."""
    if not parent_dir.exists():
        return
    for entry in parent_dir.iterdir():
        if not entry.name.startswith(prefix):
            continue
        if entry.is_dir():
            shutil.rmtree(entry, ignore_errors=True)
        else:
            try:
                entry.unlink()
            except OSError:
                pass


def _download_and_verify_sha256(
    url: str,
    expected_sha256: str,
    dest_part_path: Path,
    *,
    max_bytes: int,
    timeout_seconds: int = HTTP_TIMEOUT_SECONDS,
) -> Path:
    """Stream asset to a .part file in 1 MB chunks and verify exact SHA-256."""
    dest_part_path.parent.mkdir(parents=True, exist_ok=True)
    req = Request(url, headers={"User-Agent": "FootIntel-Hydrator/1.0"})
    hasher = hashlib.sha256()
    total_bytes = 0

    try:
        with urlopen(req, timeout=timeout_seconds) as resp:
            status_code = getattr(resp, "status", 200)
            if status_code >= 400:
                raise HydrationError(f"Asset download failed with HTTP {status_code}: {url}")
            with open(dest_part_path, "wb") as out_f:
                while True:
                    chunk = resp.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    total_bytes += len(chunk)
                    if total_bytes > max_bytes:
                        raise HydrationError(
                            f"Downloaded asset exceeded maximum size limit ({max_bytes} bytes): {url}"
                        )
                    hasher.update(chunk)
                    out_f.write(chunk)
    except HydrationError:
        dest_part_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        dest_part_path.unlink(missing_ok=True)
        raise HydrationError(f"Failed downloading {url}: {exc}") from exc

    if total_bytes == 0:
        dest_part_path.unlink(missing_ok=True)
        raise HydrationError(f"Downloaded asset is empty (0 bytes): {url}")

    actual_sha256 = hasher.hexdigest().lower()
    if actual_sha256 != expected_sha256.lower():
        dest_part_path.unlink(missing_ok=True)
        raise HydrationError(
            f"SHA-256 checksum mismatch for {url}: expected {expected_sha256.lower()}, got {actual_sha256}"
        )

    return dest_part_path


def _is_gzip_asset(url: str, file_path: Path) -> bool:
    """Detect gzipped DuckDB asset by URL suffix or gzip magic header."""
    if urlparse(url).path.lower().endswith(".gz"):
        return True
    with open(file_path, "rb") as f:
        return f.read(2) == b"\x1f\x8b"


def _decompress_gzip_stream(src_gz: Path, dst_path: Path) -> None:
    """Stream-decompress a gzip file with strict uncompressed size ceiling."""
    written = 0
    try:
        with gzip.open(src_gz, "rb") as gz_in, open(dst_path, "wb") as out_f:
            while True:
                chunk = gz_in.read(CHUNK_SIZE)
                if not chunk:
                    break
                written += len(chunk)
                if written > MAX_DB_DECOMPRESSED_BYTES:
                    raise HydrationError(
                        f"Decompressed database exceeded maximum size limit ({MAX_DB_DECOMPRESSED_BYTES} bytes)."
                    )
                out_f.write(chunk)
    except HydrationError:
        dst_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        dst_path.unlink(missing_ok=True)
        raise HydrationError(f"Corrupt gzipped database stream: {exc}") from exc

    if written == 0:
        dst_path.unlink(missing_ok=True)
        raise HydrationError("Decompressed DuckDB file is empty (0 bytes).")


def verify_duckdb_file(db_path: Path) -> None:
    """Open DuckDB read-only and verify all core tables exist and contain rows."""
    if not db_path.is_file() or db_path.stat().st_size == 0:
        raise HydrationError(f"DuckDB file missing or empty: {db_path}")

    con: duckdb.DuckDBPyConnection | None = None
    try:
        con = duckdb.connect(str(db_path), read_only=True, config=get_duckdb_config())
        tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
        missing = [tbl for tbl in CORE_TABLES if tbl not in tables]
        if missing:
            raise HydrationError(f"DuckDB integrity check failed; missing tables: {missing}")

        for tbl in CORE_TABLES:
            res = con.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()
            count = int(res[0]) if res else 0
            if count <= 0:
                raise HydrationError(
                    f"DuckDB integrity check failed; table '{tbl}' has {count} rows."
                )
    except HydrationError:
        raise
    except Exception as exc:
        raise HydrationError(f"DuckDB integrity verification failed: {exc}") from exc
    finally:
        if con is not None:
            con.close()


def verify_outputs_dir(output_dir: Path) -> None:
    """Confirm all 10 required Phase 2 output artifacts exist, are non-empty, and parse cleanly."""
    if not output_dir.is_dir():
        raise HydrationError(f"Outputs directory missing: {output_dir}")

    for filename in REQUIRED_OUTPUT_FILES:
        file_path = output_dir / filename
        if not file_path.is_file() or file_path.stat().st_size == 0:
            raise HydrationError(f"Required Phase 2 output missing or empty: {filename}")
        if filename.endswith(".json"):
            try:
                with open(file_path, encoding="utf-8") as f:
                    json.load(f)
            except Exception as exc:
                raise HydrationError(f"Invalid JSON artifact {filename}: {exc}") from exc


def _normalize_output_member_name(raw_name: str, is_dir: bool) -> str | None:
    """
    Validate and normalize a tar member name.
    Returns None for an allowed root container directory, or the exact allowlisted
    artifact filename for regular files. Raises HydrationError on any unsafe path.
    """
    if not raw_name or "\x00" in raw_name or "\\" in raw_name or raw_name.startswith("/"):
        raise HydrationError(f"Rejected unsafe archive member path: {raw_name!r}")
    if ":" in raw_name.split("/")[0]:
        raise HydrationError(f"Rejected drive-qualified archive member path: {raw_name!r}")

    raw_parts = raw_name.split("/")
    if ".." in raw_parts:
        raise HydrationError(f"Rejected path-traversal archive member: {raw_name!r}")

    posix_parts = [p for p in PurePosixPath(raw_name).parts if p not in {"", "."}]
    if not posix_parts:
        if is_dir:
            return None
        raise HydrationError(f"Rejected empty archive file path: {raw_name!r}")

    if posix_parts[0] == "analysis_outputs":
        posix_parts = posix_parts[1:]
        if not posix_parts:
            if is_dir:
                return None
            raise HydrationError(f"Rejected directory path as file: {raw_name!r}")

    if is_dir:
        raise HydrationError(f"Unexpected subdirectory in outputs archive: {raw_name!r}")

    if len(posix_parts) != 1:
        raise HydrationError(f"Unexpected nested path in outputs archive: {raw_name!r}")

    filename = posix_parts[0]
    if filename not in _REQUIRED_OUTPUT_SET:
        raise HydrationError(f"Unexpected file in outputs archive: {filename!r}")
    return filename


def extract_verified_outputs_archive(archive_path: Path, staging_dir: Path) -> None:
    """
    Hardened tar.gz extraction:
    rejects symlinks, hardlinks, device/FIFO entries, absolute or traversal paths,
    unexpected files, size bombs, or incomplete artifact sets before extracting.
    """
    staging_dir.mkdir(parents=True, exist_ok=True)
    seen_files: set[str] = set()
    declared_total = 0

    try:
        with tarfile.open(archive_path, mode="r:gz") as tar:
            members = tar.getmembers()
            validated_members: list[tuple[tarfile.TarInfo, str]] = []

            for member in members:
                if member.issym() or member.islnk():
                    raise HydrationError(
                        f"Rejected link member in outputs archive: {member.name!r}"
                    )
                if member.ischr() or member.isblk() or member.isfifo() or not (
                    member.isfile() or member.isdir()
                ):
                    raise HydrationError(
                        f"Rejected unsupported member type in outputs archive: {member.name!r}"
                    )

                clean_name = _normalize_output_member_name(member.name, member.isdir())
                if member.isdir():
                    continue
                assert clean_name is not None

                if clean_name in seen_files:
                    raise HydrationError(
                        f"Duplicate file entry in outputs archive: {clean_name!r}"
                    )
                if member.size <= 0 or member.size > MAX_OUTPUT_MEMBER_BYTES:
                    raise HydrationError(
                        f"Invalid file size ({member.size} bytes) for archive member {clean_name!r}"
                    )
                declared_total += member.size
                if declared_total > MAX_OUTPUTS_TOTAL_BYTES:
                    raise HydrationError(
                        f"Outputs archive exceeded total uncompressed size cap ({MAX_OUTPUTS_TOTAL_BYTES} bytes)."
                    )
                seen_files.add(clean_name)
                validated_members.append((member, clean_name))

            missing = sorted(_REQUIRED_OUTPUT_SET - seen_files)
            if missing:
                raise HydrationError(
                    f"Outputs archive missing required Phase 2 files: {missing}"
                )

            actual_total = 0
            for member, clean_name in validated_members:
                src_stream = tar.extractfile(member)
                if src_stream is None:
                    raise HydrationError(f"Failed extracting stream for {clean_name!r}")
                target_file = staging_dir / clean_name
                member_written = 0
                with src_stream, open(target_file, "wb") as out_f:
                    while True:
                        chunk = src_stream.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        member_written += len(chunk)
                        actual_total += len(chunk)
                        if (
                            member_written > MAX_OUTPUT_MEMBER_BYTES
                            or actual_total > MAX_OUTPUTS_TOTAL_BYTES
                        ):
                            raise HydrationError(
                                "Actual decompressed output size exceeded safety ceiling."
                            )
                        out_f.write(chunk)
    except HydrationError:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise HydrationError(f"Failed extracting outputs archive: {exc}") from exc

    try:
        verify_outputs_dir(staging_dir)
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise


def replace_directory_with_rollback(staging_dir: Path, target_dir: Path) -> None:
    """
    Safely replace target_dir with staging_dir using backup-and-rollback.
    Preserves previous valid outputs if the swap fails.
    """
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    backup_dir = target_dir.parent / f"{target_dir.name}.hydrate.backup.{os.getpid()}"
    if backup_dir.exists():
        shutil.rmtree(backup_dir, ignore_errors=True)

    had_existing = target_dir.exists()
    if had_existing:
        try:
            os.replace(target_dir, backup_dir)
        except Exception as exc:
            raise HydrationError(
                f"Failed moving existing outputs directory to backup: {exc}"
            ) from exc

    try:
        os.replace(staging_dir, target_dir)
    except Exception as exc:
        if had_existing and backup_dir.exists() and not target_dir.exists():
            try:
                os.replace(backup_dir, target_dir)
            except OSError as rollback_exc:
                raise HydrationError(
                    f"Output directory replacement failed ({exc}) AND rollback failed ({rollback_exc})."
                ) from exc
        raise HydrationError(
            f"Failed swapping staged outputs into {target_dir}: {exc}"
        ) from exc

    if had_existing and backup_dir.exists():
        shutil.rmtree(backup_dir, ignore_errors=True)


def _hydrate_database(db_path: Path, asset_url: str, expected_sha256: str) -> None:
    prefix = f"{db_path.name}.hydrate."
    _cleanup_stale_paths(db_path.parent, prefix)

    pid = os.getpid()
    part_path = db_path.parent / f"{prefix}{pid}.part"
    staged_db_path = db_path.parent / f"{prefix}{pid}.tmp"
    try:
        _log(f"Downloading DuckDB asset from {asset_url}...")
        _download_and_verify_sha256(
            asset_url,
            expected_sha256,
            part_path,
            max_bytes=MAX_DB_ASSET_BYTES,
        )
        if _is_gzip_asset(asset_url, part_path):
            _log("Decompressing gzipped DuckDB asset...")
            _decompress_gzip_stream(part_path, staged_db_path)
            part_path.unlink(missing_ok=True)
        else:
            os.replace(part_path, staged_db_path)

        _log("Verifying DuckDB core tables before atomic replacement...")
        verify_duckdb_file(staged_db_path)
        os.replace(staged_db_path, db_path)
        _write_sha256_stamp(_stamp_path_for(db_path), expected_sha256)
        _log(f"Hydrated DuckDB database cleanly at {db_path}.")
    finally:
        part_path.unlink(missing_ok=True)
        staged_db_path.unlink(missing_ok=True)


def _hydrate_outputs(output_dir: Path, asset_url: str, expected_sha256: str) -> None:
    prefix = f"{output_dir.name}.hydrate."
    _cleanup_stale_paths(output_dir.parent, prefix)

    pid = os.getpid()
    part_path = output_dir.parent / f"{prefix}{pid}.tar.gz.part"
    staging_dir = output_dir.parent / f"{prefix}staging.{pid}"
    try:
        _log(f"Downloading Phase 2 outputs archive from {asset_url}...")
        _download_and_verify_sha256(
            asset_url,
            expected_sha256,
            part_path,
            max_bytes=MAX_OUTPUTS_ARCHIVE_BYTES,
        )
        extract_verified_outputs_archive(part_path, staging_dir)
        part_path.unlink(missing_ok=True)
        replace_directory_with_rollback(staging_dir, output_dir)
        _write_sha256_stamp(_stamp_path_for(output_dir), expected_sha256)
        _log(f"Hydrated validated Phase 2 outputs cleanly at {output_dir}.")
    finally:
        part_path.unlink(missing_ok=True)
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)


def ensure_hydrated() -> HydrationResult:
    """
    Validate runtime hydration config and hydrate missing DuckDB / outputs artifacts.
    In local dev without production flags or hydration env vars, returns immediately as a no-op.
    """
    production = is_production_runtime()
    settings = get_hydration_settings()
    any_hydration_var = any(settings.values())

    if not production and not any_hydration_var:
        return HydrationResult(
            status="skipped_local",
            db_hydrated=False,
            outputs_hydrated=False,
        )

    if production:
        try:
            get_cors_origins()
        except ValueError as exc:
            raise HydrationError(str(exc)) from exc

    required_keys = {
        "FOOTINTEL_DB_ASSET_URL": settings["db_asset_url"],
        "FOOTINTEL_DB_SHA256": settings["db_sha256"],
        "FOOTINTEL_OUTPUTS_ASSET_URL": settings["outputs_asset_url"],
        "FOOTINTEL_OUTPUTS_SHA256": settings["outputs_sha256"],
    }
    missing = [key for key, value in required_keys.items() if not value]
    if missing:
        raise HydrationError(
            "Missing required hydration configuration: " + ", ".join(missing)
        )

    db_url = _validate_asset_url("FOOTINTEL_DB_ASSET_URL", settings["db_asset_url"])
    db_sha = _validate_sha256_format("FOOTINTEL_DB_SHA256", settings["db_sha256"])
    out_url = _validate_asset_url(
        "FOOTINTEL_OUTPUTS_ASSET_URL", settings["outputs_asset_url"]
    )
    out_sha = _validate_sha256_format(
        "FOOTINTEL_OUTPUTS_SHA256", settings["outputs_sha256"]
    )

    db_path = get_db_path()
    output_dir = get_output_dir()
    db_stamp = _stamp_path_for(db_path)
    out_stamp = _stamp_path_for(output_dir)
    db_hydrated = False
    outputs_hydrated = False

    db_valid = False
    if db_path.is_file() and db_path.stat().st_size > 0:
        recorded_db_sha = _read_sha256_stamp(db_stamp)
        if recorded_db_sha != db_sha:
            _log(
                f"Existing DuckDB stamp ({recorded_db_sha or 'missing'}) does not match "
                f"configured SHA-256 ({db_sha}); re-hydrating."
            )
        else:
            try:
                verify_duckdb_file(db_path)
                db_valid = True
            except HydrationError as exc:
                _log(f"Existing DuckDB failed validation ({exc}); re-hydrating.")

    if not db_valid:
        _hydrate_database(db_path, db_url, db_sha)
        db_hydrated = True
    else:
        _log(f"Verified existing DuckDB and SHA-256 stamp at {db_path}; skipping download.")

    outputs_valid = False
    if output_dir.is_dir():
        recorded_out_sha = _read_sha256_stamp(out_stamp)
        if recorded_out_sha != out_sha:
            _log(
                f"Existing outputs stamp ({recorded_out_sha or 'missing'}) does not match "
                f"configured SHA-256 ({out_sha}); re-hydrating."
            )
        else:
            try:
                verify_outputs_dir(output_dir)
                outputs_valid = True
            except HydrationError as exc:
                _log(f"Existing outputs failed validation ({exc}); re-hydrating.")

    if not outputs_valid:
        _hydrate_outputs(output_dir, out_url, out_sha)
        outputs_hydrated = True
    else:
        _log(
            f"Verified existing outputs directory and SHA-256 stamp at {output_dir}; skipping download."
        )

    return HydrationResult(
        status="hydrated" if (db_hydrated or outputs_hydrated) else "verified_existing",
        db_hydrated=db_hydrated,
        outputs_hydrated=outputs_hydrated,
    )


def main() -> int:
    try:
        result = ensure_hydrated()
        _log(f"Startup hydration status: {result.status}")
        return 0
    except HydrationError as exc:
        _log(f"FATAL: {exc}")
        return 1
    except Exception as exc:
        _log(f"FATAL unexpected hydration error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

