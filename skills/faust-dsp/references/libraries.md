# Faust Standard Libraries Reference

Quick reference for the most-used functions in Faust's standard libraries. Import with `import("stdfaust.lib");`.

## Library Environments

| Prefix | Library | Description |
|--------|---------|-------------|
| `sf` | all.lib | All functions from all libraries |
| `aa` | aanl.lib | Analytical functions |
| `an` | analyzers.lib | Signal analysis |
| `ba` | basics.lib | Basic operations, counters, timers |
| `co` | compressors.lib | Dynamic range processing |
| `de` | delays.lib | Delay lines |
| `dm` | demos.lib | Demo functions with built-in UI |
| `dx` | dx7.lib | DX7 FM synthesis |
| `en` | envelopes.lib | Envelope generators |
| `fd` | fds.lib | Fractional delay systems |
| `fi` | filters.lib | Audio filters |
| `ho` | hoa.lib | Higher Order Ambisonics |
| `it` | interpolators.lib | Interpolation |
| `la` | linearalgebra.lib | Linear algebra |
| `ma` | maths.lib | Math constants and functions |
| `mi` | mi.lib | Mutable Instruments models |
| `ef` | misceffects.lib | Miscellaneous effects |
| `mo` | motion.lib | Motion/sensor processing |
| `no` | noises.lib | Noise generators |
| `os` | oscillators.lib | Oscillators |
| `pf` | phaflangers.lib | Phase and flanger effects |
| `pm` | physmodels.lib | Physical modeling |
| `qu` | quantizers.lib | Quantization effects |
| `rm` | reducemaps.lib | Reduction mappings |
| `re` | reverbs.lib | Reverb algorithms |
| `ro` | routes.lib | Signal routing |
| `si` | signals.lib | Signal utilities |
| `so` | soundfiles.lib | Sound file access |
| `sp` | spats.lib | Spatial audio |
| `sy` | synths.lib | Synthesis utilities |
| `ve` | vaeffects.lib | Variable delay effects |
| `vl` | version.lib | Version info |
| `wa` | webaudio.lib | WebAudio integration |
| `wd` | wdmodels.lib | Wave digital filter models |

---

## basics.lib (`ba`)

| Function | Signature | Description |
|----------|-----------|-------------|
| `ba.counter` | `(trigger)` | Counts trigger impulses |
| `ba.time` | `()` | Sample counter (0, 1, 2, ...) |
| `ba.samp` | `()` | Current sample index |
| `ba.impulse` | `(period)` | Impulse every `period` samples |
| `ba.pulsen` | `(level, n)` | Pulse of `n` samples at `level` |
| `ba.sequencer` | `(n, input, trigger)` | Sample-and-hold `n` values |
| `ba.bypass` | `(enabled, x)` | Bypass signal when enabled=1 |
| `ba.if` | `(cond, then, else)` | Conditional (cond is 0 or 1) |
| `ba.select` | `(n, s)` | Select one of n signals |
| `ba.selector` | `(index, n)` | Route selector for n outputs |
| `ba.latch` | `(trigger, x)` | Sample and hold |
| `ba.memo` | `(f)` | Memoize (share) computation |
| `ba.once` | `(trigger)` | Single impulse on first trigger |
| `ba.count` | `(trigger, max)` | Count up to max |
| `ba.zerocross` | `(x)` | Zero crossing detector |
| `ba.semi2ratio` | `(x)` | Semitones to frequency ratio |
| `ba.ratio2semi` | `(x)` | Frequency ratio to semitones |
| `ba.midikey2freq` | `(x)` | MIDI note to frequency |
| `ba.freq2midikey` | `(x)` | Frequency to MIDI note |
| `ba.db2linear` | `(x)` | dB to linear |
| `ba.linear2db` | `(x)` | Linear to dB |

## maths.lib (`ma`)

| Function | Signature | Description |
|----------|-----------|-------------|
| `ma.SR` | — | Sampling rate (constant) |
| `ma.PI` | — | pi (3.14159...) |
| `ma.PI2` | — | 2*pi |
| `ma.EPSILON` | — | Smallest positive float |
| `ma.INFINITY` | — | Positive infinity |
| `ma.FMIN` | — | Smallest normal float |
| `ma.FMAX` | — | Largest float |
| `ma.TAU` | — | 2*PI |
| `ma.min` | `(a, b)` | Minimum |
| `ma.max` | `(a, b)` | Maximum |
| `ma.inf` | `(n)` | Infinity check |
| `ma.isnanan` | `(n)` | NaN check |
| `ma.clamp` | `(x, lo, hi)` | Clamp to range |
| `ma.sqrt` | `(x)` | Square root |
| `ma.pow` | `(x, y)` | Power |
| `ma.log` | `(x)` | Natural log |
| `ma.log2` | `(x)` | Base-2 log |
| `ma.log10` | `(x)` | Base-10 log |
| `ma.exp` | `(x)` | Exponential |
| `ma.abs` | `(x)` | Absolute value |
| `ma.ceil` | `(x)` | Ceiling |
| `ma.floor` | `(x)` | Floor |
| `ma.round` | `(x)` | Round to nearest |
| `ma.fmod` | `(x, y)` | Float modulo |
| `ma.sign` | `(x)` | Sign (-1, 0, 1) |
| `ma.inv` | `(x)` | 1/x |

