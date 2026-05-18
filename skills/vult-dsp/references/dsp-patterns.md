# Vult DSP Patterns

Ready-made DSP building blocks for common audio processing tasks. All patterns use Vult's `mem` variables for state management and follow the official example conventions.

## Table of Contents

- [Signal Conventions](#signal-conventions)
- [Utility Functions](#utility-functions)
- [Filters](#filters)
- [Oscillators](#oscillators)
- [Envelopes](#envelopes)
- [Effects](#effects)
- [Oversampling Patterns](#oversampling-patterns)
- [Pitch and Frequency Conversion](#pitch-and-frequency-conversion)

## Signal Conventions

The Vult example modules follow these conventions (Eurorack divided by 10):

| Signal | Range | CV mapping |
|--------|-------|------------|
| Pitch | 0.0–1.0 | 0.1 per octave, 0.0 = C0 |
| Audio | -1.0 to 1.0 | Bipolar |
| Envelope | 0.0 to 1.0 | Unipolar |
| Gate | 0.0 or 1.0 | Boolean-like |

## Utility Functions

These small utilities appear throughout the Vult examples and are fundamental building blocks.

### Edge detection (rising edge of a gate)

```
fun edge(x : bool) : bool {
    mem pre;
    val ret = x && not(pre);
    pre = x;
    return ret;
}
```

### Change detection (value differs from previous sample)

```
fun change(x : real) : bool {
    mem pre_x;
    val v : bool = pre_x <> x;
    pre_x = x;
    return v;
}
```

Use `change()` to trigger coefficient recalculation only when parameters actually change, avoiding per-sample expense.

### Smooth (one-pole lowpass for parameter smoothing)

```
fun smooth(input) {
    mem x;
    x = x + (input - x) * 0.005;
    return x;
}
```

Adjust the coefficient (`0.005`) for faster/slower smoothing.

### DC blocker

```
fun dcblock(x0) {
    mem x1, y1;
    val y0 = x0 - x1 + y1 * 0.995;
    x1, y1 = x0, y0;
    return y0;
}
```

### Map (linear interpolation between ranges)

```
fun map(x : real, x0, x1, y0, y1) : real {
    return (x - x0) * (y1 - y0) / (x1 - x0) + y0;
}
```

### Clip (branchless-friendly saturation)

```
fun clip(x, lo, hi) {
    return if x < lo then lo else if x > hi then hi else x;
}
```

### Cubic clipper (smooth saturation for filter feedback)

```
fun cubic_clipper(x) {
    if(x <= -2.0 / 3.0)
        return -2.0 / 3.0;
    else if(x >= 2.0 / 3.0)
        return 2.0 / 3.0;
    else
        return x - (x * x * x) / 3.0;
}
```

This is used in the diode ladder filter to model the nonlinear behavior of analog diode clippers.

### Moving average (2-sample)

```
fun average2(x1 : real) : real {
    mem x0;
    val result = (x0 + x1) / 2.0;
    x0 = x1;
    return result;
}
```

## Filters

### Biquad filter (Direct Form 2)

The biquad is the workhorse of digital filtering. `mem` variables `w1` and `w2` act as single-sample delays (z^-1):

```
fun biquad(x, b0, b1, b2, a1, a2) {
    mem w1, w2;
    val w0 = x - a1 * w1 - a2 * w2;
    val y0 = b0 * w0 + b1 * w1 + b2 * w2;
    w2 = w1;
    w1 = w0;
    return y0;
}
```

### Lowpass filter (Audio EQ Cookbook coefficients)

Efficient version that only recalculates coefficients when `fc` or `q` changes:

```
fun lowpass(x, fc, q) {
    mem w1, w2;
    mem b0, b1, b2, a1, a2;

    if change(fc) || change(q) {
        val w0 = 2.0 * 3.14159 * fc;
        val alpha = sin(w0) / (2.0 * q);
        val cos_w0 = cos(w0);
        val a0 = 1.0 + alpha;
        b0 = (1.0 - cos_w0) / 2.0 / a0;
        b1 = (1.0 - cos_w0) / a0;
        b2 = (1.0 - cos_w0) / 2.0 / a0;
        a1 = -2.0 * cos_w0 / a0;
        a2 = (1.0 - alpha) / a0;
    }

    val w0 = x - a1 * w1 - a2 * w2;
    val y0 = b0 * w0 + b1 * w1 + b2 * w2;
    w2 = w1;
    w1 = w0;
    return y0;
}
```

### State Variable Filter (SVF)

Topologically significant zero-delay feedback filter with LP, HP, BP, and notch outputs:

```
fun svf_calc_g(cv) @[table(size=128, min=0.0, max=0.9)] {
    val pitch = cvToPitch(cv);
    val f = 8.175798915643707 * exp(0.057762265046662105 * pitch);
    val pi_val = 3.141592653589793;
    val wd = 2.0 * pi_val * f;
    val T = 1.0 / 44100.0;
    val wa = (2.0 / T) * tan(wd * T / 2.0);
    val g = wa * T / 2.0;
    return g;
}

fun svf(x, cv, q, sel) {
    mem z1, z2;
    mem g, inv_den, R;

    val q_adj = q + 0.5;
    if change(cv) || change(q_adj) {
        g = svf_calc_g(cv);
        R = 1.0 / (2.0 * (q_adj + eps()));
        inv_den = 1.0 / (1.0 + 2.0 * R * g + g * g);
    }

    val high = (x - (2.0 * R + g) * z1 - z2) * inv_den;
    val band = g * high + z1;
    val low = g * band + z2;
    val notch = low + high;

    z1 = g * high + band;
    z2 = g * band + low;

    // sel: 0=low, 1=high, 2=band, 3=notch
    val output =
        if sel == 0 then low else
        if sel == 1 then high else
        if sel == 2 then band else
        notch;
    return output;
}
```

### Diode Ladder Filter (Euler method)

A model of the classic diode ladder filter with 4x oversampling:

```
fun ladder_tune(cut) @[table(min=0.0, max=1.0, size=128)] {
    val f = cvTokHz(cut);
    val f_clipped = clip(f, 0.0, 20.0);
    val fh = (2.0 * pi()) * f_clipped / (4.0 * 44.1);
    return fh;
}

fun ladder_euler(input, fh, res) {
    mem p0, p1, p2, p3;

    val w0 = cubic_clipper(input - 4.0 * res * p3);
    val w1 = cubic_clipper(p0);
    val dp0 = (w0 - w1) * fh;
    val w2 = cubic_clipper(p1);
    val dp1 = (w1 - w2) * fh;
    val w3 = cubic_clipper(p2);
    val dp2 = (w2 - w3) * fh;
    val w4 = cubic_clipper(p3);
    val dp3 = (w3 - w4) * fh;

    p0 = p0 + dp0;
    p1 = p1 + dp1;
    p2 = p2 + dp2;
    p3 = p3 + dp3;
    return p3;
}

fun ladder_process(input : real, cut : real, res : real) : real {
    mem fh;
    if change(cut) { fh = ladder_tune(cut); }
    _ = e:ladder_euler(input, fh, res);  // 4x oversampling
    _ = e:ladder_euler(input, fh, res);
    _ = e:ladder_euler(input, fh, res);
    return e:ladder_euler(input, fh, res);
}
```

### Diode Ladder Filter (Heun method — more accurate)

Same structure as Euler but uses predictor-corrector (Heun's method) for better numerical stability:

```
fun ladder_heun(input, fh, res) {
    mem p0, p1, p2, p3;

    // Predictor (Euler step)
    val wt0 = cubic_clipper(input - 4.0 * res * p3);
    val wt1 = cubic_clipper(p0);
    val dpt0 = (wt0 - wt1) * fh;
    val wt2 = cubic_clipper(p1);
    val dpt1 = (wt1 - wt2) * fh;
    val wt3 = cubic_clipper(p2);
    val dpt2 = (wt2 - wt3) * fh;
    val wt4 = cubic_clipper(p3);
    val dpt3 = (wt3 - wt4) * fh;

    val pt0 = p0 + dpt0;
    val pt1 = p1 + dpt1;
    val pt2 = p2 + dpt2;
    val pt3 = p3 + dpt3;

    // Corrector
    val w0 = cubic_clipper(input - 4.0 * res * pt3);
    val w1 = cubic_clipper(pt0);
    val dp0 = (w0 - w1) * fh;
    val w2 = cubic_clipper(pt1);
    val dp1 = (w1 - w2) * fh;
    val w3 = cubic_clipper(pt2);
    val dp2 = (w2 - w3) * fh;
    val w4 = cubic_clipper(pt3);
    val dp3 = (w3 - w4) * fh;

    // Average of predictor and corrector
    p0 = p0 + (dp0 + dpt0) / 2.0;
    p1 = p1 + (dp1 + dpt1) / 2.0;
    p2 = p2 + (dp2 + dpt2) / 2.0;
    p3 = p3 + (dp3 + dpt3) / 2.0;
    return p3;
}
```

## Oscillators

### Phase accumulator oscillator

The fundamental building block for all oscillator shapes:

```
fun phase_accumulator(rate) {
    mem phase;
    phase = phase + rate;
    if phase > 1.0 { phase = phase - 1.0; }
    return phase;
}
```

### Sawtooth oscillator

```
fun saw(cv) {
    mem phase;
    val rate = cvToRate(cv);
    phase = phase + rate;
    if phase > 2.0 { phase = phase - 2.0; }
    return phase - 1.0;
}
```

### Square oscillator

```
fun square(cv) {
    mem phase;
    val rate = cvToRate(cv);
    phase = phase + rate;
    if phase > 2.0 { phase = phase - 2.0; }
    return if phase > 1.0 then 1.0 else -1.0;
}
```

### Triangle oscillator

```
fun triangle(cv) {
    mem phase;
    val rate = cvToRate(cv);
    phase = phase + rate;
    if phase > 2.0 { phase = phase - 2.0; }
    val tmp = phase - 1.0;
    return abs(tmp) * 2.0 - 1.0;
}
```

### Anti-aliased saw (BLIT-based)

For bandlimited oscillators, use a lookup table for the sinc function and integrate BLIT impulses. The `@[table]` tag makes this efficient:

```
fun sinc(x) @[table(size=256, min=-1.0, max=1.0)] {
    val px = 3.14159265 * x;
    return if abs(x) < eps() then 1.0 else sin(px) / px;
}
```

## Envelopes

### ADSR envelope

State-machine ADSR with gate triggering. The `do` function takes direct values; the `process` function uses stored knob values:

```
fun adsr_do(gate : real, a, d, s, r) {
    mem state;
    mem out;
    mem rate;
    mem target;
    mem scale;

    val a_rate = 1.0 / (100.0 * a + 0.01);
    val d_rate = 1.0 / (100.0 * d + 0.01);
    val r_rate = 1.0 / (100.0 * r + 0.01);

    // Smooth approach to target
    out = out + (target - out) * rate * 0.004;

    val bgate = gate > 0.0;

    // State 0: idle / release
    if (state == 0) {
        if edge(bgate) {
            state = 1;
            scale = gate / 5.0;
        }
        rate = r_rate;
        target = 0.0;
    }

    // State 1: attack
    if (state == 1) {
        if not(bgate) { state = 0; }
        if (out > 1024.0) { state = 2; }
        rate = a_rate;
        target = 1.2 * 1024.0;
    }

    // State 2: decay / sustain
    if (state == 2) {
        if not(bgate) { state = 0; }
        rate = d_rate;
        target = s * 1024.0;
    }

    return smooth(scale) * clip(out / 1024.0, 0.0, 1.0);
}
```

The `1024.0` scaling factor improves numeric precision when using fixed-point arithmetic.

### LFO (saw, triangle, square)

Shape-selectable LFO with reset and soft (4-sample average) output:

```
fun lfo_soft(x1) {
    mem x2, x3, x4;
    val o = (x1 + x2 + x3 + x4) / 4.0;
    x2, x3, x4 = x1, x2, x3;
    return o;
}

fun lfo_process(cv, shape, reset) {
    mem rate;
    if change(cv) { rate = cvToRate(cv - 0.3); }

    mem phase;
    phase = phase + rate;
    phase = if phase > 2.0 then phase - 2.0 else phase;

    val breset = reset > 0.0;
    if edge(breset) { phase = 0.0; }

    val tmp = phase - 1.0;
    val o =
        if shape < 1.0 then tmp
        else if shape < 2.0 then (abs(tmp) * 2.0 - 1.0)
        else (if tmp > 0.0 then 1.0 else 0.0);

    return lfo_soft(o);
}
```

## Effects

### Simple delay (fixed buffer)

```
fun simple_delay(input, time_samples) {
    mem buffer : array(real, 44100);   // 1 second at 44.1kHz
    mem write_pos;

    // Read from delay tap
    val read_pos = (write_pos - time_samples + size(buffer)) % size(buffer);
    val output = get(buffer, read_pos);

    // Write input
    _ = set(buffer, write_pos, input);
    write_pos = (write_pos + 1) % size(buffer);

    return output;
}
```

### Feedback delay with mix

```
fun feedback_delay(input, time_samples, feedback, mix) {
    mem buffer : array(real, 44100);
    mem write_pos;

    val read_pos = (write_pos - time_samples + size(buffer)) % size(buffer);
    val delayed = get(buffer, read_pos);

    // Write input + feedback
    _ = set(buffer, write_pos, input + delayed * feedback);
    write_pos = (write_pos + 1) % size(buffer);

    // Wet/dry mix
    return input * (1.0 - mix) + delayed * mix;
}
```

### Saturation (soft clip)

```
fun saturate(x) {
    // Bram de Jong-style soft saturation
    return if abs(x) < 1.0 then x else (x > 0.0 then 1.0 else -1.0) * (1.0 - exp(-abs(x)));
}
```

### Saturate_soft (used in SVF output)

```
fun saturate_soft(x) {
    // Polynomial approximation of tanh
    val a = abs(x);
    val xx = a * a;
    return if a > 3.0 then
        if x > 0.0 then 1.0 else -1.0
    else if a > 1.0 then
        (3.0 - x * 2.0 - 1.0 / (3.0 * a - 6.0)) / 3.0 * (if x > 0.0 then 1.0 else -1.0)
    else
        x * (1.0 + xx * (-0.166666666666666 + xx * 0.008333333333333));
}
```

### Decimator/bitcrusher

```
fun decimate(input, rate_reduction, bits) {
    mem held;
    mem counter;

    counter = counter + 1.0;
    if counter >= rate_reduction {
        counter = 0.0;
        held = input;
    }

    // Bit reduction
    val levels = exp2(real(bits));
    held = floor(held * levels) / levels;
    return held;
}
```

## Oversampling Patterns

### 2x oversampling

Run the same processing function twice per sample using a named context:

```
fun process_2x(input, param) {
    _ = inst:my_filter(input, param);   // first pass
    return inst:my_filter(input, param); // second pass
}
```

### 4x oversampling

```
fun process_4x(input, param) {
    _ = inst:my_filter(input, param);
    _ = inst:my_filter(input, param);
    _ = inst:my_filter(input, param);
    return inst:my_filter(input, param);
}
```

### Stereo with oversampling

Combine named contexts for channels and oversampling:

```
fun stereo_2x(input_l, input_r, param) {
    // Left channel: 2x oversampled
    _ = left:my_filter(input_l, param);
    val out_l = left:my_filter(input_l, param);

    // Right channel: 2x oversampled
    _ = right:my_filter(input_r, param);
    val out_r = right:my_filter(input_r, param);

    return out_l, out_r;
}
```

**Important**: When oversampling, the internal frequency parameters must be scaled. For 2x oversampling, divide frequency by 2. For 4x, divide by 4. This accounts for the doubled/quadrupled effective sample rate.

## Pitch and Frequency Conversion

These conversion functions are used throughout the examples. They convert between Vult's CV convention, MIDI pitch, frequency, and sample rates.

```
fun cvToPitch(cv) {
    return cv * 120.0 + 24.0;
}

fun pitchToCv(pitch) {
    return 1.0 / 120.0 * (-24.0 + pitch);
}

// Rate for phase accumulator (cycles per sample)
fun pitchToRate(pitch) @[table(size=32, min=0.0, max=127.0)] {
    return 0.00018539226566085504 * exp(0.057762265046662105 * pitch);
}

// CV to rate (convenience wrapper)
fun cvToRate(cv) @[table(size=128, min=0.0, max=0.9)] {
    return pitchToRate(cvToPitch(cv));
}

// CV to frequency in kHz
fun cvTokHz(cv) @[table(size=32, min=0.0, max=1.0)] {
    val pitch = cvToPitch(cv);
    val f = 8.175798915643707 * exp(0.057762265046662105 * pitch);
    return f / 1000.0;
}

// CV to period in samples
fun cvToperiod(cv) @[table(size=32, min=0.0, max=1.0)] {
    val pitch = cvToPitch(cv);
    val f = 8.175798915643707 * exp(0.057762265046662105 * pitch);
    return 44100.0 / f / 2.0;
}
```

The exponential `0.057762265046662105` equals `ln(2)/12` — the factor for converting semitones to frequency ratios (equal temperament). The base frequency `8.175798915643707` is C0 (MIDI note 0).

These are wrapped in `@[table]` tags because `exp()` is expensive — the lookup table replaces each call with a few multiplications and additions.
