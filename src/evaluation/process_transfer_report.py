"""Data-driven, explicitly exploratory forcing and geographical-transfer report."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.evaluation.confirmation_report import markdown_table
from src.models.process_transfer import heat_into_ocean
from src.publication_delivery import hashes

DOMAINS = {"yellow_bohai": "Yellow–Bohai", "northern_ecs": "Northern Eastern China Sea"}
GROUPS = {
    "sst": "SST only",
    "sst_heat": "SST + heat",
    "sst_heat_wind": "SST + heat + wind",
}


def one(frame, **conditions):
    mask = pd.Series(True, index=frame.index)
    for key, value in conditions.items():
        mask &= frame[key].eq(value)
    selected = frame.loc[mask]
    if len(selected) != 1:
        raise ValueError(
            f"expected exactly one result: {conditions}, got {len(selected)}"
        )
    return selected.iloc[0]


def tables(root):
    metrics = pd.read_csv(root / "metrics.csv")
    baselines = metrics.loc[
        metrics.family.eq("local_anomaly_persistence"),
        ["domain", "period", "horizon_days", "rmse"],
    ].rename(columns={"rmse": "baseline_rmse"})
    skill = metrics.merge(
        baselines, on=["domain", "period", "horizon_days"], validate="many_to_one"
    )
    skill["skill_vs_local_anomaly_persistence"] = 1 - skill.rmse / skill.baseline_rmse
    transfer = []
    for period in ["2023-2025", "2026-Jan-Aug"]:
        for family in ["ridge", "trees"]:
            for h in [1, 7, 30]:
                ref = dict(period=period, family=family, group="sst", horizon_days=h)
                source = one(
                    metrics, **ref, domain="yellow_bohai", fitting="source_local"
                )
                transported = one(
                    metrics, **ref, domain="northern_ecs", fitting="source_transfer"
                )
                local = one(
                    metrics, **ref, domain="northern_ecs", fitting="destination_local"
                )
                base = one(
                    metrics,
                    period=period,
                    domain="northern_ecs",
                    horizon_days=h,
                    fitting="baseline",
                    family="local_anomaly_persistence",
                )
                transfer.append(
                    {
                        "Period": period,
                        "Family": family,
                        "Lead (d)": h,
                        "Source RMSE": f"{source.rmse:.4f}",
                        "Transfer RMSE": f"{transported.rmse:.4f}",
                        "Local-fit RMSE": f"{local.rmse:.4f}",
                        "Local persistence RMSE": f"{base.rmse:.4f}",
                        "Transfer skill (%)": f"{100 * (1 - transported.rmse / base.rmse):.2f}",
                    }
                )
    return metrics, skill, pd.DataFrame(transfer)


def text_fields(root=None):
    root = root or Path("data/processed/process_transfer")
    if not (root / "metrics.csv").exists():
        root = Path("paper/process_transfer/results")
    metrics, _, transfer = tables(root)
    inference = pd.read_csv(root / "forcing_inference.csv")
    source = inference.loc[
        inference.domain.eq("yellow_bohai") & inference.bootstrap_block_days.eq(60)
    ]
    both = (
        inference.assign(
            supported=lambda x: (x.p_holm_36.lt(0.05) & x.rmse_skill.gt(0))
        )
        .groupby(["domain", "fitting", "family", "group", "horizon_days"])
        .supported.all()
    )
    source_both = both.loc["yellow_bohai"]
    support_sentence = (
        "No source contrast retains a positive gain and a Holm-adjusted p value below 0.05"
        if source_both.sum() == 0
        else f"{int(source_both.sum())} source contrasts retain a positive gain and a Holm-adjusted p value below 0.05"
    )
    text = (
        f"The forcing ablation uses all 1,096 dates in 2023–2025. Across the twelve Yellow–Bohai "
        f"family/group/horizon contrasts, {int(source.rmse_skill.gt(0).sum())} have a positive point estimate, "
        f"with RMSE changes relative to matched SST-only controls ranging from "
        f"{100 * source.rmse_skill.min():.2f}% to {100 * source.rmse_skill.max():.2f}% "
        f"(positive denotes improvement). {support_sentence} under both block lengths in the full "
        f"36-comparison exploratory family. The adjustment does not erase the prior viewing of outcomes; "
        f"these are conditional exploratory diagnostics, not new confirmatory discoveries."
    )
    text += (
        "\n\nTransfer is evaluated on 230 fixed ocean cells in the northern Eastern China Sea "
        "(cell centres 31.125–33.125°N, 120.875–127.875°E), distinct from the 651 source cells. "
        "Source coefficients, feature definitions and scaling are copied unchanged. Destination-local "
        "fits use destination 2010–2019 observations but the same source-selected hyperparameters; "
        "they are references rather than destination-optimized upper bounds. Table 7 retains both "
        "families and all leads, including deterioration relative to destination-local anomaly persistence. "
        "January–August 2026 SST-only results are reported separately in the supplement. "
        "The subregion is contiguous with the source shelf and does not establish transfer to "
        "the full Eastern China Sea or a distant dynamical regime."
    )
    alignment_file = root / "alignment_metrics.csv"
    alignment_table = ""
    if alignment_file.exists():
        aligned = pd.read_csv(alignment_file)
        rows = []
        for period in ["2023-2025", "2026-Jan-Aug"]:
            for family in ["ridge", "trees"]:
                for h in [1, 7, 30]:
                    r = one(
                        aligned,
                        period=period,
                        family=family,
                        group="sst",
                        horizon_days=h,
                    )
                    raw = one(
                        metrics,
                        period=period,
                        family=family,
                        group="sst",
                        horizon_days=h,
                        domain="northern_ecs",
                        fitting="source_transfer",
                    )
                    local = one(
                        metrics,
                        period=period,
                        family=family,
                        group="sst",
                        horizon_days=h,
                        domain="northern_ecs",
                        fitting="destination_local",
                    )
                    base = one(
                        metrics,
                        period=period,
                        family="local_anomaly_persistence",
                        horizon_days=h,
                        domain="northern_ecs",
                        fitting="baseline",
                    )
                    rows.append(
                        {
                            "Period": period,
                            "Family": family,
                            "Lead (d)": h,
                            "Raw transfer RMSE": f"{raw.rmse:.4f}",
                            "Training-calibrated RMSE": f"{r.rmse:.4f}",
                            "Local-fit RMSE": f"{local.rmse:.4f}",
                            "Local persistence RMSE": f"{base.rmse:.4f}",
                        }
                    )
        alignment_table = markdown_table(pd.DataFrame(rows))
        worse = sum(
            one(
                aligned, period="2023-2025", family=family, group="sst", horizon_days=h
            ).rmse
            > one(
                metrics,
                period="2023-2025",
                family="local_anomaly_persistence",
                horizon_days=h,
                domain="northern_ecs",
                fitting="baseline",
            ).rmse
            for family in ["ridge", "trees"]
            for h in [1, 7, 30]
        )
        text += (
            "\n\nAfter the raw transfer failures were inspected, a further descriptive reference calibrated "
            "destination feature and increment location/scale from 2010–2019 alone, retaining source "
            "regression/tree coefficients. This uses destination training histories and is distinct from "
            "unchanged-scaler transfer. At thirty days in 2023–2025, calibrated SST-only RMSE is "
            f"{one(aligned, period='2023-2025', family='ridge', group='sst', horizon_days=30).rmse:.4f}°C for ridge and "
            f"{one(aligned, period='2023-2025', family='trees', group='sst', horizon_days=30).rmse:.4f}°C for trees. "
            f"The large raw-transfer penalty is reduced, but {'all six' if worse == 6 else str(worse) + ' of six'} calibrated SST-only family/lead "
            "point estimates remain worse than local anomaly persistence in these three years. "
            "Joint calibration does not identify which distributional component or physical process "
            "causes the remaining gap. No new significance test or model selection is attached."
        )
    external_text = ""
    external_file = root / "external_metrics.csv"
    if external_file.exists():
        external = pd.read_csv(external_file)
        comparisons = []
        for family in ["ridge", "trees"]:
            for h in [1, 7, 30]:
                base = one(
                    external,
                    target="AMSR2_night",
                    family=family,
                    group="sst",
                    horizon_days=h,
                )
                for group in ["sst_heat", "sst_heat_wind"]:
                    r = one(
                        external,
                        target="AMSR2_night",
                        family=family,
                        group=group,
                        horizon_days=h,
                    )
                    comparisons.append(1 - r.rmse / base.rmse)
        external_text = (
            f"A further descriptive diagnostic projects every source-region forecast onto the "
            f"origin OISST spatial offsets and evaluates the same {int(external.n_days.min()):,} "
            f"nighttime AMSR2 dates. Across all twelve forcing-versus-SST-only contrasts, "
            f"point-estimated gains range from {100 * min(comparisons):.2f}% to {100 * max(comparisons):.2f}%; "
            f"{sum(x > 0 for x in comparisons)} of the twelve estimates are positive. "
            f"No additional fitting, selection or significance claim is made. These regional-increment "
            f"projections are distinct from the previously locked nonlinear spatial model."
        )
        text += "\n\n" + external_text
    display = source.copy()
    display["Gain (%)"] = (100 * display.rmse_skill).map(lambda x: f"{x:.2f}")
    display["60-d pointwise CI (%)"] = [
        f"[{100 * a:.2f}, {100 * b:.2f}]"
        for a, b in zip(display.skill_ci_lower, display.skill_ci_upper)
    ]
    display["Holm p (36)"] = display.p_holm_36.map(lambda x: f"{x:.4f}")
    display = display[
        [
            "family",
            "group",
            "horizon_days",
            "Gain (%)",
            "60-d pointwise CI (%)",
            "Holm p (36)",
        ]
    ]
    return {
        "process_results_text": text,
        "process_transfer_table": markdown_table(
            transfer.loc[transfer.Period.eq("2023-2025")].drop(columns="Period")
        ),
        "process_transfer_full_table": markdown_table(transfer),
        "process_forcing_table": markdown_table(display),
        "process_external_text": external_text,
        "process_alignment_table": alignment_table,
    }


def write_report(output, cfg):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from shapely.geometry import shape

    def save(fig, name):
        fig.savefig(output / (name + ".png"), dpi=300)
        fig.savefig(output / (name + ".svg"))
        plt.close(fig)

    metrics, skill, transfer = tables(output)
    alignment_file = output / "alignment_metrics.csv"
    aligned = pd.read_csv(alignment_file) if alignment_file.exists() else None
    skill.to_csv(output / "skill.csv", index=False)
    transfer.to_csv(output / "transfer_summary.csv", index=False)
    inf = pd.read_csv(output / "forcing_inference.csv")
    contexts = [
        ("yellow_bohai", "source_local", "Yellow–Bohai: source fit"),
        ("northern_ecs", "source_transfer", "Northern ECS: source transfer"),
        ("northern_ecs", "destination_local", "Northern ECS: local fit"),
    ]
    colors = {"sst_heat": "#ac6622", "sst_heat_wind": "#267c80"}
    fig, axes = plt.subplots(1, 3, figsize=(12.5, 4.3), layout="constrained")
    for ax, (domain, fitting, title) in zip(axes, contexts):
        for family, style, offset in [("ridge", "o-", -0.14), ("trees", "s--", 0.14)]:
            for group, shift in [("sst_heat", -0.04), ("sst_heat_wind", 0.04)]:
                q = inf.loc[
                    inf.domain.eq(domain)
                    & inf.fitting.eq(fitting)
                    & inf.family.eq(family)
                    & inf.group.eq(group)
                    & inf.bootstrap_block_days.eq(60)
                ].sort_values("horizon_days")
                x = np.arange(3) + offset + shift
                ax.plot(
                    x,
                    100 * q.rmse_skill,
                    style,
                    color=colors[group],
                    ms=4,
                    lw=1.1,
                    label=f"{family}: {GROUPS[group].replace('SST + ', '')}",
                )
                for pos, (_, r) in zip(x, q.iterrows()):
                    ax.plot(
                        [pos, pos],
                        100 * np.array([r.skill_ci_lower, r.skill_ci_upper]),
                        color=colors[group],
                        lw=0.8,
                        alpha=0.8,
                    )
        ax.axhline(0, color="black", lw=0.7)
        ax.set(
            xticks=np.arange(3),
            xticklabels=["1", "7", "30"],
            xlabel="Lead (days)",
            ylabel="RMSE gain vs matched SST-only (%)",
            title=title,
        )
        ax.grid(alpha=0.18)
    axes[0].legend(fontsize=7, loc="best")
    fig.suptitle(
        "Past-forcing ablations | 2023–2025 | Exploratory, 60-day pointwise intervals"
    )
    save(fig, "past_forcing_ablation")

    fig, axes = plt.subplots(1, 3, figsize=(12.5, 4.3), layout="constrained")
    for ax, h in zip(axes, [1, 7, 30]):
        q = metrics.loc[
            metrics.period.eq("2023-2025")
            & metrics.horizon_days.eq(h)
            & metrics.domain.eq("northern_ecs")
        ]
        for fitting, style, color in [
            ("source_transfer", "o-", "#b86533"),
            ("destination_local", "s--", "#2e7888"),
        ]:
            for family, shift in [("ridge", -0.08), ("trees", 0.08)]:
                r = (
                    q.loc[q.fitting.eq(fitting) & q.family.eq(family)]
                    .set_index("group")
                    .loc[cfg["feature_groups"]]
                )
                ax.plot(
                    np.arange(3) + shift,
                    r.rmse,
                    style,
                    color=color,
                    lw=1.2,
                    alpha=0.95 if family == "trees" else 0.5,
                    label=f"{fitting.replace('_', ' ')}: {family}",
                )
        if aligned is not None:
            for family, shift in [("ridge", -0.08), ("trees", 0.08)]:
                r = (
                    aligned.loc[
                        aligned.period.eq("2023-2025")
                        & aligned.horizon_days.eq(h)
                        & aligned.family.eq(family)
                    ]
                    .set_index("group")
                    .loc[cfg["feature_groups"]]
                )
                ax.plot(
                    np.arange(3) + shift,
                    r.rmse,
                    "^-.",
                    color="#8a629d",
                    lw=1.2,
                    alpha=0.95 if family == "trees" else 0.5,
                    label=f"Training-calibrated: {family}",
                )
        base = one(q, family="local_anomaly_persistence").rmse
        ax.axhline(base, color="#414b56", lw=1, label="Local anomaly persistence")
        ax.set(
            xticks=np.arange(3),
            xticklabels=["SST", "+ Heat", "+ Heat/wind"],
            ylabel="Northern ECS RMSE (°C)",
            title=f"{h}-day lead",
        )
        ax.grid(alpha=0.18)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside lower center", ncol=4, fontsize=7)
    fig.suptitle(
        "Source transfer, training calibration and destination-local fitting | 2023–2025"
    )
    save(fig, "regional_transfer")

    fig, axes = plt.subplots(1, 3, figsize=(12.5, 4.6), layout="constrained")
    with np.load(output / "domains.npz") as d:
        for domain, color in [("yellow_bohai", "#bc943c"), ("northern_ecs", "#2e7888")]:
            axes[0].scatter(
                d[domain + "__lon"],
                d[domain + "__lat"],
                s=3,
                c=color,
                label=f"{DOMAINS[domain]} ({len(d[domain + '__lat'])})",
            )
    for path, label in [
        (Path("data/raw/boundaries/yellow_sea_iho.geojson"), "source"),
        (Path("data/raw/processes/east_china_sea_iho.geojson"), "destination"),
    ]:
        geom = shape(json.loads(path.read_text())["features"][0]["geometry"])
        for p in geom.geoms if geom.geom_type == "MultiPolygon" else [geom]:
            xx, yy = p.exterior.xy
            axes[0].plot(xx, yy, color="#7a8084", lw=0.6)
    axes[0].set(
        xlim=(117, 132),
        ylim=(24, 42),
        xlabel="Longitude (°E)",
        ylabel="Latitude (°N)",
        title="(a) Fixed evaluated ocean cells",
    )
    axes[0].set_aspect(1 / np.cos(np.deg2rad(33)))
    axes[0].legend(fontsize=6.5)
    sst = pd.read_csv(output / "regional_sst.csv", index_col="date", parse_dates=True)
    for ax, domain in zip(axes[1:], ["yellow_bohai", "northern_ecs"]):
        forcing = pd.read_csv(
            output / f"{domain}_forcing.csv", index_col="date", parse_dates=True
        )
        q = heat_into_ocean(forcing).loc[:"2019-12-31"]
        tendency = sst[domain].diff().loc[:"2019-12-31"]
        ax.plot(
            np.arange(1, 13),
            q.groupby(q.index.month).mean(),
            "o-",
            color="#b86533",
            lw=1.2,
        )
        ax.axhline(0, color="#b86533", lw=0.5, alpha=0.4)
        twin = ax.twinx()
        twin.plot(
            np.arange(1, 13),
            tendency.groupby(tendency.index.month).mean(),
            "s--",
            color="#2e7888",
            lw=1.2,
            ms=3,
        )
        ax.set(
            xlabel="Month",
            ylabel="Heat into ocean (W m⁻²)",
            title=DOMAINS[domain],
            xticks=[1, 4, 7, 10],
        )
        twin.set_ylabel("Daily SST tendency (°C day⁻¹)", color="#2e7888")
        ax.tick_params(axis="y", labelcolor="#b86533")
        ax.grid(alpha=0.15)
    fig.suptitle("Geographical support and training-only monthly means (2010–2019)")
    save(fig, "process_domains_and_seasonality")
    fields = text_fields(output)
    report = (
        "# Past-forcing information and geographical transfer\n\n"
        "## Evidence status\n\n"
        + cfg["scope"]
        + "\n\n"
        + cfg["availability_amendment"]
        + "\n\n"
        + cfg["destination_scope_amendment"]
        + "\n\n## Results\n\n"
        + fields["process_results_text"]
        + "\n\n## Every SST-only transfer comparison\n\n"
        + fields["process_transfer_full_table"]
        + "\n\n## Source forcing contrasts\n\n"
        + fields["process_forcing_table"]
        + "\n\n## Post-outcome training-calibrated reference\n\n"
        + fields["process_alignment_table"]
        + "\n\n## Interpretation\n\n"
        "These models add lagged, coarse reanalysis information. They do not close a mixed-layer heat budget, "
        "separate forcing from feedback, or identify advection, entrainment or causal drivers. The wind magnitude "
        "is the magnitude of a daily regional-mean vector, not daily-mean scalar wind speed or wind stress. "
        "Reanalysis fluxes depend on prescribed/analysed SST and may include coastal land fractions. "
        "The one-day input delay is a calendar cutoff, not a measured operational publication latency. "
        "The destination lies on the adjacent shelf; no complete Eastern China Sea or instrument-independent "
        "geographical validation is established. Every selected family, horizon, year and season is retained. "
        "Raw predictions and serialized models accompany the local reproducibility package.\n\n"
        "![Past forcing](past_forcing_ablation.png)\n\n"
        "![Source transfer](regional_transfer.png)\n\n"
        "![Domain and training seasonal cycle](process_domains_and_seasonality.png)\n"
    )
    (output / "report_en.md").write_text(report)
    (output / "checksums.json").write_text(json.dumps(hashes(output), indent=2) + "\n")
