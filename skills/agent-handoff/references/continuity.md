# Continuity across harnesses and interruptions

## Contents
- [Events](#events)
- [Harnesses](#harnesses)
- [Long-running jobs](#long-running-jobs)
- [Lessons, skill defects and proposals](#lessons-skill-defects-and-proposals)

## Events

| Event | Warning | What the record must already say | On resume |
|---|---|---|---|
| Context compaction | Sometimes (a pre-compaction hook, or the agent noticing) | Everything below; refresh it when compaction is near | Re-read the record, not the compacted summary, for decisions and references |
| Interruption by the owner | None | The last milestone | `check`, then ask what changed |
| Provider outage, crash, network loss | None | The last milestone | `check`; jobs may still be running |
| Quota or budget exhaustion | Rarely | Spend so far under Budget | Do not resume paid work until the owner confirms the budget |
| Model switch (same harness) | Yes | As for a new agent: the record, not memory, carries the state | Full resumption; verification does not transfer between models either |
| Agent switch (Claude Code, Codex, OpenCode) | Yes | Transfer token for the claim; commands spelled out | Full resumption |
| Machine restart | Sometimes | Jobs with host, PID and start time | Recorded local jobs show as ended; check their outputs |

Because the worst events give no warning, refresh the record at milestones: after a commit, a result, a decision or
before starting anything long.

## Harnesses

- **Claude Code** and **Codex** document a `PreCompact` hook. An owner may configure one to remind the agent to
  refresh its record; this skill never installs hooks or edits harness settings (`instruction-governance` documents
  opt-in adapters). Both can resume sessions, but a resumed session still runs `check`: the repository may have moved.
- **OpenCode**: no pre-compaction hook was established when this skill was written; rely on milestones.
- All three read Agent Skills and the repository's instruction files, so the commands here work unchanged. Spell out
  commands in Pending and Resume: the next agent may not share your aliases or memory.

## Long-running jobs

- Record each job as JSON (id, kind, command, started, host, PID and start time, log, outputs, how to stop it, cost)
  under `## Running processes and jobs`.
- The receiving agent never restarts, duplicates or stops a job because of the record. `check` says whether a local
  job still runs (PID **and** start time match) or has ended.
- A finished expensive job is evidence to read, not work to repeat: compare its outputs and inputs by digest.
- A job that must not outlive the owner's attention (paid compute) belongs under Blockers with its cost.

## Lessons, skill defects and proposals

An optional `## Lessons and proposals` section is the extension point for knowledge worth keeping beyond the task.
Each item is labelled and points somewhere; nothing is acted on automatically:

```markdown
## Lessons and proposals
- [OBSERVED] Lesson: the sweep needs 6 GiB per worker; see results/sweep-a/run.log
- [VERIFIED] Skill defect: <skill> <what it got wrong>; method: <command that shows it>; artifact: commit <id>; at: <time>
- [INFERRED] Proposal: record the dataset digest in the run manifest (premises: two runs differed only in data)
```

The owner decides whether a lesson becomes an instruction, a skill change or an issue. This skill does not write
skills, instructions or automation.
