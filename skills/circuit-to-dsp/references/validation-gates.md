# Validation Gates For Circuit Models

## Contents

- Decompose the error before gating it
- Stage isolation
- Hard gates and quality targets
- Example: a discretisation gate family
- Coherent tones and phase ensembles
- Population-level gates and test tiers
- Checking fixture completeness by content
- Setting and changing criteria
- Envelope-scoped gates
- Product checks are not fidelity checks
- Reporting
- Checklist

The reference data comes from the `spice-circuit-modeling` skill (`references/golden-fixtures.md`). The measurement contract, source hierarchy, result axes and release integrity are in [circuit-reference-validation.md](circuit-reference-validation.md). This reference is about turning comparisons into **gates** whose PASS means something.

## Decompose The Error Before Gating It

Keep four artifacts distinct:

| Symbol | Artifact |
| --- | --- |
| A | The oracle (SPICE) |
| B | The reduced model run at a very high rate (close to continuous time) |
| C | The production discrete model at a production internal rate |
| D | The production path, including host-rate resampling filters |

Then:

- **model-reduction error** = B vs A (what the simplifications cost);
- **discretisation error** = C vs B, same stimulus and same phase (what the integrator and rate cost);
- **resampling error** = D vs C, or D against a higher oversampling factor (what the filters cost);
- **total error** = C vs A (and D vs A where the phase contract allows).

Never compare unlike quantities and call the difference "discretisation". A discretisation error measured against a matched high-rate model and a total error measured against the oracle answer different questions; a rule that mixes them can pass a method that is actually inadequate.

## Stage Isolation

Isolate a stage by driving it with the oracle's **own** signal at the stage input: the recorded node waveform, or the oracle's small-signal transfer to that node applied to the test tone, with amplitude **and phase**. Hold the stage's source and load as in the full circuit. A stage-isolated failure localises a defect; a whole-chain comparison only says that something is wrong somewhere.

## Hard Gates And Quality Targets

A **hard gate** encodes a bound the product actually needs; its failure blocks release. A **quality target** records a preferred engineering margin; it is always measured and printed but does not fail the run.

- Test exit status comes from hard gates only.
- Print quality targets as `TARGET MET` or `TARGET MISS (x dB short)` and count misses in the final summary line. Never print PASS for a missed target, never drop the line, never mark it expected-to-fail.
- Do not turn every desirable margin into a hard gate. Do not demote a hard requirement to a target to get a green build.
- Use a third status, **NOT EVALUATED**, when the data cannot establish the gate (below). It is neither PASS nor FAIL and must say why.

## Example: A Discretisation Gate Family

A pattern that separated concerns cleanly (the thresholds are examples, not defaults):

| Gate | Population | Requirement | Role |
| --- | --- | --- | --- |
| A1 absolute | Every case, including stress and exact-period cases, every sub-sample phase | Discretisation error ≤ an absolute bound at every production rate | Hard: nothing is ever badly discretised |
| A2 non-dominance | The cases inside the fidelity envelope | Worst phase-averaged discretisation error ≤ F, where F is the worst continuous-model (model-reduction) error over the **same** cases, recomputed from the current model on every run | Hard: the discrete approximation is not a larger error source than the model it discretises |
| A2 preferred margin | Same | ≤ F − margin (for example 3 dB) | Quality target: extra headroom, reported |
| A3 total | Every case | Total error vs the oracle within its worst and median bounds | Hard: the combined model is good enough |

Why the margin belongs in a target, not the hard gate:

1. A1 already bounds discretisation absolutely at every tested phase.
2. A3 measures the combined model against the oracle directly.
3. Output-level gates measure what the product actually produces.
4. Model and discretisation errors are deterministic and can correlate; their powers do not simply add, so a power budget between them is a heuristic, not a bound on the total.
5. Improving the model lowers F. A relative budget can turn red while the discrete model and the product output both improve.

Never pin F to a historical number: the budget must track the current model.

## Coherent Tones And Phase Ensembles

A test tone whose period is an exact integer number of samples at the internal rate samples the same points of every cycle, so its discretisation error depends on the sub-sample phase of the stimulus and can vary by tens of dB with that phase. This commensurate-tone phase sensitivity is a real response of the discrete model, not a measurement bug. Consequences:

- A budget metric evaluated at one phase per case becomes a lottery at exact-period rates.
- Keep exact-period cases in the **absolute** gate at every phase (A1): they are legitimate stress cases.
- For **budget** metrics, average error **power** over a deterministic ensemble of sub-sample phases, for example φ_m = φ₀ + 2π·f·(m/M)/F_s for m = 0 … M−1 (M = 16 was sufficient in the case study; check that the average is stable as M grows), each phase compared with a reference run at the same phase. Report the phase-averaged value and the minimum/maximum over the phases.
- Never "fix" a coherent failure by detuning the test tones.

