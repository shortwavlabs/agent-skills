# Procedures

## Contents
- [Session lifecycle](#session-lifecycle)
- [Handing a claim to another session](#handing-a-claim-to-another-session)
- [Safe execution of disruptive operations](#safe-execution-of-disruptive-operations)
- [Common operations](#common-operations)
- [When the checkout is busy](#when-the-checkout-is-busy)
- [Manual coordination fallback](#manual-coordination-fallback)
- [Several machines](#several-machines)
- [Composition with other skills](#composition-with-other-skills)
- [Limitations](#limitations)

## Session lifecycle

1. **Start.** If the task will modify a shared working tree, run `check`, then `acquire --scope checkout`. Keep the
   claim ID and session token; write them into your handoff record.
2. **Work.** Edit, build and test normally. No claim per edit, no check before every test run.
3. **Renew** before the claim expires if the task continues (`--ttl` is in minutes, at most 1440).
4. **Release** when the task ends. If another session takes over, transfer the claim instead of releasing it (see
   below); the session token itself is never handed over as a substitute.

Read-only work (reviewing, running tests in your own build directory, reading logs) needs no claim.

## Handing a claim to another session

| Situation | What to do |
|---|---|
| You are handing over (compaction ahead, quota running out, switching agent or model) | `transfer --id I --session T --ttl 60`; put the claim ID and the printed transfer token in the handoff record. The successor runs `accept --id I --transfer-token X` and receives its own session token. The claim stays yours until then, and stays protected if your process ends first |
| The successor finds an open offer | `accept` before it lapses. Your earlier token stops working: renew with the new one |
| The previous session died without offering a transfer, and its token is in the handoff | `adopt --id I --session T` succeeds only once the holder is provably dead (process gone, PID reused or host rebooted). The claim's history records the recovery |
| The holder is alive, unknown, or on another host | Nothing takes the claim over. Ask the holder to transfer or release it, or wait for expiry and the owner's decision |
| No safe transfer is possible | Release it (or let it expire) and acquire anew; report the gap between the two claims in the handoff |

A token pasted from one session into another does not make the second session the holder: `renew` refuses it and
`check` reports the claim as someone else's.

## Safe execution of disruptive operations

1. **Authorization.** Establish what the risk model requires (the operational core): task scope for R1, a verified
   authorization or the owner's instruction for R2, owner reconfirmation for R3.
2. **Claim.** Hold an exclusive claim covering the operation's scope.
3. **Check.** `check --session <token> --disruptive` (or `--destructive` for deletions and discards): claims,
   processes, git state, uncommitted work. A passive process blocks unless the owner accepted that exact identity for
   this reversible operation (see [passive processes](activity-check.md#passive-processes-and-interactive-shells)).
4. **Preconditions.** Confirm what the operation assumes still holds (the branch exists, the tree is clean, the commits
   are pushed).
5. **Execute** within the authorized scope, chained with the check so nothing slips in between:
   `python3 $C check --session <token> --disruptive && git switch release/1.4`.
6. **Verify** the resulting state (`git status`, the branch, the build output).
7. **Release or renew** the claim.

Never: stash or overwrite another agent's work; switch branches under an active session; kill another session's
processes without authorization; bypass git's safety refusals (`--force`, `-D`, `--no-verify`); create a worktree
because the checkout is busy; treat owner approval as proof that an unknown concurrency condition is resolved.

## Common operations

| Operation | Scope | Notes |
|---|---|---|
| Switch branches, reset, rebase, merge, clean | `checkout`, `--disruptive` check | Uncommitted work blocks: preserve or attribute it first (`workspace-housekeeping`) |
| Commit in a shared checkout | `checkout` | The index and HEAD are shared even when the files are not |
| Rebuild a shared build directory | `checkout`, or `resource=build@<dir>` if independence is established | A build writing shared paths conflicts with other edits |
| Start or stop a long-lived dev server | `resource=<name>@<dir>` or `checkout` | Stopping someone else's server needs their session's consent or the owner's |
| Push to a branch you did not create | `branch=<name>` | Fetch and compare immediately before; a non-fast-forward refusal is investigated, never forced |
| Remove a worktree or delete build output | — | `workspace-housekeeping`: owner-approved manifest, in-use check, plain `git worktree remove` |
| A harness offers an isolated worktree | — | Decline unless the owner explicitly authorized it for this task or a scoped standing exception covers it |

## When the checkout is busy

A busy or unknown verdict normally leads to one of:
- **Defer:** wait for the claim to be released or the process to finish, then check again.
- **Hand off:** ask the owner, or the holding session, to release the claim or offer you a transfer.
- **Choose a non-conflicting alternative:** work that does not touch the shared tree (planning, reviewing, writing
  notes in your own files), or a narrower paths claim if its independence from the holder's work is established.

Report the holder's intent, agent and expiry, which the conflict output includes, so the owner can decide quickly.

## Manual coordination fallback

Where the tool reports claims or process inspection as unavailable (Windows, network filesystems, missing `lsof` or
`ps`), ordinary non-conflicting work continues. For a genuinely disruptive operation:
1. State the operation, its scope and its expected duration to the owner (and in the PR or handoff if other agents
   read them).
2. Wait for the owner's confirmation that no other session is using the checkout. This is coordination, not a lock.
3. Rely on git's own refusals and never force past them.
4. Report what you did and that no automated mutual exclusion was available.

## Several machines

Local claims are invisible to other machines, and nothing is pushed to share them. Across machines the signals are the
remote's own: an open PR or a recently pushed branch belongs to whoever opened or pushed it. Fetch and compare
immediately before pushing to a branch you did not create. These are signals, not distributed locks.

## Composition with other skills

- **`workspace-housekeeping`** owns worktree policy and removal, deletion manifests, backups and the authoritative
  in-use check. This skill's `scripts/path_in_use.py` is a generated, byte-checked copy of that check.
- **`agent-handoff`** (Phase 1c) carries the claim ID and transfer token across sessions, and verifies authorization
  references before a receiving agent acts.
- **`instruction-governance`** (Phase 1d) will put this skill's consultation triggers into each agent's instruction
  file and hold owner-approved standing exceptions.

## Limitations

- Claims bind only agents that use the tool; the registry is not a security boundary.
- A race window remains between any check and the operation for processes that do not participate.
- Cross-machine coordination and network filesystems are out of scope for the lock.
- Process visibility is limited to what `lsof` can read; other users' processes need root.
- Tested on macOS and Linux only; the Windows behaviour is a documented fallback (unknown), not a tested feature.
- Agents in containers sharing the checkout see different PID namespaces: inside a container claims are unavailable
  and the check reports unknown. Coordinate such setups manually.
- A shell that started two agents is recognised as shared only once one of them holds a claim; until then an explicit
  `--holder-pid` naming that shell would be accepted. Leave `--holder-pid` unset unless the automatic choice is wrong.
- A stray file in `.agent-state/claims/` other than a regular `.DS_Store` makes the registry uninspectable, so every
  acquisition reports unknown until the owner removes it. An unrecognized entry is never skipped silently.
