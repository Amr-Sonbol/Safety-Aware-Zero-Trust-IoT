"""Phase C / E2 — structural-invariance sweeps over the two Phase 0 calibration knobs.

E2a (STRENGTH_THR): recompute the undefended Gate A pa(t) curve at several thresholds.
E2b (HARDENING_DELTA): recompute the Gate B pa-vs-Nk curve at several deltas.

Claim: the *shape* of the bypass probability is invariant — a monotone S-curve in
time (E2a) and a diminishing-returns curve in defense budget (E2b); the calibration
parameter sets the magnitude, not the existence, of these features. delta=1.0 (full
isolation) collapses pa to ~0 — the overshoot that motivated partial hardening
(doc 05 Divergence 3).

SAFETY (Phase C governing rule). C0 confirmed BOTH knobs are function arguments:
``compute_pa(..., strength_thr=VALUE)`` (attack_engine.py:211) and
``greedy_search(..., delta=VALUE)`` (policy_engine.py:110). So this script passes
them directly — config.py is NEVER touched, no read-restore needed. We still assert
``STRENGTH_THR == 0.30`` and ``HARDENING_DELTA == 0.40`` at the end as proof.

Determinism: same seeds as the runner/figures (Gate A loop at SEED+1; greedy at the
N_FDI_POLICY=2000 slice, exactly as run_phase0 Gate B and make_figures use).

Run from the project root::

    python docs/make_shape_sweeps.py
"""

from __future__ import annotations

import csv
import os
import sys

import numpy as np

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from zt_cps_phase0.src import (
    attack_engine as ae,
    config,
    policy_engine as pe,
    power_system as ps,
    topology as tp,
)

DEFAULT_STRENGTH = 0.30
DEFAULT_DELTA = 0.40

STRENGTHS = [0.15, 0.20, 0.25, 0.30, 0.35, 0.40]
DELTAS = [0.2, 0.3, 0.4, 0.5, 0.6, 1.0]   # incl. full-isolation endpoint
NKS = [0, 5, 10, 15]


def build_model():
    """Network + H, B, A + shared full FDI targets (as runner/make_figures)."""
    net = ps.load_network()
    H, _branch_rows, _ = ps.build_H(net)
    B = tp.build_B()
    A = tp.build_A(H.shape[0])
    rng = np.random.default_rng(config.SEED)
    C_targets = ae.generate_fdi_targets(H, rng)
    return H, B, A, C_targets


def gate_a_series(H, B, A, C_targets, strength_thr):
    """Undefended Gate A pa(t) at a given strength_thr (passed as argument)."""
    rng = np.random.default_rng(config.SEED + 1)
    rho = np.full(config.N_NODES, config.RHO0)
    compromised = np.zeros(config.N_NODES)
    pa = np.empty(config.N_STEPS)
    for t in range(config.N_STEPS):
        rho = ae.update_worm(rho, B)
        compromised = ae.sample_compromise(rho, compromised, rng)
        pa[t] = ae.compute_pa(C_targets, H, A, compromised, strength_thr=strength_thr)
    return pa


