#!/usr/bin/env python3
"""Is any process using a path? Run it immediately before removing a worktree or checkout, or deleting a directory.

    python3 path_in_use.py <path>      exit 0 CLEAR, 1 IN USE, 2 UNKNOWN
    python3 path_in_use.py --self-test

One `lsof` pass covers every process. It checks working directories and open files, including executables and
mapped libraries, and never filters by process name. A process uses the path when one of its entries is the path
or lies under it. A sibling `<path>-old` does not match.

Visibility is reported explicitly:
  complete        every running process was inspected (normally only when run as root);
  owner-complete  every process of the path's owner was inspected; other users' processes were not;
  partial         at least one live process of the path's owner could not be inspected;
  failed          no listing was obtained (lsof or ps missing or failing).
CLEAR needs complete or owner-complete visibility and no match. A path that cannot be resolved, or a partial or
failed listing, is UNKNOWN, never CLEAR.

`--self-test` also checks the git behaviour the housekeeping procedure relies on. Plain `git worktree remove` removes
a worktree that holds only ignored files, and refuses one with modified or untracked files or a lock. Those checks
create worktrees only in a temporary fixture repository.

Standard library, plus `lsof` and `ps` (macOS, Linux) and `git` for the self-test.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time

CLEAR, IN_USE, UNKNOWN = 0, 1, 2
VERDICT = {CLEAR: "CLEAR", IN_USE: "IN USE", UNKNOWN: "UNKNOWN"}


def resolve(target: str) -> tuple[str | None, str | None]:
    """The fully resolved path (lsof reports resolved paths), or (None, reason)."""
    try:
        real = os.path.realpath(target, strict=True)
    except (OSError, ValueError) as e:
        return None, f"cannot resolve {target!r}: {e}"
    if real == os.sep:
        return None, "refusing to check the filesystem root"
    return real, None


def list_processes() -> dict[int, int]:
    """{pid: uid} for every running process. Zombies are left out: they hold no files and have no working directory."""
    run = subprocess.run(["ps", "-A", "-o", "pid=", "-o", "uid=", "-o", "stat="], capture_output=True, text=True,
                         timeout=60)
    procs, seen = {}, 0
    for line in run.stdout.split("\n"):
        f = line.split()
        if len(f) >= 3 and f[0].isdigit() and f[1].isdigit():
            seen += 1
            if not f[2].startswith("Z"):
                procs[int(f[0])] = int(f[1])
    if run.returncode != 0 or not seen:
        raise RuntimeError(f"ps failed (exit {run.returncode})")
    return procs


def list_open_files(lsof: str = "lsof") -> tuple[dict[int, dict], int]:
    """({pid: {"cmd": name, "files": [(fd, name), ...]}}, lsof's own pid) for every process lsof can read."""
    proc = subprocess.Popen([lsof, "-w", "-n", "-P", "-F", "pcfn"], stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True)
    out, _ = proc.communicate(timeout=300)
    records: dict[int, dict] = {}
    rec, fd = None, None
    for line in out.split("\n"):
        tag, val = line[:1], line[1:]
        if tag == "p" and val.isdigit():
            rec, fd = records.setdefault(int(val), {"cmd": "?", "files": []}), None
        elif rec is None:
            continue
        elif tag == "c":
            rec["cmd"] = val
        elif tag == "f":
            fd = val
        elif tag == "n":
            rec["files"].append((fd, val))
    if not records:
        raise RuntimeError(f"lsof listed nothing (exit {proc.returncode})")
    return records, proc.pid


def inspected(rec: dict | None) -> bool:
    """lsof could read this process: it reported a readable working directory."""
    return bool(rec) and any(fd == "cwd" and name.startswith("/") and "Permission denied" not in name
                             and "(readlink" not in name for fd, name in rec["files"])


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def classify(target: str, owner: int, procs: dict[int, int], records: dict[int, dict], skip: set[int],
             is_alive=alive) -> tuple[int, str, list[tuple[int, str, str, str]]]:
    """(verdict, visibility description, matches [(pid, command, fd, name)]). Pure, apart from is_alive."""
    matches = []
    for pid, rec in sorted(records.items()):
        if pid in skip:
            continue
        for fd, name in rec["files"]:
            if name == target or name.startswith(target + "/"):
                matches.append((pid, rec["cmd"], fd, name))
    hidden_owner, hidden_other = [], 0
    for pid, uid in procs.items():
        if pid in skip or inspected(records.get(pid)) or not is_alive(pid):   # exited between ps and lsof
            continue
        if uid == owner:
            hidden_owner.append(pid)
        else:
            hidden_other += 1
    if hidden_owner:
        visibility = f"partial ({len(hidden_owner)} live processes of uid {owner} not inspected: {hidden_owner[:10]})"
    elif hidden_other:
        visibility = (f"owner-complete (every process of uid {owner} inspected; {hidden_other} processes of other "
                      "users not inspected; run as root for complete visibility)")
    else:
        visibility = "complete (every process inspected)"
    if matches:
        return IN_USE, visibility, matches
    return (UNKNOWN if hidden_owner else CLEAR), visibility, matches


def check(target: str, lsof: str = "lsof") -> tuple[int, list[str], list[tuple[int, str, str, str]]]:
    """(verdict, report lines, matches) for a path."""
    real, why = resolve(target)
    if real is None:
        return UNKNOWN, [f"target: {why}", "verdict: UNKNOWN"], []
    lines = [f"target: {real}"]
    try:
        owner = os.stat(real).st_uid
        procs = list_processes()                 # before lsof: a process that exits in between is filtered as dead
        records, lsof_pid = list_open_files(lsof)
    except (OSError, RuntimeError, subprocess.SubprocessError) as e:
        return UNKNOWN, lines + [f"visibility: failed ({e})", "verdict: UNKNOWN"], []
    verdict, visibility, matches = classify(real, owner, procs, records, {os.getpid(), lsof_pid})
    lines.append(f"visibility: {visibility}")
    lines += [f"in use: pid {pid} ({cmd}) {fd} {name}" for pid, cmd, fd, name in matches]
    lines.append(f"verdict: {VERDICT[verdict]}")
    return verdict, lines, matches


# ---------------------------------------------------------------------------------------------------------- self-test

def _wait_for(target: str, pid: int, timeout: float = 10.0) -> list[tuple[int, str, str, str]]:
    """Matches for pid once lsof sees it (a just-started child needs a moment)."""
    deadline = time.monotonic() + timeout
    while True:
        _, _, matches = check(target)
        mine = [m for m in matches if m[0] == pid]
        if mine or time.monotonic() > deadline:
            return mine
        time.sleep(0.2)


def _git(args: list[str], cwd: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@example.invalid",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=env, timeout=60)


def _git_worktree_tests(root: str, fail) -> None:
    repo = os.path.join(root, "repo")
    os.makedirs(repo)
    for args in (["init", "-q"], ["config", "commit.gpgsign", "false"]):
        _git(args, repo)
    with open(os.path.join(repo, ".gitignore"), "w") as fh:
        fh.write("build/\n")
    with open(os.path.join(repo, "tracked.txt"), "w") as fh:
        fh.write("original\n")
    _git(["add", "."], repo)
    if _git(["commit", "-q", "-m", "init"], repo).returncode != 0:
        fail("git fixture: initial commit failed")
        return

    def add(name: str) -> str:
        wt = os.path.join(root, name)
        if _git(["worktree", "add", "-q", wt, "-b", name], repo).returncode != 0:
            fail(f"git fixture: worktree add {name} failed")
        return wt

    # Ignored files alone: plain removal succeeds, so --force is never needed for them.
    wt = add("ignored-only")
    os.makedirs(os.path.join(wt, "build"))
    with open(os.path.join(wt, "build", "out.o"), "w") as fh:
        fh.write("object\n")
    r = _git(["worktree", "remove", wt], repo)
    if r.returncode != 0 or os.path.exists(wt):
        fail(f"git: a worktree holding only ignored files was not removed without --force: {r.stderr.strip()}")

    # Modified tracked file, untracked file, lock: plain removal refuses and the work survives.
    cases = {"modified": ("tracked.txt", "changed\n"), "untracked": ("new.txt", "new\n"), "locked": None}
    for name, change in cases.items():
        wt = add(name)
        if change:
            with open(os.path.join(wt, change[0]), "w") as fh:
                fh.write(change[1])
        else:
            _git(["worktree", "lock", wt], repo)
        r = _git(["worktree", "remove", wt], repo)
        if r.returncode == 0 or not os.path.isdir(wt):
            fail(f"git: plain removal of a {name} worktree was not refused")
            continue
        if change:
            with open(os.path.join(wt, change[0])) as fh:
                if fh.read() != change[1]:
                    fail(f"git: the {name} change did not survive the refused removal")


def self_test() -> list[str]:
    """Explicit checks, not assert, so it also runs under python -O."""
    failures: list[str] = []
    fail = failures.append

    # Classification, with synthetic data: deterministic on any machine.
    t = "/w/t"
    rec = lambda *files: {"cmd": "x", "files": [("cwd", "/elsewhere"), *files]}
    procs = {10: 501, 11: 501, 20: 0}
    records = {10: rec(), 11: rec(("3r", "/w/t/sub/file"))}
    v, vis, m = classify(t, 501, procs, records, set(), lambda p: True)
    if v != IN_USE or [x[0] for x in m] != [11] or not vis.startswith("owner-complete"):
        fail(f"classify: open file under the target, other user hidden -> {VERDICT[v]}, {vis}, {m}")
    v, vis, _ = classify(t, 501, procs, {10: rec(), 11: rec(("cwd", "/w/t-old"))}, set(), lambda p: True)
    if v != CLEAR or not vis.startswith("owner-complete"):
        fail(f"classify: sibling '<target>-old' must not match -> {VERDICT[v]}, {vis}")
    v, vis, _ = classify(t, 501, procs, {10: rec()}, set(), lambda p: True)
    if v != UNKNOWN or not vis.startswith("partial"):
        fail(f"classify: a live owner process lsof could not read -> {VERDICT[v]}, {vis}")
    v, vis, _ = classify(t, 501, procs, {10: rec()}, set(), lambda p: p != 11)
    if v != CLEAR:
        fail(f"classify: an owner process that exited before lsof ran must not count -> {VERDICT[v]}, {vis}")
    v, vis, _ = classify(t, 501, {10: 501}, {10: rec()}, set(), lambda p: True)
    if v != CLEAR or not vis.startswith("complete"):
        fail(f"classify: everything inspected -> {VERDICT[v]}, {vis}")
    denied = {10: {"cmd": "x", "files": [("cwd", "/proc/10/cwd (readlink: Permission denied)")]}}
    v, vis, _ = classify(t, 501, {10: 501}, denied, set(), lambda p: True)
    if v != UNKNOWN:
        fail(f"classify: a permission-denied working directory is not inspected -> {VERDICT[v]}, {vis}")

    root = os.path.realpath(tempfile.mkdtemp(prefix="path-in-use-"))
    children: list[subprocess.Popen] = []
    try:
        # Resolution and failed listing.
        if check(os.path.join(root, "missing"))[0] != UNKNOWN:
            fail("check: an unresolvable target must be UNKNOWN")
        target = os.path.join(root, "wt")
        os.makedirs(os.path.join(target, "sub"))
        os.makedirs(os.path.join(root, "wt-old"))
        held = os.path.join(target, "held.log")
        open(held, "w").close()
        v, lines, _ = check(target, lsof="lsof-not-installed")
        if v != UNKNOWN or not any(line.startswith("visibility: failed") for line in lines):
            fail(f"check: a failed listing must be UNKNOWN with visibility 'failed': {lines}")

        if shutil.which("lsof") is None or shutil.which("ps") is None:
            fail("lsof and ps are required for the live checks of this self-test")
        else:
            # Live processes. None of these names is node, vite, cargo, python or cmake, the old procedure's filter.
            def spawn(args: list[str], cwd: str) -> subprocess.Popen:
                children.append(subprocess.Popen(args, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
                return children[-1]

            inside = spawn(["sleep", "60"], os.path.join(target, "sub"))
            if not any(fd == "cwd" for _, _, fd, _ in _wait_for(target, inside.pid)):
                fail("check: a process whose working directory is under the target was not found")
            holder = spawn(["tail", "-f", held], root)
            if not any(fd != "cwd" and name == held for _, _, fd, name in _wait_for(target, holder.pid)):
                fail("check: a process holding a file open under the target (working directory elsewhere) "
                     "was not found")
            sibling = spawn(["sleep", "60"], os.path.join(root, "wt-old"))
            _wait_for(os.path.join(root, "wt-old"), sibling.pid)
            if _wait_for(target, sibling.pid, timeout=0):
                fail("check: a process in the sibling '<target>-old' matched the target")
            link = os.path.join(root, "link")
            os.symlink(target, link)
            if not _wait_for(link, inside.pid):
                fail("check: a target given through a symlink was not resolved")
            for c in children:
                c.kill()
                c.wait()
            v, lines, _ = check(target)
            if v == IN_USE:
                fail(f"check: target still reported in use after its processes exited: {lines}")
            elif v == UNKNOWN and not any("partial" in line for line in lines):
                fail(f"check: unexpected UNKNOWN on an idle target: {lines}")

        if shutil.which("git") is None:
            fail("git is required for the worktree checks of this self-test")
        else:
            _git_worktree_tests(os.path.join(root, "git"), fail)
    finally:
        for c in children:
            if c.poll() is None:
                c.kill()
                c.wait()
        shutil.rmtree(root, ignore_errors=True)
    return failures


def main() -> int:
    if sys.argv[1:] == ["--self-test"]:
        failures = self_test()
        for f in failures:
            print("FAIL:", f)
        print("path_in_use self-test: " + ("PASS" if not failures else f"{len(failures)} FAILED"))
        return 1 if failures else 0
    if len(sys.argv) != 2 or sys.argv[1].startswith("-"):
        print(__doc__.strip().split("\n\n")[1], file=sys.stderr)
        return UNKNOWN
    verdict, lines, _ = check(sys.argv[1])
    print("\n".join(lines))
    return verdict


if __name__ == "__main__":
    sys.exit(main())
