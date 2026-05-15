# Object Catalog

plugdata provides 1,653 objects across 8 libraries. This reference covers the most important objects organized by category.

## Library Overview

| Library | Count | Description |
|---------|-------|-------------|
| ELSE | 573 | High-level audio abstractions, effects, modules |
| Gem | 529 | 3D graphics, OpenGL, video processing |
| cyclone | 223 | Max/MSP compatibility |
| vanilla | 294 | Core Pure Data objects |
| heavylib | 29 | Heavy compiler-specific |
| pdlua | 2 | Lua scripting |
| plugdata | 3 | DAW integration |

---

## Oscillators & Sound Sources

### Vanilla
- `osc~ [freq]` — Cosine wave oscillator (default 0 Hz)
- `phasor~ [freq]` — Sawtooth phasor (0 to 1 ramp)
- `noise~` — White noise
- `tabosc4~ [tablename]` — Wavetable oscillator (4-point interpolation)

### ELSE (bandlimited, anti-aliased)
- `saw~ [freq]` — Sawtooth wave
- `tri~ [freq]` — Triangle wave
- `pulse~ [freq]` — Pulse wave
- `square~ [freq]` — Square wave
- `bl.saw~`, `bl.tri~`, `bl.square~`, `bl.imp~` — Bandlimited versions
- `impulse~ [freq]` — Impulse wave
- `cosine~ [freq]` — Cosine (same as osc~ but clearer name)

### ELSE Noise
- `white~` — White noise
- `pink~` — Pink noise (1/f)
- `brown~` — Brown noise (1/f^2)
- `lfnoise~ [freq]` — Low-frequency noise
- `crackle~` — Crackle/pop noise
- `dust~ [density]` — Random impulses
- `perlin~` — Perlin noise

### ELSE Advanced
- `plaits~` — Mutable Instruments Plaits macro-oscillator emulation
- `sine~ [freq]` — Sine wave
- `parabolic~ [freq]` — Parabolic wave

---

## Filters

### Vanilla
- `lop~ [freq]` — One-pole lowpass
- `hip~ [freq]` — One-pole highpass
- `bp~ [freq] [q]` — Bandpass (2-pole)
- `vcf~ [q]` — Voltage-controlled filter (bandpass/lowpass)
- `biquad~ [b0] [b1] [b2] [a1] [a2]` — General biquad IIR
- `svf~ [freq] [q]` — State-variable filter (cyclone)

### ELSE
- `lowpass~ [freq] [q]` — Lowpass filter
- `highpass~ [freq] [q]` — Highpass filter
- `bandpass~ [freq] [q]` — Bandpass filter
- `bandstop~ [freq] [q]` — Bandstop/notch filter
- `allpass.filt~ [freq] [q]` — Allpass filter
- `eq~ [freq] [gain] [q]` — Parametric EQ
- `resonator~ [freq] [q]` — Resonator
- `resonbank~` — Bank of resonators
- `brickwall~ [freq]` — Brick-wall filter
- `lowshelf~ [freq] [gain]` — Low shelf EQ
- `highshelf~ [freq] [gain]` — High shelf EQ
- `svfilter~ [freq] [q]` — State-variable filter with multiple outputs

---

## Effects

### Reverb
- `rev1~`, `rev2~`, `rev3~` — Vanilla reverbs (simple to complex)
- `free.rev~` — Free reverb (ELSE)
- `giga.rev~` — Giga reverb (ELSE)
- `plate.rev~` — Plate reverb (ELSE)
- `echo.rev~` — Echo reverb (ELSE)
- `fdn.rev~` — Feedback delay network reverb (ELSE)
- `stereo.rev~` — Stereo reverb (ELSE)
- `mono.rev~` — Mono reverb (ELSE)
- `hv.reverb~` — Heavy-compatible reverb (heavylib)

### Delay
- `delwrite~ [name] [maxsize]` — Write to delay line
- `delread~ [name] [delay]` — Read from delay line
- `delread4~ [name] [delay]` / `vd~` — 4-point interpolating delay read
- `delay~ [delay] [maxsize]` — Simple delay (cyclone)

### Modulation
- `chorus~ [rate] [depth]` — Chorus (ELSE)
- `flanger~ [rate] [depth]` — Flanger (ELSE)
- `phaser~ [rate] [depth]` — Phaser (ELSE)
- `freq.shift~ [freq]` — Frequency shifter (ELSE)
- `pitch.shift~ [shift]` — Pitch shifter (ELSE)
- `rm~ [freq]` — Ring modulator (ELSE)

### Distortion & Dynamics
- `drive~ [drive]` — Soft-clip distortion (ELSE)
- `compress~ [thresh] [ratio] [attack] [release]` — Compressor (ELSE)
- `duck~` — Sidechain ducker (ELSE)
- `crusher~ [bits] [rate]` — Bitcrusher/decimator (ELSE)
- `clip~ [min] [max]` — Signal clipper (vanilla)

---

## Envelopes & Modulation

### Vanilla
- `line~` — Linear ramp generator (message: `[target duration]`)
- `vline~` — High-precision ramp (supports delays and offsets)
- `env~` — Envelope follower (RMS)

