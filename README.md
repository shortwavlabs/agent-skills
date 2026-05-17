# agent-skills

AI coding agent skills for audio development workflows.

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
