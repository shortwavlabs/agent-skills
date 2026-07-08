# Tone Stack Modeling

## Contents

- When to use this reference
- Tone stack roles
- Choosing a model depth
- Passive network modeling
- Active and utility EQ modeling
- Placement and gain staging
- Control smoothing
- Measurement and tests

## When To Use This Reference

Read this when implementing or reviewing bass/mid/treble/presence/depth controls, amp tone stacks, pedal tone controls, graphic EQ adjacent to an amp, or passive loaded tone networks.

## Tone Stack Roles

Tone controls in guitar DSP can mean different things:

- **Amp tone stack**: interactive, lossy, often after a nonlinear preamp stage.
- **Pedal tone control**: part of the effect identity, often before final volume.
- **Post-amp EQ**: utility shaping, usually clean and predictable.
- **Presence/depth**: power-amp or speaker-feedback inspired controls.
- **Cabinet filter path**: HPF/LPF around an IR or no-IR cabinet stage.

Decide which role the block has before choosing the math. A clean RBJ EQ can be excellent for utility EQ and wrong for a passive Muff-style tone stack.

## Choosing A Model Depth

| Model | Use when | Tradeoff |
| --- | --- | --- |
| RBJ shelves/peaks | utility tone, fast amp macro, post EQ | simple and stable, but controls do not interact much |
| Tilt/crossfade | one-knob tone, presence/darkness macro | musical but not circuit-like |
| Precomputed response interpolation | fixed analog stack with few controls | cheap at runtime, less flexible |
| Nodal passive solver | interactive tone pots, loading, lossy networks | more code and state, needs stability tests |
| Full circuit stage around tone network | fuzzes, wah/tone interactions, impedance-sensitive pedals | best behavior, highest implementation cost |

Use the shallowest model that preserves the musical behavior users notice.

## Passive Network Modeling

Passive tone networks are often lossy and load-dependent. Preserve these traits:

- insertion loss
- pot interaction
- source impedance
- output load
- coupling capacitors
- tone-bypass level jumps when the hardware has them

A passive solver can be small and robust:

```text
known source voltage
  -> conductance matrix for resistors/pot segments
  -> trapezoidal companion conductances for capacitors
  -> solve node voltages
  -> update capacitor histories
```

Guidelines:

- Clamp pot resistances to a small floor so matrix terms never divide by zero.
- Keep capacitor state per channel.
- Sanitize failed solves to silence or bypass rather than NaN.
- Smooth or crossfade switch changes like tone bypass.
- Do not automatically normalize away meaningful insertion loss.

Passive tone examples:

- Big Muff-style low/high branch blend: model the low branch, high branch, pot wiper, and output load together when interaction matters.
- Amp stack: model bass/mid/treble loading if the target is classic interactive tone behavior.
- One-knob pedal tone: a tilt or crossfade can be enough unless the loaded response is central to the sound.

## Active And Utility EQ Modeling

For amp macro controls and post EQ, RBJ filters are often the right tool.

Useful starting landmarks:

- Depth / low resonance: around 80 Hz.
- Bass shelf: around 100 to 120 Hz.
- Mid peak: around 650 to 750 Hz.
- Treble shelf: around 3 to 4 kHz.
- Presence: around 3.2 to 4.5 kHz.

Rules:

- Neutral settings should be exact or near-exact passthrough.
- Use `double` for coefficient calculation.
- Clamp frequencies below Nyquist.
- Smooth gains and cutoff targets around 5 to 20 ms.
- Rebuild coefficients at a bounded control rate, or crossfade when jumps click.
- Keep input/output trims separate from band coefficients.

## Placement And Gain Staging

Tone stack placement changes the nonlinear behavior:

- Pre-clip tone changes what distorts.
- Post-clip tone shapes harmonics after generation.
- Amp tone between preamp and power amp can affect power-stage drive.
- Cabinet filtering after distortion is essential for believable guitar tone.

For neural amp cores:

- If the model already captured the tone stack, do not apply a second amp stack by default.
- If the model is an amp-head capture without cabinet, keep cabinet separate and post-neural.
- Keep output compensation visible when a tone stack has large insertion loss.

## Control Smoothing

Automation is the most common failure mode.

- Smooth visible controls.
- Smooth hidden derived controls.
- Crossfade mode switches and bypass branches.
- Avoid per-sample coefficient rebuilds unless the algorithm is designed for it.
- Reset filter state only when exact bypass or sample-rate changes require it.

## Measurement And Tests

Measure:

- frequency responses at min/default/max and representative combinations
- insertion loss
- response changes with source/load assumptions
- automation max-adjacent-delta
- mono/stereo routing

Tests:

- neutral passthrough
- finite output at extremes
- sample-rate stability
- reset determinism
- automation safety
- tone control changes expected bands
- passive bypass preserves intentional level/tone difference

For product tuning, keep a few known-good guitar DI renders so later coefficient changes do not erase a good musical balance.
