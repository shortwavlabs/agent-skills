# Workspace policy (revision 3)

This applies to every project under the workspace root and to every person or agent working there. It
restates the owner's global agent instructions and adds what preservation and storage need. Revision 3 adds lessons from a real
workspace cleanup.

**Precedence:** a project's own preservation rules (for example a project's protected-set file, or research freeze
manifests) override this generic policy wherever they are stricter.

## 0. Principles
1. **Never publish unreviewed work.** Work in progress, stashes and reflog-only commits from public repositories go
   to a private backup repository as git bundles. Never push them to the public repository, including as a
   "preservation" push. A public remote receives only commits the owner has approved for publication.
2. **Back up what cannot be regenerated, and verify the backup.**
   - **Needs a backup:** irreplaceable and expensive data must have an independent copy that has been restored and
     compared before anything it protects is deleted.
   - **Does not:** a cache that is demonstrably disposable needs no backup before deletion. That means reproducible
     from committed source and recorded inputs, and not referenced by any document, manifest, verifier or project
     rule.
3. **Full bundle preservation checks.** A plug-in or app bundle is preserved only when its whole tree matches:
   every path, file content, permission bit and symlink target, not just the main binary's hash.
4. **Project-specific retention rules come first** (protected sets, freeze manifests, "never delete" records).
5. **Manifest-driven destructive operations.** Nothing is deleted, moved or rewritten except through a written,
   owner-approved manifest. It is revalidated against the filesystem immediately before execution, and any entry
   that fails a precondition is dropped and reported.
6. **No unauthorised worktrees or duplicate checkouts.** One checkout per project. Agents must not create worktrees
   (including tool-managed ones such as `.claude/worktrees/`), clones or copies of a checkout without the owner's
   explicit authorisation. A temporary bare restore in a scratch folder, used only to verify a backup, is not a
   working copy.
7. **Do not interrupt or needlessly block development.**
   - Never switch branches, reset, clean or rebuild in a checkout someone else is using.
   - Keep working environments (virtual environments, root `node_modules`) and each project's primary builds.
   - Run destructive steps only when the project is idle. Snapshot others' work from a temporary index.
   - Housekeeping never holds a checkout or a PR hostage.
8. **Archival integrity is not scientific reproducibility.** An archive proves that exact bytes are kept. It does
   not prove that a result can be regenerated: that needs committed source, recorded inputs and the same toolchain.
   Keep both claims separate in records, and never present one as the other.
9. **Retrospective commits are not historical provenance.** Committing code after the fact preserves it, but does
   not show that it is the code that produced earlier results. Label such commits as preservation. Qualification
   claims rest only on provenance recorded at the time (locks, source hashes, run records).
10. **Measure reclaimed space per tree.** Whole-disk free space is not attributable while other processes write to
    the same volume, and APFS clones share blocks. Record the tree's allocated size before and after deletion.

## 1. Checkouts
1. One primary checkout per project: `<workspace>/<project>`.
2. No additional clones, worktrees or duplicate checkouts without the owner's explicit authorisation. This covers
   agent-generated ones. An authorised one is named in the task that needs it and removed once its work is pushed.
3. Dependent phases use feature branches and stacked PRs, each based on its predecessor.
4. Preserve uncommitted work before switching branches: commit it, or stash it with a descriptive message.
5. Before removing a worktree or checkout:
   - check the **complete** process list (never a truncated one) for dev servers, watchers or builds whose working
     directory is inside it;
   - move any ignored evidence (test outputs, logs, renders) into the primary checkout.

## 2. Builds
1. **At most three persistent build directories per project by default**, e.g. `build/` (Release), `build-debug/`
   and one sanitizer or experiment directory. Each is reused across branches.
2. **Exceptions, each recorded in the project's docs with a reason and an end condition:**
   - build trees that active research reads;
   - protected qualification builds;
   - build trees an integrity manifest or preservation verifier fingerprints;
   - builds cited by name in committed documents.
3. A one-off `build-<experiment>` directory is removed once its results are written up and its cited binaries have
   been copied to `auditions/` (see 3).
4. Shared pinned dependencies (one checkout per JUCE commit, eurorack, Rack SDK) are referenced by path, never
   patched in place. No project may build against another project's build directory.

## 3. Preserved binaries (auditions, approved releases, cited diagnostic builds)
1. Never audition, approve or cite a binary straight from a build directory. Copy it into
   `<project>/auditions/<name>/`, which is excluded from git through `.git/info/exclude`.
