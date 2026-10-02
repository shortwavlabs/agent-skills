# Performance Of A Validated Model

## Contents

- What may change and what may not
- Order of work
- Where the time goes
- Identical-channel sharing
- Independent-channel interleaving
- Settled-state hold
- Constants while controls rest
- Composing shortcuts
- Call boundaries and code generation
- Evidence
- Checklist

A validated circuit model is allowed to be expensive when the accepted reference requires that cost. This reference is about making it cheaper **without silently changing what it computes**. The measurement method (attribution between audio thread and editor, harness construction, live-callback measurement, reading a profile, null tests), the equivalence classes used below and reporting belong to the `juce-plugin` skill's [performance-investigation.md](../../juce-plugin/references/performance-investigation.md). What to report for a circuit model is listed in [integrators-and-rates.md](integrators-and-rates.md#performance-measurement).

## What May Change And What May Not

Once gates have accepted a model, these belong to the **current validated model contract**: the minimum internal rate and oversampling policy, the integrator, solver tolerance and iteration limits, device laws and shipped tables, the state inventory and couplings, control smoothing and coefficient cadence, the resampling filters and latency. Any of them can be changed deliberately, but the change is a new model revision that reopens the gates it touches. None of them is a knob to turn inside a performance pass.

- **Do not lower the oversampling factor by instinct.** Time the resampling filters and the work inside the island separately. In an implicit island the filters are often a small share and the island is the cost, and the rate may be set by stiffness, not aliasing ([integrators-and-rates.md](integrators-and-rates.md#what-can-set-the-internal-rate)). A lower rate that fails a rate gate is a large, invalid speed-up.
- **Any change to the arithmetic is a new model revision**: reordering operations within a channel, another table, approximations, relaxed floating-point flags, a looser solver acceptance. Re-run every gate and tier and null the result against the previous kernel at a stated bound. Budget that work before promising the gain.
- **Classify a vector (SIMD) implementation by what it computes, not by the fact that it uses vectors.** Presume it needs complete re-validation, because vectorising often changes something numerical: evaluation order, fused multiply-add use, rounding, or solver behaviour when lanes iterate in lockstep and diverge at mode changes. If a particular implementation keeps each lane's operation semantics and is bit-identical in output and state on each supported target, compiler and floating-point mode, it belongs to the bit-exact class like any other implementation change. If it is not, it is a new model revision.
- **Changing how the same arithmetic is scheduled or compiled is not a change to the arithmetic**, as long as every channel still performs the same floating-point operations in the same order and no channel reads what another wrote inside the rescheduled span: [interleaving independent channels](#independent-channel-interleaving), [inlining a call boundary](#call-boundaries-and-code-generation). Such a change is a candidate for the bit-exact class. The bit-identical null test proves it, on each supported target, compiler and floating-point mode, because a compiler's freedom to fuse or re-associate operations (floating-point contraction, fused multiply-add selection) can depend on code structure and on the target.
- **Lower fidelity for speed is a product decision**, not a side effect of a performance pass. When the owner has already offered it ("halve the oversampling if you need to"), take the shortcuts below first; then return it as a costed option, with the measured gain and which gates pass or fail at the lower setting, for an explicit decision.

## Order Of Work

1. Remove duplicated computation (the same result computed twice).
2. Skip computation whose result is already known (a settled subsystem).
3. Skip inactive work (bypassed or disabled paths).
4. Hoist invariants (constants while nothing moves).
5. Optimize surrounding infrastructure (buffers, resampling, host-rate work) where measurement says it matters.
6. Reschedule the unchanged arithmetic: overlap independent channels, and remove call overhead at hot boundaries where a measured variant shows a gain.
7. Only then consider numerical changes, with full re-validation.

Steps 1, 3, 4 and 6 can be bit-exact. Step 2, when it rests on a finite convergence threshold, is a bounded shortcut with its own validation; it is exact only if fixed-point equivalence is actually proven for the model. Steps 1 to 4 remove work and come first; step 6 makes the remaining work faster. Take all of them before step 7, and record each change's [equivalence class](../../juce-plugin/references/performance-investigation.md#equivalence-classes).

## Where The Time Goes

Time the stages (resampler, islands, host-rate work) before choosing anything. Typical for an implicit island: the islands dominate, the cost is per internal sample and independent of the host block size, and **silence is not cheap**, because the states are integrated and the nonlinear solve still runs on zero input. Benchmark silence as its own signal: it may be cheaper (fewer solver iterations), equal, or dearer (denormals, noise models).

An island with one solve per stage is one serial dependency chain: companion sources → linear network → solve → outputs → state commit → next stage. Such a kernel is typically latency-bound, with no wasteful loop to remove, and a sampling profiler can blame the commit or clamp where the chain ends ([reading a profile](../../juce-plugin/references/performance-investigation.md#stage-breakdown-and-reading-a-profile)).

"Latency-bound" describes **one** island. It does not mean the kernel is at its floor:

- A long dependency chain leaves little instruction-level parallelism inside one island. A second, independent island is a second chain that can supply work ready to execute while the first waits on its own results: [independent-channel interleaving](#independent-channel-interleaving).
- Whether the hot call boundaries inside a stage were inlined is a fact about the shipped binary, not about its build flags. Link-time optimization can leave them out of line: [call boundaries](#call-boundaries-and-code-generation).
- Object alignment is a quick experiment, judged against the measured noise like any other.

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

## Independent-Channel Interleaving

Sharing does nothing for a stereo signal whose channels genuinely differ: nothing is duplicated. But a kernel that is serial **within** one island still offers parallelism **between** islands. Two independent islands are two independent dependency chains. Run one island for the whole block and then the other, and each chain waits alone. Advance them side by side, and an out-of-order processor can execute ready work from one chain while the other waits on a dependent result.

This is instruction-level parallelism across independent state machines. It is not SIMD: no operation is vectorised, fused across channels, or reordered within a channel.

| Layout | What applies |
| --- | --- |
| Mono | One chain. There is nothing to overlap; the cost is the chain's latency. |
| Stereo, equivalent inputs **and** state | [Identical-channel sharing](#identical-channel-sharing): one island runs. Removing duplicate work beats overlapping it, so this case never goes to the interleaved path. |
| Stereo, different inputs or state | Sharing is invalid. Interleave the two islands if the invariant below holds for them. |

**Invariant.** Each channel performs the same floating-point operations in the same order as when it runs alone. Only the order **between** channels changes. It holds when all of these are true:

- each channel owns its complete semantic state (as defined for [sharing](#identical-channel-sharing)): histories, solver memory, modes, coefficient caches;
- nothing written for one channel inside the reordered span is read by the other: no cross-channel coupling, shared scratch buffer, shared mutable cache or shared random state;
- objects both channels use are read-only during the span (device tables, rate constants);
- every step receives the input sample and control values that the channel would have received alone;
- guards and fallbacks act per channel and have the effect they have in sequential execution (a non-finite reset of one island leaves the other untouched).

If the channels are coupled (a stereo link, a shared supply or bias model, cross-feed, a shared stochastic source), the span that may be reordered ends at the coupling, or the pattern does not apply.

When the invariant holds, the change is a candidate for the bit-exact class: the saving is schedule, not arithmetic. A vector (SIMD) island is a different change. It runs both channels in the lanes of one instruction stream, and it is classified by its own numerical result, not by this invariant ([what may change](#what-may-change-and-what-may-not)).

**Granularity is measured, not prescribed.** Candidates run from "one island per block" (no overlap) through "per internal sample" and "per integrator stage" to finer units.

- Too coarse: one chain fills the processor's window before the other begins, and little latency is hidden.
- Too fine: dispatch and loop overhead grow, and the compiler gets a worse shape to optimize.
- The size of the interleaved unit matters too: inlining more into each unit can reduce the overlap ([call boundaries](#call-boundaries-and-code-generation)).

For a multi-stage integrator the stage boundary is a natural first experiment, because each stage is one long chain. Time the candidates against each other on the real kernel.

**The invariant is portable; the proof is per target; the gain is per machine.** The equivalence argument is made at source level and holds anywhere: independent channels, unchanged per-channel operation order, no cross-channel read or write inside the span. What a compiler emits for the restructured code is not covered by that argument ([what may change](#what-may-change-and-what-may-not)), so the bit-exact claim is verified by the null test on each supported target, compiler and floating-point mode. The size of the speed-up is hardware-specific. It depends on the processor's out-of-order window, on the core tier and on the code the compiler emits, and it is established only for the machines measured. Benchmark each supported architecture before quoting a figure, and report static and moving controls separately: the gain can differ materially between them.

**Oracle: two mono engines.** For a processor whose channels are meant to be independent, the accepted single-channel path is the reference for the interleaved one. Run a stereo engine on two different channels and two mono engines on one channel each, and require bit-identical output. The comparison means something only when both sides:

- start from the same state and take the same resets;
- are prepared at the same rate and oversampling configuration;
- receive the same per-channel input;
- receive the same control trajectory, block for block.

Exercise it where the arithmetic is busiest: every control moving, and overload (mode changes, solver re-seeds), not only a static mid-level case. Confirm that the stereo engine really ran the interleaved path for the comparison (not shared, not held). The oracle catches a channel reading the other's state, a control applied to the wrong channel or stage, and any ordering dependence through a shared object.

*Case study (one circuit, one machine; not defaults): stage-level interleaving of two islands was bit-identical over the whole render set and took a true-stereo signal from about 1.9 to about 1.3 times the mono cost. Sample-level interleaving gained less, and the gain with all controls automated was about three fifths of the static one. The figures are in the [case study](case-study-sd1-overdrive.md).*

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

## Composing Shortcuts

Several exact paths can cover overlapping cases. Decide per block or span in order of strength, and let each path take only what the stronger ones left:

1. **Held**: the subsystem is settled, silent and static. No island runs.
2. **Shared**: inputs and state are equivalent. One island runs.
3. **Interleaved**: two islands that differ. Both run, overlapped.
4. **Single**: one channel.

A newer, more general optimization does not take cases from an older, cheaper one. Identical channels stay on the shared path even though the interleaved path would also be correct for them.

Paths that are each correct can still fail where they hand over. Test the transitions the implementation actually has:

- shared → interleaved at the first differing sample, in the middle of a block, and shared again after the states re-converge (a reset or a restore);
- held → resumed on signal and on a control change, from the shared and from the interleaved case;
- automation starting and stopping;
- bypass in and out, reset, state restore;
- every configuration of the rate policy.

Compare against the right reference for each: an engine with sharing and hold disabled for those two, [two mono engines](#independent-channel-interleaving) for the interleaved schedule of channels meant to be independent, and the previous build's renders for everything. Report which path ran in each segment, so a test cannot pass by never entering the path it names.

## Call Boundaries And Code Generation

In a latency-bound stage that runs hundreds of thousands of times a second, call overhead can be a measurable share. A call inside the stage is a candidate for forced inlining when the profile or the disassembly shows that it:

- is crossed at least once per stage;
- returns an aggregate through memory, or passes values that are spilled and reloaded around it;
- saves and restores many registers;
- separates code that the processor could otherwise schedule together.

Derive the candidates from the disassembly, the profile, call frequency and data movement, not from which functions look small in the source.

- **Establish what the shipped binary does.** Link-time optimization, an `inline` keyword and "the compiler will handle it" are not evidence. List the kernel symbols that survive in the product binary and read the calls inside the hot function ([generated code as evidence](../../juce-plugin/references/performance-investigation.md#stage-breakdown-and-reading-a-profile)).
- **Forced inlining is a code-generation experiment, not a monotonic optimization.** Inlining one boundary changes the compiler's decisions elsewhere in the same function: register pressure, code size, which loops are vectorised, what is outlined instead. Inlining more can be slower than inlining less. Build each candidate as its own variant, time all of them against one baseline, and re-inspect the whole hot kernel after each, not only the annotated function.
- **Every compiler-level idea is a hypothesis**: forced inlining, alignment, manual unrolling, branch hints, hand-written SIMD, cache layout. Keep one only when its gain is clear of the [measured run-to-run noise](../../juce-plugin/references/performance-investigation.md#harness-and-tooling). Reject complexity that lands inside it.
- **Class.** Inlining leaves the source-level operation order alone, so it is a bit-exact candidate. The null test is what proves it, on each supported target, compiler and floating-point mode.

*Case study: link-time optimization had inlined the stages into the island but left two sub-blocks of every stage out of line. Forcing those two inline was worth about 6 %. Inlining the solver as well gained nothing; forcing the stage functions inline left another loop out of line and scalar and was slower; forcing everything inline matched the simple variant within noise for four times the code. The figures are in the [case study](case-study-sd1-overdrive.md).*

## Evidence

- A null test against the previous build over the render set in [prove equivalence](../../juce-plugin/references/performance-investigation.md#prove-equivalence), including a tail and signal after long silence. Bit-exact changes are bit-identical; a hold differs only around silence, within the stated bound.
- Every unit gate and reference tier unchanged and passing. Do not loosen one to admit an optimization.
- Solver statistics, cap hits and finite output over the same runs. Bit-exactness is defined by the output and by the state that determines future output, not by these counters. For a pure scheduling or code-generation change (interleaving, inlining), where the claim is the same algorithmic work executed differently, unchanged evaluations per solve, re-seeds and cap hits are the expected evidence. Other bit-exact changes can legitimately move a counter: sharing one exact result between equivalent channels, or skipping a solve whose exact result is already known, does less work for the same result. If a counter changes, explain why, decide whether it is diagnostic only or reflects different arithmetic (fewer iterations from a looser acceptance is different arithmetic), and prove that output and future state still meet the claimed class.
- Before and after by layout and signal, with static and moving controls as separate rows, including the rows that did not improve. Both kernels are timed by the same harness, built with the product's compile and link settings ([harness](../../juce-plugin/references/performance-investigation.md#harness-and-tooling)), and the hardware the gain was measured on is named.
- A switch that disables the shortcuts, used by tests as the reference engine.
- Identity: where the project defines its model revision as the identity of the audio and mathematical model, a proven bit-exact scheduling or code-generation change need not advance it. A project whose model revision deliberately tracks implementation revisions may decide otherwise. Either way the source revision (commit), the binary hashes and the build identity change and are recorded with the evidence.

## Checklist

- [ ] Stage timings taken; the dominant stage identified; silence benchmarked separately.
- [ ] No item of the validated contract (rate, integrator, tolerance, tables, cadence) changed without a new revision and its gates.
- [ ] Duplicated, inactive and invariant work removed before any numerical change; each change classified.
- [ ] Channel sharing only where inputs **and** complete semantic state are equivalent; explicit comparison and complete copy; mid-block divergence tested; output bit-exact.
- [ ] Differing channels interleaved only where each channel's operation order is unchanged; granularity chosen by measurement; identical channels still shared; bit-exact against two mono engines with matching state, inputs and control trajectory.
- [ ] Hot call boundaries read from the shipped binary; inlining variants timed separately; gains inside the noise rejected.
- [ ] Transitions between shortcut paths tested, with the path taken reported.
- [ ] Hold applied only to a convergent deterministic subsystem; tested at that subsystem's input; surrounding tails intact.
- [ ] Hold tolerance derived from the measured noise floor over corners; looser value tried; residuals and bound reported.
- [ ] Hold invalidated within the block by every relevant change (input, controls, mode, bypass, rate, configuration, reset, restore).
- [ ] Solver counters unchanged for scheduling and code-generation changes, and any counter change explained and shown not to alter output or future state; static and moving controls reported separately; the measured hardware named.
- [ ] Null test and every gate pass, the null test on each supported target, compiler and floating-point mode for rescheduled or recompiled code; unchanged costs reported with the reason.
