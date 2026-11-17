# Parameter Management with APVTS

`AudioProcessorValueTreeState` (APVTS) is the central pattern for managing plugin parameters. It provides thread-safe parameter access, host automation, UI attachments, and state serialization.

## Parameter Types

| Class | Value Type | Use For |
|-------|-----------|---------|
| `AudioParameterFloat` | `float` | Gain, frequency, mix, any continuous value |
| `AudioParameterInt` | `int` | Octave, semitone, discrete ranges |
| `AudioParameterBool` | `bool` | On/off, bypass, polarity |
| `AudioParameterChoice` | `int` (index) | Filter type, waveform, mode selection |

## Defining Parameters

Use a free function returning `ParameterLayout`. This makes the parameter list declarative and easy to read:

```cpp
juce::AudioProcessorValueTreeState::ParameterLayout createParameterLayout()
{
    return {
        // Float parameter with NormalisableRange (skew, snap, etc.)
        std::make_unique<juce::AudioParameterFloat>(
            juce::ParameterID { "gain", 1 },      // ID + version hint (orders the AU parameter list: see below)
            "Gain",                                 // Display name
            juce::NormalisableRange<float> (0.0f, 1.0f, 0.001f),  // range
            0.5f),                                  // default

        // Float with skew (for frequency — logarithmic feel)
        std::make_unique<juce::AudioParameterFloat>(
            juce::ParameterID { "frequency", 1 },
            "Frequency",
            juce::NormalisableRange<float> (20.0f, 20000.0f,
                [] (float start, float end, float skew, float normalised) {
                    return start * std::pow (end / start, normalised);
                },
                [] (float start, float end, float skew, float value) {
                    return std::log (value / start) / std::log (end / start);
                }),
            1000.0f),

        // Choice parameter
        std::make_unique<juce::AudioParameterChoice>(
            juce::ParameterID { "waveform", 1 },
            "Waveform",
            juce::StringArray { "Sine", "Saw", "Square", "Triangle" },
            0),

        // Boolean parameter
        std::make_unique<juce::AudioParameterBool>(
            juce::ParameterID { "sync", 1 },
            "Sync",
            false)
    };
}
```

### NormalisableRange Options

```cpp
NormalisableRange<float> (min, max)                    // Linear, step = continuous
NormalisableRange<float> (min, max, step)              // Fixed step size
NormalisableRange<float> (min, max, step, skew)        // Skew factor (>1 = more resolution at low end)
NormalisableRange<float> (min, max, { ... }, { ... }) // Custom convert/invert functions
```

Skew values: `0.5` = more resolution at high end, `2.0` = more resolution at low end, `1.0` = linear.

## Initializing APVTS

In the processor constructor:

```cpp
MyProcessor()
    : AudioProcessor (BusesProperties()
        .withInput  ("Input",  juce::AudioChannelSet::stereo())
        .withOutput ("Output", juce::AudioChannelSet::stereo())),
      apvts (*this, nullptr, "Parameters", createParameterLayout())
{
}
```

The `"Parameters"` string is the ValueTree type name used for serialization.

## Reading Parameters in processBlock

### Method 1: Cached Raw Pointers (recommended for performance)

Cache pointers in `prepareToPlay()` or the constructor:

```cpp
// In header:
std::atomic<float>* gainParam = nullptr;
std::atomic<float>* freqParam = nullptr;

// In constructor or prepareToPlay:
gainParam = apvts.getRawParameterValue ("gain");
freqParam = apvts.getRawParameterValue ("frequency");

// In processBlock (thread-safe, lock-free):
auto gain = gainParam->load();
auto freq = freqParam->load();
```

### Method 2: Parameter References Struct (cleanest for large plugins)

