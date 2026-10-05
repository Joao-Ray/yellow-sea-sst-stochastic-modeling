"""Audited HTTP byte-range access to original RSS AMSR2 observation files."""

import hashlib
import io
import json
import re


class HTTPRangeFile(io.RawIOBase):
    """Read-only HDF5 file object; pin identity and verify every byte range."""

    def __init__(self, url, session, block_size=131072):
        super().__init__()
        self.url, self.session, self.block_size = url, session, block_size
        self.position, self.size = 0, None
        self.blocks, self.records = {}, []
        self.identity = None
        self._block(0)

    def _block(self, number):
        if number in self.blocks:
            return self.blocks[number]
        start = number * self.block_size
        end = start + self.block_size - 1
        if self.size is not None:
            end = min(end, self.size - 1)
        headers = {"Range": f"bytes={start}-{end}", "Accept-Encoding": "identity"}
        if self.identity:
            headers["If-Match"] = self.identity
        with self.session.get(self.url, headers=headers, timeout=60) as response:
            response.raise_for_status()
            match = re.fullmatch(
                r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", "")
            )
            if response.status_code != 206 or not match:
                raise ValueError("server must return an explicit HTTP byte range")
            a, b, size = map(int, match.groups())
            data = response.content
            if a != start or b != min(end, size - 1) or len(data) != b - a + 1:
                raise ValueError("server returned the wrong byte range")
            identity = response.headers.get("ETag")
            if self.size is not None and (
                size != self.size or identity != self.identity
            ):
                raise ValueError("remote file changed during acquisition")
            self.size, self.identity = size, identity
            if not identity or identity.startswith("W/"):
                raise ValueError("range acquisition requires a strong file ETag")
            self.blocks[number] = data
            self.records.append(
                {
                    "start": a,
                    "end": b,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "etag": identity,
                    "last_modified": response.headers.get("Last-Modified"),
                }
            )
            return data

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=0):
        value = (
            offset
            if whence == 0
            else self.position + offset
            if whence == 1
            else self.size + offset
            if whence == 2
            else -1
        )
        if value < 0:
            raise ValueError("invalid seek")
        self.position = value
        return value

    def read(self, size=-1):
        if size is None or size < 0:
            size = self.size - self.position
        stop = min(self.size, self.position + size)
        result = []
        while self.position < stop:
            number, offset = divmod(self.position, self.block_size)
            block = self._block(number)
            count = min(stop - self.position, len(block) - offset)
            result.append(block[offset : offset + count])
            self.position += count
        return b"".join(result)

    def readinto(self, buffer):
        data = self.read(len(buffer))
        buffer[: len(data)] = data
        return len(data)


def readable_attributes(attributes):
    def convert(value):
        if hasattr(value, "tolist"):
            value = value.tolist()
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        if isinstance(value, list):
            return [convert(x) for x in value]
        return value

    return {
        key: convert(value)
        for key, value in attributes.items()
        if key not in ("DIMENSION_LIST", "REFERENCE_LIST")
    }


def inspect_historical_file(url):
    import h5py
    from src.data.download_oisst import build_session

    with build_session(retries=2) as session:
        with HTTPRangeFile(url, session) as stream:
            with h5py.File(stream, "r") as source:
                metadata = {
                    "attributes": readable_attributes(source.attrs),
                    "variables": {
                        name: {
                            "shape": value.shape,
                            "chunks": value.chunks,
                            "attributes": readable_attributes(value.attrs),
                        }
                        for name, value in source.items()
                    },
                }
            print(json.dumps(metadata, indent=2))
            print(
                "bytes acquired",
                sum(len(x) for x in stream.blocks.values()),
                "global bytes",
                stream.size,
            )


