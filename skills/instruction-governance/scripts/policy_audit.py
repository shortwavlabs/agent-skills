#!/usr/bin/env python3
"""Audit, update and roll back the canonical instruction blocks in each agent's instruction file.

    policy_audit.py audit   [--home DIR]                 read-only: drift of every adapter and installed skill
    policy_audit.py diff    --harness H [--home DIR]     read-only: the exact change and its approval digest
    policy_audit.py apply   --harness H --approve DIGEST [--home DIR]
    policy_audit.py rollback --harness H --backup FILE --approve DIGEST [--home DIR]
    policy_audit.py block   ID                           print a canonical block, with its markers, to paste
    policy_audit.py --self-test

One canonical source (references/instructions.md, a generated copy of operational/instructions.md, holding every block
with its id and revision) and one adapter per harness (references/adapters.json says which file and which blocks).
In an adapter, a canonical block sits between markers:

    <!-- policy:begin id=ignore-rules rev=2 sha256=<digest of the block's text> -->
    ...the canonical text, unchanged...
    <!-- policy:end id=ignore-rules -->

Everything outside the markers is the harness's or the owner's own and is never touched. The audit is read-only.
`diff` shows the change and a digest binding it to the file's current bytes; `apply` writes only that exact change,
only with that digest, after keeping a backup, atomically. Nothing is written when markers are missing, duplicated or
unbalanced (the owner places them once, by hand), when the file changed since the diff, or when it is a symlink or
not writable. `rollback` restores a backup the same way. The tool never edits harness settings, installs hooks or
skills, or touches files outside the adapters it was asked about. Standard library only.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REFERENCES = HERE.parent / "references"
BEGIN = re.compile(r"^<!-- policy:begin id=([a-z0-9-]+) rev=(\d+) sha256=([0-9a-f]{64}) -->$")
END = re.compile(r"^<!-- policy:end id=([a-z0-9-]+) -->$")
ANY_MARKER = re.compile(r"<!-- policy:(begin|end)\b")
CANON_BLOCK = re.compile(r"^<!-- block id=([a-z0-9-]+) rev=(\d+) -->\n(.*?)^<!-- end block -->$", re.S | re.M)


def read_json(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["content"] if isinstance(data, dict) and "$generated" in data else data


def unwrap_markdown(text: str) -> str:
    """A generated Markdown copy starts with one header line and a blank line; the canonical text follows."""
    if text.startswith("<!-- Generated from "):
        return text.split("\n", 2)[2]
    return text


def canonical(references: Path = REFERENCES) -> tuple[dict, dict]:
    """(adapter manifest, {block id: (revision, text)}) from the skill's references."""
    manifest = read_json(references / "adapters.json")
    if manifest.get("kind") != "instruction-adapters" or manifest.get("version") != 1:
        raise SystemExit("error: incompatible adapter manifest")
    text = unwrap_markdown((references / "instructions.md").read_text(encoding="utf-8"))
    blocks = {}
    for m in CANON_BLOCK.finditer(text):
        if m.group(1) in blocks:
            raise SystemExit(f"error: canonical block {m.group(1)} is defined twice")
        blocks[m.group(1)] = (int(m.group(2)), m.group(3).rstrip("\n") + "\n")
    missing = {b for a in manifest["adapters"] for b in a["blocks"]} - set(blocks)
    if missing:
        raise SystemExit(f"error: adapters name blocks the canonical source does not define: {sorted(missing)}")
    return manifest, blocks


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def render(block_id: str, revision: int, text: str) -> str:
    return (f"<!-- policy:begin id={block_id} rev={revision} sha256={digest(text)} -->\n{text}"
            f"<!-- policy:end id={block_id} -->\n")


def parse_blocks(text: str) -> tuple[dict, list[str]]:
    """({id: {"rev", "sha", "body", "span": (start, end) line indexes}}, structural problems)."""
    lines = text.split("\n")
    found, problems, open_block = {}, [], None
    for i, line in enumerate(lines):
        b, e = BEGIN.match(line), END.match(line)
        if b:
            if open_block:
                problems.append(f"block {open_block[0]} is not closed before {b.group(1)} begins")
            open_block = (b.group(1), int(b.group(2)), b.group(3), i)
        elif e:
            if not open_block or open_block[0] != e.group(1):
                problems.append(f"an end marker for {e.group(1)} has no matching begin")
                open_block = None
                continue
            bid, rev, sha, start = open_block
            if bid in found:
                problems.append(f"block {bid} appears twice")
            found[bid] = {"rev": rev, "sha": sha, "body": "\n".join(lines[start + 1:i]) + "\n", "span": (start, i)}
            open_block = None
        elif ANY_MARKER.search(line):
            problems.append(f"line {i + 1} holds a malformed policy marker")
    if open_block:
        problems.append(f"block {open_block[0]} is never closed")
    return found, problems


