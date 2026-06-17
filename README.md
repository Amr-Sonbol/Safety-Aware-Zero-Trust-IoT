# Safety-Aware-CPS-Zero-Trust

A Master's-degree research project reproducing and extending **Feng & Hu (2023)**,
*"Cyber-Physical Zero Trust Architecture for Industrial Cyber-Physical Systems."*

**Phase 0** (the frozen baseline) faithfully reproduces the paper's cyber-physical attack/defense model on
the **IEEE 30-bus** power system and validates it against the paper's published numbers — a worm spreading
over a 55-node cyber trust graph, sensor compromise, undetectable false-data-injection (FDI) attacks against
DC state estimation, the bad-data-detector **bypass probability $pa$**, and a zero-trust node-hardening
defense.

**Phase 1/1b** (shipped) is the contribution layer built *on top of* that frozen engine: a safety-aware
**five-action decision function** (`full`/`restricted`/`read_only`/`safe_mode`/`deny`) with two physical
channels (security $\gamma\to pa$, safety $O\to$ observability) and operational **metrics M1–M7** — where M7,
the state-estimation observability cost, is the physical safety axis. Runtime awareness (latched-compromise
trust floor, process-state $P$, IEC-weighted denial cost) makes the decision respond to the live attack
phase. **Deferred to Phase 2:** deep Q-learning and the physical safety cost $S_c$ (objective
$J = pa + \lambda S_c$); see [docs/12](docs/12_phase1_divergences.md) Divergence 5.

## Results (validated)

| Quantity | Achieved | Paper | Band | |
|---|---|---|---|---|
| Clean unobservability residual | 7.89e-12 | ≈0 | <1e-6 | ✅ |
| Gate A — no-defense avg pa (40 steps) | **0.7408** | 0.7474 | [0.70, 0.80] | ✅ |
| Gate B — greedy pa, Nk=10 | **0.5606** | 0.5291 | [0.50, 0.58] | ✅ |
| Gate B — greedy pa, Nk=15 | **0.5483** | 0.5094 | [0.49, 0.57] | ✅ |
| Unit tests | 58 / 58 | — | all pass | ✅ |

![pa over time](docs/figures/pa_vs_step.png)

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python run_phase0.py          # the 6 PASS/FAIL validation gates (~10-25 min)

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest zt_cps_phase0/tests -p no:cacheprovider -q   # 58 tests

python docs/make_figures.py --fast   # regenerate the Gate A figures (fast)
python docs/make_figures.py          # regenerate all figures incl. the slow Gate B sweep
```

> Use a fresh `venv` (not anaconda base). pandapower is pinned to 3.4.0; the IEEE 30-bus case is
> `case_ieee30` (283.4 MW, 1.06 p.u. slack). See [docs/07_environment_repro.md](docs/07_environment_repro.md).

## Documentation

Full system documentation lives in **[`docs/`](docs/00_overview.md)** — start at
[`docs/00_overview.md`](docs/00_overview.md), which maps the chapters. Docs 00–07 cover the Phase 0 baseline
(background, the end-to-end cyber-physical model with equations, code architecture, results & validation,
divergences, roadmap, reproducibility); docs 08–13 cover the Phase 1/1b contribution layer (decision model,
metrics M1–M7, results, divergences, pre-paper review).

## Layout

```
run_phase0.py            # Phase 0 entry point (the 6 validation gates)
requirements.txt
zt_cps_phase0/
├── src/                 # Phase 0: config, power_system, topology, attack_engine, policy_engine, runner
│                        # Phase 1/1b: node_profiles, decision, metrics, run_experiment
└── tests/               # 6 test files, 58 pytest invariants (Phase 0 + Phase 1/1b)
docs/                    # documentation set (00-13) + make_figures.py + make_phase1_figures.py + figures/
```

Run the Phase 1 experiments with `python -m zt_cps_phase0.src.run_experiment --full`.
