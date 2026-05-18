---
name: vcv-rack-plugin
description: Build VCV Rack v2 plugins and modules in C++. Covers scaffolding, DSP implementation, panel design, widget construction, polyphony, expanders, build system, cross-compilation, and CI/CD. Use this skill whenever the user mentions VCV Rack, Rack plugins, Rack modules, eurorack simulation, modular synthesizer plugins, or wants to create audio DSP modules for VCV Rack — even if they just say "Rack plugin" or "make a module". Also applies when users are working in an existing VCV plugin codebase (files like plugin.hpp, plugin.json, Makefile with plugin.mk include, src/ with Module/ModuleWidget structs).
---

# VCV Rack Plugin Development

You are helping build a plugin for VCV Rack v2 — a open-source Eurorack modular synthesizer simulator. Plugins are C++ shared libraries (.dylib/.so/.dll) that Rack loads at runtime.

## How VCV Rack Plugins Work

A plugin is a collection of modules. Each module has two halves:

- **Module** (engine) — subclasses `rack::Module`, holds state and DSP logic. The `process()` method is called every audio sample.
- **ModuleWidget** (UI) — subclasses `rack::ModuleWidget`, lays out the panel with knobs, ports, lights, and displays.

These are always paired: one `Module` struct and one `ModuleWidget` struct, registered together via `createModel<>()`.

## Project Structure

A VCV Rack plugin follows this layout:

```
MyPlugin/
  plugin.json            # Manifest: slug, version, license, modules list
  plugin.hpp             # extern Plugin* + extern Model* declarations
  plugin.cpp             # init() — registers all module models
  Makefile               # Delegates to Rack SDK's plugin.mk
  src/
    MyModule.hpp         # Module + ModuleWidget struct declarations
    MyModule.cpp         # Module implementation + Model registration
    dsp/                 # DSP classes (separated from Rack glue)
    utils/               # Utility classes (limiters, wavetables, etc.)
    tests/               # Unit tests
  res/
    MyModule.svg         # Panel graphic (per module)
    MyModule-dark.svg    # Optional dark theme variant
  presets/
    MyModule/
      00_Preset.vcvm     # Factory presets
  dep/
    Rack-SDK/            # Vendored SDK (downloaded by CLI or manually)
  build.sh               # RACK_DIR=./dep/Rack-SDK make dist
  clean.sh               # RACK_DIR=./dep/Rack-SDK make clean
  install.sh             # RACK_DIR=./dep/Rack-SDK make install
```

## Workflow: Creating a New Plugin

### 1. Scaffold the Project

If the user has `vcp` (vc-plugins-cli) installed:
```bash
vcp --create-plugin
```

Otherwise, use the Rack SDK helper:
```bash
$RACK_DIR/helper.py createplugin MyPlugin
```

Or scaffold manually by creating the files below.

### 2. Create plugin.json

Read `references/manifest-reference.md` for the full schema. Key fields:

```json
{
  "slug": "my-plugin",
  "name": "My Plugin",
  "version": "2.0.0",
  "license": "GPL-3.0-or-later",
  "brand": "MyBrand",
  "author": "Your Name",
  "authorEmail": "you@example.com",
  "modules": []
}
```

The `slug` must NEVER change after release. Version major must match Rack major (2.x.x for Rack 2).

### 3. Create plugin.hpp and plugin.cpp

**plugin.hpp:**
```cpp
#pragma once
#include <rack.hpp>
using namespace rack;

extern Plugin* pluginInstance;
extern Model* modelMyModule;
```

**plugin.cpp:**
```cpp
#include "plugin.hpp"

Plugin* pluginInstance;

void init(Plugin* p) {
    pluginInstance = p;
    p->addModel(modelMyModule);
}
```

### 4. Create the Module

See `references/module-template.md` for a complete starter template. The core pattern:

