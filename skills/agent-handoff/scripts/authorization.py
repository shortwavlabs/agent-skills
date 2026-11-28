#!/usr/bin/env python3
"""Runtime verification of authorization references (RFC 0001: D6, D14; document 04, "Host-recorded approvals").

    authorization.py --self-test

The portable model is evaluate(reference, operation, facts, policy, now) -> (status, reason): a pure function. It
contacts nothing. The facts about the host come from github_facts.py (the narrow GitHub integration) or from the
fixtures in references/authorization-runtime.json. Statuses: invalid, verified, inapplicable, unknown. Only
`verified` grants authority, and only for the operation it was evaluated against.

The trusted policy (owners by stable account ID, trusted repositories) comes only from the owner-installed trust
policy, read by the generated copy of operational/trust_policy.py; without one, canonical_policy() returns None and
every standing reference evaluates to unknown: ask the owner once. A repository, a handoff record or a command-line
flag never supplies its own trust boundary. The result is advice: only the executor enforces.
Standard library only.
"""

from __future__ import annotations

import copy
import datetime
import fnmatch
import importlib.util
import json
import re
import sys
from pathlib import Path, PurePosixPath

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
PR_URL = re.compile(r"^https://github\.com/([^/\s]+)/([^/\s]+)/pull/([0-9]+)$")
RANK = {"R0": 0, "R1": 1, "R2": 2, "R3": 3}
DEFAULT_FILE = "ops/authorizations.json"             # the canonical policy may name another (RFC 0001, document 05)
# Operation field -> the scope key that limits it. Scope lives in standing entries (`scope`) and, only ever narrowing,
# in references (`limits`). Free-text descriptions are never consulted.
# The minimal completeness contract: what each class of consequential action must state, whatever its entry limits.
# Classes are recognised by the action's verb; each requirement is a tuple of alternatives. Future classes extend
# this table; an entry can never relax it.
CLASSES = [
    ("publication", ("publish-", "release-", "upload-", "deploy-"), [("destination",), ("target",)]),
    ("branch", ("push-", "rebase-", "delete-branch"), [("repository",), ("branch",)]),
    ("pull request", ("merge-", "open-", "mark-pr", "close-pr"), [("repository",), ("branch", "target")]),
    ("files", ("delete-", "edit-", "write-", "move-", "clean-", "remove-"), [("repository",), ("paths",)]),
    ("execution", ("run-", "trigger-", "start-", "stop-"), [("repository",), ("target", "purpose")]),
]
DEFAULT_REQUIREMENTS = [("repository",), ("target",)]
SPEND_REQUIREMENTS = [("cost_usd",), ("purpose", "target")]
DIMENSIONS = {"repository": "repositories", "branch": "branches", "paths": "paths", "destination": "destinations",
              "target": "targets", "purpose": "purposes", "cost_usd": "max_usd"}
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
    """(trusted policy, where it came from): the owner-installed trust policy (instruction-governance), loaded by the
    generated copy of operational/trust_policy.py next to this file. None when it is missing, invalid or insecure."""
    spec = importlib.util.spec_from_file_location("trust_policy_copy", HERE / "trust_policy.py")
    loader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loader)
    policy, where = loader.load()
    return policy, where if policy else f"no trust: {where}; ask the owner once"


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
    level = operation.get("level")
    if level not in RANK:
        return "unknown", ("the operation states no valid risk level (R0, R1 or R2): a missing level is never "
                           "permission; ask the owner once")
    if level == "R3":
        return "inapplicable", "R3 is never covered by a standing authorization: reconfirm with the owner"
    aspect = operation.get("aspect", "execute")
    if aspect not in ("execute", "spend"):
        return "unknown", f"the operation's aspect {aspect!r} is neither 'execute' nor 'spend'"
    if policy is None:
        return "unknown", ("no installed trust policy declares owner identities and trusted repositories: ask the "
                           "owner once")
    owners, trusted = set(policy.get("owners", [])), {r.lower() for r in policy.get("repositories", [])}
    path, commit, entry_id = parse_ref(reference["ref"])
    if not facts.get("host_reachable"):
        return "unknown", facts.get("why") or "the host cannot be reached now: ask the owner once"
    if facts.get("default_branch_moved") is not False and "default_branch_moved" in facts:
        return "unknown", "the default branch moved since the pinned revision: verify again against the current one"
    repository = str(facts.get("repository") or "").lower()
    if repository not in trusted:
        return "inapplicable", (f"{repository or 'this repository'} is not a trusted repository in the canonical "
                                "policy: an untrusted repository cannot establish its own trust boundary")
    files = policy.get("authorization_files") or {}
    designated = files.get(repository) or policy.get("authorizations_file", DEFAULT_FILE)
    if path != designated:
        return "invalid", (f"a standing reference must name the designated authorizations file {designated}, not "
                           f"{path}: an authorizations-shaped file elsewhere is not one")
    pinned_id = (policy.get("repository_ids") or {}).get(repository)
    if pinned_id is not None:
        if facts.get("repository_id") is None:
            return "unknown", "the repository's stable id is not recorded with the facts: ask the owner once"
        if facts["repository_id"] != pinned_id:
            return "inapplicable", (f"{repository} has another id than the trusted one: a recreated or replaced "
                                    "repository is not the trusted repository")
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
    account_ids = policy.get("owner_account_ids") or {}
    unpinned = sorted(set(owners) - set(account_ids))
    if unpinned:
        return "unknown", (f"the trust policy records no stable account id for {unpinned[0]}: a login alone never "
                           "establishes an owner")
    if approval.get("by_id") is None:
        return "unknown", f"the stable account id of {by} is not recorded with the approval: ask the owner once"
    if approval["by_id"] not in set(account_ids.values()):
        return "inapplicable", (f"the approving account ({by}, id {approval['by_id']}) is not an owner's account: a "
                                "login that matches an owner's name, renamed or reused, is not the owner")
    if state != "active":
        return "inapplicable", f"the owner's approval was {state}: a dismissed or superseded approval grants nothing"
    merged = approval.get("merged_into_default_branch")
    if merged is None:
        return "unknown", "whether the approved PR reached the default branch cannot be established: ask once"
    if merged is not True:
        return "inapplicable", "the approved PR's merge is not on the default branch: the entry there did not come from it"
    introduced = approval.get("introduced_entry")
    if introduced is None:
        return "unknown", "whether the approved PR introduced or changed this entry cannot be established: ask once"
    if introduced is not True:
        return "inapplicable", ("the approved PR did not introduce or change this entry: approving or merging an "
                                "unrelated PR approves nothing here")
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
    changed = facts.get("changed_after_approval")
    if changed is None:
        return "unknown", "whether the entry changed after its approval cannot be established: ask the owner once"
    if changed is not False:
        return "inapplicable", ("the entry changed on the default branch after its approval (even if restored since): "
                                "it needs fresh owner approval")
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
    if RANK[level] > RANK[entry["level"]]:
        return "inapplicable", f"the operation's level {level} exceeds the entry's level {entry['level']}"
    if entry.get("cost_only") and aspect != "spend":
        return "inapplicable", ("a cost-only authorization covers spending only, never the execution itself: the "
                                "execution needs its own authorization")
    incomplete = completeness_problem(operation)
    if incomplete:
        return "unknown", incomplete
    scope = entry.get("scope")
    if not isinstance(scope, dict):
        return "unknown", ("the entry has no structured scope (repositories, branches, paths, destinations, targets, "
                           "purposes, max_usd), so what it covers cannot be established: ask the owner once")
    target_repository = str(operation.get("repository") or "").lower()
    if target_repository and target_repository not in trusted:
        return "inapplicable", f"the operation's repository {target_repository} is not trusted by the canonical policy"
    for label, limits, holder in (("entry", scope, repository), ("reference", reference.get("limits"), None)):
        problem = scope_problem(limits, operation, holder, label) if limits is not None else None
        if problem:
            return problem
    if aspect == "spend":
        return "verified", (f"entry {entry_id} covers the spending of '{operation['action']}' only (cost-only "
                            f"or spend aspect): the execution itself needs its own authorization")
    return "verified", (f"entry {entry_id} granted by {by}, recorded by the host as a {kind} in {entry['approved_in']}, "
                        f"unchanged at the approved revision and on the default branch, covers '{operation['action']}' "
                        f"until {entry['expires']}")


