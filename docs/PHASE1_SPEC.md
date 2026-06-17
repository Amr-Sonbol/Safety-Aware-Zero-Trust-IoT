# Phase 1 — Safety-Aware Decision Function: Implementation Spec (Reconciled)

**Project:** Safety-Aware-CPS-Zero-Trust (extends Feng & Hu 2023).
**Status:** This document is the single source of truth for Phase 1. It supersedes the *foundation chapters*
of the friend's "Final Technical Specification v4" and "Python Implementation Plan" (their `power_system.py`,
`attack_engine.py`, `topology.py`, H matrix, FDI/pa, worm, and tau-calibration content). It keeps the v4
*contribution layer* (the decision model, baselines, metrics, experiments, ablations) and folds in three
resolved design decisions. Where this document and v4 disagree, **this document wins.**

---

## 0. Integration rules (READ FIRST — these prevent conflicts)

Phase 0 is a **validated, frozen baseline**. Do not modify, re-derive, or re-implement it. Concretely:

- **Keep `power_system.py`, `attack_engine.py`, `topology.py`, `policy_engine.py` exactly as they are.**
  They already pass all six gates and 17 tests. The new code (`node_profiles.py`, `decision.py`,
  `metrics.py`, `run_experiment.py`) sits *on top* of them.
  > *Note (post-implementation): the "17 tests" throughout this spec is the Phase 0 regression set this spec
  > was written against. The shipped Phase 1/1b code added tests; the full current suite is **58 tests**. The
  > 17-test references below are preserved as the original contract.*
- **The Phase 0 six-gate runner and the 17 unit tests must stay green after every Phase 1 change.** Treat
  them as a regression harness. If any Phase 0 gate or test breaks, the change is wrong — revert it.
- **Ignore these v4 items — Phase 0 already supersedes them (do NOT follow the v4 versions):**

  | v4 / impl-plan says | Use instead (Phase 0, validated) |
  |---|---|
  | `pn.case30()` | `case_ieee30()` (Phase 0 `load_network`) |
  | H shape (41, 30), `net.line` only | H shape (41, **29**), reactance-weighted, transformers included, slack removed (Phase 0 `build_H`) |
  | `compute_pa` with `r=a−HKa`, `norm×(1−ρ̄)` vs tau | Phase 0 `compute_pa` (subspace-feasible projector + `STRENGTH_THR=0.30`) |
  | `update_worm` without recovery term | Phase 0 `update_worm` (mean-field SIS with `−ρ·γ`) |
  | "calibrate tau by binary search to 74.74%" | Already done via `STRENGTH_THR=0.30`; Gate A = 0.7408. **No tau.** |
  | `B.sum()==2·82` (82 edges) | 83 edges (verified). Phase 0 test `==2·83` is correct. |
  | Milestone 0 / Milestone 1 procedures | Already passed by Phase 0 (Gate A, Gate B). Do not re-run them as new work. |

- **Reuse, don't duplicate:** import `build_H`, `build_R`, `build_estimator`, `generate_z`,
  `clean_residual_norm` from `power_system`; `build_B`, `build_A`, `sensor_nodes` from `topology`;
  `update_worm`, `sample_compromise`, `measurement_mask`, `_feasible_projector`, `compute_pa`,
  `generate_fdi_targets` from `attack_engine`; `apply_policy`, `evaluate_policy`, `greedy_search` from
  `policy_engine`.

---

## 1. The three resolved design decisions (baked in)

**D1 — Soft actions get physical teeth via two channels (keeps "only Deny changes B′" true).**
Each action carries the v4 coefficients γ_a (command/attack capability retained) and the pair (O_a, C_a)
that yields δ_a. They now drive the simulation through two *separate* channels:
- **Security channel (γ_a → FDI injection mask, affects pa / M4).** A measurement is attacker-injectable
  only if its collecting node is infected/latched **AND** the node's action retains control authority —
  defined as the action keeping the C3 control-command channel, i.e. **Full or Restricted** (γ_a ≥ 0.6).
  Read-Only, Safe-Mode, Deny strip C3 → that node's measurements are removed from the compromised set used
  by `_feasible_projector`. This makes Read-Only/Safe-Mode lower pa (physically: FDI needs a write path).
- **Safety channel (O_a → observability set, affects M7).** The fraction O_a of a node's measurements still
  reported to the EMS defines what the state estimator can still see. Denying/safe-moding sensors removes
  their rows from the observed H → degraded estimation (this is the physical cost of denial).

