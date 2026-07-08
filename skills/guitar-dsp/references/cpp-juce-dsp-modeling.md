# C++ And JUCE DSP Modeling

## Contents

- Source of these lessons
- DSP class shape
- Circuit-to-DSP translation
- Nonlinear pedal modeling
- Dynamics and gates
- Tone, EQ, and cabinet stages
- Modulation, delay, and reverb
- Utility DSP
- Performance lessons
- Measurement-first tuning

## Source Of These Lessons

This reference distills reusable lessons from building a full guitar amp modeler with standalone DSP blocks for input buffering, gates, compressors, overdrives, fuzz, amp/tone processing, graphic EQ, cabinet simulation, modulation, delay, reverb, tuner, metronome, and final post color. Keep the guidance generic; do not copy project-specific branding, parameter IDs, or product assumptions unless the target repo already uses them.

The key lesson is that "sounds right" usually came from combining circuit-informed topology, musical control mapping, smoothing, measurement fixtures, and host-safe runtime architecture. The best block was rarely the first literal translation of a schematic.

## DSP Class Shape

Use a small reusable shape for most blocks:

```cpp
struct BlockParameters
{
    bool enabled = false;
    float amount = 50.0f;
    float levelDb = 0.0f;
};

class Block
{
public:
    void prepare (double sampleRate, int maxBlockSize, int numChannels);
    void reset() noexcept;
    void processBlock (juce::AudioBuffer<float>& buffer,
                       const BlockParameters& parameters) noexcept;
};
```

Rules:

- Keep DSP classes independent from UI and APVTS.
- Preallocate scratch buffers, delay memory, oversamplers, and convolution state in `prepare`.
- Normalize and clamp parameter snapshots once per block.
- Store one state object per audio channel when filters, detectors, or delays carry history.
- Use `noexcept` for hot-path methods when the surrounding codebase permits it.
- Sanitize non-finite samples and snap tiny states to zero in long-running feedback/filter paths.

## Circuit-To-DSP Translation

Translate analog references into audible DSP constraints:

- Coupling capacitors become high-pass behavior and DC cleanup.
- Tone networks become either RBJ filters, one-pole tilt stages, or small nodal solvers when interaction matters.
- Pots become shaped control laws, not always linear percentages.
- Diodes and op-amps become transfer curves, feedback solvers, slew/rail limits, and recovery filtering.
- Bucket-brigade or analog delay behavior becomes bandwidth loss, interpolation, clock/modulation artifacts, and feedback damping.
- VCA/OTA behavior becomes detector timing, gain-computer curves, saturation, and program-dependent release.

Do not expose every component as a UI control. Hide calibration constants behind a simple musical surface.

## Nonlinear Pedal Modeling

For deeper transfer-curve decisions, read `nonlinear-waveshaping.md`. For diode/fuzz circuits, read `diode-and-fuzz-circuits.md`. For aliasing and oversampling decisions, read `aliasing-oversampling.md`.

A good guitar drive/fuzz block usually needs more than a waveshaper:

```text
input conditioning
  -> pre-emphasis / low-end tightening
  -> gain cell
  -> nonlinear clipper or solver
  -> recovery filtering and DC cleanup
  -> tone network
  -> output level compensation
```

Useful techniques:

- Shape drive controls so low and mid knob ranges are playable.
- Derive stepped controls from the reference behavior, then calibrate into a musically useful range.
- Use local oversampling or multiple nonlinear substeps only around the nonlinear island.
- Add pre-clip and post-clip filtering before reaching for full-chain oversampling.
- Use DC blockers after asymmetric or biased clipping.
- Tune output compensation separately from the clipping transfer so high gain does not collapse or jump in loudness.
- Test alias spectra and transfer curves, then level-match listening clips.

For fuzzes with passive tone networks, a small nodal solver can be worth the complexity when the tone control interacts strongly with loading and source impedance. For simpler drives, a cascade of high-pass, low-pass, shelves, peaking filters, and a calibrated clipper is often easier to tune and validate.

## Dynamics And Gates

Pedal-style dynamics should feel fast and playable before they look like studio processors.

For gates:

- Keep detector/key path independent from the audio path.
- Use detector conditioning filters so DC, thumps, and hiss do not dominate.
- Work in dB for threshold, range, and knee math.
- Add hysteresis or a soft knee to avoid chatter.
- Link stereo gain reduction when independent closure would shift the image.
- Treat a sidechain/key input as a product decision, not an automatic feature.

