"""Phase C / E3 — why B1, B3, and Proposed alpha=0.5 report the SAME M4 (0.0015525).

Claim under test: the shared M4 is mechanistic, not a coincidence or hardcode. Per
step t each policy gates the latched-compromise set by the action's write-path
coefficient (injectable = compromised AND gamma_a >= C3_GAMMA_MIN). If, once the
worm saturates, the three policies' *injectable* sets coincide step-for-step, then
since compute_pa is deterministic the same input yields the same pa(t) — so the
40-step averages coincide.

This script reads only. It reuses the frozen engine and the same seed as Exp7
(SEED+1) and the real ``dec.run_step`` (whose record exposes the gated ``injectable``
array and ``pa``). No source module, test, runner, or config is modified.

Run from the project root::

    python docs/make_injectable_overlap.py
"""

from __future__ import annotations

import csv
import os
import sys

import numpy as np

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from zt_cps_phase0.src import (
    config,
    decision as dec,
    node_profiles as npf,
    run_experiment as re,
)


def _decide_B1(profiles):
    return {p["node_id"]: ("deny" if p["T"] < 0.5 else "full") for p in profiles}


def _decide_B3(profiles):
    out = {}
    for p in profiles:
        T = p["T"]
        if T > 0.7:
            a = "full"
        elif T > 0.5:
            a = "restricted"
        elif T > 0.35:
            a = "read_only"
        elif T > 0.2:
            a = "safe_mode"
        else:
            a = "deny"
        out[p["node_id"]] = a
    return out


def _decide_a05(profiles):
    return {p["node_id"]: dec.select_action(p, 0.5, 0.5) for p in profiles}


def run_logging_injectable(model, decide_fn):
    """Mirror run_experiment.run_policy exactly, but capture per-step injectable+pa.

    Returns (injectable_sets, pas): injectable_sets[t] is a frozenset of node indices
    with a retained write path at step t; pas[t] is that step's bypass probability.
    """
    H, B, A = model["H"], model["B"], model["A"]
    C = model["C_targets"]
    profiles = npf.build_node_profiles(B, A, model["classes"])
    rng = np.random.default_rng(config.SEED + 1)
    rho = np.full(config.N_NODES, config.RHO0)
    compromised = np.zeros(config.N_NODES)

    inj_sets, pas = [], []
    for _ in range(config.N_STEPS):
        decisions = decide_fn(profiles)
        rho, compromised, rec = dec.run_step(
            decisions, rho, compromised, B, H, A, C, rng
        )
        inj = rec["injectable"]  # gated (55,) array fed to compute_pa
        inj_sets.append(frozenset(int(i) for i in np.where(inj > 0)[0]))
        pas.append(float(rec["pa"]))
        npf.update_profiles(profiles, rho, compromised, rec["pa"])
    return inj_sets, pas


def main() -> None:
    print("Phase C / E3 — injectable-set overlap for B1, B3, Proposed alpha=0.5\n")
    model = re.build_model()

    inj_b1, pa_b1 = run_logging_injectable(model, _decide_B1)
    inj_b3, pa_b3 = run_logging_injectable(model, _decide_B3)
    inj_a5, pa_a5 = run_logging_injectable(model, _decide_a05)

    outdir = os.path.join(_PROJECT_ROOT, "results")
    os.makedirs(outdir, exist_ok=True)
    csv_path = os.path.join(outdir, "injectable_overlap.csv")

    n_identical = 0
    pa_match_where_identical = True
    rows = []
    for t in range(config.N_STEPS):
        identical = (inj_b1[t] == inj_b3[t] == inj_a5[t])
        if identical:
            n_identical += 1
            # where the gated input coincides, deterministic compute_pa must agree
            if not (abs(pa_b1[t] - pa_b3[t]) < 1e-15
                    and abs(pa_b1[t] - pa_a5[t]) < 1e-15):
                pa_match_where_identical = False
        rows.append({
            "step": t,
            "n_inj_B1": len(inj_b1[t]),
            "n_inj_B3": len(inj_b3[t]),
            "n_inj_a0.5": len(inj_a5[t]),
            "sets_identical": identical,
            "pa_B1": pa_b1[t],
            "pa_B3": pa_b3[t],
            "pa_a0.5": pa_a5[t],
        })

    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"[injectable_overlap] wrote {csv_path}\n")

    # compact printed view
    print(f"  {'step':>4} {'|B1|':>5} {'|B3|':>5} {'|a0.5|':>6} {'ident?':>7} "
          f"{'pa_B1':>9} {'pa_B3':>9} {'pa_a0.5':>9}")
    for r in rows:
        print(f"  {r['step']:4d} {r['n_inj_B1']:5d} {r['n_inj_B3']:5d} "
              f"{r['n_inj_a0.5']:6d} {str(r['sets_identical']):>7} "
              f"{r['pa_B1']:9.5f} {r['pa_B3']:9.5f} {r['pa_a0.5']:9.5f}")

    m4_b1 = float(np.mean(pa_b1))
    m4_b3 = float(np.mean(pa_b3))
    m4_a5 = float(np.mean(pa_a5))
    print(f"\n  identical injectable sets at {n_identical}/{config.N_STEPS} steps")
    print(f"  pa(t) identical wherever the sets coincide: {pa_match_where_identical}")
    print(f"  M4 (40-step mean):  B1={m4_b1:.7f}  B3={m4_b3:.7f}  a0.5={m4_a5:.7f}")
    print(f"  M4 all three equal: "
          f"{abs(m4_b1 - m4_b3) < 1e-12 and abs(m4_b1 - m4_a5) < 1e-12}")


if __name__ == "__main__":
    main()
