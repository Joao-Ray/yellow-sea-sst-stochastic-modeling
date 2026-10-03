"""Reproduce a frozen exploratory observational pilot from NOAA regional data."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from datetime import date
from importlib.metadata import version
from pathlib import Path

import pandas as pd

from src.data.download_psl import download_regional_range
from src.data.preprocess import Region, build_anomaly_table, load_regional_sst
from src.evaluation.bootstrap import skill_interval
from src.evaluation.diagnostics import write_diagnostics
from src.evaluation.experiment import run_experiment, write_experiment
from src.evaluation.report_zh import write_chinese_summary


def run_pilot(config_file: Path, raw_dir: Path, output_dir: Path) -> None:
    config = json.loads(config_file.read_text())
    output_dir.mkdir(parents=True, exist_ok=True)
    snapshot = output_dir / "pilot_config.json"
    if snapshot.exists() and json.loads(snapshot.read_text()) != config:
        raise ValueError(
            "output directory belongs to a different pilot design; choose a new directory"
        )
    snapshot.write_text(json.dumps(config, indent=2) + "\n")
    region = Region(**config["region"])
    files = download_regional_range(
        date.fromisoformat(config["date_start"]),
        date.fromisoformat(config["date_end"]),
        region,
        raw_dir,
    )
    sst = load_regional_sst(files, region)
    table = build_anomaly_table(
        sst,
        max_gap_days=0,
        climatology=config["climatology"],
        reference_start=config["date_start"],
        reference_end=config["train_end"],
    )
    processed = output_dir / "regional_sst_daily.csv"
    table.to_csv(processed, date_format="%Y-%m-%d")
    # Exercise the same on-disk input path as the standalone experiment CLI.
    table = pd.read_csv(processed, parse_dates=["date"]).set_index("date")
    result = run_experiment(
        table,
        train_end=config["train_end"],
        validation_end=config["validation_end"],
        horizons=tuple(config["horizons"]),
        climatology=config["climatology"],
        data_kind="observed",
        ar_candidates=tuple(config["ar_candidates"]),
        selection_horizon=config["selection_horizon"],
    )
    bootstrap_rows = []
    for row in result.metrics.itertuples():
        if row.split != "test":
            bootstrap_rows.append({})
            continue
        group = result.predictions.query(
            "split == 'test' and horizon_days == @row.horizon_days"
        )
        scored = group[group.model.eq(row.model)].set_index("date").sort_index()
        baseline = group[group.model.eq("persistence")].set_index("date").sort_index()
        bootstrap_rows.append(
            skill_interval(
                scored.observed_anomaly_celsius,
                scored.predicted_anomaly_celsius,
                baseline.predicted_anomaly_celsius,
                block_days=max(config["bootstrap_block_days"], row.horizon_days),
                replicates=config["bootstrap_replicates"],
                seed=config["random_seed"],
            )
        )
    result.metrics = pd.concat([result.metrics, pd.DataFrame(bootstrap_rows)], axis=1)
    provenance = [json.loads(path.with_suffix(".json").read_text()) for path in files]
    result.protocol.update(
        {
            "pilot_config": config,
            "input_sha256": hashlib.sha256(processed.read_bytes()).hexdigest(),
            "source_acquisitions": provenance,
            "source_bytes": sum(path.stat().st_size for path in files),
            "provider_acknowledgment": "Data provided by NOAA PSL, Boulder, Colorado, USA, https://psl.noaa.gov",
            "runtime_versions": {
                name: version(name)
                for name in (
                    "numpy",
                    "pandas",
                    "xarray",
                    "netCDF4",
                    "statsmodels",
                    "matplotlib",
                )
            },
            "skill_intervals": "paired circular calendar-block bootstrap; test only; blocks at least 30 days and at least forecast horizon; percentile 95%; assumes approximate stationarity",
            "claim_scope": "preliminary bounding-box pilot; selection-biased validation; dependent test errors; no final geographical Yellow Sea conclusion",
        }
    )
    write_experiment(result, output_dir)
    write_diagnostics(result, output_dir)
    write_chinese_summary(result, output_dir)
    with (output_dir / "summary.md").open("a") as handle:
        handle.write(
            "\n## Diagnostics\n\n![Residual diagnostics](residual_diagnostics.png)\n\nSee residual_acf.csv, training_residuals.csv, diagnostics.json, and coverage_by_year.csv.\n"
        )
    print(result.metrics.to_string(index=False))
    print(f"Observed pilot report: {output_dir / 'summary.md'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/pilot.json"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw/psl-pilot"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed/pilot"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    run_pilot(args.config, args.raw_dir, args.output_dir)


if __name__ == "__main__":
    main()
