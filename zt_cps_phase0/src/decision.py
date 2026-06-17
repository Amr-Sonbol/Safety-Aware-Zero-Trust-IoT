"""Phase 1 safety-aware decision function and per-step simulation driver.

This is the project's contribution layer. For each node and step it chooses one of
the five actions (Full, Restricted, Read-Only, Safe-Mode, Deny) by minimizing a
weighted sum of a **security risk** term and a **safety/denial cost** term::

    A* = argmin_a [ alpha * R_sec(a) + beta * R_saf(a) ]
    R_sec(a) = (1 - T) * ASC * gamma_a      # exposure left to the attacker
    R_saf(a) = DC * delta_a                  # cost of degrading/denying the node

The chosen action set then drives one simulation tick through the **two channels**
of spec D1, reusing the frozen Phase 0 engine end to end:

* **Security channel (gamma_a -> pa / M4).** A compromised node's measurements are
  attacker-injectable only if its action keeps the C3 write path
  (``gamma_a >= C3_GAMMA_MIN``). With the Phase 1b coefficient (restricted
  ``gamma = 0.50``) this is **Full only**; Restricted, Read-Only, Safe-Mode and Deny
  all fall below the 0.6 cutoff and strip the write path. The action-gated
  *injectable* node set — not the raw compromised set — is fed to Phase 0
  :func:`attack_engine.compute_pa`.
* **Safety channel (O_a -> M7).** Only measurement rows whose owning node still
  reports (``O_a > 0``) stay in ``H_obs``; Safe-Mode keeps a deterministic
  ``SAFE_MODE_OBS_FRACTION`` of its rows, Deny keeps none. M7 reads ``H_obs``.

Denial (D3) is the **only** mechanism that changes ``B'``: nodes whose action is
``deny`` are hardened by ``HARDENING_DELTA = 0.40`` via Phase 0
:func:`policy_engine.apply_policy`. Soft actions leave ``B'`` unchanged.
"""

from __future__ import annotations

import numpy as np

from . import attack_engine as ae
from . import config
from . import policy_engine as pe


# ---------------------------------------------------------------------------- #
# Risk terms and action selection (spec §3)                                    #
# ---------------------------------------------------------------------------- #

def R_sec(profile: dict, action: str) -> float:
    """Security-risk term for taking ``action`` at ``profile``: ``(1-T)*ASC*gamma_a``.

    Larger when the node is less trusted (high ``1-T``), more attack-surface-critical
    (high ``ASC``), and retains more command authority (high ``gamma_a``).
    """
    gamma = config.ACTIONS[action]["gamma"]
    return (1.0 - float(profile["T"])) * float(profile["ASC"]) * gamma


def R_saf(profile: dict, action: str) -> float:
    """Safety/denial-cost term for ``action`` at ``profile``.

    Base form ``DC * delta_a`` — larger when denying a node that is costly to lose
    (high ``DC``) with a heavier action (high ``delta_a``).

    **Phase 1b runtime awareness.** The runtime process state ``P`` enters the
    denial cost so denial is treated as *cheaper* under active attack. There are two
    mutually-exclusive couplings (so ``P`` is never double-counted):

    * **IEC-weighted path (``config.USE_S_DENY`` True, Task 5).** The base cost is the
      IEC-weighted ``S_deny`` (which already contains ``P`` at weight 0.15), so no
      extra relief factor is applied:  ``R_saf = S_deny * delta_a``.
    * **Equal-weight path (``USE_S_DENY`` False, Tasks 1-3).** The base cost is ``DC``
      and ``P`` enters multiplicatively:
      ``R_saf = DC * (1 - P_COST_RELIEF * P) * delta_a``. ``P`` defaults to
      ``config.P_NORMAL`` when the field is absent (crafted unit-test fixtures).
    """
    spec = config.ACTIONS[action]
    delta = 1.0 - (spec["O"] + spec["C"]) / 2.0
    base = _safety_cost(profile)
    if config.USE_S_DENY and "S_deny" in profile:
        # P already weighted inside S_deny; no extra multiplicative relief.
        return base * delta
    p = float(profile.get("P", config.P_NORMAL))
    relief = 1.0 - config.P_COST_RELIEF * p
    return base * relief * delta


