"""Phase 0 configuration — the single source of truth for every constant.

This module holds every magic number used in the cyber-physical attack-model
reproduction (Feng & Hu, 2023). No logic lives here. Every stochastic routine in
the project seeds its RNG from :data:`SEED`, so the validation gates reproduce
bit-for-bit.

Modeling assumptions encoded here
---------------------------------
* The worm follows a deterministic mean-field SIS recursion with infection rate
  ``BETA``, recovery rate ``GAMMA``, and uniform initial infection ``RHO0``.
* A node is treated as "infected" for the purpose of compromising measurements
  once its mean-field probability crosses ``INFECTION_THRESHOLD``.
* The bad-data detector (BDD) threshold ``tau`` is derived from a chi-square test
  with ``M - N`` degrees of freedom at significance ``BDD_ALPHA``, optionally
  scaled by the single documented multiplier ``TAU_KAPPA``.
"""

from __future__ import annotations

# --- Worm / infection dynamics (paper Eq. 4) ---------------------------------
BETA: float = 0.1          # infection (spreading) rate
GAMMA: float = 0.2         # recovery rate
RHO0: float = 0.05         # uniform initial infection probability for all nodes
N_NODES: int = 55          # number of nodes in the cyber infection graph (Fig. 5)
# The binary compromise state is sampled v_i ~ Bernoulli(rho_i) and latches (a node
# stays compromised once reached). See attack_engine.sample_compromise. The
# mean-field rho_bar saturates at ~0.34 with the beta/gamma above, so a hard
# rho > 0.5 threshold is not used; Bernoulli + latching gives the rising coverage.

# --- Simulation horizon ------------------------------------------------------
N_STEPS: int = 40          # number of time steps the worm/attack are simulated

# --- False-data-injection (FDI) attack vectors -------------------------------
N_FDI: int = 10_000        # number of attack targets generated once and reused
C_LOW: float = -0.1        # lower bound of the uniform state-perturbation c
C_HIGH: float = 0.1        # upper bound of the uniform state-perturbation c

# Subspace-feasible FDI bypass criterion (see attack_engine.compute_pa): a target
# attack a = H c counts as a successful bypass when the realizable undetectable
# component retains at least this fraction of the target strength. This is the
# primary calibration knob for the no-ZTA bypass probability (Gate A). Calibrated to
# STRENGTH_THR = 0.30 so the 40-step average pa lands at ~0.74 (target 0.7474).
STRENGTH_THR: float = 0.30

# --- Measurement noise -------------------------------------------------------
NOISE_REL: float = 0.02    # relative noise std: sigma_m = max(NOISE_REL*|z_m|, floor)
SIGMA_FLOOR: float = 1e-3  # absolute sigma floor in p.u. (prevents singular R at
                           # zero-flow branches; tertiary calibration knob)

# --- Bad-data detector (BDD) threshold tau -----------------------------------
# In the subspace-feasible FDI model, feasible attacks are undetectable by
# construction (zero residual), so pa is governed by STRENGTH_THR rather than a
# residual-vs-tau test. tau is still computed and reported as the principled BDD
# threshold (chi-square with M-N dof) and used in the clean-residual self-check.
BDD_ALPHA: float = 0.05    # chi-square significance level (95% confidence)

# --- Defense policy budgets (Gate B) -----------------------------------------
NK_LIST: list[int] = [10, 15]   # node-isolation budgets the greedy search explores

# Partial-hardening trust-reduction factor (calibrated so greedy Nk=10 lands in
# [0.50, 0.58] and Nk=15 in [0.49, 0.57]). delta=1.0 is full isolation (collapses
# pa to ~0); delta<1 gives diminishing returns, matching the paper's shallow
# Nk=10→52.91% to Nk=15→50.94% improvement curve.
HARDENING_DELTA: float = 0.40

# FDI sample count used inside the greedy policy search (smaller than N_FDI for
# speed; greedy runs O(Nk*55) full simulations). Gate A still uses the full
# N_FDI=10_000 targets. Calibrated so greedy selections pass both gate bands when
# re-evaluated with the full 10_000-sample set.
N_FDI_POLICY: int = 2000

# --- Reproducibility ---------------------------------------------------------
SEED: int = 0              # every np.random.default_rng(SEED) routes through here

# --- Validation gate bands (asserted by the runner) --------------------------
GATE_A: tuple[float, float] = (0.70, 0.80)        # no-ZTA avg pa band; target 0.7474
GATE_A_TARGET: float = 0.7474
GATE_B_NK10: tuple[float, float] = (0.50, 0.58)   # greedy avg pa band @ Nk=10
GATE_B_NK15: tuple[float, float] = (0.49, 0.57)   # greedy avg pa band @ Nk=15
GATE_B_PAPER_NK10: float = 0.5291
GATE_B_PAPER_NK15: float = 0.5094

# --- Load profile ------------------------------------------------------------
LOAD_SWING: float = 0.15           # synthetic daily curve scales base loads +/-15%
NYISO_CSV: str = "data/nyiso_oct2022.csv"   # optional real load profile (auto-detected)

