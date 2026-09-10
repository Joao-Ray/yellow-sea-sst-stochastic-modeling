"""One-day persistence baseline for the regional SST-anomaly series."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from src.evaluation.metrics import regression_metrics

RANDOM_SEED = 42


def persistence_predictions(anomaly: pd.Series) -> pd.Series:
    """Predict each day's anomaly using the preceding calendar day's anomaly."""
    if not isinstance(anomaly.index, pd.DatetimeIndex):
        raise TypeError("anomaly index must be a DatetimeIndex")
    if anomaly.index.has_duplicates:
        raise ValueError("anomaly index contains duplicate dates")
    daily = anomaly.sort_index().asfreq("D")
    prediction = daily.shift(1)
    prediction.name = "predicted_anomaly_celsius"
    return prediction


def evaluate_persistence(
    anomaly: pd.Series, *, test_fraction: float = 0.2
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Evaluate persistence on the final chronological fraction of the record."""
    if not 0 < test_fraction < 1:
        raise ValueError("test_fraction must be between 0 and 1")

    observed = anomaly.sort_index().asfreq("D").rename("observed_anomaly_celsius")
    predicted = persistence_predictions(observed)
    paired = pd.concat([observed, predicted], axis=1)
    if len(paired) < 2:
        raise ValueError("at least two daily rows are required")

    split_position = max(1, int(len(paired) * (1 - test_fraction)))
    test = paired.iloc[split_position:].dropna().copy()
    if test.empty:
        raise ValueError("the chronological test segment has no valid pairs")
    test["error_celsius"] = (
        test["predicted_anomaly_celsius"] - test["observed_anomaly_celsius"]
    )

    metrics = regression_metrics(
        test["observed_anomaly_celsius"].to_numpy(),
        test["predicted_anomaly_celsius"].to_numpy(),
    )
    metadata: dict[str, object] = {
        "baseline": "one-day persistence",
        "target": "sst anomaly (degrees Celsius)",
        "split_method": "final chronological fraction",
        "test_fraction": test_fraction,
        "test_start": test.index.min().date().isoformat(),
        "test_end": test.index.max().date().isoformat(),
        "random_seed": RANDOM_SEED,
        "metrics": metrics,
    }
    test.index.name = "date"
    return test, metadata


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-file", required=True, type=Path)
    parser.add_argument("--predictions-file", required=True, type=Path)
    parser.add_argument("--metrics-file", required=True, type=Path)
    parser.add_argument("--test-fraction", type=float, default=0.2)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    table = pd.read_csv(args.input_file, parse_dates=["date"]).set_index("date")
    if "anomaly_celsius" not in table:
        raise ValueError("input CSV must contain an 'anomaly_celsius' column")
    predictions, metadata = evaluate_persistence(
        table["anomaly_celsius"], test_fraction=args.test_fraction
    )
    args.predictions_file.parent.mkdir(parents=True, exist_ok=True)
    args.metrics_file.parent.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(args.predictions_file, date_format="%Y-%m-%d")
    args.metrics_file.write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