def outside_blocks(text: str) -> str:
    """The text with the content of every marked block removed: what an update must never change."""
    found, problems = parse_blocks(text)
    if problems:
        raise SystemExit("error: markers are malformed: " + "; ".join(problems))
    lines = text.split("\n")
    for b in sorted(found.values(), key=lambda b: b["span"][0], reverse=True):
        start, end = b["span"]
        lines[start:end + 1] = ["<managed block>"]
    return "\n".join(lines)


def adapter_path(adapter: dict, home: Path) -> Path:
    return home / adapter["path"].removeprefix("~/")


def audit_adapter(adapter: dict, blocks: dict, home: Path) -> tuple[str, list[str]]:
    """(state, findings) for one adapter: in-sync, drift, missing-markers, refused or absent."""
    path = adapter_path(adapter, home)
    if path.is_symlink():
        return "refused", [f"{adapter['path']} is a symlink: not audited or written"]
    if not path.exists():
        return "absent", [f"{adapter['path']} does not exist"]
    text = path.read_text(encoding="utf-8")
    found, problems = parse_blocks(text)
    if problems:
        return "refused", problems
    findings, state = [], "in-sync"
    for bid in adapter["blocks"]:
        rev, canon_text = blocks[bid]
        if bid not in found:
            hint = "its canonical text appears verbatim, unmarked" if canon_text.strip() in text else \
                "no marked block, and the canonical text does not appear verbatim"
            findings.append(f"block {bid}: missing markers ({hint}); place them by hand (`block {bid}`)")
            state = "missing-markers"
            continue
        b = found[bid]
        if digest(b["body"]) != b["sha"]:
            findings.append(f"block {bid}: edited by hand since it was installed (its text no longer matches its marker)")
            state = "drift" if state == "in-sync" else state
        elif (b["rev"], b["sha"]) != (rev, digest(canon_text)):
            findings.append(f"block {bid}: outdated (rev {b['rev']}, canonical rev {rev})")
            state = "drift" if state == "in-sync" else state
    for bid in set(found) - set(adapter["blocks"]):
        findings.append(f"block {bid}: not expected in this adapter (left untouched)")
    return state, findings or ["all canonical blocks in sync"]


def proposal(adapter: dict, blocks: dict, home: Path) -> tuple[bytes, bytes, str]:
    """(current bytes, proposed bytes, approval digest). Raises SystemExit when no safe proposal exists."""
    path = adapter_path(adapter, home)
    state, findings = audit_adapter(adapter, blocks, home)
    if state in ("refused", "absent", "missing-markers"):
        raise SystemExit("error: no change can be proposed: " + "; ".join(findings))
    current = path.read_bytes()
    lines = current.decode("utf-8").split("\n")
    found, _ = parse_blocks(current.decode("utf-8"))
    for bid in sorted(adapter["blocks"], key=lambda b: found[b]["span"][0], reverse=True):
        start, end = found[bid]["span"]
        rev, text = blocks[bid]
        lines[start:end + 1] = render(bid, rev, text).rstrip("\n").split("\n")
    proposed = "\n".join(lines).encode("utf-8")
    if outside_blocks(current.decode("utf-8")) != outside_blocks(proposed.decode("utf-8")):
        raise SystemExit("error: the proposal would change text outside the managed blocks: nothing proposed")
    return current, proposed, hashlib.sha256(current + b"\0" + proposed).hexdigest()


def unified(current: bytes, proposed: bytes, name: str) -> str:
    return "".join(difflib.unified_diff(current.decode().splitlines(True), proposed.decode().splitlines(True),
                                        f"{name} (current)", f"{name} (proposed)"))


def backup_dir(home: Path) -> Path:
    return home / ".local" / "state" / "agent-operations" / "instruction-backups"


