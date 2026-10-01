---
name: circuit-to-dsp
description: Turn a validated analog circuit reference (SPICE netlist, schematic) into a bounded realtime DSP model and prove it matches. Covers circuit reduction and physical state design, reduced op-amp and device models, monotone nonlinear solvers and lookup-table proofs, integrator and internal-rate selection, oversampling evidence, exact DC reset, time-varying controls, error decomposition, phase-ensemble and population-level validation gates, hard gates versus quality targets, and the end-to-end SPICE → KiCad → C++ → JUCE workflow. Use when building virtual-analog or circuit-accurate emulations (pedals, preamps, filters, compressors, synth circuits), choosing between waveshapers, nodal/state-space, DK or WDF models, designing Newton solvers for diode or transistor stages, choosing an integrator or oversampling rate for stiff circuits, designing SPICE-referenced regression gates for a realtime model, or reducing the CPU cost of a circuit model that already passes its gates.
---

# Circuit To DSP

## Overview

Use this skill to go from a frozen circuit oracle to a realtime model whose accuracy is **proven**, not assumed: decide what physics must survive, design the states and the nonlinear solve, choose the integrator and rate from evidence, and gate the result with tests whose PASS means something. It is instrument-agnostic: guitar pedals, amps, synth filters, studio compressors.

Ownership (load the other skills for their parts):

- `spice-circuit-modeling`: building and freezing the SPICE/KiCad oracle, device-model qualification, golden-fixture generation.
- `guitar-dsp`: guitar-specific decisions (signal chain, drive and control feel, tone, aliasing ladders, guitar release checks).
- `dsp-engineer`: measurement methodology (spectra, windows, coherent tones, error metrics).
- `dsp`: filter and numerical building blocks.
- `juce-plugin`: AudioProcessor/APVTS, lifecycle, latency and bypass APIs, CMake, formats, host validation.

This skill also owns [references/circuit-reference-validation.md](references/circuit-reference-validation.md), the instrument-agnostic authority for comparing DSP with a circuit reference: source hierarchy, the four result axes, the measurement contract (including the digital-sample ↔ physical-voltage calibration and electrical versus panel pot position), stage comparison, golden captures, drift and release integrity.

## Core Principles

1. **SPICE is an offline oracle.** Never run it in the audio callback; derive a bounded model.
2. **Partition by physics, not schematic boxes.** Classify every subsystem (must model / calibrated simplification / optional / omit) with measured evidence; small shared-return currents and off-device capacitances often dominate the last errors.
3. **Physical states, minimal nonlinear dimension.** Keep an authoritative state inventory; many linear states with one scalar monotone solve is a strong target.
4. **Prove the shipped numerics.** Monotonicity of the table actually shipped, solver bounds by fuzzing, solver memory at the returned root.
5. **Choose integrator and rate from decomposed error**, not tradition: discretisation versus the same model at high rate, total versus the oracle.
6. **Rate can be set by stiffness, not only aliasing.** Measure the actual production filters.
7. **Reset deterministically and exactly:** to the discrete model's DC fixed point when there is one intended quiescent state, to the declared state for multistable circuits, and by a validated start policy for oscillators.
8. **Validate controls in motion** against a time-varying reference.
9. **Gates must mean something**: hard gates for required bounds, visible quality targets for preferred margins, NOT EVALUATED when the data cannot establish a gate, completeness checked by content.
10. **Never loosen a gate to get green.** Revise a criterion only as a documented, evidenced revision.
11. **Speed up a validated model without changing it.** Remove duplicated and already-known computation first; any change to the arithmetic, rate or tolerance is a new revision that re-runs every gate.

## End-To-End Playbook

A reusable checklist; each step names the skill/reference that owns the details.

| # | Step | Owner |
| --- | --- | --- |
| 1 | Establish schematic/source provenance and the oracle's role | `spice-circuit-modeling` (oracle-provenance); [circuit-reference-validation.md](references/circuit-reference-validation.md) (source hierarchy, result axes) |
| 2 | Build and verify the canonical SPICE netlist | `spice-circuit-modeling` (netlist and simulator mechanics); [circuit-reference-validation.md](references/circuit-reference-validation.md) (reference verification checklist) |
| 3 | Qualify device models in isolation and in-circuit | `spice-circuit-modeling` (device-model-qualification) |
| 4 | Stress numerical convergence, operating states and statement order | `spice-circuit-modeling` (numerical-qualification) |
| 5 | Convert/map to KiCad if needed | `spice-circuit-modeling` (kicad-spice-parity) |
| 6 | Structurally compare the KiCad export with the oracle | `spice-circuit-modeling` (`scripts/netlist_compare.py`) |
| 7 | Numerically compare raw SPICE and the KiCad export | `spice-circuit-modeling` (kicad-spice-parity) |
| 8 | Freeze the oracle: hash manifest, failure path tested | `spice-circuit-modeling` (`scripts/spice_manifest.py`) |
| 9 | Classify circuit blocks for realtime importance | [circuit-reduction.md](references/circuit-reduction.md) |
| 10 | Derive the reduced model: states, coupling, reduced op-amps, reset | [circuit-reduction.md](references/circuit-reduction.md) |
| 11 | Build stage-isolated experiments driven by the oracle's own node signals | [validation-gates.md](references/validation-gates.md) |
| 12 | Choose integrator and internal rate from evidence | [integrators-and-rates.md](references/integrators-and-rates.md) |
| 13 | Build realtime-safe nonlinear solvers and prove tables | [nonlinear-solvers.md](references/nonlinear-solvers.md) |
| 14 | Generate independent golden data with complete gate populations | `spice-circuit-modeling` (golden-fixtures) |
| 15 | Implement the C++ DSP (allocation-free, per-channel state, cached coefficients) | `dsp`; `juce-plugin` audio-thread-safety; `guitar-dsp` cpp-juce-dsp-modeling for guitar products |
| 16 | Validate oracle → reduced model → production path, with decomposed errors | [validation-gates.md](references/validation-gates.md) |
| 17 | Integrate into JUCE: rate policy, latency, bypass, state | `juce-plugin`; [integrators-and-rates.md](references/integrators-and-rates.md) |
| 18 | Validate hosts (pluginval, auval, DAW smoke) | `juce-plugin` production-plugin-practices; `guitar-dsp` validation-and-release for guitar products |
| 19 | Benchmark realtime performance (back-to-back and live callback); take exact shortcuts before any numerical change | [integrators-and-rates.md](references/integrators-and-rates.md); [model-performance.md](references/model-performance.md); `juce-plugin` performance-investigation for attribution and tooling |
| 20 | Preserve evidence, known limitations, omission register and model/document identities | [validation-gates.md](references/validation-gates.md); [circuit-reference-validation.md](references/circuit-reference-validation.md) (release integrity) |

