---
name: development-coordination
description: Coordinate cooperating coding agents that share one git checkout, without a daemon, database or service. Covers session-level checkout claims through a serialized advisory registry (acquire, renew, release, stale archival), conservative overlap of checkout, branch, path and resource scopes, holder identity by session, host, PID and process start time, activity checks of process working directories, open files, claims, git operations in progress and uncommitted work, partial process visibility reported as unknown, safe execution of disruptive operations, and documented fallbacks for Windows and network filesystems. Use before switching branches, committing, resetting, rebasing, cleaning or rebuilding in a checkout other agents may use, before starting or stopping a shared dev server, before pushing to a branch you did not create, when another agent's activity is observed, when a harness offers an isolated worktree, or when a checkout looks idle but has not been checked.
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
   for long tasks; release it when the task ends or ownership is handed over.
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
# ... edit, build and test normally: no further checks ...
python3 $C check --session <token> --disruptive && git switch release/1.4     # before a disruptive step
python3 $C renew --id <id> --session <token> --ttl 120                         # long task
python3 $C release --id <id> --session <token>                                 # task ends or is handed over
```

Record the claim ID and session token in your handoff record so another session can renew or release it.

| Command | Purpose | Exit status |
|---|---|---|
| `check [--scope S] [--session T] [--disruptive]` | Read-only activity check | 0 idle, 1 busy, 2 unknown |
| `acquire --scope S --intent TEXT [--mode shared] [--ttl M]` | Serialized conflict check and claim | 0 granted, 1 conflict, 2 unknown |
| `renew --id I --session T [--ttl M]` / `release --id I --session T` | Extend or end your claim | 0 done, 2 otherwise |
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
- **Documented fallback, not tested:** on Windows, on network filesystems (NFS, SMB and similar) and wherever locking
  or process inspection cannot be established, the tool reports the capability as unavailable and the result as
  unknown. It never reports a grant or "idle" it cannot back. Ordinary non-conflicting work continues; disruptive
  operations follow the manual procedure in [procedures](references/procedures.md#manual-coordination-fallback).
- Remote branches and PRs are coordination signals across machines, not distributed locks.

## Composition

- **`workspace-housekeeping`** owns worktree policy, worktree removal, deletion manifests and the authoritative
  in-use check; this skill runs a generated copy of that check (`scripts/path_in_use.py`) and never re-implements it.
  If housekeeping is not installed, delete nothing that is not a disposable, task-owned file without the owner's
  approval.
- **`agent-handoff`** (Phase 1c) records the claim ID and session token so another session can resume, renew or
  release the claim.
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
evidence: claim 20261127T184000Z-7f3a1c2b (exclusive checkout, live: process 41237 is running): Refactor the parser
evidence: process 52110 (node) works in /work/app
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
