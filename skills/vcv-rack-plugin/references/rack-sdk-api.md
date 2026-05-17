# Rack SDK API Quick Reference

Accessed via `#include <rack.hpp>`, namespace `rack::`.

## engine::Module (your module's base class)

```cpp
struct MyModule : Module {
    // Constructor: declare all params, inputs, outputs, lights
    MyModule() {
        config(numParams, numInputs, numOutputs, numLights);
        configParam(id, minValue, maxValue, defaultValue, "label", unit, displayBase, displayMultiplier);
        configSwitch(id, minValue, maxValue, defaultValue, "label", {"option1", "option2"});
        configButton(id, "label");
        configInput(id, "label");
        configOutput(id, "label");
        configBypass(inputId, outputId);  // auto-bypass for effects
    }

    // Core DSP — called every sample
    void process(const ProcessArgs& args) override;

    // Accessors
    params[id].getValue()                    // read parameter
    inputs[id].getVoltage()                  // read mono input
    inputs[id].getVoltage(channel)           // read poly channel
    inputs[id].getPolyVoltage(channel)       // auto-mono-to-poly
    inputs[id].getChannels()                 // polyphony count (0 = unpatched)
    inputs[id].isConnected()                 // check if cable attached
    inputs[id].getVoltageSum()               // sum all channels
    outputs[id].setVoltage(voltage)          // write mono output
    outputs[id].setVoltage(voltage, channel) // write poly channel
    outputs[id].setChannels(n)               // set output polyphony
    lights[id].setBrightness(0..1)           // set light

    // Optional overrides
    void onReset() override;                          // module reset
    void onRandomize() override;                      // randomize values
    void onSampleRateChange() override;               // sample rate changed
    void onAdd() override;                            // module added to rack
    void onRemove() override;                         // module removed
    void onBypass(bool bypassed) override;            // bypass toggled
    void onExpanderChange(const ExpanderChangeEvent& e) override;  // expander changed
    json_t* dataToJson() override;                    // serialize custom state
    void dataFromJson(json_t* root) override;         // deserialize custom state
    void processBypass(const ProcessArgs& args) override;  // custom bypass behavior
};
```

## ProcessArgs

```cpp
struct ProcessArgs {
    float sampleTime;    // 1.0 / sampleRate (e.g., 1/44100 ≈ 0.0000227)
    float sampleRate;    // Current sample rate (e.g., 44100.0)
};
```

## dsp Namespace (built-in DSP utilities)

```cpp
// Constants
dsp::FREQ_C4      // 261.6256 Hz (middle C)
dsp::FREQ_A4      // 440.0 Hz

// Scaling functions
dsp::quadraticBipolar(x)     // bipolar to unipolar mapping
dsp::cubic(x)                // smooth interpolation
dsp::exponentialBipolar(x)   // exponential mapping

// Fast approximations (use instead of std:: versions in process())
dsp::exp2_taylor5(x)         // fast 2^x approximation
dsp::approxSin(x)            // fast sine
dsp::approxCos(x)            // fast cosine

// Digital utilities
dsp::SchmittTrigger          // edge detection for triggers/gates
  .process(voltage, lowThresh, highThresh) → bool
dsp::PulseGenerator          // generate timed pulses
  .trigger(duration)         // start pulse (seconds)
  .process(sampleTime) → bool  // returns true while active
dsp::Timer                   // timing utility
  .process(sampleTime)       // advance timer
  .getTime() → float        // elapsed time
  .reset()                   // reset to 0

// Filters
dsp::RCFilter               // simple one-pole lowpass
  .setCutoff(cutoffHz, sampleRate)
  .process(input) → output
dsp::ExponentialFilter      // exponential smoothing
  .setLambda(lambda)         // smoothing factor
  .process(sampleTime, target) → filtered
dsp::SlewLimiter            // slew rate limiting
  .setRiseFall(rise, fall)
  .process(sampleTime, input) → output
dsp::BiquadFilter           // biquad (LP/HP/BP/notch/peak/shelf)
  .setParameters(type, freq, Q)
  .process(input) → output
  // Types: LOWPASS, HIPASS, BANDPASS, NOTCH, PEAK, LOWSHELF, HIGHSHELF
dsp::IIRFilter<N>           // generic N-th order IIR
dsp::PeakFilter             // peak detection

// ODE Solvers (circuit modeling)
dsp::eulerStep(f, t, x, dt)  // forward Euler
dsp::rungeKutta4Step(f, t, x, dt)  // RK4

// FFT
dsp::fft(buffer, size)       // in-place FFT
dsp::ifft(buffer, size)      // in-place IFFT

// Ring buffer (lock-free)
dsp::RingBuffer<T, SIZE>     // single-producer, single-consumer
  .push(value)
  .shift() → value
  .size() → int
  .full() / .empty()
```

