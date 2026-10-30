"""Reconstruct frozen forecasts in a separate directory and verify their hashes."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
from importlib.metadata import version
import shutil

from src import confirmation
from src.validation import sha256


def rebuild(destination, install_exact=False):
    destination = Path(destination)
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("reconstruction directory must be new or empty")
    original_output, original_frozen = confirmation.OUTPUT, confirmation.FROZEN
    frozen = json.loads(original_frozen.read_text())
    # Require the publicly locked fitting code, not an outcome-adjusted variant.
    for path, digest in frozen["software_sha256"].items():
        if sha256(path) != digest:
            raise ValueError("locked fitting software changed: " + path)
    for path, digest in frozen["input_sha256"].items():
        if not Path(path).is_relative_to(original_output) and sha256(path) != digest:
            raise ValueError("upstream fitting input differs: " + path)
    destination.mkdir(parents=True, exist_ok=True)
    try:
        confirmation.OUTPUT = destination
        confirmation.FROZEN = destination / "replication_record.json"
        confirmation.prepare()
    finally:
        confirmation.OUTPUT, confirmation.FROZEN = original_output, original_frozen
    generated = json.loads((destination / "replication_record.json").read_text())
    generated.update(
        replication_only=True,
        external_targets_previously_viewed=True,
        scope="Post-outcome reconstruction of the original fixed training/selection calculation; not a new prospective lock. Original protocol and archived forecast bytes are unchanged.",
    )
    (destination / "replication_record.json").write_text(
        json.dumps(generated, indent=2) + "\n"
    )
    rows = {}
    for path, expected in frozen["input_sha256"].items():
        if Path(path).is_relative_to(original_output):
            name = Path(path).name
            actual = sha256(destination / name)
            rows[name] = {
                "expected_sha256": expected,
                "reconstructed_sha256": actual,
                "exactly_reproduced": expected == actual,
            }
    exact = all(row["exactly_reproduced"] for row in rows.values())
    audit = {
        "verified_utc": datetime.now(timezone.utc).isoformat(),
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            **{name: version(name) for name in ["numpy", "scikit-learn", "joblib"]},
        },
        "original_protocol_sha256": sha256(original_frozen),
        "files": rows,
        "all_frozen_output_bytes_reproduced": exact,
        "scope": "Independent rerun of the locked fitting code with unchanged upstream inputs; external targets are not used for fitting or selection. No refitting of the archived model or replacement of original results.",
    }
    (destination / "reconstruction_audit.json").write_text(
        json.dumps(audit, indent=2) + "\n"
    )
    if install_exact:
        if not exact:
            raise ValueError("cannot install reconstruction: frozen byte hashes differ")
        original_output.mkdir(parents=True, exist_ok=True)
        for name in rows:
            target = original_output / name
            if target.exists():
                if sha256(target) != rows[name]["expected_sha256"]:
                    raise ValueError(
                        "existing archive differs; it will not be overwritten"
                    )
            else:
                shutil.copy2(destination / name, target)
    print(json.dumps(audit, indent=2))
    return audit


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=Path("data/processed/confirmation_rebuild")
    )
    parser.add_argument("--install-exact", action="store_true")
    args = parser.parse_args()
    rebuild(args.output_dir, args.install_exact)