**D2 — Keep static DC (M1–M6 verbatim from v4) and ADD a physical metric M7.**
M7 = physical observability cost under a policy's action set: (a) is the still-reported H full column rank
(observable)? and (b) estimation-error inflation = `trace((H_obsᵀ W H_obs)⁻¹)` relative to the clean
(all-observed) baseline. Reuses Phase 0 `build_H`/`build_R`. M7 is the non-circular safety axis (M2/M3 are
the optimizer's own objective terms; M1, M5, M7 are the independent ones).

**D3 — One denial mechanism everywhere: partial hardening δ = 0.40.**
Both B2's greedy hardening and the proposed method's `deny` apply the same `(1−δ)` row/column multiplier to
B′ (Phase 0 `apply_policy`), δ = `HARDENING_DELTA = 0.40`. **Do not** zero rows/columns (full isolation
overshoots — Phase 0 Divergence 3). Soft actions (Full/Restricted/Read-Only/Safe-Mode) leave B′ unchanged;
only `deny` hardens B′. The five-action security gradient lives in the γ-injection channel (D1), not in
differential B′ changes.

---

## 2. Node profile data (`node_profiles.py` + `topology.py` additions)

Each of the 55 nodes gets a fixed profile (computed once) plus a per-step `rho`.

- **Device class** (`assign_classes()` in `topology.py`): one of `C-PDP-critical`, `C-PDP-controller`,
  `T-PDP-relay`, `T-PDP-sensor`, `T-PDP-monitor`, read from FENG2023 Fig. 5 (Assumption A1/A5).
- **SIL → H_s** (IEC 61508 Table 2, log-PFD/4.00): none=0.00, SIL1=0.38, SIL2=0.63, SIL3=0.88.
  SIL-by-class mapping: C-PDP-critical→SIL3, C-PDP-controller→SIL2, T-PDP-relay→SIL1,
  T-PDP-sensor/monitor→none (Assumption A6 — document as general-practice, not HAZOP).
- **D_c** (FENG2023 I_sec): C-PDP-critical=0.90, C-PDP-controller=0.70, all T-PDP=0.30.
- **ASC_r** = `degree(node)/max_degree(B)` from the Phase 0 B (already 83 edges, 55 nodes).
- **R_d** = `1 − max_{j≠i} coverage(j→i)`, `coverage(j→i)=|buses(j)∩buses(i)|/|buses(i)|`, from A.

> **A-matrix integrity (Assumption A2 — important).** R_d is only meaningful if A is a real node→bus map.
> Phase 0's `build_A` is a synthetic round-robin placeholder. For Phase 1, either (a) reconstruct a real A
> from Fig. 5, or (b) if that reading is unavailable, keep the placeholder but **clearly label R_d as
> synthetic** in the profile and in the write-up, and lean on ABL-4 (B perturbation) + report R_d
> sensitivity. Do not silently treat a round-robin A as a real redundancy map.

Profile fields: `node_id, class, H_s, D_c, R_d, ASC_r, ASC=0.5*D_c+0.5*ASC_r, DC=(H_s+D_c+R_d)/3, rho`.
Assertions: all of H_s, D_c, R_d, ASC_r, ASC, DC ∈ [0,1]; 55 profiles.

---

## 3. The decision model (`decision.py`) — v4 math, verbatim

- Trust: `T = 1 − rho` (per node, per step; uses the latched/instantaneous rho consistently — see D1).
- `DC = (H_s + D_c + R_d)/3`, `ASC = (D_c + ASC_r)/2` (fixed per node).
- Action table `(γ_a, O_a, C_a)`: Full (1.00,1.0,1.0), Restricted (0.60,1.0,0.5), Read-Only (0.20,1.0,0.0),
  Safe-Mode (0.10,0.2,0.0), Deny (0.00,0.0,0.0). `δ_a = 1 − (O_a+C_a)/2` → {0.00,0.25,0.50,0.90,1.00}.
- `R_sec(a) = (1−T)·ASC·γ_a`, `R_saf(a) = DC·δ_a`.
- **Decision:** `A* = argmin_a [ α·R_sec(a) + β·R_saf(a) ]`, with (α,β) ∈ {(0.8,0.2),(0.5,0.5),(0.2,0.8)}.
- `select_action(profile, α, β) -> action_name`; `apply_actions(decisions, B) -> B'` applies D3 (only
  `deny` hardens B′ by δ=0.40 via Phase 0 `apply_policy`; soft actions leave B′ unchanged).

---

## 4. How an action set drives one simulation step

Given per-node actions for step k:
1. **B′ (worm):** harden (δ=0.40) the rows/cols of nodes whose action is `deny`; all else unchanged.
2. **Worm:** `rho = update_worm(rho, B')` (Phase 0); `compromised = sample_compromise(rho, compromised, rng)`
   (Phase 0 Bernoulli+latch).
3. **Injection mask (security, D1):** `injectable_node = compromised AND (action ∈ {full, restricted})`.
   Compromised measurement set `S = measurement_mask(A, injectable_node)`. `pa = compute_pa(C_targets, H, A,
   injectable_node, STRENGTH_THR)` — i.e. feed the *action-gated* injectable set, not raw `compromised`.
4. **Observability (safety, D1/D2):** observed-measurement set = rows whose collecting node has O_a>0 (Full/
   Restricted/Read-Only keep all rows; Safe-Mode keeps a 0.2 fraction; Deny keeps none). `H_obs` = those
   rows of H. M7 from `H_obs` (rank + covariance trace).
5. **Log** decisions, T, DC, ASC, γ, δ, R_sec, R_saf, pa, and the M7 inputs for this step.

---

## 5. Baselines (`policy_engine.py` / `run_experiment.py`)

- **B1 — Binary ZT:** per node, `deny if T<0.5 else full`. No DC, no soft actions.
- **B2 — FENG2023 greedy:** the **existing Phase 0 node-greedy** (`greedy_search`, partial hardening δ=0.40),
  minimizing pa, at Nk=10 and Nk=15. Read v4's "Nk links" as "Nk nodes" (per-node matches the per-node
  proposed method). Already validated: 0.5606 / 0.5483.