### ELSE
- `adsr~ [attack] [decay] [sustain] [release]` — ADSR envelope
- `asr~ [attack] [sustain] [release]` — ASR envelope
- `decay~ [time]` — Exponential decay
- `envgen~` — Multi-segment envelope generator
- `lag~ [time]` — Non-linear lag
- `slew~ [up] [down]` — Slew rate limiter
- `lfo~ [freq] [type]` — Low-frequency oscillator

---

## Math (Signal)

- `+~` / `-~` / `*~` / `/~` — Arithmetic
- `max~` / `min~` — Min/max of two signals
- `clip~ [lo] [hi]` — Clamp signal range
- `wrap~` — Wrap signal into 0-1 range
- `abs~` — Absolute value
- `sqrt~` / `exp~` / `log~` — Math functions
- `pow~ [exponent]` — Power
- `expr~` — Expression evaluation

---

## Math (Control)

- `+` / `-` / `*` / `/` / `%` — Arithmetic
- `>` / `<` / `>=` / `<=` / `==` / `!=` — Comparison
- `&&` / `||` / `!` — Logical
- `moses [low] [high]` — Range splitter
- `select [val]` / `sel` — Value matcher
- `change` — Filter repeated values
- `random [max]` — Random integer
- `expr` — Expression evaluation
- `mtof` — MIDI note to frequency
- `ftom` — Frequency to MIDI note
- `dbtopow` / `powtodb` — dB conversion
- `dbtorms` / `rmstodb` — dB RMS conversion

---

## Message Flow & Logic

- `trigger` / `t` — Message ordering and type conversion (e.g., `t b f` — bang then float)
- `pack` — Combine atoms into a list (e.g., `pack f f`)
- `unpack` — Split a list into atoms (e.g., `unpack f f f`)
- `route [type1] [type2] ...` — Route messages by first element
- `select` / `sel` — Match specific values
- `spigot` — Pass or block messages
- `pipe [delay]` — Delay a message
- `delay [delay]` — Delayed bang
- `metro [interval]` — Periodic bang (milliseconds)
- `float` / `f` — Store a number
- `int` / `i` — Store an integer
- `send` / `s` — Wireless send
- `receive` / `r` — Wireless receive
- `loadbang` — Bang when patch loads
- `bang` / `b` — Pass through bang
- `print` — Print to console
- `swap` — Swap two values

---

## MIDI

### Vanilla
- `notein` — MIDI note input (pitch, velocity, channel)
- `noteout` — MIDI note output
- `ctlin [cc] [channel]` — MIDI CC input
- `ctlout [cc] [channel]` — MIDI CC output
- `bendin [channel]` — Pitch bend input
- `bendout [channel]` — Pitch bend output
- `pgmin [channel]` — Program change input
- `pgmout [channel]` — Program change output
- `midiin` / `midiout` — Raw MIDI
- `makenote [delay] [vel]` — Generate note-off from note-on
- `stripnote` — Remove note-off messages

### ELSE
- `note.in` / `note.out` — Simplified MIDI note I/O
- `ctl.in [cc]` / `ctl.out [cc]` — Simplified MIDI CC
- `bend.in` / `bend.out` — Simplified pitch bend
- `pgm.in` / `pgm.out` — Simplified program change
- `touch.in` / `touch.out` — Aftertouch
- `ptouch.in` / `ptouch.out` — Polyphonic aftertouch
- `mpe.in` — MPE input
- `midi.in` / `midi.out` — Cooked MIDI I/O
- `midi.learn` — MIDI learn
- `panic` — All notes off

---

## Audio I/O

- `adc~ [ch1] [ch2] ...` — Audio input (microphone, line in)
- `dac~ [ch1] [ch2] ...` — Audio output (speakers, headphones)
- `inlet` / `inlet~` — Subpatch input
- `outlet` / `outlet~` — Subpatch output
- `send~` / `throw~` — Wireless signal send
- `receive~` / `catch~` — Wireless signal receive
- `readsf~` — Read soundfile (async)
- `writesf~` — Write soundfile (async)
- `soundfiler` — Read/write arrays from soundfiles

---

## Tables & Arrays

- `array define [name] [size]` — Define an array
- `table [name] [size]` — Define a table (invisible array)
- `tabread~ [name]` — Read from table (signal index)
- `tabread4~ [name]` — Read with 4-point interpolation
- `tabwrite~ [name]` — Write to table (signal index + value)
- `tabosc4~ [name]` — Wavetable oscillator
- `tabplay~ [name]` — Play table as sample
- `tabread [name]` — Read (control-rate)
- `tabwrite [name]` — Write (control-rate)
- `soundfiler` — Load/save soundfiles to arrays

---

## GUI Objects

### Vanilla
- `bng` — Bang button (click to send bang)
- `tgl` — Toggle (on/off)
- `nbx` — Number box
- `hsl` / `vsl` — Horizontal/vertical slider
- `vradio` / `hradio` — Radio button group
- `vu` — VU meter
- `cnv` — Canvas (visual container)

