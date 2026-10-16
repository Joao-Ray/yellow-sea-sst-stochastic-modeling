"""Exploratory past-forcing ablations and northern Eastern China Sea transfer.

No original frozen forecast or protocol is overwritten. This is retrospective.
"""

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import shutil
from concurrent.futures import ProcessPoolExecutor, as_completed
from urllib.parse import urlencode

import joblib
import numpy as np
import pandas as pd
from shapely.geometry import shape
import xarray as xr

from src.data.download_processes import FIELDS, acquire_forcing, validate_forcing
from src.data.download_oisst import build_session
from src.data.marine_boundary import grid_mask
from src.evaluation.publication_stats import holm_adjust, paired_block_inference
from src.models.process_transfer import feature_matrix, fit_increment, select_source
from src.models.seasonal import fit_seasonal
from src.publication_delivery import hashes
from src.validation import sha256

CONFIG = Path("configs/process_transfer.json")
OUTPUT = Path("data/processed/process_transfer")
REVIEWED = Path("paper/process_transfer")


def load_config():
    return json.loads(CONFIG.read_text())


def forcing_job(job):
    variable, year, config = job
    return str(
        acquire_forcing(
            variable,
            date(year, 1, 1),
            date(year, 12, 31),
            config["forcing_box"],
            Path("data/raw/processes/forcing"),
            full_file=True,
        )
    )


def acquire(workers=3):
    config = load_config()
    jobs = [(v, y, config) for y in range(2010, 2026) for v in FIELDS]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    done, failures = [], []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(forcing_job, j): j[:2] for j in jobs}
        for future in as_completed(futures):
            try:
                done.append(future.result())
                print("Ready", futures[future], len(done), flush=True)
            except Exception as exc:
                failures.append({"job": futures[future], "error": repr(exc)})
                print("Failed", futures[future], repr(exc), flush=True)
            (OUTPUT / "acquisition_status.json").write_text(
                json.dumps({"completed": done, "failures": failures}, indent=2) + "\n"
            )
    if failures:
        raise RuntimeError("forcing acquisition incomplete; valid caches retained")


def destination_geometry(document):
    """Separate validation: do not relax the original Yellow Sea identity gate."""
    features = document.get("features", [])
    if document.get("type") != "FeatureCollection" or len(features) != 1:
        raise ValueError("exactly one Eastern China Sea feature required")
    props = features[0].get("properties", {})
    if props.get("mrgid") != 4302 or props.get("name") != "Eastern China Sea":
        raise ValueError("destination must identify Eastern China Sea MRGID 4302")
    crs = document.get("crs", {}).get("properties", {}).get("name")
    if crs not in {
        "urn:ogc:def:crs:EPSG::4326",
        "EPSG:4326",
        "urn:ogc:def:crs:OGC:1.3:CRS84",
    }:
        raise ValueError("destination requires longitude/latitude WGS84")
    g = shape(features[0]["geometry"])
    if not g.is_valid or g.is_empty or g.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError("invalid destination geometry")
    west, south, east, north = g.bounds
    if not (
        118 < west < 119 and 24 < south < 25 and 131 < east < 132 and 33 < north < 34
    ):
        raise ValueError("unexpected destination bounds/axis order")
    return g


def acquire_destination_boundary():
    url = "https://geo.vliz.be/geoserver/MarineRegions/wfs?" + urlencode(
        {
            "service": "WFS",
            "version": "1.0.0",
            "request": "GetFeature",
            "typeName": "MarineRegions:iho",
            "cql_filter": "mrgid=4302",
            "outputFormat": "application/json",
            "srsName": "EPSG:4326",
        }
    )
    path = Path("data/raw/processes/east_china_sea_iho.geojson")
    sidecar = path.with_suffix(".json")
    if path.exists():
        meta = json.loads(sidecar.read_text())
        if meta.get("source_url") != url or meta.get("sha256") != sha256(path):
            raise ValueError("destination boundary provenance mismatch")
    else:
        with build_session(retries=2) as session:
            response = session.get(url, timeout=90)
            response.raise_for_status()
            raw = response.content
        destination_geometry(json.loads(raw))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        meta = {
            "source_url": url,
            "sha256": sha256(path),
            "acquired_utc": datetime.now(timezone.utc).isoformat(),
        }
    g = destination_geometry(json.loads(path.read_text()))
    meta.update(
        provider="Flanders Marine Institute / Marine Regions",
        mrgid=4302,
        name="Eastern China Sea",
        dataset_doi="10.14284/323",
        source_page="https://www.marineregions.org/gazetteer.php?id=4302&p=details",
        bounds_west_south_east_north=list(g.bounds),
        distribution="Official boundary downloaded locally; geometry not committed or redistributed",
    )
    sidecar.write_text(json.dumps(meta, indent=2) + "\n")
    return path


