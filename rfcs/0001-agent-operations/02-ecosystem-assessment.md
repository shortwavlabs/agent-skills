# 2. Existing skills and ecosystem assessment

Part of [RFC 0001: Agent Operations](README.md). Status: **draft for owner review**. Sources checked 2026-11-27.

**How to read the labels.**
- **[V]** I fetched or read the source myself during this phase.
- **[R]** A research pass fetched the primary source, and I did not re-fetch it. The URL is given; treat the claim as
  reported until it is re-checked.
- Unlabelled statements about this repository come from reading its files directly.
- Recommendations are ours, and are marked as such. Established practice is cited.

## Contents
- [Repository findings](#repository-findings)
- [workspace-housekeeping findings](#workspace-housekeeping-findings)
- [Overlap with existing skills](#overlap-with-existing-skills)
- [Agent Skills format and activation](#agent-skills-format-and-activation)
- [Instruction files and precedence](#instruction-files-and-precedence)
- [Enforcement versus advice](#enforcement-versus-advice)
- [Session continuity and compaction](#session-continuity-and-compaction)
- [Coordination between agents](#coordination-between-agents)
- [Comparable collections and the name](#comparable-collections-and-the-name)
- [Engineering practice prior art](#engineering-practice-prior-art)
- [Gaps this family fills](#gaps-this-family-fills)

## Repository findings

| Finding | Consequence for this RFC |
|---|---|
| 16 skills under `skills/<name>/`, each with `SKILL.md` (frontmatter `name` and `description` only), `agents/openai.yaml` and usually `references/`; some have `scripts/` | Family skills follow the same layout. No new frontmatter fields are needed |
| `scripts/validate_skills.py` (standard library only) checks frontmatter, `agents/openai.yaml`, relative links and anchors, absolute-path leaks, vendor model text, and runs every script's `--self-test` normally and under `python -O`. CI runs it on every PR and on pushes to `main` | The natural home for Tier 0 checks ([validation strategy](06-validation-strategy.md#tier-0-repository-checks-on-every-ci-run)) |
| The validator scans only `README.md` and `skills/` | A document outside those paths is not link- or leak-checked. Phase 0 runs those checks ad hoc over `rfcs/`; Phase 1a extends the validator |
| `.gitignore` ignores `docs/`. The README's source-documentation lists point to local copies such as `docs/plugdata/` and `docs/vcv/`, which suggests why | Design documents cannot live in `docs/` without changing an ignore rule. This RFC uses `rfcs/` |
| Skills install through `npx skills add shortwavlabs/agent-skills`. Each skill lands in its own directory, and an agent's skill folder may hold only some of them | Each family skill must work alone |
| 107 relative links of the form `../../<other-skill>/...` in 27 files of the existing skills | They resolve only when the sibling skill is installed next to the linking one, in the same folder. The family references siblings by name ([rules](03-responsibility-matrix.md#rules-for-references-between-skills)) |
| No `AGENTS.md` or `CLAUDE.md` in the repository; no skill mentions either | Nothing in the repository yet tells agents when to consult which skill |
| The README already uses "one owner per area" tables for the circuit-modeling skills | The family's README section reuses that style |
| The CI workflow has no `concurrency` group or path filter. It runs one short Linux job | Low cost here. The same pattern on macOS jobs is a cost driver (incident I10) |

## workspace-housekeeping findings

**What it does well.** It already embodies several of this family's principles: a risk-proportional split between
disposable caches and evidence (principle 2), whole-bundle preservation, manifest-driven deletion revalidated before
execution, the distinction between archival integrity and reproducibility (principle 8), and the rule that
retrospective commits are not historical provenance (principle 9). Its R3-style deletion procedure is the model for
the family's [R3 requirements](04-risk-and-authorization.md#requirements-per-level).

**Overlaps.** Policy §1, §3 and §4 and principles 6 and 7 cover ground the proposed coordination, provenance and
release skills will own. The [responsibility matrix](03-responsibility-matrix.md#overlaps-with-workspace-housekeeping)
gives each overlap an owner now, an owner later, and the migration that needs approval.

**Defects and tensions found** (not fixed in Phase 0):

1. **A name-filtered process check.** The procedure for removing a worktree says to check every process "without
   truncating the list", then gives a command that lists only processes matching
   `node|vite|cargo|python|cmake` (`references/procedures.md`, "Removing a worktree or checkout", step 3). A `ninja`,
   `make`, `bun`, `java` or agent process inside the worktree would be missed. It is the same class of gap as incident
   I6 (a partial process list), whatever that incident's exact cause was. **It is our main argument for turning such
   checks into tested scripts:** prose said "complete", and the example did not match it.
2. **Every deletion needs a manifest** (policy §6.1), including disposable caches that need no backup (principle 2).
   Read literally, deleting your own scratch build directory during development needs a written, owner-approved
   manifest. The family's risk model would put that at R0 or R1. The owner should decide whether §6.1 is meant for
   cleanups or for every deletion.
3. **Domain- and machine-specific wording.** "Audio-plugin and research workspace", APFS clone accounting, a macOS
   keychain command and the owner's approved external disk are specific to one workspace. They are correct there, but
   they clash with the family's domain-agnostic and portable principles.
4. **It restates the owner's global instructions** (policy preamble). Every restatement is another copy that can drift
   from the source (incident I8).

## Overlap with existing skills

A read-only audit of the other 15 skills found substantial operational guidance, all of it domain-scoped. Items
marked **✓** were opened and checked during this phase. The others are reported by the audit and were not
re-checked.

| Concern | Where it already appears |
|---|---|
| Evidence classes and fact labels | `circuit-to-dsp`: maturity levels ✓, four independent result axes. `juce-plugin`: fact classes (tested, source-derived with version, vendor facts with a check date) ✓. `bbd-modeling`: fact classification, hash-frozen criteria, retained failures. `guitar-gear-qa`: frozen visual oracle |
| Changing criteria | `circuit-to-dsp`: a criterion changes only by documented revision, with old and new definition, evidence and a before/after table, and no expected-failure markers ✓. `bbd-modeling`: an authorized numerical change needs an owner-approved error budget and a re-freeze, with superseded references kept ✓. `spice-circuit-modeling`: clean-machine reproducibility is reported as pending until a clean machine has run it ✓; change records for oracle edits |
| Release gates and identity | `juce-plugin`: a status of "implemented but not yet fully qualified" for unexecuted release procedures ✓; release gates, signing and notarization, install qualification, CI evidence where NOT RUN never counts as a pass. `circuit-to-dsp`: release tiers, artifact inventory, release classes. `vcv-rack-plugin`: version checks on tags |
| Cost | `juce-plugin`: runner prices per OS, macOS about 10× Linux ✓. `circuit-to-dsp`: don't re-run hours of SPICE for a checksum fix when hashes match ✓. `guitar-product-render`: cheap preview before an expensive render |
| Reports for the next agent | `juce-plugin`: the performance report keeps rejected candidates as engineering knowledge ✓, and a rejected-approaches table records dead ends for the next agent ✓. `guitar-gear-modeling`: an accepted-constraints ledger ✓ |
| Version-pinned workarounds and omissions | `juce-plugin`: examples scoped to a named framework version, with a "recheck for another version" column ✓. `circuit-to-dsp`: omission register ✓. `bbd-modeling`: research agenda, known limitations |
| Concurrency | Nothing found on concurrent agents, shared-checkout ownership or process ownership. Isolated hints only: two simultaneous Blender bakes crashed; mount the repository read-only in Docker |

**Tensions between skills** that the family should resolve rather than add to:
- **Clones and worktrees ✓:** `spice-circuit-modeling` (clean-machine regeneration from a new clone) and
  `bbd-modeling` (reproduce a reference binary's hash from a clean worktree of the cited commit) versus
  `workspace-housekeeping` (no unauthorized clones or worktrees). Neither side mentions the other.
- **Build directories ✓:** `guitar-dsp` proposes four build presets; `workspace-housekeeping`'s default limit is
  three. Housekeeping's exceptions may cover the difference; nothing says so.
- **Status vocabularies (audit-reported):** NOT EVALUATED, NOT MET, NOT RUN, NOT CHECKED, PENDING, UNRESOLVED and
  others, each defined locally; the letters A to D reportedly mean three different things in three references.
- **Change terminology:** "versioned amendment" (`workspace-housekeeping`, which also requires owner approval) ✓ and
  "documented revision" (`circuit-to-dsp`, which requires evidence) ✓, plus appended revisions, release classes and
  fixture versions elsewhere (audit-reported).

Recommendation (ours): the family introduces one evidence-label set and one amendment record, and the domain skills
may adopt them in Phase 4 where nothing is lost. The family does not rewrite domain vocabularies.

## Agent Skills format and activation

- **[V] Specification fields.** `name` (at most 64 characters, lowercase letters, digits and hyphens, matching the
  folder) and `description` (at most 1024 characters, what the skill does and when to use it) are required.
  `license`, `compatibility` (at most 500 characters), `metadata` and an experimental `allowed-tools` are optional.
  ([specification](https://agentskills.io/specification))
- **[V] Progressive disclosure.** Metadata (about 100 tokens) loads at start-up; the `SKILL.md` body loads on
  activation, with under 5000 tokens recommended; resources load only when needed. The specification recommends
  keeping `SKILL.md` under 500 lines. File references use relative paths from the skill root and stay one level
  deep. (same source)
- **[V] Installation is not activation.** "A skill only helps if it gets activated." The description alone decides
  whether an agent loads the skill, and agents tend to consult skills only for tasks they could not handle with
  their basic tools. The guide recommends about 20 trigger queries, half of them near-misses.
  ([optimizing descriptions](https://agentskills.io/skill-creation/optimizing-descriptions))
- **Consequence (ours).** Operational skills are exactly the kind an agent believes it can do without: anyone can
  switch a branch or delete a directory. Description matching alone will under-trigger them. Mandatory consultation
  triggers in instruction files, and harness enforcement for hard rules, are therefore part of the design, not
  extras. This is why `instruction-governance` is P0.
- **[R] Client support.** Claude Code, Codex, OpenCode, Gemini CLI, Cursor and GitHub Copilot document Agent Skills
  support, with differing discovery folders (`.claude/skills`, `.agents/skills`, `.github/skills`, …) and catalogue
  size limits. Codex's optional `agents/openai.yaml` (display name, default prompt, `allow_implicit_invocation`)
  matches this repository's convention. Sources:
  [Claude Code](https://code.claude.com/docs/en/skills), [Codex](https://learn.chatgpt.com/docs/build-skills),
  [OpenCode](https://opencode.ai/docs/skills), [Cursor](https://cursor.com/docs/context/skills),
  [Copilot](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills),
  [Gemini CLI](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/skills.md).
- **[R] Catalogue budgets.** Claude Code drops the descriptions of the least-used skills when the listing exceeds its
  budget; Codex caps its catalogue at a share of the context. Seven more skills compete for that space, which argues
  for few, sharply described skills.

## Instruction files and precedence

- **[V] AGENTS.md** is plain Markdown, now stewarded by the Agentic AI Foundation under the Linux Foundation. "The
  closest AGENTS.md to the edited file wins", and explicit chat instructions from the user override every file.
  ([agents.md](https://agents.md))
- **[V] Claude Code** concatenates `CLAUDE.md` files from the filesystem root down to the working directory rather
  than letting one override another; imports (`@path`) recurse at most four hops. By default it reads `AGENTS.md`
  only when no `CLAUDE.md` or `CLAUDE.local.md` exists in the working directory or above (the user-level file does
  not count), and recommends importing `AGENTS.md` from `CLAUDE.md` where it cannot read it directly.
  ([memory](https://code.claude.com/docs/en/memory))
- **[R] Precedence differs by tool.** Codex concatenates a global file and one file per directory from the root down,
  capped at 32 KiB by default, with `AGENTS.override.md` taking a directory's slot
  ([Codex AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)). OpenCode combines files without
  resolving conflicts between them, falling back to `CLAUDE.md` ([rules](https://opencode.ai/docs/rules)). Gemini CLI
  concatenates `GEMINI.md` files and supports imports
  ([GEMINI.md](https://github.com/google-gemini/gemini-cli/blob/main/docs/cli/gemini-md.md)). Cursor uses rule files
  with its own ordering ([rules](https://cursor.com/docs/context/rules)).
- **Consequence (ours).** No tool resolves a conflict between two instructions. Most simply concatenate them and leave
  the model to choose. "Closest file wins" is AGENTS.md's convention, not a universal rule. A canonical-policy design
  must therefore (a) avoid conflicts rather than rely on precedence, and (b) state its own conflict rule in the text
  every agent reads.
- **Observed in this phase.** The owner's agent-specific instruction files are maintained by hand and currently
  differ. This is incident I8, still live.

## Enforcement versus advice

- **[V] Instruction files are advisory.** Claude Code's documentation says `CLAUDE.md` files are not enforced
  configuration, and points to a PreToolUse hook for blocking an action whatever the model decides.
  ([memory](https://code.claude.com/docs/en/memory))
- **[R] Hooks and permissions.** Claude Code's PreToolUse hooks can deny a tool call, and deny rules take precedence
  over allow rules ([hooks](https://code.claude.com/docs/en/hooks), [permissions](https://code.claude.com/docs/en/permissions)).
  Codex hooks exist, but its documentation presents them as a guardrail rather than a complete enforcement boundary
  ([hooks](https://learn.chatgpt.com/docs/hooks)). Git's `pre-commit` hook can be skipped with `--no-verify`
  ([githooks](https://git-scm.com/docs/githooks)); server-side protection (branch protection, CI) is the stronger
  gate.
- **[V] Codex sandbox.** In the default workspace-write sandbox, `.git` (and `.agents`, `.codex`, `.aws`) inside a
  writable root is read-only, recursively. ([approvals and security](https://learn.chatgpt.com/docs/agent-approvals-security))
  **Consequence:** shared coordination state cannot live under `.git/`. This RFC puts it in an excluded
  `.agent-state/` directory ([location rule](05-artifact-conventions.md#location-rule)).
- **Our enforcement ladder**, from weakest to strongest: prose in a skill → a mandatory trigger in an instruction file
  → a deterministic script the skill tells the agent to run → a harness hook or deny rule → a server-side gate. The
  family uses the strongest rung that is practical for each rule and says plainly which rung a rule is on.

## Session continuity and compaction

- **[R] Anthropic, long-running agents.** An initializer session writes a progress file, a JSON feature list whose
  items start as failing, and an initial commit; later sessions read progress and git log, test, work on one item,
  commit and update progress. JSON was chosen because the model is less likely to overwrite it inappropriately than
  Markdown. Compaction alone was not enough.
  ([effective harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents))
- **[R] Context engineering.** Compaction, structured note-taking and sub-agents are the three named techniques.
  ([context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents))
- **[R] What survives compaction in Claude Code:** the project-root `CLAUDE.md`, the plan and skill descriptions are
  re-injected; nested instruction files are summarized away until they reload.
  ([context window](https://code.claude.com/docs/en/context-window))
- **[R] OpenAI ExecPlans:** a self-contained living plan with mandatory progress, discoveries, decision-log and
  outcome sections, written so that work can always restart from the plan alone. The cookbook article is archived.
  ([ExecPlans](https://developers.openai.com/cookbook/articles/codex_exec_plans))
- **[R] Structured handoffs outside software.** The I-PASS handoff bundle reduced medical errors by 23% and
  preventable adverse events by 30% in a nine-hospital study, without lengthening handoffs (Starmer et al., NEJM
  2014; [PubMed](https://pubmed.ncbi.nlm.nih.gov/25372088/)). The effect is for the whole bundle (mnemonic, training,
  observation), not a template alone. Its elements map well onto agent handoffs: severity first, a summary, an action
  list with owners, if-then contingencies, and **synthesis by the receiver**. SRE incident handoffs likewise transfer
  command explicitly and keep one living document ([SRE book](https://sre.google/sre-book/managing-incidents/)).
- **Consequence (ours).** The handoff record is a structured, living file refreshed at milestones, and the receiver's
  first action is verification against the repository: the agent equivalent of I-PASS's receiver synthesis.

## Coordination between agents

- **[R] Vendors recommend worktrees for parallel agents** ([Claude Code](https://code.claude.com/docs/en/worktrees),
  [Codex](https://learn.chatgpt.com/docs/environments/git-worktrees)). This conflicts with owners who forbid
  unauthorized worktrees, as this workspace's policy does. The family supports both: one writer at a time in a shared
  checkout, or authorized isolation.
- **[R] Claude Code agent teams** (experimental) share a task list and claim tasks through file locking, and warn
  that two teammates editing the same file overwrite each other ([agent teams](https://code.claude.com/docs/en/agent-teams)).
- **[R] mcp_agent_mail** gives agents identities, inboxes and advisory file leases with a time-to-live
  ([repository](https://github.com/Dicklesworthstone/mcp_agent_mail)). It is a service, which the family's portability
  principle avoids requiring.
- **[R] Leases and advisory locks.** A lease grants rights for a limited term, so a failed holder blocks others only
  until it expires (Gray and Cheriton, SOSP 1989; [ACM](https://dl.acm.org/doi/10.1145/74851.74870)). `flock` locks
  are advisory ([man page](https://man7.org/linux/man-pages/man2/flock.2.html)).
- **Consequence (ours).** No vendor documents a cross-agent claim protocol. A file-based, advisory lease in the
  checkout, combined with an activity check that does not depend on cooperation, is the lightest design that works
  across agents without a service.

## Comparable collections and the name

| Collection | Covers | Overlap with this family |
|---|---|---|
| [obra/superpowers](https://github.com/obra/superpowers) [R] | Planning, worktrees, finishing a branch, verification before completion, code review, debugging; a start-up hook forces its bootstrap skill to load | Coordination (it **recommends** worktrees) and branch completion. No provenance, budget, debt or instruction governance |
| [boshu2/agentops](https://github.com/boshu2/agentops) [R] | Presents itself as DevOps discipline for coding agents: planning, research, memory, orchestration, validation, postmortems, session handoff | High overlap with handoff and coordination, based on its README only |
| [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) [R] | Includes ADRs, shipping and launch, git workflow, context engineering | Possible overlap with release and debt; skill names only were checked |
| [anthropics/skills](https://github.com/anthropics/skills) [R] | Document, creative and development examples | None |
| Several single handoff and ADR skills [R] | Session handoff notes; ADR templates | Handoff; decision records |

**[R] Not found:** dedicated skills for resource budgets, release governance, research provenance or instruction
governance. One round of searching found none. That is weak evidence, not proof that none exist.

**[R] The name "AgentOps" is taken three times:** a skills collection for coding agents in this exact category
([boshu2/agentops](https://github.com/boshu2/agentops)), Microsoft's AgentOps accelerator
([Azure/agentops](https://github.com/Azure/agentops)), and an agent observability product
([AgentOps-AI/agentops](https://github.com/AgentOps-AI/agentops)). See [decision D1](README.md#d1-the-family-name).

## Engineering practice prior art

What we take is deliberately small. "Established" means a standard, a canonical book or paper, or official
documentation.

| Practice | Source | Status | What we take | What we leave |
|---|---|---|---|---|
| Reversible vs irreversible decisions | Amazon 2015 shareholder letter, Type 1 and Type 2 decisions ([SEC filing](https://www.sec.gov/Archives/edgar/data/1018724/000119312516530910/d168744dex991.htm)) [R] | Canonical | Reversibility as the first risk dimension; the failure mode of heavy process on reversible decisions | — |
| Changes cause most incidents | Google SRE book, introduction: roughly 70% of outages are attributed to changes in a live system ([SRE](https://sre.google/sre-book/introduction/)) [R] | Canonical | Gate changes to shared state, not every action | Service-specific practice |
| Toil | SRE book ([toil](https://sre.google/sre-book/eliminating-toil/)) [R] | Canonical | The family's own ceremony must not become toil (overhead limits) | — |
| Change categories | ITIL standard, normal and emergency changes (concept only; primary text not consulted) [R] | Industry framework | Standing authorizations are ITIL's pre-authorized standard changes | The rest of ITIL |
| Impact levels | NIST FIPS 199, low, moderate, high ([PDF](https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.199.pdf)) [R] | Standard | Integrity and availability of evidence as a risk dimension | The security-categorization process |
| Build provenance | SLSA v1.2 provenance: `buildDefinition` (build type, external parameters, resolved dependencies) and `runDetails` (builder, metadata, byproducts) ([SLSA](https://slsa.dev/spec/v1.2/build-provenance)) [R] | Standard | Field names for the artifact manifest. Agent-written records are at most SLSA Build L1 grade, and are labelled so | Signed attestations; build levels above L1 (projects use CI tooling) |
| Attestations | in-toto statement: subject by digest plus a typed predicate ([in-toto](https://github.com/in-toto/attestation/blob/main/spec/README.md)) [R] | Standard | Identify artifacts by digest; typed records (`kind`) | Envelopes, signing |
| Reproducible builds | Same source, environment and instructions give bit-identical artifacts ([definition](https://reproducible-builds.org/docs/definition/)) [R] | Community standard | The distinction between integrity and reproducibility; record the environment | Requiring reproducibility |
| Versions | SemVer 2.0.0: released contents never change; pre-releases like `-rc.1` rank below the release ([semver.org](https://semver.org/)) [R] | De facto standard | Immutable release candidates; a fix is `-rc.2` | — |
| Build once, promote | Humble and Farley, *Continuous Delivery*: build binaries only once ([excerpt](https://www.informit.com/articles/article.aspx?p=1621865&seqNum=3)) [R] | Canonical | Promote the approved bytes; never rebuild for release | Pipeline tooling |
| Release engineering | SRE book ([release engineering](https://sre.google/sre-book/release-engineering/)) [R] | Canonical | Hermetic builds; known contents of every release; rollback readiness | — |
| Decision records | Nygard 2011 ADRs ([post](https://www.cognitect.com/blog/2011/11/15/documenting-architecture-decisions)); MADR 4.0 with a "confirmation" section ([MADR](https://github.com/adr/madr)) [R] | Community practice | Status lifecycle; superseded records kept; a checkable confirmation | A mandatory ADR practice (projects keep theirs) |
| Technical debt | Cunningham, OOPSLA 1992 ([c2](http://c2.com/doc/oopsla92.html)); Fowler's debt quadrant ([bliki](https://martinfowler.com/bliki/TechnicalDebtQuadrant.html)) [R] | Canonical metaphor | Debt is acceptable if tracked and repaid; deliberate vs inadvertent | A debt-scoring methodology (no standard register exists) |
| Reproducibility terms | ACM Artifact Review and Badging v1.1: repeatability, reproducibility, replicability ([ACM](https://www.acm.org/publications/policies/artifact-review-and-badging-current)) [R] | Professional standard | Vocabulary for what a result claims | Badging |
| Computational provenance | Sandve et al. 2013, *Ten Simple Rules for Reproducible Computational Research* ([PLOS](https://doi.org/10.1371/journal.pcbi.1003285)) [R]; W3C PROV ([primer](https://www.w3.org/TR/prov-primer/)) [R] | Canonical; standard | Record how every result was produced, exact versions, seeds; PROV's entity, activity and agent vocabulary | RDF; RO-Crate packaging (optional for projects) |
| Preregistration | Nosek et al., PNAS 2018 ([PNAS](https://www.pnas.org/doi/10.1073/pnas.1708274114)); Registered Reports ([COS](https://www.cos.io/initiatives/registered-reports)) [R] | Canonical | Criteria fixed before results; exploratory vs confirmatory; negative results published | Journal processes |
| Reporting compute | NeurIPS paper checklist: compute per run and for the whole project, including failed runs ([checklist](https://neurips.cc/public/guides/PaperChecklist)) [R] | Venue policy | Record cost for failed and preliminary runs too | — |
| Cost management | FinOps Foundation phases: inform, optimize, operate ([FinOps](https://www.finops.org/framework/phases/)) [R] | Industry framework | Visibility before optimization; alerts versus hard caps | Organizational roles |
| CI cost | GitHub runner pricing: Linux 2-core $0.006, Windows $0.010, macOS $0.062 per minute ([pricing](https://docs.github.com/en/billing/reference/actions-runner-pricing)) [V]; concurrency groups with `cancel-in-progress` ([docs](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)) [R] | Vendor docs | Estimates from current prices, never hard-coded multipliers; concurrency and path filters | — |
| Ownership signals | GitHub CODEOWNERS ([docs](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-code-owners)) [R] | Vendor docs | Read ownership files before editing others' paths | — |

**Our synthesis, not a source:** no source defines four risk levels (FIPS 199 has three, ITIL three, Amazon two).
Four levels are a design choice: they separate "shared but reversible" (R1, where an automated preflight is enough)
from "consequential" (R2, where the owner is asked), which is the line that matters most for keeping agents fast.

## Gaps this family fills

1. **Cross-agent coordination on one checkout** without a service: nothing documented works across tools.
2. **Instruction governance:** tools concatenate instructions and resolve no conflicts, and owners maintain adapter
   copies by hand.
3. **Research provenance for agents:** domain skills have it for circuits; nothing general exists for benchmarks,
   ML runs or numerical experiments run by agents.
4. **Cost awareness before launching work:** no skill found.
5. **Domain-agnostic release decisions:** the procedures exist per domain, the decision layer does not.
6. **Reassessment of version-pinned workarounds:** recurring in the domain skills, tracked nowhere.
