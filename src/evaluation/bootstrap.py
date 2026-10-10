"""Paired circular calendar-block bootstrap for descriptive forecast skill."""

from __future__ import annotations

import numpy as np
import pandas as pd


def skill_interval(
    observed: pd.Series,
    predicted: pd.Series,
    baseline: pd.Series,
    *,
    block_days: int = 30,
    replicates: int = 500,
    seed: int = 42,
) -> dict[str, float | int | None]:
    """Resample paired daily loss blocks, preserving gaps on the calendar grid.

    Percentile intervals rely on approximate stationarity and the chosen block
    length. They do not remove trend bias or establish final scientific claims.
    """
    if block_days < 1 or replicates < 100:
        raise ValueError("positive block length and at least 100 replicates required")
    if not observed.index.equals(predicted.index) or not observed.index.equals(
        baseline.index
    ):
        raise ValueError("bootstrap inputs must share the same dates")
    if (
        not isinstance(observed.index, pd.DatetimeIndex)
        or observed.index.has_duplicates
    ):
        raise ValueError("bootstrap inputs need unique datetime dates")
    data = (
        pd.DataFrame(
            {
                "model": (predicted - observed) ** 2,
                "baseline": (baseline - observed) ** 2,
            }
        )
        .sort_index()
        .asfreq("D")
    )
    data = data.replace([np.inf, -np.inf], np.nan)
    n = len(data)
    if n < 2 * block_days:
        raise ValueError("scoring period must contain at least two bootstrap blocks")
    losses = data.to_numpy()
    complete = np.isfinite(losses).all(axis=1)
    losses[~complete] = np.nan
    rng = np.random.default_rng(seed)
    samples = []
    offsets = np.arange(block_days)
    blocks = int(np.ceil(n / block_days))
    for _ in range(replicates):
        starts = rng.integers(0, n, size=blocks)
        positions = ((starts[:, None] + offsets) % n).ravel()[:n]
        resampled = losses[positions]
        valid = np.isfinite(resampled).all(axis=1)
        if not valid.any():
            continue
        model_mse, baseline_mse = resampled[valid].mean(axis=0)
        if baseline_mse > 0:
            samples.append(float(1 - np.sqrt(model_mse / baseline_mse)))
    if len(samples) < 100:
        low = high = None
    else:
        low, high = (float(x) for x in np.quantile(samples, [0.025, 0.975]))
    return {
        "skill_ci_lower": low,
        "skill_ci_upper": high,
        "bootstrap_replicates_valid": len(samples),
        "bootstrap_block_days": block_days,
    }
