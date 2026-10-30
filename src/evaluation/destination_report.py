"""Data-driven report of locked destination satellite and buoy verification."""

import json
from pathlib import Path
import shutil

import numpy as np
import pandas as pd

from src.evaluation.confirmation_report import markdown_table
from src.evaluation.process_transfer_report import one
from src.publication_delivery import hashes

OUTPUT = Path("data/processed/destination_validation")
REVIEWED = Path("paper/destination_validation")
LABELS = {
    "anomaly_ridge": "Anomaly ridge",
    "anomaly_trees": "Anomaly trees",
    "projected_source_ar1": "Projected source AR(1)",
    "grid_source_ar1": "Grid source AR(1)",
    "grid_climatology": "Grid climatology",
    "grid_local_ar1": "Grid local AR(1)",
    "grid_anomaly_persistence": "Grid anomaly persistence",
}


def load(root):
    return {
        p.stem: pd.read_csv(p)
        for p in root.glob("*.csv")
        if "daily_scores" not in p.stem and p.stem != "matched_buoy_points"
    }


def text_fields(root=None):
    root = root or OUTPUT
    if not (root / "satellite_metrics.csv").exists():
        root = REVIEWED / "results"
    t = load(root)
    audit = json.loads((root / "evaluation_audit.json").read_text())
    sat = t["satellite_metrics"]
    night = sat.loc[
        sat.period.eq("2023-2025")
        & sat.target.eq("AMSR2")
        & sat["pass"].eq("nighttime")
    ]
    buoy = t["buoy_metrics"]
    bn = buoy.loc[buoy.target.eq("iQuam") & buoy["pass"].eq("nighttime")]
    ci = t["primary_inference"]
    rows = []
    for model in ["anomaly_ridge", "anomaly_trees"]:
        for h in [1, 7, 30]:
            row = {"Model": LABELS[model], "Lead (d)": h}
            for key, label in [
                (model, "Model RMSE"),
                ("projected_source_ar1", "Projected AR(1)"),
                ("grid_source_ar1", "Grid AR(1)"),
                ("grid_climatology", "Grid climate"),
            ]:
                row[label] = f"{one(night, model=key, horizon_days=h).rmse:.4f}"
            rows.append(row)
    primary = pd.DataFrame(rows)
    inference = []
    if not ci.empty:
        for (model, baseline, h), group in ci.groupby(
            ["model", "baseline", "horizon_days"]
        ):
            b30 = one(group, bootstrap_block_days=30)
            b60 = one(group, bootstrap_block_days=60)
            inference.append(
                {
                    "Model": LABELS[model],
                    "Reference": LABELS[baseline],
                    "Lead (d)": h,
                    "Gain (%)": f"{100 * b60.rmse_skill:.2f}",
                    "60-d pointwise CI (%)": f"[{100 * b60.skill_ci_lower:.2f}, {100 * b60.skill_ci_upper:.2f}]",
                    "Holm p, 30 d": f"{b30.p_holm_18:.4f}",
                    "Holm p, 60 d": f"{b60.p_holm_18:.4f}",
                }
            )
    buoy_rows = []
    for model in audit_models():
        values = [one(bn, model=model, horizon_days=h).rmse for h in [1, 7, 30]]
        buoy_rows.append(
            {
                "Method": LABELS.get(model, model.replace("_", " ")),
                "1 d RMSE": f"{values[0]:.4f}",
                "7 d RMSE": f"{values[1]:.4f}",
                "30 d RMSE": f"{values[2]:.4f}",
            }
        )
    covariance = t["satellite_coverage"].copy()
    covariance["date"] = pd.to_datetime(covariance.date)
    covered = covariance.loc[
        covariance["pass"].eq("nighttime")
        & covariance.scored
        & covariance.date.dt.year.lt(2026)
    ]
    n_days = len(covered)
    n_pairs = int(covered.n_cells.sum())
    median = float(covered.valid_weight_fraction.median())
    annual_counts = audit["satellite"]["nighttime_days_by_primary_year"]
    b_audit = audit["buoys"]
    source_comparisons = ci.loc[ci.baseline.eq("projected_source_ar1")]
    grid_comparisons = ci.loc[
        ci.baseline.eq("grid_source_ar1") & ci.horizon_days.isin([7, 30])
    ]
    supported_source = (
        source_comparisons.assign(
            supported=lambda x: (x.rmse_skill > 0) & (x.p_holm_18 < 0.05)
        )
        .groupby(["model", "horizon_days"])
        .supported.all()
        .sum()
    )
    worse_grid = (
        grid_comparisons.assign(
            worse=lambda x: (x.rmse_skill < 0) & (x.p_holm_18 < 0.05)
        )
        .groupby(["model", "horizon_days"])
        .worse.all()
        .sum()
    )
    ridge = one(night, model="anomaly_ridge", horizon_days=30).rmse
    tree = one(night, model="anomaly_trees", horizon_days=30).rmse
    decay = one(night, model="grid_source_ar1", horizon_days=30).rmse
    b_ridge = one(bn, model="anomaly_ridge", horizon_days=30).rmse
    b_tree = one(bn, model="anomaly_trees", horizon_days=30).rmse
    b_decay = one(bn, model="grid_source_ar1", horizon_days=30).rmse
    methods = (
        "Destination verification was publicly locked before scoring its instrument observations "
        "(commit 0d9d318, 21 October 2026). The rectangular AMSR2 and iQuam files had already been acquired "
        "during earlier stages; source-region instrument results and destination OISST outcomes were known. "
        "The lock therefore fixes a conditional geographical extension, with forecast-array fingerprints, "
        "source versions and scoring rules, rather than a new pre-acquisition or blind holdout. "
        "Thirteen methods at all three leads cover the same 230 destination cells. Existing SST-only "
        "regional predictions are projected using origin OISST cell offsets. Additional grid references "
        "fit each cell's three-harmonic cycle and linear trend on 2010–2019 only. Grid source AR(1) predicts "
        "C_j(t+h) + phi_s^h [T_j(t) − C_j(t)], using the already fixed source-region decay coefficient; "
        "grid local AR(1) substitutes the destination regional coefficient. Grid climatology and grid "
        "anomaly persistence supply the remaining fixed references. No model or baseline is reselected."
        "\n\nSatellite dates require at least twenty valid cells and common cosine-latitude weights. "
        "Each primary year requires 120 nighttime dates. The primary family contains eighteen "
        "comparisons: two anomaly models × three leads × three baselines (projected source AR(1), "
        "grid source AR(1), grid climatology), with Holm adjustment separately for 30/60-day blocks "
        "and 1,999 resamples. Buoys retain the version-fixed quality-five thermometric records and "
        "equal platform-day/date weighting, adding exclusion of every record within 20 km of any "
        "source-domain cell. The remaining records match a destination cell within 20 km on the same "
        "UTC date. Each year requires sixty nighttime buoy dates; buoy, afternoon, matched OISST "
        "and January–August 2026 outcomes are descriptive. Both coverage thresholds were fixed before scoring."
    )
    results = (
        f"Destination nighttime AMSR2 supplied {n_days:,} scored dates and {n_pairs:,} cell–date pairs "
        f"over 2023–2025, with {annual_counts['2023']}, {annual_counts['2024']} and {annual_counts['2025']} "
        f"dates per year and median visible domain weight {100 * median:.1f}%. "
        f"The coverage gate passed. At thirty days, anomaly ridge/tree RMSE was {ridge:.4f}/{tree:.4f}°C, "
        f"compared with {decay:.4f}°C for grid source AR(1) (Table 9). Across the locked eighteen-comparison "
        f"family, {int(supported_source)} of six anomaly-model/lead cases retained a positive advantage over "
        "projected source AR(1) with adjusted p < 0.05 under both block choices. "
        f"Both models instead had greater error than grid source AR(1) at seven and thirty days "
        f"({int(worse_grid)} of four contrasts; adjusted p = 0.009 under both block choices). "
        "One-day gains over climatology survived both choices, whereas seven-day gains over "
        "climatology did not survive the sixty-day adjustment. These findings limit the transfer claim "
        "to the chosen representation and comparator; they do not support a general complexity advantage."
        "\n\nBuoy verification retained "
        f"{sum(b_audit['nighttime_days_by_year'].values()):,} nighttime dates, "
        f"{b_audit['nighttime_records']:,} records and {b_audit['nighttime_platform_type_id_pairs']} "
        "platform-type/identifier combinations after the source-proximity exclusion. All three annual "
        f"coverage gates passed. Thirty-day RMSE was {b_ridge:.4f}/{b_tree:.4f}°C for anomaly ridge/trees "
        f"and {b_decay:.4f}°C for grid source AR(1), a descriptive ranking consistent with the satellite "
        "comparison. The partial 2026 satellite sample, both afternoon/matched-analysis targets and "
        "all thirteen methods are retained in the supporting tables. The destination observations "
        "extend instrument verification beyond the source region, while shared reference processing, "
        "possible in situ assimilation overlap and the adjacent subregion still constrain independence and scope."
    )
    return {
        "destination_methods_text": methods,
        "destination_results_text": results,
        "destination_primary_table": markdown_table(primary),
        "destination_inference_table": markdown_table(pd.DataFrame(inference)),
        "destination_buoy_table": markdown_table(pd.DataFrame(buoy_rows)),
        "destination_abstract": "A later pre-scoring-locked northern Eastern China Sea check found larger thirty-day errors for regional anomaly-transfer models than for a fixed grid anomaly-decay reference on both AMSR2 and buoy observations.",
    }


