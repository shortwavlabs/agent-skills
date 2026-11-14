# Host Automation, Editor Synchronization and the Audio Thread

How host automation reaches parameter listeners, why JUCE's stock editor attachments can make the host's audio thread lock and allocate, the editor pattern that avoids it, and how to test for it. Verified on JUCE 9.0.3, macOS (arm64), AU v2 and VST3, in one plug-in (case study at the end). The mechanism is in framework code shared by other JUCE versions and platforms, but those were **not** measured: re-check the source of the JUCE version you ship.

## Contents

- [The Failure Pattern](#the-failure-pattern)
- [Mechanism](#mechanism)
- [Why Tests Miss It](#why-tests-miss-it)
- [The Remedy: Polled Editor Attachments](#the-remedy-polled-editor-attachments)
- [Anti-Patterns](#anti-patterns)
- [Regression Tests](#regression-tests)
- [What Remains in the Wrappers](#what-remains-in-the-wrappers)
- [Custom and WebView Interfaces](#custom-and-webview-interfaces)
- [Case Study and Sources](#case-study-and-sources)

## The Failure Pattern

A plug-in whose editor uses `AudioProcessorValueTreeState::SliderAttachment`, `ComboBoxAttachment` or `ButtonAttachment` (or `juce::ParameterAttachment` and the classes built on it) makes the **host's audio thread** take locks, wake the main run loop and, on macOS, call `malloc`, whenever the host automates a parameter **while the editor is open**.

- **Signature in an allocation trace:** small blocks (64 or 128 bytes on JUCE 9.0.3 macOS) from `juce::MessageQueue::post`, under `AudioProcessorParameter::setValueNotifyingHost`, under `JuceVST3Component::process` or `JuceAU::SetParameter`.
- **Editor closed:** nothing. That asymmetry is the tell.
- **Not format- or parameter-specific:** any automated parameter whose change is notified on the audio thread triggers it, in AU and VST3 alike.

## Mechanism

1. **Wrappers notify on the host's thread.** The VST3 wrapper applies the last automation point of each block with `setValueNotifyingHost()` inside `process()`. The AU wrapper does the same inside `SetParameter`, on whatever thread the host calls `AudioUnitSetParameter` from, which for automation playback is usually the render thread. **`parameterValueChanged` and APVTS `parameterChanged` must be treated as audio-thread callbacks.**
2. **`setValueNotifyingHost()` calls every listener** on that thread, under the parameter's `listenerLock`.
3. **The stock attachment posts.** `ParameterAttachment::parameterValueChanged` calls `MessageManager::isThisTheMessageThread()` (it takes a `std::mutex` in 9.0.3) and, off the message thread, `AsyncUpdater::triggerAsyncUpdate()`.
4. **The post locks, signals and allocates.** `triggerAsyncUpdate` posts to the message queue. On macOS that is a `ReferenceCountedArray` under a `CriticalSection`, followed by `CFRunLoopSourceSignal` / `CFRunLoopWakeUp`. The array gives back its storage when it drains (`removeAndReturn` shrinks it), so a post onto an idle queue grows it with `malloc` / `realloc`.

JUCE documents the hazard on `AsyncUpdater::triggerAsyncUpdate` ("beware of calling it from a real-time (e.g. audio) thread"). Its own `GenericAudioProcessorEditor` already avoids it with an atomic flag and a timer. Only `ParameterAttachment` posts.

**Is the wrapper wrong to notify?** No. `setValueNotifyingHost()` is how listeners (the APVTS, your processor, the wrapper's own host-sync code) learn about the change. The wrappers guard against echoing the change back to the host (a thread-local "in parameter-changed callback" flag). The defect is a listener that does message-thread work.

## Why Tests Miss It

| Trap | Effect |
|---|---|
| Testing with the editor closed | the attachments do not exist; the trace is clean |
| A test host that sets AU parameters from its **message thread** | the listeners run on the message thread and update the controls directly; nothing is posted, the count reads 0. **Deliver AU automation from the audio callback**, as a DAW playing automation does. |
| VST3 with the transport stopped, in a host that also updates the edit controller | JUCE's controller applies the value on the message thread first; `process()` then finds it unchanged and does not notify. Only parameters whose stored value differs from the sent one (snapping ranges, float round-trips) show the defect. JUCE's controller does not apply values while the host is playing, so during playback every automated parameter goes through `process()`. Apply changes in the audio callback, or run a playing transport. |
| Counting only `operator new` / `delete` | JUCE containers grow with `realloc`. On macOS hook `malloc_logger` (the MallocStackLogging hook) or interpose `malloc`; filter by thread. |
| Counting only allocations | locks and the run-loop wake-up happen on every post, also when the array has room. Prove that nothing is posted at all. |
| An idle message thread in a unit test | undelivered messages keep the queue's storage, so later posts do not allocate. Drain the queue (run the run loop briefly) before measuring. |
| Comparing totals between runs | a format's first-use allocations (thread-local storage) can fall inside or outside the measured window by chance. Record stacks and classify them. |

## The Remedy: Polled Editor Attachments

**Editor-side parameter listeners do nothing on a non-message thread except set an atomic flag.** A message-thread timer reads the flag and refreshes the control from the parameter's **current** value. On the message thread, keep the synchronous behaviour.

```cpp
// One parameter, one control. Construct, use and destroy on the message thread.
class ParameterLink final : private juce::AudioProcessorParameter::Listener
{
public:
    ParameterLink (juce::RangedAudioParameter& p, std::function<void (float)> setControlToPlainValue)
        : parameter (p), setControl (std::move (setControlToPlainValue)) { parameter.addListener (this); }
    ~ParameterLink() override { parameter.removeListener (this); }

    void refresh() { setControl (parameter.convertFrom0to1 (parameter.getValue())); }
    bool poll()    { if (! dirty.exchange (false, std::memory_order_acq_rel)) return false; refresh(); return true; }

    // control -> parameter and host: the same calls as juce::ParameterAttachment
    void beginGesture() { parameter.beginChangeGesture(); }
    void endGesture()   { parameter.endChangeGesture(); }
    void setValueAsPartOfGesture (float plain)
    {
        if (const float n = parameter.convertTo0to1 (plain); ! juce::approximatelyEqual (parameter.getValue(), n))
            parameter.setValueNotifyingHost (n);
    }
    void setValueAsCompleteGesture (float plain)
    {
        if (const float n = parameter.convertTo0to1 (plain); ! juce::approximatelyEqual (parameter.getValue(), n))
        {
            parameter.beginChangeGesture();
            parameter.setValueNotifyingHost (n);
            parameter.endChangeGesture();
        }
    }

    juce::RangedAudioParameter& parameter;

private:
    void parameterValueChanged (int, float) override
    {
        if (juce::Thread::getCurrentThreadId() == messageThread)   // captured at construction: no mutex
            refresh();                                             // state restore, programs, the editor itself
        else
            dirty.store (true, std::memory_order_release);         // host automation: one atomic store
    }
    void parameterGestureChanged (int, bool) override {}

    std::function<void (float)> setControl;
    const juce::Thread::ThreadID messageThread = juce::Thread::getCurrentThreadId();
    std::atomic<bool> dirty { false };
};
```

Build slider, combo-box and button attachments on it by mirroring the JUCE classes in `juce_ParameterAttachments.cpp`:
- the slider's `NormalisableRange<double>` built from the parameter's range, its text functions and double-click default;
- an `ignoreCallbacks` guard while the attachment sets the control;
- gestures on drag start / end for sliders;
- complete gestures for combo boxes and toggles.

The editor owns a `juce::Timer` (30–60 Hz) that calls `poll()` on every attachment and is stopped in the editor's destructor before the attachments are destroyed.

**Properties:**
- **Real-time cost off the message thread:** one atomic store per notified control. No allocation, lock, message or wake-up.
- **No queue:** a flag coalesces any number of changes into one refresh to the latest value. There is no capacity, ordering or overflow to prove, and nothing can grow. Intermediate values of fast automation may not be drawn, as with the stock attachment; the parameter and the audio receive every value.
- **Lifetime:** `addListener` / `removeListener` and `listenerLock` guarantee no callback runs after the destructor returns.
- **Latency of the display:** one timer tick (measured 27–30 ms including waking an idle run loop, with a 60 Hz timer).
- **Idle cost:** one timer per open editor; measured at about +0.1 % of a core on the message thread.

## Anti-Patterns

- `AsyncUpdater`, `ChangeBroadcaster::sendChangeMessage`, `MessageManager::callAsync`, `Component::postCommandMessage`, `Timer::callAfterDelay` or `repaint()` inside a parameter listener.
- `MessageManager::isThisTheMessageThread()` in code that can run on the audio thread (mutex in 9.0.3). Compare thread ids directly.
- **Suppressing or deferring `setValueNotifyingHost`** in the processor or a patched wrapper to make the trace clean. Every listener then sees changes late or not at all: the APVTS atomics, processor-side listeners and the wrapper's host synchronization. Automation recording, undo, control surfaces and state can diverge. It also moves the problem rather than removing it.
- A lock-protected queue from the audio thread to the editor.
- A permissive "few allocations are fine" threshold in the gate.
- Changing a parameter's range or snapping so the wrapper's equality test hides the notification.
- Hiding the problem by testing only with the editor closed.

## Regression Tests

**Unit level (no audio device, CI-friendly):**

1. A thread-filtered `malloc` counter (macOS: `malloc_logger`; count type bit 2 = allocate on one chosen thread). Positive control: a deliberate `malloc` on that thread is counted.
2. Editor closed: change every parameter many times with `setValueNotifyingHost` from a second thread → 0 mallocs (proves the processor itself is clean).
3. Editor open, **queue drained first**: the same → 0 mallocs, the controls unchanged until a poll, one poll applies exactly one refresh per parameter, a second poll applies none, every control then equals its parameter. Build the same test against the stock attachments once and keep the failing log: it proves the test discriminates.
4. The editor's own timer applies an off-thread change without an explicit poll, within a bound.
5. Editor → host: a programmatic slider change notifies once without a gesture; a combo box and a toggle each send begin, one change, end; a synthetic mouse drag on a knob sends begin, changes, end; a message-thread parameter change is shown at once.
6. Lifetime: create and destroy the editor repeatedly while another thread changes every parameter continuously.
7. State restored on a non-message thread with the editor open: controls follow after the poll.

**Host level (a real device callback):**

- Count allocations on the audio thread **inside the callback only**, with a preallocated ring recording size, call stack (`backtrace()` does not allocate) and callback index; symbolize and group by stack on the message thread afterwards.
- Apply automation **in the IO callback** for AU (and for VST3, to cover the playing-transport path).
- Matrix: editor open and closed; trims or other snapping parameters and ordinary knobs; continuous automation at the host's normal rate **and** a new value in every callback; every discrete parameter (mode, bypass, toggles); program selection; 8 instances with 8 editors; editors closed and reopened during automation; a long run (≥ 120 s).
- Confirm in the plug-in's **own saved state** that the automated values arrived (the host's cached value proves nothing).
- **Gate:** zero audio-thread allocations, except framework allocations named by their stack and bounded (see the next section), reported per row and never hidden. Fail on deadline misses and state mismatches too.

**AU parameter order** belongs in the same upgrade qualification: see [parameter-management.md](parameter-management.md#au-parameter-order-and-version-hints).

## What Remains in the Wrappers

The editor fix removes the message-queue path. On JUCE 9.0.3 macOS these remained, in framework code a plug-in cannot change without patching JUCE:

| Item | Format | Cost |
|---|---|---|
| `AudioProcessorParameter::listenerLock` taken on every notified change | both | an uncontended `CriticalSection` on the audio thread |
| `ThreadLocalValue<bool>` in the AU wrapper allocates its holder the first time a thread sets a parameter | AU | 24 bytes, once per instance and thread |
| The VST3 wrapper's C++ `thread_local bool`: in a `dlopen`ed plug-in, dyld allocates the thread's TLS block on first access | VST3 | 136 bytes, once per thread |
| An audio-thread change of the AU bypass parameter calls `PropertyChanged (kAudioUnitProperty_BypassEffect)`; AudioToolbox allocates to notify the host's listener | AU | 32 bytes per bypass change |

Report a plug-in as "no allocation in the editor path", not "real-time safe", unless these are addressed upstream.

## Custom and WebView Interfaces

The rule applies to every interface, not only stock components:
- A custom or 3D (WebView / Three.js) editor must not attach parameter listeners that post to the message thread. Set a flag; publish from the editor's timer or frame loop. JUCE 9's web attachments (`WebSliderParameterAttachment` and the toggle and combo-box ones) wrap `juce::ParameterAttachment` and post from the changing thread: use the [polled web attachments](webview-ui.md#real-time-safe-relay-attachments) instead.
- Keep the message-thread synchronous path, so state restores and program changes are visible immediately.
- Re-run the editor-open allocation gate whenever the interface is replaced.

## Case Study and Sources

**Case study (Prismatica, a circuit-modelled BBD effect):**
- **Before the fix:** with the stock attachments open, 960–1,105 audio-thread allocations per 21 s run at 48 kHz / 32 under trim automation (VST3); about 1,050 under knob automation with AU parameters applied in the IO callback; 25,000–28,000 with a change in every callback.
- **After the fix (polled attachments):** 0 in the editor path, in both formats, across a 14-row gate and a 14-row stress set; sound bit-identical, parameter and AU order unchanged.
- The earlier "AU: 0 allocations" results were a harness artifact (message-thread delivery).
- Implementation: `plugin/Source/PolledAttachments.h` in the Prismatica repository; evidence in its `docs/audio/k3j-*` reports.

**Sources (JUCE 9.0.3):**
- `juce_audio_processors/utilities/juce_ParameterAttachments.cpp` (`ParameterAttachment::parameterValueChanged`);
- `juce_events/broadcasters/juce_AsyncUpdater.cpp/.h`;
- `juce_events/native/juce_MessageQueue_mac.h`;
- `juce_core/containers/juce_ReferenceCountedArray.h` (`removeAndReturn`);
- `juce_audio_plugin_client/juce_audio_plugin_client_VST3.cpp` (`processParameterChanges`, `setValueAndNotifyIfChanged`, `Param::setNormalized`);
- `juce_audio_plugin_client/juce_audio_plugin_client_AU_1.mm` (`SetParameter`, `GetParameterList`, the bypass listener);
- `juce_audio_processors/processors/juce_GenericAudioProcessorEditor.cpp` (flag-and-timer precedent);
- JUCE forum, "BUG REPORT: AsyncUpdater for real time use in ParameterAttachment" (2022, no team reply): https://forum.juce.com/t/bug-report-asyncupdater-for-real-time-use-in-parameterattachment/50645
