# Interactive guitar-gear runtime export

Use for Blender assets destined for an interactive amp, pedal or rack editor. Source construction rules still apply to the master; these reductions apply only to the runtime derivative. Material translation belongs to [runtime PBR](../../guitar-gear-materials/references/runtime-pbr.md), camera translation to [runtime presentation](../../guitar-product-render/references/runtime-presentation.md), and acceptance to [runtime QA](../../guitar-gear-qa/references/runtime-qa.md).

## Protect the source

Inspect the accepted file, evaluated instances, dimensions, controls, materials and cameras first. Record its revision/hash. Save `gear_master.blend` → `gear_juce.blend` → `gear.glb`; never destructively optimize the master. Preserve its reusable components, cutters, production geometry, studio lights, QA cameras and material-development helpers. Scope repeatable export work to an explicit `EXPORT_JUCE` collection. Reopen the derivative and exported asset before delivery.

Use the existing [Blender operations](blender-operations.md) procedure for nested instances and context-sensitive conversion. Source object counts are not evaluated assembly counts.

## Semantic hierarchy

Export application roles, not construction history. An amplifier example (adapt counts/names to the actual product):

```text
EXPORT_JUCE
└── AMP_ROOT
    ├── HEAD_STATIC
    ├── CAB_STATIC
    ├── CTRL_BASS
    │   ├── VIS_BASS
    │   └── HIT_BASS
    ├── CTRL_CH1_GAIN
    ├── CTRL_CH2_GAIN
    ├── SWITCH_AMP_MODE
    ├── LED_POWER
    ├── LED_CH1
    ├── LED_CH2
    ├── INPUT_HIGH
    └── INPUT_REGULAR
```

Each moving control can instead be a single semantic mesh with a separate proxy if its pivot is already correct. Do not rename an accepted runtime contract unnecessarily. Keep fixed toggle nuts/bushings and printed scales in the static assembly; only the lever or knob rotates. Preserve jack attachment frames for optional plugs/cables.

Join a knob's cap, skirt, pointer and grip ribs into its visual mesh while retaining material slots, silhouette and pointer readability. Consolidate noninteractive shells, chassis, fascia, piping and fixed fasteners into sensible assemblies. Share equivalent mesh data where useful. Joining objects does not eliminate separate draw calls for different material primitives. Measure scene graph complexity and draw calls as well as triangles; never flatten away controls or independently driven LED materials.

Bake flat ticks, numbers, section rules, logos and warning text into panel graphics. Keep relief geometry only where raised/engraved detail changes silhouette or visibly contributes parallax at maximum intended zoom. Fiber-level grille geometry is normally replaced by the material workflow.

## Pivot and metadata contract

Place the moving node origin at its shaft/pivot and verify the local rotation axis. Preserve its imported rest quaternion. Resolve transform application in the derivative before recording calibration; do not apply transforms again after calibration. Keep parent scales well behaved and test mirrored controls. Blender's Z-up to glTF Y-up conversion means a source-world axis is not automatically the loaded node's local axis: validate the exported result.

Enable custom-property/extras export in the installed Blender glTF exporter. Example properties on a control, expressed here as JSON-compatible data:

```json
{
  "ui_type": "knob",
  "parameter_id": "bass",
  "min_angle": -135,
  "max_angle": 135,
  "rest_angle": 0,
  "rotation_axis": "Y",
  "rotation_sign": -1,
  "interaction": "vertical_drag",
  "hit_target": "HIT_BASS"
}
```

Define angles in degrees about the loaded node's local axis. In this convention `min_angle`, `max_angle` and `rest_angle` are calibration coordinates before applying direction; apply `rotation_sign` once to the angle difference. If existing metadata stores already-signed physical angles, preserve that convention and do not apply another sign. Record which convention is used.

For a toggle provide `ui_type = "toggle"`, `parameter_id = "ampMode"`, `state_count = 3`, local axis, `state_angles`, `rest_angle`, `state_labels` and a hit-target name. Angles must come from the actual switch travel, not a universal amp angle. Indicators use `ui_type = "indicator"` and a derived `state_id`, such as `power`; they are not extra host parameters. Two input nodes may deliberately reference one `inputMode` with distinct choice indices; one parameter binding serves both targets.

Semantic interactive nodes and their hit targets must have unique, explicitly assigned names in the derivative before export. Blender auto-suffixes such as `.001` and realized duplicate instances are not stable semantic IDs. Inspect the raw exported node list too: fail on duplicate contract names, missing expected names or unexpected suffixed replacements before a loader can rename them. Do not rely on `getObjectByName()` returning an arbitrary first match. Static construction names outside the contract need not be renamed cosmetically.

