# agent-skills

AI coding agent skills for audio development workflows.

## Installation

```bash
npx skills add shortwavlabs/agent-skills
```

## Skills

### plugdata-patch

Generate Pure Data / plugdata audio patches (`.pd` files) programmatically. The skill understands the full `.pd` text format, 1,653+ objects across 8 libraries, compilation targets, and Lua scripting — enabling AI agents to create synthesizers, effects, MIDI processors, and DSP patches from natural language descriptions.

**Triggers on:** building synths, audio effects, MIDI patches, Pure Data/plugdata patches, `.pd` file generation, visual audio programming.

#### Structure

```
skills/plugdata-patch/
├── SKILL.md                    Main skill instructions & patch generation workflow
└── references/
    ├── pd-format.md            .pd file format specification
    ├── objects.md              Object catalog (1,653 objects, 8 libraries)
    ├── else.md                 ELSE library (595 objects) — oscillators, effects, modules
    ├── cyclone.md              Cyclone library (206 objects) — Max/MSP compatibility
    ├── hvcc.md                 Heavy compiler — targets, constraints, parameter annotations
    └── pd-lua.md               pd-lua API — custom objects in Lua
```

#### What it covers

| Area | Details |
|------|---------|
| **Patch format** | Complete `.pd` syntax: canvas, objects, connections, subpatches, arrays, GUI |
| **ELSE library** | 595 objects — bandlimited oscillators, 9 reverbs, 20 M.E.R.D.A. modules, MIDI, tuning, multichannel |
| **Cyclone library** | 206 objects — Max/MSP clones, `zl` polymode, non-alphanumeric operators |
| **hvcc compilation** | Vanilla + heavylib subset (~323 objects), `@hv_param` annotations, Daisy/DPF/C++ targets |
| **pd-lua scripting** | Custom objects in Lua: inlets/outlets, DSP, clocks, receivers, arrays, GUI graphics |
| **DAW integration** | `param`, `playhead`, `plugin_latency`, `adc~`/`dac~` patterns for 7 DAWs |

#### Source documentation

