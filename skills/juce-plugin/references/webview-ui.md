# WebView UIs (JUCE 8)

JUCE 8 supports building plugin UIs with web technologies — React, Vue, Svelte, or plain HTML/CSS/JS — via an enhanced `WebBrowserComponent`. This enables hot reloading, mature web frameworks, and cross-platform hardware-accelerated graphics (WebGL).

The native browser components are: WebKit on macOS/iOS, Edge (Chromium) on Windows, GTK WebKit2 on Linux.

Source: [JUCE 8 Feature Overview: WebView UIs](https://juce.com/blog/juce-8-feature-overview-webview-uis/)

## CMake Setup

```cmake
juce_add_plugin(MyPlugin
    ...
    NEEDS_WEBVIEW2 TRUE)   # Required on Windows; JUCE searches for WebView2 NuGet package

target_compile_definitions(MyPlugin PUBLIC
    JUCE_WEB_BROWSER=1                             # On by default, but be explicit
    JUCE_USE_WIN_WEBVIEW2_WITH_STATIC_LINKING=1)   # Windows best practice
```

If the WebView2 NuGet package is in a non-standard location:
```cmake
set(JUCE_WEBVIEW2_PACKAGE_LOCATION "/path/to/NuGet/package")
```

## WebBrowserComponent Options

```cpp
juce::WebBrowserComponent webComponent {
    juce::WebBrowserComponent::Options()
        // Required: enables JUCE's JS shim for C++/JS communication
        .withNativeIntegrationEnabled()

        // Windows: use webview2 backend (not the default)
        .withBackend (juce::WebBrowserComponent::Options::Backend::webview2)
        .withWinWebView2Options (
            juce::WebBrowserComponent::Options::WinWebView2{}
                .withUserDataFolder (juce::File::getSpecialLocation (
                    juce::File::tempDirectory)))

        // Pass initial data to JS (accessible via window.__JUCE__)
        .withInitialisationData ({{ "pluginName", "My Plugin" },
                                   { "version", "1.0.0" }})

        // Run JS before anything else loads
        .withUserScript ("console.log('JUCE initialized');")

        // Expose a C++ function callable from JS
        .withNativeFunction ("loadPreset",
            [this] (const auto& args, auto complete) {
                auto presetIndex = (int) args[0];
                loadPreset (presetIndex);
                complete ("Preset " + juce::String (presetIndex) + " loaded");
            })

        // Listen for a JS event from the frontend
        .withEventListener ("uiReady",
            [this] (const auto& args) {
                // Frontend is mounted and ready
            })

        // Serve resources from C++ (acts as a lightweight web server)
        .withResourceProvider (
            [this] (const juce::String& url) -> std::optional<juce::WebBrowserComponent::Resource> {
                auto path = url.toStdString();
                if (path == "/index.html") {
                    return juce::WebBrowserComponent::Resource {
                        BinaryData::index_html,
                        BinaryData::index_htmlSize,
                        "text/html"
                    };
                }
                return std::nullopt;
            },
            juce::StringArray { "localhost" })  // Allow localhost in debug
};
```

## Loading Pages

```cpp
// Debug: load from dev server (hot reloading)
webComponent.goToURL ("localhost:3000");

// Release: load from resource provider (BinaryData)
webComponent.goToURL (juce::WebBrowserComponent::getResourceProviderRoot());
```

## Parameter Attachments (C++ Side)

Web attachments connect APVTS parameters to JS state objects, just like SliderAttachment connects a parameter to a C++ Slider.

### WebSliderRelay + WebSliderParameterAttachment

```cpp
// In editor header:
juce::WebSliderRelay gainRelay;
juce::WebSliderParameterAttachment gainAttachment;

// In editor constructor:
WebViewEditor (MyProcessor& p)
    : AudioProcessorEditor (p),
      processor (p),
      gainRelay (webComponent, "gain"),
      gainAttachment (*processor.apvts.getParameter ("gain"), gainRelay, nullptr)
{
    // Pass relay options to the WebBrowserComponent
    // .withOptionsFrom (gainRelay)
}
```

### WebToggleButtonRelay + WebToggleButtonParameterAttachment

```cpp
juce::WebToggleButtonRelay bypassRelay;
juce::WebToggleButtonParameterAttachment bypassAttachment;

// Constructor:
bypassRelay (webComponent, "bypass"),
bypassAttachment (*processor.apvts.getParameter ("bypass"), bypassRelay, nullptr)
```

### WebComboBoxRelay + WebComboBoxParameterAttachment

```cpp
juce::WebComboBoxRelay filterTypeRelay;
juce::WebComboBoxParameterAttachment filterTypeAttachment;

// Constructor:
filterTypeRelay (webComponent, "filterType"),
filterTypeAttachment (*processor.apvts.getParameter ("filterType"), filterTypeRelay, nullptr)
```

## JavaScript Frontend Library

The JUCE frontend library is at `modules/juce_gui_extra/native/javascript/index.js`.

### Installation

```bash
# Copy or symlink the library into your frontend project
cp JUCE/modules/juce_gui_extra/native/javascript/index.js frontend/src/juce.js
```

### Slider State (Parameter Binding)

```js
import * as Juce from "./juce.js";

const gainState = Juce.getSliderState("gain");

// Get/set normalised value (0.0 - 1.0)
gainState.getNormalisedValue();
gainState.setNormalisedValue(0.75);

// Gesture notifications (required for host automation)
gainState.sliderDragStarted();
gainState.sliderDragEnded();

// Listen for value changes from the DAW
gainState.valueChangedEvent.addListener(() => {
    console.log("Gain changed:", gainState.getNormalisedValue());
});
```

### Toggle Button State

```js
const bypassState = Juce.getToggleButtonState("bypass");
bypassState.getToggleState();         // returns boolean
bypassState.setToggleState(true);
bypassState.valueChangedEvent.addListener(() => {
    console.log("Bypass:", bypassState.getToggleState());
});
```

### ComboBox State

```js
const filterState = Juce.getComboBoxState("filterType");
filterState.getChoiceIndex();          // returns 0-based index
filterState.setChoiceIndex(2);
filterState.valueChangedEvent.addListener(() => {
    console.log("Filter:", filterState.getChoiceIndex());
});
```

### Calling Native C++ Functions

```js
// Functions exposed via .withNativeFunction()
const loadPreset = Juce.getNativeFunction("loadPreset");
const getSpectrum = Juce.getNativeFunction("getSpectrum");

// Returns a Promise (async API)
loadPreset(45).then(result => {
    console.log(result);  // "Preset 45 loaded"
});

// Async/await pattern
const spectrum = await getSpectrum();
```

### Accessing Backend Resources

```js
// URL to reach C++ resource provider
const url = Juce.getBackendResourceAddress("spectrum.json");

// Platform-specific:
// macOS/iOS/Linux:  juce://juce.backend/spectrum.json
// Windows/Android:  https://juce.backend/spectrum.json
```

### Emitting Events to C++

```js
// C++ side listens via .withEventListener("customEvent", callback)
Juce.emitEvent("customEvent", { value: 42, label: "hello" });
```

## React Integration Pattern

The WebViewPluginDemo in JUCE uses React. The pattern:

```
frontend/
  public/
    index.html
  src/
    App.jsx           # Main plugin UI
    juce.js            # JUCE frontend library (copied from JUCE)
    components/
      GainSlider.jsx   # Parameter-bound slider component
      Spectrum.jsx     # Visualization fed from C++
  package.json
```

### React Component Example

```jsx
import { useState, useEffect } from "react";
import * as Juce from "../juce";

function GainSlider() {
    const [value, setValue] = useState(0.5);
    const [sliderState] = useState(() => Juce.getSliderState("gain"));

    useEffect(() => {
        const listenerId = sliderState.valueChangedEvent.addListener(() => {
            setValue(sliderState.getNormalisedValue());
        });
        return () => sliderState.valueChangedEvent.removeListener(listenerId);
    }, [sliderState]);

    const handleChange = (e) => {
        const normalised = e.target.value / 100;
        setValue(normalised);
        sliderState.sliderDragStarted();
        sliderState.setNormalisedValue(normalised);
        sliderState.sliderDragEnded();
    };

    return (
        <div className="slider-container">
            <label>Gain</label>
            <input
                type="range"
                min="0" max="100"
                value={value * 100}
                onChange={handleChange}
                onMouseDown={() => sliderState.sliderDragStarted()}
                onMouseUp={() => sliderState.sliderDragEnded()}
            />
        </div>
    );
}
```

## Resource Provider Pattern

In Release builds, serve frontend assets from BinaryData:

```cpp
// In CMakeLists.txt:
juce_add_binary_data(MyPluginGui
    SOURCES
        gui/index.html
        gui/bundle.js
        gui/bundle.css
        gui/assets/logo.png
)
```

```cpp
// Resource provider implementation:
.withResourceProvider ([this] (const juce::String& url)
    -> std::optional<juce::WebBrowserComponent::Resource>
{
    auto path = url.trimCharactersAtStart ("/");

    if (path == "" || path == "index.html")
        return { { BinaryData::index_html, BinaryData::index_htmlSize, "text/html" } };
    if (path == "bundle.js")
        return { { BinaryData::bundle_js, BinaryData::bundle_jsSize, "application/javascript" } };
    if (path == "bundle.css")
        return { { BinaryData::bundle_css, BinaryData::bundle_cssSize, "text/css" } };

    return std::nullopt;
})
```

## Hot Reloading (Development)

During development, serve the frontend from a dev server for instant hot reloading:

```cpp
#if JUCE_DEBUG
    webComponent.goToURL ("localhost:3000");    // Dev server (npm start)
#else
    webComponent.goToURL (juce::WebBrowserComponent::getResourceProviderRoot());
#endif
```

```bash
# In frontend directory:
npm install
npm start    # Starts dev server, usually at localhost:3000
```

Frontend changes (JS, CSS, HTML) reload instantly without recompiling C++.

## Platform Notes

| Platform | Backend | Notes |
|----------|---------|-------|
| macOS | WebKit | System-provided, always available |
| Windows | Edge (Chromium) | WebView2 runtime pre-installed on Win11; most Win10 machines have it via 2022 update. Use `JUCE_USE_WIN_WEBVIEW2_WITH_STATIC_LINKING=1` |
| Linux | GTK WebKit2 | Requires `libwebkit2gtk-4.1-dev` package |

Windows requires `withUserDataFolder()` to be set and `withBackend(Backend::webview2)` to be specified explicitly.

## Streaming Data to WebView (Spectrum, Waveforms)

To send real-time data (spectrum, waveforms) from C++ to the WebView:

```cpp
// C++ side: use evaluateJavascript or emitEventIfBrowserIsVisible
void pushSpectrumData (const std::vector<float>& spectrum)
{
    juce::String js = "window.updateSpectrum([";
    for (size_t i = 0; i < spectrum.size(); ++i) {
        if (i > 0) js << ",";
        js << juce::String (spectrum[i], 4);
    }
    js << "]);";
    webComponent.emitEventIfBrowserIsVisible ("spectrumUpdate",
        juce::var (spectrum.size()));  // lightweight event
    webComponent.evaluateJavascript (js);
}
```

```js
// JS side
window.updateSpectrum = (data) => {
    // Update canvas or visualization
    drawSpectrum(data);
};
```

Note: don't push data every audio block — throttle to ~30fps using a timer, otherwise the WebView will be overwhelmed.
