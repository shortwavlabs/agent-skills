# Runtime authorization verification

`handoff.py verify-auth --action <action>` evaluates each authorization reference in a record for one operation, at
the moment of use. A record never grants authority; a reference that verifies is evidence that a standing
authorization covers this operation now.

## Contents
- [The model](#the-model)
- [Conditions, in order](#conditions-in-order)
- [Actions](#actions)
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
| verified | Yes, for the evaluated action only |
| inapplicable | No |
| invalid | No |
| unknown | No: ask the owner once |

## Conditions, in order

The first condition that fails decides.

1. The reference is well formed (shared `authorization-reference` format; R3 is never valid). Otherwise **invalid**.
2. An `owner-session` reference (a quotation) cannot be verified by another agent: **unknown**.
3. The operation names an action, and is not R3. Otherwise unknown, or inapplicable for R3.
4. A trusted policy exists. Otherwise **unknown** (see [the trusted policy](#the-trusted-policy)).
5. The reference names the designated authorizations file (`ops/authorizations.json`, or the file the canonical
   policy names). An authorizations-shaped file elsewhere (an example, a fixture) is not one: **invalid**.
6. The host was reached. Otherwise **unknown**.
7. The repository is trusted by the policy. Otherwise **inapplicable**: a repository cannot establish its own trust.
8. The referenced commit exists, and holds the referenced entry. Otherwise **invalid** (fabricated or missing).
9. The entry is well formed, matches the reference (who granted it, its level), was granted by an owner identity, and
   names an `approved_in` PR in the same repository.
10. The host records an approval or merge of that PR by an owner identity, still active (not dismissed, not superseded
    by a later change request). **That PR introduced or changed the entry** (its content at the PR's base is absent or
    different): merging an unrelated PR approves nothing already on the branch. The entry's content at the approved
    revision equals the referenced content. Git author fields never count.
11. The entry is unchanged on the current default branch (absent: revoked; changed: not covered), and was not removed
    and reintroduced after the approval (a reinstatement needs fresh approval).
12. Neither the entry nor the reference has expired.
13. The entry lists the operation's action, and the operation's level does not exceed the entry's.

Only then: **verified**. Content is compared, not commit IDs, so squash merges are handled.

## Actions

Whether a sentence such as "push feature branches and open draft PRs" covers an operation is a judgment no script
should make. Entries therefore list the actions they cover, and the operation names one:

```json
{
  "id": "push-feature-branches",
  "level": "R2",
  "operations": "Push feature branches of this repository to origin and open draft PRs",
  "actions": ["push-branch", "open-draft-pr"],
  "granted_by": "github:<owner login>",
  "approved_in": "https://github.com/<owner>/<repo>/pull/<n>",
  "expires": "2027-06-30T00:00:00Z"
}
```

Actions are lowercase slugs compared exactly; there is no global vocabulary, and a near-miss (`push-branches`)
simply does not match. An entry without `actions` evaluates to unknown. Approving a tool is never the action of using
it: an entry for `merge-pr` does not cover `delete-files`.

## The GitHub integration

`github_facts.gather()` reads, through `gh api` and nothing else: the repository and its default branch; the
referenced commit (GitHub answers a missing one with HTTP 422, read as "does not exist"); the authorizations file at
the referenced commit, at the PR's base, at each approved revision and on the default branch; the PR named in
`approved_in` (its merge, merged-by and base) and its reviews; and the commits that touched the file
on the default branch since the approval (up to 100; more is unknown). It writes nothing. Each reviewer's latest
decisive review counts: an approval later dismissed is `dismissed`, one followed by a change request is
`superseded`. Any failure to reach or parse the host gives `host_reachable: false`, hence unknown.

It is deliberately narrow: no general reading of PR approvals as permission, no caching, no other API.

## The trusted policy

Owner identities and trusted repositories come only from the canonical policy (RFC 0001, D14), whose format Phase 1d
defines. Until then `authorization.canonical_policy()` returns none, and `verify-auth` reports every standing
reference as unknown, still gathering and printing the facts the host records (a `facts:` line per reference), so the
owner can decide quickly. No flag, environment variable,
repository file or handoff record can supply the policy instead: a trust root the agent could write is not one.

## Limitations

- Evaluation is as good as the host's records. The host records **an account**, not a person: an agent running with
  the owner's credentials (a `gh` login, a token) approves or merges as the owner, and nothing here can tell the
  difference. Approvals of authorization PRs therefore mean something only if agents do not approve or merge them
  with the owner's credentials; that is a rule for the owner's setup, not something this tool can enforce.
- `gh` must be installed and authenticated for live facts; otherwise every standing reference is unknown.
- A dismissed approval is recognised only when the host records the dismissal.
- Time comes from the local clock.
