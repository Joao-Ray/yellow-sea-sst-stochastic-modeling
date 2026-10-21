"""Scientific guards for retrospective physical-information/transfer controls."""

from datetime import date

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from src.data.download_processes import FIELDS, forcing_url, validate_forcing
from src.models.process_transfer import (
    feature_matrix,
    fit_increment,
    heat_into_ocean,
    select_source,
)
from src.process_transfer import destination_geometry
from src.process_alignment import increment_moments, aligned_prediction


def series():
    dates = pd.date_range("2010-01-01", "2014-12-31")
    t = np.arange(len(dates))
    sst = pd.Series(15 + 8 * np.sin(t / 58) + 0.1 * np.cos(t / 3), index=dates)
    forcing = pd.DataFrame(
        {v: np.sin(t / 11) + j + 1 for j, v in enumerate(FIELDS)}, index=dates
    )
    return sst, forcing


def test_explicit_flux_sign():
    # Incoming radiation 200+350; outgoing 30+400+100+20 => zero.
    f = dict(dswrf=200, dlwrf=350, uswrf=30, ulwrf=400, lhtfl=100, shtfl=20)
    assert heat_into_ocean(f) == 0
    assert heat_into_ocean({**f, "dswrf": 210}) == 10
    assert heat_into_ocean({**f, "lhtfl": 110}) == -10


@pytest.mark.parametrize("h", [1, 7, 30])
def test_origin_and_weather_cutoff(h):
    sst, forcing = series()
    origin = pd.Timestamp("2013-03-01")
    target = origin + pd.Timedelta(days=h)
    x, base = feature_matrix(sst, forcing, h, "sst_heat_wind")
    assert base.loc[target] == sst.loc[origin]
    assert x.loc[target, "sst_origin_minus_7"] == sst.loc[origin - pd.Timedelta(days=7)]
    sst2, f2 = sst.copy(), forcing.copy()
    sst2.loc[origin + pd.Timedelta(days=1) :] += 1000
    # Even weather on the origin day is prohibited by the one-day delay.
    f2.loc[origin:] += 2000
    altered, b2 = feature_matrix(sst2, f2, h, "sst_heat_wind")
    np.testing.assert_array_equal(x.loc[target], altered.loc[target])
    assert b2.loc[target] == base.loc[target]
    q = heat_into_ocean(forcing)
    assert (
        x.loc[target, "heat_into_ocean_past_mean_1"]
        == q.loc[origin - pd.Timedelta(days=1)]
    )


def test_no_future_label_training_or_scaling():
    sst, forcing = series()
    x, origin = feature_matrix(sst, forcing, 30, "sst_heat_wind")
    a = fit_increment(x, origin, sst, "ridge", 1, "2012-12-31")
    sst2, forcing2 = sst.copy(), forcing.copy()
    sst2.loc["2013-01-01":] *= 100
    forcing2.loc["2013-01-01":] *= 100
    x2, origin2 = feature_matrix(sst2, forcing2, 30, "sst_heat_wind")
    b = fit_increment(x2, origin2, sst2, "ridge", 1, "2012-12-31")
    for va, vb in [
        (a.mean, b.mean),
        (a.scale, b.scale),
        (a.fitted.coef_, b.fitted.coef_),
    ]:
        np.testing.assert_array_equal(va, vb)
    assert a.fitted.intercept_ == b.fitted.intercept_


def test_selection_ignores_post_selection_outcomes_and_transfer_does_not_refit():
    sst, forcing = series()
    cfg = dict(
        selection_horizon=7,
        forcing_delay_days=1,
        train_end="2012-12-31",
        random_seed=1,
        tree_estimators=10,
        selection_start="2013-01-01",
        selection_end="2013-12-31",
    )
    chosen, rows = select_source(sst, forcing, "ridge", "sst_heat", [0.1, 1], cfg)
    altered = sst.copy()
    altered.loc["2014-01-01":] += 100
    chosen2, rows2 = select_source(altered, forcing, "ridge", "sst_heat", [0.1, 1], cfg)
    assert chosen == chosen2 and rows == rows2
    x, origin = feature_matrix(sst, forcing, 7, "sst_heat")
    model = fit_increment(x, origin, sst, "ridge", chosen, cfg["train_end"])
    coefficients, mean = model.fitted.coef_.copy(), model.mean.copy()
    xd, od = feature_matrix(sst + 5, forcing * 2, 7, "sst_heat")
    assert model.predict(xd, od).notna().sum() > 1000
    np.testing.assert_array_equal(model.fitted.coef_, coefficients)
    np.testing.assert_array_equal(model.mean, mean)


