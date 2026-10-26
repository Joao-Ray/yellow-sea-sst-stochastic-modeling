"""Assemble reviewed manuscript/results without fitting or changing forecasts."""

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

import pandas as pd

from src.confirmation import verify_inputs
from src.evaluation.publication_report import write_documents
from src.insitu import protocol
from src.models.spatial_benchmarks import load_spatial
from src.validation import sha256


def hashes(root):
    return {
        str(p.relative_to(root)): sha256(p)
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.name != "checksums.json" and ".matplotlib" not in p.parts
    }


def main():
    verify_inputs()
    protocol()
    original = Path("data/processed/publication")
    reviewed = Path("paper/submission")
    output = Path("data/processed/submission")
    output.mkdir(parents=True, exist_ok=True)
    for stage, names in {
        "confirmation": [
            "metrics.csv",
            "annual_metrics.csv",
            "annual_skill.csv",
            "seasonal_metrics.csv",
            "seasonal_skill.csv",
            "primary_inference.csv",
            "coverage.csv",
            "monthly_coverage.csv",
            "loss_decomposition.csv",
            "skill_transfer.csv",
            "provenance.json",
            "evaluation_audit.json",
            "report_en.md",
            "benchmark_selection.csv",
            "benchmark_parameters.json",
            "chronology_audit.json",
        ],
        "insitu": [
            "metrics.csv",
            "annual_metrics.csv",
            "coverage.csv",
            "platform_support.csv",
            "provenance.json",
            "evaluation_audit.json",
            "extraction_audit.json",
            "compatibility_audit.json",
            "chronology_audit.json",
            "report_en.md",
        ],
        "anomaly_transfer": [
            "metrics.csv",
            "annual_metrics.csv",
            "seasonal_metrics.csv",
            "selection.csv",
            "parameters.json",
            "climatology_parameters.json",
            "descriptive_intervals.csv",
            "decay_reference_intervals.csv",
            "benchmark_metrics.csv",
            "benchmark_annual_metrics.csv",
            "benchmark_audit.json",
            "evaluation_audit.json",
            "external_metrics.csv",
            "external_annual_metrics.csv",
            "external_audit.json",
            "external_benchmark_metrics.csv",
            "external_benchmark_annual_metrics.csv",
            "external_reference_audit.json",
            "external_decay_intervals.csv",
            "reconstruction_audit.json",
            "transfer_summary.csv",
            "report_en.md",
        ],
        "destination_validation": [
            "satellite_metrics.csv",
            "satellite_annual_metrics.csv",
            "satellite_seasonal_metrics.csv",
            "satellite_coverage.csv",
            "buoy_metrics.csv",
            "buoy_annual_metrics.csv",
            "buoy_seasonal_metrics.csv",
            "buoy_coverage.csv",
            "buoy_platform_support.csv",
            "primary_inference.csv",
            "evaluation_audit.json",
            "independent_audit.json",
            "report_en.md",
        ],
        "process_transfer": [
            "metrics.csv",
            "annual_metrics.csv",
            "seasonal_metrics.csv",
            "selection.csv",
            "parameters.json",
            "forcing_inference.csv",
            "skill.csv",
            "transfer_summary.csv",
            "provenance.json",
            "sst_provenance.json",
            "evaluation_audit.json",
            "report_en.md",
            "external_metrics.csv",
            "external_annual_metrics.csv",
            "external_audit.json",
            "alignment_metrics.csv",
            "alignment_annual_metrics.csv",
            "alignment_audit.json",
            "reconstruction_audit.json",
        ],
    }.items():
        source = Path("data/processed") / stage
        target = Path("paper") / stage / "results"
        target.mkdir(parents=True, exist_ok=True)
        for name in names:
            shutil.copy2(source / name, target / name)
        for figure in source.iterdir():
            if figure.suffix in [".png", ".svg"]:
                shutil.copy2(figure, target / figure.name)
                shutil.copy2(figure, reviewed / figure.name)
        (target / "checksums.json").write_text(
            json.dumps(hashes(target), indent=2) + "\n"
        )
    # Preserve the original model/results and figures; regenerate only documents.
    original_hashes = json.loads((original / "checksums.json").read_text())
    reconstruction = Path(
        "data/processed/confirmation_rebuild/reconstruction_audit.json"
    )
    if not json.loads(reconstruction.read_text())["all_frozen_output_bytes_reproduced"]:
        raise ValueError("frozen reconstruction audit did not reproduce every file")
    shutil.copy2(
        reconstruction, Path("paper/confirmation/results/reconstruction_audit.json")
    )
    for name, digest in original_hashes.items():
        if sha256(original / name) != digest:
            raise ValueError("original publication output changed: " + name)
    for figure in reviewed.iterdir():
        if figure.suffix in [".png", ".svg"]:
            shutil.copy2(figure, output / figure.name)
    tables = {p.stem: pd.read_csv(p) for p in original.glob("*.csv")}
    spatial = load_spatial(reviewed / "results/spatial_parameters.json")
    config = json.loads(Path("configs/publication.json").read_text())
    write_documents(tables, tables["spatial_selection"], spatial, config, output)
    for name in ["manuscript_en.md", "supplement_en.md"]:
        shutil.copy2(output / name, reviewed / name)
    record = {
        "assembled_utc": datetime.now(timezone.utc).isoformat(),
        "original_temporal_protocol_sha256": sha256(
            "paper/validation/frozen_protocol.json"
        ),
        "original_instrument_protocol_sha256": sha256(
            "paper/independent/frozen_protocol.json"
        ),
        "multiyear_protocol_sha256": sha256("paper/confirmation/frozen_protocol.json"),
        "insitu_protocol_sha256": sha256("paper/insitu/frozen_protocol.json"),
        "assembly_software_sha256": sha256(__file__),
        "document_software_sha256": sha256("src/evaluation/manuscript_extension.py"),
        "process_document_software_sha256": sha256(
            "src/evaluation/process_transfer_report.py"
        ),
        "anomaly_document_software_sha256": sha256(
            "src/evaluation/anomaly_transfer_report.py"
        ),
        "destination_document_software_sha256": sha256(
            "src/evaluation/destination_report.py"
        ),
        "scope": "Documents assembled from completed locked evaluations; no fitting, tuning or recalibration. Original primary records preserved.",
    }
    (reviewed / "assembly_audit.json").write_text(json.dumps(record, indent=2) + "\n")
    for stage in ["confirmation", "insitu"]:
        stage_results = Path("paper") / stage / "results"
        (stage_results / "checksums.json").write_text(
            json.dumps(hashes(stage_results), indent=2) + "\n"
        )
    (reviewed / "checksums.json").write_text(
        json.dumps(hashes(reviewed), indent=2) + "\n"
    )
    (output / "checksums.json").write_text(json.dumps(hashes(output), indent=2) + "\n")
    print(
        "Integrated English manuscript and supplementary information:", output.resolve()
    )


if __name__ == "__main__":
    main()
