# Faust DSP Patterns

A cookbook of common audio DSP algorithms implemented in Faust. These patterns use the standard libraries (`import("stdfaust.lib")`).

## Table of Contents

- [Oscillators](#oscillators)
- [Filters](#filters)
- [Delay Effects](#delay-effects)
- [Dynamics](#dynamics)
- [Modulation Effects](#modulation-effects)
- [Distortion](#distortion)
- [Reverb](#reverb)
- [Synthesis Techniques](#synthesis-techniques)
- [Envelope Generators](#envelope-generators)
- [Analysis](#analysis)
- [Signal Routing](#signal-routing)

## Oscillators

### Sine Wave
```faust
import("stdfaust.lib");
freq = hslider("freq", 440, 20, 20000, 0.1);
process = os.osc(freq);
```

### Sawtooth (Bandlimited)
```faust
freq = hslider("freq", 220, 20, 20000, 0.1);
process = os.sawtooth(freq);
```

### Square Wave (Bandlimited)
```faust
freq = hslider("freq", 220, 20, 20000, 0.1);
process = os.square(freq);
```

### Triangle Wave (Bandlimited)
```faust
freq = hslider("freq", 220, 20, 20000, 0.1);
process = os.triangle(freq);
```

### Pulse Wave (Variable Width)
```faust
freq = hslider("freq", 220, 20, 20000, 0.1);
width = hslider("width", 0.5, 0.01, 0.99, 0.01);
process = os.pulsetrain(freq, width);
```

### Wavetable Oscillator
```faust
import("stdfaust.lib");
freq = hslider("freq", 440, 20, 20000, 0.1);
// Using waveform primitive
process = os.osc(freq);  // library already uses wavetable internally

// Custom wavetable
size = 1024;
table = waveform{0, 0.5, 1, 0.5, 0, -0.5, -1, -0.5};  // crude saw
phasor = os.phasor(size, freq);
process = rdtable(size, table, int(phasor));
```

### Noise Generators
```faust
// White noise
process = no.noise;

// Pink noise (1/f)
process = no.pinknoise;

// Pseudo-random at compile time
random = +(12345) ~ *(1103515245);
process = random : /(2147483647.0) : *(2) : -(1);
```

## Filters

### One-Pole Lowpass
```faust
a = hslider("alpha", 0.01, 0.001, 1, 0.001);
process = _ : + ~ *(1-a) : *(a);
```

### Resonant Lowpass (Library)
```faust
freq = si.smoo(hslider("freq", 1000, 20, 20000, 1));
q = si.smoo(hslider("q", 1, 0.1, 100, 0.1));
gain = si.smoo(hslider("gain", 1, 0, 10, 0.01));
process = _ : fi.resonlp(freq, q, gain);
```

### Resonant Highpass
```faust
freq = si.smoo(hslider("freq", 1000, 20, 20000, 1));
q = si.smoo(hslider("q", 1, 0.1, 100, 0.1));
process = _ : fi.resonhp(freq, q, 1);
```

### Resonant Bandpass
```faust
freq = si.smoo(hslider("freq", 1000, 20, 20000, 1));
q = si.smoo(hslider("q", 1, 0.1, 100, 0.1));
process = _ : fi.resonbp(freq, q, 1);
```

### State Variable Filter (SVF)
```faust
// Using library SVF with LP, HP, BP, notch outputs
freq = si.smoo(hslider("freq", 1000, 20, 20000, 1));
q = si.smoo(hslider("q", 1, 0.1, 100, 0.1));
lp, hp, bp, br = fi.svf1(freq, q, _);
process = lp;  // use hp, bp, or br for other outputs
```

### Moog Ladder Filter
```faust
freq = si.smoo(hslider("freq", 1000, 20, 20000, 1));
q = si.smoo(hslider("q", 1, 0.1, 10, 0.1));
process = _ : fi.moogLadder(freq, q);
```

### Parametric EQ (Peak)
```faust
import("stdfaust.lib");
freq = si.smoo(hslider("freq", 1000, 20, 20000, 1));
q = si.smoo(hslider("q", 1, 0.1, 100, 0.1));
gain = si.smoo(hslider("gain", 0, -20, 20, 0.1));
process = _ : fi.peak_eq(freq, q, gain);
```

### Multi-Band Peak EQ (Iterated)
```faust
import("stdfaust.lib");
N = 4;
process = seq(i, N,
    fi.peak_eq(
        hslider("Freq%i", 1000 * (i+1), 20, 20000, 1),
        hslider("Q%i", 1, 0.1, 100, 0.1),
        hslider("Gain%i [unit:dB]", 0, -20, 20, 0.1)
    )
);
```

## Delay Effects

### Simple Delay
```faust
import("stdfaust.lib");
delayTime = hslider("delay[unit:ms]", 250, 1, 2000, 0.1);
del = delayTime * ma.SR / 1000;  // ms to samples
process = _ <: _, @(int(del)) :> _;
```

### Delay with Feedback
```faust
import("stdfaust.lib");
delayTime = hslider("delay[unit:ms]", 250, 1, 2000, 0.1);
feedback = hslider("feedback", 0.5, 0, 0.99, 0.01);
del = delayTime * ma.SR / 1000;

process = _ <: dry, wet
    with {
        dry = _;
        wet = (+ : @(int(del))) ~ *(feedback);
    };
```

### Stereo Ping-Pong Delay
```faust
import("stdfaust.lib");
delayTime = hslider("delay[unit:ms]", 375, 1, 2000, 0.1);
feedback = hslider("feedback", 0.5, 0, 0.99, 0.01);
del = delayTime * ma.SR / 1000;

wet = (+ : @(int(del))) ~ *(feedback);
process = _ <: _, wet <: (_+_, _+_);
```

### Comb Filter
```faust
import("stdfaust.lib");
delayTime = hslider("delay[unit:ms]", 10, 0.1, 100, 0.01);
feedback = hslider("feedback", 0.7, 0, 0.99, 0.01);
del = delayTime * ma.SR / 1000;

// Feedforward comb
ff_comb = _ + @(int(del)) * feedback;

// Feedback comb
fb_comb = (+ : @(int(del))) ~ *(feedback);

process = _ : fb_comb;
```

## Dynamics

### Simple Compressor
```faust
import("stdfaust.lib");
threshold = hslider("threshold[unit:dB]", -20, -60, 0, 0.1);
ratio = hslider("ratio", 4, 1, 20, 0.1);
attack = hslider("attack[unit:ms]", 10, 0.1, 100, 0.1);
release = hslider("release[unit:ms]", 100, 1, 1000, 0.1);

process = co.compressor(threshold, ratio, attack, release, _);
```

### Simple Limiter
```faust
import("stdfaust.lib");
process = co.limiter_1176(_, _);
```

### Gate/Expander
```faust
import("stdfaust.lib");
threshold = hslider("threshold", 0.1, 0, 1, 0.01);
process = co.gate(threshold, _, _);
```

## Modulation Effects

### Chorus
```faust
import("stdfaust.lib");
rate = hslider("rate[unit:Hz]", 0.5, 0.1, 5, 0.01);
depth = hslider("depth[unit:ms]", 5, 0.1, 20, 0.1);
process = ve.chorus(rate, depth, 0.5, _);
```

### Flanger
```faust
import("stdfaust.lib");
rate = hslider("rate[unit:Hz]", 0.3, 0.05, 5, 0.01);
depth = hslider("depth", 0.003, 0.001, 0.01, 0.001);
feedback = hslider("feedback", 0.6, 0, 0.99, 0.01);
process = ve.flangerStereo(rate, depth, feedback, _, _);
```

### Phaser
```faust
import("stdfaust.lib");
rate = hslider("rate[unit:Hz]", 0.5, 0.1, 5, 0.01);
depth = hslider("depth", 1, 0, 5, 0.01);
process = pf.phaser2(6, rate, depth, _, _);
```

### Tremolo
```faust
import("stdfaust.lib");
rate = hslider("rate[unit:Hz]", 5, 0.1, 20, 0.1);
depth = hslider("depth", 0.5, 0, 1, 0.01);
process = _ * (1 - depth * (1 - os.osc(rate)));
```

### Vibrato
```faust
import("stdfaust.lib");
rate = hslider("rate[unit:Hz]", 5, 0.1, 20, 0.1);
depth = hslider("depth[unit:ms]", 3, 0.1, 10, 0.1);
process = _ : de.fdelay(ma.SR, depth * ma.SR / 1000 * (1 + os.osc(rate)));
```

## Distortion

### Soft Clipping (tanh)
```faust
drive = hslider("drive", 1, 0.1, 10, 0.01);
process = _ : *(drive) : tanh : /(drive);
```

### Hard Clipping
```faust
drive = hslider("drive", 1, 0.1, 10, 0.01);
clip(x) = max(-1, min(1, x));
process = _ : *(drive) : clip : /(drive);
```

### Bit Crusher
```faust
import("stdfaust.lib");
bits = hslider("bits", 8, 1, 16, 1);
process = _ : qu.bitbuster(bits);
```

### Waveshaper
```faust
drive = hslider("drive", 1, 0.1, 10, 0.01);
// Polynomial approximation of tanh
process = _ : *(drive) : *(1.5) : *(1 - abs : *(0.5)) : /(drive);
```

## Reverb

### Zita Reverb (High Quality)
```faust
import("stdfaust.lib");
// Stereo in, stereo out - ready-made with UI
process = dm.zita_light;
```

### Freeverb
```faust
import("stdfaust.lib");
process = dm.freeverb_demo;
```

### Simple Schroeder Reverb (from scratch)
```faust
import("stdfaust.lib");
del1 = 2999; del2 = 2357; del3 = 1933; del4 = 1553;
fb = 0.7;

comb(n) = (+ : @(n)) ~ *(fb);
allpass(n) = (+ : -(@(n) : *(0.5))) ~ *(0.5);

process = _ <: comb(del1), comb(del2), comb(del3), comb(del4)
          :> allpass(191) : allpass(293) : _;
```

## Synthesis Techniques

### Additive Synthesis
```faust
import("stdfaust.lib");
N = 8;  // number of harmonics
baseFreq = hslider("freq", 220, 20, 2000, 0.1);
process = sum(i, N,
    os.osc(baseFreq * (i + 1)) * hslider("Harm%i", 1.0/(i+1), 0, 1, 0.001)
) / N;
```

### FM Synthesis
```faust
import("stdfaust.lib");
carrier = hslider("carrier", 220, 20, 2000, 0.1);
modRatio = hslider("modRatio", 2, 0.1, 10, 0.01);
index = hslider("index", 100, 0, 1000, 1);
process = os.osc(carrier + os.osc(carrier * modRatio) * index);
```

### Karplus-Strong (Plucked String)
```faust
import("stdfaust.lib");
freq = hslider("freq", 220, 20, 2000, 0.1);
damping = hslider("damping", 0.99, 0.9, 1.0, 0.001);
delayLength = ma.SR / freq;

process = no.noise * ba.impulse(0.999) : (+ ~ ( @(int(delayLength)) : *(damping) ));
```

### Subtractive Synthesis
```faust
import("stdfaust.lib");
freq = si.smoo(hslider("freq", 220, 20, 2000, 0.1));
cutoff = si.smoo(hslider("cutoff", 2000, 20, 20000, 1));
q = si.smoo(hslider("q", 5, 0.1, 30, 0.1));
process = os.sawtooth(freq) : fi.resonlp(cutoff, q, 1);
```

### Physical Modeling (String)
```faust
import("stdfaust.lib");
// Using the pm library for physical models
freq = hslider("freq", 220, 20, 2000, 0.1);
pluck = button("pluck");
process = pm.fireString(freq, pluck);
```

## Envelope Generators

### AR Envelope
```faust
import("stdfaust.lib");
attack = hslider("attack[unit:ms]", 10, 1, 1000, 1);
release = hslider("release[unit:ms]", 100, 1, 2000, 1);
gate = button("gate");
process = en.ar(attack, release, gate);
```

### ADSR Envelope
```faust
import("stdfaust.lib");
attack = hslider("attack[unit:ms]", 10, 1, 1000, 1);
decay = hslider("decay[unit:ms]", 100, 1, 1000, 1);
sustain = hslider("sustain", 0.5, 0, 1, 0.01);
release = hslider("release[unit:ms]", 200, 1, 2000, 1);
gate = button("gate");
process = en.adsr(attack, decay, sustain, release, gate);
```

### Exponential Smoothing
```faust
import("stdfaust.lib");
// Smooth any signal with exponential decay
smooth = _ : si.smoo;
process = hslider("param", 440, 20, 20000, 1) : si.smoo;
```

## Analysis

### Level Meter (RMS)
```faust
import("stdfaust.lib");
process = _ : an.meter(_)
    : vbargraph("Level[unit:dB]", -60, 0) : attach;
```

### Simple VU Meter
```faust
process = _ <: _, (_ : abs : si.smoo : vbargraph("VU", 0, 1));
```

### Zero Crossing Counter
```faust
import("stdfaust.lib");
process = _ : ba.zeroCrossing;
```

## Signal Routing

### Crossfade
```faust
xfade = hslider("mix", 0.5, 0, 1, 0.01);
process(x, y) = x * (1 - xfade) + y * xfade;
```

### Stereo Width
```faust
import("stdfaust.lib");
width = hslider("width", 1, 0, 2, 0.01);
process = ef.stereoWidth(width, _, _);
```

### Mid/Side Encoding
```faust
// L,R -> Mid,Side
mid = _,_ :> _;
side = _,-(_ : *(2)) :> _;
process = mid, side;
```

### Mid/Side Decoding
```faust
// Mid,Side -> L,R
L = _ + _ : /(2);
R = _ - _ : /(2);
process(x, y) = x+y, x-y;
```

### N-Channel Bus
```faust
import("stdfaust.lib");
N = 4;
process = si.bus(N);  // creates N identity wires
```

### Signal Reversal
```faust
import("stdfaust.lib");
reverse(expr) = expr <: par(i, n, ba.selector(n-i-1, n))
    with { n = outputs(expr); };
```