```cpp
// MyModule.hpp
#pragma once
#include <rack.hpp>
using namespace rack;

struct MyModule : Module {
    enum ParamId {
        FREQ_PARAM,
        NUM_PARAMS
    };
    enum InputId {
        FREQ_INPUT,
        AUDIO_INPUT,
        NUM_INPUTS
    };
    enum OutputId {
        AUDIO_OUTPUT,
        NUM_OUTPUTS
    };
    enum LightId {
        NUM_LIGHTS
    };

    MyModule() {
        config(NUM_PARAMS, NUM_INPUTS, NUM_OUTPUTS, NUM_LIGHTS);
        configParam(FREQ_PARAM, -54.f, 54.f, 0.f, "Frequency", " Hz", dsp::FREQ_C4, dsp::FREQ_C4);
        configInput(FREQ_INPUT, "Frequency CV");
        configInput(AUDIO_INPUT, "Audio");
        configOutput(AUDIO_OUTPUT, "Audio");
    }

    void process(const ProcessArgs& args) override;
};

struct MyModuleWidget : ModuleWidget {
    MyModuleWidget(MyModule* module) {
        setModule(module);
        setPanel(createPanel(asset::plugin(pluginInstance, "res/MyModule.svg")));

        addChild(createWidget<ScrewSilver>(Vec(0, 0)));
        addChild(createWidget<ScrewSilver>(Vec(box.size.x - RACK_GRID_WIDTH, 0)));
        addChild(createWidget<ScrewSilver>(Vec(0, RACK_HEIGHT - RACK_GRID_WIDTH)));
        addChild(createWidget<ScrewSilver>(Vec(box.size.x - RACK_GRID_WIDTH, RACK_HEIGHT - RACK_GRID_WIDTH)));

        float cx = box.size.x / 2.f;
        addParam(createParamCentered<RoundBlackKnob>(Vec(cx, 80.f), module, MyModule::FREQ_PARAM));
        addInput(createInputCentered<PJ301MPort>(Vec(cx, 130.f), module, MyModule::FREQ_INPUT));
        addInput(createInputCentered<PJ301MPort>(Vec(cx, 250.f), module, MyModule::AUDIO_INPUT));
        addOutput(createOutputCentered<PJ301MPort>(Vec(cx, 310.f), module, MyModule::AUDIO_OUTPUT));
    }
};
```

```cpp
// MyModule.cpp
#include "MyModule.hpp"

Model* modelMyModule = createModel<MyModule, MyModuleWidget>("MyModule");

void MyModule::process(const ProcessArgs& args) {
    float pitch = params[FREQ_PARAM].getValue() + inputs[FREQ_INPUT].getVoltage();
    float freq = dsp::FREQ_C4 * std::pow(2.f, pitch / 12.f);
    float in = inputs[AUDIO_INPUT].getVoltage() / 5.f;
    // ... DSP here ...
    outputs[AUDIO_OUTPUT].setVoltage(in * 5.f);
}
```

### 5. Create the Panel SVG

Panels are SVGs designed in Inkscape. See `references/panel-design.md` for full details. Key specs:

- Document units: **mm** (not px)
- Height: **128.5 mm** (standard Eurorack)
- Width: multiples of **5.08 mm** (1 HP)
- Text must be **converted to paths** (Path > Object to Path)
- Use a `components` layer with colored circles for auto-generation:
  - Red `#ff0000` = Param
  - Green `#00ff00` = Input
  - Blue `#0000ff` = Output
  - Magenta `#ff00ff` = Light

### 6. Build and Test

```bash
make            # Compile
make dist       # Package as .vcvplugin
make install    # Install to Rack user folder
```

If plugin doesn't appear, check `log.txt` in Rack user folder.

## The process() Method — Where DSP Happens

`process()` is called once per audio sample (typically 44100 or 48000 Hz). Rules:

1. **Always use `args.sampleTime`** for time-dependent math — never hardcode sample rates
2. **Audio signals**: +/-5V (divide by 5 to normalize, multiply by 5 to output)
3. **CV signals**: 0-10V unipolar, +/-5V bipolar
4. **Pitch**: 1V/octave, baseline C4 = `dsp::FREQ_C4` (261.6256 Hz)
5. **NaN/Inf guard**: `std::isfinite(out) ? out : 0.f` on all outputs
6. **No allocations, no locks, no blocking I/O** in process()

