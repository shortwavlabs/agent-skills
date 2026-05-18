---
name: faust-dsp
description: Write DSP algorithms in the Faust programming language for real-time audio processing and synthesis. Faust (Functional Audio Stream) is a functional, block-diagram language that compiles to optimized C/C++, WebAssembly, LLVM IR, and more — targeting VST/AU plugins, standalone JACK apps, PureData/Max externals, WebAudio, embedded platforms (Teensy, ESP32, Bela), and more. Use this skill whenever the user asks about Faust, faust code, .dsp files, Faust libraries, faust2xx scripts, or any real-time audio DSP that could be expressed as a signal processing block diagram. Also use when the user mentions functional audio programming, compiling DSP to plugins, or cross-platform audio signal processing from a single source.
---

# Faust DSP Development

Faust is a functional programming language designed for real-time audio signal processing. A Faust program describes a block diagram of signal processors using five composition operators, and the compiler generates highly optimized C++ (or C, Rust, WebAssembly, etc.) that runs at sample level.

## Core Workflow

1. **Analyze the requirement** — identify inputs, outputs, parameters (with ranges), and the signal flow
2. **Sketch the block diagram** — think in terms of the five composition operators
3. **Write the `.dsp` file** — import libraries, declare metadata, define `process`
4. **Add UI elements** — sliders, buttons, groups for parameters
5. **Compile and test** — use `faust` CLI, Faust Online IDE, or `faust2xx` scripts

## Language Essentials

Every Faust program must define `process` — the main signal processor (like `main` in C). Programs are lists of statements: metadata, imports, definitions, and comments.

### File Template

```faust
import("stdfaust.lib");

declare name "MyEffect";
declare author "Author Name";
declare version "1.0";

// Parameters with UI
freq = hslider("Frequency", 440, 20, 20000, 1);
gain = hslider("Gain", 0.5, 0, 1, 0.01);

process = no.noise : fi.resonlp(freq, 1, gain);
```

### Five Composition Operators

These are the backbone of Faust. Everything is a block diagram.

| Operator | Syntax | Description |
|----------|--------|-------------|
| Parallel | `A,B` | Place A and B side by side (no connections) |
| Sequential | `A:B` | Connect A's outputs to B's inputs |
| Split | `A<:B` | Distribute A's outputs to B's inputs (outputs must divide inputs evenly) |
| Merge | `A:>B` | Sum A's outputs into B's inputs (outputs must be multiple of inputs) |
| Recursive | `A~B` | Create feedback loop: A's outputs feed back through B with 1-sample delay |

**Priority** (higher = tighter binding): `~` (4) > `,` (3) > `:` (2) > `<:`,`:>` (1). Use parentheses to clarify.

### Iterations

Faust provides compile-time loop constructs for algorithmic diagram construction:

| Iteration | Syntax | Result |
|-----------|--------|--------|
| `par(i,N,x)` | Parallel | N copies of x in parallel |
| `seq(i,N,x)` | Sequential | N copies of x in series |
| `sum(i,N,x)` | Sum | N copies summed together |
| `prod(i,N,x)` | Product | N copies multiplied together |

`i` is the iteration variable (0-indexed), `N` is a compile-time constant.

### Key Primitives

| Primitive | Description |
|-----------|-------------|
| `_` | Identity (wire): passes signal through |
| `!` | Cut: terminates a signal |
| `+(x)` | Add (partial application: adds x to input) |
| `*(x)` | Multiply (partial application: scales input by x) |
| `@(n)` | Integer delay of n samples (n can be dynamic but bounded) |
| `'` | One-sample delay (equivalent to `@(1)`) |
| `mem` | One-sample delay (equivalent to `'`) |
| `select2(s)` | Two-way selector: s=0 picks first, s=1 picks second |
| `select3(s)` | Three-way selector |
| `rdtable(n,s,r)` | Read-only table: size n, content s, read index r |
| `rwtable(n,s,w,_,r)` | Read/write table for loopers etc. |
| `route(A,B,...)` | Custom signal routing: A inputs, B outputs, pairs of connections |
| `waveform{...}` | Fixed waveform as a list of samples |
| `soundfile("label[url:path]",n)` | Load and access external sound files |
| `attach(x,y)` | Force y to be compiled (for side effects like bargraphs) |

### Infix Operators

Standard math/comparison operators work as infix: `+`, `-`, `*`, `/`, `%`, `^`, `<`, `<=`, `==`, `!=`, `>=`, `>`, `&`, `|`, `xor`, `<<`, `>>`. All compare/compute sample-by-sample on two signals.

Built-in math functions: `sin`, `cos`, `tan`, `acos`, `asin`, `atan`, `atan2`, `exp`, `log`, `log10`, `pow`, `sqrt`, `abs`, `min`, `max`, `fmod`, `floor`, `ceil`, `round`, `rint`.

### Pattern Matching

Define functions with multiple cases using pattern matching:

