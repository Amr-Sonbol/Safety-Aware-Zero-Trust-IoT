# 05 — Documented Divergences from the Paper Spec

A faithful reproduction is not a literal transcription. The paper (Feng & Hu, 2023) describes the attack/
defense model at a level that, taken *verbatim*, either contradicts its own reported results or under-
specifies a mechanism. Phase 0 makes **four** deliberate, documented modeling choices that depart from the
literal recipe in order to reproduce the paper's *reported behaviour*. This chapter records each one
honestly: the paper's recipe, why it fails as written, the chosen reconciliation, and the evidence that the
choice is faithful. Each divergence is also narrated at the relevant source docstring (cited inline).

This is the integrity chapter — an examiner should be able to read it and see exactly where the
reproduction exercises modeling judgment, and why each judgment is defensible.

---

## Divergence 1 — Subspace-feasible FDI instead of literal residual masking

**Where:** `attack_engine.compute_pa`, `_feasible_projector` (module docstring documents this).

**Paper recipe (literal).** Pre-draw a single undetectable attack vector $a = Hc$. Mask it to the
compromised measurements, $a_{\text{eff}} = a \odot \text{mask}$, add it to $z$, and declare a bypass when
the bad-data-detector residual stays under a threshold: $\lVert (I-HK)(z + a_{\text{eff}})\rVert \le \tau$.

**Why it fails as written.** A full undetectable vector $a=Hc$ has *zero* residual. But **slicing** it to
only the compromised rows destroys its unobservability: the masked vector no longer lies in
$\operatorname{col}(H)$, so it produces a *large* residual and is loudly detected. The consequence is a
**non-monotonic, U-shaped** $pa$ versus compromise curve — an attack bypasses when *nothing* is compromised
(the vector is untouched and fully unobservable) or when *everything* is compromised (the full vector is
realizable), but is **detected in the middle**, exactly where the paper reports rising $pa$. No setting of
$\tau$ recovers a curve that rises smoothly from ~0 to ~0.7474.

**Chosen reconciliation.** Model feasibility *structurally* rather than by a residual test. An attack is
realizable-and-undetectable iff it is $a = Hc$ whose entries on the **uncompromised** rows $\bar S$ vanish,
i.e. $c \in \operatorname{null}(H_{\bar S})$. The orthogonal projector $P$ onto that null space is built from
the SVD of $H_{\bar S}$, and a random target $c$ counts as a bypass when its feasible projection retains
enough strength:

$$ pa \;=\; \Pr_c\!\left[\frac{\lVert H P c\rVert}{\lVert H c\rVert} \ge \texttt{STRENGTH\_THR}=0.30\right]. $$

**Evidence it is faithful.** The feasible subspace grows **monotonically** with the compromised set, so
$pa$ rises smoothly from 0 (nothing compromised, $P=0$) to 1 (all compromised, $P=I$) — the qualitative
behaviour the paper reports. The boundary and monotonicity are unit-tested (`test_pa_zero_when_no_compromise`,
`test_pa_one_when_fully_compromised`, `test_pa_rises_with_compromise`), and the 40-step average lands at
0.7408, inside the paper's $[0.70,0.80]$ band. See the $pa(t)$ S-curve in
[04_results_and_validation.md §3.1](04_results_and_validation.md).

---

## Divergence 2 — Stochastic Bernoulli + latching instead of a hard ρ > 0.5 threshold

**Where:** `attack_engine.sample_compromise` (module docstring documents this); rates set in `config.py`.

**Paper recipe (literal).** Treat a node as compromised once its mean-field infection probability crosses a
hard threshold, $\rho_i > 0.5$, and build the measurement mask from those nodes.

**Why it fails as written.** With the paper's own rates $\beta=0.1$, $\gamma=0.2$ on the Fig. 5 graph, the
mean-field SIS recursion is only **weakly endemic**: $\beta\,\lambda_{\max}(B) \approx 0.37$ versus
$\gamma=0.2$, so the infection **saturates at $\bar\rho \approx 0.32$–$0.34$ and never reaches 0.5**. A hard
$\rho>0.5$ rule would therefore mark *almost no* node compromised, the mask would stay near-empty, and $pa$
could never rise — directly contradicting the reported result. This saturation is shown empirically in
[04 §3.2](04_results_and_validation.md) (the $\bar\rho$ curve plateaus well under the 0.5 line).

**Chosen reconciliation.** Keep the worm recursion (Eq. 4) **exactly** as specified, but read the binary
compromise state stochastically and make it persistent: each step sample $v_i \sim \text{Bernoulli}(\rho_i)$
and **latch** it (malware does not leave once it arrives),

$$ \text{compromised}^{+} = \max(\text{compromised},\ v). $$

This is the Monte-Carlo infection-state variant the paper's framework allows; the spreading/recovery
*dynamics* are untouched. Even though instantaneous $\rho_i$ caps below 0.5, the **accumulated** compromised
set climbs toward full coverage over the 40 steps.

