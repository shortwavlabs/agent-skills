#!/usr/bin/env python3
"""Handoff records: create one, check it against the repository, verify its authorizations, draft a PR summary.

    handoff.py new --title T [--author A] [--claim ID] [--transfer-token X|-] [--supersede] [--repo DIR]
    handoff.py check [FILE] [--fresh] [--repo DIR]   exit 0 matches; 1 drift or unknown; 2 invalid record
    handoff.py verify-auth [FILE] --action SLUG --level R0|R1|R2 [--branch B] [--path P]... [--destination D]
                           [--target T] [--purpose P] [--cost-usd N] [--aspect execute|spend] [--repository R]
                           [--pin SHA] [--repo DIR]      exit 0 when a reference is verified for that operation
    handoff.py summary [FILE]                        a redacted draft for a PR description: review before posting
    handoff.py --self-test
FILE defaults to the current branch's record under .agent-state/handoffs/.

A handoff is evidence, not authority. `check` compares the record with the repository as it is now: repository
identity, checkout, branch, HEAD, upstream (cached, or freshly verified with --fresh), the uncommitted paths and their
contents, artifacts (existence, type, content identity), recorded jobs (running, ended or unknown) and the claim. It
reports every difference, reports what it could not establish as unknown, changes nothing, never restarts,
duplicates or stops a job, and writes no bytecode. `verify-auth` evaluates each reference with authorization.py for
one structured operation; only `verified` grants authority. Records are private files (mode 0600), published
atomically; a superseded record is kept under history/. Format: `handoff` version 1 (operational/formats.json).
Standard library only.
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
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
STATE = ".agent-state"
CLAIM_ID = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{8}$")
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
PLACEHOLDER = re.compile(r"<[a-z][^<>\n]{2,}>")
DIRTY_LINE = re.compile(r"^- (.+) (sha256:[0-9a-f]{64}|deleted|not-hashed)$")
MAX_DIRTY = 200                                       # uncommitted paths recorded with digests; more is unknown
REDACT = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(-----END [A-Z ]*PRIVATE KEY-----|$)", re.S), "<private key>"),
    (re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|xox[abp]-[\w-]{10,})\b"),
     "<credential>"),
    (re.compile(r"(?i)\b(bearer|token|password|secret|api[_-]?key)(\s*[:=]\s*|\s+)(\S{8,})"), r"\1\2<redacted>"),
    (re.compile(r"\b([a-z][a-z0-9+.-]*://)[^\s/:@]+:[^\s/@]+@"), r"\1<credentials>@"),
    (re.compile(r"(?<![\w/])(?:/Users|/home|/private|/var|/tmp|/opt|/mnt|/root|[A-Za-z]:\\)[^\s`'\")\]]*"), "<path>"),
    (re.compile(r"\b[0-9a-f]{32}\b"), "<token>"),
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "<email>"),
]
SUMMARY_SECTIONS = ("Goal", "State", "Done", "Pending", "Blockers and decisions needed", "Verification",
                    "Assumptions and limitations")
_modules: dict = {}


def module(name: str):
    """A sibling script, loaded by path: works the same in the repository and in an installed skill."""
    if name not in _modules:
        spec = importlib.util.spec_from_file_location(f"handoff_{name}", HERE / f"{name}.py")
        _modules[name] = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_modules[name])
    return _modules[name]


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def stamp(t: datetime.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=60,
                              env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
    except (OSError, subprocess.SubprocessError) as e:
        return subprocess.CompletedProcess(args, 127, "", str(e))


def git_bytes(root: Path, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=60,
                              env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
    except (OSError, subprocess.SubprocessError) as e:
        return subprocess.CompletedProcess(args, 127, b"", str(e).encode())


def checkout_root(repo) -> Path:
    r = git(Path(repo), "rev-parse", "--show-toplevel")
    if r.returncode != 0:
        raise SystemExit(f"error: {repo} is not inside a git checkout")
    return Path(r.stdout.strip()).resolve()


def canonical_remote(url: str) -> str | None:
    """host/owner/name of a remote URL (https, scp-like or ssh), lowercase; None for local or unknown forms."""
    url = url.strip()
    m = re.match(r"^(?:[a-z][a-z0-9+.-]*://)(?:[^@/]+@)?([^/:]+)(?::\d+)?/(.+?)(?:\.git)?/?$", url) or \
        re.match(r"^(?:[^@/]+@)?([^/:]+):(?!/)(.+?)(?:\.git)?/?$", url)
    if not m or m.group(1) in ("", "localhost"):
        return None
    return f"{m.group(1)}/{m.group(2)}".lower()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def dirty_inventory(root: Path) -> tuple[dict[str, str] | None, str | None, int]:
    """({path: "sha256:<hex>" | "deleted" | "not-hashed"}, why unknown, total). None when git status failed."""
    r = git_bytes(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if r.returncode != 0:
        return None, f"git status failed: {(r.stderr or b'').decode(errors='replace').strip()[:120]}", 0
    entries = (r.stdout or b"").decode("utf-8", "surrogateescape").split("\0")
    paths, i = [], 0
    while i < len(entries):
        item = entries[i]
        if len(item) > 3:
            paths.append(item[3:])
            if item[0] in "RC":
                i += 1                                # the next entry is the rename's source path
        i += 1
    out: dict[str, str] = {}
    for rel in sorted(set(paths))[:MAX_DIRTY]:
        p = root / rel
        if not os.path.lexists(p):
            out[rel] = "deleted"
        elif p.is_file() and not p.is_symlink():
            try:
                out[rel] = "sha256:" + sha256_file(p)
            except OSError:
                out[rel] = "not-hashed"
        else:
            out[rel] = "not-hashed"
    return out, None, len(set(paths))


def repo_state(root: Path, fresh: bool = False) -> dict:
    """Identity, branch, HEAD, upstream and working tree as they are now. Anything that cannot be read is None, with
    the reason in `unknown`: unavailable information is never reported as a verified absence."""
    unknown: list[str] = []
    branch_r = git(root, "symbolic-ref", "--short", "-q", "HEAD")
    branch = branch_r.stdout.strip() if branch_r.returncode == 0 else "(detached)"
    head_r = git(root, "rev-parse", "--verify", "-q", "HEAD")
    head = head_r.stdout.strip() if head_r.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", head_r.stdout.strip()) \
        else None
    if head is None:
        unknown.append("HEAD cannot be read")
    upstream_ref = git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}")
    remote = None
    if upstream_ref.returncode == 0 and "/" in upstream_ref.stdout:
        remote = git(root, "config", f"branch.{branch}.remote").stdout.strip() or upstream_ref.stdout.split("/")[0]
    remotes = git(root, "remote").stdout.split()
    remote = remote or ("origin" if "origin" in remotes else (remotes[0] if remotes else None))
    url = git(root, "remote", "get-url", remote).stdout.strip() if remote else ""
    identity = canonical_remote(url) if url else None
    upstream, basis = "not pushed", "no upstream"
    if upstream_ref.returncode == 0:
        counts = git(root, "rev-list", "--left-right", "--count", "@{upstream}...HEAD")
        if counts.returncode != 0:
            upstream = None
            unknown.append("the upstream comparison failed")
        else:
            behind, ahead = (int(x) for x in counts.stdout.split())
            state = "in sync" if not (ahead or behind) else ", ".join(
                p for p in (f"ahead {ahead}" if ahead else "", f"behind {behind}" if behind else "") if p)
            upstream = f"{state} ({upstream_ref.stdout.strip()})"
            fetched = Path(git(root, "rev-parse", "--git-dir").stdout.strip() or ".git")
            fetched = (fetched if fetched.is_absolute() else root / fetched) / "FETCH_HEAD"
            basis = "cached; last fetched " + (stamp(datetime.datetime.fromtimestamp(
                fetched.stat().st_mtime, datetime.timezone.utc).replace(microsecond=0)) if fetched.exists() else "never")
    remote_head = None
    if fresh and remote and branch != "(detached)":
        ls = git(root, "ls-remote", "--heads", remote, f"refs/heads/{branch}")
        if ls.returncode != 0:
            unknown.append(f"the remote {remote} could not be queried")
        else:
            remote_head = ls.stdout.split()[0] if ls.stdout.strip() else "absent"
    dirty, why, total = dirty_inventory(root)
    if dirty is None:
        unknown.append(why)
        worktree = f"unknown ({why})"
    elif not total:
        worktree = "clean"
    else:
        worktree = f"dirty ({total} paths, listed under State)"
        if total > MAX_DIRTY:
            unknown.append(f"{total - MAX_DIRTY} uncommitted paths beyond the first {MAX_DIRTY} are not recorded")
    return {"identity": identity, "remote": remote, "checkout": f"{socket.gethostname()}:{root}", "branch": branch,
            "head": head, "upstream": upstream, "basis": basis, "remote_head": remote_head, "worktree": worktree,
            "dirty": dirty, "dirty_total": total, "unknown": unknown}


def record_name(branch: str) -> str:
    """A collision-resistant file name: the branch percent-encoded (so a/b and a--b differ) plus a digest of the exact
    name (so names differing only in case differ on case-insensitive filesystems)."""
    return f"{urllib.parse.quote(branch, safe='-_.')}.{hashlib.sha256(branch.encode()).hexdigest()[:10]}.md"


def default_path(root: Path, branch: str) -> Path:
    return root / STATE / "handoffs" / record_name(branch)


def parse(text: str) -> tuple[dict, dict]:
    """(headers, sections) of a record; sections map a heading to its lines."""
    lines = text.split("\n")
    first = next((i for i, line in enumerate(lines) if line.startswith("## ")), len(lines))
    headers = {}
    for line in lines[1:first]:
        m = re.match(r"^([A-Za-z][A-Za-z ]*):\s*(.*)$", line)
        if m:
            headers[m.group(1)] = m.group(2).strip()
    sections: dict[str, list[str]] = {}
    current = None
    for line in lines[first:]:
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return headers, sections


def json_block(lines: list[str]):
    blocks = re.findall(r"```json\n(.*?)\n```", "\n".join(lines), re.S)
    return module("operational_records").strict_json(blocks[0]) if len(blocks) == 1 else None


def safe_dir(root: Path, d: Path) -> None:
    if d.is_symlink() or (d.exists() and not d.is_dir()):
        raise SystemExit(f"error: {d.relative_to(root)} is a symlink or not a directory: refusing to use it")
    d.mkdir(mode=0o700, exist_ok=True)
    if d.is_symlink() or d.resolve() != root / d.relative_to(root):
        raise SystemExit(f"error: {d.relative_to(root)} resolves outside the checkout: refusing to use it")


def ensure_state_dir(root: Path) -> Path:
    """.agent-state/ with its self-ignoring .gitignore; refuses symlinks anywhere and a location git would track."""
    state, handoffs = root / STATE, root / STATE / "handoffs"
    for d in (state, handoffs, handoffs / "history"):
        safe_dir(root, d)
    ignore = state / ".gitignore"
    if ignore.is_symlink():
        raise SystemExit("error: .agent-state/.gitignore is a symlink: refusing to use the directory")
    if not ignore.exists():
        try:
            fd = os.open(ignore, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
            with os.fdopen(fd, "w") as fh:
                fh.write("*\n")
        except FileExistsError:
            pass
    if git(root, "check-ignore", "-q", f"{STATE}/handoffs/probe.md").returncode != 0:
        raise SystemExit("error: git would track .agent-state/: refusing to write a handoff record there")
    return handoffs


def publish(path: Path, data: bytes) -> None:
    """Write a private file atomically: a temporary file in the same directory, flushed, then renamed into place."""
    tmp = path.parent / f".tmp-{path.name}-{secrets.token_hex(4)}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    dfd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def archive(history: Path, stem: str, data: bytes) -> Path:
    """Keep a superseded record under history/, never overwriting: the name carries its Created time (validated) and
    a digest of its bytes, and is created exclusively."""
    created = parse(data.decode("utf-8", "replace"))[0].get("Created", "")
    created = created.replace(":", "") if TIMESTAMP.match(created) else "unknown"
    target = history / f"{stem}.{created}.{hashlib.sha256(data).hexdigest()[:12]}.md"
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except FileExistsError:
        if target.is_file() and not target.is_symlink() and target.read_bytes() == data:
            return target                             # already kept (an earlier, interrupted supersession)
        raise SystemExit(f"error: {target.name} exists with other content: refusing to overwrite history")
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    return target


# ------------------------------------------------------------------------------------------------------- new

TEMPLATE = """# Handoff: {title}

