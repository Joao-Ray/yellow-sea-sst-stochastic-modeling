"""Report finite-grid and climatology-assisted transfer sensitivities."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.evaluation.confirmation_report import markdown_table
from src.evaluation.process_transfer_report import one
from src.publication_delivery import hashes


def tables(root):
    metrics = pd.read_csv(root / "metrics.csv")
    benchmarks = pd.read_csv(root / "benchmark_metrics.csv")
    intervals = pd.read_csv(root / "decay_reference_intervals.csv")
    rows = []
    for period in ["2023-2025", "2026-Jan-Aug"]:
        for family in ["ridge", "trees"]:
            for h in [1, 7, 30]:
                ref = dict(
                    period=period,
                    family=family,
                    group="sst",
                    horizon_days=h,
                    domain="northern_ecs",
                    fitting="source_transfer",
                )
                raw = one(metrics, **ref, representation="raw")
                anomaly = one(metrics, **ref, representation="seasonal_anomaly")
                b = dict(period=period, horizon_days=h, domain="northern_ecs")
                local = one(benchmarks, **b, model="local_anomaly_ar1")
                source = one(benchmarks, **b, model="source_anomaly_ar1_transfer")
                climate = one(benchmarks, **b, model="training_climatology")
                ci = one(
                    intervals,
                    period=period,
                    family=family,
                    group="sst",
                    horizon_days=h,
                    bootstrap_block_days=60,
                )
                rows.append(
                    {
                        "Period": period,
                        "Family": family,
                        "Lead (d)": h,
                        "Raw transfer": f"{raw.rmse:.4f}",
                        "Anomaly transfer": f"{anomaly.rmse:.4f}",
                        "Local AR(1)": f"{local.rmse:.4f}",
                        "Source AR(1) transfer": f"{source.rmse:.4f}",
                        "Climatology": f"{climate.rmse:.4f}",
                        "Gain vs local AR(1) (%)": f"{100 * ci.skill:.2f}",
                        "60-d pointwise CI (%)": f"[{100 * ci.skill_ci_lower:.2f}, {100 * ci.skill_ci_upper:.2f}]",
                    }
                )
    return metrics, benchmarks, pd.DataFrame(rows)


def text_fields(root=None):
    root = root or Path("data/processed/anomaly_transfer")
    if not (root / "metrics.csv").exists():
        root = Path("paper/anomaly_transfer/results")
    metrics, benchmarks, transfer = tables(root)
    selection = pd.read_csv(root / "selection.csv")
    chosen = selection.loc[selection.selected].copy()
    chosen["Lower edge"] = [
        bool(
            r.hyperparameter
            == selection.loc[selection.family.eq(r.family), "hyperparameter"].min()
        )
        for _, r in chosen.iterrows()
    ]
    chosen["Upper edge"] = chosen.selected_at_maximum_grid_value
    chosen["Value"] = chosen.hyperparameter.map(lambda v: f"{v:g}")
    for src, dest in [
        ("rmse", "Pooled RMSE"),
        ("rmse_2020", "2020 RMSE"),
        ("rmse_2021", "2021 RMSE"),
    ]:
        chosen[dest] = chosen[src].map(lambda v: f"{v:.4f}")
    selection_table = chosen[
        [
            "representation",
            "family",
            "group",
            "Value",
            "2020 RMSE",
            "2021 RMSE",
            "Pooled RMSE",
            "Lower edge",
            "Upper edge",
        ]
    ]
    refs = dict(
        period="2023-2025",
        domain="northern_ecs",
        fitting="source_transfer",
        group="sst",
        horizon_days=30,
    )
    r = one(metrics, **refs, representation="seasonal_anomaly", family="ridge")
    t = one(metrics, **refs, representation="seasonal_anomaly", family="trees")
    ar = one(
        benchmarks,
        period="2023-2025",
        domain="northern_ecs",
        horizon_days=30,
        model="source_anomaly_ar1_transfer",
    )
    base = one(
        metrics,
        period="2023-2025",
        domain="northern_ecs",
        horizon_days=30,
        fitting="baseline",
        family="local_anomaly_persistence",
    )
    audit = json.loads((root / "benchmark_audit.json").read_text())
    phi_s = audit["training_phi_and_pair_count"]["yellow_bohai"][0]
    phi_d = audit["training_phi_and_pair_count"]["northern_ecs"][0]
    partial = {
        family: one(
            metrics,
            period="2026-Jan-Aug",
            domain="northern_ecs",
            fitting="source_transfer",
            representation="seasonal_anomaly",
            family=family,
            group="sst",
            horizon_days=30,
        ).rmse
        for family in ["ridge", "trees"]
    }
    partial_b = {
        model: one(
            benchmarks,
            period="2026-Jan-Aug",
            domain="northern_ecs",
            model=model,
            horizon_days=30,
        ).rmse
        for model in [
            "local_anomaly_ar1",
            "source_anomaly_ar1_transfer",
            "training_climatology",
        ]
    }
    external = pd.read_csv(root / "external_metrics.csv")
    external_b = pd.read_csv(root / "external_benchmark_metrics.csv")
    sat, sat_b = {}, {}
    for period in ["2023-2025", "2026-Jan-Aug"]:
        sat[period] = one(
            external,
            period=period,
            target="AMSR2_night",
            representation="seasonal_anomaly",
            family="trees",
            group="sst",
            horizon_days=30,
        ).rmse
        sat_b[period] = one(
            external_b,
            period=period,
            target="AMSR2_night",
            model="training_climatology",
            horizon_days=30,
        ).rmse
    text = (
        "Expanding the source-selection grids removes every upper-edge choice: "
        f"{int(chosen['Upper edge'].sum())} of twelve selected configurations remain at the expanded upper limit. "
        "The raw ridge penalty remains 10 in all groups, while raw trees select a minimum leaf size of 100 "
        "instead of the earlier maximum of 50. One anomaly-tree configuration (heat/wind) selects the lower "
        "edge of five, so finite-candidate sensitivity is not eliminated. Original narrow-grid selection RMSEs "
        "reproduce exactly. Neither expanded grid nor representation is selected by destination outcomes; "
        "both representations and all source-selected configurations are retained (Supplementary Table S16)."
        "\n\nRemoving each region's training seasonal cycle/trend and scaling its anomalies markedly reduces "
        "the large raw-transfer penalty. In 2023–2025 the thirty-day SST-only destination RMSE is "
        f"{r.rmse:.4f}°C for ridge and {t.rmse:.4f}°C for regional trees, compared with "
        f"{base.rmse:.4f}°C for local anomaly persistence. However, the transferred one-parameter "
        f"source AR(1) gives {ar.rmse:.4f}°C, slightly better than either complex model. "
        "This comparison supports a climatology-assisted anomaly-memory reference, without establishing "
        "a nonlinear or multifeature transfer advantage. The normalization change and model selection "
        "change are joint statistical interventions and do not identify a physical cause."
        "\n\nThe partial-year check is less favourable to complexity. In January–August 2026, thirty-day "
        f"destination RMSE is {partial['ridge']:.4f}°C for ridge and {partial['trees']:.4f}°C for trees, versus "
        f"{partial_b['local_anomaly_ar1']:.4f}°C for local AR(1), "
        f"{partial_b['source_anomaly_ar1_transfer']:.4f}°C for source AR(1) transfer and "
        f"{partial_b['training_climatology']:.4f}°C for training climatology alone. "
        "Thus a three-complete-year reduction relative to non-decaying persistence does not imply a "
        "uniform gain over simple decay or climatology across periods. Figure 7 and Supplementary "
        "Table S17 retain both periods, families and all horizons."
        "\n\nOn the source region's same nighttime AMSR2 support, the thirty-day SST-only anomaly-tree "
        f"projection has RMSE {sat['2023-2025']:.4f}°C in 2023–2025 and {sat['2026-Jan-Aug']:.4f}°C in January–August 2026. "
        f"Projected training climatology gives {sat_b['2023-2025']:.4f}°C and {sat_b['2026-Jan-Aug']:.4f}°C, respectively. These new regional-increment "
        "models do not improve on that simple thirty-day reference in either period. They are distinct from "
        "the previously locked EOF-based spatial tree control, whose three-year RMSE remains 1.9387°C. "
        "New satellite scores are descriptive reuses of viewed observations, not a new independent test."
    )
    methods = (
        "Following inspection of the raw-transfer failures and candidate-boundary choices, we added an "
        "explicitly retrospective sensitivity. Ridge penalties span 0.01–1,000,000 (nine logarithmic values) "
        "and minimum tree leaf sizes are 5, 20, 50, 100, 200, 400 and 800 (200 trees). Each representation, "
        "family and feature group is selected only by source seven-day RMSE over 2020–2021, retaining all "
        "choices for evaluation at 1, 7 and 30 days. All fits end in 2019. Raw-feature models retain the "
        "original feature definitions and random seed, permitting exact selection-score checks at the old candidates."
        "\n\nFor the second representation, a regional three-harmonic seasonal cycle with linear trend C_r(t) "
        "and residual standard deviation sigma_r are estimated on 2010–2019 alone. SST state is "
        "a_r(t) = [T_r(t) − C_r(t)] / sigma_r. Models predict a_r(t+h)−a_r(t), using the same lag/calendar "
        "layout; weather drivers are likewise normalized by their own regional training cycle and residual "
        "scale before delayed trailing windows are formed. Transfer keeps the source increment predictor "
        "and source feature scaler, and decodes C_d(t+h)+sigma_d[a_d(t)+u_s(X_d)]. The destination "
        "seasonal/trend coefficients and scales require destination 2010–2019 history. This is "
        "climatology-assisted transfer, not a data-free or zero-shot forecast. Origin SST histories are also local."
        "\n\nFixed descriptive references are training climatology alone and no-intercept AR(1) decay: "
        "C_d(t+h)+sigma_d phi^h a_d(t), with phi fitted by least squares on consecutive training anomalies "
        f"only. Source and destination phi are {phi_s:.6f} and {phi_d:.6f}; each uses 3,651 training pairs. "
        "We report both destination phi and unchanged source phi, and reject rather than clip unstable "
        "training coefficients. No decay value is chosen using validation or test scores. Pointwise "
        "paired 30/60-day block intervals (1,999 resamples) are descriptive; no new p values or confirmatory "
        "family is introduced. Neither this expansion nor its simple controls convert previously viewed "
        "outcomes into an untouched holdout."
    )
    return {
        "anomaly_methods_text": methods,
        "anomaly_results_text": text,
        "anomaly_transfer_table": markdown_table(
            transfer.loc[transfer.Period.eq("2023-2025")].drop(
                columns=[
                    "Period",
                    "Climatology",
                    "Gain vs local AR(1) (%)",
                    "60-d pointwise CI (%)",
                ]
            )
        ),
        "anomaly_transfer_full_table": markdown_table(
            transfer.drop(columns=["Climatology"])
        ),
        "anomaly_selection_table": markdown_table(selection_table),
    }


def write_report(output, cfg):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    def save(fig, name):
        fig.savefig(output / (name + ".png"), dpi=300)
        svg = output / (name + ".svg")
        fig.savefig(svg)
        svg.write_text(
            "\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n"
        )
        plt.close(fig)

    metrics, benchmarks, transfer = tables(output)
    transfer.to_csv(output / "transfer_summary.csv", index=False)
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.2), layout="constrained")
    styles = [
        ("Raw source transfer", "#b86533", "o-"),
        ("Climatology-assisted anomaly transfer", "#267c80", "s-"),
        ("Local AR(1)", "#8173a4", "^--"),
        ("Source AR(1) transfer", "#444b56", "v--"),
        ("Training climatology", "#a6a646", "d:"),
    ]
    for row, family in enumerate(["ridge", "trees"]):
        for col, period in enumerate(["2023-2025", "2026-Jan-Aug"]):
            ax = axes[row, col]
            for i, (label, color, fmt) in enumerate(styles):
                if i < 2:
                    q = metrics.loc[
                        metrics.domain.eq("northern_ecs")
                        & metrics.fitting.eq("source_transfer")
                        & metrics.period.eq(period)
                        & metrics.family.eq(family)
                        & metrics.group.eq("sst")
                        & metrics.representation.eq(["raw", "seasonal_anomaly"][i])
                    ]
                else:
                    model = [
                        "local_anomaly_ar1",
                        "source_anomaly_ar1_transfer",
                        "training_climatology",
                    ][i - 2]
                    q = benchmarks.loc[
                        benchmarks.domain.eq("northern_ecs")
                        & benchmarks.period.eq(period)
                        & benchmarks.model.eq(model)
                    ]
                q = q.sort_values("horizon_days")
                ax.plot(
                    np.arange(3), q.rmse, fmt, color=color, lw=1.3, ms=4, label=label
                )
            ax.set(
                xticks=np.arange(3),
                xticklabels=["1", "7", "30"],
                xlabel="Lead (days)",
                ylabel="Northern ECS RMSE (°C)",
                title=f"{family.title()} | {period}",
            )
            ax.grid(alpha=0.18)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncol=3, fontsize=8)
    fig.suptitle(
        "SST-only transfer and fixed simple controls | Retrospective sensitivity"
    )
    save(fig, "anomaly_transfer_controls")

    selection = pd.read_csv(output / "selection.csv")
    fig, axes = plt.subplots(2, 3, figsize=(12, 6.8), layout="constrained")
    for row, family in enumerate(["ridge", "trees"]):
        for col, group in enumerate(cfg["feature_groups"]):
            ax = axes[row, col]
            for rep, color in [("raw", "#b86533"), ("seasonal_anomaly", "#267c80")]:
                q = selection.loc[
                    selection.family.eq(family)
                    & selection.group.eq(group)
                    & selection.representation.eq(rep)
                ].sort_values("hyperparameter")
                ax.plot(
                    q.hyperparameter,
                    q.rmse,
                    "o-",
                    color=color,
                    ms=3,
                    label=rep.replace("_", " "),
                )
                chosen = q.loc[q.selected]
                ax.scatter(
                    chosen.hyperparameter,
                    chosen.rmse,
                    marker="*",
                    s=100,
                    color=color,
                    edgecolors="black",
                    linewidths=0.5,
                    zorder=4,
                )
            ax.axvline(
                10 if family == "ridge" else 50, color="#7a8084", linestyle=":", lw=1
            )
            ax.set(
                xscale="log",
                xlabel="Ridge penalty" if family == "ridge" else "Minimum leaf size",
                ylabel="Source 7-day selection RMSE (°C)",
                title=f"{family.title()} | {group}",
            )
            ax.grid(alpha=0.18)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncol=2, fontsize=9)
    fig.suptitle(
        "Source validation only: 2020–2021 | Stars: selected; dotted: old upper limit"
    )
    save(fig, "expanded_source_selection")
    fields = text_fields(output)
    report = (
        "# Climatology-assisted anomaly transfer and simple controls\n\n## Evidence status\n\n"
        + cfg["scope"]
        + "\n\n## Methods\n\n"
        + fields["anomaly_methods_text"]
        + "\n\n## Results\n\n"
        + fields["anomaly_results_text"]
        + "\n\n## All SST-only comparisons\n\n"
        + fields["anomaly_transfer_full_table"]
        + "\n\n## Complete source selection\n\n"
        + fields["anomaly_selection_table"]
        + "\n\n![Transfer controls](anomaly_transfer_controls.png)\n\n![Source selection](expanded_source_selection.png)\n"
    )
    (output / "report_en.md").write_text(report)
    (output / "checksums.json").write_text(json.dumps(hashes(output), indent=2) + "\n")
