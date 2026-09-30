# Nonlinear Circuit Solvers

## Contents

- Derive the residual from the circuit
- Feedback clipping is not a waveshaper
- Reduce to the smallest nonlinear dimension
- Monotone scalar residuals
- A realtime-safe scalar solver
- Solver memory and statistics
- Fuzzing the solver
- Device laws from the simulator
- Lookup tables: validate the shipped interpolant
- When one dimension is not enough
- Checklist

## Derive The Residual From The Circuit

Write Kirchhoff's current law at the nodes that touch the nonlinear device, with every capacitor replaced by its discrete companion model for the chosen integrator (a conductance G and a history current J: i = G·v − J). Eliminate every linear node you can. What remains is the nonlinear residual the realtime model must solve each step. Record:

- which unknown(s) remain (voltage across a diode pair, a transistor's base-emitter voltage...);
- whether the nonlinearity is memoryless or has its own state (junction capacitance, charge storage);
- whether it is current-domain (a device current into a node) or voltage-domain;
- whether it sits inside a feedback loop.

## Feedback Clipping Is Not A Waveshaper

A diode pair in an op-amp's feedback path limits the **feedback impedance**, so the stage's gain collapses as the diodes conduct while the op-amp keeps driving. The result depends on frequency (feedback capacitors, coupling networks), on the op-amp's finite bandwidth and on bias. It is not `prefilter → tanh → postfilter`. Also preserve parallel paths the circuit really has: many overdrive stages sum a clean component (the non-inverting input's signal) with the clipped feedback component.

Model the feedback network and solve it; use a static shaper only as a quantified fallback.

## Reduce To The Smallest Nonlinear Dimension

After eliminating linear nodes, many practical circuits have **one** nonlinear unknown per step even when they carry many linear states. A scalar solve is far easier to make bounded, monotone and fast than a vector one. Before accepting a multi-dimensional solve, check whether:

- series/parallel diode strings can be combined into one branch law;
- linearised buffers remove device unknowns;
- an explicit one-step coupling of a slow shared node (verified by measurement) decouples two nonlinear blocks.

## Monotone Scalar Residuals

If the residual can be written as

```text
r(v) = G·v + I(v) − p,   with G > 0 and I′(v) ≥ 0 everywhere
```

then `r′(v) ≥ G > 0` wherever `I` is differentiable: the residual is strictly increasing, so it has **at most one** root. Existence needs more:

- if `I` is finite and continuous on the whole real line, `r(v) − G·v` is non-decreasing, so `r(v) → ±∞` as `v → ±∞` and a root exists for every `p`;
- on a restricted domain (a table range, a clamped or overflowing exponential), existence needs an explicit sign-changing bracket `r(a) < 0 < r(b)` inside the domain.

With both, the solve has exactly one root, and it supports a unique, bounded safeguarded solve when a valid bracket is maintained and the device law remains finite:

- no wrong-branch solutions and no chattering between roots;
- a bracket that contains the root and shrinks safely;
- guaranteed convergence of a bracketing safeguard (bisection fallback) within the bracket.

Check the conditions on the law actually shipped (for a table, on the interpolant, not only on the analytic equation) and on every operating mode (rails, cutoffs) that changes G or p.

## A Realtime-Safe Scalar Solver

A pattern that worked well:

1. **Predictor**: start from the previous root plus a tangent-line step using the previous slope; clamp the step to a physical range.
2. **Conditional re-seed**: if the first Newton step is large (the operating point jumped), replace the start with a value from a small precomputed inverse table indexed by the equivalent conductance and right-hand side. Build it at prepare time.
3. **Safeguarded Newton**: limit forward steps logarithmically near exponential knees (SPICE-style voltage limiting), maintain a bracket from residual signs, and fall back to bisection when a step leaves the bracket.
4. **Convergence test before the bracket guard**: accept when |Δv| is below the tolerance (for example 1 nV), so a converged step is never rejected by the guard.
5. **Fixed cap** on evaluations per solve, then a deterministic fallback (the bracket midpoint). Count cap hits: in normal operation there should be none.

Keep the solver per channel and allocation-free. Start and qualify it in double precision; single precision is acceptable only if parity, convergence margin and the stress corpora establish it.

