# Circuit Reference Validation

## Contents

- Scope, evidence, and fidelity target
- Verify the reference circuit
- Match the measurement contract
- Progress from simple to combined behavior
- Compare equivalent stages
- Align signals and interpret metrics
- Isolate the mismatch
- Correct, preserve, and regress
- Automate and report

## Scope, Evidence, And Fidelity Target

Use a schematic-derived executable reference to validate analog-inspired amp, preamp, pedal, EQ, filter, clipping, dynamics, or power-stage DSP. SPICE is one source of engineering evidence, not unquestioned ground truth. Agreement depends on the source drawing, transcription, device models, simulator configuration, loading, and assumptions.

The workflow is:

```text
source schematic -> verified circuit reference -> matched measurements
  -> stage comparison -> mismatch attribution -> isolated correction -> regression
```

Define the target first: nominal circuit behavior, a measured hardware specimen, or an intentionally simplified musical approximation. Set acceptable errors for the behavior that matters; do not demand exact harmonic parity from a deliberately coarse model.

Establish the source hierarchy for this task. Use the original schematic and service manual to identify revision/topology, manufacturer notes for device limits, verified component information for values, and calibrated hardware measurements for the specimen's behavior. Verified analysis can resolve ambiguity; existing DSP constants are implementation assumptions until independently supported. Hardware measurements do not silently redefine another circuit revision.

Keep provenance with consequential values, connections, and boundary choices:

| Label | Record |
| --- | --- |
| DOCUMENTED | Source, drawing revision/page, annotation or component listing |
| MEASURED | Specimen, setup, units, calibration, controls, and uncertainty |
| INFERRED | Evidence and reasoning; unresolved alternatives |
| ASSUMED | Missing information, chosen approximation, and sensitivity to it |
| SIMULATOR-SPECIFIC | Model/dialect behavior, numerical workaround, and its scope |

Retrace junctions and ambiguous labels visually; a parts inventory alone does not establish connectivity. Do not invent missing values, silently substitute another revision, or combine incompatible variants. Expose behaviorally significant uncertainties as reference parameters or documented alternatives, without automatically adding product UI controls.

## Verify The Reference Circuit

Convergence proves numerical completion, not correct wiring. Before using a circuit as a regression reference, check:

- Stage order, connectivity, junctions, grounds, device pin order/orientation/polarity, and signal return paths.
- Component values/units, coupling and bypass capacitors, intentional small capacitors/parasitics, bias networks and supply rails.
- Pot wipers, strapped terminals, endpoint resistances, switch/push-pull states, jack normal contacts, and inactive branches.
- Source/load termination, grid/gate/base resistors, input attenuation, interstage/pot loading, and cathode/source/emitter degeneration.
- Local/global feedback paths, sign, sensing point, output tap, and connected load.
- Device-model family, revision, units, temperature/defaults, applicability to bias/current/headroom, and omitted behavior.

For active circuits, inspect the DC operating point: quiescent voltages/currents, bias, device regions, supply drops, and available swing. A familiar device name does not guarantee an equivalent operating point. For passive sections, independently check limiting cases such as DC, mute, divider ratios, and loading.

Validate simulator behavior with a minimal subcircuit when an element gives surprising results. Compare small-signal AC with a settled, sufficiently small transient sine at the same bias. Verify static switch states in both analyses. A documented static equivalent can help isolate a switch-model problem; it cannot validate switching transients.

Check numerical sensitivity where it could change the conclusion:

- Reduce transient maximum step and tighten tolerances until the relevant metrics stabilize. Output sample spacing is not necessarily the internal integration step.
- Record integration method and assess its damping; investigate artificial ringing or suppressed dynamics before retuning DSP.
- Inspect convergence aids, conductance/leakage paths and resistor floors for unintended loading, especially near open circuits and control endpoints.
- Verify initialization, capacitor charge, settling, temperature and device defaults. An ideal source can remove real pickup/interstage loading.
- Reject missing/nonfinite data, incomplete time windows, singular-node failures and failed analyses even if the process exits successfully.

A bounded overload run establishes behavior only over that interval. Do not label long-term stability, settling or recovery as verified when a longer simulation timed out. Do not loosen tolerances merely to obtain a passing match.

## Match The Measurement Contract

Record one explicit contract per fixture; convert both systems to it before computing errors.

