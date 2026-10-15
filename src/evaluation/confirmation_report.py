"""Data-driven report and figures for the locked multi-year extension."""

import json

import numpy as np
import pandas as pd

from src.validation import sha256


LABELS = {
    "frozen_selected_projection": "Regional projection",
    "frozen_anomaly_projection": "Regional persistence projection",
    "grid_anomaly_persistence": "Grid anomaly persistence",
    "grid_raw_persistence": "Raw grid persistence",
    "eof_ar_increments": "EOF–AR",
    "eof_var_ridge": "EOF–VAR ridge",
    "eof_extra_trees": "EOF–ExtraTrees",
}
COLORS = {
    "grid_anomaly_persistence": "#414b56",
    "frozen_selected_projection": "#3274a1",
    "eof_ar_increments": "#d67d20",
    "eof_var_ridge": "#207c67",
    "eof_extra_trees": "#8b56a4",
}


def markdown_table(frame):
    """Render simple tables without an optional tabulate dependency."""

    def clean(value):
        return str(value).replace("|", "\\|").replace("\n", " ")

    rows = [frame.columns.tolist(), ["---"] * len(frame.columns)]
    rows.extend(frame.astype(object).values.tolist())
    return "\n".join("| " + " | ".join(map(clean, row)) + " |" for row in rows)


def relative_skill(frame, keys):
    """Pair each aggregate with persistence on the identical grouping support."""
    baseline = frame.loc[frame.model.eq("grid_anomaly_persistence"), keys + ["rmse"]]
    if baseline.duplicated(keys).any():
        raise ValueError("duplicate persistence comparison")
    paired = frame.merge(
        baseline.rename(columns={"rmse": "baseline_rmse"}),
        on=keys,
        how="left",
        validate="many_to_one",
    )
    if paired.baseline_rmse.isna().any() or (paired.baseline_rmse <= 0).any():
        raise ValueError("missing or degenerate persistence comparison")
    paired["skill_vs_grid_anomaly_persistence"] = 1 - paired.rmse / paired.baseline_rmse
    return paired