## Solver Memory And Statistics

- The state carried to the next step (last root, current, slope) must describe the **returned** root. If the loop exits after a final Newton update, re-evaluate the law at the returned value before storing it; otherwise the next predictor and any state that depends on the device current use stale values.
- Keep plain counters (solves, evaluations, re-seeds, bisections, cap hits, non-finite results, an evaluation histogram) readable outside the callback. Never log from the audio thread.

## Fuzzing The Solver

Prove the bound with data, not argument:

- **Synthetic corpus**: millions of solves with roots spread over and beyond the physical range, arbitrary warm starts and the full range of equivalent conductances.
- **Time-series corpora**: real signals through the whole model (sweeps, bursts, square waves at full scale, silence, automation, non-finite and extreme input).
- Report maximum evaluations, histogram, cap hits, bisections, fallbacks and non-finite results. Gate on zero cap hits and zero non-finite results; keep maximum evaluations as a regression metric.
- Re-run after any change to the law, the table, the integrator or the rate.

## Device Laws From The Simulator

When the realtime law must match a SPICE card, implement the simulator's actual equations (recombination terms, generation factors, high-injection knee, piecewise reverse handling, gmin), verified against the installed simulator's DC sweep on a fine grid across every branch threshold. Details are in the `spice-circuit-modeling` skill's `references/device-model-qualification.md`. Piecewise laws create slope discontinuities (kinks) in the branch law: check that the solver and any table stay monotone across them.

## Lookup Tables: Validate The Shipped Interpolant

A table replaces an expensive law in the callback. The table is then the model, so validate the **table**:

| Check | Method |
| --- | --- |
| Monotonicity (if the solver relies on it) | For each interval, compute the exact minimum of the interpolant's derivative (for a cubic Hermite it is a quadratic in the local coordinate) in extended precision; require it positive with margin |
| No overshoot | Node values strictly increasing; interpolant within neighbouring node values where required |
| Fritsch–Carlson condition | α² + β² ≤ 9 per interval for monotone cubic Hermite data |
| C¹ continuity | Derivative jump at knots near rounding level |
| Value and derivative error | Dense comparison against the analytic law (many points per interval); report both relative current error and the resulting **voltage** error, which is what circuit gates see |
| Kinks | Intervals containing a law branch point: check their derivative ratio and error separately |
| Outside the range | The outside-range policy must preserve the solver invariants (monotonicity, finiteness, C¹ where the solver needs it). Linear extrapolation from the edge value and slope is one safe option; an analytic law that is not monotone or finite at extreme arguments is not |
| Reachability | Count evaluations outside the table range in the stress corpora; normally zero |

Evaluate exactly the stored coefficients in the proof, the same ones the solver uses.

## When One Dimension Is Not Enough

For genuinely coupled nonlinearities, use a small vector Newton with the same safeguards: damping, a line search or trust region, a fixed iteration cap and a deterministic fallback, plus the same fuzzing. Reconsider the formulation first: an avoidable second dimension usually costs more robustness than it buys accuracy.

## Checklist

- [ ] Residual derived from KCL with integrator companions; unknowns, memory, domain and feedback identified.
- [ ] Feedback clipping modelled as a network, clean paths preserved.
- [ ] Nonlinear dimension minimised; monotonicity conditions checked on the shipped law.
- [ ] Solver: predictor, conditional re-seed, limited safeguarded Newton, bracket, cap, deterministic fallback.
- [ ] Solver memory re-evaluated at the returned root.
- [ ] Synthetic and time-series fuzzing: zero cap hits, zero non-finite.
- [ ] Device law verified against the simulator; table proven monotone on the shipped interpolant.

## Sources

- F. N. Fritsch and R. E. Carlson, "Monotone Piecewise Cubic Interpolation," *SIAM J. Numer. Anal.* 17(2), 1980, pp. 238–246: the monotonicity region for cubic Hermite data used in the table checks.
- L. W. Nagel, *SPICE2*, UC Berkeley ERL Memo M520, 1975: logarithmic junction-voltage limiting (the origin of SPICE-style step limiting).
- The pinned simulator's device source (see the `spice-circuit-modeling` skill's device-model-qualification reference) for the law being tabulated.
