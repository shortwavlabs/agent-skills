# DSP Patterns

Common audio DSP patterns using the `juce::dsp` module. All patterns follow the prepare/process/reset lifecycle.

## Core Concepts

```cpp
// ProcessSpec — passed to prepare()
struct ProcessSpec {
    double sampleRate;
    uint32 numChannels;
    uint32 maximumBlockSize;
};

// AudioBlock — lightweight view into sample data (no allocation)
AudioBlock<float> block (buffer);
AudioBlock<float> channelBlock = block.getSubsetChannelBlock (0, numChannels);

// ProcessContext — wraps input/output blocks
ProcessContextReplacing<float> context (channelBlock);   // in-place
// ProcessContextNonReplacing<float> context (inputBlock, outputBlock);  // separate I/O
```

## ProcessorChain — Composing DSP Stages

`ProcessorChain` chains multiple processors that all implement `prepare()`, `process()`, and `reset()`:

```cpp
// Define a chain type
using FilterBand = juce::dsp::ProcessorDuplicator<
    juce::dsp::IIR::Filter<float>,
    juce::dsp::IIR::Coefficients<float>>;

using Chain = juce::dsp::ProcessorChain<
    juce::dsp::Gain<float>,        // index 0: input gain
    FilterBand,                     // index 1: low-pass filter
    juce::dsp::Gain<float>>;       // index 2: output gain

Chain chain;

// prepare
void prepareToPlay (double sampleRate, int samplesPerBlock) override
{
    juce::dsp::ProcessSpec spec { sampleRate, (uint32) samplesPerBlock, 2 };
    chain.prepare (spec);
    updateFilter();
}

// process
void processBlock (AudioBuffer<float>& buffer, MidiBuffer&) override
{
    auto block = juce::dsp::AudioBlock<float> (buffer);
    auto context = juce::dsp::ProcessContextReplacing<float> (block);
    chain.process (context);
}

// Access individual stages by index
void updateFilter()
{
    auto& filter = chain.get<1>();
    *filter.state = *juce::dsp::IIR::Coefficients<float>::makeLowPass (
        getSampleRate(), cutoffFrequency);
}
```

## Oscillator

```cpp
juce::dsp::Oscillator<float> oscillator;

// In prepareToPlay:
oscillator.prepare (spec);

// In constructor or prepare:
oscillator.initialise ([] (float x) { return std::sin (x); });  // sine
oscillator.initialise ([] (float x) {                           // sawtooth
    return (2.0f / MathConstants<float>::pi) * std::atan (std::tan (x * 0.5f));
});

// Built-in waveforms via template parameter:
juce::dsp::Oscillator<float, juce::dsp::Oscillator<float>::WaveShape::saw> sawOsc;
```

## IIR Filter

```cpp
// Mono filter — use ProcessorDuplicator for stereo
using StereoFilter = juce::dsp::ProcessorDuplicator<
    juce::dsp::IIR::Filter<float>,
    juce::dsp::IIR::Coefficients<float>>;

StereoFilter lowPass;

// Coefficient generators (static methods):
*lowPass.state = *juce::dsp::IIR::Coefficients<float>::makeLowPass  (sampleRate, freq);
*lowPass.state = *juce::dsp::IIR::Coefficients<float>::makeHighPass (sampleRate, freq);
*lowPass.state = *juce::dsp::IIR::Coefficients<float>::makeBandPass (sampleRate, freq);
*lowPass.state = *juce::dsp::IIR::Coefficients<float>::makePeakFilter (sampleRate, freq, Q, gainFactor);
```

## State Variable Filter (TPT)

Better for modulation than IIR — no transient artifacts when coefficients change:

```cpp
juce::dsp::StateVariableTPTFilter<float> svf;

svf.prepare (spec);
svf.setCutoffFrequency (1000.0f);
svf.setResonance (0.707f);
svf.setType (juce::dsp::StateVariableTPTFilter<float>::Type::lowpass);
// Types: lowpass, bandpass, highpass

// Process per-sample:
auto filteredSample = svf.processSample (channel, inputSample);
```

## FIR Filter

```cpp
juce::dsp::FIR::Filter<float> firFilter;

// Design a windowed-sinc lowpass
auto coefficients = juce::dsp::FilterDesign<float>::designFIRLowpassWindowMethod (
    cutoffFrequency, sampleRate, filterOrder,
    juce::dsp::WindowingFunction<float>::hamming);

*firFilter.coefficients = *coefficients;
```

## Gain

