"""Tests for Phase 1 node profiles: counts, unit-interval bounds, R_d synthetic."""

from __future__ import annotations

import numpy as np
import pytest

from zt_cps_phase0.src import (
    config,
    node_profiles as npf,
    topology as tp,
)


@pytest.fixture(scope="module")
def topo():
    B = tp.build_B()
    A = tp.build_A(41)
    classes = tp.assign_classes()
    return B, A, classes


@pytest.fixture(scope="module")
def profiles(topo):
    B, A, classes = topo
    return npf.build_node_profiles(B, A, classes)


def test_profile_count(profiles):
    """There are exactly 55 profiles, one per node, indexed by node_id."""
    assert len(profiles) == config.N_NODES
    for i, p in enumerate(profiles):
        assert p["node_id"] == i


def test_all_unit_fields_in_range(profiles):
    """H_s, D_c, R_d, ASC_r, ASC, DC, rho, T all lie in [0, 1]."""
    for p in profiles:
        for f in ("H_s", "D_c", "R_d", "ASC_r", "ASC", "DC", "rho", "T"):
            assert 0.0 <= float(p[f]) <= 1.0, f"node {p['node_id']} {f}={p[f]}"


def test_R_d_flagged_synthetic(profiles):
    """Every profile flags R_d as synthetic (Assumption A2)."""
    assert all(p["R_d_synthetic"] is True for p in profiles)


def test_R_d_role_based(profiles, topo):
    """Sensor nodes get R_d=1.0, non-sensor nodes get R_d=0.0 (synthetic surrogate)."""
    _, A, _ = topo
    collects = A.sum(axis=0) > 0
    for p in profiles:
        expected = 1.0 if collects[p["node_id"]] else 0.0
        assert p["R_d"] == expected


def test_derived_fields_consistent(profiles):
    """ASC = 0.5*D_c + 0.5*ASC_r and DC = (H_s + D_c + R_d)/3 hold."""
    for p in profiles:
        assert abs(p["ASC"] - (0.5 * p["D_c"] + 0.5 * p["ASC_r"])) < 1e-12
        assert abs(p["DC"] - (p["H_s"] + p["D_c"] + p["R_d"]) / 3.0) < 1e-12


def test_class_drives_H_s_and_D_c(profiles):
    """H_s/D_c follow the SIL/criticality-by-class maps."""
    for p in profiles:
        cls = p["class"]
        assert p["H_s"] == config.SIL_MAP[config.SIL_BY_CLASS[cls]]
        assert p["D_c"] == config.D_C_BY_CLASS[cls]


def test_initial_rho_and_trust(profiles):
    """Profiles start at rho = RHO0 and T = 1 - RHO0."""
    for p in profiles:
        assert p["rho"] == config.RHO0
        assert abs(p["T"] - (1.0 - config.RHO0)) < 1e-12


def test_update_profiles_sets_trust(profiles):
    """update_profiles writes rho and T = 1 - rho, keeping bounds."""
    rho = np.linspace(0.0, 1.0, config.N_NODES)
    npf.update_profiles(profiles, rho)
    for i, p in enumerate(profiles):
        assert p["rho"] == rho[i]
        assert abs(p["T"] - (1.0 - rho[i])) < 1e-12
        assert 0.0 <= p["T"] <= 1.0
    # restore initial state so module-scoped fixture isn't left mutated
    npf.update_profiles(profiles, np.full(config.N_NODES, config.RHO0))


# --- Phase 1b: trust floor (Task 2) -----------------------------------------

def test_trust_floor_on_latched_nodes(profiles):
    """Latched-compromised nodes get T <= T_LATCH_FLOOR; others keep T = 1 - rho."""
    rho = np.full(config.N_NODES, 0.1)            # 1 - rho = 0.9 (well above floor)
    compromised = np.zeros(config.N_NODES)
    compromised[:5] = 1.0                          # latch the first five
    npf.update_profiles(profiles, rho, compromised)
    for i, p in enumerate(profiles):
        if i < 5:
            assert p["T"] <= config.T_LATCH_FLOOR + 1e-12
        else:
            assert abs(p["T"] - (1.0 - 0.1)) < 1e-12
        assert 0.0 <= p["T"] <= 1.0
    npf.update_profiles(profiles, np.full(config.N_NODES, config.RHO0))


