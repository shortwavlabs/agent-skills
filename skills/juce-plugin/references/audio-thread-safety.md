# Audio Thread Safety

The real-time audio thread has strict constraints. Violating these causes audible glitches (clicks, pops, dropouts) that ruin the user experience.

## The Rules

### NEVER allocate memory on the audio thread

Memory allocation can trigger OS-level locks (malloc, mmap, page faults). These are unbounded — they can take milliseconds, causing buffer underruns.

**Banned in `processBlock()`:**
- `new`, `delete`, `malloc`, `free`
- `std::vector::push_back()`, `std::string` concatenation
- `juce::String` construction or concatenation
- `juce::Array`, `juce::HashMap` operations that grow
- `juce::File` operations
- Creating any `juce::Component` or `juce::Graphics`

**Allowed:**
- Stack allocation of POD types
- Reading from pre-allocated containers (no growth)
- `std::atomic` operations

### NEVER use locks on the audio thread

`std::mutex`, `CriticalSection`, `SpinLock` — any lock that could block is forbidden. Priority inversion will cause audio glitches.

**Use instead:**
- `std::atomic<float>`, `std::atomic<bool>` for single values
- Lock-free queues (`juce::AbstractFifo`) for buffers
- SPSC (single-producer single-consumer) patterns
- RCU-style: atomically swap pointers to immutable data

### NEVER call blocking functions

- No file I/O
- No network calls
- No `sleep()` or `wait()`
- No `DBG()` in production (allocates strings)

## Parameter Access Pattern

```cpp
// CORRECT: Cache atomic pointers
class MyProcessor : public AudioProcessor
{
    std::atomic<float>* gainParam = nullptr;

    MyProcessor() : ..., apvts (...) {
        gainParam = apvts.getRawParameterValue ("gain");
    }

    void processBlock (AudioBuffer<float>& buffer, MidiBuffer&) override {
        auto gain = gainParam->load();  // atomic load, lock-free
        // ... use gain
    }
};

// WRONG: Calling getRawParameterValue inside processBlock
void processBlock (AudioBuffer<float>& buffer, MidiBuffer&) override {
    auto gain = apvts.getRawParameterValue ("gain")->load();  // string hash lookup every block
}
```

For large numbers of parameters, consider using the ParameterReferences struct pattern (see parameter-management.md) to avoid even the atomic overhead of many individual loads.

## Cross-Thread Communication

### Audio → UI (metering, peak levels)

```cpp
// Processor side (audio thread):
std::atomic<float> meterLevel { 0.0f };
meterLevel.store (currentPeak, std::memory_order_relaxed);

// Editor side (message thread):
void timerCallback() override {
    auto level = processor.meterLevel.load (std::memory_order_relaxed);
    meter.setLevel (level);
    meter.repaint();
}
```

### UI → Audio (updating coefficients)

```cpp
// When a parameter changes, recalculate coefficients
std::atomic<bool> coefficientsNeedUpdate { false };
juce::dsp::IIR::Coefficients<float>::Ptr newCoefficients;

// In parameterChanged (could be any thread):
void parameterChanged (const String&, float) override {
    // This is atomic-refcounted, so the assignment is safe
    newCoefficients = juce::dsp::IIR::Coefficients<float>::makeLowPass (sampleRate, cutoff);
    coefficientsNeedUpdate.store (true);
}

// In processBlock (audio thread):
if (coefficientsNeedUpdate.exchange (false)) {
    *filter.state = *newCoefficients;
}
```

## Pre-Allocation Pattern

Allocate everything in `prepareToPlay()`:

```cpp
class DelayEffect
{
    void prepare (const juce::dsp::ProcessSpec& spec)
    {
        // Pre-allocate maximum buffer size
        delayBuffer.setSize (spec.numChannels, spec.maximumBlockSize * 4);
        delayBuffer.clear();

        delayLine.prepare (spec);
        delayLine.setMaximumDelayInSamples ((int) (spec.sampleRate * 2.0));
    }

    void process (juce::AudioBuffer<float>& buffer)
    {
        // Use pre-allocated buffer — no allocation here
        // ...
    }

private:
    juce::AudioBuffer<float> delayBuffer;
    juce::dsp::DelayLine<float> delayLine;
};
```

## Common Pitfalls

| Pitfall | Symptom | Fix |
|---------|---------|-----|
| `std::vector::push_back()` in `processBlock` | Random clicks/pops | Pre-allocate in `prepareToPlay()` |
| `CriticalSection` in `processBlock` | Occasional dropouts under CPU load | Use `std::atomic` |
| `String` operations in `processBlock` | Subtle glitches on some systems | Use `std::atomic<float>*` for parameter reads |
| `DBG()` in release build audio code | Inexplicable performance issues | Remove all `DBG()` calls |
| `repaint()` from audio thread | Random crashes | Use atomic flag + timer instead |
| Creating objects in `processBlock` | Periodic glitches (GC/malloc pressure) | Create in `prepareToPlay()` or constructor |
| `parameterChanged` doing heavy work | Audio glitches when twisting knobs | Flag + defer to `processBlock` |

## Denormal Prevention

Denormal (subnormal) floats cause massive performance penalties on some CPUs — a single denormal operation can take 100x longer than normal. Always add at the top of `processBlock()`:

```cpp
void processBlock (AudioBuffer<float>& buffer, MidiBuffer&) override
{
    juce::ScopedNoDenormals noDenormals;
    // ...
}
```

Also call `snapToZero()` on filters after processing:

```cpp
filter.snapToZero();
```

## Debugging Audio Glitches

1. **Use `pluginval`** — the standard JUCE plugin validator. Catches threading, state, and parameter bugs.
   ```bash
   pluginval --validate-in-process /path/to/plugin.vst3
   ```

2. **Profile with Instruments/Very Sleepy** — look for syscalls or locks inside `processBlock`.

3. **Add timing assertions** (debug only):
   ```cpp
   void processBlock (AudioBuffer<float>& buffer, MidiBuffer&) override
   {
       juce::ScopedNoDenormals noDenormals;
       auto start = juce::Time::getHighResolutionTicks();

       // ... process ...

       auto elapsed = juce::Time::highResolutionTicksToSeconds (
           juce::Time::getHighResolutionTicks() - start);
       auto maxAllowed = buffer.getNumSamples() / getSampleRate();
       jassert (elapsed < maxAllowed * 0.5);  // warn if using >50% of available time
   }
   ```

4. **Test at small buffer sizes** — 32 or 64 samples. This stresses real-time behavior more than large buffers.
