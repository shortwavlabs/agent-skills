# SPICE Numerical Qualification

## Contents

- "Converged" is not "accurate"
- Analysis types and what they assume
- Initial conditions: `.ic`, `.nodeset`, iteration limits and fallbacks
- Solver, tolerance and timestep settings
- Timestep and tolerance convergence study
- Convergence failures versus physical behaviour
- Statement-order stress
- Operating-state tests for bistable and switching circuits
- Multiple engines and versions
- Checklist

General numerical-qualification criteria (declared limits, threshold searches, `UNQUALIFIED_NUMERICAL` versus `FAIL`, rejecting incomplete windows) live in the `circuit-to-dsp` skill's [circuit-reference-validation.md](../../circuit-to-dsp/references/circuit-reference-validation.md). This reference adds the simulator-level mechanics that decide whether an ngspice-style oracle can be trusted.

## "Converged" Is Not "Accurate"

A SPICE run that finishes without an error has only met its internal Newton and local-truncation tolerances. It says nothing about:

- whether the timestep was small enough for the **metric you care about** (harmonics at 20 kHz, a 0.1 dB response, a millivolt bias);
- whether the DC operating point is the **intended** one (bistables, latches, switches);
- whether the answer depends on statement order, solver choice or simulator version;
- whether convergence aids (gmin, source stepping, added conductances) loaded the circuit.

Qualify each of these separately and record the result per metric.

## Analysis Types And What They Assume

| Analysis | Computes | Trap |
| --- | --- | --- |
| `.op` | One DC solution | A multi-stable circuit has several; Newton picks one, and fallbacks pick unpredictably |
| `.ac` | Small-signal response linearised about the `.op` point | Meaningless if the `.op` landed in the wrong state; cannot show clipping or recovery |
| `.tran` | Time response from an initial state (the DC point at t = 0, or `.ic`/UIC values) | Output samples are interpolated or adaptive; internal steps may be much larger than the output spacing; start-up transients can dominate short windows |
| `.dc` sweep | Chained DC solutions | Hysteresis depends on sweep direction and on the previous point |

Cross-check where it matters: compare `.ac` with a settled, sufficiently small transient sine at the same bias; compare static-switch states in both analyses.

## Initial Conditions: `.ic`, `.nodeset`, Iteration Limits And Fallbacks

- `.nodeset` gives **hints** to the DC Newton solve. `.ic` sets **initial values** for transient analysis (and, with UIC, skips the DC solve). They answer different questions; a deck that selects a state with `.ic` for transient runs has not selected it for a standalone `.op`/`.ac`.
- When DC Newton fails within its iteration limit (ngspice `itl1`, default 100), the simulator falls back to gmin stepping and source stepping. Those continuation methods can **ignore `.nodeset`** and land in the opposite state or on a metastable balance point. The run still "succeeds".
- Raising the DC iteration limit (for example `itl1=10000`) keeps Newton on the `.nodeset` path. Treat it as deterministic scaffolding: keep it, document why, and test whether the deck still needs it.
- Transient per-timepoint limits (ngspice `itl4`) and the initial-step rules affect start-up. A deck that fails its **first** transient step is usually a model or solver problem, not a physical one.
- Always verify the operating point that an `.ac` analysis used (node voltages that identify the state) before trusting any AC gain or impedance.

## Solver, Tolerance And Timestep Settings

Record every setting that changes numerics in the manifest and the fixture metadata:

| Setting | Notes |
| --- | --- |
| Matrix solver (ngspice: `.options klu` or the default sparse solver) | The solver can decide whether a stiff or switch-heavy deck starts at all; keep the qualified choice and fail if it disappears |
| `reltol`, `abstol`, `vntol`, `chgtol`, `trtol` | Tighten `reltol` for nodes that feed precise metrics; loosening tolerances to "get a pass" is not qualification |
| Integration method (`trap`, `gear`) and order | Trapezoidal can ring on stiff nodes; Gear damps; record which, and check whether ringing is numerical |
| Maximum timestep (`.tran` TMAX) | The main accuracy knob for audio metrics; output step ≠ internal step |
| `gmin` and added leakage/parallel conductances | Convergence aids are circuit elements; check their loading near open circuits and pot endpoints |
| Compatibility mode (ngspice `ngbehavior` in `.spiceinit`: `ltpsa`, `psa`, `hs`...) | Changes parsing and defaults for vendor models; the same deck may behave differently without it |
| Temperature (`.temp`, `TNOM`) | Device equations are temperature dependent; state it |

