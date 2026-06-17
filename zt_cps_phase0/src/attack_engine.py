"""Attack engine: worm propagation, FDI feasibility, and bypass probability.

This module reproduces the dynamic attack model of Feng & Hu (2023): the worm
infection recursion (paper Eq. 4), the construction and *feasibility* of false-data-
injection (FDI) attacks given a compromised measurement set, and the bad-data-
detector (BDD) bypass probability ``pa`` (paper Eq. 7, reproduced in intent).

Resolved modeling decisions (documented because they diverge from the spec text)
--------------------------------------------------------------------------------
The spec's literal recipe -- mask a single pre-drawn structured vector ``a = Hc`` by
the infection state and test ``||z + a_eff - H x_hat|| <= tau`` -- produces a
*non-monotonic, U-shaped* ``pa`` versus compromise curve (an attack bypasses when
*no* measurement is compromised or when *all* are, but is loudly detected in
between, because slicing an unobservable vector destroys its unobservability). That
cannot reproduce the paper's reported behaviour (``pa`` rising from ~0 to ~74.74% as
the worm saturates). Two reconciliations were chosen and validated end-to-end:

1. **Subspace-feasible FDI.** A measurement attack is undetectable iff it lies in
   the column space of ``H`` (``a = Hc``). When the attacker can only alter the
   *compromised* measurements ``S`` (mask = 1), the realizable undetectable attacks
   are exactly ``a = Hc`` whose components on the *uncompromised* measurements
   vanish -- i.e. ``c`` in the null space of ``H`` restricted to the uncompromised
   rows. The feasible-``c`` subspace grows monotonically as ``S`` grows. For a
   random target attack direction, ``pa`` counts the fraction for which a feasible
   undetectable attack retains at least ``STRENGTH_THR`` of the target's strength
   (the projection-ratio test). This rises smoothly from 0 (nothing compromised) to
   1 (everything compromised). See :func:`compute_pa`.

2. **Stochastic Bernoulli infection with latching.** The mean-field ``rho`` with the
   spec's ``beta=0.1, gamma=0.2`` saturates at ``rho_bar ~ 0.34``, so a hard
   ``rho > 0.5`` threshold almost never fires. Instead each step samples
   ``v_i ~ Bernoulli(rho_i)`` (the MC variant the spec allows), and a node, once
   sampled compromised, *latches* (malware persists). The compromised set therefore
   accumulates toward full coverage over the 40 steps, matching the paper's rising
   infection trend while keeping ``beta``/``gamma`` exactly as specified.

The worm recursion itself (:func:`update_worm`) is the deterministic mean-field SIS
model exactly as specified; the Bernoulli sampling and latching live in the masking
step (:func:`sample_compromise`), not in the worm dynamics.
"""

from __future__ import annotations

import numpy as np

from . import config


def update_worm(
    rho: np.ndarray,
    B_prime: np.ndarray,
    beta: float = config.BETA,
    gamma: float = config.GAMMA,
) -> np.ndarray:
    """Advance the deterministic mean-field SIS worm by one step (paper Eq. 4).

    For each node ``i``::

        rho_new[i] = clip( rho[i]
                           + (1 - rho[i]) * beta * sum_j B'[i,j] * rho[j]
                           - rho[i] * gamma,
                           0, 1 )

    ``B_prime @ rho`` is exactly ``sum_j B'[i,j] * rho[j]`` per node. This is a
    *mean-field* model: ``rho`` holds infection probabilities, not binary states. It
    is deliberately not Monte Carlo and takes no ``n_monte_carlo`` argument.

    Parameters
    ----------
    rho : numpy.ndarray, shape (55,)
        Current infection probabilities.
    B_prime : numpy.ndarray, shape (55, 55)
        (Possibly defended) infection adjacency matrix.
    beta, gamma : float
        Infection (spreading) and recovery rates.

    Returns
    -------
    rho_new : numpy.ndarray, shape (55,)
        Updated infection probabilities, clipped to ``[0, 1]``.
    """
    pressure = B_prime @ rho
    rho_new = rho + (1.0 - rho) * beta * pressure - rho * gamma
    return np.clip(rho_new, 0.0, 1.0)


def sample_compromise(
    rho: np.ndarray,
    compromised: np.ndarray,
    rng: np.random.Generator,
) -> np.ndarray:
    """Update the latching binary compromise state from infection probabilities.

    Samples ``v_i ~ Bernoulli(rho_i)`` for each node and OERs it into the running
    ``compromised`` state, so a node stays compromised once the worm has reached it
    (malware persistence). This is the stochastic infection-state variant: the
    instantaneous mean-field ``rho`` caps below 0.5, but the accumulated compromised
    set grows toward full coverage over the simulation horizon.

    Parameters
    ----------
    rho : numpy.ndarray, shape (55,)
        Current infection probabilities.
    compromised : numpy.ndarray, shape (55,)
        Running binary compromise state (0/1).
    rng : numpy.random.Generator
        Seeded RNG for the Bernoulli draws.

    Returns
    -------
    numpy.ndarray, shape (55,)
        Updated (latched) binary compromise state.
    """
    v = (rng.random(rho.shape) < rho).astype(float)
    return np.maximum(compromised, v)


