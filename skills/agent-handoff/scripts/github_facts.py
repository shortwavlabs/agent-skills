#!/usr/bin/env python3
"""Facts about a standing authorization reference, read from GitHub: the narrow host integration of RFC 0001, D14.

    github_facts.py --self-test

gather(reference, repo_root, owners) returns the facts authorization.evaluate() needs, in the same shape as the
fixtures. It reads, through `gh api`, only: the repository and its default branch; the referenced commit; the
authorizations file at the referenced commit, at the approved revision and on the default branch; the pull request
named in `approved_in` and its reviews; and the commits that touched the file on the default branch since the
approval. It writes nothing. Any failure to reach or read the host yields host_reachable false (unknown), never an
assumption. `owners` only chooses which recorded approval to report; evaluate() still decides.
Standard library and the GitHub CLI (`gh`) only.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PR_URL = re.compile(r"^https://github\.com/([^/\s]+)/([^/\s]+)/pull/([0-9]+)$")
REMOTE = re.compile(r"^(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([^/\s]+)/([^/\s]+?)(?:\.git)?/?$")
MAX_COMMITS = 100


class HostError(Exception):
    """The host could not be queried."""


class NotFound(Exception):
    """The host answered that the object does not exist."""


def gh_api(path: str):
    try:
        r = subprocess.run(["gh", "api", "-H", "Accept: application/vnd.github+json", path], capture_output=True,
                           text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        raise HostError(f"gh is not available: {e}")
    if r.returncode != 0:
        if not_found(r.stderr):
            raise NotFound(path)
        raise HostError((r.stderr.strip().splitlines() or ["gh api failed"])[-1][:200])
    try:
        return json.loads(r.stdout)
    except ValueError as e:
        raise HostError(f"unreadable answer for {path}: {e}")


def not_found(stderr: str) -> bool:
    """GitHub answers a missing file with 404, and a missing or malformed commit with 422 "No commit found"."""
    return "HTTP 404" in stderr or ("HTTP 422" in stderr and "No commit found" in stderr)


def repository_slug(root: Path, remote: str = "origin") -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(root), "remote", "get-url", remote], capture_output=True, text=True,
                           timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    m = REMOTE.match(r.stdout.strip()) if r.returncode == 0 else None
    return f"{m.group(1)}/{m.group(2)}" if m else None


def entry_at(api, slug: str, path: str, ref: str, entry_id: str):
    """The entry with this id in the authorizations file at ref; None when the file or the entry is absent."""
    try:
        meta = api(f"repos/{slug}/contents/{urllib.parse.quote(path)}?ref={urllib.parse.quote(ref)}")
    except NotFound:
        return None
    if not isinstance(meta, dict) or meta.get("encoding") != "base64":
        raise HostError(f"{path} at {ref[:12]} is not a file")
    try:
        data = records().strict_json(base64.b64decode(meta["content"]).decode("utf-8"))
    except (ValueError, KeyError) as e:
        raise HostError(f"{path} at {ref[:12]} cannot be parsed: {e}")
    if isinstance(data, dict) and data.get("kind") == "authorizations" and isinstance(data.get("authorizations"), list):
        matches = [e for e in data["authorizations"] if isinstance(e, dict) and e.get("id") == entry_id]
        if len(matches) > 1:
            raise HostError(f"{path} at {ref[:12]} holds entry {entry_id!r} twice")
        return matches[0] if matches else None
    raise HostError(f"{path} at {ref[:12]} is not an authorizations file")


def same(a, b) -> bool:
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def approvals(api, slug: str, number: str) -> tuple[list[dict], str | None]:
    """(every host-recorded approval candidate on the PR: its merge and each reviewer's latest decisive review,
    the PR's base branch name)."""
    pr = api(f"repos/{slug}/pulls/{number}")
    out = []
    if pr.get("merged") and pr.get("merged_by") and pr.get("merge_commit_sha"):
        out.append({"kind": "merge", "by": f"github:{pr['merged_by']['login']}", "revision": pr["merge_commit_sha"],
                    "at": pr.get("merged_at"), "state": "active"})
    reviews = api(f"repos/{slug}/pulls/{number}/reviews?per_page=100")
    if len(reviews) >= 100:
        raise HostError("more than 100 reviews: not inspected")
    per_user: dict[str, list[dict]] = {}
    for review in reviews:
        if review.get("state") in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED") and review.get("user"):
            per_user.setdefault(review["user"]["login"], []).append(review)
    for login, rs in per_user.items():
        approved = [r for r in rs if r["state"] in ("APPROVED", "DISMISSED")]
        if not approved:
            continue
        last = rs[-1]
        state = {"APPROVED": "active", "DISMISSED": "dismissed", "CHANGES_REQUESTED": "superseded"}[last["state"]]
        basis = last if last["state"] != "CHANGES_REQUESTED" else approved[-1]
        out.append({"kind": "approval", "by": f"github:{login}", "revision": basis.get("commit_id"),
                    "at": basis.get("submitted_at"), "state": state})
    return out, (pr.get("base") or {}).get("ref")


def introduced(api, slug: str, path: str, entry_id: str, candidate: dict, at_revision, base_ref: str | None):
    """True when the approved PR itself introduced or changed the entry. The point of comparison is what the PR's own
    changes sit on: for a merge, the merge commit's first parent (the base branch just before the merge); for a review,
    the merge base of the reviewed commit and the base branch. The PR's recorded base commit is not used: it can
    predate an entry pushed to the base branch later, which an unrelated merge would then appear to approve."""
    if candidate["revision"] is None or at_revision is None:
        return None if candidate["revision"] is None else False
    if candidate["kind"] == "merge":
        parents = api(f"repos/{slug}/commits/{candidate['revision']}").get("parents") or []
        if not parents:
            return None
        before = parents[0]["sha"]
    else:
        if not base_ref:
            return None
        base = api(f"repos/{slug}/compare/{urllib.parse.quote(base_ref)}...{candidate['revision']}")
        before = (base.get("merge_base_commit") or {}).get("sha")
        if not before:
            return None
    previous = entry_at(api, slug, path, before, entry_id)
    return previous is None or not same(previous, at_revision)


def reinstated(api, slug: str, branch: str, path: str, entry_id: str, since: str | None):
    """True if the entry was absent from the default branch at any commit touching the file since the approval."""
    if not since:
        return None
    query = urllib.parse.urlencode({"sha": branch, "path": path, "since": since, "per_page": MAX_COMMITS})
    commits = api(f"repos/{slug}/commits?{query}")
    if len(commits) >= MAX_COMMITS:
        return None                                   # ponytail: too many to inspect; unknown rather than paginate
    return any(entry_at(api, slug, path, c["sha"], entry_id) is None for c in commits)


def gather(reference: dict, root: Path, owners=(), api=gh_api, remote: str = "origin") -> dict:
    """Facts for one standing reference, in the shape of the runtime fixtures' `state`."""
    path, _, rest = reference.get("ref", "").partition("@")
    commit, _, entry_id = rest.partition("#")
    slug = repository_slug(root, remote)
    if slug is None:
        return {"host_reachable": False, "why": f"remote {remote!r} is not a GitHub repository: no host adapter for it"}
    facts: dict = {"host_reachable": False}
    try:
        info = api(f"repos/{slug}")
        facts.update(host_reachable=True, repository=f"github.com/{info['full_name']}".lower())
        try:
            api(f"repos/{slug}/commits/{commit}")
            facts["commit_exists"] = True
        except NotFound:
            facts["commit_exists"] = False
            return facts
        entry = entry_at(api, slug, path, commit, entry_id)
        facts["entry_at_reference"] = entry
        if entry is None:
            return facts
        m = PR_URL.match(str(entry.get("approved_in", "")))
        if not m:
            return facts
        candidates, base_ref = approvals(api, f"{m.group(1)}/{m.group(2)}", m.group(3))
        for c in candidates:
            at_revision = entry_at(api, slug, path, c["revision"], entry_id) if c["revision"] else None
            c["entry_at_approved_revision"] = None if at_revision is None and c["revision"] is None else \
                ("identical" if at_revision is not None and same(at_revision, entry) else "changed")
            c["introduced_entry"] = introduced(api, slug, path, entry_id, c, at_revision, base_ref)
        owned = [c for c in candidates if c["by"] in owners]
        usable = [c for c in owned if c["state"] == "active" and c["entry_at_approved_revision"] == "identical"]
        chosen = (usable or owned or candidates or [{"kind": "none", "by": None, "state": "active",
                                                     "entry_at_approved_revision": None}])[0]
        facts["approval"] = {k: chosen.get(k) for k in ("kind", "by", "state", "entry_at_approved_revision",
                                                        "introduced_entry", "at")}
        current = entry_at(api, slug, path, info["default_branch"], entry_id)
        facts["entry_on_default_branch"] = "absent" if current is None else (
            "identical" if same(current, entry) else "changed")
        facts["reinstated_after_approval"] = reinstated(api, slug, info["default_branch"], path, entry_id,
                                                        chosen.get("at"))
    except NotFound as e:
        return {"host_reachable": False, "why": f"the host has no {e}: cannot be established now"}
    except (HostError, KeyError, TypeError) as e:
        return {"host_reachable": False, "why": f"the host could not be read: {e}"}
    return facts


_records = None


def records():
    global _records
    if _records is None:
        spec = importlib.util.spec_from_file_location("operational_records_copy", HERE / "operational_records.py")
        _records = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_records)
    return _records


