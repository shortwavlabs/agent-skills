---
name: vult-dsp
description: Write DSP algorithms in the Vult language for audio plugins, VCV Rack modules, embedded audio, and real-time signal processing. Vult transcompiles to C/C++ with zero-cost abstractions for stateful DSP. Use this skill whenever the user mentions Vult, vultc, Vult DSP code generation, writing audio DSP for VCV Rack plugins with Vult, embedded audio on Teensy/Arduino with Vult, fixed-point audio DSP, or any task involving transcompiling DSP to C/C++. Also use when the user asks about implementing filters, oscillators, envelopes, effects, or synthesizers using the Vult language.
---

# Vult DSP Skill

Vult is a transcompiled language designed specifically for high-performance DSP code. It compiles to plain C/C++ (or JavaScript/Lua) and excels at writing audio effects, synthesizers, and signal processing algorithms that run on anything from VCV Rack plugins to Teensy microcontrollers.

The key insight behind Vult is that DSP code is fundamentally about stateful computations — filters hold previous samples, oscillators track phase, envelopes remember their state. Vult makes this first-class with `mem` variables and implicit function context, eliminating the boilerplate of manually managing structs and state in C++.

## When to use this skill

- Writing audio DSP in Vult (`.vult` files)
- Integrating Vult-generated C/C++ into audio plugins or embedded projects
- Implementing filters, oscillators, envelopes, effects, or synths in Vult
- Targeting VCV Rack, Teensy Audio Library, PureData, WebAudio, or bare-metal platforms
- Generating fixed-point or floating-point C/C++ from Vult
- Understanding Vult's unique context system for stateful DSP

## Workflow

### 1. Design the DSP algorithm

Start by identifying the processing function signature and what state it needs. Read `references/dsp-patterns.md` for ready-made patterns covering common audio DSP building blocks.

Key decisions:
- **Floating-point vs fixed-point**: Use `real` type in code; choose at compile time with `-real fixed`. Fixed-point uses q16.16 format (range ~32767, precision ~0.0000153).
- **Oversampling needs**: If the algorithm has nonlinearities or can become unstable at high frequencies, plan for named contexts to enable oversampling.
- **Parameter update strategy**: Separate per-sample processing from per-block coefficient updates using the `change()` pattern.

### 2. Write the Vult code

Read `references/language-reference.md` for complete syntax. The core patterns:

```
// Passive function (no state, pure computation)
fun add(a, b) { return a + b; }

// Active function (has state via mem variables)
fun filter(x, fc) {
    mem y;                    // state persists across calls
    val alpha = 0.1;          // local variable, reset each call
    y = y + (x - y) * alpha;
    return y;
}
```

**Function context naming** for multiple instances:
```
fun stereo(input_l, input_r, fc) {
    val out_l = left:filter(input_l, fc);   // independent context "left"
    val out_r = right:filter(input_r, fc);  // independent context "right"
    return out_l, out_r;
}
```

**Oversampling** (reuse same context for multiple passes):
```
fun process_2x(input, fc) {
    _ = inst:filter(input, fc);              // first pass
    return inst:filter(input, fc);           // second pass, same state
}
```

**Shared context with `and`** (functions accessing the same state):
```
fun process(x) {
    mem count;
    count = count + 1;
    return count;
}
and reset() {
    count = 0;    // accesses same 'count' mem variable
}
```

### 3. Compile to C/C++

Read `references/code-generation.md` for compilation details and integration patterns.

```bash
# Floating-point C/C++ output
vultc -ccode input.vult -o output

# Fixed-point C/C++ output (for microcontrollers without FPU)
vultc -ccode -real fixed input.vult -o output

# PureData external
vultc -ccode -template pd input.vult -o output

# Teensy Audio Library object
vultc -ccode -template teensy input.vult -o output
```

This generates `output.h`, `output.cpp`, and optionally `output_tables.h`. You must also include `runtime/vultin.h` and `runtime/vultin.cpp` from the Vult source.

### 4. Integrate with target platform

Read `references/code-generation.md` for platform-specific integration patterns covering:
- **VCV Rack**: Use the RackPlayground template pattern with `process()` function
- **Teensy Audio**: Use `-template teensy` for automatic AudioStream integration
- **PureData**: Use `-template pd` for external generation
- **Arduino/Bare metal**: External function stubs for hardware I/O
- **Custom C++**: Direct function calls with context types

## Vult conventions (from the official examples)

When writing Vult modules, follow these signal conventions:

| Signal type | Range | Notes |
|-------------|-------|-------|
| Pitch/CV | 0.0–1.0 = 10 octaves | 0.1 per octave, 0.0 = C0 |
| Audio | -1.0 to 1.0 | Standard bipolar audio |
| Envelopes | 0.0 to 1.0 | Unipolar control |
| Gates | 0.0 or 1.0 | Boolean-like |

These correspond to the Eurorack convention divided by 10.

## Common patterns

### Change detection (recompute coefficients only when parameters change)
```
fun change(x) {
    mem pre_x;
    val v = pre_x <> x;
    pre_x = x;
    return v;
}

// Usage:
fun process(x, cutoff) {
    mem b0, b1, b2, a1, a2;
    if change(cutoff) {
        // recalculate filter coefficients
        val w0 = 2.0 * 3.14159 * cutoff;
        b0 = ...;
    }
    // process with cached coefficients
}
```

### Lookup tables for expensive functions
```
fun expensive(x) @[table(size=128, min=0.0, max=1.0)] {
    return exp(x * x) * tanh(x) / (x * x + 1.0);
}
```

### WAV file embedding
```
external mywave(channel:int, index:int) : real @[wave(channels=1, file="ir.wav")];

fun playback() {
    mem i = (i + 1) % mywave_samples();
    return mywave(0, i);
}
```

## Reference files

- **`references/language-reference.md`** — Complete Vult syntax: types, operators, expressions, statements, mem variables, function context, tags, builtin functions. Read when you need exact syntax details.
- **`references/dsp-patterns.md`** — Ready-made DSP patterns: biquad filter, ladder filter (Euler/Heun), SVF filter, ADSR envelope, LFO, oscillators, delay, saturation, utilities (edge detection, smoothing, pitch conversion). Read when implementing audio algorithms.
- **`references/code-generation.md`** — Compilation, C/C++ output structure, generated function naming, integration patterns for VCV Rack/Teensy/Arduino/PureData/WebAudio, fixed-point specifics, polyphony. Read when integrating Vult output into a project.

## Source documentation

- [Vult Language Reference](https://github.com/vult-dsp/vult/wiki/Language-Reference)
- [Vult Tutorials](https://vult-dsp.github.io/vult/tutorials/)
- [Vult Examples](https://github.com/vult-dsp/vult/tree/master/examples)
- [Vult Compiler (GitHub)](https://github.com/vult-dsp/vult)
- [VCV Rack Playground Template](https://github.com/vult-dsp/RackPlayground)
