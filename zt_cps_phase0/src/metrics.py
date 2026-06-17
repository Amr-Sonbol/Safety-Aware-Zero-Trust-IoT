"""Phase 1 metrics M1-M7 and CSV export.

A :class:`MetricsLogger` accumulates one record per simulation step (the node
profiles as seen that step, the chosen actions, the bypass probability ``pa``, and
the observed-measurement row mask), then reduces them to the seven metrics defined
in spec §6. M1-M6 are reproduced verbatim from the v4 contribution layer; M7 is the
new, independent physical-observability axis and reuses the **frozen Phase 0**
:func:`power_system.build_H` / :func:`power_system.build_R`.

Metric summary (all averaged over the 40-step horizon unless noted)
-------------------------------------------------------------------
* **M1** high-safety denial rate ``count(deny ∧ DC>0.5 ∧ T>0.3)/count(deny ∧ DC>0.5)`` — lower better.
* **M2** aggregate denial cost ``mean_t sum_i(DC_i·delta_i)/55`` — lower better.
* **M3** security risk exposure ``mean_t sum_i((1-T_i)·ASC_i·gamma_i)/55``.
* **M4** FDI bypass ``mean_t pa`` (the optimizer feeds the action-gated set; D1).
* **M5** action distribution: fraction of each action per device class per step.
* **M6** mean trust ``T`` at the moment of denial (appendix sanity check).
* **M7** physical observability cost from ``H_obs``: ``observable=(rank==29)`` and
  ``est_inflation = trace((H_obsᵀ W H_obs)⁻¹)/trace((Hᵀ W H)⁻¹)`` (>=1).
"""

from __future__ import annotations

import csv

import numpy as np

from . import config


def _delta(action: str) -> float:
    """delta_a = 1 - (O_a + C_a)/2 for an action."""
    spec = config.ACTIONS[action]
    return 1.0 - (spec["O"] + spec["C"]) / 2.0


def observability_cost(
    H: np.ndarray,
    W: np.ndarray,
    obs_mask: np.ndarray,
) -> tuple[bool, float]:
    """M7 kernel: is the still-observed system observable, and by how much is the
    estimation covariance inflated relative to the all-observed baseline?

    Parameters
    ----------
    H : numpy.ndarray, shape (M, N)
        The full Phase 0 measurement matrix.
    W : numpy.ndarray, shape (M, M)
        The full inverse-noise weight ``R^{-1}`` (Phase 0 ``build_R`` inverse).
    obs_mask : numpy.ndarray, shape (M,)
        Boolean mask of rows still reported to the EMS (the safety channel).

    Returns
    -------
    observable : bool
        ``True`` iff ``H_obs`` retains full column rank (N = 29) — the state is
        still uniquely estimable from the reported measurements.
    est_inflation : float
        ``trace((H_obsᵀ W_obs H_obs)⁻¹) / trace((Hᵀ W H)⁻¹)`` (>= 1). ``inf`` if not
        observable (the information matrix is singular). 1.0 when every row is kept.
    """
    rows = np.where(obs_mask)[0]
    n = H.shape[1]
    H_full_info = H.T @ W @ H
    base_trace = float(np.trace(np.linalg.inv(H_full_info)))

    if rows.size < n:
        return False, float("inf")
    H_obs = H[rows, :]
    W_obs = W[np.ix_(rows, rows)]
    rank = int(np.linalg.matrix_rank(H_obs, tol=config.RANK_TOL))
    if rank < n:
        return False, float("inf")
    info = H_obs.T @ W_obs @ H_obs
    obs_trace = float(np.trace(np.linalg.inv(info)))
    return True, obs_trace / base_trace


