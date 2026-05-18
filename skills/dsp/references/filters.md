# Filters

Audio filter design and implementation in C/C++. Covers IIR (biquad, Moog ladder, state variable), FIR, crossover, and utility filters.

## Table of Contents

1. [First-Order IIR Building Blocks](#first-order-iir-building-blocks)
2. [Biquad / RBJ Filters](#biquad--rbj-filters)
3. [State Variable Filters](#state-variable-filters)
4. [Moog Ladder Filters](#moog-ladder-filters)
5. [FIR Filter Design](#fir-filter-design)
6. [Linkwitz-Riley Crossovers](#linkwitz-riley-crossovers)
7. [DC Blocking Filter](#dc-blocking-filter)
8. [Formant Filter](#formant-filter)
9. [Tilt Equalizer](#tilt-equalizer)
10. [Parameter Smoothing](#parameter-smoothing)
11. [All-Pass Filters](#all-pass-filters)

---

## First-Order IIR Building Blocks

Every complex IIR filter is built from these primitives. They process one state variable `s` and one coefficient `f` (or `g`).

```cpp
// 1. Leaky integrator
out = (s += in - f * s);

// 2. Basic lowpass
out = (s += f * (in - s));

// 3. Lowpass (alternate form)
out = (s = in + g * (s - in));

// 4. Basic highpass
out = in - (s += f * (in - s));

// 5. Basic allpass
s = in + g * (out = s - g * in);
```

The coefficient `f` relates to cutoff frequency:

```cpp
float f = 1.0f - expf(-2.0f * M_PI * cutoffHz / sampleRate);
```

---

## Biquad / RBJ Filters

The biquad (second-order IIR) is the workhorse of audio EQ. Robert Bristow-Johnson's "Audio EQ Cookbook" provides coefficient formulas for all standard filter types.

### Transfer Function

```
H(z) = (b0 + b1*z^-1 + b2*z^-2) / (a0 + a1*z^-1 + a2*z^-2)
```

### Direct Form I Processing

```cpp
float processBiquad(float input) {
    float output = b0 * input
                 + b1 * x1
                 + b2 * x2
                 - a1 * y1
                 - a2 * y2;
    x2 = x1; x1 = input;
    y2 = y1; y1 = output;
    return output;
}
```

### Coefficient Calculation

Shared variables for all types:

```cpp
float w0 = 2.0f * M_PI * fc / sampleRate;
float alpha = sinf(w0) / (2.0f * Q);
```

#### Lowpass

```cpp
b0 =  (1.0f - cosf(w0)) / 2.0f;
b1 =   1.0f - cosf(w0);
b2 =  (1.0f - cosf(w0)) / 2.0f;
a0 =   1.0f + alpha;
a1 =  -2.0f * cosf(w0);
a2 =   1.0f - alpha;
```

#### Highpass

```cpp
b0 =  (1.0f + cosf(w0)) / 2.0f;
b1 = -(1.0f + cosf(w0));
b2 =  (1.0f + cosf(w0)) / 2.0f;
a0 =   1.0f + alpha;
a1 =  -2.0f * cosf(w0);
a2 =   1.0f - alpha;
```

#### Bandpass (constant skirt gain, peak gain = Q)

```cpp
b0 =   alpha;
b1 =   0.0f;
b2 =  -alpha;
a0 =   1.0f + alpha;
a1 =  -2.0f * cosf(w0);
a2 =   1.0f - alpha;
```

#### Notch

```cpp
b0 =   1.0f;
b1 =  -2.0f * cosf(w0);
b2 =   1.0f;
a0 =   1.0f + alpha;
a1 =  -2.0f * cosf(w0);
a2 =   1.0f - alpha;
```

#### Peaking EQ

```cpp
float A = powf(10.0f, dBgain / 40.0f);
float alpha = sinf(w0) / (2.0f * Q);

b0 =   1.0f + alpha * A;
b1 =  -2.0f * cosf(w0);
b2 =   1.0f - alpha * A;
a0 =   1.0f + alpha / A;
a1 =  -2.0f * cosf(w0);
a2 =   1.0f - alpha / A;
```

#### Low Shelf

```cpp
float A = powf(10.0f, dBgain / 40.0f);
float alpha = sinf(w0) / 2.0f * sqrtf((A + 1.0f / A) * (1.0f / S - 1.0f) + 2.0f);

b0 =    A * ((A + 1.0f) - (A - 1.0f) * cosf(w0) + 2.0f * sqrtf(A) * alpha);
b1 =  2.0f * A * ((A - 1.0f) - (A + 1.0f) * cosf(w0));
b2 =    A * ((A + 1.0f) - (A - 1.0f) * cosf(w0) - 2.0f * sqrtf(A) * alpha);
a0 =        (A + 1.0f) + (A - 1.0f) * cosf(w0) + 2.0f * sqrtf(A) * alpha;
a1 = -2.0f * ((A - 1.0f) + (A + 1.0f) * cosf(w0));
a2 =        (A + 1.0f) + (A - 1.0f) * cosf(w0) - 2.0f * sqrtf(A) * alpha;
```

Always normalize by `a0`: divide all `b0,b1,b2,a1,a2` by `a0` and set `a0 = 1.0f`. Q must be >= 0.5.

---

## State Variable Filters

SVFs simultaneously produce lowpass, highpass, bandpass, and notch outputs from a single structure. They're efficient and musically responsive.

### Classic SVF (Dattorro)

```cpp
class StateVariableFilter {
    float low = 0, band = 0;
    float f, q;
public:
    void setCutoff(float cutoffHz, float sampleRate) {
        f = 2.0f * sinf(M_PI * cutoffHz / sampleRate);
    }
    void setResonance(float resonance) {
        q = resonance;  // 0 < q <= 1
    }
    void process(float input, float& lp, float& hp, float& bp, float& notch) {
        low += f * band;
        hp = input - low - q * band;
        band = f * hp + band;
        notch = hp + low;
    }
};
```

Cutoff is limited to approximately sampleRate / 4.

### Chamberlin SVF

```cpp
class ChamberlinSVF {
    float d1 = 0, d2 = 0;  // delay elements
    float f1, q1;
    static constexpr float kDenorm = 1.0e-24f;
public:
    void setCoefficients(float freqHz, float Q, float sampleRate) {
        f1 = 2.0f * sinf(M_PI * freqHz / sampleRate);
        q1 = 1.0f / Q;
    }
    void process(float input, float& low, float& high, float& band, float& notch) {
        low  = d2 + f1 * d1;
        high = input - low - q1 * d1;
        band = f1 * high + d1;
        notch = high + low;
        d1 = band + kDenorm;
        d2 = low + kDenorm;
    }
};
```

### Double-Sampled SVF (Stable at High Frequencies)

Runs the SVF twice per sample with half the effective frequency, then averages outputs. This dramatically improves stability near Nyquist.

```cpp
class DoubleSampledSVF {
    float low = 0, band = 0;
    float freq, damp;
public:
    void setCoefficients(float fc, float resonance, float sampleRate) {
        freq = 2.0f * sinf(M_PI * std::min(0.25f, fc / (sampleRate * 2.0f)));
        damp = std::min(2.0f * (1.0f - powf(resonance, 0.25f)),
                        std::min(2.0f, 2.0f / freq - freq * 0.5f));
    }
    float process(float input, float drive = 0.0f) {
        // First pass
        float high = input - low - damp * band;
        band = freq * high + band - drive * band * band * band;
        low = low + freq * band;
        // Second pass
        float input2 = input;  // same input
        float high2 = input2 - low - damp * band;
        band = freq * high2 + band - drive * band * band * band;
        low = low + freq * band;
        return low;  // or band, high, etc.
    }
};
```

---

## Moog Ladder Filters

The Moog ladder is a 4-pole resonant lowpass with a distinctive "musical" sound. Multiple models exist with different accuracy/complexity tradeoffs.

### Basic Moog VCF (24 dB/oct)

Four cascaded one-pole filters with global resonance feedback.

```cpp
class MoogVCF {
    float y1 = 0, y2 = 0, y3 = 0, y4 = 0;
    float x1 = 0, x2 = 0, x3 = 0, x4 = 0;
public:
    float process(float input, float cutoff, float resonance) {
        // Frequency tuning (improved over empirical formula)
        float f = cutoff;
        float k = 2.0f * sinf(f * M_PI * 0.5f) - 1.0f;

        // First pole
        x1 = y1;
        y1 = (input - resonance * y4) + x1;
        // Band-limited sigmoid (approximates tanh)
        y1 -= y1 * y1 * y1 / 6.0f;

        // Second pole
        x2 = y2;
        y2 = y1 + x2;

        // Third pole
        x3 = y3;
        y3 = y2 + x3;

        // Fourth pole
        x4 = y4;
        y4 = y3 + x4;

        return y4;
    }
};
```

### Nonlinear Moog Ladder (Antti's Model)

More accurate model using `tanh()` to simulate transistor differential pairs. Requires 2x oversampling for best results.

```cpp
class NonlinearMoog {
    float az1 = 0, az2 = 0, az3 = 0, az4 = 0, az5 = 0;
    float ay1 = 0, ay2 = 0, ay3 = 0, ay4 = 0;
    double v2 = 40000.0;  // twice thermal voltage
public:
    float process(float input, float cutoffHz, float resonance, float sampleRate) {
        double fc = cutoffHz / sampleRate;
        double kfcr = 1.8730 * fc*fc*fc + 0.4955 * fc*fc - 0.6490 * fc + 0.9988;
        double kacr = -3.9364 * fc*fc + 1.8409 * fc + 0.9968;
        double k2vg = v2 * (1.0 - exp(-2.0 * M_PI * kfcr * fc));

        double ain = tanh(input / v2);
        double ares = tanh(resonance * az4 / v2);

        ay1 = az1 + k2vg * (ain - ares - (1.0/v2) * az1);
        ay2 = az2 + k2vg * (tanh(ay1/v2) - (1.0/v2) * az2);
        ay3 = az3 + k2vg * (tanh(ay2/v2) - (1.0/v2) * az3);
        ay4 = az4 + k2vg * (tanh(ay3/v2) - (1.0/v2) * az4);

        // Half-sample delay compensation
        double amf = (ay4 + az5) * 0.5;

        az1 = ay1; az2 = ay2; az3 = ay3; az4 = ay4; az5 = ay4;
        return (float)amf;
    }
};
```

### Simple 2-Pole (RC-style)

A lightweight Moog-style 2-pole filter.

```cpp
class RCFilter {
    float v0 = 0, v1 = 0;
public:
    void process(float input, float cutoff, float resonance) {
        float c = powf(0.5f, (128.0f - cutoff) / 16.0f);
        float r = powf(0.5f, (resonance + 24.0f) / 16.0f);
        v0 = (1.0f - r * c) * v0 - c * v1 + c * input;
        v1 = (1.0f - r * c) * v1 + c * v0;
    }
    float getLowpass() const { return v1; }
    float getHighpass() const { return input - v1; }
};
```

---

## FIR Filter Design

### Windowed Sinc Method

Generates coefficients for LP, HP, BP, and BS FIR filters using windowed sinc functions.

```cpp
void generateSincFIR(float* coeffs, int numTaps, float cutoff, int type,
                     int windowType = 0 /* 0=Blackman, 1=Hanning, 2=Hamming */) {
    int M = numTaps - 1;
    float sum = 0.0f;

    for (int i = 0; i <= M; i++) {
        // Sinc
        float sinc;
        if (i == M / 2)
            sinc = 2.0f * cutoff;
        else
            sinc = sinf(2.0f * M_PI * cutoff * (i - M / 2.0f))
                 / (M_PI * (i - M / 2.0f));

        // Window
        float w;
        switch (windowType) {
            case 0:  // Blackman
                w = 0.42f - 0.5f * cosf(2.0f * M_PI * i / M)
                         + 0.08f * cosf(4.0f * M_PI * i / M);
                break;
            case 1:  // Hanning
                w = 0.5f - 0.5f * cosf(2.0f * M_PI * i / M);
                break;
            case 2:  // Hamming
                w = 0.54f - 0.46f * cosf(2.0f * M_PI * i / M);
                break;
            default: w = 1.0f;
        }

        coeffs[i] = sinc * w;
        sum += coeffs[i];
    }

    // Normalize to unity gain
    for (int i = 0; i < numTaps; i++)
        coeffs[i] /= sum;

    // Spectral inversion: LP -> HP
    if (type == 1) {
        for (int i = 0; i < numTaps; i++) coeffs[i] = -coeffs[i];
        coeffs[M / 2] += 1.0f;
    }
}
```

---

## Linkwitz-Riley Crossovers

Used for speaker crossovers. The sum of LP + HP produces a perfectly flat magnitude response. 4th-order (LR4) is most common.

```cpp
class LinkwitzRiley4 {
    // Shared feedback coefficients for both LP and HP
    double b1, b2, b3, b4;
    double lpA0, lpA1, lpA2, lpA3, lpA4;  // LP numerator
    double hpA0, hpA1, hpA2, hpA3, hpA4;  // HP numerator

    // State (two parallel 2nd-order sections)
    double x1 = 0, x2 = 0, x3 = 0, x4 = 0;
    double y1_lp = 0, y2_lp = 0, y3_lp = 0, y4_lp = 0;
    double y1_hp = 0, y2_hp = 0, y3_hp = 0, y4_hp = 0;
public:
    void init(float fc, float sampleRate) {
        double wc = 2.0 * M_PI * fc;
        double k = wc / tan(M_PI * fc / sampleRate);
        double wc2 = wc * wc, wc3 = wc2 * wc, wc4 = wc2 * wc2;
        double k2 = k * k, k3 = k2 * k, k4 = k2 * k2;

        double a_tmp = wc4 + 2.0 * sqrt(2.0) * wc3 * k
                     + 4.0 * wc2 * k2 + 2.0 * sqrt(2.0) * wc * k3 + k4;

        // Shared feedback
        b1 = (4.0 * wc4 + 2.0 * sqrt(2.0) * wc3 * k
            - 2.0 * sqrt(2.0) * wc * k3 - 4.0 * k4) / a_tmp;
        b2 = (6.0 * wc4 - 8.0 * wc2 * k2 + 6.0 * k4) / a_tmp;
        b3 = (4.0 * wc4 - 2.0 * sqrt(2.0) * wc3 * k
            + 2.0 * sqrt(2.0) * wc * k3 - 4.0 * k4) / a_tmp;
        b4 = (wc4 - 2.0 * sqrt(2.0) * wc3 * k
            + 4.0 * wc2 * k2 - 2.0 * sqrt(2.0) * wc * k3 + k4) / a_tmp;

        // LP numerator
        lpA0 = wc4 / a_tmp;
        lpA1 = 4.0 * wc4 / a_tmp;
        lpA2 = 6.0 * wc4 / a_tmp;
        lpA3 = 4.0 * wc4 / a_tmp;
        lpA4 = wc4 / a_tmp;

        // HP numerator
        hpA0 = k4 / a_tmp;
        hpA1 = -4.0 * k4 / a_tmp;
        hpA2 = 6.0 * k4 / a_tmp;
        hpA3 = -4.0 * k4 / a_tmp;
        hpA4 = k4 / a_tmp;
    }
};
```

Use double precision for stability at low frequencies.

---

## DC Blocking Filter

A 1-pole/1-zero highpass at sub-audio frequencies. Essential for removing DC offset from audio signals.

```cpp
class DCBlocker {
    float xm1 = 0, ym1 = 0;
    float R;
public:
    void init(float sampleRate, float cutoffHz = 20.0f) {
        R = 1.0f - (M_PI * 2.0f * cutoffHz / sampleRate);
    }
    float process(float input) {
        float output = input - xm1 + R * ym1;
        xm1 = input;
        ym1 = output;
        return output;
    }
};
```

Common R values for reference: -3dB at 40Hz → `R = 1 - 250/sr`, at 30Hz → `R = 1 - 190/sr`, at 20Hz → `R = 1 - 126/sr`.

---

## Formant Filter

10th-order FIR filter for vowel synthesis using pre-computed coefficients.

```cpp
// Female soprano formant data at 44.1 kHz
static const float vowelA[11] = { 0.12f, 0.24f, 0.0f, 0.0f, 0.0f,
                                   0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f };
// ... additional vowel coefficients for E, I, O, U

class FormantFilter {
    float z[11] = {};
    const float* coeffA;
    const float* coeffB;
    float morph = 0.0f;  // 0 = vowel A, 1 = vowel B
public:
    void setVowels(const float* a, const float* b) {
        coeffA = a; coeffB = b;
    }
    void setMorph(float m) { morph = m; }
    float process(float input) {
        // Shift state
        for (int i = 10; i > 0; i--) z[i] = z[i-1];
        z[0] = input;

        float output = 0;
        for (int i = 0; i < 11; i++) {
            float c = coeffA[i] + morph * (coeffB[i] - coeffA[i]);
            output += z[i] * c;
        }
        return output;
    }
};
```

---

## Tilt Equalizer

Boosts one frequency range while cutting the other, pivoting around a center frequency. Mimics the Elysia mPressor "Niveau" filter.

```cpp
class TiltEQ {
    float lpOut = 0;
    float a0, b1, lgain, hgain;
    static constexpr float denorm = 1e-30f;
public:
    void init(float f0, float gain, float sampleRate) {
        const float amp = 6.0f / logf(2.0f);
        const float gfactor = 5.0f;

        float g1, g2;
        if (gain > 0) { g1 = -gfactor * gain; g2 = gain; }
        else           { g1 = -gain;           g2 = gfactor * gain; }

        lgain = expf(g1 / amp) - 1.0f;
        hgain = expf(g2 / amp) - 1.0f;

        float omega = 2.0f * M_PI * f0;
        float n = 1.0f / (3.0f * sampleRate + omega);
        a0 = 2.0f * omega * n;
        b1 = (3.0f * sampleRate - omega) * n;
    }
    float process(float input) {
        lpOut = a0 * input + b1 * lpOut + denorm;
        return input + lgain * lpOut + hgain * (input - lpOut);
    }
};
```

---

## Parameter Smoothing

One-pole lowpass for smoothing parameter changes over time. Prevents clicks and zipper noise.

```cpp
class ParamSmoother {
    float z = 0.0f;
    float a;
public:
    void init(float smoothingTimeMs, float sampleRate) {
        a = expf(-2.0f * M_PI / (smoothingTimeMs * 0.001f * sampleRate));
    }
    float process(float input) {
        return z = input + a * (z - input);
    }
};
```

---

## All-Pass Filters

All-pass filters have flat magnitude response but introduce frequency-dependent phase shift. Essential for reverb design and phase alignment.

```cpp
class AllPassFilter {
    float z = 0;
    float g;
public:
    void setCoefficient(float g) { this->g = g; }
    // From frequency: g = (1 - v) / (1 + v) where v = freq/sr
    float process(float input) {
        float output = -g * input + z;
        z = input + g * output;
        return output;
    }
};
```
