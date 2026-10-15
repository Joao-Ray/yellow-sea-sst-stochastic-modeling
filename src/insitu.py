"""Frozen descriptive third-source verification using NOAA iQuam buoys."""

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.download_iquam import acquire_month
from src.evaluation.confirmation_report import LABELS, markdown_table, relative_skill
from src.validation import sha256

FROZEN = Path("paper/insitu/frozen_protocol.json")
OUTPUT = Path("data/processed/insitu")
RAW = Path("data/raw/insitu")


def protocol():
    f = json.loads(FROZEN.read_text())
    for path, digest in f["input_sha256"].items():
        if sha256(path) != digest:
            raise ValueError("in situ frozen input changed: " + path)
    return f


def acquire(workers, failed_only=False):
    f = protocol()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    successes, failures = [], []
    selected = f["source_urls"]
    status_file = OUTPUT / "acquisition_status.json"
    if failed_only:
        previous = json.loads(status_file.read_text())
        stamps = {item["month"] for item in previous["failures"]}
        selected = {stamp: url for stamp, url in selected.items() if stamp in stamps}
        status_file = OUTPUT / "acquisition_retry_status.json"
    with ProcessPoolExecutor(max_workers=workers) as pool:
        jobs = {
            pool.submit(acquire_month, stamp, url, f["region"], RAW): stamp
            for stamp, url in selected.items()
        }
        for job in as_completed(jobs):
            stamp = jobs[job]
            try:
                job.result()
                successes.append(stamp)
                print(f"Acquired {stamp}; {len(successes)}/{len(selected)}", flush=True)
            except Exception as exc:
                failures.append({"month": stamp, "error": repr(exc)})
                print(f"Failed {stamp}: {exc}", flush=True)
            status_file.write_text(
                json.dumps(
                    {
                        "updated_utc": datetime.now(timezone.utc).isoformat(),
                        "completed": successes,
                        "failures": failures,
                    },
                    indent=2,
                )
                + "\n"
            )
    if failures:
        raise RuntimeError("iQuam acquisition incomplete; valid caches retained")


def nearest_cells(lat, lon, cell_lat, cell_lon):
    """Spherical nearest fixed-cell center, including a physically scaled gate."""
    lat, lon, cell_lat, cell_lon = map(np.deg2rad, [lat, lon, cell_lat, cell_lon])
    a = (
        np.sin((lat[:, None] - cell_lat) / 2) ** 2
        + np.cos(lat[:, None])
        * np.cos(cell_lat)
        * np.sin((lon[:, None] - cell_lon) / 2) ** 2
    )
    index = np.argmin(a, axis=1)
    distance = (
        2 * 6371.0088 * np.arcsin(np.sqrt(np.clip(a[np.arange(len(lat)), index], 0, 1)))
    )
    return index, distance


def equal_platform_daily(frame, error):
    """Equal platform-day loss, then equal daily weight; do not square daily means."""
    q = frame[["date", "platform_type", "platform_id"]].copy()
    q["mse"], q["mae"], q["bias"] = error**2, np.abs(error), error
    q["n_records"] = 1
    platform = q.groupby(["date", "platform_type", "platform_id"]).agg(
        mse=("mse", "mean"),
        mae=("mae", "mean"),
        bias=("bias", "mean"),
        n_records=("n_records", "sum"),
    )
    return (
        platform.groupby("date")
        .agg(
            mse=("mse", "mean"),
            mae=("mae", "mean"),
            bias=("bias", "mean"),
            n_records=("n_records", "sum"),
            n_platforms=("mse", "size"),
        )
        .reset_index()
    )


