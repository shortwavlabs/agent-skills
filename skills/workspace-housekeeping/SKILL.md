---
name: workspace-housekeeping
description: Keep a multi-project audio-plugin and research workspace recoverable and lean without blocking development. Covers private verified backups for unpublished work (git bundles, Restic), never publishing unreviewed work, whole-bundle preservation of audition and cited binaries with SHA-256 provenance, research provenance and frozen evidence, project-specific retention rules, owner-approved deletion manifests revalidated before execution, at most three persistent build directories, no unauthorised worktrees or duplicate checkouts, and APFS-aware recoverable space. Use before creating clones or worktrees, switching branches in a shared checkout, deleting or archiving build directories, caches, research output or audition builds, backing up work in progress, citing a binary or research result, or reporting disk usage.
---

# Workspace Housekeeping

Rules and procedures for keeping a workspace of many projects (plug-ins, research code, simulation outputs) small
without losing evidence or getting in the way of development:
- the full policy: [references/policy.md](references/policy.md);
- the commands and verification recipes: [references/procedures.md](references/procedures.md);
- the in-use check before any removal or deletion: [scripts/path_in_use.py](scripts/path_in_use.py).

## Principles

1. **Never publish unreviewed work.** Work in progress, stashes and reflog-only commits from public repositories go
   to a private backup repository as git bundles. Never push them to the public repository, including as a
   "preservation" push. Public remotes get only commits the owner approved for publication.
2. **Back up what cannot be regenerated, and verify the backup.**
   - **Irreplaceable or expensive data** needs an independent copy (not the same SSD, not an APFS clone), restored
     and compared before anything it protects is deleted. Bulk data goes to Restic on the owner's external disk.
   - **Demonstrably disposable caches** need no backup: reproducible from committed source and recorded inputs, and
     not referenced by any document, manifest, verifier or project rule.
3. **Full bundle preservation checks.** A bundle is preserved only when its whole tree matches: paths, contents,
   permission bits and symlink targets.
4. **Project-specific retention rules come first**: protected sets, freeze manifests, "never delete" records.
5. **Manifest-driven destructive operations.** Nothing is deleted or moved except through a written, owner-approved
   manifest, revalidated against the filesystem immediately before execution.
6. **No unauthorised worktrees or duplicate checkouts.** One checkout per project. Agents do not create worktrees
   (including tool-managed `.claude/worktrees/`), clones or copies without explicit authorisation.
7. **Do not interrupt or needlessly block development.**
   - Never switch branches, reset or rebuild in a checkout someone is using.
   - Keep working environments and primary builds.
   - Run destructive steps when the project is idle.
8. **Archival integrity is not scientific reproducibility.** An archive keeps exact bytes. Reproducing a result
   needs committed source, recorded inputs and the toolchain.
9. **Retrospective commits are not historical provenance.** Code committed after the fact is preservation, not
   proof of what produced earlier results.

## Workflow

1. **Inventory.** Per project, measure:
   - source and `.git`, build directories, research by class, caches, auditions;
   - worktrees (including agent-generated ones), unpushed branches, stashes, reflog-only commits;
   - local-only evidence without an independent backup.

   Use consistent units (GiB) and say whether a figure is logical, allocated or recoverable.
2. **Protect before reclaiming.**
   - Push unpushed branches only to remotes where the commits are approved for publication. Check for open PRs and
     CI triggers first.
   - Pin stashes and reflog-only commits to `refs/backup/*`.
   - Snapshot uncommitted work without touching the working tree.
   - Bundle public-repo refs into a private backup repository and verify a restore from the remote copy.
3. **Preserve binaries that must survive.**
   - Copy audition, approved and document-cited bundles into `<project>/auditions/` (excluded from git).
   - For each, record the executable's SHA-256, a whole-bundle digest, build time, codesign status, source commit
     (verified or inferred), external inputs and citing documents.
   - Back up `auditions/` independently and verify the restore.
4. **Classify** every candidate into exactly one class:
   - essential evidence;
   - expensive reproducible;
   - disposable cache;
   - redundant;
   - unknown.

   Failed experiments cited by a decision are evidence. Caches referenced by an integrity manifest are frozen.
5. **Write the manifest.** For every entry give the path, logical and allocated size, class, reason, references
   checked and regeneration command. Get owner approval.
6. **Revalidate and execute.**
   - Immediately before deleting, check that:
     - the set is unchanged and nothing was written recently;
     - **no process uses it**: `scripts/path_in_use.py` reports CLEAR, having checked the working directories and
       open files of every process (UNKNOWN blocks the entry like IN USE);
     - every bundle has a whole-bundle twin in the preserved set;
     - diagnostic files are preserved;
     - the backups required by principle 2 are verified.
   - Drop any entry that fails a check, and report it.
   - Delete only the approved literal paths, with the project's own tool where one exists. Then measure the tree.
7. **Report:**
   - what was protected, with links;
   - what remains local-only;
   - the preserved binaries and their hashes;
   - the deleted entries and the measured reclaimed space;
   - the blocked items and the remaining risks.

## Pitfalls

- **A truncated process list hides dev servers.** So does a filter on process names. Removing a worktree under a
  running dev server orphans it, and its file watcher may recreate files in the deleted path. Check every process's
  working directory and open files first, with `scripts/path_in_use.py`.
- **Never force a worktree removal.** Plain `git worktree remove` already handles ignored files. Its refusals protect
  modified, untracked or locked work: investigate them.
- **"Preservation" pushes publish.** A push to a public repository makes work in progress public, whatever the
  intent.
- **Duplicates may share blocks.** On APFS, deleting a "duplicate" may free nothing. See
  [procedures](references/procedures.md#apfs-clones-and-recoverable-space).
- **Whole-disk free space is not evidence** while other processes write to the volume. Measure the tree.
- **Compressing frozen evidence in place breaks its hashes.** Back up and archive externally.
- **Rebuilt binaries rarely reproduce a cited hash.** Keep cited bundles as bundles.
- **Store external build inputs content-addressed.** Assets named by hash in committed manifests must be stored that
  way, or historical builds become unbuildable.
- **Extracted copies keep read-only permissions.** `chmod -R u+w` your own scratch extraction before removing it.
