"""Regenerate the Phase 0 documentation figures.

Run from the project root::

    python docs/make_figures.py            # all three figures (slow: Gate B sweep)
    python docs/make_figures.py --fast     # skip the slow Nk sweep figure

This script is **read-only** with respect to ``zt_cps_phase0/src`` — it imports the
exact same model code the runner uses and only *reads* from it. It writes three PNGs
to ``docs/figures/`` and prints the numeric series it plotted so every figure is
auditable against ``python run_phase0.py``.

Figures
-------
1. ``pa_vs_step.png``     — Gate A bypass probability pa(t) over the 40-step horizon
                            (no defense, full N_FDI=10000), with reference lines at the
                            paper target (0.7474) and the achieved 40-step average.
2. ``rho_bar_vs_step.png``— mean infection level rho_bar(t) over the same run, showing
                            the mean-field SIS saturation (~0.34) that motivates the
                            Bernoulli+latching compromise model.
3. ``gateB_nk_sweep.png`` — greedy partial-hardening average pa versus defense budget
                            Nk in {0, 5, 10, 15} (Nk=0 = the Gate A baseline), with the
                            paper's reported Nk=10/15 points overlaid. Uses the same
                            N_FDI_POLICY=2000 slice the runner's Gate B uses.
"""

from __future__ import annotations

import os
import sys

import numpy as np

# Import the model code exactly as run_phase0.py does (project root on sys.path).
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

import matplotlib

matplotlib.use("Agg")  # headless: write files, never open a window
import matplotlib.pyplot as plt  # noqa: E402

from zt_cps_phase0.src import attack_engine as ae  # noqa: E402
from zt_cps_phase0.src import config  # noqa: E402
from zt_cps_phase0.src import policy_engine as pe  # noqa: E402
from zt_cps_phase0.src import power_system as ps  # noqa: E402
from zt_cps_phase0.src import topology as tp  # noqa: E402

_FIG_DIR = os.path.join(_PROJECT_ROOT, "docs", "figures")
_DPI = 150


def _build_model():
    """Load the network and build H, B, A, and the shared FDI targets (as the runner)."""
    net = ps.load_network()
    H, _branch_rows, _ = ps.build_H(net)
    B = tp.build_B()
    A = tp.build_A(H.shape[0])
    rng = np.random.default_rng(config.SEED)
    C_targets = ae.generate_fdi_targets(H, rng)  # (N_FDI, N_STATES)
    return H, B, A, C_targets


def _gate_a_series(H, B, A, C_targets):
    """Replay the runner's Gate A loop, returning per-step pa(t) and rho_bar(t).

    Mirrors runner.run_phase0 Check 4 exactly: no defense (B' = B), full N_FDI
    targets, RNG seeded at SEED + 1, Bernoulli+latching compromise.
    """
    rng = np.random.default_rng(config.SEED + 1)
    rho = np.full(config.N_NODES, config.RHO0)
    compromised = np.zeros(config.N_NODES)
    pa = np.empty(config.N_STEPS)
    rho_bar = np.empty(config.N_STEPS)
    for t in range(config.N_STEPS):
        rho = ae.update_worm(rho, B)
        compromised = ae.sample_compromise(rho, compromised, rng)
        pa[t] = ae.compute_pa(C_targets, H, A, compromised)
        rho_bar[t] = ae.compute_rho_bar(rho)
    return pa, rho_bar


def figure_pa_vs_step(pa):
    """Plot pa(t) with paper-target and achieved-average reference lines."""
    avg = float(pa.mean())
    steps = np.arange(config.N_STEPS)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(steps, pa, marker="o", ms=3, lw=1.5, color="#1f77b4", label="pa(t)")
    ax.axhline(
        config.GATE_A_TARGET,
        ls="--",
        color="#d62728",
        lw=1.2,
        label=f"paper target {config.GATE_A_TARGET}",
    )
    ax.axhline(
        avg,
        ls=":",
        color="#2ca02c",
        lw=1.5,
        label=f"achieved 40-step avg {avg:.4f}",
    )
    lo, hi = config.GATE_A
    ax.axhspan(lo, hi, color="#2ca02c", alpha=0.07, label=f"Gate A band [{lo}, {hi}]")
    ax.set_xlabel("simulation step  t")
    ax.set_ylabel("FDI bypass probability  pa")
    ax.set_title("Gate A: no-ZTA bypass probability over the 40-step horizon")
    ax.set_ylim(0, 1)
    ax.grid(alpha=0.3)
    ax.legend(loc="lower right", fontsize=8)
    fig.tight_layout()
    out = os.path.join(_FIG_DIR, "pa_vs_step.png")
    fig.savefig(out, dpi=_DPI)
    plt.close(fig)
    print(f"[pa_vs_step] avg={avg:.4f}  first={pa[0]:.4f}  last={pa[-1]:.4f}")
    print(f"[pa_vs_step] series={np.round(pa, 4).tolist()}")
    print(f"[pa_vs_step] wrote {out}")
    return avg


