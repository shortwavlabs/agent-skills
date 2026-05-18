# Analysis

Spectral analysis and signal detection algorithms in C/C++. Covers Fourier transforms, envelope following, beat detection, LPC analysis, and limiting.

## Table of Contents

1. [DFT (Direct Fourier Transform)](#dft-direct-fourier-transform)
2. [FFT](#fft)
3. [Walsh-Hadamard Transform](#walsh-hadamard-transform)
4. [Goertzel Algorithm (Single-Frequency Detection)](#goertzel-algorithm)
5. [Envelope Detection](#envelope-detection)
6. [Peak Follower](#peak-follower)
7. [Beat Detection](#beat-detection)
8. [LPC Analysis](#lpc-analysis)
9. [Look-Ahead Limiting (Binary Tree)](#look-ahead-limiting-binary-tree)
10. [Bit-Reversed Counting (for FFT)](#bit-reversed-counting)

---

## DFT (Direct Fourier Transform)

For partial analysis when you only need a few frequency bins (not the full spectrum).

```cpp
void partialAnalysis(const float* signal, int length, int maxPartial,
                     float* amplitudes, float sampleRate) {
    for (int h = 1; h <= maxPartial; h++) {
        float aa = 0, bb = 0;
        for (int i = 0; i < length; i++) {
            float w = 2.0f * M_PI * h * i / sampleRate;
            aa += signal[i] * cosf(w);
            bb += signal[i] * sinf(w);
        }
        amplitudes[h] = sqrtf(aa * aa + bb * bb) / length;
    }
}
```

---

## FFT

Fast Fourier Transform implementations. The split-radix variant (Sorensen) is generally fastest. Use existing libraries (FFTW, KissFFT, IPP) for production code — the algorithms below are for educational or embedded use.

Key FFT principles:
- Radix-2 Cooley-Tukey: O(N log N), requires power-of-2 sizes
- Split-radix: ~5.6% fewer operations than radix-2
- Real-valued FFT exploits symmetry for 2x speedup
- Inverse FFT = forward FFT with conjugate twiddle factors + 1/N scaling

For real-time audio, use overlap-add or overlap-save with a window (Hanning, Blackman-Harris) for spectral processing.

---

## Walsh-Hadamard Transform

Butterfly-based transform using only additions/subtractions (no multiplies). Basis functions are square waves, making it useful for fast spectral estimation where sine-like resolution isn't needed. Inverse = forward.

```cpp
void FWHT(std::vector<int>& data) {
    int n = data.size();
    int log2 = 0;
    for (int tmp = n; tmp > 1; tmp >>= 1) log2++;

    for (int i = 0; i < log2; i++) {
        for (int j = 0; j < (1 << log2); j += (1 << (i + 1))) {
            for (int k = 0; k < (1 << i); k++) {
                int a = data[j + k];
                int b = data[j + k + (1 << i)];
                data[j + k] = a + b;
                data[j + k + (1 << i)] = a - b;
            }
        }
    }
}
```

---

## Goertzel Algorithm

Efficient single-frequency DFT detection. Ideal for DTMF tone detection — computes one bin of the DFT without computing the entire spectrum.

```cpp
float goertzel(const float* x, int N, float targetFreq, float sampleRate) {
    float Skn = 0, Skn1 = 0, Skn2 = 0;
    float coeff = 2.0f * cosf(2.0f * M_PI * targetFreq / sampleRate);

    for (int i = 0; i < N; i++) {
        Skn2 = Skn1;
        Skn1 = Skn;
        Skn = coeff * Skn1 - Skn2 + x[i];
    }

    float WNk = expf(-2.0f * M_PI * targetFreq / sampleRate);
    float result = Skn - WNk * Skn1;
    return result;
}

// For magnitude only (most common use):
float goertzelMagnitude(const float* x, int N, float targetFreq, float sampleRate) {
    float s0 = 0, s1 = 0, s2 = 0;
    float coeff = 2.0f * cosf(2.0f * M_PI * targetFreq / sampleRate);

    for (int i = 0; i < N; i++) {
        s0 = x[i] + coeff * s1 - s2;
        s2 = s1;
        s1 = s0;
    }
    return sqrtf(s1 * s1 + s2 * s2 - coeff * s1 * s2);
}
```

---

## Envelope Detection

### One-Pole Envelope Detector with Attack/Release

```cpp
class EnvelopeDetector {
    float envelope = 0;
    float attackCoeff, releaseCoeff;
public:
    void init(float sampleRate, float attackMs, float releaseMs) {
        // 100% to 1% time definition
        attackCoeff  = expf(logf(0.01f) / (attackMs  * sampleRate * 0.001f));
        releaseCoeff = expf(logf(0.01f) / (releaseMs * sampleRate * 0.001f));
    }
    float process(float input) {
        float absInput = fabsf(input);
        if (absInput > envelope)
            envelope = attackCoeff * (envelope - absInput) + absInput;
        else
            envelope = releaseCoeff * (envelope - absInput) + absInput;
        return envelope;
    }
};
```

### RMS Envelope Detector

```cpp
class RMSEnvelope {
    float envelope = 0;
    float attackCoeff, releaseCoeff;
public:
    void init(float sampleRate, float attackMs, float releaseMs) {
        attackCoeff  = expf(-1.0f / (sampleRate * attackMs * 0.001f));
        releaseCoeff = expf(-1.0f / (sampleRate * releaseMs * 0.001f));
    }
    float process(float input) {
        float rms = input * input;  // square for RMS
        float theta = (rms > envelope) ? attackCoeff : releaseCoeff;
        envelope = (1.0f - theta) * rms + theta * envelope;
        return sqrtf(envelope);
    }
};
```

---

## Peak Follower

Instant attack on peaks, exponential decay. Useful for metering.

```cpp
class PeakFollower {
    float output = 0;
    float scalar;
public:
    void init(float sampleRate, float halfLifeSeconds) {
        scalar = powf(0.5f, 1.0f / (halfLifeSeconds * sampleRate));
    }
    float process(float input) {
        float absInput = fabsf(input);
        if (absInput >= output)
            output = absInput;
        else
            output *= scalar;
        if (output < 1e-10f) output = 0.0f;
        return output;
    }
};
```

---

## Beat Detection

Pipeline: 2nd-order LP (150Hz) -> peak envelope (0.02s release) -> Schmitt trigger (0.3/0.15) -> rising edge detector.

```cpp
class BeatDetector {
    float lpState = 0, envState = 0;
    float prevTrigger = 0;
    static constexpr float FREQ_LP = 150.0f;
    static constexpr float BEAT_RTIME = 0.02f;
public:
    void init(float sampleRate) {
        // Lowpass coefficient for 150Hz
        lpCoeff = 1.0f - expf(-2.0f * M_PI * FREQ_LP / sampleRate);
        // Release coefficient for 20ms
        relCoeff = expf(-1.0f / (sampleRate * BEAT_RTIME));
    }
    bool process(float input, float sampleRate) {
        // 1. Lowpass at 150Hz
        lpState += lpCoeff * (input - lpState);

        // 2. Peak envelope
        float absLp = fabsf(lpState);
        if (absLp > envState)
            envState = absLp;
        else
            envState = relCoeff * envState + (1.0f - relCoeff) * absLp;

        // 3. Schmitt trigger
        float trigger = 0;
        if (envState > 0.3f) trigger = 1.0f;
        if (envState < 0.15f) trigger = 0.0f;
        else trigger = prevTrigger;

        // 4. Rising edge = beat
        bool beat = (trigger > 0.5f && prevTrigger < 0.5f);
        prevTrigger = trigger;
        return beat;
    }
private:
    float lpCoeff, relCoeff;
};
```

---

## LPC Analysis

Linear Predictive Coding via warped autocorrelation and Levinson-Durbin recursion. Produces AR (all-pole) coefficients for formant analysis and resynthesis.

```cpp
void levinsonDurbin(const float* R, int order, float* a, float* K) {
    // R[0..order] = autocorrelation, a[1..order] = AR coefficients
    // K[1..order] = reflection coefficients
    float Em = R[0];
    a[0] = 1.0f;

    for (int m = 1; m <= order; m++) {
        float err = 0.0f;
        for (int k = 1; k < m; k++)
            err += a[k] * R[m - k];
        float km = (R[m] - err) / Em;

        // Update coefficients
        a[m] = km;
        for (int k = 1; k < m; k++)
            a[k] -= km * a[m - k];

        Em = (1.0f - km * km) * Em;
        K[m] = km;
    }
}
```

The `lambda` parameter for warped autocorrelation controls frequency resolution. Warped LPC maps the frequency axis for better resolution at low frequencies (matching auditory perception).

---

## Look-Ahead Limiting (Binary Tree)

Binary tree approach for tracking the maximum in a sliding window, enabling O(log N) per sample for lookahead limiting.

```cpp
class BinaryTreeLimiter {
    std::vector<unsigned> tree;
    int blockSize;
public:
    void init(int lookaheadSamples) {
        blockSize = lookaheadSamples;
        tree.resize(blockSize * 2);
    }
    // Add a value to the tree (O(log N))
    void add(unsigned section, unsigned size, unsigned value) {
        if (size == 1) { tree[section] = value; return; }
        unsigned half = size >> 1;
        if (value < half)
            add(section, half, value);
        else
            add(section + half, half, value - half);
        tree[section] = std::max(tree[section], tree[section + half]);
    }
    // Get maximum from tree (O(1))
    unsigned getMax() const { return tree[0]; }
};
```

---

## Bit-Reversed Counting

For FFT butterfly addressing. Non-branching increment in bit-reversed order.

```cpp
// Increment in bit-reversed order for N-point FFT
void bitReversedSequence(int N) {
    int r = 0, s = 0, N2 = N << 1;
    do {
        printf("%u ", s);
        r += 2;
        s ^= N - (N / (r & -r));
    } while (r < N2);
}

// Full 32-bit reversal (5 swap rows)
unsigned reverseBits(unsigned r) {
    r = ((r & 0x55555555) << 1) | ((r & 0xaaaaaaaa) >> 1);
    r = ((r & 0x33333333) << 2) | ((r & 0xcccccccc) >> 2);
    r = ((r & 0x0f0f0f0f) << 4) | ((r & 0xf0f0f0f0) >> 4);
    r = ((r & 0x00ff00ff) << 8) | ((r & 0xff00ff00) >> 8);
    r = (r << 16) | (r >> 16);
    return r;
}
```
