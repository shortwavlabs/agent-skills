---
name: spice-circuit-modeling
description: Build, qualify and freeze trustworthy SPICE/ngspice circuit references (oracles) and KiCad schematic simulations. Covers netlist and model provenance, hash manifests, device-model selection and datasheet-calibrated project models, numerical convergence, statement-order stress, operating-state checks for bistable circuits, KiCad SPICE-export parity, and golden-data generation for DSP regression tests. Use when writing or checking a .cir/.lib/.subckt deck, choosing or qualifying op-amp/diode/transistor models, debugging ngspice convergence, first-step failures or wrong operating points, converting a netlist to a KiCad schematic or validating a KiCad export, pinning simulator/model versions, or generating SPICE reference data for audio or DSP tests.
---

# SPICE Circuit Modeling

## Overview

Use this skill to make a SPICE deck an **oracle**: a frozen, reproducible, numerically qualified reference that other artifacts (a KiCad schematic, golden fixtures, a realtime DSP model) are checked against. "The simulation ran" is never the finish line. The deck must be correctly transcribed, built from labelled and hashed models, numerically converged for the metrics that matter, robust to statement order, in the intended operating state, and reproducible on another machine.

Related skills (load them for their parts; do not duplicate them here):

- `circuit-to-dsp`: turning the frozen oracle into a realtime model, choosing solvers, integrators and rates, and designing validation gates. Its `references/circuit-reference-validation.md` is the authority for comparing DSP against a circuit reference: the claim-specific source hierarchy and four result axes, measurement contracts, golden captures, drift and release integrity.
- `guitar-dsp`: guitar-specific signal-chain, drive-feel, tone and product decisions.
- `dsp-engineer`: spectral measurement methodology (windows, coherent tones, error metrics).
- `juce-plugin`: plugin build, lifecycle and host validation.

## When To Use

- Writing, transcribing or reviewing a `.cir` netlist, `.lib`/`.mod` model files or `.subckt` wrappers.
- Choosing between vendor op-amp/diode/transistor models, or writing a datasheet-calibrated model.
- ngspice errors or instability: "timestep too small", first-step failure, gmin/source-stepping fallbacks, results that change with statement order, solver or version.
- Circuits with switching or bistable logic whose operating point must be asserted.
- Converting a validated netlist to KiCad, or proving a KiCad schematic simulates the same circuit.
- Pinning simulator and model versions; generating SPICE golden data for DSP tests.

Not this skill: tuning DSP to match a reference (use `circuit-to-dsp`'s circuit-reference validation), realtime model structure (use `circuit-to-dsp`), or runtime SPICE in an audio callback (don't; SPICE is an offline oracle).

## Core Principles

1. **Declare the direction of truth.** Name the oracle. Derived views (schematics, exports, fixtures) are fixed to match it, never the reverse.
2. **Label every model honestly**: exact manufacturer, exact device wrong grade, similar substitute, datasheet-calibrated project model, generic fallback or diagnostic control. Never promote a label silently.
3. **Hash before you simulate.** Netlist, project libraries, external files (whole file by default, or used cards only when chosen per file), the used card text, simulator version and required options. Refuse to run on a mismatch.
4. **Converged is not accurate.** Qualify timestep and tolerances per metric, against a criterion well below the gate the data will support.
5. **Assert the operating state.** An AC result is meaningless if its operating point landed in the wrong state; `.ic`, `.nodeset` and raised iteration limits are scaffolding, not physics.
6. **Physics does not depend on statement order.** Stress with unique keyed permutations; count failures and wrong states separately.
7. **Select models on all the evidence.** Exact-part provenance is valuable, but it does not override demonstrated numerical fragility or wrong in-circuit behaviour. A model must jointly satisfy provenance, the physical fidelity this circuit needs, simulator compatibility and numerical robustness; qualify it in-circuit, not only on the datasheet bench.
8. **Read the simulator source** when a realtime model must match a device law to millivolts, and verify against a sufficiently fine DC sweep.
9. **ERC, connectivity, exported-netlist equivalence and numerical parity are four different gates.**
10. **Prove the validators.** Every checker gets a failure-path or mutation test.

## Workflow

