# Production Plugin Practices

## Contents

- When to use this reference
- Build structure
- Processor structure
- Parameters and state (state saved in a decimal-comma host, factory preset qualification)
- Asset and model loading
- Realtime callback rules
- Tests and measurement targets (filesystem side effects of tests and validators)
- Oversampled circuit-model plugins
- Host validation and release gates
- Third-party notices and the framework licence

## When To Use This Reference

Read this when moving from a minimal JUCE plugin to a product-shaped plugin with many DSP blocks, external assets, model files, IRs, presets, MIDI mapping, tests, measurement tools, and DAW validation. It complements the general JUCE references by focusing on engineering practices that keep a large plugin maintainable and host-safe.

## Build Structure

Use CMake options to separate development convenience from validation:

- Enable `COPY_PLUGIN_AFTER_BUILD` only for plugin audition builds.
- Disable bundle copying for test and measurement builds. Exception: a macOS AU must be installed in
  `~/Library/Audio/Plug-Ins/Components` before `auval` or pluginval can find it; install it in the validation job
  only ([platform-builds.md](platform-builds.md#macos)).
- On Windows the default VST3 copy folder needs administrator rights; keep copying off in CI.
- Keep test and measurement targets separate from plugin formats.
- Make dependency paths explicit and overridable.
- Fail early when required local dependencies are missing, or use a pinned fetch fallback deliberately.
- Link only required JUCE modules; add `juce_dsp` explicitly for DSP chains and convolution.
- Use `juce_add_binary_data` for embedded models, presets, IRs, or image assets that should ship inside the binary.

Current JUCE CMake practice still centers on `juce_add_plugin`, which creates the plugin target and format-specific build products. Keep manufacturer and plugin codes unique and valid for AU/VST compatibility. Use `NEEDS_WEB_BROWSER` only when the plugin actually embeds a web UI.

For multi-target projects, include the same DSP source files in:

- The plugin target.
- A CTest/Catch2 or similar test executable.
- Optional Release-only measurement executable.

Generated JUCE headers and binary data headers often live under the build tree. Test and measurement targets may need include directories for the plugin artefact `JuceLibraryCode` and binary data `JuceLibraryCode`.

## Processor Structure

Keep the processor as the orchestration layer:

- Own APVTS, parameters, state serialization, meters, latency, tail reporting, and host-facing file/status metadata.
- Own DSP block instances and call their `prepare`, `reset`, and `processBlock` methods.
- Keep DSP blocks independent of APVTS; pass small parameter structs into DSP code.
- Prepare all blocks in `prepareToPlay()` using the actual sample rate, output channel count, and a safe maximum block size.
- Reset stateful blocks in `prepareToPlay()` and after loading new models/assets.
- Clear output channels above the active input channel count at the start of `processBlock()`.
- Use `juce::ScopedNoDenormals` at the top of the audio callback.
- Update `setLatencySamples()` when active delayed stages change.

For mono/stereo support, make the policy explicit in `isBusesLayoutSupported()`. If the plugin supports mono and stereo only, reject mismatched input/output layouts and return true only for mono or stereo.

## Parameters And State

Use APVTS with a `ParameterLayout` constructed from `std::unique_ptr<juce::RangedAudioParameter>` objects. Cache `getRawParameterValue()` pointers in the processor constructor and read those atomics in the audio callback.

Useful patterns:

- Helper functions for repeated bool, choice, and float parameter creation.
- Stable parameter IDs; do not rename IDs casually once sessions/presets exist.
- `juce::ParameterID { id, version }` for modern parameter construction.
- Separate non-parameter state in the APVTS ValueTree: selected file paths, display names, status strings, preset metadata, and version markers.
- Persist loaded model, package, preset, IR, or sample paths in `getStateInformation()`.
- On restore, load missing files safely and report visible warnings instead of failing the processor.
- Number text in XML state follows the host's C++ locale in JUCE 9.0.3, so a restore can misread a project saved in a decimal-comma host ([below](#state-saved-in-a-decimal-comma-host)).

### State saved in a decimal-comma host

**Why it happens.** JUCE 9.0.3 writes each number in an XML state through `serialiseDouble`, and so do `var::toString` and `XmlElement::setAttribute (double)`. That function uses a `std::ostream` which takes the process's global C++ locale; only its buffer is classic ([number text](user-presets.md#number-text-follows-the-hosts-c-locale)).
- A host that sets a decimal-comma global locale therefore saves values such as `"0,6600000262260437"`, `"1,0"`, `"0,"` for zero, and `"9,999999974752427e-7"`.
- **Source-derived** (`text/juce_String.cpp`), and **tested** in the Prismatica case study: states written under `de_DE.UTF-8` on macOS, Linux and Windows hold exactly these forms.

**Find where the text is first read as a number before fixing anything.**
- **Unpacking keeps the text.** `AudioProcessor::getXmlFromBinary` and `ValueTree::fromXml` keep each attribute as the original string: `NamedValueSet::setFromXmlAttributes` stores `var (String)`, decoding only `base64:` names. **Source-derived;** consistent with the case study, whose reader received the comma text intact.
- **The first conversion truncates.** It is `String::getDoubleValue` (`CharacterFunctions::readDoubleValue`, which accepts only a point), and it stops at the comma: `"0,66"` reads as 0, `"-3,25"` as −3, and `"9,99…e-7"` as 9. In the case study this call was in its own reader, which rebuilds the tree before `replaceState`. Under `de_DE.UTF-8`, 7 of its 12 parameters restored with other values. **Tested** on all three platforms.
- **The common pattern has no such call to fix.** With `apvts.replaceState (ValueTree::fromXml (*xml))`, `AudioProcessorValueTreeState::setNewState` hands the property `var` to the parameter as a `float`, and a string `var` converts through the same `getDoubleValue` inside JUCE (`juce_AudioProcessorValueTreeState.cpp`, `juce_Variant.cpp`). **Source-derived**, and **tested** in a second case study, Vintage Combo, below. Changing a `getDoubleValue` call elsewhere does not reach this path. Convert each value's text in the tree yourself before `replaceState`, or rebuild the tree with numbers as the first case study does.

**The direct `replaceState` path, with migrations.** **Tested** (Vintage Combo, JUCE 9.0.3, macOS arm64). Its reader runs schema migrations on the tree, then calls `apvts.replaceState`:
- a state from before schema 4 gets Reverb 0;
- one from before schema 5 gets the Cabinet off;
- a missing power parameter is added, on.

What was found and done:
- **Reproduced first.** The plug-in's own `getStateInformation` under `de_DE.UTF-8` wrote `"6,369999885559082"`, and a restore read 6.37 as 6.0; trims and the other knobs truncated the same way.
- **The fix.** After the unchanged migrations and before `replaceState`, every parameter value in the tree is read with the number pattern above and stored back as a `double`. Text that is not a finite number restores that parameter's default.
- **Evidence:**
  - a comma state restores exactly;
  - the same state relabelled schema 3 and 4 still gets its migrations, with exact comma values;
  - `nan`, `inf`, `abc`, an empty value and `1e999` restore the default, with no NaN anywhere;
  - a decimal-point state restores bit for bit and writes the same bytes again;
  - the writer's bytes match the earlier build's for the same sound.
- A text-equal comparison of `getStateInformation` against the previous commit backs the writer claim.
- Like the first case study, the writer is left alone, so a build without the fix still misreads comma states.

**The reader-only fix.** **Tested** (case study). Make it at that conversion:
- **Accept a number.** A trimmed, length-capped value with one optional sign, digits with one decimal point **or** one decimal comma, and an optional exponent: `[-+]?(\d+([.,]\d*)?|[.,]\d+)([eE][-+]?\d+)?`. Replace the comma with a point, then call the same `getDoubleValue` as before, so a decimal-point value reads exactly as it always did.
- **Anything else is no value.** That covers words, mixed or repeated separators (`0,2.5`, `1.234,5`), NaN and Inf. The parameter takes the default it would take if missing, and the rest of the state restores. Before the fix, the case study read such text by its prefix (`"0.5abc"` as 0.5).
- **Keep the existing range clamping and step snapping** after the conversion.
- **Leave the writer alone:** no new field, format or migration.

**Limitations.**
- A build without the fix still misreads a comma state, and states saved in such a host keep their commas. A classic-locale writer would be a separate decision, because it changes those bytes.
- Grouped numbers are refused, which is safe only while no parameter can reach 1000.
- `setStateInformation`'s thread is the host's choice. The fix adds parsing to a path that already parses XML and allocates.
- No real host known to set a comma locale was identified, so no host session was run. Only `de_DE.UTF-8` was exercised.

**Regression checklist:**
- [ ] Every parameter restores from a state the plug-in itself wrote under a real decimal-comma locale (`std::locale::global` in the test, restored afterwards). The values must equal those restored from the same session's decimal-point state, and the saved values for named cases: zero, scientific notation, negatives, range ends, fractions, switches and choices.
- [ ] That check prints NOT RUN without a comma locale, so CI requires its PASS line on each platform. A Linux container needs `locales` and `locale-gen de_DE.UTF-8`.
- [ ] Committed comma states with decimal-point twins, which run without any locale.
- [ ] Decimal-point states, including fixtures from earlier releases, restore bit-identically to a copy of the previous reader kept in the test.
- [ ] Malformed text and mixed separators leave the parameter at its default. Comma values out of range are still clamped, and values between steps snapped.
- [ ] The state writer is unchanged.

*Case study:*
- Prismatica PR #9, stacked on its preset reliability PR #8; open, not merged at the time of writing.
- The fix is in `7d22b53`, in `plugin/Source/StateSerialization.cpp`'s `state::read`. The tests (ST.01–ST.06) are in `plugin/tests/ProcessorTests.cpp`.
- Code and CI at `1add365`, GitHub Actions run 44005725936, where the comma-locale checks ran under `de_DE.UTF-8` on:
  - macOS arm64;
  - Linux x86_64 (Ubuntu 22.04 container);
  - Windows x64 (Windows Server 2025).
- Report: `docs/reliability/state-decimal-comma-reader.md`.

*Second case study:*
- Vintage Combo, `shortwavlabs/vintage-combo`, branch `feature/greenfield-dsp`.
- Reproduction: `docs/reliability/evidence/baseline-bdd6824.json`, section F.
- Fix: `restoreState` in `Source/PluginProcessor.cpp`, commit `9861bab`.
- Tests: group E of `Tests/PresetReliability.cpp`, with committed baseline state blobs, decimal point and decimal comma, in `Tests/fixtures/state`.
- macOS arm64 only.
- Report: `docs/reliability/cross-product-reliability-audit.md`.

### Factory preset qualification

A factory preset made only of legal parameter values can still drive the engine somewhere it fails. Validating the values is not enough.

1. **Validate every value.** Each one is in range, snapped to a legal step and whole for switches and choices. Pin the table in a test, so a change to a value or the order changes the test.
2. **Render representative audio for every preset.** Use stimuli like the real input, at a hot but realistic level. For a guitar amplifier that means band-limited plucks rather than a naive sawtooth, whose instant steps a real pickup never produces.
3. **Check every render.** The output must be finite and not silent, with no engine fault, recovery or fail-closed state.
4. **Separate preset faults from engine limits.** Render the defaults or Init with the same stimuli. A fault that also appears there belongs to the engine, not the preset.
5. **Keep the approved DSP.** Choose another value; do not change the engine to suit a preset. Prove the sound is unchanged with the existing golden renders, through the built plug-in.
6. **Approval needs an audition.** Until the owner has listened, label the bank provisional.

**Tested** (Vintage Combo, group F5 of `Tests/PresetReliability.cpp`, commit `9861bab`).
- The first draft of one clean preset tripped the engine's fail-closed path on band-limited plucks peaking at −12 dBFS.
- A sweep traced the trip to one switch combined with high settings of two other controls. The final value avoids that region, and the engine was not changed.
- The seven presets and Init render with no fault from band-limited plucks peaking at −6 dBFS.
- A naive sawtooth trips the defaults too: that is an engine limit, which the presets do not cause and which this work did not fix.
- **Owner accepted:** the owner reported after `f5cb173` that they had auditioned and approved all seven factory sounds. No Vintage Combo commit records that yet: the cited reports, at `f5cb173`, still call the bank provisional.
- The thresholds found belong to that engine. Find your own engine's limits by measurement.

User preset libraries (named files the user saves, renames and deletes, kept apart from the host's program list) are in [user-presets.md](user-presets.md): storage per platform, atomic writes, validation before applying, the Trash, the modified mark and their tests.

Do not do message-thread work from parameter callbacks. If parameter changes need preset-dirty tracking or UI notification, set an atomic flag in the listener and publish from a `juce::Timer` or message-thread path. This includes the editor: JUCE's stock attachments post from the audio thread under host automation ([host-automation-and-editor-sync.md](host-automation-and-editor-sync.md)).

Once a version has shipped, adding a parameter can move existing AU parameters in Logic and GarageBand even when every ID is unchanged; follow [the version-hint rules](parameter-management.md#au-parameter-order-and-version-hints) and check the hosted list.

For user-facing controls that can click or zipper, smooth values with `juce::SmoothedValue` or a DSP-block-local smoother. Current JUCE docs expose `SmoothedValue` helpers for applying smoothly interpolated gain; use the concept for gain and adapt it carefully for filters.

## Asset And Model Loading

File-backed assets belong outside `processBlock()`:

- Model JSON parsing.
- Neural model construction.
- IR file loading.
- Preset file reads/writes.
- Looper/recorder disk writes.
- Large image or binary data decoding.

Embedded assets:

- Use `juce_add_binary_data` when the asset is fixed at build time.
- Parse embedded JSON from memory on a non-audio path.
- Store status and metadata in state so the UI can display it.

User-selected assets:

- Resolve folder/file selections before loading.
- For package folders, expect a known filename such as `model.rtneural.json`.
- Read metadata opportunistically, but keep audio safe if metadata is absent.
- Restore paths from DAW state and show missing-file warnings.
- Prefer background workers for production loads that may block.

For realtime publication, publish immutable raw pointers or lightweight handles to the audio thread. Keep ownership and retirement off the audio thread. Avoid reference-count churn in the callback when a raw pointer plus non-audio ownership list will work.

## Realtime Callback Rules

Inside `processBlock()`:

- Read cached atomics and immutable pointers.
- Process already prepared DSP and already constructed models.
- Update lightweight atomics for meters or observations.
- Keep stack allocations small and bounded.

Never do:

- File I/O.
- JSON/XML parsing.
- Model or convolution engine construction.
- Heap allocation or container growth.
- Locking or blocking waits.
- UI calls.
- Logging/string formatting.
- Object destruction that could free data read by another callback.

If a JUCE helper might allocate, lock, or message the UI, assume it is not callback-safe until inspected.

## Tests And Measurement Targets

Use tests for both DSP blocks and processor behavior.

DSP block tests:

- Bypass identity.
- Finite output at extremes.
- Reset determinism.
- Sample-rate stability.
- Automation safety.
- Stereo routing/linking.
- Latency/tail behavior.

Processor tests:

- Parameter IDs exist and ranges make sense.
- Bus layouts accept/reject the intended channel sets.
- Model/asset load metadata is reflected in state.
- State save/restore preserves paths and parameters.
- Missing files fail safely.
- Latency updates when delayed stages are enabled or replaced.
- A user preset library: names, atomic writes, damaged files, the Trash, the audio thread
  ([test list](user-presets.md#test-seams-and-the-test-list)).
- Block-size invariance and other exact-equality checks run on every shipped CPU and compiler: on x86, JUCE's
  Intel-only snap-to-zero makes `juce::dsp` filter and oversampler output depend on block size
  ([platform-builds.md](platform-builds.md#floating-point-results-differ-between-cpus)).

Measurement target:

- Build Release-only, with the plugin's effective compile and link optimization settings (link-time optimization included). A separate target does not automatically inherit the plugin target's options; it has them only where the build shares them deliberately (a common interface target, a shared library, common configuration). Verify the effective settings instead of assuming parity from shared sources.
- Benchmark per-stage and full-chain timing at target sample rates and buffer sizes.
- Include expensive stages such as neural inference, convolution, tuner analysis, pitch shifting, reverb, and full chain.
- Capture automation stress metrics where abrupt changes can cause clicks or instability.
- Benchmark digital silence and stereo with identical channels as their own cases; neither is automatically cheap.
- Construct and own the engine as the product does, and keep one harness for before/after comparisons.
- Dump reference renders so a performance change can be null-tested against the previous build.

A headless target measures work; a live audio-device callback measures deadline behaviour and editor cost. For a CPU investigation or a performance pass, follow [performance-investigation.md](performance-investigation.md).

### Filesystem side effects of tests and validators

Isolating the feature under test does not isolate the plug-in. Before running tests, pluginval, auval or a host harness on a developer's machine, list every path the plug-in, its editor and its standalone can write or create.

| What | Example |
|---|---|
| user data | the preset folder, the Trash it deletes into |
| diagnostics | fault or crash logs, telemetry, written on a timer or on a state change |
| configuration | the standalone's settings file, audio device state, research or feature flag files |
| licensing | license files, activation markers, an install record |
| caches and temporary files | temporary files beside a target, extracted assets, WebView caches |

Then decide, for each path, how the tests avoid it:
- a test seam, for example a folder parameter or an injected Trash call;
- a scratch location;
- or an accepted, recorded side effect.

A validator such as pluginval runs the real plug-in, so test seams in the test target do not apply to it.

To prove the isolation on macOS, run the suite inside a `sandbox-exec` profile. The profile allows everything but denies `file-write*` on the user paths that must stay untouched; any write there then fails the test instead of passing unseen.
- Run a negative control on a scratch path first, to show that the profile denies writes on that macOS version.
- **Limitation (Vintage Combo):** an AU registered in-process could not be instantiated inside such a profile, so its in-process AU checks ran outside it.

Two traps on macOS:
- **`HOME` does not redirect JUCE's user folders.** JUCE resolves `userHomeDirectory` with `NSHomeDirectory()`, which ignores `$HOME` for an unsandboxed process. Redirecting `HOME` therefore does not isolate a test that uses `userApplicationDataDirectory`. **Source-derived** (`native/juce_Files_mac.mm`), and confirmed by a scratch probe during the Vintage Combo work. That probe is not committed: `NSHomeDirectory()` returned the real home with `HOME` set elsewhere.
- **A validator writes through the plug-in's own diagnostics.** Vintage Combo's preset tests and its pluginval runs denied writes to the preset folder and the Trash. Yet its two pluginval runs on the VST3 made the plug-in append 15 and 13 rows to the user's real `fault-log.jsonl`. Its editor, once its page loads, also lists the real preset folder, read only; that read was not observed.
  - **Tested** (Vintage Combo, `docs/reliability/cross-product-reliability-audit.md`).
  - That diagnostic log is **not** isolated in Vintage Combo; the side effect is only recorded.

## Oversampled Circuit-Model Plugins

JUCE-specific practices for plugins whose DSP runs an oversampled circuit model (the modelling method itself is in the `circuit-to-dsp` skill):

- Choose the oversampling factor in `prepareToPlay()` from the host rate with an algorithm (smallest power of two reaching the model's minimum validated internal rate, with a flagged fallback), and build `juce::dsp::Oversampling` there with the maximum block size. Pass `useIntegerLatency = true` when the host must compensate an exact integer latency.
- Some hosts and validators query latency before the first `prepareToPlay()`. Define a valid pre-prepare policy: if the latency is invariant, or can be computed correctly before the host rate is known (for example integer-latency oversampling whose latency is the same for every factor the policy can choose), report it in the constructor; otherwise do not invent a value. Always call `setLatencySamples()` with the correct value in `prepareToPlay()` and on every reconfiguration, and test the wrappers and hosts you actually target.
- Expose bypass through `getBypassParameter()`. In current JUCE wrappers the host bypass then arrives as that parameter and `processBlockBypassed()` is used only when no bypass parameter exists; verify this on your JUCE version. Implement a dry path delayed by exactly the reported latency plus a crossfade, and test that the bypassed output equals the delayed input bit for bit after the crossfade.
- Non-parameter state such as an interface calibration reference: a user edit notifies the host (`updateHostDisplay (ChangeDetails().withNonParameterStateChanged (true))`); `setStateInformation()` stores the value **without** notifying, so restoring a session does not mark it dirty.
- Store a **model revision** string (changes only when the audio changes) separately from the **state schema version** (changes only when serialization changes). Under that convention a proven bit-exact implementation change (scheduling, inlining) leaves the model revision alone; the commit and the binary hash still identify the build. Test that a session saved by an older model revision restores every parameter unchanged and re-saves with the new revision.
- Publish engine facts the editor shows (factor, latency, degraded flag) through atomics written in `prepareToPlay()`, not by reading engine members from the message thread.
- Guard the product formats in CMake: fail configuration if a target you do not ship (for example `<Plugin>_Standalone`) appears.

## Host Validation And Release Gates

Before wider testing:

- Configure and build Release plugin artifacts.
- Run the audio-thread allocation gate under host automation with the editor **open and closed**, AU automation delivered from the audio callback ([host-automation-and-editor-sync.md](host-automation-and-editor-sync.md#regression-tests)).
- For a release that adds parameters: compare the hosted AU parameter list with the previous release's, and restore a previous release's state ([parameter-management.md](parameter-management.md#au-parameter-order-and-version-hints)).
- For a release that adds or changes factory programs, check:
  - the program list;
  - the hosted VST3 parameter surface, which gains a Program parameter;
  - a project saved after a factory program and an edit, which must restore the edit;
  - the qualification renders above.
  - See [factory programs and host restore](parameter-management.md#factory-programs-and-host-restore).
- List the files the tests and validators will write, and isolate them ([filesystem side effects](#filesystem-side-effects-of-tests-and-validators)).
- Build and run Release tests.
- Run the measurement harness.
- Validate AU with `auval` on macOS.
- Validate AU/VST3 with pluginval when available.
- Smoke in at least one real DAW.

DAW smoke should include:

- Mono and stereo inserts.
- 32, 64, and 128 sample buffers where the plugin claims low-latency use.
- Automation write/read.
- Host bypass and plugin bypass.
- Session save, close, reopen, and playback.
- A factory program from the host's own preset menu, then an edit, save and reopen: the edit remains. Note the host's preset display with the editor open and closed.
- Missing asset path restore.
- Sample-rate changes.
- Multiple instances of the heaviest expected preset, with the editor closed and with one editor open.

For signed distribution, add platform signing, notarization, installer validation, clean-machine install, strict plugin validation, and checksums: [signing-and-notarization.md](signing-and-notarization.md). Windows and Linux builds and their validation (pluginval under Xvfb on Linux) are in [platform-builds.md](platform-builds.md).

## Third-Party Notices And The Framework Licence

Ship a notices file in every package and inside each bundle (`Contents/Resources`), and derive its contents from
the build, not from a sibling product's file.

- **JUCE modules.** List the modules the plug-in target actually compiled: each module is one
  `include_juce_<module>` translation unit among the target's object files. A copied list can name modules the
  product does not link (*tested*: a second product's copied list named `juce_dsp`, which it did not link).
- **Code those modules compile in.** In the case study (JUCE 9.0.3; `juce_audio_utils` and `juce_gui_extra`
  with their dependencies), the compiled modules brought in:
  - zlib, HarfBuzz and SheenBidi;
  - LunaSVG and PlutoVG;
  - libpng, the IJG JPEG library and libwebp;
  - FLAC, libogg, libvorbis, Opus, opusfile and libopusenc.

  Each has its own notice to reproduce. Re-derive the list from the module sources of the JUCE version you ship.
- **Format SDKs.** List them per format and platform: the VST3 SDK, the PreSonus plug-in extensions, the
  AudioUnitSDK (macOS AU only), and the WebView2 SDK loader (Windows only).
- **The page bundle.** List every npm package the bundler included (the JUCE WebView library, three.js, …),
  taken from the lockfile's production dependencies or the bundler's metafile.
- **Media.** Fonts (for example SIL OFL) and images such as HDRIs or textures. Record the author, source and
  licence even where none is required (CC0).
- **Not shipped.** Say which system components are loaded from the user's machine and not distributed:
  WebKit, WebKitGTK, the WebView2 Runtime, GTK.

**State the framework licence you actually hold.** JUCE is dual-licensed: AGPLv3, or the JUCE End User Licence
Agreement. Under the JUCE 9 EULA (read 2026-11-16 at <https://juce.com/legal/juce-9-licence/>; recheck it, terms
and prices change):

| Licence type | Eligibility (revenue or funding, previous 12 months) |
|---|---|
| Starter | free; up to US$20,000 |
| Indie | paid; up to US$300,000 |
| Pro | paid; no limit |
| Educational | free; educational use, as the EULA defines it |

- **What counts.** For an individual: all revenue or funding from their use of JUCE, including donations,
  sponsorship and advertising. For a company: all revenue of the company and its affiliates, from all sources.
- **Above the limit,** move to a higher type, or stop developing and distributing. Sales of the plug-in count,
  so check eligibility before paid releases.
- **No mixing.** Starter, Indie and Pro may not be used at the same time, nor products combined across types.
  Every developer working on JUCE-dependent code needs a licence seat.
- **Keep JUCE's notices.** §2.9 forbids removing or altering JUCE's copyright and proprietary notices. Keep
  JUCE's copyright line, its dual-licence statement and its warranty disclaimer. The JUCE 9 EULA has no
  splash-screen or attribution requirement.
- **Never write that a paid licence was bought unless it was.** Do not copy another product's licence wording
  without checking it, and never ship an unresolved `TODO` about the licence.

## Sources

- JUCE `AudioProcessor` reference (https://docs.juce.com/master/classAudioProcessor.html): `setLatencySamples()`, `getBypassParameter()`, `processBlockBypassed()`, `updateHostDisplay()`.
- JUCE `dsp::Oversampling` reference (https://docs.juce.com/master/classdsp_1_1Oversampling.html).
- JUCE 9 End User Licence Agreement (https://juce.com/legal/juce-9-licence/), read 2026-11-16.
- JUCE 9.0.3 `juce_core` and `juce_audio_processors` sources:
  - `text/juce_String.cpp` (`serialiseDouble`) and `text/juce_CharacterFunctions.h` (`readDoubleValue`);
  - `containers/juce_NamedValueSet.cpp` (`setFromXmlAttributes`) and `containers/juce_Variant.cpp` (string to double);
  - `utilities/juce_AudioProcessorValueTreeState.cpp` (`setNewState`).
- Wrapper behaviour (when latency is queried, how host bypass is delivered) differs between JUCE versions and plugin formats; check the pinned JUCE version's wrapper sources and test in the target hosts.
- Vintage Combo (`shortwavlabs/vintage-combo`, branch `feature/greenfield-dsp`), the second case study for state in a decimal-comma host, factory preset qualification and test side effects:
  - `docs/reliability/cross-product-reliability-audit.md`;
  - `docs/presets/factory-user-preset-architecture.md`;
  - `Tests/PresetReliability.cpp`;
  - commits `bdd6824` to `f5cb173`.
