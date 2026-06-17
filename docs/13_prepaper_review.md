# 13 — Pre-Paper Review & Integrity Checklist (LIVING DOCUMENT)

**Purpose.** A conservative review of the Safety-Aware-CPS-Zero-Trust system *as documented*, written
before the literature/research paper is drafted. It records what can be claimed safely, what must be
verified first, and where an examiner is most likely to probe. **This document is meant to be updated:**
fill in the verification results (§2), revise framing decisions (§5) as they're settled, and append notes as
the paper takes shape.

> **Scope of this review.** It is based on the project **documentation** (docs 00–12 + the three figures),
> *not* on a read of the source code or a fresh run. It therefore checks internal consistency, logical
> soundness, and scientific integrity of the *claims*. It does **not** certify that the code produces the
> reported numbers — that requires the clean re-run in §2.

---

## 1. Overall judgment

The work is in good shape and is unusually honest with itself. The physical layer is rigorous; the
divergence documentation (docs 05, 12) is candid; the test/figure scaffolding is real. It is **not** a clean
"we reproduced Feng & Hu" result and must not be written as one. The defensible framing is:

> *We built a cyber-physical attack/defense model that reproduces the paper's reported bypass numbers under
> documented, calibrated assumptions, then extended it with a safety-aware decision layer whose central
> result is a security/observability **trade-off** (metric M7) — not a security win over the paper.*

Written that way, it is a respectable master's contribution. Written as a faithful reproduction plus a win,
it is exposed. The risk is entirely in over-claiming, not in the work itself.

---

## 2. MUST-DO verifications before drafting (fill these in)

These gate the paper. Do not write claims that depend on them until each is confirmed.

| # | Verification | How | Status | Result / notes |
|---|---|---|---|---|
| V1 | Clean re-run reproduces Phase 0 gates | `python run_phase0.py` from clean checkout | ☐ | _expected: all 6 PASS, Gate A 0.7408_ |
| V2 | Test suite passes | pytest (58 tests: 17 P0 + 41 P1/1b) | ☐ | _expected: 58 passed_ |
| V3 | Phase 1 experiment sweep reproduces the trade-off table | `run_experiment --full` | ☐ | _expected: Exp1–8 match doc 11 §2_ |
| V4 | Figures regenerate and match printed series | `make_figures.py`, `make_phase1_figures.py` | ☐ | _pa_vs_step avg must equal Gate A_ |
| **V5** | **Paper target numbers actually appear in Feng & Hu (2023)** | open the PDF | ☐ | **see §3 — highest priority** |
| V6 | Paper's defense really is deep Q-learning | PDF, methods section | ☐ | _project assumes DQL; abstract says "data-driven + model-based optimizer"_ |
| V7 | Repo is under version control with a tagged baseline | `git init`, tag validated commit | ☐ | _docs note it is NOT a git repo — reproducibility liability_ |
| V8 | Doc bug fixed: `restricted` γ value | reconcile doc 09 table vs code | ☐ | _table says 0.60, prose/doc12 say 0.50 — see §4.7_ |

---

## 3. Highest-priority risk: are the "paper target" numbers real and correctly matched?

The entire Phase 0 validation is anchored to three numbers attributed to the paper:
**pa = 74.74% (undefended), 52.91% (N_k=10), 50.94% (N_k=15)**.

