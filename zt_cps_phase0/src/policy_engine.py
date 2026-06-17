"""Defense policy engine: greedy node-hardening search (heuristic).

This module reproduces the paper's *policy optimizer* in a simplified, honest form.
The paper uses deep Q-learning (DQL) to select a defense policy that minimizes the
attacker's bypass probability ``pa``; Phase 0 deliberately substitutes a
**deterministic greedy forward-selection heuristic** -- it is *not* a guaranteed
global optimum and is labelled as such.

Defense model
-------------
A zero-trust defense reduces (does not necessarily sever) the *trust* the worm
exploits. Hardening a node ``i`` multiplies its infection couplings -- row and
column ``i`` of ``B`` -- by ``(1 - HARDENING_DELTA)``. With ``HARDENING_DELTA < 1``
the node still leaks some infection, so the defense has diminishing returns: this
reproduces the paper's *shallow* improvement from ``Nk = 10`` to ``Nk = 15`` (full
node isolation, by contrast, collapses ``pa`` to ~0 and cannot match the paper).

``Nk`` is the defense budget: the number of nodes the greedy search may harden.
"""

from __future__ import annotations

from typing import Callable

import numpy as np

from . import attack_engine as ae, config


def apply_policy(
    B: np.ndarray,
    selected: list[int],
    delta: float = config.HARDENING_DELTA,
) -> np.ndarray:
    """Return the defended infection matrix ``B'`` after hardening ``selected`` nodes.

    Hardening node ``i`` multiplies row and column ``i`` of ``B`` by ``(1 - delta)``,
    attenuating (not removing) its infection couplings.

    Parameters
    ----------
    B : numpy.ndarray, shape (55, 55)
        Baseline infection adjacency matrix.
    selected : list[int]
        0-indexed node ids to harden.
    delta : float
        Trust-reduction factor in ``[0, 1]``; ``delta = 1`` is full isolation.

    Returns
    -------
    B_prime : numpy.ndarray, shape (55, 55)
        The defended infection matrix.
    """
    B_prime = B.copy()
    factor = 1.0 - delta
    for node in selected:
        B_prime[node, :] *= factor
        B_prime[:, node] *= factor
    return B_prime


def evaluate_policy(
    B_prime: np.ndarray,
    H: np.ndarray,
    A: np.ndarray,
    C_targets: np.ndarray,
    n_steps: int = config.N_STEPS,
    seed: int = config.SEED,
) -> float:
    """Run the full worm+attack simulation under ``B'`` and return the average ``pa``.

    Re-initializes the worm to ``rho0``, advances it for ``n_steps`` under ``B'``,
    samples the latching compromise state each step, and averages the bypass
    probability. ``pa`` is a function of the *dynamics* under ``B'``, not a static
    property -- hence the re-simulation. The RNG is reseeded identically each call so
    policies are compared on the same infection/attack realization.

    Parameters
    ----------
    B_prime : numpy.ndarray, shape (55, 55)
    H : numpy.ndarray, shape (M, N)
    A : numpy.ndarray, shape (M, 55)
    C_targets : numpy.ndarray, shape (n_fdi, N)
        Shared FDI target perturbations (reused across all policies).
    n_steps : int
    seed : int

    Returns
    -------
    avg_pa : float
        Mean bypass probability over the horizon.
    """
    rng = np.random.default_rng(seed + 1)
    rho = np.full(config.N_NODES, config.RHO0)
    compromised = np.zeros(config.N_NODES)
    pas = np.empty(n_steps)
    for t in range(n_steps):
        rho = ae.update_worm(rho, B_prime)
        compromised = ae.sample_compromise(rho, compromised, rng)
        pas[t] = ae.compute_pa(C_targets, H, A, compromised)
    return float(pas.mean())


def greedy_search(
    B: np.ndarray,
    Nk: int,
    H: np.ndarray,
    A: np.ndarray,
    C_targets: np.ndarray,
    delta: float = config.HARDENING_DELTA,
) -> tuple[list[int], float]:
    """Greedily select ``Nk`` nodes to harden so as to minimize the average ``pa``.

    Forward selection: in each of ``Nk`` rounds, harden the single not-yet-selected
    node whose addition most reduces the average bypass probability, given those
    already chosen. This is a **heuristic** -- it is not guaranteed to find the
    globally optimal node set.

    Cost is ``O(Nk * 55)`` full simulations. The shared ``C_targets`` and the fixed
    seed keep every evaluation comparable.

    Parameters
    ----------
    B : numpy.ndarray, shape (55, 55)
    Nk : int
        Defense budget (number of nodes to harden).
    H : numpy.ndarray, shape (M, N)
    A : numpy.ndarray, shape (M, 55)
    C_targets : numpy.ndarray, shape (n_fdi, N)
    delta : float
        Trust-reduction factor per hardened node.

    Returns
    -------
    selected : list[int]
        The hardened node ids, in selection order.
    avg_pa : float
        The average bypass probability achieved by the selected policy.
    """
    selected: list[int] = []
    n_nodes = B.shape[0]
    best_pa = float("inf")
    for _ in range(Nk):
        round_best_node = None
        round_best_pa = float("inf")
        for candidate in range(n_nodes):
            if candidate in selected:
                continue
            trial = selected + [candidate]
            pa = evaluate_policy(apply_policy(B, trial, delta), H, A, C_targets)
            if pa < round_best_pa:
                round_best_pa = pa
                round_best_node = candidate
        selected.append(int(round_best_node))
        best_pa = round_best_pa
    return selected, best_pa
