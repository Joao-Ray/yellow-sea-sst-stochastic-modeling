import copy

import numpy as np
import pandas as pd
import pytest

from src.evaluation.research_experiment import run_research_fold
from src.validation import freeze_models, frozen_means, score_holdout
from tests.test_research import design, fold, synthetic_sst


def validation_design():
    return {
        **fold(),
        "test_start": "2016-01-01",
        "test_end": "2016-08-31",
        "horizons": [1, 7],
        "candidate_order": [
            "climatology",
            "persistence",
            "raw_persistence",
            "trend_seasonal",
            "ar_day",
            "ar_harmonic",
            "ar_harmonic_trend",
            "ridge_harmonic_trend",
        ],
        "baseline": "persistence",
        "interval_level": 0.95,
        "minimum_scoring_days": 200,
        "bootstrap_block_days": [30, 60],
        "bootstrap_replicates": 100,
        "random_seed": 42,
    }


def test_unseen_targets_cannot_change_frozen_methods_or_radii():
    history = synthetic_sst()
    frozen = freeze_models(history, validation_design(), design())
    altered = history.copy()
    altered.loc["2016-01-01":] += 200
    assert freeze_models(altered, validation_design(), design()) == frozen
    before = copy.deepcopy(frozen)
    score_holdout(altered, frozen)
    assert frozen == before


def test_calibration_cannot_change_overall_method_selection():
    history = synthetic_sst()
    frozen = freeze_models(history, validation_design(), design())
    altered = history.copy()
    altered.loc["2015-01-01":"2015-12-31"] += 5
    other = freeze_models(altered, validation_design(), design())
    for key in (
        "selected_methods",
        "selection_scores",
        "models",
        "seasonal_fits",
        "calendar_cycle",
    ):
        assert frozen[key] == other[key]
    assert frozen["interval_radii"] != other["interval_radii"]


def test_serialized_forecasts_match_original_research_and_common_support():
    history = synthetic_sst()
    frozen = freeze_models(history, validation_design(), design())
    research = run_research_fold(history, fold(), design())
    metrics, forecasts, _ = score_holdout(history, frozen)
    assert set(forecasts.model) <= set(frozen["selected_methods"].values()) | {
        "persistence"
    }
    for h in [1, 7]:
        chosen = frozen["selected_methods"][str(h)]
        expected = (
            research["predictions"]
            .loc[lambda df: df.model.eq(chosen) & df.horizon_days.eq(h)]
            .set_index("date")
        )
        actual = forecasts.loc[
            lambda df: df.model.eq(chosen) & df.horizon_days.eq(h)
        ].set_index("date")
        np.testing.assert_allclose(
            actual.predicted_sst_celsius,
            expected.loc[actual.index].predicted_sst_celsius,
            atol=1e-12,
        )
        assert metrics.query("horizon_days == @h").n.nunique() == 1


def test_frozen_multiday_forecasts_cannot_read_intermediate_observations():
    history = synthetic_sst()
    frozen = freeze_models(history, validation_design(), design())
    target = pd.Timestamp("2016-05-08")
    first = frozen_means(history, frozen, 7)
    altered = history.copy()
    altered.loc["2016-05-02":"2016-05-08"] += 100
    second = frozen_means(altered, frozen, 7)
    for name in first:
        assert first[name].loc[target] == second[name].loc[target]


def test_insufficient_test_support_is_not_silently_reported():
    history = synthetic_sst()
    frozen = freeze_models(history, validation_design(), design())
    history.loc["2016-01-01":"2016-07-31"] = np.nan
    with pytest.raises(ValueError, match="too few"):
        score_holdout(history, frozen)


def test_holdout_uses_frozen_cells_even_when_new_ocean_cells_appear(monkeypatch):
    import xarray as xr
    from src.validation import aggregate_holdout

    dataset = xr.Dataset(
        {"sst": (("time", "lat", "lon"), np.array([[[10.0, 100.0]], [[12.0, 100.0]]]))},
        coords={
            "time": pd.date_range("2026-01-01", periods=2),
            "lat": [35.0],
            "lon": [120.0, 121.0],
        },
    )
    monkeypatch.setattr(xr, "open_mfdataset", lambda *a, **kw: dataset.copy())
    frozen = {
        "design": {"test_start": "2026-01-01", "test_end": "2026-01-02"},
        "spatial_mask": {
            "lat": [35.0],
            "lon": [120.0, 121.0],
            "selected_cells": [[35.0, 120.0]],
            "minimum_valid_weight_fraction": 0.8,
        },
    }
    result = aggregate_holdout([], frozen)
    np.testing.assert_allclose(result.sst_observed_celsius, [10.0, 12.0])
    frozen["spatial_mask"]["lon"] = [120.0, 122.0]
    with pytest.raises(ValueError, match="grid differs"):
        aggregate_holdout([], frozen)