**Why this needs checking.** The paper's publicly visible abstract describes its result as increasing the
**detection probability** against FDI attacks by "more than 31%," via a multi-layer access-control engine and
an integrated model-based + data-driven policy optimizer. That is not transparently the same quantity as a
**bypass probability** pa, and the arithmetic does not cleanly reconcile (the undefended→defended detection
gain implied by the project's numbers is ~22–24 points, not 31%). The numbers may well be in the paper — but
they cannot be confirmed from public sources, and the supervisor very likely has the PDF.

**Action (V5/V6).** From the actual PDF, confirm and record here, with page/figure/table references:

- [ ] 0.7474 appears, and is an attack-success / bypass probability (not detection, not something else):
      _______________________
- [ ] 0.5291 (N_k=10) and 0.5094 (N_k=15) appear and are the same quantity: _______________________
- [ ] The metric correspondence "paper's X = our pa" is exact, or else documented as a mapping: ____________
- [ ] The defense optimizer is deep Q-learning (the project's stated assumption): _______________________

If any of these do not hold, the "faithful reproduction" framing must change before submission, not after.

---

## 4. Concerns ranked by how much they can hurt (examiner's likely probes)

### 4.1 Calibration circularity (most fragile point)
Three knobs were tuned to produce the very numbers used to "validate":
- `STRENGTH_THR = 0.30` set so Gate A averages 0.7408 (≈ paper 0.7474).
- `HARDENING_DELTA = 0.40` set so Gate B lands in band.
- `T_LATCH_FLOOR = 0.35` (Phase 1b) — by the docs' own words "calibrated for exactly this," so that α=0.5
  chooses `read_only` not `deny`; "a deeper floor… erases the trade-off."

So the **headline contribution result exists because a threshold was hand-set to produce it.** This is
documented (not hidden), but it is circular if presented as *validation* or *robustness*.
- **Safe framing:** an *existence demonstration* — "there exists a balanced parameterization under which
  restriction preserves observability while collapsing pa."
- **Mitigation (recommended):** add a sensitivity sweep showing the *qualitative* outcome
  (read_only-not-deny; M7obs stays high) survives over a **range** of `T_LATCH_FLOOR` values. This converts
  the weakest point into a defensible one. → see §6 open items.

### 4.2 Accept "bands" may enclose the answer
Gate B band [0.50, 0.58] contains both the achieved 0.5606 and the paper's 0.5291. If bands were drawn after
seeing results, "passing" them is not independent validation.
- **Safe framing:** drop PASS/FAIL "gate" language in the paper; report "achieved X vs paper Y (Z% relative
  difference), the gap attributable to greedy-heuristic vs DQL." Or define bands by an a-priori tolerance
  rule stated *before* results.

### 4.3 Milestone-2 goal not met → contribution re-centered
Honestly handled in doc 12, but **sequencing in the writeup matters**. Present M7 (the security/observability
trade-off) as the thesis from the first sentence. Do **not** narrate "we set criterion X, failed it, then
decided M7 was the point" — that reads as moving goalposts. Same facts, opposite reception.

### 4.4 Named deliverables (DQL, physical safety cost S_c) are not built
Project is "Safety-Aware"; the Phase 0 roadmap promised `J = pa + λ·S_c` with a learned DQL policy. Neither
shipped: the defense is a deterministic argmin; the safety axis is **M7 (observability)**, not a line-flow /
voltage S_c. `config.LAMBDA` exists but is unused.
- **Safe framing:** scope sentence claims only what is built. The title/intro must not promise a safety
  *cost* model the body lacks. DQL and S_c are explicitly "Phase 2 / future work."

### 4.5 Profile layer rests on synthetic / placeholder inputs
- `R_d` is synthetic (flagged `R_d_synthetic=True`).
- Device classes assigned by a degree heuristic (no published per-node labels in Fig. 5).
- Sensor map `A` is round-robin, **not** a real branch→sensor incidence.
- `S_deny`'s availability (A) and operational-impact (O) terms are static per-class proxies, not live models.

Each is flagged, but cumulatively the profile-derived metrics (DC, ASC, M2, M5) are **illustrations of a
method on placeholder data**, not results validated on the IEEE 30-bus benchmark.
- **Safe framing:** "illustrative profile layer." Do not imply these inputs are grounded in the benchmark.

### 4.6 Identical M4 across three policies (minor — have the explanation ready)
B1, B3, and Proposed α=0.5 all report **M4 = 0.0016** to four decimals. Explicable (once the *injectable* set
coincides at the same steps, pa(t) coincides), but three different policies giving a byte-identical security
number invites "is this hardcoded / a bug?" Prepare the one-sentence answer.

### 4.7 Documentation bug to fix now (V8)
Doc 09 §B.1 action table lists `restricted` γ = **0.60**, but the Phase 1b note atop doc 09 *and* Divergence 7
in doc 12 say it was lowered to **0.50** (the whole point: 0.60 sat exactly on the ≥0.6 injection cutoff and
did nothing). Table contradicts prose. **Reconcile against the live code value**, since M3 and the headline
pa both depend on it.

---

## 5. What is solid (claim these confidently)

- **Physical layer.** DC power flow, H with reactance weights 1/(xτ) (not ±1 incidence), WLS estimator with
  KH=I, and the **7.89×10⁻¹² clean-residual certificate** that H/K/units/branch-ordering all agree. Sound and
  well-tested. This is the foundation.
- **Honesty layer (docs 05, 12).** Each divergence states the paper's recipe, why it fails verbatim, the
  fix, and the evidence. Exactly the right posture for a reproduction; lead with it, don't bury it.
- **Gate A.** 0.7408 vs paper 0.7474 — a faithful, in-band match.
- **Channel-fidelity guarantee.** The all-`full` Phase 1 pipeline is numerically *identical* (to 10⁻¹²) to a
  direct `update_worm → sample_compromise → compute_pa` loop recomputed inside the test on the same seed — i.e.
  the Phase 1 layer adds **no drift** to the validated engine rather than re-deriving the physics. (The test
  checks "no drift" plus Gate A band membership; it does not pin M4 to the runner's stored 0.7408.)
- **Figures.** All three (pa_vs_step S-curve, ρ̄ saturating ≈0.318 below 0.5, Gate B sweep) are consistent
  with the documented numbers.

---

## 6. Open items / decisions to settle before drafting

- [ ] **Paper type.** Is the deliverable a *literature-review* paper or the paper presenting *this* work?
      This changes which findings above are central. (Asked; pending.)
- [ ] **Sensitivity sweep on `T_LATCH_FLOOR`** (and ideally `STRENGTH_THR`, `HARDENING_DELTA`) to de-risk §4.1.
- [ ] **Decide on gate language** (§4.2): keep with a-priori justification, or replace with honest
      comparison.
- [ ] **Scope sentence** drafted so it claims only built deliverables (§4.4).
- [ ] **Metric-correspondence statement** (paper's quantity ↔ our pa) once §3 is verified.
- [ ] Confirm whether the IEC-61508 H_s mapping and the SIL→class assignment are presented as *assumptions*
      or as grounded values (they are assumptions).

---

## 7. Provenance & limitations of this review

- Reviewed: docs `00`–`12` (Phase 0 `_system` set + Phase 1 set) and figures `pa_vs_step.png`,
  `rho_bar_vs_step.png`, `gateB_nk_sweep.png`.
- Confirmed: the `_system` docs (00–05, 07) are byte-identical to their non-suffixed development copies;
  Phase 1 docs (08–12) and 06 have no separate development/system split.
- Confirmed: Feng & Hu (2023) exists and is correctly cited — *IEEE Transactions on Industrial
  Cyber-Physical Systems*, vol. 1, pp. 394–405.
- **Not done here:** code read, fresh execution, and verification of the paper's internal numbers (the §2/§3
  actions). Treat §5 "solid" items as *consistent-as-documented*, pending the clean re-run.

---

*Last updated: initial draft (pre-run). Append verification results to §2/§3 and revise §5/§6 as decisions
are settled.*