def write_atomic(path: Path, data: bytes, current: bytes, managed_only: bool = True) -> None:
    """Replace path with data only if it still holds current, and (for updates) only inside managed blocks."""
    if managed_only and outside_blocks(current.decode("utf-8")) != outside_blocks(data.decode("utf-8")):
        raise SystemExit(f"error: the change to {path} reaches outside the managed blocks: nothing written")
    if path.is_symlink() or not os.access(path, os.W_OK):
        raise SystemExit(f"error: {path} is a symlink or not writable: nothing written")
    if path.read_bytes() != current:
        raise SystemExit(f"error: {path} changed since the diff was made: nothing written; run diff again")
    tmp = path.parent / f".{path.name}.tmp-{secrets.token_hex(4)}"
    tmp.write_bytes(data)
    os.chmod(tmp, path.stat().st_mode & 0o777)
    os.replace(tmp, path)


def keep_backup(home: Path, harness: str, data: bytes) -> Path:
    folder = backup_dir(home)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = folder / f"{harness}-{hashlib.sha256(data).hexdigest()[:16]}.md"
    if not target.exists():
        target.write_bytes(data)
        os.chmod(target, 0o600)
    return target


def find_adapter(manifest: dict, harness: str) -> dict:
    for a in manifest["adapters"]:
        if a["harness"] == harness:
            return a
    raise SystemExit(f"error: no adapter for {harness!r}; known: {[a['harness'] for a in manifest['adapters']]}")


