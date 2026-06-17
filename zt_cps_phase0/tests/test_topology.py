"""Tests for the cyber topology: B symmetry/edges and A incidence shape."""

from __future__ import annotations

import numpy as np

from zt_cps_phase0.src import config, topology as tp


def test_B_shape_and_symmetry():
    """B is 55x55, symmetric, with a zero diagonal."""
    B = tp.build_B()
    assert B.shape == (config.N_NODES, config.N_NODES)
    assert np.array_equal(B, B.T)
    assert np.trace(B) == 0.0


def test_B_edge_count():
    """B has exactly 2 * (number of Fig. 5 edges) nonzeros (no dup/dropped edges)."""
    B = tp.build_B()
    n_edges = len(tp.get_edges())
    assert B.sum() == 2 * n_edges
    assert n_edges == 83  # the Fig. 5 edge list has 83 unique edges


def test_B_is_binary():
    """B is a binary adjacency matrix."""
    B = tp.build_B()
    assert set(np.unique(B)).issubset({0.0, 1.0})


def test_A_shape_and_rows():
    """A is (M, 55) with exactly one nonzero per row (one collecting node each)."""
    m = 41  # branch count for case_ieee30
    A = tp.build_A(m)
    assert A.shape == (m, config.N_NODES)
    assert np.all(A.sum(axis=1) == 1)


def test_A_row_count_matches_M():
    """A's row count equals the measurement count M."""
    for m in (10, 41, 50):
        A = tp.build_A(m)
        assert A.shape[0] == m


# --- Phase 1 additions -------------------------------------------------------

def test_assign_classes_labels_all_55_nodes():
    """assign_classes labels every node with a known device class."""
    classes = tp.assign_classes()
    assert len(classes) == config.N_NODES
    assert set(classes.keys()) == set(range(config.N_NODES))
    assert all(c in config.DEVICE_CLASSES for c in classes.values())


def test_assign_classes_all_five_present():
    """All five device classes are non-empty (required for the M5 distribution)."""
    classes = tp.assign_classes()
    assert set(classes.values()) == set(config.DEVICE_CLASSES)


def test_assign_classes_deterministic():
    """assign_classes is deterministic across calls."""
    assert tp.assign_classes() == tp.assign_classes()


def test_assign_classes_respects_sensor_role():
    """Sensor nodes map to T-PDP-*, non-sensor nodes to C-PDP-*."""
    classes = tp.assign_classes()
    sensors = set(int(i) for i in tp.sensor_nodes())
    for node, cls in classes.items():
        if node in sensors:
            assert cls.startswith("T-PDP-"), f"sensor node {node} got {cls}"
        else:
            assert cls.startswith("C-PDP-"), f"non-sensor node {node} got {cls}"


def test_action_delta_values():
    """delta_a = 1 - (O_a + C_a)/2 yields the spec's {0, 0.25, 0.5, 0.9, 1.0}."""
    expected = {
        "full": 0.00, "restricted": 0.25, "read_only": 0.50,
        "safe_mode": 0.90, "deny": 1.00,
    }
    for name, spec in config.ACTIONS.items():
        delta = 1.0 - (spec["O"] + spec["C"]) / 2.0
        assert abs(delta - expected[name]) < 1e-12, f"{name}: delta={delta}"
