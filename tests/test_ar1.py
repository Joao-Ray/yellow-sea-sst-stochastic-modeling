import numpy as np
import pandas as pd
import pytest

from src.models.ar1 import AR1, fit_ar1


def test_ar1_recovers_known_transition_and_multiday_forecast():
    x = [3.0]
    for _ in range(60):
        x.append(0.1 + 0.8 * x[-1])
    series = pd.Series(x, index=pd.date_range("2000-01-01", periods=len(x)))
    model = fit_ar1(series)
    assert model.phi == pytest.approx(0.8)
    assert model.intercept == pytest.approx(0.1)
    assert model.forecast(pd.Series([2.0]), 7).iloc[0] == pytest.approx(
        0.5 + 0.8**7 * 1.5
    )


def test_ar1_never_bridges_missing_calendar_days():
    values = np.random.default_rng(42).normal(size=100)
    values[50] = np.nan
    series = pd.Series(values, index=pd.date_range("2000-01-01", periods=100))
    assert fit_ar1(series).n_pairs == 97
    assert fit_ar1(series.dropna()).n_pairs == 97


def test_ou_exact_transition_matches_ar1_mean_and_variance():
    model = AR1(0.1, 0.9, 0.04, 100)
    ou = model.ou_parameters()
    h, origin = 7, 2.0
    decay = np.exp(-ou["theta_per_day"] * h)
    mean = ou["mu_celsius"] + decay * (origin - ou["mu_celsius"])
    variance = (
        ou["sigma_celsius_per_sqrt_day"] ** 2
        / (2 * ou["theta_per_day"])
        * (1 - decay**2)
    )
    assert model.forecast(pd.Series([origin]), h).iloc[0] == pytest.approx(mean)
    assert model.interval_radius(h) / 1.9599639845400538 == pytest.approx(
        np.sqrt(variance)
    )


@pytest.mark.parametrize("phi", [-0.2, 0.0, 1.0, 1.1])
def test_non_ou_ar1_does_not_produce_ou_parameters(phi):
    assert AR1(0, phi, 1, 30).ou_parameters() is None


def test_ar1_rejects_constant_series():
    with pytest.raises(ValueError, match="constant"):
        fit_ar1(pd.Series(np.ones(60), index=pd.date_range("2000-01-01", periods=60)))