Iterate: a failed gate at step 16 usually sends you back to 9–13, not to a wider tolerance.

## Reference Map

| Reference | Read when |
| --- | --- |
| [references/circuit-reference-validation.md](references/circuit-reference-validation.md) | Verifying a reference circuit, claim-specific source hierarchy and result axes, measurement contracts, stage comparison, mismatch attribution, golden captures and drift, handoff to realtime DSP, release integrity and versioning, bench escalation |
| [references/circuit-reduction.md](references/circuit-reduction.md) | Choosing the realtime formulation, classifying subsystems, testing simplifications, state inventory, shared-node coupling, reduced op-amps, exact reset, automation, fidelity envelope |
| [references/nonlinear-solvers.md](references/nonlinear-solvers.md) | Deriving the nonlinear residual, feedback clipping, monotone scalar solvers, solver memory, fuzzing, device laws, table proofs |
| [references/integrators-and-rates.md](references/integrators-and-rates.md) | Comparing integrators, choosing the internal rate and oversampling policy, measuring production filters, latency/bypass, coefficient cadence, performance measurement |
| [references/validation-gates.md](references/validation-gates.md) | Error decomposition, stage isolation, hard gates versus quality targets, phase ensembles, population-level gates, tiers, criteria changes, reporting |
| [references/model-performance.md](references/model-performance.md) | Reducing the cost of a model that already passes its gates: what is contract and what is not, order of work, identical-channel sharing, settled-state hold and how to derive its tolerance, constants while controls rest, the evidence required |
| [references/case-study-sd1-overdrive.md](references/case-study-sd1-overdrive.md) | A worked example (clearly labelled case study) when a concrete precedent helps; never a source of defaults |

## Project-Specific Outcomes Are Not Rules

Rates, integrators, state counts, coupling choices, tolerance values, margin sizes, calibration levels and fidelity envelopes are **outcomes** of a project's measurements. Teach and apply the method that derived them. Quote a project's numbers only as a labelled case study.

## Common Mistakes

| Mistake | Correction |
| --- | --- |
| Running SPICE (or a general MNA engine) in the callback | Offline oracle, bounded realtime model |
| Modelling feedback diode clipping as pre-filter → tanh → post-filter | Solve the feedback network; keep clean parallel paths |
| Assuming "clean" op-amps are ideal, or modelling every datasheet parameter | Measure each property's effect in-circuit; keep what matters |
| Proving monotonicity of the analytic law but shipping a table | Prove the shipped interpolant per interval |
| Storing the last evaluated point as solver memory | Re-evaluate at the returned root |
| Picking trapezoidal "because it's standard" | Compare integrators on decomposed error across dense rates |
| Choosing oversampling from aliasing alone | Check stiffness, warping, solver and coupling drivers |
| Zero or approximate initial states | Exact discrete DC fixed point (or the declared state / validated start policy for multistable and oscillating circuits) |
| Validating only static responses | Time-varying reference for automation |
| Comparing a discretisation error with a total error | Decompose: reduction, discretisation, resampling, total |
| Detuning test tones to avoid coherent failures | Absolute gate at every phase; phase-averaged budget |
| A smoke tier recomputing a population gate from its subset | NOT EVALUATED plus a subset diagnostic; release tiers must be complete |
| Hiding a missed margin, or failing the build on a preference | Hard gates for requirements; reported targets for margins |
| Widening a gate to get a green build | Keep it red and report, or revise it with documented evidence |
| Lowering the oversampling factor, solver accuracy or integrator to save CPU | Those are the validated contract; time the stages and take exact shortcuts first |
| Assuming silence is cheap | A stateful model integrates on zeros; benchmark silence and hold only after verified convergence |
| Forcing mono to halve stereo cost | Share one island only while inputs and states are bit-identical; mono processing is a product decision |
| Picking a convergence tolerance as a round number, or waiting for bit-stationary state | Derive it from the settled model's measured rounding-noise floor over the corners |