Version: 1
Created: {created}
Author: {author}
Repository: {repository}
Checkout: {checkout}
Branch: {branch}
HEAD: {head}
Upstream: {upstream}
Working tree: {worktree}
PR: {pr}
Claim: {claim}
Transfer: {transfer}
Supersedes: {supersedes}

## Goal
<objective, and what is in and out of scope>

## State
<one line of status>{dirty}

## Done
- [REPORTED] <what was completed; VERIFIED items need method:, artifact: and at:>

## Pending
1. <the next step, startable without reading anything else>

## Decisions and rejected approaches
- <decision and reason; rejected approach and the evidence against it>

## Blockers and decisions needed
- None.

## Artifacts
```json
[]
```

## Authorizations in force
```json
[]
```

## Running processes and jobs
- None.

## Verification
<tests and checks run, with commands and results; what was not tested>

## Assumptions and limitations
- [UNKNOWN] <known defects, limitations and open questions>

## Resume
1. Run `handoff.py check` and resolve every difference it reports before acting.
2. Treat Done items as REPORTED until re-verified; reuse expensive results whose inputs are unchanged.
3. Accept the claim transfer, if any; verify the authorizations the next step needs (`handoff.py verify-auth`).
4. Continue with Pending item 1.
"""


def new(root: Path, title: str, author: str, claim: str, transfer: str, supersede: bool, pr: str | None = None) -> Path:
    state = repo_state(root)
    if state["head"] is None:
        raise SystemExit("error: HEAD cannot be read: a record must name a commit")
    if claim and not CLAIM_ID.match(claim):
        raise SystemExit(f"error: {claim!r} is not a claim id")
    folder = ensure_state_dir(root)
    target = folder / record_name(state["branch"])
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise SystemExit(f"error: {target.relative_to(root)} is a symlink or not a regular file: refusing it")
    previous, supersedes = None, "none"
    if target.exists():
        if not supersede:
            raise SystemExit(f"error: {target.relative_to(root)} exists: pass --supersede to keep it as history "
                             "and start a new record")
        previous = target.read_bytes()
        archive(folder / "history", target.stem, previous)
        created = parse(previous.decode("utf-8", "replace"))[0].get("Created", "")
        supersedes = created if TIMESTAMP.match(created) else "unknown"
    if pr is None:
        try:
            r = subprocess.run(["gh", "pr", "view", "--json", "url", "-q", ".url"], cwd=root, capture_output=True,
                               text=True, timeout=30)
            pr = r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else "none"
        except (OSError, subprocess.SubprocessError):
            pr = "unknown (gh unavailable)"
    dirty = "".join(f"\n- {p} {v}" for p, v in (state["dirty"] or {}).items())
    if state["dirty_total"] > MAX_DIRTY:
        dirty += f"\n{state['dirty_total'] - MAX_DIRTY} more uncommitted paths are not recorded."
    text = TEMPLATE.format(
        title=title, created=stamp(utcnow()), author=author,
        repository=state["identity"] or "none (no remote: local repository)", checkout=state["checkout"],
        branch=state["branch"], head=state["head"], worktree=state["worktree"], pr=pr, claim=claim or "none",
        upstream=f"{state['upstream'] or 'unknown'}; {state['basis']}", transfer=transfer or "none",
        supersedes=supersedes, dirty=dirty)
    # Concurrent supersession: the record must still be the one archived when the new one replaces it.
    current = target.read_bytes() if target.exists() else None
    if current != previous:
        raise SystemExit("error: the record changed while it was being superseded: read it again and retry")
    publish(target, text.encode("utf-8"))
    return target


# ----------------------------------------------------------------------------------------------------- check

def check(path: Path, root: Path, fresh: bool = False) -> tuple[str, list[str]]:
    """(verdict, lines): matches, drift, unknown or invalid. Read-only."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return "invalid", [f"problem: {path} cannot be read: {e}"]
    rec = module("operational_records")
    problems = rec.Checker(rec.load_formats()).check_text(text, path.name)
    if problems:
        return "invalid", [f"problem: {p}" for p in problems]
    headers, sections = parse(text)
    out, flags = [], {"drift": False, "unknown": False}

    def drift(line: str) -> None:
        flags["drift"] = True
        out.append(f"drift: {line}")

    def unknown(line: str) -> None:
        flags["unknown"] = True
        out.append(f"unknown: {line}")
    if path.stat().st_mode & 0o077:
        drift(f"{path.name} is readable by other users: it may hold a transfer token (chmod 600)")
    now = repo_state(root, fresh)
    for why in now["unknown"]:
        unknown(why)
    if headers["Repository"] != (now["identity"] or "none (no remote: local repository)"):
        drift(f"recorded repository {headers['Repository']!r}, this checkout is {now['identity'] or 'local only'!r}: "
              "a remote's name proves nothing")
    if "Checkout" in headers and headers["Checkout"] != now["checkout"]:
        drift(f"recorded in checkout {headers['Checkout']}, this is {now['checkout']}: local files and processes "
              "may differ")
    if headers["Branch"] != now["branch"]:
        drift(f"recorded on branch {headers['Branch']}, the checkout is on {now['branch']}")
    recorded = headers["HEAD"]
    if now["head"] and recorded != now["head"]:
        if git(root, "cat-file", "-e", f"{recorded}^{{commit}}").returncode != 0:
            drift(f"recorded HEAD {recorded[:12]} does not exist here (rewritten history, or not fetched)")
        elif git(root, "merge-base", "--is-ancestor", recorded, now["head"]).returncode == 0:
            n = git(root, "rev-list", "--count", f"{recorded}..{now['head']}").stdout.strip()
            drift(f"{n} commits since the record (HEAD {now['head'][:12]}): re-verify what depends on them")
        else:
            drift(f"HEAD {now['head'][:12]} does not descend from the recorded {recorded[:12]}")
    recorded_upstream = headers["Upstream"].split(";")[0].strip()
    if now["upstream"] is not None and recorded_upstream != now["upstream"]:
        drift(f"upstream was '{recorded_upstream}', now '{now['upstream']}' ({now['basis']})")
    if now["remote_head"] is not None:
        if now["remote_head"] == now["head"]:
            out.append(f"ok: freshly verified: {now['remote']} has this branch at HEAD")
        else:
            drift(f"freshly verified: {now['remote']} has this branch at {now['remote_head'][:12]}, not at HEAD")
    if now["dirty"] is not None:
        if headers["Working tree"] != now["worktree"]:
            drift(f"working tree was '{headers['Working tree']}', now '{now['worktree']}'")
        recorded_dirty = {m.group(1): m.group(2) for m in (DIRTY_LINE.match(l) for l in sections.get("State", [])) if m}
        if now["dirty"] or recorded_dirty:
            if set(recorded_dirty) != set(now["dirty"]):
                drift(f"the uncommitted paths differ from those listed under State "
                      f"(now: {', '.join(list(now['dirty'])[:5]) or 'none'})")
            else:
                for rel, digest in now["dirty"].items():
                    if "not-hashed" in (digest, recorded_dirty[rel]):
                        unknown(f"the uncommitted content of {rel} is not hashed: compare it by hand")
                    elif digest != recorded_dirty[rel]:
                        drift(f"the uncommitted content of {rel} changed since the record (same path, other content)")
                if not flags["drift"]:
                    out.append(f"ok: {len(now['dirty'])} uncommitted paths match the record by content")
    for heading, lines in sections.items():
        for line in lines:
            if PLACEHOLDER.search(line) and not line.lstrip().startswith(("```", "{", "[", "\"")):
                drift(f"'## {heading}' still holds a template placeholder: {line.strip()[:70]!r}")
                break
    for a in json_block(sections.get("Artifacts", [])) or []:
        kind, ident = a["type"], a["id"]
        supports = f"; it does not by itself establish: {a['supports']}" if a.get("supports") else \
            "; whether it establishes the claimed result is for you to judge"
        if kind == "file":
            target = Path(ident) if os.path.isabs(ident) else root / ident
            if not os.path.lexists(target):
                drift(f"artifact {ident} is missing")
            elif target.is_symlink() or not target.is_file():
                drift(f"artifact {ident} is not a regular file (recorded as a file)")
            elif sha256_file(target) != a["sha256"]:
                drift(f"artifact {ident} changed (sha256 differs from the record)")
            else:
                out.append(f"ok: artifact {ident} exists, is a file and matches its sha256{supports}")
        elif kind in ("commit", "tree"):
            actual = git(root, "cat-file", "-t", ident)
            if actual.returncode != 0:
                drift(f"{kind} {ident[:12]} does not exist here")
            elif actual.stdout.strip() != kind:
                drift(f"{ident[:12]} is a {actual.stdout.strip()}, recorded as a {kind}")
            else:
                out.append(f"ok: {kind} {ident[:12]} exists{supports}")
        else:
            out.append(f"note: {kind} {ident} is not checked locally: open it before relying on it")
    identity = module("process_identity")
    local = identity.here()
    for job in json_block(sections.get("Running processes and jobs", [])) or []:
        label = f"job {job['id']} ({job['command'][:60]})"
        if job.get("pid") is None:
            out.append(f"note: {label} is not a local process: check it where it runs before deciding anything")
            continue
        state, reason = identity.liveness(job["pid"], job["process_start"], job.get("host", local["host"]),
                                          job.get("boot"), local)
        if state == "live":
            out.append(f"note: {label} is still running: do not restart, duplicate or stop it; wait or ask")
        elif state == "dead":
            drift(f"{label} has ended ({reason}): inspect its output and logs before deciding; never rerun an "
                  "expensive job whose inputs are unchanged without checking its results")
        else:
            unknown(f"{label}: whether it still runs cannot be established ({reason}); do not assume it ended")
    claim = headers.get("Claim", "none")
    if claim != "none" and not CLAIM_ID.match(claim):
        drift(f"'Claim: {claim[:40]}' is not a claim id")
    elif claim != "none":
        file = root / STATE / "claims" / f"{claim}.json"
        if file.is_symlink() or not file.is_file():
            drift(f"claim {claim} is no longer active (released, archived or never made here): acquire anew with "
                  "development-coordination before a disruptive step")
        else:
            try:
                data = rec.strict_json(file.read_text(encoding="utf-8"))
                holder = data["holder"]
                pending = " A transfer is pending: accept it with development-coordination (`accept`)." \
                    if data.get("transfer") else ""
                out.append(f"note: claim {claim} is held by {holder['agent']} (process {holder['pid']}).{pending}")
            except (OSError, ValueError, KeyError, TypeError) as e:
                unknown(f"claim {claim} cannot be read: {e}")
    references = json_block(sections["Authorizations in force"]) or []
    if references:
        out.append(f"note: {len(references)} authorization references are unverified until `verify-auth` checks them "
                   "for the operation at hand; only verified grants authority")
    return ("drift" if flags["drift"] else "unknown" if flags["unknown"] else "matches"), out


