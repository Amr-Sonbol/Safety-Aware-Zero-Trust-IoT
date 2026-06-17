"""Regenerate the Phase 1 (safety-aware decision function) documentation figures.

Run from the project root::

    python docs/make_phase1_figures.py            # all three figures (fast: ~30 s)
    python docs/make_phase1_figures.py --fast     # identical (no slow path here)

This script is **read-only** with respect to ``zt_cps_phase0/src`` — it imports the
exact Phase 1 contribution-layer code (``decision``, ``metrics``, ``node_profiles``,
``run_experiment``) and only *reads* from it. It re-runs the **fast** experiments
in-process (deterministic, seconds) to obtain both the scalar metrics and the
per-step ``pa(t)`` series, then writes three PNGs to ``docs/figures/`` and prints the
numbers it plotted so every figure is auditable against ``results/full_run.log``.

B2 (FENG greedy) is reproduced **without** re-running the ~20-min greedy search: its
validated Nk=10 hardened-node set is hard-coded
(``[13, 23, 7, 15, 12, 8, 5, 6, 3, 16]`` — the set ``run_experiment``'s greedy selects
under the 2000-sample policy slice, which reproduces the canonical
``results/Exp2_B2_Nk10.csv`` numbers M4=0.4671 / M2=0.088) and replayed as a fixed
deny/full policy — exactly what ``run_experiment.b2_fixed_decisions`` produces. (Note
this differs from the Phase 0 runner's Gate-B selection ``[…3, 6, 4, 10]``; the greedy
breaks late-round ties differently here, but both land in the validated Gate-B band.)

Figures
-------
1. ``phase1_tradeoff_bars.png``       — M1, M2, M4 (pa), and M7 observability fraction
                                         across the eight experiments; the safety-aware
                                         trade-off at a glance.
2. ``phase1_m5_action_dist.png``      — per-device-class action distribution (M5) for
                                         the proposed configs, stacked bars.
3. ``phase1_pa_vs_step_by_policy.png``— pa(t) over the 40-step horizon for B1, B2
                                         (Nk=10), and Proposed (alpha=0.8), showing how
                                         each policy bends the Gate-A bypass curve.
"""

from __future__ import annotations

import os
import sys

import numpy as np

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from zt_cps_phase0.src import config  # noqa: E402
from zt_cps_phase0.src import decision as dec  # noqa: E402
from zt_cps_phase0.src import metrics as mx  # noqa: E402
from zt_cps_phase0.src import node_profiles as npf  # noqa: E402
from zt_cps_phase0.src import run_experiment as rx  # noqa: E402

_FIG_DIR = os.path.join(_PROJECT_ROOT, "docs", "figures")
_DPI = 150

# B2 FENG greedy Nk=10 hardened-node set as selected by run_experiment's greedy under
# the 2000-sample policy slice; reproduces results/Exp2_B2_Nk10.csv (M4=0.4671).
_B2_NK10_NODES = [13, 23, 7, 15, 12, 8, 5, 6, 3, 16]

# Plot palette per action (used by the M5 stacked bars).
_ACTION_COLORS = {
    "full": "#2ca02c",
    "restricted": "#98df8a",
    "read_only": "#1f77b4",
    "safe_mode": "#ff7f0e",
    "deny": "#d62728",
}


def _run_policy_with_pa_series(model, decide_fn=None, fixed_decisions=None):
    """Run one 40-step experiment and return (logger, pa_series).

    Mirrors run_experiment.run_policy but also records the per-step pa(t) so the
    pa-vs-step figure does not need a second pass.
    """
    H, W, B, A = model["H"], model["W"], model["B"], model["A"]
    classes, C = model["classes"], model["C_targets"]
    profiles = npf.build_node_profiles(B, A, classes)
    logger = mx.MetricsLogger(H, W, classes)
    rng = np.random.default_rng(config.SEED + 1)
    rho = np.full(config.N_NODES, config.RHO0)
    compromised = np.zeros(config.N_NODES)
    pa_series = np.empty(config.N_STEPS)
    for t in range(config.N_STEPS):
        decisions = (fixed_decisions if fixed_decisions is not None
                     else decide_fn(profiles))
        rho, compromised, rec = dec.run_step(
            decisions, rho, compromised, B, H, A, C, rng
        )
        # Phase 1b: feed the latched compromise + previous pa so the next decision
        # sees the trust floor and the runtime process state P (mirrors run_policy).
        npf.update_profiles(profiles, rho, compromised, rec["pa"])
        logger.log_step(profiles, decisions, rec["pa"], rec["obs_mask"])
        pa_series[t] = rec["pa"]
    return logger, pa_series


def _collect():
    """Run every fast experiment in-process; return {label: (summary, M5, pa_series)}."""
    model = rx.build_model()
    b2_fixed = {i: ("deny" if i in set(_B2_NK10_NODES) else "full")
                for i in range(config.N_NODES)}
    specs = [
        ("B1", lambda p: rx.decide_B1(p), None),
        ("B3", lambda p: rx.decide_B3(p), None),
        ("B4(α=1)", lambda p: rx.decide_proposed(p, 1.0, 0.0), None),
        ("Prop α=0.8", lambda p: rx.decide_proposed(p, 0.8, 0.2), None),
        ("Prop α=0.5", lambda p: rx.decide_proposed(p, 0.5, 0.5), None),
        ("Prop α=0.2", lambda p: rx.decide_proposed(p, 0.2, 0.8), None),
        ("B2 Nk=10", None, b2_fixed),
    ]
    out = {}
    for label, fn, fixed in specs:
        logger, pa = _run_policy_with_pa_series(model, fn, fixed)
        out[label] = (logger.summary(), logger.M5(), pa)
        s = out[label][0]
        print(f"[collect] {label:12s} M1={s['M1']:.3f} M2={s['M2']:.4f} "
              f"M4={s['M4']:.4f} M7obs={s['M7_frac_observable']:.2f}")
    return out


