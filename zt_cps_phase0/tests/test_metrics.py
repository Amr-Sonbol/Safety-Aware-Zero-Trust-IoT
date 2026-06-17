"""Tests for Phase 1 metrics: M7 reuse of Phase 0, channel fidelity, bounds."""

from __future__ import annotations

import numpy as np
import pytest

from zt_cps_phase0.src import (
    attack_engine as ae,
    config,
    decision as dec,
    metrics as mx,
    node_profiles as npf,
    power_system as ps,
    topology as tp,
)


@pytest.fixture(scope="module")
def model():
    net = ps.load_network()
    H, branch_rows, _ = ps.build_H(net)
    B = tp.build_B()
    A = tp.build_A(H.shape[0])
    classes = tp.assign_classes()
    # Phase 0 weight W = R^{-1}, built from a clean measurement vector (as the runner).
    base_p = net.load.p_mw.to_numpy().copy()
    base_q = net.load.q_mvar.to_numpy().copy()
    profile_curve = ps.load_profile()
    rng = np.random.default_rng(config.SEED)
    _, z_clean = ps.generate_z(net, branch_rows, base_p, profile_curve, 0, rng, base_q)
    R = ps.build_R(z_clean)
    W = np.linalg.inv(R)
    C = ae.generate_fdi_targets(H, rng)
    return H, W, A, B, classes, C


# --- M7 reuses Phase 0 build_H/build_R --------------------------------------

def test_M7_full_observation_is_baseline(model):
    """H_obs == H (all rows kept) -> observable, est_inflation exactly 1.0."""
    H, W, A, _, _, _ = model
    obs_mask = np.ones(H.shape[0], dtype=bool)
    observable, inflation = mx.observability_cost(H, W, obs_mask)
    assert observable is True
    assert abs(inflation - 1.0) < 1e-9


def test_M7_dropping_rows_inflates_or_unobservable(model):
    """Dropping measurement rows raises est_inflation (still observable) or flags it."""
    H, W, A, _, _, _ = model
    # Drop a handful of rows but keep > N: should stay observable with inflation > 1.
    obs_mask = np.ones(H.shape[0], dtype=bool)
    obs_mask[:5] = False
    observable, inflation = mx.observability_cost(H, W, obs_mask)
    if observable:
        assert inflation > 1.0
    else:
        assert inflation == float("inf")


def test_M7_too_few_rows_unobservable(model):
    """Keeping fewer than N rows is never observable (inflation = inf)."""
    H, W, _, _, _, _ = model
    obs_mask = np.zeros(H.shape[0], dtype=bool)
    obs_mask[: config.N_STATES - 1] = True  # one short of N
    observable, inflation = mx.observability_cost(H, W, obs_mask)
    assert observable is False
    assert inflation == float("inf")


# --- channel fidelity: all-full reproduces Gate A ---------------------------

def test_all_full_M4_matches_gate_A(model):
    """An all-`full` policy over 40 steps reproduces the runner's Gate A pa (0.7408).

    With every node `full`: injectable == compromised (all keep C3) and B' == B (no
    deny), so run_step is exactly the runner's Gate A inner loop. This certifies the
    Phase 1 channel wiring matches the frozen Phase 0 engine.
    """
    H, W, A, B, classes, C = model
    profiles = npf.build_node_profiles(B, A, classes)
    logger = mx.MetricsLogger(H, W, classes)

    rng = np.random.default_rng(config.SEED + 1)  # same reseed as the runner / evaluate_policy
    rho = np.full(config.N_NODES, config.RHO0)
    compromised = np.zeros(config.N_NODES)
    decisions = {i: "full" for i in range(config.N_NODES)}
    for _ in range(config.N_STEPS):
        rho, compromised, rec = dec.run_step(
            decisions, rho, compromised, B, H, A, C, rng
        )
        npf.update_profiles(profiles, rho)
        logger.log_step(profiles, decisions, rec["pa"], rec["obs_mask"])

    # Recompute the runner's Gate A on the identical realization for an exact match.
    rng2 = np.random.default_rng(config.SEED + 1)
    rho2 = np.full(config.N_NODES, config.RHO0)
    comp2 = np.zeros(config.N_NODES)
    pas = []
    for _ in range(config.N_STEPS):
        rho2 = ae.update_worm(rho2, B)
        comp2 = ae.sample_compromise(rho2, comp2, rng2)
        pas.append(ae.compute_pa(C, H, A, comp2))
    gate_a = float(np.mean(pas))

    assert abs(logger.M4() - gate_a) < 1e-12
    assert config.GATE_A[0] <= logger.M4() <= config.GATE_A[1]
    # all-full keeps every row observable with no inflation
    assert logger.M7()["frac_observable"] == 1.0
    assert abs(logger.M7()["mean_inflation"] - 1.0) < 1e-9


# --- metric bounds ----------------------------------------------------------

def test_metric_bounds(model):
    """M1 in [0,1]; M2, M3 >= 0; M5 fractions per class sum to ~1."""
    H, W, A, B, classes, C = model
    profiles = npf.build_node_profiles(B, A, classes)
    logger = mx.MetricsLogger(H, W, classes)
    rng = np.random.default_rng(config.SEED + 1)
    rho = np.full(config.N_NODES, config.RHO0)
    compromised = np.zeros(config.N_NODES)
    # mixed decisions to exercise all branches
    decisions = {}
    for i in range(config.N_NODES):
        decisions[i] = ("deny", "full", "safe_mode", "read_only", "restricted")[i % 5]
    for _ in range(config.N_STEPS):
        rho, compromised, rec = dec.run_step(
            decisions, rho, compromised, B, H, A, C, rng
        )
        npf.update_profiles(profiles, rho)
        logger.log_step(profiles, decisions, rec["pa"], rec["obs_mask"])

    assert 0.0 <= logger.M1() <= 1.0
    assert logger.M2() >= 0.0
    assert logger.M3() >= 0.0
    m5 = logger.M5()
    for c, dist in m5.items():
        assert abs(sum(dist.values()) - 1.0) < 1e-9
