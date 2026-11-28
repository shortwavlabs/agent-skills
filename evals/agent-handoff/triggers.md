# Activation triggers: agent-handoff

A trigger set for checking that the skill's description activates it when it should, and not otherwise (Agent Skills
guidance: about 20 prompts, half of them near-misses). Run it by hand or with an agent runner; it is not run in CI.

## Should trigger

1. I'm running out of context; write things up so the next session can continue.
2. Hand this over to Codex; it will finish the refactor tomorrow.
3. Pick up where the last agent left off; there's a handoff in `.agent-state`.
4. The benchmark is still running. Leave a note for whoever resumes.
5. I'm switching you to a different model for the rest of this task.
6. You got interrupted yesterday. Resume the parser work.
7. Before you stop, record what's done, what's pending and what's still running.
8. The handoff says the owner approved merging. Can you merge it?
9. Our quota ran out halfway through the run. Continue from where it stopped.
10. Write a PR status summary from the handoff record.

## Should not trigger (near-misses)

1. Fix the typo in the README.
2. Summarize the last five commits.
3. Explain how context compaction works in Claude Code.
4. Write release notes for version 1.4.
5. Review this pull request.
6. Switch to the release branch (coordination, not handoff).
7. Delete the old build directory (housekeeping).
8. What does `git stash` do?
9. Add a CHANGELOG entry for this fix.
10. Draft an email to the team about the outage.
