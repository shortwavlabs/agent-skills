# C++ Patterns

## Table Of Contents

1. [Conventions](#conventions)
2. [Signal And Wave Basics](#signal-and-wave-basics)
3. [Spectrum And DFT](#spectrum-and-dft)
4. [Harmonic Waveforms](#harmonic-waveforms)
5. [Chirps And Spectrograms](#chirps-and-spectrograms)
6. [Noise](#noise)
7. [Correlation And Pitch](#correlation-and-pitch)
8. [DCT-IV](#dct-iv)
9. [Convolution And Filters](#convolution-and-filters)
10. [Differentiation And Integration](#differentiation-and-integration)
11. [Modulation And Sampling](#modulation-and-sampling)

## Conventions

The examples use ordinary C++17 and mirror Think DSP's Python/NumPy names where useful:

```cpp
#include <algorithm>
#include <cmath>
#include <complex>
#include <numeric>
#include <random>
#include <vector>

constexpr double pi = 3.14159265358979323846264338327950288;
constexpr double twoPi = 2.0 * pi;
using Complex = std::complex<double>;
```

Use the reusable educational header at `assets/thinkdsp.hpp` when you want these patterns as code instead of snippets.

## Signal And Wave Basics

Translate Think DSP's `Signal.make_wave` by producing sample times, evaluating, and storing a sample rate.

```cpp
struct Wave {
    std::vector<double> ys;
    double sampleRate = 44100.0;
    double start = 0.0;
};

std::vector<double> makeTimes(std::size_t n, double sampleRate, double start = 0.0) {
    std::vector<double> ts(n);
    for (std::size_t i = 0; i < n; ++i) {
        ts[i] = start + static_cast<double>(i) / sampleRate;
    }
    return ts;
}

Wave makeSine(double freq, double amp, double phase, double duration, double sampleRate) {
    const std::size_t n = static_cast<std::size_t>(std::llround(duration * sampleRate));
    Wave wave{{}, sampleRate, 0.0};
    wave.ys.resize(n);
    for (std::size_t i = 0; i < n; ++i) {
        const double t = static_cast<double>(i) / sampleRate;
        wave.ys[i] = amp * std::sin(twoPi * freq * t + phase);
    }
    return wave;
}
```

The C++ equivalent of adding two Think DSP signals is usually sample-wise addition after both are evaluated at the same sample rate and duration:

```cpp
Wave mixSameLength(const Wave& a, const Wave& b) {
    Wave out{{}, a.sampleRate, a.start};
    const std::size_t n = std::min(a.ys.size(), b.ys.size());
    out.ys.resize(n);
    for (std::size_t i = 0; i < n; ++i) {
        out.ys[i] = a.ys[i] + b.ys[i];
    }
    return out;
}
```

Normalize and unbias before comparing shapes, correlation, or noise statistics:

```cpp
void unbias(std::vector<double>& ys) {
    if (ys.empty()) return;
    const double mean = std::accumulate(ys.begin(), ys.end(), 0.0) / ys.size();
    for (double& y : ys) y -= mean;
}

void normalize(std::vector<double>& ys, double amp = 1.0) {
    double peak = 0.0;
    for (double y : ys) peak = std::max(peak, std::abs(y));
    if (peak == 0.0) return;
    for (double& y : ys) y *= amp / peak;
}
```

## Spectrum And DFT

Use direct DFT for educational examples and small tests. Replace it with an FFT library for production.

```cpp
std::vector<Complex> dft(const std::vector<Complex>& xs, bool inverse = false) {
    const std::size_t n = xs.size();
    std::vector<Complex> out(n);
    const double sign = inverse ? 1.0 : -1.0;
    for (std::size_t k = 0; k < n; ++k) {
        Complex sum = 0.0;
        for (std::size_t i = 0; i < n; ++i) {
            const double phase = sign * twoPi * static_cast<double>(k * i) / static_cast<double>(n);
            sum += xs[i] * std::exp(Complex(0.0, phase));
        }
        out[k] = inverse ? sum / static_cast<double>(n) : sum;
    }
    return out;
}

std::vector<Complex> rfft(const std::vector<double>& ys) {
    std::vector<Complex> xs(ys.begin(), ys.end());
    auto full = dft(xs);
    full.resize(ys.size() / 2 + 1);
    return full;
}

std::vector<double> realFrequencies(std::size_t n, double sampleRate) {
    std::vector<double> fs(n / 2 + 1);
    for (std::size_t k = 0; k < fs.size(); ++k) {
        fs[k] = static_cast<double>(k) * sampleRate / static_cast<double>(n);
    }
    return fs;
}
```

Low-pass, high-pass, and band-stop filters are bin edits:

```cpp
void lowPass(std::vector<Complex>& hs, const std::vector<double>& fs, double cutoff, double factor = 0.0) {
    for (std::size_t k = 0; k < hs.size(); ++k) {
        if (fs[k] > cutoff) hs[k] *= factor;
    }
}

void highPass(std::vector<Complex>& hs, const std::vector<double>& fs, double cutoff, double factor = 0.0) {
    for (std::size_t k = 0; k < hs.size(); ++k) {
        if (fs[k] < cutoff) hs[k] *= factor;
    }
}

void bandStop(std::vector<Complex>& hs, const std::vector<double>& fs,
              double lowCutoff, double highCutoff, double factor = 0.0) {
    for (std::size_t k = 0; k < hs.size(); ++k) {
        if (fs[k] >= lowCutoff && fs[k] <= highCutoff) hs[k] *= factor;
    }
}
```

For a real sinusoid centered exactly on bin `k`, use `2 * abs(hs[k]) / N` for amplitude. DC and Nyquist bins are not doubled.

## Harmonic Waveforms

Triangle, square, and sawtooth examples translate the book's `evaluate(ts)` methods into functions that compute each sample.

```cpp
double frac(double x) {
    return x - std::floor(x);
}

Wave makeTriangle(double freq, double amp, double duration, double sampleRate, double phase = 0.0) {
    const std::size_t n = static_cast<std::size_t>(std::llround(duration * sampleRate));
    Wave wave{{}, sampleRate, 0.0};
    wave.ys.resize(n);
    for (std::size_t i = 0; i < n; ++i) {
        const double t = static_cast<double>(i) / sampleRate;
        const double cycles = freq * t + phase / twoPi;
        wave.ys[i] = std::abs(frac(cycles) - 0.5);
    }
    unbias(wave.ys);
    normalize(wave.ys, amp);
    return wave;
}

Wave makeSquare(double freq, double amp, double duration, double sampleRate, double phase = 0.0) {
    const std::size_t n = static_cast<std::size_t>(std::llround(duration * sampleRate));
    Wave wave{{}, sampleRate, 0.0};
    wave.ys.resize(n);
    for (std::size_t i = 0; i < n; ++i) {
        const double t = static_cast<double>(i) / sampleRate;
        const double centered = frac(freq * t + phase / twoPi) - 0.5;
        wave.ys[i] = centered < 0.0 ? -amp : amp;
    }
    return wave;
}

Wave makeSawtooth(double freq, double amp, double duration, double sampleRate, double phase = 0.0) {
    const std::size_t n = static_cast<std::size_t>(std::llround(duration * sampleRate));
    Wave wave{{}, sampleRate, 0.0};
    wave.ys.resize(n);
    for (std::size_t i = 0; i < n; ++i) {
        const double t = static_cast<double>(i) / sampleRate;
        wave.ys[i] = 2.0 * frac(freq * t + phase / twoPi) - 1.0;
    }
    normalize(wave.ys, amp);
    return wave;
}
```

Before generating rich waveforms, compare every harmonic to Nyquist. If a harmonic exceeds `sampleRate / 2`, either oversample and filter, bandlimit the waveform, or expect aliases.

## Chirps And Spectrograms

For chirps, integrate instantaneous frequency into phase.

```cpp
Wave makeLinearChirp(double startHz, double endHz, double amp,
                     double duration, double sampleRate) {
    const std::size_t n = static_cast<std::size_t>(std::llround(duration * sampleRate));
    Wave wave{{}, sampleRate, 0.0};
    wave.ys.resize(n);
    double phase = 0.0;
    for (std::size_t i = 0; i < n; ++i) {
        const double u = n > 1 ? static_cast<double>(i) / static_cast<double>(n - 1) : 0.0;
        const double freq = startHz + (endHz - startHz) * u;
        phase += twoPi * freq / sampleRate;
        wave.ys[i] = amp * std::cos(phase);
    }
    return wave;
}

Wave makeExponentialChirp(double startHz, double endHz, double amp,
                          double duration, double sampleRate) {
    const std::size_t n = static_cast<std::size_t>(std::llround(duration * sampleRate));
    Wave wave{{}, sampleRate, 0.0};
    wave.ys.resize(n);
    double phase = 0.0;
    for (std::size_t i = 0; i < n; ++i) {
        const double u = n > 1 ? static_cast<double>(i) / static_cast<double>(n - 1) : 0.0;
        const double freq = startHz * std::pow(endHz / startHz, u);
        phase += twoPi * freq / sampleRate;
        wave.ys[i] = amp * std::cos(phase);
    }
    return wave;
}
```

A basic Hamming-windowed spectrogram loop:

```cpp
std::vector<double> hamming(std::size_t n) {
    std::vector<double> w(n);
    if (n <= 1) {
        if (n == 1) w[0] = 1.0;
        return w;
    }
    for (std::size_t i = 0; i < n; ++i) {
        w[i] = 0.54 - 0.46 * std::cos(twoPi * static_cast<double>(i) / static_cast<double>(n - 1));
    }
    return w;
}

std::vector<std::vector<Complex>> spectrogram(const Wave& wave, std::size_t segmentLength) {
    const auto win = hamming(segmentLength);
    const std::size_t hop = segmentLength / 2;
    std::vector<std::vector<Complex>> frames;
    for (std::size_t i = 0; i + segmentLength <= wave.ys.size(); i += hop) {
        std::vector<double> segment(segmentLength);
        for (std::size_t j = 0; j < segmentLength; ++j) {
            segment[j] = wave.ys[i + j] * win[j];
        }
        frames.push_back(rfft(segment));
    }
    return frames;
}
```

## Noise

White uniform and Gaussian noise differ in value distribution but both have flat average power spectra.

```cpp
Wave whiteUniformNoise(double amp, double duration, double sampleRate, std::mt19937& rng) {
    const std::size_t n = static_cast<std::size_t>(std::llround(duration * sampleRate));
    std::uniform_real_distribution<double> dist(-amp, amp);
    Wave wave{{}, sampleRate, 0.0};
    wave.ys.resize(n);
    for (double& y : wave.ys) y = dist(rng);
    return wave;
}

Wave brownianNoise(double amp, double duration, double sampleRate, std::mt19937& rng) {
    const std::size_t n = static_cast<std::size_t>(std::llround(duration * sampleRate));
    std::uniform_real_distribution<double> step(-1.0, 1.0);
    Wave wave{{}, sampleRate, 0.0};
    wave.ys.resize(n);
    double sum = 0.0;
    for (double& y : wave.ys) {
        sum += step(rng);
        y = sum;
    }
    unbias(wave.ys);
    normalize(wave.ys, amp);
    return wave;
}
```

Pink noise by spectral shaping:

```cpp
Wave pinkNoise(double amp, double beta, double duration, double sampleRate, std::mt19937& rng) {
    Wave wave = whiteUniformNoise(1.0, duration, sampleRate, rng);
    auto hs = rfft(wave.ys);
    auto fs = realFrequencies(wave.ys.size(), sampleRate);
    for (std::size_t k = 1; k < hs.size(); ++k) {
        hs[k] /= std::pow(fs[k], beta / 2.0);
    }
    hs[0] = 0.0;
    wave.ys = irfft(hs, wave.ys.size()); // See assets/thinkdsp.hpp.
    unbias(wave.ys);
    normalize(wave.ys, amp);
    return wave;
}
```

When implementing this outside the bundled header, mirror the one-sided spectrum to recover the conjugate-symmetric full spectrum before inverse transforming.

## Correlation And Pitch

Pearson correlation:

```cpp
double correlation(const std::vector<double>& a, const std::vector<double>& b) {
    const std::size_t n = std::min(a.size(), b.size());
    if (n == 0) return 0.0;
    const double meanA = std::accumulate(a.begin(), a.begin() + n, 0.0) / n;
    const double meanB = std::accumulate(b.begin(), b.begin() + n, 0.0) / n;
    double num = 0.0, denA = 0.0, denB = 0.0;
    for (std::size_t i = 0; i < n; ++i) {
        const double da = a[i] - meanA;
        const double db = b[i] - meanB;
        num += da * db;
        denA += da * da;
        denB += db * db;
    }
    const double den = std::sqrt(denA * denB);
    return den > 0.0 ? num / den : 0.0;
}
```

Pitch from autocorrelation:

```cpp
double estimateFundamental(const std::vector<double>& ys, double sampleRate,
                           double minHz = 50.0, double maxHz = 2000.0) {
    const std::size_t minLag = static_cast<std::size_t>(std::floor(sampleRate / maxHz));
    const std::size_t maxLag = std::min<std::size_t>(
        static_cast<std::size_t>(std::ceil(sampleRate / minHz)), ys.size() / 2);

    double bestCorr = -1.0;
    std::size_t bestLag = minLag;
    for (std::size_t lag = minLag; lag <= maxLag; ++lag) {
        std::vector<double> a(ys.begin(), ys.end() - lag);
        std::vector<double> b(ys.begin() + lag, ys.end());
        const double corr = correlation(a, b);
        if (corr > bestCorr) {
            bestCorr = corr;
            bestLag = lag;
        }
    }
    return bestLag > 0 ? sampleRate / static_cast<double>(bestLag) : 0.0;
}
```

Use a short segment where pitch is nearly constant. For voiced sound, search only plausible lag ranges.

## DCT-IV

DCT-IV is its own inverse up to scale, which makes it good for understanding analysis and synthesis.

```cpp
std::vector<double> dctIV(const std::vector<double>& ys) {
    const std::size_t n = ys.size();
    std::vector<double> out(n, 0.0);
    for (std::size_t k = 0; k < n; ++k) {
        double sum = 0.0;
        for (std::size_t i = 0; i < n; ++i) {
            const double angle = pi / static_cast<double>(n) *
                (static_cast<double>(i) + 0.5) * (static_cast<double>(k) + 0.5);
            sum += ys[i] * std::cos(angle);
        }
        out[k] = sum;
    }
    return out;
}

std::vector<double> inverseDctIV(const std::vector<double>& amps) {
    auto ys = dctIV(amps);
    const double scale = 2.0 / static_cast<double>(amps.size());
    for (double& y : ys) y *= scale;
    return ys;
}
```

## Convolution And Filters

Direct linear convolution:

```cpp
std::vector<double> convolveLinear(const std::vector<double>& x, const std::vector<double>& h) {
    if (x.empty() || h.empty()) return {};
    std::vector<double> y(x.size() + h.size() - 1, 0.0);
    for (std::size_t i = 0; i < x.size(); ++i) {
        for (std::size_t j = 0; j < h.size(); ++j) {
            y[i + j] += x[i] * h[j];
        }
    }
    return y;
}
```

Moving average smoothing:

```cpp
std::vector<double> boxcar(std::size_t n) {
    return std::vector<double>(n, 1.0 / static_cast<double>(n));
}

auto smoothed = convolveLinear(wave.ys, boxcar(11));
```

FFT convolution pattern:

1. Pad both signals to at least `x.size() + h.size() - 1`.
2. Compute FFT of both padded arrays.
3. Multiply complex bins element-wise.
4. Inverse FFT.
5. Keep the first `x.size() + h.size() - 1` samples.

Do this instead of direct convolution for long signals or impulse responses.

## Differentiation And Integration

Finite difference:

```cpp
std::vector<double> diff(const std::vector<double>& ys) {
    if (ys.size() < 2) return {};
    std::vector<double> out(ys.size() - 1);
    for (std::size_t i = 1; i < ys.size(); ++i) {
        out[i - 1] = ys[i] - ys[i - 1];
    }
    return out;
}
```

Frequency-domain differentiation and integration:

```cpp
void differentiateSpectrum(std::vector<Complex>& hs, const std::vector<double>& fs) {
    for (std::size_t k = 0; k < hs.size(); ++k) {
        hs[k] *= Complex(0.0, twoPi * fs[k]);
    }
}

void integrateSpectrum(std::vector<Complex>& hs, const std::vector<double>& fs) {
    hs[0] = 0.0; // DC constant is unknown after differentiation.
    for (std::size_t k = 1; k < hs.size(); ++k) {
        hs[k] /= Complex(0.0, twoPi * fs[k]);
    }
}
```

Use the spectral method primarily for periodic or well-windowed signals. Non-periodic boundaries create artifacts.

## Modulation And Sampling

Amplitude modulation:

```cpp
Wave amplitudeModulate(const Wave& input, double carrierHz) {
    Wave out{{}, input.sampleRate, input.start};
    out.ys.resize(input.ys.size());
    for (std::size_t i = 0; i < input.ys.size(); ++i) {
        const double t = input.start + static_cast<double>(i) / input.sampleRate;
        out.ys[i] = input.ys[i] * std::cos(twoPi * carrierHz * t);
    }
    return out;
}
```

Sampling by impulse train:

```cpp
Wave keepEveryNthSample(const Wave& input, std::size_t factor) {
    Wave out{{}, input.sampleRate, input.start};
    out.ys.assign(input.ys.size(), 0.0);
    for (std::size_t i = 0; i < input.ys.size(); i += factor) {
        out.ys[i] = input.ys[i];
    }
    return out;
}
```

For actual downsampling, low-pass before decimation and then write a new sample rate:

```cpp
Wave decimateAfterAntiAlias(const Wave& filtered, std::size_t factor) {
    Wave out{{}, filtered.sampleRate / static_cast<double>(factor), filtered.start};
    for (std::size_t i = 0; i < filtered.ys.size(); i += factor) {
        out.ys.push_back(filtered.ys[i]);
    }
    return out;
}
```

The anti-alias cutoff should be no higher than the new Nyquist frequency.
