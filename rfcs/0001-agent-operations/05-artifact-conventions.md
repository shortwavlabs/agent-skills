# 5. Shared artifact conventions and the coordination protocol

Part of [RFC 0001: Operational Skills](README.md). Status: **approved** (owner decisions D8 and D14; revision 3).
protocol's details, the reference format and the standing-authorizations format are new in revision 2, for owner
review.

**Which formats are normative when.** Phase 1a defines the formats the Phase 1 skills need, in machine-readable form,
in the top-level `operational/` directory: verification records, authorization references, standing authorizations,
claims, handoff records and scenarios. Those definitions are then the single normative source, and this document
describes them. The other formats here (run manifests, amendments, budgets, artifact manifests, release decisions,
the debt register) remain **proposals** until the phase that implements their skill. The JSON examples in this
document use placeholders and are illustrations, not test fixtures.

## Contents
- [Format rule](#format-rule)
- [Location rule](#location-rule)
- [Evidence labels and verification records](#evidence-labels-and-verification-records)
- [Authorization references](#authorization-references)
- [Standing authorizations](#standing-authorizations)
- [Claims and the coordination protocol](#claims-and-the-coordination-protocol)
- [Advisory coordination versus enforcement](#advisory-coordination-versus-enforcement)
- [Handoff record](#handoff-record)
- [Generated copies of shared files](#generated-copies-of-shared-files)
- [Canonical policy blocks](#canonical-policy-blocks)
- [Run manifest (proposal, Phase 2)](#run-manifest-proposal-phase-2)
- [Amendment record (proposal, Phase 2)](#amendment-record-proposal-phase-2)
- [Resource budget](#resource-budget)
- [Artifact provenance manifest (proposal, Phase 3)](#artifact-provenance-manifest-proposal-phase-3)
- [Release decision record (proposal, Phase 3)](#release-decision-record-proposal-phase-3)
- [Debt register (proposal, Phase 3, provisional)](#debt-register-proposal-phase-3-provisional)
- [Versioning the formats](#versioning-the-formats)

## Format rule

| Use | When | Why |
|---|---|---|
| **JSON** | A tool reads, compares or validates the record: claims, verification records, standing authorizations, scenarios, run manifests, budgets, artifact manifests | Standard-library parsing. Anthropic's long-running-agent harness found models less likely to overwrite JSON state inappropriately than Markdown ([source](02-ecosystem-assessment.md#session-continuity-and-compaction)) |
| **Markdown with `Key: value` header lines and fixed headings** | People read the record and agents write prose in it: handoffs, release decisions, amendments, the debt register | Readable in review; header lines and headings are checkable with regular expressions |
| **A JSON block inside a Markdown record** | One section must be exact, such as a handoff's authorizations | Precision where authority is at stake, prose elsewhere |
| **Never YAML** for operational records | — | No standard-library parser; implicit typing. Agent Skills frontmatter is unchanged and out of scope |

Every record carries `kind` and `version` (JSON) or a `Version:` header line (Markdown).

## Location rule

| Where | What | Retention |
|---|---|---|
| **`.agent-state/` at the checkout root**, self-ignoring | Claims and the claim registry lock; handoff records; activity-check output | Claims are ephemeral. Handoffs are valuable. See below |
| **`ops/`**, committed (or the project's declared override) | Standing authorizations, budget, debt register, release decisions, amendments | Normal git history |
| **Next to the results they describe** | Run manifests | The project's research layout decides |
| **Private storage** (`workspace-housekeeping`) | Anything that must outlive the machine but must not be published, including important handoffs | Verified backup |
| **PR description** | A public-safe status summary taken from a handoff | Public: nothing private |

### `.agent-state/` layout and exclusion

```text
.agent-state/
  .gitignore        contains "*": ignores everything here, itself included
  claims.lock       the claim registry lock (an empty file)
  claims/<id>.json  live claims
  claims/stale/     claims taken over from dead holders, kept until reviewed
  handoffs/<branch>.md
```

- **Sandbox-compatible exclusion.** The agent creates `.agent-state/.gitignore` containing `*` before writing anything
  else there. This needs no write to `.git/` (read-only in Codex's default sandbox) and no change to any tracked file.
  Tested: with a read-only `.git`, `git status` shows nothing and `git check-ignore -v` attributes every path to
  `.agent-state/.gitignore`; with a writable `.git` (staging needs one), `git add -A` stages nothing.
- **Ignored is not disposable.** `git clean -x` (and `-X`) deletes the directory. Handoffs are not caches: no agent
  runs `git clean -x` in a checkout that may hold them, and housekeeping classifies them as evidence until reviewed.
- **Claims are ephemeral.** A released claim is deleted by its holder. Stale claims are moved to `claims/stale/`, not
  deleted, until reviewed.
- **Handoffs are valuable.** They are never deleted automatically. The preservation path: a public-safe summary in
  the PR description; a copy in the owner's private backup (`workspace-housekeeping`); or, in a **private**
  repository whose owner chooses it, a committed `ops/handoffs/` directory that is not ignored. Never force-add an
  ignored file, use index plumbing or rename files to get them committed.
- **Public repositories never receive** private coordination records, credentials, session transcripts, host names,
  process lists or personal paths.

## Evidence labels and verification records

| Label | Precise meaning |
|---|---|
| **VERIFIED** | The recorder checked the claim itself, at a recorded time, with a repeatable method, against the source of truth for that claim, and identifies the artifact it checked (commit, tree or file digest, PR or CI run). It holds for that artifact identity. A reader re-verifies when the identity has changed |
| **OBSERVED** | The recorder saw it directly (output, a log line, a page) but did not check it against the source of truth, or the source may have changed since |
| **REPORTED** | Someone else asserted it (another agent, a person, a document, a handoff), and the recorder did not re-check it |
| **INFERRED** | Derived by reasoning from premises, which are listed with their own labels |
| **UNKNOWN** | Not established, including when a check could not run or ran with partial visibility |

Rules:
- R1 and higher decisions rest only on VERIFIED facts, or treat what is missing as unsafe.
- **Verification does not transfer.** A receiving agent reads a VERIFIED item in a handoff as REPORTED until it
  re-checks it or confirms that the artifact identity is unchanged.
- **Identity is not state.** Verifying an artifact's identity (a commit, a digest) does not verify the mutable state
  that refers to it: a branch tip, a PR's status, a working tree, a running process or an authorization's current
  validity is checked again when relied on.
- **A digest verifies identity or integrity only.** A matching SHA-256 shows the bytes are the expected bytes. It does
  not show that they are correct, how they were produced, or that anyone authorized their use.
- Archival integrity and reproducibility are separate claims in separate fields (`workspace-housekeeping` principle 8).

A **verification record** carries the claim, the method, the artifact identity and the time:

```json
{
  "kind": "verification",
  "version": 1,
  "claim": "The repository validator passes",
  "label": "VERIFIED",
  "method": "python3 scripts/validate_skills.py exited 0 and printed ALL CHECKS PASSED",
  "artifact": { "type": "commit", "id": "<40-hex commit>" },
  "verified_at": "2026-11-27T19:40:00Z",
  "by": "<agent product>"
}
```

`artifact.type` is one of `commit`, `tree`, `file` (with `sha256`), `url`, `pr`, `ci-run`. In Markdown records the
same fields appear inline: `- [VERIFIED] <claim>; method: <...>; artifact: <identity>; at: <time>`.

## Authorization references

An authorization reference lets another agent check where an authorization came from
([rules](04-risk-and-authorization.md#authorization-across-a-handoff)).

```json
{
  "level": "R2",
  "scope": "Push feature branches of this repository to origin and open draft PRs",
  "source": "standing",
  "by": "github:<owner login>",
  "ref": "ops/authorizations.json@<40-hex commit>#push-feature-branches",
  "granted": "2026-11-27T19:00:00Z",
  "expires": "2027-06-30T00:00:00Z"
}
```

References point only to the approved sources of authorization
([04](04-risk-and-authorization.md#sources)):

| `source` | `ref` form | Verifiable by another agent? |
|---|---|---|
| `standing` | `<path>@<commit>#<id>`, naming an entry in the designated authorizations file (cost-only entries included) | Yes: within the [trust boundary](04-risk-and-authorization.md#trust-boundary-for-standing-authorizations) |
| `owner-session` | a locator for the session in which the owner gave the instruction; may carry a `quote` | **No.** For any other agent its status is *unknown*: ask the owner once |

Host-recorded PR approvals and merges (D14) are not a separate source: they are the evidence behind a `standing` entry
(its `approved_in`, checked against the host's record of that PR). Any other `source` value is invalid. Comments are not references:
collaborators with write access can edit other users' comments.

**Statuses.** A structurally valid reference is never treated as authenticated or authorized because it matches the
format.

| Status | Meaning | Who can report it | Grants authority? |
|---|---|---|---|
| **invalid** | Malformed (unknown source, missing or malformed `ref`, `scope`, `level` or `by`, a level other than R1 or R2, contradictory or malformed dates), inside an invalid record, or pointing to a commit or entry that does not exist | Structural checks and runtime checks | No |
| **unverified** | Structurally valid; nothing about its authenticity or applicability has been checked | Structural checks (Phase 1a) | No |
| **verified** | Authentic and applicable: every condition of the [trust boundary](04-risk-and-authorization.md#trust-boundary-for-standing-authorizations) holds for this operation, now | Runtime checks only (Phase 1c) | **Yes** |
| **inapplicable** | Authentic or not, it does not cover this use: expired, revoked, out of scope, changed since approval, not approved by an owner identity, or from an untrusted repository | Runtime checks only | No |
| **unknown** | Cannot be established now: offline, host records unavailable, or an `owner-session` authorization the receiving agent cannot verify | Runtime checks only | No: ask the owner once |

Phase 1a's validator reports only *invalid* or *unverified*. The expected runtime behavior for fabricated, nonexistent,
expired, revoked, changed and quoted authorizations is defined as fixtures in `operational/fixtures/` (Phase 1a), for
the runtime checks of Phase 1c to satisfy; Phase 1a does not perform those checks.

## Standing authorizations

Committed in `ops/authorizations.json` (or the file the canonical policy names), and trusted only within the
[trust boundary](04-risk-and-authorization.md#trust-boundary-for-standing-authorizations):

```json
{
  "kind": "authorizations",
  "version": 1,
  "authorizations": [
    {
      "id": "push-feature-branches",
      "level": "R2",
      "operations": "Push feature branches of this repository to origin and open draft PRs",
      "granted_by": "github:<owner login>",
      "approved_in": "https://github.com/<owner>/<repo>/pull/<n>",
      "expires": "2027-06-30T00:00:00Z"
    },
    {
      "id": "nightly-benchmarks",
      "level": "R2",
      "operations": "The nightly benchmark workflow as committed, up to USD 10 per run",
      "cost_only": true,
      "granted_by": "github:<owner login>",
      "approved_in": "https://github.com/<owner>/<repo>/pull/<n>",
      "expires": "until revoked"
    }
  ]
}
```

- `level` is R1 or R2, never R3. A `cost_only` entry authorizes spending alone, never publication or deletion.
- Existing authorized workflows that cost money (D9) are entries here; the budget file only holds thresholds.
- **No owner list here.** Owner identities and trusted repositories are declared only in the canonical policy (D14);
  a repository cannot establish its own owner identity.
- **Bound to approval.** `approved_in` names the PR. The revision the owner approved or merged comes from the host's
  record for that PR, never from this file (an entry cannot name the commit that contains it). The entry is covered
  only if its content at that revision equals its content at the referenced commit and on the current default branch;
  an entry changed after approval is not covered until approved again.
- **Revocation** is removal: an entry that no longer appears, unchanged, on the current default branch is revoked, and
  older commits that still contain it grant nothing. Reintroducing it needs fresh owner approval.
- **Hosts.** `approved_in` accepts GitHub PR URLs: the initial capability, not an architectural restriction.

## Claims and the coordination protocol

Owner: `development-coordination` (Phase 1b implements it). The protocol serializes conflict checking and acquisition
for **cooperating** agents, without a daemon, database or service.

### Claim

```json
{
  "kind": "claim",
  "version": 1,
  "id": "20261127T184000Z-7f3a",
  "holder": {
    "agent": "<agent product>",
    "session": "<random token generated when the claim is created>",
    "host": "<host name>",
    "pid": 41237,
    "process_start": "<start time of that process>"
  },
  "scope": { "type": "checkout", "value": "." },
  "mode": "exclusive",
  "intent": "Commit the reconciled RFC and push it",
  "created": "2026-11-27T18:40:00Z",
  "expires": "2026-11-27T19:40:00Z",
  "handoff": ".agent-state/handoffs/rfc-agent-operations.md"
}
```

- `holder.pid` is the agent's long-lived process, not the short-lived shell that ran the tool. `process_start`
  defends against **PID reuse**: a holder is alive only if a process with that PID exists **and** started at that
  time. `session` distinguishes two sessions of the same agent.
- **Fail closed on identity.** If the tool cannot determine the agent's long-lived process, it records `pid` and
  `process_start` as `null`. Other agents then treat the holder as *unknown*, never *dead*, so a claim can never be
  taken over merely because its holder was recorded wrongly. How the long-lived process is found is settled in
  Phase 1b.
- `scope.type`: `checkout` (anything that touches the index, HEAD or the whole working tree: commit, switch, reset,
  merge, stash, clean), `branch` (operations on a ref without the working tree: push, PR updates), `paths` (a list of
  path globs being edited), `resource` (a build directory, port or device; may name a `path`).
- `mode`: `exclusive` conflicts with every overlapping claim; `shared` conflicts only with overlapping exclusive
  claims.

### Overlap rules

| | `checkout` | `branch` X | `paths` P | `resource` R |
|---|---|---|---|---|
| **`checkout`** | overlap | overlap | overlap | overlap |
| **`branch` Y** | overlap | if X = Y | no | no |
| **`paths` Q** | overlap | no | if P and Q may share a file (compared conservatively on their literal prefixes) | if R has a path inside Q |
| **`resource` S** | overlap | no | if S has a path inside P | if R = S |

### Holder states

| State | Meaning | Effect on an overlapping request |
|---|---|---|
| **live** | Same host; the PID exists with the recorded start time | Conflict while unexpired |
| **expired-held** | Live, but past `expires` | Still a conflict: the holder is active. Report it; the holder renews or releases, or the owner decides |
| **dead** | Same host; the recorded PID is gone, its start time differs (reused), or the host has rebooted since | Stale **only once also expired**: then move it to `claims/stale/`, record it, continue. Until expiry it remains a conflict |
| **unknown** | Another host, no recorded PID, or the process table cannot be read | Conflict while unexpired; after expiry, **expired-unknown**: still a conflict, and the owner may release it (ask once) |

### Procedure

1. Ensure `.agent-state/` exists with its `.gitignore`.
2. **Enter the critical section:** open `.agent-state/claims.lock` and take an exclusive advisory lock
   (`fcntl.flock`), non-blocking, retried for a few seconds. If it stays busy, report "registry busy". If locking is
   not supported, claims are **unavailable**: report unknown, and do not pretend to hold a claim.
3. Read every claim and determine each holder's state.
4. Compare the request with every claim that overlaps in an incompatible mode. Any live, expired-held, unknown or
   expired-unknown holder is a conflict, and so is a dead holder's claim that has not expired: release the lock and
   report holder, intent and state. Claims that are both expired and held by a dead holder are moved to
   `claims/stale/`.
5. Write the new claim to a temporary file in `claims/`, flush it, rename it into place, and **leave the critical
   section**. The lock is held for milliseconds, never for the operation.
6. **Run the activity check after acquiring:** every process's working directory **and** open files under the scoped
   paths (`path_in_use.py`), plus git in-progress state (index lock, merge, rebase, cherry-pick, bisect). A busy or
   unknown result means the operation does not start; release or keep the claim and report.
7. **Revalidate immediately before any destructive step**, chained with it, as `workspace-housekeeping` does for
   worktree removal.
8. **Renew** and **release** inside the same critical section, after checking that `holder.session` matches.

**Failure modes of the lock.** A crashed holder releases the lock automatically (the kernel drops it with the file
descriptor), so the lock itself never goes stale; only claims can. On network filesystems advisory locks may be
local-only, so claims there are unreliable and reported as such. On platforms without `fcntl` (Windows), claims are
unavailable until Phase 1b settles a substitute. None of these failures is ever reported as "no conflict".

### Several machines

Local claims are invisible to other machines, and nothing is pushed to share them (that would publish private
state). Across machines the signals are the remote's own: an open PR or recently pushed branch belongs to whoever
opened or pushed it; fetch and compare immediately before pushing to a branch you did not create; git refuses
non-fast-forward pushes, and that refusal is investigated, never forced.

## Advisory coordination versus enforcement

| Mechanism | Who it binds | Strength |
|---|---|---|
| Claims and the registry lock | Agents that use the coordination tool | **Advisory**: an uncooperative agent or external process ignores them |
| Activity check (`path_in_use.py`, git state) | Detects any process the check can see | **Detection only**: it prevents nothing, and partial visibility is reported as unknown |
| git's own refusals (non-fast-forward push, worktree protections, unmerged branch deletion) | Everyone using git without force | **Enforced** by git, unless someone forces it (which the family forbids) |
| Server-side branch protection and required reviews | Everyone pushing to the remote | **Enforced** by the server |
| Owner-installed harness deny rules and hooks | That agent | **Enforced** to the extent the harness guarantees it (Codex calls its hooks a guardrail) |
| Operating-system permissions | Other users' processes | **Enforced** by the OS |

## Handoff record

Owner: `agent-handoff` (Phase 1c). Location: `.agent-state/handoffs/<branch>.md`. Refreshed at milestones and at the
end of a session with unfinished work. Phase 1a defines its required header lines and headings.

````markdown
# Handoff: <one-line task title>

Version: 1
Created: 2026-11-27T18:40:00Z
Author: <agent product> / <model> / <session id, if the agent has one>
Repository: <remote name or URL>
Branch: <branch>
HEAD: <full commit id>
Upstream: in sync | ahead <n> | behind <n> | not pushed
Working tree: clean | dirty (listed under State)
PR: <URL> | none
Claim: <claim id> | none
Supersedes: <Created time of the previous record> | none

## Goal
What the owner asked for, in one paragraph.

## State
One line of status, then the dirty files, if any, and why they are uncommitted.

## Done
- [VERIFIED] Validator passes; method: python3 scripts/validate_skills.py exit 0; artifact: commit <id>; at: <time>
- [OBSERVED] CI run green on the previous push (not re-checked after the last commit)

## Pending
1. Ordered next steps. The first one can be started without reading anything else.

## Decisions and rejected approaches
- Decisions taken, with the reason. Approaches rejected, with the evidence.

## Blockers and decisions needed
- Decisions only the owner can make, each phrased as a question with the options.

## Authorizations in force
```json
[
  { "level": "R2", "scope": "...", "source": "standing", "by": "github:<owner login>",
    "ref": "ops/authorizations.json@<40-hex commit>#push-feature-branches", "granted": "...", "expires": "..." }
]
```

## Running processes and jobs
- <pid or job URL>: <command>, started <time>, output at <path>, stop with <command>

## Verification
What was tested, with which command and result, and what was not tested.

## Assumptions and limitations
- [INFERRED] ... (premises: ...)
- [UNKNOWN] ...

## Resume
1. Check this record against the repository (branch, HEAD, upstream, working tree, PR state).
2. Verify the authorization references you need; ask once for any whose status is unknown.
3. Re-verify what the next step depends on, then continue with Pending item 1.
````

## Generated copies of shared files

Owner: the repository (Phase 1a). One authoritative source; copies installed with each skill
([D4](README.md#d4-shared-operational-core)). A copy is the generator's exact output:

```markdown
<!-- Generated from operational/core.md (revision 1, sha256 <64-hex digest of the source>). Do not edit this copy: change the source and regenerate. -->

...the source text, unchanged...
```

The check reports a copy as **missing**, **edited** (bytes differ from the output for the recorded revision),
**outdated** (generated from an older revision or digest), or **unlisted** (a generated header in a file the manifest
does not list).

## Canonical policy blocks

Owner: `instruction-governance` (Phase 1d). Adapters that cannot import the canonical policy carry a marked copy:

```markdown
<!-- policy:begin id=git-workflow rev=4 sha256=<digest of the canonical block> -->
...the canonical text, unchanged...
<!-- policy:end id=git-workflow -->
```

The audit tool changes nothing outside the markers, refuses to write when markers are missing, duplicated or
unbalanced or when the file changed since the audit, and writes only the exact diff the owner approved
([requirements](03-responsibility-matrix.md#instruction-governance)).

## Run manifest (proposal, Phase 2)

Owner: `research-provenance`. One per run, written **before** the run starts and completed when it ends.

```json
{
  "kind": "run",
  "version": 1,
  "id": "20261127T190000Z-sweep-a",
  "purpose": "exploratory | confirmatory | qualification",
  "question": "<what the run decides>",
  "source": { "repository": "<name>", "commit": "<full id>", "dirty": false, "verified": true },
  "command": ["python3", "tools/run_sweep.py", "--config", "configs/sweep-a.json"],
  "config": [{ "path": "configs/sweep-a.json", "sha256": "<digest>" }],
  "inputs": [{ "path": "data/heldout/", "tree_sha256": "<digest>", "role": "held-out", "opened": false }],
  "outputs_class": "evidence | expensive-reproducible | disposable-cache",
  "toolchain": { "os": "<name version>", "python": "<version>", "compiler": "<name version>", "flags": "-O2" },
  "numerics": { "precision": "float64", "seed": 1234, "threads": 8, "tolerance": "<declared before the run>" },
  "criteria": { "path": "criteria/sweep-a.md", "sha256": "<digest>", "commit": "<id>", "frozen_before_run": true },
  "estimate": { "cpu_hours": { "low": 5, "high": 7 }, "wall_hours": { "low": 1, "high": 1.5 }, "basis": "<pilot>" },
  "stop": { "max_wall_hours": 2, "early_stop": "first gate failure" },
  "authorization": "<authorization reference, if the run is R2>",
  "cost": { "elapsed_s": null, "cpu_s": null, "billed_ci_minutes": null, "ci_usd": null, "api_usd": null },
  "status": "planned | running | completed | failed | aborted",
  "outputs": [],
  "result": { "verdict": "pass | fail | inconclusive", "summary": null, "evidence": [] }
}
```

A qualification run requires a clean, committed source and frozen criteria. An exploratory run may be dirty, labelled
as such, and keeps *unknown* provenance even if its code is committed later. Failed and aborted runs keep their
manifests.

## Amendment record (proposal, Phase 2)

Owner: `research-provenance` (criteria and frozen evidence) and `release-governance` (release gates).

```markdown
# Amendment 3: <title>

Version: 1
Amends: criteria/sweep-a.md (revision 2 -> 3)
Before: sha256 <digest>
After: sha256 <digest>
Approved: <authorization reference to the owner's approval>
Applies to: runs started after this amendment's commit

## Reason
## Effect on existing results
Earlier runs keep their original criteria and verdicts; any re-evaluation is labelled as such.
```

## Resource budget

Owner: `resource-budgeting` (Phase 2; this format is a proposal until then). Thresholds are configurable and
owner-approved. **The `per_operation` values below are the owner's initial workspace values, not universal
defaults.** `material_overrun` (1.25) is approved as a material-deviation threshold that requires reassessment; it
never permits exceeding an authorized hard limit.

```json
{
  "kind": "budget",
  "version": 1,
  "scope": "workspace",
  "approved": { "by": "github:<owner login>", "ref": "<path>@<commit>" },
  "per_operation": {
    "cpu_hours": 8,
    "wall_hours": 2,
    "paid_gpu_usd": 0,
    "ci_usd": 2,
    "api_usd": 5,
    "storage_gib": 20,
    "network_gib": 5
  },
  "material_overrun": 1.25
}
```

Design requirements (D9):
- **Classification, not permission.** Reaching a threshold makes an operation R2; it then needs a verified authorization or the owner's instruction.
- **Existing authorized workflows** are respected. The committed CI is the project's normal cost and is not
  re-approved on every push; a workflow that reaches a threshold by itself is covered by a cost-only standing
  authorization. Changing a workflow's triggers or matrix is estimated as an incremental cost.
- **Money, not minutes, for CI.** Estimates keep elapsed minutes, billed minutes (per runner type) and USD separate,
  using the provider's current price list with its date.
- **No implicit paid GPU:** any paid GPU cost is R2.
- **Cumulative.** Related operations (the same task, PR or run series) are summed, so splitting a task into smaller
  runs cannot circumvent a threshold.
- **Uncertainty.** Each estimate has a low and a high value and its basis (a pilot, a scaling assumption). Decisions
  compare the **high** value, accumulated, with the threshold.
- **Stop conditions** are declared before launch (maximum wall time, maximum spend, early-termination rule). When
  actuals exceed the high estimate by the material-overrun factor, or would cross a threshold, the job stops or the
  agent seeks authorization. The factor triggers reassessment; it is never permission to exceed an authorized hard
  limit on spending, compute, storage or execution time.

## Artifact provenance manifest (proposal, Phase 3)

Owner: `release-governance`. `workspace-housekeeping` keeps preservation of the bytes and its preserved-binary entry,
which this extends.

```json
{
  "kind": "artifact",
  "version": 1,
  "class": "development | audition | release-candidate | release",
  "subject": [{ "name": "Example.vst3", "sha256": "<executable digest>", "tree_sha256": "<whole-bundle digest>" }],
  "version_label": "1.4.0-rc.2",
  "source": { "repository": "<name>", "commit": "<full id>", "dirty": false, "verified": true, "tag": "v1.4.0-rc.2" },
  "build": { "builder": "ci:<run URL> | local:<machine label>", "command": ["cmake", "--build", "build"], "configuration": "Release" },
  "dependencies": [{ "name": "<external asset>", "uri": "assets/<sha256>/<name>", "sha256": "<digest>" }],
  "signing": { "signed": true, "identity": "<certificate name>", "notarized": true },
  "attestation": "<URL of a build attestation, or null>"
}
```

Field names follow SLSA provenance and in-toto loosely. This is not an attestation and must not be presented as one;
a digest here identifies the bytes, it does not prove they are correct or authorized. When signing changes the bytes,
the candidate is the signed artifact.

## Release decision record (proposal, Phase 3)

Owner: `release-governance`. Committed (default `ops/releases/<version>.md`). Header lines: `Version`, `Candidate`,
`Source commit` (with its verification), `Decision` (release, do not release, release with waivers), `Decided` (an
authorization reference to the owner's decision). Sections: Artifacts (name, SHA-256, provenance manifest), Acceptance
gates (criterion as frozen before the candidate, result pass / fail / waived / not run, evidence), Waivers (one per
failed or unrun gate, owner-approved, with the tracking debt record), Known issues, Rollback, Publication. A candidate
that fails or skips any gate is not releasable without a waiver for that gate.

## Debt register (proposal, Phase 3, provisional)

Owner: `technical-debt-management`, if Phase 3 decides to implement it. One committed register per project (default
`ops/DEBT.md`), entries with ID, kind (workaround, deferred decision, known defect, limitation, test gap), status, scope
and version pins, risk, owner, resolution criterion, reassessment trigger and links; code markers (`DEBT-007`) checked
against the register. An entry is written only when a compromise outlives the current PR.

## Versioning the formats

- Removing or renaming a field increments `version`. Readers accept the versions they know and reject the others as
  **incompatible**; they never guess.
- Adding an optional field does not increment `version`.
- Phase 1a's validator checks example records and fixtures against the definitions in `operational/`.
