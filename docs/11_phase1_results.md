# 11 — Phase 1 Results & Validation

This chapter reports the measured **Phase 1b** results: the eight experiments and four ablations, the
trade-off table with a **physical interpretation of every number**, the Milestone 2 acceptance gate and its
honest verdict, the three generated figures, and the 41 new unit tests. It is the analogue of
[04](04_results_and_validation.md) for the contribution layer. Every number is read from `results/Exp*.csv`
and `results/phase1b_full_run.log`, produced by `python -m zt_cps_phase0.src.run_experiment --full`.

These numbers reflect the Phase 1b enrichment (runtime process-state **P**, the latched-compromise **trust
floor** at `T_LATCH_FLOOR=0.35`, IEC-weighted **S_deny**, and the **restricted** write-path fix); they
supersede the original Phase 1 table. The hard contract held throughout: **`run_phase0.py` still passes all
six gates and pytest reports 58 tests passed**. (The suite has no clean per-phase split: `test_topology.py`
and `test_metrics.py` mix Phase 0 invariants with Phase 1/1b ones, so we report the true total — 58 — rather
than a phase breakdown.) Phase 0 was never modified, and the
channel-fidelity guarantee (all-`full` ⇒ M4 = 0.7408 to $10^{-12}$) still holds.

---

## 1. The experiments

Each experiment runs one policy through the *same* engine, the *same* two D1 channels, and the *same*
$\delta=0.40$ denial — so any metric difference comes only from **how the policy chooses actions**.

| # | Label | Policy rule |
|---|---|---|
| Exp1 | **B1** binary ZT | `deny if T<0.5 else full` (no DC, no soft actions) |
| Exp2 | **B2** FENG greedy $N_k{=}10$ | Phase 0 `greedy_search` picks 10 nodes; those `deny` every step, rest `full` |
| Exp3 | **B2** FENG greedy $N_k{=}15$ | as Exp2 with 15 nodes |
| Exp4 | **B3** naive 5-action | fixed trust thresholds (>0.7 full, >0.5 restricted, >0.35 read-only, >0.2 safe-mode, else deny); DC ignored |
| Exp5 | **B4** security-only | proposed `select_action` with $(\alpha,\beta)=(1,0)$ |
| Exp6 | **Proposed** $\alpha{=}0.8$ | `select_action` with $(0.8,0.2)$ |
| Exp7 | **Proposed** $\alpha{=}0.5$ | `select_action` with $(0.5,0.5)$ |
| Exp8 | **Proposed** $\alpha{=}0.2$ | `select_action` with $(0.2,0.8)$ |

B2 is modeled in this framework as a static deny/full policy: the greedy search (the slow Phase 0 path) picks
the hardened-node set once, then those nodes are `deny`-ed every step — which is exactly partial hardening at
$\delta=0.40$, so B2's M4 reproduces its Phase 0 Gate-B behaviour, while also acquiring M1/M2/M7 in the
common framework.

---

## 2. The trade-off table

> **Phase 1b update.** These numbers are the post-Phase-1b run (runtime process-state **P** + the
> latched-compromise **trust floor** + IEC-weighted **S_deny** + the **restricted** write-path fix). They
> supersede the original Phase 1 table. The headline config moved from $\alpha{=}0.8$ to **$\alpha{=}0.5$**:
> giving the trust signal real range made $\alpha{=}0.8$ over-deny (and blind the EMS), while the *balanced*
> $\alpha{=}0.5$ became the policy that collapses $pa$ **and** keeps full observability. See
> [12 Divergence 3](12_phase1_divergences.md) for the before/after.

| Experiment | M1 ↓ | M2 ↓ | M3 | M4 ($pa$) ↓ | M7 infl | M7 obs ↑ |
|---|---|---|---|---|---|---|
| Exp1 B1 binary ZT | 1.0000 | 0.2926 | 0.0207 | 0.0016 | 1.000 | 0.025 |
| Exp4 B3 naive 5-action | 0.0000 | 0.3267 | 0.0492 | 0.0016 | 1.000 | 0.025 |
| Exp5 B4 security-only | 1.0000 | 0.4410 | 0.0000 | **0.0000** | ∞ | **0.00** |
| Exp6 Proposed $\alpha{=}0.8$ | 1.0000 | 0.2869 | 0.0197 | **0.0000** | 1.000 | 0.025 |
| **Exp7 Proposed $\alpha{=}0.5$ (headline)** | **0.0000** | 0.1033 | 0.1358 | **0.0016** | 1.000 | **1.00** |
| Exp8 Proposed $\alpha{=}0.2$ | **0.0000** | **0.0000** | 0.2875 | 0.7414 | 1.000 | **1.00** |
| Exp2 B2 greedy $N_k{=}10$ | 1.0000 | 0.0590 | 0.2311 | 0.4671 | ∞ | **0.00** |
| Exp3 B2 greedy $N_k{=}15$ | 1.0000 | 0.0933 | 0.2062 | 0.4068 | ∞ | **0.00** |

