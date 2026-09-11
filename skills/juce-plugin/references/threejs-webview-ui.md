# Interactive 3D guitar-gear plugin UI

Use for Blender-authored amps, pedals and rack gear rendered with Three.js in JUCE 9. This reference owns runtime/control architecture. [WebView integration](webview-ui.md) owns CMake, native APIs and offline serving; [runtime export](../../guitar-gear-modeling/references/runtime-export.md), [PBR translation](../../guitar-gear-materials/references/runtime-pbr.md), [camera translation](../../guitar-product-render/references/runtime-presentation.md) and [runtime QA](../../guitar-gear-qa/references/runtime-qa.md) own their respective asset stages.

Do not overfit this architecture to amplifiers. Pedal footswitches, rack rotary selectors, alternative patch jacks, LED rings and meters use the same bindings and derived-state rules. Choose boolean, discrete or continuous semantics from the actual control contract; real independently routed patch ports must not be collapsed merely because alternative amp inputs use one choice.

## Minimal project layout

```text
GuitarGearPlugin/
├── CMakeLists.txt
├── Source/
│   ├── PluginProcessor.h/.cpp
│   └── PluginEditor.h/.cpp
├── blender/
│   ├── gear_master.blend
│   └── gear_juce.blend
└── web/
    ├── package.json
    ├── package-lock.json
    ├── index.html
    ├── src/
    │   ├── main.ts
    │   ├── parameters/        # registry, mock/JUCE bindings
    │   └── three/             # scene, controls, hits, invalidator
    ├── assets/
    │   ├── gear.glb
    │   ├── runtime_manifest.json
    │   └── runtime_camera_presets.json
    └── dist/                  # generated HTML/JS/CSS/assets
```

Export the derivative to `web/assets`; the frontend build copies required runtime assets into `web/dist`. CMake depends on frontend sources, lockfile and input assets, builds `dist`, then embeds its outputs with `juce_add_binary_data`. The editor resource map serves those outputs; master/derivative Blender files stay out of BinaryData. The manifest may be validation-only. Reuse an existing equivalent layout rather than reorganizing a working project.

## Implementation sequence

Follow this order, reusing accepted artifacts and existing implementations at each phase:

1. Inspect Blender source and protect the accepted master.
2. Create a runtime/export collection in a derivative file.
3. Build semantic hierarchy and control pivots.
4. Create/verify simple hit targets.
5. Consolidate static geometry and flatten printed graphics.
6. Translate/bake materials to glTF PBR.
7. Export GLB with metadata and verify a fresh load.
8. Build a standalone Three.js validation app.
9. Add generic parameter bindings using mock state.
10. Embed the same frontend into JUCE WebBrowserComponent.
11. Serve local production resources; prove offline loading.
12. Connect one parameter end-to-end, such as Gain or Bass.
13. Verify DAW recording, playback and state restoration for it.
14. Generalize to all controls using metadata and the same bindings.
15. Add the product's physical semantic controls: discrete switches, pull knobs, input jacks and any derived mechanical/LED/plug state.
16. Profile 1, 5 and 10 instances, idle rendering and editor cleanup.

Do not repeatedly optimize the asset after its browser gate passes. Profile the actual host before pursuing compression, more atlases or geometry reduction.

## State ownership and runtime structure

```text
DAW ↔ APVTS ↔ WebView relay/attachment ↔ ParameterBinding ↔ Three.js
              ↓
         DSP parameter reads
```

APVTS owns plugin parameter truth. Three.js represents it. Avoid a second channel/power/input state in the frontend. Scene controllers should not import JUCE; keep the native dependency in the binding/environment adapter.

Reuse small components with these responsibilities (names are illustrative):

| Component | Responsibility |
|---|---|
| ParameterRegistry | One binding per supported parameter ID; reject missing/duplicate registrations |
| MockParameterBinding / JuceParameterBinding | Same normalized value/gesture/subscription contract, different backend |
| AmpKnobController | Metadata, rest pose, absolute angle, calibration |
| AmpSwitchController | Discrete choice snapping and absolute poses |
| AmpIndicatorController | Derived per-instance lens/emission state |
| HitTestController | Proxy-only raycast, pointer capture and gesture lifecycle |
| CameraController | Presets, orbit constraints, resize |
| RenderInvalidator | Coalesced redraw requests and idle/visibility lifecycle |

