"""Power-system model: network, DC measurement matrix, measurements, estimator.

This module reproduces the *physical* half of the cyber-physical attack model:
the IEEE 30-bus network, the DC state-estimation measurement matrix ``H``, the
generation of real branch-flow measurements ``z``, and the weighted-least-squares
estimator gain ``K`` (paper Eqs. 5-6).

Key modeling assumptions
------------------------
* **H is the DC power-flow Jacobian, NOT an incidence matrix.** For a branch ``k``
  between buses ``i`` and ``j`` with per-unit series reactance ``x_k``, the active
  power flow is ``P_ij = (theta_i - theta_j) / x_k``. Hence row ``k`` of ``H`` holds
  ``+1/x_k`` in column ``i`` and ``-1/x_k`` in column ``j`` — never ``+/-1``.
* **States are bus voltage angles with the slack angle removed**, so ``H`` is
  ``(M x N)`` with ``N = 29`` (30 buses minus the slack), and ``z`` lives in
  ``R^M`` with ``M = n_line + n_trafo`` branch-flow measurements.
* **Measurements ``z`` are real DC power flows**, converted from MW to per-unit on
  the 100 MVA system base so they lie in the column space of ``H`` (which is built
  in ``1/x`` per-unit units). ``z`` is never random noise.
* The estimator is weighted least squares with ``W = R^{-1}``, the inverse
  measurement-noise covariance (the maximum-likelihood Gaussian estimator).
"""

from __future__ import annotations

import os
from typing import Tuple

import numpy as np
import pandapower as pp
import pandapower.networks as pn

from . import config

# MATPOWER/PYPOWER branch-matrix column indices (0-based).
_F_BUS = 0
_T_BUS = 1
_BR_X = 3
_TAP = 8
_PF = 13


def load_network() -> "pp.pandapowerNet":
    """Load and DC-solve the IEEE 30-bus test case.

    Uses :func:`pandapower.networks.case_ieee30` (the MATPOWER-origin case), which
    has a total load of 283.4 MW and a slack-bus voltage of 1.06 p.u. — both spec
    validation targets. (``case30`` would give a 1.0 p.u. slack and is *not* used.)

    Returns
    -------
    pp.pandapowerNet
        The network after a converged DC power flow, with ``net._ppc`` populated.

    Raises
    ------
    AssertionError
        If the DC power flow did not produce finite results, or the total load /
        slack voltage do not match the published case.
    """
    net = pn.case_ieee30()
    pp.rundcpp(net)

    # DC power flow has no AC-style ``converged`` flag; guard on populated _ppc and
    # finite bus angles instead.
    assert net._ppc is not None, "DC power flow did not populate net._ppc"
    assert np.isfinite(net.res_bus.va_degree.to_numpy()).all(), (
        "DC power flow produced non-finite bus angles"
    )

    total_load = float(net.load.p_mw.sum())
    assert abs(total_load - 283.4) < 0.5, f"total load {total_load} MW != 283.4 MW"

    slack_vm = float(net.ext_grid.vm_pu.iloc[0])
    assert abs(slack_vm - 1.06) < 1e-6, f"slack vm_pu {slack_vm} != 1.06"

    return net


