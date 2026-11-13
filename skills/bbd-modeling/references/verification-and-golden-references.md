# Verification and Golden References

How to prove a BBD model matches its reference, keep it matching through later work, and make it impossible to replace a baseline by accident. The gate-design method in general is the `circuit-to-dsp` skill's; golden-data generation from SPICE is `spice-circuit-modeling`'s. This file adds what BBD work needs.

## Contents

- [Two Identity Tiers](#two-identity-tiers)
- [Golden Datasets](#golden-datasets)
- [Freezing and Guarding References](#freezing-and-guarding-references)
- [Equivalence Matrices](#equivalence-matrices)
- [Test Signals](#test-signals)
- [BBD-Specific Checks](#bbd-specific-checks)
- [Regeneration Measurements](#regeneration-measurements)
- [Performance and Deadlines](#performance-and-deadlines)
- [Hosted = Offline](#hosted--offline)
- [Measurement Mistakes Worth Avoiding](#measurement-mistakes-worth-avoiding)

## Two Identity Tiers

| Comparison | Bar | Why |
|---|---|---|
| Offline reference (Python, float64) → real-time engine (C++) | **residual-bounded**, per metric, with stated bounds | different arithmetic; sample identity is not expected |
| Approved real-time build → any later build, **when the approved DSP contract mandates bit-identity** | **exact float32 equality** (`array_equal`) | a refactor, a JUCE upgrade or a new feature must not change approved audio; "sounds the same" is not evidence |
| Approved real-time build → a build with an **authorized** numerical change or optimization | **a newly approved, measured error budget** (per metric, on the frozen inputs) and **revised golden references** | some changes (reordered sums, a different integrator, float instead of double) cannot be bit-identical; they are allowed only as explicit revisions |

**Bit-identity is a contract choice, not a law of nature.** Where the project's approved DSP contract requires it, it is the preservation standard: any difference is a failure to investigate, not to explain away. A project may instead authorize a numerical change, for example an optimization that reorders floating-point sums. Then:
1. **say so explicitly:** a new model revision, with the reason;
2. **justify it:** what it buys (CPU, portability) against what it costs;
3. **measure the difference** against the frozen references, and have the owner approve the error budget, per metric, before the result counts;
4. **validate** with the full gate set, listening where the budget allows audible change;
5. **re-freeze:** generate revised golden references from the approved build, and keep the old set labelled as superseded;
6. **document** it in the phase report and the references' manifest.

It is never silently treated as equivalent.

*Case study:* Prismatica's approved contract requires bit-identity for Classic and Extended audio across later builds. Optimizations that would have changed the bits were rejected rather than re-budgeted ([realtime-implementation.md](realtime-implementation.md#cpu-budget)).

*Case study residuals, reference → engine:*
- static cases reached −150 dB (the float32 floor);
- automation cases −46 to −51 dB, after removing a known causal delay;
- host-rate cases −104 to −210 dB;
- guitar DI −132 dB.

## Golden Datasets

- **Render goldens from the frozen reference.** Keep the large audio out of version control, but **commit a manifest:** per-case SHA-256 of the float32 output, the input hashes, and the generating binary's hash. Record that they reproduce only with the same numerical libraries.
- **When an approved real-time build replaces the reference as the authority** (after listening approval), render new goldens from that build, from the same inputs, with float32-rounded parameter values. Regenerating them with the approved build must give byte-identical files.
- **Keep old goldens labelled as superseded,** with the reason. Never re-threshold them.
- **Record, per case,** beyond the hash: peak, last-2-seconds RMS, and whether L = R. A mismatch can then be characterized without re-rendering.

## Freezing and Guarding References

- **Freeze the criteria file** (hash) before the first run. Revisions are appended, and the original results stay in the report.
- **Make the qualification tool refuse to run** if:
  - the criteria lock, the golden manifest or the generated reference headers have drifted;
  - a code-generation script finds its committed header stale (`--check`).
- **Make "freeze" and "verify" separate commands.** Write the reference file only from `freeze`, and refuse to overwrite an existing reference without an explicit flag.
- **Pin the reference binary:** reproduce its hash from a clean worktree of the cited commit.
- **Re-run every earlier frozen set in every later phase.** A superseded check is printed with its original result, not counted.

## Equivalence Matrices

**A matrix crosses:**
- modes × feature switches × feedback levels × sample rates;
- every factory program × DI / noise / hot-DI inputs × three rates;
- abrupt automation of each control;
- the golden fixtures.

**Each row has an expected outcome:** identical, or "expected to differ" (for example, enhanced feedback above its threshold). "As expected" counts both.

*Case study sizes:*
- 887 rows against the previous product binary: 887 / 887 as expected; with the enhancement off, 284 / 284 identical;
- 226 frozen renders of the approved enhanced FILTER MATRIX voice;
- 142 references for the enhancement in the other modes;
- all re-checked, bit for bit, in each later phase.

## Test Signals

| Signal | Use |
|---|---|
| Impulse, clicks | delay measurement (cross-correlation), comb positions, transfer counts |
| Tones (coherent), sweeps | filter magnitude and phase per path, image levels, compander slopes |
| White / pink noise bursts | comb depth (broadband), regeneration excitation, onset bisection |
| **Real instrument DI** | the audible verdict: program-dependent compander behaviour, comb depth on music |
| Hot input (×4 or more) | headroom, limiter bounds, finite output |
| Digital silence | idle cost, denormals, no self-start |
| Parameter ramps and steps | smoothing, zipper, mode transitions |

**Specify the stimulus in every criterion.** BBD comb depth differs by stimulus (*case study:* 6–9 dB on noise, about 17 dB on tones, 12–25 dB on guitar).

## BBD-Specific Checks

- **Transfer counts and event times** under fixed, stepped, ramped and FM clocks, against an independent stage-array oracle (*case study:* 0 mismatches over 195,000 transfers).
- **Delay per mode and control extreme,** against the clock law (*case study:* the delay ranges match the calibrated clock table).
- **Image level** with the OUT1/OUT2 balance at nominal and off-nominal.
- **Control-voltage error** against the control network oracle (*case study:* within 6e-12 V).
- **Mono-sum residual** for dry ± wet output pairs.
- **Block-size invariance:** 1 / 7 / 512 bit-identical, also while regenerating.
- **Mode transitions** against the same render's steady state, not separate renders.

## Regeneration Measurements

- **Onset:** bisection on the control (or a constant gain) with a fixed excitation.
- **"Sustained":** the last 10 s above −60 dB re 1 V **and** drift under 0.05 dB/s.
- **Hysteresis:** slow ramps both ways.
- **Recovery:** time to −60 dB after turning down.
- **Echo T60:** from the repeat-envelope slope.
- **Aliasing:** compare the oscillation across internal rates.
- **Long run:** 600 s with eight excitations.
- **Toggle edges:** twin renders, with and without the event.

See [feedback-and-regeneration.md](feedback-and-regeneration.md#measuring-onset-sustain-and-recovery).

## Performance and Deadlines

- **Headless benchmark:** many cases × 10 s, both run orders, interleaved A/B rounds, the noise floor reported.
- **Profiler:** ns per internal sample by stage, median of several runs.
- **Live callback:**
  - a real audio device, at least 21 s per row;
  - small blocks;
  - every supported rate;
  - 8 instances;
  - editors open and closed.
- **Record per row:**
  - deadline misses, xruns, p99.9 and worst callback load;
  - audio-thread allocations;
  - the plug-in binary hash and the model revision read from the plug-in's own state.

## Hosted = Offline

- **Capture** the plug-in's input and output in a real host for a few seconds per configuration.
- **Re-render offline** with the engine CLI, using float32 parameter values.
- **Require bit-identity** for each mode, with the enhancement off and on, below, near and above onset.
- *Case study:* 16 / 16 per format for the product.

**This catches what engine tests cannot:** wrong parameter routing, a stale binary, wrapper gain staging.

## Measurement Mistakes Worth Avoiding

All of these happened in the case study, and the original results were kept with corrections:

| Mistake | Corrected practice |
|---|---|
| The test host never actually set the parameters it claimed (names against hashed IDs); some rows ran at defaults | unknown IDs fail hard; every setting confirmed in the plug-in's saved state |
| The host's cached value accepted an impossible value | read values back from the plug-in, not the host cache |
| A reused thread ID produced false audio-thread allocations | refresh the audio-thread identity every callback |
| The offline CLI got decimal values while the plug-in held float32 | pass float32-rounded values |
| A digital tail threshold flagged a correct tail at a hot input calibration | convert to volts (dB re 1 V) |
| A step-ratio heuristic "found" edges that were the signal's own slope changes | twin renders |
| A rectangular mean over a non-whole period overstated DC 400× | Hann-weighted mean, or whole periods |
| Comparing a causal engine with a look-ahead reference | remove the known causal delay first |
| Judging voice quality by raw notch depth | perceptual (ERB-band) metric on real material |
| Levels read from a power-up simulation | quiescent-start references |
