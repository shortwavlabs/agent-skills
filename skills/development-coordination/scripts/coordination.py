#!/usr/bin/env python3
"""Coordinate cooperating coding agents in one shared git checkout: claims, ownership transfer and activity checks.

    coordination.py acquire  --scope SCOPE --intent TEXT [--mode exclusive|shared] [--ttl MIN] [--session T] [--agent NAME]
    coordination.py renew    --id ID --session T [--ttl MIN]           (the current holder only)
    coordination.py release  --id ID --session T                       (the current holder, or once it has died)
    coordination.py transfer --id ID --session T [--ttl MIN]           (offer: prints a one-time transfer token)
    coordination.py accept   --id ID --transfer-token X [--agent NAME] (the successor takes over, atomically)
    coordination.py adopt    --id ID --session T [--agent NAME]        (recovery once the holder has provably died)
    coordination.py status
    coordination.py check    [--scope S] [--session T] [--disruptive | --destructive] [--accept-passive ID]... [--all]
    coordination.py archive-stale
    coordination.py --self-test
Every command takes [--repo DIR]; all but status and archive-stale take [--holder-pid PID].

SCOPE is `checkout`, `branch=NAME`, `paths=GLOB[,GLOB...]` or `resource=ID[@PATH]`, relative to the checkout root.
Exit status: 0 granted, idle or done; 1 conflict or busy; 2 unknown, refused, unavailable or error.

What this enforces, and what it does not:
- Every registry change runs inside one critical section: an exclusive advisory `fcntl.flock` on
  `.agent-state/claims.lock`, non-blocking with a bounded retry, held only for check-and-publish. The lock file is never
  deleted or replaced. Cooperating agents never both hold overlapping claims, and a transfer leaves no window.
- Ownership is a verified process identity (host, boot, PID, process start time) plus the session token. A token alone
  never proves ownership and never turns an unknown holder into a verified one. Tokens prevent accidents between
  cooperating agents; they are not authentication against a hostile process of the same user.
- A claim is stale only when it has expired, its holder is established to be dead and no transfer is pending.
- Anything that cannot be inspected or relied on (a malformed record, an unexpected registry file, a symlinked or
  git-tracked registry, a lock timeout, no `fcntl`, a network or unidentified filesystem, a container, partial process
  visibility) yields unknown: never a grant, never "idle".
- The activity check reuses `path_in_use.py` (a generated copy of `workspace-housekeeping`'s): working directories and
  open files of every readable process. It excludes only this session's own processes: its holder (found through
  ancestry and validated as a session boundary) and the holder's descendants. It never excludes a process by name.
  Passive processes (working directory only, no children) are reported separately; an owner-approved acceptance pinned
  to one process identity can let a reversible operation proceed, never a destructive one.
- The check is read-only: it creates no registry, runs git without optional locks and writes no bytecode.
Standard library only; tested on macOS and Linux. On Windows, claims are unavailable and the result is unknown.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import re
import secrets
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import unicodedata
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

sys.dont_write_bytecode = True                       # never write bytecode next to an installed skill
try:
    import fcntl
except ImportError:                                   # Windows: claims are unavailable, never faked
    fcntl = None

STATE = ".agent-state"
CLAIM_ID = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{8}$")
TMP_PREFIX = ".tmp-"
METADATA_FILES = {".DS_Store"}                        # harmless filesystem metadata: reported, never deleted
MAX_CLAIM_BYTES = 65536
DISPLAY_LIMIT = 10
GLOB_CHARS = set("*?[")
NO_TTY = {"", "?", "??", "-"}
WRAPPER = re.compile(r"^(?:\S*/)?(?:(?:sh|bash|zsh|dash|ksh|fish)\s+-[A-Za-z]*c\b|env(?:\s|$))")
NETWORK_FS = {"nfs", "nfs4", "cifs", "smbfs", "smb3", "afpfs", "webdav", "fuse.sshfs", "sshfs", "9p", "ncpfs",
              "glusterfs", "ceph", "lustre", "fuse.rclone", "davfs"}
GIT_IN_PROGRESS = {"index.lock": "a git command holds the index lock", "MERGE_HEAD": "a merge is in progress",
                   "CHERRY_PICK_HEAD": "a cherry-pick is in progress", "REVERT_HEAD": "a revert is in progress",
                   "BISECT_LOG": "a bisect is in progress", "rebase-merge": "a rebase is in progress",
                   "rebase-apply": "a rebase or am is in progress"}
VISIBILITY_RANK = ("complete", "owner-complete", "not checked", "partial", "failed")
HERE = Path(__file__).resolve().parent


class Unknown(Exception):
    """Something needed for a safe answer cannot be established. Never treated as success."""


class Usage(Exception):
    """An invalid request."""


# ------------------------------------------------------------------------------------------------------ basics

def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def stamp(t: datetime.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_stamp(value) -> datetime.datetime | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        return None
    try:
        return datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return None


def strict_json(text: str):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError(f"duplicate key {key!r}")
            out[key] = value
        return out
    return json.loads(text, object_pairs_hook=pairs)


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    """git without optional locks, so read-only commands never rewrite the index."""
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=60,
                          env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})


def checkout_root(repo) -> Path:
    try:
        r = git(Path(repo), "rev-parse", "--show-toplevel")
    except (OSError, subprocess.SubprocessError) as e:
        raise Unknown(f"git is not available: {e}")
    if r.returncode != 0 or not r.stdout.strip():
        raise Usage(f"{repo} is not inside a git checkout")
    return Path(r.stdout.strip()).resolve()


# ------------------------------------------------------------------------------------- processes and identity

def process_table() -> dict[int, tuple[int, str, str]]:
    """{pid: (ppid, controlling terminal, command)} for every process."""
    try:
        r = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,tty=,command="], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        raise Unknown(f"the process table cannot be read: {e}")
    table = {}
    for line in r.stdout.splitlines():
        parts = line.strip().split(None, 3)
        if len(parts) >= 3 and parts[0].isdigit() and parts[1].isdigit():
            table[int(parts[0])] = (int(parts[1]), parts[2], parts[3] if len(parts) > 3 else "")
    if r.returncode != 0 or not table:
        raise Unknown("the process table cannot be read")
    return table


def ancestry(pid: int, table: dict) -> list[int]:
    chain, seen = [], set()
    while pid in table and pid > 1 and pid not in seen:
        chain.append(pid)
        seen.add(pid)
        pid = table[pid][0]
    return chain


def descendants(pid: int, table: dict) -> set[int]:
    children: dict[int, list[int]] = {}
    for child, row in table.items():
        children.setdefault(row[0], []).append(child)
    out, todo = set(), [pid]
    while todo:
        for child in children.get(todo.pop(), []):
            if child not in out:
                out.add(child)
                todo.append(child)
    return out


def broad_reason(pid: int, table: dict, claims=(), chain=()) -> str | None:
    """Why pid cannot stand for one session (and so must not own its descendants), or None.

    Name-free tests: a session boundary hosts no controlling terminal other than its own (terminal multiplexers, IDEs
    and terminal applications do), and contains no other registered claim holder (sibling agents that coordinate)."""
    own_tty = table[pid][1]
    below = descendants(pid, table)
    for d in sorted(below):
        tty = table[d][1]
        if tty not in NO_TTY and tty != own_tty:
            return f"it hosts another terminal ({tty}, process {d})"
    for claim in claims:
        other = claim["holder"]["pid"]
        if other and other in below and other not in chain:
            return f"it contains another session's claim holder (process {other})"
    return None


def resolve_holder(explicit: int | None, table: dict, claims=(), start: int | None = None) -> int | None:
    """The long-lived process that stands for this session: the nearest ancestor that is not a `sh -c`-style wrapper,
    provided it is a session boundary; otherwise None (the conservative fallback). An explicit PID must be this
    process or an ancestor, and must itself be a session boundary."""
    chain = ancestry(os.getpid() if start is None else start, table)
    if explicit is not None:
        if explicit not in chain:
            raise Usage(f"--holder-pid {explicit} is not this process or one of its ancestors")
        why = broad_reason(explicit, table, claims, chain)
        if why:
            raise Usage(f"--holder-pid {explicit} is not a session boundary: {why}")
        return explicit
    for pid in chain[1:]:
        if not WRAPPER.match(table[pid][2]):
            return None if broad_reason(pid, table, claims, chain) else pid
    return None


def process_start(pid: int) -> str | None:
    proc = Path(f"/proc/{pid}/stat")
    if proc.exists():
        try:
            data = proc.read_text()
            return "proc:" + data[data.rindex(")") + 2:].split()[19]
        except (OSError, ValueError, IndexError):
            return None
    try:
        r = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, timeout=10,
                           env={**os.environ, "LC_ALL": "C", "TZ": "UTC"})
    except (OSError, subprocess.SubprocessError):
        return None
    out = " ".join(r.stdout.split())
    return f"lstart:{out}" if r.returncode == 0 and out else None


def identity_token(pid: int, start: str) -> str:
    """A short, revalidatable name for one process: its PID and a digest of its start time."""
    return f"{pid}:{hashlib.sha256(start.encode()).hexdigest()[:16]}"


def boot_id() -> str | None:
    proc = Path("/proc/sys/kernel/random/boot_id")
    if proc.exists():
        try:
            return "linux:" + proc.read_text().strip()
        except OSError:
            return None
    try:
        r = subprocess.run(["sysctl", "-n", "kern.boottime"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"sec = (\d+)", r.stdout)
    return f"bsd:{m.group(1)}" if m else None


def here() -> dict:
    return {"host": socket.gethostname(), "boot": boot_id()}


def caller_identity(holder_pid: int | None, claims=(), table: dict | None = None) -> dict:
    """This session's identity. pid and start are both None when the holder cannot be established."""
    table = table if table is not None else process_table()
    pid = resolve_holder(holder_pid, table, claims)
    start = process_start(pid) if pid else None
    local = here()
    return {"host": local["host"], "boot": local["boot"], "pid": pid if start else None, "start": start if pid else None}


def same_holder(holder: dict, who: dict) -> bool:
    """A recorded holder matches a caller only when every established identity element matches."""
    return (holder["pid"] is not None and who["pid"] is not None and holder["pid"] == who["pid"]
            and holder["process_start"] == who["start"] and holder["host"] == who["host"]
            and (not holder.get("boot") or not who["boot"] or holder["boot"] == who["boot"]))


def holder_state(holder: dict, local: dict) -> tuple[str, str]:
    if holder["host"] != local["host"]:
        return "unknown", "held on another host"
    if holder.get("boot") and local["boot"] and holder["boot"] != local["boot"]:
        return "dead", "the host has rebooted since the claim was made"
    if holder["pid"] is None or holder["process_start"] is None:
        return "unknown", "the holder's process identity was not recorded"
    try:
        os.kill(holder["pid"], 0)
    except ProcessLookupError:
        return "dead", f"process {holder['pid']} no longer exists"
    except PermissionError:
        pass
    except OSError as e:
        return "unknown", f"process {holder['pid']} cannot be inspected: {e}"
    start = process_start(holder["pid"])
    if start is None:
        return "unknown", f"the start time of process {holder['pid']} cannot be read"
    if start != holder["process_start"]:
        return "dead", f"PID {holder['pid']} now belongs to another process (reused)"
    return "live", f"process {holder['pid']} is running"


