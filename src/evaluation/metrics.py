"""Small, explicit regression metrics used by forecast baselines."""

from __future__ import annotations

import numpy as np


def regression_metrics(
    observed: np.ndarray, predicted: np.ndarray
) -> dict[str, float | int]:
    """Return sample count, MAE, and RMSE after pairwise finite-value filtering."""
    observed_array = np.asarray(observed, dtype=float)
    predicted_array = np.asarray(predicted, dtype=float)
    if observed_array.shape != predicted_array.shape:
        raise ValueError("observed and predicted arrays must have the same shape")

    valid = np.isfinite(observed_array) & np.isfinite(predicted_array)
    if not valid.any():
        raise ValueError("no finite observed/predicted pairs are available")

    errors = predicted_array[valid] - observed_array[valid]
    return {
        "n": int(valid.sum()),
        "mae": float(np.mean(np.abs(errors))),
        "rmse": float(np.sqrt(np.mean(errors**2))),
    }
