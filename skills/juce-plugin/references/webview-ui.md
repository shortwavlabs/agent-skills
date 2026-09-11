# WebView UIs (JUCE 9)

Use WebBrowserComponent for an existing web frontend or a requested web-based plugin editor. Plain JS, React, Vue and Svelte use the same bridge. For Blender/GLB guitar-gear controls, read [Three.js runtime architecture](threejs-webview-ui.md); keep platform and bridge mechanics here.

## Compatibility baseline

All concrete API examples below target JUCE 9.0.1, not an unversioned promise. Inspect the pinned project's headers (`juce_WebBrowserComponent.h`, `juce_WebControlRelays.h`, `juce_ParameterAttachments.h/.cpp`), frontend package and `docs/CMake API.md` before adapting them. Keep version-sensitive platform assumptions here.

| Area | For JUCE 9.0.1 | Recheck for another version/target |
|---|---|---|
| Build | CMake minimum 3.22; browser targets use `NEEDS_WEB_BROWSER` and Windows WebView2 targets use `NEEDS_WEBVIEW2` | CMake minimum, package discovery and module flags |
| Windows | Explicit `Backend::webview2`; static-loader macro enables WebView2, but a browser runtime is still required | Runtime availability, loader packaging and options support |
| WebView2 package | `JUCE_WEBVIEW2_PACKAGE_LOCATION` is the parent containing the `*Microsoft.Web.WebView2*` NuGet directory | Discovery layout, supported loader architectures |
| macOS | Native backend uses system WebKit | Supported OS version, resource/CSP/WebGL behavior |
| Linux | Backend uses WebKitGTK; this release uses WebKit2GTK 4.1 dependencies | Required development/runtime packages for the pinned release/distribution |
| Frontend | `@juce-framework/webview`; bundled source under `modules/juce_gui_extra/native/typescript/webview-interop` | Matching frontend/backend protocol; older releases may use `native/javascript` |
| Slider teardown | WebSliderParameterAttachment destructor removes its listener without ending an active gesture | Destructor and relay-listener behavior before reusing the guard below |

These are source-verified compatibility facts, not claims that every platform was runtime-tested. JUCE 8 introduced modern integration; copy signatures from the pinned release, not historical tutorials.

## CMake and WebView2

Using the compatibility baseline above, in the existing target declaration enable `NEEDS_WEB_BROWSER TRUE` (including Linux WebKit linkage) and `NEEDS_WEBVIEW2 TRUE` for Windows. Replace a native-editor target's `JUCE_WEB_BROWSER=0` with `JUCE_WEB_BROWSER=1`; do not define both.

```cmake
target_compile_definitions(MyPlugin PUBLIC JUCE_WEB_BROWSER=1)
if(WIN32)
    target_compile_definitions(MyPlugin PUBLIC
        JUCE_USE_WIN_WEBVIEW2_WITH_STATIC_LINKING=1)
endif()
target_link_libraries(MyPlugin PRIVATE juce::juce_gui_extra)
```

Static loader linking enables `JUCE_USE_WIN_WEBVIEW2` in the installed module header. If choosing dynamic loader linking instead, enable `JUCE_USE_WIN_WEBVIEW2=1` and package the appropriate loader DLL. Neither loader includes the WebView2 browser runtime.

JUCE CMake searches the NuGet package directory. For a nonstandard location set `JUCE_WEBVIEW2_PACKAGE_LOCATION` before adding JUCE using the layout in the compatibility table. Inspect the pinned CMake implementation if discovery fails. Detect the browser runtime and document its prerequisite or the product's supported installer path; test on a clean Windows system. Do not silently fall back to the legacy browser for WebGL.

Select `Options::Backend::webview2` on Windows and set `WinWebView2::withUserDataFolder()` to a writable product-specific directory outside the plugin bundle. Establish compatible folder/options behavior across instances/processes; avoid creating a permanent profile on every editor reopen. Use `areOptionsSupported()` to report unavailable options. Use the platform dependencies in the compatibility table and validate each backend rather than assuming Chrome behavior transfers.

## Relays and lifetime

Relays take an identifier, not a browser argument. Declare them before the browser that consumes their options; attachments follow the browser and are destroyed before it. APVTS belongs to the longer-lived processor. One host parameter has one relay/attachment in an editor, even if multiple visual objects represent it.

