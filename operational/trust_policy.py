#!/usr/bin/env python3
"""The canonical trust policy: who the owner is, which repositories are trusted, and where their authorizations live.

    trust_policy.py verify [--path FILE]   report whether a trust policy is installed and valid (read-only)
    trust_policy.py remember               record the installed revision as reviewed (the owner, after reviewing it)
    trust_policy.py template               print an example policy for the owner to adapt (installs nothing)
    trust_policy.py --self-test

The trust root is established by the owner, outside anything an agent can write: a root-owned file, writable by no
one else, at the system location below. Installing it needs administrator rights (`sudo`), which agents do not have,
so finding it there is evidence the owner put it there. A policy in a repository, in the home directory, or anywhere
the agent's own account can write is never a trust root, whatever it claims about itself: `--path` inspects such a
file but never grants it authority. Missing, malformed, ambiguous or insecurely installed policy: no trust (unknown).
Nothing here expands trust automatically, installs a policy or changes credentials, and nothing here ever runs sudo.

What this protects, and what it does not: the root-owned file protects the trust configuration from being written
by the agent's account. It does not make this reader, the authorization evaluator or any agent skill a security
boundary: they run as the owner's user, can be modified by that user, and only advise. Execution is restricted only
by what actually executes (the harness's permission mode, the operating system, branch protection). A record of the
last reviewed revision (`remember`) catches rollback, silent replacement and trust expansion between reviews; it lives
in user space, so it is a tripwire, not a lock.

    macOS  /Library/Application Support/AgentOperations/trust-policy.json
    Linux  /etc/agent-operations/trust-policy.json

`instruction-governance` and `agent-handoff` carry byte-identical generated copies of this file (source:
operational/trust_policy.py). Standard library only.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
LOCATIONS = {"darwin": Path("/Library/Application Support/AgentOperations/trust-policy.json"),
             "linux": Path("/etc/agent-operations/trust-policy.json")}
IDENTITY = re.compile(r"^github:[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
SEEN = Path.home() / ".local" / "state" / "agent-operations" / "trust-policy-seen.json"
REPOSITORY = re.compile(r"^github\.com/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
SAFE_FILE = re.compile(r"^(?!.*(?:^|/)\.\.?(?:/|$))[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*\.json$")
TEMPLATE = {
    "kind": "trust-policy", "version": 1, "revision": 1, "previous_sha256": None,
    "owners": [{"identity": "github:<owner login, for readability>", "account_id": 0}],
    "agent_accounts": ["github:<an agent or bot account, never an owner>"],
    "repositories": [{"identity": "github.com/<owner>/<repository>", "repository_id": 0,
                      "authorizations_file": "ops/authorizations.json"}],
    "provenance": {"repository": "github.com/<owner>/<policy repository>", "path": "<path of the reviewed copy>",
                   "commit": "<40-hex commit id of the reviewed copy>"},
}


def location() -> Path | None:
    return LOCATIONS.get(sys.platform if sys.platform != "linux2" else "linux")


def secure(path: Path, trusted_uid: int, boundary: Path | None = None) -> str | None:
    """Why path cannot be the owner's trust root, or None. Every component from / down must be a real directory or
    file owned by trusted_uid (root) and writable by no group or other user: anyone who can write a parent could have
    replaced the file."""
    try:
        st = path.lstat()
    except FileNotFoundError:
        return "no trust policy is installed"
    except OSError as e:
        return f"the trust policy cannot be inspected: {e}"
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        return f"{path} is a symlink or not a regular file"
    chain = [path, *path.parents]
    if boundary is not None:                          # tests only: fixtures live below a directory the test owns
        chain = chain[:chain.index(boundary) + 1]
    for p in chain:
        try:
            s = p.lstat()
        except OSError as e:
            return f"{p} cannot be inspected: {e}"
        if stat.S_ISLNK(s.st_mode):
            return f"{p} is a symlink"
        if s.st_uid != trusted_uid:
            return f"{p} is not owned by the administrator: it could have been written without the owner"
        if s.st_mode & 0o022:
            return f"{p} is writable by others: it could have been replaced without the owner"
    return None


def problems_of(data) -> list[str]:
    """Semantic checks beyond the shared format: unique identities, owners and agents disjoint, safe file paths."""
    if not isinstance(data, dict):
        return ["not an object"]
    p = []
    if data.get("kind") != "trust-policy" or type(data.get("version")) is not int or data.get("version") != 1:
        return ["not a version 1 trust policy"]
    if type(data.get("revision")) is not int or data["revision"] < 1:
        p.append("revision must be a positive integer")
    prev = data.get("previous_sha256")
    if prev is not None and not (isinstance(prev, str) and re.fullmatch(r"[0-9a-f]{64}", prev)):
        p.append("previous_sha256 must be null or a SHA-256")
    if (data.get("revision") == 1) != (prev is None):
        p.append("revision 1 has no previous_sha256; every later revision names its predecessor")
    owners = data.get("owners")
    if not isinstance(owners, list) or not owners:
        p.append("owners must be a non-empty list")
        owners = []
    seen = set()
    for o in owners:
        if not isinstance(o, dict) or not IDENTITY.match(str(o.get("identity", ""))) \
                or type(o.get("account_id")) is not int or o["account_id"] < 1:
            p.append(f"malformed owner {o!r}: identity github:<login> and a positive account_id (the stable ID "
                     "establishes the owner; the login is only a label)")
            continue
        if o["identity"].lower() in seen:
            p.append(f"owner {o['identity']} is declared twice")
        seen.add(o["identity"].lower())
    agents = data.get("agent_accounts", [])
    if not isinstance(agents, list) or not all(isinstance(a, str) and IDENTITY.match(a) for a in agents):
        p.append("agent_accounts must be a list of github:<login> identities")
    elif seen & {a.lower() for a in agents}:
        p.append("an identity is declared both as an owner and as an agent account")
    repos = data.get("repositories")
    if not isinstance(repos, list) or not repos:
        p.append("repositories must be a non-empty list")
        repos = []
    names = set()
    for r in repos:
        if not isinstance(r, dict) or not REPOSITORY.match(str(r.get("identity", ""))) \
                or not SAFE_FILE.match(str(r.get("authorizations_file", "ops/authorizations.json"))) \
                or (r.get("repository_id") is not None and (type(r["repository_id"]) is not int or r["repository_id"] < 1)):
            p.append(f"malformed repository {r!r}: identity github.com/<owner>/<name>, a safe relative .json file")
            continue
        if r["identity"].lower() in names:
            p.append(f"repository {r['identity']} is declared twice")
        names.add(r["identity"].lower())
    unknown = set(data) - {"kind", "version", "revision", "previous_sha256", "owners", "agent_accounts",
                           "repositories", "provenance", "notes"}
    if unknown:
        p.append(f"unknown fields {sorted(unknown)}: a trust policy is never extended by guesswork")
    return p


def trust_set(data: dict) -> dict:
    return {"owners": sorted(o["account_id"] for o in data["owners"]),
            "repositories": sorted(f"{r['identity'].lower()}#{r.get('repository_id') or ''}" for r in data["repositories"])}


def succession_problem(data: dict, digest: str, seen: dict | None) -> str | None:
    """Why this revision may not follow the last reviewed one, or None. Rollback, a different policy under the same
    revision, a broken digest chain and any expansion of trust are refused until the owner reviews and records the
    revision (`remember`); a narrowing of trust is accepted at once."""
    if not seen:
        return None
    if data["revision"] < seen["revision"]:
        return f"rollback: revision {data['revision']} is older than revision {seen['revision']}, already reviewed"
    if data["revision"] == seen["revision"]:
        return None if digest == seen["sha256"] else \
            f"revision {data['revision']} was replaced by different content: review it and run remember"
    if data["revision"] == seen["revision"] + 1 and data.get("previous_sha256") != seen["sha256"]:
        return f"revision {data['revision']} does not name the reviewed revision {seen['revision']} as its predecessor"
    if data["revision"] > seen["revision"] + 1:
        return (f"revisions {seen['revision'] + 1}..{data['revision'] - 1} were never reviewed here: the chain cannot "
                "be checked; review it and run remember")
    old, new = seen.get("trust", {}), trust_set(data)
    added = {k: sorted(set(map(str, new[k])) - set(map(str, old.get(k, [])))) for k in new}
    if any(added.values()):
        return f"trust expanded since the reviewed revision ({added}): review it and run remember"
    return None


def read_seen(path: Path | None) -> dict | None:
    try:
        return json.loads(path.read_text()) if path and path.exists() else None
    except (OSError, ValueError):
        return {"revision": 10 ** 9, "sha256": "unreadable"}   # a damaged record trusts nothing until rewritten


def load(path: Path | None = None, trusted_uid: int = 0, boundary: Path | None = None,
         seen: Path | None = SEEN) -> tuple[dict | None, str]:
    """(policy in the evaluator's shape, where it came from) or (None, why there is none). trusted_uid exists for
    tests with fixture files, like boundary; the command line never changes either."""
    path = path or location()
    if path is None:
        return None, f"no trust policy location is defined for {sys.platform}"
    why = secure(path, trusted_uid, boundary)
    if why:
        return None, why
    try:
        raw = path.read_bytes()
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_pairs)
    except (OSError, UnicodeDecodeError, ValueError) as e:
        return None, f"the trust policy cannot be read: {e}"
    found = problems_of(data)
    if found:
        return None, "the trust policy is invalid: " + "; ".join(found)
    digest = hashlib.sha256(raw).hexdigest()
    why = succession_problem(data, digest, read_seen(seen))
    if why:
        return None, why
    policy = {"owners": [o["identity"] for o in data["owners"]],
              "owner_account_ids": {o["identity"]: o["account_id"] for o in data["owners"]},
              "repository_ids": {r["identity"].lower(): r["repository_id"] for r in data["repositories"]
                                 if r.get("repository_id")},
              "agent_accounts": list(data.get("agent_accounts", [])),
              "repositories": [r["identity"].lower() for r in data["repositories"]],
              "authorization_files": {r["identity"].lower(): r.get("authorizations_file", "ops/authorizations.json")
                                      for r in data["repositories"]},
              "revision": data["revision"], "sha256": digest}
    return policy, f"{path} (revision {data['revision']}, sha256 {digest[:12]})"


def remember(path: Path | None = None, seen: Path = SEEN, trusted_uid: int = 0, boundary: Path | None = None) -> str:
    """Record the installed, valid policy as reviewed. Run by the owner after reviewing a new revision."""
    path = path or location()
    why = secure(path, trusted_uid, boundary) if path else "no location"
    if why:
        raise SystemExit(f"error: {why}")
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8"), object_pairs_hook=_strict_pairs)
    found = problems_of(data)
    if found:
        raise SystemExit("error: the trust policy is invalid: " + "; ".join(found))
    seen.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    record = {"revision": data["revision"], "sha256": hashlib.sha256(raw).hexdigest(), "trust": trust_set(data)}
    seen.write_text(json.dumps(record, indent=2) + "\n")
    os.chmod(seen, 0o600)
    return f"recorded revision {data['revision']} as reviewed"


def _strict_pairs(items):
    out = {}
    for key, value in items:
        if key in out:
            raise ValueError(f"duplicate key {key!r}")
        out[key] = value
    return out


def self_test() -> list[str]:
    """Temporary fixtures only: the test user stands in for root below a boundary directory the test owns."""
    failures: list[str] = []
    me = os.getuid()
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp).resolve()
        os.chmod(base, 0o755)
        folder = base / "AgentOperations"
        folder.mkdir(mode=0o755)
        policy_file = folder / "trust-policy.json"
        seen = base / "seen.json"
        owner = {"identity": "github:example-owner", "account_id": 42}
        repo = {"identity": "github.com/Example/Repo", "repository_id": 7, "authorizations_file": "ops/authorizations.json"}
        good = {"kind": "trust-policy", "version": 1, "revision": 1, "previous_sha256": None, "owners": [owner],
                "agent_accounts": ["github:example-bot"], "repositories": [repo]}

        def write(data, mode=0o644):
            policy_file.write_text(json.dumps(data) if not isinstance(data, str) else data)
            os.chmod(policy_file, mode)
            return hashlib.sha256(policy_file.read_bytes()).hexdigest()

        def loaded(uid=me, seen_path=None):
            return load(policy_file, trusted_uid=uid, boundary=base, seen=seen_path)

        def expect(label, ok, uid=me, seen_path=None):
            policy, why = loaded(uid, seen_path)
            if (policy is not None) != ok:
                failures.append(f"{label}: expected {'trusted' if ok else 'no trust'}, got {why}")
            return policy
        write(good)
        policy = expect("a valid fixture policy", True)
        if policy and (policy["owner_account_ids"] != {"github:example-owner": 42}
                       or policy["repository_ids"] != {"github.com/example/repo": 7}
                       or policy["repositories"] != ["github.com/example/repo"]):
            failures.append(f"loaded policy shape: {policy}")
        # Ownership and permissions of the file and every directory up to the boundary.
        if me != 0:
            expect("a policy owned by the agent's own account, judged as the real trust root", False, uid=0)
        for label, setup, undo in [
                ("group-writable file", lambda: os.chmod(policy_file, 0o664), lambda: os.chmod(policy_file, 0o644)),
                ("world-writable file", lambda: os.chmod(policy_file, 0o646), lambda: os.chmod(policy_file, 0o644)),
                ("group-writable directory", lambda: os.chmod(folder, 0o775), lambda: os.chmod(folder, 0o755)),
                ("world-writable parent", lambda: os.chmod(base, 0o777), lambda: os.chmod(base, 0o755))]:
            setup()
            expect(label, False)
            undo()
        # Symlinks: the file, and a directory on the path.
        elsewhere = base / "elsewhere.json"
        elsewhere.write_text(json.dumps(good))
        policy_file.unlink()
        policy_file.symlink_to(elsewhere)
        expect("symlinked policy file", False)
        policy_file.unlink()
        real_folder = base / "real-folder"
        real_folder.mkdir(mode=0o755)
        (real_folder / "trust-policy.json").write_text(json.dumps(good))
        os.chmod(real_folder / "trust-policy.json", 0o644)
        linked = base / "linked"
        linked.symlink_to(real_folder)
        if load(linked / "trust-policy.json", trusted_uid=me, boundary=base, seen=None)[0] is not None:
            failures.append("a policy reached through a symlinked directory was trusted")
        # Missing, malformed, unsupported.
        expect("missing policy", False)
        for label, data in [
                ("unsupported version", {**good, "version": 2}), ("boolean version", {**good, "version": True}),
                ("wrong kind", {**good, "kind": "policy"}), ("not an object", [good]),
                ("owner without a stable account id", {**good, "owners": [{"identity": "github:example-owner"}]}),
                ("malformed repository id", {**good, "repositories": [{**repo, "repository_id": "7"}]}),
                ("missing owners", {**good, "owners": []}),
                ("owner who is also an agent account", {**good, "agent_accounts": ["github:Example-Owner"]}),
                ("duplicate owner", {**good, "owners": [owner, owner]}),
                ("unsafe authorizations file", {**good, "repositories": [{**repo, "authorizations_file": "../x.json"}]}),
                ("unknown field", {**good, "trust_everyone": True}),
                ("revision 2 without a predecessor", {**good, "revision": 2}),
                ("revision 1 with a predecessor", {**good, "previous_sha256": "0" * 64})]:
            write(data)
            expect(label, False)
        write('{"kind": "trust-policy", "kind": "trust-policy"}')
        expect("duplicate JSON keys", False)
        write("{not json")
        expect("unparseable policy", False)
        # Succession against the reviewed revision: rollback, replacement, chain, expansion.
        d1 = write(good)
        print_ok = remember(policy_file, seen, trusted_uid=me, boundary=base)
        if "revision 1" not in print_ok or stat.S_IMODE(seen.stat().st_mode) != 0o600:
            failures.append("remember did not record the reviewed revision privately")
        expect("the reviewed revision", True, seen_path=seen)
        write({**good, "notes": "same revision, other bytes"})
        expect("revision 1 replaced by other content", False, seen_path=seen)
        r2 = {**good, "revision": 2, "previous_sha256": d1}
        d2 = write(r2)
        expect("revision 2 naming revision 1 as predecessor", True, seen_path=seen)
        write({**r2, "previous_sha256": "f" * 64})
        expect("revision 2 naming another predecessor", False, seen_path=seen)
        write({**good, "revision": 3, "previous_sha256": "e" * 64})
        expect("a skipped revision", False, seen_path=seen)
        write({**r2, "owners": [owner, {"identity": "github:new-owner", "account_id": 77}]})
        expect("trust expanded by a new owner, unreviewed", False, seen_path=seen)
        write({**r2, "repositories": [repo, {"identity": "github.com/example/other"}]})
        expect("trust expanded by a new repository, unreviewed", False, seen_path=seen)
        write({**r2, "repositories": [{**repo, "repository_id": 8}]})
        expect("a recreated repository (new id), unreviewed", False, seen_path=seen)
        write(r2)
        remember(policy_file, seen, trusted_uid=me, boundary=base)
        write({**good, "revision": 3, "previous_sha256": d2, "agent_accounts": []})
        expect("revision 3 that only narrows trust", True, seen_path=seen)
        write(good)
        expect("rollback to revision 1 after revision 2 was reviewed", False, seen_path=seen)
        seen.write_text("{damaged")
        write(r2)
        expect("a damaged review record", False, seen_path=seen)
        if load(policy_file, trusted_uid=me, seen=None)[0] is not None:
            failures.append("without a test boundary, a fixture below user-owned directories was trusted")
    return failures


def main(argv: list[str]) -> int:
    if argv == ["--self-test"]:
        failures = self_test()
        for f in failures:
            print("FAIL:", f)
        print("trust_policy self-test: " + ("PASS" if not failures else f"{len(failures)} FAILED"))
        return 1 if failures else 0
    if argv[:1] == ["template"]:
        print(json.dumps(TEMPLATE, indent=2))
        return 0
    if argv == ["remember"]:
        print(remember())
        return 0
    if argv[:1] == ["verify"]:
        path = Path(argv[2]) if argv[1:2] == ["--path"] and len(argv) > 2 else None
        policy, where = load(path)
        if path is not None:
            print("note: --path inspects a file; only the system location can be the trust root")
        print(("trusted: " if policy else "no trust: ") + where)
        return 0 if policy else 1
    print(__doc__.split("\n\n")[1].strip())
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
