# Triode And Tube Stage Approximation

## Contents

- When to use this reference
- Modeling scope
- Stage anatomy
- Approximation levels
- Triode-like transfer options
- Grid, cathode, and coupling memory
- Power-amp style behavior
- Measurement and tests

## When To Use This Reference

Read this when approximating tube preamp stages, power-amp color, triode-like nonlinearities, cathode bypass behavior, blocking distortion, sag, negative feedback, or tube-inspired amp stages in realtime C++.

Use neural modeling references when the task is to capture a real amp from audio. Use this reference when writing an explicit DSP approximation.

## Modeling Scope

A tube stage can mean:

- clean preamp triode
- overdriven preamp gain stage
- cathode follower
- tone-stack driver
- phase inverter
- power amp
- rectifier/power-supply sag

Do not model all of these by default. Pick the audible behavior needed for the product.

## Stage Anatomy

Useful generic stage:

```text
input coupling HPF
  -> grid/leak behavior
  -> triode-like nonlinear transfer
  -> cathode memory / local feedback
  -> plate load and Miller/bandwidth filtering
  -> output coupling HPF
```

Important behaviors:

- asymmetric clipping
- gain compression
- low-frequency recovery after large hits
- high-frequency rolloff from Miller capacitance and circuit loading
- interaction with the following tone stack

## Approximation Levels

| Level | Use when | Notes |
| --- | --- | --- |
| Asymmetric soft clip | fast amp color macro | simple, stable, not circuit-specific |
| Waveshaper plus filters | preamp channel approximation | good first explicit model |
| Triode curve approximation | tube-like knee and compression | needs calibration and clamps |
| Dynamic triode stage | cathode/coupling memory, blocking behavior | more realistic but stateful |
| Full circuit solve | research or highly specific amp recreation | expensive and harder to maintain |

Most guitar plugins should start at "waveshaper plus filters" unless the tube behavior is the main product.

## Triode-Like Transfer Options

Simple asymmetric clip:

```text
x = input * preGain + bias
y = tanh(posScale * max(x, 0)) + negMix * tanh(negScale * min(x, 0))
```

Triode-inspired static curve:

```text
effective = grid + plate / mu + bias
current = k * max(effective, 0) ^ 1.5
output = plateLoadTransform(current)
```

Use normalized units unless the project has a full circuit-voltage model. Clamp all exponent inputs and outputs.

For realtime use:

- precompute constants
- use `double` for curve math
- bound output before filters
- add DC cleanup after asymmetric stages
- smooth bias, drive, and gain

## Grid, Cathode, And Coupling Memory

Tube feel often comes from memory, not only the static curve.

Useful approximations:

- **Grid conduction**: when input exceeds a threshold, charge a small state that temporarily shifts bias.
- **Blocking distortion**: large hits push bias colder, then recover with a slow time constant.
- **Cathode bypass**: frequency-dependent local feedback; more gain where the cathode is effectively bypassed.
- **Coupling caps**: HPF behavior plus recovery after sustained overload.
- **Miller effect**: input low-pass that changes with gain assumptions.

Keep memory terms subtle and test reset behavior. If the state is too strong, the model may feel broken rather than tubelike.

## Power-Amp Style Behavior

Power amp approximation can include:

- master-volume-dependent saturation
- low-frequency resonance or depth control
- presence/negative-feedback shaping
- sag or supply compression
- speaker-load interaction
- output transformer bandwidth limits

A practical product chain:

```text
preamp output
  -> tone stack
  -> phase-inverter/power soft clip
  -> sag envelope gain
  -> depth/presence feedback filters
  -> cabinet or speaker dynamics
```

Do not report latency for these stages unless an actual lookahead or linear-phase process is added.

## Measurement And Tests

Measure:

- static transfer at several bias/drive settings
- harmonic spectra for clean, edge, and driven levels
- DC offset and recovery after large transients
- frequency response before and after the nonlinear stage
- sag envelope attack/release
- interaction with tone stack and cabinet

Tests:

- finite output under extreme gain
- reset determinism
- sample-rate stability
- no denormal spikes on silence and decay
- bias/sag states recover to neutral
- automation of drive, bias, master, presence, and depth is click-safe

Listening fixtures:

- edge-of-breakup chords
- palm mutes
- sustained bends
- low-string chugs
- volume-knob cleanup
- bright single-coil input
