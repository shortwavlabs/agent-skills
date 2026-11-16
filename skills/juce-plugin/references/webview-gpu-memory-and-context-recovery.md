# WebView GPU Memory and WebGL Context Recovery

How to measure what a WebGL editor really costs in WebKit, how to release CPU copies of data the GPU already holds, and how to keep the editor recoverable after a WebGL context loss once those copies are gone. Use it after [rendering and lifetime](threejs-webview-ui.md#rendering-threading-and-lifetime) are in place and a memory problem has been measured, not before.

**Evidence base.** One product (the Prismatica case study: a three.js 0.185.1 pedal editor in a JUCE 9 WKWebView; historical sources: its `plugin/web/src/scene.ts` and `main.ts`, and its `docs/ui/ui-b3o-*` and `ui-b3or1-*` reports. The snippets below are self-contained and need none of them), macOS 26 on Apple silicon, one machine, debug and release VST3/AU builds. Context losses were forced with `WEBGL_lose_context`. WebView2 and WebKitGTK were not measured. Each statement below is marked as one of:

| Label | Meaning |
|---|---|
| **Validated** | implemented and qualified in the case study (byte-identical views, host tests) |
| **Case-study choice** | a value or design that worked there; adapt it, do not copy it as a rule |
| **Untested** | reasoned from the source code, not exercised |
| **Rejected** | tried or analysed and turned down, with the reason |
| **Limitation** | a known gap in the evidence |

## Contents

- [Measure memory the way WebKit spends it](#measure-memory-the-way-webkit-spends-it)
- [Release decoded images after upload](#release-decoded-images-after-upload)
- [Release vertex arrays after upload](#release-vertex-arrays-after-upload)
- [WebGL context loss and recovery](#webgl-context-loss-and-recovery)
- [Separate phenomena](#separate-phenomena)
- [Rejected approaches and attribution lessons](#rejected-approaches-and-attribution-lessons)
- [Acceptance checklist](#acceptance-checklist)

## Measure memory the way WebKit spends it

**RSS is not enough.** A WebGL page's largest allocations are GPU-private surfaces (textures, render targets, shadow maps). On macOS they appear in the physical footprint as "Owned physical footprint (unmapped) (graphics)" and barely move RSS. In the case study, removing two 32 MB shadow maps moved helper RSS by about 10 MB and the footprint by 80 MB.

| Measure | What it shows | Tool |
|---|---|---|
| RSS | mapped resident pages; misses GPU-private memory | `ps -o rss` |
| Physical footprint | what the OS charges the process, including the graphics line | `footprint <pid>` |
| Graphics line | GPU-private allocations charged to that process | `footprint`, "(graphics)" |
| WebContent process | the page: JS heap, decoded images, its share of GPU surfaces | per process id |
| GPU process | WebKit's shared GPU process: textures, render targets, compositing | per process id |
| Networking process | small and steady; count it, do not attribute to the page | per process id |

- **Sum the footprint of every WebKit helper** (WebContent, GPU, Networking) by process id and report the sum per editor. The split between WebContent and GPU process can double-charge one surface: freeing the decoded images lowered both by about 174 MB, the size of the decoded copies. Do not add the two halves as separate savings.
- **Compare builds alternately in one session.** A, B, A, B, with a fresh host process per run, the same window size and the same sampling time. Cross-session comparisons drift: in the case study the host's callback p50 rose by about 1.3 points between two sessions, for both builds alike.
- **Measure an editor ladder** (1, 4 and 8 editors where several are supported). Shared GPU-process memory makes the total non-linear.
- **Take a series, not only a snapshot.** Sample every 2–3 s. The GPU process held about 480 MB for about 10 s after a load and then trimmed to about 275 MB; a snapshot inside that window reads 200 MB high.
- **Record garbage-collection variability.** Other WebContent memory (JS heap, malloc) swung by up to 190 MB between otherwise identical variants.
- **Measure in visible, unlocked sessions** and record the session state with every row ([windowed lifecycle testing](webview-ui.md#windowed-lifecycle-and-visible-window-testing)). Keep the editor windows unoccluded and check it per row; with the screen locked and the display asleep WebKit stops rendering the page.
- **Separate steady state from transients.** A reload or first load peaks well above steady state for a few seconds (below). Report both.
- **Preserve and repeat outliers.** One four-editor run in the case study measured the GPU process at 779 MB against 315–329 MB in the other three. Four further runs did not reproduce it; it stays unexplained, not resolved.

**Case-study results** (Prismatica measurements on the tested machine; not expectations for another plug-in):

| Finding | Result |
|---|---|
| Approved page, 1 editor (summed helper footprint) | about 1.33 GB |
| Both releases below plus recovery, 1 editor, same session | about 1.04 GB (median 1,037 vs 1,331 MB) |
| Net saving | about 294 MB (22 %) |
| 8 editors, the same two releases without recovery | 8,435 / 8,397 → 6,065 / 6,090 MB (about −28 %) |
| Recovery reload transient | about +600 MB for under 2.5 s, then about +150–270 MB (mostly the GPU process) for about 10 s |
| Repeated recovery | no accumulation over 5 cycles and two 8 s losses, same WebContent process |
| Visual fidelity | 45 / 45 WKWebView views byte-identical to the approved page |

## Release decoded images after upload

**Problem.** After three.js uploads a texture, the decoded image it uploaded from stays referenced by `texture.source.data`. For a GLB with large PBR maps that copy is held in WebKit's memory for the editor's whole life.

**Conditions.** The decoded image is an `ImageBitmap` (three 0.185.1's GLTFLoader uses `ImageBitmapLoader` whenever `createImageBitmap` exists, except for user agents it identifies as Safari < 17 or Firefox < 98; check `texture.source.data instanceof ImageBitmap` in your target WebView). Where it is an `HTMLImageElement`, `close` does not exist and nothing is freed.

**Mechanism** (three.js 0.185.1, `WebGLTextures.uploadTexture`):
- three keeps one WebGL texture per `Source` **and texture-parameter cache key**: wrap modes, filters, anisotropy, internal format, format, type, mipmap generation, premultiply-alpha, flip-Y, unpack alignment and colour space.
- It uploads from `source.data` when the source version changes or a new cache key appears, then calls `texture.onUpdate(texture)`. `texImage2D` has copied the pixels by then, so the bitmap is no longer needed **for that upload**.
- GLTFLoader caches one `Texture` per image and sampler. It clones (sharing the same `Source`) for a different sampler, `texCoord > 0` or `KHR_texture_transform`. A clone with a different cache key needs a second upload from the same `Source`.

**Safe implementation (Validated, under these preconditions):**
- each `Source` reaches the GPU under exactly one cache key (audit the GLB: images, textures, samplers, `texCoord`, texture transforms);
- every cache-key field is set before the first render and never changed afterwards;
- nothing sets `texture.needsUpdate` or `source.needsUpdate` later;
- nothing else reads the pixels (CPU sampling, canvas copies, a second renderer or WebView);
- a recovery strategy that does not need three to re-upload exists ([below](#webgl-context-loss-and-recovery)).

```ts
// Shipped in the case study (three 0.185.1), run on the loaded glTF scene before the first render.
// Valid there: 15 images, 24 glTF textures, 1 sampler, no texCoord > 0, no texture transforms,
// so GLTFLoader returns one Texture (one Source, one cache key) per image.
gltf.scene.traverse((node) => {
  if (!(node instanceof Mesh)) return;
  for (const material of Array.isArray(node.material) ? node.material : [node.material])
    for (const value of Object.values(material))
      if ((value as Texture)?.isTexture)
        (value as Texture).onUpdate = (t: Texture) => (t.source.data as { close?: () => void })?.close?.();
});
```

**Shared sources under several cache keys (Untested).** Close only after the last cache key has uploaded: count, per `Source`, the distinct cache keys that will be used, and close in the `onUpdate` that brings the count to zero. Better still, make the textures share one cache key, or leave that source open.

**Verification:**
- the audit above, recorded with the asset hash;
- the summed helper footprint, alternating with and without the release; the graphics line should fall by about the decoded size;
- a byte-identical (or thresholded, if pixels may change) view comparison in the real WebView, at the closest zoom and largest size, covering every material;
- no console errors; `renderer.info.memory.textures` unchanged.

**Failure modes.** A texture closed before its upload renders black or blank. A second cache key, a later `needsUpdate` or a changed sampler re-uploads from a closed bitmap. A context restore makes three re-upload everything: blank or broken textures.

**Evidence.** Footprint 1,320–1,333 → 1,026–1,037 MB per editor (−296 MB median); graphics −349 MB; 45 / 45 views byte-identical; load time unchanged.

**When not to use it.** When the editor relies on three's in-place context restore; when textures are re-parameterised, streamed or updated at run time; when several renderers or WebViews share a texture; when the decoded images are small enough that the saving does not matter.

## Release vertex arrays after upload

**Problem.** GLTFLoader builds each `BufferAttribute` as a typed-array **view** into the GLB's single binary `ArrayBuffer`. One surviving view keeps the whole buffer alive (39 MB in the case study), even when the view itself covers a few kilobytes.

**Safe implementation (Validated, in this order):**
1. Compute what needs CPU positions **first**: bounding boxes and spheres (frustum culling, placement of anything derived from bounds).
2. Give every mesh that is raycast against (hit proxies, picking targets) an **independent** copy: `attribute.array = attribute.array.slice()`. A copy owns its own small buffer and does not pin the GLB.
3. For every other non-interleaved attribute and index, drop the array once three has uploaded it: three's documented `onUpload` hook.

```ts
// Shipped in the case study (three 0.185.1), before the first render. Interleaved attributes are
// skipped (they share one InterleavedBuffer); morph targets and skinning were not present.
gltf.scene.traverse((node) => {
  if (!(node instanceof Mesh)) return;
  const g = node.geometry as BufferGeometry;
  g.computeBoundingBox(); g.computeBoundingSphere();
  const attributes = [...Object.values(g.attributes), ...(g.index ? [g.index] : [])]
    .filter((a) => !(a as InterleavedBufferAttribute).isInterleavedBufferAttribute) as BufferAttribute[];
  if (node.name.startsWith('HIT_')) for (const a of attributes) a.array = a.array.slice();
  else for (const a of attributes) a.onUpload(function (this: BufferAttribute) { (this as { array: unknown }).array = null; });
});
```

**What breaks after release:** raycasting and CPU picking on released meshes; `computeBoundingBox`/`computeBoundingSphere`, `computeVertexNormals` and tangents; `clone`, `toJSON`, merging; any later `needsUpdate` on the attribute; CPU morph or skinning work; and a context restore (`TypeError: null is not an object (evaluating 'c.byteLength')` in WKWebView).

**Measuring it.** Footprint per editor, alternating: −40 MB alone in the case study, and the GLB's 39 MB buffer no longer pinned. Check that hit-testing still works on every proxy and that no geometry is missing at any camera preset.

**Limitation.** Interleaved, morphed and skinned attributes were not exercised.

**Pair it with a recovery strategy.** Both releases remove the CPU sources three needs to restore a context in place. Use them only with a recovery that rebuilds from the original assets, or document the editor as unrecoverable after a loss.

## WebGL context loss and recovery

**Do not assume three.js recovers in place.** In the case study the approved page, with no resources released, did **not** recover correctly from a forced loss:
- three re-initialised its GL state on `webglcontextrestored`;
- it did not rebuild the custom PMREM environment, the reflection probes or the cached shadow maps;
- after a redraw the environment and probe reflections were black, and 8 forced views differed from the approved image on 86–98 % of pixels.

With the decoded images and vertex arrays released, three's restore path threw on the freed data, and the editor stayed blank. A page that pre-renders derived GPU state (environment maps, probes, baked or cached shadows, render-target caches) needs its own rebuild.

**Options considered:**

| Option | Decision |
|---|---|
| Rebuild renderer and assets in place | **Rejected:** costs the same as a reload (GLB and HDRI fetch, decode, upload, environment, probes, shadows), and every subsystem holding scene references (controls, hit-testing, meter, camera UI) must be re-wired and guarded |
| Keep the CPU sources so three can restore | **Rejected:** gives back the memory saving, and three still does not rebuild derived state |
| **Guarded page reload** | **Validated:** reuses the page's own startup path, which is already the qualified path |

**The sequence (Validated; the values are case-study choices):**
1. Listen for `webglcontextlost` on the canvas and call `event.preventDefault()`, which tells the browser a restore is wanted.
2. Enter a `lost` state and stop scheduling frames (no render touches the invalid context). Show a short status.
3. Start a timeout (10 s in the case study). Whichever comes first, `webglcontextrestored` or the timeout, leaves `lost`; the other becomes a no-op. One recovery per loss.
4. Check the reload guard (below). If it refuses, show a manual instruction and stop.
5. Save transient presentation state, such as the camera, to `sessionStorage`. It is not plug-in state; never add it to the serialized processor state.
6. `location.reload()`. The old document's `pagehide` disposes its subscriptions, ends open gestures and stops timers.
7. The new document starts exactly like a freshly opened editor: assets load, the environment, probes and shadows are rebuilt, the decoded images and vertex arrays are released again.
8. It asks the processor for every value (for example a native `requestParameterSync` that calls each attachment's `sendInitialUpdate()`; [state ownership](threejs-webview-ui.md#state-ownership-and-runtime-structure)), the preset list and current program, and the meter status.
9. It restores the saved camera once and deletes it.

```ts
// Case-study guard: at most 3 reloads in 60 s per WebView session. No sessionStorage means no guard,
// so no reload: the editor shows the manual instruction instead of risking a loop.
const RECOVERY_KEY = 'app.graphicsRecovery', CAMERA_KEY = 'app.camera';
function guardedReload(scene: Scene) {
  try {
    const now = Date.now();
    const log = (JSON.parse(sessionStorage.getItem(RECOVERY_KEY) || '[]') as number[]).filter((t) => now - t < 60000);
    if (log.length >= 3) { scene.fail(); return; }        // 'Graphics context lost. Close and reopen this editor.'
    sessionStorage.setItem(RECOVERY_KEY, JSON.stringify([...log, now]));
    sessionStorage.setItem(CAMERA_KEY, JSON.stringify(scene.cameraState()));
  } catch { scene.fail(); return; }
  location.reload();
}
```

**States.** `initializing → ready → lost → recovering → (reload)`, plus `failed` (manual reopen) and `disposed` (page hide or editor close). The loss handler ignores events in `disposed` and `failed`; recovery acts only from `lost`; disposal clears the timer and removes the listeners. A reload discards the old document, so no old callback can reach a new renderer.

**Host safety.** The processor stays authoritative:
- **The reload must send nothing.** The new page reads values; it never writes defaults or remembered values. Verify that the host's end state equals what the host set, with non-default values, through two losses.
- **Automation during recovery.** Drive every parameter from the host through the losses; after recovery, page = host for every parameter.
- **Presets.** Read the current program from the host after the reload; a host program change during a loss must show up.
- **Gestures.** A gesture open at the loss must end exactly once. In the case study the page's `pagehide` disposal ended it: the host saw 1 begin and 1 end, the end at the reload. `pagehide` is a page event, so test it on every backend; keep the [native gesture cleanup](webview-ui.md#gesture-cleanup-on-editor-destruction) for editor destruction as well.
- **Several editors.** Each WebView has its own `sessionStorage` and guard; every editor recovered independently with 2 and 4 instances open.
- **Closing during a loss or a reload.** 20 / 20 closes in each phase left no WebContent process alive.
- **Reopen after `failed`.** A reopened editor is a new WebView session with a clean guard.

**Evidence (case study).** Every forced loss recovered without reopening the editor; 45 / 45 views byte-identical after recovery; camera exact; 10.0 s timeout reload; the guard stopped at the fourth loss inside 60 s; meter and preset resumed; minimize, hide, display sleep and a lock / unlock caused no context loss at all.

**Adapting it.** Choose the timeout, guard counts and message for the product. Carry only presentation state. If startup is slow, the reload is a visible blank for that long; measure it. Budget the reload transient (about +600 MB for under 2.5 s in the case study) when several editors may recover at once (four at once peaked at 3,867 MB helper RSS against 3,435–3,535 MB idle).

**Limitations.** Only forced losses were tested: a real GPU reset was not produced, and WebKit helper processes must never be killed to provoke one. The forced losses ran in debug builds. A lock of several minutes with the display asleep, and display disconnect, were not covered.

## Separate phenomena

Keep these apart in reports and fixes:
- **[Locked-screen WebKit helper accumulation](webview-ui.md#windowed-lifecycle-and-visible-window-testing):** WebKit keeps closed views' WebContent processes while the display is asleep and the screen locked. Releasing decoded images does not touch it, and context recovery does not fix it.
- **[JUCE 9.0.3 native-integration retention](webview-ui.md#wkwebview-teardown-on-macos-juce-903):** a small in-process leak per closed editor, fixed by removing the script handler. Context recovery does not fix it.
- **Resource retention (this reference):** CPU copies of uploaded data held for an open editor's lifetime.

## Rejected approaches and attribution lessons

Recorded so the next agent does not repeat them without new evidence. Each was judged against byte-identical (class A) or thresholded (class B) WKWebView views ([comparison classes](../../guitar-gear-qa/references/visual-oracle.md#comparison-classes), [performance candidates](../../guitar-gear-qa/references/runtime-qa.md#performance-candidates-that-can-change-appearance)).

| Candidate | Outcome | Lesson |
|---|---|---|
| Remove reflection probes (attribution) | load 672 → 358 ms, but the first render was only ~118 ms earlier | The first probe bake (314–326 ms) was mostly first-use shader compilation and upload; a second bake took 22–24 ms. Separate work **eliminated** from work **moved** to the first frame |
| Half-size base colour and normal maps for four low-information images | **Rejected:** the ivory stripe's edge where it wraps onto the sides softened (13 views) | Region-specific close-ups at the largest size and closest zoom catch what full views miss |
| The same without the enclosure base colour | **Rejected:** the enclosure normal shapes the knob top-edge highlight band; the ivory diagonal moved (3 views) | A normal map can carry a highlight no base-colour check sees |
| No shadow map for a 0.06-intensity fill light | **Rejected:** contact shadows around raised details at the closest zoom (4 views) | A weak light can still own the contact shadows |
| Half-resolution transmission target for the LED glass | **Rejected:** LED lens and nearby views (27 views) | — |
| Build the studio environment once instead of twice; ask for host values during the GLB load | **Rejected:** no measured gain (the first frame was not earlier) | Measure before keeping even an obviously redundant step's removal |
| Geometry reduction (an earlier asset) | **Rejected** after it passed position audits within 11 µm | Edge collapse minimises positional error and ignores shading normals: interpolated fillet tilt across large triangles left a dark band on knob skirts and fine lines on knob flutes at the closest zoom. Audit normals at points **inside** faces, not only at corners, and reduce per part family; a global triangle target can damage exactly the glossy parts that matter ([geometry fidelity](../../guitar-gear-modeling/references/runtime-derivative-and-geometry-fidelity.md)) |
| The ~200 ms "first orbit stall" | a **harness artefact** | It was the first animation frame after ~90 synchronous `gl.finish()` measurement frames. A user's first orbit measured 18–22 ms. Synchronous GPU waits distort the frames that follow them |
| LED glass (`KHR_materials_transmission`) | **unresolved trade-off** | It costs about 77 MB and a second opaque pass (draw calls 80 → 40 without it), but cheaper techniques visibly changed the approved look. An owner decision, not an optimization |
| GPU-compressed textures (KTX2 with raw ASTC) | **not built** (architectural; owner decision) | Estimated about −180 MB per editor; needs an encoder, a loader, a larger asset and a backend check |

## Acceptance checklist

- [ ] Memory measured as summed helper footprint, alternating builds, editor ladder, series around the sampling time, visible session recorded.
- [ ] GLB audited for shared sources and cache keys before releasing images; hit and picking meshes identified before releasing arrays.
- [ ] Byte-identical (or thresholded) views in the real WebView before and after each release, including the closest zoom and largest editor size.
- [ ] Forced context loss with the release in place: recovery or a deliberate, documented manual fallback; no loop; camera, parameters, preset, meter and gestures checked against the host.
- [ ] Close during loss and during recovery, reopen after failure, several editors, automation through the loss.
- [ ] Repeated recovery with a footprint series: no accumulation, transient recorded.
- [ ] Real-time and host gates unchanged; failed and harness-fault runs preserved and classified.
