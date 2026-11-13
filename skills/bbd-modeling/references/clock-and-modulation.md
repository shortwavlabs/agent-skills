# Clock and Modulation

The clock is the BBD effect's main control: it sets the delay, the modulation, the bandwidth and, through the anti-alias limits, the tone. This file covers the clock oscillator and its control voltage, LFOs, how to render a variable-clock BBD in real time, and what happens at discontinuities and mode changes.

## Contents

- [Clock Oscillator and CV Law](#clock-oscillator-and-cv-law)
- [LFO and Control Network](#lfo-and-control-network)
- [Rendering a Variable Clock](#rendering-a-variable-clock)
- [Host Rate, Internal Rate and Aliasing](#host-rate-internal-rate-and-aliasing)
- [Pitch Modulation](#pitch-modulation)
- [Control-Rate Grid and Automation Timing](#control-rate-grid-and-automation-timing)
- [Stereo and Multiple BBDs](#stereo-and-multiple-bbds)
- [Discontinuities and Mode Transitions](#discontinuities-and-mode-transitions)

## Clock Oscillator and CV Law

Pedal clocks are commonly:
- a dedicated driver IC (MN3101-class) with its own duty and drive specifications; or
- a discrete relaxation oscillator (current source charging a capacitor, comparator reset) followed by a **÷2 flip-flop** that produces the two complementary phases.

**Derive the CV → period law from the oracle, not from an idealized formula.**
- *Case study:* period = 8.187 µs/V × (CLK_CV − 0.7225 V) above 4 V. Below 4 V the comparator's delays dominate.
- The real-time engine therefore interpolates the period in a 24-point table extracted from SPICE, with the CV clamped to the simulated 1.2–13.2 V range.

**Calibrate the clock trimmer from the documented procedure, and resolve ambiguous wording.**
- *Case study:* "100 µs at TP#1" could mean a full period, a half-period or the master oscillator period. Only the reading "full period of one clock line (10 kHz)" was consistent with the circuit. The calibrated trim moved the delay ranges substantially from the mid-travel default.

**Report the clock range per mode,** and check it against the BBD's limits. *Case study:*
- the long-delay part ran from 10 kHz up to about 80 kHz (mode 1) or 94 kHz (mode 2, sweep centre) at the calibrated trim;
- the short-delay part ran 10–208 kHz, slightly above its 200 kHz specification at one control extreme;
- one mode reached 1.75 MHz for a few milliseconds at power-up.

## LFO and Control Network

- **Model the LFO as the circuit makes it.** Commonly a Schmitt trigger plus integrator triangle. Its trip points depend on op-amp output limits: *case study* "about one diode drop" on an LM324.
- **Map each pot through its own transfer.** Rate pots are often steep near one end (*case study:* 0.017–15.2 Hz). Width controls are frequently a loaded cross-fade between the tune voltage and the LFO, not a linear depth.
- **Keep the control network's filters:** RC smoothing of the LFO before the clock CV, and switchable capacitors such as a "sweep filter" that slows the modulation. Closing such a switch shares charge between capacitors, so model the switch event, not just the two steady states.
- **Reduce the network to its few real states.** *Case study:* a follower-isolated control network reduced to two capacitor states. Trapezoidal integration with 2×2 closed-form algebra matched the oracle within 6e-12 V.
- **Know which modes route the LFO to the clock.** In multi-mode pedals some modes force a static CV (delay or "filter" modes), and some feed the LFO through a resistor that a buffer swamps.

## Rendering a Variable Clock

**A BBD is a clocked sample-transfer system, not a fractional delay line.** Two exact formulations:

**1. Transfer events (phase accumulation).**
- Integrate φ(t) = ∫ 2 f_CP dt. Transfer k happens where φ crosses k.
- On a capture transfer, take the input interpolated at the fractional event time. On an output transfer, update the held output.
- Between transfers the outputs hold; integrate the hold over the host sample interval (box average) to get the zero-order-hold response.
- Store samples in a ring indexed by transfer count: O(1) per transfer.
- The number of transfers per host sample is bounded by the maximum clock: ⌊2 f_max / fs⌋ + 1. Size fixed arrays from that bound at prepare time.

*Case study:*
- the phase step held f_CP across each internal sample (left Riemann);
- fractional event times came from that step;
- captures were resolved one sample late, because the next input sample depends on this sample's output through the feedback loop. That is safe while the read margin, N − 1 transfers, is large;
- an independent stage-array oracle matched the event times and counts exactly over 195,000 transfers, under fixed, stepped, ramped and FM clocks.

**2. Delay-time integration.**
- Track, for each stored sample, the time at which it will reach the output, from the integrated clock.
- Read with interpolation.
- Equivalent in principle, but easier to get subtly wrong (rounding, buffer growth).

**Common wrong formulation:** a fractional delay line whose read position is N / (2 f_CP(now)) × fs. It modulates the delay of samples already in flight, as if the clock had always been at its current value. It mis-renders pitch and asymmetry under fast modulation. Use it only as an explicit approximation, with its error measured against an event-based reference.

## Host Rate, Internal Rate and Aliasing

- **The BBD's own sampling** happens at f_CP, inside the model, and is rendered exactly by the event formulation. **The host-rate sampling of the model's analog parts** is a separate question: the filters, compander and nonlinear limits.
- **Choose the internal rate from the filter-realization error, not from CPU.**
  - *Case study:* at 1× host rate, the worst filter path missed its 0.1 dB / 1° bound (0.43 dB, 2.9°). The 1× vs 2× output residual was only −28.5 to −31.2 dB.
  - 2× met the bound for under 1 % of a core and 20 samples of latency at 44.1 / 48 kHz.
  - So the policy is 2× up to 50 kHz and 1× above.
- **Resampler latency must be integer and reported.**
  - *Case study:* a causal copy of the offline reference's 41-tap half-band FIR (Kaiser β 5) gives 2 × 20 internal samples = 20 host samples.
  - The first 20 internal samples after reset are skipped, so the real-time output matches the zero-phase offline reference at −104 to −133 dB.
- **Accept a bounded host-rate range and say what happens outside it.**
  - *Case study:* the engine supports 22.05–192 kHz host rates, and outputs zeros elsewhere.
  - The plug-in passes audio through instead, because a silent insert looks like a fault in a session.

## Pitch Modulation

- **The instantaneous pitch ratio of the delayed signal** is 1 / (1 + dτ/dt), where τ is the delay seen by the sample at capture.
- **Expect large excursions at full settings.** *Case study:*
  - one chorus mode reached 77 % (95th percentile) pitch deviation at mid rate and full width; classic chorus depths need width ≲ 0.1;
  - with the sweep filter off, the excursion grows with rate. It reached 3 semitones at half width, and 92 % at full settings.
- **Before calling a pitch extreme a defect, compare it with the reference.** *Case study:* "too wild" turned out to be circuit-correct. It was addressed with presets that use the sweep filter, not by changing the DSP.

## Control-Rate Grid and Automation Timing

- **A control grid is acceptable** (*case study:* 2 kHz, with CLK_CV linearly interpolated between ticks) if its phase is integer arithmetic (i · f_tick − k · fs), so block size cannot change it.
- **A causal grid computes tick k + 1 when tick k becomes current,** so host automation lands one tick later than in an offline reference that looks ahead. Remove that known delay before computing residuals; otherwise a correct engine fails (*case study:* −9.2 dB unshifted, −50.6 dB shifted).
- **Apply parameter targets at the block's first sample, and smooth inside the engine** (per sample, or per control tick). Only one layer smooths: the plug-in wrapper must not smooth the same parameter again.

## Stereo and Multiple BBDs

- **Many "stereo" BBD pedals** derive two outputs from one delay (dry ± wet). Their mono sum is the dry signal. Never generate a mono output by averaging such a pair; use the pedal's own mono output.
- **When a pedal has two BBDs and a mode switch selects one,** both may run in hardware. A model need only run the selected one, but must handle the switch (below).
- **True stereo BBD effects** (two clocks or quadrature LFOs) need each clock's phase relationship modelled from the circuit.

## Discontinuities and Mode Transitions

- **A mode change usually changes the BBD, the clock range and the control routing at once.** Crossfade between two engine instances (constant-sum, not equal-power, when both share the dry signal: equal-power raises the dry by up to 3 dB).
- **Copy the running state into the incoming instance:** filters, compander, LFO, smoothing. Clear the incoming BBD's contents while keeping its clock phase, and ramp captures in over a few ms. The incoming wet signal then arrives after its own delay.
- **Keep the modulation networks of every mode running** ("shadow" control states). *Case study:* starting a new mode's control network "settled" from the current LFO value made it sweep beyond its steady range, a 24 dB dip on entering one mode.
- **Judge a transition against the same render's steady state, not against separate renders:** separate renders compare different histories.
- **With regeneration,** an emptied incoming BBD means the regeneration must rebuild. See [feedback-and-regeneration.md](feedback-and-regeneration.md#mode-changes-during-regeneration).
- **Invalid input** (NaN, ±Inf, absurd levels) should become 0, not a clamped extreme. A clamped value is still a huge step into long-memory coupling networks (*case study:* a seconds-long transient).
