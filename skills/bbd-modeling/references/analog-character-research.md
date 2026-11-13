# Analog-Character Research Note

Imperfections a BBD product might model later, and what each would need before it could be modelled honestly. This is a **research agenda, not an implementation guide**. A circuit-faithful model that leaves these out is not wrong: say what is omitted.

| Topic | Physical origin | Evidence needed before modelling | Risk if invented |
|---|---|---|---|
| **Hiss** | BBD thermal and switching noise, compander-modulated; op-amp noise | measured output noise spectra at several clock rates and levels, with and without signal, after the compander | a noise source fitted to A-weighted datasheet maxima is shaped by assumption |
| **Clock instability** | oscillator jitter, supply ripple on the clock CV, temperature drift | measured clock period statistics (jitter spectrum, drift over warm-up) on real units | invented "wobble" is a tape effect in BBD clothing (below) |
| **Component variation** | resistor and capacitor tolerances; transistor and BBD unit spread; trim positions | a population of measured units, or at least tolerance-driven sensitivity analysis with stated distributions | a single "vintage" preset presented as typical |
| **Charge-transfer imperfections** | CTI, leakage at low clock rates, clock feedthrough | frequency response and droop measured against the clock rate on one device, under a compliant and the original clock | non-identifiable parameters that tune the sound arbitrarily |
| **Gain-stage noise** | op-amps, compander gain cells | measured noise floor per stage, or datasheet noise densities with the circuit impedances | — |
| **Control-voltage fluctuations** | LFO ripple, potentiometer noise, supply coupling into the clock CV | scope captures of the CV at the oscillator, idle and moving | clicks or warble that the hardware does not have |

## Cautions

- **Wow and flutter are tape-transport phenomena** (capstan and reel speed variation). A BBD's delay varies only through its clock. Slow random clock modulation can resemble them, but describe and justify it as clock instability, measured on the BBD circuit, not as tape character.
- **Keep extensions separate:** an analog-character feature is a new behaviour. Give it its own switch or revision, its own references, and leave the frozen circuit-fidelity references untouched.
- **Measure with the instrument the claim needs:** noise needs a known gain structure and bandwidth; jitter needs a time-interval analyser or a long scope capture; population claims need several units.

*Case study status:* none of these was modelled. The project kept a hardware measurement plan (clock cross point and edges, clock-line capacitance, output DC and impedance, gain against clock, headroom, frequency response, noise, feedthrough, the same BBD under the original and a compliant clock, bias) for a later phase.