The measurement mechanics (coherent sampling, windows, harmonic-vector error) are in the `dsp-engineer` skill's `references/engineering-checks.md`.

## Population-Level Gates And Test Tiers

A metric defined over a population ("F = worst model error over all N in-envelope cases of the grid") is a property of **that** population. A smaller test subset cannot compute a different F and claim to have evaluated the same gate: a subset's worst case is a different, usually stricter, reference.

- If a tier does not contain the complete population, the gate's status in that tier is **NOT EVALUATED**, with the reason (for example "requires the complete N-case population; this fixture holds a K-case subset"). This differs from the `UNQUALIFIED_NUMERICAL` status in [circuit-reference-validation.md](circuit-reference-validation.md): that one means a computation completed without enough refinement evidence; NOT EVALUATED means the available data cannot establish the gate at all.
- Keep the subset computation visible as an explicitly labelled **subset diagnostic** (subset floor, worst value, delta, case, phase range). It is informational.
- Continue to hard-gate everything the subset **can** evaluate (absolute per-case bounds, per-case totals).
- Every tier that gates a release (in the case study, STANDARD and FULL; the RELEASE tier in [circuit-reference-validation.md](circuit-reference-validation.md#qualification-failures-and-tiers) adds freeze and publication checks) must contain every gate's complete population. A release-tier fixture that lacks it must **fail**, not quietly become NOT EVALUATED.
- Decide completeness from fixture **content**, not from the tier's name.
- Population worsts need not come from the same case. Report per-case diagnostics (cases whose own discretisation error exceeds their own model error) so reviewers see the whole picture.

## Checking Fixture Completeness By Content

```python
from itertools import product

def population_complete(cases, axes):
    """True only if cases hold exactly one case per grid point: no missing, duplicate or extra cases."""
    want = set(product(*axes.values()))
    got = [tuple(c[k] for k in axes) for c in cases]
    return len(got) == len(want) and set(got) == want

axes = {"control": (0.0, 0.5, 1.0), "level_v": (0.02, 0.3, 1.0, 2.5), "freq_hz": (100.0, 1e3, 5e3)}   # the grid the gate defines
```

Test the check itself: a truncated grid (one case missing) and a grid with one case replaced by a duplicate of another must both be rejected.

## Setting And Changing Criteria

- Derive tolerances from the product requirement and the reference's own numerical uncertainty; a gate tighter than the oracle's convergence is noise.
- A failing gate is a finding. Keep it red and report it with numbers until the model is fixed or the criterion is revised for a stated reason.
- Revise a criterion only as a documented revision: old definition, new definition, the evidence that the old one was unsound (for example phase-lottery results, a population defined inconsistently), and the full before/after table. "It made the build green" is never a reason.
- No expected-failure markers, no silently skipped cases, no widened windows without evidence.

## Envelope-Scoped Gates

Gate fidelity inside the declared fidelity envelope (see `circuit-reduction.md`). Outside it, gate robustness: finite output, bounded peak error, no chattering, continuity through mode changes, recovery. Report out-of-envelope fidelity numbers as information.

## Product Checks Are Not Fidelity Checks

Plugin validators prove host compatibility, not circuit accuracy, and vice versa. A circuit-emulation plugin needs both:

- host validation (for example pluginval at high strictness and auval), mono and stereo, bypass, state save/restore, automation, sample-rate and block-size changes, silence, hot and non-finite input, finite output, no allocations in the callback;
- the fidelity gates above, plus a performance harness.

Framework-specific checks are in the `juce-plugin` skill (`references/production-plugin-practices.md`).

## Reporting

- For each rate: worst and median per gate, the worst case's identity, its phase range, and the margin (signed, in dB) to the gate and to any target.
- For every revision: the old and new numbers side by side, and what changed in the model or criterion.
- Keep diagnostic measurement modes (rate sweeps, phase studies, production-path comparisons) in the test executable, non-gating, so evidence can be regenerated.
- Separate model identity (what the audio does) from document/qualification identity (what the evidence says); see [release integrity and versioning](circuit-reference-validation.md#release-integrity-and-versioning).

## Checklist

- [ ] Errors decomposed: reduction (B vs A), discretisation (C vs B), resampling (D vs C), total (C vs A).
- [ ] Stage isolation driven by the oracle's own node signal with phase.
- [ ] Hard gates and quality targets separated; NOT EVALUATED used and explained where data is insufficient.
- [ ] Relative budgets recomputed from the current model; never pinned.
- [ ] Exact-period cases in absolute gates; phase ensembles for budget metrics; no detuning.
- [ ] Population-level gates evaluated only on complete populations, checked by content; release tiers fail if incomplete.
- [ ] Criteria changes documented with evidence; nothing loosened to get green.
- [ ] Fidelity gated inside the envelope, robustness outside it.
- [ ] Host validation and fidelity validation both run and reported separately.
