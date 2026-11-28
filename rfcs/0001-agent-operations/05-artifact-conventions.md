# 5. Shared artifact conventions

Part of [RFC 0001: Agent Operations](README.md). Status: **draft for owner review**.

These are **proposals**. No template here is implemented yet. Each one moves into the skill that owns it, in the
phase that implements that skill (see the [roadmap](07-roadmap.md)).

## Contents
- [Format rule: JSON or Markdown](#format-rule-json-or-markdown)
- [Location rule](#location-rule)
- [Evidence labels](#evidence-labels)
- [Handoff record](#handoff-record)
- [Claim](#claim)
- [Run manifest](#run-manifest)
- [Amendment record](#amendment-record)
- [Resource budget](#resource-budget)
- [Artifact provenance manifest](#artifact-provenance-manifest)
- [Release decision record](#release-decision-record)
- [Debt register](#debt-register)
- [Canonical policy blocks](#canonical-policy-blocks)
- [Versioning the formats](#versioning-the-formats)

## Format rule: JSON or Markdown

| Use | When | Why |
|---|---|---|
| **JSON** | A script reads, compares or validates the record: claims, run manifests, budgets, artifact provenance, scenarios | Python's standard library parses it, so checks need no dependencies. The repository's validator is standard-library only and already hand-parses YAML because no YAML library is available. Anthropic's long-running-agent harness also found that models are less likely to overwrite JSON state inappropriately than Markdown ([source](02-ecosystem-assessment.md#session-continuity-and-compaction)). |
| **Markdown with fixed headings and `Key: value` header lines** | People read the record and agents write prose in it: handoffs, release decisions, debt registers, amendments | Readable in review and in PRs. Fixed headings and flat header lines keep it machine-checkable with a regular expression, the way the validator already checks frontmatter. |
| **Not YAML** | — | No standard-library parser, and its implicit typing and indentation rules are a source of silent errors. |

Every record carries `kind` and `version` (JSON) or a `Version:` header line (Markdown), so formats can evolve.

## Location rule

| Where | What | Why |
|---|---|---|
| **`.agent-state/` at the checkout root**, excluded from git | Claims, handoff records, activity-check output | Local to the machine and checkout. Every agent working in the checkout sees it, and it is never committed or pushed. It is outside `.git/` because Codex's default sandbox makes `.git` read-only ([source](02-ecosystem-assessment.md#enforcement-versus-advice)). Excluded through `.git/info/exclude` (a one-time set-up that changes no tracked file) or through `.gitignore` (an owner decision). |
| **Committed, in a project records directory** (proposed default `ops/`, overridable in the project's instruction file) | Budget, debt register, release decision records, amendment records | Shared with everyone who clones the project, reviewed through PRs. |
| **Next to the results they describe** | Run manifests | The project's research layout decides. The skill never imposes one. |
| **Private backup** (see `workspace-housekeeping`) | Anything that must survive the machine but must not be published | A record committed to a public repository is published (an R2 operation). |
| **PR description** | A public-safe status summary taken from the handoff | Lets a different machine or person resume. Write nothing private there. |

Handoff records and claims stay local by default because they routinely contain private paths, host names, process
lists and unreviewed plans.

## Evidence labels

Every factual statement in a handoff record, release decision or experiment conclusion carries one label:

| Label | Meaning |
|---|---|
| **VERIFIED** | Checked against the source of truth in this session. The check is named: command and result, or link. |
| **OBSERVED** | Seen directly (a log line, an output), but not checked against the source of truth, or possibly stale. |
| **REPORTED** | Stated by someone else (another agent, a handoff, a document, a PR comment) and not re-checked. |
| **INFERRED** | Concluded by reasoning from other facts. The reasoning is given. |
| **UNKNOWN** | Not established. Saying so is required, not optional. |

Rules:
- R1 and higher decisions rest only on VERIFIED facts.
- **Verification does not transfer.** A receiving agent reads every VERIFIED item in a handoff as REPORTED until it
  re-checks it, because the repository may have changed since.
- Archival integrity and reproducibility are separate claims, recorded in separate fields. An archive digest that
  matches is VERIFIED integrity. It is not evidence that the result reproduces (this restates
  `workspace-housekeeping` principle 8).

## Handoff record

Owner: `agent-handoff`. Default location: `.agent-state/handoffs/<branch>.md`. It is refreshed at milestones and at
the end of a session with unfinished work, not after every step.

```markdown
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
What the owner asked for, in one paragraph, with a link to the request if there is one.

## State
One line of status, then the dirty files, if any, and why they are uncommitted.

## Done
- [VERIFIED] Validator passes on HEAD: `python3 scripts/validate_skills.py` -> ALL CHECKS PASSED
- [OBSERVED] CI run green on the previous push (not re-checked after the last commit)

## Pending
1. Ordered next steps. The first one can be started without reading anything else.

## Decisions and rejected approaches
- Decisions taken during the work, with the reason.
- Approaches tried and rejected, with the evidence, so the next agent does not repeat them.

## Blockers and decisions needed
- Decisions only the owner can make, each phrased as a question with the options.

## Authorizations in force
- "<owner's words, quoted>" (date). Scope: <what it covers>. Expires: <condition>.

## Running processes and jobs
- <pid or job URL>: <command>, started <time>, output at <path>, stop with <command>

## Verification
What was tested, with which command and result, and what was not tested.

## Assumptions and limitations
- [INFERRED] ...
- [UNKNOWN] ...

## Resume
1. Check this record against the repository (branch, HEAD, upstream, working tree, PR state).
2. Re-verify what the next step depends on.
3. Continue with Pending item 1.
```

The header lines are the machine-checkable part. A future `handoff_check.py` compares them with `git` and, where
available, the PR state, and reports drift before anyone acts on the record.

## Claim

Owner: `development-coordination`. Location: `.agent-state/claims/<id>.json`. A claim is **advisory**. It informs
cooperating agents and does not block an agent that ignores it, which is why the activity check also inspects
processes and git state.

```json
{
  "kind": "claim",
  "version": 1,
  "id": "20261127T184000Z-codex-7f3a",
  "holder": { "agent": "codex", "session": "<session id or null>", "pid": 41237 },
  "scope": { "type": "checkout", "value": "." },
  "mode": "exclusive",
  "intent": "Switch to release/1.4 and rebuild build/ for an RC",
  "created": "2026-11-27T18:40:00Z",
  "expires": "2026-11-27T20:40:00Z",
  "handoff": ".agent-state/handoffs/release-1.4.md"
}
```

- `scope.type` is one of `checkout`, `branch`, `paths` (a list of globs), or `resource` (a build directory, a port,
  a device).
- **Create atomically** (exclusive create). Renew by rewriting through a temporary file and a rename. Release by
  deleting your own claim.
- **Stale** means expired **and** the holder is not running (where that can be checked on the same machine). A
  stale claim is moved to `.agent-state/claims/stale/` and reported. It is never silently deleted, and the holder's
  uncommitted work is never touched.
- Leases with expiry follow the lease idea from distributed systems (see the
  [ecosystem assessment](02-ecosystem-assessment.md#engineering-practice-prior-art)). Advisory leases with a TTL are
  also what `mcp_agent_mail` uses between agents.

## Run manifest

Owner: `research-provenance`. One per run of an experiment, benchmark, simulation or evaluation. It is written
**before** the run starts and completed when the run ends.

```json
{
  "kind": "run",
  "version": 1,
  "id": "20261127T190000Z-sweep-a",
  "purpose": "exploratory | confirmatory | qualification",
  "question": "Does the 2x internal rate keep the alias residual below -90 dBFS on the held-out set?",
  "source": { "repository": "<name or URL>", "commit": "<full id>", "dirty": false, "verified": true },
  "command": ["python3", "tools/run_sweep.py", "--config", "configs/sweep-a.json"],
  "config": [{ "path": "configs/sweep-a.json", "sha256": "<digest>" }],
  "inputs": [{ "path": "data/heldout/", "tree_sha256": "<digest>", "role": "held-out", "opened": false }],
  "toolchain": { "os": "<name version>", "cpu": "<model>", "python": "3.15.2", "compiler": "<name version>", "flags": "-O2" },
  "numerics": { "precision": "float64", "seed": 1234, "threads": 8, "tolerance": "<declared before the run>" },
  "criteria": { "path": "criteria/sweep-a.md", "sha256": "<digest>", "commit": "<id where it was committed>", "frozen_before_run": true },
  "budget": { "estimate": { "cpu_hours": 6.5 }, "authorization": "<quote or budget reference>", "stop": { "max_wall_hours": 8, "early_stop": "first gate failure" } },
  "started": "2026-11-27T19:00:00Z",
  "finished": null,
  "status": "running | completed | failed | aborted",
  "cost": { "wall_s": null, "cpu_s": null, "gpu_s": null, "ci_minutes": null, "api_spend": null },
  "outputs": [],
  "result": { "verdict": "pass | fail | inconclusive", "summary": null, "evidence": [] },
  "amendments": []
}
```

- A **qualification** run requires `source.dirty == false` and `criteria.frozen_before_run == true`. An
  **exploratory** run may be dirty: it is labelled exploratory, and its provenance stays *unknown* even if its code is
  committed later (`workspace-housekeeping` principle 9).
- Failed and aborted runs keep their manifests. A failure cited by a decision is evidence.
- Fields map onto W3C PROV: the run is an *activity*, inputs and outputs are *entities*, the agent and owner are
  *agents*. The manifest does not use PROV syntax.

## Amendment record

Owner: `research-provenance` (for criteria and frozen evidence) and `release-governance` (for release gates).
Committed. Changes to acceptance criteria are never made in place without one.

```markdown
# Amendment 3: <title>

Version: 1
Amends: criteria/sweep-a.md (revision 2 -> 3)
Before: sha256 <digest>
After: sha256 <digest>
Approved: <owner>, 2026-11-27, "<quoted approval>"
Applies to: runs started after this amendment's commit

## Reason
Why the criterion changes, and what evidence prompted it.

## Effect on existing results
Earlier runs keep their original criteria and verdicts. List any result whose verdict would change, labelled as a
re-evaluation, never as a replacement.
```

## Resource budget

Owner: `resource-budgeting`. Committed (default `ops/budget.json`). It pre-authorizes operations up to a threshold.
Above it, the operation is R2 and needs owner approval with an estimate.

```json
{
  "kind": "budget",
  "version": 1,
  "approved": "<owner>, 2026-11-27, PR <link>",
  "per_operation": {
    "cpu_hours": 4,
    "gpu_hours": 0,
    "ci_minutes": 60,
    "api_spend_usd": 5,
    "disk_gib": 20,
    "network_gib": 5
  },
  "standing": [
    { "operation": "CI on every PR push", "limit": "the existing workflow as committed" }
  ],
  "notes": "CI minutes are billed minutes after the provider's runner multipliers."
}
```

- The values above are placeholders. Real thresholds are an owner decision.
- Per-period limits are left to the providers' own spending limits and alerts where they exist. A per-period ledger
  is an open question, not part of the first version.
- A budget covers cost only. It never authorizes publication, deletion or anything else that is R2 or R3 for a
  reason other than cost.

## Artifact provenance manifest

Owner: `release-governance` (creation and promotion). `workspace-housekeeping` keeps owning preservation of the
bytes and its existing preserved-binary manifest entry, which this extends rather than replaces.

```json
{
  "kind": "artifact",
  "version": 1,
  "class": "development | audition | release-candidate | release",
  "subject": [{ "name": "Example.vst3", "sha256": "<executable digest>", "tree_sha256": "<whole-bundle digest>" }],
  "version_label": "1.4.0-rc.2",
  "source": { "repository": "<name or URL>", "commit": "<full id>", "dirty": false, "verified": true, "tag": "v1.4.0-rc.2" },
  "build": { "builder": "ci:<run URL> | local:<machine label>", "command": ["cmake", "--build", "build", "--config", "Release"], "configuration": "Release", "started": "...", "finished": "..." },
  "dependencies": [
    { "name": "<framework>", "version": "<version>", "commit": "<id>" },
    { "name": "<external asset>", "uri": "assets/<sha256>/<name>", "sha256": "<digest>" }
  ],
  "signing": { "signed": true, "identity": "<team or certificate name>", "notarized": true },
  "attestation": "<URL of a build attestation, or null>",
  "cited_by": ["<document or record>"]
}
```

- Field names are deliberately close to SLSA provenance and in-toto: `subject` (subject), `build.builder` (builder),
  `build.command` and `configuration` (external parameters), `dependencies` (resolved dependencies). A project that
  needs real attestations generates them with its CI provider's tooling. This manifest is not an attestation and must
  not be presented as one.
- **Signing changes bytes.** When signing or notarization modifies the artifact, the release candidate is the signed
  artifact, and the unsigned build is recorded as a dependency.

## Release decision record

Owner: `release-governance`. Committed (default `ops/releases/<version>.md`).

```markdown
# Release decision: <product> <version>

Version: 1
Candidate: <version>-rc.<n>
Source commit: <full id> [VERIFIED: tag points at it; CI run <link>]
Artifacts: see table
Decision: release | do not release | release with waivers
Decided: <owner>, <date>, "<quoted decision>"

## Artifacts
| Name | SHA-256 | Provenance manifest |
|---|---|---|

## Acceptance gates
| Gate | Criterion, as frozen before the candidate | Result | Evidence |
|---|---|---|---|
| ... | ... | pass / fail / waived / not run | ... |

## Waivers
One per failed or unrun gate: the owner's approval, the reason, the scope, and the debt record that tracks it.

## Known issues
Debt register IDs that ship with this release.

## Rollback
The previous release's identity and digests, where it is stored, how to revert, and whether reverting was rehearsed.

## Publication
Where, when and by whom it was published.
```

## Debt register

Owner: `technical-debt-management`. One committed register per project (default `ops/DEBT.md`). Code that embodies a
debt carries its ID in a comment (`DEBT-007`), so a script can check that markers and entries match.

```markdown
# Technical debt register

| ID | Title | Kind | Risk | Status | Reassess when |
|---|---|---|---|---|---|
| DEBT-007 | Gesture teardown guard | workaround | medium | open | framework version changes |

## DEBT-007: Gesture teardown guard

Kind: workaround | deferred decision | known defect | limitation | test gap
Status: open | accepted | resolved | superseded
Introduced: <commit or PR>
Scope: <component>; pinned to <dependency> <version>
Risk: medium (impact: <...>; likelihood: <...>)
Owner: <person or role>
Resolution: <the observable condition that closes it>
Reassess: <dependency version change | date | before the next release>
Links: <decision records, releases, issues>
```

Write an entry only when a compromise outlives the current PR. A TODO comment that the same PR resolves is not debt.

## Canonical policy blocks

Owner: `instruction-governance`. Agent-specific instruction files that cannot import a canonical file carry a
generated copy between markers, so a script can detect drift:

```markdown
<!-- policy:begin id=git-workflow rev=4 sha256=<digest of the canonical block> -->
...the canonical text, unchanged...
<!-- policy:end id=git-workflow -->
```

Where an agent supports imports (Claude Code's `@path`, Gemini CLI's `@file.md`), the adapter imports the canonical
file instead and carries no copy. The same marker convention can keep a shared block identical across skills (see
[decision D3](README.md#d3-sharing-the-risk-model-without-coupling-the-skills)).

## Versioning the formats

- A format change that removes or renames a field increments `version`. Readers accept the versions they know and
  report the others as unknown rather than guessing.
- Adding an optional field does not increment `version`.
- Examples in a skill are checked by the validator against the field list for their `kind` and `version` (see the
  [validation strategy](06-validation-strategy.md#tier-0-repository-checks-on-every-ci-run)).