def test_trust_default_path_unchanged(profiles):
    """With compromised=None, T = 1 - rho (the spec-faithful default)."""
    rho = np.linspace(0.0, 0.9, config.N_NODES)
    npf.update_profiles(profiles, rho, compromised=None)
    for i, p in enumerate(profiles):
        assert abs(p["T"] - (1.0 - rho[i])) < 1e-12
    npf.update_profiles(profiles, np.full(config.N_NODES, config.RHO0))


def test_trust_floor_only_lowers(profiles):
    """The floor never raises trust: a latched node with low rho still drops to floor."""
    rho = np.full(config.N_NODES, 0.05)            # 1 - rho = 0.95
    compromised = np.ones(config.N_NODES)
    npf.update_profiles(profiles, rho, compromised)
    assert all(p["T"] <= config.T_LATCH_FLOOR + 1e-12 for p in profiles)
    npf.update_profiles(profiles, np.full(config.N_NODES, config.RHO0))


# --- Phase 1b: runtime process state P (Task 1) -----------------------------

def test_compute_P_three_levels():
    """compute_P returns Emergency / Degraded / Normal on the documented triggers."""
    lo = np.full(config.N_NODES, 0.05)             # mean 0.05 < P_DEGRADED_RHO
    hi = np.full(config.N_NODES, 0.30)             # mean 0.30 >= P_DEGRADED_RHO
    # Emergency: previous pa above threshold (regardless of rho)
    assert npf.compute_P(lo, prev_pa=0.9) == config.P_EMERGENCY
    # Degraded: worm spreading, pa low
    assert npf.compute_P(hi, prev_pa=0.0) == config.P_DEGRADED
    # Normal: idle, pa low (and pa None at step 0)
    assert npf.compute_P(lo, prev_pa=0.0) == config.P_NORMAL
    assert npf.compute_P(lo, prev_pa=None) == config.P_NORMAL


def test_P_written_and_bounded(profiles):
    """update_profiles writes a P in [0,1] to every profile."""
    rho = np.full(config.N_NODES, 0.30)
    npf.update_profiles(profiles, rho, compromised=None, prev_pa=0.0)
    assert all(p["P"] == config.P_DEGRADED for p in profiles)
    assert all(0.0 <= p["P"] <= 1.0 for p in profiles)
    npf.update_profiles(profiles, np.full(config.N_NODES, config.RHO0))


# --- Phase 1b: IEC-weighted S_deny (Task 5) ---------------------------------

def test_S_deny_bounded_and_weighted(profiles):
    """S_deny in [0,1] and equals the documented 0.35/0.25/0.20/0.15/0.05 mix."""
    npf.update_profiles(profiles, np.full(config.N_NODES, config.RHO0),
                        compromised=None, prev_pa=0.0)  # P = Normal
    w = config.S_DENY_WEIGHTS
    for p in profiles:
        expected = (w["H"] * p["H_s"] + w["D"] * p["D_c"] + w["A"] * p["A_avail"]
                    + w["P"] * p["P"] + w["O"] * p["O_op"])
        assert abs(p["S_deny"] - expected) < 1e-12
        assert 0.0 <= p["S_deny"] <= 1.0


def test_S_deny_rises_with_P(profiles):
    """S_deny increases when the runtime phase escalates (P is its 0.15-weighted term)."""
    rho_idle = np.full(config.N_NODES, 0.05)
    npf.update_profiles(profiles, rho_idle, compromised=None, prev_pa=0.0)  # Normal
    normal = [p["S_deny"] for p in profiles]
    npf.update_profiles(profiles, rho_idle, compromised=None, prev_pa=0.9)  # Emergency
    emergency = [p["S_deny"] for p in profiles]
    # every node's S_deny rises by exactly 0.15*(P_EMERGENCY - P_NORMAL)
    delta = config.S_DENY_WEIGHTS["P"] * (config.P_EMERGENCY - config.P_NORMAL)
    for n, e in zip(normal, emergency):
        assert abs((e - n) - delta) < 1e-12
    npf.update_profiles(profiles, np.full(config.N_NODES, config.RHO0))


def test_S_deny_weights_sum_to_one():
    """The IEC weights sum to 1 (so S_deny stays in [0,1] for unit-interval inputs)."""
    assert abs(sum(config.S_DENY_WEIGHTS.values()) - 1.0) < 1e-12
