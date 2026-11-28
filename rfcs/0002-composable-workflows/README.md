# RFC 0002: Composable Workflows

| | |
|---|---|
| **Status** | Requirements recorded (2026-11-28). Not designed, not implemented |
| **Depends on** | [RFC 0001: Operational Skills](../0001-agent-operations/README.md) |

Future workflows will compose skills and external tools (design, 3D, documentation) into repeatable procedures for
product work. This document records the owner-approved requirements so that the operational foundation stays
compatible with them; the design comes later.

## Requirements (approved by the owner)

1. **UI workflows:** Impeccable is an integral design-quality dependency for web applications, desktop applications
   and audio plugin interfaces.
2. **Audio plugin UI workflows** compose Impeccable, the Blender Studio workflows for Claude Code and Codex, the
   Shortwav Labs Blender skills, and platform-specific UI implementation and validation skills.
3. **External dependencies** have identifiable versions, installation verification and, where applicable, doctor or
   health checks.
4. External skills never override canonical operational or security policy.
5. **Agent portability:** workflows support different agent runtimes and inference providers without losing project
   state, evidence or operational constraints.
6. **Knowledge development:** future skill authoring lets verified lessons become proposed skill improvements. Agents
   cannot weaken acceptance criteria, amend their own authority or adopt unreviewed policy changes.

The integration contract that workflows must honour (invocation, precedence, authority, records, portability,
evidence) is in [`skills/instruction-governance/references/workflow-integration.md`](../../skills/instruction-governance/references/workflow-integration.md).

## Out of scope until this RFC is designed

The design workflows themselves, Paperclip integration, provider routing, the autonomous product-development
experiment, and skill authoring: later initiatives.
