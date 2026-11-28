#!/usr/bin/env python3
"""Generated copies of shared operational files: one authoritative source, byte-identical copies (RFC 0001, D4).

    python3 scripts/operational_sync.py            read-only check, the default (CI runs this)
    python3 scripts/operational_sync.py --diff     read-only: show what --write would change
    python3 scripts/operational_sync.py --write    write the missing, edited and outdated copies
    python3 scripts/operational_sync.py --self-test

Trust boundary:
- Sources come only from APPROVED below, which is reviewed code. Each approved source has exactly one designated
  destination, and its copies may only live at `skills/<skill>/<that destination>` in a skill other than the source's
  own. Extending the list is a reviewed change.
- `operational/copies.json` only says which skills receive which approved source. It is validated completely (kind,
  integer version, exact keys, types, approved sources, designated destinations, no duplicates, no absolute paths, no
  `..`, no symlink anywhere on a path) before anything is written, and any such problem blocks every write.
- A Markdown copy is exactly one generated header line naming the source, its revision and its SHA-256, a blank line,
  then the source bytes unchanged. A Python copy keeps the source's shebang line first, then one `#` header line
  (source and SHA-256), then the rest of the source unchanged. JSON has no comments, so a JSON copy is an object whose
  first line carries the generated header as `"$generated"` and whose `"content"` is the source bytes unchanged.
  Comparison is byte for byte.
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
APPROVED = {                                                   # source -> its designated destination in a skill
    "operational/core.md": "references/operational-core.md",
    "skills/workspace-housekeeping/scripts/path_in_use.py": "scripts/path_in_use.py",
    "scripts/operational_records.py": "scripts/operational_records.py",
    "operational/formats.json": "references/formats.json",
    "operational/fixtures/authorization-runtime.json": "references/authorization-runtime.json",
    "operational/process_identity.py": "scripts/process_identity.py",
}
HEADER = ("<!-- Generated from {source} (revision {revision}, sha256 {digest}). Do not edit this copy: change the source "
          "and regenerate. -->")
PY_HEADER = "# Generated from {source} (sha256 {digest}). Do not edit this copy: change the source and regenerate."
JSON_HEADER = ('{{"$generated": "Generated from {source} (sha256 {digest}). Do not edit this copy: change the source and '
               'regenerate.",')
HEADER_RE = re.compile(rb"^(?:<!-- |# |\{\"\$generated\": \")Generated from (\S+) \((?:revision (\d+), )?sha256 ([0-9a-f]{64})\)\. Do not edit")
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


def header_match(data: bytes):
    """The generated-header match on the first line, or on the second when the first is a shebang."""
    lines = data.split(b"\n", 2)
    m = HEADER_RE.match(lines[0])
    if not m and lines[0].startswith(b"#!") and len(lines) > 1:
        m = HEADER_RE.match(lines[1])
    return m


def generated_header_source(path: Path) -> str | None:
    """The source a file's generated header names, or None."""
    with path.open("rb") as fh:
        m = header_match(fh.readline() + fh.readline())
    return m.group(1).decode("utf-8", "replace") if m else None


