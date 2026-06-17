"""Tests for the attack engine: worm bounds, pa range, and pa monotonicity."""

from __future__ import annotations

import numpy as np
import pytest

from zt_cps_phase0.src import (
    attack_engine as ae,
    config,
    power_system as ps,
    topology as tp,
)


@pytest.fixture(scope="module")
def model():
    net = ps.load_network()
    H, branch_rows, _ = ps.build_H(net)
    B = tp.build_B()
    A = tp.build_A(H.shape[0])
    return net, H, B, A


def test_rho_stays_in_unit_interval(model):
    """The mean-field worm keeps rho in [0, 1] over the full horizon."""
    _, _, B, _ = model
    rho = np.full(config.N_NODES, config.RHO0)
    for _ in range(config.N_STEPS):
        rho = ae.update_worm(rho, B)
        assert np.all(rho >= 0.0) and np.all(rho <= 1.0)


def test_rho_rises_then_saturates(model):
    """rho_bar rises from rho0 toward an endemic steady state."""
    _, _, B, _ = model
    rho = np.full(config.N_NODES, config.RHO0)
    bars = [ae.compute_rho_bar(rho)]
    for _ in range(config.N_STEPS):
        rho = ae.update_worm(rho, B)
        bars.append(ae.compute_rho_bar(rho))
    assert bars[-1] > bars[0]  # the worm spreads
    assert all(0.0 <= b <= 1.0 for b in bars)


def test_pa_in_unit_interval(model):
    """pa is a probability in [0, 1] at every step."""
    _, H, B, A = model
    rng = np.random.default_rng(config.SEED)
    C = ae.generate_fdi_targets(H, rng)
    rng2 = np.random.default_rng(config.SEED + 1)
    rho = np.full(config.N_NODES, config.RHO0)
    compromised = np.zeros(config.N_NODES)
    for _ in range(config.N_STEPS):
        rho = ae.update_worm(rho, B)
        compromised = ae.sample_compromise(rho, compromised, rng2)
        pa = ae.compute_pa(C, H, A, compromised)
        assert 0.0 <= pa <= 1.0


def test_pa_zero_when_no_compromise(model):
    """With nothing compromised, pa is 0 (no realizable attack)."""
    _, H, _, A = model
    rng = np.random.default_rng(config.SEED)
    C = ae.generate_fdi_targets(H, rng)
    pa = ae.compute_pa(C, H, A, np.zeros(config.N_NODES))
    assert pa == 0.0


def test_pa_one_when_fully_compromised(model):
    """With every node compromised, pa is 1 (any a = Hc is realizable)."""
    _, H, _, A = model
    rng = np.random.default_rng(config.SEED)
    C = ae.generate_fdi_targets(H, rng)
    pa = ae.compute_pa(C, H, A, np.ones(config.N_NODES))
    assert pa == 1.0


def test_pa_rises_with_compromise(model):
    """pa increases monotonically as more measurements are compromised."""
    _, H, _, A = model
    rng = np.random.default_rng(config.SEED)
    C = ae.generate_fdi_targets(H, rng)
    m = H.shape[0]
    pas = []
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        # Compromise the sensor nodes owning the first frac*M measurements.
        n_meas = int(round(frac * m))
        compromised = np.zeros(config.N_NODES)
        owners = np.where(A[:n_meas])[1] if n_meas > 0 else []
        compromised[list(owners)] = 1.0
        pas.append(ae.compute_pa(C, H, A, compromised))
    assert all(pas[i] <= pas[i + 1] + 1e-9 for i in range(len(pas) - 1))
    assert pas[0] == 0.0 and pas[-1] == 1.0
