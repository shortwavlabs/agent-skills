# The trust policy

The trust policy is the canonical declaration of who the owner is, which repositories are trusted, and where each
keeps its standing authorizations. `agent-handoff`'s runtime verification checks approvals against it.

## Contents
- [Three things not to confuse](#three-things-not-to-confuse)
- [Format](#format)
- [Bootstrap: the owner's installation procedure](#bootstrap-the-owners-installation-procedure)
- [Verification](#verification)
- [Revisions, rollback and trust expansion](#revisions-rollback-and-trust-expansion)
- [Limits of running agents under the owner's account](#limits-of-running-agents-under-the-owners-account)

## Three things not to confuse

| Layer | What does it | What it guarantees | What it does not |
|---|---|---|---|
| **Protecting the trust configuration** | A root-owned policy file in a root-owned directory | The agent's account cannot write it (without administrator rights) | Anything about how the policy is read or used |
| **Verifying authorization evidence** | `trust_policy.py` and `agent-handoff`'s evaluator, run as the owner's user | An honest, deterministic answer: verified, inapplicable, invalid or unknown | Nothing against a process that edits these scripts or ignores their answer: they are user-writable, advisory code |
| **Enforcing execution restrictions** | Whatever actually executes: the harness's permission mode and sandbox, OS permissions, branch protection on the host | The operation is actually prevented | Only exists where it is configured; this skill configures none of it |

A protected configuration does not make a user-writable verifier, or an advisory agent skill, a security boundary.
Verification informs an agent that follows its instructions; it stops nothing by itself. Authorization verification
stays advisory unless the executor enforces the decision.

## Format

`trust-policy` version 1 (`operational/formats.json`; checked by `scripts/trust_policy.py`):

```json
{
  "kind": "trust-policy",
  "version": 1,
  "revision": 2,
  "previous_sha256": "<SHA-256 of the bytes of revision 1>",
  "owners": [ { "identity": "github:<login, a label>", "account_id": 1234567 } ],
  "agent_accounts": [ "github:<an agent or bot account>" ],
  "repositories": [
    { "identity": "github.com/<owner>/<repository>", "repository_id": 7654321,
      "authorizations_file": "ops/authorizations.json" }
  ],
  "provenance": { "repository": "github.com/<owner>/<policy repository>", "path": "trust-policy.json",
                  "commit": "<40-hex commit of the reviewed copy>" }
}
```

| Field | Meaning |
|---|---|
| `revision`, `previous_sha256` | Versioned revisions. Revision 1 has no predecessor; every later one names the digest of the one it replaces |
| `owners[].account_id` | **Required.** The stable numeric GitHub user ID. It establishes the owner; the login is only a readable label. A renamed account keeps its ID; a login reused by someone else has another ID |
| `agent_accounts` | Accounts known to be agents or bots. Never owners |
| `repositories[].repository_id` | The stable GitHub repository ID, where practical. A recreated repository under the same name has a new ID and is not trusted; a renamed repository is outside the policy until the owner updates it |
| `repositories[].authorizations_file` | The designated authorizations file (default `ops/authorizations.json`) |
| `provenance` | Optional: where the reviewed copy of this exact content lives |

Unknown fields, duplicate keys, duplicate identities, an owner without an account ID, an identity that is both owner
and agent, an unsafe file path, or a version other than 1 make the policy invalid. No field widens trust by pattern.

## Bootstrap: the owner's installation procedure

Done by the owner, never by an agent. Agents never run `sudo`. Every step is a plain command the owner can read
before running it:

1. Write the policy from `python3 scripts/trust_policy.py template`. Look up the stable IDs:
   `gh api users/<login> --jq .id` and `gh api repos/<owner>/<repo> --jq .id`.
2. Review it, ideally in a private repository, and record the reviewed commit under `provenance`.
3. Install it, root-owned and writable by no one else:

```bash
sudo install -d -o root -m 755 "/Library/Application Support/AgentOperations"      # Linux: /etc/agent-operations
sudo install -o root -m 644 trust-policy.json "/Library/Application Support/AgentOperations/trust-policy.json"
sudo -k                                                                               # drop cached sudo credentials
```

4. Check and record it: `python3 scripts/trust_policy.py verify` must say `trusted:`; then
   `python3 scripts/trust_policy.py remember` records this revision as reviewed.

## Verification

`trust_policy.load()` (used by `verify` and by `agent-handoff`) accepts the policy only when:
- it is at the system location for this platform, as a regular file, never through a symlink;
- the file and every directory above it are owned by root and writable by no group or other user;
- it parses strictly and passes the format and semantic checks above;
- it may follow the last reviewed revision (next section).

Otherwise it returns no policy with the reason, and every consumer treats that as no trust. `verify --path` inspects a
draft anywhere, but a file found that way never grants authority.

## Revisions, rollback and trust expansion

`remember` keeps a record of the last reviewed revision (`~/.local/state/agent-operations/trust-policy-seen.json`).
Against it, `load()` refuses:
- a **rollback** to an older revision;
- **different content under the same revision** (a silent replacement);
- a successor that does not name the reviewed revision's digest, or a **skipped** revision whose chain cannot be
  checked;
- any **expansion of trust** (a new owner, repository or repository ID) until the owner reviews the new revision and
  runs `remember`. Narrowing trust is accepted at once.

The record is in user space, so an agent could rewrite it: it is a tripwire that makes silent changes visible to an
agent following its instructions, not a lock. The root-owned file is the protection; the review is the owner's.

## Limits of running agents under the owner's account

- **Same user, same powers.** An agent runs with the owner's operating-system account: it can read and change
  everything that account can, including these scripts, the review record, instruction files and the `gh`
  credentials.
- **Existing sudo rights.** If the owner's account may use `sudo`, an agent's command could too. With cached sudo
  credentials (sudo's timestamp, typically minutes after the owner last typed the password), it would not even be
  asked for the password. The root-owned policy then protects nothing. Mitigations, for the owner to choose:
  - run `sudo -k` before starting agents;
  - set `Defaults timestamp_timeout=0`;
  - keep administrator rights on a separate account;
  - run agents under their own operating-system user.

  The canonical instructions forbid agents from running `sudo` at all, but an instruction is not enforcement.
- **Credentials.** The owner's `gh` login on the same machine lets an agent approve as the owner
  ([identity](identity.md)). Reserve owner credentials for the owner; give agents their own identity where possible.