def build_H(
    net: "pp.pandapowerNet",
) -> Tuple[np.ndarray, np.ndarray, dict[int, int]]:
    """Build the reactance-weighted DC measurement matrix ``H``.

    Each measurement is the active power flow on a branch (transmission line *or*
    transformer). Row ``k`` of ``H`` encodes ``P_ij = (theta_i - theta_j)/x_k`` as
    ``+1/x_k`` in the state column of bus ``i`` and ``-1/x_k`` in the state column
    of bus ``j``. The slack-bus angle is the reference and is dropped, so ``H`` has
    ``N = 29`` columns.

    Parameters
    ----------
    net : pp.pandapowerNet
        A DC-solved IEEE 30-bus network (see :func:`load_network`).

    Returns
    -------
    H : numpy.ndarray, shape (M, 29)
        The DC Jacobian measurement matrix. ``M = n_line + n_trafo``.
    branch_rows : numpy.ndarray, shape (M,)
        The ``_ppc`` branch-matrix row indices (lines then trafos), in the same
        order as ``H``'s rows, so :func:`generate_z` reads flows consistently.
    state_index : dict[int, int]
        Maps each non-slack ``_ppc`` bus index to its column in ``H``.

    Raises
    ------
    AssertionError
        If ``H`` is not full column rank (29), or its entries are not
        reactance-weighted (a spot check that catches the ``+/-1`` incidence bug).
    """
    branch = net._ppc["branch"]
    bus_lookup = net._pd2ppc_lookups["bus"]

    # Branch element row ranges: lines occupy [0, n_line), trafos next.
    line_start, line_end = net._pd2ppc_lookups["branch"]["line"]
    trafo_range = net._pd2ppc_lookups["branch"].get("trafo")
    if trafo_range is not None:
        _, trafo_end = trafo_range
    else:
        trafo_end = line_end
    branch_rows = np.arange(line_start, trafo_end)
    m = int(branch_rows.shape[0])

    # Slack ppc bus and the state-column assignment (all ppc buses except slack,
    # in sorted order for determinism).
    slack_ppc = int(bus_lookup[net.ext_grid.bus.iloc[0]])
    all_ppc_buses = sorted(int(b) for b in np.unique(bus_lookup))
    non_slack = [b for b in all_ppc_buses if b != slack_ppc]
    assert len(non_slack) == config.N_STATES, (
        f"expected {config.N_STATES} non-slack buses, got {len(non_slack)}"
    )
    state_index = {bus: col for col, bus in enumerate(non_slack)}

    H = np.zeros((m, config.N_STATES), dtype=float)
    for row, k in enumerate(branch_rows):
        i = int(branch[k, _F_BUS].real)
        j = int(branch[k, _T_BUS].real)
        x = float(branch[k, _BR_X].real)
        assert abs(x) > 1e-9, f"branch {k} has near-zero reactance {x}"
        # Off-nominal-tap transformers divide the series susceptance by the tap
        # ratio: the DC flow is P_ij = (theta_i - theta_j)/(x * tap). Lines have
        # tap == 1.0 (or 0.0 in MATPOWER, meaning nominal), so b = 1/x there.
        tap = float(branch[k, _TAP].real)
        if tap == 0.0:
            tap = 1.0
        b = 1.0 / (x * tap)
        if i != slack_ppc:
            H[row, state_index[i]] += b
        if j != slack_ppc:
            H[row, state_index[j]] -= b

    n = H.shape[1]
    print(f"[build_H] M (measurements) = {m}, N (states) = {n}")
    rank = int(np.linalg.matrix_rank(H, tol=config.RANK_TOL))
    print(f"[build_H] rank(H) = {rank}")
    assert n == config.N_STATES, f"H has {n} columns, expected {config.N_STATES}"
    assert rank == config.N_STATES, f"rank(H) = {rank}, expected {config.N_STATES}"

    # Spot-check reactance weighting: pick a non-slack-only line branch and verify
    # |H[k, col_i]| == 1/x_k (and is well above 1.0, not the incidence value).
    _spot_check_reactance_weighting(H, branch, branch_rows, slack_ppc, state_index)

    return H, branch_rows, state_index


def _spot_check_reactance_weighting(
    H: np.ndarray,
    branch: np.ndarray,
    branch_rows: np.ndarray,
    slack_ppc: int,
    state_index: dict[int, int],
) -> None:
    """Assert at least one H entry equals 1/(x*tap) (not the +/-1 incidence value).

    Catches the classic bug of building an incidence matrix instead of the DC
    Jacobian. Picks the first nominal-tap branch (a line) whose from-bus is a
    non-slack state bus, so the expected value is simply ``1/x``.
    """
    for row, k in enumerate(branch_rows):
        i = int(branch[k, _F_BUS].real)
        if i == slack_ppc:
            continue
        tap = float(branch[k, _TAP].real)
        if tap not in (0.0, 1.0):
            continue  # prefer a nominal-tap branch for an unambiguous 1/x check
        x = float(branch[k, _BR_X].real)
        col = state_index[i]
        expected = 1.0 / x
        assert abs(abs(H[row, col]) - expected) < 1e-6, (
            f"H[{row},{col}]={H[row,col]} != 1/x={expected} (reactance weighting)"
        )
        assert abs(H[row, col]) > 1.5, (
            f"H[{row},{col}]={H[row,col]} looks like a +/-1 incidence entry, "
            "not a reactance weight"
        )
        print(
            f"[build_H] reactance spot-check OK: |H[{row},{col}]| = "
            f"{abs(H[row, col]):.4f} == 1/x = {expected:.4f}"
        )
        return
    raise AssertionError("no nominal-tap non-slack branch found for spot-check")


def build_R(z: np.ndarray) -> np.ndarray:
    """Build the diagonal measurement-noise covariance ``R = diag(sigma^2)``.

    The per-measurement standard deviation is ``sigma_m = max(NOISE_REL*|z_m|,
    SIGMA_FLOOR)``. The floor prevents a singular ``R`` at zero-flow branches.

    Parameters
    ----------
    z : numpy.ndarray, shape (M,)
        Measurement vector (clean or noisy) used to scale the noise.

    Returns
    -------
    R : numpy.ndarray, shape (M, M)
        Diagonal covariance matrix.
    """
    sigma = compute_sigma(z)
    return np.diag(sigma ** 2)


def compute_sigma(z: np.ndarray) -> np.ndarray:
    """Per-measurement noise standard deviation ``sigma_m``.

    Parameters
    ----------
    z : numpy.ndarray, shape (M,)

    Returns
    -------
    sigma : numpy.ndarray, shape (M,)
        ``max(NOISE_REL*|z_m|, SIGMA_FLOOR)`` elementwise.
    """
    return np.maximum(config.NOISE_REL * np.abs(z), config.SIGMA_FLOOR)


