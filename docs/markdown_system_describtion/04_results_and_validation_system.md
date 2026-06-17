# 04 — Results & Validation

This is the experimental-results chapter. Phase 0's deliverable is a **trusted baseline**: a faithful
reproduction whose numbers fall inside the bands the paper's reported values define. Validation is layered —
six runtime gates in `run_phase0.py` and 17 unit tests in `pytest` — so that a structural error fails
*loudly* (an assertion or an out-of-band gate) rather than silently shifting a result.

All numbers below were produced by `python run_phase0.py` and reproduced independently by
`python docs/make_figures.py`; the figures' printed series match the runner exactly (the
`pa_vs_step` average equals the Gate A value, and the Gate B sweep selects the same nodes).

---

## 1. Headline results

| Quantity | Achieved | Paper target | Accept band | Status |
|---|---|---|---|---|
| Clean unobservability residual | $7.89\times10^{-12}$ | $\approx 0$ | $< 10^{-6}$ | ✅ |
| **Gate A** — no-ZTA avg $pa$ (40 steps) | **0.7408** | 0.7474 | $[0.70, 0.80]$ | ✅ |
| **Gate B** — greedy $pa$, $N_k{=}10$ | **0.5606** | 0.5291 | $[0.50, 0.58]$ | ✅ |
| **Gate B** — greedy $pa$, $N_k{=}15$ | **0.5483** | 0.5094 | $[0.49, 0.57]$ | ✅ |
| Monotonicity $pa(15)\le pa(10)$ | $0.5483 \le 0.5606$ | — | required | ✅ |
| Unit tests | 17 / 17 pass | — | all pass | ✅ |

The reproduction sits slightly **above** the paper's defended values (0.5606 vs 0.5291; 0.5483 vs 0.5094) —
expected, because the defense is a transparent greedy heuristic rather than the paper's DQL optimum, so it
removes marginally less bypass capability. The *shape* (steep first gain, shallow tail) matches.

---

## 1a. What the numbers mean (physical interpretation)

The table above is the *what*; this section is the *so what*. Each result translated into one plain
statement of its real-world / attacker–defender meaning:

- **Clean residual $= 7.89\times10^{-12}$ → "the physics is wired up correctly."** This is a consistency
  certificate, not a tuning result. It says the real per-unit branch flows lie in the column space of $H$
  to machine precision — i.e. the measurement matrix $H$, the estimator $K$, the MW→p.u. unit conversion,
  and the branch ordering all agree. A large value here would mean a units/ordering bug, and *every*
  attack number downstream would be meaningless. Because it is ~$10^{-12}$, the attack results rest on a
  sound physical model. (Expanded in [§3 and §A.6 of the model chapter](02_cyber_physical_model.md).)

- **Gate A $pa = 0.7408$ → "undefended, the attacker wins about 3 times in 4."** With no zero-trust
  defense, roughly **74 % of crafted false-data-injection attempts slip past the bad-data detector** and
  silently corrupt the control center's estimate of the grid state. An operator acting on that corrupted
  estimate could be steered toward wrong control decisions without any alarm firing. This is the *baseline
  risk* the defense must reduce. It is a 40-step **average**: the per-step value (the S-curve, §3.1) climbs
  from 0 to 1 as the worm spreads, and 0.74 is the area under that climb.

- **Gate B $pa = 0.5606$ at $N_k{=}10$ → "hardening 10 nodes turns a ~74 % attack success rate into
  ~56 %."** Spending the zero-trust budget on the 10 most valuable nodes removes roughly **18 percentage
  points** of the attacker's success rate. That is a meaningful but partial defense — the system is safer,
  not safe.