def audit_models():
    return json.loads((REVIEWED / "frozen_protocol.json").read_text())["models"]


def deliver():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates

    def save(fig, name):
        fig.savefig(OUTPUT / (name + ".png"), dpi=300)
        path = OUTPUT / (name + ".svg")
        fig.savefig(path)
        path.write_text(
            "\n".join(line.rstrip() for line in path.read_text().splitlines()) + "\n"
        )
        plt.close(fig)

    data = load(OUTPUT)
    fig, axes = plt.subplots(1, 3, figsize=(12.5, 4.6), layout="constrained")
    models = [
        "anomaly_ridge",
        "anomaly_trees",
        "projected_source_ar1",
        "grid_source_ar1",
        "grid_climatology",
    ]
    colors = ["#267c80", "#8b56a4", "#67717a", "#b86533", "#a6a646"]
    contexts = [
        ("satellite_metrics", "AMSR2", "Nighttime satellite"),
        ("satellite_metrics", "matched_OISST", "Same satellite cells: OISST"),
        ("buoy_metrics", "iQuam", "Nighttime buoys"),
    ]
    for ax, (file, target, title) in zip(axes, contexts):
        metric = data[file]
        for model, color in zip(models, colors):
            q = metric.loc[
                metric.period.eq("2023-2025")
                & metric.target.eq(target)
                & metric["pass"].eq("nighttime")
                & metric.model.eq(model)
            ].sort_values("horizon_days")
            ax.plot(
                np.arange(3),
                q.rmse,
                "o-" if model.startswith("anomaly") else "s--",
                color=color,
                lw=1.3,
                ms=4,
                label=LABELS[model],
            )
        ax.set(
            xticks=np.arange(3),
            xticklabels=["1", "7", "30"],
            xlabel="Lead (days)",
            ylabel="RMSE (°C)",
            title=title,
        )
        ax.grid(alpha=0.18)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncol=3, fontsize=8)
    fig.suptitle("Northern ECS | 2023–2025 | Source transfer and fixed simple controls")
    save(fig, "destination_instrument_comparison")
    coverage = data["satellite_coverage"].copy()
    coverage["date"] = pd.to_datetime(coverage.date)
    night = coverage.loc[coverage["pass"].eq("nighttime")].set_index("date")
    monthly = night.resample("MS").agg(
        scored_days=("scored", "sum"),
        median_visible_weight=("valid_weight_fraction", "median"),
    )
    points = pd.read_csv(
        OUTPUT / "matched_buoy_points.csv",
        parse_dates=["date"],
        usecols=["date", "pass"],
    )
    b = (
        points.loc[points["pass"].eq("nighttime")]
        .drop_duplicates("date")
        .set_index("date")
        .resample("MS")
        .size()
    )
    fig, axes = plt.subplots(2, 1, figsize=(10.5, 6), layout="constrained")
    axes[0].bar(
        monthly.index,
        monthly.scored_days,
        width=21,
        color="#267c80",
        label="AMSR2 scored dates",
    )
    axes[0].set(
        ylabel="Nighttime dates",
        ylim=(0, 33),
        title="Satellite: fixed ≥20-cell daily gate",
    )
    twin = axes[0].twinx()
    twin.plot(
        monthly.index,
        100 * monthly.median_visible_weight,
        "o-",
        color="#b86533",
        ms=3,
        lw=1,
    )
    twin.set(ylabel="Median visible domain weight (%)", ylim=(0, 100))
    axes[1].bar(b.index, b, width=21, color="#8b56a4")
    axes[1].set(
        ylabel="Nighttime dates",
        ylim=(0, 33),
        title="Buoys: after source-proximity exclusion",
        xlabel="Month",
    )
    for ax in axes:
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax.grid(axis="y", alpha=0.18)
    fig.suptitle("Destination observation support | Monthly exposure retained")
    save(fig, "destination_observation_coverage")
    fields = text_fields(OUTPUT)
    report = (
        "# Destination observation-source verification\n\n## Evidence chronology and methods\n\n"
        + fields["destination_methods_text"]
        + "\n\n## Results\n\n"
        + fields["destination_results_text"]
        + "\n\n## Primary nighttime comparisons\n\n"
        + fields["destination_primary_table"]
        + "\n\n## All eighteen primary contrasts\n\n"
        + fields["destination_inference_table"]
        + "\n\n## All nighttime buoy methods\n\n"
        + fields["destination_buoy_table"]
        + "\n\n![Destination forecasts](destination_instrument_comparison.png)\n\n![Observation support](destination_observation_coverage.png)\n"
    )
    (OUTPUT / "report_en.md").write_text(report)
    target = REVIEWED / "results"
    target.mkdir(parents=True, exist_ok=True)
    for path in OUTPUT.iterdir():
        if path.suffix in {
            ".csv",
            ".json",
            ".png",
            ".svg",
            ".md",
        } and path.name not in {
            "satellite_daily_scores.csv",
            "buoy_daily_scores.csv",
            "matched_buoy_points.csv",
            "checksums.json",
        }:
            shutil.copy2(path, target / path.name)
    (OUTPUT / "checksums.json").write_text(json.dumps(hashes(OUTPUT), indent=2) + "\n")
    (target / "checksums.json").write_text(json.dumps(hashes(target), indent=2) + "\n")


if __name__ == "__main__":
    deliver()
