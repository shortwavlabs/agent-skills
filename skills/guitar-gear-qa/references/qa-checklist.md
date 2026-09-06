# Guitar Gear QA Checklist

Use this matrix as a reference. Do not mechanically inspect invisible details that cannot affect the requested output.

## Dimensions

- Overall W/D/H matches known brief.
- Knob, switch, footswitch, LED, and jack positions are plausible/known.
- Hardware diameters and enclosure proportions look correct.
- No accidental scale mismatch between imported and native objects.

## Geometry

- Exposed edges have believable bevels.
- No obvious Boolean tears or shading pinches.
- No z-fighting.
- No floating washers/nuts/screws.
- Round parts are smooth enough for target camera distance.
- Repeated fasteners/hardware are consistent.
- Seams match physical assembly.

## Pedal-specific

- Bottom plate seam is believable if visible.
- Footswitch hardware stack is plausible.
- Knob pointers/legends align.
- Input/output/power locations agree with labels.
- Rubber feet contact the ground plane if visible.

## Amp-specific

- Cabinet shell has believable depth.
- Tolex/vinyl grain scale is plausible.
- Grille is offset from baffle/cabinet appropriately.
- Handle and corner protectors sit on the cabinet rather than float.
- Control panel, knobs, jacks, and badge have convincing depth.
- Speaker/grille representation is appropriate for camera distance.

## Materials

- Coated metal is not accidentally treated as bare metallic substrate.
- Bare metal/chrome has useful reflected shapes.
- Plastic and rubber retain realistic specular response.
- Surface microtexture is subtle.
- Wood grain direction follows construction.
- Grille/tolex scale does not look miniature or oversized.

## Graphics

- Labels are sharp at final output size.
- No alpha halos.
- No mirrored text.
- Legends align with controls.
- Decals do not visibly float at grazing angles.
- Artwork does not unintentionally cross seams/hardware.

## Camera

- Product is not distorted by an overly wide lens.
- Hero angle reveals enough top/front/side information.
- Straight documentation views are actually close to square-on.
- Focus plane is correct.
- Margins are consistent for product sets.

## Lighting

- Main form reads from highlight gradients.
- Dark edges separate from background.
- Chrome and glossy hardware are not featureless black/white blobs.
- Fill does not erase form.
- Product is grounded with contact shadow.

## Render

- Noise acceptable in dark glossy regions.
- Denoising preserves text and fine texture.
- No fireflies or bright pixel artifacts.
- Transparent LED/lens areas are clean.
- No moire on grille cloth or fine repeated patterns.
- Correct final aspect ratio/resolution/background/alpha.

## Refinement contract and regression evidence

For an existing accepted asset, record the source version, requested changes and protected properties before editing. Include the latest direct feedback; a prior PASS does not override a newly reported visual defect. Start with fresh representative baseline images from that source, then inspect before changing it.

Use checks proportional to the revision. A single placement fix needs targeted coordinates and views; a broad material-only pass benefits from a serialized baseline of object transforms, source relationships, geometry, modifiers, text/font assignments, materials, cameras and lights. Hash earlier delivered files when preservation is an explicit requirement.

Distinguish source state from evaluated state:

- A mesh hash alone does not cover modifiers, UVs, material assignments, parents or instance transforms.
- A material name alone does not prove its graph, socket values, links or dependencies are unchanged.
- A camera matrix alone does not cover lens, shift, orthographic scale, DOF, render aspect or framing percentage.
- A light transform alone does not cover energy, size, color, world, exposure or color management.
- Normalize JSON representations consistently; tuple/list conversion or serialization differences can create false failures.

Test meaningful invariants with a small runnable check where scripting is available. Derive expected counts and tolerances from this product's brief, not another project's ledger. Allowlist intentional changes so a regression check does not demand that the repaired part remain identical. Read failures before weakening assertions: an incorrect clearance test and a real blocked bore require different fixes.

## Mounting and alignment evidence

