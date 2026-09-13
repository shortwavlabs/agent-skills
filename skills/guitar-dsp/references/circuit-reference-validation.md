# Circuit Reference Validation

## Contents

- Scope, evidence, and fidelity target
- Verify the reference circuit
- Match the measurement contract
- Progress from simple to combined behavior
- Qualify supplies, loads, and effects
- Compare equivalent stages
- Align signals and interpret metrics
- Isolate the mismatch
- Correct, preserve, and regress
- Automate and report
- Release integrity and versioning
- Escalate to hardware measurements
- Readiness checklist

## Scope, Evidence, And Fidelity Target

Use a schematic-derived executable reference to validate analog-inspired amp, preamp, pedal, EQ, filter, clipping, dynamics, or power-stage DSP. **A circuit reference is not hardware ground truth.** A schematic-derived model can become a frozen **IMPLEMENTATION REFERENCE** for fitting/testing DSP without becoming a verified model of a physical specimen. Keep schematic fidelity, simulator correctness, numerical convergence, published-spec comparison, calibrated assumptions, external hypotheses and measured hardware truth separate. Agreement depends on the source drawing, transcription, device models, simulator configuration, loading, and assumptions.

The workflow is:

```text
source schematic -> verified circuit reference -> matched measurements
  -> stage comparison -> mismatch attribution -> isolated correction -> regression
```

Define the target first: nominal circuit behavior, a measured hardware specimen, or an intentionally simplified musical approximation. Set acceptable errors for the behavior that matters; do not demand exact harmonic parity from a deliberately coarse model.

Use this preferred source order when reconstructing a documented design:

1. Original schematic / factory service documentation.
2. Original BOM / board layout / factory test table.
3. Original owner's manual / published specifications.
4. Manufacturer semiconductor/component documentation.
5. Photographs of actual hardware/components.
6. Credible repair/technical sources.
7. Modern replacement-component documentation.
8. Forum/community reports.
9. Inference.

Lower-tier evidence must not silently override higher-tier material. Calibrated hardware measurements establish the measured specimen's behavior, with setup and uncertainty; they do not silently redefine another revision or prove original factory intent. Existing DSP constants are assumptions until independently supported.

Preserve source problems: reversed table headings, ambiguous test-point units, undocumented generator amplitude/impedance, incomplete switching/loading conditions, duplicate designators, inconsistent pin numbering and sibling-model revision differences. For a suspected typo, retain both `LITERAL_SOURCE_TARGET` and `TYPO_HYPOTHESIS`, with evidence for each. Do not silently replace the printed target or merge sibling schematics without demonstrated revision compatibility.

Keep provenance with consequential values, connections, and boundary choices:

| Label | Meaning and required record |
| --- | --- |
| DOCUMENTED | Direct support from schematic, BOM, service/factory table or manufacturer documentation; cite revision/page |
| SOURCE_COMPARISON | Simulation compared with a published source target; agreement alone is not independent validation |
| MEASURED | Actual specimen, setup, units, calibration, controls and measurement uncertainty |
| INFERRED | Evidence and reasoning; unresolved alternatives |
| ASSUMED | Required physical parameter absent from sources; chosen value and sensitivity |
| CALIBRATED | Parameter deliberately fitted/chosen to meet a target; record target, method and fitted value |
| APPROXIMATE | Reduced behavioral representation; state omitted circuitry and applicable range |
| HYPOTHESIS | Plausible external-research value/model, not established as original hardware |
| SENSITIVITY | Dependence of results on uncertain parameters; not proof of their actual values |
| SIMULATOR-SPECIFIC | Model/dialect behavior or numerical workaround and its scope |
| PASS_IMPLEMENTATION | Structure/software behaves according to its specified contract |
| PASS_NUMERICAL | Metrics stabilize within declared numerical criteria for the stated fixture |
| UNRESOLVED_HARDWARE | Requires physical measurement to resolve responsibly |
| FAIL | A declared qualification criterion failed; preserve the failed evidence |

Evidence labels and qualification outcomes are different axes: a `HYPOTHESIS` may receive `PASS_NUMERICAL` while remaining `UNRESOLVED_HARDWARE`. Never collapse these into generic PASS or one global accuracy percentage.

