"""Run the entire local NetCDF-to-forecast workflow on labeled synthetic data."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from src.data.preprocess import Region, build_anomaly_table, load_regional_sst
from src.evaluation.experiment import run_experiment, write_experiment


def generate_synthetic_grid(seed: int = 42) -> xr.Dataset:
    """Ten years, fixed land cells, short/long gaps, and a known AR(1) signal."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2010-01-01", "2019-12-31", freq="D")
    phi, sigma = 0.96, 0.22
    anomaly = np.zeros(len(dates))
    anomaly[0] = rng.normal(0, sigma / np.sqrt(1 - phi**2))
    for i in range(1, len(dates)):
        anomaly[i] = phi * anomaly[i - 1] + rng.normal(0, sigma)
    calendar = dates.map(
        lambda d: pd.Timestamp(2000, d.month, d.day).dayofyear
    ).to_numpy()
    seasonal = 15 + 9 * np.sin(2 * np.pi * (calendar - 105) / 366)
    latitude = np.array([31.125, 33.125, 35.125, 37.125, 38.875])
    longitude = np.array([117.125, 119.125, 121.125, 123.125, 125.125, 126.875])
    spatial = -0.3 * (latitude[:, None] - 35) + 0.08 * (longitude[None, :] - 122)
    values = seasonal[:, None, None] + anomaly[:, None, None] + spatial[None, :, :]
    values[:, :, 0] = np.nan  # permanently masked land, never counted as missing sea
    values[800:802, :, :] = np.nan
    values[2200:2212, :, :] = np.nan
    data = xr.Dataset(
        {"sst": (("time", "zlev", "lat", "lon"), values[:, None].astype("float32"))},
        coords={"time": dates, "zlev": [0.0], "lat": latitude, "lon": longitude},
        attrs={
            "title": "SYNTHETIC workflow fixture — NOT NOAA or Yellow Sea observations",
            "data_kind": "synthetic",
            "random_seed": seed,
            "generating_phi": phi,
            "generating_innovation_sd_celsius": sigma,
        },
    )
    data["sst"].attrs["units"] = "degree_C"
    return data


def run_demo(work_dir: Path, output_dir: Path, *, seed: int = 42) -> None:
    work_dir.mkdir(parents=True, exist_ok=True)
    source = work_dir / "synthetic_oisst_fixture.nc"
    generate_synthetic_grid(seed).to_netcdf(source, engine="netcdf4")
    regional = load_regional_sst([source], Region())
    table = build_anomaly_table(
        regional, reference_start="2010-01-01", reference_end="2015-12-31"
    )
    processed = work_dir / "synthetic_sst_daily.csv"
    table.to_csv(processed, date_format="%Y-%m-%d")
    # Read back the CSV to exercise exactly the same input path as real runs.
    table = pd.read_csv(processed, parse_dates=["date"]).set_index("date")
    result = run_experiment(
        table,
        train_end="2015-12-31",
        validation_end="2017-12-31",
        data_kind="synthetic",
    )
    result.protocol.update(
        {
            "random_seed": seed,
            "input_file": str(processed),
            "input_sha256": hashlib.sha256(processed.read_bytes()).hexdigest(),
            "netcdf_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "generating_phi": 0.96,
            "generating_innovation_sd_celsius": 0.22,
        }
    )
    write_experiment(result, output_dir)
    print("SYNTHETIC DEMO — not observational research results")
    print(result.metrics.to_string(index=False))
    print(f"Report: {output_dir / 'summary.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, default=Path("data/raw/demo"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed/demo"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    run_demo(args.work_dir, args.output_dir, seed=args.seed)


if __name__ == "__main__":
    main()
