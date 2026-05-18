---
name: juce-plugin
description: Build JUCE audio plugins (VST3, AU, AAX, Standalone, LV2) in C++ with CMake. Covers the full development workflow from project scaffolding to multi-format builds, including AudioProcessor lifecycle, parameter management with APVTS, DSP module chains, custom editor GUIs, state serialization, real-time audio safety, and cross-platform CI/CD. Use this skill whenever the user mentions JUCE, audio plugins, VST plugins, AU plugins, audio effects, synthesizers, MIDI processors, AudioProcessor, AudioProcessorEditor, Projucer, or wants to create audio software — even if they just say "make a plugin" or "audio plugin". Also applies when users are working in an existing JUCE codebase (files like PluginProcessor.cpp, PluginEditor.cpp, CMakeLists.txt with juce_add_plugin).
---

# JUCE Audio Plugin Development

You are helping build an audio plugin using JUCE — a cross-platform C++ framework for audio applications and plugins. Plugins compile to VST3, AU, AAX, LV2, and Standalone formats from a single codebase.

## How JUCE Plugins Work

A JUCE plugin has two core classes that are always paired:

- **AudioProcessor** (engine) — the DSP core. Owns parameters, processes audio in `processBlock()`, handles state save/load. Runs on the real-time audio thread.
- **AudioProcessorEditor** (GUI) — the visual interface. Connected to parameters via APVTS attachments. Runs on the message thread.

`AudioProcessorValueTreeState` (APVTS) bridges both: thread-safe parameter access for the audio thread, UI attachments for the editor, and XML serialization for presets/state.

## Project Structure

```
MyPlugin/
  CMakeLists.txt           # Build configuration with juce_add_plugin()
  Source/
    PluginProcessor.h      # AudioProcessor subclass declaration
    PluginProcessor.cpp    # AudioProcessor implementation
    PluginEditor.h         # AudioProcessorEditor subclass declaration
    PluginEditor.cpp       # Editor GUI implementation
    dsp/                   # Custom DSP classes (filters, oscillators, etc.)
    components/            # Custom UI components (spectrum displays, etc.)
  resources/               # Assets (images, impulse responses, fonts)
```

## Workflow: Creating a New Plugin

### 1. Set Up the Project

Decide how to include JUCE:

```cmake
# Option A: JUCE as subdirectory (most common for plugins)
add_subdirectory(JUCE)

# Option B: System-installed JUCE
find_package(JUCE CONFIG REQUIRED)
```

### 2. Write CMakeLists.txt

```cmake
cmake_minimum_required(VERSION 3.22)
project(MyPlugin VERSION 1.0.0)

add_subdirectory(JUCE)

juce_add_plugin(MyPlugin
    COMPANY_NAME "YourCompany"
    PLUGIN_MANUFACTURER_CODE Yco1    # 4 chars, at least 1 uppercase
    PLUGIN_CODE Mp01                  # 4 chars, exactly 1 uppercase
    FORMATS VST3 AU Standalone        # Build targets
    PRODUCT_NAME "My Plugin"
    IS_SYNTH FALSE
    NEEDS_MIDI_INPUT FALSE
    NEEDS_MIDI_OUTPUT FALSE
    COPY_PLUGIN_AFTER_BUILD TRUE)     # Auto-install on build

target_sources(MyPlugin PRIVATE
    Source/PluginProcessor.cpp
    Source/PluginEditor.cpp)

target_compile_definitions(MyPlugin PUBLIC
    JUCE_WEB_BROWSER=0
    JUCE_USE_CURL=0
    JUCE_VST3_CAN_REPLACE_VST2=0)

target_link_libraries(MyPlugin
    PRIVATE juce::juce_audio_utils
    PUBLIC
        juce::juce_recommended_config_flags
        juce::juce_recommended_lto_flags
        juce::juce_recommended_warning_flags)
```

For the full CMake API (SDK paths, binary data, bundle resources, iOS/macOS specifics), read `references/cmake-reference.md`.

### 3. Create the Processor

The AudioProcessor subclass must override specific methods. Read `references/plugin-lifecycle.md` for the complete contract.

**Minimal processor skeleton:**

