# Guitar DSP Task Playbooks

## Contents

- How to use these playbooks
- Add or modify a conventional DSP block
- Build an RTNeural model loader
- Review a neural training or export run
- Diagnose latency, phase, or alignment mismatch
- Investigate aliasing or nonlinear harshness
- Add or refine cabinet IR support
- Design a release validation plan

## How To Use These Playbooks

Start with the playbook that matches the user's request, then load deeper references only when needed:

- Conventional pedal/effect code: read `guitar-signal-chain.md` and `cpp-juce-dsp-modeling.md`.
- Generic waveshaping work: read `nonlinear-waveshaping.md`.
- Diode or fuzz work: read `diode-and-fuzz-circuits.md`.
- Aliasing or oversampling work: read `aliasing-oversampling.md`.
- Tone stack work: read `tone-stack-modeling.md`.
- Tube-stage work: read `triode-and-tube-stage-approximation.md`.
- Dynamic cabinet work: read `speaker-cabinet-dynamics.md`.
- RTNeural runtime work: read `rtneural-runtime.md` and `runtime-code-patterns.md`.
- Training/export work: read `neural-modeling-workflow.md` and `neural-modeling-math.md`.
- Validation or release work: read `validation-and-release.md` and `failure-diagnosis.md`.

Prefer a measurable next step over a broad rewrite. Guitar DSP usually improves fastest when the agent can render before/after fixtures, inspect a short metric report, and then make a narrow change.

## Add Or Modify A Conventional DSP Block

1. Identify the block role: utility, dynamics, nonlinear pedal, amp/tone, cabinet, modulation, delay, reverb, or post color.
2. Keep the public class small: `prepare`, `reset`, and a `process`/`processBlock` method fed by a parameter snapshot.
3. Keep APVTS access, file paths, host state, and UI state outside the DSP class.
4. Preallocate buffers and delay lines in `prepare`; resize only when sample rate, channel count, or maximum block size changes.
5. Add parameter smoothing before listening tests. Smooth gain, wet/dry, filter cutoffs, mode crossfades, bypass ramps, and nonlinear drive.
6. Add tests before broad tuning:
   - disabled/bypass identity when promised
   - finite output at extremes
   - reset determinism
   - automation stress
   - mono/stereo routing
   - sample-rate stability
   - latency/tail behavior when relevant
7. Add a small measurement fixture for the behavior being tuned: transfer curves for drives, attack/release for dynamics, response sweeps for filters, repeat decay for delay, RT60/spectral decay for reverb, and stereo correlation for post-FX.

Do not treat a component schematic as a literal implementation mandate. Translate it into audible constraints: coupling filters, impedance-dependent tone shifts, detector timing, nonlinear transfer shape, bandwidth limits, control taper, and output gain behavior.

## Build An RTNeural Model Loader

1. Define the package contract before writing UI:
   - model JSON path
   - metadata sidecar path
   - expected sample rate
   - input/output channel count
   - latency/alignment metadata
   - validation/benchmark/aliasing summaries
2. Parse JSON and sidecars outside the audio callback.
3. Construct model objects off-thread or on the message/background thread.
4. Validate architecture and shape before publishing the model:
   - supported layer types
   - mono or stereo input size
   - known activation support
   - expected sample rate
   - metadata status
5. For stereo models, use one stateful model instance per channel unless the model is explicitly stateless and shared-state-safe.
6. Publish immutable runtime state to the audio thread using a realtime-safe handoff.
7. Keep old runtime objects alive until the audio thread can no longer see them.
8. Report warnings in UI/state, not through logging or allocation inside `processBlock`.

Useful first commands:

```bash
python skills/guitar-dsp/scripts/model_package_summary.py /path/to/model-or-package --host-sample-rate 48000
python skills/guitar-dsp/scripts/receptive_field.py /path/to/model.rtneural.json
```

## Review A Neural Training Or Export Run

