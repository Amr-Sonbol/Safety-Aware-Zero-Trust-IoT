# 12 — Phase 1 Divergences & Honest Modeling Choices

This is the Phase 1 integrity chapter, the analogue of [05](05_divergences.md). It records every place where
the implementation exercises modeling judgment beyond the literal spec, or where a result departs from what
the spec anticipated — each with the expectation, why the literal version is degenerate or insufficient, the
choice made, and why it is defensible. An examiner should be able to read this and see exactly where Phase 1
is honest about its limitations.

There are **five**.

---

## Divergence 1 — $R_d$ is synthetic under the round-robin `A`

**Where:** `node_profiles.build_node_profiles` (module docstring documents this); Assumption A2 in
[`PHASE1_SPEC.md`](PHASE1_SPEC.md) §2.

**Spec recipe.** Measurement redundancy $R_d = 1 - \max_{j\ne i}\mathrm{coverage}(j\to i)$ with
$\mathrm{coverage}(j\to i) = |\text{buses}(j)\cap\text{buses}(i)| / |\text{buses}(i)|$ — a node is redundant
if another node measures the same buses.

**Why it is degenerate as written.** $R_d$ is only meaningful if `A` is a real node→bus incidence. Phase 0's
`build_A` is a *synthetic round-robin placeholder*: measurement $m$ is assigned to sensor node $m \bmod 30$,
so distinct nodes own **disjoint** measurement sets. Then $\mathrm{coverage}(j\to i)=0$ for every $j\ne i$,
giving $R_d = 1$ for every sensor node and an *undefined* $R_d$ (zero measurements) for the 25 non-sensor
nodes. The formula carries no real information.

**Choice.** Keep the placeholder `A`, use a documented role-based surrogate, and **flag it on every profile**
(`R_d_synthetic = True`): sensor nodes (own ≥1 measurement) $\to R_d = 1.0$; non-sensor nodes (own 0) $\to
R_d = 0.0$. Lean on ablation **ABL-4** for sensitivity rather than claiming a validated redundancy axis.

**Why it is defensible.** It keeps $\mathrm{DC} = \tfrac13(H_s+D_c+R_d)$ well-defined and in $[0,1]$, it is
transparent (the flag and the docs say "synthetic"), and it does not *pretend* a round-robin map is a
redundancy map. The honest fix is a real Fig. 5 `A`; until then $R_d$ is a labeled placeholder, not evidence.

---

## Divergence 2 — Device classes assigned by role + degree (no published labels)

**Where:** `topology.assign_classes` (additive to the frozen module; Assumption A1/A5).

**Spec recipe.** Each node has a device class (C-PDP-critical/controller, T-PDP-relay/sensor/monitor) "read
from FENG2023 Fig. 5."

**Why the literal reading is unavailable.** Fig. 5 does not publish a per-node class label for all 55 nodes
(the Phase 0 topology docs already note the figure is read approximately). There is nothing to transcribe.

**Choice.** Derive classes **deterministically** from structure already in the validated model: the
sensor/non-sensor role (which nodes the map `A` reads) and node degree in `B`. Non-sensor (`id≥30`) → C-PDP
(critical if degree ≥4, else controller); sensor (`id<30`) → T-PDP (relay/sensor/monitor by degree tier).

**Why it is defensible.** It is reproducible, it yields all five classes non-empty (8/17/6/13/11 = 55), and
it respects the model's real distinction (control plane vs. field devices) rather than inventing arbitrary
labels. It is documented as an approximation, and the metric most sensitive to it (M5, the per-class action
distribution) is *descriptive*, not a gate.

---

## Divergence 3 — Mean-field trust vs. latched compromise (why some configs sit at the $pa$ ceiling)

**Where:** the interaction between `node_profiles.update_profiles` ($T = 1-\rho$, mean-field) and the
security channel ($\text{injectable}$ uses the *latched* `compromised`).

**The subtlety.** Phase 0 has **two** notions of infection: the deterministic mean-field $\rho$ (from
`update_worm`, which saturates near $\bar\rho \approx 0.318$ and whose hottest node only reaches
$\rho \approx 0.53$), and the **latched** binary `compromised` set (from `sample_compromise`, which
accumulates toward full coverage over the horizon). Phase 1's trust signal is $T = 1-\rho$ (the *mean-field*
value, per spec §3), while the attacker's reachable set is the *latched* `compromised`.

