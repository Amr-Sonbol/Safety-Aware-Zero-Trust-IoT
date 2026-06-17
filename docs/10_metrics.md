# 10 — Metrics M1–M7

Phase 1 reduces each 40-step experiment to seven metrics. **M1–M6 are reproduced verbatim** from the v4
contribution-layer specification; **M7 is the new, independent physical-observability axis**, added by D2,
that reuses the frozen Phase 0 `build_H` / `build_R`. This chapter defines each metric, says what it measures
and which direction is better, separates the optimizer's *own objective terms* from the *independent* axes,
and documents the CSV export. The implementation is `metrics.py` (`MetricsLogger` + `M1()…M7()`).

The numbers quoted here are read directly from `results/Exp*.csv` (produced by
`python -m zt_cps_phase0.src.run_experiment --full`).

> **Phase 1b note (what changed for the metrics).** The denial-cost the safety metrics read is now the
> IEC-weighted **$S_\text{deny}$** (Task 5) rather than the equal-weight $\mathrm{DC}$: wherever "$\mathrm{DC}$"
> appears below in **M1**'s high-criticality gate and **M2**'s cost, the code reads $S_\text{deny}$ when
> `config.USE_S_DENY` is True (the default). $S_\text{deny} = 0.35 H_s + 0.25 D_c + 0.20 A + 0.15 P + 0.05 O$
> folds in the **runtime process state $P$** at weight 0.15, so the denial cost is now phase-aware. The CSV
> also gains the dynamic profile fields used to compute it. M3–M7 are unchanged in form. The "Reading it"
> commentary below is updated for the Phase 1b run (the headline config is now $\alpha{=}0.5$).

---

## Why two kinds of metric (and why M7 matters)

The decision function *optimizes* $\alpha R_\text{sec} + \beta R_\text{saf}$. Two metrics, **M2** and **M3**,
are essentially the aggregated $R_\text{saf}$ and $R_\text{sec}$ terms — they are the optimizer's *own
objective*, so a method scoring well on them is partly circular. The **independent** axes — the ones a method
cannot trivially game because it is not optimizing them directly — are:

- **M1** (does it deny nodes it should still trust?),
- **M4** (the actual attacker bypass probability $pa$, from the Phase 0 engine),
- **M7** (the *physical* cost: did the defense keep the grid observable?).

**M7 is the crux of the Phase 1 claim.** A defense can drive $pa$ to zero by denying everything — but then the
operator's state estimator goes blind, which in a real grid is itself a safety failure. M7 measures that, so
"good security" and "preserved visibility" can be reported as the genuine trade-off they are.

---

## The seven metrics

Notation: index $t$ runs over the 40 steps; $i$ over the 55 nodes; $a_i$ is node $i$'s action at step $t$,
with coefficients $\gamma_{a_i}, \delta_{a_i}$; $T_i$, $\mathrm{DC}_i$, $\mathrm{ASC}_i$ from the profile.

### M1 — high-safety denial rate ↓ *(independent)*

