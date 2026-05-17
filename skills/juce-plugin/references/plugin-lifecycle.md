# AudioProcessor Lifecycle

The complete contract for subclassing `juce::AudioProcessor`. Every override the host expects, organized by category.

## Constructor Pattern

```cpp
MyProcessor()
    : AudioProcessor (BusesProperties()
        .withInput  ("Input",  juce::AudioChannelSet::stereo())
        .withOutput ("Output", juce::AudioChannelSet::stereo())),
      apvts (*this, nullptr, "Parameters", createParameterLayout())
{
}
```

Bus layout options:
- `AudioChannelSet::mono()` — single channel
- `AudioChannelSet::stereo()` — left + right
- `AudioChannelSet::createLCR()` — 3-channel surround
- `AudioChannelSet::quadraphonic()` — 4-channel
- `AudioChannelSet::create5point1()` — 5.1 surround
- `AudioChannelSet::disabled()` — no channels (for MIDI-only buses)

Chain `.withInput()` / `.withOutput()` calls for multiple buses (e.g., sidechain).

## Mandatory Overrides

### Audio Processing

```cpp
void prepareToPlay (double sampleRate, int samplesPerBlock) override
{
    // Called when playback starts or sample rate/block size changes.
    // Allocate buffers, initialize DSP state, reset phase accumulators.
    // This is the ONLY safe place to allocate memory.
}

void releaseResources() override
{
    // Called when playback stops. Free large buffers if needed.
    // Not always called — don't rely on it for critical cleanup.
}

void processBlock (AudioBuffer<float>& buffer, MidiBuffer& midiMessages) override
{
    // THE audio callback. Runs on real-time thread.
    // See audio-thread-safety.md for rules.
    juce::ScopedNoDenormals noDenormals;

    auto totalNumInputChannels  = getTotalNumInputChannels();
    auto totalNumOutputChannels = getTotalNumOutputChannels();

    // Clear unused output channels (important for effects with mono-in/stereo-out)
    for (auto i = totalNumInputChannels; i < totalNumOutputChannels; ++i)
        buffer.clear (i, 0, buffer.getNumSamples());

    // Process audio here...
}
```

Optional: override `processBlock(AudioBuffer<double>&, MidiBuffer&)` for double-precision processing. Also set `supportsDoublePrecisionProcessing()` to return `true`.

### Editor

```cpp
bool hasEditor() const override { return true; }

AudioProcessorEditor* createEditor() override
{
    // Option 1: Custom editor
    return new MyEditor (*this);

    // Option 2: Auto-generated generic editor (good for prototyping)
    return new juce::GenericAudioProcessorEditor (*this);
}
```

### Plugin Info

```cpp
const juce::String getName() const override             { return "My Plugin"; }
bool acceptsMidi() const override                       { return false; }  // true for synths
bool producesMidi() const override                      { return false; }  // true for arpeggiators etc.
double getTailLengthSeconds() const override             { return 0.0; }    // reverb tail, etc.
```

### Program/Preset Slots

```cpp
int getNumPrograms() override                           { return 1; }      // minimum 1
int getCurrentProgram() override                        { return 0; }
void setCurrentProgram (int index) override             {}
const juce::String getProgramName (int index) override  { return "Init"; }
void changeProgramName (int index, const juce::String& newName) override {}
```

### State Serialization

```cpp
void getStateInformation (MemoryBlock& destData) override
{
    // Save plugin state (called by host for project save, preset save)
    auto state = apvts.copyState();
    if (auto xml = state.createXml())
        copyXmlToBinary (*xml, destData);
}

void setStateInformation (const void* data, int sizeInBytes) override
{
    // Restore plugin state (called by host when loading project/preset)
    if (auto xml = getXmlFromBinary (data, sizeInBytes))
        if (xml->hasTagName (apvts.state.getType()))
            apvts.replaceState (ValueTree::fromXml (*xml));
}
```

## Important Optional Overrides

### Bus Layout Validation

```cpp
bool isBusesLayoutSupported (const BusesLayout& layouts) const override
{
    // Enforce which I/O configurations this plugin supports
    const auto& mainIn  = layouts.getChannelSet (true, 0);
    const auto& mainOut = layouts.getChannelSet (false, 0);

    // Must have matching in/out, at least stereo
    return (mainIn == mainOut && ! mainIn.isDisabled());
}
```

