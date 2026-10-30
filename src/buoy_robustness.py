"""Retrospective descriptive checks of buoy platform leverage; no new inference."""

from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import shutil
import platform as runtime_platform

import numpy as np
import pandas as pd

from src.validation import sha256

KEYS = ["date", "platform_type", "platform_id"]
LOSSES = ["mse", "mae", "bias"]
OUTPUT = Path("data/processed/buoy_robustness")
REVIEWED = Path("paper/buoy_robustness/results")


def platform_day_losses(points, errors):
    errors = np.asarray(errors, dtype=float)
    if errors.shape != (len(points),) or not np.isfinite(errors).all():
        raise ValueError("one finite error per accepted observation is required")
    if points[KEYS].isna().any().any() or points.platform_id.str.strip().eq("").any():
        raise ValueError("complete composite platform/date identifiers are required")
    q = points[KEYS].copy()
    q["mse"], q["mae"], q["bias"] = errors**2, np.abs(errors), errors
    q["n_records"] = 1
    return q.groupby(KEYS, as_index=False).agg(
        mse=("mse", "mean"),
        mae=("mae", "mean"),
        bias=("bias", "mean"),
        n_records=("n_records", "sum"),
    )


def daily_losses(platform):
    return platform.groupby("date")[LOSSES].mean()


def score_platform_days(platform):
    daily = daily_losses(platform)
    counts = {
        "n_days": len(daily),
        "n_platform_days": len(platform),
        "n_platforms": len(
            platform[["platform_type", "platform_id"]].drop_duplicates()
        ),
        "n_records": int(platform.n_records.sum()),
        "status": "scored" if len(daily) else "unscorable",
    }
    values = daily.mean().to_dict()
    counts.update(values)
    counts["rmse"] = float(np.sqrt(values["mse"]))
    # Changes the estimand: every platform gets the same total period weight.
    alternative = (
        platform.groupby(["platform_type", "platform_id"])[LOSSES].mean().mean()
    )
    counts.update({"platform_equal_" + k: v for k, v in alternative.items()})
    counts["platform_equal_rmse"] = float(np.sqrt(alternative["mse"]))
    return counts


def support_weights(platform):
    q = platform.copy()
    n = q.groupby("date").date.transform("size")
    q["score_weight"] = 1 / n / q.date.nunique()
    q["sole_platform_days"] = (n == 1).astype(int)
    support = q.groupby(["platform_type", "platform_id"], as_index=False).agg(
        score_weight=("score_weight", "sum"),
        sole_platform_days=("sole_platform_days", "sum"),
        n_days=("date", "size"),
        n_records=("n_records", "sum"),
    )
    support["record_fraction"] = support.n_records / support.n_records.sum()
    return support