(M2 and the M1 "high-criticality" gate now read the IEC-weighted $S_\text{deny}$, not the equal-weight DC —
hence B2's M2 = 0.059 here vs 0.088 in the pre-Phase-1b table. All numbers are read from `results/Exp*.csv`.)

### 2a. What the numbers mean (one physical sentence per experiment)

- **Proposed $\alpha{=}0.5$ (the headline)** — `M4 = 0.0016`, `M7obs = 1.00`, `M1 = 0`: the balanced config
  puts latched-compromised nodes in a **write-stripped but fully-observable** action (`restricted` at the
  default trust floor 0.35; `read_only` at lower floors) rather than denying them, so it strips the FDI write
  path on almost every infected node (collapsing $pa$ to ~0) **while keeping every measurement row reported**
  — the operator stays fully sighted. **This is the only policy in the table that achieves both.**
- **Proposed $\alpha{=}0.8$ (security extreme)** — `M4 = 0.0000`, `M7obs ≈ 0.03`: once the trust floor exposes
  the latched nodes, the security-dominant weighting **denies** them, which (like B2/B4) drops their rows from
  $H_\text{obs}$ and blinds the EMS. Maximum security, minimal visibility.
- **Proposed $\alpha{=}0.2$ (safety extreme)** — `M4 = 0.7414`, `M2 = 0.0000`: the safety cost dominates, so
  the method keeps nodes `full`; $pa$ sits at the undefended ceiling but the denial cost is zero and
  observability is perfect. The "do no harm to operations" extreme.
- **B1 / B3 (trust-threshold baselines)** — `M4 ≈ 0.0016`, `M7obs ≈ 0.03`: with the trust floor, latched nodes
  fall below their thresholds and get denied en masse → they cut $pa$ but blind the EMS (M7obs≈0), and they
  do it indiscriminately (no criticality awareness), so their denial cost M2 is the highest in the table.

> **Why B1, B3, and Proposed $\alpha{=}0.5$ all report the *identical* `M4 = 0.0015525`** (E3 analysis —
> `results/injectable_overlap.csv`). It is **not** because the three deny/gate the same nodes across the
> saturated horizon — their action-gated injectable sets are identical at only **8 of 40 steps** and diverge
> permanently after step ~13. The equality is carried by a **single step**: $pa(t)$ is zero at all 40 steps
> *except step 5*, where the three policies' injectable sets happen to coincide (9 nodes), so the
> deterministic `compute_pa` returns the same $pa = 0.06210$ → $M4 = 0.06210/40 = 0.0015525$ for all three.
> The shared value is mechanistic (one coincident high-water step over a deterministic engine), not a
> coincidence of "same denial behavior" and not a hardcode.
- **B4 (security-only, $\alpha{=}1$)** — `M4 = 0.0000`, `M7obs = 0.00`: total denial → no bypass, total
  blindness. The over-defense the safety-aware objective exists to avoid.
- **B2 (FENG greedy, $N_k{=}10/15$)** — `M4 = 0.467 / 0.407`, `M7obs = 0.00`: hardening the sensor nodes that
  gate FDI cuts $pa$, but those denied sensor nodes drop their rows from $H_\text{obs}$ → the EMS is blind at
  every step. B2 buys security with the operator's eyes.

> The single takeaway: **every policy that meaningfully cuts $pa$ — B1, B3, B4, B2, and Proposed
> $\alpha{=}0.8$ — destroys observability (M7obs ≈ 0). Proposed $\alpha{=}0.5$ is the lone exception**: it
> collapses $pa$ to ~0 *and* holds M7obs = 1.0, because it **restricts** instead of **denies**. That is the
> safety-aware contribution made concrete by the Phase 1b runtime awareness.

---

## 3. The figures

![Phase 1 trade-off bars](figures/phase1_tradeoff_bars.png)

*Grouped bars of M1, M2, M4, and M7's observable fraction (green) across the eight experiments. Almost every
policy that drives M4 (blue) toward zero also drives the green bar toward zero — security bought with
blindness. **Proposed $\alpha{=}0.5$ is the exception: low blue (M4≈0) with full green (M7obs=1.0).** B4, B2,
B1, B3, and $\alpha{=}0.8$ all leave the green bar at/near zero.*

![pa(t) by policy](figures/phase1_pa_vs_step_by_policy.png)

*$pa(t)$ over the 40-step horizon for B2 ($N_k{=}10$), the headline Proposed $\alpha{=}0.5$, and the soft
$\alpha{=}0.2$. B2 (red) is suppressed early but rises in steps as the worm spreads beyond its 10 hardened
nodes. Proposed $\alpha{=}0.5$ (blue) drives $pa$ to ~0 as the trust floor exposes latched nodes and the
method restricts them — and unlike B2 it does so without blinding the EMS (M7obs=1.0). The soft $\alpha{=}0.2$
(grey) stays near the undefended ceiling.*

![M5 action distribution](figures/phase1_m5_action_dist.png)

*M5: per-device-class action distribution for the three proposed configs. At $\alpha{=}0.8$ (security-leaning)
latched nodes are pushed to `deny`; at $\alpha{=}0.5$ (balanced) they go instead to a write-stripped but
fully-observable action (`restricted` at the default floor 0.35, `read_only` at lower floors) — which is why
$\alpha{=}0.5$ preserves observability; at $\alpha{=}0.2$ (safety-leaning) most stay `full`. The
write-stripped-but-observable band at $\alpha{=}0.5$ ($\gamma<0.6$, $O_a=1.0$) is the visual signature of the
headline result: stripping the FDI write path without dropping measurement rows.*

---

## 4. The four ablations (Phase 1b run)

| Ablation | What it perturbs | Result |
|---|---|---|
| **ABL-1** | $S_\text{deny}$ IEC weights ±50% per weight | **robust**: worst-case M1–M4 move < 10% (max 9.7% on M3); validates the proposal's robustness claim |
| **ABL-2** | **runtime process-state P** swept {0.2, 0.6, 1.0}, design-time attrs fixed | **P changes the decision**: $\alpha{=}0.5$ `read_only`→`deny`, $\alpha{=}0.2$ `full`→`restricted` (the runtime-awareness demo) |
| **ABL-3** | $\gamma/\delta$ ±20% | action ranking preserved (objective terms monotone in these) |
| **ABL-4** | toggle ~5% of $B$'s edges | proposed M4 **0.0016 → 0.0016** (Δ = 0.00 pp; within the ±5 pp target) |

> **ABL-1** is now the quantitative weight-sensitivity sweep enabled by Task 5's $S_\text{deny}$: each of the
> five IEC weights is scaled ±50% (renormalized) and the balanced config re-run; the largest relative metric
> move is reported. **ABL-2** is the Phase 1b "process-state contribution" demonstration — it is the direct
> evidence that the safety score is *runtime-aware* (changing only P flips the chosen action).
>
> **ABL-4 caveat (Assumption A2).** $R_d$ is **synthetic** under the round-robin `A` (see
> [09 §A.3](09_decision_model.md) and [12](12_phase1_divergences.md)): the redundancy sensitivity is
> *structural*, not validated against a real node→bus map. A genuine Fig. 5 `A` would change $R_d$.

---

## 5. The Milestone 2 acceptance gate

**Gate (spec §8):** for at least one $(\alpha,\beta)$ config,

$$ \mathrm{M1}_\text{proposed} < \mathrm{M1}_{B2} \ \wedge\ \mathrm{M2}_\text{proposed} < \mathrm{M2}_{B2}
   \ \wedge\ \big| \mathrm{M4}_\text{proposed} - \mathrm{M4}_{B2}\big| / \mathrm{M4}_{B2} \le 0.10. $$

Reference: B2 $N_k{=}10$ — M1 = 1.0000, M2 = 0.0590, M4 = 0.4671 (Phase 1b run).

| Config | M1 < 1.0000? | M2 < 0.0590? | M4 within ±10%? | Gate |
|---|---|---|---|---|
| Proposed $\alpha{=}0.8$ | No (1.0000) | No (0.2869) | No — M4 = 0.0000 (far below B2: better security, outside band) | no |
| **Proposed $\alpha{=}0.5$** | **Yes (0.0000)** | No (0.1033) | No — M4 = 0.0016 (far below B2) | no |
| Proposed $\alpha{=}0.2$ | Yes (0.0000) | Yes (0.0000) | No — M4 = 0.7414 (+58.7%) | no |

**Verdict: the strict gate is still not met by any single config** — for an instructive reason, not a bug
(full analysis in [12 Divergence 4](12_phase1_divergences.md)):

- $\alpha{=}0.5$ now beats B2 decisively on M1 (0 vs 1.0) and crushes $pa$ (0.0016 vs 0.467), but its
  aggregate denial cost M2 (0.1033) exceeds B2's (0.0590). B2 denies *few* nodes (low M2) but blinds the EMS;
  $\alpha{=}0.5$ restricts *many* nodes (higher M2) but keeps the EMS sighted. The gate's M2 condition rewards
  B2's narrow-but-blinding strategy.
- The ±10% M4 band still doesn't fit: the proposed configs are *far* below B2 on $pa$ (better) or at the
  ceiling — never within ±10% of B2's 0.467. The gate presumes a config security-*comparable* to B2; the
  Phase 1b method instead either crushes $pa$ or stays soft.

**The robust contribution the gate does not capture:** **Proposed $\alpha{=}0.5$ is the only policy in the
entire table that drives $pa$ to ~0 while keeping `M7obs = 1.0`.** Every other low-$pa$ policy (B1, B3, B4,
B2, $\alpha{=}0.8$) collapses observability to ~0. The safety-aware method's value is precisely this
preservation of grid-state visibility — the independent M7 axis the security-driven baselines all sacrifice.
The correct framing is a **trade-off** (balance preserves visibility while collapsing $pa$), *not* "beats
Feng & Hu on security."

---

## 6. Unit tests (58 total)

Each new module is covered; the suite is the Phase 1/1b regression harness alongside Phase 0's 17.

| Module | Tests | Key invariants guarded |
|---|---|---|
| `test_topology.py` (+5) | 10 | `assign_classes` labels all 55 nodes, all five classes present, deterministic, respects sensor/non-sensor role; $\delta_a$ table = {0, .25, .5, .9, 1} |
| `test_node_profiles.py` | 16 | 55 profiles; all unit fields ∈ [0,1]; `R_d_synthetic`; role-based $R_d$; derived ASC/DC; **Phase 1b**: latched **trust floor**, `compute_P` three levels, `S_deny` bounds/weights/rises-with-P |
| `test_decision.py` | 15 | the three `select_action` cases; `apply_actions` hardens **only** deny nodes; security channel never raises $pa$; **Phase 1b**: $R_\text{saf}$ P-relief monotone, **runtime-sensitivity** (P alone flips the action), **restricted strips the write path** |
| `test_metrics.py` | 5 | **M7 reuses Phase 0 build_H/build_R** ($H_\text{obs}{=}H$ ⇒ inflation 1.0); **channel fidelity** (all-`full` ⇒ M4 = Gate A to $10^{-12}$); metric bounds; M5 fractions sum to 1 |

(Phase 0's `test_power_system.py` (6) and `test_attack.py` (6) are unchanged.) Run:
`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest zt_cps_phase0/tests -p no:cacheprovider -q` → **58 passed**.
Phase 0 gates: `python run_phase0.py` → all six PASS. The channel-fidelity test still pins all-`full` M4 to
Gate A's 0.7408 within $10^{-12}$ — Phase 1b's P/trust-floor/S_deny changes cannot perturb it because
all-`full` never denies.

---

## 7. Reproducing this chapter

```bash
cd /home/poky/Workspace/Amr/CPS_Safety_Aware
source .venv/bin/activate

python -m zt_cps_phase0.src.run_experiment --full   # 8 experiments + ablations + Milestone-2 report
                                                     # writes results/Exp*.csv (~25-45 min incl. B2 greedy)
python docs/make_phase1_figures.py                   # the three figures above (~30 s, no greedy needed)
```

The fast experiments (B1/B3/B4/Proposed) and the figures take seconds; only B2's greedy search is slow.
Numbers are deterministic (all RNG via `config.SEED`). See [12 — divergences](12_phase1_divergences.md) for
the honest modeling choices behind these results.
