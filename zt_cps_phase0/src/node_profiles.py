"""Phase 1 node profiles: the fixed per-node safety/security attributes.

Each of the 55 cyber nodes carries a *fixed* profile (computed once from the
Phase 0 topology) plus per-step dynamic fields: the infection probability ``rho``,
the trust ``T``, and the runtime process state ``P``. The profile supplies the
inputs to the safety-aware decision function (:mod:`decision`):

* ``H_s``  — hardware safety score from the node's SIL (IEC 61508 Table 2).
* ``D_c``  — data criticality of the node (FENG2023 I_sec).
* ``R_d``  — measurement redundancy (see the synthetic-``A`` caveat below).
* ``ASC_r``— relative attack-surface connectivity = ``degree(node)/max_degree(B)``.
* ``ASC``  — attack-surface criticality = ``0.5*D_c + 0.5*ASC_r``.
* ``DC``   — denial criticality = ``(H_s + D_c + R_d)/3`` (cost of denying the node).

Phase 1b dynamic fields
-----------------------
* ``T``  — trust. Default ``1 - rho`` (mean-field); **once a node latches
  compromised** its trust is floored to ``config.T_LATCH_FLOOR`` so the decision
  function has usable range (Task 2). The mean-field ``rho`` saturates ~0.53, so
  without this floor the safety-leaning configs never restrict/deny.
* ``P``  — runtime process state in [0,1] (Task 1): a global operational-phase
  scalar (Normal 0.2 / Degraded 0.6 / Emergency 1.0) keyed to the worm/attack
  phase. It makes the *denial cost* phase-aware — denial is cheaper under active
  attack — via :func:`decision.R_saf`. This is the mechanism that makes the score
  genuinely "safety-*aware* at runtime".

R_d is synthetic (Assumption A2)
--------------------------------
``R_d = 1 - max_{j!=i} coverage(j->i)`` with
``coverage(j->i) = |buses(j) ∩ buses(i)| / |buses(i)|`` is only meaningful if ``A``
is a real node->bus map. Phase 0's :func:`topology.build_A` is a synthetic
round-robin placeholder in which distinct nodes own **disjoint** measurement sets,
so ``coverage(j->i) = 0`` for every ``j != i`` and the formula degenerates. We
therefore use a documented role-based surrogate and flag it:

* sensor nodes (own >=1 measurement under ``A``)  -> ``R_d = 1.0`` (no real backup);
* non-sensor nodes (own 0 measurements)           -> ``R_d = 0.0`` (nothing to lose).

Every profile sets ``R_d_synthetic = True``. The redundancy axis is exercised for
sensitivity by ablation ABL-4, not treated as a validated redundancy map. Build a
real ``A`` from Fig. 5 to replace this.
"""

from __future__ import annotations

import numpy as np

from . import config
from . import topology as tp


# Fields whose value must lie in the unit interval [0, 1] (asserted on build/update).
_UNIT_FIELDS = (
    "H_s", "D_c", "R_d", "ASC_r", "ASC", "DC", "A_avail", "O_op",
    "rho", "T", "P", "S_deny",
)


def _assert_unit(profile: dict, fields: tuple[str, ...] = _UNIT_FIELDS) -> None:
    """Assert the named numeric fields of ``profile`` lie in ``[0, 1]``."""
    for f in fields:
        if f in profile:
            v = float(profile[f])
            assert 0.0 <= v <= 1.0, (
                f"node {profile.get('node_id')} field {f}={v} not in [0,1]"
            )


def _s_deny(h_s: float, d_c: float, a_avail: float, p: float, o_op: float) -> float:
    """IEC-weighted denial cost (Task 5): ``0.35 H + 0.25 D + 0.20 A + 0.15 P + 0.05 O``.

    Each input is in [0,1] and the weights sum to 1, so the result is in [0,1]. ``P``
    is the only dynamic input, so ``S_deny`` is refreshed every step by
    :func:`update_profiles`.
    """
    w = config.S_DENY_WEIGHTS
    return w["H"] * h_s + w["D"] * d_c + w["A"] * a_avail + w["P"] * p + w["O"] * o_op


