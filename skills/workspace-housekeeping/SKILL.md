---
name: workspace-housekeeping
description: Keep a multi-project audio-plugin and research workspace recoverable and lean, with private verified backups for unpublished work, whole-bundle preservation of audition and cited binaries with SHA-256 provenance, committed source for qualification runs, frozen evidence changed only by versioned amendment, project-specific retention rules, owner-approved deletion manifests revalidated before execution, at most three persistent build directories, no worktree proliferation and no interruption of concurrent development. Use before creating clones or worktrees, switching branches in a shared checkout, deleting or archiving build directories, caches, research output or audition builds, backing up work in progress, citing a binary or research result, or reporting disk usage and recoverable space.
---

# Workspace Housekeeping

Rules and procedures for keeping a workspace of many projects (plug-ins, research code, simulation outputs) small
without losing evidence. The full policy is in [references/policy.md](references/policy.md). The measurement and
verification recipes are in [references/procedures.md](references/procedures.md).

## Principles

1. **Private backups for unpublished work.** Work in progress, stashes and reflog-only commits from public
   repositories go to a private backup repository as git bundles, never to the public repository.
2. **Independent, verified backups.** A backup counts only when it is on independent storage (not the same SSD, not
   an APFS clone) and has been restored from the remote copy and compared with the original.
3. **Full bundle preservation checks.** A bundle is preserved only when its whole tree matches: paths, contents,
   permission bits and symlink targets, not just the main binary hash.
4. **Project-specific retention rules come first**: protected sets, freeze manifests, "never delete" records.
5. **Manifest-driven destructive operations.** Nothing is deleted or moved except through a written, owner-approved
   manifest, revalidated against the filesystem immediately before execution.
6. **No worktree or clone proliferation.** One checkout per project.
7. **No interruption of concurrent development.** Never switch branches, reset or rebuild in a checkout someone else
   is using. Snapshot their work from a temporary index instead.
8. **Archival integrity is not scientific reproducibility.** An archive keeps exact bytes. Reproducing a result
   needs committed source, recorded inputs and the toolchain. Never present one as the other.

## Workflow

1. **Inventory.** Per project, measure source and `.git`, build directories, research by class, caches, auditions,
   worktrees, unpushed branches, stashes, reflog-only commits and local-only evidence. Use consistent units (GiB)
   and say whether a figure is logical, allocated or recoverable.
2. **Protect before reclaiming.**
   - Push unpushed branches. Before pushing, check for open PRs and CI triggers; use `[skip ci]` or non-branch refs
     where a run would be wasted.
   - Pin stashes and reflog-only commits to `refs/backup/*`.
   - Snapshot uncommitted work without touching the working tree.
   - Bundle public-repo refs into a private backup repository and verify a restore from the remote copy.
3. **Preserve binaries that must survive.** Copy audition, approved and document-cited bundles into
   `<project>/auditions/` (excluded from git). For each, record the full SHA-256 of the executable, a whole-bundle
   digest, build time, codesign status, source commit (verified or inferred), external inputs and citing documents.
   Then archive `auditions/` to independent storage and verify the archive by extraction.
4. **Classify** every candidate for deletion into exactly one class:
   - essential evidence;
   - expensive reproducible;
   - cheap reproducible cache;
   - redundant;
   - unknown.

   Failed experiments cited by a decision are evidence. Caches referenced by an integrity manifest are frozen.
5. **Write the manifest.** For every entry give the path, logical and allocated size, class, reason, references
   checked and regeneration command. Get owner approval.
6. **Revalidate and execute.**
   - Immediately before deleting, check that:
     - the set is unchanged;
     - nothing was written there recently;
     - no open files and no build processes;
     - every bundle has a whole-bundle twin in the preserved set;
     - diagnostic files are preserved;
     - the independent backup is verified.
   - Drop any entry that fails a check, and report it.
   - Delete only the approved literal paths. Then measure the tree's allocated size.
7. **Report:**
   - what was protected, with links;
   - what remains local-only;
   - the preserved binaries and their hashes;
   - the deleted entries and the measured reclaimed space;
   - the blocked items and the remaining risks.

## Pitfalls

- **Duplicates may share blocks.** APFS clones mean that deleting a "duplicate" may free nothing. Count a clone
  group once, and only if every member is deleted. See [procedures](references/procedures.md#apfs-clones-and-recoverable-space).
- **Whole-disk free space is not evidence of reclaimed space** while other processes write to the volume. Measure
  the tree.
- **Compressing frozen evidence in place breaks its hashes.** Archive externally instead.
- **Rebuilt binaries rarely reproduce a cited hash** (embedded timestamps, unversioned assets). Keep cited bundles
  as bundles.
- **Store external build inputs content-addressed.** Assets named by hash in a committed manifest must be stored
  content-addressed, or historical builds become unbuildable.
- **Public repositories never receive backups of unreviewed work.**
