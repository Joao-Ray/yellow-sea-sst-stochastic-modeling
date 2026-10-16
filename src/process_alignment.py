"""Post-outcome descriptive location/scale transfer reference; no coefficient refit.

Added after inspecting raw transfer failures. Destination 2010–2019 histories
calibrate feature location/scale and increment location/scale. This is not the
original unchanged-parameter experiment and has no additional significance test.
"""

from datetime import datetime, timezone
import json

import joblib
import numpy as np
import pandas as pd

from src.models.process_transfer import feature_matrix
from src.process_transfer import OUTPUT, load_config
from src.validation import sha256


def increment_moments(features, origin, target, train_end):
    mask = (
        (target.index <= pd.Timestamp(train_end))
        & np.isfinite(features.to_numpy(float)).all(axis=1)
        & np.isfinite(origin)
        & np.isfinite(target)
    )
    delta = (target - origin).loc[mask].to_numpy(float)
    if len(delta) < 730 or np.std(delta) <= 1e-12:
        raise ValueError("nondegenerate training increments required")
    return float(np.mean(delta)), float(np.std(delta)), int(len(delta))


def aligned_prediction(
    source_model,
    local_training_scaler,
    features,
    origin,
    source_moments,
    destination_moments,
):
    if (
        tuple(features.columns) != source_model.columns
        or source_model.columns != local_training_scaler.columns
    ):
        raise ValueError("shared ordered feature definitions required")
    z = (
        features.to_numpy(float) - local_training_scaler.mean
    ) / local_training_scaler.scale
    valid = np.isfinite(z).all(axis=1) & np.isfinite(origin)
    delta = source_model.fitted.predict(z[valid])
    src_mean, src_std, _ = source_moments
    dst_mean, dst_std, _ = destination_moments
    result = pd.Series(np.nan, index=features.index)
    result.loc[valid] = (
        origin.loc[valid] + dst_mean + dst_std * (delta - src_mean) / src_std
    )
    return result


def main():
    cfg = load_config()
    archive = OUTPUT / "models.joblib"
    before = sha256(archive)
    models = joblib.load(archive)
    sst = pd.read_csv(OUTPUT / "regional_sst.csv", index_col="date", parse_dates=True)
    forcing = {
        d: pd.read_csv(OUTPUT / f"{d}_forcing.csv", index_col="date", parse_dates=True)
        for d in ["yellow_bohai", "northern_ecs"]
    }
    predictions, parameters = [], {}
    for group in cfg["feature_groups"]:
        end = cfg["date_end"] if group == "sst" else cfg["forcing_end"]
        ss = sst.yellow_bohai.loc[:end]
        sd = sst.northern_ecs.loc[:end]
        for h in cfg["horizons"]:
            xs, os = feature_matrix(
                ss, forcing["yellow_bohai"].reindex(ss.index), h, group
            )
            xd, od = feature_matrix(
                sd, forcing["northern_ecs"].reindex(sd.index), h, group
            )
            sm = increment_moments(xs, os, ss, cfg["train_end"])
            dm = increment_moments(xd, od, sd, cfg["train_end"])
            for family in ["ridge", "trees"]:
                key = f"{family}__{group}__h{h}"
                source = models[key + "__source"]
                local = models[key + "__local"]
                predicted = aligned_prediction(source, local, xd, od, sm, dm)
                parameters[key] = {
                    "source_increment_mean_std_n": sm,
                    "destination_increment_mean_std_n": dm,
                    "destination_feature_mean": local.mean.tolist(),
                    "destination_feature_scale": local.scale.tolist(),
                }
                for period, (start, stop) in cfg["test_periods"].items():
                    if stop > end:
                        continue
                    q = pd.DataFrame(
                        {
                            "date": sd.loc[start:stop].index,
                            "observed": sd.loc[start:stop].values,
                            "predicted": predicted.loc[start:stop].values,
                            "period": period,
                            "family": family,
                            "group": group,
                            "horizon_days": h,
                        }
                    )
                    if not np.isfinite(q.predicted).all():
                        raise ValueError("all evaluation dates required")
                    predictions.append(q)
    frame = pd.concat(predictions, ignore_index=True)
    frame["error"] = frame.predicted - frame.observed
    frame["mse"] = frame.error**2
    frame["year"] = frame.date.dt.year
    frame.to_csv(OUTPUT / "alignment_predictions.csv", index=False)
    for extra, name in [
        ([], "alignment_metrics.csv"),
        (["year"], "alignment_annual_metrics.csv"),
    ]:
        out = frame.groupby(["period", "family", "group", "horizon_days"] + extra).agg(
            n_days=("error", "size"), mse=("mse", "mean"), bias=("error", "mean")
        )
        out["rmse"] = np.sqrt(out.mse)
        out.reset_index().to_csv(OUTPUT / name, index=False)
    if sha256(archive) != before:
        raise ValueError("source/local model archive changed")
    record = {
        "evaluated_utc": datetime.now(timezone.utc).isoformat(),
        "software_sha256": sha256(__file__),
        "input_sha256": {
            str(p): sha256(p)
            for p in [
                archive,
                OUTPUT / "regional_sst.csv",
                OUTPUT / "yellow_bohai_forcing.csv",
                OUTPUT / "northern_ecs_forcing.csv",
            ]
        },
        "original_model_archive_unchanged": True,
        "parameters": parameters,
        "scope": "Added after raw transfer scores were inspected. Descriptive post-outcome diagnostic, no new selection or p value. Destination training histories calibrate feature and increment location/scale; source regression/tree coefficients stay fixed. Not a destination-data-free or unchanged-scaler forecast. Joint alignment does not identify a unique physical cause of domain shift.",
    }
    (OUTPUT / "alignment_audit.json").write_text(json.dumps(record, indent=2) + "\n")


if __name__ == "__main__":
    main()