- **B3 — Naive multi-action:** five actions by fixed T thresholds, no DC: Full if T>0.7, Restricted if
  T>0.5, Read-Only if T>0.35, Safe-Mode if T>0.2, else Deny.
- **B4 — Security-only:** the proposed `select_action` with α=1.0, β=0.0 (DC ignored). Expected to collapse
  toward heavy denial.

All baselines and the proposed method use the **same** engine and the **same** two channels (D1) and the
**same** δ=0.40 (D3), so differences come only from how actions are chosen.

---

## 6. Metrics (`metrics.py`) — M1–M6 verbatim from v4, plus M7

- **M1** (high-safety denial rate): `count(deny ∧ DC>0.5 ∧ T>0.3) / count(deny ∧ DC>0.5)`. Lower is better.
- **M2** (aggregate DenialCost): mean over steps of `sum(DC·δ_a)/55`.
- **M3** (security risk exposure): mean over steps of `sum((1−T)·ASC·γ_a)/55`.
- **M4** (FDI bypass): mean pa over 40 steps.
- **M5** (action distribution): fraction of each action per device class per step.
- **M6** (mean T at deny): appendix sanity check.
- **M7** (physical observability cost — NEW, the independent safety axis): per step, from `H_obs`:
  `observable = (rank(H_obs)==29)`; `est_inflation = trace((H_obsᵀ W H_obs)⁻¹) / trace((Hᵀ W H)⁻¹)`
  (≥1; ∞/flagged if not observable). Report mean `est_inflation` and the fraction of steps observable.
  Lower M7 = the policy preserved physical visibility while defending.

---

## 7. Experiments & ablations (`run_experiment.py`)

**Eight experiments:** Exp1 B1; Exp2 B2 (Nk=10); Exp3 B2 (Nk=15); Exp4 B3; Exp5 B4 (α=1,β=0);
Exp6 Proposed (0.8/0.2); Exp7 Proposed (0.5/0.5); Exp8 Proposed (0.2/0.8). Export per-experiment CSV with
all of M1–M7.

**Four ablations:** ABL-1 DC weights ±50% from equal (M1/M2 ranking proposed>B2 should hold);
ABL-2 ASC weight split 0.4/0.6→0.8/0.2 (M3 trend); ABL-3 γ/δ ±20% (action ranking preserved);
ABL-4 B 5% edge toggle (Gate-A and proposed M4 within ±5pp; also report R_d sensitivity given A2).

---

## 8. Milestone 2 gate (Phase 1 acceptance)

For at least one (α,β) config: **M1(proposed) < M1(B2) AND M2(proposed) < M2(B2) AND M4(proposed) within
10% of M4(B2)**. Additionally report M7(proposed) vs M7(B2)/M7(B4) — the safety-aware claim is that the
proposed method preserves observability (lower or comparable M7) while keeping security (M4) within 10% of
the security-only baselines. The expected narrative is a *trade-off* (safety improved, security roughly
maintained), not "beats FENG on security." If the gate fails, debug `select_action`, the γ-injection
channel, and `apply_actions` — not the Phase 0 engine.

**Hard constraint:** after every Phase 1 change, Phase 0's six gates and 17 tests still pass.

---

## 9. New modules (only these are created)

```
src/
├── node_profiles.py   # build_node_profiles(B, A, classes), update_profiles(profiles, rho)
├── decision.py        # compute_DC, compute_ASC, select_action, apply_actions, run_step
├── metrics.py         # MetricsLogger + M1..M7 + export_csv
└── run_experiment.py  # Exp1..Exp8 + ABL1..ABL4; reuses runner's model build
topology.py            # ADD assign_classes(); (real build_A if reconstructable, else label R_d synthetic)
config.py              # ADD: ACTIONS table, CONFIGS (α/β), SIL_MAP, H_S, D_C, lambda (unused yet), M7 refs
```

Standards: type hints + NumPy docstrings; all constants in `config.py`; all RNG via `config.SEED`;
every new function gets a unit test; keep the `sys.path`/package layout Phase 0 uses (do not rename).

---

## 10. What NOT to do

- Do NOT re-implement or "fix" Phase 0's physics, worm, FDI, or topology from v4's foundation chapters.
- Do NOT introduce `case30`, an (41,30) H, a residual-tau, or a recovery-less worm.
- Do NOT use full node isolation for deny — use δ=0.40 (D3).
- Do NOT let any Phase 0 gate or test break. They are the contract.
- Do NOT renumber or alter M1–M6 (keep v4 intact); M7 is purely additive.