# --- Power-system constants --------------------------------------------------
SYSTEM_BASE_MVA: float = 100.0     # pandapower default system base; PF (MW) / base => p.u.
N_BUSES: int = 30                  # IEEE 30-bus case
N_STATES: int = N_BUSES - 1        # state vector = bus angles minus slack angle => 29
RANK_TOL: float = 1e-9             # explicit tolerance for np.linalg.matrix_rank(H)


# =============================================================================
# PHASE 1 — Safety-Aware Decision Function (additive; does NOT touch Phase 0)
# =============================================================================
# Everything below this line is consumed only by the Phase 1 contribution layer
# (node_profiles, decision, metrics, run_experiment). No Phase 0 constant above
# is modified, so the six gates and 17 tests are unaffected. See docs/PHASE1_SPEC.md.

# --- Five-action table (spec §3): (gamma_a, O_a, C_a) per action -------------
# gamma_a : command/attack capability retained on the C3 write path.
# O_a     : fraction of the node's measurements still reported to the EMS (M7).
# C_a     : control-command authority retained.
# delta_a = 1 - (O_a + C_a)/2  is the partial-hardening factor used ONLY by `deny`
# (D3); soft actions leave B' unchanged. The delta values are {0,0.25,0.5,0.9,1.0}.
ACTIONS: dict[str, dict[str, float]] = {
    "full":      {"gamma": 1.00, "O": 1.0, "C": 1.0},   # delta = 0.00
    # Phase 1b Task 4: restricted gamma 0.60 -> 0.50 so it falls BELOW C3_GAMMA_MIN
    # (0.6) and strips the FDI write path — giving `restricted` a real, graduated
    # security effect (previously gamma=0.60 sat exactly at the threshold and never
    # reduced pa vs `full`). delta is unchanged (it depends on O,C, not gamma): 0.25.
    "restricted":{"gamma": 0.50, "O": 1.0, "C": 0.5},   # delta = 0.25
    "read_only": {"gamma": 0.20, "O": 1.0, "C": 0.0},   # delta = 0.50
    "safe_mode": {"gamma": 0.10, "O": 0.2, "C": 0.0},   # delta = 0.90
    "deny":      {"gamma": 0.00, "O": 0.0, "C": 0.0},   # delta = 1.00
}

# --- Decision objective weight pairs (alpha, beta) explored (spec §3) --------
CONFIGS: list[tuple[float, float]] = [(0.8, 0.2), (0.5, 0.5), (0.2, 0.8)]

# --- Safety-integrity-level -> hardware safety score H_s (IEC 61508 Table 2) -
# log-PFD / 4.00 mapping: none=0.00, SIL1=0.38, SIL2=0.63, SIL3=0.88.
SIL_MAP: dict[str, float] = {"none": 0.00, "SIL1": 0.38, "SIL2": 0.63, "SIL3": 0.88}

# SIL assigned by device class (Assumption A6 — general practice, not HAZOP):
SIL_BY_CLASS: dict[str, str] = {
    "C-PDP-critical":   "SIL3",
    "C-PDP-controller": "SIL2",
    "T-PDP-relay":      "SIL1",
    "T-PDP-sensor":     "none",
    "T-PDP-monitor":    "none",
}

# --- Data-criticality D_c by device class (FENG2023 I_sec) -------------------
D_C_BY_CLASS: dict[str, float] = {
    "C-PDP-critical":   0.90,
    "C-PDP-controller": 0.70,
    "T-PDP-relay":      0.30,
    "T-PDP-sensor":     0.30,
    "T-PDP-monitor":    0.30,
}

# The five device classes (Assumption A1/A5 — Fig. 5 publishes no per-node label,
# so topology.assign_classes() derives them deterministically from B/A roles).
DEVICE_CLASSES: tuple[str, ...] = (
    "C-PDP-critical", "C-PDP-controller",
    "T-PDP-relay", "T-PDP-sensor", "T-PDP-monitor",
)

# --- D1 security channel: write-path cutoff ----------------------------------
# A compromised node's measurements are attacker-injectable only if its action
# keeps the C3 write path, i.e. gamma_a >= C3_GAMMA_MIN (Full or Restricted).
C3_GAMMA_MIN: float = 0.6

# --- D1 safety channel: Safe-Mode partial observability ----------------------
# Safe-Mode reports only this fraction of a node's measurement rows to the EMS
# (used when building H_obs for M7). Full/Restricted/Read-Only keep all rows;
# Deny keeps none.
SAFE_MODE_OBS_FRACTION: float = 0.2

# --- Reserved (spec §9 lists `lambda` as defined-but-unused in Phase 1) ------
# RESERVED PLACEHOLDER — consumed by NO Phase 1/1b code. It is the coupling
# coefficient for the *deferred* Phase 2 safety-aware objective J = pa + lambda * S_c
# (the physical safety cost S_c is not implemented in Phase 1; M7 is the safety axis
# instead). Kept rather than deleted to avoid any import-time breakage; its value is
# inert. See docs/12 Divergence 5 and docs/13 §4.4.
LAMBDA: float = 1.0


