import numpy as np
import pandas as pd
import pytest

from src.evaluation.metrics import regression_metrics
from src.models.persistence import evaluate_persistence, persistence_predictions


def test_persistence_uses_previous_calendar_day() -> None:
    anomaly = pd.Series(
        [0.5, 1.0, -0.5], index=pd.date_range("2020-01-01", periods=3)
    )
    prediction = persistence_predictions(anomaly)
    assert np.isnan(prediction.iloc[0])
    assert prediction.iloc[1:].tolist() == [0.5, 1.0]


def test_metrics_filter_nonfinite_pairs() -> None:
    metrics = regression_metrics(
        np.array([1.0, 2.0, np.nan]), np.array([2.0, 2.0, 9.0])
    )
    assert metrics == {"n": 2, "mae": 0.5, "rmse": pytest.approx(2**-0.5)}


def test_persistence_evaluation_uses_final_chronological_segment() -> None:
    anomaly = pd.Series(
        [0.0, 1.0, 2.0, 4.0, 7.0],
        index=pd.date_range("2020-01-01", periods=5),
    )
    predictions, metadata = evaluate_persistence(anomaly, test_fraction=0.4)
    assert predictions.index.min() == pd.Timestamp("2020-01-04")
    assert predictions["predicted_anomaly_celsius"].tolist() == [2.0, 4.0]
    assert metadata["split_method"] == "final chronological fraction"
    assert metadata["random_seed"] == 42
