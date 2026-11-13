# BBD Fundamentals

What a bucket-brigade device does, the conventions you must pin down before writing an equation, and the non-idealities a model may or may not carry. Numbers marked *case study* come from one MN3008/MN3009 project (see [prismatica-case-study.md](prismatica-case-study.md)); everything else is general.

## Contents

- [Operation](#operation)
- [Conventions to Fix First](#conventions-to-fix-first)
- [Delay, Sampling and Bandwidth](#delay-sampling-and-bandwidth)
- [Two Outputs and Image Cancellation](#two-outputs-and-image-cancellation)
- [Clock Drive Requirements](#clock-drive-requirements)
- [Bias, Headroom and Gain](#bias-headroom-and-gain)
- [Non-Idealities](#non-idealities)
- [Datasheet Reading Rules](#datasheet-reading-rules)

## Operation

A BBD is a chain of N capacitor stages separated by MOS switches. Two complementary clock lines (CP1, CP2) open alternate switches, so charge moves one stage per **half** clock period. The input is captured on one phase, travels down the chain as a sampled (discrete-time, continuous-amplitude) value, and is read by source followers at the end.

- **Sampled but not quantized:** a BBD is a sample-and-hold delay line. It aliases like any sampler and needs analog anti-alias and reconstruction filters around it.
- **The delay is set by the clock, not by memory length:** changing the clock frequency changes the delay of every sample in flight. That is how chorus, flange and vibrato are made, and it means each sample's delay depends on the clock **history** while it travels, not on the current clock alone.
- **About N/2 samples are in flight:** with a two-phase chain, alternate stages hold samples. Parts with a 2 × N/2 structure exist; read the datasheet's block diagram.

## Conventions to Fix First

Write these down before any equation; most BBD modelling errors are convention errors.

| Question | Why it matters |
|---|---|
| What does f_CP mean: the frequency of **each** clock line, the master oscillator before a divider, or the transfer rate? | the same "delay = N / (2 f)" is off by 2× under another convention |
| How many transfers per clock period? (two, for a two-phase BBD) | sets the time per stage |
| On which phase edge is the input **captured**? | sets the latency and which output is "first" |
| How many stages does the signal pass to reach each output? (OUT1 after N, OUT2 one stage later, for example) | sets OUT2's lag |
| What does the output do between transfers (zero-order hold, droop)? | adds T/2 of delay and the sin(x)/x response |
| Where is the switching threshold relative to the clock swing? | moves every event by tens to hundreds of ns at real edge rates; usually an assumption |

**Case study convention** (MN3008/MN3009, Panasonic two-phase):
- f_CP is the frequency of each of the two complementary clock lines. The master oscillator runs at 2·f_CP because a CD4013 divides by two.
- T = 1/f_CP; one transfer per half-period.
- Capture on CP1 activation.
- OUT1 on stage N, OUT2 one transfer (T/2) later.
- Outputs are zero-order holds.

## Delay, Sampling and Bandwidth

Under the two-phase convention above:

- **Capture to OUT1:** (N − 1) · T/2.
- **OUT1 phase delay including the hold:** N · T/2 = **N / (2 f_CP)**.
- **Datasheet check (case study):** MN3008 (N = 2048), f_CP 10–100 kHz → 102.4–10.24 ms; MN3009 (N = 256), 10–200 kHz → 12.8–0.64 ms. "tD = N / (2 f_CP)" holds at both ends of both ranges, but the datasheets state the limits, not the formula: derive it, then check it against the limits.
- **Variable clock:** a sample's delay is the **sum of the half-periods that elapse while it is in flight**, not N/(2 f_CP(now)). A model that computes a read position from the current clock alone gets modulation wrong (pitch, symmetry of vibrato). See [clock-and-modulation.md](clock-and-modulation.md).
- **Input sampling rate** is one capture per clock period (f_CP under this convention), so the anti-alias filter must remove content above f_CP/2 at the **highest delay** (lowest clock) the design uses.
- **The usable audio bandwidth shrinks as the delay grows.** Long-delay BBD effects are dark partly by necessity: the filters are set for the lowest clock.

Other conventions exist (for example "sample rate = 2 f_CP"). Convert to yours explicitly and cite where each number came from.

## Two Outputs and Image Cancellation

Two-phase BBDs often offer OUT1 and OUT2, one transfer apart. Summing them equally:
- averages the two half-period holds;
- cancels the first sampling image at f_CP;
- adds a quarter-period of delay at equal weights (N/(2 f_CP) + T/4).

Case study: at balance 0.5 the image measured −63 to −65 dBc, against about −46 dBc at 0.25 or 0.75. The balance trimmer is therefore a **fidelity** control, not just a level control. A model that keeps only OUT1 must add reconstruction filtering to match the image level.

## Clock Drive Requirements

Datasheets specify what the clock must satisfy, and real pedal clocks often do not:
- edge times;
- the **cross point** (the voltage where CP1 and CP2 cross);
- maximum pulse width;
- clock-line capacitance;
- the amplitude relative to the supply.

**Case study:**
- **Cross point:** a CD4013 Q/Q̄ drive crossed at −6.9 to −7.5 V from the high rail, against a required 0 to −3 V. That is set by the Q/Q̄ topology, whatever the drive strength.
- **Overlap:** both lines sat below the threshold for 244–726 ns per transition.
- **Result:** the clock is physically **non-compliant**.
- **What that means:** the functional model still assumes clean transfers. The audible effect of the overlap could not be bounded without hardware, so it was recorded as UNRESOLVED rather than modelled.

Lesson: check the clock against the datasheet. If it fails, decide explicitly whether the model represents the ideal device or the pedal as built, and say which.

## Bias, Headroom and Gain

- **Input DC bias** sets where the signal sits in the BBD's linear window. Bias trimmers are adjusted by hand on real units, so a model's "nominal" bias is an assumption unless the service manual specifies the procedure.
- **Headroom is asymmetric and soft** at the window edges. Case study:
  - a smooth softplus window was fitted to digitized datasheet curves, Vo(x) = L + w·sp((y − L)/w) − w·sp((y − U)/w), with y = s·x + c and sp(z) = ln(1 + e^z);
  - it was validated only at the datasheet's test conditions; an extrapolation elsewhere is labelled as such;
  - mid-trim bias cost about 3.5 dB of headroom on a typical part.
- **Insertion gain** is specified loosely (case study: −4 to +4 dB guaranteed) and varies with clock frequency. Only relative curves are identifiable from datasheets.

## Non-Idealities

| Mechanism | Typical model form | Identifiable from datasheets? |
|---|---|---|
| **Charge-transfer inefficiency** (CTI, ε per transfer) | a high-frequency roll-off; a literature form is \|H\| = exp(−N ε (1 − cos 2π f / f_CP)) | rarely: ε trades off against the hold aperture, the output summing and the unknown test filter. The case study could only bound N ε ≤ 0.018 *if* everything else were ideal. |
| **Leakage / droop** at low clock rates | decay of held charge between transfers | no |
| **Clock feedthrough** | clock-frequency components at the output, removed by the reconstruction filter | no amplitude data in typical datasheets |
| **Noise** | white plus clock-related, after the compander | only as A-weighted maxima, which "shape by assumption" anything fitted to them |
| **Distortion floor** | 0.3–0.6 % typical at the test level | partly (THD vs level curves) |
| **Phase overlap** | stages briefly transparent while both phases conduct | no; an exploratory mixing law showed the output is extremely sensitive to an unbounded parameter |

**Rule:** add a non-ideality only when evidence constrains it (a measurement, or a datasheet curve at relevant conditions). Otherwise record it as not modelled and keep a hardware measurement plan. Structure that nothing constrains is a tuning knob, not a model.

## Datasheet Reading Rules

- Hash and archive the exact datasheet revision you read.
- Separate guaranteed limits from typical curves. Do not calibrate to a "max only" figure as if it were typical.
- Digitize curves reproducibly (record the method and the points). **Never interpolate raw digitized points into a nonlinearity:** pixel steps become distortion. Fit a smooth function and validate it against points it was not fitted to.
- Block diagrams in datasheets are sometimes the only source for stage structure; label conclusions drawn from them as inferred.
