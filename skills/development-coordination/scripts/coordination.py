#!/usr/bin/env python3
"""Coordinate cooperating coding agents in one shared git checkout: claims and activity checks.

    coordination.py acquire --scope SCOPE --intent TEXT [--mode exclusive|shared] [--ttl MINUTES]
                            [--session TOKEN] [--holder-pid PID] [--agent NAME] [--repo DIR]
    coordination.py renew   --id ID --session TOKEN [--ttl MINUTES] [--repo DIR]
    coordination.py release --id ID --session TOKEN [--repo DIR]
    coordination.py status  [--repo DIR]
    coordination.py check   [--scope SCOPE] [--session TOKEN] [--disruptive] [--holder-pid PID] [--repo DIR]
    coordination.py archive-stale [--repo DIR]
    coordination.py --self-test

SCOPE is `checkout`, `branch=NAME`, `paths=GLOB[,GLOB...]` or `resource=ID[@PATH]`, relative to the checkout root.
Exit status: 0 granted, idle or done; 1 conflict or busy; 2 unknown, unavailable or error.

What this enforces, and what it does not:
- Every change to the registry (`<checkout>/.agent-state/claims/`) happens inside one critical section: an exclusive
  advisory `fcntl.flock` on `.agent-state/claims.lock`, taken non-blocking with a bounded retry and held only for the
  check-and-publish. The lock file is never deleted or replaced. Two cooperating agents therefore never both acquire
  overlapping scopes. Claims bind only agents that use this tool: the registry is coordination, not a security
  boundary, and session tokens guard against accidents, not against a hostile process of the same user.
- A claim is archived as stale only when it has expired and its holder is established to be dead (PID gone, PID
  reused, or the host rebooted). An expired claim whose holder runs is a conflict; a holder that cannot be verified is
  unknown, and unknown is a conflict.
- Anything the tool cannot inspect (a malformed record, a symlinked registry path, a registry git would track, a lock
  that stays busy, no `fcntl`, a network filesystem, an unreadable process table) yields "unknown": never a grant,
  never "idle".
- The activity check reuses `path_in_use.py` (a generated copy of `workspace-housekeeping`'s), so it sees working
  directories and open files of every readable process, and reports partial visibility as unknown. It excludes only
  this session's own processes: the holder process found through ancestry and its descendants. It never excludes a
  process because of its name.
Standard library only; macOS and Linux. On Windows, claims are unavailable and the result is unknown.
"""

from __future__ import annotations

import argparse
import datetime
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

try:
    import fcntl
except ImportError:                                   # Windows: claims are unavailable, never faked
    fcntl = None

STATE = ".agent-state"
CLAIM_ID = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{8}$")
TMP_PREFIX = ".tmp-"
MAX_CLAIM_BYTES = 65536
GLOB_CHARS = set("*?[")
WRAPPER = re.compile(r"^(?:\S*/)?(?:(?:sh|bash|zsh|dash|ksh|fish)\s+-[A-Za-z]*c\b|env(?:\s|$))")
NETWORK_FS = {"nfs", "nfs4", "cifs", "smbfs", "smb3", "afpfs", "webdav", "fuse.sshfs", "sshfs", "9p", "ncpfs",
              "glusterfs", "ceph", "lustre", "fuse.rclone", "davfs"}
GIT_IN_PROGRESS = {"index.lock": "a git command holds the index lock", "MERGE_HEAD": "a merge is in progress",
                   "CHERRY_PICK_HEAD": "a cherry-pick is in progress", "REVERT_HEAD": "a revert is in progress",
                   "BISECT_LOG": "a bisect is in progress", "rebase-merge": "a rebase is in progress",
                   "rebase-apply": "a rebase or am is in progress"}
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
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=60)


def checkout_root(repo) -> Path:
    try:
        r = git(Path(repo), "rev-parse", "--show-toplevel")
    except (OSError, subprocess.SubprocessError) as e:
        raise Unknown(f"git is not available: {e}")
    if r.returncode != 0 or not r.stdout.strip():
        raise Usage(f"{repo} is not inside a git checkout")
    return Path(r.stdout.strip()).resolve()


# ------------------------------------------------------------------------------------- processes and identity