```cpp
// PluginProcessor.h
#pragma once
#include <juce_audio_processors/juce_audio_processors.h>

class MyPluginProcessor : public juce::AudioProcessor
{
public:
    MyPluginProcessor();
    ~MyPluginProcessor() override;

    // Audio processing
    void prepareToPlay (double sampleRate, int samplesPerBlock) override;
    void releaseResources() override;
    void processBlock (juce::AudioBuffer<float>&, juce::MidiBuffer&) override;

    // Editor
    juce::AudioProcessorEditor* createEditor() override;
    bool hasEditor() const override;

    // Info
    const juce::String getName() const override;
    bool acceptsMidi() const override;
    bool producesMidi() const override;
    double getTailLengthSeconds() const override;
    int getNumPrograms() override;
    int getCurrentProgram() override;
    void setCurrentProgram (int index) override;
    const juce::String getProgramName (int index) override;
    void changeProgramName (int index, const juce::String& newName) override;

    // State
    void getStateInformation (juce::MemoryBlock& destData) override;
    void setStateInformation (const void* data, int sizeInBytes) override;

    // Bus layout
    bool isBusesLayoutSupported (const BusesLayout& layouts) const override;

    // APVTS — the parameter manager
    juce::AudioProcessorValueTreeState apvts;

private:
    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (MyPluginProcessor)
};
```

### 4. Set Up Parameters with APVTS

Define all parameters statically in a free function, then initialize APVTS in the constructor. Read `references/parameter-management.md` for the full patterns (attachments, dynamic-ish parameters, non-parameter state).

```cpp
// In PluginProcessor.cpp

juce::AudioProcessorValueTreeState::ParameterLayout createParameterLayout()
{
    return {
        std::make_unique<juce::AudioParameterFloat>(
            juce::ParameterID { "gain", 1 },
            "Gain",
            juce::NormalisableRange<float> (0.0f, 1.0f, 0.001f),
            0.5f),
        std::make_unique<juce::AudioParameterChoice>(
            juce::ParameterID { "filterType", 1 },
            "Filter Type",
            juce::StringArray { "Low Pass", "High Pass", "Band Pass" },
            0),
        std::make_unique<juce::AudioParameterBool>(
            juce::ParameterID { "bypass", 1 },
            "Bypass",
            false)
    };
}

MyPluginProcessor::MyPluginProcessor()
    : AudioProcessor (BusesProperties()
        .withInput  ("Input",  juce::AudioChannelSet::stereo())
        .withOutput ("Output", juce::AudioChannelSet::stereo())),
      apvts (*this, nullptr, "Parameters", createParameterLayout())
{
}
```

### 5. Implement processBlock

This is where audio processing happens. It runs on the real-time thread — follow strict rules. Read `references/audio-thread-safety.md` for the full safety guide.

```cpp
void MyPluginProcessor::processBlock (juce::AudioBuffer<float>& buffer,
                                       juce::MidiBuffer& midiMessages)
{
    juce::ScopedNoDenormals noDenormals;

    // Read parameter values (thread-safe via atomics)
    auto gainValue = apvts.getRawParameterValue("gain")->load();

    for (int channel = 0; channel < buffer.getNumChannels(); ++channel)
    {
        auto* channelData = buffer.getWritePointer (channel);
        for (int sample = 0; sample < buffer.getNumSamples(); ++sample)
        {
            channelData[sample] *= gainValue;
        }
    }
}
```

For DSP module patterns (filters, oscillators, effects chains, convolution), read `references/dsp-patterns.md`.

### 6. Implement State Save/Load

```cpp
void MyPluginProcessor::getStateInformation (juce::MemoryBlock& destData)
{
    auto state = apvts.copyState();
    if (auto xml = state.createXml())
        copyXmlToBinary (*xml, destData);
}

void MyPluginProcessor::setStateInformation (const void* data, int sizeInBytes)
{
    if (auto xml = getXmlFromBinary (data, sizeInBytes))
        if (xml->hasTagName (apvts.state.getType()))
            apvts.replaceState (juce::ValueTree::fromXml (*xml));
}
```

### 7. Create the Editor

The editor connects UI controls to APVTS parameters via attachments. Read `references/ui-patterns.md` for custom components, layout strategies, and LookAndFeel customization.

```cpp
// PluginEditor.h
#pragma once
#include <juce_audio_processors/juce_audio_processors.h>
#include "PluginProcessor.h"

class MyPluginEditor : public juce::AudioProcessorEditor
{
public:
    MyPluginEditor (MyPluginProcessor&);
    ~MyPluginEditor() override;

    void paint (juce::Graphics&) override;
    void resized() override;

private:
    MyPluginProcessor& processorRef;

    juce::Slider gainSlider;
    juce::AudioProcessorValueTreeState::SliderAttachment gainAttachment;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (MyPluginEditor)
};
```

```cpp
// PluginEditor.cpp
MyPluginEditor::MyPluginEditor (MyPluginProcessor& p)
    : AudioProcessorEditor (&p),
      processorRef (p),
      gainAttachment (p.apvts, "gain", gainSlider)
{
    addAndMakeVisible (gainSlider);
    gainSlider.setSliderStyle (juce::Slider::RotaryHorizontalVerticalDrag);
    gainSlider.setTextBoxStyle (juce::Slider::TextBoxBelow, false, 80, 20);

    setResizeLimits (200, 150, 800, 600);
    setResizable (true, true);
    setSize (400, 300);
}

void MyPluginEditor::resized()
{
    auto bounds = getLocalBounds().reduced (10);
    gainSlider.setBounds (bounds.removeFromTop (100));
}
```

