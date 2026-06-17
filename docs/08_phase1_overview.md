# 08 — Phase 1 Overview: The Safety-Aware Decision Function

**Project:** Safety-Aware-CPS-Zero-Trust — a Master's-degree reproduction and extension of Feng & Hu (2023),
*"Cyber-Physical Zero Trust Architecture for Industrial Cyber-Physical Systems."*

Phase 0 ([docs 00–07](00_overview.md)) delivered a **trusted, frozen baseline**: a validated cyber-physical
attack/defense model on the IEEE 30-bus grid whose bypass probability $pa$ and infection level $\bar\rho$
match the paper. **Phase 1 is the project's own contribution layer.** It sits *on top of* that frozen engine
and answers a question Phase 0 never asked: given a worm spreading through the control network, **which
defensive action should each node take — and at what cost to the physical grid's visibility?**

Phase 1 adds a **safety-aware, five-action decision function**. For every cyber node, every step, it chooses
one of {`full`, `restricted`, `read_only`, `safe_mode`, `deny`} by minimizing a weighted sum of a **security
risk** term and a **safety/denial cost** term. The novelty is the explicit *trade-off*: denying a node stops
attacks but blinds the operator's state estimator, and Phase 1 makes that cost a first-class, measured
quantity (metric **M7**).

> **One-line framing.** Phase 0 asked *"can the attacker get through?"* ($pa$). Phase 1 asks *"how do we keep
> the attacker out **without** going blind?"* — and measures both sides.

---

## What Phase 1 adds, concretely

| New piece | What it is | Source |
|---|---|---|
| **Node profiles** | per-node safety/security attributes ($H_s, D_c, R_d, \mathrm{ASC}, \mathrm{DC}$) + per-step trust $T$ | `node_profiles.py`, `topology.assign_classes()` |
| **Decision function** | `select_action`: per-node argmin of $\alpha R_\text{sec} + \beta R_\text{saf}$ over five actions | `decision.py` |
| **Two physical channels (D1)** | security channel ($\gamma_a\to pa$) and safety channel ($O_a\to$ observability) | `decision.py` |
| **Metrics M1–M7** | M1–M6 (v4 verbatim) + **M7**, the new physical-observability cost | `metrics.py` |
| **Experiments & ablations** | 8 experiments (4 baselines + proposed at 3 weightings) + 4 ablations | `run_experiment.py` |

Everything imports and **reuses** the frozen Phase 0 engine (`power_system`, `attack_engine`, `topology`,
`policy_engine`); no Phase 0 module was re-implemented. The Phase 0 six-gate runner and 17 unit tests (the
Phase 0 subset; the full current suite is 58 tests) stay
green, and a **channel-fidelity guarantee** (see [10](10_metrics.md)) proves the new wiring rides exactly on
the validated engine: an all-`full` policy reproduces Gate A's $pa = 0.7408$ to $10^{-12}$.

---

## The three baked-in design decisions (D1, D2, D3)

These three decisions, fixed in the spec, make the five-action model physically meaningful while keeping
Phase 0 intact. Full detail in [09](09_decision_model.md); in plain language:

- **D1 — soft actions act through *two separate channels*.** Each action carries coefficients
  $(\gamma_a, O_a, C_a)$.
  - **Security channel ($\gamma_a$ → $pa$ / M4).** A compromised node's measurements can carry a false-data
    injection *only if* the node keeps its command/write path — i.e. its action is `full` or `restricted`
    ($\gamma_a \ge 0.6$). `read_only`, `safe_mode`, `deny` strip that write path, so an attacker cannot inject
    through them even when the node is infected. (Physically: FDI needs a write path.)
  - **Safety channel ($O_a$ → M7).** The fraction $O_a$ of a node's measurements still reported to the energy
    management system (EMS) defines what the state estimator can still see. Denying sensors removes their rows
    from the observed matrix → degraded estimation. This is the *physical cost of denial*.
- **D2 — keep static DC power flow and metrics M1–M6 verbatim; *add* M7.** M7 is the independent physical
  axis: is the still-observed system observable, and how much does the estimate's covariance inflate?
- **D3 — one denial mechanism everywhere: partial hardening $\delta = 0.40$.** Only `deny` hardens the worm
  graph $B \to B'$, via the existing Phase 0 `apply_policy`. Soft actions leave $B'$ unchanged. The five-action
  *security gradient* lives entirely in the $\gamma$-channel, not in differential $B'$ changes. (Full node
  isolation overshoots — see Phase 0 [Divergence 3](05_divergences.md).)

---

## Headline results — the trade-off table

All produced by `python -m zt_cps_phase0.src.run_experiment --full` and stored in `results/Exp*.csv`
(**Phase 1b** run: runtime process-state **P**, the latched-compromise **trust floor**, IEC-weighted
**S_deny**, and the **restricted** write-path fix). M1, M2, M3 are averaged over the 40-step horizon; M4 is
the mean $pa$; M7 reports the mean covariance inflation over observable steps and the fraction of steps that
stayed observable. **Lower is better for M1, M2, M4; higher is better for M7's observable fraction.**

