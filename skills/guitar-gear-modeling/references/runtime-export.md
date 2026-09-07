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

Three.js reads extras through `object.userData`. Validate finite angles, valid axis/sign, state array lengths, unique node names and resolved target names at startup. Register by metadata against the processor's supported parameter IDs; do not silently create a host parameter for every mesh.

## Dedicated hit targets

Use slightly enlarged low-poly cylinders/boxes for `HIT_BASS`, `HIT_SWITCH`, `HIT_INPUT_HIGH` and `HIT_INPUT_REGULAR`. Test close neighbors at real editor size. Export proxies deliberately, or generate them in Three.js when changing Blender is unnecessary. Keep them out of the production camera's render layers while enabling the raycaster's proxy layer; expose a debug overlay. Raycast only the explicit proxy list, never the entire detailed amp. Verify proxy transforms after every camera and control pose change.

## Export gate

Select only the export collection/objects using options supported by the installed exporter. Exclude cutters, library display copies, studio rigs and helpers without runtime roles. Preserve required semantic parent nodes and extras, UVs, normals, material regions and intentional open surfaces. Do not weld or fill all boundaries indiscriminately.

Inspect GLB structure and a fresh load for units/bounds, control count, pivots, material coverage and finite transforms. Deliver source provenance, derivative, GLB, metadata convention and camera presets. Once it loads correctly, looks acceptable at target size/zoom, has working semantic interactions and reasonable measured costs, proceed to JUCE integration. Revisit asset optimization only for measured bottlenecks.