### Common process() Patterns

**Simple per-sample:**
```cpp
void process(const ProcessArgs& args) {
    float dt = args.sampleTime;
    float cv = inputs[CV_INPUT].getVoltage();
    float param = params[PARAM].getValue();
    float combined = param + cv;
    combined = clamp(combined, 0.f, 1.f);
    // ... DSP ...
    float out = dsp.process(combined);
    out = std::isfinite(out) ? clamp(out, -5.f, 5.f) : 0.f;
    outputs[OUT].setVoltage(out);
}
```

**Block-based (for FFT, neural nets, convolution):**
```cpp
static const int BLOCK_SIZE = 128;
float inBuffer[BLOCK_SIZE];
float outBuffer[BLOCK_SIZE];
int bufferPos = 0;

void process(const ProcessArgs& args) {
    float in = inputs[AUDIO_IN].getVoltage() / 5.f;
    inBuffer[bufferPos] = in;
    bufferPos++;
    if (bufferPos >= BLOCK_SIZE) {
        bufferPos = 0;
        engine.processBlock(inBuffer, outBuffer, BLOCK_SIZE);
    }
    float out = outBuffer[bufferPos] * 5.f;
    outputs[AUDIO_OUT].setVoltage(clamp(out, -5.f, 5.f));
}
```

## Voltage Standards Quick Reference

| Signal | Range | Notes |
|--------|-------|-------|
| Audio | +/-5V (10Vpp) | Standard output level |
| Unipolar CV | 0 to 10V | Envelopes, velocity |
| Bipolar CV | +/-5V | Pitch, LFO, modulation |
| Triggers | 10V, 1ms duration | Use `dsp::PulseGenerator` |
| Gates | 10V when high | Use `dsp::SchmittTrigger` for input |
| Pitch | 1V/oct | C4 = 0V = 261.6 Hz |

## Widget Construction — Building the UI

Always use centered layout helpers:

```cpp
float cx = box.size.x / 2.f;
addParam(createParamCentered<RoundBlackKnob>(Vec(cx, y), module, ParamId));
addInput(createInputCentered<PJ301MPort>(Vec(cx, y), module, InputId));
addOutput(createOutputCentered<PJ301MPort>(Vec(cx, y), module, OutputId));
addLight(createLightCentered<MediumLight<GreenLight>>(Vec(cx, y), module, LightId));
```

### Available Components

The Rack SDK includes a full component library. See `references/component-library.md` for the complete catalog of 60+ components (knobs, ports, switches, buttons, sliders, screws, lights). Most commonly used:

| Component | Use For |
|-----------|---------|
| `RoundBlackKnob` | Standard knobs |
| `RoundLargeBlackKnob` | Primary/main knobs |
| `RoundSmallBlackKnob` | Secondary/CV amount knobs |
| `RoundBlackSnapKnob` | Stepped selection knobs |
| `Trimpot` | Small trim pots (attenuverters) |
| `Davies1900hLargeBlackKnob` | Vintage-style knobs |
| `PJ301MPort` | Standard jacks (in/out) |
| `ThemedPJ301MPort` | Theme-aware jacks (dark/light) |
| `CKSS` | 2-position toggle |
| `CKSSThree` | 3-position toggle |
| `LEDButton` | Illuminated button |
| `ScrewSilver` / `ScrewBlack` | Panel screws |
| `ThemedScrew` | Theme-aware screws |

### Context Menus

```cpp
void appendContextMenu(Menu* menu) override {
    auto* m = dynamic_cast<MyModule*>(module);
    if (!m) return;
    menu->addChild(new MenuSeparator());
    menu->addChild(createMenuItem("Action", "", [=]() { m->doSomething(); }));
    menu->addChild(createBoolMenuItem("Toggle", "",
        [=]() { return m->getState(); },
        [=](bool v) { m->setState(v); }));
}
```

