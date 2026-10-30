"""Audited NOAA NCEP/NCAR R1 surface-forcing subsets for exploratory ablations."""

from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlencode

import numpy as np
import pandas as pd
import xarray as xr

from src.data.download_oisst import build_session, download_file
from src.data.download_psl import SUBSET_IO_LOCK, file_sha256

FIELDS = {
    "dswrf": "dswrf.sfc.gauss",
    "uswrf": "uswrf.sfc.gauss",
    "dlwrf": "dlwrf.sfc.gauss",
    "ulwrf": "ulwrf.sfc.gauss",
    "lhtfl": "lhtfl.sfc.gauss",
    "shtfl": "shtfl.sfc.gauss",
    "uwnd": "uwnd.10m.gauss",
    "vwnd": "vwnd.10m.gauss",
}
BASE = "https://psl.noaa.gov/thredds/ncss/grid/Datasets/ncep.reanalysis.dailyavgs/surface_gauss"


def forcing_url(variable, start, end, box):
    if variable not in FIELDS or start.year != end.year or end < start:
        raise ValueError("known variable and ordered within-year dates required")
    if not (
        0 <= box["west"] < box["east"] < 360
        and -90 <= box["south"] < box["north"] <= 90
    ):
        raise ValueError("invalid non-wrapping forcing box")
    params = {
        "var": variable,
        **box,
        "horizStride": 1,
        "time_start": f"{start}T00:00:00Z",
        "time_end": f"{end}T23:59:59Z",
        "timeStride": 1,
        "accept": "netcdf4",
        "disableProjSubset": "on",
        "addLatLon": "true",
    }
    return f"{BASE}/{FIELDS[variable]}.{start.year}.nc?{urlencode(params)}"


def validate_forcing(dataset, variable, start, end):
    """Fail closed on product, units, calendar, dimensions and missing values."""
    if variable not in FIELDS or variable not in dataset:
        raise ValueError("missing known forcing variable")
    if dataset.attrs.get("dataset_title") != "NCEP-NCAR Reanalysis 1":
        raise ValueError("source must identify NCEP-NCAR Reanalysis 1")
    a = dataset[variable].squeeze(drop=True)
    if set(a.dims) != {"time", "lat", "lon"}:
        raise ValueError("forcing requires time/lat/lon dimensions")
    units = str(a.attrs.get("units", "")).lower().replace(" ", "")
    allowed = (
        {"m/s", "ms-1", "m.s-1"}
        if variable in {"uwnd", "vwnd"}
        else {"w/m^2", "w/m2", "wm-2", "w/m**2"}
    )
    if units not in allowed:
        raise ValueError(f"unexpected {variable} units: {units}")
    a = a.sel(time=slice(str(start), str(end))).transpose("time", "lat", "lon")
    if not pd.DatetimeIndex(a.time.values).equals(pd.date_range(start, end)):
        raise ValueError("forcing calendar must contain exactly every requested day")
    if not np.isfinite(a.values).all() or a.sizes["lat"] < 2 or a.sizes["lon"] < 2:
        raise ValueError("forcing must be finite on a nonempty spatial grid")
    for coord in [a.lat.values, a.lon.values]:
        if len(np.unique(coord)) != len(coord) or not np.isfinite(coord).all():
            raise ValueError("forcing coordinates must be unique and finite")
    return a.to_dataset()


def acquire_forcing(
    variable, start: date, end: date, box, output: Path, *, full_file=False
):
    url = (
        f"https://downloads.psl.noaa.gov/Datasets/ncep.reanalysis.dailyavgs/surface_gauss/{FIELDS[variable]}.{start.year}.nc"
        if full_file
        else forcing_url(variable, start, end, box)
    )
    key = hashlib.sha256(
        (url + json.dumps(box, sort_keys=True) + str(start) + str(end)).encode()
    ).hexdigest()[:12]
    path = output / f"{variable}-{start:%Y%m%d}-{end:%Y%m%d}-{key}.nc"
    sidecar = path.with_suffix(".json")
    output.mkdir(parents=True, exist_ok=True)
    if path.exists():
        record = json.loads(sidecar.read_text())
        if record["request_url"] != url or record["sha256"] != file_sha256(path):
            raise ValueError("forcing cache provenance/checksum mismatch")
        return path
    raw = path.with_suffix(".response.nc")
    partial = path.with_suffix(".partial.nc")
    try:
        with build_session(retries=2) as session:
            # Whole-response retries also cover a truncated streamed response.
            for attempt in range(3):
                try:
                    download_file(
                        url, raw, session, overwrite=True, timeout_seconds=120
                    )
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(30 * (attempt + 1))
        with SUBSET_IO_LOCK:
            with xr.open_dataset(raw, engine="netcdf4") as ds:
                cropped = ds.sel(
                    lat=(ds.lat >= box["south"]) & (ds.lat <= box["north"]),
                    lon=(ds.lon >= box["west"]) & (ds.lon <= box["east"]),
                )
                selected = validate_forcing(cropped, variable, start, end).load()
                attrs = {k: str(v) for k, v in ds.attrs.items()}
            selected.attrs.update(attrs)
            selected.to_netcdf(partial, engine="netcdf4")
        record = {
            "provider": "NOAA PSL",
            "product": "NCEP/NCAR Reanalysis 1 daily averages",
            "variable": variable,
            "request_url": url,
            "date_start": str(start),
            "date_end": str(end),
            "box": box,
            "source_attrs": attrs,
            "variable_attrs": {k: str(v) for k, v in selected[variable].attrs.items()},
            "response_sha256": file_sha256(raw),
            "sha256": file_sha256(partial),
            "sizes": dict(selected.sizes),
            "acquired_utc": datetime.now(timezone.utc).isoformat(),
            "processing": "Daily field only; no interpolation or missing-value filling",
        }
        partial.replace(path)
        sidecar.write_text(json.dumps(record, indent=2) + "\n")
    finally:
        raw.unlink(missing_ok=True)
        raw.with_suffix(raw.suffix + ".part").unlink(missing_ok=True)
        partial.unlink(missing_ok=True)
    return path
