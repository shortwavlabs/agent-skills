# Vult Code Generation and Integration

How to compile Vult code and integrate the generated C/C++ into real projects.

## Table of Contents

- [Installation](#installation)
- [Command Line Options](#command-line-options)
- [Generated C/C++ Structure](#generated-cc-structure)
- [Calling Generated Code from C++](#calling-generated-code-from-c)
- [Platform Integration Patterns](#platform-integration-patterns)
- [Fixed-Point Arithmetic](#fixed-point-arithmetic)
- [Polyphony](#polyphony)

## Installation

```bash
# Install globally via npm
npm install vult -g

# This provides the 'vultc' command
# Update to latest version with the same command
```

Native binaries are available from the [releases page](https://github.com/vult-dsp/vult/releases) for faster compilation (the npm version uses Node.js and is slower).

## Command Line Options

### Code generation targets

```bash
vultc -ccode input.vult -o output     # C/C++ (default: floating-point)
vultc -ccode -real fixed input.vult   # C/C++ with fixed-point (q16.16)
vultc -jscode input.vult              # JavaScript (WebAudio)
vultc -luacode input.vult             # LuaJIT

# Multiple targets at once
vultc -jscode -ccode input.vult
```

### Templates

```bash
vultc -ccode -template pd input.vult       # PureData external
vultc -ccode -template teensy input.vult   # Teensy Audio Library object
vultc -ccode -template modelica input.vult # Modelica simulation
```

### Other options

| Flag | Description |
|------|-------------|
| `-o prefix` | Output file prefix (also used as module name) |
| `-i directory` | Additional include directory for `.vult` files |
| `-version` | Show compiler version |
| `-check` | Syntax check only (no output) |
| `-eval` | Execute the Vult code directly |
| `-deps` | Print file dependencies (for build systems) |

## Generated C/C++ Structure

Running `vultc -ccode filter.vult -o filter` produces:

- `filter.h` — Type definitions and function declarations
- `filter.cpp` — Function implementations
- `filter_tables.h` — Lookup table data (if `@[table]` tags are used)

You must also include from the Vult runtime:
- `runtime/vultin.h`
- `runtime/vultin.cpp`

### Generated function naming

For a Vult file `Filter.vult` containing a function `lowpass`, Vult generates:

```
Filter_lowpass_type       // Context struct type
Filter_lowpass_init       // Initialization function
Filter_lowpass            // Processing function
```

Functions without memory (`mem` variables) generate only the function itself — no type or init.

### Return value handling

**Single return value** — function returns the value directly:
```cpp
float Filter_lowpass(Filter_lowpass_type &_ctx, float x);
```

**Multiple return values** — values are stored in the context struct and accessed via `_ret_N` functions:
```cpp
void Example_foo2(Example_foo2_type &_ctx, float x);
float Example_foo2_ret_0(Example_foo2_type &_ctx);  // first return
float Example_foo2_ret_1(Example_foo2_type &_ctx);  // second return
```

## Calling Generated Code from C++

### Basic usage

```cpp
#include "filter.h"

// 1. Declare the context
Filter_lowpass_type ctx;

// 2. Initialize
Filter_lowpass_init(ctx);

// 3. Process samples
for (int i = 0; i < blockSize; i++) {
    float output = Filter_lowpass(ctx, inputBuffer[i]);
}
```

### Multiple return values

```cpp
Example_foo2_type ctx;
Example_foo2_init(ctx);

Example_foo2(ctx, inputValue);
float first = Example_foo2_ret_0(ctx);
float second = Example_foo2_ret_1(ctx);
```

### Functions linked with `and`

All functions in an `and` chain share the same context type. Initialize once, call any function:

```cpp
// From Vult:
// fun process(x) { mem count; ... }
// and reset() { count = 0; }

Counter_process_type ctx;
Counter_process_init(ctx);

float val = Counter_process(ctx, input);  // calls process
Counter_reset(ctx);                        // calls reset on same context
```

## Platform Integration Patterns

### VCV Rack plugin

The [RackPlayground](https://github.com/vult-dsp/RackPlayground) template shows the standard pattern:

**Vult side** (`processor.vult`):
```
fun process(in1 : real, in2 : real, in3 : real, in4 : real) {
    mem param1, param2, param3, param4;
    val out1, out2, out3, out4 = 0.0, 0.0, 0.0, 0.0;

    // Your DSP here
    out1 = in1 * param1;

    return out1, out2, out3, out4;
}
```

**C++ side** (in your VCV Rack module):
```cpp
#include "processor.h"

struct MyModule : Module {
    Processor_process_type vultCtx;

    MyModule() {
        config(4, 4, 4, 0);
        Processor_process_init(vultCtx);
    }

    void process(const ProcessArgs &args) override {
        float in1 = inputs[0].getVoltage();
        float in2 = inputs[1].getVoltage();
        float in3 = inputs[2].getVoltage();
        float in4 = inputs[3].getVoltage();

        Processor_process(vultCtx, in1, in2, in3, in4);

        outputs[0].setVoltage(Processor_process_ret_0(vultCtx));
        outputs[1].setVoltage(Processor_process_ret_1(vultCtx));
        outputs[2].setVoltage(Processor_process_ret_2(vultCtx));
        outputs[3].setVoltage(Processor_process_ret_3(vultCtx));
    }
};
```

### Audio plugin pattern (JUCE, custom frameworks)

Separate the processing function from parameter updates for efficiency:

**Vult side**:
```
fun process(input : real) : real {
    mem b0, b1, b2, a1, a2;
    mem w1, w2;

    // Coefficients are only recalculated when setParams is called
    val w0 = input - a1 * w1 - a2 * w2;
    val y = b0 * w0 + b1 * w1 + b2 * w2;
    w2 = w1;
    w1 = w0;
    return y;
}
and setParams(fc : real, q : real) {
    val w0 = 2.0 * 3.14159 * fc;
    val alpha = sin(w0) / (2.0 * q);
    val a0 = 1.0 + alpha;
    b0 = (1.0 - cos(w0)) / 2.0 / a0;
    b1 = (1.0 - cos(w0)) / a0;
    b2 = (1.0 - cos(w0)) / 2.0 / a0;
    a1 = -2.0 * cos(w0) / a0;
    a2 = (1.0 - alpha) / a0;
}
```

**C++ side**:
```cpp
Filter_process_type ctx;
Filter_process_init(ctx);

// Audio callback (called every sample or block)
void processBlock(float* buffer, int numSamples) {
    for (int i = 0; i < numSamples; i++) {
        buffer[i] = Filter_process(ctx, buffer[i]);
    }
}

// GUI callback (called when knob changes)
void parameterChanged(float cutoff, float resonance) {
    Filter_setParams(ctx, cutoff, resonance);
}
```

### Teensy Audio Library

Use the `-template teensy` flag to generate a Teensy Audio Library compatible object:

```bash
vultc -ccode -template teensy input.vult -o myeffect
```

See [teensy-vult-example](https://github.com/modlfo/teensy-vult-example) for a complete setup.

### Arduino / bare metal

Use external function stubs for hardware I/O:

**Vult side**:
```
external readKnob(pin : int) : int "stub_readKnob";
external writeDac(pin : int, val : int) : unit "stub_writeDac";

fun process() {
    val knob = readKnob(0);
    writeDac(0, knob);
}
```

**C++ side (in Arduino sketch)**:
```cpp
#include "output.h"

// Stub implementations
int stub_readKnob(int pin) { return analogRead(pin); }
void stub_writeDac(int pin, int val) { analogWrite(pin, val); }

Output_process_type ctx;

void setup() {
    Output_process_init(ctx);
}

void loop() {
    Output_process(ctx);
}
```

### PureData externals

Vult can compile modules directly into PureData externals using the `-template pd` flag. The official examples in the Vult repository are all designed as standalone PD modules.

#### Module interface

PureData externals follow a specific function contract. A PD-compatible module defines a `process` function linked with `and` to optional MIDI and initialization handlers:

```
fun process(input : real, ...) {
    // Main audio processing — called per sample
    // Arguments map to PD inlets
    return output;
}
and noteOn(note : int, velocity : int, channel : int) {
    // Called on MIDI Note On
}
and noteOff(note : int, channel : int) {
    // Called on MIDI Note Off
}
and controlChange(control : int, value : int, channel : int) {
    // Called on MIDI CC — use to map CC numbers to parameters
    if (control == 1)
        knob1 = real(value) / 127.0;
    if (control == 2)
        knob2 = real(value) / 127.0;
}
and default() @[init] {
    // Initial knob/parameter values (called at startup)
    knob1 = 0.0;
    knob2 = 0.5;
}
```

All functions in this `and` chain share the same context, so `mem` variables declared in `process` are accessible from `controlChange`, `noteOn`, etc.

#### Compiling a single PD external

```bash
vultc -ccode -template pd input.vult -o myeffect
```

This generates a PureData external with standard inlet/outlet handling. The `-template pd` flag wraps the Vult processing code in PD's `class_new` / `dsp_add` boilerplate, creating proper signal inlets and outlets.

#### Building PD externals with the CMake system

The examples include a complete CMake build system (`examples/CMakeLists.txt` + `examples/cmake/`) that automates the full pipeline: compiling Vult to C++, then building into PD externals.

The core is the `vult_pd()` CMake function (defined in `examples/cmake/pd.cmake`). Given a Vult source file, it:
1. Locates the Vult compiler (`vultc.native` or `vultc`)
2. Runs `vultc -deps` to discover Vult file dependencies for correct incremental builds
3. Runs `vultc -ccode -template pd` to generate the C++ PD external
4. Compiles the generated code + Vult runtime (`runtime/vultin.cpp`) into a shared library

The PureData API header (`m_pd.h`) is bundled in `examples/cmake/pd-deps/` — you don't need a PD installation to build.

**Platform-specific output formats:**

| Platform | File suffix | Link libraries |
|----------|------------|----------------|
| macOS | `.pd_darwin` | none (uses `undefined dynamic_lookup`) |
| Linux | `.pd_linux` | `m`, `c` |
| Windows | `.dll` | `pd` |

External objects are named with the tilde convention (e.g., `ladder~.pd_darwin` for audio-rate objects).

**Build commands:**

```bash
# Prerequisites: cmake installed, vultc in PATH

cd examples
mkdir build && cd build
cmake ../
make
```

On Windows:
```bash
cd examples
mkdir build && cd build
cmake ../ -G "NMake Makefiles"
nmake
```

After building, all PD externals are in the `build/` directory. To use them in PureData, add this directory to PD's start path (Preferences → Path).

#### Adding your own module to the CMake build

In `CMakeLists.txt`, add a `vult_pd()` call following the existing pattern:

```cmake
# VULT_INCLUDES points to directories with imported Vult files
set(VULT_INCLUDES util osc midi env filters effects)

# Add your module
vult_pd(mymodule ${CMAKE_CURRENT_SOURCE_DIR}/path/to/mymodule.vult VULT_INCLUDES)
```

This builds `mymodule~.pd_darwin` (or platform equivalent) from `mymodule.vult`.

#### Complete list of example PD modules

The CMakeLists.txt builds these externals from the example Vult sources:

| Category | PD object name | Source file | Description |
|----------|---------------|-------------|-------------|
| **Oscillators** | `phase~` | `osc/phase.vult` | Phase accumulator |
| | `blit~` | `osc/blit.vult` | Bandlimited impulse train |
| | `saw_blit~` | `osc/saw_blit.vult` | BLIT-based sawtooth |
| | `noise~` | `osc/noise.vult` | Noise generator |
| | `phd~` | `osc/phd.vult` | Phase distortion |
| | `saw_eptr~` | `osc/saw_eptr.vult` | Saw (efficient PTR) |
| | `saw_ptr1~` | `osc/saw_ptr1.vult` | Saw (PTR variant 1) |
| | `saw_ptr2~` | `osc/saw_ptr2.vult` | Saw (PTR variant 2) |
| | `saw_r~` | `osc/saw_r.vult` | Basic sawtooth |
| | `sawcore~` | `osc/sawcore.vult` | Saw core oscillator |
| | `sine~` | `osc/sine.vult` | Sine oscillator |
| | `tricore~` | `osc/tricore.vult` | Triangle core oscillator |
| | `minblep~` | `osc/minblep.vult` | MinBLEP anti-aliased |
| **MIDI** | `gates~` | `midi/gates.vult` | MIDI gate extraction |
| | `monocv~` | `midi/monocv.vult` | Mono MIDI to CV |
| | `polycv~` | `midi/monocv.vult` | Poly MIDI to CV |
| **Envelopes** | `ad~` | `env/ad.vult` | Attack-Decay envelope |
| | `adsr~` | `env/adsr.vult` | Full ADSR envelope |
| | `ahr~` | `env/ahr.vult` | Attack-Hold-Release |
| | `lfo~` | `env/lfo.vult` | Shape-selectable LFO |
| | `swept~` | `env/swept.vult` | Swept resonator |
| **Filters** | `ladder~` | `filters/ladder.vult` | Diode ladder filter |
| | `svf~` | `filters/svf.vult` | State variable filter |
| **Effects** | `saturate~` | `effects/saturate.vult` | Hard saturation |
| | `saturate_soft~` | `effects/saturate_soft.vult` | Soft saturation |
| | `short_delay~` | `effects/short_delay.vult` | Short delay/echo |
| | `bitcrush~` | `effects/bitcrush.vult` | Bitcrusher / decimator |
| | `rescomb~` | `effects/rescomb.vult` | Resonant comb filter |
| | `clipper~` | `effects/clipper.vult` | Wave clipper |
| | `fold~` | `effects/fold.vult` | Wavefolder |
| **Units** | `kick~` | `units/kick.vult` | Kick drum synth |
| | `voice_4~` | `units/voice_4.vult` | 4-voice polyphonic |

These modules can also be imported into other Vult files to assemble more complex patches — they aren't limited to PureData use.

### WebAudio (JavaScript)

```bash
vultc -jscode input.vult -o myeffect
```

See [vult-webaudio](https://github.com/modlfo/vult-webaudio) for browser integration examples.

## Fixed-Point Arithmetic

### When to use fixed-point

Fixed-point (q16.16) is ideal for microcontrollers without an FPU:
- Arduino (AVR, some ARM)
- Raspberry Pi Pico
- Low-power ARM Cortex-M0/M0+

Floating-point is better for:
- Desktop processors (x86, x64)
- ARM Cortex-M4F/M7 (with FPU)
- VCV Rack, JUCE plugins

### Generating fixed-point code

```bash
vultc -ccode -real fixed input.vult -o output
```

This replaces all `real` operations with `fix16_t` operations. The generated code uses `fix_mul`, `fix_exp`, etc.

### Range considerations

q16.16 format limits:
- Maximum value: ~32767.0
- Minimum nonzero: ~0.0000153
- Sample rate values (44100, 48000) **exceed** the range

**Solutions**:
- Scale computations (e.g., use kHz instead of Hz)
- Pre-divide constants: `(44100.0 / 2.0) / hz` instead of `44100.0 / hz`
- Use `@[table]` tags for expensive functions like `exp()`

### Mixed fixed/floating-point

In recent compiler versions, you can mix `fix16` and `real` in the same file without the `-real fixed` flag:

```
val x = 12.5x;          // 'x' suffix = fixed-point literal
val y = 34.0x;
val z = x + y;           // fixed-point addition
val w = foo(real(z));    // convert to float for foo()
```

## Polyphony

Vult doesn't have built-in polyphony, but it's straightforward with arrays of context structs:

```cpp
// C++ side for polyphonic VCV Rack module
static const int MAX_VOICES = 16;

struct MyModule : Module {
    Processor_process_type voices[MAX_VOICES];
    int numVoices = 1;

    MyModule() {
        for (int v = 0; v < MAX_VOICES; v++)
            Processor_process_init(voices[v]);
    }

    void process(const ProcessArgs &args) override {
        for (int v = 0; v < numVoices; v++) {
            float input = inputs[POLY_INPUT].getVoltage(v);
            Processor_process(voices[v], input);
            outputs[POLY_OUTPUT].setVoltage(
                Processor_process_ret_0(voices[v]), v
            );
        }
        outputs[POLY_OUTPUT].setChannels(numVoices);
    }
};
```

### Voice sharing optimization

If `setParameters` is expensive, compute once and copy to other voices:

```cpp
void parameterChanged(float param) {
    Processor_setParameters(voices[0], param);
    // Copy the computed coefficients to all other voices
    for (int v = 1; v < numVoices; v++) {
        voices[v].b0 = voices[0].b0;
        voices[v].b1 = voices[0].b1;
        // ... copy coefficient fields
    }
}
```
