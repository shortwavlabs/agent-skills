---
name: development-coordination
description: Coordinate cooperating coding agents sharing one git checkout, without a daemon or service. Covers session claims through a serialized advisory registry (acquire, renew, release, transfer to a successor, recovery after holder death), conservative overlap of checkout, branch, path and resource scopes, holder identity by session, host, PID and start time validated as a session boundary, activity checks of process working directories, open files, claims, git operations in progress and uncommitted work, passive interactive shells, partial visibility reported as unknown, safe disruptive and destructive operations, and fallbacks for Windows, network filesystems and containers. Use before switching branches, committing, resetting, rebasing, cleaning or rebuilding in a checkout other agents may use, before starting or stopping a shared dev server, before pushing to a branch you did not create, when handing work to another session, when another agent's activity is observed, or when a harness offers a worktree.
---

# Development Coordination

Lets several coding agents (Claude Code, Codex, OpenCode or others) work in one shared checkout without stepping on
each other: who holds the working tree, whether anything is running in it, and how to perform a disruptive operation
safely. Everything is files, git and the standard library: no daemon, database or hosted service.

- The protocol, overlap rules and holder identity: [references/protocol.md](references/protocol.md).
- The activity check and how to read it: [references/activity-check.md](references/activity-check.md).
- Safe execution, busy checkouts, fallbacks and composition: [references/procedures.md](references/procedures.md).
- The shared risk, authorization and evidence rules: [references/operational-core.md](references/operational-core.md)
  (a generated copy; do not edit it).

## When to use it, and when not

Use it when you will change shared state that another agent may depend on: switching branches, committing, resetting,
rebasing, cleaning or rebuilding in a checkout others may use; starting or stopping a long-lived dev server; pushing to
a branch you did not create.

Do **not** use it for routine work in your own scope. No claim per edit, no activity check before every test run, no
confirmation prompts. One session-level claim covers a whole task.

## Principles

1. **A clean working tree is not an idle checkout.** Another agent may be running a server, a build or a git command
   in it. Check before disruptive operations.
2. **Claim the checkout once per session** when you will modify a shared working tree, then work normally. Renew it
   for long tasks; release it when the task ends, or transfer it when another session takes over.
3. **Unknown is not idle.** Partial process visibility, an uninspectable registry or a missing capability is reported
   as unknown, and unknown blocks disruptive operations.
4. **Claims are advisory.** They stop cooperating agents, not other processes. The activity check is the backstop.
5. **Busy means defer, hand off or choose a non-conflicting alternative.** Never stash or overwrite another agent's
   work, switch branches under an active session, kill another session's processes, bypass git's refusals, or create
   a worktree because the checkout is busy.
6. **Owner approval does not resolve unknown concurrency.** It authorizes an operation; it does not make an unknown
   process safe to disturb.
7. **Revalidate immediately before a destructive step**, chained with it.

## Session workflow

```bash
C=skills/development-coordination/scripts/coordination.py      # or this skill's installed scripts/ folder
python3 $C check                                                 # read-only: idle, busy or unknown, with evidence
python3 $C acquire --scope checkout --intent "Refactor the parser" --ttl 120
# -> {"status": "granted", "claim": {"id": "20261127T184000Z-7f3a1c2b", ...}, "session": "<token>"}
python3 $C check --session <token>                               # after acquiring: catches non-participants
# ... edit, build and test normally: no further checks ...
python3 $C check --session <token> --disruptive && git switch release/1.4     # before a disruptive step
python3 $C renew --id <id> --session <token> --ttl 120                         # long task
python3 $C release --id <id> --session <token>                                 # task ends
python3 $C transfer --id <id> --session <token>       # handing over: prints a one-time transfer token for the handoff
python3 $C accept --id <id> --transfer-token <x>      # the successor takes over and gets its own session token
```

