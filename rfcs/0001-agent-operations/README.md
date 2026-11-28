# RFC 0001: Agent Operations

| | |
|---|---|
| **Status** | Draft for owner review (Phase 0: research and design). Nothing here is approved or implemented |
| **Created** | 2026-11-27 |
| **Scope** | A family of operational skills for coding agents, alongside the existing `workspace-housekeeping` skill |
| **Working name** | "Agent Operations". The name collides with existing projects; see [D1](#d1-the-family-name) |

> Technical skills teach agents how to build software. Operational skills teach agents how to sustain software
> engineering.

## Documents

| # | Deliverable | Location |
|---|---|---|
| 1 | RFC: motivation, scope, architecture, terminology, principles, decisions | This file |
| 2 | Existing skills and ecosystem assessment | [02-ecosystem-assessment.md](02-ecosystem-assessment.md) |
| 3 | Skill responsibility matrix | [03-responsibility-matrix.md](03-responsibility-matrix.md) |
| 4 | Operational risk and authorization model | [04-risk-and-authorization.md](04-risk-and-authorization.md) |
| 5 | Shared artifact conventions (templates and schemas) | [05-artifact-conventions.md](05-artifact-conventions.md) |
| 6 | Scenario-based validation strategy | [06-validation-strategy.md](06-validation-strategy.md) |
| 7 | Implementation roadmap | [07-roadmap.md](07-roadmap.md) |

Every decision that needs the owner is collected in one place:
[decisions requiring owner approval](#decisions-requiring-owner-approval).

## Contents
- [Summary](#summary)
- [Motivation](#motivation)
- [Motivating incidents](#motivating-incidents)
- [Scope and non-goals](#scope-and-non-goals)
- [Terminology](#terminology)
- [Design principles](#design-principles)
- [Architecture](#architecture)
- [Design decisions](#design-decisions)
- [Decisions requiring owner approval](#decisions-requiring-owner-approval)
- [Unresolved questions](#unresolved-questions)
- [Revision history](#revision-history)

## Summary

Most agent skills teach an agent to perform a technical task. Few teach it to work safely next to other agents, leave
work resumable, keep results trustworthy, spend resources deliberately, ship traceable builds, or keep its
compromises visible. A recent workspace cleanup produced `workspace-housekeeping`, which covers preservation and
storage. This RFC proposes seven more skills around it:

| Skill | Priority | Responsibility |
|---|---|---|
| `development-coordination` | P0 | Whether a shared-state operation is safe now: activity checks, advisory claims, ownership |
| `agent-handoff` | P0 | A verifiable record that lets another agent or session resume without the conversation |
| `instruction-governance` | P0 | One canonical policy, synchronized agent adapters, mandatory consultation triggers |
| `research-provenance` | P1 | Provenance, frozen criteria and amendments for experiments and benchmarks |
| `resource-budgeting` | P1 | Estimates, thresholds, authorization and stop rules before expensive operations |
| `release-governance` | P2 | Build classes, immutable candidates, gates, release decisions, rollback |
| `technical-debt-management` | P2 | Debt records with reassessment triggers; may be cut at Phase 3 |

They share one four-level risk model (R0 routine, R1 shared state, R2 consequential, R3 irreversible or
evidence-sensitive), one set of evidence labels and a small set of record formats. Each skill is installable on its
own. Rules that matter are backed by deterministic scripts or harness hooks wherever practical, because
documentation alone enforces nothing.

## Motivation

Coding agents are now participants in long-running projects: many sessions, several agents, expensive experiments,
real releases. The failures that hurt in such projects are rarely about writing code. They are about state that
nobody recorded, work that collided, results that cannot be traced, money spent without a decision, and rules that
one agent saw and another did not.

`workspace-housekeeping` showed that this knowledge can be packaged as a skill. It also showed the limits of doing
so: a skill that is installed is not necessarily consulted, and a rule written in prose is not necessarily followed
(see incidents I6 to I8 below, and the [ecosystem assessment](02-ecosystem-assessment.md#agent-skills-format-and-activation)).

## Motivating incidents

Real incidents from one owner's workspace, generalized. No project details are included. The incident column is the
owner's account. The "what failed" column is our reconstruction from that account, **inferred and pending owner
confirmation**.

| ID | Incident | What failed (inferred) | Generalized lesson | Owner | Strongest practical enforcement |
|---|---|---|---|---|---|
| I1 | Hundreds of gigabytes of research output accumulated with no retention strategy | Output was classified only at cleanup time, long after anyone remembered what it was | Decide each output's class (evidence, expensive reproducible, disposable cache) when the run is created; count disk in budgets | `research-provenance`, `resource-budgeting`, `workspace-housekeeping` | Run manifests declare output class; disk threshold in the budget |
| I2 | Critical source code stayed uncommitted while expensive simulation outputs accumulated | Results had no recorded provenance; committing the code afterwards could not restore it | Qualification runs start from committed source; retrospective commits are preservation, not provenance | `research-provenance` | The run-manifest script refuses a dirty tree for qualification runs |
| I3 | Approved binaries were hard to distinguish from later rebuilds | Approval named a build, not bytes | Approve digests; promote the approved bytes; a rebuild is a new candidate | `release-governance`, `workspace-housekeeping` | Artifact manifest with whole-bundle digest; release check compares digests |
| I4 | Historical builds depended on unversioned external assets | Inputs were named, not pinned | Store external inputs by content digest before any build that uses them is cited | `release-governance`, `workspace-housekeeping` | Manifest dependencies require a digest |
| I5 | Unpublished work needed preservation without publishing it to public repositories | A "preservation" push to a public remote publishes | Classify a public push as R2 whatever its intent; back up to private storage | `workspace-housekeeping` (exists) | Check repository visibility before any push |
| I6 | A truncated process check allowed a cache to be removed while processes still held it | The check listed only some processes, and a missing signal was read as "idle" | Check the complete process list; a missing signal means *unknown*, never *idle* | `development-coordination` | A tested activity-check script with no name filter |
| I7 | An agent created an unauthorized worktree minutes after a workspace cleanup | The rule existed in prose, but the harness offered worktree isolation as a normal feature | Prose loses to tool affordances; hard rules need harness-level enforcement and a decision procedure | `instruction-governance`, `development-coordination` | A deny rule or pre-tool hook for worktree creation |
| I8 | Different coding agents operated under inconsistent global Git instructions | Adapter files for each agent were maintained by hand and drifted | One canonical policy; adapters import it or carry checked copies | `instruction-governance` | A policy-sync script reporting drift |
| I9 | Qualification criteria and frozen experimental evidence required explicit protection | Nothing technical stopped criteria from changing after results were seen | Freeze criteria before results; change them only by amendment; protect frozen files from cleanup | `research-provenance`, `workspace-housekeeping` | Criteria hash recorded in the run manifest and checked at evaluation |
| I10 | GitHub Actions spend rose because of repeated build and validation workloads | Workflow changes were made without a cost estimate; macOS minutes cost about ten times Linux | Estimate before changing CI or launching paid work; deduplicate; cancel superseded runs | `resource-budgeting` | A check that workflows set concurrency groups and timeouts |

**Observed during this phase** (details in the
[assessment](02-ecosystem-assessment.md#workspace-housekeeping-findings)):
- The owner's agent-specific instruction files are maintained by hand and currently differ. I8 is ongoing.
- `workspace-housekeeping`'s worktree-removal procedure tells the reader to check every process, then gives a
  command that lists only processes matching five names. That is the same class of gap as I6 (a partial process
  list), whatever the original check's exact cause.

## Scope and non-goals

**In scope:** operational practice for coding agents working on real repositories: coordination, continuity,
instruction governance, provenance of results, resource use, release decisions, technical debt, and (existing)
preservation and storage. Applicable to any software domain, any agent, any operating system.

**Non-goals:**
- A project-management framework: no tickets, sprints, estimates of effort or status meetings.
- A service: no daemon, database, orchestrator or hosted dependency. Files and git only.
- Replacing domain procedures: signing, notarization, circuit validation and the like stay in their domain skills.
- Signed supply-chain attestations: projects that need SLSA levels above L1 use their CI provider's tooling.
- Changing any existing skill in Phase 0.

## Terminology

| Term | Meaning |
|---|---|
| **Owner** | The person with authority over the project (or someone they name). The only source of authorization |
| **Agent** | Any coding agent or model acting in the repository, in any harness |
| **Session** | One continuous run of an agent; it ends, or loses detail at context compaction |
| **Shared state** | Anything another agent or person depends on: a checkout, a pushed branch, a PR, CI configuration, a build directory, a running server |
| **Activity check** | An automated inspection of processes, git state, recent writes and claims, answering `busy`, `idle` or `unknown` |
| **Claim** | An advisory, expiring record that an agent is using a checkout, branch, path set or resource |
| **Handoff record** | A structured, verifiable file describing unfinished work so that another agent can resume it |
| **Evidence label** | VERIFIED, OBSERVED, REPORTED, INFERRED or UNKNOWN, attached to each factual statement in a record |
| **Risk level** | R0 routine, R1 shared state, R2 consequential, R3 irreversible or evidence-sensitive ([model](04-risk-and-authorization.md)) |
| **Standing authorization** | A committed, owner-authored rule pre-authorizing a class of operations, with a scope |
| **Run manifest** | The provenance record of one experiment, benchmark or simulation run |
| **Frozen evidence** | Criteria, held-out data, golden references or results protected from change except by amendment |
| **Amendment** | A committed, owner-approved record of a change to frozen criteria or evidence, never applied retroactively |
| **Build classes** | Development build, audition build (preserved for review), release candidate (immutable), released product |
| **Canonical policy** | The single source text of operational rules that agent-specific instruction files import or copy |
| **Adapter** | An agent-specific instruction file (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, rule files) that carries canonical policy to one agent |
| **Operational core** | The short shared text (risk levels, evidence labels, authorization rule) copied into every family skill |

## Design principles

The brief's principles, with how the family meets each, and the strongest
[enforcement rung](02-ecosystem-assessment.md#enforcement-versus-advice) available.

| Principle | How the family meets it | Enforcement |
|---|---|---|
| **Agent-agnostic** | Plain files and git; no agent-specific feature is required. Agent-specific adapters (hooks, deny rules) are optional extras documented by `instruction-governance` | Scenario runs on at least two agents per phase |
| **Domain-agnostic** | Examples span benchmarks, ML runs, numerical computing and releases; audio examples appear only as one case among several | Review |
| **Composable** | Each skill installs alone; siblings are referenced by name with a minimum fallback; the shared core is copied, not linked | Validator: no cross-skill relative links; core drift check |
| **Non-overlapping** | One owner per responsibility, with explicit rules for every known overlap ([matrix](03-responsibility-matrix.md)) | Review; boundary tests |
| **Risk-proportional** | Four levels; R0 requires nothing; R1 one automated preflight; questions only at R2 and above | Negative scenarios fail a skill that adds ceremony |
| **Evidence-based** | Evidence labels in every record; verification does not transfer across a handoff | Record checks; handoff check |
| **Authorization-aware** | Sources, scope and expiry of authorization defined once; observed content never authorizes | Scenarios with injected "approvals" |
| **Non-disruptive** | Overhead limits are requirements; claims are advisory; nothing blocks on a service | Negative scenarios |
| **Progressive disclosure** | `SKILL.md` near 150 lines, detail in `references/`, one level deep | Validator size check |
| **Portable** | Standard-library Python and `git`; no paths, services or platform assumptions; a missing tool yields *unknown* | Script self-tests on CI's Linux runner |
| **Enforceable where practical** | Each key rule has a script, and each skill states which rung each rule is on | Tier 0 and Tier 1 checks |

## Architecture

### Layers

| Layer | Skills | Consulted |
|---|---|---|
| **Policy** | `instruction-governance` | When instruction files or installed skills change; makes the other skills discoverable |
| **Runtime** | `development-coordination`, `agent-handoff` | Every session that touches shared state or leaves work unfinished |
| **Evidence** | `research-provenance`, `release-governance` | When results will be cited or bytes will ship |
| **Stewardship** | `resource-budgeting`, `technical-debt-management`, `workspace-housekeeping` | When resources are spent, compromises persist, or storage is reclaimed |

### How agents find and follow the skills

Three mechanisms, from weakest to strongest. The family uses all three, because installing a skill guarantees none
of them:

1. **Descriptions.** Each skill's description lists its consultation triggers in the repository's
   "Capability. Covers …. Use when …" style, and is tested with a trigger set of about 20 prompts.
2. **Mandatory triggers in instruction files.** `instruction-governance` maintains a table such as "before switching
   branches in a shared checkout, consult `development-coordination`", carried into every agent's adapter. The
   owner's existing instruction already does this for `workspace-housekeeping`.
3. **Harness enforcement for hard rules.** Where an agent supports it, a deny rule or pre-tool hook blocks the
   operations that must never happen without authorization (for example, worktree creation). These adapters are
   optional and agent-specific.

### Shared foundation

- **Operational core** (about 40 lines): the four risk levels with their requirements, the evidence labels, and the
  authorization rule. Copied into each skill (see [D3](#d3-sharing-the-risk-model-without-coupling-the-skills)).
- **Record formats** ([conventions](05-artifact-conventions.md)): JSON where scripts read the record, Markdown with
  fixed headings where people do; every record versioned.
- **Locations:** `.agent-state/` (local, excluded from git) for claims and handoffs; a committed records directory
  for budgets, debt, release decisions and amendments; run manifests next to their results.

## Design decisions

### D1: The family name

"AgentOps" already names a skills collection for coding agents in this same category, a Microsoft accelerator and an
agent observability product ([assessment](02-ecosystem-assessment.md#comparable-collections-and-the-name)).
- **Option A (recommended):** a plain descriptive label, **"Operational skills"**, in the README and documentation;
  never "AgentOps" as an identifier.
- **Option B:** keep "Agent Operations" spelled out and accept the confusion.
- **Option C:** a distinctive name ("Sustained Engineering").

Skill names stay unprefixed, matching every existing skill in the repository. A prefix (`ops-handoff`) would reduce
collision risk with other collections at the cost of the repository's naming convention. Collision risk is low for
the proposed names.

### D2: Seven proposed skills, with clear triggers

Each responsibility became a skill only if its consultation trigger is distinct from its neighbours'
([boundary tests](03-responsibility-matrix.md#boundary-tests)). Rejected: one combined skill (its description could
not cover seven trigger families, and every activation would load irrelevant guidance); merging handoff and
coordination (their triggers differ, and coordination is consulted far more often). `technical-debt-management` is
the weakest candidate and carries an explicit cut point at Phase 3.

### D3: Sharing the risk model without coupling the skills

The risk model, evidence labels and authorization rule must mean the same thing in every skill, yet each skill must
install alone.

| Option | For | Against |
|---|---|---|
| A base skill that the others require | One copy | Breaks independent installation; agents rarely load two skills for one task |
| Reference by name only ("see `development-coordination`") | No duplication | The text is missing whenever that skill is not installed |
| **A short copied block, checked for drift (recommended)** | Every skill is complete alone; drift is caught in CI | About 40 lines copied into each of the seven new skills |

The copy lives in each skill's `references/operational-core.md`, and the validator checks that every copy is
byte-identical. The same marker-and-hash mechanism serves `instruction-governance`, so one primitive covers both.

### D4: Instruction governance as its own P0 skill

The brief asked whether instruction governance deserves its own skill or belongs in `development-coordination`.
**Recommendation: its own skill, at P0.**
- Its triggers (editing instruction files, installing skills, finding conflicting rules) are rare and
  configuration-time. Coordination's are frequent and runtime. Folding them together would dilute coordination's
  description and load policy maintenance on every branch switch.
- Operational skills under-trigger on descriptions alone, because agents believe they can do these tasks unaided.
  Mandatory triggers in instruction files are what make the Phase 1 skills effective, so governance cannot wait.
- Incident I8 is live today, and the fix is small: a canonical file, adapters and a sync script.

Alternative: a section of `development-coordination`. Cheaper by one skill, but weaker discovery for both.

### D5: Design documents live in `rfcs/`

`docs/` is ignored by `.gitignore` (it holds local upstream documentation), and the owner's rules forbid bypassing or
weakening ignore rules without authorization. This RFC therefore lives in `rfcs/0001-agent-operations/`. Future
RFCs take the next number. The validator does not yet scan `rfcs/`; Phase 1a adds it, and Phase 0 runs the same
checks ad hoc.

### D6: Local coordination state lives in `.agent-state/`

Claims and handoff records are local, uncommitted and visible to every agent in the checkout.
- `.git/` would be ideal (never committed, shared across worktrees), but Codex's default sandbox makes `.git`
  read-only ([assessment](02-ecosystem-assessment.md#enforcement-versus-advice)).
- A user-level directory outside the repository needs sandbox escalation in some agents.
- **Recommended:** `.agent-state/` at the checkout root, excluded through `.git/info/exclude` (one-time set-up,
  changes no tracked file). Excluding it through a committed `.gitignore` entry is the alternative. Caveat:
  `git clean -x` removes it, which is acceptable for ephemeral state.

### D7: JSON for machines, Markdown for people, no YAML

Scripts read JSON with the standard library; people read Markdown records with fixed headings that a regular
expression can check. YAML has no standard-library parser, which is why the validator already hand-parses
frontmatter ([format rule](05-artifact-conventions.md#format-rule-json-or-markdown)).

### D8: Canonical policy, adapters and the conflict rule

- One canonical policy file with a revision number and stable section IDs. Adapters import it where the agent
  supports imports (`@path` in Claude Code, `@file.md` in Gemini CLI). Elsewhere they carry a marked copy, checked
  by a sync script ([policy blocks](05-artifact-conventions.md#canonical-policy-blocks)). Symlinks are a third option,
  but they break on Windows and some editing tools refuse to write through them.
- **Conflict rule (proposed):** no tool resolves conflicts between instruction files: most concatenate them. The
  canonical policy therefore states its own rule, and every agent reads it:
  1. The owner's explicit instruction in the current session wins for that task.
  2. An owner-authored, explicit exception in a project file (a standing authorization) wins over a general rule.
  3. Otherwise, the **more protective** rule wins: the one that preserves data, requires authorization, or blocks
     publication.
  4. The conflict is reported to the owner either way. An agent never resolves it by editing instruction files
     without authorization (global files are R2).
- Third-party skills rank below the owner's policy. A skill that recommends what the owner forbids (worktrees, for
  example) loses.

### D9: Deterministic checks in CI; paid evaluations on demand

Tier 0 (repository checks) and Tier 1 (script self-tests on fixture repositories) run on every CI run, using the
standard library only. Tier 2 (agent scenario runs) is budgeted, run before a skill's first merge and after material
changes, never on every push ([validation strategy](06-validation-strategy.md)).

### D10: `workspace-housekeeping` changes wait for Phase 4

The overlaps are resolved on paper now and migrated later with explicit approval
([overlap table](03-responsibility-matrix.md#overlaps-with-workspace-housekeeping)). Until then the stricter rule
applies wherever housekeeping and a new skill both speak. The procedural defect found in this audit (the
name-filtered process check) is an exception the owner may choose to fix earlier.

## Decisions requiring owner approval

1. **Family name** ([D1](#d1-the-family-name)): adopt "Operational skills" (recommended), keep "Agent Operations",
   or choose another. Drop "AgentOps" as an identifier.
2. **Skill names:** keep the proposed names unprefixed (recommended), or add a family prefix.
3. **Boundaries** ([D2](#d2-seven-proposed-skills-with-clear-triggers), [D4](#d4-instruction-governance-as-its-own-p0-skill)):
   seven proposed skills; `instruction-governance` separate and P0; `technical-debt-management` subject to a cut at
   Phase 3.
4. **Shared core** ([D3](#d3-sharing-the-risk-model-without-coupling-the-skills)): a copied block with a drift check.
5. **Risk model** ([model](04-risk-and-authorization.md)): the four levels, their requirements and the overhead
   limits.
6. **Authorization across handoffs:** R1 scope transfers; R2 only when quoted with a covering scope; R3 never.
7. **Conflict rule** ([D8](#d8-canonical-policy-adapters-and-the-conflict-rule)): owner in session, then explicit
   project exception, then the more protective rule.
8. **Locations** ([D5](#d5-design-documents-live-in-rfcs), [D6](#d6-local-coordination-state-lives-in-agent-state)):
   `rfcs/` for design documents; `.agent-state/` excluded via `.git/info/exclude` or via `.gitignore`; `ops/` as the
   default committed records directory; handoff records local by default with a public-safe PR summary.
9. **Budget thresholds:** real per-operation values for CPU-hours, GPU-hours, billed CI minutes, API spend, disk and
   network, per project.
10. **Tier 2 evaluations:** how many runs per scenario, the pass rule, the agents to cover, and a budget per run.
11. **`workspace-housekeeping`:** whether policy §6.1 (a manifest for every deletion) is meant for cleanups only or for
    every deletion; whether to fix its name-filtered process check before Phase 1; the Phase 4 migration; whether to
    generalize its domain- and macOS-specific wording.
12. **Clean-machine reproducibility:** whether to write a standing authorization for the fresh clones that
    `spice-circuit-modeling` and `bbd-modeling` call for, which the worktree and clone policy currently forbids
    without authorization.
13. **Roadmap** ([roadmap](07-roadmap.md)): Phase 1 as four stacked PRs (foundation, coordination, handoff,
    governance).

## Unresolved questions

- **Coordination across machines.** Claims are local. Across machines the only signals are branches, PRs and CI.
  Is a convention (for example a draft PR as the claim on a branch) enough?
- **Identifying the agent's own processes.** The activity check must exclude its caller. Harnesses expose process
  ancestry differently; the fallback is to report own-looking processes as *unknown* rather than *busy*.
- **Platforms without `lsof`.** On Windows the process check reports *unknown* until a portable method is chosen.
- **When to refresh a handoff before compaction.** Some harnesses offer a pre-compaction hook; others give no
  warning. The default is "at milestones", which may be too coarse for long sessions.
- **Per-period budgets.** Providers' own spending limits may suffice; a local ledger is deferred.
- **Enforcement adapters in the skills or beside them.** Shipping hook examples inside `instruction-governance`
  makes them easy to find but agent-specific; keeping them out keeps the skills agent-agnostic.
- **Interoperability.** Whether run manifests should optionally export to RO-Crate, and artifact manifests to in-toto
  statements, for projects that publish them.

## Revision history

| Revision | Date | Change |
|---|---|---|
| 1 | 2026-11-27 | First draft for owner review (Phase 0) |