| Question | Strong evidence | Insufficient alone |
|---|---|---|
| Is a control mounted on the correct axis? | Mount frame plus concentric evaluated bore, washer and bushing; square-on guides | Knob-cap center or label baseline in an oblique photo |
| Does a socket have a real opening? | Evaluated panel clearance at center and required radius; visible recessed throat | Black face disk, hidden cutter object or a single clear ray |
| Is a toggle connected? | Root/pivot overlap in source coordinates and shallow-angle render | Concentric washer/nut or front silhouette |
| Are both jacks the same part? | Shared source identity plus identical dimensions and correct mount transforms | Similar names or similar-looking renders |
| Is the head supported? | Actual top footprint and all foot contact patches, side view | Center over maximum cabinet depth |
| Is the badge centered? | Artwork bounds relative to intended grille opening, front view | Imported origin equals zero |
| Is the panel layout preserved? | Center, left/right content margins and internal spacing checked independently | Panel width or center alone |

Inspect shallow angles for detached washers, labels/dividers that hover, buried piping, blocked recesses and control stems that do not penetrate the panel. Keep raw images alongside any axis/center overlays: annotation can hide the very gap being checked. Intentional contact overlaps between assembled parts are not automatically topology defects.

For source-coordinate ray tests, transform both origin and direction into the same frame. Account for scale when interpreting hit distance; convert hit positions back to world/physical units before comparison. A termination hit behind the face proves depth only if no nearer panel or unrelated surface blocks the required opening.

## Slant, cloth transition and side-boundary diagnosis

Audit the entire dependency chain after a slant change: shell, frame, baffle apertures, speaker normals, cloth, piping, top caps, badge clearance and head support. Check the orthographic side silhouette as well as the hero; front views can hide an unchanged box or overhanging head.

For a dark line or horizontal stripe, first locate it against the geometry and texture:

1. Check duplicate/near-coincident surfaces, open gaps and cloth/frame overlap.
2. Inspect normals, smoothing islands, bevels and the exact hinge topology.
3. Check coordinate continuity, masks and any AO contribution.
4. Render the same camera/material under the established studio and a broad diagnostic source; optionally use a grazing source or simple material override.
5. Where ambiguity remains, probe evaluated cross-sections or distances on both sides of the joint.

A line changing with lighting supports a reflection/shadow explanation but does not alone prove good construction. Pair it with geometry evidence. A line staying dark is a reason to inspect further, not proof of a gap. Real closed butt joints with small bevels can legitimately form a narrow recessed shadow. Preserve them when physically plausible. A hard cloth hinge can require local tangent-continuous smoothing while a structural cabinet seam should remain. Do not remove real construction or relight the whole product to hide an upstream defect.

## Physical texture scale and material age

Equal node frequency and unit object scale do not establish equal grain size. Use identical physical footprints and comparable lighting on actual front/top/side/slanted surfaces. Distinguish density from direction and anisotropy; see [material diagnostics](../../guitar-gear-materials/references/material-diagnostics.md) for the visual patch test and optional projection audit. Check after instancing and on bevel transitions, not only on flat test planes.

For subtle aging, inspect both native hero size and useful detail size. Compare black balance between head and cabinet, fiber warmth, metal reflection bands, piping cream value, handle-cup darkness and speaker obscuration. Contact variation should follow plausible use and remain within the requested age level. Do not count random noise, brown coloration or generic edge brightening as realism.

Check the actual visible glyphs as well as string contents, particularly easily confused digits and letters. Verify thin printed rules at grazing angles and confirm that fonts/images survive file reopen.

## Honest evidence and delivery gates

A render's existence, a completed progress bar, an automatic image score or a clean static audit is not a visual pass. Open each requested final image and inspect the features it is supposed to establish. Full-sheet thumbnails help compare overall appearance; open individual pairs/crops where detail is too small to assess.

Before/after evidence should use matching camera, crop, lighting, exposure, color management and quality settings unless one of those is the deliberate subject of the comparison. When a new detail camera is added, render the prior source with that same camera in a temporary unsaved setup. Do not overwrite the prior source to obtain a baseline.

Record PASS, FAIL, NOT CHECKED or NOT APPLICABLE for applicable requirements, with a concrete measurement/image and any reference uncertainty. Do not prefill every criterion as PASS or claim that preservation establishes realism. If an early diagnosis is disproved by better crops, correct the source, report and ledger, then invalidate affected renders.

Confirm final images correspond to the final saved revision, not an earlier candidate still rendering in the background. A compact manifest can record source revision/hash, shot, dimensions, settings, output hash and inspection status. Timestamps help detect stale files but do not establish full provenance by themselves. Reopen the master and requested libraries/exports; confirm the intended scene, dependencies and instance relationships. Report meaningful approximations explicitly.

