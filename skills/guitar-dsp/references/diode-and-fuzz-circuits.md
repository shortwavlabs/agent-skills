# Diode And Fuzz Circuits

## Contents

- When to use this reference
- Circuit reading priorities
- Diode clipping topologies
- Feedback diode solvers
- Fuzz-specific behavior
- Bias, impedance, and loading
- Oversampling and aliasing handoff
- Measurement and tests

## When To Use This Reference

Read this when modeling diode clippers, Tube Screamer-style feedback clipping, Big Muff-style fuzz, transistor fuzzes, diode ladders, octave fuzzes, or any pedal where the exact clipping topology matters.

Use `nonlinear-waveshaping.md` for generic transfer curves and `aliasing-oversampling.md` for sample-rate artifact control.

## Circuit Reading Priorities

Do not start by copying every component. First extract the audible constraints:

- input coupling and loading
- pre-gain and pre-emphasis
- clipping topology
- diode count and direction
- feedback versus shunt clipping
- bias references and asymmetry
- recovery filtering
- tone network loading
- output volume and compensation

Then choose a model depth:

- generic soft clip for quick prototypes
- calibrated transfer curve for simple diode-to-ground behavior
- Newton-solved diode branch for diode knees and feedback behavior
- staged op-amp/transistor model for fuzz feel and recovery
- nodal network when source/load interaction is central

## Diode Clipping Topologies

| Topology | Behavior | Modeling notes |
| --- | --- | --- |
| Antiparallel shunt to ground | direct clipping after a series resistance | transfer curve or simple diode solve is often enough |
| Op-amp feedback diodes | gain reduces as diodes conduct | model as feedback branch, not plain output clip |
| Series diode strings | higher knee, harder hit before conduction | scale diode voltage/knee by count |
| Asymmetric diode counts | even harmonics and DC tendency | add DC blocker and level tests |
| LED or germanium options | different knee and dynamic resistance | expose only if product needs voicing options |
| Diode plus capacitor feedback | clipping and bandwidth interact | include feedback low-pass or recovery filter |

Feedback clipping is the common trap. A feedback diode pair changes the effective gain dynamically; it is not equivalent to `tanh(output)`.

## Feedback Diode Solvers

A practical solver shape:

```text
input current through Rin
feedback resistor current through Rf
diode branch current through antiparallel diodes
solve KCL at op-amp summing node
apply op-amp rail, slew, and recovery limits
```

Implementation rules:

- Bound Newton iterations.
- Clamp exponent inputs.
- Use `double` internally.
- Provide a fallback if the solve diverges.
- Add tiny floors to resistances.
- Smooth drive and topology changes.
- Keep the solver inside a local nonlinear island when oversampling is used.

Do not expose diode type, count, or mismatch as public controls unless they are part of the product. Hidden voicing constants are easier to tune and safer for presets.

## Fuzz-Specific Behavior

Fuzz circuits often depend on more than diode clipping:

- transistor bias and starvation
- op-amp bandwidth limits
- coupling cap recovery
- interstage loading
- sustain/gain controls affecting more than level
- passive tone stack insertion loss
- raw tone-bypass modes
- speaker/cabinet filtering after the fuzz

For Big Muff-inspired circuits:

- Sustain is often a coupled gain and clipper-feed control, not only pre-clip gain.
- The tone stack is lossy and loaded; a plain EQ can miss the feel.
- Tone bypass may intentionally jump in level and bite.

For Fuzz Face or Tone Bender-inspired circuits:

- Input impedance and guitar volume interaction can dominate the feel.
- Bias and transistor gain spread matter.
- Cleanup behavior should be checked with reduced input level, not only the drive knob.

For octave or foldback fuzz:

- Polarity, rectification, and filter placement are critical.
- Aliasing checks matter early.

## Bias, Impedance, And Loading

Bias and loading are tone controls in disguise.

- Bias shifts clipping symmetry and recovery.
- Input impedance changes how a passive guitar pickup would feed the circuit.
- Output load changes tone stack response and level.
- Coupling caps create high-pass behavior and recovery after large transients.

In plugin form, you usually do not have the real pickup impedance. Decide whether to:

- assume a buffered input
- provide an input-buffer stage
- model pickup loading as a hidden part of the pedal
- expose pickup/loading only for advanced workflows

## Oversampling And Aliasing Handoff

Fuzz stages can create dense high-order harmonics. Read `aliasing-oversampling.md` before choosing a factor.

Good default:

```text
host-rate input conditioning
  -> local 2x or 4x diode/fuzz island
  -> oversampled recovery filtering
  -> host-rate passive tone/output
```

Keep full-chain oversampling as a last resort.

## Measurement And Tests

Measure:

- transfer curves by gain/sustain
- harmonic spectra at 1 kHz
- alias probes at 5 and 7 kHz
- output RMS/peak versus drive
- DC offset
- tone stack response
- cleanup with reduced input level
- bypass or tone-bypass level change

Tests:

- disabled bypass identity
- finite output at extreme drive
- reset determinism
- solver convergence on impulse/noise/silence
- DC rejection
- automation safety
- output compensation stays bounded
- tone bypass preserves intentional raw behavior

Use listening fixtures with palm mutes, sustained single notes, low-tuned riffs, guitar-volume cleanup, and bright lead lines.
