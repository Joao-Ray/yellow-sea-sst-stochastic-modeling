"""Lock then score a previously unscored destination subset of cached instruments."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from src.confirmation import verify_inputs as verify_original
from src.evaluation.publication_stats import holm_adjust, paired_block_inference
from src.independent import quality_mask
from src.insitu import equal_platform_daily, nearest_cells
from src.models.seasonal import seasonal_design
from src.publication_delivery import hashes
from src.validation import sha256

CONFIG = Path("configs/destination_validation.json")
REVIEWED = Path("paper/destination_validation")
FROZEN = REVIEWED / "frozen_protocol.json"
OUTPUT = Path("data/processed/destination_validation")
SOURCE_ROOTS = [
    Path("data/raw/confirmation"),
    Path("data/raw/independent"),
    Path("data/raw/insitu"),
]


def dump(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def array_hash(value):
    return hashlib.sha256(
        np.ascontiguousarray(value, dtype="<f8").tobytes()
    ).hexdigest()


def grid_cycles(values, dates, train_end):
    """No evaluation values enter the seasonal/trend coefficient fit."""
    train = dates <= pd.Timestamp(train_end)
    design = seasonal_design(dates, dates[0], 3, True)
    beta = np.linalg.lstsq(design[train], values[train], rcond=None)[0]
    return design @ beta, beta


def forecast(cube, model, h):
    key = f"h{h}__{model}"
    if key in cube:
        return cube[key]
    return cube[f"origin_h{h}"] + cube[f"delta_h{h}__{model}"][:, None]


def point_geography(
    lat, lon, destination_lat, destination_lon, source_lat, source_lon, cfg
):
    cell, destination_distance = nearest_cells(
        lat, lon, destination_lat, destination_lon
    )
    _, source_distance = nearest_cells(lat, lon, source_lat, source_lon)
    keep = (destination_distance <= cfg["buoy_max_distance_km"]) & (
        source_distance > cfg["buoy_exclude_within_source_km"]
    )
    return cell, destination_distance, source_distance, keep


def prepare():
    if FROZEN.exists():
        verify(require_public=False)
        print("Existing destination lock verified; not overwritten")
        return
    verify_original()
    cfg = json.loads(CONFIG.read_text())
    OUTPUT.mkdir(parents=True, exist_ok=True)
    REVIEWED.mkdir(parents=True, exist_ok=True)
    prior_audit = json.loads(
        Path("data/processed/anomaly_transfer/evaluation_audit.json").read_text()
    )
    for path, digest in prior_audit["protected_previous_files_sha256"].items():
        if sha256(path) != digest:
            raise ValueError("prior protected file changed: " + path)
    grid = np.load("data/processed/process_transfer/domains.npz")
    files = sorted(Path("data/raw/research").glob("*.nc")) + sorted(
        Path("data/raw/validation").glob("*.nc")
    )
    input_hashes = {}
    for p in files:
        digest = json.loads(p.with_suffix(".json").read_text())["sha256"]
        if sha256(p) != digest:
            raise ValueError("OISST source changed")
        input_hashes[str(p)] = digest
    with xr.open_mfdataset(files, combine="by_coords", engine="netcdf4") as ds:
        field = ds.sst.load()
    dates = pd.DatetimeIndex(field.time.values)
    yy, xx = np.meshgrid(field.lat.values, field.lon.values, indexing="ij")
    mask = np.zeros(yy.shape, bool)
    for y, x in zip(grid["northern_ecs__lat"], grid["northern_ecs__lon"]):
        mask |= (yy == y) & (xx == x)
    if mask.sum() != 230 or not np.array_equal(yy[mask], grid["northern_ecs__lat"]):
        raise ValueError("destination coordinate support changed")
    values = field.values[:, mask].astype(float)
    if not np.isfinite(values).all():
        raise ValueError("no destination imputation permitted")
    weights = grid["northern_ecs__weights"]
    region = values @ weights
    recorded = pd.read_csv(
        "data/processed/process_transfer/regional_sst.csv",
        index_col="date",
        parse_dates=True,
        float_precision="round_trip",
    ).northern_ecs
    if not dates.equals(recorded.index) or not np.allclose(
        region, recorded, atol=1e-10, rtol=0
    ):
        raise ValueError("destination mean did not reproduce")
    cycle, beta = grid_cycles(values, dates, cfg["train_end"])
    selected = np.flatnonzero((dates >= cfg["date_start"]) & (dates <= cfg["date_end"]))
    target_dates = dates[selected]
    expected = pd.date_range(cfg["date_start"], cfg["date_end"])
    if not target_dates.equals(expected):
        raise ValueError("incomplete target calendar")
    phi = json.loads(
        Path("data/processed/anomaly_transfer/benchmark_audit.json").read_text()
    )["training_phi_and_pair_count"]
    frame = pd.read_csv(
        "data/processed/anomaly_transfer/predictions.csv",
        parse_dates=["date"],
        float_precision="round_trip",
    )
    frame = frame.loc[frame.domain.eq("northern_ecs") & frame.group.eq("sst")]
    refs = pd.read_csv(
        "data/processed/anomaly_transfer/benchmark_predictions.csv",
        parse_dates=["date"],
        float_precision="round_trip",
    )
    refs = refs.loc[refs.domain.eq("northern_ecs")]
    models = [
        "raw_ridge",
        "raw_trees",
        "anomaly_ridge",
        "anomaly_trees",
        "projected_climatology",
        "projected_local_ar1",
        "projected_source_ar1",
        "projected_anomaly_persistence",
        "raw_persistence",
        "grid_climatology",
        "grid_source_ar1",
        "grid_local_ar1",
        "grid_anomaly_persistence",
    ]
    cube = {
        "dates": target_dates.strftime("%Y-%m-%d").to_numpy(dtype="U10"),
        "analysis": values[selected],
        "weights": weights,
        "lat": yy[mask],
        "lon": xx[mask],
        "fixed_mask": mask,
        "source_lat": grid["yellow_bohai__lat"],
        "source_lon": grid["yellow_bohai__lon"],
    }
    fingerprints = {}
    for h in cfg["horizons"]:
        origins = dates.get_indexer(target_dates - pd.Timedelta(days=h))
        if (origins < 0).any():
            raise ValueError("missing origins")
        cube[f"origin_h{h}"] = values[origins]
        for model in models[:9]:
            if model.startswith(("raw_", "anomaly_")) and model != "raw_persistence":
                rep, family = model.split("_", 1)
                q = frame.loc[
                    frame.fitting.eq("source_transfer")
                    & frame.representation.eq(
                        "raw" if rep == "raw" else "seasonal_anomaly"
                    )
                    & frame.family.eq(family)
                    & frame.horizon_days.eq(h)
                ]
            elif model in {"projected_anomaly_persistence", "raw_persistence"}:
                q = frame.loc[
                    frame.fitting.eq("baseline")
                    & frame.family.eq(
                        "local_anomaly_persistence"
                        if model.startswith("projected")
                        else model
                    )
                    & frame.horizon_days.eq(h)
                ]
            else:
                name = {
                    "projected_climatology": "training_climatology",
                    "projected_local_ar1": "local_anomaly_ar1",
                    "projected_source_ar1": "source_anomaly_ar1_transfer",
                }[model]
                q = refs.loc[refs.model.eq(name) & refs.horizon_days.eq(h)]
            q = q.set_index("date").sort_index()
            if not q.index.equals(target_dates):
                raise ValueError("projection must use every common target date")
            cube[f"delta_h{h}__{model}"] = q.predicted.to_numpy() - region[origins]
        cube[f"h{h}__grid_climatology"] = cycle[selected]
        for model, decay in [
            ("grid_source_ar1", phi["yellow_bohai"][0]),
            ("grid_local_ar1", phi["northern_ecs"][0]),
            ("grid_anomaly_persistence", 1.0),
        ]:
            cube[f"h{h}__{model}"] = cycle[selected] + decay**h * (
                values[origins] - cycle[origins]
            )
        for model in models:
            prediction = forecast(cube, model, h)
            if not np.isfinite(prediction).all():
                raise ValueError("nonfinite locked prediction")
            fingerprints[f"h{h}__{model}"] = array_hash(prediction)
    np.savez_compressed(OUTPUT / "locked_forecasts.npz", **cube)
    dump(
        REVIEWED / "grid_parameters.json",
        {
            "training_end": cfg["train_end"],
            "harmonics": 3,
            "linear_trend": True,
            "origin": str(dates[0].date()),
            "coefficients": beta.tolist(),
            "regional_phi": phi,
            "scope": "Grid seasonal coefficients fitted on 2010-2019 only; regional decay coefficients copied from prior training-only reference.",
        },
    )
    manifest = []
    for root in SOURCE_ROOTS:
        for p in sorted(root.glob("*.npz")):
            meta_path = p.with_suffix(".json")
            meta = json.loads(meta_path.read_text())
            digest = sha256(p)
            if meta["subset_sha256"] != digest:
                raise ValueError("instrument cache identity changed")
            manifest.append(
                {
                    "path": str(p),
                    "sha256": digest,
                    "metadata_path": str(meta_path),
                    "metadata_sha256": sha256(meta_path),
                    "source_url": meta["source_url"],
                    "acquired_utc": meta["acquired_utc"],
                }
            )
    if len(manifest) != 1096 + 243 + 36:
        raise ValueError("all expected existing source files required")
    dump(REVIEWED / "source_manifest.json", manifest)
    protect = {}
    for stage in ["process_transfer", "anomaly_transfer", "confirmation", "insitu"]:
        for path in (Path("data/processed") / stage).iterdir():
            if path.is_file():
                protect[str(path)] = sha256(path)
    for path in Path("paper").glob("*/frozen_protocol.json"):
        protect[str(path)] = sha256(path)
    for path in [
        CONFIG,
        OUTPUT / "locked_forecasts.npz",
        REVIEWED / "source_manifest.json",
        REVIEWED / "grid_parameters.json",
        Path("data/processed/anomaly_transfer/predictions.csv"),
        Path("data/processed/anomaly_transfer/benchmark_predictions.csv"),
        Path("data/processed/process_transfer/domains.npz"),
    ]:
        input_hashes[str(path)] = sha256(path)
    software = [
        Path(__file__),
        Path("src/independent.py"),
        Path("src/insitu.py"),
        Path("src/evaluation/publication_stats.py"),
        Path("src/models/seasonal.py"),
    ]
    frozen = {
        "frozen_utc": datetime.now(timezone.utc).isoformat(),
        "config": cfg,
        "models": models,
        "input_sha256": input_hashes,
        "software_sha256": {
            str(p.relative_to(Path.cwd()) if p.is_absolute() else p): sha256(p)
            for p in software
        },
        "forecast_array_sha256": fingerprints,
        "protected_previous_sha256": protect,
        "external_files_previously_acquired": True,
        "destination_instrument_scores_previously_produced": False,
        "chronology_correction": "Earlier process_external audit said destination satellite observations were not acquired. The cached full rectangular subsets already included these cells; they had not been evaluated for the destination. Preserve that historical audit and correct its acquisition wording here.",
        "source_counts": {
            "AMSR2_2023_2025": 1096,
            "AMSR2_2026_Jan_Aug": 243,
            "iQuam_months": 36,
        },
        "scope": cfg["scope"],
    }
    dump(FROZEN, frozen)
    print(
        json.dumps(
            {
                "protocol_sha256": sha256(FROZEN),
                "forecast_dates": len(target_dates),
                "models": len(models),
                "destination_cells": int(mask.sum()),
                "source_files": len(manifest),
            },
            indent=2,
        )
    )


def verify(require_public=True):
    frozen = json.loads(FROZEN.read_text())
    for section in ["input_sha256", "software_sha256", "protected_previous_sha256"]:
        for path, digest in frozen[section].items():
            if sha256(path) != digest:
                raise ValueError("locked item changed: " + path)
    for item in json.loads((REVIEWED / "source_manifest.json").read_text()):
        if (
            sha256(item["path"]) != item["sha256"]
            or sha256(item["metadata_path"]) != item["metadata_sha256"]
        ):
            raise ValueError("instrument version changed")
    with np.load(OUTPUT / "locked_forecasts.npz") as cube:
        for h in frozen["config"]["horizons"]:
            for model in frozen["models"]:
                if (
                    array_hash(forecast(cube, model, h))
                    != frozen["forecast_array_sha256"][f"h{h}__{model}"]
                ):
                    raise ValueError("projected forecast fingerprint changed")
    if require_public:
        lock = json.loads((REVIEWED / "public_lock.json").read_text())
        if (
            lock["protocol_sha256"] != sha256(FROZEN)
            or not lock["verified_remote_protocol_bytes"]
        ):
            raise ValueError("public protocol verification required before scoring")
        if datetime.fromisoformat(lock["verified_utc"]) < datetime.fromisoformat(
            frozen["frozen_utc"]
        ):
            raise ValueError("invalid public chronology")
    return frozen


def aggregate(daily, prefix):
    daily = daily.copy()
    if daily.empty:
        pd.DataFrame(
            columns=[
                "date",
                "period",
                "target",
                "pass",
                "horizon_days",
                "model",
                "mse",
                "mae",
                "bias",
            ]
        ).to_csv(OUTPUT / f"{prefix}_daily_scores.csv", index=False)
        for label, extra in [
            ("metrics", []),
            ("annual_metrics", ["year"]),
            ("seasonal_metrics", ["season"]),
        ]:
            pd.DataFrame(
                columns=[
                    "period",
                    "target",
                    "pass",
                    "horizon_days",
                    "model",
                    *extra,
                    "n_days",
                    "mse",
                    "mae",
                    "bias",
                    "rmse",
                ]
            ).to_csv(OUTPUT / f"{prefix}_{label}.csv", index=False)
        return daily
    daily["year"] = daily.date.dt.year
    daily["season"] = daily.date.dt.month.map(
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
    daily.to_csv(OUTPUT / f"{prefix}_daily_scores.csv", index=False)
    keys = ["period", "target", "pass", "horizon_days", "model"]
    for extra, label in [
        ([], "metrics"),
        (["year"], "annual_metrics"),
        (["season"], "seasonal_metrics"),
    ]:
        result = daily.groupby(keys + extra).agg(
            n_days=("mse", "size"),
            mse=("mse", "mean"),
            mae=("mae", "mean"),
            bias=("bias", "mean"),
        )
        result["rmse"] = np.sqrt(result.mse)
        result.reset_index().to_csv(OUTPUT / f"{prefix}_{label}.csv", index=False)
    return daily


def satellite(cube, frozen):
    cfg = frozen["config"]
    dates = pd.DatetimeIndex(cube["dates"])
    fixed, weights = cube["fixed_mask"], cube["weights"]
    rows, coverage = [], []
    predictions = {
        (h, m): forecast(cube, m, h) for h in cfg["horizons"] for m in frozen["models"]
    }
    for i, day in enumerate(dates):
        root = SOURCE_ROOTS[0 if day.year < 2026 else 1]
        path = root / f"amsr2-{day:%Y-%m-%d}.npz"
        with np.load(path) as obs:
            yy, xx = np.meshgrid(obs["lat"], obs["lon"], indexing="ij")
            if not np.array_equal(yy[fixed], cube["lat"]) or not np.array_equal(
                xx[fixed], cube["lon"]
            ):
                raise ValueError("external coordinate order mismatch")
            for pass_index, passage in enumerate(["afternoon", "nighttime"]):
                valid = quality_mask(
                    obs["SST"][pass_index],
                    obs["time"][pass_index],
                    [
                        obs[k][pass_index]
                        for k in [
                            "land_mask",
                            "coast_mask",
                            "sea_ice_mask",
                            "noobs_mask",
                        ]
                    ],
                    fixed,
                )[fixed]
                n = int(valid.sum())
                scored = n >= cfg["minimum_satellite_cells"]
                coverage.append(
                    {
                        "date": day,
                        "year": day.year,
                        "pass": passage,
                        "n_cells": n,
                        "valid_weight_fraction": float(weights[valid].sum()),
                        "scored": scored,
                    }
                )
                if not scored:
                    continue
                w = weights[valid] / weights[valid].sum()
                truths = {
                    "AMSR2": obs["SST"][pass_index][fixed][valid].astype(float),
                    "matched_OISST": cube["analysis"][i, valid],
                }
                for (h, model), prediction in predictions.items():
                    for target, truth in truths.items():
                        error = prediction[i, valid] - truth
                        rows.append(
                            {
                                "date": day,
                                "period": "2023-2025"
                                if day.year < 2026
                                else "2026-Jan-Aug",
                                "target": target,
                                "pass": passage,
                                "horizon_days": h,
                                "model": model,
                                "n_cells": n,
                                "mse": float(w @ error**2),
                                "mae": float(w @ abs(error)),
                                "bias": float(w @ error),
                            }
                        )
    coverage = pd.DataFrame(coverage)
    coverage.to_csv(OUTPUT / "satellite_coverage.csv", index=False)
    daily = aggregate(pd.DataFrame(rows), "satellite")
    counts = (
        coverage.loc[coverage["pass"].eq("nighttime") & coverage.year.lt(2026)]
        .groupby("year")
        .scored.sum()
        .reindex([2023, 2024, 2025], fill_value=0)
    )
    adequate = bool((counts >= cfg["minimum_primary_days_per_year"]).all())
    inference = []
    if adequate:
        primary = daily.loc[
            daily.period.eq("2023-2025")
            & daily.target.eq("AMSR2")
            & daily["pass"].eq("nighttime")
        ]
        for block in cfg["bootstrap_block_days"]:
            for h in cfg["horizons"]:
                losses = primary.loc[primary.horizon_days.eq(h)].pivot(
                    index="date", columns="model", values="mse"
                )
                if losses.isna().any().any():
                    raise ValueError(
                        "every model must have identical observation support"
                    )
                for model in cfg["primary_models"]:
                    for baseline in cfg["primary_baselines"]:
                        inference.append(
                            {
                                "model": model,
                                "baseline": baseline,
                                "horizon_days": h,
                                "rmse_skill": float(
                                    1
                                    - np.sqrt(
                                        losses[model].mean() / losses[baseline].mean()
                                    )
                                ),
                                **paired_block_inference(
                                    losses[model],
                                    losses[baseline],
                                    block,
                                    cfg["bootstrap_replicates"],
                                    cfg["bootstrap_seed"],
                                ),
                            }
                        )
        inf = pd.DataFrame(inference)
        for block in cfg["bootstrap_block_days"]:
            take = inf.bootstrap_block_days.eq(block)
            if take.sum() != cfg["primary_family_size"]:
                raise ValueError("predefined family incomplete")
            inf.loc[take, "p_holm_18"] = holm_adjust(
                inf.loc[take, "p_bootstrap_two_sided"]
            )
    else:
        inf = pd.DataFrame(
            columns=[
                "model",
                "baseline",
                "horizon_days",
                "rmse_skill",
                "bootstrap_block_days",
                "p_holm_18",
            ]
        )
    inf.to_csv(OUTPUT / "primary_inference.csv", index=False)
    return {
        "primary_coverage_gate_passed": adequate,
        "nighttime_days_by_primary_year": {str(k): int(v) for k, v in counts.items()},
        "minimum_days_per_year": cfg["minimum_primary_days_per_year"],
        "primary_family_size": cfg["primary_family_size"],
        "inference_suppressed": not adequate,
    }


def buoys(cube, frozen):
    cfg = frozen["config"]
    dates = pd.DatetimeIndex(cube["dates"])
    rows, coverage, points = [], [], []
    for path in sorted(SOURCE_ROOTS[2].glob("iquam-*.npz")):
        with np.load(path) as obs:
            q = pd.DataFrame({k: obs[k] for k in obs.files})
        q["date"] = (
            pd.Timestamp("1981-01-01") + pd.to_timedelta(q.time.astype(float), unit="s")
        ).dt.normalize()
        q["observed"] = q.sst.astype(float) - 273.15
        cell, distance, source_distance, geography = point_geography(
            q.lat.to_numpy(float),
            q.lon.to_numpy(float),
            cube["lat"],
            cube["lon"],
            cube["source_lat"],
            cube["source_lon"],
            cfg,
        )
        q["cell"] = cell
        q["distance_km"] = distance
        q["source_distance_km"] = source_distance
        q["pass"] = np.where(
            (q.sst_flags.astype(int) & 2).eq(0), "nighttime", "daytime"
        )
        q["valid"] = (
            geography
            & q.quality_level.eq(cfg["buoy_quality_level"])
            & q.platform_type.isin(cfg["buoy_platform_types"])
            & np.isfinite(q.observed)
            & q.observed.between(-2, 35)
            & q.date.between(cfg["date_start"], cfg["primary_end"])
            & q.date.dt.strftime("%Y%m").eq(path.stem.removeprefix("iquam-"))
            & q.platform_id.str.strip().ne("")
            & (q.sst_flags.astype(int) & 1).eq(0)
        )
        for passage, group in q.groupby("pass"):
            coverage.append(
                {
                    "month": path.stem.removeprefix("iquam-"),
                    "pass": passage,
                    "geographic_crop_records": len(group),
                    "within_destination_20km": int(
                        (group.distance_km <= cfg["buoy_max_distance_km"]).sum()
                    ),
                    "excluded_near_source_records": int(
                        (
                            (group.distance_km <= cfg["buoy_max_distance_km"])
                            & (
                                group.source_distance_km
                                <= cfg["buoy_exclude_within_source_km"]
                            )
                        ).sum()
                    ),
                    "valid_records": int(group.valid.sum()),
                }
            )
        points.append(q.loc[q.valid].copy())
    q = pd.concat(points, ignore_index=True)
    pd.DataFrame(coverage).to_csv(OUTPUT / "buoy_coverage.csv", index=False)
    q.to_csv(OUTPUT / "matched_buoy_points.csv", index=False)
    if q.empty:
        aggregate(pd.DataFrame(), "buoy")
        pd.DataFrame(
            columns=[
                "pass",
                "platform_type",
                "platform_id",
                "n_records",
                "n_days",
                "first_date",
                "last_date",
            ]
        ).to_csv(OUTPUT / "buoy_platform_support.csv", index=False)
        return {
            "nighttime_days_by_year": {str(y): 0 for y in [2023, 2024, 2025]},
            "nighttime_records": 0,
            "nighttime_platform_type_id_pairs": 0,
            "minimum_days_per_year": cfg["minimum_buoy_days_per_year"],
            "coverage_gate_passed": False,
            "all_retained_points_outside_previous_source_matching_radius": True,
            "inference": "No valid destination records; inference suppressed, thresholds unchanged.",
        }
    for passage, group in q.groupby("pass"):
        i = dates.get_indexer(group.date)
        j = group.cell.to_numpy(int)
        if (i < 0).any():
            raise ValueError("buoy outside locked calendar")
        for h in cfg["horizons"]:
            for model in frozen["models"]:
                prediction = forecast(cube, model, h)[i, j]
                for target, truth in [
                    ("iQuam", group.observed.to_numpy(float)),
                    ("matched_OISST", cube["analysis"][i, j]),
                ]:
                    scored = equal_platform_daily(group, prediction - truth)
                    (
                        scored["period"],
                        scored["target"],
                        scored["pass"],
                        scored["horizon_days"],
                        scored["model"],
                    ) = "2023-2025", target, passage, h, model
                    rows.extend(scored.to_dict("records"))
    aggregate(pd.DataFrame(rows), "buoy")
    support = (
        q.groupby(["pass", "platform_type", "platform_id"])
        .agg(
            n_records=("date", "size"),
            n_days=("date", "nunique"),
            first_date=("date", "min"),
            last_date=("date", "max"),
        )
        .reset_index()
    )
    support.to_csv(OUTPUT / "buoy_platform_support.csv", index=False)
    night = q.loc[q["pass"].eq("nighttime")]
    counts = (
        night.groupby(night.date.dt.year)
        .date.nunique()
        .reindex([2023, 2024, 2025], fill_value=0)
    )
    return {
        "nighttime_days_by_year": {str(k): int(v) for k, v in counts.items()},
        "nighttime_records": len(night),
        "nighttime_platform_type_id_pairs": len(
            night[["platform_type", "platform_id"]].drop_duplicates()
        ),
        "minimum_days_per_year": cfg["minimum_buoy_days_per_year"],
        "coverage_gate_passed": bool(
            (counts >= cfg["minimum_buoy_days_per_year"]).all()
        ),
        "all_retained_points_outside_previous_source_matching_radius": bool(
            (q.source_distance_km > cfg["buoy_exclude_within_source_km"]).all()
        ),
        "inference": "Descriptive only; QC reference and assimilation dependencies remain.",
    }


def evaluate():
    frozen = verify()
    started = datetime.now(timezone.utc).isoformat()
    with np.load(OUTPUT / "locked_forecasts.npz") as cube:
        sat = satellite(cube, frozen)
        insitu = buoys(cube, frozen)
    verify()
    dump(
        OUTPUT / "evaluation_audit.json",
        {
            "evaluation_started_utc": started,
            "evaluation_finished_utc": datetime.now(timezone.utc).isoformat(),
            "protocol_sha256": sha256(FROZEN),
            "public_lock": json.loads((REVIEWED / "public_lock.json").read_text()),
            "satellite": sat,
            "buoys": insitu,
            "all_forecast_fingerprints_and_previous_files_unchanged": True,
            "software_sha256": sha256(__file__),
            "scope": frozen["scope"],
        },
    )
    dump(OUTPUT / "checksums.json", hashes(OUTPUT))
    print(json.dumps({"satellite": sat, "buoys": insitu}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["prepare", "evaluate", "deliver"])
    args = parser.parse_args()
    if args.stage == "prepare":
        prepare()
    elif args.stage == "evaluate":
        evaluate()
    else:
        from src.evaluation.destination_report import deliver

        deliver()


if __name__ == "__main__":
    main()
