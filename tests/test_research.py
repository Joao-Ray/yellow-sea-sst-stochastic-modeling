import copy
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Polygon
import xarray as xr

from src.data.marine_boundary import grid_mask, validate_boundary
from src.evaluation.calibration import empirical_radius
from src.evaluation.research_experiment import run_research_fold
from src.models.ridge import fit_ridge
from src.models.seasonal import fit_seasonal


def synthetic_sst():
    index = pd.date_range("2010-01-01", "2018-12-31")
    rng = np.random.default_rng(27)
    noise = np.zeros(len(index))
    for i in range(1, len(index)):
        noise[i] = 0.8 * noise[i - 1] + rng.normal(scale=0.2)
    values = (
        15
        + 8 * np.cos(2 * np.pi * index.dayofyear / 365.25)
        + np.arange(len(index)) * 0.1 / 365.25
        + noise
    )
    return pd.Series(values, index=index)


def design():
    return {
        "harmonics": 3,
        "ar_candidates": [1, 3],
        "selection_horizon": 7,
        "ridge_order": 3,
        "ridge_alphas": [0.01, 0.1],
        "horizons": [1, 7],
        "interval_level": 0.95,
    }


def fold():
    return {
        "name": "synthetic",
        "train_end": "2013-12-31",
        "selection_end": "2014-12-31",
        "calibration_end": "2015-12-31",
        "test_end": "2018-12-31",
    }


def test_polygon_mask_excludes_holes_and_covers_boundary():
    geometry = Polygon(
        [(0, 0), (4, 0), (4, 4), (0, 4)], holes=[[(1, 1), (3, 1), (3, 3), (1, 3)]]
    )
    mask = grid_mask(
        geometry,
        xr.DataArray([0, 2, 5], dims="lat"),
        xr.DataArray([0, 2, 5], dims="lon"),
    )
    np.testing.assert_array_equal(
        mask.values, [[True, True, False], [True, False, False], [False, False, False]]
    )


def test_wrong_marine_identity_and_crs_are_rejected():
    document = {
        "type": "FeatureCollection",
        "features": [{"properties": {"mrgid": 1, "name": "Other"}}],
    }
    with pytest.raises(ValueError, match="identity"):
        validate_boundary(document)
    document["features"][0]["properties"] = {"mrgid": 4303, "name": "Yellow Sea"}
    with pytest.raises(ValueError, match="WGS84"):
        validate_boundary(document)


def test_harmonic_trend_recovers_training_signal_and_extrapolates():
    index = pd.date_range("2010-01-01", "2015-12-31")
    from src.models.seasonal import seasonal_design

    coefficients = np.array([15, 8, 0.3, 0.12])
    values = seasonal_design(index, index[0], 1, True) @ coefficients
    fit = fit_seasonal(pd.Series(values, index=index), harmonics=1, trend=True)
    np.testing.assert_allclose(fit.coefficients, coefficients, atol=1e-10)
    np.testing.assert_allclose(fit.predict(index), values, atol=1e-10)
    assert fit.to_dict()["trend_celsius_per_year"] == pytest.approx(0.12)


def test_ridge_shrinks_training_lags_without_interpolating_gaps():
    values = synthetic_sst()
    low = fit_ridge(values, 3, 0.001)
    high = fit_ridge(values, 3, 1)
    assert np.linalg.norm(high.coefficients) < np.linalg.norm(low.coefficients)
    missing = values.copy()
    missing.iloc[100] = np.nan
    assert fit_ridge(missing, 3, 0.1).n_pairs == low.n_pairs - 4
    with pytest.raises(ValueError, match="positive"):
        fit_ridge(values, 3, 0)


def test_empirical_radius_uses_conservative_rank_and_requires_enough_pairs():
    observed = pd.Series(np.arange(100, dtype=float))
    predicted = observed * 0
    result = empirical_radius(observed, predicted)
    assert result["order_statistic_rank"] == 96
    assert result["radius_celsius"] == 95
    with pytest.raises(ValueError, match="100"):
        empirical_radius(observed.iloc[:99], predicted.iloc[:99])


def test_future_test_values_cannot_change_training_selection_or_calibration():
    series = synthetic_sst()
    first = run_research_fold(series, fold(), design())
    altered = series.copy()
    altered.loc["2016-01-01":] += 100
    second = run_research_fold(altered, fold(), design())
    assert first["models"] == second["models"]
    assert first["seasonal_fits"] == second["seasonal_fits"]
    assert first["interval_radii"] == second["interval_radii"]


def test_calibration_observations_cannot_change_model_selection():
    series = synthetic_sst()
    first = run_research_fold(series, fold(), design())
    altered = series.copy()
    altered.loc["2015-01-01":"2015-12-31"] += 10
    second = run_research_fold(altered, fold(), design())
    assert first["models"] == second["models"]
    assert first["seasonal_fits"] == second["seasonal_fits"]
    assert first["interval_radii"] != second["interval_radii"]


def test_multiday_forecasts_do_not_use_intermediate_future_observations():
    series = synthetic_sst()
    first = run_research_fold(series, fold(), design())
    altered = series.copy()
    altered.loc["2017-02-02":"2017-02-07"] += 20
    second = run_research_fold(altered, fold(), design())

    def target(result):
        frame = result["predictions"]
        mask = frame.date.eq(pd.Timestamp("2017-02-08")) & frame.horizon_days.eq(7)
        return frame.loc[mask].set_index("model").predicted_sst_celsius

    pd.testing.assert_series_equal(target(first), target(second))
    counts = first["metrics"].groupby("horizon_days").n.nunique()
    assert counts.eq(1).all()


def test_research_split_order_is_validated():
    wrong = copy.deepcopy(fold())
    wrong["selection_end"] = wrong["calibration_end"]
    with pytest.raises(ValueError, match="ordered"):
        run_research_fold(synthetic_sst(), wrong, design())


def test_spatial_mask_is_fixed_before_future_ocean_availability(tmp_path, monkeypatch):
    from shapely.geometry import box
    from src.data import research_series

    monkeypatch.setattr(research_series, "_plot_domains", lambda *args: None)
    dates = pd.date_range("2010-01-01", periods=3)
    values = np.full((3, 3, 3), 10.0)
    values[0, 1, 1] = np.nan
    values[1:, 1, 1] = 100.0
    dataset = xr.Dataset(
        {"sst": (("time", "lat", "lon"), values)},
        coords={"time": dates, "lat": [32, 35, 40], "lon": [118, 121, 126]},
    )
    path = tmp_path / "fixture.nc"
    dataset.to_netcdf(path, engine="netcdf4")
    config = {
        "acquisition_region": {
            "lat_min": 31,
            "lat_max": 42,
            "lon_min": 117,
            "lon_max": 128,
        },
        "domains": ["iho_yellow_sea", "original_pilot_box", "iho_interior"],
        "interior_buffer_degrees": 0.125,
        "date_start": "2010-01-01",
        "date_end": "2010-01-03",
    }
    series, quality = research_series.build_research_series(
        [path], box(119, 33, 127, 41), config, tmp_path
    )
    np.testing.assert_allclose(series["iho_yellow_sea"], 10)
    assert quality["domains"][0]["ocean_grid_cells"] == 3
    assert quality["domains"][0]["min_valid_fraction"] == 1
