"""Held-out empirical error radii; no iid conformal guarantee is claimed."""

import numpy as np
import pandas as pd


def empirical_radius(
    observed: pd.Series, predicted: pd.Series, level: float = 0.95
) -> dict:
    if not observed.index.equals(predicted.index) or not 0 < level < 1:
        raise ValueError("matching dates and interval level in (0,1) required")
    error = np.abs((observed - predicted).to_numpy(dtype=float))
    error = error[np.isfinite(error)]
    if len(error) < 100:
        raise ValueError("at least 100 complete calibration errors required")
    # Conservative finite-sample order statistic, but serial dependence means
    # the usual exchangeability-based coverage guarantee does not apply here.
    rank = min(len(error), int(np.ceil((len(error) + 1) * level)))
    return {
        "radius_celsius": float(np.partition(error, rank - 1)[rank - 1]),
        "n_calibration": len(error),
        "level": level,
        "order_statistic_rank": rank,
        "scope": "held-out empirical absolute-error radius; dependent data, no guaranteed coverage",
    }
