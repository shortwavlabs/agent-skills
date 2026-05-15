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