def filesystem_type(path: Path) -> str | None:
    """Best effort: the filesystem type holding path, or None if it cannot be determined."""
    best, kind = "", None
    try:
        if Path("/proc/mounts").exists():
            rows = [line.split()[1:3] for line in Path("/proc/mounts").read_text().splitlines() if len(line.split()) > 2]
            rows = [(m.replace("\\040", " "), t) for m, t in rows]
        else:
            out = subprocess.run(["mount"], capture_output=True, text=True, timeout=10).stdout
            rows = [(m.group(1), m.group(2)) for m in re.finditer(r" on (.+?) \(([^,)]+)", out)]
    except (OSError, subprocess.SubprocessError):
        return None
    target = str(path)
    for mount, fstype in rows:
        if (target == mount or target.startswith(mount.rstrip("/") + "/")) and len(mount) > len(best):
            best, kind = mount, fstype
    return kind


def in_container() -> bool:
    if Path("/.dockerenv").exists() or Path("/run/.containerenv").exists():
        return True
    try:
        return bool(re.search(r"docker|kubepods|containerd|libpod", Path("/proc/1/cgroup").read_text()))
    except OSError:
        return False


def coordination_problem(root: Path) -> str | None:
    """Why reliable coordination is unavailable for this checkout, or None. Shared by every command, read-only or not."""
    if fcntl is None:
        return "advisory locking (fcntl) is unavailable on this platform"
    kind = filesystem_type(root)
    if kind is None:
        return "the checkout's filesystem type could not be identified"
    if kind in NETWORK_FS:
        return f"the checkout is on a network filesystem ({kind}): advisory claims are unreliable there"
    if in_container():
        return "this runs inside a container: holders in other PID namespaces cannot be verified"
    return None


# ------------------------------------------------------------------------------------------------- scopes

def safe_relpath(text: str) -> bool:
    return (bool(text) and "\\" not in text and not text.startswith("/") and ".." not in PurePosixPath(text).parts
            and text == PurePosixPath(text).as_posix())


def parse_scope(text: str) -> dict:
    if text == "checkout":
        return {"type": "checkout", "value": "."}
    kind, sep, rest = text.partition("=")
    if not sep or not rest:
        raise Usage(f"unknown scope {text!r}: use checkout, branch=NAME, paths=GLOB[,GLOB] or resource=ID[@PATH]")
    if kind == "branch":
        name = rest.removeprefix("refs/heads/")
        if not re.fullmatch(r"[A-Za-z0-9._/-]+", name) or ".." in name:
            raise Usage(f"invalid branch name {name!r}")
        return {"type": "branch", "value": name}
    if kind == "paths":
        globs = [g.strip() for g in rest.split(",") if g.strip()]
        bad = [g for g in globs if not safe_relpath(g)]
        if not globs or bad:
            raise Usage(f"paths must be canonical, relative and inside the checkout: {bad or rest!r}")
        return {"type": "paths", "value": globs}
    if kind == "resource":
        rid, _, path = rest.partition("@")
        if not re.fullmatch(r"[A-Za-z0-9._:-]+", rid) or (path and not safe_relpath(path)):
            raise Usage(f"invalid resource {rest!r}")
        return {"type": "resource", "value": rid, **({"path": path} if path else {})}
    raise Usage(f"unknown scope type {kind!r}")


def literal_prefix(glob: str) -> str:
    parts = []
    for part in PurePosixPath(glob).parts:
        if any(c in part for c in GLOB_CHARS):
            break
        parts.append(part)
    return "/".join(parts)


def scope_paths(scope: dict, root: Path) -> list[Path] | None:
    """Resolved path prefixes of a scope (symlinks followed), or None when they cannot be resolved inside the
    checkout. None means overlap cannot be determined, which counts as a conflict."""
    globs = scope["value"] if scope["type"] == "paths" else ([scope["path"]] if scope.get("path") else [])
    out = []
    for glob in globs:
        if not isinstance(glob, str) or not safe_relpath(glob):
            return None
        try:
            resolved = (root / literal_prefix(glob)).resolve()
            resolved.relative_to(root)
        except (OSError, RuntimeError, ValueError):
            return None
        out.append(resolved)
    return out


def case_insensitive(root: Path) -> bool:
    try:
        return (root / ".GIT").exists() and os.path.samefile(root / ".GIT", root / ".git")
    except OSError:
        return False


def overlap(a: dict, b: dict, root: Path) -> bool:
    """Conservative: True when the scopes may touch the same thing, or when that cannot be determined."""
    if "checkout" in (a["type"], b["type"]):
        return True                                   # a checkout claim overlaps every narrower claim
    if "branch" in (a["type"], b["type"]):
        return a["type"] == b["type"] and a["value"] == b["value"]   # a branch is not the working tree
    if a["type"] == b["type"] == "resource" and a["value"] == b["value"]:
        return True
    pa, pb = scope_paths(a, root), scope_paths(b, root)
    if pa is None or pb is None:
        return True
    fold = case_insensitive(root)

    def key(path: Path) -> PurePosixPath:
        text = unicodedata.normalize("NFC", str(path))
        return PurePosixPath(text.casefold() if fold else text)
    ka, kb = [key(x) for x in pa], [key(y) for y in pb]
    return any(x == y or x in y.parents or y in x.parents for x in ka for y in kb)


def conflicts_with(mode_a: str, mode_b: str) -> bool:
    return not (mode_a == "shared" and mode_b == "shared")


# ------------------------------------------------------------------------------------------------ registry

def validate_claim(data, stem: str) -> list[str]:
    where = f"claim {stem}"
    if not isinstance(data, dict):
        return [f"{where}: not an object"]
    if data.get("kind") != "claim" or type(data.get("version")) is not int or data.get("version") != 1:
        return [f"{where}: not a version 1 claim"]
    p = []
    if data.get("id") != stem:
        p.append(f"{where}: id does not match the file name")
    h = data.get("holder")
    if not isinstance(h, dict):
        return p + [f"{where}: holder is not an object"]
    for key in ("agent", "session", "host"):
        if not isinstance(h.get(key), str) or not h[key]:
            p.append(f"{where}: holder.{key} missing")
    pid, start = h.get("pid"), h.get("process_start")
    if (pid is None) != (start is None) or (pid is not None and (type(pid) is not int or pid < 1
                                                                 or not isinstance(start, str) or not start)):
        p.append(f"{where}: holder pid and process_start must be a positive PID and a string, or both null")
    if h.get("boot") is not None and not isinstance(h["boot"], str):
        p.append(f"{where}: holder.boot must be a string")
    s = data.get("scope")
    try:
        if not isinstance(s, dict) or s.get("type") not in ("checkout", "branch", "paths", "resource"):
            raise ValueError
        if s["type"] == "paths":
            if not isinstance(s.get("value"), list) or not s["value"] or not all(isinstance(g, str) and safe_relpath(g)
                                                                                for g in s["value"]):
                raise ValueError
        elif not isinstance(s.get("value"), str) or (s.get("path") is not None and not (
                isinstance(s["path"], str) and safe_relpath(s["path"]))):
            raise ValueError
    except (ValueError, KeyError):
        p.append(f"{where}: invalid scope")
    if data.get("mode") not in ("exclusive", "shared"):
        p.append(f"{where}: invalid mode")
    if not isinstance(data.get("intent"), str) or not data["intent"]:
        p.append(f"{where}: intent missing")
    created, expires = parse_stamp(data.get("created")), parse_stamp(data.get("expires"))
    if not created or not expires or expires <= created:
        p.append(f"{where}: created and expires must be UTC timestamps with expires after created")
    t = data.get("transfer")
    if t is not None and not (isinstance(t, dict) and isinstance(t.get("token_sha256"), str)
                              and re.fullmatch(r"[0-9a-f]{64}", t["token_sha256"])
                              and parse_stamp(t.get("offered")) and parse_stamp(t.get("expires"))
                              and parse_stamp(t["expires"]) > parse_stamp(t["offered"])):
        p.append(f"{where}: invalid pending transfer")
    hist = data.get("history")
    if hist is not None and not (isinstance(hist, list) and all(
            isinstance(e, dict) and e.get("event") in ("transferred", "recovered") and parse_stamp(e.get("at"))
            for e in hist)):
        p.append(f"{where}: invalid ownership history")
    return p


