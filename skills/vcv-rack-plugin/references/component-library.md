# Component Library Reference

VCV Rack includes a built-in component library with SVG graphics for knobs, ports, switches, buttons, screws, and sliders. These live in the Rack SDK's `componentlibrary.hpp` header and are the standard components used across all VCV modules.

## Knobs

| Class Name | Style | Best For |
|-----------|-------|----------|
| `RoundSmallBlackKnob` | Small black knob | Secondary controls, CV amount, fine tuning |
| `RoundBlackKnob` | Medium black knob | Standard parameters |
| `RoundLargeBlackKnob` | Large black knob | Primary controls (frequency, gain) |
| `RoundBigBlackKnob` | Extra-large black knob | Main module control |
| `RoundHugeBlackKnob` | Very large knob | Feature centerpiece |
| `RoundBlackSnapKnob` | Medium knob with snap | Discrete selection (waveform, mode) |
| `Trimpot` | Tiny trim pot | CV attenuverters, hidden settings |
| `Davies1900hSmallBlackKnob` | Small vintage knob | Retro-style modules |
| `Davies1900hBlackKnob` | Medium vintage knob | Vintage-style parameters |
| `Davies1900hWhiteKnob` | Medium vintage white | Contrast control |
| `Davies1900hLargeBlackKnob` | Large vintage black | Primary vintage control |
| `Davies1900hLargeWhiteKnob` | Large vintage white | Primary contrast control |
| `Davies1900hLargeRedKnob` | Large vintage red | Accent/emphasis control |
| `BefacoBigKnob` | Befaco-style large | Befaco hardware clones |
| `BefacoTinyKnobWhite` | Befaco-style tiny | Befaco secondary controls |
| `SynthTechAlco` | SynthTech-style | Specific hardware clones |
| `Rogan1P...` | Rogan small series | Available in Blue/Green/Red/White |
| `Rogan1PS...` | Rogan small snap | Stepped selection |
| `Rogan2P...` | Rogan medium series | Available in Blue/Green/Red/White |
| `Rogan2PS...` | Rogan medium snap | Stepped selection |
| `Rogan3P...` | Rogan large series | Available in Blue/Green/Red/White |
| `Rogan3PS...` | Rogan large snap | Stepped selection |
| `Rogan5PSGray` | Rogan extra-large snap | Large stepped control |
| `Rogan6PSWhite` | Rogan huge snap | Very large stepped control |

## Ports (Jacks)

| Class Name | Style | Best For |
|-----------|-------|----------|
| `PJ301MPort` | Standard 3.5mm jack (silver) | Most inputs/outputs |
| `ThemedPJ301MPort` | Theme-aware 3.5mm jack | Dark/light panel support |
| `PJ3410Port` | PJ3410 style jack | Alternative jack style |
| `ADATPort` | ADAT optical connector | Digital audio I/O |

## Switches

| Class Name | Style | Positions |
|-----------|-------|-----------|
| `CKSS` | Small toggle | 2 positions |
| `CKSSThree` | Small toggle | 3 positions |
| `CKSSThreeHorizontal` | Small toggle (horizontal) | 3 positions |
| `CKD6` | Push-button with LED indicator | On/off |
| `NKK` | Large toggle | 3 positions |
| `BefacoSwitch` | Befaco toggle | 3 positions |

## Buttons

| Class Name | Style | Best For |
|-----------|-------|----------|
| `LEDButton` | Illuminated round button | Triggers, actions |
| `TL1105` | Tactile push button | Momentary actions |
| `PB61303` | E-Switch pushbutton | Momentary/cycle |
| `VCVButton` | VCV-branded button | Standard action |
| `BefacoPush` | Befaco momentary | Befaco-style triggers |

## Sliders

| Class Name | Style | Best For |
|-----------|-------|----------|
| `BefacoSlidePot` | Befaco fader | Mixers, crossfaders |
| `VCVSlider` | VCV fader | Standard sliders |

## Screws

| Class Name | Style | Best For |
|-----------|-------|----------|
| `ScrewSilver` | Silver screw | Light panels |
| `ScrewBlack` | Black screw | Dark panels |
| `ThemedScrew` | Theme-aware screw | Dark/light panel support |

## Lights

| Class Name | Size | Colors Available |
|-----------|------|-----------------|
| `SmallLight<ColorLight>` | Small | Red, Green, Blue, Yellow, White |
| `MediumLight<ColorLight>` | Medium | Red, Green, Blue, Yellow, White |
| `LargeLight<ColorLight>` | Large | Red, Green, Blue, Yellow, White |
| `TinyLight<ColorLight>` | Tiny | Red, Green, Blue, Yellow, White |

Color variants: `RedLight`, `GreenLight`, `BlueLight`, `YellowLight`, `WhiteLight`

For bicolor/tricolor: `RedGreenLight` (2-color), `RedGreenBlueLight` (3-color)

## Connectors (decorative)

| Class Name | Style |
|-----------|-------|
| `MIDI_DIN` | MIDI DIN connector |
| `USB_B` | USB Type-B connector |

## Usage in Widget Constructor

```cpp
// Knob
addParam(createParamCentered<RoundBlackKnob>(Vec(x, y), module, MyModule::PARAM));

// Port
addInput(createInputCentered<PJ301MPort>(Vec(x, y), module, MyModule::INPUT));
addOutput(createOutputCentered<PJ301MPort>(Vec(x, y), module, MyModule::OUTPUT));

// Themed (dark/light support)
addInput(createInputCentered<ThemedPJ301MPort>(Vec(x, y), module, MyModule::INPUT));

// Switch
addParam(createParamCentered<CKSS>(Vec(x, y), module, MyModule::SWITCH_PARAM));
addParam(createParamCentered<CKSSThree>(Vec(x, y), module, MyModule::MODE_PARAM));

// Snap knob (stepped selection)
addParam(createParamCentered<RoundBlackSnapKnob>(Vec(x, y), module, MyModule::SELECT_PARAM));

// Button with light
addParam(createParamCentered<LEDButton>(Vec(x, y), module, MyModule::BUTTON_PARAM));
addChild(createLightCentered<MediumLight<GreenLight>>(Vec(x, y), module, MyModule::BUTTON_LIGHT));

// Screw
addChild(createWidget<ScrewSilver>(Vec(0, 0)));
// Or themed:
addChild(createWidget<ThemedScrew>(Vec(0, 0)));
```
