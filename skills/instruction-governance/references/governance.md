# Governing instruction files

## Contents
- [Layers](#layers)
- [Harness conventions](#harness-conventions)
- [Markers and adapters](#markers-and-adapters)
- [Drift detection](#drift-detection)
- [Updating and rolling back](#updating-and-rolling-back)
- [Installed skills](#installed-skills)
- [Ignore rules and evidence](#ignore-rules-and-evidence)
- [Adding a runtime](#adding-a-runtime)

## Layers

| Layer | Where | Who changes it |
|---|---|---|
| Canonical shared instructions | `operational/instructions.md` in this repository (blocks with ids and revisions), copied into this skill as `references/instructions.md` | The owner, through a reviewed PR |
| Harness adapters | Each runtime's global instruction file: canonical blocks between markers, plus the runtime's own text outside them | The owner; agents propose exact diffs |
| Project extensions | A repository's `AGENTS.md` or `CLAUDE.md`: project rules (level 5), never canonical blocks unless the owner chooses to mirror them | The project's maintainers |
| Consultation triggers | The canonical `operational-skills` block: when to consult each operational skill | The owner, as part of the canonical text |

One canonical source keeps the rules identical; adapters stay small, so each harness keeps its own tool notes
(documentation servers, search tools) without forking the shared rules.

## Harness conventions

Audited when this skill was written; `references/adapters.json` records the paths and can be extended.

| Runtime | Global instructions | Project instructions | Skills |
|---|---|---|---|
| Claude Code | `~/.claude/CLAUDE.md` | `CLAUDE.md` (and imports) | `~/.claude/skills/` |
| Codex | `~/.codex/AGENTS.md` (`$CODEX_HOME/AGENTS.md` when set) | `AGENTS.md` | `~/.agents/skills/`, `~/.codex/skills/` |
| OpenCode | `~/.config/opencode/AGENTS.md` | `AGENTS.md` | `~/.config/opencode/skills/`, and Claude-compatible locations |

On the owner's machine at the time of writing, the three global files carried the same ignore rules and housekeeping
rules, but only the Claude Code file had the Git workflow section, and the primary-checkout rule was worded
differently: exactly the drift this skill exists to catch.

## Markers and adapters

```markdown
<!-- policy:begin id=ignore-rules rev=1 sha256=<SHA-256 of the block text> -->
## Git ignore rules (all projects)
...
<!-- policy:end id=ignore-rules -->
```

- The marker records the block's revision and the digest of its text, so a hand edit inside the block is detectable.
- Text outside markers is never read as canonical and never written by the tool.
- First adoption: `policy_audit.py block <id>` prints the marked block; the owner pastes it once, replacing the
  section it supersedes. The tool refuses to insert markers itself.

## Drift detection

`policy_audit.py audit` (read-only) reports, per adapter:

| State | Meaning |
|---|---|
| in-sync | Every expected block present, unedited, at the canonical revision |
| drift | A block is outdated (older revision) or edited by hand (its text no longer matches its marker's digest) |
| missing-markers | An expected block has no markers; the audit says whether its canonical text appears verbatim anyway |
| refused | Malformed, duplicated or unbalanced markers, or a symlinked adapter: nothing is proposed or written |
| absent | The runtime's file does not exist on this machine |

It also reports installed copies of this repository's skills and the account `gh` is authenticated as.

## Updating and rolling back

1. `diff --harness <h>` shows the exact change, limited to marked blocks, and a digest of the file's current bytes
   together with the proposed bytes.
2. The owner reviews it and approves that digest in the session.
3. `apply --harness <h> --approve <digest>` recomputes the change, refuses if the file changed since (or the digest
   differs), keeps the current file under `~/.local/state/agent-operations/instruction-backups/`, and replaces the
   file atomically.
4. `rollback --harness <h> --backup <file> --approve <digest>` restores a kept version the same way (it prints the
   full diff and the digest to approve when none is given). It restores the **whole** kept file, so it also reverts
   any unrelated edit made since that backup: read the diff before approving.

The tool never edits harness settings, installs hooks or skills, or writes outside the adapter it was asked about and
its backup directory.

## Installed skills

The audit compares each installed copy of a skill from this repository with the repository's version (a digest of
every file) and reports in sync, differs, or not installed, per skill root. It never installs or updates a skill:
installation remains the owner's step (`workspace-housekeeping` covers preserving local changes first).

## Ignore rules and evidence

The operational core lets the owner authorize a specific bypass of a refusal (rule 4). Ignore rules are the exception:
the canonical `ignore-rules` block says an authorized exception changes what is kept, never how. Ignored evidence
enters Git only through a narrowly scoped, commented negation pattern, verified with `git check-ignore --no-index`,
never through `git add -f` or plumbing. Evidence preservation is not weakened: what must be kept is kept, locally, in
a private backup, or through an approved negation pattern.

## Installation and verification

1. **Review** the canonical blocks: `policy_audit.py block <id>` prints each, with its markers.
2. **First adoption (the owner, by hand, once per runtime):** in each global instruction file, replace the section a
   block supersedes with the printed marked block, leaving everything else (tool notes, personal rules) untouched.
   The tool never inserts markers.
3. **Verify:** `policy_audit.py audit` reports `in-sync` for that runtime.
4. **Later updates:** a canonical block changes in a reviewed PR; `diff` shows each adapter's exact change and digest;
   the owner approves a digest; `apply` writes it with a backup; `rollback` restores a backup the same way.
5. **Installed skills:** the audit reports each installed copy of this repository's skills as in sync or different;
   reinstalling is the owner's step.

## Proposed changes from the first audit

The read-only audit of the owner's three runtimes found, before adoption:

| Block | Claude Code | Codex | OpenCode |
|---|---|---|---|
| `git-workflow` | Present verbatim, unmarked | Missing | Missing |
| `workspace-housekeeping` | Present without the primary-checkout bullet | Present verbatim, unmarked | Present verbatim, unmarked |
| `ignore-rules` | Present without the two new bullets (no force-add even when authorized; narrow corrections, no silent untracking) | Same | Same |
| `operational-skills` | Missing | Missing | Missing |

Adoption would replace those sections with the four marked blocks in each file, and add the missing ones, leaving
the harness-specific sections (documentation and search tool notes) exactly as they are.

## Adding a runtime

1. Find its global and project instruction files and skill locations in its documentation.
2. Add an adapter entry to `references/adapters.json` naming the file and the canonical blocks it carries.
3. The owner places the markers once; from then on the audit and diffs keep it in line.
