# 03 — Code Architecture & API Reference

This chapter is the developer's map: what each module is responsible for, the public functions and their
signatures, how the runner orchestrates them, where the calibration knobs live, and the runtime cost. For
the *mathematics* behind each function see [02_cyber_physical_model.md](02_cyber_physical_model.md); for the
*measured results* see [04_results_and_validation.md](04_results_and_validation.md).

---

## 1. Repository layout

```
CPS_Safety_Aware/
├── run_phase0.py               # entry point: sys.path shim + runner.run_phase0()
├── requirements.txt            # pinned deps
├── docs/                       # this documentation set + make_figures.py + figures/
└── zt_cps_phase0/
    ├── src/
    │   ├── __init__.py         # empty (marks package)
    │   ├── config.py           # ALL constants + the RNG seed (no logic)
    │   ├── power_system.py     # physical half: network, H, R, K, z, residual
    │   ├── topology.py         # cyber graph B and sensor map A
    │   ├── attack_engine.py    # worm, compromise, FDI feasibility, pa
    │   ├── policy_engine.py    # defense: apply / evaluate / greedy_search
    │   └── runner.py           # orchestrates the six PASS/FAIL gates
    └── tests/
        ├── __init__.py
        ├── test_power_system.py   # 6 tests
        ├── test_topology.py       # 5 tests
        └── test_attack.py         # 6 tests
```

There is no `zt_cps_phase0/__init__.py`; the package is resolved as a namespace directory once the project
root is on `sys.path`. Imports everywhere are `from zt_cps_phase0.src import <module>`.

## 2. Call graph

```
run_phase0.py
└── runner.run_phase0()
    ├── power_system.load_network()              ── pandapower case_ieee30 + rundcpp
    ├── power_system.build_H(net)                ── (H, branch_rows, state_index)
    ├── topology.build_B()                        ── 55×55 infection graph
    ├── topology.build_A(M)                       ── 41×55 sensor map
    ├── attack_engine.generate_fdi_targets(H,rng) ── C_targets (10000×29), drawn once
    ├── power_system.load_profile()               ── ±15% synthetic curve
    │
    ├── [Gate 3] power_system.generate_z / build_R / build_estimator / clean_residual_norm
    │
    ├── [Gate A] INNER LOOP  t = 0..39:                     ── full 10000 targets, ~3 s total
    │       update_worm(rho, B)                  rho (55,)      → rho (55,)
    │       sample_compromise(rho, compromised)  (55,),(55,)    → compromised (55,)
    │       compute_pa(C_targets, H, A, compromised)            → pa (scalar)
    │           ├ measurement_mask(A, v)         A(41,55)@v(55,)→ mask (41,)
    │           └ _feasible_projector(H, mask)   SVD            → P (29,29)
    │   avg over 40 steps → Gate A pa = 0.7408
    │
    └── [Gate B] OUTER LOOP  for Nk in {10,15}:             ── C_policy = first 2000 targets
            policy_engine.greedy_search(B, Nk, H, A, C_policy)
              └─ Nk rounds × (~55 candidate nodes):              ── O(Nk×55) full inner loops, ~5-10 min/Nk
                   apply_policy(B, trial, δ)       → B' (55,55)   (row/col × (1-δ))
                   evaluate_policy(B', …)          → avg pa       (runs a FULL 40-step inner loop)
                 keep the node that most lowers avg pa
```

