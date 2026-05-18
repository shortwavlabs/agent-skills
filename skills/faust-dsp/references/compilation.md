# Faust Compilation Targets and Architecture Files

How to compile Faust `.dsp` files to various platforms, plugins, and standalone applications.

## Table of Contents

- [Compiler Options](#compiler-options)
- [Generated C++ Class](#generated-c-class)
- [faust2xx Scripts](#faust2xx-scripts)
- [Plugin Formats](#plugin-formats)
- [Embedded Platforms](#embedded-platforms)
- [Web and Mobile](#web-and-mobile)
- [Architecture Files](#architecture-files)
- [Code Generation Modes](#code-generation-modes)
- [Online Tools](#online-tools)

## Compiler Options

### Basic Usage

```bash
# Default: output C++ to stdout
faust mydsp.dsp

# Output to file
faust mydsp.dsp -o mydsp.cpp

# With architecture file
faust -a architecture-file.cpp mydsp.dsp -o mydsp.cpp

# Compile and link
g++ -O3 mydsp.cpp -o mydsp
```

### Backend Selection

```bash
-lang cpp        # C++ output (default)
-lang c          # C output
-lang llvm       # LLVM IR
-lang wasm       # WebAssembly
-lang rust       # Rust
-lang julia      # Julia
-lang cmajor     # Cmajor
-lang jsfx       # REAPER JSFX
```

### Precision

```bash
-single          # Single precision float (default)
-double          # Double precision
-quad            # Quad precision (some backends)
-fx              # Fixed point
```

### Optimization

```bash
-vec             # Vector code generation (for SIMD)
-vec --vec-size 64   # Vector size (default 32)
-omp             # OpenMP parallel code
-sch             # Work-stealing scheduler parallel code
-inpl            # In-place computation (scalar mode only)
-sp              # Scalar mode (default, explicit)
```

### Output Control

```bash
-o file.cpp      # Output file
-strip           # Strip comments from generated code
-sd              # Static data allocation in global scope
-mdoc            # Generate mathematical documentation
-svg             # Generate SVG block diagram
-xml             # Generate XML description
-json            # Generate JSON description
-graph           # Generate graph for visualization
```

### Other Useful Options

```bash
-I path          # Add include path for libraries
-sr rate         # Set sampling rate
-bs size         # Set block size
-mid             # Enable MIDI awareness
-ns name         # Set generated class name
-cn name         # Set class name
-scn name        # Set super class name
-diff            # Differentiate the DSP
-it              # Interactive mode
-time            # Print compilation time
```

## Generated C++ Class

The Faust compiler generates a `dsp` subclass with this interface:

```cpp
class mydsp : public dsp {
  public:
    // Metadata
    void metadata(Meta* m);

    // Channel count
    int getNumInputs();
    int getNumOutputs();

    // Initialization
    void init(int sample_rate);
    void instanceInit(int sample_rate);
    void instanceConstants(int sample_rate);
    void instanceResetUserInterface();
    void instanceClear();

    // Cloning
    mydsp* clone();

    // Sample rate
    int getSampleRate();

    // UI description
    void buildUserInterface(UI* ui_interface);

    // Audio processing
    void compute(int count, FAUSTFLOAT** inputs, FAUSTFLOAT** outputs);
};
```

The `compute` method processes `count` samples. `inputs` and `outputs` are arrays of mono channel buffers. `FAUSTFLOAT` is typically `float` or `double` depending on the architecture.

## faust2xx Scripts

One-step compilation from `.dsp` to runnable binary. Run `faust2` then press Tab for a full list.

### Audio Applications

| Script | Description |
|--------|-------------|
| `faust2jaqt` | JACK application with Qt GUI |
| `faust2jack` | JACK application with GTK GUI |
| `faust2jackconsole` | JACK headless |
| `faust2caqt` | CoreAudio application with Qt GUI (macOS) |
| `faust2alqt` | ALSA application with Qt GUI (Linux) |
| `faust2alsa` | ALSA application with GTK GUI (Linux) |
| `faust2alsaconsole` | ALSA headless (Linux) |
| `faust2netjackqt` | NetJack with Qt GUI |
| `faust2netjackconsole` | NetJack headless |

### Audio Plugins

| Script | Description |
|--------|-------------|
| `faust2faustvst` | VST2 plugin |
| `faust2lv2` | LV2 plugin |
| `faust2au` | Audio Unit plugin (macOS) |
| `faust2api` | C/C++ API (dsp.h + dsp.cpp) |
| `faust2csound` | Csound opcode |
| `faust2supercollider` | SuperCollider external |
| `faust2puredata` | PureData external |
| `faust2max6` | Max/MSP 6+ external |
| `faust2msp` | Max/MSP 5 external |
| `faust2owl` | OWL Program |
| `faust2ck` | ChucK external |
| `faust2unity` | Unity plugin |
| `faust2juce` | JUCE plugin project |
| `faust2rpnc` | RNBO compatible code |

### Mobile / Embedded

| Script | Description |
|--------|-------------|
| `faust2android` | Android app |
| `faust2ios` | iOS app |
| `faust2caqtios` | iOS app with Qt |
| `faust2bela` | Bela board |
| `faust2rpialsaconsole` | Raspberry Pi ALSA |
| `faust2rpinetjackconsole` | Raspberry Pi JACK |

### Visualization / Documentation

| Script | Description |
|--------|-------------|
| `faust2svg` | SVG block diagram |
| `faust2png` | PNG block diagram |
| `faust2pdf` | PDF documentation |
| `faust2graph` | SVG signal graph |
| `faust2sig` | SVG signal diagram |
| `faust2mathdoc` | Automatic mathematical PDF |
| `faust2plot` | Command-line sample plotter |

### Example Usage

```bash
# VST plugin (outputs .so/.dll/.vst)
faust2faustvst mydsp.dsp

# JACK Qt app
faust2jaqt mydsp.dsp

# SVG block diagram
faust2svg mydsp.dsp

# PureData external
faust2puredata mydsp.dsp

# iOS app
faust2ios mydsp.dsp

# C/C++ API
faust2api -double mydsp.dsp
```

## Plugin Formats

### VST Plugin
```bash
faust2faustvst mydsp.dsp          # produces mydsp.vst
```

Metadata for the plugin:
```faust
declare name "Plugin Name";
declare author "Author";
declare description "Plugin description";
declare version "1.0";
declare category "Effect";  // or "Synth", "Instrument", etc.
```

### Audio Unit (macOS)
```bash
faust2au mydsp.dsp                # produces .component
```

### LV2 Plugin
```bash
faust2lv2 mydsp.dsp               # produces LV2 bundle
```

### JUCE Plugin
```bash
faust2juce mydsp.dsp              # produces JUCE project
```

## Embedded Platforms

### Bela
```bash
faust2bela mydsp.dsp
```

Bela-specific: analog I/O, digital I/O accessible through special primitives.

### Teensy
Use the Faust Teensy tutorial for setup. Compile with:
```bash
faust -lang c -double mydsp.dsp -o mydsp.cpp
```
Then integrate with the Teensy Audio library.

### ESP32
```bash
# WebAssembly output for ESP32
faust -lang wasm mydsp.dsp -o mydsp.wasm
```

### Raspberry Pi
```bash
faust2rpialsaconsole mydsp.dsp
faust2rpinetjackconsole mydsp.dsp
```

## Web and Mobile

### WebAudio / WebAssembly
```bash
faust2wasm mydsp.dsp              # WebAssembly + JS wrapper
```

The generated code can be loaded directly in a browser. The Faust Web IDE provides a ready-to-use web environment.

### Android
```bash
faust2android mydsp.dsp           # produces .apk
```

### iOS
```bash
faust2ios mydsp.dsp               # produces Xcode project
```

## Architecture Files

Architecture files bridge the Faust DSP to the real world (audio drivers, GUI, MIDI, etc.). They are specified with `-a`:

```bash
faust -a architecture-file.cpp mydsp.dsp -o output.cpp
```

Standard architecture files are in the `architecture/` directory of the Faust distribution:

### Audio Drivers
- `alsa-gtk.cpp` — ALSA audio + GTK GUI
- `alsa-qt.cpp` — ALSA audio + Qt GUI
- `jack-gtk.cpp` — JACK audio + GTK GUI
- `jack-qt.cpp` — JACK audio + Qt GUI
- `coreaudio-qt.cpp` — CoreAudio + Qt (macOS)
- `au/AU.cpp` — Audio Unit
- `vst/vst2p4.cpp` — VST2
- `lv2/` — LV2 architectures
- `webaudio/wasm.cpp` — WebAssembly
- `android/` — Android architectures
- `ios/` — iOS architectures
- `bela/` — Bela architectures

### Key C++ Classes
- `faust/dsp/dsp.h` — Base `dsp` class
- `faust/gui/UI.h` — UI builder interface
- `faust/gui/MidiUI.h` — MIDI handler
- `faust/gui/OSCUI.h` — OSC handler
- `faust/gui/HttpUI.h` — HTTP control
- `faust/gui/SoundUI.h` — Soundfile loader
- `faust/dsp/poly-dsp.h` — Polyphony handler
- `faust/dsp/dsp-combiner.h` — DSP chain combiner

## Code Generation Modes

### Scalar (default)
Single sample computation in one loop. Simple but prevents SIMD.

```bash
faust -sp mydsp.dsp -o mydsp.cpp
```

### Vector (`-vec`)
Splits computation into simpler loops that communicate via vectors. Enables C++ compiler autovectorization. Typical speedup: 2-4x.

```bash
faust -vec --vec-size 32 mydsp.dsp -o mydsp.cpp
```

### OpenMP (`-omp`)
Built on vector mode. Inserts OpenMP directives for multi-core parallelism. Best for complex Faust programs.

```bash
faust -omp mydsp.dsp -o mydsp.cpp
g++ -O3 -fopenmp mydsp.cpp -o mydsp
```

### Scheduler (`-sch`)
Built on vector mode. Uses a work-stealing scheduler with thread pool. Better than OpenMP for some workloads and on macOS.

```bash
faust -sch mydsp.dsp -o mydsp.cpp
```

## Online Tools

### Faust Online IDE
https://faustide.grame.fr — Full IDE with real-time compilation, audio output, block diagrams, and export to all targets.

### Faust Online Editor
https://fausteditor.grame.fr — Lightweight editor with instant compilation.

### Faust Playground
https://faustplayground.grame.fr — Visual drag-and-drop Faust programming in the browser.

## Embedding Faust

### Static Compilation
```bash
faust -a my-arch.cpp mydsp.dsp -o mydsp.cpp
g++ mydsp.cpp -o mydsp
```

### Dynamic Compilation (libfaust)
Use the LLVM backend to compile Faust at runtime:

```cpp
#include "faust/dsp/libfaust.h"

dsp* DSP = createDSPFromString("process = _;", "", 0);
DSP->init(44100);
DSP->compute(count, inputs, outputs);
```

### Cmajor Backend
```bash
faust -lang cmajor mydsp.dsp -o mydsp.cmajor
```

### JSFX (REAPER) Backend
```bash
faust -lang jsfx mydsp.dsp -o mydsp.jsfx
```

### RNBO Backend
```bash
faust2rpnc mydsp.dsp
```
