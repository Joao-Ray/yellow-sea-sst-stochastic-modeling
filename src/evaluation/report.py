"""Local report artifacts; synthetic runs are prominently labeled."""

from __future__ import annotations

from pathlib import Path
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.evaluation.experiment import ExperimentResult


def write_report(result: ExperimentResult, output_dir: Path) -> None:
    os.environ.setdefault("MPLCONFIGDIR", str((output_dir / ".matplotlib").resolve()))
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd

    synthetic = result.protocol["data_kind"] == "synthetic"
    label = (
        "SYNTHETIC DEMO — not Yellow Sea observations"
        if synthetic
        else "Observational experiment — preliminary"
    )
    has_skill_intervals = (
        "skill_ci_lower" in result.metrics
        and result.metrics["skill_ci_lower"].notna().any()
    )
    figure, axes = plt.subplots(
        4 if has_skill_intervals else 3,
        1,
        figsize=(12, 13 if has_skill_intervals else 10),
        constrained_layout=True,
    )
    figure.suptitle(f"Yellow Sea SST workflow | {label}", fontsize=14, weight="bold")
    table = result.anomalies
    axes[0].plot(
        table.index, table["sst_observed_celsius"], lw=0.7, label="Regional SST"
    )
    axes[0].plot(
        table.index,
        table["climatology_celsius"],
        lw=0.7,
        alpha=0.8,
        label="Training-only seasonal cycle",
    )
    for boundary, name in (
        (result.protocol["train_end"], "Training end"),
        (result.protocol["validation_end"], "Validation end"),
    ):
        axes[0].axvline(
            pd.Timestamp(boundary), color="#666666", ls="--", lw=0.8, label=name
        )
    axes[0].set(ylabel="SST (°C)", title="Raw observations and frozen seasonal cycle")
    axes[0].legend(loc="upper left", ncol=2, fontsize=8)
    horizon = min(result.protocol["horizons_days"])
    predictions = result.predictions
    selected_ar = result.parameters.get("selected_ar")
    primary_model = f"ar{selected_ar['order']}" if selected_ar else "ar1"
    excerpt = predictions[
        (predictions["split"] == "test") & (predictions["horizon_days"] == horizon)
    ]
    for name, group in excerpt.groupby("model"):
        group = group.sort_values("date").iloc[:180]
        axes[1].plot(
            group["date"], group["predicted_anomaly_celsius"], lw=0.8, label=name
        )
        if name == primary_model:
            axes[1].plot(
                group["date"],
                group["observed_anomaly_celsius"],
                color="#222222",
                lw=1,
                label="Observed",
            )
            axes[1].fill_between(
                group["date"],
                group["lower_95_celsius"],
                group["upper_95_celsius"],
                color="#3488b8",
                alpha=0.16,
                label=f"{primary_model} conditional 95% interval",
            )
    axes[1].set(
        ylabel="Anomaly (°C)",
        title=f"First 180 scored test targets | {horizon}-day horizon",
    )
    axes[1].legend(loc="upper left", ncol=3, fontsize=8)
    for name, group in result.metrics[result.metrics["split"] == "test"].groupby(
        "model"
    ):
        group = group.sort_values("horizon_days")
        axes[2].plot(group["horizon_days"], group["rmse"], marker="o", label=name)
    axes[2].set(
        xlabel="Forecast horizon (days)",
        ylabel="Test RMSE (°C)",
        title="All models scored on the same target/origin pairs",
    )
    axes[2].set_xticks(result.protocol["horizons_days"])
    axes[2].legend()
    if has_skill_intervals:
        for name, group in result.metrics[
            (result.metrics["split"] == "test")
            & result.metrics.model.str.startswith("ar")
        ].groupby("model"):
            group = group.sort_values("horizon_days")
            (line,) = axes[3].plot(
                group.horizon_days,
                group.rmse_skill_vs_persistence,
                marker="o",
                label=name,
            )
            axes[3].vlines(
                group.horizon_days,
                group.skill_ci_lower,
                group.skill_ci_upper,
                color=line.get_color(),
                lw=2,
            )
        axes[3].axhline(0, color="#333333", ls="--", lw=0.8)
        axes[3].set(
            title="Test RMSE skill vs persistence | paired 95% calendar-block intervals",
            xlabel="Forecast horizon (days)",
            ylabel="RMSE skill",
        )
        axes[3].set_xticks(result.protocol["horizons_days"])
        axes[3].legend()
    for axis in axes:
        axis.grid(alpha=0.18)
    figure.savefig(output_dir / "overview.png", dpi=150)
    plt.close(figure)
    lines = [
        f"# Experiment report: {label}",
        "",
        "This synthetic run validates the software workflow and provides no observational research findings."
        if synthetic
        else "This run is a preliminary observational experiment, not evidence of statistically significant superiority.",
        "",
        f"Training: {result.protocol['train_start']} through {result.protocol['train_end']}.",
        f"Validation ends: {result.protocol['validation_end']}; test ends: {result.protocol['test_end']}.",
        "",
        "Climatology and all model parameters use training observations only. Parameters remain frozen during validation/test; each forecast origin uses the observation available on that date. Missing and interpolated values are excluded.",
        result.protocol["model_selection"],
        "",
        "## Scores",
        "",
        "| Split | Horizon (days) | Model | n | MAE (°C) | RMSE (°C) | RMSE skill vs persistence | 95% skill interval | AR 95% coverage |",
        "|---|---:|---|---:|---:|---:|---:|---|---:|",
    ]
    for row in result.metrics.itertuples():
        coverage = f"{row.coverage_95:.1%}" if row.model.startswith("ar") else "—"
        low, high = (
            getattr(row, "skill_ci_lower", None),
            getattr(row, "skill_ci_upper", None),
        )
        interval = (
            f"[{low:.2%}, {high:.2%}]" if pd.notna(low) and pd.notna(high) else "—"
        )
        skill = (
            f"{row.rmse_skill_vs_persistence:.2%}"
            if pd.notna(row.rmse_skill_vs_persistence)
            else "undefined"
        )
        lines.append(
            f"| {row.split} | {row.horizon_days} | {row.model} | {row.n} | {row.mae:.4f} | {row.rmse:.4f} | {skill} | {interval} | {coverage} |"
        )
    lines += [
        "",
        "Positive RMSE skill means a smaller point-estimate RMSE than persistence. This is not a significance test.",
        "",
        "## Model and limitations",
        "",
        f"AR(1) parameters: `{result.parameters['ar1']}`.",
        f"Selected AR(p): `{selected_ar}`."
        if selected_ar
        else "No AR-order selection in this run.",
        "",
        "When 0 < phi < 1, OU is the exact continuous-time interpretation of the same AR(1) transition, so it is not counted as an independent competitor. Otherwise OU parameters are unavailable.",
        "",
        "Prediction intervals assume Gaussian innovations and ignore parameter and seasonal-cycle estimation uncertainty. Overlapping multi-day forecasts have dependent errors.",
        result.protocol.get(
            "skill_intervals", "No skill confidence intervals in this run."
        ),
        "Where supplied, block-bootstrap skill intervals are descriptive and depend on approximate stationarity and block length; they do not establish robust superiority across periods or marine boundaries.",
        "",
        "The default input region is a rectangular ocean-cell average, not a geographical Yellow Sea polygon. A study must decide the marine boundary, training/reference periods, trend treatment, and validation design before drawing conclusions.",
        "",
        "![Overview](overview.png)",
        "",
        "See protocol.json, parameters.json, metrics.csv, predictions.csv, and anomalies.csv for audit details.",
        result.protocol.get("provider_acknowledgment", ""),
    ]
    (output_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
