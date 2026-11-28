#!/usr/bin/env python3
# Generated from scripts/operational_records.py (sha256 4de77bfd86af3333e762bf1dc1f63c127f05d983a59d276fbea6f5be9be5994c). Do not edit this copy: change the source and regenerate.
"""Check operational records against operational/formats.json (RFC 0001, document 05).

    python3 scripts/operational_records.py FILE...    exit 0 when every file is valid
    python3 scripts/operational_records.py --self-test

JSON records are checked by their `kind` and integer `version`; Markdown records by their title (`# Handoff: ...`).
Malformed input fails with a message, never an exception; duplicate JSON keys are rejected.

Authorization references get a **structural** status only: `invalid` or `unverified`. A reference that matches the
format is unverified: it is never authenticated or authorized by being well formed, and every reference inside an
invalid record is invalid. Only runtime verification (Phase 1c) can report `verified`, the one status that grants
authority (`grants_authority`). The runtime contract is defined in operational/fixtures/authorization-runtime.json;
this script checks only that file's structural column. Standard library only.
"""

from __future__ import annotations

import datetime
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORMATS = ROOT / "operational" / "formats.json"
RUNTIME_FIXTURES = ROOT / "operational" / "fixtures" / "authorization-runtime.json"
if not FORMATS.exists():                      # installed in a skill: scripts/ beside generated copies in references/
    FORMATS = ROOT / "references" / "formats.json"
    RUNTIME_FIXTURES = ROOT / "references" / "authorization-runtime.json"
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
EXPIRY_WORDS = ("task-end", "until revoked")


def strict_json(text: str):
    """json.loads that rejects duplicate keys, which could make an authorization or a claim ambiguous."""
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError(f"duplicate key {key!r}")
            out[key] = value
        return out
    return json.loads(text, object_pairs_hook=pairs)


