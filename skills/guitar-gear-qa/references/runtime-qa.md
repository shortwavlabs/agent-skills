# GLB, Three.js and plugin UI acceptance

Use after [runtime export](../../guitar-gear-modeling/references/runtime-export.md), before embedding, and again on the final JUCE build. The Blender scene audit cannot certify GLB hierarchy, WebGL appearance or host automation.

## Asset and browser gate

- Confirm master preservation and derivative/GLB provenance. Reimport/load the final export; check units, bounds, finite transforms and normal orientation.
- Compare intended roles against the independent [validation manifest](../../guitar-gear-modeling/references/runtime-export.md#validation-manifest-example); fail duplicate interactive/proxy names in raw GLB nodes and unexpected `.001` replacements. Check parent relationships, extras, choice indices and camera preset contents. No cutters, source-library display duplicates or unneeded helpers; retain semantic parents.
- Resolve all hit targets. Reject accidental duplicate parameter registrations; deliberate multiple jack targets share one binding with different choice indices.
- Test each knob at normalized 0 / 0.5 / 1 against panel markings, including reversed axes and nonzero rest poses. Repeat the same value and revisit a pose to detect drift. Check shaft/pivot remains stationary.
- Check switch state count, label order and every physical pose; fixed nuts and scales must stay fixed. Confirm LEDs have independent material state.
- Standalone Three.js must load the GLB, orbit/zoom, select camera presets, discover `userData`, expose proxy/debug views, move knobs and switches, illuminate lamps and report runtime statistics.
- Test ray hits at actual editor size, close neighbors, maximum zoom and all relevant presets. Proxy-only raycasting must work while proxies are hidden from production rendering.
- Compare Blender/runtime views with matched framing at native editor size, medium distance and maximum intended zoom. Inspect text/glyphs, grille moiré during movement, alpha/speaker visibility, black surfaces, chrome, tangents/seams and contact shadows.
- Review matched candidates at approximately 100%, 50% and 25% of delivery size. Full-resolution detail can become noise, moiré or disappear in the actual plugin; choose the smallest treatment that still reads at the intended editor size.
- Sweep the allowed orbit through front, side, rear and grazing angles. Opaque side/top/bottom walls must not reveal interior objects; rear boards must occlude what their construction covers; only intentional openings may expose speakers, tubes, chassis or wiring. Check flat print and panel-border rules for depth flicker at both close and ordinary distances.
- Verify render-on-demand: after settling, render count stops increasing; changing a control, camera, LED or size redraws. Damping/animations must stop scheduling frames when finished.

Stop asset optimization once these checks pass and measured metrics are reasonable for the product. Move to the real host; do not chase hypothetical polygon targets.

## Host and backend gate

Use [JUCE integration](../../juce-plugin/references/threejs-webview-ui.md) for implementation. Test the production embedded frontend with the dev server stopped and networking unavailable, including all images, GLB, camera data, fonts and optional decoders. Browser Chrome success does not prove native WebKit or Windows WebView2 success. Record each OS/backend/version separately; unavailable platforms are NOT CHECKED.

Verify [accessible control acceptance](../../juce-plugin/references/threejs-webview-ui.md#accessible-physical-controls) using keyboard and assistive technology on each supported backend.

For each important control: 3D interaction → host value/recorded automation → playback → matching visual state. Verify begin/end gestures on pointerup, cancellation, lost capture, blur and editor destruction; orbit must resume. Test all nine knobs when the asset has nine, otherwise the actual product's complete control list.

Save and restore all discrete choices through editor close/reopen, fresh plugin state restore and DAW save/quit/reopen. APVTS must win over frontend defaults. Check every product-defined pose and all derived lamps/mechanisms together; for an `inputMode` choice, verify each jack selection, plug placement and the DSP-facing flag. Do not infer audio behavior from a switch's artwork or physical pose.

Test the actual clean embedded build, not only the dev server. After a known visible frontend change, rebuild from the native target and prove the packaged editor changed; otherwise compare the packaged asset list/hashes with the expected `dist` outputs before visual sign-off. Then test 1, 5 and 10 plugin instances. Measure editor open/GLB load time, visible and hidden CPU, idle GPU behavior, memory growth and repeated editor-close resource cleanup. Test instance isolation by changing one instance. Distinguish one visible editor from all editors visible, DAW-wide RSS from per-instance memory, and geometry counts from renderer draw calls. Record unsupported instrumentation honestly. Use pluginval/auval and existing knob automation/state checks where available; they complement visual/backend checks.

## State-space integrity tests

Whenever several physical objects represent one logical parameter, enumerate every legal choice and assert the complete derived state: all transforms, selected target, LEDs, plug placement and DSP-facing enum/flag. Test the product's actual truth table: this may be a three-position selector, one boolean shown by two synchronized levers, or one input choice shown by two jacks. Test the Cartesian product when independent compound controls coexist so changing one cannot alter another. Do not create extra independent booleans to simplify tests.

Exercise each state through pointer/keyboard edits, normalized host updates and serialized restore; include endpoints, quantization boundaries and repeated identical updates. Assert incompatible combinations cannot be produced, non-finite/out-of-range metadata is rejected, and one instance never changes another. Drive the actual binding/derivation code and compare against an independently specified table; a test that copies the implementation only checks itself. The [gesture check](../../juce-plugin/scripts/webview_gesture_check.cpp) demonstrates counting host begin/end events, including editor teardown.

## Asset totals versus frame measurements

| Kind | Suggested method and scope |
|---|---|
| Static asset | Parse the GLB JSON chunk: count `nodes`, `meshes`, material definitions, textures/images and primitive/accessor references. For triangle-list primitives use index accessor `count / 3`, or POSITION accessor `count / 3` when nonindexed; handle strip/fan modes explicitly and exclude points/lines. Report unique mesh totals separately from scene-instance-expanded totals: count each referenced mesh primitive once per rendered scene-node instance, including repeated mesh references under different node transforms. State the selected scene and visibility policy before frame-specific culling; transforms alone do not change triangle counts. Decode/inspect image dimensions separately. |
| Specific rendered frame | Read `renderer.info.render.calls` and `renderer.info.render.triangles` after rendering a named camera at recorded size/DPR/visibility. For multiple passes, control/reset statistics explicitly and report per-pass or full-frame totals. Culling, instances, material groups and shadows affect these values. Draw calls are not an intrinsic GLB property. |
| Runtime allocation | `renderer.info.memory` counts tracked geometries/textures, not complete GPU bytes. Estimate image storage separately; use platform instrumentation for actual memory/GPU measurements and disclose its scope. |

## Reusable report

Copy into the project's existing QA record; fill measured values and evidence, not preset PASS entries.

```text
Source revision/hash / derivative / GLB hash:
Blender / Three.js / JUCE / frontend package versions:
OS / WebView backend / DAW / plugin format:
Editor pixels / DPR / camera / zoom:

Asset metric                   Before   After   Measurement method
GLB bytes:
Nodes / mesh nodes:
Unique mesh data / materials:
Unique textures / image dimensions:
Estimated decoded image memory:
Unique / scene-expanded asset triangles:
Interactive controls / hit targets:
Camera presets:

Frame/runtime metric           Before   After   Camera, size, DPR, passes
Rendered triangles / draw calls:
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
Keyboard / visible focus / screen-reader state / no focus trap:
Legal state-space / impossible combinations:
Text / cloth / material parity:
Idle rendering / cleanup / instance isolation:
Offline embedded assets / target backend:
Recorded automation and visual playback:
Editor / plugin / DAW state restore:
Remaining limitations and measured bottlenecks:
```

Compare like-for-like cameras/resolutions and explain legitimate count changes. `renderer.info` describes rendered work/resources, not necessarily asset totals or complete GPU memory. A saved screenshot proves nothing until inspected; record visual and numerical evidence separately.