| Field | Align or declare |
| --- | --- |
| Stimulus | Deterministic waveform, frequency/content, phase, amplitude, seed where needed |
| Units | Volts/amperes/normalized samples, peak versus RMS, dB reference and digital-to-physical calibration |
| Boundary | Source impedance, output load, tap/port, electrical versus acoustic output, downstream loading |
| Runtime | Host rate, each oversampled stage rate, filters, block size, precision, channel layout/routing |
| Simulation | Simulator/device-model versions, analysis type, temperature, integration method, tolerances, maximum step |
| State/time | Initialization/reset, warm-up, settling, measurement start/end, DC treatment, window and resampling |
| Controls | Physical position, electrical taper/wiper travel, DSP mapping, switches, shared/interacting controls |
| Calibration | Input/output trims, any normalization or compensation, and deliberately excluded subsystems |

For a sine, `V_rms = V_peak / sqrt(2)`. For digital input, declare a calibration such as `V = C_V * x`; do not assume one normalized sample equals one volt. State the dBFS peak/RMS convention. A 1-unit AC source is a linearized analysis excitation, not evidence that a 1-unit transient remains linear.

Keep absolute gain visible. Equal input voltage, equal internal-stage drive and equal final output level answer different questions; label them separately. Matching final RMS cannot establish equal clipping-stage excitation. Never divide unrelated internal calibration constants without showing that their units and measurement boundaries correspond.

Control mapping belongs in the circuit model: verify linear/log/reverse-log taper, wiper orientation, endpoint resistance, rheostat versus divider wiring, adjacent loading, switch topology, parameter scaling and minimum/maximum behavior. Matching panel labels is insufficient. If the physical taper is unknown, label the comparison mapping as an assumption.

Use a compact operating grid: endpoints, low-mid, center, high-mid and maximum for relevant controls; selected Cartesian combinations for interactions; multiple input levels for nonlinear stages; multiple rates for rate-sensitive code; and relevant channels/switch states. Expand around observed failures rather than exhaustively testing irrelevant combinations. One centered preset is not acceptance evidence for the whole model.

## Progress From Simple To Combined Behavior

Choose fixtures for specific questions; use the following order where applicable.

| Gate | Fixture | Evidence before moving on |
| --- | --- | --- |
| DC / operating point | Idle and bias/control cases | Plausible bias, quiescent current/voltage, headroom and termination |
| Small signal | Logarithmic sweep, or suitable low-level multitone/impulse | Magnitude, phase where relevant, insertion gain/loss, corners, shelves, resonances, group delay |
| Controls | Representative control grid at small signal | Taper, endpoints, switch branches and interaction behave as intended |
| Large signal | Stepped sine amplitude; static sweep where meaningful; two-tone probe when needed | Transfer shape, peak/RMS, gain compression, clipping onset/asymmetry, harmonic spectrum/THD, even/odd balance, DC/bias shift, intermodulation |
| Memory | Bursts, amplitude steps, low-frequency overload, repeated transients, silence after overload | Charge/discharge, bias movement, bypass dynamics, sag, attack/release, blocking and recovery; hysteresis-like/load dynamics when modeled |
| Combined system | Same deterministic probes plus controlled guitar renders | Stage interactions, musical behavior, existing routing/host contracts and adjacent operating regions remain acceptable |

Confirm the small-signal regime by reducing the transient/DSP amplitude and checking gain invariance. Stay above quantization, LUT and measurement noise floors. AC analysis linearizes about a bias point and cannot predict large-signal clipping or recovery. A finite-amplitude transient is not automatically a small-signal transfer measurement.

Use enough logarithmic sweep points to resolve response shape; refine densely around resonances, notches or delay combs. A few spot frequencies are useful regression anchors after characterization, not a substitute for it. Evaluate phase/group delay only where magnitude and signal-to-noise support a meaningful estimate.

Static transfer curves cannot validate memory. Design the burst or step to expose the relevant state, and measure that state directly when available. For a compressor, inspect sidechain detector/control voltage as well as audio gain reduction; for an uncertain mechanical/transducer model, isolate its electrical drive/recovery interfaces instead of treating the entire approximation as a fidelity target.

## Compare Equivalent Stages

Add offline checkpoints at meaningful boundaries: input network, gain stage, coupling filter, tone network, clipping stage, degeneration/feedback network, master/output network, power approximation and speaker/cabinet interface. Compare upstream to downstream to find the first discrepancy.