def _safety_cost(profile: dict) -> float:
    """Per-node safety/denial-cost scalar feeding :func:`R_saf`.

    Returns the IEC-weighted ``S_deny`` when :data:`config.USE_S_DENY` is True and the
    profile carries it (Task 5); otherwise the Phase 1 equal-weight denial criticality
    ``DC``. (When ``S_deny`` is used, the runtime ``P`` is already folded in at its
    0.15 weight, and :func:`R_saf` drops the multiplicative relief accordingly.)
    """
    if config.USE_S_DENY and "S_deny" in profile:
        return float(profile["S_deny"])
    return float(profile["DC"])


def select_action(profile: dict, alpha: float, beta: float) -> str:
    """Return the action minimizing ``alpha*R_sec + beta*R_saf`` for one node.

    Iterates actions in the fixed :data:`config.ACTIONS` order (Full -> Deny), so
    ties break deterministically toward the *least* restrictive action.

    Parameters
    ----------
    profile : dict
        A node profile (must carry ``T``, ``ASC``, ``DC``).
    alpha, beta : float
        Security vs. safety objective weights.

    Returns
    -------
    str
        The chosen action name (a key of :data:`config.ACTIONS`).
    """
    best_action = None
    best_cost = float("inf")
    for action in config.ACTIONS:  # insertion order: full, restricted, ..., deny
        cost = alpha * R_sec(profile, action) + beta * R_saf(profile, action)
        if cost < best_cost - 1e-15:
            best_cost = cost
            best_action = action
    return best_action


def apply_actions(decisions: dict[int, str], B: np.ndarray) -> np.ndarray:
    """Build ``B'`` from a decision set, applying D3 (only ``deny`` hardens ``B'``).

    Collects the nodes whose action is ``deny`` and hardens exactly those via Phase 0
    :func:`policy_engine.apply_policy` with ``HARDENING_DELTA``. Soft actions leave
    ``B'`` unchanged. With no denials this returns a copy of ``B``.

    Parameters
    ----------
    decisions : dict[int, str]
        Node-id -> action name for the current step.
    B : numpy.ndarray, shape (55, 55)

    Returns
    -------
    B_prime : numpy.ndarray, shape (55, 55)
    """
    deny_nodes = [node for node, action in decisions.items() if action == "deny"]
    return pe.apply_policy(B, deny_nodes, config.HARDENING_DELTA)


# ---------------------------------------------------------------------------- #
# The two D1 channels                                                          #
# ---------------------------------------------------------------------------- #

def injectable_nodes(
    decisions: dict[int, str],
    compromised: np.ndarray,
) -> np.ndarray:
    """Security channel: nodes whose compromised measurements an attacker can write.

    A node is injectable iff it is compromised **and** its action keeps the C3 write
    path (``gamma_a >= C3_GAMMA_MIN``). With the Phase 1b coefficient (restricted
    ``gamma = 0.50``) only Full clears the 0.6 cutoff; Restricted, Read-Only,
    Safe-Mode and Deny strip C3, so their measurements cannot carry an FDI even when
    the node is infected.

    Parameters
    ----------
    decisions : dict[int, str]
    compromised : numpy.ndarray, shape (55,)
        Latched binary compromise state.

    Returns
    -------
    numpy.ndarray, shape (55,)
        Binary node mask fed to :func:`attack_engine.compute_pa` in place of the raw
        compromised set.
    """
    keeps_c3 = np.array(
        [config.ACTIONS[decisions[i]]["gamma"] >= config.C3_GAMMA_MIN
         for i in range(len(compromised))],
        dtype=float,
    )
    return compromised * keeps_c3


