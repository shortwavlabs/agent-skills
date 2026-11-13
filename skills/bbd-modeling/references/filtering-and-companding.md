# Filtering and Companding

A BBD is never used bare: pre-emphasis, an anti-alias filter, the BBD, a reconstruction filter, de-emphasis, and often a compander (compressor before, expandor after) together make the "BBD sound". Model the chain the circuit actually has, from the schematic values, and do not replace it with an EQ curve unless the approximation is labelled and validated.

## Contents

- [The Typical Chain](#the-typical-chain)
- [Read Values From the Schematic](#read-values-from-the-schematic)
- [Discretizing the Filters](#discretizing-the-filters)
- [Compander](#compander)
- [Calibration and Gain Staging](#calibration-and-gain-staging)
- [Signal-Dependent Behaviour](#signal-dependent-behaviour)
- [Noise Floor](#noise-floor)

## The Typical Chain

```text
input buffer -> pre-emphasis -> compressor -> anti-alias LPF -> BBD -> output summing/balance
             -> reconstruction LPF -> expandor -> de-emphasis -> wet level -> mix / feedback
```

- **Pre-emphasis / de-emphasis:** boost highs before the noisy, band-limited BBD and cut them after, improving signal-to-noise. Sometimes the pre-emphasis stage also sums the regeneration signal.
- **Anti-alias and reconstruction:** typically 2nd- to 3rd-order active filters (Sallen-Key) set for the **lowest** clock the product uses.
- **Compander:** halves the dynamic range in dB before the BBD and restores it after, so BBD noise is pushed down when the signal is quiet.

*Case study (EHX Polychorus-style circuit):*
- **Input buffer:** gain −1.74, pole at 8.67 kHz.
- **Pre-emphasis / regeneration sum:** lifts the compressor input by about 4 dB from 400 Hz to 4 kHz.
- **Anti-alias:** an RC followed by a Sallen-Key; 3rd order in total.
- **Reconstruction:** a Sallen-Key followed by an RC.
- **De-emphasis:** an RC network.
- **Result:** the wet path's bandwidth is about 4 kHz, and the expandor **doubles** the filters' attenuation in dB for steady tones (−77 dB at 10 kHz).

## Read Values From the Schematic

- **Take every R and C from the schematic** and record the reading conventions. For example: unit-less capacitor values read as µF, the convention of that manufacturer's drawings.
- **Keep a decisions log** of every ambiguous reading, with its confidence.
- **Op-amps:** ideal op-amps are usually adequate inside the audio band. Check the error where the gain-bandwidth matters. *Case study: up to 0.9 dB above 6 kHz with ideal op-amps.*
- **Trimmers:** "nominal" positions are assumptions unless the service procedure says otherwise. Many drawings calibrate only the clock trimmer.

## Discretizing the Filters

- **Derive the filter from the circuit:** nodal analysis (MNA) of each linear section gives a rational transfer function. Convert it to zeros, poles and gain, and discretize per section.
- **Choose bilinear or impulse-invariant per path, by measured error:** do not pick one by habit. *Case study: bilinear alone left 0.50 dB error in one path; mixing bilinear with impulse-invariant for the high-frequency part reached 0.08 dB.*
- **Check the library's conventions in the time domain.** *Case study: scipy's zpk conversion silently advanced strictly proper filters by one sample. A time-domain comparison found it; explicit z⁻¹ sections fixed it.*
- **Mind the rates:** the filters around a BBD run at the host or internal audio rate, while the BBD runs on its own clock. Keep that boundary explicit (see [clock-and-modulation.md](clock-and-modulation.md)).

## Compander

**Model structure.** Model the compander IC's internal blocks and keep the circuit's external networks in the model. Whether a channel compresses or expands comes **only** from how the external circuit connects it. *Case study: an NE570-family part. No vendor model existed, so a project model was calibrated to the datasheet.*

| Block | Typical law (NE570 family) |
|---|---|
| Rectifier | full-wave \|i\| plus a small bias current, averaged by the rectifier capacitor |
| Control current | I_G = 2 · avg\|I_IN\| |
| Gain cell | I_OUT = I_IN · I_G / I₁ |
| Gain-cell saturation (empirical) | I_L = I_IN / (1 + (\|I_IN\|/I₁)^p)^(1/p) |

**Time constants** come from the external capacitor and internal resistor: 10 kΩ × 1 µF = 10 ms attack and release in the case study. Verify them in circuit, not only on the datasheet.

**Realtime identity worth knowing.** An RC envelope of a squared signal satisfies d(e²)/dt = 2(K|x| − e²)/τ. So a feed-forward envelope of K|x| with time constant τ/2 reproduces the feedback detector loop **exactly**, not as an approximation. The gain is then g = K / (√env + small bias term). This removes a delay-free loop from the realtime model.

**Calibration items that are assumptions** (label them):
- op-amp output headroom inside the IC;
- the saturation exponent;
- the impedance at the distortion-trim pin;
- the feedthrough term.

*Case study:* the idle limit cycle (12.5 mV pp) existed only because of the feedthrough term, so it is a model property until measured.

## Calibration and Gain Staging

- **Define the digital ↔ volts contract once:** which voltage at which node 1.0 digital represents. *Case study: 1.0 = 1 V peak at the input jack.* A plug-in then exposes an input calibration parameter in dBu, so users can match their interface's level.
- **Headroom depends on that contract:** the BBD's linear window and the compander's clipping are in volts. A hot input changes the timbre, as it does on hardware.
- **Report levels in both units** when a threshold matters. *Case study: at +24 dBu calibration a sustained output reads −43 dBFS while it is −19 dB re 1 V. A digital threshold flagged it as "decayed" when it was not.*

## Signal-Dependent Behaviour

- **Program-dependent wet/dry ratio:** the compressor's detector sees the full pre-emphasized band, ultrasonic content included, while the expandor sees only the band-limited wet signal. Their gains therefore do not cancel exactly on real material.
- **Distortion partly cancels across the compander:** *case study 0.62 % → 0.08 %.* Measuring one half alone misleads.
- **Comb depth depends on the stimulus:** white noise, single tones and guitar give different notch depths. *Case study: 6–9 dB on broadband noise, about 17 dB on tones, 12–25 dB on guitar DI.* Specify the stimulus in every criterion.

## Noise Floor

- A compander-based BBD is quieter on loud passages than on soft ones. Its residual noise "breathes" with the expandor.
- **Do not fit a noise model to A-weighted maxima:** it would be shaped by assumption. Leave noise unmodelled (silence is silent) until it is measured, and say so; see [analog-character-research.md](analog-character-research.md).
