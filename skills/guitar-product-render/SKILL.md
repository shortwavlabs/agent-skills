---
name: guitar-product-render
description: Light, frame, preview, and render guitar pedals and amplifiers in Blender as polished commercial product photography with controlled reflections and repeatable studio setups.
---

# Guitar Product Render

Use this skill for product-camera setup, studio lighting, Cycles rendering, framing, background treatment, and iterative render refinement of guitar pedals, amplifiers, cabinets, and related gear.

Read [studio recipes](references/studio-recipes.md) for lighting patterns, fixed-rig diagnostics, two-distance testing, render freshness and comparison evidence. Read [the shot list](references/shot-list.md) to choose deliverable and QA views by the feature being tested.

## Refinement decision rules

Lock accepted systems and name the allowed changes before editing. For ambiguous visible defects, compare the baseline with restrained candidates under fixed conditions; keep the smallest change that improves reference match at delivery size. Stop when requested work is complete, delivery-preventing or visibly/dimensionally wrong issues are resolved, and protected systems pass regression checks; do not discard verified repairs or mark unfinished requirements passed to stop.

Use the [refinement contract](../guitar-gear-modeling/templates/accepted-constraints.md) for source/target versions, evidence and stop conditions. The shared [candidate and diagnosis procedure](../guitar-gear-qa/references/qa-checklist.md#controlled-refinement-decisions) owns detailed comparison rules. If using this skill alone, record facts, accepted values, uncertain estimates, allowed changes and protected properties in the existing project brief.

## When to use

Use when the user asks for a hero render, catalog image, ecommerce/product shot, studio setup, camera matching, lighting improvement, or final render settings.

Do not use this as the primary modeling or material-authoring workflow. Pair with `$guitar-gear-modeling`, `$guitar-gear-materials`, and `$guitar-gear-qa`.

## Rendering principles

1. **Reflections define product form.** Place large sources intentionally so bevels, chrome, painted surfaces, and plastics reveal their shape.
2. **Use realistic perspective.** Product shots usually benefit from moderate-to-long focal lengths instead of dramatic wide angle.
3. **Start simple.** One key, one fill/bounce, and one edge/background control can outperform a cluttered light rig.
4. **Preview early.** Render small/low-sample tests before expensive finals.
5. **Judge the actual deliverable.** A technically correct scene is not finished if labels are unreadable, highlights are clipped, or the silhouette is weak.

## MCP discipline

- Inspect the current camera, lighting, render engine, and color-management state before replacing them.
- Discover Blender MCP render/view operations dynamically.
- Change one major lighting variable at a time when diagnosing an image.
- Retrieve and inspect preview renders after meaningful changes.
- Do not launch a costly final render until a lower-cost preview has passed composition and material checks.

## Accepted-scene refinement

- Preserve accepted product cameras, lights, world, exposure and color management unless the current request calls for changes. Keep temporary diagnostic setups out of delivered lighting.
- Use a matched baseline to isolate a revision. Match resolution and sampling as well as framing; a cleaner render can otherwise masquerade as better materials.
- Preview composition cheaply, then check vulnerable details at final pixel scale before the full batch. Inspect the native hero crop as well as a separate macro.
- Use a true side view for slant and support, a square-on panel for layout, and a shallow angle for mechanical seating.
- Track final-source provenance and inspect each final output. Superseded renders and stale comparison sheets must be replaced after a source correction.

## Camera procedure

1. Establish the target shot: ecommerce, hero 3/4, front panel, rear panel, macro/detail, or contextual.
2. Start around a moderate-to-long focal length for product work; adjust distance to frame rather than moving immediately to a wide lens.
3. Keep verticals and product geometry visually stable unless a stylized perspective is requested.
4. Use depth of field sparingly for product documentation; use it more deliberately for advertising hero shots.
5. Check that important controls and labels remain legible at final output size.

## Lighting procedure

1. Start with a large area-light key positioned to create a readable highlight gradient across the main enclosure/cabinet.
2. Add a weaker fill or large white-card equivalent to control contrast without flattening the object.
3. Add a rim/edge source only when it improves separation or reveals dark edges.
4. Shape chrome and glossy hardware with bright reflected cards/area lights rather than trying to brighten the material itself.
5. Use background lighting independently when practical.
6. For black products, prioritize edge separation and reflected gradients rather than simply increasing exposure.

## Render procedure

1. Prefer Cycles for final photoreal product work unless the user explicitly chooses another engine.
2. Use GPU rendering when available and stable in the user's environment.
3. For previews, reduce resolution and samples aggressively enough to iterate quickly.
4. Use adaptive sampling/denoising when it improves efficiency without destroying small labels, brushed-metal texture, grille cloth, or fine highlights.
5. Render a representative preview at the target camera before increasing quality.
6. Inspect noise in dark areas, chrome, transparent LED lenses, contact shadows, and fine cloth/text.
7. Increase samples only where the image shows a problem; do not treat a huge sample count as a substitute for good lighting.

## Background and grounding

- Use a neutral sweep/cyclorama for commercial studio images unless another style is requested.
- Keep a real or shadow-catching ground relationship so the product does not float.
- For transparent-background delivery, preserve enough contact/shadow information if the compositor/output format supports the intended use.
- Avoid distracting horizon lines unless compositionally intentional.

## Composition defaults

For pedals:

- Hero 3/4 slightly above the top face so controls and enclosure depth are both readable.
- Near-front view for label/control documentation.
- Rear/side detail when jacks or power connections matter.

For amps:

- 3/4 hero showing front and cabinet depth.
- Straight-ish front view for control/grille readability.
- Rear view for I/O and cabinet construction.
- Detail shots for knobs, grille, badge, tolex, handle, tubes, or hardware as needed.

## Efficiency plan

- Lock modeling and major materials before polishing lights.
- Use one preview camera and one hero camera unless multiple deliverables are required.
- Iterate at reduced resolution.
- Diagnose lighting with simple clay/material overrides only when material complexity obscures form.
- Stop refining invisible micro-noise once the target output size is clean.

## Common failure modes

- **Metal/chrome looks dead:** lighting has no useful bright shapes to reflect.
- **Black pedal disappears:** add edge/reflection separation rather than washing the whole image with fill.
- **Pedal looks distorted:** focal length is too wide or the camera is too close.
- **Everything looks flat:** key and fill are too similar in size/intensity/direction.
- **Highlights clip:** reduce source intensity/exposure or reposition reflection before dulling all materials.
- **Render is clean but fake:** contact shadow, bevel reflections, and material scale may be missing.
- **Fine text gets mushy:** denoising or resolution is too aggressive; improve sampling or render size.

## Verification checklist

Before final render:

- Composition is approved at preview resolution.
- Product proportions are not distorted by the lens.
- Important labels and controls are legible.
- Bevel highlights describe the shape.
- Chrome/metal/plastic materials show believable reflections.
- Black regions retain separation and detail.
- Contact shadow/grounding is convincing.
- No major clipping, fireflies, or distracting noise remains.
- Final resolution, aspect ratio, file format, alpha/background, and color expectations match the request.
