"""Separated training, model selection, interval calibration, and test periods."""

import numpy as np
import pandas as pd
from src.data.preprocess import calculate_climatology
from src.evaluation.calibration import empirical_radius
from src.evaluation.diagnostics import calendar_residual_acf
from src.evaluation.metrics import regression_metrics
from src.models.autoregression import select_ar_order
from src.models.ridge import select_ridge
from src.models.seasonal import fit_seasonal


def run_research_fold(sst: pd.Series, fold: dict, config: dict) -> dict:
    if (
        not isinstance(sst.index, pd.DatetimeIndex)
        or sst.index.has_duplicates
        or sst.index.tz is not None
        or not sst.index.equals(sst.index.normalize())
    ):
        raise ValueError("input needs unique timezone-free midnight dates")
    sst = (
        sst.sort_index()
        .asfreq("D")
        .replace([np.inf, -np.inf], np.nan)
        .loc[: fold["test_end"]]
    )
    boundaries = [
        pd.Timestamp(fold[k])
        for k in ("train_end", "selection_end", "calibration_end", "test_end")
    ]
    if (
        not sst.index[0]
        < boundaries[0]
        < boundaries[1]
        < boundaries[2]
        < boundaries[3]
        <= sst.index[-1]
    ):
        raise ValueError("ordered training/selection/calibration/test dates required")
    train_end, selection_end, calibration_end, _ = boundaries
    models, selections, cycles, residuals, harmonic, trend = fit_research_candidates(
        sst, train_end, selection_end, config
    )
    daily_cycle = cycles["day"]
    predictions, metrics, yearly, radii = [], [], [], []
    for horizon in config["horizons"]:
        means = {
            "climatology": daily_cycle,
            "persistence": daily_cycle + residuals["day"].shift(horizon),
            "raw_persistence": sst.shift(horizon),
            "trend_seasonal": cycles["harmonic_trend"],
        }
        gaussian = {}
        for name, (model, cycle, residual) in models.items():
            means[name] = cycle + model.forecast(residual, horizon)
            # Ridge intervals are calibrated empirically; do not present a
            # penalized fit's residual variance as an exact Gaussian interval.
            gaussian[name] = (
                model.interval_radius(horizon, config["interval_level"])
                if name.startswith("ar_")
                else np.nan
            )
        common = sst.notna()
        for mean in means.values():
            common &= np.isfinite(mean)
        calibration = (
            common & (sst.index > selection_end) & (sst.index <= calibration_end)
        )
        testing = common & (sst.index > calibration_end)
        if not testing.any():
            raise ValueError("test has no shared scoring dates")
        for name, predicted in means.items():
            radius = empirical_radius(
                sst[calibration], predicted[calibration], config["interval_level"]
            )
            radii.append({"model": name, "horizon_days": horizon, **radius})
            selected_dates = common & (sst.index > selection_end)
            frame = pd.DataFrame(
                {
                    "date": sst.index[selected_dates],
                    "origin_date": sst.index[selected_dates]
                    - pd.Timedelta(days=horizon),
                    "split": np.where(
                        sst.index[selected_dates] <= calibration_end,
                        "calibration",
                        "test",
                    ),
                    "model": name,
                    "horizon_days": horizon,
                    "observed_sst_celsius": sst[selected_dates].values,
                    "predicted_sst_celsius": predicted[selected_dates].values,
                    "calibrated_radius_celsius": radius["radius_celsius"],
                    "gaussian_radius_celsius": gaussian.get(name, np.nan),
                }
            )
            predictions.append(frame)
            error = sst[testing] - predicted[testing]
            row = {
                "model": name,
                "horizon_days": horizon,
                **regression_metrics(sst[testing], predicted[testing]),
                "bias_celsius": float((-error).mean()),
                "coverage_calibrated": float(
                    (error.abs() <= radius["radius_celsius"]).mean()
                ),
                "width_calibrated_celsius": 2 * radius["radius_celsius"],
                "n_calibration": radius["n_calibration"],
                "coverage_gaussian": float((error.abs() <= gaussian[name]).mean())
                if name in gaussian and np.isfinite(gaussian[name])
                else np.nan,
                "width_gaussian_celsius": 2 * gaussian.get(name, np.nan),
            }
            metrics.append(row)
            for year in sorted(sst[testing].index.year.unique()):
                mask = testing & (sst.index.year == year)
                err = sst[mask] - predicted[mask]
                yearly.append(
                    {
                        "model": name,
                        "horizon_days": horizon,
                        "year": int(year),
                        **regression_metrics(sst[mask], predicted[mask]),
                        "bias_celsius": float((-err).mean()),
                        "coverage_calibrated": float(
                            (err.abs() <= radius["radius_celsius"]).mean()
                        ),
                    }
                )
    training_residuals = pd.DataFrame(
        {
            name: model.residuals(residual.loc[:train_end])
            for name, (model, _, residual) in models.items()
        }
    )
    training_residuals.index.name = "date"
    residual_diagnostics = []
    for name in training_residuals:
        finite = training_residuals[name].dropna()
        table = calendar_residual_acf(training_residuals[name])
        table["model"] = name
        table["std_celsius"] = float(finite.std())
        table["skewness"] = float(finite.skew())
        table["excess_kurtosis"] = float(finite.kurt())
        residual_diagnostics.append(table)
    return {
        "training_residuals": training_residuals.reset_index(),
        "residual_diagnostics": pd.concat(residual_diagnostics, ignore_index=True),
        "predictions": pd.concat(predictions, ignore_index=True),
        "metrics": pd.DataFrame(metrics),
        "yearly": pd.DataFrame(yearly),
        "interval_radii": radii,
        "models": selections,
        "seasonal_fits": {
            "harmonic": harmonic.to_dict(),
            "harmonic_trend": trend.to_dict(),
        },
        "support_rule": "all models share complete target and required origin-lag dates separately at each horizon",
        "protocol": fold,
    }


