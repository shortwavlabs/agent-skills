# Gumroad Licensing (License Keys In A JUCE Plugin)

A runbook for selling a JUCE plugin on Gumroad with per-sale license keys: product set-up (including the Gumroad
MCP server), the Gumroad API facts that shape the code, a `LicenseManager` shared by every instance in a host,
demo-mode dropouts, HTTPS on all three platforms, and the WebView activation UI. The pattern is "the plugin calls
Gumroad's verify endpoint itself"; a signing server is the upgrade path, described at the end.

Gumroad's API behaviour, the MCP server's tools and the JUCE 9.0.3 APIs named here were checked in 2026-11:
confirm vendor facts before relying on them. Italic case-study notes describe one pedal plugin; they show how a
decision was reached, not defaults.

## Contents

- [Quick Reference](#quick-reference)
- [Choose The Architecture](#choose-the-architecture)
- [Gumroad Product Set-Up](#gumroad-product-set-up)
- [Gumroad MCP Server](#gumroad-mcp-server)
- [The Verify Endpoint](#the-verify-endpoint)
- [Reading Gumroad's Source](#reading-gumroads-source)
- [Units](#units)
- [LicenseManager Rules](#licensemanager-rules)
- [HTTPS From JUCE](#https-from-juce)
- [Demo Mode In The Audio Path](#demo-mode-in-the-audio-path)
- [WebView Activation UI](#webview-activation-ui)
- [Tests And Validation](#tests-and-validation)
- [Ways Activations Get Burned](#ways-activations-get-burned)
- [Upgrade Path: A Signing Server](#upgrade-path-a-signing-server)
- [Common Mistakes](#common-mistakes)
- [Sources](#sources)

## Quick Reference

| Decision | Pattern (bracketed figures are the case study's choices, not defaults) |
| --- | --- |
| Who calls Gumroad | The plugin, `POST https://api.gumroad.com/v2/licenses/verify`; no server of your own |
| Product identifier | `product_id` from the License key block (required for products created on or after 2023-01-09) |
| Seats | `uses` counter per key; refuse activation above a fixed N, stated on the product page (case study: 3) |
| Re-check | In the background when the last success is older than a re-check interval, `increment_uses_count=false` (case study: 7 days) |
| Offline grace | Licensed for a fixed period after the last successful check (case study: 30 days) |
| Unlicensed | Demo dropouts, only while the effect is engaged (case study: 2 s of silence every 45-60 s, 10 ms fades) |
| State | One `LicenseManager` per host process (`juce::SharedResourcePointer`), a worker thread, an atomic flag for the audio thread |
| Storage | `license.json` next to the presets, never in `getStateInformation` |
| Linux HTTPS | `JUCE_USE_CURL=1` + `JUCE_LOAD_CURL_SYMBOLS_LAZILY=1`, and probe for libcurl before the first request |
| UI | Header button + dialog in the WebView; four native functions and one status event; the page never touches the network |
| Tests | The gate compiles into the shipped plugin target only; tests drive the manager through a fake `Verifier` |

## Choose The Architecture

| | A: plugin verifies directly | B: plugin talks to your server |
| --- | --- | --- |
| Infrastructure | None | A service (for example a Cloudflare Worker) for the product's lifetime |
| Offline check | Unsigned cached state: forgeable, the check can be patched out | Key file signed with your private key, checked offline with an embedded public key |
| Seat management | Only the seller frees a seat (dashboard) | Your server frees a seat on "deactivate this computer" |
| Refunds | Seen at the next re-check | Immediately, through Gumroad's signed Ping webhook |
| Fit | Small catalogue, low price, honest-customer protection | Piracy or seat-reset support becomes a measurable cost |

Start with A and keep the network call behind one interface, so B replaces only that class. Every client-only
scheme can be cracked; A aims to keep honest customers honest without hurting them offline.

JUCE's `juce_product_unlocking` (`OnlineUnlockStatus`, `KeyGeneration::generateKeyFile`) is not a drop-in for A:
it expects an RSA-signed key file produced by *your* server. It fits B.

## Gumroad Product Set-Up

1. Create the product (by hand or with the MCP server below). Description copy: avoid other companies' trademarks
   (name "a classic yellow overdrive pedal", not the brand and model).
2. On the product's **Content** page: **Insert → License key**. Leave the multi-seat toggle off unless selling site
   licenses (then `is_multiseat_license` is true and `quantity` is the seat count).
3. Copy the `product_id` the block shows while editing. It equals the `id` the API and the MCP server return for
   the product. It is not secret: compile it in.
4. The key the editor shows (labelled "License key (sample)") is a placeholder, the same for every product. Gumroad
   answers it with "That license does not exist for the provided product." Useful to test the error path only.
5. A draft product is not for sale to anyone, the seller included ("This product is not currently for sale").
   A real test key needs a purchase: publish briefly with a 100 %-off, single-use, expiring discount code, buy it,
   unpublish. A purchase made while signed in as the seller is flagged `test: true`.
6. Before rotating a leaked key in the dashboard, reset its **Uses**: the old count stays on the license.

Customers find their key in the receipt email, on the download page, and through
`https://gumroad.com/license-key-lookup` (link it from the plugin as "Find my key").

## Gumroad MCP Server

When the session has the Gumroad connector (an MCP server bound to the creator's store), use it for the store side:

| Task | Tool | Notes |
| --- | --- | --- |
| Confirm the account | `get_account` | Name, username, storefront URL, currency |
| Find products | `list_products`, `get_product` | `get_product` returns the id to compile in |
| Create the product | `create_draft_product` | Name, `price_cents`, currency, description; stays a draft. Confirm name and price with the creator first |
| Edit copy and listing | `update_product` | Category, tags, summary, receipt text, permalink |
| Media and deliverables | `add_cover`, `add_file`, `add_content_link` | Files up to 250 MB from a public URL; larger in the editor |
| Test purchase code | `create_discount_code` | `percent_off`, `product_id`, `max_purchase_count`, `expires_at` |
| Go on/off sale | `publish_product`, `unpublish_product` | Confirm with the creator before either |
| After launch | `list_sales`, `get_customers`, `get_sales_totals`, `get_analytics` | Read-only |

It cannot insert the License key block (do that in the Content tab) and it cannot buy anything (checkout is the
buyer's, with their email). Record the product id in the project's licensing doc once the block exists.

## The Verify Endpoint

`POST https://api.gumroad.com/v2/licenses/verify`, form-encoded, no API token, CORS `*`:

| Parameter | Value |
| --- | --- |
| `product_id` | From the License key block |
| `license_key` | Trimmed and upper-cased (keys are an upper-case UUID regrouped as four 8-hex groups) |
| `increment_uses_count` | Counts a use unless the value is exactly the string `false`; `"0"`, `"no"` or a typo all count |

Legacy `product_permalink`, `id` and `link_id` only work for products created before 2023-01-09; omitting
`product_id` on a newer product returns **500**, not 404.

| Reply | Meaning | Plugin action |
| --- | --- | --- |
| 404 `"That license does not exist for the provided product."` | Unknown key, other product's key, rotated (old) key | Unlicensed |
| 404 `"This license key has been disabled."` | Seller disabled it, **or the purchase was fully refunded** (Gumroad disables the key itself) | Unlicensed |
| 404 `"Access to the purchase associated with this license has expired."` | Seller revoked access | Unlicensed |
| 404 that is not JSON `{"success":false,…}` | A proxy page or moved endpoint, not Gumroad's answer | Retry later; never remove a license on it |
| 400 `"The '<name>' parameter must be a string."` | Bug on your side | Retry later |
| 0 / timeout / 429 / 5xx / unreadable body | Network or service trouble | Retry later; keep the license within grace; honour `Retry-After` |
| 200 `success: true` | Key exists and is enabled | Licensed **unless** `chargebacked`, or `disputed && !dispute_won`: a chargeback does not disable the key |

Also in the 200 reply: `uses` (top level, the only seat counter), `purchase.email` (show "Licensed to…", never
log it), `refunded` (normally already a 404; keep the check as a guard), `subscription_ended_at` /
`_cancelled_at` / `_failed_at` for memberships (the key stays enabled when a membership ends), and `test` (present
as `true` only for a seller self-purchase, otherwise absent, never `false`). A 200 with `success: true` but no
`purchase` object or a non-numeric `uses` is malformed: retry later, never license.

Rate limits: none at Gumroad's application layer for this route (only malformed-parameter throttling); any
Cloudflare edge limit is unknown. At one call per activation and about one per week per machine a limit is
unlikely to matter; handle 429 anyway.

Seller-only endpoints (`enable`, `disable`, `decrement_uses_count`, `rotate`) need an OAuth `access_token` that
can act on the whole store: never ship it in a plugin. Consequence for A: the plugin cannot free a seat.

## Reading Gumroad's Source

Gumroad's code is public (`antiwork/gumroad`), and every API response carries an `x-revision` header that is a
commit of that repository. For behaviour the docs omit, read the code at that commit:

```bash
curl -s -D - -o /dev/null -X POST https://api.gumroad.com/v2/licenses/verify -d product_id=x -d license_key=y | grep -i x-revision
gh api -H 'Accept: application/vnd.github.raw' "repos/antiwork/gumroad/contents/app/controllers/api/v2/licenses_controller.rb?ref=<sha>"
```

Useful files: `app/controllers/api/v2/licenses_controller.rb` and its Go port `go_web/internal/licenses/`
(reply bodies, fields), `app/modules/purchase/refundable.rb` (refunds disable keys), `config/initializers/rack_attack.rb`
(rate limits), `app/models/license.rb` (key format). A fake key with `increment_uses_count=false` is a safe live
probe of error shapes.

## Units

All in one folder (for example `Source/licensing/`), one namespace:

| Unit | Responsibility |
| --- | --- |
| `LicenseConfig.h` | Product id, URLs, `kMaxActivations`, timeout, re-check and grace periods, every customer-facing string |
| `LicenseRules` | Pure: `Evaluation evaluate (int httpStatus, const String& body, bool activating)` → licensed / unlicensed / retryLater + message, email, uses |
| `Verifier` | `virtual Reply verify (const String& key, bool countUse) = 0; virtual void cancel() = 0;` — the seam for tests and for B |
| `GumroadVerifier` | The real call (below); takes an injectable "HTTPS available?" probe |
| `LicenseFile` | `read()` / `write()` / `remove()` of `license.json` in a given folder |
| `LicenseManager` | Shared state, worker thread, flag, change notifications; constructed from `Deps { verifier, folder, now(), deviceId }` |
| `ProductionLicenseManager` | Default-constructible subclass passing the real dependencies, for `SharedResourcePointer` |
| `DemoGate` | Header-only audio-thread dropouts |
| `LicenseBridge` | The editor's native functions and the status payload |

`evaluate` applies the seat limit only when `activating`: a refused extra machine still raises `uses`, and
without the exemption every legitimate machine's re-check would start failing.

## LicenseManager Rules

- **Start:** read the file. Ignore it if its `deviceId` differs from `juce::SystemStats::getUniqueDeviceID()`
  (another machine). Licensed if `now - lastChecked <= grace`. A `lastChecked` in the future (clock set back):
  rewrite it as "just over the re-check interval ago", so a re-check is due and offline use stays bounded. If the
  device id is empty, substitute a fixed placeholder, or every session writes a file it cannot read back.
- **`checkIfDue()`** (start-up in production, and every editor open): re-read the file first, adopting a newer
  license for this device written by another host process, then start a background re-check if due and idle.
- **`activateNow (key)`** (blocking; worker thread): trim and upper-case; empty → "Enter your license key."
  without a network call; re-read the file; if this machine already holds that key, verify with
  `countUse=false` and no seat limit; otherwise `countUse=true`. On success write the file; if the write fails,
  stay licensed for this process and keep a warning in the status naming the folder and the seat cost.
- **`recheckNow()`** (`countUse=false`): licensed → refresh `lastChecked` and the file; unlicensed → remove the
  file, clear the flag, keep Gumroad's message for the dialog; retryLater → change nothing.
- **Status:** `licensed` wins over `checking`, or a background re-check shows "Demo" to a paying customer and can
  trigger the activation prompt. Offer "works offline until" only when the last success is over the re-check age.
- **Threads:** one `juce::Thread` with an atomic `busy`; a second request while busy answers at once with the
  current status (a JS promise must always resolve). Async results go back with `MessageManager::callAsync`
  through a `juce::WeakReference` created on the message thread. The destructor calls `verifier->cancel()`, then
  `stopThread`, so closing the host never waits on the network. `sendChangeMessage()` is safe from the worker.
- **Shared across instances:** `juce::SharedResourcePointer<ProductionLicenseManager>` as a processor member;
  activating in one editor unlocks every instance in that process. Hosts that run plug-ins in separate processes
  pick it up at the next `checkIfDue()`.
- **File:** `userApplicationDataDirectory/<Company>/<Product>/license.json` (on macOS `~/Library/<Company>/…`),
  fields `key`, `email`, `deviceId`, `lastChecked` (UTC ms). Write under a `juce::InterProcessLock` with
  `File::replaceWithText`, which writes a temporary file and replaces the target with it (JUCE 9.0.3:
  `TemporaryFile::overwriteTargetFileWithTemporary` → `File::replaceFileIn`, which is `rename()` on POSIX and
  `ReplaceFile` on Windows). `File::moveFileTo` deletes the target first, so it is not an atomic replace. Never store the license in plugin
  state: it would travel inside project files.

*Case study: a whole-branch review of the first implementation found the "Demo during re-check" status order, the
second-process re-activation and the clock-set-back gap; each fix shipped with a test that failed first.*

## HTTPS From JUCE

| Platform | Backend | Needs |
| --- | --- | --- |
| macOS | NSURLSession | Nothing |
| Windows | WinINet | Nothing |
| Linux | libcurl via `juce_Network_curl.cpp`; plain sockets otherwise (no TLS) | `JUCE_USE_CURL=1`, `JUCE_LOAD_CURL_SYMBOLS_LAZILY=1`; build needs `libcurl4-openssl-dev` (headers); run time `dlopen`s `libcurl.so` / `.so.4` / `.so.3` / `-gnutls` variants |

Lazy loading keeps libcurl out of the plugin's link list, but if no libcurl can be opened, the `WebInputStream`
constructor calls through a null symbol table in Release builds: in JUCE 9.0.3, `WebInputStream::Pimpl` in
`juce_Network_curl.cpp` guards `symbols` with a debug-only `jassert`, then calls `symbols->curl_multi_init()`.
Pressing Activate crashes the host. Re-check this against the JUCE version in use. Probe first with `juce::DynamicLibrary` on the same names and a
`curl_multi_init` symbol, and return a "needs libcurl 4 (libcurl.so.4)" result instead. See
[platform builds](platform-builds.md#linux) for the CI packages.

The request:

```cpp
const auto url = juce::URL (kVerifyUrl).withParameter ("product_id", kProductId)
                                       .withParameter ("license_key", key)
                                       .withParameter ("increment_uses_count", countUse ? "true" : "false");
auto stream = std::make_unique<juce::WebInputStream> (url, true);   // parameters in the body: POST
stream->withConnectionTimeout (15000);
// Keep the pointer under a lock so cancel() from another thread can call stream->cancel().
const bool connected = stream->connect (nullptr);   // a 404 is still a connection
Reply reply = connected ? Reply { stream->getStatusCode(), stream->readEntireStreamAsString() } : Reply {};
```

Never on the audio thread, never in the processor constructor, never synchronously on the message thread (hosts
scan plug-ins with timeouts).

## Demo Mode In The Audio Path

- `DemoGate::process (channels, numChannels, numSamples, active)`: unity for a random 45-60 s, linear 10 ms fade
  down, 2 s of zeros, 10 ms fade up, repeat (case-study timings). Integer fade counters give exact 0 and 1. While
  inactive at unity, return without touching the buffer (bit-exact). Going inactive mid-dropout fades up and stays.
- Realtime-safe by construction: the gate allocates nothing, takes no lock, adds no latency and makes no system
  call; its state is a few integers and a `juce::Random` seeded in `prepare`. The license flag is a
  `std::atomic<bool>` written by the manager's threads and only loaded on the audio thread.
- `active = ! manager->isLicensed() && ! bypassed`, evaluated once per block after the DSP; a bypassed instance
  passes dry audio. One relaxed atomic load per block; one multiply per sample only while active.
- `prepare (sampleRate, seed)` resets the countdown only when the rate changes: many hosts call `prepareToPlay`
  at every transport start, and a reset there means a stop-start session never hears a dropout.
- Compile the gate and the manager only into the shipped plug-in target (for example
  `YOURPLUGIN_LICENSE_GATE=1` on that target, defaulting to 0 in the header). Test, perf and editor-host targets
  then have no manager, make no network call, and their golden references and CPU figures do not change.

Realtime rules in general: [audio-thread safety](audio-thread-safety.md).

## WebView Activation UI

Built on [native functions and events](webview-ui.md#native-functions-and-events):

| Native function | Returns |
| --- | --- |
| `getLicenseStatus()` | `{ state: "demo" \| "checking" \| "licensed", email, keyTail, message, lastChecked, offlineUntil }` (times in ms, 0 when absent) |
| `activateLicense (key)` | The same object when the background call finishes |
| `claimLicensePrompt()` | `true` once per manager lifetime: the "open by itself once per session" switch |
| `openLicenseLink ("buy" \| "lookup")` | Nothing; opens one of two fixed URLs with `URL::launchInDefaultBrowser`. Never let the page pass a URL |

- The editor listens to the manager (`ChangeListener`) and sends `licenseStatus` through
  `emitEventIfBrowserIsVisible`; the page re-reads the status on `visibilitychange`.
- Complete an `activateLicense` promise only while the editor exists: guard the callback with a
  `juce::Component::SafePointer` (JUCE's completion captures the browser). Without a manager (test builds),
  report `licensed` with "Test build" and never claim the prompt.
- The page makes no network requests, so the production CSP does not change.
- Markup: a key-icon button in the header ("Demo" until licensed, icon only after) and a native `<dialog>` with
  three states. Demo: one line explaining the dropouts, key field, error line, Activate, Cancel, Buy, Find my key.
  Checking: all controls disabled. Licensed: licensed-to, key tail, last check, offline-until, Close. Use plain
  `type="button"` buttons and handle Enter in the key field; inside a `<form>`, implicit submission picks the
  first button (often Cancel).
- Keep a browser mock behind the same API (for example keys starting `TEST` activate, `DISABLED` and `OFFLINE`
  return the matching messages), so the dialog is built and checked without a host.
- Check the header at the smallest editor size: the button must not clip the brand or the next control.

## Tests And Validation

| Test | What it pins |
| --- | --- |
| `LicenseRules` table | Every reply in [The Verify Endpoint](#the-verify-endpoint), including a non-JSON 404 and a malformed 200 |
| `LicenseFile` | Round trip through a second instance, malformed and missing fields, an unwritable folder |
| `LicenseManager` with a fake `Verifier`, temp folder, injected clock and device id | Activation, key normalisation, empty key makes no call, seat limit, 29 vs 31 days, other device, due rule, revoke, offline keep, save failure, adopting another process's file, re-entering the held key costs no seat, licensed during a re-check, clock set back |
| Blocking fake `Verifier` | A second activate while busy makes no call; the destructor returns within 2 s with a call stalled |
| `DemoGate` | First dropout in 45-60 s, 2 s of zeros, 480-sample ramps at 48 kHz, bit-exact when inactive, ramp up on deactivate, same-rate `prepare` keeps the countdown |
| Bridge | The four functions are registered; the test-build status |
| Manual smoke mode (not a ctest entry) | One live verify with a fake key returns Gumroad's 404 |
| pluginval / auval | Run on the gated plug-in: the unlicensed path must load, process and close |

Tests built without the gate cannot see the dialog's demo and checking states inside the plug-in; cover them
with the browser mock and the manual release check: a real purchase, activation, offline restart and a refund
revoke in each target host and platform. Host validation in general:
[production practices](production-plugin-practices.md#host-validation-and-release-gates).

## Ways Activations Get Burned

Every path that calls activate with `countUse=true` spends a Gumroad use the plugin cannot give back:

- Re-checks without the literal `increment_uses_count=false`.
- A missing, corrupt or unsaveable license file, or an empty device id that makes the file unreadable.
- Activating again in a second host process instead of adopting its file, or re-entering the key this machine
  already holds.
- A refused extra machine (its attempt still counts).
- Rotating a key without first resetting its uses.
- A device id that changes: on Linux JUCE hashes BIOS fields and `lscpu` output, so a BIOS update or locale change
  asks for the key again.
- A reply lost after Gumroad counted the use (timeout, cancellation at shutdown).

Name the seat cost in the UI where it applies, and give support a short dashboard procedure for resetting uses.

## Upgrade Path: A Signing Server

Plugin → your endpoint with key and device id → server calls `verify` (`increment_uses_count=false`), keeps its own
activation table (deactivate frees a seat), subscribes to Gumroad's Ping (`refund`, `dispute`, `cancellation`…,
form-encoded, signed with `X-Gumroad-Signature: t=…,v1=<HMAC-SHA256 of "t.rawBody">`, retried on 499/500/502/503/504,
5 s to answer) and returns a key file signed with your private key. The plug-in verifies offline with an embedded
public key, through `OnlineUnlockStatus::applyKeyFile` or a small Ed25519 verifier. Only the `Verifier`
implementation and the file format change.

## Common Mistakes

- Sending `product_permalink` for a new product, or leaving `increment_uses_count` at its default on re-checks.
- Treating every 404 as revoked, or every 200 as licensed (chargebacks stay 200).
- Calling the network from the processor constructor or the message thread.
- Shipping a seller `access_token` to free seats.
- Building the Linux plug-in with `JUCE_USE_CURL=0` (no HTTPS at all) or with lazy loading and no libcurl probe
  (host crash).
- Showing "Demo" while a licensed customer's background re-check runs.
- Resetting the demo countdown in every `prepareToPlay`.
- Letting test targets construct the real manager (network calls and dropouts in golden tests).
- Testing with the editor's sample key and concluding activation is broken.
- Storing the license in plugin state.

## Sources

- Gumroad API, Licenses: <https://gumroad.com/api#licenses>; Help Center, "License keys" (article 76); Ping:
  <https://gumroad.com/ping>; source: <https://github.com/antiwork/gumroad>
- JUCE 9.0.3: `juce_core/network/juce_WebInputStream.h`, `juce_core/native/juce_Network_curl.cpp`,
  `juce_core/juce_core.h` (`JUCE_USE_CURL`, `JUCE_LOAD_CURL_SYMBOLS_LAZILY`), `juce_core/files/juce_File.cpp`
  (`replaceWithText`, `moveFileTo`), `juce_core/memory/juce_SharedResourcePointer.h`,
  `juce_product_unlocking/marketplace/juce_OnlineUnlockStatus.h`
