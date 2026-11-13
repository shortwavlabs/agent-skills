# Real-Time Implementation

Turning a validated BBD reference into an engine that runs in a plug-in callback without changing its sound. Host-specific matters (APVTS, editors, wrapper threading, validators) belong to the `juce-plugin` skill; this file covers the engine.

## Contents

- [Engine Shape](#engine-shape)
- [CPU Budget](#cpu-budget)
- [Allocation, Locks and Determinism](#allocation-locks-and-determinism)
- [Block-Size and Sample-Rate Handling](#block-size-and-sample-rate-handling)
- [Precision and Denormals](#precision-and-denormals)
- [Linear Networks With a Varying Pot](#linear-networks-with-a-varying-pot)
- [Long-Duration Operation](#long-duration-operation)
- [Lifecycle, State, Latency and Tail](#lifecycle-state-latency-and-tail)
- [Multiple Instances](#multiple-instances)

## Engine Shape

- **A framework-free library** behind a small API (`prepare`, `process`, `reset`, `setParameters`), testable without a plug-in host.
- **Fixed-size, trivially copyable cores** sharing an immutable design object built at prepare time. A mode crossfade can then copy a running core with no allocation.
- **Double precision inside, float at the API.**
- **Per host sample** (*case study*): sanitize the input, upsample, tick the core(s) at the internal rate, decimate, apply the routing and bypass ramps.
- **Inside a core tick** (*case study* order):
  1. input stage;
  2. control (CV, then clock);
  3. BBD transfers;
  4. reconstruction, expandor and swing limit;
  5. the regeneration summer step;
  6. pre-emphasis and compressor;
  7. anti-alias;
  8. BBD input coupling;
  9. resolve the previous sample's captures.

  Fix the order once and keep it: a reorder changes the bits.

## CPU Budget

- **Measure before optimizing.** *Case study:* the whole engine cost 1.2–1.8 % of a core (M-series laptop) at 2× internal rate, so no optimization was attempted for the faithful model.
- **Budget an extension separately.** *Case study:*
  - an active regeneration copy cost +27–39 % with a 15-state reduction (+53–74 % for the full 25-state copy);
  - by mode, ×1.34–1.35 median: +0.40–0.58 % of a core, at most 2.47 % per instance;
  - idle ×1.005, because the copy is skipped when settled.
- **After a reference is frozen by hash, an optimization is a sound change.** *Case study:*
  - a column-major layout was slower **and** not bit-identical (705,599 of 705,600 steps differed): floating-point sums reordered;
  - skipping exact zeros was worth at most 3 %, and would change −0 and inf/NaN semantics.

  Both were rejected. Optimize before freezing, or accept a new equivalence revision.
- **Headless benchmarks measure work, not deadlines.** Run interleaved A/B rounds, both run orders, and report the noise floor (*case study:* ×1.023 median). Then check deadlines in a live callback at small blocks.
- **A relative CPU gate can be legitimately missed.** *Case study:* "no substantial CPU regression" was **not met** while regenerating, and the overhead was accepted by the owner as the price of the feature. Record such a gate as NOT MET with the decision, not as passed.

## Allocation, Locks and Determinism

- **Only `prepare()` allocates.** No locks, file I/O, exceptions or virtual dispatch in the per-sample path.
- **Bound every loop:**
  - BBD transfers per sample ≤ ⌊2 f_max / fs⌋ + 1 (size fixed pending arrays from it, and reject rates that would exceed it);
  - LFO corner handling ≤ 2 per tick (guarded);
  - matrix steps of fixed size;
  - resampler taps fixed.
- **Verify with an allocation counter in the tests**, and with a live-callback allocation counter in a host.
- **Determinism:**
  - `reset()` followed by the same input gives the same output, bit for bit;
  - re-prepare gives the same output as a fresh instance;
  - zero input after reset gives exactly zero output.

## Block-Size and Sample-Rate Handling

- **Apply parameter targets at the first sample of a block, and smooth per sample or per control tick inside the engine.** Use integer arithmetic for any control-grid phase, so block size cannot change it.
- **Tests:**
  - blocks of 1, 7, 64, 511 and 2048 against 128 must be bit-identical;
  - under automation, bit-identical when blocks split only at parameter changes;
  - one oversized call (larger than prepared) must equal the chunked result;
  - repeat while regenerating.
- **Internal rate:** chosen from filter-realization error (see [clock-and-modulation.md](clock-and-modulation.md#host-rate-internal-rate-and-aliasing)). Report the resulting integer latency per host rate.
- **Supported rates:** define the range. Outside it, choose a documented behaviour (engine silence or plug-in pass-through), never undefined output.
- **Design the filters per rate at `prepare()`,** with no runtime root-finding.

## Precision and Denormals

- **Flush denormals inside the engine** (arm64 FPCR.FZ, x86 MXCSR FTZ/DAZ), restored on exit, in addition to any wrapper guard.
- **Do not build with fast-math.** It breaks exactness and the reproducibility the references depend on.
- **Test silence:** no subnormal state after 60 s of zeros; a silent block costs what a loud one costs (*case study:* 148 vs 149 µs).
- **Sanitize input:** NaN, ±Inf and absurd levels → 0. A non-finite internal state resets the cores and increments a counter the tests watch.
- **Plug-in parameters are float.** A preset value like 0.6 becomes 0.6000000238 through the host. Expect a small residual between the engine and the plug-in (*case study:* −69.8 dB on DI, against −132 dB engine to reference). Feed offline references float32-rounded values when comparing for bit-identity.

## Linear Networks With a Varying Pot

**A summing network with a pot in it (the regeneration/feedback node) can be modelled as a trapezoidal MNA descriptor.**

*Case study:*
- 25 states;
- a step prewarped at 3 kHz;
- a dense inverse at the pot's mid position computed once.

**The pot as a low-rank update.** The pot's movement is a rank-2 update: G(P) = G(0.5) + U diag(Δg) Uᵀ.
- Per sample: y = Qx − PU·M·Uᵀx + PB(u + u₀), then x' = y − PU·W·Uᵀy.
- W = (I + MK)⁻¹M is a closed-form 2×2, recomputed only while the pot moves.
- About 625 MACs per sample; 5e-13 relative against a dense solve.

## Long-Duration Operation

- **Run 10 minutes or more:**
  - with regeneration active;
  - with excitations spaced across the run;
  - with automation.
- **Check:** levels stay bounded, there is no drift (dB/s), there is no DC creep (use a Hann-weighted mean: a rectangular mean read 4.2e-3 V for a true 1e-5 V), and every output is finite.
- **Watch the clock phase accumulator:** keep it in an integer-plus-fraction form or wrap it, so precision does not decay over hours.

## Lifecycle, State, Latency and Tail

- **State.** Store parameters plus a **model revision** string, which changes only when the audio changes, separately from the **state schema version**. Old states restore new parameters at safe defaults: an enhancement off.
- **Latency.** Report it from `prepare()` for the actual host rate, and re-report it when the rate changes. *Case study:* 96 → 44.1 → 96 → 48 kHz gives 0 / 20 / 0 / 20 samples.
- **Bypass.** A wrapper-level raw-dry bypass, delayed by the latency, with a short crossfade (*case study:* 20 ms raised cosine). This is independent of trims, unlike an engine-internal bypass. Bypass hides a sustained regeneration but does not stop it.
- **Tail.**
  - Finite for a faithful loop: compute it from the maximum delay and the per-pass loss (*case study:* 1.5 s reported; 0.93 s measured worst case).
  - **Infinite** once the loop can sustain, if the framework cannot notify a tail change.

## Multiple Instances

- Each instance owns its cores; nothing is shared but immutable tables.
- Measure 8 instances in a live callback: *case study* p99.9 about 23 % of the period at 48 kHz / 128, with regeneration active.
- Include editors open in multi-instance host tests (see the `juce-plugin` skill's host-automation reference).