def fit_research_candidates(sst, train_end, selection_end, config):
    """Fit and tune candidates using only training and selection targets."""
    training = sst.loc[:train_end]
    daily_cycle, _ = calculate_climatology(
        sst,
        reference_start=str(sst.index[0].date()),
        reference_end=str(train_end.date()),
    )
    if daily_cycle.isna().any():
        raise ValueError("training seasonal cycle has uncovered calendar bins")
    harmonic = fit_seasonal(training, config["harmonics"], False)
    trend = fit_seasonal(training, config["harmonics"], True)
    cycles = {
        "day": daily_cycle,
        "harmonic": harmonic.predict(sst.index),
        "harmonic_trend": trend.predict(sst.index),
    }
    residuals = {name: sst - cycle for name, cycle in cycles.items()}
    models, selections = {}, {}
    for name, residual in residuals.items():
        model, scores = select_ar_order(
            residual,
            train_end=train_end,
            validation_end=selection_end,
            orders=tuple(config["ar_candidates"]),
            horizon=config["selection_horizon"],
        )
        models[f"ar_{name}"] = (model, cycles[name], residual)
        selections[f"ar_{name}"] = {
            "selected_order": model.order,
            "scores": scores,
            "parameters": model.to_dict(),
        }
    ridge, alpha, scores = select_ridge(
        residuals["harmonic_trend"],
        train_end,
        selection_end,
        config["ridge_order"],
        config["ridge_alphas"],
        config["selection_horizon"],
    )
    models["ridge_harmonic_trend"] = (
        ridge,
        cycles["harmonic_trend"],
        residuals["harmonic_trend"],
    )
    selections["ridge_harmonic_trend"] = {
        "selected_alpha": alpha,
        "scores": scores,
        "parameters": ridge.to_dict(),
        "penalty_definition": "mean squared training error + alpha * sum(standardized lag coefficients squared); intercept unpenalized",
    }
    return models, selections, cycles, residuals, harmonic, trend
