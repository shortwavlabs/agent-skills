# 3. Skill responsibility matrix

Part of [RFC 0001: Operational Skills](README.md). Status: **approved** (owner decision D3; revision 3, amended in revision 5 after the Phase 1b review).

## Contents
- [The family](#the-family)
- [Matrix](#matrix)
- [Boundary tests](#boundary-tests)
- [Overlaps with workspace-housekeeping](#overlaps-with-workspace-housekeeping)
- [Overlaps with domain skills](#overlaps-with-domain-skills)
- [Rules for references between skills](#rules-for-references-between-skills)

## The family

Eight skills: the existing `workspace-housekeeping` and seven approved ones ([D3](README.md#d3-skill-boundaries)).

| Skill | Status | Priority | One-line responsibility |
|---|---|---|---|
| `workspace-housekeeping` | Exists (policy revision 3, procedures corrected by PR #18) | — | Retention: what must be preserved and backed up, how storage is reclaimed, the authoritative in-use check |
| `development-coordination` | Approved | P0 | Concurrency: who is using what, and whether a shared-state operation is safe now |
| `agent-handoff` | Approved | P0 | Continuity: a verifiable record that lets another agent or session resume |
| `instruction-governance` | Approved | P0 | Policy: one canonical source, audited adapters, the trust boundary, consultation triggers |
| `research-provenance` | Approved | P1 | Integrity of results: provenance, frozen criteria and amendments |
| `resource-budgeting` | Approved | P1 | Cost: thresholds, estimates, cumulative accounting, authorization and stop rules |
| `release-governance` | Approved | P2 | Trust in shipped bytes: build classes, immutable candidates, gates, decisions, rollback |
| `technical-debt-management` | Provisional | P2 | Compromises that outlive a PR; implemented only if the Phase 3 decision point says so |

## Matrix

Each skill names its siblings by name and states a minimum fallback for when a sibling is not installed
([rules](#rules-for-references-between-skills)). Every family skill carries a generated copy of the operational core
([D4](README.md#d4-shared-operational-core)).

### development-coordination

| | |
|---|---|
| **Owns** | The [coordination protocol](05-artifact-conventions.md#claims-and-the-coordination-protocol): the claim registry and its serialized acquire, renew, release, transfer and recovery; overlap rules; holder states (live, expired-held, dead, unknown, transfer-pending) with process identity by PID and start time, validated as a session boundary; the activity check (process working directories **and** open files, git in-progress state, explicit visibility), through a generated copy of `workspace-housekeeping`'s `path_in_use.py`; branch and PR ownership signals across machines; safe interruption and cancellation; the worktree decision procedure (ask, or use a scoped exception) |
| **Does not own** | Worktree policy, worktree removal and the in-use check's implementation (`workspace-housekeeping`); what to write when leaving (`agent-handoff`); where exceptions are written (`instruction-governance`) |
| **Triggers** | Before an R1-or-higher operation on shared state where another party could be affected: switching branches, committing or resetting in a shared checkout, rebuilding a shared build directory, starting or stopping a dev server, pushing to a branch the agent did not create, cancelling a job; when another agent's activity is observed; when a harness offers an isolated worktree |
| **Inputs** | The process table (working directories and open files); git state; existing claims; optionally PR and CI state |
| **Produces** | Claims; activity-check results (`busy`, `idle` or `unknown`, with visibility and evidence) |
| **References** | `workspace-housekeeping` (worktree policy and removal, the in-use check's source), `agent-handoff`, `instruction-governance` |
| **Limits, stated in the skill** | Advisory for cooperating agents only; uncooperative agents and external processes are detected, not prevented ([advisory versus enforced](05-artifact-conventions.md#advisory-coordination-versus-enforcement)); local claims are invisible to other machines |

### agent-handoff

| | |
|---|---|
| **Owns** | Handoff records; the resume procedure (verify the record against the repository before acting); runtime verification of authorization references on resume (invalid, unverified, verified, inapplicable, unknown; only verified proceeds), including host-recorded approval evidence (D14); evidence labels in records; refreshing the record before compaction where the harness allows |
| **Does not own** | Authority: a handoff is never an independent source of it ([D6](README.md#d6-authorization-across-handoffs)); claims (`development-coordination`); run manifests and release decisions (their skills) |
| **Triggers** | Ending a session with unfinished work; passing work to another agent or model; leaving long-running jobs; blocking on an owner decision; resuming someone else's work; approaching the context limit |
| **Inputs** | Git and PR state; test and CI results; processes the agent started; decisions and authorization references from the session |
| **Produces** | `.agent-state/handoffs/<branch>.md`; optionally a redacted status draft for the PR description, reviewed before posting |
| **References** | `development-coordination`, `research-provenance`, `release-governance` (link their records, never restate them), `workspace-housekeeping` (preserving important handoffs) |

### instruction-governance

| | |
|---|---|
| **Owns** | The canonical operational policy, its revision and digest; the owner identities and trusted repositories it declares (D14); the trust boundaries for the [canonical policy](04-risk-and-authorization.md#trust-boundary-for-the-canonical-policy) and for [standing authorizations](04-risk-and-authorization.md#trust-boundary-for-standing-authorizations); the [precedence rule](04-risk-and-authorization.md#instruction-precedence); adapters (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, rule files) and how they import or carry the policy; the consultation-trigger table; documentation of opt-in enforcement adapters |
| **Does not own** | The content of domain policies (`workspace-housekeeping` owns its policy text); runtime coordination |
| **Triggers** | Creating or editing an agent instruction file; installing, renaming or removing a skill; finding conflicting rules; setting up a new agent, machine or repository; an agent behaving as if it had not seen a rule |
| **Inputs** | The canonical policy; the adapter files the owner names; the installed skills list |
| **Produces** | An audit report (missing, extra, outdated, edited or conflicting blocks); a proposed diff; the trigger table |
| **References** | Every family skill (it maintains their consultation triggers) |

**Policy audit tool requirements:**
1. Read-only audit is the default mode.
2. It proposes a diff and shows it.
3. It verifies the canonical revision and digest, and the digest recorded in each adapter block.
4. It applies changes only with explicit approval of that exact diff (the approval names the diff's digest).
5. It changes nothing outside the policy markers; unrelated user instructions stay byte-identical.
6. It fails without modifying anything when an adapter cannot be updated safely: markers missing, duplicated or
   unbalanced, the file changed since the audit, the adapter a symlink, or the file not writable.
7. It never installs hooks, changes harness settings or edits global instruction files on its own. Global adapters
   change only when the owner applies the approved diff or explicitly instructs the agent to.

### research-provenance

| | |
|---|---|
| **Owns** | Run manifests; exploratory, confirmatory and qualification purposes; output classes declared at creation; freezing criteria before results; sealed held-out data; amendment records; numerical metadata; negative results; recording consumption |
| **Does not own** | Whether frozen files may be deleted, moved or compressed (`workspace-housekeeping`); thresholds and authorization of spending (`resource-budgeting`); domain gates (`circuit-to-dsp`, `spice-circuit-modeling`, `bbd-modeling`) |
| **Triggers** | Before a run whose result may be cited; before changing acceptance criteria or frozen evidence; before citing a result; when an experiment fails |
| **Inputs** | Committed source, configuration, inputs, toolchain identity, criteria |
| **Produces** | Run manifests; amendment records |
| **References** | `resource-budgeting`, `workspace-housekeeping`, domain skills |

### resource-budgeting

| | |
|---|---|
| **Owns** | The budget file and its thresholds, which classify operations (at or above a threshold is R2); estimates with low and high values and their basis; money for CI, kept apart from billed and elapsed minutes; cumulative accounting of related operations so that splitting a task cannot circumvent a threshold; stop conditions and the material-overrun rule; respect for standing authorized workflows; CI hygiene (concurrency groups, path filters, caching, matrix size); local versus remote execution choices |
| **Does not own** | Storage retention and cleanup (`workspace-housekeeping`); recording actual consumption (`research-provenance` records it; this skill compares it with the estimate) |
| **Triggers** | Before launching compute, paid CI, an API batch, paid GPU, a large download or upload, or anything adding persistent storage; before changing CI triggers or matrix; when a job passes its estimate |
| **Inputs** | The budget file; pilot measurements; providers' current price lists; existing run manifests (to find a run that already answers the question) |
| **Produces** | An estimate; the classification; an R2 request where needed; stop conditions; estimate versus actual |
| **References** | `research-provenance`, `workspace-housekeeping`, `development-coordination` |

The owner's initial workspace thresholds (D9, not universal defaults): 8 CPU-hours, 2 hours wall clock, no implicit
paid GPU, USD 2 incremental paid CI, USD 5 API, 20 GiB persistent storage and 5 GiB network transfer, per operation
([format](05-artifact-conventions.md#resource-budget)).

### release-governance

| | |
|---|---|
| **Owns** | Build classes; version labels and immutable release candidates; release gates, results per gate and waivers; artifact provenance manifests; release decision records; rollback readiness |
| **Does not own** | Preserving the bytes (`workspace-housekeeping`); platform procedures such as signing and installers (`juce-plugin` and other domain skills); debt records |
| **Triggers** | Creating a candidate; promoting, publishing or tagging a release; a candidate failing or skipping a gate; rolling back; "is this the approved build?" |
| **Inputs** | Source commit and tag, build provenance, gate results, known issues, previous release |
| **Produces** | Artifact provenance manifests; release decision records; amendments to release gates |
| **References** | `workspace-housekeeping`, `research-provenance`, `technical-debt-management` (if implemented), domain skills |

### technical-debt-management (provisional)

| | |
|---|---|
| **Owns, if implemented** | The debt register; when a compromise becomes a record; risk classification; reassessment triggers; code markers and their consistency with the register |
| **Does not own** | Architecture decision records in general; release gates |
| **Triggers** | Leaving a workaround, defect, limitation or deferred decision beyond the current PR; upgrading a dependency a workaround is pinned to; preparing a release |

### workspace-housekeeping (existing)

| | |
|---|---|
| **Owns** | Preservation and backups; preserved binaries; retention classes; deletion manifests and pre-deletion revalidation; the build-directory limit; worktree and duplicate-checkout policy and removal (plain removal, never forced); the authoritative in-use check `scripts/path_in_use.py`; storage accounting |
| **Does not own (after this RFC)** | Claims and coordination (`development-coordination`); creating provenance and amending criteria (`research-provenance`); promotion of builds (`release-governance`) |
| **Triggers** | Unchanged |

## Boundary tests

A responsibility earns its own skill only if its consultation trigger is distinct, because activation is driven by the
description ([assessment](02-ecosystem-assessment.md#agent-skills-format-and-activation)).

| Pair | Distinct triggers? | Verdict |
|---|---|---|
| `instruction-governance` vs `development-coordination` | Yes: configuration-time versus runtime | **Separate** (D3) |
| `agent-handoff` vs `development-coordination` | Yes: leaving or resuming versus acting now | **Separate**, sharing `.agent-state/` |
| `resource-budgeting` vs `research-provenance` | Mostly: "about to spend" versus "about to produce a citable result" | **Separate**; provenance records cost, budgeting classifies and compares |
| `release-governance` vs `workspace-housekeeping` | Yes: promoting bytes versus keeping bytes | **Separate** |
| `technical-debt-management` vs `release-governance` | Yes | **Separate if implemented** |
| `technical-debt-management` vs `agent-handoff` | Partly | **Separate if implemented**; a limitation outliving the PR becomes a debt entry |

Rejected alternatives: one combined skill (seven trigger families in one description); merging handoff and
coordination (different triggers, very different frequency).

## Overlaps with workspace-housekeeping

`workspace-housekeeping` contains parts of three family skills. Broader integration is deferred to Phase 4 (D11). Until
then, where housekeeping and a family skill both speak, the stricter rule applies, and the family skill says so in one
line rather than restating housekeeping's text.

| Topic | Housekeeping text | Owner now | Owner later | Migration (Phase 4, needs approval) |
|---|---|---|---|---|
| No unauthorized worktrees or clones | Principle 6, policy §1.2 | Housekeeping | Unchanged (D12: no blanket exception) | None |
| Don't switch branches in a checkout someone is using | Principle 7, policy §1.4 | Housekeeping states the rule | Coordination owns how to tell (claims, activity check) | Housekeeping points to coordination |
| In-use check before removal or deletion | Procedures; `scripts/path_in_use.py` | **Resolved by PR #18**: housekeeping holds the authoritative implementation | Unchanged; coordination carries a generated copy | None |
| Forced worktree removal | Procedures, step 4 | **Resolved by PR #18**: never forced; refusals investigated | Unchanged | None |
| Manifest scope | Principle 5, policy §6.1 ("every deletion") | Housekeeping, read with D11: deliberate cleanup, destructive operations, evidence-sensitive deletion; not routine edits, fixture teardown or task-owned temporary files | Unchanged | Reword §6.1 to state the D11 scope |
| Committed source before a qualification run | Policy §4.1 | Housekeeping | `research-provenance` | §4.1 becomes a pointer; "unknown provenance stays unknown" stays as a retention fact |
| Frozen evidence changed only by versioned amendment | Policy §4.3 | Housekeeping (retention) | Retention stays; the amendment procedure moves to `research-provenance` | §4.3 links to the amendment format |
| Failed experiments are evidence | Policy §4.5 | Housekeeping | Shared: don't delete (housekeeping), record (provenance) | None |
| Preserved-binary manifest entry | Policy §3.2 | Housekeeping | Housekeeping keeps preservation; the artifact manifest is a superset | §3.2 accepts an artifact manifest |
| Policy restates the owner's global instructions | Policy preamble | Housekeeping | `instruction-governance` owns the canonical text | Housekeeping stops restating global rules |
| Audio- and macOS-specific wording | Description, procedures | Housekeeping | Housekeeping, generalized | Generalize; keep specialized procedures in references |

## Overlaps with domain skills

The rule: domain skills keep domain procedures; the operational skills own the domain-agnostic decision and record.
Nothing in a domain skill changes before Phase 4.

| Operational concern | Already in domain skills | Resolution |
|---|---|---|
| Criteria changes | `circuit-to-dsp` (documented revision), `bbd-modeling` (owner-approved error budget, re-freeze), `spice-circuit-modeling` (change records) | `research-provenance` defines one amendment record; domain skills keep their domain conditions |
| Release gates, signing, installers | `juce-plugin`, `circuit-to-dsp`, `vcv-rack-plugin` | `release-governance` owns build classes and the decision record; platform procedures stay |
| Cost of CI and re-runs | `juce-plugin` (runner prices per OS), `circuit-to-dsp` (no SPICE re-runs when hashes match), `bbd-modeling` (re-verify frozen sets every phase) | `resource-budgeting` owns classification and authorization; re-verifying a frozen set is cheap and required, regenerating an oracle is expensive and avoided |
| Reports for the next agent | `juce-plugin` (rejected candidates kept), `guitar-gear-modeling` (accepted-constraints ledger), `circuit-to-dsp` (report fields) | `agent-handoff` links to them and keeps a "rejected approaches" section |
| Version-pinned workarounds and omissions | `juce-plugin`, `circuit-to-dsp`, `bbd-modeling` | `technical-debt-management`, if implemented, links the domain registers |
| Fresh clones for reproducibility | `spice-circuit-modeling` (clean-machine regeneration in a new clone), `bbd-modeling` (reproduce a hash from a clean worktree) | **D12:** no blanket authorization. A clone or worktree needs explicit authorization or a narrowly scoped exception. Preferred alternatives: a disposable CI job, a container, or a `git archive` export into scratch ([roadmap](07-roadmap.md#outside-this-roadmap)) |

## Rules for references between skills

1. **Reference siblings by name, never by relative path.** The Agent Skills specification keeps file references
   relative to the skill root and one level deep. The existing skills contain 116 relative links into other skills
   (88 distinct source-and-target pairs, most of the form `../../<other-skill>/...`), which break whenever the sibling
   is not installed next to the linking skill. Phase 1a
   freezes them in a baseline and rejects new ones repository-wide.
2. **State a minimum fallback.** For example: "If `workspace-housekeeping` is installed, follow it before deleting.
   Otherwise, delete nothing that is not a disposable, task-owned file without the owner's approval."
3. **One owner per responsibility; one source per shared file.** A skill that needs another's rule names the owner and
   gives a one-line minimum. Text or code that several installed skills must carry identically (the operational core,
   the in-use check) has exactly one authoritative source and generated, drift-checked copies
   ([D4](README.md#d4-shared-operational-core)). Nothing is re-implemented.
