"""Phase C — sensitivity sweep over the latched-compromise trust floor T_LATCH_FLOOR.

E1: does the headline (alpha=0.5 chooses ``read_only`` on latched nodes, so M4 -> ~0
while M7obs stays 1.0) hold across a *band* of floor values, or only at the default
0.35? This script sweeps T_LATCH_FLOOR and reports where the read_only regime holds
and where it tips to ``deny`` (which re-blinds the EMS).

SAFETY (Phase C governing rule)
-------------------------------
``config.T_LATCH_FLOOR`` is read as a module global inside
``node_profiles.update_profiles`` (node_profiles.py:251) — there is no argument seam.
So this sweep uses the **read-restore pattern**: the original value is saved, set for
the duration of one run, and ALWAYS restored in a ``finally`` block. After the whole
sweep we assert ``config.T_LATCH_FLOOR == 0.35`` to prove the frozen default survived.
config.py itself is never edited; no existing source module is modified.

Determinism: every run uses the same engine/seed as Exp7 (``run_policy`` at
``config.SEED + 1``), so results are reproducible.

Run from the project root::

    python docs/make_sensitivity_figures.py
"""

from __future__ import annotations

import csv
import os
import sys

import numpy as np

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

import matplotlib

matplotlib.use("Agg")  # headless: write files, never open a window
import matplotlib.pyplot as plt

from zt_cps_phase0.src import (
    config,
    decision as dec,
    node_profiles as npf,
    run_experiment as re,
)

# The frozen default we must restore to (asserted at the end).
DEFAULT_FLOOR = 0.35

# Sweep grid: the requested values plus 0.33, 0.37 for finer resolution near default.
FLOORS = [0.15, 0.20, 0.25, 0.30, 0.33, 0.35, 0.37, 0.40, 0.45, 0.50]

# The three configs, so the whole picture moves coherently.
ALPHAS = [(0.8, 0.2), (0.5, 0.5), (0.2, 0.8)]


def dominant_latched_action(model: dict, alpha: float, beta: float) -> str:
    """Re-run the policy and return the most common action on latched nodes at the
    final step.

    Mirrors ``run_experiment.run_policy`` exactly (same engine, same seed SEED+1),
    but additionally tracks the latched-compromise mask so we can read what the policy
    *does* to latched nodes — the read_only vs deny question E1 asks. Reads only;
    mutates nothing outside its own locals.
    """
    H, B, A = model["H"], model["B"], model["A"]
    C = model["C_targets"]
    profiles = npf.build_node_profiles(B, A, model["classes"])
    rng = np.random.default_rng(config.SEED + 1)
    rho = np.full(config.N_NODES, config.RHO0)
    compromised = np.zeros(config.N_NODES)
    last_decisions: dict[int, str] = {}
    last_compromised = compromised

    for _ in range(config.N_STEPS):
        decisions = {p["node_id"]: dec.select_action(p, alpha, beta) for p in profiles}
        rho, compromised, rec = dec.run_step(
            decisions, rho, compromised, B, H, A, C, rng
        )
        npf.update_profiles(profiles, rho, compromised, rec["pa"])
        last_decisions = decisions
        last_compromised = compromised

    latched = [i for i in range(config.N_NODES) if last_compromised[i] > 0]
    if not latched:
        return "none"
    actions = [last_decisions[i] for i in latched]
    # most common action among latched nodes
    return max(set(actions), key=actions.count)


def run_at_floor(model: dict, floor: float) -> dict:
    """Run all three configs at one floor value via read-restore. ALWAYS restores."""
    original = config.T_LATCH_FLOOR
    try:
        config.T_LATCH_FLOOR = floor
        row = {"floor": floor}
        for alpha, beta in ALPHAS:
            logger = re.run_policy(model, lambda p, a=alpha, b=beta: {
                pr["node_id"]: dec.select_action(pr, a, b) for pr in p
            })
            s = logger.summary()
            dom = dominant_latched_action(model, alpha, beta)
            tag = f"a{alpha}"
            row[f"{tag}_M4"] = s["M4"]
            row[f"{tag}_M7obs"] = s["M7_frac_observable"]
            row[f"{tag}_dom"] = dom
        return row
    finally:
        config.T_LATCH_FLOOR = original  # restore even on crash


