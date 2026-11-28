# 7. Implementation roadmap

Part of [RFC 0001: Operational Skills](README.md). Status: **approved** (owner decision D13, revision 2).

Phase 1 is four reviewable PRs on stacked branches, each based on its predecessor. Implementation PRs stay in draft
until the owner reviews them, and a phase starts only after the previous one has been reviewed. Small, coherent and
trustworthy beats numerous.

## Contents
- [Phase 0: research and RFC](#phase-0-research-and-rfc)
- [Phase 1: foundation and continuity](#phase-1-foundation-and-continuity)
- [Phase 2: evidence and cost](#phase-2-evidence-and-cost)
- [Phase 3: releases and debt](#phase-3-releases-and-debt)
- [Phase 4: integration](#phase-4-integration)
- [Definition of done for every skill PR](#definition-of-done-for-every-skill-pr)
- [Outside this roadmap](#outside-this-roadmap)

## Phase 0: research and RFC

- Revision 1: the seven design documents.
- Revision 2: owner decisions D1–D13 recorded, architectural corrections, reconciliation with PR #18.
- Checks: the repository validator, plus the validator's link, anchor and path-leak logic run over `rfcs/`, and a
  scan for private names.
- Exit: final owner review of revision 2.

## Phase 1: foundation and continuity

| PR | Content | Base |
|---|---|---|
| **1a** | **Shared foundation only:** the canonical operational core; deterministic synchronization of generated copies with drift detection (read-only check by default, explicit write mode); validator support for `rfcs/`; record and scenario format definitions for the Phase 1 formats; example records and synthetic fixtures; validator checks for record structure; prevention of new cross-skill relative links; deterministic self-tests, including regression tests for malformed records, drifted copies, incompatible versions and invalid authorization references. Standard library only. No skill directories, no paid evaluations | RFC branch |
| 1b | `development-coordination`: the [coordination protocol](05-artifact-conventions.md#claims-and-the-coordination-protocol), the activity check through a generated copy of `path_in_use.py`, the worktree decision procedure, safe interruption, scenarios. Settles process start time, Windows, network filesystems and the several-machines convention | 1a |
| 1c | `agent-handoff`: the record, the resume procedure, authorization-reference verification, refreshing before compaction, `handoff_check.py`, scenarios. Settles where owner identities are declared | 1b |
| 1d | `instruction-governance`: canonical policy, adapters per agent, the trust boundary, the precedence rule, the trigger table, the policy audit tool (read-only by default, proposed diff, revision and digest checks, explicit approval, unrelated text preserved, no partial writes), opt-in enforcement adapters documented but never installed by an agent | 1a |

**Phase 1 exit:**
- Tier 0 and Tier 1 pass.
- A first Tier 2 suite on Claude Code and Codex is estimated, the owner approves the estimate (proposed cap USD 25),
  and it runs with the [approved settings](06-validation-strategy.md#tier-2-scenario-evaluations-with-an-agent).
- The owner applies the consultation-trigger changes to their own instruction files. The agent proposes the diff and
  does not apply it.

## Phase 2: evidence and cost

| PR | Content | Base |
|---|---|---|
| 2a | `research-provenance`: run manifests, purposes, criteria freeze, amendments, numerical metadata, negative results, output classes at creation | 1a (or the last Phase 1 branch) |
| 2b | `resource-budgeting`: thresholds as classification, estimates with uncertainty, money for CI, cumulative related operations, stop conditions, standing workflows, CI hygiene; `budget_check.py`. Settles how related operations are identified | 2a |

**Exit:** as Phase 1, plus one real experiment run under both skills, with its manifest and estimate-versus-actual
reviewed by the owner.

## Phase 3: releases and debt

| PR | Content | Base |
|---|---|---|
| 3a | `release-governance`: build classes, candidates, gates and waivers, artifact manifest, decision record, rollback | 2a |
| 3b | `technical-debt-management`, **only if** the decision point below says so | 3a |

**Decision point (D3):** if handoff limitations, release known-issues and the domain skills' existing registers already
cover enough, `technical-debt-management` is not implemented.

## Phase 4: integration

Each item touches existing content and needs explicit owner approval:
- **`workspace-housekeeping` integration** per the [overlap table](03-responsibility-matrix.md#overlaps-with-workspace-housekeeping),
  including the manifest scope from D11 (deliberate cleanup, destructive operations and evidence-sensitive deletion;
  not routine edits, fixture teardown or task-owned temporary files), with stricter project rules preserved.
- **Generalizing `workspace-housekeeping`** for non-audio projects and platforms beyond macOS, keeping the specialized
  procedures (APFS clone accounting, Restic on the owner's disk, audition bundles) in its references.
- Whether `workspace-housekeeping` adopts the generated operational core.
- A README section for the Operational Skills family, in the repository's "one owner per area" table style.
- Optional alignment of domain skills' status vocabularies and change terms with the family's evidence labels and
  amendment record, per skill, where nothing is lost.
- A Tier 2 run across all the skills that exist by then; prune or merge whatever the scenarios show is unused or
  overlapping.

## Definition of done for every skill PR

1. `SKILL.md` under 500 lines and near the family target of about 150; detail in `references/`, one level deep.
2. `description` at most 1024 characters, with the consultation triggers; `agents/openai.yaml` with the required keys.
3. Siblings referenced by name with a minimum fallback; no new cross-skill relative links.
4. `references/operational-core.md` present and generated; the drift check passes.
5. Scripts standard library only, `--self-test` passing normally and under `python -O`.
6. Scenarios: at least four positive and two negative, critical ones marked, incidents mapped.
7. A trigger set of about 20 prompts for the description.
8. No private paths, project names, host names or unpublished results.
9. The repository validator passes; the PR is a draft for owner review; nothing merges without the owner.

## Outside this roadmap

- **PR #18 (merged 2026-11-27, independently of this RFC)** corrected `workspace-housekeeping`: a tested in-use check
  (`path_in_use.py`: working directories and open files of every process, explicit visibility, UNKNOWN never treated
  as idle), revalidation chained with removal, and no forced worktree removal. The family builds on it.
- **Existing cross-skill links.** Phase 1a freezes the 107 existing `../../<other-skill>/` links in a baseline so no
  new ones appear. Removing the existing ones is a separate repository-wide change.
- **Clean-machine reproducibility without persistent checkouts (D12).** To investigate: a disposable CI job that
  checks out a commit; a container with the repository mounted read-only; a `git archive` export into a scratch
  directory, removed after use. None creates a persistent duplicate development checkout, and none weakens the
  workspace policy. Any clone or worktree still needs explicit authorization or a narrowly scoped exception.