def build_node_profiles(
    B: np.ndarray,
    A: np.ndarray,
    classes: dict[int, str],
) -> list[dict]:
    """Build the fixed profile for every node from the Phase 0 topology.

    Parameters
    ----------
    B : numpy.ndarray, shape (55, 55)
        The Phase 0 infection adjacency matrix (:func:`topology.build_B`).
    A : numpy.ndarray, shape (M, 55)
        The Phase 0 measurement-to-sensor map (:func:`topology.build_A`). Used only
        to decide which nodes collect measurements (synthetic ``R_d``; see module
        docstring).
    classes : dict[int, str]
        Node-id -> device-class label (:func:`topology.assign_classes`).

    Returns
    -------
    list[dict]
        One profile dict per node, index ``i`` == ``node_id`` ``i``. Each holds
        ``node_id, class, H_s, D_c, R_d, R_d_synthetic, ASC_r, ASC, DC, rho, T, P``.
        ``rho``/``T``/``P`` are initialized to ``RHO0`` / ``1 - RHO0`` / ``P_NORMAL``
        and updated each step by :func:`update_profiles`.

    Raises
    ------
    AssertionError
        If the topology shapes are inconsistent or any unit-interval field is out
        of range.
    """
    n = config.N_NODES
    assert B.shape == (n, n), f"B shape {B.shape} != ({n},{n})"
    assert A.shape[1] == n, f"A has {A.shape[1]} columns, expected {n}"
    assert len(classes) == n, f"{len(classes)} class labels != {n} nodes"

    degree = B.sum(axis=1)
    max_degree = float(degree.max())
    assert max_degree > 0.0, "B has no edges (max degree 0)"

    # A node "collects measurements" iff some row of A maps to it (column sum > 0).
    collects = A.sum(axis=0) > 0  # shape (55,), bool

    profiles: list[dict] = []
    for node in range(n):
        cls = classes[node]
        h_s = config.SIL_MAP[config.SIL_BY_CLASS[cls]]
        d_c = config.D_C_BY_CLASS[cls]
        asc_r = float(degree[node]) / max_degree

        # Synthetic, role-based redundancy (Assumption A2 — see module docstring).
        r_d = 1.0 if bool(collects[node]) else 0.0

        asc = 0.5 * d_c + 0.5 * asc_r
        dc = (h_s + d_c + r_d) / 3.0

        # Static per-class proxies for the IEC-weighted S_deny (Task 5). Documented
        # stand-ins, NOT live models (see config).
        a_avail = config.AVAIL_BY_CLASS[cls]
        o_op = config.OP_IMPACT_BY_CLASS[cls]

        profile = {
            "node_id": node,
            "class": cls,
            "H_s": h_s,
            "D_c": d_c,
            "R_d": r_d,
            "R_d_synthetic": True,
            "ASC_r": asc_r,
            "ASC": asc,
            "DC": dc,
            "A_avail": a_avail,
            "O_op": o_op,
            "rho": config.RHO0,
            "T": 1.0 - config.RHO0,
            "P": config.P_NORMAL,   # runtime process state; updated each step
            # S_deny is dynamic (depends on P); initialized here, refreshed each step.
            "S_deny": _s_deny(h_s, d_c, a_avail, config.P_NORMAL, o_op),
        }
        _assert_unit(profile)
        profiles.append(profile)

    assert len(profiles) == n, f"built {len(profiles)} profiles != {n}"
    return profiles


def compute_P(rho: np.ndarray, prev_pa: float | None) -> float:
    """Compute the runtime process-state scalar ``P`` in [0,1] (Phase 1b Task 1).

    A documented three-level rule keyed to the worm/attack phase, using state the
    simulation already has:

    * **Emergency** ``P = P_EMERGENCY`` if the previous step's ``pa`` exceeds
      ``P_EMERGENCY_PA`` (FDI is succeeding *now*);
    * **Degraded** ``P = P_DEGRADED`` if mean infection ``rho.mean()`` is at least
      ``P_DEGRADED_RHO`` (the worm is actively spreading);
    * **Normal** ``P = P_NORMAL`` otherwise (idle / early).

    ``prev_pa`` is ``None`` only at the very first step (no attack has run yet), in
    which case the emergency test is skipped.

    Parameters
    ----------
    rho : numpy.ndarray, shape (55,)
        Current mean-field infection probabilities.
    prev_pa : float or None
        The bypass probability from the *previous* step (None at step 0).

    Returns
    -------
    float
        The process-state level (one of the three configured values).
    """
    if prev_pa is not None and float(prev_pa) > config.P_EMERGENCY_PA:
        return config.P_EMERGENCY
    if float(rho.mean()) >= config.P_DEGRADED_RHO:
        return config.P_DEGRADED
    return config.P_NORMAL


def update_profiles(
    profiles: list[dict],
    rho: np.ndarray,
    compromised: np.ndarray | None = None,
    prev_pa: float | None = None,
) -> None:
    """Write the per-step dynamic fields ``rho``, ``T``, and ``P``.

    Mutates each profile in place. The fixed fields (class, H_s, D_c, R_d, ASC_r,
    ASC, DC) are untouched. The dynamic fields:

    * ``rho`` = the supplied mean-field infection probability.
    * ``T`` = ``1 - rho`` by default; **if ``compromised`` is given and the node has
      latched compromised**, ``T = min(1 - rho, config.T_LATCH_FLOOR)`` (Task 2).
      Passing ``compromised=None`` keeps the spec-faithful ``T = 1 - rho`` (used by
      back-compatible callers and the un-blended default path).
    * ``P`` = :func:`compute_P` of the current ``rho`` and ``prev_pa`` — a single
      global phase scalar written to every profile (Task 1).

    Parameters
    ----------
    profiles : list[dict]
        The profiles from :func:`build_node_profiles`.
    rho : numpy.ndarray, shape (55,)
        Current infection probabilities (from :func:`attack_engine.update_worm`).
    compromised : numpy.ndarray, shape (55,), optional
        Latched binary compromise state. If given, latched nodes get the trust
        floor (Task 2 blend); if None, ``T = 1 - rho`` (default path).
    prev_pa : float, optional
        Previous step's bypass probability, used by :func:`compute_P`. None at the
        first step.

    Raises
    ------
    AssertionError
        If ``rho`` is the wrong length or yields an out-of-range dynamic field.
    """
    assert len(rho) == len(profiles), (
        f"rho length {len(rho)} != {len(profiles)} profiles"
    )
    if compromised is not None:
        assert len(compromised) == len(profiles), (
            f"compromised length {len(compromised)} != {len(profiles)} profiles"
        )
    p_level = compute_P(rho, prev_pa)
    for i, profile in enumerate(profiles):
        r = float(rho[i])
        profile["rho"] = r
        t = 1.0 - r
        if compromised is not None and compromised[i] > 0:
            t = min(t, config.T_LATCH_FLOOR)
        profile["T"] = t
        profile["P"] = p_level
        # Refresh the IEC-weighted denial cost (P is its only dynamic input).
        profile["S_deny"] = _s_deny(
            profile["H_s"], profile["D_c"], profile["A_avail"],
            p_level, profile["O_op"],
        )
        _assert_unit(profile, ("rho", "T", "P", "S_deny"))