def process_table() -> dict[int, tuple[int, str]]:
    """{pid: (ppid, command)} for every process."""
    try:
        r = subprocess.run(["ps", "-A", "-o", "pid=,ppid=,command="], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        raise Unknown(f"the process table cannot be read: {e}")
    table = {}
    for line in r.stdout.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            table[int(parts[0])] = (int(parts[1]), parts[2] if len(parts) > 2 else "")
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
    for child, (parent, _) in table.items():
        children.setdefault(parent, []).append(child)
    out, todo = set(), [pid]
    while todo:
        for child in children.get(todo.pop(), []):
            if child not in out:
                out.add(child)
                todo.append(child)
    return out


def resolve_holder(explicit: int | None, table: dict) -> int | None:
    """The long-lived process that represents this session: the nearest ancestor of this process that is not a
    `sh -c`-style wrapper shell. An explicit PID must be this process or one of its ancestors."""
    chain = ancestry(os.getpid(), table)
    if explicit is not None:
        if explicit not in chain:
            raise Usage(f"--holder-pid {explicit} is not this process or one of its ancestors")
        return explicit
    for pid in chain[1:]:
        if not WRAPPER.match(table[pid][1]):
            return pid
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
    """Resolved path prefixes of a scope (symlinks and aliases followed), or None when they cannot be resolved inside
    the checkout. None means overlap cannot be determined, which counts as a conflict."""
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
    """Whether the checkout's filesystem folds case (macOS and Windows defaults): probed through `.git`."""
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

    def key(path: Path) -> PurePosixPath:                 # aliases by case or Unicode form compare equal
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
    p = []
    if data.get("kind") != "claim" or type(data.get("version")) is not int or data.get("version") != 1:
        return [f"{where}: not a version 1 claim"]
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
                                                                 or not isinstance(start, str))):
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
        r = git(self.root, "check-ignore", "-q", f"{STATE}/claims/probe.json")
        if r.returncode != 0:
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

    def read(self) -> tuple[list[dict], list[str], list[str]]:
        """(claims, leftover temporary files, problems). Any problem means the registry cannot be inspected."""
        claims, leftovers, problems = [], [], []
        for entry in sorted(os.scandir(self.claims), key=lambda e: e.name):
            name = entry.name
            if name == "stale" and entry.is_dir(follow_symlinks=False):
                continue
            if name.startswith(TMP_PREFIX) and entry.is_file(follow_symlinks=False):
                leftovers.append(name)
                continue
            stem = name[:-5] if name.endswith(".json") else ""
            if not CLAIM_ID.match(stem):
                problems.append(f"unexpected entry {name!r} in the registry")
                continue
            if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
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
        return claims, leftovers, problems

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


def blocking_state(claim: dict, state: str, now: datetime.datetime) -> str | None:
    """None when the claim is stale (expired AND holder dead); otherwise why it still blocks overlapping requests."""
    expired = parse_stamp(claim["expires"]) <= now
    if state == "dead":
        return None if expired else "holder-dead-unexpired"
    if state == "live":
        return "expired-held" if expired else "live"
    return "expired-unknown" if expired else "unknown"


def describe(claim: dict, state: str, reason: str) -> dict:
    return {"id": claim["id"], "state": state, "reason": reason, "scope": claim["scope"], "mode": claim["mode"],
            "intent": claim["intent"], "agent": claim["holder"]["agent"], "expires": claim["expires"]}


# ------------------------------------------------------------------------------------------------ operations

def _ttl(minutes) -> datetime.timedelta:
    if type(minutes) not in (int, float) or not 1 <= minutes <= 1440:
        raise Usage("--ttl must be between 1 and 1440 minutes")
    return datetime.timedelta(minutes=minutes)


def _registry(repo) -> tuple[Path, Registry]:
    root = checkout_root(repo)
    kind = filesystem_type(root)
    if kind in NETWORK_FS:
        raise Unknown(f"the checkout is on a network filesystem ({kind}): advisory claims are unreliable there")
    registry = Registry(root)
    registry.ensure()
    return root, registry


def acquire(repo, scope: dict, *, mode: str = "exclusive", intent: str, ttl_minutes=120, session: str | None = None,
            holder_pid: int | None = None, agent: str = "agent", lock_timeout: float = 10.0) -> dict:
    """Serialized conflict-check-and-acquire. Returns {"status": "granted"|"conflict"|"unknown", ...}."""
    if mode not in ("exclusive", "shared") or not intent:
        raise Usage("mode must be exclusive or shared, and intent is required")
    ttl = _ttl(ttl_minutes)
    try:
        root, registry = _registry(repo)
        table = process_table()
        holder = resolve_holder(holder_pid, table)
        start = process_start(holder) if holder else None
        local = here()
        with registry.locked(lock_timeout):
            claims, _, problems = registry.read()
            if problems:
                return {"status": "unknown", "reason": "the claim registry cannot be inspected: " + "; ".join(problems)}
            now, conflicts, archived = utcnow(), [], []
            for claim in claims:
                state, reason = holder_state(claim["holder"], local)
                blocks = blocking_state(claim, state, now)
                if blocks is None:
                    registry.archive(claim["id"])
                    archived.append(claim["id"])
                    continue
                own = session is not None and claim["holder"]["session"] == session and claim["holder"]["pid"] == holder
                if not own and conflicts_with(mode, claim["mode"]) and overlap(scope, claim["scope"], root):
                    conflicts.append(describe(claim, blocks, reason))
            if conflicts:
                return {"status": "conflict", "conflicts": conflicts, "archived": archived}
            token = session or secrets.token_hex(16)
            claim = {"kind": "claim", "version": 1, "id": now.strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4),
                     "holder": {"agent": agent, "session": token, "host": local["host"],
                                "pid": holder if start else None, "process_start": start if holder else None,
                                "boot": local["boot"]},
                     "scope": scope, "mode": mode, "intent": intent, "created": stamp(now), "expires": stamp(now + ttl)}
            registry.publish(claim)
            return {"status": "granted", "claim": claim, "session": token, "archived": archived}
    except Unknown as e:
        return {"status": "unknown", "reason": str(e)}


