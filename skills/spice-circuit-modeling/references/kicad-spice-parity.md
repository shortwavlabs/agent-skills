# KiCad And SPICE Parity

## Contents

- Direction of truth
- Four separate gates
- Build the mapping before drawing
- Adapter subcircuits
- Structural validation
- Mutation self-test
- Numerical parity
- Simulator workbook and GUI caveats
- KiCad SPICE-export pitfalls
- Hand-off to hardware
- Checklist

This reference covers turning a trusted SPICE netlist into an editable KiCad schematic (or checking an existing schematic against a netlist) without changing the circuit. The same method applies to other EDA tools that export SPICE.

## Direction Of Truth

Decide and write down which artifact is canonical. When a validated netlist exists, it is usually the oracle and the schematic is a **derived view**: if they disagree, the schematic is wrong. Do not redraw the circuit from memory or from a photo of the original schematic and then "fix" the netlist to match. Do not edit the canonical netlist or its models from the schematic side.

## Four Separate Gates

| Gate | What it proves | What it does not prove |
| --- | --- | --- |
| ERC clean | Symbols are connected legally (no unconnected pins, conflicting drivers, missing power flags) | That the connections are the right ones |
| Schematic connectivity looks right | Nothing | Anything: a visually correct symbol can export the wrong node order |
| Exported SPICE is structurally equivalent to the oracle | Same elements, values, models and topology | That both simulate identically (directives, includes, engine) |
| Numerical parity | Same results for the same stimuli, settings and engine | Hardware accuracy |

Pass all four, in this order, and re-run them after every schematic edit.

## Build The Mapping Before Drawing

Make an explicit element-by-element and net-by-net mapping table from the oracle:

- element count and designators (in KiCad 10, references must end in a digit and the simulator infers the device type from the reference prefix; verify on your version, and choose designators that export as the intended SPICE element letter);
- device identity: model/subcircuit name and the file it comes from;
- node names for the nets you will label, and the rest left to the tool;
- polarity/orientation of every diode, electrolytic capacitor, source and switch;
- transistor pin order (SPICE order C-B-E, D-G-S) versus symbol pin numbers;
- op-amp pin order per section and which package half is which;
- pot segments: which end is pin 1, which segment is "wiper to CW end", and how the reference expresses the taper;
- subcircuit argument order and parameters.

If the schematic is generated programmatically, validate the output the same way as a hand-drawn one; the generator is not evidence.

## Adapter Subcircuits

Symbols rarely match reference models one to one. Bridge them with small **project-owned adapter subcircuits** that contain wiring only, never device parameters:

- a dual op-amp package symbol exports as one SPICE item: wrap two instances of the unchanged reference op-amp model in one 8-terminal subcircuit whose terminal order equals the package pins;
- a three-pin pot symbol cannot carry two parameterised resistor segments: a pot adapter holds exactly the reference's two segment expressions;
- vendor pin orders: a shim maps the vendor's terminal order to the circuit's.

Rules: the adapter `.include`s the same model file the oracle uses (so there is one copy of every model); the adapter header states "interconnect only"; the structural validator flattens adapters before comparing.

## Structural Validation

Export the netlist with the tool's command line (for KiCad 10: `kicad-cli sch export netlist --format spice`; confirm the options with `kicad-cli sch export netlist --help` on the installed version), then compare with the oracle programmatically (`scripts/netlist_compare.py`):

1. Parse both decks within a declared grammar: join continuation lines, drop comments, normalise case and numbers (`20e3` = `20k`), treat ground aliases as one net. Anything outside the grammar (an unknown element letter, XSPICE `A` devices, an unrecognised directive, `.lib FILE SECTION`, a nested inline subcircuit, any `.control` command outside a small read-only allowlist) must stop the comparison as **not qualified**, never be skipped: a validator that silently drops syntax can report false equivalence.
2. Flatten project adapters one level (reject an adapter that calls another adapter rather than guessing).
3. Pair elements by name through an explicit alias map (for example `vtest1 → vtest`, `xic1.xa → xic_a`), and list tool-only elements that are allowed because all their terminals sit on one net (for example a strapped pot segment).
4. Infer **one consistent 1:1 net map** from every paired terminal: polarised and multi-terminal parts bind first; symmetric parts (R, C, L) are oriented by the nets already mapped. Any conflict is a pin swap or a wrong net.
5. Report every unmapped net on either side (a missing or extra connection).
6. Compare values numerically, model names (or model definitions when the tool renames per-instance models), inline subcircuit bodies (with ports bound in order), source specifications with defaults made explicit, behavioural expressions with `v(net)` references remapped, and `.param`, `.func`, `.options`, `.temp`, `.global`, `.ic`/`.nodeset` (with nodes mapped). A model or subcircuit defined inline on only one side cannot be verified and is a difference.
7. Check which **file** each model comes from, not just its name: two libraries can define the same name differently. Hash the files with the manifest (see `oracle-provenance.md`).

