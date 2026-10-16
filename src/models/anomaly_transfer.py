"""Training-climatology-assisted transfer of dimensionless SST anomaly increments."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.models.process_transfer import (
    feature_matrix,
    heat_into_ocean,
    validate_calendar,
)
from src.models.seasonal import fit_seasonal


def drivers(forcing):
    return pd.DataFrame(
        {
            "heat": heat_into_ocean(forcing),
            "u": forcing.uwnd,
            "v": forcing.vwnd,
            "vector_magnitude": np.hypot(forcing.uwnd, forcing.vwnd),
        }
    )


@dataclass(frozen=True)
class ClimateScale:
    sst_cycle: object
    sst_scale: float
    driver_cycles: dict
    driver_scales: dict
    train_end: str

    def state(self, sst):
        return (sst - self.sst_cycle.predict(sst.index)) / self.sst_scale

    def decode(self, prediction):
        return self.sst_cycle.predict(prediction.index) + self.sst_scale * prediction

    def to_dict(self):
        return {
            "sst_cycle": self.sst_cycle.to_dict(),
            "sst_residual_std": self.sst_scale,
            "driver_cycles": {k: v.to_dict() for k, v in self.driver_cycles.items()},
            "driver_residual_stds": self.driver_scales,
            "training_end": self.train_end,
            "scope": "Local training information: harmonic/trend coefficients and residual scales. Not destination-data-free transfer.",
        }


def fit_climate(sst, forcing, train_end, harmonics=3, trend=True):
    validate_calendar(sst)
    validate_calendar(forcing)
    if not forcing.index.isin(sst.index).all():
        raise ValueError("forcing calendar must be a subset of the SST calendar")
    training = sst.loc[:train_end]
    cycle = fit_seasonal(training, harmonics=harmonics, trend=trend)
    scale = float((training - cycle.predict(training.index)).std(ddof=0))
    if not np.isfinite(scale) or scale < 1e-8:
        raise ValueError("nondegenerate training SST anomalies required")
    cycles, scales = {}, {}
    for name, s in drivers(forcing).items():
        train = s.loc[:train_end]
        c = fit_seasonal(train, harmonics=harmonics, trend=trend)
        sd = float((train - c.predict(train.index)).std(ddof=0))
        cycles[name] = c
        scales[name] = sd if sd > 1e-12 else 1.0
    return ClimateScale(
        cycle, scale, cycles, scales, str(pd.Timestamp(train_end).date())
    )


def design(sst, forcing, climate, representation, horizon, group, delay=1):
    if representation == "raw":
        x, origin = feature_matrix(sst, forcing, horizon, group, delay)
        return x, origin, sst
    if representation != "seasonal_anomaly":
        raise ValueError("unknown representation")
    state = climate.state(sst)
    x, origin = feature_matrix(state, None, horizon, "sst", delay)
    x = x.rename(
        columns={
            k: k.replace("sst_", "normalized_anomaly_")
            for k in x
            if k.startswith("sst_")
        }
    )
    if group not in {"sst", "sst_heat", "sst_heat_wind"}:
        raise ValueError("unknown feature group")
    if group != "sst":
        if not forcing.index.equals(sst.index):
            raise ValueError("forcing and SST dates must align for forcing features")
        validate_calendar(forcing)
        wanted = (
            ["heat"] if group == "sst_heat" else ["heat", "u", "v", "vector_magnitude"]
        )
        raw = drivers(forcing)
        for name in wanted:
            anomaly = (
                raw[name] - climate.driver_cycles[name].predict(raw.index)
            ) / climate.driver_scales[name]
            for window in [1, 7, 30]:
                x[f"{name}_normalized_anomaly_past_mean_{window}"] = (
                    anomaly.rolling(window).mean().shift(horizon + delay)
                )
    return x, origin, state


def decode(prediction, climate, representation):
    return prediction if representation == "raw" else climate.decode(prediction)
