"""Exact matched-loss identities and dependence-aware secondary inference."""

import numpy as np
import pandas as pd


def loss_components(forecast, analysis, observation, weights):
    weights = np.asarray(weights, float)
    weights = weights / weights.sum()
    error = np.asarray(forecast, float) - np.asarray(analysis, float)
    discrepancy = np.asarray(analysis, float) - np.asarray(observation, float)
    external_error = error + discrepancy
    row = {
        "analysis_forecast_mse": float(weights @ error**2),
        "product_discrepancy_mse": float(weights @ discrepancy**2),
        "interaction": float(2 * weights @ (error * discrepancy)),
        "external_mse": float(weights @ external_error**2),
        "external_mean_error_squared": float((weights @ external_error) ** 2),
    }
    row["external_spatial_error_variance"] = (
        row["external_mse"] - row["external_mean_error_squared"]
    )
    row["identity_error"] = (
        row["external_mse"]
        - row["analysis_forecast_mse"]
        - row["product_discrepancy_mse"]
        - row["interaction"]
    )
    return row


def holm_adjust(pvalues):
    pvalues = np.asarray(pvalues, float)
    order = np.argsort(pvalues, kind="stable")
    adjusted = np.maximum.accumulate(
        (len(pvalues) - np.arange(len(pvalues))) * pvalues[order]
    )
    result = np.empty_like(pvalues)
    result[order] = np.minimum(1.0, adjusted)
    return result


def paired_block_inference(model_loss, baseline_loss, block_days, replicates, seed):
    if (
        not model_loss.index.equals(baseline_loss.index)
        or model_loss.index.has_duplicates
    ):
        raise ValueError("paired losses require identical unique calendar dates")
    frame = (
        pd.DataFrame({"model": model_loss, "base": baseline_loss})
        .sort_index()
        .asfreq("D")
    )
    values = frame.to_numpy(float)
    complete = np.isfinite(values).all(axis=1)
    if not complete.any() or len(frame) < 2 * block_days or replicates < 100:
        raise ValueError("insufficient support for paired calendar blocks")
    values[~complete] = np.nan
    difference = values[:, 1] - values[:, 0]
    advantage = float(np.nanmean(difference))
    null_difference = difference - advantage
    rng = np.random.default_rng(seed)
    offsets = np.arange(block_days)
    skills, advantage_samples, null_samples = [], [], []
    for _ in range(replicates):
        starts = rng.integers(0, len(frame), size=int(np.ceil(len(frame) / block_days)))
        position = ((starts[:, None] + offsets) % len(frame)).ravel()[: len(frame)]
        sample = values[position]
        valid = np.isfinite(sample).all(axis=1)
        if valid.any() and np.mean(sample[valid, 1]) > 0:
            mse = sample[valid].mean(axis=0)
            skills.append(1 - np.sqrt(mse[0] / mse[1]))
            advantage_samples.append(mse[1] - mse[0])
            null_samples.append(float(np.nanmean(null_difference[position])))
    if len(skills) < 100:
        raise ValueError("too few valid paired bootstrap draws")
    lower, upper = np.quantile(skills, [0.025, 0.975])
    lo_delta, hi_delta = np.quantile(advantage_samples, [0.025, 0.975])
    p = (1 + np.sum(np.abs(null_samples) >= abs(advantage))) / (len(null_samples) + 1)
    return {
        "mean_loss_advantage": advantage,
        "loss_advantage_ci_lower": float(lo_delta),
        "loss_advantage_ci_upper": float(hi_delta),
        "skill_ci_lower": float(lower),
        "skill_ci_upper": float(upper),
        "p_bootstrap_two_sided": float(p),
        "bootstrap_block_days": block_days,
        "replicates_valid": len(skills),
        "scope": "secondary centered circular-block bootstrap, approximate stationary-loss inference; not a correction for prior outcome viewing",
    }


def interval_score(observed, predicted, radius, level=0.95):
    observed, predicted, radius = np.broadcast_arrays(observed, predicted, radius)
    alpha = 1 - level
    lower, upper = predicted - radius, predicted + radius
    return (
        2 * radius
        + (2 / alpha) * np.maximum(lower - observed, 0)
        + (2 / alpha) * np.maximum(observed - upper, 0)
    )