def write_report(tables, frozen, output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    def save(fig, name):
        fig.savefig(output / (name + ".png"), dpi=300)
        fig.savefig(output / (name + ".svg"))
        plt.close(fig)

    config = frozen["config"]
    metrics = tables["metrics"]
    infer = tables["primary_inference"]
    annual = relative_skill(
        tables["annual_metrics"], ["year", "target", "pass", "horizon_days"]
    )
    seasonal = relative_skill(
        tables["seasonal_metrics"],
        ["period", "season", "target", "pass", "horizon_days"],
    )
    annual.to_csv(output / "annual_skill.csv", index=False)
    seasonal.to_csv(output / "seasonal_skill.csv", index=False)
    contexts = [
        ("full_grid_OISST", "all", "Complete fixed grid: OISST"),
        ("matched_grid_OISST", "descending", "Nighttime matched cells: OISST"),
        ("matched_grid_AMSR2", "descending", "Same nighttime cells: AMSR2"),
        ("matched_grid_AMSR2", "ascending", "Afternoon matched cells: AMSR2"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(11.5, 8), layout="constrained")
    for i, (ax, (target, passage, title)) in enumerate(zip(axes.ravel(), contexts)):
        for model, color in COLORS.items():
            g = metrics.loc[
                metrics.period.eq("2023-2025")
                & metrics.target.eq(target)
                & metrics["pass"].eq(passage)
                & metrics.model.eq(model)
            ]
            g = g.sort_values("horizon_days")
            ax.plot(
                g.horizon_days, g.rmse, "o-", color=color, label=LABELS[model], lw=1.5
            )
        ax.set(
            title=f"({chr(97 + i)}) {title}",
            xlabel="Lead time (days)",
            ylabel="RMSE (°C)",
        )
        ax.set_xticks(config["horizons"])
        ax.grid(alpha=0.2)
    axes[0, 0].legend(fontsize=8)
    fig.suptitle("Locked forecasts across verification sources | Full years 2023–2025")
    save(fig, "multiyear_sources")

    fig, axes = plt.subplots(1, 3, figsize=(12, 4.6), layout="constrained")
    for ax, h in zip(axes, config["horizons"]):
        for model in config["primary_models"]:
            g = annual.loc[
                annual.year.lt(2026)
                & annual.target.eq("matched_grid_AMSR2")
                & annual["pass"].eq("descending")
                & annual.horizon_days.eq(h)
                & annual.model.eq(model)
            ].sort_values("year")
            ax.plot(
                g.year,
                100 * g.skill_vs_grid_anomaly_persistence,
                "o-",
                label=LABELS[model],
                color=COLORS[model],
            )
        ax.axhline(0, color="black", lw=0.7)
        ax.set(
            title=f"{h}-day lead",
            xticks=[2023, 2024, 2025],
            xlabel="Year",
            ylabel="RMSE skill versus grid persistence (%)",
        )
        ax.grid(alpha=0.2)
    axes[0].legend(fontsize=8)
    fig.suptitle("Nighttime AMSR2: annual consistency (descriptive)")
    save(fig, "annual_external_skill")

    point = metrics.loc[
        metrics.period.eq("2023-2025")
        & metrics.target.eq("matched_grid_AMSR2")
        & metrics["pass"].eq("descending")
    ]
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 5), layout="constrained")
    comparisons = [(m, h) for m in config["primary_models"] for h in config["horizons"]]
    labels = [f"{LABELS[m]}, {h} d" for m, h in comparisons]
    for ax, block in zip(axes, config["bootstrap_block_days"]):
        for y, (model, h) in enumerate(comparisons):
            row = infer.loc[
                infer.bootstrap_block_days.eq(block)
                & infer.model.eq(model)
                & infer.horizon_days.eq(h)
            ].iloc[0]
            estimate = point.loc[point.model.eq(model) & point.horizon_days.eq(h)].iloc[
                0
            ]
            ax.plot(
                100 * np.array([row.skill_ci_lower, row.skill_ci_upper]),
                [y, y],
                color=COLORS[model],
                lw=2,
            )
            ax.plot(
                100 * estimate.skill_vs_grid_anomaly_persistence,
                y,
                "o",
                color=COLORS[model],
            )
        ax.axvline(0, color="black", lw=0.8)
        ax.set(
            yticks=range(len(labels)),
            yticklabels=labels,
            xlabel="RMSE skill (%)",
            title=f"{block}-day calendar blocks",
        )
        ax.invert_yaxis()
        ax.grid(axis="x", alpha=0.2)
    fig.suptitle("Nighttime AMSR2, 2023–2025 | Pointwise paired 95% intervals")
    save(fig, "primary_external_intervals")

    coverage = tables["coverage"].copy()
    coverage["month"] = pd.DatetimeIndex(coverage.date).to_period("M").astype(str)
    coverage_rows = []
    for (month, passage), g in coverage.groupby(["month", "pass"]):
        coverage_rows.append(
            {
                "month": month,
                "pass": passage,
                "n_dates": len(g),
                "n_scored": int(g.scored.sum()),
                "median_weight_fraction": float(g.valid_weight_fraction.median()),
            }
        )
    monthly = pd.DataFrame(coverage_rows)
    monthly.to_csv(output / "monthly_coverage.csv", index=False)
    fig, axes = plt.subplots(2, 1, figsize=(12, 5.5), layout="constrained", sharex=True)
    for passage, label, color in [
        ("descending", "Nighttime", "#3274a1"),
        ("ascending", "Afternoon", "#d67d20"),
    ]:
        g = monthly.loc[monthly["pass"].eq(passage)].sort_values("month")
        axes[0].plot(
            g.month, 100 * g.n_scored / g.n_dates, ".-", color=color, label=label
        )
        axes[1].plot(g.month, 100 * g.median_weight_fraction, ".-", color=color)
    axes[0].set(ylabel="Scored dates (%)", ylim=(0, 105))
    axes[1].set(ylabel="Median domain weight (%)", ylim=(0, 100), xlabel="UTC month")
    for ax in axes:
        ax.grid(alpha=0.2)
    axes[0].legend()
    for i, label in enumerate(axes[1].get_xticklabels()):
        label.set_visible(i % 3 == 0)
        label.set_rotation(35)
        label.set_horizontalalignment("right")
    fig.suptitle(
        "External sampling coverage | Full years 2023–2025 and January–August 2026"
    )
    save(fig, "external_coverage_calendar")

    summary = point.loc[point.model.isin(config["primary_models"])].merge(
        infer, on=["model", "horizon_days"], validate="one_to_many"
    )
    display = pd.DataFrame(
        {
            "Model": summary.model.map(LABELS),
            "Lead (d)": summary.horizon_days,
            "RMSE (°C)": summary.rmse.map(lambda x: f"{x:.4f}"),
            "Skill (%)": summary.skill_vs_grid_anomaly_persistence.map(
                lambda x: f"{100 * x:.2f}"
            ),
            "Block (d)": summary.bootstrap_block_days,
            "95% skill interval (%)": [
                f"[{100 * a:.2f}, {100 * b:.2f}]"
                for a, b in zip(summary.skill_ci_lower, summary.skill_ci_upper)
            ],
            "Holm p (9 tests)": summary.p_holm_nine_comparisons.map(
                lambda x: f"{x:.4f}"
            ),
        }
    )
    annual_display = annual.loc[
        annual.year.lt(2026)
        & annual.target.eq("matched_grid_AMSR2")
        & annual["pass"].eq("descending")
        & annual.model.isin(config["primary_models"])
    ].copy()
    annual_display["Model"] = annual_display.model.map(LABELS)
    annual_display["Skill (%)"] = (
        100 * annual_display.skill_vs_grid_anomaly_persistence
    ).map(lambda x: f"{x:.2f}")
    annual_display["RMSE (°C)"] = annual_display.rmse.map(lambda x: f"{x:.4f}")
    text = f"""# Locked multi-year instrument extension and stronger spatial controls

## Design and chronology

Forecast and model bytes were locked in the protocol with SHA-256 `{sha256("paper/confirmation/frozen_protocol.json")}`. The public freeze commit is `6edc533f2cd5f7d0d6f61a0b441f6610cd54ebed`. Estimation uses 2010–2019, selection uses 2020–2021 and new AMSR2 targets cover three complete calendar years (2023–2025). Existing 2026 results are retained as a separate period. The previous OISST and 2026 AMSR2 outcomes were already viewed; this extension is conditional on that exploration. New targets do not establish an untouched OISST experiment.

The established rank-10 spatial basis and seasonal field are retained. Coupled ridge VAR coefficients and direct multi-output ExtraTrees increments are new controls. VAR orders 1/3/7 and penalties 0.0001/0.001/0.01/0.1, and six tree specifications (minimum leaf 5/20/50; feature fraction 0.5/1.0) are compared solely using selection-period seven-day full-grid loss. Each tree uses 200 trees, modal features at origin lags 0/1/6/13, known target calendar harmonics and elapsed time. Horizon-specific targets end within the estimation period. Target increments are standardized on training data alone. No atmospheric drivers or numerical ocean forecasts are included, so these controls cannot establish superiority to the broader forecasting literature.

The primary endpoint is nighttime AMSR2 RMSE on common dates and cells, relative to grid-specific anomaly persistence. Nine comparisons comprise three spatial models and three horizons. Paired calendar-block intervals use 1,999 replicates with 30- and 60-day blocks; centered two-sided tests receive Holm adjustment within the nine-test family separately for each block choice. Intervals are pointwise, not simultaneous; a positive interval can coexist with an adjusted p value exceeding 0.05. Approximate stationary-loss assumptions remain. Annual, seasonal and afternoon tables are descriptive. No post-score model changes or bias adjustments are permitted.

## Primary results

{markdown_table(display)}

![Common-source comparison](multiyear_sources.png)

![Paired uncertainty](primary_external_intervals.png)

## Annual consistency

{markdown_table(annual_display[["year", "Model", "horizon_days", "n_days", "RMSE (°C)", "Skill (%)"]])}

![Annual skill](annual_external_skill.png)

![Sampling coverage](external_coverage_calendar.png)

## Interpretation and reproducibility

Positive relative skill indicates lower RMSE against the sampled instrument; it does not identify true SST. RSS calibration uses reference SST information. Microwave quality screening samples only part of the fixed domain, and UTC-date matching does not match observation time or footprint. Report the matched OISST and AMSR2 errors together when interpreting model ranking. The exact loss decomposition is checked on every scored date, and the original 2026 frozen forecast scores are replicated within the documented floating-point tolerance.

The CSV files preserve all daily paired losses, annual and seasonal scores, sampling coverage, source provenance, model selections and adjusted inference. The forecasts and model serialization are protected by the pre-acquisition hashes. The findings strengthen the evidence base but do not by themselves establish a physical mechanism, regional generalization, statistically independent latent truth or suitability for a specific journal tier.
"""
    (output / "report_en.md").write_text(text)
    (output / "figure_manifest.json").write_text(
        json.dumps({p.name: sha256(p) for p in sorted(output.glob("*.png"))}, indent=2)
        + "\n"
    )
