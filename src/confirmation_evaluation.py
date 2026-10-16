"""Evaluate locked stronger controls on three previously unread AMSR2 years."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.confirmation import FROZEN, OUTPUT, RAW, verify_inputs
from src.evaluation.publication_stats import (
    holm_adjust,
    loss_components,
    paired_block_inference,
)
from src.independent import quality_mask
from src.publication import aggregate_scores, daily_score
from src.validation import sha256


def evaluate():
    frozen = verify_inputs()
    config = frozen["config"]
    cube = np.load(OUTPUT / "locked_forecasts.npz")
    dates = pd.DatetimeIndex(cube["dates"])
    date_positions = {str(d.date()): i for i, d in enumerate(dates)}
    analysis = cube["analysis"]
    weights = cube["weights"]
    fixed = cube["fixed_mask"]
    models = frozen["models"]
    forecasts = {(h, m): cube[f"h{h}__{m}"] for h in config["horizons"] for m in models}
    score_rows = []
    decomposition = []
    coverage = []
    provenance = []
    for i, d in enumerate(dates):
        period = "2023-2025" if d.year < 2026 else "2026-Jan-Aug"
        for h in config["horizons"]:
            for name in models:
                prediction = forecasts[h, name][i]
                for target in ["full_grid_OISST", "regional_OISST"]:
                    forecast, truth, w = (
                        (prediction, analysis[i], weights)
                        if target.startswith("full")
                        else (
                            np.array([prediction.astype(float) @ weights]),
                            np.array([cube["regional"][i]]),
                            np.ones(1),
                        )
                    )
                    score_rows.append(
                        {
                            "date": d,
                            "period": period,
                            "target": target,
                            "pass": "all",
                            "horizon_days": h,
                            "model": name,
                            "n_cells": len(weights),
                            **daily_score(forecast, truth, w),
                        }
                    )
    for day in pd.date_range(config["external_start"], config["external_end"]):
        path = RAW / f"amsr2-{day.date()}.npz"
        if not path.exists():
            absent = RAW / f"missing-{day.date()}.json"
            if not absent.exists() or json.loads(absent.read_text())["status"] != 404:
                raise ValueError("unacquired external date: " + str(day.date()))
    sources = list(sorted(RAW.glob("amsr2-*.npz"))) + list(
        sorted(Path("data/raw/independent").glob("amsr2-*.npz"))
    )
    for path in sources:
        stamp = path.stem.removeprefix("amsr2-")
        if stamp not in date_positions:
            raise ValueError("external record outside locked dates")
        i = date_positions[stamp]
        day = dates[i]
        metadata = json.loads(path.with_suffix(".json").read_text())
        if sha256(path) != metadata["subset_sha256"]:
            raise ValueError("external subset hash changed")
        provenance.append(
            {
                "date": stamp,
                "source_url": metadata["source_url"],
                "subset_sha256": metadata["subset_sha256"],
                "source_etag": metadata["source_etag"],
                "acquired_utc": metadata["acquired_utc"],
                "acquired_bytes": metadata["acquired_bytes"],
            }
        )
        with np.load(path) as source:
            ygrid, xgrid = np.meshgrid(source["lat"], source["lon"], indexing="ij")
            if not np.array_equal(ygrid[fixed], cube["lat"]) or not np.array_equal(
                xgrid[fixed], cube["lon"]
            ):
                raise ValueError("external and locked coordinate order differ")
            for pass_index, pass_name in enumerate(["ascending", "descending"]):
                valid_grid = quality_mask(
                    source["SST"][pass_index],
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
                n = int(valid.sum())
                coverage.append(
                    {
                        "date": day,
                        "pass": pass_name,
                        "n_cells": n,
                        "valid_weight_fraction": float(weights[valid].sum()),
                        "scored": n >= config["minimum_external_cells"],
                    }
                )
                if n < config["minimum_external_cells"]:
                    continue
                w = weights[valid]
                w = w / w.sum()
                observed = source["SST"][pass_index][fixed][valid].astype(float)
                oisst = analysis[i, valid].astype(float)
                period = "2023-2025" if day.year < 2026 else "2026-Jan-Aug"
                for h in config["horizons"]:
                    for name in models:
                        prediction = forecasts[h, name][i, valid].astype(float)
                        parts = loss_components(prediction, oisst, observed, w)
                        if abs(parts["identity_error"]) > 1e-10:
                            raise ValueError("loss identity failed")
                        decomposition.append(
                            {
                                "date": day,
                                "period": period,
                                "pass": pass_name,
                                "horizon_days": h,
                                "model": name,
                                **parts,
                            }
                        )
                        for target, truth in [
                            ("matched_grid_OISST", oisst),
                            ("matched_grid_AMSR2", observed),
                        ]:
                            score_rows.append(
                                {
                                    "date": day,
                                    "period": period,
                                    "target": target,
                                    "pass": pass_name,
                                    "horizon_days": h,
                                    "model": name,
                                    "n_cells": n,
                                    **daily_score(prediction, truth, w),
                                }
                            )
    daily = pd.DataFrame(score_rows)
    daily["year"] = pd.DatetimeIndex(daily.date).year
    daily["season"] = [
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
        }[d.month]
        for d in daily.date
    ]
    metrics = aggregate_scores(daily)
    years = (
        daily.loc[
            daily.period.eq("2023-2025")
            & daily.target.eq("matched_grid_AMSR2")
            & daily["pass"].eq(config["primary_pass"])
        ]
        .groupby(["year", "horizon_days", "model"])
        .size()
    )
    if (
        len(years) != 3 * len(config["horizons"]) * len(models)
        or (years < config["minimum_primary_days_per_year"]).any()
    ):
        raise ValueError("a primary year/model fails the frozen minimum-day gate")
    old = pd.read_csv("paper/independent/metrics.csv")
    original = json.loads(Path("paper/validation/frozen_protocol.json").read_text())
    for h in config["horizons"]:
        for p in ["ascending", "descending"]:
            new = metrics.loc[
                metrics.period.eq("2026-Jan-Aug")
                & metrics.target.eq("matched_grid_AMSR2")
                & metrics["pass"].eq(p)
                & metrics.horizon_days.eq(h)
                & metrics.model.eq("frozen_selected_projection")
            ].iloc[0]
            primary = old.loc[
                old["pass"].eq(p)
                & old.horizon_days.eq(h)
                & old.model.eq(original["selected_methods"][str(h)])
            ].iloc[0]
            if new.n_days != primary.n_days or abs(new.rmse - primary.rmse) > 1e-5:
                raise ValueError("original 2026 score failed replication")
    inference = []
    for block in config["bootstrap_block_days"]:
        for h in config["horizons"]:
            g = daily.loc[
                daily.period.eq("2023-2025")
                & daily.target.eq("matched_grid_AMSR2")
                & daily["pass"].eq(config["primary_pass"])
                & daily.horizon_days.eq(h)
            ]
            losses = {
                m: q.set_index("date").sort_index().mse for m, q in g.groupby("model")
            }
            for model in config["primary_models"]:
                inference.append(
                    {
                        "model": model,
                        "horizon_days": h,
                        "family_size": config["primary_family_size"],
                        **paired_block_inference(
                            losses[model],
                            losses[config["primary_baseline"]],
                            block,
                            config["bootstrap_replicates"],
                            config["bootstrap_seed"],
                        ),
                    }
                )
    infer = pd.DataFrame(inference)
    for block in config["bootstrap_block_days"]:
        selected = infer.bootstrap_block_days.eq(block)
        if selected.sum() != config["primary_family_size"]:
            raise ValueError("primary family size differs")
        infer.loc[selected, "p_holm_nine_comparisons"] = holm_adjust(
            infer.loc[selected, "p_bootstrap_two_sided"]
        )
    annual = []
    for key, g in daily.groupby(["year", "target", "pass", "horizon_days", "model"]):
        annual.append(
            {
                **dict(zip(["year", "target", "pass", "horizon_days", "model"], key)),
                "n_days": len(g),
                "rmse": float(np.sqrt(g.mse.mean())),
                "bias": float(g.bias.mean()),
            }
        )
    seasonal = []
    for key, g in daily.groupby(
        ["period", "season", "target", "pass", "horizon_days", "model"]
    ):
        seasonal.append(
            {
                **dict(
                    zip(
                        ["period", "season", "target", "pass", "horizon_days", "model"],
                        key,
                    )
                ),
                "n_days": len(g),
                "rmse": float(np.sqrt(g.mse.mean())),
                "bias": float(g.bias.mean()),
            }
        )
    parts = pd.DataFrame(decomposition)
    transfer = []
    for key, group in parts.groupby(["date", "period", "pass", "horizon_days"]):
        by_model = group.set_index("model")
        base = by_model.loc[config["primary_baseline"]]
        for model in models:
            current = by_model.loc[model]
            analysis_advantage = (
                base.analysis_forecast_mse - current.analysis_forecast_mse
            )
            external_advantage = base.external_mse - current.external_mse
            perturbation = base.interaction - current.interaction
            residual = external_advantage - analysis_advantage - perturbation
            if abs(residual) > 1e-10:
                raise ValueError("relative-advantage identity failed")
            transfer.append(
                {
                    **dict(zip(["date", "period", "pass", "horizon_days"], key)),
                    "model": model,
                    "advantage_analysis": analysis_advantage,
                    "advantage_external": external_advantage,
                    "discrepancy_perturbation": perturbation,
                    "identity_error": residual,
                }
            )
    tables = {
        "daily_scores": daily,
        "metrics": metrics,
        "primary_inference": infer,
        "annual_metrics": pd.DataFrame(annual),
        "seasonal_metrics": pd.DataFrame(seasonal),
        "coverage": pd.DataFrame(coverage),
        "loss_decomposition_daily": parts,
        "skill_transfer_daily": pd.DataFrame(transfer),
    }
    tables["loss_decomposition"] = parts.groupby(
        ["period", "pass", "horizon_days", "model"], as_index=False
    ).agg(
        n_days=("date", "size"),
        analysis_forecast_mse=("analysis_forecast_mse", "mean"),
        product_discrepancy_mse=("product_discrepancy_mse", "mean"),
        interaction=("interaction", "mean"),
        external_mse=("external_mse", "mean"),
    )
    tables["skill_transfer"] = (
        tables["skill_transfer_daily"]
        .groupby(["period", "pass", "horizon_days", "model"], as_index=False)
        .agg(
            n_days=("date", "size"),
            advantage_analysis=("advantage_analysis", "mean"),
            advantage_external=("advantage_external", "mean"),
            discrepancy_perturbation=("discrepancy_perturbation", "mean"),
        )
    )
    for name, table in tables.items():
        table.to_csv(OUTPUT / (name + ".csv"), index=False, date_format="%Y-%m-%d")
    (OUTPUT / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    (OUTPUT / "evaluation_audit.json").write_text(
        json.dumps(
            {
                "frozen_protocol_sha256": sha256(FROZEN),
                "scoring_software_sha256": sha256(__file__),
                "maximum_loss_identity_residual": float(
                    parts.identity_error.abs().max()
                ),
                "maximum_relative_advantage_identity_residual": float(
                    tables["skill_transfer_daily"].identity_error.abs().max()
                ),
                "replicated_original_2026": True,
                "external_source_files": len(provenance),
                "scope": config["scope"],
            },
            indent=2,
        )
        + "\n"
    )
    from src.evaluation.confirmation_report import write_report

    write_report(tables, frozen, OUTPUT)
    (OUTPUT / "checksums.json").write_text(
        json.dumps(
            {
                p.name: sha256(p)
                for p in OUTPUT.iterdir()
                if p.is_file() and p.name != "checksums.json"
            },
            indent=2,
        )
        + "\n"
    )
    print(infer.to_string(index=False))


if __name__ == "__main__":
    evaluate()