When the comparison reports **not qualified**, equivalence has not been established. Either extend the comparator's grammar for the construct, adding a self-test with a planted fault that the extension must catch, or review the unsupported construct manually and record the review (what it is, why it is equivalent, who checked it). Until one of those is done, report the schematic as unverified.

## Mutation Self-Test

A validator that has never caught a planted fault proves nothing. Keep a mutation list and require every mutation of the exported deck to be reported:

- diode or LED reversed; zener reversed;
- transistor collector/emitter swapped; JFET drain/source or drain/gate swapped; base/emitter swapped;
- op-amp inputs swapped; op-amp halves swapped; supply pins swapped;
- pot ends reversed; pot pin 1 and wiper swapped; pot driven by the wrong control parameter;
- battery/source reversed; switch contact and control swapped; switch logic inverted;
- element moved to a wrong net; value changed by 1 %; model name changed; element missing;
- `.options` line dropped; `.ic` on the wrong node; `.param` default changed.

`netlist_compare.py --mutation-check` generates generic mutations for any deck; keep circuit-specific ones (switch logic, control mapping) in the project's own validator. Report "N/N planted faults detected".

## Numerical Parity

After structural equivalence, simulate the oracle and the exported deck with **identical** stimuli, options and engine, over a case grid that exercises every branch: control endpoints, every switch and operating state, supply modes, several loads, no input. Compare transient, DC and AC results within a declared solver-noise tolerance, and run the circuit's behaviour checks (bias, switching, clipping, response, loading, input impedance) on both. Run the same comparison in the GUI's bundled engine as well as the command-line engine.

## Simulator Workbook And GUI Caveats

- GUI simulation tabs may **rebuild analysis lines** from dialog fields. In KiCad 10 (verify on your version), editing an AC tab through the Simulation Command dialog regenerates the `.ac` line and drops extra lines such as `.options itl1=...` or a `.param` that selects an operating state. Use custom tabs for multi-line commands and re-inspect the workbook file after any GUI edit.
- Lines that exist only in a GUI tab are not in the command-line export, so the structural check never sees them. Keep state-selecting parameters and solver options that the analysis needs visible in the documentation and validated separately.
- Some GUIs accept only a bare `.op` (KiCad 10's does); read operating points from a transient tab at t = 0 when needed.
- Keep a documented sanity value per tab (for example "state-A tab, 1 kHz: about +N dB", with N taken from the validated oracle) so a silently broken tab is noticed.

## KiCad SPICE-Export Pitfalls

Observed with KiCad 10.0 and its bundled ngspice 45 (tool-version dependent: verify each on the installed version before relying on it, and do not change generic SPICE practice because of one KiCad release):

- A multi-unit symbol (dual op-amp) exports as **one** SPICE item; it needs a package-level wrapper subcircuit.
- References must end in a digit, otherwise annotation errors block simulation, and the reference prefix decides the device type (an `LED` reference can be inferred as an inductor).
- If any line of a schematic text item is a recognised directive, the **whole** text item is exported, prose included: never start a note line with `.`.
- Export element order differs from file order and changes after unrelated edits: one more reason for order-stress testing (see `numerical-qualification.md`).
- `Sim.Library` fields expand `${HOME}` and project variables; text-directive `.include` lines expand project variables but not environment variables. Relative includes inside a library resolve relative to that library.
- Local labels export as `/NAME` and automatic nets as `Net-(...)`-style names; some simulator expression commands reject those names, so export results via rawfiles instead of `let`/`print` expressions.
- The bundled library engine may need its code models loaded explicitly, or `POLY` sources fail with code-model errors.
- Parameter values containing spaces must be quoted in symbol fields.
- Per-user UI state files (`*.kicad_prl`) are not project data; ignore them in version control.

## Hand-Off To Hardware

Simulation parity is not a PCB. Symbol pin numbers are not proof of physical package pinout; verify every pinout against datasheets and assign footprints deliberately before layout. Make review archives from version control (`git archive`) rather than OS compression, which adds metadata folders.

## Checklist

- [ ] Direction of truth written down; the oracle is never edited from the schematic.
- [ ] Element/net mapping table built before drawing, including pin orders and pot segments.
- [ ] Adapters are interconnect-only and include the oracle's own model files.
- [ ] ERC clean, structural equivalence, mutation self-test and numerical parity all pass, re-run after every edit.
- [ ] Workbook/GUI tabs re-inspected after GUI edits; their extra lines documented.
- [ ] Both GUI and command-line engines exercised.
- [ ] Physical pinouts verified separately before any layout work.

## Sources

- KiCad documentation for the installed version (https://docs.kicad.org/): the Command-Line Interface chapter (`kicad-cli sch erc`, `kicad-cli sch export netlist`) and the Schematic Editor's simulator chapter (symbol simulation fields, workbooks).
- ngspice User's Manual for the engine version KiCad bundles (https://ngspice.sourceforge.io/docs.html): subcircuits, `.include` resolution, XSPICE code models.
