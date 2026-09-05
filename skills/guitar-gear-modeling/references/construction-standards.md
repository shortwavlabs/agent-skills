# Guitar Gear Construction Standards

Use these as modeling heuristics, not universal manufacturing specifications. Prefer measured references or datasheets when available.

## Pedal enclosure

Typical modeled assembly:

- Main cast or folded enclosure.
- Removable bottom plate.
- Footswitch and mounting nut/washer.
- Potentiometer shafts and knobs.
- LED and lens/bezel.
- Audio jacks.
- DC power jack.
- Screws and rubber feet.
- Printed/painted/dec applied graphics.

Model the visible enclosure wall thickness only when it affects openings, seams, or close-up renders.

### Edge treatment

Small aluminum pedal enclosures typically need a visible but restrained bevel. Judge the bevel by highlight width in the target camera, not by a single universal number.

### Holes and hardware

Use the actual hardware outside diameter and mounting-hole dimensions when known. Keep the hole and the visible nut/washer as separate concerns: the hole size is not the same as the visible hardware diameter.

## Amplifier head or combo

Typical assembly:

- Cabinet shell.
- Front/rear panels.
- Chassis or visible control plate.
- Knobs and switches.
- Input/output jacks.
- Handle and handle mounts.
- Corner protectors.
- Feet/casters.
- Grille cloth and baffle.
- Speakers if visible.
- Piping or trim.
- Tolex/vinyl covering.
- Ventilation openings.

Avoid making the cabinet a single textured cube. Small physical offsets between trim, grille, panel, and shell create important real-world shadow lines.

## Speaker cabinets

Separate:

- Outer shell.
- Baffle.
- Speaker cones/dust caps/surrounds when visible.
- Grille cloth or metal grille.
- Handles.
- Corners.
- Feet/casters.
- Jack plate.

For a grille-cloth hero shot, actual geometry or a carefully tuned material may be required depending on camera distance. Use geometry only when the weave needs silhouette/parallax.

## Manufacturing realism

A believable product usually includes:

- Small seams between removable parts.
- Consistent fastener families.
- Slightly recessed or proud control panels where appropriate.
- Correct washer/nut stacking.
- Plausible panel thickness.
- Enough clearance around knobs and switches to be operable.

Do not add random greebles. Every visible detail should have a plausible function or manufacturing reason.

## Reference measurements and user-directed layout

Separate three kinds of evidence: confirmed dimensions, proportions inferred from photographs, and explicit user art direction. A later request to center a badge overrides an earlier photographic offset; do not reintroduce the rejected placement during a subsequent fidelity pass. Keep a small list of accepted constraints and changed requirements.

For an oblique panel photograph, rectify the panel plane using its four corners before comparing spacing. Measure washer/bushing centers on the panel, not projecting knob caps, toggle tips, lens highlights, or text baselines. Perspective correction cannot recover exact dimensions from an uncalibrated image. Register estimates to already accepted control datums and report uncertainty rather than claiming submillimeter accuracy.

Treat these as independent constraints:

- Panel center relative to the head.
- Left and right content margins within the panel.
- Control-group spacing and individual shaft positions.
- Panel opening/notch, surround, trim endpoints, bores, labels and dividers.

For example, with panel width W centered at X=0, preserving the left content margin while adding Δ to the right margin can be achieved by increasing W by Δ and shifting the entire content group left by Δ/2. Move dependent bores, legends and dividers with it; expand the notch symmetrically. This preserves internal spacing, not absolute control coordinates. If those coordinates are also locked, this solution is unavailable: resolve the incompatible constraints rather than silently changing one. Do not add equal blank margins when the user explicitly accepts the original left margin.

Center a badge by its visible evaluated artwork bounds in the grille's local plane, not by the imported object's origin or the photograph's image center. Define whether the registration mark belongs to the centering bounds; move it with the badge either way. Verify horizontal and vertical placement in a square-on view. On a bent grille, use the intended front-projected opening or mounting-plane convention and record it; surface arc-length and projected centers are not interchangeable.

## Mounting datums and actual holes

For every control, define a mount frame: origin at the panel seating surface, local outward normal, and shaft/bore axis. Drive the panel cutter, washer, retaining nut, bushing, body and associated markings from that frame. Keep label baselines separate from mechanical centers: adjacent pilot, knob and jack axes need not all share one height.

A dark material disk is not an open socket, and a washer can conceal an uncut panel. Inspect the evaluated Boolean result through the full panel thickness. Use a central ray and, when clearance matters, offset rays around the required radius; a single clear center ray does not establish the usable bore diameter. Check rear geometry too: a shell, fascia or baffle behind the panel can still block the opening.

Changing a mount position and repairing a faulty source part are separate operations. Translating an entire toggle assembly cannot fix its detached lever. Rotating or moving a component should carry its cutter and decorations without leaving old holes or displaced labels behind.

## Two-plane slant cabinets

A slant cabinet is not necessarily a tilted rectangular box. Read the side silhouette for an upright lower region, an upper setback and a hinge height. Express the rake as atan(setback / vertical rise), with the selected measurements and their uncertainty. Preserve the level rear, top support and floor datum when that matches the construction.

Propagate the profile coherently:

- Shell and front frame follow the same side boundary and breakpoint.
- Rotate an upper baffle rigidly about the hinge so circular speaker apertures stay circular. Avoid indiscriminate shear of the baffle and its holes.
- Upper speakers use the same hinge transform; check cone-to-grille clearance normal to the new plane and clearance to the rear wall.
- Cloth follows the frame, with its own physically plausible bending behavior.
- Insert piping control points at the transition; check seating, thickness and continuous joins.
- Change corner-cap variants only where the actual mating angle changes. Preserve the regular source elsewhere.
- Keep a rigid badge planar unless the reference supports deformation. A thin badge spanning a shallow bend can use an angle-bisector mount and small standoff; verify all of its surface clears the cloth. This is an approximation, not a universal mounting design.

A hard shading band exactly at a cloth hinge can come from flat faces and an abrupt normal change. If inspection confirms that cause, use a narrow tangent-continuous transition with adequate subdivisions and appropriate front/back smoothing. Keep the upper/lower planes, outer silhouette and structural baffle fixed. Do not smooth the whole cabinet or paint out the band. A broad tonal difference between differently oriented cloth planes can remain correct.

## Head-to-cabinet support

After changing cabinet depth or slant, recompute the usable top footprint. Centering a head over the cabinet's maximum depth can leave it overhanging the narrower top.

Measure the top's front/rear boundaries, bevel inset and relevant protrusions, then check each foot's contact patch against the actual support surface. Where appropriate, center the head fore/aft on that usable footprint, translating the assembled instance so its internal parts remain registered. Keep the head level and preserve its feet-to-top contact height. Distinguish enclosure fit from hardware-inclusive fit; a projecting control tip is not a supporting foot.

Verify both a true side view and the assembled hero. Check caster wheel contact, head feet, front/rear clearances and handle/cap interference. A convincing front view cannot prove support in depth.

## Wrapped shells, trim and edge shading

Continuous vinyl covering can hide board joints; do not expose every internal panel seam as a black line through the wrap. Preserve genuine removable-panel boundaries. Inspect trim depth: piping must sit in its intended groove or edge, neither buried inside the frame nor floating ahead of it.

Boolean and bevel order affects both outer rounding and opening edges. Inspect the evaluated result after cuts. Tiny nearby edges and overlap-clamping can suppress a large outer bevel; separate outer-shell rounding from hole-edge treatment when needed. There is no universally correct modifier order for every assembly. Apply only the necessary modifier on the intended object after a checkpoint, rather than globally flattening the stack.
