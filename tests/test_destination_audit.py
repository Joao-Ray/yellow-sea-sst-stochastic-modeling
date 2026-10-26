"""Independent matching must respect the locked coordinate arithmetic."""

import numpy as np
from scipy.spatial import cKDTree

from src.destination_audit import nearest_like_frozen, xyz
from src.insitu import nearest_cells


def test_sphere_coordinates_use_double_precision_even_for_float32_input():
    unit = xyz(
        np.array([32.125, 32.875], dtype=np.float32),
        np.array([126.625, 126.875], dtype=np.float32),
    )
    assert unit.dtype == np.float64
    np.testing.assert_allclose(np.linalg.norm(unit, axis=1), 1, atol=2e-15, rtol=0)


def test_tree_candidates_reproduce_locked_matching_at_cell_bisectors():
    lat, lon = np.meshgrid(
        np.arange(31.125, 33.126, 0.25, dtype=np.float32),
        np.arange(120.875, 127.876, 0.25, dtype=np.float32),
        indexing="ij",
    )
    lat, lon = lat.ravel(), lon.ravel()
    obs_lat = np.array([32.630001068115234, 32.689998626708984, 32.875, 31.25, 32.63])
    obs_lon = np.array([126.75, 126.75, 126.75, 124.25, 121.03])
    tree = cKDTree(xyz(lat, lon))
    expected_index, expected_distance = nearest_cells(obs_lat, obs_lon, lat, lon)
    index, distance = nearest_like_frozen(tree, obs_lat, obs_lon, lat, lon)
    np.testing.assert_array_equal(index, expected_index)
    np.testing.assert_allclose(distance, expected_distance, atol=1e-10, rtol=0)