def dataset():
    d = xr.Dataset(
        {"dswrf": (("time", "lat", "lon"), np.ones((3, 2, 2)))},
        coords={
            "time": pd.date_range("2010-01-01", periods=3),
            "lat": [30, 32],
            "lon": [120, 122],
        },
        attrs={"dataset_title": "NCEP-NCAR Reanalysis 1"},
    )
    d.dswrf.attrs["units"] = "W/m^2"
    return d


def test_forcing_product_units_calendar_and_missing_data_fail_closed():
    d = dataset()
    assert (
        validate_forcing(d, "dswrf", date(2010, 1, 1), date(2010, 1, 3)).sizes["time"]
        == 3
    )
    for bad in [d.assign_attrs(dataset_title="NCEP Reanalysis 2"), d.isel(time=[0, 2])]:
        with pytest.raises(ValueError):
            validate_forcing(bad, "dswrf", date(2010, 1, 1), date(2010, 1, 3))
    d.dswrf.attrs["units"] = "J/m^2"
    with pytest.raises(ValueError, match="units"):
        validate_forcing(d, "dswrf", date(2010, 1, 1), date(2010, 1, 3))
    d = dataset()
    d.dswrf.values[0, 0, 0] = np.nan
    with pytest.raises(ValueError, match="finite"):
        validate_forcing(d, "dswrf", date(2010, 1, 1), date(2010, 1, 3))


def test_destination_identity_and_forcing_url():
    with pytest.raises(ValueError):
        destination_geometry(
            {
                "type": "FeatureCollection",
                "features": [{"properties": {"mrgid": 4303, "name": "Yellow Sea"}}],
            }
        )
    with pytest.raises(ValueError):
        forcing_url("invented", date(2010, 1, 1), date(2010, 1, 3), {})
    with pytest.raises(ValueError):
        forcing_url("dswrf", date(2010, 1, 1), date(2011, 1, 3), {})


def test_alignment_moments_exclude_future_targets():
    sst, forcing = series()
    x, origin = feature_matrix(sst, forcing, 30, "sst")
    first = increment_moments(x, origin, sst, "2012-12-31")
    changed = sst.copy()
    changed.loc["2013-01-01":] += 1000
    second = increment_moments(x, origin, changed, "2012-12-31")
    assert first == second


def test_alignment_uses_local_scaler_but_not_local_regression_coefficients():
    sst, forcing = series()
    xs, os = feature_matrix(sst, forcing, 7, "sst")
    destination = sst * 1.5 + 4
    xd, od = feature_matrix(destination, forcing, 7, "sst")
    source = fit_increment(xs, os, sst, "ridge", 1, "2012-12-31")
    local = fit_increment(xd, od, destination, "ridge", 1, "2012-12-31")
    sm = increment_moments(xs, os, sst, "2012-12-31")
    dm = increment_moments(xd, od, destination, "2012-12-31")
    original_coefficients = source.fitted.coef_.copy()
    first = aligned_prediction(source, local, xd, od, sm, dm)
    local.fitted.coef_[:] = 1e12
    second = aligned_prediction(source, local, xd, od, sm, dm)
    np.testing.assert_array_equal(first, second)
    np.testing.assert_array_equal(source.fitted.coef_, original_coefficients)
    # An affine copy of the source series recovers the corresponding affine
    # forecast when both input and increment moments are calibrated in training.
    source_forecast = source.predict(xs, os)
    np.testing.assert_allclose(
        first, source_forecast * 1.5 + 4, atol=1e-10, equal_nan=True
    )
