# Module Template

Complete starter template for a VCV Rack module with all common features. Copy and adapt.

## Minimal Module (Header + Source)

### MyModule.hpp

```cpp
#pragma once
#include <rack.hpp>
using namespace rack;

struct MyModule : Module {
    // Component IDs — add your params, inputs, outputs, lights here
    enum ParamId {
        PARAM_PARAM,
        NUM_PARAMS
    };
    enum InputId {
        CV_INPUT,
        AUDIO_INPUT,
        NUM_INPUTS
    };
    enum OutputId {
        AUDIO_OUTPUT,
        NUM_OUTPUTS
    };
    enum LightId {
        NUM_LIGHTS
    };

    // State variables
    float phase = 0.f;

    MyModule() {
        config(NUM_PARAMS, NUM_INPUTS, NUM_OUTPUTS, NUM_LIGHTS);

        // Parameters
        configParam(PARAM_PARAM, 0.f, 1.f, 0.5f, "Parameter", "%", 0.f, 100.f);

        // Inputs
        configInput(CV_INPUT, "CV modulation");
        configInput(AUDIO_INPUT, "Audio");

        // Outputs
        configOutput(AUDIO_OUTPUT, "Audio");
    }

    void process(const ProcessArgs& args) override;

    // Optional overrides:
    // void onReset() override;
    // void onRandomize() override;
    // void onSampleRateChange() override;
    // void onAdd() override;
    // json_t* dataToJson() override;
    // void dataFromJson(json_t* root) override;
};

struct MyModuleWidget : ModuleWidget {
    MyModuleWidget(MyModule* module) {
        setModule(module);
        setPanel(createPanel(asset::plugin(pluginInstance, "res/MyModule.svg")));

        // Screws
        addChild(createWidget<ScrewSilver>(Vec(0, 0)));
        addChild(createWidget<ScrewSilver>(Vec(box.size.x - RACK_GRID_WIDTH, 0)));
        addChild(createWidget<ScrewSilver>(Vec(0, RACK_HEIGHT - RACK_GRID_WIDTH)));
        addChild(createWidget<ScrewSilver>(Vec(box.size.x - RACK_GRID_WIDTH, RACK_HEIGHT - RACK_GRID_WIDTH)));

        float cx = box.size.x / 2.f;

        // Params
        addParam(createParamCentered<RoundBlackKnob>(Vec(cx, 80.f), module, MyModule::PARAM_PARAM));

        // Inputs
        addInput(createInputCentered<PJ301MPort>(Vec(cx, 140.f), module, MyModule::CV_INPUT));
        addInput(createInputCentered<PJ301MPort>(Vec(cx, 250.f), module, MyModule::AUDIO_INPUT));

        // Outputs
        addOutput(createOutputCentered<PJ301MPort>(Vec(cx, 310.f), module, MyModule::AUDIO_OUTPUT));
    }

    // Optional: right-click context menu
    // void appendContextMenu(Menu* menu) override;
};
```

### MyModule.cpp

```cpp
#include "MyModule.hpp"

Model* modelMyModule = createModel<MyModule, MyModuleWidget>("MyModule");

void MyModule::process(const ProcessArgs& args) {
    float dt = args.sampleTime;

    // Read parameter + CV
    float param = params[PARAM_PARAM].getValue();
    float cv = inputs[CV_INPUT].getVoltage();
    float value = param + cv / 10.f;
    value = clamp(value, 0.f, 1.f);

    // Read audio input
    float in = inputs[AUDIO_INPUT].getVoltage() / 5.f;

    // Process
    float out = in * value;

    // Write output
    out = std::isfinite(out) ? out * 5.f : 0.f;
    outputs[AUDIO_OUTPUT].setVoltage(clamp(out, -5.f, 5.f));
}
```

## Full-Featured Module Template

### With serialization, sample rate handling, and reset

