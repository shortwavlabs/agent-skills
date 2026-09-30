#!/usr/bin/env python3
"""Hash-pin a SPICE oracle and refuse to simulate on any provenance mismatch.

  spice_manifest.py make --out manifest.json --file DECK.cir --card LIB=CARD [--used-cards LIB] ...
                    [--simulator-command EXE [--simulator-arg ARG ...] [--simulator-version V]]
                    [--version-regex RE] [--require-feature TEXT] [--require-text PATH=REGEX]
                    [--external-root DIR] [--external-root-env VAR]
  spice_manifest.py check manifest.json [--root DIR]
  spice_manifest.py hash FILE [--card NAME ...]
  spice_manifest.py --self-test

Per-file hash policy (manifest field "hash_policy"):
  strict_file (default)  the whole-file SHA-256 and size are hard requirements; any edit anywhere in the
                         file fails. Used-card hashes are checked as well and name the card that changed.
  used_cards             the used-card hashes are the hard requirement; the whole-file hash and size are
                         recorded for provenance and reported as ADVISORY when they differ while every
                         pinned card's canonical text still matches (the changed bytes may be elsewhere in
                         the file or, for example, a comment inside a used card). Needs at least one card.

`check` first requires manifest_version 2 and the exact card_hash_rule text below, and refuses any other
manifest before looking at files.

Card-text rule: for `.model NAME`, the .model line plus its '+' continuation lines; for `.subckt NAME`,
every line from .subckt to its matching .ends. Each line is stripped of surrounding whitespace (CR
included); blank and full-line `*` comment lines are dropped; lines are joined with '\n' without a
trailing newline; the result is hashed as UTF-8 bytes.

Paths: relative paths are stored relative to the manifest's directory. Paths beginning with `$EXT/`
resolve against the manifest's `external_root`, the environment variable named by `external_root_env`,
or `--root` (in increasing priority). `--card PATH=NAME` splits at the LAST '=' and `--require-text
PATH=REGEX` at the FIRST '=', so Windows drive letters and '=' inside a regex are safe; PATH itself must
not contain '='. Standard library only. Run `check` before every simulation batch.
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

POLICIES = ("strict_file", "used_cards")
DEFAULT_VERSION_REGEX = r"ngspice-\d+(?:\.\d+)?"
CARD_RULE = (
    ".model: the .model line plus '+' continuation lines; .subckt: .subckt through matching .ends; "
    "each line stripped, blank and full-line '*' comments dropped, joined with '\\n', no trailing newline, UTF-8"
)
MIN_PREFIX = 12
SUPPORTED_VERSIONS = {2}


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


def split_last(text: str, what: str) -> tuple[str, str]:
    path, sep, value = text.rpartition("=")
    if not sep or not path or not value:
        raise ManifestError(f"{what} must be PATH=VALUE, got {text!r}")
    return path, value


def split_first(text: str, what: str) -> tuple[str, str]:
    path, sep, value = text.partition("=")
    if not sep or not path or not value:
        raise ManifestError(f"{what} must be PATH=VALUE, got {text!r}")
    return path, value


def resolve(path_text: str, manifest_dir: Path, ext_root: Path | None) -> Path:
    if path_text.startswith("$EXT/"):
        if ext_root is None:
            raise ManifestError(f"{path_text}: no external root configured (--root, external_root or external_root_env)")
        return ext_root / path_text[len("$EXT/") :]
    p = Path(os.path.expanduser(path_text))
    return p if p.is_absolute() else manifest_dir / p


def stored_path(path_text: str, manifest_dir: Path) -> str:
    """Path as recorded in a manifest: $EXT/... unchanged, otherwise relative to the manifest if possible."""
    if path_text.startswith("$EXT/"):
        return path_text
    p = Path(os.path.expanduser(path_text)).resolve()
    try:
        return Path(os.path.relpath(p, manifest_dir.resolve())).as_posix()
    except ValueError:        # different drive on Windows
        return p.as_posix()


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
    m = re.search(sim.get("version_regex", DEFAULT_VERSION_REGEX), text)
    return (m.group(0) if m else None), text.strip()


def check(manifest: dict, manifest_dir: Path, root_override: str | None = None) -> tuple[list[dict], list[str]]:
    """Return (mismatches, advisories). Mismatches block simulation; advisories are reported only."""
    fails: list[dict] = []
    advisories: list[str] = []

    def fail(kind: str, name: str, where: str, expected: str, actual: str) -> None:
        fails.append(dict(kind=kind, name=name, path=where, expected=expected, actual=actual))

    # Schema first: never interpret a manifest written for another version or card-hash rule.
    if manifest.get("manifest_version") not in SUPPORTED_VERSIONS:
        fail("configuration", "manifest_version", "manifest", f"one of {sorted(SUPPORTED_VERSIONS)}",
             str(manifest.get("manifest_version", "absent")))
    if manifest.get("card_hash_rule") != CARD_RULE:
        fail("configuration", "card_hash_rule", "manifest", CARD_RULE, str(manifest.get("card_hash_rule", "absent")))
    if fails:
        return fails, advisories

    sim = manifest.get("simulator")
    if sim:
        version, text = simulator_report(sim)
        if version != sim["expected"]:
            fail("simulator", "version", " ".join(sim["command"]), sim["expected"], version or text[:200])
        for feature in sim.get("require", []):
            if feature not in text:
                fail("simulator", f"feature {feature}", " ".join(sim["command"]), f"'{feature}' reported", "not reported")

    root = external_root(manifest, root_override)
    for entry in manifest.get("files", []):
        name = entry.get("name", entry["path"])
        policy = entry.get("hash_policy", "strict_file")
        if policy not in POLICIES:
            fail("configuration", name, entry["path"], f"hash_policy in {POLICIES}", str(policy))
            continue
        if policy == "used_cards" and not entry.get("cards"):
            fail("configuration", name, entry["path"], "at least one card under used_cards", "no cards")
            continue
        try:
            path = resolve(entry["path"], manifest_dir, root)
        except ManifestError as exc:
            fail("configuration", name, entry["path"], "resolvable path", str(exc))
            continue
        if not path.is_file():
            fail("file", name, str(path), entry.get("sha256", "present"), "MISSING")
            continue
        digest, size = sha256_file(path), path.stat().st_size
        for key, actual, kind in (("sha256", digest, "file"), ("size", size, "file size")):
            if key in entry and actual != entry[key]:
                if policy == "strict_file":
                    fail(kind, name, str(path), str(entry[key]), str(actual))
                else:
                    advisories.append(f"{name}: whole-file {kind} changed ({entry[key]} -> {actual}) while all pinned "
                                      "used-card canonical texts still match; allowed by hash_policy used_cards")
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
    return fails, advisories


def report(fails: list[dict], advisories: list[str], out=sys.stdout) -> None:
    for a in advisories:
        print(f"ADVISORY: {a}", file=out)
    for f in fails:
        print(f"MISMATCH [{f['kind']}] {f['name']}\n  path:     {f['path']}\n"
              f"  expected: {f['expected']}\n  actual:   {f['actual']}", file=out)
    print("MANIFEST " + ("OK" if not fails else f"FAILED ({len(fails)} mismatches): do not simulate"), file=out)


def build(a: argparse.Namespace) -> dict:
    """Build a manifest from `make` arguments."""
    out_dir = a.out.parent
    ext = Path(os.path.expanduser(a.external_root)) if a.external_root else None
    if a.external_root_env and os.environ.get(a.external_root_env):
        ext = Path(os.path.expanduser(os.environ[a.external_root_env]))
    entries: dict[str, dict] = {}

    def entry(path_text: str) -> dict:
        key = stored_path(path_text, out_dir)
        if key not in entries:
            path = resolve(path_text, Path.cwd(), ext)
            if not path.is_file():
                raise ManifestError(f"{path}: not a file")
            entries[key] = dict(name=Path(path_text).name, path=key, hash_policy="strict_file",
                                sha256=sha256_file(path), size=path.stat().st_size, _abs=str(path))
        return entries[key]

    for f in a.file:
        entry(f)
    for spec in a.card:
        path_text, name = split_last(spec, "--card")
        e = entry(path_text)
        text = card_text(Path(e["_abs"]), name)
        if text is None:
            raise ManifestError(f"{e['_abs']}: card {name} not found")
        e.setdefault("cards", []).append(dict(name=name, sha256=sha256_bytes(text.encode())))
    for path_text in a.used_cards:
        e = entry(path_text)
        if not e.get("cards"):
            raise ManifestError(f"{path_text}: --used-cards needs at least one --card for that file")
        e["hash_policy"] = "used_cards"
    manifest: dict = dict(manifest_version=2, card_hash_rule=CARD_RULE, hash_policies={
        "strict_file": "whole-file SHA-256 and size are hard requirements (default)",
        "used_cards": "used-card hashes are hard requirements; whole-file hash and size are advisory"})
    if a.external_root:
        manifest["external_root"] = a.external_root
    if a.external_root_env:
        manifest["external_root_env"] = a.external_root_env
    if a.simulator_command:
        sim = dict(command=[a.simulator_command, *a.simulator_arg], version_args=a.version_arg or ["--version"],
                   version_regex=a.version_regex, require=a.require_feature)
        version, text = simulator_report(dict(sim, expected=""))
        if a.simulator_version:
            sim["expected"] = a.simulator_version
        elif version:
            sim["expected"] = version
        else:
            raise ManifestError(f"simulator version not detected with {a.version_regex!r}: {text[:200]}")
        manifest["simulator"] = sim
    elif a.simulator_version or a.require_feature:
        raise ManifestError("--simulator-version/--require-feature need --simulator-command")
    manifest["files"] = [{k: v for k, v in e.items() if k != "_abs"} for e in entries.values()]
    rules = []
    for spec in a.require_text:
        path_text, regex = split_first(spec, "--require-text")
        re.compile(regex)
        rules.append(dict(name=regex, path=stored_path(path_text, out_dir), regex=regex))
    if rules:
        manifest["required_text"] = rules
    return manifest


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    mk = sub.add_parser("make", help="write a manifest")
    mk.add_argument("--out", required=True, type=Path)
    mk.add_argument("--file", action="append", default=[], help="pin a whole file (hash_policy strict_file)")
    mk.add_argument("--card", action="append", default=[], help="PATH=NAME: pin a used .model/.subckt card")
    mk.add_argument("--used-cards", action="append", default=[], help="PATH: switch that file to hash_policy used_cards")
    mk.add_argument("--external-root", help="root for $EXT/... paths, recorded in the manifest")
    mk.add_argument("--external-root-env", help="environment variable that overrides the external root")
    mk.add_argument("--simulator-command", help="simulator executable (pins its version)")
    mk.add_argument("--simulator-arg", action="append", default=[], help="extra leading argument(s) for the command")
    mk.add_argument("--version-arg", action="append", default=[], help="argument(s) that print the version (default --version)")
    mk.add_argument("--simulator-version", help="expected version string (default: detected now)")
    mk.add_argument("--version-regex", default=DEFAULT_VERSION_REGEX)
    mk.add_argument("--require-feature", action="append", default=[], help="text the version output must contain, e.g. KLU")
    mk.add_argument("--require-text", action="append", default=[], help="PATH=REGEX that must match the file, e.g. an option")
    ck = sub.add_parser("check", help="verify a manifest")
    ck.add_argument("manifest", type=Path)
    ck.add_argument("--root", help="override the external model root")
    hs = sub.add_parser("hash", help="print hashes")
    hs.add_argument("file", type=Path)
    hs.add_argument("--card", action="append", default=[])
    return ap


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--self-test" in argv:
        return self_test()
    a = parser().parse_args(argv)
    try:
        if a.cmd == "make":
            manifest = build(a)
            a.out.write_text(json.dumps(manifest, indent=2) + "\n")
            print(f"wrote {a.out}")
            return 0
        if a.cmd == "hash":
            print(f"{sha256_file(a.file)}  size {a.file.stat().st_size}  {a.file}")
            for card in a.card:
                text = card_text(a.file, card)
                print(f"  card {card}: " + (sha256_bytes(text.encode()) if text is not None else "NOT FOUND"))
            return 0
        manifest = json.loads(a.manifest.read_text())
        fails, advisories = check(manifest, a.manifest.parent, a.root)
        report(fails, advisories, sys.stdout if not fails else sys.stderr)
        return 1 if fails else 0
    except (ManifestError, OSError, json.JSONDecodeError, re.error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


# ----------------------------------------------------------------- self-test
LIB = ("* vendor library\n.model DX D(IS=2e-15 N=1.9\n+ RS=0.5)\n"
       ".subckt OPX inp inn vcc vee out\n* comment\nR1 inp inn 1meg\nE1 out 0 inp inn 1e5\n.ends OPX\n"
       ".model OTHER NPN(BF=100)\n")
DECK = "oracle\n.include vendor.lib\n.options klu\nD1 a 0 DX\nR1 a 0 1k\n.end\n"
FAKE_SIM = "print('fakesim-7 : compiled with KLU')\n"


def self_test() -> int:
    problems: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        lib, deck, fake = d / "vendor.lib", d / "oracle.cir", d / "fake_sim.py"
        fake.write_text(FAKE_SIM)

        def reset() -> None:
            lib.write_text(LIB)
            deck.write_text(DECK)

        def make(out: str, *extra: str) -> int:
            with open(os.devnull, "w") as null:
                saved, sys.stdout = sys.stdout, null
                try:
                    return main(["make", "--out", str(d / out), "--file", str(deck), "--card", f"{lib}=DX",
                                 "--card", f"{lib}=OPX", "--simulator-command", sys.executable,
                                 "--simulator-arg", str(fake), "--version-regex", r"fakesim-\d+",
                                 "--require-feature", "KLU", "--require-text", rf"{deck}=^\.options\b.*\bklu\b",
                                 *extra])
                finally:
                    sys.stdout = saved

        def kinds(manifest_name: str, m: dict | None = None) -> tuple[set[str], int]:
            manifest = m or json.loads((d / manifest_name).read_text())
            fails, adv = check(manifest, d)
            return {f["kind"] for f in fails}, len(adv)

        def expect(label: str, manifest_name: str, want: set[str], want_advisory: bool = False, m=None) -> None:
            got, adv = kinds(manifest_name, m)
            if got != want or bool(adv) != want_advisory:
                problems.append(f"{label}: expected {sorted(want) or 'PASS'}{' + advisory' if want_advisory else ''}, "
                                f"got {sorted(got) or 'PASS'}{' + advisory' if adv else ''}")

        reset()
        if make("strict.json") != 0 or make("used.json", "--used-cards", str(lib)) != 0:
            problems.append("CLI make failed")
            print("\n".join("SELF-TEST FAILURE: " + p for p in problems))
            return 1
        strict = json.loads((d / "strict.json").read_text())
        if (strict["simulator"]["expected"] != "fakesim-7" or strict["files"][0]["path"] != "oracle.cir"
                or {f["hash_policy"] for f in strict["files"]} != {"strict_file"}):
            problems.append(f"CLI round trip recorded unexpected fields: {strict['simulator']}, {strict['files'][0]}")
        with open(os.devnull, "w") as null:
            saved, sys.stdout = sys.stdout, null
            try:
                fresh = main(["check", str(d / "strict.json")])
            finally:
                sys.stdout = saved
        if fresh != 0:
            problems.append("CLI check of a fresh manifest did not pass")
        expect("pristine, strict", "strict.json", set())
        expect("pristine, used_cards", "used.json", set())

        edits = [
            ("unrelated card edited", lambda: lib.write_text(LIB.replace("BF=100", "BF=120")), {"file"}, set(), True),
            ("used .model edited", lambda: lib.write_text(LIB.replace("RS=0.5", "RS=0.6")), {"file", "card"}, {"card"}, True),
            ("used .subckt edited", lambda: lib.write_text(LIB.replace("1e5", "2e5")), {"file", "card"}, {"card"}, True),
            ("comment inside used subckt edited", lambda: lib.write_text(LIB.replace("* comment", "* longer comment")),
             {"file", "file size"}, set(), True),
            ("used card renamed", lambda: lib.write_text(LIB.replace(".model DX", ".model DY")), {"file", "card"}, {"card"}, True),
            ("used card missing", lambda: lib.write_text(LIB.replace(".model DX D(IS=2e-15 N=1.9\n+ RS=0.5)\n", "")),
             {"file", "file size", "card"}, {"card"}, True),
        ]
        for label, edit, want_strict, want_used, used_advisory in edits:
            reset()
            edit()
            expect(f"{label}, strict_file", "strict.json", want_strict)
            expect(f"{label}, used_cards", "used.json", want_used, used_advisory)
        reset()
        deck.write_text(DECK.replace("R1 a 0 1k", "R1 a 0 2k"))
        expect("project file edited", "strict.json", {"file"})
        reset()
        deck.write_text(DECK.replace(".options klu\n", ""))
        expect("required option removed", "strict.json", {"file", "file size", "required text"})
        reset()
        deck.unlink()
        expect("oracle missing", "strict.json", {"file", "required text"})
        reset()
        for label, mutate in (("missing manifest_version", lambda m: m.pop("manifest_version")),
                              ("manifest_version 999", lambda m: m.update(manifest_version=999)),
                              ("missing card_hash_rule", lambda m: m.pop("card_hash_rule")),
                              ("altered card_hash_rule", lambda m: m.update(card_hash_rule=m["card_hash_rule"] + " ")),
                              ("wrong simulator version", lambda m: m["simulator"].update(expected="fakesim-8")),
                              ("missing simulator feature", lambda m: m["simulator"].update(require=["OpenMP"])),
                              ("unknown hash policy", lambda m: m["files"][1].update(hash_policy="loose")),
                              ("used_cards without cards", lambda m: m["files"][1].update(hash_policy="used_cards", cards=[])),
                              ("card prefix too short", lambda m: m["files"][1]["cards"][0].update(sha256="abc123"))):
            m = json.loads((d / "strict.json").read_text())
            mutate(m)
            want = {"simulator"} if "simulator" in label else {"card"} if "prefix" in label else {"configuration"}
            expect(label, "", want, m=m)
        ext = json.loads((d / "strict.json").read_text())
        ext["files"][1]["path"] = "$EXT/vendor.lib"
        if kinds("", ext)[0] != {"configuration"}:
            problems.append("unconfigured $EXT root was not reported as a configuration mismatch")
        if check(ext, d, root_override=str(d))[0]:
            problems.append("$EXT root supplied with --root did not verify")
        with open(os.devnull, "w") as null:
            saved_err, sys.stderr = sys.stderr, null
            try:
                if main(["make", "--out", str(d / "bad.json"), "--used-cards", str(lib)]) != 2:
                    problems.append("--used-cards without --card was accepted")
            finally:
                sys.stderr = saved_err
        if split_last(r"C:\models\vendor.lib=1SS133", "--card") != (r"C:\models\vendor.lib", "1SS133"):
            problems.append("Windows drive-letter path not parsed by --card")
        if split_first(r"C:\deck.cir=^\.param A=1", "--require-text") != (r"C:\deck.cir", r"^\.param A=1"):
            problems.append("'=' inside a --require-text regex not preserved")
    for p in problems:
        print("SELF-TEST FAILURE:", p)
    print(f"self-test: {'PASS' if not problems else 'FAIL'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
