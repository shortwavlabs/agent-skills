# CMake Reference

Full reference for JUCE's CMake build system. JUCE requires CMake 3.22+.

## Project Setup

```cmake
cmake_minimum_required(VERSION 3.22)
project(MyPlugin VERSION 1.0.0)

# Option A: JUCE as subdirectory (most common)
add_subdirectory(JUCE)

# Option B: System-installed JUCE
find_package(JUCE CONFIG REQUIRED)
```

## juce_add_plugin

The main function for creating audio plugin targets:

```cmake
juce_add_plugin(MyPlugin
    # Identity
    PRODUCT_NAME "My Plugin"                  # Display name in DAW
    COMPANY_NAME "MyCompany"
    COMPANY_COPYRIGHT "Copyright 2024 MyCompany"
    COMPANY_WEBSITE "https://example.com"
    COMPANY_EMAIL "dev@example.com"
    BUNDLE_ID "com.mycompany.myplugin"

    # Plugin codes (required for AU/VST3)
    PLUGIN_MANUFACTURER_CODE Manu             # 4 chars, at least 1 uppercase
    PLUGIN_CODE Mp01                           # 4 chars, exactly 1 uppercase (unique!)

    # Build formats
    FORMATS VST3 AU Standalone                # VST3 AU AAX LV2 Standalone Unity AUv3

    # Plugin type
    IS_SYNTH TRUE                             # TRUE for instruments, FALSE for effects
    NEEDS_MIDI_INPUT TRUE                     # Required for synths and MIDI effects
    NEEDS_MIDI_OUTPUT FALSE                   # For arpeggiators, MIDI generators
    IS_MIDI_EFFECT FALSE                      # TRUE for MIDI-only plugins
    EDITOR_WANTS_KEYBOARD_FOCUS FALSE         # TRUE if editor needs keyboard input

    # Build behavior
    COPY_PLUGIN_AFTER_BUILD TRUE              # Auto-install after building
    VERSION 1.0.0                             # Defaults to project version

    # Description (shown in some DAWs)
    DESCRIPTION "A simple gain plugin"

    # Plugin categories (host-specific)
    VST3_CATEGORIES "Fx|Dynamics"             # VST3: Fx, Instrument, Fx|Dynamics, etc.
    AU_MAIN_TYPE "kAudioUnitType_Effect"      # AU: Effect, MusicDevice, MusicEffect
    AAX_CATEGORY 0                            # AAX category integer
)
```

## VST3 Categories

Common values for `VST3_CATEGORIES`:
- `"Fx"` — effect
- `"Fx|Dynamics"` — compressor, limiter, gate
- `"Fx|EQ"` — equalizer
- `"Fx|Filter"` — filter
- `"Fx|Delay"` — delay, echo
- `"Fx|Reverb"` — reverb
- `"Fx|Distortion"` — distortion, saturation
- `"Fx|Modulation"` — chorus, flanger, phaser
- `"Instrument"` — synthesizer
- `"Instrument|Synth"` — synthesizer (specific)

## AU Main Types

- `"kAudioUnitType_Effect"` — audio effect (aufx)
- `"kAudioUnitType_MusicDevice"` — instrument (aumu)
- `"kAudioUnitType_MusicEffect"` — MIDI-controlled effect (aumf)
- `"kAudioUnitType_MIDIProcessor"` — MIDI effect (aumi)

## Linking Modules

```cmake
target_link_libraries(MyPlugin
    PRIVATE
        juce::juce_audio_utils      # Audio utilities + MIDI keyboard
        # juce::juce_dsp            # DSP module (filters, oscillators, etc.)
        # juce::juce_gui_extra      # Code editor, web browser
        # juce::juce_opengl         # OpenGL rendering
        # juce::juce_osc            # OSC protocol
        MyPluginData                # Binary data target (if created)
    PUBLIC
        juce::juce_recommended_config_flags    # Optimization flags
        juce::juce_recommended_lto_flags       # Link-time optimization
        juce::juce_recommended_warning_flags   # Compiler warnings
)
```

Transitive dependencies resolve automatically — `juce::juce_audio_utils` pulls in `juce::juce_audio_processors`, `juce::juce_gui_basics`, `juce::juce_core`, etc.

## Binary Data (Embedding Assets)

```cmake
juce_add_binary_data(MyPluginData
    NAMESPACE MyPlugin                # Optional: namespace for BinaryData class
    SOURCES
        resources/background.png
        resources/knob.svg
        resources/impulse_response.wav
        resources/custom_font.ttf
)
```