def acquire_day(day, region, output_dir):
    """Acquire original SST/time/masks; keep range checksums and cropped data."""
    from datetime import datetime, timezone
    from pathlib import Path
    import h5py
    import numpy as np
    import requests
    from src.data.download_oisst import build_session

    stamp = day.isoformat()
    url = f"https://data.remss.com/amsr2/ocean/L3/v08.2/daily/{day.year}/RSS_AMSR2_ocean_L3_daily_{stamp}_v08.2.nc"
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"amsr2-{stamp}.npz"
    sidecar = target.with_suffix(".json")
    if target.exists():
        if not sidecar.exists():
            raise ValueError("AMSR2 cache is missing provenance")
        saved = json.loads(sidecar.read_text())
        if (
            saved.get("source_url") != url
            or saved.get("region") != region
            or saved.get("subset_sha256")
            != hashlib.sha256(target.read_bytes()).hexdigest()
        ):
            raise ValueError("AMSR2 cache failed provenance/checksum validation")
        return str(target)
    partial = target.with_suffix(".part.npz")
    try:
        with build_session(retries=2) as session:
            with HTTPRangeFile(url, session, block_size=524288) as stream:
                with h5py.File(stream, "r") as source:
                    attributes = readable_attributes(source.attrs)
                    if (
                        attributes.get("sensor") != "AMSR2"
                        or attributes.get("version") != "8.2"
                        or attributes.get("platform") != "GCOM-W1"
                        or attributes.get("time_coverage_start") != stamp + "T00:00:00Z"
                    ):
                        raise ValueError("AMSR2 identity or UTC date does not match")
                    lat, lon = source["lat"][:], source["lon"][:]
                    yi = np.flatnonzero(
                        (lat >= region["lat_min"]) & (lat <= region["lat_max"])
                    )
                    xi = np.flatnonzero(
                        (lon >= region["lon_min"]) & (lon <= region["lon_max"])
                    )
                    if (
                        len(yi) == 0
                        or len(xi) == 0
                        or not np.array_equal(source["pass"][:], [1, 2])
                    ):
                        raise ValueError("AMSR2 grid/pass definition is incompatible")
                    y, x = slice(yi[0], yi[-1] + 1), slice(xi[0], xi[-1] + 1)
                    names = [
                        "SST",
                        "time",
                        "land_mask",
                        "coast_mask",
                        "sea_ice_mask",
                        "noobs_mask",
                    ]
                    if (
                        readable_attributes(source["SST"].attrs).get("units")
                        != "degrees_Celsius"
                        or readable_attributes(source["time"].attrs).get("units")
                        != "hours since " + stamp + "T00:00:00Z"
                    ):
                        raise ValueError("AMSR2 units/date origin are incompatible")
                    values = {name: source[name][:, y, x] for name in names}
                    values.update(lat=lat[y], lon=lon[x])
                    variable_metadata = {
                        name: readable_attributes(source[name].attrs) for name in names
                    }
                np.savez_compressed(partial, **values)
                metadata = {
                    "provider": "Remote Sensing Systems",
                    "source_url": url,
                    "region": region,
                    "subset_sha256": hashlib.sha256(partial.read_bytes()).hexdigest(),
                    "source_global_bytes": stream.size,
                    "source_etag": stream.identity,
                    "source_byte_ranges": stream.records,
                    "acquired_bytes": sum(len(v) for v in stream.blocks.values()),
                    "acquired_utc": datetime.now(timezone.utc).isoformat(),
                    "source_attributes": attributes,
                    "variable_attributes": variable_metadata,
                    "processing": "exact grid crop only; missing/fill values and all masks preserved; original global file not fully downloaded or fully hashed",
                }
        target_tmp = sidecar.with_suffix(".part.json")
        target_tmp.write_text(json.dumps(metadata, indent=2) + "\n")
        partial.replace(target)
        target_tmp.replace(sidecar)
        return str(target)
    except requests.HTTPError as exc:
        if exc.response.status_code != 404:
            raise
        (directory / f"missing-{stamp}.json").write_text(
            json.dumps(
                {
                    "date": stamp,
                    "source_url": url,
                    "status": 404,
                    "checked_utc": datetime.now(timezone.utc).isoformat(),
                }
            )
            + "\n"
        )
        return None
    finally:
        partial.unlink(missing_ok=True)
        sidecar.with_suffix(".part.json").unlink(missing_ok=True)