Retrace junctions and ambiguous labels visually; a parts inventory alone does not establish connectivity. Do not invent missing values, silently substitute another revision, or combine incompatible variants. Expose behaviorally significant uncertainties as reference parameters or documented alternatives, without automatically adding product UI controls.

## Verify The Reference Circuit

Convergence proves numerical completion, not correct wiring. Before using a circuit as a regression reference, check:

- Stage order, connectivity, junctions, grounds, device pin order/orientation/polarity, and signal return paths.
- Component values/units, coupling and bypass capacitors, intentional small capacitors/parasitics, bias networks and supply rails.
- Pot wipers, strapped terminals, endpoint resistances, switch/push-pull states, jack normal contacts, and inactive branches.
- Source/load termination, grid/gate/base resistors, input attenuation, interstage/pot loading, and cathode/source/emitter degeneration.
- Local/global feedback paths, sign, sensing point, output tap, and connected load.
- Device-model family, revision, units, temperature/defaults, applicability to bias/current/headroom, and omitted behavior.

### Trace First, Tune Later

Do not alter traced non-adjustable R/C/L values to hit published gain, tone or power numbers. Investigate stimulus definition, source impedance, pot position/taper, switches, loading, normalled jacks, missing control circuitry, omitted semiconductor behavior, supplies, device tolerances/models, ambiguous documentation, then specimen variation. Only correct a traced value/connection when evidence establishes a transcription error; deliberately changed designs belong in separately named variants.

Every traced-source correction requires a `SOURCE CORRECTION` entry: old value/connection, new value/connection, schematic page, component identifier and evidence/reason. Lower factory error is not that evidence.

For active circuits, inspect the DC operating point: quiescent voltages/currents, bias, device regions, supply drops, and available swing. A familiar device name does not guarantee an equivalent operating point. For passive sections, independently check limiting cases such as DC, mute, divider ratios, and loading.

Validate simulator behavior with a minimal subcircuit when an element gives surprising results. Compare small-signal AC with a settled, sufficiently small transient sine at the same bias. Verify static switch states in both analyses. A documented static equivalent can help isolate a switch-model problem; it cannot validate switching transients.

Check numerical sensitivity where it could change the conclusion:

- Reduce transient maximum step and tighten tolerances until the relevant metrics stabilize. Output sample spacing is not necessarily the internal integration step.
- Record integration method and assess its damping; investigate artificial ringing or suppressed dynamics before retuning DSP.
- Inspect convergence aids, conductance/leakage paths and resistor floors for unintended loading, especially near open circuits and control endpoints.
- Verify initialization, capacitor charge, settling, temperature and device defaults. An ideal source can remove real pickup/interstage loading.
- Reject missing/nonfinite data, incomplete time windows, singular-node failures and failed analyses even if the process exits successfully.

A bounded overload run establishes behavior only over that interval. Do not label long-term stability, settling or recovery as verified when a longer simulation timed out. Do not loosen tolerances merely to obtain a passing match.

### Numerical Convergence And Threshold Searches

Numerical qualification is an independent gate. For nonlinear transients, compare coarse/fine/finer maximum timesteps and inspect both refinement pairs against declared limits. Select steps and tolerances for the circuit and metric; no one project's values are universal. Report quantity, units, absolute/relative criterion and denominator floor.

Power/supply fixtures may need crossing input, power, THD, rail mean/extrema/ripple, average/peak rectifier current, conduction duty and reservoir recharge timing. Measure reservoir recharge from its own current, not automatically from diode conduction. Define current thresholds and event interpolation. Switching/detector fixtures need transition count/timing, oscillation frequency, amplitude and envelope extrema. Preserve chatter and determine whether it survives refinement; nonconverged transitions remain `NUMERICAL / UNQUALIFIED`. A finite-time ascending/descending difference alone does not establish static hysteresis.

For a threshold metric such as first 5%-THD power, independently run:

```text
ascending coarse samples -> first sampled upward bracket -> bisection/refinement
```

Repeat the search at each timestep with its own samples and trace. Reusing one coarse crossing at all steps tests fixed-drive metrics, not crossing convergence. Retain coarse points, bracket, stopping tolerances, selected input and threshold residual; identical selected inputs can reflect search resolution, so inspect traces before claiming searches were shared. Do not assume global monotonicity. Test synthetic nonmonotonic/multiple-crossing cases, exact hits, no bracket and invalid values. State that finite sampling cannot exclude an arbitrarily narrow unsampled excursion between grid points.

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