**The consequence.** Because mean-field $\rho$ caps around 0.53, trust $T = 1-\rho$ rarely drops below ~0.47.
So trust-threshold policies (B1's $T<0.5$, B3's tiers) and the safety-leaning proposed configs
($\alpha=0.5/0.2$) **rarely trigger denial or restriction** — even though the *latched* compromise has
reached most nodes. Those configs therefore leave the write path open and $pa$ stays at the undefended
ceiling (0.7414). Only the security-leaning $\alpha=0.8$ weights $R_\text{sec}$ heavily enough to restrict
nodes at moderate trust and pull $pa$ down to 0.394.

**Why it is faithful (not a bug).** $T = 1-\rho$ is exactly the spec definition (§3), and the mean-field
$\rho$ is the validated Phase 0 worm. The behaviour is a *correct* consequence of the endemic equilibrium
documented in Phase 0 [04](04_results_and_validation.md). It is called out here because it explained the
*original Phase 1* trade-off table's shape — and it pointed at a clean lever: feed the latched compromise into
the trust signal to widen its dynamic range. **Phase 1b takes that lever.**

### Phase 1b refinement — the latched-compromise trust floor (and why the headline config shifted)

The narrow mean-field range left two of three proposed configs inert (at the $pa$ ceiling), so Phase 1b
introduces a **trust floor**: once a node latches compromised, $T = \min(1-\rho,\ \texttt{T\_LATCH\_FLOOR})$
with `T_LATCH_FLOOR = 0.35`. $T = 1-\rho$ remains the spec-faithful default for un-latched nodes; the floor is
an *intentional refinement*, recorded here, not a silent change to the spec definition.

**Before → after (the affected configs):**

| Config | Phase 1 ($T=1-\rho$) | Phase 1b (trust floor 0.35) |
|---|---|---|
| $\alpha{=}0.8$ | M4 0.394, M7obs 1.00 (the old headline) | M4 0.000, **M7obs 0.03** (now over-denies → blinds EMS) |
| $\alpha{=}0.5$ | M4 0.741 (inert, at ceiling) | **M4 0.0016, M7obs 1.00** (the new headline) |
| $\alpha{=}0.2$ | M4 0.741 (inert) | M4 0.741 (still soft; safety-dominant keeps nodes full) |

**The headline config shifted from $\alpha{=}0.8$ to $\alpha{=}0.5$.** With usable trust range, the
security-dominant $\alpha{=}0.8$ now *denies* latched nodes (dropping their measurement rows, blinding the
EMS — exactly what B2/B4 do). The *balanced* $\alpha{=}0.5$ instead puts them in a **write-stripped but
fully-observable** action (`restricted` at the default floor 0.35; `read_only` at lower floors): either way
$\gamma<0.6$ strips the FDI write path (so $pa\to0$) while $O_a=1.0$ keeps every measurement row reported (so
M7obs stays 1.0). The balanced config is the only policy that gets both — a *stronger* and more defensible
result than the Phase 1 headline.

**Floor-sensitivity (E1 sweep — `results/sweep_tlatch.csv`, `docs/figures/fig_tlatch_sweep.png`).** Sweeping
`T_LATCH_FLOOR` over $[0.15, 0.50]$ shows the $\alpha{=}0.5$ outcome (M4 $\approx$ 0.0016, M7obs = 1.0) is
**robust across the entire band** — a wide *regime*, not a knife-edge; the default 0.35 sits mid-plateau. What
the floor selects for $\alpha{=}0.5$ is merely *which* write-stripping action dominates (`read_only` at floors
$\le 0.30$, `restricted` at the default and above) — immaterial to M4/M7, since both strip the write path and
keep all rows; $\alpha{=}0.5$ never reaches `deny` anywhere in $[0.15, 0.50]$. It is the **security-dominant
$\alpha{=}0.8$** that is floor-sensitive: it is `deny`-dominant (M7obs $\approx$ 0, EMS blinded) for floors
0.15–0.45 and only relaxes off `deny` near 0.50. So the "deeper floor $\to$ `deny` $\to$ re-blinds the EMS"
mechanism is real, but it belongs to $\alpha{=}0.8$, not to the balanced config.

