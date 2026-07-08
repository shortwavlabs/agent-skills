# RTNeural Runtime Integration

## Contents

- Runtime modes
- CMake and backends
- Model lifecycle
- Stereo and mono state
- Metadata and warnings
- Latency semantics
- Sample-rate policy
- Output level compensation
- Realtime handoff patterns

## Runtime Modes

Use one of two loading modes:

1. Embedded factory models:
   - Add RTNeural JSON files with the host framework's binary data system.
   - Parse at startup or another non-audio time.
   - Store per-model metadata in plugin state for UI/status display.
   - Good for fixed products and factory amp channels.
2. User-loaded export packages:
   - Let the user select a folder containing `model.rtneural.json`.
   - Opportunistically read validation, benchmark, aliasing, and package metadata.
   - Persist selected model/package paths in DAW state.
   - Warn and fall back safely when files are missing on restore.

Raw JSON loading is useful for debugging, but package loading is better for product decisions because it carries proof about quality and runtime cost.

## CMake And Backends

For RTNeural in JUCE/CMake projects:

- Prefer a known local checkout for development when the project depends on forked layers or patches.
- Allow an override path such as `RTNEURAL_LOCAL_PATH=/path/to/RTNeural`.
- Disable RTNeural tests, benches, and examples in plugin builds.
- Select exactly one backend for a given build: Eigen, STL, or xsimd.
- Use Eigen as a strong default for larger WaveNet-style models, but benchmark shape-specific results.
- Build backend-specific validators when comparing exports.

Dynamic JSON is the compatibility baseline. Static `ModelT` or generated model code is an optimization path after dynamic JSON passes parity and profiling shows the cost matters.

## Model Lifecycle

Never parse JSON or construct RTNeural models in `processBlock()`.

Load flow:

1. Resolve the selected package folder or JSON file.
2. Open and parse JSON on a non-audio thread.
3. Construct the model instances.
4. Validate input and output sizes.
5. Read package metadata.
6. Reset model state.
7. Publish an immutable model set to the audio thread.
8. Retain or safely retire the previous model set outside the callback.

For RTNeural dynamic JSON:

```cpp
auto model = RTNeural::json_parser::parseJson<float>(stream);
```

Check:

- `model != nullptr`
- model has layers
- input size is supported, usually `1`
- output size is supported, usually `1`
- `forward()` produces finite output on a smoke input

Reset model state in:

- `prepareToPlay()`
- model replacement
- explicit user reset if the product has one

Avoid surprising resets during continuous playback unless transport-reset behavior is a documented feature.

## Stereo And Mono State

RTNeural recurrent/stateful and causal Conv1D models carry internal state.

For stereo package playback:

- Parse the JSON twice.
- Keep one model instance for left and one for right.
- Use channel index clamped to the number of instances.
- Reset both models together.

For intentionally mono amp cores:

- Fold active input channels before the core.
- Process one model instance.
- Fan out after amp/tone processing.

Do not share one RTNeural object across channels unless the architecture itself is multi-channel and has been validated that way.

## Metadata And Warnings

Read metadata outside the callback and cache UI strings/status flags.

Useful package/model fields:

- `metadata.sample_rate`
- `metadata.latency_samples`
- `metadata.architecture`
- `metadata.loss`
- `metadata.rtneural_commit`
- `package.quality.esr`
- `validation.status`
- `validation.max_abs_error`
- `aliasing.status`
- `aliasing.worst_asr`
- `aliasing.average_asr`
- `benchmark.summary.realtime_factor_worst`
- `benchmark.model_info.receptive_field_samples`
- `benchmark.model_info.conv1d_layers`
- `benchmark.model_info.size_bytes`

Warnings to surface:

- No model loaded.
- Raw JSON loaded without package metadata.
- Model sample rate differs from host sample rate.
- Validation status is not `pass`.
- Aliasing status is not `pass`.
- Native realtime headroom is low.
- Model input size is not supported.
- Cab IR is enabled but no IR is loaded.
- Restored file path is missing.

Warnings should never allocate, parse, or touch files in the audio callback.

## Latency Semantics

Separate three concepts:

1. Export alignment latency:
   - Stored as metadata from capture preparation.
   - Describes how the target was aligned for training/export.
   - Not automatically plugin latency.
2. Receptive field:
   - Number of previous samples a causal Conv1D model can depend on.
   - Model memory, not lookahead.
   - Not automatically host-reported latency.
3. Plugin processing latency:
   - Report with JUCE `setLatencySamples()` only for real delayed output.
   - Examples: latency-introducing convolution, lookahead, linear-phase filters, or oversampling filters with uncompensated delay.

Causal RTNeural inference can usually report zero plugin latency. Add cabinet, lookahead, or oversampling latency only when those stages actually delay the signal.

## Sample-Rate Policy

Model behavior is tied to training sample rate. Frequency response, nonlinear behavior, receptive-field time scale, and aliasing all change when the host rate changes.

Recommended policy:

1. Require matching sample rate and show a clear warning when mismatched.
2. Support separate exports per sample rate.
3. Add explicit resampling or oversampling only after measurement and listening.

Do not silently run a 48 kHz model in a 96 kHz session and call it correct.

## Output Level Compensation

When embedded factory models include output RMS/loss metadata, use it carefully:

- Choose a benchmark RMS across the loaded model family.
- Lift quieter models toward the loudest model when that matches product intent.
- Clamp gain to a safe maximum, such as +24 dB.
- Never attenuate below unity unless the user expects auto-level to reduce louder captures.
- Store/report compensation gain so debugging model loudness is possible.

For user-loaded models, prefer explicit user gain and package metadata display over hidden automatic normalization.

## Realtime Handoff Patterns

Good enough for a simple loader:

- Retain loaded `ModelSet` objects for the processor lifetime.
- Publish `ModelSet*` through `std::atomic<ModelSet*>`.
- Audio thread reads the raw pointer and never owns/destroys it.

Better for production:

- Construct model/IR engines on a worker.
- Publish immutable raw pointers.
- Keep ownership in non-audio containers.
- Retire old engines after a grace period or message-thread drain.

Avoid:

- `shared_ptr` refcount churn in the audio callback.
- Atomic `shared_ptr` load/store on every block if a raw pointer publication pattern is possible.
- Deleting old model/IR data from the audio thread.
- Holding locks around model access in `processBlock()`.