### Latency Reporting

```cpp
latencySamples = myDelayLine.getDelaySamples();  // call when delay changes
// The base class getLatencySamples() reports this to the host automatically
```

### Track Properties (host tells plugin about the track)

```cpp
void updateTrackProperties (const TrackProperties& properties) override
{
    // properties.name = track name in DAW
    // properties.colour = track colour
    // properties.tags = track tags (JUCE 8+)
}
```

## Synthesizer Plugin Pattern

For synths, use the `Synthesiser` framework inside your AudioProcessor:

```cpp
class MySynthProcessor : public AudioProcessor
{
    Synthesiser synth;

    void prepareToPlay (double sampleRate, int samplesPerBlock) override
    {
        synth.setCurrentPlaybackSampleRate (sampleRate);

        // Add voices (polyphony count)
        for (auto i = 0; i < 16; ++i)
            synth.addVoice (new MySynthVoice());

        synth.addSound (new MySynthSound());
    }

    void processBlock (AudioBuffer<float>& buffer, MidiBuffer& midi) override
    {
        buffer.clear();
        synth.renderNextBlock (buffer, midi, 0, buffer.getNumSamples());
    }
};
```

### SynthesiserVoice

Override these methods:

```cpp
class MySynthVoice : public SynthesiserVoice
{
    bool canPlaySound (SynthesiserSound* sound) override;

    void startNote (int midiNoteNumber, float velocity,
                    SynthesiserSound* sound, int currentPitchWheelPosition) override
    {
        // Called on Note On. Initialize oscillator phase, set level from velocity.
        auto freq = MidiMessage::getMidiNoteInHertz (midiNoteNumber);
        auto cyclesPerSample = freq / getSampleRate();
        angleDelta = cyclesPerSample * MathConstants<double>::twoPi;
        level = velocity * 0.15;
    }

    void stopNote (float velocity, bool allowTailOff) override
    {
        // Called on Note Off. Either begin tail-off or clear immediately.
        if (allowTailOff) { tailOff = 1.0; }
        else { clearCurrentNote(); angleDelta = 0.0; }
    }

    void renderNextBlock (AudioBuffer<float>& output, int startSample, int numSamples) override
    {
        // Render audio samples into the buffer
        if (! approximatelyEqual (angleDelta, 0.0))
        {
            while (--numSamples >= 0)
            {
                auto sample = (float) (std::sin (currentAngle) * level * tailOff);
                for (int ch = 0; ch < output.getNumChannels(); ++ch)
                    output.addSample (ch, startSample, sample);

                currentAngle += angleDelta;
                ++startSample;
            }
        }
    }

    void pitchWheelMoved (int newValue) override {}
    void controllerMoved (int controllerNumber, int newValue) override {}

private:
    double currentAngle = 0.0, angleDelta = 0.0, level = 0.0, tailOff = 0.0;
};
```

### SynthesiserSound

Minimal — just defines which notes/channels this sound applies to:

```cpp
class MySynthSound : public SynthesiserSound
{
    bool appliesToNote (int) override    { return true; }
    bool appliesToChannel (int) override { return true; }
};
```

## Accessing Bus Buffers

For multi-bus plugins (sidechain, surround):

```cpp
// Main input bus (bus 0)
auto mainInput = getBusBuffer (buffer, true, 0);

// Sidechain input (bus 1)
auto sidechain = getBusBuffer (buffer, true, 1);

// Main output bus (bus 0)
auto mainOutput = getBusBuffer (buffer, false, 0);
```

## Double Precision

```cpp
bool supportsDoublePrecisionProcessing() const override { return true; }

void processBlock (AudioBuffer<float>& buffer, MidiBuffer& midi) override
{
    jassert (! isUsingDoublePrecision());
    processInternal (buffer, midi);
}

void processBlock (AudioBuffer<double>& buffer, MidiBuffer& midi) override
{
    jassert (isUsingDoublePrecision());
    processInternal (buffer, midi);
}

template <typename FloatType>
void processInternal (AudioBuffer<FloatType>& buffer, MidiBuffer& midi)
{
    // Shared implementation
}
```
