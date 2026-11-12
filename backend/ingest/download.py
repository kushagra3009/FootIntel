"""
Download transfermarkt-datasets from Cloudflare R2 public storage.

Source: https://github.com/dcaribou/transfermarkt-datasets
Data is published as gzipped CSVs at a public R2 bucket.
"""

import sys
import gzip
import shutil
import requests
from pathlib import Path

# R2 public bucket (from the project's README / DVC config)
R2_BASE_URL = "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data"

# Key datasets we need for our analysis
DATASETS = [
    "appearances.csv",
    "clubs.csv",
    "competitions.csv",
    "games.csv",
    "game_events.csv",
    "game_lineups.csv",
    "player_valuations.csv",
    "players.csv",
    "transfers.csv",
]

# Project paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"


def download_file(url: str, dest: Path) -> bool:
    """Download a gzipped CSV from R2 and decompress it."""
    try:
        print(f"  Downloading {dest.name} ...")
        response = requests.get(url, stream=True, timeout=120)
        response.raise_for_status()

        dest.parent.mkdir(parents=True, exist_ok=True)

        # Save the gzipped file temporarily, then decompress
        gz_path = dest.with_suffix(".csv.gz")
        with open(gz_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        # Decompress .gz → .csv
        with gzip.open(gz_path, "rb") as f_in:
            with open(dest, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

        # Remove the gz file
        gz_path.unlink()

        size_mb = dest.stat().st_size / (1024 * 1024)
        print(f"  ✓ {dest.name} ({size_mb:.1f} MB)")
        return True

    except requests.RequestException as e:
        print(f"  ✗ Failed to download {url}: {e}")
        return False
    except (gzip.BadGzipFile, OSError) as e:
        print(f"  ✗ Failed to decompress {dest.name}: {e}")
        # Maybe it's not gzipped — try direct download
        try:
            direct_url = url.replace(".csv.gz", ".csv")
            print(f"  Retrying without compression: {direct_url}")
            response = requests.get(direct_url, stream=True, timeout=120)
            response.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            size_mb = dest.stat().st_size / (1024 * 1024)
            print(f"  ✓ {dest.name} ({size_mb:.1f} MB)")
            return True
        except Exception as e2:
            print(f"  ✗ Direct download also failed: {e2}")
            return False


def download_all(force: bool = False) -> dict[str, bool]:
    """Download all required datasets from R2 storage."""
    print("=" * 60)
    print("FootIntel — Dataset Download")
    print(f"Source: {R2_BASE_URL}")
    print("=" * 60)

    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    results = {}

    print(f"\nDownloading {len(DATASETS)} datasets to {RAW_DATA_DIR}\n")

    for filename in DATASETS:
        dest = RAW_DATA_DIR / filename

        if dest.exists() and not force:
            size_mb = dest.stat().st_size / (1024 * 1024)
            print(f"  ⊘ {filename} already exists ({size_mb:.1f} MB), skipping")
            results[filename] = True
            continue

        # Try gzipped version first (what R2 hosts)
        url = f"{R2_BASE_URL}/{filename}.gz"
        success = download_file(url, dest)
        results[filename] = success

    # Summary
    succeeded = sum(1 for v in results.values() if v)
    failed = sum(1 for v in results.values() if not v)
    print(f"\n{'=' * 60}")
    print(f"Download complete: {succeeded} succeeded, {failed} failed")
    print(f"{'=' * 60}")

    return results


if __name__ == "__main__":
    force = "--force" in sys.argv
    results = download_all(force=force)

    if any(not v for v in results.values()):
        sys.exit(1)
