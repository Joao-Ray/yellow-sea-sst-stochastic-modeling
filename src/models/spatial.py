"""Training-only weighted EOFs and autoregressive spatial-increment forecasts."""

from dataclasses import dataclass
import numpy as np
import pandas as pd

from src.models.autoregression import fit_ar
from src.models.seasonal import seasonal_design


@dataclass
class SpatialForecast:
    coefficients: np.ndarray
    basis: np.ndarray
    weights: np.ndarray
    origin: pd.Timestamp
    harmonics: int
    trend: bool
    models: list
    rank: int
    order: int
    variance_fraction: float

    def cycle(self, dates):
        return (
            seasonal_design(dates, self.origin, self.harmonics, self.trend)
            @ self.coefficients
        )

    def predict(self, values, dates, horizon):
        """Persist unresolved origin structure; update retained modal anomalies."""
        cycle = self.cycle(dates)
        anomalies = values - cycle
        scores = anomalies @ (np.sqrt(self.weights)[:, None] * self.basis)
        future = np.column_stack(
            [
                m.forecast(pd.Series(scores[:, j], index=dates), horizon).values
                for j, m in enumerate(self.models)
            ]
        )
        origin_scores = pd.DataFrame(scores, index=dates).shift(horizon).values
        origin_anomaly = pd.DataFrame(anomalies, index=dates).shift(horizon).values
        return (
            cycle
            + origin_anomaly
            + (future - origin_scores) @ (self.basis.T / np.sqrt(self.weights)[None, :])
        )

    def to_dict(self):
        return {
            "seasonal_coefficients": self.coefficients.tolist(),
            "weighted_eof_basis": self.basis.tolist(),
            "normalized_area_weights": self.weights.tolist(),
            "origin": str(self.origin.date()),
            "harmonics": self.harmonics,
            "trend": self.trend,
            "rank": self.rank,
            "order": self.order,
            "training_variance_fraction": self.variance_fraction,
            "mode_ar_parameters": [m.to_dict() for m in self.models],
            "prediction_rule": "origin anomaly plus predicted retained-mode increment; unresolved origin structure persists",
        }


def fit_spatial_candidates(values, dates, weights, config):
    """Never use selection/test rows to estimate cycles, EOFs, or AR coefficients."""
    weights = np.asarray(weights, dtype=float)
    weights = weights / weights.sum()
    if values.shape != (len(dates), len(weights)) or not np.isfinite(values).all():
        raise ValueError("spatial input needs complete finite daily grid values")
    if not dates.equals(pd.date_range(dates[0], dates[-1])):
        raise ValueError("spatial input requires consecutive daily dates")
    train = dates <= pd.Timestamp(config["train_end"])
    selection = (dates > pd.Timestamp(config["train_end"])) & (
        dates <= pd.Timestamp(config["selection_end"])
    )
    maximum = max(config["spatial_ranks"])
    candidates, scores = [], []
    for trend in config["trend_candidates"]:
        design = seasonal_design(dates, dates[0], config["harmonics"], trend)
        coefficients = np.linalg.lstsq(design[train], values[train], rcond=None)[0]
        anomalies = values - design @ coefficients
        weighted_training = anomalies[train] * np.sqrt(weights)
        eigenvalues, vectors = np.linalg.eigh(weighted_training.T @ weighted_training)
        eigenvalues, vectors = eigenvalues[::-1], vectors[:, ::-1]
        if maximum > len(weights):
            raise ValueError("requested spatial rank exceeds available grid cells")
        basis = vectors[:, :maximum].copy()
        for j in range(maximum):
            if basis[np.argmax(np.abs(basis[:, j])), j] < 0:
                basis[:, j] *= -1
        principal = anomalies @ (np.sqrt(weights)[:, None] * basis)
        for order in config["ar_orders"]:
            models = [
                fit_ar(pd.Series(principal[train, j], index=dates[train]), order)
                for j in range(maximum)
            ]
            for rank in config["spatial_ranks"]:
                if any(not m.to_dict()["stationary"] for m in models[:rank]):
                    continue
                candidate = SpatialForecast(
                    coefficients,
                    basis[:, :rank],
                    weights,
                    dates[0],
                    config["harmonics"],
                    trend,
                    models[:rank],
                    rank,
                    order,
                    float(eigenvalues[:rank].sum() / eigenvalues.sum()),
                )
                forecast = candidate.predict(values, dates, config["selection_horizon"])
                daily_loss = ((forecast[selection] - values[selection]) ** 2) @ weights
                score = {
                    "trend": trend,
                    "rank": rank,
                    "order": order,
                    "selection_days": int(selection.sum()),
                    "selection_horizon": config["selection_horizon"],
                    "selection_rmse": float(np.sqrt(daily_loss.mean())),
                }
                candidates.append(candidate)
                scores.append(score)
    if not candidates:
        raise ValueError("no stationary training-only spatial candidate")
    best = min(
        range(len(scores)),
        key=lambda j: (
            scores[j]["selection_rmse"],
            scores[j]["rank"],
            scores[j]["order"],
            scores[j]["trend"],
        ),
    )
    return candidates[best], pd.DataFrame(scores)
