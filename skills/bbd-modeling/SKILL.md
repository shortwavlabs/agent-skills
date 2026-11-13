---
name: bbd-modeling
description: Model bucket-brigade device (BBD) analog delay circuits as validated real-time DSP. Covers reading BBD schematics (MN3xxx, SAD, Reticon parts), clock-to-delay conventions and two-phase transfer semantics, clock oscillators and modulation, variable-clock delay rendering, OUT1/OUT2 summing and sampling images, pre/de-emphasis, anti-alias and reconstruction filters, compander (NE570-family) modelling, headroom and bias, feedback loop gain, regeneration and controlled self-oscillation, mode transitions, real-time architecture and CPU, golden-reference verification, and an evidence-backed case study with failed experiments. Use when building or reviewing chorus, flanger, vibrato, analog delay, double-tracking, filter-matrix or multi-mode BBD pedal emulations, deriving delay from a BBD clock, adding feedback or regeneration to a BBD model, or qualifying such a model in a plugin.
---

# BBD Modeling: Bucket-Brigade Device Circuit Modeling and Real-Time DSP

## Overview

A bucket-brigade device is a clocked, sampled, unquantized analog delay. Most of a BBD effect's sound comes from:
- the clock (delay, modulation, bandwidth);
- the filters and compander around the chip;
- the feedback loop.

This skill guides the BBD-specific parts of turning such a circuit into a real-time model whose accuracy is proven. It routes to sibling skills for everything that is not BBD-specific.

| Need | Skill |
|---|---|
| A frozen SPICE / KiCad oracle of the circuit around the BBD | `spice-circuit-modeling` |
| Circuit reduction, nonlinear solvers, integrator and rate choice, gate design | `circuit-to-dsp` |
| Plug-in integration, parameters, state, host validation, editor-open real-time hazards | `juce-plugin` |
| Spectral measurement and error metrics | `dsp-engineer` |
| Filter and delay building blocks | `dsp` |
| Guitar-specific tone and product decisions | `guitar-dsp` |

## When To Use

- Chorus, vibrato, flanger, analog delay, double-tracking or "filter matrix" effects built on MN3xxx, SAD, Reticon or similar BBDs, or multi-mode pedals that switch between them.
- Converting a BBD clock frequency into delay, or modelling a modulated BBD clock.
- Modelling the compander, emphasis and anti-alias/reconstruction filters around a BBD.
- Adding feedback, regeneration or self-oscillation to a BBD model, including enhanced behaviour beyond the circuit.
- Building golden references and regression gates for such a model, or qualifying it in a plug-in.

Not this skill: digital delay lines that do not model a BBD (use `dsp`), or tape echo (wow and flutter are tape-transport effects, not BBD behaviour).

## Core Principles

