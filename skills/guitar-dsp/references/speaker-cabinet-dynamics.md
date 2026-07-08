# Speaker Cabinet Dynamics

## Contents

- When to use this reference
- Static IR versus dynamic cabinet
- Dynamic behaviors to model
- Practical model layers
- Placement and routing
- Measurement workflow
- Tests and release gates

## When To Use This Reference

Read this when static cabinet IRs sound too stiff, bright, flat, or disconnected from amp drive, or when adding speaker compression, resonance, excursion behavior, dynamic EQ, breakup, impedance interaction, or cabinet/mic nonlinearity.

Use `guitar-signal-chain.md` for basic IR loading and realtime-safe file handling. Use this reference for the dynamic behavior beyond a static convolution.

## Static IR Versus Dynamic Cabinet

A cabinet IR is linear and time-invariant. It captures:

- frequency response
- phase response
- mic position and room early response
- cabinet/speaker coloration at one operating level

It does not capture:

- power compression
- cone excursion limits
- level-dependent resonance
- speaker breakup
- amp/speaker impedance interaction
- mic/preamp nonlinearities

Do not discard IRs. They are still the foundation. Add dynamics around or alongside the IR when the product needs the speaker to react to level.

## Dynamic Behaviors To Model

| Behavior | Audible effect | Practical approximation |
| --- | --- | --- |
| Power compression | loud hits flatten and darken | envelope-controlled gain and high cut |
| Low-frequency excursion | palm mutes bloom or clamp | level-dependent low-resonance filter |
| Speaker resonance | cab feels connected to amp | resonant low band before/after IR |
| Cone breakup | upper-mid rasp at high level | band-limited saturation or dynamic EQ |
| Thermal drift | sustained loudness changes tone | slow envelope controlling gain/brightness |
| Impedance interaction | amp depth/presence feel | feedback-style depth/presence filters before cab |
| Mic/preamp overload | subtle density after cab | post-IR soft clip or post color |

Keep each layer bypassable or measurable. Dynamic cabinet modeling can quickly become a pile of hidden tone changes.

## Practical Model Layers

Start simple:

```text
amp output
  -> optional speaker-drive trim
  -> low-resonance / excursion stage
  -> cabinet IR
  -> dynamic high-cut / power compression
  -> optional breakup band color
  -> output trim
```

Layer choices:

1. **Envelope-controlled cabinet compression**
   - Detect post-amp or pre-cab level.
   - Reduce gain subtly on loud sustained passages.
   - Use attack/release long enough to avoid pumping.

2. **Dynamic low resonance**
   - Add or modulate a low-frequency resonant band around the cabinet resonance.
   - Clamp resonance under heavy palm mutes to avoid woof.

3. **Dynamic brightness**
   - Lower high-cut or high shelf as level/thermal state rises.
   - Avoid making the cab dull at normal playing levels.

4. **Breakup band**
   - Add band-limited saturation in upper mids.
   - Keep it subtle and post-IR unless modeling a specific speaker before mic capture.

5. **Post-cab color**
   - Use for mic/preamp/console density.
   - Keep separate from speaker dynamics so users can debug tone.

## Placement And Routing

Cabinet dynamics placement depends on intent:

- Pre-IR dynamics feel like the speaker reacting before the microphone capture.
- Post-IR dynamics feel like mic/preamp or output color.
- Depth/presence interactions usually belong before cabinet filtering.
- Delay/reverb usually belong after cabinet unless modeling a recorded room or post-cab ambience lane.

For stereo:

- Mono amp into stereo cab can fan out after mono speaker dynamics.
- Stereo post-FX should usually remain after cabinet dynamics.
- Linked stereo detection avoids image shift for compression-like cabinet behavior.

## Measurement Workflow

Measure static and dynamic behavior separately:

- frequency response at low, medium, and high drive
- impulse response with dynamics disabled
- step or burst response for compression timing
- palm-mute low-frequency envelope
- high-cut movement under sustained loud input
- stereo correlation for stereo cabinet paths
- output RMS/peak versus input level

Compare:

- static IR only
- IR plus compression
- IR plus low resonance
- IR plus full dynamic stack

Always level-match before listening. A dynamic cabinet often sounds "better" simply because it is louder or darker.

## Tests And Release Gates

Tests:

- disabled cab is passthrough when promised
- no-IR filter path stays finite
- dynamic layers disabled reproduce static IR path
- finite output under impulses, sine bursts, noise, and silence
- linked stereo dynamics preserve image
- reset determinism
- automation safety
- tail and latency reporting remain correct

Release gates:

- benchmark dynamic cab at 44.1, 48, and 96 kHz
- verify no file loading or IR construction occurs in `processBlock`
- confirm dynamic states reset on preset/model changes when intended
- check DAW save/reopen for selected IRs and dynamic settings
- keep before/after renders for the previous known-good cabinet sound
