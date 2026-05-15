# ELSE Library Reference

ELSE (EL Locus Solus' Externals) is a 595-object library by Alexandre Torres Porres that extends Pure Data with high-level audio objects, effects, synthesizers, and GUI tools. It is **included in plugdata** and requires no separate installation.

- **Repository**: https://github.com/porres/pd-else
- **License**: WTFPL (with some objects under GPL, BSD, or MIT)
- **Requires**: Pd 0.56-2 or later
- **Status**: Release Candidate (pre-1.0, actively developed)

ELSE also ships a **Live Electronics Tutorial** — a comprehensive learning resource that uses only ELSE objects.

## Loading

In plugdata, ELSE is loaded automatically. In vanilla Pd:
```
[declare -path else]
[declare -lib else]
```

Loading as a library enables the object browser plugin and pd-lua loader.

## Object Categories

### GUI Objects (42 objects)

| Object | Description |
|--------|-------------|
| `knob` | Rotary knob control |
| `numbox~` | Signal number display |
| `drum.seq` | Drum sequencer GUI |
| `bicoeff` | Biquad coefficient editor |
| `pad` | X/Y touch pad |
| `messbox` | Message box GUI |
| `mtx.ctl` | Matrix control grid |
| `biplot` | Biquad filter response plot |
| `zbiplot` | Z-plane filter plot |
| `pic` | Image display |
| `colors` | Color palette |
| `function` | Breakpoint function editor |
| `circle` | Circular control |
| `slider2d` | 2D slider |
| `display` | Message display |
| `popmenu` | Popup/dropdown menu |
| `scope~` | Oscilloscope |
| `scope3d~` | 3D oscilloscope |
| `spectrograph~` | Spectrograph display |
| `meter~` | Mono VU meter |
| `meter2~` | Stereo VU meter |
| `meter4~` | 4-channel meter |
| `meter8~` | 8-channel meter |
| `note` | Comment/note (replaces Cyclone's deprecated `comment`) |
| `mix2~` | 2-channel mixer |
| `mix4~` | 4-channel mixer |
| `out~` / `out.mc~` | Audio output with gain |
| `out4~` / `out8~` | Multi-channel output |
| `gain~` / `gain2~` | Gain control |
| `level~` | Level meter |
| `button` | Clickable button |
| `keyboard` | Piano keyboard |
| `graph~` | Signal graph display |
| `range.hsl` | Range slider |
| `multi.vsl` | Multi vertical slider |
| `openfile` | Open file button |
| `setdsp~` | DSP toggle |

### Synthesis: Oscillators

| Object | Description |
|--------|-------------|
| `sine~ [freq]` | Sine wave |
| `cosine~ [freq]` | Cosine wave |
| `saw~ [freq]` | Sawtooth |
| `saw2~ [freq]` | Variable slope sawtooth |
| `tri~ [freq]` | Triangle |
| `pulse~ [freq]` | Pulse |
| `square~ [freq]` | Square |
| `impulse~ [freq]` | Impulse |
| `impulse2~ [freq]` | Double impulse |
| `parabolic~ [freq]` | Parabolic wave |
| `gaussian~ [freq]` | Gaussian wave |
| `vsaw~ [freq]` | Variable sawtooth |
| `oscbank~` | Oscillator bank |
| `superosc~` | Supersaw oscillator |
| `oscnoise~` | Noisy oscillator |
| `fm~` | FM synthesis |
| `pm~` | Phase modulation |
| `wavetable~` | Wavetable oscillator |
| `wt2d~` | 2D wavetable |
| `damp.osc~` | Damped oscillator |

#### Bandlimited (Anti-Aliased) Oscillators

| Object | Description |
|--------|-------------|
| `bl.osc~` | Bandlimited oscillator |
| `bl.saw~` | Bandlimited sawtooth |
| `bl.saw2~` | Bandlimited variable saw |
| `bl.square~` | Bandlimited square |
| `bl.tri~` | Bandlimited triangle |
| `bl.imp~` | Bandlimited impulse |
| `bl.imp2~` | Bandlimited double impulse |
| `bl.vsaw~` | Bandlimited variable saw |
| `bl.wavetable~` | Bandlimited wavetable |
| `blip~` | Bandlimited impulse (sum of cosines) |

### Synthesis: Noise & Chaotic

| Object | Description |
|--------|-------------|
| `white~` | White noise |
| `pink~` | Pink noise (1/f) |
| `brown~` | Brown noise |
| `perlin~` | Perlin noise |
| `gray~` | Gray noise |
| `crackle~` | Crackle noise |
| `lfnoise~ [freq]` | Low-frequency noise |
| `stepnoise~ [freq]` | Step noise |
| `rampnoise~ [freq]` | Ramp noise |
| `randpulse~` | Random pulse |
| `randpulse2~` | Random pulse (variant) |
| `velvet~` | Velvet noise |
| `cusp~` | Cusp map |
| `fbsine~` / `fbsine2~` | Feedback sine |
| `gbman~` | Gingerbreadman map |
| `henon~` | Henon map |
| `ikeda~` | Ikeda map |
| `latoocarfian~` | Latoocarfian attractor |
| `lincong~` | Lin Cong map |
| `lorenz~` | Lorenz attractor |
| `logistic~` | Logistic map |
| `quad~` | Quad map |
| `standard~` | Standard map |
| `xmod~` / `xmod2~` | Cross modulation |
| `gendyn~` | GenDyn stochastic synthesis |
| `lsystem~` | L-system generator |

### Synthesis: Physical Modeling & Formant

| Object | Description |
|--------|-------------|
| `pluck~` | Karplus-Strong plucked string |
| `formlet~` | Formant filter |
| `formant~` | Formant synthesis |
| `paf~` | Phased array formant |
| `vosim~` | VOSIM pulse synthesis |
| `formfm~` | Formant FM synthesis |
| `packet~` | Packet synthesis |

### Synthesis: Complete Instruments

| Object | Description |
|--------|-------------|
| `plaits~` | Mutable Instruments Plaits macro-oscillator (MIT license) |
| `synth~` | General synthesizer |
| `pm2~` / `pm4~` / `pm6~` | Phase modulation (2/4/6 operator) |
| `sfont~` | SoundFont player (GPL) |
| `sfz~` | SFZ sampler (BSD) |

### Synthesis: Granular

| Object | Description |
|--------|-------------|
| `grain.synth~` | Granular synthesizer |

### Effects: Filters

| Object | Description |
|--------|-------------|
| `lowpass~ [freq] [q]` | Lowpass |
| `highpass~ [freq] [q]` | Highpass |
| `bandpass~ [freq] [q]` | Bandpass |
| `bandstop~ [freq] [q]` | Bandstop/notch |
| `allpass.filt~ [freq] [q]` | Allpass filter |
| `allpass.2nd~` | 2nd-order allpass |
| `comb.filt~` | Comb filter |
| `brickwall~ [freq]` | Brick-wall filter |
| `crossover~` | Crossover filter |
| `eq~ [freq] [gain] [q]` | Parametric EQ |
| `highshelf~ [freq] [gain]` | High shelf |
| `lowshelf~ [freq] [gain]` | Low shelf |
| `moog~ [freq] [q]` | Moog-style ladder filter |
| `resonant~ [freq] [q]` | Resonant filter |
| `resonator~ [freq] [q]` | Resonator |
| `resonator2~` | Resonator (variant) |
| `resonbank~` / `resonbank2~` | Bank of resonators |
| `svfilter~ [freq] [q]` | State-variable filter (LP/BP/HP outputs) |
| `biquads~` | Cascaded biquad sections |
| `lop2~` | 2-pole lowpass |
| `lop.bw~` | Butterworth lowpass |
| `hip.bw~` | Butterworth highpass |

### Effects: Reverb

| Object | Description |
|--------|-------------|
| `free.rev~` | Freeverb algorithm |
| `giga.rev~` | Gigaverb algorithm (GPL) |
| `plate.rev~` | Plate reverb (Tom Erbe) |
| `echo.rev~` | Echo reverb |
| `fdn.rev~` | Feedback delay network |
| `mono.rev~` | Mono reverb |
| `stereo.rev~` | Stereo reverb |
| `allpass.rev~` | Allpass reverb |
| `comb.rev~` | Comb reverb |

### Effects: Delay

| Object | Description |
|--------|-------------|
| `fbdelay~ [time] [fb]` | Feedback delay |
| `ffdelay~ [time]` | Feed-forward delay |
| `revdelay~ [time]` | Reverse delay |
| `filterdelay~` | Filtered delay |

### Effects: Modulation & Other

| Object | Description |
|--------|-------------|
| `chorus~ [rate] [depth]` | Chorus |
| `flanger~ [rate] [depth]` | Flanger |
| `phaser~ [stages]` | Phaser |
| `freq.shift~ [freq]` | Frequency shifter |
| `pitch.shift~ [shift]` | Pitch shifter |
| `rm~ [freq]` | Ring modulator |
| `tremolo~ [rate] [depth]` | Tremolo |
| `vibrato~ [rate] [depth]` | Vibrato |
| `vocoder~` | Vocoder |
| `morph~` | Signal morphing |
| `drive~ [drive]` | Soft-clip distortion |
| `shaper~` | Waveshaper |
| `crush~ [bits] [rate]` | Bitcrusher/decimator |
| `downsample~ [factor]` | Downsampler |
| `compress~ [thresh] [ratio]` | Compressor |
| `duck~` | Sidechain ducker |
| `expand~` | Expander |
| `noisegate~` | Noise gate |
| `norm~` | Normalizer |
| `freeze~` | Signal freeze |
| `pvoc.freeze~` | Phase vocoder freeze |
| `conv~` | Convolution (based on William Brent's convolve~) |
| `vca~` / `vca2~` | Voltage-controlled amplifier |

### Effects: Delay (Comb)

| Object | Description |
|--------|-------------|
| `ping.pong~` | Ping-pong delay |
| `stretch.shift~` | Time stretch + pitch shift |

### Envelopes & Ramp Generators

| Object | Description |
|--------|-------------|
| `adsr~ [a] [d] [s] [r]` | ADSR envelope |
| `asr~ [a] [s] [r]` | ASR envelope |
| `decay~ [time]` | Exponential decay |
| `envgen~` | Multi-segment envelope generator |
| `envelope~` | Trapezoid envelope |
| `ramp~ [time]` | Linear ramp |
| `susloop~` | Sustain loop envelope |
| `lag~ [time]` | Non-linear lag |
| `lag2~ [time]` | Double lag |
| `slew~ [up] [down]` | Slew rate limiter |
| `slew2~ [up] [down]` | Double slew |
| `glide~ [time]` | Portamento |
| `glide2~ [time]` | Double portamento |
| `smooth~` | Smoothing |
| `smooth2~` | Double smoothing |

### MIDI

| Object | Description |
|--------|-------------|
| `midi.in` / `midi.out` | Cooked MIDI I/O |
| `note.in` / `note.out` | MIDI note I/O |
| `ctl.in [cc]` / `ctl.out [cc]` | MIDI CC I/O |
| `bend.in` / `bend.out` | Pitch bend |
| `pgm.in` / `pgm.out` | Program change |
| `touch.in` / `touch.out` | Channel aftertouch |
| `ptouch.in` / `ptouch.out` | Polyphonic aftertouch |
| `mpe.in` | MPE input |
| `midi.learn` | MIDI learn |
| `midi.clock` | MIDI clock |
| `noteinfo` | Note analysis (duration, velocity, etc.) |
| `panic` | All notes off |
| `mono` / `mono~` | Monophonic mode |
| `voices` / `voices~` | Polyphonic voice allocator |
| `suspedal` | Sustain pedal |
| `sendmidi` | Raw MIDI send |

### Sequencers & Timing

| Object | Description |
|--------|-------------|
| `sequencer` / `sequencer~` | Data/signal sequencer |
| `score` / `score2` | Score sequencer |
| `pattern` | Rhythmic pattern |
| `euclid [steps] [hits]` | Euclidean rhythm |
| `arpeggiator` | Arpeggiator |
| `list.seq` | List sequencer |
| `phaseseq~` | Phase-based sequencer |
| `impseq~` | Impulse sequencer |
| `drum.seq` | Drum sequencer GUI |
| `tempo [bpm]` / `tempo~ [bpm]` | Tempo metronome |
| `polymetro` / `polymetro~` | Polymetric metronome |
| `metronome` / `metronome~` | Metronome |
| `rec` / `rec2` | Record/playback sequences |
| `midi` | MIDI file sequencer |
| `clock` | Clock source |

### Triggers & Logic

| Object | Description |
|--------|-------------|
| `above [threshold]` | Threshold trigger |
| `above~ [threshold]` | Signal threshold |
| `bangdiv [n]` | Bang divider |
| `chance [prob]` | Probabilistic pass |
| `dust~ [density]` / `dust2~` | Random impulses |
| `gatehold` / `gatehold~` | Gate hold |
| `gaterelease` / `gaterelease~` | Gate release |
| `gatemin~` | Minimum gate length |
| `gatedelay` / `gatedelay~` | Gate delay |
| `match~` | Pattern matcher |
| `trig2bang` / `trig2bang~` | Trigger to bang |
| `pulsecount~` / `pulsediv~` | Pulse counter/divider |
| `toggleff~` | Toggle flip-flop |
| `timed.gate` / `timed.gate~` | Timed gate |
| `schmitt` / `schmitt~` | Schmitt trigger |
| `status` / `status~` | Status detector |
| `changed~` / `changed2~` | Change detector |
| `detect~` | Edge detector |
| `loop` | Loop counter |

### Analysis

| Object | Description |
|--------|-------------|
| `env~` | Envelope follower |
| `follow~` | Envelope follower |
| `rms~` | RMS level |
| `mov.rms~` | Moving RMS |
| `vu~` | VU measurement |
| `peak~` | Peak detector |
| `maxpeak~` | Max peak hold |
| `range~` | Min/max range |
| `lastvalue~` | Last value detector |
| `median~` | Median filter |
| `beat~` | Beat detector |
| `zerocross~` | Zero crossing detector |
| `changed~` / `changed2~` | Change detector |
| `tap` | Tap tempo |

### Sampling & Playback

| Object | Description |
|--------|-------------|
| `player~` | Sample player |
| `gran.player~` | Granular sample player |
| `pvoc.player~` | Phase vocoder player |
| `pvoc.live~` | Live phase vocoder |
| `tabplayer~` | Table player |
| `tabwriter~` | Table recorder |
| `sample~` | Sample buffer |
| `rec.file~` / `play.file~` | Record/play soundfile |
| `batch.rec~` / `batch.write~` | Batch record/write |
| `sfload` / `sfinfo` | Soundfile load/info |
| `streamin~` / `streamout~` | Network audio streaming |

### Multichannel Tools

| Object | Description |
|--------|-------------|
| `nchs~` | Channel count |
| `mix~` | Multichannel mix |
| `group~` | Group channels |
| `repeat~` | Repeat channels |
| `select~` / `pick~` | Channel select/pick |
| `get~` / `sum~` | Get/sum channels |
| `merge~` / `unmerge~` | Merge/unmerge channels |
| `slice~` | Slice channels |
| `lace~` / `delace~` | Interleave/deinterleave |

### Tuning & Pitch

| Object | Description |
|--------|-------------|
| `scales` | Scale definitions |
| `scale2freq` | Scale to frequency |
| `scala` | Scala tuning file loader |
| `autotune` / `autotune2` | Auto-tune |
| `retune` | Retune |
| `eqdiv` | Equal division |
| `cents2ratio` / `ratio2cents` | Cents/ratio conversion |
| `cents2frac` / `frac2cents` | Cents/fraction conversion |
| `freq2midi` / `midi2freq` | Frequency/MIDI conversion |
| `note2midi` / `midi2note` | Note name/MIDI conversion |
| `makenote2` | Enhanced note generation |
| `intervals` | Musical interval calculations |
| `notes.on` / `sortnote` / `notedur2ratio` | Note utilities |

### Math & Conversion

| Object | Description |
|--------|-------------|
| `db2lin` / `lin2db` / `db2lin~` / `lin2db~` | dB/linear conversion |
| `car2pol` / `pol2car` / `car2pol~` / `pol2car~` | Cartesian/polar |
| `mtof` / `ftom` | MIDI/frequency |
| `rescale` / `rescale~` | Value rescaling |
| `add` / `add~` | Addition |
| `op` / `op~` | Generic math operator |
| `wrap2` / `wrap2~` | Wrap with range |
| `fold` / `fold~` | Fold with range |
| `quantizer` / `quantizer~` | Quantize to steps |
| `median` / `mov.avg` | Median / moving average |
| `sr~` | Sample rate |
| `nyquist~` | Nyquist frequency |
| `pi` / `e` | Constants |
| `samps2ms` / `ms2samps` / `samps2ms~` / `ms2samps~` | Sample/time conversion |
| `float2bits` | Float to bits |

### Message & List Management

| Object | Description |
|--------|-------------|
| `pack2` | Pack (outputs on any inlet) |
| `merge` / `unmerge` | Merge/split lists |
| `slice` | Slice list |
| `sort` / `scramble` / `reverse` / `rotate` | List operations |
| `iterate` | Iterate over list |
| `group` / `stream` | Group/stream items |
| `sum` | Sum list |
| `order` | Order by index |
| `break` | Break list |
| `combine` / `delete` / `remove` / `replace` | List manipulation |
| `equal` | List equality |
| `unique` | Unique elements |
| `filter` | Filter list |
| `insert` / `pick` / `spread` | List selection |
| `rand.list` / `rand.dev` / `rand.harm` | Random lists |
| `format` | Format string |
| `router` / `route2` / `routeall` / `routetype` / `selector` | Message routing |
| `changed` | Filter repeats |
| `hot` | Hot/cold inlet control |
| `shift` | Shift register |
| `store` / `stack` | Storage |
| `messcoll` | Message collection |
| `dispatch` | Message dispatch |
| `initmess` | Initial message (like Max's loadmess) |

### OSC & Networking

| Object | Description |
|--------|-------------|
| `osc.send` / `osc.receive` | OSC send/receive |
| `osc.format` / `osc.parse` | OSC format/parse |
| `osc.route` | OSC route |
| `pd.link` / `pd.link~` | Inter-instance messaging |

### Patch Management

| Object | Description |
|--------|-------------|
| `loadbanger` | Multi-trigger loadbang |
| `closebang` | Bang on patch close |
| `args` | Get patch arguments |
| `presets` | Preset management |
| `dollsym` | Dollar symbol expansion |
| `sender` / `receiver` / `retrieve` | Named send/receive |
| `var` | Named variable |
| `send2~` | Send to multiple |
| `canvas.active` | Canvas active state |
| `canvas.bounds` / `canvas.gop` / `canvas.pos` | Canvas properties |
| `canvas.edit` / `canvas.vis` | Canvas state |
| `canvas.name` / `canvas.setname` | Canvas naming |
| `canvas.zoom` | Canvas zoom level |
| `abs.pd~` | Abstract subpatch |

### Control: Fade/Pan/Routing

| Object | Description |
|--------|-------------|
| `autofade~` / `autofade.mc~` | Auto fade in/out |
| `autofade2~` / `autofade2.mc~` | Dual auto fade |
| `balance~` | L/R balance |
| `ms.enc~` / `ms.dec~` | Mid/Side encode/decode |
| `width~` | Stereo width |
| `pan2~` / `pan4~` / `pan~` / `pan.mc~` | Panning |
| `pan.stereo~` | Stereo panner |
| `spread~` / `spread.mc~` | Channel spread |
| `rotate~` / `rotate.mc~` | Channel rotation |
| `xfade~` / `xfade.mc~` | Crossfade |
| `xgate~` / `xgate2~` / `xselect~` / `xselect2~` | Channel routing |
| `mtx~` / `mtx.mc~` | Matrix routing |

## M.E.R.D.A. Modules (20 objects)

EuroRack-inspired modules with built-in GUI controls.

### Classic
`adsr.m~`, `lfo.m~`, `seq.m~`, `vca.m~`, `vca2.m~`, `vcf.m~`, `vco.m~`

### FX
`bob.m~` (Moog ladder filter), `chorus.m~`, `crusher.m~`, `delay.m~`, `drive.m~`, `flanger.m~`, `phaser.m~`, `plate.rev.m~`, `rm.m~`

### Generators
`superosc.m~`, `gendyn.m~`, `plaits.m~`, `pluck.m~`, `pm6.m~`, `sfont.m~`

### Tools
`presets.m`, `sig.m~`, `level.m~`

### Extra
`brane.m~` (multichannel delay)

## ELSE Alternatives to Cyclone Objects

ELSE provides alternatives for most Cyclone objects. Key mappings:

| Cyclone | ELSE |
|---------|------|
| `accum` | `add` |
| `average~` | `mov.avg~` |
| `bondo` | `hot` |
| `bucket` | `shift` |
| `buffer~` | `sample~` |
| `comb~` | `comb.rev~` |
| `count~` | `ramp~` |
| `cycle` | `robin` |
| `curve~` | `envgen~` |
| `cartopol~/poltocar~` | `car2pol~/pol2car~` |
| `degrade~` | `crusher~` |
| `drunk` | `drunkard` |
| `delay~` | `ffdelay~` |
| `gate` | `router` |
| `gate~` | `xgate~` |
| `line~` | `envgen~` |
| `loadmess` | `initmess` |
| `pak` | `pack2` |
| `prepend` | `insert` |
| `play~` | `tabplayer~` |
| `reson~` | `bandpass~` |
| `scale/scale~` | `rescale/rescale~` |
| `slide~` | `lag2~` |
| `svf~` | `svfilter~` |

For new patches, prefer ELSE objects over Cyclone — they are more actively maintained and often provide more features.