Access in code:
```cpp
#include "BinaryData.h"
// BinaryData::background_png, BinaryData::background_pngSize
// BinaryData::knob_svg, BinaryData::knob_svgSize
```

## SDK Paths

Required for proprietary formats:

```cmake
# VST2 (deprecated, requires NDA with Steinberg)
juce_set_vst2_sdk_path(${CMAKE_CURRENT_SOURCE_DIR}/SDKs/VST2)

# VST3 (usually found automatically on macOS/Windows)
juce_set_vst3_sdk_path(${CMAKE_CURRENT_SOURCE_DIR}/SDKs/VST3)

# AAX (requires Avid developer account)
juce_set_aax_sdk_path(${CMAKE_CURRENT_SOURCE_DIR}/SDKs/AAX)

# ARA (requires Celemony ARA SDK)
juce_set_ara_sdk_path(${CMAKE_CURRENT_SOURCE_DIR}/SDKs/ARA)
```

Set these before calling `juce_add_plugin()`.

## Compile Definitions

Common JUCE module configuration flags:

```cmake
target_compile_definitions(MyPlugin PUBLIC
    JUCE_WEB_BROWSER=0              # Disable web browser (saves build time)
    JUCE_USE_CURL=0                 # Disable CURL (no network features)
    JUCE_VST3_CAN_REPLACE_VST2=0    # Don't try VST2 compatibility
    JUCE_DISPLAY_SPLASH_SCREEN=0    # Disable splash screen (commercial license)
    JUCE_REPORT_APP_USAGE=0         # Disable usage reporting
    JUCE_STRICT_REFCOUNTEDPOINTER=1 # Compile-time null pointer checks
    JUCE_DSP_ENABLE_SNAP_TO_ZERO=0  # Only with ScopedNoDenormals in processBlock: see below
)
```

Module-specific flags are documented in each module's header file (e.g., `juce_core/juce_core.h`).

