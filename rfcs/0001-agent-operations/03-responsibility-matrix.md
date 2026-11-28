# 3. Skill responsibility matrix

Part of [RFC 0001: Agent Operations](README.md). Status: **draft for owner review**.

## Contents
- [The family](#the-family)
- [Matrix](#matrix)
- [Boundary tests](#boundary-tests)
- [Overlaps with workspace-housekeeping](#overlaps-with-workspace-housekeeping)
- [Overlaps with domain skills](#overlaps-with-domain-skills)
- [Rules for references between skills](#rules-for-references-between-skills)

## The family

Eight skills: the existing `workspace-housekeeping` and seven proposed ones. The candidates from the brief survive
with one change: `instruction-governance`
becomes its own skill instead of a section of `development-coordination` (see [boundary tests](#boundary-tests)).

| Skill | Status | Priority | One-line responsibility |
|---|---|---|---|
| `workspace-housekeeping` | Exists (policy revision 3) | — | Retention: what must be preserved, backed up and how storage is reclaimed |
| `development-coordination` | Proposed | P0 | Concurrency: who is using what, and whether a shared-state operation is safe now |
| `agent-handoff` | Proposed | P0 | Continuity: a record that lets another agent or session resume without the conversation |
| `instruction-governance` | Proposed | P0 (raised from cross-cutting; see [D4](README.md#d4-instruction-governance-as-its-own-p0-skill)) | Policy: one canonical source for operational rules, synchronized agent adapters, consultation triggers |
| `research-provenance` | Proposed | P1 | Integrity of results: provenance, frozen criteria and amendments for experiments and benchmarks |
| `resource-budgeting` | Proposed | P1 | Cost: estimates, thresholds, authorization and stop rules before expensive operations |
| `release-governance` | Proposed | P2 | Trust in shipped bytes: build classes, immutable candidates, gates, release decisions, rollback |
| `technical-debt-management` | Proposed | P2 | Compromises that outlive a PR: debt records, reassessment triggers, links to releases and decisions |

## Matrix

Each skill names its siblings by name and states a minimum fallback for when a sibling is not installed (see
[rules for references](#rules-for-references-between-skills)).

### development-coordination

| | |
|---|---|
| **Owns** | The activity check (is anyone using this checkout, branch, build directory or port?); claims and leases in `.agent-state/claims/`; stale-claim detection; branch and PR ownership signals; safe interruption and cancellation; the worktree **decision procedure** (ask, use only with authorization) |
| **Does not own** | Worktree policy itself and worktree removal (`workspace-housekeeping`); what to write when leaving (`agent-handoff`) |
| **Triggers** | Before any R1-or-higher operation on shared state: switching branches, resetting, rebasing, rebuilding a shared build directory, starting or stopping a dev server, pushing to a branch the agent did not create, cancelling a job; when another agent's activity is observed; when a harness offers to create an isolated worktree |
| **Inputs** | Process list with working directories; git state (dirty files, in-progress operations, recent ref changes); existing claims; optionally PR and CI state |
| **Produces** | Activity-check result (`busy`, `idle` or `unknown`, with evidence); claims |
| **References** | `workspace-housekeeping` (worktree policy and removal), `agent-handoff` (claims point to handoff records), `instruction-governance` (where standing authorizations for worktrees are written) |

### agent-handoff

| | |
|---|---|
| **Owns** | Handoff records; the resume procedure (verify the record before acting on it); evidence labels in records; refreshing the record before context compaction is expected |
| **Does not own** | Claims (`development-coordination`); run manifests (`research-provenance`); release decisions (`release-governance`) |
| **Triggers** | Ending a session with unfinished work; passing work to another agent or model; long-running jobs left running; blocking on an owner decision; resuming work someone else started; approaching the context limit |
| **Inputs** | Git and PR state; test and CI results; running processes started by the agent; decisions and authorizations given during the session |
| **Produces** | `.agent-state/handoffs/<branch>.md`; optionally a public-safe status section in the PR description |
| **References** | `development-coordination` (claims, activity check on resume), `research-provenance` and `release-governance` (link their records rather than restating them) |

### instruction-governance

| | |
|---|---|
| **Owns** | The canonical operational policy and its revision number; agent-specific adapters (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, rule files) and how they import or copy the canonical text; the precedence and conflict rule; the table of mandatory skill-consultation triggers; optional enforcement adapters (hooks, deny rules, git hooks) |
| **Does not own** | The content of domain policies (`workspace-housekeeping` owns its policy text); runtime coordination |
| **Triggers** | Creating or editing any agent instruction file; installing, renaming or removing a skill; finding two rules that conflict; setting up a new agent, machine or repository; an agent behaving as if it had not seen a rule |
| **Inputs** | The canonical policy file; every adapter file the owner names; the installed skills list |
| **Produces** | A drift report (missing, extra, outdated or conflicting blocks); a proposed patch for the owner to apply; trigger table |
| **References** | Every skill in the family (it maintains their consultation triggers) |

### research-provenance

| | |
|---|---|
| **Owns** | Run manifests; the exploratory, confirmatory and qualification distinction; freezing acceptance criteria before results exist; sealed held-out data; amendment records for criteria; numerical-reproducibility metadata (precision, seeds, threads, tolerances); recording negative results; recording consumption (cost fields) |
| **Does not own** | Whether a frozen file may be deleted, moved or compressed (`workspace-housekeeping`); spending thresholds and authorization (`resource-budgeting`); domain gates and oracles (`circuit-to-dsp`, `spice-circuit-modeling`, `bbd-modeling`) |
| **Triggers** | Before running an experiment, benchmark, simulation or evaluation whose result may be cited; before changing acceptance criteria or a frozen evidence set; before citing a result in a decision or document; when an experiment fails |
| **Inputs** | Committed source, configuration, inputs, toolchain identity, criteria file |
| **Produces** | Run manifests; amendment records |
| **References** | `resource-budgeting` (before launching), `workspace-housekeeping` (retention of evidence), domain skills for domain gates |

### resource-budgeting

| | |
|---|---|
| **Owns** | Cost estimates before expensive operations (pilot runs, extrapolation, CI minutes with runner prices); the project budget file; stop and early-termination criteria; deduplication of identical runs; CI hygiene (concurrency groups, path filters, caching, matrix size); local versus remote execution choices |
| **Does not own** | Disk retention and cleanup (`workspace-housekeeping`); recording actual consumption in run manifests (`research-provenance` records it, this skill compares it with the estimate) |
| **Triggers** | Before launching compute, a paid CI workload, an API batch job, a large download or upload; before changing a CI workflow's triggers or matrix; when a running job exceeds its estimate |
| **Inputs** | Budget file; pilot measurements; provider pricing pages; existing run manifests (to find a run that already answers the question) |
| **Produces** | An estimate with assumptions, the decision (proceed within budget, or an R2 request to the owner), stop criteria, estimate versus actual |
| **References** | `research-provenance` (manifests), `workspace-housekeeping` (disk), `development-coordination` (shared runners and build directories) |

### release-governance

| | |
|---|---|
| **Owns** | Build classes (development, audition, release candidate, released); version labels and immutable release candidates; acceptance gates for a release, results per gate, waivers; artifact provenance manifests; release decision records; rollback readiness |
| **Does not own** | Preserving the bytes and their backups (`workspace-housekeeping`); platform procedures such as signing, notarization and installers (`juce-plugin` and other domain skills); debt records (`technical-debt-management`) |
| **Triggers** | Creating a release candidate; promoting, publishing or tagging a release; a candidate that fails or skips a gate; rolling back; being asked whether a build is "the approved one" |
| **Inputs** | Source commit and tag, build provenance, gate results, debt register, previous release |
| **Produces** | Artifact provenance manifests; release decision records; amendment records for release gates |
| **References** | `workspace-housekeeping`, `research-provenance` (qualification evidence), `technical-debt-management`, domain skills for platform procedures |

### technical-debt-management

| | |
|---|---|
| **Owns** | The debt register; when a compromise becomes a record; risk classification; reassessment triggers; code markers and their consistency with the register |
| **Does not own** | Architecture decision records in general (projects use their existing ADR practice; a debt entry links to an ADR); release gates (`release-governance`) |
| **Triggers** | Leaving a workaround, known defect, limitation or deferred decision in place beyond the current PR; upgrading a dependency that a workaround is pinned to; preparing a release; reviewing open debt |
| **Inputs** | The register; code markers; dependency versions |
| **Produces** | Register entries; a reassessment report (entries whose trigger has fired) |
| **References** | `release-governance` (known issues), `agent-handoff` (limitations that outlive a session) |

### workspace-housekeeping (existing)

| | |
|---|---|
| **Owns** | Preservation and backups (git bundles, Restic, restore verification); preserved binaries and their manifest entries; classification of data for retention; deletion manifests and pre-deletion revalidation; the build-directory limit; worktree and duplicate-checkout policy and removal; storage accounting |
| **Does not own (after this RFC)** | The activity check (`development-coordination`); creating provenance and amending criteria (`research-provenance`); promotion of builds (`release-governance`) |
| **Triggers** | Unchanged: before creating clones or worktrees, switching branches in a shared checkout, deleting or archiving, backing up work in progress, citing a binary or result, reporting disk usage |

## Boundary tests

A responsibility earns its own skill only if its **consultation trigger** is distinct, because a skill is useful
only when it is activated, and activation is driven by the description (see the
[ecosystem assessment](02-ecosystem-assessment.md#agent-skills-format-and-activation)).

| Pair | Distinct triggers? | Verdict |
|---|---|---|
| `instruction-governance` vs `development-coordination` | Yes. One triggers on editing instruction files, installing skills or finding conflicting rules, which is rare and configuration-time. The other triggers before mutating shared state, which happens many times a day | **Separate.** Folding governance into coordination would load policy-maintenance guidance on every branch switch, and dilute coordination's description |
| `agent-handoff` vs `development-coordination` | Yes. Leaving or resuming work, versus acting on shared state now | **Separate**, sharing `.agent-state/` |
| `resource-budgeting` vs `research-provenance` | Mostly. "About to spend" versus "about to produce a citable result". An expensive qualification run triggers both | **Separate.** The overlap is one set of fields: provenance records actual cost, budgeting owns thresholds and compares |
| `release-governance` vs `workspace-housekeeping` | Yes. Promoting bytes versus keeping bytes | **Separate.** The overlap is the artifact manifest, resolved below |
| `technical-debt-management` vs `release-governance` | Yes. Debt exists outside releases | **Separate.** Releases read the register |
| `technical-debt-management` vs `agent-handoff` | Partly. Both record limitations | **Separate.** A handoff limitation that outlives the PR becomes a debt entry |

Alternatives considered and rejected:
- **One `agent-operations` skill with everything in references.** Its description would have to cover seven trigger
  families within 1024 characters, and every activation would load guidance irrelevant to the task.
- **Merging handoff and coordination into `agent-continuity`.** Saves one skill. Rejected because the triggers differ
  and coordination is consulted far more often.
- **Dropping `technical-debt-management`.** Defensible: it is the least novel. Kept at P2 because version-pinned
  workarounds already recur in the existing skills and nothing reassesses them (see
  [domain overlaps](#overlaps-with-domain-skills)). It can be cut at Phase 3 if the earlier skills cover enough.

## Overlaps with workspace-housekeeping

`workspace-housekeeping` already contains parts of three proposed skills. It cannot be edited in Phase 0. Each overlap
gets a rule for now, a rule for later, and the migration that needs the owner's approval.

| Topic | Housekeeping text | Owner now | Owner later | Migration (needs approval) |
|---|---|---|---|---|
| No unauthorized worktrees or clones | Principle 6, policy §1.2 | `workspace-housekeeping` | Unchanged | None |
| Don't switch branches in a checkout someone is using | Principle 7, policy §1.4 | Housekeeping states the rule | `development-coordination` owns how to tell whether someone is using it | Housekeeping's workflow calls the activity check instead of describing its own |
| Process check before removing a worktree or deleting | Procedures: "Removing a worktree", "Pre-deletion revalidation" | Housekeeping | `development-coordination` provides the check; housekeeping keeps the removal and deletion steps | Replace the inline `pgrep` filter with the activity check (see the defect noted in the [assessment](02-ecosystem-assessment.md#workspace-housekeeping-findings)) |
| Committed source before a qualification run; run records | Policy §4.1 | Housekeeping | `research-provenance` | §4.1 becomes a pointer; housekeeping keeps "results with unknown provenance stay unknown" as a retention fact |
| Frozen evidence changed only by versioned amendment | Policy §4.3 | Housekeeping (retention) | Retention stays in housekeeping; the amendment procedure moves to `research-provenance` | §4.3 links to the amendment record format |
| Failed experiments are evidence | Policy §4.5 | Housekeeping | Shared: housekeeping (don't delete), provenance (record them) | None; both keep a one-line statement |
| Preserved-binary manifest entry | Policy §3.2 | Housekeeping | Housekeeping keeps preservation; `release-governance`'s artifact manifest is a superset that satisfies §3.2 | §3.2 accepts an artifact provenance manifest as its entry |
| Policy restates the owner's global instructions | Policy preamble | Housekeeping | `instruction-governance` owns the canonical text; housekeeping references it | Housekeeping stops restating global rules |

**Conflict rule until the migration lands:** where housekeeping and a new skill both speak, the stricter rule
applies, and the new skill says so in one line rather than restating housekeeping's text.

## Overlaps with domain skills

The repository audit (see the [assessment](02-ecosystem-assessment.md#overlap-with-existing-skills)) found
operational guidance spread through the domain skills. The rule: **domain skills keep domain procedures; the
operational skills own the domain-agnostic decision and record.** Nothing in a domain skill changes in Phase 0.

| Operational concern | Already in domain skills | Resolution |
|---|---|---|
| Criteria changes | `circuit-to-dsp` (documented revision of a gate), `bbd-modeling` (owner-approved error budget, re-freeze), `spice-circuit-modeling` (change record for oracle edits) | `research-provenance` defines one amendment record. Domain skills keep their domain conditions (what evidence justifies a revision) |
| Release gates, signing, installers | `juce-plugin` (release gates, signing and notarization, install qualification, CI evidence), `circuit-to-dsp` (release classes and artifact inventory), `vcv-rack-plugin` (tag and version checks) | `release-governance` owns build classes and the release decision record. Platform procedures stay in the domain skills |
| Cost of CI and re-runs | `juce-plugin` (runner prices per OS), `circuit-to-dsp` (don't re-run SPICE when hashes match), `bbd-modeling` (re-run frozen verification every phase) | `resource-budgeting` owns the estimate and authorization. The re-run guidance does not conflict: re-verifying a frozen set is cheap and required; regenerating an oracle is expensive and avoided |
| Reports for the next agent | `juce-plugin` (report keeps rejected candidates), `guitar-gear-modeling` (accepted-constraints ledger), `circuit-to-dsp` (report fields) | `agent-handoff` links to these reports and adds a "rejected approaches" section to every handoff |
| Version-pinned workarounds and omissions | `juce-plugin` (workarounds scoped to framework versions, re-checked on upgrade), `circuit-to-dsp` (omission register), `bbd-modeling` (research agenda, known limitations) | `technical-debt-management` gives these a common register and a reassessment trigger; domain registers can stay where they are and be linked |
| Fresh clones for reproducibility | `spice-circuit-modeling` (clean-machine regeneration in a new clone), `bbd-modeling` (reproduce a binary hash from a clean worktree) | Conflicts with housekeeping's worktree and clone rule. `development-coordination` routes these to the owner as R2 requests; `instruction-governance` lets the owner write a standing authorization for them |

## Rules for references between skills

1. **Reference siblings by name, never by relative path.** The Agent Skills specification says file references are
   relative to the skill root and one level deep. The existing skills contain 107 links of the form
   `../../<other-skill>/...`, which resolve in this repository but break whenever the sibling is not installed
   next to the linking skill.
   Operational skills must not add more.
2. **State a minimum fallback.** For example: "If `workspace-housekeeping` is installed, follow it before deleting.
   Otherwise, delete nothing that is not a disposable cache without the owner's written approval."
3. **One owner per responsibility.** When a skill needs another's rule, it names the owner and gives the one-line
   minimum. It never copies the procedure. The exception is the shared operational core (see
   [decision D3](README.md#d3-sharing-the-risk-model-without-coupling-the-skills)), which is copied deliberately and
   checked for drift.