### Electrical Versus Panel Pot Position

Control mapping belongs in the reference contract. Verify linear/audio-log/reverse-audio classes, wiper orientation, strapped terminals, rheostat/divider wiring, adjacent loading, switches and endpoint resistance. A normalized electrical position of .5 is not automatically panel position “5.” Preserve documented taper classes without assuming one universal audio curve.

Keep `ELECTRICAL` mode as raw 0..1 electrical travel for debugging/regression and `PANEL` mode as mechanical position mapped through an explicit profile. Provide named nominal profiles, per-pot midpoint overrides and replaceable measured LUTs where controls affect the reference. Test exact endpoint behavior, monotonicity and invalid/nonfinite or partial LUT inputs; disclose any numerical resistance floors. Nominal tapers are hypotheses. Use an ensemble/sensitivity study for unmeasured controls rather than selecting the lowest factory error. Valid wiper measurements for the relevant control supersede nominal priors; preserve their measurement provenance.

Use a compact operating grid: endpoints, low-mid, center, high-mid and maximum for relevant controls; selected Cartesian combinations for interactions; multiple input levels for nonlinear stages; multiple rates for rate-sensitive code; and relevant channels/switch states. Expand around observed failures rather than exhaustively testing irrelevant combinations. One centered preset is not acceptance evidence for the whole model.

### Factory Test Points And Calibration

Service-manual test points constrain internal stages more directly than headline gain/power specifications. At each available point record Vpp, DC offset, polarity/phase where meaningful, clipping shape/class, stimulus frequency, controls, switch state, source impedance and expected load. Preserve unknown conditions explicitly.

If generator amplitude is missing, do not fit every stage independently. If necessary infer one common input from a defensible reference point and label it `CALIBRATED`; also compare ratios such as TP2/TP1 or TP3/TP2 that cancel common input amplitude in the linear regime. For nonlinear stages, retain the input-level dependence of those ratios. The point used for calibration is no longer independent validation of that calibration.

Reports must structurally separate **SOURCE TARGET**, **CALIBRATION TARGET**, **INDEPENDENT VALIDATION**, and **SENSITIVITY / HYPOTHESIS**. Record which parameters were fitted to which targets and which conditions were withheld. A fitted factory number, the same formula on both sides, or a model acting as its own oracle cannot establish independent validity. Unfitted source comparisons still depend on the completeness and quality of the source contract.

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

## Qualify Supplies, Loads, And Effects

Apply these boundaries when the circuit contains the relevant subsystem; they are not requirements to add unsupported realism to every pedal or preamp.

### Supply And Electrical Load Boundaries

Retain a deterministic reference supply even when adding realism. Useful modes are `IDEAL` rails, `SIMPLE SAG / THEVENIN` approximate rail impedance, and `PHYSICAL_PROXY` transformer equivalent + rectifier + reservoir capacitors. The last is a hypothesis until secondary voltage, regulation and winding resistance are measured. Evaluate one/both channels driven where applicable, relevant phase relationships and multiple loads. Use uncertainty envelopes; do not infer a transformer by optimizing until manual wattage agrees.

Preserve speaker-return/current-feedback sensing and actual output/return connections. A resistor-only comparison does not qualify a current-sensing amp under reactive loads. Distinguish:

| Load | Use and evidence |
| --- | --- |
| Pure resistance | Canonical implementation fixture with explicit terminals/value |
| Generic reactive electrical load | Sensitivity fixture; assumptions visible |
| Speaker-specific impedance | Measured data or credible component impedance evidence; identify specimen/model and scope |

Keep electrical load separate from acoustic cabinet/IR response. Never fabricate measured impedance from a marketing acoustic response plot. If only Re/Fs or similar anchors are sourced, separate **DOCUMENTED ANCHORS**, **ASSUMED PARAMETERS** and **COMPUTED MODEL OUTPUT**. Sweep uncertain Re/Le/resonance/Q terms, especially with current feedback. Neighboring cabinet-DSP approximations are product options, not evidence of the amplifier's electrical load.

