#!/usr/bin/env python3
"""Handoff records: create one, check it against the repository, verify its authorizations, summarize it for a PR.

    handoff.py new --title T [--author A] [--claim ID] [--transfer-token X] [--supersede] [--repo DIR]
    handoff.py check [FILE] [--repo DIR]           exit 0 matches, 1 drift found, 2 invalid record
    handoff.py verify-auth [FILE] --action SLUG [--level R1|R2] [--repo DIR]
                                                   exit 0 when a reference is verified for that action, 1 otherwise
    handoff.py summary [FILE]                      a public-safe status summary for a PR description
    handoff.py --self-test
FILE defaults to .agent-state/handoffs/<branch>.md for the current branch ("/" in a branch name becomes "--").

A handoff is evidence, not authority. `check` compares the record with the repository as it is now (branch, HEAD,
upstream, working tree, artifact digests, recorded jobs, the claim) and reports every difference; it changes
nothing, never restarts, duplicates or stops a job, and writes no bytecode. `verify-auth` evaluates each reference
with authorization.py at run time; only `verified` grants authority. The record format is `handoff` version 1
(operational/formats.json, checked by the generated copy of operational_records.py). Standard library only.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
STATE = ".agent-state"
PLACEHOLDER = re.compile(r"<[a-z][^<>\n]{2,}>")
CLAIM_ID = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{8}$")
REDACT = [(re.compile(r"(?<![\w/])(?:/Users|/home|/private|/var|/tmp|/opt|/mnt|[A-Za-z]:\\)[^\s`'\")\]]*"), "<path>"),
          (re.compile(r"\b[0-9a-f]{32}\b"), "<token>"),
          (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "<email>")]
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
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=60,
                          env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})


def checkout_root(repo) -> Path:
    r = git(Path(repo), "rev-parse", "--show-toplevel")
    if r.returncode != 0:
        raise SystemExit(f"error: {repo} is not inside a git checkout")
    return Path(r.stdout.strip()).resolve()


def repo_state(root: Path) -> dict:
    """Branch, HEAD, upstream and working tree as they are now."""
    branch = git(root, "symbolic-ref", "--short", "-q", "HEAD").stdout.strip() or "(detached)"
    head = git(root, "rev-parse", "HEAD").stdout.strip()
    upstream = "not pushed"
    counts = git(root, "rev-list", "--left-right", "--count", "@{upstream}...HEAD")
    if counts.returncode == 0:
        behind, ahead = (int(x) for x in counts.stdout.split())
        upstream = "in sync" if not (ahead or behind) else ", ".join(
            p for p in (f"ahead {ahead}" if ahead else "", f"behind {behind}" if behind else "") if p)
    dirty = [line[3:] for line in git(root, "status", "--porcelain=v1").stdout.splitlines() if line.strip()]
    return {"branch": branch, "head": head, "upstream": upstream,
            "worktree": "clean" if not dirty else f"dirty ({len(dirty)} paths, listed under State)", "dirty": dirty}


def default_path(root: Path, branch: str) -> Path:
    return root / STATE / "handoffs" / (branch.replace("/", "--") + ".md")


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


def ensure_state_dir(root: Path) -> Path:
    """.agent-state/ with its self-ignoring .gitignore, refusing a location git would track or a symlink."""
    state = root / STATE
    for d in (state, state / "handoffs"):
        if d.is_symlink() or (d.exists() and not d.is_dir()):
            raise SystemExit(f"error: {d.relative_to(root)} is a symlink or not a directory")
        d.mkdir(mode=0o700, exist_ok=True)
    ignore = state / ".gitignore"
    if not ignore.exists():
        ignore.write_text("*\n")
    if git(root, "check-ignore", "-q", f"{STATE}/handoffs/probe.md").returncode != 0:
        raise SystemExit("error: git would track .agent-state/: refusing to write a handoff record there")
    return state / "handoffs"


# ------------------------------------------------------------------------------------------------------- new

TEMPLATE = """# Handoff: {title}