def sweep_strength(H, B, A, C_targets):
    print("E2a — STRENGTH_THR sweep (undefended Gate A curve; arg-passed)\n")
    series = {}
    rows = []
    for s in STRENGTHS:
        pa = gate_a_series(H, B, A, C_targets, s)
        series[s] = pa
        rows.append({"strength_thr": s, "avg_pa": float(np.mean(pa))})
        marker = "  <- default" if abs(s - DEFAULT_STRENGTH) < 1e-9 else ""
        print(f"  strength_thr={s:.2f}  avg_pa={np.mean(pa):.5f}{marker}")

    csv_path = os.path.join(_PROJECT_ROOT, "results", "sweep_strength.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["strength_thr", "avg_pa"])
        w.writeheader()
        w.writerows(rows)
    print(f"\n[sweep_strength] wrote {csv_path}")

    fig, ax = plt.subplots(figsize=(8, 5))
    steps = np.arange(config.N_STEPS)
    for s in STRENGTHS:
        lw = 2.4 if abs(s - DEFAULT_STRENGTH) < 1e-9 else 1.3
        ax.plot(steps, series[s], marker=".", lw=lw, label=f"thr={s:.2f}")
    ax.set_xlabel("step t")
    ax.set_ylabel("pa(t)  (undefended Gate A)")
    ax.set_title("E2a: pa(t) is the same monotone S-curve at every STRENGTH_THR\n"
                 "(threshold shifts the level, not the shape)")
    ax.legend(title="strength_thr", fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig_path = os.path.join(_PROJECT_ROOT, "docs", "figures", "fig_strength_sweep.png")
    fig.savefig(fig_path, dpi=120)
    plt.close(fig)
    print(f"[fig_strength_sweep] wrote {fig_path}\n")


def sweep_delta(H, B, A, C_targets):
    print("E2b — HARDENING_DELTA sweep (Gate B pa-vs-Nk; greedy delta arg-passed)")
    print("  using the N_FDI_POLICY=2000 policy slice (same as run_phase0 Gate B);")
    print(f"  Nk grid = {NKS}; deltas = {DELTAS}\n")
    C_policy = C_targets[: config.N_FDI_POLICY]

    # Nk=0 baseline is delta-independent (no hardening applied to B), computed once.
    pa0 = pe.evaluate_policy(B, H, A, C_policy)

    series = {}
    rows = []
    for d in DELTAS:
        achieved = []
        for nk in NKS:
            if nk == 0:
                achieved.append(pa0)
            else:
                _, pa_nk = pe.greedy_search(B, nk, H, A, C_policy, delta=d)
                achieved.append(pa_nk)
        series[d] = achieved
        for nk, pa in zip(NKS, achieved):
            rows.append({"delta": d, "Nk": nk, "avg_pa": float(pa)})
        marker = "  <- default" if abs(d - DEFAULT_DELTA) < 1e-9 else ""
        print(f"  delta={d:.1f}  pa(Nk={NKS}) = "
              f"[{', '.join(f'{p:.4f}' for p in achieved)}]{marker}")

    csv_path = os.path.join(_PROJECT_ROOT, "results", "sweep_delta.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["delta", "Nk", "avg_pa"])
        w.writeheader()
        w.writerows(rows)
    print(f"\n[sweep_delta] wrote {csv_path}")

    fig, ax = plt.subplots(figsize=(8, 5))
    for d in DELTAS:
        lw = 2.4 if abs(d - DEFAULT_DELTA) < 1e-9 else 1.3
        ax.plot(NKS, series[d], marker="o", lw=lw, label=f"δ={d:.1f}")
    ax.set_xlabel("defense budget Nk (nodes hardened)")
    ax.set_ylabel("greedy avg pa")
    ax.set_title("E2b: pa-vs-Nk has the same diminishing-returns shape at every δ\n"
                 "(δ=1.0 = full isolation collapses pa to ~0 — the overshoot)")
    ax.legend(title="HARDENING_DELTA", fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig_path = os.path.join(_PROJECT_ROOT, "docs", "figures", "fig_delta_sweep.png")
    fig.savefig(fig_path, dpi=120)
    plt.close(fig)
    print(f"[fig_delta_sweep] wrote {fig_path}\n")


def main() -> None:
    print("Phase C / E2 — structural-invariance sweeps")
    print(f"  frozen defaults: STRENGTH_THR={DEFAULT_STRENGTH}, "
          f"HARDENING_DELTA={DEFAULT_DELTA}")
    print(f"  (at start: STRENGTH_THR={config.STRENGTH_THR}, "
          f"HARDENING_DELTA={config.HARDENING_DELTA})\n")
    os.makedirs(os.path.join(_PROJECT_ROOT, "results"), exist_ok=True)

    H, B, A, C_targets = build_model()
    sweep_strength(H, B, A, C_targets)
    sweep_delta(H, B, A, C_targets)

    # PROVE the frozen defaults survived (these were never written, only arg-passed).
    assert config.STRENGTH_THR == DEFAULT_STRENGTH, (
        f"STRENGTH_THR corrupted: {config.STRENGTH_THR}")
    assert config.HARDENING_DELTA == DEFAULT_DELTA, (
        f"HARDENING_DELTA corrupted: {config.HARDENING_DELTA}")
    print(f"[restore-proof] config.STRENGTH_THR == {DEFAULT_STRENGTH}  -> PASSED")
    print(f"[restore-proof] config.HARDENING_DELTA == {DEFAULT_DELTA}  -> PASSED")


if __name__ == "__main__":
    main()