- [plugdata docs](https://plugdata.org/docs/) (`docs/plugdata/`)
- [ELSE library](https://github.com/porres/pd-else) by Alexandre Torres Porres
- [Cyclone library](https://github.com/porres/pd-cyclone) by Krzysztof Czaja, maintained by Porres
- [Heavy/hvcc compiler](https://wasted-audio.github.io/hvcc/) by Wasted Audio
- [pd-lua](https://agraef.github.io/pd-lua/tutorial/pd-lua-intro.html) by Albert Graf

### vcv-rack-plugin

Build VCV Rack v2 plugins and modules in C++. Covers the full development workflow from scaffolding to cross-platform release, with DSP patterns, widget construction, and Rack SDK API guidance tailored for AI coding agents.

**Triggers on:** VCV Rack, Rack plugins/modules, eurorack simulation, modular synthesizer plugins, `plugin.hpp`/`plugin.json` files, `plugin.mk` build system.

#### Structure

```
skills/vcv-rack-plugin/
├── SKILL.md                    Main skill instructions & module development workflow
└── references/
    ├── manifest-reference.md   plugin.json schema, fields, module tags
    ├── module-template.md      Copy-paste module templates with all features
    ├── dsp-patterns.md         DSP cookbook: oscillators, filters, envelopes, triggers
    ├── panel-design.md         SVG panel creation, component placement, dark theme
    ├── component-library.md    60+ built-in UI components (knobs, ports, switches)
    ├── testing.md              DSP unit testing: frameworks, mock strategies, coverage, benchmarks
    ├── ci-cd.md                GitHub Actions workflow for multi-platform builds
    └── rack-sdk-api.md         Key SDK API reference (engine, dsp, app, widget)
```

#### What it covers

| Area | Details |
|------|---------|
| **Module development** | Module/ModuleWidget pattern, process() DSP, config() API, enum IDs |
| **DSP patterns** | VCO, VCF, VCA, ADSR, delay, LFO, S&H, clock divider, mixer — with voltage conventions |
| **Panel design** | SVG specs (mm units, 128.5mm height), Inkscape workflow, component placeholder system |
| **Components** | 60+ built-in knobs, ports, switches, buttons, sliders, screws, lights |
| **Testing** | Custom test framework, Rack API mocking strategies, DSP test patterns, coverage, benchmarks |
| **Polyphony** | 16-channel support, per-voice engines, getPolyVoltage(), setChannels() |
| **Serialization** | JSON state persistence, dataToJson/dataFromJson, patch storage |
| **Build system** | Makefile + plugin.mk, Rack SDK, cross-compilation toolchain, Docker builds |
| **CI/CD** | GitHub Actions for lin-x64, win-x64, mac-x64, mac-arm64 with automated releases |
| **SDK utilities** | clamp(), rescale(), SchmittTrigger, PulseGenerator, BiquadFilter, and more |

#### Source documentation

- [VCV Rack Manual](https://vcvrack.com/manual/) (`docs/vcv/`)
- [Rack SDK](https://vcvrack.com/manual/PluginDevelopmentTutorial) — API headers, build system
- [VCV Community — Development](https://community.vcvrack.com/c/development/8) — forum discussions
- [vc-plugins-cli](https://github.com/stephanepericat/vc-plugins-cli) — project scaffolding tool
- [rack-plugin-toolchain](https://github.com/stephanepericat/rack-plugin-toolchain) — cross-compilation build system

### juce-plugin

Build JUCE audio plugins (VST3, AU, AAX, LV2, Standalone) in C++ with CMake. Covers the full development workflow from project scaffolding to multi-format builds — AudioProcessor lifecycle, parameter management with APVTS, DSP module chains, custom editor GUIs, WebView UIs with web technologies (React, Vue, Svelte), state serialization, real-time audio safety, and cross-platform CI/CD.

**Triggers on:** JUCE, audio plugins, VST plugins, AU plugins, audio effects, synthesizers, MIDI processors, AudioProcessor, AudioProcessorEditor, Projucer, `juce_add_plugin`, PluginProcessor.cpp, PluginEditor.cpp.

#### Structure

```
skills/juce-plugin/
├── SKILL.md                    Main skill instructions & plugin development workflow
└── references/
    ├── plugin-lifecycle.md     AudioProcessor contract: overrides, bus configs, Synthesiser framework
    ├── parameter-management.md APVTS patterns: parameter layout, attachments, state, groups
    ├── dsp-patterns.md         DSP cookbook: ProcessorChain, filters, oscillators, wavetable synthesis, delay, distortion
    ├── ui-patterns.md          Editor patterns: layout, custom widgets, LookAndFeel, meters, FFT spectrum analyser
    ├── webview-ui.md           WebView UIs (JUCE 8): React/Vue frontends, JS parameter bindings, hot reloading
    ├── audio-thread-safety.md  Real-time safety: processBlock rules, lock-free patterns, debugging
    └── cmake-reference.md      Full CMake API: juce_add_plugin, SDK paths, CI/CD, platform specifics
```

#### What it covers

| Area | Details |
|------|---------|
| **Plugin development** | AudioProcessor/AudioProcessorEditor pattern, processBlock(), CMake project setup |
| **Parameter management** | APVTS: ParameterLayout, SliderAttachment, raw pointers, ParameterReferences struct |
| **DSP module** | ProcessorChain, IIR/FIR/SVF filters, Oscillator, WaveShaper, Convolution, DelayLine, LadderFilter, wavetable synthesis, LFO at control rate, two-level chain architecture |
| **Editor/GUI** | Component layout (FlexBox, Grid), custom widgets, LookAndFeel, meters, FFT spectrum analyser, binary data |
| **WebView UIs (JUCE 8)** | WebBrowserComponent, React/Vue frontends, JS parameter bindings, resource providers, hot reloading |
| **State serialization** | XML state save/load, non-parameter state via ValueTree children |
| **Audio thread safety** | No-allocation rules, lock-free patterns, denormal prevention, debugging |
| **Synths** | Synthesiser/SynthesiserVoice/SynthesiserSound framework, polyphonic MIDI, gain ramping |
| **AudioProcessorGraph** | Processor chaining, graph nodes, dynamic rebuild, node bypass |
| **Build system** | CMake: juce_add_plugin, SDK paths, binary data, cross-platform, GitHub Actions CI/CD |
| **Plugin formats** | VST3, AU, AUv3, AAX, LV2, Standalone — format-specific categories and properties |

#### Source documentation

- [JUCE Framework](https://juce.com/) — C++ audio plugin framework by Raw Material Software
- [JUCE CMake API](https://github.com/juce-framework/JUCE/blob/master/docs/CMake%20API.md) — build system reference
- [JUCE Examples](https://github.com/juce-framework/JUCE/tree/master/examples) — official plugin and DSP examples
- [JUCE Development Forum](https://forum.juce.com/c/development/21) — community Q&A and best practices
- [JUCE Tutorials](https://juce.com/learn/tutorials/) — official tutorials on plugins, DSP, synth, MIDI, GUI, and more
- [Pamplejuce](https://github.com/sudara/pamplejuce) — community CMake template for production plugins

### dsp

Digital signal processing algorithms and techniques for real-time audio in C/C++. Covers filter design, audio effects, sound synthesis, spectral analysis, and DSP utilities — derived from the musicdsp.org community archive of practitioner-tested algorithms spanning two decades.

**Triggers on:** audio DSP, digital filters, biquad/Moog/SVF filter code, delay/reverb/compressor/distortion effects, oscillator/wavetable/noise synthesis, FFT/envelope detection, fast math approximations, denormal prevention, interpolation, dithering, any real-time audio processing task.

#### Structure

```
skills/dsp/
├── SKILL.md                    Main skill instructions & implementation principles
└── references/
    ├── filters.md              Filter design: biquad/RBJ, Moog ladder, SVF, FIR, crossover, DC block
    ├── effects.md              Effects: delay, reverb, dynamics, modulation, distortion, stereo
    ├── synthesis.md            Synthesis: oscillators, bandlimited waveforms, FM/PM, noise, envelopes
    ├── analysis.md             Analysis: FFT, DFT, Goertzel, envelope following, beat detection, LPC
    └── utilities.md            Utilities: fast math, interpolation, clipping, denormals, dithering, MIDI
```

#### What it covers

| Area | Details |
|------|---------|
| **Filter design** | RBJ/biquad cookbook (LP, HP, BP, notch, peaking, shelf), state variable (Dattorro, Chamberlin, double-sampled), Moog ladder (basic, nonlinear, RC-style), windowed-sinc FIR, Linkwitz-Riley crossover, DC blocker, formant filter, tilt EQ, parameter smoothing, all-pass |
| **Audio effects** | Static/feedback delay with cubic interpolation, reverb techniques (Schroeder to FDN), RMS compressor, lookahead limiter, 6-stage phaser, waveshapers (Bram de Jong, soft saturation, variable-hardness, gloubi-boulga, polynomial), decimator/bit-crusher, stereo width/rotation/enhancement, dynamic convolution, fold-back distortion |
| **Sound synthesis** | SVF/recurrence/Taylor/wavetable oscillators, bandlimited synthesis (sinc-train, additive mip-mapping, DSF BLIT, Tomisawa PWM), FM vs PM, noise (Gaussian Box-Muller, XOR-shift, pink auto-correlated), exponential/quadratic envelopes, Chebyshev waveshaping, MinBLEP generation, AM formantic synthesis, granular time-stretching, chaotic LFOs (Rossler/Lorenz) |
| **Spectral analysis** | DFT partial analysis, FFT overview, Walsh-Hadamard transform, Goertzel single-frequency detection, envelope detection (attack/release, RMS, peak), beat detection pipeline, LPC/Levinson-Durbin, binary-tree lookahead limiting, bit-reversed counting |
| **DSP utilities** | Fast exp/log/sin/sqrt approximations, IEEE 754 bit manipulation (abs/neg/sign/power/root), interpolation (linear, cubic, Hermite, spline), branchless clipping, denormal prevention (3 methods), triangular-PDF dithering with noise shaping, MIDI/frequency conversion, exponential parameter mapping, cycle-accurate benchmarking, lock-free FIFO |

#### Source documentation

- [musicdsp.org Archive](https://www.musicdsp.org/) — community-contributed DSP algorithms and code (2001-2012)

### vult-dsp

Write DSP algorithms in the Vult language — a transcompiled language designed for high-performance audio signal processing. Vult compiles to plain C/C++ (or JavaScript/Lua) and excels at writing audio effects, synthesizers, and real-time DSP for VCV Rack plugins, Teensy/Arduino microcontrollers, PureData externals, and WebAudio. The language's unique `mem` variable and implicit function context system eliminates the boilerplate of manual state management in DSP code.

**Triggers on:** Vult, vultc, Vult DSP code generation, audio DSP for VCV Rack with Vult, embedded audio on Teensy/Arduino with Vult, fixed-point audio DSP, transcompiling DSP to C/C++, Vult filters/oscillators/envelopes/effects, `.vult` files.

#### Structure

```
skills/vult-dsp/
├── SKILL.md                    Main skill instructions & DSP development workflow
└── references/
    ├── language-reference.md   Complete syntax: types, mem variables, function context, tags, arrays
    ├── dsp-patterns.md         DSP cookbook: biquad, ladder, SVF filters, oscillators, ADSR, LFO, delay, saturation
    └── code-generation.md      Compilation, C/C++ output, integration patterns, fixed-point, polyphony
```

#### What it covers

| Area | Details |
|------|---------|
| **Language syntax** | Static typing with inference, `int`/`real`/`bool`/`unit`, explicit casting, `val`/`mem` variables |
| **Function context** | Implicit state via `mem`, named contexts for stereo/oversampling, `and` for shared state |
| **Filters** | Biquad (Direct Form 2), Audio EQ Cookbook lowpass, SVF (LP/HP/BP/notch), diode ladder (Euler/Heun) |
| **Oscillators** | Phase accumulator, saw, square, triangle, BLIT-based bandlimited |
| **Envelopes** | ADSR state machine with gate triggering, shape-selectable LFO with reset |
| **Effects** | Simple delay, feedback delay, soft saturation, decimator/bitcrusher |
| **Tags** | `@[init]` custom init, `@[table]` lookup tables, `@[wave]` WAV file embedding |
| **Oversampling** | 2x/4x patterns using named contexts, frequency scaling |
| **Pitch/frequency** | CV↔pitch↔frequency conversion, rate calculation with table optimizations |
| **Compilation** | `vultc` CLI: `-ccode`, `-jscode`, `-luacode`, `-real fixed`, `-template pd/teensy` |
| **Code generation** | C/C++ naming conventions, context types, return value access, runtime files |
| **Integration** | VCV Rack (RackPlayground), JUCE/audio plugins, Teensy Audio, Arduino, PureData, WebAudio |
| **Fixed-point** | q16.16 format, range/scaling strategies, mixed float/fixed, `fix16` type |
| **Polyphony** | Context struct arrays, voice sharing optimizations |

#### Source documentation

- [Vult Language Reference](https://github.com/vult-dsp/vult/wiki/Language-Reference) — official syntax guide
- [Vult Tutorials](https://vult-dsp.github.io/vult/tutorials/) — basics through advanced DSP
- [Vult Examples](https://github.com/vult-dsp/vult/tree/master/examples) — filters, oscillators, envelopes, effects, utilities
- [Vult Compiler (GitHub)](https://github.com/vult-dsp/vult) — compiler source and releases
- [VCV Rack Playground](https://github.com/vult-dsp/RackPlayground) — Vult + VCV Rack template
