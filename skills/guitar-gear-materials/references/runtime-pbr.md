# Guitar-gear materials for glTF and WebGL

Use on the runtime derivative from [runtime export](../../guitar-gear-modeling/references/runtime-export.md). Keep accepted Blender materials in the master. glTF does not preserve arbitrary Blender procedural node networks or Blender-specific coordinate-driven shader logic; bake or translate the resulting appearance into supported glTF PBR inputs.

## Translation and baking

Inventory each material's visible contributions. Use glTF-supported Base Color, Metallic, Roughness, tangent-space Normal, AO, Emissive and alpha where required. Verify extensions against the installed exporter and runtime loader before depending on transmission, clearcoat or other non-core features. Prefer a simple proven PBR baseline.

Create suitable UVs with sufficient padding at intended mip levels. Bake unsupported color, grain, bump/normal and roughness variation separately. Bake color without studio illumination; do not freeze highlights or moving-knob shadows into base color. Keep AO restrained and avoid baking a dynamic control's shadow onto the panel. Inspect seams, mirrored UVs, tangent orientation and bake margins on the loaded GLB.

Use sRGB for base-color/emissive images and non-color data for metallic, roughness, AO and normal. In glTF, packed occlusion/roughness/metallic use R/G/B respectively when sharing one image. Check the actual exported channels and UV sets. GLTFLoader sets imported texture conventions; do not globally override color space or flipY on loaded maps. Manually supplied replacement maps must match the loader's UV/color conventions.

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

## Budget from pixels, then profile

Start around 2K primary surfaces and 1K–2K grille, with shared hardware textures and atlases where they reduce cost without sacrificing close-up labels. These are experiments, not mandatory caps. Do not carry 8K source textures into a plugin without evidence.

Record unique image count, dimensions, formats and estimated decoded memory. An uncompressed RGBA8 image costs width × height × 4 bytes, about 4/3 of that with a full mip chain: a 2048² image is about 21.3 MiB with mips, even if its PNG is small. Actual formats, render targets and environment maps alter the total; multiple independent WebViews may duplicate it.

First ship a correct baseline GLB. Consider KTX2/Basis texture compression or Draco/mesh compression only after profiling shows the relevant bottleneck. Include any decoder/transcoder JS/WASM locally, test backend support and decode latency, and compare quality at the same view. Compression is not a substitute for removing invisible construction geometry.

If grille/labels vanish only inside JUCE, inspect resource responses, MIME types and CSP before rebaking. GLB embedded images can decode through `blob:` URLs; the policy must allow the required image scheme. See [offline resources](../../juce-plugin/references/webview-ui.md#local-resources-and-development-mode).
