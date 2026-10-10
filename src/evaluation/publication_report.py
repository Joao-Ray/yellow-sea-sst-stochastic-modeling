"""Scientific figures and reproducible English manuscript assembly."""

import html
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd


LABELS = {
    "frozen_selected_projection": "Frozen regional forecast",
    "frozen_anomaly_projection": "Frozen regional persistence",
    "grid_anomaly_persistence": "Grid anomaly persistence",
    "grid_raw_persistence": "Raw grid persistence",
    "eof_ar_increments": "EOF–AR spatial increments",
}


def write_publication(
    tables, selection, spatial, lat, lon, weights, config, output_dir
):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    def save(fig, name):
        fig.savefig(output_dir / (name + ".png"), dpi=300)
        fig.savefig(output_dir / (name + ".svg"))
        plt.close(fig)

    metrics = tables["metrics"]
    contexts = [
        ("regional_OISST", "all", "Regional mean: OISST"),
        ("full_grid_OISST", "all", "All fixed ocean cells: OISST"),
        ("matched_grid_OISST", "descending", "Matched nighttime cells: OISST"),
        ("matched_grid_AMSR2", "descending", "Same nighttime cells: AMSR2"),
    ]
    colors = {
        "frozen_selected_projection": "#1874b6",
        "frozen_anomaly_projection": "#77a6c4",
        "grid_anomaly_persistence": "#454f58",
        "eof_ar_increments": "#d76e19",
    }
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), layout="constrained")
    for panel, (ax, (target, pass_name, title)) in enumerate(
        zip(axes.ravel(), contexts)
    ):
        for name in colors:
            g = metrics.loc[
                metrics.period.eq("2026-Jan-Aug")
                & metrics.target.eq(target)
                & metrics["pass"].eq(pass_name)
                & metrics.model.eq(name)
            ].sort_values("horizon_days")
            ax.plot(
                g.horizon_days,
                g.rmse,
                "o-",
                color=colors[name],
                label=LABELS[name],
                lw=1.6,
            )
        ax.set(
            title=f"({chr(97 + panel)}) {title}",
            xlabel="Lead time (days)",
            ylabel="RMSE (°C)",
        )
        ax.set_xticks([1, 7, 30])
        ax.grid(alpha=0.2)
    axes[0, 0].legend(fontsize=7)
    fig.suptitle(
        "Forecast errors across target scales and verification sources | January–August 2026"
    )
    save(fig, "evaluation_scales")

    parts = tables["loss_decomposition"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    names = ["frozen_selected_projection", "eof_ar_increments"]
    for ax, pass_name in zip(axes, ["descending", "ascending"]):
        g = pd.concat(
            [
                parts.loc[
                    parts["pass"].eq(pass_name)
                    & parts.horizon_days.eq(h)
                    & parts.model.eq(name)
                ]
                for h in [1, 7, 30]
                for name in names
            ]
        )
        x = np.arange(len(g))
        positive = np.zeros(len(g))
        negative = np.zeros(len(g))
        for column, color, label in [
            ("analysis_forecast_mse", "#1874b6", "Forecast loss against matched OISST"),
            ("product_discrepancy_mse", "#bdcbd5", "OISST–AMSR2 squared discrepancy"),
            ("interaction", "#d76e19", "Signed interaction"),
        ]:
            v = g[column].values
            ax.bar(
                x,
                v,
                bottom=np.where(v >= 0, positive, negative),
                color=color,
                label=label,
            )
            positive += np.maximum(v, 0)
            negative += np.minimum(v, 0)
        ax.scatter(
            x,
            g.external_mse,
            color="black",
            s=20,
            label="Total loss against AMSR2",
            zorder=4,
        )
        ax.axhline(0, color="black", lw=0.6)
        ax.set(
            xticks=x,
            xticklabels=[
                f"{h}d\n{label}" for h in [1, 7, 30] for label in ["Frozen", "EOF–AR"]
            ],
            title=pass_name,
            ylabel="Daily area-weighted MSE (°C²)",
        )
        ax.grid(axis="y", alpha=0.15)
    axes[0].legend(fontsize=7)
    fig.suptitle("Matched-loss decomposition across verification sources")
    save(fig, "loss_decomposition")

    grid = tables["product_grid"]
    fig, axes = plt.subplots(2, 2, figsize=(10, 9), layout="constrained")
    bias = grid.bias_oisst_minus_amsr2.abs().max()
    rms = grid.rms_difference.max()
    for row, pass_name in enumerate(["descending", "ascending"]):
        g = grid.loc[grid["pass"].eq(pass_name) & grid.n_days.gt(0)]
        for col, (field, title, cmap, vmin, vmax) in enumerate(
            [
                (
                    "bias_oisst_minus_amsr2",
                    "OISST minus AMSR2 bias",
                    "RdBu_r",
                    -bias,
                    bias,
                ),
                ("rms_difference", "OISST–AMSR2 RMS difference", "viridis", 0, rms),
            ]
        ):
            ax = axes[row, col]
            ax.scatter(lon, lat, c="#dedede", s=14, marker="s", zorder=0)
            sc = ax.scatter(
                g.lon,
                g.lat,
                c=g[field],
                cmap=cmap,
                vmin=vmin,
                vmax=vmax,
                s=14,
                marker="s",
            )
            ax.set(
                title=f"({chr(97 + row * 2 + col)}) " + pass_name + " | " + title,
                xlabel="Longitude (°E)",
                ylabel="Latitude (°N)",
                xlim=(117, 128),
                ylim=(31, 42),
            )
            ax.set_aspect(1 / np.cos(np.deg2rad(36.5)))
            fig.colorbar(sc, ax=ax, label="°C", shrink=0.8)
    fig.suptitle(
        "Spatial product differences | grey: fixed ocean cells without matched observations"
    )
    save(fig, "product_spatial_diagnostics")

    k = min(4, spatial.rank)
    fig, axes = plt.subplots(
        1, k, figsize=(3.5 * k, 4.8), layout="constrained", squeeze=False
    )
    for j, ax in enumerate(axes.ravel()):
        pattern = spatial.basis[:, j] / np.sqrt(weights)
        bound = np.abs(pattern).max()
        sc = ax.scatter(
            lon,
            lat,
            c=pattern,
            cmap="RdBu_r",
            vmin=-bound,
            vmax=bound,
            s=12,
            marker="s",
        )
        ax.set(
            title=f"Training EOF {j + 1}",
            xlabel="Longitude (°E)",
            ylabel="Latitude (°N)",
            xlim=(117, 128),
            ylim=(31, 42),
        )
        ax.set_aspect(1 / np.cos(np.deg2rad(36.5)))
        fig.colorbar(
            sc, ax=ax, label="Weighted spatial loading (normalized)", shrink=0.75
        )
    fig.suptitle("Spatial covariance modes fitted to 2010–2019")
    save(fig, "spatial_modes")

    seasons = ["DJF", "MAM", "JJA", "SON"]
    seasonal = tables["seasonal_scores"]
    fig, axes = plt.subplots(2, 3, figsize=(12, 7), layout="constrained")
    for row, period in enumerate(["2023-2025", "2026-Jan-Aug"]):
        for col, h in enumerate([1, 7, 30]):
            ax = axes[row, col]
            for name in [
                "frozen_selected_projection",
                "frozen_anomaly_projection",
                "eof_ar_increments",
            ]:
                g = (
                    seasonal.loc[
                        seasonal.period.eq(period)
                        & seasonal.target.eq("regional_OISST")
                        & seasonal.horizon_days.eq(h)
                        & seasonal.model.eq(name)
                    ]
                    .set_index("season")
                    .reindex(seasons)
                )
                ax.plot(
                    np.arange(4), g.rmse, "o-", color=colors[name], label=LABELS[name]
                )
            ax.set(
                title=f"{period} | {h}-day regional mean",
                xticks=np.arange(4),
                xticklabels=seasons,
                ylabel="RMSE (°C)",
            )
            ax.grid(alpha=0.2)
    axes[0, 0].legend(fontsize=7)
    fig.suptitle(
        "Season-stratified regional errors | 2026 SON is unavailable, not imputed"
    )
    save(fig, "seasonal_diagnostics")

    inference = tables["primary_inference"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), layout="constrained")
    for ax, target in zip(axes, ["regional_OISST_2026", "matched_AMSR2_night_2026"]):
        for offset, block, color in [(-0.12, 30, "#1874b6"), (0.12, 60, "#d76e19")]:
            g = inference.loc[
                inference.target.eq(target) & inference.bootstrap_block_days.eq(block)
            ].sort_values("horizon_days")
            x = np.arange(3) + offset
            ax.vlines(
                x,
                g.skill_ci_lower * 100,
                g.skill_ci_upper * 100,
                color=color,
                lw=2,
                label=f"{block}-day blocks",
            )
        ax.axhline(0, color="black", lw=0.7)
        ax.set(
            title="Regional OISST"
            if target.startswith("regional")
            else "Matched nighttime AMSR2",
            xticks=np.arange(3),
            xticklabels=["1", "7", "30"],
            xlabel="Lead time (days)",
            ylabel="Skill interval (%)",
        )
        ax.grid(alpha=0.15)
        ax.legend(fontsize=8)
    fig.suptitle(
        "Secondary paired skill intervals | sensitivity to calendar-block length"
    )
    save(fig, "secondary_inference")
    write_documents(tables, selection, spatial, config, output_dir)


