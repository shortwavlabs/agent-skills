# Nonlinear Waveshaping

## Contents

- When to use this reference
- Nonlinear guitar DSP frame
- Waveshaper families
- Static transfer design
- Dynamic waveshaping
- Control mapping and gain staging
- Implementation notes
- Measurement and tests

## When To Use This Reference

Read this when designing or reviewing the core nonlinear transfer of a guitar stage:

- boost, overdrive, distortion, fuzz, compressor color, post color, input buffer color
- memoryless transfer curves, asymmetric clipping, soft knees, foldback, polynomial shapers, output compensation
- deciding whether a single shaper is enough or whether to move to diode, fuzz, tube, or speaker-specific modeling

Read `aliasing-oversampling.md` separately when the question is about sample-rate artifacts, local oversampling, ADAA, or alias measurement.

## Nonlinear Guitar DSP Frame

Most useful guitar nonlinearities are not only `y = f(x)`. Treat the shaper as part of a gain and tone path:

```text
input trim
  -> coupling / DC protection
  -> pre-emphasis or low-end tightening
  -> gain cell
  -> nonlinear transfer
  -> recovery filtering
  -> output calibration
  -> DC cleanup
```

The transfer curve matters, but it is rarely the whole sound:

- Pre-clip bandwidth controls which frequencies create harmonics.
- Output compensation decides whether a drive control feels powerful or unusable.
- Bias and asymmetry create even harmonics but can leak DC into later stages.
- Recovery filters and tone stacks make a clipped signal feel like a pedal or amp instead of a raw math function.

## Waveshaper Families

| Family | Good for | Watch for |
| --- | --- | --- |
| Hard clip | aggressive distortion, test baselines | harsh high harmonics; often too static alone |
| `tanh` / `atan` soft clip | smooth overdrive, bounded output | generic tone unless staged with filtering and gain recovery |
| Piecewise soft clip | tuned knee and headroom | discontinuities if derivative is not smooth |
| Polynomial shaper | controlled harmonic design | output can become unbounded; alias behavior depends on order |
| Foldback | octave/fuzz/synthetic behavior | chaotic level and strong high-frequency content |
| Asymmetric shaper | even harmonics, biased stages | DC offset and level drift |
| Slew or rate limited shaper | op-amp blur, pick softening | can dull attacks or become sample-rate dependent |
| Envelope-dependent shaper | sag, recovery, touch response | harder reset determinism and more state to test |

Use the simplest family that matches the audible target and survives measurement. A good first version is often:

```text
HPF -> pre-gain -> soft clip -> recovery LPF/shelf -> level
```

Then add asymmetry, memory, or circuit-specific behavior only when a listening or measurement fixture proves the gap.

## Static Transfer Design

Design transfer curves with explicit goals:

- **Knee**: how gently the curve bends into clipping.
- **Rail**: maximum output level.
- **Slope near zero**: small-signal gain and clean feel.
- **Symmetry**: odd/even harmonic balance.
- **Derivative continuity**: click and alias risk under fast movement.
- **Inverse level compensation**: whether output level stays musical as drive increases.

Useful pattern:

```text
driveNorm = smoothstep(drivePercent / 100)
preGainDb = lerp(minDriveDb, maxDriveDb, driveNorm)
clipAmount = lerp(soft, hard, driveNorm)
outputTrimDb = measuredCompensation(driveNorm)
```

Avoid mapping the UI knob directly to a raw mathematical coefficient unless that coefficient is already perceptually useful.

## Dynamic Waveshaping

Dynamic waveshaping changes the curve based on signal history:

- envelope-controlled knee or rail
- bias that shifts with recent signal level
- slew limiting before or after clipping
- sag-like gain reduction
- recovery filters that open or darken with drive
- feedback from output level into clipper hardness

Dynamic behavior can make a model feel alive, but it adds obligations:

- Reset must be deterministic.
- Silence must not create denormal CPU spikes.
- Bypass and preset changes must not dump state into the output.
- Offline renders must match realtime renders.
- Automation must smooth both visible controls and hidden dynamic targets.

## Control Mapping And Gain Staging

For guitar stages, control mapping is part of the model:

- Keep low-drive settings useful; do not spend half the knob on near-clean silence.
- Tune output compensation separately from the clipper transfer.
- Clamp internal gain before a solver or feedback clipper can explode.
- Treat "tone", "attack", "tight", and "brightness" controls as macros over filtering plus drive behavior when needed.
- Store measured default levels so regressions are easy to detect.

Output compensation should not erase intentional level differences. A fuzz tone-bypass switch or raw boost mode may be louder by design; protect digital clipping without flattening the musical effect.

## Implementation Notes

Hot-path rules:

- Keep APVTS access outside DSP classes.
- Precompute slow constants outside the sample loop.
- Smooth drive, level, mix, bias, tone, and mode changes.
- Sanitize non-finite values.
- Snap tiny state values to zero.
- Use `double` for coefficient or solver math when it improves stability, then return finite `float`.
- Keep exact bypass separate from enabled-but-neutral tone.

For code organization, keep a small named function for the transfer curve:

```cpp
float shapeSample (float input, float drive, float bias) noexcept
{
    const auto x = juce::jlimit (-8.0f, 8.0f, input * drive + bias);
    const auto y = std::tanh (x) - std::tanh (bias);
    return sanitize (y);
}
```

Then test the function independently from the full block.

## Measurement And Tests

Measure before changing the curve:

- static transfer curves at several drive values
- harmonic growth with 1 kHz sine
- RMS/peak output level versus drive
- DC offset after asymmetric shaping
- impulse response for state leakage or clicks
- guitar DI fixtures for low-drive cleanup, palm mutes, and lead sustain

Tests:

- disabled bypass identity
- finite output for silence, impulse, sine, noise, and extremes
- reset determinism
- smooth automation of drive and output
- no unexpected DC after the block
- output compensation stays within the product target

When aliasing is the concern, switch to `aliasing-oversampling.md` and `scripts/alias_probe_report.py`.
