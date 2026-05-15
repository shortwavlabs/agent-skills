# Cyclone Library Reference

Cyclone is a library of Pure Data objects cloned from Cycling '74's Max/MSP. It provides compatibility for migrating Max patches to Pd. **Included in plugdata** — no separate installation needed.

- **Repository**: https://github.com/porres/pd-cyclone
- **License**: BSD-3-Clause
- **Compatibility**: Targets Max 7.3.5
- **Current version**: 0.9-4 (February 2026)
- **Status**: Maintenance mode (bug fixes only, primary maintainer focuses on ELSE)

## Loading

In plugdata, Cyclone is loaded automatically. In vanilla Pd:
```
[declare -path cyclone]
[declare -lib cyclone]   // loads non-alphanumeric operators
```

The library binary must be loaded to use non-alphanumeric operator objects (`!-`, `==~`, `%~`, etc.).

## Key Differences from Vanilla Pd

| Cyclone | Vanilla Equivalent | Key Difference |
|---------|-------------------|----------------|
| `loadmess` | `loadbang` | Sends typed message, not just bang |
| `pak` | `pack` | Outputs on ANY inlet change (not just left/hot) |
| `line~` | `line~` | Cyclone supports multi-segment ramps |
| `gate` | `spigot` | N-to-1 routing (spigot is 1-to-1 pass/block) |
| `switch` | `route` | Input selection (route matches on content) |
| `zl` | list ops | 30+ list processing modes in one object |
| `buffer~` | `array` | Max-style sample buffer |

## Non-Alphanumeric Operators

These objects are compiled into the library binary (cannot be separate files due to filesystem naming restrictions). Each has an alphanumeric alias.

| Symbol | Alias | Description |
|--------|-------|-------------|
| `!-` | `rminus` | Reverse subtraction (R - L) |
| `!-~` | `rminus~` | Reverse subtraction (signal) |
| `!/` | `rdiv` | Reverse division (R / L) |
| `!/~` | `rdiv~` | Reverse division (signal) |
| `!=~` | `neq~` | Not equal (signal) |
| `%~` | `modulo~` | Modulo (signal) |
| `+=~` | `plusequals~` | Add and assign (signal) |
| `<=~` | `lte~` | Less than or equal (signal) |
| `<~` | `lt~` | Less than (signal) |
| `==~` | `equals~` | Equal (signal) |
| `>=~` | `gte~` | Greater than or equal (signal) |
| `>~` | `gt~` | Greater than (signal) |

All can be namespaced: `cyclone/!-~`, `cyclone/equals~`, etc.

## Control Objects (~93 objects)

### Data Management
- `accum` — Accumulate with increment/reset
- `bag` — Collect data pairs
- `bucket` — Shift register (pass values left-to-right)
- `capture` — Capture messages to a text buffer
- `coll` — Indexed data collection (key-value pairs)
- `counter` — Multi-mode counter (up/down/ud/routine)
- `cycle` — Cycle through a list of values
- `decode` — One-hot decode (1 of N)
- `dict` — Dictionary (key-value) — **limited, no full Max dict support**
- `funbuff` — Function buffer (x,y pairs)
- `histo` — Histogram
- `iterate` — Iterate over incoming data
- `mean` — Running mean
- `peak` / `trough` — Track max/min values
- `spell` — Convert to ASCII codes
- `table` — Named data table (different from vanilla `table`)

### List Processing
- `append` — Append to list
- `group` — Group items into list
- `join` — Join multiple lists
- `prepend` — Prepend to list/message
- `sort` — Sort list
- `zl` — Swiss-army knife: 30+ modes (group, slice, iter, sort, scramble, sum, etc.)

### Flow Control
- `bangbang` — Multiple bang outlets
- `bondo` — Synchronize multiple inlets
- `buddy` — Wait for all inputs
- `gate` — N-to-1 switch
- `match` — Match message patterns
- `onebang` — Pass one bang then block
- `past` — Trigger when value exceeds threshold
- `spray` — 1-to-N distribution
- `switch` — Select between multiple inputs
- `toggledump` — Toggle through outputs
- `universal` — Send to all patches

### Sequencing & Timing
- `mtr` — Multi-track recorder/player (**not yet updated to Max 7.3.5**)
- `seq` — MIDI sequencer
- `tempo` — Tempo-based timing
- `uzi` — Rapid-fire bang (N times)

### Logic & Comparison
- `decide` — Random yes/no
- `prob` — Weighted random
- `urn` — Random without replacement

### Data Formatting
- `fromsymbol` / `tosymbol` — Convert between symbols and other types
- `sprintf` — Format string
- `subst` / `substitute` — String substitution

### Mouse & Input
- `active` — Report active window/patcher
- `mousefilter` — Filter mouse events
- `mousestate` — Track mouse position/buttons

### Special
- `flush` — Send bang to all connected objects
- `forward` — Send message to named object
- `grab` — Get value from named object
- `offer` — Offer value to named object
- `pv` — Persistent variable
- `next` — Sequential value output
- `linedrive` — Scale with exponential curve
- `speedlim` — Rate limiter
- `funnel` — Combine values with inlet number prefix