## app Namespace (UI components)

```cpp
// ModuleWidget (your widget's base class)
struct MyWidget : ModuleWidget {
    MyWidget(MyModule* module) {
        setModule(module);
        setPanel(createPanel(svgPath));           // or createPanel(light, dark)
        addParam(createParamCentered<T>(pos, module, paramId));
        addInput(createInputCentered<T>(pos, module, inputId));
        addOutput(createOutputCentered<T>(pos, module, outputId));
        addLight(createLightCentered<T>(pos, module, lightId));
        addChild(createWidget<T>(pos));
    }
    void appendContextMenu(Menu* menu) override;
};

// Pre-built knob types
RoundBlackKnob               // standard
RoundLargeBlackKnob          // large
RoundSmallBlackKnob          // small
RoundBlackSnapKnob           // stepped/snapping
Davies1900hLargeBlackKnob    // vintage style
Davies1900hWhiteKnob         // vintage white
Trimpot                      // tiny trim pot
SnapKnob                     // generic snap knob

// Port types
PJ301MPort                   // standard jack
ThemedPJ301MPort             // theme-aware jack

// Switch types
CKSS                         // 2-position toggle
CKSSThree                    // 3-position toggle

// Button types
LEDButton                    // illuminated button

// Screw types
ScrewSilver                  // silver screw
ScrewBlack                   // black screw
ThemedScrew                  // theme-aware screw

// Light types (used with createLightCentered)
MediumLight<RedLight>
MediumLight<GreenLight>
MediumLight<BlueLight>
MediumLight<YellowLight>
MediumLight<WhiteLight>

// Size constants
RACK_GRID_WIDTH              // 1 HP in px
RACK_HEIGHT                  // panel height in px (≈380 at default zoom)
```

## asset Namespace (file paths)

```cpp
asset::plugin(pluginInstance, "res/file.svg")  // plugin resource
asset::system("res/fonts/..." )                // system resource
asset::user("patches/...")                     // user data directory
```

## simd Namespace (4-wide SIMD)

```cpp
simd::float_4                // 4-wide float vector
simd::int32_4                // 4-wide int vector
simd::sin(x)                 // vector sine
simd::cos(x)                 // vector cosine
simd::pow(x, y)              // vector power
simd::exp2(x)                // vector 2^x
simd::sqrt(x)                // vector sqrt
simd::clamp(x, min, max)     // vector clamp
simd::ifelse(cond, a, b)     // vector conditional
simd::movemask(x)            // extract sign bits
```

## widget::Widget (custom drawing)

```cpp
// For custom displays, subclass OpaqueWidget:
struct MyWidget : OpaqueWidget {
    void draw(const DrawArgs& args) override;
    void drawLayer(const DrawArgs& args, int layer) override;  // layer 1 = illuminated
    void onButton(const event::Button& e) override;
    void onDragStart(const event::DragStart& e) override;
    void onDragMove(const event::DragMove& e) override;
    void onDragEnd(const event::DragEnd& e) override;
    void onHover(const event::Hover& e) override;
    void step() override;  // called every frame
};
```

## JSON Serialization (Jansson)

```cpp
// Creating JSON
json_t* root = json_object();
json_object_set_new(root, "key", json_string("value"));
json_object_set_new(root, "int", json_integer(42));
json_object_set_new(root, "float", json_real(3.14));
json_object_set_new(root, "bool", json_boolean(true));
json_t* arr = json_array();
json_array_append_new(arr, json_integer(0));
json_object_set_new(root, "array", arr);
// Don't forget to decref when done
json_decref(root);

// Reading JSON
json_t* val = json_object_get(root, "key");
const char* str = json_string_value(val);
int i = json_integer_value(val);
double d = json_real_value(val);
bool b = json_boolean_value(val);
size_t len = json_array_size(arr);
json_t* item = json_array_get(arr, index);
```
