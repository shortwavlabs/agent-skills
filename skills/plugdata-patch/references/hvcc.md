# Heavy Compiler (hvcc) Reference

hvcc compiles Pure Data `.pd` patches into optimized C/C++ code. It's integrated into plugdata as the "Compiled Mode" feature.

## Compilation Pipeline

```
.pd patch → heavylang IR → heavyir → C/C++ source → target wrapper
```

The compiler statically interprets the patch — it does NOT use libpd or any Pd runtime. Audio processes in single-sample blocks (block~ is ignored).

## Invocation

```bash
hvcc _main.pd -o output/ -n ProjectName -g c dpf
```

- First arg: top-level `.pd` file
- `-o` / `--out_dir`: output directory
- `-n` / `--name`: namespace for generated code
- `-g` / `--gen`: generators to use
- `-p` / `--search_paths`: additional paths for abstractions

## Compilation Targets

| Generator | Output |
|-----------|--------|
| `c` | Generic C/C++ source code |
| `unity` | Unity audio plugin |
| `wwise` | Wwise audio plugin |
| `js` | JavaScript / Web Audio |
| `dpf` | DPF plugin (VST2, VST3, LV2, CLAP, AU, JACK) |
| `daisy` | Electro-Smith Daisy embedded |
| `daisy_json` | Daisy with JSON config |
| `fmod` | FMOD audio plugin |
| `owl` | OWL audio plugin |
| `pdext` | Pure Data external (.pd_linux/.dll/.pd_darwin) |
| `custom` | Custom generator |

## Parameter Annotations

### Input Parameters (Plugin UI Controls)

```
[r NAME @hv_param MIN MAX DEFAULT [TYPE]]
```

- `NAME` becomes the parameter name in the plugin UI
- `MIN`, `MAX` — parameter range
- `DEFAULT` — initial value
- `TYPE` (optional): `float`, `bool`, `int`, `trig`, `dB`, `Hz`, `log`, `log_hz`

Example:
```pd
#X obj 200 50 r cutoff @hv_param 20 20000 1000 Hz;
#X obj 200 100 sig~;
#X obj 100 150 lop~;
```

### Output Parameters (Send Data Out)

```
[s NAME @hv_param]
```

### Events (Unity/JS)

```
[r NAME @hv_event]
```

### Externed Tables

```
[table NAME SIZE @hv_table]
```

## Critical Design Rules for hvcc Compatibility

1. **Keep processing in signal domain** — Use `~` (tilde) objects as much as possible. Control-rate operations introduce interruptions and delay.

2. **Convert control to signal** — Use `[sig~]` before connecting control values to signal inlets:
   ```pd
   #X obj 200 50 r freq @hv_param 20 20000 440 Hz;
   #X obj 200 100 sig~;
   #X obj 100 150 osc~;
   ```
   `[osc~]` always requires `[sig~]` for non-constant frequency input.

3. **Use `[trigger]` for execution order** — `[t b f]` or `[t f b]` to enforce correct message ordering.

4. **No spaces in table/array names.**

5. **`[block~]` is ignored** — always single-sample processing.

6. **`[expr]` / `[expr~]`** — Only a single expression, limited function set. No `size()`, `sum()`, `avg()`, `mtof()`, `ftom()`, etc.

7. **`[unpack]`** — Only supports `f` and `s` arguments (no initialized values like `[unpack 0 0]`).

8. **`[select]` / `[route]`** — Right inlet is not functional for dynamic re-configuration.

9. **No multichannel connections.**

10. **`[snapshot~]`** — Output happens on next audio cycle, not synchronous.

11. **`[delay]`, `[metro]`, `[timer]`** — No tempo messages or unit arguments.

12. **Remote send messages** — `[; bla 1(` needs at least something on the first line: `[_; bla 1(`.

## Supported Objects (Complete List)

### Control (Message) Objects (~90+)

**Arithmetic/Logic:** `+`, `-`, `*`, `/`, `%`, `>`, `<`, `>=`, `<=`, `==`, `!=`, `&`, `|`, `^`, `&&`, `||`, `<<`, `>>`, `mod`, `div`, `pow`, `abs`, `sqrt`, `exp`, `log`, `sin`, `cos`, `tan`, `atan`, `atan2`

**Data flow:** `trigger`/`t`, `pack`, `unpack` (only `f` and `s`), `route` (right inlet unsupported), `select`/`sel` (right inlet unsupported), `spigot`, `change`, `moses`, `swap`, `pipe`

**Values:** `float`/`f`, `int`/`i`, `symbol`, `table`, `tabread`, `tabwrite`

**Send/Receive:** `send`/`s`, `receive`/`r` (with `@hv_param` and `@hv_event`)

