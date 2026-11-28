# Activity check

`python3 scripts/coordination.py check [--scope S] [--session T] [--disruptive | --destructive] [--accept-passive ID]...
[--all]` is read-only: it creates no registry, runs git without optional locks and writes no bytecode. It answers
**idle**, **busy** or **unknown**, and says whether coordination is available, what visibility it had and what it
found.

## Contents
- [What it inspects](#what-it-inspects)
- [Verdicts and output](#verdicts-and-output)
- [Disruptive and destructive checks](#disruptive-and-destructive-checks)
- [This session's own processes](#this-sessions-own-processes)
- [Passive processes and interactive shells](#passive-processes-and-interactive-shells)
- [Interpreting benign system activity](#interpreting-benign-system-activity)
- [What it cannot detect](#what-it-cannot-detect)

## What it inspects

| Evidence | How | Effect |
|---|---|---|
| Coordination availability | `fcntl`, the filesystem type, container detection, the registry's safety and git-ignore status | Unavailable: unknown, reported on its own line, never as idle |
| Other agents' claims overlapping the scope | The registry, read without the lock (claims are published atomically) | Live, expired-held, dead-unexpired or transfer-pending: busy. Unknown holder: unknown. Uninspectable registry: unknown |
| A claim carrying your session token but another process identity | The registry | Busy: it is not this session's claim (accept a transfer or recover it first) |
| Processes using the scope | `scripts/path_in_use.py`, a generated copy of `workspace-housekeeping`'s in-use check: every readable process's working directory **and** open files, including executables and mapped libraries, for every target of the scope | Active or passive: busy, unless an owner-accepted passive identity applies. Partial or failed visibility on any target: unknown |
| Git operations in progress | `index.lock`, `MERGE_HEAD`, `CHERRY_PICK_HEAD`, `REVERT_HEAD`, `BISECT_LOG`, `rebase-merge/`, `rebase-apply/` in the git directory | Busy |
| Uncommitted and untracked work | `git status --porcelain` | Reported. Disruptive or destructive: busy, because the operation would put it at risk and its owner is unknown |

Development servers and builds are detected through their working directories and open files: a server whose working
directory is elsewhere but which holds a file in the checkout open is still found.

## Verdicts and output

- **idle** means idle *within the verified scope*: no claim, process or git operation was found, coordination is
  available, and process visibility was complete or owner-complete (every process of the checkout's owner was
  inspected). Processes of other users are not inspected without root.
- **busy** means something was found. Defer, hand off, or choose a non-conflicting alternative.
- **unknown** means the check could not establish the answer: coordination unavailable, partial visibility, a failed
  `lsof` or `ps`, an uninspectable registry, an unverifiable holder. Unknown blocks disruptive operations exactly like
  busy. It is never a statement that the checkout is idle.

The verdict uses every matching process. The output gives the total (active, passive and accepted), lists the first
ten, says how many more were omitted, and `--all` lists every one. The visibility line reports the worst visibility
over all targets.

## Disruptive and destructive checks

- `--disruptive` (a branch switch, reset, rebase, commit in a shared tree, rebuild): requires this session's **live
  exclusive** claim covering the scope, passed with `--session`; a shared claim or a branch claim never authorizes it.
  Uncommitted work blocks.
- `--destructive` (deleting files or directories, removing a worktree, discarding work): everything `--disruptive`
  requires, and no passive acceptance ever applies.

## This session's own processes

The check excludes only processes established, by ancestry, to belong to this session: the holder (validated as a
session boundary, as in [holder identity](protocol.md#holder-identity)), all of its descendants, and the tool's own
process chain. The number excluded is printed. Nothing is excluded because of its name. If no holder can be
established, only the tool's own chain is excluded, which may report the session's helper processes as busy:
conservative, never optimistic.

## Passive processes and interactive shells

A terminal tab whose shell sits in the checkout (the Terminal panel of an agent app, opened at the project) is a
process with its working directory there. The check reports it as **passive** when its only presence in the scope is
its working directory, it has no child processes and no open files there, with its PID, command, working directory and
an identity of the form `<pid>:<digest of its start time>`. Passive is evidence, not a verdict: a person may run
`git switch` in that shell a second later, so a passive process is busy.

An **active** process holds files open in the scope or has child processes. A process with children is active even
when it is a shell.

For a **reversible** operation, the owner may accept one established passive process:
1. Show the owner the passive line (process, command, working directory, identity) and the operation.
2. With the owner's explicit approval for that identity and operation, run
   `check --session T --disruptive --accept-passive <identity>`, chained with the operation.
3. The acceptance applies only while the same process (same PID **and** start time) is still passive: each check
   revalidates it. A restarted shell, a child process or an open file ends it.
4. Record the acceptance in the handoff or report.

An acceptance never applies to `--destructive` checks, never stands in for this session's claim, and never hides
another agent's claim, uncommitted work, a git operation in progress or incomplete visibility. There is no global
switch to ignore shells.

## Interpreting benign system activity

The operating system and tools often touch a checkout: Spotlight (`mdworker_shared`), file-system event daemons, IDE
indexers, backup agents, antivirus scanners. The check reports them like any other process, because a familiar name is
not evidence of harmlessness.

To judge such a report:
1. Read what it holds: `lsof -p <pid>`. A read-only handle on files you are not about to delete is usually harmless for
   a branch switch; a write handle, a working directory inside the checkout, or a lock file is not.
2. Re-run the check after a short wait. Indexers come and go; a persistent holder deserves attention.
3. Never kill a process you did not start without the owner's authorization.
4. For destructive operations (deleting, removing a worktree), a reported holder blocks the entry until it is gone or
   the owner decides.
5. Record what you saw and decided in the handoff or report. Do not add the process to any allowlist: there is none.

## What it cannot detect

- Agents or processes on other machines (remote branches and PRs are the only signals there).
- Processes of other users, unless run as root (reported as owner-complete visibility).
- Processes of this user that the system does not let `lsof` read (non-dumpable processes, as on GitHub-hosted
  Linux runners). Visibility is then partial, and the check answers unknown, never idle, unless run with more
  privilege. Ordinary work is unaffected; only disruptive steps wait for the owner.
- A process that will write into the checkout but has no working directory or open file there yet.
- Activity between the check and your operation: chain the check with the command to narrow the window.
- On Windows, or without `lsof` and `ps`, processes at all: the verdict is unknown.
- Processes in another PID namespace. Inside a container the check reports coordination as unavailable, and an agent
  there cannot hold claims; coordinate such setups manually.