def render_markdown(source, target, image_dir, title):
    from src.evaluation.research_report import _html_report

    _html_report(source.splitlines(), image_dir)
    rendered = (
        (image_dir / "完整研究报告.html")
        .read_text()
        .replace('<html lang="zh-CN">', '<html lang="en">')
        .replace(
            "<title>黄海 SST 完整研究报告</title>",
            f"<title>{html.escape(title)}</title>",
        )
    )
    rendered = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", rendered)
    target.write_text(rendered)
    (image_dir / "完整研究报告.html").unlink()


def write_documents(tables, selection, spatial, config, output_dir):
    template = Path("paper/submission/manuscript_en.template.md")
    if not template.exists():
        return
    manuscript = template.read_text()
    data = dynamic_text(tables, selection, spatial, config)
    for key, value in data.items():
        manuscript = manuscript.replace("{{" + key + "}}", str(value))
    if re.search(r"\{\{\w+\}\}", manuscript):
        raise ValueError("unfilled manuscript result placeholder")
    references = Path("paper/submission/references_verified.md").read_text()
    manuscript += "\n\n## References\n\n" + references
    (output_dir / "manuscript_en.md").write_text(manuscript.rstrip() + "\n")
    render_markdown(
        manuscript,
        output_dir / "manuscript_en.html",
        output_dir,
        "SST predictability across scales and observation sources",
    )
    supplement = Path("paper/submission/supplement_en.template.md").read_text()
    for key, value in data.items():
        supplement = supplement.replace("{{" + key + "}}", str(value))
    if re.search(r"\{\{\w+\}\}", supplement):
        raise ValueError("unfilled supplement result placeholder")
    (output_dir / "supplement_en.md").write_text(supplement.rstrip() + "\n")
    render_markdown(
        supplement,
        output_dir / "supplement_en.html",
        output_dir,
        "Supplementary information — SST scale and source verification",
    )


