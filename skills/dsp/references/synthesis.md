# Synthesis

Sound generation algorithms in C/C++. Covers oscillators, bandlimited waveforms, FM/PM synthesis, noise generation, envelope generators, and specialized techniques.

## Table of Contents

1. [Sine / Oscillator Generation](#sine--oscillator-generation)
2. [Wavetable Oscillator](#wavetable-oscillator)
3. [Bandlimited Waveform Synthesis](#bandlimited-waveform-synthesis)
4. [Discrete Summation Formula (DSF)](#discrete-summation-formula-dsf)
5. [Phase Modulation vs Frequency Modulation](#phase-modulation-vs-frequency-modulation)
6. [Noise Generation](#noise-generation)
7. [Envelope Generation](#envelope-generation)
8. [Chebyshev Waveshaping](#chebyshev-waveshaping)
9. [MinBLEP Table Generation](#minblep-table-generation)
10. [Formant / Vocal Synthesis](#formant--vocal-synthesis)
11. [Granular Time Stretching](#granular-time-stretching)
12. [LFO and Chaotic Generators](#lfo-and-chaotic-generators)

---

## Sine / Oscillator Generation

### SVF Oscillator (Simultaneous Sine + Cosine)

Fastest method. Degrades above sampleRate/6. Needs periodic amplitude resync.

```cpp
class SVFOscillator {
    float s0 = 0, s1 = 1;  // s0=sine, s1=cosine
    float a;
public:
    void setFrequency(float freq, float sampleRate) {
        a = 2.0f * sinf(M_PI * freq / sampleRate);
    }
    void process() {
        s0 -= a * s1;
        s1 += a * s0;
    }
    float sine()   const { return s0; }
    float cosine() const { return s1; }
    void resync() {  // Periodic amplitude correction
        float tmp = 1.5f - 0.5f * (s1 * s1 + s0 * s0);
        s0 *= tmp;
        s1 *= tmp;
    }
};
```

### Second-Order Recurrence Oscillator

James McCartney / Julius O. Smith method. Extremely efficient — one multiply per sample after setup.

```cpp
class RecurrenceOscillator {
    float y1, y2, b1;
public:
    void init(float freq, float sampleRate, float initialPhase = 0) {
        float w = freq * 2.0f * M_PI / sampleRate;
        b1 = 2.0f * cosf(w);
        y1 = sinf(initialPhase - w);
        y2 = sinf(initialPhase - 2.0f * w);
    }
    // Unrolled by 3 for efficiency (no variable swaps)
    void process3(float& out0, float& out1, float& out2) {
        out0 = b1 * y1 - y2;
        out2 = b1 * out0 - y1;
        out1 = b1 * out2 - out0;
        y1 = out1;
        y2 = out2;
    }
};
```

Caveat: changing frequency causes amplitude perturbation. Recalculate phase from the last value if frequency changes.

### Taylor Series Sine

Linear frequency control — suitable for FM and time-varying applications.

```cpp
class TaylorSineOsc {
    float phase = 0, phaseInc;
public:
    void setFrequency(float freq, float sampleRate) {
        phaseInc = freq / sampleRate;
    }
    float process() {
        phase += phaseInc;
        if (phase >= 1.0f) phase -= 1.0f;

        // Map to [-0.5, 0.5] for accuracy
        float x = phase;
        if (x > 0.5f) x -= 1.0f;
        x *= 2.0f * M_PI;

        // Taylor series: sin(x) ≈ x - x^3/3! + x^5/5! - x^7/7! + x^9/9!
        float x2 = x * x;
        return x * (1.0f - x2 / 6.0f * (1.0f - x2 / 20.0f
                   * (1.0f - x2 / 42.0f * (1.0f - x2 / 72.0f))));
    }
};
```

---

## Wavetable Oscillator

Pre-computed waveform table with interpolation. The standard approach for polyphonic synthesizers.

```cpp
class WavetableOsc {
    std::vector<float> table;
    float phase = 0, phaseInc;
    int tableSize;
public:
    WavetableOsc(int size = 1024) : tableSize(size), table(size + 1) {
        // Fill table (example: sawtooth)
        for (int i = 0; i < size; i++)
            table[i] = 2.0f * i / size - 1.0f;
        table[size] = table[0];  // wrap point for interpolation
    }

    void setFrequency(float freq, float sampleRate) {
        phaseInc = freq / sampleRate;
    }

    float process() {
        float fIndex = phase * tableSize;
        int index = (int)fIndex;
        float alpha = fIndex - index;

        // Linear interpolation
        float output = table[index] + alpha * (table[index + 1] - table[index]);

        phase += phaseInc;
        while (phase >= 1.0f) phase -= 1.0f;
        while (phase < 0.0f)  phase += 1.0f;  // FM support
        return output;
    }

    float processCubic() {
        float fIndex = phase * tableSize;
        int index = (int)fIndex;
        float alpha = fIndex - index;

        // Hermite interpolation (Laurent de Soras)
        float xm1 = table[(index - 1 + tableSize) % tableSize];
        float x0  = table[index];
        float x1  = table[(index + 1) % tableSize];
        float x2  = table[(index + 2) % tableSize];

        float c  = (x1 - xm1) * 0.5f;
        float v  = x0 - x1;
        float w  = c + v;
        float a  = w + v + (x2 - x0) * 0.5f;
        float bn = w + a;
        float output = ((((a * alpha) - bn) * alpha + c) * alpha + x0);

        phase += phaseInc;
        while (phase >= 1.0f) phase -= 1.0f;
        while (phase < 0.0f)  phase += 1.0f;
        return output;
    }
};
```

---

## Bandlimited Waveform Synthesis

### Additive Wavetable Builder with Mip-Mapping

```cpp
void buildBandlimitedSaw(float* table, int tableSize, float fundamentalHz,
                         float sampleRate) {
    float omega = fundamentalHz / sampleRate;
    int maxHarmonic = (int)(0.5f / omega);  // Nyquist limit

    for (int i = 0; i < tableSize; i++) {
        float phase = 2.0f * M_PI * i / tableSize;
        float sample = 0.0f;
        for (int h = 1; h <= maxHarmonic; h++) {
            float amp = 1.0f / h;  // sawtooth: 1/n
            sample += amp * sinf(h * phase);
        }
        table[i] = sample;
    }
}
// For square wave: use h += 2 (odd harmonics only)
// Mip-map: generate tables at halved sizes (1024 -> 512 -> 256 -> ...)
```

### Sinc-Train Bandlimited Sawtooth

```cpp
class BandlimitedSaw {
    float phase = 0, pmax, dc, leak;
    float saw = 0;
public:
    void setFrequency(float freq, float sampleRate) {
        pmax = 0.5f * sampleRate / freq;
        dc = -0.498f / pmax;
        leak = 0.998f;
    }
    float process(float sampleRate, float freq) {
        phase += freq / sampleRate;
        if (phase >= pmax) phase -= pmax;

        float p = phase;
        float sinc = (p == 0) ? 1.0f : sinf(M_PI * p) / (M_PI * p);
        saw = leak * saw + dc + sinc;
        return saw;
    }
};
```

### Bandlimited PWM (Tomisawa Method)

Anti-aliased pulse wave via self-phase-modulated sine waves.

```cpp
class BandlimitedPWM {
    float phi = 0, Y0 = 0, Y1 = 0;
    float B, PW;  // B = feedback (bandwidth), PW = pulse width (0..2pi)
public:
    void setFrequency(float freq, float sampleRate) {
        B = 2.3f * (1.0f - 0.0001f * freq);  // limit feedback at high freq
    }
    float process(float freq, float sampleRate) {
        float dphi = 2.0f * M_PI * freq / sampleRate;
        phi += dphi;

        float out0 = cosf(phi + B * Y0);
        Y0 = 0.5f * (out0 + Y0);  // anti-"hunting" filter

        float out1 = cosf(phi + B * Y1 + PW);
        Y1 = 0.5f * (out1 + Y1);

        return out0 - out1;
    }
};
```

---

## Discrete Summation Formula (DSF)

Moorer's closed-form formula for generating harmonic-rich spectra without aliasing.

```cpp
// DSF: sum(k=0..N-1)(a^k * sin(beta + k*theta))
double DSF(double theta, double a, double N, double fi) {
    double s4 = 1.0 - 2.0 * a * cos(theta) + a * a;
    if (s4 == 0.0) return 0.0;
    return (sin(fi)
          - a * sin(theta + fi)
          - pow(a, N) * sin(N * theta + fi)
          + pow(a, N - 1) * sin((N - 1) * theta + fi))
         / s4;
}
// Bandlimit: maxN = 1 + floor(bandlimitHz / fundamentalHz)
// For BLIT: N = maxN, a = atten_at_Nyquist^(1/maxN), beta = pi/2
```

---

## Phase Modulation vs Frequency Modulation

PM is preferred over FM for synthesis because:
1. DC in FM causes pitch shift with cascaded modulation; PM only causes phase shift
2. PM modulation index = amplitude in radians, independent of modulator frequency

```cpp
struct Oscillator {
    double freq;
    double phase;
    double wavetable[512];

    double process(double fm, double pm, double am) {
        phase += freq + fm;  // FM: added to frequency
        return wavetable[((int)(phase + pm)) & 511] * am;  // PM: added to phase
    }
};
```

---

## Noise Generation

### Gaussian White Noise (Box-Muller)

```cpp
class GaussianNoise {
    bool hasSpare = false;
    float spare;
public:
    float generate() {
        if (hasSpare) {
            hasSpare = false;
            return spare;
        }
        float s, u, v;
        do {
            u = 2.0f * rand() / (float)RAND_MAX - 1.0f;
            v = 2.0f * rand() / (float)RAND_MAX - 1.0f;
            s = u * u + v * v;
        } while (s >= 1.0f || s == 0.0f);

        s = sqrtf(-2.0f * logf(s) / s);
        spare = v * s;
        hasSpare = true;
        return u * s;
    }
};
```

### Fast White Noise (XOR Shift)

SID-style shift register. Very fast with long period.

```cpp
class FastWhiteNoise {
    unsigned int x1 = 0x67452301;
    unsigned int x2 = 0xEFCDAB89;
public:
    float generate() {
        x1 ^= x2;
        float output = (float)(int)x2 * (1.0f / (float)0x7FFFFFFF);
        x2 += x1;
        return output;
    }
};
```

### Pink Noise (Auto-Correlated Generator)

16-bit fixed-point, 5-stage generator. Accurate to +/-0.25 dB over 9 octaves.

```cpp
class PinkNoise {
    int32_t accum = 0;
    int16_t contrib[5] = {};
    static constexpr int16_t pA[5] = {14055, 7457, 3848, 1936, 954};
    static constexpr int16_t pPSUM[5] = {10343, 6506, 3281, 1617, 795};
public:
    int16_t generate() {
        // Random selection of which stage to update
        int32_t rnd = rand();
        for (int i = 0; i < 5; i++) {
            if (rnd < pPSUM[i] * (RAND_MAX / 11898)) {
                accum -= contrib[i];
                int32_t r = rand();
                contrib[i] = (int16_t)((r >> 16) * pA[i] >> 16);
                accum += contrib[i];
                break;
            }
        }
        return accum >> 16;
    }
};
```

---

## Envelope Generation

### Fast Exponential Envelope

~100x faster than `exp()` per sample. IIR-based with negligible drift.

```cpp
class ExponentialEnvelope {
    float currentLevel;
    float coeff;
public:
    void init(float startLevel, float endLevel, float timeMs, float sampleRate) {
        currentLevel = startLevel;
        coeff = 1.0f + (logf(endLevel) - logf(startLevel)) / (timeMs * 0.001f * sampleRate);
    }
    float process() {
        currentLevel *= coeff;
        return currentLevel;
    }
};
```

### Quadratic Envelope (Forward Differencing)

No multiplications needed after initialization.

```cpp
class QuadraticEnvelope {
    float bigr, bigs, bigt;
public:
    void init(float startLevel, float midLevel, float endLevel, int numSamples) {
        bigt = (startLevel - 2.0f * midLevel + endLevel)
             / ((float)numSamples * numSamples);
        bigs = bigr = (endLevel - startLevel) / (float)numSamples - bigt * numSamples;
        bigr = startLevel;
    }
    float process() {
        float out = bigr;
        bigr += bigs;
        bigs += bigt;
        return out;
    }
};
```

---

## Chebyshev Waveshaping

Recursive Chebyshev polynomial for generating specific harmonics from a sinusoidal input. Input amplitude must be exactly 1.0.

```cpp
// T_n(x) = 2*x*T_{n-1}(x) - T_{n-2}(x)
// T_0(x) = 1, T_1(x) = x

float chebyshevWaveshaper(float x, const float* harmonicGains, int maxHarmonic) {
    float Tnm2 = 1.0f;          // T_0
    float Tnm1 = x;             // T_1
    float output = harmonicGains[0] * Tnm2 + harmonicGains[1] * Tnm1;

    for (int n = 2; n <= maxHarmonic; n++) {
        float Tn = 2.0f * x * Tnm1 - Tnm2;
        output += harmonicGains[n] * Tn;
        Tnm2 = Tnm1;
        Tnm1 = Tn;
    }
    return output;
}
```

---

## MinBLEP Table Generation

Minimum-phase bandlimited step function. Inserted at waveform discontinuities for alias-free hard-sync and waveform transitions.

Pipeline: sinc table -> Blackman window -> FFT -> minimum-phase spectrum (cepstral method) -> IFFT -> integrate -> normalize.

```cpp
// In MATLAB/Octave:
// 1. Generate windowed sinc
// 2. FFT to get spectrum
// 3. Compute minimum-phase via cepstral method:
//    min_phase = exp(fft(fold(ifft(log(spectrum)))))
// 4. IFFT back to time domain
// 5. Integrate (cumsum) and normalize

// The resulting table is applied at each waveform discontinuity
// by adding it to the output stream to correct aliasing.
```

---

## Formant / Vocal Synthesis

AM-based formant synthesis without filters. Uses double carrier crossfading between harmonics.

```cpp
// Double AM carrier crossfades between integer harmonics
float formantCarrier(float phase, float harmonicFraction) {
    int h0 = (int)phase;
    float hf = phase - h0;
    float Porteuse0 = sinf(2.0f * M_PI * h0);  // carrier at h0
    float Porteuse1 = sinf(2.0f * M_PI * (h0 + 1));  // carrier at h0+1
    return Porteuse0 + hf * (Porteuse1 - Porteuse0);
}
// Formant shape via Gaussian + Hann weighting on carrier
// -3dB/oct spectral envelope: scale amplitude by f0/fn
```

---

## Granular Time Stretching

Overlap-add with independent analysis and synthesis hop sizes.

```cpp
void timeStretch(const float* input, float* output, int length,
                 int analysisHop, int synthesisHop) {
    int grainSize = analysisHop * 2;  // grain = 2x hop
    int outPos = 0;

    for (int inPos = 0; inPos + grainSize < length; inPos += analysisHop) {
        // Window and copy grain
        for (int i = 0; i < grainSize; i++) {
            float window = 0.5f * (1.0f - cosf(2.0f * M_PI * i / grainSize));
            output[outPos + i] += input[inPos + i] * window;
        }
        outPos += synthesisHop;
    }
}
```

---

## LFO and Chaotic Generators

### Smooth Random LFO

Sinusoidal oscillator with randomly varying frequency and amplitude.

```cpp
class SmoothRandomLFO {
    float phase = 0, freq = 0, targetFreq;
    float amp = 1.0f, targetAmp = 1.0f;
    float rate;  // average frequency
public:
    SmoothRandomLFO(float avgFreq) : rate(avgFreq) {}
    float process(float sampleRate) {
        phase += freq / sampleRate;
        if (phase >= 1.0f) {
            phase -= 1.0f;
            targetFreq = rate * (0.5f + (float)rand() / RAND_MAX);
            targetAmp = 0.5f + 0.5f * (float)rand() / RAND_MAX;
        }
        freq += 0.001f * (targetFreq - freq);
        amp += 0.001f * (targetAmp - amp);
        return amp * sinf(2.0f * M_PI * phase);
    }
};
```

### Chaotic Oscillators (Rossler / Lorenz)

For analog-drift simulation. Lorenz is unpitched (pink-noise-like); Rossler has spectral peaks.

```cpp
struct RosslerOscillator {
    float x = 0.1f, y = 0, z = 0;
    float a = 0.2f, b = 0.2f, c = 5.7f, dt = 0.01f;

    float process() {
        float dx = -y - z;
        float dy = x + a * y;
        float dz = b + z * (x - c);
        x += dt * dx;
        y += dt * dy;
        z += dt * dz;
        return x;  // or y, z for different characteristics
    }
};
```
