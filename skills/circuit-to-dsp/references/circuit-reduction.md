# Circuit Reduction And State Design

## Contents

- SPICE is an offline oracle
- Choosing the realtime formulation
- Partition by physics, not by schematic boxes
- Testing a simplification
- Omission register
- State inventory
- Coupled nodes and update order
- Reduced op-amp workflow
- Exact reset to the DC fixed point
- Time-varying controls
- Fidelity envelope
- Checklist

## SPICE Is An Offline Oracle

Do not put a SPICE engine in `processBlock()`. Typical reasons it fails in production:

- CPU: transistor-level transient analysis runs far slower than real time for an audio circuit;
- adaptive timesteps do not fit a fixed-rate, fixed-latency callback;
- allocation, global state and non-reentrant libraries;
- convergence failures have no realtime-safe fallback;
- blocking and threading constraints;
- redistribution and licence terms of the engine and of vendor model files.

Use SPICE offline for calibration, hypothesis tests, sensitivity studies, golden data and regression references (see the `spice-circuit-modeling` skill). Ship a bounded realtime model derived from it.

## Choosing The Realtime Formulation

Compare candidates on measured error against the oracle, nonlinear dimension, worst-case cost and robustness, not on familiarity:

| Candidate | Consider when | Watch for |
| --- | --- | --- |
| Static or parallel waveshaper | Prototype or fallback | Quantify its in-band error at the clipping node; feedback networks rarely reduce to a static curve |
| Series pre-filter → shaper → post-filter | Genuinely memoryless, voltage-domain clipping | Wrong structure for feedback clipping (see `nonlinear-solvers.md`) |
| Block-structured nodal / state-space model with physical states and a small nonlinear solve | Most analog stages: op-amp gain stages, tone networks, followers | Coupling between blocks through shared nodes |
| Monolithic nodal (DK-style) model of the whole path | Strong global coupling | Larger linear algebra per sample; compare CPU with the block model |
| Wave digital filters | Networks with one nonlinearity per adaptor tree | Multiple nonlinearities, shared return paths and non-closed-form device laws complicate adaptors |
| Full MNA of the transistor-level circuit | Offline studies only | Many nonlinear ports and MHz poles |
| Lookup tables of the whole stage, neural models | When physics is unknown or too costly | Controls and states multiply table dimensions; validation of the shipped function is still required |

Keep the rejected alternatives and their measured reasons in the design record.

## Partition By Physics, Not By Schematic Boxes

Classify every subsystem, with evidence:

| Class | Meaning | Evidence required |
| --- | --- | --- |
| A. Must model accurately | Changes audible behaviour or a declared gate | Error with the effect removed exceeds the budget |
| B. Model with calibrated simplification | Needed, but a reduced form reproduces it | The reduced form meets the budget over the declared range |
| C. Optional authenticity | Small audible effect; product decision | Measured effect documented |
| D. Omit from the audio path | Negligible inside the fidelity envelope | Measured effect below the budget, with a regression check |

Questions worth asking for every circuit:

- Can transistor or JFET buffers be linearised (gain, input impedance, input capacitance) inside the envelope?
- Is the bias/reference node really AC ground, or does its finite impedance couple stages through **shared return currents**?
- Does each op-amp need finite gain-bandwidth, bias current, rails or output resistance, and does the "clean" one also need them?
- Does output or interstage loading matter at the supported settings?
- Do **off-state** switch devices (their capacitances) feed signal through at deep attenuation settings?
- Do device junction or base capacitances matter at the top of the band?
- Does the supply move with signal or with operating mode?

Expect the remaining error, after the obvious blocks are right, to be dominated by small effects: a return current into a shared bias node, an off JFET's capacitances at minimum level, a follower's base capacitance, the finite bandwidth of a second op-amp. Find them by error attribution, not intuition.

## Testing A Simplification

Measure each simplification's effect directly:

1. **In the oracle** (preferred for device-level simplifications): replace the detailed element with its reduced form inside SPICE (for example a transistor follower with a behavioural linear follower) and compare the circuit's outputs with the unmodified oracle. This isolates the simplification from every DSP error.
2. **In a high-rate scratch model**: toggle the effect (a return current, a capacitance, finite GBW) and measure the change in the gated metrics across the operating grid.
3. Report the worst and median change per metric and level, and keep the toggle available for regression.

Never accept a simplification because one centred preset sounds the same.

## Omission Register

Keep a table of everything intentionally not modelled:

| Item | Classification | Measured effect | Regression check |
| --- | --- | --- | --- |
| e.g. op-amp slew rate | Experimentally negligible inside the envelope | worst change in the gated metric | the transient grid |

Items move in or out only with evidence. When new evidence shows an omitted item matters (for example a device-law branch), move it into the model and record the old and new measurements.

## State Inventory

Before writing DSP code, write one authoritative table of continuous states per channel:

| Field | Content |
| --- | --- |
| State | Capacitor voltage (or charge), inductor current, op-amp internal state, filter state |
| Physical meaning | The component and nodes it belongs to |
| Rate | Host rate or internal (oversampled) rate |
| Integrator | Which discretisation, and its companion form |
| Reset value | Its value at the exact DC fixed point |
| In the nonlinear residual? | Whether it enters the coefficients of the nonlinear solve in the same step |
| Bypass behaviour | Processed, frozen, or reset when bypassed |

