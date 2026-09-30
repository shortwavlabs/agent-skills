# Case Study: An Op-Amp Diode-Clipper Overdrive (SD-1-Style)

**CASE STUDY. Every number here belongs to one circuit, one oracle and one product.** Use it as an example of the method, never as defaults. The general principles are in the other references of this skill and of the `spice-circuit-modeling` skill; each lesson below links to its principle.

## The Project In One Paragraph

An asymmetric diode-feedback overdrive built around one dual-op-amp package (one half in the clipping stage, one in the tone stage), with a passive-active tone network, JFET electronic switching (effect/bypass flip-flop), transistor input/output buffers and a shared half-supply bias node was modelled from a transistor-level ngspice netlist into a JUCE AU/VST3 plugin. The shipped model is one oversampled island per channel with 19 continuous physical states, **one** scalar nonlinear solve per integrator stage, an L-stable two-stage integrator (TR-BDF2) at an internal rate of at least 352.8 kHz reached with power-of-two oversampling (8× at 44.1/48 kHz), and an explicit one-step coupling of the bias node. SPICE stayed offline as the oracle and golden-data source.

## Decisions And Surprises

| Lesson | What happened | Principle |
| --- | --- | --- |
| Vendor op-amp models were less robust than a project model | The only exact-part macro failed the first transient step; four substitute macros failed start-up, pre-AC operating-point selection or statement-order stress (one failed 311 of 2000 orders; inspection found suspect clamp and output-stage structures, but no single root cause was proven). A transistor-level datasheet-calibrated project model had 0 failures in 35,500 runs over two engines and was closer to the datasheet where it mattered (input bias current 57 nA vs datasheet 60 nA, against 140 nA for the old macro). | `spice-circuit-modeling`: device-model-qualification |
| Statement order exposed fragility | Reordering element statements, which the KiCad export does after unrelated edits, made the old model fail start-up or land in the wrong flip-flop state. A keyed, de-duplicated permutation harness run order-for-order in two engines turned that into a measurable gate. | `spice-circuit-modeling`: numerical-qualification |
| Bistable operating points | Standalone `.op` before `.ac` could fall back to stepping methods that ignore `.nodeset`, giving meaningless AC gain. A raised DC iteration limit plus explicit state assertions fixed the procedure; the aid was kept as documented scaffolding. | `spice-circuit-modeling`: numerical-qualification |
| A coarse sweep hid a device-law error | The realtime diode law continued a recombination term into reverse bias; the simulator freezes it below −3·N·Vt. A coarse branch sweep showed 0.81 mV worst error; a 1 nA-resolution sweep showed 1.27 mV (over a 1 mV gate). Implementing the simulator's branch gave 0.68 mV. | `spice-circuit-modeling`: device-model-qualification; `nonlinear-solvers.md` |
| Shared bias coupling mattered | Dropping one return current into the shared bias node caused up to 27.7 dB extra transient error. Explicit and implicit coupling agreed within 0.9 dB worst; explicit was 8 % cheaper. | `circuit-reduction.md` (coupled nodes) |
| An "off" JFET's capacitances mattered | At minimum level, feedthrough via the off switch's gate-drain/gate-source capacitances set a 15 dB error until modelled. | `circuit-reduction.md` (partition by physics) |
| The tone-stage op-amp half needed finite bandwidth | An ideal tone-stage op-amp (plus missing base capacitances) left a 0.33 µs delay error; an ideal op-amp with switched rails also chattered in overload. A one-pole op-amp state with in-loop rails fixed both. | `circuit-reduction.md` (reduced op-amp) |
| Static-equivalent tone realisations differed under automation | Two realisations with identical static responses scored −31 dB and −4.7 dB under tone automation; the physical-state realisation scored −83.7 dB against a time-varying SPICE reference with the real op-amp. | `circuit-reduction.md` (time-varying controls) |
| Coefficient cadence | Holding coefficients for a host sample raised automation error to −41 dB (from −84 dB) to save well under one CPU point. | `integrators-and-rates.md` (control update cadence) |
| Trapezoidal integration only looked adequate | Its discretisation error had been compared with a total error. Decomposed properly, it exceeded the continuous-model error at some production rates; the L-stable method did not. | `integrators-and-rates.md`, `validation-gates.md` |
| Exact-period tones made a budget a lottery | At rates where a test tone had an integer number of samples per period, discretisation error varied from about −72 dB to −48 dB with sub-sample phase; a dense rate sweep failed only at such points. A 16-phase power average made the budget metric stable; exact-period cases stayed in the absolute gate. | `validation-gates.md` (phase ensembles) |
| A relative budget turned red when the model improved | Correcting the diode law lowered the continuous-model error floor; the "discretisation ≥ 3 dB below the model error" rule then failed at the lower production rates although every output gate passed and the doubled rate (16×) gave no measurable output gain at about twice the CPU. The rule was split into a hard non-dominance gate (passes) and a reported 3 dB target (missed by up to 2.6 dB). | `validation-gates.md` (hard gates and targets) |
| A subset tier cannot evaluate a population gate | The 6-case smoke tier recomputed the floor from its own cases and failed the hard comparison by 0.76 dB for a case that passes in the complete 72-case population. The fix was semantic: hard A2 NOT EVALUATED in the smoke tier, a visible subset diagnostic, and release tiers required to contain the complete grid (checked by content). | `validation-gates.md` (population-level gates) |
| An approximate reset produced a long false transient | A 0.5 mV output step decaying over 92 ms turned a −42.9 dB small-signal case into −4.5 dB. The exact discrete DC fixed point fixed it. | `circuit-reduction.md` (exact reset) |
| The real oversampling filters had to be measured | Integer-latency polyphase IIR filters gave 6-sample latency at 8×/4× and bit-exact latency-matched bypass; their non-linear phase dominates host-rate waveform comparisons, so fidelity was gated at the island rate and the filters were gated separately. | `integrators-and-rates.md` |
| Plugin validation and fidelity are separate | pluginval (strictness 10) and auval passing said nothing about circuit accuracy; the SPICE reference tiers said nothing about host behaviour. Both were required. | `validation-gates.md` (product checks) |
| Solver memory must describe the returned root | Carrying the last evaluated point instead of the returned root into the next predictor was a latent correctness bug, found in a code-correctness review. | `nonlinear-solvers.md` |

## Numbers Worth Remembering Only As Examples

- Newton budget after adding a conditional re-seed table: maximum 6 evaluations over 6 million synthetic solves (previously the cap was hit 31 % of the time from arbitrary warm starts), 0 cap hits in every time-series corpus.
- Table proof: 8192-node cubic Hermite, minimum interpolant/node slope ratio 0.996 at the device-law kink interval, Fritsch–Carlson α²+β² ≤ 2.24.
- CPU (one machine): about 5 % of a core mono and 10 % stereo at 48 kHz × 8 back to back; about 10 % mono at 16×.
- Interface calibration default: +12 dBu at the jack = 0 dBFS (a product choice for typical interfaces), with a user trim.
- Fidelity envelope: 1.4 V peak at the input, set by the measured onset of the tone op-amp's saturation; above it, robustness grade.

## What Not To Copy

The rate, the integrator, the state count, the explicit coupling, the 1 mV diode gate, the 3 dB margin, the +12 dBu calibration and the 1.4 V envelope were **derived** for this circuit. Derive yours the same way.