def build_estimator(H: np.ndarray, R: np.ndarray) -> np.ndarray:
    """Build the weighted-least-squares estimator gain ``K`` (paper Eq. 6).

    ``x_hat = K z`` with ``K = (H^T W H)^{-1} H^T W`` and ``W = R^{-1}``. ``W`` is
    the inverse measurement-noise covariance, making this the maximum-likelihood
    Gaussian state estimator (not an unweighted pseudoinverse).

    Parameters
    ----------
    H : numpy.ndarray, shape (M, N)
    R : numpy.ndarray, shape (M, M)
        Diagonal measurement-noise covariance.

    Returns
    -------
    K : numpy.ndarray, shape (N, M)
        Estimator gain. Satisfies ``K @ H == I_N`` (to machine precision).
    """
    W = np.linalg.inv(R)
    HtW = H.T @ W
    K = np.linalg.inv(HtW @ H) @ HtW
    return K


def load_profile(n_steps: int = config.N_STEPS) -> np.ndarray:
    """Return a per-step load-scaling multiplier of length ``n_steps``.

    Uses the NYISO October-2022 CSV at :data:`config.NYISO_CSV` if present
    (normalized so its mean is 1.0 and resampled to ``n_steps`` points); otherwise
    falls back to a documented smooth daily sinusoidal curve that scales the base
    loads by ``+/- LOAD_SWING``. Prints which source was used.

    Parameters
    ----------
    n_steps : int
        Number of simulation steps.

    Returns
    -------
    profile : numpy.ndarray, shape (n_steps,)
        Multiplicative scaling applied to the base case loads at each step.
    """
    csv_path = config.NYISO_CSV
    if os.path.exists(csv_path):
        import pandas as pd

        raw = pd.read_csv(csv_path)
        # Use the first numeric column as the load series.
        numeric = raw.select_dtypes(include="number")
        series = numeric.iloc[:, 0].to_numpy(dtype=float)
        # Resample to n_steps by linear interpolation, normalize to mean 1.0.
        idx = np.linspace(0, len(series) - 1, n_steps)
        profile = np.interp(idx, np.arange(len(series)), series)
        profile = profile / profile.mean()
        print(f"[load_profile] source = NYISO CSV ({csv_path}), {len(series)} samples")
        return profile

    # Synthetic smooth daily curve: one cosine period across the horizon.
    t = np.arange(n_steps)
    profile = 1.0 + config.LOAD_SWING * np.cos(2.0 * np.pi * t / n_steps)
    print(
        f"[load_profile] source = synthetic daily curve (+/-{config.LOAD_SWING:.0%}); "
        f"no CSV at {csv_path}"
    )
    return profile


def generate_z(
    net: "pp.pandapowerNet",
    branch_rows: np.ndarray,
    base_load_p: np.ndarray,
    profile: np.ndarray,
    t: int,
    rng: np.random.Generator,
    base_load_q: np.ndarray | None = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """Generate real branch-flow measurements ``z`` at step ``t``.

    Scales the case loads by ``profile[t]``, runs DC power flow, reads the per-unit
    branch active-power flows for the same branches (and ordering) that ``H`` maps,
    and adds Gaussian measurement noise. **Never** substitutes random noise for the
    measurements themselves.

    Parameters
    ----------
    net : pp.pandapowerNet
    branch_rows : numpy.ndarray, shape (M,)
        ``_ppc`` branch rows from :func:`build_H`, defining z's ordering.
    base_load_p : numpy.ndarray
        Base active loads captured once before any scaling.
    profile : numpy.ndarray
        Per-step load multiplier (see :func:`load_profile`).
    t : int
        Current simulation step.
    rng : numpy.random.Generator
        Seeded RNG for the measurement noise.
    base_load_q : numpy.ndarray, optional
        Base reactive loads (scaled too for consistency; DC ignores Q).

    Returns
    -------
    z : numpy.ndarray, shape (M,)
        Noisy per-unit branch-flow measurements.
    z_clean : numpy.ndarray, shape (M,)
        Noise-free per-unit branch flows (for the unobservability self-check).
    """
    scale = float(profile[t])
    net.load.p_mw = base_load_p * scale
    if base_load_q is not None:
        net.load.q_mvar = base_load_q * scale

    pp.rundcpp(net)

    # PF (col 13) is in MW; divide by the system base to get per-unit, matching H.
    z_clean = net._ppc["branch"][branch_rows, _PF].real.astype(float) / config.SYSTEM_BASE_MVA

    sigma = compute_sigma(z_clean)
    e = rng.normal(0.0, sigma)
    z = z_clean + e
    return z, z_clean


def clean_residual_norm(z_clean: np.ndarray, H: np.ndarray, K: np.ndarray) -> float:
    """Return ``||z_clean - H (K z_clean)||`` — the unobservability self-check.

    Because real measurements lie in the column space of ``H``, the WLS-projected
    residual of a *clean* measurement must be at machine precision. A large value
    means ``H`` or ``z`` is wrong (units/ordering) — the spec's #1 gate-killer.

    Parameters
    ----------
    z_clean : numpy.ndarray, shape (M,)
    H : numpy.ndarray, shape (M, N)
    K : numpy.ndarray, shape (N, M)

    Returns
    -------
    float
        The residual 2-norm.
    """
    r = z_clean - H @ (K @ z_clean)
    return float(np.linalg.norm(r))
