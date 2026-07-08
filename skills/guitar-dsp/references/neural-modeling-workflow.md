# Neural Guitar Modeling Workflow

## Contents

- Capture pair contract
- Levels and gain consistency
- Latency and alignment
- Capture length and source material
- Preset selection
- CLI workflow
- Export package contract
- Interpreting warnings

## Capture Pair Contract

A neural guitar model starts with a matched dry/processed pair:

1. Dry input WAV.
2. Processed target WAV made from the same performance through the amp, pedal, plugin, or signal chain being modeled.

The files should:

- Have the same sample rate.
- Have the same channel layout, ideally mono.
- Start from the same performance with no trim differences.
- Preserve real device latency until the prepare/alignment step estimates or adjusts it.
- Be long enough to contain the behavior the model should learn.

For v1 guitar amp/pedal work, 48 kHz mono WAV is the safest default. 32-bit float prepared audio is appropriate for DAW-exported captures because it avoids avoidable quantization in the prep pipeline.

Avoid modeling delay, reverb, modulation, gates, limiters, cabinet changes, knob moves, pickup switches, or output-gain moves unless the experiment is specifically about those behaviors.

## Levels And Gain Consistency

Aim for repeatable headroom:

- Dry input peak: roughly -12 to -6 dBFS.
- Processed target peak: roughly -12 to -3 dBFS.
- Avoid peaks above -1 dBFS.
- Avoid clipped samples.
- Keep active playing well above the noise floor.

For a profile family:

- Set interface gain once.
- Set the device/plugin output once.
- Record all targets without changing capture gain unless the change is intentional.
- Use the same DI file for every target in the family when comparing profiles.
- Document intentional output-level changes.

Do not normalize every target independently by default. Independent normalization hides the rig's real output level and can make exported models feel wrong when switched in a plugin.

## Latency And Alignment

Alignment quality often decides whether a training run succeeds.

A robust prepare step should estimate latency using active windows, transient evidence, pre-emphasized detail, onset shape, and signed correlation. It should report:

- Estimated samples.
- Confidence.
- Window agreement.
- Candidate offsets.
- Polarity and polarity confidence when available.
- Manual adjustment and effective latency.

Practical rules:

- Trust high-confidence estimates around 0.85 and above for long runs.
- Treat around 0.75 as usable but worth review.
- Treat around 0.60 or below as a prompt to sweep candidate offsets before long runs.
- Do not assume all captures in a family share latency.
- Heavy saturation and dense lead/rhythm tones can reduce confidence even with a good transient preamble.
- If tone is close but residual peaks remain high, check alignment before changing architecture.

## Capture Length And Source Material

Recommended lengths:

- 5-15 seconds for pipeline smoke tests.
- 30-60 seconds for a useful first training pass.
- 90-180 seconds for stronger real-world profiles.

For longer captures, sample training windows across the file:

- Around 1024 windows can work for 45-120 second captures.
- Around 2048 windows is a good first pass for 90-180 seconds.
- 4096-8192 windows is more appropriate for final hard rhythm/lead runs.

Use material that excites the behavior:

- 2-3 seconds of clear transient preamble.
- Soft and hard picking.
- Single notes across the register.
- Chords and double-stops.
- Palm mutes for rhythm.
- Sustained notes for compression and decay.
- Transitions between muted, open, single-note, and chordal playing.

Avoid long mid-capture silence unless modeling noise behavior.

## Preset Selection

Favor RTNeural-safe WaveNet-style Conv1D presets for product guitar captures. Dense, GRU, LSTM, and small Conv1D models can remain useful for layer/export fixtures, but they are usually not the product quality lane.

Practical preset routing:

- `wavenet_tcn_fast`: quick compatibility and alignment sanity check.
- `wavenet_tcn_balanced`: default first serious run for many amp/pedal captures.
- `wavenet_tcn_clean`: clean or low-gain captures where phase/EQ/mostly linear transfer matters.
- `wavenet_tcn_edge`: edge-of-breakup captures that are too nonlinear for clean but not dense high-gain.
- `wavenet_tcn_quality`: crunch, rhythm, high-gain, and hard captures where balanced leaves audible residual.
- `wavenet_tcn_compressor`: compressor/dynamics-pedal captures when quality gets close but misses attack/release behavior.
- `wavenet_tcn_quality_tanh15` or `wavenet_tcn_quality_tanh18`: research paths for high-band residual or aliasing concerns.
- `wavenet_tcn_a2_prelu`: strong high-gain candidate with mixed kernels and PReLU when quality/tanh still leaves upper-band residual.
- `wavenet_tcn_high_gain`: keep as research-only unless new evidence proves it; extra sequential tanh depth can create optimization walls.

Do not assume lower theoretical MAC count means faster dynamic RTNeural runtime. Extra layers and dynamic dispatch can outweigh smaller kernels/widths.

## CLI Workflow

A reusable local flow is:

```bash
rttrainer prepare --manifest prepare.json
rttrainer train --manifest train.json
rttrainer evaluate --manifest evaluate.json
rttrainer export --manifest export.json
```

Prepare manifests should include input path, target path, output directory, channel policy, optional resampling, and optional known/manual latency.

Train manifests should include run id, run directory, prepared directory, WaveNet preset, backend, epochs, batch size, learning rate, sequence length, max windows, window resampling policy, and seed.

Export manifests should include name, run directory, export directory, sample rate, latency samples, and parity tolerance.

For long captures, keep validation/preview excerpts fixed while rotating training windows. Use streaming validation as the checkpoint anchor, with short-window diagnostics and output-level penalty to avoid selecting near-silent early checkpoints.

## Export Package Contract

Prefer loading an export package folder instead of a raw JSON file. A production-quality package should include:

```text
model.rtneural.json
package.json
validation-report.json
benchmark-report.json
native-benchmark-matrix.json
aliasing-report.json
export-manifest.json
export-events.jsonl
parity-snapshot.json
parity-snapshot-input.wav
parity-snapshot-expected.wav
stderr.log
```

Minimum for playback:

- `model.rtneural.json`

Minimum for safety display:

- `package.json`
- `validation-report.json`
- `benchmark-report.json`
- `aliasing-report.json`
- `native-benchmark-matrix.json`

Important metadata fields:

- `sample_rate`
- `preset`
- `quality.esr`
- `validation.status`
- `validation.max_abs_error`
- `benchmark.summary.realtime_factor_worst`
- `benchmark.model_info.architecture`
- `benchmark.model_info.latency_samples`
- `benchmark.model_info.receptive_field_samples`
- `benchmark.model_info.conv1d_layers`
- `aliasing.status`
- `aliasing.worst_asr`
- `aliasing.average_asr`

Use the parity snapshot for plugin regression tests: render `parity-snapshot-input.wav` through the plugin with neural-only unity-gain settings and compare to `parity-snapshot-expected.wav` after reset.

## Interpreting Warnings

`capture_headroom_low`: recapture with more headroom when possible.

`capture_level_low`: recapture hotter if the signal is close to the noise floor.

`rms_mismatch`: review whether output-level difference is intentional.

`latency_estimate_review`: try candidate offsets before long runs.

`long_capture`: increase window budget so training sees enough of the file.

`aliasing.status != pass`: warn and listen; do not block loading solely because of ASR unless the product policy says so.

Low native realtime factor:

- `>= 6x`: comfortable.
- `>= 3x`: likely usable but test in DAW with UI and IR.
- `>= 2x`: caution.
- `< 2x`: high risk.
- `< 1x`: not recommended for realtime use.