# ------------------------------------------------------------------------------------------------ verify-auth

def verify_auth(path: Path, root: Path, operation: dict, gather=None, policy_source=None,
                now: datetime.datetime | None = None, pin: str | None = None) -> list[tuple[object, str, str, dict]]:
    """[(reference, status, reason, facts)] for every reference in the record, evaluated for one structured
    operation. Every reference in a structurally invalid record is invalid. Facts are gathered (read-only) even
    without a trusted policy, so the owner sees what the host records; without the policy nothing verifies."""
    auth, facts_mod, rec = module("authorization"), module("github_facts"), module("operational_records")
    text = path.read_text(encoding="utf-8")
    problems = rec.Checker(rec.load_formats()).check_text(text, path.name)
    try:
        references = json_block(parse(text)[1].get("Authorizations in force", [])) or []
    except ValueError as e:
        problems = problems + [f"the authorization block does not parse: {e}"]
        references = []
    if problems:
        why = "the record is invalid, so every reference in it is invalid: " + "; ".join(problems)[:300]
        return [(r, "invalid", why, {}) for r in references] or [(None, "invalid", why, {})]
    policy, _ = (policy_source or auth.canonical_policy)()
    owners = policy.get("owners", []) if policy else []
    out = []
    for reference in references:
        facts = {}
        if isinstance(reference, dict) and reference.get("source") == "standing":
            facts = (gather or facts_mod.gather)(reference, root, owners, pin=pin) if pin else \
                (gather or facts_mod.gather)(reference, root, owners)
        status, reason = auth.evaluate(reference, operation, facts, policy, now or utcnow())
        out.append((reference, status, reason, facts))
    return out


