# Integration contract for composable workflows (RFC 0002)

Requirements the owner approved for future composable workflows, recorded so that Phase 1 does not paint them into a
corner. Nothing here is implemented in Phase 1d: no design workflow, no Paperclip integration, no skill authoring.

## Contents
- [Approved requirements](#approved-requirements)
- [The contract a workflow must honour](#the-contract-a-workflow-must-honour)
- [External skill manifest (proposal)](#external-skill-manifest-proposal)

## Approved requirements

1. **Impeccable** is an integral design-quality dependency for user-interface workflows: web applications, desktop
   applications and audio plugin interfaces.
2. **Audio plugin UI workflows** compose Impeccable, the Blender Studio workflows for Claude Code and Codex, the
   Shortwav Labs Blender skills, and platform-specific UI implementation and validation skills.
3. **External dependencies** have identifiable versions, installation verification and, where applicable, health or
   doctor checks.
4. **External skills never override** canonical operational or security policy: they are level-6 guidance in the
   [hierarchy](hierarchy.md).
5. **Portability:** workflows support different agent runtimes and inference providers without losing project state,
   evidence or operational constraints.
6. **Knowledge development:** future skill authoring lets verified lessons become proposed skill improvements (the
   `agent-handoff` lessons and proposals section is the first input). Agents cannot weaken acceptance criteria, amend
   their own authority or adopt unreviewed policy changes.
7. **Later initiatives,** not part of this contract yet: Paperclip integration, provider routing, and the autonomous
   product-development experiment.

## The contract a workflow must honour

- **Invocation:** a workflow names the skills and external tools it requires, by name and minimum version, and checks
  that each is installed (and healthy, where a doctor check exists) before starting. A missing or unhealthy
  dependency stops the workflow with a clear report; it never silently degrades to a weaker path.
- **Precedence:** a workflow step inherits the hierarchy. A design tool's recommendation never overrides the ignore
  rules, the worktree policy or an authorization requirement.
- **Authority:** a workflow grants no authority. Operations above R1 still need the owner's instruction or a standing
  authorization that verifies for the exact operation.
- **Records:** workflows hand over through `agent-handoff` records and coordinate through `development-coordination`
  claims; they keep no hidden state.
- **Portability:** steps describe what to do with standard tools and skills; harness-specific features (hooks, slash
  commands) are optional adapters, never the only path.
- **Evidence:** a workflow's quality gates (for example Impeccable's checks) produce evidence with method, artifact
  and time, as the operational core defines.

## External skill manifest (proposal)

A possible shape for RFC 0002 to refine, not a format defined here:

```json
{ "name": "impeccable", "source": "<registry or repository>", "version": "<semver or commit>",
  "check": "<command that confirms installation>", "doctor": "<command for a health check, if any>",
  "harnesses": ["claude-code", "codex", "opencode"], "role": "design-quality" }
```
