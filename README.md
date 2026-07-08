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
    ├── cmake-reference.md      Full CMake API: juce_add_plugin, SDK paths, CI/CD, platform specifics
    └── production-plugin-practices.md  Product plugin practices: validation, assets, state restore
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
| **Production practices** | Separate plugin/test/measurement builds, asset/model loading, state restore, host validation, release gates |

#### Source documentation

- [JUCE Framework](https://juce.com/) — C++ audio plugin framework by Raw Material Software
- [JUCE CMake API](https://github.com/juce-framework/JUCE/blob/master/docs/CMake%20API.md) — build system reference
- [JUCE Examples](https://github.com/juce-framework/JUCE/tree/master/examples) — official plugin and DSP examples
- [JUCE Development Forum](https://forum.juce.com/c/development/21) — community Q&A and best practices
- [JUCE Tutorials](https://juce.com/learn/tutorials/) — official tutorials on plugins, DSP, synth, MIDI, GUI, and more
- [Pamplejuce](https://github.com/sudara/pamplejuce) — community CMake template for production plugins

### guitar-dsp

Design, implement, debug, train, and validate guitar amp/effects DSP systems. Covers realtime guitar plugin architecture, C++/JUCE DSP block modeling, nonlinear waveshaping, aliasing/oversampling, tone stacks, diode/fuzz circuits, tube-stage approximations, speaker cabinet dynamics, RTNeural/neural amp modeling, capture and export workflows, cabinet IRs, pedal chains, validation, and release checks.

**Triggers on:** guitar amp modelers, pedal emulations, neural audio model training/export, RTNeural loaders, cabinet simulators, tone stacks, diode clippers, fuzz circuits, tube stages, speaker dynamics, C++/JUCE guitar DSP blocks, measurement harnesses, guitar plugin latency/CPU/aliasing/tone quality, neural modeling math, ESR/ASR/loss theory.

#### Structure

```
skills/guitar-dsp/
├── SKILL.md                         Main workflow and reference routing
├── scripts/
│   ├── alias_probe_report.py         Harmonic/non-harmonic energy from sine renders
│   ├── compare_audio_metrics.py      WAV alignment, polarity, residual, ESR, correlation metrics
│   ├── model_package_summary.py      RTNeural package/model summary and warnings
│   └── receptive_field.py            Conv1D receptive-field calculator
└── references/
    ├── aliasing-oversampling.md      Aliasing diagnosis, oversampling islands, ADAA, alias probes
    ├── cpp-juce-dsp-modeling.md      C++/JUCE block modeling lessons for guitar effects
    ├── diode-and-fuzz-circuits.md    Diode clipping, feedback solvers, fuzz bias/loading behavior
    ├── example-prompts.md            Realistic prompts for testing and demonstrating skill use
    ├── failure-diagnosis.md          Symptom-to-cause-to-check debugging matrix
    ├── guitar-signal-chain.md       Guitar chain, gain staging, mono/stereo policy, block tests
    ├── nonlinear-waveshaping.md      Transfer curves, dynamic shaping, gain staging, compensation
    ├── neural-modeling-workflow.md  Capture, alignment, training presets, export packages
    ├── neural-modeling-math.md      Causal TCN math, metrics, losses, ASR, runtime theory
    ├── rtneural-runtime.md          RTNeural loading, metadata, sample-rate and latency policy
    ├── runtime-code-patterns.md      C++ runtime patterns for snapshots, handoff, smoothing
    ├── speaker-cabinet-dynamics.md  Speaker compression, resonance, breakup, dynamic cabinet behavior
    ├── task-playbooks.md             Common guitar DSP workflows
    ├── tone-stack-modeling.md        Passive/active tone stacks, loading, smoothing, response tests
    ├── triode-and-tube-stage-approximation.md  Tube-like curves, memory, sag, power-stage behavior
    └── validation-and-release.md    Tests, benchmarks, plugin validation, DAW smoke gates
```

#### What it covers

| Area | Details |
|------|---------|
| **Signal chain** | Input trim, gate, compressor, drives, neural amp, tone stack, EQ, cabinet, modulation, delay, reverb, utility output |
| **C++/JUCE DSP modeling** | Parameter snapshots, smoothing, realtime-safe class shape, circuit-to-DSP translation, block tests, measurement fixtures |
| **Neural modeling** | Dry/target capture contracts, latency alignment, WaveNet-family preset selection, RTNeural export packages |
| **Math theory** | Causal finite-memory models, Conv1D receptive field, ESR/RMSE/correlation, checkpoint scoring, pre-emphasis/STFT losses, ASR, RTF |
| **Runtime integration** | Embedded factory models, user-loaded package folders, per-channel model state, metadata warnings, sample-rate policy |
| **Cabinet and effects** | IR loading, resampling, normalization policy, convolution latency, nonlinear pedal tests, automation safety |
| **Nonlinear DSP** | Waveshaping families, diode/fuzz circuits, tube-stage approximation, aliasing analysis, local oversampling islands, ADAA tradeoffs |
| **Tone and speaker modeling** | Passive/active tone stacks, insertion loss, speaker compression, resonance, breakup, dynamic cabinet behavior |
| **Diagnosis and validation** | Failure matrix, Python/native parity, native benchmarks, aliasing reports, DSP unit tests, measurement harnesses, auval/pluginval, DAW smoke |

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

### dsp-engineer

Think DSP-inspired signal-processing engineering guide for C++ implementations. Covers concept-first DSP workflows: Signal/Wave/Spectrum modeling, spectra, spectrograms, harmonics, aliasing, noise, autocorrelation, DCT/DFT, convolution, LTI systems, modulation, sampling, interpolation, and C++ translations of Think DSP's Python/NumPy examples.

**Triggers on:** Think DSP, translating DSP examples from Python/NumPy to C++, signal analysis, spectral decomposition, FFT/DFT/DCT explanations, spectrograms, autocorrelation pitch estimation, convolution theorem, impulse responses, sampling theorem, aliasing, modulation, educational DSP prototypes.

#### Structure

```
skills/dsp-engineer/
├── SKILL.md                         Main skill workflow and reference routing
├── references/
│   ├── thinkdsp-concepts.md         Chapter-by-chapter concept map from Think DSP
│   ├── cpp-patterns.md              C++ translations of core Think DSP examples
│   └── engineering-checks.md        Validation, scaling, aliasing, and production checks
└── assets/
    └── thinkdsp.hpp                 Self-contained educational C++ DSP header
```

#### What it covers

| Area | Details |
|------|---------|
| **DSP mental model** | Signal/Wave/Spectrum/Spectrogram object model, unit-first workflow, sample rate and bin spacing discipline |
| **Spectral analysis** | DFT/IDFT conventions, one-sided real spectra, harmonic structure, phase, DC handling, spectrogram resolution |
| **C++ translations** | Sine/cosine synthesis, triangle/square/sawtooth waves, chirps, windows, direct DFT, DCT-IV, convolution, filters, noise, autocorrelation, AM, sampling |
| **Signal phenomena** | Leakage, aliasing, Nyquist/folding frequency, Gabor limit, pink/Brownian noise slopes, spectral differentiation/integration |
| **Systems view** | Convolution theorem, LTI systems, impulse responses, transfer functions, linear versus circular convolution |
| **Engineering validation** | Round-trip tests, amplitude scaling checks, alias fold tests, pitch-lag tests, FFT replacement guidance, real-time safety notes |

#### Source documentation

- Think DSP by Allen B. Downey, Green Tea Press — CC BY-NC-SA 4.0

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

### faust-dsp

Write DSP algorithms in Faust — a functional, block-diagram programming language that compiles to optimized C/C++, WebAssembly, LLVM IR, Rust, and more. Covers the full Faust workflow from signal processing design to cross-platform deployment: VST/AU plugins, standalone JACK apps, PureData/Max externals, SuperCollider, Csound, WebAudio, iOS/Android, Bela, Teensy, ESP32, and JUCE integration. The skill covers Faust's five composition operators, standard libraries (30+ libraries with 500+ functions), UI primitives, MIDI/polyphony, and the complete compilation pipeline.

**Triggers on:** Faust, faust code, `.dsp` files, functional audio programming, block-diagram DSP, faust2xx scripts, compiling DSP to audio plugins, cross-platform audio from a single source, signal processing block diagrams, any real-time audio DSP task that could be expressed functionally.

#### Structure

```
skills/faust-dsp/
├── SKILL.md                    Main skill instructions & Faust development workflow
└── references/
    ├── dsp-patterns.md         DSP cookbook: oscillators, filters, delays, dynamics, modulation, distortion, reverb, synthesis, envelopes, analysis
    ├── libraries.md            Standard library reference: 30+ libraries (basics, maths, oscillators, filters, delays, reverbs, envelopes, compressors, etc.)
    └── compilation.md          Compiler options, faust2xx scripts, architecture files, plugin targets, code generation modes
```

#### What it covers

| Area | Details |
|------|---------|
| **Language syntax** | Five composition operators (parallel, sequential, split, merge, recursive), iterations (par/seq/sum/prod), pattern matching, lexical environments (`with`, `environment`, `letrec`), foreign functions |
| **Primitives** | Numbers, identity (`_`), cut (`!`), delay (`@`, `'`), tables (rdtable, rwtable), waveform, soundfile, route, select2/3, math.h equivalents |
| **Standard libraries** | 30+ libraries via stdfaust.lib: oscillators, filters, delays, reverbs, envelopes, compressors, noises, signals, analyzers, physical models, DX7, wavetable, ambisonics, and more |
| **DSP patterns** | Oscillators (sine, saw, square, wavetable), filters (one-pole, resonant, SVF, Moog, parametric EQ, Butterworth), delay/echo/comb, dynamics (compressor, limiter, gate), modulation (chorus, flanger, phaser, tremolo, vibrato), distortion (soft/hard clip, bitcrusher), reverb (Zita, Freeverb, Schroeder), synthesis (additive, FM, Karplus-Strong, subtractive, physical modeling), envelopes (AR, ADSR) |
| **User interface** | UI primitives (hslider, vslider, nentry, button, checkbox, groups, bargraphs), metadata for styling, parameter smoothing with `si.smoo` |
| **MIDI & polyphony** | MIDI CC/note/velocity/pitchwheel mapping, polyphonic voice allocation, `freq`/`gain`/`gate` standard params, shared `effect` line, sustain pedal |
| **Compilation** | `faust` CLI options, code generation modes (scalar, vector, OpenMP, scheduler), precision (single/double/quad/fixed-point) |
| **Targets** | VST2, AU, LV2, JACK, ALSA, CoreAudio, PureData, Max/MSP, SuperCollider, Csound, WebAudio/WASM, iOS, Android, Bela, Teensy, ESP32, Raspberry Pi, JUCE, Unity, Cmajor, JSFX, RNBO |
| **faust2xx scripts** | 30+ one-step compilation scripts: faust2faustvst, faust2au, faust2jaqt, faust2puredata, faust2supercollider, faust2android, faust2ios, faust2bela, faust2api, etc. |
| **Architecture files** | Audio driver + GUI bridges: ALSA, JACK, CoreAudio, VST, AU, LV2, WebAudio, Android, iOS, Bela; embedding via libfaust LLVM JIT |

#### Source documentation

- [Faust Documentation](https://faustdoc.grame.fr/) — official manual, syntax reference, compiler guide, tutorials
- [Faust Libraries](https://faustlibraries.grame.fr/) — complete library function reference (30+ libraries)
- [Faust GitHub](https://github.com/grame-cncm/faust) — compiler source, examples, architecture files
- [Faust Examples](https://faustdoc.grame.fr/examples/) — categorized examples (ambisonics, reverb, physical modeling, etc.)
- [Faust Wiki](https://github.com/grame-cncm/faust/wiki) — tutorials, platform-specific guides, workshops