```cpp
juce::dsp::Gain<float> gain;
gain.prepare (spec);
gain.setGainLinear (0.5f);       // linear scale
gain.setGainDecibels (-6.0f);    // dB scale
gain.setRampDurationSeconds (0.05);  // smooth transitions
```

## WaveShaper (Distortion)

```cpp
// Tanh soft clipping
juce::dsp::WaveShaper<float> waveshaper ([] (float x) {
    return std::tanh (x);
});

// Hard clipping
juce::dsp::WaveShaper<float> clipper ([] (float x) {
    return juce::jlimit (-1.0f, 1.0f, x);
});

// Cubic soft clip (fast approximation)
juce::dsp::WaveShaper<float> cubicClip ([] (float x) {
    if (x > 1.0f) return 1.0f;
    if (x < -1.0f) return -1.0f;
    return x - (1.0f / 3.0f) * x * x * x;
});
```

## Convolution (Reverb)

```cpp
juce::dsp::Convolution convolution;

// Load impulse response
void prepareToPlay (double sampleRate, int samplesPerBlock) override
{
    juce::dsp::ProcessSpec spec { sampleRate, (uint32) samplesPerBlock, 2 };
    convolution.prepare (spec);

    // From file
    juce::File irFile = juce::File::getSpecialLocation (juce::File::currentApplicationFile)
        .getParentDirectory().getChildFile ("ir.wav");
    convolution.loadImpulseResponse (irFile,
        juce::dsp::Convolution::Stereo::yes,
        juce::dsp::Convolution::Trim::yes,
        0);  // size override (0 = use IR size)

    // Or from BinaryData (embedded)
    convolution.loadImpulseResponse (
        BinaryData::reverb_ir_wav, BinaryData::reverb_ir_wavSize,
        juce::dsp::Convolution::Stereo::yes,
        juce::dsp::Convolution::Trim::yes,
        0);
}

// Process as part of chain
convolution.process (context);
```

## Delay Line

```cpp
juce::dsp::DelayLine<float> delayLine;

delayLine.prepare (spec);
delayLine.setMaximumDelayInSamples (static_cast<int> (sampleRate * 2.0));  // 2 sec max
delayLine.setDelay (delayInSamples);

// Per-sample processing:
delayLine.pushSample (channel, inputSample);
auto delayed = delayLine.popSample (channel);
```

## Ladder Filter (Moog-style)

```cpp
juce::dsp::LadderFilter<float> ladder;

ladder.prepare (spec);
ladder.setCutoffFrequencyHz (cutoff);
ladder.setResonance (resonance);  // 0.0 to 1.0
ladder.setDrive (drive);          // 1.0 = normal, higher = more distortion
ladder.setEnabled (true);

// Process per-sample or via context
ladder.process (context);
```

## Per-Sample Processing Pattern

When you need sample-by-sample control (feedback loops, modulation):

```cpp
void processBlock (AudioBuffer<float>& buffer, MidiBuffer&) override
{
    auto block = juce::dsp::AudioBlock<float> (buffer);
    auto context = juce::dsp::ProcessContextReplacing<float> (block);

    for (int ch = 0; ch < buffer.getNumChannels(); ++ch)
    {
        auto* samples = buffer.getWritePointer (ch);
        for (int s = 0; s < buffer.getNumSamples(); ++s)
        {
            auto input = samples[s];

            // Per-sample DSP here
            auto filtered = svf.processSample (ch, input);
            auto delayed = delayLine.popSample (ch);
            delayLine.pushSample (ch, filtered + delayed * feedback);
            auto output = filtered + delayed;

            samples[s] = output;
        }
    }

    svf.snapToZero();  // avoid denormal accumulation
}
```

## Chorus Effect

```cpp
// Multiple modulated delay lines with LFO
class Chorus
{
    std::array<juce::dsp::DelayLine<float>, 2> delayLines {
        juce::dsp::DelayLine<float> (96000),
        juce::dsp::DelayLine<float> (96000)
    };
    juce::dsp::Oscillator<float> lfo;

    Chorus() : lfo ([] (float x) { return std::sin (x); })
    {
        lfo.prepare (spec);
        lfo.setFrequency (0.5f);  // 0.5 Hz modulation rate
    }

    void process (AudioBuffer<float>& buffer)
    {
        for (int ch = 0; ch < 2; ++ch)
        {
            for (int s = 0; s < buffer.getNumSamples(); ++s)
            {
                auto mod = lfo.processSample (ch);
                auto delaySamples = baseDelay + mod * depth;
                delayLines[ch].setDelay (delaySamples);
                delayLines[ch].pushSample (ch, buffer.getSample (ch, s));
                auto delayed = delayLines[ch].popSample (ch);
                buffer.setSample (ch, s, buffer.getSample (ch, s) * dryMix + delayed * wetMix);
            }
        }
    }
};
```

