#!/usr/bin/env python3
"""Runtime verification of authorization references (RFC 0001: D6, D14; document 04, "Host-recorded approvals").

    authorization.py --self-test

The portable model is evaluate(reference, operation, facts, policy, now) -> (status, reason): a pure function. It
contacts nothing. The facts about the host come from github_facts.py (the narrow GitHub integration) or from the
fixtures in references/authorization-runtime.json. Statuses: invalid, verified, inapplicable, unknown. Only
`verified` grants authority, and only for the operation it was evaluated against.

The trusted policy (owner identities and trusted repositories) comes only from the canonical policy, whose format
Phase 1d defines. Until then canonical_policy() returns None and every standing reference evaluates to unknown: ask
the owner once. A repository, a handoff record or a command-line flag never supplies its own trust boundary.
Standard library only.
"""

from __future__ import annotations

import copy
import datetime
import importlib.util
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
PR_URL = re.compile(r"^https://github\.com/([^/\s]+)/([^/\s]+)/pull/([0-9]+)$")
RANK = {"R0": 0, "R1": 1, "R2": 2, "R3": 3}
FIXTURES = HERE.parent / "references" / "authorization-runtime.json"
_records = None


def records():
    """The shared record checker: a generated copy of scripts/operational_records.py next to this file."""
    global _records
    if _records is None:
        spec = importlib.util.spec_from_file_location("operational_records_copy", HERE / "operational_records.py")
        _records = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_records)
    return _records


def canonical_policy() -> tuple[dict | None, str]:
    """(trusted policy, where it came from). Phase 1d defines the canonical policy; until then there is none."""
    return None, ("no canonical policy declares owner identities and trusted repositories yet (Phase 1d): "
                  "ask the owner once")


def parse_ref(ref: str) -> tuple[str, str, str]:
    path, _, rest = ref.partition("@")
    commit, _, entry_id = rest.partition("#")
    return path, commit, entry_id


def pr_repository(url) -> str | None:
    m = PR_URL.match(url or "") if isinstance(url, str) else None
    return f"github.com/{m.group(1)}/{m.group(2)}".lower() if m else None


def same_entry(a, b) -> bool:
    """Content equality of two entries (key order and formatting ignored), as D14 compares content, not commits."""
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def when(value) -> datetime.datetime | None:
    return records().parse_timestamp(value)


