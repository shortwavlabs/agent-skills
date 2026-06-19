#pragma once

#include <algorithm>
#include <cmath>
#include <complex>
#include <cstddef>
#include <numeric>
#include <random>
#include <stdexcept>
#include <vector>

namespace thinkdsp_cpp {

constexpr double pi = 3.14159265358979323846264338327950288;
constexpr double twoPi = 2.0 * pi;
using Complex = std::complex<double>;

struct Wave {
    std::vector<double> ys;
    double sampleRate = 44100.0;
    double start = 0.0;

    std::size_t size() const { return ys.size(); }
    double duration() const { return sampleRate > 0.0 ? static_cast<double>(ys.size()) / sampleRate : 0.0; }
    double end() const { return start + duration(); }
};

inline std::vector<double> makeTimes(std::size_t n, double sampleRate, double start = 0.0) {
    std::vector<double> ts(n);
    for (std::size_t i = 0; i < n; ++i) {
        ts[i] = start + static_cast<double>(i) / sampleRate;
    }
    return ts;
}

inline double frac(double x) {
    return x - std::floor(x);
}

inline void unbias(std::vector<double>& ys) {
    if (ys.empty()) return;
    const double mean = std::accumulate(ys.begin(), ys.end(), 0.0) / static_cast<double>(ys.size());
    for (double& y : ys) y -= mean;
}

inline void normalize(std::vector<double>& ys, double amp = 1.0) {
    double peak = 0.0;
    for (double y : ys) peak = std::max(peak, std::abs(y));
    if (peak == 0.0) return;
    const double scale = amp / peak;
    for (double& y : ys) y *= scale;
}

inline Wave segment(const Wave& wave, double startSeconds, double durationSeconds) {
    const double rel = std::max(0.0, startSeconds - wave.start);
    const std::size_t first = std::min<std::size_t>(
        wave.ys.size(), static_cast<std::size_t>(std::llround(rel * wave.sampleRate)));
    const std::size_t count = static_cast<std::size_t>(std::llround(durationSeconds * wave.sampleRate));
    const std::size_t last = std::min(wave.ys.size(), first + count);
    return Wave{std::vector<double>(wave.ys.begin() + first, wave.ys.begin() + last), wave.sampleRate, startSeconds};
}

inline Wave sineWave(double freq, double amp, double phase, double duration, double sampleRate) {
    const std::size_t n = static_cast<std::size_t>(std::llround(duration * sampleRate));
    Wave wave{{}, sampleRate, 0.0};
    wave.ys.resize(n);
    for (std::size_t i = 0; i < n; ++i) {
        const double t = static_cast<double>(i) / sampleRate;
        wave.ys[i] = amp * std::sin(twoPi * freq * t + phase);
    }
    return wave;
}

inline Wave cosineWave(double freq, double amp, double phase, double duration, double sampleRate) {
    const std::size_t n = static_cast<std::size_t>(std::llround(duration * sampleRate));
    Wave wave{{}, sampleRate, 0.0};
    wave.ys.resize(n);
    for (std::size_t i = 0; i < n; ++i) {
        const double t = static_cast<double>(i) / sampleRate;
        wave.ys[i] = amp * std::cos(twoPi * freq * t + phase);
    }
    return wave;
}

inline Wave triangleWave(double freq, double amp, double duration, double sampleRate, double phase = 0.0) {
    const std::size_t n = static_cast<std::size_t>(std::llround(duration * sampleRate));
    Wave wave{{}, sampleRate, 0.0};
    wave.ys.resize(n);
    for (std::size_t i = 0; i < n; ++i) {
        const double t = static_cast<double>(i) / sampleRate;
        wave.ys[i] = std::abs(frac(freq * t + phase / twoPi) - 0.5);
    }
    unbias(wave.ys);
    normalize(wave.ys, amp);
    return wave;
}

inline Wave squareWave(double freq, double amp, double duration, double sampleRate, double phase = 0.0) {
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

inline Wave sawtoothWave(double freq, double amp, double duration, double sampleRate, double phase = 0.0) {
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

inline Wave chirp(double startHz, double endHz, double amp, double duration, double sampleRate, bool exponential = false) {
    const std::size_t n = static_cast<std::size_t>(std::llround(duration * sampleRate));
    Wave wave{{}, sampleRate, 0.0};
    wave.ys.resize(n);
    double phase = 0.0;
    for (std::size_t i = 0; i < n; ++i) {
        const double u = n > 1 ? static_cast<double>(i) / static_cast<double>(n - 1) : 0.0;
        const double freq = exponential
            ? startHz * std::pow(endHz / startHz, u)
            : startHz + (endHz - startHz) * u;
        phase += twoPi * freq / sampleRate;
        wave.ys[i] = amp * std::cos(phase);
    }
    return wave;
}

inline std::vector<double> hamming(std::size_t n) {
    std::vector<double> w(n);
    if (n == 0) return w;
    if (n == 1) {
        w[0] = 1.0;
        return w;
    }
    for (std::size_t i = 0; i < n; ++i) {
        w[i] = 0.54 - 0.46 * std::cos(twoPi * static_cast<double>(i) / static_cast<double>(n - 1));
    }
    return w;
}

inline std::vector<Complex> dft(const std::vector<Complex>& xs, bool inverse = false) {
    const std::size_t n = xs.size();
    std::vector<Complex> out(n);
    if (n == 0) return out;
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

inline std::vector<Complex> idft(const std::vector<Complex>& hs) {
    return dft(hs, true);
}

inline std::vector<Complex> rfft(const std::vector<double>& ys) {
    std::vector<Complex> xs(ys.begin(), ys.end());
    auto full = dft(xs, false);
    full.resize(ys.size() / 2 + 1);
    return full;
}

inline std::vector<double> irfft(const std::vector<Complex>& half, std::size_t n) {
    if (half.empty() && n == 0) return {};
    if (half.size() != n / 2 + 1) {
        throw std::invalid_argument("irfft half-spectrum size does not match n");
    }
    std::vector<Complex> full(n, 0.0);
    for (std::size_t k = 0; k < half.size(); ++k) full[k] = half[k];
    const std::size_t mirrorLimit = half.size() - (n % 2 == 0 ? 1 : 0);
    for (std::size_t k = 1; k < mirrorLimit; ++k) {
        full[n - k] = std::conj(half[k]);
    }
    auto xs = idft(full);
    std::vector<double> ys(n);
    for (std::size_t i = 0; i < n; ++i) ys[i] = xs[i].real();
    return ys;
}

inline std::vector<double> realFrequencies(std::size_t n, double sampleRate) {
    std::vector<double> fs(n / 2 + 1);
    for (std::size_t k = 0; k < fs.size(); ++k) {
        fs[k] = static_cast<double>(k) * sampleRate / static_cast<double>(n);
    }
    return fs;
}

inline std::vector<double> magnitudes(const std::vector<Complex>& hs) {
    std::vector<double> out(hs.size());
    for (std::size_t k = 0; k < hs.size(); ++k) out[k] = std::abs(hs[k]);
    return out;
}

inline std::vector<double> powers(const std::vector<Complex>& hs) {
    std::vector<double> out(hs.size());
    for (std::size_t k = 0; k < hs.size(); ++k) out[k] = std::norm(hs[k]);
    return out;
}

inline void lowPass(std::vector<Complex>& hs, const std::vector<double>& fs, double cutoff, double factor = 0.0) {
    for (std::size_t k = 0; k < hs.size(); ++k) {
        if (fs[k] > cutoff) hs[k] *= factor;
    }
}

inline void highPass(std::vector<Complex>& hs, const std::vector<double>& fs, double cutoff, double factor = 0.0) {
    for (std::size_t k = 0; k < hs.size(); ++k) {
        if (fs[k] < cutoff) hs[k] *= factor;
    }
}

inline void bandStop(std::vector<Complex>& hs, const std::vector<double>& fs,
                     double lowCutoff, double highCutoff, double factor = 0.0) {
    for (std::size_t k = 0; k < hs.size(); ++k) {
        if (fs[k] >= lowCutoff && fs[k] <= highCutoff) hs[k] *= factor;
    }
}

inline std::vector<double> convolveLinear(const std::vector<double>& x, const std::vector<double>& h) {
    if (x.empty() || h.empty()) return {};
    std::vector<double> y(x.size() + h.size() - 1, 0.0);
    for (std::size_t i = 0; i < x.size(); ++i) {
        for (std::size_t j = 0; j < h.size(); ++j) {
            y[i + j] += x[i] * h[j];
        }
    }
    return y;
}

inline std::vector<double> diff(const std::vector<double>& ys) {
    if (ys.size() < 2) return {};
    std::vector<double> out(ys.size() - 1);
    for (std::size_t i = 1; i < ys.size(); ++i) {
        out[i - 1] = ys[i] - ys[i - 1];
    }
    return out;
}

inline std::vector<double> cumsum(const std::vector<double>& ys) {
    std::vector<double> out(ys.size());
    double sum = 0.0;
    for (std::size_t i = 0; i < ys.size(); ++i) {
        sum += ys[i];
        out[i] = sum;
    }
    return out;
}

inline void differentiateSpectrum(std::vector<Complex>& hs, const std::vector<double>& fs) {
    for (std::size_t k = 0; k < hs.size(); ++k) {
        hs[k] *= Complex(0.0, twoPi * fs[k]);
    }
}

inline void integrateSpectrum(std::vector<Complex>& hs, const std::vector<double>& fs) {
    if (!hs.empty()) hs[0] = 0.0;
    for (std::size_t k = 1; k < hs.size(); ++k) {
        hs[k] /= Complex(0.0, twoPi * fs[k]);
    }
}

inline Wave whiteUniformNoise(double amp, double duration, double sampleRate, std::mt19937& rng) {
    const std::size_t n = static_cast<std::size_t>(std::llround(duration * sampleRate));
    std::uniform_real_distribution<double> dist(-amp, amp);
    Wave wave{{}, sampleRate, 0.0};
    wave.ys.resize(n);
    for (double& y : wave.ys) y = dist(rng);
    return wave;
}

inline Wave gaussianNoise(double stddev, double duration, double sampleRate, std::mt19937& rng) {
    const std::size_t n = static_cast<std::size_t>(std::llround(duration * sampleRate));
    std::normal_distribution<double> dist(0.0, stddev);
    Wave wave{{}, sampleRate, 0.0};
    wave.ys.resize(n);
    for (double& y : wave.ys) y = dist(rng);
    return wave;
}

inline Wave brownianNoise(double amp, double duration, double sampleRate, std::mt19937& rng) {
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

inline Wave pinkNoise(double amp, double beta, double duration, double sampleRate, std::mt19937& rng) {
    Wave wave = whiteUniformNoise(1.0, duration, sampleRate, rng);
    auto hs = rfft(wave.ys);
    const auto fs = realFrequencies(wave.ys.size(), sampleRate);
    if (!hs.empty()) hs[0] = 0.0;
    for (std::size_t k = 1; k < hs.size(); ++k) {
        hs[k] /= std::pow(fs[k], beta / 2.0);
    }
    wave.ys = irfft(hs, wave.ys.size());
    unbias(wave.ys);
    normalize(wave.ys, amp);
    return wave;
}

inline double correlation(const std::vector<double>& a, const std::vector<double>& b) {
    const std::size_t n = std::min(a.size(), b.size());
    if (n == 0) return 0.0;
    const double meanA = std::accumulate(a.begin(), a.begin() + static_cast<std::ptrdiff_t>(n), 0.0) / static_cast<double>(n);
    const double meanB = std::accumulate(b.begin(), b.begin() + static_cast<std::ptrdiff_t>(n), 0.0) / static_cast<double>(n);
    double num = 0.0;
    double denA = 0.0;
    double denB = 0.0;
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

inline std::vector<double> autocorrelation(const std::vector<double>& ys, std::size_t maxLag) {
    maxLag = std::min(maxLag, ys.size() > 0 ? ys.size() - 1 : 0);
    std::vector<double> out(maxLag + 1, 0.0);
    for (std::size_t lag = 0; lag <= maxLag; ++lag) {
        std::vector<double> a(ys.begin(), ys.end() - static_cast<std::ptrdiff_t>(lag));
        std::vector<double> b(ys.begin() + static_cast<std::ptrdiff_t>(lag), ys.end());
        out[lag] = correlation(a, b);
    }
    return out;
}

inline double estimateFundamental(const std::vector<double>& ys, double sampleRate,
                                  double minHz = 50.0, double maxHz = 2000.0) {
    if (ys.size() < 3 || minHz <= 0.0 || maxHz <= minHz) return 0.0;
    const std::size_t minLag = std::max<std::size_t>(1, static_cast<std::size_t>(std::floor(sampleRate / maxHz)));
    const std::size_t maxLag = std::min<std::size_t>(
        static_cast<std::size_t>(std::ceil(sampleRate / minHz)), ys.size() / 2);
    if (minLag > maxLag) return 0.0;
    double bestCorr = -1.0;
    std::size_t bestLag = minLag;
    for (std::size_t lag = minLag; lag <= maxLag; ++lag) {
        std::vector<double> a(ys.begin(), ys.end() - static_cast<std::ptrdiff_t>(lag));
        std::vector<double> b(ys.begin() + static_cast<std::ptrdiff_t>(lag), ys.end());
        const double corr = correlation(a, b);
        if (corr > bestCorr) {
            bestCorr = corr;
            bestLag = lag;
        }
    }
    return sampleRate / static_cast<double>(bestLag);
}

inline std::vector<double> dctIV(const std::vector<double>& ys) {
    const std::size_t n = ys.size();
    std::vector<double> out(n, 0.0);
    if (n == 0) return out;
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

inline std::vector<double> inverseDctIV(const std::vector<double>& amps) {
    auto ys = dctIV(amps);
    if (amps.empty()) return ys;
    const double scale = 2.0 / static_cast<double>(amps.size());
    for (double& y : ys) y *= scale;
    return ys;
}

inline double foldedAlias(double frequency, double sampleRate) {
    double f = std::fmod(std::abs(frequency), sampleRate);
    if (f > sampleRate / 2.0) f = sampleRate - f;
    return f;
}

inline Wave amplitudeModulate(const Wave& input, double carrierHz) {
    Wave out{{}, input.sampleRate, input.start};
    out.ys.resize(input.ys.size());
    for (std::size_t i = 0; i < input.ys.size(); ++i) {
        const double t = input.start + static_cast<double>(i) / input.sampleRate;
        out.ys[i] = input.ys[i] * std::cos(twoPi * carrierHz * t);
    }
    return out;
}

inline Wave keepEveryNthSample(const Wave& input, std::size_t factor) {
    if (factor == 0) throw std::invalid_argument("factor must be nonzero");
    Wave out{{}, input.sampleRate, input.start};
    out.ys.assign(input.ys.size(), 0.0);
    for (std::size_t i = 0; i < input.ys.size(); i += factor) {
        out.ys[i] = input.ys[i];
    }
    return out;
}

inline Wave decimate(const Wave& filtered, std::size_t factor) {
    if (factor == 0) throw std::invalid_argument("factor must be nonzero");
    Wave out{{}, filtered.sampleRate / static_cast<double>(factor), filtered.start};
    out.ys.reserve((filtered.ys.size() + factor - 1) / factor);
    for (std::size_t i = 0; i < filtered.ys.size(); i += factor) {
        out.ys.push_back(filtered.ys[i]);
    }
    return out;
}

} // namespace thinkdsp_cpp
