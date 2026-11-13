# Circuit-to-DSP Workflow for BBD Effects

The end-to-end path from a schematic to a qualified plug-in, with what each step must prove. The generic oracle and reduction methods belong to other skills; this file adds what is specific to clocked analog delay.

| Concern | Owner |
|---|---|
| SPICE oracle: netlist, model provenance, convergence, statement order, KiCad parity, golden data | `spice-circuit-modeling` |
| Circuit reduction, solvers, integrators and rates, validation-gate design | `circuit-to-dsp` |
| Plug-in lifecycle, parameters, state, host validation, real-time host hazards | `juce-plugin` |
| Measurement methodology | `dsp-engineer` |
| BBD clock semantics, two-phase transfer, variable-clock rendering, the BBD filter/compander chain, regeneration, BBD-specific gates | **this skill** |

## Contents

- [Classify Every Fact](#classify-every-fact)
- [The Twelve Steps](#the-twelve-steps)
- [Gate Discipline](#gate-discipline)
- [What a Functional BBD Reference Looks Like](#what-a-functional-bbd-reference-looks-like)

## Classify Every Fact

Tag every number in the model with its kind; reviews and later phases depend on it.

| Kind | Example | Treatment |
|---|---|---|
| **Circuit-derived** | an R or C value read from the drawing; the routing of a mode switch traced from the netlist | authoritative once the reading is verified |
| **Datasheet-derived** | stage count; clock limits; a typical THD curve | hash the datasheet revision; separate guaranteed limits from typical values |
| **Component tolerance / trim** | a bias trimmer at "mid"; a compander resistor at ±15 % | a declared nominal plus the range; never presented as a measured fact |
| **Inferred** | stage structure from a block diagram; a mode position read from switch-arc order | label "inferred", with the confidence and the corroborations |
| **Assumption** | the clock switching threshold at 50 % of the swing; an op-amp's output headroom | label it, and show the sensitivity when cheap (move it and report what changes) |
| **Deliberate extension** | a regeneration law that lets the loop sustain beyond the circuit's own maximum | separate switch or mode, separate references; never mixed into "circuit fidelity" claims |

## The Twelve Steps

1. **Obtain trustworthy documentation.** Schematic (vector PDF if possible), service notes, datasheets; hash and archive them. Record the build variant you assume.
2. **Reconstruct the signal paths.** Extract the netlist reproducibly (for example vector geometry → wire nets, plus a manual reading reconciled pin by pin). Compare **pin partitions**, not net names, and prove the checker catches injected faults. Know its limit: it cannot detect an error in the original drawing.
3. **Identify the BBDs:**
   - part numbers and stage counts;
   - which output (OUT1, OUT2 or both) is used, and through what balance network;
   - the input bias network;
   - which BBD each mode uses. Some pedals run two BBDs and switch outputs.
4. **Determine the clock:**
   - the oscillator topology and its control-voltage law (period against CV is often linear above a knee);
   - any divider (÷2 flip-flops are common, and they set the two-phase relationship);
   - the calibration trimmer and its documented target;
   - the frequency range per mode;
   - compliance with the BBD's clock requirements ([bbd-fundamentals.md](bbd-fundamentals.md#clock-drive-requirements));
   - the LFO and how each mode feeds it to the clock CV ([clock-and-modulation.md](clock-and-modulation.md)).
5. **Identify filtering and companding.** Pre/de-emphasis, anti-alias, reconstruction, compander channels (which is compressor, which expandor, traced from the netlist) and their time constants ([filtering-and-companding.md](filtering-and-companding.md)).
6. **Model gain stages and nonlinearities:**
   - op-amp stages: ideal until shown otherwise, with the error measured where it matters;
   - compander gain cells;
   - BBD headroom windows;
   - the feedback path's loop gain at every control extreme ([feedback-and-regeneration.md](feedback-and-regeneration.md)).
7. **Build an offline reference.** Two levels are useful:
   - **a SPICE oracle** of the analog circuitry. The BBD itself is usually not simulated in SPICE: see below;
   - **a functional reference renderer** (offline, float64) that implements the documented transfer contract, validated against the SPICE oracle at steady state.
8. **Validate numerical behaviour:**
   - step-size and tolerance convergence per metric;
   - breakpoints at clock edges (piecewise-linear sources, not analytic expressions with kinks);
   - co-simulation integrity, if the BBD is event-driven next to SPICE;
   - steady-state versus power-up levels (compander servos and DC blocks can take seconds to settle; do not read levels from a power-up run).
9. **Develop the real-time architecture:**
   - the BBD clock domain against the host rate;
   - delay interpolation or clock-domain resampling;
   - discretized filters;
   - an exact compander envelope;
   - parameter smoothing, CPU budget and allocation-free processing ([realtime-implementation.md](realtime-implementation.md)).
10. **Freeze reference datasets.** Hash-identified renders of the reference and of each approved real-time build; criteria files frozen before the first run ([verification-and-golden-references.md](verification-and-golden-references.md)).
11. **Integrate into a plug-in:**
    - parameters with stable IDs;
    - state with a model revision;
    - latency and bypass;
    - tail reporting consistent with any regeneration;
    - real-time host safety, including editor-open automation (`juce-plugin`).
12. **Qualify host behaviour and performance:**
    - hosted = offline bit-identity;
    - live-callback deadlines at small blocks and all supported rates;
    - multi-instance;
    - validators (auval, pluginval);
    - DAW checks the owner performs.

## Gate Discipline

- **Write the criteria before the results,** freeze them with a hash, and append revisions with the original results kept. Never re-grade a failure to make a phase pass; a retained FAIL with its explanation is evidence.
- **Re-run the earlier phases' frozen baselines in every later phase,** and require zero value differences where the earlier code is unchanged.
- **Record the convergence aids for every simulation:** initial conditions, gmin or source stepping, timestep limits. A run that needed scaffolding says so.
- **Use an evidence vocabulary:** for example VERIFIED / SUPPORTED BY MODEL / UNRESOLVED / NONCOMPLIANT, and model classes A (functional), B (datasheet-typical), C (exploratory), D (hardware-measured). Exploratory (class C) results never enter circuit runs or claims.
- **Keep diagnostic fixtures apart from source-faithful decks.** Examples are an ideal clock, or a zero-delay BBD pass-through for audio-path qualification. Label every diagnostic result as such.

## What a Functional BBD Reference Looks Like

A **written transfer contract** first, then code that implements it:
- what activates a clock phase (a threshold relative to the supply);
- when the input is captured, and how a charge packet moves;
- which stage each output reads;
- what the outputs do between transfers;
- how clock violations (overlap, missing or repeated phases) are **reported**, rather than silently "handled".

**Implementation options:**

| Option | Use when | Caution |
|---|---|---|
| Event-driven model coupled to the circuit simulator, outputs as external sources updated only at accepted time points | the analog circuitry around the BBD must be simulated with the BBD in the loop (feedback paths) | ensure rejected solver trials cannot change state; measure the coupling latency |
| Offline post-processing of a recorded clock and input | an independent oracle for the event-driven model | not a closed-loop integration method |
| A native simulator stage network (switches and capacitors) | a physics study of the transfer itself | under overlapping clocks, solver time constants decide how transparent the stages become, which is an invented physical law; avoid as the reference |

*Case study:* a Python event-driven BBD coupled live to libngspice, with an independent literal-stage oracle. It matched exact stage counts, delays and OUT1/OUT2 sequencing under fixed, stepped and frequency-modulated clocks, with 0 value changes across thousands of rejected solver trials.
