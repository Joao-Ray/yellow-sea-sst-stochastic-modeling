"""Audited exploratory extension for an English scientific manuscript."""

import argparse
from datetime import datetime, timezone
import json
from importlib.metadata import version
import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from src.evaluation.publication_stats import (
    holm_adjust,
    interval_score,
    loss_components,
    paired_block_inference,
)
from src.independent import load_inputs, quality_mask
from src.models.seasonal import fit_seasonal, seasonal_design
from src.models.spatial import fit_spatial_candidates
from src.validation import frozen_means, sha256


def read_fields(config, frozen):
    files = sorted(Path("data/raw/research").glob("*.nc")) + sorted(
        Path("data/raw/validation").glob("*.nc")
    )
    records = []
    for p in files:
        record = json.loads(p.with_suffix(".json").read_text())
        if sha256(p) != record["sha256"]:
            raise ValueError("NOAA source checksum differs: " + str(p))
        records.append(
            {
                "path": str(p),
                "sha256": record["sha256"],
                "source_url": record.get("request_url", record.get("url")),
            }
        )
    with xr.open_mfdataset(files, combine="by_coords", engine="netcdf4") as ds:
        data = ds.sst.load()
    dates = pd.DatetimeIndex(data.time.values)
    if not dates.equals(pd.date_range(config["date_start"], config["date_end"])):
        raise ValueError("field cube has missing or extra dates")
    mask = frozen["spatial_mask"]
    if not np.array_equal(data.lat, mask["lat"]) or not np.array_equal(
        data.lon, mask["lon"]
    ):
        raise ValueError("frozen and acquired grids differ")
    fixed = np.zeros((len(mask["lat"]), len(mask["lon"])), bool)
    for lat, lon in mask["selected_cells"]:
        fixed[mask["lat"].index(lat), mask["lon"].index(lon)] = True
    ygrid, xgrid = np.meshgrid(mask["lat"], mask["lon"], indexing="ij")
    lat, lon = ygrid[fixed], xgrid[fixed]
    weights = np.cos(np.deg2rad(lat))
    weights /= weights.sum()
    land = ~np.isfinite(data.values[0])
    landlat, landlon = np.deg2rad(ygrid[land]), np.deg2rad(xgrid[land])
    phi, lam = np.deg2rad(lat)[:, None], np.deg2rad(lon)[:, None]
    haversine = (
        np.sin((phi - landlat) / 2) ** 2
        + np.cos(phi) * np.cos(landlat) * np.sin((lam - landlon) / 2) ** 2
    )
    distance = (2 * 6371.0088 * np.arcsin(np.sqrt(np.clip(haversine, 0, 1)))).min(
        axis=1
    )
    values = data.values[:, fixed]
    if not np.isfinite(values).all():
        raise ValueError("complete fixed ocean fields required for the spatial control")
    return dates, values, weights, fixed, lat, lon, distance, records


def season_labels(dates, config):
    result = np.empty(len(dates), dtype="U3")
    for name, months in config["seasons"].items():
        result[np.isin(dates.month, months)] = name
    return result


def daily_score(forecast, observed, weights):
    error = np.asarray(forecast, float) - np.asarray(observed, float)
    w = weights / weights.sum()
    return {
        "mse": float(w @ error**2),
        "mae": float(w @ np.abs(error)),
        "bias": float(w @ error),
    }


def aggregate_scores(daily):
    rows = []
    keys = ["period", "target", "pass", "horizon_days"]
    for key, group in daily.groupby(keys):
        base = {
            name: g.set_index("date").sort_index() for name, g in group.groupby("model")
        }
        for name, g in base.items():
            row = dict(zip(keys, key))
            row.update(
                model=name,
                n_days=len(g),
                n_cell_day_pairs=int(g.n_cells.sum()),
                rmse=float(np.sqrt(g.mse.mean())),
                mae=float(g.mae.mean()),
                bias_celsius=float(g.bias.mean()),
            )
            for baseline in ["frozen_anomaly_projection", "grid_anomaly_persistence"]:
                if not g.index.equals(base[baseline].index) or not np.array_equal(
                    g.n_cells, base[baseline].n_cells
                ):
                    raise ValueError("spatial comparisons do not share scoring support")
                row["skill_vs_" + baseline] = 1 - row["rmse"] / np.sqrt(
                    base[baseline].mse.mean()
                )
            rows.append(row)
    return pd.DataFrame(rows)


