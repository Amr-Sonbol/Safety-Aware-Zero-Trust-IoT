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
