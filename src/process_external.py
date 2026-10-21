"""Descriptive satellite check of new regional forcing-model increments.

Projection preserves the observed spatial offset at the origin. No extra fitting,
selection or significance tests are performed; all physical/SST ablations remain.
"""

from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.independent import quality_mask
from src.confirmation import verify_inputs
from src.process_transfer import OUTPUT, load_config
from src.publication import read_fields
from src.validation import sha256


def evaluate():
    verify_inputs()
    cfg = load_config()
    frozen = json.loads(Path("paper/validation/frozen_protocol.json").read_text())
    dates, fields, weights, fixed, _, _, _, oisst_records = read_fields(cfg, frozen)
    positions = {d: i for i, d in enumerate(dates)}
    regional = fields.astype(float) @ weights
    forecasts = pd.read_csv(
        OUTPUT / "predictions.csv",
        parse_dates=["date", "origin_date"],
        low_memory=False,
    )
    forecasts = forecasts.loc[
        (forecasts.domain == "yellow_bohai")
        & (forecasts.fitting == "source_local")
        & (forecasts.period == "2023-2025")
    ]
    grouped = {
        (h, family, group): g.set_index("date").predicted
        for (h, family, group), g in forecasts.groupby(
            ["horizon_days", "family", "group"]
        )
    }
    days = pd.date_range("2023-01-01", "2025-12-31")
    if len(grouped) != 18 or any(not g.index.equals(days) for g in grouped.values()):
        raise ValueError(
            "all eighteen new forecasts must share the complete test calendar"
        )
    models = ["grid_anomaly_persistence"]
    rows, records = [], []
    with np.load("data/processed/confirmation/locked_forecasts.npz") as locked:
        locked_dates = pd.DatetimeIndex(locked["dates"])
        locked_index = {d: i for i, d in enumerate(locked_dates)}
        for day in days:
            path = Path("data/raw/confirmation") / f"amsr2-{day:%Y-%m-%d}.npz"
            if not path.exists():
                # File names are provider-date based; require a unique date match.
                candidates = list(
                    Path("data/raw/confirmation").glob(f"*{day:%Y-%m-%d}*.npz")
                )
                if len(candidates) != 1:
                    raise ValueError(
                        "expected one audited AMSR2 file for " + str(day.date())
                    )
                path = candidates[0]
            rec = json.loads(path.with_suffix(".json").read_text())
            if rec.get("subset_sha256", rec.get("sha256")) != sha256(path):
                raise ValueError("AMSR2 cache checksum mismatch")
            records.append(
                {"date": str(day.date()), "path": str(path), "sha256": sha256(path)}
            )
            with np.load(path) as obs:
                if not np.array_equal(
                    obs["lat"], frozen["spatial_mask"]["lat"]
                ) or not np.array_equal(obs["lon"], frozen["spatial_mask"]["lon"]):
                    raise ValueError("AMSR2 grid differs from frozen OISST grid")
                # Source archive ordering and decoder follow the original lock.
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
                )
                y = obs["SST"][1][fixed].astype(float)
                valid = valid[fixed]
            n = int(valid.sum())
            if n < 20:
                continue
            w = weights[valid] / weights[valid].sum()
            i = positions[day]
            for h in cfg["horizons"]:
                origin = positions[day - pd.Timedelta(days=h)]
                base = locked[f"h{h}__{models[0]}"][locked_index[day]].astype(float)
                for family, group, predicted in [
                    ("grid_anomaly_persistence", "sst", base),
                    *[
                        (
                            family,
                            group,
                            fields[origin].astype(float)
                            + forecasts_series.loc[day]
                            - regional[origin],
                        )
                        for (lead, family, group), forecasts_series in grouped.items()
                        if lead == h
                    ],
                ]:
                    for target, truth in [
                        ("matched_OISST", fields[i].astype(float)),
                        ("AMSR2_night", y),
                    ]:
                        e = predicted[valid] - truth[valid]
                        rows.append(
                            {
                                "date": day,
                                "horizon_days": h,
                                "family": family,
                                "group": group,
                                "target": target,
                                "n_cells": n,
                                "mse": float(w @ e**2),
                                "bias": float(w @ e),
                                "mae": float(w @ abs(e)),
                            }
                        )
    frame = pd.DataFrame(rows)
    frame["year"] = frame.date.dt.year
    old = pd.read_csv(
        "data/processed/confirmation/daily_scores.csv", parse_dates=["date"]
    )
    original = old.loc[
        (old.period == "2023-2025")
        & (old.target == "matched_grid_AMSR2")
        & (old["pass"] == "descending")
        & (old.model == "grid_anomaly_persistence")
    ]
    repeat = frame.loc[
        (frame.target == "AMSR2_night") & (frame.family == "grid_anomaly_persistence")
    ]
    original = original.set_index(["date", "horizon_days"]).sort_index()
    repeat = repeat.set_index(["date", "horizon_days"]).sort_index()
    if not repeat.index.equals(original.index) or not np.allclose(
        repeat.mse, original.mse, rtol=1e-12, atol=1e-12
    ):
        raise ValueError("original AMSR2 scoring support/loss failed replication")
    frame.to_csv(OUTPUT / "external_daily_scores.csv", index=False)
    keys = ["target", "horizon_days", "family", "group"]
    for extra, filename in [
        ([], "external_metrics.csv"),
        (["year"], "external_annual_metrics.csv"),
    ]:
        out = frame.groupby(keys + extra).agg(
            n_days=("mse", "size"), mse=("mse", "mean"), bias=("bias", "mean")
        )
        out["rmse"] = np.sqrt(out.mse)
        out.reset_index().to_csv(OUTPUT / filename, index=False)
    audit = {
        "evaluated_utc": datetime.now(timezone.utc).isoformat(),
        "forecast_source_sha256": sha256(OUTPUT / "predictions.csv"),
        "original_locked_cube_sha256": sha256(
            "data/processed/confirmation/locked_forecasts.npz"
        ),
        "software_sha256": sha256(__file__),
        "oisst_files": oisst_records,
        "amsr2_files": records,
        "n_nighttime_dates": int(frame.date.nunique()),
        "projection": "origin OISST cell + new regional forecast - original regional OISST at origin",
        "scope": "Additional descriptive post-design diagnostic, after viewing original external outcomes. No new fitting, selection, p value or independent-confirmation claim. Source domain only; destination satellite observations are not acquired.",
    }
    (OUTPUT / "external_audit.json").write_text(json.dumps(audit, indent=2) + "\n")


if __name__ == "__main__":
    evaluate()