$$ \mathrm{M1} = \frac{\#\{(t,i): a_i=\texttt{deny}\ \wedge\ \mathrm{DC}_i>0.5\ \wedge\ T_i>0.3\}}{\#\{(t,i): a_i=\texttt{deny}\ \wedge\ \mathrm{DC}_i>0.5\}}. $$

**What it measures:** of the denials applied to *high-criticality* nodes, what fraction hit a node that was
**still reasonably trusted** ($T>0.3$)? A safety-aware method should deny a costly node only once it is
genuinely untrusted, so **lower is better**. If there are no high-DC denials at all, M1 is defined as 0.

> **Reading it (Phase 1b).** M1 = 1.0 (B1, B4, B2, Proposed $\alpha=0.8$) means *every* high-cost denial hit a
> node still above the $T>0.3$ line — an aggressive denial pattern. M1 = 0.0 (B3, Proposed $\alpha=0.5/0.2$)
> means no premature high-cost denials. The headline $\alpha{=}0.5$ scores **M1 = 0** because it *restricts*
> (`read_only`) high-criticality nodes rather than denying them — so it never trips the "deny a still-trusted
> costly node" condition, even though the trust floor ([12](12_phase1_divergences.md)) has pushed latched
> nodes well below 1.

### M2 — aggregate denial cost ↓ *(objective term — $R_\text{saf}$)*

$$ \mathrm{M2} = \frac1{40}\sum_t \frac1{55}\sum_i \mathrm{DC}_i\,\delta_{a_i}. $$

**What it measures:** the average safety cost incurred by the actions taken (criticality × hardening, summed
over nodes, averaged over steps). **Lower is better.** This is the $R_\text{saf}$ the optimizer minimizes,
so treat it as descriptive, not as independent evidence.

### M3 — security risk exposure *(objective term — $R_\text{sec}$)*

$$ \mathrm{M3} = \frac1{40}\sum_t \frac1{55}\sum_i (1-T_i)\,\mathrm{ASC}_i\,\gamma_{a_i}. $$

**What it measures:** the residual attack exposure left after the actions (untrust × surface × retained
command). Lower means less exposure, but again this is the optimizer's own $R_\text{sec}$ term.

### M4 — FDI bypass probability ↓ *(independent — the Phase 0 metric)*

$$ \mathrm{M4} = \frac1{40}\sum_t pa(t), \qquad pa(t)=\texttt{compute\_pa}(C, H, A, \text{injectable}(t)). $$

**What it measures:** the mean attacker bypass probability over the horizon, where the *injectable* set is the
action-gated compromised set (security channel, [09 §C.1](09_decision_model.md)). This is the **same
`compute_pa`** that produced Phase 0's Gate A — see the fidelity guarantee below. **Lower is better.**

### M5 — action distribution *(descriptive)*

Per device class, the mean-over-steps fraction of each of the five actions. Returned as a nested dict
`{class: {action: fraction}}`; each class's five fractions sum to 1. **No "better" direction** — it is the
*explanation* of the other metrics: it shows *which* nodes the method restricts. Visualized in
[11](11_phase1_results.md) (the stacked-bar figure).

### M6 — mean trust at denial *(appendix sanity check)*

$$ \mathrm{M6} = \operatorname{mean}\{T_i : a_i=\texttt{deny}\}. $$

The average trust of nodes at the moment they were denied. A pure sanity check: a security-leaning method
denies at higher trust (B2 M6 = 0.94, B4 M6 = 0.99), a more patient one at lower trust (Proposed
$\alpha=0.8$ M6 = 0.60).

### M7 — physical observability cost ↑(obs frac) / ↓(inflation) *(independent — the safety axis)*

Per step, from the observed measurement matrix $H_\text{obs}$ (the rows kept by the safety channel,
[09 §C.2](09_decision_model.md)):

$$ \text{observable}(t) = \big[\operatorname{rank}(H_\text{obs}) = 29\big], \qquad
   \text{inflation}(t) = \frac{\operatorname{tr}\!\big((H_\text{obs}^\top W_\text{obs} H_\text{obs})^{-1}\big)}{\operatorname{tr}\!\big((H^\top W H)^{-1}\big)} \ge 1. $$

M7 reports two summary numbers: **`frac_observable`** (fraction of the 40 steps that stayed observable —
**higher is better**) and **`mean_inflation`** (mean estimation-covariance inflation over the *observable*
steps — **lower is better**, 1.0 = no cost; the non-observable steps' $\infty$ is excluded so the mean is
finite). $H$ and $W = R^{-1}$ are built once from the frozen Phase 0 `build_H` / `build_R`.

> **What it means physically.** `frac_observable = 1.0, inflation = 1.0` means the operator can still
> reconstruct the full grid state with no loss of precision. `frac_observable = 0.0` (B2, B4) means
> $H_\text{obs}$ lost full column rank at *every* step — the state estimator **cannot uniquely solve for the
> bus angles**; the operator is flying blind exactly when under attack.

---

## The channel-fidelity guarantee

The strongest internal check on Phase 1 lives in `test_metrics.py`. An **all-`full`** policy run over the 40
steps, seeded identically to the Phase 0 runner (`SEED+1`):

- has `injectable == compromised` (every node keeps its write path), so its $pa(t)$ is *identical* to a
  direct `update_worm → sample_compromise → compute_pa` loop **recomputed inside the test on the same seed**
  — verified to $|{\Delta}| < 10^{-12}$. This certifies the Phase 1 pipeline adds **no numerical drift** to the
  Phase 0 engine; the test does **not** pin `M4` to the runner's stored `0.7408`. It separately asserts that
  `M4` lands in the Gate A band $[0.70, 0.80]$ (and in practice equals the runner's 0.7408, since the seed and
  engine are identical);
- keeps every measurement row, so $H_\text{obs} = H$ ⇒ `frac_observable = 1.0`, `inflation = 1.0`.

This proves the Phase 1 wiring rides *exactly* on the validated Phase 0 engine — the decision layer adds
gating, it does not re-derive the physics. (A tiny consequence: a policy that denies even one node, like B1
late in the horizon, shows `inflation = 1.0002` — a few rows dropped but rank preserved. The headline table
rounds to 1.000.)

---

## CSV export format

`MetricsLogger.export_csv(path, label)` writes two blocks (one file per experiment, in `results/`):

```
experiment,<label>
metric,value
M1,<float>
M2,<float>
M3,<float>
M4,<float>
M6,<float>
M7_mean_inflation,<float or inf>
M7_frac_observable,<float>

M5_class,action,fraction
C-PDP-critical,full,<float>
C-PDP-critical,restricted,<float>
…                                  (5 classes × 5 actions = 25 rows)
```

M4 is the headline security number; M7's two fields are the safety axis; the M5 block is the per-class action
breakdown the figures visualize. (M5 is not a single scalar, so it lives in its own block, not the
`metric,value` summary.)

Next: [11 — Phase 1 results & validation](11_phase1_results.md), where these metrics are reported across all
eight experiments with a physical interpretation per row.
