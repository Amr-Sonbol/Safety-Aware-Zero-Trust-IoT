"""Tests for the Phase 1 decision function and the two D1 channels."""

from __future__ import annotations

import numpy as np
import pytest

from zt_cps_phase0.src import (
    attack_engine as ae,
    config,
    decision as dec,
    policy_engine as pe,
    power_system as ps,
    topology as tp,
)


def _profile(T: float, DC: float, ASC: float = 0.6, P: float = config.P_NORMAL) -> dict:
    """Minimal profile carrying just the fields select_action/run_step read."""
    return {"node_id": 0, "T": T, "DC": DC, "ASC": ASC, "P": P}


# --- select_action: the three spec cases ------------------------------------

def test_select_action_infected_low_dc_denies():
    """Infected (low T) + low denial-cost (low DC), security-weighted -> deny."""
    p = _profile(T=0.05, DC=0.1, ASC=0.9)
    assert dec.select_action(p, alpha=0.8, beta=0.2) == "deny"


def test_select_action_trusted_high_dc_full():
    """Trusted (high T) + high denial-cost (high DC) -> full (no reason to restrict)."""
    p = _profile(T=0.98, DC=0.95, ASC=0.9)
    assert dec.select_action(p, alpha=0.8, beta=0.2) == "full"


def test_select_action_safety_dominant_high_dc_not_deny():
    """Safety-dominant (high beta) + high DC -> never the full-denial action."""
    p = _profile(T=0.2, DC=0.95, ASC=0.9)
    assert dec.select_action(p, alpha=0.2, beta=0.8) != "deny"


def test_select_action_returns_known_action():
    """select_action always returns a valid action key for varied inputs."""
    for T in (0.0, 0.3, 0.6, 1.0):
        for DC in (0.0, 0.5, 1.0):
            for (a, b) in config.CONFIGS:
                assert dec.select_action(_profile(T, DC), a, b) in config.ACTIONS


def test_select_action_runtime_sensitive_to_P():
    """Changing ONLY the runtime process state P flips the chosen action (Task 1).

    This is the core "safety-aware at runtime" demonstration: with everything else
    held fixed, escalating from Normal to Emergency makes denial cheaper, so the
    decision becomes more willing to deny.
    """
    base = dict(T=0.2, DC=0.7, ASC=0.9)
    normal = dec.select_action(_profile(**base, P=config.P_NORMAL), 0.5, 0.5)
    emergency = dec.select_action(_profile(**base, P=config.P_EMERGENCY), 0.5, 0.5)
    assert normal != emergency
    assert normal == "read_only" and emergency == "deny"


# --- risk terms and delta ----------------------------------------------------

def test_risk_terms_match_formulas():
    """R_sec = (1-T)*ASC*gamma; R_saf = DC*(1-P_COST_RELIEF*P)*delta (Phase 1b)."""
    p = _profile(T=0.4, DC=0.7, ASC=0.5, P=config.P_NORMAL)
    relief = 1.0 - config.P_COST_RELIEF * config.P_NORMAL
    for action, spec in config.ACTIONS.items():
        delta = 1.0 - (spec["O"] + spec["C"]) / 2.0
        assert abs(dec.R_sec(p, action) - (1 - 0.4) * 0.5 * spec["gamma"]) < 1e-12
        assert abs(dec.R_saf(p, action) - 0.7 * relief * delta) < 1e-12


def test_R_saf_phase_relief_monotone():
    """Higher P → lower denial cost (emergency makes denial cheaper)."""
    pf = lambda P: _profile(T=0.4, DC=0.7, ASC=0.5, P=P)
    normal = dec.R_saf(pf(config.P_NORMAL), "deny")
    degraded = dec.R_saf(pf(config.P_DEGRADED), "deny")
    emergency = dec.R_saf(pf(config.P_EMERGENCY), "deny")
    assert normal > degraded > emergency >= 0.0


def test_R_saf_defaults_P_when_absent():
    """A profile without a P field is treated as P_NORMAL (back-compat)."""
    p = {"node_id": 0, "T": 0.4, "DC": 0.7, "ASC": 0.5}  # no P
    relief = 1.0 - config.P_COST_RELIEF * config.P_NORMAL
    assert abs(dec.R_saf(p, "deny") - 0.7 * relief * 1.0) < 1e-12


# --- apply_actions: only deny hardens B' (D3) -------------------------------