### Nonlinear Devices And Research Priors

Prioritize devices by their effect on the circuit: clipping diodes/zeners, op-amp swing/current/common-mode limits, power-stage devices, then secondary protection behavior are a useful starting order, not a universal ranking. Tube bias/grid-current or magnetic behavior may dominate another circuit. Check operating range before adding detail.

A generic family designation does not establish an exact OEM model. Use documented family limits, nominal priors and low/high sensitivity envelopes when manufacturer/specimen is unknown. Historical manufacturer curves remain `HYPOTHESIS` priors for an unidentified original device. For digitized graphs, retain CSV points, source/revision and source hash, graph-reading uncertainty and fit residuals; do not imply more precision than the plot supports.

### Core Path, BBD Transport, And Spring Boundary

Keep a named core path separable: input -> gain/nonlinear stages -> tone -> level -> relevant buffer/mixer -> power stage -> electrical load, omitting blocks absent from the design. Preserve effects loading while audibly bypassed when the hardware does. An uncertain spring/BBD block need not prevent freezing the audited core.

Trace analog BBD input/output filters and control circuitry in SPICE; separate DSP transport can be more useful than an expensive artificial SPICE delay. Derive delay from clock and documented stage/clock-phase relationships. Distinguish slow LFO rate, oscillator frequency and the clock actually reaching the BBD; expose overclock/underrange instead of silently clamping the reference. Keep CMOS thresholds/parasitics and uncertain endpoints explicit. Production protection may differ under a separately declared contract.

Qualify fractional-delay magnitude, phase/delay and modulation sidebands at intended production rates. Interpolation that passes at a high offline rate does not automatically pass at 44.1/48 kHz. A high-rate model can be an **EQUIVALENCE REFERENCE** without prescribing the production algorithm.

Spring-tank impedance classes normally describe AC impedance, not literal DC coil resistance. Treat a candidate replacement pan as a hypothesis; use impedance/decay constraints while keeping DCR, inductance and coupling uncertainty visible. Do not retune factory drive/recovery circuitry to fit one point. Test identifiability: if one diagnostic coupling scalar matches one channel, does it predict the other channel or withheld conditions? If not, a scalar has not identified the boundary; retain alternative pan/drive/recovery hypotheses or an inadequate approximation as unresolved. Report the diagnostic without applying it merely because one comparison improves.

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

### Freeze The Core And Name The Fitting Profile

Freeze reusable audio topology once schematic connectivity/values, major switching/jack routing and repeatable core validation are audited. Further work should qualify uncertainty, numerical behavior and release integrity rather than endlessly refit topology. Reopen the model for an evidenced transcription error, newly acquired factory source, physical measurement or genuine numerical/modeling defect; document why. An assumed transformer, speaker, taper or effect missing a published target is not sufficient cause.

Name one canonical fitting configuration and specify channel, source impedance, electrical/panel pot profile, control mode, device profile, PSU mode, effects/loading state, load terminals/type, input levels and sample/test frequencies. Choose stability and auditability, not the hypothesis with the smallest manual error. Ideal rails and a resistor can be appropriate; test uncertain physical profiles separately.

Track reusable-library identity separately from complete-deck identity: an unchanged audio subcircuit does not imply an unchanged demonstration/fixture deck. State exactly which files/regions and versions match. Use byte identity for an intentionally frozen library; do not silently ignore semantic edits through convenient normalization.

### Golden Captures And Drift

For the frozen fitting profile, retain self-describing captures over representative frequencies, controls, linear/nonlinear amplitudes and important internal probes. Store raw adaptive timestamps/voltages, units, full configuration, source impedance, dependency hashes, simulator identity, requested windows and harmonic summaries. Keep enough preceding settling history to independently verify the selected window; normalized plots or summary numbers alone are insufficient.

Reconstruct summaries from raw data with an independent analysis implementation, respecting adaptive time intervals and metric floors. Missing prior history is an explicit audit limitation, not proof of settling. Retain the bounded golden capture needed for this audit, optionally compressed, rather than every exploratory run.

Declare drift limits for small-signal fundamental dB, nonlinear Vpp %, critical DC bias, harmonic levels above a floor and phase where resolvable. Distinguish implementation drift from intentional model change. Maintenance should preserve model behavior; identical capture and measurement code under the same numerical runtime should yield zero metric drift. Do not impose cross-simulator bit identity or loosen golden limits to hide a failure. A changed frozen topology requires a model/source change entry and requalification.