Minimal embedded editor, assuming processor-owned `gain` and generated `BinaryData.h` containing `index.html` and `bundle.js`:

```cpp
#include <juce_audio_processors/juce_audio_processors.h>
#include <juce_gui_extra/juce_gui_extra.h>
#include <BinaryData.h>
#include <cstring>

class WebViewEditor final : public juce::AudioProcessorEditor
{
public:
    WebViewEditor (juce::AudioProcessor& processor,
                   juce::AudioProcessorValueTreeState& state)
        : AudioProcessorEditor (&processor),
          gainAttachment (*state.getParameter ("gain"), gainRelay)
    {
        addAndMakeVisible (browser);
        setSize (800, 600);
        browser.goToURL (juce::WebBrowserComponent::getResourceProviderRoot());
    }

    void resized() override { browser.setBounds (getLocalBounds()); }

private:
    using Browser = juce::WebBrowserComponent;

    static Browser::Resource bytes (const char* data, int size, const char* mime)
    {
        std::vector<std::byte> result (static_cast<size_t> (size));
        std::memcpy (result.data(), data, result.size());
        return { std::move (result), mime };
    }

    static std::optional<Browser::Resource> resource (const juce::String& path)
    {
        if (path == "/" || path == "/index.html")
            return bytes (BinaryData::index_html, BinaryData::index_htmlSize, "text/html");
        if (path == "/bundle.js")
            return bytes (BinaryData::bundle_js, BinaryData::bundle_jsSize, "text/javascript");
        return std::nullopt;
    }

    Browser::Options makeOptions()
    {
        auto options = Browser::Options{}
            .withNativeIntegrationEnabled()
            .withOptionsFrom (gainRelay)
            .withInitialisationData ("pluginName", "Guitar Gear")
            .withResourceProvider (resource);
       #if JUCE_WINDOWS
        options = options.withBackend (Browser::Options::Backend::webview2)
            .withWinWebView2Options (Browser::Options::WinWebView2{}
                .withUserDataFolder (juce::File::getSpecialLocation (
                    juce::File::userApplicationDataDirectory)
                    .getChildFile ("YourCompany/GuitarGear/WebView2")));
       #endif
        return options;
    }

    juce::WebSliderRelay gainRelay { "gain" };
    Browser browser { makeOptions() };
    juce::WebSliderParameterAttachment gainAttachment;
};
```

Validate IDs before dereferencing parameters registered from metadata. Add routes for CSS, GLB, camera JSON and images for the full asset. Resource is `{ std::vector<std::byte>, mimeType }`, not `{ pointer, size, mimeType }`.

Other controls use the same order: declare `juce::WebToggleButtonRelay bypassRelay { "bypass" };` or `juce::WebComboBoxRelay filterRelay { "filterType" };`, register with `withOptionsFrom()`, then construct `WebToggleButtonParameterAttachment` or `WebComboBoxParameterAttachment` from the matching parameter and relay. A choice can also use WebSliderRelay for a shared normalized 3D binding, with explicit quantization; never reduce three states to a boolean.

## Gesture cleanup on editor destruction

This applies to any WebSliderRelay-backed web control, including flat sliders and discrete controls that use slider gestures. JS pointer/keyboard cancellation remains the primary cleanup path, but editor destruction can prevent JS unload from completing. The compatibility baseline requires an explicit native fallback.

Use the small `WebGestureGuard` in [the runnable gesture check](../scripts/webview_gesture_check.cpp). It observes relay starts/ends without sending a second begin/end during normal interaction; destruction ends only an outstanding gesture. Declare members in this order:

```cpp
juce::WebSliderRelay gainRelay { "gain" };
juce::WebBrowserComponent browser { makeOptions() };
juce::WebSliderParameterAttachment gainAttachment;
WebGestureGuard gainGestureGuard;
```

Construct the attachment with `(parameter, gainRelay)` and the guard with `(parameter, gainRelay)`. The guard dies before the attachment, browser and relay. Use the guard for each gesture-bearing parameter; do not separately register a second attachment. Toggle/combo attachments that send complete gestures do not need artificial drag state.

This is a JUCE 9.0.1 workaround verified against that implementation, not a recommended abstraction to copy unchanged across JUCE versions. The example uses relay listener hooks marked internal by JUCE; recheck them when upgrading. It assumes frontend begin/end events are balanced except for teardown; it does not make duplicate frontend starts safe. In particular, do not call its cleanup early while JS can still send an end event. Stop interaction/destroy the page as part of teardown, on the message thread.

