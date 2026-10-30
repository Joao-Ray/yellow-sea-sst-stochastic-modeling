import numpy as np
import pandas as pd
import pytest

from src.evaluation.experiment import observed_sst, run_experiment


@pytest.fixture
def table():
    index = pd.date_range("2010-01-01", "2012-12-31")
    rng = np.random.default_rng(42)
    anomaly = np.zeros(len(index))
    for i in range(1, len(index)):
        anomaly[i] = 0.9 * anomaly[i - 1] + rng.normal(0, 0.2)
    return pd.DataFrame(
        {
            "sst_celsius": 15
            + 8 * np.sin(index.dayofyear.to_numpy() / 366 * 2 * np.pi)
            + anomaly
        },
        index=index,
    )


def run(table):
    return run_experiment(
        table,
        train_end="2010-12-31",
        validation_end="2011-12-31",
        horizons=(1, 7),
        climatology="month",
    )


def test_future_values_cannot_change_training_or_validation_predictions(table):
    original = run(table)
    altered = table.copy()
    altered.loc["2012-01-01":, "sst_celsius"] += 1000
    altered["anomaly_celsius"] = 99999  # input anomalies must never be reused
    future_changed = run(altered)
    assert original.parameters == future_changed.parameters
    pd.testing.assert_series_equal(
        original.anomalies.climatology_celsius,
        future_changed.anomalies.climatology_celsius,
    )
    pd.testing.assert_frame_equal(
        original.predictions.query("split == 'validation'"),
        future_changed.predictions.query("split == 'validation'"),
    )


def test_multiday_prediction_uses_only_its_origin(table):
    before = run(table)
    changed = table.copy()
    changed.loc["2012-01-02":"2012-01-06", "sst_celsius"] += 1000
    after = run(changed)
    target = pd.Timestamp("2012-01-07")
    left = before.predictions.loc[
        before.predictions.date.eq(target) & before.predictions.horizon_days.eq(7)
    ]
    right = after.predictions.loc[
        after.predictions.date.eq(target) & after.predictions.horizon_days.eq(7)
    ]
    pd.testing.assert_frame_equal(left, right)


def test_missing_and_interpolated_values_have_equal_model_support(table):
    table["is_interpolated"] = False
    table.loc["2012-01-10", "is_interpolated"] = True
    table.loc["2012-01-20", "sst_celsius"] = np.nan
    result = run(table)
    assert np.isnan(result.anomalies.loc["2012-01-10", "sst_observed_celsius"])
    for horizon in (1, 7):
        frames = result.predictions.query(
            "split == 'test' and horizon_days == @horizon"
        )
        supports = [tuple(group.date) for _, group in frames.groupby("model")]
        assert supports[0] == supports[1] == supports[2]
        assert pd.Timestamp("2012-01-10") not in supports[0]
        assert (
            pd.Timestamp("2012-01-10") + pd.Timedelta(days=horizon) not in supports[0]
        )


def test_raw_column_and_csv_boolean_flags_are_honored(table):
    table["sst_observed_celsius"] = table.sst_celsius
    table["is_interpolated"] = "False"
    table.loc["2012-01-10", "sst_observed_celsius"] = np.nan
    table.loc["2012-01-10", "is_interpolated"] = "True"
    assert np.isnan(observed_sst(table).loc["2012-01-10"])


def test_split_rejects_empty_test(table):
    with pytest.raises(ValueError, match="split dates"):
        run_experiment(table, train_end="2010-12-31", validation_end="2012-12-31")


def test_selected_ar_parameters_and_selection_scores_ignore_test_changes(table):
    arguments = dict(
        train_end="2010-12-31",
        validation_end="2011-12-31",
        horizons=(1, 7),
        climatology="month",
        ar_candidates=(1, 3, 7),
        selection_horizon=7,
    )
    before = run_experiment(table, **arguments)
    changed = table.copy()
    changed.loc["2012-01-01":, "sst_celsius"] += 999
    after = run_experiment(changed, **arguments)
    assert before.parameters == after.parameters
    assert (
        before.protocol["ar_selection_scores"] == after.protocol["ar_selection_scores"]
    )
    for (_, _), group in before.predictions.groupby(["split", "horizon_days"]):
        assert group.groupby("model").size().nunique() == 1
