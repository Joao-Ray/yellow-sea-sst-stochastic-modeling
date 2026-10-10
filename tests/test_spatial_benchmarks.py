import numpy as np
import pandas as pd

from src.models.spatial_benchmarks import fit_trees, fit_var, shift


def modal_sample():
    rng = np.random.default_rng(6)
    scores = np.zeros((2200, 2))
    transition = np.array([[0.65, 0.25], [-0.15, 0.8]])
    for j in range(1, len(scores)):
        scores[j] = transition @ scores[j - 1] + rng.normal(0, 0.15, 2)
    return scores, pd.date_range("2010-01-01", periods=len(scores)), transition


def test_coupled_var_recovers_cross_mode_dependence():
    scores, _, transition = modal_sample()
    model = fit_var(scores, 1, 0.0001)
    np.testing.assert_allclose(model.coefficients.T, transition, atol=0.04)
    assert model.spectral_radius < 1


def test_var_cannot_read_intermediate_or_target_states():
    scores, _, _ = modal_sample()
    model = fit_var(scores[:1000], 3, 0.01)
    altered = scores.copy()
    altered[1494:1501] += 100
    np.testing.assert_array_equal(
        model.predict(scores, 7)[1500], model.predict(altered, 7)[1500]
    )
    altered[1493] += 10
    assert not np.allclose(
        model.predict(scores, 7)[1500], model.predict(altered, 7)[1500]
    )


def test_nonlinear_training_and_forecast_are_origin_restricted():
    scores, dates, _ = modal_sample()
    model = fit_trees(scores, dates, "2013-12-31", 7, [0, 1, 6, 13], 5, 1.0, 12, 9)
    altered = scores.copy()
    altered[dates > "2013-12-31"] += 100
    other = fit_trees(altered, dates, "2013-12-31", 7, [0, 1, 6, 13], 5, 1.0, 12, 9)
    assert model.to_dict() == other.to_dict()
    np.testing.assert_array_equal(
        model.estimator.predict(np.ones((1, 15))),
        other.estimator.predict(np.ones((1, 15))),
    )
    altered = scores.copy()
    altered[1494:1501] += 100
    np.testing.assert_array_equal(
        model.predict(scores, dates)[1500], model.predict(altered, dates)[1500]
    )


def test_direct_training_excludes_targets_beyond_training_boundary():
    scores, dates, _ = modal_sample()
    model = fit_trees(scores, dates, "2013-12-31", 30, [0, 1, 6, 13], 20, 0.5, 5, 8)
    train_days = int((dates <= pd.Timestamp("2013-12-31")).sum())
    assert model.n_training == train_days - 30 - 13
    np.testing.assert_array_equal(shift(scores, 0), scores)
