# Claim protocol

## Contents
- [Registry layout](#registry-layout)
- [Claim record](#claim-record)
- [Holder identity](#holder-identity)
- [Holder states and claim lifetime](#holder-states-and-claim-lifetime)
- [Acquisition](#acquisition)
- [Ownership lifecycle](#ownership-lifecycle)
- [Overlap rules](#overlap-rules)
- [When the registry cannot be trusted](#when-the-registry-cannot-be-trusted)
- [What the lock guarantees](#what-the-lock-guarantees)

## Registry layout

```text
<checkout>/.agent-state/
  .gitignore        "*": the directory ignores itself; no write to .git and no tracked-file change is needed
  claims.lock       the registry lock; created once, never deleted or replaced
  claims/<id>.json  active claims, each published atomically
  claims/stale/     claims archived because they expired and their holder is dead; kept for review
  claims/.tmp-*     an interrupted publication; ignored by readers, reported by `status`
  claims/.DS_Store  if Finder wrote one: reported by `status` and `check`, ignored, never deleted
```

The registry is per checkout. Every directory must be a real directory inside the checkout (no symlinks), and git
must ignore it: the tool refuses a registry git would track rather than risk committing coordination records.
`.agent-state/` may also hold handoff records (`agent-handoff`): ignored is not disposable, so never run `git clean -x`
in a checkout that may hold them.

## Claim record

The format is `claim` version 1 (RFC 0001, document 05). The tool writes it; you do not.

```json
{
  "kind": "claim",
  "version": 1,
  "id": "20261127T184000Z-7f3a1c2b",
  "holder": { "agent": "claude-code", "session": "<random token>", "host": "<host name>", "pid": 41237,
              "process_start": "lstart:Fri Nov 27 18:02:11 2026", "boot": "bsd:1764200000" },
  "scope": { "type": "checkout", "value": "." },
  "mode": "exclusive",
  "intent": "Refactor the parser",
  "created": "2026-11-27T18:40:00Z",
  "expires": "2026-11-27T20:40:00Z"
}
```

Two optional fields record ownership changes. `transfer` is a pending offer: the SHA-256 of a one-time transfer token
(never the token), when it was offered and when it lapses. `history` lists each change of holder (`transferred` or
`recovered`), when, and the public identities of the former and new holders, never their session tokens.

## Holder identity

- **The holder is the session's long-lived process**, not the command that ran the tool. The tool walks up its own
  ancestry and takes the nearest ancestor that is not a `sh -c`, `bash -lc`, `zsh -c` or `env` wrapper. Under Claude
  Code or Codex that is the agent process.
- **It must be a session boundary.** A candidate is rejected if a process beneath it has a controlling terminal other
  than its own and those of this session's own process chain (a terminal multiplexer, IDE or terminal application
  hosts several; an agent that runs each command in a fresh pty does not count against itself), or if a process
  beneath it holds another registered claim (a shell that started two agents). These tests use the process tree, terminals and the registry;
  no process name is consulted. If the nearest candidate is not a boundary, there is no holder: the tool does not
  climb further, because anything higher is broader still.
- **`--holder-pid`** overrides the choice, but only with this process or one of its ancestors, and only if it passes
  the same boundary test. A claim can never be made on behalf of an unrelated or shared process.
- **Process identity** is read by `scripts/process_identity.py`, a generated copy of `operational/process_identity.py`
  that `agent-handoff` shares, so both skills judge a process the same way.
- **Process start time** defends against PID reuse: `/proc/<pid>/stat` on Linux, `ps -o lstart=` (C locale, UTC)
  elsewhere. A holder is alive only if its PID exists **and** its start time matches.
- **Boot identity** (`/proc/sys/kernel/random/boot_id`, or `kern.boottime`) shows that a same-host holder predates a
  reboot, and therefore cannot be running.
- **Fail closed.** If no holder can be established, `acquire` reports unknown instead of writing a claim that could
  never be verified, renewed or released. A claim with `pid` and `process_start` null (written by another tool) is
  treated as unknown, never dead.
- **Session tokens** stop cooperating agents from renewing or releasing each other's claims by mistake. They are not
  authentication: any process running as the same user can read the registry. A token alone never establishes
  ownership; see the [ownership lifecycle](#ownership-lifecycle).

A limitation remains: a shell that started two agents is recognised as shared only once the other agent holds a
claim. Leave `--holder-pid` unset unless the automatic choice is wrong, and never point it at a shell other sessions
run in.

## Holder states and claim lifetime

| State | Established when | Effect on an overlapping request |
|---|---|---|
| live | Same host and boot; the PID exists with the recorded start time | Conflict |
| expired-held | Live, but past `expires` | Conflict: an expired claim is not abandoned while its holder runs |
| holder-dead-unexpired | The holder is provably dead, but the claim has not expired | Conflict until expiry |
| transfer-pending | The holder is not live, but its transfer offer has not lapsed | Conflict: the claim waits for its successor |
| stale | Expired **and** the holder is provably dead (PID gone, PID reused, or host rebooted) and no offer is open | Archived to `claims/stale/` under the lock; no conflict |
| unknown / expired-unknown | Another host, no recorded identity, or the process table cannot be read | Conflict; after expiry the owner may decide to move the file to `claims/stale/` by hand |

## Acquisition

1. Resolve the checkout root with git. Coordination must be available: `fcntl` exists, the filesystem is identified and
   local, and the tool does not run in an isolated PID namespace (a container). Otherwise: unknown.
2. Make sure the registry exists, is real directories and is ignored by git.
3. Determine the holder identity and validate it as a session boundary (outside the lock). None: unknown.
4. **Enter the critical section:** open `claims.lock` (no symlinks followed) and take `fcntl.flock(LOCK_EX | LOCK_NB)`,
   retried every 20 ms until the timeout (10 s by default). Timeout: "registry busy", status unknown.
5. Read every entry in `claims/`. Any malformed record, unexpected or hidden file (other than a regular `.DS_Store`),
   symlink or oversized file stops the acquisition with status unknown: nothing is granted.
6. Determine each holder's state; archive stale claims; collect every overlapping claim in an incompatible mode.
7. If there is any conflict, return it (status conflict) with each holder's state, reason, intent and expiry.
8. Otherwise write the new claim to a temporary file, flush it, rename it into place, flush the directory, and leave
   the critical section. The lock is held for milliseconds, never for the work.

A request carrying `--session` of an existing claim held by this same process treats that claim as its own. For a
disruptive check, that claim must also be exclusive, live and **cover** the checked scope (see
[activity check](activity-check.md#disruptive-and-destructive-checks)).

## Ownership lifecycle

Every operation below runs inside the critical section. Ownership means the session token **and** the recorded
identity (host, boot, PID, start time) both match the caller.

| Operation | Command | Who may | Effect |
|---|---|---|---|
| Renew | `renew --id I --session T` | The current holder | New expiry |
| Release | `release --id I --session T` | The current holder; or the token's bearer once the holder is provably dead and no transfer is pending | Claim deleted |
| Offer a transfer | `transfer --id I --session T [--ttl M]` | The current holder | Prints a one-time transfer token; the claim records its digest and stays the holder's |
| Accept a transfer | `accept --id I --transfer-token X` | The successor, before the offer lapses | One atomic replacement: the successor becomes holder with a new session token, the offer is removed, `history` records it |
| Recover | `adopt --id I --session T` | The token's bearer, once the holder is provably dead and no transfer is pending | The bearer becomes holder with a new session token; `history` records `recovered` |

- **The token is not ownership.** A process with the right token but another identity cannot renew; the activity
  check reports such a claim as someone else's, never as this session's.
- **A transfer leaves no window.** The registry never shows the claim as released between holders, so a third agent
  cannot acquire in between. The former holder's token stops working at once. An open offer also protects the claim
  if the former holder dies before the successor accepts.
- **Copying a token is not a handoff.** Put the claim ID and the transfer token in the handoff record; the successor
  runs `accept`. If no safe transfer is possible (the holder died without offering one and its token is lost, or it
  runs on another host), the claim is released or expires and the successor acquires anew; report the gap.
- **Recovery never displaces a live or unknown holder.** A holder on another host, or one whose identity was never
  recorded, stays until it releases, its claim expires and the owner moves it, or the owner decides otherwise.
- A renewal that loses the race with a release finds no claim and reports `missing`: a released claim is never
  resurrected. `archive-stale` moves every stale claim to `claims/stale/`.

## Overlap rules

| | `checkout` | `branch` X | `paths` P | `resource` R |
|---|---|---|---|---|
| **`checkout`** | overlap | overlap | overlap | overlap |
| **`branch` Y** | overlap | if X = Y | no | no |
| **`paths` Q** | overlap | no | if any prefix of P is equal to, a parent of, or a child of a prefix of Q | if R's path is related to a prefix of Q |
| **`resource` S** | overlap | no | if S's path is related to a prefix of P | if R = S, or their paths are related |

- Exclusive conflicts with every overlapping claim; shared conflicts only with overlapping exclusive claims. Shared
  claims never authorize writes.
- Paths must be canonical, relative and inside the checkout (`..`, `./`, `//`, backslashes and absolute paths are
  rejected). Each glob's literal prefix (the part before the first `*`, `?` or `[`) is resolved, following symlinks, so
  aliases compare as the same path. On a case-insensitive filesystem, prefixes are compared case-folded and
  NFC-normalized.
- A prefix that resolves outside the checkout cannot be compared reliably and counts as a conflict.
- A branch claim is not a claim on the working tree: an agent holding `branch=X` still needs a checkout or paths claim
  to edit files.

## When the registry cannot be trusted

| Condition | Result |
|---|---|
| `.agent-state`, `claims/` or `claims/stale/` is a symlink, not a directory, or resolves outside the checkout | Unknown: unsafe registry location |
| git would track `.agent-state` | Unknown: refusing to use it |
| A malformed, symlinked, oversized, unexpected or hidden entry in `claims/` (a regular `.DS_Store` excepted) | Unknown: registry cannot be inspected |
| The lock stays busy beyond the timeout | Unknown: try again later |
| `fcntl` is missing (Windows) or `flock` fails on this filesystem | Unknown: claims unavailable |
| The checkout is on a network filesystem, or its filesystem cannot be identified | Unknown: advisory claims are unreliable there |
| The tool runs in a Linux PID namespace other than the initial one (most containers) | Unknown: processes and holders outside it cannot be verified |
| This session's holder cannot be established as a session boundary | Unknown: no claim is written |

None of these is ever reported as a grant, as "no conflict" or as "idle". The read-only `check` reports the same
conditions as coordination being unavailable.

## What the lock guarantees

- **Guaranteed among cooperating agents on one machine and a local filesystem:** acquire, renew, release, transfer,
  recovery and archival never interleave, so two overlapping claims are never both granted. A crashed holder releases
  the lock with its file descriptor; only its claim remains, and it follows the lifetime rules above.
- **Not guaranteed:** anything about processes that do not use the tool; anything across machines; anything on a
  filesystem where advisory locks are not shared between clients.