```ts
interface ParameterBinding {
  readonly id: string;
  getNormalisedValue(): number;
  beginGesture(): void;
  setNormalisedValue(value: number): void;
  endGesture(): void;
  subscribe(callback: (value: number) => void): () => void;
}
```

Reject non-finite inputs and clamp normalized values to [0, 1]. Define subscriptions to immediately publish the current value and then publish backend changes. Mocks own defaults only in standalone browser mode. In JUCE mode require the expected relays and fail visibly if absent; never silently fall back to mocks inside a broken plugin editor.

Create bindings/subscriptions, request current attachment state, then apply it to controls. JUCE slider properties/range may arrive asynchronously; listen to both properties and value changes so normalized readings update correctly. Do not write frontend defaults into APVTS. If explicit resynchronization is needed, expose a small native `requestParameterSync` function that invokes each attachment's `sendInitialUpdate()` on the message thread after frontend listeners are ready. Repeat on editor reload/reopen. The native bridge's initial-state request remains useful; the handshake closes startup timing gaps.

## Absolute controls and pointer UX

Discover controls via validated `object.userData`, not one handwritten JS handler per knob. Cache each imported local rest quaternion. For the export convention defined in runtime-export, calculate:

```text
angle(u) = min_angle + u × (max_angle − min_angle)
q(u) = qRest × axisAngle(localAxis, rotation_sign × (angle(u) − rest_angle))
```

Convert degrees to radians once. Use quaternion copy/multiply from `qRest` each update, never `rotation += delta`. For switches choose the absolute entry in `state_angles` and subtract the recorded rest angle. Check 0 / 0.5 / 1 against printed markings, repeated values, axis direction and pivot stability. Do not rotate the panel scale with the knob.

