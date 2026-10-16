"""Daily AR(1) forecasts and their exact stationary OU interpretation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import NormalDist

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class AR1:
    intercept: float
    phi: float
    innovation_variance: float
    n_pairs: int

    def forecast(self, origin: pd.Series, horizon: int) -> pd.Series:
        """Conditional mean at origin+h, using no intermediate observations."""
        if not isinstance(horizon, int) or isinstance(horizon, bool) or horizon < 1:
            raise ValueError("horizon must be a positive integer number of days")
        mean = origin.astype(float).copy()
        for _ in range(horizon):
            mean = self.intercept + self.phi * mean
        return mean

    def interval_radius(self, horizon: int, level: float = 0.95) -> float:
        if not isinstance(horizon, int) or horizon < 1:
            raise ValueError("horizon must be a positive integer")
        if not 0 < level < 1:
            raise ValueError("interval level must be between 0 and 1")
        variance = self.innovation_variance * sum(
            self.phi ** (2 * k) for k in range(horizon)
        )
        return float(NormalDist().inv_cdf((1 + level) / 2) * np.sqrt(variance))

    def ou_parameters(self) -> dict[str, float] | None:
        """Map X[t+1]=c+phi*X[t]+epsilon to dX=theta*(mu-X)dt+sigma*dW.

        Time is in days. A stationary scalar OU requires 0 < phi < 1.
        AR(1) and this exact OU transition have identical forecast distributions;
        they should not be presented as independent competing models.
        """
        if not 0 < self.phi < 1:
            return None
        theta = -np.log(self.phi)
        return {
            "theta_per_day": float(theta),
            "mu_celsius": float(self.intercept / (1 - self.phi)),
            "sigma_celsius_per_sqrt_day": float(
                np.sqrt(self.innovation_variance * 2 * theta / (1 - self.phi**2))
            ),
            "half_life_days": float(np.log(2) / theta),
        }

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "ou": self.ou_parameters()}


def fit_ar1(anomaly: pd.Series, *, min_pairs: int = 30) -> AR1:
    """OLS on finite adjacent calendar-day training pairs, with an intercept."""
    if not isinstance(anomaly.index, pd.DatetimeIndex):
        raise TypeError("anomaly index must be a DatetimeIndex")
    if anomaly.index.has_duplicates:
        raise ValueError("anomaly index contains duplicate dates")
    if min_pairs < 3:
        raise ValueError("min_pairs must be at least 3")
    daily = anomaly.sort_index().astype(float).asfreq("D")
    pairs = pd.concat([daily.shift(1).rename("lag"), daily.rename("target")], axis=1)
    pairs = pairs.replace([np.inf, -np.inf], np.nan).dropna()
    if len(pairs) < min_pairs:
        raise ValueError(f"AR(1) needs at least {min_pairs} valid adjacent-day pairs")
    design = np.column_stack([np.ones(len(pairs)), pairs["lag"].to_numpy()])
    coefficients, _, rank, _ = np.linalg.lstsq(design, pairs["target"], rcond=None)
    if rank < 2:
        raise ValueError("AR(1) cannot be identified from a constant training series")
    errors = pairs["target"].to_numpy() - design @ coefficients
    return AR1(
        intercept=float(coefficients[0]),
        phi=float(coefficients[1]),
        innovation_variance=float(errors @ errors / (len(pairs) - 2)),
        n_pairs=len(pairs),
    )
