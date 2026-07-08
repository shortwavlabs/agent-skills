# Neural Guitar Modeling Math

## Contents

- Source and scope
- System-identification frame
- Causal finite-memory models
- Receptive field
- Alignment and polarity
- Residual metrics
- Checkpoint score and losses
- WaveNet-family architecture math
- Aliasing-to-signal ratio
- Native real-time factor
- Engineering implications

## Source And Scope

This reference distills the mathematical model and evaluation theory from:

```text
/Users/shortwavlabs/Workspace/shortwavlabs/rtneural-trainer/paper/arxiv/main.tex
```

The paper is an applied research report on aliasing-aware, RTNeural-compatible WaveNet modeling of guitar amplifier and pedal captures. Treat the formulas here as engineering tools for implementing and evaluating neural guitar DSP, not as proof that one architecture dominates all amp-modeling problems.

## System-Identification Frame

A fixed guitar amp, pedal, or signal-chain setting can be treated as a nonlinear system that maps a dry direct-input sequence `x[n]` to a processed target `y[n]`.

The task is not just to minimize a training loss. A useful model must also be:

- Causal and streamable.
- Finite-memory or otherwise bounded in state.
- Exportable to the intended runtime, such as RTNeural JSON.
- Parity-checked against the training backend.
- Fast enough in native C++ at small DAW buffers.
- Musically acceptable after listening, residual inspection, and aliasing review.

High-gain guitar tones make the problem harder because they are compressive, level-dependent, alignment-sensitive, and prone to audible upper-band residual and foldback.

## Causal Finite-Memory Models

For a causal model with receptive field `R`, prediction is:

```tex
\hat{y}[n] = f_\theta(x[n], x[n-1], ..., x[n-R+1])
```

Important consequences:

- The model can run sample-by-sample without lookahead.
- Receptive field is memory, not automatically plugin latency.
- A longer receptive field can model slower dynamics, but it increases runtime and can make optimization harder.
- Causality is a product constraint, not just a modeling preference, because the model must run in a DAW callback.

## Receptive Field

For a sequential stack of causal Conv1D layers with kernel size `k_l`, dilation `d_l`, and no striding:

```tex
R = 1 + \sum_l (k_l - 1)d_l
```

Common preset examples at 48 kHz:

| Preset family | Kernel/dilation shape | R samples | R ms |
| --- | --- | ---: | ---: |
| Fast | 6 layers, k=3, dilations 1..32 powers of two | 127 | 2.65 |
| Balanced | 8 layers, k=3, dilations 1..128 powers of two | 511 | 10.65 |
| Quality | 10 layers, k=3, dilations 1..512 powers of two | 2047 | 42.65 |
| High-gain tanh research | 11 layers, k=3, dilations 1..1024 powers of two | 4095 | 85.31 |
| Clean/edge long-field | 10 layers, k=7, dilations 1..512 powers of two | 6139 | 127.90 |
| A2-inspired PReLU | mixed k=6/15, dilations 1,3,7,17,41,101,239,1,3,7,17,41 | 2481 | 51.69 |

Use:

```tex
R_ms = 1000 R / sampleRate
```

Do not report `R` as host latency unless the runtime actually delays output. A causal Conv1D can have a large receptive field and still report zero added plugin latency.

## Alignment And Polarity

Latency alignment shifts the target relative to the dry input:

```tex
x_aligned[n] = x[n]
y_aligned[n] = y[n + L]
```

where `L` is the estimated target latency in samples after optional manual adjustment.

Engineering rules:

- A few samples of error can dominate high-frequency residual.
- High-gain distortion weakens simple dry/target correlation.
- Treat latency as a measurement variable, not hidden preprocessing.
- Report candidate offsets, confidence, and window agreement.
- Add manual latency sweeps for low-confidence high-gain captures.
- Detect polarity where possible; an inverted capture can look like a bad model.

Useful alignment features include transient onset evidence, envelope correlation, pre-emphasized detail, band-limited scoring, signed correlation, and post-training residual-shift checks.

## Residual Metrics

Residual:

```tex
e[n] = y[n] - \hat{y}[n]
```

Error-to-signal ratio:

```tex
ESR = \frac{\sum_n e[n]^2}{\max(\sum_n y[n]^2, \epsilon)}
```

Root mean square error:

```tex
RMSE = \sqrt{\frac{1}{N}\sum_n e[n]^2}
```

Mean absolute error:

```tex
MAE = \frac{1}{N}\sum_n |e[n]|
```

Prediction RMS ratio:

```tex
\rho_{rms} = \frac{RMS(\hat{y})}{\max(RMS(y), \epsilon)}
```

Use the RMS ratio to catch underpowered predictions that may have stable-looking validation curves but are musically wrong.

Correlation is useful for broad waveform tracking, but do not over-trust it on saturated tones. Two models can have similar correlation and different residual spectra, output level, aliasing, or pick attack.

Separate metric spans:

- Window validation: held-out training windows.
- Stream validation: longer continuous segment, better for state/continuity.
- Preview/export metrics: rendered WAVs from a checkpoint or exported model; best for user-facing comparisons.

