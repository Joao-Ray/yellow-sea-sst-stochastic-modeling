"""Manuscript text derived from locked multi-year and point-support results."""

import json
from pathlib import Path

import pandas as pd

from src.evaluation.confirmation_report import LABELS, markdown_table


def results_path(stage):
    local = Path("data/processed") / stage
    return (
        local
        if (local / "evaluation_audit.json").exists()
        else Path("paper") / stage / "results"
    )


def select_one(frame, **selectors):
    subset = frame
    for key, value in selectors.items():
        subset = subset.loc[subset[key].eq(value)]
    if len(subset) != 1:
        raise ValueError(f"expected exactly one manuscript result: {selectors}")
    return subset.iloc[0]


def extension_text():
    root, buoy = results_path("confirmation"), results_path("insitu")
    metrics = pd.read_csv(root / "metrics.csv")
    inference = pd.read_csv(root / "primary_inference.csv")
    annual = pd.read_csv(root / "annual_skill.csv")
    coverage = pd.read_csv(root / "coverage.csv", parse_dates=["date"])
    night = metrics.loc[
        metrics.period.eq("2023-2025")
        & metrics.target.eq("matched_grid_AMSR2")
        & metrics["pass"].eq("descending")
    ]
    trees = select_one(night, model="eof_extra_trees", horizon_days=30)
    ar = select_one(night, model="eof_ar_increments", horizon_days=30)
    base = select_one(night, model="grid_anomaly_persistence", horizon_days=30)
    p30 = select_one(
        inference, model="eof_extra_trees", horizon_days=30, bootstrap_block_days=30
    )
    p60 = select_one(
        inference, model="eof_extra_trees", horizon_days=30, bootstrap_block_days=60
    )
    annual_base = annual.loc[
        annual.year.lt(2026)
        & annual.target.eq("matched_grid_AMSR2")
        & annual["pass"].eq("descending")
        & annual.horizon_days.eq(30)
        & annual.model.eq("grid_anomaly_persistence")
    ].sort_values("year")
    if len(annual_base) != 3:
        raise ValueError("three full external years required")
    annual_trees = annual.loc[
        annual.year.lt(2026)
        & annual.target.eq("matched_grid_AMSR2")
        & annual["pass"].eq("descending")
        & annual.horizon_days.eq(30)
        & annual.model.eq("eof_extra_trees")
    ].sort_values("year")
    years_skill = ", ".join(
        f"{100 * x:.2f}%" for x in annual_trees.skill_vs_grid_anomaly_persistence
    )
    grid_tree = select_one(
        metrics,
        period="2023-2025",
        target="full_grid_OISST",
        model="eof_extra_trees",
        horizon_days=30,
        **{"pass": "all"},
    )
    matched_tree = select_one(
        metrics,
        period="2023-2025",
        target="matched_grid_OISST",
        model="eof_extra_trees",
        horizon_days=30,
        **{"pass": "descending"},
    )
    seven = select_one(
        inference, model="eof_extra_trees", horizon_days=7, bootstrap_block_days=60
    )
    text = (
        f"The locked ExtraTrees control reduces thirty-day nighttime AMSR2 RMSE from {base.rmse:.4f} "
        f"to {trees.rmse:.4f}°C, a {100 * trees.skill_vs_grid_anomaly_persistence:.2f}% improvement over "
        f"grid-specific anomaly persistence. Pointwise 95% skill intervals are "
        f"[{100 * p30.skill_ci_lower:.2f}, {100 * p30.skill_ci_upper:.2f}]% and "
        f"[{100 * p60.skill_ci_lower:.2f}, {100 * p60.skill_ci_upper:.2f}]% for 30- and 60-day blocks. "
        f"The corresponding nine-comparison Holm p values are {p30.p_holm_nine_comparisons:.4f} "
        f"and {p60.p_holm_nine_comparisons:.4f}. Annual thirty-day tree skills are {years_skill} "
        f"in 2023, 2024 and 2025. This provides support across two block choices and three annual "
        "point estimates for a specific sampled-instrument comparison, conditional on the prior exploration.\n\n"
        f"The EOF–AR thirty-day point skill is {100 * ar.skill_vs_grid_anomaly_persistence:.2f}%, "
        "but its adjusted tests do not provide the same support. Seven-day results are less stable: "
        "EOF–AR and VAR have negative annual skill in 2024; the tree comparison's adjusted "
        f"60-day-block p value is {seven.p_holm_nine_comparisons:.4f}. Neither a positive pooled estimate "
        "nor a pointwise interval alone establishes multiplicity-adjusted superiority.\n\n"
        f"The tree control's thirty-day full-grid OISST improvement is "
        f"{100 * grid_tree.skill_vs_grid_anomaly_persistence:.2f}%, compared with "
        f"{100 * matched_tree.skill_vs_grid_anomaly_persistence:.2f}% on nighttime matched OISST and "
        f"{100 * trees.skill_vs_grid_anomaly_persistence:.2f}% on exactly the same AMSR2 cells. "
        "The OISST outcomes were previously viewed and these percentages are descriptive. Their "
        "differences show why improved model representation does not remove verification-source dependence."
    )
    chosen = night.loc[
        night.model.isin(["eof_ar_increments", "eof_var_ridge", "eof_extra_trees"])
    ]
    joined = chosen.merge(
        inference.loc[inference.bootstrap_block_days.eq(60)],
        on=["model", "horizon_days"],
        validate="one_to_one",
    )
    display = pd.DataFrame(
        {
            "Model": joined.model.map(LABELS),
            "Lead (d)": joined.horizon_days,
            "RMSE (°C)": joined.rmse.map(lambda x: f"{x:.4f}"),
            "Skill (%)": (100 * joined.skill_vs_grid_anomaly_persistence).map(
                lambda x: f"{x:.2f}"
            ),
            "95% interval (%)": [
                f"[{100 * a:.2f}, {100 * b:.2f}]"
                for a, b in zip(joined.skill_ci_lower, joined.skill_ci_upper)
            ],
            "Holm p": joined.p_holm_nine_comparisons.map(lambda x: f"{x:.4f}"),
        }
    )
    bm = pd.read_csv(buoy / "metrics.csv")
    ba = pd.read_csv(buoy / "annual_metrics.csv")
    audit = json.loads((buoy / "evaluation_audit.json").read_text())
    support = pd.read_csv(buoy / "platform_support.csv")
    bnight = bm.loc[bm.target.eq("iQuam_buoys") & bm["pass"].eq("nighttime")]
    btree = select_one(bnight, model="eof_extra_trees", horizon_days=30)
    bbase = select_one(bnight, model="grid_anomaly_persistence", horizon_days=30)
    counts = ba.loc[
        ba.target.eq("iQuam_buoys")
        & ba["pass"].eq("nighttime")
        & ba.model.eq("grid_anomaly_persistence")
        & ba.horizon_days.eq(1)
    ].sort_values("year")
    platform_n = len(support.loc[support["pass"].eq("nighttime")])
    gate = "meets" if audit["primary_annual_coverage_gate_passed"] else "does not meet"
    buoy_text = (
        f"The 36 source months yield {int(bbase.n_days):,} nighttime dates, "
        f"{int(bbase.n_records):,} records and {platform_n} platform-type/identifier combinations. "
        f"Annual nighttime date counts are {', '.join(str(int(x)) for x in counts.n_days)}; "
        f"the sample {gate} the frozen 60-date-per-year coverage gate. "
        f"The thirty-day tree RMSE is {btree.rmse:.4f}°C, compared with {bbase.rmse:.4f}°C for "
        f"grid anomaly persistence (skill {100 * btree.skill_vs_grid_anomaly_persistence:.2f}%). "
        "October 2025 has no accepted nighttime buoy records; complete source acquisition does not imply complete monthly sampling. "
        "All models, annual results and matched OISST losses are retained in the supplement. "
        "This comparison concerns the sampled buoy locations and dates. Quality-control reference "
        "dependence, possible assimilation overlap, repeated platforms and support mismatch preclude "
        "a statistically independent truth claim; no additional significance claim is made."
    )
    bdisplay = pd.DataFrame(
        {
            "Model": bnight.model.map(LABELS),
            "Lead (d)": bnight.horizon_days,
            "Dates": bnight.n_days,
            "RMSE (°C)": bnight.rmse.map(lambda x: f"{x:.4f}"),
            "Bias (°C)": bnight.bias.map(lambda x: f"{x:.4f}"),
            "Skill (%)": (100 * bnight.skill_vs_grid_anomaly_persistence).map(
                lambda x: f"{x:.2f}"
            ),
        }
    )
    selection = pd.read_csv(root / "benchmark_selection.csv").fillna("—")
    selection_display = pd.DataFrame(
        {
            "Family": selection.model.map(LABELS),
            "Order": selection.order,
            "Penalty": selection.alpha,
            "Min leaf": selection.leaf,
            "Feature fraction": selection.max_features,
            "7-day selection RMSE (°C)": selection.selection_rmse.map(
                lambda x: f"{x:.4f}"
            ),
        }
    )
    infer_display = pd.DataFrame(
        {
            "Model": inference.model.map(LABELS),
            "Lead (d)": inference.horizon_days,
            "Block (d)": inference.bootstrap_block_days,
            "95% skill interval (%)": [
                f"[{100 * a:.2f}, {100 * b:.2f}]"
                for a, b in zip(inference.skill_ci_lower, inference.skill_ci_upper)
            ],
            "Raw p": inference.p_bootstrap_two_sided.map(lambda x: f"{x:.4f}"),
            "Holm p (9 tests)": inference.p_holm_nine_comparisons.map(
                lambda x: f"{x:.4f}"
            ),
        }
    )
    transfer = pd.read_csv(root / "skill_transfer.csv")
    transfer = transfer.loc[
        transfer.period.eq("2023-2025")
        & transfer.horizon_days.eq(30)
        & transfer.model.isin(
            [
                "frozen_selected_projection",
                "eof_ar_increments",
                "eof_var_ridge",
                "eof_extra_trees",
            ]
        )
    ].copy()
    transfer_display = pd.DataFrame(
        {
            "Pass": transfer["pass"],
            "Model": transfer.model.map(LABELS),
            "Analysis advantage (°C²)": transfer.advantage_analysis.map(
                lambda x: f"{x:.4f}"
            ),
            "External advantage (°C²)": transfer.advantage_external.map(
                lambda x: f"{x:.4f}"
            ),
            "Discrepancy perturbation (°C²)": transfer.discrepancy_perturbation.map(
                lambda x: f"{x:.4f}"
            ),
        }
    )
    bannual = ba.loc[
        ba.target.eq("iQuam_buoys")
        & ba["pass"].eq("nighttime")
        & ba.model.isin(["eof_extra_trees", "grid_anomaly_persistence"])
    ].copy()
    bannual_display = pd.DataFrame(
        {
            "Year": bannual.year,
            "Model": bannual.model.map(LABELS),
            "Lead (d)": bannual.horizon_days,
            "Dates": bannual.n_days,
            "RMSE (°C)": bannual.rmse.map(lambda x: f"{x:.4f}"),
            "Bias (°C)": bannual.bias.map(lambda x: f"{x:.4f}"),
            "Skill (%)": (100 * bannual.skill_vs_grid_anomaly_persistence).map(
                lambda x: f"{x:.2f}"
            ),
        }
    )
    return {
        "confirmation_night_days": int(trees.n_days),
        "confirmation_night_pairs": f"{int(trees.n_cell_day_pairs):,}",
        "confirmation_annual_days": ", ".join(str(int(x)) for x in annual_base.n_days),
        "confirmation_weight_percent": f"{100 * coverage.loc[coverage.date.dt.year.lt(2026) & coverage['pass'].eq('descending')].valid_weight_fraction.median():.1f}",
        "confirmation_abstract": f"A subsequent forecast-locked extension to all three years 2023–2025 reduces thirty-day nighttime AMSR2 RMSE by {100 * trees.skill_vs_grid_anomaly_persistence:.1f}% using a nonlinear spatial control; the nine-comparison Holm test supports the gain with both 30- and 60-day blocks.",
        "insitu_abstract": f"A descriptive buoy comparison covers {int(bbase.n_days):,} nighttime dates with platform-balanced daily losses.",
        "confirmation_results_text": text,
        "confirmation_primary_table": markdown_table(display),
        "insitu_results_text": buoy_text,
        "insitu_primary_table": markdown_table(bdisplay),
        "confirmation_selection_table": markdown_table(selection_display),
        "confirmation_inference_table": markdown_table(infer_display),
        "confirmation_transfer_table": markdown_table(transfer_display),
        "insitu_annual_table": markdown_table(bannual_display),
    }
