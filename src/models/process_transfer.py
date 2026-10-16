"""Past-only regional direct-increment models and unchanged-parameter transfer."""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.linear_model import Ridge

from src.models.seasonal import seasonal_design


def heat_into_ocean(fields):
    """Explicit downward minus upward radiation, minus upward turbulent heat."""
    return (
        fields["dswrf"]
        - fields["uswrf"]
        + fields["dlwrf"]
        - fields["ulwrf"]
        - fields["lhtfl"]
        - fields["shtfl"]
    )


def validate_calendar(series):
    if (
        not isinstance(series.index, pd.DatetimeIndex)
        or series.index.tz is not None
        or series.index.has_duplicates
        or not series.index.equals(pd.date_range(series.index[0], series.index[-1]))
    ):
        raise ValueError(
            "ordered, unique, complete timezone-free daily calendar required"
        )
    if not np.isfinite(series.to_numpy(float)).all():
        raise ValueError("series must be finite, without imputed values")


def feature_matrix(sst, forcing, horizon, group, delay=1):
    """Target-indexed rows: SST <= target-h; forcing <= target-h-delay."""
    validate_calendar(sst)
    if group not in {"sst", "sst_heat", "sst_heat_wind"}:
        raise ValueError("unknown feature group")
    if not isinstance(horizon, int) or horizon < 1 or delay < 1:
        raise ValueError("positive horizon and forcing delay required")
    f = pd.DataFrame(index=sst.index)
    for lag in [0, 1, 7, 30]:
        f[f"sst_origin_minus_{lag}"] = sst.shift(horizon + lag)
    for window in [7, 30]:
        f[f"sst_past_mean_{window}"] = sst.rolling(window).mean().shift(horizon)
        f[f"sst_past_std_{window}"] = sst.rolling(window).std().shift(horizon)
        f[f"sst_past_change_{window}"] = sst.diff(window).shift(horizon)
    cal = seasonal_design(sst.index, pd.Timestamp("2010-01-01"), 3, True)
    for j in range(1, cal.shape[1]):
        f[f"known_target_calendar_{j}"] = cal[:, j]
    if group != "sst":
        if forcing is None or not forcing.index.equals(sst.index):
            raise ValueError("forcing must align exactly with the SST calendar")
        validate_calendar(forcing)
        drivers = pd.DataFrame({"heat_into_ocean": heat_into_ocean(forcing)})
        if group == "sst_heat_wind":
            drivers["daily_mean_u"] = forcing.uwnd
            drivers["daily_mean_v"] = forcing.vwnd
            # Magnitude of a daily-mean vector, not the daily mean wind speed.
            drivers["daily_vector_magnitude"] = np.hypot(forcing.uwnd, forcing.vwnd)
        for name in drivers:
            for window in [1, 7, 30]:
                f[f"{name}_past_mean_{window}"] = (
                    drivers[name].rolling(window).mean().shift(horizon + delay)
                )
    return f, sst.shift(horizon)


@dataclass
class IncrementModel:
    family: str
    hyperparameter: float
    columns: tuple
    mean: np.ndarray
    scale: np.ndarray
    fitted: object
    training_end: str
    training_rows: int

    def predict(self, features, origin):
        if tuple(features.columns) != self.columns:
            raise ValueError("source and destination feature definitions differ")
        x = (features.to_numpy(float) - self.mean) / self.scale
        valid = np.isfinite(x).all(axis=1) & np.isfinite(origin)
        result = pd.Series(np.nan, index=features.index, name="predicted_sst_celsius")
        result.loc[valid] = origin.loc[valid] + self.fitted.predict(x[valid])
        return result


def fit_increment(
    features,
    origin,
    target,
    family,
    hyperparameter,
    train_end,
    seed=20261016,
    estimators=200,
):
    if not features.index.equals(target.index) or not origin.index.equals(target.index):
        raise ValueError("features, origins and targets must align")
    # The mask is on target dates, including for direct h-day increment labels.
    mask = (
        (target.index <= pd.Timestamp(train_end))
        & np.isfinite(features.to_numpy(float)).all(axis=1)
        & np.isfinite(origin)
        & np.isfinite(target)
    )
    if mask.sum() < 730:
        raise ValueError("at least two years of training targets required")
    x = features.loc[mask].to_numpy(float)
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale = np.where(scale > 1e-12, scale, 1.0)
    y = (target.loc[mask] - origin.loc[mask]).to_numpy(float)
    if family == "ridge":
        fitted = Ridge(alpha=float(hyperparameter))
    elif family == "trees":
        fitted = ExtraTreesRegressor(
            n_estimators=estimators,
            min_samples_leaf=int(hyperparameter),
            max_features=1.0,
            random_state=seed,
            n_jobs=2,
        )
    else:
        raise ValueError("unknown model family")
    fitted.fit((x - mean) / scale, y)
    return IncrementModel(
        family,
        hyperparameter,
        tuple(features.columns),
        mean,
        scale,
        fitted,
        str(pd.Timestamp(train_end).date()),
        int(mask.sum()),
    )


def select_source(sst, forcing, family, group, candidates, config):
    """No destination series or outcomes enter source model selection."""
    h = config["selection_horizon"]
    x, origin = feature_matrix(sst, forcing, h, group, config["forcing_delay_days"])
    rows = []
    for value in candidates:
        fitted = fit_increment(
            x,
            origin,
            sst,
            family,
            value,
            config["train_end"],
            config["random_seed"],
            config["tree_estimators"],
        )
        prediction = fitted.predict(x, origin)
        mask = (sst.index >= config["selection_start"]) & (
            sst.index <= config["selection_end"]
        )
        error = prediction.loc[mask] - sst.loc[mask]
        if not np.isfinite(error).all():
            raise ValueError("selection requires complete matched days")
        rows.append(
            {
                "family": family,
                "group": group,
                "hyperparameter": value,
                "selection_horizon": h,
                "rmse": float(np.sqrt(np.mean(error**2))),
                "n_days": int(mask.sum()),
            }
        )
    # Candidate order is the fixed deterministic tie breaker.
    best = min(rows, key=lambda r: r["rmse"])
    return best["hyperparameter"], rows
