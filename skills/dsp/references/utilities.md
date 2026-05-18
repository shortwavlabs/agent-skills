# Utilities

DSP utility functions and optimizations in C/C++. Covers fast math approximations, interpolation, clipping, denormal prevention, dithering, MIDI conversion, parameter mapping, benchmarking, and lock-free communication.

## Table of Contents

1. [Fast Math Approximations](#fast-math-approximations)
2. [Interpolation](#interpolation)
3. [Branchless Clipping](#branchless-clipping)
4. [Denormal Prevention](#denormal-prevention)
5. [Dithering and Noise Shaping](#dithering-and-noise-shaping)
6. [MIDI Note / Frequency Conversion](#midi-note--frequency-conversion)
7. [Exponential Parameter Mapping](#exponential-parameter-mapping)
8. [Fast Float Random Numbers](#fast-float-random-numbers)
9. [IEEE 754 Float Bit Manipulation](#ieee-754-float-bit-manipulation)
10. [Block/Loop Benchmarking](#blockloop-benchmarking)
11. [Lock-Free FIFO](#lock-free-fifo)

---

## Fast Math Approximations

### Fast exp2

Fixed-point 2^(x-1) approximation for x in [0,1]. Max error 0.3%.

```cpp
inline float fastExp2(float x) {
    // For x in [0, 1]
    float y = x * x;
    float a = 1.0f + x * 0.5f;
    float b = 1.0f + y * 0.25f;
    return a * b;
}
```

### Fast log2

IEEE 754 bit manipulation to extract exponent, then use mantissa for refinement.

```cpp
inline float fastLog2(float val) {
    int* const exp_ptr = reinterpret_cast<int*>(&val);
    int x = *exp_ptr;
    const int log_2 = ((x >> 23) & 255) - 128;
    x &= ~(255 << 23);
    x += 127 << 23;
    *exp_ptr = x;
    return (val + log_2);
}
```

### Fast exp() (Taylor / Horner)

```cpp
// 4th-order Taylor, max error 0.36% in [-1,1]
inline float fastExp4(float x) {
    return (24.0f + x * (24.0f + x * (12.0f + x * (4.0f + x)))) * 0.041666666f;
}
// 6th-order for wider range:
inline float fastExp6(float x) {
    return (720 + x*(720 + x*(360 + x*(120 + x*(30 + x*(6 + x)))))) * 0.0013888888f;
}
```

### Fast atan

```cpp
inline float fastAtan(float x) {
    return x / (1.0f + 0.28f * x * x);
}
```

### Fast Power and Root (IEEE 754 Exponent Manipulation)

Rough approximation. Good for parameter curves where precision isn't critical.

```cpp
inline float fastPower(float f, int n) {
    long* lp = (long*)&f;
    long l = *lp;
    l -= 0x3F800000L;
    l <<= (n - 1);
    l += 0x3F800000L;
    *lp = l;
    return f;
}

inline float fastRoot(float f, int n) {
    long* lp = (long*)&f;
    long l = *lp;
    l -= 0x3F800000L;
    l >>= (n - 1);
    l += 0x3F800000L;
    *lp = l;
    return f;
}
```

### Fast Square Root / Cube Root (SSE)

```cpp
// 11-bit precision sqrt (~6 clocks)
inline float fastSqrt11(float x) {
    __m128 reg = _mm_set_ss(x);
    reg = _mm_sqrt_ss(reg);
    float result;
    _mm_store_ss(&result, reg);
    return result;
}

// Fast inverse sqrt (Newton-Raphson refined)
inline float fastInvSqrt(float x) {
    float xhalf = 0.5f * x;
    int i = *(int*)&x;
    i = 0x5f3759df - (i >> 1);  // Quake III constant
    x = *(float*)&i;
    x = x * (1.5f - xhalf * x * x);  // 1 NR iteration
    return x;
}
```

---

## Interpolation

### Linear Interpolation

```cpp
inline float linearInterp(float y0, float y1, float frac) {
    return y0 + frac * (y1 - y0);
}
```

### Cubic Interpolation (4-point)

```cpp
inline float cubicInterp(float xm1, float x0, float x1, float x2, float frac) {
    float a = (3.0f * (x0 - x1) - xm1 + x2) / 2.0f;
    float b = 2.0f * x1 + xm1 - (5.0f * x0 + x2) / 2.0f;
    float c = (x1 - xm1) / 2.0f;
    return (((a * frac) + b) * frac + c) * frac + x0;
}
```

### Hermite Interpolation (Laurent de Soras)

Preferred for audio — best quality/performance ratio.

```cpp
inline float hermiteInterp(float frac, float xm1, float x0, float x1, float x2) {
    float c  = (x1 - xm1) * 0.5f;
    float v  = x0 - x1;
    float w  = c + v;
    float a  = w + v + (x2 - x0) * 0.5f;
    float bn = w + a;
    return ((((a * frac) - bn) * frac + c) * frac + x0);
}
```

### 3rd-Order Spline Interpolation (5-point)

```cpp
inline float spline3Interp(float x, float L1, float L0, float H0, float H1) {
    return L0 + 0.5f * x * (H0 - L1 + x * (H0 + L0 * (-2.0f) + L1
         + x * ((H0 - L0) * 9.0f + (L1 - H1) * 3.0f
         + x * ((L0 - H0) * 15.0f + (H1 - L1) * 5.0f
         + x * ((H0 - L0) * 6.0f + (L1 - H1) * 2.0f)))));
}
```

---

## Branchless Clipping

Eliminates branch prediction penalties in hot loops. Side effect: eliminates denormals and quantizes to 23-bit mantissa precision.

### Clip to [-1, 1]

```cpp
inline float clip(float x, float lo, float hi) {
    float x1 = fabsf(x - lo);
    float x2 = fabsf(x - hi);
    x = x1 + (lo + hi);
    x -= x2;
    x *= 0.5f;
    return x;
}
// For [-1, 1]: clip(x, -1.0f, 1.0f)
```

### Fast Clamp

```cpp
inline float clampf(float x, float lo, float hi) {
    return fmaxf(lo, fminf(x, hi));
}
```

---

## Denormal Prevention

Denormal (subnormal) floating-point numbers near zero cause 10-100x CPU slowdown on x86. Prevent them in any feedback loop.

### Method 1: Tiny Offset

```cpp
static constexpr float kDenormal = 1e-24f;
// Add to state variables each sample:
state += kDenormal;
```

### Method 2: Flush-to-Zero (Compiler Flag)

```cpp
// GCC/Clang: -ffast-math (includes -fno-math-errno, unsafe optimizations)
// Or specifically: -msse -mfpmath=sse -ffast-math
// This sets the DAZ/FTZ bits in the MXCSR register
```

### Method 3: Conditional Zeroing

```cpp
inline float flushDenormal(float x) {
    if (fabsf(x) < 1e-15f) return 0.0f;
    return x;
}
```

---

## Dithering and Noise Shaping

### Highpass Triangular-PDF Dither with 2nd-Order Noise Shaping

Lowers noise floor 11dB below 0.1 Fs.

```cpp
class TriangularDither {
    float s1 = 0, s2 = 0;
    float s = 0.5f;     // 0 for no noise shaping, 0.5 for 2nd-order
    float wi, d, o;
    int w;
public:
    void init(int bits) {
        w = 1 << (bits - 1);  // e.g., 32768 for 16-bit
        wi = 1.0f / w;
        d = wi / (float)RAND_MAX;
        o = wi * 0.5f;
    }
    int process(float input) {
        input += s * (s1 + s1 - s2);           // error feedback
        float tmp = input + o + d * (float)(rand() - rand());  // TPDF dither
        int out = (int)(w * tmp);
        if (tmp < 0.0f) out--;
        s2 = s1;
        s1 = input - wi * (float)out;          // quantization error
        return out;
    }
};
```

### Gaussian Dither (Central Limit Theorem)

```cpp
float gaussianDither(int N = 4) {
    // Average N uniform randoms; N=4 or 5 is generally enough
    float sum = 0;
    for (int i = 0; i < N; i++)
        sum += (float)rand() / RAND_MAX - 0.5f;
    return sum / N;
}
```

---

## MIDI Note / Frequency Conversion

```cpp
// MIDI note number to frequency (Hz)
// A4 = MIDI 69 = 440 Hz
double midiToFreq(int note) {
    return 440.0 * pow(2.0, (double)(note - 69) / 12.0);
}

// Frequency (Hz) to MIDI note number
int freqToMidi(double freq) {
    return (int)round(12.0 * log2(freq / 440.0)) + 69;
}

// Fast version using fast log2:
float fastMidiToFreq(int note) {
    return 440.0f * fastPower(2.0f, note - 69);  // needs integer power
}

// Note name to MIDI (C4 = 60)
int noteNameToMidi(const char* name) {
    // Parse "C4", "A#3", "Bb2", etc.
    // ... string parsing logic
}
```

---

## Exponential Parameter Mapping

Maps a linear parameter (0..1) to an exponential range. Essential for frequency knobs where linear scaling feels wrong.

```cpp
class ExponentialParameter {
    float minVal, maxVal;
    float logMin, logMax;
public:
    void init(float min, float max) {
        minVal = min;
        maxVal = max;
        logMin = logf(min);
        logMax = logf(max);
    }
    float map(float param) {  // param in [0..1]
        float logVal = param * (logMax - logMin) + logMin;
        float result = expf(logVal);
        return fmaxf(minVal, fminf(result, maxVal));
    }
};
// Optimization: use ln/exp instead of log10/pow(10,x)
// Further: ln(x) - ln(y) == ln(x/y) trades expensive ln for cheaper divide
```

---

## Fast Float Random Numbers

```cpp
// Fast float random in [-1, 1]
inline float fastRandomFloat() {
    static unsigned int seed = 12345;
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    return (float)seed * (2.0f / 0x7fffffff) - 1.0f;
}

// Fast float random in [0, 1]
inline float fastRandom01() {
    static unsigned int seed = 12345;
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    return (float)seed / 0x7fffffff;
}
```

---

## IEEE 754 Float Bit Manipulation

### Fast abs, negate, sign

```cpp
inline float fastAbs(float f) {
    int i = (*(int*)&f) & 0x7fffffff;
    return *(float*)&i;
}

inline float fastNeg(float f) {
    int i = (*(int*)&f) ^ 0x80000000;
    return *(float*)&i;
}

inline int fastSign(float f) {
    return 1 + (((*(int*)&f) >> 31) << 1);  // returns 1 or -1
}
```

---

## Block/Loop Benchmarking

Cycle-accurate DSP benchmarking using x86 RDTSC instruction.

```cpp
class BlockBenchmark {
    unsigned int time_low, time_high;
public:
    void start() {
        unsigned int lo, hi;
        __asm__ __volatile__ ("rdtsc" : "=a"(lo), "=d"(hi));
        time_low = lo;
        time_high = hi;
    }
    unsigned int finish(unsigned int numSamples) {
        unsigned int lo, hi;
        __asm__ __volatile__ ("rdtsc" : "=a"(lo), "=d"(hi));
        lo -= time_low;
        hi -= time_high;
        // 64-bit subtraction result in (hi:lo)
        return lo / numSamples;  // cycles per sample
    }
};
// On multiprocessor: SetThreadAffinityMask(GetCurrentThread(), 1) on Windows
// On macOS/Linux: use sched_setaffinity or pin to core
```

---

## Lock-Free FIFO

Single-reader/single-writer circular buffer for passing audio between threads (e.g., audio thread to UI).

```cpp
template<typename T, int SIZE>
class LockFreeFIFO {
    T buffer[SIZE];
    std::atomic<int> readPos{0};
    std::atomic<int> writePos{0};
public:
    bool push(const T& item) {
        int nextWrite = (writePos.load(std::memory_order_relaxed) + 1) % SIZE;
        if (nextWrite == readPos.load(std::memory_order_acquire))
            return false;  // full
        buffer[writePos.load(std::memory_order_relaxed)] = item;
        writePos.store(nextWrite, std::memory_order_release);
        return true;
    }
    bool pop(T& item) {
        if (readPos.load(std::memory_order_relaxed) == writePos.load(std::memory_order_acquire))
            return false;  // empty
        item = buffer[readPos.load(std::memory_order_relaxed)];
        readPos.store((readPos.load(std::memory_order_relaxed) + 1) % SIZE,
                      std::memory_order_release);
        return true;
    }
};
```

Warning: The original musicdsp.org lock-free FIFO was noted as flawed for multi-processor systems. Use `std::atomic` with proper memory ordering (as shown above) or established libraries like `moodycamel::ReaderWriterQueue` for production.
