"""Tests for the power-system model: H shape, rank, reactance weighting, residual."""

from __future__ import annotations

import numpy as np
import pytest

from zt_cps_phase0.src import config, power_system as ps


@pytest.fixture(scope="module")
def network():
    return ps.load_network()


@pytest.fixture(scope="module")
def H_bundle(network):
    H, branch_rows, state_index = ps.build_H(network)
    return network, H, branch_rows, state_index


def test_network_load_and_slack(network):
    """Total load is 283.4 MW and the slack voltage is 1.06 p.u."""
    assert abs(float(network.load.p_mw.sum()) - 283.4) < 0.5
    assert abs(float(network.ext_grid.vm_pu.iloc[0]) - 1.06) < 1e-6


def test_H_shape(H_bundle):
    """H is (M, 29) with N = 29 states (slack angle removed)."""
    _, H, _, _ = H_bundle
    assert H.shape[1] == config.N_STATES == 29
    assert H.shape[0] == 41  # 34 lines + 7 trafos for case_ieee30


def test_H_full_rank(H_bundle):
    """H is full column rank (29)."""
    _, H, _, _ = H_bundle
    assert np.linalg.matrix_rank(H, tol=config.RANK_TOL) == config.N_STATES


def test_H_reactance_weighted(H_bundle):
    """H entries are reactance weights (1/x), not +/-1 incidence values."""
    _, H, _, _ = H_bundle
    nonzero = H[H != 0]
    # The classic incidence bug would make every entry exactly +/-1.
    assert not np.allclose(np.abs(nonzero), 1.0)
    # At least some entries are well above 1.0 (typical 1/x for x ~ 0.05-0.2).
    assert np.max(np.abs(nonzero)) > 1.5


def test_clean_residual_is_small(H_bundle):
    """With no attack/no infection, ||z_clean - H x_hat|| is at the noise floor.

    Real measurements lie in the column space of H, so the clean WLS residual must
    be at machine precision. A large value means H or z is wrong (units/ordering).
    """
    net, H, branch_rows, _ = H_bundle
    base_p = net.load.p_mw.to_numpy().copy()
    base_q = net.load.q_mvar.to_numpy().copy()
    profile = ps.load_profile()
    rng = np.random.default_rng(config.SEED)
    z, z_clean = ps.generate_z(net, branch_rows, base_p, profile, 0, rng, base_q)
    R = ps.build_R(z_clean)
    K = ps.build_estimator(H, R)
    assert ps.clean_residual_norm(z_clean, H, K) < 1e-6


def test_estimator_inverts_H(H_bundle):
    """The WLS gain satisfies K H = I_N."""
    _, H, _, _ = H_bundle
    R = np.eye(H.shape[0])
    K = ps.build_estimator(H, R)
    assert np.allclose(K @ H, np.eye(H.shape[1]), atol=1e-9)