## Serialization (Saving/Loading State)

Parameters are auto-saved. Only serialize custom state:

```cpp
json_t* dataToJson() override {
    json_t* root = json_object();
    json_object_set_new(root, "filePath", json_string(filePath.c_str()));
    json_object_set_new(root, "mode", json_integer(mode));
    json_object_set_new(root, "enabled", json_boolean(enabled));
    return root;
}

void dataFromJson(json_t* root) override {
    json_t* j = json_object_get(root, "filePath");
    if (j) filePath = json_string_value(j);
    json_t* m = json_object_get(root, "mode");
    if (m) mode = json_integer_value(m);
}
```

## Async Loading (for file I/O, heavy DSP init)

Never block the audio thread. Use this pattern for file loading:

```cpp
std::thread loadThread;
std::atomic<bool> isLoading{false};
std::atomic<bool> hasPending{false};

void loadFile(const std::string& path) {
    if (isLoading) return;
    if (loadThread.joinable()) loadThread.join();
    isLoading = true;
    loadThread = std::thread([this, path]() {
        // Heavy work here (file I/O, model loading, etc.)
        hasPending.store(true, std::memory_order_release);
        isLoading = false;
    });
}

// In process():
if (hasPending.exchange(false, std::memory_order_acq_rel)) {
    // Apply loaded data on audio thread
}

~MyModule() {
    if (loadThread.joinable()) loadThread.join();
}
```

## Polyphony

Support 16 channels max. Organize per-channel state into structs:

```cpp
struct Engine {
    float phase = 0.f;
    dsp::BiquadFilter filter;
};
Engine engines[16];

void process(const ProcessArgs& args) {
    int channels = std::max(1, inputs[AUDIO_INPUT].getChannels());
    for (int c = 0; c < channels; c++) {
        float in = inputs[AUDIO_INPUT].getPolyVoltage(c) / 5.f;
        float out = engines[c].process(in);
        outputs[AUDIO_OUTPUT].setVoltage(out * 5.f, c);
    }
    outputs[AUDIO_OUTPUT].setChannels(channels);
}
```

## Expanders (Inter-Module Communication)

Use double-buffered expander messages for thread-safe communication between adjacent modules:

```cpp
struct ExpanderMessage {
    float audioL, audioR;
    bool connected;
};

// Host module constructor:
rightExpander.producerMessage = new ExpanderMessage();
rightExpander.consumerMessage = new ExpanderMessage();

// Host process():
if (rightExpander.module && rightExpander.module->model == modelMyExpander) {
    auto* msg = static_cast<ExpanderMessage*>(rightExpander.consumerMessage);
    // Read from expander
}
```

## Makefile Pattern

```makefile
RACK_DIR ?= dep/Rack-SDK
FLAGS += -Isrc
CXXFLAGS +=
LDFLAGS +=
SOURCES += $(wildcard src/*.cpp)
DISTRIBUTABLES += res
DISTRIBUTABLES += $(wildcard LICENSE*)
include $(RACK_DIR)/plugin.mk
```

Add subdirectories: `SOURCES += $(wildcard src/dsp/*.cpp)`
Add presets: `DISTRIBUTABLES += presets`

## DSP Architecture: Separate Concerns

Keep Rack glue separate from DSP. Your DSP classes should not include `rack.hpp`:

```
src/
  MyModule.cpp        # Rack Module — reads params/inputs, calls DSP, writes outputs
  dsp/
    MyDspEngine.h     # Pure DSP — no Rack dependency
    filters.h
    oscillator.h
```

The Module is a thin wrapper that:
1. Reads Rack params and inputs (voltage domain)
2. Converts to normalized values (/ 5.f for audio)
3. Calls DSP engine methods
4. Converts back to voltage (* 5.f) and writes outputs

## Build and Release

### Local Build
```bash
RACK_DIR=./dep/Rack-SDK make dist    # Build .vcvplugin package
RACK_DIR=./dep/Rack-SDK make install  # Install to Rack
```

