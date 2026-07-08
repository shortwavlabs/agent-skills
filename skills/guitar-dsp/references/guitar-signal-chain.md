# Guitar Signal Chain And DSP Blocks

## Contents

- Core chain
- Gain staging
- Mono and stereo policy
- Amp model and tone stack
- Cabinet IR
- Conventional guitar effects
- Automation and smoothing
- Block-level tests

## Core Chain

Start with a chain that matches how guitar players think about a rig, then revise only for a measured reason:

```text
tuner analysis tap, only when armed
  -> input trim or input buffer color
  -> noise gate
  -> compressor
  -> boosts, drives, overdrives, fuzzes
  -> amp input gain
  -> amp model
  -> amp tone stack / master
  -> graphic or post-amp EQ
  -> cabinet simulator or IR
  -> chorus / modulation
  -> granular, delay, reverb, ambience
  -> post color
  -> global master
  -> optional tuner mute / metronome / utility mix
```

The important reusable lesson is not the exact pedal list. It is the separation of:

- Pre-amp dynamics and nonlinearities.
- The amp core.
- Tone/EQ shaping.
- Cabinet filtering.
- Post-cab stereo and time-domain effects.

## Gain Staging

Keep gain decisions visible and stable:

- Input trim is pre-pedal and pre-amp.
- Pedal output gain belongs after the pedal and before the amp.
- Amp input gain should drive the neural or physical amp model.
- Amp master should sit after amp/tone processing.
- Output gain is final trim.
- Output meters and clip indicators should read after final trim.

For neural capture families, preserve intended output-level differences. Clean tones may be much quieter in RMS than distorted tones because they are dynamic; do not "fix" that unless the capture was wrong.

Use dB controls for user-facing level changes and convert once per block or with smoothing. Avoid hidden automatic normalization in the runtime unless it is explicitly derived from model metadata and shown or documented.

## Mono And Stereo Policy

Many guitar amp captures and RTNeural exports are mono. Be explicit:

- If the amp core is mono, fold active input channels into channel 0 before the mono core.
- Average channels or use a documented equal-power fold. Do not accidentally use only the left channel.
- Process the mono core once.
- Fan out after the amp/tone core so cabinet and post-FX can operate on the intended output channels.
- Preserve stereo from the cabinet/post-FX lane onward when the design supports it.

For stereo neural package playback, prefer one independent model instance per channel. Stateful models should not share a single RTNeural object across channels.

## Amp Model And Tone Stack

A practical neural amp stage should:

- Load/construct the model outside the audio callback.
- Reject unsupported input sizes early.
- Reset model state in `prepareToPlay()` and after model replacement.
- Read model metadata for sample rate, latency, architecture, validation, benchmark, aliasing, and output level when available.
- Track model-specific latency only when it is true plugin processing delay.

Tone-stack rules:

- Smooth gain targets around 5-20 ms for user/automation changes.
- Update coefficients at a bounded control rate instead of rebuilding every sample unless the algorithm requires it.
- Make neutral controls exact or near-exact passthrough.
- Test automation across extremes, not only static settings.
- For passive, lossy, or interactive stacks, read `tone-stack-modeling.md` before reducing the circuit to generic EQ.

Useful starting frequency landmarks:

- Depth / low resonance: around 80 Hz.
- Bass shelf: around 100-120 Hz.
- Mid peak: around 650-750 Hz.
- Treble shelf: around 3-4 kHz.
- Presence: around 3.2-4.5 kHz.

Treat these as musical defaults, not universal law.

## Cabinet IR

Cabinet simulation is part of the tone, but it is also a file-loading and latency problem.

When loading user IRs:

- Read files outside `processBlock()`.
- Support common audio formats when the host framework provides readers.
- Sum or choose channels deliberately for mono/stereo behavior.
- Resample IRs offline to the prepared sample rate.
- Cap extreme IR length for realtime cost, or use a partitioned convolution engine designed for long IRs.
- Make normalization optional or clearly documented.
- Preserve quiet captured IRs; avoid auto-boosting them unless the user asked for normalization.
- Report tail length and latency honestly.

Runtime options:

- A simple JUCE `dsp::Convolution` stage is good for a loader or MVP.
- A custom immutable convolution engine can support lock-free swaps, old-engine retirement, and fixed partition size.
- A no-IR filter path is useful: HPF/LPF can still shape tone when no IR is loaded.

Tests should cover bypass identity, no-IR finite output, non-project sample-rate IRs, missing-file rejection, repeated load/swap/clear while processing, blend endpoints, HPF/LPF automation, tail length, and latency reporting.

## Conventional Guitar Effects

Pedal and utility blocks should be self-contained classes with `prepare`, `reset`, and `processBlock` methods. Favor small parameter structs over direct APVTS access inside DSP classes.

For nonlinear pedals:

- Add a DC blocker or explicit bias cleanup after asymmetric clipping.
- Check aliasing with high-frequency tones and high-gain settings.
- Use local oversampling or substeps only when measurement/listening justifies it.
- Calibrate output level so gain changes feel intentional.
- Read `nonlinear-waveshaping.md` for generic transfer curves and `diode-and-fuzz-circuits.md` for circuit-specific fuzz/diode behavior.

For dynamics:

- Link stereo gain reduction when the effect should preserve image.
- Test attack/release on transient and sustained material.
- Include silence and near-threshold tests.

For modulation and delay:

- Smooth delay-time changes or use interpolation/crossfade.
- Bound feedback under all automation paths.
- Report meaningful tail length for hosts.
- Test zero mix/zero level as exact or ramped dry passthrough.

For tuner/metronome/looper utilities:

- Gate expensive analysis behind an armed/visible state where possible.
- Keep recording/file writes off the audio thread.
- Treat utility state restore as host-facing behavior, not only UI state.

## Automation And Smoothing

Automation is where many guitar plugins fail:

- Smooth gain, wet/dry mix, filter frequency, and coefficient-changing parameters.
- Reset smoothing state deliberately on bypass transitions when exact passthrough matters.
- Avoid rebuilding heavy objects in response to every block if a control-rate update is enough.
- If a coefficient flip can produce instability, constrain parameter ordering or crossfade between stable states.

Use `juce::SmoothedValue` in JUCE code or a small sample-rate-derived one-pole smoother in framework-neutral code.

## Block-Level Tests

Every production DSP block should have tests for:

- Bypass sample identity when the product promises exact bypass.
- Finite output at parameter extremes.
- Reset determinism: same input after reset gives same output.
- Sample-rate stability at common rates.
- Automation safety for abrupt parameter changes.
- Channel routing: mono, stereo, linked stereo where expected.
- Latency and tail length when relevant.
- Aliasing/DC behavior for nonlinear stages.

For guitar tone blocks, add at least one test that reflects musical intent: drive grows harmonics, tone darkens/brightens expected bands, gate closes silence without chopping open notes, cabinet filtering reduces implausible full-range energy, and post-FX preserve or intentionally widen stereo image.
