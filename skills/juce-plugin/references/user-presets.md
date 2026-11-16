# User Presets (A Preset Library On Disk)

Sounds the user names and saves as files, kept apart from the factory programs the host lists. The library must behave the same on macOS, Windows and Linux, survive damaged files and interrupted writes, never lose a preset to a mistaken click, and keep the audio thread untouched.

**Evidence base.** One product (the Prismatica case study, JUCE 9.0.3). The library, processor and bridge tests (UP.01–UP.16 below) ran on macOS (arm64 and universal builds), Windows x64 and Linux x86_64 in GitHub Actions, and on Linux arm64 in Docker. The editor was accepted by its owner in Logic Pro on macOS. The editor's preset UI in WebView2 (Windows) and WebKitGTK (Linux) has not been checked in a real host. Each statement is marked as one of:

| Label | Meaning |
|---|---|
| **Tested** | implemented, and passed the named automated test on the platforms named |
| **Source-derived** | read in the framework's or browser engine's source (version given); not reproduced as a failure |
| **Case-study choice** | a value or design that worked there; adapt it, do not copy it as a rule |
| **Limitation** | a known gap in the evidence |

## Contents

- [Decide what a preset is](#decide-what-a-preset-is)
- [Where the files live](#where-the-files-live)
- [File format and loading](#file-format-and-loading)
- [Names](#names)
- [Writing a file safely](#writing-a-file-safely)
- [Listing, renaming and deleting](#listing-renaming-and-deleting)
- [Processor: selection and the modified mark](#processor-selection-and-the-modified-mark)
- [Editor bridge](#editor-bridge)
- [A native select in macOS WebKit](#a-native-select-in-macos-webkit)
- [Test seams and the test list](#test-seams-and-the-test-list)
- [Regression checklist](#regression-checklist)
- [Sources](#sources)

## Decide what a preset is

- **Sound parameters only.** Store what makes the sound and its level. Leave out session parameters: input calibration for the user's interface, output routing or monitoring, bypass, and the editor size. A load never changes them. **Case-study choice;** tested by UP.02.
- **Factory programs stay the host's program list.** `getNumPrograms`, the program names and what each program sets do not change when user presets exist. Hosts store a program by its index, so adding user presets to the list would make saved projects point at other programs. **Case-study choice;** tested by UP.09.
- **The selection is session state.** Which preset is selected is not saved in the plug-in state, so the state format stays unchanged and a restored project shows no preset. Storing the name in projects is a product decision; if you do, add a format version first. **Case-study choice;** tested by UP.11.
- **Presets are shared files, not instance state.** Another instance, or the same host after a restart, lists and loads them. **Tested** by UP.08.

## Where the files live

`File::getSpecialLocation (userApplicationDataDirectory)` resolves differently on each platform (JUCE 9.0.3). **Source-derived;** the folder and the Trash were **tested** on all three platforms by UP.16.

| Platform | `userApplicationDataDirectory` | Preset folder to use |
|---|---|---|
| macOS | `~/Library` | `~/Library/Application Support/<Company>/<Product>/Presets`: append `Application Support` yourself |
| Windows | `%APPDATA%` (the Roaming profile, `CSIDL_APPDATA`) | `%APPDATA%\<Company>\<Product>\Presets` |
| Linux | the `XDG_CONFIG_HOME` line of `~/.config/user-dirs.dirs` if that folder exists, else `~/.config` | `~/.config/<Company>/<Product>/Presets` |

- **macOS pitfall.** Without the extra folder the files land in `~/Library/<Company>`, outside the Application Support folder Apple documents for app data. Choose once: moving an existing library later means a migration.
- **Linux detail.** JUCE reads only `~/.config/user-dirs.dirs` here; it does not consult the `$XDG_CONFIG_HOME` environment variable.

```cpp
juce::File defaultPresetDirectory()
{
    auto base = juce::File::getSpecialLocation (juce::File::userApplicationDataDirectory);
   #if JUCE_MAC
    base = base.getChildFile ("Application Support");
   #endif
    return base.getChildFile ("<Company>").getChildFile ("<Product>").getChildFile ("Presets");
}
```

Create the folder on the first save, not at start-up, and report a failure to create it.

## File format and loading

One file per preset, with a product-specific extension. A small XML root records the format version, the plug-in version and, for a circuit model, the model revision. Each parameter is stored as its plain (denormalised) value under its parameter ID:

```xml
<ProductPreset formatVersion="1" pluginVersion="1.2.0" modelRevision="R1">
  <PARAM id="rate" value="0.42"/>
  ...
</ProductPreset>
```

**Read the whole file and validate it before changing any parameter.** A damaged file then never touches the active sound. **Tested** by UP.06: 21 damaged files, including an oversized one, are refused with every parameter unchanged, and a folder named like a preset is neither listed nor loaded. The checks:

1. Cap the file size (64 KiB in the case study) before reading it.
2. Check the root tag. The format version must be an integer. A newer version gets its own message ("saved by a newer version of …"), not "damaged".
3. Each known ID may appear at most once. Ignore unknown IDs: a session parameter found in a file is never applied.
4. Each value must be a plain decimal number. `juce::String::getDoubleValue` reads `"abc"` as 0, so match the text first.
5. Each value must be finite and within the range, with a small tolerance. Choice and switch parameters must be whole steps.
6. Every stored parameter that the layout has must be present.
7. Skip parameters this build does not have, so files from a build with an optional feature still load.

**Apply through the parameters.** For each stored parameter call `beginChangeGesture`, then `setValueNotifyingHost (convertTo0to1 (value))`, then `endChangeGesture`. Do this on the message thread. Do not use `apvts.replaceState`: it would also replace session parameters and non-parameter state.

## Names

The name is the file name, so validate it exactly as given and never trim silently. Apply the same rules on every platform, so a preset folder can move between systems. **Tested** by UP.01 (refused names create no file).

- not empty, with a length limit (64 in the case study);
- none of `/ \ : * ? " < > |` and no control characters;
- no leading dot. That would make a hidden file, and it is how the save's temporary file is told apart ([listing](#listing-renaming-and-deleting));
- no leading or trailing space, and no trailing dot (Windows does not support a trailing space or dot);
- not a Windows device name: `CON`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9`. Compare the part before the first dot, uppercased, because `con.txt` is reserved too;
- not the name of a built-in entry such as "Init".

**Names are case-insensitive on every platform.** macOS and Windows file systems normally are; Linux ext4 is not. Compare names case-insensitively everywhere, so "Lush" and "lush" are the same preset on all three systems. A preset keeps the case it was first saved with, and an overwrite keeps the stored name. **Tested** by UP.03 and UP.16; on Linux's case-sensitive file system, UP.16 checks that a duplicate differing only in case is refused.

## Writing a file safely

`File::replaceWithText` is not enough for user data (JUCE 9.0.3, **source-derived**):

- It writes a `TemporaryFile` with `appendText` and ignores that call's result, then returns `overwriteTargetFileWithTemporary()`.
- If the temporary file cannot be opened, nothing exists to move, so it returns `false` and the target is untouched.
- If the file opens but the write is short (a full disk or a quota), it still returns `true` and replaces the target with the truncated file.

Write through a stream and check it before replacing the target:

```cpp
juce::TemporaryFile temp (target, juce::TemporaryFile::useHiddenFile);
bool written = false;
{
    juce::FileOutputStream out (temp.getFile());
    written = out.openedOk() && out.writeText (text, false, false, "\n");
    out.flush();
    written = written && out.getStatus().wasOk();
}   // close the stream before renaming
if (! written || ! temp.overwriteTargetFileWithTemporary())
    return failure ("could not be saved");
```

`overwriteTargetFileWithTemporary` renames the temporary file over the target: `rename()` on POSIX, `ReplaceFile` on Windows. It tries five times, 100 ms apart, and if every attempt fails, `TemporaryFile`'s destructor deletes the temporary file. **Source-derived.** **Limitation:** the case study never forced a failed or short write in a test. Its tests cover saving, overwriting and refusing (UP.02, UP.03). Add a test that makes the write fail, for example with a read-only folder or a folder standing where the file should be, and checks that the previous file is unchanged.

## Listing, renaming and deleting

**Listing.** List `*.<ext>` with `File::findFiles | File::ignoreHiddenFiles`, then drop every name that fails the name rules. Sort the result naturally and case-insensitively. **Tested** by UP.07.

The name check matters on Windows. `useHiddenFile` only prefixes the temporary file's name with a dot and sets no attribute. Windows decides "hidden" by the `FILE_ATTRIBUTE_HIDDEN` attribute alone, so `ignoreHiddenFiles` keeps a temporary file left by an interrupted save, and only the name check removes it. **Source-derived** (JUCE 9.0.3 `File::isHidden`).

Re-list the folder:
- when the window or the picker gains focus, to catch changes made by other processes;
- when a process-wide revision counter changes, which any instance bumps after it changes the folder.

**Renaming.** Use `File::moveFileTo`. In JUCE 9.0.3, `NAMES_ARE_CASE_SENSITIVE` is defined only on Linux and BSD. Elsewhere `moveFileTo` skips deleting the target when the two paths differ only in case, so a case-only rename happens in place. Do not hand-roll a rename as "delete the target, then move": on a case-insensitive file system, the target of a case-only rename is the source file itself. Refuse a rename onto another existing preset, compared case-insensitively. **Tested** by UP.04 on all three platforms.

**Deleting.** Move the file to the Trash, and report a failure. Never fall back silently to a permanent delete. **Source-derived;** **tested** by UP.16 on all three platforms. `File::moveToTrash` in JUCE 9.0.3:

| Platform | Mechanism |
|---|---|
| macOS | `NSFileManager trashItemAtURL` (Finder Trash) |
| Windows | `SHFileOperation` with `FOF_ALLOWUNDO` (Recycle Bin) |
| Linux | GIO's `g_file_trash`, through `dlopen` of `libgio`. Returns `false` when GIO is missing, so the delete must fail visibly |

In the confirmation dialog, focus Cancel, so Return never deletes. Say where the file goes ("It will be moved to the Trash"). Give the library a constructor flag that deletes permanently, for tests only, so test runs do not fill the Trash.

## Processor: selection and the modified mark

Hosts call `setCurrentProgram` and `setStateInformation` on threads of their choosing. Keep the selection in atomics, and work out "modified" when asked, instead of tracking edits. **Tested** by UP.10, and by UP.14, which processes audio on one thread while another loads, saves and selects presets, and counts zero allocations on the audio thread.

- **State.**
  - the kind of selection, in an atomic: none, init, factory or user;
  - one `std::atomic<float>` per stored parameter: the normalised value the preset gave it, read back from the parameter after loading (after snapping);
  - a selection revision counter, bumped on every change;
  - the user preset's name, which is message-thread only.
- **Modified.** True when a parameter the selected preset sets differs from its reference value by more than a tolerance (1e-5 normalised in the case study; a host echoing a value through float or double is not an edit).
  - A factory program compares only the parameters it sets.
  - Session parameters never count.
- **`setStateInformation`.** Once the state is read, set the kind to none: the values now come from the host.
- **Renaming the selected preset.** The selection follows the file; the values and their references stay.
- **Deleting the selected preset.** The sound stays, but no preset is selected.

## Editor bridge

- **One native function per operation:** state, list, load, save, rename, delete (six in the case study). Never a generic function that takes a path. Check each argument's type and refuse anything else. **Tested** by UP.12 (10 malformed calls refused) and UP.13.
- **Each result carries the whole preset state:** `{ ok, error, state }`. The page renders the state whether the call succeeded or not.
- **Push changes as an event,** from the editor's message-thread timer. Compare a tuple of (selection revision, library revision, modified) with the tuple last sent, and emit only when it differs, so an idle editor sends nothing. **Tested** by UP.12: zero events while idle.
- **Only an emitted event counts as sent.** A native function's result may arrive while the page is not ready to render it, so a call must never suppress the next event.
- `emitEventIfBrowserIsVisible` drops events while the editor is hidden. Resend the full state from `visibilityChanged` when the editor shows again.

## A native select in macOS WebKit

A preset picker built from a `<select>` gets the platform's native popup in WKWebView. Three behaviours of WebKit on macOS are **source-derived** (WebKit `main`, `WebPopupMenu`, `WebPopupMenuProxyMac` and `HTMLSelectElement`, read 2026-11-16):

1. **The open popup is a snapshot.** `WebPopupMenu::updateFromElement()` is empty, so options changed while the popup is open are not shown.
2. **A choice is applied by row position against the current options.** `HTMLSelectElement::valueChanged (listIndex)` calls `optionSelectedByUser (listToOptionIndex (listIndex))`. If options are inserted or removed while the popup is open, for example a "(modified)" mark added because host automation moved a knob, the click selects a neighbour of the row the user chose.
3. **Hidden options are listed.** `HTMLSelectElement::itemStyle()` computes `display: none`, but `WebPopupMenu::populateItems` does not pass it on, and `WebPopupMenuProxyMac::populate` hides no item. An option with `hidden` or `display: none` appears as a row. Chromium hides it, so a browser preview running in Chromium cannot show this.

**Mitigations:**
- Make the first option a fixed status row: disabled, never hidden, with changing text. For example "Choose a preset…" when nothing is selected, and "<name> (modified)" for a modified preset.
- Keep every option's position fixed while the picker has focus. Defer list rebuilds until `blur`.
- Appending a mark as the **last** option also keeps earlier positions. It is safe only while nothing above it changes.

**Evidence.**
- **Tested** in the real WKWebView: in the case study's live check, every row has text and the row count stays constant when the mark appears.
- The owner's Logic acceptance passed. Its checklist includes choosing from the open popup.
- **Limitation:** choosing a row while the list changes was never reproduced in a controlled test, and the WebView2 and WebKitGTK popups were not examined. Check WebKit-specific UI in the real WebView or in WebKit's source, never only in the browser preview.

## Test seams and the test list

- **Construct the library with a folder and a Trash flag.** Every test uses a scratch folder with permanent deletion. **Case-study choice.**
- **Debug-only folder override.** For a page harness, an environment variable such as `<PRODUCT>_PRESET_DIRECTORY` can redirect the library, but only in debug builds. Check that release binaries do not contain it: `strings <binary> | grep -c <PRODUCT>_PRESET_DIRECTORY` must print 0.
- **The real folder and Trash, in CI only.** One test uses the product's own folder and the system Trash. It runs only when an opt-in variable is set, on a disposable CI home. It refuses a folder that already holds presets, reports `NOT RUN` otherwise, and deletes what it made whatever happens. The CI step must require its `PASS` line, so that a skipped run cannot count as a pass.

```bash
<PRODUCT>_TEST_DEFAULT_PRESET_FOLDER=1 ctest --test-dir build -C Release -L default-folder -V | tee up16.txt
grep -q 'PASS  UP.16' up16.txt   # NOT RUN also leaves ctest green, so require the PASS line
```

The case study's tests, as a starting list:

| ID | Checks |
|---|---|
| UP.01 | name rules; refused names create no file |
| UP.02 | save and load restore the stored parameters exactly; session parameters untouched |
| UP.03 | overwrite refused unless asked, in any case; an overwrite keeps the stored name |
| UP.04 | rename: the selection follows; clashes refused; a case-only rename happens in place |
| UP.05 | delete: another preset keeps the selection; the selected one leaves no preset selected |
| UP.06 | damaged, newer and oversized files refused before any parameter changes; unknown IDs ignored |
| UP.07 | listing skips hidden, temporary, invalid and foreign files; natural order |
| UP.08 | another instance lists and loads the same presets |
| UP.09 | factory programs unchanged: count, names, values |
| UP.10 | selection kinds and the modified mark; session parameters never count |
| UP.11 | plug-in state format unchanged; a project restores exactly |
| UP.12 | bridge: argument checks, results carry state, events only on change, none while idle |
| UP.13 | the native function list |
| UP.14 | audio thread during preset activity: no allocation, finite output |
| UP.15 | the product folder path, checked as a path only |
| UP.16 | CI only: the real folder and Trash, round trip, case-insensitive duplicate refused |

**Case-study specifics** (adapt, do not copy):
- nine stored parameters;
- the 64-character and 64 KiB limits;
- the 1e-5 tolerance;
- the extension and root tag;
- six bridge functions;
- "Init" reserved.

## Regression checklist

- [ ] A load changes no session parameter. A damaged file changes nothing.
- [ ] Saving "Lush" over "lush" asks before overwriting, on Linux too.
- [ ] A save interrupted after the temporary file was created leaves the previous file and lists nothing new, on Windows too.
- [ ] Delete moves to the Trash, Recycle Bin or GIO Trash, and fails visibly when it cannot.
- [ ] The factory program count and names are unchanged; old projects restore exactly.
- [ ] No preset activity allocates on the audio thread.
- [ ] An idle editor sends no preset events.
- [ ] In the real WebView, the picker's rows all have text and keep their positions when the modified mark changes.
- [ ] Release binaries contain no debug folder override.

## Sources

- JUCE 9.0.3 `juce_core`:
  - `files/juce_File.cpp` (`replaceWithText`, `moveFileTo`, `NAMES_ARE_CASE_SENSITIVE`);
  - `files/juce_TemporaryFile.cpp`;
  - `native/juce_Files_mac.mm`, `juce_Files_windows.cpp`, `juce_Files_linux.cpp` (`userApplicationDataDirectory`, `moveToTrash`, `isHidden`).
- WebKit `main` (read 2026-11-16):
  - `Source/WebKit/WebProcess/WebCoreSupport/WebPopupMenu.cpp`;
  - `Source/WebKit/UIProcess/mac/WebPopupMenuProxyMac.mm`;
  - `Source/WebCore/html/HTMLSelectElement.cpp`.
- Microsoft, "Naming Files, Paths, and Namespaces": reserved device names, trailing dots and spaces.
- Case study: the Prismatica repository's `plugin/Source/UserPresets.{h,cpp}`, its processor and web editor, `plugin/web/src/presets.ts` and `plugin/tests/ProcessorTests.cpp`. The snippets above are self-contained.
