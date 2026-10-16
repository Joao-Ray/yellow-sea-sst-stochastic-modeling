"""Fixed training-only climatology and one-parameter anomaly-decay references."""

from datetime import datetime, timezone
import json

import numpy as np
import pandas as pd

from src.anomaly_transfer import OUTPUT, REVIEWED, inputs, config
from src.independent import paired_loss_interval
from src.models.anomaly_transfer import fit_climate
from src.validation import sha256


def fit_decay(state, train_end):
    training = state.loc[:train_end]
    previous = training.shift(1)
    mask = np.isfinite(previous) & np.isfinite(training)
    if mask.sum() < 730 or float(previous.loc[mask] @ previous.loc[mask]) <= 1e-12:
        raise ValueError("nondegenerate training residual pairs required")
    phi = float(
        (previous.loc[mask] @ training.loc[mask])
        / (previous.loc[mask] @ previous.loc[mask])
    )
    if abs(phi) >= 1:
        raise ValueError("unstable decay reference; do not silently clip")
    return phi, int(mask.sum())


def main():
    cfg = config()
    sst, weather, digests = inputs()
    design_path = REVIEWED / "benchmark_design.json"
    record = {
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "training_end": cfg["train_end"],
        "references": [
            "destination training harmonic/trend climatology",
            "destination no-intercept AR(1) of training anomalies",
            "source AR(1) coefficient with destination training climatology/scale",
        ],
        "scope": "Added while expanded sensitivity was being computed, after earlier outcomes were known. Fixed descriptive references, no hyperparameter selection or new p values. Reject unstable training AR(1), rather than clipping after outcome inspection.",
    }
    if not design_path.exists():
        design_path.write_text(json.dumps(record, indent=2) + "\n")
    climates = {d: fit_climate(sst[d], weather[d], cfg["train_end"]) for d in sst}
    states = {d: climates[d].state(sst[d]) for d in sst}
    decays = {d: fit_decay(states[d], cfg["train_end"]) for d in sst}
    rows = []
    for domain in sst:
        for h in cfg["horizons"]:
            cycle = climates[domain].sst_cycle.predict(sst.index)
            refs = {
                "training_climatology": cycle,
                "local_anomaly_ar1": climates[domain].decode(
                    decays[domain][0] ** h * states[domain].shift(h)
                ),
            }
            if domain == "northern_ecs":
                refs["source_anomaly_ar1_transfer"] = climates[domain].decode(
                    decays["yellow_bohai"][0] ** h * states[domain].shift(h)
                )
            for model, prediction in refs.items():
                for period, (start, stop) in cfg["test_periods"].items():
                    q = pd.DataFrame(
                        {
                            "date": sst.loc[start:stop].index,
                            "observed": sst[domain].loc[start:stop].values,
                            "predicted": prediction.loc[start:stop].values,
                            "domain": domain,
                            "model": model,
                            "horizon_days": h,
                            "period": period,
                        }
                    )
                    rows.append(q)
    frame = pd.concat(rows, ignore_index=True)
    frame["error"] = frame.predicted - frame.observed
    frame["mse"] = frame.error**2
    frame["year"] = frame.date.dt.year
    frame.to_csv(OUTPUT / "benchmark_predictions.csv", index=False)
    for extra, name in [
        ([], "benchmark_metrics.csv"),
        (["year"], "benchmark_annual_metrics.csv"),
    ]:
        out = frame.groupby(["period", "domain", "model", "horizon_days"] + extra).agg(
            n_days=("mse", "size"), mse=("mse", "mean"), bias=("error", "mean")
        )
        out["rmse"] = np.sqrt(out.mse)
        out.reset_index().to_csv(OUTPUT / name, index=False)
    f = pd.read_csv(OUTPUT / "predictions.csv", parse_dates=["date"])
    cases = f.loc[
        f.domain.eq("northern_ecs")
        & f.fitting.eq("source_transfer")
        & f.representation.eq("seasonal_anomaly")
    ]
    intervals = []
    for (period, family, group, h), q in cases.groupby(
        ["period", "family", "group", "horizon_days"]
    ):
        b = frame.loc[
            frame.domain.eq("northern_ecs")
            & frame.model.eq("local_anomaly_ar1")
            & frame.period.eq(period)
            & frame.horizon_days.eq(h)
        ]
        a = q.set_index("date").mse
        b = b.set_index("date").mse
        for block in cfg["bootstrap_block_days"]:
            intervals.append(
                {
                    "period": period,
                    "family": family,
                    "group": group,
                    "horizon_days": h,
                    "baseline": "local_anomaly_ar1",
                    "skill": 1 - np.sqrt(a.mean() / b.mean()),
                    **paired_loss_interval(a, b, block, cfg),
                }
            )
    pd.DataFrame(intervals).to_csv(
        OUTPUT / "decay_reference_intervals.csv", index=False
    )
    (OUTPUT / "benchmark_audit.json").write_text(
        json.dumps(
            {
                "evaluated_utc": datetime.now(timezone.utc).isoformat(),
                "software_sha256": sha256("src/anomaly_benchmarks.py"),
                "input_sha256": digests,
                "training_phi_and_pair_count": decays,
                "training_end": cfg["train_end"],
                "intercept": 0,
                "scope": "Fixed descriptive controls, not selected on validation or test. Local AR1 has destination training information, like destination climatology. All periods and horizons retained.",
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
