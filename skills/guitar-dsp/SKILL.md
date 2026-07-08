---
name: guitar-dsp
description: Design, implement, debug, train, and validate guitar amp/effects DSP systems, especially realtime C++/JUCE plugins, C++ DSP block modeling, nonlinear waveshaping, aliasing and oversampling strategy, tone stack modeling, diode/fuzz circuits, triode and tube stage approximation, speaker cabinet dynamics, RTNeural/neural amp models, cabinet IRs, pedal chains, capture/training/export workflows, neural modeling math theory, plugin validation, and DAW-safe release checks. Use when building guitar amp modelers, pedal emulations, neural audio model training/export, RTNeural loaders, cabinet simulators, tone stacks, guitar-focused realtime DSP, DSP measurement harnesses, or troubleshooting guitar plugin tone quality, latency, CPU, aliasing, oversampling, metrics, losses, or host behavior.
---

# Guitar DSP

## Overview

Use this skill for guitar-centric DSP work that spans tone, realtime safety, C++/JUCE DSP modeling, neural model capture/training, RTNeural runtime integration, and host validation. It complements:

- Load `juce-plugin` as well for JUCE API usage, AudioProcessor/APVTS structure, CMake/plugin formats, UI, assets, signing, validation, or host lifecycle.
- Load `dsp` as well for low-level filter/effect cookbook implementations.
- Load `dsp-engineer` as well for spectral analysis, measurements, aliasing experiments, FFT workflows, or prototype reasoning.

## Workflow

1. Classify the task:
   - Conventional DSP: pedals, tone stacks, EQ, cabinet, delay, reverb, tuner, metronome, looper.
   - Nonlinear DSP: waveshaping, clipping, diode/fuzz circuits, tube-like stages, aliasing, DC, harmonic measurement, oversampling.
   - Tone and cabinet modeling: tone stacks, presence/depth, cabinet IR, speaker dynamics, cabinet compression.
   - C++/JUCE DSP modeling: block class shape, parameter snapshots, smoothing, circuit-to-DSP translation, tests, measurement fixtures.
   - Neural modeling: capture, alignment, training preset selection, export package validation.
   - Runtime integration: RTNeural model loading, inference, sample-rate policy, model metadata, state restore.
   - Product validation: tests, measurement harnesses, plugin validation, DAW smoke, release gates.
2. Read only the reference files needed for that task.
3. Keep the audio callback hard-realtime: no file I/O, JSON parsing, model construction, IR loading, allocations, locks, UI calls, logging, or object destruction that could touch data read by the audio thread.
4. Validate tone and behavior with measurable checks before polishing UI: bypass identity, finite output, reset determinism, automation safety, latency, tail reporting, CPU headroom, aliasing, and DAW state restore.

## Reference Map

| Reference | Read when |
| --- | --- |
| `references/task-playbooks.md` | Need step-by-step workflows for common guitar DSP tasks: conventional blocks, RTNeural loaders, training/export review, latency diagnosis, aliasing investigation, cabinet support, or release validation. |
| `references/failure-diagnosis.md` | Debugging audible or host failures: bad tone despite metrics, clicks, zipper noise, aliasing, gate chatter, stereo image shift, preset/model/IR restore bugs, or validation failures. |
| `references/guitar-signal-chain.md` | Designing amp/effects order, mono/stereo routing, gain staging, cabinet IR, pedal/tone-stack behavior, or DSP block tests. |
| `references/cpp-juce-dsp-modeling.md` | Implementing or reviewing C++/JUCE DSP blocks for gates, compressors, drives, fuzzes, tone/EQ, cabinet, modulation, delay, reverb, tuner/metronome, or post color. |
| `references/nonlinear-waveshaping.md` | Designing or reviewing memoryless/dynamic waveshapers, transfer curves, asymmetry, output compensation, nonlinear control mapping, or harmonic-growth tests. |
| `references/aliasing-oversampling.md` | Diagnosing aliasing, choosing local oversampling islands, using ADAA, measuring harmonic/non-harmonic energy, or handling nonlinear CPU/latency tradeoffs. |
| `references/tone-stack-modeling.md` | Modeling amp tone stacks, pedal tone controls, passive loaded networks, active EQ macros, presence/depth controls, smoothing, and response tests. |
| `references/diode-and-fuzz-circuits.md` | Modeling diode clippers, feedback clipping, op-amp diode solvers, fuzz circuits, bias/loading behavior, tone bypass, and fuzz-specific tests. |
| `references/triode-and-tube-stage-approximation.md` | Approximating tube preamp/power stages, triode-like curves, grid/cathode/coupling memory, sag, presence/depth, and tube-stage tests. |
| `references/speaker-cabinet-dynamics.md` | Adding dynamics beyond static IRs: speaker compression, resonance, excursion, breakup, dynamic EQ, impedance-style behavior, and cabinet dynamic tests. |
| `references/neural-modeling-workflow.md` | Preparing dry/target captures, choosing WaveNet-family training presets, aligning latency, exporting RTNeural packages, or interpreting validation reports. |
| `references/neural-modeling-math.md` | Need the math behind causal TCN amp modeling: receptive field, latency alignment, ESR/RMSE/correlation, checkpoint scoring, pre-emphasis/STFT losses, ASR, RTF, and architecture tradeoffs. |
| `references/rtneural-runtime.md` | Loading embedded or user-selected RTNeural JSON, choosing dynamic vs static models, handling stereo state, metadata warnings, sample-rate mismatch, and plugin latency semantics. |
| `references/runtime-code-patterns.md` | Need compact C++ runtime patterns for parameter snapshots, model/IR handoff, per-channel model state, smoothing, latency/tail updates, or test target shape. |
| `references/validation-and-release.md` | Building test plans, measurement harnesses, native validator runs, aliasing reports, DAW smoke tests, pluginval/auval gates, and release checklists. |
| `references/example-prompts.md` | Need realistic prompts to test or demonstrate this skill's intended use cases. |