def main() -> None:
    print("Phase C / E1 — T_LATCH_FLOOR sensitivity sweep")
    print(f"  frozen default = {DEFAULT_FLOOR}; grid = {FLOORS}")
    print(f"  (config.T_LATCH_FLOOR at start = {config.T_LATCH_FLOOR})\n")

    model = re.build_model()
    rows = [run_at_floor(model, f) for f in FLOORS]

    # --- write CSV --------------------------------------------------------- #
    outdir = os.path.join(_PROJECT_ROOT, "results")
    os.makedirs(outdir, exist_ok=True)
    csv_path = os.path.join(outdir, "sweep_tlatch.csv")
    fields = ["floor"]
    for alpha, _ in ALPHAS:
        fields += [f"a{alpha}_M4", f"a{alpha}_M7obs", f"a{alpha}_dom"]
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"[sweep_tlatch] wrote {csv_path}\n")

    # --- printed table for alpha=0.5 (the headline) ----------------------- #
    print("alpha=0.5 (balanced) — floor -> (M4, M7obs, dominant latched action)")
    print(f"  {'floor':>6} {'M4':>10} {'M7obs':>7}  dominant_latched_action")
    for r in rows:
        marker = "  <- default" if abs(r["floor"] - DEFAULT_FLOOR) < 1e-9 else ""
        print(f"  {r['floor']:6.2f} {r['a0.5_M4']:10.5f} "
              f"{r['a0.5_M7obs']:7.2f}  {r['a0.5_dom']}{marker}")

    # --- figure: M4 and M7obs vs floor for alpha=0.5 ----------------------- #
    floors = [r["floor"] for r in rows]
    m4 = [r["a0.5_M4"] for r in rows]
    m7 = [r["a0.5_M7obs"] for r in rows]
    dom = [r["a0.5_dom"] for r in rows]

    fig, ax1 = plt.subplots(figsize=(8, 5))
    ax1.set_xlabel("T_LATCH_FLOOR")
    ax1.set_ylabel("M4 (bypass probability pa)", color="tab:blue")
    ax1.plot(floors, m4, "o-", color="tab:blue", label="M4 (pa)")
    ax1.tick_params(axis="y", labelcolor="tab:blue")
    ax1.set_ylim(-0.05, 1.05)

    ax2 = ax1.twinx()
    ax2.set_ylabel("M7 frac_observable", color="tab:green")
    ax2.plot(floors, m7, "s--", color="tab:green", label="M7obs")
    ax2.tick_params(axis="y", labelcolor="tab:green")
    ax2.set_ylim(-0.05, 1.05)

    # mark the read_only -> deny transition (first floor whose dominant action is deny)
    transition = None
    for i in range(1, len(dom)):
        if dom[i] == "deny" and dom[i - 1] != "deny":
            transition = (floors[i - 1] + floors[i]) / 2.0
            break
    if transition is not None:
        ax1.axvline(transition, color="tab:red", ls=":", lw=1.5)
        ax1.text(transition, 0.5, "  read_only -> deny",
                 color="tab:red", rotation=90, va="center", fontsize=9)
    ax1.axvline(DEFAULT_FLOOR, color="gray", ls="-", lw=0.8, alpha=0.6)
    ax1.text(DEFAULT_FLOOR, 1.02, "default 0.35", color="gray",
             ha="center", fontsize=8)

    ax1.set_title("E1: alpha=0.5 sensitivity to T_LATCH_FLOOR\n"
                  "(M4 collapsed + M7obs=1.0 = the read_only regime)")
    fig.tight_layout()
    fig_path = os.path.join(_PROJECT_ROOT, "docs", "figures", "fig_tlatch_sweep.png")
    fig.savefig(fig_path, dpi=120)
    plt.close(fig)
    print(f"\n[fig_tlatch_sweep] wrote {fig_path}")

    # --- PROVE the frozen default survived --------------------------------- #
    assert config.T_LATCH_FLOOR == DEFAULT_FLOOR, (
        f"T_LATCH_FLOOR corrupted: {config.T_LATCH_FLOOR} != {DEFAULT_FLOOR}"
    )
    print(f"\n[restore-proof] config.T_LATCH_FLOOR == {DEFAULT_FLOOR}  -> ASSERTION PASSED")


if __name__ == "__main__":
    main()