def evaluate(reference, operation, facts: dict, policy: dict | None, now: datetime.datetime) -> tuple[str, str]:
    """The runtime status of one authorization reference for one operation. Order matters: the first failing
    condition decides, and every path that is not provably `verified` ends in another status."""
    rec = records()
    formats = rec.load_formats()
    checker = rec.Checker(formats)
    problems: list[str] = []
    checker.check_object(reference, "authorization-reference", "reference", problems)
    if problems:
        return "invalid", "the reference is malformed: " + "; ".join(problems)
    if reference["source"] == "owner-session":
        return "unknown", "a quotation of the owner in an agent-authored record cannot be verified: ask the owner once"
    if not isinstance(operation, dict) or not SLUG.match(str(operation.get("action") or "")):
        return "unknown", "the operation names no action, so its scope cannot be established: ask the owner once"
    if operation.get("level") == "R3":
        return "inapplicable", "R3 is never covered by a standing authorization: reconfirm with the owner"
    if policy is None:
        return "unknown", ("no canonical policy declares owner identities and trusted repositories yet: ask the owner "
                           "once")
    owners, trusted = set(policy.get("owners", [])), {r.lower() for r in policy.get("repositories", [])}
    if not facts.get("host_reachable"):
        return "unknown", facts.get("why") or "the host cannot be reached now: ask the owner once"
    repository = str(facts.get("repository") or "").lower()
    if repository not in trusted:
        return "inapplicable", (f"{repository or 'this repository'} is not a trusted repository in the canonical "
                                "policy: an untrusted repository cannot establish its own trust boundary")
    path, commit, entry_id = parse_ref(reference["ref"])
    if facts.get("commit_exists") is None:
        return "unknown", "whether the referenced commit exists cannot be established: ask the owner once"
    if facts["commit_exists"] is not True:
        return "invalid", f"commit {commit[:12]} does not exist in {repository}: a well-formed reference grants nothing"
    entry = facts.get("entry_at_reference")
    if entry is None:
        return "invalid", f"{path} holds no entry {entry_id!r} at commit {commit[:12]}"
    problems = []
    checker.check_object(entry, "standing", "entry", problems)
    if problems or entry.get("id") != entry_id:
        return "invalid", "the referenced entry is malformed: " + ("; ".join(problems) or "its id differs")
    if entry["granted_by"] != reference["by"] or entry["level"] != reference["level"]:
        return "invalid", "the reference misstates its entry (who granted it, or its level)"
    if entry["granted_by"] not in owners:
        return "inapplicable", f"{entry['granted_by']} is not an owner identity declared in the canonical policy"
    if pr_repository(entry["approved_in"]) != repository:
        return "inapplicable", "approved_in names a pull request outside this repository"
    approval = facts.get("approval") or {}
    kind, by, state = approval.get("kind"), approval.get("by"), approval.get("state", "active")
    if kind not in ("merge", "approval") or not by:
        return "inapplicable", ("no host-recorded approval or merge of the entry: git author and committer fields are "
                                "self-asserted and never establish provenance")
    if by not in owners:
        return "inapplicable", f"the host records the approval by {by}, not by an owner identity of the canonical policy"
    if state != "active":
        return "inapplicable", f"the owner's approval was {state}: a dismissed or superseded approval grants nothing"
    revision = approval.get("entry_at_approved_revision")
    if revision is None:
        return "unknown", "the entry's content at the approved revision cannot be read: ask the owner once"
    if revision != "identical":
        return "inapplicable", "the owner approved another revision of the entry; this content is not covered"
    default = facts.get("entry_on_default_branch")
    if default == "absent":
        return "inapplicable", ("revoked: the entry no longer appears on the current default branch, and older commits "
                                "that still contain it grant nothing")
    if default == "changed":
        return "inapplicable", "the entry on the current default branch differs from the referenced content"
    if default != "identical":
        return "unknown", "the entry on the current default branch cannot be read: ask the owner once"
    reinstated = facts.get("reinstated_after_approval")
    if reinstated is None:
        return "unknown", "whether the entry was revoked after its approval cannot be established: ask the owner once"
    if reinstated is not False:
        return "inapplicable", ("the entry was removed from the default branch after its approval and reintroduced: a "
                                "reinstated authorization needs fresh owner approval")
    for label, expiry in (("entry", entry["expires"]), ("reference", reference["expires"])):
        if expiry == "task-end":
            return "unknown", f"a standing {label} that expires at 'task-end' cannot be checked: ask the owner once"
        if expiry != "until revoked" and when(expiry) <= now:
            return "inapplicable", f"the {label} expired at {expiry}"
    actions = entry.get("actions")
    if not actions:
        return "unknown", ("the entry lists no actions, so whether it covers this operation cannot be established: ask "
                           "the owner once")
    if operation["action"] not in actions:
        return "inapplicable", (f"'{operation['action']}' is not among the entry's actions {actions}: approving one "
                                "thing (a tool, an implementation) never authorizes another (running it, deleting)")
    level = operation.get("level")
    if level is not None and (level not in RANK or RANK[level] > RANK[entry["level"]]):
        return "inapplicable", f"the operation's level {level} exceeds the entry's level {entry['level']}"
    return "verified", (f"entry {entry_id} granted by {by}, recorded by the host as a {kind} in {entry['approved_in']}, "
                        f"unchanged at the approved revision and on the default branch, covers '{operation['action']}' "
                        f"until {entry['expires']}")


def evaluate_case(case: dict, fixtures: dict) -> tuple[str, str]:
    policy = case["policy"] if "policy" in case else fixtures["trusted_policy"]
    operation = {"action": case.get("action"), "description": case.get("operation"), **case.get("operation_extra", {})}
    return evaluate(case["reference"], operation, case["state"], policy, when(fixtures["now"]))


