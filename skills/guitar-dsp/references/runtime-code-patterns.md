# Runtime Code Patterns

## Contents

- Use these patterns carefully
- Parameter snapshot boundary
- RTNeural model handoff
- Per-channel model state
- Cabinet or IR engine handoff
- Smoothing and coefficient updates
- Latency and tail updates
- CMake and test target shape

## Use These Patterns Carefully

These snippets are intentionally small and incomplete. Adapt them to the owning project's style, thread model, and existing helpers. Keep the invariant: the audio callback consumes prepared immutable state and simple parameter snapshots.

## Parameter Snapshot Boundary

Do not read APVTS, build strings, or traverse UI/state trees in DSP classes. Take a plain snapshot at the processor edge.

```cpp
struct DriveParameters
{
    bool enabled = false;
    float gain = 35.0f;
    float tone = 50.0f;
    float levelDb = 0.0f;
};

DriveParameters AudioProcessorImpl::loadDriveParameters() const noexcept
{
    DriveParameters p;
    p.enabled = getBool ("drive_enabled");
    p.gain = getFloat ("drive_gain");
    p.tone = getFloat ("drive_tone");
    p.levelDb = getFloat ("drive_level_db");
    return p;
}

void AudioProcessorImpl::processBlock (juce::AudioBuffer<float>& buffer,
                                       juce::MidiBuffer&)
{
    juce::ScopedNoDenormals noDenormals;
    drive.processBlock (buffer, loadDriveParameters());
}
```

The DSP block should clamp/sanitize the snapshot once per block, then smooth toward targets sample-by-sample or at a bounded control rate.

## RTNeural Model Handoff

Construct and validate model state outside the callback. Publish only a pointer to a complete runtime object.

```cpp
struct ModelRuntime
{
    std::vector<std::unique_ptr<RTNeural::Model<float>>> channels;
    int sampleRate = 48000;
    int trueLatencySamples = 0;
    float outputGain = 1.0f;
};

std::atomic<ModelRuntime*> activeModel { nullptr };
std::shared_ptr<ModelRuntime> ownedModel;
std::vector<std::shared_ptr<ModelRuntime>> retiredModels;

void publishModel (std::shared_ptr<ModelRuntime> next)
{
    auto* raw = next.get();
    auto previous = std::move (ownedModel);
    ownedModel = std::move (next);
    activeModel.store (raw, std::memory_order_release);

    if (previous != nullptr)
        retiredModels.push_back (std::move (previous));
}

ModelRuntime* model = activeModel.load (std::memory_order_acquire);
```

Retire old runtimes on a non-audio thread after a safe interval or with an existing audio-thread epoch mechanism. Never let `shared_ptr` reference count destruction of heavy objects happen from the callback.

## Per-Channel Model State

Stateful causal models need independent state per channel.

```cpp
for (int ch = 0; ch < channelsToProcess; ++ch)
{
    auto* data = buffer.getWritePointer (ch);
    auto& model = *runtime.channels[static_cast<size_t> (ch)];

    for (int n = 0; n < numSamples; ++n)
        data[n] = sanitize (model.forward ({ data[n] })[0] * runtime.outputGain);
}
```

For mono amp cores, fold intentionally and process once:

```cpp
for (int n = 0; n < numSamples; ++n)
{
    float mono = 0.0f;
    for (int ch = 0; ch < channelsToFold; ++ch)
        mono += buffer.getReadPointer (ch)[n];

    mono /= static_cast<float> (channelsToFold);
    scratch[n] = monoModel.forward ({ mono })[0];
}

for (int ch = 0; ch < channelsToOutput; ++ch)
    std::copy (scratch.begin(), scratch.begin() + numSamples, buffer.getWritePointer (ch));
```

## Cabinet Or IR Engine Handoff

Use immutable engines for user-loaded IRs. Load, resample, normalize, and construct the convolution state before publication.

```cpp
struct CabinetEngine
{
    int latencySamples = 0;
    double sampleRate = 48000.0;
    void process (juce::AudioBuffer<float>& buffer) noexcept;
};

std::atomic<CabinetEngine*> activeCabinet { nullptr };

void CabinetStage::processBlock (juce::AudioBuffer<float>& buffer,
                                 const CabinetParameters& p) noexcept
{
    auto* engine = activeCabinet.load (std::memory_order_acquire);
    if (engine == nullptr || ! p.enabled)
    {
        filterOnlyPath.processBlock (buffer, p);
        return;
    }

    engine->process (buffer);
    postFilters.processBlock (buffer, p);
}
```

Update host latency and tail from the message/processor side after publishing a new engine.

## Smoothing And Coefficient Updates

Use a target smoother for continuous controls and a dirty flag for coefficient rebuilds.

```cpp
void ToneStage::setTargets (float bassDb, float trebleDb) noexcept
{
    targetBass = juce::jlimit (-12.0f, 12.0f, bassDb);
    targetTreble = juce::jlimit (-12.0f, 12.0f, trebleDb);
}

void ToneStage::processSampleBlock (float* data, int numSamples) noexcept
{
    for (int n = 0; n < numSamples; ++n)
    {
        bass = smoothTowards (bass, targetBass, smoothingCoefficient);
        treble = smoothTowards (treble, targetTreble, smoothingCoefficient);

        if ((n & 15) == 0 && coefficientsMovedEnough())
            updateFilters();

        data[n] = filters.process (data[n]);
    }
}
```

For stepped modes or routing changes, prefer short crossfades over abrupt branch switches unless tests prove the transition is click-free.

## Latency And Tail Updates

Use `setLatencySamples()` only for true delayed output. Causal model memory and export alignment are not automatically host latency.

When convolution, lookahead, or another real delay changes:

1. Publish the new runtime state.
2. Update the processor's reported latency from a safe thread.
3. Notify the host when required by the framework/project.
4. Add an impulse render test so future changes do not drift.

Report plugin tail for delay/reverb/cabinet behavior that continues after input silence. Keep zero-mix and disabled cases honest when the host relies on tail length.

## CMake And Test Target Shape

Production guitar plugins benefit from separate fast tests and slower measurement targets:

```cmake
add_executable(DspTests
    tests/DspTests.cpp
    Source/dsp/Drive.cpp
    Source/dsp/Cabinet.cpp)

target_link_libraries(DspTests PRIVATE juce::juce_dsp)

add_executable(DspMeasurementHarness
    tools/DspMeasurementHarness.cpp
    Source/dsp/Drive.cpp
    Source/dsp/Cabinet.cpp)
```

Keep the measurement target out of normal plugin runtime. It can render CSV/WAV fixtures, run longer sweeps, and collect spectra without adding callback instrumentation to the plugin.
