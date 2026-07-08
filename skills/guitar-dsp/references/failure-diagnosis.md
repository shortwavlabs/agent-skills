# Guitar DSP Failure Diagnosis

## Contents

- How to diagnose
- Neural model and RTNeural failures
- Conventional DSP failures
- Host and product integration failures
- First reports to collect

## How To Diagnose

Work from audible symptom to a measurable check. Avoid changing several tone variables before proving which stage is responsible.

1. Reproduce with a minimal chain.
2. Render the same fixture through bypass and enabled paths.
3. Check finite output, peak/RMS level, DC, correlation, and latency shift.
4. Add blocks back one at a time.
5. Confirm the sample rate, channel count, and preset/model/IR state in the failing host session.

## Neural Model And RTNeural Failures

| Symptom | Likely causes | First checks |
| --- | --- | --- |
| Good ESR but bad tone | Fixture too narrow, loss underweights the audible band, level mismatch, polarity/alignment mistake, missing cabinet assumption | Listen to level-matched renders; run `compare_audio_metrics.py`; inspect correlation, lag, and polarity; compare with a wider DI fixture set |
| Model sounds dull or too bright | Wrong sample rate, missing pre/post EQ assumption, bad cabinet placement, output compensation error | Check metadata sample rate; bypass cabinet/EQ; inspect frequency response on pink noise or sweep |
| Model works in Python but not plugin | RTNeural export mismatch, unsupported layer/activation, wrong input shape, state reset issue | Run native parity; inspect `model_package_summary.py`; verify model reset and one instance per stateful channel |
| Model clicks after preset/model swap | Audio thread sees partially built state, old object destroyed in callback, no bypass/model crossfade | Audit model handoff; hold retired objects off-thread; add short crossfade or ramped mute during swap |
| Stereo model image shifts | Shared recurrent/causal state, independent dynamics when linked behavior is expected, accidental left-only fold | Verify one model instance per channel; inspect mono fold/fanout; render stereo correlation fixtures |
| Model loudness jumps between channels/presets | Per-model RMS compensation missing or overactive, capture output levels inconsistent | Print metadata RMS; clamp compensation; compare clean/dirty model RMS on the same fixture |
| High CPU or dropouts | Dynamic model too large, denormals, JSON parse/allocation in process, cabinet swap destruction, debug build | Benchmark Release build; search callback for allocation/logging/locks; measure RTF and stage timings |
| Host latency feels wrong | Confused export alignment, receptive field, and true processing delay | Render impulse; check `setLatencySamples`; report only actual delayed output |
| Validation passes but palm mutes fail | Training material lacks transient/low-note coverage, receptive field too short, data alignment too forgiving | Add low-tuned palm mute fixtures; compute receptive field; review residual around transients |
| Aliasing report fails | Nonlinear model learned out-of-band artifacts, export sample rate mismatch, insufficient anti-alias loss/checks | Review ASR; add high-frequency sine tests; train/export at intended sample rate |

## Conventional DSP Failures

| Symptom | Likely causes | First checks |
| --- | --- | --- |
| Bypass is not transparent | Bypass still processes filters/dynamics, smoothing state not neutral, dry path delayed | Add disabled identity test; compare samples; render impulse |
| Pops on bypass or automation | Unsmooth gain/filter changes, reset during nonzero signal, mode jump without crossfade | Smooth affected parameters; add bypass ramp; add automation stress tests |
| Zipper noise on tone/EQ | Coefficients rebuilt abruptly, parameter atomics read per sample without smoothing | Add target smoothing; update coefficients at bounded control rate; consider short crossfade for unstable changes |
| Drive sounds fizzy or brittle | Host-rate hard clipping, too much high-frequency input, no post filtering, DC bias | Render high-frequency alias tests; add local oversampling or improved transfer; add DC blocker and recovery low-pass |
| Drive gets quieter at high gain | Output compensation too aggressive, clipper rail too low, detector/envelope memory pulling level down | Plot RMS vs drive; inspect transfer curve; tune compensation separately from clipping shape |
| Gate chatters | No hysteresis/hold, detector too fast, threshold smoothing missing, detector filtered poorly | Render threshold sweep; add dB-domain hysteresis; tune attack/release/hold; test decaying palm mutes |
| Gate shifts stereo image | Unlinked stereo gain reduction or left-only detector | Use linked detector for pedal-style gates; test stereo image fixture |
| Compressor blend hollows out | Dry/wet polarity mismatch, unmatched wet latency, wet path all-pass phase shift | Render blend null checks; align wet/dry paths; keep dry path delay matched |
| Delay or modulation explodes | Feedback not bounded under automation, interpolation reads invalid delay, mode switch discontinuity | Clamp feedback before smoothing; bound delay reads; crossfade mode/routing changes |
| Reverb collapses to mono | Mono wet return without decorrelation, shared tank reads, width stage too late | Measure stereo correlation; decorrelate wet reads; preserve dry stereo path |
| Cabinet swap crashes or glitches | Convolution engine destroyed on callback, IR load/resample in process, latency update race | Publish immutable engine pointer; retire old engines off-thread; move file work outside callback |
| Filter sounds different by sample rate | Frequency clamps wrong, bilinear math using stale sample rate, coefficient update missed | Sweep at 44.1/48/96 kHz; recompute on prepare/sample-rate change; clamp below Nyquist |
| Silence produces CPU spikes | Denormals in filters/envelopes/reverbs | Use `juce::ScopedNoDenormals`; snap tiny state to zero; add silence benchmark |

## Host And Product Integration Failures

| Symptom | Likely causes | First checks |
| --- | --- | --- |
| Preset reload loses models or IRs | State stores only UI labels, path missing, no missing-file warning | Inspect ValueTree/XML; store path plus display name/status; reject missing files clearly |
| DAW reopen changes tone | Default parameter mismatch, prepare/reset order, model/IR async restore race | Save/reopen smoke in at least one DAW; compare rendered fixture before/after reopen |
| AU/VST3 validation fails | Bus layout mismatch, tail/latency reporting, parameter range issue, thread misuse | Run `auval`/pluginval; inspect bus layout support; check latency/tail updates |
| Meter/UI update causes clicks | Audio callback posts messages, allocates strings, or locks UI data | Publish atomics/ring snapshots; move formatting to message thread |
| CPU only fails in host | Debug build, UI repaint pressure, host buffer size, offline render path differs | Benchmark Standalone and plugin Release builds at small buffers; profile in host |

## First Reports To Collect

Ask for or produce these artifacts before guessing:

- Plugin format and host, sample rate, buffer size, channel layout.
- Enabled block list and preset/model/IR names.
- Short dry DI fixture and rendered output.
- `model_package_summary.py` output for model issues.
- `compare_audio_metrics.py` output for alignment/null issues.
- Unit test or pluginval/auval failure text.
- CPU benchmark matrix for performance complaints.
- A level-matched previous-build render when the issue is subjective tone regression.
