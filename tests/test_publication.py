import numpy as np
import pandas as pd
import pytest

from src.evaluation.publication_stats import (
    holm_adjust,
    interval_score,
    loss_components,
    paired_block_inference,
)
from src.models.spatial import fit_spatial_candidates


def spatial_sample():
    dates = pd.date_range("2010-01-01", "2017-12-31")
    rng = np.random.default_rng(21)
    state = np.zeros((len(dates), 3))
    for i in range(1, len(dates)):
        state[i] = np.array([0.92, 0.75, 0.5]) * state[i - 1] + rng.normal(0, 0.2, 3)
    pattern = rng.normal(size=(3, 8))
    seasonal = 15 + 7 * np.sin(2 * np.pi * np.arange(len(dates)) / 365.25)
    values = seasonal[:, None] + state @ pattern + rng.normal(0, 0.03, (len(dates), 8))
    config = {
        "train_end": "2013-12-31",
        "selection_end": "2014-12-31",
        "harmonics": 3,
        "spatial_ranks": [1, 3],
        "ar_orders": [1, 3],
        "trend_candidates": [False, True],
        "selection_horizon": 7,
    }
    return values, dates, np.linspace(0.8, 1, 8), config


def test_future_fields_cannot_change_cycles_modes_or_selection():
    values, dates, weights, config = spatial_sample()
    first, scores = fit_spatial_candidates(values, dates, weights, config)
    altered = values.copy()
    altered[dates > pd.Timestamp(config["selection_end"])] += 100
    second, other_scores = fit_spatial_candidates(altered, dates, weights, config)
    assert first.to_dict() == second.to_dict()
    pd.testing.assert_frame_equal(scores, other_scores)


def test_spatial_forecast_never_reads_intermediate_or_target_fields():
    values, dates, weights, config = spatial_sample()
    model, _ = fit_spatial_candidates(values, dates, weights, config)
    target = dates.get_loc("2016-05-08")
    first = model.predict(values, dates, 7)[target]
    altered = values.copy()
    altered[(dates >= "2016-05-02") & (dates <= "2016-05-08")] += 100
    np.testing.assert_array_equal(first, model.predict(altered, dates, 7)[target])
    np.testing.assert_allclose(
        model.basis.T @ model.basis, np.eye(model.rank), atol=1e-12
    )


def test_signed_discrepancy_interaction_can_cancel_all_external_loss():
    observed = np.array([11.0, 14.0, 8.0])
    analysis = np.array([10.0, 10.0, 10.0])
    row = loss_components(observed, analysis, observed, np.array([1.0, 2.0, 3.0]))
    assert row["product_discrepancy_mse"] > 0
    assert row["interaction"] == pytest.approx(-2 * row["product_discrepancy_mse"])
    assert row["external_mse"] == 0
    assert abs(row["identity_error"]) < 1e-12
    assert row["external_spatial_error_variance"] == 0


def test_holm_adjustment_is_order_invariant_and_accounts_for_family():
    np.testing.assert_allclose(holm_adjust([0.04, 0.01, 0.03]), [0.06, 0.03, 0.06])
    np.testing.assert_allclose(holm_adjust([0.9, 0.8, 1.0]), [1.0, 1.0, 1.0])


def test_null_paired_losses_retain_calendar_gaps_and_cannot_show_skill():
    dates = pd.date_range("2020-01-01", periods=180).delete([20, 21, 77, 120])
    losses = pd.Series(1 + np.sin(np.arange(len(dates))) ** 2, index=dates)
    row = paired_block_inference(losses, losses, 30, 199, 8)
    assert row["mean_loss_advantage"] == 0
    assert row["p_bootstrap_two_sided"] == 1
    assert row["skill_ci_lower"] == row["skill_ci_upper"] == 0
    with pytest.raises(ValueError, match="identical"):
        paired_block_inference(losses, losses.iloc[1:], 30, 199, 8)


def test_interval_score_penalizes_misses_and_unnecessarily_wide_intervals():
    scores = interval_score(
        np.array([0.0, 2.0, 0.0]), np.zeros(3), np.array([1.0, 1.0, 2.0])
    )
    np.testing.assert_allclose(scores, [2.0, 42.0, 4.0])