def figure_rho_bar_vs_step(rho_bar):
    """Plot rho_bar(t), annotating the mean-field saturation level."""
    sat = float(rho_bar[-1])
    steps = np.arange(config.N_STEPS)
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(steps, rho_bar, marker="s", ms=3, lw=1.5, color="#9467bd", label=r"$\bar\rho(t)$")
    ax.axhline(
        sat,
        ls=":",
        color="#9467bd",
        lw=1.2,
        label=f"saturation ≈ {sat:.3f}",
    )
    ax.axhline(0.5, ls="--", color="#7f7f7f", lw=1.0, label="hard threshold ρ>0.5 (unused)")
    ax.set_xlabel("simulation step  t")
    ax.set_ylabel(r"mean infection level  $\bar\rho$")
    ax.set_title("Mean-field SIS worm: infection saturates below the 0.5 threshold")
    ax.set_ylim(0, 1)
    ax.grid(alpha=0.3)
    ax.legend(loc="center right", fontsize=8)
    fig.tight_layout()
    out = os.path.join(_FIG_DIR, "rho_bar_vs_step.png")
    fig.savefig(out, dpi=_DPI)
    plt.close(fig)
    print(f"[rho_bar_vs_step] start={rho_bar[0]:.4f}  saturation={sat:.4f}")
    print(f"[rho_bar_vs_step] series={np.round(rho_bar, 4).tolist()}")
    print(f"[rho_bar_vs_step] wrote {out}")
    return sat


def figure_gateB_nk_sweep(H, B, A, C_targets, baseline_pa):
    """Greedy avg pa versus defense budget Nk, with paper points overlaid.

    Uses the same N_FDI_POLICY slice the runner's Gate B uses. Nk=0 is the
    undefended baseline (the Gate A average); higher Nk runs greedy_search.
    """
    C_policy = C_targets[: config.N_FDI_POLICY]
    nks = [0, 5, 10, 15]
    achieved = []
    for nk in nks:
        if nk == 0:
            # Baseline under the policy slice (no hardening), for a fair curve.
            pa0 = pe.evaluate_policy(B, H, A, C_policy)
            achieved.append(pa0)
            print(f"[gateB_sweep] Nk=0 baseline pa={pa0:.4f} (policy slice)")
        else:
            selected, pa_nk = pe.greedy_search(B, nk, H, A, C_policy)
            achieved.append(pa_nk)
            print(f"[gateB_sweep] Nk={nk} pa={pa_nk:.4f} selected={selected}")

    paper_pts = {10: config.GATE_B_PAPER_NK10, 15: config.GATE_B_PAPER_NK15}

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.plot(nks, achieved, marker="o", ms=6, lw=1.8, color="#1f77b4", label="this work (greedy, δ=0.40)")
    px = sorted(paper_pts)
    ax.plot(
        px,
        [paper_pts[k] for k in px],
        marker="D",
        ms=7,
        ls="--",
        color="#d62728",
        label="Feng & Hu (2023), DQL",
    )
    # Gate B bands at Nk=10 and Nk=15.
    ax.errorbar(10, np.mean(config.GATE_B_NK10), yerr=(config.GATE_B_NK10[1] - config.GATE_B_NK10[0]) / 2,
                fmt="none", ecolor="#2ca02c", elinewidth=8, alpha=0.18)
    ax.errorbar(15, np.mean(config.GATE_B_NK15), yerr=(config.GATE_B_NK15[1] - config.GATE_B_NK15[0]) / 2,
                fmt="none", ecolor="#2ca02c", elinewidth=8, alpha=0.18, label="Gate B bands")
    for k, v in zip(nks, achieved):
        ax.annotate(f"{v:.4f}", (k, v), textcoords="offset points", xytext=(0, 8), fontsize=8, ha="center")
    ax.set_xlabel("defense budget  Nk  (number of hardened nodes)")
    ax.set_ylabel("average FDI bypass probability  pa")
    ax.set_title("Gate B: greedy partial-node-hardening vs. defense budget")
    ax.set_xticks(nks)
    ax.set_ylim(0, max(0.8, max(achieved) + 0.05))
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    out = os.path.join(_FIG_DIR, "gateB_nk_sweep.png")
    fig.savefig(out, dpi=_DPI)
    plt.close(fig)
    print(f"[gateB_sweep] nks={nks} achieved={[round(a, 4) for a in achieved]}")
    print(f"[gateB_sweep] wrote {out}")
    return nks, achieved


def main(argv: list[str]) -> int:
    fast = "--fast" in argv
    os.makedirs(_FIG_DIR, exist_ok=True)
    print("Building model (network, H, B, A, FDI targets)...")
    H, B, A, C_targets = _build_model()

    print("\nReplaying Gate A loop for pa(t) and rho_bar(t)...")
    pa, rho_bar = _gate_a_series(H, B, A, C_targets)
    avg = figure_pa_vs_step(pa)
    figure_rho_bar_vs_step(rho_bar)

    if fast:
        print("\n--fast: skipping the slow Gate B Nk-sweep figure.")
    else:
        print("\nRunning greedy Gate B sweep (slow: ~15-25 min)...")
        figure_gateB_nk_sweep(H, B, A, C_targets, avg)

    print("\nDone. Figures written to docs/figures/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
