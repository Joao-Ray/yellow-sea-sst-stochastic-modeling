"""Fixed geographical masks and audited regional means for the complete study."""

from pathlib import Path
import numpy as np
import pandas as pd
from shapely.geometry import box
import xarray as xr

from src.data.marine_boundary import grid_mask


def build_research_series(
    files: list[Path], geometry, config: dict, output_dir: Path
) -> tuple[dict, dict]:
    region = config["acquisition_region"]
    west, south, east, north = geometry.bounds
    if not (
        region["lon_min"] <= west < east <= region["lon_max"]
        and region["lat_min"] <= south < north <= region["lat_max"]
    ):
        raise ValueError("acquisition region truncates the marine polygon")
    with xr.open_mfdataset(
        [str(p) for p in files],
        combine="by_coords",
        chunks={"time": 31},
        engine="netcdf4",
    ) as source:
        data = source.sst.load()
    expected = pd.date_range(config["date_start"], config["date_end"])
    if not pd.DatetimeIndex(data.time.values).equals(expected):
        raise ValueError(
            "research input does not contain exactly all configured daily dates"
        )
    geometries = {
        "iho_yellow_sea": geometry,
        "original_pilot_box": box(117, 31, 127, 39),
        "iho_interior": geometry.buffer(-config["interior_buffer_degrees"]),
    }
    if set(config["domains"]) != set(geometries):
        raise ValueError(
            "configured domains must match the three implemented definitions"
        )
    # The first available analysis defines the fixed land mask. Later values do
    # not decide whether a cell is ocean, avoiding a full-record spatial lookup.
    initial_ocean = data.isel(time=0).notnull()
    latitude_weights = np.cos(np.deg2rad(data.lat))
    full_weights = latitude_weights.broadcast_like(initial_ocean)
    series, quality, masks = {}, [], []
    for name in config["domains"]:
        mask = grid_mask(geometries[name], data.lat, data.lon) & initial_ocean
        count = int(mask.sum())
        if count == 0:
            raise ValueError(f"{name} has no ocean grid cells")
        weights = full_weights.where(mask, 0)
        fraction = (
            weights.where(data.notnull(), 0).sum(("lat", "lon")) / weights.sum()
        ).to_series()
        mean = (
            data.where(mask)
            .weighted(weights)
            .mean(("lat", "lon"))
            .where(fraction.to_xarray() >= 0.8)
            .to_series()
        )
        mean.index = expected
        mean.name = "sst_observed_celsius"
        series[name] = mean
        pd.DataFrame(
            {
                "sst_observed_celsius": mean,
                "valid_ocean_weight_fraction": fraction.values,
            },
            index=expected,
        ).rename_axis("date").to_csv(
            output_dir / f"{name}_daily.csv", date_format="%Y-%m-%d"
        )
        quality.append(
            {
                "domain": name,
                "ocean_grid_cells": count,
                "daily_records": len(mean),
                "observed_days": int(mean.notna().sum()),
                "missing_days": int(mean.isna().sum()),
                "min_valid_fraction": float(fraction.min()),
                "mask_date": str(expected[0].date()),
                "minimum_allowed_fraction": 0.8,
            }
        )
        grid = mask.to_dataframe(name="selected").reset_index()
        grid["domain"] = name
        masks.append(grid)
    pd.DataFrame(quality).to_csv(output_dir / "data_quality.csv", index=False)
    pd.concat(masks, ignore_index=True).to_csv(
        output_dir / "grid_masks.csv", index=False
    )
    _plot_domains(
        data.lat, data.lon, initial_ocean, geometries, config["domains"], output_dir
    )
    return series, {
        "domains": quality,
        "grid_shape": dict(data.sizes),
        "spatial_mask": "Marine Regions IHO polygon grid-center membership intersect first-day valid OISST cells",
        "interior_sensitivity": f"polygon eroded by {config['interior_buffer_degrees']} degrees in lon/lat; not a geodesic distance or coastline-only buffer",
        "coverage_rule": "at least 80% of the fixed domain ocean cosine-latitude weight",
    }


def _plot_domains(lat, lon, ocean, geometries, names, output_dir):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    figure, axes = plt.subplots(
        1, 3, figsize=(13, 5), constrained_layout=True, sharex=True, sharey=True
    )
    x, y = np.meshgrid(lon, lat)
    labels = {
        "iho_yellow_sea": "IHO Yellow Sea (MRGID 4303)",
        "original_pilot_box": "Original pilot rectangle",
        "iho_interior": "IHO polygon interior sensitivity",
    }
    for axis, name in zip(axes, names):
        mask = grid_mask(geometries[name], lat, lon).values & ocean.values
        axis.scatter(
            x[~ocean.values],
            y[~ocean.values],
            s=8,
            color="#c0c4c9",
            label="OISST first-day land/missing",
        )
        axis.scatter(
            x[mask], y[mask], s=9, color="#1874b6", label="Selected ocean grid centers"
        )
        simplified = geometries["iho_yellow_sea"].simplify(
            0.015, preserve_topology=True
        )
        polygons = (
            list(simplified.geoms)
            if simplified.geom_type == "MultiPolygon"
            else [simplified]
        )
        for polygon in polygons:
            coordinates = np.asarray(polygon.exterior.coords)
            axis.plot(coordinates[:, 0], coordinates[:, 1], color="#273847", lw=0.65)
        if name == "original_pilot_box":
            axis.add_patch(
                Rectangle((117, 31), 10, 8, fill=False, edgecolor="#d76e19", lw=1.3)
            )
        axis.set(
            title=labels[name], xlabel="Longitude (°E)", xlim=(117, 128), ylim=(31, 42)
        )
        axis.set_aspect(1 / np.cos(np.deg2rad(36.5)))
        axis.grid(alpha=0.15)
    axes[0].set_ylabel("Latitude (°N)")
    axes[1].legend(loc="lower center", fontsize=7)
    figure.suptitle(
        "Explicit marine definition and grid-center mask | NOAA OISST 0.25°"
    )
    figure.savefig(output_dir / "domain_map.png", dpi=150)
    plt.close(figure)
