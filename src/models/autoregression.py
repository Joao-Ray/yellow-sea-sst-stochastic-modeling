"""Training-only AR(p) fitting and recursive forecasts at observed origins."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import NormalDist

import numpy as np
import pandas as pd

from src.evaluation.metrics import regression_metrics


@dataclass(frozen=True)
class Autoregression:
    intercept: float
    coefficients: tuple[float, ...]
    innovation_variance: float
    n_pairs: int

    @property
    def order(self) -> int:
        return len(self.coefficients)

    def forecast(self, anomaly: pd.Series, horizon: int) -> pd.Series:
        if not isinstance(horizon, int) or isinstance(horizon, bool) or horizon < 1:
            raise ValueError("horizon must be a positive integer")
        daily = anomaly.sort_index().asfreq("D")
        # At target d, the newest allowed input is d-h; all other inputs precede it.
        state = np.column_stack(
            [daily.shift(horizon + lag) for lag in range(self.order)]
        )
        for _ in range(horizon):
            next_value = self.intercept + state @ np.asarray(self.coefficients)
            state = np.column_stack([next_value, state[:, :-1]])
        return pd.Series(
            state[:, 0], index=daily.index, name="predicted_anomaly_celsius"
        )

    def interval_radius(self, horizon: int, level: float = 0.95) -> float:
        if not isinstance(horizon, int) or horizon < 1 or not 0 < level < 1:
            raise ValueError(
                "positive integer horizon and interval level in (0, 1) required"
            )
        impulse = np.zeros(horizon)
        impulse[0] = 1
        for k in range(1, horizon):
            impulse[k] = sum(
                self.coefficients[j - 1] * impulse[k - j]
                for j in range(1, min(self.order, k) + 1)
            )
        return float(
            NormalDist().inv_cdf((1 + level) / 2)
            * np.sqrt(self.innovation_variance * (impulse @ impulse))
        )

    def residuals(self, anomaly: pd.Series) -> pd.Series:
        return (anomaly - self.forecast(anomaly, 1)).rename("residual_celsius")

    def to_dict(self) -> dict[str, object]:
        companion = np.zeros((self.order, self.order))
        companion[0] = self.coefficients
        if self.order > 1:
            companion[1:, :-1] = np.eye(self.order - 1)
        radius = float(np.max(np.abs(np.linalg.eigvals(companion))))
        return {
            **asdict(self),
            "order": self.order,
            "spectral_radius": radius,
            "stationary": radius < 1,
        }


def fit_ar(anomaly: pd.Series, order: int) -> Autoregression:
    if not isinstance(order, int) or isinstance(order, bool) or order < 1:
        raise ValueError("AR order must be a positive integer")
    if not isinstance(anomaly.index, pd.DatetimeIndex) or anomaly.index.has_duplicates:
        raise ValueError("AR input requires unique datetime dates")
    daily = anomaly.sort_index().asfreq("D").astype(float)
    columns = {"target": daily}
    columns.update({f"lag{k}": daily.shift(k) for k in range(1, order + 1)})
    pairs = pd.DataFrame(columns).replace([np.inf, -np.inf], np.nan).dropna()
    minimum = max(30, 3 * (order + 1))
    if len(pairs) < minimum:
        raise ValueError(
            f"AR({order}) needs at least {minimum} complete calendar-day lag vectors"
        )
    design = np.column_stack([np.ones(len(pairs)), pairs.iloc[:, 1:].to_numpy()])
    values, _, rank, _ = np.linalg.lstsq(design, pairs.target, rcond=None)
    if rank < order + 1:
        raise ValueError(f"AR({order}) training design is rank deficient")
    errors = pairs.target.to_numpy() - design @ values
    return Autoregression(
        float(values[0]),
        tuple(float(x) for x in values[1:]),
        float(errors @ errors / (len(pairs) - order - 1)),
        len(pairs),
    )


def select_ar_order(
    anomaly: pd.Series,
    *,
    train_end: pd.Timestamp,
    validation_end: pd.Timestamp,
    orders: tuple[int, ...],
    horizon: int,
) -> tuple[Autoregression, list[dict[str, object]]]:
    if not orders or len(set(orders)) != len(orders):
        raise ValueError("AR candidates must be non-empty unique orders")
    models = {p: fit_ar(anomaly.loc[:train_end], p) for p in sorted(orders)}
    forecasts = {p: model.forecast(anomaly, horizon) for p, model in models.items()}
    common = (
        anomaly.notna()
        & (anomaly.index > train_end)
        & (anomaly.index <= validation_end)
    )
    for predicted in forecasts.values():
        common &= np.isfinite(predicted)
    if not common.any():
        raise ValueError("AR order selection has no common validation targets")
    scores = []
    for order, predicted in forecasts.items():
        metrics = regression_metrics(anomaly.loc[common], predicted.loc[common])
        scores.append({"order": order, "horizon_days": horizon, **metrics})
    best = min(scores, key=lambda row: (row["rmse"], row["order"]))
    return models[int(best["order"])], scores