def tree_digest(folder: Path) -> str | None:
    if not folder.is_dir():
        return None
    h = hashlib.sha256()
    for p in sorted(folder.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            h.update(p.relative_to(folder).as_posix().encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()


def audit_skills(manifest: dict, home: Path, repo_skills: Path | None) -> list[str]:
    """Installed copies of this repository's skills: in sync, different, or not installed. Read-only."""
    out = []
    if repo_skills is None or not repo_skills.is_dir():
        return ["skills: this repository's skills are not available here; installed copies not compared"]
    for skill in sorted(p.name for p in repo_skills.iterdir() if (p / "SKILL.md").exists()):
        want = tree_digest(repo_skills / skill)
        for root in manifest.get("skill_roots", []):
            have = tree_digest(home / root.removeprefix("~/") / skill)
            if have is not None:
                out.append(f"skill {skill} in {root}: " + ("in sync" if have == want else "differs from this repository"))
    return out or ["skills: no installed copies of this repository's skills found"]


def gh_user() -> tuple[str, int] | None:
    """(login, stable account id) of the account this machine's gh is authenticated as, or None."""
    try:
        r = subprocess.run(["gh", "api", "user", "--jq", ".login + \" \" + (.id|tostring)"], capture_output=True,
                           text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    parts = r.stdout.split()
    return (parts[0], int(parts[1])) if r.returncode == 0 and len(parts) == 2 and parts[1].isdigit() else None


def credential_check(owner_ids: list[int] | None, user=gh_user) -> str:
    """Whether this machine's GitHub CLI is authenticated as an owner's account, compared by stable id (read-only)."""
    found = user()
    if found is None:
        return "credentials: gh is not available or not authenticated here; nothing to check"
    login, account = found
    if owner_ids is None:
        return (f"credentials: gh is authenticated as github:{login} (id {account}). No trust policy is installed; if "
                "this is the owner's account, agents on this machine can approve and merge as the owner")
    if account in owner_ids:
        return (f"credentials: gh is authenticated as an owner's account (github:{login}, id {account}): approvals made "
                "with it here cannot be told apart from the owner's; agents must not approve or merge authority "
                "changes with it")
    return f"credentials: gh is authenticated as github:{login} (id {account}), not an owner's account"


# ------------------------------------------------------------------------------------------------- self-test

def self_test() -> list[str]:
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        refs = base / "references"
        refs.mkdir()
        (refs / "instructions.md").write_text(
            "<!-- Generated from operational/instructions.md (revision 2, sha256 " + "0" * 64 + "). Do not edit this "
            "copy: change the source and regenerate. -->\n\n# Canonical\n\nRevision: 2\n\n"
            "<!-- block id=git-workflow rev=1 -->\n- Work in the primary checkout.\n<!-- end block -->\n\n"
            "<!-- block id=ignore-rules rev=2 -->\n- Never force-add ignored files.\n<!-- end block -->\n")
        manifest = {"kind": "instruction-adapters", "version": 1,
                    "adapters": [{"harness": "codex", "path": "~/.codex/AGENTS.md",
                                  "blocks": ["git-workflow", "ignore-rules"]}],
                    "skill_roots": ["~/.agents/skills"]}
        (refs / "adapters.json").write_text(json.dumps(manifest))
        man, blocks = canonical(refs)
        home = base / "home"
        adapter = find_adapter(man, "codex")
        target = adapter_path(adapter, home)
        target.parent.mkdir(parents=True)
        own = "## Tool notes\nPrefer the docs tool.\n\n"
        old_rules = render("ignore-rules", 1, "- Old wording.\n")
        target.write_text(own + render("git-workflow", 1, blocks["git-workflow"][1]) + "\n" + old_rules + "\n## Mine\nKeep.\n")
        state, findings = audit_adapter(adapter, blocks, home)
        if state != "drift" or not any("ignore-rules: outdated" in f for f in findings):
            failures.append(f"an outdated block was not reported: {state} {findings}")
        before = target.read_bytes()
        current, proposed, approval = proposal(adapter, blocks, home)
        if target.read_bytes() != before:
            failures.append("diff modified the adapter")
        if b"Never force-add" not in proposed or not proposed.startswith(own.encode()) or b"## Mine\nKeep.\n" not in proposed:
            failures.append("the proposal changed text outside the markers or missed the block")
        # apply: only the exact digest, only if unchanged, with a backup
        def apply(digest_given):
            cur, prop, appr = proposal(adapter, blocks, home)
            if digest_given != appr:
                raise SystemExit("error: the approval digest does not match this change")
            keep_backup(home, "codex", cur)
            write_atomic(target, prop, cur)
        try:
            apply("0" * 64)
            failures.append("a wrong approval digest was accepted")
        except SystemExit:
            pass
        if target.read_bytes() != before:
            failures.append("a refused apply modified the adapter")
        apply(approval)
        if target.read_bytes() != proposed or audit_adapter(adapter, blocks, home)[0] != "in-sync":
            failures.append("an approved apply did not produce the proposal")
        backups = list(backup_dir(home).glob("codex-*.md"))
        if len(backups) != 1 or backups[0].read_bytes() != before:
            failures.append("no exact backup was kept")
        # an update reaching outside the managed blocks is refused, even with a matching current file
        tampered = proposed.replace(b"## Mine\nKeep.\n", b"## Mine\nChanged.\n")
        try:
            write_atomic(target, tampered, target.read_bytes())
            failures.append("a change outside the managed blocks was written")
        except SystemExit:
            pass
        # rollback restores the backup with its own digest
        write_atomic(target, backups[0].read_bytes(), target.read_bytes(), managed_only=False)
        if target.read_bytes() != before:
            failures.append("rollback did not restore the backup")
        # the file changed between diff and apply
        current, proposed, approval = proposal(adapter, blocks, home)
        target.write_bytes(current + b"\nan edit by the owner\n")
        try:
            write_atomic(target, proposed, current)
            failures.append("a file changed since the diff was written")
        except SystemExit:
            pass
        # refusals: missing, duplicated, unbalanced markers; hand edits; symlinks
        for label, text, want in [
                ("missing markers", own + "- Never force-add ignored files.\n", "missing-markers"),
                ("duplicated block", render("git-workflow", 1, "x\n") * 2 + render("ignore-rules", 2, "y\n"), "refused"),
                ("unbalanced markers", "<!-- policy:begin id=git-workflow rev=1 sha256=" + "0" * 64 + " -->\nx\n", "refused"),
                ("malformed marker", "<!-- policy:begin id=Bad -->\n", "refused")]:
            target.write_text(text)
            if audit_adapter(adapter, blocks, home)[0] != want:
                failures.append(f"{label}: expected {want}, got {audit_adapter(adapter, blocks, home)}")
            try:
                proposal(adapter, blocks, home)
                failures.append(f"{label}: a change was proposed")
            except SystemExit:
                pass
        target.write_text(render("git-workflow", 1, blocks["git-workflow"][1]).replace("primary", "secondary")
                          + render("ignore-rules", 2, blocks["ignore-rules"][1]))
        if not any("edited by hand" in f for f in audit_adapter(adapter, blocks, home)[1]):
            failures.append("a hand edit inside a block was not reported")
        real = base / "real.md"
        real.write_text("x")
        target.unlink()
        target.symlink_to(real)
        if audit_adapter(adapter, blocks, home)[0] != "refused":
            failures.append("a symlinked adapter was not refused")
        # installed skills
        repo_skills = base / "skills"
        (repo_skills / "demo").mkdir(parents=True)
        (repo_skills / "demo" / "SKILL.md").write_text("---\nname: demo\n---\n")
        installed = home / ".agents" / "skills" / "demo"
        installed.mkdir(parents=True)
        (installed / "SKILL.md").write_text("---\nname: demo\n---\nold\n")
        if not any("differs" in line for line in audit_skills(man, home, repo_skills)):
            failures.append("a differing installed skill was not reported")
        shutil.copy(repo_skills / "demo" / "SKILL.md", installed / "SKILL.md")
        if not any("in sync" in line for line in audit_skills(man, home, repo_skills)):
            failures.append("an installed skill in sync was not reported")
        # credential separation, compared by stable account id, never by login
        for label, user, ids, fragment in [
                ("an owner's account", lambda: ("example-owner", 42), [42], "an owner's account"),
                ("the owner's login on another account", lambda: ("example-owner", 1001), [42], "not an owner's account"),
                ("a renamed owner account", lambda: ("renamed", 42), [42], "an owner's account"),
                ("no trust policy", lambda: ("example-owner", 42), None, "No trust policy is installed"),
                ("gh unavailable", lambda: None, [42], "nothing to check")]:
            if fragment not in credential_check(ids, user):
                failures.append(f"credential check, {label}: {credential_check(ids, user)}")
    return failures


def main(argv: list[str]) -> int:
    if argv == ["--self-test"]:
        failures = self_test()
        for f in failures:
            print("FAIL:", f)
        print("policy_audit self-test: " + ("PASS" if not failures else f"{len(failures)} FAILED"))
        return 1 if failures else 0
    parser = argparse.ArgumentParser(prog="policy_audit.py", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("audit", "diff", "apply", "rollback", "block"):
        p = sub.add_parser(name)
        p.add_argument("--home", default=str(Path.home()))
        if name in ("diff", "apply", "rollback"):
            p.add_argument("--harness", required=True)
        if name in ("apply", "rollback"):
            p.add_argument("--approve", required=True)
        if name == "rollback":
            p.add_argument("--backup", required=True)
        if name == "block":
            p.add_argument("id")
    args = parser.parse_args(argv)
    manifest, blocks = canonical()
    home = Path(args.home)
    if args.command == "block":
        rev, text = blocks[args.id]
        print(render(args.id, rev, text), end="")
        return 0
    if args.command == "audit":
        worst = 0
        for adapter in manifest["adapters"]:
            state, findings = audit_adapter(adapter, blocks, home)
            print(f"{adapter['harness']} ({adapter['path']}): {state}")
            for f in findings:
                print(f"  {f}")
            worst = max(worst, {"in-sync": 0, "absent": 0, "drift": 1, "missing-markers": 1, "refused": 2}[state])
        repo_skills = HERE.parent.parent if (HERE.parent.parent.parent / "operational").is_dir() else None
        for line in audit_skills(manifest, home, repo_skills):
            print(line)
        policy = None
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("trust_policy_copy", HERE / "trust_policy.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            loaded, _ = mod.load()
            policy = list(loaded["owner_account_ids"].values()) if loaded else None
        except (OSError, ImportError, AttributeError):
            policy = None
        print(credential_check(policy))
        return worst
    adapter = find_adapter(manifest, args.harness)
    path = adapter_path(adapter, home)
    if args.command == "diff":
        current, proposed, approval = proposal(adapter, blocks, home)
        print(unified(current, proposed, adapter["path"]) or "no change: the adapter is in sync")
        print(f"approval digest: {approval}")
        return 0
    if args.command == "apply":
        current, proposed, approval = proposal(adapter, blocks, home)
        if args.approve != approval:
            raise SystemExit("error: the approval digest does not match this change: run diff again and review it")
        kept = keep_backup(home, adapter["harness"], current)
        write_atomic(path, proposed, current)
        print(f"applied to {adapter['path']}; previous version kept at {kept}")
        return 0
    backup = Path(args.backup)
    if backup.parent.resolve() != backup_dir(home).resolve() or not backup.is_file() or backup.is_symlink():
        raise SystemExit("error: the backup must be a file in the instruction backup directory")
    current, restored = path.read_bytes(), backup.read_bytes()
    approval = hashlib.sha256(current + b"\0" + restored).hexdigest()
    if args.approve != approval:
        print(unified(current, restored, adapter["path"]))
        raise SystemExit(f"error: approve this rollback with --approve {approval}")
    keep_backup(home, adapter["harness"], current)
    write_atomic(path, restored, current, managed_only=False)
    print(f"restored {adapter['path']} from {backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