The tool records the session's long-lived process as holder and checks that it stands for this session alone (no
other terminal and no other claim holder beneath it); it never goes by process names. Leave `--holder-pid` unset
unless that choice is wrong. A token alone is not ownership: a session that only copied another's token cannot renew
the claim, so hand over with `transfer` and `accept` ([ownership lifecycle](references/protocol.md#ownership-lifecycle)).

An interactive shell sitting in the checkout with no children and no open files is reported as **passive**, and still
busy: a person may type a command there at any moment. For a reversible operation the owner may accept that one
process by its identity; for a destructive one nothing overrides it
([passive processes](references/activity-check.md#passive-processes-and-interactive-shells)).

| Command | Purpose | Exit status |
|---|---|---|
| `check [--scope S] [--session T] [--disruptive \| --destructive] [--accept-passive ID] [--all]` | Read-only activity check | 0 idle, 1 busy, 2 unknown |
| `acquire --scope S --intent TEXT [--mode shared] [--ttl M]` | Serialized conflict check and claim | 0 granted, 1 conflict, 2 unknown |
| `renew --id I --session T [--ttl M]` / `release --id I --session T` | Extend or end your claim (the holder only) | 0 done, 2 otherwise |
| `transfer --id I --session T` / `accept --id I --transfer-token X` | Hand a claim to a successor, atomically | 0 done, 2 otherwise |
| `adopt --id I --session T` | Recover a claim whose holder provably died | 0 done, 2 otherwise |
| `status` | List claims with their holder state | 0, or 2 if uninspectable |
| `archive-stale` | Move claims that are expired **and** whose holder is dead to `claims/stale/` | 0, or 2 |

## Scopes

| Scope | Use it for | Overlaps |
|---|---|---|
| `checkout` (default, exclusive) | Any session that modifies the shared working tree: edits, builds writing shared paths, index or HEAD changes | Everything in the checkout |
| `branch=NAME` | Operations on a ref without the working tree (push, PR updates). **Not** ownership of the working tree | The same branch, and checkout claims |
| `paths=GLOB,...` | Edits limited to paths shown to be independent of other work | Parent, child and aliased paths; checkout claims |
| `resource=ID[@PATH]` | A build directory, port or device | The same ID; paths containing or inside PATH; checkout claims |

Shared mode lets several holders read the same scope; it never authorizes writes. When overlap cannot be determined
(a path escaping the checkout through a symlink, for example), it counts as a conflict.

## What is enforced, and what is not

| Mechanism | Strength |
|---|---|
| The registry lock serializes acquire, renew, release and stale archival among agents using this tool | Enforced between cooperating agents only |
| Claims | Advisory: an agent that ignores them is not stopped |
| The activity check (working directories, open files, claims, git state, uncommitted work) | Detection, not prevention; partial visibility is reported |
| git's own refusals (index lock, non-fast-forward push, unmerged branch deletion) | Enforced by git unless forced, which is never done |
| Operating-system permissions, branch protection, owner-installed harness rules | Enforced outside this skill |

A race window remains between a check and the operation for processes that do not participate. Chaining the check with
the command narrows it; nothing closes it. The protocol does not guarantee safety against arbitrary concurrent writers.

## Platforms

- **Tested:** macOS (locally) and Linux (CI), with `fcntl.flock`, `ps` and `lsof`.
- **Documented fallback, not tested:** on Windows, on network or unidentified filesystems, inside containers and
  wherever locking or process inspection cannot be established, the tool reports coordination as unavailable and the
  result as unknown. It never reports a grant or "idle" it cannot back. Ordinary non-conflicting work continues; disruptive
  operations follow the manual procedure in [procedures](references/procedures.md#manual-coordination-fallback).
- Remote branches and PRs are coordination signals across machines, not distributed locks.

## Composition

- **`workspace-housekeeping`** owns worktree policy, worktree removal, deletion manifests and the authoritative
  in-use check; this skill runs a generated copy of that check (`scripts/path_in_use.py`) and never re-implements it.
  If housekeeping is not installed, delete nothing that is not a disposable, task-owned file without the owner's
  approval.
- **`agent-handoff`** (Phase 1c) records the claim ID and transfer token so the next session can accept the claim
  and resume.
- **`instruction-governance`** (Phase 1d) carries this skill's consultation triggers into each agent's instruction
  file and holds any owner-approved standing exception, for example one permitting worktrees for a named task.

## Example: two agents, one checkout

Agent A (Claude Code) claims the checkout for a refactor. Agent B (Codex) is asked to switch to the release branch:

```text
B$ python3 coordination.py acquire --scope checkout --intent "Switch to release/1.4 and build an RC"
{"status": "conflict", "conflicts": [{"state": "live", "reason": "process 41237 is running",
 "intent": "Refactor the parser", "agent": "claude-code", "expires": "2026-11-27T20:40:00Z", ...}]}
B$ python3 coordination.py check
verdict: busy
coordination: available
evidence: claim 20261127T184000Z-7f3a1c2b (exclusive checkout, live: process 41237 is running): Refactor the parser
evidence: 1 matching processes (1 active, 0 passive, 0 accepted passive)
evidence: active: process 52110 (node) works in /work/app; has child processes
```

B does not switch, stash or open a worktree. It tells the owner the checkout is held for the parser refactor until
20:40, and offers to wait, to prepare the release notes meanwhile, or to ask A's session to hand over.

## Common mistakes

| Mistake | Correction |
|---|---|
| Treating a clean `git status` as "nobody is working here" | Run `check`: processes, open files, claims and git state |
| Claiming per edit, or checking before every test | One session claim; check only before disruptive steps |
| Treating an expired claim as abandoned | Stale needs expiry **and** a dead holder; an expired claim whose holder runs is a conflict |
| Ignoring a process because its name looks harmless | Judge by identity and evidence; see [benign activity](references/activity-check.md#interpreting-benign-system-activity) |
| Opening a worktree because the checkout is busy | Defer, hand off or pick a non-conflicting task; worktrees need explicit authorization |
| Retrying with `--force` after git refuses | Investigate the refusal |
| Using a branch claim to edit the working tree | Branch claims cover the ref only; edits need a checkout or independent paths claim |
| Pasting another session's token to take over its claim | `transfer` then `accept`; `adopt` only once the holder has provably died |
| Treating an idle terminal shell in the checkout as nothing | It is passive and busy; ask the owner, who may accept that one identity for a reversible step |
