"""Independent arithmetic and spatial-matching audit of destination scores."""

from datetime import datetime, timezone
import json

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from src.destination_validation import FROZEN, OUTPUT, SOURCE_ROOTS, forecast, verify
from src.validation import sha256


def xyz(lat, lon):
    lat, lon = (
        np.deg2rad(np.asarray(lat, dtype=float)),
        np.deg2rad(np.asarray(lon, dtype=float)),
    )
    return np.column_stack(
        [np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)]
    )


def tree_distance(tree, lat, lon):
    distance, index = tree.query(xyz(lat, lon))
    return index, 2 * 6371.0088 * np.arcsin(np.clip(distance / 2, 0, 1))


def nearest_like_frozen(tree, lat, lon, cell_lat, cell_lon):
    """Independent candidate search, then preserve frozen angle precision/ties."""
    _, candidates = tree.query(xyz(lat, lon), k=min(8, len(cell_lat)))
    candidates = np.sort(np.atleast_2d(candidates), axis=1)
    lat_rad, lon_rad = np.deg2rad(lat), np.deg2rad(lon)
    # The public production rule converts the stored float32 cell coordinates
    # directly to radians. Preserve that arithmetic when ranking near bisectors.
    cell_lat_rad, cell_lon_rad = np.deg2rad(cell_lat), np.deg2rad(cell_lon)
    a = np.sin((lat_rad[:, None] - cell_lat_rad[candidates]) / 2) ** 2
    a += (
        np.cos(lat_rad[:, None])
        * np.cos(cell_lat_rad[candidates])
        * np.sin((lon_rad[:, None] - cell_lon_rad[candidates]) / 2) ** 2
    )
    best = np.argmin(a, axis=1)
    index = candidates[np.arange(len(lat)), best]
    distance = (
        2 * 6371.0088 * np.arcsin(np.sqrt(np.clip(a[np.arange(len(lat)), best], 0, 1)))
    )
    return index, distance