```faust
// Simple pattern matching with parallel composition
count((x,xs)) = 1+count(xs);
count(x) = 1;

// Case expression
swap = case {
  (x:y) => y:x;  // invert sequential
  (x) => x;      // pass through
};
```

### Lexical Environments

```faust
// with: local definitions
myFilter(x) = x : + ~ *(0.99)
    with { cutoff = 0.99; };

// environment: named group of definitions
consts = environment {
    pi = 3.14159;
    e = 2.718;
};

// letrec: mutually recursive difference equations
ar(a,r,g) = v letrec {
    'v = max(0, v + (n<a)/a - (n>=a)/r) * c;
    where c = g<=g';
};
```

### Foreign Functions

Call external C functions directly:

```faust
asinh = ffunction(float asinhf|asinh|asinhl|asinfx(float), <math.h>, "");
SR = min(192000.0, max(1.0, fconstant(int fSamplingFreq, <math.h>)));
```

## Standard Libraries

Import all libraries with `import("stdfaust.lib");` and access via environment prefixes:

| Prefix | Library | Key Contents |
|--------|---------|--------------|
| `sf` | all.lib | All functions from all libraries |
| `ba` | basics.lib | Counters, timers, bypass, MIDI freq conversion |
| `ma` | maths.lib | Constants (SR, PI, etc.), math functions |
| `os` | oscillators.lib | osc, sawtooth, square, triangle, bandlimited oscillators |
| `fi` | filters.lib | resonlp, resonhp, resonbp, peak_eq, butterfly, svf |
| `de` | delays.lib | Delay lines, fractional delay, comb filters |
| `re` | reverbs.lib | zita_light, freeverb, faustplate |
| `en` | envelopes.lib | AR, ADSR, smooth envelope generators |
| `co` | compressors.lib | Compressor, limiter, gate |
| `no` | noises.lib | White/pink noise generators |
| `si` | signals.lib | smoo, bus, polySmooth, block |
| `ef` | misceffects.lib | Autowah, crossover, talkbox |
| `pm` | physmodels.lib | Physical models (strings, brass, wind, etc.) |
| `sy` | synths.lib | Ready-made synth components |
| `dm` | demos.lib | Demo functions with built-in UI |
| `an` | analyzers.lib | Level meters, FFT, zero crossing |
| `sp` | spats.lib | Spatial audio, panning |
| `ro` | routes.lib | Signal routing, crossfading |
| `ve` | vaeffects.lib | Variable delay effects (chorus, flanger, phaser) |
| `pf` | phaflangers.lib | Phase shifter, flanger |
| `it` | interpolators.lib | Interpolation methods |
| `qu` | quantizers.lib | Bit crushing, downsampling |
| `dx` | dx7.lib | DX7 FM synthesis |
| `wd` | wdmodels.lib | Wave digital filter models |
| `ho` | hoa.lib | Higher Order Ambisonics |
| `mi` | mi.lib | Mutable Instruments models |

Read `references/libraries.md` for detailed library function signatures and usage patterns.

## User Interface Primitives

UI elements are signal generators that produce control-rate signals:

```faust
// Continuous controls
freq = hslider("freq", 440, 20, 20000, 0.1);    // horizontal slider
gain = vslider("gain", 0.5, 0, 1, 0.01);         // vertical slider
mode = nentry("mode", 0, 0, 3, 1);               // numerical entry

// Discrete controls
gate = button("gate");                            // button (0 or 1)
on   = checkbox("on");                            // toggle (0 or 1)

// Groups for organization
hgroup("Oscillator", osc_code);                   // horizontal group
vgroup("Filter", filter_code);                    // vertical group
tgroup("Effects", effect_code);                   // tab group

// Meters (pass-through, display value)
level = _ : vbargraph("Level", 0, 1) : _;        // vertical meter
level = _ : hbargraph("Level", 0, 1) : _;        // horizontal meter
```

UI metadata can customize appearance: `[style:knob]`, `[unit:Hz]`, `[scale:log]`, etc.

## MIDI and Polyphony

Enable MIDI with metadata:

```faust
declare options "[midi:on][nvoices:12]";
```

Standard polyphony parameters (use these exact names):

```faust
freq  = hslider("freq", 440, 50, 2000, 0.01);   // pitch from MIDI note
gain  = hslider("gain", 0.5, 0, 1, 0.01);        // velocity
gate  = button("gate");                            // key on/off
```

MIDI CC mapping: `hslider("param[midi:ctrl 7]", ...)`
Pitch wheel: `hslider("bend[midi:pitchwheel]", 0, -2, 2, 0.01)`

Use `effect = ...` for a shared post-processing effect across all polyphonic voices:

```faust
process = os.sawtooth(freq) * gain * gate;
effect = dm.zita_light;
```

## Compilation

### Command-Line Compiler