def _modify(repo, claim_id: str, session: str, lock_timeout: float, change) -> dict:
    if not CLAIM_ID.match(claim_id or ""):
        raise Usage(f"invalid claim id {claim_id!r}")
    try:
        _, registry = _registry(repo)
        with registry.locked(lock_timeout):
            claims, _, problems = registry.read()
            if problems:
                return {"status": "unknown", "reason": "the claim registry cannot be inspected: " + "; ".join(problems)}
            claim = next((c for c in claims if c["id"] == claim_id), None)
            if claim is None:
                return {"status": "missing", "reason": f"no active claim {claim_id}"}
            if not secrets.compare_digest(claim["holder"]["session"], session or ""):
                return {"status": "refused", "reason": "the session token does not match this claim"}
            return change(registry, claim)
    except Unknown as e:
        return {"status": "unknown", "reason": str(e)}


def renew(repo, claim_id: str, session: str, ttl_minutes=120, lock_timeout: float = 10.0) -> dict:
    ttl = _ttl(ttl_minutes)

    def change(registry, claim):
        claim["expires"] = stamp(utcnow() + ttl)
        registry.publish(claim)
        return {"status": "renewed", "claim": claim}
    return _modify(repo, claim_id, session, lock_timeout, change)


def release(repo, claim_id: str, session: str, lock_timeout: float = 10.0) -> dict:
    def change(registry, claim):
        (registry.claims / f"{claim['id']}.json").unlink()
        return {"status": "released", "id": claim["id"]}
    return _modify(repo, claim_id, session, lock_timeout, change)


def status(repo, lock_timeout: float = 10.0) -> dict:
    try:
        root = checkout_root(repo)
        registry = Registry(root)
        if not registry.exists():
            return {"status": "ok", "claims": [], "leftovers": []}
        with registry.locked(lock_timeout):
            claims, leftovers, problems = registry.read()
        if problems:
            return {"status": "unknown", "reason": "the claim registry cannot be inspected: " + "; ".join(problems)}
        local, now = here(), utcnow()
        rows = []
        for claim in claims:
            state, reason = holder_state(claim["holder"], local)
            rows.append(describe(claim, blocking_state(claim, state, now) or "stale", reason))
        return {"status": "ok", "claims": rows, "leftovers": leftovers}
    except Unknown as e:
        return {"status": "unknown", "reason": str(e)}


def archive_stale(repo, lock_timeout: float = 10.0) -> dict:
    try:
        _, registry = _registry(repo)
        with registry.locked(lock_timeout):
            claims, _, problems = registry.read()
            if problems:
                return {"status": "unknown", "reason": "the claim registry cannot be inspected: " + "; ".join(problems)}
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


