# Editor and UI Patterns

Patterns for building plugin GUIs with JUCE's component system.

## Editor Basics

```cpp
class MyEditor : public juce::AudioProcessorEditor
{
public:
    MyEditor (MyProcessor& p)
        : AudioProcessorEditor (&p),
          processor (p),
          gainAttachment (p.apvts, "gain", gainSlider),
          bypassAttachment (p.apvts, "bypass", bypassButton)
    {
        // Add child components
        addAndMakeVisible (gainSlider);
        addAndMakeVisible (bypassButton);
        addAndMakeVisible (titleLabel);

        // Configure controls
        gainSlider.setSliderStyle (juce::Slider::RotaryHorizontalVerticalDrag);
        gainSlider.setTextBoxStyle (juce::Slider::TextBoxBelow, false, 80, 20);
        gainSlider.setColour (juce::Slider::rotarySliderFillColourId, juce::Colours::orange);

        // Window sizing
        setResizeLimits (300, 200, 1200, 800);
        setResizable (true, true);
        setSize (600, 400);
    }

    void paint (juce::Graphics& g) override
    {
        g.fillAll (juce::Colours::darkgrey);
        g.setColour (juce::Colours::white);
        g.setFont (20.0f);
        g.drawText ("My Plugin", getLocalBounds().removeFromTop (40),
                     juce::Justification::centred);
    }

    void resized() override
    {
        auto bounds = getLocalBounds().reduced (20);

        // Layout controls
        titleLabel.setBounds (bounds.removeFromTop (40));
        gainSlider.setBounds (bounds.removeFromTop (80).withSizeKeepingCentre (80, 80));
        bypassButton.setBounds (bounds.removeFromTop (30).withSizeKeepingCentre (100, 30));
    }

private:
    MyProcessor& processor;

    juce::Label titleLabel;
    juce::Slider gainSlider;
    juce::ToggleButton bypassButton;
    juce::AudioProcessorValueTreeState::SliderAttachment gainAttachment;
    juce::AudioProcessorValueTreeState::ButtonAttachment bypassAttachment;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (MyEditor)
};
```

## Layout Strategies

### FlexBox (Responsive)

```cpp
void resized() override
{
    juce::FlexBox flexBox;
    flexBox.flexDirection = juce::FlexBox::Direction::column;
    flexBox.flexWrap = juce::FlexBox::Wrap::wrap;
    flexBox.justifyContent = juce::FlexBox::JustifyContent::center;
    flexBox.alignItems = juce::FlexBox::AlignItems::center;

    for (auto* slider : { &gainSlider, &mixSlider, &freqSlider })
        flexBox.items.add (juce::FlexItem (*slider)
            .withWidth (80.0f).withHeight (100.0f)
            .withMargin (juce::FlexItem::Margin (5.0f)));

    flexBox.performLayout (getLocalBounds().toFloat());
}
```

### Grid (Table-like)

```cpp
void resized() override
{
    using Track = juce::Grid::TrackInfo;

    juce::Grid grid;
    grid.templateColumns = { Track (1_fr), Track (1_fr), Track (1_fr) };
    grid.templateRows = { Track (1_fr), Track (1_fr) };
    grid.items = {
        juce::GridItem (gainSlider),    juce::GridItem (mixSlider),    juce::GridItem (freqSlider),
        juce::GridItem (resoSlider),    juce::GridItem (driveSlider),  juce::GridItem (outputSlider)
    };
    grid.performLayout (getLocalBounds());
}
```

### Manual Bounds Slicing

```cpp
void resized() override
{
    auto bounds = getLocalBounds().reduced (10);
    auto header = bounds.removeFromTop (40);
    titleLabel.setBounds (header);

    auto controls = bounds.removeFromTop (120);
    auto colWidth = controls.getWidth() / 3;
    gainSlider.setBounds (controls.removeFromLeft (colWidth).reduced (5));
    freqSlider.setBounds (controls.removeFromLeft (colWidth).reduced (5));
    mixSlider.setBounds (controls.reduced (5));

    auto footer = bounds.removeFromBottom (30);
    bypassButton.setBounds (footer.withSizeKeepingCentre (100, 30));
}
```

## Slider Styles

```cpp
// Rotary knob
slider.setSliderStyle (juce::Slider::RotaryHorizontalVerticalDrag);
slider.setRotaryParameters (juce::MathConstants<float>::pi * 0.25f,
                             juce::MathConstants<float>::pi * 1.75f,
                             true);  // stopAtEnd

// Vertical fader
slider.setSliderStyle (juce::Slider::LinearVertical);

// Horizontal fader
slider.setSliderStyle (juce::Slider::LinearHorizontal);

// Bar (thin horizontal)
slider.setSliderStyle (juce::Slider::LinearBar);
```

## Custom Component (Meters, Displays)

```cpp
class LevelMeter : public juce::Component,
                   private juce::Timer
{
public:
    LevelMeter (std::atomic<float>& levelSource)
        : level (levelSource)
    {
        startTimerHz (30);
    }

    void paint (juce::Graphics& g) override
    {
        auto bounds = getLocalBounds().toFloat();
        auto levelValue = juce::jlimit (0.0f, 1.0f, level.load());

        // Background
        g.setColour (juce::Colours::black);
        g.fillRoundedRectangle (bounds, 2.0f);

        // Level bar
        auto fillHeight = bounds.getHeight() * levelValue;
        auto fillRect = bounds.removeFromBottom (fillHeight);
        g.setColour (levelValue > 0.8f ? juce::Colours::red : juce::Colours::green);
        g.fillRoundedRectangle (fillRect, 2.0f);
    }

    void timerCallback() override { repaint(); }

private:
    std::atomic<float>& level;
};
```