- Reuse the actual production DSP implementation and normal processing path. Preserve parameter initialization, smoothing, oversampling and channel state; a separately rewritten formula does not verify that path.
- Keep taps observational. In a deterministic build, compare instrumented and uninstrumented final output, preferably sample-bit hashes, to catch changed processing. This is a harness check, not a requirement for SPICE/DSP bit identity.
- Map each tap's units, polarity, rate, loading and included filters. An unloaded stage output is not the same node as a loaded circuit terminal; an output after a lumped coupling filter is not a raw device electrode. Inactive or crossfaded branches may also differ.
- Isolate subsections with equivalent source/load impedance and bias. Bypassing a branch may remove loading; preserve that load or label the experiment's altered boundary. Shared supplies and feedback can make upstream stages depend on downstream settings.
- Check passive feedback impedance separately from complete closed-loop behavior. Matching passive values does not prove matching loop gain, operating point, saturation or transformer/load response.

If upstream waveforms already differ, inject the same signal into a downstream stage under matched conditions before attributing its output difference to that stage's nonlinearity. Whole-chain ratios are diagnostic clues, not proof of an isolated device defect.

## Align Signals And Interpret Metrics

Before RMSE, ESR, correlation or a null test, verify polarity, lag, gain reference, DC offset, settling and the exact analysis window. Estimate lag with an unambiguous fixture; a periodic sine can admit several equivalent lags. Report removed delay and preserve physical phase/group-delay differences when those are the subject of the test.

SPICE transient timestamps can be nonuniform. Integrate using actual time intervals or resample to a common uniform grid with a documented interpolation/anti-alias policy. Do not FFT an adaptive trace as though its rows were evenly spaced. Clip/interpolate exact analysis-window boundaries. Retain and report DC/bias separately; remove the window's time-weighted DC before AC/harmonic quadrature so a large bias does not leak into estimated harmonics. Do not subtract DC when DC movement is the quantity being tested.

When converting an analog/reference transient to the DSP sample rate, define the observation bandwidth and apply an appropriate anti-alias filter before decimation. Report in-band agreement separately from out-of-band harmonic generation. Do not let reference resampling create alias products and then attribute them to the DSP.

Useful metrics include:

```text
gain_error_db(f) = 20 * log10(|H_dsp(f)| / |H_ref(f)|)
THD = sqrt(sum(|A_h|^2, h = 2..H)) / |A_1|
```

Declare harmonic range, analysis bandwidth, coherent-window length or window correction, and noise floor. Exclude unresolvable harmonics and mark muted/below-floor reference points as such instead of dividing by zero or presenting an arbitrary dB floor as a measurement. Compare matched absolute metrics first; optional gain-normalized shape metrics must retain the fitted gain error. Independent normalization can conceal the defect being diagnosed.

Separate discretization correctness from physical-frequency fidelity. For a bilinear implementation, its digital frequency `f` corresponds to analog frequency `f_a = (f_s / pi) * tan(pi * f / f_s)`, using that block's actual processing rate. A warped-frequency reference can verify the solver; a same-physical-frequency comparison exposes the remaining warping and bandwidth error. Label which is being tested; do not hide audible-band error through undocumented prewarping.

## Isolate The Mismatch

First identify its owner: **schematic interpretation, reference model, harness, DSP, intentional approximation, or unresolved evidence**. Fix the earliest responsible boundary, not its downstream symptoms.

| Symptom | Check before retuning |
| --- | --- |
| Broadband gain error | Unit/calibration conversion, source/load impedance, insertion loss, stage gain, tap location and normalization |
| Response shape/corner error | RC values and topology, omitted loading/coupling/bypass, control law, transform and coefficient normalization |
| Wrong control curve/endpoints | Taper, wiper direction, endpoint floors, rheostat/divider mapping, switch branches, shared controls |
| Nonlinear mismatch | Equal internal drive, operating point/headroom, device-model suitability, transfer knee/asymmetry, interstage loading and memory |
| Dynamic mismatch | Missing state, charge/recovery time constants, smoothing, initialization, solver/integration behavior |
| High-frequency mismatch | Aliasing/oversampling filters, bilinear warping/discretization, parasitics, simulation step, FFT/window/resampling errors |
| Low-frequency/DC mismatch | Coupling/bypass network, bias shift, DC blocker, insufficient settling and reset behavior |
| Rate/block-dependent mismatch | Stale rate or coefficients, normalization/stability, prewarping, float precision, state reset, sample/control-rate updates and topology-preserving transform implementation |

