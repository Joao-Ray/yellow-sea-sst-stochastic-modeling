import numpy as np
import pandas as pd
import pytest

from src.evaluation.confirmation_report import relative_skill
from src.insitu import equal_platform_daily, nearest_cells


def test_hourly_records_cannot_overweight_one_platform_or_cancel_squared_loss():
    dates = pd.to_datetime(["2023-01-01"] * 12 + ["2023-01-02"])
    records = pd.DataFrame(
        {
            "date": dates,
            "platform_type": [2] * 13,
            "platform_id": ["A"] * 10 + ["B"] * 2 + ["A"],
        }
    )
    errors = np.array([1.0] * 10 + [-3.0, 3.0, 2.0])
    result = equal_platform_daily(records, errors)
    assert result.n_records.tolist() == [12, 1]
    assert result.n_platforms.tolist() == [2, 1]
    assert result.mse.tolist() == [5.0, 4.0]
    assert result.bias.tolist() == [0.5, 2.0]
    assert np.sqrt(result.mse.mean()) == pytest.approx(np.sqrt(4.5))


def test_spherical_point_match_respects_latitude_scale_and_dateline():
    indices, distance = nearest_cells(
        np.array([36.0, 60.0, 0.0]),
        np.array([123.0, 1.0, 179.99]),
        np.array([36.0, 60.0, 0.0]),
        np.array([123.0, 0.9, -179.99]),
    )
    assert indices.tolist() == [0, 1, 2]
    np.testing.assert_allclose(distance, [0.0, 5.559754, 2.223902], atol=1e-4)


def test_skill_grouping_keeps_years_passes_and_horizons_separate():
    records = pd.DataFrame(
        {
            "year": [2023, 2023, 2024, 2024],
            "model": ["grid_anomaly_persistence", "eof_ar_increments"] * 2,
            "rmse": [1.0, 0.8, 2.0, 2.2],
        }
    )
    result = relative_skill(records, ["year"])
    np.testing.assert_allclose(
        result.skill_vs_grid_anomaly_persistence, [0, 0.2, 0, -0.1]
    )
    with pytest.raises(ValueError, match="duplicate"):
        relative_skill(pd.concat([records, records.iloc[[0]]]), ["year"])
    with pytest.raises(ValueError, match="missing"):
        relative_skill(records.iloc[[0, 1, 3]], ["year"])
