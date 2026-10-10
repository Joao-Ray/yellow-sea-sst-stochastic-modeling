import numpy as np
import pandas as pd
import pytest

from src.data.download_amsr2 import HTTPRangeFile
from src.independent import (
    aggregate_results,
    project_forecast,
    quality_mask,
    weighted_daily_score,
)


class Response:
    status_code = 206

    def __init__(self, payload, start, end, etag):
        self.content = payload[start : end + 1]
        self.headers = {
            "Content-Range": f"bytes {start}-{min(end, len(payload) - 1)}/{len(payload)}",
            "ETag": etag,
        }

    def raise_for_status(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class Session:
    def __init__(self, payload=b"0123456789", corrupt=None):
        self.payload, self.corrupt, self.calls = payload, corrupt, []

    def get(self, url, headers, timeout):
        self.calls.append(headers)
        start, end = map(int, headers["Range"].removeprefix("bytes=").split("-"))
        response = Response(self.payload, start, end, '"stable"')
        if self.corrupt and len(self.calls) > 1:
            self.corrupt(response)
        return response


def test_byte_ranges_cross_blocks_and_cache_without_changing_identity():
    session = Session()
    with HTTPRangeFile("url", session, block_size=4) as stream:
        stream.seek(2)
        assert stream.read(7) == b"2345678"
        stream.seek(0)
        assert stream.read() == session.payload
        assert len(session.calls) == 3
        assert all(c["If-Match"] == '"stable"' for c in session.calls[1:])
        assert [(r["start"], r["end"]) for r in stream.records] == [
            (0, 3),
            (4, 7),
            (8, 9),
        ]


@pytest.mark.parametrize(
    "corrupt",
    [
        lambda r: r.headers.update(ETag='"changed"'),
        lambda r: r.headers.update({"Content-Range": "bytes 0-3/10"}),
        lambda r: setattr(r, "status_code", 200),
        lambda r: setattr(r, "content", b"short"),
    ],
)
def test_mixed_or_unverifiable_remote_bytes_are_rejected(corrupt):
    with HTTPRangeFile("url", Session(corrupt=corrupt), block_size=4) as stream:
        with pytest.raises(ValueError):
            stream.read(8)


def test_quality_gate_rejects_fill_time_coast_and_unfrozen_cells():
    sst = np.array([[10.0, -999, 36, 10, 10, 10, 10]])
    hours = np.array([[2.0, 2, 2, 24, 2, 2, 2]])
    fixed = np.array([[True, True, True, True, True, False, True]])
    coast = np.array([[0, 0, 0, 0, 1, 0, 0]])
    np.testing.assert_array_equal(
        quality_mask(sst, hours, [coast], fixed),
        [[True, False, False, False, False, False, True]],
    )
    coast[0, 0] = 255
    with pytest.raises(ValueError, match="zero/one"):
        quality_mask(sst, hours, [coast], fixed)


def test_spatial_projection_preserves_regional_mean_and_origin_offsets():
    origin = np.array([9.0, 12.0, 15.0])
    weights = np.array([1.0, 2.0, 3.0])
    regional = np.average(origin, weights=weights)
    predicted = project_forecast(origin, 20.0, regional)
    assert np.average(predicted, weights=weights) == pytest.approx(20.0)
    np.testing.assert_allclose(predicted - 20.0, origin - regional)


def test_all_methods_share_valid_cells_and_minimum_support():
    observed = np.array([10.0, 100.0, 30.0])
    predictions = {
        "a": np.array([12.0, 0.0, 33.0]),
        "b": np.array([10.0, np.nan, 30.0]),
    }
    scores, common = weighted_daily_score(
        observed, predictions, np.array([1.0, 1.0, 3.0]), np.ones(3, bool), 2
    )
    np.testing.assert_array_equal(common, [True, False, True])
    assert scores["a"]["mse"] == pytest.approx(7.75)
    assert scores["b"]["mse"] == 0
    assert (
        weighted_daily_score(observed, predictions, np.ones(3), np.ones(3, bool), 3)[0]
        is None
    )


def test_scoring_days_are_equal_weight_and_do_not_pool_spatial_replicates():
    rows = []
    for model, losses in [("persistence", [4.0, 4.0]), ("selected", [1.0, 9.0])]:
        for day, loss, count in zip(
            pd.date_range("2026-01-01", periods=2), losses, [20, 200]
        ):
            rows.append(
                {
                    "date": day,
                    "pass": "descending",
                    "horizon_days": 1,
                    "model": model,
                    "n_cells": count,
                    "mse": loss,
                    "mae": np.sqrt(loss),
                    "bias": 0.0,
                }
            )
    agreement = pd.DataFrame(
        {
            "pass": ["descending"],
            "n_cells": [20],
            "mse": [1.0],
            "mae": [1.0],
            "bias": [0.0],
        }
    )
    config = {
        "minimum_scoring_days": 2,
        "bootstrap_block_days": [1],
        "bootstrap_replicates": 100,
        "random_seed": 1,
    }
    metrics, _, _ = aggregate_results(pd.DataFrame(rows), agreement, config)
    assert metrics.loc[metrics.model.eq("selected"), "rmse"].iloc[0] == pytest.approx(
        np.sqrt(5)
    )
    rows[-1]["n_cells"] = 199
    with pytest.raises(ValueError, match="same observation support"):
        aggregate_results(pd.DataFrame(rows), agreement, config)


def test_target_day_oisst_cannot_enter_external_forecasts(tmp_path):
    import xarray as xr
    from src.independent import evaluate_pairs

    path = tmp_path / "amsr2-2026-01-02.npz"
    flags = np.zeros((2, 1, 2), dtype=int)
    np.savez(
        path,
        SST=np.full((2, 1, 2), 12.0),
        time=np.full((2, 1, 2), 2.0),
        lat=[35.0],
        lon=[121.0, 122.0],
        land_mask=flags,
        coast_mask=flags,
        sea_ice_mask=flags,
        noobs_mask=flags,
    )
    days = pd.date_range("2026-01-01", periods=2)
    fields = xr.DataArray(
        np.array([[[10.0, 14.0]], [[12.0, 16.0]]]),
        dims=["time", "lat", "lon"],
        coords={"time": days, "lat": [35.0], "lon": [121.0, 122.0]},
    )
    model = {
        "selected_methods": {"1": "selected"},
        "spatial_mask": {
            "lat": [35.0],
            "lon": [121.0, 122.0],
            "selected_cells": [[35.0, 121.0], [35.0, 122.0]],
        },
    }
    predictions = pd.DataFrame(
        {
            "date": [days[1]] * 2,
            "horizon_days": [1, 1],
            "model": ["selected", "persistence"],
            "predicted_sst_celsius": [13.0, 12.0],
        }
    )
    regional = pd.Series([12.0, 14.0], index=days)
    config = {"horizons": [1], "minimum_daily_cells": 2}
    before, _, agreement = evaluate_pairs(
        [str(path)], fields, model, predictions, regional, config
    )
    fields.loc[{"time": days[1]}] += 100
    after, _, changed_agreement = evaluate_pairs(
        [str(path)], fields, model, predictions, regional, config
    )
    pd.testing.assert_frame_equal(before, after)
    assert not agreement.equals(changed_agreement)


def test_locked_2026_observations_supply_origins_and_inconsistent_rows_fail(
    tmp_path, monkeypatch
):
    import hashlib
    import json
    from src.independent import load_inputs

    monkeypatch.chdir(tmp_path)
    files = {
        "paper/validation/frozen_protocol.json": "{}",
        "data/processed/research/iho_yellow_sea_daily.csv": "date,sst_observed_celsius\n2025-12-31,10.5\n",
        "data/processed/validation/predictions.csv": "date,origin_date,observed_sst_celsius\n2026-01-01,2025-12-31,10.1\n2026-01-01,2025-12-31,10.1\n2026-01-02,2026-01-01,10.2\n",
    }
    protocol = {"input_sha256": {}}
    for name, content in files.items():
        from pathlib import Path

        p = Path(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        protocol["input_sha256"][name] = hashlib.sha256(p.read_bytes()).hexdigest()
    frozen = tmp_path / "frozen.json"
    frozen.write_text(json.dumps(protocol))
    *_, regional = load_inputs(frozen)
    assert regional.loc["2025-12-31"] == 10.5
    assert regional.loc["2026-01-01"] == 10.1
    p = tmp_path / "data/processed/validation/predictions.csv"
    p.write_text(
        p.read_text().replace(
            "2026-01-01,2025-12-31,10.1", "2026-01-01,2025-12-31,11.1", 1
        )
    )
    protocol["input_sha256"][str(p.relative_to(tmp_path))] = hashlib.sha256(
        p.read_bytes()
    ).hexdigest()
    frozen.write_text(json.dumps(protocol))
    with pytest.raises(ValueError, match="observations disagree"):
        load_inputs(frozen)
