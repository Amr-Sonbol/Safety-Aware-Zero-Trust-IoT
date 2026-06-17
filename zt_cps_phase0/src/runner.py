"""Phase 0 validation runner.

Orchestrates all six PASS/FAIL checks that constitute the Phase 0 deliverable
for the Feng & Hu (2023) cyber-physical attack-model reproduction:

    1. Network: total load ≈ 283.4 MW, slack voltage = 1.06 p.u.
    2. H matrix: shape (M, 29), rank 29, reactance-weighted entries.
    3. Clean baseline residual ≈ noise floor (unobservability self-check).
    4. Gate A: no-ZTA avg pa ∈ [0.70, 0.80] over 40 steps; target 0.7474.
    5. Gate B Nk=10: greedy-defended avg pa ∈ [0.50, 0.58].
    6. Gate B Nk=15: greedy-defended avg pa ∈ [0.49, 0.57] and ≤ Nk=10 result.
"""

from __future__ import annotations

import sys
import time

import numpy as np
import pandapower as pp

from . import attack_engine as ae
from . import config
from . import policy_engine as pe
from . import power_system as ps
from . import topology as tp


def _pass_fail(label: str, ok: bool, detail: str = "") -> bool:
    status = "PASS" if ok else "FAIL"
    line = f"  [{status}] {label}"
    if detail:
        line += f" — {detail}"
    print(line)
    return ok