Change one suspect component, connection, mapping or boundary in a temporary reference/DSP variant while holding the rest fixed. Predict its direction and affected stages first. If the measured change explains only part of the discrepancy, retain the remainder as unresolved. Sensitivity experiments support attribution; they do not automatically establish physical accuracy.

Check global feedback, bias and loading before compensating an upper-frequency discrepancy with arbitrary EQ. Avoid chains of compensating errors: establish topology and measurable stage behavior before repeatedly tuning gain/EQ by ear.

## Correct, Preserve, And Regress

Apply the smallest responsible correction. Preserve realtime architecture, parameter IDs, host state, smoothing, routing, latency contract, accepted musical calibration and existing tests unless the diagnosed change requires otherwise. Prototype broader network changes offline before replacing accepted behavior.

For an intentional approximation, record what differs, why (CPU, stability, aliasing, smoothness, portability or musical tuning), measured effect, expected audible effect, acceptable range and regression criterion. Do not repeatedly rediscover it as a bug, or relabel an unexplained error as intentional after the fact.

After a confirmed mismatch matters to the target:

1. Add the smallest practical regression that fails before the correction and passes after it: e.g. loaded response, control endpoint, stage gain, attenuation, bias, harmonic growth, coupling corner or feedback behavior.
2. Keep expected data independent of the implementation. A different solver sharing the same mistranscribed values cannot catch that transcription error. Capture compact results from the separately verified reference and retain their provenance/regeneration recipe.
3. Set tolerances from fidelity goals, numerical uncertainty and relevant band/control range. Use gain/corner/control-curve, harmonic, peak/RMS, bias or timing errors as appropriate; there is no universal tolerance or cross-simulator bit-identity requirement.
4. Rerun the affected grid, existing DSP/processor regressions, and aliasing/rate checks when drive or bandwidth changed. Check nearby operating regions and shared paths.
5. Audition controlled musical fixtures against the previous accepted build, preserving input drive and documenting listening-level compensation. Report measurements and listening outcomes separately. One graph does not establish better tone; an uncontrolled loudness comparison does not invalidate an isolated correction.

Separate nominal circuit matching from expected hardware variation. Where useful, sweep resistor/capacitor/pot tolerance, device gain/model and supply voltage. Do not use tolerance spread to excuse a wrong nominal implementation. Triangulate schematic, validated circuit reference, measured hardware and listening when available; disagreement with hardware calls for investigating assumptions and specimen variation, not automatically forcing DSP toward SPICE.

## Automate And Report

Keep simulator execution, file parsing, allocation, plots and heavy measurement offline in tests, analysis executables or scripts. None belongs in the production audio callback. Follow [validation-and-release.md](validation-and-release.md) for runtime and host gates.

Reuse existing harnesses before extracting another tool. A repeatable harness should generate deterministic stimuli/control cases, run or load versioned reference results, run actual DSP, validate outputs, align/analyze them, emit tables/plots and machine-readable results, and return failures for breached tolerances. Record failures/timeouts as failures, not missing rows in a passing report. Keep originals immutable and name controlled variants explicitly.

Store only the compact operating points, response tables, selected transient traces or harmonic summaries needed for regression, with source/netlist/device-model revisions, simulator/settings, DSP revision/build, stimulus/control configuration, units and regeneration command. Avoid committing large raw runs by default.

The existing [compare_audio_metrics.py](../scripts/compare_audio_metrics.py) can compare calibrated PCM WAV renders for lag, polarity, residual and DC metrics; it averages multichannel files to mono. Use separate channel renders when testing channel differences. It does not establish circuit-node equivalence or parse adaptive SPICE traces. Extract a new helper only when its inputs/units are explicit, its ports/controls are parameterized, deterministic tests are available, and it runs without proprietary project files or build-specific paths.

A useful report has these fields:

| Field | Required evidence |
| --- | --- |
| Reference | Schematic/version, netlist revision, simulator/device models, provenance and assumptions |
| Conditions | Stimulus/units, source/load, controls, rates/step, initialization/window and alignment/calibration |
| Result | Stage/control/level-specific differences, metrics/plots, tolerance and uncertainty |
| Diagnosis | First divergent boundary, likely owner, isolating experiment and remaining alternatives |
| Change | DSP, circuit, transcription or harness correction; before/after evidence |
| Status | Resolved, intentional difference, unresolved uncertainty, or untested scope |
| Regression | Runnable check and reference provenance, or why no practical check was added |

State the remaining experiment needed to resolve uncertainty. Keep future recommendations separate from changes and tests actually performed.
