# Safety-Aware-CPS-Zero-Trust

A Master's-degree research project reproducing and extending **Feng & Hu (2023)**,
*"Cyber-Physical Zero Trust Architecture for Industrial Cyber-Physical Systems."*

**Phase 0** (this repository's current state) faithfully reproduces the paper's cyber-physical
attack/defense model on the **IEEE 30-bus** power system and validates it against the paper's published
numbers — a worm spreading over a 55-node cyber trust graph, sensor compromise, undetectable false-data-
injection (FDI) attacks against DC state estimation, the bad-data-detector **bypass probability $pa$**, and a
zero-trust node-hardening defense. It is the *trusted baseline* against which later safety-aware phases (deep
Q-learning, the five-action decision function, safety cost, metrics M1/M2/M3) will be measured.

## Results (validated)

| Quantity | Achieved | Paper | Band | |
|---|---|---|---|---|
| Clean unobservability residual | 7.89e-12 | ≈0 | <1e-6 | ✅ |
| Gate A — no-defense avg pa (40 steps) | **0.7408** | 0.7474 | [0.70, 0.80] | ✅ |
| Gate B — greedy pa, Nk=10 | **0.5606** | 0.5291 | [0.50, 0.58] | ✅ |
| Gate B — greedy pa, Nk=15 | **0.5483** | 0.5094 | [0.49, 0.57] | ✅ |
| Unit tests | 17 / 17 | — | all pass | ✅ |

![pa over time](docs/figures/pa_vs_step.png)

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python run_phase0.py          # the 6 PASS/FAIL validation gates (~10-25 min)

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest zt_cps_phase0/tests -p no:cacheprovider -q   # 17 tests

python docs/make_figures.py --fast   # regenerate the Gate A figures (fast)
python docs/make_figures.py          # regenerate all figures incl. the slow Gate B sweep
```

> Use a fresh `venv` (not anaconda base). pandapower is pinned to 3.4.0; the IEEE 30-bus case is
> `case_ieee30` (283.4 MW, 1.06 p.u. slack). See [docs/07_environment_repro.md](docs/07_environment_repro.md).

## Documentation

Full system documentation lives in **[`docs/`](docs/00_overview.md)** — start at
[`docs/00_overview.md`](docs/00_overview.md), which maps the eight chapters (background, the end-to-end
cyber-physical model with equations, code architecture, results & validation, the documented divergences from
the paper, the Phase-1 roadmap, and reproducibility).

## Layout

```
run_phase0.py            # entry point
requirements.txt
zt_cps_phase0/
├── src/                 # config, power_system, topology, attack_engine, policy_engine, runner
└── tests/               # 17 pytest invariants
docs/                    # this documentation set + make_figures.py + figures/
```
