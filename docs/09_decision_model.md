# 09 — The Safety-Aware Decision Model

This chapter is the technical spine of Phase 1, the analogue of [02](02_cyber_physical_model.md) for the
contribution layer. It defines every new component — the **node profiles**, the device-class assignment, the
**decision math** (`select_action`), and the **two D1 channels** — with the mathematics, every symbol
defined, a *"Why it exists"* note per component, and a single-step end-to-end trace. For the metrics it feeds,
see [10](10_metrics.md); for the measured results, [11](11_phase1_results.md).

Everything here imports the frozen Phase 0 engine. The only edits to existing files were *additive*:
`topology.assign_classes()` and a Phase 1 constants block in `config.py`.

> **Phase 1b runtime enrichment (read alongside the formulas below).** Three changes make the decision
> genuinely *runtime-aware* without altering the architecture: (1) **trust floor** — once a node latches
> compromised, $T = \min(1-\rho,\ \texttt{T\_LATCH\_FLOOR}{=}0.35)$, giving the trust signal real range (the
> mean-field $\rho$ alone caps ~0.53); (2) **runtime process state $P\in[0,1]$** (Normal 0.2 / Degraded 0.6 /
> Emergency 1.0) that makes denial *cheaper under active attack*; (3) **IEC-weighted denial cost**
> $S_\text{deny} = 0.35H_s+0.25D_c+0.20A+0.15P+0.05O$ replacing the equal-weight DC, with $P$ as its
> 0.15-weighted term. Plus a coefficient fix: **`restricted` $\gamma$ 0.60→0.50** so it falls below the
> $\texttt{C3\_GAMMA\_MIN}=0.6$ write-path cutoff and actually reduces $pa$. These shift the headline config
> from $\alpha{=}0.8$ to $\alpha{=}0.5$ — see [11](11_phase1_results.md) and [12](12_phase1_divergences.md).

---

## The contribution in one diagram

```
                          ┌─────────────────────── node profiles (fixed) ───────────────────────┐
                          │  H_s  D_c  R_d  ASC_r  →  ASC = ½(D_c+ASC_r),  DC = ⅓(H_s+D_c+R_d)   │
                          └───────────────────────────────┬─────────────────────────────────────┘
   per step:  rho ──► T = 1 − rho ──► profile.T           │
                                          │               │
                                          ▼               ▼
                          select_action(profile, α, β):  A* = argmin_a [ α·R_sec(a) + β·R_saf(a) ]
                                          │
                                          ▼
                                   decisions: node → action               (one of 5 actions)
                          ┌───────────────┼───────────────────────────────┐
            D3 denial     │          D1 security channel          D1 safety channel
                          ▼               ▼                               ▼
              deny nodes → apply_policy   injectable = compromised        observed rows = nodes
              (δ=0.40)  →  B'             AND γ_a≥0.6 (full only)         with O_a>0  →  H_obs
                          │               │                               │
                          ▼               ▼                               ▼
            ┌──── WORM (Phase 0) ────┐   compute_pa(C, H, A, injectable)  observability_cost(H, W, mask)
            │ rho = update_worm(rho,B')│  → pa  (M4)                       → observable?, est_inflation (M7)
            │ compromised = sample_…   │
            └──────────┬───────────────┘
                       └────────────► next step (B' fed back only through deny; soft actions leave B unchanged)
```

The two halves of the system meet exactly as in Phase 0 — through the sensor map `A` and the `compromised`
state — but Phase 1 inserts the **decision** between the worm and the attack: actions *gate* what the
attacker can inject (security channel) and *gate* what the operator can still see (safety channel).

---

## Part A — Node profiles (`node_profiles.py`)

Each of the 55 cyber nodes carries a **fixed** profile (computed once from the Phase 0 topology) plus a
per-step infection probability `rho` and trust `T = 1 − rho`.

> **Why it exists.** The decision function needs a per-node notion of *how much it would hurt to lock this
> node down* (its **denial criticality**, DC) and *how exposed it is* (its **attack-surface criticality**,
> ASC). The profile precomputes these from the device's safety integrity, data criticality, measurement
> redundancy, and graph connectivity, so `select_action` is a cheap per-step lookup.

### A.1 The fields and their formulas

