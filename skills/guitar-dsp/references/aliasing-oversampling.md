# Aliasing And Oversampling

## Contents

- When to use this reference
- Aliasing model
- Diagnosis workflow
- First-line alias controls
- Oversampling decision ladder
- Oversampling island design
- ADAA and antiderivative options
- Measurement workflow
- JUCE/C++ notes
- Tests and acceptance criteria

## When To Use This Reference

Read this when nonlinear guitar DSP has sample-rate artifacts, fizz, brittle highs, alias residue, or oversampling questions.

This reference intentionally does not teach transfer-curve design. Read `nonlinear-waveshaping.md`, `diode-and-fuzz-circuits.md`, or `triode-and-tube-stage-approximation.md` for the model itself, then return here to control sample-rate artifacts.

## Aliasing Model

Any nonlinear operation creates new frequencies. If those frequencies exceed Nyquist, they fold back into the audible band as inharmonic aliases.

For a sine input at frequency `f`, a static nonlinearity can create:

```text
2f, 3f, 4f, ...
```

At sample rate `Fs`, frequencies above `Fs / 2` fold back:

```text
alias(f_h) = abs(((f_h + Fs / 2) mod Fs) - Fs / 2)
```

Implications:

- A 1 kHz probe may look clean while a 7 kHz probe aliases badly.
- Higher drive creates more high-order harmonics.
- Bright pre-emphasis before clipping can worsen aliasing.
- Post-lowpass filtering cannot remove aliases that already folded into the guitar band.
- Oversampling only helps when the up/down filters and nonlinear island are correct.

Do not call all harshness aliasing. Fizz can also come from wrong gain staging, too much pre-clip treble, missing cabinet filtering, DC bias, bad output compensation, coefficient zipper noise, or a transfer curve that simply sounds bad.

## Diagnosis Workflow

1. Identify every nonlinear stage in the enabled path.
2. Render the stage alone if possible.
3. Confirm pre-clip level and bandwidth.
4. Render coherent sine probes at 1, 3, 5, and 7 kHz.
5. Compare host-rate output against a higher-rate or oversampled reference.
6. Level-match listening renders before declaring the cleaner plot better.

Use the helper:

```bash
python skills/guitar-dsp/scripts/alias_probe_report.py rendered-7khz.wav --fundamental 7000 --settle-samples 2048
```

The helper expects a coherent sine render. If the fundamental is not close to an FFT bin for the analyzed window, render a different duration or treat the report as a warning.

## First-Line Alias Controls

Try these before broad oversampling:

1. **Gain-stage audit**
   - Confirm input level into each nonlinear stage.
   - Check RMS/peak before and after the gain cell.

2. **Pre-nonlinearity bandwidth limit**
   - Remove excessive high-frequency energy before clipping.
   - Tune against guitar DI, not only sine probes.

3. **Smoother transfer**
   - Replace discontinuities with finite-slope knees where the target allows it.
   - Smooth mode and drive automation.

4. **Post-nonlinearity recovery filter**
   - Shape legitimate harmonics and reduce harshness.
   - Remember this cannot remove folded aliases.

5. **Narrow the nonlinear island**
   - Keep only the truly nonlinear work inside any expensive upsampled path.

## Oversampling Decision Ladder

Use oversampling when it solves a measured and audible problem.

1. **Stay host-rate** when the stage is mild, bandwidth-limited, and probes/listening are acceptable.
2. **Improve the transfer and filtering first** when the shaper is a placeholder or pre/post bandwidth is obviously wrong.
3. **Use a local 2x island** for moderate clipping where 5 to 7 kHz probes fail at 44.1/48 kHz.
4. **Use a local 4x island** for high-gain drives and fuzzes where 2x still leaves obvious aliases.
5. **Use 8x only for research or extreme cases** when CPU, latency, and listening justify it.
6. **Avoid full-chain oversampling by default** because it wastes CPU on clean filters, utility blocks, cabinet convolution, delay/reverb, and routing.

## Oversampling Island Design

Use a narrow boundary:

```text
host-rate pre-conditioning
  -> upsample filter
  -> oversampled nonlinear core
  -> oversampled recovery filter when needed
  -> downsample filter
  -> host-rate tone/output path
```

Rules:

- Allocate and initialize oversamplers in `prepare`.
- Reset oversampler state on block reset and sample-rate change.
- Keep dry paths latency-matched when used inside dry/wet effects.
- Smooth bypass around the island.
- Decide whether the oversampling filter adds true host-reported latency.
- Split host blocks into prepared-size chunks when necessary.
- Benchmark Release builds at target sample rates and buffer sizes.

Filter choice matters:

- Cheap filters can leave imaging or downsampling residue.
- Linear-phase filters can add latency and pre-ringing.
- IIR/polyphase filters are usually practical for realtime guitar stages, but validate dry/wet phase effects.

## ADAA And Antiderivative Options

Antiderivative anti-aliasing can reduce aliasing for known memoryless functions without a full oversampling island.

Use ADAA when:

- the nonlinearity is a smooth memoryless function
- CPU must stay low
- dry/wet phase and latency must stay simple
- small `x[n] - x[n-1]` differences are handled safely

Avoid or postpone ADAA when:

- the model includes feedback, diode solving, slew limiting, envelope memory, or moving bias
- the function has hard discontinuities
- local oversampling is simpler and fast enough

Good candidates: `tanh`, `atan`, soft-clip, and polynomial stages. Poor candidates: full fuzz circuits with passive loading, diode feedback, and envelope-dependent behavior.

## Measurement Workflow

Render coherent sine probes:

- 1 kHz for transfer sanity
- 3 kHz for midrange harmonic growth
- 5 kHz and 7 kHz for 44.1/48 kHz alias stress
- 10 kHz for high-rate or bright-input stress

Sweep:

- drive low, default, high, maximum
- tone dark, default, bright
- oversampling off, 2x, 4x if implemented
- host rate 44.1, 48, and 96 kHz when supported

Measure:

- harmonic energy
- non-harmonic energy
- alias-to-signal ratio
- DC offset
- peak/RMS level
- CPU per sample or realtime factor

## JUCE/C++ Notes

Typical local island shape:

```cpp
oversampling = std::make_unique<juce::dsp::Oversampling<float>> (
    static_cast<size_t> (channels),
    2,
    juce::dsp::Oversampling<float>::filterHalfBandPolyphaseIIR,
    true,
    false);
oversampling->initProcessing (static_cast<size_t> (maxBlockSize));
```

Hot-path rules:

- Do not construct or resize oversamplers in `processBlock`.
- Do not allocate scratch buffers in `processBlock`.
- Keep nonlinear parameters smoothed before the oversampled core.
- Use one oversampled state per channel unless intentionally processing mono.
- Test exact bypass separately; oversampling filters can break identity if left in path.

## Tests And Acceptance Criteria

- Alias report improves or stays below the product threshold.
- CPU remains within budget at small buffers.
- Reset determinism holds with oversampling enabled.
- Dry/wet paths remain phase and latency aligned.
- Bypass and oversampling mode changes are click-safe.
- Level-matched listening prefers the new path.

Treat alias reports as decision support, not final audibility truth.