| Experiment | Policy | M1 ↓ | M2 ↓ | M3 | M4 ($pa$) ↓ | M7 infl | M7 obs ↑ |
|---|---|---|---|---|---|---|---|
| Exp1 | B1 binary ZT | 1.00 | 0.2926 | 0.0207 | 0.0016 | 1.000 | 0.025 |
| Exp4 | B3 naive 5-action | 0.00 | 0.3267 | 0.0492 | 0.0016 | 1.000 | 0.025 |
| Exp5 | B4 security-only ($\alpha{=}1$) | 1.00 | 0.4410 | 0.0000 | **0.0000** | ∞ | **0.00** |
| Exp6 | Proposed $\alpha{=}0.8$ | 1.00 | 0.2869 | 0.0197 | **0.0000** | 1.000 | 0.025 |
| **Exp7** | **Proposed $\alpha{=}0.5$ (headline)** | **0.00** | 0.1033 | 0.1358 | **0.0016** | 1.000 | **1.00** |
| Exp8 | Proposed $\alpha{=}0.2$ | **0.00** | **0.0000** | 0.2875 | 0.7414 | 1.000 | **1.00** |
| Exp2 | B2 FENG greedy $N_k{=}10$ | 1.00 | 0.0590 | 0.2311 | 0.4671 | ∞ | **0.00** |
| Exp3 | B2 FENG greedy $N_k{=}15$ | 1.00 | 0.0933 | 0.2062 | 0.4068 | ∞ | **0.00** |

![Phase 1 trade-off bars](figures/phase1_tradeoff_bars.png)

*The green bars are M7's observable fraction. **Almost every policy that drives $pa$ (M4) toward zero also
drives observability toward zero** — security bought with blindness (B1, B3, B4, B2, and $\alpha{=}0.8$).
**Proposed $\alpha{=}0.5$ is the lone exception:** M4 ≈ 0 with M7obs = 1.0 — it restricts rather than denies,
so it stops the attack while keeping the operator sighted.*

### The one paragraph that matters

The **Milestone 2 gate** (strict: a proposed config beating B2 on M1 **and** M2 while keeping M4 within ±10%
of B2) is **not met** — for an instructive reason, not a failure of the method. The robust contribution is
the **M7 column**: with the Phase 1b runtime awareness, **Proposed $\alpha{=}0.5$ is the only policy that
collapses $pa$ to ~0 *and* preserves full physical observability (M7obs = 1.0)**, because it puts latched
nodes in `read_only` (strips the FDI write path, keeps measurement rows) rather than `deny`. Every other
low-$pa$ policy — B1, B3, B4, B2, and the security-dominant $\alpha{=}0.8$ — blinds the EMS (M7obs ≈ 0). The
gate's M2 condition rewards B2's narrow-but-blinding denial; the safety-aware method instead spends more
denial budget to keep the grid *visible*. The narrative is a *trade-off* (balance preserves visibility while
collapsing $pa$), **not** a "beats Feng & Hu on security" claim. See [12](12_phase1_divergences.md) for why
the headline config shifted from $\alpha{=}0.8$ (Phase 1) to $\alpha{=}0.5$ (Phase 1b).

---

## Study aids — three questions, where each is answered

These docs are written to be fed to an AI for study-material generation (as the Phase 0 docs were). The three
core questions map to specific places in the Phase 1 set:

| Question | Where it is answered explicitly |
|---|---|
| **What each new component does and *why* it exists** | [09](09_decision_model.md) — each subsection (profiles, `assign_classes`, the decision math, the two channels) opens with a *"Why it exists"* note |
| **What the M1–M7 results mean numerically *and physically*** | [10](10_metrics.md) (each metric defined + interpreted) and [11 §"What the numbers mean"](11_phase1_results.md) (one physical sentence per experiment row) |
| **How the components connect in the overall flow** | [09 §B.0](09_decision_model.md) — a single-step end-to-end **trace with array shapes** through both D1 channels; the top-of-09 diagram shows the `deny→B'` feedback and the two nested loops |

---

## Document map (Phase 1 chapters)

Read [00](00_overview.md)–[07](07_environment_repro.md) first for the frozen engine, then:

| # | Document | What it gives you | For |
|---|---|---|---|
| 08 | **this file** | orientation, headline trade-off, the three decisions | everyone |
| 09 | [Decision model](09_decision_model.md) | profiles, `select_action`, the two D1 channels, single-step trace | technical core |
| 10 | [Metrics M1–M7](10_metrics.md) | every metric defined + interpreted; the M7 safety axis; CSV format | results / examiner |
| 11 | [Phase 1 results & validation](11_phase1_results.md) | 8 experiments + 4 ablations, the Milestone-2 verdict, figures, 29 tests | examiner / results section |
| 12 | [Phase 1 divergences](12_phase1_divergences.md) | the five honest modeling choices (incl. R_d synthetic, the gate verdict, DQL deferred) | integrity / defense |

The authoritative specification is [`PHASE1_SPEC.md`](PHASE1_SPEC.md) (D1/D2/D3, §§2–9, the Milestone 2 gate).
Where these chapters and the spec agree, the spec is the source of truth; these chapters *explain* it.

---

## What Phase 1 deliberately does **not** include

The original Phase 0 roadmap ([06](06_roadmap_phase1.md)) anticipated that Phase 1 would bring deep
Q-learning (DQL) and a physical **safety cost $S_c$** with objective $J = pa + \lambda S_c$. **Those remain
deferred.** Phase 1's "proposed method" is the *deterministic* `select_action` decision function — not a
learned policy — and its safety axis is **M7** (observability cost), not a line-flow/voltage $S_c$. The
roadmap has been annotated accordingly; the DQL environment seam and the $S_c$ physical-impact model are now
the Phase 2 plan. See [12 §5](12_phase1_divergences.md) and the [06 status update](06_roadmap_phase1.md).
