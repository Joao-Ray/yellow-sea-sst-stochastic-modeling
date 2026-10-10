"""Training-only coupled linear and nonlinear controls in a locked EOF space."""

from dataclasses import dataclass
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor

from src.models.autoregression import Autoregression
from src.models.seasonal import seasonal_design
from src.models.spatial import SpatialForecast


def load_spatial(path):
    p = json.loads(Path(path).read_text())
    return SpatialForecast(
        np.asarray(p["seasonal_coefficients"]),
        np.asarray(p["weighted_eof_basis"]),
        np.asarray(p["normalized_area_weights"]),
        pd.Timestamp(p["origin"]),
        p["harmonics"],
        p["trend"],
        [
            Autoregression(
                m["intercept"],
                tuple(m["coefficients"]),
                m["innovation_variance"],
                m["n_pairs"],
            )
            for m in p["mode_ar_parameters"]
        ],
        p["rank"],
        p["order"],
        p["training_variance_fraction"],
    )


def shift(values, days):
    result = np.full(np.shape(values), np.nan, dtype=float)
    if days == 0:
        return np.asarray(values, float).copy()
    if days < 0:
        raise ValueError("future shifts are forbidden")
    result[days:] = values[:-days]
    return result


def project_modes(values, dates, spatial):
    cycle = spatial.cycle(dates)
    anomaly = np.asarray(values, float) - cycle
    scores = anomaly @ (np.sqrt(spatial.weights)[:, None] * spatial.basis)
    return cycle, anomaly, scores


def reconstruct(cycle, anomaly, scores, future_scores, spatial, horizon):
    increment = future_scores - shift(scores, horizon)
    return (
        cycle
        + shift(anomaly, horizon)
        + increment @ (spatial.basis.T / np.sqrt(spatial.weights)[None, :])
    )


@dataclass
class RidgeVAR:
    intercept: np.ndarray
    coefficients: np.ndarray
    order: int
    alpha: float
    spectral_radius: float
    n_training: int

    def predict(self, scores, horizon):
        state = np.column_stack([shift(scores, horizon + j) for j in range(self.order)])
        rank = scores.shape[1]
        for _ in range(horizon):
            new = self.intercept + state @ self.coefficients
            state = np.column_stack([new, state[:, :-rank]])
        return state[:, :rank]

    def to_dict(self):
        return {
            "intercept": self.intercept.tolist(),
            "coefficients": self.coefficients.tolist(),
            "order": self.order,
            "alpha": self.alpha,
            "spectral_radius": self.spectral_radius,
            "n_training": self.n_training,
        }


def fit_var(scores, order, alpha):
    x = np.column_stack([shift(scores, j) for j in range(1, order + 1)])[order:]
    y = scores[order:]
    if not np.isfinite(x).all() or not np.isfinite(y).all() or len(y) < 5 * x.shape[1]:
        raise ValueError("VAR needs sufficient finite training lag vectors")
    center, scale = x.mean(axis=0), x.std(axis=0)
    if (scale <= np.finfo(float).eps).any():
        raise ValueError("VAR training features have zero variance")
    z = (x - center) / scale
    coef = (
        np.linalg.solve(
            z.T @ z + len(y) * alpha * np.eye(z.shape[1]), z.T @ (y - y.mean(axis=0))
        )
        / scale[:, None]
    )
    intercept = y.mean(axis=0) - center @ coef
    rank = y.shape[1]
    companion = np.zeros((rank * order, rank * order))
    companion[:rank] = coef.T
    companion[rank:, :-rank] = np.eye(rank * (order - 1))
    radius = float(np.abs(np.linalg.eigvals(companion)).max())
    return RidgeVAR(intercept, coef, order, alpha, radius, len(y))


@dataclass
class DirectTrees:
    estimator: ExtraTreesRegressor
    center: np.ndarray
    scale: np.ndarray
    lags: tuple
    horizon: int
    n_training: int

    def predict(self, scores, dates):
        features = tree_features(scores, dates, self.horizon, self.lags)
        valid = np.isfinite(features).all(axis=1)
        result = np.full(scores.shape, np.nan)
        increments = self.estimator.predict(features[valid]) * self.scale + self.center
        result[valid] = shift(scores, self.horizon)[valid] + increments
        return result

    def to_dict(self):
        return {
            "hyperparameters": self.estimator.get_params(),
            "target_center": self.center.tolist(),
            "target_scale": self.scale.tolist(),
            "feature_lags": self.lags,
            "horizon_days": self.horizon,
            "n_training": self.n_training,
            "features": "origin modal states at lags 0/1/6/13 and known target calendar/trend",
            "target": "standardized retained-mode increment from origin to target",
        }