class Registry:
    def __init__(self, root: Path):
        self.root = root
        self.state = root / STATE
        self.claims = self.state / "claims"
        self.stale = self.claims / "stale"

    def _safe_dir(self, d: Path, create: bool) -> bool:
        if d.is_symlink() or (d.exists() and not d.is_dir()):
            raise Unknown(f"{d.relative_to(self.root)} is a symlink or not a directory: unsafe registry location")
        if not d.exists():
            if not create:
                return False
            try:
                d.mkdir(mode=0o700)
            except FileExistsError:                   # another agent created it first: verify what is there now
                pass
            if d.is_symlink() or not d.is_dir():
                raise Unknown(f"{d.relative_to(self.root)} is a symlink or not a directory: unsafe registry location")
        if d.resolve() != self.root / d.relative_to(self.root):
            raise Unknown(f"{d.relative_to(self.root)} resolves outside the checkout: unsafe registry location")
        return True

    def ignored(self) -> bool:
        return git(self.root, "check-ignore", "-q", f"{STATE}/claims/probe.json").returncode == 0

    def ensure(self) -> None:
        for d in (self.state, self.claims, self.stale):
            self._safe_dir(d, create=True)
        ignore = self.state / ".gitignore"
        if ignore.is_symlink():
            raise Unknown(".agent-state/.gitignore is a symlink: unsafe registry location")
        if not ignore.exists():
            try:
                fd = os.open(ignore, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
                with os.fdopen(fd, "w") as fh:
                    fh.write("*\n")
            except FileExistsError:
                pass
        if not self.ignored():
            raise Unknown("git would track the claim registry (.agent-state is not ignored): refusing to use it")

    def exists(self) -> bool:
        return self._safe_dir(self.state, create=False) and self._safe_dir(self.claims, create=False)

    @contextmanager
    def locked(self, timeout: float):
        if fcntl is None:
            raise Unknown("advisory locking (fcntl) is unavailable on this platform: claims are unavailable")
        try:
            fd = os.open(self.state / "claims.lock", os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        except OSError as e:
            raise Unknown(f"the registry lock cannot be opened safely: {e}")
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise Unknown("the registry lock is not a regular file")
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise Unknown(f"the claim registry stayed locked for {timeout:g}s: try again later")
                    time.sleep(0.02)
                except OSError as e:
                    raise Unknown(f"advisory locking failed on this filesystem: {e}")
            yield
        finally:
            os.close(fd)                              # closing releases the lock; the file itself is never removed

    def read(self) -> tuple[list[dict], list[str], list[str], list[str]]:
        """(claims, leftover temporary files, problems, metadata files). Any problem: the registry is uninspectable."""
        claims, leftovers, problems, metadata = [], [], [], []
        for entry in sorted(os.scandir(self.claims), key=lambda e: e.name):
            name = entry.name
            if name == "stale" and entry.is_dir(follow_symlinks=False):
                continue
            regular = entry.is_file(follow_symlinks=False) and not entry.is_symlink()
            if name in METADATA_FILES and regular:
                metadata.append(name)
                continue
            if name.startswith(TMP_PREFIX) and regular:
                leftovers.append(name)
                continue
            stem = name[:-5] if name.endswith(".json") else ""
            if not CLAIM_ID.match(stem):
                problems.append(f"unexpected entry {name!r} in the registry")
                continue
            if not regular:
                problems.append(f"{name} is not a regular file")
                continue
            if entry.stat(follow_symlinks=False).st_size > MAX_CLAIM_BYTES:
                problems.append(f"{name} is too large to be a claim")
                continue
            try:
                data = strict_json(Path(entry.path).read_text(encoding="utf-8"))
            except (OSError, ValueError, RecursionError) as e:
                problems.append(f"{name} cannot be read: {e}")
                continue
            errors = validate_claim(data, stem)
            if errors:
                problems.extend(errors)
            else:
                claims.append(data)
        return claims, leftovers, problems, metadata

    def publish(self, claim: dict) -> None:
        tmp = self.claims / f"{TMP_PREFIX}{claim['id']}-{secrets.token_hex(4)}"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(claim, indent=2) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.claims / f"{claim['id']}.json")
        dfd = os.open(self.claims, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)

    def archive(self, claim_id: str) -> None:
        target = self.stale / f"{claim_id}.json"
        if target.exists():
            target = self.stale / f"{claim_id}-{secrets.token_hex(4)}.json"
        os.replace(self.claims / f"{claim_id}.json", target)


def transfer_pending(claim: dict, now: datetime.datetime) -> bool:
    t = claim.get("transfer")
    return bool(t) and parse_stamp(t["expires"]) > now


def blocking_state(claim: dict, state: str, now: datetime.datetime) -> str | None:
    """None when the claim is stale (expired, holder dead, no pending transfer); otherwise why it still blocks."""
    expired = parse_stamp(claim["expires"]) <= now
    if transfer_pending(claim, now) and state != "live":
        return "transfer-pending"
    if state == "dead":
        return None if expired else "holder-dead-unexpired"
    if state == "live":
        return "expired-held" if expired else "live"
    return "expired-unknown" if expired else "unknown"


def describe(claim: dict, state: str, reason: str) -> dict:
    return {"id": claim["id"], "state": state, "reason": reason, "scope": claim["scope"], "mode": claim["mode"],
            "intent": claim["intent"], "agent": claim["holder"]["agent"], "expires": claim["expires"],
            "transfer_pending": bool(claim.get("transfer")), "ownership_changes": len(claim.get("history", []))}


def public_identity(holder: dict) -> dict:
    return {k: holder.get(k) for k in ("agent", "host", "boot", "pid", "process_start")}


# ------------------------------------------------------------------------------------------------ operations

def _ttl(minutes) -> datetime.timedelta:
    if type(minutes) not in (int, float) or not 1 <= minutes <= 1440:
        raise Usage("--ttl must be between 1 and 1440 minutes")
    return datetime.timedelta(minutes=minutes)


def _registry(repo) -> Registry:
    root = checkout_root(repo)
    problem = coordination_problem(root)
    if problem:
        raise Unknown(problem)
    registry = Registry(root)
    registry.ensure()
    return registry


def _uninspectable(problems: list[str]) -> dict:
    return {"status": "unknown", "reason": "the claim registry cannot be inspected: " + "; ".join(problems)}


def _unidentified() -> dict:
    return {"status": "unknown", "reason": "this session's holder process cannot be established as a session boundary "
                                           "(see --holder-pid): a claim it made could not be verified, renewed or "
                                           "released; coordinate manually"}


def acquire(repo, scope: dict, *, mode: str = "exclusive", intent: str, ttl_minutes=120, session: str | None = None,
            holder_pid: int | None = None, agent: str = "agent", lock_timeout: float = 10.0) -> dict:
    """Serialized conflict-check-and-acquire. Returns {"status": "granted"|"conflict"|"unknown", ...}."""
    if mode not in ("exclusive", "shared") or not intent:
        raise Usage("mode must be exclusive or shared, and intent is required")
    ttl = _ttl(ttl_minutes)
    try:
        registry = _registry(repo)
        visible, _, _, _ = registry.read()            # unlocked, best effort: only to judge the session boundary
        me = caller_identity(holder_pid, visible)
        if me["pid"] is None:
            return _unidentified()
        with registry.locked(lock_timeout):
            claims, _, problems, _ = registry.read()
            if problems:
                return _uninspectable(problems)
            now, conflicts, archived = utcnow(), [], []
            local = {"host": me["host"], "boot": me["boot"]}
            for claim in claims:
                state, reason = holder_state(claim["holder"], local)
                blocks = blocking_state(claim, state, now)
                if blocks is None:
                    registry.archive(claim["id"])
                    archived.append(claim["id"])
                    continue
                own = session is not None and claim["holder"]["session"] == session and same_holder(claim["holder"], me)
                if not own and conflicts_with(mode, claim["mode"]) and overlap(scope, claim["scope"], registry.root):
                    conflicts.append(describe(claim, blocks, reason))
            if conflicts:
                return {"status": "conflict", "conflicts": conflicts, "archived": archived}
            token = session or secrets.token_hex(16)
            claim = {"kind": "claim", "version": 1, "id": now.strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4),
                     "holder": {"agent": agent, "session": token, "host": me["host"], "pid": me["pid"],
                                "process_start": me["start"], "boot": me["boot"]},
                     "scope": scope, "mode": mode, "intent": intent, "created": stamp(now), "expires": stamp(now + ttl)}
            registry.publish(claim)
            return {"status": "granted", "claim": claim, "session": token, "archived": archived}
    except Unknown as e:
        return {"status": "unknown", "reason": str(e)}


def _change(repo, claim_id: str, holder_pid: int | None, lock_timeout: float, change) -> dict:
    """Run change(registry, claim, caller, local, now) inside the critical section, on one claim."""
    if not CLAIM_ID.match(claim_id or ""):
        raise Usage(f"invalid claim id {claim_id!r}")
    try:
        registry = _registry(repo)
        visible, _, _, _ = registry.read()
        me = caller_identity(holder_pid, visible)
        with registry.locked(lock_timeout):
            claims, _, problems, _ = registry.read()
            if problems:
                return _uninspectable(problems)
            claim = next((c for c in claims if c["id"] == claim_id), None)
            if claim is None:
                return {"status": "missing", "reason": f"no active claim {claim_id}"}
            return change(registry, claim, me, {"host": me["host"], "boot": me["boot"]}, utcnow())
    except Unknown as e:
        return {"status": "unknown", "reason": str(e)}


def _token_ok(claim: dict, session) -> bool:
    return secrets.compare_digest(claim["holder"]["session"], session or "")


def _not_holder(claim: dict) -> dict:
    return {"status": "refused", "reason": "the session token matches, but this process is not the recorded holder "
                                           f"(process {claim['holder']['pid']}): a token alone does not establish "
                                           "ownership; take over with accept after a transfer, or adopt once the holder "
                                           "has died"}


def _pending(claim: dict) -> dict:
    return {"status": "refused", "reason": "a transfer of this claim is pending: the successor accepts it with the "
                                           "transfer token, or it lapses at " + claim["transfer"]["expires"]}


def renew(repo, claim_id: str, session: str, ttl_minutes=120, *, holder_pid: int | None = None,
          lock_timeout: float = 10.0) -> dict:
    """Extend a claim: only its current, verified holder may."""
    ttl = _ttl(ttl_minutes)

    def change(registry, claim, me, local, now):
        if not _token_ok(claim, session):
            return {"status": "refused", "reason": "the session token does not match this claim"}
        if not same_holder(claim["holder"], me):
            return _not_holder(claim)
        claim["expires"] = stamp(now + ttl)
        registry.publish(claim)
        return {"status": "renewed", "claim": claim}
    return _change(repo, claim_id, holder_pid, lock_timeout, change)


def release(repo, claim_id: str, session: str, *, holder_pid: int | None = None, lock_timeout: float = 10.0) -> dict:
    """End a claim: its verified holder may, and so may the bearer of its token once the holder has provably died and
    no transfer is pending."""
    def change(registry, claim, me, local, now):
        if not _token_ok(claim, session):
            return {"status": "refused", "reason": "the session token does not match this claim"}
        if not same_holder(claim["holder"], me):
            if holder_state(claim["holder"], local)[0] != "dead":
                return _not_holder(claim)
            if transfer_pending(claim, now):
                return _pending(claim)
        (registry.claims / f"{claim['id']}.json").unlink()
        return {"status": "released", "id": claim["id"]}
    return _change(repo, claim_id, holder_pid, lock_timeout, change)


def offer_transfer(repo, claim_id: str, session: str, ttl_minutes=30, *, holder_pid: int | None = None,
                   lock_timeout: float = 10.0) -> dict:
    """The current holder offers its claim to a successor and gets a one-time transfer token for the handoff. The claim
    stays the holder's until accepted; while the offer is open it is never archived as stale."""
    ttl = _ttl(ttl_minutes)

    def change(registry, claim, me, local, now):
        if not _token_ok(claim, session):
            return {"status": "refused", "reason": "the session token does not match this claim"}
        if not same_holder(claim["holder"], me):
            return _not_holder(claim)
        token = secrets.token_hex(16)
        claim["transfer"] = {"token_sha256": hashlib.sha256(token.encode()).hexdigest(), "offered": stamp(now),
                             "expires": stamp(now + ttl)}
        if parse_stamp(claim["expires"]) < now + ttl:
            claim["expires"] = stamp(now + ttl)       # the claim outlives its own transfer offer
        registry.publish(claim)
        return {"status": "offered", "id": claim["id"], "transfer_token": token,
                "offer_expires": claim["transfer"]["expires"]}
    return _change(repo, claim_id, holder_pid, lock_timeout, change)


