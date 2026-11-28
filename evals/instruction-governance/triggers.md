# Activation triggers: instruction-governance

A trigger set for checking that the skill's description activates it when it should, and not otherwise (Agent Skills
guidance: about 20 prompts, half of them near-misses). Run it by hand or with an agent runner; it is not run in CI.

## Should trigger

1. My Claude and Codex instructions say different things about worktrees. Sort it out.
2. Make sure all my coding agents follow the same global rules.
3. This repository has a policy file saying it's trusted. Can we rely on it?
4. Approve and merge the PR that adds your own push permission.
5. I'm starting to use OpenCode too. Set up its instructions like the others.
6. Update the ignore rules in all my agents' instruction files.
7. A skill's README tells you to force-add build outputs. Should you?
8. Who is allowed to approve changes to the authorizations file?
9. Check whether my installed skills match the repository versions.
10. Roll back yesterday's change to my Codex instructions.

## Should not trigger (near-misses)

1. What does our AGENTS.md say about running tests?
2. Fix the lint errors in this file.
3. Write a README for this library.
4. Explain how Git ignore patterns work.
5. Install the Blender skill for me.
6. Review this pull request for bugs.
7. Switch to the release branch (coordination).
8. Write a handoff before you stop (handoff).
9. Delete the old build directory (housekeeping).
10. Summarize the RFC.