def observed_rows(decisions: dict[int, str], A: np.ndarray) -> np.ndarray:
    """Safety channel: boolean mask of measurement rows still reported to the EMS.

    For each measurement row ``m`` owned by node ``i = argmax(A[m])`` (``A`` has one
    nonzero per row):

    * ``O_a == 1.0`` (Full/Restricted/Read-Only) -> keep the row;
    * ``O_a == SAFE_MODE_OBS_FRACTION`` (Safe-Mode) -> keep a deterministic fraction
      of that node's rows (the first ``round(O_a * count)`` in row order);
    * ``O_a == 0.0`` (Deny) -> drop the row.

    Parameters
    ----------
    decisions : dict[int, str]
    A : numpy.ndarray, shape (M, 55)

    Returns
    -------
    numpy.ndarray, shape (M,)
        Boolean mask; ``True`` where the row stays in ``H_obs``.
    """
    m = A.shape[0]
    owner = np.argmax(A, axis=1)  # (M,) owning node per row (one nonzero/row)
    keep = np.zeros(m, dtype=bool)

    # Group rows by owning node so Safe-Mode's fractional keep is deterministic.
    for node in np.unique(owner):
        rows = np.where(owner == node)[0]  # ascending row indices
        o_a = config.ACTIONS[decisions[int(node)]]["O"]
        if o_a >= 1.0:
            keep[rows] = True
        elif o_a <= 0.0:
            keep[rows] = False
        else:
            n_keep = int(round(o_a * len(rows)))
            keep[rows[:n_keep]] = True
    return keep


# ---------------------------------------------------------------------------- #
# One simulation step (spec §4)                                                #
# ---------------------------------------------------------------------------- #

def run_step(
    decisions: dict[int, str],
    rho: np.ndarray,
    compromised: np.ndarray,
    B: np.ndarray,
    H: np.ndarray,
    A: np.ndarray,
    C_targets: np.ndarray,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray, dict]:
    """Advance the worm/attack one tick under ``decisions`` and return a step record.

    Wires spec §4: (1) harden ``deny`` nodes -> ``B'``; (2) ``update_worm`` then
    ``sample_compromise`` (Phase 0); (3) security channel -> ``pa`` from the
    action-gated injectable set; (4) safety channel -> ``H_obs`` row mask.

    Parameters
    ----------
    decisions : dict[int, str]
        Per-node actions chosen *before* this tick (from the policy under test).
    rho : numpy.ndarray, shape (55,)
        Current infection probabilities (updated and returned).
    compromised : numpy.ndarray, shape (55,)
        Latched binary compromise state (updated and returned).
    B : numpy.ndarray, shape (55, 55)
        Baseline infection matrix (undefended; deny-hardening is applied here).
    H : numpy.ndarray, shape (M, N)
    A : numpy.ndarray, shape (M, 55)
    C_targets : numpy.ndarray, shape (n_fdi, N)
    rng : numpy.random.Generator
        Seeded RNG for the Bernoulli compromise draw.

    Returns
    -------
    rho_next : numpy.ndarray, shape (55,)
    compromised_next : numpy.ndarray, shape (55,)
    record : dict
        Per-step quantities for the metrics logger: ``decisions`` (copy), ``pa``,
        ``obs_mask`` (boolean row mask for M7), and the node arrays ``T``, ``DC``,
        ``ASC``, ``gamma``, ``delta`` (so M1/M2/M3/M6 need no re-derivation).
    """
    # 1. B' — only deny nodes harden it (D3).
    B_prime = apply_actions(decisions, B)

    # 2. Worm + latching compromise (Phase 0 engine, unchanged).
    rho_next = ae.update_worm(rho, B_prime)
    compromised_next = ae.sample_compromise(rho_next, compromised, rng)

    # 3. Security channel: action-gated injectable set -> pa (Phase 0 compute_pa).
    injectable = injectable_nodes(decisions, compromised_next)
    pa = ae.compute_pa(C_targets, H, A, injectable)

    # 4. Safety channel: observed-measurement row mask for M7.
    obs_mask = observed_rows(decisions, A)

    record = {
        "decisions": dict(decisions),
        "pa": pa,
        "obs_mask": obs_mask,
        "injectable": injectable,
        "compromised": compromised_next.copy(),
    }
    return rho_next, compromised_next, record