class MetricsLogger:
    """Accumulate per-step records and reduce them to M1-M7.

    Parameters
    ----------
    H : numpy.ndarray, shape (M, N)
        Frozen Phase 0 measurement matrix (for M7).
    W : numpy.ndarray, shape (M, M)
        Frozen Phase 0 inverse-noise weight ``R^{-1}`` (for M7).
    classes : dict[int, str]
        Node-id -> device class (for the M5 per-class distribution).
    """

    def __init__(self, H: np.ndarray, W: np.ndarray, classes: dict[int, str]) -> None:
        self.H = H
        self.W = W
        self.classes = classes
        self.steps: list[dict] = []

    def log_step(
        self,
        profiles: list[dict],
        decisions: dict[int, str],
        pa: float,
        obs_mask: np.ndarray,
    ) -> None:
        """Record one step.

        Parameters
        ----------
        profiles : list[dict]
            Node profiles as seen this step (carry current ``T`` and fixed
            ``DC``/``ASC``).
        decisions : dict[int, str]
            Per-node actions chosen this step.
        pa : float
            Step bypass probability (M4).
        obs_mask : numpy.ndarray, shape (M,)
            Observed-measurement row mask (M7 input).
        """
        observable, inflation = observability_cost(self.H, self.W, obs_mask)
        # Snapshot the per-node quantities the metrics need (T is dynamic).
        node_T = np.array([p["T"] for p in profiles], dtype=float)
        node_DC = np.array([p["DC"] for p in profiles], dtype=float)
        node_ASC = np.array([p["ASC"] for p in profiles], dtype=float)
        # Phase 1b: the safety-cost the denial metrics read is the IEC-weighted
        # S_deny when active (Task 5), else the equal-weight DC. M1's "high
        # criticality" gate and M2's denial cost both use this consistently.
        if config.USE_S_DENY and all("S_deny" in p for p in profiles):
            node_cost = np.array([p["S_deny"] for p in profiles], dtype=float)
        else:
            node_cost = node_DC
        actions = [decisions[i] for i in range(len(profiles))]
        node_gamma = np.array([config.ACTIONS[a]["gamma"] for a in actions], dtype=float)
        node_delta = np.array([_delta(a) for a in actions], dtype=float)
        self.steps.append({
            "T": node_T, "DC": node_DC, "ASC": node_ASC, "cost": node_cost,
            "gamma": node_gamma, "delta": node_delta,
            "actions": actions, "pa": float(pa),
            "observable": observable, "inflation": inflation,
        })

    # --- the seven metrics --------------------------------------------------

    def M1(self) -> float:
        """High-safety denial rate: deny on a high-cost, still-trusted node. Lower better.

        ``count(deny ∧ cost>0.5 ∧ T>0.3) / count(deny ∧ cost>0.5)``; 0.0 if the
        denominator is empty (no high-cost denials at all). ``cost`` is the
        IEC-weighted ``S_deny`` when active (Task 5), else the equal-weight ``DC``.
        """
        num = den = 0
        for s in self.steps:
            for i, a in enumerate(s["actions"]):
                if a == "deny" and s["cost"][i] > 0.5:
                    den += 1
                    if s["T"][i] > 0.3:
                        num += 1
        return (num / den) if den > 0 else 0.0

    def M2(self) -> float:
        """Aggregate denial cost: ``mean_t sum_i(cost_i·delta_i)/55``. Lower better.

        ``cost`` is the IEC-weighted ``S_deny`` when active (Task 5), else ``DC``.
        """
        per = [float(np.sum(s["cost"] * s["delta"]) / config.N_NODES) for s in self.steps]
        return float(np.mean(per)) if per else 0.0

    def M3(self) -> float:
        """Security risk exposure: ``mean_t sum_i((1-T_i)·ASC_i·gamma_i)/55``."""
        per = [
            float(np.sum((1.0 - s["T"]) * s["ASC"] * s["gamma"]) / config.N_NODES)
            for s in self.steps
        ]
        return float(np.mean(per)) if per else 0.0

    def M4(self) -> float:
        """FDI bypass: mean ``pa`` over the horizon."""
        per = [s["pa"] for s in self.steps]
        return float(np.mean(per)) if per else 0.0

    def M5(self) -> dict[str, dict[str, float]]:
        """Action distribution: mean over steps of the per-class action fraction.

        Returns ``{device_class: {action: fraction}}`` averaged over all steps.
        """
        class_nodes: dict[str, list[int]] = {c: [] for c in config.DEVICE_CLASSES}
        for node, c in self.classes.items():
            class_nodes[c].append(node)

        # accumulate per-step fractions, then average
        accum = {c: {a: 0.0 for a in config.ACTIONS} for c in config.DEVICE_CLASSES}
        for s in self.steps:
            for c, nodes in class_nodes.items():
                if not nodes:
                    continue
                counts = {a: 0 for a in config.ACTIONS}
                for i in nodes:
                    counts[s["actions"][i]] += 1
                for a in config.ACTIONS:
                    accum[c][a] += counts[a] / len(nodes)
        n_steps = max(len(self.steps), 1)
        return {
            c: {a: accum[c][a] / n_steps for a in config.ACTIONS}
            for c in config.DEVICE_CLASSES
        }

    def M6(self) -> float:
        """Mean trust ``T`` at the moment of denial (appendix sanity)."""
        ts = [s["T"][i] for s in self.steps
              for i, a in enumerate(s["actions"]) if a == "deny"]
        return float(np.mean(ts)) if ts else 0.0

    def M7(self) -> dict[str, float]:
        """Physical observability cost.

        Returns
        -------
        dict
            ``mean_inflation`` (mean ``est_inflation`` over the observable steps; the
            ``inf`` from non-observable steps is excluded so the mean is finite) and
            ``frac_observable`` (fraction of steps that stayed observable). Lower
            ``mean_inflation`` and higher ``frac_observable`` = better physical
            visibility preserved.
        """
        infl = [s["inflation"] for s in self.steps if s["observable"]]
        n_steps = max(len(self.steps), 1)
        frac_obs = sum(1 for s in self.steps if s["observable"]) / n_steps
        mean_infl = float(np.mean(infl)) if infl else float("inf")
        return {"mean_inflation": mean_infl, "frac_observable": frac_obs}

    def summary(self) -> dict:
        """Return all scalar metrics in one dict (M5 collapsed for CSV)."""
        m7 = self.M7()
        return {
            "M1": self.M1(),
            "M2": self.M2(),
            "M3": self.M3(),
            "M4": self.M4(),
            "M6": self.M6(),
            "M7_mean_inflation": m7["mean_inflation"],
            "M7_frac_observable": m7["frac_observable"],
        }

    def export_csv(self, path: str, label: str = "") -> None:
        """Write the scalar metric summary (and per-class M5) to ``path``.

        Two sections are written: a ``metric,value`` block for M1-M7, then an
        ``M5`` block of ``class,action,fraction`` rows.

        Parameters
        ----------
        path : str
            Output CSV path.
        label : str
            Optional experiment label written as the first row.
        """
        summary = self.summary()
        m5 = self.M5()
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            if label:
                w.writerow(["experiment", label])
            w.writerow(["metric", "value"])
            for k, v in summary.items():
                w.writerow([k, v])
            w.writerow([])
            w.writerow(["M5_class", "action", "fraction"])
            for c, dist in m5.items():
                for a, frac in dist.items():
                    w.writerow([c, a, frac])