def expected_copy(source: str, data: bytes) -> tuple[bytes | None, str | None]:
    """(copy bytes, None) for a source's bytes, or (None, reason)."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None, f"{source}: not UTF-8"
    if source.endswith(".json"):
        try:
            strict_json(text)
        except ValueError as e:
            return None, f"{source}: not valid JSON: {e}"
        header = JSON_HEADER.format(source=source, digest=hashlib.sha256(data).hexdigest()).encode("utf-8")
        return header + b'\n"content":\n' + data.rstrip(b"\n") + b"\n}\n", None
    if source.endswith(".py"):
        header = PY_HEADER.format(source=source, digest=hashlib.sha256(data).hexdigest()).encode("utf-8")
        if data.startswith(b"#!"):
            shebang, _, rest = data.partition(b"\n")
            return shebang + b"\n" + header + b"\n" + rest, None
        return header + b"\n" + data, None
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
        own = Path(source).parts[1] if source.startswith("skills/") else None
        for copy in copies:
            parts = Path(copy).parts if isinstance(copy, str) else ()
            if (len(parts) < 3 or parts[0] != "skills" or not SLUG.match(parts[1]) or parts[1] == own
                    or copy != f"skills/{parts[1]}/{APPROVED[source]}" or not plain_path(root, copy)):
                problems.append(f"refused: {copy!r} (copies of {source} may only be skills/<skill>/"
                                f"{APPROVED[source]} in another skill, as a plain path, not through a symlink)")
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
        found = header_match(have)
        if not found or found.group(1).decode("utf-8", "replace") != source:
            structural.append(f"unrelated: {copy} exists without a generated header for {source}; refusing to overwrite it")
            continue
        if header_match(want).groups()[1:] != found.groups()[1:]:
            revision = f"revision {found.group(2).decode()}, " if found.group(2) else ""
            drift.append(f"outdated: {copy} (generated from {revision}sha256 {found.group(3).decode()[:12]}…)")
        else:
            drift.append(f"edited: {copy} (bytes differ from the generated copy of {source})")
        writes.append((path, want, source))
    listed = {copy for _, copy in pairs}
    skills = root / "skills"
    for path in sorted([*skills.rglob("*.md"), *skills.rglob("*.py"), *skills.rglob("*.json")]) if skills.is_dir() else []:
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

        # plain_path itself rejects non-canonical spellings (a second layer behind the exact destination rule).
        for spelling in ["skills/./a/references/operational-core.md", "skills//a/references/operational-core.md",
                         "skills/a/references/operational-core.md/", "./operational/core.md"]:
            if plain_path(root, spelling):
                failures.append(f"plain_path accepted the non-canonical spelling {spelling!r}")

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

        # A Python source: shebang first, header second, rest unchanged; never copied into the source's own skill.
        tool = root / "skills" / "src" / "scripts" / "tool.py"
        tool.parent.mkdir(parents=True)
        tool.write_bytes(b'#!/usr/bin/env python3\n"""Tool."""\nprint("ok")\n')
        (root / "skills" / "a" / "scripts").mkdir()
        copy = root / "skills" / "a" / "scripts" / "tool.py"
        for core_copy in (a, b):              # otherwise they would be unlisted, which blocks every write
            core_copy.unlink(missing_ok=True)
        APPROVED["skills/src/scripts/tool.py"] = "scripts/tool.py"
        try:
            manifest([{"source": "skills/src/scripts/tool.py", "copies": ["skills/a/scripts/tool.py"]}])
            expect("python copy missing", ["missing: skills/a/scripts/tool.py"], structural=False)
            write(root)
            lines = copy.read_bytes().split(b"\n", 2)
            if (lines[0] != b"#!/usr/bin/env python3" or not lines[1].startswith(
                    b"# Generated from skills/src/scripts/tool.py (sha256 ") or lines[2] != b'"""Tool."""\nprint("ok")\n'):
                failures.append(f"python copy layout: {lines}")
            try:
                compile(copy.read_bytes(), "tool.py", "exec")
            except SyntaxError as e:
                failures.append(f"the python copy no longer compiles: {e}")
            expect("python copy in sync", [])
            copy.write_bytes(copy.read_bytes().replace(b'"ok"', b'"changed"'))
            expect("python copy edited", ["edited: skills/a/scripts/tool.py"], structural=False)
            write(root)
            tool.write_bytes(tool.read_bytes() + b'print("new")\n')
            expect("python source changed", ["outdated: skills/a/scripts/tool.py (generated from sha256"], structural=False)
            write(root)
            expect("python copy regenerated", [])
            manifest([{"source": "skills/src/scripts/tool.py", "copies": ["skills/src/scripts/tool.py"]}])
            expect("copy into the source's own skill", ["refused: 'skills/src/scripts/tool.py'"], structural=True)
            manifest([{"source": "skills/src/scripts/tool.py", "copies": ["skills/a/references/tool.py"]}])
            expect("python copy at a non-designated path", ["refused: 'skills/a/references/tool.py'"], structural=True)
        finally:
            del APPROVED["skills/src/scripts/tool.py"]
        copy.unlink()

        # A JSON source: a wrapper object whose first line is the header and whose content is the source unchanged.
        data_src = root / "operational" / "data.json"
        data_src.write_bytes(b'{\n  "kind": "formats",\n  "version": 1\n}\n')
        data_copy = root / "skills" / "a" / "references" / "data.json"
        APPROVED["operational/data.json"] = "references/data.json"
        try:
            manifest([{"source": "operational/data.json", "copies": ["skills/a/references/data.json"]}])
            expect("json copy missing", ["missing: skills/a/references/data.json"], structural=False)
            write(root)
            wrapped = strict_json(data_copy.read_text(encoding="utf-8"))
            if set(wrapped) != {"$generated", "content"} or wrapped["content"] != {"kind": "formats", "version": 1} \
                    or not data_copy.read_bytes().startswith(b'{"$generated": "Generated from operational/data.json'):
                failures.append(f"json copy layout: {data_copy.read_bytes()[:120]!r}")
            expect("json copy in sync", [])
            data_copy.write_bytes(data_copy.read_bytes().replace(b'"version": 1', b'"version": 2'))
            expect("json copy edited", ["edited: skills/a/references/data.json"], structural=False)
            write(root)
            data_src.write_bytes(b'{"kind": "formats", "version": 1, "x": 2}\n')
            expect("json source changed", ["outdated: skills/a/references/data.json"], structural=False)
            data_src.write_bytes(b'{"kind": ')
            expect("json source invalid", ["not valid JSON"], structural=True)
            data_src.write_bytes(b'{"kind": "formats", "version": 1, "x": 2}\n')
            write(root)
            manifest()
            expect("unlisted json copy", ["unlisted: skills/a/references/data.json"], structural=True)
        finally:
            del APPROVED["operational/data.json"]
        data_copy.unlink()
        data_src.unlink()
        manifest()

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
