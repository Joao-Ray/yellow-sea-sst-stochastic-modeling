"""Train-only seasonal preprocessing and fixed-parameter rolling forecasts."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.data.preprocess import calculate_climatology
from src.evaluation.metrics import regression_metrics
from src.models.ar1 import fit_ar1
from src.models.autoregression import select_ar_order


@dataclass
class ExperimentResult:
    anomalies: pd.DataFrame
    predictions: pd.DataFrame
    metrics: pd.DataFrame
    protocol: dict[str, object]
    parameters: dict[str, object]


def observed_sst(table: pd.DataFrame) -> pd.Series:
    """Recover raw observations, excluding any values filled using future days."""
    if not isinstance(table.index, pd.DatetimeIndex):
        raise TypeError("input must have a DatetimeIndex")
    if table.empty or table.index.has_duplicates:
        raise ValueError("input must be non-empty with unique dates")
    if table.index.tz is not None or not table.index.equals(table.index.normalize()):
        raise ValueError("input dates must be timezone-free daily midnight dates")
    column = (
        "sst_observed_celsius" if "sst_observed_celsius" in table else "sst_celsius"
    )
    if column not in table:
        raise ValueError("input needs sst_observed_celsius or sst_celsius")
    series = table[column].astype(float).copy()
    if "is_interpolated" in table:
        flags = table["is_interpolated"]
        true_values = [True, 1, "True", "true", "1"]
        false_values = [False, 0, "False", "false", "0"]
        if not flags.isin(true_values + false_values).all():
            raise ValueError("is_interpolated must contain boolean values")
        series = series.mask(flags.isin(true_values))
    return series.replace([np.inf, -np.inf], np.nan).sort_index().asfreq("D")


def run_experiment(
    table: pd.DataFrame,
    *,
    train_end: str,
    validation_end: str,
    horizons: tuple[int, ...] = (1, 7, 30),
    climatology: str = "dayofyear",
    data_kind: str = "observed",
    ar_candidates: tuple[int, ...] = (),
    selection_horizon: int = 7,
) -> ExperimentResult:
    """Fit once on training data and score validation/test on common support.

    For each target date d and horizon h, the forecast uses the actually observed
    anomaly at d-h. Parameters and the seasonal cycle remain frozen. There is
    no interpolation, tuning, test refit, or use of intermediate future values.
    """
    if data_kind not in {"observed", "synthetic"}:
        raise ValueError("data_kind must be observed or synthetic")
    if (
        not horizons
        or len(set(horizons)) != len(horizons)
        or any(not isinstance(h, int) or isinstance(h, bool) or h < 1 for h in horizons)
    ):
        raise ValueError("horizons must be unique positive integers")
    sst = observed_sst(table)
    train_boundary, validation_boundary = (
        pd.Timestamp(train_end),
        pd.Timestamp(validation_end),
    )
    if any(
        t.tz is not None or t != t.normalize()
        for t in (train_boundary, validation_boundary)
    ):
        raise ValueError("split dates must be timezone-free daily dates")
    if not sst.index.min() <= train_boundary < validation_boundary < sst.index.max():
        raise ValueError(
            "split dates must leave non-empty chronological train/validation/test periods"
        )
    mapped, cycle = calculate_climatology(
        sst,
        frequency=climatology,
        reference_start=str(sst.index.min().date()),
        reference_end=str(train_boundary.date()),
    )
    if mapped.isna().any():
        raise ValueError(
            "training climatology does not cover every calendar bin; use more training years"
        )
    anomaly = (sst - mapped).rename("anomaly_celsius")
    model = fit_ar1(anomaly.loc[:train_boundary])
    selected_ar = None
    selection_scores = []
    if ar_candidates:
        selected_ar, selection_scores = select_ar_order(
            anomaly,
            train_end=train_boundary,
            validation_end=validation_boundary,
            orders=ar_candidates,
            horizon=selection_horizon,
        )
    splits = pd.Series("train", index=sst.index)
    splits.loc[splits.index > train_boundary] = "validation"
    splits.loc[splits.index > validation_boundary] = "test"
    predictions: list[pd.DataFrame] = []
    coverage: list[dict[str, object]] = []
    for horizon in sorted(horizons):
        origin = anomaly.shift(horizon)
        means = {
            "climatology": pd.Series(0.0, index=sst.index),
            "persistence": origin,
            "ar1": model.forecast(origin, horizon),
        }
        if selected_ar is not None and selected_ar.order > 1:
            means[f"ar{selected_ar.order}"] = selected_ar.forecast(anomaly, horizon)
        support = anomaly.notna() & origin.notna()
        for predicted in means.values():
            support &= np.isfinite(predicted)
        for split in ("validation", "test"):
            selected = support & splits.eq(split)
            if not selected.any():
                raise ValueError(f"no valid {split} forecasts at horizon {horizon}")
            coverage.append(
                {
                    "split": split,
                    "horizon_days": horizon,
                    "candidate_days": int(splits.eq(split).sum()),
                    "scored_days": int(selected.sum()),
                }
            )
            for name, predicted in means.items():
                frame = pd.DataFrame(
                    {
                        "date": sst.index[selected],
                        "origin_date": sst.index[selected] - pd.Timedelta(days=horizon),
                        "split": split,
                        "horizon_days": horizon,
                        "model": name,
                        "observed_anomaly_celsius": anomaly.loc[selected].to_numpy(),
                        "predicted_anomaly_celsius": predicted.loc[selected].to_numpy(),
                    }
                )
                radius = (
                    model.interval_radius(horizon)
                    if name == "ar1"
                    else selected_ar.interval_radius(horizon)
                    if name.startswith("ar")
                    else np.nan
                )
                frame["lower_95_celsius"] = frame["predicted_anomaly_celsius"] - radius
                frame["upper_95_celsius"] = frame["predicted_anomaly_celsius"] + radius
                predictions.append(frame)
    forecasts = pd.concat(predictions, ignore_index=True)
    rows = []
    for (split, horizon, name), group in forecasts.groupby(
        ["split", "horizon_days", "model"], sort=True
    ):
        metrics = regression_metrics(
            group["observed_anomaly_celsius"], group["predicted_anomaly_celsius"]
        )
        observed = group["observed_anomaly_celsius"]
        interval_coverage = (
            float(
                observed.between(
                    group["lower_95_celsius"], group["upper_95_celsius"]
                ).mean()
            )
            if name.startswith("ar")
            else np.nan
        )
        rows.append(
            {
                "split": split,
                "horizon_days": horizon,
                "model": name,
                **metrics,
                "coverage_95": interval_coverage,
            }
        )
    scores = pd.DataFrame(rows)
    baseline = scores[scores["model"].eq("persistence")].set_index(
        ["split", "horizon_days"]
    )["rmse"]
    scores["rmse_skill_vs_persistence"] = [
        1 - row.rmse / baseline.loc[(row.split, row.horizon_days)]
        if baseline.loc[(row.split, row.horizon_days)] > 0
        else np.nan
        for row in scores.itertuples()
    ]
    anomalies = pd.DataFrame(
        {
            "sst_observed_celsius": sst,
            "climatology_celsius": mapped,
            "anomaly_celsius": anomaly,
            "split": splits,
        }
    )
    anomalies.index.name = "date"
    protocol = {
        "data_kind": data_kind,
        "train_start": str(sst.index.min().date()),
        "train_end": str(train_boundary.date()),
        "validation_end": str(validation_boundary.date()),
        "test_end": str(sst.index.max().date()),
        "horizons_days": sorted(horizons),
        "climatology": climatology,
        "climatology_fit": "training observations only",
        "missing_policy": "exclude; never interpolate training, origins, or targets",
        "forecast_protocol": "rolling observed origins; frozen training parameters; no intermediate observations",
        "model_selection": (
            f"AR order selected on validation {selection_horizon}-day RMSE; training fits frozen; selected-model validation scores are selection-biased"
            if selected_ar is not None
            else "none; validation and test are reported separately"
        ),
        "ar_selection_scores": selection_scores,
        "coverage": coverage,
        "observed_days": int(sst.notna().sum()),
        "missing_days": int(sst.isna().sum()),
        "interval_assumptions": "Gaussian autoregressive innovations; fitted parameters treated as known; no parameter or climatology uncertainty",
        "ou_interpretation": "exact daily OU transition equals AR(1); not a separate comparison model",
        "spatial_scope": "Input region must be checked in source metadata; default preprocessing is a bounding-box ocean-cell average, not an exact Yellow Sea boundary",
    }
    return ExperimentResult(
        anomalies,
        forecasts,
        scores,
        protocol,
        {
            "ar1": model.to_dict(),
            "climatology_bins": len(cycle),
            "selected_ar": selected_ar.to_dict() if selected_ar is not None else None,
        },
    )


def write_experiment(result: ExperimentResult, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    result.anomalies.to_csv(output_dir / "anomalies.csv", date_format="%Y-%m-%d")
    result.predictions.to_csv(
        output_dir / "predictions.csv", index=False, date_format="%Y-%m-%d"
    )
    result.metrics.to_csv(output_dir / "metrics.csv", index=False)
    for name, value in (
        ("protocol", result.protocol),
        ("parameters", result.parameters),
    ):
        (output_dir / f"{name}.json").write_text(
            json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
    from src.evaluation.report import write_report

    write_report(result, output_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--train-end", required=True)
    parser.add_argument("--validation-end", required=True)
    parser.add_argument("--horizons", type=int, nargs="+", default=[1, 7, 30])
    parser.add_argument("--ar-candidates", type=int, nargs="*", default=[])
    parser.add_argument("--selection-horizon", type=int, default=7)
    parser.add_argument(
        "--climatology", choices=["dayofyear", "month"], default="dayofyear"
    )
    parser.add_argument(
        "--data-kind", choices=["observed", "synthetic"], default="observed"
    )
    args = parser.parse_args()
    table = pd.read_csv(args.input_file, parse_dates=["date"]).set_index("date")
    result = run_experiment(
        table,
        train_end=args.train_end,
        validation_end=args.validation_end,
        horizons=tuple(args.horizons),
        climatology=args.climatology,
        data_kind=args.data_kind,
        ar_candidates=tuple(args.ar_candidates),
        selection_horizon=args.selection_horizon,
    )
    result.protocol["input_file"] = str(args.input_file)
    result.protocol["input_sha256"] = hashlib.sha256(
        args.input_file.read_bytes()
    ).hexdigest()
    sidecar = args.input_file.with_suffix(".metadata.json")
    if sidecar.exists():
        result.protocol["preprocessing_metadata"] = json.loads(
            sidecar.read_text(encoding="utf-8")
        )
    write_experiment(result, args.output_dir)
    print(result.metrics.to_string(index=False))
    print(f"Wrote reproducible outputs to {args.output_dir}")


if __name__ == "__main__":
    main()
