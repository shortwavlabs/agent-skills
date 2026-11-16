# Procedural wear, baking, metals and LEDs for runtime assets

What two pedal projects established about carrying procedural wear, plated and machined metal, and LED lenses from Blender into a three.js editor. It extends [runtime PBR](runtime-pbr.md), which owns the general translation rules, colour spaces and texture budgets.

## Bundled tools

These run on any Blender project. They need nothing from the case-study workspaces. Tested with Blender 5.2.1 LTS. Each runs a plain-Python `--self-test` (CI) and a Blender `--blender-test` on synthetic scenes (local; CI has no Blender).

| Tool | Use |
|---|---|
| [`scripts/wear_library.py`](../scripts/wear_library.py) | the `GG_WEAR_*` node groups and `metal_wear` / `plastic_wear` / `paint_wear` builders, ported node for node from the case study's wear library; JSON wear profiles ([example](../examples/wear_profile.example.json)). `blender --background in.blend --python wear_library.py -- apply --profile p.json [--save out.blend]` |
| [`scripts/material_inspect.py`](../scripts/material_inspect.py) | read-only JSON report: materials, Principled inputs linked or default, `GG_WEAR_*` groups used, per-object `gg_*` properties and slot links, image colour spaces, missing external images |
| [`scripts/pbr_bake.py`](../scripts/pbr_bake.py) | base colour, ORM (R AO, G roughness, B metallic) and tangent normal bakes per family, with a UV report, source hashing and a cache key in `bake_provenance.json` ([example config](../examples/bake_config.example.json)). `blender --background in.blend --python pbr_bake.py -- --config bake.json --out dir` |

Two departures from the case-study procedure are deliberate:
- **Margin repair pass.** `pbr_bake.py` adds a second, margin-0 pass for families of several objects (`repair_margin_overlap`, on by default). Blender bakes object by object, and a later object's margin overwrites an earlier object's edge texels; that was reproduced with a 2-texel island gap.
- **RGBA output.** It writes RGBA PNGs by default; `"color_mode": "RGB"` reproduces the case studies' files.

**Evidence (historical; not needed to use the tools).** The file names below identify the case-study sources the tools were ported from.
- **Yellow Punch** (its Blender `wear_lib.py`, runtime `build_runtime.py` and runtime report).
- **Prismatica:**
  - Blender stages B2 and B3 (`Blender/prismatica/b2|b3/build_runtime.py`, `bake_materials.py`, `wear_master.json`);
  - reports `docs/ui/ui-b2-production-asset-final-report.md`, `ui-b3-visual-recovery-plan.md` and `ui-b3-refinement-1-final-report.md`;
  - B2 was rejected by the owner; B3 checkpoint 1 was not approved; B3 refinement 1 was accepted.

Every number below is a **case-study value**: derive your own from the master. Labels used: **Validated**, **Case-study value**, **Rejected**, **Untested**, **Limitation**.

## Contents

