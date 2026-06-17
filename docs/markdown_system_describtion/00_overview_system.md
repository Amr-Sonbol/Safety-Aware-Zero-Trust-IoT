# 00 — Phase 0 Overview

**Project:** Safety-Aware-CPS-Zero-Trust — a Master's-degree reproduction and extension of Feng & Hu (2023),
*"Cyber-Physical Zero Trust Architecture for Industrial Cyber-Physical Systems."*

**Phase 0** has a single job: **faithfully reproduce the paper's cyber-physical attack/defense model and
validate it against the paper's published numbers.** The deliverable is a *trusted baseline* — every later
phase (safety cost, deep Q-learning, the five-action decision function, metrics M1/M2/M3) is measured against
the numbers established here. This documentation set explains that baseline end-to-end: the model, the
results, the modeling judgments, the code, and where the next phases attach.

---

## Headline results

All produced by `python run_phase0.py` and reproduced independently by `python docs/make_figures.py`.

| Quantity | Achieved | Paper | Accept band | Status |
|---|---|---|---|---|
| Clean unobservability residual | $7.89\times10^{-12}$ | $\approx 0$ | $<10^{-6}$ | ✅ |
| **Gate A** — no-defense avg $pa$ (40 steps) | **0.7408** | 0.7474 | $[0.70, 0.80]$ | ✅ |
| **Gate B** — greedy $pa$, $N_k=10$ | **0.5606** | 0.5291 | $[0.50, 0.58]$ | ✅ |
| **Gate B** — greedy $pa$, $N_k=15$ | **0.5483** | 0.5094 | $[0.49, 0.57]$ | ✅ |
| Monotonicity $pa(15)\le pa(10)$ | ✓ | — | required | ✅ |
| Unit tests | **17 / 17 pass** | — | all pass | ✅ |

![Gate A: pa(t) over the 40-step horizon](figures/pa_vs_step.png)

*The attacker's bypass probability $pa(t)$: zero while the worm is still spreading, rising as
measurement-collecting sensor nodes are compromised, saturating at 1.0 once any FDI attack has a feasible
undetectable realization. The 40-step average (0.7408) is the Gate A figure of merit.*

---

## What this models, in one paragraph

A worm spreads over a 55-node cyber trust graph (epidemic SIS dynamics). As it reaches **sensor** nodes, the
attacker gains control of the physical **measurements** those sensors collect on an IEEE 30-bus power grid.
The attacker injects **false data** designed to corrupt the grid's estimated state while staying invisible to
the **bad-data detector** — a *false-data-injection* (FDI) attack. The **bypass probability $pa$** is the
fraction of such attacks that succeed. A **zero-trust defense** hardens nodes to slow the worm and push $pa$
down. Phase 0 reproduces the no-defense $pa$ and the defended $pa$ under a hardening budget. Full narrative:
[01_background_paper.md](01_background_paper.md); full mathematics: [02_cyber_physical_model.md](02_cyber_physical_model.md).

---

## Quickstart

```bash
cd /home/poky/Workspace/Amr/CPS_Safety_Aware
source .venv/bin/activate

python run_phase0.py                                          # the 6 validation gates (~10-25 min)
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest zt_cps_phase0/tests -p no:cacheprovider -q   # 17 tests
python docs/make_figures.py            # regenerate all 3 figures (slow: Gate B sweep)
python docs/make_figures.py --fast     # just the two Gate A figures (~10 s)
```

Full environment, pins, and reproducibility notes: [07_environment_repro.md](07_environment_repro.md).

---

## Document map

Read top-to-bottom as an essay, or jump to what you need:

| # | Document | What it gives you | For |
|---|---|---|---|
| 00 | **this file** | orientation, headline results, doc map | everyone |
| 01 | [Background & threat model](01_background_paper.md) | the paper's problem and terminology, in prose | reader new to Feng & Hu |
| 02 | [Cyber-physical model](02_cyber_physical_model.md) | the end-to-end mathematics, mapped to code | technical core |
| 03 | [Code architecture](03_code_architecture.md) | modules, API, call graph, knobs, runtime | developer |
| 04 | [Results & validation](04_results_and_validation.md) | the 6 gates, 17 tests, and 3 figures | examiner / results section |
| 05 | [Divergences from the paper](05_divergences.md) | the four documented modeling choices + why | integrity / defense |
| 06 | [Roadmap to Phase 1](06_roadmap_phase1.md) | where DQL / 5-action / safety cost attach | next phases |
| 07 | [Environment & reproducibility](07_environment_repro.md) | exact env, pins, commands, timings | re-running from scratch |

### Study aids — three questions, where each is answered

If you are building study materials from these docs, the three core questions map to specific places:

| Question | Where it is answered explicitly |
|---|---|
| **What each component does and *why* it exists** | [02](02_cyber_physical_model.md) — each component subsection (Parts A–C) opens with a *"Why it exists"* note; the cyber-physical **bridge** is framed at the top of Part B |
| **What the results mean numerically *and physically*** | [04 §1 table](04_results_and_validation.md) (numbers + bands + paper) and [04 §1a "What the numbers mean"](04_results_and_validation.md) (one plain physical sentence per result) |
| **How the components connect in the overall flow** | [02 §B.0](02_cyber_physical_model.md) — a single-step end-to-end **trace with array shapes** and the **two nested loops**; the top-of-02 diagram shows the `B→B′` defender feedback; [03 §2](03_code_architecture.md) gives the shape-annotated call graph |

---

## The three calibration knobs (frozen baseline)

| Knob | Value | Sets |
|---|---|---|
| `STRENGTH_THR` | 0.30 | Gate A bypass probability |
| `HARDENING_DELTA` | 0.40 | Gate B defense curve |
| `N_FDI_POLICY` | 2000 | greedy-search speed (Gate A uses the full 10 000) |

These three values, plus the worm rates ($\beta=0.1$, $\gamma=0.2$, $\rho_0=0.05$) and the seed (`SEED=0`),
fully determine every number in this documentation. Why each holds its value:
[04 §5](04_results_and_validation.md) and [05_divergences.md](05_divergences.md).

---

## Honesty note

Four mechanisms in this reproduction depart from the paper's *literal* recipe — because the literal recipe,
taken verbatim, cannot produce the paper's own reported results (a U-shaped $pa$ curve; a worm that never
crosses the compromise threshold; a defense that collapses $pa$ to zero). Each departure is the minimal change
that recovers the reported behaviour, and each is documented with its failure mode and its evidence in
[05_divergences.md](05_divergences.md). **The physics ($H$, $K$, DC power flow) is reproduced exactly** — the
$7.89\times10^{-12}$ unobservability residual certifies it.