## Signal Objects (~101 objects)

### Math & Trigonometry
- `acos~` / `acosh~` / `asin~` / `asinh~` / `atan~` / `atan2~` / `atanh~`
- `cosx~` / `cosh~` / `sinx~` / `sinh~` / `tanx~` / `tanh~`
- `average~` — Moving average (bipolar/rms/magnitude)
- `count~` — Counting signal
- `delta~` — First difference
- `downsamp~` — Downsample signal
- `pow~` — Power function
- `round~` — Round to nearest multiple
- `rampsmooth~` — Smooth with ramp
- `slide~` — Exponential smoothing (like lag)
- `deltaclip~` — Limit rate of change
- `pong~` — Bounce/fold within range

### Comparison (Signal)
- `==~` / `>~` / `<~` / `>=~` / `<=~` — Comparison operators
- `change~` — Detect signal change
- `edge~` — Signal to bang (zero crossing)
- `equals~` / `greaterthan~` / `lessthan~` — Comparison (alphanumeric aliases)

### Bitwise (Signal)
- `bitand~` / `bitor~` / `bitxor~` / `bitnot~` / `bitshift~` / `bitsafe~`

### Filters
- `comb~` — Comb filter
- `lores~` — Resonant lowpass (like Max)
- `reson~` — Resonant bandpass
- `teeth~` — Comb with delay and feedback
- `allpass~` — Allpass filter
- `phaseshift~` — Phase shift
- `onset~` — Onset detection

### Delay & Effects
- `delay~` — Simple delay
- `tapin~` / `tapout~` — Tap delay (Max style)
- `overdrive~` — Distortion
- `phaser~` — Phaser effect

### Envelopes & Dynamics
- `curve~` — Curve envelope generator
- `line~` — Multi-segment ramp (enhanced over vanilla)
- `train~` — Pulse train generator
- `trapezoid~` — Trapezoidal envelope
- `triangle~` — Triangle wave (control rate)

### Conversion
- `cartopol~` / `poltocar~` — Cartesian/polar conversion
- `atodb~` / `dbtoa~` — Amplitude/dB conversion
- `mstosamps~` / `samps2ms~` — Time/sample conversion
- `phasewrap~` — Wrap phase to -pi..pi
- `avedev~` — Average deviation

### Buffers & Playback
- `buffer~` — Sample buffer (abstraction)
- `play~` — Play from buffer
- `record~` — Record to buffer
- `poke~` — Write to buffer by index
- `peek~` — Read from buffer by index
- `index~` — Read by signal index
- `lookup~` — Lookup table
- `wave~` — Wavetable from buffer
- `sfplay~` / `sfrecord~` — Soundfile play/record

### Analysis
- `snapshot~` — Signal to float
- `minmax~` — Track min/max
- `peakamp~` — Peak amplitude
- `zerox~` — Zero crossing counter
- `average~` — Signal averaging

### Routing & Mixing
- `gate~` — Signal router
- `matrix~` — Signal matrix
- `selector~` — Signal selector
- `mixdown~` — Channel mixing

### Scaling & Limiting
- `scale~` — Scale signal range
- `clip~` — Signal clip
- `pong~` — Bounce within range
- `maximum~` / `minimum~` — Signal min/max

## GUI Objects

- `scope~` — Oscilloscope display
- `number~` — Signal number display (abstraction)
- `comment` — Enhanced comment (**deprecated, based on ELSE's `note`**)
- `active` — Window/patcher active indicator
- `mousestate` — Mouse position display
- `mousefilter` — Mouse event filter

## The `zl` Object

`zl` is a polymorphic list processor with 30+ modes. Usage: `zl [mode] [args]`

Common modes: `change`, `compare`, `delace`, `ecils`, `group`, `indexmap`, `iter`, `join`, `lace`, `len`, `lookup`, `median`, `mth`, `nth`, `queue`, `reg`, `rev`, `rot`, `sect`, `scramble`, `slice`, `sort`, `stack`, `stream`, `sub`, `sum`, `swap`, `thin`, `union`, `unique`

Example:
```pd
#X obj 100 100 zl group 4;   // group list elements into sublists of 4
#X obj 100 200 zl sort;       // sort a list
#X obj 100 300 zl rev;        // reverse a list
```

## Not Implemented from Max

These Max features will **never** be implemented in Cyclone:
- **transport** — Max's global transport system
- **dictionaries** — Max's dict object system
- **MC (multichannel)** — No plans for multichannel versions (only `tanh~` has MC support via ELSE)

## When to Use Cyclone vs ELSE

- **Use Cyclone** when porting existing Max/MSP patches to Pd
- **Use ELSE** for new development — it's more actively maintained, has more features, and better plugdata integration
- Many Cyclone objects are now borrowed from ELSE (`pink~`, `tanh~`, `comment`) with backwards compatibility
- See `references/else.md` for the full ELSE-to-Cyclone migration table