- **Gate B $pa = 0.5483$ at $N_k{=}15$ → "the next 5 nodes buy almost nothing (~1 point)."** Going from 10
  to 15 hardened nodes lowers $pa$ by only ~1.2 points. The defense has **diminishing returns**: the first
  nodes hardened are the high-leverage ones, and once they are protected, additional budget is nearly
  wasted. This is *why* the paper's own curve is shallow between budgets — a property of the network, not
  an artifact of our heuristic. *(The reason the early nodes are high-leverage — their connectivity in $B$
  and how many measurements they collect through $A$ — is quantified in the [topology note](#1b-why-the-first-hardened-nodes-matter-most) below.)*

- **$\bar\rho$ saturates at $\approx 0.318$ → "the worm reaches an endemic equilibrium; about a third of
  the network stays infected forever."** Infection does not die out and does not take over: it settles at a
  steady state where new infections and recoveries balance. In epidemic terms the spread rate slightly
  exceeds the recovery rate ($R_0 = \beta\,\lambda_{\max}(B)/\gamma > 1$), so the worm is **endemic** —
  self-sustaining without ever reaching everyone. Crucially this equilibrium sits **below the 0.5 mark**,
  which is the empirical reason a hard "$\rho>0.5 \Rightarrow$ compromised" rule would never fire and the
  model instead uses Bernoulli sampling with latching (see [05 Divergence 2](05_divergences.md)).

- **Greedy vs. DQL gap (~3 points at each budget) → "our transparent heuristic finds a slightly weaker
  defense than the paper's learned one."** Our greedy defense lands a few points *above* the paper's DQL
  values (0.5606 vs 0.5291; 0.5483 vs 0.5094). A weaker optimizer removing marginally less bypass capability
  is exactly the expected direction — the reproduction is faithful in *shape* and close in *magnitude*, and
  closing this gap is precisely what reintroducing DQL in Phase 1 is for.

### 1b. Why the first hardened nodes matter most

The diminishing-returns curve (§3.3) is partly structural to the greedy heuristic — greedy is *defined* to
take the single most-helpful node each round, so by construction the largest $pa$ reductions come first and
the marginal gain can only shrink. But the *interesting* question is **which** nodes it picks, and the
answer is not the obvious one. Computing the relevant graph statistics for the selected nodes:

| rank | node | degree in $B$ | measurements collected (via $A$) | is a sensor (id < 30)? |
|---|---|---|---|---|
| 1 | 13 | 4 | 1 | yes |
| 2 | 23 | 4 | 1 | yes |
| 3 | 7 | 3 | 2 | yes |
| 4 | 15 | 4 | 1 | yes |
| 5 | 12 | 2 | 1 | yes |
| 6 | 8 | 2 | 2 | yes |
| 7 | 3 | 3 | 2 | yes |
| 8 | 6 | 3 | 2 | yes |
| 9 | 4 | 2 | 2 | yes |
| 10 | 10 | 3 | 2 | yes |
| 11 | 18 | **5** (max in $B$) | 1 | yes |
| 12 | 14 | 3 | 1 | yes |
| 13 | 16 | 4 | 1 | yes |
| 14 | 51 | 3 | 0 | **no** |
| 15 | 26 | 3 | 1 | yes |

*(Graph context: mean degree in $B$ is 3.0, max is 5; all 41 measurements are spread over the 30 sensor
nodes.)*

Two things stand out, and **neither matches the naive "harden the biggest hubs first" intuition**:

1. **It is not about raw degree.** The highest-degree node in the whole graph (node 18, degree 5) is picked
   *eleventh*, not first. The first ten picks have ordinary degrees (2–4). So the greedy defender is **not**
   simply going after network hubs.
2. **It is about gating measurements.** Every one of the first ten hardened nodes **is a sensor** — a node
   that actually collects physical measurements. The first non-sensor node (51, which collects zero
   measurements) is not touched until rank 14. This is the real signal: because $pa$ depends only on which
   *measurements* become tamperable, hardening a node helps only insofar as it keeps the worm away from
   **measurement-collecting** nodes. A high-degree node that collects nothing (like 51) barely moves $pa$,
   so greedy ignores it until late.

In short, the leverage that drives the steep early drop in §3.3 comes from protecting the **sensor layer**
(the bridge $A$), not from cutting the most-connected nodes. This is a concrete, falsifiable illustration of
why the cyber-physical bridge — not the worm topology alone — is what the defense must reason about, and it
is the kind of insight a learned DQL policy in Phase 1 should also discover (and ideally exploit better).

---

## 2. The six validation gates (`runner.run_phase0`)

The runner prints `[PASS]`/`[FAIL]` for each and returns success only if all pass. In order:

### Gate 1 — Network sanity
Asserts total load $= 283.4$ MW (±0.5) and slack voltage $= 1.06$ p.u. (±$10^{-6}$). Guards against loading
the wrong IEEE 30-bus variant (`case30` vs `case_ieee30`), which would silently shift every flow.

### Gate 2 — H matrix structure
Asserts shape $(41, 29)$, full column **rank 29**, and **reactance weighting** — explicitly that the nonzero
entries are *not* all $\pm 1$ and that $\max|H| > 1.5$. This catches the classic "built an incidence matrix
instead of the DC Jacobian" bug. (Observed $\max|H| = 42.4$, a small-reactance transformer branch.)

### Gate 3 — Clean residual (unobservability self-check)
Asserts $\lVert z_{\text{clean}} - H K z_{\text{clean}}\rVert < 10^{-6}$. This is the **load-bearing**
check: it certifies that real per-unit measurements lie in $\operatorname{col}(H)$, i.e. $H$, $K$, the units
(MW → p.u.), and the branch ordering are all mutually consistent. Achieved $7.89\times10^{-12}$.

### Gate 4 — Gate A (no-ZTA bypass probability)
Runs the undefended 40-step worm/attack loop with the **full 10 000** FDI targets and averages $pa(t)$. Must
land in $[0.70, 0.80]$; achieved **0.7408** (target 0.7474). Governed by the calibration knob
`STRENGTH_THR = 0.30`.

### Gates 5 & 6 — Gate B (greedy defense at $N_k=10, 15$)
Runs `greedy_search` at each budget (partial hardening $\delta=0.40$, the **2 000**-target policy slice
`N_FDI_POLICY` for tractable speed) and checks the resulting average $pa$ against its band, plus
monotonicity $pa(15)\le pa(10)$. Achieved 0.5606 and 0.5483.

> **Why two FDI sample sizes?** Gate A reports the headline no-ZTA number on the full 10 000 targets for
> precision. Gate B runs hundreds of full re-simulations inside the greedy loop, so it uses a 2 000-target
> slice for speed; the selected node sets were verified to stay in-band when re-scored on the full 10 000
> (Nk=10 → 0.5640, Nk=15 → 0.5504). The reported gate values use the 2 000 slice consistently.

---

## 3. Figures

### 3.1 Gate A bypass probability over time

![Gate A: pa(t) over the 40-step horizon](figures/pa_vs_step.png)

$pa(t)$ traces the attacker's growing reach as the worm spreads. It is **exactly 0** for the first steps
(no node has yet latched a compromise, so the feasible subspace is empty, $P=0$), rises steeply as
measurement-collecting sensor nodes fall (steps ~5–14), and **saturates at 1.0** once enough sensors are
compromised that any target attack has a feasible undetectable realization. The **40-step average is
0.7408**, inside the Gate A band — the paper's 0.7474 is an *average over the horizon*, not a steady-state
value, which is why an S-curve that ends at 1.0 still averages ~0.74. The step-0 value of 0 is also a free
sanity check: with $\rho_0=0.05$ and nothing yet latched, no attack is realizable regardless of the
threshold.

### 3.2 Mean infection level (why Bernoulli + latching)

![Mean-field infection rho_bar(t) saturating below 0.5](figures/rho_bar_vs_step.png)

The deterministic mean-field worm $\bar\rho(t)$ rises from $\rho_0 = 0.05$ and **saturates around 0.32**,
comfortably **below the 0.5 line** (dashed). This is the empirical evidence for divergence #2: a hard
"compromised iff $\rho_i > 0.5$" rule would essentially never fire, so the model instead samples
$v_i\sim\text{Bernoulli}(\rho_i)$ each step and latches it. The *accumulated* compromised set still climbs
to full coverage (driving §3.1's $pa\to 1$) even though the *instantaneous* infection probability never
reaches one half. See [05_divergences.md](05_divergences.md).

### 3.3 Gate B — defense effectiveness vs. budget

![Gate B: greedy pa vs Nk](figures/gateB_nk_sweep.png)

Average $pa$ as the greedy defender is allowed to harden more nodes. The undefended baseline (here 0.7395 on
the policy slice) drops **steeply** with the first five hardened nodes (→ 0.5811), then **flattens** through
$N_k{=}10$ (0.5606) and $N_k{=}15$ (0.5483). This **diminishing-returns** shape is the signature of *partial*
hardening ($\delta<1$): the most valuable nodes are taken first, and later nodes add little. The paper's DQL
points (red diamonds, 0.5291 and 0.5094) sit just below this work's greedy curve, both inside the green Gate
B bands — the reproduction is faithful in shape and close in magnitude. The greedy node order is identical to
the runner's: `[13, 23, 7, 15, 12, 8, 3, 6, 4, 10, 18, 14, 16, 51, 26]`.

---

## 4. Unit-test invariants (17 tests)

`pytest` checks the structural invariants the gates rely on. Grouped by module:

### `test_power_system.py` (6)
| Test | Invariant |
|---|---|
| `test_network_load_and_slack` | load $=283.4$ MW, slack $=1.06$ p.u. |
| `test_H_shape` | $H$ is $(41, 29)$ |
| `test_H_full_rank` | $\operatorname{rank}(H)=29$ |
| `test_H_reactance_weighted` | entries are $1/x$ weights, not $\pm 1$; $\max|H|>1.5$ |
| `test_clean_residual_is_small` | $\lVert z_{\text{clean}}-HKz_{\text{clean}}\rVert < 10^{-6}$ |
| `test_estimator_inverts_H` | $KH = I_{29}$ to $10^{-9}$ |

### `test_topology.py` (5)
| Test | Invariant |
|---|---|
| `test_B_shape_and_symmetry` | $B$ is $(55,55)$, symmetric, zero diagonal |
| `test_B_edge_count` | $B.\text{sum}()=2\cdot 83$ (no dup/dropped edge) |
| `test_B_is_binary` | $B\in\{0,1\}$ |
| `test_A_shape_and_rows` | $A$ is $(41,55)$, exactly one nonzero per row |
| `test_A_row_count_matches_M` | $A$'s row count equals $M$ for $M\in\{10,41,50\}$ |

### `test_attack.py` (6)
| Test | Invariant |
|---|---|
| `test_rho_stays_in_unit_interval` | $\rho_i\in[0,1]$ across all 40 steps |
| `test_rho_rises_then_saturates` | $\bar\rho$ rises from $\rho_0$ toward an endemic level |
| `test_pa_in_unit_interval` | $pa\in[0,1]$ at every step |
| `test_pa_zero_when_no_compromise` | $pa=0$ when nothing is compromised |
| `test_pa_one_when_fully_compromised` | $pa=1$ when everything is compromised |
| `test_pa_rises_with_compromise` | $pa$ monotone in compromise fraction; endpoints 0 and 1 |

The two boundary tests (`pa_zero…`, `pa_one…`) and the monotonicity test pin the qualitative shape of the
$pa$ curve independent of any calibration knob — so a knob can be retuned without silently breaking the
model's logic.

---

## 5. Calibration — the three knobs and why they hold these values

All three live in `config.py` and were tuned in a documented order (never touch $H$, it is physics):

| Knob | Value | Calibrates | Rationale |
|---|---|---|---|
| `STRENGTH_THR` | **0.30** | Gate A | The fraction of target strength a feasible attack must retain to count as a bypass. Lower → more attacks count → higher $pa$. 0.30 lands the 40-step average at 0.7408 (target 0.7474). |
| `HARDENING_DELTA` | **0.40** | Gate B | Trust reduction per hardened node. $\delta=1$ (full isolation) collapses $pa\to0$ and overshoots; $\delta$ too small barely moves $pa$. 0.40 gives the shallow, in-band $N_k{=}10\to15$ curve. |
| `N_FDI_POLICY` | **2000** | Gate B speed | FDI sample count inside the greedy loop (Gate A keeps the full 10 000). Large enough that the in-band verdict is stable, small enough that greedy finishes in ~5–10 min per budget. |

The full numerical recipe and the reasons each *literal* paper mechanism was replaced are in
[05_divergences.md](05_divergences.md). The exact commands and expected timings are in
[07_environment_repro.md](07_environment_repro.md).
