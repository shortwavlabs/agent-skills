# Runtime authorization verification

`handoff.py verify-auth` evaluates each authorization reference in a record for one structured operation, at the
moment of use. A record never grants authority; a reference that verifies is evidence that a standing authorization
covers this exact operation now.

## Contents
- [The model](#the-model)
- [Describing the operation](#describing-the-operation)
- [Structured scope](#structured-scope)
- [Conditions, in order](#conditions-in-order)
- [The GitHub integration](#the-github-integration)
- [The trusted policy](#the-trusted-policy)
- [Limitations](#limitations)

## The model

`scripts/authorization.py` holds the portable model: `evaluate(reference, operation, facts, policy, now)` returns a
status and a reason. It is a pure function: it contacts nothing and trusts nothing it is not given. `facts` describe
the host's records (the shape of `references/authorization-runtime.json`, a generated copy of the RFC's regression
fixtures); `scripts/github_facts.py` gathers them from GitHub. Another host needs only another facts adapter.

| Status | Grants authority |
|---|---|
| verified | Yes, for the evaluated operation only |
| inapplicable | No |
| invalid | No |
| unknown | No: ask the owner once |

## Describing the operation

The operation is structured data, never prose: free-text descriptions are not consulted, so an agent's wording cannot
widen a grant.

| Field | Meaning | Required |
|---|---|---|
| `action` | A lowercase slug (`push-branch`, `run-ci`, `delete-files`) | Always |
| `level` | R0, R1 or R2. A missing level is never permission; R3 is never covered | Always |
| `repository` | `host/owner/name` the operation acts on (`verify-auth` defaults it to this checkout's identity) | Always |
| `branch`, `destination`, `target`, `purpose` | Strings | When stated, or when the grant limits them |
| `paths` | Canonical relative paths (no `..`, no absolute paths) | Likewise |
| `cost_usd` | The operation's spending, a number | Likewise |
| `aspect` | `execute` (the default) or `spend` | For cost-only grants |

**Completeness.** Whatever an entry limits, each class of consequential action must state its required parameters,
or the result is unknown:

| Class (action verb) | Must state |
|---|---|
| Publication (`publish-`, `release-`, `upload-`, `deploy-`) | `destination` and `target` (the artifact) |
| Branch (`push-`, `merge-`, `rebase-`, `delete-branch`, `open-`, `mark-pr`, `close-pr`) | `repository` and `branch` (or `target`, a PR) |
| Files (`delete-`, `edit-`, `write-`, `move-`, `clean-`, `remove-`) | `repository` and `paths` |
| Execution (`run-`, `trigger-`, `start-`, `stop-`) | `repository` and `target` or `purpose` |
| Any other action | `repository` and `target` |
| Any operation that spends (`aspect` spend, or a `cost_usd`) | also `cost_usd` and `purpose` or `target` (its budget scope) |

The table is deliberately small: a future operation registry or `resource-budgeting` can extend it; an entry can never
relax it.

```bash
python3 $H verify-auth --action run-ci --level R2 --purpose qualification --cost-usd 1.50
python3 $H verify-auth --action push-branch --level R2 --branch feature/parser --destination origin --pin <sha>
```

## Structured scope

A standing entry lists the `actions` it covers and a `scope` saying where and how much:

```json
{
  "id": "ci-qualification",
  "level": "R2",
  "operations": "Qualification runs of the app's CI, up to USD 2 each",
  "actions": ["run-ci"],
  "scope": { "purposes": ["qualification"], "max_usd": 2 },
  "granted_by": "github:<owner login>",
  "approved_in": "https://github.com/<owner>/<repo>/pull/<n>",
  "expires": "2027-06-30T00:00:00Z"
}
```

| Scope key | Limits | Matching |
|---|---|---|
| `repositories` | `repository` | Exact, case-insensitive; no wildcard. Absent: the repository that holds the entry |
| `branches`, `paths` | `branch`, `paths` | Glob patterns (`*` crosses `/`); `"*"` alone allows any |
| `destinations`, `targets`, `purposes` | `destination`, `target`, `purpose` | Exact; `"*"` allows any |
| `max_usd` | `cost_usd` | The operation's cost must not exceed it |

- **Both directions.** Every dimension the operation states must be limited by the entry (an unlimited dimension is
  unknown, not permission), and every dimension the entry limits must be stated by the operation.
- **References only narrow.** A reference may carry `limits` (the same keys); the operation must satisfy those too.
  A reference claiming a higher limit than its entry changes nothing.
- **Cost-only grants** (`"cost_only": true`) cover spending alone: they verify only an operation whose `aspect` is
  `spend`. Running the workflow itself needs its own authorization.
- **No scope, no authority.** An entry without `actions` or without `scope` stays structurally valid (records from
  before Phase 1c still pass the checker) but evaluates to unknown.
- Approving a tool is never the action of using it: an entry for `merge-pr` does not cover `delete-files`.

## Conditions, in order

The first condition that fails decides.

1. The reference is well formed (shared format; R3 is never valid). Otherwise **invalid**.
2. An `owner-session` reference (a quotation) cannot be verified by another agent: **unknown**.
3. The operation names an action and a valid risk level; R3 is **inapplicable** (reconfirm with the owner).
4. A trusted policy exists, and the reference names the designated authorizations file (`ops/authorizations.json`,
   or the file the policy names). Otherwise unknown, or **invalid** for another file.
5. The host was reached, and the default branch has not moved since a pinned revision (`--pin`). Otherwise unknown.
6. The repository is trusted by name and, where the policy pins one, by stable repository ID (a recreated or renamed
   repository is not). The referenced commit exists and holds the entry, which is well formed, matches the reference,
   was granted by an owner and names an `approved_in` PR of this repository.
7. The host records an approval or merge of that PR by an owner's account, identified by its stable account ID (the
   policy must record one for every owner; a login alone never counts), still active (not dismissed, not superseded
   by a later change request), of content identical to the referenced entry.
8. The PR's merge lies on the default branch's first-parent chain, and **the PR itself introduced or changed the
   entry**: the entry is absent or different just before the PR's own changes. Merging an unrelated PR approves
   nothing already on the branch.
9. Since the merge, the entry was never removed and never changed on the default branch, even if restored later; it
   is identical at the pinned revision. Removal or change needs fresh owner approval.
10. Neither the entry nor the reference has expired.
11. The action is listed; the level does not exceed the entry's; a cost-only entry is used only to spend; the
    operation states every parameter its class requires; it is inside the entry's scope and the reference's limits.

Only then: **verified**. Content is compared, not commit IDs, so squash merges are handled.

## The GitHub integration

`github_facts.gather()` reads, through `gh api` and nothing else, and writes nothing:
- **The pinned revision.** The default branch's head is resolved once and used for every later read. `--pin <sha>`
  passes the revision an earlier verification used: if the branch has moved, the result is unknown. Run it again,
  chained with a consequential operation, to revalidate (`still_current()`).
- **History by ancestry.** The adapter walks the first-parent chain from the pinned revision back to the PR's merge,
  reading the file at each merge commit and at each commit whose changed-file list includes it (or is truncated).
  Commit dates are never used, so a misleadingly dated revocation is still seen. States that existed only on a side
  branch are not counted. More than 100 first-parent commits is unknown, never assumed unchanged.
- **The point before the PR's changes.** For a merge commit, its first parent. For a squash or rebase merge, the
  first commit, walking back along first parents, that the host does not associate with the PR (at most as many
  steps as the PR has commits). A merge the host does not associate with the PR, or an inconsistent commit count, is
  unknown.
- **Approval candidates.** The PR's merge and each reviewer's latest decisive review: an approval later dismissed is
  `dismissed`, one followed by a change request is `superseded`. Only a candidate that satisfies the whole contract is
  chosen; otherwise the closest one is reported so the reason is precise.
- **Missing commits.** GitHub answers a missing commit with HTTP 422, read as "does not exist" (invalid).
- **Failures.** Missing, malformed or unexpected answers are never positive evidence: an unreachable host or an
  unreadable answer gives unknown.

It is deliberately narrow: no general reading of PR approvals as permission, no caching across runs, no other API.

## The trusted policy

Owner identities and trusted repositories come only from the owner-installed trust policy (`instruction-governance`;
a generated copy of its reader is `scripts/trust_policy.py`): root-owned, at a fixed system location, with stable
account IDs for every owner. Without an installed, valid, securely owned and reviewed policy,
`authorization.canonical_policy()` returns none and `verify-auth` reports every standing reference as unknown, still
printing the facts the host records. No flag, environment variable, repository file or handoff record can supply the
policy instead: a trust root the agent could write is not one. Verification is advisory: it enforces nothing unless
the executor acts on it.

## Limitations

- Evaluation is as good as the host's records. The host records **an account**, not a person: an agent running with
  the owner's credentials (a `gh` login, a token) approves or merges as the owner, and nothing here can tell the
  difference. Approvals of authorization PRs therefore mean something only if agents do not approve or merge them
  with the owner's credentials. That is a rule for the owner's setup, not something this tool can enforce.
- Scope binds what the operation states and what the entry limits. An operation that leaves out a dimension the
  entry does not limit still verifies, so describe operations completely; an entry that should constrain a
  dimension must say so in its `scope`.
- A verified `spend` operation covers the spending only; its execution needs its own authorization.
- Bounded inspection: 100 first-parent commits and 100 reviews; beyond that, unknown.
- Spending limits are per operation. Cumulative budgets belong to `resource-budgeting` (Phase 2).
- `gh` must be installed and authenticated for live facts; otherwise every standing reference is unknown.
- Time comes from the local clock.
