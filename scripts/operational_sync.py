#!/usr/bin/env python3
"""Generated copies of shared operational files: one authoritative source, byte-identical copies (RFC 0001, D4).

    python3 scripts/operational_sync.py            read-only check, the default (CI runs this)
    python3 scripts/operational_sync.py --diff     read-only: show what --write would change
    python3 scripts/operational_sync.py --write    write the missing, edited and outdated copies
    python3 scripts/operational_sync.py --self-test

Trust boundary:
- Sources come only from APPROVED below, which is reviewed code. Each approved source has exactly one designated
  destination name, and its copies may only live at `skills/<skill>/references/<that name>`. Extending the list is a
  reviewed change (Phase 1b adds the in-use check).
- `operational/copies.json` only says which skills receive which approved source. It is validated completely (kind,
  integer version, exact keys, types, approved sources, designated destinations, no duplicates, no absolute paths, no
  `..`, no symlink anywhere on a path) before anything is written, and any such problem blocks every write.
- A copy is exactly one generated header line naming the source, its revision and its SHA-256, a blank line, then
  the source bytes unchanged. Comparison is byte for byte: line-ending, BOM or final-newline changes are edits.
- An existing file that does not carry this source's generated header is never overwritten.
- `--write` revalidates each path immediately before an atomic replacement, and writes mode 0644. The check and
  `--diff` never modify anything.
Standard library only.
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
APPROVED = {"operational/core.md": "operational-core.md"}       # source -> its designated destination name
HEADER = ("<!-- Generated from {source} (revision {revision}, sha256 {digest}). Do not edit this copy: change the source "
          "and regenerate. -->")
HEADER_RE = re.compile(rb"^<!-- Generated from (\S+) \(revision (\d+), sha256 ([0-9a-f]{64})\)\. Do not edit")
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def plain_path(root: Path, rel) -> bool:
    """A canonical repository-relative path (no absolute part, no `.`, `..` or empty segment) with no symlink on it."""
    if (not isinstance(rel, str) or not rel or Path(rel).is_absolute() or ".." in Path(rel).parts or "\\" in rel
            or rel != Path(rel).as_posix()):
        return False
    return (root / rel).resolve() == root.resolve() / rel


def strict_json(text: str):
    """json.loads that rejects duplicate keys: a second 'sources' or 'copies' must not silently win."""
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError(f"duplicate key {key!r}")
            out[key] = value
        return out
    return json.loads(text, object_pairs_hook=pairs)


def generated_header_source(path: Path) -> str | None:
    """The source a file's generated header names, or None."""
    with path.open("rb") as fh:
        m = HEADER_RE.match(fh.readline())
    return m.group(1).decode("utf-8", "replace") if m else None


