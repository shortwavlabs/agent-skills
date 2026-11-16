# Visual-first acceptance and the frozen visual oracle

The process lesson from Prismatica's runtime editor:
- **B2** optimized against engineering gates first, passed them all, and was rejected by the owner on appearance.
- **B3** established the appearance first and won the owner's acceptance.
- **B3-O** then optimized under a frozen visual oracle without changing a pixel.

This reference owns that process and the comparison rules. [Runtime QA](runtime-qa.md) owns the asset, host and candidate checks it relies on.

**Evidence.** Prismatica `docs/ui/ui-b3o-visual-oracle.md`, `ui-b3o-experiment-ledger.md`, `ui-b3-refinement-1-final-report.md` and `ui-b2-production-asset-final-report.md`. The thresholds and counts are **case-study values**.

## Contents

- [The six phases](#the-six-phases)
- [What the oracle freezes](#what-the-oracle-freezes)
- [Matched comparisons](#matched-comparisons)
- [Comparison classes](#comparison-classes)
- [Failure patterns this prevents](#failure-patterns-this-prevents)

## The six phases

1. **High-fidelity reference.** Build the best runtime representation achievable, without optimizing yet: full geometry, adequate texel density, the master's own lighting intent, local reflections, and the signature details (wear, LED, engraving).
2. **Owner approval in the real plug-in.** Review the actual editor in the target host and WebView, at the product's editor sizes and closest zoom.
   - A Blender Cycles render, a desktop-browser capture or a locked-screen run is not the plug-in.
   - Approval covers the **runtime as a whole**: asset, lighting, probes and renderer settings.
3. **Freeze the oracle** ([below](#what-the-oracle-freezes)) by hash, and treat it as read-only.
4. **Profile.** Find the real costs before reducing anything: memory by process, load and first-frame time, frame time and per-pass cost on the target hardware. Separate work eliminated from work moved ([attribution lessons](../../juce-plugin/references/webview-gpu-memory-and-context-recovery.md#rejected-approaches-and-attribution-lessons)).
5. **Controlled optimization.** One hypothesis and one change at a time, each with its comparison class declared in advance, then measured, compared and accepted or rejected. Keep rejected candidates in a ledger with their evidence. Every change stays reversible to the oracle.
6. **Qualification.** Runtime performance, functional contracts, visual equivalence to the oracle, and host compatibility, on the final binaries.

**Case study.** Accepted B3 cost more than rejected B2:
- 597,676 against 249,168 triangles;
- about 232 against 102 MiB of decoded textures;
- 1,048–1,161 against 572–587 MB of WebKit helper RSS per editor (the measure used before B3-O; its physical footprint was later measured at about 1.32–1.33 GB).

B3-O then removed about 294 MB per editor (−22 %) with **all 45 oracle views byte-identical**. Fidelity first gave the optimization a fixed target; B2's gates had protected numbers that were not the product.

## What the oracle freezes

The complete rendering configuration, not only the GLB. Prismatica's oracle recorded, by hash:
- the GLB and its derivative `.blend`, build manifest, validation and texel-density reports, wear and look-development read-outs;
- the HDRI;
- camera presets;
- the runtime scene code and the built page bundle;
- the plug-in binaries;
- the three.js and WebView-package versions;
- the machine and OS;
- a table of every rendering setting: lights, probes, environment, tone mapping, exposure, shadow maps, pixel ratio, MSAA.

The frozen copies were 81 files under one digest.

**Fix the views as data.**
- Prismatica's 45 views:
  - camera presets at two editor sizes;
  - every control and state (knobs at their limits, toggles, footswitch, LED lit and bypassed);
  - close-ups of the signature materials at the closest zoom.
- Each view is captured in the plug-in's own WebView, in a visible, unlocked session.
- The capture must be **repeatable before it can be a reference**: the 45 views were byte-identical across 3 fresh host processes.

## Matched comparisons

A comparison is valid only when everything but the candidate is identical:
- the same camera, canvas size and pixel ratio;
- the same control states;
- the same lighting, environment and probes;
- the same WebView backend and session conditions.

Cover the default view **and** the closest zoom at the largest editor size, plus regions of interest per material: chrome and nickel, spun metal, wear, the LED, engraving, paint boundaries, black plastic.

## Comparison classes

Declare the class before running the candidate:

| Class | For | Rule |
|---|---|---|
| **A** | a change that must not touch pixels (resource release, instrumentation, scheduling) | every view byte-identical |
| **B** | a change that may move pixels (texture size, shadow resolution, transmission resolution) | per view (Prismatica's thresholds): at most 0.1 % of pixels more than 8 codes off in any channel, the largest connected patch of such pixels at most 16 px, and the 99.9th percentile at most 8 codes. Any view with a difference above 2 codes gets a 1:1 crop sheet (oracle / candidate / difference × 8), which must be reviewed by eye |

- **A global score never excuses a local defect.** A class-B candidate that passes the numbers is still rejected if a crop shows any of: flatter chrome, a lost highlight, blurred wear, a flatter LED, shallower engraving, shifted colour or changed lighting.
- **Never loosen a threshold to obtain a pass.**
- **A materially visible change needs the owner**, however good the scores.
- **Self-test the thresholds** with a known small, real change. Prismatica used a probe move that changed 0.96 % of pixels in a 630 px patch, which class B correctly rejects.
- **Error against the master is a tuning aid, not acceptance.** The accepted refinement scored worse against the Cycles master than the unapproved checkpoint ([runtime lighting](../../guitar-product-render/references/runtime-lighting-and-probes.md#what-b3-changed)).

## Failure patterns this prevents

| Pattern | Case study |
|---|---|
| Structural gates read as quality | B2 passed the validator, re-import, an 11 µm position audit and host integration, and was rejected ([geometry fidelity](../../guitar-gear-modeling/references/runtime-derivative-and-geometry-fidelity.md#gates-are-necessary-not-sufficient)) |
| Optimizing before the target exists | B2's 250,000-triangle target damaged knob shading while frames were not geometry-bound |
| An engineering rating standing in for the owner | B2's LED was rated "Improved"; the owner saw a painted red circle |
| A defect blamed on the wrong layer | B3's "missing wear" was lighting and probes, not the materials |
| Evidence from the wrong runtime | Chromium or Cycles images presented as plug-in evidence; locked-screen captures |
| A comparison that did not apply the candidate | see [performance candidates](runtime-qa.md#performance-candidates-that-can-change-appearance) |
