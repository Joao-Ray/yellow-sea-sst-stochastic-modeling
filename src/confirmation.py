"""Lock stronger forecasts before acquiring a multi-year AMSR2 target record."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from functools import partial
from importlib.metadata import version
import json
import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from src.data.download_amsr2 import acquire_day
from src.independent import load_inputs
from src.models.seasonal import seasonal_design
from src.models.spatial_benchmarks import (
    load_spatial,
    project_modes,
    reconstruct,
    select_benchmarks,
    shift,
)
from src.publication import read_fields
from src.validation import frozen_means, sha256


CONFIG = Path("configs/confirmation.json")
FROZEN = Path("paper/confirmation/frozen_protocol.json")
OUTPUT = Path("data/processed/confirmation")
RAW = Path("data/raw/confirmation")


def prepare():
    if FROZEN.exists():
        verify_inputs()
        logging.info(
            "Existing locked forecasts verified; preparation will not overwrite them"
        )
        return
    config = json.loads(CONFIG.read_text())
    OUTPUT.mkdir(parents=True, exist_ok=True)
    FROZEN.parent.mkdir(parents=True, exist_ok=True)
    _, original, _, regional = load_inputs(
        Path("paper/independent/frozen_protocol.json")
    )
    pub = json.loads(Path("configs/publication.json").read_text())
    dates, values, weights, fixed, lat, lon, _, _ = read_fields(pub, original)
    spatial = load_spatial("paper/submission/results/spatial_parameters.json")
    if not np.allclose(weights, spatial.weights, rtol=0, atol=1e-14):
        raise ValueError("locked spatial weights differ")
    logging.info("Selecting coupled VAR and nonlinear controls on 2020-2021 only")
    var, trees, selection = select_benchmarks(
        values.astype(float), dates, spatial, config
    )
    selection.to_csv(OUTPUT / "benchmark_selection.csv", index=False)
    params = {
        "var": var.to_dict(),
        "trees": {str(h): m.to_dict() for h, m in trees.items()},
        "locked_spatial_source": "paper/submission/results/spatial_parameters.json",
    }
    (OUTPUT / "benchmark_parameters.json").write_text(
        json.dumps(params, indent=2) + "\n"
    )
    joblib.dump(trees, OUTPUT / "tree_models.joblib", compress=3)
    cycle, anomaly, scores = project_modes(values, dates, spatial)
    training = dates <= pd.Timestamp(config["train_end"])
    design = seasonal_design(dates, dates[0], 3, False)
    grid_cycle = (
        design @ np.linalg.lstsq(design[training], values[training], rcond=None)[0]
    )
    test = dates >= pd.Timestamp(config["external_start"])
    data = {
        "dates": dates[test].strftime("%Y-%m-%d").to_numpy(dtype="U10"),
        "analysis": values[test],
        "regional": regional.loc[dates[test]].values,
        "weights": weights,
        "lat": lat,
        "lon": lon,
        "fixed_mask": fixed,
    }
    names = [
        "frozen_selected_projection",
        "frozen_anomaly_projection",
        "grid_anomaly_persistence",
        "grid_raw_persistence",
        "eof_ar_increments",
        "eof_var_ridge",
        "eof_extra_trees",
    ]
    for h in config["horizons"]:
        means = frozen_means(regional, original, h)
        origin = shift(values, h).astype(np.float32)
        origin_regional = regional.shift(h).loc[dates].values.astype(np.float32)
        for name, key in [
            (names[0], original["selected_methods"][str(h)]),
            (names[1], "persistence"),
        ]:
            forecast = (
                origin
                + means[key].loc[dates].values.astype(np.float32)[:, None]
                - origin_regional[:, None]
            )
            data[f"h{h}__{name}"] = forecast[test]
        data[f"h{h}__grid_raw_persistence"] = origin[test]
        data[f"h{h}__grid_anomaly_persistence"] = (
            origin.astype(float) + grid_cycle - shift(grid_cycle, h)
        )[test].astype(np.float32)
        data[f"h{h}__eof_ar_increments"] = spatial.predict(
            values.astype(float), dates, h
        )[test].astype(np.float32)
        data[f"h{h}__eof_var_ridge"] = reconstruct(
            cycle, anomaly, scores, var.predict(scores, h), spatial, h
        )[test].astype(np.float32)
        data[f"h{h}__eof_extra_trees"] = reconstruct(
            cycle, anomaly, scores, trees[h].predict(scores, dates), spatial, h
        )[test].astype(np.float32)
    if any(not np.isfinite(v).all() for k, v in data.items() if k.startswith("h")):
        raise ValueError("nonfinite locked test forecasts")
    np.savez_compressed(OUTPUT / "locked_forecasts.npz", **data)
    inputs = [
        CONFIG,
        Path("configs/publication.json"),
        Path("paper/validation/frozen_protocol.json"),
        Path("paper/independent/frozen_protocol.json"),
        Path("paper/submission/results/spatial_parameters.json"),
        Path("data/processed/research/iho_yellow_sea_daily.csv"),
        Path("data/processed/validation/predictions.csv"),
        OUTPUT / "benchmark_selection.csv",
        OUTPUT / "benchmark_parameters.json",
        OUTPUT / "tree_models.joblib",
        OUTPUT / "locked_forecasts.npz",
    ]
    for name in ["benchmark_selection.csv", "benchmark_parameters.json"]:
        (FROZEN.parent / name).write_bytes((OUTPUT / name).read_bytes())
    frozen = {
        "frozen_utc": datetime.now(timezone.utc).isoformat(),
        "config": config,
        "input_sha256": {str(p): sha256(p) for p in inputs},
        "software_sha256": {
            str(p): sha256(p)
            for p in [
                Path("src/confirmation.py"),
                Path("src/models/spatial_benchmarks.py"),
            ]
        },
        "runtime_versions": {
            p: version(p) for p in ["numpy", "pandas", "scikit-learn", "joblib", "h5py"]
        },
        "models": names,
        "external_targets_previously_viewed": False,
        "prior_oisst_and_2026_external_outcomes_viewed": True,
        "quality_rules": json.loads(
            Path("paper/independent/frozen_protocol.json").read_text()
        )["config"],
        "region": {"lat_min": 31, "lat_max": 42, "lon_min": 117, "lon_max": 128},
        "scope": config["scope"],
    }
    FROZEN.write_text(json.dumps(frozen, indent=2) + "\n")
    print(
        json.dumps(
            {
                "protocol_sha256": sha256(FROZEN),
                "var_order": var.order,
                "var_alpha": var.alpha,
                "tree_settings": trees[7].to_dict(),
                "locked_dates": int(test.sum()),
            },
            indent=2,
        )
    )


def verify_inputs():
    frozen = json.loads(FROZEN.read_text())
    for name, digest in frozen["input_sha256"].items():
        if sha256(name) != digest:
            raise ValueError("locked input changed: " + name)
    return frozen


def acquire(workers=4):
    frozen = verify_inputs()
    config = frozen["config"]
    RAW.mkdir(parents=True, exist_ok=True)
    days = [
        d.date()
        for d in pd.date_range(config["external_start"], config["external_end"])
    ]
    complete, missing, failures = [], [], []

    def status():
        record = {
            "updated_utc": datetime.now(timezone.utc).isoformat(),
            "expected_days": len(days),
            "complete_days": len(complete),
            "missing_days": missing,
            "failures": failures,
            "frozen_protocol_sha256": sha256(FROZEN),
        }
        p = OUTPUT / "acquisition_status.json"
        tmp = p.with_suffix(".tmp.json")
        tmp.write_text(json.dumps(record, indent=2) + "\n")
        tmp.replace(p)

    downloader = partial(acquire_day, region=frozen["region"], output_dir=RAW)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(downloader, d): d for d in days}
        for future in as_completed(futures):
            day = futures[future].isoformat()
            try:
                result = future.result()
                if result:
                    complete.append(day)
                else:
                    missing.append(day)
            except Exception as exc:
                failures.append({"date": day, "error": str(exc)})
            status()
            if len(complete) % 20 == 0:
                logging.info(
                    "Acquired %s/%s days; missing=%s failed=%s",
                    len(complete),
                    len(days),
                    len(missing),
                    len(failures),
                )
    status()
    if failures:
        raise RuntimeError(
            "acquisition incomplete; cached successes retained for retry"
        )
    logging.info(
        "Multi-year acquisition complete: %s dates, %s source absences",
        len(complete),
        len(missing),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "acquire"])
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s"
    )
    if args.action == "prepare":
        prepare()
    else:
        acquire(args.workers)


if __name__ == "__main__":
    main()
