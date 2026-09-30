#!/usr/bin/env python3
"""Hash-pin a SPICE oracle and refuse to simulate on any provenance mismatch.

Subcommands:
  make  --out manifest.json FILE[:CARD,CARD...] ...   write a manifest (file hashes + used-card hashes)
  check manifest.json [--root DIR]                    verify; exit 1 with a full report on any mismatch
  hash  FILE [--card NAME ...]                        print file and card hashes
  --self-test                                         prove that mismatches are detected

Card-text rule (documented in every manifest): for `.model NAME`, the .model line plus its '+'
continuation lines; for `.subckt NAME`, every line from .subckt to its matching .ends. Each line is
stripped of surrounding whitespace (CR included); blank and full-line `*` comment lines are dropped;
lines are joined with '\n' without a trailing newline; the result is hashed as UTF-8 bytes. A card hash
therefore survives unrelated edits elsewhere in a vendor library but fails on any change to the used card.

Paths beginning with `$EXT/` resolve against the manifest's `external_root` (or `--root`, or the
environment variable named by `external_root_env`), so model collections that cannot be vendored can
live outside the repository. Standard library only. Run `check` before every simulation batch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

CARD_RULE = (
    ".model: the .model line plus '+' continuation lines; .subckt: .subckt through matching .ends; "
    "each line stripped, blank and full-line '*' comments dropped, joined with '\\n', no trailing newline, UTF-8"
)
MIN_PREFIX = 12


class ManifestError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _clean(lines: list[str]) -> list[str]:
    return [s for s in (line.strip() for line in lines) if s and not s.startswith("*")]


def card_text(path: Path, name: str) -> str | None:
    """Return the canonical text of `.model name` or `.subckt name`, or None if absent."""
    lines = path.read_text(encoding="utf-8", errors="replace").replace("\r", "").split("\n")
    head = re.compile(r"\s*\.(model|subckt)\s+" + re.escape(name) + r"(\s|$)", re.I)
    for i, line in enumerate(lines):
        m = head.match(line)
        if not m:
            continue
        if m.group(1).lower() == "model":
            block = [line]
            for cont in lines[i + 1 :]:
                if cont.strip().startswith("*") or not cont.strip():
                    continue
                if not cont.lstrip().startswith("+"):
                    break
                block.append(cont)
            return "\n".join(_clean(block))
        depth, block = 0, []
        for inner in lines[i:]:
            low = inner.strip().lower()
            if low.startswith(".subckt"):
                depth += 1
            block.append(inner)
            if low.startswith(".ends"):
                depth -= 1
                if depth == 0:
                    return "\n".join(_clean(block))
        raise ManifestError(f"{path}: .subckt {name} has no matching .ends")
    return None


def resolve(path_text: str, manifest_dir: Path, ext_root: Path | None) -> Path:
    if path_text.startswith("$EXT/"):
        if ext_root is None:
            raise ManifestError(f"{path_text}: no external root configured (--root or external_root)")
        return ext_root / path_text[len("$EXT/") :]
    p = Path(os.path.expanduser(path_text))
    return p if p.is_absolute() else manifest_dir / p


def external_root(manifest: dict, override: str | None) -> Path | None:
    if override:
        return Path(os.path.expanduser(override))
    env = manifest.get("external_root_env")
    if env and os.environ.get(env):
        return Path(os.path.expanduser(os.environ[env]))
    root = manifest.get("external_root")
    return Path(os.path.expanduser(root)) if root else None


def simulator_report(sim: dict) -> tuple[str | None, str]:
    cmd = list(sim["command"]) + list(sim.get("version_args", ["--version"]))
    try:
        run = subprocess.run(cmd, capture_output=True, text=True, timeout=sim.get("timeout", 30))
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    text = run.stdout + run.stderr
    m = re.search(sim.get("version_regex", r"ngspice-\d+(?:\.\d+)?"), text)
    return (m.group(0) if m else None), text.strip()


def check(manifest: dict, manifest_dir: Path, root_override: str | None = None) -> list[dict]:
    """Return a list of mismatches (empty = OK). Never raises for ordinary mismatches."""
    fails: list[dict] = []

    def fail(kind: str, name: str, where: str, expected: str, actual: str) -> None:
        fails.append(dict(kind=kind, name=name, path=where, expected=expected, actual=actual))

    sim = manifest.get("simulator")
    if sim:
        version, text = simulator_report(sim)
        if version != sim["expected"]:
            fail("simulator", "version", " ".join(sim["command"]), sim["expected"], version or text[:200])
        for feature in sim.get("require", []):
            if feature not in text:
                fail("simulator", f"feature {feature}", " ".join(sim["command"]), f"'{feature}' reported", "not reported")

    try:
        root = external_root(manifest, root_override)
    except ManifestError as exc:
        fail("configuration", "external root", "-", "configured", str(exc))
        return fails
    for entry in manifest.get("files", []):
        try:
            path = resolve(entry["path"], manifest_dir, root)
        except ManifestError as exc:
            fail("configuration", entry.get("name", entry["path"]), entry["path"], "resolvable path", str(exc))
            continue
        name = entry.get("name", entry["path"])
        if not path.is_file():
            fail("file", name, str(path), entry.get("sha256", "present"), "MISSING")
            continue
        if "sha256" in entry and sha256_file(path) != entry["sha256"]:
            fail("file", name, str(path), entry["sha256"], sha256_file(path))
        if "size" in entry and path.stat().st_size != entry["size"]:
            fail("file size", name, str(path), str(entry["size"]), str(path.stat().st_size))
        for card in entry.get("cards", []):
            try:
                text = card_text(path, card["name"])
            except ManifestError as exc:
                fail("card", card["name"], str(path), card["sha256"], str(exc))
                continue
            actual = sha256_bytes(text.encode()) if text is not None else "CARD NOT FOUND"
            want = card["sha256"].lower()
            if len(want) < MIN_PREFIX or not actual.startswith(want):
                fail("card", card["name"], str(path), want, actual)
    for rule in manifest.get("required_text", []):
        try:
            path = resolve(rule["path"], manifest_dir, root)
            ok = path.is_file() and re.search(rule["regex"], path.read_text(errors="replace"), re.M | re.I)
        except ManifestError:
            ok = False
        if not ok:
            fail("required text", rule.get("name", rule["regex"]), rule["path"], rule["regex"], "not found")
    return fails


def report(fails: list[dict], out=sys.stdout) -> None:
    for f in fails:
        print(f"MISMATCH [{f['kind']}] {f['name']}\n  path:     {f['path']}\n"
              f"  expected: {f['expected']}\n  actual:   {f['actual']}", file=out)
    print("MANIFEST " + ("OK" if not fails else f"FAILED ({len(fails)} mismatches): do not simulate"), file=out)


def make(specs: list[str], out: Path, root: str | None) -> dict:
    ext = Path(os.path.expanduser(root)) if root else None
    files = []
    for spec in specs:
        path_text, _, cards = spec.partition(":")
        path = resolve(path_text, out.parent, ext)
        if not path.is_file():
            raise ManifestError(f"{path}: not a file")
        entry = dict(name=Path(path_text).name, path=path_text, sha256=sha256_file(path), size=path.stat().st_size)
        entry_cards = []
        for card in filter(None, cards.split(",")):
            text = card_text(path, card)
            if text is None:
                raise ManifestError(f"{path}: card {card} not found")
            entry_cards.append(dict(name=card, sha256=sha256_bytes(text.encode())))
        if entry_cards:
            entry["cards"] = entry_cards
        files.append(entry)
    manifest = dict(manifest_version=1, card_hash_rule=CARD_RULE, files=files)
    if root:
        manifest["external_root"] = root
    out.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def self_test() -> int:
    """Each deliberate corruption must be reported; an unrelated library edit must not break the card hash."""
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        lib = d / "vendor.lib"
        lib.write_text("* vendor library\n.model DX D(IS=2e-15 N=1.9\n+ RS=0.5)\n"
                       ".subckt OPX inp inn vcc vee out\n* comment\nR1 inp inn 1meg\nE1 out 0 inp inn 1e5\n.ends OPX\n"
                       ".model OTHER NPN(BF=100)\n")
        deck = d / "oracle.cir"
        deck.write_text("oracle\n.include vendor.lib\n.options klu\nD1 a 0 DX\n.end\n")
        fake_sim = [sys.executable, "-c", "print('fakesim-7 : compiled with KLU')"]
        man_path = d / "manifest.json"
        manifest = make([f"{deck}", f"{lib}:DX,OPX"], man_path, None)
        manifest["simulator"] = dict(command=fake_sim, version_args=[], version_regex=r"fakesim-\d+", expected="fakesim-7",
                                     require=["KLU"])
        manifest["required_text"] = [dict(name=".options klu", path=str(deck), regex=r"^\.options\b.*\bklu\b")]

        def expect(label: str, want_kinds: set[str], m: dict | None = None) -> None:
            kinds = {f["kind"] for f in check(m or manifest, d)}
            if kinds != want_kinds:
                problems.append(f"{label}: expected {sorted(want_kinds) or 'no mismatch'}, got {sorted(kinds) or 'none'}")

        expect("pristine", set())
        original = lib.read_text()
        lib.write_text(original.replace(".model OTHER NPN(BF=100)", ".model OTHER NPN(BF=120)"))
        expect("unrelated card edited", {"file"})   # whole-file hash fails, used-card hashes still pass
        lib.write_text(original.replace("RS=0.5", "RS=0.6"))
        expect("used .model edited", {"file", "card"})
        lib.write_text(original.replace("1e5", "2e5"))
        expect("used .subckt edited", {"file", "card"})
        lib.write_text(original.replace("* comment\n", "* reworded comment\n"))
        expect("comment inside subckt edited", {"file", "file size"})
        lib.write_text(original.replace(".model DX", ".model DY"))
        expect("used card renamed", {"file", "card"})
        lib.write_text(original)
        deck.write_text(deck.read_text().replace(".options klu\n", ""))
        expect("required option removed", {"file", "file size", "required text"})
        deck.unlink()
        expect("oracle missing", {"file", "required text"})
        deck.write_text("oracle\n.include vendor.lib\n.options klu\nD1 a 0 DX\n.end\n")
        wrong = json.loads(json.dumps(manifest))
        wrong["simulator"]["expected"] = "fakesim-8"
        expect("wrong simulator version", {"simulator"}, wrong)
        missing_feature = json.loads(json.dumps(manifest))
        missing_feature["simulator"]["require"] = ["OpenMP"]
        expect("missing simulator feature", {"simulator"}, missing_feature)
        short = json.loads(json.dumps(manifest))
        short["files"][1]["cards"][0]["sha256"] = short["files"][1]["cards"][0]["sha256"][:6]
        expect("card prefix too short to be meaningful", {"card"}, short)
        ext = json.loads(json.dumps(manifest))
        ext["files"][1]["path"] = "$EXT/vendor.lib"
        kinds = {f["kind"] for f in check(ext, d)}
        if kinds != {"configuration"}:
            problems.append(f"unconfigured $EXT root: expected configuration mismatch, got {sorted(kinds)}")
        if check(ext, d, root_override=str(d)):
            problems.append("$EXT root via --root should verify cleanly")
    for p in problems:
        print("SELF-TEST FAILURE:", p)
    print(f"self-test: {'PASS' if not problems else 'FAIL'}")
    return 1 if problems else 0


def main() -> int:
    if "--self-test" in sys.argv[1:]:
        return self_test()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    mk = sub.add_parser("make", help="write a manifest")
    mk.add_argument("--out", required=True, type=Path)
    mk.add_argument("--root", help="external root recorded in the manifest ($EXT/... paths)")
    mk.add_argument("specs", nargs="+", help="FILE or FILE:CARD1,CARD2 (FILE may start with $EXT/)")
    ck = sub.add_parser("check", help="verify a manifest")
    ck.add_argument("manifest", type=Path)
    ck.add_argument("--root", help="override the external model root")
    hs = sub.add_parser("hash", help="print hashes")
    hs.add_argument("file", type=Path)
    hs.add_argument("--card", action="append", default=[])
    a = ap.parse_args()
    try:
        if a.cmd == "make":
            make(a.specs, a.out, a.root)
            print(f"wrote {a.out}")
            return 0
        if a.cmd == "hash":
            print(f"{sha256_file(a.file)}  size {a.file.stat().st_size}  {a.file}")
            for card in a.card:
                text = card_text(a.file, card)
                print(f"  card {card}: " + (sha256_bytes(text.encode()) if text is not None else "NOT FOUND"))
            return 0
        manifest = json.loads(a.manifest.read_text())
        fails = check(manifest, a.manifest.parent, a.root)
        report(fails, sys.stdout if not fails else sys.stderr)
        return 1 if fails else 0
    except (ManifestError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
