"""Hand-calculated checks for the retrospective platform-support sensitivity."""

import numpy as np
import pandas as pd
import pytest

from src.buoy_robustness import (
    add_skills,
    deletion_scores,
    platform_day_losses,
    score_platform_days,
    support_weights,
)


def sample():
    return pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2023-01-01"] * 3 + ["2023-01-02"] * 2 + ["2023-01-03"]
            ),
            "platform_type": [2, 2, 4, 2, 4, 4],
            "platform_id": ["A", "A", "B", "A", "C", "B"],
        }
    )


def test_record_repetition_does_not_change_platform_day_weight():
    q = platform_day_losses(sample(), np.array([0, 2, 4, 2, 0, 6], float))
    scores = score_platform_days(q)
    assert scores["mse"] == pytest.approx(47 / 3)
    assert scores["mae"] == pytest.approx(19 / 6)
    assert scores["bias"] == pytest.approx(19 / 6)
    assert scores["n_records"] == 6
    assert scores["n_platform_days"] == 5
    # A different estimand: equal platforms over the whole period.
    assert scores["platform_equal_mse"] == pytest.approx(29 / 3)


def test_composite_type_and_id_are_distinct_platforms():
    p = sample().iloc[:3].copy()
    p["platform_id"] = "shared"
    q = platform_day_losses(p, np.array([0, 2, 4], float))
    assert len(q) == 2
    assert score_platform_days(q)["mse"] == 9


def test_support_weights_include_single_platform_dates():
    q = platform_day_losses(sample(), np.zeros(6))
    weights = support_weights(q).set_index("platform_id")
    assert weights.loc["A", "score_weight"] == pytest.approx(1 / 3)
    assert weights.loc["B", "score_weight"] == pytest.approx(1 / 2)
    assert weights.loc["C", "score_weight"] == pytest.approx(1 / 6)
    assert weights.loc["B", "sole_platform_days"] == 1
    assert weights.score_weight.sum() == pytest.approx(1)


def test_deletion_renormalizes_and_records_matching_date_reference():
    q = platform_day_losses(sample(), np.array([0, 2, 4, 2, 0, 6], float))
    rows = deletion_scores(q)
    b = rows.loc[(rows.unit_kind == "platform") & (rows.removed_id == "B")].iloc[0]
    assert b.n_days == 2
    assert b.n_days_lost == 1
    assert b.mse == 2
    assert b.full_on_retained_dates_mse == 5.5
    types = rows.loc[
        (rows.unit_kind == "platform_type") & (rows.removed_type == 4)
    ].iloc[0]
    assert types.n_days == 2
    assert types.mse == 3
    assert types.full_on_retained_dates_mse == 5.5


def test_deleting_only_platform_is_explicitly_unscorable():
    q = platform_day_losses(sample().iloc[:2], np.array([0, 2], float))
    rows = deletion_scores(q)
    assert rows.n_days.eq(0).all()
    assert rows.status.eq("unscorable").all()
    assert rows.mse.isna().all()


def test_skill_pairs_same_deletion_and_retained_date_reference():
    # The two removal cases have deliberately opposite model rankings.
    rows = []
    for removed_id, model_rmse, baseline_rmse in [("A", 1, 2), ("B", 3, 1)]:
        for model, rmse, retained_mse in [
            ("test", model_rmse, 4),
            ("grid_anomaly_persistence", baseline_rmse, 9),
        ]:
            rows.append(
                dict(
                    region="source",
                    **{"pass": "nighttime"},
                    target="iQuam",
                    horizon_days=30,
                    unit_kind="platform",
                    removed_type=2,
                    removed_id=removed_id,
                    model=model,
                    rmse=rmse,
                    platform_equal_rmse=rmse,
                    full_on_retained_dates_mse=retained_mse,
                )
            )
    q = add_skills(pd.DataFrame(rows), deletion=True)
    q = q.loc[q.model.eq("test")].set_index("removed_id")
    assert q.loc["A", "skill"] == 0.5
    assert q.loc["B", "skill"] == -2
    assert q.loc["A", "full_on_retained_dates_skill"] == pytest.approx(1 / 3)


@pytest.mark.parametrize("errors", [[0, np.nan, 1, 2, 3, 4], [0, np.inf, 1, 2, 3, 4]])
def test_nonfinite_errors_fail_closed(errors):
    with pytest.raises(ValueError, match="finite"):
        platform_day_losses(sample(), np.array(errors))
