# Activity check

`python3 scripts/coordination.py check [--scope S] [--session T] [--disruptive]` is read-only: it creates no registry
and changes nothing. It answers **idle**, **busy** or **unknown**, with the evidence and the visibility it had.

## Contents
- [What it inspects](#what-it-inspects)
- [Verdicts](#verdicts)
- [This session's own processes](#this-sessions-own-processes)
- [Interpreting benign system activity](#interpreting-benign-system-activity)
- [Interactive shells](#interactive-shells)
- [What it cannot detect](#what-it-cannot-detect)

## What it inspects

| Evidence | How | Effect |
|---|---|---|
| Other agents' claims overlapping the scope | The registry, read without the lock (claims are published atomically) | Live, expired-held or dead-unexpired: busy. Unknown holder: unknown. Uninspectable registry: unknown |
| Processes using the scope | `scripts/path_in_use.py`, a generated copy of `workspace-housekeeping`'s in-use check: every readable process's working directory **and** open files, including executables and mapped libraries | Any match: busy. Partial or failed visibility: unknown |
| Git operations in progress | `index.lock`, `MERGE_HEAD`, `CHERRY_PICK_HEAD`, `REVERT_HEAD`, `BISECT_LOG`, `rebase-merge/`, `rebase-apply/` in the git directory | Busy |
| Uncommitted and untracked work | `git status --porcelain` | Reported. With `--disruptive`: busy, because a branch switch, reset or clean would put it at risk and its owner is unknown |

Development servers and builds are detected through their working directories and open files: a server whose working
directory is elsewhere but which holds a file in the checkout open is still found.

## Verdicts

- **idle** means idle *within the verified scope*: no claim, process or git operation was found, and process
  visibility was complete or owner-complete (every process of the checkout's owner was inspected). The visibility line
  says which. Processes of other users are not inspected without root.
- **busy** means something was found. Defer, hand off, or choose a non-conflicting alternative.
- **unknown** means the check could not establish the answer: partial visibility, a failed `lsof` or `ps`, an
  uninspectable registry, an unverifiable holder. Unknown blocks disruptive operations exactly like busy.

## This session's own processes

The check excludes only processes established, by ancestry, to belong to this session: the holder process (the first
non-wrapper ancestor, or `--holder-pid`), all of its descendants, and the tool's own process chain. The number excluded
is printed. Nothing is excluded because of its name. If the holder cannot be determined, only the tool's own chain is
excluded, which may report the session's helper processes as busy: conservative, never optimistic.

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

## Interactive shells

A terminal tab whose shell sits in the checkout (for example the Terminal panel of an agent app, opened at the
project) is a process with its working directory there, and it is reported as busy. The evidence adds "no child
processes" when nothing runs under it. That hint is evidence, not a verdict: a person may run `git switch` in that
shell a second later. Before a disruptive step, tell the owner which shell was found and ask whether it is theirs and
idle, or whether they can move it out of the checkout. The tool has no switch to ignore it, and the owner's approval of
the operation does not by itself make the shell idle.

## What it cannot detect

- Agents or processes on other machines (remote branches and PRs are the only signals there).
- Processes of other users, unless run as root (reported as owner-complete visibility).
- A process that will write into the checkout but has no working directory or open file there yet.
- Activity between the check and your operation: chain the check with the command to narrow the window.
- On Windows, or without `lsof` and `ps`, processes at all: the verdict is unknown.
- Processes in another PID namespace (a container sharing the checkout through a bind mount): their PIDs mean nothing
  here, so a live holder inside a container can look dead from the host, and the reverse.