def tree_features(scores, dates, horizon, lags):
    return np.column_stack(
        [shift(scores, horizon + j) for j in lags]
        + [seasonal_design(dates, dates[0], 3, True)[:, 1:]]
    )


def fit_trees(scores, dates, train_end, horizon, lags, leaf, features, count, seed):
    x = tree_features(scores, dates, horizon, lags)
    delta = scores - shift(scores, horizon)
    valid = (dates <= pd.Timestamp(train_end)) & np.isfinite(x).all(axis=1)
    valid &= np.isfinite(delta).all(axis=1)
    y = delta[valid]
    center, scale = y.mean(axis=0), y.std(axis=0)
    if len(y) < 100 or (scale <= np.finfo(float).eps).any():
        raise ValueError("tree targets need sufficient nonconstant training increments")
    estimator = ExtraTreesRegressor(
        n_estimators=count,
        min_samples_leaf=leaf,
        max_features=features,
        bootstrap=False,
        random_state=seed,
        n_jobs=2,
    ).fit(x[valid], (y - center) / scale)
    return DirectTrees(estimator, center, scale, tuple(lags), horizon, int(valid.sum()))


def select_benchmarks(values, dates, spatial, config):
    cycle, anomaly, scores = project_modes(values, dates, spatial)
    train = dates <= pd.Timestamp(config["train_end"])
    selection = (dates > pd.Timestamp(config["train_end"])) & (
        dates <= pd.Timestamp(config["selection_end"])
    )
    h = config["selection_horizon"]
    rows, var_candidates, tree_candidates = [], [], []
    for order in config["var_orders"]:
        for alpha in config["var_alphas"]:
            model = fit_var(scores[train], order, alpha)
            if model.spectral_radius >= 1:
                rows.append(
                    {
                        "model": "eof_var_ridge",
                        "order": order,
                        "alpha": alpha,
                        "eligible": False,
                        "selection_rmse": np.nan,
                    }
                )
                continue
            predicted = reconstruct(
                cycle, anomaly, scores, model.predict(scores, h), spatial, h
            )
            rmse = float(
                np.sqrt(
                    np.mean(
                        (predicted[selection] - values[selection]) ** 2
                        @ spatial.weights
                    )
                )
            )
            row = {
                "model": "eof_var_ridge",
                "order": order,
                "alpha": alpha,
                "eligible": True,
                "selection_rmse": rmse,
            }
            rows.append(row)
            var_candidates.append((rmse, order, -alpha, model))
    if not var_candidates:
        raise ValueError("no stable VAR candidate")
    selected_var = min(var_candidates, key=lambda x: x[:3])[-1]
    for leaf in config["tree_leaf_sizes"]:
        for feature in config["tree_max_features"]:
            model = fit_trees(
                scores,
                dates,
                config["train_end"],
                h,
                config["tree_feature_lags"],
                leaf,
                feature,
                config["tree_count"],
                config["tree_seed"],
            )
            predicted = reconstruct(
                cycle, anomaly, scores, model.predict(scores, dates), spatial, h
            )
            rmse = float(
                np.sqrt(
                    np.mean(
                        (predicted[selection] - values[selection]) ** 2
                        @ spatial.weights
                    )
                )
            )
            rows.append(
                {
                    "model": "eof_extra_trees",
                    "leaf": leaf,
                    "max_features": feature,
                    "eligible": True,
                    "selection_rmse": rmse,
                }
            )
            tree_candidates.append((rmse, -leaf, feature, model))
    selected_tree = min(tree_candidates, key=lambda x: x[:3])[-1]
    p = selected_tree.estimator.get_params()
    trees = {h: selected_tree}
    for horizon in config["horizons"]:
        if horizon != h:
            trees[horizon] = fit_trees(
                scores,
                dates,
                config["train_end"],
                horizon,
                config["tree_feature_lags"],
                p["min_samples_leaf"],
                p["max_features"],
                config["tree_count"],
                config["tree_seed"],
            )
    table = pd.DataFrame(rows)
    table["selection_days"] = int(selection.sum())
    return selected_var, trees, table