1. Confirm the data contract:
   - same dry input and target performance
   - matched sample rate
   - preserved level intent
   - known polarity
   - documented alignment latency
2. Check receptive field and model family before interpreting metrics. A model with too little memory can score acceptably on short fixtures while missing low-frequency recovery and palm-mute feel.
3. Inspect ESR, RMSE, correlation, and listening renders together. Do not ship on one scalar metric.
4. Inspect ASR or aliasing reports for high-gain captures.
5. Check native RTF at the target buffer sizes and sample rates.
6. Verify the exported RTNeural JSON against Python output before blaming the plugin.
7. Package validation, benchmark, aliasing, and metadata summaries next to the model so the plugin can surface warnings.

When the model sounds wrong but metrics look good, suspect alignment, polarity, level compensation, fixture coverage, or frequency-weighted loss before changing the plugin runtime.

## Diagnose Latency, Phase, Or Alignment Mismatch

1. Separate the possible sources:
   - capture/export alignment latency
   - causal model receptive field
   - plugin-reported processing latency
   - cabinet convolution latency
   - dry/wet path mismatch
   - DAW delay compensation behavior
2. Render a dry impulse through the plugin with the suspect blocks enabled one at a time.
3. Compare dry and processed files with:

```bash
python skills/guitar-dsp/scripts/compare_audio_metrics.py dry.wav processed.wav --max-shift 2048
```

4. Confirm polarity before interpreting null tests.
5. For dry/wet effects, verify both paths include matching delay or that the wet path is mixed additively by design.
6. Update host latency only for actual delayed output, not for causal model memory.

## Investigate Aliasing Or Nonlinear Harshness

1. Identify every nonlinear stage in the enabled path.
2. Confirm input gain into each nonlinear stage. A correct clipper can sound wrong if driven 12 dB hotter than intended.
3. Render sines at 1 kHz, 5 kHz, 7 kHz, and 10 kHz at realistic drive settings.
4. Measure a coherent sine render when available:

```bash
python skills/guitar-dsp/scripts/alias_probe_report.py rendered-7khz.wav --fundamental 7000 --settle-samples 2048
```

5. Compare host-rate processing against a local oversampled or reference render.
6. Try cheap improvements before large architecture changes:
   - pre-nonlinearity bandwidth limiting
   - post-nonlinearity recovery filtering
   - DC cleanup after asymmetric stages
   - better transfer curve or diode solver
   - small local oversampling island
7. Keep full-chain oversampling as a last resort. It is often too expensive and can complicate latency and state.

Read `aliasing-oversampling.md` before choosing an oversampling factor, and read `nonlinear-waveshaping.md` before changing a known-good transfer curve.

## Add Or Refine Cabinet IR Support

1. Decide whether the stage is IR-backed only or also provides a no-IR filter path.
2. Load and resample IRs outside the audio callback.
3. Cap IR length or use partitioned convolution designed for long responses.
4. Preserve quiet IRs unless the user chooses normalization.
5. Optimize endpoints: A-only, B-only, no-IR, dry/wet, and 50/50 blend should avoid unnecessary work.
6. Publish immutable convolution state and retire old engines off the audio thread.
7. Report latency and tail changes to the host after engine swaps.
8. Test repeated load/swap/clear while audio is rendering.

## Design A Release Validation Plan

1. Start with local deterministic gates:
   - unit tests
   - model/package summary
   - native model parity
   - offline renders
   - benchmark matrix
2. Add musical measurement reports:
   - transfer curves
   - frequency responses
   - attack/release plots
   - alias spectra
   - stereo correlation
   - latency/impulse reports
3. Add host validation:
   - pluginval for supported formats
   - `auval` on macOS AU builds
   - DAW save/reopen smoke tests
   - preset/model/IR path restore tests
4. Require level-matched listening checks against the previous known-good build for tone changes.
5. Treat release notes as a technical artifact: include changed DSP behavior, known limitations, sample-rate policy, model package requirements, latency/tail behavior, and validation status.