def activity_check(repo, scope: dict | None = None, *, session: str | None = None, disruptive: bool = False,
                   holder_pid: int | None = None, lsof: str = "lsof") -> dict:
    """Read-only. {"verdict": "idle"|"busy"|"unknown", "visibility": ..., "evidence": [...], "excluded": [...]}"""
    scope = scope or {"type": "checkout", "value": "."}
    evidence, busy, unknown, visibility, excluded, holder_info = [], False, False, "not checked", [], None
    try:
        root = checkout_root(repo)
    except Unknown as e:
        return {"verdict": "unknown", "visibility": visibility, "evidence": [str(e)], "excluded": []}
    # Claims (read-only: claim files are published atomically).
    registry = Registry(root)
    try:
        if registry.exists():
            claims, _, problems = registry.read()
            if problems:
                unknown = True
                evidence.append("claim registry cannot be inspected: " + "; ".join(problems))
            local, now = here(), utcnow()
            for claim in claims if not problems else []:
                if session is not None and claim["holder"]["session"] == session:
                    continue
                state, reason = holder_state(claim["holder"], local)
                blocks = blocking_state(claim, state, now)
                if blocks and overlap(scope, claim["scope"], root):
                    if blocks in ("unknown", "expired-unknown"):
                        unknown = True
                    else:
                        busy = True
                    evidence.append(f"claim {claim['id']} ({claim['mode']} {claim['scope']['type']}, {blocks}: "
                                    f"{reason}): {claim['intent']}")
    except Unknown as e:
        unknown = True
        evidence.append(str(e))
    # Git operations in progress, and uncommitted work.
    r = git(root, "rev-parse", "--absolute-git-dir")
    if r.returncode != 0:
        unknown = True
        evidence.append("git state cannot be read")
    else:
        git_dir = Path(r.stdout.strip())
        for name, meaning in GIT_IN_PROGRESS.items():
            if (git_dir / name).exists():
                busy = True
                evidence.append(f"{meaning} ({name})")
        st = git(root, "status", "--porcelain=v1", "--untracked-files=normal")
        if st.returncode != 0:
            unknown = True
            evidence.append("git status failed")
        elif st.stdout.strip():
            count = len(st.stdout.strip().splitlines())
            evidence.append(f"{count} uncommitted or untracked paths" + (
                ": a disruptive operation would put them at risk; preserve or attribute them first" if disruptive else ""))
            busy = busy or disruptive
    # Processes: working directories and open files, through the reused in-use check.
    try:
        table = process_table()
        holder = resolve_holder(holder_pid, table)
        own = set(ancestry(os.getpid(), table))
        if holder is not None:
            own |= {holder} | descendants(holder, table)
            holder_info = f"pid {holder} ({table[holder][1][:80]})"
        excluded = sorted(own)
        pin = load_path_in_use()
        targets = [root] if scope["type"] in ("checkout", "branch") else (scope_paths(scope, root) or [root])
        procs = pin.list_processes()
        records, lsof_pid = pin.list_open_files(lsof)
        for target in targets:
            verdict, visibility, matches = pin.classify(str(target), os.stat(root).st_uid, procs, records,
                                                        own | {os.getpid(), lsof_pid})
            for pid, cmd, fd, name in matches[:10]:
                idle_hint = "" if any(parent == pid for parent, _ in table.values()) else " (no child processes)"
                evidence.append(f"process {pid} ({cmd}) {'works in' if fd == 'cwd' else 'has open'} {name}{idle_hint}")
            busy = busy or bool(matches)
            if verdict == pin.UNKNOWN:
                unknown = True
                evidence.append(f"process visibility: {visibility}")
    except (Unknown, OSError, RuntimeError, subprocess.SubprocessError) as e:
        unknown = True
        visibility = f"failed ({e})"
        evidence.append(f"process inspection failed: {e}")
    verdict = "busy" if busy else "unknown" if unknown else "idle"
    return {"verdict": verdict, "visibility": visibility, "evidence": evidence, "excluded": excluded,
            "holder": holder_info}


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
    for name in ("acquire", "renew", "release", "status", "check", "archive-stale"):
        p = sub.add_parser(name)
        p.add_argument("--repo", default=".")
        if name in ("acquire", "check"):
            p.add_argument("--scope", default="checkout")
            p.add_argument("--holder-pid", type=int)
            p.add_argument("--session")
        if name == "acquire":
            p.add_argument("--intent", required=True)
            p.add_argument("--mode", default="exclusive", choices=("exclusive", "shared"))
            p.add_argument("--agent", default=os.environ.get("CODING_AGENT", "agent"))
        if name in ("acquire", "renew"):
            p.add_argument("--ttl", type=float, default=120)
        if name in ("renew", "release"):
            p.add_argument("--id", required=True)
            p.add_argument("--session", required=True)
        if name == "check":
            p.add_argument("--disruptive", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "acquire":
            result = acquire(args.repo, parse_scope(args.scope), mode=args.mode, intent=args.intent, ttl_minutes=args.ttl,
                             session=args.session, holder_pid=args.holder_pid, agent=args.agent)
            print(json.dumps(result, indent=2))
            return {"granted": 0, "conflict": 1}.get(result["status"], 2)
        if args.command in ("renew", "release"):
            fn = renew if args.command == "renew" else release
            result = fn(args.repo, args.id, args.session, args.ttl) if args.command == "renew" else \
                fn(args.repo, args.id, args.session)
            print(json.dumps(result, indent=2))
            return 0 if result["status"] in ("renewed", "released") else 2
        if args.command == "status":
            result = status(args.repo)
            print(json.dumps(result, indent=2))
            return 0 if result["status"] == "ok" else 2
        if args.command == "archive-stale":
            result = archive_stale(args.repo)
            print(json.dumps(result, indent=2))
            return 0 if result["status"] == "done" else 2
        result = activity_check(args.repo, parse_scope(args.scope), session=args.session, disruptive=args.disruptive,
                                holder_pid=args.holder_pid)
        print(f"verdict: {result['verdict']}")
        print(f"visibility: {result['visibility']}")
        for line in result["evidence"]:
            print(f"evidence: {line}")
        print(f"session holder: {result['holder'] or 'not determined (only this command excluded)'}")
        print(f"excluded as this session's own processes: {len(result['excluded'])}")
        return {"idle": 0, "busy": 1}.get(result["verdict"], 2)
    except Usage as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


# ---------------------------------------------------------------------------------------------------------- self-test

RACER = r"""
import json, os, sys, time
sys.path.insert(0, sys.argv[1])
import coordination as c
repo, scope, mode, go, stop = sys.argv[2:7]
while not os.path.exists(go):
    time.sleep(0.002)
r = c.acquire(repo, c.parse_scope(scope), mode=mode, intent="race", ttl_minutes=30, holder_pid=os.getpid(),
              lock_timeout=30)
print(json.dumps({"status": r["status"]}), flush=True)
while not os.path.exists(stop):
    time.sleep(0.05)
"""

HOLD_LOCK = r"""
import os, sys, time
sys.path.insert(0, sys.argv[1])
import coordination as c
reg = c.Registry(c.checkout_root(sys.argv[2]))
reg.ensure()
with reg.locked(10):
    if sys.argv[3] == "publish":
        tmp = reg.claims / (c.TMP_PREFIX + "interrupted")
        tmp.write_text('{"kind": "claim", "version"')       # a partial claim, never renamed into place
    print("locked", flush=True)
    time.sleep(120)
"""


def self_test() -> list[str]:
    """Real processes and fixture repositories under one private directory. Explicit checks, so it runs under -O."""
    failures: list[str] = []
    if os.name != "posix" or fcntl is None:
        return ["this self-test needs a POSIX system with fcntl (macOS or Linux)"]
    for tool in ("git", "ps", "lsof"):
        if shutil.which(tool) is None:
            return [f"{tool} is required by this self-test"]
    base = Path(tempfile.mkdtemp(prefix="coordination-")).resolve()
    children: list[subprocess.Popen] = []
    orphans: list[int] = []
    env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="t",
               GIT_AUTHOR_EMAIL="t@example.invalid", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")

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

    def spawn(args, **kw) -> subprocess.Popen:
        children.append(subprocess.Popen(args, **kw))
        return children[-1]

    def sleeper() -> subprocess.Popen:
        return spawn(["sleep", "300"])

    def fixture_claim(root: Path, scope: dict, *, mode="exclusive", pid=None, start="auto", host=None, boot="auto",
                      expires_in=30, session="fixture-session") -> str:
        reg = Registry(root)
        reg.ensure()
        now = utcnow()
        cid = now.strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4)
        if start == "auto":
            start = process_start(pid) if pid else None
        created = now - datetime.timedelta(minutes=120)
        claim = {"kind": "claim", "version": 1, "id": cid,
                 "holder": {"agent": "other-agent", "session": session, "host": host or socket.gethostname(),
                            "pid": pid, "process_start": start, "boot": boot_id() if boot == "auto" else boot},
                 "scope": scope, "mode": mode, "intent": "fixture", "created": stamp(created),
                 "expires": stamp(now + datetime.timedelta(minutes=expires_in))}
        reg.publish(claim)
        return cid

    def clear(root: Path) -> None:
        for p in (root / STATE / "claims").glob("*"):
            if p.is_file():
                p.unlink()

    def expect(label: str, result: dict, want: str, fragment: str = "") -> None:
        text = json.dumps(result)
        if result.get("status", result.get("verdict")) != want or fragment not in text:
            fail(f"{label}: expected {want} {fragment!r}, got {text[:300]}")

    checkout = parse_scope("checkout")

    def watchdog(signum, frame):
        raise TimeoutError("the self-test took longer than 240 s: a child process is blocking")
    previous = signal.signal(signal.SIGALRM, watchdog)
    signal.alarm(240)
    try:
        # ---- races between real processes
        root = repo("race")                            # no registry yet: the racers also race to create it
        go, stop = base / "go", base / "stop"

        def race(scopes: list[tuple[str, str]]) -> list[str]:
            go.unlink(missing_ok=True)
            stop.unlink(missing_ok=True)
            racers = [spawn([sys.executable, "-c", RACER, str(HERE), str(root), s, m, str(go), str(stop)],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for s, m in scopes]
            time.sleep(0.5)
            go.touch()
            results = []
            for r in racers:
                line = r.stdout.readline()
                if line:
                    results.append(json.loads(line)["status"])
                else:
                    r.wait()
                    results.append("crashed: " + (r.stderr.read().strip().splitlines() or ["?"])[-1][:120])
            return results

        results = race([("checkout", "exclusive")] * 8)
        live = sorted((root / STATE / "claims").glob("*.json"))
        if results.count("granted") != 1 or results.count("conflict") != 7 or len(live) != 1:
            fail(f"8 simultaneous overlapping requests: {results}, {len(live)} claims")
        stop.touch()
        time.sleep(0.2)
        clear(root)
        results = race([(f"paths=area{i}/**", "exclusive") for i in range(6)])
        if results != ["granted"] * 6:
            fail(f"6 simultaneous non-overlapping requests: {results}")
        stop.touch()
        time.sleep(0.2)
        clear(root)

        # ---- registry created concurrently: another agent's mkdir wins between our check and our mkdir
        racing = repo("mkdir-race")
        original_mkdir = Path.mkdir

        def mkdir_after_another_agent(self, *args, **kwargs):
            original_mkdir(self, *args, **{**kwargs, "exist_ok": True})     # the other agent creates it first
            return original_mkdir(self, *args, **kwargs)                     # ours then raises FileExistsError
        Path.mkdir = mkdir_after_another_agent
        try:
            expect("registry created concurrently by another agent",
                   acquire(racing, checkout, intent="x", holder_pid=os.getpid()), "granted")
        finally:
            Path.mkdir = original_mkdir

        # ---- shared and exclusive
        holder = sleeper()
        time.sleep(0.1)
        fixture_claim(root, parse_scope("paths=docs/**"), mode="shared", pid=holder.pid)
        expect("shared beside shared", acquire(root, parse_scope("paths=docs/**"), mode="shared", intent="read docs",
                                               holder_pid=os.getpid()), "granted")
        expect("exclusive beside shared", acquire(root, parse_scope("paths=docs/x/**"), intent="edit docs",
                                                  holder_pid=os.getpid()), "conflict", '"state": "live"')
        clear(root)
        fixture_claim(root, checkout, pid=holder.pid)
        expect("shared beside exclusive checkout", acquire(root, parse_scope("paths=docs/**"), mode="shared",
                                                           intent="read", holder_pid=os.getpid()), "conflict")
        clear(root)

        # ---- branch ownership is not working-tree ownership
        fixture_claim(root, parse_scope("branch=feature"), pid=holder.pid)
        expect("paths beside another agent's branch claim", acquire(root, parse_scope("paths=src/**"), intent="edit",
                                                                    holder_pid=os.getpid()), "granted")
        clear(root)
        fixture_claim(root, parse_scope("branch=feature"), pid=holder.pid)
        expect("checkout beside a branch claim", acquire(root, checkout, intent="switch", holder_pid=os.getpid()),
               "conflict")
        expect("same branch twice", acquire(root, parse_scope("branch=feature"), intent="push",
                                            holder_pid=os.getpid()), "conflict")
        clear(root)

        # ---- lifetime: expired-but-running, PID reuse, unknown identity, another host, reboot
        fixture_claim(root, checkout, pid=holder.pid, expires_in=-5)
        expect("expired claim whose holder runs", acquire(root, checkout, intent="x", holder_pid=os.getpid()),
               "conflict", "expired-held")
        clear(root)
        fixture_claim(root, checkout, pid=holder.pid, start="lstart:Thu Jan  1 00:00:00 1970")
        expect("reused PID, not expired", acquire(root, checkout, intent="x", holder_pid=os.getpid()), "conflict",
               "holder-dead-unexpired")
        clear(root)
        cid = fixture_claim(root, checkout, pid=holder.pid, start="lstart:Thu Jan  1 00:00:00 1970", expires_in=-5)
        result = acquire(root, checkout, intent="x", holder_pid=os.getpid())
        expect("reused PID and expired: archived as stale", result, "granted")
        if cid not in result.get("archived", []) or not (root / STATE / "claims" / "stale" / f"{cid}.json").exists():
            fail(f"stale claim not archived: {result}")
        clear(root)
        gone = spawn(["true"])
        gone.wait()
        fixture_claim(root, checkout, pid=gone.pid, start="lstart:x", expires_in=-5)
        expect("holder gone and expired", acquire(root, checkout, intent="x", holder_pid=os.getpid()), "granted")
        clear(root)
        fixture_claim(root, checkout, pid=None, start=None, expires_in=-5)
        expect("holder identity not recorded", acquire(root, checkout, intent="x", holder_pid=os.getpid()),
               "conflict", "expired-unknown")
        clear(root)
        fixture_claim(root, checkout, pid=holder.pid, host="another-machine.example", expires_in=-60)
        expect("claim from another machine", acquire(root, checkout, intent="x", holder_pid=os.getpid()), "conflict",
               "another host")
        clear(root)
        fixture_claim(root, checkout, pid=holder.pid, boot="previous-boot", expires_in=-5)
        expect("holder from before a reboot, expired", acquire(root, checkout, intent="x", holder_pid=os.getpid()),
               "granted")
        clear(root)

        # ---- registry lock: timeout, death inside the critical section, interrupted publication
        locker = spawn([sys.executable, "-c", HOLD_LOCK, str(HERE), str(root), "plain"], stdout=subprocess.PIPE,
                       text=True)
        locker.stdout.readline()
        t0 = time.monotonic()
        expect("registry lock held elsewhere", acquire(root, checkout, intent="x", holder_pid=os.getpid(),
                                                       lock_timeout=0.5), "unknown", "stayed locked")
        if not 0.4 < time.monotonic() - t0 < 5:
            fail(f"lock timeout took {time.monotonic() - t0:.2f}s")
        locker.send_signal(signal.SIGKILL)
        locker.wait()
        t0 = time.monotonic()
        result = acquire(root, checkout, intent="after a crash", holder_pid=os.getpid(), lock_timeout=5)
        expect("lock after its holder was killed inside the critical section", result, "granted")
        if time.monotonic() - t0 > 2:
            fail("the lock of a killed process was not released promptly")
        release(root, result["claim"]["id"], result["session"])
        lock_inode = os.stat(root / STATE / "claims.lock").st_ino
        writer = spawn([sys.executable, "-c", HOLD_LOCK, str(HERE), str(root), "publish"], stdout=subprocess.PIPE,
                       text=True)
        writer.stdout.readline()
        writer.send_signal(signal.SIGKILL)
        writer.wait()
        result = acquire(root, checkout, intent="after an interrupted publication", holder_pid=os.getpid())
        expect("acquire after an interrupted publication", result, "granted")
        st = status(root)
        if st.get("leftovers") != [TMP_PREFIX + "interrupted"] or len(st.get("claims", [])) != 1:
            fail(f"interrupted publication: {st}")
        if os.stat(root / STATE / "claims.lock").st_ino != lock_inode:
            fail("the registry lock file was replaced")
        release(root, result["claim"]["id"], result["session"])

        # ---- concurrent renewal and release
        result = acquire(root, checkout, intent="renew race", holder_pid=os.getpid())
        cid, token = result["claim"]["id"], result["session"]
        code = ("import json, sys, time; sys.path.insert(0, sys.argv[1]); import coordination as c\n"
                "print('started', flush=True)\nout = []\n"
                "for _ in range(40):\n    out.append(c.renew(sys.argv[2], sys.argv[3], sys.argv[4], 30)['status'])\n"
                "    time.sleep(0.01)\nprint(json.dumps(out), flush=True)")
        renewer = spawn([sys.executable, "-c", code, str(HERE), str(root), cid, token], stdout=subprocess.PIPE, text=True)
        renewer.stdout.readline()
        time.sleep(0.3)                                   # some renewals land before the release
        rel = release(root, cid, token)
        renewed = json.loads(renewer.stdout.readline() or "[]")
        renewer.wait()
        if rel["status"] != "released" or (root / STATE / "claims" / f"{cid}.json").exists():
            fail(f"release during renewals: {rel}")
        if "renewed" not in renewed or "missing" not in renewed:
            fail(f"the renew/release race did not interleave: {renewed}")
        elif "renewed" in renewed[renewed.index("missing"):]:
            fail(f"a claim was renewed after its release: {renewed}")
        if any(p.name.startswith(TMP_PREFIX) and "interrupted" not in p.name for p in (root / STATE / "claims").iterdir()):
            fail("renewal left a temporary file behind")
        expect("renewal of a released claim", renew(root, cid, token), "missing")
        result = acquire(root, checkout, intent="x", holder_pid=os.getpid())
        expect("renewal of a live claim with a wrong token", renew(root, result["claim"]["id"], "not-the-token"),
               "refused")
        expect("release of a live claim with a wrong token", release(root, result["claim"]["id"], "not-the-token"),
               "refused")
        release(root, result["claim"]["id"], result["session"])
        clear(root)

        # ---- malformed and unsafe registries are never silently passed
        claims_dir = root / STATE / "claims"
        for label, name, content in [("garbage", "20260101T000000Z-0000aaaa.json", "{not json"),
                                     ("duplicate keys", "20260101T000000Z-0000aaab.json",
                                      '{"kind": "claim", "kind": "claim"}'),
                                     ("wrong types", "20260101T000000Z-0000aaac.json",
                                      json.dumps({"kind": "claim", "version": 1, "id": "20260101T000000Z-0000aaac"})),
                                     ("unexpected file", "notes.txt", "hello")]:
            (claims_dir / name).write_text(content)
            expect(f"malformed registry ({label})", acquire(root, checkout, intent="x", holder_pid=os.getpid()),
                   "unknown", "cannot be inspected")
            expect(f"activity check with a malformed registry ({label})", activity_check(root, holder_pid=os.getpid()),
                   "unknown")
            (claims_dir / name).unlink()
        (claims_dir / "20260101T000000Z-0000aaad.json").symlink_to(base / "elsewhere.json")
        expect("symlinked claim", acquire(root, checkout, intent="x", holder_pid=os.getpid()), "unknown",
               "not a regular file")
        (claims_dir / "20260101T000000Z-0000aaad.json").unlink()
        unsafe = repo("unsafe")
        (base / "outside-state").mkdir()
        (unsafe / STATE).symlink_to(base / "outside-state", target_is_directory=True)
        expect("symlinked registry directory", acquire(unsafe, checkout, intent="x", holder_pid=os.getpid()),
               "unknown", "unsafe registry location")
        tracked = repo("tracked")
        (tracked / STATE).mkdir()
        (tracked / STATE / ".gitignore").write_text("# ignores nothing\n")
        expect("registry git would track", acquire(tracked, checkout, intent="x", holder_pid=os.getpid()), "unknown",
               "would track")

        # ---- overlap semantics: parents, children, aliases, canonical paths
        o = repo("overlap")
        (o / "lnk").symlink_to(o / "src", target_is_directory=True)
        (o / "out").symlink_to(base, target_is_directory=True)
        cases = [("paths=src/**", "paths=src/parser/**", True), ("paths=src/**", "paths=srcfoo/**", False),
                 ("paths=lnk/**", "paths=src/parser/a.py", True), ("paths=**", "paths=docs/x.md", True),
                 ("resource=build@src/build", "paths=src/**", True), ("resource=build", "resource=build", True),
                 ("resource=build", "resource=dev-server", False), ("paths=out/x/**", "paths=docs/**", True),
                 ("branch=main", "paths=src/**", False), ("branch=main", "branch=main", True),
                 ("branch=a", "branch=b", False), ("checkout", "resource=port:5173", True)]
        cases.append(("paths=SRC/**", "paths=src/parser/**", case_insensitive(o)))   # same directory only if case folds
        for a, b, want in cases:
            if overlap(parse_scope(a), parse_scope(b), o) != want:
                fail(f"overlap({a}, {b}) should be {want}")
        for bad in ["paths=../x", "paths=/etc", "paths=a//b", "paths=a\\b", "paths=./a", "resource=x@../y", "branch=a..b",
                    "nothing"]:
            try:
                parse_scope(bad)
                fail(f"scope {bad!r} was accepted")
            except Usage:
                pass

        # ---- activity checks
        idle = repo("idle")
        result = activity_check(idle, holder_pid=os.getpid())
        expect("ordinary isolated checkout", result, "idle")
        if (idle / STATE).exists():
            fail("the read-only activity check created a registry")
        git_dir = idle / ".git"
        for name in GIT_IN_PROGRESS:
            marker = git_dir / name
            marker.mkdir() if name.startswith("rebase") else marker.write_text("x")
            expect(f"git {name}", activity_check(idle, holder_pid=os.getpid()), "busy", name)
            marker.rmdir() if name.startswith("rebase") else marker.unlink()
        (idle / "new.txt").write_text("work in progress")
        expect("dirty tree, ordinary check", activity_check(idle, holder_pid=os.getpid()), "idle", "uncommitted")
        expect("dirty tree, disruptive check", activity_check(idle, holder_pid=os.getpid(), disruptive=True), "busy",
               "preserve or attribute")
        (idle / "new.txt").unlink()
        served = idle / "src" / "parser" / "a.py"
        own = spawn(["tail", "-f", str(served)], cwd=base, stdout=subprocess.DEVNULL)
        time.sleep(0.5)
        expect("own session's process holding a file", activity_check(idle, holder_pid=os.getpid()), "idle")
        own.kill()
        own.wait()
        out = subprocess.run(["sh", "-c", 'tail -f "$1" </dev/null >/dev/null 2>&1 & echo $!', "sh", str(served)],
                             cwd=base, capture_output=True, text=True, timeout=30)
        orphans.append(int(out.stdout.strip()))
        time.sleep(0.5)
        expect("another agent's dev server holding a file, working directory elsewhere",
               activity_check(idle, holder_pid=os.getpid()), "busy", f"process {orphans[-1]}")
        os.kill(orphans.pop(), signal.SIGKILL)
        fixture_claim(idle, checkout, pid=holder.pid)
        expect("another agent's live claim", activity_check(idle, holder_pid=os.getpid()), "busy", "live")
        clear(idle)
        fake = base / "fake-lsof"
        fake.write_text("#!/bin/sh\necho p1\necho fcwd\necho n/\n")
        fake.chmod(0o755)
        expect("partial process visibility", activity_check(idle, holder_pid=os.getpid(), lsof=str(fake)), "unknown",
               "partial")
        expect("process inspection unavailable", activity_check(idle, holder_pid=os.getpid(), lsof="lsof-not-installed"),
               "unknown", "failed")

        # ---- unsupported locking; holder identity rules
        module = sys.modules[__name__]
        saved, module.fcntl = module.fcntl, None
        try:
            expect("no fcntl", acquire(root, checkout, intent="x", holder_pid=os.getpid()), "unknown", "unavailable")
        finally:
            module.fcntl = saved
        saved_fs, module.filesystem_type = module.filesystem_type, lambda path: "nfs"
        try:
            expect("network filesystem", acquire(root, checkout, intent="x", holder_pid=os.getpid()), "unknown",
                   "network filesystem")
        finally:
            module.filesystem_type = saved_fs
        try:
            acquire(root, checkout, intent="x", holder_pid=holder.pid)
            fail("a holder PID that is not an ancestor was accepted")
        except Usage:
            pass
        table = process_table()
        if resolve_holder(None, table) not in ancestry(os.getpid(), table):
            fail("the default holder is not an ancestor")
        wrapped = spawn(["sh", "-c", f"{sys.executable} -c \"import sys; sys.path.insert(0, '{HERE}'); "
                                     f"import coordination as c, os; print(c.resolve_holder(None, c.process_table()))\""],
                        stdout=subprocess.PIPE, text=True)
        reported = wrapped.stdout.readline().strip()
        if reported != str(os.getpid()):
            fail(f"the wrapper shell was not skipped: holder {reported}, expected {os.getpid()}")
        for line, want in [("zsh -c source x", True), ("/bin/bash -lc make", True), ("sh -c true", True),
                           ("/usr/bin/env python3 x", True), ("zsh -l", False), ("claude --verbose", False),
                           ("bash", False)]:
            if bool(WRAPPER.match(line)) != want:
                fail(f"wrapper detection for {line!r} should be {want}")
        if filesystem_type(base) in NETWORK_FS:
            fail("the fixture directory looks like a network filesystem")
    except TimeoutError as e:
        fail(str(e))
    except Exception as e:  # noqa: BLE001 - an unexpected state is a failure, reported rather than raised
        fail(f"unexpected {type(e).__name__}: {e}")
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
        for c in children:
            if c.poll() is None:
                c.kill()
            c.wait()
        for pid in orphans:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        shutil.rmtree(base, ignore_errors=True)
    return failures


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