- [Procedural wear is a technique, not a texture](#procedural-wear-is-a-technique-not-a-texture)
- [Bake the evaluated appearance](#bake-the-evaluated-appearance)
- [Brushed, spun and turned metal](#brushed-spun-and-turned-metal)
- [Chrome, nickel and satin plating](#chrome-nickel-and-satin-plating)
- [LED lenses](#led-lenses)
- [Texture fidelity](#texture-fidelity)

## Procedural wear is a technique, not a texture

**Structure (Validated, Yellow Punch `wear_lib.py`):**
- **Base materials stay untouched.** Each base material gets one copied derivative (`<name>__V12_WORN`). Only the Principled BSDF's Base Color, Roughness, Metallic and Normal inputs are re-routed through a wear layer; outside every mask the result equals the base material.
- **Masks are physically scaled.** They use Object coordinates × 1000, so feature sizes are in millimetres on every part.
- **Reusable node groups:**

  | Group | What it makes | Key inputs |
  |---|---|---|
  | `GG_WEAR_Scratches` | four rotated families of stretched-noise contour lines, filtered by direction and broken into segments | Length, Feature, Width, Density, Angle, Spread, Seed |
  | `GG_WEAR_Blotch` | soft patches for tarnish, polish and dull areas | Size, Threshold, Softness, Seed |
  | `GG_WEAR_CreviceOxide` | oxide specks gated by local ambient occlusion | Distance, Speck, Density, Seed |
  | `GG_WEAR_ConvexEdge` | edge wear from a Bevel-node normal dotted with the true normal, × local AO | Radius, Low, High |
  | `GG_WEAR_EnclosureChips`, `…Strokes` | deterministic paint chips, rubs and scratches from data lists, some cut to the substrate | per-feature data |

- **Base finishes are not in the wear layer.** Powder-coat orange peel, machining rings and the radial tangent for spun metal live in each product's base material graphs, which the wear layer leaves untouched. Yellow Punch's earlier builds show orange-peel noise and a radial tangent, but whether those exact values survive in its final build was not verified. No anodized finish was found in either product.
- **One builder per material family:** `metal_wear` (scratches, polish, dull, tarnish, oxide, edge, lip wear), `plastic_wear`, `insert_wear`, `paint_wear`, `bottom_wear`, `rubber_wear`, `dc_wear`.
  - Metal bump distance is about 4 µm; paint bump is 40 µm ("about the coating thickness").
- **Per-part amounts:**
  - Each part carries custom properties (`gg_wear_*`, `gg_wear_seed`, `gg_lip_z`, `gg_lip_r`), read by `Attribute (Object)` nodes.
  - A profile table sets each amount: `level[family][key]` × a per-object multiplier. A lightly handled output jack runs at about 0.8 of the input jack's wear.

**Vary wear by manufactured component (Validated):**
- **Turned footswitch cap.** A narrow contact zone with two scratch families: front-to-back shoe travel (long, along one direction) and short handling marks, plus a polished patch.
- **Satin nickel washers.** Crevice oxide and tarnish, no scratches across the face.
- **Polished chrome** (plunger, LED bezel). Grey tarnish only.
- **Moulded black knobs.** Polished ridge edges (lower roughness) in the grip band and contact scuffs, not metal scratches.
- **Powder-coated enclosure.**
  - Edge-apex and corner wear, footswitch-shoe and jack rubs, micro-abrasion and deterministic chips that expose the substrate.
  - Labels and engraving are excluded from the masks.
- **Toggle levers** (Prismatica B3, F4). `metal_wear` on the toggle's own plated material, amounts per part, feature sizes scaled to the toggle assembly, a distinct seed per part.

**Transferring wear to another product (Validated, Prismatica B3):**
- **Check what the master already contains.** Prismatica's master already used Yellow Punch's `GG_WEAR_*` groups on the footswitch, LED bezel, knobs, pot hardware and jacks. B3 read them out (per object: its `gg_wear_*` properties, materials and link type; `material_inspect.py` does this) and baked them.
- **Separate missing wear from hidden wear.** The owner's "missing wear" was the runtime lighting hiding it (a probe bug, a dim scrim, panel reflections in the knobs; see [runtime lighting](../../guitar-product-render/references/runtime-lighting-and-probes.md)), not missing data. Check that before adding wear.
- **Transfer the technique, not the numbers.** Apply the groups to the target part's own material with amounts and feature sizes fitted to that part. Never copy another product's baked texture or its whole material.

## Bake the evaluated appearance

**Settings both products used (Validated):**
- Cycles on the Metal GPU; 16 samples, seed 12; no denoiser; 8-texel margin; 8-bit RGBA PNG. Prismatica added single-threaded baking for reproducibility ([reproducible derivatives](../../guitar-gear-modeling/references/runtime-derivative-and-geometry-fidelity.md#make-the-build-reproducible)).
- **Base colour:** baked as emission through a temporary emission node, without studio light.
- **ORM:** R = AO, G = roughness, B = metallic. Roughness and metallic are baked as emission into G and B; AO is baked separately with an AO node (16 samples) and packed into R afterwards, leaving the raw bakes untouched.
  - AO distance is set per family: Yellow Punch 4 mm; Prismatica 4 mm for knobs and enclosure, 2 mm for hardware and spun parts.
  - Hide the studio ground during the AO bake.
- **Normal:** tangent space.
  - Relief replaced by flat geometry, or a reduced part, is baked selected-to-active from the detailed source. Yellow Punch's engraved cap: cage 0.4 mm, ray 0.9 mm. Prismatica's reduced parts: cage 40 µm, ray 0.2 mm, 128 samples.
- **Colour spaces:** base colour sRGB; ORM, AO and normal Non-Color.
- **Order:**
  1. convert parts in place;
  2. restore the object-linked wear materials that conversion drops;
  3. assert the wear properties are unchanged;
  4. UV-unwrap;
  5. bake each part from its own material;
  6. **only then** join into semantic meshes.
- **Atlases:** one per material family (knobs, hardware, spun metal, enclosure, top or bottom). UV methods:
  - smart project at 66° with island and pack margins;
  - an unfolded single chart for a flat plate (Yellow Punch's bottom plate: smart project gave 9.1 px/mm, the unfolded chart 15.8);
  - lathe (polar) UVs for turned parts (below).
- **Limitation:** Yellow Punch's bake logs repeat a Cycles "maximum number of closures exceeded (76 > 64)" warning, never investigated. Check the baked result against the master when a material graph is that large.

**Preserve the procedural appearance, not its average.**
- Inspect the baked maps at texel scale against the master's own render, region by region: scratches, tarnish edges, chip rims, machining rings.
- A material can match the master's mean colour and still have lost every scratch.
- Compare under the runtime's lighting too, because wear that the bake kept can still be hidden there.

## Brushed, spun and turned metal

**Direction comes from the UVs (Validated, both products).**
- Spun knob tops and the turned footswitch cap are split from their rims (by face normal), poked, and given **lathe (polar) UVs**: u = angle about the shaft.
- The glTF tangent then runs around the shaft and `KHR_materials_anisotropy` draws circular brushing with no rotation texture.
- Export tangents, then orthonormalise them, with a fixed fallback for faces whose UVs collapse at the pole. Limitation: a 4-pixel dark dot remained at Prismatica's lathe pole.

**Strength must be calibrated, not copied.**
- **Yellow Punch:** it measured Blender's Anisotropic input by baking it and taking the mean (0.823 spun, 0.45 cap), then exported those values. They suited its renderer.
- **Prismatica, Rejected:** exporting Blender's values unconverted drew a hard star highlight under its lighting.
- **Prismatica, Validated:** glTF `anisotropyStrength` = Blender Anisotropic × 0.35 on spun knob tops (softer satin) and × 0.6 on the turned cap, patched into the GLB JSON after export. Anisotropy 0 made the cap too dark.
- **The rule:** Blender's Anisotropic input and glTF `anisotropyStrength` are not equivalent units. Calibrate per finish in the target renderer against the master.
- **Limitation:** Blender's glTF importer renders anisotropic faces darker than the three.js viewer. Judge anisotropy in the target viewer, not in a Blender re-import.

**Footswitch cap (Validated, Prismatica B3 refinement 1).** What made it convincing:
- **Material:** turned-cap anisotropy × 0.6 on lathe UVs, from the shared spun-metal atlas.
- **Geometry:** the cap keeps every face, including the overhanging rim; stem, washer, nut and plunger stay unreduced, with 2048² hardware maps.
- **Lighting:** the reflection probe moved above the control instead of inside it; the scrim raised from 0.38 to 0.6.

The cap was black at oblique angles until the probe moved: that was a lighting fault, not a material fault ([probe placement](../../guitar-product-render/references/runtime-lighting-and-probes.md#reflection-probes)).

**Limitations:** the footswitch nut stayed a warm nickel (a recorded defect), and the toggle nuts render darker than the master's; that cause was not isolated.

## Chrome, nickel and satin plating

- **Metal reads from what it reflects.** A surface with correct metalness, roughness and wear can look like grey plastic when the environment is a uniform grey room. That was Prismatica B2's chrome ([runtime lighting](../../guitar-product-render/references/runtime-lighting-and-probes.md#what-made-b2-look-wrong)). Dark chrome is rarely a base-colour problem, so fix the environment before the material.
- **Rejected (Prismatica B3, F4a):** Yellow Punch's polished-chrome material put on Prismatica's toggles read as a **dark mirror**.
- **Validated:** the toggles' own satin plating (metallic 1, low anisotropy), baked into the hardware atlas, with procedural wear added.
- **The rule:** keep the target product's own finish, and add wear to it.

## LED lenses

**Two opaque domes, different outcomes:**
- **Yellow Punch's opaque dome (its shipped runtime).** A dark red base colour with a 64² emission map (a Gaussian hot core), the internals deleted. It is that product's design, not evidence that the technique suits every lens.
- **Rejected: Prismatica B2's opaque dome.** Roughness 0.06, emission from an orthographic Cycles render of the lit LED (128²) at emissive strength 7.64, internals deleted. The owner rejected it: "a red circle painted on the pedal".

**Validated (Prismatica B3 refinement 1):**
- **Geometry:** the master's lens, die, reflector cup and post, all under the LED's semantic node.
- **Lens material:**
  - glass with `KHR_materials_transmission` 1.0, `KHR_materials_ior` 1.52 and `KHR_materials_volume`;
  - volume thickness 3 mm, attenuation distance 1 mm;
  - attenuation colour derived from the master's absorption colour and density, as exp(−ρ(1−c)d);
  - roughness 0.02, and a faint emissive glow of 0.15.
- **Die:** emissive with `KHR_materials_emissive_strength` 27, the master's 9 × a gain of 3.
- **Reflector cup:** base colour = master × 0.15 to stand in for the bezel's shadow, which image-based light does not know. Metallic, roughness 0.12, glow 0.6.
- **Lit and bypassed states:** the controller clones the LED materials per instance. Bypass sets emissive intensity to 0 and multiplies the colour by 0.18.
- **Rejected during tuning:**
  - cup glow ≥ 1.2 (a glowing ball);
  - glass glow 0.6 (reads painted);
  - the glass material named outside the controller's material prefix, so it did not switch.

**Support and cost:**
- three.js 0.185.1's GLTFLoader accepted all four extensions. Check the extensions against your exporter, loader version and WebView before depending on them.
- Transmission renders an extra opaque pass into a full-viewport target on every frame the LED is on screen. The die lights nothing, and there is no interreflection inside the lens.
- Prismatica's attribution measured about 77 MB of graphics memory and half the per-frame opaque work for the glass.
- A half-resolution transmission target failed 27 views, and no cheaper technique kept the approved look. The trade-off is unresolved ([rejected approaches](../../juce-plugin/references/webview-gpu-memory-and-context-recovery.md#rejected-approaches-and-attribution-lessons)).
- **Do not use transmission everywhere.** Use it where the lens is a signature detail at the intended zoom and the cost is measured.

## Texture fidelity

Use [budget from pixels](runtime-pbr.md#budget-from-pixels-then-profile) for the method. The evidence:

**Density, not file size, made B2 blurry (Validated).**
- Prismatica B2's hardware atlas was 1024² and only 28 % filled: 7.2 texels/mm. B3 diagnosed it as a cause of blurred hardware.
- B3 used 2048² (14.5 texels/mm, close to Yellow Punch's 14.9).

**Packed size is not memory.**
- B2's 13 images were 8.57 MB as files and about 102 MiB decoded with mips (w × h × 4 × 4/3).
- Accepted B3's 15 images were about 232 MiB decoded.
- A smaller PNG does not reduce decoded or GPU memory; only fewer texels or a GPU-compressed format does.
- Decoded CPU copies held by the page are a separate cost, which can be released after upload ([WebView GPU memory](../../juce-plugin/references/webview-gpu-memory-and-context-recovery.md)).

**Reduce with evidence, region by region.**
- **Validated (Yellow Punch):** three normal maps were halved after `probe_normal_stats` showed more than 95 % of texels flat and under 0.04 % losing more than 2° at half size.
- **Rejected (Prismatica):**
  - Half-size base colour and normal maps softened the ivory diagonal and its wrap onto the sides, and changed the knob's top-edge highlight band. The enclosure normal map shapes that band.
  - In B2, a half-size top base colour softened the paint boundary. The boundary moved into geometry instead: the cap was cut along it and carries three paint materials, reconstructed within 0.66 of one 8-bit code.
  - Smaller spun and knob maps passed, but saved 6 MiB: not worth a new asset.
- **Protect** engraving normals, delicate hardware wear, UV-seam regions and paint boundaries. Check them at 1:1 at the largest editor size and closest zoom, where a texel covers the most screen pixels.

**GPU-compressed textures (KTX2 / ASTC)** remained an unimplemented architectural option in Prismatica (estimated about −180 MB per editor), and Yellow Punch rejected KTX2 for its new dependency and content-security policy. Neither is a validated optimization.
