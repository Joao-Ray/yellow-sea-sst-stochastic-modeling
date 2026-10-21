"""Training-standardized ridge autoregression, selected before calibration/test."""

import numpy as np
import pandas as pd
from src.models.autoregression import Autoregression
from src.evaluation.metrics import regression_metrics


def fit_ridge(anomaly: pd.Series, order: int, alpha: float) -> Autoregression:
    if (
        not isinstance(order, int)
        or isinstance(order, bool)
        or order < 1
        or not np.isfinite(alpha)
        or alpha <= 0
    ):
        raise ValueError("positive integer order and finite positive alpha required")
    if not isinstance(anomaly.index, pd.DatetimeIndex) or anomaly.index.has_duplicates:
        raise ValueError("ridge input needs unique calendar dates")
    daily = anomaly.sort_index().asfreq("D")
    frame = (
        pd.concat([daily] + [daily.shift(k) for k in range(1, order + 1)], axis=1)
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )
    if len(frame) < max(60, 3 * (order + 1)):
        raise ValueError("insufficient complete calendar lag vectors for ridge")
    target, lags = frame.iloc[:, 0].to_numpy(), frame.iloc[:, 1:].to_numpy()
    center, scale = lags.mean(axis=0), lags.std(axis=0)
    if (scale <= np.finfo(float).eps).any():
        raise ValueError("ridge training lags have zero variance")
    standardized = (lags - center) / scale
    penalty = len(frame) * alpha
    coefficients_z = np.linalg.solve(
        standardized.T @ standardized + penalty * np.eye(order),
        standardized.T @ (target - target.mean()),
    )
    coefficients = coefficients_z / scale
    intercept = target.mean() - center @ coefficients
    errors = target - intercept - lags @ coefficients
    singular = np.linalg.svd(standardized, compute_uv=False)
    effective_df = 1 + np.sum(singular**2 / (singular**2 + penalty))
    variance = errors @ errors / (len(frame) - effective_df)
    return Autoregression(
        float(intercept),
        tuple(float(x) for x in coefficients),
        float(variance),
        len(frame),
    )


def select_ridge(
    anomaly: pd.Series,
    train_end: pd.Timestamp,
    selection_end: pd.Timestamp,
    order: int,
    alphas: list[float],
    horizon: int,
):
    if not alphas or len(set(alphas)) != len(alphas):
        raise ValueError("ridge alphas must be non-empty and unique")
    models = {
        alpha: fit_ridge(anomaly.loc[:train_end], order, alpha)
        for alpha in sorted(alphas)
    }
    forecasts = {
        alpha: model.forecast(anomaly, horizon) for alpha, model in models.items()
    }
    common = (
        anomaly.notna() & (anomaly.index > train_end) & (anomaly.index <= selection_end)
    )
    for predicted in forecasts.values():
        common &= np.isfinite(predicted)
    if not common.any():
        raise ValueError("no common ridge selection targets")
    scores = [
        {
            "alpha": alpha,
            "order": order,
            "horizon_days": horizon,
            **regression_metrics(anomaly[common], predicted[common]),
        }
        for alpha, predicted in forecasts.items()
    ]
    best = min(scores, key=lambda row: (row["rmse"], -row["alpha"]))
    return models[best["alpha"]], best["alpha"], scores
