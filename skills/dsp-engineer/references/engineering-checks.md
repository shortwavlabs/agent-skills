# Engineering Checks

## Table Of Contents

1. [Before Coding](#before-coding)
2. [Porting NumPy To C++](#porting-numpy-to-c)
3. [Scaling And Bins](#scaling-and-bins)
4. [Aliasing Checks](#aliasing-checks)
5. [Window And Spectrogram Checks](#window-and-spectrogram-checks)
6. [Convolution Checks](#convolution-checks)
7. [Noise Checks](#noise-checks)
8. [Test Cases](#test-cases)
9. [Production Notes](#production-notes)

## Before Coding

- Identify whether the input is conceptual, offline analysis, real-time audio, embedded DSP, or a plugin/framework integration.
- Write down `sampleRate`, `duration`, `n`, `dt = 1/sampleRate`, `df = sampleRate/n`, and `nyquist = sampleRate/2`.
- Decide whether the signal is assumed periodic. DFT, spectral derivatives, and circular convolution depend on this.
- Decide whether amplitude needs physical units, normalized full-scale units, or arbitrary analysis units.
- Decide whether phase matters. If it does, keep complex spectra intact and avoid magnitude-only processing.

## Porting NumPy To C++

| NumPy/Think DSP | C++ pattern |
| --- | --- |
| `np.arange(n) / sampleRate` | loop filling `i / sampleRate` |
| `np.linspace(a, b, n)` | `a + (b - a) * i / (n - 1)` |
| `np.logspace(log10(a), log10(b), n)` | `a * pow(b / a, i / (n - 1))` |
| `np.diff(xs)` | loop over `xs[i] - xs[i-1]` |
| `np.cumsum(xs)` | running sum |
| `np.outer(ts, fs)` | nested loop over time and frequency |
| `np.dot(M, v)` | nested loop matrix-vector multiply |
| `np.exp(1j * phase)` | `std::exp(std::complex<double>(0, phase))` |
| `np.fft.rfft` | real FFT library, or full DFT then keep `N/2 + 1` bins |
| `np.fft.irfft` | rebuild conjugate-symmetric full spectrum, inverse FFT, take real part |
| `np.convolve` | direct nested loop for small cases, FFT convolution for long signals |
| `np.roll` | index modulo `n`, or rotate/copy if needed |

## Scaling And Bins

- Full DFT bin `k` has frequency `k * sampleRate / N`.
- Real FFT bins run from `0` through `N/2` for even `N`.
- With DFT convention `X = sum x * exp(-i...)`, inverse divides by `N`.
- Magnitude spectrum is `abs(X[k])`. Power is `norm(X[k])`.
- For real one-sided amplitude:
  - DC amplitude is `abs(X[0]) / N`.
  - Nyquist amplitude, for even `N`, is `abs(X[N/2]) / N`.
  - Other bin amplitudes are `2 * abs(X[k]) / N`.
- A mismatch by a factor of `N`, `2`, or `sqrt(N)` usually means two libraries use different normalization conventions.

## Aliasing Checks

Use this fold calculation for a frequency in Hz:

```cpp
double foldedAlias(double frequency, double sampleRate) {
    const double period = sampleRate;
    double f = std::fmod(std::abs(frequency), period);
    if (f > sampleRate / 2.0) f = sampleRate - f;
    return f;
}
```

Check these cases:

- `5500 Hz` sampled at `10000 Hz` folds to `4500 Hz`.
- `7700 Hz` sampled at `10000 Hz` folds to `2300 Hz`.
- `9900 Hz` sampled at `10000 Hz` folds to `100 Hz`.
- Harmonic waveforms with discontinuities can create many aliased harmonics unless bandlimited.
- Downsampling requires a low-pass filter before decimation, not after.

## Window And Spectrogram Checks

- If a pure tone is not on an exact DFT bin, leakage is expected.
- Hamming reduces sidelobes but widens the main lobe. Do not expect perfect frequency isolation.
- A longer segment improves frequency resolution but blurs time changes.
- A shorter segment improves time resolution but makes pitch bins coarser.
- Half-overlap is a reasonable default for exploratory spectrograms.
- Use consistent window energy correction if amplitudes must be numerically accurate.

## Convolution Checks

- Direct linear convolution length is `x.size() + h.size() - 1`.
- FFT convolution without enough padding is circular convolution and wraps the tail into the beginning.
- To compute linear convolution by FFT, pad to at least the linear length. Many FFT libraries prefer the next power of two or a smooth composite size.
- For an LTI system, input convolved with impulse response should match input spectrum multiplied by transfer function, after correct padding and scaling.
- For impulse response work, normalize intentionally. Blind normalization can destroy the measured gain of the system.

## Noise Checks

- White noise: average power is flat over frequency. Individual spectra are random; average across segments for stable estimates.
- Brownian/red noise: generate as cumulative sum of white noise; log-log power slope should be close to -2.
- Pink noise: after shaping by `1/f^(beta/2)` in amplitude, log-log power slope should be close to `-beta`.
- Serial correlation:
  - White noise should be near 0 at lag 1.
  - Brownian noise should be close to 1 at lag 1.
  - Pink noise should sit between them depending on `beta`.

## Test Cases

Use these as quick correctness checks:

| Test | Expected result |
| --- | --- |
| 440 Hz sine, 44100 Hz sample rate, 1 second | Spectrum peak at 440 Hz. |
| DFT then IDFT | Max absolute reconstruction error near floating-point tolerance. |
| DCT-IV then inverse DCT-IV | Reconstructs input within tolerance. |
| Triangle wave at 200 Hz | Odd harmonics, amplitude slope near `1/f^2`. |
| Square wave at 100 Hz | Odd harmonics, amplitude slope near `1/f`. |
| 5500 Hz cosine sampled at 10000 Hz | Matches 4500 Hz samples. |
| Linear chirp 220 to 440 Hz | Spectrogram ridge rises approximately linearly. |
| Gaussian-window smoothing | Low-pass response with fewer sidelobes than boxcar. |
| Direct convolution versus padded FFT convolution | Same linear result after trimming. |
| Autocorrelation pitch | `sampleRate / bestLag` near known tone frequency. |

## Production Notes

- Replace direct DFT/DCT experiments with optimized libraries once behavior is clear.
- Preallocate buffers in real-time code. Avoid `std::vector::push_back`, heap allocation, locks, I/O, and logging in audio callbacks.
- Smooth parameter changes, especially filter coefficients, gains, oscillator frequency, and delay time.
- Use denormal protection for recursive filters, reverb tails, and feedback paths.
- Prefer overlap-add or overlap-save for long FFT convolution in streaming audio.
- Use framework-native FFTs when working inside JUCE, VCV Rack, Apple platforms, or embedded SDKs.
- Write numerical tests against small deterministic signals before testing with long recordings.
