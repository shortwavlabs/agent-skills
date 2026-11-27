# Housekeeping procedures

## Contents
- [Snapshot work in progress without touching the checkout](#snapshot-work-in-progress-without-touching-the-checkout)
- [Private bundle backups and remote verification](#private-bundle-backups-and-remote-verification)
- [Whole-bundle digest](#whole-bundle-digest)
- [Archive verification](#archive-verification)
- [APFS clones and recoverable space](#apfs-clones-and-recoverable-space)
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

## Whole-bundle digest

A bundle matches only if this digest matches. It covers every entry's relative path, type, permission bits, file
SHA-256 and symlink target:

```python
def digest(bundle):
    h = hashlib.sha256()
    for dp, dns, fs in os.walk(bundle, followlinks=False):
        dns.sort()
        for name in sorted(dns + fs):
            p = os.path.join(dp, name); rel = os.path.relpath(p, bundle); st = os.lstat(p)
            mode = stat.S_IMODE(st.st_mode)
            if stat.S_ISLNK(st.st_mode):  h.update(f"L {rel} {mode:o} {os.readlink(p)}\n".encode())
            elif stat.S_ISDIR(st.st_mode): h.update(f"D {rel} {mode:o}\n".encode())
            else: h.update(f"F {rel} {mode:o} {hashlib.sha256(open(p,'rb').read()).hexdigest()}\n".encode())
    return h.hexdigest()
```

A copy installed by a host or an installer often differs in permission bits even when every byte is equal. That is
not a preserved copy of the build output.

## Archive verification

- Create the archive:
  ```bash
  tar --no-mac-metadata -cf - <dirs> | zstd -10 -T0 --long=27 -o archive.tar.zst
  ```
- Extract it elsewhere and compare:
  ```bash
  rsync -nac --delete --itemize-changes <orig>/ <extracted>/
  ```
  - Count only content, size, time and permission flags (`c s t p`) and deletions.
  - Group ownership (`g`) differs naturally in a scratch extraction.
  - Also compare file, symlink and executable counts.
- Repeat the comparison on a copy downloaded back from the remote store.

## APFS clones and recoverable space

- **Clones share blocks.** `cp -c`, `clonefile` and many copy APIs clone on APFS. Deleting one clone frees nothing
  until every clone sharing those blocks is deleted.
- **Detect clones** with `getattrlist(2)`, using `ATTR_CMNEXT_CLONEID` and the `FSOPT_ATTR_CMN_EXTENDED` option.
  - A clone inherits its source's clone id.
  - A source, or a file never cloned, has clone id equal to its own inode.
- **Group files by clone id.** A group's blocks are recoverable only if every member is deleted, and they count once.
- **`ATTR_CMNEXT_PRIVATESIZE` is not reliable on its own.** It has been seen to report 0 for old files that were
  never cloned. Calibrate it on known files (a fresh file, a plain copy, a `cp -c` clone) before trusting it.
- **Measure reclaimed space as the tree's allocated size before and after.** Whole-container free space moves with
  every other writer on the volume.

## Pre-deletion revalidation

Run immediately before deleting:
1. The current set of directories equals the manifest's set.
2. No file is newer than the manifest's preparation time.
3. No open files (`lsof -Fn | grep <root>`) and no build or render processes.
4. Every bundle with a binary has a whole-bundle twin in the preserved set. If one has none, copy it first and
   verify it, or drop the entry.
5. Logs, test reports and captures inside the directories are preserved.
6. The independent backup of the preserved set was verified from the remote copy.
7. Record each directory's allocated size. Delete only the literal approved paths. Measure the tree afterwards.
