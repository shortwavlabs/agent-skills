# Housekeeping procedures

## Contents
- [Snapshot work in progress without touching the checkout](#snapshot-work-in-progress-without-touching-the-checkout)
- [Private bundle backups and remote verification](#private-bundle-backups-and-remote-verification)
- [Restic backups of bulk data](#restic-backups-of-bulk-data)
- [Whole-tree digest](#whole-tree-digest)
- [Restore verification](#restore-verification)
- [APFS clones and recoverable space](#apfs-clones-and-recoverable-space)
- [Removing a worktree or checkout](#removing-a-worktree-or-checkout)
- [Pre-deletion revalidation](#pre-deletion-revalidation)

## Snapshot work in progress without touching the checkout

Commit the working tree from a temporary index. HEAD, branches, the real index and the files stay as they are:

```bash
tmp=$SCRATCH/index-$repo; cp "$(git rev-parse --git-dir)/index" "$tmp"
GIT_INDEX_FILE=$tmp git add -A -- . ':!*.DS_Store'
tree=$(GIT_INDEX_FILE=$tmp git write-tree)
c=$(git commit-tree "$tree" -p HEAD -m "backup: working-tree snapshot (preservation only)")
git update-ref refs/backup/wip-$(date +%F) "$c"
```

Pin stashes and reflog-only commits the same way (`git update-ref refs/backup/stash-N <sha>`), because reflogs
expire. Afterwards, check that `git status` and the staged-file count are unchanged.

For a private repository you may push these refs as non-branch refs:
```bash
git push origin 'refs/backup/*:refs/backup/*'
```
They create no branch and trigger no CI.

**Never do this for a public repository.** A pushed ref there is published. Use a private backup repository instead.

## Private bundle backups and remote verification

- Create the private repository first, disable Actions, and check `private == true` before every push.
- Build bundles, one per project:
  ```bash
  git bundle create <project>-<date>.bundle --glob='refs/backup/*'
  git bundle verify <project>-<date>.bundle
  ```
  A bundle that "records a complete history" restores without the original remote.
- Before uploading, scan every object that is not already public (`git rev-list --objects --glob='refs/backup/*' --not --remotes`):
  - credentials and tokens;
  - e-mail addresses;
  - large binaries;
  - third-party assets.
- Record a manifest and `SHA256SUMS`: the origin URL, every ref with its commit, date, kind and source branch.
- **Verify from the remote, not the local file:**
  1. Fetch the backup repository into a temporary bare repository.
  2. Extract each bundle, compare its SHA-256 with the manifest, and `git clone --bare` from it.
  3. Run `git fsck --full`.
  4. Compare every ref and commit id with the original.

## Restic backups of bulk data

Restic is the approved mechanism for bulk local-only evidence (simulation outputs, recordings, archives of preserved
builds) on the owner's external disk. Repositories are encrypted, compressed and deduplicated.

```bash
export RESTIC_REPOSITORY=/Volumes/<disk>/restic
export RESTIC_PASSWORD_COMMAND='security find-generic-password -w -s restic-<disk>'   # password lives in the keychain or password manager
restic init                                   # once; repository format v2 compresses by default
restic backup --tag <project> <paths...>      # frozen trees: back up as they are, never compress in place first
restic snapshots --tag <project>
restic check --read-data-subset=10%           # routine; use --read-data after the first backup of a project
restic restore latest --tag <project> --target "$SCRATCH/restore" --include <one representative path>
```

Then compare the restored subset with the original, as in [restore verification](#restore-verification).
- Do not exclude anything an integrity manifest hashes.
- Never store the password in a repository, a script or shell history.

## Whole-tree digest

A bundle or tree matches only if this digest matches. It covers every entry's relative path, type, permission bits,
file SHA-256 and symlink target:

```python
def digest(root):
    h = hashlib.sha256()
    for dp, dns, fs in os.walk(root, followlinks=False):
        dns.sort()
        for name in sorted(dns + fs):
            p = os.path.join(dp, name); rel = os.path.relpath(p, root); st = os.lstat(p)
            mode = stat.S_IMODE(st.st_mode)
            if stat.S_ISLNK(st.st_mode):  h.update(f"L {rel} {mode:o} {os.readlink(p)}\n".encode())
            elif stat.S_ISDIR(st.st_mode): h.update(f"D {rel} {mode:o}\n".encode())
            else: h.update(f"F {rel} {mode:o} {hashlib.sha256(open(p,'rb').read()).hexdigest()}\n".encode())
    return h.hexdigest()
```

A copy installed by a host or an installer often differs in permission bits even when every byte is equal. That is
not a preserved copy of the build output.

## Restore verification

A backup or archive passes only when the restored tree matches the original in **file contents, permission bits and
symlink targets**. An archive checksum proves only that the archive file is intact.

1. **Restore from the remote or external copy**, not the local staging file: download the release asset, read the
   bundle from a fresh fetch, or `restic restore`.
2. **Compare whole-tree digests** (above) of each original folder and its restored copy. They must be equal.
3. **Optionally**, `rsync -nac --delete --itemize-changes <orig>/ <restored>/` locates differences. Ignore only
   group-ownership flags (`g`), which differ naturally in a scratch restore. Check file, symlink and executable
   counts as well.
4. **For standalone archives:**
   ```bash
   tar --no-mac-metadata -cf - <dirs> | zstd -10 -T0 --long=27 -o archive.tar.zst   # create
   zstd -dc --long=27 archive.tar.zst | tar -xf - -C "$SCRATCH/restore"               # restore
   ```

## APFS clones and recoverable space

- **Clones share blocks.** `cp -c`, `clonefile` and some copy APIs clone on APFS. Deleting one clone frees nothing
  until every clone sharing those blocks is deleted.
- **Detect clones** with `getattrlist(2)`, using `ATTR_CMNEXT_CLONEID` and the `FSOPT_ATTR_CMN_EXTENDED` option.
  - A clone inherits its source's clone id.
  - A source, or a file never cloned, has clone id equal to its own inode.
- **Group files by clone id.** A group's blocks are recoverable only if every member is deleted, and they count once.
- **`ATTR_CMNEXT_PRIVATESIZE` is not reliable on its own.** It has been seen to report 0 for old, never-cloned files.
  Calibrate it on a fresh file, a plain copy and a `cp -c` clone before trusting it.
- **Test your copy tool rather than assuming.** Check on the target machine whether `ditto` or a tool's copy step
  clones.
- **Measure reclaimed space as the tree's allocated size before and after** (`du -sk`). Container free space moves
  with every other writer on the volume; it is trustworthy only when nothing else writes during the measurement.

## Removing a worktree or checkout

1. **The branch is safe:** it is clean (`git status --short` empty), and its commits are reachable from a remote
   (`git rev-list --count <branch> --not --remotes` is 0), or backed up under `refs/backup/*` in a private store.
2. **Ignored evidence is moved:** test outputs, logs and renders go into an ignored folder of the primary checkout
   (`mv` on the same volume costs nothing). Record a README of the origins.
3. **No process uses it.** Run [`path_in_use.py`](../scripts/path_in_use.py) from this skill's `scripts/` folder:
   ```bash
   python3 scripts/path_in_use.py "$WORKTREE"     # exit 0 CLEAR, 1 IN USE, 2 UNKNOWN
   ```
   It checks the working directory **and** the open files (including executables and mapped libraries) of every
   process in one `lsof` pass. It never filters by process name, because a name filter misses `make`, `ninja`, `bun`,
   `java`, agents and anything else not on the list. It resolves the path first, because `lsof` reports resolved
   paths (on macOS, `/tmp` is `/private/tmp`). It matches by path prefix, so a sibling `<path>-old` is not matched.
   - **CLEAR:** the path resolved, no process uses it, and visibility was *complete* (every process inspected) or
     *owner-complete* (every process of the path's owner inspected; other users' processes not). Run it as root when
     another user's processes could use the path.
   - **IN USE:** each process and the entry that matched are listed. Stop leftover dev servers only with the owner's
     agreement.
   - **UNKNOWN:** the path did not resolve, or visibility was *partial* (a live process of the owner could not be
     inspected) or *failed* (no `lsof` or `ps`). Unknown is not idle: do not proceed.
4. **Revalidate and remove in one step**, so that nothing can change between the checks and the removal. Repeat the
   checks of steps 1 and 3, and remove only if every one passes:
   ```bash
   test -z "$(git -C "$WORKTREE" status --porcelain)" \
     && [ "$(git -C "$WORKTREE" rev-list --count HEAD --not --remotes --glob='refs/backup/*')" = 0 ] \
     && python3 scripts/path_in_use.py "$WORKTREE" \
     && git worktree remove "$WORKTREE"
   ```
   **Never use `--force`.** Plain `git worktree remove` already removes a worktree that holds only ignored files. It
   refuses one with modified or untracked files, or a lock, and those refusals protect work. If git refuses, stop and
   find out why; never escalate to a forced removal. `path_in_use.py --self-test` checks these git behaviours.

   Then run `git worktree prune`. Confirm the path is gone and stays gone: a still-running watcher can recreate it.

## Pre-deletion revalidation

Run immediately before deleting:
1. The current set of directories equals the manifest's set.
2. No file is newer than the manifest's preparation time.
3. `python3 scripts/path_in_use.py <target>` reports CLEAR for every target: no process has its working directory or
   an open file inside it ([above](#removing-a-worktree-or-checkout)). UNKNOWN drops the entry, exactly like IN USE.
4. Every bundle with a binary has a whole-bundle twin in the preserved set. If one has none, copy it and verify it
   first, or drop the entry.
5. Logs, test reports and captures inside the directories are preserved.
6. Every entry that is not a demonstrably disposable cache has a verified independent backup of whatever it is
   needed for.
7. Record each directory's allocated size. Delete only the literal approved paths. Measure the tree afterwards.