def measurement_mask(A: np.ndarray, compromised: np.ndarray) -> np.ndarray:
    """Map the node compromise state to a per-measurement compromise mask.

    The mask is ``A @ v`` clamped to ``{0, 1}``: measurement ``m`` is compromisable
    iff its (unique) collecting sensor node is compromised.

    Parameters
    ----------
    A : numpy.ndarray, shape (M, 55)
    compromised : numpy.ndarray, shape (55,)

    Returns
    -------
    mask : numpy.ndarray, shape (M,)
        1.0 where the measurement can be manipulated, else 0.0.

    Notes
    -----
    The mapping uses ``A @ v``, not ``A^T v`` as written in the paper. With ``A`` of
    shape ``(M, 55)`` and ``v`` of shape ``(55,)``, ``A @ v -> (M,)`` gives, per
    measurement ``m``, the compromise state of ``m``'s unique collecting node (``A``
    has exactly one nonzero per row). ``A^T v`` would land in node space ``R^55``
    (wrong direction and shape).
    """
    return (A @ compromised > 0).astype(float)


def generate_fdi_targets(
    H: np.ndarray,
    rng: np.random.Generator,
    n_fdi: int = config.N_FDI,
) -> np.ndarray:
    """Generate ``n_fdi`` random target state-perturbations ``c`` for FDI attacks.

    Each row ``c ~ U(C_LOW, C_HIGH)^N`` defines a desired (fully undetectable) attack
    ``a = H c``. The attacker can only *realize* the portion of this target that is
    feasible given the compromised measurement set (see :func:`compute_pa`). Drawn
    once and reused across all steps and gates for reproducibility.

    Parameters
    ----------
    H : numpy.ndarray, shape (M, N)
    rng : numpy.random.Generator
    n_fdi : int
        Number of attack targets.

    Returns
    -------
    C : numpy.ndarray, shape (n_fdi, N)
        Random target state perturbations.
    """
    n_states = H.shape[1]
    return rng.uniform(config.C_LOW, config.C_HIGH, size=(n_fdi, n_states))


def _feasible_projector(H: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Projector onto the feasible attack-state subspace given a compromise mask.

    The feasible undetectable attacks are ``a = H c`` supported on the compromised
    measurements only, i.e. ``c`` in the null space of ``H`` restricted to the
    *uncompromised* rows. Returns the orthogonal projector ``P`` onto that null
    space, so ``H (P c)`` is a realizable undetectable attack for any target ``c``.

    Parameters
    ----------
    H : numpy.ndarray, shape (M, N)
    mask : numpy.ndarray, shape (M,)
        1.0 on compromised measurements, 0.0 elsewhere.

    Returns
    -------
    P : numpy.ndarray, shape (N, N)
        Orthogonal projector onto the feasible-``c`` subspace. ``I`` if every
        measurement is compromised; the zero matrix if no feasible attack exists.
    """
    n = H.shape[1]
    uncompromised = np.where(mask == 0)[0]
    if uncompromised.size == 0:
        return np.eye(n)  # everything compromised: any a = Hc is realizable
    H_unc = H[uncompromised, :]
    _, s, vt = np.linalg.svd(H_unc, full_matrices=True)
    rank = int(np.sum(s > config.RANK_TOL))
    null_basis = vt[rank:].T  # (N, null_dim)
    if null_basis.shape[1] == 0:
        return np.zeros((n, n))
    return null_basis @ null_basis.T


def compute_pa(
    C_targets: np.ndarray,
    H: np.ndarray,
    A: np.ndarray,
    compromised: np.ndarray,
    strength_thr: float = config.STRENGTH_THR,
) -> float:
    """Compute the BDD bypass probability ``pa`` under partial compromise (Eq. 7).

    For each random target attack ``a_target = H c``, the attacker can realize only
    the feasible undetectable component ``a_feasible = H (P c)`` where ``P`` projects
    onto the feasible-``c`` subspace for the current compromised set (see
    :func:`_feasible_projector`). The attack is counted as a successful bypass iff
    the realizable attack retains at least ``strength_thr`` of the target strength::

        ||a_feasible|| / ||a_target|| >= strength_thr.

    Feasible attacks are undetectable by construction (they lie in ``H``'s column
    space and leave zero residual), so this strength ratio -- not a residual test --
    is what determines a successful, *impactful* bypass. ``pa`` rises monotonically
    from 0 (nothing compromised) to 1 (everything compromised).

    Parameters
    ----------
    C_targets : numpy.ndarray, shape (n_fdi, N)
        Random target perturbations from :func:`generate_fdi_targets`.
    H : numpy.ndarray, shape (M, N)
    A : numpy.ndarray, shape (M, 55)
    compromised : numpy.ndarray, shape (55,)
        Current latched binary node-compromise state.
    strength_thr : float
        Minimum realizable-strength ratio for a bypass to count.

    Returns
    -------
    pa : float
        Fraction of target attacks realizable above the strength threshold.
    """
    mask = measurement_mask(A, compromised)
    P = _feasible_projector(H, mask)

    a_target = C_targets @ H.T            # (n_fdi, M)
    a_feasible = (C_targets @ P.T) @ H.T  # (n_fdi, M)
    n_target = np.linalg.norm(a_target, axis=1)
    n_feasible = np.linalg.norm(a_feasible, axis=1)
    n_target = np.where(n_target == 0.0, 1.0, n_target)
    ratio = n_feasible / n_target
    return float(np.mean(ratio >= strength_thr))


def compute_rho_bar(rho: np.ndarray) -> float:
    """Return the mean infection level ``rho_bar`` over all nodes.

    Parameters
    ----------
    rho : numpy.ndarray, shape (55,)

    Returns
    -------
    float
        ``rho.mean()``.
    """
    return float(rho.mean())
