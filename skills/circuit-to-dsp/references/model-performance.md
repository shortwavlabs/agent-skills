# Performance Of A Validated Model

## Contents

- What may change and what may not
- Order of work
- Where the time goes
- Identical-channel sharing
- Settled-state hold
- Constants while controls rest
- Evidence
- Checklist

A validated circuit model is allowed to be expensive when the accepted reference requires that cost. This reference is about making it cheaper **without silently changing what it computes**. The measurement method (attribution between audio thread and editor, harness construction, live-callback measurement, reading a profile, null tests), the equivalence classes used below and reporting belong to the `juce-plugin` skill's [performance-investigation.md](../../juce-plugin/references/performance-investigation.md). What to report for a circuit model is listed in [integrators-and-rates.md](integrators-and-rates.md#performance-measurement).

## What May Change And What May Not

Once gates have accepted a model, these belong to the **current validated model contract**: the minimum internal rate and oversampling policy, the integrator, solver tolerance and iteration limits, device laws and shipped tables, the state inventory and couplings, control smoothing and coefficient cadence, the resampling filters and latency. Any of them can be changed deliberately, but the change is a new model revision that reopens the gates it touches. None of them is a knob to turn inside a performance pass.

- **Do not lower the oversampling factor by instinct.** Time the resampling filters and the work inside the island separately. In an implicit island the filters are often a small share and the island is the cost, and the rate may be set by stiffness, not aliasing ([integrators-and-rates.md](integrators-and-rates.md#what-can-set-the-internal-rate)). A lower rate that fails a rate gate is a large, invalid speed-up.
- **Any change to the arithmetic is a new model revision**: reordering, vectorising channels with lockstep solves, another table, approximations, relaxed floating-point flags. Re-run every gate and tier and null the result against the previous kernel at a stated bound. Budget that work before promising the gain.
- **Lower fidelity for speed is a product decision**, not a side effect of a performance pass. When the owner has already offered it ("halve the oversampling if you need to"), take the shortcuts below first; then return it as a costed option, with the measured gain and which gates pass or fail at the lower setting, for an explicit decision.

## Order Of Work

1. Remove duplicated computation (the same result computed twice).
2. Skip computation whose result is already known (a settled subsystem).
3. Skip inactive work (bypassed or disabled paths).
4. Hoist invariants (constants while nothing moves).
5. Optimize surrounding infrastructure (buffers, resampling, host-rate work) where measurement says it matters.
6. Only then consider kernel or numerical changes, with full re-validation.

Steps 1, 3 and 4 can be bit-exact. Step 2, when it rests on a finite convergence threshold, is a bounded shortcut with its own validation; it is exact only if fixed-point equivalence is actually proven for the model. Take all four before step 6, and record each change's [equivalence class](../../juce-plugin/references/performance-investigation.md#equivalence-classes).

## Where The Time Goes

Time the stages (resampler, islands, host-rate work) before choosing anything. Typical for an implicit island: the islands dominate, the cost is per internal sample and independent of the host block size, and **silence is not cheap**, because the states are integrated and the nonlinear solve still runs on zero input. Benchmark silence as its own signal: it may be cheaper (fewer solver iterations), equal, or dearer (denormals, noise models).

An island with one solve per stage is one serial dependency chain: companion sources → linear network → solve → outputs → state commit → next stage. Such a kernel is typically latency-bound, with no wasteful loop to remove, and a sampling profiler can blame the commit or clamp where the chain ends ([reading a profile](../../juce-plugin/references/performance-investigation.md#stage-breakdown-and-reading-a-profile)). Object alignment and forced inlining are worth one measurement each; check whether the product build's link-time optimization already has the gain.

## Identical-Channel Sharing

Hosts often run an effect stereo even for a mono source, so independent per-channel islands compute the same numbers twice.

**Scope.** The pattern assumes deterministic, independent per-channel processing. A channel with stochastic noise, intentionally independent random state, cross-channel coupling, stereo modulation or channel-dependent external state can share only when its complete relevant state and deterministic future behaviour are proven equivalent. It is not a property of every stereo processor.

**Invariant.** The shared computation is used only for samples for which the inputs **and** all relevant state of both channels are equivalent at the level the claim needs (bit-identical for a bit-exact claim). Everything below follows from it.

- **Where to compare inputs:** at the input of the shared expensive stage, not at the plugin input. Preprocessing (trim, filters, up-sampling) has state of its own and can make equal plugin inputs unequal.
- **Granularity is a choice, not part of the invariant.** Conservative: prove the whole block or span identical, then share it. Opportunistic: share the common prefix, stop at the first differing sample, and continue independently from the copied state. Finer checks cost comparisons; choose by measuring comparison overhead against the work saved.
- **What "state" means:** the complete semantic state, that is, everything mutable that affects future output: integrator histories, solver memory (predictor, previous root), modes, latches and hysteresis, limiter and internal filter state, coefficient sets and cached nonlinear values, random or noise state if any. Not only the obvious voltages.
- **How to compare it:** with an explicit function that visits every such field and, where bit identity matters, compares floating-point bit patterns (for example `std::bit_cast` of each scalar to an integer, or a canonical representation built for comparison). Do not `memcmp` whole state structs: padding bytes, indeterminate representation and non-trivially-copyable members make that unsafe or misleading. Decide deliberately how signed zeros and NaN compare; value `==` calls +0 and −0 equal and NaN unequal.
- **Copying state** to the other channel must be equally complete. Copying only the main integrator histories is not enough.
- **Diagnostics** (solver statistics, counters) need deliberate semantics: copy them, or count the shared work for both channels, so tests that read them keep their meaning.
- After the channels have diverged, share again only when the state comparison says so; in practice after both are reset or restored to the same state.

With bit-identical inputs and state the output is bit-identical to running both islands (class: bit-exact). Input equality alone is not enough: two islands with different histories diverge on identical input.

This is **not** "process stereo as mono". Summing or forcing mono changes what a true stereo input sounds like (class: product-semantic).

Tests: identical → different → identical input, including a divergence in the middle of a block, and sharing again after a reset or restore, bit-exact against an engine with the shortcut disabled; sharing observed where expected and absent where not.

## Settled-State Hold

Digital silence does not by itself stop a stateful physical model: its states keep integrating toward the quiescent point, and the work continues, for as long as the host calls it. A hold is **state-integration suspension after verified convergence of the subsystem**. It is not silence gating: nothing is muted, faded, reset or shortened.

**Scope.** A hold suits a deterministic subsystem that has no relevant external excitation, settles asymptotically, has no control in motion and has no autonomous behaviour that must continue. It is not automatically valid for oscillators, LFO-driven systems, noise generators and stochastic models, chaotic or autonomous dynamics, reverbs and delays with intentionally audible tails, or any model whose internal time evolution is itself part of the output. Those need equivalence proven specifically.

**Where to test.** Host-input silence is not subsystem-input silence. Test the input and state of the subsystem actually being held, after everything upstream of it (up-sampling filters, coupling filters, latency lines). Hold only that subsystem. Surrounding state that still evolves (resampling filters, dry path, downstream filters) keeps running unless separately proven safe to suspend, so no upstream or downstream tail is truncated.

Enter the hold only when all of these are true:

- the subsystem's input is digital silence (treat a denormal residue of upstream filters as zero only where the callback's denormal mode would flush it anyway);
- nothing the subsystem reads is moving: no control ramp, no pending target;
- no state has moved by more than a tolerance over a window that is not short against the system's slowest dynamics.

**Small motion is not small distance.** A small change over a short window does not prove proximity to the settled region. For a nonlinear system do not rely on one nominal time constant: validate with long runs against uninterrupted integration over the accepted operating grid.

While held, keep every state and repeat the last output. Invalidate the hold, resuming within the same block, on anything that changes the held equations or their input, as applicable: non-zero input; a control or parameter target; smoothing or ramp state; model mode; a bypass transition; sample rate or oversampling configuration; topology or configuration; reset; preset or state restore; externally supplied state.

Choose the tolerance by measurement, not as a round number:

1. Measure the settled model's own rounding-noise motion over the window at the control corners, both ends of the rate policy, normal and overload excitation, and from reset. This is the floor.
2. Do not wait for bit-stationary state. A floating-point model can sit in a tiny limit cycle indefinitely, and some settings may not become bit-identical in any practical time.
3. Set the tolerance a clear margin above the floor and confirm that every corner reaches it in bounded time.
4. Try a looser value. Reject it if the held state is measurably different from the settled one or if resumed output differs beyond output rounding.
5. Compare with uninterrupted integration: the residual while held (in dBFS and in state units), then after resuming with signal and after resuming with a control change.

Class: bounded-numerical, with the bound reported, unless exact fixed-point equivalence is proven.

State the consequences in the report: the hold engages only once the tail has decayed to that floor, which can take many times the slowest time constant, so the cost just after a signal stops is unchanged; and an input that never reaches digital silence never holds.

Tests: a fresh instance on silence; a tail after signal (the reference tail must be at the floor before the hold); resume within the same block on signal, on a control change and on each other invalidator the model has; held and resumed output against an engine with the hold disabled.

*Case study (one circuit; not defaults): the window was a sizeable fraction of the slowest time constant, and the tolerance sat more than an order of magnitude above the worst settled motion measured over a grid of corner cases, every one of which reached it in bounded time. A looser tolerance engaged sooner but held a state measurably away from the settled one, and some control settings were still not bit-stationary after minutes. The figures are in the [case study](case-study-sd1-overdrive.md).*

## Constants While Controls Rest

A smoother that has reached its target and is at rest returns the same value every sample (a finished linear ramp; an exponential smoother only once it is snapped to its target). While every relevant smoother is at rest, skip per-sample gain conversions (`pow`, `exp`), per-internal-sample control interpolation and coefficient selection, and read the current values directly. Guard the fast path on "at rest **and** current equals target", so a zero-length ramp cannot leave a stale value. It can be bit-exact and is low risk, and usually small: profile before presenting it as a win.

## Evidence

- A null test against the previous build over the render set in [prove equivalence](../../juce-plugin/references/performance-investigation.md#prove-equivalence), including a tail and signal after long silence. Bit-exact changes are bit-identical; a hold differs only around silence, within the stated bound.
- Every unit gate and reference tier unchanged and passing. Do not loosen one to admit an optimization.
- Solver statistics, cap hits and finite output over the same runs.
- Before and after by layout and signal, including the rows that did not improve.
- A switch that disables the shortcuts, used by tests as the reference engine.

## Checklist

- [ ] Stage timings taken; the dominant stage identified; silence benchmarked separately.
- [ ] No item of the validated contract (rate, integrator, tolerance, tables, cadence) changed without a new revision and its gates.
- [ ] Duplicated, inactive and invariant work removed before any numerical change; each change classified.
- [ ] Channel sharing only where inputs **and** complete semantic state are equivalent; explicit comparison and complete copy; mid-block divergence tested; output bit-exact.
- [ ] Hold applied only to a convergent deterministic subsystem; tested at that subsystem's input; surrounding tails intact.
- [ ] Hold tolerance derived from the measured noise floor over corners; looser value tried; residuals and bound reported.
- [ ] Hold invalidated within the block by every relevant change (input, controls, mode, bypass, rate, configuration, reset, restore).
- [ ] Null test and every gate pass; unchanged costs reported with the reason.