## Multiband Split

```cpp
// Linkwitz-Riley crossover for lossless band splitting
juce::dsp::LinkwitzRileyFilter<float> crossover;
// crossover.setCutoffFrequency (cutoffFreq);
// Low output = lowpass, High output = highpass
// Sum of low + high = original signal (phase-coherent)
```

## Wavetable Synthesis

Pre-computing one cycle of a waveform into a table, then reading back with linear interpolation. This trades memory for CPU — significantly faster than calling `std::sin()` per sample, especially with many voices.

```cpp
class WavetableOscillator
{
public:
    WavetableOscillator (const juce::AudioSampleBuffer& wavetable)
        : wavetable (wavetable), tableSize ((int) wavetable.getNumSamples() - 1)
    {
        jassert (wavetable.getNumChannels() == 1);
    }

    void prepare (double sampleRate)
    {
        tableDelta = frequency * (float) tableSize / (float) sampleRate;
    }

    void setFrequency (float freq, double sampleRate)
    {
        frequency = freq;
        tableDelta = freq * (float) tableSize / (float) sampleRate;
    }

    float getNextSample() noexcept
    {
        auto index0 = (unsigned int) currentIndex;
        auto index1 = index0 + 1;  // safe: table has wrap guard
        auto frac = currentIndex - (float) index0;

        auto* table = wavetable.getReadPointer (0);
        auto value0 = table[index0];
        auto value1 = table[index1];
        auto currentSample = value0 + frac * (value1 - value0);

        currentIndex += tableDelta;
        while (currentIndex >= (float) tableSize)
            currentIndex -= (float) tableSize;

        return currentSample;
    }

private:
    const juce::AudioSampleBuffer& wavetable;
    int tableSize;
    float currentIndex = 0.0f, tableDelta = 0.0f, frequency = 440.0f;
};
```

Key: `tableSize` is `getNumSamples() - 1` because the last sample is a wrap guard — a copy of the first sample. This eliminates a conditional branch in `getNextSample()` since `index1 = index0 + 1` is always valid.

### Generating Harmonic Wavetables

```cpp
juce::AudioSampleBuffer generateWavetable (int tableSize)
{
    juce::AudioSampleBuffer table (1, tableSize + 1);  // +1 for wrap guard
    auto* samples = table.getWritePointer (0);

    int harmonics[] = { 1, 3, 5, 7, 9, 13, 15 };
    float harmonicWeights[] = { 0.5f, 0.1f, 0.05f, 0.09f, 0.005f, 0.002f, 0.001f };

    for (auto harmonic = 0; harmonic < numElementsInArray (harmonics); ++harmonic)
    {
        auto angleDelta = MathConstants<double>::twoPi / (double) (tableSize - 1)
                          * harmonics[harmonic];
        auto currentAngle = 0.0;

        for (unsigned int i = 0; i < tableSize; ++i)
        {
            auto sample = std::sin (currentAngle);
            samples[i] += (float) sample * harmonicWeights[harmonic];
            currentAngle += angleDelta;
        }
    }

    samples[tableSize] = samples[0];  // wrap guard
    return table;
}
```

Note: adding high harmonics causes aliasing if they exceed Nyquist. For production, use band-limited wavetables (multiple tables per octave, crossfade between them).

## LFO at Control Rate

LFOs are control-rate, not audio-rate. They should NOT be in the ProcessorChain — run them separately and apply their output to parameters at a reduced update rate:

```cpp
static constexpr size_t lfoUpdateRate = 100;  // update every 100 samples
size_t lfoUpdateCounter = lfoUpdateRate;
juce::dsp::Oscillator<float> lfo;

// In prepare — run at reduced rate:
lfo.prepare ({ spec.sampleRate / lfoUpdateRate, spec.maximumBlockSize, spec.numChannels });

// In processBlock — manual block splitting:
for (size_t pos = 0; pos < (size_t) numSamples;)
{
    auto max = juce::jmin ((size_t) numSamples - pos, lfoUpdateCounter);
    auto block = audioBlock.getSubBlock (pos, max);
    juce::dsp::ProcessContextReplacing<float> context (block);
    processorChain.process (context);
    pos += max;
    lfoUpdateCounter -= max;

    if (lfoUpdateCounter == 0)
    {
        lfoUpdateCounter = lfoUpdateRate;
        auto lfoOut = lfo.processSample (0.0f);
        auto cutoffFreq = juce::jmap (lfoOut, -1.0f, 1.0f, 100.0f, 2000.0f);
        processorChain.get<filterIndex>().setCutoffFrequencyHz (cutoffFreq);
    }
}
```

