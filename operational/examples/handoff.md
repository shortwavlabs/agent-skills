# Handoff: Reconcile the RFC with the owner's decisions

Version: 1
Created: 2026-11-27T18:40:00Z
Author: example-agent / example-model / 4b1f0c9e6a2d4e7f
Repository: github.com/example/repo
Branch: rfc/example
HEAD: 0123456789abcdef0123456789abcdef01234567
Upstream: in sync
Working tree: clean
PR: https://github.com/example/repo/pull/3
Claim: 20261127T184000Z-7f3a1c2b
Transfer: none
Supersedes: none

## Goal
Record the owner's decisions in the RFC and prepare it for final review.

## State
Revision 2 committed and pushed; CI not yet read on the final head.

## Done
- [VERIFIED] The repository validator passes; method: python3 scripts/validate_skills.py exit 0; artifact: commit 0123456789abcdef0123456789abcdef01234567; at: 2026-11-27T19:40:00Z
- [OBSERVED] CI was green on the previous head (not re-checked after the last push)

## Pending
1. Read CI once on the final head; if it passes, mark the PR ready. Do not merge.

## Decisions and rejected approaches
- Authorization references are limited to the approved sources; owner comments were rejected because collaborators can edit them.

## Blockers and decisions needed
- None.

## Authorizations in force
```json
[
  {
    "level": "R2",
    "scope": "Push feature branches of this repository to origin and open draft PRs",
    "source": "standing",
    "by": "github:example-owner",
    "ref": "ops/authorizations.json@0123456789abcdef0123456789abcdef01234567#push-feature-branches",
    "granted": "2026-11-27T18:00:00Z",
    "expires": "2027-06-30T00:00:00Z"
  },
  {
    "level": "R2",
    "scope": "Mark the PR ready for review once CI passes",
    "source": "owner-session",
    "by": "github:example-owner",
    "ref": "the previous agent's session of 2026-11-27",
    "quote": "mark it ready once CI passes",
    "granted": "2026-11-27T18:05:00Z",
    "expires": "task-end"
  }
]
```

## Artifacts
```json
[
  {"type": "commit", "id": "0123456789abcdef0123456789abcdef01234567"},
  {"type": "pr", "id": "https://github.com/example/repo/pull/3"}
]
```

## Running processes and jobs
- None.

## Verification
The validator and the RFC link check ran on the committed head. CI has not been read on the final head.

## Assumptions and limitations
- [INFERRED] No other agent uses this checkout (premises: the activity check reported only this session's processes)
- [UNKNOWN] Whether the owner has started the final review

## Resume
1. Check this record against the repository (branch, HEAD, upstream, working tree, PR state).
2. Verify the standing authorization at run time (it is only unverified until then); ask the owner once about the session
   authorization, which another agent cannot verify.
3. Continue with Pending item 1.
