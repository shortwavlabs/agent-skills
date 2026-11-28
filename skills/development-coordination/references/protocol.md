# Claim protocol

## Contents
- [Registry layout](#registry-layout)
- [Claim record](#claim-record)
- [Holder identity](#holder-identity)
- [Holder states and claim lifetime](#holder-states-and-claim-lifetime)
- [Acquisition](#acquisition)
- [Renewal, release and stale archival](#renewal-release-and-stale-archival)
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
```

The registry is per checkout. Every directory must be a real directory inside the checkout (no symlinks), and git
must ignore it: the tool refuses a registry git would track rather than risk committing coordination records.
`.agent-state/` may also hold handoff records later (`agent-handoff`): ignored is not disposable, so never run
`git clean -x` in a checkout that may hold them.

## Claim record

The format is `claim` version 1 (RFC 0001, document 05). The tool writes it; you do not.

```json
{
  "kind": "claim",
  "version": 1,
  "id": "20261127T184000Z-7f3a1c2b",
  "holder": { "agent": "claude-code", "session": "<random token>", "host": "<host name>", "pid": 41237,
              "process_start": "lstart:Thu Nov 27 18:02:11 2026", "boot": "bsd:1764000000" },
  "scope": { "type": "checkout", "value": "." },
  "mode": "exclusive",
  "intent": "Refactor the parser",
  "created": "2026-11-27T18:40:00Z",
  "expires": "2026-11-27T20:40:00Z"
}
```

## Holder identity

- **The holder is the session's long-lived process**, not the command that ran the tool. The tool walks up its own
  ancestry and takes the first ancestor that is not a `sh -c`, `bash -lc`, `zsh -c` or `env` wrapper. Under Claude
  Code or Codex that is the agent process; in an interactive terminal it is the shell.
- **`--holder-pid`** overrides the choice, but only with this process or one of its ancestors. A claim can never be
  made on behalf of an unrelated process.
- **Process start time** defends against PID reuse: `/proc/<pid>/stat` on Linux, `ps -o lstart=` (C locale, UTC)
  elsewhere. A holder is alive only if its PID exists **and** its start time matches.
- **Boot identity** (`/proc/sys/kernel/random/boot_id`, or `kern.boottime`) shows that a same-host holder predates a
  reboot, and therefore cannot be running.
- **Fail closed.** If the holder process or its start time cannot be determined, the claim records `pid` and
  `process_start` as null; other agents then see the holder as unknown, never dead.
- **Session tokens** stop cooperating agents from renewing or releasing each other's claims by mistake. They are not
  authentication: any process running as the same user can read the registry.

## Holder states and claim lifetime

| State | Established when | Effect on an overlapping request |
|---|---|---|
| live | Same host and boot; the PID exists with the recorded start time | Conflict |
| expired-held | Live, but past `expires` | Conflict: an expired claim is not abandoned while its holder runs |
| holder-dead-unexpired | The holder is provably dead, but the claim has not expired | Conflict until expiry |
| stale | Expired **and** the holder is provably dead (PID gone, PID reused, or host rebooted) | Archived to `claims/stale/` under the lock; no conflict |
| unknown / expired-unknown | Another host, no recorded identity, or the process table cannot be read | Conflict; after expiry the owner may decide to move the file to `claims/stale/` by hand |

## Acquisition

1. Resolve the checkout root with git and refuse network filesystems (best-effort detection from the mount table).
2. Make sure the registry exists, is real directories and is ignored by git.
3. Determine the holder identity (outside the lock).
4. **Enter the critical section:** open `claims.lock` (no symlinks followed) and take `fcntl.flock(LOCK_EX | LOCK_NB)`,
   retried every 20 ms until the timeout (10 s by default). Timeout: "registry busy", status unknown.
5. Read every entry in `claims/`. Any malformed record, unexpected file, symlink or oversized file stops the
   acquisition with status unknown: the registry cannot be inspected, so nothing is granted.
6. Determine each holder's state; archive stale claims; collect every overlapping claim in an incompatible mode.
7. If there is any conflict, return it (status conflict) with each holder's state, reason, intent and expiry.
8. Otherwise write the new claim to a temporary file, flush it, rename it into place, flush the directory, and leave
   the critical section. The lock is held for milliseconds, never for the work.

A request carrying `--session` of an existing claim with the same holder treats that claim as its own.

## Renewal, release and stale archival

All three take the same lock. Renewal and release require the claim's session token; renewal rewrites the claim
atomically with a new expiry; release deletes the claim file. `archive-stale` moves every stale claim to
`claims/stale/`. A renewal that loses the race with a release finds no claim and reports `missing`: a released claim
is never resurrected.

## Overlap rules

| | `checkout` | `branch` X | `paths` P | `resource` R |
|---|---|---|---|---|
| **`checkout`** | overlap | overlap | overlap | overlap |
| **`branch` Y** | overlap | if X = Y | no | no |
| **`paths` Q** | overlap | no | if any prefix of P is equal to, a parent of, or a child of a prefix of Q | if R's path is related to a prefix of Q |
| **`resource` S** | overlap | no | if S's path is related to a prefix of P | if R = S, or their paths are related |

- Exclusive conflicts with every overlapping claim; shared conflicts only with overlapping exclusive claims.
- Paths must be canonical, relative and inside the checkout (`..`, `./`, `//`, backslashes and absolute paths are
  rejected). Each glob's literal prefix (the part before the first `*`, `?` or `[`) is resolved, following symlinks, so
  aliases compare as the same path.
- A prefix that resolves outside the checkout cannot be compared reliably and counts as a conflict.
- A branch claim is not a claim on the working tree: an agent holding `branch=X` still needs a checkout or paths claim
  to edit files.

## When the registry cannot be trusted

| Condition | Result |
|---|---|
| `.agent-state`, `claims/` or `claims/stale/` is a symlink, not a directory, or resolves outside the checkout | Unknown: unsafe registry location |
| git would track `.agent-state` | Unknown: refusing to use it |
| A malformed, symlinked, oversized or unexpected entry in `claims/` | Unknown: registry cannot be inspected |
| The lock stays busy beyond the timeout | Unknown: try again later |
| `fcntl` is missing (Windows) or `flock` fails on this filesystem | Unknown: claims unavailable |
| The checkout is on a network filesystem | Unknown: advisory claims are unreliable there |

None of these is ever reported as a grant or as "no conflict".

## What the lock guarantees

- **Guaranteed among cooperating agents on one machine and a local filesystem:** acquire, renew, release and archival
  never interleave, so two overlapping claims are never both granted. A crashed holder releases the lock with its file
  descriptor; only its claim remains, and it follows the lifetime rules above.
- **Not guaranteed:** anything about processes that do not use the tool; anything across machines; anything on a
  filesystem where advisory locks are not shared between clients.