# ------------------------------------------------------------------------------------------------- self-test

class FakeGitHub:
    """A deterministic stand-in for the GitHub API: files per commit, one PR with reviews, a default branch."""

    def __init__(self, slug="example/repo", default="main"):
        self.slug, self.default = slug, default
        self.files: dict[str, dict] = {}              # revision -> authorizations document (or None)
        self.branch_history: list[str] = []           # commits touching the file on the default branch, newest first
        self.pr = {"merged": False}
        self.parents: dict[str, str] = {}             # commit -> first parent
        self.merge_base: str | None = None            # the compare endpoint's merge base
        self.reviews: list[dict] = []
        self.down = False
        self.calls: list[str] = []

    def __call__(self, path: str):
        self.calls.append(path)
        if self.down:
            raise HostError("network unreachable")
        parsed = urllib.parse.urlparse(path)
        parts, query = parsed.path.split("/"), urllib.parse.parse_qs(parsed.query)
        base = f"repos/{self.slug}"
        if parsed.path == base:
            return {"full_name": self.slug, "default_branch": self.default}
        if parsed.path.startswith(base + "/commits/"):
            if parts[-1] not in self.files:
                raise NotFound(path)
            parent = self.parents.get(parts[-1])
            return {"sha": parts[-1], "parents": [{"sha": parent}] if parent else []}
        if parsed.path.startswith(base + "/compare/"):
            return {"merge_base_commit": {"sha": self.merge_base}} if self.merge_base else {}
        if parsed.path.startswith(base + "/contents/"):
            ref = query["ref"][0]
            doc = self.files.get(self.branch_history[0] if ref == self.default and self.branch_history else ref)
            if doc is None:
                raise NotFound(path)
            return {"encoding": "base64", "content": base64.b64encode(json.dumps(doc).encode()).decode()}
        if parsed.path == base + "/commits":
            return [{"sha": s} for s in self.branch_history]
        if parsed.path.endswith("/reviews"):
            return self.reviews
        if "/pulls/" in parsed.path:
            return self.pr
        raise NotFound(path)