Version: 1
Created: {created}
Author: {author}
Repository: {repository}
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
    target = default_path(root, state["branch"])
    folder = ensure_state_dir(root)
    supersedes = "none"
    if target.exists():
        if not supersede:
            raise SystemExit(f"error: {target.relative_to(root)} exists: pass --supersede to keep it as history "
                             "and start a new record")
        old_created = parse(target.read_text(encoding="utf-8"))[0].get("Created", "unknown")
        history = folder / "history"
        history.mkdir(mode=0o700, exist_ok=True)
        os.replace(target, history / f"{target.stem}-{old_created.replace(':', '')}.md")
        supersedes = old_created
    if pr is None:
        try:
            r = subprocess.run(["gh", "pr", "view", "--json", "url", "-q", ".url"], cwd=root, capture_output=True,
                               text=True, timeout=30)
            pr = r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else "none"
        except (OSError, subprocess.SubprocessError):
            pr = "unknown (gh unavailable)"
    remote = git(root, "remote").stdout.split()
    dirty = "".join(f"\n- {p}" for p in state["dirty"])
    target.write_text(TEMPLATE.format(
        title=title, created=stamp(utcnow()), author=author, repository=remote[0] if remote else "none (local only)",
        branch=state["branch"], head=state["head"], upstream=state["upstream"], worktree=state["worktree"], pr=pr,
        claim=claim or "none", transfer=transfer or "none", supersedes=supersedes, dirty=dirty), encoding="utf-8")
    return target


# ----------------------------------------------------------------------------------------------------- check

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


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