**The nesting is the key cost.** Gate B's outer greedy loop calls `evaluate_policy` once per candidate
node, and **each `evaluate_policy` is itself a complete 40-step inner loop** (the same body as Gate A).
So one greedy budget runs on the order of $N_k\times55$ forty-step simulations — which is why Gate A
(one inner loop) finishes in seconds while each Gate B budget takes minutes. Hardening a candidate node is
the `B → B'` step; changing `B'` changes the worm dynamics, so the whole inner loop must be re-run to score
it. A single tick of the inner loop, with shapes, is traced in
[02 §B.0](02_cyber_physical_model.md#part-b0--one-step-and-two-loops-the-execution-flow).

`runner` is the only module that knows the orchestration; every other module is a pure, testable library.

## 3. Module reference

### `config.py` — single source of truth
No logic, only constants; every RNG routes through `SEED`. Grouped: worm rates
(`BETA=0.1`, `GAMMA=0.2`, `RHO0=0.05`, `N_NODES=55`), horizon (`N_STEPS=40`), FDI
(`N_FDI=10_000`, `C_LOW=-0.1`, `C_HIGH=0.1`, **`STRENGTH_THR=0.30`**), noise (`NOISE_REL=0.02`,
`SIGMA_FLOOR=1e-3`), BDD (`BDD_ALPHA=0.05`), defense (`NK_LIST=[10,15]`, **`HARDENING_DELTA=0.40`**,
**`N_FDI_POLICY=2000`**), reproducibility (`SEED=0`), gate bands (`GATE_A`, `GATE_B_NK10`, `GATE_B_NK15`,
plus paper targets), load profile (`LOAD_SWING=0.15`, `NYISO_CSV`), and power-system constants
(`SYSTEM_BASE_MVA=100`, `N_BUSES=30`, `N_STATES=29`, `RANK_TOL=1e-9`).

### `power_system.py` — physical half
| Function | Signature (abbrev.) | Returns / role |
|---|---|---|
| `load_network` | `() -> net` | DC-solved IEEE 30-bus; asserts load/slack |
| `build_H` | `(net) -> (H, branch_rows, state_index)` | DC Jacobian $(41,29)$; asserts rank & weighting |
| `compute_sigma` | `(z) -> sigma` | $\max(0.02|z|, 10^{-3})$ per measurement |
| `build_R` | `(z) -> R` | $\operatorname{diag}(\sigma^2)$ |
| `build_estimator` | `(H, R) -> K` | WLS gain $(HᵀWH)^{-1}HᵀW$, $KH=I$ |
| `load_profile` | `(n_steps) -> profile` | NYISO CSV if present, else ±15% cosine |
| `generate_z` | `(net, branch_rows, base_p, profile, t, rng, base_q) -> (z, z_clean)` | real per-unit flows + noise |
| `clean_residual_norm` | `(z_clean, H, K) -> float` | unobservability self-check (≈ $10^{-12}$) |

### `topology.py` — cyber graph & sensor map
| Function | Signature | Returns / role |
|---|---|---|
| `get_edges` | `() -> list[(int,int)]` | the 83 Fig-5 edges, **1-indexed** (only such function) |
| `build_B` | `() -> B` | symmetric binary $(55,55)$; asserts symmetry/diag/edge count |
| `sensor_nodes` | `() -> ndarray` | the 30 sensor node ids (`arange(30)`) |
| `build_A` | `(m) -> A` | $(m,55)$ round-robin map; asserts one nonzero per row |

### `attack_engine.py` — worm, compromise, FDI, pa
| Function | Signature | Returns / role |
|---|---|---|
| `update_worm` | `(rho, B_prime, beta, gamma) -> rho_new` | mean-field SIS step (Eq. 4) |
| `sample_compromise` | `(rho, compromised, rng) -> compromised_new` | Bernoulli draw + latch |
| `measurement_mask` | `(A, compromised) -> mask` | $\mathbb 1[Av>0]$ |
| `generate_fdi_targets` | `(H, rng, n_fdi) -> C_targets` | $(n,29)$ uniform targets, drawn once |
| `_feasible_projector` | `(H, mask) -> P` | $(29,29)$ projector onto $\operatorname{null}(H_{\bar S})$ (SVD) |
| `compute_pa` | `(C_targets, H, A, compromised, strength_thr) -> pa` | strength-ratio bypass probability (Eq. 7) |
| `compute_rho_bar` | `(rho) -> float` | $\rho.\text{mean}()$ |

### `policy_engine.py` — defense
| Function | Signature | Returns / role |
|---|---|---|
| `apply_policy` | `(B, selected, delta) -> B_prime` | row/col $\times(1-\delta)$ for each hardened node |
| `evaluate_policy` | `(B_prime, H, A, C_targets, n_steps, seed) -> avg_pa` | full 40-step re-sim, mean $pa$ |
| `greedy_search` | `(B, Nk, H, A, C_targets, delta) -> (selected, avg_pa)` | forward-selection heuristic, $O(N_k\times55)$ |

### `runner.py` — orchestration
`run_phase0() -> bool` builds the model once, runs the six gates (network, H, residual, Gate A, Gate B
Nk=10, Nk=15+monotone), prints `[PASS]/[FAIL]` per check and a summary, and returns `True` iff all pass.
`_pass_fail(label, ok, detail)` is the print helper. `run_phase0.py` calls it and exits 0/1.

## 4. The three calibration knobs (in `config.py`)

| Knob | Value | Used by | Effect |
|---|---|---|---|
| `STRENGTH_THR` | 0.30 | `compute_pa` | bypass strength-ratio cutoff → sets Gate A $pa$ |
| `HARDENING_DELTA` | 0.40 | `apply_policy` / `greedy_search` | trust reduction per hardened node → sets Gate B curve |
| `N_FDI_POLICY` | 2000 | `runner` (slices `C_targets` for greedy) | greedy speed vs. precision; Gate A uses full 10 000 |

See [05_divergences.md](05_divergences.md) for *why* each holds its value.

## 5. Reproducibility model

- `C_targets` drawn once with `default_rng(config.SEED)` (=0) and reused across all gates and figures.
- The worm/compromise simulation reseeds `default_rng(SEED + 1)` at the **start of each run** (Gate A and
  every `evaluate_policy` call) so policies are compared on the identical infection/attack realization.
- No other source of randomness exists; runs are bit-for-bit reproducible.

## 6. Runtime cost

`compute_pa` dominates: ~24 ms at 2 000 FDI targets, ~120 ms at 10 000 (one SVD + a batch of matrix-vector
norms). Therefore:

- Gate A = one 40-step loop × 120 ms ≈ **3 s**.
- `evaluate_policy` (one 40-step loop at 2 000 targets) ≈ **1 s**.
- `greedy_search(Nk)` = $\sum_{k} (55-k)$ evaluations ≈ $55\!-\!1\!+\!\dots$ ≈ **5–10 min per budget**.

There is no `numba` JIT installed (pandapower prints a harmless warning); DC power flow does not need it.

## 7. Import mechanism (and why not to change it)

`run_phase0.py` and `docs/make_figures.py` both do `sys.path.insert(0, <project_root>)` then
`from zt_cps_phase0.src import …`; the tests rely on the same path. `src/__init__.py` is present and empty.
**Do not rename the package or alter this path** — it would break the runner and the entire test suite at
once. A cleaner `pyproject.toml`-based install is recommended but deferred to Phase 1
([06_roadmap_phase1.md](06_roadmap_phase1.md), [07_environment_repro.md](07_environment_repro.md)).
