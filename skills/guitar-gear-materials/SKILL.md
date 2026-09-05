---
name: guitar-gear-materials
description: Create and apply physically plausible Blender materials for guitar pedals and amps, including powder coat, metal, plastic, rubber, tolex, grille cloth, wood, LEDs, and printed graphics.
---

# Guitar Gear Materials

Use this skill to create, tune, organize, and apply materials for guitar pedals, amplifiers, cabinets, and associated hardware.

Read only the references needed for the task:

- [Material recipes](references/material-recipes.md): basic response ranges for coatings, metal, plastic, rubber, lenses and other common materials.
- [Amplifier surfaces](references/amplifier-surfaces.md): vinyl grain, cloth, vintage hardware, cups, sockets and piping when those surfaces are involved.
- [Material diagnostics](references/material-diagnostics.md): unexpected black levels, sparkle or physical-scale mismatches. The visual patch test is primary; anisotropic math is an advanced optional fallback.
- [Graphics and decals](references/graphics-and-decals.md): logos, centering, flush printing and glyph verification.

## Refinement decision rules

**Stop rule:** once the requested work is complete and all Blocker/High issues (delivery-preventing or visibly/dimensionally wrong results) are resolved, stop discretionary iteration when remaining changes lack reference support or a candidate does not materially improve the relevant hero/detail views. Retain the accepted baseline for that candidate, including already verified repairs. Do not undo useful fixes or mark unresolved requirements as passed merely to stop.

**Accepted constraints:** keep a compact ledger of AUTHORITATIVE USER FACTS, LOCKED / ACCEPTED, PHOTO-INFERRED / UNCERTAIN, ALLOWED TO CHANGE THIS PASS, and PROTECTED FROM REGRESSION. Record source/evidence and superseded decisions; update it when the user changes direction. The modeling skill provides a [copyable ledger](../guitar-gear-modeling/templates/accepted-constraints.md) when working with the pack; the five categories above are sufficient when using this skill alone.

**Candidate testing:** when one uncertain, allowed-to-change scalar or design parameter dominates a visible mismatch, render 2–3 isolated variants under identical conditions before committing. Include the baseline, vary only that parameter, compare relevant hero/detail views and reject regressions. Prefer the smallest variant set that can distinguish the decision; do not generate variants when the expected visual difference is below delivery-scale visibility. This applies to dimensions, bevels, grain/weave contrast, logo scale or other focused choices; do not reopen accepted parameters or run a variant sweep when the correction is already clear.

## When to use

Use for material creation, PBR texture setup, procedural surface variation, UV/image textures, decals, printed labels, LEDs/lenses, and reusable material libraries.

Do not use this as the primary modeling or lighting workflow. Pair with `$guitar-gear-modeling` and `$guitar-product-render`.

## Core principles

1. **Material identity comes from reflection first.** Roughness, metallic response, normals, and lighting matter more than decorative noise.
2. **Keep texture scale physically believable.** A 1 mm powder-coat texture should not appear as 20 mm bumps.
3. **Use subtle variation.** Real product surfaces are imperfect, but product renders should not look dirty unless requested.
4. **Separate geometry from graphics intentionally.** Printed ink, engraved marks, embossed logos, and physical badges should not all be solved the same way.
5. **Prefer reusable node groups/materials.** Guitar gear repeats the same families of metal, plastic, rubber, vinyl, fabric, and wood.

## MCP discipline

- Inspect existing materials and node trees before replacing them.
- Discover available Blender MCP node/material operations instead of assuming a particular API.
- Make one material family at a time and inspect a rendered/material-preview result before proliferating it.
- Avoid opaque large Python scripts when direct node operations are available.
- Do not delete existing custom materials unless the user asked for replacement or they are clearly throwaway placeholders.

## Material procedure