## Checkpoint Score And Losses

The paper uses a composite validation score:

```tex
s = ESR_stream + 0.25 ESR_window + p_under
```

where `p_under` penalizes severely underpowered prediction level.

This score says: prefer models that work on continuous audio, keep short-window validation in the loop, and reject near-silent "stable" checkpoints.

Loss components used in the workflow include:

- Waveform ESR or MSE.
- Pre-emphasis MSE.
- Multi-resolution STFT loss.
- Light envelope/slope terms for dynamics-pedal presets.

Pre-emphasis is normally:

```tex
x_pre[n] = x[n] - a x[n-1]
```

with `a = 0.95` in the paper's implementation notes. It increases the importance of upper-band and transient errors.

The multi-resolution STFT setup in the paper uses frame sizes 256, 1024, and 2048 samples, with small weights for STFT magnitude and log-magnitude terms. Treat these as tuned implementation defaults, not universal constants.

## WaveNet-Family Architecture Math

The product-facing models are sequential causal TCNs:

```tex
x -> [causal Conv1D -> activation]^N -> output
```

They are not full residual/skip WaveNet graphs. The sequential constraint preserves RTNeural dynamic-JSON compatibility, but limits how much depth can be added before optimization becomes difficult.

Rough Conv1D multiply-add cost per sample for a full middle block:

```text
in_channels * out_channels * kernel_size
```

After the first layer expands to `C` channels, middle blocks are roughly:

```text
C * C * k
```

This makes width expensive:

| Width C | k=3 middle-block MACs/sample |
| ---: | ---: |
| 12 | 432 |
| 16 | 768 |
| 20 | 1200 |

Architectural lessons:

- Dilation expands context without recurrent sample-by-sample cost.
- Smaller Conv models are fast but can leave residual structure in guitar tones.
- Extra receptive field alone does not guarantee a better high-gain fit.
- Smoothed tanh activations can trade waveform fit and aliasing behavior.
- PReLU and mixed non-power-of-two dilation patterns can help hard high-gain captures, but they need benchmark headroom review.
- Dynamic RTNeural JSON overhead can make theoretically cheaper layer factorizations slower than expected.

## Aliasing-To-Signal Ratio

ASR is a deterministic probe diagnostic, not a perceptual model.

Procedure from the paper:

1. Render sine probes at requested frequencies such as 1250, 2500, and 5000 Hz.
2. Use input amplitude 0.5.
3. Warm up the model for 2048 samples.
4. Analyze a 4096-sample window.
5. Snap the probe frequency to the nearest FFT bin.
6. Subtract the mean before FFT.
7. Identify harmonic bins that should exist below Nyquist.
8. Treat non-harmonic positive-frequency energy as alias/residual energy.

Definitions:

```tex
E_harm = \sum_{b \in H} P[b]
E_alias = \sum_{b>0} P[b] - E_harm
ASR = \frac{E_alias}{\max(E_harm, \epsilon)}
```

Engineering thresholds from the paper:

- Worst ASR below 0.02: low aliasing in the current probes.
- Below 0.08: review warning.
- Above 0.08: stronger warning.

Do not treat those as audibility thresholds. Use ASR to focus listening tests, compare exports, and decide whether to try smoother activations, oversampling, higher-rate models, or revised captures.

## Native Real-Time Factor

Native real-time factor:

```tex
RTF = audio_duration_processed / wall_time_elapsed
```

Interpretation:

- `RTF > 1` means faster than real time in the benchmark.
- Product headroom needs a larger margin for DAWs, small buffers, UI work, IRs, and multiple instances.
- Benchmark block sizes 16, 32, 64, 128, 256, and 512 when possible.
- Benchmark mono and stereo when the plugin supports both.
- Compare RTNeural backends because Eigen, STL, and xsimd performance is model-shape-dependent.

Practical headroom bands:

- `>= 6x`: comfortable on the reference machine.
- `>= 3x`: likely usable but needs DAW testing.
- `>= 2x`: caution.
- `< 2x`: high risk.
- `< 1x`: not recommended for realtime.

## Engineering Implications

Use the math to make concrete decisions:

- If ESR is high and correlation is low, check architecture fit, capture quality, and alignment.
- If ESR is good but RMS ratio is low, penalize underpowered checkpoints or adjust training.
- If ESR is good but ASR is high, compare smoother activations, A2-inspired variants, oversampling, or higher-rate exports.
- If high-gain latency confidence is low, run candidate offset ablations before long training.
- If a clean capture diverges with a nonlinear high-gain preset, try clean/edge long-field presets before adding capacity.
- If runtime is tight, benchmark before switching architectures; model width, layer count, backend, and dynamic dispatch all matter.
- If a plugin reports latency, make sure it comes from real delayed output, not the Conv1D receptive field or export alignment metadata.
- If a model passes Python metrics but fails native parity, treat the export/runtime contract as broken.

The central lesson is multi-objective evaluation: backend parity, native validation, runtime headroom, preview metrics, ASR, residual listening, and DAW behavior together decide whether a neural guitar model is usable.