def markdown_table(frame, columns, labels=None):
    headings = {
        "period": "Period",
        "target": "Target",
        "pass": "Pass",
        "horizon_days": "Lead (d)",
        "model": "Method",
        "baseline": "Baseline",
        "n_days": "Days",
        "rmse": "RMSE (°C)",
        "bias_celsius": "Bias (°C)",
        "bootstrap_block_days": "Block (d)",
        "skill_ci_lower": "Skill lower",
        "skill_ci_upper": "Skill upper",
        "rank": "Rank",
        "order": "Order",
        "trend": "Trend",
        "selection_days": "Selection days",
        "selection_rmse": "Selection RMSE (°C)",
        "skill_vs_grid_anomaly_persistence": "Skill vs grid persistence",
        "skill_vs_frozen_anomaly_projection": "Skill vs frozen persistence",
    }
    labels = [headings.get(x, x.replace("_", " ")) for x in (labels or columns)]
    lines = [
        "| " + " | ".join(labels) + " |",
        "|" + "|".join(["---"] * len(columns)) + "|",
    ]
    for row in frame.to_dict("records"):
        values = []
        for column in columns:
            value = row[column]
            if isinstance(value, (float, np.floating)):
                values.append(f"{value:.4f}" if np.isfinite(value) else "NA")
            else:
                label = {
                    **LABELS,
                    "regional_OISST": "Regional OISST",
                    "full_grid_OISST": "Full-grid OISST",
                    "matched_grid_OISST": "Matched OISST",
                    "matched_grid_AMSR2": "Matched AMSR2",
                    "regional_OISST_2026": "Regional OISST (2026)",
                    "matched_AMSR2_night_2026": "Nighttime AMSR2 (2026)",
                    "ascending": "Afternoon",
                    "descending": "Nighttime",
                }.get(str(value), str(value))
                values.append(label)
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def dynamic_text(tables, selection, spatial, config):
    metrics = tables["metrics"]
    primary = pd.read_csv("paper/validation/metrics.csv")
    external = pd.read_csv("paper/independent/metrics.csv")
    decomposition = tables["loss_decomposition"]
    selected = decomposition.loc[
        decomposition["pass"].eq("descending")
        & decomposition.model.eq("frozen_selected_projection")
    ].sort_values("horizon_days")
    modes = metrics.loc[
        metrics.period.eq("2026-Jan-Aug")
        & metrics["pass"].eq("descending")
        & metrics.target.eq("matched_grid_AMSR2")
        & metrics.model.eq("eof_ar_increments")
    ].sort_values("horizon_days")
    primary_methods = json.loads(
        Path("paper/validation/frozen_protocol.json").read_text()
    )["selected_methods"]
    rows = []
    for h in [1, 7, 30]:
        o = primary.loc[
            primary.horizon_days.eq(h) & primary.model.eq(primary_methods[str(h)])
        ].iloc[0]
        a = external.loc[
            external["pass"].eq("descending")
            & external.horizon_days.eq(h)
            & external.model.eq(primary_methods[str(h)])
        ].iloc[0]
        rows.append(
            {
                "lead": h,
                "regional_rmse": o.rmse,
                "regional_skill_percent": 100 * o.rmse_skill_vs_persistence,
                "external_rmse": a.rmse,
                "external_skill_percent": 100 * a.rmse_skill_vs_persistence,
                "external_days": a.n_days,
            }
        )
    allgrid = metrics.loc[
        metrics.target.eq("full_grid_OISST")
        & metrics.model.isin(
            [
                "frozen_selected_projection",
                "grid_anomaly_persistence",
                "eof_ar_increments",
            ]
        )
    ]
    transfer = tables["skill_transfer"].loc[
        lambda x: x["pass"].eq("descending")
        & x.model.isin(["frozen_selected_projection", "eof_ar_increments"])
    ]
    inference = tables["primary_inference"]
    seasonal = tables["seasonal_scores"].loc[
        lambda x: x.target.eq("regional_OISST")
        & x.model.eq("frozen_selected_projection")
    ]
    ratio = selected.product_discrepancy_mse / selected.external_mse
    return {
        "primary_table": markdown_table(
            pd.DataFrame(rows),
            [
                "lead",
                "regional_rmse",
                "regional_skill_percent",
                "external_rmse",
                "external_skill_percent",
                "external_days",
            ],
            [
                "Lead (days)",
                "Regional OISST RMSE (°C)",
                "Regional skill (%)",
                "Matched AMSR2 RMSE (°C)",
                "External skill (%)",
                "External days",
            ],
        ),
        "spatial_rank": spatial.rank,
        "spatial_order": spatial.order,
        "spatial_trend": str(spatial.trend).lower(),
        "spatial_variance_percent": f"{100 * spatial.variance_fraction:.1f}",
        "selection_rmse": f"{selection.selection_rmse.min():.4f}",
        "spatial_comparison_table": markdown_table(
            allgrid[
                [
                    "period",
                    "horizon_days",
                    "model",
                    "rmse",
                    "skill_vs_grid_anomaly_persistence",
                    "n_days",
                ]
            ],
            [
                "period",
                "horizon_days",
                "model",
                "rmse",
                "skill_vs_grid_anomaly_persistence",
                "n_days",
            ],
        ),
        "decomposition_table": markdown_table(
            selected,
            [
                "horizon_days",
                "analysis_forecast_mse",
                "product_discrepancy_mse",
                "interaction",
                "external_mse",
            ],
            [
                "Lead",
                "OISST forecast MSE",
                "Product discrepancy MSE",
                "Signed interaction",
                "AMSR2 MSE",
            ],
        ),
        "discrepancy_ratios": ", ".join(f"{100 * x:.1f}%" for x in ratio),
        "eof_external_rmse": ", ".join(f"{x:.4f}" for x in modes.rmse),
        "transfer_table": markdown_table(
            transfer,
            [
                "horizon_days",
                "model",
                "advantage_analysis",
                "advantage_external",
                "discrepancy_perturbation",
            ],
        ),
        "inference_table": markdown_table(
            inference,
            [
                "target",
                "horizon_days",
                "bootstrap_block_days",
                "p_bootstrap_two_sided",
                "p_holm_six_comparisons",
                "skill_ci_lower",
                "skill_ci_upper",
            ],
        ),
        "seasonal_table": markdown_table(
            seasonal,
            ["period", "horizon_days", "season", "n_days", "rmse", "bias_celsius"],
        ),
        "interval_table": markdown_table(
            tables["interval_diagnostics"],
            [
                "horizon_days",
                "model",
                "season",
                "n_days",
                "coverage",
                "mean_interval_score_celsius",
                "mean_width_celsius",
            ],
        ),
        "memory_table": markdown_table(
            tables["seasonal_memory"], ["season", "lag_days", "n_pairs", "correlation"]
        ),
        "distance_table": markdown_table(
            tables["product_distance"],
            [
                "pass",
                "distance_proxy_bin",
                "season",
                "n_days",
                "n_cell_day_pairs",
                "rms_difference",
                "bias",
            ],
        ),
        "selection_table": markdown_table(
            selection, ["trend", "rank", "order", "selection_days", "selection_rmse"]
        ),
        "spatial_intervals_table": markdown_table(
            tables["spatial_intervals"],
            [
                "period",
                "target",
                "horizon_days",
                "baseline",
                "bootstrap_block_days",
                "skill_ci_lower",
                "skill_ci_upper",
            ],
        ),
        "all_metrics_table": markdown_table(
            metrics,
            [
                "period",
                "target",
                "pass",
                "horizon_days",
                "model",
                "n_days",
                "rmse",
                "skill_vs_frozen_anomaly_projection",
                "skill_vs_grid_anomaly_persistence",
            ],
        ),
        "identity_tolerance": f"{decomposition.max_absolute_identity_error.max():.2e}",
    }