## LookAndFeel Customization

```cpp
class CustomLookAndFeel : public juce::LookAndFeel_V4
{
public:
    CustomLookAndFeel()
    {
        setColour (juce::Slider::rotarySliderFillColourId, juce::Colour (0xff4488ff));
        setColour (juce::Slider::rotarySliderOutlineColourId, juce::Colour (0xff333333));
        setColour (juce::Slider::thumbColourId, juce::Colour (0xff88ccff));
    }

    void drawRotarySlider (juce::Graphics& g, int x, int y, int width, int height,
                           float sliderPos, float rotaryStartAngle, float rotaryEndAngle,
                           juce::Slider& slider) override
    {
        auto radius = (float) juce::jmin (width / 2, height / 2) * 0.8f;
        auto centreX = (float) x + (float) width * 0.5f;
        auto centreY = (float) y + (float) height * 0.5f;

        // Track arc
        juce::Path track;
        track.addCentredArc (centreX, centreY, radius, radius, 0.0f,
                              rotaryStartAngle, rotaryEndAngle, true);
        g.setColour (findColour (juce::Slider::rotarySliderOutlineColourId));
        g.strokePath (track, juce::PathStrokeType (3.0f));

        // Fill arc
        auto fillEnd = rotaryStartAngle + sliderPos * (rotaryEndAngle - rotaryStartAngle);
        juce::Path fill;
        fill.addCentredArc (centreX, centreY, radius, radius, 0.0f,
                             rotaryStartAngle, fillEnd, true);
        g.setColour (findColour (juce::Slider::rotarySliderFillColourId));
        g.strokePath (fill, juce::PathStrokeType (3.0f));

        // Thumb dot
        auto thumbAngle = rotaryStartAngle + sliderPos * (rotaryEndAngle - rotaryStartAngle);
        auto thumbX = centreX + std::sin (thumbAngle) * radius * 0.7f;
        auto thumbY = centreY - std::cos (thumbAngle) * radius * 0.7f;
        g.setColour (findColour (juce::Slider::thumbColourId));
        g.fillEllipse (thumbX - 4, thumbY - 4, 8, 8);
    }
};
```

Important: declare the LookAndFeel as a member of the editor (before any components that use it), not as a local variable. Destruction is reverse of declaration order.

## Binary Data for Assets

Embed images, fonts, and other files:

```cmake
# In CMakeLists.txt:
juce_add_binary_data (MyPluginData
    SOURCES
        resources/background.png
        resources/knob.png
        resources/font.ttf)
```

```cpp
// In code:
auto backgroundImage = juce::ImageCache::getFromMemory (
    BinaryData::background_png, BinaryData::background_pngSize);

juce::Font customFont (juce::FontOptions {
    juce::Typeface::createSystemTypefaceFor (
        BinaryData::font_ttf, BinaryData::font_ttfSize)
});
```

## Paint Best Practices

```cpp
void paint (juce::Graphics& g) override
{
    // Use getLocalBounds() — it's cached and cheap
    auto bounds = getLocalBounds();

    // Background
    g.fillAll (juce::Colours::darkgrey);

    // Rounded rectangle panel
    g.setColour (juce::Colour (0xff2a2a2a));
    g.fillRoundedRectangle (bounds.reduced (5).toFloat(), 8.0f);

    // Border
    g.setColour (juce::Colour (0xff444444));
    g.drawRoundedRectangle (bounds.reduced (5).toFloat(), 8.0f, 1.0f);

    // Gradient
    juce::ColourGradient gradient (
        juce::Colour (0xff1a1a2e), 0.0f, 0.0f,
        juce::Colour (0xff16213e), 0.0f, (float) getHeight(),
        false);
    g.setGradientFill (gradient);
    g.fillAll();
}
```

Avoid allocating `Path`, `Image`, `ColourGradient`, or `Font` objects inside `paint()` — declare them as members and reuse.

## Preset Management UI

```cpp
class PresetPanel : public juce::Component,
                    private juce::ComboBox::Listener
{
public:
    PresetPanel (MyProcessor& p) : processor (p)
    {
        addAndMakeVisible (presetBox);
        presetBox.addListener (this);
        refreshPresetList();

        addAndMakeVisible (saveButton);
        saveButton.onClick = [this] { savePreset(); };
    }

    void comboBoxChanged (juce::ComboBox*) override
    {
        auto index = presetBox.getSelectedId() - 1;
        if (index >= 0 && index < presets.size())
            processor.loadPreset (presets[index]);
    }

private:
    void refreshPresetList()
    {
        presetBox.clear();
        for (int i = 0; i < presets.size(); ++i)
            presetBox.addItem (presets[i].name, i + 1);
        presetBox.setSelectedId (1);
    }

    MyProcessor& processor;
    juce::ComboBox presetBox;
    juce::TextButton saveButton { "Save" };
    std::vector<Preset> presets;
};
```

## Showing Plugin UI from Processor

To communicate processor state to the editor safely (thread crossing):

```cpp
// In processor:
std::atomic<float> levelMeterValue { 0.0f };

// In processBlock:
levelMeterValue.store (maxLevel);

// In editor constructor:
addAndMakeVisible (meter);
meter = std::make_unique<LevelMeter> (processor.levelMeterValue);
```

For more complex state, use `juce::AsyncUpdater` or `juce::MessageManager::callAsync()` to post updates from the audio thread to the message thread.
