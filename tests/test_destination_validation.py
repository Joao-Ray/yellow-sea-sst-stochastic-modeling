"""Scientific boundaries for destination observation verification."""

import numpy as np
import pandas as pd

from src.destination_validation import (
    array_hash,
    forecast,
    grid_cycles,
    point_geography,
)


def test_grid_climatology_ignores_evaluation_values():
    dates = pd.date_range("2010-01-01", "2023-12-31")
    t = np.arange(len(dates))
    values = np.column_stack([10 + np.sin(t / 58) + t / 10000, 15 + 2 * np.sin(t / 58)])
    cycle, beta = grid_cycles(values, dates, "2019-12-31")
    changed = values.copy()
    changed[dates > "2019-12-31"] += 1000
    repeat, repeat_beta = grid_cycles(changed, dates, "2019-12-31")
    np.testing.assert_array_equal(beta, repeat_beta)
    np.testing.assert_array_equal(cycle, repeat)


def test_destination_points_exclude_previous_source_matching_radius():
    cfg = {"buoy_max_distance_km": 20, "buoy_exclude_within_source_km": 20}
    _, distance, source_distance, keep = point_geography(
        np.array([32.0, 32.0, 32.0]),
        np.array([124.0, 124.10, 125.0]),
        np.array([32.0]),
        np.array([124.0]),
        np.array([32.0]),
        np.array([124.3]),
        cfg,
    )
    assert distance[0] < 1e-10 and source_distance[0] > 20
    assert distance[1] < 20 and source_distance[1] < 20
    np.testing.assert_array_equal(keep, [True, False, False])


def test_locked_projection_preserves_origin_spatial_offsets():
    cube = {
        "origin_h7": np.array([[10.0, 12.0], [11.0, 13.0]]),
        "delta_h7__anomaly_ridge": np.array([0.5, -0.25]),
    }
    prediction = forecast(cube, "anomaly_ridge", 7)
    np.testing.assert_allclose(
        prediction, [[10.5, 12.5], [10.75, 12.75]], atol=0, rtol=0
    )
    assert array_hash(prediction) != array_hash(prediction + 1e-5)
    cube["h7__grid_climatology"] = np.array([[14.0, 15.0], [14.1, 15.1]])
    np.testing.assert_array_equal(
        forecast(cube, "grid_climatology", 7), cube["h7__grid_climatology"]
    )