def figure_tradeoff_bars(data):
    """Grouped bars: M1, M2, M4, M7obs across the experiments."""
    labels = list(data.keys())
    m1 = [data[l][0]["M1"] for l in labels]
    m2 = [data[l][0]["M2"] for l in labels]
    m4 = [data[l][0]["M4"] for l in labels]
    obs = [data[l][0]["M7_frac_observable"] for l in labels]

    x = np.arange(len(labels))
    w = 0.2
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.bar(x - 1.5 * w, m1, w, label="M1 (unsafe-denial rate ↓)", color="#d62728")
    ax.bar(x - 0.5 * w, m2, w, label="M2 (denial cost ↓)", color="#ff7f0e")
    ax.bar(x + 0.5 * w, m4, w, label="M4 (pa, bypass ↓)", color="#1f77b4")
    ax.bar(x + 1.5 * w, obs, w, label="M7 observable frac ↑", color="#2ca02c")
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=20, ha="right", fontsize=9)
    ax.set_ylabel("metric value")
    ax.set_title("Phase 1 trade-off: security (M4) vs. safety (M1/M2) vs. observability (M7)")
    ax.set_ylim(0, 1.05)
    ax.grid(axis="y", alpha=0.3)
    ax.legend(loc="upper center", ncol=4, fontsize=8, framealpha=0.9)
    fig.tight_layout()
    out = os.path.join(_FIG_DIR, "phase1_tradeoff_bars.png")
    fig.savefig(out, dpi=_DPI)
    plt.close(fig)
    print(f"[tradeoff_bars] wrote {out}")


def figure_m5_action_dist(data):
    """Stacked bars of per-class action fractions for the three proposed configs."""
    configs = ["Prop α=0.8", "Prop α=0.5", "Prop α=0.2"]
    classes = list(config.DEVICE_CLASSES)
    actions = list(config.ACTIONS)

    fig, axes = plt.subplots(1, 3, figsize=(13, 4.5), sharey=True)
    for ax, cfg in zip(axes, configs):
        m5 = data[cfg][1]
        bottoms = np.zeros(len(classes))
        for a in actions:
            vals = np.array([m5[c][a] for c in classes])
            ax.bar(range(len(classes)), vals, bottom=bottoms,
                   color=_ACTION_COLORS[a], label=a)
            bottoms += vals
        ax.set_title(cfg, fontsize=10)
        ax.set_xticks(range(len(classes)))
        ax.set_xticklabels([c.replace("PDP-", "") for c in classes],
                           rotation=35, ha="right", fontsize=8)
        ax.set_ylim(0, 1)
        ax.grid(axis="y", alpha=0.3)
    axes[0].set_ylabel("mean action fraction")
    handles, labs = axes[0].get_legend_handles_labels()
    fig.legend(handles, labs, loc="upper center", ncol=5, fontsize=9,
               bbox_to_anchor=(0.5, 1.02))
    fig.suptitle("M5: per-device-class action distribution (proposed method)", y=1.08)
    fig.tight_layout()
    out = os.path.join(_FIG_DIR, "phase1_m5_action_dist.png")
    fig.savefig(out, dpi=_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"[m5_action_dist] wrote {out}")


def figure_pa_vs_step(data):
    """pa(t) over the horizon: the headline Proposed alpha=0.5 vs B2 and the soft alpha=0.2."""
    steps = np.arange(config.N_STEPS)
    series = {
        "B2 greedy Nk=10": ("#d62728", data["B2 Nk=10"][2]),
        "Proposed α=0.5 (headline)": ("#1f77b4", data["Prop α=0.5"][2]),
        "Proposed α=0.2 (soft)": ("#7f7f7f", data["Prop α=0.2"][2]),
    }
    fig, ax = plt.subplots(figsize=(8.5, 4.5))
    for label, (color, pa) in series.items():
        ax.plot(steps, pa, marker="o", ms=3, lw=1.6, color=color,
                label=f"{label} (avg {pa.mean():.4f})")
    ax.axhline(config.GATE_A_TARGET, ls="--", color="#2ca02c", lw=1.0,
               label=f"undefended ceiling ≈ {config.GATE_A_TARGET}")
    ax.set_xlabel("simulation step  t")
    ax.set_ylabel("FDI bypass probability  pa")
    ax.set_title("pa(t) by policy: how each defense bends the bypass curve")
    ax.set_ylim(0, 1)
    ax.grid(alpha=0.3)
    ax.legend(loc="center right", fontsize=8)
    fig.tight_layout()
    out = os.path.join(_FIG_DIR, "phase1_pa_vs_step_by_policy.png")
    fig.savefig(out, dpi=_DPI)
    plt.close(fig)
    print(f"[pa_vs_step_by_policy] wrote {out}")


def main(argv: list[str]) -> int:
    os.makedirs(_FIG_DIR, exist_ok=True)
    print("Collecting fast experiments in-process (deterministic)...")
    data = _collect()
    print("\nRendering figures...")
    figure_tradeoff_bars(data)
    figure_m5_action_dist(data)
    figure_pa_vs_step(data)
    print("\nDone. Phase 1 figures written to docs/figures/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
