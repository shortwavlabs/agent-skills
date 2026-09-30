# Device-Model Qualification

## Contents

- The question a device model must answer
- Candidate search and labelling
- Isolated benchmark (example: op-amps)
- In-circuit qualification
- Choosing between candidates
- Project-authored calibrated models
- Device-law details that matter at millivolt parity
- Case-study notes
- Checklist

## The Question A Device Model Must Answer

"Is this model good?" has no answer. Ask: **does this model reproduce the behaviours of the part that matter in this circuit, over this circuit's operating range, robustly in the simulators that will be used?** A datasheet-perfect isolated model can still fail in the full circuit (start-up, operating-point selection, order sensitivity). A model with the correct part number can still be numerically fragile or wrong in the properties this circuit exercises. Qualify both halves.

## Candidate Search And Labelling

1. Search the local model collections first, then maker websites for the exact part, then makers of equivalent parts.
2. Deduplicate: many collections redistribute the same vendor macro. Compare element-for-element before counting "another candidate".
3. Label every candidate (exact manufacturer / exact device wrong grade / similar substitute / project-authored / generic / diagnostic control) as defined in `oracle-provenance.md`, with source, revision, dialect, terminal order and hash.
4. Wire each candidate into the circuit through a small **shim subcircuit** that maps its terminal order to the circuit's, so swapping candidates changes one include line and nothing else. Evaluate in temporary copies of the deck; hash the canonical files before and after.
5. Add a **diagnostic control** (for an op-amp: ideal gain, single pole, no rails, no supply current). It is not eligible for selection; it shows which circuit behaviours come from the circuit and which come from the model.
6. Record candidates that could not be obtained (login walls, dead links) as "not obtained" rather than silently skipping them.

## Isolated Benchmark (Example: Op-Amps)

Measure only the properties the target circuit can feel, under the datasheet's conditions **and** under the circuit's supply/bias/load:

| Property | Typical bench | Why a circuit may care |
| --- | --- | --- |
| Open-loop gain A0 (datasheet load) | Open loop with a DC servo (large R/C feedback holds the output at bias; open above a few µHz) | Closed-loop gain error, diode-feedback operating point |
| Gain-bandwidth / unity-gain frequency, phase margin | Same deck, AC sweep to beyond GBW | High-gain stages, phase/group delay, stiffness of the realtime model |
| Slew rate | Unity-gain follower, large step, 10–90 % | Large high-frequency signals |
| Input bias/offset current and offset voltage | DC through large source resistors | DC offsets across diodes, idle bias of clippers |
| Output swing versus load (several loads) | Clipped sine or DC drive into R_L | Clipping onset and asymmetry at the circuit's supply |
| Output current limit | Low-ohm loads | Heavy loads, overload recovery |
| Input common-mode range | Follower with swept input | Single-supply biasing near the rails |
| Supply current (per package) | Idle supply current | Supply sag through series resistors, battery/adaptor behaviour |
| CMRR, PSRR (SVR) | Standard benches at a stated frequency | Ripple and common-mode injection |
| Output impedance | Closed-loop with load step | Driving capacitive or low-impedance loads |

Compare with the datasheet **typical** values and curves, with the basis written next to each number (table entry, curve reading, derived from power dissipation). Score closeness only for properties that matter to the circuit.

Also record, per simulator/version and compatibility mode:

- does it parse (and with what warnings, ignored parameters or compatibility notes)?
- does a simple follower converge?

## In-Circuit Qualification

Isolated fidelity is necessary, not sufficient. In the full circuit, with each candidate:

1. Current-order regression: the circuit's own behaviour checks (bias points, switching, clipping levels, response, loading) in every operating state.
2. Start-up: transient start in every state and at control endpoints.
3. Operating point before AC: in the intended state (see `numerical-qualification.md`).
4. Statement-order stress in stages: a small screening corpus first, then larger corpora only for survivors; same orders in every engine.
5. Settled behaviour differences versus the incumbent model, attributed to specific model properties (for example "input bias current 140 → 57 nA shifts the idle offset across the clipping diodes, raising small-signal gain 0.8 dB").
6. Downstream consequences: validator windows or expected values that were tuned to the old model's behaviour (supply current, sag) must be recentred **with evidence**, not widened.

Reject a candidate at the first stage it fails and report where. A vendor model that fails start-up or order stress is not rescued by its part number.

## Choosing Between Candidates

Decide with an explicit, ordered criteria list written before the results are known, for example:

