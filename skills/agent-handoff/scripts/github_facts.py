#!/usr/bin/env python3
"""Facts about a standing authorization reference, read from GitHub: the narrow host integration of RFC 0001, D14.

    github_facts.py --self-test

gather(reference, repo_root, owners, pin=None) returns the facts authorization.evaluate() needs, in the shape of the
runtime fixtures. Through `gh api`, read-only, it establishes:
- the default branch's revision, pinned once (or checked against `pin`, the revision an earlier verification used);
- the referenced commit and entry;
- the approval candidates on the `approved_in` PR: its merge, and each reviewer's latest decisive review;
- provenance by ancestry, never by timestamps: the PR's merge must lie on the default branch's first-parent chain
  from the pinned revision; the point just before the PR's own changes is the merge commit's first parent (a merge
  commit), or the first commit, walking back along first parents, that the host does not associate with the PR (a
  squash or rebase merge); the PR introduced the entry only if it is absent or different there;
- the entry's state at every first-parent commit after the merge: removal, any change (even if restored), and the
  state at the pinned revision. Side-branch commits that never were first-parent states are not counted.
Anything ambiguous, unsupported, malformed or beyond MAX_HISTORY first-parent commits is reported as None (unknown);
an unreachable host gives host_reachable false. `owners` only chooses which candidate to report; evaluate() decides.
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
SHA = re.compile(r"^[0-9a-f]{40}$")
MAX_HISTORY = 100                                     # first-parent commits inspected between the merge and the pin
MAX_REVIEWS = 100
FILES_PAGE = 300                                      # GitHub truncates a commit's file list at this size


class HostError(Exception):
    """The host could not be queried, or answered something this adapter does not understand."""


class NotFound(Exception):
    """The host answered that the object does not exist."""


def not_found(stderr: str) -> bool:
    """GitHub answers a missing file with 404, and a missing or malformed commit with 422 "No commit found"."""
    return "HTTP 404" in stderr or ("HTTP 422" in stderr and "No commit found" in stderr)


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


def repository_slug(root: Path, remote: str = "origin") -> str | None:
    try:
        r = subprocess.run(["git", "-C", str(root), "remote", "get-url", remote], capture_output=True, text=True,
                           timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    m = REMOTE.match(r.stdout.strip()) if r.returncode == 0 else None
    return f"{m.group(1)}/{m.group(2)}" if m else None


_records = None


def records():
    global _records
    if _records is None:
        spec = importlib.util.spec_from_file_location("operational_records_copy", HERE / "operational_records.py")
        _records = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_records)
    return _records


def same(a, b) -> bool:
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


class Host:
    """Read-only queries against one repository, with the answers validated before use."""

    def __init__(self, api, slug: str):
        self.api, self.slug = api, slug
        self.commit_cache: dict[str, dict] = {}

    def commit(self, ref: str) -> dict:
        if ref not in self.commit_cache:
            data = self.api(f"repos/{self.slug}/commits/{urllib.parse.quote(ref, safe='')}")
            if not isinstance(data, dict) or not SHA.match(str(data.get("sha", ""))) \
                    or not isinstance(data.get("parents"), list):
                raise HostError(f"malformed commit answer for {ref[:12]}")
            parents = [p.get("sha") for p in data["parents"] if isinstance(p, dict)]
            if len(parents) != len(data["parents"]) or not all(SHA.match(str(p)) for p in parents):
                raise HostError(f"malformed parents for {ref[:12]}")
            files = data.get("files")
            data = {"sha": data["sha"], "parents": parents,
                    "files": None if not isinstance(files, list) or len(files) >= FILES_PAGE
                    else [f.get("filename") for f in files if isinstance(f, dict)]}
            self.commit_cache[ref] = self.commit_cache[data["sha"]] = data
        return self.commit_cache[ref]

    def entry(self, path: str, ref: str, entry_id: str):
        """The entry with this id in the authorizations file at ref; None when the file or the entry is absent."""
        try:
            meta = self.api(f"repos/{self.slug}/contents/{urllib.parse.quote(path)}?ref={urllib.parse.quote(ref)}")
        except NotFound:
            return None
        if not isinstance(meta, dict) or meta.get("encoding") != "base64" or not isinstance(meta.get("content"), str):
            raise HostError(f"{path} at {ref[:12]} is not a file")
        try:
            data = records().strict_json(base64.b64decode(meta["content"]).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            raise HostError(f"{path} at {ref[:12]} cannot be parsed: {e}")
        if not (isinstance(data, dict) and data.get("kind") == "authorizations"
                and isinstance(data.get("authorizations"), list)):
            raise HostError(f"{path} at {ref[:12]} is not an authorizations file")
        matches = [e for e in data["authorizations"] if isinstance(e, dict) and e.get("id") == entry_id]
        if len(matches) > 1:
            raise HostError(f"{path} at {ref[:12]} holds entry {entry_id!r} twice")
        return matches[0] if matches else None

    def associated(self, sha: str, number: int) -> bool:
        pulls = self.api(f"repos/{self.slug}/commits/{sha}/pulls")
        if not isinstance(pulls, list):
            raise HostError(f"malformed pull request association for {sha[:12]}")
        return any(isinstance(p, dict) and p.get("number") == number for p in pulls)


def approvals(api, slug: str, number: str) -> tuple[dict, list[dict]]:
    """(the PR, every host-recorded approval candidate on it: its merge, and each reviewer's latest decisive review)."""
    pr = api(f"repos/{slug}/pulls/{number}")
    if not isinstance(pr, dict):
        raise HostError("malformed pull request answer")
    out = []
    if pr.get("merged") is True and isinstance(pr.get("merged_by"), dict) and SHA.match(str(pr.get("merge_commit_sha"))):
        out.append({"kind": "merge", "by": f"github:{pr['merged_by']['login']}", "revision": pr["merge_commit_sha"],
                    "at": pr.get("merged_at"), "state": "active"})
    reviews = api(f"repos/{slug}/pulls/{number}/reviews?per_page={MAX_REVIEWS}")
    if not isinstance(reviews, list) or len(reviews) >= MAX_REVIEWS:
        raise HostError("reviews missing, malformed, or too many to inspect")
    per_user: dict[str, list[dict]] = {}
    for review in reviews:
        if isinstance(review, dict) and review.get("state") in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED") \
                and isinstance(review.get("user"), dict):
            per_user.setdefault(review["user"]["login"], []).append(review)
    for login, rs in per_user.items():
        approved = [r for r in rs if r["state"] in ("APPROVED", "DISMISSED")]
        if not approved:
            continue
        last = rs[-1]
        state = {"APPROVED": "active", "DISMISSED": "dismissed", "CHANGES_REQUESTED": "superseded"}[last["state"]]
        basis = last if last["state"] != "CHANGES_REQUESTED" else approved[-1]
        revision = basis.get("commit_id") if SHA.match(str(basis.get("commit_id"))) else None
        out.append({"kind": "approval", "by": f"github:{login}", "revision": revision, "at": basis.get("submitted_at"),
                    "state": state})
    return pr, out


def provenance(host: Host, path: str, entry_id: str, entry: dict, pr: dict, head: str) -> dict:
    """The PR-level provenance facts: merged into the default branch, introduced the entry, and the entry's history
    on the first-parent chain from the merge up to the pinned head. None wherever it cannot be established."""
    out = {"merged_into_default_branch": None, "introduced_entry": None, "reinstated_after_approval": None,
           "changed_after_approval": None, "entry_on_default_branch": None}
    anchor = pr.get("merge_commit_sha") if pr.get("merged") is True else None
    if not anchor:
        out["merged_into_default_branch"] = False
        return out
    chain, sha = [], head                             # first-parent chain from the pinned head down to the anchor
    while True:
        if sha == anchor:
            break
        if len(chain) >= MAX_HISTORY:
            return out                                # beyond the supported history: unknown
        commit = host.commit(sha)
        chain.append(commit)
        if not commit["parents"]:
            out["merged_into_default_branch"] = False  # the root was reached: the merge is not on the default branch
            return out
        sha = commit["parents"][0]
    out["merged_into_default_branch"] = True
    anchor_commit = host.commit(anchor)
    at_anchor = host.entry(path, anchor, entry_id)
    # The point just before the PR's own changes, by merge strategy.
    if len(anchor_commit["parents"]) > 1:
        before = anchor_commit["parents"][0]          # a merge commit: its first parent is the base branch
    else:
        number = int(str(pr.get("number")))
        limit = pr.get("commits") if isinstance(pr.get("commits"), int) and pr["commits"] > 0 else None
        if limit is None or not host.associated(anchor, number):
            return out                                # ambiguous provenance: unknown
        before, steps = anchor, 0
        while host.associated(before, number):
            steps += 1
            parents = host.commit(before)["parents"]
            if steps > limit or not parents:
                return out                            # more commits than the PR has, or no base: unknown
            before = parents[0]
    at_before = host.entry(path, before, entry_id)
    out["introduced_entry"] = (at_anchor is not None and same(at_anchor, entry)
                               and (at_before is None or not same(at_before, at_anchor)))
    # The entry's state on each first-parent commit after the merge, oldest first.
    state, removed, changed = at_anchor, False, False
    for commit in reversed(chain):
        touches = commit["files"] is None or len(commit["parents"]) > 1 or path in commit["files"]
        if touches:
            state = host.entry(path, commit["sha"], entry_id)
        if state is None:
            removed = True
        elif not same(state, entry):
            changed = True
    out["entry_on_default_branch"] = "absent" if state is None else ("identical" if same(state, entry) else "changed")
    out["reinstated_after_approval"] = removed and state is not None
    out["changed_after_approval"] = changed
    return out


def gather(reference: dict, root: Path, owners=(), api=gh_api, remote: str = "origin", pin: str | None = None) -> dict:
    """Facts for one standing reference, in the shape of the runtime fixtures' `state`."""
    path, _, rest = str(reference.get("ref", "")).partition("@")
    commit, _, entry_id = rest.partition("#")
    slug = repository_slug(root, remote)
    if slug is None:
        return {"host_reachable": False, "why": f"remote {remote!r} is not a GitHub repository: no host adapter for it"}
    host = Host(api, slug)
    facts: dict = {"host_reachable": False}
    try:
        info = api(f"repos/{slug}")
        if not isinstance(info, dict) or not info.get("full_name") or not info.get("default_branch"):
            raise HostError("malformed repository answer")
        facts.update(host_reachable=True, repository=f"github.com/{info['full_name']}".lower())
        head = host.commit(info["default_branch"])["sha"]
        facts["default_revision"] = head
        if pin is not None:
            facts["default_branch_moved"] = head != pin
            if head != pin:
                return facts
        try:
            host.commit(commit)
            facts["commit_exists"] = True
        except NotFound:
            facts["commit_exists"] = False
            return facts
        entry = host.entry(path, commit, entry_id)
        facts["entry_at_reference"] = entry
        if entry is None:
            return facts
        m = PR_URL.match(str(entry.get("approved_in", "")))
        if not m:
            return facts
        pr_slug = f"{m.group(1)}/{m.group(2)}"
        if pr_slug.lower() != slug.lower():
            return facts                              # evaluate() reports the foreign PR from the entry itself
        pr, candidates = approvals(api, pr_slug, m.group(3))
        for c in candidates:
            at_revision = host.entry(path, c["revision"], entry_id) if c["revision"] else None
            c["entry_at_approved_revision"] = None if c["revision"] is None else \
                ("identical" if at_revision is not None and same(at_revision, entry) else "changed")
        shared = provenance(host, path, entry_id, entry, pr, head)
        owned = [c for c in candidates if c["by"] in owners]
        usable = [c for c in owned if c["state"] == "active" and c["entry_at_approved_revision"] == "identical"
                  and shared["merged_into_default_branch"] is True and shared["introduced_entry"] is True]
        chosen = (usable or owned or candidates or [{"kind": "none", "by": None, "state": "active",
                                                     "entry_at_approved_revision": None}])[0]
        facts["approval"] = {**{k: chosen.get(k) for k in ("kind", "by", "state", "entry_at_approved_revision", "at")},
                             "introduced_entry": shared["introduced_entry"],
                             "merged_into_default_branch": shared["merged_into_default_branch"]}
        for key in ("entry_on_default_branch", "reinstated_after_approval", "changed_after_approval"):
            facts[key] = shared[key]
    except NotFound as e:
        return {"host_reachable": False, "why": f"the host has no {e}: cannot be established now"}
    except (HostError, KeyError, TypeError, ValueError, AttributeError) as e:
        return {"host_reachable": False, "why": f"the host could not be read: {e}"}
    return facts


def still_current(api, slug: str, branch: str, pinned: str) -> bool | None:
    """Revalidation before a consequential operation: True if the branch is still at the pinned revision."""
    try:
        return Host(api, slug).commit(branch)["sha"] == pinned
    except (HostError, NotFound, KeyError, TypeError):
        return None


# ------------------------------------------------------------------------------------------------- self-test

class FakeGitHub:
    """A deterministic stand-in for the GitHub API: a commit graph with an authorizations file per commit, the pull
    requests the host associates with each commit, one PR with reviews, and a default branch."""

    def __init__(self, slug="example/repo", default="main"):
        self.slug, self.default = slug, default
        self.commits: dict[str, dict] = {}            # sha -> {"parents", "doc", "prs", "date"}
        self.docs: dict[str, dict | None] = {}        # extra revisions outside the graph (review commits)
        self.head = None
        self.pr: dict = {"merged": False}
        self.reviews: list[dict] = []
        self.down = False
        self.calls: list[str] = []

    def add(self, sha, parents, doc, prs=(), date="2026-11-27T00:00:00Z"):
        self.commits[sha] = {"parents": list(parents), "doc": doc, "prs": list(prs), "date": date}
        self.head = sha
        return sha

    def doc_at(self, ref):
        if ref == self.default:
            ref = self.head
        if ref in self.commits:
            return self.commits[ref]["doc"]
        return self.docs.get(ref)

    def __call__(self, path: str):
        self.calls.append(path)
        if self.down:
            raise HostError("network unreachable")
        parsed = urllib.parse.urlparse(path)
        query = urllib.parse.parse_qs(parsed.query)
        base = f"repos/{self.slug}"
        rest = parsed.path[len(base):]
        if not parsed.path.startswith(base):
            raise NotFound(path)
        if rest == "":
            return {"full_name": self.slug, "default_branch": self.default}
        if rest.startswith("/commits/") and rest.endswith("/pulls"):
            sha = rest.split("/")[2]
            return [{"number": n} for n in self.commits.get(sha, {}).get("prs", [])]
        if rest.startswith("/commits/"):
            ref = urllib.parse.unquote(rest.split("/", 2)[2])
            sha = self.head if ref == self.default else ref
            if sha in self.commits:
                c = self.commits[sha]
                parent_doc = self.commits[c["parents"][0]]["doc"] if c["parents"] else None
                files = [{"filename": "ops/authorizations.json"}] if len(c["parents"]) == 1 and c["doc"] != parent_doc \
                    else ([] if len(c["parents"]) == 1 else [{"filename": "other"}])
                return {"sha": sha, "parents": [{"sha": p} for p in c["parents"]], "files": files,
                        "commit": {"committer": {"date": c["date"]}}}
            if sha in self.docs:
                return {"sha": sha, "parents": [], "files": []}
            raise NotFound(path)
        if rest.startswith("/contents/"):
            doc = self.doc_at(query["ref"][0])
            if doc is None:
                raise NotFound(path)
            return {"encoding": "base64", "content": base64.b64encode(json.dumps(doc).encode()).decode()}
        if rest.endswith("/reviews"):
            return self.reviews
        if "/pulls/" in rest:
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
    module = sys.modules[__name__]
    try:
        root = base / "repo"
        root.mkdir()
        env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
        subprocess.run(["git", "-C", str(root), "init", "-q"], check=True, env=env)
        subprocess.run(["git", "-C", str(root), "remote", "add", "origin", "git@github.com:example/repo.git"],
                       check=True, env=env)
        sha = lambda c: c * 40                         # noqa: E731
        entry = {"id": "push-feature-branches", "level": "R2", "operations": "Push feature branches",
                 "actions": ["push-branch"], "scope": {"branches": ["feature/*"], "destinations": ["origin"]},
                 "granted_by": "github:example-owner", "approved_in": "https://github.com/example/repo/pull/1",
                 "expires": "2027-06-30T00:00:00Z"}
        changed = {**entry, "scope": {"branches": ["*"], "destinations": ["origin"]}}
        policy = {"owners": ["github:example-owner"], "repositories": ["github.com/example/repo"]}
        owners = policy["owners"]
        now = datetime.datetime(2026, 11, 28, tzinfo=datetime.timezone.utc)
        request = {"action": "push-branch", "level": "R2", "repository": "github.com/example/repo",
                   "branch": "feature/x", "destination": "origin"}
        merged = {"number": 1, "merged": True, "merged_by": {"login": "example-owner"}, "commits": 1,
                  "merged_at": "2026-11-27T18:00:00Z", "base": {"ref": "main"}}

        def reference(at):
            return {"level": "R2", "scope": "Push feature branches", "source": "standing", "by": "github:example-owner",
                    "ref": f"ops/authorizations.json@{at}#push-feature-branches", "granted": "2026-11-27T18:00:00Z",
                    "expires": "2027-06-30T00:00:00Z"}

        def outcome(gh, at, pin=None, req=None):
            facts = gather(reference(at), root, owners, api=gh, pin=pin)
            return model.evaluate(reference(at), req or request, facts, policy, now)

        def linear(after=(), merge_doc=None, before_doc=None, pr=None, assoc=(1,)):
            """base <- merge (the PR's squash commit) <- after... ; returns the fake host and the merge sha."""
            gh = FakeGitHub()
            gh.add(sha("0"), [], before_doc if before_doc is not None else doc())
            gh.add(sha("1"), [sha("0")], merge_doc or doc(entry), prs=assoc)
            parent = sha("1")
            for i, (d, date) in enumerate(after):
                parent = gh.add(sha("abcdef"[i]), [parent], d, prs=(9,), date=date)
            gh.pr = {**merged, "merge_commit_sha": sha("1"), **(pr or {})}
            return gh

        cases = [
            ("squash merge by the owner, unchanged since", linear(after=[(doc(entry), "2026-11-28T00:00:00Z")]),
             "verified"),
            ("removed, then reinstated, with misleading (old) commit dates",
             linear(after=[(doc(), "2020-01-01T00:00:00Z"), (doc(entry), "2020-01-02T00:00:00Z")]), "inapplicable"),
            ("changed after approval, then restored",
             linear(after=[(doc(changed), "2026-11-28T00:00:00Z"), (doc(entry), "2026-11-28T01:00:00Z")]),
             "inapplicable"),
            ("revoked at the pinned revision", linear(after=[(doc(), "2026-11-28T00:00:00Z")]), "inapplicable"),
            ("an unrelated PR merged over an entry already on main",
             linear(before_doc=doc(entry)), "inapplicable"),
            ("the PR was never merged", linear(pr={"merged": False}), "inapplicable"),
            ("the merge commit is not associated with the PR (ambiguous)", linear(assoc=()), "unknown"),
            ("merged by a non-owner, no owner review", linear(pr={"merged_by": {"login": "someone"}}), "inapplicable"),
        ]
        for label, gh, want in cases:
            got = outcome(gh, sha("1"))
            if got[0] != want:
                failures.append(f"{label}: expected {want}, got {got}")
        # A side branch that removed and re-added the entry, merged with no net change: not a default-branch state.
        gh = FakeGitHub()
        gh.add(sha("0"), [], doc())
        gh.add(sha("1"), [sha("0")], doc(entry), prs=(1,))
        gh.add(sha("2"), [sha("1")], doc(), prs=(3,))            # side branch: removal
        gh.add(sha("3"), [sha("2")], doc(entry), prs=(3,))       # side branch: re-added
        gh.add(sha("4"), [sha("1")], doc(entry), prs=(4,))       # main moves on
        gh.add(sha("5"), [sha("4"), sha("3")], doc(entry), prs=(3,))   # merge commit of the side branch
        gh.pr = {**merged, "merge_commit_sha": sha("1")}
        if outcome(gh, sha("1"))[0] != "verified":
            failures.append(f"side-branch states were counted as default-branch history: {outcome(gh, sha('1'))}")
        # A rebase merge of a two-commit PR whose first commit added the entry.
        gh = FakeGitHub()
        gh.add(sha("0"), [], doc())
        gh.add(sha("1"), [sha("0")], doc(entry), prs=(1,))
        gh.add(sha("2"), [sha("1")], doc(entry), prs=(1,))
        gh.pr = {**merged, "merge_commit_sha": sha("2"), "commits": 2}
        if outcome(gh, sha("2"))[0] != "verified":
            failures.append(f"a rebase merge was not recognised: {outcome(gh, sha('2'))}")
        gh.pr["commits"] = 1                                     # the host says one commit: inconsistent
        if outcome(gh, sha("2"))[0] != "unknown":
            failures.append("inconsistent rebase provenance was not unknown")
        # A merge commit: the feature branch added the entry; the first parent is the base branch.
        gh = FakeGitHub()
        gh.add(sha("0"), [], doc())
        gh.add(sha("7"), [sha("0")], doc(entry), prs=(1,))
        gh.add(sha("1"), [sha("0"), sha("7")], doc(entry), prs=(1,))
        gh.pr = {**merged, "merge_commit_sha": sha("1"), "commits": 1}
        if outcome(gh, sha("1"))[0] != "verified":
            failures.append(f"a merge-commit merge was not recognised: {outcome(gh, sha('1'))}")
        # The PR merged into another branch: its merge is not on the default branch's first-parent chain.
        gh = linear()
        gh.add(sha("8"), [sha("0")], doc(entry), prs=(5,))       # the default branch head, without the merge
        if outcome(gh, sha("1"))[0] != "inapplicable":
            failures.append("a merge outside the default branch was accepted")
        # Bounded history: beyond MAX_HISTORY first-parent commits is unknown, never assumed valid.
        saved = module.MAX_HISTORY
        module.MAX_HISTORY = 2
        try:
            gh = linear(after=[(doc(entry), "2026-11-28T00:00:00Z")] * 4)
            if outcome(gh, sha("1"))[0] != "unknown":
                failures.append("history beyond the inspection limit was not unknown")
        finally:
            module.MAX_HISTORY = saved
        # Pinning: a moved default branch is unknown; the pinned revision verifies; revalidation sees the move.
        gh = linear(after=[(doc(entry), "2026-11-28T00:00:00Z")])
        if outcome(gh, sha("1"), pin=sha("1"))[0] != "unknown" or outcome(gh, sha("1"), pin=sha("a"))[0] != "verified":
            failures.append("pinning the default branch revision does not work")
        if still_current(gh, "example/repo", "main", sha("a")) is not True \
                or still_current(gh, "example/repo", "main", sha("1")) is not False:
            failures.append("revalidation of the pinned revision does not work")
        # Reviews: the owner's active approval of identical content counts; dismissed, superseded or stale do not.
        review = {"user": {"login": "example-owner"}, "state": "APPROVED", "commit_id": sha("e"),
                  "submitted_at": "2026-11-27T17:00:00Z"}
        for label, reviews, docs_at, want in [
                ("owner's approval, merged by someone else", [review], doc(entry), "verified"),
                ("owner's approval dismissed", [{**review, "state": "DISMISSED"}], doc(entry), "inapplicable"),
                ("owner's approval superseded", [review, {**review, "state": "CHANGES_REQUESTED"}], doc(entry),
                 "inapplicable"),
                ("owner approved other content", [review], doc(changed), "inapplicable")]:
            gh = linear(pr={"merged_by": {"login": "someone"}})
            gh.reviews, gh.docs = reviews, {sha("e"): docs_at}
            got = outcome(gh, sha("1"))
            if got[0] != want:
                failures.append(f"{label}: expected {want}, got {got}")
        # Malformed or missing host answers are never positive evidence.
        for label, breakage in [("host down", lambda g: setattr(g, "down", True)),
                                ("malformed PR", lambda g: setattr(g, "pr", ["not", "an", "object"])),
                                ("malformed reviews", lambda g: setattr(g, "reviews", {"x": 1})),
                                ("too many reviews", lambda g: setattr(g, "reviews", [{}] * MAX_REVIEWS))]:
            gh = linear()
            breakage(gh)
            if outcome(gh, sha("1"))[0] == "verified":
                failures.append(f"{label}: still verified")
        gh = linear()
        outcome(gh, sha("1"))
        if any(not c.startswith("repos/example/repo") for c in gh.calls):
            failures.append(f"the adapter queried outside the repository: {gh.calls}")
        if outcome(linear(), "f" * 40)[0] != "invalid":
            failures.append("a fabricated commit was not invalid")
        subprocess.run(["git", "-C", str(root), "remote", "set-url", "origin", "https://gitlab.com/example/repo.git"],
                       check=True, env=env)
        facts = gather(reference(sha("1")), root, owners, api=linear())
        if facts["host_reachable"] or "not a GitHub repository" not in facts.get("why", ""):
            failures.append(f"a non-GitHub remote was not reported as having no adapter: {facts}")
        for stderr, want in [("gh: No commit found for SHA: 1111 (HTTP 422)", True), ("gh: Not Found (HTTP 404)", True),
                             ("gh: Validation Failed (HTTP 422)", False), ("gh: Bad credentials (HTTP 401)", False),
                             ("error connecting to api.github.com", False)]:
            if not_found(stderr) != want:
                failures.append(f"host answer {stderr!r} classified as not-found={not want}")
        for url, want in [("https://github.com/a/b.git", "a/b"), ("git@github.com:a/b.git", "a/b"),
                          ("ssh://git@github.com/a/b", "a/b"), ("https://github.com/a/b/", "a/b")]:
            m = REMOTE.match(url)
            if not m or f"{m.group(1)}/{m.group(2)}" != want:
                failures.append(f"remote {url} not parsed as {want}")
    except Exception as e:  # noqa: BLE001 - an unexpected state is a failure, reported rather than raised
        failures.append(f"unexpected {type(e).__name__}: {e}")
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
