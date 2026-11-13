# Feedback and Regeneration

How to model a BBD effect's feedback loop faithfully, and how to add sustained regeneration or controlled self-oscillation as a deliberate extension without disturbing the faithful behaviour. The Prismatica F1 / F2 / Extended Feedback work is the worked example; its coefficients are **case-study values**, not BBD constants.

## Contents

- [Two Contracts: Classic and Extended](#two-contracts-classic-and-extended)
- [Measure the Classic Loop Gain](#measure-the-classic-loop-gain)
- [Why a Faithful Loop May Never Oscillate](#why-a-faithful-loop-may-never-oscillate)
- [Where to Add Gain](#where-to-add-gain)
- [A Regeneration Law](#a-regeneration-law)
- [Bounding the Oscillation](#bounding-the-oscillation)
- [Per-Mode Laws](#per-mode-laws)
- [Measuring Onset, Sustain and Recovery](#measuring-onset-sustain-and-recovery)
- [Silence, Idle and Initial Conditions](#silence-idle-and-initial-conditions)
- [Smoothing and Switching](#smoothing-and-switching)
- [Mode Changes During Regeneration](#mode-changes-during-regeneration)
- [Tail, Bypass and Safety](#tail-bypass-and-safety)

## Two Contracts: Classic and Extended

- **Classic** is the circuit's own loop. It is judged against the oracle, and once approved it is frozen by hash.
- **Extended** is a deliberate enhancement, for example a feedback range that sustains or self-oscillates where the circuit cannot.

**Rules:**
- The extension has its **own switch** (or mode) and its **own reference set**.
- With the extension off, the output is **bit-identical** to Classic. Gate it by hash, not by listening.
- The extension changes nothing below its threshold, so approved presets and existing sessions are untouched.
- Presets made for Classic load with the extension **off**; states saved before it existed restore it off.

## Measure the Classic Loop Gain

Several methods exist and they do not agree exactly; report which one a number comes from.

| Method | What it gives |
|---|---|
| Circuit analysis: product of stage gains around the loop at the worst frequency | a bound (*case study:* ≤ 0.54 on the long BBD, 0.61 on the short) |
| Comb peak / trough ratio r on a real signal: \|L\| = (r − 1)/(r + 1) | an in-use estimate (*case study:* about 0.7) |
| **Bisection on an added constant gain G until the loop sustains: L = 1/G\*** | the most direct number for designing an extension (*case study:* 0.46–0.53 on the long BBD, 0.53–0.59 on the short) |

**A compander changes the arithmetic.** A compressor / expandor pair (2:1, then 1:2) is log-linear: between its floor and the swing limits the loop is linear in amplitude, and any gain error in the BBD or the trims is **squared** by the expandor. Verify trims and insertion gain carefully.

## Why a Faithful Loop May Never Oscillate

- **The schematic's feedback maximum often stays well below unity,** at the nominal (assumed) trim positions. *Case study:* a hot setting of two trimmers raised the loop gain to 1.03, and to 1.24 with both at their extremes. The reference then sustained, limited by an op-amp's swing; it was multistable, with a dead zone near the compander floor.
- **"The original pedal self-oscillates" claims usually depend on trims, part tolerances or modifications.** Do not tune Classic to reproduce them; model them as an extension, or as a separately labelled "calibrated unit" variant.
- **Check that onset is not numerical:** it should be independent of the internal rate (*case study:* within 0.006–0.018 across rates).

## Where to Add Gain

**Place the enhancement gain where it cannot change the approved outputs at settings below the threshold.**

*Case study:*
- **Rejected:**
  - raising the trimmers (changes the wet level and the loop at every setting);
  - adding gain inside the loop with rescaled emphasis (the summing network leaks dry into the outputs, so the dry would be re-weighted);
  - changing BBD headroom (changes every mode).
- **Chosen:**
  - add an extra return at the regeneration summer only, through a **copy** of that part of the circuit, driven by (G − 1) times the expandor output;
  - the copy's output is superposed exactly at one node, before that node's swing limiter;
  - the jacks and the mix are untouched.

**Reducing the copy:**
- Keep only the states the extra return actually reaches: the closure of the injection and output nodes through couplings above a tolerance relative to the largest coupling (*case study:* 15 of 25 states).
- Prove the reduction against the full copy (*case study:* within 2.98e-8 V over 90 cases, within one float32 ULP in another check).

## A Regeneration Law

*Case study law (Prismatica F1 / F2), per mode {f0, gMax, vs}:*

```text
G(P) = 1 + (gMax − 1) · smoothstep((P − f0) / (1 − f0)),   smoothstep(u) = u²(3 − 2u),  u clamped to [0, 1]
P    = the engine's smoothed FEEDBACK control; G − 1 is exactly 0 for P ≤ f0
F1 extra return: (G − 1) · x
F2 extra return: (G − 1) · vs · tanh(x / vs)          x = the expandor output (volts)
```

| Parameter | Meaning | How it was chosen |
|---|---|---|
| f0 | control value where the law starts (bit-for-bit Classic below it) | 0.85: above every approved preset's FEEDBACK (0.75) |
| gMax | G at full FEEDBACK | a margin of 17–27 % over the highest measured G\* (1.885), so the loop sustains at full FEEDBACK at every TUNE: 2.2 |
| vs | tanh scale in volts | swept 0.15 / 0.3 / 0.5 V (each doubling adds about 6 dB of sustained level): 0.3 V |

- **Onset is shared by F1 and F2:** tanh has unit slope at zero, so F2's small-signal loop gain, and hence its onset, equals F1's.
- **Above onset they differ:** the tanh saturates the extra return, and the loop gain returns to 1 at a moderate amplitude.

## Bounding the Oscillation

| Voice | Limiter | Result (case study) |
|---|---|---|
| F1 | the circuit's own op-amp swing | all-or-nothing at the rails, about 25 dB above playing level |
| **F2** | a smooth tanh on the **extra return only** | sustained level −15 to −21 dB re 1 V, same onset; **selected** |

**Lessons:**
- **A log-linear compander loop has no amplitude-dependent gain below the rails,** so without an explicit limiter the only bound is the rails.
- **Put the limiter on the added path,** so Classic keeps its own clipping behaviour.
- **Test the extremes:** research gains up to 3.0 stayed bounded (F1 ≤ 2.9 V, F2 ≤ 0.43 V). The product has no output limiter; the tanh is the bound.

## Per-Mode Laws

**One law does not fit loops of different strength.**
- *Case study:* the FILTER MATRIX law (gMax 2.2), applied unchanged to the long-delay modes, sustained only at full FEEDBACK; one setting needed G\* 2.18.
- **The fix: match the margin, not the gain.** gMax × L(1) = 2.2 × 0.572 = 1.26 on the reference loop, which gives gMax = 2.5 on the 12 % weaker long-delay loop.
- Keep f0 and vs, so the onset position and level character match across modes.
- *Case study table (`kRegenLaws`):* Double Track and Chorus {0.85, 2.5, 0.3}; Flange and FILTER MATRIX {0.85, 2.2, 0.3}. FILTER MATRIX was frozen from the earlier approved phase (a `static_assert` guards it).

## Measuring Onset, Sustain and Recovery

| Quantity | Method (case study) | Result (case study) |
|---|---|---|
| **Onset** | bisection on FEEDBACK (or on a constant G in a research build) with a 1 s noise burst, then silence | 0.942–0.959 across modes and TUNE, ±0.003 by excitation |
| **"Sustained" criterion** | the last 10 s stay above −60 dB re 1 V RMS **and** drift less than 0.05 dB/s | — |
| **Hysteresis** | slow 60 s FEEDBACK ramps up and down; crossing −40 dB once each way | none (a ±0.01 apparent lag is dynamic) |
| **Sustained level** | dB re 1 V, last seconds, per mode / TUNE / sweep filter | Double Track −19.5 to −20.5; Chorus −19.1 to −20.1; Flange −18.2 to −20.3; FILTER MATRIX −17.7 (peaks ≤ 0.25 V after input stops) |
| **Recovery** | time to −60 dB after lowering FEEDBACK or switching off | 0.1–0.8 s depending on mode |
| **Echo decay T60** | repeat-envelope slope, 10–70 dB down | Double Track at FEEDBACK 0.95: 4.4–8.1 s Extended against 0.29–1.24 s Classic |
| **Excitation dependence** | 8 different excitations over 600 s | the oscillation mode and pitch depend on TUNE and excitation; level spread 2.7 dB (F2) |

**Report levels in volts** (or dB re 1 V) when the plug-in has an input calibration. A digital threshold at a hot calibration flags a correct sustained tail as decayed.

## Silence, Idle and Initial Conditions

- **Without a noise source, a regenerating loop never starts from digital silence.** *Case study:* 600 s of exact zeros from reset. This is a feature: a state restored at full FEEDBACK is silent until played.
- **Any input starts it:** a 1 µV impulse is enough. Make sure the extension has no dead zone just above onset (*case study:* G / G\* = 1.17–1.27 at full FEEDBACK).
- **Idle cost:** run the extra path only while it matters. *Case study:* once G = 1, the copy runs until every state is below 1e-10 V, is then cleared and skipped, and costs nothing until needed.
- **`reset()` and re-prepare must silence it completely,** and be bit-deterministic.

## Smoothing and Switching

- Smooth FEEDBACK (*case study:* a 30 ms one-pole per sample).
- Ramp the extension's enable (30 ms), and ramp any limiter blend (30 ms).
- Snap exactly to the target when within 1e-12, so steady states are bit-reproducible.
- **Test toggle edges with twin renders:** the same render with and without the event, compared afterwards. Step-ratio and "max sample step" heuristics fail on signals whose own slope changes: oscillation modes, LFO, regrowth.

## Mode Changes During Regeneration

If the mode crossfade empties the incoming BBD, which is usually right for Classic transitions, **a sustained regeneration does not carry over: it rebuilds.**

| Transition (case study) | Rebuild time |
|---|---|
| between the two short-delay modes; Chorus → FILTER MATRIX | 0.25–0.5 s |
| into Flange from a long-delay mode; into FILTER MATRIX from Double Track | 2.25–2.75 s |
| into Double Track | 3.0–5.5 s |
| into Chorus | 5.75–6.75 s |

**Document it as intended behaviour,** or design a different transition deliberately: for example, carrying the BBD contents, with its own references and approval. Do not patch it quietly.

## Tail, Bypass and Safety

- **Tail.** A loop that can sustain makes any finite tail a lie. *Case study:*
  - the plug-in reports an **infinite** tail in both extension states, because JUCE 9.0.3 cannot notify a host of a tail change, and a host that cached a finite tail could cut off a sustained regeneration;
  - consequence: hosts may keep processing an idle instance, and silence costs what audio costs.
- **Bypass hides an oscillation; it does not stop it.** Document this for users.
- **Programs and legacy states load with the extension off.**
- **Test bounds under abuse:** hot input, every-sample automation of FEEDBACK and the switch, mode changes, many instances, a long (600 s) run. Every output must be finite.