def main():
    frozen = verify()
    cfg = frozen["config"]
    with np.load(OUTPUT / "locked_forecasts.npz") as cube:
        dates = pd.DatetimeIndex(cube["dates"])
        fixed, weights = cube["fixed_mask"], cube["weights"]
        predictions_by_model = {
            (h, model): forecast(cube, model, h)
            for h in cfg["horizons"]
            for model in frozen["models"]
        }
        analysis = cube["analysis"]
        keys = ["date", "pass", "horizon_days", "model", "target"]
        saved = pd.read_csv(
            OUTPUT / "satellite_daily_scores.csv",
            parse_dates=["date"],
            float_precision="round_trip",
        ).set_index(keys)
        coverage = pd.read_csv(
            OUTPUT / "satellite_coverage.csv",
            parse_dates=["date"],
            float_precision="round_trip",
        ).set_index(["date", "pass"])
        max_gap, checked = 0.0, 0
        for i, day in enumerate(dates):
            path = (
                SOURCE_ROOTS[0 if day.year < 2026 else 1] / f"amsr2-{day:%Y-%m-%d}.npz"
            )
            with np.load(path) as raw:
                for slot, passage in enumerate(["afternoon", "nighttime"]):
                    temperature = raw["SST"][slot][fixed].astype(float)
                    time = raw["time"][slot][fixed].astype(float)
                    valid = (
                        np.isfinite(temperature)
                        & (temperature >= -3)
                        & (temperature <= 35)
                        & (time >= 0)
                        & (time < 24)
                    )
                    for name in [
                        "land_mask",
                        "coast_mask",
                        "sea_ice_mask",
                        "noobs_mask",
                    ]:
                        valid &= raw[name][slot][fixed] == 0
                    original = coverage.loc[(day, passage)]
                    if int(valid.sum()) != original.n_cells or bool(
                        original.scored
                    ) != (valid.sum() >= cfg["minimum_satellite_cells"]):
                        raise ValueError(
                            "independent satellite quality/support mismatch"
                        )
                    if valid.sum() < cfg["minimum_satellite_cells"]:
                        continue
                    w = weights[valid] / np.sum(weights[valid])
                    for h in cfg["horizons"]:
                        predictions = np.stack(
                            [
                                predictions_by_model[h, model][i, valid]
                                for model in frozen["models"]
                            ]
                        )
                        for target, truth in [
                            ("AMSR2", temperature[valid]),
                            ("matched_OISST", analysis[i, valid]),
                        ]:
                            errors = predictions - truth[None, :]
                            recomputed = np.column_stack(
                                [
                                    np.sum(errors**2 * w, axis=1),
                                    np.sum(abs(errors) * w, axis=1),
                                    np.sum(errors * w, axis=1),
                                ]
                            )
                            for j, model in enumerate(frozen["models"]):
                                row = saved.loc[(day, passage, h, model, target)]
                                gap = float(
                                    np.max(
                                        abs(
                                            recomputed[j]
                                            - row[["mse", "mae", "bias"]].to_numpy(
                                                float
                                            )
                                        )
                                    )
                                )
                                max_gap = max(max_gap, gap)
                                checked += 1
        if checked != len(saved) or max_gap > 1e-10:
            raise ValueError("satellite arithmetic audit failed")
        satellite_audit = {
            "all_daily_rows_recomputed": checked,
            "maximum_absolute_loss_difference": max_gap,
            "method": "Raw cache masks independently reconstructed; vectorized weighted sums replace production dot products.",
        }
        dst_tree = cKDTree(xyz(cube["lat"], cube["lon"]))
        src_tree = cKDTree(xyz(cube["source_lat"], cube["source_lon"]))
        independently_matched = []
        raw_columns = None
        raw_dtypes = None
        for path in sorted(SOURCE_ROOTS[2].glob("iquam-*.npz")):
            with np.load(path) as raw:
                q = pd.DataFrame({k: raw[k] for k in raw.files})
            raw_columns, raw_dtypes = q.columns.tolist(), q.dtypes
            q["date"] = pd.to_datetime(q.time, unit="s", origin="1981-01-01").dt.floor(
                "D"
            )
            q["observed"] = q.sst.astype(float) - 273.15
            indices, dest_distance = nearest_like_frozen(
                dst_tree,
                q.lat.to_numpy(float),
                q.lon.to_numpy(float),
                cube["lat"],
                cube["lon"],
            )
            _, source_distance = nearest_like_frozen(
                src_tree,
                q.lat.to_numpy(float),
                q.lon.to_numpy(float),
                cube["source_lat"],
                cube["source_lon"],
            )
            valid = (
                (dest_distance <= cfg["buoy_max_distance_km"])
                & (source_distance > cfg["buoy_exclude_within_source_km"])
                & (q.quality_level == cfg["buoy_quality_level"])
                & np.isin(q.platform_type, cfg["buoy_platform_types"])
                & np.isfinite(q.observed)
                & (q.observed >= -2)
                & (q.observed <= 35)
                & (q.date >= pd.Timestamp(cfg["date_start"]))
                & (q.date <= pd.Timestamp(cfg["primary_end"]))
                & (q.date.dt.strftime("%Y%m") == path.stem.removeprefix("iquam-"))
                & q.platform_id.str.strip().ne("")
                & ((q.sst_flags.astype(int) & 1) == 0)
            )
            q["cell"] = indices
            q["pass"] = np.where(
                (q.sst_flags.astype(int) & 2) == 0, "nighttime", "daytime"
            )
            independently_matched.append(q.loc[valid].copy())
        q = pd.concat(independently_matched, ignore_index=True)
        recorded = pd.read_csv(
            OUTPUT / "matched_buoy_points.csv",
            parse_dates=["date"],
            dtype={"platform_id": str},
            float_precision="round_trip",
        )
        for name in raw_columns:
            recorded[name] = recorded[name].astype(raw_dtypes[name])
        left = pd.util.hash_pandas_object(
            q[raw_columns + ["cell", "pass"]], index=False
        ).to_numpy()
        right = pd.util.hash_pandas_object(
            recorded[raw_columns + ["cell", "pass"]], index=False
        ).to_numpy()
        if not np.array_equal(np.sort(left), np.sort(right)):
            raise ValueError("independent spherical KD-tree/quality matching differs")
        saved = pd.read_csv(
            OUTPUT / "buoy_daily_scores.csv",
            parse_dates=["date"],
            float_precision="round_trip",
        ).set_index(keys)
        gap, checked = 0.0, 0
        for passage, group in q.groupby("pass"):
            count_per_platform = (
                group.groupby(["date", "platform_type", "platform_id"])["cell"]
                .transform("size")
                .to_numpy(float)
            )
            platform_count = (
                group[["date", "platform_type", "platform_id"]]
                .drop_duplicates()
                .groupby("date")
                .size()
            )
            weight = (
                1 / count_per_platform / group.date.map(platform_count).to_numpy(float)
            )
            unique_days = pd.DatetimeIndex(sorted(group.date.unique()))
            bins = unique_days.get_indexer(group.date)
            if not np.allclose(
                np.bincount(bins, weights=weight), 1, atol=1e-12, rtol=0
            ):
                raise ValueError("platform balancing weight not normalized")
            i, j = dates.get_indexer(group.date), group.cell.to_numpy(int)
            for h in cfg["horizons"]:
                for model in frozen["models"]:
                    prediction = predictions_by_model[h, model][i, j]
                    for target, truth in [
                        ("iQuam", group.observed.to_numpy(float)),
                        ("matched_OISST", analysis[i, j]),
                    ]:
                        errors = prediction - truth
                        calculated = np.column_stack(
                            [
                                np.bincount(bins, weights=weight * errors**2),
                                np.bincount(bins, weights=weight * abs(errors)),
                                np.bincount(bins, weights=weight * errors),
                            ]
                        )
                        expected = saved.loc[
                            [(d, passage, h, model, target) for d in unique_days],
                            ["mse", "mae", "bias"],
                        ].to_numpy(float)
                        gap = max(gap, float(np.max(abs(calculated - expected))))
                        checked += len(unique_days)
        if checked != len(saved) or gap > 1e-10:
            raise ValueError("buoy weighting audit failed")
    verify()
    record = {
        "audited_utc": datetime.now(timezone.utc).isoformat(),
        "protocol_sha256": sha256(FROZEN),
        "software_sha256": sha256(__file__),
        "satellite": satellite_audit,
        "buoys": {
            "matched_records": len(q),
            "all_daily_rows_recomputed": checked,
            "maximum_absolute_loss_difference": gap,
            "matching_method": "Double-precision unit-sphere KD-tree candidates followed by frozen-precision spherical reranking independently replace all-pairs search; every record and nearest-cell assignment reproduces. Stored float32 cell-angle conversion is preserved at near bisectors.",
            "weighting_method": "Inverse platform-day count and inverse daily platform count; bincount sums independently replace hierarchical grouped averages.",
        },
        "all_previous_files_and_locked_forecasts_unchanged": True,
        "scope": "Independent implementation of extraction, matching and score arithmetic; not independent acquisition, a new observation source, or evidence of latent-truth independence.",
    }
    (OUTPUT / "independent_audit.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