Prefer vertical drag: up increases, down decreases; Shift optionally reduces sensitivity. Map pointer coordinates using the canvas bounds. On a proxy hit, disable orbit before its handler starts, capture the pointer and begin one gesture. Moves set normalized values; pointerup ends it once. One idempotent cleanup path handles pointercancel, lost capture, window blur, page teardown and editor destruction, releases capture and restores orbit. Use the shared [native gesture cleanup pattern](webview-ui.md#gesture-cleanup-on-editor-destruction) so editor destruction closes an outstanding gesture even when JS unload does not run. Preserve existing click-cycle toggle UX when it works; bracket each cycle/select with one gesture. Double-click reset is optional and uses the actual parameter default.

## Physical controls and one logical state

Use the existing physical knob/toggle/jack/lamp as the interaction target instead of adding an unnecessary flat selector. Keep debug selectors in development. Provide accessible names and keyboard equivalents without creating duplicate authoritative state.

Define the legal state space from the actual hardware/product behavior; do not force every amplifier into the same switch model. One physical selector should normally have one boolean/choice authority. Conversely, several mechanical objects that deliberately represent one state should share one binding and have multiple subscribers, not independent parameters that can disagree.

For a product whose three-way amp toggle genuinely selects Channel 1 / Off / Channel 2, create one `AudioParameterChoice`, such as `ampMode`, with those labels and default index 1. Remove redundant independent power/channel parameters and relays. Keep shipped IDs/order compatible or implement an explicit state migration; a pre-release rename must document old-state behavior.

| Index | Normalized | Physical pose | Power | CH1 | CH2 |
|---|---|---|---|---|---|
| 0: Channel 1 | 0.0 | UP | on | on | off |
| 1: Off | 0.5 | CENTER | off | off | off |
| 2: Channel 2 | 1.0 | DOWN | on | off | on |

Snap finite normalized input with `Math.round(Math.min(1, Math.max(0, u)) * 2)`; writes use `index / 2`. APVTS choice quantization and frontend snapping must agree, including automation at intermediate values. All switch and lamp subscribers consume this same choice. Do not feed derived visual updates back into the parameter.

Expose `enum class AmpMode { channel1 = 0, off = 1, channel2 = 2 };` and a DSP-facing `getAmpMode()` that safely converts the raw choice index. Cache its atomic parameter pointer during setup. Define Off audio behavior from the existing DSP contract; otherwise leave an explicit TODO. Never infer silence/bypass/modeled power-off from the artwork or add DSP switching during a UI-only task.

Another product may expose one `ampEnabled` boolean through two synchronized levers and a pilot lamp. Give it one relay/attachment/binding; every lever and indicator subscribes to the same normalized state, and clicking either lever edits that binding. Derive transforms and lamp state one-way from the parameter and test both entry points. Do not introduce a second standby boolean unless the DSP/product contract truly permits an independent state.

As an optional extension, the same subscriber may modulate a cloned per-instance tube-heater emissive material. Keep the glow restrained and avoid a dynamic light or bloom unless target-size comparison justifies it; report it as a recommendation, not an implemented feature, until the target runtime validates it.

For two alternative input jacks, use one choice parameter whose labels and order come from the product/manual; examples include High/Low, input 1/2 and Regular/High. Read each target's exported choice-index field as defined in the [validation manifest](../../guitar-gear-modeling/references/runtime-export.md#validation-manifest-example); preserve an existing `choice_index`/`choice_value` contract and do not special-case the node name. Clicking a jack writes its verified choice index. Name and derive any DSP-facing flag from that contract rather than geometry spelling. These alternative physical sockets do not imply two audio buses or two independent booleans. Keep the existing plugin bus layout.

Derive a plug's position/visibility from `inputMode`: attach it to the selected jack frame. A lightweight cable is optional visual state, never another parameter authority. Implement click-to-select before drag-and-drop cable interaction. A debug readout should expose the enum index/label and selected jack so tests can compare the physical representation to host state.

## Pull/rotate controls

A pull-capable rotary has two degrees of freedom and usually two host parameters: continuous rotation plus a binary mechanical position. Export a pull parent with a rotary child and independent metadata/hit targets. Bind rotation to the continuous parameter and parent translation to the binary parameter, each from its cached rest transform. Clicking or keyboard-activating the pull cap edits only the binary state; dragging the rotary rim edits only rotation. Verify all four endpoint combinations and repeat updates to catch transform drift.

Expose those two actions as two accessible semantic controls—for example, a `Clean Volume` range and a `Bright` toggle—even when both highlight the same physical knob. Avoiding duplicate focus targets means one accessible target per action, not hiding the pull action because rotation already has one.

## Plugin utilities and camera controls

Keep software-only utilities in ordinary accessible chrome rather than inventing historical hardware. Input/output trim, cabinet simulation and a view selector are typical header controls; register them in the same parameter registry/APVTS contract when they are host state, but explicitly exclude them from the GLB's expected physical-control nodes. A camera preset/view selector is presentation state unless the product explicitly needs it automated or serialized. It may activate Front, Front 3/4, Rear or Controls presets while the canvas still permits bounded orbit/zoom.

## Accessible physical controls

Canvas meshes alone do not provide accessible controls. Expose focusable DOM controls using the same ParameterBinding: native range inputs for knobs, a radio group/select for exclusive modes/jacks, and buttons for appropriate switches. A compact accessible control view or overlays may accompany the 3D view; avoid two competing focus targets for one control. Do not hide the accessible controls with `display: none` or `aria-hidden`.

Give each control a meaningful label, current value/choice, units and disabled state where applicable. Show a visible focus indicator on the corresponding hardware or accessible control. Provide predictable Tab order, arrow-key adjustment/choice selection, Home/End where appropriate, and Enter/Space activation. Focused control keys must not also orbit the camera. Route keyboard edits through the same gesture/snap path, end an active edit on blur, and reflect host automation without stealing focus. Use text/semantics as well as lamp color to expose selected states; do not announce every automation frame as a live-region update.

Acceptance includes keyboard-only access to every intended control, visible focus, no focus trap, screen-reader names/current values, and state/gesture parity with pointer operation on the actual WebView backend. Unsupported accessibility testing is NOT CHECKED, not a visual pass.

## Rendering, threading and lifetime

Coalesce invalidations into a pending requestAnimationFrame. Invalidate after GLB/texture load, visible parameter/LED changes, camera changes, active animation, resize and visibility restoration. With no damping, render once per change. With orbit damping/animated transitions, schedule only until settled. An unconditional 60 FPS loop is inappropriate for an idle amp panel.

Stop scheduling while hidden; on reopen/requested visibility resync state and redraw. Cancel active gestures and pending frames on teardown; unsubscribe binding, DOM and orbit listeners. Dispose owned geometries, cloned materials, textures, environment/render targets and renderer; close owned ImageBitmaps where applicable. Track shared ownership so one viewer cannot dispose a resource still used by another. Do not assume separate WebViews share GPU textures.

Never call WebBrowserComponent, JS, Three.js, filesystem access, GLB parsing, JSON serialization or UI locks from `processBlock()`. Keep [audio-thread rules](audio-thread-safety.md): audio → reduced atomic/lock-free state → message-thread timer → WebView. Throttle future meters only while visible; APVTS attachments handle parameter UI synchronization. No WebView is required for audio processing or host automation.

## Failure diagnosis

| Symptom | First check |
|---|---|
| Knob orbits instead of rotating | Shaft origin, semantic parent and local axis |
| Knob drifts under automation | Incremental transforms instead of rest-based absolute mapping |
| Editing spins the whole amp | Orbit handler started before control capture/disable |
| Clicking is frustrating | Missing/undersized proxies, camera/canvas coordinate mismatch |
| Hundreds of runtime nodes | Grip ribs, ticks and source construction leaked into export |
| Slow editor opening | GLB parse time, decoded textures, resource copies and frontend startup measured separately |
| GPU busy while idle | Unconditional loop, damping never settles, redundant invalidations |
| DAW disagrees with visuals | Frontend defaults overwrite host state or initial properties/state never synchronized |
| Strange automation | Nested/missing begin/end gestures or unsnapped choices |
| Impossible power/channel state | Separate authorities for one physical three-state switch |
| High/low jacks disagree | Independent booleans instead of one input choice |
| Pulling a knob changes its setting | Rotation and pull share one transform/controller instead of parent/child state |
| Coupled levers disagree | Duplicate parameters or local visual state instead of multiple subscribers to one binding |
| Blender/runtime material mismatch | Unsupported graph, missing bake, wrong texture channels/color space |
| Chrome looks black | No useful runtime environment reflections |
| Grille flicker/moiré | Fine weave signal, alpha sorting, sampling/mip behavior |
| Chrome browser works, plugin fails | Backend support, packaged routes/MIME, CSP or missing local decoder; test actual WebView |
| Grille/labels disappear only in plugin | Embedded image `blob:` URLs blocked by CSP; inspect console before editing the GLB |

## Acceptance and sources

Use the [runtime QA checklist/report](../../guitar-gear-qa/references/runtime-qa.md) for before/after asset metrics, every discrete state, visual automation playback, editor/plugin/DAW restore and 1/5/10-instance measurements. Preserve existing knob bindings, camera presets, mock mode and embedded mode. Do not claim visual restore from a C++ serialization test alone.

API guidance checked against JUCE 9.0.1 and Three.js documentation; inspect pinned project versions before copying APIs. References: [JUCE WebSliderRelay](https://docs.juce.com/master/classjuce_1_1WebSliderRelay.html), [Three.js rendering on demand](https://threejs.org/manual/en/rendering-on-demand.html), [resource disposal](https://threejs.org/manual/en/how-to-dispose-of-objects.html), [GLTFLoader](https://threejs.org/docs/#GLTFLoader). Three-position selection, physical jack choice, pull/rotate controls and multiple mechanical subscribers have been exercised across real plugin implementations; adapt the pattern to the target product rather than treating any one state table as universal. Cable dragging and optional tube-heater glow remain recommendations until the target product implements and validates them.
