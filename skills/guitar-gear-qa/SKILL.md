---
name: guitar-gear-qa
description: Audit Blender guitar-gear scenes for dimensional, geometric, shading, material, camera, lighting, naming, and render issues before final delivery, then fix only high-confidence problems.
---

# Guitar Gear QA

Use this skill as the final audit for guitar pedal, amplifier, cabinet, and related Blender product scenes.

Read [the QA checklist](references/qa-checklist.md) for the inspection matrix, mounting tests, boundary diagnosis, preservation evidence and delivery gates. `scripts/scene_audit.py` is an optional direct-scene heuristic; it does not validate nested evaluated assemblies, physical clearances or visual quality.

## Refinement decision rules

Lock accepted systems and name the allowed changes before editing. For ambiguous visible defects, compare the baseline with restrained candidates under fixed conditions; keep the smallest change that improves reference match at delivery size. Stop when requested work is complete, delivery-preventing or visibly/dimensionally wrong issues are resolved, and protected systems pass regression checks; do not discard verified repairs or mark unfinished requirements passed to stop.

Use the [refinement contract](../guitar-gear-modeling/templates/accepted-constraints.md) for source/target versions, evidence and stop conditions. The shared [candidate and diagnosis procedure](references/qa-checklist.md#controlled-refinement-decisions) owns detailed comparison rules. If using this skill alone, record facts, accepted values, uncertain estimates, allowed changes and protected properties in the existing project brief.

## When to use

Use before final render/delivery, after major modeling revisions, or when the user asks why a product render still looks wrong.

This skill is inspection-first. Do not rebuild large parts of the scene simply because a different modeling approach would be cleaner.

## Revision and evidence rules

- Establish the latest request, accepted baseline and protected properties before editing. Treat new user feedback as a reason to recheck the relevant claim.
- Fix source-level causes: shared hardware geometry, mount/bore registration, cloth normals or actual support placement. Do not hide a defect with framing, dark material or lighting.
- Compare measurements with rendered evidence. Check both hero and useful detail distances, and inspect every requested final image before marking it passed.
- Verify evaluated instances when the product uses collection instances; source counts and empty bounds are insufficient.
- Record PASS, FAIL, NOT CHECKED or NOT APPLICABLE with evidence for relevant requirements. Preservation is not proof of realism, and a saved render is not proof it was inspected.
- Confirm outputs come from the final saved revision; reopen requested master/library/export files and preserve prior versions where required.

## Severity model

Classify findings as:

- **Blocker:** prevents the requested deliverable or produces clearly incorrect output.
- **High:** visually or dimensionally wrong in the target render.
- **Medium:** noticeable quality issue with a safe fix.
- **Low:** polish or maintainability issue that may not affect the requested image.
- **Info:** assumption, limitation, or observation only.

Fix Blocker/High findings when the correction is high-confidence and within scope. Fix Medium findings when low-risk. Report Low/Info rather than churning the scene.

## MCP discipline

1. Inspect before modifying.
2. Discover the Blender MCP tools actually available.
3. Prefer viewport/render evidence over guessing from object names alone.
4. Make fixes in small groups and re-inspect after each group.
5. Do not execute broad cleanup scripts that rename, join, delete, or apply modifiers across the whole scene without explicit justification.
6. Use `scripts/scene_audit.py` only as supporting evidence; its warnings are not automatically errors.

## Audit procedure

### 1. Product brief and dimensions

- Confirm overall dimensions against the known brief.
- Verify important component sizes/positions when known.
- Identify which dimensions were inferred.
- Look for accidental global scaling.

### 2. Geometry

Inspect hero-visible areas for:

- Missing or oversized bevels.
- Boolean artifacts.
- Accidental intersections.
- Coplanar/z-fighting surfaces.
- Faceted circular parts.
- Impossible clearances.
- Floating hardware.
- Wrong panel seams.
- Inconsistent repeated hardware.

### 3. Shading and normals

Check:

- Hard-surface shading continuity.
- Unexpected dark patches.
- Negative scale or transform issues contributing to normals problems.
- Over-smoothed sharp features.
- Bevel modifier ordering/width issues.

### 4. Materials and graphics

Check:

- Correct physical material classification.
- Plausible roughness/reflection response.
- Texture scale.
- Repeated material consistency.
- Label sharpness and alignment.
- Decal haloing/floating.
- LED lens/emission behavior.

### 5. Camera and composition

Check:

- Perspective distortion.
- Cropping/margins.
- Product leveling where appropriate.
- Label/control readability.
- Depth-of-field focus.
- Consistency across multi-shot sets.

### 6. Lighting

Check:

- Shape-defining highlight gradients.
- Separation on black surfaces.
- Useful reflections on chrome/metal.
- Clipped highlights.
- Flat fill.
- Distracting reflection shapes.
- Grounding/contact shadow.

### 7. Render quality

Inspect a representative preview/final-sized crop for:

- Noise in dark glossy areas.
- Denoising damage to text or fine texture.
- Fireflies.
- Aliasing on labels and grille cloth.
- Transparency artifacts.
- Moire.
- Background banding or unwanted horizon lines.

### 8. Scene hygiene

Check only issues that affect repeatability or delivery:

- Default-style `.001` names on important assets.
- Duplicate unused materials when obvious.
- Missing active camera.
- Hidden temporary cutters leaking into renders.
- Accidental render-enabled helpers.
- Unintended objects outside the product frame.

Do not perform mass cleanup for cosmetic organization alone unless requested.

## Optional static audit script

If Blender Python execution is available, run `scripts/scene_audit.py` inside Blender. Capture the printed JSON report and use it to guide inspection.

The script intentionally reports warnings rather than making changes. A warning must be confirmed visually or against the product brief before editing.

## Fix policy

Apply fixes in this order:

1. Wrong dimensions or catastrophic transforms.
2. Visible geometry/shading artifacts.
3. Material/graphics problems.
4. Camera/composition.
5. Lighting.
6. Sampling/noise.
7. Low-value scene hygiene.

Avoid compensating downstream for upstream errors. For example, do not use lighting to hide broken shading if the bevel/normal problem is safe to fix.

## Efficiency plan

- Begin with the requested final camera, not exhaustive hidden-surface inspection.
- Check front/side/back only when relevant to the deliverable.
- Use the static script once, then rely on visual evidence.
- Batch closely related safe fixes.
- Stop when the requested output is clean and remaining issues are not visible or not in scope.

## Final report format

Return a concise report with:

```text
QA result: PASS / PASS WITH NOTES / NEEDS FIXES

Fixed:
- ...

Remaining:
- [severity] ...

Assumptions:
- ...

Final render readiness:
- ...
```

Do not claim PASS without inspecting a representative rendered or material-preview image when rendering is part of the requested deliverable.
