"""Cyber-topology model: the infection graph ``B`` and sensor map ``A``.

This module reproduces the *cyber* half of the attack model: the 55-node worm
infection graph (paper Fig. 5) as a symmetric adjacency matrix ``B``, and the
measurement-to-sensor assignment ``A`` that maps each physical branch-flow
measurement to the cyber node that collects it.

Modeling assumptions
--------------------
* **The 55-node edge list is read from Fig. 5 of the paper and is approximate.**
  Nodes are 1-indexed in the paper and 0-indexed in code; the only place the
  1-indexing lives is :func:`get_edges`.
* **B is symmetric with a zero diagonal** (the worm spreads bidirectionally along
  trust relationships; no self-infection edges).
* **A maps each of the M branch-flow measurements to exactly one collecting sensor
  node** (``A[m, i] = 1`` means node ``i`` measures branch ``m``). Because there
  are more branch measurements (M = 41) than red sensor nodes (~30), a node may
  collect several branches — so columns of ``A`` may have multiple ones, but every
  *row* has exactly one. The exact branch->sensor incidence is not published in the
  paper, so the assignment here is a deterministic, documented approximation:
  measurements are distributed round-robin over a fixed set of sensor nodes, in
  branch order, guaranteeing each sensor node owns at least one measurement.
"""

from __future__ import annotations

import numpy as np

from . import config

# Paper Fig. 5 infection-graph edges, 1-indexed exactly as published.
# Treated as approximate (read from a figure). 83 unique edges over 55 nodes.
_EDGES_1_INDEXED: list[tuple[int, int]] = [
    (1, 21), (1, 22), (2, 3), (2, 22), (3, 18), (4, 5), (4, 6), (4, 14),
    (5, 7), (6, 7), (6, 14), (7, 8), (8, 9), (8, 10), (9, 12), (10, 11),
    (11, 12), (11, 13), (13, 53), (14, 15), (14, 18), (15, 16), (15, 17),
    (16, 17), (16, 52), (16, 53), (17, 19), (17, 43), (18, 20), (19, 27),
    (19, 38), (19, 39), (19, 43), (20, 24), (20, 26), (21, 23), (22, 23),
    (23, 24), (24, 25), (24, 26), (25, 29), (26, 27), (26, 29), (27, 28),
    (28, 32), (28, 35), (29, 30), (30, 31), (31, 32), (31, 33), (32, 35),
    (33, 34), (34, 35), (34, 36), (35, 36), (36, 46), (37, 42), (37, 46),
    (38, 39), (38, 40), (39, 40), (39, 41), (40, 41), (40, 42), (41, 43),
    (41, 44), (42, 45), (43, 52), (44, 45), (44, 50), (44, 51), (44, 54),
    (45, 47), (45, 48), (46, 47), (47, 48), (48, 49), (49, 51), (50, 51),
    (50, 54), (52, 54), (53, 55), (54, 55),
]


def get_edges() -> list[tuple[int, int]]:
    """Return the Fig. 5 infection-graph edges, **1-indexed** as in the paper.

    Returns
    -------
    list[tuple[int, int]]
        Each tuple ``(u, v)`` is an undirected edge with 1-based node labels.

    Notes
    -----
    These edges are read off Fig. 5 and are therefore approximate. This is the only
    function in the codebase that uses 1-based indexing.
    """
    return list(_EDGES_1_INDEXED)


def build_B() -> np.ndarray:
    """Build the 55x55 symmetric infection adjacency matrix ``B``.

    Converts the 1-indexed Fig. 5 edge list to 0-indexed and sets ``B[u,v] =
    B[v,u] = 1`` for each edge. The diagonal is zero (no self-infection).

    Returns
    -------
    B : numpy.ndarray, shape (55, 55)
        Symmetric binary adjacency matrix with zero diagonal.

    Raises
    ------
    AssertionError
        If ``B`` is not symmetric, has a non-zero diagonal, or its edge count does
        not match the published edge list (catches duplicate/dropped edges).
    """
    n = config.N_NODES
    B = np.zeros((n, n), dtype=float)
    edges = get_edges()
    for u, v in edges:
        B[u - 1, v - 1] = 1.0
        B[v - 1, u - 1] = 1.0

    assert B.shape == (n, n), f"B shape {B.shape} != ({n},{n})"
    assert np.array_equal(B, B.T), "B is not symmetric"
    assert np.trace(B) == 0.0, "B has a non-zero diagonal (self-edge present)"
    assert B.sum() == 2 * len(edges), (
        f"B edge count {int(B.sum() / 2)} != {len(edges)} (duplicate/dropped edge)"
    )

    degrees = B.sum(axis=1)
    print(
        f"[build_B] nodes={n}, edges={len(edges)}, "
        f"mean degree={degrees.mean():.2f}, max degree={int(degrees.max())}"
    )
    return B


# Fixed set of sensor (red) nodes that collect physical measurements. Chosen as a
# documented approximation: the first SENSOR_COUNT node ids. The paper does not
# publish the exact branch->sensor incidence; what matters for the attack model is
# that infected sensor nodes gate which measurements an attacker can manipulate.
_SENSOR_COUNT = 30


def sensor_nodes() -> np.ndarray:
    """Return the 0-indexed node ids designated as physical-measurement sensors.

    Returns
    -------
    numpy.ndarray, shape (SENSOR_COUNT,)
        The sensor node indices (a deterministic subset of the 55 nodes).
    """
    return np.arange(_SENSOR_COUNT)


def build_A(m: int) -> np.ndarray:
    """Build the M x 55 measurement-to-sensor incidence matrix ``A``.

    ``A[m, i] = 1`` means branch-flow measurement ``m`` is collected by sensor node
    ``i``. Measurements are assigned round-robin over :func:`sensor_nodes` in branch
    order, so every sensor node owns at least one measurement and (because M > number
    of sensors) some own several.

    Parameters
    ----------
    m : int
        Number of branch-flow measurements (rows of ``H``).

    Returns
    -------
    A : numpy.ndarray, shape (m, 55)
        Binary incidence matrix with exactly one nonzero per row.

    Raises
    ------
    AssertionError
        If the shape is wrong or any row does not have exactly one nonzero.
    """
    n = config.N_NODES
    sensors = sensor_nodes()
    A = np.zeros((m, n), dtype=float)
    for meas in range(m):
        node = int(sensors[meas % len(sensors)])
        A[meas, node] = 1.0

    assert A.shape == (m, n), f"A shape {A.shape} != ({m},{n})"
    assert np.all(A.sum(axis=1) == 1), "A has a row without exactly one nonzero"
    print(
        f"[build_A] shape={A.shape}, sensor nodes used={len(np.unique(np.where(A)[1]))}"
    )
    return A