def test_apply_actions_only_deny_hardens():
    """apply_actions hardens exactly the deny nodes via Phase 0 apply_policy."""
    B = tp.build_B()
    decisions = {i: "full" for i in range(config.N_NODES)}
    decisions[3] = "deny"
    decisions[7] = "safe_mode"   # heavy soft action: must NOT harden B'
    decisions[9] = "deny"
    B_prime = dec.apply_actions(decisions, B)
    expected = pe.apply_policy(B, [3, 9], config.HARDENING_DELTA)
    assert np.array_equal(B_prime, expected)


def test_apply_actions_no_deny_is_copy_of_B():
    """With no deny actions, B' equals B (soft actions leave B' unchanged)."""
    B = tp.build_B()
    decisions = {i: "safe_mode" for i in range(config.N_NODES)}
    B_prime = dec.apply_actions(decisions, B)
    assert np.array_equal(B_prime, B)


# --- security channel: gating only lowers pa --------------------------------

@pytest.fixture(scope="module")
def model():
    net = ps.load_network()
    H, _, _ = ps.build_H(net)
    A = tp.build_A(H.shape[0])
    rng = np.random.default_rng(config.SEED)
    C = ae.generate_fdi_targets(H, rng)
    return H, A, C


def test_injectable_subset_of_compromised(model):
    """The injectable set never exceeds the compromised set; only `full` keeps C3.

    Phase 1b Task 4: `restricted` gamma was lowered to 0.50 (< C3_GAMMA_MIN=0.6), so
    it now strips the write path like read_only/safe_mode/deny. Only `full` keeps it.
    """
    _, _, _ = model
    compromised = np.ones(config.N_NODES)
    decisions = {i: "read_only" for i in range(config.N_NODES)}  # all strip C3
    inj = dec.injectable_nodes(decisions, compromised)
    assert np.all(inj == 0.0)
    decisions = {i: "restricted" for i in range(config.N_NODES)}  # now strips C3
    inj = dec.injectable_nodes(decisions, compromised)
    assert np.all(inj == 0.0)
    decisions = {i: "full" for i in range(config.N_NODES)}  # only full keeps C3
    inj = dec.injectable_nodes(decisions, compromised)
    assert np.all(inj == compromised)


def test_restricted_strips_write_path(model):
    """Phase 1b Task 4: a compromised node under `restricted` is now NOT injectable."""
    _, _, _ = model
    compromised = np.zeros(config.N_NODES)
    compromised[5] = 1.0
    # full → injectable; restricted → not injectable (gamma 0.50 < 0.6)
    full_dec = {i: "full" for i in range(config.N_NODES)}
    restr_dec = {i: "restricted" for i in range(config.N_NODES)}
    assert dec.injectable_nodes(full_dec, compromised)[5] == 1.0
    assert dec.injectable_nodes(restr_dec, compromised)[5] == 0.0
    assert config.ACTIONS["restricted"]["gamma"] < config.C3_GAMMA_MIN


def test_gating_does_not_increase_pa(model):
    """pa under the action-gated injectable set <= pa under the raw compromised set."""
    H, A, C = model
    compromised = np.ones(config.N_NODES)
    pa_raw = ae.compute_pa(C, H, A, compromised)
    # Read-Only everywhere strips every write path -> injectable empty -> pa 0.
    decisions = {i: "read_only" for i in range(config.N_NODES)}
    inj = dec.injectable_nodes(decisions, compromised)
    pa_gated = ae.compute_pa(C, H, A, inj)
    assert pa_gated <= pa_raw + 1e-12
    assert pa_gated == 0.0


# --- safety channel: observed-row mask --------------------------------------

def test_observed_rows_full_keeps_all(model):
    """Full action everywhere keeps every measurement row."""
    _, A, _ = model
    decisions = {i: "full" for i in range(config.N_NODES)}
    keep = dec.observed_rows(decisions, A)
    assert keep.all()


def test_observed_rows_deny_drops_owned(model):
    """Denying a node drops exactly the rows it owns."""
    _, A, _ = model
    owner = np.argmax(A, axis=1)
    target = int(owner[0])
    decisions = {i: "full" for i in range(config.N_NODES)}
    decisions[target] = "deny"
    keep = dec.observed_rows(decisions, A)
    dropped = np.where(~keep)[0]
    assert set(dropped) == set(np.where(owner == target)[0])
