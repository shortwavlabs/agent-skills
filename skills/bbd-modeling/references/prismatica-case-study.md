# Case Study: Prismatica (EHX Polychorus-Inspired Four-Mode BBD Plug-In)

**A labelled case study, not a template.** Its numbers are the outcomes of one circuit's measurements. Report paths refer to the Prismatica repository (`docs/kicad`, `docs/spice`, `docs/dsp`, `docs/juce`, `docs/audio`); the rest of this skill does not depend on them.

## Contents

- [Starting Point](#starting-point)
- [Architecture](#architecture)
- [Phases](#phases)
- [Major Decisions](#major-decisions)
- [Failed and Rejected Approaches](#failed-and-rejected-approaches)
- [Validated Evidence](#validated-evidence)
- [Known Limitations](#known-limitations)
- [Reusable Lessons](#reusable-lessons)

## Starting Point

- **Circuit:** the Electro-Harmonix Polychorus (EC7000) schematic.
- **Devices:**
  - two BBDs: MN3008 (2048 stages) and MN3009 (256 stages);
  - an NE570 compander;
  - an LM311 + CD4013 clock;
  - an LM324 LFO.
- **Four modes from one circuit:**

| Mode | BBD | LFO on the clock | Delay (calibrated clock) |
|---|---|---|---|
| Double Track / Echo | MN3008 | no (a buffer swamps it) | 12.8–102.4 ms |
| Chorus / Vibrato | MN3008 | yes | 10.9–102.4 ms |
| Flange | MN3009 | yes | 0.64–12.8 ms |
| Filter Matrix | MN3009 | no (static clock: a tuned comb) | 0.64–12.8 ms |

- **Outputs:** MAIN = (dry − wet)/2 and STEREO = (dry + wet)/2, the pedal's two jacks.
- **Mode-switch positions 2–4:** inferred from the switch-arc order (medium confidence, four corroborations).

## Architecture

**Offline:**
- a SPICE oracle (ngspice) of everything except the BBDs;
- an event-driven Python BBD coupled live to libngspice;
- a float64 Python four-mode renderer, validated against SPICE at steady state (within 0.07 dB).

**Real-time:** a C++20 engine, at 2× internal rate up to 50 kHz host rate:
- an event-based BBD with box-averaged zero-order-hold outputs;
- a SPICE-table clock law;
- a reduced two-state control network on a 2 kHz causal grid;
- per-path discretized filters (bilinear, or bilinear plus impulse-invariant, chosen by error);
- an exact feed-forward compander envelope;
- a 25-state trapezoidal MNA regeneration summer with a rank-2 pot update;
- two cores for 30 ms mode crossfades.

**Plug-in:** JUCE AU/VST3 with 12 parameters, 26 factory programs, an infinite tail, and a polled-attachment editor.

## Phases

| Phase | Work | Outcome | Reports |
|---|---|---|---|
| K1 | KiCad reconstruction from the vector PDF; pin-partition netlist check with fault injection | PASS | `docs/kicad/01-08` |
| K2-A | SPICE power, LFO, CV routing, master clock; model registry; TP1 calibration reading | PARTIAL, 109/111 | `docs/spice/01-08` |
| K2-B | NE570 project model; audio path with a diagnostic zero-delay BBD; clock/BBD audit → five entry gates | PASS, 51/51 | `docs/spice/09-15` |
| K2-C1 | Functional MN3008/MN3009 reference: transfer contract, event-driven co-simulation, independent oracle | PASS functional; clock **physically non-compliant** | `docs/spice/16-22` |
| K2-C2 | Non-ideal mechanisms: feasibility matrix; three bounded datasheet-typical mechanisms; the rest STOP; hardware plan | PARTIAL, 33/37 | `docs/spice/23-30` |
| K2-D1 / D2 / D2F | Four-mode routing and control laws; reference renderer; guitar-DI audition; Filter Matrix investigation | PASS with one retained clause; listening | `docs/spice/31-38`, `docs/audio/01-04`, `filter-matrix-*` |
| K3-A | Native C++ real-time core | PASS (4 evidenced revisions) | `docs/dsp/01-11` |
| K3-B | JUCE plug-in, stock editor, validation, live host | PARTIAL (editor memory P.U02 FAIL) | `docs/juce/01-18` |
| K3-C … K3-E | Musical refinement; Filter Matrix voice C1; presets; product 0.2.0 | promoted | `docs/audio/k3c-*`, `k3d-*`, `k3e-*` |
| K3-F | Filter Matrix self-oscillation research: F1 / F2 | F2 selected | `docs/audio/k3f-*` |
| K3-G | F2 production readiness; Extended Feedback switch; live-host corrections | validated | `docs/audio/k3g-*`, `docs/juce/19` |
| K3-H | Extended Feedback in every mode (per-mode laws) | validated | `docs/audio/k3h-*` |
| K3-I | Product 0.3.0: Extended Feedback in all modes; AU parameter-order fix | installed | `docs/audio/k3i-*` |
| K3-J | Editor-open audio-thread allocation: root cause and polled attachments | installed | `docs/audio/k3j-*`, `docs/juce/20` |

## Major Decisions

1. **Functional BBD, not physical.** Ideal charge transfer with exact clock semantics.
   - The non-idealities were non-identifiable from datasheets.
   - Three datasheet-typical mechanisms were built as options, off by default.
   - The original clock's non-compliance is recorded, not modelled.
2. **Calibrated clock trim.** The documented "100 µs at TP1" was resolved to the full period of one clock line, which moved the delay ranges.
3. **2× internal rate,** from the filter-realization bound (1× missed 0.1 dB / 1°).
4. **The compander as an exact feed-forward envelope.** The τ/2 identity removes a delay-free loop.
5. **Filter Matrix voice "C1".**
   - The circuit's Filter Matrix was judged too subtle on guitar. Raw notch depth had misled; a perceptual ERB metric did not.
   - A matched STEREO-polarity mix was chosen: `{1.0, 2.5, 0.55, 1.0}`.
6. **Extended Feedback as a separate contract:**
   - a regeneration copy at the summer;
   - a smoothstep law above f0 = 0.85;
   - a tanh-bounded extra return ("F2");
   - per-mode gMax matched by margin (2.2 short BBD, 2.5 long BBD);
   - Classic bit-identical with it off;
   - an infinite tail.
7. **Mode crossfade empties the incoming BBD,** so regeneration rebuilds in 0.25–7 s. Documented as intended.
8. **Product compatibility:** the new parameter was appended with a higher AU version hint, and legacy states restore it OFF.
9. **Editor real-time safety:** polled attachments instead of JUCE's stock attachments (see the `juce-plugin` skill).

## Failed and Rejected Approaches

Each entry gives the hypothesis, what was tried, the result, why it failed, the corrected understanding, the lesson, and when the rejected approach might still be appropriate. **"Why"** is the reports' own explanation unless marked *inferred*.

### Oracle and circuit phases (K1–K2)

**Vendor op-amp and comparator macros** (`docs/spice/01`, `07`)
- **Hypothesis:** manufacturer macros are the best models.
- **Tried:** ten macros qualified in-circuit.
- **Result:** start-up failures:
  - an op-amp sourced 11 mA from its supply pin at 1.7 V;
  - another saturated 0.56 V below its negative rail and stalled the LFO;
  - comparator macros never oscillated.
- **Why:** the macros are non-passive at low supply, and ideal rails hid it.
- **Corrected:** datasheet-calibrated project cards, with passivity at low supply as a gate.
- **Lesson:** qualify models under the real start-up.
- **Still appropriate:** as cross-check values.

**Linear CD4013 output law** (`docs/spice/13`, `17`)
- **Hypothesis:** a resistive output calibrated at one point gives the edge times.
- **Result:** 390 ns edges and a 60 mA peak, apparently compliant.
- **Why:** real outputs saturate.
- **Corrected:** a saturating law, giving 506–1080 ns.
- **Lesson:** single-point resistive drivers flatter edges into large loads.
- **Still appropriate:** a labelled, frozen baseline.

**Native SPICE stage network for the BBD** (`docs/spice/18`), rejected before it was built
- **Why:** under clock overlap, solver time constants decide how transparent the stages become: an invented physical law.
- **Lesson:** do not let solver artefacts define transfer semantics.
- **Still appropriate:** an XSPICE event model gated by the oracle, if long modulated runs become routine.

**Analytic expression for a modulated clock source** (`docs/spice/20`)
- **Result:** edges smeared, the pulse width mis-measured, and the clock ran during the rail ramp.
- **Why:** ngspice places no breakpoints at the kinks of behavioural sources.
- **Corrected:** piecewise-linear schedules.
- **Lesson:** a fixture defect can look like a model finding.

**Interpolating raw digitized curves into the headroom nonlinearity** (`docs/spice/27`)
- **Result:** 1.3–5 % spurious THD from the pixel staircase. One gate also failed because of a +0.8 dB reference bug.
- **Corrected:** a smooth five-parameter fit, with the validation disclosed as "not blind in the strict sense". One point still misses at the highest level.
- **Lesson:** never interpolate digitized points into a nonlinearity.

**Physical non-idealities fitted from datasheets** (`docs/spice/24-26`)
- **Hypothesis:** CTI, leakage, feedthrough, noise and phase overlap can be fitted.
- **Result:** non-identifiable. An exploratory overlap law showed that α = 4.7e-5 already costs 1 dB at 2 kHz.
- **Corrected:** STOP, plus a hardware measurement plan.
- **Lesson:** do not add structure nothing constrains.
- **Still appropriate:** class-C sensitivity sweeps, never in claims.

**Levels from power-up runs** (`docs/spice/33`, `38`)
- **Result:** the renderer was −8 dB against SPICE.
- **Why:** a 2.9 s compander relaxation.
- **Corrected:** quiescent references.
- **Lesson:** separate timing claims from level claims during settling.

**Bilinear-only discretization and a library convention** (`docs/spice/38`)
- **Result:** 0.50 dB error.
- **Why:** bilinear alone was not enough; separately, scipy's zpk conversion advanced strictly proper filters by one sample.
- **Corrected:** per-path bilinear plus impulse invariance (0.08 dB), and explicit z⁻¹ sections.
- **Lesson:** check discretization in the time domain.

**Hot trimmers for a stronger Filter Matrix** (`filter-matrix-investigation`)
- **Result:** loop gain 1.24: self-oscillation, and the character shifted.
- **Corrected:** nominal trims kept.
- **Still appropriate:** a labelled "calibrated unit" variant.

**"tmax ≤ 0.2 µs" as a universal remedy** (`docs/spice/28`)
- **Result:** another deck aborted at that step.
- **Corrected:** the advice was retracted.
- **Lesson:** no single numerical policy completes every configuration; record the policy per run.

### Real-time and product phases (K3)

**1× internal rate** (`docs/dsp/07`, `09`)
- **Result:** 0.43 dB / 2.9° against a bound of 0.1 dB / 1°; residual −28.5 to −31.2 dB.
- **Why:** not stated in the reports. *Inferred:* discretization error near Nyquist.
- **Lesson:** derive the rate from the realization bound.
- **Still appropriate:** host rates above 50 kHz, where 1× is used.

**Re-settled control network at mode change, and judging transitions against separate renders** (`docs/dsp/05`, `07`)
- **Result:** a 24 dB MAIN dip entering one mode; the comparison method failed for unrelated reasons.
- **Corrected:** shadow networks always run, and transitions are judged against the same render's steady state.
- **Lesson:** keep every switchable mode's modulation state alive.

**Unshifted comparison of a causal engine with a look-ahead reference** (`docs/dsp/07`)
- **Result:** −9.2 dB, a FAIL. The reference against itself delayed 0.5 ms gives −9.3 dB.
- **Corrected:** compare against the causally delayed reference: −50.6 dB.
- **Lesson:** remove known causal delays before computing residuals.

**Clamping invalid input** (`docs/dsp/11`)
- **Result:** a seconds-long coupling transient.
- **Corrected:** invalid samples become 0.
- **Lesson:** treat invalid input as missing, not as extreme.

**"Chorus too wild" as a suspected defect** (`docs/audio/k3c-02`)
- **Result:** circuit-correct. The engine matches the reference at −151 dB; the sweep filter acts on the control voltage only.
- **Corrected:** no DSP change; sweep-filter presets added.
- **Lesson:** check "wrong-sounding" behaviour against the reference before changing DSP.

**Raw notch depth as the Filter Matrix metric** (`docs/audio/k3c-03`, `k3c-04`)
- **Result:** 13 dB of raw ripple, but 0.7 dB of ERB-band variation: judged "too subtle".
- **Why:** the ear smooths narrow notches within an ERB.
- **Corrected:** a DI-weighted ERB metric, which led to the C1 voice.
- **Lesson:** choose voices with perceptual metrics.

**Circuit-like routes to self-oscillation** (`docs/audio/k3f-02`, `k3f-03`)
- **Tried:** hot trims, in-loop gain with rescaled emphasis, BBD headroom.
- **Result:** rejected:
  - hot trims change the loop at every setting;
  - the summing network leaks dry into the outputs;
  - headroom changes every mode.
- **Corrected:** an extra return at the summer only.
- **Lesson:** place enhancement gain where it cannot touch approved outputs.

**F1, swing-limited regeneration** (`docs/audio/k3f-03`, `k3g-01`)
- **Result:** all-or-nothing at the rails, about 25 dB above playing level.
- **Why:** "not selected", with no reason recorded. *Inferred:* loudness.
- **Corrected:** F2, a tanh on the extra return only.
- **Still appropriate:** a deliberately rail-bound voice.

**Optimizing the regeneration copy after freezing** (`docs/audio/k3f-04`, `k3g-03`)
- **Result:** a column-major layout was slower and not bit-identical; skipping zeros was worth at most 3 %.
- **Corrected:** F2 kept as frozen.
- **Lesson:** after a hash freeze, an optimization is a sound change.

**One regeneration law for every mode** (`docs/audio/k3h-02`)
- **Result:** the long-delay modes sustained only at full FEEDBACK.
- **Why:** their loop is 12 % weaker.
- **Corrected:** match the margin, gMax × L(1) = 1.26, giving gMax 2.5.
- **Lesson:** define laws relative to each loop's measured gain.

**Step-ratio edge tests** (`docs/audio/k3f-04`, `k3h-09`)
- **Result:** false FAILs, with no edge present.
- **Corrected:** twin renders.
- **Lesson:** compare against a counterfactual render.

**Live-host measurement errors** (`docs/juce/19`, `docs/audio/k3g-02`, `k3h-07`)
- **Result:**
  - parameters silently not applied (names against hashed IDs);
  - the host cache trusted;
  - false allocations from a reused thread ID;
  - decimal against float32 values;
  - digital against volts thresholds.
- **Corrected:** each fixed, with the original results kept.
- **Lesson:** verify at the device under test.

**New parameter with the same AU version hint** (`docs/audio/k3i-03`)
- **Result:** three existing AU parameters moved one index, which would redirect Logic automation; the ID checks all passed.
- **Corrected:** version hint 2, and a hosted-list check.
- **Lesson:** check the hosted parameter list.

**AU "0 allocations" in the editor-open tests** (`docs/audio/k3j-01`)
- **Result:** an artifact. The test host set AU parameters on the message thread; delivered from the audio callback, the AU allocated like the VST3.
- **Lesson:** deliver automation as a DAW does.

## Validated Evidence

Product 0.3.0 with the K3-J editor, re-verified in K3-K:
- **References:**
  - Classic 887 / 887 against the previous product (Extended OFF 284 / 284 identical);
  - F2 226 / 226;
  - other-mode Extended references 142 / 142;
  - engine CLI byte-identical across phases.
- **Plug-in vs engine:** processor = engine; hosted = offline 16 / 16 per format.
- **Compatibility:** parameter IDs 12 / 12; legacy and new states 8 / 8 per format; AU list order unchanged.
- **Allocations:** none in the editor path, in a 14-row gate and a 14-row stress set (about 1,000 per run before).
- **Validators:** pluginval strictness 10 and auval pass.

## Known Limitations

- **Not modelled:** BBD loss, leakage, feedthrough, noise and saturation, and phase-overlap physics. The original clock is physically non-compliant. No hardware measurements exist.
- **No noise source,** so regeneration never self-starts from silence (intended).
- **Regeneration rebuilds after a mode change** (0.25–7 s), and bypass hides rather than stops an oscillation.
- **CPU:** the relative gate is NOT MET while regenerating (+0.4–0.6 % of a core; accepted).
- **JUCE wrapper residuals:** a listener lock, one-time thread-local allocations, and an AU bypass-property allocation.
- **Platform:** one machine and platform (macOS, arm64).
- **Historical PARTIAL / FAIL verdicts** (K2-A, K2-C2, K3-B P.U02) are kept as recorded.

## Reusable Lessons

1. Fix the clock convention and the capture edge in writing before any delay equation.
2. Render the BBD as transfer events from the integrated clock; prove it against a literal stage oracle.
3. Keep the analog chain around the BBD; its filters and compander set the bandwidth and the noise behaviour.
4. Do not model what nothing constrains; write the measurement plan instead.
5. Make enhancements separate contracts, bit-identical when off, with their own references.
6. Freeze by hash, re-check every earlier set in every phase, and keep failed results.
7. Verify test inputs at the device under test: parameters in the plug-in's state, units in volts, automation on the right thread.
