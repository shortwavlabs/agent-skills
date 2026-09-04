---
name: guitar-gear-modeling
description: Model guitar pedals, amplifiers, cabinets, controls, and hardware in Blender with real dimensions, clean hard-surface construction, reusable parts, and inspection-driven iteration.
---

# Guitar Gear Modeling

Use this skill for dimensionally grounded Blender modeling of guitar pedals, amplifiers, speaker cabinets, rack gear, footswitches, knobs, jacks, switches, handles, corners, vents, fasteners, and related product hardware.

Read `references/construction-standards.md` before substantial modeling. Read `references/component-library.md` when creating repeated hardware. Use `templates/product-brief.md` when the request lacks a compact specification.

## When to use

Use when the user asks to create, revise, rebuild, dimension, or clean up physical guitar gear in Blender.

Do not use this skill as the primary workflow for materials, studio lighting, final rendering, or final QA. Hand those phases to `$guitar-gear-materials`, `$guitar-product-render`, and `$guitar-gear-qa`.

## Inputs to gather

Before editing the scene, gather the smallest useful set of facts:

- Product type and target dimensions.
- Reference images and which views are authoritative.
- Known component sizes or datasheets.
- Whether the goal is exact reproduction, plausible concept, or stylized product.
- Which parts must remain editable or reusable.
- Required output views or render framing.

If dimensions are incomplete, infer only low-risk secondary dimensions from visual proportions. Mark inferred dimensions in the work summary. Never silently invent critical mounting dimensions for an exact-reproduction request.

## Blender and MCP discipline

1. Inspect the current scene before changing it.
2. Discover the Blender MCP operations available in the session instead of assuming tool names.
3. Prefer small, reversible edits and non-destructive modifiers.
4. After each major modeling phase, inspect at least one useful viewport/image result before continuing.
5. Do not run large opaque Python programs when direct Blender/MCP operations are sufficient.
6. When Python execution is the best route, make the script idempotent when practical and scope it to named objects/collections.
7. Save or checkpoint before broad destructive operations when the available MCP supports it.

## Coordinate and unit conventions

- Use Metric units.
- Keep scene unit scale at normal metric scale unless an existing project intentionally differs.
- Enter real product dimensions using explicit units such as `125 mm` or `430 mm`.
- Treat Z as up unless the existing project uses another established convention.
- Apply object scale before bevel-sensitive or manufacturing-like operations unless there is a deliberate reason not to.

## Modeling procedure

1. **Establish the envelope.** Create a simple blockout at the real overall dimensions. Verify width, depth, and height before adding detail.
2. **Split real assemblies.** Keep enclosure, base plate, knobs, switches, jacks, fasteners, handles, feet, grille, and other manufactured parts as separate semantic objects when they are separate physical parts.
3. **Build primary forms.** Use simple meshes, bevels, mirror, array, solidify, and booleans before manual topology work.
4. **Add openings non-destructively.** Use Boolean cutters for jack holes, footswitch holes, vents, speaker apertures, screw recesses, panel cutouts, and handle openings. Keep cutters organized until the design is stable.
5. **Add edge behavior.** Real products almost never have mathematically sharp exposed edges. Use physically plausible bevels sized to the part.
6. **Build one good component.** Model one knob, screw, footswitch, jack nut, corner protector, or vent pattern correctly, then duplicate or instance it.
7. **Model only visible complexity.** Internal threads, hidden electronics, and invisible construction are unnecessary unless requested or visible in the deliverable.
8. **Inspect silhouettes and spacing.** Check front, rear, side, top, and 3/4 views for proportion errors before adding micro-detail.
9. **Prepare for materials.** Keep logical material regions separable and avoid needless mesh joining that will complicate assignment or UV work.
10. **Report assumptions.** Summarize exact dimensions, inferred dimensions, omitted hidden details, and reusable components created.

## Hard-surface rules

- Prefer modifier-based Boolean + Bevel workflows for enclosures and chassis.
- Avoid giant all-in-one meshes when the real product is assembled from parts.
- Use weighted/custom normals only when they visibly solve shading problems; do not add them reflexively.
- N-gons are acceptable on flat, non-deforming hard-surface regions when shading is clean and downstream operations remain stable.
- Prevent coplanar surfaces and z-fighting.
- Do not fake circular hardware with visibly faceted low-segment geometry in hero shots.
- Keep bevel width proportional to the real object. A pedal enclosure edge and a thin washer should not share the same bevel.

## Naming and organization

Prefer semantic names over Blender defaults. Examples:

```text
GG_PEDAL_Enclosure
GG_PEDAL_BottomPlate
GG_HW_Footswitch_01
GG_HW_Knob_Gain
GG_HW_Jack_Input
GG_HW_Screw_M3_01
GG_CUT_Footswitch
GG_CUT_Jack_Input
```

Use collections such as:

```text
GG_PRODUCT
GG_HARDWARE
GG_CUTTERS
GG_GRAPHICS
GG_LIGHTING
GG_CAMERAS
```

Do not rename a well-organized existing project merely to match this convention.

## Efficiency plan

- Block out the full product before detail.
- Reuse components aggressively.
- Batch repeated holes with arrays, linked duplicates, or shared cutter patterns.
- Inspect after primary forms, after openings/hardware, and after final bevels instead of after every tiny edit.
- Stop adding geometry when remaining differences will not affect the requested render distance.

## Common failure modes

- **Pedal looks toy-like:** bevels are too large, hardware is oversized, or the enclosure proportions are wrong.
- **Product looks CG-sharp:** exposed edges have no realistic bevel.
- **Boolean shading artifacts:** apply scale, simplify cutter topology, improve modifier order, or isolate the cut from an edge.
- **Knobs look faceted:** increase radial segments or improve shading before adding more materials.
- **Amp front looks flat:** separate grille, baffle, piping, panel, hardware, and cabinet depth instead of relying on textures alone.
- **Scene becomes fragile:** too many applied booleans or duplicated unique components; restore non-destructive structure and shared assets.

## Verification checklist

Before handing off to materials:

- Overall dimensions match the brief.
- Critical controls and openings are in plausible/known positions.
- Exposed edges have appropriate bevels.
- No obvious z-fighting or accidental intersections are visible.
- Repeated hardware is consistent.
- Objects have meaningful names or preserve an existing coherent convention.
- Front, rear, side, top, and 3/4 inspection views look proportionally correct.
- Material regions are practical to assign.
- Any inferred dimensions are documented.