```bash
# Compile to C++ (default)
faust mydsp.dsp -o mydsp.cpp

# Compile with architecture file
faust -a alsa-gtk.cpp mydsp.dsp -o mydsp.cpp

# Vector code generation (for SIMD optimization)
faust -vec --vec-size 32 mydsp.dsp -o mydsp.cpp

# Parallel code (OpenMP)
faust -omp mydsp.dsp -o mydsp.cpp

# Parallel code (work-stealing scheduler)
faust -sch mydsp.dsp -o mydsp.cpp

# Double precision
faust -double mydsp.dsp -o mydsp.cpp

# Other backends
faust -lang c mydsp.dsp          # C output
faust -lang rust mydsp.dsp       # Rust output
faust -lang wasm mydsp.dsp       # WebAssembly
faust -lang llvm mydsp.dsp       # LLVM IR
```

### faust2xx Scripts

These one-step scripts compile `.dsp` to ready-to-run binaries:

| Script | Target |
|--------|--------|
| `faust2jaqt` | JACK app with Qt GUI |
| `faust2faustvst` | VST2 plugin |
| `faust2au` | Audio Unit plugin |
| `faust2lv2` | LV2 plugin |
| `faust2puredata` | PureData external |
| `faust2max6` | Max/MSP external |
| `faust2supercollider` | SuperCollider external |
| `faust2csound` | Csound opcode |
| `faust2android` | Android app |
| `faust2ios` | iOS app |
| `faust2bela` | Bela board |
| `faust2api` | C/C++ API |
| `faust2svg` | SVG block diagram |
| `faust2pdf` | PDF block diagram |

## Common Patterns

### One-Pole Lowpass Filter
```faust
onePole(x) = x : + ~ *(a)
    with { a = hslider("cutoff", 0.99, 0, 1, 0.001); };
```

### Simple Delay with Feedback
```faust
delay(x) = x <: @(d), feedback
    with {
        d = hslider("delay", 44100, 1, 44100, 1);
        fb = hslider("feedback", 0.5, 0, 0.99, 0.01);
        feedback = (+ ~ @(d)) * fb;
    };
```

### Stereo from Mono
```faust
stereo(fx) = _ <: fx, fx;
```

### Mono from Stereo
```faust
mono(fx) = _,_ :> fx;
```

### Parameter Smoothing
```faust
freq = si.smoo(hslider("freq", 440, 20, 20000, 1));
```

### Additive Synthesis
```faust
process = sum(i, 8, os.osc(baseFreq * (i+1)) * hslider("Gain%i", 0.5, 0, 1, 0.01))
    with { baseFreq = hslider("BaseFreq", 220, 20, 2000, 1); };
```

### FM Synthesis
```faust
process = os.osc(carrierFreq + os.osc(modFreq) * index)
    with {
        carrierFreq = hslider("Carrier", 220, 20, 2000, 1);
        modFreq = hslider("Modulator", 220, 20, 2000, 1);
        index = hslider("Index", 100, 0, 1000, 1);
    };
```

### Karplus-Strong String
```faust
process = burst : (+ ~ (@(del) : *(damp)))
    with {
        del = ma.SR / hslider("freq", 220, 20, 2000, 1);
        damp = hslider("damping", 0.99, 0.9, 1, 0.001);
        burst = no.noise * (1 - ba.impulse(0.999));
    };
```

## DSP Patterns Reference

For detailed DSP algorithm implementations (filters, oscillators, effects, analysis), read `references/dsp-patterns.md`.

For detailed library function signatures, read `references/libraries.md`.

For compilation targets and architecture files, read `references/compilation.md`.

## Tips for Writing Good Faust Code

- **Think in block diagrams first.** Sketch the signal flow before writing code. The five composition operators map directly to visual connections.
- **Use `with` for local definitions.** Keep helper variables scoped to the function that uses them.
- **Smooth UI parameters.** Wrap sliders with `si.smoo()` to prevent clicks from sudden value changes.
- **The compiler optimizes aggressively.** `no.noise : filter <: _,_` and `no.noise <: filter, filter` produce identical code. Write what reads best.
- **Delays must be bounded.** Use UI elements (`hslider`, `nentry`) for dynamic delays — their ranges tell the compiler how much memory to allocate.
- **Use `library()` over `import()` to avoid name conflicts.** `fl = library("filters.lib"); ... fl.lowpass(...)` is safer than `import("filters.lib")`.
- **Pattern matching order matters.** More specific patterns must precede general ones.
- **The `'` (prime) operator is your friend for filters.** `x'` means "x delayed by one sample" — essential for IIR filter structures.

## Source Documentation

- [Faust Documentation](https://faustdoc.grame.fr/) — official manual, syntax reference, compiler guide
- [Faust Libraries](https://faustlibraries.grame.fr/) — complete library function reference
- [Faust GitHub](https://github.com/grame-cncm/faust) — compiler source, examples, architecture files
- [Faust Examples](https://faustdoc.grame.fr/examples/) — categorized examples (ambisonics, reverb, physical modeling, etc.)
- [Faust Wiki](https://github.com/grame-cncm/faust/wiki) — tutorials, platform-specific guides
