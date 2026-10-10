import numpy as np
import pandas as pd
import pytest

from src.evaluation.bootstrap import skill_interval
from src.evaluation.diagnostics import calendar_residual_acf


def test_paired_skill_bootstrap_known_limits_and_reproducibility():
    observed = pd.Series(
        np.sin(np.arange(120)), index=pd.date_range("2000-01-01", periods=120)
    )
    predicted = observed + 0.5
    baseline = observed + 1
    result = skill_interval(observed, predicted, baseline, replicates=100)
    assert result["skill_ci_lower"] == pytest.approx(0.5)
    assert result["skill_ci_upper"] == pytest.approx(0.5)
    assert result == skill_interval(observed, predicted, baseline, replicates=100)


def test_bootstrap_preserves_calendar_gaps_and_undefined_zero_baseline():
    observed = pd.Series(
        np.ones(120), index=pd.date_range("2000-01-01", periods=120)
    ).drop(pd.Timestamp("2000-02-01"))
    assert (
        skill_interval(observed, observed, observed, replicates=100)["skill_ci_lower"]
        is None
    )
    result = skill_interval(observed, observed, observed + 1, replicates=100)
    assert result["skill_ci_lower"] == 1
    assert result["bootstrap_replicates_valid"] == 100


def test_residual_acf_pairs_use_calendar_days_with_gaps():
    residual = pd.Series(
        [1.0, 2.0, 4.0, 8.0],
        index=pd.to_datetime(["2000-01-01", "2000-01-02", "2000-01-04", "2000-01-05"]),
    )
    acf = calendar_residual_acf(residual, (1,))
    assert acf.loc[0, "n_pairs"] == 2