### 8. Build and Test

```bash
# Configure
cmake -B build -DCMAKE_BUILD_TYPE=Release

# Build all formats
cmake --build build --config Release

# On macOS, plugins are copied to:
#   ~/Library/Audio/Plug-Ins/VST3/
#   ~/Library/Audio/Plug-Ins/Components/ (AU)
# On Linux:
#   ~/.vst3/
#   ~/.lv2/ (if LV2 format enabled)
# On Windows:
#   %APPDATA%/VST3/
```

For cross-platform builds, CI/CD with GitHub Actions, and releasing, read `references/cmake-reference.md`.

## Plugin Types

JUCE supports several plugin categories, configured via CMake properties:

| Type | CMake Flags | Description |
|------|-------------|-------------|
| **Audio Effect** | defaults | Processes audio input to output |
| **Synthesizer** | `IS_SYNTH TRUE`, `NEEDS_MIDI_INPUT TRUE` | Generates audio from MIDI |
| **MIDI Effect** | `IS_MIDI_EFFECT TRUE` | Processes MIDI only (no audio) |
| **Synth + MIDI Out** | Add `NEEDS_MIDI_OUTPUT TRUE` | Synth that also sends MIDI |

## JUCE Modules

Modules are the building blocks. Link the top-level module and transitive dependencies resolve automatically:

| Module | Purpose | Link |
|--------|---------|------|
| `juce_audio_utils` | Audio utilities, MIDI keyboard | `juce::juce_audio_utils` |
| `juce_dsp` | DSP: filters, oscillators, convolution, ProcessorChain | `juce::juce_dsp` |
| `juce_audio_processors` | AudioProcessor, APVTS, plugin format hosting | (auto-included) |
| `juce_graphics` | Graphics, Colour, Path, Image | (auto-included) |
| `juce_gui_basics` | Component, Slider, Button, Label | (auto-included) |
| `juce_gui_extra` | CodeEditorComponent, WebBrowserComponent | `juce::juce_gui_extra` |
| `juce_opengl` | OpenGL rendering in plugins | `juce::juce_opengl` |
| `juce_osc` | Open Sound Control (OSC) | `juce::juce_osc` |

The 24 JUCE modules are: `juce_analytics`, `juce_animation`, `juce_audio_basics`, `juce_audio_devices`, `juce_audio_formats`, `juce_audio_plugin_client`, `juce_audio_processors`, `juce_audio_utils`, `juce_box2d`, `juce_core`, `juce_cryptography`, `juce_data_structures`, `juce_dsp`, `juce_events`, `juce_graphics`, `juce_gui_basics`, `juce_gui_extra`, `juce_javascript`, `juce_midi_ci`, `juce_opengl`, `juce_osc`, `juce_product_unlocking`, `juce_video`.

## WebView UIs (JUCE 8)

JUCE 8 supports building plugin UIs with web technologies (React, Vue, Svelte, plain HTML/CSS/JS) via `WebBrowserComponent`. This allows rapid UI iteration with hot reloading, use of mature web frontend frameworks, and cross-platform hardware-accelerated graphics via WebGL. Frontend web developers can participate in plugin UI development without touching C++.

The WebView feature lives in the `juce_gui_extra` module. It works by embedding a native browser component — WebKit on macOS/iOS, Edge (Chromium) on Windows, GTK WebKit2 on Linux.

### CMake Setup

```cmake
juce_add_plugin(MyPlugin
    ...
    NEEDS_WEBVIEW2 TRUE)   # Required on Windows

target_compile_definitions(MyPlugin PUBLIC
    JUCE_WEB_BROWSER=1
    JUCE_USE_WIN_WEBVIEW2_WITH_STATIC_LINKING=1)  # Windows best practice
```

### C++ Side: WebBrowserComponent with Parameter Attachments

```cpp
#include <juce_gui_extra/juce_gui_extra.h>

class WebViewEditor : public juce::AudioProcessorEditor
{
public:
    WebViewEditor (MyProcessor& p)
        : AudioProcessorEditor (p),
          processor (p),
          gainRelay (webComponent, "gain"),
          gainAttachment (*processor.apvts.getParameter ("gain"), gainRelay, nullptr)
    {
        addAndMakeVisible (webComponent);
        setSize (600, 400);
    }

    void resized() override { webComponent.setBounds (getLocalBounds()); }

private:
    MyProcessor& processor;

    juce::WebBrowserComponent webComponent {
        juce::WebBrowserComponent::Options()
            .withNativeIntegrationEnabled()
            .withBackend (juce::WebBrowserComponent::Options::Backend::webview2)
            .withWinWebView2Options (juce::WebBrowserComponent::Options::WinWebView2{}
                .withUserDataFolder (juce::File::getSpecialLocation (
                    juce::File::tempDirectory)))
            .withOptionsFrom (gainRelay)
            .withResourceProvider ([this] (const auto& url) -> std::optional<juce::WebBrowserComponent::Resource> {
                // Serve BinaryData resources to the WebView
                return std::nullopt;
            })
    };

    juce::WebSliderRelay gainRelay;
    juce::WebSliderParameterAttachment gainAttachment;
};
```