def deletion_scores(platform):
    original = daily_losses(platform)
    units = [
        ("platform", t, i)
        for t, i in platform[KEYS[1:]]
        .drop_duplicates()
        .itertuples(index=False, name=None)
    ]
    units += [("platform_type", t, "") for t in sorted(platform.platform_type.unique())]
    rows = []
    for kind, ptype, pid in units:
        drop = platform.platform_type.eq(ptype)
        if kind == "platform":
            drop &= platform.platform_id.eq(pid)
        remaining = platform.loc[~drop]
        row = score_platform_days(remaining)
        dates = remaining.date.unique()
        row.update(
            unit_kind=kind,
            removed_type=int(ptype),
            removed_id=pid,
            n_days_lost=len(original) - len(dates),
        )
        row.update(
            {
                "full_on_retained_dates_" + k: v
                for k, v in original.loc[dates].mean().items()
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def add_skills(frame, deletion=False):
    rows = []
    for region, group in frame.groupby("region"):
        baselines = (
            ["grid_anomaly_persistence"]
            if region == "source"
            else ["grid_source_ar1", "projected_source_ar1", "grid_climatology"]
        )
        keys = ["region", "pass", "target", "horizon_days"]
        if deletion:
            keys += ["unit_kind", "removed_type", "removed_id"]
        for baseline in baselines:
            reference = group.loc[
                group.model.eq(baseline),
                keys
                + ["rmse", "platform_equal_rmse"]
                + (["full_on_retained_dates_mse"] if deletion else []),
            ]
            reference = reference.rename(
                columns={
                    "rmse": "baseline_rmse",
                    "platform_equal_rmse": "baseline_platform_equal_rmse",
                    "full_on_retained_dates_mse": "baseline_full_on_retained_dates_mse",
                }
            )
            q = group.merge(reference, on=keys, validate="many_to_one")
            q["baseline"] = baseline
            q["skill"] = 1 - q.rmse / q.baseline_rmse
            q["platform_equal_skill"] = (
                1 - q.platform_equal_rmse / q.baseline_platform_equal_rmse
            )
            if deletion:
                q["full_on_retained_dates_skill"] = 1 - np.sqrt(
                    q.full_on_retained_dates_mse / q.baseline_full_on_retained_dates_mse
                )
            rows.append(q)
    return pd.concat(rows, ignore_index=True)


def protected_hashes():
    roots = [
        Path("data/processed") / name
        for name in [
            "confirmation",
            "insitu",
            "process_transfer",
            "anomaly_transfer",
            "destination_validation",
        ]
    ]
    roots += [
        Path("paper") / name
        for name in [
            "confirmation",
            "insitu",
            "process_transfer",
            "anomaly_transfer",
            "destination_validation",
        ]
    ]
    return {
        str(p): sha256(p)
        for root in roots
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def main():
    from src.destination_validation import forecast, verify

    verify()
    before = protected_hashes()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    full, deleted, weights, annual, audits, inputs = [], [], [], [], [], {}
    for region, stage, point_file, daily_file in [
        (
            "source",
            "confirmation",
            "data/processed/insitu/collocations.csv",
            "data/processed/insitu/daily_scores.csv",
        ),
        (
            "destination",
            "destination_validation",
            "data/processed/destination_validation/matched_buoy_points.csv",
            "data/processed/destination_validation/buoy_daily_scores.csv",
        ),
    ]:
        cube_path = Path("data/processed") / stage / "locked_forecasts.npz"
        for p in [point_file, daily_file, str(cube_path)]:
            inputs[p] = sha256(p)
        points = pd.read_csv(
            point_file,
            dtype={"platform_id": str},
            parse_dates=["date"],
            float_precision="round_trip",
        )
        points = points.loc[points.valid].copy()
        expected = pd.read_csv(
            daily_file, parse_dates=["date"], float_precision="round_trip"
        )
        index_keys = ["pass", "target", "horizon_days", "model", "date"]
        expected = expected.set_index(index_keys)
        max_gap, checked = 0.0, 0
        with np.load(cube_path) as cube:
            dates = pd.DatetimeIndex(cube["dates"])
            models = [k.split("__", 1)[1] for k in cube.files if k.startswith("h1__")]
            if region == "destination":
                models = json.loads(
                    Path(
                        "paper/destination_validation/frozen_protocol.json"
                    ).read_text()
                )["models"]
            for passage, g in points.groupby("pass"):
                i = dates.get_indexer(g.date)
                j = g["cell_index" if region == "source" else "cell"].to_numpy(int)
                if np.any(i < 0):
                    raise ValueError("point lies outside frozen cube dates")
                for h in [1, 7, 30]:
                    for model in models:
                        prediction = (
                            cube[f"h{h}__{model}"][i, j].astype(float)
                            if region == "source"
                            else forecast(cube, model, h)[i, j]
                        )
                        for target, truth in [
                            (
                                "iQuam",
                                g[
                                    "observed_celsius"
                                    if region == "source"
                                    else "observed"
                                ].to_numpy(float),
                            ),
                            ("matched_OISST", cube["analysis"][i, j].astype(float)),
                        ]:
                            key = dict(
                                region=region,
                                **{"pass": passage},
                                target=target,
                                horizon_days=h,
                                model=model,
                            )
                            p = platform_day_losses(g, prediction - truth)
                            daily = daily_losses(p)
                            old_target = (
                                "iQuam_buoys"
                                if region == "source" and target == "iQuam"
                                else target
                            )
                            old = expected.xs(
                                (passage, old_target, h, model), level=index_keys[:-1]
                            ).sort_index()
                            if not daily.index.equals(old.index):
                                raise ValueError(
                                    "sensitivity date support differs from original scoring"
                                )
                            max_gap = max(
                                max_gap,
                                float(
                                    np.max(
                                        abs(daily.to_numpy() - old[LOSSES].to_numpy())
                                    )
                                ),
                            )
                            checked += len(daily)
                            full.append({**key, **score_platform_days(p)})
                            deleted.append(deletion_scores(p).assign(**key))
                            for year, group in p.groupby(p.date.dt.year):
                                annual.append(
                                    {
                                        **key,
                                        "year": int(year),
                                        **score_platform_days(group),
                                    }
                                )
                            if h == 1 and model == models[0] and target == "iQuam":
                                weights.append(
                                    support_weights(p).assign(
                                        region=region, **{"pass": passage}
                                    )
                                )
        if max_gap > 1e-10 or checked != len(expected):
            raise ValueError("original daily buoy scores not reproduced")
        audits.append(
            {
                "region": region,
                "daily_rows_reproduced": checked,
                "maximum_loss_difference": max_gap,
            }
        )
    full = add_skills(pd.DataFrame(full))
    deleted = add_skills(pd.concat(deleted, ignore_index=True), deletion=True)
    annual = pd.DataFrame(annual)
    # Annual contrasts require year in the matching key, so score each year separately.
    annual = pd.concat(
        [add_skills(g).assign(year=year) for year, g in annual.groupby("year")],
        ignore_index=True,
    )
    support = pd.concat(weights, ignore_index=True)
    for name, frame in [
        ("full_metrics", full),
        ("deletion_metrics", deleted),
        ("annual_metrics", annual),
        ("platform_weights", support),
    ]:
        frame.to_csv(OUTPUT / f"{name}.csv", index=False)
    verify()
    after = protected_hashes()
    if before != after:
        raise ValueError("previous phase artifacts changed")
    record = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Retrospective descriptive support sensitivity after outcomes were known; no refitting, matching changes, new p-values, confidence intervals or independent observations.",
        "software_sha256": sha256(__file__),
        "report_software_sha256": sha256("src/evaluation/buoy_robustness_report.py"),
        "runtime_versions": {
            "python": runtime_platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
        },
        "input_sha256": inputs,
        "previous_phase_sha256": before,
        "previous_phase_file_count": len(before),
        "all_previous_phase_files_unchanged": True,
        "original_daily_score_audits": audits,
        "removal_units": "All composite platform type/ID combinations and all observed platform types; both passes, all 3 horizons, all 7 source and 13 destination models, both iQuam and same-point OISST targets.",
        "date_policy": "Reweight remaining platforms within each surviving date, then equal dates. Also report original full-sample loss restricted to those exact surviving dates; do not fill vanished dates.",
        "alternative_estimand": "Equal weight per platform over period, with equal dates within each platform; not the original estimand.",
        "concentration": "Sum each platform's daily 1/n_platforms weights divided by scoring dates. Inverse sum of squared period weights is descriptive concentration, not effective independent sample size.",
    }
    (OUTPUT / "evaluation_audit.json").write_text(
        json.dumps(record, indent=2, allow_nan=False) + "\n"
    )
    from src.evaluation.buoy_robustness_report import write_report

    write_report(OUTPUT, full, deleted, annual, support)
    REVIEWED.mkdir(parents=True, exist_ok=True)
    for p in OUTPUT.iterdir():
        if p.is_file() and p.name != "checksums.json":
            if p.name == "deletion_metrics.csv":
                (REVIEWED / (p.name + ".gz")).write_bytes(
                    gzip.compress(p.read_bytes(), mtime=0)
                )
                # This phase alone owns this generated, uncompressed reviewed copy.
                (REVIEWED / p.name).unlink(missing_ok=True)
            else:
                shutil.copyfile(p, REVIEWED / p.name)
    for root in [OUTPUT, REVIEWED]:
        checksums = {
            p.name: sha256(p)
            for p in sorted(root.iterdir())
            if p.is_file() and p.name != "checksums.json"
        }
        (root / "checksums.json").write_text(json.dumps(checksums, indent=2) + "\n")
    print(
        json.dumps(
            {
                "audits": audits,
                "protected_files": len(before),
                "full_rows": len(full),
                "deletion_rows": len(deleted),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
