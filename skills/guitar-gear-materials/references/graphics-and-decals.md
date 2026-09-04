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
