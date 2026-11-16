# Runtime lighting, environments and reflection probes

What a Blender-to-three.js lighting translation got wrong, how it was diagnosed and what fixed it. It extends [runtime presentation](runtime-presentation.md), which owns camera presets and the general rule to translate studio intent.

**Evidence (historical case studies; the method needs none of these files).**
- **Yellow Punch:** an overdrive pedal; its editor's `web/src/scene.ts` (three.js 0.185.1).
- **Prismatica:** a chorus pedal; its `plugin/web/src/scene.ts` and reports `docs/ui/ui-b3-visual-recovery-plan.md` and `ui-b3-refinement-1-final-report.md`.
  - B2 was rejected by the owner.
  - B3 checkpoint 1 was **not approved**.
  - B3 refinement 1 was accepted as a whole: asset, lighting, probes and renderer settings.

Every value below is a **case-study value**, fitted to one master on one machine. Labels used: **Validated**, **Case-study value**, **Rejected**, **Not approved** (B3 checkpoint 1), **Limitation**.

## Contents

- [Copying a rig is not translating it](#copying-a-rig-is-not-translating-it)
- [What made B2 look wrong](#what-made-b2-look-wrong)
- [What B3 changed](#what-b3-changed)
- [Reflection probes](#reflection-probes)
- [Diagnosing lighting versus materials](#diagnosing-lighting-versus-materials)

## Copying a rig is not translating it

**Prismatica B2 reused Yellow Punch's renderer:**
- a PMREM studio rendered from four emissive cards (key, fill, overhead scrim, rear strip) inside a uniform grey surround of 0.27;
- directional key, fill and floor-bounce lights;
- `NeutralToneMapping` at exposure 0.82, matching both masters' Khronos PBR Neutral at −0.28 EV.

That rig was fitted to Yellow Punch's own master, and it served that product. On Prismatica it produced the lighting half of the rejected B2.

**Translate intent, not settings:**
- what each master light contributes to the reflections and to the diffuse shading;
- what the master's world contributes;
- which surfaces need local reflections.

Then fit the runtime to **this** master, with matched-camera renders as the reference.

## What made B2 look wrong

Diagnosed in B3 by A/B experiments, scored as mean absolute error (MAE) against the master's Cycles renders (Validated):

| Cause | Effect | Evidence |
|---|---|---|
| The environment was a uniform grey room plus cards; the master lights reflections with an HDRI (`studio_small_09`, strength 0.4) over a grey ground | mirrors reflect flat grey, so toggles, footswitch wall and bezel read as grey paint | adding the HDRI and ground |
| Card radiance converted as W/(4π·A) | reflected studio lights too weak | W/(π·A), 4× brighter, scored best (footswitch luminance 63 against the master's 64). The code records it as an empirical fit, not a derivation of Cycles' radiance |
| The overhead scrim at Yellow Punch's 1.0; the master's light gives 0.38 | overhead glare; with unconverted anisotropy, a hard star | scrim and anisotropy experiments |
| The key light added again as a directional light | key counted twice | MAE fell as the directional key was lowered; it is 0 in the accepted rig |
| Directional key: no falloff | the master's panel is about 30 % brighter at the front left than at the top; the runtime was flat | spot key with decay 2 |
| A floor-bounce light that the master does not have | a bright band on the base plate's front edge, lit from below | bounce off: 75.6 → 26.9, master 30.6 |
| No local reflections | nothing reflected the panel in the controls | reflection probes |

**Not causes, by test:** the GLB export, the tone mapping and the exposure. The asset's own causes (hardware texture density, the LED, the knob reduction) are in [runtime wear, metals and LEDs](../../guitar-gear-materials/references/runtime-wear-metal-and-led.md) and [geometry fidelity](../../guitar-gear-modeling/references/runtime-derivative-and-geometry-fidelity.md).

## What B3 changed

The accepted configuration (Validated as a whole; every value is a case-study value):

**Environment**
- **HDRI:** the master's own `studio_small_09`, downscaled to 1024×512 and shipped as a local 32-bit `.hdr`, strength 0.4.
- **Rotation:** 0°. The assumed 180° scored worst.
- **Ground in the reflections:** the master's ground (albedo about 0.2, roughness 0.72) as a flat unlit plane inside the PMREM scene, never drawn in the view.
  - PMREM near plane 0.5 mm. An earlier run's near plane clipped the ground and was discarded.

**Cards**
- Fill 2.2 and rear 8.8, as W/(π·A) of the master's lights. The key card keeps a quarter of its 14.3 (3.6); the key's direct light comes from the spot below.
- Scrim **0.6**. Checkpoint 1 used the rule's 0.38 (Not approved), which hid the metals' wear; 1.0 made the knob tops glare.

**Key light**
- A `SpotLight` at the key softbox's position: `angle` π/3 (three.js's half-angle), penumbra 0.6, **decay 2**, intensity 0.3.
- 2048² shadow map.
- Narrowing its shadow camera (focus 0.41) hardened the shadows and worsened every score: rejected.

**Other lights**
- Directional key 0.
- Directional fill 0.06, with its own shadow map; removing that shadow failed contact-shadow views later.
- Bounce off. The trade-off is a darker underside.

**Renderer**
- `NeutralToneMapping` exposure 0.82.
- `PCFShadowMap` with `autoUpdate` off: maps redrawn only when a caster moves ([render scheduling](../../juce-plugin/references/threejs-webview-ui.md#rendering-threading-and-lifetime)).
- Pixel ratio capped at 1.5, MSAA.

**Black knob plastic**
- The knob material is excluded from the per-control probes and keeps the studio environment.
- Probes that reflect the turquoise panel made the black plastic look glossy turquoise.
- The cost is about 1.5 MAE worse against the master, which does reflect the panel. It was accepted as part of the refinement, and it is reversible.

**Limitation: MAE is not acceptance.** The accepted refinement scored about 1.5 MAE *worse* against the master than the unapproved checkpoint (controls 12.97 → 14.80). Scores guide experiments; the owner's review of the real plug-in decides ([visual oracle](../../guitar-gear-qa/references/visual-oracle.md)).

## Reflection probes

**Why probes are needed.** A single environment map reflects a distant studio, so nothing nearby shows in metal and gloss. Prismatica bakes local probes at load, `PMREMGenerator.fromScene(scene, 0, near, far, { size, position })`, one per control plus one for the static hardware:
- 10 probes, 128 px each, static after load;
- each sees the HDRI, the cards and the shadowed ground;
- the probe's own node is hidden during its capture;
- each probed node gets its own material clones.

**The checkpoint-1 bug (Not approved).**
- **What happened:** each control's probe sat at its node's bounding-box centre. That point lies inside the static footswitch stem and the LED bezel, which were not hidden during the capture. The probes saw the inside of a metal tube, and oblique reflections on the cap, plunger and lens came back nearly black.
- **The second instance:** the static-hardware probe, placed 4 mm over the cap, sat about 1 mm from the MODE knob's side, which filled half of every nut, washer and jack reflection.

**The fix (Validated):**
- Each control's probe now sits 2 mm above its bounding box, centred on it.
- The hardware probe sits above the highest knob top.
- The cap and plunger turned from black to spun silver and chrome.
- The hardware fix alone changed 0.96 % of pixels.
- Nothing else in the material system changed.

**Placement rules:**
- Place each probe where its surface "looks from": above or in front of the reflecting part, in open air.
- Hide the probed part during capture, and check that **no other static geometry** encloses or touches the probe position.
- Inspect what the probe actually captured (render its cube faces, or put a mirror sphere at that position) before tuning materials.
- Decide per material whether local probes help. Black plastic and the panel's own colours may read better with the distant studio.

**Cost:** the first bake took 314–326 ms in WKWebView, but mostly as first-use shader compilation and upload; a second bake took 22–24 ms. See [rejected approaches](../../juce-plugin/references/webview-gpu-memory-and-context-recovery.md#rejected-approaches-and-attribution-lessons) before optimizing probes away.

## Diagnosing lighting versus materials

The method that found the B2 and checkpoint-1 faults (Validated):

1. **Match cameras to the master.** Same offsets from each control node, same framing. Prismatica also matched Yellow Punch's controls at the same panel distance to compare the two products directly.
2. **Look from the side.** Oblique views expose environment and probe faults that the front view hides.
3. **Inspect what the environment and each probe actually capture** before touching a material.
4. **Change one variable** (an intensity, a position, an anisotropy factor) through a live hook in the running page, and score it against the master. Prismatica's score masked the background and compared MAE, luminance and the 95th percentile.
5. **Separate the probe or environment from the material.** If a part is wrong only at some angles or positions, suspect what it reflects first.
6. **Compare matched views** at default and closest zoom, and keep each improvement to the approved appearance.
7. **Judge in the real plug-in WebView.** A browser capture is not evidence for the plug-in's WebView, and neither is a locked-screen run.

**Lesson (Validated):** "missing wear" on the hardware was the lighting hiding baked wear (the probe bug, a dim scrim, panel reflections), not missing data. Check the reflections before adding wear or changing materials.
