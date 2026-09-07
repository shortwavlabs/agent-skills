# WebView UIs (JUCE 9)

Use WebBrowserComponent for an existing web frontend or a requested web-based plugin editor. Plain JS, React, Vue and Svelte use the same bridge. For Blender/GLB guitar-gear controls, read [Three.js runtime architecture](threejs-webview-ui.md); keep platform and bridge mechanics here.

Examples target installed JUCE 9.0.1 APIs. Inspect the project's JUCE version, `juce_WebBrowserComponent.h`, WebControlRelays/WebControlParameterAttachments headers, frontend package and `docs/CMake API.md` before adapting them. JUCE 8 introduced modern integration; old snippets may have incompatible signatures and frontend paths.

## CMake and WebView2

JUCE 9.0.1 requires CMake 3.22 or newer. In the existing target declaration enable `NEEDS_WEB_BROWSER TRUE` (including Linux WebKit linkage) and `NEEDS_WEBVIEW2 TRUE` for Windows. Replace a native-editor target's `JUCE_WEB_BROWSER=0` with `JUCE_WEB_BROWSER=1`; do not define both.

```cmake
target_compile_definitions(MyPlugin PUBLIC JUCE_WEB_BROWSER=1)
if(WIN32)
    target_compile_definitions(MyPlugin PUBLIC
        JUCE_USE_WIN_WEBVIEW2_WITH_STATIC_LINKING=1)
endif()
target_link_libraries(MyPlugin PRIVATE juce::juce_gui_extra)
```

Static loader linking enables `JUCE_USE_WIN_WEBVIEW2` in the installed module header. If choosing dynamic loader linking instead, enable `JUCE_USE_WIN_WEBVIEW2=1` and package the appropriate loader DLL. Neither loader includes the WebView2 browser runtime.

JUCE CMake searches the NuGet package directory. For a nonstandard location set `JUCE_WEBVIEW2_PACKAGE_LOCATION` before adding JUCE; in 9.0.1 it names the parent containing the `*Microsoft.Web.WebView2*` package directory, not an arbitrary include path. Inspect the pinned CMake implementation if discovery fails. Detect the browser runtime and document its prerequisite or the product's supported installer path; test on a clean Windows system. Do not silently fall back to the legacy browser for WebGL.

Select `Options::Backend::webview2` on Windows and set `WinWebView2::withUserDataFolder()` to a writable product-specific directory outside the plugin bundle. Establish compatible folder/options behavior across instances/processes; avoid creating a permanent profile on every editor reopen. Use `areOptionsSupported()` to report unavailable options. macOS uses system WebKit; Linux requires the WebKitGTK dependencies for the installed JUCE version (9.0.1 uses WebKit2GTK 4.1). Validate each backend rather than assuming Chrome behavior transfers.

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

## Frontend package and state

JUCE 9.0.1 includes `modules/juce_gui_extra/native/typescript/webview-interop` and the `@juce-framework/webview` package. Pin a compatible package in the frontend lockfile. Earlier versions used `native/javascript`; do not copy an obsolete `index.js` path or one file with unresolved imports.

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

| Resource | MIME |
|---|---|
| HTML | `text/html` |
| JS / CSS | `text/javascript` / `text/css` |
| GLB / JSON | `model/gltf-binary` / `application/json` |
| PNG / JPEG / WASM | `image/png` / `image/jpeg` / `application/wasm` |

Serve `/` as the entry HTML; use an explicit route map and return `std::nullopt` for unknown resources. Package fonts, environments, textures and optional KTX2/Draco decoder/transcoder assets locally. Production must not require CDN imports, remote GLBs or localhost. Verify with the server stopped and networking unavailable.

Make dev-server loading an explicit build option, default OFF, independent of Debug/Release. Development can use Vite/esbuild in a normal browser with mocks or a native WebView at `http://127.0.0.1:5173/`. If that page needs native resources, `withResourceProvider(provider, origin)` takes one optional origin string, such as `http://127.0.0.1:5173`, not a StringArray. Keep the origin allowance out of production. Production navigates to `getResourceProviderRoot()`.

Preserve a scoped CSP. GLB embedded images commonly decode through `blob:` URLs: permit `blob:` in `img-src` when required. Allow only schemes/sources actually used for images, local fetches and optional workers/decoders. Missing grille or face graphics with an otherwise loaded model warrants CSP/console/resource inspection before rebaking. Do not disable CSP globally.

## Streaming visual data

Never access WebView from `processBlock()`. Publish reduced meter/spectrum state through atomics or a lock-free queue. A message-thread timer snapshots it, builds a payload and sends only while visible at an appropriate rate (for example 30 Hz for meters); stop with editor destruction. See [audio-thread safety](audio-thread-safety.md). Attachments remain authoritative for controls; custom events carry non-parameter visual data. Do not serialize every audio block or continuously render a static panel.

## Sources and verification

Checked against JUCE 9.0.1 headers, frontend source and CMake documentation. Verify against each product's pinned version; Windows availability needs a Windows test.

- [JUCE CMake API](https://github.com/juce-framework/JUCE/blob/master/docs/CMake%20API.md)
- [WebBrowserComponent](https://docs.juce.com/master/classjuce_1_1WebBrowserComponent.html)
- [WebSliderRelay](https://docs.juce.com/master/classjuce_1_1WebSliderRelay.html)
- [WebSliderParameterAttachment](https://docs.juce.com/master/classjuce_1_1WebSliderParameterAttachment.html)
- [JUCE 8 WebView introduction](https://juce.com/blog/juce-8-feature-overview-webview-uis/) for historical context, not current signature authority.
