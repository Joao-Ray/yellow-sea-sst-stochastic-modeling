"""Create a regional daily SST and SST-anomaly time series from OISST files."""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, Sequence

import numpy as np
import pandas as pd
import xarray as xr

LOGGER = logging.getLogger(__name__)
ClimatologyFrequency = Literal["dayofyear", "month"]


@dataclass(frozen=True)
class Region:
    """Geographic bounding box in degrees north/east."""

    lat_min: float = 31.0
    lat_max: float = 39.0
    lon_min: float = 117.0
    lon_max: float = 127.0

    def validate(self) -> None:
        if not -90 <= self.lat_min < self.lat_max <= 90:
            raise ValueError("latitude bounds must satisfy -90 <= min < max <= 90")
        if not -180 <= self.lon_min < self.lon_max <= 360:
            raise ValueError("longitude bounds must satisfy -180 <= min < max <= 360")


def _longitude_for_dataset(value: float, longitude: xr.DataArray) -> float:
    """Convert one longitude bound to the dataset's coordinate convention."""
    if float(longitude.min()) >= 0:
        return value % 360
    return ((value + 180) % 360) - 180


def select_region(data: xr.DataArray, region: Region) -> xr.DataArray:
    """Select a bounding box regardless of coordinate sort order."""
    region.validate()
    if "lat" not in data.coords or "lon" not in data.coords:
        raise ValueError("input must contain 'lat' and 'lon' coordinates")

    lon_min = _longitude_for_dataset(region.lon_min, data["lon"])
    lon_max = _longitude_for_dataset(region.lon_max, data["lon"])
    if lon_min >= lon_max:
        raise ValueError("regions crossing the antimeridian are not supported")

    selected = data.where(
        (data["lat"] >= region.lat_min)
        & (data["lat"] <= region.lat_max)
        & (data["lon"] >= lon_min)
        & (data["lon"] <= lon_max),
        drop=True,
    )
    if selected.sizes.get("lat", 0) == 0 or selected.sizes.get("lon", 0) == 0:
        raise ValueError("the requested region does not overlap the input grid")
    return selected


def area_weighted_mean_sst(
    sst: xr.DataArray, *, min_valid_fraction: float = 0.8
) -> xr.DataArray:
    """Compute a cosine-latitude weighted regional mean with coverage control."""
    if not 0 < min_valid_fraction <= 1:
        raise ValueError("min_valid_fraction must be in (0, 1]")
    if "lat" not in sst.dims or "lon" not in sst.dims:
        raise ValueError("SST data must have 'lat' and 'lon' dimensions")

    weights = np.cos(np.deg2rad(sst["lat"])).clip(min=0)
    if "time" not in sst.dims or sst.sizes["time"] == 0:
        raise ValueError("SST data must have a non-empty 'time' dimension")
    # A cell missing throughout the record is treated as land. This empirical
    # mask is fixed across dates; it is not a geographical Yellow Sea polygon.
    ocean_mask = sst.notnull().any("time")
    full_weight = (
        weights.broadcast_like(ocean_mask).where(ocean_mask).sum(("lat", "lon"))
    )
    valid_weight = weights.broadcast_like(sst).where(sst.notnull()).sum(("lat", "lon"))
    valid_fraction = valid_weight / full_weight
    regional_mean = sst.weighted(weights).mean(("lat", "lon"), skipna=True)
    return regional_mean.where(valid_fraction >= min_valid_fraction).rename("sst")


def regularize_and_fill(series: pd.Series, *, max_gap_days: int = 3) -> pd.DataFrame:
    """Reindex daily and interpolate only short, internal gaps."""
    if max_gap_days < 0:
        raise ValueError("max_gap_days must be non-negative")
    if not isinstance(series.index, pd.DatetimeIndex):
        raise TypeError("series index must be a DatetimeIndex")
    if series.index.has_duplicates:
        raise ValueError("series index contains duplicate dates")

    if series.empty:
        raise ValueError("SST series must not be empty")
    if not series.index.equals(series.index.normalize()):
        raise ValueError("SST dates must be normalized to midnight")
    original = (
        series.sort_index().astype(float).replace([np.inf, -np.inf], np.nan).asfreq("D")
    )
    if max_gap_days == 0:
        filled = original.copy()
    else:
        missing = original.isna()
        groups = missing.ne(missing.shift()).cumsum()
        gap_length = missing.groupby(groups).transform("sum")
        candidate = original.interpolate(method="time", limit_area="inside")
        filled = original.where(~missing | (gap_length > max_gap_days), candidate)
    return pd.DataFrame(
        {
            "sst_observed_celsius": original,
            "sst_celsius": filled,
            "is_interpolated": original.isna() & filled.notna(),
        }
    )


def calculate_climatology(
    sst: pd.Series,
    *,
    frequency: ClimatologyFrequency = "dayofyear",
    reference_start: str = "1991-01-01",
    reference_end: str = "2020-12-31",
) -> tuple[pd.Series, pd.Series]:
    """Calculate and map a reference-period seasonal cycle to every date."""
    if not isinstance(sst.index, pd.DatetimeIndex):
        raise TypeError("SST index must be a DatetimeIndex")
    if frequency not in {"dayofyear", "month"}:
        raise ValueError("frequency must be 'dayofyear' or 'month'")

    if pd.Timestamp(reference_start) > pd.Timestamp(reference_end):
        raise ValueError("climatology reference start must not exceed end")
    reference = sst.sort_index().loc[reference_start:reference_end].dropna()
    if reference.empty:
        raise ValueError(
            "no valid SST values fall inside the climatology reference period"
        )

    if frequency == "month":
        reference_key = reference.index.month
        all_key = sst.index.month
    else:
        # Calendar-day strings avoid shifting March-December in leap years.
        reference_key = reference.index.strftime("%m-%d")
        all_key = sst.index.strftime("%m-%d")

    seasonal_cycle = reference.groupby(reference_key).mean()
    if frequency == "dayofyear" and "02-29" not in seasonal_cycle.index:
        neighbors = seasonal_cycle.reindex(["02-28", "03-01"])
        if neighbors.notna().all():
            seasonal_cycle.loc["02-29"] = neighbors.mean()
    mapped = pd.Series(all_key, index=sst.index).map(seasonal_cycle)
    mapped.name = "climatology_celsius"
    seasonal_cycle.name = "sst_celsius"
    return mapped.astype(float), seasonal_cycle