`juce::dsp` filters and `dsp::Oversampling` zero tiny state values at the end of every block, on Intel CPUs
only, so x86 output depends on the host block size while ARM output does not. With denormals already flushed by
`ScopedNoDenormals`, `JUCE_DSP_ENABLE_SNAP_TO_ZERO=0` makes x86 match ARM; see
[platform-builds.md](platform-builds.md#floating-point-results-differ-between-cpus).

## Plugin Copy Directories

Override where plugins are copied after build:

```cmake
juce_add_plugin(MyPlugin
    ...
    VST3_COPY_DIR "/custom/path/VST3"
    AU_COPY_DIR "/custom/path/Components"
    AAX_COPY_DIR "/custom/path/AAX"
)
```

Default locations (`COPY_PLUGIN_AFTER_BUILD` itself defaults to off):
- **macOS VST3**: `~/Library/Audio/Plug-Ins/VST3/`
- **macOS AU**: `~/Library/Audio/Plug-Ins/Components/`
- **Linux VST3 / LV2**: `~/.vst3/` / `~/.lv2/`
- **Windows VST3 (64-bit)**: `C:\Program Files\Common Files\VST3` (`$ENV{CommonProgramW6432}/VST3`): the build
  needs administrator rights to copy there, so turn copying off in CI
- **Windows LV2**: `%APPDATA%\LV2`

## macOS Specifics

```cmake
# Universal binary (Apple Silicon + Intel)
set(CMAKE_OSX_ARCHITECTURES "arm64;x86_64")

# Bundle resources (xcassets, storyboards)
juce_add_bundle_resources_directory(MyPlugin Resources/Assets.xcassets)
```

The hardened runtime that notarization requires is not a CMake setting: it is applied when signing, with
`codesign --options runtime`. Signing, packaging and notarization are in
[signing-and-notarization.md](signing-and-notarization.md); Windows and Linux build differences are in
[platform-builds.md](platform-builds.md).

## VST3 Manifest

```cmake
# Auto-generate VST3 manifest (default ON for VST3 format)
juce_add_plugin(MyPlugin
    ...
    VST3_AUTO_MANIFEST TRUE
)

# Or manually enable after the fact
juce_enable_vst3_manifest_step(MyPlugin)
```

## Helper Functions

```cmake
# Generate JuceHeader.h (optional — you can include module headers directly)
juce_generate_juce_header(MyPlugin)

# Add a single JUCE module by path
juce_add_module(${CMAKE_CURRENT_SOURCE_DIR}/modules/my_custom_module)
# IMPORTANT: link PRIVATE only
target_link_libraries(MyPlugin PRIVATE my_custom_module)

# Add multiple JUCE modules
juce_add_modules(juce_my_module1 juce_my_module2)

# Disable default compiler flags (if you want full control)
juce_disable_default_flags()
```

## Build Commands

```bash
# Configure (Debug for development)
cmake -B build -DCMAKE_BUILD_TYPE=Debug

# Configure (Release for distribution)
cmake -B build -DCMAKE_BUILD_TYPE=Release

# Build
cmake --build build --config Debug
cmake --build build --config Release -j8

# Build specific target
cmake --build build --target MyPlugin_Standalone

# Install globally
cmake --build build --target install
```

Generated targets (with the example name `MyPlugin`):
- `MyPlugin` — shared code (static library)
- `MyPlugin_VST3` — VST3 plugin
- `MyPlugin_AU` — Audio Unit plugin
- `MyPlugin_Standalone` — Standalone application
- `MyPlugin_AAX` — AAX plugin (if enabled)
- `MyPlugin_LV2` — LV2 plugin (if enabled)
- `MyPlugin_All` — builds all enabled formats

## GitHub Actions CI/CD

A compile-only matrix for a native-editor plugin; a WebView2 editor also needs the WebView2 SDK on Windows
([webview-ui.md](webview-ui.md#windows-webview2)). Wire `COPY_PLUGIN_AFTER_BUILD` to a CMake option and pass it OFF in CI. Release builds, editor tests under Xvfb, an older-glibc container for Linux, the WebView2
SDK on Windows and pluginval per platform are in [platform-builds.md](platform-builds.md#ci-jobs).

```yaml
name: Build Plugin
on: [push, pull_request]

jobs:
  build:
    strategy:
      matrix:
        include:
          - os: macos-latest
            cmake_args: -DCMAKE_OSX_ARCHITECTURES="arm64;x86_64"
          - os: windows-latest
            cmake_args: ""
          - os: ubuntu-24.04     # builds against its glibc; release builds use an older container
            cmake_args: ""

    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v7      # take majors from the release pages; v4 is on deprecated Node 20
        with:
          submodules: true

      - name: Install Linux dependencies
        if: runner.os == 'Linux'
        run: |
          sudo apt-get update
          sudo apt-get install -y libasound2-dev libjack-jackd2-dev \
            libfreetype-dev libfontconfig1-dev libx11-dev libxcomposite-dev \
            libxcursor-dev libxext-dev libxinerama-dev libxrandr-dev \
            libxrender-dev libxi-dev libwebkit2gtk-4.1-dev

      - name: Configure
        run: cmake -B build ${{ matrix.cmake_args }}

      - name: Build
        run: cmake --build build --config Release -j 4

      - name: Upload artifacts
        uses: actions/upload-artifact@v7
        with:
          name: plugin-${{ runner.os }}
          path: |
            build/*/VST3/**
            build/*/AU/**
            build/**/Standalone/**
```

## Pamplejuce Template

For production plugins, [Pamplejuce](https://github.com/sudara/pamplejuce) is the community-standard CMake template. It includes:
- CI/CD for all platforms
- Installer generation (macOS .dmg, Windows .exe, Linux .deb)
- Pluginval integration
- Code signing setup
- Catch2 testing framework

## Linux Dependencies

JUCE's full list for Ubuntu (`docs/Linux Dependencies.md`; JUCE 9 added `libxi-dev`, and `juce_opengl` now uses EGL):

```bash
sudo apt-get install -y clang libasound2-dev libjack-jackd2-dev \
    ladspa-sdk libcurl4-openssl-dev libfreetype-dev libfontconfig1-dev \
    libx11-dev libxcomposite-dev libxcursor-dev libxext-dev \
    libxinerama-dev libxrandr-dev libxrender-dev libxi-dev \
    libwebkit2gtk-4.1-dev libglu1-mesa-dev mesa-common-dev libegl-dev
```

Only some are needed for a given plugin: `libcurl4-openssl-dev` with `JUCE_USE_CURL=1`, `ladspa-sdk` for plugin
hosting, the GL/EGL packages for `juce_opengl`. `libwebkit2gtk-4.1-dev` is required (headers only; WebKitGTK is
loaded at run time) whenever a target uses `juce::WebBrowserComponent`. A missing package shows up as a
compile error, not a configure error. Trimmed list and glibc baseline: [platform-builds.md](platform-builds.md#linux).

## WebView editor targets

For JUCE 9 browser/WebView2 flags, NuGet package discovery, loader/runtime distinctions and frontend resource build dependencies, use the maintained [WebView CMake guidance](webview-ui.md#cmake-and-webview2). Its browser-enabled flags replace the native-editor example's `JUCE_WEB_BROWSER=0`; do not combine both definitions.
