# Guitar Gear Material Recipes

These are starting ranges, not laws. Tune them against references and the actual lighting setup.

## Powder-coated aluminum or steel

- Metallic behavior depends on whether the coating itself is opaque paint/powder: the visible coating is generally treated as non-metallic even when the substrate is metal.
- Roughness: often around 0.30-0.60 depending on satin/matte/gloss finish.
- Add very subtle high-frequency roughness and bump variation.
- Keep orange-peel scale small relative to the enclosure.
- Edge highlights should come from real bevel geometry.

## Bare/brushed aluminum

- Metallic: 1.0.
- Roughness: often 0.20-0.45 depending on finish.
- Add directional anisotropy or fine directional normal/roughness texture for brushing.
- Keep brushing aligned to manufacturing direction.

## Chrome / nickel hardware

- Metallic: 1.0.
- Low to moderate roughness depending on polish.
- The environment and area-light reflections define the appearance.
- Add tiny roughness variation only if it is visible in close-ups.

## Black ABS / molded plastic

- Metallic: 0.0.
- Roughness: commonly 0.25-0.50 depending on finish.
- Subtle molded texture can be represented with fine bump/roughness variation.
- Avoid exaggerated subsurface or mirror-like highlights.

## Rubber feet

- Metallic: 0.0.
- Roughness: often 0.55-0.90.
- Very subtle bump can suggest molded rubber.
- Keep specular response present; rubber is not a perfectly flat black void.

## Tolex / vinyl amp covering

- Metallic: 0.0.
- Roughness: commonly 0.35-0.65.
- Use a repeatable grain normal/bump texture at measured or visually plausible scale.
- Grain should remain subordinate to cabinet seams, corners, piping, and edge construction.

## Grille cloth

Choose representation by distance:

- Far/medium shot: texture + normal/bump + opacity/transmission cues may be sufficient.
- Hero close-up: geometry or a high-quality weave material may be required.

Avoid ultra-dense physical weave geometry unless the camera needs it.

## Painted/screen-printed ink

- Usually non-metallic.
- Roughness may differ slightly from the substrate.
- Keep relief near zero unless the real printing is visibly raised.
- Use crisp masks and preserve type edges.

## LED lens

- Use transmission and an appropriate IOR for clear/tinted plastic.
- Add volume/absorption or tinted transmission only as needed.
- The emissive source can be separate from the lens for better control.
- Do not make the entire lens uniformly emissive unless the reference supports that look.

## Wood veneer / cabinet wood

- Metallic: 0.0.
- Respect real grain direction on each board or veneer face.
- Use roughness variation and subtle normal rather than deep displacement for finished wood.
- If lacquered, build the clear finish response intentionally rather than merely lowering roughness globally.

## Further guidance when needed

- [Amplifier surfaces](amplifier-surfaces.md): embossed vinyl, woven cloth, aged hardware, sockets, cups and piping.
- [Material diagnostics](material-diagnostics.md): black-level/sparkle diagnosis, visual physical-scale testing and acceptance; optional analytic fallback for existing anisotropic graphs.

## Material identity at product scale

| Part/finish | Cues to preserve | Fake-looking failure |
|---|---|---|
| Coated cast metal | Dense opaque coating, restrained specularity, fine orange-peel normal and slight highlight breakup | Perfect glossy plastic or coarse procedural stucco |
| Opaque molded knob/adjuster | Near-black pigment, subtle mold grain, weak roughness variation and restrained dielectric reflection | Brown/translucent plastic, piano lacquer, rubber or metal |
| Thin metal knob insert | Very thin cap, controlled edge reflection, fine radial/concentric machining or anisotropy when supported | Thick chrome puck or deep visible scratches |
| Plated nut/washer/bushing | Physical thickness, crisp edge bands, small roughness differences among pieces, environment-dependent reflections | One uniform silver-painted plastic finish |
| Black-oxide/phosphate fastener | Dark steel response with subdued metal highlights and a readable recessed drive | Universal black plastic, featureless black disk or mirror chrome |
| Molded rubber pad | High roughness, fine irregular non-directional normal, broad weak variation, restrained sheen | Perfectly smooth rectangle or noisy sandpaper |
| LED lens/bezel | Shallow lens, separate retaining rim, tint and internal depth appropriate to on/off state | Uniform glowing orb used to hide incorrect lens geometry |

Tune each physical finish separately; sharing should follow material identity, not color alone. Dark conversion coatings are not a universal bare-metal preset: match the photographed finish under useful reflections. Warm enclosure reflections on opaque black plastic are legitimate; do not tint the pigment brown to reproduce them. Coating and rubber microtexture should remain nearly invisible at hero size. See [graphics and decals](graphics-and-decals.md) for molded branding relief and print edges.
