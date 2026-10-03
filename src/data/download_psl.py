"""Acquire audited regional OISST v2.1 subsets from NOAA PSL's NCSS service."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import calendar
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd
import requests
import xarray as xr

from src.data.download_oisst import (
    FIRST_AVAILABLE_DATE,
    build_session,
    download_file,
    parse_date,
)
from src.data.preprocess import Region, select_region

BASE_URL = "https://psl.noaa.gov/thredds/ncss/grid/Datasets/noaa.oisst.v2.highres"
LOGGER = logging.getLogger(__name__)
SUBSET_IO_LOCK = threading.Lock()  # netCDF4/HDF5 access is not thread-safe


def year_blocks(start: date, end: date):
    if start < FIRST_AVAILABLE_DATE or end < start:
        raise ValueError("dates must be ordered and start on/after 1981-09-01")
    for year in range(start.year, end.year + 1):
        yield max(start, date(year, 1, 1)), min(end, date(year, 12, 31))


def build_subset_url(start: date, end: date, region: Region) -> str:
    region.validate()
    if start.year != end.year or end < start:
        raise ValueError("a subset request must stay within one calendar year")
    if not 0 <= region.lon_min < region.lon_max < 360:
        raise ValueError("PSL downloader requires non-wrapping longitudes in [0, 360)")
    params = {
        "var": "sst",
        "north": format(region.lat_max, ".15g"),
        "south": format(region.lat_min, ".15g"),
        "east": format(region.lon_max, ".15g"),
        "west": format(region.lon_min, ".15g"),
        "horizStride": 1,
        "time_start": f"{start.isoformat()}T00:00:00Z",
        "time_end": f"{end.isoformat()}T00:00:00Z",
        "timeStride": 1,
        "accept": "netcdf4",
        "disableProjSubset": "on",
        "addLatLon": "true",
    }
    return f"{BASE_URL}/sst.day.mean.{start.year}.nc?{urlencode(params)}"


def file_sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def validate_subset(
    dataset: xr.Dataset, start: date, end: date, region: Region
) -> xr.Dataset:
    """Validate product identity, crop service padding, and require every day."""
    if "sst" not in dataset or "time" not in dataset.coords:
        raise ValueError("NOAA subset must contain SST and time coordinates")
    identity = str(dataset.attrs.get("title", "")) + str(
        dataset.attrs.get("version", "")
    )
    modern = "2.1" in identity and "OISST" in identity
    historical = (
        end <= date(2015, 12, 31)
        and dataset.attrs.get("dataset_title")
        == "NOAA Daily Optimum Interpolation Sea Surface Temperature"
        and str(dataset.attrs.get("title", "")).startswith(
            "NOAA High-resolution Blended Analysis"
        )
    )
    if not modern and not historical:
        raise ValueError("source metadata does not identify NOAA OISST Version 2.1")
    units = str(dataset.sst.attrs.get("units", "")).lower()
    if units not in {"degc", "degree_c", "celsius"}:
        raise ValueError("NOAA subset must provide SST in Celsius")
    selected = select_region(dataset.sst, region).to_dataset(name="sst")
    selected = selected.sel(time=slice(str(start), str(end)))
    expected = pd.date_range(start, end, freq="D")
    actual = pd.DatetimeIndex(selected.time.values)
    if not actual.equals(expected):
        raise ValueError(
            "NOAA subset does not contain exactly the requested daily dates"
        )
    selected.attrs.update(dataset.attrs)
    selected.attrs["source_version_note"] = (
        "OISST v2.1 metadata"
        if modern
        else "Legacy OISST v2 metadata; NOAA NCEI states SST before 2016 is unchanged in v2.1"
    )
    return selected


def download_subset(
    start: date,
    end: date,
    region: Region,
    output_dir: Path,
    session: requests.Session,
    *,
    overwrite: bool = False,
) -> Path:
    url = build_subset_url(start, end, region)
    key = hashlib.sha256(url.encode()).hexdigest()[:12]
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"oisst-psl-region-{start:%Y%m%d}-{end:%Y%m%d}-{key}.nc"
    sidecar = target.with_suffix(".json")
    if target.exists() and not overwrite:
        if not sidecar.exists():
            raise ValueError(
                f"cached subset has no provenance: {target}; use --overwrite"
            )
        metadata = json.loads(sidecar.read_text())
        if metadata.get("request_url") != url or metadata.get("sha256") != file_sha256(
            target
        ):
            raise ValueError(
                f"cached subset failed provenance/checksum validation: {target}; use --overwrite"
            )
        LOGGER.info("Verified cached subset %s", target.name)
        return target
    raw = target.with_suffix(".download.nc")
    partial = target.with_suffix(".part.nc")
    try:
        LOGGER.info("Downloading NOAA PSL subset %s through %s", start, end)
        download_file(url, raw, session, overwrite=True, timeout_seconds=120)
        response_hash = file_sha256(raw)
        with SUBSET_IO_LOCK:
            with xr.open_dataset(raw, engine="netcdf4") as dataset:
                cropped = validate_subset(dataset, start, end, region).load()
            cropped.attrs["acquisition_url"] = url
            cropped.to_netcdf(partial, engine="netcdf4")
        metadata = {
            "provider": "NOAA PSL",
            "product": "NOAA/NCEI OISST v2.1",
            "dataset_doi": "10.25921/RE9P-PT57",
            "request_url": url,
            "date_start": str(start),
            "date_end": str(end),
            "region": asdict(region),
            "grid_shape": dict(cropped.sizes),
            "sha256": file_sha256(partial),
            "response_sha256": response_hash,
            "source_version_note": cropped.attrs["source_version_note"],
            "source_title": cropped.attrs.get("title"),
            "acquired_utc": datetime.now(timezone.utc).isoformat(),
            "processing": "SST only; crop service padding; no temporal interpolation",
        }
        sidecar_partial = sidecar.with_suffix(".json.part")
        sidecar_partial.write_text(json.dumps(metadata, indent=2) + "\n")
        os.replace(partial, target)
        os.replace(sidecar_partial, sidecar)
    finally:
        raw.unlink(missing_ok=True)
        raw.with_suffix(raw.suffix + ".part").unlink(missing_ok=True)
        partial.unlink(missing_ok=True)
        sidecar.with_suffix(".json.part").unlink(missing_ok=True)
    return target


def month_blocks(start: date, end: date):
    for first, last in year_blocks(start, end):
        current = first
        while current <= last:
            month_end = min(
                last,
                date(
                    current.year,
                    current.month,
                    calendar.monthrange(current.year, current.month)[1],
                ),
            )
            yield current, month_end
            current = month_end + timedelta(days=1)


def download_regional_range(
    start: date,
    end: date,
    region: Region,
    output_dir: Path,
    *,
    overwrite: bool = False,
    workers: int = 3,
) -> list[Path]:
    # PSL notes that values less than 15 days old may be revised.
    if end > datetime.now(timezone.utc).date() - timedelta(days=16):
        raise ValueError(
            "choose an end date at least 16 days old to avoid recent provisional data"
        )
    if not 1 <= workers <= 4:
        raise ValueError("workers must be between 1 and 4")

    # Small monthly requests avoid service timeouts on full annual subsets.
    def acquire(block):
        with build_session(retries=2) as session:
            return download_subset(
                *block, region, output_dir, session, overwrite=overwrite
            )

    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(acquire, month_blocks(start, end)))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", type=parse_date, required=True)
    parser.add_argument("--end-date", type=parse_date, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--lat-min", type=float, default=31)
    parser.add_argument("--lat-max", type=float, default=39)
    parser.add_argument("--lon-min", type=float, default=117)
    parser.add_argument("--lon-max", type=float, default=127)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    files = download_regional_range(
        args.start_date,
        args.end_date,
        Region(args.lat_min, args.lat_max, args.lon_min, args.lon_max),
        args.output_dir,
        overwrite=args.overwrite,
        workers=args.workers,
    )
    LOGGER.info("Ready: %d regional files", len(files))


if __name__ == "__main__":
    main()