def check(path: Path, root: Path) -> tuple[str, list[str]]:
    """(verdict, lines): verdict is matches, drift or invalid. Read-only."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return "invalid", [f"problem: {path} cannot be read: {e}"]
    rec = module("operational_records")
    checker = rec.Checker(rec.load_formats())
    problems = checker.check_text(text, path.name)
    if problems:
        return "invalid", [f"problem: {p}" for p in problems]
    headers, sections = parse(text)
    out, drift = [], False

    def finding(line: str) -> None:
        nonlocal drift
        drift = True
        out.append(f"drift: {line}")
    now = repo_state(root)
    if headers["Branch"] != now["branch"]:
        finding(f"recorded on branch {headers['Branch']}, the checkout is on {now['branch']}")
    recorded = headers["HEAD"]
    if recorded != now["head"]:
        if git(root, "cat-file", "-e", f"{recorded}^{{commit}}").returncode != 0:
            finding(f"recorded HEAD {recorded[:12]} does not exist here (rewritten history, or not fetched)")
        elif git(root, "merge-base", "--is-ancestor", recorded, now["head"]).returncode == 0:
            n = git(root, "rev-list", "--count", f"{recorded}..{now['head']}").stdout.strip()
            finding(f"{n} commits since the record (HEAD {now['head'][:12]}): re-verify what depends on them")
        else:
            finding(f"HEAD {now['head'][:12]} does not descend from the recorded {recorded[:12]}")
    for key, value in (("Upstream", now["upstream"]), ("Working tree", now["worktree"])):
        if headers[key] != value:
            finding(f"{key.lower()} was '{headers[key]}', now '{value}'")
    recorded_dirty = {line[2:].strip() for line in sections.get("State", []) if line.startswith("- ")}
    if headers["Working tree"].startswith("dirty") and now["dirty"] and recorded_dirty != set(now["dirty"]):
        finding(f"the uncommitted paths differ from those listed under State (now: {', '.join(now['dirty'][:5])})")
    for heading, lines in sections.items():
        for line in lines:
            if PLACEHOLDER.search(line) and not line.lstrip().startswith(("```", "{", "[", "\"")):
                finding(f"'## {heading}' still holds a template placeholder: {line.strip()[:70]!r}")
                break
    artifacts = json_block(sections.get("Artifacts", [])) or []
    for a in artifacts:
        kind, ident = a["type"], a["id"]
        if kind == "file":
            target = (root / ident) if not os.path.isabs(ident) else Path(ident)
            if not target.is_file():
                finding(f"artifact {ident} is missing")
            elif sha256_file(target) != a["sha256"]:
                finding(f"artifact {ident} changed (sha256 differs from the record)")
            else:
                out.append(f"ok: artifact {ident} matches its recorded sha256")
        elif kind in ("commit", "tree"):
            if git(root, "cat-file", "-e", ident).returncode != 0:
                finding(f"{kind} {ident[:12]} does not exist here")
            else:
                out.append(f"ok: {kind} {ident[:12]} exists")
        else:
            out.append(f"note: {kind} {ident} is not checked locally: open it before relying on it")
    jobs = json_block(sections.get("Running processes and jobs", [])) or []
    host = socket.gethostname()
    for job in jobs:
        label = f"job {job['id']} ({job['command'][:60]})"
        if job.get("pid") is None:
            out.append(f"note: {label} is not a local process: check it where it runs before deciding anything")
        elif job.get("host", host) != host:
            out.append(f"note: {label} runs on {job['host']}: its state cannot be checked here")
        elif process_start(job["pid"]) == job["process_start"]:
            out.append(f"note: {label} is still running: do not restart, duplicate or stop it; wait or ask")
        else:
            finding(f"{label} has ended since the record: inspect its output and logs before deciding; never rerun "
                    "an expensive job whose inputs are unchanged without checking its results")
    claim = headers.get("Claim", "none")
    if claim != "none" and not CLAIM_ID.match(claim):
        finding(f"'Claim: {claim[:40]}' is not a claim id")
    elif claim != "none":
        file = root / STATE / "claims" / f"{claim}.json"
        if not file.is_file():
            finding(f"claim {claim} is no longer active (released, archived or never made here): acquire anew with "
                    "development-coordination before a disruptive step")
        else:
            try:
                data = rec.strict_json(file.read_text(encoding="utf-8"))
                holder = data["holder"]
                pending = " A transfer is pending: accept it with development-coordination (`accept`)." \
                    if data.get("transfer") else ""
                out.append(f"note: claim {claim} is held by {holder['agent']} (process {holder['pid']}).{pending}")
            except (OSError, ValueError, KeyError, TypeError) as e:
                finding(f"claim {claim} cannot be read: {e}")
    references = json_block(sections["Authorizations in force"]) or []
    if references:
        out.append(f"note: {len(references)} authorization references are unverified until `verify-auth` checks them "
                   "for the operation at hand; only verified grants authority")
    return ("drift" if drift else "matches"), out


# ------------------------------------------------------------------------------------------------ verify-auth

def verify_auth(path: Path, root: Path, action: str, level: str | None, gather=None, policy_source=None,
                now: datetime.datetime | None = None) -> list[tuple[object, str, str, dict]]:
    """[(reference, status, reason, facts)] for every reference in the record, evaluated for one operation. Every
    reference in a structurally invalid record is invalid. Facts are gathered (read-only) even without a trusted
    policy, so the owner sees what the host records; without the policy nothing verifies."""
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
            facts = (gather or facts_mod.gather)(reference, root, owners)
        status, reason = auth.evaluate(reference, {"action": action, **({"level": level} if level else {})}, facts,
                                       policy, now or utcnow())
        out.append((reference, status, reason, facts))
    return out


def describe_facts(facts: dict) -> str:
    if not facts:
        return "no host facts (not a standing reference)"
    if not facts.get("host_reachable"):
        return f"host not reached: {facts.get('why', 'unknown')}"
    approval = facts.get("approval") or {}
    return (f"repository {facts.get('repository')}; commit exists: {facts.get('commit_exists')}; entry found: "
            f"{facts.get('entry_at_reference') is not None}; approval: {approval.get('kind')} by {approval.get('by')} "
            f"({approval.get('state')}, content {approval.get('entry_at_approved_revision')}, introduced by the PR: "
            f"{approval.get('introduced_entry')}); default branch: {facts.get('entry_on_default_branch')}; "
            f"reinstated: {facts.get('reinstated_after_approval')}")


# ---------------------------------------------------------------------------------------------------- summary

def redact(text: str) -> str:
    for pattern, replacement in REDACT:
        text = pattern.sub(replacement, text)
    return text


def summary(path: Path) -> str:
    """Goal, state, done, pending, blockers, verification and limitations, with paths, tokens and addresses removed.
    Authorizations, jobs, claim and transfer details, the author and the repository location are left out."""
    headers, sections = parse(path.read_text(encoding="utf-8"))
    title = path.read_text(encoding="utf-8").split("\n", 1)[0].removeprefix("# Handoff: ")
    out = [f"### Status: {redact(title)}", "", f"From the handoff record of {headers.get('Created', 'unknown')} "
           f"(HEAD `{headers.get('HEAD', '?')[:12]}`, upstream {headers.get('Upstream', 'unknown')}).", ""]
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
            p.add_argument("--transfer-token", default="")
            p.add_argument("--supersede", action="store_true")
        else:
            p.add_argument("file", nargs="?")
        if name == "verify-auth":
            p.add_argument("--action", required=True)
            p.add_argument("--level", choices=("R1", "R2", "R3"))
    args = parser.parse_args(argv)
    root = checkout_root(args.repo)
    if args.command == "new":
        path = new(root, args.title, args.author, args.claim, args.transfer_token, args.supersede)
        print(f"written: {path.relative_to(root)} (fill in every <placeholder>, then run `handoff.py check`)")
        return 0
    path = Path(args.file) if args.file else default_path(root, repo_state(root)["branch"])
    if args.command == "check":
        verdict, lines = check(path, root)
        print(f"verdict: {verdict}")
        for line in lines:
            print(line)
        return {"matches": 0, "drift": 1}.get(verdict, 2)
    if args.command == "verify-auth":
        results = verify_auth(path, root, args.action, args.level)
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
    env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="t",
               GIT_AUTHOR_EMAIL="t@example.invalid", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@example.invalid")
    sleeper = None

    def fail(msg: str) -> None:
        failures.append(msg)

    def run(root: Path, *args: str) -> None:
        subprocess.run(["git", "-C", str(root), *args], env=env, check=True, capture_output=True)

    try:
        root = base / "repo"
        (root / "src").mkdir(parents=True)
        (root / "src" / "parser.py").write_text("x = 1\n")
        run(root, "init", "-q", "-b", "feature/parser")
        run(root, "add", ".")
        run(root, "commit", "-q", "-m", "init")
        saved_env = {k: os.environ.get(k) for k in env if k.startswith("GIT_")}
        os.environ.update({k: v for k, v in env.items() if k.startswith("GIT_")})   # restored in finally
        path = new(root, "Parser refactor", "claude-code / test-model / s1", "", "", False, pr="none")
        if path != root / STATE / "handoffs" / "feature--parser.md":
            fail(f"record path: {path}")
        if git(root, "status", "--porcelain").stdout.strip():
            fail("writing a record made the working tree dirty (the state directory is not self-ignoring)")
        verdict, lines = check(path, root)
        if verdict != "drift" or not any("placeholder" in line for line in lines):
            fail(f"an unfilled template passed: {verdict} {lines}")
        artifact = root / "src" / "parser.py"
        art = [{"type": "file", "id": "src/parser.py", "sha256": sha256_file(artifact)},
               {"type": "commit", "id": git(root, "rev-parse", "HEAD").stdout.strip()},
               {"type": "ci-run", "id": "https://github.com/example/repo/actions/runs/1"}]
        sleeper = subprocess.Popen(["sleep", "300"])
        job = [{"id": "sweep-a", "kind": "process", "command": "sleep 300", "started": stamp(utcnow()),
                "host": socket.gethostname(), "pid": sleeper.pid, "process_start": process_start(sleeper.pid)}]
        body = path.read_text(encoding="utf-8")
        body = fill(body, Artifacts="```json\n" + json.dumps(art, indent=2) + "\n```\n",
                    **{"Running processes and jobs": "```json\n" + json.dumps(job, indent=2) + "\n```\n"})
        path.write_text(body, encoding="utf-8")
        before = tree_digest(root)
        verdict, lines = check(path, root)
        if verdict != "matches":
            fail(f"a filled record of an unchanged repository: {verdict} {lines}")
        if not any("still running" in line for line in lines) or not any("ci-run" in line for line in lines):
            fail(f"job or remote artifact not reported: {lines}")
        if tree_digest(root) != before:
            fail("check changed the repository")
        # Changes since the record are reported, never ignored.
        sleeper.kill()
        sleeper.wait()
        verdict, lines = check(path, root)
        if verdict != "drift" or not any("has ended" in line for line in lines):
            fail(f"an ended job was not reported: {lines}")
        artifact.write_text("x = 2\n")
        verdict, lines = check(path, root)
        if not any("src/parser.py changed" in line for line in lines) or not any("working tree" in line for line in lines):
            fail(f"a changed artifact or working tree was not reported: {lines}")
        dirty_record = path.read_text(encoding="utf-8")
        tampered = dirty_record.replace("Working tree: clean", "Working tree: dirty (1 paths, listed under State)")
        tampered = tampered.replace("Refactor half done; tests pass on HEAD.", "Refactor half done.\n- notes.txt")
        path.write_text(tampered, encoding="utf-8")
        _, lines = check(path, root)
        if not any("uncommitted paths differ" in line for line in lines):
            fail(f"a different set of dirty paths with the same count was not reported: {lines}")
        path.write_text(dirty_record.replace("Upstream: not pushed", "Upstream: ahead 12"), encoding="utf-8")
        _, lines = check(path, root)
        if not any("upstream was 'ahead 12'" in line for line in lines):
            fail(f"a changed upstream was not reported: {lines}")
        path.write_text(dirty_record.replace("Claim: none", "Claim: ../../etc/passwd"), encoding="utf-8")
        _, lines = check(path, root)
        if not any("is not a claim id" in line for line in lines):
            fail(f"a malformed claim id was not reported: {lines}")
        path.write_text(dirty_record, encoding="utf-8")
        run(root, "commit", "-qam", "more work")
        verdict, lines = check(path, root)
        if not any("1 commits since the record" in line for line in lines):
            fail(f"commits since the record were not reported: {lines}")
        artifact.unlink()
        verdict, lines = check(path, root)
        if not any("src/parser.py is missing" in line for line in lines):
            fail(f"a missing artifact was not reported: {lines}")
        run(root, "checkout", "-q", "-b", "other")
        verdict, lines = check(path, root)
        if not any("the checkout is on other" in line for line in lines):
            fail(f"a branch change was not reported: {lines}")
        run(root, "checkout", "-q", "feature/parser")
        # Claims: an active claim with a pending transfer, and a claim that is gone.
        claims = root / STATE / "claims"
        claims.mkdir(parents=True)
        cid = "20261127T184000Z-7f3a1c2b"
        (claims / f"{cid}.json").write_text(json.dumps({"kind": "claim", "holder": {"agent": "claude-code", "pid": 1},
                                                        "transfer": {"token_sha256": "0" * 64}}))
        text = path.read_text(encoding="utf-8").replace("Claim: none", f"Claim: {cid}")
        path.write_text(text, encoding="utf-8")
        _, lines = check(path, root)
        if not any("transfer is pending" in line for line in lines):
            fail(f"a pending transfer was not reported: {lines}")
        (claims / f"{cid}.json").unlink()
        _, lines = check(path, root)
        if not any(f"claim {cid} is no longer active" in line for line in lines):
            fail(f"a vanished claim was not reported: {lines}")
        # Invalid records.
        bad = base / "bad.md"
        bad.write_text(text.replace("## Resume", "## Next"), encoding="utf-8")
        if check(bad, root)[0] != "invalid":
            fail("a record without '## Resume' was not invalid")
        bad.write_text(text.replace("Version: 1", "Version: 2"), encoding="utf-8")
        if check(bad, root)[0] != "invalid":
            fail("an incompatible version was not invalid")
        # Superseding keeps the previous record as history.
        try:
            new(root, "Again", "codex", "", "", False, pr="none")
            fail("an existing record was overwritten without --supersede")
        except SystemExit:
            pass
        old_created = parse(path.read_text(encoding="utf-8"))[0]["Created"]
        time.sleep(1.1)
        again = new(root, "Again", "codex / test-model / s2", "", "", True, pr="none")
        history = list((root / STATE / "handoffs" / "history").glob("*.md"))
        if len(history) != 1 or parse(again.read_text(encoding="utf-8"))[0]["Supersedes"] != old_created:
            fail(f"superseding: history {history}")
        # The PR summary is public-safe.
        leaky = again.read_text(encoding="utf-8")
        leaky = leaky.replace("<one line of status>", "Logs at /home/someone/project/out.log; mail me@example.com; "
                              "copy at C:\\Users\\someone\\out.log; the tokenizer is fixed")
        leaky = leaky.replace("Transfer: none", "Transfer: 0123456789abcdef0123456789abcdef")
        leaky = leaky.replace("- [REPORTED] <what was", "- [REPORTED] session 0123456789abcdef0123456789abcdef <what was")
        again.write_text(leaky, encoding="utf-8")
        text = summary(again)
        for secret in ("/home/someone", "me@example.com", "0123456789abcdef0123456789abcdef", "Transfer",
                       "Authorizations", "Running processes", "codex / test-model", "Users\\someone"):
            if secret in text:
                fail(f"the PR summary leaks {secret!r}")
        if "tokenizer is fixed" not in text:
            fail("the PR summary dropped a line that merely mentions a token-like word")
        if "**Goal**" not in text or "<path>" not in text:
            fail(f"the PR summary lost its content: {text}")
        # Authorization references through the evaluator, with a fake host and an explicit test policy.
        facts_mod, auth = module("github_facts"), module("authorization")
        reference = {"level": "R2", "scope": "Push feature branches", "source": "standing", "by": "github:example-owner",
                     "ref": "ops/authorizations.json@" + "a" * 40 + "#push-feature-branches",
                     "granted": "2026-11-27T18:00:00Z", "expires": "2027-06-30T00:00:00Z"}
        session = {"level": "R2", "scope": "Mark the PR ready", "source": "owner-session", "by": "github:example-owner",
                   "ref": "the previous session", "quote": "mark it ready", "granted": "2026-11-27T18:05:00Z",
                   "expires": "task-end"}
        record = again.read_text(encoding="utf-8").replace(
            "## Authorizations in force\n```json\n[]\n```",
            "## Authorizations in force\n```json\n" + json.dumps([reference, session]) + "\n```")
        again.write_text(record, encoding="utf-8")
        verified_facts = {"host_reachable": True, "repository": "github.com/example/repo", "commit_exists": True,
                          "entry_at_reference": {"id": "push-feature-branches", "level": "R2",
                                                 "operations": "Push feature branches", "actions": ["push-branch"],
                                                 "granted_by": "github:example-owner",
                                                 "approved_in": "https://github.com/example/repo/pull/1",
                                                 "expires": "2027-06-30T00:00:00Z"},
                          "approval": {"kind": "merge", "by": "github:example-owner", "state": "active",
                                       "entry_at_approved_revision": "identical", "introduced_entry": True},
                          "entry_on_default_branch": "identical", "reinstated_after_approval": False}
        test_policy = lambda: ({"owners": ["github:example-owner"], "repositories": ["github.com/example/repo"]}, "test")
        now = datetime.datetime(2026, 11, 28, tzinfo=datetime.timezone.utc)
        results = verify_auth(again, root, "push-branch", None, gather=lambda *a: verified_facts,
                              policy_source=test_policy, now=now)
        if [r[1] for r in results] != ["verified", "unknown"]:
            fail(f"verify-auth with a test policy: {[r[1:3] for r in results]}")
        results = verify_auth(again, root, "publish-release", None, gather=lambda *a: verified_facts,
                              policy_source=test_policy, now=now)
        if results[0][1] != "inapplicable":
            fail(f"verify-auth for another action: {results[0][1:]}")
        results = verify_auth(again, root, "push-branch", None, gather=lambda *a: verified_facts, now=now)
        if any(r[1] == "verified" for r in results) or not results[0][3].get("host_reachable"):
            fail("without the canonical policy, a reference was verified, or its facts were not reported")
        broken = base / "broken.md"
        broken.write_text(record.replace("## Resume", "## Next"), encoding="utf-8")
        results = verify_auth(broken, root, "push-branch", None, gather=lambda *a: verified_facts,
                              policy_source=test_policy, now=now)
        if [r[1] for r in results] != ["invalid", "invalid"]:
            fail(f"references inside an invalid record were not all invalid: {[r[1] for r in results]}")
        broken.write_text(record.replace('"level": "R2"', '"level": "R2", "level": "R1"', 1), encoding="utf-8")
        results = verify_auth(broken, root, "push-branch", None, gather=lambda *a: verified_facts,
                              policy_source=test_policy, now=now)
        if not results or any(r[1] != "invalid" for r in results):
            fail(f"a duplicate JSON key did not make the references invalid: {results}")
        if auth.canonical_policy()[0] is not None:
            fail("a canonical policy appeared before Phase 1d defines one")
        if facts_mod.REMOTE.match("git@github.com:example/repo.git") is None:
            fail("the GitHub adapter does not recognise an SSH remote")
    except Exception as e:  # noqa: BLE001 - an unexpected state is a failure, reported rather than raised
        fail(f"unexpected {type(e).__name__}: {e}")
    finally:
        for k, v in (locals().get("saved_env") or {}).items():
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
