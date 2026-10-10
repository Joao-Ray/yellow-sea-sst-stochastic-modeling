import numpy as np
import pandas as pd
import pytest

from src.models.ar1 import fit_ar1
from src.models.autoregression import fit_ar, select_ar_order


def signal():
    rng = np.random.default_rng(42)
    values = np.zeros(1000)
    for i in range(2, len(values)):
        values[i] = 0.2 + 0.6 * values[i - 1] - 0.2 * values[i - 2] + rng.normal(0, 0.2)
    return pd.Series(values, index=pd.date_range("2010-01-01", periods=len(values)))


def test_generic_ar1_matches_specialized_ar1_forecast_and_uncertainty():
    series = signal()
    general, specific = fit_ar(series, 1), fit_ar1(series)
    for horizon in (1, 7, 30):
        np.testing.assert_allclose(
            general.forecast(series, horizon),
            specific.forecast(series.shift(horizon), horizon),
            equal_nan=True,
        )
        assert general.interval_radius(horizon) == pytest.approx(
            specific.interval_radius(horizon)
        )


def test_recursive_ar2_forecast_uses_only_origin_history():
    series = signal()
    model = fit_ar(series.iloc[:500], 2)
    original = model.forecast(series, 7)
    altered = series.copy()
    altered.iloc[501:507] += 999
    changed = model.forecast(altered, 7)
    assert original.iloc[507] == pytest.approx(changed.iloc[507])


def test_ar_order_selection_never_uses_test_values():
    series = signal()
    train, validation = series.index[499], series.index[749]
    original, scores = select_ar_order(
        series, train_end=train, validation_end=validation, orders=(1, 2, 7), horizon=7
    )
    altered = series.copy()
    altered.iloc[750:] += 999
    selected, new_scores = select_ar_order(
        altered, train_end=train, validation_end=validation, orders=(1, 2, 7), horizon=7
    )
    assert original == selected
    assert scores == new_scores
    assert len({row["n"] for row in scores}) == 1


def test_ar_training_does_not_bridge_gap():
    series = signal()
    series.iloc[500] = np.nan
    model = fit_ar(series, 3)
    assert model.n_pairs == len(series) - 3 - 4