def primary_inference(config):
    temporal = pd.read_csv(
        "data/processed/validation/predictions.csv", parse_dates=["date"]
    )
    external = pd.read_csv(
        "data/processed/independent/daily_metrics.csv", parse_dates=["date"]
    )
    frozen = json.loads(Path("paper/validation/frozen_protocol.json").read_text())
    rows = []
    for block in config["bootstrap_block_days"]:
        for target in ["regional_OISST_2026", "matched_AMSR2_night_2026"]:
            for h in config["horizons"]:
                chosen = frozen["selected_methods"][str(h)]
                source = (
                    temporal
                    if target.startswith("regional")
                    else external.loc[external["pass"].eq("descending")]
                )
                source = source.loc[source.horizon_days.eq(h)]
                series = {}
                for model in [chosen, "persistence"]:
                    g = (
                        source.loc[source.model.eq(model)]
                        .set_index("date")
                        .sort_index()
                    )
                    series[model] = (
                        (g.predicted_sst_celsius - g.observed_sst_celsius) ** 2
                        if target.startswith("regional")
                        else g.mse
                    )
                row = {
                    "target": target,
                    "horizon_days": h,
                    "model": chosen,
                    "family_size": 6,
                    **paired_block_inference(
                        series[chosen],
                        series["persistence"],
                        max(h, block),
                        config["bootstrap_replicates"],
                        config["random_seed"],
                    ),
                }
                rows.append(row)
    table = pd.DataFrame(rows)
    for block in config["bootstrap_block_days"]:
        use = table.bootstrap_block_days.eq(block)
        table.loc[use, "p_holm_six_comparisons"] = holm_adjust(
            table.loc[use, "p_bootstrap_two_sided"]
        )
    return table


def interval_diagnostics(config):
    table = pd.read_csv(
        "data/processed/validation/predictions.csv", parse_dates=["date"]
    )
    table["season"] = season_labels(pd.DatetimeIndex(table.date), config)
    table["interval_score"] = interval_score(
        table.observed_sst_celsius,
        table.predicted_sst_celsius,
        table.calibrated_radius_celsius,
    )
    table["covered"] = (
        table.observed_sst_celsius - table.predicted_sst_celsius
    ).abs() <= table.calibrated_radius_celsius
    rows = []
    for key, group in table.groupby(["model", "horizon_days", "season"]):
        rows.append(
            {
                "model": key[0],
                "horizon_days": key[1],
                "season": key[2],
                "n_days": len(group),
                "coverage": float(group.covered.mean()),
                "mean_interval_score_celsius": float(group.interval_score.mean()),
                "mean_width_celsius": float(2 * group.calibrated_radius_celsius.mean()),
            }
        )
    return pd.DataFrame(rows)


def memory_diagnostics(regional, config):
    train = regional.loc[: config["train_end"]]
    residual = train - fit_seasonal(train, config["harmonics"], True).predict(
        train.index
    )
    seasons = pd.Series(season_labels(train.index, config), index=train.index)
    rows = []
    for season in config["seasons"]:
        for lag in [1, 7, 30]:
            good = (
                seasons.eq(season)
                & seasons.shift(lag).eq(season)
                & residual.shift(lag).notna()
            )
            a, b = residual.shift(lag)[good], residual[good]
            row = {
                "season": season,
                "lag_days": lag,
                "n_pairs": int(good.sum()),
                "correlation": float(a.corr(b)),
                "scope": "training-only conditional same-season SST association; not a heat-budget or reemergence attribution",
            }
            if lag == 1:
                phi = float(
                    np.linalg.lstsq(
                        np.column_stack([np.ones(len(a)), a]), b, rcond=None
                    )[0][1]
                )
                row["ar1_coefficient"] = phi
                row["conditional_half_life_days"] = (
                    float(-np.log(2) / np.log(phi)) if 0 < phi < 1 else np.nan
                )
            rows.append(row)
    return pd.DataFrame(rows)


