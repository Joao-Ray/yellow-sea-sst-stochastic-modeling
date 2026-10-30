"""Computed manuscript fields and descriptive platform-deletion figure."""

from pathlib import Path

import numpy as np
import pandas as pd

from src.evaluation.confirmation_report import markdown_table

ROOT = Path("paper/buoy_robustness/results")
LABELS = {
    "eof_ar_increments": "EOF–AR",
    "eof_var_ridge": "EOF–VAR",
    "eof_extra_trees": "EOF–ExtraTrees",
    "anomaly_ridge": "Anomaly ridge",
    "anomaly_trees": "Anomaly trees",
}


def select(frame, region, model, h, baseline=None):
    baseline = baseline or (
        "grid_anomaly_persistence" if region == "source" else "grid_source_ar1"
    )
    return frame.loc[
        frame.region.eq(region)
        & frame.model.eq(model)
        & frame.horizon_days.eq(h)
        & frame.target.eq("iQuam")
        & frame["pass"].eq("nighttime")
        & frame.baseline.eq(baseline)
    ]


def text_fields(root=ROOT):
    full = pd.read_csv(root / "full_metrics.csv")
    deletions = root / "deletion_metrics.csv"
    if not deletions.exists():
        deletions = deletions.with_suffix(".csv.gz")
    deleted = pd.read_csv(deletions, dtype={"removed_id": str})
    support = pd.read_csv(root / "platform_weights.csv", dtype={"platform_id": str})
    summary, coverage = [], []
    for region, models in [
        ("source", ["eof_extra_trees"]),
        ("destination", ["anomaly_ridge", "anomaly_trees"]),
    ]:
        for model in models:
            for h in [1, 7, 30]:
                a = select(full, region, model, h).iloc[0]
                b = select(deleted, region, model, h)
                one = b.loc[b.unit_kind.eq("platform")]
                typ = b.loc[b.unit_kind.eq("platform_type")]
                summary.append(
                    {
                        "Region / model / lead": f"{region} / {LABELS[model]} / {h} d",
                        "Original gain (%)": f"{100 * a.skill:.2f}",
                        "Platform removal range (%)": f"{100 * one.skill.min():.2f} to {100 * one.skill.max():.2f}",
                        "Type removal range (%)": f"{100 * typ.skill.min():.2f} to {100 * typ.skill.max():.2f}",
                        "Equal-period-platform gain (%)": f"{100 * a.platform_equal_skill:.2f}",
                    }
                )
    for (region, passage), g in support.groupby(["region", "pass"]):
        coverage.append(
            {
                "Region / pass": f"{region} / {passage}",
                "Type/ID combinations": len(g),
                "Largest score weight (%)": f"{100 * g.score_weight.max():.2f}",
                "Largest three weights (%)": f"{100 * g.score_weight.nlargest(3).sum():.2f}",
                "Weight concentration (1/sum w²)": f"{1 / np.sum(g.score_weight**2):.2f}",
                "Days with only one platform": int(g.sole_platform_days.sum()),
            }
        )
    source = select(deleted, "source", "eof_extra_trees", 30)
    sp = source.loc[source.unit_kind.eq("platform")]
    st = source.loc[source.unit_kind.eq("platform_type")]
    sa = select(full, "source", "eof_extra_trees", 30).iloc[0]
    dst = select(deleted, "destination", "anomaly_ridge", 30)
    dp = dst.loc[dst.unit_kind.eq("platform")]
    dt = dst.loc[dst.unit_kind.eq("platform_type")]
    dst_tree = select(deleted, "destination", "anomaly_trees", 30)
    tp = dst_tree.loc[dst_tree.unit_kind.eq("platform")]
    tt = dst_tree.loc[dst_tree.unit_kind.eq("platform_type")]
    source_text = (
        f"A later descriptive platform-support sensitivity retained thirty-day ExtraTrees gains "
        f"of {100 * sp.skill.min():.2f}–{100 * sp.skill.max():.2f}% after removing each of {len(sp)} "
        f"nighttime platform type/ID combinations, compared with {100 * sa.skill:.2f}% originally. "
        f"Removing an entire platform type gave {100 * st.skill.min():.2f}–{100 * st.skill.max():.2f}%; "
        f"equal total weight per platform over the period gave {100 * sa.platform_equal_skill:.2f}%. "
        "These are different observed-support summaries, not uncertainty intervals or new independent validation (Supplementary Section S15)."
    )
    dest_text = (
        "The same support sensitivity gave thirty-day anomaly ridge/tree gains against grid source AR(1) "
        f"of {100 * dp.skill.min():.2f} to {100 * dp.skill.max():.2f}% and {100 * tp.skill.min():.2f} "
        f"to {100 * tp.skill.max():.2f}% across single-platform removals, respectively; whole-type "
        f"removals gave {100 * dt.skill.min():.2f} to {100 * dt.skill.max():.2f}% and "
        f"{100 * tt.skill.min():.2f} to {100 * tt.skill.max():.2f}%. "
        "All removals, vanished-date counts, same-retained-date references and alternative period-platform weights are reported in Supplementary Section S15."
    )
    ds = support.loc[support.region.eq("destination") & support["pass"].eq("nighttime")]
    source_brief = (
        f"In a later descriptive check, thirty-day ExtraTrees gains remained "
        f"{100 * sp.skill.min():.2f}–{100 * sp.skill.max():.2f}% after each nighttime "
        "platform type/ID combination was removed in turn. Whole-type exclusions and "
        "alternative period-platform weights are retained in Supplementary Section S15; "
        "removal ranges are not uncertainty intervals."
    )
    dest_brief = (
        f"Buoy support was concentrated: three of {len(ds)} nighttime platform type/ID "
        f"combinations received {100 * ds.score_weight.nlargest(3).sum():.2f}% of score weight. "
        "Thirty-day ridge and tree transfer remained worse than grid source AR(1) under "
        "every single-platform and whole-type exclusion, but these checks retain the "
        "original observational dependencies and limited geographical support "
        "(Supplementary Section S15)."
    )
    return {
        "buoy_robustness_source_text": source_brief,
        "buoy_robustness_destination_text": dest_brief,
        "buoy_robustness_detail_text": source_text + "\n\n" + dest_text,
        "buoy_robustness_table": markdown_table(pd.DataFrame(summary)),
        "buoy_robustness_support_table": markdown_table(pd.DataFrame(coverage)),
    }


