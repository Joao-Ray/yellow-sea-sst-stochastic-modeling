"""Exact common-support satellite scores for simple regional-increment references."""

from datetime import datetime, timezone
import json

import numpy as np
import pandas as pd

from src.anomaly_transfer import OUTPUT, config, inputs
from src.independent import paired_loss_interval
from src.validation import sha256


def main():
    cfg = config()
    sst, _, _ = inputs()
    score = pd.read_csv(
        OUTPUT / "external_daily_scores.csv",
        parse_dates=["date"],
        float_precision="round_trip",
    )
    predictions = pd.read_csv(
        OUTPUT / "predictions.csv", parse_dates=["date"], float_precision="round_trip"
    )
    predictions = predictions.loc[
        predictions.domain.eq("yellow_bohai") & predictions.fitting.eq("source_local")
    ]
    keys = ["period", "date", "horizon_days", "representation", "family", "group"]
    scored = score.loc[score.representation.ne("baseline")].merge(
        predictions[keys + ["predicted"]], on=keys, validate="many_to_one"
    )
    origins = pd.DatetimeIndex(
        scored.date - pd.to_timedelta(scored.horizon_days, unit="D")
    )
    scored["increment"] = (
        scored.predicted.to_numpy() - sst.yellow_bohai.reindex(origins).to_numpy()
    )
    ref = scored.loc[
        scored.representation.eq("raw")
        & scored.family.eq("ridge")
        & scored.group.eq("sst")
    ].copy()
    ref["linear_term"] = ref.bias - ref.increment
    ref["constant_term"] = (
        ref.mse - 2 * ref.linear_term * ref.increment - ref.increment**2
    )
    support = ["period", "date", "horizon_days", "target"]
    coefficients = ref[support + ["linear_term", "constant_term", "n_cells"]]
    checked = scored.merge(
        coefficients.drop(columns="n_cells"), on=support, validate="many_to_one"
    )
    reconstructed = (
        checked.constant_term
        + 2 * checked.linear_term * checked.increment
        + checked.increment**2
    )
    residual = float(np.max(np.abs(reconstructed - checked.mse)))
    if residual > 1e-10:
        raise ValueError(
            "regional-increment loss quadratic failed common-support audit"
        )
    benchmarks = pd.read_csv(
        OUTPUT / "benchmark_predictions.csv",
        parse_dates=["date"],
        float_precision="round_trip",
    )
    benchmarks = benchmarks.loc[benchmarks.domain.eq("yellow_bohai")]
    merged = coefficients.merge(
        benchmarks[["period", "date", "horizon_days", "model", "predicted"]],
        on=["period", "date", "horizon_days"],
        validate="many_to_many",
    )
    origins = pd.DatetimeIndex(
        merged.date - pd.to_timedelta(merged.horizon_days, unit="D")
    )
    delta = merged.predicted.to_numpy() - sst.yellow_bohai.reindex(origins).to_numpy()
    merged["mse"] = merged.constant_term + 2 * merged.linear_term * delta + delta**2
    merged["bias"] = merged.linear_term + delta
    if not np.isfinite(merged.mse).all() or (merged.mse < 0).any():
        raise ValueError("finite nonnegative reference losses required")
    merged["year"] = merged.date.dt.year
    keep = support + ["model", "n_cells", "mse", "bias", "year"]
    merged[keep].to_csv(OUTPUT / "external_benchmark_daily_scores.csv", index=False)
    for extra, name in [
        ([], "external_benchmark_metrics.csv"),
        (["year"], "external_benchmark_annual_metrics.csv"),
    ]:
        out = merged.groupby(["period", "target", "model", "horizon_days"] + extra).agg(
            n_days=("mse", "size"), mse=("mse", "mean"), bias=("bias", "mean")
        )
        out["rmse"] = np.sqrt(out.mse)
        out.reset_index().to_csv(OUTPUT / name, index=False)
    intervals = []
    cases = score.loc[score.representation.eq("seasonal_anomaly")]
    for (period, target, family, group, h), g in cases.groupby(
        ["period", "target", "family", "group", "horizon_days"]
    ):
        base = merged.loc[
            merged.period.eq(period)
            & merged.target.eq(target)
            & merged.model.eq("local_anomaly_ar1")
            & merged.horizon_days.eq(h)
        ]
        a = g.set_index("date").mse
        b = base.set_index("date").mse
        for block in cfg["bootstrap_block_days"]:
            intervals.append(
                {
                    "period": period,
                    "target": target,
                    "family": family,
                    "group": group,
                    "horizon_days": h,
                    "baseline": "projected_source_local_anomaly_ar1",
                    "skill": 1 - np.sqrt(a.mean() / b.mean()),
                    **paired_loss_interval(a, b, block, cfg),
                }
            )
    pd.DataFrame(intervals).to_csv(OUTPUT / "external_decay_intervals.csv", index=False)
    (OUTPUT / "external_reference_audit.json").write_text(
        json.dumps(
            {
                "evaluated_utc": datetime.now(timezone.utc).isoformat(),
                "software_sha256": sha256("src/anomaly_reference_external.py"),
                "identity": "L(delta)=A+2B delta+delta^2 on identical cells and weights",
                "all_model_common_support_identity_max_abs_error": residual,
                "n_checked_model_target_dates": len(checked),
                "input_sha256": {
                    str(OUTPUT / n): sha256(OUTPUT / n)
                    for n in [
                        "predictions.csv",
                        "external_daily_scores.csv",
                        "benchmark_predictions.csv",
                    ]
                },
                "scope": "Descriptive reference scores, algebraically reconstructed from audited common-support losses. No additional measurements, fitting, p values or instrument-independence claim.",
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