| Field | Symbol | Formula | Meaning |
|---|---|---|---|
| Hardware safety score | $H_s$ | from SIL via IEC 61508 Table 2 | how safety-rated the device is |
| Data criticality | $D_c$ | from device class (Feng's $I_\text{sec}$) | how sensitive its data is |
| Measurement redundancy | $R_d$ | **synthetic** (see A.3) | is there a backup measurement? |
| Relative connectivity | $\mathrm{ASC}_r$ | $\deg(i) / \max_j \deg(j)$ in $B$ | how connected in the worm graph |
| Attack-surface criticality | $\mathrm{ASC}$ | $\tfrac12 D_c + \tfrac12 \mathrm{ASC}_r$ | combined exposure weight |
| Denial criticality | $\mathrm{DC}$ | $\tfrac13 (H_s + D_c + R_d)$ | cost of denying this node |
| Trust | $T$ | $1 - \rho$ (per step) | how trustworthy right now |

All seven are asserted to lie in $[0,1]$ on build and on every per-step update.

### A.2 Device classes and the SIL / criticality maps (`topology.assign_classes()`)

> **Why it exists.** $H_s$ and $D_c$ depend on *what kind of device* a node is. Feng & Hu Fig. 5 does not
> publish a per-node class label for all 55 nodes, so `assign_classes()` derives them **deterministically**
> from structure already in the Phase 0 model — the sensor/non-sensor role (which nodes the map `A` reads)
> and the node's degree in `B`.

The rule (documented as an Assumption A1/A5 approximation):

- **Non-sensor nodes** (`id ≥ 30`, the control plane): degree $\ge 4$ → `C-PDP-critical`; else
  `C-PDP-controller`.
- **Sensor nodes** (`id < 30`, field devices): degree $\ge 4$ → `T-PDP-relay`; degree $= 3$ →
  `T-PDP-sensor`; degree $\le 2$ → `T-PDP-monitor`.

On the Fig. 5 graph this gives all five classes non-empty: **critical 8, controller 17, relay 6, sensor 13,
monitor 11** (= 55). The class then fixes $H_s$ and $D_c$:

| Class | SIL | $H_s$ | $D_c$ |
|---|---|---|---|
| C-PDP-critical | SIL3 | 0.88 | 0.90 |
| C-PDP-controller | SIL2 | 0.63 | 0.70 |
| T-PDP-relay | SIL1 | 0.38 | 0.30 |
| T-PDP-sensor | none | 0.00 | 0.30 |
| T-PDP-monitor | none | 0.00 | 0.30 |

(SIL→$H_s$ from IEC 61508 Table 2, log-PFD/4.00: none 0.00, SIL1 0.38, SIL2 0.63, SIL3 0.88.)

### A.3 Why $R_d$ is *synthetic* (Assumption A2 — read this)

The spec defines redundancy as $R_d = 1 - \max_{j\ne i}\mathrm{coverage}(j\to i)$ with
$\mathrm{coverage}(j\to i) = |\text{buses}(j)\cap\text{buses}(i)| / |\text{buses}(i)|$ — meaningful **only**
if `A` is a real node→bus map. Phase 0's `build_A` is a *synthetic round-robin placeholder* in which distinct
nodes own **disjoint** measurement sets, so $\mathrm{coverage}(j\to i)=0$ for every $j\ne i$ and the formula
degenerates. Phase 1 therefore uses a documented role-based surrogate and **flags it**:

- sensor nodes (own ≥1 measurement under `A`) → $R_d = 1.0$ (no real backup);
- non-sensor nodes (own 0 measurements) → $R_d = 0.0$ (nothing to lose).

Every profile sets `R_d_synthetic = True`. The redundancy axis is exercised for sensitivity by **ABL-4**, not
treated as a validated redundancy map. Replacing `build_A` with a real Fig. 5 incidence would change $R_d$.
This is [Divergence 1](12_phase1_divergences.md) of Phase 1.

---

## Part B — The decision math (`decision.py`)

> **Why it exists.** This is the project's namesake. Zero trust without safety-awareness would simply deny
> anything suspicious — and (as B4 shows) blind the operator. The decision function balances *security risk*
> against *the safety cost of acting*, per node, via two tunable weights.

### B.1 The five actions and their coefficients

Each action carries $(\gamma_a, O_a, C_a)$, and a derived hardening factor
$\delta_a = 1 - \tfrac{O_a + C_a}{2}$:

| Action | $\gamma_a$ (command/attack capability) | $O_a$ (observability kept) | $C_a$ (control kept) | $\delta_a$ |
|---|---|---|---|---|
| `full` | 1.00 | 1.0 | 1.0 | 0.00 |
| `restricted` | 0.50 | 1.0 | 0.5 | 0.25 |
| `read_only` | 0.20 | 1.0 | 0.0 | 0.50 |
| `safe_mode` | 0.10 | 0.2 | 0.0 | 0.90 |
| `deny` | 0.00 | 0.0 | 0.0 | 1.00 |

### B.2 The risk terms and the objective

For a node with trust $T$, attack-surface criticality ASC, and denial criticality DC:

$$ R_\text{sec}(a) = (1 - T)\cdot \mathrm{ASC}\cdot \gamma_a, \qquad R_\text{saf}(a) = \underbrace{S_\text{deny}}_{\text{or } \mathrm{DC}}\cdot \delta_a. $$

- $R_\text{sec}$ is large when the node is **untrusted** (high $1-T$), **exposed** (high ASC), and **retains
  command** (high $\gamma_a$): exactly the conditions under which leaving it `full` is dangerous.
- $R_\text{saf}$ is large when **denying a node that is costly to lose** with a **heavy action** (high
  $\delta_a$). The cost is the IEC-weighted $S_\text{deny}$ (Phase 1b; equal-weight $\mathrm{DC}$ if
  `USE_S_DENY` is False).

> **Phase 1b — runtime process-state coupling.** $P$ enters $R_\text{saf}$ exactly once: as the 0.15-weighted
> term inside $S_\text{deny}$ when that is active, **or** (equal-weight path) as a multiplicative relief
> $R_\text{saf}=\mathrm{DC}\,(1-\texttt{P\_COST\_RELIEF}\cdot P)\,\delta_a$. Either way, a higher $P$
> (emergency) lowers the denial cost, so the method denies/restricts more readily under active attack — the
> mechanism that makes the score *safety-aware at runtime* (demonstrated by Ablation 2 in
> [11](11_phase1_results.md)).

The decision is the per-node argmin over the five actions, with two weights $(\alpha, \beta)$ trading
security against safety:

$$ A^* = \arg\min_a \big[\, \alpha\, R_\text{sec}(a) + \beta\, R_\text{saf}(a) \,\big], \qquad (\alpha,\beta)\in\{(0.8,0.2),(0.5,0.5),(0.2,0.8)\}. $$

`select_action` iterates the actions in the fixed order `full → … → deny`, so ties break deterministically
toward the **least restrictive** action.

> **Reading the extremes.** With $\alpha=1,\beta=0$ (baseline B4) the objective ignores safety entirely and
> collapses toward `deny` — maximal security, zero observability. As $\beta$ rises, $R_\text{saf}$ penalizes
> heavy actions on high-DC nodes, pulling decisions back toward `full`. This is exactly the gradient the M5
> figure in [11](11_phase1_results.md) shows.

---

## Part C — The two physical channels (D1)

A decision is just a label until it changes the simulation. D1 routes each action through **two separate
physical channels**, so soft actions get real teeth while keeping "only `deny` changes $B'$" true (D3).

### C.1 Security channel — $\gamma_a$ gates FDI injection (→ $pa$, M4)

> **Why it exists.** A false-data injection needs a *write path* into the measurement stream. A node that has
> been put in `read_only`, `safe_mode`, or `deny` no longer has that path, so even if the worm has latched it,
> the attacker cannot inject through it.

`injectable_nodes(decisions, compromised)` returns

$$ \text{injectable}_i = \text{compromised}_i \wedge \big(\gamma_{a_i} \ge \texttt{C3\_GAMMA\_MIN}=0.6\big), $$

i.e. a node contributes to the attack **only if** it is compromised **and** its action keeps the C3
write path ($\gamma_{a_i} \ge 0.6$). With the Phase 1b coefficient (restricted $\gamma=0.50$), only
`full` clears this cutoff; `restricted`, `read_only`, `safe_mode`, and `deny` all strip the write path.
This action-gated set — *not* the raw `compromised` set — is fed to the Phase 0
`compute_pa(C_targets, H, A, injectable)`. Restricting/denying nodes therefore *lowers* $pa$.

### C.2 Safety channel — $O_a$ defines the observed set (→ M7)

> **Why it exists.** Locking a node down protects it but costs the operator the measurements it reports. The
> safety channel makes that loss explicit: it is the *physical price* of the security channel's protection.

`observed_rows(decisions, A)` returns a boolean mask over the 41 measurement rows. For each row owned by node
$i$ (the map `A` has one nonzero per row):

- $O_a = 1.0$ (`full`/`restricted`/`read_only`) → keep the row;
- $O_a = 0.2$ (`safe_mode`) → keep a deterministic fraction $\texttt{SAFE\_MODE\_OBS\_FRACTION}=0.2$ of that
  node's rows;
- $O_a = 0.0$ (`deny`) → drop the row.

The kept rows form $H_\text{obs}$, from which M7 (rank + covariance inflation) is computed in
[10](10_metrics.md). Note the asymmetry that drives the whole Phase 1 story: `read_only` **keeps full
observability** ($O_a=1$) while **stripping the write path** ($\gamma_a=0.2<0.6$) — it lowers $pa$ *without*
blinding the EMS. `deny` does both: stops injection *and* removes observability.

### C.3 Denial — the only thing that changes $B'$ (D3)

> **Why partial.** The plant still needs inter-node communication, so a denied node's worm couplings are
> *reduced*, not severed: `apply_actions` hardens exactly the `deny` nodes by $\delta = 0.40$ via the Phase 0
> `apply_policy` (row/column $\times(1-\delta)$). Soft actions leave $B'$ unchanged. Full isolation overshoots
> (Phase 0 [Divergence 3](05_divergences.md)).

---

## Part B.0 — One step, end to end (the execution flow)

A single tick of `decision.run_step(decisions, rho, compromised, B, H, A, C_targets, rng)`, with the array
shape at every handoff (this mirrors the praised trace in [02 §B.0](02_cyber_physical_model.md)):

```
INPUT  decisions: {node→action} (55 entries),  rho (55,),  compromised (55,)

1. D3 denial      apply_actions(decisions, B)        deny nodes → apply_policy(B, ·, δ=0.40)
                                                     → B'  (55, 55)
2. worm           rho = update_worm(rho, B')         (55,) → (55,)          [Phase 0]
   compromise     compromised = sample_compromise(rho, compromised, rng)    [Phase 0, latching]
                                                     → compromised (55,)
3. SECURITY ch.   injectable = injectable_nodes(decisions, compromised)
                     = compromised ∧ (γ_a ≥ 0.6)     → injectable (55,)
                  pa = compute_pa(C_targets, H, A, injectable)              [Phase 0]
                     C_targets (10000, 29), H (41, 29), A (41, 55)
                                                     → pa  (scalar)         → M4
4. SAFETY ch.     obs_mask = observed_rows(decisions, A)
                     A (41, 55), one owner per row   → obs_mask (41,) bool
                  (observable, inflation) = observability_cost(H, W, obs_mask)
                     H (41, 29), W (41, 41)          → (bool, float ≥ 1)    → M7

OUTPUT rho (55,),  compromised (55,),  record{pa, obs_mask, injectable, …}
```

### The two nested loops

- **Inner loop — the 40-step horizon.** `run_policy` (in `run_experiment.py`) calls `select_action` then
  `run_step` for `t = 0 … 39`, logging a record per step. This produces the $pa(t)$ curves and every metric.
  One inner loop ≈ a few hundred milliseconds (it is the same body as Phase 0's Gate A loop).
- **Outer loop — the experiment/ablation sweep.** `run_experiments` runs the inner loop once per policy
  (B1, B3, B4, Proposed×3, and — behind `--full` — B2 at $N_k=10,15$). B2 additionally pays the slow Phase 0
  `greedy_search` ($O(N_k\times55)$ full inner loops, ~10–20 min/$N_k$) to choose its hardened-node set; the
  fast policies are all $O(\text{40 steps})$.

---

## Symbol table (Phase 1)

| Symbol | Code | Shape | Meaning |
|---|---|---|---|
| $H_s$ | `profile["H_s"]` | scalar | hardware safety score (from SIL) |
| $D_c$ | `profile["D_c"]` | scalar | data criticality (from class) |
| $R_d$ | `profile["R_d"]` | scalar | measurement redundancy (**synthetic**) |
| $\mathrm{ASC}_r$ | `profile["ASC_r"]` | scalar | $\deg(i)/\max\deg$ in $B$ |
| $\mathrm{ASC}$ | `profile["ASC"]` | scalar | $\tfrac12 D_c+\tfrac12\mathrm{ASC}_r$ |
| $\mathrm{DC}$ | `profile["DC"]` | scalar | $\tfrac13(H_s+D_c+R_d)$ |
| $T$ | `profile["T"]` | scalar | trust $=1-\rho$ (per step) |
| $\gamma_a, O_a, C_a$ | `config.ACTIONS[a]` | scalar | command / observability / control kept |
| $\delta_a$ | derived | scalar | $1-(O_a+C_a)/2$, hardening factor |
| $\alpha, \beta$ | `config.CONFIGS` | scalar | security / safety objective weights |
| injectable | `injectable_nodes(...)` | (55,) | action-gated compromised set → $pa$ |
| obs_mask | `observed_rows(...)` | (41,) bool | rows kept in $H_\text{obs}$ → M7 |
| $B'$ | `apply_actions(...)` | (55, 55) | worm graph after deny-hardening |

Next: [10 — Metrics M1–M7](10_metrics.md), which defines what `run_step`'s records are reduced to.
