# Plugin Performance Investigation

## Contents

- When to use this reference
- Attribute before optimizing
- Two measurements, two questions
- Measurement matrix
- Stage breakdown and reading a profile
- Harness and tooling
- Prove equivalence
- Editor and WebView cost
- Multi-instance scaling
- Gate hierarchy
- Engineering versus product decisions
- Report and definition of done

## When To Use This Reference

Read this when a plugin "uses too much CPU", before any performance pass, and when adding performance gates. It owns the plugin-level method: attribution, measurement, tooling, gates and reporting. Domain detail has one owner each:

- Speeding up a validated circuit model without changing it (shared channels, settled-state hold, what forces re-validation): `circuit-to-dsp` skill, [model-performance.md](../../circuit-to-dsp/references/model-performance.md).
- WebView meter, repaint and bridge cost: [webview-ui.md](webview-ui.md#streaming-visual-data).
- Three.js render scheduling, shadow maps, pixel ratio, draw calls: [threejs-webview-ui.md](threejs-webview-ui.md#rendering-threading-and-lifetime).
- Matched visual evidence for anything that can change the picture: `guitar-gear-qa` skill, [runtime-qa.md](../../guitar-gear-qa/references/runtime-qa.md#performance-candidates-that-can-change-appearance).

Numbers in the italic case-study notes come from one product on one machine. They show how a decision was reached; derive your own.

## Attribute Before Optimizing

A plugin with a web editor has four cost domains, measured by different tools and shown by different meters:

| Domain | Runs in | In a DAW's audio CPU meter? |
|---|---|---|
| DSP | Audio thread | Yes |
| Native editor, timers, bridge | Host message thread | No |
| Page script, style, layout, paint | WebView content process | No |
| WebGL, raster, compositing | WebView GPU process and the GPU | No |

One host percentage does not say which domain pays, so first establish which meter produced it. A DAW's own CPU meter is audio-engine load: the first row only. A system monitor shows the whole host process (audio and message threads together) and lists the WebView's helper processes separately, under their own names. Then run these isolations, on the same Release binary, before reading code for "the slow part":

1. **Editor closed versus open.** Measure the audio callback in both. If it does not move, the host's audio meter is DSP, however heavy the editor looks.
2. **Bypassed versus active.** A cheap bypass that drops the callback to near zero localises the cost to the DSP path, not the wrapper, parameters or lifecycle.
3. **Silence versus signal.** Silence is a test signal, not an assumption. It can be cheaper, equal or dearer (state integration, solver iterations, denormals, tails, noise models).
4. **CPU by thread and process**: audio callback, host main thread, WebView content process, WebView GPU process, each with the editor idle, with audio playing, and while something moves.

*Case study: a pedal plugin with a 3D WebView editor read about 11 % idle and 16 % playing in a DAW. The live callback read the same with the editor open or closed, bypass read 0.1 %, and the idle editor drew 0 frames. The whole figure was the circuit model; the editor's own cost was real but in other processes. A plugin with the same symptoms can have the opposite answer: the isolations decide, not this precedent.*

## Two Measurements, Two Questions

| | Headless, back to back | Live audio callback |
|---|---|---|
| What | Production DSP in a loop on one thread, as fast as it runs | The built plugin (or production processor) inside a real audio-device callback |
| Answers | How much work? Before/after ratios, stage attribution, sweeps | Is the deadline met? Duty cycle, p99/max, overruns, editor open/closed, instance scaling |
| Noise | Low: repeatable to about a percent | Depends on the clock and core the OS gives the thread |
| Blind to | Scheduling, clock scaling, the editor | Which stage pays |

- A sleep-paced synthetic loop is neither: it can read far above or below both.
- On macOS/Apple silicon, callback duty cycle moves with block duration, QoS and CPU clock scaling. A longer block can read a larger percentage for the same work per sample, and total duty is not linear in instance count. Compare algorithms with headless numbers and judge deadlines with live numbers. Do not derive per-sample cost from host percentages across buffer sizes.
- Label every figure with which measurement it is, plus machine, build, rate, buffer and layout.

## Measurement Matrix

Vary one axis at a time against a fixed default.

| Axis | Values | Reveals |
|---|---|---|
| Signal | Digital silence, sine, representative programme (a guitar-like fixture), overload or stress where relevant | Silence behaviour, level-dependent cost |
| Layout | Mono, stereo with identical L/R, stereo with different L/R | Channel scaling, duplicated work |
| Sample rate | Every representative supported rate | Rate policy; whether cost follows the host or the internal rate |
| Buffer size | Smallest to largest host blocks | Per-block overhead versus per-sample cost |
| Editor | Closed, open idle, open with audio, open interacting (orbit, drag, host automation) | UI cost by domain |
| Plugin state | Active, bypassed, controls static, controls automated | Bypass sanity, smoothing and coefficient cost |
| Instances | A ladder such as 1, 2, 4, 8 | Scaling |

Hosts usually instantiate an effect stereo even on a mono source, so "stereo with identical L/R" is the common real case and needs its own row.

## Stage Breakdown And Reading A Profile

Split the callback into its major stages (input conditioning, up/down-sampling, nonlinear or circuit core, tone and filter stages, host-rate scaling and smoothing, meters, dry/bypass path) and time each. Prefer timing the same pieces directly in the harness (the resampler alone, the core alone on already-upsampled input, the whole engine) to instrumenting the production callback.

- **Optimize the dominant stage, not the most obvious code.** Parameter reads, meters, host-rate arithmetic and buffer copies are easy to spot and usually negligible next to a nonlinear core.
- The [hot-path audit](audio-thread-safety.md#hot-path-audit) finds risks; the profile sets priority.
- Do not assume the resampling filters are the cost of an oversampled design. Time the filters and the work done inside the oversampled domain separately.
- A sampling profiler piles samples on the instruction where a long dependency chain finally resolves, often the last store or state commit of a stage. That marks where the chain ends, not where time is spent. For serial numerical kernels, read the dependency structure and the generated code and trust stage timings over flat-profile percentages. Simple arithmetic can be latency-bound.

*Case study: 87–94 % of the callback was the circuit core, 5–7 % the oversampling filters, under 1 % everything at host rate. The profiler put 30 % of samples on a short state commit that was only the end of the chain.*

## Harness And Tooling

The benchmark is part of the experiment. Validate it before trusting a difference.

- Release build, production DSP sources, warm-up excluded, input synthesised outside the timed region.
- Production-like object placement and lifetime: allocate the engine the way the plugin does (normally on the heap, inside the processor).
- Before and after with the **same harness code** built against both DSP revisions, same compiler and flags, runs interleaved. Pin thread QoS so a run does not move between core tiers.
- Re-run an outlier before believing it. If timings change with things that cannot matter (environment size, path, an unrelated edit), fix the harness first.
- Keep instrumentation out of the product: measurement modes live in harness and test targets.

*Case study: with the engine on the benchmark thread's own stack, identical code timed between 5.1 % and 6.6 % depending only on the size of the process environment. On the heap, as in the plugin, it was stable.*

Three small tools answer most questions:

| Tool | Does | Used for |
|---|---|---|
| Headless harness | Runs the production engine over the matrix; reports share of real time, percentiles, stage split, solver statistics; dumps reference renders | Stable comparison of work; null tests |
| Live host | Loads the **built** plugin binary, runs it in a real audio-device callback (silence to the device), optionally opens the real editor; reports callback duty (average, p99, max, overruns) and CPU of the host main thread and the WebView content and GPU processes | Host-like numbers without a DAW; editor open/closed; instance ladder |
| Editor QA host | Hosts the real editor in the real system WebView and drives it like a host and a user | Deterministic editor acceptance and render studies; see `guitar-gear-qa` [runtime QA](../../guitar-gear-qa/references/runtime-qa.md) |

Live-host notes:

- Count frames, draw calls, bridge messages each way and resize events by wrapping the page's own entry points from the tool. Do not ship debug counters to get them.
- A JUCE-based host that loads a JUCE plugin must export no symbols of its own (hidden visibility), or the dynamic loader can merge the two copies' weak symbols and crash inside the plugin's editor.
- Keep the measured window visible and unobscured; an occluded WebView stops delivering animation frames.
- It is a proxy. Do not report an improvement in a DAW that was not measured: give the proxy figures and the steps to confirm them there.

Implementation hints (macOS; check the equivalents on other platforms):

- Live host: JUCE's plugin-hosting classes load the built bundle; an audio-device callback fills the input, calls `processBlock` and is timed with a monotonic clock around that call.
- CPU of the host's own threads: per-thread CPU time from the thread-info API. CPU of another process: its resource-usage record by process id. The system WebView exposes its content and GPU process ids to the embedding process; in a test tool, reading them is acceptable.
- Pin the benchmark thread to the user-interactive QoS class so it stays on the fastest core tier.
- Frame time: render, then read back one pixel so the GPU must finish before the clock stops; average over many frames, because page timers are coarse.
- Counters: wrap `requestAnimationFrame`, the WebGL draw calls and the bridge's emit functions from an injected script.

## Prove Equivalence

A performance change is incomplete without output evidence against the previous build.

1. Before touching the DSP, render a reference set from the unmodified engine: every supported rate, several buffer sizes, each layout, representative signal, automation, gain and control steps, bypass transitions, overload, silence, a tail into long silence, and signal after long silence.
2. After each change compare sample by sample. Exact shortcuts must be bit-identical. Otherwise report the largest difference in dBFS, with the float rounding of the output separated from any real difference.
3. Check solver statistics, cap hits and finite output over the same runs.
4. Run every existing correctness gate unchanged (unit tests, reference tiers). Never relax a tolerance to admit an optimization.

## Editor And WebView Cost

Idle acceptance, verified with counters and not by reading the code: a stable open editor draws zero frames and exchanges zero bridge messages, with no resize callbacks and no parameter or preset polling, apart from telemetry that is deliberately active. Then measure three active cases separately: audio playing (meter), direct manipulation (orbit, drag, zoom) and host-driven change (automation, preset load).

The patterns are in [webview-ui.md](webview-ui.md#streaming-visual-data) (meter and repaint cost, DOM batching) and [threejs-webview-ui.md](threejs-webview-ui.md#rendering-threading-and-lifetime) (invalidation, shadow maps, redraw cadence, pixel ratio, draw calls). Anything that can change the picture is a candidate to accept or reject on matched evidence, never a default. Texture resolution in particular is usually a memory cost, not a frame-time or CPU cost ([budget from pixels](../../guitar-gear-materials/references/runtime-pbr.md#budget-from-pixels-then-profile)).

When a sibling product shares the architecture, measure it in the same host: it separates the architecture's baseline cost from a regression of this plugin.

## Multi-Instance Scaling

One instance is not enough for a plugin that sits on many tracks. Measure a ladder of instances for audio cost, the same ladder with one editor open, and several editors only when that is a supported scenario. Report measurements, not extrapolations: clock scaling makes the total non-linear, and one open editor should cost the same whatever the instance count.

## Gate Hierarchy

The structure is reusable; each project sets its own numbers on its own named machine.

| Layer | Gates |
|---|---|
| DSP correctness | Unit tests; reference or oracle tiers where fidelity is a requirement; null test against the previous build |
| DSP performance | Headless benchmark; live callback with no overruns and p99/p99.9 within a stated share of the block |
| Frontend | Logic tests; idle frame and message counters; interaction tests |
| Integrated editor | Real system WebView host: first-paint sync, both directions, gestures, automation, presets, resize, reopen, teardown mid-gesture, state restore |
| Plugin | Format validators at the accepted strictness |
| Scale | Instance ladder |

Correctness gates are machine-independent. Performance gates are machine-specific and name the machine.

## Engineering Versus Product Decisions

| Engineering optimization: do it and prove it | Product decision: raise it, do not slip it in |
|---|---|
| Removing duplicated or already-known computation with identical output | Summing a stereo input to mono |
| Suspending work that is provably settled | Lower model fidelity, oversampling or solver accuracy |
| Change-driven shadow maps and redraws | Visibly lower visual quality |
| Telemetry throttling that keeps the display's meaning | Removing interaction, views or editor sizes |

A performance pass must not take a right-hand choice silently. Record it as an option with its cost.

## Report And Definition Of Done

"Optimized" is not a result. A performance task is done when it states **before, after, correctness and what remains**: what improved, what did not and why, what a further gain would require, and whether that would change product semantics. Do not hide an unchanged expensive path.

Write the control document from the unmodified build before the first optimization. A time-boxed pass still needs the four isolations, one headless before/after on the dominant case, a null test and the existing gates; drop breadth, not those. When no target figure was given, report the measured floor and what each further step would cost, and do not invent a target. A thorough pass covers the following.

1. Reported problem and its source (which meter, which host).
2. Machine, OS, display, audio device, build, binary hashes.
3. Baseline: editor closed/open, rates, buffers, layouts.
4. Headless benchmark, stage breakdown, profiler findings and how they were read.
5. Editor findings: idle activity, bridge and message rates, drawing buffer and pixel ratio, shadows, textures and memory, draw calls.
6. Implemented optimizations, each with its equivalence class: bit-exact, bounded (with the bound), or visual.
7. **Rejected candidates and why**: breaks a reference gate, visibly softer, shadow or texture artifacts, saves memory but no CPU, dependency or security-policy cost, negligible measured cost, breaks bit parity, complexity above benefit. They stop the next agent rediscovering the same dead ends.
8. Visual comparison; DSP regression and null test; frontend and integrated-editor tests; plugin validation.
9. Multi-instance results.
10. Remaining bottlenecks, split into engineering work and product decisions.
11. Files changed, and which installed plugin copies were replaced.
