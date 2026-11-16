# Building For macOS, Windows And Linux

What changes when a JUCE plugin that builds on macOS is also built, tested and packaged on Windows and Linux.
Three kinds of fact: JUCE behaviour, from the JUCE 9.0.3 sources (recheck when upgrading JUCE); results marked
*tested*, observed in CI and container builds of a JUCE 9.0.3 VST3 with a WebView editor; and runner images,
action releases and prices, which are vendor facts checked 2026-10. WebView
editors have extra platform rules in [webview-ui.md](webview-ui.md#platform-backends); signing and notarization
are in [signing-and-notarization.md](signing-and-notarization.md).

## Contents

- [Quick Reference](#quick-reference)
- [Formats, Bundle Layout And Copy Folders](#formats-bundle-layout-and-copy-folders)
- [macOS](#macos)
- [Windows](#windows)
- [Linux](#linux)
- [Floating-Point Results Differ Between CPUs](#floating-point-results-differ-between-cpus)
- [CI Jobs](#ci-jobs)
- [CI Evidence And Test Portability](#ci-evidence-and-test-portability)
- [GitHub Actions Behaviour](#github-actions-behaviour)
- [Reproducing Linux Locally](#reproducing-linux-locally)
- [Common Mistakes](#common-mistakes)
- [Sources](#sources)

## Quick Reference

| | macOS | Windows | Linux |
| --- | --- | --- | --- |
| Compiler | Apple Clang (Xcode) | MSVC, Visual Studio 2019 or newer (JUCE minimum); no MinGW, no cross-compiling from Linux | GCC ≥ 7 or Clang ≥ 6 |
| CMake generator in CI | default | default Visual Studio generator with `--config Release` (or Ninja inside the MSVC developer environment) | Ninja |
| Formats JUCE builds | AU, AUv3 (Xcode generator), VST3, AAX, LV2, Standalone | VST3, AAX (x64, non-GNU), LV2, Standalone | VST3, LV2, Standalone |
| Architectures | universal `arm64;x86_64` | x64 (ARM64/ARM64EC possible) | x86_64 (aarch64 possible) |
| WebView editor | system WKWebView | WebView2 (must be selected explicitly) | WebKitGTK 4.1/4.0, loaded at run time |
| Extra build deps | none | WebView2 SDK NuGet package for WebView editors | apt packages below |
| Editor tests in CI | run directly | run directly | need an X display: `xvfb-run` |
| Host validation | `auval` (installed AU), pluginval | pluginval | pluginval under `xvfb-run` |
| Runtime floor | `CMAKE_OSX_DEPLOYMENT_TARGET` | Windows 10 1607 (JUCE 9) | the build machine's glibc |
| Package | signed, notarized `.pkg` | `.zip` and/or installer, Authenticode-signed | `.tar.gz` with `install.sh`, checksums |

## Formats, Bundle Layout And Copy Folders

- `FORMATS VST3 AU` can stay as is everywhere: JUCE intersects the requested list with what the platform
  supports (`_juce_get_platform_plugin_kinds`; AU only on Darwin), so no per-platform CMake branch is needed.
- VST3 layout: macOS `Name.vst3/Contents/MacOS/Name`; Windows `Name.vst3/Contents/x86_64-win/Name.vst3` (the
  inner file is the DLL); Linux `Name.vst3/Contents/x86_64-linux/Name.so` (or `aarch64-linux`). All get
  `Contents/Resources/moduleinfo.json` (`VST3_AUTO_MANIFEST` defaults on), whose `"Version"` field is a handy
  release check. The file has trailing commas, so `grep` it rather than parsing it as JSON.
- Default `COPY_PLUGIN_AFTER_BUILD` destinations: macOS `~/Library/Audio/Plug-Ins/{VST3,Components}`; Windows
  64-bit VST3 `C:\Program Files\Common Files\VST3` (needs an elevated build) and LV2 `%APPDATA%\LV2`; Linux
  `~/.vst3` and `~/.lv2`. Turn copying off in CI.

## macOS

- Universal builds: `-DCMAKE_OSX_ARCHITECTURES="arm64;x86_64"`; check both slices with `lipo -archs`.
- AUs are found through the system registry, which only scans `/Library/Audio/Plug-Ins/Components` and
  `~/Library/Audio/Plug-Ins/Components`. Validating a build-directory `.component` with pluginval fails with
  "No types found" on a clean runner (it passes on a dev machine only because an installed copy is found by its
  type/subtype/manufacturer). In CI, `ditto` the component into `~/Library/Audio/Plug-Ins/Components`, remove
  `~/Library/Caches/AudioUnitCache` (and `/Library/Caches/AudioUnitCache` with `sudo` after a system-wide install), `killall -9 AudioComponentRegistrar`, wait a moment, run
  `auval -v <type> <subtype> <manufacturer>`, then pluginval on the installed path. VST3 can be validated in
  place.
- Validate the universal AU's Intel slice too: `arch -x86_64 auval -v <type> <subtype> <manufacturer>` runs it
  through Rosetta on an Apple-silicon runner (*tested* on `macos-26`). Guard the step with
  `arch -x86_64 /usr/bin/true` so that a runner without Rosetta reports the check as not run, not passed.
- A universal build's x86_64 slice runs the Intel code paths described in
  [Floating-Point Results Differ Between CPUs](#floating-point-results-differ-between-cpus), which Apple-silicon
  CI never exercises.

## Windows

**Toolchain.** GitHub's `windows-2025` image ships Visual Studio 2026 (MSVC 14.5x); CMake's default generator
picks it. If a runner's CMake lacks the installed Visual Studio's generator, use Ninja inside the MSVC
developer environment.

**Code that compiles on Clang/GCC but not MSVC (C++17):**

| Construct | MSVC replacement |
| --- | --- |
| `std::aligned_alloc` | `_aligned_malloc(size, alignment)` from `<malloc.h>`, freed with `_aligned_free`, not `std::free`. In a test allocator that overrides `operator new`, change only the aligned overloads |
| `clock_gettime (CLOCK_THREAD_CPUTIME_ID, …)` | `GetThreadTimes (GetCurrentThread(), …)`: kernel + user `FILETIME`s in 100 ns units. Include `<windows.h>` with `NOMINMAX` and `WIN32_LEAN_AND_MEAN` |
| `__attribute__((always_inline))` behind `#if __GNUC__ \|\| __clang__` | add `#elif defined(_MSC_VER)` → `__forceinline`. It implies inline linkage: safe for private members defined and used in one `.cpp` |
| `#pragma clang diagnostic …` | warnings only; guard with `#if defined(__clang__)` |
| designated initializers, VLAs, GNU statement expressions | rewrite; MSVC C++17 rejects them |

**Build plumbing.**
- `find_program(NPM npm)` can find the extension-less shell script; use `find_program(NPM NAMES npm.cmd npm REQUIRED)`.
  The Visual Studio generator prefixes `.cmd`/`.bat` custom commands with `call`, so several npm commands in
  one `add_custom_command` all run.
- Paths in Git Bash steps: pass `$(cygpath -m "$RUNNER_TEMP")` (forward slashes) to CMake. Do not rely on a shell
  waiting implicitly for a GUI-subsystem tool such as `pluginval.exe`: wait explicitly and check its exit code.
  From Git Bash (*tested*) a plain invocation waits and returns the exit code; in PowerShell use
  `$p = Start-Process pluginval.exe -ArgumentList $args -Wait -PassThru; if ($p.ExitCode) { exit $p.ExitCode }`.
- Git on Windows may rewrite text files to CRLF on checkout, depending on `core.autocrlf` (Git for Windows
  installs with it on). Make hashed inputs (fixtures, SPICE netlists) invariant with `.gitattributes`
  (`eol=lf` for them, `binary` for binary blobs) instead of relying on a runner's configuration.
- WebView editors: see [webview-ui.md](webview-ui.md#windows-webview2). In CI, install the SDK with
  `nuget install Microsoft.Web.WebView2 -Version <version> -OutputDirectory <dir>` and configure with
  `-DJUCE_WEBVIEW2_PACKAGE_LOCATION=<dir>`.

**ARM64.** Steinberg recommends an `arm64x-win` VST3 for Windows on Arm. Before building it, check that
`FindWebView2.cmake` picks the arm64 loader (it compares `CMAKE_SYSTEM_PROCESSOR` with lowercase `arm64`) and
that the VST3 manifest helper can run on the build machine.

## Linux

**Packages** (JUCE's list, trimmed to a VST3 effect with a WebView editor; JUCE 9 requires `libxi-dev`):

```bash
sudo apt-get install cmake ninja-build g++ pkg-config libasound2-dev libjack-jackd2-dev \
  libfreetype-dev libfontconfig1-dev libx11-dev libxcomposite-dev libxcursor-dev libxext-dev \
  libxinerama-dev libxrandr-dev libxrender-dev libxi-dev libwebkit2gtk-4.1-dev xvfb
```

Add `libcurl4-openssl-dev` only with `JUCE_USE_CURL=1`, `ladspa-sdk` only for hosting, and
`libglu1-mesa-dev mesa-common-dev libegl-dev` only when linking `juce_opengl`. Development packages pulled with
apt recommends also bring fonts and Mesa software GL, which editor tests under Xvfb need.

**glibc baseline.** A binary needs a glibc at least as new as the one it was built against (Ubuntu 22.04: 2.35,
Debian 12: 2.36, Ubuntu 24.04: 2.39). Build in an old-distribution **container**, for example `ubuntu:22.04` on
an `ubuntu-24.04` runner (GitHub is retiring the `ubuntu-22.04` runner image), and check the result:

```bash
objdump -T "Name.so" | grep -oE 'GLIBC_[0-9.]+' | sort -Vu | tail -1   # must not exceed the baseline
readelf -d "Name.so" | grep NEEDED                                     # webkit/gtk must not appear
```

*Tested* (JUCE 9.0.3 VST3 with a WebView editor, GCC 11 and 12, x86_64 and aarch64): the direct `NEEDED`
entries were libc, libm, libstdc++, libgcc_s, fontconfig, freetype and the dynamic loader. WebKitGTK and GTK are
loaded at run time; check your own binary with `readelf` rather than assuming the same list.

**Targets JUCE did not create.** `juce_add_plugin(... NEEDS_WEB_BROWSER TRUE)` gives its targets the GTK/WebKit
include paths. A plain `add_executable` that compiles the editor (a test runner) does not get them and fails
with `gtk/gtk.h: No such file or directory`:

```cmake
if(TARGET juce::pkgconfig_JUCE_BROWSER_LINUX_DEPS)   # created by JUCE on Linux/BSD only
    target_link_libraries(MyPluginTests PRIVATE juce::pkgconfig_JUCE_BROWSER_LINUX_DEPS)
endif()
```

**Static libraries inside the plug-in.** A project static library (a DSP core shared by the plug-in and its
tests) linked into the Linux `.so` must be position-independent. Without it, the link fails with
`relocation R_X86_64_PC32 against symbol … can not be used when making a shared object; recompile with -fPIC`
(*tested*). macOS and Windows do not need this.

```cmake
if(UNIX AND NOT APPLE)
    set_target_properties(my_dsp PROPERTIES POSITION_INDEPENDENT_CODE ON)
endif()
```

The Windows counterpart (the WebView2 loader) and the alternative of creating the test runner with
`juce_add_console_app (... NEEDS_WEB_BROWSER TRUE NEEDS_WEBVIEW2 TRUE)` are in
[webview-ui.md](webview-ui.md#cmake-and-webview2).

**Headless tests.** Creating a WebView forks a helper that needs an X display; without one it logs "cannot open
display" and the test process dies with SIGPIPE. Run `xvfb-run -a ctest …` and `xvfb-run -a pluginval …`. In a container without user namespaces
also set `WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS=1` for the test steps (CI only, never in the product).

**Package.** `.tar.gz` with the bundle, a README (requirements: glibc, X11/XWayland, WebKitGTK and GTK 3
packages) and an `install.sh` copying to `~/.vst3` or, with `--system`, `/usr/lib/vst3`. Test it in CI by
unpacking the archive and running `install.sh` with `HOME` set to an empty directory, then validating the
installed copy. Publish `SHA256SUMS`.

## Floating-Point Results Differ Between CPUs

- **JUCE snap-to-zero is Intel-only.** `juce::dsp` filters and `dsp::Oversampling` (polyphase IIR) call
  `snapToZero()` on their state at the end of every processed block (`juce_Oversampling.cpp`, the TPT, SVF,
  IIR, Linkwitz-Riley and ballistics filters). It zeroes values within ±1e-8 through `JUCE_SNAP_TO_ZERO`, which
  is a no-op unless `JUCE_INTEL` (`juce_FloatVectorOperations.h`). So on x86 (Intel Macs, Windows x64, Linux
  x86_64) output depends on the host's block size; on ARM it does not. A test asserting that 1-sample and
  64-sample blocks are bit-identical fails only on x86. When `processBlock()` already sets `ScopedNoDenormals`,
  define `JUCE_DSP_ENABLE_SNAP_TO_ZERO=0` for all targets (JUCE documents this case as safe). The flag also turns
  explicit `filter.snapToZero()` calls into no-ops, since they go through the same `util::snapToZero`. ARM output
  is unchanged by construction; prove it with a bit-exact render comparison before and after.
- Apple Clang fuses multiply-adds by default and x86 builds without FMA do not, and `long double` is 64-bit on
  MSVC and Apple silicon, 80-bit on x86_64 Linux and Intel Macs, and 128-bit on Linux aarch64. Compare rendered audio only within one
  platform; cross-platform references need tolerances.
- Exact-equality tests between two code paths in one binary (a stereo kernel against two mono runs, block
  sizes) can still differ under a new compiler's inlining. Run them on every new toolchain before trusting a
  port.

## CI Jobs

Recent Node-20 majors (`actions/checkout@v4`, `actions/setup-node@v4`, `actions/upload-artifact@v4` and `@v5`)
are now run under Node 24 with a deprecation warning (observed 2026-10); older majors target even older Node
versions. Take majors from the actions'
release pages, not from this file (v7 when checked, 2026-10). In jobs that hold signing credentials, pin to full
commit SHAs ([signing-and-notarization.md](signing-and-notarization.md#windows-release-workflow)).

Linux job (Ubuntu 22.04 glibc on a current runner):

```yaml
linux:
  runs-on: ubuntu-24.04
  container: ubuntu:22.04
  env:
    DEBIAN_FRONTEND: noninteractive
    WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS: 1     # container only
  steps:
    - run: apt-get update && apt-get install -y ca-certificates curl git unzip xvfb xauth <packages above>
    - uses: actions/checkout@v7          # after git is installed, so it is a real clone
    # setup-node, configure with -G Ninja and "$GITHUB_WORKSPACE" (not ${{ github.workspace }}:
    # in container jobs that expression is the host path), build, then:
    - run: xvfb-run -a ctest --test-dir build -L "unit" --output-on-failure
    - run: xvfb-run -a "$RUNNER_TEMP/pluginval/pluginval" --strictness-level 5 --validate-in-process "<bundle>"
```

Windows job: `runs-on: windows-2025`, `defaults: run: shell: bash`, WebView2 SDK from NuGet, configure without
`-G`, `cmake --build … --config Release`, `ctest -C Release`, then `pluginval.exe` from the `pluginval_Windows.zip`
release (extract with `7z`). Name each job's uploaded artifact uniquely (`pluginval-logs-linux`, …).

Cost: GitHub-hosted minutes are priced per OS (in 2026 about $0.006 Linux, $0.010 Windows and $0.062 macOS per
minute); a macOS job of a few minutes costs more than Linux and Windows jobs several times longer.

## CI Evidence And Test Portability

A port is qualified by what each platform's CI actually ran, not by green jobs. *Tested* in a JUCE 9.0.3 product
whose suite started macOS-only and was ported to Windows and Linux CI.

**Tests that need one platform's facilities.**
- Replace macOS-only facilities with JUCE equivalents where one exists:
  - CommonCrypto → `juce::SHA256`;
  - a CFRunLoop wait → `MessageManager::runDispatchLoopUntil`. Off macOS this needs
    `JUCE_MODAL_LOOPS_PERMITTED=1` on the test target.
- Where no equivalent exists, report the check as `NOT MEASURED` or `NOT RUN` with the reason, never as a pass.
  Examples: an allocation counter hooked into libmalloc, or the `mach` memory footprint. A check that depends on
  an instrument (an allocation count) needs the instrument's positive control to run on the same platform;
  without the control, the count is `NOT MEASURED`.
- **Compare per-group check counts across platforms.** A group that quietly runs fewer checks on one platform
  still exits 0. Print a `SUMMARY <group>: <checks> checks, <fails> FAIL` line per group, and tabulate macOS,
  Windows and Linux side by side. Every difference must be a documented not-run item.

**Inputs a clean runner does not have.**
- Commit the approved runtime assets (models, images, camera presets) and check them against a manifest of
  SHA-256 hashes at build time. Keep them out of any folder a frontend build copies recursively, or they ship
  twice.
- Mark hashed inputs `-text` or `binary` in `.gitattributes` ([Windows](#windows)). On Windows, a checked-out
  `package-lock.json` hashed differently until it was marked.
- Large fixtures that stay out of Git (golden renders): give the fixture-free test groups their own ctest label
  (for example `portable`), run only that label in CI, and list the groups that did not run in the release report.

**Keeping evidence.**
- ctest rewrites `Testing/Temporary/LastTest.log` on every run. When a job runs ctest twice (a suite, then an
  opt-in test), copy the log after the first run, or its output is lost.
- **Windows writes CRLF.** Strip `\r` before matching lines read back from a file such as `CMakeCache.txt`
  (`tr -d '\r' < CMakeCache.txt | grep …`). Python's text mode writes `\r\n` on Windows, which breaks
  `shasum -c` on another system: write checksum files with `open(path, "w", newline="\n")`.
- **Record the source commit, not the merge commit.** A `pull_request` run checks out a synthetic merge commit.
  Record `github.event.pull_request.head.sha` as the source, next to `github.sha`.
- **Read the compiler from CMake's own record.** `CMAKE_CXX_COMPILER_ID` and `CMAKE_CXX_COMPILER_VERSION` in
  `build/CMakeFiles/<cmake-version>/CMakeCXXCompiler.cmake` work for MSVC, GCC and Clang alike.
- Join lists of tests run or skipped with a separator that cannot occur in an item (`;`). Commas occur inside
  parenthesised notes.

**Check the artifact itself, with negative controls.** Assert the identity in the built bundle, not in the build
options. A standard-library Python script runs unchanged on all three runners:
- **Identity.**
  - VST3: `Name`, `Version` and the `CID` values in `Contents/Resources/moduleinfo.json`, read by pattern
    (the file has trailing commas).
  - macOS: also `CFBundleIdentifier` and `CFBundleShortVersionString` in `Info.plist`.
  - AU: also the type, subtype, manufacturer, name and packed version (`major<<16 | minor<<8 | patch`) in the
    first `AudioComponents` entry.
- **Architecture.**
  - macOS: every required slice in `lipo -archs`.
  - Windows: the PE machine field at `e_lfanew + 4` (`0x8664` for x64).
  - Linux: the ELF class byte and `e_machine` at offset 18 (`0x3E` for x86_64).
- **Embedded assets.** `juce_add_binary_data` stores the bytes verbatim. Find the first 4 KiB of each approved
  asset in the binary, then compare the whole file at that offset. The same hashes on all three platforms prove
  they ship the same assets.
- **Required and forbidden strings.** The bridge's function names must be present. Debug-only environment
  variables and test hooks must be absent.
- **Negative controls.** Run the same script on builds that must fail (a development variant with another
  identity, a debug build) and require the failure. A check that has never failed proves nothing.

## GitHub Actions Behaviour

From GitHub's documentation, read 2026-11-16; recheck before relying on it.

- **Release workflows: `workflow_dispatch` only.** A dispatch trigger works only once the workflow file is on the
  default branch. A release workflow added in a pull request cannot be dispatched until it is merged, so rehearse
  its steps in the PR's own jobs or locally first.
- **`paths` filters on `pull_request`** compare the pull request's whole diff with its base (a three-dot diff),
  not the files of the latest push. Once any file in the PR matches, every push re-runs the workflow.
- **`[skip ci]`** in a pushed commit's message creates no run. It therefore does not cancel runs already in
  progress for the same concurrency group.
- **Runner capacity.** A job that fails after waiting, with a message that it was "not acquired by Runner …
  after multiple attempts", is a capacity failure (*tested*: seen on macOS runners). Re-run it with
  `gh run rerun <run-id> --failed`; do not change the workflow.
- **Stacked pull requests.** When PR B's base is PR A's branch, deleting A's branch after merging A retargets B
  to A's base. If the repository does not delete merged branches automatically, delete A's branch after merging,
  then check that B's base reads `main` before merging B. *Documented; not yet exercised in the case study.*

## Reproducing Linux Locally

Docker reproduces the Linux job: run the job's `run:` steps in `ubuntu:22.04`, fetching JUCE at the CI pin and
Node from its tarball in place of the actions. arm64 containers run natively on Apple silicon;
`--platform linux/amd64` runs under emulation, slowly (the link-time-optimized link is single-threaded).
pluginval publishes Linux builds for x86_64 only. This reference's Windows path is native MSVC on Windows (JUCE
dropped MinGW and does not support building Windows binaries from Linux); cross-compilation is not covered.
Without a Windows machine, the Windows CI job is the first build. Docker Desktop shares only some host folders (not `/Applications`):
fetch dependencies inside the container instead. Mount the repository read-only and `git clone --depth 1 file:///src`
inside the container (with `--branch <branch>` for another branch), so the container's `npm ci` never touches the
host's `node_modules` (*tested*).

## Common Mistakes

- Testing only on Apple silicon and assuming x86 output is the same (see snap-to-zero).
- Building Linux releases on the newest runner image, which raises the glibc floor for every user.
- Running Linux editor tests without a display and reading the SIGPIPE as a product crash.
- Adding Windows or Linux only to the plugin target and forgetting test executables that compile the editor.
- Validating a macOS AU in the build folder.
- Copying plugins after build on Windows CI (needs admin) instead of passing `-D<copy option>=OFF`.
- Linking a non-PIC static library into the Linux `.so`.
- Counting a test that printed `NOT RUN` as a pass because ctest stayed green; require its `PASS` line.
- Trusting a green test group whose check count dropped on one platform.
- Losing the first ctest run's log to a second run in the same job.
- Recording a pull request's merge commit as the source commit.

## Sources

- GitHub Docs (read 2026-11-16): "Events that trigger workflows" (`workflow_dispatch`, `pull_request`, path
  filters), "Skipping workflow runs", "Changing the base branch of a pull request", "Re-running workflows and jobs".
- JUCE 9.0.3: `extras/Build/CMake/JUCEModuleSupport.cmake` (`_juce_get_platform_plugin_kinds`),
  `JUCEUtils.cmake` (copy folders, `pkgconfig_JUCE_BROWSER_LINUX_DEPS`, `NEEDS_WEBVIEW2`),
  `FindWebView2.cmake`, `docs/Linux Dependencies.md`, `BREAKING_CHANGES.md` (libxi-dev, Windows 10 1607),
  `modules/juce_dsp/juce_dsp.h` (`JUCE_DSP_ENABLE_SNAP_TO_ZERO`),
  `modules/juce_audio_basics/buffers/juce_FloatVectorOperations.h` (`JUCE_SNAP_TO_ZERO`).
- [GitHub runner images](https://github.com/actions/runner-images) (Windows Visual Studio and Ubuntu
  deprecation notices); [pluginval releases](https://github.com/Tracktion/pluginval/releases);
  [Steinberg VST3 plugin locations and format](https://steinbergmedia.github.io/vst3_dev_portal/pages/Technical+Documentation/Locations+Format/Plugin+Locations.html).
