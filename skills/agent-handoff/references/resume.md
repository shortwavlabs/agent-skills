# Verified resumption

A handoff record tells you what the previous session believed. Resumption turns that into what you know now, before
you act on it.

## Contents
- [The eight steps](#the-eight-steps)
- [Reading `check` output](#reading-check-output)
- [Completion claims](#completion-claims)
- [Expensive work and running jobs](#expensive-work-and-running-jobs)
- [Unfinished qualification work](#unfinished-qualification-work)
- [When resumption stops](#when-resumption-stops)

## The eight steps

1. **Check the record.** `handoff.py check`. An invalid record (exit 2) is read for context only: nothing in it is
   relied on.
2. **Compare with the repository.** Every `drift:` line is investigated: read new commits, find out why the branch or
   working tree differs, open the PR.
3. **Re-verify completion claims** you will build on (see below). Until then they are REPORTED.
4. **Check jobs and expensive results.** Running jobs are left alone; finished ones are read, not rerun.
5. **Take over the claim.** `coordination.py accept` with the recorded transfer token. If the claim is gone, acquire
   anew before any disruptive step. If the holder is alive and no transfer was offered, ask it or the owner.
6. **Verify authority.** `handoff.py verify-auth --action <action>` for the next operation above R1. Only `verified`
   grants authority, and only for that action. Ask the owner once about unknown references, including every quoted
   owner instruction. R3 is reconfirmed every time.
7. **Re-check the first pending step's preconditions,** then continue with it.
8. **Refresh the record** at your next milestone with `new --supersede`.

## Reading `check` output

| Line | Meaning | Do |
|---|---|---|
| `drift: recorded repository …, this checkout is …` | Another repository, whatever its remote is called | Stop: this record is not for this repository |
| `drift: recorded in checkout …` | Another checkout or machine | Local artifacts and jobs may differ; check each |
| `unknown: git status failed` (or other `unknown:`) | Something could not be inspected | Treat it as unknown, never as clean or ended; fix the cause and check again |
| `drift: the uncommitted content of … changed` | Same paths, other content | Find out who changed it before building on it |
| `drift: N commits since the record` | Someone (maybe the previous session) committed after writing it | Read them; re-verify Done items that depend on them |
| `drift: recorded HEAD … does not exist here` | Rewritten history, or a commit not fetched | Fetch; if still missing, treat the record's state as unknown and ask |
| `drift: recorded on branch X, the checkout is on Y` | Wrong branch, or the work moved | Do not switch blindly: check who uses the checkout (`development-coordination`) |
| `drift: working tree was … now …` | Uncommitted changes appeared or vanished | Find out whose they are before touching them |
| `drift: artifact … is missing` / `changed` | A recorded output is gone or differs | Done items resting on it become UNKNOWN; regenerate only if cheap, otherwise ask |
| `drift: job … has ended` | It finished or died after the record | Read its log and outputs before deciding anything |
| `note: job … is still running` | PID and start time match | Leave it; do not start a second copy |
| `unknown: job …: whether it still runs cannot be established` | Its identity cannot be read | Do not assume it ended; look where it runs |
| `drift: … readable by other users` | The record may expose a transfer token | `chmod 600` the record |
| `drift: claim … is no longer active` | Released, archived or never made here | Acquire anew before disruptive steps |
| `drift: … template placeholder` | The record was never completed | Treat the section as missing |

## Completion claims

- **Cheap to re-check** (a unit test run, a validator, `git status`): re-run it, then treat the claim as VERIFIED by
  you.
- **Expensive** (a long experiment, paid CI, a sweep): do not rerun by default. Confirm the recorded artifacts' digests
  and, where recorded, the inputs' digests and the commit. Unchanged identities make the recorded result OBSERVED
  evidence for that identity; changed ones make it stale.
- **Unverifiable** (a remote result you cannot open): keep it REPORTED and say so in your own record.
- A claim that turns out false is a finding: report it to the owner, correct the record, and do not build on it.

## Expensive work and running jobs

Never auto-restart, duplicate or terminate a job because a record lists it. A job listed as running may have finished,
crashed or be running elsewhere; a job you start again may double the cost or corrupt shared outputs. If a running
job blocks your next step, wait, work on something independent, or ask the owner. Stopping another session's job
needs the owner's authorization.

## Unfinished qualification work

When the record names frozen criteria (by digest and commit), check that the criteria file still has that digest
before running anything. If it changed, the qualification is not resumable as recorded: report it and ask. Never
change frozen criteria to make a result pass; an amendment needs owner approval (`research-provenance`, Phase 2).

## When resumption stops

Stop and ask the owner when: the record is invalid; HEAD is unrelated to the recorded one; an artifact a Done item
depends on is missing and expensive to regenerate; the claim's holder is alive and offered no transfer; or the next
step needs authority that does not verify.