```cpp
struct ParameterReferences
{
    juce::AudioParameterFloat& gain;
    juce::AudioParameterChoice& filterType;
    juce::AudioParameterBool& bypass;

    // Helper to get all from APVTS
    static ParameterReferences create (juce::AudioProcessorValueTreeState& apvts)
    {
        return {
            *dynamic_cast<juce::AudioParameterFloat*> (apvts.getParameter ("gain")),
            *dynamic_cast<juce::AudioParameterChoice*> (apvts.getParameter ("filterType")),
            *dynamic_cast<juce::AudioParameterBool*> (apvts.getParameter ("bypass"))
        };
    }
};

// In processor:
ParameterReferences params;

MyProcessor() : ..., params (ParameterReferences::create (apvts)) {}

// In processBlock:
auto gain = params.gain.get();  // returns the current value
```

### Method 3: Direct APVTS Call (simplest, avoid in hot loops)

```cpp
auto gain = apvts.getRawParameterValue("gain")->load();
```

Don't call this per-sample in tight loops — the atomic load has a cost.

## UI Attachments

Attachments synchronize a UI control with a parameter. They handle host automation and gesture start/end.

```cpp
// In editor header:
juce::Slider gainSlider;
juce::AudioProcessorValueTreeState::SliderAttachment gainAttachment;

juce::ToggleButton bypassButton;
juce::AudioProcessorValueTreeState::ButtonAttachment bypassAttachment;

juce::ComboBox filterTypeCombo;
juce::AudioProcessorValueTreeState::ComboBoxAttachment filterTypeAttachment;

// In editor constructor:
gainAttachment   (processor.apvts, "gain",      gainSlider),
bypassAttachment (processor.apvts, "bypass",    bypassButton),
filterTypeAttachment (processor.apvts, "filterType", filterTypeCombo)
```

Important: the control must outlive its attachment. Declare the control before the attachment in your class: members are destroyed in reverse declaration order, so the attachment is destroyed first and never touches a control that no longer exists.

