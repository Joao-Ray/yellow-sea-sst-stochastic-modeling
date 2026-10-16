"""Information-set and coordinate-system guards for anomaly transfer."""

import numpy as np
import pandas as pd
import pytest

from src.anomaly_transfer import choose_source
from src.anomaly_benchmarks import fit_decay
from src.models.anomaly_transfer import fit_climate, design, decode
from src.models.process_transfer import fit_increment


def sample():
    dates = pd.date_range("2010-01-01", "2014-12-31")
    t = np.arange(len(dates))
    s = pd.Series(
        14 + 8 * np.sin(t / 58) + 0.25 * np.sin(t / 4) + 0.12 * np.cos(t / 19),
        index=dates,
    )
    f = pd.DataFrame(
        {
            v: 10 + j + np.sin(t / (9 + j))
            for j, v in enumerate(
                ["dswrf", "uswrf", "dlwrf", "ulwrf", "lhtfl", "shtfl", "uwnd", "vwnd"]
            )
        },
        index=dates,
    )
    return s, f


def test_training_climatology_and_scales_ignore_future_values():
    s, f = sample()
    a = fit_climate(s, f, "2012-12-31")
    changed = s.copy()
    weather = f.copy()
    changed.loc["2013-01-01":] += 1000
    weather.loc["2013-01-01":] *= 20
    b = fit_climate(changed, weather, "2012-12-31")
    assert a.to_dict() == b.to_dict()


@pytest.mark.parametrize("h", [1, 7, 30])
def test_anomaly_inputs_respect_origin_and_weather_delay(h):
    s, f = sample()
    climate = fit_climate(s, f, "2012-12-31")
    origin = pd.Timestamp("2013-03-01")
    target = origin + pd.Timedelta(days=h)
    x, o, _ = design(s, f, climate, "seasonal_anomaly", h, "sst_heat_wind")
    changed = s.copy()
    weather = f.copy()
    changed.loc[origin + pd.Timedelta(days=1) :] += 1000
    weather.loc[origin:] += 1000
    xx, oo, _ = design(
        changed, weather, climate, "seasonal_anomaly", h, "sst_heat_wind"
    )
    np.testing.assert_array_equal(x.loc[target], xx.loc[target])
    assert o.loc[target] == oo.loc[target]


def test_zero_anomaly_increment_is_the_same_local_persistence_benchmark():
    s, f = sample()
    c = fit_climate(s, f, "2012-12-31")
    for h in [1, 7, 30]:
        state = c.state(s)
        prediction = decode(state.shift(h), c, "seasonal_anomaly")
        cycle = c.sst_cycle.predict(s.index)
        expected = s.shift(h) + cycle - cycle.shift(h)
        np.testing.assert_allclose(prediction, expected, atol=1e-12, equal_nan=True)


def test_affine_climates_transfer_with_unchanged_source_increment_model():
    s, f = sample()
    destination = 1.5 * s + 4
    source_climate = fit_climate(s, f, "2012-12-31")
    destination_climate = fit_climate(destination, f, "2012-12-31")
    xs, os, ys = design(s, f, source_climate, "seasonal_anomaly", 7, "sst")
    xd, od, _ = design(
        destination, f, destination_climate, "seasonal_anomaly", 7, "sst"
    )
    model = fit_increment(xs, os, ys, "ridge", 10, "2012-12-31")
    original = model.fitted.coef_.copy()
    scaler = model.mean.copy()
    source = decode(model.predict(xs, os), source_climate, "seasonal_anomaly")
    transferred = decode(model.predict(xd, od), destination_climate, "seasonal_anomaly")
    np.testing.assert_allclose(transferred, 1.5 * source + 4, atol=1e-9, equal_nan=True)
    np.testing.assert_array_equal(original, model.fitted.coef_)
    np.testing.assert_array_equal(scaler, model.mean)


def test_source_selection_does_not_use_post_selection_outcomes():
    s, f = sample()
    c = fit_climate(s, f, "2012-12-31")
    cfg = dict(
        train_end="2012-12-31",
        selection_start="2013-01-01",
        selection_end="2013-12-31",
        random_seed=1,
        tree_estimators=10,
    )
    x, o, y = design(s, f, c, "seasonal_anomaly", 7, "sst_heat")
    chosen, rows = choose_source(
        x, o, y, s, c, "seasonal_anomaly", "ridge", [0.1, 1, 10, 100], cfg
    )
    changed = s.copy()
    weather = f.copy()
    changed.loc["2014-01-01":] += 1000
    weather.loc["2014-01-01":] *= 100
    xx, oo, yy = design(changed, weather, c, "seasonal_anomaly", 7, "sst_heat")
    other, rows2 = choose_source(
        xx, oo, yy, changed, c, "seasonal_anomaly", "ridge", [0.1, 1, 10, 100], cfg
    )
    assert chosen == other
    assert rows == rows2


def test_simple_decay_ignores_future_values_and_is_scale_invariant():
    s, f = sample()
    c = fit_climate(s, f, "2012-12-31")
    state = c.state(s)
    first, n = fit_decay(state, "2012-12-31")
    altered = state.copy()
    altered.loc["2013-01-01":] *= 1000
    assert fit_decay(altered, "2012-12-31") == (first, n)
    scaled, _ = fit_decay(state * 100, "2012-12-31")
    assert abs(first - scaled) < 1e-12


def test_unstable_simple_decay_is_rejected_instead_of_clipped():
    index = pd.date_range("2010-01-01", periods=1000)
    state = pd.Series(1.01 ** np.arange(1000), index=index)
    with pytest.raises(ValueError, match="unstable"):
        fit_decay(state, "2012-12-31")