def completeness_problem(operation: dict) -> str | None:
    """Which required parameter a consequential operation leaves out, or None."""
    action = operation["action"]
    name, required = next(((n, r) for n, verbs, r in CLASSES if action.startswith(verbs)), ("other", DEFAULT_REQUIREMENTS))
    if operation.get("aspect") == "spend" or operation.get("cost_usd") is not None:
        required = required + SPEND_REQUIREMENTS
        name += " with spending"
    for alternatives in required:
        if all(operation.get(f) in (None, [], "") for f in alternatives):
            return (f"the operation is incomplete: a {name} operation must state its {' or '.join(alternatives)}; "
                    "missing information is never permission")
    return None


def matches(key: str, value: str, allowed: str) -> bool:
    """Exact or glob matching only: branches and paths take glob patterns (`*` crosses `/`), repositories compare
    case-insensitively and never by wildcard, the rest compare exactly ("*" explicitly allows any value)."""
    if key in ("branches", "paths"):
        return fnmatch.fnmatchcase(value, allowed)
    if key == "repositories":
        return value.lower() == allowed.lower()
    return allowed == "*" or value == allowed


def scope_problem(scope: dict, operation: dict, holder: str | None, label: str) -> tuple[str, str] | None:
    """Why the operation is not inside a scope, or None. Every dimension the operation states must be limited by the
    entry, and every dimension the entry or the reference limits must be stated by the operation. An entry applies
    to the repository that holds it unless it names repositories; a reference can only narrow."""
    for field, key in DIMENSIONS.items():
        stated = operation.get(field)
        if key in scope:
            allowed = scope[key]
        elif field == "repository" and holder:
            allowed = [holder]
        elif label == "reference" or stated in (None, [], ""):
            continue
        else:
            return "unknown", (f"the entry does not limit {field}, so whether it covers {stated!r} cannot be "
                               "established: ask the owner once")
        if stated in (None, [], ""):
            return "unknown", f"the operation does not state its {field}, which the {label} limits: ask the owner once"
        if key == "max_usd":
            if isinstance(stated, bool) or not isinstance(stated, (int, float)) or not 0 <= stated < float("inf"):
                return "unknown", f"the operation's cost {stated!r} is not an amount in USD"
            if stated > allowed:
                return "inapplicable", f"the operation's cost of USD {stated} exceeds the {label}'s limit of USD {allowed}"
            continue
        values = stated if field == "paths" else [stated]
        if not isinstance(values, list) or not all(isinstance(v, str) and v for v in values):
            return "unknown", f"the operation's {field} is malformed"
        for value in values:
            if field == "paths" and (value.startswith("/") or "\\" in value or ".." in PurePosixPath(value).parts
                                     or value != PurePosixPath(value).as_posix()):
                return "unknown", f"path {value!r} is not a canonical relative path"
            if not any(isinstance(a, str) and matches(key, value, a) for a in allowed):
                return "inapplicable", f"the operation's {field} {value!r} is outside the {label}'s {key} {allowed}"
    return None