def build_anomaly_table(
    regional_sst: pd.Series,
    *,
    max_gap_days: int = 3,
    climatology: ClimatologyFrequency = "dayofyear",
    reference_start: str = "1991-01-01",
    reference_end: str = "2020-12-31",
) -> pd.DataFrame:
    """Build the auditable SST, climatology, and anomaly output table."""
    output = regularize_and_fill(regional_sst, max_gap_days=max_gap_days)
    mapped, _ = calculate_climatology(
        output["sst_observed_celsius"],
        frequency=climatology,
        reference_start=reference_start,
        reference_end=reference_end,
    )
    output["climatology_celsius"] = mapped
    output["anomaly_celsius"] = output["sst_celsius"] - mapped
    output.index.name = "date"
    return output


def load_regional_sst(
    files: Sequence[Path],
    region: Region,
    *,
    min_valid_fraction: float = 0.8,
) -> pd.Series:
    """Open OISST NetCDF files lazily and return the regional mean series."""
    if not files:
        raise FileNotFoundError("no OISST NetCDF files were found")

    def _preprocess(dataset: xr.Dataset) -> xr.Dataset:
        if "sst" not in dataset:
            raise ValueError("an input file does not contain the 'sst' variable")
        data = dataset["sst"]
        units = str(data.attrs.get("units", "")).lower().replace(" ", "_")
        if units not in {
            "celsius",
            "degree_c",
            "degrees_c",
            "degree_celsius",
            "degrees_celsius",
            "degc",
        }:
            raise ValueError(f"SST units must be Celsius; got {units!r}")
        if "zlev" in data.dims:
            data = data.squeeze("zlev", drop=True)
        return select_region(data, region).to_dataset(name="sst")

    with xr.open_mfdataset(
        [str(path) for path in files],
        combine="by_coords",
        preprocess=_preprocess,
        chunks={"time": 31},
        engine="netcdf4",
    ) as dataset:
        mean = area_weighted_mean_sst(
            dataset["sst"], min_valid_fraction=min_valid_fraction
        ).compute()

    result = mean.to_series()
    result.index = pd.DatetimeIndex(result.index).tz_localize(None).normalize()
    result.name = "sst_celsius"
    return result


def find_input_files(input_dir: Path) -> list[Path]:
    """Find downloaded OISST NetCDF files recursively in stable order."""
    files = sorted(
        [
            *input_dir.rglob("oisst-avhrr-v02r01.*.nc"),
            *input_dir.rglob("oisst-psl-region-*.nc"),
        ]
    )
    if not files:
        raise FileNotFoundError(f"no OISST NetCDF files found under {input_dir}")
    return files


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output-file", required=True, type=Path)
    parser.add_argument("--lat-min", type=float, default=31.0)
    parser.add_argument("--lat-max", type=float, default=39.0)
    parser.add_argument("--lon-min", type=float, default=117.0)
    parser.add_argument("--lon-max", type=float, default=127.0)
    parser.add_argument("--max-gap-days", type=int, default=3)
    parser.add_argument("--min-valid-fraction", type=float, default=0.8)
    parser.add_argument(
        "--climatology", choices=("dayofyear", "month"), default="dayofyear"
    )
    parser.add_argument("--climatology-start", default="1991-01-01")
    parser.add_argument("--climatology-end", default="2020-12-31")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    region = Region(args.lat_min, args.lat_max, args.lon_min, args.lon_max)
    files = find_input_files(args.input_dir)
    LOGGER.info("Processing %d OISST files", len(files))
    regional_sst = load_regional_sst(
        files, region, min_valid_fraction=args.min_valid_fraction
    )
    output = build_anomaly_table(
        regional_sst,
        max_gap_days=args.max_gap_days,
        climatology=args.climatology,
        reference_start=args.climatology_start,
        reference_end=args.climatology_end,
    )
    args.output_file.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(args.output_file, date_format="%Y-%m-%d")
    metadata = {
        "source": "NOAA/NCEI OISST v2.1 AVHRR-only (local input files)",
        "region": asdict(region),
        "spatial_mask": "cells with any valid SST in this input record; not a geographical marine polygon",
        "min_valid_fraction": args.min_valid_fraction,
        "max_gap_days": args.max_gap_days,
        "climatology": args.climatology,
        "climatology_start": args.climatology_start,
        "climatology_end": args.climatology_end,
        "input_file_count": len(files),
        "date_start": str(output.index.min().date()),
        "date_end": str(output.index.max().date()),
        "observed_days": int(output["sst_observed_celsius"].notna().sum()),
        "interpolated_days": int(output["is_interpolated"].sum()),
        "remaining_missing_days": int(output["sst_celsius"].isna().sum()),
    }
    args.output_file.with_suffix(".metadata.json").write_text(
        json.dumps(metadata, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    LOGGER.info("Wrote %d daily records to %s", len(output), args.output_file)


if __name__ == "__main__":
    main()