## oscillators.lib (`os`)

| Function | Signature | Description |
|----------|-----------|-------------|
| `os.osc` | `(freq)` | Sine oscillator |
| `os.oscph` | `(freq, phase)` | Sine with phase |
| `os.sawtooth` | `(freq)` | Bandlimited sawtooth |
| `os.square` | `(freq)` | Bandlimited square |
| `os.triangle` | `(freq)` | Bandlimited triangle |
| `os.pulsetrain` | `(freq, width)` | Bandlimited pulse |
| `os.phasor` | `(size, freq)` | Phasor (0 to size ramp) |
| `os.phasormod` | `(size, freq, mod)` | Phasor with modulation |
| `os.lf_imptrain` | `(freq)` | Low-frequency impulse train |
| `os.lf_saw` | `(freq)` | Low-frequency saw (not bandlimited) |
| `os.lf_squarewave` | `(freq)` | Low-frequency square |
| `os.lf_triangle` | `(freq)` | Low-frequency triangle |
| `os.lf_pulsetrain` | `(freq, width)` | Low-frequency pulse train |
| `os.dwnSampSignal` | `(n, x)` | Downsample signal by n |

## filters.lib (`fi`)

| Function | Signature | Description |
|----------|-----------|-------------|
| `fi.resonlp` | `(freq, q, gain, x)` | Resonant lowpass |
| `fi.resonhp` | `(freq, q, gain, x)` | Resonant highpass |
| `fi.resonbp` | `(freq, q, gain, x)` | Resonant bandpass |
| `fi.resonbr` | `(freq, q, x)` | Band reject (notch) |
| `fi.peak_eq` | `(freq, q, gain, x)` | Parametric EQ |
| `fi.svf1` | `(freq, q, x)` | 1st-order SVF (lp,hp,bp,br outputs) |
| `fi.moogLadder` | `(freq, q, x)` | Moog ladder filter |
| `fi.diodeLadder` | `(freq, q, x)` | Diode ladder filter |
| `fi.butLP` | `(n, freq, x)` | Butterworth LP of order n |
| `fi.butHP` | `(n, freq, x)` | Butterworth HP of order n |
| `fi.butBP` | `(n, freq, x)` | Butterworth BP of order n |
| `fi.butBR` | `(n, freq, x)` | Butterworth BR of order n |
| `fi.lowpass` | `(freq, x)` | 1st-order lowpass |
| `fi.highpass` | `(freq, x)` | 1st-order highpass |
| `fi.allpass` | `(freq, x)` | 1st-order allpass |
| `fi.dcblocker` | `(x)` | DC blocker |
| `fi.zita_rev` | `(...)` | Zita reverb internals |
| `fi.butterpole` | `(n, freq, x)` | General Butterworth |
| `fi.slow_roe` | `(x)` | Smooth (1-pole) at ~1Hz |
| `fi.smooth` | `(tau, x)` | Smooth with time constant |

## delays.lib (`de`)

| Function | Signature | Description |
|----------|-----------|-------------|
| `de.delay` | `(max, d, x)` | Integer delay (max buffer, d samples) |
| `de.fdelay` | `(max, d, x)` | Fractional delay (linear interp) |
| `de.fdelaylti` | `(max, d, x)` | Fractional delay (Thiran allpass) |
| `de.sdelay` | `(max, d, x)` | Spline-interpolated delay |
| `de.cdelay` | `(max, x)` | Circular delay with write index |
| `de.rev1` | `(delay, x)` | Simple reverb from allpass chain |
| `de.fcomb` | `(max, d, fb, ff, x)` | Comb filter (delay, feedback, feedforward) |

## reverbs.lib (`re`)

| Function | Signature | Description |
|----------|-----------|-------------|
| `re.zita_rev` | `(stereo_in)` | Zita reverb (full) |
| `re.zita_light` | `(stereo_in)` | Zita reverb (simplified controls) |
| `re.jcrev` | `(x)` | Schroeder reverb |
| `re.freeverb` | `(stereo_in)` | Freeverb algorithm |

## envelopes.lib (`en`)

| Function | Signature | Description |
|----------|-----------|-------------|
| `en.ar` | `(a, r, gate)` | Attack-Release envelope |
| `en.adsr` | `(a, d, s, r, gate)` | ADSR envelope |
| `en.asr` | `(a, s, r, gate)` | Attack-Sustain-Release |
| `en.ahdsfr` | `(a,h,d,s,f,r,gate)` | Full envelope |
| `en.smoothEnvelope` | `(tau, gate)` | Smooth envelope |
| `en.tau2pole` | `(tau)` | Convert time constant to pole |
| `en.pole2tau` | `(pole)` | Convert pole to time constant |

## compressors.lib (`co`)