To run its headless native test inside an existing JUCE CMake project, add:

```cmake
juce_add_console_app(WebGestureCheck
    PRODUCT_NAME "WebGestureCheck"
    NEEDS_WEB_BROWSER TRUE
    NEEDS_WEBVIEW2 TRUE)
target_sources(WebGestureCheck PRIVATE path/to/webview_gesture_check.cpp)
target_compile_features(WebGestureCheck PRIVATE cxx_std_17)
target_compile_definitions(WebGestureCheck PRIVATE JUCE_WEB_BROWSER=1)
target_link_libraries(WebGestureCheck PRIVATE juce::juce_audio_processors juce::juce_gui_extra)
```

Apply the same platform browser dependency flags as the product target. The check sends real relay events and counts host gesture notifications for normal completion, cancellation-equivalent completion, active teardown and idle teardown. It requires no browser window. Browser pointer/focus delivery and native editor lifetime still need the target-backend acceptance checks.

## Frontend package and state

Use the frontend package/source path in the compatibility table and pin a compatible package in the frontend lockfile. Do not copy an obsolete `index.js` path or one file with unresolved imports.

```js
import * as Juce from '@juce-framework/webview';

const gain = Juce.getSliderState('gain');
const listener = gain.valueChangedEvent.addListener(() => {
  console.log(gain.getNormalisedValue());
});
// A discrete edit; a drag begins once, updates many times, then ends once.
gain.sliderDragStarted();
gain.setNormalisedValue(0.75);
gain.sliderDragEnded();
// At component/page teardown:
gain.valueChangedEvent.removeListener(listener);
```

