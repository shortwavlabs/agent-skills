# Blender execution, instances and delivery

Use this reference when scripting, using a live Blender connection, saving libraries, or exporting a product built from nested instances. These are observed workflow pitfalls, not guarantees about every Blender version or MCP implementation.

## Choose a reproducible execution path

Inspect the actual Blender executable/version, available MCP operations, loaded file, scene and view layer. If an inspector cannot locate Blender, supply the discovered executable path where supported; do not assume it is on PATH or hard-code another machine's app location.

Use live tools for small inspection/edits and deterministic Blender Python for repeatable construction or render batches. Keep reusable construction helpers in normal modules with explicit inputs; do not splice helper definitions from another script by string offsets. Scripts should start from a known source file or safely reuse named data so reruns do not accumulate objects, material copies or additive transforms.

For a background script, arrange CLI arguments so the intended file loads before the script runs, and use a nonzero Python error exit code where supported. Import modules used by command-line parsing explicitly. Verify a short setup/save or single preview before launching the whole batch. A successful process exit and a saved PNG are necessary evidence, but neither proves visual correctness.

## Context and file reloads

Opening another .blend replaces datablocks and can invalidate cached object, collection, scene and node references. Reacquire them by stable semantic identity after loading. A live MCP callback can temporarily lack `bpy.context.window`; do not assume a foreground window remains bound after a file-open call. Complete the load, then inspect the available window-manager windows in a subsequent call and select the intended scene/window when one exists. In a truly windowless context, use data operations and an appropriate explicit context rather than indexing a nonexistent window.

Before context-sensitive operators, set the intended scene, view layer, active object, selection and mode, or use a valid context override. Inspect the operator's required context instead of retrying the identical failing call. After transforms/modifiers, update the dependency graph before reading evaluated bounds or raycasting. Return only serializable primitives from MCP Python results; convert vectors, matrices and datablock identities deliberately.

If a screenshot tool fails, use the supported viewport capture or render to a known local image and inspect it. Do not claim that a viewport was checked when only a data query succeeded. If a render call times out or a response is uncertain, inspect process/log/output status before launching another copy. Restrict termination to a known task-owned process when superseding a render.

## Nested instances and geometry evidence

A scene can contain only a few collection-instance empties while rendering hundreds of parts. `scene.objects`, source mesh counts and empty bounds do not measure the assembled product. Inspect the intended scene/view layer's evaluated object instances, retain each instance transform, and transform evaluated vertices or bounding corners into world space. Filter the actual product deliberately, excluding studio, reference and diagnostic objects. Report enclosure bounds separately from hardware-inclusive bounds.

Compare the visible assembly count with semantic source relationships: several knobs should share a source while producing several evaluated instances. Two occurrences of the same source at different transforms are not duplicates to delete.

Some evaluated pipelines expose both curve/text entries and mesh representations of the same contribution. Inspect original identity, evaluated type, instance path/persistent identity and transform before realizing geometry. Avoid both double-converting one label and dropping legitimate repeated labels. A version-specific mesh-only filter worked in one pipeline; it is not a universal export rule. Verify counts and appearance after conversion. Release temporary evaluated meshes where the API requires it.

## Standalone files and libraries

An appendable datablock library and an independently openable product project are different deliverables. Write the appropriate scenes, source collections and dependencies, reopen the saved file, select its intended scene/view layer/camera, and save a useful opening state where needed. Verify that source collections remain available to instances and that the display grid does not duplicate the actual assembly in renders.

Pack or deliberately resolve fonts, images and other external assets. Check the component library as well as the master: a successful master render cannot prove that a separately saved library contains the revised source. Preserve requested prior versions; do not overwrite a known-good source while testing a candidate.

## Export only when required

Keep the authored .blend authoritative for procedural material fidelity. An interchange format may not represent procedural coordinates, mixed cloth shaders or custom node groups. Bake supported textures when visual equivalence is required, or explicitly label a base-PBR/geometry-only export and inspect it. A white grille after export is a material translation defect, not proof the source shader was wrong.

Realize/triangulate and clean an export copy rather than modifying accepted authored geometry. Use scale-aware tolerances for negligible welds, zero-length edges and sliver triangles. Do not globally fill every boundary: cloth, open cups, cones and flat graphics may intentionally be open in a visualization asset. Printability is a separate requirement.

Reimport the export into a fresh scene and compare assembled bounds, part count, material coverage, finite coordinates and representative views. Account for legitimate triangulation differences rather than requiring identical triangle counts blindly. Export optimization is not a substitute for improving the requested beauty renders.
