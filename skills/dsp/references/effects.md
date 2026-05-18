# Effects

Audio effect algorithms in C/C++. Covers delay, reverb, dynamics processing, modulation, distortion, lo-fi, stereo processing, and convolution.

## Table of Contents

1. [Delay Lines](#delay-lines)
2. [Reverb](#reverb)
3. [Dynamics (Compressor/Limiter)](#dynamics-compressorlimiter)
4. [Modulation (Phaser/Wah/Vibe)](#modulation-phaserwahvibe)
5. [Waveshaping / Distortion](#waveshaping--distortion)
6. [Lo-Fi / Bit Crushing](#lo-fi--bit-crushing)
7. [Stereo Processing](#stereo-processing)
8. [Dynamic Convolution](#dynamic-convolution)
9. [Fold-Back Distortion](#fold-back-distortion)

---

## Delay Lines

### Simple Static Delay

Circular buffer with write-then-read indexing.

```cpp
class SimpleDelay {
    std::vector<float> buffer;
    int index = 0;
public:
    SimpleDelay(int delaySamples) : buffer(delaySamples, 0.0f) {}
    float process(float input) {
        float output = buffer[index];
        buffer[index] = input;
        index = (index + 1) % (int)buffer.size();
        return output;
    }
};
```

### Feedback Delay with Interpolation

Smooth delay time changes without pitch artifacts using cubic Hermite interpolation.

```cpp
class FeedbackDelay {
    std::vector<float> buffer;
    int writeIndex = 0;
    float delayTime = 0.5f;    // 0..1 normalized
    float feedback = 0.5f;     // 0..1
public:
    FeedbackDelay(int maxDelaySamples) : buffer(maxDelaySamples, 0.0f) {}

    float process(float input) {
        int bufSize = (int)buffer.size();
        // Fractional read position
        float readPos = writeIndex - delayTime * bufSize;
        if (readPos < 0) readPos += bufSize;

        int i0 = (int)readPos;
        int im1 = (i0 - 1 + bufSize) % bufSize;
        int i1 = (i0 + 1) % bufSize;
        int i2 = (i0 + 2) % bufSize;
        float frac = readPos - i0;

        // Cubic Hermite interpolation
        float y0 = buffer[i0];
        float y_1 = buffer[im1], y1 = buffer[i1], y2 = buffer[i2];
        float c0 = y0;
        float c1 = 0.5f * (y1 - y_1);
        float c2 = y_1 - 2.5f * y0 + 2.0f * y1 - 0.5f * y2;
        float c3 = 0.5f * (y2 - y_1) + 1.5f * (y0 - y1);
        float output = ((c3 * frac + c2) * frac + c1) * frac + c0;

        // Write with feedback
        buffer[writeIndex] = input + output * feedback;
        writeIndex = (writeIndex + 1) % bufSize;

        return output;
    }
};
```

---

## Reverb

### Reverberation Techniques Overview

| Approach | Quality | CPU | Notes |
|----------|---------|-----|-------|
| Schroeder (parallel combs + series allpass) | Low | Low | Metallic on transients |
| Nested allpass (Gardner) | Medium | Low-Med | Allpass within allpass delay line |
| Dattorro "figure-8" feedback | High | Medium | 4 allpass reverbs, modulated delays, based on Lexicon |
| Feedback Delay Networks (FDN) | High | Medium | Modulating delay lines + feedback matrices |
| Waveguide (Julius Smith) | High | Medium | Equivalent to FDN, nice sound |
| Convolution | Best | High | Inflexible, computationally expensive |

FDN and waveguide approaches are the best algorithmic options.

### Delay Time Calculation for Reverb Diffusion

Calculates delay times and feedback gains for parallel diffuse delays from a base time and RT60.

```cpp
struct DiffusionLine {
    float delayMs;
    float gain;
};

std::vector<DiffusionLine> calculateDiffusionLines(
    int numLines, float baseTimeMs, float baseGain) {
    std::vector<DiffusionLine> lines(numLines);
    float revTime = -3.0f * baseTimeMs / log10f(baseGain);

    for (int n = 0; n < numLines; n++) {
        lines[n].delayMs = baseTimeMs / powf(2.0f, (float)n / numLines);
        lines[n].gain = powf(10.0f, -(3.0f * lines[n].delayMs) / revTime);
    }
    return lines;
}
```

---

## Dynamics (Compressor/Limiter)

### RMS Compressor with Attack/Release

```cpp
class Compressor {
    float env = 0;
    float attackCoeff, releaseCoeff;
    float threshold, slope;
public:
    void init(float sampleRate, float attackMs, float releaseMs,
              float thresholdDb, float ratio) {
        attackCoeff = expf(-1.0f / (sampleRate * attackMs * 0.001f));
        releaseCoeff = expf(-1.0f / (sampleRate * releaseMs * 0.001f));
        threshold = powf(10.0f, thresholdDb / 20.0f);
        slope = 1.0f - (1.0f / ratio);
    }

    float process(float input) {
        float inputAbs = fabsf(input);
        // Envelope follower with separate attack/release
        if (inputAbs > env)
            env = inputAbs + attackCoeff * (env - inputAbs);
        else
            env = inputAbs + releaseCoeff * (env - inputAbs);

        // Gain reduction
        float gain = 1.0f;
        if (env > threshold)
            gain = 1.0f - slope * (env - threshold);

        return input * gain;
    }
};
```

### Lookahead Limiter

Delays audio by the lookahead amount, scans ahead for peaks, applies smooth gain reduction.

```cpp
class LookaheadLimiter {
    std::vector<float> delayBuffer;
    std::vector<float> gainReduction;
    int writePos = 0, lookaheadSamples;
    float attackCoeff, releaseCoeff;
    float ceiling;
public:
    void init(float sampleRate, float lookaheadMs, float releaseMs, float ceilingDb) {
        lookaheadSamples = (int)(sampleRate * lookaheadMs * 0.001f);
        delayBuffer.resize(lookaheadSamples, 0.0f);
        gainReduction.resize(lookaheadSamples, 1.0f);
        attackCoeff = 1.0f / lookaheadSamples;  // linear ramp
        releaseCoeff = expf(-1.0f / (sampleRate * releaseMs * 0.001f));
        ceiling = powf(10.0f, ceilingDb / 20.0f);
    }

    float process(float input) {
        // Write to delay buffer
        delayBuffer[writePos] = input;

        // Detect peak in lookahead window
        float peak = 0;
        for (int i = 0; i < lookaheadSamples; i++)
            peak = std::max(peak, fabsf(delayBuffer[i]));

        // Calculate gain reduction
        float targetGain = peak > ceiling ? ceiling / peak : 1.0f;
        float currentGain = gainReduction[writePos];
        float gain = currentGain + attackCoeff * (targetGain - currentGain);
        gain = std::min(gain, targetGain);
        gain = gain + releaseCoeff * (1.0f - gain);  // release toward unity

        gainReduction[writePos] = gain;

        // Read from delay buffer with gain
        int readPos = (writePos + 1) % lookaheadSamples;
        float output = delayBuffer[readPos] * gainReduction[readPos];

        writePos = (writePos + 1) % lookaheadSamples;
        return output;
    }
};
```

---

## Modulation (Phaser/Wah/Vibe)

### Phaser (6-Stage Allpass)

```cpp
class Phaser {
    static constexpr int kStages = 6;
    float allpassState[kStages] = {};
    float lfoPhase = 0;
    float depth = 0.5f, feedback = 0.7f;
    float lfoFreq = 0.5f;    // Hz
    float minFreq = 200.0f;   // Hz
    float maxFreq = 800.0f;   // Hz
    float sampleRate;
    float previousOutput = 0;
    static constexpr float kDenorm = 1e-25f;
public:
    void init(float sr) { sampleRate = sr; }

    float process(float input) {
        // LFO
        lfoPhase += lfoFreq / sampleRate;
        if (lfoPhase >= 1.0f) lfoPhase -= 1.0f;
        float lfoValue = 0.5f * (sinf(2.0f * M_PI * lfoPhase) + 1.0f);
        float freq = minFreq + (maxFreq - minFreq) * lfoValue;

        // Allpass coefficient from frequency
        float v = freq / sampleRate;
        float a1 = (1.0f - v) / (1.0f + v);

        // Process through 6 allpass stages
        float output = input + feedback * previousOutput;
        for (int i = 0; i < kStages; i++) {
            float tmp = output;
            output = -a1 * output + allpassState[i] + kDenorm;
            allpassState[i] = a1 * output + tmp;
        }
        previousOutput = output;

        // Mix dry/wet
        return input + depth * (output - input);
    }
};
```

---

## Waveshaping / Distortion

### Bram de Jong Waveshaper

Musical distortion with controllable hardness. `a` ranges from 1 (soft) to infinity (hard).

```cpp
float waveshaper(float x, float a) {
    // x in [-1..1], a = distortion (1..inf)
    return x * (fabsf(x) + a) / (x * x + (a - 1.0f) * fabsf(x) + 1.0f);
}
```

### Soft Saturation (Piecewise)

```cpp
float softSaturation(float x, float a) {
    // a in [0..1] controls knee point
    if (x < a) return x;
    if (x > 1.0f) return (a + 1.0f) / 2.0f;
    return a + (x - a) / (1.0f + powf((x - a) / (1.0f - a), 2.0f));
}
// Normalize: output *= 2.0f / (a + 1.0f);
```

### Variable-Hardness Clipping

```cpp
float variableClip(float x, float k) {
    // k >= 1: k=1 is soft (atan shape), k=infinity is hard clipping
    return tanhf(x * k) / tanhf(k);
}
// Fast approximation:
float fastVariableClip(float x, float shape) {
    float inv_shape = 1.0f / atanf(shape);
    return inv_shape * atanf(x * shape);
}
```

### Polynomial Waveshaper (3rd harmonic)

```cpp
float polynomialDistort(float in) {
    // Produces 2nd harmonic from sinusoid input
    // Requires 3x oversampling for alias-free operation
    return 1.5f * in - 0.5f * in * in * in;
}
```

### Gloubi-Boulga Waveshaper

Complex waveshaper with rich harmonic content.

```cpp
float gloubiBoulga(float input) {
    double x = input * 0.686306;
    double a = 1.0 + exp(sqrt(fabs(x)) * -0.75);
    return (float)((exp(x) - exp(-x * a)) / (exp(x) + exp(-x)));
}
// Fast approximation: x - 0.15*x^2 - 0.15*x^3
```

---

## Lo-Fi / Bit Crushing

### Decimator (Bit Depth + Sample Rate Reduction)

```cpp
class Decimator {
    float y = 0, cnt = 0;
    float rate;     // 0..1, 1 = original sample rate
    int bits;       // 1..32
public:
    Decimator(int bits = 8, float rate = 0.5f) : bits(bits), rate(rate) {}
    float process(float input) {
        long m = 1L << (bits - 1);
        cnt += rate;
        if (cnt >= 1.0f) {
            cnt -= 1.0f;
            y = (float)(long)(input * m) / (float)m;
        }
        return y;
    }
};
```

### Fractional Bit Depth Reduction

```cpp
float bitcrush(float x, float bits) {
    float quantum = powf(2.0f, -bits);
    return floorf(x / quantum + 0.5f) * quantum;
}
```

---

## Stereo Processing

### M/S Width Control

```cpp
void stereoWidth(float& left, float& right, float width) {
    // width: < 1 = narrow, 1 = no change, > 1 = wide, 0 = mono
    float tmp = 1.0f / std::max(1.0f + width, 2.0f);  // volume compensation
    float coefM = 1.0f * tmp;
    float coefS = width * tmp;

    float m = (left + right) * coefM;
    float s = (right - left) * coefS;
    left = m - s;
    right = m + s;
}
```

### Stereo Field Rotation

```cpp
void stereoRotate(float& left, float& right, float angle) {
    float c = cosf(angle);
    float s = sinf(angle);
    float l = left * c - right * s;
    float r = left * s + right * c;
    left = l;
    right = r;
}
```

### Stereo Enhancer (Side Boost)

```cpp
void stereoEnhance(float& left, float& right, float width) {
    float mono = (left + right) * 0.5f;
    float delta = (left - mono) * width;  // width: 0.0 to 1.5
    left += delta;
    right -= delta;
}
```

---

## Dynamic Convolution

Naive amplitude-dependent impulse response selection. Expensive (O(L) per sample) but models nonlinear systems.

```cpp
class DynamicConvolution {
    std::vector<std::vector<float>> impulseResponses;  // [amplitudeRegion][sample]
    std::vector<int> amplitudeRegion;                  // per-sample history
    int irLength;
    float dv;  // amplitude quantization step
public:
    void init(int numRegions, int irLen, float maxAmplitude) {
        irLength = irLen;
        dv = maxAmplitude / numRegions;
        impulseResponses.resize(numRegions, std::vector<float>(irLen, 0.0f));
        amplitudeRegion.resize(irLen, 0);
        // Pre-fill IRs with your measured/-designed responses
    }

    float process(float input) {
        int sel = std::min((int)(dv * fabsf(input)),
                          (int)impulseResponses.size() - 1);

        float output = 0.0f;
        for (int i = 0; i < irLength; i++) {
            output += input * impulseResponses[amplitudeRegion[i]][i];
        }

        // Shift amplitude region history
        for (int i = irLength - 1; i > 0; i--)
            amplitudeRegion[i] = amplitudeRegion[i - 1];
        amplitudeRegion[0] = sel;

        return output;
    }
};
```

---

## Fold-Back Distortion

Signal exceeding the threshold is mirrored (folded) back instead of clipped.

```cpp
float foldBack(float input, float threshold) {
    if (input > threshold || input < -threshold) {
        input = fabsf(fabsf(fmodf(input + threshold, threshold * 4.0f))
                      - threshold * 2.0f) - threshold;
    }
    return input;
}
```