def _take_over(registry, claim, me, now, event: str, agent: str) -> dict:
    if me["pid"] is None:
        return _unidentified()
    new_session = secrets.token_hex(16)
    history = claim.get("history", [])
    history.append({"event": event, "at": stamp(now), "from": public_identity(claim["holder"]),
                    "to": {"agent": agent, "host": me["host"], "boot": me["boot"], "pid": me["pid"],
                           "process_start": me["start"]}})
    claim["holder"] = {"agent": agent, "session": new_session, "host": me["host"], "pid": me["pid"],
                       "process_start": me["start"], "boot": me["boot"]}
    claim["history"] = history
    claim.pop("transfer", None)
    registry.publish(claim)                           # one atomic replacement under the lock: no window for a third agent
    return {"status": event, "claim": claim, "session": new_session}


def accept_transfer(repo, claim_id: str, transfer_token: str, *, holder_pid: int | None = None, agent: str = "agent",
                    lock_timeout: float = 10.0) -> dict:
    """The successor takes over an offered claim, atomically. The previous holder's session token stops working."""
    def change(registry, claim, me, local, now):
        if not transfer_pending(claim, now):
            return {"status": "refused", "reason": "no open transfer offer for this claim"}
        digest = hashlib.sha256((transfer_token or "").encode()).hexdigest()
        if not secrets.compare_digest(claim["transfer"]["token_sha256"], digest):
            return {"status": "refused", "reason": "the transfer token does not match the offer"}
        if same_holder(claim["holder"], me):
            return {"status": "refused", "reason": "this process already holds the claim"}
        return _take_over(registry, claim, me, now, "transferred", agent)
    return _change(repo, claim_id, holder_pid, lock_timeout, change)


def adopt(repo, claim_id: str, session: str, *, holder_pid: int | None = None, agent: str = "agent",
          lock_timeout: float = 10.0) -> dict:
    """Recovery: the bearer of a claim's session token takes it over once its holder has provably died. A live or
    unverifiable holder is never displaced this way, and a pending transfer goes to its intended successor."""
    def change(registry, claim, me, local, now):
        if not _token_ok(claim, session):
            return {"status": "refused", "reason": "the session token does not match this claim"}
        state, reason = holder_state(claim["holder"], local)
        if state != "dead":
            return {"status": "refused", "reason": f"the holder is {state} ({reason}): ask it to transfer the claim"}
        if transfer_pending(claim, now):
            return _pending(claim)
        return _take_over(registry, claim, me, now, "recovered", agent)
    return _change(repo, claim_id, holder_pid, lock_timeout, change)


def status(repo, lock_timeout: float = 10.0) -> dict:
    try:
        root = checkout_root(repo)
        registry = Registry(root)
        if not registry.exists():
            return {"status": "ok", "claims": [], "leftovers": [], "metadata": []}
        with registry.locked(lock_timeout):
            claims, leftovers, problems, metadata = registry.read()
        if problems:
            return _uninspectable(problems)
        local, now = here(), utcnow()
        rows = []
        for claim in claims:
            state, reason = holder_state(claim["holder"], local)
            rows.append(describe(claim, blocking_state(claim, state, now) or "stale", reason))
        return {"status": "ok", "claims": rows, "leftovers": leftovers, "metadata": metadata}
    except Unknown as e:
        return {"status": "unknown", "reason": str(e)}


def archive_stale(repo, lock_timeout: float = 10.0) -> dict:
    try:
        registry = _registry(repo)
        with registry.locked(lock_timeout):
            claims, _, problems, _ = registry.read()
            if problems:
                return _uninspectable(problems)
            local, now, moved = here(), utcnow(), []
            for claim in claims:
                state, _ = holder_state(claim["holder"], local)
                if blocking_state(claim, state, now) is None:
                    registry.archive(claim["id"])
                    moved.append(claim["id"])
        return {"status": "done", "archived": moved}
    except Unknown as e:
        return {"status": "unknown", "reason": str(e)}


