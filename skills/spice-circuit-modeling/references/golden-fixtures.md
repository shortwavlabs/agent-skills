# SPICE Golden Fixtures For DSP Tests

## Contents

- Purpose and independence
- Generator pipeline
- Stimulus and boundary design
- Fixture metadata
- Storage, determinism and versioning
- Tiers and populations
- Checklist

This reference covers the generator side: producing compact, independent expected data from a frozen SPICE oracle for a C++ (or other) realtime model's regression tests. For frozen-release golden captures, drift limits and release integrity see the `circuit-to-dsp` skill's [circuit-reference-validation.md](../../circuit-to-dsp/references/circuit-reference-validation.md#golden-captures-and-drift). For how tests turn fixtures into gates (hard gates, quality targets, population completeness) see the `circuit-to-dsp` skill's `references/validation-gates.md`.

## Purpose And Independence

Expected data must come from the **oracle running in the simulator**, never from the equations or code of the model under test. A second implementation of the same equations shares its mistakes (a mistranscribed value, a missing return current). Keep the generator in a separate language or at least a separate code path, and never let the model's constants flow into the fixtures.

## Generator Pipeline

1. **Check the manifest first** (see `oracle-provenance.md`). On any mismatch, write nothing and exit non-zero. Test that failure path.
2. **Build decks from the canonical netlist.** For whole-circuit fixtures, apply parameter overrides to a copy of the canonical deck and strip its interactive control block. For stage-isolation fixtures, assemble the testbench from **verbatim canonical element lines** (by designator) plus explicit sources and loads; never retype component values.
3. **Run the simulator** (parallel runs are fine; one deck per case) with the qualified options and output settings.
4. **Parse the raw output robustly.** Use binary rawfiles for size and precision; parse headers by field name, not by line position (a header line such as `No. Variables:` contains the word `Variables:` too). Reject non-finite values, missing vectors, truncated windows and runs whose log contains errors even when the exit code is zero.
5. **Reduce on the oracle side** to the quantities the tests compare (spectral bins, operating points, AC responses), using the declared resampling and window. Store raw traces only where a test needs them.
6. **Write the fixture** and its hashes. Record every generator decision in the fixture itself (next section).

Record a convergence study per fixture family (for example the same cases at two maximum timesteps) and keep its result with the fixtures; see `numerical-qualification.md`.

## Stimulus And Boundary Design

- **Source impedance.** Drive the oracle through a very small series resistance (milliohms) if the realtime model's input is an ideal voltage source, so both see the same analytic stimulus. Otherwise model the real source impedance on both sides and record it.
- **Load.** Use the load the product contract specifies, and record it.
- **Stage isolation.** When a test isolates one stage, drive it with the oracle's **own** signal at that stage's input node: amplitude **and phase** from the oracle's small-signal transfer to that node (or the recorded waveform itself). A magnitude-only shortcut changes the sub-sample alignment of the stimulus and can move discretization-error measurements by tens of dB at exact-period tones.
- **Control and time-varying inputs.** For automation fixtures, feed the simulator the control trajectory directly (for example behavioural conductances driven by a file source) and give the model the identical trajectory. Decide deliberately whether the model's own input interpolation is part of the measured error, and document it.
- **Settling.** Start from the DC point, include enough settling before the analysis window, and state the window.
- **Deterministic stimuli.** Analytic sines, chords, bursts and ramps with stated parameters; seeded noise only with the seed recorded.

## Fixture Metadata

Each fixture family records, in its own file:

| Field | Content |
| --- | --- |
| Oracle identity | Netlist, project-library and external-card hashes; manifest version |
| Simulator | Version string, solver (for example KLU), compatibility mode |
| Analysis | Type, maximum step, tolerances, stop time, output interpolation |
| Stimulus | Waveform family and parameters, amplitude reference (peak or RMS), phase |
| Source and load | Values and where they connect |
| Controls | Every parameter value or trajectory, and its mapping (electrical versus panel position) |
| Window | Measurement start/end, settling, DC treatment |
| Probes | Node names, units, reference node (for example "relative to the bias node") |
| Resampling and metric | Method, grid, window function, bin definition, frequency range |
| Schema | `fixture_version` and a short description of what changed in each version |
| Case list | Per-case parameters with stable identifiers |

## Storage, Determinism And Versioning

- Store metadata as JSON and arrays as a binary blob (for example float64 real traces, float32 complex spectra), with the blob's SHA-256 in the metadata.
- Make regeneration **byte-identical**: no timestamps or host paths in hashed content, stable key and case order, fixed float formats. Regenerate twice and compare before claiming determinism.
- Bump `fixture_version` when a stimulus or metric definition changes, regenerate every family, and show that the unaffected families came out byte-identical.
- Track small tiers in version control deliberately (binary-file ignore rules with explicit negations for the tracked tiers); keep large tiers generated on demand and ignored.
- Tests verify fixture provenance (oracle hashes, blob hash, schema version) before using any number.

## Tiers And Populations

Typical tiers:

| Tier | Size and use |
| --- | --- |
| QUICK | Small, tracked; every build; smoke coverage of each family |
| STANDARD | Tracked; core regression, and a release gate in many projects: must then contain the complete population of every gate it evaluates |
| FULL | Generated on demand; large grids; release confirmation |
| RESEARCH | Sensitivity and hypothesis ensembles; never gates on their own |

A gate that is defined over a population (for example "worst error over all in-envelope cases") can only be evaluated by a tier that contains that **whole** population. Design the grids so STANDARD (and FULL) contain every gate's complete population, and write each family's grid axes in its metadata so a test can check completeness by content. The gate semantics are in the `circuit-to-dsp` skill's `references/validation-gates.md`.

## Checklist

- [ ] Manifest check gates the generator; its failure path writes nothing and is tested.
- [ ] Decks built from verbatim canonical element lines; no retyped values.
- [ ] Stage stimuli carry the oracle's amplitude and phase at the isolated node.
- [ ] Raw parsing validates every vector, window and log.
- [ ] Every fixture carries oracle, simulator, analysis, stimulus, boundary, control, window, probe, metric and schema metadata.
- [ ] Regeneration is byte-identical; schema changes bump the version.
- [ ] Each gate's complete population lives in the tiers that gate it.
