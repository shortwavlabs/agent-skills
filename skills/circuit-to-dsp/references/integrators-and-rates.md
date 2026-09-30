# Integrators, Internal Rate And Oversampling

## Contents

- What can set the internal rate
- Comparing integrators
- Choosing the minimum internal rate
- Oversampling-factor policy
- Measure the production resampling filters
- Latency and bypass
- Control update cadence
- Performance measurement
- Checklist

## What Can Set The Internal Rate

The internal (oversampled) rate of a circuit model is an accuracy requirement with several possible drivers. Measure each; do not assume aliasing is the only one:

| Driver | Symptom when the rate is too low |
| --- | --- |
| Aliasing of nonlinear products | Inharmonic energy in the audio band (see the `guitar-dsp` skill's `references/aliasing-oversampling.md`) |
| Stiff analog poles (op-amp gain-bandwidth poles, small parasitic capacitances) | Rate-dependent gain/phase errors, ringing, erratic error versus rate |
| Discretisation of the audio-band response | Frequency warping and phase error near the top of the band |
| Nonlinear solver accuracy | Large per-step jumps across device knees; more iterations; missed fast transitions |
| Coupling lags (explicit one-step coupling of shared nodes) | Error that falls with rate |

## Comparing Integrators

Do not pick an integrator because it is A-stable or traditional in virtual-analog work. Compare candidates on the actual model:

- backward Euler (L-stable, first order, strongly damped);
- trapezoidal / bilinear (A-stable, second order; maps very stiff poles near z = −1, so they ring or produce rate-sensitive error);
- BDF2 (L-stable, second order, needs history);
- TR-BDF2 or other L-stable multi-stage methods (second order, stiff-accurate, more work per sample).

Procedure:

1. Build a **stage-isolated** experiment driven by the oracle's own signal at the stage input (amplitude and phase).
2. Use as reference the **same model** run at a much higher rate (discretisation error), and separately the oracle (total error). Never compare one integrator's discretisation error with another quantity's total error.
3. Measure, over the operating grid and several rates: in-band harmonic/vector error, phase, transient error, sensitivity to small rate changes (dense sweeps, including non-power-of-two rates), numerical ringing, and CPU (stages and solves per sample).
4. Choose the cheapest method that meets the error budget with margin at every production rate.

*Case study: trapezoidal integration first looked adequate because its discretisation error was compared with a total error; decomposed properly, it exceeded the continuous-model error at some production rates, and an L-stable two-stage method was required.* (Useful detail for TR-BDF2: with γ = 2 − √2 both stages use the same companion conductance 2C/(γh), so one set of coefficients serves both stages.)

## Choosing The Minimum Internal Rate

1. Sweep the internal rate densely (not only the power-of-two candidates) over the complete gated case grid.
2. Separate the smooth trend (error falling roughly with the method's order as the step shrinks) from isolated spikes. Spikes at rates where a test tone has an exact integer number of samples per period are **measurement alignment** effects; evaluate them with a sub-sample phase ensemble (see `validation-gates.md`) rather than choosing rates around them.
3. Choose the minimum validated rate from the smooth, phase-averaged behaviour with margin, and keep the exact-period cases as absolute gates.
4. Record which driver sets it; when the driver is a stiff pole, the requirement does not relax at high host rates.

## Oversampling-Factor Policy

Define an **algorithm**, not a list of common host rates:

```text
factor = smallest power of two in {1, 2, 4, ..., max} with hostRate * factor >= minimumValidatedRate
if no factor reaches it: use max and flag "degraded accuracy" (unvalidated)
internal rate = hostRate * factor, in [minimum, 2 * minimum) for supported host rates
```

Test the policy at many host rates, including unusual ones (22.05, 32, 50, 176.4, 200, 352.8 kHz and above), and state which internal rates the gates must cover (every rate the policy can produce, or its extremes and the rates of the common host rates).

## Measure The Production Resampling Filters

Validate the oversampler actually shipped, not an ideal one:

- alias probes (coherent sines at several frequencies and levels) through the real up/down filters at each supported host rate;
- a broadband, guitar-like or program-like signal compared against a higher factor;
- passband flatness to 20 kHz and the filter's phase and group delay;
- latency (integer or fractional) and its effect on dry/wet alignment;
- CPU of the filters themselves.

Polyphase IIR half-band filters have non-linear phase: waveform comparisons of the host-rate output with an analog reference will be dominated by filter phase at high frequencies even when magnitude is flat. Gate circuit fidelity at the island's internal rate (stage/island isolation) and gate the resampling path separately (aliasing, passband, latency).

## Latency And Bypass

- Report the latency the host must compensate (prefer integer latency when the filters allow it) and keep it constant for a given configuration.
- Report it early (before the first prepare if the framework allows) and update it when the rate or factor changes.
- Bypass through a dry path delayed by exactly the reported latency, with a crossfade; test that the bypassed output equals the delayed input bit for bit once the crossfade completes.
- Framework specifics (JUCE latency, bypass parameters, lifecycle) are in the `juce-plugin` skill.

## Control Update Cadence

Coefficient rebuilds cost CPU; stale coefficients cost accuracy. Decide by measurement against a time-varying reference (see `circuit-reduction.md`):

- rebuild whenever a smoothed control has changed, per integrator stage, interpolating controls within the host sample;
- versus holding coefficients for a whole host sample;
- versus rebuilding only when the change exceeds a threshold.

Cache coefficients per control value and stage kind so static controls cost nothing. *Case study: holding coefficients for a host sample raised automation error from about −84 dB to −41 dB while saving well under one percentage point of CPU; thresholds were worse still.*

## Performance Measurement

- **Back-to-back** benchmarks (process blocks as fast as possible on one thread) measure kernel cost. **Live callback** duty cycle (time per callback divided by the block period, inside a real audio device callback) includes clock scaling and scheduling; it is often much higher. Sleep-paced synthetic loops can mislead in both directions because of CPU frequency scaling. Report which one you measured.
- Report mean, p95, p99, p99.9, worst block, block-period percentage, overruns, and solver statistics (evaluations per solve, re-seeds, cap hits) across host rates, block sizes, mono/stereo, static and continuously automated controls, and normal and stress signals.
- Re-run a single outlier before calling it a regression; call it a regression only when it repeats.
- Keep correctness gates (machine-independent) separate from performance gates (machine-specific, with the machine named).

## Checklist

- [ ] Rate drivers identified and measured (aliasing, stiffness, warping, solver, coupling).
- [ ] Integrators compared on discretisation error versus the same model at a high rate, and total error versus the oracle.
- [ ] Minimum internal rate chosen from dense, phase-averaged sweeps; exact-period cases kept as absolute gates.
- [ ] Oversampling factor chosen by an algorithm covering unusual host rates, with a degraded flag.
- [ ] Production filters measured: alias, broadband, passband, phase, latency, CPU.
- [ ] Latency reported early and constant; bypass latency-matched and bit-exact.
- [ ] Control update cadence chosen from automation measurements.
- [ ] Back-to-back and live-callback performance reported separately, with solver statistics.