def region_inputs():
    """Use the original NOAA cube; region definition never depends on scores."""
    cfg = load_config()
    files = sorted(Path("data/raw/research").glob("*.nc")) + sorted(
        Path("data/raw/validation").glob("*.nc")
    )
    records = []
    for p in files:
        rec = json.loads(p.with_suffix(".json").read_text())
        if sha256(p) != rec["sha256"]:
            raise ValueError("original OISST cache hash mismatch")
        records.append(
            {"path": str(p), "sha256": rec["sha256"], "url": rec["request_url"]}
        )
    boundary = Path("data/raw/processes/east_china_sea_iho.geojson")
    meta = json.loads(boundary.with_suffix(".json").read_text())
    if meta["sha256"] != sha256(boundary):
        raise ValueError("destination boundary hash mismatch")
    geometry = destination_geometry(json.loads(boundary.read_text()))
    frozen = json.loads(Path("paper/validation/frozen_protocol.json").read_text())
    with xr.open_mfdataset(files, combine="by_coords", engine="netcdf4") as ds:
        data = ds.sst.load()
    dates = pd.DatetimeIndex(data.time.values)
    if not dates.equals(pd.date_range(cfg["date_start"], cfg["date_end"])):
        raise ValueError("incomplete original OISST calendar")
    lat, lon = np.meshgrid(data.lat.values, data.lon.values, indexing="ij")
    source = np.zeros(lat.shape, bool)
    for y, x in frozen["spatial_mask"]["selected_cells"]:
        source |= (lat == y) & (lon == x)
    destination = grid_mask(geometry, data.lat, data.lon).values & np.isfinite(
        data.values[0]
    )
    if (source & destination).any() or source.sum() != 651 or destination.sum() < 100:
        raise ValueError("source/destination must be distinct fixed ocean domains")
    means, domains = {}, {}
    for name, mask in [("yellow_bohai", source), ("northern_ecs", destination)]:
        weights = np.cos(np.deg2rad(lat[mask].astype(float)))
        weights /= weights.sum()
        values = data.values[:, mask].astype(float)
        if not np.isfinite(values).all():
            raise ValueError("complete fixed SST cells required; do not fill")
        means[name] = pd.Series(values @ weights, index=dates)
        domains[name] = {"lat": lat[mask], "lon": lon[mask], "weights": weights}
    return (
        means,
        domains,
        {
            "oisst": records,
            "destination_boundary": meta,
            "boundary_file_sha256": sha256(boundary),
        },
    )