def doc(*entries) -> dict:
    return {"kind": "authorizations", "version": 1, "authorizations": list(entries)}


def self_test() -> list[str]:
    import datetime
    import os
    import shutil
    import tempfile
    failures: list[str] = []
    spec = importlib.util.spec_from_file_location("authorization_model", HERE / "authorization.py")
    model = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(model)
    base = Path(tempfile.mkdtemp(prefix="github-facts-")).resolve()
    try:
        root = base / "repo"
        root.mkdir()
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        subprocess.run(["git", "-C", str(root), "init", "-q"], check=True, env=env)
        subprocess.run(["git", "-C", str(root), "remote", "add", "origin", "git@github.com:example/repo.git"],
                       check=True, env=env)
        ref_commit, merge_commit, review_commit, head, base_commit = "a" * 40, "b" * 40, "c" * 40, "d" * 40, "0" * 40
        entry = {"id": "push-feature-branches", "level": "R2",
                 "operations": "Push feature branches of this repository to origin and open draft PRs",
                 "actions": ["push-branch", "open-draft-pr"], "granted_by": "github:example-owner",
                 "approved_in": "https://github.com/example/repo/pull/1", "expires": "2027-06-30T00:00:00Z"}
        reference = {"level": "R2", "scope": entry["operations"], "source": "standing", "by": "github:example-owner",
                     "ref": f"ops/authorizations.json@{ref_commit}#push-feature-branches",
                     "granted": "2026-11-27T18:00:00Z", "expires": "2027-06-30T00:00:00Z"}
        policy = {"owners": ["github:example-owner"], "repositories": ["github.com/example/repo"]}
        now = datetime.datetime(2026, 11, 27, 20, tzinfo=datetime.timezone.utc)
        owners = policy["owners"]

        def host(**kw) -> FakeGitHub:
            gh = FakeGitHub()
            gh.files = {ref_commit: doc(entry), merge_commit: doc(entry), review_commit: doc(entry), head: doc(entry),
                        base_commit: doc()}
            gh.branch_history = [head]
            gh.pr = {"merged": True, "merged_by": {"login": "example-owner"}, "merge_commit_sha": merge_commit,
                     "merged_at": "2026-11-27T18:00:00Z"}
            for k, v in kw.items():
                setattr(gh, k, v)
            gh.pr.setdefault("base", {"ref": "main", "sha": base_commit})
            gh.files.setdefault(base_commit, doc())
            gh.parents.setdefault(merge_commit, base_commit)
            if gh.merge_base is None:
                gh.merge_base = base_commit
            return gh

        def outcome(gh, action="push-branch") -> tuple[str, str]:
            facts = gather(reference, root, owners, api=gh)
            return model.evaluate(reference, {"action": action}, facts, policy, now)

        changed = {**entry, "operations": entry["operations"] + " and publish releases",
                   "actions": entry["actions"] + ["publish-release"]}
        cases = [
            ("owner merged the entry unchanged", host(), "verified"),
            ("host down", host(down=True), "unknown"),
            ("fabricated commit", host(files={merge_commit: doc(entry), head: doc(entry)}), "invalid"),
            ("entry missing at the commit", host(files={ref_commit: doc(), merge_commit: doc(entry), head: doc(entry)}),
             "invalid"),
            ("merged by a non-owner, no owner review", host(pr={"merged": True, "merged_by": {"login": "someone"},
                                                                "merge_commit_sha": merge_commit,
                                                                "merged_at": "2026-11-27T18:00:00Z"}), "inapplicable"),
            ("not merged, owner's active approval of identical content",
             host(pr={"merged": False}, reviews=[{"user": {"login": "example-owner"}, "state": "APPROVED",
                                                  "commit_id": review_commit, "submitted_at": "2026-11-27T17:00:00Z"}]),
             "verified"),
            ("owner's approval dismissed", host(pr={"merged": False}, reviews=[
                {"user": {"login": "example-owner"}, "state": "DISMISSED", "commit_id": review_commit,
                 "submitted_at": "2026-11-27T17:00:00Z"}]), "inapplicable"),
            ("owner's approval superseded by a change request", host(pr={"merged": False}, reviews=[
                {"user": {"login": "example-owner"}, "state": "APPROVED", "commit_id": review_commit,
                 "submitted_at": "2026-11-27T17:00:00Z"},
                {"user": {"login": "example-owner"}, "state": "CHANGES_REQUESTED", "commit_id": review_commit,
                 "submitted_at": "2026-11-27T17:30:00Z"}]), "inapplicable"),
            ("owner approved an earlier revision", host(pr={"merged": False}, reviews=[
                {"user": {"login": "example-owner"}, "state": "APPROVED", "commit_id": "e" * 40,
                 "submitted_at": "2026-11-27T17:00:00Z"}], files={ref_commit: doc(entry), "e" * 40: doc(changed),
                                                                head: doc(entry)}), "inapplicable"),
            ("revoked on the default branch", host(files={ref_commit: doc(entry), merge_commit: doc(entry),
                                                          head: doc()}), "inapplicable"),
            ("changed on the default branch", host(files={ref_commit: doc(entry), merge_commit: doc(entry),
                                                          head: doc(changed)}), "inapplicable"),
            ("revoked, then reinstated without fresh approval",
             host(files={ref_commit: doc(entry), merge_commit: doc(entry), "f" * 40: doc(), head: doc(entry)},
                  branch_history=[head, "f" * 40]), "inapplicable"),
            ("approval names another repository's PR", host(), "inapplicable"),
            ("owner merged a PR that never touched the entry",
             host(files={ref_commit: doc(entry), merge_commit: doc(entry), head: doc(entry), base_commit: doc(entry)}),
             "inapplicable"),
            ("entry pushed to main after the PR was opened, then the owner merged the unrelated PR",
             host(files={ref_commit: doc(entry), merge_commit: doc(entry), head: doc(entry), base_commit: doc(),
                         "9" * 40: doc(entry)}, parents={merge_commit: "9" * 40}), "inapplicable"),
            ("owner's review of a PR whose merge base already had the entry",
             host(pr={"merged": False, "base": {"ref": "main"}}, merge_base="9" * 40,
                  files={ref_commit: doc(entry), review_commit: doc(entry), head: doc(entry), "9" * 40: doc(entry)},
                  reviews=[{"user": {"login": "example-owner"}, "state": "APPROVED", "commit_id": review_commit,
                            "submitted_at": "2026-11-27T17:00:00Z"}]), "inapplicable"),
            ("merge commit without parents recorded", host(parents={merge_commit: ""}), "unknown"),
            ("the PR changed the entry the owner merged",
             host(files={ref_commit: doc(entry), merge_commit: doc(entry), head: doc(entry),
                         base_commit: doc({**entry, "expires": "2026-12-31T00:00:00Z"})}), "verified"),
        ]
        for label, gh, want in cases:
            if label == "approval names another repository's PR":
                other = {**entry, "approved_in": "https://github.com/other/repo/pull/1"}
                gh.files = {k: doc(other) for k in gh.files}
                got = model.evaluate(reference, {"action": "push-branch"}, gather(reference, root, owners, api=gh),
                                     policy, now)
            else:
                got = outcome(gh)
            if got[0] != want:
                failures.append(f"{label}: expected {want}, got {got}")
        if outcome(host(), action="publish-release")[0] != "inapplicable":
            failures.append("an action outside the entry was covered")
        if model.evaluate(reference, {"action": "push-branch"}, gather(reference, root, owners, api=host()),
                          None, now)[0] != "unknown":
            failures.append("without a canonical policy, a reference was not unknown")
        gh = host()
        gather(reference, root, owners, api=gh)
        if any(not c.startswith("repos/example/repo") for c in gh.calls):
            failures.append(f"the adapter queried outside the repository: {gh.calls}")
        subprocess.run(["git", "-C", str(root), "remote", "set-url", "origin", "https://gitlab.com/example/repo.git"],
                       check=True, env=env)
        facts = gather(reference, root, owners, api=host())
        if facts["host_reachable"] or "not a GitHub repository" not in facts.get("why", ""):
            failures.append(f"a non-GitHub remote was not reported as having no adapter: {facts}")
        for stderr, want in [("gh: No commit found for SHA: 1111 (HTTP 422)", True), ("gh: Not Found (HTTP 404)", True),
                             ("gh: Validation Failed (HTTP 422)", False), ("gh: Bad credentials (HTTP 401)", False),
                             ("error connecting to api.github.com", False)]:
            if not_found(stderr) != want:
                failures.append(f"host answer {stderr!r} classified as not-found={not not want}")
        for url, want in [("https://github.com/a/b.git", "a/b"), ("git@github.com:a/b.git", "a/b"),
                          ("ssh://git@github.com/a/b", "a/b"), ("https://github.com/a/b/", "a/b")]:
            m = REMOTE.match(url)
            if not m or f"{m.group(1)}/{m.group(2)}" != want:
                failures.append(f"remote {url} not parsed as {want}")
    finally:
        shutil.rmtree(base, ignore_errors=True)
    return failures


def main(argv: list[str]) -> int:
    if argv == ["--self-test"]:
        failures = self_test()
        for f in failures:
            print("FAIL:", f)
        print("github_facts self-test: " + ("PASS" if not failures else f"{len(failures)} FAILED"))
        return 1 if failures else 0
    print(__doc__.split("\n\n")[1].strip())
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
