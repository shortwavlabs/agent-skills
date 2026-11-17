# User Presets (A Preset Library On Disk)

Sounds the user names and saves as files, kept apart from the factory programs the host lists. The library must behave the same on macOS, Windows and Linux, survive damaged files and interrupted writes, never lose a preset to a mistaken click, and keep the audio thread untouched.

**Evidence base.** One product (the Prismatica case study, JUCE 9.0.3). The library, processor and bridge tests (UP.01–UP.16 below) ran on macOS (arm64 and universal builds), Windows x64 and Linux x86_64 in GitHub Actions, and on Linux arm64 in Docker. The exception is UP.14's allocation count, which needs a macOS facility and is `NOT MEASURED` elsewhere. The editor was accepted overall by its owner in Logic Pro on macOS; item-level results were not recorded. The editor's preset UI in WebView2 (Windows) and WebKitGTK (Linux) has not been checked in a real host. The file-safety statements below (writing, renaming, deleting, number text) also draw on a second JUCE 9.0.3 product, a pedal plugin with the same kind of library; its tests ran on macOS arm64 (locally and in GitHub Actions), Windows x64 and Linux x86_64 in GitHub Actions, and each statement it supports says "pedal plugin". Each statement is marked as one of:

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
4. Each value must be a plain decimal number. `juce::String::getDoubleValue` reads `"abc"` as 0, so match the text first. Accept a decimal comma as well as a point, and read it as the decimal separator ([number text](#number-text-follows-the-hosts-c-locale)).
5. Each value must be finite and within the range, with a small tolerance. Choice and switch parameters must be whole steps.
6. Every stored parameter that the layout has must be present.
7. Skip parameters this build does not have, so files from a build with an optional feature still load.

**Apply through the parameters.** For each stored parameter call `beginChangeGesture`, then `setValueNotifyingHost (convertTo0to1 (value))`, then `endChangeGesture`. Do this on the message thread. `apvts.replaceState` replaces the whole state, session parameters and non-parameter state included. It is simpler when a preset is meant to be the entire state, but not when a load must leave some of it alone. **Case-study choice.**

### Number text follows the host's C++ locale

JUCE 9.0.3 formats a `double` (`String (double)`, a `var` holding a double, and therefore every `ValueTree` property written as XML) through a `std::ostream`. It imbues the classic locale on the stream buffer, but the stream that formats the number takes the process's global C++ locale (`text/juce_String.cpp`, `StackArrayStream`). **Source-derived**, and reproduced with JUCE 9.0.3 on macOS: after `std::locale::global (std::locale ("de_DE.UTF-8"))`, `String (0.83)` is `"0,83"` and a preset holds `value="0,8299999833106995"`.

- A host that sets a decimal-comma global locale therefore writes presets, and plug-in state, with decimal commas. `getDoubleValue` stops at the comma: `"0,83"` reads as 0 and `"1,0e-7"` as 1. For plug-in state, where JUCE first converts the text and the tested reader fix, see [state saved in a decimal-comma host](production-plugin-practices.md#state-saved-in-a-decimal-comma-host).
- A preset loader should accept one decimal comma in place of the point and parse the value that was saved. **Tested** (pedal plugin): every decimal-point fixture converted to commas loads bit-identically to the original; a preset saved by JUCE under a comma locale holds commas and loads its saved values (macOS and Windows; **not run** on Linux, whose CI container had no comma locale).
- The writer is not fixed by this. Files saved in such a host keep their commas, and an older plug-in version that reads with `getDoubleValue` misreads them. **Limitation:** no host known to set a comma locale was identified; the pedal plugin left its writer and state format unchanged.

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
- If the file opens but the write is short (a full disk or a quota), it still returns `true` and replaces the target with the truncated file. **Tested** (pedal plugin, macOS and Linux): with `RLIMIT_FSIZE` lowered to 64 bytes, `replaceWithText` of 200 bytes returned `true` and left 64 bytes.

**Checking the stream is not enough either** (JUCE 9.0.3, **source-derived**). `FileOutputStream::write` only copies a small payload into its buffer and returns `true`. `flush()` discards `flushBuffer()`'s result. `writeInternal` sets the stream's status only when `::write` (POSIX) or `WriteFile` (Windows) fails outright, not when it writes fewer bytes than asked, which a full disk or quota can do. A short write therefore leaves `openedOk()`, the write's result and `getStatus()` all reporting success (reproduced on macOS and Linux with `RLIMIT_FSIZE`, below; the Windows path is read in source only). After closing the stream, compare the size of the file on disk with the number of bytes intended.

**Replace the target with one rename, not `overwriteTargetFileWithTemporary`** (JUCE 9.0.3, **source-derived**). That call uses `File::replaceFileIn` → `moveInternal`. On POSIX, when `rename()` fails, `moveInternal` falls back to `copyInternal`; on Linux (`native/juce_CommonFile_linux.cpp`) that deletes the target and then copies, and deletes the target again if the copy fails, so a failed replacement can lose both versions. (macOS's `copyInternal` refuses an existing destination.) On Windows it is `ReplaceFile` without a backup name, which Microsoft documents can fail with `ERROR_UNABLE_TO_MOVE_REPLACEMENT` after the replaced file no longer exists.

```cpp
// The bytes File::replaceWithText writes (UTF-8, no BOM, CRLF), so existing files keep their exact format.
juce::MemoryOutputStream bytes;
bytes.writeText (text, false, false, "\r\n");

// Next to the target (same volume); ".tmp" keeps a leftover out of every "*.<ext>" listing.
const auto temp = target.getParentDirectory().getNonexistentChildFile (
    "." + target.getFileName() + "." + juce::String::toHexString (juce::Random::getSystemRandom().nextInt()), ".tmp", false);
const juce::TemporaryFile cleanup (target, temp);   // deletes the temporary file on every return below
{
    juce::FileOutputStream out (temp);
    if (! out.openedOk() || ! out.write (bytes.getData(), bytes.getDataSize()))
        return false;
    out.flush();                                     // fsync (POSIX) or FlushFileBuffers (Windows)
    if (out.getStatus().failed())
        return false;
}                                                    // closed before the rename
if (temp.getSize() != (juce::int64) bytes.getDataSize())
    return false;                                    // a short write: the target is untouched
// One rename that replaces the target or leaves it as it was:
// POSIX std::rename (from, to); Windows MoveFileExW (from, to, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH).
// Retry it a few times on Windows (JUCE tries five times, 100 ms apart): a scanner or indexer can hold the target.
return renameOver (temp, target);
```

**Tested** (pedal plugin, macOS, Linux and Windows): each step made to fail through an injected fault (temporary file not created, half the bytes written, flush failure, rename failure) for an overwrite and a new file; the previous file stays byte-identical and no temporary file remains. A real short write runs with `RLIMIT_FSIZE` lowered (macOS and Linux; ignore `SIGXFSZ` and print nothing while the limit is low, since stdout may be a file). An empty folder standing where the file should be survives the failed write on all three platforms (JUCE's Linux fallback would delete it). **Limitation:** Windows has no `RLIMIT_FSIZE`, so its short write is simulated only, and a real full disk (`ENOSPC`) was not reproduced anywhere. The Prismatica case study (UP.02, UP.03) covers saving, overwriting and refusing, not failed writes.

## Listing, renaming and deleting

**Listing.** List `*.<ext>` with `File::findFiles | File::ignoreHiddenFiles`, then drop every name that fails the name rules. Sort the result naturally and case-insensitively. **Tested** by UP.07.

The name check matters on Windows. `useHiddenFile` only prefixes the temporary file's name with a dot and sets no attribute. Windows decides "hidden" by the `FILE_ATTRIBUTE_HIDDEN` attribute alone, so `ignoreHiddenFiles` keeps a temporary file left by an interrupted save, and only the name check removes it. **Source-derived** (JUCE 9.0.3 `File::isHidden`).

Re-list the folder:
- when the window or the picker gains focus, to catch changes made by other processes;
- when a process-wide revision counter changes, which any instance bumps after it changes the folder.

**Renaming.** Do not use `File::moveFileTo`, and do not hand-roll "delete the target, then move". In JUCE 9.0.3 `moveFileTo` deletes an existing destination before moving, unless the two paths compare equal, and it compares path **strings**: ignoring case on macOS and Windows, exactly on Linux and BSD (`NAMES_ARE_CASE_SENSITIVE`). **Source-derived.** Where the file system matches names more loosely than that comparison, the "destination" is the source itself and the rename deletes the preset:

- macOS: APFS ignores Unicode normalisation, while JUCE lists names precomposed. A new name typed or pasted with a decomposed accent (`e` + U+0300) is a different string but the same file. **Tested** (pedal plugin): the rename deleted the preset before the fix below.
- Linux on a case-insensitive volume (ext4 casefold, CIFS, vfat): `"foo"` → `"Foo"` is the same file, but JUCE compares exactly. **Source-derived;** not reproduced.

Instead:
- Refuse a rename onto another listed preset whose name matches ignoring case, compared by full path so the source never counts as "another".
- Refuse when anything exists at the destination that is not the source itself (compare `File::getFileIdentifier`).
- Then rename once, without deleting anything: `std::rename` on POSIX, `MoveFileW` on Windows (it refuses an existing destination other than the source itself).

**Tested** (pedal plugin, all three platforms, with the single rename): a case-only rename happens in place, and a rename to the other accent encoding in capitals keeps the preset and its contents. Prismatica's UP.04 passed with `moveFileTo`, on ordinary volumes only; it does not show `moveFileTo` is safe where names match loosely.

The same loose matching affects **Save As**: a new preset must not be written over a file that already exists at its path even when no listed name matches. Refuse it. **Tested** (pedal plugin, macOS: before the fix, Save As of the decomposed spelling silently replaced the existing preset).

**Deleting.** Move the file to the Trash, and report a failure. Never fall back silently to a permanent delete. **Source-derived;** **tested** by UP.16 on all three platforms (each runner had a Trash or Recycle Bin). `File::moveToTrash` in JUCE 9.0.3:

| Platform | Mechanism |
|---|---|
| macOS | `NSFileManager trashItemAtURL` (Finder Trash); fails when the item can't be trashed |
| Windows | `SHFileOperation` with `FOF_ALLOWUNDO \| FOF_NOCONFIRMATION \| FOF_SILENT \| FOF_NOERRORUI`: the Recycle Bin **when possible**, otherwise a permanent delete that still returns success (below) |
| Linux | GIO's `g_file_trash`, through `dlopen` of `libgio`. Returns `false` when GIO is missing or the item can't be trashed, so the delete must fail visibly |

**Windows: `moveToTrash` is not always recoverable.** `FOF_ALLOWUNDO` recycles only if possible. Where an item can't be recycled (a drive without a Recycle Bin, a network path, the bin turned off by the user or by policy), the shell deletes it permanently and the call still succeeds; the file is gone, so a "gone means recycled" check passes. `FOF_WANTNUKEWARNING` only shows a confirmation first, and `IFileOperation` with `FOFX_RECYCLEONDELETE` makes the same decision. From Microsoft's documentation of the flags (not JUCE source); JUCE's own call is characterised by the test below. To recycle **or fail**:

- Use `IFileOperation` (`FOF_ALLOWUNDO | FOFX_RECYCLEONDELETE | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI`) with an `IFileOperationProgressSink`.
- In `PreDeleteItem`, return an error unless `dwFlags` contains `TSF_DELETE_RECYCLE_IF_POSSIBLE`. An error cancels that delete and the rest of the operation (**documented** by Microsoft). That the flag is absent exactly when the item would be removed permanently is a forum-sourced claim; the test below is what verifies it.
- Count success only when `PostDeleteItem` receives a non-null `psiNewlyCreated`, the item now in the Recycle Bin (**documented**: null means it was deleted outright), and the file is gone from its folder.

**Tested** (pedal plugin, Windows x64 in GitHub Actions): with the documented policy "Do not move deleted files to the Recycle Bin" (`HKCU\Software\Microsoft\Windows\CurrentVersion\Policies\Explorer`, `NoRecycleFiles` = 1) set on the disposable runner, deleting a file and a preset fails and both stay unchanged, with no dialog; JUCE's `File::moveToTrash` on the same runner returned `true` and the file was gone, deleted permanently. With the bin available, the same code moves presets to the Recycle Bin (UP.16-style real-folder test). Run such a test only on a disposable machine, require its `PASS` line, and give the step a timeout in case a shell dialog appears. The same refusal held for the file reached through a network path (`\\localhost\C$\…`), in the same run with the policy set. **Limitation:** a drive without a Recycle Bin, and a network path without the policy, were not exercised separately; only Windows Server 2025 (the `windows-2025` runner) was tested.

In the confirmation dialog, focus Cancel, so Return never deletes. Say where the file goes ("It will be moved to the Trash"). Give the library a constructor flag that deletes permanently, for tests only, so test runs do not fill the Trash.

## Processor: selection and the modified mark

Hosts call `setCurrentProgram` and `setStateInformation` on threads of their choosing. Keep the selection in atomics, and work out "modified" when asked, instead of tracking edits. **Tested** by UP.10, and by UP.14, which processes audio on one thread while another loads, saves and selects presets. UP.14 counts zero allocations on the audio thread on macOS, where its allocation counter (a libmalloc hook) exists. On Windows and Linux it checks the other conditions and reports the count `NOT MEASURED`.

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
- The owner's Logic acceptance passed overall. Its checklist includes choosing from the open popup, but item-level results were not recorded.
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
| UP.14 | audio thread during preset activity: finite output; no allocation (counted on macOS only) |
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
- [ ] Delete moves to the Trash, Recycle Bin or GIO Trash, and fails visibly when it cannot. On Windows with the Recycle Bin turned off, the file is still there afterwards.
- [ ] A short write (half the bytes, and a real one under `RLIMIT_FSIZE` where the OS has it) leaves the previous file byte-identical; success means the bytes on disk were counted.
- [ ] A failed replacement never deletes the previous file (no `overwriteTargetFileWithTemporary`, no `moveFileTo`).
- [ ] A rename or Save As to another spelling of an existing name (case, accent encoding) never deletes or replaces that preset.
- [ ] A preset with decimal commas loads the values it was saved with.
- [ ] The factory program count and names are unchanged; old projects restore exactly.
- [ ] No preset activity allocates on the audio thread, on every platform that has an allocation counter.
- [ ] An idle editor sends no preset events.
- [ ] In the real WebView, the picker's rows all have text and keep their positions when the modified mark changes.
- [ ] Release binaries contain no debug folder override.

## Sources

- JUCE 9.0.3 `juce_core`:
  - `files/juce_File.cpp` (`replaceWithText`, `replaceFileIn`, `moveFileTo`, `NAMES_ARE_CASE_SENSITIVE`);
  - `files/juce_TemporaryFile.cpp`, `files/juce_FileOutputStream.cpp` (`write`, `flush`, `flushBuffer`);
  - `native/juce_SharedCode_posix.h` (`writeInternal`, `moveInternal`), `native/juce_CommonFile_linux.cpp` (`copyInternal`);
  - `text/juce_String.cpp` (`StackArrayStream`, number formatting);
  - `native/juce_Files_mac.mm`, `juce_Files_windows.cpp`, `juce_Files_linux.cpp` (`userApplicationDataDirectory`, `moveToTrash`, `isHidden`).
- WebKit `main` (read 2026-11-16):
  - `Source/WebKit/WebProcess/WebCoreSupport/WebPopupMenu.cpp`;
  - `Source/WebKit/UIProcess/mac/WebPopupMenuProxyMac.mm`;
  - `Source/WebCore/html/HTMLSelectElement.cpp`.
- Microsoft, "Naming Files, Paths, and Namespaces": reserved device names, trailing dots and spaces.
- Microsoft: `ReplaceFile` (`ERROR_UNABLE_TO_MOVE_REPLACEMENT`), `SHFILEOPSTRUCT` (`FOF_ALLOWUNDO`, `FOF_WANTNUKEWARNING`), `IFileOperation::SetOperationFlags` (`FOFX_RECYCLEONDELETE`), `IFileOperationProgressSink::PreDeleteItem` and `PostDeleteItem`; the "Do not move deleted files to the Recycle Bin" policy (`NoRecycleFiles`).
- CodeGuru forum, "How to tell if a file or a folder could be placed into the Recycle Bin?": the `TSF_DELETE_RECYCLE_IF_POSSIBLE` reading, verified by the Windows test above.
- Second case study: a pedal plugin's checked write, rename, Windows delete and preset loader, and their tests (not public). The snippets above are self-contained.
- Case study: the Prismatica repository's `plugin/Source/UserPresets.{h,cpp}`, its processor and web editor, `plugin/web/src/presets.ts` and `plugin/tests/ProcessorTests.cpp`. The snippets above are self-contained.