def run(config_path, output_dir):
    config = json.loads(config_path.read_text())
    output_dir.mkdir(parents=True, exist_ok=True)
    event_path = output_dir / "protocol.json"
    config_hash = sha256(config_path)
    if (
        event_path.exists()
        and json.loads(event_path.read_text())["config_sha256"] != config_hash
    ):
        raise ValueError("publication output belongs to a different design")
    _, frozen, regional_predictions, regional = load_inputs(
        Path("paper/independent/frozen_protocol.json")
    )
    dates, values, weights, fixed, lat, lon, distance, acquisitions = read_fields(
        config, frozen
    )
    mean_precision_difference = float(
        np.max(np.abs(values.astype(float) @ weights - regional.loc[dates].values))
    )
    # The locked series used float32 xarray weights and reductions, then CSV
    # rounding. Diagnostics use float64 weights; observed maximum is 1.23e-5 C.
    if mean_precision_difference > 2e-5:
        raise ValueError("field means differ from locked regional observations")
    logging.info("Fitting training-only spatial modes and selection-period candidates")
    spatial, selection = fit_spatial_candidates(
        values.astype(float), dates, weights, config
    )
    selection.to_csv(output_dir / "spatial_selection.csv", index=False)
    logging.info(
        "Selected spatial rank=%s order=%s trend=%s",
        spatial.rank,
        spatial.order,
        spatial.trend,
    )
    design = seasonal_design(dates, dates[0], config["harmonics"], False)
    training = dates <= pd.Timestamp(config["train_end"])
    grid_cycle = (
        design @ np.linalg.lstsq(design[training], values[training], rcond=None)[0]
    )
    forecasts = {}
    score_rows = []
    test = dates >= pd.Timestamp(config["historical_test_start"])
    for h in config["horizons"]:
        means = frozen_means(regional, frozen, h)
        chosen = frozen["selected_methods"][str(h)]
        origin_field = (
            pd.DataFrame(values, index=dates).shift(h).values.astype(np.float32)
        )
        origin_regional = regional.shift(h).loc[dates].values.astype(np.float32)
        projected = {
            name: origin_field
            + means[key].loc[dates].values.astype(np.float32)[:, None]
            - origin_regional[:, None]
            for name, key in [
                ("frozen_selected_projection", chosen),
                ("frozen_anomaly_projection", "persistence"),
            ]
        }
        projected["grid_anomaly_persistence"] = (
            origin_field.astype(float)
            + grid_cycle
            - pd.DataFrame(grid_cycle, index=dates).shift(h).values
        )
        projected["grid_raw_persistence"] = origin_field
        projected["eof_ar_increments"] = spatial.predict(values.astype(float), dates, h)
        forecasts[h] = projected
        for i in np.flatnonzero(test):
            period = "2023-2025" if dates[i].year < 2026 else "2026-Jan-Aug"
            for name, forecast in projected.items():
                for target in ["full_grid_OISST", "regional_OISST"]:
                    predicted, observed, w = (
                        (forecast[i], values[i], weights)
                        if target.startswith("full")
                        else (
                            np.array([forecast[i].astype(float) @ weights]),
                            np.array([regional.loc[dates[i]]]),
                            np.ones(1),
                        )
                    )
                    score_rows.append(
                        {
                            "date": dates[i],
                            "period": period,
                            "target": target,
                            "pass": "all",
                            "horizon_days": h,
                            "model": name,
                            "n_cells": len(weights),
                            **daily_score(predicted, observed, w),
                        }
                    )
    decomposition, transfer, product_rows = [], [], []
    sums = {
        p: {
            "count": np.zeros(len(weights)),
            "difference": np.zeros(len(weights)),
            "square": np.zeros(len(weights)),
        }
        for p in ["ascending", "descending"]
    }
    for path in sorted(Path("data/raw/independent").glob("amsr2-*.npz")):
        metadata = json.loads(path.with_suffix(".json").read_text())
        if sha256(path) != metadata["subset_sha256"]:
            raise ValueError("external observation cache checksum changed")
        day = pd.Timestamp(path.stem.removeprefix("amsr2-"))
        i = dates.get_loc(day)
        with np.load(path) as source:
            for pass_index, pass_name in enumerate(["ascending", "descending"]):
                observed_grid = source["SST"][pass_index]
                valid_grid = quality_mask(
                    observed_grid,
                    source["time"][pass_index],
                    [
                        source[k][pass_index]
                        for k in [
                            "land_mask",
                            "coast_mask",
                            "sea_ice_mask",
                            "noobs_mask",
                        ]
                    ],
                    fixed,
                )
                valid = valid_grid[fixed]
                if valid.sum() < config["minimum_external_cells"]:
                    continue
                analysis, observed = (
                    values[i, valid].astype(float),
                    observed_grid[fixed][valid].astype(float),
                )
                w = weights[valid]
                w /= w.sum()
                difference = analysis - observed
                sums[pass_name]["count"][valid] += 1
                sums[pass_name]["difference"][valid] += difference
                sums[pass_name]["square"][valid] += difference**2
                for lo, hi in zip(
                    config["land_distance_proxy_bins_km"][:-1],
                    config["land_distance_proxy_bins_km"][1:],
                ):
                    bin_valid = valid & (distance >= lo) & (distance < hi)
                    if bin_valid.any():
                        product_rows.append(
                            {
                                "date": day,
                                "pass": pass_name,
                                "distance_proxy_bin": f"{lo}-{hi}",
                                "n_cells": int(bin_valid.sum()),
                                **daily_score(
                                    values[i, bin_valid],
                                    observed_grid[fixed][bin_valid],
                                    weights[bin_valid],
                                ),
                            }
                        )
                for h, models in forecasts.items():
                    base = models["frozen_anomaly_projection"][i, valid].astype(float)
                    for name, predictions in models.items():
                        forecast = predictions[i, valid].astype(float)
                        key = {
                            "date": day,
                            "pass": pass_name,
                            "horizon_days": h,
                            "model": name,
                            "n_cells": int(valid.sum()),
                        }
                        parts = loss_components(forecast, analysis, observed, w)
                        if abs(parts["identity_error"]) > 1e-10:
                            raise ValueError("matched-loss decomposition failed")
                        decomposition.append({**key, **parts})
                        advantage_o = float(
                            w @ ((base - analysis) ** 2 - (forecast - analysis) ** 2)
                        )
                        advantage_a = float(
                            w @ ((base - observed) ** 2 - (forecast - observed) ** 2)
                        )
                        perturbation = float(2 * w @ ((base - forecast) * difference))
                        if abs(advantage_a - advantage_o - perturbation) > 1e-10:
                            raise ValueError("relative-loss transport identity failed")
                        transfer.append(
                            {
                                **key,
                                "advantage_analysis": advantage_o,
                                "advantage_external": advantage_a,
                                "discrepancy_perturbation": perturbation,
                            }
                        )
                        for target, truth in [
                            ("matched_grid_OISST", analysis),
                            ("matched_grid_AMSR2", observed),
                        ]:
                            score_rows.append(
                                {
                                    "date": day,
                                    "period": "2026-Jan-Aug",
                                    "target": target,
                                    "pass": pass_name,
                                    "horizon_days": h,
                                    "model": name,
                                    "n_cells": int(valid.sum()),
                                    **daily_score(forecast, truth, w),
                                }
                            )
    daily = pd.DataFrame(score_rows)
    daily["season"] = season_labels(pd.DatetimeIndex(daily.date), config)
    metrics = aggregate_scores(daily)
    # Retain original frozen scores; new float64 diagnostic arithmetic may differ
    # slightly from original float32 loss arithmetic but never changes forecasts.
    old = pd.read_csv("paper/independent/metrics.csv")
    for h in config["horizons"]:
        for p in ["ascending", "descending"]:
            for name, old_name in [
                ("frozen_selected_projection", frozen["selected_methods"][str(h)]),
                ("frozen_anomaly_projection", "persistence"),
            ]:
                a = metrics.loc[
                    metrics.target.eq("matched_grid_AMSR2")
                    & metrics["pass"].eq(p)
                    & metrics.horizon_days.eq(h)
                    & metrics.model.eq(name)
                ].iloc[0]
                b = old.loc[
                    old["pass"].eq(p) & old.horizon_days.eq(h) & old.model.eq(old_name)
                ].iloc[0]
                if a.n_days != b.n_days or abs(a.rmse - b.rmse) > 1e-5:
                    raise ValueError("frozen primary external score does not replicate")
    tables = {
        "daily_scores": daily,
        "metrics": metrics,
        "loss_decomposition_daily": pd.DataFrame(decomposition),
        "skill_transfer_daily": pd.DataFrame(transfer),
        "product_distance_daily": pd.DataFrame(product_rows),
        "primary_inference": primary_inference(config),
        "interval_diagnostics": interval_diagnostics(config),
        "seasonal_memory": memory_diagnostics(regional, config),
    }
    exploratory_intervals = []
    for key, group in daily.loc[
        daily.target.eq("full_grid_OISST")
        | (daily.target.eq("matched_grid_AMSR2") & daily["pass"].eq("descending"))
    ].groupby(["period", "target", "pass", "horizon_days"]):
        losses = {
            name: g.set_index("date").sort_index().mse
            for name, g in group.groupby("model")
        }
        for baseline in ["frozen_anomaly_projection", "grid_anomaly_persistence"]:
            for block in config["bootstrap_block_days"]:
                interval = paired_block_inference(
                    losses["eof_ar_increments"],
                    losses[baseline],
                    block,
                    config["bootstrap_replicates"],
                    config["random_seed"],
                )
                # These are descriptive retrospective intervals, outside the
                # frozen six-comparison family; do not report new p-value claims.
                interval.pop("p_bootstrap_two_sided")
                interval["scope"] = (
                    "retrospective spatial comparison; unadjusted descriptive interval"
                )
                exploratory_intervals.append(
                    {
                        **dict(zip(["period", "target", "pass", "horizon_days"], key)),
                        "baseline": baseline,
                        **interval,
                    }
                )
    tables["spatial_intervals"] = pd.DataFrame(exploratory_intervals)
    tables["loss_decomposition"] = (
        tables["loss_decomposition_daily"]
        .groupby(["pass", "horizon_days", "model"], as_index=False)
        .agg(
            n_days=("date", "size"),
            analysis_forecast_mse=("analysis_forecast_mse", "mean"),
            product_discrepancy_mse=("product_discrepancy_mse", "mean"),
            interaction=("interaction", "mean"),
            external_mse=("external_mse", "mean"),
            mean_error_squared=("external_mean_error_squared", "mean"),
            spatial_error_variance=("external_spatial_error_variance", "mean"),
            max_absolute_identity_error=(
                "identity_error",
                lambda x: float(abs(x).max()),
            ),
        )
    )
    tables["skill_transfer"] = (
        tables["skill_transfer_daily"]
        .groupby(["pass", "horizon_days", "model"], as_index=False)
        .agg(
            n_days=("date", "size"),
            advantage_analysis=("advantage_analysis", "mean"),
            advantage_external=("advantage_external", "mean"),
            discrepancy_perturbation=("discrepancy_perturbation", "mean"),
        )
    )
    season_rows = []
    for key, group in daily.groupby(
        ["period", "target", "pass", "horizon_days", "model", "season"]
    ):
        season_rows.append(
            dict(
                zip(
                    ["period", "target", "pass", "horizon_days", "model", "season"], key
                ),
                n_days=len(group),
                rmse=float(np.sqrt(group.mse.mean())),
                mae=float(group.mae.mean()),
                bias_celsius=float(group.bias.mean()),
            )
        )
    tables["seasonal_scores"] = pd.DataFrame(season_rows)
    product = tables["product_distance_daily"]
    product["season"] = season_labels(pd.DatetimeIndex(product.date), config)
    tables["product_distance"] = product.groupby(
        ["pass", "distance_proxy_bin", "season"], as_index=False
    ).agg(
        n_days=("date", "size"),
        n_cell_day_pairs=("n_cells", "sum"),
        mse=("mse", "mean"),
        bias=("bias", "mean"),
    )
    tables["product_distance"]["rms_difference"] = np.sqrt(
        tables["product_distance"].mse
    )
    cell_rows = []
    for p, summary in sums.items():
        count = summary["count"]
        denom = np.where(count > 0, count, np.nan)
        for j in range(len(weights)):
            cell_rows.append(
                {
                    "pass": p,
                    "lat": lat[j],
                    "lon": lon[j],
                    "n_days": int(count[j]),
                    "grid_to_land_proxy_km": distance[j],
                    "bias_oisst_minus_amsr2": summary["difference"][j] / denom[j],
                    "rms_difference": np.sqrt(summary["square"][j] / denom[j]),
                }
            )
    tables["product_grid"] = pd.DataFrame(cell_rows)
    for name, table in tables.items():
        table.to_csv(output_dir / (name + ".csv"), index=False, date_format="%Y-%m-%d")
    params = spatial.to_dict()
    params["grid_coordinates"] = {"lat": lat.tolist(), "lon": lon.tolist()}
    (output_dir / "spatial_parameters.json").write_text(
        json.dumps(params, indent=2) + "\n"
    )
    event = {
        "config_sha256": config_hash,
        "config": config,
        "evaluated_utc": datetime.now(timezone.utc).isoformat(),
        "source_acquisitions": acquisitions,
        "locked_original_protocol_sha256": sha256(
            "paper/validation/frozen_protocol.json"
        ),
        "locked_independent_protocol_sha256": sha256(
            "paper/independent/frozen_protocol.json"
        ),
        "scope": config["scope"],
        "primary_replication_tolerance_celsius": 1e-5,
        "regional_float64_vs_locked_max_difference_celsius": mean_precision_difference,
        "regional_precision_check_tolerance_celsius": 2e-5,
        "external_source_record": "paper/independent/provenance.json",
        "runtime_versions": {
            name: version(name)
            for name in ["numpy", "pandas", "xarray", "netCDF4", "h5py", "matplotlib"]
        },
        "software_sha256": {
            str(p): sha256(p)
            for p in [
                Path("src/publication.py"),
                Path("src/models/spatial.py"),
                Path("src/evaluation/publication_stats.py"),
                Path("src/evaluation/publication_report.py"),
                Path("paper/submission/manuscript_en.template.md"),
                Path("paper/submission/supplement_en.template.md"),
                Path("paper/submission/references_verified.md"),
            ]
        },
    }
    event_path.write_text(json.dumps(event, indent=2) + "\n")
    from src.evaluation.publication_report import write_publication

    write_publication(tables, selection, spatial, lat, lon, weights, config, output_dir)
    (output_dir / "checksums.json").write_text(
        json.dumps(
            {
                p.name: sha256(p)
                for p in output_dir.iterdir()
                if p.is_file() and p.name != "checksums.json"
            },
            indent=2,
        )
        + "\n"
    )
    print(metrics.to_string(index=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/publication.json"))
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data/processed/publication")
    )
    args = parser.parse_args()
    os.environ.setdefault(
        "MPLCONFIGDIR", str((args.output_dir / ".matplotlib").resolve())
    )
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    run(args.config, args.output_dir)


if __name__ == "__main__":
    main()