1. **Fix the clock convention before any equation.** "Delay = N / (2 f)" is right only when f is the frequency of each two-phase clock line. State what f means, how many transfers each period makes, and which edge captures ([bbd-fundamentals.md](references/bbd-fundamentals.md#conventions-to-fix-first)).
2. **A sample's delay is the sum of the clock half-periods it spends in flight**, not N / (2 f(now)). Modulation, pitch and asymmetry depend on it.
3. **The chain is the sound.** Model pre/de-emphasis, anti-alias, reconstruction and the compander from schematic values. An EQ curve is an approximation, to be labelled and validated.
4. **Classify every fact:** circuit-derived, datasheet-derived, tolerance or trim, inferred, assumption, or deliberate extension. Never present an assumption as a measurement.
5. **Do not add structure nothing constrains.** Charge-transfer inefficiency, leakage, feedthrough, noise and phase overlap are usually non-identifiable from datasheets. Record them as not modelled, and plan measurements.
6. **Classic fidelity and enhanced behaviour are separate contracts.** A regeneration law beyond the circuit's own loop gain is an extension: its own switch, its own references, and bit-identical Classic behaviour when it is off.
7. **Freeze references by hash and re-run them every phase.** When the project's approved DSP contract mandates bit-identity (as Prismatica's does), a refactor must reproduce the frozen output exactly; "sounds the same" is not evidence. An authorized numerical change or optimization may instead use a newly approved, measured error budget and revised golden references, made explicit, justified, validated and documented as a new revision, never silently treated as equivalent ([verification](references/verification-and-golden-references.md#two-identity-tiers)).
8. **Real time is part of correctness:** allocation-free, lock-free processing, block-size invariance, bounded state, a valid tail contract, and host qualification with the editor open.

## Workflow

Twelve steps, each with what it must prove: [circuit-to-dsp-workflow.md](references/circuit-to-dsp-workflow.md).

1. Trustworthy documentation.
2. Signal paths.
3. BBD devices and stage counts.
4. Clock behaviour.
5. Filtering and companding.
6. Gain stages, nonlinearities, loop gain.
7. Offline reference (SPICE oracle plus a functional BBD renderer).
8. Numerical validation.
9. Real-time architecture.
10. Frozen reference datasets.
11. Plug-in integration.
12. Host and performance qualification.

## Reference Map

| Reference | Read when |
|---|---|
| [references/bbd-fundamentals.md](references/bbd-fundamentals.md) | BBD operation, clock conventions, delay/sampling/bandwidth, OUT1/OUT2 summing, clock drive requirements, bias and headroom, non-idealities, reading datasheets |
| [references/circuit-to-dsp-workflow.md](references/circuit-to-dsp-workflow.md) | Planning a BBD modelling project end to end; fact classification; gate discipline; what a functional BBD reference is |
| [references/clock-and-modulation.md](references/clock-and-modulation.md) | Clock oscillators and CV laws, LFOs, variable-clock delay rendering, interpolation, host-rate interaction, pitch modulation, discontinuities and mode transitions |
| [references/filtering-and-companding.md](references/filtering-and-companding.md) | Emphasis, anti-alias and reconstruction filters, discretization, compander modelling and the exact envelope identity, calibration and headroom, program dependence |
| [references/feedback-and-regeneration.md](references/feedback-and-regeneration.md) | Loop gain, regeneration threshold, resonance, controlled self-oscillation, saturation, smoothing, recovery, idle behaviour, mode changes during regeneration, Classic versus enhanced behaviour |
| [references/realtime-implementation.md](references/realtime-implementation.md) | CPU budget, internal rate, allocation and lock freedom, block-size independence, denormals, precision, long runs, lifecycle, state, latency, tail, multiple instances |
| [references/verification-and-golden-references.md](references/verification-and-golden-references.md) | Golden renders, bit-identity gates, impulse and DI tests, onset and decay measurements, CPU and deadline benchmarks, hosted = offline checks, freezing references |
| [references/analog-character-research.md](references/analog-character-research.md) | Considering hiss, clock instability, component variation or other analog imperfections as future features |
| [references/prismatica-case-study.md](references/prismatica-case-study.md) | A worked, evidence-referenced example (EHX Polychorus-inspired four-mode BBD plug-in), including failed experiments and their lessons |

## Project-Specific Numbers Are Not Rules

Stage counts, clock ranges, trimmer positions, regeneration coefficients, onset values, CPU figures and tolerances in the references are **outcomes of one project's measurements**, labelled as case-study values. Apply the method that produced them; re-derive the numbers for your circuit.

## Common Mistakes

| Mistake | Correction |
|---|---|
| Using N / (2 f) without saying what f is | State the convention; check it against the datasheet limits |
| Computing delay from the current clock only | Integrate the clock: each sample's delay is the half-periods it spent in flight |
| Replacing the emphasis, filters and compander with an EQ | Model them from schematic values; label any approximation and measure its error |
| Fitting a noise or CTI model to datasheet maxima | Leave it unmodelled and plan a measurement; fitted structure without evidence is a tuning knob |
| Interpolating raw digitized datasheet points into a nonlinearity | Fit a smooth function; validate on points not used for the fit |
| Reading levels from a power-up simulation | Compander servos and DC blocks settle over seconds; use quiescent starts for level claims |
| Treating "self-oscillates" as one number | Report onset per mode and settings, sustained level, recovery time and idle behaviour |
| Letting an enhanced feedback mode change Classic output | Keep Classic bit-identical with the extension off, and gate it by hash |
| Declaring a refactor "inaudible" | Bit-identity against frozen references where the contract requires it; otherwise an explicitly approved, measured error budget with revised references, documented as a new revision |
| Qualifying the plug-in only with the editor closed | Run allocation and deadline gates with the editor open and host automation delivered on the audio thread (`juce-plugin`) |
