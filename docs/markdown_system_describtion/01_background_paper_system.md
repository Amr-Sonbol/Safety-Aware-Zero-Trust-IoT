# 01 — Background: The Paper and the Threat Model

This chapter frames the research for a reader who has **not** read Feng & Hu (2023). It introduces the
problem the paper addresses, the cyber-physical threat model in prose, and the shared terminology used
throughout this documentation. It closes by stating precisely what Phase 0 reproduces and what it
deliberately leaves to later phases.

> **Reference.** Feng & Hu (2023), *"Cyber-Physical Zero Trust Architecture for Industrial Cyber-Physical
> Systems."* The present project, *Safety-Aware-CPS-Zero-Trust*, reproduces and then extends this work as a
> Master's-degree research project. Phase 0 is the faithful-reproduction baseline.

---

## 1. The problem: trust in industrial cyber-physical systems

An **industrial cyber-physical system (CPS)** — a power grid, water network, or factory — couples a physical
plant to a cyber network of sensors, controllers, and communication links. Operators rely on **state
estimation**: the control center collects sensor measurements and infers the plant's internal state (in a
power grid, the bus voltage angles) to make control and safety decisions.

Two facts make this dangerous. First, the cyber network is **interconnected**, so malware (a *worm*) that
compromises one device can spread to others along trust relationships. Second, state estimators run a
**bad-data detector (BDD)** that flags inconsistent measurements — but a sufficiently clever attacker can
craft a **false-data-injection (FDI)** attack that the BDD cannot see, silently corrupting the operator's
view of the plant.

A **zero-trust architecture (ZTA)** responds by refusing to grant implicit trust between devices: it can
*harden* nodes (tighten or reduce the trust they extend) to slow or contain a spreading worm. The paper's
central question is: **how much can a ZTA defense reduce the attacker's ability to slip an undetectable FDI
attack past the bad-data detector — and how should it spend a limited hardening budget?**

## 2. The threat model, end to end

The paper models a chain of four interacting pieces. (The mathematics is in
[02_cyber_physical_model.md](02_cyber_physical_model.md); here it is the narrative.)

1. **The physical plant and its estimator.** The grid is the IEEE 30-bus benchmark. Under the standard DC
   approximation, each branch's power flow is a linear function of the bus angles, captured by a measurement
   matrix $H$. A weighted-least-squares (WLS) estimator $K$ recovers the state from the measurements, and the
   BDD watches the *residual* — the part of the measurements the estimator cannot explain.

2. **The worm.** A piece of malware spreads over a fixed **cyber trust graph** $B$ of 55 nodes following an
   epidemic (SIS — susceptible/infected/susceptible) dynamic governed by a spread rate $\beta$ and a recovery
   rate $\gamma$. Over time it infects a growing fraction of the network.

3. **Sensor compromise.** Some nodes are **sensors** that collect physical measurements. When the worm reaches
   a sensor node, the attacker gains the ability to manipulate that node's measurements. A map $A$ records
   which measurement each sensor collects.

4. **The FDI attack and the bypass probability $pa$.** Owning a set of compromised measurements, the attacker
   tries to inject a false-data attack that (a) meaningfully corrupts the estimated state yet (b) leaves the
   BDD residual small enough to go undetected. The headline metric is the **bypass probability $pa$**: the
   fraction of attack attempts that succeed in passing the detector. A high $pa$ means the system is wide
   open; a successful defense pushes $pa$ down.

The **defense** is the ZTA hardening the trust graph $B \to B'$: by reducing the trust a node extends, it
slows the worm, fewer sensors are compromised, fewer measurements are manipulable, and $pa$ falls. The paper
uses **deep Q-learning** to choose which nodes to harden under a budget $N_k$.

## 3. Shared terminology

These symbols recur in every chapter (full table in [02 §Symbol table](02_cyber_physical_model.md)):

| Term | Meaning |
|---|---|
| **$H$** | measurement matrix (DC power-flow Jacobian): maps bus angles → branch-flow measurements |
| **$K$** | WLS state estimator gain: maps measurements → estimated state |
| **BDD** | bad-data detector: flags measurements whose residual is too large |
| **$B$ / $B'$** | the 55-node cyber trust (infection) graph; $B'$ is the *defended* graph |
| **$A$** | measurement→sensor map: which node collects each measurement |
| **$\rho$ / $\bar\rho$** | per-node infection probability / its mean over all nodes |
| **FDI** | false-data injection: a crafted, ideally undetectable, measurement attack |
| **$pa$** | **bypass probability**: fraction of FDI attempts that evade the BDD |
| **$N_k$** | defense budget: number of nodes the ZTA may harden |
| **ZTA** | zero-trust architecture: the defense that hardens nodes |

## 4. What Phase 0 reproduces (and what it does not)

Phase 0 has **one job**: faithfully reproduce the paper's **cyber-physical attack/defense measurement model**
and validate it against the paper's published numbers. Concretely, it reproduces:

- the physical model ($H$, $K$, real DC measurements, the unobservability property);
- the worm dynamics, sensor compromise, and FDI feasibility that produce $pa$;
- the **no-defense bypass probability** ("Gate A", paper $\approx 74.74\%$); and
- a **defended bypass probability under a node-hardening budget** ("Gate B", paper $52.91\%$ at $N_k{=}10$,
  $50.94\%$ at $N_k{=}15$).

The validated numbers are in [04_results_and_validation.md](04_results_and_validation.md). Where the paper's
literal recipe could not produce its own reported behaviour, Phase 0 makes documented modeling choices —
recorded honestly in [05_divergences.md](05_divergences.md).

**Deliberately deferred to later phases** (not built in Phase 0):

- the full **deep Q-learning** policy optimizer (Phase 0 uses a transparent greedy heuristic in its place);
- the **five-action decision function** (full / restricted / read-only / safe-mode / deny) and *soft* actions;
- the **safety cost $S_c$** and the safety-aware objective that the project's name points toward;
- the operational **metrics M1 / M2 / M3**.

Where each of these will attach to the existing code is laid out in
[06_roadmap_phase1.md](06_roadmap_phase1.md). The point of Phase 0 is that those later phases are measured
against a baseline we can *trust* — a baseline whose every number is reproducible and whose every modeling
choice is documented.