def read_json(path: Path):
    """A JSON file, or the content of its generated copy (scripts/operational_sync.py wraps JSON copies)."""
    data = strict_json(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "$generated" in data:
        if set(data) != {"$generated", "content"}:
            raise ValueError(f"{path}: malformed generated copy")
        data = data["content"]
    return data


def load_formats(path: Path = FORMATS) -> dict:
    """The format definitions. Raises ValueError for an unknown kind or version: readers never guess."""
    formats = read_json(path)
    if not isinstance(formats, dict) or formats.get("kind") != "formats" or type(formats.get("version")) is not int \
            or formats.get("version") != 1:
        raise ValueError(f"{path}: incompatible format definitions (expected kind 'formats', integer version 1)")
    return formats


def grants_authority(status: str, formats: dict) -> bool:
    return status in formats["authorization_statuses"]["grants_authority"]


def parse_timestamp(value) -> datetime.datetime | None:
    if not isinstance(value, str) or not TIMESTAMP.match(value):
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class Checker:
    """Checks records against one set of definitions. `references` collects [where, status, note] for every
    authorization reference seen; statuses are structural only (invalid or unverified)."""

    def __init__(self, formats: dict, known_skills: set[str] | None = None):
        self.f = formats
        self.known_skills = known_skills
        self.references: list[list[str]] = []

    def check_type(self, value, t: str, where: str, problems: list[str]) -> None:
        if t.endswith("?"):
            if value is None:
                return
            t = t[:-1]
        if t == "any":
            return
        if t.startswith(("list:", "list+:")):
            if not isinstance(value, list):
                problems.append(f"{where}: expected a list, got {type(value).__name__}")
            elif t.startswith("list+:") and not value:
                problems.append(f"{where}: must not be empty")
            else:
                for i, item in enumerate(value):
                    self.check_type(item, t.split(":", 1)[1], f"{where}[{i}]", problems)
            return
        if t.startswith("obj:"):
            self.check_object(value, t[4:], where, problems)
            return
        if t.startswith("enum:"):
            if not isinstance(value, str) or value not in t[5:].split(","):
                problems.append(f"{where}: {value!r} is not one of {t[5:]}")
            return
        if t in ("int", "count", "pid"):
            if type(value) is not int:
                problems.append(f"{where}: expected an integer, got {value!r}")
            elif t == "count" and value < 0:
                problems.append(f"{where}: must not be negative, got {value}")
            elif t == "pid" and value < 1:
                problems.append(f"{where}: a process ID is a positive integer, got {value}")
            return
        if t == "bool":
            if not isinstance(value, bool):
                problems.append(f"{where}: expected true or false, got {value!r}")
            return
        if not isinstance(value, str) or not value.strip():
            problems.append(f"{where}: expected a non-empty string, got {value!r}")
            return
        if t == "str":
            return
        if t == "timestamp":
            if parse_timestamp(value) is None:
                problems.append(f"{where}: {value!r} is not a UTC timestamp (YYYY-MM-DDTHH:MM:SSZ)")
        elif t == "label":
            if value not in self.f["labels"]:
                problems.append(f"{where}: {value!r} is not an evidence label")
        elif t == "expiry":
            if value not in EXPIRY_WORDS and parse_timestamp(value) is None:
                problems.append(f"{where}: {value!r} is not a timestamp, 'task-end' or 'until revoked'")
        elif t in self.f["patterns"]:
            if not re.search(self.f["patterns"][t], value):
                problems.append(f"{where}: {value!r} is not a valid {t}")
        else:
            problems.append(f"{where}: unknown type {t!r} in the format definitions")

    def check_fields(self, value, spec: dict, where: str, problems: list[str]) -> tuple[str | None, str | None]:
        """Checks an object against a spec; returns the (status, note) its matching case declares, if any."""
        if not isinstance(value, dict):
            problems.append(f"{where}: expected an object, got {type(value).__name__}")
            return None, None
        for name, t in spec.get("required", {}).items():
            if name not in value:
                problems.append(f"{where}.{name}: missing")
            else:
                self.check_type(value[name], t, f"{where}.{name}", problems)
        for name, t in spec.get("optional", {}).items():
            if name in value:
                self.check_type(value[name], t, f"{where}.{name}", problems)
        status = note = None
        for field, cases in spec.get("cases", {}).items():
            case = cases.get(value[field]) if isinstance(value.get(field), str) else None
            for name, t in (case or {}).get("required", {}).items():
                if name not in value:
                    problems.append(f"{where}.{name}: missing (required when {field} is {value[field]!r})")
                else:
                    self.check_type(value[name], t, f"{where}.{name}", problems)
            status, note = (case or {}).get("status", status), (case or {}).get("note", note)
        for group in spec.get("null_together", []):
            if len({value.get(name) is None for name in group}) > 1:
                problems.append(f"{where}: {' and '.join(group)} must be null together")
        for later, earlier in spec.get("after", []):
            a, b = parse_timestamp(value.get(later)), parse_timestamp(value.get(earlier))
            if a and b and a <= b:
                problems.append(f"{where}.{later}: must be after {earlier}")
        for field, key in spec.get("unique", {}).items():
            items = value.get(field)
            keys = [item.get(key) for item in items if isinstance(item, dict)] if isinstance(items, list) else []
            keys = [k for k in keys if isinstance(k, str)]          # other types are already type errors
            duplicates = sorted({k for k in keys if keys.count(k) > 1})
            if duplicates:
                problems.append(f"{where}.{field}: duplicate {key} {duplicates}")
        return status, note

    def check_object(self, value, name: str, where: str, problems: list[str]) -> None:
        spec = self.f["objects"].get(name)
        if spec is None:
            problems.append(f"{where}: unknown object type {name!r} in the format definitions")
            return
        before = len(problems)
        status, note = self.check_fields(value, spec, where, problems)
        if name == "authorization-reference":
            valid = len(problems) == before and status in self.f["authorization_statuses"]["structural"]
            self.references.append([where, status if valid else "invalid", note if valid else None])

    def check_json(self, record, where: str) -> list[str]:
        kind = record.get("kind") if isinstance(record, dict) else None
        spec = self.f["json"].get(kind) if isinstance(kind, str) else None
        if spec is None:
            return [f"{where}: unknown kind {kind!r}"]
        version = record.get("version")
        if type(version) is not int or version not in spec["versions"]:
            return [f"{where}: incompatible {kind} version {version!r} (supported: {spec['versions']})"]
        problems: list[str] = []
        self.check_fields(record, spec, where, problems)
        if kind == "scenario" and self.known_skills is not None and isinstance(record.get("skills"), list):
            for skill in record["skills"]:
                if isinstance(skill, str) and skill not in self.known_skills:
                    problems.append(f"{where}.skills: no skill named {skill!r} in this repository")
        return problems

    def check_handoff(self, text: str, where: str) -> list[str]:
        spec = self.f["markdown"]["handoff"]
        lines = text.split("\n")
        problems: list[str] = []
        if not re.search(spec["title"], lines[0]):
            problems.append(f"{where}: the first line must be '# Handoff: <title>'")
        first_section = next((i for i, line in enumerate(lines) if line.startswith("## ")), len(lines))
        headers: dict[str, str] = {}
        for line in lines[1:first_section]:
            m = re.match(r"^([A-Za-z][A-Za-z ]*):\s*(.*)$", line)
            if m:
                if m.group(1) in headers:
                    problems.append(f"{where}: header '{m.group(1)}:' appears twice")
                headers[m.group(1)] = m.group(2).strip()
        version = headers.get("Version", "")
        if not version.isdigit() or int(version) not in spec["versions"]:
            return problems + [f"{where}: incompatible handoff Version {version!r} (supported: {spec['versions']})"]
        for key, t in spec["headers"].items():
            if key not in headers:
                problems.append(f"{where}: header '{key}:' missing")
            else:
                self.check_type(headers[key], t, f"{where}: header '{key}'", problems)
        for key, t in spec.get("optional_headers", {}).items():
            if key in headers:
                self.check_type(headers[key], t, f"{where}: header '{key}'", problems)
        sections: dict[str, list[str]] = {}
        current = None
        for line in lines[first_section:]:
            if line.startswith("## "):
                current = line[3:].strip()
                if current in sections:
                    problems.append(f"{where}: section '## {current}' appears twice")
                sections[current] = []
            elif current is not None:
                sections[current].append(line)
        for heading in spec["headings"]:
            if heading not in sections:
                problems.append(f"{where}: section '## {heading}' missing")
        for heading in spec["labelled"]:
            for line in sections.get(heading, []):
                if not line.startswith("- "):
                    continue
                m = re.match(r"^- \[([A-Z]+)\] \S", line)
                if not m or m.group(1) not in self.f["labels"]:
                    problems.append(f"{where}: an item under '## {heading}' has no evidence label: {line[:70]!r}")
                elif m.group(1) == "VERIFIED":
                    missing = [f for f in spec["verified_fields"] if f not in line]
                    at = re.search(r"\bat:\s*(\S+)", line)
                    if missing:
                        problems.append(f"{where}: a VERIFIED item lacks {', '.join(missing)}: {line[:70]!r}")
                    elif not at or parse_timestamp(at.group(1).rstrip(".;,")) is None:
                        problems.append(f"{where}: a VERIFIED item's 'at:' is not a UTC timestamp: {line[:70]!r}")
        optional = spec.get("optional_json_sections", {})
        for heading, t in [*spec["json_sections"].items(), *optional.items()]:
            blocks = re.findall(r"```json\n(.*?)\n```", "\n".join(sections.get(heading, [])), re.S)
            if heading in optional and heading not in spec["json_sections"] and not blocks:
                continue
            if len(blocks) != 1:
                problems.append(f"{where}: '## {heading}' needs exactly one ```json block")
                continue
            try:
                value = strict_json(blocks[0])
            except ValueError as e:
                problems.append(f"{where}: the JSON under '## {heading}' does not parse: {e}")
                continue
            self.check_type(value, t, f"{where}: {heading}", problems)
        return problems

    def check_text(self, text: str, name: str) -> list[str]:
        """Problems for one record. Never raises on malformed input; every reference in an invalid record is invalid."""
        start = len(self.references)
        try:
            if name.endswith(".json"):
                try:
                    record = strict_json(text)
                except (ValueError, RecursionError) as e:
                    problems = [f"{name}: not valid JSON: {e}"]
                else:
                    problems = self.check_json(record, name)
            elif name.endswith(".md"):
                problems = self.check_handoff(text, name) if text.startswith("# Handoff:") else \
                    [f"{name}: not a known Markdown record (expected '# Handoff: ...')"]
            else:
                problems = [f"{name}: not a .json or .md record"]
        except (TypeError, ValueError, KeyError, AttributeError, IndexError, RecursionError) as e:
            problems = [f"{name}: could not be checked ({type(e).__name__}: {e}); treated as invalid"]
        if problems:
            for ref in self.references[start:]:
                ref[1], ref[2] = "invalid", None
        return problems


# ---------------------------------------------------------------------------------------------------------- self-test

COMMIT = "0123456789abcdef0123456789abcdef01234567"
STANDING = {"level": "R2", "scope": "Push feature branches and open draft PRs", "source": "standing",
            "by": "github:example-owner", "ref": f"ops/authorizations.json@{COMMIT}#push-feature-branches",
            "granted": "2026-11-27T19:00:00Z", "expires": "2027-06-30T00:00:00Z"}
SESSION = {"level": "R2", "scope": "Merge the reviewed PR", "source": "owner-session", "by": "github:example-owner",
           "ref": "session of 2026-11-27, previous agent", "quote": "merge it once CI passes",
           "granted": "2026-11-27T19:05:00Z", "expires": "task-end"}
VALID = {
    "verification": {"kind": "verification", "version": 1, "claim": "The validator passes", "label": "VERIFIED",
                     "method": "python3 scripts/validate_skills.py exited 0", "artifact": {"type": "commit", "id": COMMIT},
                     "verified_at": "2026-11-27T19:40:00Z", "by": "example-agent"},
    "authorizations": {"kind": "authorizations", "version": 1, "authorizations": [
        {"id": "push-feature-branches", "level": "R2", "operations": "Push feature branches and open draft PRs",
         "granted_by": "github:example-owner", "approved_in": "https://github.com/example/repo/pull/1",
         "expires": "2027-06-30T00:00:00Z"}]},
    "claim": {"kind": "claim", "version": 1, "id": "c1", "holder": {"agent": "a", "session": "s", "host": "h",
              "pid": 42, "process_start": "2026-11-27T18:00:00Z"}, "scope": {"type": "paths", "value": ["src/**"]},
              "mode": "exclusive", "intent": "Edit the parser", "created": "2026-11-27T18:40:00Z",
              "expires": "2026-11-27T19:40:00Z"},
    "scenario": {"kind": "scenario", "version": 1, "id": "CLEAN-02", "title": "t", "skills": ["workspace-housekeeping"],
                 "polarity": "positive", "critical": True, "risk_level": "R3", "incidents": ["I6"], "setup": "s.sh",
                 "prompt": "p", "expected": ["e"], "forbidden": [], "authorization": "must_request",
                 "overhead": {"max_questions": 1, "max_new_records": 1}},
}


def handoff(authorizations, done: str = "- [VERIFIED] Tests pass; method: make test exit 0; "
            f"artifact: commit {COMMIT}; at: 2026-11-27T19:40:00Z", head: str = COMMIT, version: str = "1",
            drop: str = "") -> str:
    headers = {"Version": version, "Created": "2026-11-27T18:40:00Z", "Author": "a / m / s", "Repository": "origin",
               "Branch": "b", "HEAD": head, "Upstream": "in sync", "Working tree": "clean", "PR": "none",
               "Claim": "none", "Supersedes": "none"}
    block = authorizations if isinstance(authorizations, str) else json.dumps(authorizations)
    sections = {"Goal": "g", "State": "s", "Done": done, "Pending": "1. p", "Decisions and rejected approaches": "-",
                "Blockers and decisions needed": "-", "Authorizations in force": "```json\n" + block + "\n```",
                "Running processes and jobs": "-", "Verification": "v",
                "Assumptions and limitations": "- [INFERRED] x (premises: y)", "Resume": "1. r"}
    head_lines = [f"{k}: {v}" for k, v in headers.items() if k != drop]
    body = [f"## {k}\n{v}\n" for k, v in sections.items() if k != drop]
    return "# Handoff: example\n\n" + "\n".join(head_lines) + "\n\n" + "\n".join(body)


def mutate(record: dict, path: str, value) -> dict:
    """A deep copy of record with the dotted path set to value (or removed when value is ...)."""
    out = json.loads(json.dumps(record))
    keys = path.split(".")
    target = out
    for k in keys[:-1]:
        target = target[int(k)] if isinstance(target, list) else target[k]
    if value is ...:
        del target[keys[-1]]
    else:
        target[keys[-1]] = value
    return out


def self_test() -> list[str]:
    """Explicit checks, not assert, so it also runs under python -O."""
    failures: list[str] = []
    formats = load_formats()
    known = {"workspace-housekeeping"}

    def problems_of(record, name="fixture.json") -> list[str]:
        return Checker(formats, known).check_json(record, name)

    def expect_ok(label: str, problems: list[str]) -> None:
        if problems:
            failures.append(f"{label}: expected valid, got {problems}")

    def expect_bad(label: str, problems: list[str], fragment: str) -> None:
        if not any(fragment in p for p in problems):
            failures.append(f"{label}: expected a problem containing {fragment!r}, got {problems}")

    for kind, record in VALID.items():
        expect_ok(f"valid {kind}", problems_of(record))

    # Malformed records fail cleanly.
    expect_bad("malformed JSON", Checker(formats).check_text('{"kind": "claim", ', "x.json"), "not valid JSON")
    expect_bad("duplicate key", Checker(formats).check_text(
        '{"kind": "verification", "kind": "claim", "version": 1}', "x.json"), "duplicate key 'kind'")
    expect_bad("unknown kind", problems_of({"kind": "receipt", "version": 1}), "unknown kind")
    expect_bad("missing field", problems_of(mutate(VALID["verification"], "claim", ...)), ".claim: missing")
    expect_bad("empty string", problems_of(mutate(VALID["verification"], "method", " ")), "non-empty string")
    expect_bad("label", problems_of(mutate(VALID["verification"], "label", "CONFIRMED")), "not an evidence label")
    expect_bad("timestamp", problems_of(mutate(VALID["verification"], "verified_at", "2026-13-01T00:00:00Z")),
               "not a UTC timestamp")
    expect_bad("artifact commit", problems_of(mutate(VALID["verification"], "artifact.id", "abc123")), "valid commit")
    expect_bad("artifact file needs sha256",
               problems_of(mutate(VALID["verification"], "artifact", {"type": "file", "id": "a.txt"})), "sha256")
    expect_bad("nested object is a list", problems_of(mutate(VALID["verification"], "artifact", [COMMIT])),
               "expected an object")
    expect_bad("pid as a string", problems_of(mutate(VALID["claim"], "holder.pid", "42")), "expected an integer")
    expect_bad("pid zero", problems_of(mutate(VALID["claim"], "holder.pid", 0)), "positive integer")
    expect_bad("pid negative", problems_of(mutate(VALID["claim"], "holder.pid", -7)), "positive integer")
    expect_bad("pid boolean", problems_of(mutate(VALID["claim"], "holder.pid", True)), "expected an integer")
    expect_bad("enum", problems_of(mutate(VALID["claim"], "mode", "write")), "not one of")
    expect_bad("enum unhashable", problems_of(mutate(VALID["claim"], "mode", ["exclusive"])), "not one of")
    expect_bad("expires after created", problems_of(mutate(VALID["claim"], "expires", "2026-11-27T18:00:00Z")),
               "must be after created")
    expect_bad("pid and start null together", problems_of(mutate(VALID["claim"], "holder.pid", None)), "null together")
    expect_ok("holder unknown (both null)",
              problems_of(mutate(mutate(VALID["claim"], "holder.pid", None), "holder.process_start", None)))
    expect_bad("empty paths scope", problems_of(mutate(VALID["claim"], "scope.value", [])), "must not be empty")
    expect_bad("scope is a string", problems_of(mutate(VALID["claim"], "scope", "checkout")), "expected an object")
    expect_bad("authorizations not a list", problems_of(mutate(VALID["authorizations"], "authorizations", {})),
               "expected a list")
    expect_bad("duplicate standing ids", problems_of(mutate(VALID["authorizations"], "authorizations",
               VALID["authorizations"]["authorizations"] * 2)), "duplicate id")
    unhashable = mutate(VALID["authorizations"], "authorizations",
                        [dict(VALID["authorizations"]["authorizations"][0], id={"x": 1})] * 2)
    expect_bad("unhashable ids", problems_of(unhashable), "expected a non-empty string")
    expect_bad("standing R3", problems_of(mutate(VALID["authorizations"], "authorizations.0.level", "R3")),
               "not one of R1,R2")
    expect_bad("approval not a PR URL", problems_of(mutate(VALID["authorizations"], "authorizations.0.approved_in",
               "https://example.com/approved")), "valid pr-url")
    expect_bad("negative overhead", problems_of(mutate(VALID["scenario"], "overhead.max_questions", -1)),
               "must not be negative")
    expect_bad("unknown skill", problems_of(mutate(VALID["scenario"], "skills", ["no-such-skill"])), "no skill named")
    expect_bad("scenario id", problems_of(mutate(VALID["scenario"], "id", "clean-2")), "valid scenario-id")

    # Incompatible versions, including booleans and floats.
    for label, value in [("2", 2), ("true", True), ("1.0", 1.0), ("'1'", "1"), ("null", None)]:
        expect_bad(f"version {label}", problems_of(mutate(VALID["verification"], "version", value)), "incompatible")
    expect_bad("handoff Version 2", Checker(formats).check_handoff(handoff([], version="2"), "h.md"), "incompatible")
    with tempfile.TemporaryDirectory() as tmp:
        for label, definitions in [("definitions version 2", dict(formats, version=2)),
                                   ("definitions version 1.0", dict(formats, version=1.0)),
                                   ("definitions of another kind", dict(formats, kind="schema"))]:
            path = Path(tmp) / "formats.json"
            path.write_text(json.dumps(definitions), encoding="utf-8")
            try:
                load_formats(path)
                failures.append(f"{label}: accepted")
            except ValueError as e:
                if "incompatible format definitions" not in str(e):
                    failures.append(f"{label}: unexpected error {e}")

    # Robustness: no input raises.
    weird = [None, [], {}, 0, -1, 1.5, True, "", "x", [1], {"a": 1}, [[]], {"kind": []}]
    for kind, record in VALID.items():
        for field in record:
            for value in weird:
                try:
                    Checker(formats, known).check_json(mutate(record, field, value), "fuzz.json")
                except Exception as e:  # noqa: BLE001 - the point is that nothing escapes
                    failures.append(f"fuzz {kind}.{field}={value!r} raised {type(e).__name__}: {e}")
    for text in ["", "null", "[]", "1", '"x"', '{"kind": {}}', '{"kind": "claim", "version": 1, "holder": [], "scope": "x"}',
                 "[" * 100000 + "]" * 100000]:
        try:
            if not Checker(formats).check_text(text, "fuzz.json"):
                failures.append(f"fuzz text {text[:30]!r} passed as valid")
        except Exception as e:  # noqa: BLE001
            failures.append(f"fuzz text {text[:30]!r} raised {type(e).__name__}: {e}")
    for text in ["# Handoff: x", "# Handoff: x\nVersion: 1\n## Done\n- [VERIFIED] at: x", "# Handoff:\n\n\n"]:
        try:
            if not Checker(formats).check_text(text, "fuzz.md"):
                failures.append(f"fuzz handoff {text[:30]!r} passed as valid")
        except Exception as e:  # noqa: BLE001
            failures.append(f"fuzz handoff {text[:30]!r} raised {type(e).__name__}: {e}")

    # Authorization references: structural statuses only, and nothing structural grants authority.
    def classify(reference) -> tuple[list[str], list[str]]:
        checker = Checker(formats)
        problems: list[str] = []
        checker.check_object(reference, "authorization-reference", "ref", problems)
        return problems, [status for _, status, _ in checker.references]

    cases = [
        ("standing", STANDING, "unverified", False),
        ("owner-session with quote", SESSION, "unverified", False),
        ("unapproved source", mutate(STANDING, "source", "owner-comment"), "invalid", True),
        ("quote only, no source", {k: v for k, v in SESSION.items() if k != "source"}, "invalid", True),
        ("short commit in ref", mutate(STANDING, "ref", "ops/authorizations.json@abc123#push"), "invalid", True),
        ("ref without entry id", mutate(STANDING, "ref", f"ops/authorizations.json@{COMMIT}"), "invalid", True),
        ("R3 never transfers", mutate(STANDING, "level", "R3"), "invalid", True),
        ("missing scope", mutate(STANDING, "scope", ...), "invalid", True),
        ("bad identity", mutate(STANDING, "by", "example-owner"), "invalid", True),
        ("bad expiry", mutate(STANDING, "expires", "soon"), "invalid", True),
        ("expires before granted", mutate(STANDING, "expires", "2026-01-01T00:00:00Z"), "invalid", True),
        ("absolute path in ref", mutate(STANDING, "ref", f"/etc/authorizations.json@{COMMIT}#push"), "invalid", True),
        ("traversal in ref", mutate(STANDING, "ref", f"../authorizations.json@{COMMIT}#push"), "invalid", True),
        ("inner traversal in ref", mutate(STANDING, "ref", f"ops/../x.json@{COMMIT}#push"), "invalid", True),
        ("dot segment in ref", mutate(STANDING, "ref", f"./ops/authorizations.json@{COMMIT}#push"), "invalid", True),
        ("not an object", ["standing"], "invalid", True),
    ]
    for label, reference, want, has_problems in cases:
        problems, statuses = classify(reference)
        if statuses != [want] or bool(problems) != has_problems:
            failures.append(f"reference '{label}': expected {want}, got {statuses} with {problems}")
        if any(grants_authority(s, formats) for s in statuses):
            failures.append(f"reference '{label}': a structural check granted authority")

    # Handoffs: a quotation never authorizes; references in an invalid record are invalid.
    checker = Checker(formats)
    expect_ok("valid handoff", checker.check_text(handoff([STANDING, SESSION]), "h.md"))
    if [s for _, s, _ in checker.references] != ["unverified", "unverified"] or not checker.references[1][2]:
        failures.append(f"handoff reference statuses: {checker.references}")
    if any(grants_authority(s, formats) for _, s, _ in checker.references):
        failures.append("a handoff's quoted owner authorization granted authority")
    checker = Checker(formats)
    expect_bad("invalid handoff", checker.check_text(handoff([STANDING], drop="Branch"), "h.md"), "'Branch:' missing")
    if [s for _, s, _ in checker.references] != ["invalid"]:
        failures.append(f"a reference inside an invalid handoff was not invalid: {checker.references}")
    expect_bad("handoff duplicate JSON key", Checker(formats).check_text(handoff(
        '[{"level": "R2", "level": "R1"}]'), "h.md"), "duplicate key 'level'")
    expect_bad("handoff invalid reference", Checker(formats).check_text(handoff([mutate(STANDING, "level", "R3")]),
               "h.md"), "not one of R1,R2")
    expect_bad("handoff header", Checker(formats).check_text(handoff([], drop="Branch"), "h.md"), "'Branch:' missing")
    expect_bad("handoff HEAD", Checker(formats).check_text(handoff([], head="abc123"), "h.md"), "valid commit")
    expect_bad("handoff section", Checker(formats).check_text(handoff([], drop="Resume"), "h.md"), "'## Resume'")
    expect_bad("unlabelled item", Checker(formats).check_text(handoff([], done="- tests pass"), "h.md"),
               "no evidence label")
    expect_bad("VERIFIED without method", Checker(formats).check_text(handoff([], done="- [VERIFIED] tests pass; "
               f"artifact: commit {COMMIT}; at: 2026-11-27T19:40:00Z"), "h.md"), "lacks method:")
    expect_bad("VERIFIED bad time", Checker(formats).check_text(handoff([], done="- [VERIFIED] x; method: m; "
               "artifact: a; at: yesterday"), "h.md"), "not a UTC timestamp")
    expect_bad("handoff without JSON", Checker(formats).check_text(
        handoff([]).replace("```json\n[]\n```", "none"), "h.md"), "exactly one ```json block")
    job = {"id": "sweep-a", "kind": "process", "command": "python3 sweep.py", "started": "2026-11-27T18:00:00Z",
           "host": "h", "pid": 4242, "process_start": "lstart:Fri Nov 27 18:00:00 2026"}
    artifact = {"type": "file", "id": "results/summary.json", "sha256": "0" * 64}

    def extended(jobs, artifacts, transfer="none") -> str:
        text = handoff([]).replace("Supersedes: none", f"Transfer: {transfer}\nSupersedes: none")
        text = text.replace("## Running processes and jobs\n-", "## Running processes and jobs\n```json\n"
                            + json.dumps(jobs) + "\n```")
        return text.replace("## Verification", "## Artifacts\n```json\n" + json.dumps(artifacts) + "\n```\n\n"
                            "## Verification")
    expect_ok("handoff with jobs, artifacts and a transfer", Checker(formats).check_text(extended([job], [artifact]),
                                                                                         "h.md"))
    expect_ok("handoff with prose jobs and no artifacts section", Checker(formats).check_text(handoff([]), "h.md"))
    expect_bad("job with a PID but no start time", Checker(formats).check_text(
        extended([mutate(job, "process_start", None)], []), "h.md"), "must be null together")
    expect_bad("job of an unknown kind", Checker(formats).check_text(extended([mutate(job, "kind", "cron")], []),
                                                                      "h.md"), "not one of process")
    expect_bad("file artifact without a digest", Checker(formats).check_text(
        extended([], [mutate(artifact, "sha256", ...)]), "h.md"), "sha256: missing")
    expect_bad("empty transfer header", Checker(formats).check_text(extended([], [], transfer=""), "h.md"),
               "header 'Transfer'")
    with tempfile.TemporaryDirectory() as tmp:
        wrapped = Path(tmp) / "copy.json"
        wrapped.write_text('{"$generated": "Generated from x", "content": {"kind": "formats"}, "extra": 1}')
        try:
            read_json(wrapped)
            failures.append("a generated JSON copy with extra keys was accepted")
        except ValueError:
            pass
        wrapped.write_text('{"$generated": "Generated from x", "content": {"kind": "formats"}}')
        if read_json(wrapped) != {"kind": "formats"}:
            failures.append("a generated JSON copy was not unwrapped")
    expect_bad("two artifact blocks", Checker(formats).check_text(extended([], []).replace(
        "## Verification", "```json\n[]\n```\n## Verification"), "h.md"), "exactly one ```json block")

    # Runtime fixtures: Phase 1a checks the structural column only, and never grants authority.
    try:
        fixtures = read_json(RUNTIME_FIXTURES)
    except (OSError, ValueError) as e:
        return failures + [f"runtime fixtures cannot be read: {e}"]
    statuses = formats["authorization_statuses"]
    if fixtures.get("kind") != "authorization-fixtures" or type(fixtures.get("version")) is not int \
            or fixtures.get("version") != 1 or not isinstance(fixtures.get("cases"), list):
        return failures + ["runtime fixtures: incompatible file"]
    ids = [case.get("id") for case in fixtures["cases"] if isinstance(case, dict)]
    if len(ids) != len(set(ids)) or len(ids) != len(fixtures["cases"]):
        failures.append("runtime fixtures: case ids must be unique")
    for case in fixtures["cases"]:
        cid = case.get("id")
        if case.get("structural") not in statuses["structural"] or case.get("runtime") not in statuses["runtime"] \
                or not isinstance(case.get("reason"), str) or not case["reason"]:
            failures.append(f"runtime fixture {cid}: needs a structural status, a runtime status and a reason")
            continue
        _, got = classify(case.get("reference"))
        if got != [case["structural"]]:
            failures.append(f"runtime fixture {cid}: structural status {got}, expected {case['structural']}")
        if any(grants_authority(s, formats) for s in got):
            failures.append(f"runtime fixture {cid}: a structural check granted authority")
        if case["structural"] == "invalid" and case["runtime"] != "invalid":
            failures.append(f"runtime fixture {cid}: a structurally invalid reference must stay invalid at run time")
    if [c.get("runtime") for c in fixtures["cases"]].count("verified") != 1:
        failures.append("runtime fixtures: exactly one positive control (runtime 'verified') is expected")
    for cid, want in [("fabricated-reference", "invalid"), ("missing-entry", "invalid"), ("expired", "inapplicable"),
                      ("revoked", "inapplicable"), ("changed-after-approval", "inapplicable"),
                      ("quoted-session", "unknown")]:
        if not any(c.get("id") == cid and c.get("runtime") == want for c in fixtures["cases"]):
            failures.append(f"runtime fixtures: case {cid!r} must expect {want!r} at run time")
    return failures


def main() -> int:
    args = sys.argv[1:]
    if args == ["--self-test"]:
        failures = self_test()
        for f in failures:
            print("FAIL:", f)
        print("operational_records self-test: " + ("PASS" if not failures else f"{len(failures)} FAILED"))
        return 1 if failures else 0
    if not args or any(a.startswith("-") for a in args):
        print(__doc__.strip().split("\n\n")[1], file=sys.stderr)
        return 2
    checker = Checker(load_formats())
    problems = []
    for name in args:
        problems += checker.check_text(Path(name).read_text(encoding="utf-8"), name)
    for where, status, note in checker.references:
        print(f"authorization {where}: {status} (grants no authority)" + (f"; {note}" if note else ""))
    for p in problems:
        print("FAIL:", p)
    print(f"{len(args)} records: " + ("ALL VALID" if not problems else f"{len(problems)} PROBLEMS"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
