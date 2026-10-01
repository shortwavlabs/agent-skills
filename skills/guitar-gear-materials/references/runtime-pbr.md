# Guitar-gear materials for glTF and WebGL

Use on the runtime derivative from [runtime export](../../guitar-gear-modeling/references/runtime-export.md). Keep accepted Blender materials in the master. glTF does not preserve arbitrary Blender procedural node networks or Blender-specific coordinate-driven shader logic; bake or translate the resulting appearance into supported glTF PBR inputs.

## Translation and baking

Inventory each material's visible contributions. Use glTF-supported Base Color, Metallic, Roughness, tangent-space Normal, AO, Emissive and alpha where required. Verify extensions against the installed exporter and runtime loader before depending on transmission, clearcoat or other non-core features. Prefer a simple proven PBR baseline.

Create suitable UVs with sufficient padding at intended mip levels. Bake unsupported color, grain, bump/normal and roughness variation separately. Bake color without studio illumination; do not freeze highlights or moving-knob shadows into base color. Keep AO restrained and avoid baking a dynamic control's shadow onto the panel. Inspect seams, mirrored UVs, tangent orientation and bake margins on the loaded GLB.

If a normal-map seam or spike appears only after export, inspect tangent normalization/orthogonality and collapsed UV derivatives in the GLB. Repair the exporter/input data deterministically; use a stable perpendicular fallback only for genuinely degenerate vertices, not a random tangent or blanket normal-map removal.

Audit the evaluated appearance before baking. Object-linked material overrides and source-local `Generated`/`Object` coordinates can disappear when evaluated meshes are created or many parts are joined. Copy effective material slots and preserve the required per-part coordinates/variation as mesh attributes before consolidation. A matching material name is not proof that localized wear survived.

Use sRGB for base-color/emissive images and non-color data for metallic, roughness, AO and normal. In glTF, packed occlusion/roughness/metallic use R/G/B respectively when sharing one image. Check the actual exported channels and UV sets. GLTFLoader sets imported texture conventions; do not globally override color space or flipY on loaded maps. Manually supplied replacement maps must match the loader's UV/color conventions.

Keep source bakes immutable while packing channels. In particular, do not repeatedly load an already encoded sRGB base-color image through color management merely to add alpha; treat the alpha mask as non-color data and pack once into a new output. Compare the RGB bytes before/after packing so a transparency fix cannot silently change color.

Choose alpha mode by construction. Use opaque for continuous shells, `MASK`/alpha-test for hard cutouts or worn covering where the surface still owns depth, and `BLEND` only for genuinely translucent layers such as some cloth or glass. Blended materials may disable depth writes and expose interior/rear objects through an otherwise solid side panel. Orbit every opaque enclosure edge and rear board in the target loader before accepting it.

| Surface | Runtime representation and check |
|---|---|
| Tolex/vinyl | Physically scaled normal and roughness grain; retain seams and cabinet silhouette in geometry. Check wrap direction and sparkle at grazing views. |
| Grille cloth | Base color plus normal/roughness and alpha only if speaker visibility needs it. Preserve grille/baffle depth; avoid fiber geometry unless maximum zoom demonstrates the need. |
| Nickel/chrome | Metallic PBR with useful environment reflections and restrained roughness variation. Black chrome often means a reflection-lighting problem, not missing white pigment. |
| Molded plastic | Dielectric response, subtle grain; avoid exporting unsupported subsurface effects as accidental translucency. |
| Rubber | Rough dielectric with small normal detail and visible broad reflections, not featureless black. |
| Speaker cones | Subtle roughness/fiber normal, preserve visible cone depth; do not brighten hidden speakers just to expose them through cloth. |
| LED lenses | Keep an off-state lens/bezel and independently controlled emission. Use transmission only when supported and worth its cost; emission need not imply a dynamic light or bloom. |
| Panel graphics | Bake flush labels, tick marks, rules and flat logos into readable panel textures/masks. Keep raised/engraved geometry only for visible relief. |

