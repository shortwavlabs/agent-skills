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
