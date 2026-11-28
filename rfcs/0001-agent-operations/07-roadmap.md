# 7. Implementation roadmap

Part of [RFC 0001: Agent Operations](README.md). Status: **draft for owner review**.

The brief's tentative roadmap holds, with three changes:
- `instruction-governance` joins Phase 1 as a P0 skill, because the Phase 1 skills depend on instruction-file
  triggers to be consulted at all (see [D4](README.md#d4-instruction-governance-as-its-own-p0-skill)).
- A small foundation PR comes first: shared core, validator support and the scenario format.
- Each skill is its own PR. Within a phase, the PRs are stacked, each based on its predecessor (the repository's
  existing practice for dependent work).

## Contents
- [Phase 0: research and RFC (this PR)](#phase-0-research-and-rfc-this-pr)
- [Phase 1: foundation and continuity](#phase-1-foundation-and-continuity)
- [Phase 2: evidence and cost](#phase-2-evidence-and-cost)
- [Phase 3: releases and debt](#phase-3-releases-and-debt)
- [Phase 4: integration](#phase-4-integration)
- [Definition of done for every skill PR](#definition-of-done-for-every-skill-pr)
- [Outside this roadmap](#outside-this-roadmap)

## Phase 0: research and RFC (this PR)

- The seven design documents in `rfcs/0001-agent-operations/`.
- No skill, script, validator or CI change.
- Checks: the repository validator (unchanged), plus an ad-hoc run of the validator's link, anchor and path-leak
  logic over `rfcs/`, which the validator does not yet scan. A manual scan for private names.
- Exit: the owner approves the RFC, or approves it with the decisions in the
  [decision list](README.md#decisions-requiring-owner-approval) settled.

## Phase 1: foundation and continuity

| PR | Content | Depends on |
|---|---|---|
| 1a | Foundation: the operational core text (risk levels, evidence labels, authorization rule, about 40 lines); validator support (scan `rfcs/`, core drift check, scenario-file and record-example checks, no new cross-skill relative links); the scenario format; scenarios for the brief's nine situations as fixtures, with no runner yet | Phase 0 approval |
| 1b | `development-coordination`: `SKILL.md`, references (activity check, claims and leases, worktree decision procedure, interruption), `activity_check.py` with self-tests, scenarios | 1a |
| 1c | `agent-handoff`: `SKILL.md`, references (record, resume procedure, compaction), `handoff_check.py`, scenarios | 1b (uses `.agent-state/` and claims) |
| 1d | `instruction-governance`: `SKILL.md`, references (canonical policy, adapters per agent, precedence, triggers, enforcement adapters), `policy_sync.py`, scenarios | 1a |

**Exit:** the three skills pass Tier 0 and Tier 1; one budgeted Tier 2 run of their scenarios on at least two
agents; the owner adds the consultation triggers to their own instruction files (the agent proposes the patch and
does not apply it).

## Phase 2: evidence and cost

| PR | Content | Depends on |
|---|---|---|
| 2a | `research-provenance`: run manifest, purposes, criteria freeze, amendments, numerical metadata, negative results; `run_manifest.py` | 1a |
| 2b | `resource-budgeting`: estimates, budget file, stop criteria, deduplication, CI hygiene; `budget_check.py` | 2a (reads manifests) |

**Exit:** as Phase 1, plus one real experiment in a project run under the two skills, with its manifest and
estimate-versus-actual reviewed by the owner.

## Phase 3: releases and debt

| PR | Content | Depends on |
|---|---|---|
| 3a | `release-governance`: build classes, candidates, gates and waivers, artifact manifest, decision record, rollback; `release_check.py` | 2a (qualification evidence) |
| 3b | `technical-debt-management`: register, triggers, markers; `debt_check.py` | 3a (releases list known issues) |

**Decision point before 3b:** if Phases 1–3a already cover limitations well enough (handoff limitations, release
known issues, domain omission registers), cut 3b. Fewer, better skills.

## Phase 4: integration

These changes touch existing content, so each needs explicit owner approval:
- `workspace-housekeeping` migration, per the [overlap table](03-responsibility-matrix.md#overlaps-with-workspace-housekeeping):
  pointers to `development-coordination` (activity check), `research-provenance` (run records, amendments) and
  `release-governance` (artifact manifest); stop restating global instructions.
- Whether to generalize `workspace-housekeeping`'s audio-plugin- and macOS-specific wording to match the family's
  domain-agnostic, portable principles, or to keep it as the audio-workspace member of the family.
- A README section for the family, in the repository's existing "one owner per area" table style.
- Optional alignment of domain skills: replacing their own status vocabularies and change terms with the family's
  evidence labels and amendment record where that loses nothing. Optional, and per skill.
- A second budgeted Tier 2 run across all eight skills (the seven new ones and `workspace-housekeeping`); prune or
  merge anything that the scenarios show is unused or
  overlapping.

## Definition of done for every skill PR

1. `SKILL.md` under 500 lines (specification) and near the family's target of about 150; detail in `references/`,
   one level deep.
2. `description` at most 1024 characters, in the repository's style ("Capability. Covers …. Use when …"), with the
   consultation triggers in it; `agents/openai.yaml` with the required keys.
3. References to siblings by name, each with its minimum fallback; no cross-skill relative links.
4. The operational core copy, byte-identical to the canonical one.
5. Scripts: standard library only, `--self-test` passing normally and under `python -O`.
6. Scenarios: at least four positive and two negative, with incident mapping.
7. A trigger set of about 20 prompts for the description, checked at least once.
8. No private paths, project names, host names or unpublished results.
9. The repository validator passes; the PR is opened as a draft for owner review.

## Outside this roadmap

Found during the audit, but independent of the family:
- **A defect in `workspace-housekeeping`'s procedures** (see the
  [assessment](02-ecosystem-assessment.md#workspace-housekeeping-findings)): a name-filtered process check that
  contradicts the skill's own "complete process list" rule. A small fix that could land before Phase 1, with owner
  approval.
- **107 cross-skill relative links** in the existing skills break whenever the linked sibling is not installed next to
  the linking skill. Fixing them is a
  separate repository-wide change.