```cpp
struct FullModule : Module {
    enum ParamId {
        FREQ_PARAM,
        RES_PARAM,
        MODE_PARAM,
        NUM_PARAMS
    };
    enum InputId {
        FREQ_CV_INPUT,
        AUDIO_INPUT,
        TRIG_INPUT,
        NUM_INPUTS
    };
    enum OutputId {
        AUDIO_OUTPUT,
        ENV_OUTPUT,
        NUM_OUTPUTS
    };
    enum LightId {
        ACTIVE_LIGHT,
        NUM_LIGHTS
    };

    // DSP state
    float phase = 0.f;
    dsp::SchmittTrigger trigTrigger;
    dsp::PulseGenerator trigPulse;
    std::string filePath;
    int mode = 0;

    FullModule() {
        config(NUM_PARAMS, NUM_INPUTS, NUM_OUTPUTS, NUM_LIGHTS);

        configParam(FREQ_PARAM, -54.f, 54.f, 0.f, "Frequency", " Hz", dsp::FREQ_C4, dsp::FREQ_C4);
        configParam(RES_PARAM, 0.f, 1.f, 0.5f, "Resonance", "%", 0.f, 100.f);
        configSwitch(MODE_PARAM, 0.f, 2.f, 0.f, "Mode", {"LP", "BP", "HP"});

        configInput(FREQ_CV_INPUT, "Frequency CV");
        configInput(AUDIO_INPUT, "Audio");
        configInput(TRIG_INPUT, "Trigger");

        configOutput(AUDIO_OUTPUT, "Audio");
        configOutput(ENV_OUTPUT, "Envelope");
    }

    void onReset() override {
        phase = 0.f;
        filePath = "";
        mode = 0;
    }

    void onSampleRateChange() override {
        // Recalculate DSP coefficients if needed
    }

    json_t* dataToJson() override {
        json_t* root = json_object();
        json_object_set_new(root, "filePath", json_string(filePath.c_str()));
        json_object_set_new(root, "mode", json_integer(mode));
        return root;
    }

    void dataFromJson(json_t* root) override {
        json_t* fp = json_object_get(root, "filePath");
        if (fp) filePath = json_string_value(fp);
        json_t* m = json_object_get(root, "mode");
        if (m) mode = json_integer_value(m);
    }

    void process(const ProcessArgs& args) override;
};
```

## Parameter Configuration Cheatsheet

```cpp
// Basic knob: min, max, default, display name
configParam(ID, 0.f, 1.f, 0.5f, "Label");

// With unit: name, unit, displayBase, displayMultiplier
configParam(ID, 20.f, 20000.f, 440.f, "Frequency", " Hz", 10.f, 1.f);

// V/oct pitch knob (standard pattern)
configParam(PITCH_PARAM, -54.f, 54.f, 0.f, "Pitch", " Hz", dsp::FREQ_C4, dsp::FREQ_C4);

// Snap/stepped knob
auto* p = configParam(ID, 0.f, 7.f, 0.f, "Waveform");
p->snapEnabled = true;

// Button (0 or 1)
configButton(ID, "Trigger");

// Switch (multiple positions)
configSwitch(ID, 0.f, 2.f, 0.f, "Mode", {"LP", "BP", "HP"});

// Bypass routing (effect module)
configBypass(AUDIO_INPUT, AUDIO_OUTPUT);

// Input/output description
configInput(ID, "Frequency CV");
configOutput(ID, "Audio");

// Input with description of what it does
configInput(GATE_INPUT, "Gate").description = "Triggers envelope";
```

## Widget Layout Cheatsheet

```cpp
// Centered components (preferred)
float cx = box.size.x / 2.f;
addParam(createParamCentered<RoundBlackKnob>(Vec(cx, y), module, Id));
addInput(createInputCentered<PJ301MPort>(Vec(cx, y), module, Id));
addOutput(createOutputCentered<PJ301MPort>(Vec(cx, y), module, Id));
addLight(createLightCentered<MediumLight<GreenLight>>(Vec(cx, y), module, Id));

// Multiple columns
float col1 = box.size.x * 0.25f;
float col2 = box.size.x * 0.75f;
addParam(createParamCentered<RoundSmallBlackKnob>(Vec(col1, y), module, Id1));
addParam(createParamCentered<RoundSmallBlackKnob>(Vec(col2, y), module, Id2));

// Large knob for primary control
addParam(createParamCentered<RoundLargeBlackKnob>(Vec(cx, 60.f), module, MAIN_PARAM));

// Small knob for CV amount
addParam(createParamCentered<Trimpot>(Vec(cx - 20.f, y), module, CV_AMOUNT_PARAM));

// Toggle switch
addParam(createParamCentered<CKSS>(Vec(cx, y), module, SWITCH_PARAM));

// 3-position switch
addParam(createParamCentered<CKSSThree>(Vec(cx, y), module, MODE_PARAM));

// Button with light
addParam(createParamCentered<LEDButton>(Vec(cx, y), module, BUTTON_PARAM));
addChild(createLightCentered<MediumLight<GreenLight>>(Vec(cx, y), module, BUTTON_LIGHT));

// Dark theme support (Rack 2.4+)
setPanel(createPanel(
    asset::plugin(pluginInstance, "res/MyModule.svg"),
    asset::plugin(pluginInstance, "res/MyModule-dark.svg")
));
```

## Registering in plugin.hpp/plugin.cpp

After creating a module, add it to the plugin:

**plugin.hpp** — add declaration:
```cpp
extern Model* modelMyModule;
```

**plugin.cpp** — add to init():
```cpp
void init(Plugin* p) {
    pluginInstance = p;
    p->addModel(modelMyModule);  // Add this line
}
```

**plugin.json** — add to modules array:
```json
{
  "slug": "MyModule",
  "name": "My Module",
  "description": "What it does",
  "tags": ["Oscillator"]
}
```
