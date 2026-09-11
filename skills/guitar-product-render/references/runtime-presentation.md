# Runtime camera and lighting translation

Use when an accepted Blender guitar-gear product scene becomes an interactive WebGL editor. Preserve the original studio rig; create runtime presets and lighting in the derivative/viewer. Read [runtime QA](../../guitar-gear-qa/references/runtime-qa.md) for matched comparisons.

## Camera presets

Derive useful presets such as Front, Front 3/4, Rear and Controls from existing hero/detail cameras. Add side or macro presets only when the product needs them; pedals and rack units may need different names/counts. Record evaluated camera position, view target, up vector, perspective vertical FOV (or orthographic bounds), near/far planes, target aspect, orbit distance/polar/azimuth limits and allowed zoom. Resolve Blender tracking constraints/rigs to evaluated transforms; do not expect the rig itself to transfer.

Store presets as JSON/TypeScript when that is clearer than exporting cameras. Convert camera position, target and up into the same glTF/root coordinate frame as the model, accounting for exporter axis conversion and any runtime root transform. Avoid applying that conversion twice. Derive vertical FOV from evaluated projection and sensor fit/aspect, not a blind copy of focal length or horizontal FOV. Preserve lens shift with an equivalent projection only when needed; otherwise document and visually approve the approximation.

Match editor aspect ratio, product screen size and margins first. Recompute projection on resize. Keep controls readable at both minimum editor size and intended maximum zoom; limit orbit so controls remain usable and the camera cannot enter the enclosure. Test each preset with front-panel text, jack mouths, head/cabinet boundaries and grounding visible. Retain orthographic documentation views where appropriate rather than silently turning them into perspective.

## Translate studio intent

Blender area lights, Cycles shaders, shadow catchers and compositing do not automatically become equivalent glTF lighting. Recreate the useful broad key/fill/rim reflection shapes with a locally packaged environment and a small runtime light rig. Use filtered environment lighting for PBR metals; a black environment makes chrome black regardless of the source material's quality.

For dark amps, preserve black-surface separation, highlight gradients, grille readability and metal reflections without washing the cabinet gray. Use a simple ground/contact treatment if needed. Real-time shadows, transmissive lenses, bloom and other postprocessing are optional costs to justify at actual plugin size.

A meaningful rear view may need a separately authored neutral environment/reflection treatment when the front presentation rig leaves the recess unreadable. Switch presentation lighting with the camera preset, not by changing material values, and compare both views against their accepted Blender references. Keep the transition deterministic and per viewer.

Record runtime tone mapping, exposure, output color space, environment and shadow settings. Blender AgX/Cycles and WebGL output are not guaranteed pixel-identical; approve perceptual material identity and composition using matched framing. Keep runtime lighting fixed while comparing material candidates. Inspect native editor size plus intended detail zoom, especially labels, cloth, black levels and chrome. Do not compensate for a failed material bake by hiding the defect in a darker runtime scene.