2. **Every preserved binary gets a manifest entry:**
   - full SHA-256 of the executable and a whole-bundle digest;
   - build time and codesign status;
   - source commit, marked **verified** (recorded at the time, or named by a committed doc) or **inferred**;
   - build configuration and external inputs (e.g. asset manifests and their hashes);
   - the documents that cite it.
3. A binary whose hash a committed doc cites is evidence: rebuilding never reproduces it (JUCE timestamps,
   unversioned assets). Keep the bundle.
4. External build inputs (3D assets, IRs, models) that a committed manifest names by hash must exist in a
   versioned, content-addressed store (see 5.6).

## 4. Research evidence
1. **Committed source provenance is mandatory for any qualification run.**
   - The producing code (including tools, gates and locks) is committed **before** a result is cited.
   - Each run records its commit, command line, input hashes, machine and CPU time.
   - Results produced from code that was uncommitted at the time stay "unknown" provenance even after that code is
     committed later (principle 9).
2. **Classes**, each kept in a different location:
   - **evidence:** committed, or stored with a manifest;
   - **expensive reproducible runs:** `runs/`;
   - **disposable caches:** `cache/`, never cited by a document.
3. **Frozen evidence** (locked gates, sealed held-out cases, freeze and integrity manifests, and the files they
   hash) is never deleted, moved, compressed in place or modified without a **versioned amendment**: a committed
   record that names the change, the reason and the owner's approval, and that updates the manifests.
4. **Caches referenced by an integrity or freeze manifest are never deleted automatically**, even when they are
   duplicates or cheap to regenerate.
5. Failed experiments are not disposable by default: a failure cited by a decision is evidence.
6. Sealed held-out data is preserved without being opened.

## 5. Backups and archives
1. **Irreplaceable local-only evidence must have an independent backup.** A second copy on the same SSD,
   including an APFS clone, does not count.
   - Small material goes to the project's private GitHub repository:
     - committed;
     - or as a backup commit under `refs/backup/*`, which creates no branch and triggers no CI.
   - Unpublished work from public repositories goes to the private backup repository as git bundles.
   - Bulk data goes to a **Restic** repository on the owner's independent storage (approved: an external SSD).
     Restic stores it encrypted, compressed and deduplicated. Keep the repository password in the owner's password
     manager, never in a repository or in plain text.
2. Public repositories never receive backups of unreviewed work (principle 1).
3. **Verification:**
   - **Restic:** `restic check --read-data` (or `--read-data-subset` for routine runs), plus a restore of a
     representative subset to a scratch folder.
   - **Archives:** a full restore test before any original is removed.
   - Either way, compare the restored files with the originals by **full file contents, permission bits and symlink
     targets**. Checksums of the archive alone are not enough.
4. Lossless only: Restic's built-in compression, or zstd / xz for standalone archives. Check free space first, and
   never take the disk below 20 % free.
5. Converting text numerics to binary, or float64 to float32, is allowed only where every value round-trips exactly.
6. Unversioned build inputs (e.g. Blender exports named by asset manifests) are copied into a content-addressed
   store, `assets/<sha256>/<name>`, before any build that uses them is cited.

## 6. Deletion
1. Every deletion goes through a written manifest: path, logical and allocated size, class, reason, references
   checked, regeneration command. The owner approves it before anything is removed.
2. A deletion manifest never contains:
   - uncommitted work, unpushed commits, stashes or reflog-only commits (pin these to `refs/backup/*` first);
   - frozen evidence without its amendment.
3. Disposable caches (principle 2) need no backup. Anything else needs a verified independent backup, or a
   whole-bundle twin in the preserved set, first.
4. **Recoverable space is measured, not assumed.** APFS clones share blocks, so deleting one clone frees nothing.
   Count a clone group once, and only if every member is deleted.
5. Delete only the literal approved paths, using the project's own cleanup tool where one exists. Verify afterwards
   against the project's preservation checks.

## 7. Reporting
1. Monthly, and at the end of every phase: a per-project table of disk use, covering:
   - source and `.git`;
   - build directories;
   - research by class;
   - caches;
   - auditions.

   Plus the worktrees, unpushed branches, stashes, reflog-only commits and local-only evidence without an
   independent backup.
2. Use consistent units (GiB) and say whether figures are logical, allocated or recoverable.
3. This reporting is part of the definition of done for a phase.