def run_phase0() -> bool:
    """Run all six Phase 0 validation checks and print a PASS/FAIL report.

    Returns
    -------
    bool
        ``True`` if every check passed, ``False`` if any failed.
    """
    print("=" * 70)
    print("Phase 0 — Feng & Hu (2023) Cyber-Physical Attack Model Validation")
    print(f"pandapower version: {pp.__version__}")
    print("=" * 70)

    all_pass = True

    # ------------------------------------------------------------------ #
    # Setup: load network and build core objects                           #
    # ------------------------------------------------------------------ #
    print("\n[Setup] Loading IEEE 30-bus network and building model objects...")
    t0 = time.time()

    net = ps.load_network()
    H, branch_rows, _ = ps.build_H(net)
    B = tp.build_B()
    A = tp.build_A(H.shape[0])

    base_load_p = net.load.p_mw.to_numpy().copy()
    base_load_q = net.load.q_mvar.to_numpy().copy()
    profile = ps.load_profile()

    rng = np.random.default_rng(config.SEED)
    C_targets = ae.generate_fdi_targets(H, rng)  # shape (N_FDI, N_STATES)
    C_policy = C_targets[: config.N_FDI_POLICY]   # 2000-sample slice for greedy

    print(f"  Setup completed in {time.time() - t0:.1f}s")

    # ------------------------------------------------------------------ #
    # Check 1: Network sanity                                              #
    # ------------------------------------------------------------------ #
    print("\n[Check 1] Network: total load and slack voltage")
    total_load = float(net.load.p_mw.sum())
    slack_vm = float(net.ext_grid.vm_pu.iloc[0])
    ok1a = abs(total_load - 283.4) < 0.5
    ok1b = abs(slack_vm - 1.06) < 1e-6
    ok1 = ok1a and ok1b
    all_pass &= _pass_fail(
        "Total load ≈ 283.4 MW",
        ok1a,
        f"got {total_load:.1f} MW",
    )
    all_pass &= _pass_fail(
        "Slack vm_pu = 1.06",
        ok1b,
        f"got {slack_vm:.4f} p.u.",
    )

    # ------------------------------------------------------------------ #
    # Check 2: H matrix properties                                         #
    # ------------------------------------------------------------------ #
    print("\n[Check 2] H matrix: shape, rank, reactance weighting")
    m, n = H.shape
    rank = int(np.linalg.matrix_rank(H, tol=config.RANK_TOL))
    ok2a = m == 41 and n == config.N_STATES
    ok2b = rank == config.N_STATES
    nonzero = np.abs(H[H != 0])
    ok2c = not np.allclose(nonzero, 1.0) and np.max(nonzero) > 1.5
    all_pass &= _pass_fail(
        f"H shape ({m}, {n}) with M=41, N=29",
        ok2a,
        f"shape = ({m}, {n})",
    )
    all_pass &= _pass_fail(
        f"H is full column rank (29)",
        ok2b,
        f"rank = {rank}",
    )
    all_pass &= _pass_fail(
        "H entries are reactance-weighted (not ±1 incidence)",
        ok2c,
        f"max |H| = {np.max(nonzero):.3f}",
    )

    # ------------------------------------------------------------------ #
    # Check 3: Clean baseline residual (unobservability self-check)        #
    # ------------------------------------------------------------------ #
    print("\n[Check 3] Clean residual ≈ noise floor (z in col-space of H)")
    rng_check = np.random.default_rng(config.SEED)
    z, z_clean = ps.generate_z(
        net, branch_rows, base_load_p, profile, 0, rng_check, base_load_q
    )
    R = ps.build_R(z_clean)
    K = ps.build_estimator(H, R)
    residual = ps.clean_residual_norm(z_clean, H, K)
    ok3 = residual < 1e-6
    all_pass &= _pass_fail(
        "Clean residual ‖z_clean − H K z_clean‖ < 1e-6",
        ok3,
        f"residual = {residual:.2e}",
    )

    # ------------------------------------------------------------------ #
    # Check 4: Gate A — no-ZTA average pa                                  #
    # ------------------------------------------------------------------ #
    print("\n[Check 4] Gate A: no-ZTA average bypass probability over 40 steps")
    print("  (B' = B, no defense, 10 000 FDI targets)")
    t4 = time.time()

    rng_a = np.random.default_rng(config.SEED + 1)
    rho = np.full(config.N_NODES, config.RHO0)
    compromised = np.zeros(config.N_NODES)
    pa_series: list[float] = []

    for t in range(config.N_STEPS):
        rho = ae.update_worm(rho, B)
        compromised = ae.sample_compromise(rho, compromised, rng_a)
        pa_t = ae.compute_pa(C_targets, H, A, compromised)
        pa_series.append(pa_t)

    avg_pa_a = float(np.mean(pa_series))
    lo_a, hi_a = config.GATE_A
    ok4 = lo_a <= avg_pa_a <= hi_a
    all_pass &= _pass_fail(
        f"Gate A avg pa ∈ [{lo_a:.2f}, {hi_a:.2f}]  (target {config.GATE_A_TARGET})",
        ok4,
        f"achieved {avg_pa_a:.4f}  ({time.time()-t4:.1f}s)",
    )

    # ------------------------------------------------------------------ #
    # Checks 5 & 6: Gate B — greedy-defended pa at Nk=10 and Nk=15        #
    # ------------------------------------------------------------------ #
    print("\n[Check 5 & 6] Gate B: greedy partial-node-hardening defense")
    print(f"  delta = {config.HARDENING_DELTA}, {config.N_FDI_POLICY} FDI targets")
    print(f"  This runs O(Nk × 55) full simulations per budget — takes ~10–20 min.")

    results: dict[int, float] = {}
    for nk in config.NK_LIST:
        print(f"\n  [Greedy Nk={nk}] Forward selection...")
        t_nk = time.time()
        selected, pa_nk = pe.greedy_search(B, nk, H, A, C_policy)
        results[nk] = pa_nk
        print(
            f"  [Greedy Nk={nk}] done: selected={selected}, pa={pa_nk:.4f}, "
            f"t={time.time()-t_nk:.0f}s"
        )

    pa10 = results[10]
    pa15 = results[15]
    lo10, hi10 = config.GATE_B_NK10
    lo15, hi15 = config.GATE_B_NK15
    ok5 = lo10 <= pa10 <= hi10
    ok6a = lo15 <= pa15 <= hi15
    ok6b = pa15 <= pa10
    all_pass &= _pass_fail(
        f"Gate B Nk=10 avg pa ∈ [{lo10:.2f}, {hi10:.2f}]",
        ok5,
        f"achieved {pa10:.4f}",
    )
    all_pass &= _pass_fail(
        f"Gate B Nk=15 avg pa ∈ [{lo15:.2f}, {hi15:.2f}]",
        ok6a,
        f"achieved {pa15:.4f}",
    )
    all_pass &= _pass_fail(
        "Gate B monotone: pa(Nk=15) ≤ pa(Nk=10)",
        ok6b,
        f"{pa15:.4f} ≤ {pa10:.4f}",
    )

    # ------------------------------------------------------------------ #
    # Summary                                                              #
    # ------------------------------------------------------------------ #
    print("\n" + "=" * 70)
    print("Summary")
    print("=" * 70)
    print(f"  Gate A (no-ZTA avg pa):   {avg_pa_a:.4f}  target={config.GATE_A_TARGET}")
    print(f"  Gate B Nk=10 avg pa:      {pa10:.4f}  paper={config.GATE_B_PAPER_NK10}")
    print(f"  Gate B Nk=15 avg pa:      {pa15:.4f}  paper={config.GATE_B_PAPER_NK15}")
    print(f"  Hardening delta:          {config.HARDENING_DELTA}")
    print(f"  Strength threshold:       {config.STRENGTH_THR}")
    print()
    if all_pass:
        print("ALL CHECKS PASSED — Phase 0 baseline validated.")
    else:
        print("ONE OR MORE CHECKS FAILED — see FAIL lines above.")
    print("=" * 70)

    return all_pass
