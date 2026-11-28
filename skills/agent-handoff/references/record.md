# The handoff record

## Contents
- [Location and retention](#location-and-retention)
- [Format](#format)
- [Field by field](#field-by-field)
- [Artifacts and jobs](#artifacts-and-jobs)
- [Claim and transfer](#claim-and-transfer)
- [What stays local](#what-stays-local)

## Location and retention

- `.agent-state/handoffs/<encoded branch>.<digest>.md`: the branch name percent-encoded (so `a/b` and `a--b`
  differ) plus a digest of the exact name (so `Feature` and `feature` differ on case-insensitive filesystems).
  `.agent-state/` ignores itself (its `.gitignore` holds `*`), so nothing there is ever staged. `handoff.py new`
  refuses a location git would track, and any symlinked directory, ignore file or record.
- **Private.** Records are mode 0600 in 0700 directories: a record may hold a claim transfer token. `check` reports a
  record other users can read.
- **Atomic, and never lost.** A record is written to a temporary file, flushed and renamed into place. `new
  --supersede` first keeps the previous record under `history/` (created exclusively, named by its validated
  `Created` time and a digest of its bytes, never overwriting), then replaces it, and refuses if the record changed
  meanwhile (another session superseding at the same time). An interruption leaves the current record intact.
- **Valuable, not disposable.** A record is never deleted automatically. `git clean -x` would delete the directory:
  never run it in a checkout that may hold records.
- **Preserving one** that must outlive the machine: a private backup (`workspace-housekeeping`), or, in a private
  repository whose owner chooses it, a committed `ops/handoffs/` directory. Never force-add an ignored file.

## Format

`handoff` version 1 (RFC 0001, document 05; `operational/formats.json`). Required header lines and sections, in this
order; optional ones are marked.

````markdown
# Handoff: <one-line task title>

Version: 1
Created: 2026-11-27T18:40:00Z
Author: <agent product> / <model> / <session id, if any>
Repository: <host/owner/name of the remote> | none (no remote: local repository)
Checkout: <host name>:<checkout path>                (optional)
Branch: <branch>
HEAD: <full commit id>
Upstream: <in sync | ahead n | behind n> (<upstream ref>); cached; last fetched <time> | not pushed; no upstream
Working tree: clean | dirty (<n> paths, listed under State) | unknown (<why>)
PR: <URL> | none
Claim: <claim id> | none
Transfer: <one-time transfer token> | none          (optional)
Supersedes: <Created time of the previous record> | none

## Goal                          objective, and what is in and out of scope
## State                         one status line; then each uncommitted path with its content digest
## Done                          evidence-labelled items
## Pending                       ordered next steps; the first startable without reading anything else
## Decisions and rejected approaches
## Blockers and decisions needed  owner decisions, each as a question with options
## Artifacts                     (optional) a JSON block: artifacts with stable identities and digests
## Authorizations in force       a JSON block: authorization references, as originally recorded
## Running processes and jobs    text, or a JSON block of jobs
## Budget                        (optional) spend and limits, where relevant
## Verification                  tests and checks: commands, results, what was not tested
## Assumptions and limitations   known defects, limitations, open questions; evidence-labelled
## Lessons and proposals         (optional) see continuity.md
## Resume                        the steps for the receiving agent
````

`handoff.py check` validates the structure with the shared checker (a generated copy of
`scripts/operational_records.py` and of `operational/formats.json`), then compares the record with the repository.

## Field by field

| Field | Write | Avoid |
|---|---|---|
| Goal | What the owner asked for, the scope, and what is explicitly out of scope | Restating the whole conversation |
| State | One line ("refactor half done; tests pass on HEAD"), then dirty paths and why | Vague status ("mostly done") |
| Done | `- [VERIFIED] <claim>; method: <command> exit 0; artifact: commit <id>; at: <time>`, or OBSERVED, REPORTED, INFERRED (with premises), UNKNOWN | VERIFIED without method, artifact and time |
| Pending | Numbered, concrete, ordered | "Continue the work" |
| Decisions and rejected approaches | The decision and its reason; each rejected approach with the evidence against it | Rejected approaches without the reason (they get retried) |
| Blockers and decisions needed | Questions only the owner can answer, with options | Questions the next agent can settle itself |
| Authorizations in force | The references exactly as recorded (standing: `ops/authorizations.json@<commit>#<id>`; owner-session: with the quote) | Paraphrases; anything the owner did not grant |
| Budget | Spend so far, the authorized limit, what remains, as numbers | Estimates presented as spend |
| Verification | Commands and results; what was not tested and why | "All good" |
| Assumptions and limitations | Known defects, limitations, open questions, each labelled | Hiding a failing test |
| Resume | The steps you would want, starting with `handoff.py check` | Instructions that grant authority |

**Identity and state.** `Repository:` is the remote's canonical identity (`github.com/owner/name`), never a remote's
name: two checkouts with an `origin` remote may be different repositories. `Checkout:` names this host and path, so
a resume elsewhere knows local files and processes may differ. `Upstream:` says the comparison came from cached
remote-tracking refs and when they were last fetched; `check --fresh` asks the remote itself (read-only). Under
State, `new` lists each uncommitted path as `- <path> sha256:<digest>[+x] index=<mode>:<blob>` (or `deleted`, or
`not-hashed`; the index part is `none` when nothing is staged and `conflict` for an unmerged entry), so `check` tells a
matching inventory from matching content and staged state, and notices a changed file mode, without archiving
anything. A failed `git status` is recorded and
reported as unknown, never as clean.

Unfinished qualification work: record the frozen criteria by digest and commit under Artifacts, and say in Pending that
they must not change before the run. A receiving agent that wants different criteria needs the owner's approval of
an amendment.

## Artifacts and jobs

**Artifacts** use the shared `artifact` object: `{"type": "file", "id": "<path relative to the checkout>",
"sha256": "<digest>"}`, or `commit`, `tree`, `url`, `pr`, `ci-run` with an `id`, and optionally `supports` (the claim
it is evidence for). `check` establishes existence, the type (a regular file; a commit or tree object of that type)
and the content identity, and lists URLs, PRs and CI runs for you to open. It never decides whether an artifact
establishes a result: that stays your judgment.

```json
[
  {"type": "file", "id": "results/sweep-a/summary.json", "sha256": "<64-hex digest>"},
  {"type": "commit", "id": "<40-hex commit id>"},
  {"type": "ci-run", "id": "https://github.com/<owner>/<repo>/actions/runs/<id>"}
]
```

**Jobs** under `## Running processes and jobs` may be a JSON list of `job` objects: `id`, `kind` (`process`,
`ci-run` or `remote`), `command`, `started`, and as known `host`, `pid` with `process_start` (from `ps -o lstart=` or
`/proc/<pid>/stat`), `boot`, `cwd`, `log`, `outputs`, `inputs_sha256`, `expected_end`, `stop` (how the owner can
stop it) and `cost`. `check` uses the same process-identity code as `development-coordination` (a generated copy of
`operational/process_identity.py`): **running** only if PID and start time match, **ended** only when provably so
(the PID is gone or reused, or the host rebooted), and **unknown** otherwise; an unreadable process is never taken
as ended. It never restarts, duplicates or stops anything.

## Claim and transfer

`Claim:` names the claim the work depends on. Before leaving, the holder runs `coordination.py transfer` and writes the
printed one-time token in `Transfer:`. The successor runs `coordination.py accept --transfer-token <x>` and gets its own
session token; the old token stops working. If you cannot transfer (no claim tool, the claim is gone), write
`Transfer: none` and say in State whether the claim was released or will expire, so the successor knows to acquire
anew.

## What stays local

The record is for the next agent on this machine and may hold paths, process IDs, the transfer token and authorization
references. None of that goes into a public repository or a PR. `handoff.py summary` produces a **redacted draft**
from an allowlist: the title, the record's time, HEAD, the upstream state, and Goal, State's first line, Done,
Pending, Blockers, Verification and limitations. Headers (repository, checkout, author, claim, transfer token),
authorization records, artifacts, jobs and process commands are never included. Within the allowlisted prose it
replaces private paths, credential-like strings (GitHub and cloud tokens, `password:` values, URL credentials,
private keys), 32-hex tokens and e-mail addresses. Redaction is a pattern match, not a guarantee: read the draft
before posting it.