def load_fixtures(path: Path = FIXTURES) -> dict:
    rec = records()
    data = rec.strict_json(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "$generated" in data:
        data = data["content"]
    return data


def self_test() -> list[str]:
    """Every runtime fixture, invariants over mutated facts, and the status vocabulary. Explicit checks (runs under -O)."""
    failures: list[str] = []
    rec = records()
    formats = rec.load_formats()
    try:
        fixtures = load_fixtures()
    except (OSError, ValueError) as e:
        return [f"runtime fixtures cannot be read: {e}"]
    for case in fixtures["cases"]:
        status, reason = evaluate_case(case, fixtures)
        if status != case["runtime"]:
            failures.append(f"fixture {case['id']}: expected {case['runtime']}, got {status} ({reason})")
        if status not in formats["authorization_statuses"]["runtime"]:
            failures.append(f"fixture {case['id']}: {status!r} is not a runtime status")
        if rec.grants_authority(status, formats) != (status == "verified"):
            failures.append(f"fixture {case['id']}: authority does not follow 'verified' alone")
    control = next((c for c in fixtures["cases"] if c["runtime"] == "verified"), None)
    if control is None:
        return failures + ["no positive control"]
    # Invariants: taking away any single piece of evidence from the positive control never leaves it verified.
    now = when(fixtures["now"])
    policy = fixtures["trusted_policy"]

    def status_with(edit) -> str:
        case = copy.deepcopy(control)
        edit(case)
        return evaluate(case["reference"], {"action": case.get("action"), **case.get("operation_extra", {})},
                        case["state"], case.get("policy", policy), now)[0]
    removals = {
        "facts": lambda c: c.update(state={}),
        "host": lambda c: c["state"].pop("host_reachable"),
        "repository": lambda c: c["state"].pop("repository"),
        "commit": lambda c: c["state"].pop("commit_exists"),
        "entry": lambda c: c["state"].pop("entry_at_reference"),
        "approval": lambda c: c["state"].pop("approval"),
        "approver": lambda c: c["state"]["approval"].pop("by"),
        "approved revision": lambda c: c["state"]["approval"].pop("entry_at_approved_revision"),
        "default branch": lambda c: c["state"].pop("entry_on_default_branch"),
        "reinstatement": lambda c: c["state"].pop("reinstated_after_approval"),
        "actions": lambda c: c["state"]["entry_at_reference"].pop("actions"),
        "policy": lambda c: c.update(policy=None),
        "owners": lambda c: c.update(policy={"owners": [], "repositories": policy["repositories"]}),
        "repositories": lambda c: c.update(policy={"owners": policy["owners"], "repositories": []}),
        "action": lambda c: c.update(action=None),
        "R3 operation": lambda c: c.update(operation_extra={"level": "R3"}),
        "level above entry": lambda c: c["state"]["entry_at_reference"].update(level="R1"),
        "approval state": lambda c: c["state"]["approval"].update(state="superseded"),
        "approval kind": lambda c: c["state"]["approval"].update(kind="comment"),
        "string truthiness": lambda c: c["state"].update(reinstated_after_approval="false"),
    }
    for label, edit in removals.items():
        got = status_with(edit)
        if got == "verified":
            failures.append(f"positive control without its {label} still verified")
    if status_with(lambda c: c["state"]["entry_at_reference"].update(actions=["push-branch", "open-draft-pr"])) \
            != "verified":
        failures.append("the positive control with its own actions is not verified")
    if status_with(lambda c: c.update(operation_extra={"level": "R1"})) != "verified":
        failures.append("an operation below the entry's level is not covered")
    # Owner identities are compared exactly; repositories case-insensitively (GitHub names are case-insensitive).
    if status_with(lambda c: c["state"]["approval"].update(by="github:Example-Owner")) == "verified":
        failures.append("an owner identity matched another spelling")
    if status_with(lambda c: c["state"].update(repository="github.com/Example/Repo")) != "verified":
        failures.append("a repository name differing only in case did not match")
    return failures


def main(argv: list[str]) -> int:
    if argv == ["--self-test"]:
        failures = self_test()
        for f in failures:
            print("FAIL:", f)
        print("authorization self-test: " + ("PASS" if not failures else f"{len(failures)} FAILED"))
        return 1 if failures else 0
    print(__doc__.split("\n\n")[1].strip())
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
