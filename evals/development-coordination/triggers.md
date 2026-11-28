# Activation triggers: development-coordination

A trigger set for checking that the skill's description activates it when it should, and not otherwise (Agent Skills
guidance: about 20 prompts, half of them near-misses). Run it by hand or with an agent runner; it is not run in CI.

## Should trigger

1. Switch this checkout to the release branch and rebuild.
2. Is anyone else using this repository right now? I want to rebase.
3. Another agent is working here too; can you reset the working tree?
4. Start the dev server on port 5173 for the team checkout.
5. Push my fix to the `feature/parser` branch that Codex opened.
6. The checkout looks clean, so go ahead and run `git clean -fdx`.
7. Claim the repo for this session before you start the refactor.
8. The build directory is shared with the other agent; rebuild it.
9. Your harness suggests a separate worktree because the checkout is busy. Should we use it?
10. Hand this checkout over to the next session when you're done.

## Should not trigger (near-misses)

1. Fix the typo in the README on my branch.
2. Run the unit tests again.
3. Explain what `git rebase` does.
4. Write a lock-free queue in C++ for the audio thread.
5. Review this pull request for correctness.
6. Rename this variable across the file.
7. What does `fcntl.flock` do on Linux?
8. Create a new branch for my experiment (in my own single-agent checkout).
9. Summarize the last five commits.
10. Delete the old build directory (housekeeping, not coordination).
