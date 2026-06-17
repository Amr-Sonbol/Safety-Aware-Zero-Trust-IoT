# Phase B — Validation Evidence (fresh reproduction)

**Date of reproduction:** 2026-06-16
**Validated commit (the paper cites this):** `baa64a7f1bb48512bcc5dd8223af4794be1d845b`
**Branch:** `phaseB-validate-and-fix`
**Environment:** project root `/home/poky/Workspace/Amr/CPS_Safety_Aware`, `.venv` active,
pandapower 3.4.0, `SEED=0` (all results deterministic).

This document is a recorded, dated reproduction of every headline number, run from a clean
checkout of the validated commit **before** any documentation/comment fixes. It exists because
`results/*.csv` and `docs/figures/*.png` are gitignored and therefore cannot themselves be
version-pinned; the outputs are transcribed here verbatim.

---

## 1. Phase 0 six gates — `python run_phase0.py`

All six PASS. No FAIL lines.

```
[PASS] Total load ≈ 283.4 MW — got 283.4 MW
[PASS] Slack vm_pu = 1.06 — got 1.0600 p.u.
[PASS] H shape (41, 29) with M=41, N=29 — shape = (41, 29)
[PASS] H is full column rank (29) — rank = 29
[PASS] H entries are reactance-weighted (not ±1 incidence) — max |H| = 42.373
[PASS] Clean residual ‖z_clean − H K z_clean‖ < 1e-6 — residual = 7.89e-12
[PASS] Gate A avg pa ∈ [0.70, 0.80]  (target 0.7474) — achieved 0.7408
[PASS] Gate B Nk=10 avg pa ∈ [0.50, 0.58] — achieved 0.5606
[PASS] Gate B Nk=15 avg pa ∈ [0.49, 0.57] — achieved 0.5483
[PASS] Gate B monotone: pa(Nk=15) ≤ pa(Nk=10) — 0.5483 ≤ 0.5606
ALL CHECKS PASSED — Phase 0 baseline validated.
```

| Quantity | Achieved | Band / threshold |
|---|---|---|
| Clean residual | 7.89e-12 | < 1e-6 |
| Gate A avg pa | 0.7408 | [0.70, 0.80], target 0.7474 |
| Gate B pa @ Nk=10 | 0.5606 | [0.50, 0.58] |
| Gate B pa @ Nk=15 | 0.5483 | [0.49, 0.57] |
| Monotonicity | 0.5483 ≤ 0.5606 | required |

---

## 2. Unit tests

```
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest zt_cps_phase0/tests -p no:cacheprovider -q
```

Result: **58 passed**, 0 failed (12 pandapower DeprecationWarnings, unrelated to project code).

---

## 3. Full experiment suite — `python -m zt_cps_phase0.src.run_experiment --full`

Trade-off table (read from the freshly written `results/Exp*.csv`):

| Experiment | M1 | M2 | M3 | M4 | M7 infl | M7 obs |
|---|---|---|---|---|---|---|
| Exp1 B1 | 1.0000 | 0.2926 | 0.0207 | 0.0016 | 1.000 | 0.03 |
| Exp4 B3 | 0.0000 | 0.3267 | 0.0492 | 0.0016 | 1.000 | 0.03 |
| Exp5 B4 (α=1) | 1.0000 | 0.4410 | 0.0000 | 0.0000 | inf | 0.00 |
| Exp6 Proposed α=0.8 | 1.0000 | 0.2869 | 0.0197 | 0.0000 | 1.000 | 0.03 |
| **Exp7 Proposed α=0.5 (headline)** | **0.0000** | **0.1033** | **0.1358** | **0.0016** | **1.000** | **1.00** |
| Exp8 Proposed α=0.2 | 0.0000 | 0.0000 | 0.2875 | 0.7414 | 1.000 | 1.00 |
| Exp2 B2 greedy Nk=10 | 1.0000 | 0.0590 | 0.2311 | 0.4671 | inf | 0.00 |
| Exp3 B2 greedy Nk=15 | 1.0000 | 0.0933 | 0.2062 | 0.4068 | inf | 0.00 |

### Headline (Exp7, α=0.5) — exact values from `results/Exp7_Proposed_a0.5_b0.5.csv`

```
M1,0.0
M2,0.10327261363636364
M3,0.13575787383839505
M4,0.0015525
M6,0.0
M7_mean_inflation,1.0
M7_frac_observable,1.0
```

These are **byte-for-byte identical** to the CSV that predated this run (delta = 0 on every field):
the result is deterministic and reproduces exactly.

### Key baselines

- **Exp5 B4:** M4 = 0.0, M7_frac_observable = 0.0 (security bought with total blindness).
- **Exp2 B2 Nk=10:** M4 = 0.4670775, M7_frac_observable = 0.0 (greedy hardening blinds the EMS).

### Milestone-2 verdict (verbatim)

```
[Milestone 2] Strict gate not met (no config satisfies all three conditions).
```

Reported as a trade-off, not a failure: Exp7 (α=0.5) is the only policy that drives pa to ~0
(M4 = 0.0016) **while** preserving full observability (M7obs = 1.00); every other low-pa policy
(B1, B3, B4, B2, α=0.8) collapses observability to ~0.

### Ablations (from the same run)

```
ABL-4 (B 5% edge toggle): proposed M4 0.0016 -> 0.0016 (Δ=0.00 pp; within ±5pp target)
ABL-2 (process-state P): α=0.5 Normal=read_only Degraded=read_only Emergency=deny (P changes the decision)
ABL-1 (S_deny weight ±50%): max relative move M1=0.0% M2=8.9% M3=9.7% M4=0.0% => robust (<10%)
ABL-3 (γ/δ ±20%): action ranking preserved by construction.
```

---

## 4. Figures — `python docs/make_figures.py` and `python docs/make_phase1_figures.py`

Both scripts completed with exit code 0; all six PNGs written to `docs/figures/`.

- **pa_vs_step average = 0.7408** — equals the Gate A value (the script replays the undefended
  Gate A / all-`full` loop, not the B1 *policy*; B1's experiment M4 is 0.0015525, a different
  number, because B1 denies latched nodes).
- **rho_bar plateau (saturation) = 0.3175** (≈ 0.318, below 0.5 — endemic SIS equilibrium).
- **Greedy node-selection order:**
  - Nk=10: `[13, 23, 7, 15, 12, 8, 3, 6, 4, 10]`
  - Nk=15: `[13, 23, 7, 15, 12, 8, 3, 6, 4, 10, 18, 14, 16, 51, 26]`
  - Matches the documented reference order exactly.

---

## 5. Summary

Every documented gate, test count, headline metric, figure series, and the Milestone-2 verdict
reproduced exactly from commit `baa64a7`. This is the validated state the paper cites. No source,
config, test, or logic was modified to produce this evidence; only the documented run commands were
executed and their outputs transcribed.
