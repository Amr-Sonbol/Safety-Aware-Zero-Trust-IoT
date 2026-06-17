# 02 — The Cyber-Physical Attack Model (End-to-End)

This is the technical spine of Phase 0. It walks the full model **in execution order**, and for
each step gives the mathematics (the equation the paper specifies), the code that implements it,
and the modeling assumption it encodes. Section anchors use the paper's equation labels that also
appear in the source docstrings: the worm is *Eq. 4*, the measurement model and estimator are
*Eqs. 5–6*, and the bypass probability is *Eq. 7*.

The model has two halves that meet at the measurement layer:

```
   PHYSICAL HALF (built once)            CYBER HALF (evolves over 40 steps)
   power_system.py                       topology.py, attack_engine.py

   IEEE 30-bus  ──► H (DC Jacobian)      worm graph B  ──◄── B' (defender hardens, Part C)
        │                │                       │
        ▼                ▼                       ▼  update_worm  (mean-field SIS, B.3)
   DC power flow     WLS estimator K        ρ(t)  infection probabilities
        │                │                       │  sample_compromise (Bernoulli + latch, B.4)
        ▼                │                       ▼
   z (real flows)  ──────┘            compromised(t) ──► A ──► mask(t)   (B.2, B.5)
        │                                                          │
        │  (z, H certify the physics                               ▼
        │   via the residual check, A.6)          _feasible_projector → P(t)   (B.6)
        │                                                          │
        └───────────────► H ──────────────────────────────────────┤
                                                                   ▼
                                                       compute_pa → pa(t)   (B.7)

   ── inner loop: repeat the cyber half for t = 0 … 39, average pa(t)  → one policy's score
   ── outer loop: greedy_search tries hardenings B → B', re-runs the inner loop to pick nodes (Part C)
```