## Automate And Report

Keep simulator execution, file parsing, allocation, plots and heavy measurement offline in tests, analysis executables or scripts. None belongs in the production audio callback. Follow [validation-and-release.md](validation-and-release.md) for runtime and host gates.

Reuse existing harnesses before extracting another tool. A repeatable harness should generate deterministic stimuli/control cases, run or load versioned reference results, run actual DSP, validate outputs, align/analyze them, emit tables/plots and machine-readable results, and return failures for breached tolerances. Record failures/timeouts as failures, not missing rows in a passing report. Keep originals immutable and name controlled variants explicitly.

Keep routine regressions compact: operating points, response tables, selected traces and harmonic summaries with source/device revisions, settings, configuration, units and regeneration command. For a frozen release, also retain the bounded raw golden capture and settling history required for independent reconstruction above. Archive large exploratory runs only when their evidence is needed; do not create redundant captures for documentation or checksum changes.

The existing [compare_audio_metrics.py](../scripts/compare_audio_metrics.py) can compare calibrated PCM WAV renders for lag, polarity, residual and DC metrics; it averages multichannel files to mono. Use separate channel renders when testing channel differences. It does not establish circuit-node equivalence or parse adaptive SPICE traces. Extract a new helper only when its inputs/units are explicit, its ports/controls are parameterized, deterministic tests are available, and it runs without proprietary project files or build-specific paths.

### Qualification Failures And Tiers

Never use Python `assert` for qualification-critical behavior: optimization removes it. Use explicit exceptions, for example `ValidationError(RuntimeError)` and `require(condition, message)`. Reject simulator nonzero exit and error text even on zero exit, missing output, malformed columns, NaN/Inf, incomplete windows, failed criteria, missing artifacts, checksum mismatch and dependency mismatch. Record timeout/partial work as incomplete or FAIL, never as a silently omitted passing case.

Add deliberate failure probes under normal Python, `python -O` and `PYTHONOPTIMIZE=1`; prove each invalid condition remains rejected. This is a failure-path test, not just three successful runs of valid input.

Scale execution with tiers such as:

| Tier | Scope |
| --- | --- |
| QUICK | Syntax, routing, DC sanity, one nonlinear trace |
| STANDARD | Core schematic/manual/test-point regression |
| FULL | Nonlinear spectra, power/effects/loads and numerical convergence |
| RESEARCH | Explicit hypothesis/sensitivity ensembles |
| RELEASE | Required freeze/publication checks, provenance, raw-capture audits, corruption and artifact verification; reuse qualified results when justified |

Run affected checks first and expand around failures. Tier names do not justify skipping a declared acceptance gate or claiming retained results as fresh simulations.

A useful report has these fields:

| Field | Required evidence |
| --- | --- |
| Reference | Schematic/version, netlist revision, simulator/device models, provenance and assumptions |
| Conditions | Stimulus/units, source/load, controls, rates/step, initialization/window and alignment/calibration |
| Result | Stage/control/level-specific differences, metrics/plots, tolerance and uncertainty |
| Diagnosis | First divergent boundary, likely owner, isolating experiment and remaining alternatives |
| Change | DSP, circuit, transcription or harness correction; before/after evidence |
| Status | Evidence label plus PASS_IMPLEMENTATION, PASS_NUMERICAL, UNRESOLVED_HARDWARE or FAIL as applicable; state intentional differences and untested scope separately |
| Regression | Runnable check and reference provenance, or why no practical check was added |

State what each result establishes and its limits. Prefer “topology passes implementation regression; PSU metrics converge under an unmeasured transformer hypothesis” over “the model is validated.” Prefer “reactive-load sensitivity evaluated; actual cabinet impedance unresolved” over “speaker validated.” State the remaining experiment needed to resolve uncertainty. Keep future recommendations separate from changes and tests actually performed.

## Release Integrity And Versioning

Use these gates when publishing/freezing reusable scientific results; ordinary exploratory fixtures need not acquire a release framework.

### Artifact Graph And Reusable Results

