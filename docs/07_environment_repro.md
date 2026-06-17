# 07 — Environment & Reproducibility

This chapter pins the exact environment and the commands that reproduce every number and
figure in this documentation set. If a result here disagrees with a fresh run, the cause is
almost always an environment drift listed below.

---

## 1. Runtime environment

| Component | Value | Why it matters |
|---|---|---|
| OS | Linux (x86-64) | pandapower/numpy wheels are platform-specific |
| Python | **3.12.3** | Matches the project `.venv`; pandapower 3.4.0 supports 3.10–3.12 |
| Virtual env | `.venv/` at project root (`python3 -m venv .venv`) | Isolated from the system/anaconda Python (the anaconda base has a broken NumPy 2.x/pandas ABI and no pandapower) |

> **Do not use the anaconda base interpreter.** Phase 0 was built in a fresh `venv` precisely
> because the anaconda base on this machine has an incompatible NumPy/pandas ABI and lacks
> pandapower. Always `source .venv/bin/activate` first.

## 2. Pinned dependencies (`requirements.txt`)

```text
pandapower==3.4.0
numpy>=1.26,<2.4
scipy<1.17
pandas~=2.3
matplotlib>=3.7
pytest>=7.0
```

Resolved/installed versions at validation time:

| Package | Installed | Notes |
|---|---|---|
| pandapower | 3.4.0 | **Exact pin** — the IEEE 30-bus case data and `_ppc` layout must not drift |
| numpy | 2.3.5 | within `>=1.26,<2.4`… (resolver pulled 2.3.x; compatible) |
| scipy | 1.16.3 | within `<1.17` |
| pandas | 2.3.3 | `~=2.3` |
| matplotlib | 3.10.9 | only needed for `docs/make_figures.py` |

To recreate from scratch:

```bash
cd /home/poky/Workspace/Amr/CPS_Safety_Aware
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -c "import pandapower as pp; print('pandapower', pp.__version__)"   # -> 3.4.0
```

## 3. The IEEE 30-bus case — `case_ieee30`, not `case30`

`power_system.load_network()` calls `pandapower.networks.case_ieee30()`. This is deliberate:

- `case_ieee30()` → **total load 283.4 MW**, **slack voltage 1.06 p.u.** (the published MATPOWER-origin case the paper's numbers assume).
- `case30()` → a different variant with a 1.0 p.u. slack; it would silently shift the DC flows and break the calibration.

`load_network()` asserts both values (`|load − 283.4| < 0.5`, `|slack − 1.06| < 1e-6`), so a wrong
case fails loudly at startup rather than producing subtly wrong gates.

## 4. Load profile: synthetic vs. NYISO (synthetic is active)

`power_system.load_profile()` has two branches:

1. **If `data/nyiso_oct2022.csv` exists** → it is loaded, the first numeric column is resampled to
   40 points and normalized to mean 1.0.
2. **Otherwise (the current state)** → a documented smooth daily curve
   `profile[t] = 1 + 0.15·cos(2π·t / 40)` scales the base loads by ±15% across the horizon.

The `data/` folder is **empty**, so the **synthetic ±15% cosine profile is the active path**. The
function prints which source it used at runtime (`[load_profile] source = synthetic daily curve …`).
Dropping a `nyiso_oct2022.csv` into `data/` would switch the run to real load data with no code change.

## 5. Reproducibility model

Every stochastic draw routes through a single seed, `config.SEED = 0`:

- FDI targets `C_targets` are drawn once with `default_rng(SEED)` and reused everywhere.
- The worm/compromise simulation reseeds `default_rng(SEED + 1)` at the start of **each** run
  (Gate A and every `evaluate_policy` call), so policies are compared on the *same* infection
  realization. This makes Gate A, Gate B, and the figures bit-for-bit reproducible.

## 6. Commands

### Run the validation gates (fast: ~10–25 min, dominated by Gate B greedy)

```bash
source .venv/bin/activate
python run_phase0.py          # prints the 6 PASS/FAIL checks; exits 0 iff all pass
```

Expected tail:

```text
ALL CHECKS PASSED — Phase 0 baseline validated.
```

### Run the unit tests (fast: ~10 s)

```bash
source .venv/bin/activate
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest zt_cps_phase0/tests -p no:cacheprovider -q
```

> **Why the flags?** This machine has ROS (`/opt/ros/jazzy`) on the path, whose pytest
> `launch_testing` plugins are auto-discovered and crash collection with a `yaml` import error.
> `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` and `-p no:cacheprovider` isolate our suite from them.

Expected: `17 passed`.

### Regenerate the documentation figures

```bash
source .venv/bin/activate
python docs/make_figures.py            # all 3 PNGs (slow: Gate B sweep ~15-25 min)
python docs/make_figures.py --fast     # only pa_vs_step + rho_bar_vs_step (fast: ~10 s)
```

The script prints the numeric series it plots so the figures can be audited against
`run_phase0.py` output (e.g. the `pa_vs_step` average must equal the Gate A value, 0.7408).

## 7. Expected wall-clock

| Task | Approx. time | Bottleneck |
|---|---|---|
| `pytest` | ~10 s | network build, small sims |
| Gate A (in `run_phase0.py`) | ~3 s | one 40-step loop, full 10 000 FDI targets |
| Gate B greedy, per `Nk` | ~5–10 min | `O(Nk × 55)` full 40-step re-simulations (2 000 FDI targets each) |
| `make_figures.py --fast` | ~10 s | the two Gate A figures only |
| `make_figures.py` (full) | ~15–25 min | the `Nk ∈ {0,5,10,15}` greedy sweep |

`compute_pa` is the inner cost (~24 ms at 2 000 FDI targets, ~120 ms at 10 000); everything else
is negligible. There is no `numba` acceleration installed — pandapower prints a one-line warning to
that effect, which is harmless for DC power flow.

## 8. Known-harmless warnings

- `numba cannot be imported and numba functions are disabled` — DC power flow does not need it.
- `DeprecationWarning: tap_dependency_table is missing in net` — an internal pandapower 3.x notice
  about the case format; it does not affect the DC Jacobian or flows.

## 9. Packaging status (and a deferred recommendation)

Phase 0 is **not** a git repo and has **no `pyproject.toml`/`setup.py`**. Imports work because
`run_phase0.py` and the figures script prepend the project root to `sys.path` and import the package
as `zt_cps_phase0.src.<module>`; `src/__init__.py` exists (empty). **Do not rename the package or
change this import path** — `runner.py` and all tests depend on it.

A `pyproject.toml` (with `[tool.pytest.ini_options] pythonpath = ["."]` and `pip install -e .`) would
remove the `sys.path` shims and is **recommended for Phase 1**, where new modules are added. It is
deliberately *not* introduced now, to avoid perturbing the validated import path. See
[06_roadmap_phase1.md](06_roadmap_phase1.md).