### Cross-Compilation (all platforms)
If using rack-plugin-toolchain with Docker:
```bash
docker run --rm -v $(pwd):/plugin rack-plugin-toolchain:19 make plugin-build PLUGIN_DIR=/plugin
```

### GitHub Actions CI/CD
See `references/ci-cd.md` for a complete workflow that builds for all 4 targets (lin-x64, win-x64, mac-x64, mac-arm64) and publishes releases on tag.

Tag releases: `git tag v2.0.0 && git push --tags` (tag must match version in plugin.json).

## Use the Rack SDK — Don't Reinvent Utilities

The Rack SDK provides a rich set of utility functions. Always use these instead of writing your own. Agents commonly make the mistake of re-implementing basic utilities that already exist in the SDK.

**Math/Utility functions available in `rack.hpp` (namespace `rack` or `rack::dsp`):**
- `clamp(value, min, max)` — clamps a value to range. Do NOT write your own clamp.
- `rescale(value, min, max, outMin, outMax)` — maps a value from one range to another
- `math::clamp()`, `math::rescale()`, `math::normalize()` — in `rack::math` namespace
- `math::interpolateLinear()`, `math::interpolateLog()` — interpolation helpers
- `dsp::quadraticBipolar()`, `dsp::cubic()`, `dsp::exponentialBipolar()` — parameter curves
- `dsp::amplitudeToDb()`, `dsp::dbToAmplitude()` — dB conversion
- `dsp::FREQ_C4` (261.6256 Hz), `dsp::FREQ_A4` (440 Hz) — standard frequencies
- `dsp::exp2_taylor5()` — fast 2^x approximation for pitch conversion
- `dsp::approxSin()`, `dsp::approxCos()` — fast trig approximations
- `dsp::SchmittTrigger`, `dsp::PulseGenerator`, `dsp::Timer` — digital utilities
- `dsp::BiquadFilter`, `dsp::RCFilter`, `dsp::SlewLimiter`, `dsp::ExponentialFilter` — filters
- `dsp::minBlep` — anti-aliasing for oscillator discontinuities

**String/formatting:**
- `string::f()` — sprintf-like formatting returning std::string
- `string::toLowerCase()`, `string::trim()`, `string::truncate()` — string utils

**Always check the SDK API before writing utility code.** See `references/rack-sdk-api.md` for the full reference, or read the SDK headers in `dep/Rack-SDK/include/`.

## Common Pitfalls

- **No spaces in paths** — the Makefile build system cannot handle them
- **Text in SVGs must be paths** — Rack's renderer doesn't support fonts
- **Don't store font/image references across frames** — OpenGL context may be destroyed; load each frame via `APP->window->loadFont()`
- **Don't hardcode sample rate** — use `args.sampleTime`
- **Don't allocate in process()** — no new/malloc, no STL container growth
- **Don't block in process()** — no file I/O, no mutex locks, no network
- **Don't hard-clip outputs** — let downstream modules handle saturation
- **Don't write your own clamp/rescale** — use `clamp()` and `rescale()` from the SDK
- **Slug must never change** — it's the permanent identifier

## Reference Files

Load these when you need deeper detail on a specific topic:

- `references/manifest-reference.md` — Full plugin.json schema with all fields and module tags
- `references/module-template.md` — Complete copy-paste module template with all optional features
- `references/dsp-patterns.md` — DSP cookbook: oscillators, filters, envelopes, triggers
- `references/panel-design.md` — SVG panel creation with Inkscape, component placement, dark theme
- `references/component-library.md` — Full catalog of 60+ built-in UI components (knobs, ports, switches, etc.)
- `references/ci-cd.md` — GitHub Actions workflow for multi-platform builds
- `references/rack-sdk-api.md` — Key SDK API reference (engine, dsp, app, widget namespaces)
- `references/testing.md` — DSP unit testing: test framework, mock strategies, coverage, performance benchmarks