1. Parses and converges in every required engine.
2. Zero order-stress failures and zero wrong states in the declared corpus.
3. Circuit behaviour checks pass.
4. Datasheet fidelity for the properties that matter.
5. Provenance quality (exact > substitute), licence and maintainability.

Robustness outranks provenance for an oracle: an oracle that fails for some statement orders is not an oracle. Document the rejected candidates and why.

## Project-Authored Calibrated Models

Writing a model can be the right answer when vendor macros are solver-fragile or unfaithful in the properties that matter. It is acceptable only when:

- the required datasheet behaviours are identified and each calibration target is listed with its datasheet basis;
- the topology and every simplification are documented in the model file header;
- excluded behaviours (noise, temperature drift, second-order effects) are listed explicitly;
- a calibration table in the header shows datasheet value, model value and the element that sets it;
- the model is qualified in every engine/version that will run it, including order stress and operating-point selection;
- target-circuit parity against the previous accepted model is measured and explained;
- the file is labelled "datasheet-calibrated project model", never "manufacturer model".

Design notes that generalise:

- Prefer physical, monotone device-level structures (transistor-level stages with ratio-trimmed mirrors) over high-gain controlled-source loops and clamps. Very high-gain polynomial output stages, clamps referenced a fixed distance inside the rails (they cross when the supply is low) and resistor-programmed supply currents all create regions where Newton or its fallbacks fail.
- Local feedback helpers inside the model (for example a beta-helper mirror) can hurt Newton convergence from `.nodeset` starts; test operating-point selection after every structural edit.
- Calibrate with the same benchmark decks used to evaluate vendor candidates so the comparison is apples to apples.

## Device-Law Details That Matter At Millivolt Parity

When a realtime model must reproduce a SPICE device (a diode law, a JFET switch, a BJT follower), do not assume the textbook equation is what the simulator computes. Simulator device models commonly include:

- recombination/generation current with its own emission coefficient and a voltage-dependent generation factor;
- high-injection knee (IKF) dividing the forward current;
- series resistance, junction capacitance and transit-time charge;
- piecewise reverse-bias handling (for example a region below a threshold where one current component is **frozen** at its threshold value and another follows a different continuous formula);
- breakdown behaviour and its knee;
- `gmin` conductance in parallel with every junction;
- temperature-scaled parameters.

Procedure:

1. Read the simulator's device **source code** for the version you pin (for ngspice, the device's `*load.c`), not only the manual. Note branch conditions, thresholds, which terms are frozen and which carry slope.
2. Implement the law offline and compare with the installed simulator's DC sweep of the same card, on a grid **fine enough for the claim**. A coarse current sweep can straddle a narrow region where the laws differ; sweep densely across branch thresholds and in the current range the circuit actually uses.
3. Report the worst branch error in the units of the downstream gate (for example millivolts of branch voltage) and where it occurs.
4. Record which device terms the realtime model omits (for example series resistance or transit time) and their measured effect; move an item from "omitted" to "modelled" when the evidence says it matters.

## Case-Study Notes

*Case study (SD-1 overdrive, one project; values are specific to it):*

- The only exact-part vendor macro failed the circuit's first transient step. Four substitute macros failed start-up, operating-point selection or order stress; one failed 311 of 2000 randomised orders because its output clamps crossed below about 5 V of supply and its polynomial output stage had a gain near 6e6. A transistor-level datasheet-calibrated project model had 0 failures in 35,500 runs across two engines.
- The project model moved results in explainable ways: pedal supply current 2.35 → 4.13 mA (the pedal's published figure is 4 mA), input bias current 140 → 57 nA (datasheet 60 nA), which raised small-signal gain 0.8 dB through the diode idle offset.
- The realtime diode law initially continued the forward recombination term into reverse bias. The simulator freezes it below −3·N·Vt. A coarse branch sweep reported 0.81 mV worst error; a 1 nA-resolution sweep found 1.27 mV. With the freeze implemented the error was 0.68 mV.

## Checklist

- [ ] Candidates found, deduplicated, labelled, hashed and wired through shims in temporary decks.
- [ ] A diagnostic control model is included.
- [ ] Isolated benchmark covers the properties this circuit exercises, under datasheet and circuit conditions.
- [ ] In-circuit: regression, start-up, pre-AC operating point, staged order stress, settled differences attributed.
- [ ] Selection criteria written before results; robustness outranks part-number provenance.
- [ ] Project-authored models carry a calibration table, simplifications, exclusions and the correct label.
- [ ] Realtime device laws verified against the simulator source and a sufficiently fine DC sweep.