def audit_decode(day, raw_dir, output_path):
    """Post-score full-file/second-backend check; never alters scoring support."""
    from datetime import datetime, timezone
    from pathlib import Path
    import netCDF4
    import numpy as np
    from src.data.download_oisst import build_session

    directory, output_path = Path(raw_dir), Path(output_path)
    stamp = day.isoformat()
    cropped_path = directory / f"amsr2-{stamp}.npz"
    metadata = json.loads(cropped_path.with_suffix(".json").read_text())
    if (
        hashlib.sha256(cropped_path.read_bytes()).hexdigest()
        != metadata["subset_sha256"]
    ):
        raise ValueError("audit crop failed its original checksum")
    target = directory / f"source-audit-{stamp}.nc"
    previous = json.loads(output_path.read_text()) if output_path.exists() else {}
    if target.exists():
        if (
            previous.get("source_etag") != metadata["source_etag"]
            or previous.get("complete_global_sha256")
            != hashlib.sha256(target.read_bytes()).hexdigest()
        ):
            raise ValueError("full audit cache failed identity/checksum verification")
    else:
        with build_session(retries=2) as session:
            response = session.get(
                metadata["source_url"],
                headers={
                    "Accept-Encoding": "identity",
                    "If-Match": metadata["source_etag"],
                },
                timeout=120,
            )
            response.raise_for_status()
            if (
                response.headers.get("ETag") != metadata["source_etag"]
                or len(response.content) != metadata["source_global_bytes"]
            ):
                raise ValueError("audit source differs from the scored original")
            target.write_bytes(response.content)
    with netCDF4.Dataset(target) as source, np.load(cropped_path) as cropped:
        lat, lon = source["lat"][:], source["lon"][:]
        y = np.flatnonzero(np.isin(lat, cropped["lat"]))
        x = np.flatnonzero(np.isin(lon, cropped["lon"]))
        variables = {}
        for name in [
            "SST",
            "time",
            "land_mask",
            "coast_mask",
            "sea_ice_mask",
            "noobs_mask",
        ]:
            values = np.ma.filled(
                source[name][:, y[0] : y[-1] + 1, x[0] : x[-1] + 1], -999
            )
            np.testing.assert_array_equal(values, cropped[name])
            variables[name] = {
                "exactly_matches_range_h5py_crop": True,
                "dtype": str(values.dtype),
            }
        pass_attributes = readable_attributes(
            {a: source["pass"].getncattr(a) for a in source["pass"].ncattrs()}
        )
    audit = {
        "date": stamp,
        "purpose": "Post-score decoding audit prompted by large same-day product differences; no quality rule, model, score or selection changed",
        "audited_utc": datetime.now(timezone.utc).isoformat(),
        "source_url": metadata["source_url"],
        "source_etag": metadata["source_etag"],
        "global_bytes": target.stat().st_size,
        "complete_global_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "independent_backend": "netCDF4 with automatic masking/scaling, compared to original h5py byte-range crop",
        "variables": variables,
        "pass_attributes": pass_attributes,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
    return audit


if __name__ == "__main__":
    import argparse
    from datetime import date
    from pathlib import Path

    parser = argparse.ArgumentParser(
        description="Audit original AMSR2 decoding with a second backend"
    )
    parser.add_argument("--audit-date", type=date.fromisoformat, required=True)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw/independent"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/processed/independent/source_audit.json"),
    )
    args = parser.parse_args()
    print(
        json.dumps(
            audit_decode(args.audit_date, args.raw_dir, args.output), ensure_ascii=False
        )
    )