| Function | Signature | Description |
|----------|-----------|-------------|
| `co.compressor` | `(thresh, ratio, att, rel, x)` | Basic compressor |
| `co.compressor_stereo` | `(thresh, ratio, att, rel, L, R)` | Stereo compressor |
| `co.limiter_1176` | `(x, y)` | 1176-style limiter |
| `co.gate` | `(thresh, x, y)` | Noise gate |
| `co.expander` | `(thresh, ratio, att, rel, x)` | Expander |

## signals.lib (`si`)

| Function | Signature | Description |
|----------|-----------|-------------|
| `si.smoo` | `(x)` | Exponential smoothing (good for sliders) |
| `si.polySmooth` | `(x, smooth, trigger)` | Polyphony-safe smoothing |
| `si.bus` | `(n)` | N identity wires |
| `si.block` | `(x)` | Block a signal (output 0) |
| `si.cascade` | `(n, f, x)` | Apply f n times in series |
| `si.sum` | `(n, f, x)` | Apply f n times and sum |
| `si.count` | `(n, trigger)` | Count triggers modulo n |
| `si.mix` | `(sig1, sig2, mix)` | Crossfade between two signals |

## demos.lib (`dm`)

Demo functions include built-in UI elements (sliders, buttons, etc.) and are ready to use directly:

| Function | I/O | Description |
|----------|-----|-------------|
| `dm.zita_light` | 2in/2out | High-quality reverb |
| `dm.freeverb_demo` | 2in/2out | Freeverb |
| `dm.wah4_demo` | 1in/1out | Auto-wah |
| `dm.phaser2_demo` | 2in/2out | Phaser |
| `dm.spectral_level_demo` | 1in/1out | Spectral level display |
| `dm.flanger_demo` | 2in/2out | Flanger |
| `dm.cubicnl_demo` | 1in/1out | Cubic nonlinearity |
| `dm.compressor_demo` | 1in/1out | Compressor |
| `dm.echo_demo` | 1in/1out | Echo effect |
| `dm.karplus32` | 0in/1out | Karplus-Strong plucked string |

## noises.lib (`no`)

| Function | Signature | Description |
|----------|-----------|-------------|
| `no.noise` | `()` | White noise |
| `no.pinknoise` | `()` | Pink noise (1/f) |
| `no.randn` | `()` | Gaussian white noise |

## misceffects.lib (`ef`)

| Function | Signature | Description |
|----------|-----------|-------------|
| `ef.cubicnl` | `(drive, offset, x)` | Cubic nonlinearity |
| `ef.softclip` | `(x)` | Soft clip |
| `ef.stereoWidth` | `(width, L, R)` | Stereo width control |
| `ef.talkbox` | `(source, excitation)` | Vocoder/talkbox |
| `ef.crossover` | `(n, freq, x)` | N-band crossover |

## vaeffects.lib (`ve`)

| Function | Signature | Description |
|----------|-----------|-------------|
| `ve.chorus` | `(rate, depth, fb, x)` | Mono chorus |
| `ve.chorusStereo` | `(rate, depth, fb, L, R)` | Stereo chorus |
| `ve.flanger` | `(rate, depth, fb, x)` | Mono flanger |
| `ve.flangerStereo` | `(rate, depth, fb, L, R)` | Stereo flanger |
| `ve.pitchShift` | `(shift, window, x)` | Pitch shifter |
| `ve.transposer` | `(shift, x)` | Simple pitch transposition |

## quantizers.lib (`qu`)

| Function | Signature | Description |
|----------|-----------|-------------|
| `qu.bitbuster` | `(bits, x)` | Bit depth reduction |
| `qu.sampleratebuster` | `(freq, x)` | Sample rate reduction |
| `qu.quantize` | `(levels, x)` | Quantize to N levels |
| `qu.ring` | `(x, y)` | Ring modulation |

## physmodels.lib (`pm`)

Contains physical modeling instruments: strings, brass, wind, drums, etc. Key entry points:

- `pm.fireString` — Plucked string model
- `pm.bowedString` — Bowed string model
- `pm.brass` — Brass instrument model
- `pm.flute` — Flute model
- `pm.bell` — Church bell model
- `pm.membrane` — Drum membrane model

## synths.lib (`sy`)

- `sy.combString` — Comb filter string synthesis
- `sy.windInstrument` — Wind instrument model

## routes.lib (`ro`)

| Function | Signature | Description |
|----------|-----------|-------------|
| `ro.cross` | `(x, y)` | Cross signals: (x,y) -> (y,x) |
| `ro.crossnn` | `(n, signals)` | Cross n pairs of signals |
| `ro.interleave` | `(n, signals)` | Interleave n groups |
| `ro.deinterleave` | `(n, signals)` | De-interleave n groups |
| `ro.recursive` | `(n, f, signals)` | Apply f recursively n times |

## analyzers.lib (`an`)

| Function | Signature | Description |
|----------|-----------|-------------|
| `an.meter` | `(x)` | RMS level meter |
| `an.amp_follower` | `(att, rel, x)` | Envelope follower |
| `an.amp_follower_rel` | `(rel, x)` | Release envelope follower |
| `an.zeroCrossing` | `(x)` | Zero crossing rate |
| `an.freqmeter` | `(x)` | Frequency measurement |