Clone materials for independently driven LEDs and per-plugin state before changing emission. Geometry/static textures can be shared within a viewer when ownership is explicit; changing one lamp must not illuminate every lamp or another plugin instance.

## Graphics and cloth acceptance

Use the existing [graphics rules](graphics-and-decals.md) for source artwork, alignment and glyph fidelity. Atlas flat graphics where beneficial; retain separate artwork sources. Inspect numbers and pointer alignment at actual editor resolution and maximum zoom, not only a large texture preview. Check alpha halos, mip bleeding, z-fighting and grazing views.

For cloth, inspect hero, medium and maximum zoom while orbiting. Tune contrast/filtering and representation before distorting physical weave scale to hide moiré. Compare opaque, masked or blended alpha only as needed for the required appearance; transparent sorting, overdraw, speaker visibility and backfaces must be tested in the target WebView. Do not layer many transparent weave sheets as a substitute for a workable texture.

Set AO distance from the physical relationship being represented. Millimetre-scale AO can define washers and seams yet leave a cabinet recess or rear opening visually flat; add or rebake restrained enclosure-scale occlusion when those large relationships need grounding. Do not compensate by globally darkening the base color.

## Budget from pixels, then profile

Start around 2K primary surfaces and 1K–2K grille, with shared hardware textures and atlases where they reduce cost without sacrificing close-up labels. These are experiments, not mandatory caps. Do not carry 8K source textures into a plugin without evidence.

Record unique image count, dimensions, formats and estimated decoded memory. An uncompressed RGBA8 image costs width × height × 4 bytes, about 4/3 of that with a full mip chain: a 2048² image is about 21.3 MiB with mips, even if its PNG is small. Actual formats, render targets and environment maps alter the total; multiple independent WebViews may duplicate it.

Texture memory and frame time are different problems. With mip-mapping, a larger map costs memory while its editor is open and little or no frame time, so a smaller map is a memory decision: weigh it against how long editors stay open and how many are open at once, and do not expect it to fix CPU.

Judge resolution from density, not from source dimensions:

```text
texel density  = texture pixels across a surface / its physical width          (texels per mm)
screen density = drawing-buffer pixels across the view / physical width in view (pixels per mm)
```

Evaluate screen density at the closest supported zoom for every editor-size tier, using the renderer's actual pixel ratio. Where texel density is well above the largest tier's screen density, a smaller map is a candidate; where it is at or below it, the map is already the limit. Then confirm with matched views in the target WebView ([performance candidates](../../guitar-gear-qa/references/runtime-qa.md#performance-candidates-that-can-change-appearance)): the signature surfaces (relief, engraving, wear, fine grain) fail first, and they fail on the largest tier.

*Case study: half-resolution normal, hardware and enclosure maps were indistinguishable at the default tier and visibly softer at the largest tier's closest zoom, where the screen put about 30 pixels on a millimetre against 20 for the halved relief map. They saved memory only, so the maps stayed.*

When a plugin has fixed size tiers, lower-resolution texture sets for the small tiers are an option. Pursue it only when the memory matters, switching and loading between tiers is robust, equivalence is proven per tier, and the pipeline cost is justified.

First ship a correct baseline GLB. Consider KTX2/Basis texture compression or Draco/mesh compression only after profiling shows the relevant bottleneck. Compressed-texture support is architectural, not only an asset format: check that the transcoder ships locally, whether it needs WebAssembly and a worker, whether the page's Content Security Policy permits both, and how each target WebView behaves, then test decode latency and compare quality at the same view. Do not recommend it for a page whose policy forbids its worker. Compression is not a substitute for removing invisible construction geometry.

If grille/labels vanish only inside JUCE, inspect resource responses, MIME types and CSP before rebaking. GLB embedded images can decode through `blob:` URLs; the policy must allow the required image scheme. See [offline resources](../../juce-plugin/references/webview-ui.md#local-resources-and-development-mode).
