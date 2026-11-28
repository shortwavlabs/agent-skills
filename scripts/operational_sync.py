#!/usr/bin/env python3
"""Generated copies of shared operational files: one authoritative source, byte-identical copies (RFC 0001, D4).

    python3 scripts/operational_sync.py            read-only check, the default (CI runs this)
    python3 scripts/operational_sync.py --diff     read-only: show what --write would change
    python3 scripts/operational_sync.py --write    write the missing, edited and outdated copies
    python3 scripts/operational_sync.py --self-test

`operational/copies.json` lists each source and the paths of its copies. A copy is exactly one generated header line,
naming the source, its revision and its SHA-256, then a blank line, then the source text unchanged. The check reports
copies that are missing, edited or outdated (generated from another revision or digest), and unlisted files that carry
a generated header. Every copy must be a plain relative path under `skills/` that resolves without passing through a
symlink; anything else is refused. `--write` never touches an unlisted or refused file, never creates a missing
directory, and writes copies with mode 0644.
Markdown sources only. Standard library only.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = "operational/copies.json"
HEADER = ("<!-- Generated from {source} (revision {revision}, sha256 {digest}). Do not edit this copy: change the source "
          "and regenerate. -->")
HEADER_RE = re.compile(r"^<!-- Generated from (\S+) \(revision (\d+), sha256 ([0-9a-f]{64})\)\. Do not edit")


def expected_copy(source: str, text: str) -> tuple[str | None, str | None]:
    """(copy text, None) for a source, or (None, reason)."""
    m = re.search(r"^Revision: (\d+)$", text, re.M)
    if not m:
        return None, f"{source}: no 'Revision: N' line"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return HEADER.format(source=source, revision=m.group(1), digest=digest) + "\n\n" + text, None


def plan(root: Path) -> tuple[list[str], list[tuple[Path, str]]]:
    """(problems, writes): every problem the check reports, and the (path, text) pairs --write would write."""
    problems: list[str] = []
    writes: list[tuple[Path, str]] = []
    try:
        manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return [f"{MANIFEST}: cannot be read: {e}"], []
    if not isinstance(manifest, dict) or manifest.get("kind") != "copies" or manifest.get("version") != 1:
        return [f"{MANIFEST}: incompatible manifest (expected kind 'copies', version 1)"], []
    listed: set[str] = set()
    for entry in manifest.get("sources", []):
        source, copies = entry.get("source"), entry.get("copies")
        if not isinstance(source, str) or not isinstance(copies, list) or not all(isinstance(c, str) for c in copies):
            problems.append(f"{MANIFEST}: each entry needs a 'source' path and a 'copies' list of paths")
            continue
        if not source.endswith(".md"):
            problems.append(f"{source}: only Markdown sources are supported")
            continue
        try:
            text = (root / source).read_text(encoding="utf-8")
        except OSError as e:
            problems.append(f"{source}: source cannot be read: {e}")
            continue
        want, why = expected_copy(source, text)
        if want is None:
            problems.append(why)
            continue
        current_header = want.split("\n", 1)[0]
        for copy in copies:
            listed.add(copy)
            path = root / copy
            parts = Path(copy).parts
            if (Path(copy).is_absolute() or ".." in parts or parts[:1] != ("skills",)
                    or path.resolve() != root.resolve() / copy):
                problems.append(f"refused: {copy} (a copy must be a plain path under skills/, not through a symlink)")
            elif not path.exists():
                problems.append(f"missing: {copy}")
                writes.append((path, want))
            else:
                have = path.read_text(encoding="utf-8")
                if have == want:
                    continue
                first = have.split("\n", 1)[0]
                m = HEADER_RE.match(first)
                if m and m.group(1) == source and first != current_header:
                    problems.append(f"outdated: {copy} (generated from revision {m.group(2)}, sha256 "
                                    f"{m.group(3)[:12]}…; the source is now {current_header.split('(', 1)[1][:30]}…)")
                else:
                    problems.append(f"edited: {copy} (differs from the generated copy of {source})")
                writes.append((path, want))
    skills = root / "skills"
    for path in sorted(skills.rglob("*.md")) if skills.is_dir() else []:
        rel = path.relative_to(root).as_posix()
        if rel not in listed:
            with path.open(encoding="utf-8") as fh:
                if HEADER_RE.match(fh.readline()):
                    problems.append(f"unlisted: {rel} carries a generated header but is not listed in {MANIFEST}")
    return problems, writes


def write(writes: list[tuple[Path, str]]) -> list[str]:
    """Write each copy atomically. Refuses (and reports) when the directory does not exist."""
    refused = []
    for path, text in writes:
        if not path.parent.is_dir():
            refused.append(f"not written: {path} (its directory does not exist; create the skill first)")
            continue
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".operational-sync-")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(tmp, 0o644)              # mkstemp creates 0600; copies are ordinary repository files
        os.replace(tmp, path)
    return refused


def diff(writes: list[tuple[Path, str]], root: Path) -> str:
    out = []
    for path, text in writes:
        have = path.read_text(encoding="utf-8") if path.exists() else ""
        rel = path.relative_to(root).as_posix()
        out += difflib.unified_diff(have.splitlines(True), text.splitlines(True), f"a/{rel}", f"b/{rel}")
    return "".join(out)


# ---------------------------------------------------------------------------------------------------------- self-test

def self_test() -> list[str]:
    """Explicit checks, not assert, so it also runs under python -O."""
    failures: list[str] = []
    root = Path(tempfile.mkdtemp(prefix="operational-sync-"))
    try:
        (root / "operational").mkdir()
        for skill in ("a", "b", "c"):
            (root / "skills" / skill / "references").mkdir(parents=True)
        source = root / "operational" / "core.md"
        source.write_text("# Core\n\nRevision: 1\n\nRule one.\n", encoding="utf-8")
        copies = ["skills/a/references/operational-core.md", "skills/b/references/operational-core.md"]
        (root / MANIFEST).write_text(json.dumps({"kind": "copies", "version": 1, "sources": [
            {"source": "operational/core.md", "copies": copies}]}), encoding="utf-8")
        a, b = root / copies[0], root / copies[1]

        def expect(label: str, fragments: list[str]) -> None:
            problems, _ = plan(root)
            missing = [f for f in fragments if not any(f in p for p in problems)]
            if missing or (not fragments and problems):
                failures.append(f"{label}: expected {fragments or 'no problems'}, got {problems}")

        expect("fresh tree", [f"missing: {copies[0]}", f"missing: {copies[1]}"])
        if a.exists() or b.exists():
            failures.append("the check wrote files: it must be read-only")
        refused = write(plan(root)[1])
        if refused:
            failures.append(f"write refused unexpectedly: {refused}")
        expect("after --write", [])
        if not a.read_text(encoding="utf-8").startswith("<!-- Generated from operational/core.md (revision 1, sha256 "):
            failures.append("a copy does not start with the generated header")
        if not a.read_text(encoding="utf-8").endswith(source.read_text(encoding="utf-8")):
            failures.append("a copy does not end with the unchanged source text")
        if a.stat().st_mode & 0o777 != 0o644:
            failures.append(f"a written copy has mode {a.stat().st_mode & 0o777:o}, expected 644")

        # Drift: an edited copy.
        a.write_text(a.read_text(encoding="utf-8").replace("Rule one.", "Rule one, relaxed."), encoding="utf-8")
        expect("edited copy", [f"edited: {copies[0]}"])
        if "+Rule one." not in diff(plan(root)[1], root):
            failures.append("--diff does not show the restoring change")
        write(plan(root)[1])
        expect("edited copy rewritten", [])

        # Drift: an edited header is also an edit, not a silent pass.
        a.write_text(a.read_text(encoding="utf-8").replace("Do not edit this copy", "Edit freely"), encoding="utf-8")
        expect("edited header", [f"edited: {copies[0]}"])
        write(plan(root)[1])

        # Drift: a new source revision makes every copy outdated.
        source.write_text("# Core\n\nRevision: 2\n\nRule one.\nRule two.\n", encoding="utf-8")
        expect("new revision", [f"outdated: {copies[0]} (generated from revision 1",
                                f"outdated: {copies[1]} (generated from revision 1"])
        write(plan(root)[1])
        expect("after regenerating", [])
        # A source change without a revision bump is still caught by the digest.
        source.write_text("# Core\n\nRevision: 2\n\nRule one.\nRule two, changed.\n", encoding="utf-8")
        expect("same revision, new digest", [f"outdated: {copies[0]}"])
        write(plan(root)[1])

        # Unlisted generated file: reported, never written.
        stray = root / "skills" / "c" / "references" / "operational-core.md"
        stray.write_text(a.read_text(encoding="utf-8"), encoding="utf-8")
        expect("unlisted copy", ["unlisted: skills/c/references/operational-core.md"])
        before = stray.read_text(encoding="utf-8")
        write(plan(root)[1])
        if stray.read_text(encoding="utf-8") != before:
            failures.append("--write modified an unlisted file")
        stray.unlink()

        # Copies that are symlinks, sit under a symlinked directory or leave skills/ are refused, never written.
        outside = Path(tempfile.mkdtemp(prefix="operational-sync-outside-"))
        try:
            (root / "skills" / "d").symlink_to(outside, target_is_directory=True)
            (outside / "references").mkdir()
            b.unlink()
            b.symlink_to(a)
            bad = ["skills/b/references/operational-core.md", "skills/d/references/operational-core.md",
                   str(outside / "absolute.md"), "../escape.md", "skills/../operational/escape.md", "operational/x.md"]
            (root / MANIFEST).write_text(json.dumps({"kind": "copies", "version": 1, "sources": [
                {"source": "operational/core.md", "copies": bad}]}), encoding="utf-8")
            problems, writes = plan(root)
            for copy in bad:
                if not any(p.startswith(f"refused: {copy} ") for p in problems):
                    failures.append(f"copy path {copy!r} was not refused: {problems}")
            write(writes)
            if writes or any(outside.rglob("*.md")) or (root.parent / "escape.md").exists():
                failures.append(f"--write wrote outside skills/ or through a symlink: {writes}")
        finally:
            shutil.rmtree(outside, ignore_errors=True)
        (root / "skills" / "d").unlink()
        b.unlink()
        (root / MANIFEST).write_text(json.dumps({"kind": "copies", "version": 1, "sources": [
            {"source": "operational/core.md", "copies": copies}]}), encoding="utf-8")

        # A missing directory is never created.
        shutil.rmtree(root / "skills" / "b")
        refused = write(plan(root)[1])
        if not refused or (root / "skills" / "b").exists():
            failures.append("--write created a missing directory")

        # Malformed inputs.
        source.write_text("# Core\n\nNo revision line.\n", encoding="utf-8")
        expect("source without revision", ["no 'Revision: N' line"])
        (root / MANIFEST).write_text(json.dumps({"kind": "copies", "version": 2, "sources": []}), encoding="utf-8")
        expect("incompatible manifest", ["incompatible manifest"])
        (root / MANIFEST).write_text("{", encoding="utf-8")
        expect("unreadable manifest", ["cannot be read"])
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return failures


def main() -> int:
    args = sys.argv[1:]
    if args == ["--self-test"]:
        failures = self_test()
        for f in failures:
            print("FAIL:", f)
        print("operational_sync self-test: " + ("PASS" if not failures else f"{len(failures)} FAILED"))
        return 1 if failures else 0
    if args not in ([], ["--diff"], ["--write"]):
        print(__doc__.strip().split("\n\n")[1], file=sys.stderr)
        return 2
    problems, writes = plan(ROOT)
    if args == ["--diff"]:
        sys.stdout.write(diff(writes, ROOT))
    elif args == ["--write"]:
        for line in write(writes):
            print(line)
        problems, _ = plan(ROOT)
    for p in problems:
        print("FAIL:", p)
    print("generated copies: " + ("in sync" if not problems else f"{len(problems)} PROBLEMS"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
