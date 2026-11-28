# RFC 0001: Operational Skills

| | |
|---|---|
| **Status** | Revision 4: approved by the owner, with all 14 decisions and the Phase 1a review decisions recorded (2026-11-27). Phase 1a merged (#19); Phase 1b in progress |
| **Created** | 2026-11-27 |
| **Scope** | The Operational Skills family for coding agents, alongside the existing `workspace-housekeeping` skill |
| **Terms** | "Operational Skills" is the family name. "Agent Operations" is a descriptive architectural term only ([D1](#d1-family-name)) |

> Technical skills teach agents how to build software. Operational skills teach agents how to sustain software
> engineering.

## Documents

| # | Deliverable | Location |
|---|---|---|
| 1 | RFC: motivation, scope, architecture, terminology, principles, owner decisions, corrections | This file |
| 2 | Existing skills and ecosystem assessment | [02-ecosystem-assessment.md](02-ecosystem-assessment.md) |
| 3 | Skill responsibility matrix | [03-responsibility-matrix.md](03-responsibility-matrix.md) |
| 4 | Operational risk and authorization model | [04-risk-and-authorization.md](04-risk-and-authorization.md) |
| 5 | Shared artifact conventions and the coordination protocol | [05-artifact-conventions.md](05-artifact-conventions.md) |
| 6 | Scenario-based validation strategy | [06-validation-strategy.md](06-validation-strategy.md) |
| 7 | Implementation roadmap | [07-roadmap.md](07-roadmap.md) |

## Contents
- [Summary](#summary)
- [Motivation](#motivation)
- [Motivating incidents](#motivating-incidents)
- [Scope and non-goals](#scope-and-non-goals)
- [Terminology](#terminology)
- [Design principles](#design-principles)
- [Architecture](#architecture)
- [Owner decisions](#owner-decisions)
- [Architectural corrections](#architectural-corrections)
- [Unresolved implementation questions](#unresolved-implementation-questions)
- [Revision history](#revision-history)

## Summary

Most agent skills teach an agent to perform a technical task. Few teach it to work safely next to other agents, leave
work resumable, keep results trustworthy, spend resources deliberately, ship traceable builds, or keep its
compromises visible. A workspace cleanup produced `workspace-housekeeping`, which covers preservation and storage.
This RFC adds seven skills around it:

| Skill | Priority | Responsibility |
|---|---|---|
| `development-coordination` | P0 | Whether a shared-state operation is safe now: activity checks, a serialized claim registry, ownership |
| `agent-handoff` | P0 | A verifiable record that lets another agent or session resume without the conversation |
| `instruction-governance` | P0 | One canonical policy, synchronized agent adapters, a trust boundary for exceptions, consultation triggers |
| `research-provenance` | P1 | Provenance, frozen criteria and amendments for experiments and benchmarks |
| `resource-budgeting` | P1 | Estimates, thresholds, cumulative accounting, authorization and stop rules before expensive operations |
| `release-governance` | P2 | Build classes, immutable candidates, gates, release decisions, rollback |
| `technical-debt-management` | P2, provisional | Debt records with reassessment triggers; the decision to implement it is taken at Phase 3 |

They share one canonical operational core: four risk levels (R0 routine, R1 shared state, R2 consequential,
R3 irreversible or evidence-sensitive), precise evidence labels and the authorization rules. The core is copied
into every skill by a deterministic generator, so each skill installs on its own. Rules that matter are backed by
deterministic scripts or harness controls where practical, because documentation alone enforces nothing.

## Motivation

Coding agents are now participants in long-running projects: many sessions, several agents, expensive experiments,
real releases. The failures that hurt in such projects are rarely about writing code. They are about state that
nobody recorded, work that collided, results that cannot be traced, money spent without a decision, and rules that
one agent saw and another did not.

`workspace-housekeeping` showed that this knowledge can be packaged as a skill. It also showed the limits of doing
so: a skill that is installed is not necessarily consulted, and a rule written in prose is not necessarily followed
(incidents I6 to I8 below, and the [ecosystem assessment](02-ecosystem-assessment.md#agent-skills-format-and-activation)).

## Motivating incidents

Real incidents from one owner's workspace, generalized. No project details are included. The incident column is the
owner's account. The "what failed" column is our reconstruction from that account, **inferred and pending owner
confirmation**.

| ID | Incident | What failed (inferred) | Generalized lesson | Owner | Strongest practical enforcement |
|---|---|---|---|---|---|
| I1 | Hundreds of gigabytes of research output accumulated with no retention strategy | Output was classified only at cleanup time, long after anyone remembered what it was | Decide each output's class (evidence, expensive reproducible, disposable cache) when the run is created; count storage in budgets | `research-provenance`, `resource-budgeting`, `workspace-housekeeping` | Run manifests declare output class; storage threshold in the budget |
| I2 | Critical source code stayed uncommitted while expensive simulation outputs accumulated | Results had no recorded provenance; committing the code afterwards could not restore it | Qualification runs start from committed source; retrospective commits are preservation, not provenance | `research-provenance` | The run-manifest tool refuses a dirty tree for qualification runs |
| I3 | Approved binaries were hard to distinguish from later rebuilds | Approval named a build, not bytes | Approve digests; promote the approved bytes; a rebuild is a new candidate | `release-governance`, `workspace-housekeeping` | Artifact manifest with whole-bundle digest; release check compares digests |
| I4 | Historical builds depended on unversioned external assets | Inputs were named, not pinned | Store external inputs by content digest before any build that uses them is cited | `release-governance`, `workspace-housekeeping` | Manifest dependencies require a digest |
| I5 | Unpublished work needed preservation without publishing it to public repositories | A "preservation" push to a public remote publishes | Any push to a public remote is publication (R2); back up to private storage | `workspace-housekeeping` (exists) | Check repository visibility before any push |
| I6 | A truncated process check allowed a cache to be removed while processes still held it | The check saw only some processes, and a missing signal was read as "idle" | Check every process's working directory and open files; unknown is never idle | `development-coordination`, `workspace-housekeeping` | `path_in_use.py` (merged in PR #18) |
| I7 | An agent created an unauthorized worktree minutes after a workspace cleanup | The rule existed in prose, but the harness offered worktree isolation as a normal feature | Prose loses to tool affordances; hard rules need harness-level controls and a decision procedure | `instruction-governance`, `development-coordination` | An owner-installed deny rule or pre-tool hook (never installed by an agent) |
| I8 | Different coding agents operated under inconsistent global Git instructions | Adapter files for each agent were maintained by hand and drifted | One canonical policy; adapters import it or carry digest-checked copies | `instruction-governance` | A policy audit that reports drift and proposes a diff |
| I9 | Qualification criteria and frozen experimental evidence required explicit protection | Nothing technical stopped criteria from changing after results were seen | Freeze criteria before results; change them only by amendment; protect frozen files from cleanup | `research-provenance`, `workspace-housekeeping` | Criteria digest recorded in the run manifest and checked at evaluation |
| I10 | GitHub Actions spend rose because of repeated build and validation workloads | Workflow changes were made without a cost estimate; macOS minutes cost about ten times Linux | Estimate money, not minutes, before changing CI or launching paid work; count related runs together | `resource-budgeting` | A check that workflows set concurrency groups and timeouts |

**Observed during Phase 0, and since resolved:** `workspace-housekeeping`'s worktree-removal procedure said to check
every process, then gave a command that listed only processes matching five names, and it permitted a forced
removal. PR #18 (merged independently of this RFC, before revision 2) replaced the command with a tested in-use check
(`skills/workspace-housekeeping/scripts/path_in_use.py`) and removed `--force` entirely
([findings](02-ecosystem-assessment.md#workspace-housekeeping-findings)). The owner's agent-specific instruction files
are maintained by hand and still differed when re-checked on 2026-11-27 (I8).

## Scope and non-goals

**In scope:** operational practice for coding agents working on real repositories: coordination, continuity,
instruction governance, provenance of results, resource use, release decisions, technical debt, and (existing)
preservation and storage. Applicable to any software domain, any agent, any operating system the tools support.

**Non-goals:**
- A project-management framework: no tickets, sprints, effort estimates or status meetings.
- A service: no daemon, database, orchestrator or hosted dependency. Files, git and the standard library only.
- Enforceable locking against uncooperative processes. Coordination between cooperating agents is advisory; what
  can actually be enforced is listed in [05](05-artifact-conventions.md#advisory-coordination-versus-enforcement).
- Replacing domain procedures: signing, notarization, circuit validation and the like stay in their domain skills.
- Signed supply-chain attestations: projects that need them use their CI provider's tooling.
- Installing hooks, changing harness settings or editing global instruction files on an agent's own initiative.

## Terminology

| Term | Meaning |
|---|---|
| **Owner** | The person with authority over the project, identified by declared identities (for example a GitHub account). The only source of authorization |
| **Agent** | Any coding agent or model acting in the repository, in any harness |
| **Session** | One continuous run of an agent; it ends, or loses detail at context compaction |
| **Shared state** | Anything another agent or person depends on: a checkout, a pushed branch, a PR, CI configuration, a build directory, a running server |
| **Activity check** | An inspection of every process's working directory and open files, git state and recent writes, answering `busy`, `idle` or `unknown` with an explicit visibility level |
| **Visibility** | How much of the process table a check could read: complete, owner-complete, partial or failed. Only the first two can support "idle" |
| **Claim** | An advisory, expiring record that an agent is using a checkout, branch, path set or resource, acquired through the serialized [coordination protocol](05-artifact-conventions.md#claims-and-the-coordination-protocol) |
| **Handoff record** | A structured, verifiable file describing unfinished work so that another agent can resume it. Not a source of authority |
| **Evidence label** | VERIFIED, OBSERVED, REPORTED, INFERRED or UNKNOWN, defined precisely in [05](05-artifact-conventions.md#evidence-labels-and-verification-records) |
| **Verification record** | The claim, method, artifact identity and time behind a VERIFIED label |
| **Risk level** | R0 routine, R1 shared state, R2 consequential, R3 irreversible or evidence-sensitive ([model](04-risk-and-authorization.md)). A property of the operation's consequences, never of who authorized it |
| **Authorization** | Permission for an operation, from a recognized source (the owner in the session, or a verified standing authorization). It permits an operation; it does not lower its risk level |
| **Standing authorization** | An entry in a designated, committed file that pre-authorizes an explicitly scoped class of R1 or R2 operations, whose approval the host records as the owner's for that exact content ([trust boundary](04-risk-and-authorization.md#trust-boundary-for-standing-authorizations), [D14](#d14-host-recorded-approvals-as-authorization-evidence)) |
| **Authorization reference** | A pointer to the original authorization: a standing authorization at a commit (verifiable by another agent), or the owner session that granted it (not verifiable by another agent) |
| **Authorization status** | invalid, unverified (structurally valid only), verified (authentic and applicable), inapplicable (expired, revoked, out of scope, or changed since approval) or unknown. Only *verified* grants authority; repository validators can report only *invalid* or *unverified* ([05](05-artifact-conventions.md#authorization-references)) |
| **Refusal** | A safety mechanism declining an operation (git, a preflight, a permission check, a hook). A finding to investigate, never a reason to escalate |
| **Run manifest** | The provenance record of one experiment, benchmark or simulation run |
| **Frozen evidence** | Criteria, held-out data, golden references or results protected from change except by amendment |
| **Amendment** | A committed, owner-approved record of a change to frozen criteria or evidence, never applied retroactively |
| **Build classes** | Development build, audition build (preserved for review), release candidate (immutable), released product |
| **Canonical policy** | The single source text of operational rules that agent-specific instruction files import or copy |
| **Adapter** | An agent-specific instruction file (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, rule files) that carries canonical policy to one agent |
| **Operational core** | The canonical shared text (risk levels, evidence labels, authorization rules), with exactly one authoritative source and identical generated copies in every family skill |

## Design principles

The brief's principles, with how the family meets each, and the strongest
[enforcement rung](02-ecosystem-assessment.md#enforcement-versus-advice) available.

| Principle | How the family meets it | Enforcement |
|---|---|---|
| **Agent-agnostic** | Plain files, git and standard-library Python; agent-specific controls are optional adapters the owner installs | Scenario runs on Claude Code and Codex |
| **Domain-agnostic** | Examples span benchmarks, ML runs, numerical computing and releases | Review |
| **Composable** | Each skill installs alone; siblings are referenced by name with a minimum fallback; shared text and the in-use check are generated copies of one source | Validator: drift check; no new cross-skill relative links |
| **Non-overlapping** | One owner per responsibility, with explicit rules for every known overlap ([matrix](03-responsibility-matrix.md)) | Review; boundary tests |
| **Risk-proportional** | R0 needs nothing; R1 needs a preflight only where another party could be affected; R2 needs a verified authorization; R3 controls match the actual consequence | Negative scenarios fail a skill that adds ceremony |
| **Evidence-based** | Precise labels; verification records name claim, method, artifact identity and time; missing evidence is never proof of safety | Record checks; handoff check |
| **Authorization-aware** | Sources, references, scope, expiry and trust boundary defined once; observed content never authorizes | Scenarios with injected "approvals" |
| **Refusals are findings** | A safety mechanism that refuses an operation triggers investigation, never a more forceful variant | Critical scenarios |
| **Non-disruptive** | Overhead limits are requirements; claims are advisory; nothing blocks on a service | Negative scenarios |
| **Progressive disclosure** | `SKILL.md` near 150 lines, detail in `references/`, one level deep | Validator size check |
| **Portable** | Standard library and `git`; where a tool is missing (for example `lsof` on Windows) the answer is *unknown*, not *idle* | Self-tests on CI's Linux runner and locally on macOS |
| **Enforceable where practical** | Each key rule has a deterministic check, and each skill states which rung each rule is on | Tier 0 and Tier 1 checks |

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

1. **Descriptions.** Each skill's description lists its consultation triggers and is tested with a trigger set of
   about 20 prompts. Activation failures are reported as failures.
2. **Mandatory triggers in instruction files.** `instruction-governance` maintains a trigger table carried into
   every agent's adapter, through an audited, owner-approved change.
3. **Harness controls for hard rules.** Where an agent supports them, deny rules or pre-tool hooks block operations
   that must never happen without authorization. The skills document them; only the owner installs them.

### Shared foundation (Phase 1a)

- **One authoritative source** in a top-level `operational/` directory: the operational core text and the record and
  scenario format definitions. It is not a skill and is never installed.
- **Generated copies:** each family skill carries `references/operational-core.md`, byte-identical to what the
  generator produces from the source (a generated header naming the source, its revision and digest, then the source
  text). The generator's default mode is a read-only check, which CI runs; writing copies is an explicit mode.
- **Records:** JSON where tools read them, Markdown with fixed headings where people do (with a JSON block where
  precision matters, such as authorizations); every record versioned
  ([conventions](05-artifact-conventions.md)).
- **Locations:** `.agent-state/` (local, self-ignoring) for claims and handoffs; `ops/` (or a project override) for
  committed operational records; run manifests next to their results.

## Owner decisions

All fourteen decisions were settled by the owner on 2026-11-27 (D14 in the final review). Each entry records the decision, the resulting design,
and where it is specified.

| # | Decision | Outcome | Specified in |
|---|---|---|---|
| D1 | Family name | Approved: "Operational Skills" | This file |
| D2 | Skill names | Approved: unprefixed | This file |
| D3 | Skill boundaries | Approved: seven skills; governance P0; debt provisional | [03](03-responsibility-matrix.md) |
| D4 | Shared operational core | Approved: one source, generated copies, drift check | [D4](#d4-shared-operational-core), [06](06-validation-strategy.md#tier-0-repository-checks-on-every-ci-run) |
| D5 | Risk model | Approved with corrections | [04](04-risk-and-authorization.md) |
| D6 | Authorization across handoffs | Approved with corrections | [04](04-risk-and-authorization.md#authorization-across-a-handoff), [05](05-artifact-conventions.md#authorization-references) |
| D7 | Instruction precedence | Approved: five levels; trust boundary to define | [04](04-risk-and-authorization.md#instruction-precedence) |
| D8 | Artifact locations and formats | Approved with requirements | [05](05-artifact-conventions.md#location-rule) |
| D9 | Resource budgets | Approved: configurable; initial workspace values | [05](05-artifact-conventions.md#resource-budget) |
| D10 | Scenario evaluations | Approved: Tier 0–1 always; Tier 2 smoke tests | [06](06-validation-strategy.md#tier-2-scenario-evaluations-with-an-agent) |
| D11 | Workspace housekeeping | Manifest scope clarified; PR #18 separate; integration in Phase 4 | [03](03-responsibility-matrix.md#overlaps-with-workspace-housekeeping), [07](07-roadmap.md#phase-4-integration) |
| D12 | Fresh clones | No blanket authorization; investigate alternatives | [03](03-responsibility-matrix.md#overlaps-with-domain-skills), [07](07-roadmap.md#outside-this-roadmap) |
| D13 | Roadmap | Approved: Phase 1 as four stacked PRs | [07](07-roadmap.md) |
| D14 | Host-recorded approvals | Approved with strict conditions: evidence for an explicitly scoped standing authorization only | [D14](#d14-host-recorded-approvals-as-authorization-evidence), [04](04-risk-and-authorization.md#host-recorded-approvals) |

### Design added in revision 2

The following design was added in revision 2 to carry out the decisions and the architectural corrections, and was
accepted in the owner's final review (revision 3):
- the coordination protocol's overlap rules, holder states and lock failure modes
  ([05](05-artifact-conventions.md#claims-and-the-coordination-protocol));
- the authorization-reference format, limited to the approved sources, and the standing-authorizations file format
  ([05](05-artifact-conventions.md#authorization-references));
- the trust-boundary conditions for the canonical policy and for standing authorizations, anchored in host-attested
  records rather than self-asserted git authors ([04](04-risk-and-authorization.md#trust-boundary-for-the-canonical-policy));
- R3 controls by consequence ([04](04-risk-and-authorization.md#r3-controls-by-consequence));
- the repository-wide baseline of cross-skill links, which also binds the domain skills
  ([06](06-validation-strategy.md#tier-0-repository-checks-on-every-ci-run));
- the generated copy of `path_in_use.py` in `development-coordination` ([D4](#d4-shared-operational-core));
- the added scenarios and the `critical` flag ([06](06-validation-strategy.md#scenario-catalogue)).

### D1: Family name

**Decision:** "Operational Skills" is the descriptive family name. "AgentOps" is never used as a product name or
identifier, because it already names a skills collection in this category, a Microsoft accelerator and an agent
observability product ([assessment](02-ecosystem-assessment.md#comparable-collections-and-the-name)). "Agent
Operations" may remain a descriptive architectural term; this directory keeps its name.

### D2: Skill names

**Decision:** keep the proposed names unprefixed, consistent with every existing skill in the repository.

### D3: Skill boundaries

**Decision:** approve the seven skills listed in the [summary](#summary). `instruction-governance` is a separate P0
skill: its triggers (editing instruction files, installing skills, conflicting rules) are rare and
configuration-time, while coordination's are frequent and runtime, and the Phase 1 skills depend on instruction-file
triggers to be consulted at all. `technical-debt-management` stays provisional; whether to implement it is decided at
Phase 3 ([boundary tests](03-responsibility-matrix.md#boundary-tests)).

### D4: Shared operational core

**Decision:** independently installable skills; one authoritative source; identical generated copies; a
deterministic synchronization and drift check; no additional base skill to install.

- The source lives in `operational/` (Phase 1a). Copies live at `skills/<skill>/references/operational-core.md`.
- A copy is *identical* when its bytes equal the generator's output for the current source: a fixed generated header
  (source path, revision, SHA-256 of the source) followed by the source text unchanged.
- The generator's default is a read-only check that reports missing, extra, edited and outdated copies; CI runs it.
  Writing copies is an explicit mode, reviewed in the PR like any other change.
- Sources and destinations are restricted to an explicit, reviewed list. In Phase 1a it holds only `operational/`
  sources, each with one designated destination name. Phase 1b extends it, by a reviewed change, with
  `workspace-housekeeping`'s `path_in_use.py` and its designated destination in `development-coordination`, so
  coordination installs alone without a second, divergent implementation of the in-use check.

### D5: Risk model

**Decision:** approve R0–R3 and the risk-proportional approach, with these corrections, all applied in
[04](04-risk-and-authorization.md):
1. A push to a public remote is publication, whatever the branch: R2. Pushing a feature branch is permitted when the
   owner's instruction or a standing authorization covers it; the push is still R2.
2. R0 requires no additional ceremony.
3. Routine operations are not escalated because an agent lacks confidence. Classification rests on facts; an unknown
   deciding fact is established, or treated as unsafe for that dimension.
4. R1 requires a shared-state preflight only where there is a genuine concurrency risk.
5. R2 may proceed under explicit, scoped standing authorization.
6. R3 controls match the actual consequence: backups for destruction, amendments for evidence changes, no
   irrelevant backup requirement for evidence-sensitive operations that destroy nothing.
7. Risk classification and authorization are separate. Authorization permits an operation; it never reduces its risk.
8. Missing or incomplete evidence is never proof of safety.
9. A safety mechanism refusing an operation triggers investigation, not escalation to a more destructive command.

### D6: Authorization across handoffs

**Decision:** R1 scope transfers; scoped R2 authorization transfers only with a **verifiable reference** to the
original owner authorization wherever one exists. A handoff is not an independent source of authority, and a
quotation in an agent-authored record is not sufficient by itself. If the authorization cannot be established, the
receiving agent asks once. R3 authorization is reconfirmed by the receiving agent, and the operation revalidated
before execution ([04](04-risk-and-authorization.md#authorization-across-a-handoff),
[reference format](05-artifact-conventions.md#authorization-references)).

### D7: Instruction precedence

**Decision:**
1. Applicable system, security and harness constraints.
2. Explicit owner instructions in the current session.
3. Explicit, trusted, owner-approved project exceptions (standing authorizations).
4. The canonical operational policy.
5. General project guidance and technical skills.

Where applicable instructions at the same level conflict, the more protective rule applies and the conflict is
reported. Instructions are never silently edited to resolve a conflict. The
[trust boundary](04-risk-and-authorization.md#trust-boundary-for-standing-authorizations) separates owner-approved
standing authorizations from text found in files, issues, PR comments or tool output.

### D8: Artifact locations and formats

**Decision:** `rfcs/` for design documents; `.agent-state/` for local coordination records; `ops/` as the default for
committed operational records, with project overrides; JSON for machine-read records; Markdown for human-read
records; no YAML as an operational record format (Agent Skills frontmatter conventions are unchanged). Additional
requirements, specified in [05](05-artifact-conventions.md#location-rule):
- a sandbox-compatible exclusion of `.agent-state/` (a self-ignoring `.gitignore` inside it, tested with a read-only
  `.git`);
- claims are ephemeral, handoffs are valuable, and the two are kept apart;
- ignored files are never assumed safe to delete;
- a preservation path for important handoffs that never force-adds ignored files;
- no private coordination records, credentials, transcripts or personal paths in public repositories.

### D9: Resource budgets

**Decision:** thresholds are configurable and owner-approved. The owner's initial **workspace** values, which are not
universal defaults: 8 CPU-hours, 2 hours of wall-clock execution, no implicit paid GPU compute, USD 2 of incremental
paid CI, USD 5 of API spend, 20 GiB of additional persistent storage and 5 GiB of network transfer, per operation.
The design respects existing authorized workflows, separates billed minutes from elapsed minutes and money, evaluates
related operations cumulatively so that splitting a task cannot circumvent a threshold, records estimate
uncertainty, and stops or seeks authorization when an estimate is materially exceeded
([05](05-artifact-conventions.md#resource-budget), [03](03-responsibility-matrix.md#resource-budgeting)).

### D10: Scenario evaluations

**Decision:** deterministic Tier 0 and Tier 1 checks on every CI run. Tier 2 starts as engineering smoke tests on
Claude Code and Codex, two runs per scenario per agent (a third for a meaningful non-safety disagreement, within
budget), with every run passing Preservation and Authorization, at least 90% aggregate Action and Overhead success
without hiding a critical failure, results reported by agent, model and scenario, activation failures included, and a
proposed USD 25 cap for the first Phase 1 suite, estimated before execution. No paid evaluation runs in Phase 1a
([06](06-validation-strategy.md#tier-2-scenario-evaluations-with-an-agent)).

### D11: Workspace housekeeping

**Decision:** the manifest requirement applies to deliberate workspace cleanup, destructive operations and
evidence-sensitive deletion. It does not apply to routine source edits, test-fixture teardown or ordinary deletion of
demonstrably disposable, task-owned temporary files. Stricter project rules are preserved. PR #18 stays independent
of this RFC; it was merged on 2026-11-27, before this revision. Broader housekeeping integration is deferred to
Phase 4, which also generalizes the skill for non-audio projects and platforms beyond macOS, keeping the specialized
procedures in its references.

### D12: Fresh clones

**Decision:** no blanket standing authorization for fresh clones. Additional clones and worktrees require explicit
authorization or a narrowly scoped, owner-approved exception. Clean-machine reproducibility stays valuable; the
roadmap investigates disposable CI environments, containers and temporary source exports (`git archive` into a
scratch directory), none of which creates a persistent duplicate development checkout. The workspace policy is not
weakened.

### D13: Roadmap

**Decision:** Phase 1 as four reviewable PRs: 1a shared foundation, 1b `development-coordination`, 1c
`agent-handoff`, 1d `instruction-governance`, on stacked branches for dependent work ([07](07-roadmap.md)).


### D14: Host-recorded approvals as authorization evidence

**Decision (final review):** host-recorded GitHub PR approvals and merges by the owner's account may serve as
**evidence** of owner authorization, under strict conditions. For Phase 1 they support a standing authorization
committed to a trusted default branch; they are never a general mechanism that reads arbitrary PR approvals as
operational permission.
- The approved content must itself explicitly authorize the operation or class of operations. Approving an
  implementation does not authorize running it; approving a cleanup tool does not authorize deletion; approving a
  build system does not authorize publication; approving a policy grants nothing beyond its stated scope.
- The owner's identity comes from trusted host metadata, never from git author fields or text.
- The approval is bound to the exact approved content and revision. An approval of an earlier revision does not cover
  authorization content that changed afterwards.
- Scope, expiry and revocation are checked against the current trusted policy.
- An untrusted repository cannot establish its own owner identity or trust boundary: owner identities and trusted
  repositories are declared only in the canonical policy.
- R3 authorization is still reconfirmed, as the operational core requires.

### Decisions from the Phase 1a review (revision 4)

Approved by the owner on 2026-11-27, after the Phase 1a review:
- The approved revision of a standing authorization comes from trusted host metadata.
- Removing a standing authorization from the current default branch revokes it. **Reintroducing** a revoked
  authorization requires fresh owner approval; historical approval never revives it.
- Host-recorded approval must apply to the exact authorization content. Dismissed, superseded or otherwise
  inapplicable approvals grant no authority.
- The five authorization statuses stay: invalid, unverified, verified, inapplicable, unknown.
- Owner identities and trusted repositories are declared exclusively in the canonical policy.
- Operational record formats stay at version 1: Phase 1a had not been released when they changed.
- `approved_in` accepts GitHub PR URLs. This is the initial capability, not an architectural restriction: other
  hosts can be added with their own trusted metadata.
- The cross-skill link baseline stays as it is, domain skills included.
- A generated copy whose byte-order mark hides its generated identity is refused, never rewritten.
- The 1.25 material-overrun factor is approved as a **material-deviation threshold that requires reassessment**. It
  never permits exceeding an authorized hard limit on spending, compute, storage or execution time.
- From the Phase 1b instructions: an expired claim is not automatically abandoned. A claim is archived as stale only
  when it has expired **and** its holder is established to be dead; a claim whose holder cannot be verified stays
  unknown. Session tokens prevent accidental misuse between cooperating agents; they are not authentication against a
  hostile process running as the same user.

Runtime authorization verification and its regression fixtures belong to Phase 1c; budget enforcement belongs to
Phase 2.

Specified in [04](04-risk-and-authorization.md#host-recorded-approvals) and
[05](05-artifact-conventions.md#standing-authorizations).
## Architectural corrections

The owner's review identified four areas to correct before implementation (coordination takes two rows below). Each is
specified where it belongs.

| Area | Correction | Rationale | Specified in |
|---|---|---|---|
| **Coordination protocol** | Claims are acquired, renewed and released inside one serialized critical section (an OS advisory lock on a single registry lock file), with overlap rules per scope type, process identity by PID **and** start time, explicit states for expired and unverifiable holders, and the activity check run after acquisition and again before execution | Atomic creation of individual claim files does not stop two agents acquiring overlapping scopes at the same moment | [05](05-artifact-conventions.md#claims-and-the-coordination-protocol) |
| **Advisory versus enforced** | Claims bind only cooperating agents; uncooperative agents and external processes are detected by the activity check, not prevented; the enforceable mechanisms are listed separately | Documentation must not pretend to be a lock | [05](05-artifact-conventions.md#advisory-coordination-versus-enforcement) |
| **Instruction governance** | A trust boundary for the canonical policy and one for standing authorizations; a policy audit tool that is read-only by default, proposes a diff, verifies revision and digest, applies only with explicit approval of that exact diff, preserves unrelated instructions, and fails without modifying anything when an adapter cannot be updated safely; never installs hooks or edits harness settings or global files on its own | The tool that keeps instructions consistent must not itself become an unreviewed writer of instructions | [04](04-risk-and-authorization.md#trust-boundary-for-the-canonical-policy), [04](04-risk-and-authorization.md#trust-boundary-for-standing-authorizations), [03](03-responsibility-matrix.md#instruction-governance) |
| **Evidence and authorization** | Precise labels; verification records with claim, method, artifact identity and time; a digest verifies identity or integrity only, and identity is not state; authorization statuses (invalid, unverified, verified, inapplicable, unknown) with only *verified* granting authority, and a quotation alone never verified | Labels used loosely spread unverified claims with the authority of verified ones | [05](05-artifact-conventions.md#evidence-labels-and-verification-records) |
| **Shared-state and cleanup safety** | The lessons of PR #18 apply family-wide: no forced worktree removal, no process-name filters, no truncated inventories, unknown is not idle, working directories and open files, revalidation immediately before destructive operations. The family references the corrected housekeeping procedure and its `path_in_use.py`; it never re-implements them | One corrected implementation, not two contradictory ones | [04](04-risk-and-authorization.md#refusals-and-missing-evidence), [03](03-responsibility-matrix.md#development-coordination) |

## Unresolved implementation questions

These are implementation details within the approved design, to be settled in the phase named.

- **Owner identities and trusted repositories (1d).** Decided (D14): declared only in the canonical policy. Open: the
  exact format of that declaration.
- **Runtime verification of host-recorded approvals (1c).** Which host API calls establish a merge or approving review
  by an owner identity and the revision it applied to, and what happens offline (the status is *unknown*: ask once).
  Until 1d declares owner identities in the canonical policy, runtime verification reports *unknown*: ask once.
- **Identifying the claim holder's process (1b).** The tool must record the agent's long-lived process, not the
  short-lived shell that ran it; otherwise every claim would look dead at once and be taken over. Safe default: if the
  long-lived process cannot be determined, record no PID, and other agents treat the holder as *unknown*, never
  *dead*.
- **Settled in Phase 1b** (see `skills/development-coordination/references/protocol.md`): process start time comes
  from `/proc/<pid>/stat` on Linux and `ps -o lstart=` (C locale, UTC) elsewhere; the holder is the nearest
  non-wrapper ancestor, with an override limited to ancestors and a null (unknown) fallback; Windows and network
  filesystems report claims as unavailable (unknown) with a manual procedure; across machines, remote branches and PRs
  are signals only. The original questions follow for the record.
- **Process start time (1b).** `ps -o lstart=` output is locale-dependent; Linux has `/proc/<pid>/stat`. The portable
  choice, and the behaviour when neither is readable (the holder's status is then unknown).
- **Windows (1b).** `fcntl` is unavailable; whether `msvcrt.locking` is an adequate substitute, or claims are
  unavailable there and the protocol reports *unknown*.
- **Network filesystems (1b).** Advisory locks may be local-only or emulated on NFS and SMB. Detecting such a checkout
  and reporting claims as unreliable.
- **Several machines (1b).** Beyond the PR-and-branch convention and git's own refusal of non-fast-forward pushes,
  whether any cross-machine signal is worth adding without publishing private state.
- **Handoff refresh before compaction (1c).** Some harnesses offer a pre-compaction hook; others give no warning.
- **Related operations (Phase 2).** How a task is identified for cumulative budget accounting (a PR, a run series, a
  declared task ID), and whether a per-period ledger is needed beyond providers' own spending limits.
- **Hook adapters (1d).** Whether opt-in hook examples live in `instruction-governance`'s references or outside the
  skills.
- **Housekeeping and the core (Phase 4).** Whether `workspace-housekeeping` adopts the generated operational core.
- **Interoperability (Phases 2–3).** Optional export of run manifests to RO-Crate and artifact manifests to in-toto
  statements.

## Revision history

| Revision | Date | Change |
|---|---|---|
| 1 | 2026-11-27 | First draft for owner review (Phase 0) |
| 2 | 2026-11-27 | Owner decisions D1–D13 recorded; architectural corrections (coordination protocol, instruction-governance trust boundary and audit tool, evidence and verification records, shared-state safety); reconciled with PR #18 (merged); family renamed Operational Skills |
| 3 | 2026-11-27 | Final review: D14 (host-recorded approvals as evidence for explicitly scoped standing authorizations); authorization statuses (invalid, unverified, verified, inapplicable, unknown); owner identities and trusted repositories only in the canonical policy; revocation and approval binding; level-1 constraints never overridden; force-exception and R0-deletion limits; identity is not state. Approved |
| 4 | 2026-11-27 | Phase 1a review decisions recorded: approved interpretations, fresh approval for reintroduced authorizations, inapplicable approvals grant nothing, GitHub PR URLs as the initial `approved_in` capability, the 1.25 factor as a reassessment threshold, stale claims require expiry and holder death |