**Evidence it is faithful.** $\beta$, $\gamma$, $\rho_0$ remain exactly the paper's values — nothing in the
worm model was retuned. The accumulation produces the rising $pa(t)$ S-curve of [04 §3.1](04_results_and_validation.md),
and the curve's average matches the paper. The choice is the minimal change that respects the paper's rates.

---

## Divergence 3 — Partial node hardening (δ < 1) instead of full isolation

**Where:** `policy_engine.apply_policy` (module docstring documents this); $\delta$ in `config.py`.

**Paper recipe (literal).** The ZTA defense "removes trust relationships," naturally read as **isolating** a
defended node — zeroing its row and column in the trust graph $B$.

**Why it fails as written.** Full isolation is far too strong for this graph. Zeroing a node's couplings
removes it entirely from the worm dynamics; with a budget of 10–15 nodes the greedy defender drives $pa$ to
**~0.0006** — three orders of magnitude below the paper's defended values (0.5291, 0.5094). It also produces
the *wrong shape*: a cliff rather than the paper's **shallow** improvement from $N_k{=}10$ (52.91 %) to
$N_k{=}15$ (50.94 %), a change of only ~2 points. (An intermediate experiment with *edge* removal gave
$N_k{=}10\to0.56$ ✓ but $N_k{=}15\to0.25$ ✗ — still too aggressive at the larger budget.)

**Chosen reconciliation.** Harden, don't isolate: multiply the node's row and column by $(1-\delta)$ with
$\delta = \texttt{HARDENING\_DELTA} = 0.40$, so a defended node still leaks $0.6$ of its trust couplings:

$$ B'_{i,:}\leftarrow(1-\delta)B_{i,:},\qquad B'_{:,i}\leftarrow(1-\delta)B_{:,i}. $$

Partial hardening gives the defense **diminishing returns** — the first few nodes help a lot, later ones
little.

**Evidence it is faithful.** The achieved curve is shallow and in-band: $N_k{=}10\to0.5606$ (band
$[0.50,0.58]$), $N_k{=}15\to0.5483$ (band $[0.49,0.57]$), monotone, with the paper's DQL points sitting just
below — see the sweep in [04 §3.3](04_results_and_validation.md). $\delta=0.40$ was found by a documented
calibration sweep (sweeping $\delta$ and re-scoring the greedy selection on the full 10 000 targets).

---

## Divergence 4 — Greedy forward-selection heuristic instead of deep Q-learning

**Where:** `policy_engine.greedy_search` (module docstring labels it a heuristic).

**Paper recipe (literal).** Select the defense policy with **deep Q-learning (DQL)** — a learned policy that
minimizes the attacker's bypass probability.

**Why it is deferred, not failed.** DQL is a *Phase 1+* deliverable: it needs an environment, a reward, a
state encoding, a replay buffer, and training/seed management — none of which belongs in a Phase 0 whose sole
job is to validate the *attack model* against published numbers. Reproducing the defended $pa$ does not
require the optimizer to be DQL; it requires *a* policy optimizer that lands in the bands.

**Chosen reconciliation.** A **deterministic greedy forward-selection** heuristic: at each of $N_k$ rounds,
harden the single not-yet-chosen node that most reduces the average $pa$. It is transparent, fully
reproducible (no training stochasticity), and runs in $O(N_k\times55)$ simulations. It is **explicitly
labeled non-optimal** in the docstring — greedy can plateau and is not guaranteed to find the globally best
node set.

**Evidence it is acceptable.** The greedy selections land inside both Gate B bands and are monotone in $N_k$.
That this work's greedy curve sits slightly *above* the paper's DQL curve is exactly what one expects from a
weaker (heuristic) optimizer removing marginally less bypass capability — consistent, not contradictory.
DQL is reintroduced as the first Phase 1 task, with `evaluate_policy` becoming the RL environment's reward;
see [06_roadmap_phase1.md](06_roadmap_phase1.md).

---

## Summary

| # | Paper recipe | Failure mode | Phase 0 choice | Result |
|---|---|---|---|---|
| 1 | residual test on masked $a=Hc$ | non-monotonic, U-shaped $pa$ | subspace-feasibility + strength ratio | smooth $pa$ 0→1, avg 0.7408 |
| 2 | hard $\rho>0.5$ threshold | $\bar\rho$ saturates ~0.34, never fires | Bernoulli sample + latch | rising compromise, rates unchanged |
| 3 | full node isolation | $pa\to0.0006$, cliff not shallow | partial hardening $\delta=0.40$ | shallow in-band $N_k$ curve |
| 4 | deep Q-learning | out of Phase 0 scope | greedy heuristic (labeled) | in-band, monotone; DQL → Phase 1 |

None of these touches the **physics**: $H$, $K$, $R$, and the DC power flow are reproduced exactly, and the
unobservability self-check ($7.89\times10^{-12}$) certifies it. The divergences are confined to the
*attack-realization semantics*, the *compromise-state readout*, and the *defense/optimizer* — the parts the
paper under-specifies — and each is the minimal change that reproduces the reported behaviour.
