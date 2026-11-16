# Reproducible runtime derivatives and geometry fidelity

How to build a runtime GLB as a reproducible derivative of a protected Blender master, and why reducing visible geometry is the riskiest optimization in the pipeline. Extends [runtime export](runtime-export.md); materials belong to [runtime PBR](../../guitar-gear-materials/references/runtime-pbr.md) and acceptance to the [visual oracle](../../guitar-gear-qa/references/visual-oracle.md).

**Evidence.** Two products, each a labelled case study, not a template:
- **Yellow Punch:** an overdrive pedal, its runtime build script and report.
- **Prismatica:** a chorus pedal, its builds B2 and B3 in `Blender/prismatica/b2|b3/` and its reports in `docs/ui/ui-b2-*` and `ui-b3-*`.

| Label | Meaning |
|---|---|
| **Validated** | implemented and evidenced, or owner-accepted |
| **Case-study value** | a number that worked there; derive your own |
| **Rejected** | tried and turned down, with the reason |
| **Limitation** | a known gap |

## Contents

- [Protect the master, build a derivative](#protect-the-master-build-a-derivative)
- [Make the build reproducible](#make-the-build-reproducible)
- [Gates are necessary, not sufficient](#gates-are-necessary-not-sufficient)
- [Reduce invisible geometry, not glossy geometry](#reduce-invisible-geometry-not-glossy-geometry)
- [Audit shading normals, not only positions](#audit-shading-normals-not-only-positions)
- [The B2 knob case](#the-b2-knob-case)
- [Rules](#rules)

## Protect the master, build a derivative

**Validated (both products):**
- **Hash the master.** The build script asserts the master `.blend`'s SHA-256 before it starts and again after export; audits and probes assert it at their end. A changed master stops the build.
- **Guard the directories.** The script refuses to write into the master's directory or into earlier accepted stages' directories.
- **Never save the master.** Open it, convert in memory, and save the derivative separately: `save_as_mainfile(copy=True)`. Prismatica also hashed the master's whole folder (373 files) before and after the stage and found it identical.
- **Record the build in a manifest beside the GLB:**
  - Blender version (`bpy.app.version_string`; 5.2.1 LTS in both products);
  - glTF exporter version (from the GLB `generator`);
  - master SHA and asset SHA;
  - bake settings;
  - map sizes and texel densities.
- **Key the bake cache to its inputs:** master SHA, bake settings, image sizes, AO distance and a digest of the UVs. A cache that outlives its inputs ships stale textures.
- **Order matters.** Prismatica B2's build (abridged):
  1. collect source objects;
  2. count the master's evaluated triangles and snapshot master meshes and corner normals;
  3. record pivots and extras;
  4. convert evaluated meshes;
  5. **restore the master's material slots**, which conversion drops for object-linked materials;
  6. geometry changes, then triangulate (custom normals kept, zero degenerate triangles asserted);
  7. **bake, before any join**;
  8. join into semantic nodes, add hit proxies, export, orthonormalise tangents.

  Both products bake each part from its own material before joining, because joining loses per-object wear localisation ([object-linked materials](runtime-export.md#evaluated-conversion-and-consolidation)).
- **Cameras ship as data.** Both products export no cameras or lights. Presets live in a JSON file that is checked against the accepted stage (Prismatica: byte-identical to the previous stage's file).
- **Re-import fresh.** Inspect the exported GLB in a clean Blender with `--factory-startup --disable-autoexec`, and validate it with a standard-library validator whose expected values were written by hand. Expected values generated from the same export validate nothing.

## Make the build reproducible

- **Validated (Prismatica B2):** two clean rebuilds gave a byte-identical GLB, 0 of 224 buffer views different (SHA-256 per buffer view). Two changes were needed:
  - **single-threaded baking** (`--threads 1`);
  - **a fixed perpendicular tangent** for faces with zero UV area, instead of whatever the exporter produced.
- **Limitation:** a cold re-bake into an empty cache still differed in 1 of 224 views: 2 texels of one image, by 1 code. Treat the bake cache as a source artifact and record its file list and digest.
- **Limitation (Yellow Punch):** no repeat-build comparison existed. Two builds of equal size had different SHA-256s, and the logs cannot tell whether the script changed in between. Without a repeat check, "the GLB changed" cannot be told apart from "the build is not deterministic".
- **Limitation:** Cycles on the Metal GPU crashed in its kernel cache when two Blender processes baked concurrently. Run bakes alone.
- **A `.blend` is not byte-reproducible.** Compare its content with a digest of the meaningful data, not with a file hash.

## Gates are necessary, not sufficient

Prismatica B2 passed every gate it had:
- the semantic contract;
- the glTF validator;
- the fresh re-import;
- a position audit within 11 µm of the master;
- host integration.

The owner then **rejected** it on visual quality: its lighting, LED, hardware texture density and knob shading were all below standard (diagnosed in B3). Some defects only became visible after the gates had passed:
- a dark band on the knob skirts;
- fine lines on the knob flutes.

A gate checks what it measures. Structural and positional gates cannot see shading, reflection or material identity. Establish the [visual oracle](../../guitar-gear-qa/references/visual-oracle.md) first, then build gates that protect it.

## Reduce invisible geometry, not glossy geometry

**Validated (Yellow Punch):** 1,657,368 → 240,074 triangles, mostly without collapsing anything visible:
- the 1.26 M-triangle engraved cap was replaced by a flat cap carrying a normal map baked selected-to-active from the engraving (correlation 0.97 on groove walls);
- faces that no camera can reach were deleted, and a dark interior liner was added so image-based light cannot tint the cavity;
- the knob bodies were un-subdivided once: 384 → 192 radial segments, about 3 µm chord error;
- the visible hardware kept 153,888 triangles, unreduced.

**Rejected (Prismatica B2):**
- **The triangle target.** B2 aimed at ≤ 250,000 triangles. The master shows 597,500, and B2 reached 249,168 by reducing 7 part families, 409,308 → 59,598. The largest was the knob bodies: 326,400 → 40,800, ratio 0.125.
- **Reducing plated hardware.** Threads, nuts and washers were clean only unreduced.
- **Curvature-guarded collapse** at 1°, 2° and 4°. It folded triangles over, kept 345,086 triangles at 1°, and still left 9 % of knob in-face points more than 2° off.
- **An earlier un-subdivide**, which moved the knob insert lip by 0.47 mm.

**Validated (Prismatica B3, the accepted asset):**
- no reduction at all: 597,676 triangles;
- profiling then showed frames of 1–5 ms against a 16.7 ms display interval on the tested GPU, so geometry was **not a bottleneck there** and reduction was not pursued.

**Limitation:** a weaker GPU may answer differently. Profile it first.

**Visibility probes can mislead.** An 80-direction visibility probe called the pot bushings unreachable. A 2,400-direction probe found rays escaping. No part was dropped on the coarse result.

## Audit shading normals, not only positions

**Why positions are not enough.** Collapse-based decimation minimises positional error and is blind to normals. A collapse can leave a large triangle running from a fillet's end across a flat wall. The renderer then interpolates the fillet's tilt across the wall, so a highlight bends or darkens where the surface is in fact flat. Glossy and metal surfaces show it at once.

**The Prismatica audit** (`audit_normals.py`, Validated):
- **Read the GLB the way a renderer does.** For each exported triangle, sample 7 points: the 3 corners, plus the centroid and the 3 edge midpoints for the **in-face** measure.
- **Compare with the master's interpolated normal at the nearest point.** Try every master triangle within 20 µm and keep the best match.
- **Measure again with the normal map applied** (`n = T·x + B·y + N·z`, read bilinearly). That is the normal that actually shades.
- **Report:**
  - median, 99th percentile, maximum, and the share of points over 2° and over 5°;
  - reachable and unreachable surface separately.
- **Set a pass threshold before reading the result.** Prismatica's audit reported 0.7–1.2 % of knob points over 5° with no threshold, and the part was first rated "equivalent". A later control build proved the defect real.

## The B2 knob case

How the cause of the dark band on the knob skirts was established, one variable at a time (Validated):

| Test | Result |
|---|---|
| Knob AO, normal map, all textures removed | band unchanged: not a texture |
| Knob bodies stopped from casting shadows | band unchanged |
| GLB corner normals against the master | > 5° off at 8.8 % of hardware corners, 1.1–1.4 % of knob corners |
| The master's normals copied to every corner | corners exact, **band unchanged** |
| Normals **inside** faces | still > 5° off at about 6 % of knob points |

**Fixes tried:**
- **Kept, not sufficient alone:** copying the master's normals to the corners.
- **Adopted:** baking each reduced part's normal map from the **master part's surface**:
  - selected-to-active;
  - 40 µm cage, 0.2 mm ray distance;
  - 128 samples (16 samples left grain in the normal map).

  Result: in-face p99 16.9° and 5.5 % over 5°; with the normal map applied, 0.7–1.2 % over 5°.
- **Not repaired:** fine lines remained on the knob flutes at the closest zoom.
  - **The control:** a build with the knob bodies at the master's tessellation (533,158 triangles) had no lines. The normal map differed at 20 % of texels, stepping at the boundaries between flutes and lands.
  - **The rating:** "Degraded at the closest zoom".
  - **Do not claim normal-map baking always repairs collapsed geometry.** It did not here.

## Rules

1. Establish and approve the high-fidelity reference first; reduce later, and only with evidence.
2. Profile the target before reducing: triangles, draw calls, frame time, and per-pass costs such as shadow and transmission passes.
3. No global triangle target without a measured reason.
4. Remove what cannot be seen first:
   - unreachable faces, verified with enough probe directions;
   - hidden internals;
   - construction history;
   - relief that a normal map reproduces, verified by correlation on the relief.
5. Keep silhouette-critical, glossy and visually prominent hardware unreduced unless a matched close-up at maximum zoom accepts the reduction.
6. Preserve curvature boundaries:
   - fillets;
   - thin bevels;
   - flutes and lands;
   - machining rings and thread crests.
7. Audit normals inside faces and after the normal map, with a pass threshold, and look at low-angle specular highlights.
8. Change one variable at a time, compare matched views, and keep a control build that isolates the suspect change.
9. Reject a reduction whose measured benefit does not pay for its visual cost.
