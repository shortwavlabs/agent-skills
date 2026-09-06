# Studio Lighting Recipes for Guitar Gear

These are starting patterns. Adjust size, distance, angle, and strength to the object's dimensions and material response.

## Recipe A: Clean ecommerce pedal

Goal: readable shape, accurate color, minimal drama.

- Large soft key above/front-left or front-right.
- Broad soft fill from the opposite side at lower intensity.
- Neutral sweep background.
- Optional top/back strip or area light for dark-edge separation.
- Moderate-to-long lens and restrained depth of field.

Use enough contrast to show bevels and knobs without making the face graphic hard to read.

## Recipe B: Premium pedal hero

Goal: stronger form and material appeal.

- Large key positioned to create a long highlight gradient across the enclosure.
- Controlled darker side for shape.
- Narrower rim/strip source to catch chrome footswitch, knob edges, or enclosure edge.
- Background gradient or separate background light.
- Slightly lower camera angle than ecommerce, but still readable from above.

Do not make every metal edge equally bright.

## Recipe C: Black amp / dark cabinet

Goal: reveal a dark object without flattening it.

- Large lateral key for a broad side reflection.
- Top/back light to outline cabinet shoulders/handle.
- Soft frontal fill just strong enough to reveal grille/control labels.
- Keep the background distinct enough from black to preserve silhouette.

Use reflected bright cards/large sources to shape black vinyl and chrome rather than relying on exposure alone.

## Recipe D: Front-panel documentation

Goal: readable controls and typography.

- Camera nearly square to panel.
- Large frontal/overhead source, offset enough to reveal knob volume.
- Gentle side fill.
- Minimal depth of field.
- Keep reflections away from critical text.

## Reflection debugging

If a glossy surface looks wrong, temporarily move or enlarge the area light instead of changing the material. Product materials are often easier to judge when the scene provides clean reflected shapes.

## Preserve an accepted rig during refinement

Record camera, light, world, exposure, color-management and render settings before a material or geometry pass. Keep these fixed unless the brief allows changing them or a demonstrated failure requires it. Add separate QA cameras rather than silently reframing accepted product views. Temporary diagnostic lights should live in an unsaved/copy scene or be restored before delivery; verify they do not leak into the final file.

For a black amp that reads gray, identify whether the problem is base reflectance, specular response or too much world/fill illumination. Adjust one family at a time when relighting is allowed. Maintain correctly exposed metal and control graphics; global exposure reduction can conceal the symptom while damaging the rest of the product. Once a rig is accepted, do not move it merely to make a tiny material edit look more dramatic.

Hardware needs shaped reflections, but uniformly bright white caps can look plastic. Use broad controlled bands with darker regions between them. Very small intense sources can exaggerate steep vinyl bump into glitter. Diagnose source size/angle and bump/roughness separately rather than automatically adding samples or roughening every surface.

## Boundary and texture diagnostic setups

**Boundary test:** lock camera and material; render the existing studio, then a broad frontal/lateral source, and optionally a grazing source. Compare whether the same seam/cloth hinge changes reflection naturally. Combine this with normals and geometry evidence; lighting response alone cannot certify that the assembly is closed. Keep a legitimate narrow bevel shadow if it matches construction.

**Physical-scale test:** place orthographic cameras perpendicular to equal-size clear patches on actual wrapped surfaces. Use identical patch footprint, output pixels, and a light positioned relative to each local surface frame with equal size, distance and power. Avoid cropping a handle instead of the covering. Label the physical width, surface and revision. These images diagnose scale; they do not replace appearance checks under the final studio rig.

**Evaluation order:** native hero pixels → standard product view → detail → macro. Hero-scale plausibility has priority; impressive microgeometry can worsen the delivered image. Inspect an unresized crop of the final hero first, then the whole product and a relevant detail view. For weave, add a medium-distance sample when needed to reveal interference. A macro may expose manufacturing cues but can hide the fact that the same signal creates noisy stripes in the hero. Use an unresized crop from the actual hero to assess tiny jack mouths or glyphs; a separate zoomed camera cannot prove delivery-scale readability.

## Sampling and full-resolution surprises

Low-resolution previews approve framing and broad material direction. They cannot approve fine weave, tiny printed text, narrow metal rims or denoising behavior. Before rendering a large set, test a representative crop at the final camera's actual pixel scale and comparable final sampling. Inspect bright micro-highlights and dark recesses, not only a smooth background.

Cycles with AgX, denoising and adaptive sampling is a useful product-work combination when available; a moderate budget around 128 samples can be a starting experiment, not a universal requirement. Keep the project's accepted settings for comparisons. Raise quality only when a visible failure warrants it. Changes in resolution, sample budget, denoising or exposure can otherwise masquerade as material improvements.

If full-resolution cloth reveals banding missed in a preview, revisit yarn contrast, relative directional scales, distortion, filtering and geometry. Do not accept the entire batch solely because its first preview passed. Stop or supersede only the known obsolete job, repair the cause, and rerender every affected shot.

## Render jobs and file freshness

Use an explicit shot list with scene, camera, output path, dimensions and preview/final settings. Separate baseline, preview, diagnostic and final output locations. Log long background renders and check their actual status after a tool timeout before starting a duplicate. Ensure Python failures return a failing exit status where supported.

A multi-scene driver must select the scene and its camera for each shot; a previous scene's active camera can otherwise produce valid files of the wrong product. Save the deliverable with final settings and a useful scene/camera active, rather than the last temporary macro or library grid. Reopening a .blend can require reacquiring the live window/context; use the modeling skill's Blender-operations reference when relevant.

Validate output count, dimensions, format and source revision before delivery. Open each final image. If a source change occurred during a batch, determine exactly which outputs are stale and replace them; do not mix candidate revisions under final filenames. Rebuild comparison sheets after the replacement renders finish.

## Comparison sheets that prove the change

Use two distinct comparisons when relevant:

- Matched prior/current views isolate the edit under consistent conditions.
- Original-photo/current crops assess reference fidelity and the intended age level.

Keep references identifiable and preserve aspect ratio; do not stretch photographs to force agreement. Use equivalent features and comparable scale where the source allows it, but label photo-derived dimensions as inferred. A corner crop should actually show the cap; a piping crop should include the relevant run and corner; a weave crop should avoid hiding the fabric under a badge. Open the composite and inspect individual pairs at a readable size.

Contact sheets are useful for overall consistency, not microscopic proof. Preserve individual final files and raw QA views; place measurement guides on separate annotated copies. Do not use synthesized texture images as evidence of what the Blender scene rendered. Aggregate image differences can support a claim of restrained overall change but cannot establish correct geometry, centering or material realism.

A coincident floor and sweep can create a visible band or shadow artifact. Inspect the stage geometry before changing material or exposure. Keep one coherent grounding surface and verify caster/foot contact from the useful side and hero views.
