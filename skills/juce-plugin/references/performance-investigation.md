# Plugin Performance Investigation

## Contents

- When to use this reference
- Attribute before optimizing
- Two measurements, two questions
- Measurement matrix
- Stage breakdown and reading a profile
- Harness and tooling
- Prove equivalence
- Equivalence classes
- Editor and WebView cost
- Multi-instance scaling
- Gate hierarchy
- Report and definition of done

## When To Use This Reference

Read this when a plugin "uses too much CPU", before any performance pass, and when adding performance gates. **Measure first.** High plugin CPU is not a reason to lower oversampling, shrink textures, lower the pixel ratio, merge meshes, rewrite a solver or blame the WebView; the first task is attribution.

This reference owns the plugin-level method: attribution, measurement, tooling, gates and reporting. Domain detail has one owner each:

- Speeding up a validated circuit model without changing it (shared channels, settled-state hold, what forces re-validation): `circuit-to-dsp` skill, [model-performance.md](../../circuit-to-dsp/references/model-performance.md).
- Meter, repaint, telemetry and DOM cost in a WebView: [webview-ui.md](webview-ui.md#streaming-visual-data).
- Three.js render and shadow invalidation, redraw cadence, pixel ratio, draw calls: [threejs-webview-ui.md](threejs-webview-ui.md#rendering-threading-and-lifetime).
- Visual accept/reject evidence for anything that can change the picture: `guitar-gear-qa` skill, [runtime-qa.md](../../guitar-gear-qa/references/runtime-qa.md#performance-candidates-that-can-change-appearance).
- Runtime texture density and memory: `guitar-gear-materials` skill, [runtime-pbr.md](../../guitar-gear-materials/references/runtime-pbr.md#budget-from-pixels-then-profile).

Italic case-study notes describe one product on one machine. They show how a decision was reached; the figures are in the `circuit-to-dsp` skill's [case study](../../circuit-to-dsp/references/case-study-sd1-overdrive.md). Derive your own.

## Attribute Before Optimizing

A plugin with a web editor typically has these cost domains, measured by different tools (the process model depends on the WebView backend, and DSP is not always a single thread):

| Domain | Runs in |
|---|---|
| DSP | Audio thread |
| Native editor, timers, bridge | Host message thread |
| Page script, style, layout, paint | WebView content process |
| WebGL, raster, compositing | WebView GPU process and the GPU |

**Host meter semantics are host-specific.** Establish what the reported figure measures before interpreting it. Many DAW realtime or "audio" meters mainly show audio-engine deadline load, not total process CPU; editor and WebView cost may then sit on other threads or helper processes and not appear in that figure at all. A system monitor shows something else again (whole processes). Do not rely on the meter's label: verify with the isolations below, on the same Release binary, before reading code for "the slow part".

1. **Editor closed versus open.** Measure the audio callback in both. If it does not move, the callback cost is not the editor, however heavy the editor looks.
2. **Bypassed versus active.** A cheap bypass that drops the callback to near zero localises the cost to the DSP path, not the wrapper, parameters or lifecycle.
3. **Silence versus signal.** Silence is a test signal, not an assumption. It can be cheaper, equal or dearer (state integration, solver iterations, denormals, tails, noise models).
4. **CPU by thread and process**: audio callback, host main thread, WebView content process, WebView GPU process, each with the editor idle, with audio playing, and while something moves.

*Case study: for a pedal plugin with a 3D WebView editor, the live callback read the same with the editor open or closed and near zero when bypassed, and the idle editor drew no frames. The figure its DAW reported was the circuit model; the editor's cost was real but in other processes. A plugin with the same symptoms can have the opposite answer: the isolations decide, not this precedent.*

## Two Measurements, Two Questions

| | Headless, back to back | Live audio callback |
|---|---|---|
| What | Production DSP in a loop on one thread, as fast as it runs | The built plugin (or production processor) inside a real audio-device callback |
| Answers | How much work? Before/after ratios, stage attribution, sweeps | Is the deadline met? Duty cycle, p99/max, overruns, editor open/closed, instance scaling |
| Noise | Low when the harness is sound | Depends on the scheduling and clock the OS gives the thread |
| Blind to | Scheduling, clock scaling, the editor | Which stage pays |

- A sleep-paced synthetic loop is neither: it can read far above or below both.
- Callback duty cycle depends on scheduling and CPU clock scaling as well as on work. Compare algorithms with headless numbers and judge deadlines with live numbers, and do not derive per-sample cost from host percentages across buffer sizes. *Observed on macOS/Apple silicon: a longer block read a larger percentage for the same work per sample, and total duty was not linear in instance count.*
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

Hosts often instantiate an effect stereo even on a mono source, so "stereo with identical L/R" is a common real case and needs its own row.

## Stage Breakdown And Reading A Profile

Split the callback into its major stages (input conditioning, up/down-sampling, nonlinear or circuit core, tone and filter stages, host-rate scaling and smoothing, meters, dry/bypass path) and time each. Prefer timing the same pieces directly in the harness (the resampler alone, the core alone on already-upsampled input, the whole engine) to instrumenting the production callback.

- **Optimize the dominant stage, not the most obvious code.** Parameter reads, meters, host-rate arithmetic and buffer copies are easy to spot and often negligible next to a nonlinear core.
- The [hot-path audit](audio-thread-safety.md#hot-path-audit) finds risks; the profile sets priority.
- Do not assume the resampling filters are the cost of an oversampled design. Time the filters and the work done inside the oversampled domain separately.
- A sampling profiler can pile samples on the instruction where a long dependency chain finally resolves, often the last store or state commit of a stage. That marks where the chain ends, not necessarily where time is spent. For serial numerical kernels, read the dependency structure and the generated code and trust stage timings over flat-profile percentages. Simple arithmetic can be latency-bound.

*Case study: nearly all of the callback was the circuit core; the oversampling filters were a few percent and host-rate work under one. The profiler put almost a third of its samples on a short state commit that was only the end of the chain.*

## Harness And Tooling

The benchmark is part of the experiment. Validate it before trusting a difference.

- Release build, production DSP sources, warm-up excluded, input synthesised outside the timed region.
- **Match production object lifetime and placement.** Construct and own the engine the way the product does: on the heap inside the processor if that is what ships, embedded differently if it is not. A benchmark can mislead because its environment changes code or data placement or scheduling.
- Before and after with the **same harness code** built against both DSP revisions, same compiler and flags, same construction, runs interleaved.
- Keep benchmark scheduling consistent and record it (priority or QoS class, and core tier on machines that have tiers); control unwanted migration where practical. A benchmark thread is not a realtime audio thread: use the live callback for deadline behaviour.
- Re-run an outlier before believing it. If timings change with things that should not matter (environment size, path, an unrelated edit), fix the harness first.
- Keep instrumentation out of the product: measurement modes live in harness and test targets.

*Case study: with the engine on the benchmark thread's own stack, identical code timed up to 30 % apart depending only on the size of the process environment. Constructed as in the plugin (there, on the heap) it was stable. The lesson is to match production, not that the heap is faster.*

Three small tools answer most questions:

| Tool | Does | Used for |
|---|---|---|
| Headless harness | Runs the production engine over the matrix; reports share of real time, percentiles, stage split, solver statistics; dumps reference renders | Stable comparison of work; null tests |
| Live host | Loads the **built** plugin binary, runs it in a real audio-device callback (silence to the device), optionally opens the real editor; reports callback duty (average, p99, max, overruns) and CPU by thread and helper process | Host-like numbers without a DAW; editor open/closed; instance ladder |
| Editor QA host | Hosts the real editor in the real system WebView and drives it like a host and a user | Deterministic editor acceptance and render studies; see `guitar-gear-qa` [runtime QA](../../guitar-gear-qa/references/runtime-qa.md) |

General notes for the live host:

- Count frames, draw calls, bridge messages each way and resize events by wrapping the page's own entry points from the tool. Do not ship debug counters to get them.
- Keep the measured editor in the visibility state the scenario means, and record whether the platform's WebView throttles hidden, minimized, backgrounded or occluded content. Do not define correctness from one platform's throttling behaviour.
- Where a test host and a dynamically loaded plugin each statically contain the same framework (or other weak or global symbols), symbol interposition can cause hard-to-diagnose crashes. Whether it happens depends on the platform, linker, visibility settings, framework build and plugin format; hiding the test host's symbols is one effective mitigation.
- It is a proxy. Do not report an improvement in a DAW that was not measured: give the proxy figures and the steps to confirm them there.

**macOS / Apple-silicon implementation example** (what the case study used; find and verify the equivalents on other platforms):

- Callback timing: a monotonic clock around `processBlock` inside an audio-device callback, with JUCE's plugin-hosting classes loading the built bundle.
- CPU accounting: per-thread CPU time for the host's own threads, and the resource-usage record by process id for the WebKit content and GPU helpers, whose ids the embedding process can read (a non-public interface: test tools only).
- Scheduling: the headless thread ran at the user-interactive QoS class to keep it on one core tier. That is an experimental control for that machine, not a model of realtime audio scheduling.
- Frame time: render, then read back one pixel so the GPU must finish before the clock stops, averaged over many frames because page timers are coarse.
- Visibility: an occluded WebView delivered no animation frames there, so the measured window was kept in front.
- Symbols: a JUCE test host crashed inside a JUCE plugin's editor until the host was built with hidden symbol visibility.

## Prove Equivalence

A performance change is incomplete without output evidence against the previous build.

1. Before touching the DSP, render a reference set from the unmodified engine: every supported rate, several buffer sizes, each layout, representative signal, automation, gain and control steps, bypass transitions, overload, silence, a tail into long silence, and signal after long silence.
2. After each change compare sample by sample. A change claimed bit-exact must be bit-identical. For a bounded change report the largest difference in dBFS, with the float rounding of the output separated from any real difference.
3. Check solver statistics, cap hits and finite output over the same runs.
4. Run every existing correctness gate unchanged (unit tests, reference tiers). Do not relax a tolerance to admit an optimization.

## Equivalence Classes

Classify every optimization. The class says what evidence it owes and who decides.

| Class | Meaning | Owes | Examples |
|---|---|---|---|
| **Bit-exact** | Output and the state that determines future output are identical | A bit-identical null test | Sharing work between identical channels; skipping constant work while smoothers rest |
| **Bounded-numerical** | A measured numerical difference exists inside an explicitly validated bound | The bound, how it was derived, residuals against the unshortened path | A settled-state hold based on a convergence threshold |
| **Visual-equivalent** | Rendering behaviour changes; matched evidence shows no unacceptable visible change (pixel-identical under stated preconditions is the strongest form) | Matched views and the preconditions | Change-driven shadow maps; a lower redraw rate for host-driven changes |
| **Product-semantic** | Behaviour or fidelity actually changes | An explicit product decision | Summing a stereo input to mono; lower model fidelity or oversampling; visibly lower visual quality; removing interaction, views or editor sizes |

The first three are engineering work, done with the evidence shown; where the project has not already set the acceptable bound or visual threshold, that threshold still needs the owner's agreement. A performance pass does not take a product-semantic change silently; it records the option with its cost and gain. Do not describe a bounded change as exact.

## Editor And WebView Cost

A static editor with no intentionally continuous visual behaviour should approach zero frames, zero unnecessary bridge traffic, zero resize callbacks and zero polling when nothing changes. Intentional activity is legitimate and is measured, not forbidden ([idle acceptance](webview-ui.md#idle-acceptance)). Verify with counters, not by reading the code, then measure three active cases separately: audio playing (meter or other telemetry), direct manipulation (orbit, drag, zoom) and host-driven change (automation, preset load).

The patterns have their owners: [webview-ui.md](webview-ui.md#streaming-visual-data) for telemetry, repaint and DOM cost; [threejs-webview-ui.md](threejs-webview-ui.md#rendering-threading-and-lifetime) for invalidation, shadow maps, redraw cadence, pixel ratio and draw calls. Anything that can change the picture is a candidate to accept or reject on matched evidence, not a default.

When a sibling product shares the architecture, measure it in the same host: it separates the architecture's baseline cost from a regression of this plugin.

## Multi-Instance Scaling

One instance is not enough for a plugin that sits on many tracks. Measure a ladder of instances for audio cost, the same ladder with one editor open, and several editors only when that is a supported scenario. Report measurements, not extrapolations: scheduling and clock scaling can make the total non-linear in instance count.

## Gate Hierarchy

The structure is reusable; each project sets its own numbers.

| Layer | Gates |
|---|---|
| DSP correctness | Unit tests; reference or oracle tiers where fidelity is a requirement; null test against the previous build |
| DSP performance | Headless benchmark; live callback with no overruns and p99/p99.9 within a stated share of the block |
| Frontend | Logic tests; idle frame and message counters; interaction tests |
| Integrated editor | Real system WebView host: first-paint sync, both directions, gestures, automation, presets, resize, reopen, teardown mid-gesture, state restore |
| Plugin | Format validators at the accepted strictness |
| Scale | Instance ladder |

Correctness criteria describe product behaviour independently of any performance machine, but they are still run on each supported target configuration where implementation differences (floating point, SIMD path, compiler flags, architecture) can matter. Performance thresholds always name the platform and build they were measured on.

## Report And Definition Of Done

"Optimized" is not a result. A performance task is done when it states **before, after, correctness and what remains**: what improved, what did not and why, what a further gain would require, and whether that would change product semantics. Do not hide an unchanged expensive path.

Write the control document from the unmodified build before the first optimization. A time-boxed pass still needs the four isolations, one headless before/after on the dominant case, a null test and the existing gates; drop breadth, not those. When no target figure was given, report the measured floor and what each further step would cost, and do not invent a target. A thorough pass covers the following.

1. Reported problem and its source (which meter, which host, and what that meter measures).
2. Machine, OS, display, audio device, build, binary hashes.
3. Baseline: editor closed/open, rates, buffers, layouts.
4. Headless benchmark, stage breakdown, profiler findings and how they were read.
5. Editor findings: idle activity, bridge and message rates, drawing buffer and pixel ratio, shadows, textures and memory, draw calls.
6. Implemented optimizations, each with its equivalence class and the evidence that class owes.
7. **Rejected candidates and why.** They are engineering knowledge: a fidelity gate fails, visible degradation, no measured benefit, a memory-only benefit, a platform or security-policy dependency, bit parity lost, complexity above the expected gain. Recording them stops the next agent repeating the same dead ends.
8. Visual comparison; DSP regression and null test; frontend and integrated-editor tests; plugin validation.
9. Multi-instance results.
10. Remaining bottlenecks, separating engineering work from product-semantic decisions.
11. Files changed, and which installed plugin copies were replaced.
