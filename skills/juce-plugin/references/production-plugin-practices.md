# Production Plugin Practices

## Contents

- When to use this reference
- Build structure
- Processor structure
- Parameters and state
- Asset and model loading
- Realtime callback rules
- Tests and measurement targets
- Host validation and release gates

## When To Use This Reference

Read this when moving from a minimal JUCE plugin to a product-shaped plugin with many DSP blocks, external assets, model files, IRs, presets, MIDI mapping, tests, measurement tools, and DAW validation. It complements the general JUCE references by focusing on engineering practices that keep a large plugin maintainable and host-safe.

## Build Structure

Use CMake options to separate development convenience from validation:

- Enable `COPY_PLUGIN_AFTER_BUILD` only for plugin audition builds.
- Disable bundle copying for test and measurement builds.
- Keep test and measurement targets separate from plugin formats.
- Make dependency paths explicit and overridable.
- Fail early when required local dependencies are missing, or use a pinned fetch fallback deliberately.
- Link only required JUCE modules; add `juce_dsp` explicitly for DSP chains and convolution.
- Use `juce_add_binary_data` for embedded models, presets, IRs, or image assets that should ship inside the binary.

Current JUCE CMake practice still centers on `juce_add_plugin`, which creates the plugin target and format-specific build products. Keep manufacturer and plugin codes unique and valid for AU/VST compatibility. Use `NEEDS_WEB_BROWSER` only when the plugin actually embeds a web UI.

For multi-target projects, include the same DSP source files in:

- The plugin target.
- A CTest/Catch2 or similar test executable.
- Optional Release-only measurement executable.

Generated JUCE headers and binary data headers often live under the build tree. Test and measurement targets may need include directories for the plugin artefact `JuceLibraryCode` and binary data `JuceLibraryCode`.

## Processor Structure

Keep the processor as the orchestration layer:

- Own APVTS, parameters, state serialization, meters, latency, tail reporting, and host-facing file/status metadata.
- Own DSP block instances and call their `prepare`, `reset`, and `processBlock` methods.
- Keep DSP blocks independent of APVTS; pass small parameter structs into DSP code.
- Prepare all blocks in `prepareToPlay()` using the actual sample rate, output channel count, and a safe maximum block size.
- Reset stateful blocks in `prepareToPlay()` and after loading new models/assets.
- Clear output channels above the active input channel count at the start of `processBlock()`.
- Use `juce::ScopedNoDenormals` at the top of the audio callback.
- Update `setLatencySamples()` when active delayed stages change.

For mono/stereo support, make the policy explicit in `isBusesLayoutSupported()`. If the plugin supports mono and stereo only, reject mismatched input/output layouts and return true only for mono or stereo.

## Parameters And State

Use APVTS with a `ParameterLayout` constructed from `std::unique_ptr<juce::RangedAudioParameter>` objects. Cache `getRawParameterValue()` pointers in the processor constructor and read those atomics in the audio callback.

Useful patterns:

- Helper functions for repeated bool, choice, and float parameter creation.
- Stable parameter IDs; do not rename IDs casually once sessions/presets exist.
- `juce::ParameterID { id, version }` for modern parameter construction.
- Separate non-parameter state in the APVTS ValueTree: selected file paths, display names, status strings, preset metadata, and version markers.
- Persist loaded model, package, preset, IR, or sample paths in `getStateInformation()`.
- On restore, load missing files safely and report visible warnings instead of failing the processor.

Do not do message-thread work from parameter callbacks. If parameter changes need preset-dirty tracking or UI notification, set an atomic flag in the listener and publish from a `juce::Timer` or message-thread path.

For user-facing controls that can click or zipper, smooth values with `juce::SmoothedValue` or a DSP-block-local smoother. Current JUCE docs expose `SmoothedValue` helpers for applying smoothly interpolated gain; use the concept for gain and adapt it carefully for filters.

## Asset And Model Loading

File-backed assets belong outside `processBlock()`:

- Model JSON parsing.
- Neural model construction.
- IR file loading.
- Preset file reads/writes.
- Looper/recorder disk writes.
- Large image or binary data decoding.

Embedded assets:

- Use `juce_add_binary_data` when the asset is fixed at build time.
- Parse embedded JSON from memory on a non-audio path.
- Store status and metadata in state so the UI can display it.

User-selected assets:

- Resolve folder/file selections before loading.
- For package folders, expect a known filename such as `model.rtneural.json`.
- Read metadata opportunistically, but keep audio safe if metadata is absent.
- Restore paths from DAW state and show missing-file warnings.
- Prefer background workers for production loads that may block.

For realtime publication, publish immutable raw pointers or lightweight handles to the audio thread. Keep ownership and retirement off the audio thread. Avoid reference-count churn in the callback when a raw pointer plus non-audio ownership list will work.

## Realtime Callback Rules

Inside `processBlock()`:

- Read cached atomics and immutable pointers.
- Process already prepared DSP and already constructed models.
- Update lightweight atomics for meters or observations.
- Keep stack allocations small and bounded.

Never do:

- File I/O.
- JSON/XML parsing.
- Model or convolution engine construction.
- Heap allocation or container growth.
- Locking or blocking waits.
- UI calls.
- Logging/string formatting.
- Object destruction that could free data read by another callback.

If a JUCE helper might allocate, lock, or message the UI, assume it is not callback-safe until inspected.

## Tests And Measurement Targets

Use tests for both DSP blocks and processor behavior.

DSP block tests:

- Bypass identity.
- Finite output at extremes.
- Reset determinism.
- Sample-rate stability.
- Automation safety.
- Stereo routing/linking.
- Latency/tail behavior.

Processor tests:

- Parameter IDs exist and ranges make sense.
- Bus layouts accept/reject the intended channel sets.
- Model/asset load metadata is reflected in state.
- State save/restore preserves paths and parameters.
- Missing files fail safely.
- Latency updates when delayed stages are enabled or replaced.

Measurement target:

- Build Release-only.
- Benchmark per-stage and full-chain timing at target sample rates and buffer sizes.
- Include expensive stages such as neural inference, convolution, tuner analysis, pitch shifting, reverb, and full chain.
- Capture automation stress metrics where abrupt changes can cause clicks or instability.

## Host Validation And Release Gates

Before wider testing:

- Configure and build Release plugin artifacts.
- Build and run Release tests.
- Run the measurement harness.
- Validate AU with `auval` on macOS.
- Validate AU/VST3 with pluginval when available.
- Smoke in at least one real DAW.

DAW smoke should include:

- Mono and stereo inserts.
- 32, 64, and 128 sample buffers where the plugin claims low-latency use.
- Automation write/read.
- Host bypass and plugin bypass.
- Session save, close, reopen, and playback.
- Missing asset path restore.
- Sample-rate changes.
- Multiple instances of the heaviest expected preset.

For signed distribution, add platform signing, notarization, installer validation, clean-machine install, strict plugin validation, and checksums.
