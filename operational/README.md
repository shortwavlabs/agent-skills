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

`operational_records.py` checks **form**: required fields, types, enumerations, versions, and whether each
authorization reference is established, unestablished or invalid. It does not check **authenticity**: a well-formed
reference to a standing authorization can still point to an entry that does not exist, or was not approved by the
owner. That is checked at run time by the skill that relies on it. Likewise, a matching digest shows identity or
integrity, not correctness, provenance or authorization.