Distinguish the **continuous state count** from the **nonlinear solve dimension**. A model can carry many linear states and still need only one scalar nonlinear unknown per step; that is often the decisive property for realtime robustness. Prefer physical states over transformed ones: they have meaningful reset values, survive coefficient changes and can be compared with oracle node voltages.

## Coupled Nodes And Update Order

Write the exact per-step update order (which block reads which state from which step). For nodes shared between blocks (bias references, supply rails):

- **implicit** coupling solves the shared node together with the blocks (for example by eliminating it into the nonlinear solve);
- **explicit** coupling uses the previous step's value, adding a one-step lag.

Decide with measured error and CPU. An explicit lag can be accurate enough at a high internal rate; verify against the implicit form rather than assuming either way. Include every return current into the shared node in the coupling; dropping one can produce errors far larger than the discretisation.

## Reduced Op-Amp Workflow

1. Treat the transistor-level or qualified SPICE op-amp model as the oracle.
2. List the properties this circuit could feel: finite open-loop gain, gain-bandwidth pole, input bias current, slew rate, output swing (and its dependence on load and supply), output resistance, current limit, common-mode range, PSRR.
3. For each property, measure the change in the gated metrics when it is omitted, in the oracle or a high-rate model. Record a table per op-amp: property, required or omitted, evidence.
4. Implement only the required properties, as physical states where possible, and validate the reduced op-amp in-circuit against the oracle.

Neither "model every datasheet parameter" nor "op-amps are ideal" is a default. Beware ideal op-amps with **switched rails**: algebraic mode switching can chatter (repeated mode flips within a step) where a one-pole op-amp state with in-loop rails switches cleanly and needs no hidden mode logic.

## Exact Reset To The DC Fixed Point

Circuits with slow coupling capacitors or bias states produce long false transients if states start at zero or at an approximate bias. Those transients corrupt small-signal validation windows and create audible thumps.

- Compute the exact fixed point of the **discrete** model for zero input: analytically, or with one linear solve of the linearised discrete step at prepare time (exact at the bias point).
- Use it for `reset()`, for un-bypass, and before every measurement.
- Test: fresh reset, used-then-reset, drift over long silence (it should stay at numerical noise), and parity of the first analysis window at the smallest input level.

*Case study: an approximate analytic start left a 0.5 mV output step decaying with a 92 ms time constant; for a 5 mV input that alone degraded one fixture from −42.9 dB to −4.5 dB.*

## Time-Varying Controls

A matching static transfer function does not validate a control that moves.

- Realise control-dependent networks with physical state variables; coefficient changes then act on meaningful states. Transformed realisations that are equivalent for a static setting (for example different factorisations or direct forms) can behave very differently under modulation.
- Validate automation against a **time-varying SPICE reference**: drive the simulator's control element (a behavioural conductance fed by a file source, for example) with the same control trajectory the model receives.
- Measure event error (band-limited ESR over the automation event), maximum instantaneous error, worst narrow-band error, per-sample state-step ratio against the reference (no jumps), mode transitions and finiteness. Include fast ramps, slow ramps, sinusoidal modulation and a host-style staircase through the product's smoother.
- Decide the coefficient update cadence from measurements (see `integrators-and-rates.md`).

## Fidelity Envelope

Define, from measurements, the input range in which the model is claimed to be fidelity-grade: typically up to the onset of an effect the model does not reproduce accurately (an op-amp saturating into a behaviour only approximated). Above it the model must stay bounded, continuous and non-chattering (robustness grade). State the envelope in physical units at the circuit input, gate fidelity only inside it, and expose it to users where useful (for example meter marks). The number is circuit-specific; derive it, don't reuse one.

## Checklist

- [ ] Realtime formulation chosen by measured comparison; alternatives recorded.
- [ ] Every subsystem classified A–D with evidence; simplifications measured, preferably in the oracle.
- [ ] Omission register with regression checks.
- [ ] State inventory with reset values, residual membership and bypass behaviour; nonlinear dimension stated.
- [ ] Shared-node coupling and update order decided by measurement.
- [ ] Reduced op-amp properties justified per op-amp.
- [ ] Exact DC reset implemented and tested.
- [ ] Automation validated against a time-varying reference.
- [ ] Fidelity envelope derived and documented.

## Sources

- D. T. Yeh, J. S. Abel and J. O. Smith, "Automated Physical Modeling of Nonlinear Audio Circuits for Real-Time Audio Effects—Part I," *IEEE Trans. Audio, Speech, Lang. Process.* 18(4), 2010: nodal DK method.
- M. Holters and U. Zölzer, "A Generalized Method for the Derivation of Non-Linear State-Space Models from Circuit Schematics," EUSIPCO 2015.
- K. J. Werner, V. Nangia, J. O. Smith and J. S. Abel, "Resolving Wave Digital Filters with Multiple/Multiport Nonlinearities," DAFx-15, 2015: wave digital filters with several nonlinearities.