def evaluate_case(case: dict, fixtures: dict) -> tuple[str, str]:
    policy = case["policy"] if "policy" in case else fixtures["trusted_policy"]
    return evaluate(case["reference"], case["request"], case["state"], policy, when(fixtures["now"]))


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
    control = next((c for c in fixtures["cases"] if c["id"] == "verified-control"), None)
    if control is None:
        return failures + ["no positive control"]
    # Invariants: taking away any single piece of evidence from the positive control never leaves it verified.
    now = when(fixtures["now"])
    policy = fixtures["trusted_policy"]

    def status_with(edit) -> str:
        case = copy.deepcopy(control)
        edit(case)
        return evaluate(case["reference"], case["request"], case["state"], case.get("policy", policy), now)[0]
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
        "action": lambda c: c["request"].pop("action"),
        "risk level": lambda c: c["request"].pop("level"),
        "valid risk level": lambda c: c["request"].update(level="high"),
        "R3 operation": lambda c: c["request"].update(level="R3"),
        "level above entry": lambda c: (c["state"]["entry_at_reference"].update(level="R1"),
                                        c["reference"].update(level="R1"), c["request"].update(level="R2")),
        "structured scope": lambda c: c["state"]["entry_at_reference"].pop("scope"),
        "branch inside the scope": lambda c: c["request"].update(branch="main"),
        "stated branch": lambda c: c["request"].pop("branch"),
        "destination inside the scope": lambda c: c["request"].update(destination="upstream"),
        "repository inside the scope": lambda c: c["request"].update(repository="github.com/example/other"),
        "unlimited dimension": lambda c: c["request"].update(purpose="release"),
        "cost limit": lambda c: c["request"].update(cost_usd=5),
        "narrowing reference": lambda c: c["reference"].update(limits={"branches": ["feature/*"]}),
        "cost-only entry": lambda c: c["state"]["entry_at_reference"].update(cost_only=True),
        "a trusted repository holding the entry": lambda c: (
            c["state"].update(repository="github.com/other/repo"),
            c["state"]["entry_at_reference"].update(approved_in="https://github.com/other/repo/pull/1"),
            c["state"]["entry_at_reference"]["scope"].update(repositories=["github.com/example/repo"])),
        "the entry's own repository by default": lambda c: (
            c.update(policy={"owners": policy["owners"], "repositories": [*policy["repositories"],
                                                                          "github.com/example/second"]}),
            c["request"].update(repository="github.com/example/second")),
        "trusted operation repository": lambda c: (
            c["state"]["entry_at_reference"]["scope"].update(repositories=["github.com/example/untrusted"]),
            c["request"].update(repository="github.com/example/untrusted")),
        "merge on the default branch": lambda c: c["state"]["approval"].pop("merged_into_default_branch"),
        "change history": lambda c: c["state"].pop("changed_after_approval"),
        "pinned revision": lambda c: c["state"].update(default_branch_moved=True),
        "grantor": lambda c: (c["state"]["entry_at_reference"].update(granted_by="github:someone-else"),
                              c["reference"].update(by="github:someone-else")),
        "well-formed reference": lambda c: c["reference"].pop("scope"),
        "approval state": lambda c: c["state"]["approval"].update(state="superseded"),
        "approval binding": lambda c: c["state"]["approval"].pop("introduced_entry"),
        "designated file": lambda c: c["reference"].update(ref=c["reference"]["ref"].replace("ops/", "docs/", 1)),
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
    # Missing evidence is unknown, not a guess either way; the reasons tell the agent what to do.
    for label, edit, want in [
            ("approval binding", lambda c: c["state"]["approval"].pop("introduced_entry"), "unknown"),
            ("reinstatement", lambda c: c["state"].pop("reinstated_after_approval"), "unknown"),
            ("approved revision", lambda c: c["state"]["approval"].pop("entry_at_approved_revision"), "unknown"),
            ("commit", lambda c: c["state"].pop("commit_exists"), "unknown"),
            ("merge on the default branch", lambda c: c["state"]["approval"].pop("merged_into_default_branch"),
             "unknown"),
            ("change history", lambda c: c["state"].pop("changed_after_approval"), "unknown")]:
        if status_with(edit) != want:
            failures.append(f"positive control without its {label}: expected {want}, got {status_with(edit)}")

    def reason_with(edit) -> str:
        case = copy.deepcopy(control)
        edit(case)
        return evaluate(case["reference"], case["request"], case["state"], case.get("policy", policy), now)[1]
    if "does not state its destination" not in reason_with(lambda c: c["request"].pop("destination")):
        failures.append("an unstated, limited dimension is not reported as unstated")
    if "must state its branch" not in reason_with(lambda c: c["request"].pop("branch")):
        failures.append("an incomplete branch operation is not reported as incomplete")
    if "reconfirm with the owner" not in reason_with(lambda c: c["request"].update(level="R3")):
        failures.append("an R3 operation is not sent back to the owner for reconfirmation")
    missing = next(c for c in fixtures["cases"] if c["id"] == "missing-entry")
    if "holds no entry" not in evaluate_case(missing, fixtures)[1]:
        failures.append("a missing entry is not reported as missing")
    if status_with(lambda c: c["state"]["entry_at_reference"].update(expires="task-end")) != "unknown":
        failures.append("a standing entry expiring at task-end was not unknown")
    if status_with(lambda c: c["request"].update(level="R1")) != "verified":
        failures.append("an operation below the entry's level is not covered")
    # Owners are established by stable account id; the login is a label. Repositories compare case-insensitively.
    if status_with(lambda c: c["state"]["approval"].update(by="github:Example-Owner")) != "verified":
        failures.append("the owner's account, under another spelling of its login, was not recognised by its id")
    if status_with(lambda c: c["state"]["approval"].update(by_id=1001)) == "verified":
        failures.append("the owner's login on another account was accepted")
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
