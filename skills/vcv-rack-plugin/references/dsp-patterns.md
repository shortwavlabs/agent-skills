# DSP Patterns Cookbook

Common DSP patterns for VCV Rack module development.

## Oscillator (VCO)

```cpp
// Member variables
float phase = 0.f;

void process(const ProcessArgs& args) {
    float pitch = params[PITCH_PARAM].getValue();
    pitch += inputs[PITCH_INPUT].getVoltage();
    float freq = dsp::FREQ_C4 * std::pow(2.f, pitch);

    // Phase accumulator
    phase += freq * args.sampleTime;
    if (phase >= 1.f)
        phase -= 1.f;

    // Sine output
    float sine = std::sin(2.f * M_PI * phase);
    outputs[SINE_OUTPUT].setVoltage(5.f * sine);
}
```

### Bandlimited Saw (with anti-aliasing)

```cpp
#include <dsp/minblep.hpp>

float phase = 0.f;
dsp::MinBLEP<16> minblep;

void process(const ProcessArgs& args) {
    float freq = dsp::FREQ_C4 * std::pow(2.f, pitch);
    float delta = freq * args.sampleTime;

    float oldPhase = phase;
    phase += delta;

    // Detect phase wrap
    if (phase >= 1.f) {
        phase -= 1.f;
        // Add bandlimited step at discontinuity
        float crossing = -oldPhase / delta;
        minblep.insert(crossing, -1.f);
    }

    float saw = phase + minblep.process();
    outputs[OUTPUT].setVoltage(5.f * saw);
}
```

## Filter (VCF)

```cpp
dsp::BiquadFilter filter;

void onSampleRateChange() override {
    filter.setSampleRate(APP->engine->getSampleRate());
}

void process(const ProcessArgs& args) {
    float cutoff = params[CUTOFF_PARAM].getValue();
    cutoff += inputs[CUTOFF_INPUT].getVoltage() * 0.5f;
    cutoff = clamp(cutoff, 0.f, 1.f);
    float freq = dsp::FREQ_C4 * std::pow(2.f, cutoff * 10.f - 5.f);

    float resonance = params[RES_PARAM].getValue();
    float q = resonance * 10.f;

    filter.setParameters(dsp::BiquadFilter::LOWPASS, freq, q);

    float in = inputs[AUDIO_INPUT].getVoltage() / 5.f;
    float out = filter.process(in);
    outputs[AUDIO_OUTPUT].setVoltage(out * 5.f);
}
```

## Envelope Generator (ADSR)

```cpp
enum Stage { STOPPED, ATTACK, DECAY, SUSTAIN, RELEASE };
Stage stage = STOPPED;
float env = 0.f;
dsp::SchmittTrigger gateTrigger;

void process(const ProcessArgs& args) {
    float dt = args.sampleTime;

    // Gate detection
    bool gate = inputs[GATE_INPUT].getVoltage() > 1.f;

    if (gate && stage == STOPPED) {
        stage = ATTACK;
    } else if (!gate && stage != STOPPED) {
        stage = RELEASE;
    }

    float attack = std::max(params[ATTACK_PARAM].getValue(), 0.001f);
    float decay = std::max(params[DECAY_PARAM].getValue(), 0.001f);
    float sustain = params[SUSTAIN_PARAM].getValue();
    float release = std::max(params[RELEASE_PARAM].getValue(), 0.001f);

    switch (stage) {
        case ATTACK:
            env += dt / attack;
            if (env >= 1.f) { env = 1.f; stage = DECAY; }
            break;
        case DECAY:
            env -= dt / decay * (1.f - sustain);
            if (env <= sustain) { env = sustain; stage = SUSTAIN; }
            break;
        case SUSTAIN:
            env = sustain;
            break;
        case RELEASE:
            env -= dt / release * sustain;
            if (env <= 0.f) { env = 0.f; stage = STOPPED; }
            break;
        default:
            break;
    }

    outputs[ENV_OUTPUT].setVoltage(env * 10.f);
    lights[ACTIVE_LIGHT].setBrightness(env);
}
```

## Trigger and Gate Handling

```cpp
dsp::SchmittTrigger trigger;
dsp::PulseGenerator pulse;

void process(const ProcessArgs& args) {
    // Detect trigger rising edge (0.1V low threshold, 1V high threshold)
    if (trigger.process(inputs[TRIG_INPUT].getVoltage(), 0.1f, 1.f)) {
        // Trigger received — do something
        pulse.trigger(1e-3f);  // 1ms pulse
    }

    // Output trigger pulse
    float pulseOut = pulse.process(args.sampleTime) ? 10.f : 0.f;
    outputs[TRIG_OUTPUT].setVoltage(pulseOut);
}
```