def evaluate():
    f = protocol()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with np.load("data/processed/confirmation/locked_forecasts.npz") as cube:
        dates = pd.DatetimeIndex(cube["dates"])
        date_index = {d: i for i, d in enumerate(dates)}
        cell_lat, cell_lon = cube["lat"], cube["lon"]
        metadata, points = [], []
        for stamp, url in f["source_urls"].items():
            path = RAW / f"iquam-{stamp}.npz"
            record = json.loads(path.with_suffix(".json").read_text())
            if record["source_url"] != url or record["subset_sha256"] != sha256(path):
                raise ValueError("iQuam source checksum or identity changed")
            if datetime.fromisoformat(record["acquired_utc"]) <= datetime.fromisoformat(
                f["frozen_utc"]
            ):
                raise ValueError("iQuam acquisition did not follow the freeze")
            metadata.append(
                {
                    k: record[k]
                    for k in [
                        "source_url",
                        "subset_sha256",
                        "source_etag",
                        "acquired_utc",
                        "acquired_bytes",
                        "subset_records",
                    ]
                }
            )
            with np.load(path) as obs:
                q = pd.DataFrame({k: obs[k] for k in obs.files})
            q["date"] = (
                pd.Timestamp("1981-01-01")
                + pd.to_timedelta(q.time.astype(float), unit="s")
            ).dt.normalize()
            q["observed_celsius"] = q.sst.astype(float) - 273.15
            index, distance = nearest_cells(
                q.lat.to_numpy(float), q.lon.to_numpy(float), cell_lat, cell_lon
            )
            q["cell_index"], q["distance_km"] = index, distance
            q["source_month"] = stamp
            q["valid"] = (
                q.quality_level.eq(f["quality_level"])
                & q.platform_type.isin(f["primary_platform_types"])
                & np.isfinite(q.observed_celsius)
                & q.observed_celsius.between(f["sst_celsius_min"], f["sst_celsius_max"])
                & q.distance_km.le(f["maximum_nearest_fixed_cell_distance_km"])
                & q.date.between(f["date_start"], f["date_end"])
                & q.date.dt.strftime("%Y%m").eq(stamp)
                & q.platform_id.str.strip().ne("")
                & (q.sst_flags.astype(int) & 1).eq(0)
            )
            q["pass"] = np.where(
                (q.sst_flags.astype(int) & 2).eq(0), "nighttime", "daytime"
            )
            points.append(q)
        points = pd.concat(points, ignore_index=True)
        coverage = (
            points.groupby(["source_month", "pass"])
            .agg(geographic_records=("valid", "size"), valid_records=("valid", "sum"))
            .reset_index()
        )
        valid = points.loc[points.valid].copy()
        valid["target_index"] = valid.date.map(date_index)
        if valid.target_index.isna().any():
            raise ValueError("a point falls outside locked forecast dates")
        valid["target_index"] = valid.target_index.astype(int)
        model_frozen = json.loads(
            Path("paper/confirmation/frozen_protocol.json").read_text()
        )
        rows = []
        for passage, g in valid.groupby("pass"):
            i, j = g.target_index.to_numpy(int), g.cell_index.to_numpy(int)
            for target, truth in [
                ("matched_OISST", cube["analysis"][i, j].astype(float)),
                ("iQuam_buoys", g.observed_celsius.to_numpy(float)),
            ]:
                for h in f["horizons"]:
                    for model in model_frozen["models"]:
                        error = cube[f"h{h}__{model}"][i, j].astype(float) - truth
                        daily = equal_platform_daily(g, error)
                        (
                            daily["target"],
                            daily["pass"],
                            daily["horizon_days"],
                            daily["model"],
                        ) = target, passage, h, model
                        rows.extend(daily.to_dict("records"))
    daily = pd.DataFrame(rows)
    daily["year"] = pd.DatetimeIndex(daily.date).year
    annual = []
    for key, g in daily.groupby(["year", "target", "pass", "horizon_days", "model"]):
        annual.append(
            {
                **dict(zip(["year", "target", "pass", "horizon_days", "model"], key)),
                "n_days": len(g),
                "n_platform_days": int(g.n_platforms.sum()),
                "n_records": int(g.n_records.sum()),
                "rmse": float(np.sqrt(g.mse.mean())),
                "mae": float(g.mae.mean()),
                "bias": float(g.bias.mean()),
            }
        )
    annual = relative_skill(
        pd.DataFrame(annual), ["year", "target", "pass", "horizon_days"]
    )
    pooled = []
    for key, g in daily.groupby(["target", "pass", "horizon_days", "model"]):
        pooled.append(
            {
                **dict(zip(["target", "pass", "horizon_days", "model"], key)),
                "n_days": len(g),
                "n_platform_days": int(g.n_platforms.sum()),
                "n_records": int(g.n_records.sum()),
                "rmse": float(np.sqrt(g.mse.mean())),
                "mae": float(g.mae.mean()),
                "bias": float(g.bias.mean()),
            }
        )
    pooled = relative_skill(pd.DataFrame(pooled), ["target", "pass", "horizon_days"])
    gate = annual.loc[
        annual.target.eq("iQuam_buoys")
        & annual["pass"].eq("nighttime")
        & annual.model.eq(f["baseline"])
        & annual.horizon_days.eq(1)
    ]
    passed = len(gate) == 3 and bool(
        gate.n_days.ge(f["minimum_primary_dates_per_year"]).all()
    )
    platform_support = (
        valid.groupby(["platform_type", "platform_id", "pass"])
        .agg(
            n_records=("date", "size"),
            n_days=("date", "nunique"),
            lat_mean=("lat", "mean"),
            lon_mean=("lon", "mean"),
        )
        .reset_index()
    )
    for name, table in {
        "daily_scores": daily,
        "annual_metrics": annual,
        "metrics": pooled,
        "coverage": coverage,
        "platform_support": platform_support,
        "collocations": valid,
    }.items():
        table.to_csv(OUTPUT / (name + ".csv"), index=False, date_format="%Y-%m-%d")
    (OUTPUT / "provenance.json").write_text(json.dumps(metadata, indent=2) + "\n")
    audit = {
        "frozen_protocol_sha256": sha256(FROZEN),
        "public_freeze_commit": "16fa9b784692c9bf2eacdf5513433865a3e602db",
        "scoring_software_sha256": sha256(__file__),
        "source_months": len(metadata),
        "primary_annual_coverage_gate_passed": passed,
        "scope": f["scope"],
    }
    (OUTPUT / "evaluation_audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    write_report(pooled, annual, valid, cell_lat, cell_lon, f, passed)
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
    print(pooled.to_string(index=False))


def write_report(pooled, annual, valid, lat, lon, f, passed):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(11.5, 5), layout="constrained")
    for ax, passage in zip(axes, ["nighttime", "daytime"]):
        ax.scatter(lon, lat, s=4, c="#d0d8dc", label="Fixed ocean-cell centers")
        g = valid.loc[valid["pass"].eq(passage)]
        locations = g[["lon", "lat"]].drop_duplicates()
        ax.scatter(
            locations.lon,
            locations.lat,
            s=4,
            alpha=0.3,
            color="#3274a1",
            label="Accepted buoy coordinates",
        )
        ax.set(
            title=passage.capitalize(),
            xlabel="Longitude (°E)",
            ylabel="Latitude (°N)",
            xlim=(117, 128),
            ylim=(31, 42),
            aspect=1 / np.cos(np.deg2rad(36.5)),
        )
        ax.legend(fontsize=7, markerscale=2)
    fig.suptitle("iQuam point support | 2023–2025 (not full-basin sampling)")
    for extension in ["png", "svg"]:
        fig.savefig(OUTPUT / ("buoy_support." + extension), dpi=300)
    plt.close(fig)
    p = pooled.loc[
        pooled.target.eq("iQuam_buoys") & pooled["pass"].eq("nighttime")
    ].copy()
    display = pd.DataFrame(
        {
            "Model": p.model.map(LABELS),
            "Lead (d)": p.horizon_days,
            "Dates": p.n_days,
            "RMSE (°C)": p.rmse.map(lambda x: f"{x:.4f}"),
            "Bias (°C)": p.bias.map(lambda x: f"{x:.4f}"),
            "Skill (%)": (100 * p.skill_vs_grid_anomaly_persistence).map(
                lambda x: f"{x:.2f}"
            ),
        }
    )
    text = f"""# Three-year in situ buoy verification

The iQuam source versions, forecast bytes and matching rules were frozen before these SST point values were acquired. The source covers all 36 months of 2023–2025. Best-quality (`quality_level=5`) thermometric records from drifting, moored, high-resolution drifter and CRW buoys are matched to their nearest fixed ocean-cell center within 20 km on the same UTC date. Nighttime uses the provider's day/night flag; daytime is a separate descriptive sensitivity. Kelvin values are converted to degrees Celsius without bias adjustment. Neither observation time, instrument depth nor footprint is identical to a daily gridded analysis.

Repeated records first receive equal weight within a platform-day; platforms then receive equal weight within each date, and scoring dates receive equal weight. Squared errors are averaged before their square root. Consequently, many hourly records from one buoy cannot dominate a day or masquerade as many independent platforms. This sample is not area weighted and cannot be interpreted as a basin mean.

The frozen gate requires 60 nighttime scoring dates in each year: **{"passed" if passed else "not passed; coverage-limited descriptive results only"}**. Results are descriptive; no additional significance test, forecast selection or tuning was undertaken.

{markdown_table(display)}

![Spatial support](buoy_support.png)

## Limits of independence

iQuam quality control uses Reynolds and CMC analysis references; some in situ measurements may overlap inputs to OISST. This is a third measurement pathway and a useful point-support check, not a statistically independent held-out sample or error-free truth. Along with AMSR2 calibration dependencies, it prevents interpretation of agreement as three independent estimates of latent ocean temperature. Original data flags, locations, times, identifiers and source checksums are retained; matched-OISST and iQuam loss tables use exactly the same platform/day support.

Source: [NOAA iQuam](https://www.star.nesdis.noaa.gov/socd/sst/iquam/data.html); QC dependency: [Zhang et al. (2021)](https://doi.org/10.1175/JTECH-D-20-0203.1).

The [NOAA provider notice](https://www.star.nesdis.noaa.gov/socd/sst/iquam/) states that SST team members have not monitored the data since 31 May 2025. Later archived files do not establish continuing human review. In this sample, October 2025 has no accepted nighttime buoy records; the supplied monthly coverage table retains that zero. Complete acquisition of 36 source files does not imply complete observational sampling or constant data quality.
"""
    (OUTPUT / "report_en.md").write_text(text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["acquire", "evaluate"])
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--failed-only", action="store_true")
    args = parser.parse_args()
    if args.action == "acquire":
        acquire(args.workers, args.failed_only)
    else:
        evaluate()