For each released payload record path, role, byte size and SHA-256. Separate relationships:

| Relationship | Meaning |
| --- | --- |
| Scientific dependency | Input bytes that can change the numerical/scientific result |
| Render dependency | Input required to generate a report or plot |
| Verification dependency | Required for integrity/archive checks, without asserting scientific causation |
| Bundle membership | Required release file, without causal implication |

Document edge direction, for example `derived artifact -> required input`. Require scientific + render edges to form a DAG; report the actual cycle path on failure. A plot generated from JSON must not become that JSON's scientific cause. Validate expected dependency classifications as well as acyclicity; removing/demoting an edge to membership must not evade a scientific check.

A cache hit needs more than a section name. Bind result hash, exact scientific input/executable hashes, simulator identity, fixture/schema version, relevant Python/platform identity, producer/run ID and completion timestamp. Require completed records and record original producer provenance on import. Name hashes by their contents: a digest of context plus run ID is `producer_context_sha256`, not a release-manifest hash. Preserve legacy records and verify their original schema explicitly; reject ambiguous dual fields in new records. Deliberately corrupt cached values and identities. Execution caches are not release dependencies unless deliberately archived as such.

### Canonical Results And Manifest Envelope

Specify structural JSON hashing precisely: UTF-8, duplicate-key rejection, key ordering, whitespace, escaping, Unicode normalization or none, integer/finite-float representation, negative zero, NaN/Inf rejection, array order, final newline and any field exclusions. Store fixed byte/hash known-answer vectors covering these cases. Identify a project-defined format explicitly rather than calling it RFC 8785. Preserve serializer versions and historical vectors; the aim is independently reproducible bytes, not “whatever this Python version dumps.” Ordinary result hashes should exclude no fields; special identity projections must be narrow and documented.

Separate **CANONICAL MANIFEST IDENTITY** (structural identity after explicit projection) from **RAW MANIFEST SHA-256** (hash of actual final file bytes). If Markdown embeds the canonical identity, a documented projection can exclude that Markdown entry's digest/size while retaining its path, role and dependencies. The final manifest must still contain and verify the actual Markdown digest/size. JSON can reference the manifest by path/schema rather than embedding a circular digest.

Keep the manifest and detached checksum as mandatory envelope members rather than recursively self-hashed payload entries; return their actual size/hash from verification. Neither checksum nor canonical identity is a digital signature or authenticity claim.

Finalize in this order:

1. Write qualified scientific JSON, then deterministic rendered artifacts.
2. Construct and write the final manifest, including actual rendered-file hashes.
3. Hash those exact manifest bytes and write the detached checksum.
4. Independently read back both files, recompute the raw hash and compare checksum bytes.
5. Verify canonical identity separately, then verify the complete release.

Do not hash a pre-final representation. Render-only commands must preserve scientific JSON and check regenerated artifact hashes. Incomplete candidates cannot pass ordinary release verification.

### Exact Bytes And Two-Way Inventory

An exact-byte protocol must use binary output. For a checksum defined as lowercase 64-hex digest, two ASCII spaces, expected basename and one LF, validate inputs and share one small serializer/writer between generation and tests; use `Path.write_bytes`, preferably an atomic sibling-file replacement. Do not depend on `write_text`, `os.linesep` or platform newline translation. The verifier must independently construct expected bytes rather than trust the writer helper.

Test a literal known answer and a temporary fake manifest: write, hash, write checksum, read back, compare exact ASCII bytes, and mutate either file by one byte to require rejection. Check one LF, zero CR, no BOM/NUL, exact filename, spacing and digest case. Reject CRLF, extra/missing LF, one/three spaces, wrong filename, uppercase digest, BOM and trailing spaces. Run byte/canonical tests without SPICE and under all three Python optimization modes. Use Windows CI when available; otherwise claim only removal of text newline translation, not actual Windows execution.

Verify both directions: manifest -> filesystem requires every member with matching size/hash; filesystem -> manifest requires every release-relevant file to be declared. Define release roots/patterns and exclusions for caches, `__pycache__`, OS metadata, temporary files and scratch. Do not hide scientific inputs there. Reject unsupported symlinks and undeclared scientific files. Referenced historical archives must remain available and verifiable.

### Corruption And Maintenance Qualification