def prepare():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    acquire_destination_boundary()
    means, domains, provenance = region_inputs()
    pd.DataFrame(means).rename_axis("date").to_csv(OUTPUT / "regional_sst.csv")
    np.savez_compressed(
        OUTPUT / "domains.npz",
        **{
            f"{name}__{key}": value
            for name, domain in domains.items()
            for key, value in domain.items()
        },
    )
    domain_record = {
        name: {
            "n_sst_cells": len(d["lat"]),
            "cell_center_bounds": [
                float(d["lon"].min()),
                float(d["lat"].min()),
                float(d["lon"].max()),
                float(d["lat"].max()),
            ],
        }
        for name, d in domains.items()
    }
    provenance["domains"] = domain_record
    (OUTPUT / "sst_provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    REVIEWED.mkdir(parents=True, exist_ok=True)
    design = {
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "config_sha256": sha256(CONFIG),
        "config": load_config(),
        "source_files_sha256": {
            p: sha256(p)
            for p in [
                "src/models/process_transfer.py",
                "src/data/download_processes.py",
                "src/process_transfer.py",
            ]
        },
        "scope": "Local retrospective design and availability amendments; not a public prospective freeze.",
    }
    design_path = REVIEWED / "design_record.json"
    if design_path.exists():
        old = json.loads(design_path.read_text())
        if old["config_sha256"] != design["config_sha256"]:
            raise ValueError("do not change the recorded design silently")
    else:
        design_path.write_text(json.dumps(design, indent=2) + "\n")
    print(domain_record, flush=True)


def forcing_series(domains):
    cfg = load_config()
    frames = {name: {} for name in domains}
    records, mappings = [], {}
    for variable in FIELDS:
        parts = []
        for year in range(2010, 2026):
            matches = list(
                Path("data/raw/processes/forcing").glob(
                    f"{variable}-{year}0101-{year}1231-*.nc"
                )
            )
            if len(matches) != 1:
                raise ValueError(
                    f"exactly one audited forcing subset required: {variable}, {year}"
                )
            p = matches[0]
            rec = json.loads(p.with_suffix(".json").read_text())
            if sha256(p) != rec["sha256"] or rec["variable"] != variable:
                raise ValueError("forcing checksum/variable mismatch")
            expected_url = f"https://downloads.psl.noaa.gov/Datasets/ncep.reanalysis.dailyavgs/surface_gauss/{FIELDS[variable]}.{year}.nc"
            if rec["request_url"] != expected_url or rec["box"] != cfg["forcing_box"]:
                raise ValueError("forcing source URL/box differs from design")
            records.append({"path": str(p), **rec})
            with xr.open_dataset(p, engine="netcdf4") as ds:
                validated = validate_forcing(
                    ds, variable, date(year, 1, 1), date(year, 12, 31)
                )
                parts.append(validated[variable].load())
        a = xr.concat(parts, dim="time")
        dates = pd.DatetimeIndex(a.time.values)
        if not dates.equals(pd.date_range(cfg["date_start"], cfg["forcing_end"])):
            raise ValueError("forcing dates must cover the complete design period")
        y, x = np.meshgrid(a.lat.values, a.lon.values, indexing="ij")
        for name, d in domains.items():
            phi, lam = np.deg2rad(d["lat"])[:, None], np.deg2rad(d["lon"])[:, None]
            cy, cx = np.deg2rad(y.ravel()), np.deg2rad(x.ravel())
            hav = (
                np.sin((phi - cy) / 2) ** 2
                + np.cos(phi) * np.cos(cy) * np.sin((lam - cx) / 2) ** 2
            )
            nearest = np.argmin(hav, axis=1)
            w = np.bincount(nearest, weights=d["weights"], minlength=y.size)
            mapping = {
                "n_effective_coarse_cells": int(np.count_nonzero(w)),
                "lat": y.ravel()[w > 0].tolist(),
                "lon": x.ravel()[w > 0].tolist(),
                "weight": w[w > 0].tolist(),
                "rule": "Spherical nearest Gaussian center to each fixed OISST ocean center; sum original cosine-latitude ocean weights. No land-fraction correction; coarse coastal cells may include land.",
            }
            if name in mappings and mappings[name] != mapping:
                raise ValueError("forcing grids differ across variables/years")
            mappings[name] = mapping
            values = a.values.reshape(len(dates), -1).astype(float)
            if not np.isfinite(values).all():
                raise ValueError("forcing values must be finite")
            frames[name][variable] = pd.Series(values @ w, index=dates)
    return {k: pd.DataFrame(v) for k, v in frames.items()}, records, mappings


def model_record(model):
    out = {
        "family": model.family,
        "hyperparameter": model.hyperparameter,
        "columns": model.columns,
        "training_end": model.training_end,
        "training_rows": model.training_rows,
        "source_mean": model.mean.tolist(),
        "source_scale": model.scale.tolist(),
    }
    if model.family == "ridge":
        out.update(
            standardized_coefficients=model.fitted.coef_.tolist(),
            intercept=float(model.fitted.intercept_),
        )
    else:
        out["impurity_feature_importance_not_causal"] = (
            model.fitted.feature_importances_.tolist()
        )
    return out


def evaluate():
    cfg = load_config()
    if (
        sha256(CONFIG)
        != json.loads((REVIEWED / "design_record.json").read_text())["config_sha256"]
    ):
        raise ValueError("design changed")
    original = {
        str(p): sha256(p)
        for p in [
            Path("paper/validation/frozen_protocol.json"),
            Path("paper/independent/frozen_protocol.json"),
            Path("paper/confirmation/frozen_protocol.json"),
            Path("paper/insitu/frozen_protocol.json"),
            Path("data/processed/confirmation/locked_forecasts.npz"),
            Path("data/processed/confirmation/tree_models.joblib"),
        ]
    }
    means, domains, sst_provenance = region_inputs()
    forcing, forcing_provenance, mappings = forcing_series(domains)
    for name, values in forcing.items():
        values.rename_axis("date").to_csv(OUTPUT / f"{name}_forcing.csv")
    selections, predictions, fitted_models, parameters = [], [], {}, {}
    for group in cfg["feature_groups"]:
        # Complete years only for forcing; source/destination share every day.
        end = cfg["date_end"] if group == "sst" else cfg["forcing_end"]
        series = {name: v.loc[:end] for name, v in means.items()}
        weather = {name: f.reindex(series[name].index) for name, f in forcing.items()}
        for family, candidates in [
            ("ridge", cfg["ridge_alphas"]),
            ("trees", cfg["tree_min_samples_leaf"]),
        ]:
            selected, rows = select_source(
                series["yellow_bohai"],
                weather["yellow_bohai"],
                family,
                group,
                candidates,
                cfg,
            )
            selections.extend(rows)
            for h in cfg["horizons"]:
                xs, os = feature_matrix(
                    series["yellow_bohai"], weather["yellow_bohai"], h, group
                )
                source_model = fit_increment(
                    xs,
                    os,
                    series["yellow_bohai"],
                    family,
                    selected,
                    cfg["train_end"],
                    cfg["random_seed"],
                    cfg["tree_estimators"],
                )
                xd, od = feature_matrix(
                    series["northern_ecs"], weather["northern_ecs"], h, group
                )
                local_model = fit_increment(
                    xd,
                    od,
                    series["northern_ecs"],
                    family,
                    selected,
                    cfg["train_end"],
                    cfg["random_seed"],
                    cfg["tree_estimators"],
                )
                key = f"{family}__{group}__h{h}"
                fitted_models[key + "__source"] = source_model
                fitted_models[key + "__local"] = local_model
                parameters[key] = {
                    "source": model_record(source_model),
                    "destination_local": model_record(local_model),
                    "transfer_rule": "predict destination features with the identical source model object and unchanged source scaler",
                }
                for domain, fitting, model, x, origin in [
                    ("yellow_bohai", "source_local", source_model, xs, os),
                    ("northern_ecs", "source_transfer", source_model, xd, od),
                    ("northern_ecs", "destination_local", local_model, xd, od),
                ]:
                    prediction = model.predict(x, origin)
                    for period, (start, stop) in cfg["test_periods"].items():
                        if stop > end:
                            continue  # Do not silently shorten the 2026 forcing evaluation.
                        s = series[domain].loc[start:stop]
                        p = prediction.loc[s.index]
                        if not np.isfinite(p).all():
                            raise ValueError(
                                "all evaluation dates require valid predictions"
                            )
                        q = pd.DataFrame(
                            {
                                "date": s.index,
                                "observed": s.values,
                                "predicted": p.values,
                                "origin_date": s.index - pd.Timedelta(days=h),
                                "latest_forcing_date": s.index
                                - pd.Timedelta(days=h + 1)
                                if group != "sst"
                                else pd.NaT,
                                "domain": domain,
                                "fitting": fitting,
                                "family": family,
                                "group": group,
                                "horizon_days": h,
                                "period": period,
                            }
                        )
                        predictions.append(q)
                print("Fitted", key, "source-selected", selected, flush=True)
    # Destination-local training climatology is available to the benchmark only;
    # direct source transfer does not estimate destination coefficients or scaling.
    for domain, s in means.items():
        cycle = fit_seasonal(
            s.loc[: cfg["train_end"]], harmonics=3, trend=True
        ).predict(s.index)
        for h in cfg["horizons"]:
            for baseline, p in [
                ("raw_persistence", s.shift(h)),
                ("local_anomaly_persistence", s.shift(h) + cycle - cycle.shift(h)),
            ]:
                for period, (start, stop) in cfg["test_periods"].items():
                    q = pd.DataFrame(
                        {
                            "date": s.loc[start:stop].index,
                            "observed": s.loc[start:stop].values,
                            "predicted": p.loc[start:stop].values,
                            "origin_date": s.loc[start:stop].index
                            - pd.Timedelta(days=h),
                            "latest_forcing_date": pd.NaT,
                            "domain": domain,
                            "fitting": "baseline",
                            "family": baseline,
                            "group": "sst",
                            "horizon_days": h,
                            "period": period,
                        }
                    )
                    predictions.append(q)
    frame = pd.concat(predictions, ignore_index=True)
    frame["error"] = frame.predicted - frame.observed
    frame["squared_error"] = frame.error**2
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
    pd.DataFrame(selections).to_csv(OUTPUT / "selection.csv", index=False)
    keys = ["domain", "fitting", "family", "group", "horizon_days", "period"]
    for extra, filename in [
        ([], "metrics.csv"),
        (["year"], "annual_metrics.csv"),
        (["season"], "seasonal_metrics.csv"),
    ]:
        out = frame.groupby(keys + extra, observed=True).agg(
            n_days=("error", "size"),
            mse=("squared_error", "mean"),
            bias=("error", "mean"),
        )
        out["rmse"] = np.sqrt(out.mse)
        out.reset_index().to_csv(OUTPUT / filename, index=False)
    inference = []
    # Both forcing groups, families, horizons, domains and fitting modes are
    # retained: one 36-comparison exploratory family per block length.
    for key, q in frame.loc[
        (frame.period == "2023-2025") & frame.group.ne("sst")
    ].groupby(keys):
        domain, fitting, family, group, h, period = key
        base = frame.loc[
            (frame.domain == domain)
            & (frame.fitting == fitting)
            & (frame.family == family)
            & (frame.group == "sst")
            & (frame.horizon_days == h)
            & (frame.period == period)
        ].set_index("date")
        q = q.set_index("date")
        for block in cfg["bootstrap_block_days"]:
            result = paired_block_inference(
                q.squared_error,
                base.squared_error,
                block,
                cfg["bootstrap_replicates"],
                cfg["random_seed"],
            )
            inference.append(
                {
                    **dict(zip(keys, key)),
                    "comparison": "forcing vs identical SST-only family/fitting",
                    "rmse_skill": 1
                    - np.sqrt(q.squared_error.mean() / base.squared_error.mean()),
                    **result,
                }
            )
    inf = pd.DataFrame(inference)
    for block in cfg["bootstrap_block_days"]:
        mask = inf.bootstrap_block_days.eq(block)
        inf.loc[mask, "p_holm_36"] = holm_adjust(inf.loc[mask, "p_bootstrap_two_sided"])
    inf.to_csv(OUTPUT / "forcing_inference.csv", index=False)
    joblib.dump(fitted_models, OUTPUT / "models.joblib", compress=3)
    (OUTPUT / "parameters.json").write_text(json.dumps(parameters, indent=2) + "\n")
    provenance = {
        "evaluated_utc": datetime.now(timezone.utc).isoformat(),
        "design_sha256": sha256(REVIEWED / "design_record.json"),
        "config_sha256": sha256(CONFIG),
        "sst": sst_provenance,
        "forcing_files": forcing_provenance,
        "forcing_mapping": mappings,
        "model_archive_sha256": sha256(OUTPUT / "models.joblib"),
        "software_sha256": {
            p: sha256(p)
            for p in [
                "src/process_transfer.py",
                "src/models/process_transfer.py",
                "src/data/download_processes.py",
            ]
        },
        "scope": cfg["scope"],
    }
    (OUTPUT / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    if any(sha256(p) != digest for p, digest in original.items()):
        raise ValueError("original frozen inputs changed")
    audit = {
        "original_inputs_unchanged": True,
        "original_input_sha256": original,
        "destination_local_hyperparameters_selected_on_source_only": True,
        "forcing_latest_input": "origin minus one day",
        "source_destination_ocean_cells_overlap": 0,
        "forcing_inference_family_size": int(len(inf) // 2),
        "n_forecast_rows": len(frame),
        "all_evaluation_rows_finite": bool(np.isfinite(frame.predicted).all()),
        "forcing_2026_evaluated": False,
        "retrospective": True,
    }
    (OUTPUT / "evaluation_audit.json").write_text(json.dumps(audit, indent=2) + "\n")


def deliver():
    from src.evaluation.process_transfer_report import write_report

    write_report(OUTPUT, load_config())
    target = REVIEWED / "results"
    target.mkdir(parents=True, exist_ok=True)
    for p in OUTPUT.iterdir():
        if p.suffix in {".csv", ".json", ".png", ".svg", ".md"} and p.name not in {
            "predictions.csv",
            "alignment_predictions.csv",
            "checksums.json",
            "external_daily_scores.csv",
            "regional_sst.csv",
            "yellow_bohai_forcing.csv",
            "northern_ecs_forcing.csv",
        }:
            shutil.copy2(p, target / p.name)
    (target / "checksums.json").write_text(json.dumps(hashes(target), indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["prepare", "acquire", "evaluate", "deliver"])
    parser.add_argument("--workers", type=int, choices=[1, 2, 3, 4], default=3)
    args = parser.parse_args()
    if args.stage == "acquire":
        acquire(args.workers)
    else:
        {"prepare": prepare, "evaluate": evaluate, "deliver": deliver}[args.stage]()


if __name__ == "__main__":
    main()
