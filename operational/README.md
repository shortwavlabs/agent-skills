# operational/

The single sources shared by the Operational Skills family ([RFC 0001](../rfcs/0001-agent-operations/README.md)). This
directory is not a skill and is never installed. Each family skill carries generated copies of what it needs, so every
skill installs on its own.

| File | What it is |
|---|---|
| [core.md](core.md) | The canonical operational core: risk levels, rules, authorization, precedence, evidence labels |
| [formats.json](formats.json) | The normative definitions of the Phase 1 record and scenario formats |
| [copies.json](copies.json) | Each source and the paths of its generated copies (none yet: the first family skill arrives in Phase 1b) |
| [examples/](examples/) | One valid example per format, checked by the repository validator |
| [fixtures/](fixtures/) | Expected runtime outcomes for authorization references, for Phase 1c to satisfy |

## Changing the core

1. Edit `core.md` and increment its `Revision:` line.
2. Review the effect: `python3 scripts/operational_sync.py --diff`.
3. Regenerate the copies: `python3 scripts/operational_sync.py --write`.
4. Run `python3 scripts/validate_skills.py`. The regenerated copies are reviewed in the same PR as the source.

Never edit a copy. The validator reports a copy as missing, edited, outdated (generated from another revision or
digest) or unlisted ([operational_sync.py](../scripts/operational_sync.py)).

## Changing a format

- Removing or renaming a field needs a new version. Readers reject versions they do not know; they never guess.
- Adding an optional field keeps the version.
- Update the matching example here and the fixtures in
  [operational_records.py](../scripts/operational_records.py)'s self-test.

## What the checks prove, and what they do not

`operational_records.py` checks **form**: required fields, types, enumerations, integer versions, duplicate keys,
contradictory dates. It gives every authorization reference a structural status, `invalid` or `unverified`, and
**neither grants authority**. A well-formed reference can still point to a commit or entry that does not exist, or to
one that expired, was revoked, changed after approval, or was never approved by the owner. Only the runtime
verification of Phase 1c can report `verified`, the one status that grants authority.
[fixtures/authorization-runtime.json](fixtures/authorization-runtime.json) defines what that runtime verification must
report for each of those cases; Phase 1a checks only the structural column.

`operational_sync.py` accepts only the sources listed in its reviewed `APPROVED` table (today, `core.md`), each with
one designated destination name, and never overwrites a file that is not already a generated copy of that source. A
matching digest shows identity or integrity, not correctness, provenance or authorization.