## Limits of the bundled static audit

`scripts/scene_audit.py` is a direct-scene heuristic, not an evaluated assembly or clearance validator. It enumerates `scene.objects`, so nested collection instances can hide the actual product from its mesh count and object warnings. Its dimensions are raw Blender object units despite the `dimensions_m` key; only interpret them as meters when the scene's unit convention supports that conversion. Augment it with a scoped evaluated-instance audit when necessary.

Negative scale can be intentional mirroring, `.001` can be a valid distinct asset, and open edges can be deliberate visualization construction. Confirm the visible consequence before cleanup. For export-specific checks, inspect a reimported copy; do not turn a render-ready asset into a watertight printable solid without that requirement.

## Controlled refinement decisions

Once a system is correct, lock it. The smaller the remaining defect, the narrower the next pass should be. A final polish should usually look almost identical to the accepted version at first glance; the improvement appears under inspection. Finish the product without reinterpreting its industrial design.

Use this diagnostic sequence for “looks wrong”:

1. **Silhouette wrong?** Verify envelope, slope, wedge and corner boundary; fix geometry first.
2. **Proportion wrong?** Compare direct/profile references, especially component height and seating. Do not measure height from a top photograph.
3. **Highlight wrong?** Separate topology/intersections, normals and material/light response before editing; use the [corner decision table](../../guitar-gear-modeling/references/construction-standards.md#diagnose-a-rounded-corner-before-editing).
4. **Material identity wrong?** Isolate roughness, specularity and micro-normal under the accepted rig. Check whether metal reads as silver plastic, opaque plastic as translucent brown, rubber as smooth paint, or a lens as a glowing orb.
5. **Small hardware breaks realism?** Inspect its actual stack, drive, thickness, seating and finish rather than adding decoration.
6. **Only visible in macro?** Recheck native hero pixels before changing anything. Preserve required close-up quality without damaging ordinary product views.

For an ambiguous allowed change, use A = current baseline, B = restrained change, C = stronger change. Two candidates suffice when they resolve the question; skip studies when the correction is already clear or below delivery-scale visibility. Change one variable family, record values and distinguish jointly changed parameters from isolated causal tests. Examples include molding height, insert diameter, adjuster projection, lens size, emboss relief, label scale or fastener size. Freeze camera transform/lens, lighting/world, background, exposure/color management, resolution and sampling. Select the smallest change that materially improves reference match, not the most polished-looking candidate; retain the baseline if none does.

Build readable side-by-side evidence as needed: prior/current, A/B/C, reference/current/candidate, and hero/detail pairs. Mark graphics baselines/arrow centers or hardware diameter/axis on separate copies. Do not warp model renders to fit a photograph. See [comparison-sheet guidance](../../guitar-product-render/references/studio-recipes.md#comparison-sheets-that-prove-the-change) for framing and freshness.

Use the existing [refinement contract](../../guitar-gear-modeling/templates/accepted-constraints.md) in the project brief. Define fail conditions before editing: protected silhouette/centers change, unsupported details appear, pigment or rig drifts, hardware/functional print becomes dominant, moving parts intersect, or physical material distinctions weaken. Stop when the defect is resolved, required deliverables are complete and protected systems pass; do not continue improving unrelated systems. Keep unresolved requirements explicit rather than pre-filling PASS.

## Independent footprint and motion checks

For a local repair with a locked plan shape, supplement bounds with an independent top-view boundary comparison: projected silhouette overlap or nearest-boundary distance under identical orthographic projection and scale. Bounds alone cannot detect a changed radius or shortened straight run. Record the tolerance and raster pixel scale; evaluate disconnected/projecting parts separately. Compare boundary coordinates and straight runs, plus relevant vertex/normal/UV signatures, transforms and control/pivot coordinates. Allow only the intended surface/material changes.

For moving assemblies, sample the rest pose and several positions across the expected travel. Record pose, tested object pairs, collision count or minimum separation, units and intentional seating/contact exceptions. Test stationary shell, ledges/lugs and other nearby obstructions; a rest-only render cannot establish travel clearance. Restore the rest pose afterward. Surface-intersection tests may miss complete containment, so add distance/containment checks where that failure is plausible. Discrete samples are not continuous mechanical certification.