## Validation manifest example

Keep an expected contract beside the GLB, independently maintained from the exported `userData`. This small example describes a one-knob/two-input device; extend it for the actual product, not a fixed amp control count. Positions are illustrative runtime-frame meters; replace them with evaluated camera data.

```json
{
  "schema_version": 1,
  "asset": "gear.glb",
  "root": "GEAR_ROOT",
  "parameters": {
    "gain": { "type": "continuous" },
    "inputMode": { "type": "choice", "choices": ["Regular", "High"] }
  },
  "nodes": [
    { "name": "CTRL_GAIN", "parent": "GEAR_ROOT", "ui_type": "knob", "parameter_id": "gain", "rotation_axis": "Y", "rotation_sign": -1, "min_angle": -135, "max_angle": 135, "rest_angle": 0, "hit_target": "HIT_GAIN" },
    { "name": "INPUT_REGULAR", "parent": "GEAR_ROOT", "ui_type": "input", "parameter_id": "inputMode", "choice_index": 0, "hit_target": "HIT_INPUT_REGULAR" },
    { "name": "INPUT_HIGH", "parent": "GEAR_ROOT", "ui_type": "input", "parameter_id": "inputMode", "choice_index": 1, "hit_target": "HIT_INPUT_HIGH" }
  ],
  "hit_targets": [
    { "name": "HIT_GAIN", "parent": "CTRL_GAIN" },
    { "name": "HIT_INPUT_REGULAR", "parent": "INPUT_REGULAR" },
    { "name": "HIT_INPUT_HIGH", "parent": "INPUT_HIGH" }
  ],
  "camera_presets_file": "runtime_camera_presets.json",
  "expected_camera_presets": {
    "Front": { "position": [0, 0.2, 1], "target": [0, 0.2, 0], "up": [0, 1, 0], "vertical_fov_degrees": 35, "min_distance": 0.3, "max_distance": 2 },
    "Controls": { "position": [0, 0.25, 0.45], "target": [0, 0.2, 0], "up": [0, 1, 0], "vertical_fov_degrees": 35, "min_distance": 0.25, "max_distance": 1 }
  }
}
```

The manifest is validation input, not another parameter store or a glTF-standard schema. Compare each expected node/parent and metadata field against parsed GLB nodes/extras, and compare the separate preset file against `expected_camera_presets`. `camera_presets_file` identifies the sole runtime camera source; `expected_camera_presets` is an independent expected-value snapshot used only by QA, never a second production source or runtime fallback. Validate unique names, exactly one root, finite camera vectors, valid FOV/distance ranges and every referenced hit target. Include static nodes only if their identity is part of the application contract. Do not generate expected values from the same possibly broken export and call that independent validation.

`choice_index` is the exported zero-based APVTS choice index: Regular = 0, High = 1. On a jack hit, resolve its `parameter_id` and write `choice_index / (choiceCount - 1)` through that binding (for a one-choice parameter use 0). Reject noninteger/out-of-range indices. Node names identify geometry; never infer High/Regular behavior from spelling. When adding a toggle, include its expected `state_count`, `state_labels`, `state_angles`, axis and rest angle in the same manifest.

Three.js reads extras through `object.userData`. Validate finite angles, valid axis/sign, state array lengths, unique node names and resolved target names at startup. Register by metadata against the processor's supported parameter IDs; do not silently create a host parameter for every mesh.

## Dedicated hit targets

Use slightly enlarged low-poly cylinders/boxes for `HIT_BASS`, `HIT_SWITCH`, `HIT_INPUT_HIGH` and `HIT_INPUT_REGULAR`. Test close neighbors at real editor size. Export proxies deliberately, or generate them in Three.js when changing Blender is unnecessary. Keep them out of the production camera's render layers while enabling the raycaster's proxy layer; expose a debug overlay. Raycast only the explicit proxy list, never the entire detailed amp. Verify proxy transforms after every camera and control pose change.

## Export gate

Select only the export collection/objects using options supported by the installed exporter. Exclude cutters, library display copies, studio rigs and helpers without runtime roles. Preserve required semantic parent nodes and extras, UVs, normals, material regions and intentional open surfaces. Do not weld or fill all boundaries indiscriminately.

Inspect GLB structure and a fresh load for units/bounds, control count, pivots, material coverage and finite transforms. Deliver source provenance, derivative, GLB, metadata convention and camera presets. Once it loads correctly, looks acceptable at target size/zoom, has working semantic interactions and reasonable measured costs, proceed to JUCE integration. Revisit asset optimization only for measured bottlenecks.
