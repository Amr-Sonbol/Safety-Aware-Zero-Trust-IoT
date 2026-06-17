# 06 — Roadmap: Where the Safety-Aware Phases Attach

Phase 0 delivered a **trusted, frozen baseline**: a validated attack/defense model whose bypass probability
$pa$ and infection level $\bar\rho$ match the paper. The remaining phases turn that baseline into the
project's real subject — a **safety-aware** zero-trust controller. This chapter maps each future element to a
concrete seam in the existing code, so the next phases plug in rather than rewrite.

A guiding principle: **keep Phase 0's six-gate runner as a regression harness.** Every later phase must leave
Gate A, Gate B, and the 17 unit tests passing, so the baseline never silently drifts as new machinery lands.

---

## 1. The deferred elements (from the paper, beyond Phase 0)

| Element | What it is | Phase 0 placeholder |
|---|---|---|
| **Deep Q-learning (DQL)** | learned policy that minimizes $pa$ | greedy heuristic `greedy_search` |
| **Five-action decision function** | per-node action ∈ {full, restricted, read-only, safe-mode, deny} | single scalar hardening $\delta$ |
| **Soft actions** | graded trust reduction, not on/off | the $(1-\delta)$ multiplier hints at this |
| **Safety cost $S_c$** | physical-impact penalty of an action/attack | *not computed* — no physical-impact model yet |
| **Metrics M1 / M2 / M3** | operational performance metrics | only $pa$ and $\bar\rho$ exist |
| **Safety-aware objective** | trade security vs. safety, $J = pa + \lambda S_c$ | objective is $pa$ alone |

---

## 2. Seam-by-seam attachment plan

### 2.1 DQL replaces the greedy optimizer — `evaluate_policy` becomes the RL environment
The cleanest seam already exists. `policy_engine.evaluate_policy(B', …)` is, in RL terms, a full episode that
returns a scalar value. To stand up DQL:

- **Environment `step`.** Wrap the per-step body of `evaluate_policy` (one `update_worm` → `sample_compromise`
  → `compute_pa`) as `env.step(action)`. The action hardens a node (or applies one of the five actions, §2.2).
- **State.** The natural state is `(rho, compromised, current B')` — or a compressed feature vector (e.g.
  $\bar\rho$, fraction of sensors compromised, current $pa$, remaining budget).
- **Reward.** Start with $r = -pa$ (minimize bypass); generalize to the safety-aware reward in §2.4.
- **Drop-in.** `greedy_search(B, Nk, …)` is replaced by `dql_policy(B, Nk, …)` with the *same signature*
  `-> (selected, avg_pa)`, so `runner` and the Gate B checks are unchanged. The greedy stays as a baseline
  the DQL must beat (DQL should push $pa$ from ~0.56 toward the paper's ~0.53).

> New module: `src/rl_policy.py` (or `dql.py`). New config: network sizes, learning rate, replay buffer,
> episode/seed management. Keep all RNG routed through a documented seed for reproducibility, as in Phase 0.

### 2.2 Five-action decision function generalizes `apply_policy`
Today `apply_policy(B, selected, delta)` applies one action (scalar hardening) to a node. Generalize it to an
**action space**: `apply_action(B, node, action)` where `action ∈ {full, restricted, read_only, safe_mode,
deny}` maps to a different transformation of that node's row/column (and, later, of its sensor's measurement
availability in `A`). The current $(1-\delta)$ multiplier is already a "soft action," so soft/graded actions
are a natural superset — expose a per-action $\delta$ table in `config.py`.

> New config: an action→effect table. `apply_policy` stays for backward-compat (it is the "restricted/soft"
> action with $\delta=0.40$), so Gate B keeps reproducing.

### 2.3 Safety cost $S_c$ needs a new physical-impact model
This is the **largest gap** and the project's namesake. Phase 0 computes whether an FDI attack is
*undetectable* ($pa$), but **not its physical consequence**. $S_c$ requires turning a successful, undetectable
attack into a physical-impact number, e.g.:

- the **state-estimation error** it induces, $\lVert \hat\theta_{\text{attacked}} - \theta_{\text{true}}\rVert$
  (computable now: $\hat\theta = K z_{\text{att}}$, and the feasible attack is already constructed in
  `compute_pa`); and/or
- whether the corrupted state drives a **line-flow or voltage-angle limit violation** (needs branch/voltage
  limits from the case and a post-attack DC re-solve).

This hooks directly into `power_system` (reuse $H$, $K$, `generate_z`, and the feasible-attack construction
from `attack_engine._feasible_projector`). A successful, *low-$S_c$* attack is tolerable; a *high-$S_c$* one
is what the safety-aware defense must prioritize blocking.

> New module: `src/safety.py` — `safety_cost(attack, H, K, net) -> Sc`. Reuses Phase 0 physics; adds limits.

### 2.4 Metrics M1/M2/M3 and the safety-aware objective
With $S_c$ available, define the project's real objective as a trade-off

$$ J \;=\; pa \;+\; \lambda\,S_c, $$

and replace the DQL reward $-pa$ with $-J$. The operational metrics M1/M2/M3 (e.g. detection rate, residual
safety risk, defense cost) live in a new `src/metrics.py` and are reported per-episode. The Gate B runner
gains **new Phase-1 gates** for these metrics, alongside (not replacing) the Phase-0 gates.

> New modules: `src/safety.py`, `src/metrics.py`. New config: $\lambda$, limit thresholds, metric bands.

---

## 3. Suggested module additions

```
src/
├── safety.py     # safety_cost(): physical impact of an (undetectable) attack — reuses H, K, net
├── metrics.py    # M1/M2/M3 + the J = pa + λ·Sc objective
└── rl_policy.py  # DQL agent + env wrapper around evaluate_policy; same (selected, avg_pa) signature
```

Plus config additions (action→effect table, $\lambda$, limits, RL hyperparameters) — all in the existing
single-source-of-truth `config.py`.

## 4. Packaging upgrade (recommended for Phase 1)

Phase 0 imports via a `sys.path` shim and the package has no `pyproject.toml`. Before adding modules, it is
worth introducing a minimal `pyproject.toml`:

```toml
[project]
name = "zt_cps"
version = "0.1.0"

[tool.pytest.ini_options]
pythonpath = ["."]
```

Then `pip install -e .` and drop the `sys.path.insert` shims in `run_phase0.py` and `docs/make_figures.py`.
This was **deliberately not done in Phase 0** to avoid disturbing the validated import path the gates depend
on — but it is low-risk to do as the first Phase-1 commit, *with the test suite as the guardrail*. Also
recommended: initialize a git repository at this point so the Phase 0 baseline is a tagged commit.

## 5. Phase-1 acceptance principle

A Phase-1 change is acceptable only if, after it lands:

1. `pytest` still reports **17 passed** (Phase-0 invariants intact);
2. `python run_phase0.py` still **passes all six gates** (baseline not drifted); and
3. the new DQL defense achieves $pa$ **at or below** the greedy baseline (0.5606 @ $N_k{=}10$), ideally
   approaching the paper's DQL values (0.5291 / 0.5094).

That keeps every future result anchored to the trusted Phase 0 baseline documented here.