def describe_facts(facts: dict) -> str:
    if not facts:
        return "no host facts (not a standing reference)"
    if not facts.get("host_reachable"):
        return f"host not reached: {facts.get('why', 'unknown')}"
    a = facts.get("approval") or {}
    return (f"repository {facts.get('repository')} pinned at {str(facts.get('default_revision'))[:12]}; commit exists: "
            f"{facts.get('commit_exists')}; entry found: {facts.get('entry_at_reference') is not None}; approval: "
            f"{a.get('kind')} by {a.get('by')} ({a.get('state')}, content {a.get('entry_at_approved_revision')}, "
            f"merged into the default branch: {a.get('merged_into_default_branch')}, introduced by the PR: "
            f"{a.get('introduced_entry')}); default branch: {facts.get('entry_on_default_branch')}; reinstated: "
            f"{facts.get('reinstated_after_approval')}; changed since: {facts.get('changed_after_approval')}")


# ---------------------------------------------------------------------------------------------------- summary

def redact(text: str) -> str:
    for pattern, replacement in REDACT:
        text = pattern.sub(replacement, text)
    return text


def summary(path: Path) -> str:
    """A redacted draft for a PR description, from an allowlist: the title, the record's time, HEAD, the upstream
    state, and the Goal, State (first line), Done, Pending, Blockers, Verification and limitations sections. Headers
    (repository, checkout, author, claim, transfer token), authorization records, artifacts, jobs and process
    commands are never included. Redaction is pattern-based: the draft must be reviewed before it is posted."""
    text = path.read_text(encoding="utf-8")
    headers, sections = parse(text)
    title = text.split("\n", 1)[0].removeprefix("# Handoff: ")
    out = ["<!-- Redacted draft from a local handoff record: review it before publishing. Redaction is pattern-based, "
           "not a guarantee. -->", f"### Status: {redact(title)}", "",
           f"From the handoff record of {headers.get('Created', 'unknown')} (HEAD `{headers.get('HEAD', '?')[:12]}`, "
           f"upstream {redact(headers.get('Upstream', 'unknown').split(';')[0])}).", ""]
    for heading in SUMMARY_SECTIONS:
        body = [line for line in sections.get(heading, []) if line.strip()]
        if heading == "State":
            body = body[:1]
        if body:
            out += [f"**{heading}**", *[redact(line) for line in body], ""]
    return "\n".join(out).rstrip() + "\n"


