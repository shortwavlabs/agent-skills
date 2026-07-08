# Validation And Release For Guitar DSP

## Contents

- Local gates
- DSP unit tests
- Neural export validation
- Measurement harnesses
- Plugin host validation
- DAW smoke matrix
- Release checklist

## Local Gates

Use separate build presets or build directories for:

- Release plugin artifacts.
- Release tests without copying/installing plugin bundles.
- Debug tests for local iteration.
- Release measurement harnesses.

Keep plugin auto-copy/install enabled only for builds intended for DAW auditioning. Disable it for tests and measurements so CI/local validation does not disturb installed plugins.

Generic CMake preset shape:

```text
release-plugin:      Release, tests off, copy plugin on
release-tests:       Release, tests on, copy plugin off
debug-tests:         Debug, tests on, copy plugin off
release-measurement: Release, measurement target on, copy plugin off
```

## DSP Unit Tests

For every block, cover:

- Bypass identity or documented dry ramp.
- Finite output at parameter extremes.
- Reset determinism.
- Sample-rate stability.
- Automation safety.
- Mono/stereo routing.
- Channel linking where expected.
- Tail/latency reporting where relevant.
- Missing-file rejection for file-backed stages.

For nonlinear guitar stages, add:

- Harmonic growth with drive/sustain.
- DC rejection after asymmetric clipping.
- Alias residue checks or high-rate comparisons.
- Coherent sine alias-probe reports for high-gain settings when aliasing is a release risk.
- Oversampling on/off or factor comparisons when an oversampled path is introduced.
- Output calibration across gain controls.
- Transfer-curve reports for waveshapers and diode/tube stages.
- Solver convergence checks for diode feedback stages.
- Reduced-input cleanup checks for fuzz stages.

For tone stacks, add:

- Response curves at min/default/max and representative combinations.
- Insertion-loss checks.
- Automation/crossfade checks for switches and coefficient changes.
- Passive network source/load assumptions when modeled.

For cabinet stages, add:

- No-IR path remains finite.
- IR loading applies expected level policy.
- Non-matching IR sample rates are resampled or rejected deliberately.
- Blend endpoints select the intended slot.
- Repeated load/swap/clear while processing stays finite.
- Dynamic cabinet layers disabled reproduce the static IR/filter path.
- Speaker compression/resonance reports at low, medium, and high drive.

For processor-level tests, include:

- Parameter existence and ranges.
- Mono and stereo bus support.
- Right-only stereo input with mono amp enabled to prove fold-down behavior.
- State save/restore for parameters and selected files.
- Toggling bypass while processing.
- Tail and latency updates when stages change.

## Neural Export Validation

Each exported RTNeural package should pass:

1. Python/Keras parity against the checkpoint.
2. Native RTNeural parity against WAV fixtures.
3. Native benchmark at target sample rate, block sizes, and channel counts.
4. Aliasing report for deterministic sine probes.
5. Package metadata consistency check.

Native validator commands usually need:

```text
validate --model model.rtneural.json --input test-input.wav --reference test-target.wav --report validation-report.json
benchmark --model model.rtneural.json --sample-rate 48000 --seconds 2 --block-sizes 16,32,64,128,256,512 --channels 1,2 --passes 3 --warmup-blocks 8 --report benchmark-report.json
```

Benchmark multiple RTNeural backends when available. Treat the fastest passing backend as useful runtime guidance, not a universal promise across machines.

## Measurement Harnesses

Build offline measurement tools for Repeatable Release data:

- Per-stage timing at 44.1, 48, 88.2, and 96 kHz.
- Block sizes 16, 32, 64, 128, 256, and 512 where relevant.
- Full chain timing for common presets.
- Stereo correlation for stereo post-FX.
- Alias/DC checks for nonlinear blocks.
- Harmonic/non-harmonic energy reports for nonlinear blocks.
- Automation max-adjacent-delta checks for abrupt control changes.
- IR swap stress timing.

Run measurement harnesses in Release. Debug timing is useful for correctness but not for product headroom.

## Plugin Host Validation

For JUCE plugins:

- Run `auval` for AU targets on macOS.
- Run pluginval for AU/VST3 when available, preferably strictness level 5 before wider release.
- Verify signed bundles with platform signing tools before distribution.
- Validate both mono and stereo buses.
- Validate plugins with MIDI input as the correct AU type when applicable.

Make wrapper validation scripts fail early when expected bundles are missing. Allow an environment override for a preinstalled pluginval path, but make local download/cache an option for developer machines.

## DAW Smoke Matrix

Manual DAW smoke should cover:

- Logic Pro AU scan and insert.
- REAPER VST3 scan and insert.
- Another VST3 host when possible.
- Mono and stereo tracks.
- Small buffer sizes: 32, 64, 128 samples.
- 48 kHz primary sessions and at least one mismatch session such as 96 kHz.
- Automation write/read.
- Host bypass and plugin bypass.
- Session save, close, reopen, playback.
- Missing model/IR file restore warnings.
- Multiple instances of the heaviest expected model.
- Offline render when the host supports it.

For neural loaders, smoke:

- Amp only.
- Pedal only.
- Pedal plus amp.
- Amp plus cabinet IR.
- Full chain with output trim.
- Raw JSON load and package folder load.
- Package metadata warning display.

## Release Checklist

Before sharing wider test builds:

- Configure and build Release plugin artifacts.
- Build and run Release DSP tests.
- Run Release measurement harness.
- Validate AU/VST3 wrappers.
- Audition standalone or DAW plugin with fresh artifacts.
- Confirm DAW state restore.
- Confirm model and IR missing-file behavior.
- Confirm no known file I/O/model parsing/IR loading path can run in `processBlock()`.
- Check package/signing/notarization where relevant.
- Run a clean-machine install when distributing installers.
- Generate checksums for public artifacts.
