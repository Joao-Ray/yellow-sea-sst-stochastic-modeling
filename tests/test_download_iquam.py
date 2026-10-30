from contextlib import nullcontext
import io
import json

import h5py
import numpy as np
import pytest

import src.data.download_iquam as download


def make_source(tmp_path):
    path = tmp_path / "global.h5"
    with h5py.File(path, "w") as f:
        f.attrs["product_version"] = ["V2.10"]
        f.attrs["time_coverage_start"] = ["20230101T000000Z"]
        fields = {
            "lat": [30.0, 35.0, 36.0, 40.0, 50.0, 39.0],
            "lon": [123.0, 123.0, 124.0, 125.0, 120.0, 126.0],
            "sst": [280.0, 281.0, -1.0, np.nan, 285.0, 286.0],
            "quality_level": [5, 5, 0, 3, 5, 5],
            "time": [1, 2, 3, 4, 5, 6],
            "platform_type": [1, 2, 2, 4, 6, 8],
            "iquam_flags": [0, 0, 1, 128, 0, 0],
            "sst_flags": [0, 2, 0, 0, 0, 0],
        }
        for name, values in fields.items():
            f.create_dataset(name, data=values, chunks=(2,))
        f.create_dataset(
            "platform_id",
            data=["A", "B", "C", "D", "E", "F"],
            dtype=h5py.string_dtype(),
            chunks=(2,),
        )
        f["sst"].attrs["units"] = ["kelvin"]
        f["time"].attrs["units"] = ["seconds"]
        f["time"].attrs["comment"] = ["seconds since 1981-01-01 00:00:00"]
    return path.read_bytes()


@pytest.mark.parametrize("modern", [False, True])
def test_exact_geographic_extraction_preserves_unfiltered_flags_and_fill_values(
    tmp_path, monkeypatch, modern
):
    payload = make_source(tmp_path)
    url = "https://star.nesdis.noaa.gov/pub/socd/sst/iquam/v2.10/202301-STAR-L2i_GHRSST-SST-iQuam-V2.10-v01.0-fv02.0.nc"
    if modern:
        path = tmp_path / "global.h5"
        with h5py.File(path, "r+") as source:
            del source.attrs["product_version"]
            del source.attrs["time_coverage_start"]
            source.attrs["title"] = "iQuam2 - in situ SST quality monitor"
            source.attrs["institution"] = "NOAA/NESDIS/STAR"
        payload = path.read_bytes()

    class Range(io.BytesIO):
        def __init__(self, *args, **kwargs):
            super().__init__(payload)
            self.size = len(payload)
            self.identity = '"fixture"'
            self.records = []
            self.blocks = {0: payload}

    monkeypatch.setattr(download, "HTTPRangeFile", Range)
    monkeypatch.setattr(download, "build_session", lambda **kwargs: nullcontext(None))
    region = {"lat_min": 31, "lat_max": 42, "lon_min": 117, "lon_max": 128}
    result = download.acquire_month("202301", url, region, tmp_path / "subset")
    with np.load(result) as q:
        assert q["source_index"].tolist() == [1, 2, 3, 5]
        assert q["platform_id"].tolist() == ["B", "C", "D", "F"]
        assert q["quality_level"].tolist() == [5, 0, 3, 5]
        assert q["iquam_flags"].tolist() == [0, 1, 128, 0]
        np.testing.assert_array_equal(q["sst"], [281.0, -1.0, np.nan, 286.0])
    metadata = json.loads((tmp_path / "subset/iquam-202301.json").read_text())
    assert metadata["global_records"] == 6
    assert metadata["subset_records"] == 4
    # A successful cache is reusable with no server access, and tampering is rejected.
    monkeypatch.setattr(
        download,
        "build_session",
        lambda **kwargs: pytest.fail("cache accessed network"),
    )
    assert download.acquire_month("202301", url, region, tmp_path / "subset") == result
    with open(result, "ab") as stream:
        stream.write(b"corrupted")
    with pytest.raises(ValueError, match="provenance"):
        download.acquire_month("202301", url, region, tmp_path / "subset")
