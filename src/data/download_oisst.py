"""Download final NOAA OISST v2.1 AVHRR-only daily NetCDF files."""

from __future__ import annotations

import argparse
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = (
    "https://www.ncei.noaa.gov/data/sea-surface-temperature-optimum-"
    "interpolation/v2.1/access/avhrr"
)
FIRST_AVAILABLE_DATE = date(1981, 9, 1)
LOGGER = logging.getLogger(__name__)


def parse_date(value: str) -> date:
    """Parse an ISO calendar date for command-line arguments."""
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"{value!r} is not a valid date in YYYY-MM-DD format"
        ) from exc


def iter_dates(start_date: date, end_date: date) -> Iterator[date]:
    """Yield each date in an inclusive, validated date interval."""
    if start_date < FIRST_AVAILABLE_DATE:
        raise ValueError(
            f"OISST v2.1 AVHRR begins on {FIRST_AVAILABLE_DATE.isoformat()}"
        )
    if end_date < start_date:
        raise ValueError("end_date must be on or after start_date")

    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def build_url(day: date, base_url: str = BASE_URL) -> str:
    """Return the official NOAA HTTPS URL for a final daily file."""
    stamp = day.strftime("%Y%m%d")
    return f"{base_url}/{day:%Y%m}/oisst-avhrr-v02r01.{stamp}.nc"


def build_session(retries: int = 5) -> requests.Session:
    """Create an HTTP session with conservative retry behavior."""
    retry = Retry(
        total=retries,
        connect=retries,
        read=retries,
        status=retries,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    session = requests.Session()
    session.headers.update(
        {"User-Agent": "yellow-sea-sst-stochastic-modeling/0.1"}
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def download_file(
    url: str,
    destination: Path,
    session: requests.Session,
    *,
    overwrite: bool = False,
    timeout_seconds: int = 120,
) -> str:
    """Download one file atomically, returning ``downloaded`` or ``skipped``."""
    if destination.exists() and not overwrite:
        LOGGER.info("Skipping existing file: %s", destination)
        return "skipped"

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")

    try:
        with session.get(url, stream=True, timeout=timeout_seconds) as response:
            if response.status_code == 404:
                raise FileNotFoundError(
                    f"NOAA final file is not available at {url}. "
                    "Recent dates may still be preliminary."
                )
            response.raise_for_status()
            with partial.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)
        os.replace(partial, destination)
    except Exception:
        partial.unlink(missing_ok=True)
        raise

    LOGGER.info("Downloaded %s", destination)
    return "downloaded"


def download_range(
    start_date: date,
    end_date: date,
    output_dir: Path,
    *,
    overwrite: bool = False,
    dry_run: bool = False,
    base_url: str = BASE_URL,
) -> dict[str, int]:
    """Download an inclusive date range and return action counts."""
    counts = {"downloaded": 0, "skipped": 0, "planned": 0}
    session = build_session()

    for day in iter_dates(start_date, end_date):
        filename = f"oisst-avhrr-v02r01.{day:%Y%m%d}.nc"
        destination = output_dir / f"{day:%Y%m}" / filename
        url = build_url(day, base_url)
        if dry_run:
            LOGGER.info("Would download %s -> %s", url, destination)
            counts["planned"] += 1
            continue
        action = download_file(
            url, destination, session, overwrite=overwrite
        )
        counts[action] += 1

    return counts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", required=True, type=parse_date)
    parser.add_argument("--end-date", required=True, type=parse_date)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--overwrite", action="store_true", help="replace existing files"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print actions without downloading"
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    counts = download_range(
        args.start_date,
        args.end_date,
        args.output_dir,
        overwrite=args.overwrite,
        dry_run=args.dry_run,
    )
    LOGGER.info("Finished: %s", counts)


if __name__ == "__main__":
    main()