def expected_copy(source: str, data: bytes) -> tuple[bytes | None, str | None]:
    """(copy bytes, None) for a source's bytes, or (None, reason)."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None, f"{source}: not UTF-8"
    m = re.search(r"^Revision: (\d+)$", text, re.M)
    if not m:
        return None, f"{source}: no 'Revision: N' line"
    header = HEADER.format(source=source, revision=m.group(1), digest=hashlib.sha256(data).hexdigest())
    return header.encode("utf-8") + b"\n\n" + data, None


def validate_manifest(root: Path) -> tuple[list[str], list[tuple[str, str]]]:
    """(structural problems, [(source, destination)])."""
    try:
        manifest = strict_json((root / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return [f"{MANIFEST}: cannot be read: {e}"], []
    if (not isinstance(manifest, dict) or manifest.get("kind") != "copies"
            or type(manifest.get("version")) is not int or manifest.get("version") != 1):
        return [f"{MANIFEST}: incompatible manifest (expected kind 'copies', integer version 1)"], []
    problems, pairs = [], []
    extra = set(manifest) - {"kind", "version", "about", "sources"}
    if extra:
        problems.append(f"{MANIFEST}: unexpected keys {sorted(extra)}")
    if not isinstance(manifest.get("sources"), list):
        return problems + [f"{MANIFEST}: 'sources' must be a list"], []
    seen_sources, seen_destinations = set(), set()
    for i, entry in enumerate(manifest["sources"]):
        where = f"{MANIFEST}: sources[{i}]"
        if not isinstance(entry, dict) or set(entry) != {"source", "copies"}:
            problems.append(f"{where}: each entry has exactly the keys 'source' and 'copies'")
            continue
        source, copies = entry["source"], entry["copies"]
        if not isinstance(source, str) or source not in APPROVED:
            problems.append(f"{where}: source {source!r} is not an approved source {sorted(APPROVED)}")
            continue
        if source in seen_sources:
            problems.append(f"{where}: source {source} is declared twice")
            continue
        seen_sources.add(source)
        if not plain_path(root, source) or not (root / source).is_file():
            problems.append(f"refused: source {source} (missing, not a regular file, or reached through a symlink)")
            continue
        if not isinstance(copies, list):
            problems.append(f"{where}: 'copies' must be a list")
            continue
        for copy in copies:
            parts = Path(copy).parts if isinstance(copy, str) else ()
            if (len(parts) != 4 or parts[0] != "skills" or not SLUG.match(parts[1]) or parts[2] != "references"
                    or parts[3] != APPROVED[source] or not plain_path(root, copy)):
                problems.append(f"refused: {copy!r} (copies of {source} may only be skills/<skill>/references/"
                                f"{APPROVED[source]}, as a plain path, not through a symlink)")
            elif copy in seen_destinations:
                problems.append(f"{where}: destination {copy} is declared twice")
            else:
                seen_destinations.add(copy)
                pairs.append((source, copy))
    return problems, pairs


def plan(root: Path) -> tuple[list[str], list[str], list[tuple[Path, bytes, str]]]:
    """(structural problems, drift problems, writes). Nothing may be written while structural problems exist."""
    structural, pairs = validate_manifest(root)
    drift, writes = [], []
    expected: dict[str, bytes | None] = {}
    for source, copy in pairs:
        if source not in expected:
            expected[source], why = expected_copy(source, (root / source).read_bytes())
            if why:
                structural.append(why)
        want, path = expected[source], root / copy
        if want is None:
            continue
        if not path.exists():
            drift.append(f"missing: {copy}")
            writes.append((path, want, source))
            continue
        if not path.is_file():
            structural.append(f"refused: {copy} exists and is not a regular file")
            continue
        have = path.read_bytes()
        if have == want:
            continue
        found = HEADER_RE.match(have.split(b"\n", 1)[0])
        if not found or found.group(1).decode("utf-8", "replace") != source:
            structural.append(f"unrelated: {copy} exists without a generated header for {source}; refusing to overwrite it")
            continue
        if HEADER_RE.match(want.split(b"\n", 1)[0]).groups()[1:] != found.groups()[1:]:
            drift.append(f"outdated: {copy} (generated from revision {found.group(2).decode()}, sha256 "
                         f"{found.group(3).decode()[:12]}…)")
        else:
            drift.append(f"edited: {copy} (bytes differ from the generated copy of {source})")
        writes.append((path, want, source))
    listed = {copy for _, copy in pairs}
    skills = root / "skills"
    for path in sorted(skills.rglob("*.md")) if skills.is_dir() else []:
        rel = path.relative_to(root).as_posix()
        if rel not in listed and path.is_file() and generated_header_source(path) is not None:
            structural.append(f"unlisted: {rel} carries a generated header but is not listed in {MANIFEST}")
    return structural, drift, writes


def apply(root: Path, writes: list[tuple[Path, bytes, str]]) -> list[str]:
    """Write planned copies, revalidating each path immediately before its atomic replacement. Stops at the first change."""
    for path, data, source in writes:
        rel = path.relative_to(root).as_posix()
        if not plain_path(root, rel) or not path.parent.is_dir():
            return [f"stopped before {rel}: its directory is missing or the path now passes through a symlink"]
        if path.exists() and (not path.is_file() or generated_header_source(path) != source):
            return [f"stopped before {rel}: it is no longer a generated copy of {source}"]
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".operational-sync-")
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, 0o644)              # mkstemp creates 0600; copies are ordinary repository files
        os.replace(tmp, path)
    return []


def write(root: Path) -> list[str]:
    """Write every drifted copy, or nothing at all if any structural problem exists. Returns what blocked or stopped it."""
    structural, _, writes = plan(root)
    if structural:
        return ["nothing written: " + p for p in structural]
    return apply(root, writes)


def diff(root: Path) -> str:
    out = []
    for path, data, _ in plan(root)[2]:
        have = path.read_bytes() if path.exists() else b""
        rel = path.relative_to(root).as_posix()
        out += difflib.unified_diff(have.decode("utf-8", "replace").splitlines(True),
                                    data.decode("utf-8").splitlines(True), f"a/{rel}", f"b/{rel}")
    return "".join(out)


# ---------------------------------------------------------------------------------------------------------- self-test

def tree_digest(root: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        h.update(p.relative_to(root).as_posix().encode() + b"\0")
        if p.is_symlink():
            h.update(b"L" + os.readlink(p).encode())
        elif p.is_file():
            h.update(b"F" + p.read_bytes())
    return h.hexdigest()


def self_test() -> list[str]:
    """Explicit checks, not assert, so it also runs under python -O. Every fixture lives under one private directory."""
    failures: list[str] = []
    base = Path(tempfile.mkdtemp(prefix="operational-sync-"))
    root = base / "repo"
    try:
        (root / "operational").mkdir(parents=True)
        for skill in ("a", "b", "c"):
            (root / "skills" / skill / "references").mkdir(parents=True)
        source = root / "operational" / "core.md"
        source.write_bytes(b"# Core\n\nRevision: 1\n\nRule one.\n")
        good = ["skills/a/references/operational-core.md", "skills/b/references/operational-core.md"]
        a, b = root / good[0], root / good[1]

        def manifest(entries=None, **top) -> None:
            data = {"kind": "copies", "version": 1,
                    "sources": entries if entries is not None else [{"source": "operational/core.md", "copies": good}]}
            data.update(top)
            (root / MANIFEST).write_text(json.dumps(data), encoding="utf-8")

        def expect(label: str, fragments: list[str], *, structural: bool | None = None) -> None:
            s, d, _ = plan(root)
            problems = s + d
            missing = [f for f in fragments if not any(f in p for p in problems)]
            if missing or (not fragments and problems) or (structural is not None and bool(s) != structural):
                failures.append(f"{label}: expected {fragments or 'no problems'}, got structural {s}, drift {d}")

        manifest()
        before = tree_digest(base)
        expect("fresh tree", [f"missing: {good[0]}", f"missing: {good[1]}"], structural=False)
        diff(root)
        if tree_digest(base) != before:
            failures.append("the check or --diff modified the tree")
        if write(root):
            failures.append("write refused on a clean manifest")
        expect("after --write", [])
        want = (HEADER.format(source="operational/core.md", revision=1, digest=hashlib.sha256(source.read_bytes()).hexdigest())
                .encode() + b"\n\n" + source.read_bytes())
        if a.read_bytes() != want:
            failures.append("a copy is not byte-identical to header, blank line and source bytes")
        if a.stat().st_mode & 0o777 != 0o644:
            failures.append(f"a written copy has mode {a.stat().st_mode & 0o777:o}, expected 644")

        # Byte identity, not normalized text equality.
        original = a.read_bytes()
        for label, mutated in [("CRLF line endings", original.replace(b"\n", b"\r\n")),
                               ("no final newline", original.rstrip(b"\n")),
                               ("an edited body", original.replace(b"Rule one.", b"Rule one, relaxed."))]:
            a.write_bytes(mutated)
            expect(f"copy with {label}", [f"edited: {good[0]}"], structural=False)
        # A BOM hides the header: the file is no longer recognizably generated, so it is refused, not overwritten.
        a.write_bytes(b"\xef\xbb\xbf" + original)
        expect("copy with a BOM", [f"unrelated: {good[0]}"], structural=True)
        a.write_bytes(original.replace(b"Rule one.", b"Rule one, relaxed."))
        if "+Rule one." not in diff(root):
            failures.append("--diff does not show the restoring change")
        write(root)
        expect("edited copy rewritten", [])

        # Outdated: a new revision, and a changed source without a revision bump (caught by the digest).
        source.write_bytes(b"# Core\n\nRevision: 2\n\nRule one.\nRule two.\n")
        expect("new revision", [f"outdated: {good[0]} (generated from revision 1"], structural=False)
        write(root)
        source.write_bytes(b"# Core\n\nRevision: 2\n\nRule one.\nRule two, changed.\n")
        expect("same revision, new digest", [f"outdated: {good[0]}"])
        write(root)
        expect("regenerated", [])

        # An existing unrelated file is never overwritten, and it blocks every write.
        b.write_bytes(b"# Hand-written notes\n")
        a.unlink()
        expect("unrelated destination", [f"unrelated: {good[1]}"], structural=True)
        blocked = write(root)
        if not blocked or a.exists() or b.read_bytes() != b"# Hand-written notes\n":
            failures.append(f"--write overwrote an unrelated file or wrote despite a structural problem: {blocked}")
        b.unlink()
        write(root)

        # Unlisted generated file: reported, blocks writes, never touched.
        stray = root / "skills" / "c" / "references" / "operational-core.md"
        stray.write_bytes(a.read_bytes())
        expect("unlisted copy", ["unlisted: skills/c/references/operational-core.md"], structural=True)
        stray.unlink()

        # Revalidation: a file appears at a planned destination after the plan, before the write.
        a.unlink()
        _, _, writes = plan(root)
        a.write_bytes(b"# Created by someone else in the meantime\n")
        if not apply(root, writes) or a.read_bytes() != b"# Created by someone else in the meantime\n":
            failures.append("--write overwrote a file created after the plan")
        a.unlink()
        write(root)

        # Destinations: designated name, location and symlink rules; duplicates.
        outside = base / "outside"
        (outside / "references").mkdir(parents=True)
        (root / "skills" / "d").symlink_to(outside, target_is_directory=True)
        b.unlink()
        b.symlink_to(a)
        bad = ["skills/b/references/operational-core.md", "skills/d/references/operational-core.md",
               str(outside / "references" / "operational-core.md"), "../escape/references/operational-core.md",
               "skills/../operational/operational-core.md", "skills/a/references/notes.md",
               "skills/a/operational-core.md", "skills/A/references/operational-core.md", "operational/x.md", 7,
               "skills/./c/references/operational-core.md", "skills//c/references/operational-core.md",
               "skills/c/references/operational-core.md/"]
        manifest([{"source": "operational/core.md", "copies": bad}])
        before = tree_digest(base)
        expect("refused destinations", [f"refused: {c!r}" for c in bad], structural=True)
        write(root)
        if tree_digest(base) != before:
            failures.append("--write changed something despite refused destinations")
        (root / "skills" / "d").unlink()
        b.unlink()
        manifest([{"source": "operational/core.md", "copies": [good[0], good[0]]}])
        expect("duplicate destination", [f"destination {good[0]} is declared twice"], structural=True)
        manifest([{"source": "operational/core.md", "copies": [good[0]]},
                  {"source": "operational/core.md", "copies": [good[1]]}])
        expect("source declared twice", ["source operational/core.md is declared twice"], structural=True)

        # Sources: only approved, plain, regular files inside the repository.
        for label, src in [("traversal", "../core.md"), ("inner traversal", "operational/../operational/core.md"),
                           ("absolute", str(source)), ("not approved", "operational/other.md"), ("non-string", 3)]:
            manifest([{"source": src, "copies": [good[0]]}])
            expect(f"source {label}", ["is not an approved source"], structural=True)
        elsewhere = base / "elsewhere.md"
        elsewhere.write_bytes(source.read_bytes())
        source.rename(root / "operational" / "core.real.md")
        source.symlink_to(elsewhere)
        manifest()
        expect("symlinked source", ["refused: source operational/core.md"], structural=True)
        source.unlink()
        (root / "operational" / "core.real.md").rename(source)
        (root / "operational").rename(root / "operational.real")
        (root / "operational").symlink_to(root / "operational.real", target_is_directory=True)
        expect("symlinked source directory", ["refused: source operational/core.md"], structural=True)
        (root / "operational").unlink()
        (root / "operational.real").rename(root / "operational")

        # Malformed and incompatible manifests: refused before anything is written.
        for label, raw in [("unreadable", "{"), ("not an object", "[]"), ("version 2", {"kind": "copies", "version": 2}),
                           ("version true", {"kind": "copies", "version": True}),
                           ("version 1.0", {"kind": "copies", "version": 1.0}),
                           ("wrong kind", {"kind": "list", "version": 1})]:
            (root / MANIFEST).write_text(raw if isinstance(raw, str) else json.dumps(dict(raw, sources=[])),
                                         encoding="utf-8")
            expect(f"manifest {label}", ["cannot be read" if label == "unreadable" else "incompatible manifest"],
                   structural=True)
        (root / MANIFEST).write_text('{"kind": "copies", "version": 1, "sources": [], "sources": '
                                     '[{"source": "operational/core.md", "copies": []}]}', encoding="utf-8")
        expect("manifest duplicate key", ["duplicate key 'sources'"], structural=True)
        for label, top, fragment in [("extra key", {"extra": 1}, "unexpected keys"),
                                     ("sources not a list", {"sources": {}}, "'sources' must be a list")]:
            manifest(**top)
            expect(f"manifest {label}", [fragment], structural=True)
        for label, entry, fragment in [("entry not an object", "x", "exactly the keys"),
                                       ("extra entry key", {"source": "operational/core.md", "copies": [], "x": 1},
                                        "exactly the keys"),
                                       ("copies not a list", {"source": "operational/core.md", "copies": "a"},
                                        "must be a list")]:
            manifest([entry])
            expect(f"manifest {label}", [fragment], structural=True)
        manifest()
        source.write_bytes(b"# Core\n\nNo revision line.\n")
        expect("source without revision", ["no 'Revision: N' line"], structural=True)
        source.write_bytes(b"Revision: 1\n\xff\xfe\n")
        expect("source not UTF-8", ["not UTF-8"], structural=True)
    finally:
        shutil.rmtree(base, ignore_errors=True)
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
    if args == ["--diff"]:
        sys.stdout.write(diff(ROOT))
    elif args == ["--write"]:
        for line in write(ROOT):
            print(line)
    structural, drift, _ = plan(ROOT)
    for p in structural + drift:
        print("FAIL:", p)
    problems = len(structural) + len(drift)
    print("generated copies: " + ("in sync" if not problems else f"{problems} PROBLEMS"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