On disposable copies, mutate a numeric result, model, research CSV, raw capture gzip, render-only SVG, README, required DSP source (remove it), checksum, dependency edge, causal cycle and undeclared file, where present. Include the exact-checksum format variants above. Require rejection and meaningful diagnostics; report completed counts and gaps. Recompute outer hashes for semantic graph mutations so a stale checksum does not mask an untested dependency validator. Test section seals directly as well as whole-file hashes.

Use version semantics that distinguish:

| Version class | Change |
| --- | --- |
| Major / model | Topology, traced values, DSP reference behavior or hardware interpretation |
| Minor validation | Meaningful additional physical/numerical qualification without changing core topology |
| Patch / maintenance | Provenance, portability, documentation or verifier changes without scientific-result change |

Before a maintenance edit, verify the qualified baseline, envelope, section/capture hashes and scientific identities. Stop on inconsistency. Retain old releases immutably; do not rewrite prior scientific records to clean up terminology. A delta/overlay snapshot can avoid recursive archive duplication if it maps every required original path to exact verified bytes, pins the base identity and can reconstruct an independently verifiable original bundle.

For a patch, state `MODEL CHANGES: NONE`, `NUMERICAL RESULTS: UNCHANGED`, and the actual `fresh_spice_runs` count. Do not rerun hours of SPICE merely for a checksum fix when scientific executable/input hashes match. If only CLI dispatch changed in a combined harness, prove the scientific portion unchanged and retain the original executable provenance. Reuse sealed captures and results, or rerun independent analysis when needed, without implying fresh simulation. A changed scientific input requires explicit affected requalification; never silently broaden a maintenance release or relax criteria.

## Escalate To Hardware Measurements

When dominant uncertainty is physical rather than computational, stop speculative refitting and produce a prioritized bench plan. Identify the unknown, specimen, measurement conditions/uncertainty and which model boundary or hypothesis the measurement will constrain. Another simulation version is usually less useful than one discriminating measurement at this point.

High-value candidates, as applicable, are pot position-to-wiper curves; low-current diode/zener I-V and relevant junction capacitance; idle rails and loaded sag/ripple; transformer secondary voltage/regulation; electrical speaker impedance; BBD clock endpoints/control response; detector switching; tank code, DCR, impedance and response; and internal test-point waveforms. Preserve electrical safety requirements for high-voltage and mains-connected hardware when planning bench work.

A release may be **READY AS FROZEN IMPLEMENTATION REFERENCE** while listing `UNRESOLVED_HARDWARE` items. If required implementation/numerical/integrity gates fail, it is not ready for that scope; explicitly bounded limitations must remain visible. Never promote assumptions to measured truth merely to reach a release label.

## Readiness Checklist

Mark inapplicable items with a reason; do not add absent subsystems just to check a box.

| Area | Before declaring readiness |
| --- | --- |
| Source | [ ] Revision identified; BOM/layout cross-checked where available; ambiguities preserved; external research separately labeled |
| Model | [ ] No undocumented traced-value tuning; switches/jack normals audited; reusable core frozen; effects separable where appropriate |
| Controls | [ ] Electrical/panel mapping distinct; taper hypotheses explicit; measured-LUT boundary and endpoint/monotonicity checks available |
| Validation | [ ] Factory points used where available; calibration separated; nonlinear harmonics checked; convergence and crossing search qualified |
| Power/load | [ ] Deterministic reference retained; supply assumptions explicit; reactive-load sensitivity considered; electrical load distinct from acoustic response |
| Uncertainty | [ ] Nonlinear-device priors and replacement-component hypotheses labeled; hardware-only unknowns listed |
| Regression | [ ] Named fitting profile; bounded raw golden captures with settling history; independent metric reconstruction; drift limits declared |
| Software | [ ] No critical asserts; normal/-O/PYTHONOPTIMIZE failure probes pass; invalid/missing/incomplete data rejected; caches hash-bound to inputs |
| Release | [ ] Scientific/render/verification relationships separated; causal DAG and edge contract pass; canonical hashing specified; raw hashes and exact-byte protocol checked; inventory verified both ways; corruption cases rejected |
| Final claim | [ ] Implementation-reference scope distinguished from hardware truth; retained versus fresh results explicit; remaining bench measurements listed |