## Two-Level Chain Architecture (Per-Voice + Engine FX)

For synths, each voice has its own ProcessorChain for oscillators/filters/gain. Shared effects like reverb go on the engine level:

```cpp
// Per-voice chain (inside SynthesiserVoice)
enum { oscIndex, filterIndex, gainIndex };
juce::dsp::ProcessorChain<juce::dsp::Oscillator<float>,
                          juce::dsp::StateVariableTPTFilter<float>,
                          juce::dsp::Gain<float>> voiceChain;

// Engine-level chain (inside Synthesiser subclass)
enum { reverbIndex };
juce::dsp::ProcessorChain<juce::dsp::Reverb> fxChain;

// Override renderNextSubBlock to apply engine FX after all voices render:
void renderNextSubBlock (AudioBuffer<float>& output, int startSample, int numSamples) override
{
    Synthesiser::renderNextSubBlock (output, startSample, numSamples);  // render all voices
    auto block = juce::dsp::AudioBlock<float> (output)
                    .getSubBlock ((size_t) startSample, (size_t) numSamples);
    juce::dsp::ProcessContextReplacing<float> context (block);
    fxChain.process (context);  // apply shared FX
}
```

## Delay with Feedback and Saturation

The `tanh` soft-clip on the feedback path prevents runaway feedback — a standard DSP technique for natural-sounding delays:

```cpp
for (int s = 0; s < numSamples; ++s)
{
    auto delayedSample = delayLine.popSample (channel);
    auto inputSample = buffer.getSample (channel, s);

    // Soft-clip the feedback to prevent runaway
    auto dlineInput = std::tanh (inputSample + feedback * delayedSample);
    delayLine.pushSample (channel, dlineInput);

    auto output = inputSample + wetLevel * delayedSample;
    buffer.setSample (channel, s, output);
}
```

### Filtered feedback (darker repeats — more realistic)

```cpp
// Filter the delayed sample before feeding back
auto filteredDelayed = feedbackFilter.processSample (channel, delayedSample);
auto dlineInput = std::tanh (inputSample + feedback * filteredDelayed);
```

Use `IIR::Coefficients::makeFirstOrderLowPass` for natural decay (high frequencies die first), or `makeFirstOrderHighPass` for lo-fi bright repeats.

## Distortion Signal Chain

The standard distortion chain: filter → pre-gain → waveshaper → post-gain:

```cpp
enum { filterIndex, preGainIndex, waveshaperIndex, postGainIndex };

juce::dsp::ProcessorChain<
    juce::dsp::ProcessorDuplicator<juce::dsp::IIR::Filter<float>,
                                    juce::dsp::IIR::Coefficients<float>>,
    juce::dsp::Gain<float>,
    juce::dsp::WaveShaper<float>,
    juce::dsp::Gain<float>
> distortionChain;

// Setup:
auto& preGain = distortionChain.get<preGainIndex>();
preGain.setGainDecibels (30.0f);  // drive into saturation

auto& waveshaper = distortionChain.get<waveshaperIndex>();
waveshaper.functionToUse = [] (float x) { return std::tanh (x); };

auto& postGain = distortionChain.get<postGainIndex>();
postGain.setGainDecibels (-20.0f);  // trim after saturation

// High-pass before distortion prevents muddy low-frequency buildup
auto& filter = distortionChain.get<filterIndex>();
*filter.state = *juce::dsp::IIR::Coefficients<float>::makeFirstOrderHighPass (sampleRate, 200.0f);
```

## HeapBlock for Temporary Buffers

Pre-allocated temporary buffers for multi-voice rendering:

```cpp
juce::HeapBlock<char> heapBlock;
juce::dsp::AudioBlock<float> tempBlock;

// In prepare:
tempBlock = juce::dsp::AudioBlock<float> (heapBlock, spec.numChannels, spec.maximumBlockSize);

// In process — use tempBlock as scratch, then add to output:
auto output = tempBlock.getSubBlock (0, (size_t) numSamples);
output.clear();
// ... render voices into output ...
juce::dsp::AudioBlock<float> (buffer).getSubBlock (0, (size_t) numSamples).add (tempBlock);
```