### JavaScript Side: JUCE Frontend Library

The JUCE frontend library is at `modules/juce_gui_extra/native/javascript/index.js`. It works standalone — no C++ backend needed for visual testing.

```js
import * as Juce from "./index.js";

// Connect to a parameter
const gainState = Juce.getSliderState("gain");

// Listen for value changes from the DAW
gainState.valueChangedEvent.addListener(() => {
    mySlider.value = gainState.getNormalisedValue();
});

// Send value changes back to the DAW
mySlider.addEventListener("input", (event) => {
    gainState.setNormalisedValue(event.target.value / 100);
});

// Call native C++ functions
const loadPreset = Juce.getNativeFunction("loadPreset");
loadPreset(45).then(result => console.log(result));

// Access backend resources
const resourceUrl = Juce.getBackendResourceAddress("spectrum.json");
```

### Development Workflow

- **Debug**: Run a dev server (`npm start`) and point the WebView at `localhost:3000` for hot reloading
- **Release**: Serve frontend assets from `BinaryData` via the resource provider, or bundle as a zip

Read **`references/webview-ui.md`** for the complete guide: resource providers, native functions, event listeners, all attachment types, the React integration pattern, and platform-specific quirks.

## Reference Files

Read these as needed based on what you're implementing:

- **`references/plugin-lifecycle.md`** — Complete AudioProcessor contract: all overrides, bus configurations, double precision, Synthesiser framework for synths
- **`references/parameter-management.md`** — APVTS patterns: parameter layout, attachments, raw pointers, non-parameter state, parameter groups
- **`references/dsp-patterns.md`** — DSP cookbook: ProcessorChain, filters, oscillators, waveshapers, convolution reverb, delay lines, wavetable synthesis, LFO at control rate, two-level chain architecture, per-sample vs block processing
- **`references/ui-patterns.md`** — Editor patterns: component layout, custom widgets, LookAndFeel, meters, FFT spectrum analyser, responsive resize, binary data for assets
- **`references/webview-ui.md`** — WebView UIs (JUCE 8): WebBrowserComponent, resource providers, native functions, JS parameter bindings, React integration, hot reloading
- **`references/audio-thread-safety.md`** — Real-time safety rules: what you can/cannot do in processBlock, lock-free patterns, atomics, debugging audio glitches
- **`references/cmake-reference.md`** — Full CMake API: all juce_add_plugin properties, SDK paths, binary data, CI/CD, platform specifics

## Common Patterns

### Synthesizer Plugin

Uses the `Synthesiser` framework. Override `SynthesiserVoice::renderNextBlock()` for per-voice DSP, `SynthesiserSound` for note/channel routing. See `references/plugin-lifecycle.md` for the full pattern.

### Sidechain Effect

Add a sidechain bus in the constructor:
```cpp
BusesProperties()
    .withInput  ("Input",     juce::AudioChannelSet::stereo())
    .withInput  ("Sidechain", juce::AudioChannelSet::stereo())
    .withOutput ("Output",    juce::AudioChannelSet::stereo())
```
Access in processBlock: `auto sidechain = getBusBuffer (buffer, true, 1);`

### Multiband Processing

Split into bands using `juce::dsp::LinkwitzRileyFilter<>` crossover filters, process each band independently, then sum back together.

### Custom Preset System

Store presets as XML files loaded via `juce::File` or embedded as binary data. Use `apvts.replaceState()` to load.

## Tips

- **Use `GenericAudioProcessorEditor`** for quick prototypes — it auto-generates a UI from your parameters. Just return `new GenericAudioProcessorEditor(*this)` from `createEditor()`.
- **Use `pluginval`** to validate plugins before shipping — it catches threading, state, and parameter bugs.
- **Cache `getRawParameterValue()` pointers** as members — never call it inside `processBlock()`.
- **Pre-allocate all buffers** in `prepareToPlay()`, never in `processBlock()`.
- **Use `juce::ScopedNoDenormals`** at the top of `processBlock()` to avoid performance penalties from denormal floats.
- **Set `COPY_PLUGIN_AFTER_BUILD TRUE`** in CMake for rapid iteration — plugins auto-install after each build.
- **Close your DAW before rebuilding** — DAWs lock plugin files while loaded.