**Real-time caveat.** These stock attachments are parameter listeners. When a host automates a parameter on the audio thread with the editor open, they post a message to the message queue from that thread (a lock, a run-loop wake-up and, on macOS, sometimes `malloc`). For a product that must be real-time safe under automation, use the polled-attachment pattern in [host-automation-and-editor-sync.md](host-automation-and-editor-sync.md#the-remedy-polled-editor-attachments).

## AU Parameter Order and Version Hints

**Stable parameter IDs are not enough to keep Logic automation working.** Logic Pro and GarageBand address AU v2 parameters by their **index in the AU parameter list**, not by ID (JUCE documents this on `AudioProcessorParameter`'s version-hint constructor). JUCE's AU wrapper builds that list in `GetParameterList`: sorted by hashed parameter ID, then **stable-sorted by version hint**. So the hosted order:

- is **not** the declaration order in your `ParameterLayout`;
- changes when you add a parameter whose version hint is not higher than every existing one: its hash can land it in the middle and shift every parameter after it by one index;
- never safely survives removing a parameter.

**Rules for a plug-in that has shipped:**

1. Give every parameter a version hint (`juce::ParameterID { "id", 1 }`); debug AU builds assert when it is missing.
2. Every parameter added in a later release gets a hint **higher than every hint in all earlier releases**. All parameters added in one release can share that hint.
3. Never remove or re-hint a shipped parameter. Hide or deprecate it instead.
4. Check the **hosted** list, not the source, for every release that adds parameters.

**Regression test in the processor suite** (emulates the wrapper's sort with `JUCE_FORCE_USE_LEGACY_PARAM_IDS` off; the AU ID is the string ID's `hashCode()`, masked to 31 bits while `JUCE_USE_STUDIO_ONE_COMPATIBLE_PARAMETERS` is 1, its default in JUCE 9.0.3; without the mask, sort as unsigned):

```cpp
struct Entry { juce::String id; int hash, hint; };
std::vector<Entry> v;
for (auto* p : processor.getParameters())
    if (auto* w = dynamic_cast<juce::AudioProcessorParameterWithID*> (p))
        v.push_back ({ w->getParameterID(), w->getParameterID().hashCode() & 0x7fffffff, p->getVersionHint() });
std::sort        (v.begin(), v.end(), [] (auto& a, auto& b) { return a.hash < b.hash; });
std::stable_sort (v.begin(), v.end(), [] (auto& a, auto& b) { return a.hint < b.hint; });
// compare v's ids, in order, with the order frozen from the previous release; new ids must come last
```

**Host-level check:** instantiate the built AU, read `kAudioUnitProperty_ParameterList` (global scope) and the names from `kAudioUnitProperty_ParameterInfo`, and compare them with the list saved from the previous release's installed AU. Restoring a ClassInfo saved by the previous release into the new build should leave every old value in place and the new parameters at their defaults.

**Case study:** a plug-in added one boolean in its third release with hint 1, like its eleven original parameters. Its hash sorted it ninth, and three existing parameters moved one index. The processor's ID checks all passed, because no ID had changed; the defect showed only in the hosted AU list. Giving the new parameter hint 2 restored the eleven positions and listed it twelfth. The number 2 is that project's history; the rule is "higher than everything shipped before".

VST3 does not use the version hint: its parameter IDs are the hashed string IDs and its order is the declaration order. AUv3 has no equivalent mechanism; JUCE advises not adding or removing parameters there if Logic and GarageBand must keep automation.

## Factory Programs and Host Restore

Factory presets embedded in the plug-in are normally exposed through JUCE's program API: `getNumPrograms`, `getProgramName`, `setCurrentProgram` and `getCurrentProgram`. Hosts store and replay program **numbers**, so the program list behaves like the parameter list: once shipped, its order is part of every saved project. User presets on disk stay out of it ([user-presets.md](user-presets.md#decide-what-a-preset-is)).

**How the JUCE 9.0.3 wrappers use the API.**

| Wrapper | Behaviour | Evidence |
|---|---|---|
| AU | A host setting `kAudioUnitProperty_PresentPreset` to a number of 0 or more calls `NewFactoryPresetSet`, which calls `setCurrentProgram`. Restoring a project through `kAudioUnitProperty_ClassInfo` sets the present preset to −1 with the saved name, then calls `setStateInformation`; no program is applied | **Source-derived** (`juce_audio_plugin_client_AU_1.mm`, `AUBase.cpp`); **tested** in-process on the built AU (case study below) |
| AU | The factory preset list (`kAudioUnitProperty_FactoryPresets`) is built from `getProgramName`, in program order | **Tested** (case study) |
| VST3 | With `getNumPrograms() > 1`, the wrapper appends a host-visible, automatable "Program" parameter after every other parameter, Bypass included | **Source-derived** (`juce_audio_plugin_client_VST3.cpp`, `ProgramChangeParameter`); **tested**: the parameter surface grew from 21 to 22, the existing 21 unchanged in order and defaults |
| VST3 | `setComponentState` writes `getCurrentProgram()` into that parameter after every component state. The parameter's `setNormalized` calls `setCurrentProgram` only when its value differs from `getCurrentProgram()` | **Source-derived** |

**Keep `getCurrentProgram` truthful.** A plug-in that stores "the last program selected" reports it even after the user edits the sound. A host that saves that number and replays it after restoring a project would then put the factory values back over the saved ones. Derive the number from the parameters instead:
- program k while every parameter the factory preset sets holds k's values, within a normalised tolerance;
- otherwise a neutral program that changes nothing, such as 0.

An edited project then reports the neutral program, and an unedited one reports a program that only sets the values it already has. **Tested** (case study).

**The residual risk.** The plug-in cannot tell a replayed program number from a deliberate choice. Suppose a host stored a non-zero number while the values matched, and the values were edited later without the host being told; replaying that stale number after a restore still applies the program. Notifying the host on every change of the derived number (below) narrows this; it does not close it. The restore test below saves the derived number, so it cannot show this case.

Tradeoffs:
- A project that happens to sound exactly like a factory preset reports it.
- The factory values must differ from each other; test that.
- The neutral entry appears in the host's preset list.

**Program 0 can keep an older build's meaning.** A plug-in that shipped with one placeholder program, whose `setCurrentProgram` did nothing, can keep index 0 as a do-nothing entry and put factory preset i at i + 1. A host that selects program 0, by itself or from an old project, still changes nothing.
- Never reorder or remove a program after release; append new ones.
- Refuse invalid numbers without touching a parameter.
- Ignore `changeProgramName`, so a host cannot rename a factory program.
- **Case-study choice.**

**What a program sets is a product decision.** A factory program can set only the tone parameters and leave power, input calibration, input routing and trims as the user set them, so it cannot change their gain staging. Init and user presets may cover more. Decide it per parameter, write it down, and make the modified mark compare only what each kind sets ([user-presets.md](user-presets.md#processor-selection-and-the-modified-mark)).

**Host notification.**
- After the editor applies a factory program, call `updateHostDisplay (ChangeDetails().withProgramChanged (true))`, so the host's preset display follows.
- When a host selects a program itself, it already knows; do not notify it back.
- A notification sent from the editor's timer runs only while the editor is open. A host can therefore show a different program for the same values, depending on whether the editor was open when they changed.
- On AU, JUCE's notification sets the present preset to `getCurrentProgram()`. That can replace the name the host restored with the neutral program's name or a factory name.
- **Source-derived;** what Logic shows in these cases was not observed.

**Tests.** Keep the wrapper evidence apart from host behaviour.

| Level | What to check |
|---|---|
| processor | count, names and order, pinned in the test; invalid numbers and the neutral program change nothing; each program sets exactly its values with balanced gestures and leaves the rest; the factory values are distinct |
| processor, restore | select factory program k, edit a parameter it sets, save the state and `getCurrentProgram()`, restore into a fresh instance, then call `setCurrentProgram` with the saved number (an AU host replaying `PresentPreset`) and with `getCurrentProgram()` (VST3's `setComponentState`). Every restored value must remain. Repeat without the edit: the program is reported and changes nothing |
| AU, in process | load the built AU with `dlopen`, register it for the process under a spare subtype with `AudioComponentRegister`, and read `kAudioUnitProperty_FactoryPresets`. Set `PresentPreset` to each number and read the parameters back. Save ClassInfo after a program and an edit, restore it into a fresh instance: the edit remains and the present preset reads −1 |
| VST3, parameter surface | list the hosted parameters of the previous release and of the candidate, through a headless host; record the added Program parameter |
| validators | `auval` and pluginval exercise the programs; pluginval reports "Current program is -1" as a warning for an AU with no present preset, which is expected by design |
| real hosts | **not covered** by the levels above: a host that stores a program number separately and replays it, and what each host's preset display shows with the editor open and closed |

The state format does not change: projects store parameter values, not a program number, and old states restore with their existing migrations.

**Case study:** Vintage Combo (JUCE 9.0.3, macOS arm64, `shortwavlabs/vintage-combo` branch `feature/greenfield-dsp`).
- **Tested:**
  - the processor checks in `Tests/PresetReliability.cpp`, groups E8 and F, commit `9861bab`;
  - the in-process AU check `tools/reliability/au_programs.cpp`: 31 of 31, `docs/reliability/evidence/au-programs.json`;
  - the parameter surface, `docs/reliability/evidence/parameter-surface.json`;
  - pluginval at strictness 10 on the VST3.
- **Validated after installation** (`f5cb173`): `auval`, `auval -strict` and pluginval at strictness 10 on the installed AU.
- **Not established:** the host display behaviour above, and whether any real host replays a stored program number after a restore.
- Design and rationale: `docs/presets/factory-user-preset-architecture.md`, "Host programs".

## Non-Parameter State

For UI state (editor size, tab index) or non-automatable data:

```cpp
// In constructor — add a child ValueTree for UI state
apvts.state.addChild ({
    "uiState",
    {
        { "width",  400 },
        { "height", 300 },
        { "activeTab", 0 }
    },
    {}
}, -1, nullptr);

// Read in editor constructor
auto uiState = processor.apvts.state.getChildWithName ("uiState");
auto savedWidth  = uiState.getProperty ("width",  400);
auto savedHeight = uiState.getProperty ("height", 300);

// Save in editor destructor
auto& uiState = processor.apvts.state.getChildWithName ("uiState");
uiState.setProperty ("width",  getWidth(), nullptr);
uiState.setProperty ("height", getHeight(), nullptr);
```

This state is automatically included in `getStateInformation`/`setStateInformation` since it's a child of the APVTS state tree.

## Parameter Groups

Organize parameters in the host UI:

```cpp
juce::AudioProcessorValueTreeState::ParameterLayout createParameterLayout()
{
    return {
        juce::AudioProcessorParameterGroup (
            "osc", "Oscillator", "|",
            std::make_unique<juce::AudioParameterFloat> (
                juce::ParameterID { "oscTune", 1 }, "Tune",
                juce::NormalisableRange<float> (-12.0f, 12.0f, 0.01f), 0.0f),
            std::make_unique<juce::AudioParameterChoice> (
                juce::ParameterID { "oscWave", 1 }, "Waveform",
                juce::StringArray { "Sine", "Saw", "Square" }, 0)),

        juce::AudioProcessorParameterGroup (
            "filter", "Filter", "|",
            std::make_unique<juce::AudioParameterFloat> (
                juce::ParameterID { "filterCutoff", 1 }, "Cutoff",
                juce::NormalisableRange<float> (20.0f, 20000.0f), 1000.0f),
            std::make_unique<juce::AudioParameterFloat> (
                juce::ParameterID { "filterRes", 1 }, "Resonance",
                juce::NormalisableRange<float> (0.0f, 1.0f), 0.5f))
    };
}
```

Note: some hosts flatten groups and ignore the hierarchy.

## Parameter Attributes (Advanced)

Customize parameter appearance in the host:

```cpp
std::make_unique<juce::AudioParameterFloat>(
    juce::ParameterID { "mix", 1 },
    juce::AudioParameterValueTreeStateParameterAttributes()
        .withStringFromValueFunction (
            [] (float value, int) -> juce::String {
                return juce::String (static_cast<int> (value * 100)) + "%";
            })
        .withValueFromStringFunction (
            [] (const juce::String& text) -> float {
                return text.retainCharacters ("0123456789.").getFloatValue() / 100.0f;
            })
        .withLabel ("%"),
    "Dry/Wet Mix",
    juce::NormalisableRange<float> (0.0f, 1.0f),
    0.5f)
```

## Gain Ramping (Avoiding Zipper Noise)

Applying parameter values directly in `processBlock` causes zipper noise — audible clicks when values change between blocks. Always smooth parameter changes:

```cpp
// In processor header:
float previousGain = 0.0f;

// In prepareToPlay (not constructor — param value may change before audio starts):
previousGain = *gainParam;

// In processBlock:
auto currentGain = gainParam->load();

if (juce::approximatelyEqual (currentGain, previousGain))
{
    buffer.applyGain (currentGain);
}
else
{
    buffer.applyGainRamp (0, buffer.getNumSamples(), previousGain, currentGain);
    previousGain = currentGain;
}
```

The `dsp::Gain` processor handles this automatically with `setRampDurationSeconds()`, but for manual gain application, `applyGainRamp()` is the standard approach.

## Responding to Parameter Changes

To react when a parameter changes (e.g., recalculating coefficients):

```cpp
// In processor constructor:
apvts.addParameterListener ("filterCutoff", this);

// Make processor inherit from AudioProcessorValueTreeState::Listener
void parameterChanged (const juce::String& parameterID, float newValue) override
{
    if (parameterID == "filterCutoff")
        recalculateFilterCoefficients (newValue);
}
```

Warning: `parameterChanged` may be called on the audio thread. Only do trivial, allocation-free work here. For heavier work, set an atomic flag and pick it up in `processBlock` or a timer. Never post to the message thread from it (`AsyncUpdater`, `ChangeBroadcaster`, `callAsync`): [host-automation-and-editor-sync.md](host-automation-and-editor-sync.md#anti-patterns).