### Phase 1b refinement — runtime process state $P$ (the "aware" mechanism)

Phase 1's denial cost was built only from design-time attributes, so a node's safety cost was identical when
idle and under active attack. Phase 1b adds a per-step process state $P\in[0,1]$ (Normal/Degraded/Emergency,
keyed to mean infection and the previous step's $pa$) that *lowers the denial cost during an emergency*. It
enters $R_\text{saf}$ once — via the 0.15 weight inside $S_\text{deny}$ when that is active, else as a
multiplicative relief. Ablation 2 ([11 §4](11_phase1_results.md)) demonstrates the point directly: holding
design-time attributes fixed and changing **only** $P$ flips the chosen action (e.g. $\alpha{=}0.5$:
`read_only` → `deny` as the phase escalates). This is what makes the score genuinely *safety-aware at runtime*.

---

## Divergence 4 — The strict Milestone 2 gate is not met (but the safety claim holds)

**Where:** [11 §5](11_phase1_results.md); spec §8.

**Expectation.** The gate expects a config that beats B2 on M1 **and** M2 while keeping M4 within ±10% of B2
— i.e. a method that is *both* safer than the FENG greedy *and* security-comparable to it.

**What actually happens (Phase 1b run).** No single config hits all three. The headline $\alpha{=}0.5$ beats
B2 decisively on M1 (0 vs 1.0) and crushes $pa$ (0.0016 vs 0.467), but its aggregate denial cost M2 (0.103)
exceeds B2's (0.059): B2 denies *few* nodes (low M2) but blinds the EMS, while $\alpha{=}0.5$ restricts
*many* nodes (higher M2) but keeps the EMS sighted. And the ±10% M4 band never fits — the proposed configs
are far below B2 on $pa$ or at the ceiling, never *comparable* to B2's 0.467.

**Why this is reported as a finding, not patched away.** The gate could be trivially "passed" by widening the
band or cherry-picking, but that would misrepresent the result. The honest, robust contribution is the **M7
axis**: with Phase 1b, **$\alpha{=}0.5$ is the only policy that drives $pa\to0$ while keeping observability at
1.0** — every other low-$pa$ policy (B1, B3, B4, B2, $\alpha{=}0.8$) blinds the EMS. The defensible claim is a
**trade-off** (security collapsed *and* visibility preserved by the balanced config), explicitly *not* "beats
Feng & Hu on security." The spec's own §8 anticipates this narrative ("a trade-off … not 'beats FENG'").

**Where to debug if revisited (per spec §8).** `select_action`, the $\gamma$-injection channel, and
`apply_actions` — *never* the Phase 0 engine.

---

## Divergence 5 — DQL and the safety cost $S_c$ remain deferred

**Where:** the Phase 0 roadmap [06](06_roadmap_phase1.md) anticipated them; this Phase 1 does not implement
them.

**Expectation.** The Phase 0 roadmap predicted Phase 1 would deliver deep Q-learning (a *learned* defense
policy) and a physical **safety cost** $S_c$ (line-flow / voltage-limit impact of a successful attack), with
a combined objective $J = pa + \lambda S_c$.

**What shipped instead.** The Phase 1 "proposed method" is the **deterministic** `select_action` decision
function — a per-node argmin, not a learned policy. The safety axis is **M7** (state-estimation observability
cost), which reuses the existing physics, *not* a new line-flow/voltage $S_c$ model. The `config.LAMBDA`
constant exists as a reserved placeholder but is consumed by no Phase 1 code.

**Why this is the right scope.** The spec ([`PHASE1_SPEC.md`](PHASE1_SPEC.md)) deliberately scopes Phase 1 to
the decision function and M1–M7 on top of the frozen engine, with DQL/$S_c$ explicitly out of scope. M7 is a
genuine, non-circular physical safety axis that needed no new impact model and kept the Phase 0 contract
intact. DQL (wrapping `evaluate_policy` as an RL environment) and $S_c$ (a `safety.py` reusing $H, K$,
`generate_z`, and the feasible-attack construction) are now the **Phase 2** plan — the roadmap's §2 seams
remain valid and are annotated as such in the [06 status update](06_roadmap_phase1.md). (Phase 1b's $S_\text{deny}$
in Divergence 6 is the denial-cost *weighting*, not the physical $S_c$; they are distinct.)

---

## Divergence 6 — IEC-weighted $S_\text{deny}$ with static availability/operational proxies (Phase 1b)

**Where:** `node_profiles._s_deny` / the `config.S_DENY_WEIGHTS`, `AVAIL_BY_CLASS`, `OP_IMPACT_BY_CLASS`.

**Proposal recipe.** $S_\text{deny} = 0.35H + 0.25D + 0.20A + 0.15P + 0.05O$.

**What we mapped.** $H \leftarrow H_s$ (SIL) and $D \leftarrow D_c$ (class criticality) already exist; $P$ is
the runtime process state (Task 1). **$A$ (availability) and $O$ (operational impact) are documented STATIC
per-class proxies** (`AVAIL_BY_CLASS`, `OP_IMPACT_BY_CLASS`) — *not* live models. In particular $O$ is **not**
computed from a per-step MATPOWER solve (explicitly out of scope); it is a fixed per-class stand-in.

**Why it is defensible.** It aligns the denial cost with the proposal's IEC weighting and makes the
weight-sensitivity ablation (**ABL-1**) meaningful — which reports the proposed metrics move <10% under ±50%
weight swings (the proposal's robustness claim, confirmed). The proxies are labeled static; replacing $O$
with a live load-flow impact model is future work. When $S_\text{deny}$ is active it *replaces* DC in
$R_\text{saf}$ and in the DC-reading metrics (M1 gate, M2), and the multiplicative $P$-relief is dropped so
$P$ is counted exactly once.

---

## Divergence 7 — `restricted` $\gamma$ lowered 0.60 → 0.50 (Phase 1b)

**Where:** `config.ACTIONS["restricted"]["gamma"]`.

**The issue.** A node is injectable iff $\gamma_a \ge \texttt{C3\_GAMMA\_MIN} = 0.6$. With `restricted` at
$\gamma = 0.60$ — exactly the threshold — it never reduced $pa$ relative to `full`: a dead position in the
security channel.

**Choice.** Lower `restricted` to $\gamma = 0.50$ so it falls below the cutoff and strips the FDI write path,
giving it a real graduated security effect between `full` and `read_only`. $\delta_\text{restricted}$ is
unchanged (it depends on $O, C$, not $\gamma$): still 0.25.

**Why it is defensible / did not destabilize the headline.** It sharpens the contribution: it is part of why
the headline $\alpha{=}0.5$ reaches $pa \approx 0$ via restriction. The channel-fidelity guarantee is intact
(all-`full` is unaffected — only `restricted` changed), and re-running confirmed the $\alpha{=}0.5$ headline
(low $pa$ + full observability) is preserved, so the optional Task 4 was kept rather than reverted.

---

## Summary

| # | Divergence | Honest status |
|---|---|---|
| 1 | $R_d$ synthetic under round-robin `A` | flagged `R_d_synthetic`; needs real Fig. 5 `A`; exercised by ABL-4 |
| 2 | classes by role+degree | deterministic approximation; all 5 classes non-empty; feeds descriptive M5 |
| 3 | mean-field $T$ → **Phase 1b trust floor** | refinement recorded with before/after; headline shifted $\alpha{=}0.8\to0.5$ |
| 4 | strict Milestone-2 gate not met | reported as a trade-off, not patched; M7 is the robust claim |
| 5 | DQL / physical $S_c$ deferred | intentional scope; now the Phase 2 plan |
| 6 | IEC-weighted $S_\text{deny}$, static $A$/$O$ proxies | aligns with proposal weights; ABL-1 robust <10%; $O$ not a live model |
| 7 | `restricted` $\gamma$ 0.60→0.50 | gives `restricted` a real security effect; headline preserved (Task 4 kept) |

These are the seams an examiner should probe — and the honest answers are above. The physics
($H, K, pa$, the worm) is the validated Phase 0 baseline ([05](05_divergences.md)); the Phase 1/1b judgment
calls live entirely in the decision layer, the (synthetic/static) profile inputs, the runtime trust/process
signals, and the choice of M7 as the safety axis.