### ELSE (enhanced)
- `knob [min] [max]` — Rotary knob
- `button` — Click button
- `keyboard` — Piano keyboard
- `function` — Function/envelope editor
- `scope~` — Oscilloscope
- `scope3d~` — 3D oscilloscope
- `spectrograph~` — Spectrograph
- `meter~` / `meter2~` / `meter4~` / `meter8~` — VU meters (1-8 channels)
- `numbox~` — Signal number display
- `slider2d` — 2D slider
- `popmenu` — Popup menu
- `display` — Message display
- `messbox` — Message box GUI
- `presets` — Preset manager

---

## DAW Integration (plugdata-specific)

- `param [name] [default]` — Expose parameter to DAW automation
- `playhead` — Receive DAW transport/playhead info (tempo, position, bar, beat)
- `plugin_latency [samples]` — Set plugin latency compensation

---

## Timing & Sequencing

- `metro [ms]` — Periodic bang generator
- `delay [ms]` — Delayed bang
- `timer` — Measure time between two bangs
- `pipe [delay]` — Delay any message
- `tempo [bpm]` — Tempo-based metronome (ELSE)
- `sequencer~` — Signal sequencer (ELSE)
- `score` — Score sequencer (ELSE)
- `pattern` — Rhythmic pattern (ELSE)
- `euclid [steps] [hits]` — Euclidean rhythm generator (ELSE)

---

## ELSE Module Objects (with built-in GUI)

These are abstraction-based modules with integrated GUI controls:

- `plaits~` — Macro-oscillator
- `chorus.m~` — Chorus module
- `flanger.m~` — Flanger module
- `phaser.m~` — Phaser module
- `delay.m~` — Delay module
- `drive.m~` — Drive/distortion module
- `vco.m~` — Voltage-controlled oscillator module
- `vcf.m~` — Voltage-controlled filter module
- `vca.m~` — Voltage-controlled amplifier module
- `pluck.m~` — Plucked string module
- `adsr.m~` — ADSR envelope module
- `plate.rev.m~` — Plate reverb module
- `lfo.m~` — LFO module
- `seq8.m~` — 8-step sequencer module
- `drum.seq` — Drum sequencer
- `crusher.m~` — Bitcrusher module

---

## Heavy-Compatible Objects (hvcc compilation)

Only these objects work when compiling patches with the Heavy compiler. See `hvcc.md` for details.

### vanilla objects supported by hvcc
`+`, `-`, `*`, `/`, `%`, `>`, `<`, `>=`, `<=`, `==`, `!=`, `&`, `|`, `^`, `&&`, `||`, `<<`, `>>`, `mod`, `div`, `pow`, `abs`, `sqrt`, `exp`, `log`, `sin`, `cos`, `tan`, `atan`, `atan2`, `trigger`, `t`, `pack`, `unpack`, `route`, `select`, `sel`, `spigot`, `change`, `moses`, `swap`, `pipe`, `float`, `f`, `int`, `i`, `symbol`, `table`, `tabread`, `tabwrite`, `send`, `s`, `receive`, `r`, `delay`, `del`, `metro`, `timer`, `loadbang`, `bang`, `b`, `print`, `random`, `clip`, `max`, `min`, `line`, `until`, `poly`, `makenote`, `stripnote`, `wrap`, `inlet`, `outlet`, `declare`, `cnv`, `floatatom`, `nbx`, `vsl`, `hsl`, `bng`, `tgl`, `expr`

### Signal objects supported by hvcc
`+~`, `-~`, `*~`, `/~`, `max~`, `min~`, `pow~`, `osc~`, `phasor~`, `noise~`, `cos~`, `lop~`, `hip~`, `bp~`, `biquad~`, `vcf~`, `rpole~`, `rzero~`, `rzero_rev~`, `cpole~`, `czero~`, `czero_rev~`, `delwrite~`, `delread~`, `delread4~`, `vd~`, `line~`, `env~`, `samphold~`, `mtof~`, `ftom~`, `dbtopow~`, `dbtorms~`, `powtodb~`, `rmstodb~`, `wrap~`, `abs~`, `exp~`, `sqrt~`, `rsqrt~`, `clip~`, `samplerate~`, `sig~`, `adc~`, `dac~`, `inlet~`, `outlet~`, `send~`, `s~`, `receive~`, `r~`, `throw~`, `catch~`, `tabread~`, `tabread4~`, `tabwrite~`, `tabplay~`, `tabosc4~`, `snapshot~`, `bang~`, `block~`

### heavylib objects
`hv.comb~`, `hv.compressor~`, `hv.compressor2~`, `hv.dispatch`, `hv.drunk`, `hv.envfollow~`, `hv.eq~`, `hv.exp~`, `hv.filter~`, `hv.filter.gain~`, `hv.flanger~`, `hv.flanger2~`, `hv.freqshift~`, `hv.gt~`, `hv.gte~`, `hv.hip~`, `hv.lfo`, `hv.log~`, `hv.lop~`, `hv.lt~`, `hv.lte~`, `hv.multiplex~`, `hv.neq~`, `hv.osc~`, `hv.pinknoise~`, `hv.pow~`, `hv.reverb~`, `hv.tanh~`, `hv.vline~`
