"""Expanded historical selection and climatology-assisted anomaly-transfer sensitivity."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

import joblib
import numpy as np
import pandas as pd

from src.confirmation import verify_inputs
from src.independent import paired_loss_interval, quality_mask
from src.models.anomaly_transfer import fit_climate, design, decode
from src.models.process_transfer import fit_increment
from src.process_transfer import model_record
from src.publication import read_fields
from src.publication_delivery import hashes
from src.validation import sha256

CONFIG = Path("configs/anomaly_transfer.json")
OUTPUT = Path("data/processed/anomaly_transfer")
REVIEWED = Path("paper/anomaly_transfer")
UPSTREAM = Path("data/processed/process_transfer")


def config():
    return json.loads(CONFIG.read_text())


def inputs():
    manifest = json.loads((UPSTREAM / "checksums.json").read_text())
    paths = [
        UPSTREAM / n
        for n in [
            "regional_sst.csv",
            "yellow_bohai_forcing.csv",
            "northern_ecs_forcing.csv",
        ]
    ]
    for p in paths:
        if sha256(p) != manifest[p.name]:
            raise ValueError("upstream aggregate changed: " + str(p))
    frames = [
        pd.read_csv(p, index_col="date", parse_dates=True, float_precision="round_trip")
        for p in paths
    ]
    return (
        frames[0],
        dict(zip(["yellow_bohai", "northern_ecs"], frames[1:])),
        {str(p): sha256(p) for p in paths},
    )


def prepare():
    verify_inputs()
    _, _, digests = inputs()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    REVIEWED.mkdir(parents=True, exist_ok=True)
    record = {
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "config": config(),
        "config_sha256": sha256(CONFIG),
        "input_sha256": digests,
        "scope": "Local post-outcome design before new sensitivity scores. Not a public or prospective preregistration.",
    }
    p = REVIEWED / "design_record.json"
    if p.exists():
        old = json.loads(p.read_text())
        if (
            old["config_sha256"] != record["config_sha256"]
            or old["input_sha256"] != digests
        ):
            raise ValueError("recorded design/input changed")
    else:
        p.write_text(json.dumps(record, indent=2) + "\n")


def choose_source(
    x, origin, state, observed, climate, representation, family, candidates, cfg
):
    """Destination arguments are deliberately absent from this selection API."""
    rows = []
    for value in candidates:
        model = fit_increment(
            x,
            origin,
            state,
            family,
            value,
            cfg["train_end"],
            cfg["random_seed"],
            cfg["tree_estimators"],
        )
        predicted = decode(model.predict(x, origin), climate, representation)
        error = (predicted - observed).loc[
            cfg["selection_start"] : cfg["selection_end"]
        ]
        if not np.isfinite(error).all():
            raise ValueError("complete selection support required")
        row = {
            "hyperparameter": value,
            "rmse": float(np.sqrt(np.mean(error**2))),
            "n_days": len(error),
        }
        for year in error.index.year.unique():
            e = error.loc[str(year)]
            row[f"rmse_{year}"] = float(np.sqrt(np.mean(e**2)))
        if family == "ridge":
            valid = (
                (x.index <= cfg["train_end"])
                & np.isfinite(x.to_numpy()).all(axis=1)
                & np.isfinite(origin)
            )
            z = (x.loc[valid].to_numpy() - model.mean) / model.scale
            eigen = np.linalg.svd(z, compute_uv=False) ** 2
            row["effective_degrees_of_freedom"] = float(
                1 + np.sum(eigen / (eigen + value))
            )
        else:
            row["median_tree_leaves"] = float(
                np.median([t.tree_.n_leaves for t in model.fitted.estimators_])
            )
        rows.append(row)
    best = min(rows, key=lambda r: r["rmse"])
    for row in rows:
        row["selected"] = row is best
        row["selected_at_maximum_grid_value"] = best["hyperparameter"] == max(
            candidates
        )
    return best["hyperparameter"], rows


def evaluate():
    cfg = config()
    record = json.loads((REVIEWED / "design_record.json").read_text())
    sst, weather, digests = inputs()
    if sha256(CONFIG) != record["config_sha256"] or digests != record["input_sha256"]:
        raise ValueError("design/input mismatch")
    verify_inputs()
    protected = {
        str(p): sha256(p)
        for p in [
            *Path("paper").glob("*/frozen_protocol.json"),
            Path("data/processed/confirmation/locked_forecasts.npz"),
            Path("data/processed/confirmation/tree_models.joblib"),
            *UPSTREAM.glob("*"),
        ]
        if p.is_file()
    }
    climates = {
        d: fit_climate(
            sst[d],
            weather[d],
            cfg["train_end"],
            cfg["normalization_harmonics"],
            cfg["normalization_trend"],
        )
        for d in sst
    }
    (OUTPUT / "climatology_parameters.json").write_text(
        json.dumps({d: c.to_dict() for d, c in climates.items()}, indent=2) + "\n"
    )
    curves, forecasts, parameters, models = [], [], {}, {}
    narrow = pd.read_csv("paper/process_transfer/results/selection.csv")
    narrow_diffs = []
    for representation in cfg["representations"]:
        for group in cfg["feature_groups"]:
            end = cfg["date_end"] if group == "sst" else cfg["forcing_end"]
            series = {d: sst[d].loc[:end] for d in sst}
            forcing = {d: weather[d].reindex(series[d].index) for d in sst}
            source_design = design(
                series["yellow_bohai"],
                forcing["yellow_bohai"],
                climates["yellow_bohai"],
                representation,
                7,
                group,
            )
            for family, candidates in [
                ("ridge", cfg["ridge_alphas"]),
                ("trees", cfg["tree_min_samples_leaf"]),
            ]:
                selected, rows = choose_source(
                    *source_design,
                    series["yellow_bohai"],
                    climates["yellow_bohai"],
                    representation,
                    family,
                    candidates,
                    cfg,
                )
                for r in rows:
                    r.update(representation=representation, group=group, family=family)
                curves.extend(rows)
                if representation == "raw":
                    old = narrow.loc[narrow.family.eq(family) & narrow.group.eq(group)]
                    for _, r in old.iterrows():
                        new = next(
                            q for q in rows if q["hyperparameter"] == r.hyperparameter
                        )
                        diff = abs(new["rmse"] - r.rmse)
                        narrow_diffs.append(diff)
                        if diff > 1e-8:
                            raise ValueError(
                                "original narrow source selection did not reproduce"
                            )
                for h in cfg["horizons"]:
                    designs = {
                        d: design(
                            series[d], forcing[d], climates[d], representation, h, group
                        )
                        for d in sst
                    }
                    fitted = {
                        d: fit_increment(
                            *designs[d],
                            family,
                            selected,
                            cfg["train_end"],
                            cfg["random_seed"],
                            cfg["tree_estimators"],
                        )
                        for d in sst
                    }
                    key = f"{representation}__{family}__{group}__h{h}"
                    for d, model in fitted.items():
                        models[key + "__" + d] = model
                        parameters[key + "__" + d] = model_record(model)
                    for domain, mode, model in [
                        ("yellow_bohai", "source_local", fitted["yellow_bohai"]),
                        ("northern_ecs", "source_transfer", fitted["yellow_bohai"]),
                        ("northern_ecs", "destination_local", fitted["northern_ecs"]),
                    ]:
                        x, origin, _ = designs[domain]
                        prediction = decode(
                            model.predict(x, origin), climates[domain], representation
                        )
                        for period, (start, stop) in cfg["test_periods"].items():
                            if stop > end:
                                continue
                            q = pd.DataFrame(
                                {
                                    "date": series[domain].loc[start:stop].index,
                                    "observed": series[domain].loc[start:stop].values,
                                    "predicted": prediction.loc[start:stop].values,
                                    "period": period,
                                    "domain": domain,
                                    "fitting": mode,
                                    "representation": representation,
                                    "family": family,
                                    "group": group,
                                    "horizon_days": h,
                                }
                            )
                            if not np.isfinite(q.predicted).all():
                                raise ValueError("all evaluation days required")
                            forecasts.append(q)
                    print("Fitted", key, "source-selected", selected, flush=True)
    old_predictions = pd.read_csv(
        UPSTREAM / "predictions.csv",
        parse_dates=["date"],
        low_memory=False,
        float_precision="round_trip",
    )
    for domain in sst:
        cycle = climates[domain].sst_cycle.predict(sst.index)
        for h in cfg["horizons"]:
            for family, prediction in [
                (
                    "local_anomaly_persistence",
                    sst[domain].shift(h) + cycle - cycle.shift(h),
                ),
                ("raw_persistence", sst[domain].shift(h)),
            ]:
                for period, (start, stop) in cfg["test_periods"].items():
                    q = pd.DataFrame(
                        {
                            "date": sst.loc[start:stop].index,
                            "observed": sst[domain].loc[start:stop].values,
                            "predicted": prediction.loc[start:stop].values,
                            "period": period,
                            "domain": domain,
                            "fitting": "baseline",
                            "representation": "baseline",
                            "family": family,
                            "group": "sst",
                            "horizon_days": h,
                        }
                    )
                    old = old_predictions.loc[
                        (old_predictions.domain == domain)
                        & (old_predictions.period == period)
                        & (old_predictions.family == family)
                        & (old_predictions.horizon_days == h)
                    ]
                    if not np.allclose(q.predicted, old.predicted, atol=1e-10, rtol=0):
                        raise ValueError("original local persistence baseline differs")
                    forecasts.append(q)
    frame = pd.concat(forecasts, ignore_index=True)
    frame["error"] = frame.predicted - frame.observed
    frame["mse"] = frame.error**2
    frame["year"] = frame.date.dt.year
    frame["season"] = frame.date.dt.month.map(
        {
            12: "DJF",
            1: "DJF",
            2: "DJF",
            3: "MAM",
            4: "MAM",
            5: "MAM",
            6: "JJA",
            7: "JJA",
            8: "JJA",
            9: "SON",
            10: "SON",
            11: "SON",
        }
    )
    frame.to_csv(OUTPUT / "predictions.csv", index=False)
    keys = [
        "period",
        "domain",
        "fitting",
        "representation",
        "family",
        "group",
        "horizon_days",
    ]
    for extra, name in [
        ([], "metrics.csv"),
        (["year"], "annual_metrics.csv"),
        (["season"], "seasonal_metrics.csv"),
    ]:
        out = frame.groupby(keys + extra).agg(
            n_days=("mse", "size"), mse=("mse", "mean"), bias=("error", "mean")
        )
        out["rmse"] = np.sqrt(out.mse)
        out.reset_index().to_csv(OUTPUT / name, index=False)
    pd.DataFrame(curves).to_csv(OUTPUT / "selection.csv", index=False)
    (OUTPUT / "parameters.json").write_text(json.dumps(parameters, indent=2) + "\n")
    joblib.dump(
        {"models": models, "climates": climates}, OUTPUT / "models.joblib", compress=3
    )
    if any(sha256(p) != digest for p, digest in protected.items()):
        raise ValueError("a previous scientific record changed")
    audit = {
        "evaluated_utc": datetime.now(timezone.utc).isoformat(),
        "input_sha256": digests,
        "config_sha256": sha256(CONFIG),
        "design_sha256": sha256(REVIEWED / "design_record.json"),
        "software_sha256": {
            p: sha256(p)
            for p in [
                "src/anomaly_transfer.py",
                "src/models/anomaly_transfer.py",
                "src/models/process_transfer.py",
            ]
        },
        "protected_previous_files_sha256": protected,
        "all_previous_inputs_unchanged": True,
        "original_narrow_grid_max_selection_rmse_difference": max(narrow_diffs),
        "source_selected_hyperparameters_only": True,
        "destination_climatology_training_end": cfg["train_end"],
        "n_forecast_rows": len(frame),
        "model_archive_sha256": sha256(OUTPUT / "models.joblib"),
        "scope": cfg["scope"],
    }
    (OUTPUT / "evaluation_audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    intervals(frame, cfg)


def intervals(frame, cfg):
    rows = []
    keys = [
        "period",
        "domain",
        "fitting",
        "representation",
        "family",
        "group",
        "horizon_days",
    ]
    for key, q in frame.loc[frame.fitting.ne("baseline")].groupby(keys):
        period, domain, mode, representation, family, group, h = key
        baseline = frame.loc[
            (frame.period == period)
            & (frame.domain == domain)
            & (frame.family == "local_anomaly_persistence")
            & (frame.horizon_days == h)
        ]
        a = q.set_index("date").mse
        b = baseline.set_index("date").mse
        for block in cfg["bootstrap_block_days"]:
            result = paired_loss_interval(a, b, block, cfg)
            rows.append(
                {
                    **dict(zip(keys, key)),
                    "block_days": block,
                    "skill": 1 - np.sqrt(a.mean() / b.mean()),
                    **result,
                }
            )
    pd.DataFrame(rows).to_csv(OUTPUT / "descriptive_intervals.csv", index=False)


def external():
    verify_inputs()
    cfg = config()
    frozen = json.loads(Path("paper/validation/frozen_protocol.json").read_text())
    dates, fields, weights, fixed, *_ = read_fields(cfg, frozen)
    pos = {d: i for i, d in enumerate(dates)}
    regional = fields.astype(float) @ weights
    f = pd.read_csv(OUTPUT / "predictions.csv", parse_dates=["date"])
    f = f.loc[f.domain.eq("yellow_bohai") & f.fitting.eq("source_local")]
    forecasts = {
        (period, h, rep, family, group): g.set_index("date").predicted
        for (period, h, rep, family, group), g in f.groupby(
            ["period", "horizon_days", "representation", "family", "group"]
        )
    }
    rows = []
    with np.load("data/processed/confirmation/locked_forecasts.npz") as cube:
        index = {d: i for i, d in enumerate(pd.DatetimeIndex(cube["dates"]))}
        for period, (start, stop) in cfg["test_periods"].items():
            for day in pd.date_range(start, stop):
                raw = (
                    Path(
                        "data/raw/confirmation"
                        if day.year < 2026
                        else "data/raw/independent"
                    )
                    / f"amsr2-{day:%Y-%m-%d}.npz"
                )
                rec = json.loads(raw.with_suffix(".json").read_text())
                if sha256(raw) != rec["subset_sha256"]:
                    raise ValueError("external subset checksum differs")
                with np.load(raw) as obs:
                    if not np.array_equal(
                        obs["lat"], frozen["spatial_mask"]["lat"]
                    ) or not np.array_equal(obs["lon"], frozen["spatial_mask"]["lon"]):
                        raise ValueError("external grid differs")
                    valid = quality_mask(
                        obs["SST"][1],
                        obs["time"][1],
                        [
                            obs[k][1]
                            for k in [
                                "land_mask",
                                "coast_mask",
                                "sea_ice_mask",
                                "noobs_mask",
                            ]
                        ],
                        fixed,
                    )[fixed]
                    truth = obs["SST"][1][fixed].astype(float)
                if valid.sum() < 20:
                    continue
                w = weights[valid] / weights[valid].sum()
                for h in cfg["horizons"]:
                    origin = pos[day - pd.Timedelta(days=h)]
                    predictions = [
                        (
                            "baseline",
                            "grid_anomaly_persistence",
                            "sst",
                            cube[f"h{h}__grid_anomaly_persistence"][index[day]].astype(
                                float
                            ),
                        )
                    ]
                    predictions += [
                        (
                            rep,
                            family,
                            group,
                            fields[origin].astype(float)
                            + p.loc[day]
                            - regional[origin],
                        )
                        for (
                            period_key,
                            lead,
                            rep,
                            family,
                            group,
                        ), p in forecasts.items()
                        if period_key == period and lead == h
                    ]
                    for rep, family, group, pred in predictions:
                        for target, y in [
                            ("AMSR2_night", truth),
                            ("matched_OISST", fields[pos[day]].astype(float)),
                        ]:
                            e = pred[valid] - y[valid]
                            rows.append(
                                {
                                    "date": day,
                                    "period": period,
                                    "representation": rep,
                                    "family": family,
                                    "group": group,
                                    "horizon_days": h,
                                    "target": target,
                                    "n_cells": int(valid.sum()),
                                    "mse": float(w @ e**2),
                                    "bias": float(w @ e),
                                }
                            )
    frame = pd.DataFrame(rows)
    frame["year"] = frame.date.dt.year
    original = pd.read_csv(
        "data/processed/confirmation/daily_scores.csv", parse_dates=["date"]
    )
    original = (
        original.loc[
            original.target.eq("matched_grid_AMSR2")
            & original["pass"].eq("descending")
            & original.model.eq("grid_anomaly_persistence")
        ]
        .set_index(["date", "horizon_days"])
        .sort_index()
    )
    repeat = (
        frame.loc[
            frame.target.eq("AMSR2_night") & frame.family.eq("grid_anomaly_persistence")
        ]
        .set_index(["date", "horizon_days"])
        .sort_index()
    )
    if not repeat.index.equals(original.index) or not np.allclose(
        repeat.mse, original.mse, rtol=0, atol=1e-12
    ):
        raise ValueError("old satellite baseline/support did not reproduce")
    frame.to_csv(OUTPUT / "external_daily_scores.csv", index=False)
    keys = ["period", "target", "representation", "family", "group", "horizon_days"]
    for extra, name in [
        ([], "external_metrics.csv"),
        (["year"], "external_annual_metrics.csv"),
    ]:
        out = frame.groupby(keys + extra).agg(
            n_days=("mse", "size"), mse=("mse", "mean"), bias=("bias", "mean")
        )
        out["rmse"] = np.sqrt(out.mse)
        out.reset_index().to_csv(OUTPUT / name, index=False)
    (OUTPUT / "external_audit.json").write_text(
        json.dumps(
            {
                "evaluated_utc": datetime.now(timezone.utc).isoformat(),
                "software_sha256": sha256("src/anomaly_transfer.py"),
                "predictions_sha256": sha256(OUTPUT / "predictions.csv"),
                "original_baseline_support_and_loss_reproduced": True,
                "n_days_by_period": frame.groupby("period").date.nunique().to_dict(),
                "scope": "Descriptive new source projections on already viewed satellite observations; no destination instrument test and no new p values.",
            },
            indent=2,
        )
        + "\n"
    )


def deliver():
    from src.evaluation.anomaly_transfer_report import write_report

    write_report(OUTPUT, config())
    target = REVIEWED / "results"
    target.mkdir(parents=True, exist_ok=True)
    for p in OUTPUT.iterdir():
        if p.suffix in {".csv", ".json", ".png", ".svg", ".md"} and p.name not in {
            "predictions.csv",
            "external_daily_scores.csv",
            "benchmark_predictions.csv",
            "external_benchmark_daily_scores.csv",
            "checksums.json",
        }:
            shutil.copy2(p, target / p.name)
    (target / "checksums.json").write_text(json.dumps(hashes(target), indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["prepare", "evaluate", "external", "deliver"])
    args = parser.parse_args()
    {
        "prepare": prepare,
        "evaluate": evaluate,
        "external": external,
        "deliver": deliver,
    }[args.stage]()


if __name__ == "__main__":
    main()