1. Establish source provenance and the oracle's role ([oracle-provenance.md](references/oracle-provenance.md)).
2. Transcribe the canonical netlist; verify topology, values, polarity and operating point (`circuit-reference-validation.md` in `circuit-to-dsp` for the checks).
3. Select and qualify device models: isolated bench, in-circuit start-up, pre-AC operating point, order stress ([device-model-qualification.md](references/device-model-qualification.md)).
4. Qualify numerics: timestep/tolerance convergence per metric, operating-state assertions, engines and versions ([numerical-qualification.md](references/numerical-qualification.md)).
5. If an EDA view is needed, build the mapping, adapters and validators, and prove structural and numerical parity ([kicad-spice-parity.md](references/kicad-spice-parity.md)).
6. Freeze: write the hash manifest, test its failure path, record the reproducibility status (design / configured-machine tooling / clean machine).
7. Generate independent golden fixtures with complete gate populations ([golden-fixtures.md](references/golden-fixtures.md)), then hand over to `circuit-to-dsp`.

## Reference Map

| Reference | Read when |
| --- | --- |
| [references/oracle-provenance.md](references/oracle-provenance.md) | Declaring artifact roles, labelling models, freezing the oracle, hashing, licensing of external model files, reproducibility gates |
| [references/numerical-qualification.md](references/numerical-qualification.md) | Convergence and tolerance studies, `.ic`/`.nodeset`/`itl1`, solver choice, bistable operating points, statement-order stress, multiple engines |
| [references/device-model-qualification.md](references/device-model-qualification.md) | Evaluating vendor models, benchmarking op-amps, in-circuit qualification, writing datasheet-calibrated models, matching simulator device laws |
| [references/kicad-spice-parity.md](references/kicad-spice-parity.md) | Netlist → KiCad conversion, adapter subcircuits, structural validation, mutation self-tests, numerical parity, workbook and export pitfalls |
| [references/golden-fixtures.md](references/golden-fixtures.md) | Generating SPICE reference data for DSP tests: independence, stimulus/boundary design, metadata, determinism, tiers |

A worked example of the whole pipeline is the `circuit-to-dsp` skill's `references/case-study-sd1-overdrive.md`. Read it only when an example helps.

## Scripts

Standard-library Python; each has `--self-test`.

| Script | Use for |
| --- | --- |
| `python3 scripts/spice_manifest.py make --out M.json --file DECK --card LIB=NAME [--used-cards LIB] [--simulator-command EXE] [--require-feature F] [--require-text PATH=RE]`, then `check M.json` | Hash-pin netlists, libraries and used `.model`/`.subckt` cards (per-file `strict_file` or `used_cards` policy), simulator version, required solver features and deck text; exit non-zero before simulating on any mismatch |
| `python3 scripts/netlist_compare.py REF.cir DERIVED.cir [--adapters LIB] [--alias MAP.json] [--mutation-check]` | Structural equivalence of a derived netlist (for example a KiCad export) with the oracle: one consistent net map, values, inline model and subcircuit bodies, directives; planted-fault self-check. Fails closed: unsupported element types (including XSPICE `A`), directives, `.lib` sections, nested inline subcircuits and non-allowlisted `.control` commands exit "NOT QUALIFIED" rather than claiming equivalence; include files are reported, not followed |
| `python3 scripts/spice_order_stress.py DECK --count N --out DIR [--engine NAME=CMD] [--fail-regex RE] [--expect-regex RE]` | Unique keyed statement-order permutations, circuit-identity proof over whole logical statements (continuations attached, fixed statements in place), failures and wrong states counted separately per engine |

Run `--help` for options. These scripts are generic; project-specific checks (switch logic, control mapping, behaviour windows) belong in the project's own validator.

## Common Mistakes

| Mistake | Correction |
| --- | --- |
| Editing the netlist to match a schematic | The oracle wins; fix the derived view |
| Calling a substitute or project model "the manufacturer model" | Use the label table; record source and hash |
| Trusting an AC result without checking its operating point | Assert the state; raise `itl1` and use `.nodeset` as documented scaffolding |
| "Converged, so accurate" | Per-metric timestep/tolerance study with a declared criterion |
| Randomising statement order with a reseeded generator | Keyed permutations; report unique count |
| Keeping a fragile vendor macro because its part number is right | Qualify in-circuit; weigh provenance, fidelity, compatibility and robustness together |
| Treating ERC or a tidy drawing as parity | Structural comparison, mutation test and numerical parity |
| Assuming the textbook diode equation is what the simulator computes | Read the device source; fine DC sweep across branch thresholds |
| Vendoring restricted model files | Keep external, pin by hash, document how to obtain |
| Claiming clean-machine reproducibility from the development machine | Report it as pending until a clean run happens |
