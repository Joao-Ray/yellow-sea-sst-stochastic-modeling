"""Provenance-preserving geographic subsets of NOAA iQuam point records."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np

from src.data.download_amsr2 import HTTPRangeFile, readable_attributes
from src.data.download_oisst import build_session


def attribute(value, name):
    result = readable_attributes(value.attrs)[name]
    return result[0] if isinstance(result, list) else result


def acquire_month(stamp, url, region, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"iquam-{stamp}.npz"
    sidecar = target.with_suffix(".json")
    if target.exists():
        saved = json.loads(sidecar.read_text())
        if (
            saved["source_url"] != url
            or saved["region"] != region
            or saved["subset_sha256"] != hashlib.sha256(target.read_bytes()).hexdigest()
        ):
            raise ValueError("iQuam cache provenance changed")
        return str(target)
    partial = target.with_suffix(".part.npz")
    side_partial = sidecar.with_suffix(".part.json")
    try:
        with (
            build_session(retries=2) as session,
            HTTPRangeFile(url, session, block_size=1048576) as stream,
        ):
            with h5py.File(stream, "r") as source:
                if (
                    attribute(source, "product_version") != "V2.10"
                    or not attribute(source, "time_coverage_start").startswith(stamp)
                    or attribute(source["sst"], "units") != "kelvin"
                    or attribute(source["time"], "units") != "seconds"
                    or attribute(source["time"], "comment")
                    != "seconds since 1981-01-01 00:00:00"
                ):
                    raise ValueError("iQuam identity, units or UTC origin differ")
                lat, lon = source["lat"][:], source["lon"][:]
                normalized_lon = (lon.astype(float) + 180) % 360 - 180
                positions = np.flatnonzero(
                    np.isfinite(lat)
                    & np.isfinite(lon)
                    & (lat >= region["lat_min"])
                    & (lat <= region["lat_max"])
                    & (normalized_lon >= region["lon_min"])
                    & (normalized_lon <= region["lon_max"])
                )
                names = [
                    "lat",
                    "lon",
                    "time",
                    "sst",
                    "quality_level",
                    "platform_type",
                    "platform_id",
                    "iquam_flags",
                    "sst_flags",
                ]
                # Slice per HDF5 chunk; avoid quadratic fancy-index selection on large arrays.
                values = {}
                for name in names:
                    chunks = source[name].chunks
                    if chunks is None or len(chunks) != 1:
                        raise ValueError("iQuam point storage layout changed")
                    size = chunks[0]
                    parts = []
                    for chunk in np.unique(positions // size):
                        start, stop = (
                            int(chunk * size),
                            min(int((chunk + 1) * size), len(lat)),
                        )
                        indices = (
                            positions[(positions >= start) & (positions < stop)] - start
                        )
                        parts.append(source[name][start:stop][indices])
                    values[name] = (
                        np.concatenate(parts)
                        if parts
                        else np.array([], dtype=source[name].dtype)
                    )
                    if name == "platform_id":
                        values[name] = np.asarray(
                            [
                                v.decode("utf-8") if isinstance(v, bytes) else str(v)
                                for v in values[name]
                            ],
                            dtype="U64",
                        )
                values["source_index"] = positions
                attributes = readable_attributes(source.attrs)
                variables = {
                    name: readable_attributes(source[name].attrs) for name in names
                }
            np.savez_compressed(partial, **values)
            metadata = {
                "provider": "NOAA/NESDIS/STAR",
                "source_url": url,
                "region": region,
                "source_global_bytes": stream.size,
                "source_etag": stream.identity,
                "source_byte_ranges": stream.records,
                "acquired_bytes": sum(map(len, stream.blocks.values())),
                "acquired_utc": datetime.now(timezone.utc).isoformat(),
                "subset_sha256": hashlib.sha256(partial.read_bytes()).hexdigest(),
                "source_attributes": attributes,
                "variable_attributes": variables,
                "global_records": len(lat),
                "subset_records": len(positions),
                "processing": "exact geographic point subset; original units, times, flags retained; IDs decoded as UTF-8; no SST quality filtering, correction or interpolation; global file not fully hashed",
            }
        side_partial.write_text(json.dumps(metadata, indent=2) + "\n")
        partial.replace(target)
        side_partial.replace(sidecar)
        return str(target)
    finally:
        partial.unlink(missing_ok=True)
        side_partial.unlink(missing_ok=True)
