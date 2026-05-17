# Panel Design Reference

## SVG Panel Specifications

### Dimensions
- **Units**: Millimeters (mm), NOT pixels
- **Height**: 128.5 mm (standard Eurorack)
- **Width**: Multiples of 5.08 mm (1 HP)
- Common widths: 3HP (15.24mm), 6HP (30.48mm), 8HP (40.64mm), 10HP (50.8mm), 12HP (60.96mm)

### Inkscape Setup
1. File > Document Properties > Custom Size
2. Set width and height in mm
3. View > Page Grid (for alignment)
4. Set grid spacing to 5.08mm for HP alignment

### SVG Rendering Constraints
- **All text must be converted to paths**: Select all text, Path > Object to Path
- **Only simple two-color linear gradients** work reliably
- **CSS is mostly unsupported** — use inline `fill-*` and `stroke-*` style attributes
- **No external fonts** — convert to paths to avoid font licensing issues

## Component Placeholder System

The `components` layer lets `$RACK_DIR/helper.py createmodule` auto-generate C++ from SVG positions.

### Setup
1. Create a layer named `components` in Inkscape (Layer > Add Layer)
2. Place colored shapes as placeholders
3. Name each shape via Object Properties (Shift+Ctrl+O) → "Label" field
4. **Hide** the components layer before saving

### Color Codes

| Component | Color | Shape | Positioning |
|-----------|-------|-------|-------------|
| Param (knob/switch/button) | `#ff0000` (red) | Circle | Center point |
| Input | `#00ff00` (green) | Circle | Center point |
| Output | `#0000ff` (blue) | Circle | Center point |
| Light | `#ff00ff` (magenta) | Circle | Center point |
| Custom widget | `#ffff00` (yellow) | Rectangle | Top-left corner |

- **Circle size doesn't matter** — only center position is used → generates `create*Centered<>()`
- **Rectangle** generates `create*<>()` (used when component size matters, e.g., LED displays)

### Label Naming Convention

Name shapes in Object Properties "Label" field using these patterns:
- `FREQ` → generates `FREQ_PARAM` in ParamId enum
- `CV` → generates `CV_INPUT` in InputId enum
- `OUT` → generates `OUT_OUTPUT` in OutputId enum
- `ACTIVE` → generates `ACTIVE_LIGHT` in LightId enum

## Auto-Generation

After designing the panel:
```bash
$RACK_DIR/helper.py createmodule MyModule res/MyModule.svg src/MyModule.cpp
```

This creates:
- Param/Input/Output/Light enums from the colored shapes
- Widget constructor with `createParamCentered<>()` etc. calls
- Registers the module in plugin.json

## Dark Theme Panels (Rack 2.4+)

### Dual SVG Approach
Provide both light and dark panel SVGs:
- `res/MyModule.svg` — light theme
- `res/MyModule-dark.svg` — dark theme

Load both:
```cpp
setPanel(createPanel(
    asset::plugin(pluginInstance, "res/MyModule.svg"),
    asset::plugin(pluginInstance, "res/MyModule-dark.svg")
));
```

### Themed Components
```cpp
// Instead of ScrewSilver / PJ301MPort, use themed variants:
addChild(createWidget<ThemedScrew>(Vec(0, 0)));
addInput(createInputCentered<ThemedPJ301MPort>(Vec(cx, y), module, Id));
addOutput(createOutputCentered<ThemedPJ301MPort>(Vec(cx, y), module, Id));
```

### Custom Themed Widgets
```cpp
// Check current theme
bool dark = settings::preferDarkPanel;
```

## Custom Display Widgets

For waveform displays, oscilloscopes, text readouts:

```cpp
struct MyDisplay : OpaqueWidget {
    MyModule* module = nullptr;

    void draw(const DrawArgs& args) override {
        // Background
        nvgBeginPath(args.vg);
        nvgRoundedRect(args.vg, 0, 0, box.size.x, box.size.y, 4);
        nvgFillColor(args.vg, nvgRGB(0, 0, 0));
        nvgFill(args.vg);

        if (!module) return;

        // Draw waveform
        nvgBeginPath(args.vg);
        nvgStrokeColor(args.vg, nvgRGB(0, 255, 0));
        nvgStrokeWidth(args.vg, 1.5f);
        for (int i = 0; i < points; i++) {
            float x = (float)i / points * box.size.x;
            float y = box.size.y / 2.f - module->getDisplayValue(i) * box.size.y / 2.f;
            if (i == 0) nvgMoveTo(args.vg, x, y);
            else nvgLineTo(args.vg, x, y);
        }
        nvgStroke(args.vg);
    }
};

// Add to widget:
auto* display = new MyDisplay;
display->box.pos = Vec(10, 100);
display->box.size = Vec(box.size.x - 20, 80);
display->module = module;
addChild(display);
```

### NanoVG Drawing Reference

```cpp
// Paths
nvgBeginPath(vg);
nvgMoveTo(vg, x, y);
nvgLineTo(vg, x, y);
nvgRoundedRect(vg, x, y, w, h, radius);
nvgCircle(vg, cx, cy, radius);
nvgArc(vg, cx, cy, radius, startAngle, endAngle, NVGwinding);

// Fill
nvgFillColor(vg, nvgRGB(r, g, b));
nvgFill(vg);
nvgFillColor(vg, nvgRGBA(r, g, b, a));

// Stroke
nvgStrokeColor(vg, nvgRGB(r, g, b));
nvgStrokeWidth(vg, width);
nvgStroke(vg);

// Gradient
NVGpaint grad = nvgLinearGradient(vg, x0, y0, x1, y1, col0, col1);
nvgFillPaint(vg, grad);

// Text
std::shared_ptr<Font> font = APP->window->loadFont(asset::plugin(pluginInstance, "res/font.ttf"));
if (font) {
    nvgFontFaceId(vg, font->handle);
    nvgFontSize(vg, 12);
    nvgTextAlign(vg, NVG_ALIGN_CENTER | NVG_ALIGN_MIDDLE);
    nvgFillColor(vg, nvgRGB(255, 255, 255));
    nvgText(vg, x, y, "text", NULL);
}
```

### Self-Illuminating Widgets (lights that stay bright)

```cpp
void drawLayer(const DrawArgs& args, int layer) override {
    if (layer == 1) {
        // Draw illuminated content here
        nvgBeginPath(args.vg);
        nvgFillColor(args.vg, nvgRGB(255, 0, 0));
        nvgCircle(args.vg, cx, cy, radius);
        nvgFill(args.vg);
    }
    OpaqueWidget::drawLayer(args, layer);
}
```

## Framebuffer Caching

For complex widgets that don't change every frame:

```cpp
struct CachedDisplay : FramebufferWidget {
    MyModule* module = nullptr;

    void draw(const DrawArgs& args) override {
        // Expensive drawing here — cached until setDirty()
    }

    void step() override {
        if (module && module->displayDirty) {
            setDirty();
            module->displayDirty = false;
        }
        FramebufferWidget::step();
    }
};
```