## VCA (Voltage Controlled Amplifier)

```cpp
void process(const ProcessArgs& args) {
    float in = inputs[AUDIO_INPUT].getVoltage();
    float cv = inputs[CV_INPUT].getVoltage();
    float gain = params[GAIN_PARAM].getValue();

    // CV attenuates the gain (0V = no attenuation, 10V = full)
    float level = gain * cv / 10.f;
    level = clamp(level, 0.f, 1.f);

    float out = in * level;
    outputs[AUDIO_OUTPUT].setVoltage(out);
}
```

## Slew Limiter

```cpp
dsp::SlewLimiter slewLimiter;

void onSampleRateChange() override {
    slewLimiter.setSampleRate(APP->engine->getSampleRate());
}

void process(const ProcessArgs& args) {
    slewLimiter.setRiseFall(params[RISE_PARAM].getValue(), params[FALL_PARAM].getValue());

    float in = inputs[AUDIO_INPUT].getVoltage();
    float out = slewLimiter.process(args.sampleTime, in);
    outputs[AUDIO_OUTPUT].setVoltage(out);
}
```

## Sample and Hold

```cpp
float heldValue = 0.f;
dsp::SchmittTrigger trigger;

void process(const ProcessArgs& args) {
    if (trigger.process(inputs[TRIG_INPUT].getVoltage(), 0.1f, 1.f)) {
        heldValue = inputs[IN_INPUT].getVoltage();
    }
    outputs[OUT_OUTPUT].setVoltage(heldValue);
}
```

## Clock Divider

```cpp
int counter = 0;
int division = 1;
dsp::SchmittTrigger trigger;
dsp::PulseGenerator pulse;

void process(const ProcessArgs& args) {
    division = std::max(1, (int)params[DIV_PARAM].getValue());

    if (trigger.process(inputs[CLOCK_INPUT].getVoltage(), 0.1f, 1.f)) {
        counter++;
        if (counter >= division) {
            counter = 0;
            pulse.trigger(1e-3f);
        }
    }

    outputs[OUT_OUTPUT].setVoltage(pulse.process(args.sampleTime) ? 10.f : 0.f);
}
```

## LFO

```cpp
float phase = 0.f;

void process(const ProcessArgs& args) {
    float freq = params[FREQ_PARAM].getValue();  // 0 to 10 Hz range
    freq += inputs[FREQ_INPUT].getVoltage() * 0.5f;
    freq = clamp(freq, 0.01f, 20.f);

    phase += freq * args.sampleTime;
    if (phase >= 1.f) phase -= 1.f;

    // Sine LFO output (bipolar, +/-5V)
    float sine = std::sin(2.f * M_PI * phase);
    outputs[SINE_OUTPUT].setVoltage(5.f * sine);

    // Unipolar output (0 to 10V)
    float unipolar = (sine + 1.f) * 0.5f;
    outputs[UNI_OUTPUT].setVoltage(unipolar * 10.f);
}
```

## Mixer

```cpp
void process(const ProcessArgs& args) {
    float mix = 0.f;
    int channels = 1;

    for (int i = 0; i < NUM_INPUTS; i++) {
        float level = params[LEVEL_PARAM + i].getValue();
        float in = inputs[AUDIO_INPUT + i].getVoltage();
        mix += in * level;
    }

    outputs[MIX_OUTPUT].setVoltage(clamp(mix, -10.f, 10.f));
}
```

## Common Utility Patterns

### Voltage to Frequency (V/Oct)
```cpp
float freq = dsp::FREQ_C4 * std::pow(2.f, voltage);  // voltage in V/oct
```

### Fast V/Oct approximation
```cpp
float freq = dsp::FREQ_C4 * dsp::exp2_taylor5(voltage);
```

### Rescale CV
```cpp
float mapped = rescale(cv, -5.f, 5.f, 0.f, 1.f);  // bipolar CV to 0-1
```

### Bipolar CV attenuation
```cpp
float attenuated = dsp::quadraticBipolar(cv) * amount;
```

### Parameter smoothing
```cpp
float current = lastValue + (target - lastValue) * (1.f - std::exp(-args.sampleTime / smoothTime));
lastValue = current;
```

### Exponential smoothing (from Rack DSP)
```cpp
dsp::ExponentialFilter smooth;
void onSampleRateChange() override { smooth.setLambda(10.f); }
// In process:
float value = smooth.process(args.sampleTime, target);
```

### NaN/Inf safety
```cpp
float safe = std::isfinite(value) ? value : 0.f;
```

### Soft clip / tanh saturation
```cpp
float saturated = std::tanh(value);
```
