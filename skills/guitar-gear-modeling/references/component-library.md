# Reusable Guitar Gear Component Library

Build reusable hardware as separate assets when practical.

## Recommended component families

### Controls

- Skirted knob.
- Davies-style pointer knob.
- Chicken-head knob.
- Knurled metal knob.
- Mini toggle switch.
- Full-size toggle switch.
- Rotary switch.
- Push button.

### Pedal hardware

- 1/4-inch audio jack exterior hardware.
- DC barrel jack.
- Common footswitch body, nut, washer, and plunger.
- LED lens/bezel.
- Rubber foot.
- Bottom-plate screw.

### Amp hardware

- Handle and mounts.
- Metal/plastic corner protector.
- Chassis screw.
- Vent grille.
- Jack plate.
- Caster/foot.
- Speaker frame/cone assembly.

## Asset strategy

- Keep each master component at real dimensions.
- Place its origin at a useful mounting or symmetry point.
- Use linked duplicates/instances for repeated copies unless unique editing is required.
- Separate material regions only when they differ physically, such as chrome nut + black switch body.
- Store a clean master away from destructive per-product edits.

## Naming examples

```text
GG_LIB_Knob_Skirted_25mm
GG_LIB_Knob_Davies_19mm
GG_LIB_Footswitch_3PDT
GG_LIB_Jack_QuarterInch
GG_LIB_LED_Bezel_5mm
GG_LIB_CornerProtector_Small
```

## Detail levels

Use three practical levels:

- **Blockout:** dimensions and silhouette only.
- **Standard:** enough detail for normal product renders.
- **Hero:** extra chamfers, threads/knurling cues, small seams, and high radial resolution for close-ups.

Do not use hero-detail components everywhere if they increase scene complexity without affecting the final image.

## Source, mount and instance contract

Choose and document a mounting convention, such as local Z outward with Z=0 at the panel face. Keep source origins at this datum rather than at the assembly's bounding-box center. Build repeated controls from one source collection or linked mesh family; correct shared defects once in that source. Product-specific labels, placement and bores belong to the product layout.

Store useful dimensions as named parameters/custom properties: shaft axis, seating plane, bore clearance, exposed projection, nut across-flats dimension, opening diameter and intended variant. Distinguish an intentional fit variant from accidental copies. Reopen the library and a product that uses it to confirm the source relationships survive saving.

Collections used as hidden source libraries may not appear as ordinary scene meshes. An instance empty's dimensions do not describe its rendered contents. Use evaluated instances for assembly bounds and ray checks; see the QA skill's evidence guidance. Excluding a source display collection must not accidentally hide the product's instances.

## Knobs

Build the silhouette first: tapered body, restrained skirt, thin rim, top bevel and shaft-centered indicator. Fine grip ribs should read as molded grip, not a necklace of separate beads. Flat or gently crowned top surfaces and curved walls may need different smoothing treatment. Separate the indicator's paint/inset from exaggerated geometry.

Judge diameter against panel height and neighboring gaps in a square-on panel image, then in the hero. Adjust the source while preserving accepted mounting centers and group spacing. Derive the required count and grouping from the brief; never hard-code the control count from another amplifier. Keep pointer orientation tied to the intended setting without rotating its surrounding printed scale.

## Toggle switches

Separate the washer, hex nut, threaded-bushing envelope, pivot/socket and angled lever. The mounting stack is concentric with the bore; the tilted lever is not expected to align with the bore along its entire length.

Construct the lever from an anchored root. For a cylinder/cone whose local axis is Z and whose origin is its midpoint, with length L, direction d (unit vector) and root p:

    center = p + d * L/2
    root_check = center - d * L/2

Orient the lever to d, place the root within the pivot/socket by a small appropriate overlap, and verify that the tip-end detail follows the same transform. Rotating a midpoint-centered lever in place and then guessing its translation is a common cause of a floating root. Verify after modifiers, from a shallow side view; matching object origins or projected silhouettes is insufficient. The visible pivot should plausibly enclose the root, without a conspicuous buried handle or open gap.

## Quarter-inch input jacks

Model these dimensions separately:

- Functional plug opening (6.35 mm class for a quarter-inch connector).
- Stem/bushing outside diameter and panel mounting bore.
- Retaining nut across flats, across corners and circular inner clearance.
- Washer outer/inner diameter and thickness.
- Collar diameter, exposed thread length and total projection from the panel.
- Recessed barrel and visible interior depth.

The nominal plug size is not the panel mounting-hole specification. Prefer a real connector specification when known. A reduced stem fitted to a locked visualization bore can be a documented approximation, never a fabrication recommendation.

A hex nut has six exterior flats but a round clearance hole. Do not generate its inner ring with only six samples and accidentally create a nested hexagonal socket. For a regular hexagon, across-corners = across-flats / cos(30°); record which size a radius calculation represents. Use enough circular samples for the hole and restrained chamfers on the flats. When connecting rings with differing topology, inspect triangulation, normals and manifoldness where a solid part is intended.

Stack a seated thin washer, retaining nut, hollow stepped bushing and recessed barrel. Add shallow visible thread cues only if the shot benefits; concentric grooves suggest threading but are not a true helix. Terminate the interior far enough behind the mouth to show depth, and add a small off-axis contact only when useful. Do not place a centered bright disk behind the hole.

If the exposed metal dominates the panel, compare a small number of isolated size variants at identical framing. Preserve the functional opening, mount centers, bores and spacing while varying only exterior retaining hardware. Judge the metal-to-opening ratio next to a neighboring control. Once accepted, freeze dimensions for later material passes; do not keep shrinking hardware to manufacture apparent progress.

## Handles, corners, lenses and casters

- **Strap handle:** use a flattened grip cross-section and restrained sag/arch, with plausible thickness and transitions into separate end brackets. Avoid a generic thick curved bar when the reference shows a strap.
- **Recessed side handle:** cut the shell behind the mounting plate. Build true cups, lip thickness and a usable grasp bridge; a dark inset plane alone will fail at an oblique view. Preserve flat rear cup regions while smoothing curved walls as appropriate. Keep screws seated and branding relief thin.
- **Corner cap:** model connected thin stamped flanges with rounded/scalloped profiles and a wrap that follows the actual corner. Sheet thickness, perimeter shape and outer radius are separate parameters. Rounded edges on a thick cube do not make a sheet-metal protector. Check mirrored instances, screw orientation and negative-scale shading.
- **Pilot lamp:** a shallow tinted dome with a bezel and internal depth reads differently from a flat red button. Keep a possible emitter behind or within the lens rather than making every surface uniformly luminous. Smaller channel indicators should remain subordinate when the reference supports that hierarchy.
- **Caster:** separate wheel/tire, axle, yoke and mounting plate only to the detail needed. Check floor contact and assembly height after instancing; do not add hidden mechanics to compensate for an unresolved silhouette or grounding defect.