The physical half (`H`, `K`) is built **once**. The cyber half **evolves**: each step the worm updates
$\rho$, latches more compromised nodes, and re-computes $pa$. The defender closes the loop by perturbing
`B → B'`, which changes the worm and re-runs everything downstream. The two control loops (inner 40-step
horizon, outer greedy node-selection) are traced concretely in [§B.0](#b0-one-step-and-two-loops-the-execution-flow).

---

## Part B.0 — One step, and two loops: the execution flow

Before the component-by-component walk, here is how a single simulation **tick** flows end-to-end, with the
array shape at every handoff. This is the body of the inner loop (one value of `t`); `N=29`, `M=41`,
55 nodes, 10 000 FDI targets:

```
ρ            (55,)                         # infection probabilities entering the step
  │ update_worm(ρ, B')                     # mean-field SIS, Eq. 4            (B.3)
  ▼
ρ⁺           (55,)                         # updated probabilities
  │ sample_compromise(ρ⁺, compromised, rng)# Bernoulli draw, then latch       (B.4)
  ▼
compromised  (55,)   {0,1}                 # permanent compromised set (grows only)
  │ measurement_mask(A, compromised)       # A(41,55) @ v(55,) → (41,)         (B.5)
  ▼
mask         (41,)   {0,1}                 # which measurements are tamperable this step
  │ _feasible_projector(H, mask)           # SVD of H restricted to UN-masked rows → null-space proj (B.6)
  ▼
P            (29,29)                        # projector onto realizable-undetectable attack directions
  │ compute_pa(C_targets, H, A, compromised)# ‖H P c‖ / ‖H c‖ ≥ 0.30 over 10 000 targets c  (B.7)
  ▼
pa(t)        scalar ∈ [0,1]                # bypass probability at this step
```

**The two loops that wrap this body:**

- **Inner loop — the 40-step horizon.** Run the body above for `t = 0,1,…,39`, carrying `ρ` and
  `compromised` forward each step, and average the 40 values of `pa(t)`. That average is the score of *one*
  trust graph. With no defense ($B'=B$) this is **Gate A** (→ 0.7408); the resulting `pa(t)` is the S-curve
  in [04 §3.1](04_results_and_validation.md). `evaluate_policy` (C.2) *is* this inner loop.
- **Outer loop — greedy node selection.** To defend, `greedy_search` (C.3) wraps the inner loop: for a
  budget $N_k$, it does $N_k$ rounds, and in each round it tries hardening *every* not-yet-chosen node
  (~55 candidates), running a **full inner loop** for each, and keeps the node that most lowers the average
  $pa$. That is the $O(N_k\times55)$ cost — ~$N_k\times55$ forty-step simulations — and why **Gate A takes
  ~3 s but each Gate B budget takes ~5–10 min** (see [03 §6](03_code_architecture.md)). Hardening a node is
  the `B → B'` feedback arrow in the diagram above.

With the flow in hand, the rest of Part B explains each box in turn.

---

## Part A — Physical layer

### A.1 Network and DC power flow → `load_network()`

The plant is the **IEEE 30-bus** system loaded via `pandapower.networks.case_ieee30()` and solved with
DC power flow (`pp.rundcpp`). DC power flow linearizes the AC equations under the standard assumptions
(flat ~1 p.u. voltages, small angle differences, negligible branch resistance), so real power flow on a
branch depends only on the angle difference across it. The case has **30 buses**, **41 branches**
(34 lines + 7 transformers), total load **283.4 MW**, slack voltage **1.06 p.u.** — all asserted at load
time.

The **state vector** is the bus voltage angles with the slack angle removed (it is the reference, fixed
at 0). Hence the state dimension is

$$ N = N_{\text{bus}} - 1 = 30 - 1 = 29. $$

### A.2 The measurement matrix H — the DC Jacobian (Eq. 5) → `build_H()`

Measurements are the **active-power flows on all 41 branches**. For a branch $k$ from bus $i$ to bus $j$
with series reactance $x_k$ and (transformer) tap ratio $\tau_k$, the DC flow is

$$ P_{ij} \;=\; \frac{\theta_i - \theta_j}{x_k\,\tau_k}. $$

So each **row** of the measurement matrix $H \in \mathbb{R}^{M\times N}$ (with $M=41$, $N=29$) is

$$ H_{k,\,i} = +\frac{1}{x_k\,\tau_k}, \qquad H_{k,\,j} = -\frac{1}{x_k\,\tau_k}, $$

with the slack column dropped. **The entries are reactance weights $1/(x\tau)$, never $\pm 1$.** Building
$H$ as a $\pm 1$ incidence matrix is the classic state-estimation bug; the code guards against it (see
A.5). Transmission lines have $\tau = 1$ (stored as `tap = 0` in MATPOWER, which the code maps to 1);
transformers carry off-nominal taps (e.g. 0.932, 0.978), and omitting $\tau$ there is what made an early
clean residual 0.0226 instead of ~$10^{-12}$.

`build_H` returns `(H, branch_rows, state_index)`:
- `branch_rows` — the `_ppc` branch-matrix rows (lines then transformers) **in H's row order**, so the
  measurement generator reads flows in the exact same order.
- `state_index` — maps each non-slack `_ppc` bus to its column in $H$.

$H$ is asserted to be **full column rank 29** (the system is observable from these measurements).

### A.3 Noise model R (Eq. 5) → `build_R()`, `compute_sigma()`

Measurements carry zero-mean Gaussian noise $e \sim \mathcal{N}(0, R)$ with a diagonal covariance
$R = \operatorname{diag}(\sigma_1^2,\dots,\sigma_M^2)$ and a heteroscedastic standard deviation

$$ \sigma_m \;=\; \max\!\big(\texttt{NOISE\_REL}\cdot|z_m|,\ \texttt{SIGMA\_FLOOR}\big)
   \;=\; \max\!\big(0.02\,|z_m|,\ 10^{-3}\big). $$

The relative term models 2 % metering error; the floor keeps $R$ non-singular at near-zero-flow branches.

### A.4 The WLS estimator K (Eq. 6) → `build_estimator()`

The state estimate is $\hat\theta = K z$ with the weighted-least-squares gain

$$ K \;=\; (H^{\mathsf T} W H)^{-1} H^{\mathsf T} W, \qquad W = R^{-1}. $$

Weighting by the inverse noise covariance $W=R^{-1}$ makes this the **maximum-likelihood Gaussian
estimator**. By construction $K H = I_N$ (a left inverse), which the tests check to $10^{-9}$.

### A.5 Real measurements z (never random) → `generate_z()`

At step $t$ the loads are scaled by the profile multiplier `profile[t]` (the synthetic ±15 % daily
curve, see [07](07_environment_repro.md)), DC power flow is re-solved, and the branch flows are read for
exactly `branch_rows`:

$$ z_{\text{clean}} \;=\; \frac{P_{\text{branch}}\,[\text{MW}]}{100\ \text{MVA}}, \qquad
   z \;=\; z_{\text{clean}} + e, \quad e\sim\mathcal N(0,R). $$

The division by the 100 MVA system base converts MW flows to per-unit so that $z$ lives in the **same
units as $H$** (which is in $1/x$ per-unit). **The measurements are real DC flows, never random noise** —
this is what makes the unobservability self-check below pass.

### A.6 The unobservability self-check → `clean_residual_norm()`

Because clean per-unit flows lie exactly in the column space of $H$, the WLS-projected residual of a
clean measurement must be at machine precision:

$$ r \;=\; \big\| z_{\text{clean}} - H\,(K\,z_{\text{clean}})\big\|_2 \;\approx\; 0. $$

Phase 0 achieves $r = 7.89\times 10^{-12}$. A large $r$ is the **#1 gate-killer** — it means $H$ and $z$
disagree on units or branch ordering, and every downstream attack number would be meaningless. This check
is the foundation everything else stands on.

---

## Part B — Cyber layer

> **Why a cyber layer at all — the cyber-physical bridge.** Part A is pure physics: it says how branch
> flows relate to bus angles and how an estimator recovers the state. By itself it has no attacker. The
> cyber layer supplies one: a worm spreads over a trust graph $B$ (B.1), reaches *sensor* nodes, and the
> sensor map $A$ (B.2) translates "which cyber nodes are compromised" into "which physical measurements
> can be tampered with." **The two halves meet at exactly one place** — the compromised set plus $H$ feed
> the FDI feasibility test (B.6), which produces the headline metric $pa$ (B.7). Remove $A$ and the worm
> can never touch the physics; remove the worm and there is nothing to compromise. Everything in Part B
> exists to turn a cyber intrusion into a *physically realizable, undetectable* measurement attack.

### B.1 The 55-node infection graph B (paper Fig. 5) → `build_B()`

> **Why it exists.** $B$ is the *attack-surface topology*: nodes are cyber assets (e.g. SCADA/sensor
> devices) and edges are the trust relationships the worm rides from one asset to the next. It is the only
> thing that decides *how fast and how far* an intrusion spreads — and it is the object the defender later
> perturbs ($B \to B'$, Part C). Without a spread topology there is no epidemic to defend against.

The worm spreads over a fixed **cyber trust graph** of 55 nodes (the paper's Fig. 5). The 83 undirected
edges are hardcoded **1-indexed exactly as in the paper** (`get_edges()` is the only 1-indexed function;
everything else is 0-indexed). `build_B()` produces the symmetric binary adjacency matrix

$$ B \in \{0,1\}^{55\times55},\qquad B = B^{\mathsf T},\qquad \operatorname{diag}(B)=0, $$

and asserts symmetry, zero diagonal, and `B.sum() == 2·83` (catching any duplicate or dropped edge).
Mean degree is ~3.0, max degree 5.

> The exact 55-node figure is read off the paper's diagram and is therefore *approximate*; this is
> documented at the source. The worm timeline is robust to small edge perturbations.

### B.2 The measurement→sensor map A → `build_A()`, `sensor_nodes()`

> **Why it exists — this is the bridge.** $A$ is the coupling between the cyber attack surface and the
> physical observability. Compromising cyber node $i$ gives the attacker control of *exactly the
> measurements node $i$ collects* — no more, no less. In one line: $A_{m,i}=1$ means "an attacker who owns
> node $i$ can tamper with measurement $m$." This single matrix is what lets a worm on the trust graph
> reach into the power-flow measurements; it is the hinge the whole attack turns on.

Not every cyber node collects a physical measurement. A subset of **30 "sensor" nodes** (node ids 0–29)
own the 41 branch measurements. `A \in \{0,1\}^{M\times55}` encodes this, with `A[m, i] = 1` meaning
measurement $m$ is collected by node $i$. Because $M=41 > 30$, measurements are assigned **round-robin**
over the 30 sensor nodes (`m % 30`), so each sensor owns 1–2 measurements. The invariant is **exactly one
nonzero per row** (each measurement has a single collecting node); columns may have several.

> The paper does not publish the exact branch→sensor incidence, so this round-robin assignment is a
> documented approximation. Its fan-out (how many measurements each compromised node unlocks) is a
> structural lever, held fixed here.

### B.3 The mean-field SIS worm (Eq. 4) → `update_worm()`

Infection is tracked as a vector of **probabilities** $\rho \in [0,1]^{55}$, not binary states. One step of
the deterministic mean-field SIS recursion is, per node $i$,

$$ \rho_i^{+} \;=\; \operatorname{clip}\!\Big(\rho_i + (1-\rho_i)\,\beta\!\sum_j B'_{ij}\rho_j \;-\; \gamma\,\rho_i,\ 0,\ 1\Big), $$

with infection rate $\beta = 0.1$, recovery rate $\gamma = 0.2$, and uniform initial infection
$\rho_0 = 0.05$. In code the coupling term is simply `B' @ rho`. The graph here is $B'$ — the (possibly
defended) graph; with no defense $B' = B$.

**Steady state.** With these rates the mean-field infection saturates at $\bar\rho \approx 0.32$ and is
**endemic**: the basic reproduction number $R_0 = \beta\,\lambda_{\max}(B)/\gamma = 0.1\times3.667/0.2 =
1.83 > 1$ (here $\lambda_{\max}(B)=3.667$), so the worm sustains itself but, with $R_0$ only modestly above
1, it settles at a steady state and **never crosses 0.5**. This single fact drives a major modeling
decision (B.4) and is documented in [05_divergences.md](05_divergences.md).

### B.4 From probabilities to a compromised set — Bernoulli + latching → `sample_compromise()`

> **Why it exists.** The worm (B.3) gives a *probability* $\rho_i(t)$ that node $i$ is infected at time
> $t$ — a fluctuating, never-certain quantity. But an attacker either controls a node or does not, and
> **malware does not politely leave once it arrives**. This function converts the probability into the
> thing the attack actually needs: a *binary, permanent* compromise state. "Bernoulli" draws the
> infection event from $\rho_i$; "latching" makes it stick (the state can only go $0\to1$, never back).
> The result is a compromised set that only grows — modeling malware persistence — which is what lets the
> attacker's reach accumulate over the horizon. (It also resolves a modeling problem with the literal
> threshold rule; see [05_divergences.md](05_divergences.md).)

Because $\bar\rho$ caps at ~0.34, a hard "node is compromised iff $\rho_i > 0.5$" rule would almost never
fire and no attack could ever realize. Instead the model samples a binary infection each step and **latches
it** (malware persists once it reaches a node):

$$ v_i \sim \text{Bernoulli}(\rho_i), \qquad \text{compromised}^{+} = \max(\text{compromised},\ v). $$

The compromised set therefore grows monotonically toward full coverage over the 40 steps, which is what
produces the rising $pa$ curve. The worm recursion (B.3) stays exactly as the paper specifies; the
stochastic latching lives only in this masking step.

### B.5 The measurement mask → `measurement_mask()`

A measurement is manipulable iff its (unique) collecting node is compromised:

$$ \text{mask} \;=\; \mathbb{1}\big[A\,v > 0\big] \in \{0,1\}^{M}. $$

> **Direction note ($Av$ vs $A^{\mathsf T}v$).** The paper writes $A^{\mathsf T}v$, but with $A$ of shape
> $(M,55)$ and $v$ of shape $(55,)$, $A v \to (M,)$ correctly lands in *measurement* space and yields, per
> measurement, the compromise state of its unique collecting node. $A^{\mathsf T}v$ would land in node
> space $\mathbb{R}^{55}$ (wrong direction and shape). The code uses $A v$ and documents this.

### B.6 FDI feasibility — the subspace projector → `_feasible_projector()`

A false-data-injection attack on the measurements is **undetectable** by a residual-based bad-data
detector iff it lies in the column space of $H$, i.e. $a = H c$ for some state perturbation $c$ (it then
looks like a consistent change of state). When the attacker can only alter the **compromised** measurements
$S$, the realizable undetectable attacks are those $a = Hc$ whose entries on the **uncompromised** rows
$\bar S$ vanish — equivalently, $c$ lies in the null space of the restricted matrix $H_{\bar S}$:

$$ H_{\bar S}\, c = 0. $$

`_feasible_projector` computes the orthogonal projector $P$ onto $\operatorname{null}(H_{\bar S})$ from the
SVD of $H_{\bar S}$ (the right-singular vectors past the numerical rank form the null basis $V_0$, and
$P = V_0 V_0^{\mathsf T}$). Two edge cases: if **everything** is compromised, $P = I$ (any $a=Hc$ is
realizable); if no feasible direction exists, $P = 0$. As the compromised set grows, the feasible subspace
grows **monotonically**.

### B.7 The bypass probability pa (Eq. 7) → `compute_pa()`

The attacker draws a random **target** state perturbation $c \sim \mathcal U(-0.1, 0.1)^{29}$ (10 000 of
them, drawn once and reused — `generate_fdi_targets`). The realizable undetectable attack is the projection
of that target onto the feasible subspace, $a_{\text{feasible}} = H(Pc)$. The attack **counts as a
successful bypass** when the realizable part retains at least a fraction `STRENGTH_THR = 0.30` of the target
strength:

$$ pa \;=\; \Pr_{c}\!\left[\ \frac{\lVert H\,P\,c\rVert}{\lVert H\,c\rVert} \;\ge\; 0.30\ \right]. $$

Feasible attacks are undetectable by construction (zero residual), so what determines a *successful and
impactful* bypass is this **strength ratio**, not a residual-vs-threshold test. The resulting $pa$ rises
**smoothly and monotonically** from 0 (nothing compromised → $P=0$) to 1 (everything compromised → $P=I$).
Boundary behavior is unit-tested: `pa = 0` at no compromise, `pa = 1` at full compromise, monotone in
between.

The mean infection level reported alongside $pa$ is just $\bar\rho = \texttt{compute\_rho\_bar}(\rho) =
\rho.\text{mean}()$.

---

## Part C — Defense layer (the ZTA policy)

### C.1 Partial node hardening → `apply_policy()`

> **Why partial, not full.** A real plant cannot simply cut a node off — the devices still have to talk to
> one another for the system to function. So a zero-trust defense *tightens* trust rather than severing it:
> hardening a node makes it harder (not impossible) for the worm to cross. We model that as scaling the
> node's couplings by $(1-\delta)$ with $\delta<1$, leaving a residual $1-\delta$ of trust. The immediate
> consequence — and the reason this matters — is **diminishing returns**: the defender spends its budget on
> the most valuable nodes first, and each additional node buys less, which is exactly the shallow
> improvement the paper reports between budgets.

A zero-trust defense **reduces** (does not necessarily sever) the trust the worm exploits. Hardening node
$i$ multiplies its row and column in the trust graph by $(1-\delta)$ with $\delta = \texttt{HARDENING\_DELTA}
= 0.40$:

$$ B'_{i,:} \leftarrow (1-\delta)\,B_{i,:}, \qquad B'_{:,i} \leftarrow (1-\delta)\,B_{:,i}. $$

A hardened node still leaks $1-\delta = 0.6$ of its couplings, so the defense has **diminishing returns** —
which is exactly why it reproduces the paper's shallow $N_k{=}10 \to 15$ improvement. Full isolation
($\delta=1$) collapses $pa$ to ~0 and overshoots the paper (see [05](05_divergences.md)).

### C.2 Policy evaluation → `evaluate_policy()`

A policy's value is the **average $pa$ over the full 40-step horizon** under the defended graph $B'$:
re-initialize $\rho = 0.05$, advance the worm under $B'$, sample the latching compromise each step, compute
$pa(t)$, and average. The RNG is reseeded identically each call (`SEED+1`) so different policies are judged
on the same infection/attack realization. $pa$ is a property of the *dynamics under $B'$*, not a static
property of $B'$ — hence the re-simulation.

### C.3 Greedy policy search (heuristic, **not** DQL) → `greedy_search()`

> **The problem it solves.** The defender has a budget of $N_k$ nodes it may harden. Which $N_k$ of the 55
> nodes should it pick to drive the attacker's bypass probability $pa$ as low as possible? That is a
> combinatorial optimization (choosing a best subset). The paper answers it with deep Q-learning; Phase 0
> answers it with a transparent, reproducible **greedy heuristic** — repeatedly add the single node that
> helps most right now. The point of *this* function is the *node-selection* decision; `evaluate_policy`
> (C.2) is the scoring oracle it calls to compare candidates.

The paper selects the defense with deep Q-learning. Phase 0 deliberately substitutes a **deterministic
greedy forward-selection heuristic**: in each of $N_k$ rounds, harden the single not-yet-chosen node whose
addition most reduces the average $pa$, given those already chosen. Cost is $O(N_k \times 55)$ full
simulations. It is **labeled a heuristic and is not guaranteed globally optimal** — but it is transparent,
reproducible, and lands inside the paper's reported bands. DQL is reintroduced in
[06_roadmap_phase1.md](06_roadmap_phase1.md), with `evaluate_policy` becoming the RL environment.

---

## Symbol table

| Symbol | Code name | Shape | Meaning |
|---|---|---|---|
| $N$ | `N_STATES` | scalar = 29 | state dimension (bus angles minus slack) |
| $M$ | (rows of `H`) | scalar = 41 | branch-flow measurements (34 lines + 7 trafos) |
| $\theta$ | bus angles | $(29,)$ | non-slack voltage angles (the state) |
| $H$ | `H` | $(41, 29)$ | DC Jacobian / measurement matrix, $H_{k,i}=\pm 1/(x_k\tau_k)$ |
| $R$ | `R` | $(41, 41)$ | diagonal measurement-noise covariance |
| $W$ | (`R^{-1}`) | $(41, 41)$ | WLS weight matrix $=R^{-1}$ |
| $K$ | `K` | $(29, 41)$ | WLS estimator gain, $KH=I$ |
| $z,\ z_{\text{clean}}$ | `z`, `z_clean` | $(41,)$ | noisy / clean per-unit branch flows |
| $B$ | `B` | $(55, 55)$ | worm infection graph (symmetric, binary) |
| $B'$ | `B_prime` | $(55, 55)$ | defended infection graph |
| $A$ | `A` | $(41, 55)$ | measurement→sensor incidence (one nonzero per row) |
| $\rho$ | `rho` | $(55,)$ | mean-field infection probabilities |
| $v$ / compromised | `compromised` | $(55,)$ | latched binary compromise state |
| mask | `mask` | $(41,)$ | per-measurement compromise indicator |
| $c$ | row of `C_targets` | $(29,)$ | random FDI target state perturbation |
| $P$ | `P` | $(29, 29)$ | projector onto feasible-$c$ subspace $=\operatorname{null}(H_{\bar S})$ |
| $pa$ | `pa` | scalar | FDI bad-data-detector bypass probability |
| $\bar\rho$ | `rho_bar` | scalar | mean infection level $=\rho.\text{mean}()$ |
| $\beta,\gamma,\rho_0$ | `BETA`,`GAMMA`,`RHO0` | scalars | 0.1, 0.2, 0.05 (worm rates / init) |
| $\delta$ | `HARDENING_DELTA` | scalar = 0.40 | trust-reduction per hardened node |
| $N_k$ | `NK_LIST` | {10, 15} | defense budget (nodes hardened) |

Continue to [03_code_architecture.md](03_code_architecture.md) for the module/API view, or
[04_results_and_validation.md](04_results_and_validation.md) for the measured results.
