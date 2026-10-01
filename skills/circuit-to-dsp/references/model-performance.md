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

A validated circuit model is allowed to be expensive when the accepted reference requires that cost. This reference is about making it cheaper **without changing what it computes**. Plugin-level attribution (audio thread versus editor), harness construction, live-callback measurement and reporting belong to the `juce-plugin` skill's [performance-investigation.md](../../juce-plugin/references/performance-investigation.md); measurement vocabulary is in [integrators-and-rates.md](integrators-and-rates.md#performance-measurement).

## What May Change And What May Not

Once gates have accepted a model, these are its contract, not performance knobs: the minimum internal rate and oversampling policy, the integrator, solver tolerance and iteration limits, device laws and shipped tables, the state inventory and couplings, control smoothing and coefficient cadence, the resampling filters and latency.

- **Do not lower the oversampling factor by instinct.** Time the resampling filters and the work inside the island separately. In an implicit island the filters are usually a few percent and the island is the cost, and the rate may be set by stiffness, not aliasing ([integrators-and-rates.md](integrators-and-rates.md#what-can-set-the-internal-rate)). A lower rate that fails a rate gate is a large, invalid speed-up.
- **Any change to the arithmetic is a new model revision**: reordering, vectorising channels with lockstep solves, another table, approximations, relaxed floating-point flags. Re-run every gate and tier and null the result against the previous kernel at a stated bound. Budget that work before promising the gain.
- **Lower fidelity for speed is a product decision**, never a side effect of a performance pass. When the owner has already offered it ("halve the oversampling if you need to"), exact shortcuts still come first; then return it as a costed option, with the measured gain and which gates pass or fail at the lower setting, for an explicit decision.

## Order Of Work

1. Remove duplicated computation (the same result computed twice).
2. Skip computation whose result is already known (settled, held).
3. Skip inactive work (bypassed or disabled paths).
4. Hoist invariants (constants while nothing moves).
5. Optimize surrounding infrastructure (buffers, resampling, host-rate work) where measurement says it matters.
6. Only then consider kernel or numerical changes, with full re-validation.

Steps 1–4 can be exact. Take them first.

## Where The Time Goes

Time the stages (resampler, islands, host-rate work) before choosing anything. Typical for an implicit island: the islands dominate, the cost is per internal sample and independent of the host block size, and **silence is not cheap**, because the states are integrated and the nonlinear solve still runs on zero input. Benchmark silence as its own signal: it may be cheaper (fewer solver iterations), equal, or dearer (denormals, noise models).

An island with one solve per stage is one serial dependency chain: companion sources → linear network → solve → outputs → state commit → next stage. It is latency-bound, with no wasteful loop to remove. A sampling profiler will blame the commit or clamp where the chain ends; that line is not the cost. Object alignment and forced inlining are worth one measurement each; expect little, and check whether the product build's link-time optimization already has the gain.

## Identical-Channel Sharing

Hosts usually run an effect stereo even for a mono source, so independent per-channel islands compute the same numbers twice. For deterministic islands:

- **Condition**, evaluated per block at the island input (after input conditioning and up-sampling): the channels' samples are bit-identical **and** the islands hold bit-identical state (histories, modes, solver memory, coefficient sets).
- **Then** run one island, copy its output to the other channel and its state to the other island.
- **Stop** on the first block whose inputs differ: both islands run again, from identical states. Share again only when a state comparison says the states are bit-identical, which in practice means after a reset.
- Compare bits (`memcmp`), not values: `==` treats signed zeros as equal and NaN as unequal.
- Keep per-channel diagnostics (solver statistics) meaning what they meant, or the tests that read them change meaning.

The output is bit-identical to running both islands. Input equality alone is not enough: two islands with different histories diverge on identical input.

This is **not** "process stereo as mono". Summing or forcing mono changes what a true stereo input sounds like and is a product decision.

Tests: identical → different → identical input, bit-exact against an engine with the shortcut disabled; sharing observed where expected and absent where not.

## Settled-State Hold

Digital silence does not stop a physical model. Its states keep integrating toward the quiescent point, at full cost, for as long as the host calls it. A hold is **state-integration suspension after verified convergence**. It is not silence gating: nothing is muted, faded, reset or shortened.

Enter the hold only when all of these are true:

- the island input is digital silence (treat a denormal residue of upstream filters as zero only where the callback's denormal mode would flush it anyway);
- no control the island reads is moving;
- no state has moved by more than a tolerance over a window that is not short against the slowest time constant. A short window hides a large remaining distance behind a small motion.

While held: keep every state, repeat the last output, and keep running what surrounds the island (resampling filters, dry path, latency). Resume in the same block when any input sample is non-zero or any control moves.

Choose the tolerance by measurement, never as a round number:

1. Measure the settled model's own rounding-noise motion over the window at the control corners, both ends of the rate policy, normal and overload excitation, and from reset. This is the floor.
2. Do not wait for bit-stationary state. A floating-point model can sit in a tiny limit cycle indefinitely, and some settings never become bit-identical.
3. Set the tolerance a clear margin above the floor and confirm that every corner reaches it in bounded time.
4. Try a looser value. Reject it if the held state is measurably different from the settled one or if resumed output differs beyond output rounding.
5. Compare with uninterrupted integration: the residual while held (in dBFS and in state units), then after resuming with signal and after resuming with a control change.

State the consequences in the report: the hold engages only once the tail has decayed to that floor (seconds to tens of seconds for a slow bias node), so the cost just after a signal stops is unchanged; and an input that never reaches digital silence never holds.

Tests: a fresh instance on silence; a tail after signal (the reference tail must be at the floor before the hold); resume on signal and on a control change within the same block; held and resumed output against an engine with the hold disabled.

*Case study: silence cost 82 % of a guitar signal. A window of 0.25 s against a slowest time constant of 0.78 s, and a tolerance of 1e-14 V, 27× the worst settled motion of 3.7e-16 V over 108 corner cases, all of which reached it within 18.3 s. A 1e-12 V tolerance engaged about 3 s sooner but held a state measurably away from the settled one. Two of three control settings were still not bit-stationary after 120 s. These values belong to that circuit; another model's floor, window and margin come from its own measurements.*

## Constants While Controls Rest

A smoother that is not ramping returns the same value every sample. While every relevant smoother is at rest, skip per-sample gain conversions (`pow`, `exp`), per-internal-sample control interpolation and coefficient selection, and read the current values directly. Guard the fast path on "at rest **and** current equals target", so a zero-length ramp cannot leave a stale value. It is exact and low risk, and usually small: profile before presenting it as a win.

## Evidence

- Null test against the previous build over rates, block sizes, layouts, signals, automation, gain and control steps, bypass toggling, overload, silence, a tail, and signal after long silence. Exact shortcuts are bit-identical; a hold differs only around silence, within the stated bound.
- Every unit gate and reference tier unchanged and passing. Never loosen one to admit an optimization.
- Solver statistics, cap hits and finite output over the same runs.
- Before and after by layout and signal, including the rows that did not improve.
- A switch that disables the shortcuts, used by tests as the reference engine.

## Checklist

- [ ] Stage timings taken; the dominant stage identified; silence benchmarked separately.
- [ ] No contract item (rate, integrator, tolerance, tables, cadence) changed for speed.
- [ ] Exact shortcuts taken before any numerical change.
- [ ] Channel sharing conditioned on bit-identical input **and** state; transitions tested; output bit-exact.
- [ ] Hold tolerance derived from the measured noise floor over corners; looser value tried and rejected or justified; residuals reported.
- [ ] Hold resumes within the block on input or control movement; latency and surrounding state preserved.
- [ ] Null test and every gate pass; unchanged costs reported with the reason.
