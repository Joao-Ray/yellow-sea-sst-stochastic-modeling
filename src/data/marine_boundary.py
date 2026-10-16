"""Fetch an attributed official marine polygon and mask OISST grid centers."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlencode

import numpy as np
from shapely import covers, points
from shapely.geometry import shape
import xarray as xr

from src.data.download_oisst import build_session

WFS_ENDPOINT = "https://geo.vliz.be/geoserver/MarineRegions/wfs"


def boundary_url(mrgid: int = 4303) -> str:
    if mrgid != 4303:
        raise ValueError("this workflow validates the Yellow Sea MRGID 4303 only")
    return (
        WFS_ENDPOINT
        + "?"
        + urlencode(
            {
                "service": "WFS",
                "version": "1.0.0",
                "request": "GetFeature",
                "typeName": "MarineRegions:iho",
                "cql_filter": f"mrgid={mrgid}",
                "outputFormat": "application/json",
                "srsName": "EPSG:4326",
            }
        )
    )


def validate_boundary(document: dict):
    features = document.get("features", [])
    if document.get("type") != "FeatureCollection" or len(features) != 1:
        raise ValueError("boundary must contain exactly one feature")
    feature = features[0]
    if (
        feature.get("properties", {}).get("mrgid") != 4303
        or feature["properties"].get("name") != "Yellow Sea"
    ):
        raise ValueError("boundary identity must be Yellow Sea MRGID 4303")
    crs = document.get("crs", {}).get("properties", {}).get("name", "")
    if crs not in {
        "urn:ogc:def:crs:EPSG::4326",
        "EPSG:4326",
        "urn:ogc:def:crs:OGC:1.3:CRS84",
    }:
        raise ValueError("boundary coordinates must identify WGS84 longitude/latitude")
    geometry = shape(feature["geometry"])
    if (
        geometry.geom_type not in {"Polygon", "MultiPolygon"}
        or geometry.is_empty
        or not geometry.is_valid
    ):
        raise ValueError("boundary polygon is empty or invalid")
    west, south, east, north = geometry.bounds
    if not (
        117 < west < 119 and 32 < south < 34 and 126 < east < 129 and 40 < north < 42
    ):
        raise ValueError("unexpected Yellow Sea bounds or coordinate axis order")
    return geometry


def acquire_boundary(output_dir: Path) -> tuple[Path, dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "yellow_sea_iho.geojson"
    sidecar = path.with_suffix(".metadata.json")
    url = boundary_url()
    if path.exists():
        if not sidecar.exists():
            raise ValueError("cached boundary is missing its provenance")
        metadata = json.loads(sidecar.read_text())
        if (
            metadata.get("request_url") != url
            or metadata.get("sha256") != hashlib.sha256(path.read_bytes()).hexdigest()
        ):
            raise ValueError("boundary provenance/checksum mismatch")
        validate_boundary(json.loads(path.read_text()))
        return path, metadata
    with build_session(retries=2) as session:
        response = session.get(url, timeout=90)
        response.raise_for_status()
        raw = response.content
    document = json.loads(raw)
    geometry = validate_boundary(document)
    metadata = {
        "provider": "Flanders Marine Institute / Marine Regions",
        "product": "IHO Sea Areas, version 3 (2018), WFS iho layer",
        "mrgid": 4303,
        "name": "Yellow Sea",
        "request_url": url,
        "source_page": "https://www.marineregions.org/gazetteer.php?id=4303&p=details",
        "dataset_doi": "10.14284/323",
        "citation": "Flanders Marine Institute (2018). IHO Sea Areas, version 3.",
        "acquired_utc": datetime.now(timezone.utc).isoformat(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bounds_west_south_east_north": list(geometry.bounds),
        "axis_order": "WFS 1.0 EPSG:4326 GeoJSON, longitude/latitude",
        "mask_rule": "grid center covered by polygon; intersect first-day valid OISST cells",
        "distribution": "download from provider; boundary data not committed or redistributed",
    }
    temporary = path.with_suffix(".geojson.part")
    temporary.write_bytes(raw)
    temporary.replace(path)
    sidecar.write_text(json.dumps(metadata, indent=2) + "\n")
    return path, metadata


def grid_mask(geometry, lat: xr.DataArray, lon: xr.DataArray) -> xr.DataArray:
    if lat.ndim != 1 or lon.ndim != 1:
        raise ValueError("boundary mask requires one-dimensional lat/lon axes")
    x, y = np.meshgrid(lon.values, lat.values)
    values = covers(geometry, points(x, y))
    return xr.DataArray(values, coords={"lat": lat, "lon": lon}, dims=("lat", "lon"))