def load_path_in_use():
    spec = importlib.util.spec_from_file_location("path_in_use_copy", HERE / "path_in_use.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def worst_visibility(found: list[str]) -> str:
    if not found:
        return "not checked"
    return max(found, key=lambda v: max((i for i, word in enumerate(VISIBILITY_RANK) if v.startswith(word)), default=4))


def activity_check(repo, scope: dict | None = None, *, session: str | None = None, disruptive: bool = False,
                   destructive: bool = False, holder_pid: int | None = None, accept_passive=(), lsof: str = "lsof",
                   show_all: bool = False) -> dict:
    """Read-only. {"verdict": "idle"|"busy"|"unknown", "coordination", "visibility", "processes", "evidence", ...}"""
    scope = scope or {"type": "checkout", "value": "."}
    disruptive = disruptive or destructive
    evidence, visibilities, lines = [], [], []
    flags = {"busy": False, "unknown": False}
    info = {"coordination": "available", "holder": None, "excluded": []}
    counts = {"active": 0, "passive": 0, "accepted": 0}

    def result() -> dict:
        shown = lines if show_all else lines[:DISPLAY_LIMIT]
        summary = [f"{len(lines)} matching processes ({counts['active']} active, {counts['passive']} passive, "
                   f"{counts['accepted']} accepted passive)"] if lines else []
        if len(lines) > len(shown):
            summary.append(f"{len(lines) - len(shown)} more not shown: use --all to list every one")
        worst = worst_visibility(visibilities)
        tail = [f"process visibility: {worst}"] if worst.startswith(("partial", "failed")) else []
        verdict = "busy" if flags["busy"] else "unknown" if flags["unknown"] else "idle"
        return {"verdict": verdict, "coordination": info["coordination"], "visibility": worst, "processes": counts,
                "evidence": evidence + summary + shown + tail, "excluded": info["excluded"], "holder": info["holder"]}

    def unknown(why: str) -> None:
        flags["unknown"] = True
        evidence.append(why)

    def busy(why: str) -> None:
        flags["busy"] = True
        evidence.append(why)

    try:
        root = checkout_root(repo)
    except Unknown as e:
        unknown(str(e))
        return result()
    problem = coordination_problem(root)
    if problem:
        info["coordination"] = f"unavailable: {problem}"
        unknown(f"coordination unavailable: {problem}")
    # Claims, read without the lock: claim files are published atomically.
    registry, claims = Registry(root), []
    try:
        if registry.exists():
            if not registry.ignored():
                info["coordination"] = "unavailable: git would track the claim registry"
                unknown("coordination unavailable: git would track the claim registry")
            claims, _, problems, metadata = registry.read()
            if problems:
                claims = []
                unknown("claim registry cannot be inspected: " + "; ".join(problems))
            if metadata:
                evidence.append(f"registry holds filesystem metadata ({', '.join(metadata)}): ignored, never removed")
    except (Unknown, OSError) as e:
        unknown(f"claim registry cannot be inspected: {e}")
    try:
        table = process_table()
        me = caller_identity(holder_pid, claims, table)
    except Unknown as e:
        table, me = None, {**here(), "pid": None, "start": None}
        unknown(f"process inspection failed: {e}")
    local, now, own_exclusive = {"host": me["host"], "boot": me["boot"]}, utcnow(), False
    for claim in claims:
        state, reason = holder_state(claim["holder"], local)
        blocks = blocking_state(claim, state, now)
        if not blocks:
            continue
        token_match = session is not None and claim["holder"]["session"] == session
        if token_match and same_holder(claim["holder"], me):
            if (claim["mode"] == "exclusive" and blocks == "live" and claim["scope"]["type"] != "branch"
                    and overlap(scope, claim["scope"], root)):
                own_exclusive = True
            continue
        if token_match:
            busy(f"claim {claim['id']} carries your session token but another process identity ({reason}): it is not "
                 "this session's; accept a transfer or adopt it before relying on it")
        elif overlap(scope, claim["scope"], root):
            line = f"claim {claim['id']} ({claim['mode']} {claim['scope']['type']}, {blocks}: {reason}): {claim['intent']}"
            unknown(line) if blocks in ("unknown", "expired-unknown") else busy(line)
    if disruptive and not own_exclusive:
        busy("this session holds no live exclusive claim covering the scope (shared claims never authorize writes): "
             "acquire or renew one and pass --session" if session else
             "disruptive operations need this session's exclusive claim: acquire one and pass --session")
    # Git operations in progress, and uncommitted work.
    r = git(root, "rev-parse", "--absolute-git-dir")
    if r.returncode != 0:
        unknown("git state cannot be read")
    else:
        git_dir = Path(r.stdout.strip())
        for name, meaning in GIT_IN_PROGRESS.items():
            if (git_dir / name).exists():
                busy(f"{meaning} ({name})")
        st = git(root, "status", "--porcelain=v1", "--untracked-files=normal")
        if st.returncode != 0:
            unknown("git status failed")
        elif st.stdout.strip():
            n = len(st.stdout.strip().splitlines())
            if disruptive:
                busy(f"{n} uncommitted or untracked paths: a disruptive operation would put them at risk; preserve or "
                     "attribute them first")
            else:
                evidence.append(f"{n} uncommitted or untracked paths")
    # Processes: working directories and open files, through the reused in-use check.
    if table is not None:
        try:
            own = set(ancestry(os.getpid(), table))
            if me["pid"] is not None:
                own |= {me["pid"]} | descendants(me["pid"], table)
                info["holder"] = f"pid {me['pid']} ({table[me['pid']][2][:80]})"
            info["excluded"] = sorted(own)
            pin = load_path_in_use()
            targets = [root] if scope["type"] in ("checkout", "branch") else (scope_paths(scope, root) or [root])
            procs = pin.list_processes()
            records, lsof_pid = pin.list_open_files(lsof)
            by_pid: dict[int, list[tuple[str, str, str]]] = {}
            for target in targets:
                verdict, visibility, matches = pin.classify(str(target), os.stat(root).st_uid, procs, records,
                                                            own | {os.getpid(), lsof_pid})
                visibilities.append(visibility)
                if verdict == pin.UNKNOWN:
                    flags["unknown"] = True
                for pid, cmd, fd, name in matches:
                    if (cmd, fd, name) not in by_pid.setdefault(pid, []):
                        by_pid[pid].append((cmd, fd, name))
            accepted, seen = set(accept_passive), set()
            parents = {row[0] for row in table.values()}
            for pid in sorted(by_pid):
                rows = by_pid[pid]
                cmd = rows[0][0]
                start = process_start(pid)
                ident = identity_token(pid, start) if start else None
                where = "; ".join(f"{'works in' if fd == 'cwd' else 'has open'} {name}" for _, fd, name in rows[:3])
                if all(fd == "cwd" for _, fd, _ in rows) and pid not in parents and ident:
                    seen.add(ident)
                    if ident in accepted and not destructive:
                        counts["accepted"] += 1
                        lines.append(f"accepted passive (owner-approved, revalidated): process {pid} ({cmd}) {where}; "
                                     f"identity {ident}")
                        continue
                    flags["busy"] = True
                    counts["passive"] += 1
                    note = "; an acceptance never applies to a destructive operation" if ident in accepted else ""
                    lines.append(f"passive: process {pid} ({cmd}) {where}; no child processes and no open files in "
                                 f"the scope; identity {ident}{note}")
                else:
                    flags["busy"] = True
                    counts["active"] += 1
                    lines.append(f"active: process {pid} ({cmd}) {where}" + (
                        "; has child processes" if pid in parents else ""))
            for ident in sorted(accepted - seen):
                evidence.append(f"accepted identity {ident} matches no passive process here now: not applied")
        except (Unknown, OSError, RuntimeError, subprocess.SubprocessError) as e:
            visibilities.append(f"failed ({e})")
            unknown(f"process inspection failed: {e}")
    return result()


# ---------------------------------------------------------------------------------------------------------- CLI

def main(argv: list[str]) -> int:
    if argv == ["--self-test"]:
        failures = self_test()
        for f in failures:
            print("FAIL:", f)
        print("coordination self-test: " + ("PASS" if not failures else f"{len(failures)} FAILED"))
        return 1 if failures else 0
    parser = argparse.ArgumentParser(prog="coordination.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("acquire", "renew", "release", "transfer", "accept", "adopt", "status", "check", "archive-stale"):
        p = sub.add_parser(name)
        p.add_argument("--repo", default=".")
        if name not in ("status", "archive-stale"):
            p.add_argument("--holder-pid", type=int)
        if name in ("acquire", "check"):
            p.add_argument("--scope", default="checkout")
            p.add_argument("--session")
        if name in ("renew", "release", "transfer", "accept", "adopt"):
            p.add_argument("--id", required=True)
        if name in ("renew", "release", "transfer", "adopt"):
            p.add_argument("--session", required=True)
        if name in ("acquire", "accept", "adopt"):
            p.add_argument("--agent", default=os.environ.get("CODING_AGENT", "agent"))
        if name in ("acquire", "renew", "transfer"):
            p.add_argument("--ttl", type=float, default=30 if name == "transfer" else 120)
        if name == "acquire":
            p.add_argument("--intent", required=True)
            p.add_argument("--mode", default="exclusive", choices=("exclusive", "shared"))
        if name == "accept":
            p.add_argument("--transfer-token", required=True)
        if name == "check":
            group = p.add_mutually_exclusive_group()
            group.add_argument("--disruptive", action="store_true")
            group.add_argument("--destructive", action="store_true")
            p.add_argument("--accept-passive", action="append", default=[], metavar="IDENTITY")
            p.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)
    ok = {"acquire": {"granted": 0, "conflict": 1}, "renew": {"renewed": 0}, "release": {"released": 0},
          "transfer": {"offered": 0}, "accept": {"transferred": 0}, "adopt": {"recovered": 0}, "status": {"ok": 0},
          "archive-stale": {"done": 0}}
    try:
        c = args.command
        if c == "check":
            r = activity_check(args.repo, parse_scope(args.scope), session=args.session, disruptive=args.disruptive,
                               destructive=args.destructive, holder_pid=args.holder_pid,
                               accept_passive=args.accept_passive, show_all=args.all)
            print(f"verdict: {r['verdict']}")
            print(f"coordination: {r['coordination']}")
            print(f"visibility: {r['visibility']}")
            for line in r["evidence"]:
                print(f"evidence: {line}")
            print(f"session holder: {r['holder'] or 'not established (only this command excluded)'}")
            print(f"excluded as this session's own processes: {len(r['excluded'])}")
            return {"idle": 0, "busy": 1}.get(r["verdict"], 2)
        if c == "acquire":
            r = acquire(args.repo, parse_scope(args.scope), mode=args.mode, intent=args.intent, ttl_minutes=args.ttl,
                        session=args.session, holder_pid=args.holder_pid, agent=args.agent)
        elif c == "renew":
            r = renew(args.repo, args.id, args.session, args.ttl, holder_pid=args.holder_pid)
        elif c == "release":
            r = release(args.repo, args.id, args.session, holder_pid=args.holder_pid)
        elif c == "transfer":
            r = offer_transfer(args.repo, args.id, args.session, args.ttl, holder_pid=args.holder_pid)
        elif c == "accept":
            r = accept_transfer(args.repo, args.id, args.transfer_token, holder_pid=args.holder_pid, agent=args.agent)
        elif c == "adopt":
            r = adopt(args.repo, args.id, args.session, holder_pid=args.holder_pid, agent=args.agent)
        elif c == "status":
            r = status(args.repo)
        else:
            r = archive_stale(args.repo)
        print(json.dumps(r, indent=2))
        return ok[c].get(r["status"], 2)
    except Usage as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


# ---------------------------------------------------------------------------------------------------------- self-test

# A cooperating agent: prints {"pid": ...}, performs one action, prints its result, optionally renews its own claim
# when a file appears, and stays alive until the stop file appears.
AGENT = r"""
import json, os, sys, time
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[1])
import coordination as c
repo, action, stop = sys.argv[2], sys.argv[3], sys.argv[4]
args = json.loads(sys.argv[5])
me = os.getpid()
print(json.dumps({"pid": me}), flush=True)
if action == "race":
    while not os.path.exists(args["go"]):
        time.sleep(0.002)
    r = c.acquire(repo, c.parse_scope(args["scope"]), mode=args["mode"], intent="race", ttl_minutes=30, holder_pid=me,
                  lock_timeout=30)
elif action == "acquire":
    r = c.acquire(repo, c.parse_scope(args["scope"]), intent="x", ttl_minutes=30, holder_pid=me,
                  agent=args.get("agent", "agent"))
    if r["status"] == "granted" and args.get("offer"):
        r["offer"] = c.offer_transfer(repo, r["claim"]["id"], r["session"], 30, holder_pid=me)
elif action == "renew":
    r = c.renew(repo, args["id"], args["session"], 30, holder_pid=me)
elif action == "accept":
    r = c.accept_transfer(repo, args["id"], args["token"], holder_pid=me, agent="successor")
elif action == "check":
    r = c.activity_check(repo, session=args.get("session"), holder_pid=me)
elif action == "renew-loop":                          # renews as its parent's session (automatic holder resolution)
    print("{}", flush=True)
    out = []
    for _ in range(40):
        out.append(c.renew(repo, args["id"], args["session"], 30)["status"])
        time.sleep(0.01)
    r = {"status": out}
print(json.dumps(r), flush=True)
if args.get("renew_when"):
    while not os.path.exists(args["renew_when"]):
        time.sleep(0.02)
    print(json.dumps(c.renew(repo, r["claim"]["id"], r["session"], 30, holder_pid=me)), flush=True)
while not os.path.exists(stop):
    time.sleep(0.05)
"""

HOLD_LOCK = r"""
import os, sys, time
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[1])
import coordination as c
reg = c.Registry(c.checkout_root(sys.argv[2]))
reg.ensure()
with reg.locked(10):
    if sys.argv[3] == "publish":
        (reg.claims / (c.TMP_PREFIX + "interrupted")).write_text('{"kind": "claim", "version"')
    print("locked", flush=True)
    time.sleep(120)
"""


def tree_digest(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        st = p.lstat()
        h.update(f"{p.relative_to(root).as_posix()}\0{stat.S_IFMT(st.st_mode)}\0{st.st_mtime_ns}\0".encode())
        if p.is_file() and not p.is_symlink():
            h.update(p.read_bytes())
    return h.hexdigest()


def self_test() -> list[str]:
    """Real processes and fixture repositories under one private directory. Explicit checks, so it runs under -O."""
    failures: list[str] = []
    if os.name != "posix" or fcntl is None:
        return ["this self-test needs a POSIX system with fcntl (macOS or Linux)"]
    for tool in ("git", "ps", "lsof"):
        if shutil.which(tool) is None:
            return [f"{tool} is required by this self-test"]
    pycache_before = (HERE / "__pycache__").exists()
    base = Path(tempfile.mkdtemp(prefix="coordination-")).resolve()
    children: list[subprocess.Popen] = []
    orphans: dict[int, str | None] = {}               # pid -> start time: never signal a reused PID
    agents: list[int] = []
    stop = base / "stop"
    env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="t",
               GIT_AUTHOR_EMAIL="t@example.invalid", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid",
               PYTHONDONTWRITEBYTECODE="1")

    def fail(msg: str) -> None:
        failures.append(msg)

    def repo(name: str) -> Path:
        root = base / name
        (root / "src" / "parser").mkdir(parents=True)
        (root / "src" / "parser" / "a.py").write_text("x = 1\n")
        (root / "docs").mkdir()
        for args in (["init", "-q"], ["add", "."], ["commit", "-q", "-m", "init"]):
            subprocess.run(["git", "-C", str(root), *args], env=env, check=True, capture_output=True)
        return root

    def kill(pid: int) -> None:
        """SIGKILL an orphan we started, if it is still that process, and wait until it is gone."""
        if orphans.pop(pid, None) != process_start(pid):
            return
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        for _ in range(250):
            if process_start(pid) is None:
                return
            time.sleep(0.02)

    def agent(root: Path, action: str, child: bool = False, **args) -> tuple[subprocess.Popen, int]:
        """Another agent's process: detached (not our descendant) unless child is set."""
        command = [sys.executable, "-B", "-c", AGENT, str(HERE), str(root), action, str(stop), json.dumps(args)]
        if not child:
            command = ["sh", "-c", '"$@" </dev/null &', "sh", *command]
        p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        children.append(p)
        if not child:
            p.wait(timeout=30)
        first = p.stdout.readline()
        pid = json.loads(first)["pid"] if first else -1
        if not child and pid > 0:
            orphans[pid] = process_start(pid)
            agents.append(pid)
        return p, pid

    def reply(handle) -> dict:
        line = handle[0].stdout.readline()
        if not line:
            return {"status": "crashed: " + ((handle[0].stderr.read().strip().splitlines() or ["?"])[-1])[:150]}
        return json.loads(line)

    def orphan(command: str, cwd: Path) -> int:
        """A process that is not our descendant: another agent's server or shell, as far as the check can tell."""
        out = subprocess.run(["sh", "-c", f"{command} </dev/null >/dev/null 2>&1 & echo $!"], cwd=cwd,
                             capture_output=True, text=True, timeout=30)
        pid = int(out.stdout.strip())
        time.sleep(0.1)
        orphans[pid] = process_start(pid)
        return pid

    def fixture_claim(root: Path, scope: dict, *, mode="exclusive", pid=None, start="auto", host=None, boot="auto",
                      expires_in=30, session="fixture-session", extra=None) -> str:
        reg = Registry(root)
        reg.ensure()
        now = utcnow()
        cid = now.strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4)
        if start == "auto":
            start = process_start(pid) if pid else None
        claim = {"kind": "claim", "version": 1, "id": cid,
                 "holder": {"agent": "other-agent", "session": session, "host": host or socket.gethostname(),
                            "pid": pid, "process_start": start, "boot": boot_id() if boot == "auto" else boot},
                 "scope": scope, "mode": mode, "intent": "fixture", "created": stamp(now - datetime.timedelta(hours=2)),
                 "expires": stamp(now + datetime.timedelta(minutes=expires_in)), **(extra or {})}
        reg.publish(claim)
        return cid

    def clear(root: Path) -> None:
        for p in (root / STATE / "claims").glob("*"):
            if p.is_file() or p.is_symlink():
                p.unlink()

    def end_agents() -> None:
        """Every agent started so far exits; fixture holders such as `holder` keep running."""
        stop.touch()
        for p in children:
            if p.args[0] != "sh":
                try:
                    p.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    p.kill()
        for pid in agents:
            for _ in range(250):
                if pid not in orphans or process_start(pid) != orphans[pid]:
                    break
                time.sleep(0.02)
            kill(pid)
        agents.clear()
        stop.unlink()

    def expect(label: str, res: dict, want: str, fragment: str = "") -> None:
        text = json.dumps(res)
        if res.get("status", res.get("verdict")) != want or fragment not in text:
            fail(f"{label}: expected {want} {fragment!r}, got {text[:320]}")

    def refused_usage(label: str, call) -> None:
        try:
            call()
            fail(f"{label}: accepted")
        except Usage:
            pass

    def watchdog(signum, frame):
        raise TimeoutError("the self-test took longer than 300 s: a child process is blocking")
    previous = signal.signal(signal.SIGALRM, watchdog)
    signal.alarm(300)
    checkout = parse_scope("checkout")
    me = os.getpid()
    try:
        # ---- races between independent agent processes (the first race also creates the registry)
        root = repo("race")
        go = base / "go"

        def race(scopes):
            go.unlink(missing_ok=True)
            racers = [agent(root, "race", scope=s, mode=m, go=str(go)) for s, m in scopes]
            time.sleep(0.3)
            go.touch()
            return [reply(r)["status"] for r in racers]

        results = race([("checkout", "exclusive")] * 8)
        live = sorted((root / STATE / "claims").glob("*.json"))
        if results.count("granted") != 1 or results.count("conflict") != 7 or len(live) != 1:
            fail(f"8 simultaneous overlapping requests: {results}, {len(live)} claims")
        end_agents()
        clear(root)
        results = race([(f"paths=area{i}/**", "exclusive") for i in range(6)])
        if results != ["granted"] * 6:
            fail(f"6 simultaneous non-overlapping requests: {results}")
        end_agents()
        clear(root)

        # ---- registry created concurrently: another agent's mkdir wins between our check and our mkdir
        racing = repo("mkdir-race")
        original_mkdir = Path.mkdir

        def mkdir_after_another_agent(self, *args, **kwargs):
            original_mkdir(self, *args, **{**kwargs, "exist_ok": True})
            return original_mkdir(self, *args, **kwargs)
        Path.mkdir = mkdir_after_another_agent
        try:
            expect("registry created concurrently", acquire(racing, checkout, intent="x", holder_pid=me), "granted")
        finally:
            Path.mkdir = original_mkdir

        # ---- shared, exclusive and branch semantics (fixture holders are independent processes)
        holder = orphan("sleep 300", base)
        fixture_claim(root, parse_scope("paths=docs/**"), mode="shared", pid=holder)
        expect("shared beside shared", acquire(root, parse_scope("paths=docs/**"), mode="shared", intent="read",
                                               holder_pid=me), "granted")
        expect("exclusive beside shared", acquire(root, parse_scope("paths=docs/x/**"), intent="edit", holder_pid=me),
               "conflict", '"state": "live"')
        clear(root)
        fixture_claim(root, checkout, pid=holder)
        expect("shared beside exclusive checkout", acquire(root, parse_scope("paths=docs/**"), mode="shared",
                                                           intent="read", holder_pid=me), "conflict")
        clear(root)
        fixture_claim(root, parse_scope("branch=feature"), pid=holder)
        expect("paths beside a branch claim", acquire(root, parse_scope("paths=src/**"), intent="e", holder_pid=me),
               "granted")
        clear(root)
        fixture_claim(root, parse_scope("branch=feature"), pid=holder)
        expect("checkout beside a branch claim", acquire(root, checkout, intent="switch", holder_pid=me), "conflict")
        expect("same branch twice", acquire(root, parse_scope("branch=feature"), intent="p", holder_pid=me), "conflict")
        clear(root)

        # ---- lifetime: expired-but-running, PID reuse, unknown, another host, reboot, pending transfer
        fixture_claim(root, checkout, pid=holder, expires_in=-5)
        expect("expired claim whose holder runs", acquire(root, checkout, intent="x", holder_pid=me), "conflict",
               "expired-held")
        clear(root)
        fixture_claim(root, checkout, pid=holder, start="lstart:Thu Jan  1 00:00:00 1970")
        expect("reused PID, not expired", acquire(root, checkout, intent="x", holder_pid=me), "conflict",
               "holder-dead-unexpired")
        clear(root)
        cid = fixture_claim(root, checkout, pid=holder, start="lstart:Thu Jan  1 00:00:00 1970", expires_in=-5)
        r = acquire(root, checkout, intent="x", holder_pid=me)
        expect("reused PID and expired: archived as stale", r, "granted")
        if cid not in r.get("archived", []) or not (root / STATE / "claims" / "stale" / f"{cid}.json").exists():
            fail(f"stale claim not archived: {r}")
        clear(root)
        offer = {"transfer": {"token_sha256": "0" * 64, "offered": stamp(utcnow()),
                              "expires": stamp(utcnow() + datetime.timedelta(minutes=10))}}
        fixture_claim(root, checkout, pid=holder, start="lstart:x", expires_in=-5, extra=offer)
        expect("expired, holder dead, transfer pending: still protected", acquire(root, checkout, intent="x",
                                                                                  holder_pid=me), "conflict",
               "transfer-pending")
        clear(root)
        fixture_claim(root, checkout, pid=None, start=None, expires_in=-5)
        expect("holder identity not recorded", acquire(root, checkout, intent="x", holder_pid=me), "conflict",
               "expired-unknown")
        clear(root)
        fixture_claim(root, checkout, pid=holder, host="another-machine.example", expires_in=-60)
        expect("claim from another machine", acquire(root, checkout, intent="x", holder_pid=me), "conflict",
               "another host")
        clear(root)
        fixture_claim(root, checkout, pid=holder, boot="previous-boot", expires_in=-5)
        expect("holder from before a reboot, expired", acquire(root, checkout, intent="x", holder_pid=me), "granted")
        clear(root)

        # ---- registry lock: timeout, death inside the critical section, interrupted publication
        locker = subprocess.Popen([sys.executable, "-B", "-c", HOLD_LOCK, str(HERE), str(root), "plain"],
                                  stdout=subprocess.PIPE, text=True, env=env)
        children.append(locker)
        locker.stdout.readline()
        t0 = time.monotonic()
        expect("registry lock held elsewhere", acquire(root, checkout, intent="x", holder_pid=me, lock_timeout=0.5),
               "unknown", "stayed locked")
        if not 0.4 < time.monotonic() - t0 < 5:
            fail(f"lock timeout took {time.monotonic() - t0:.2f}s")
        locker.send_signal(signal.SIGKILL)
        locker.wait()
        t0 = time.monotonic()
        r = acquire(root, checkout, intent="after a crash", holder_pid=me, lock_timeout=5)
        expect("lock after its holder was killed inside the critical section", r, "granted")
        if time.monotonic() - t0 > 2:
            fail("the lock of a killed process was not released promptly")
        release(root, r["claim"]["id"], r["session"], holder_pid=me)
        inode = os.stat(root / STATE / "claims.lock").st_ino
        writer = subprocess.Popen([sys.executable, "-B", "-c", HOLD_LOCK, str(HERE), str(root), "publish"],
                                  stdout=subprocess.PIPE, text=True, env=env)
        children.append(writer)
        writer.stdout.readline()
        writer.send_signal(signal.SIGKILL)
        writer.wait()
        r = acquire(root, checkout, intent="after an interrupted publication", holder_pid=me)
        expect("acquire after an interrupted publication", r, "granted")
        st = status(root)
        if st.get("leftovers") != [TMP_PREFIX + "interrupted"] or len(st.get("claims", [])) != 1:
            fail(f"interrupted publication: {st}")
        if os.stat(root / STATE / "claims.lock").st_ino != inode:
            fail("the registry lock file was replaced")
        release(root, r["claim"]["id"], r["session"], holder_pid=me)

        # ---- ownership: the token alone is not ownership; renewal by the holder only; concurrent renew and release
        r = acquire(root, checkout, intent="ownership", holder_pid=me)
        cid, token = r["claim"]["id"], r["session"]
        expect("a successor with a valid token but another process identity cannot renew",
               reply(agent(root, "renew", id=cid, session=token)), "refused", "does not establish ownership")
        expect("a token match does not make another holder's claim one's own in a check",
               reply(agent(root, "check", session=token)), "busy", "carries your session token but another process")
        expect("renewal of a live claim with a wrong token", renew(root, cid, "not-the-token", holder_pid=me), "refused")
        expect("release of a live claim with a wrong token", release(root, cid, "not-the-token", holder_pid=me),
               "refused")
        loop = agent(root, "renew-loop", child=True, id=cid, session=token)
        loop[0].stdout.readline()
        time.sleep(0.3)
        rel = release(root, cid, token, holder_pid=me)
        renewed = reply(loop)["status"]
        if rel["status"] != "released" or (root / STATE / "claims" / f"{cid}.json").exists():
            fail(f"release during renewals: {rel}")
        if not isinstance(renewed, list) or "renewed" not in renewed or "missing" not in renewed:
            fail(f"the renew/release race did not interleave: {renewed}")
        elif "renewed" in renewed[renewed.index("missing"):]:
            fail(f"a claim was renewed after its release: {renewed}")
        expect("renewal of a released claim", renew(root, cid, token, holder_pid=me), "missing")
        end_agents()

        # ---- transfer: offered by the holder, accepted by the successor under the lock, audited
        t = repo("transfer")
        renew_a = base / "renew-a"
        a = agent(t, "acquire", scope="checkout", agent="claude-code", offer=True, renew_when=str(renew_a))
        offered = reply(a)
        cid, old_token = offered["claim"]["id"], offered["session"]
        xfer = offered["offer"]["transfer_token"]
        expect("a third agent while a transfer is open", reply(agent(t, "acquire", scope="checkout")), "conflict")
        expect("accept with a wrong transfer token", reply(agent(t, "accept", id=cid, token="not-the-transfer-token")),
               "refused")
        b = agent(t, "accept", id=cid, token=xfer)
        expect("the successor accepts the transfer", reply(b), "transferred")
        renew_a.touch()
        expect("the former holder cannot renew after the transfer", reply(a), "refused", "does not match")
        claim = json.loads((t / STATE / "claims" / f"{cid}.json").read_text())
        hist = claim.get("history", [])
        if (claim["holder"]["pid"] != b[1] or len(hist) != 1 or hist[0]["event"] != "transferred"
                or hist[0]["from"]["pid"] != a[1] or hist[0]["to"]["pid"] != b[1] or "session" in json.dumps(hist)
                or "transfer" in claim):
            fail(f"transfer record: {json.dumps(claim)[:400]}")
        kill(a[1])
        expect("the transferred claim stays live after the former holder ended", status(t), "ok", '"state": "live"')
        expect("the former holder's token no longer renews or releases", release(t, cid, old_token, holder_pid=me),
               "refused", "does not match")
        expect("a third agent after the transfer", acquire(t, checkout, intent="x", holder_pid=me), "conflict", "live")
        expect("accepting the same offer twice", reply(agent(t, "accept", id=cid, token=xfer)), "refused",
               "no open transfer")
        end_agents()
        clear(t)
        # A holder that dies while its offer is open: protected until the offer lapses, and the successor can accept.
        d = agent(t, "acquire", scope="paths=docs/**", offer=True)
        offered = reply(d)
        cid, dtoken, xfer = offered["claim"]["id"], offered["session"], offered["offer"]["transfer_token"]
        kill(d[1])
        expect("a third agent while a dead holder's offer is open", acquire(t, parse_scope("paths=docs/**"),
                                                                            intent="x", holder_pid=me), "conflict",
               "transfer-pending")
        expect("adopting while a transfer is pending", adopt(t, cid, dtoken, holder_pid=me), "refused", "pending")
        expect("releasing a dead holder's claim while a transfer is pending", release(t, cid, dtoken, holder_pid=me),
               "refused", "pending")
        expect("the successor accepts after the holder died", reply(agent(t, "accept", id=cid, token=xfer)),
               "transferred")
        end_agents()
        clear(t)
        lapsed = {"transfer": {"token_sha256": hashlib.sha256(b"t0").hexdigest(),
                               "offered": stamp(utcnow() - datetime.timedelta(minutes=30)),
                               "expires": stamp(utcnow() - datetime.timedelta(minutes=1))}}
        cid = fixture_claim(t, checkout, pid=holder, extra=lapsed)
        expect("accepting a lapsed offer", accept_transfer(t, cid, "t0", holder_pid=me), "refused", "no open transfer")
        clear(t)

        # ---- recovery (adopt): only once the holder has provably died
        rec = repo("recover")
        d = agent(rec, "acquire", scope="checkout")
        held = reply(d)
        cid, dtoken = held["claim"]["id"], held["session"]
        expect("adopt while the holder runs", adopt(rec, cid, dtoken, holder_pid=me), "refused", "live")
        kill(d[1])
        expect("adopt with a wrong token", adopt(rec, cid, "nope", holder_pid=me), "refused")
        expect("adopt after the holder died", adopt(rec, cid, dtoken, holder_pid=me, agent="codex"), "recovered")
        if json.loads((rec / STATE / "claims" / f"{cid}.json").read_text())["history"][0]["event"] != "recovered":
            fail("recovery was not recorded in the claim's history")
        unknown_id = fixture_claim(rec, parse_scope("paths=docs/**"), pid=None, start=None, session="known-token")
        expect("adopting a claim whose holder is unknown", adopt(rec, unknown_id, "known-token", holder_pid=me),
               "refused", "unknown")
        expect("renewing a claim whose holder is unknown", renew(rec, unknown_id, "known-token", holder_pid=me),
               "refused")
        expect("releasing a claim whose holder is unknown", release(rec, unknown_id, "known-token", holder_pid=me),
               "refused")

        # ---- registry contents: malformed and unsafe fail closed; recognized metadata does not
        claims_dir = root / STATE / "claims"
        clear(root)
        bad_holder = {"kind": "claim", "version": 1, "id": "20260101T000000Z-0000aaae",
                      "holder": {"agent": "a", "session": "s", "host": "h", "pid": 123, "process_start": None},
                      "scope": checkout, "mode": "exclusive", "intent": "i", "created": "2026-01-01T00:00:00Z",
                      "expires": "2026-01-01T01:00:00Z"}
        for label, name, content in [("garbage", "20260101T000000Z-0000aaaa.json", "{not json"),
                                     ("duplicate keys", "20260101T000000Z-0000aaab.json",
                                      '{"kind": "claim", "kind": "claim"}'),
                                     ("wrong types", "20260101T000000Z-0000aaac.json",
                                      json.dumps({"kind": "claim", "version": 1, "id": "20260101T000000Z-0000aaac"})),
                                     ("malformed holder identity", "20260101T000000Z-0000aaae.json",
                                      json.dumps(bad_holder)),
                                     ("unexpected file", "notes.txt", "hello"),
                                     ("unexpected hidden file", ".notes", "hello")]:
            (claims_dir / name).write_text(content)
            expect(f"registry with {label}", acquire(root, checkout, intent="x", holder_pid=me), "unknown",
                   "cannot be inspected")
            expect(f"activity check with {label}", activity_check(root, holder_pid=me), "unknown", "cannot be inspected")
            (claims_dir / name).unlink()
        (claims_dir / ".DS_Store").write_bytes(b"\x00\x00\x00\x01Bud1")
        r = acquire(root, checkout, intent="x", holder_pid=me)
        expect("harmless filesystem metadata", r, "granted")
        if status(root).get("metadata") != [".DS_Store"] or not (claims_dir / ".DS_Store").exists():
            fail("metadata was not reported, or was removed")
        if "never removed" not in json.dumps(activity_check(root, holder_pid=me, session=r["session"])):
            fail("the check does not report registry metadata")
        release(root, r["claim"]["id"], r["session"], holder_pid=me)
        (claims_dir / ".DS_Store").unlink()
        (claims_dir / ".DS_Store").symlink_to(base / "elsewhere")
        expect("a symlink named like metadata", acquire(root, checkout, intent="x", holder_pid=me), "unknown")
        (claims_dir / ".DS_Store").unlink()
        (claims_dir / "20260101T000000Z-0000aaad.json").symlink_to(base / "elsewhere.json")
        expect("symlinked claim", acquire(root, checkout, intent="x", holder_pid=me), "unknown", "not a regular file")
        (claims_dir / "20260101T000000Z-0000aaad.json").unlink()
        unsafe = repo("unsafe")
        (base / "outside-state").mkdir()
        (unsafe / STATE).symlink_to(base / "outside-state", target_is_directory=True)
        expect("symlinked registry directory", acquire(unsafe, checkout, intent="x", holder_pid=me), "unknown",
               "unsafe registry location")
        expect("check with a symlinked registry directory", activity_check(unsafe, holder_pid=me), "unknown")
        tracked = repo("tracked")
        (tracked / STATE / "claims").mkdir(parents=True)
        (tracked / STATE / ".gitignore").write_text("# ignores nothing\n")
        expect("registry git would track", acquire(tracked, checkout, intent="x", holder_pid=me), "unknown",
               "would track")
        expect("check with a registry git would track", activity_check(tracked, holder_pid=me), "unknown",
               "would track")

        # ---- overlap semantics: parents, children, aliases, case, canonical paths
        o = repo("overlap")
        (o / "lnk").symlink_to(o / "src", target_is_directory=True)
        (o / "out").symlink_to(base, target_is_directory=True)
        cases = [("paths=src/**", "paths=src/parser/**", True), ("paths=src/**", "paths=srcfoo/**", False),
                 ("paths=lnk/**", "paths=src/parser/a.py", True), ("paths=**", "paths=docs/x.md", True),
                 ("resource=build@src/build", "paths=src/**", True), ("resource=build", "resource=build", True),
                 ("resource=build", "resource=dev-server", False), ("paths=out/x/**", "paths=docs/**", True),
                 ("branch=main", "paths=src/**", False), ("branch=main", "branch=main", True),
                 ("branch=a", "branch=b", False), ("checkout", "resource=port:5173", True),
                 ("paths=SRC/**", "paths=src/parser/**", case_insensitive(o))]
        for x, y, want in cases:
            if overlap(parse_scope(x), parse_scope(y), o) != want:
                fail(f"overlap({x}, {y}) should be {want}")
        for bad in ["paths=../x", "paths=/etc", "paths=a//b", "paths=a\\b", "paths=./a", "resource=x@../y", "branch=a..b",
                    "nothing"]:
            refused_usage(f"scope {bad!r}", lambda: parse_scope(bad))

        # ---- session boundaries on synthetic hierarchies: no process name is consulted
        ide = {100: (1, "??", "ide"), 101: (100, "pts/1", "shell"), 102: (101, "pts/1", "agent-a"),
               103: (102, "pts/1", "sh -c x"), 104: (103, "pts/1", "python tool"), 110: (100, "pts/2", "shell"),
               111: (110, "pts/2", "agent-b")}
        tmux = {200: (1, "??", "server"), 201: (200, "pts/3", "shell"), 202: (201, "pts/3", "agent-a"),
                203: (202, "pts/3", "zsh -c x"), 204: (203, "pts/3", "python tool"), 210: (200, "pts/4", "shell"),
                211: (210, "pts/4", "agent-b")}
        siblings = {300: (1, "pts/5", "shell"), 301: (300, "pts/5", "agent-a"), 302: (301, "pts/5", "bash -lc x"),
                    303: (302, "pts/5", "python tool"), 310: (300, "pts/5", "agent-b")}
        desktop = {400: (1, "??", "app"), 401: (400, "??", "launcher"), 402: (401, "??", "agent"),
                   403: (402, "??", "zsh -c x"), 404: (403, "??", "python tool"), 405: (402, "??", "helper"),
                   409: (400, "??", "terminal service"), 410: (409, "ttys004", "zsh -l")}
        hosting = {**ide, 105: (102, "pts/9", "pty child")}
        sibling_claim = [{"holder": {"pid": 310}}]
        for label, table, start, claims, auto, broad in [("IDE", ide, 104, (), 102, 100),
                                                         ("terminal multiplexer", tmux, 204, (), 202, 200),
                                                         ("sibling agents", siblings, 303, sibling_claim, 301, 300),
                                                         ("desktop app", desktop, 404, (), 402, 400),
                                                         ("agent hosting a terminal", hosting, 104, (), None, 102)]:
            if resolve_holder(None, table, claims, start=start) != auto:
                fail(f"{label}: automatic holder should be {auto}, got {resolve_holder(None, table, claims, start=start)}")
            refused_usage(f"{label}: broad override {broad}",
                          lambda: resolve_holder(broad, table, claims, start=start))
        if resolve_holder(101, ide, start=104) != 101:
            fail("IDE: the agent's own terminal shell, hosting only this session, should be a valid override")
        refused_usage("override with a process that is not an ancestor", lambda: resolve_holder(111, ide, start=104))
        refused_usage("real override with a process that is not an ancestor",
                      lambda: acquire(root, checkout, intent="x", holder_pid=holder))
        table = process_table()
        chosen = resolve_holder(None, table)
        if chosen is not None and chosen not in ancestry(me, table):
            fail("the default holder is not an ancestor")
        for line, want in [("zsh -c source x", True), ("/bin/bash -lc make", True), ("sh -c true", True),
                           ("/usr/bin/env python3 x", True), ("zsh -l", False), ("claude --verbose", False),
                           ("bash", False)]:
            if bool(WRAPPER.match(line)) != want:
                fail(f"wrapper detection for {line!r} should be {want}")
        # A real shared ancestor: this process starts two agents that each hold a claim.
        sh = repo("shared-ancestor")
        first, second = (agent(sh, "acquire", child=True, scope=f"paths={p}/**") for p in ("src", "docs"))
        if reply(first)["status"] != "granted" or reply(second)["status"] != "granted":
            fail("shared ancestor: the two child agents did not get their claims")
        refused_usage("a real shared ancestor as an explicit holder",
                      lambda: acquire(sh, parse_scope("paths=x/**"), intent="x", holder_pid=me))
        refused_usage("a real shared ancestor as an explicit holder of a check",
                      lambda: activity_check(sh, holder_pid=me))
        sh_claims = Registry(sh).read()[0]
        if resolve_holder(None, process_table(), sh_claims, start=first[1]) is not None:
            fail("shared ancestor: automatic resolution from a child agent chose the shared parent")
        end_agents()

        # ---- activity checks
        idle = repo("idle")
        r = activity_check(idle, holder_pid=me)
        partial_env = r["verdict"] == "unknown" and all(e.startswith("process visibility: partial")
                                                        for e in r["evidence"])

        def expect_idle(label: str, res: dict, fragment: str = "") -> None:
            if not partial_env:
                expect(label, res, "idle", fragment)
            elif res["verdict"] != "unknown" or fragment not in json.dumps(res) or not all(
                    e.startswith(("process visibility: partial", "accepted passive", "1 matching processes"))
                    or "uncommitted" in e for e in res["evidence"]):
                fail(f"{label} (partial-visibility machine): expected unknown with only partial-visibility evidence, "
                     f"got {json.dumps(res)[:300]}")
        expect_idle("ordinary isolated checkout", r)
        if (idle / STATE).exists():
            fail("the read-only activity check created a registry")
        (idle / "draft.txt").write_text("work in progress")
        before = tree_digest(idle)
        activity_check(idle, holder_pid=me)
        activity_check(idle, holder_pid=me, disruptive=True)
        if tree_digest(idle) != before:
            fail("a read-only check changed the fixture tree (index or files)")
        expect_idle("dirty tree, ordinary check", activity_check(idle, holder_pid=me), "uncommitted")
        (idle / "draft.txt").unlink()
        expect("disruptive check without a claim", activity_check(idle, holder_pid=me, disruptive=True), "busy",
               "need this session's exclusive claim")
        shared = acquire(idle, checkout, mode="shared", intent="read", holder_pid=me)
        expect("disruptive check with only a shared claim", activity_check(idle, session=shared["session"],
                                                                           holder_pid=me, disruptive=True), "busy",
               "shared claims never authorize writes")
        release(idle, shared["claim"]["id"], shared["session"], holder_pid=me)
        mine = acquire(idle, checkout, intent="switch branches", holder_pid=me)
        session = mine["session"]
        expect_idle("disruptive check with this session's exclusive claim",
                    activity_check(idle, session=session, holder_pid=me, disruptive=True))
        git_dir = idle / ".git"
        for name in GIT_IN_PROGRESS:
            marker = git_dir / name
            marker.mkdir() if name.startswith("rebase") else marker.write_text("x")
            expect(f"git {name}", activity_check(idle, session=session, holder_pid=me), "busy", name)
            marker.rmdir() if name.startswith("rebase") else marker.unlink()
        (idle / "new.txt").write_text("work in progress")
        expect("dirty tree, disruptive check", activity_check(idle, session=session, holder_pid=me, disruptive=True),
               "busy", "preserve or attribute")
        (idle / "new.txt").unlink()
        served = idle / "src" / "parser" / "a.py"
        own = subprocess.Popen(["tail", "-f", str(served)], cwd=base, stdout=subprocess.DEVNULL)
        children.append(own)
        time.sleep(0.5)
        expect_idle("own session's process holding a file", activity_check(idle, session=session, holder_pid=me))
        own.kill()
        own.wait()
        server = orphan(f"tail -f '{served}'", base)
        time.sleep(0.4)
        expect("another agent's dev server holding a file, working directory elsewhere",
               activity_check(idle, holder_pid=me), "busy", f"active: process {server}")
        kill(server)
        # Passive (working directory only, no children) versus active.
        shell = orphan("sleep 300", idle)
        time.sleep(0.3)
        r = activity_check(idle, session=session, holder_pid=me, disruptive=True)
        line = next((e for e in r["evidence"] if e.startswith(f"passive: process {shell} ")), "")
        expect("a passive process is reported separately", r, "busy", f"passive: process {shell}")
        ident = line.rsplit("identity ", 1)[-1] if line else "?"
        expect_idle("an owner-accepted passive process, reversible operation",
                    activity_check(idle, session=session, holder_pid=me, disruptive=True, accept_passive=[ident]),
                    "accepted passive")
        expect("an acceptance never unblocks a destructive operation",
               activity_check(idle, session=session, holder_pid=me, destructive=True, accept_passive=[ident]), "busy",
               "never applies to a destructive operation")
        expect("an acceptance pinned to another identity is not applied",
               activity_check(idle, session=session, holder_pid=me, disruptive=True,
                              accept_passive=[f"{shell}:0000000000000000"]), "busy", "matches no passive process")
        (git_dir / "index.lock").write_text("x")
        expect("an acceptance never hides a git operation in progress",
               activity_check(idle, session=session, holder_pid=me, disruptive=True, accept_passive=[ident]), "busy",
               "index.lock")
        (git_dir / "index.lock").unlink()
        (idle / "new.txt").write_text("x")
        expect("an acceptance never hides uncommitted work",
               activity_check(idle, session=session, holder_pid=me, disruptive=True, accept_passive=[ident]), "busy",
               "preserve or attribute")
        (idle / "new.txt").unlink()
        expect("an acceptance never stands in for this session's claim",
               activity_check(idle, holder_pid=me, disruptive=True, accept_passive=[ident]), "busy",
               "exclusive claim")
        kill(shell)
        busy_shell = orphan("sh -c 'sleep 300; true'", idle)
        time.sleep(0.3)
        nested = descendants(busy_shell, process_table())
        for pid in nested:
            orphans[pid] = process_start(pid)
        expect("a process with children is active", activity_check(idle, session=session, holder_pid=me), "busy",
               f"active: process {busy_shell}")
        for pid in [busy_shell, *nested]:
            kill(pid)
        # More than ten matching processes: the verdict uses all of them; the display says what it omits.
        tails = []
        for i in range(12):
            f = idle / "docs" / f"f{i}.txt"
            f.write_text("x")
            tails.append(orphan(f"tail -f '{f}'", base))
        time.sleep(0.5)
        r = activity_check(idle, session=session, holder_pid=me)
        expect("twelve matching processes", r, "busy", "12 matching processes (12 active")
        expect("the omitted count is reported", r, "busy", "2 more not shown")
        full = activity_check(idle, session=session, holder_pid=me, show_all=True)
        if sum(1 for e in full["evidence"] if e.startswith("active: process")) != 12:
            fail(f"--all did not list every matching process: {full['evidence']}")
        for pid in tails:
            kill(pid)
        release(idle, mine["claim"]["id"], session, holder_pid=me)
        # Claims from another agent, partial visibility, missing capabilities.
        fixture_claim(idle, checkout, pid=holder)
        expect("another agent's live claim", activity_check(idle, holder_pid=me), "busy", "live")
        clear(idle)
        fake = base / "fake-lsof"
        fake.write_text("#!/bin/sh\necho p1\necho fcwd\necho n/\n")
        fake.chmod(0o755)
        expect("partial process visibility", activity_check(idle, holder_pid=me, lsof=str(fake)), "unknown", "partial")
        expect("process inspection unavailable", activity_check(idle, holder_pid=me, lsof="lsof-not-installed"),
               "unknown", "failed")
        module = sys.modules[__name__]
        saved_pin = module.load_path_in_use

        def one_target_partial():
            pin = saved_pin()
            real = pin.classify

            def classify(target, *a, **k):
                v, vis, m = real(target, *a, **k)
                return (pin.UNKNOWN, "partial (simulated for one target)", m) if target.endswith("docs") else (v, vis, m)
            pin.classify = classify
            return pin
        module.load_path_in_use = one_target_partial
        try:
            r = activity_check(idle, parse_scope("paths=src/**,docs/**"), holder_pid=me)
            expect("two targets, one with partial visibility", r, "unknown", "partial (simulated for one target)")
            if r["visibility"] != "partial (simulated for one target)":
                fail(f"the reported visibility is not the worst of the targets: {r['visibility']}")
        finally:
            module.load_path_in_use = saved_pin
        saved_resolve = module.resolve_holder
        module.resolve_holder = lambda *a, **k: None
        try:
            expect("acquire without an established holder", acquire(idle, checkout, intent="x"), "unknown",
                   "cannot be established")
            expect("disruptive check without an established holder", activity_check(idle, disruptive=True), "busy",
                   "exclusive claim")
        finally:
            module.resolve_holder = saved_resolve
        caps = repo("capabilities")
        for label, attr, value, fragment in [("no fcntl", "fcntl", None, "unavailable"),
                                             ("network filesystem", "filesystem_type", lambda p: "nfs", "network"),
                                             ("unidentified filesystem", "filesystem_type", lambda p: None,
                                              "could not be identified"),
                                             ("inside a container", "in_container", lambda: True, "container")]:
            saved = getattr(module, attr)
            setattr(module, attr, value)
            try:
                r = activity_check(caps, holder_pid=me)
                expect(f"read-only check: {label}", r, "unknown", fragment)
                if not r["coordination"].startswith("unavailable"):
                    fail(f"read-only check: {label}: coordination availability not reported: {r['coordination']}")
                expect(f"acquire: {label}", acquire(caps, checkout, intent="x", holder_pid=me), "unknown", fragment)
            finally:
                setattr(module, attr, saved)
        if (caps / STATE).exists():
            fail("a refused acquisition created a registry")
    except TimeoutError as e:
        fail(str(e))
    except Exception as e:  # noqa: BLE001 - an unexpected state is a failure, reported rather than raised
        fail(f"unexpected {type(e).__name__}: {e}")
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
        stop.touch()
        for c in children:
            if c.poll() is None:
                c.kill()
            c.wait()
        for pid in list(orphans):
            kill(pid)
        shutil.rmtree(base, ignore_errors=True)
    if not pycache_before and (HERE / "__pycache__").exists():
        failures.append("running the tool wrote bytecode into the skill's scripts directory")
    return failures


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
