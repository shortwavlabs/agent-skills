# Graphics, Labels, Decals, and Faceplates

## Choose the technique by physical behavior

### UV-mapped face graphic

Best for:

- Pedal top artwork.
- Large printed control panels.
- Complex multi-color silkscreen or illustration.

Advantages:

- Simple scene organization.
- Perfect alignment between related labels.
- Easy art revision outside Blender.

### Decal

Best for:

- Small labels.
- Certification marks.
- Serial stickers.
- Warning labels.
- Reusable logos/badges.

Keep decal offset minimal and avoid visible floating at grazing angles.

### Geometry

Best for:

- Engraved labels.
- Embossed logos.
- Raised badges.
- Deeply stamped panel marks.

Use geometry when the relief contributes real shadows or silhouette at the target shot distance.

## Image preparation

- Prefer sufficiently high-resolution source artwork.
- Keep alpha clean around text and logos.
- Use vector source outside Blender when possible, rasterizing only at adequate resolution.
- Preserve a master artwork file separate from generated render textures.

## Material response

Printed ink often has a subtly different roughness from the substrate. Avoid making all graphics pure emission or perfectly diffuse unless that is physically accurate.

## Alignment checks

Verify:

- Knob legends center around the actual shaft axis.
- Input/output labels match physical connector positions.
- Text baseline and panel alignment are consistent.
- Artwork does not cross seams or hardware unless the real product does.
- Serial and regulatory marks are not accidentally mirrored.

## Badge placement and printed markings

Preserve supplied vector artwork and proportions. Imported SVG origins and whitespace need not coincide with the visible logo center; measure transformed/evaluated artwork bounds in the intended panel plane. Treat a registration mark as part of the assembly, and state whether it participates in optical/geometric centering. Follow the user's latest placement instruction over an earlier reference interpretation.

Keep an applied badge thin enough to read as a badge rather than extruded lettering. On curved or two-plane fronts, inspect the whole underside clearance: a planar emblem can bridge a shallow bend, but must not intersect or float conspicuously. Avoid bending the logo simply to follow a minor cloth fold unless the reference supports that construction.

Printed legends and divider rules should sit effectively flush. Tiny excess offsets can become dark detached rails in a grazing close-up. Prefer ink masks or almost-zero relief appropriate to the printing method; do not turn thin lines into physical panel seams. Preserve the physical panel's notch and surround independently from the artwork.

Verify both the text string and its rendered glyphs. A correct digit 1 can still look like capital I in a selected font. Use a readable suitable face or a narrowly scoped alternate glyph when necessary, preserve alignment, and pack the actual font dependency. Do not invent illegible microtext, serial numbers or fine numeric graduations from an unclear photograph. Inspect label size beside the hardware and at final output resolution, not only enlarged in the text editor.