# ---------------------------------------------------------------------------------------------------------- CLI

def main(argv: list[str]) -> int:
    if argv == ["--self-test"]:
        failures = self_test()
        for f in failures:
            print("FAIL:", f)
        print("handoff self-test: " + ("PASS" if not failures else f"{len(failures)} FAILED"))
        return 1 if failures else 0
    parser = argparse.ArgumentParser(prog="handoff.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("new", "check", "verify-auth", "summary"):
        p = sub.add_parser(name)
        p.add_argument("--repo", default=".")
        if name == "new":
            p.add_argument("--title", required=True)
            p.add_argument("--author", default=os.environ.get("CODING_AGENT", "agent"))
            p.add_argument("--claim", default="")
            p.add_argument("--transfer-token", default="", help="the token, or - to read it from standard input")
            p.add_argument("--supersede", action="store_true")
        else:
            p.add_argument("file", nargs="?")
        if name == "check":
            p.add_argument("--fresh", action="store_true", help="query the remote (read-only) instead of cached refs")
        if name == "verify-auth":
            p.add_argument("--action", required=True)
            p.add_argument("--level", required=True, choices=("R0", "R1", "R2", "R3"))
            p.add_argument("--repository")
            for field in ("branch", "destination", "target", "purpose"):
                p.add_argument(f"--{field}")
            p.add_argument("--path", action="append", dest="paths")
            p.add_argument("--cost-usd", type=float, dest="cost_usd")
            p.add_argument("--aspect", choices=("execute", "spend"))
            p.add_argument("--pin", help="the default-branch revision an earlier verification used")
    args = parser.parse_args(argv)
    root = checkout_root(args.repo)
    if args.command == "new":
        token = sys.stdin.readline().strip() if args.transfer_token == "-" else args.transfer_token
        path = new(root, args.title, args.author, args.claim, token, args.supersede)
        print(f"written: {path.relative_to(root)} (fill in every <placeholder>, then run `handoff.py check`)")
        return 0
    path = Path(args.file) if args.file else default_path(root, repo_state(root)["branch"])
    if args.command == "check":
        verdict, lines = check(path, root, args.fresh)
        print(f"verdict: {verdict}")
        for line in lines:
            print(line)
        return {"matches": 0, "drift": 1, "unknown": 1}.get(verdict, 2)
    if args.command == "verify-auth":
        operation = {"action": args.action, "level": args.level,
                     "repository": args.repository or repo_state(root)["identity"]}
        for field in ("branch", "destination", "target", "purpose", "paths", "cost_usd", "aspect"):
            if getattr(args, field) is not None:
                operation[field] = getattr(args, field)
        results = verify_auth(path, root, operation, pin=args.pin)
        for reference, status, reason, facts in results:
            ref = reference.get("ref", "?") if isinstance(reference, dict) else "?"
            print(f"{status}: {ref}: {reason}")
            if facts:
                print(f"  facts: {describe_facts(facts)}")
        if not results:
            print("no authorization references in the record: ask the owner for anything above R1")
        return 0 if any(r[1] == "verified" for r in results) else 1
    print(summary(path), end="")
    return 0


# ---------------------------------------------------------------------------------------------------------- self-test

def tree_digest(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        st = p.lstat()
        h.update(f"{p.relative_to(root).as_posix()}\0{st.st_mode}\0{st.st_mtime_ns}\0".encode())
        if p.is_file() and not p.is_symlink():
            h.update(p.read_bytes())
    return h.hexdigest()


def fill(text: str, **sections) -> str:
    """Replace the template's placeholders with test content."""
    text = re.sub(r"\n<objective[^\n]*>", "\nResume the parser refactor; out of scope: the lexer.", text)
    text = re.sub(r"\n<one line of status>", "\nRefactor half done; tests pass on HEAD.", text)
    text = re.sub(r"\n- \[REPORTED\] <what was[^\n]*>", "\n- [REPORTED] The parser module is split", text)
    text = re.sub(r"\n1\. <the next step[^\n]*>", "\n1. Split the remaining visitor functions", text)
    text = re.sub(r"\n- <decision and reason[^\n]*>", "\n- Kept the public API; a rename was rejected (breaks callers)",
                  text)
    text = re.sub(r"\n<tests and checks[^\n]*>", "\nUnit tests: make test exit 0. Not tested: Windows.", text)
    text = re.sub(r"\n- \[UNKNOWN\] <known defects[^\n]*>", "\n- [UNKNOWN] Whether the benchmarks still hold", text)
    for heading, body in sections.items():
        text = re.sub(rf"(## {heading}\n)(?:.*?)(\n## )", lambda m: m.group(1) + body + m.group(2), text, count=1,
                      flags=re.S)
    return text


def self_test() -> list[str]:
    failures: list[str] = []
    pycache_before = (HERE / "__pycache__").exists()
    base = Path(tempfile.mkdtemp(prefix="handoff-")).resolve()
    env = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "t",
           "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
    saved_env = {k: os.environ.get(k) for k in env}
    os.environ.update(env)                            # restored in finally
    sleeper = None

    def fail(msg: str) -> None:
        failures.append(msg)

    def run(root: Path, *args: str) -> None:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)

    def drifted(lines, fragment) -> bool:
        return any(line.startswith("drift:") and fragment in line for line in lines)

    try:
        root = base / "repo"
        (root / "src").mkdir(parents=True)
        (root / "src" / "parser.py").write_text("x = 1\n")
        run(root, "init", "-q", "-b", "feature/parser")
        run(root, "remote", "add", "origin", "git@github.com:Example/Repo.git")
        run(root, "add", ".")
        run(root, "commit", "-q", "-m", "init")
        path = new(root, "Parser refactor", "claude-code / test-model / s1", "", "", False, pr="none")
        if path != default_path(root, "feature/parser") or "%2F" not in path.name:
            fail(f"record path: {path}")
        if stat.S_IMODE(path.stat().st_mode) != 0o600 or stat.S_IMODE((root / STATE / "handoffs").stat().st_mode) != 0o700:
            fail("the record or its directory is not private")
        if git(root, "status", "--porcelain").stdout.strip():
            fail("writing a record made the working tree dirty (the state directory is not self-ignoring)")
        headers = parse(path.read_text(encoding="utf-8"))[0]
        if headers["Repository"] != "github.com/example/repo" or not headers["Upstream"].startswith("not pushed;"):
            fail(f"repository identity or upstream not recorded: {headers}")
        verdict, lines = check(path, root)
        if verdict != "drift" or not drifted(lines, "placeholder"):
            fail(f"an unfilled template passed: {verdict} {lines}")
        artifact = root / "src" / "parser.py"
        art = [{"type": "file", "id": "src/parser.py", "sha256": sha256_file(artifact), "supports": "the split works"},
               {"type": "commit", "id": git(root, "rev-parse", "HEAD").stdout.strip()},
               {"type": "tree", "id": git(root, "rev-parse", "HEAD").stdout.strip()},
               {"type": "ci-run", "id": "https://github.com/example/repo/actions/runs/1"}]
        identity = module("process_identity")
        sleeper = subprocess.Popen(["sleep", "300"])
        job = [{"id": "sweep-a", "kind": "process", "command": "sleep 300", "started": stamp(utcnow()),
                "host": socket.gethostname(), "pid": sleeper.pid, "process_start": identity.process_start(sleeper.pid)}]
        body = fill(path.read_text(encoding="utf-8"), Artifacts="```json\n" + json.dumps(art[:2] + art[3:], indent=2)
                    + "\n```\n", **{"Running processes and jobs": "```json\n" + json.dumps(job, indent=2) + "\n```\n"})
        publish(path, body.encode("utf-8"))
        before = tree_digest(root)
        verdict, lines = check(path, root)
        if verdict != "matches":
            fail(f"a filled record of an unchanged repository: {verdict} {lines}")
        if not any("still running" in l for l in lines) or not any("ci-run" in l for l in lines) \
                or not any("does not by itself establish: the split works" in l for l in lines):
            fail(f"job, remote artifact or claimed result not reported: {lines}")
        if tree_digest(root) != before:
            fail("check changed the repository")
        # Artifact type: a commit recorded as a tree.
        typed = fill(path.read_text(encoding="utf-8"), Artifacts="```json\n" + json.dumps(art[2:3]) + "\n```\n")
        bad = base / "typed.md"
        bad.write_text(typed, encoding="utf-8")
        bad.chmod(0o600)
        if not drifted(check(bad, root)[1], "is a commit, recorded as a tree"):
            fail("an artifact of the wrong type was not reported")
        # Process liveness: unknown is not ended; ended is drift.
        saved = identity.process_start
        identity.process_start = lambda pid: None
        try:
            verdict, lines = check(path, root)
            if verdict != "unknown" or not any(l.startswith("unknown:") and "do not assume it ended" in l for l in lines):
                fail(f"an unreadable process identity was not unknown: {verdict} {lines}")
        finally:
            identity.process_start = saved
        sleeper.kill()
        sleeper.wait()
        verdict, lines = check(path, root)
        if verdict != "drift" or not drifted(lines, "has ended"):
            fail(f"an ended job was not reported: {lines}")
        # Dirty trees: same inventory, different content.
        (root / "notes.txt").write_text("draft 1\n")
        dirty = new(root, "Dirty", "a", "", "", True, pr="none")
        publish(dirty, fill(dirty.read_text(encoding="utf-8")).encode("utf-8"))
        verdict, lines = check(dirty, root)
        if verdict != "matches" or not any("match the record by content" in l for l in lines):
            fail(f"a dirty tree matching its record: {verdict} {lines}")
        (root / "notes.txt").write_text("draft 2\n")
        if not drifted(check(dirty, root)[1], "uncommitted content of notes.txt changed"):
            fail("changed uncommitted content with an identical path inventory was not reported")
        (root / "other.txt").write_text("x")
        if not drifted(check(dirty, root)[1], "uncommitted paths differ"):
            fail("a changed inventory of uncommitted paths was not reported")
        (root / "other.txt").unlink()
        (root / "notes.txt").write_text("draft 1\n")
        # A failing git status is unknown, never clean.
        index = root / ".git" / "index"
        saved_index = index.read_bytes()
        index.write_bytes(b"not an index")
        verdict, lines = check(dirty, root)
        if verdict == "matches" or not any(l.startswith("unknown:") and "git status failed" in l for l in lines):
            fail(f"a failing git status was not unknown: {verdict} {lines}")
        if repo_state(root)["worktree"] == "clean":
            fail("a failing git status was reported as a clean working tree")
        index.write_bytes(saved_index)
        (root / "notes.txt").unlink()
        # Repository identity: the same remote name for another repository is a mismatch.
        run(root, "remote", "set-url", "origin", "git@github.com:example/other.git")
        if not drifted(check(dirty, root)[1], "a remote's name proves nothing"):
            fail("a different repository behind the same remote name was not reported")
        run(root, "remote", "set-url", "origin", "git@github.com:Example/Repo.git")
        # Upstream: exact comparison, and the cached basis is stated.
        record = dirty.read_text(encoding="utf-8")
        publish(dirty, record.replace("Upstream: not pushed;", "Upstream: ahead 12 (origin/x);").encode())
        if not drifted(check(dirty, root)[1], "upstream was 'ahead 12 (origin/x)'"):
            fail("a changed upstream was not reported")
        publish(dirty, record.replace("Claim: none", "Claim: ../../etc/passwd").encode())
        if not drifted(check(dirty, root)[1], "is not a claim id"):
            fail("a malformed claim id was not reported")
        publish(dirty, record.encode())
        dirty.chmod(0o644)
        if not drifted(check(dirty, root)[1], "readable by other users"):
            fail("a record readable by others was not reported")
        dirty.chmod(0o600)
        # Branch names that collided under the old scheme map to distinct records.
        names = {record_name(b) for b in ("a/b", "a--b", "A/b", "a%2Fb")}
        if len(names) != 4 or any("/" in n for n in names):
            fail(f"branch names collide: {names}")
        # Unsafe state directories and history.
        for label, setup in [("symlinked history", lambda d: (shutil.rmtree(d / "history"),
                                                              (d / "history").symlink_to(base))),
                             ("symlinked ignore file", lambda d: ((d.parent / ".gitignore").unlink(),
                                                                  (d.parent / ".gitignore").symlink_to(base / "x")))]:
            other = base / label.replace(" ", "-")
            other.mkdir()
            run(other, "init", "-q")
            run(other, "commit", "-q", "--allow-empty", "-m", "init")
            new(other, "x", "a", "", "", False, pr="none")
            setup(other / STATE / "handoffs")
            try:
                new(other, "x", "a", "", "", True, pr="none")
                fail(f"{label}: a record was written")
            except SystemExit:
                pass
        tracked = base / "tracked"
        tracked.mkdir()
        run(tracked, "init", "-q")
        run(tracked, "commit", "-q", "--allow-empty", "-m", "init")
        (tracked / STATE).mkdir()
        (tracked / STATE / ".gitignore").write_text("# ignores nothing\n")
        try:
            new(tracked, "x", "a", "", "", False, pr="none")
            fail("a record was written where git would track it")
        except SystemExit:
            pass
        # Supersession keeps every previous record, survives interruption and refuses concurrent change.
        try:
            new(root, "Again", "codex", "", "", False, pr="none")
            fail("an existing record was overwritten without --supersede")
        except SystemExit:
            pass
        history = root / STATE / "handoffs" / "history"
        kept = len(list(history.glob("*.md")))
        current_bytes = path.read_bytes()
        unsafe = current_bytes.replace(parse(current_bytes.decode())[0]["Created"].encode(), b"../../escape", 1)
        publish(path, unsafe)
        again = new(root, "Again", "codex / test-model / s2", "", "", True, pr="none")
        names = sorted(p.name for p in history.glob("*.md"))
        if len(names) != kept + 1 or not any(".unknown." in n for n in names) or (base / "escape").exists():
            fail(f"supersession with an unsafe Created value: {names}")
        if parse(again.read_text(encoding="utf-8"))[0]["Supersedes"] != "unknown":
            fail("an unsafe Created value was carried into Supersedes")
        saved_publish = globals()["publish"]

        def interrupted(target, data):
            raise KeyboardInterrupt("simulated interruption")
        globals()["publish"] = interrupted
        before_bytes = again.read_bytes()
        try:
            new(root, "Interrupted", "codex", "", "", True, pr="none")
            fail("the simulated interruption did not happen")
        except KeyboardInterrupt:
            pass
        finally:
            globals()["publish"] = saved_publish
        if again.read_bytes() != before_bytes or list(again.parent.glob(".tmp-*")):
            fail("an interrupted supersession lost or damaged the current record")
        if not any(p.read_bytes() == before_bytes for p in history.glob("*.md")):
            fail("an interrupted supersession did not keep the previous record")
        new(root, "Retry", "codex", "", "", True, pr="none")  # the retry finds the record already archived
        real_archive = globals()["archive"]

        def racing_archive(folder, stem, data):
            kept_path = real_archive(folder, stem, data)
            publish(default_path(root, "feature/parser"), b"# Handoff: another session\n")
            return kept_path
        globals()["archive"] = racing_archive
        try:
            new(root, "Racing", "codex", "", "", True, pr="none")
            fail("a concurrent change during supersession was not detected")
        except SystemExit:
            pass
        finally:
            globals()["archive"] = real_archive
        if default_path(root, "feature/parser").read_bytes() != b"# Handoff: another session\n":
            fail("the concurrent writer's record was overwritten")
        # The PR summary: an allowlisted, redacted draft.
        again = new(root, "Again", "codex / test-model / s2", "", "", True, pr="none")
        leaky = again.read_text(encoding="utf-8")
        leaky = fill(leaky).replace("Refactor half done; tests pass on HEAD.",
                                    "Logs at /home/someone/project/out.log; mail me@example.com; copy at "
                                    "C:\\Users\\someone\\out.log; the tokenizer is fixed; token: hunter2hunter2; "
                                    "clone https://bob:pa55word@git.example.com/x.git with ghp_" + "a" * 36)
        leaky = leaky.replace("- [REPORTED] The parser module is split",
                              "- [REPORTED] session 0123456789abcdef0123456789abcdef; key AKIA" + "A" * 16)
        leaky = leaky.replace("Transfer: none", "Transfer: fedcba9876543210fedcba9876543210")
        leaky = leaky.replace("## Running processes and jobs\n- None.",
                              "## Running processes and jobs\n- python3 train.py --secret-flag")
        publish(again, leaky.encode())
        text = summary(again)
        for secret in ("/home/someone", "me@example.com", "0123456789abcdef0123456789abcdef", "Transfer",
                       "fedcba9876543210", "Authorizations", "Running processes", "train.py", "codex / test-model",
                       "Users\\someone", "hunter2hunter2", "pa55word", "ghp_aaaa", "AKIAAAAA", "Checkout",
                       "github.com/example/repo"):
            if secret in text:
                fail(f"the PR summary leaks {secret!r}")
        if "tokenizer is fixed" not in text or "review it before publishing" not in text:
            fail(f"the PR summary lost content or its review warning: {text}")
        # Authorization references: structured operations through the evaluator.
        auth = module("authorization")
        reference = {"level": "R2", "scope": "Push feature branches", "source": "standing", "by": "github:example-owner",
                     "ref": "ops/authorizations.json@" + "a" * 40 + "#push-feature-branches",
                     "granted": "2026-11-27T18:00:00Z", "expires": "2027-06-30T00:00:00Z"}
        session = {"level": "R2", "scope": "Mark the PR ready", "source": "owner-session", "by": "github:example-owner",
                   "ref": "the previous session", "quote": "mark it ready", "granted": "2026-11-27T18:05:00Z",
                   "expires": "task-end"}
        publish(again, fill(new(root, "Auth", "a", "", "", True, pr="none").read_text()).replace(
            "## Authorizations in force\n```json\n[]\n```",
            "## Authorizations in force\n```json\n" + json.dumps([reference, session]) + "\n```").encode())
        record = again.read_text(encoding="utf-8")
        facts = {"host_reachable": True, "repository": "github.com/example/repo", "commit_exists": True,
                 "entry_at_reference": {"id": "push-feature-branches", "level": "R2", "operations": "Push feature branches",
                                        "actions": ["push-branch"], "scope": {"branches": ["feature/*"],
                                                                              "destinations": ["origin"]},
                                        "granted_by": "github:example-owner",
                                        "approved_in": "https://github.com/example/repo/pull/1",
                                        "expires": "2027-06-30T00:00:00Z"},
                 "approval": {"kind": "merge", "by": "github:example-owner", "state": "active",
                              "entry_at_approved_revision": "identical", "introduced_entry": True,
                              "merged_into_default_branch": True},
                 "entry_on_default_branch": "identical", "reinstated_after_approval": False,
                 "changed_after_approval": False}
        test_policy = lambda: ({"owners": ["github:example-owner"], "repositories": ["github.com/example/repo"]}, "test")
        now = datetime.datetime(2026, 11, 28, tzinfo=datetime.timezone.utc)
        op = {"action": "push-branch", "level": "R2", "repository": "github.com/example/repo", "branch": "feature/x",
              "destination": "origin"}

        def statuses(operation, **kw):
            return [r[1] for r in verify_auth(again, root, operation, gather=lambda *a, **k: facts,
                                              policy_source=kw.get("policy", test_policy), now=now)]
        if statuses(op) != ["verified", "unknown"]:
            fail(f"verify-auth with a test policy: {statuses(op)}")
        for label, change, want in [("another action", {"action": "publish-release"}, "inapplicable"),
                                    ("a branch outside the scope", {"branch": "main"}, "inapplicable"),
                                    ("no risk level", {"level": None}, "unknown")]:
            got = statuses({k: v for k, v in {**op, **change}.items() if v is not None})[0]
            if got != want:
                fail(f"verify-auth for {label}: expected {want}, got {got}")
        if any(s == "verified" for s in statuses(op, policy=auth.canonical_policy)):
            fail("without the canonical policy, a reference was verified")
        broken = base / "broken.md"
        broken.write_text(record.replace("## Resume", "## Next"), encoding="utf-8")
        if [r[1] for r in verify_auth(broken, root, op, gather=lambda *a, **k: facts, policy_source=test_policy,
                                      now=now)] != ["invalid", "invalid"]:
            fail("references inside an invalid record were not all invalid")
        broken.write_text(record.replace('"level": "R2"', '"level": "R2", "level": "R1"', 1), encoding="utf-8")
        results = verify_auth(broken, root, op, gather=lambda *a, **k: facts, policy_source=test_policy, now=now)
        if not results or any(r[1] != "invalid" for r in results):
            fail(f"a duplicate JSON key did not make the references invalid: {results}")
        if auth.canonical_policy()[0] is not None:
            fail("a canonical policy appeared before Phase 1d defines one")
        for url, want in [("git@github.com:Example/Repo.git", "github.com/example/repo"),
                          ("https://github.com/example/repo", "github.com/example/repo"),
                          ("ssh://git@gitlab.example.com:2222/team/app.git", "gitlab.example.com/team/app"),
                          ("/srv/git/app.git", None), ("../app", None)]:
            if canonical_remote(url) != want:
                fail(f"canonical_remote({url!r}) should be {want!r}, got {canonical_remote(url)!r}")
    except Exception as e:  # noqa: BLE001 - an unexpected state is a failure, reported rather than raised
        fail(f"unexpected {type(e).__name__}: {e}")
    finally:
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        if sleeper and sleeper.poll() is None:
            sleeper.kill()
            sleeper.wait()
        shutil.rmtree(base, ignore_errors=True)
    if not pycache_before and (HERE / "__pycache__").exists():
        failures.append("running the tool wrote bytecode into the skill's scripts directory")
    return failures


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
