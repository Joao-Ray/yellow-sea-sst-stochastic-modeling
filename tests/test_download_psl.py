from datetime import date
import json
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from src.data import download_psl
from src.data.preprocess import Region


def fixture_dataset():
    return xr.Dataset(
        {"sst": (("time", "lat", "lon"), np.ones((4, 3, 3)), {"units": "degC"})},
        coords={
            "time": pd.date_range("2020-01-01", periods=4),
            "lat": [30.875, 35.125, 39.125],
            "lon": [116.875, 122.125, 127.125],
        },
        attrs={"title": "NOAA OISST Analysis Version 2.1", "version": "Version 2.1"},
    )


def test_psl_url_ends_at_midnight_not_next_calendar_day():
    url = download_psl.build_subset_url(date(2020, 1, 1), date(2020, 1, 3), Region())
    query = parse_qs(urlparse(url).query)
    assert query["time_end"] == ["2020-01-03T00:00:00Z"]
    assert query["horizStride"] == ["1"]
    assert url.startswith("https://psl.noaa.gov/")


def test_equivalent_numeric_region_coordinates_reuse_the_same_url():
    first, last = date(2020, 1, 1), date(2020, 1, 3)
    assert download_psl.build_subset_url(first, last, Region(31, 39, 117, 127)) == (
        download_psl.build_subset_url(first, last, Region(31.0, 39.0, 117.0, 127.0))
    )


def test_month_blocks_cross_leap_month_and_year():
    assert list(download_psl.month_blocks(date(2019, 12, 30), date(2020, 3, 2))) == [
        (date(2019, 12, 30), date(2019, 12, 31)),
        (date(2020, 1, 1), date(2020, 1, 31)),
        (date(2020, 2, 1), date(2020, 2, 29)),
        (date(2020, 3, 1), date(2020, 3, 2)),
    ]


def test_subset_crops_extra_service_dates_and_edge_cells():
    selected = download_psl.validate_subset(
        fixture_dataset(), date(2020, 1, 1), date(2020, 1, 3), Region()
    )
    assert dict(selected.sizes) == {"time": 3, "lat": 1, "lon": 1}
    assert pd.Timestamp(selected.time.values[-1]) == pd.Timestamp("2020-01-03")


def test_subset_rejects_missing_dates_and_wrong_product():
    source = fixture_dataset().isel(time=[0, 2, 3])
    with pytest.raises(ValueError, match="exactly"):
        download_psl.validate_subset(
            source, date(2020, 1, 1), date(2020, 1, 3), Region()
        )
    source.attrs["title"] = "unrelated SST product"
    with pytest.raises(ValueError, match="Version 2.1"):
        download_psl.validate_subset(
            source, date(2020, 1, 1), date(2020, 1, 3), Region()
        )


def test_cached_subset_detects_tampering_without_network(tmp_path, monkeypatch):
    def fake_download(url, target, session, **kwargs):
        fixture_dataset().to_netcdf(target)

    monkeypatch.setattr(download_psl, "download_file", fake_download)
    first, last = date(2020, 1, 1), date(2020, 1, 3)
    target = download_psl.download_subset(first, last, Region(), tmp_path, None)
    metadata = json.loads(target.with_suffix(".json").read_text())
    assert metadata["sha256"] == download_psl.file_sha256(target)
    monkeypatch.setattr(
        download_psl,
        "download_file",
        lambda *args, **kwargs: pytest.fail("cache must not redownload"),
    )
    assert download_psl.download_subset(first, last, Region(), tmp_path, None) == target
    with target.open("ab") as handle:
        handle.write(b"altered")
    with pytest.raises(ValueError, match="checksum"):
        download_psl.download_subset(first, last, Region(), tmp_path, None)


def test_legacy_metadata_accepted_only_before_2016():
    source = fixture_dataset()
    source.attrs = {
        "title": "NOAA High-resolution Blended Analysis: Daily Values using AVHRR only",
        "dataset_title": "NOAA Daily Optimum Interpolation Sea Surface Temperature",
    }
    source = source.assign_coords(time=pd.date_range("2010-01-01", periods=4))
    selected = download_psl.validate_subset(
        source, date(2010, 1, 1), date(2010, 1, 3), Region()
    )
    assert "Legacy" in selected.attrs["source_version_note"]
    source = source.assign_coords(time=pd.date_range("2020-01-01", periods=4))
    with pytest.raises(ValueError, match="Version 2.1"):
        download_psl.validate_subset(
            source, date(2020, 1, 1), date(2020, 1, 3), Region()
        )
