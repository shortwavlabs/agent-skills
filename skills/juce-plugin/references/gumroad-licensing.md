# Gumroad Licensing (License Keys In A JUCE Plugin)

A runbook for selling a JUCE plugin on Gumroad with per-sale license keys: product set-up (including the Gumroad
MCP server), an entitlement decision table built from Gumroad's verify replies, activation accounting, a
cross-process license-file protocol, network cancellation and shutdown, demo-mode dropouts and the WebView
activation UI. The base pattern is "the plugin calls Gumroad's verify endpoint itself"; a signing server is the
upgrade path, with criteria for choosing it.

Evidence labels used below:

- **Vendor facts** cite their source: Gumroad's API and help pages, or its public code at commit
  `antiwork/gumroad@f1a9c5b` (production on 2026-11-08); JUCE 9.0.3 file names. Vendor behaviour changes: re-check
  before relying on it.
- **Specified** marks a rule this runbook defines that no implementation has shipped yet.
- *Italic case-study notes* describe one pedal plugin. They show how a decision was reached, not defaults.

## Contents

- [Quick Reference](#quick-reference)
- [Choose The Architecture](#choose-the-architecture)
- [Gumroad Product Set-Up](#gumroad-product-set-up)
- [Gumroad MCP Server](#gumroad-mcp-server)
- [The Verify Request](#the-verify-request)
- [Entitlement Decision Table](#entitlement-decision-table)
- [Activation Accounting](#activation-accounting)
- [Reading Gumroad's Source](#reading-gumroads-source)
- [Units](#units)
- [License File Protocol](#license-file-protocol)
- [Network Requests, Cancellation And Shutdown](#network-requests-cancellation-and-shutdown)
- [Linux HTTPS](#linux-https)
- [Demo Mode In The Audio Path](#demo-mode-in-the-audio-path)
- [WebView Activation UI](#webview-activation-ui)
- [Tests And Evidence](#tests-and-evidence)
- [Support And Recovery](#support-and-recovery)
- [Upgrade Path: A Signing Server](#upgrade-path-a-signing-server)
- [Common Mistakes](#common-mistakes)
- [Sources](#sources)

## Quick Reference

| Decision | Pattern (bracketed figures are the case study's choices, not defaults) |
| --- | --- |
| Who calls Gumroad | The plugin, `POST https://api.gumroad.com/v2/licenses/verify`; no server of your own |
| Product identifier | `product_id` from the License key block |
| Entitlement | The [decision table](#entitlement-decision-table): `success: true` alone never licenses |
| Seats | A use allowance per key, checked with a non-incrementing preflight [3] |
| Re-check | Background, non-incrementing, when the last success is older than an interval [7 days] |
| Offline grace | Licensed for a fixed period after the last success [30 days], never past a known membership end |
| State | One `LicenseManager` per host process (`juce::SharedResourcePointer`), one worker thread, an atomic flag for the audio thread |
| Storage | `license.json` next to the presets, changed only under an inter-process lock with a revision check |
| Unlicensed | Demo dropouts while the effect is engaged [2 s of silence every 45-60 s, 10 ms fades] |
| Linux HTTPS | `JUCE_USE_CURL=1` + `JUCE_LOAD_CURL_SYMBOLS_LAZILY=1`, and a probe that mirrors JUCE's libcurl loading |
| Shutdown | Cancel, then wait for the worker; never force-kill it |
| UI | Header button + dialog in the WebView; four native functions and one status event; the page never touches the network |

## Choose The Architecture

| | A: plugin verifies directly | B: plugin talks to your server |
| --- | --- | --- |
| Infrastructure | None | A service for the product's lifetime |
| Offline check | Unsigned local state: forgeable, the check can be patched out | Signed license with an expiry, verified offline with an embedded public key |
| Seats | Gumroad's `uses` counter only (see [Activation Accounting](#activation-accounting)) | A device registry with self-service deactivation |
| Refunds, chargebacks, ended memberships | Seen at the next re-check | Webhook plus reconciliation, pushed at the next refresh |
| Fit | Small catalogue, low price, honest-customer protection | Any of the criteria below |

Choose B when any of these matters: customers moving machines without contacting support; seat limits that must
count devices rather than requests; prompt revocation after refunds, chargebacks or membership ends; licenses
that must not be forgeable offline; or support time spent resetting `uses` becomes a measurable cost.

JUCE's `juce_product_unlocking` (`OnlineUnlockStatus`) is not a drop-in for A: it expects a key file signed by
*your* server. It can serve B.

## Gumroad Product Set-Up

1. Create the product by hand or with the [MCP server](#gumroad-mcp-server). In the copy, describe what the
   plugin models without other companies' trademarks.
2. On the product's **Content** page: **Insert → License key**. Leave multi-seat off unless selling site licenses
   (then `is_multiseat_license` is true and `quantity` is the seat count).
3. Copy the `product_id` the block shows. It is not secret; compile it in. *Case study: it equalled the `id` the
   API and the MCP server returned for the product.*
4. The key the editor shows ("License key (sample)") is a fixed placeholder (`ProductEdit/ContentTab/index.tsx`
   at `f1a9c5b`); verify answers it with the not-found 404. It tests the error path only.
5. A draft is not for sale to anyone, the seller included. A real test key needs a purchase: publish briefly
   with a 100 %-off, single-use, expiring discount code, buy, unpublish. A purchase by the seller's signed-in
   account carries `test: true`.

## Gumroad MCP Server

Tool names as exposed by the connected Gumroad server on 2026-11-08; list the server's tools before relying on them.

| Task | Tool | Notes |
| --- | --- | --- |
| Account | `get_account` | Name, username, storefront URL, currency |
| Products | `list_products`, `get_product`, `search_products`, `list_categories` | `get_product` returns the product id |
| Create | `create_draft_product` | Name, `price_cents`, currency, description; stays a draft. Confirm name and price with the creator |
| Edit | `update_product` | Category, tags, summary, receipt text, permalink |
| Media, deliverables | `add_cover`, `add_file`, `list_files`, `add_content_link` | Files up to 250 MB from a public URL |
| Test purchase code | `create_discount_code`, `update_discount_code`, `expire_discount_code` | `percent_off`, `product_id`, `max_purchase_count`, `expires_at` |
| On/off sale | `publish_product`, `unpublish_product` | Confirm with the creator before either |
| After launch | `list_sales`, `get_customers`, `get_subscriptions`, `get_sales_totals`, `get_analytics`, `list_payouts` | Read-only |

It cannot insert the License key block (Content tab), read or reset a key's `uses` (dashboard), or buy anything.

## The Verify Request

`POST https://api.gumroad.com/v2/licenses/verify`, form-encoded, no API token, CORS `*` (API page; observed).

| Parameter | Value |
| --- | --- |
| `product_id` | From the License key block. Without it, products created after Gumroad's cutoff (help article: 2023-01-09) get **500** with a message naming `product_id` |
| `license_key` | Trimmed and upper-cased (keys are an upper-case UUID regrouped as four 8-hex groups, `license.rb`) |
| `increment_uses_count` | Counts a use unless the value is exactly `false` (`clean_params` in `licenses_controller.rb`): `"0"` or `"no"` count |

Rate limits: no Rack::Attack rule matches this route at `f1a9c5b` (only malformed-parameter throttling); an edge
limit, if any, is not in the repository. Treat 429 as retry and honour `Retry-After`.

Seller endpoints (`enable`, `disable`, `decrement_uses_count`, `rotate`) need an OAuth `access_token` that acts on
the whole store: never ship it. In A the plugin therefore cannot free or decrement a use.

## Entitlement Decision Table

`LicenseRules::evaluate` maps one reply to one verdict. Inputs: HTTP status (0 = no answer), body, `now`, and
whether the call was the incrementing activation. Verdicts: **licensed** (with an optional `entitledUntil`),
**unlicensed** (with a reason; deletes nothing by itself, see the file protocol), **retry** (keep the current
state; grace still applies), **unsupported** (deterministic, never retried). Evaluate the rows top to bottom; the
first match wins (so `imported_customer` is classified before the malformed-reply row, and a refund or dispute
before a membership's dates). Source: `licenses_controller.rb`,
`go_web/internal/licenses/purchase_json.go`, `refundable.rb`, `subscription.rb` at `f1a9c5b`.

| Reply | Verdict |
| --- | --- |
| No answer: connection failure, timeout, cancellation | retry. After an incrementing call: **uncertain** ([Activation Accounting](#activation-accounting)) |
| 429, 5xx, 3xx, 400, any status other than 200/404 | retry. A 400 or a 500 naming `product_id` is an integration bug: log it |
| Body not a JSON object, or no boolean `success` | retry |
| 404, JSON `success: false`, `"That license does not exist for the provided product."` | unlicensed: unknown key, another product's key, or a rotated key |
| 404, `"This license key has been disabled."` | unlicensed: disabled by the seller, **or fully refunded** (Gumroad disables the key after a full refund) |
| 404, `"Access to the purchase associated with this license has expired."` | unlicensed: the seller revoked access to the purchase |
| 404, JSON, any other message | Activation: refuse and show the message. Re-check: retry, so a reworded message cannot revoke every customer at once; grace still bounds it |
| 404 that is not JSON | retry (a proxy page or a moved endpoint is not Gumroad's verdict) |
| 200 `success: true` with `imported_customer` and no `purchase` | unsupported, unless the seller imports customers for this product: then licensed with no refund or dispute data to check. Default: show "This license needs manual activation. Contact <support>." |
| 200 `success: true` without `purchase`, or `uses` not a number | retry (malformed) |
| One-time purchase (`purchase` has `chargebacked`, no `subscription_*`): `refunded` | unlicensed (normally already the disabled 404) |
| One-time: `chargebacked`, or `disputed && !dispute_won` | unlicensed. A chargeback does **not** disable the key |
| One-time: partial refund | licensed. The reply does not expose partial refunds (`refunded` is false, the key stays enabled) |
| One-time: otherwise | licensed |
| Membership (`purchase` has `subscription_ended_at`, `_cancelled_at`, `_failed_at`): `refunded`, or `disputed && !dispute_won` | unlicensed |
| Membership: `subscription_failed_at` set | unlicensed: renewal failed and access was deactivated then |
| Membership: `subscription_ended_at` set | unlicensed: a fixed-length membership ended |
| Membership: `subscription_cancelled_at` in the future | licensed with `entitledUntil = subscription_cancelled_at`: a cancellation keeps the paid period (`Subscription#cancel!` stores the period's end; `alive?` counts a future value as alive) |
| Membership: `subscription_cancelled_at` now or past | unlicensed (a chargeback or product deletion cancels a membership at once) |
| Membership: all three null | licensed |
| Activation only: licensed but `uses` above the allowance | unlicensed with the limit message (that call already counted; see the preflight) |

Gumroad keeps a membership's key enabled after it ends: the timestamps are the only signal, and a restarted
membership clears them. `test: true` appears only for a seller self-purchase and is otherwise absent, never
`false`. Compare `entitledUntil` with the local clock; A cannot defend against a changed clock anyway, so store
`entitledUntil` and cap offline grace at it. An end the plugin has not seen yet (a failed renewal while offline)
is bounded only by the grace period.

## Activation Accounting

Four different things, often conflated:

| Concept | Where it lives | Authoritative for |
| --- | --- | --- |
| Verification count | Gumroad's `uses`, raised by each verify sent with `increment_uses_count` other than `false` | Nothing per device: it counts requests |
| Local machine authorization | This machine's `license.json` | Whether this plugin plays without dropouts |
| Activation allowance | The seller's policy (for example 3), compared with `uses` | What the plugin refuses; support can reset `uses` in the dashboard |
| Registered devices | Only a server of your own (architecture B) | Self-service deactivation, exact seat counts |

In A, the count is not exactly-once:

- An incrementing call consumes a use even when the plugin then refuses the activation (over the allowance).
- A timeout or lost reply leaves the outcome unknown: the use may or may not be counted, and retrying an
  incrementing request is not idempotent.
- A lost, corrupt or unsaveable `license.json`, or a device id that changes, makes the machine activate again.
- Concurrent activations of one key on several machines can pass the preflight together and exceed the allowance.
- A crash after a counting request was sent, or a request that times out, leaves the count unknowable.

**Specified** activation sequence, which spends at most one use per machine and key, including across host
processes on that machine:

1. Normalise the key. If this machine's file already holds it, verify without incrementing (a re-check).
2. Preflight: verify with `increment_uses_count=false`. A definitive "unlicensed" or "unsupported" refuses
   without spending a use; "retry" shows the network message; licensed with `uses >= allowance` refuses with the
   limit message, also without spending.
3. **Claim** the key (below). Only the claimant continues.
4. The claimant sends exactly one incrementing verify, never retried with increment, then **finishes** (below).
   Licensed: write the license. Definitive unlicensed: show the reason. No answer: the outcome is **uncertain**
   and the marker stays.

Check-and-claim, all inside the one `juce::InterProcessLock` of the [file protocol](#license-file-protocol),
held for the file work only:

- Markers are per key: one small file per key (named from a hash of the normalised key) holding `key`, `claimId`
  (a fresh random id) and `startedAt`. Activations of different keys never share or overwrite a marker.
- **Claim.** Under the lock, re-read `license.json` and this key's marker, then:
  - the license already holds this key for this device: no claim; re-check without incrementing;
  - a marker exists and is younger than the request deadline plus a margin (for example twice the deadline):
    another process is activating this key. No claim and no request; report `pending` and pick the outcome up
    from the file;
  - a marker exists and is older, or its `startedAt` is in the future: its claimant crashed or timed out. No
    claim; **resolve** it (below);
  - no marker: write one with a new `claimId`, remember that id, release the lock. This process is the claimant.
- **Finish** (claimant). Under the lock, re-read the marker. Delete it only if it still carries this
  process's `claimId`; on "no answer" keep it. Write the license on "licensed" (an activation writes
  unconditionally, as in the file protocol). A refusal never deletes `license.json`.
- **Resolve** an old marker. Snapshot its `claimId`, verify without incrementing, then under the lock: if the
  marker still carries that `claimId`, apply a definitive verdict (licensed: write the license and delete the
  marker; unlicensed: delete the marker) and keep it on "no answer". If the `claimId` changed or the marker is
  gone, discard the result and adopt what is on disk. A stale worker therefore never clears a newer marker.
- **Different keys at once:** each claimant may spend one use of its own key. `license.json` ends with the last
  successful activation; the replaced key's use on this machine is spent without being kept. The UI asks before
  replacing a license.
- **Crash recovery:** a crash after the claim leaves an old marker, which is only ever resolved without
  incrementing. If the crash came before the request left, the machine ends up authorized without a counted use;
  if after, the count is right. Which one happened cannot be known: an accepted under-count.

Customer-facing while uncertain: stay in demo mode and show "Couldn't confirm the activation with Gumroad. It
will retry automatically and won't use another activation." Retry when the editor opens and on "Try again". The
count may read one high afterwards; only support can correct it.

## Reading Gumroad's Source

Gumroad's code is public (`antiwork/gumroad`). Responses observed in 2026-11 carried an `x-revision` header naming
the deployed commit; it is undocumented and may disappear. When present, read the code at that commit:

```bash
curl -s -D - -o /dev/null -X POST https://api.gumroad.com/v2/licenses/verify -d product_id=x -d license_key=y | grep -i x-revision
gh api -H 'Accept: application/vnd.github.raw' "repos/antiwork/gumroad/contents/app/controllers/api/v2/licenses_controller.rb?ref=<sha>"
```

Useful files: `app/controllers/api/v2/licenses_controller.rb` and `go_web/internal/licenses/` (replies, fields),
`app/models/subscription.rb` (membership timestamps), `app/modules/purchase/refundable.rb` (refunds),
`app/models/imported_customer.rb`, `config/initializers/rack_attack.rb`, `app/sidekiq/post_to_individual_ping_endpoint_worker.rb`
(Ping delivery). A fake key with `increment_uses_count=false` is a safe live probe of error shapes.

## Units

All in one folder (for example `Source/licensing/`), one namespace:

| Unit | Responsibility |
| --- | --- |
| `LicenseConfig.h` | Product id, URLs, allowance, timeouts, intervals, every customer-facing string |
| `LicenseRules` | Pure: `Evaluation evaluate (int status, const String& body, juce::Time now, bool activating)` implementing the decision table |
| `Verifier` | `Reply verify (const String& key, bool countUse)`, `void abortCurrent()`, `void shutdown()`, with `struct Reply { int status = 0; String body; }` (0 = no answer; `kStatusNoHttps = -1` from the Linux probe): the seam for fakes and for B |
| `GumroadVerifier` | The real request ([below](#network-requests-cancellation-and-shutdown)) with an injectable HTTPS probe |
| `LicenseFile` | Locked, revision-checked reads, writes and deletes of `license.json`; per-key pending markers with claim-checked create and delete |
| `LicenseManager` | Shared state, one worker thread, the atomic flag, `AsyncUpdater`-based results; built from `Deps { verifier, folder, now(), deviceId }` |
| `ProductionLicenseManager` | Default-constructible subclass with the real dependencies, for `SharedResourcePointer` |
| `DemoGate` | Header-only audio-thread dropouts |
| `LicenseBridge` | The editor's native functions and status payload |

## License File Protocol

`userApplicationDataDirectory/<Company>/<Product>/license.json` (macOS `~/Library/<Company>/…`): `key`, `email`,
`deviceId`, `lastChecked` (UTC ms), optional `entitledUntil`, and `revision`, a fresh random id written with
every change. Never store the license in plugin state: it would travel inside project files.

**Specified** rules (the case study's second version implements 1-7 except `entitledUntil`; its first compared
nothing before writing or deleting):

1. **One lock for every change.** Each write, delete and pending-marker change happens inside one
   `juce::InterProcessLock` named for the product, held only for the file read-compare-write: never across a
   network call, never on the audio thread.
2. **Atomic replacement.** Write with `File::replaceWithText`: a temporary file then `replaceFileIn`, which is
   `rename()` on POSIX and `ReplaceFile` on Windows in JUCE 9.0.3. This prevents torn reads; it does not prevent
   lost updates or stale deletes, which is what rules 3-5 are for. `File::moveFileTo` deletes the target first.
3. **Every job carries the identity it checked.** A re-check snapshots `(key, revision)` when it starts.
4. **Apply a result only if that identity is still on disk.** Under the lock, re-read the file. Same key and
   revision: apply (refresh `lastChecked` with a new revision, or delete on a revocation). Anything else (another
   key, a newer revision, no file): discard the result and adopt what is on disk. A user-initiated activation
   writes unconditionally, with a new revision, after its own successful verify.
5. **Adopt, then report.** After any discard, set the in-memory state from the file just read: licensed or not,
   `entitledUntil`, cleared stale messages. Then notify editors. A process never deletes a license it did not
   just verify as revoked.
6. **Pick up other processes' changes** when an editor opens, before every job, and optionally on a slow timer.
   Reads need no lock (replacement is atomic); compare-and-change does.
7. **Start-up:** ignore a file whose `deviceId` differs. Licensed if `now - lastChecked <= grace` and
   `now < entitledUntil` when set. A `lastChecked` in the future (clock set back) is rewritten as "just over the
   re-check interval ago", so a check is due and offline use stays bounded. An empty device id is replaced by a
   fixed placeholder, or the machine writes files it cannot read back.

Device ids (`SystemStats::getUniqueDeviceID`, JUCE 9.0.3): macOS `IOPlatformUUID`, empty if unavailable;
Windows, derived from SMBIOS data; Linux, `board_serial` (usually readable by root only) or else BIOS date,
release, vendor and version plus `lscpu` fields, so a BIOS update or different `lscpu` output changes it. The Linux
path spawns child processes once: call it off the audio thread.

## Network Requests, Cancellation And Shutdown

Background work runs on the manager's worker thread only; the audio thread reads one atomic and nothing else.

What `WebInputStream::withConnectionTimeout` bounds in JUCE 9.0.3:

| Backend | Timeout maps to | `cancel()` |
| --- | --- | --- |
| macOS, NSURLSession (`juce_Network_mac.mm`) | The request's `timeoutInterval`: inactivity, not total time | `[task cancel]` |
| Windows, WinINet (`juce_Network_windows.cpp`) | Connect, send and receive timeouts, per operation (0 means 30 s) | `InternetCloseHandle` under the stream's lock |
| Linux, libcurl (`juce_Network_curl.cpp`) | `CURLOPT_CONNECTTIMEOUT`, plus a low-speed abort (under 100 B/s for the same seconds) | Cleanup under the stream's lock, which a `select` step holds for up to about a second |

None bounds the total request time. Enforce a deadline (for example 30 s) with a `juce::Timer` the manager runs on
the message thread: when it passes, the timer calls `verifier.abortCurrent()` and the request counts as "no answer".

Cancellation that cannot deadlock or touch a destroyed stream:

```cpp
// Members: juce::CriticalSection lock; std::shared_ptr<juce::WebInputStream> current;
//          std::atomic<bool> closing { false }, aborted { false };
Reply GumroadVerifier::verify (const juce::String& key, bool countUse)
{
    if (closing) return {};
    if (! hasHttps()) return { kStatusNoHttps, {} };            // see Linux HTTPS for the probe
    auto stream = std::make_shared<juce::WebInputStream> (makeUrl (key, countUse), true);   // POST
    stream->withConnectionTimeout (kConnectTimeoutMs);
    { const juce::ScopedLock sl (lock); aborted = false; current = stream; }
    if (closing) stream->cancel();                             // shutdown raced the start
    Reply reply;
    if (stream->connect (nullptr))                             // a 404 is still a connection
        reply = { stream->getStatusCode(), stream->readEntireStreamAsString() };
    { const juce::ScopedLock sl (lock); current.reset(); }
    // Aborted after the headers arrived still means "no answer": the body may be truncated, and
    // isError() is backend-specific in JUCE 9.0.3 (macOS keeps it false once headers exist).
    return (aborted || closing) ? Reply {} : reply;
}

void GumroadVerifier::abortCurrent()
{
    std::shared_ptr<juce::WebInputStream> s;
    { const juce::ScopedLock sl (lock); aborted = true; s = current; }   // copy under the lock...
    if (s != nullptr) s->cancel();                             // ...cancel outside it; the copy keeps the stream alive
}

void GumroadVerifier::shutdown() { closing = true; abortCurrent(); }
```

Shutdown contract:

- `~LicenseManager` calls `verifier->shutdown()`, then waits for the worker without a timeout
  (`waitForThreadToExit (-1)`). Do not use `stopThread (timeout)` routinely: in JUCE 9.0.3 a missed timeout calls
  `killThread()`, which the source itself warns leaves locks and events in broken states, and the killed thread
  may hold JUCE's, libcurl's or WinINet's locks.
- What this guarantees: shutdown waits as long as the backend takes to return after `cancel()`. JUCE's backends
  normally abort promptly; one that ignores cancellation returns at its own timeout (inactivity on macOS,
  per-operation on Windows, connect or low-speed on Linux), so keep the connect timeout short (for example
  10-15 s). That is not a hard bound. A plugin cannot leave a thread running into an unloaded binary, so waiting
  is still the safe choice.
- Deliver results to the message thread through an `AsyncUpdater` (or `ChangeBroadcaster`) the manager owns:
  its destructor cancels a pending callback, so no result arrives after the manager is gone. Each result carries
  its job's identity and is dropped if a newer job started. Editor-side completions are guarded by a
  `juce::Component::SafePointer` (JUCE's completion captures the browser).
- Never start requests from the processor constructor, `prepareToPlay` or synchronously on the message thread.

## Linux HTTPS

| | Detail (JUCE 9.0.3) |
| --- | --- |
| Configuration | `JUCE_USE_CURL=1` (without it Linux has no HTTPS); `JUCE_LOAD_CURL_SYMBOLS_LAZILY=1` to `dlopen` libcurl instead of linking it |
| Build time | `libcurl4-openssl-dev` for `<curl/curl.h>` (see [platform builds](platform-builds.md#linux)) |
| Run time | The first of `libcurl.so`, `libcurl.so.4`, `libcurl.so.3`, `libcurl-gnutls.so.4`, `libcurl-gnutls.so.3` that opens, with 15 symbols (`curl_easy_init`, `_setopt`, `_cleanup`, `_getinfo`, `curl_multi_add_handle`, `_cleanup`, `_fdset`, `_info_read`, `_init`, `_perform`, `_remove_handle`, `_timeout`, `curl_slist_append`, `_free_all`, `curl_version_info`) |
| Failure | Each `WebInputStream` creates its symbol table; if the library or a symbol is missing it is null. Debug builds stop at a `jassert`; Release builds call `symbols->curl_multi_init()` through null and crash the host |

The probe must mirror that loader: try the names in that order, stop at the **first that opens**, and require all
15 symbols from that same handle (JUCE does not fall back to the next name). Probe before each request or cache
the answer per process, and return "needs libcurl 4" instead of building the stream. The probe prevents only
this crash: missing CA certificates, proxies or a libcurl without TLS still fail, as "no answer".

## Demo Mode In The Audio Path

- `DemoGate::process (channels, numChannels, numSamples, active)`: unity for a random interval, a linear fade
  down, silence, a fade up, repeat [45-60 s, 10 ms, 2 s, 10 ms]. Integer fade counters give exact 0 and 1.
  Inactive at unity, return without touching the buffer (bit-exact); deactivating mid-dropout fades up.
- No heap members, no locks, no system calls, no latency: a few integers and a `juce::Random` seeded in `prepare`.
- `active = ! manager->isLicensed() && ! bypassed`, one relaxed atomic load per block, after the DSP.
- `prepare` resets the countdown only when the sample rate changes: hosts call `prepareToPlay` at every
  transport start.
- Compile the licensing into the shipped plugin target (for example `YOURPLUGIN_LICENSE_GATE=1`, defaulting to 0
  in the header). Golden-reference, perf and editor-host targets build without it, so their outputs and CPU
  figures are unaffected. Test the gate-on configuration separately ([Tests](#tests-and-evidence)).

## WebView Activation UI

Built on [native functions and events](webview-ui.md#native-functions-and-events):

| Native function | Returns |
| --- | --- |
| `getLicenseStatus()` | `{ state: "demo" \| "checking" \| "pending" \| "licensed", email, keyTail, message, lastChecked, offlineUntil, entitledUntil }` (ms, 0 when absent) |
| `activateLicense (key)` | The same object when the job finishes |
| `claimLicensePrompt()` | `true` once per manager lifetime: the "open by itself once per session" switch |
| `openLicenseLink ("buy" \| "lookup")` | Opens one of two fixed URLs with `URL::launchInDefaultBrowser`; the page never passes a URL |

- State precedence: `licensed` wins over `checking`, or a background re-check shows "Demo" to a paying customer.
  `pending` is an uncertain activation, or one another process is running ([Activation Accounting](#activation-accounting)). Activating a
  different key on a licensed machine replaces the license: ask before sending it.
- The editor listens to the manager and sends `licenseStatus` via `emitEventIfBrowserIsVisible`; the page re-reads
  on `visibilitychange`. Without a manager (builds without the gate) it reports `licensed`, "Test build".
- The page makes no network requests; the CSP does not change.
- Header key button ("Demo" until licensed) and a native `<dialog>`: key field, error line, Activate, Cancel,
  Buy, Find my key; licensed-to, key tail, last check, offline-until or membership end. Plain `type="button"`
  buttons and Enter in the key field: inside a `<form>`, implicit submission picks the first button.
- A browser mock behind the same API (keys `TEST…`, `DISABLED`, `OFFLINE`, `PENDING`) builds the dialog without a
  host. Check the header at the smallest editor size.

## Tests And Evidence

| | Scope |
| --- | --- |
| Executed for this reference | `scripts/validate_skills.py`; before/after retrieval tests of the text. No licensing code was compiled or run for it |
| Case-study implementation (another repository) | Its second version implements and tests the decision rules for one-time purchases (with `imported_customer` and unknown 404 messages), the revision-checked file with two-manager interleavings, the preflight, a single pending marker, the deadline abort, the libcurl probe (Linux build not yet confirmed in its CI) and a gate-on test target. It does not implement membership `entitledUntil` or the per-key check-and-claim above: there, two processes can still both claim one key |
| Required in an implementation | The matrix below, in the normal headless suite, with fakes only |
| Manual, needs a real purchase | Activation, offline restart, refund revoke, in each target host and platform |

Required matrix (fake `Verifier`, temp folder, injected clock and device id; two independent `LicenseManager`
instances on one folder for cross-process cases; a blocking fake makes interleavings deterministic):

- Decision table: one case per row in table order, including `imported_customer`, partial refund (an ordinary
  success reply, since partial refunds are not exposed), future and past
  `subscription_cancelled_at`, `failed_at`, `ended_at`, unknown 404 message on activation and on re-check.
- Stale revocation: A snapshots X; B activates Y; A's "disabled" arrives: file still Y, A adopts Y, no message.
- Stale success: same, A's success arrives: file and revision still B's.
- Replacement during verification: A and B re-check X; B's success writes a new revision; A's revocation is
  discarded and A adopts the file.
- Competing activations of different keys: last writer wins; both processes end on the same file.
- Failed persistence: licensed for the session, warning kept in status, no pending marker left behind.
- Uncertain activation: the incrementing call returns no answer, the marker exists, the next attempt (also in a
  fresh manager) sends only non-incrementing requests and a licensed reply clears the marker.
- One key, two processes: A claims and blocks inside its incrementing call; B activates the same key. B sends no
  incrementing request, and none at all while A's marker is young, and reports `pending`. Release A as licensed:
  the license is written, A's marker removed, B adopts it. Incrementing calls across both managers: exactly one.
- Simultaneous claims: run B's whole activation of the same key from inside A's preflight call, so B claims
  between A's preflight and A's claim. A must find B's marker and not claim: one marker, one incrementing call.
- Crash recovery: a marker older than the deadline, from no live process; B's activation sends only a
  non-incrementing request, writes the license on "licensed" and removes the marker.
- Stale resolver: A snapshots marker `c1` and blocks resolving it; B removes `c1` on a definitive verdict, then
  claims the key again (`c2`). Release A: `c2` is untouched and A's result is discarded.
- Different keys: A claims X while B claims Y; each sends one incrementing call, neither touches the other's
  marker, and both processes end on the last activation written.
- Refusal keeps a license: an incrementing call refused (over the allowance) while `license.json` holds a license
  leaves that file unchanged.
- Preflight: over the allowance is refused with no incrementing call.
- Missing libcurl: an injected failing probe makes no request and returns the libcurl message.
- Shutdown: with a blocking fake whose cancel releases it, destruction returns promptly and no callback runs
  afterwards. With a fake that ignores cancel until released, destruction waits (it must not return early or
  kill the thread). That bounds shutdown by the backend's abort time, not by a promise about networks.
- Gate on, network off: a test target that defines the gate and swaps `ProductionLicenseManager`'s dependencies
  for fakes (for example a test-only compile definition selecting a fake `Verifier` and a temp folder), so the
  processor path is exercised: unlicensed output shows a dropout at the expected time, licensed
  output is bit-identical to the gate-off build.
- Audio thread: `DemoGate` has no heap or lock members (inspection or `static_assert` on its layout); the
  processor reports the same latency with the gate on and off; add an allocation or lock detector only if the
  project has one, and claim only what it checks.

No real purchases, seller API calls or Gumroad requests in CI. A manual smoke mode that sends one verify with a
fake key and `increment_uses_count=false` is fine outside the suite.

## Support And Recovery

- **"Activation limit reached":** confirm the buyer (receipt email), open the sale in the Gumroad dashboard,
  lower or reset **Uses** in its License key section, ask them to activate again.
- **New computer or reinstall:** same procedure; the old machine keeps its file until removed.
- **Pending activation that never resolves:** reset **Uses** if the count looks one high.
- **Leaked key:** reset its **Uses**, then rotate it in the dashboard and send the buyer the new key; every
  machine holding the old key falls to demo at its next re-check.
- **Membership ended or cancelled:** nothing to do; restarting the membership clears the timestamps.

## Upgrade Path: A Signing Server

Boundaries:

| Concern | Owner |
| --- | --- |
| Was this purchase made, is it refunded, charged back or ended | Gumroad (verify, Ping, `GET /v2/sales` with the seller token) |
| Device registration, deactivation, seat policy | Your server |
| Offline license | A token your server signs (key, device, expiry), verified with an embedded public key |
| Refresh and revocation | The plugin refreshes before expiry; your server refuses refresh for revoked purchases |

Gumroad Ping facts (Ping page and `post_to_individual_ping_endpoint_worker.rb`, `ping_signature.rb` at `f1a9c5b`):

- Signing is off until the seller enables it in settings; until then the endpoint URL is the only credential.
  Keep the secret on the server only.
- Only the seller's own Ping endpoint is signed. Deliveries to OAuth resource subscriptions
  (`/v2/resource_subscriptions`) are not.
- `X-Gumroad-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256 of "t." + raw body>`. Verify on the raw bytes
  before parsing, compare in constant time, reject `t` more than 5 minutes from your clock, and remember
  accepted signatures for that window to refuse replays. Deduplicate on `sale_id` plus `resource_name`.
- Delivery is best-effort: at least once, unordered, a few retries over about an hour, then dropped. The Ping
  page says timeouts and connection errors are not retried; the worker at `f1a9c5b` retries them. Do not rely
  on either: reconcile periodically against the API and re-verify on refresh.

Moving from A to B changes more than the verifier: the activation and refresh protocol, the file format (a signed,
expiring token), the UI (deactivate, device list), seat semantics (devices instead of uses), server operations
(signing keys, Ping secret, reconciliation, uptime), the privacy policy (device ids leave the machine), the
support procedure, and a migration that accepts licenses issued under A at first contact.

## Common Mistakes

- Treating `success: true` as entitlement, or a cancelled membership as already ended.
- Sending `product_permalink` for a new product, or anything but the literal `false` on re-checks.
- Retrying an activation with `increment_uses_count=true` after a timeout.
- Writing a pending marker without re-reading it under the lock, or sharing one marker between keys: two
  processes then both send a counting request.
- Deleting or overwriting `license.json` from a result without checking that its key and revision are still on
  disk.
- Calling `cancel()` while holding a lock the worker needs, or freeing the stream another thread may cancel.
- Shutting the worker down with `stopThread (timeout)` and relying on the force-kill path.
- A libcurl probe that accepts any name with one symbol, when JUCE uses the first name that opens.
- Showing "Demo" while a licensed customer's background re-check runs.
- Letting test targets construct the real manager, or never testing the gate-on configuration.
- Trusting unsigned Ping deliveries, or treating Ping as guaranteed revocation.
- Testing with the editor's sample key and concluding activation is broken.

## Sources

- Gumroad API, Licenses: <https://gumroad.com/api#licenses>; Help Center, "License keys" (article 76):
  <https://gumroad.com/help/article/76-license-keys>; Ping: <https://gumroad.com/ping> (all read 2026-11-08)
- Gumroad source, <https://github.com/antiwork/gumroad> at `f1a9c5b5ee938eed374012ec9937d8c7f1f26631`:
  `app/controllers/api/v2/licenses_controller.rb`, `go_web/internal/licenses/purchase_json.go`,
  `app/models/subscription.rb`, `app/models/imported_customer.rb`, `app/modules/purchase/refundable.rb`,
  `app/models/license.rb`, `config/initializers/rack_attack.rb`, `app/services/ping_signature.rb`,
  `app/sidekiq/post_to_individual_ping_endpoint_worker.rb`
- JUCE 9.0.3 (<https://github.com/juce-framework/JUCE>): `juce_core/native/juce_Network_curl.cpp`,
  `juce_Network_mac.mm`, `juce_Network_windows.cpp`, `juce_SystemStats_*`, `juce_core/threads/juce_Thread.cpp`
  (`stopThread`), `juce_core/files/juce_File.cpp` and `juce_TemporaryFile.cpp`, `juce_core/juce_core.h`
  (`JUCE_USE_CURL`, `JUCE_LOAD_CURL_SYMBOLS_LAZILY`), `juce_product_unlocking/marketplace/juce_OnlineUnlockStatus.h`
