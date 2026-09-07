# GLB, Three.js and plugin UI acceptance

Use after [runtime export](../../guitar-gear-modeling/references/runtime-export.md), before embedding, and again on the final JUCE build. The Blender scene audit cannot certify GLB hierarchy, WebGL appearance or host automation.

## Asset and browser gate

- Confirm master preservation and derivative/GLB provenance. Reimport/load the final export; check units, bounds, finite transforms and normal orientation.
- Compare intended roles against stable node names. No cutters, source-library display duplicates or unneeded helpers; retain semantic parents.
- Resolve all hit targets. Reject accidental duplicate parameter registrations; deliberate multiple jack targets share one binding with different choice indices.
- Test each knob at normalized 0 / 0.5 / 1 against panel markings, including reversed axes and nonzero rest poses. Repeat the same value and revisit a pose to detect drift. Check shaft/pivot remains stationary.
- Check switch state count, label order and every physical pose; fixed nuts and scales must stay fixed. Confirm LEDs have independent material state.
- Standalone Three.js must load the GLB, orbit/zoom, select camera presets, discover `userData`, expose proxy/debug views, move knobs and switches, illuminate lamps and report runtime statistics.
- Test ray hits at actual editor size, close neighbors, maximum zoom and all relevant presets. Proxy-only raycasting must work while proxies are hidden from production rendering.
- Compare Blender/runtime views with matched framing at native editor size, medium distance and maximum intended zoom. Inspect text/glyphs, grille moiré during movement, alpha/speaker visibility, black surfaces, chrome, tangents/seams and contact shadows.
- Verify render-on-demand: after settling, render count stops increasing; changing a control, camera, LED or size redraws. Damping/animations must stop scheduling frames when finished.

Stop asset optimization once these checks pass and measured metrics are reasonable for the product. Move to the real host; do not chase hypothetical polygon targets.

## Host and backend gate

Use [JUCE integration](../../juce-plugin/references/threejs-webview-ui.md) for implementation. Test the production embedded frontend with the dev server stopped and networking unavailable, including all images, GLB, camera data, fonts and optional decoders. Browser Chrome success does not prove native WebKit or Windows WebView2 success. Record each OS/backend/version separately; unavailable platforms are NOT CHECKED.

For each important control: 3D interaction → host value/recorded automation → playback → matching visual state. Verify begin/end gestures on pointerup, cancellation, lost capture, blur and editor destruction; orbit must resume. Test all nine knobs when the asset has nine, otherwise the actual product's complete control list.

Save and restore all discrete choices through editor close/reopen, fresh plugin state restore and DAW save/quit/reopen. APVTS must win over frontend defaults. For `ampMode`, check CH1/Off/CH2 poses and all lamps together. For `inputMode`, verify High/Regular selection, plug placement and the DSP-facing flag. Do not infer audio-Off semantics from the toggle's physical center position.

Test 1, 5 and 10 plugin instances. Measure editor open/GLB load time, visible and hidden CPU, idle GPU behavior, memory growth and repeated editor-close resource cleanup. Test instance isolation by changing one instance. Distinguish one visible editor from all editors visible, DAW-wide RSS from per-instance memory, and geometry counts from renderer draw calls. Record unsupported instrumentation honestly. Use pluginval/auval and existing knob automation/state checks where available; they complement visual/backend checks.

## Reusable report

Copy into the project's existing QA record; fill measured values and evidence, not preset PASS entries.

```text
Source revision/hash / derivative / GLB hash:
Blender / Three.js / JUCE / frontend package versions:
OS / WebView backend / DAW / plugin format:
Editor pixels / DPR / camera / zoom:

Metric                         Before   After   Measurement method
GLB bytes:
Nodes / mesh nodes:
Unique mesh data / materials:
Unique textures / image dimensions:
Estimated decoded image memory:
Triangles / renderer draw calls:
Interactive controls / hit targets:
Camera presets:
GLB load / editor open time:

Instances   Visible editors   CPU visible/hidden   GPU idle   RSS/memory delta
1:
5:
10:
Repeated open/close cleanup evidence:

Criterion — PASS / FAIL / NOT CHECKED / NOT APPLICABLE — evidence
Master preserved / final export provenance:
Hierarchy / extras / no helper leakage:
Pivot and 0 / 0.5 / 1 calibration:
Switch / input / indicators:
Hit targets / camera / orbit / zoom:
Text / cloth / material parity:
Idle rendering / cleanup / instance isolation:
Offline embedded assets / target backend:
Recorded automation and visual playback:
Editor / plugin / DAW state restore:
Remaining limitations and measured bottlenecks:
```

Compare like-for-like cameras/resolutions and explain legitimate count changes. `renderer.info` describes rendered work/resources, not necessarily asset totals or complete GPU memory. A saved screenshot proves nothing until inspected; record visual and numerical evidence separately.
