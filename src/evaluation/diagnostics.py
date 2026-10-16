"""Calendar-aware training residual diagnostics and test interval coverage."""

from __future__ import annotations

import json
import os
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd

from src.evaluation.experiment import ExperimentResult
from src.models.ar1 import AR1
from src.models.autoregression import Autoregression


def calendar_residual_acf(
    residual: pd.Series, lags: tuple[int, ...] = (1, 7, 30)
) -> pd.DataFrame:
    """Correlate pairs separated by actual calendar days, never compress gaps."""
    daily = residual.sort_index().asfreq("D")
    records = []
    for lag in lags:
        paired = pd.concat([daily, daily.shift(lag)], axis=1).dropna()
        correlation = (
            paired.iloc[:, 0].corr(paired.iloc[:, 1]) if len(paired) > 2 else np.nan
        )
        records.append(
            {"lag_days": lag, "n_pairs": len(paired), "correlation": correlation}
        )
    return pd.DataFrame(records)


def write_diagnostics(result: ExperimentResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    training = result.anomalies.loc[: result.protocol["train_end"], "anomaly_celsius"]
    params = result.parameters["ar1"]
    ar1 = AR1(
        **{
            name: params[name]
            for name in ("intercept", "phi", "innovation_variance", "n_pairs")
        }
    )
    residuals = {"ar1": training - ar1.forecast(training.shift(1), 1)}
    selected = result.parameters.get("selected_ar")
    primary = "ar1"
    if selected and selected["order"] > 1:
        primary = f"ar{selected['order']}"
        model = Autoregression(
            selected["intercept"],
            tuple(selected["coefficients"]),
            selected["innovation_variance"],
            selected["n_pairs"],
        )
        residuals[primary] = model.residuals(training)
    frame = pd.DataFrame(residuals)
    frame.index.name = "date"
    frame.to_csv(output_dir / "training_residuals.csv", date_format="%Y-%m-%d")
    acfs = []
    descriptions = {}
    for name, residual in residuals.items():
        acf = calendar_residual_acf(residual)
        acf["model"] = name
        acfs.append(acf)
        finite = residual.dropna()
        descriptions[name] = {
            "n": len(finite),
            "mean_celsius": float(finite.mean()),
            "std_celsius": float(finite.std()),
            "skewness": float(finite.skew()),
            "excess_kurtosis": float(finite.kurt()),
        }
    acf_table = pd.concat(acfs, ignore_index=True)
    acf_table.to_csv(output_dir / "residual_acf.csv", index=False)
    (output_dir / "diagnostics.json").write_text(
        json.dumps(
            {
                "scope": "training residual description only; not forecast skill inference",
                "models": descriptions,
            },
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )
    predictions = result.predictions.query("split == 'test'").copy()
    predictions["year"] = predictions.date.dt.year
    coverage = []
    for (name, horizon, year), group in predictions.groupby(
        ["model", "horizon_days", "year"]
    ):
        if not name.startswith("ar"):
            continue
        coverage.append(
            {
                "model": name,
                "horizon_days": horizon,
                "year": year,
                "n": len(group),
                "coverage_95": float(
                    group.observed_anomaly_celsius.between(
                        group.lower_95_celsius, group.upper_95_celsius
                    ).mean()
                ),
            }
        )
    pd.DataFrame(coverage).to_csv(output_dir / "coverage_by_year.csv", index=False)
    os.environ.setdefault("MPLCONFIGDIR", str((output_dir / ".matplotlib").resolve()))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    label = (
        "SYNTHETIC workflow check"
        if result.protocol["data_kind"] == "synthetic"
        else "preliminary observational pilot"
    )
    figure.suptitle(f"Training residual diagnostics | {label}")
    for name, residual in residuals.items():
        axes[0, 0].plot(residual.index, residual, lw=0.45, alpha=0.65, label=name)
    axes[0, 0].set(title="Training residuals", ylabel="Residual (°C)")
    axes[0, 0].legend()
    for i, (name, group) in enumerate(acf_table.groupby("model")):
        axes[0, 1].bar(
            np.arange(len(group)) + i * 0.3, group.correlation, width=0.28, label=name
        )
    axes[0, 1].set(
        xticks=np.arange(3) + (len(residuals) - 1) * 0.15,
        xticklabels=[1, 7, 30],
        title="Calendar-lag residual correlations",
        xlabel="Lag (days)",
        ylabel="Correlation",
    )
    axes[0, 1].axhline(0, color="black", lw=0.7)
    axes[0, 1].legend()
    values = frame[primary].dropna().sort_values().to_numpy()
    probability = (np.arange(len(values)) + 0.5) / len(values)
    normal = np.array([NormalDist().inv_cdf(p) for p in probability])
    standardized = (values - values.mean()) / values.std(ddof=1)
    axes[1, 0].scatter(normal, standardized, s=5, alpha=0.4)
    axes[1, 0].plot([-4, 4], [-4, 4], "--", color="black", lw=0.8)
    axes[1, 0].set(
        title=f"{primary} residual normal Q–Q",
        xlabel="Standard normal quantile",
        ylabel="Standardized residual quantile",
    )
    cov = pd.DataFrame(coverage)
    for horizon, group in cov[cov.model.eq(primary)].groupby("horizon_days"):
        axes[1, 1].plot(
            group.year, group.coverage_95, marker="o", label=f"{horizon} days"
        )
    axes[1, 1].axhline(0.95, color="black", ls="--", lw=0.8, label="Nominal 95%")
    axes[1, 1].set(
        title=f"{primary} interval coverage in each test year",
        xlabel="Test year",
        ylabel="Observed coverage",
        ylim=(0, 1.03),
        xticks=sorted(cov.year.unique()),
    )
    axes[1, 1].legend()
    for axis in axes.ravel():
        axis.grid(alpha=0.18)
    figure.savefig(output_dir / "residual_diagnostics.png", dpi=150)
    plt.close(figure)