Adaptive transient output has non-uniform timestamps. Resample onto a uniform grid with a documented method (or integrate with actual time intervals) before any FFT, and keep the window boundaries exact. The measurement-contract rules are in [circuit-reference-validation.md](../../circuit-to-dsp/references/circuit-reference-validation.md#align-signals-and-interpret-metrics).

## Timestep And Tolerance Convergence Study

For every fixture family that becomes golden data:

1. Pick the metric the downstream gate uses (harmonic-vector error, band-limited ESR, a bias voltage, a threshold crossing), not raw waveform identity.
2. Run coarse, fine and finer settings (for example TMAX h, h/5, h/25, and a tighter `reltol`), with everything else fixed.
3. Compute the metric difference between refinement pairs and compare with a **declared** criterion that is well below the gate it will support (for a gate at −40 dB, a reference converged only to −45 dB is useless).
4. Qualify the hardest cases (highest frequency, highest drive, sharpest switching), not just a benign one.
5. Record the chosen settings and the achieved convergence in the fixture metadata.

Different metrics converge differently: a small-signal response may be converged at a step where a 7 kHz clipped waveform is not.

## Convergence Failures Versus Physical Behaviour

| Symptom | Usually numerical | Could be physical |
| --- | --- | --- |
| "timestep too small", first-step failure, singular matrix | Yes: model discontinuities, solver choice, missing DC path, floating node | Rarely |
| Result changes with statement order or solver | Yes | No: physics does not depend on statement order |
| Different stable state from the one intended | Initialisation/fallback | Possibly a real bistable: test with explicit initial states |
| Oscillation, chatter | Check with smaller steps and Gear | Real oscillators and comparators chatter too: preserve and qualify |
| Rail sag, latch-up | Check supply models and limits | Often real: keep it and measure it |

Resolve by refinement, alternative initial states, alternative solver and alternative engine. A behaviour that survives all four is probably physical; one that moves with any of them is numerical until proven otherwise.

## Statement-Order Stress

Matrix ordering, pivoting and initial guesses depend on the order of statements. EDA exports reorder statements after unrelated edits. A robust oracle gives the same result for every order; a fragile one fails some fraction of orders, and a fragile model will eventually fail in someone else's hands.

Procedure (implemented by `scripts/spice_order_stress.py`):

1. Reorder only top-level element statements; keep continuation lines with their statement; keep the title, directives, `.subckt` and `.control` blocks in place.
2. Prove every variant is the same circuit before running: fixed statements unchanged in place, and the same multiset of whole logical element statements (continuation lines attached to their parent), not the original order. Comparing sorted physical lines is not enough: it cannot see a continuation moved under the wrong element.
3. Draw orders from a **keyed** generator: order `id` of stream `s` comes from `Random(f"{seed}:{s}:{id}")`. Deduplicate and report the number of **unique** orders.
4. Use separate streams for separate corpora (primary operating states, control endpoints) and report their overlap.
5. Run the **same order file** in every engine and state (a matched set), so engines and states are compared order for order.
6. Keep runs short: start-up and operating-point selection are where order sensitivity bites. Include the standalone `.op` used before AC.
7. Report **failures** (non-zero exit, error text, aborted step, timeout) and **wrong states** (completed, but in the wrong operating point) separately. A wrong state is neither a pass nor a convergence failure.

Harness pitfall: re-creating a generator with the same seed for every run (`Random(seed).shuffle(order)` inside the loop) yields the **same** permutation every time. Thousands of "randomised" runs then test one order and give false confidence. Always count unique orders.

Size the corpus to the claim: a handful of failures in a few thousand orders is a real defect in a model that should be deterministic. Rerun the same corpus after any model change.

## Operating-State Tests For Bistable And Switching Circuits

- Define each intended state (for example EFFECT/BYPASS, battery/adaptor, switch positions) by measurable node conditions, and classify every run into intended, opposite or metastable (both sides near balance).
- Test states separately in transient start-up, standalone `.op`, and the `.op` that precedes `.ac`.
- State-selection aids (`.ic`, `.nodeset`, raised `itl1`, a named parameter that selects a branch) are **simulation scaffolding**, not physical claims. Document them as such and do not describe the aided start-up as the hardware's power-on behaviour.
- After a model change, test whether each aid is still required; keep it as a conservative safeguard only if it costs nothing and is documented.

## Multiple Engines And Versions

- A schematic tool's bundled simulator is often an older version than the command-line one. Run both on the same decks and compare.
- Library engines embedded in GUIs may need extra code models loaded (XSPICE/`POLY` support); a missing code model looks like a parse error, not a missing feature.
- Record the exact version string of each engine in every report. A result validated in one engine is not automatically valid in another.

## Checklist

- [ ] Per-metric timestep/tolerance convergence recorded, criterion declared, hardest cases included.
- [ ] Solver, tolerances, method, TMAX, compatibility mode and temperature recorded and pinned.
- [ ] Operating point verified before every AC result; intended state asserted, not assumed.
- [ ] `.ic`/`.nodeset`/`itl1` aids documented as scaffolding and retested after changes.
- [ ] Order stress: unique keyed orders, matched across engines, failures and wrong states counted separately.
- [ ] Every engine version that will be used (CLI and GUI) exercised on the same decks.

## Sources

- The ngspice User's Manual for the pinned version (https://ngspice.sourceforge.io/docs.html): `.options` (`itl1`, `itl4`, `reltol`, `abstol`, `vntol`, `gmin`, `method`, `klu`), `.ic` versus `.nodeset`, gmin and source stepping, and compatibility modes (`ngbehavior` in `.spiceinit`). Option names and defaults change between versions; check the manual that matches the pinned simulator.
- L. W. Nagel, *SPICE2: A Computer Program to Simulate Semiconductor Circuits*, UC Berkeley ERL Memo M520, 1975: Newton iteration, junction voltage limiting and timestep control that SPICE descendants still use.