Listen to `propertiesChangedEvent` as well as value changes: initial range/name properties can change normalized readings. Subscribe before applying visuals, request current attachment state and never initialize APVTS from frontend defaults. Use the mock/JUCE adapter and startup handshake in [the runtime reference](threejs-webview-ui.md#state-ownership-and-runtime-structure). Missing native integration is not a functioning mock parameter store by itself.

Other frontend APIs: `getToggleState(id)` with `getValue()/setValue()`, and `getComboBoxState(id)` with `getChoiceIndex()/setChoiceIndex()`. Subscribe/remove listeners on the same lifecycle. `getBackendResourceAddress('assets/gear.glb')` resolves the provider address without hardcoding platform URL schemes.

## Native functions and events

`withNativeFunction(name, callback)` supplies arguments and a completion callable. Validate arguments and complete exactly once; use it for discrete requests such as preset loading or initial-state sync, not a second parameter transport. JS awaits `Juce.getNativeFunction('loadPreset')(index)`. Do not capture an editor past its lifetime in async work.

C++ listens through `withEventListener('uiReady', callback)`; JS emits through `window.__JUCE__.backend.emitEvent('uiReady', {})` after confirming the native bridge. C++ sends `emitEventIfBrowserIsVisible()` to frontend backend listeners. `withInitialisationData(name, value)` takes a name/value pair; inspect the frontend's initialization-data representation instead of assuming a flat object. Use `withUserScript()` for early scripts when needed.

## React integration

Keep one slider state per control, subscribe in an effect, apply its current value after subscribing and remove listener IDs in cleanup. Pointerdown captures and begins one gesture; input/move only updates. One idempotent handler ends on pointerup/cancel/lost capture/blur/unmount. Keyboard edits need correctly bracketed gestures too. Do not begin/end on every `onChange` while also beginning on mouse/pointerdown: that nests automation gestures. This lifecycle also applies to plain DOM controls.

## Local resources and development mode

Build the frontend before BinaryData generation. Declare HTML/JS/CSS/GLB/camera outputs and source dependencies in CMake so edits rebuild the package. Use `juce_add_binary_data` and link its target into the plugin. Large GLBs are binary resources, never Base64 inside JS. Fixed filenames or a generated manifest keep provider routes aligned with bundled output.

Treat `dist` as generated and do not commit it by default, but preserve an existing intentional committed-`dist` workflow when the repository or deployment process relies on it. Do not reorganize that convention merely to integrate the WebView. In either case, make clean local builds and CI run or verify the frontend build before native BinaryData compilation. List every embedded output and its source/asset dependency so changing an SVG, GLB, camera file or stylesheet invalidates the custom command. A browser dev-server preview is not evidence that the standalone/plugin contains the same build; verify a known visible asset change in the packaged editor when stale output is suspected.

| Resource | MIME |
|---|---|
| HTML | `text/html` |
| JS / CSS | `text/javascript` / `text/css` |
| GLB / JSON | `model/gltf-binary` / `application/json` |
| PNG / JPEG / WASM | `image/png` / `image/jpeg` / `application/wasm` |

Serve `/` as the entry HTML; use an explicit route map and return `std::nullopt` for unknown resources. Package fonts, environments, textures and optional KTX2/Draco decoder/transcoder assets locally. Production must not require CDN imports, remote GLBs or localhost. Verify with the server stopped and networking unavailable.

Make dev-server loading an explicit build option, default OFF, independent of Debug/Release. Development can use Vite/esbuild in a normal browser with mocks or a native WebView at `http://127.0.0.1:5173/`. If that page needs native resources, `withResourceProvider(provider, origin)` takes one optional origin string, such as `http://127.0.0.1:5173`, not a StringArray. Keep the origin allowance out of production. Production navigates to `getResourceProviderRoot()`.

Test layout and rasterization in the actual system WebKit/WebView2 backend. For SVG/image branding, start by preserving intrinsic aspect ratio with one explicit dimension and `height: auto` (or an equivalent contained box), then inspect the SVG `viewBox`/whitespace. If a backend-specific optical correction remains necessary, scope and document it rather than silently stretching every image. A correct result in Chromium can still expose stale embedded assets or backend-specific sizing in the plugin.

Preserve a scoped CSP. GLB embedded images commonly decode through `blob:` URLs: permit `blob:` in `img-src` when required. Allow only schemes/sources actually used for images, local fetches and optional workers/decoders. Missing grille or face graphics with an otherwise loaded model warrants CSP/console/resource inspection before rebaking. Do not disable CSP globally.

A conservative production policy for external bundled JS/CSS and GLB images is:

```html
<meta http-equiv="Content-Security-Policy"
      content="default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' blob:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'">
```

Place it before page scripts/styles. This baseline assumes same-origin provider resources and no inline code, workers or decoder WASM. Test it inside each supported WebView: if a backend exposes assets at a distinct origin, add that exact resource origin to the relevant directive, not a wildcard. Add `data:` images or worker/WASM permissions only when the actual pipeline requires them. Development HMR permissions belong only in the development policy. Verify model load, embedded image decode, initial parameter sync and offline reopen with the final policy.

The sample `bytes()` helper allocates/copies the entire resource on each request. A 20 MiB GLB means another 20 MiB copy before browser parsing/decoded images; BinaryData delivery is not free. Count requests and measure provider-copy time, load time and peak memory separately. Load a model once per viewer and prevent repeated effect/mount fetches. Reuse parsed assets within a live viewer where ownership permits; cache decompression/route work only when measured. Returning an owning Resource still requires owned bytes: returning a cached vector by value can copy again. Do not assume HTTP caching or cross-WebView sharing eliminates this cost.

## Streaming visual data

Never access WebView from `processBlock()`. Publish reduced meter/spectrum state through atomics or a lock-free queue. A message-thread timer snapshots it, builds a payload and sends only while visible at an appropriate rate (for example 30 Hz for meters); stop with editor destruction. See [audio-thread safety](audio-thread-safety.md). Attachments remain authoritative for controls; custom events carry non-parameter visual data. Do not serialize every audio block or continuously render a static panel.

## Sources and verification

Checked against JUCE 9.0.1 headers, frontend source and CMake documentation. Verify against each product's pinned version; Windows availability needs a Windows test.

- [JUCE CMake API](https://github.com/juce-framework/JUCE/blob/master/docs/CMake%20API.md)
- [WebBrowserComponent](https://docs.juce.com/master/classjuce_1_1WebBrowserComponent.html)
- [WebSliderRelay](https://docs.juce.com/master/classjuce_1_1WebSliderRelay.html)
- [WebSliderParameterAttachment](https://docs.juce.com/master/classjuce_1_1WebSliderParameterAttachment.html)
- [JUCE 8 WebView introduction](https://juce.com/blog/juce-8-feature-overview-webview-uis/) for historical context, not current signature authority.