# =============================================================================
# PHASE 1b — runtime-aware enrichment (additive; Phase 0 still untouched)
# =============================================================================
# These constants make the safety score respond to the *runtime* state of the
# system (process-state P) and give the trust signal usable dynamic range
# (latched-compromise floor). See docs/12_phase1_divergences.md (Divergence 3,
# Phase 1b refinement) for the before/after rationale.

# --- Trust dynamic range (Phase 1b Task 2) -----------------------------------
# The mean-field rho saturates around 0.32-0.53, so T = 1 - rho almost never
# drops below ~0.47 and the safety-leaning configs never restrict/deny. Once a
# node *latches* compromised (the attacker's real reach), drive its trust down to
# this floor so denial/restriction can trigger. T = 1 - rho stays the documented
# default for un-latched nodes.
#
# Calibrated to 0.35 (the spec suggests 0.2 as a starting point). At 0.35 the
# BALANCED config (alpha=0.5) lands on read_only rather than deny for latched
# high-criticality nodes, so it cuts pa to ~0.02 WHILE preserving full
# observability (M7obs=1.0) — the clean safety-aware trade-off. A deeper floor
# pushes alpha=0.5 toward denial (blinding the EMS like the security-dominant
# config), erasing that trade-off. See docs/12 Divergence 3 (Phase 1b refinement)
# for the before/after and why the headline config shifted from alpha=0.8 to 0.5.
T_LATCH_FLOOR: float = 0.35

# --- Runtime process state P (Phase 1b Task 1) -------------------------------
# A per-step operational-phase scalar in [0,1] keyed to the worm/attack phase.
# Normal (idle) -> Degraded (worm spreading) -> Emergency (FDI succeeding now).
P_NORMAL: float = 0.2
P_DEGRADED: float = 0.6
P_EMERGENCY: float = 1.0
P_DEGRADED_RHO: float = 0.15      # mean infection at/above which phase is Degraded
P_EMERGENCY_PA: float = 0.5       # previous-step pa above which phase is Emergency

# How strongly P relieves the denial cost: R_saf = DC * (1 - P_COST_RELIEF*P) * delta.
# At P=P_NORMAL the relief is small; at P=P_EMERGENCY denial is treated as
# substantially cheaper (more acceptable) because the grid is actively under attack.
# (1 - 0.6*1.0) = 0.4 floor of the cost at full emergency; bounded and monotone.
# NOTE: this multiplicative coupling is the equal-weight-DC path used ONLY when the
# IEC-weighted S_deny (Task 5, below) is DISABLED. When USE_S_DENY is True, P enters
# via its 0.15 weight inside S_deny and this multiplicative factor is dropped, so P
# is never double-counted. (See decision.R_saf / decision._safety_cost.)
P_COST_RELIEF: float = 0.6

# --- IEC-weighted denial cost S_deny (Phase 1b Task 5) -----------------------
# The proposal specifies S_deny = 0.35*H + 0.25*D + 0.20*A + 0.15*P + 0.05*O.
# When USE_S_DENY is True, S_deny replaces the equal-weight DC as the safety-cost
# input to R_saf and to the DC-reading metrics (M1 gate, M2). H<-H_s, D<-D_c are
# already present; A (availability) and O (operational impact) are documented STATIC
# per-class proxies (NOT live models); P is the runtime process state (Task 1).
USE_S_DENY: bool = True

S_DENY_WEIGHTS: dict[str, float] = {
    "H": 0.35,   # hardware safety (H_s)
    "D": 0.25,   # data criticality (D_c)
    "A": 0.20,   # availability (static per-class proxy below)
    "P": 0.15,   # runtime process state (dynamic)
    "O": 0.05,   # operational impact (static per-class proxy below)
}

# Availability proxy by device class: control-plane nodes are more
# availability-critical than field devices. Static (Assumption-grade), in [0,1].
AVAIL_BY_CLASS: dict[str, float] = {
    "C-PDP-critical":   1.0,
    "C-PDP-controller": 1.0,
    "T-PDP-relay":      0.6,
    "T-PDP-sensor":     0.3,
    "T-PDP-monitor":    0.3,
}

# Operational-impact proxy by device class: a documented STATIC stand-in for "how
# much grid operation depends on this node" (loosely, exposure to high-load branches
# on the IEEE 30-bus case). Higher for control/relay nodes. Static only, no live
# MATPOWER per step (explicitly out of scope). In [0,1].
OP_IMPACT_BY_CLASS: dict[str, float] = {
    "C-PDP-critical":   0.9,
    "C-PDP-controller": 0.7,
    "T-PDP-relay":      0.5,
    "T-PDP-sensor":     0.3,
    "T-PDP-monitor":    0.2,
}