1. **Identify the physical material.** Ask what the object is made of, not merely what color it is.
2. **Set base response.** Establish Base Color, Metallic, Roughness, IOR/transmission where relevant.
3. **Add micro-surface detail.** Use restrained bump/normal/roughness variation at real-world scale.
4. **Add manufacturing cues.** Brushing direction, powder-coat orange peel, molded plastic texture, vinyl grain, cloth weave, or wood grain only where physically appropriate.
5. **Handle edge realism through geometry.** Do not try to simulate missing bevels with materials.
6. **Add graphics.** Choose UV/image, decal, geometry, or text based on permanence, relief, and viewing distance.
7. **Inspect under product lighting.** A material is not approved from a flat shader ball alone; inspect it on the actual product under representative reflections.
8. **Save reusable materials.** Use stable semantic names and avoid duplicate `.001` variants when the material is genuinely shared.

## Refinement gates

- Preserve accepted base materials, geometry and presentation; reuse existing variation layers before adding new ones. Isolate treatments that should not affect every shared metal/plastic part.
- Audit physical grain density on equal-world-size surface patches. Identical node values and unit object scales are insufficient for anisotropic 3D mapping. Keep density distinct from wrap orientation.
- Diagnose a stripe or seam through geometry, normals, coordinates and temporary lighting before altering the shader. A real beveled construction joint may remain dark.
- Use manufacturing and handling cues appropriate to the requested age. Well-maintained vintage gear need not have grunge, bright edge wear, brown cloth or damaged trim.
- Judge each meaningful change at native hero size and relevant detail distance. Full-resolution weave and small text can fail despite a clean preview.

## Naming convention

Prefer names such as:

```text
GG_MAT_PowderCoat_Black_Satin
GG_MAT_Aluminum_Brushed
GG_MAT_Chrome
GG_MAT_ABS_Black
GG_MAT_Rubber_Black
GG_MAT_Tolex_Black
GG_MAT_GrilleCloth_SaltPepper
GG_MAT_LED_Green
GG_MAT_Ink_White
```

Preserve an existing coherent project convention rather than renaming everything.

## Texture and node rules

- Use explicit Mapping/Texture Coordinate control for scale-sensitive procedurals.
- Avoid using the same procedural noise scale for bump, roughness, and color without purpose.
- Route normal maps through a Normal Map node and set image color space correctly when working manually.
- Treat roughness/metallic/normal/displacement maps as non-color data.
- Keep displacement subtle and use it only when the render method and mesh density support it.
- Prefer bump for microtexture and geometry for silhouette-changing detail.
- Do not overuse subsurface scattering on opaque plastics.

## Graphics rules

- For a full pedal face graphic, a single UV-mapped image can be simpler and more robust than many tiny decals.
- Use decals for modular labels, serial plates, warning stickers, badges, and reusable markings.
- Use geometry for engraved, embossed, stamped, or raised details that produce real parallax/shadows in close-ups.
- Preserve sharp text. Do not feed label masks through noisy displacement chains.
- Keep logos and type aligned to the real panel axes unless the reference clearly differs.

## Efficiency plan

- Create a small core library first: powder coat, aluminum, chrome/nickel, ABS, rubber, tolex, grille cloth, LED lens, and printed ink.
- Reuse materials and vary parameters rather than cloning nearly identical node trees.
- Test materials on representative parts: enclosure, knob, washer, foot, cabinet, grille.
- Stop adding procedural detail once it is below the target render's visible scale.

## Common failure modes

- **Metal looks gray plastic:** metallic is wrong or the lighting lacks useful reflections.
- **Chrome looks black:** there is nothing bright for it to reflect; fix the environment/lighting before increasing Base Color.
- **Powder coat looks like stucco:** bump amplitude or texture scale is far too large.
- **Plastic looks like candy:** roughness is too low and edges may be over-rounded.
- **Tolex looks painted on:** grain scale is wrong or cabinet seams/edge construction are missing.
- **Grille cloth causes moire:** weave geometry/texture is too fine for the render sampling; simplify or adjust representation.
- **Decals look pasted on:** roughness/specular response does not match the printing process or the decal sits visibly above the surface.

## Verification checklist

- Material names are reusable and understandable.
- Metals respond like metals under actual scene lighting.
- Texture scale is plausible relative to real dimensions.
- Surface bump is restrained at product-render distance.
- Graphics are sharp, aligned, and free of obvious haloing.
- Transparent materials/lenses render cleanly.
- No accidental duplicate materials are proliferating.
- The actual product has been preview-rendered under representative lighting.
