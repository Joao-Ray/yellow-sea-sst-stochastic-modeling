"""Training-only harmonic seasonal cycles with optional linear trend."""

from dataclasses import dataclass
import numpy as np
import pandas as pd


def seasonal_design(
    index: pd.DatetimeIndex, origin: pd.Timestamp, harmonics: int, trend: bool
) -> np.ndarray:
    if not isinstance(index, pd.DatetimeIndex) or index.tz is not None:
        raise ValueError("seasonal input needs timezone-free calendar dates")
    # A common leap-year template keeps March-December phase stable across years.
    template = pd.to_datetime("2000-" + index.strftime("%m-%d"))
    phase = (template - pd.Timestamp("2000-01-01")).days.to_numpy() / 366
    columns = [np.ones(len(index))]
    for order in range(1, harmonics + 1):
        columns.extend(
            [np.cos(2 * np.pi * order * phase), np.sin(2 * np.pi * order * phase)]
        )
    if trend:
        columns.append((index - origin).days.to_numpy() / 365.2425)
    return np.column_stack(columns)


@dataclass(frozen=True)
class SeasonalFit:
    coefficients: tuple[float, ...]
    origin: pd.Timestamp
    harmonics: int
    trend: bool
    n: int

    def predict(self, index: pd.DatetimeIndex) -> pd.Series:
        values = seasonal_design(
            index, self.origin, self.harmonics, self.trend
        ) @ np.asarray(self.coefficients)
        return pd.Series(values, index=index, name="deterministic_sst_celsius")

    def to_dict(self) -> dict:
        return {
            "coefficients": self.coefficients,
            "origin": str(self.origin.date()),
            "harmonics": self.harmonics,
            "linear_trend": self.trend,
            "trend_celsius_per_year": self.coefficients[-1] if self.trend else None,
            "n_training_observations": self.n,
            "scope": "training OLS; linear extrapolation is an assumption, not an estimate of future warming",
        }


def fit_seasonal(
    training: pd.Series, harmonics: int = 3, trend: bool = False
) -> SeasonalFit:
    if (
        not isinstance(harmonics, int)
        or isinstance(harmonics, bool)
        or not 1 <= harmonics <= 10
    ):
        raise ValueError("harmonics must be an integer in 1..10")
    finite = training.replace([np.inf, -np.inf], np.nan).dropna().sort_index()
    if (
        finite.index.has_duplicates
        or len(finite) < 730
        or (finite.index[-1] - finite.index[0]).days < 729
    ):
        raise ValueError(
            "seasonal fit needs unique dates and at least two years of observations"
        )
    origin = finite.index[0]
    design = seasonal_design(finite.index, origin, harmonics, trend)
    coefficients, _, rank, _ = np.linalg.lstsq(design, finite.values, rcond=None)
    if rank != design.shape[1]:
        raise ValueError("seasonal training design is rank deficient")
    return SeasonalFit(
        tuple(float(x) for x in coefficients), origin, harmonics, trend, len(finite)
    )
