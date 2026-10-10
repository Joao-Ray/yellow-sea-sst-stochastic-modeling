"""Reproduce the complete exploratory regional SST study and manuscript draft."""

import argparse
from datetime import date
import hashlib
from importlib.metadata import version
import json
import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd
from shapely.geometry import shape

from src.data.download_psl import download_regional_range
from src.data.marine_boundary import acquire_boundary
from src.data.preprocess import Region
from src.data.research_series import build_research_series
from src.evaluation.bootstrap import skill_interval
from src.evaluation.research_experiment import run_research_fold
from src.evaluation.research_report import write_research_report


def run_research(
    config_path: Path, raw_dir: Path, boundary_dir: Path, output_dir: Path
):
    config = json.loads(config_path.read_text())
    output_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str((output_dir / ".matplotlib").resolve()))
    snapshot = output_dir / "research_config.json"
    if snapshot.exists() and json.loads(snapshot.read_text()) != config:
        raise ValueError(
            "output directory already belongs to a different research design"
        )
    snapshot.write_text(json.dumps(config, indent=2) + "\n")
    boundary_path, boundary_metadata = acquire_boundary(boundary_dir)
    document = json.loads(boundary_path.read_text())
    geometry = shape(document["features"][0]["geometry"])
    files = download_regional_range(
        date.fromisoformat(config["date_start"]),
        date.fromisoformat(config["date_end"]),
        Region(**config["acquisition_region"]),
        raw_dir,
    )
    series, quality = build_research_series(files, geometry, config, output_dir)
    all_metrics, all_predictions, all_yearly, all_intervals, models, all_skill = (
        [],
        [],
        [],
        [],
        {},
        [],
    )
    all_residuals, all_diagnostics = [], []
    for domain, values in series.items():
        for fold in config["folds"]:
            logging.info("Evaluating %s / %s", domain, fold["name"])
            result = run_research_fold(values, fold, config)
            key = domain + "/" + fold["name"]
            models[key] = {
                k: result[k]
                for k in ("models", "seasonal_fits", "support_rule", "protocol")
            }
            for name, destination in [
                ("metrics", all_metrics),
                ("predictions", all_predictions),
                ("yearly", all_yearly),
                ("training_residuals", all_residuals),
                ("residual_diagnostics", all_diagnostics),
            ]:
                frame = result[name].copy()
                frame["domain"], frame["fold"] = domain, fold["name"]
                destination.append(frame)
            interval_frame = pd.DataFrame(result["interval_radii"])
            interval_frame["domain"], interval_frame["fold"] = domain, fold["name"]
            all_intervals.append(interval_frame)
            test = result["predictions"].query("split == 'test'")
            for horizon in config["horizons"]:
                group = test[test.horizon_days.eq(horizon)]
                baseline = (
                    group[group.model.eq("persistence")].set_index("date").sort_index()
                )
                for name, scored in group.groupby("model"):
                    scored = scored.set_index("date").sort_index()
                    mse = np.mean(
                        (scored.predicted_sst_celsius - scored.observed_sst_celsius)
                        ** 2
                    )
                    base_mse = np.mean(
                        (baseline.predicted_sst_celsius - baseline.observed_sst_celsius)
                        ** 2
                    )
                    skill = (
                        float(1 - np.sqrt(mse / base_mse)) if base_mse > 0 else np.nan
                    )
                    # Baselines still receive a 30-day CI. Richer models get all
                    # prespecified block lengths; duplicate effective lengths
                    # (15 and 30 at h=30) are recorded only once.
                    requested = (
                        config["bootstrap_block_days"]
                        if name.startswith(("ar_", "ridge_"))
                        else [30]
                    )
                    for block in sorted({max(horizon, length) for length in requested}):
                        interval = skill_interval(
                            scored.observed_sst_celsius,
                            scored.predicted_sst_celsius,
                            baseline.predicted_sst_celsius,
                            block_days=block,
                            replicates=config["bootstrap_replicates"],
                            seed=config["random_seed"],
                        )
                        all_skill.append(
                            {
                                "domain": domain,
                                "fold": fold["name"],
                                "model": name,
                                "horizon_days": horizon,
                                "rmse_skill_vs_persistence": skill,
                                **interval,
                            }
                        )
    metrics = pd.concat(all_metrics, ignore_index=True)
    skill = pd.DataFrame(all_skill)
    primary_skill = skill[skill.bootstrap_block_days.eq(30)].drop(
        columns=["bootstrap_block_days"]
    )
    metrics = metrics.merge(
        primary_skill,
        on=["domain", "fold", "model", "horizon_days"],
        validate="one_to_one",
    )
    metrics.to_csv(output_dir / "metrics.csv", index=False)
    skill.to_csv(output_dir / "block_sensitivity.csv", index=False)
    pd.concat(all_predictions, ignore_index=True).to_csv(
        output_dir / "predictions.csv", index=False, date_format="%Y-%m-%d"
    )
    pd.concat(all_yearly, ignore_index=True).to_csv(
        output_dir / "yearly_metrics.csv", index=False
    )
    pd.concat(all_intervals, ignore_index=True).to_csv(
        output_dir / "calibration_radii.csv", index=False
    )
    pd.concat(all_residuals, ignore_index=True).to_csv(
        output_dir / "training_residuals.csv", index=False, date_format="%Y-%m-%d"
    )
    pd.concat(all_diagnostics, ignore_index=True).to_csv(
        output_dir / "residual_diagnostics.csv", index=False
    )
    (output_dir / "models.json").write_text(
        json.dumps(models, indent=2, allow_nan=False) + "\n"
    )
    protocol = {
        "design": config,
        "boundary": boundary_metadata,
        "data_quality": quality,
        "source_acquisitions": [
            json.loads(path.with_suffix(".json").read_text()) for path in files
        ],
        "source_bytes": sum(path.stat().st_size for path in files),
        "runtime_versions": {
            name: version(name)
            for name in (
                "numpy",
                "pandas",
                "xarray",
                "netCDF4",
                "matplotlib",
                "shapely",
            )
        },
        "validation": "training fits frozen; selection period chooses AR order / ridge alpha; next separate calibration period fixes empirical interval radii; subsequent tests used only for retrospective scores",
        "target": "daily regional SST in Celsius; all transformed forecasts returned to the common observed SST scale",
        "baseline": "original training calendar-day anomaly persistence, with known training seasonal cycle added at target date; raw SST persistence also reported",
        "intervals": "Gaussian AR conditional innovations vs held-out empirical error radii; calibration depends on serially dependent historical errors, no guaranteed coverage",
        "interpretation": "exploratory retrospective extension; multiple comparisons; block bootstrap assumes approximate stationarity; no pristine confirmatory holdout remains",
        "provider_acknowledgment": "SST data provided by NOAA PSL, Boulder, Colorado, USA. Polygon by Flanders Marine Institute / Marine Regions.",
    }
    (output_dir / "protocol.json").write_text(
        json.dumps(protocol, indent=2, allow_nan=False) + "\n"
    )
    write_research_report(
        metrics,
        pd.concat(all_yearly, ignore_index=True),
        skill,
        models,
        protocol,
        output_dir,
    )
    checksums = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(output_dir.iterdir())
        if p.is_file() and p.name != "checksums.json"
    }
    (output_dir / "checksums.json").write_text(
        json.dumps(checksums, indent=2, ensure_ascii=False) + "\n"
    )
    print(f"Complete research outputs: {output_dir}")
    print(
        metrics.query("domain == 'iho_yellow_sea' and fold == '2023-2025'").to_string(
            index=False
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/research.json"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw/research"))
    parser.add_argument(
        "--boundary-dir", type=Path, default=Path("data/raw/boundaries")
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data/processed/research")
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    run_research(args.config, args.raw_dir, args.boundary_dir, args.output_dir)


if __name__ == "__main__":
    main()
