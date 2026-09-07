// JUCE 9.0.1 relay lifetime example and headless regression check.
// Build instructions: ../references/webview-ui.md#gesture-cleanup-on-editor-destruction
#include <juce_audio_processors/juce_audio_processors.h>
#include <juce_gui_extra/juce_gui_extra.h>
#include <algorithm>
#include <iostream>
#include <stdexcept>

// This is a JUCE 9.0.1 workaround verified against that implementation, not a
// recommended abstraction to copy unchanged across JUCE versions.
// Declare after the WebSliderParameterAttachment so the guard is destroyed first.
// Normal gestures remain owned by that attachment; this observer only closes a
// gesture abandoned by editor destruction. All access is on the message thread.
class WebGestureGuard final : private juce::WebSliderRelay::Listener
{
public:
    WebGestureGuard (juce::RangedAudioParameter& p, juce::WebSliderRelay& r)
        : parameter (p), relay (r) { relay.addListener (this); }

    ~WebGestureGuard() override
    {
        relay.removeListener (this);
        if (active)
            parameter.endChangeGesture();
    }

private:
    void sliderValueChanged (juce::WebSliderRelay*) override {}
    void initialUpdateRequested (juce::WebSliderRelay*) override {}
    void sliderDragStarted (juce::WebSliderRelay*) override { active = true; }
    void sliderDragEnded (juce::WebSliderRelay*) override { active = false; }

    juce::RangedAudioParameter& parameter;
    juce::WebSliderRelay& relay;
    bool active = false;
    JUCE_DECLARE_NON_COPYABLE (WebGestureGuard)
};

struct GestureCounts final : juce::AudioProcessorParameter::Listener
{
    void parameterValueChanged (int, float) override {}
    void parameterGestureChanged (int, bool starting) override
    {
        if (starting) ++begins;
        else ++ends;
    }
    int begins = 0, ends = 0;
};

static void require (bool condition)
{
    if (!condition) throw std::runtime_error ("Unbalanced or duplicated host gesture");
}

int main()
{
    const juce::ScopedJuceInitialiser_GUI initialise;
    juce::AudioParameterFloat parameter { juce::ParameterID { "gain", 1 },
                                         "Gain", 0.0f, 1.0f, 0.5f };
    GestureCounts counts;
    parameter.addListener (&counts);

    // 0 normal pointerup, 1 cancel/lost-capture equivalent, 2 active teardown,
    // 3 idle teardown. Browser DOM event delivery is a separate backend test.
    for (int scenario = 0; scenario < 4; ++scenario)
    {
        counts.begins = counts.ends = 0;
        juce::WebSliderRelay relay { "gain" };
        const auto options = juce::WebBrowserComponent::Options{}.withOptionsFrom (relay);
        const auto& listeners = options.getEventListeners();
        const auto found = std::find_if (listeners.begin(), listeners.end(), [] (const auto& entry)
        {
            return entry.first == juce::Identifier { "__juce__slidergain" };
        });
        require (found != listeners.end());
        const auto& receive = found->second;
        auto send = [&receive] (const char* type)
        {
            juce::DynamicObject::Ptr event = new juce::DynamicObject;
            event->setProperty ("eventType", type);
            receive (juce::var { event.get() });
        };
        {
            juce::WebSliderParameterAttachment attachment { parameter, relay };
            {
                WebGestureGuard guard { parameter, relay };
                if (scenario != 3) send ("sliderDragStarted");
                if (scenario < 2) send ("sliderDragEnded");
                require (counts.begins == (scenario == 3 ? 0 : 1));
                require (counts.ends == (scenario < 2 ? 1 : 0));
            }
            require (counts.ends == counts.begins);
        }
        require (counts.ends == counts.begins); // attachment adds no second end
    }
    parameter.removeListener (&counts);
    std::cout << "PASS: normal, cancel, active and idle teardown gestures\n";
}