## Helper Scripts

| Script | Use for |
| --- | --- |
| `scripts/model_package_summary.py` | Inspect an RTNeural JSON or package folder for layers, Conv1D receptive field, metadata, validation/aliasing/benchmark sidecars, and warnings. |
| `scripts/receptive_field.py` | Compute causal Conv1D receptive field and lookback samples from RTNeural/Keras-style JSON. |
| `scripts/compare_audio_metrics.py` | Compare two WAV renders for alignment lag, polarity, RMSE, ESR, correlation, peak error, and DC offset. |
| `scripts/alias_probe_report.py` | Estimate harmonic and non-harmonic energy from a coherent sine WAV render of a nonlinear stage. |

## Default Decisions

- Prefer 48 kHz mono WAV capture for neural models unless the project has a measured reason to differ.
- Preserve capture/output level intent; do not normalize each target independently unless it fixes a documented recording mistake.
- Keep time-based effects out of v1 neural amp/pedal captures unless deliberately researching unsupported behavior.
- Treat mono neural amp cores explicitly: fold stereo input to mono by averaging before the mono core, then fan out after amp/tone processing so cabinet and post-FX can remain stereo.
- For stereo neural package playback, use one RTNeural model instance per channel; recurrent and causal Conv1D models carry state and should not share one model object across channels.
- Parse RTNeural JSON and load IRs outside `processBlock()`. Publish immutable model/IR state to the audio thread with atomics or another realtime-safe handoff.
- Do not silently run a model at the wrong sample rate. Warn, require a matching export, or add an explicitly measured resampling/oversampling path.
- Do not confuse export alignment latency, WaveNet receptive field, and plugin processing latency.
- Prefer dynamic RTNeural JSON for compatibility and proof-of-correctness. Consider static/generated models only after benchmark data shows dynamic JSON is the bottleneck.

## Implementation Shape

For a production guitar modeler, a proven baseline chain is:

```text
input trim / input buffer
  -> gate
  -> compressor
  -> drive / fuzz / boost pedals
  -> neural amp model
  -> amp tone stack / post-amp EQ
  -> cabinet IR or cabinet filter path
  -> modulation
  -> delay
  -> reverb
  -> post color / global master
  -> tuner mute / metronome / utility output
```

Adjust the order deliberately and encode the choice in tests. For amp-head captures, keep cabinet IR optional and post-neural; for amp-plus-cab captures, avoid applying a second cabinet unless the user wants that sound.

## Validation Minimum

Before calling guitar DSP work done:

- Run unit tests for every changed DSP block and processor-level routing path.
- Include bypass, finite output, reset determinism, channel routing, and automation stress checks.
- Benchmark Release builds at small buffers and the target sample rates.
- Validate exported RTNeural models with Python parity, native RTNeural parity, runtime benchmark, and aliasing report when neural models are involved.
- Run host validation for plugins: AU validation on macOS when building AU, pluginval for AU/VST3 when available, and at least one DAW session save/reopen smoke.
