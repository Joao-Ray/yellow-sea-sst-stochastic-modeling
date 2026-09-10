import numpy as np
import pandas as pd
import pytest
import xarray as xr

from src.data.preprocess import (
    Region,
    area_weighted_mean_sst,
    build_anomaly_table,
    calculate_climatology,
    regularize_and_fill,
    select_region,
)


def test_select_region_handles_descending_latitude() -> None:
    data = xr.DataArray(
        np.arange(12).reshape(3, 4),
        coords={"lat": [40.0, 35.0, 30.0], "lon": [115.0, 120.0, 125.0, 130.0]},
        dims=("lat", "lon"),
    )
    selected = select_region(data, Region(31, 39, 117, 127))
    assert selected["lat"].values.tolist() == [35.0]
    assert selected["lon"].values.tolist() == [120.0, 125.0]


def test_area_weighted_mean_masks_days_with_low_coverage() -> None:
    data = xr.DataArray(
        [
            [[10.0, 10.0], [20.0, 20.0]],
            [[np.nan, np.nan], [20.0, np.nan]],
        ],
        coords={
            "time": pd.date_range("2000-01-01", periods=2),
            "lat": [0.0, 60.0],
            "lon": [120.0, 121.0],
        },
        dims=("time", "lat", "lon"),
    )
    result = area_weighted_mean_sst(data, min_valid_fraction=0.5)
    assert result.isel(time=0).item() == pytest.approx(40 / 3)
    assert np.isnan(result.isel(time=1).item())


def test_regularize_and_fill_marks_only_short_internal_gap() -> None:
    series = pd.Series(
        [10.0, 12.0, 20.0],
        index=pd.to_datetime(["2000-01-01", "2000-01-03", "2000-01-07"]),
    )
    output = regularize_and_fill(series, max_gap_days=1)
    assert output.loc["2000-01-02", "sst_celsius"] == pytest.approx(11.0)
    assert bool(output.loc["2000-01-02", "is_interpolated"])
    assert np.isnan(output.loc["2000-01-05", "sst_celsius"])


def test_monthly_climatology_uses_only_reference_period() -> None:
    index = pd.to_datetime(
        ["1991-01-01", "1991-01-02", "1991-02-01", "2021-01-01"]
    )
    series = pd.Series([10.0, 12.0, 20.0, 100.0], index=index)
    mapped, cycle = calculate_climatology(
        series,
        frequency="month",
        reference_start="1991-01-01",
        reference_end="2020-12-31",
    )
    assert cycle.loc[1] == pytest.approx(11.0)
    assert mapped.loc["2021-01-01"] == pytest.approx(11.0)


def test_build_anomaly_table_subtracts_calendar_day_cycle() -> None:
    index = pd.to_datetime(
        ["1991-01-01", "1991-01-02", "1992-01-01", "1992-01-02"]
    )
    series = pd.Series([10.0, 20.0, 12.0, 18.0], index=index)
    table = build_anomaly_table(
        series,
        max_gap_days=0,
        climatology="dayofyear",
        reference_start="1991-01-01",
        reference_end="1992-12-31",
    )
    assert table.loc["1991-01-01", "climatology_celsius"] == pytest.approx(11.0)
    assert table.loc["1991-01-01", "anomaly_celsius"] == pytest.approx(-1.0)