For compressors:

- Separate dry and wet paths deliberately.
- Keep dry/wet polarity and latency matched.
- Model Sustain or Compression as several hidden variables: detector drive, ratio/control amount, makeup gain, color drive, and release behavior.
- Let attack/release depend on switch mode or program level when that is part of the pedal feel.
- Use tone shaping on the intended path only. A wet-path tone control behaves differently from a global EQ.
- Do not reset detector state abruptly during bypass unless the bypass ramp has reached silence.

## Tone, EQ, And Cabinet Stages

Tone controls and cabinet stages can be clean utility DSP or part of the modeled instrument. Be explicit.

Tone/EQ:

- Use neutral passthrough when all controls are flat.
- Smooth filter gains and frequencies over roughly 5-20 ms.
- Rebuild coefficients at a bounded control interval or crossfade when coefficient jumps can click.
- Validate response windows, not only finite output.

For passive or interactive tone networks, read `tone-stack-modeling.md`.

Cabinet:

- Load, resample, normalize, and construct convolution engines outside the callback.
- Sum or route IR channels deliberately.
- Cap IR length or use a partitioned engine with known latency.
- Optimize no-IR and blend endpoint paths.
- Preserve quiet captured IRs unless normalization is explicitly enabled.
- Report latency and tail only when the active engine actually needs them.

For speaker compression, resonance, breakup, and dynamic EQ beyond a static IR, read `speaker-cabinet-dynamics.md`.

## Modulation, Delay, And Reverb

Time-domain guitar effects need dry safety and bounded feedback more than elaborate UI.

Modulation:

- Use interpolated delay lines and smoothed delay-time motion.
- Crossfade routing/mode changes.
- Keep spread/width mono-compatible unless the product intentionally sacrifices mono.
- Test stereo correlation and reset determinism.

Delay:

- Clamp feedback before smoothing and after any modulation paths.
- Add bandwidth loss or damping inside the feedback loop for analog/tape/PT-style behavior.
- Smooth time changes or use interpolation/crossfade to avoid clicks.
- Keep BPM sync edge cases bounded at slow tempos and long divisions.

Reverb:

- Preserve dry stereo unless the design is intentionally mono-in/stereo-out.
- Decorrelate wet returns.
- Bound tank feedback under automation.
- Test zero mix as passthrough, finite tails, and reported tail length.

## Utility DSP

Utility blocks still need audio-engine discipline:

- Tuner analysis should run only when armed or visible enough to justify CPU.
- Publish tuner snapshots atomically; format note names and strings on the UI thread.
- Metronomes should render from host tempo/position when available and from an internal clock when not.
- Recording and looper file writes must stay off the audio thread.
- Utility mutes and mixes need the same smoothing and state-restore tests as tone effects.

## Performance Lessons

The fastest wins usually came from removing work from the hot path:

- Collapse mono amp/pre-amp cores deliberately instead of processing duplicated stereo work.
- Hoist repeated buffer pointer lookups out of inner loops.
- Cache coefficient sets and mode-dependent constants.
- Add fast paths for disabled blocks, zero mix, zero level, and blend endpoints.
- Avoid clearing large buffers on every bypass transition.
- Keep old model/IR/convolution object destruction off the audio thread.
- Benchmark Release builds; Debug results can mislead DSP priorities.
- Measure full-chain CPU at small buffers and common sample rates before optimizing a block in isolation.

Do not add per-sample logging, allocation, locks, `shared_ptr` churn, file I/O, JSON parsing, or UI calls to get measurements. Use an offline harness or conditional non-realtime benchmark target.

## Measurement-First Tuning

Pair listening with small reports:

- Drives/fuzzes: static transfer, harmonic spectra, alias spectra, output RMS vs drive, DC offset.
- Gates: open/close curves, chatter around threshold, linked-stereo behavior, decay preservation.
- Compressors: static curves, tone-burst attack/release, blend null checks, wet-path tone response.
- EQ/tone: swept response at multiple sample rates, automation click tests.
- Cabinet: impulse alignment, blend endpoints, no-IR filter response, IR energy/latency.
- Delay/reverb: impulse repeat decay, modulation sidebands, RT60, spectral decay, stereo correlation.

When an effect finally sounds right, preserve that behavior with fixtures before continuing. Musical calibration is a product asset, not just implementation detail.