def write_report(root, full, deleted, annual, support):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = []
    for (region, passage, target, h, model, baseline), g in deleted.groupby(
        ["region", "pass", "target", "horizon_days", "model", "baseline"]
    ):
        for kind, z in g.groupby("unit_kind"):
            rows.append(
                dict(
                    region=region,
                    **{"pass": passage},
                    target=target,
                    horizon_days=h,
                    model=model,
                    baseline=baseline,
                    unit_kind=kind,
                    n_removals=len(z),
                    n_scored=int(z.status.eq("scored").sum()),
                    minimum_skill=z.skill.min(),
                    maximum_skill=z.skill.max(),
                    positive_skill_removals=int(z.skill.gt(0).sum()),
                    minimum_remaining_days=int(z.n_days.min()),
                    maximum_lost_days=int(z.n_days_lost.max()),
                    maximum_absolute_skill_change_same_dates=float(
                        abs(z.skill - z.full_on_retained_dates_skill).max()
                    ),
                )
            )
    pd.DataFrame(rows).to_csv(root / "deletion_summary.csv", index=False)
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 6.4), layout="constrained")
    for ax, region, models, title in [
        (
            axes[0],
            "source",
            ["eof_ar_increments", "eof_var_ridge", "eof_extra_trees"],
            "(a) Yellow–Bohai: vs grid persistence",
        ),
        (
            axes[1],
            "destination",
            ["anomaly_ridge", "anomaly_trees"],
            "(b) Northern ECS: vs grid source AR(1)",
        ),
    ]:
        labels = []
        y = 0
        for model in models:
            for h in [1, 7, 30]:
                a = select(full, region, model, h).iloc[0]
                z = select(deleted, region, model, h)
                for kind, offset, color, width in [
                    ("platform_type", 0.10, "#dc9a58", 4),
                    ("platform", -0.10, "#2d738f", 4),
                ]:
                    b = z.loc[z.unit_kind.eq(kind)]
                    ax.plot(
                        [100 * b.skill.min(), 100 * b.skill.max()],
                        [y + offset] * 2,
                        color=color,
                        lw=width,
                        solid_capstyle="round",
                    )
                ax.plot(100 * a.skill, y, "ko", ms=4)
                labels.append(f"{LABELS[model]} | {h} d")
                y += 1
        ax.set_yticks(range(y), labels, fontsize=8)
        ax.invert_yaxis()
        ax.axvline(0, ls="--", color="#555", lw=1)
        ax.set(title=title, xlabel="RMSE gain (%) | positive favours model")
        ax.grid(axis="x", alpha=0.18)
    from matplotlib.lines import Line2D

    fig.legend(
        handles=[
            Line2D([0], [0], color="#2d738f", lw=4, label="Remove one type/ID"),
            Line2D([0], [0], color="#dc9a58", lw=4, label="Remove one platform type"),
            Line2D(
                [0],
                [0],
                color="black",
                marker="o",
                ls="",
                label="Original date-balanced score",
            ),
        ],
        loc="outside lower center",
        ncol=3,
        fontsize=8,
    )
    fig.suptitle(
        "Buoy support sensitivity | Nighttime 2023–2025\nObserved deletion ranges, not confidence intervals",
        fontsize=12,
    )
    fig.savefig(root / "buoy_platform_sensitivity.png", dpi=300)
    fig.savefig(root / "buoy_platform_sensitivity.svg")
    plt.close(fig)
    fields = text_fields(root)
    (root / "report_en.md").write_text(
        "# Retrospective buoy support sensitivity\n\n"
        + fields["buoy_robustness_detail_text"]
        + "\n\n"
        + fields["buoy_robustness_table"]
        + "\n\n"
        + fields["buoy_robustness_support_table"]
        + "\n\n![Descriptive removal ranges](buoy_platform_sensitivity.png)\n"
    )
