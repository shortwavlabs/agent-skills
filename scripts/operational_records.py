#!/usr/bin/env python3
"""Check operational records against operational/formats.json (RFC 0001, document 05).

    python3 scripts/operational_records.py FILE...    exit 0 when every file is valid
    python3 scripts/operational_records.py --self-test

JSON records are checked by their `kind` and `version`; Markdown records by their title (`# Handoff: ...`). A version
the definitions do not list is reported as incompatible, never guessed at. Every authorization reference is
classified as established (a `standing` reference, well formed), unestablished (`owner-session`: the receiving agent
asks the owner once) or invalid. This checks form only: a well-formed reference can still point to nothing, so
authenticity is checked at run time, by the skill that relies on it. Standard library only.
"""

from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORMATS = ROOT / "operational" / "formats.json"
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")
EXPIRY_WORDS = ("task-end", "until revoked")


def load_formats(path: Path = FORMATS) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_timestamp(value) -> datetime.datetime | None:
    if not isinstance(value, str) or not TIMESTAMP.match(value):
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class Checker:
    """Checks records against one set of definitions. `references` collects (where, status) for every authorization
    reference seen: established, unestablished or invalid."""

    def __init__(self, formats: dict, known_skills: set[str] | None = None):
        self.f = formats
        self.known_skills = known_skills
        self.references: list[tuple[str, str]] = []

    def check_type(self, value, t: str, where: str, problems: list[str]) -> None:
        if t.endswith("?"):
            if value is None:
                return
            t = t[:-1]
        if t == "any":
            return
        if t.startswith(("list:", "list+:")):
            if not isinstance(value, list):
                problems.append(f"{where}: expected a list")
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
            if value not in t[5:].split(","):
                problems.append(f"{where}: {value!r} is not one of {t[5:]}")
            return
        if t == "int":
            if not isinstance(value, int) or isinstance(value, bool):
                problems.append(f"{where}: expected an integer, got {value!r}")
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

    def check_fields(self, value, spec: dict, where: str, problems: list[str]) -> str | None:
        """Checks an object against a spec; returns the status its matching case declares, if any."""
        if not isinstance(value, dict):
            problems.append(f"{where}: expected an object")
            return None
        for name, t in spec.get("required", {}).items():
            if name not in value:
                problems.append(f"{where}.{name}: missing")
            else:
                self.check_type(value[name], t, f"{where}.{name}", problems)
        for name, t in spec.get("optional", {}).items():
            if name in value:
                self.check_type(value[name], t, f"{where}.{name}", problems)
        status = None
        for field, cases in spec.get("cases", {}).items():
            case = cases.get(value.get(field)) if isinstance(value.get(field), str) else None
            for name, t in (case or {}).get("required", {}).items():
                if name not in value:
                    problems.append(f"{where}.{name}: missing (required when {field} is {value[field]!r})")
                else:
                    self.check_type(value[name], t, f"{where}.{name}", problems)
            status = (case or {}).get("status", status)
        for group in spec.get("null_together", []):
            if len({value.get(name) is None for name in group}) > 1:
                problems.append(f"{where}: {' and '.join(group)} must be null together")
        for later, earlier in spec.get("after", []):
            a, b = parse_timestamp(value.get(later)), parse_timestamp(value.get(earlier))
            if a and b and a <= b:
                problems.append(f"{where}.{later}: must be after {earlier}")
        for field, key in spec.get("unique", {}).items():
            keys = [item.get(key) for item in value.get(field, []) if isinstance(item, dict)] \
                if isinstance(value.get(field), list) else []
            duplicates = sorted({k for k in keys if k is not None and keys.count(k) > 1})
            if duplicates:
                problems.append(f"{where}.{field}: duplicate {key} {duplicates}")
        return status

    def check_object(self, value, name: str, where: str, problems: list[str]) -> None:
        spec = self.f["objects"].get(name)
        if spec is None:
            problems.append(f"{where}: unknown object type {name!r} in the format definitions")
            return
        before = len(problems)
        status = self.check_fields(value, spec, where, problems)
        if name == "authorization-reference":
            self.references.append((where, "invalid" if len(problems) > before else (status or "invalid")))

    def check_json(self, record, where: str) -> list[str]:
        kind = record.get("kind") if isinstance(record, dict) else None
        spec = self.f["json"].get(kind) if isinstance(kind, str) else None
        if spec is None:
            return [f"{where}: unknown kind {kind!r}"]
        version = record.get("version")
        if isinstance(version, bool) or version not in spec["versions"]:
            return [f"{where}: incompatible {kind} version {version!r} (supported: {spec['versions']})"]
        problems: list[str] = []
        self.check_fields(record, spec, where, problems)
        if kind == "scenario" and self.known_skills is not None:
            for skill in record.get("skills", []):
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
        headers = {}
        for line in lines[1:first_section]:
            m = re.match(r"^([A-Za-z][A-Za-z ]*):\s*(.*)$", line)
            if m:
                headers[m.group(1)] = m.group(2).strip()
        version = headers.get("Version", "")
        if not version.isdigit() or int(version) not in spec["versions"]:
            return problems + [f"{where}: incompatible handoff Version {version!r} (supported: {spec['versions']})"]
        for key, t in spec["headers"].items():
            if key not in headers:
                problems.append(f"{where}: header '{key}:' missing")
            else:
                self.check_type(headers[key], t, f"{where}: header '{key}'", problems)
        sections: dict[str, list[str]] = {}
        current = None
        for line in lines[first_section:]:
            if line.startswith("## "):
                current = line[3:].strip()
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
        for heading, t in spec["json_sections"].items():
            blocks = re.findall(r"```json\n(.*?)\n```", "\n".join(sections.get(heading, [])), re.S)
            if len(blocks) != 1:
                problems.append(f"{where}: '## {heading}' needs exactly one ```json block")
                continue
            try:
                value = json.loads(blocks[0])
            except ValueError as e:
                problems.append(f"{where}: the JSON under '## {heading}' does not parse: {e}")
                continue
            self.check_type(value, t, f"{where}: {heading}", problems)
        return problems

    def check_text(self, text: str, name: str) -> list[str]:
        if name.endswith(".json"):
            try:
                record = json.loads(text)
            except ValueError as e:
                return [f"{name}: not valid JSON: {e}"]
            return self.check_json(record, name)
        if name.endswith(".md"):
            if text.startswith("# Handoff:"):
                return self.check_handoff(text, name)
            return [f"{name}: not a known Markdown record (expected '# Handoff: ...')"]
        return [f"{name}: not a .json or .md record"]


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
    "authorizations": {"kind": "authorizations", "version": 1, "owners": ["github:example-owner"], "authorizations": [
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


def handoff(authorizations: list, done: str = "- [VERIFIED] Tests pass; method: make test exit 0; "
            f"artifact: commit {COMMIT}; at: 2026-11-27T19:40:00Z", head: str = COMMIT, version: str = "1",
            drop: str = "") -> str:
    headers = {"Version": version, "Created": "2026-11-27T18:40:00Z", "Author": "a / m / s", "Repository": "origin",
               "Branch": "b", "HEAD": head, "Upstream": "in sync", "Working tree": "clean", "PR": "none",
               "Claim": "none", "Supersedes": "none"}
    sections = {"Goal": "g", "State": "s", "Done": done, "Pending": "1. p", "Decisions and rejected approaches": "-",
                "Blockers and decisions needed": "-", "Authorizations in force":
                "```json\n" + json.dumps(authorizations) + "\n```", "Running processes and jobs": "-",
                "Verification": "v", "Assumptions and limitations": "- [INFERRED] x (premises: y)", "Resume": "1. r"}
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

    # Malformed records.
    expect_bad("malformed JSON", Checker(formats).check_text('{"kind": "claim", ', "x.json"), "not valid JSON")
    expect_bad("unknown kind", problems_of({"kind": "receipt", "version": 1}), "unknown kind")
    expect_bad("missing field", problems_of(mutate(VALID["verification"], "claim", ...)), ".claim: missing")
    expect_bad("empty string", problems_of(mutate(VALID["verification"], "method", " ")), "non-empty string")
    expect_bad("label", problems_of(mutate(VALID["verification"], "label", "CONFIRMED")), "not an evidence label")
    expect_bad("timestamp", problems_of(mutate(VALID["verification"], "verified_at", "2026-13-01T00:00:00Z")),
               "not a UTC timestamp")
    expect_bad("artifact commit", problems_of(mutate(VALID["verification"], "artifact.id", "abc123")), "valid commit")
    expect_bad("artifact file needs sha256",
               problems_of(mutate(VALID["verification"], "artifact", {"type": "file", "id": "a.txt"})), "sha256")
    expect_bad("int type", problems_of(mutate(VALID["claim"], "holder.pid", "42")), "expected an integer")
    expect_bad("enum", problems_of(mutate(VALID["claim"], "mode", "write")), "not one of")
    expect_bad("expires after created", problems_of(mutate(VALID["claim"], "expires", "2026-11-27T18:00:00Z")),
               "must be after created")
    expect_bad("pid and start null together", problems_of(mutate(VALID["claim"], "holder.pid", None)),
               "null together")
    expect_ok("holder unknown (both null)",
              problems_of(mutate(mutate(VALID["claim"], "holder.pid", None), "holder.process_start", None)))
    expect_bad("empty paths scope", problems_of(mutate(VALID["claim"], "scope.value", [])), "must not be empty")
    expect_bad("duplicate standing ids", problems_of(mutate(VALID["authorizations"], "authorizations",
               VALID["authorizations"]["authorizations"] * 2)), "duplicate id")
    expect_bad("standing R3", problems_of(mutate(VALID["authorizations"], "authorizations.0.level", "R3")),
               "not one of R1,R2")
    expect_bad("no owners", problems_of(mutate(VALID["authorizations"], "owners", [])), "must not be empty")
    expect_bad("unknown skill", problems_of(mutate(VALID["scenario"], "skills", ["no-such-skill"])), "no skill named")
    expect_bad("scenario id", problems_of(mutate(VALID["scenario"], "id", "clean-2")), "valid scenario-id")

    # Incompatible versions.
    expect_bad("version 2", problems_of(mutate(VALID["verification"], "version", 2)), "incompatible")
    expect_bad("version true", problems_of(mutate(VALID["claim"], "version", True)), "incompatible")
    expect_bad("version string", problems_of(mutate(VALID["scenario"], "version", "1")), "incompatible")
    expect_bad("handoff Version 2", Checker(formats).check_handoff(handoff([], version="2"), "h.md"), "incompatible")

    # Authorization references: established, unestablished, invalid.
    def classify(reference) -> tuple[list[str], list[str]]:
        checker = Checker(formats)
        problems: list[str] = []
        checker.check_object(reference, "authorization-reference", "ref", problems)
        return problems, [status for _, status in checker.references]

    cases = [
        ("standing", STANDING, "established", False),
        ("owner-session with quote", SESSION, "unestablished", False),
        ("unapproved source", mutate(STANDING, "source", "owner-comment"), "invalid", True),
        ("quote only, no source", {k: v for k, v in SESSION.items() if k != "source"}, "invalid", True),
        ("short commit in ref", mutate(STANDING, "ref", "ops/authorizations.json@abc123#push"), "invalid", True),
        ("ref without entry id", mutate(STANDING, "ref", f"ops/authorizations.json@{COMMIT}"), "invalid", True),
        ("R3 never transfers", mutate(STANDING, "level", "R3"), "invalid", True),
        ("missing scope", mutate(STANDING, "scope", ...), "invalid", True),
        ("bad identity", mutate(STANDING, "by", "example-owner"), "invalid", True),
        ("bad expiry", mutate(STANDING, "expires", "soon"), "invalid", True),
    ]
    for label, reference, want, has_problems in cases:
        problems, statuses = classify(reference)
        if statuses != [want] or bool(problems) != has_problems:
            failures.append(f"reference '{label}': expected {want}, got {statuses} with {problems}")

    # Handoff records.
    expect_ok("valid handoff", Checker(formats).check_handoff(handoff([STANDING, SESSION]), "h.md"))
    checker = Checker(formats)
    checker.check_handoff(handoff([STANDING, SESSION]), "h.md")
    if [s for _, s in checker.references] != ["established", "unestablished"]:
        failures.append(f"handoff reference statuses: {checker.references}")
    expect_bad("handoff invalid reference", Checker(formats).check_handoff(handoff([mutate(STANDING, "level", "R3")]),
               "h.md"), "not one of R1,R2")
    expect_bad("handoff header", Checker(formats).check_handoff(handoff([], drop="Branch"), "h.md"), "'Branch:' missing")
    expect_bad("handoff HEAD", Checker(formats).check_handoff(handoff([], head="abc123"), "h.md"), "valid commit")
    expect_bad("handoff section", Checker(formats).check_handoff(handoff([], drop="Resume"), "h.md"), "'## Resume'")
    expect_bad("unlabelled item", Checker(formats).check_handoff(handoff([], done="- tests pass"), "h.md"),
               "no evidence label")
    expect_bad("VERIFIED without method", Checker(formats).check_handoff(handoff([], done="- [VERIFIED] tests pass; "
               f"artifact: commit {COMMIT}; at: 2026-11-27T19:40:00Z"), "h.md"), "lacks method:")
    expect_bad("VERIFIED bad time", Checker(formats).check_handoff(handoff([], done="- [VERIFIED] x; method: m; "
               "artifact: a; at: yesterday"), "h.md"), "not a UTC timestamp")
    expect_bad("handoff without JSON", Checker(formats).check_handoff(
        handoff([]).replace("```json\n[]\n```", "none"), "h.md"), "exactly one ```json block")
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
    for where, status in checker.references:
        if status == "unestablished":
            print(f"note: {where}: unestablished authorization (the receiving agent asks the owner once)")
    for p in problems:
        print("FAIL:", p)
    print(f"{len(args)} records: " + ("ALL VALID" if not problems else f"{len(problems)} PROBLEMS"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