**Timing:** `delay`/`del`, `metro`, `timer`, `loadbang`, `bang`

**Conversion:** `mtof`, `ftom`, `dbtopow`, `dbtorms`, `powtodb`, `rmstodb`

**MIDI (DPF/Daisy/OWL only):** `notein`, `noteout`, `ctlin`, `ctlout`, `pgmin`, `pgmout`, `bendin`, `bendout`, `touchin`, `touchout`, `polytouchin`, `polytouchout`, `midiin`, `midiout`, `midirealtimein`

**Misc:** `print`, `random`, `clip`, `max`, `min`, `line`, `until`, `poly`, `makenote`, `stripnote`, `wrap`, `inlet`, `outlet`, `declare`, `cnv`, `expr`

**GUI (converted to `[f ]`):** `nbx`, `vsl`, `hsl`, `vradio`, `hradio`, `floatatom`
**GUI (with send/receive):** `bng`, `tgl`

### Signal (Audio) Objects (~60+)

**Arithmetic:** `+~`, `-~`, `*~`, `/~`, `max~`, `min~`, `pow~`

**Oscillators:** `osc~`, `phasor~`, `noise~`, `cos~`

**Filters:** `lop~`, `hip~`, `bp~`, `biquad~`, `vcf~`, `rpole~`, `rzero~`, `rzero_rev~`, `cpole~`, `czero~`, `czero_rev~`

**Delay:** `delwrite~`, `delread~`, `delread4~`/`vd~`

**Envelopes:** `line~`, `env~`, `samphold~`

**Conversion:** `mtof~`, `ftom~`, `dbtopow~`, `dbtorms~`, `powtodb~`, `rmstodb~`, `wrap~`

**Math:** `abs~`, `exp~`, `sqrt~`, `rsqrt~`, `clip~`, `samplerate~`, `sig~`

**I/O:** `adc~`, `dac~`, `inlet~`, `outlet~`, `send~`/`s~`, `receive~`/`r~`, `throw~`, `catch~`

**Tables:** `tabread~`, `tabread4~`, `tabwrite~`, `tabplay~`, `tabosc4~`

**Analysis:** `snapshot~`, `bang~`

**Other:** `block~` (allowed but ignored)

### Cyclone Signal Objects (hvcc-supported)
`acos~`, `acosh~`, `asin~`, `asinh~`, `atan~`, `atan2~`, `atanh~`, `cosh~`, `sinh~`, `tanh~`, `sinx~`, `cosx~`, `tanx~`, `cartopol~`, `poltocar~`, `equals~`/`==~`, `greaterthan~`/`>~`, `lessthan~`/`<~`, `bitand~`, `bitor~`, `bitxor~`, `bitnot~`, `bitsafe~`

### Supported Abstractions
`rev1~`, `rev2~`, `rev3~` (reverbs), `else/above`, `else/add`, `else/avg`, `else/car2pol`

### heavylib Objects (29)
`hv.comb~`, `hv.compressor~`, `hv.compressor2~`, `hv.dispatch`, `hv.drunk`, `hv.envfollow~`, `hv.eq~`, `hv.exp~`, `hv.filter~`, `hv.filter.gain~`, `hv.flanger~`, `hv.flanger2~`, `hv.freqshift~`, `hv.gt~`, `hv.gte~`, `hv.hip~`, `hv.lfo`, `hv.log~`, `hv.lop~`, `hv.lt~`, `hv.lte~`, `hv.multiplex~`, `hv.neq~`, `hv.osc~`, `hv.pinknoise~`, `hv.pow~`, `hv.reverb~`, `hv.tanh~`, `hv.vline~`

## Minimal Compilable Patch

```pd
#N canvas 0 0 450 300 12;
#X obj 100 50 osc~ 440;
#X obj 100 120 *~ 0.5;
#X obj 200 50 r gain @hv_param 0 1 0.5;
#X obj 200 90 sig~;
#X obj 100 200 dac~ 1 2;
#X connect 0 0 1 0;
#X connect 1 0 4 0;
#X connect 2 0 3 0;
#X connect 3 0 1 1;
```

## DPF Plugin Configuration

When generating DPF plugins, configure via metadata JSON or plugdata UI:

- **Plugin type:** Effect (processes audio input), Instrument (MIDI input), Custom
- **Formats:** VST2, VST3, LV2, CLAP, JACK
- **Export type:** Source code or pre-built binary
- **Project name** and **copyright** (optional SPDX identifier)

## Daisy Configuration

- **Board selection:** Daisy Seed, Patch, Patch Init, etc.
- **Export type:** Source, Binary, or Flash (directly program the board)
- **USB MIDI:** Enable/disable
- **Patch size:** Memory allocation for the patch
