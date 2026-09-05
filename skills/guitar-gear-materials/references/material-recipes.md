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

## Black amplifier surfaces: diagnose before darkening

Judge covering, grille, molded cups and rubber as different black materials. A near-black base can still appear medium gray under broad strong fill; a perfectly black base can lose every material cue. Inspect base reflectance, dielectric specular/IOR response, roughness, bump, world strength and reflected source size separately. Do not lower global exposure to fix vinyl while correctly exposed labels and metal become underexposed. If the lighting is already accepted, use temporary diagnostic lighting without changing the delivered rig.

Bright speckling can arise from excessively steep bump, high-contrast roughness, very small bright lights or insufficient sampling of tiny features. Reduce the responsible contribution, not all texture indiscriminately. A successful correction preserves coherent grazing highlights and embossed grain at detail distance. Overcorrecting sparkle into a smooth painted surface is also a failure.

Numeric node values are not portable presets: scene units, coordinate transforms, height remapping, light geometry and color management all affect the result. A Bump node's distance is not itself a measured peak-to-valley relief after its height signal and strength are applied.

## Embossed vinyl: grain, orientation and physical scale

For pebbled covering, build irregular islands with restrained elongation, uneven spacing and mixed local orientation. A remapped cell/distance pattern with soft shoulders can be a useful base; raw fine noise or sharp cellular borders readily resemble sandpaper, stone or glitter. Compare against the actual covering type, since not every amplifier uses the same embossing.

Keep the coordinate source explicit. Generated coordinates normalize an object's bounds and can produce different grain sizes on differently sized parts. Object coordinates can still inherit object/reference transforms; unit object scale alone is not proof of equal physical density. Audit source coordinates, object and parent scale, mapping rotation, anisotropic scale, texture frequency and deformation on the actual instanced product.

Use equivalent physical patches from representative front, top, side, frame and slanted regions:

1. Choose clear patches of the same width in real units (for example, a few centimeters), avoiding handles or trim that occlude the surface.
2. Place orthographic cameras normal to each patch, with identical footprint and pixel count.
3. Use comparable local lighting incidence, source size and power; keep an ordinary studio view as a second check.
4. Compare characteristic pebble area and spacing, separating orientation/stretch from overall grain density.
5. Correct only a demonstrated mismatch and retain the approved reference surface's density. Separate wrapped sheets can retain distinct orientations.

Do not call crops equal-scale merely because they were resized into equal image boxes. A 3D anisotropic field can produce different projected pebble areas on orthogonal faces despite identical node settings.

### Conditional correction for an existing anisotropic procedural field

Prefer physically scaled UVs or a suitable local sheet mapping for new assets. If an accepted procedural graph must be retained, its local linear coordinate transform can be audited analytically.

For q = A p, a unit surface normal n expressed in p's coordinate frame, and a nonsingular constant A, the local tangent-area stretch is:

    s(n) = abs(det(A)) * length(inverse(transpose(A)) * n)

A scalar coordinate multiplier k = sqrt(s_reference / s(n)) matches the reference plane's area density on a planar patch. For A = D R (diagonal stretch after rotation), transform n through R and inverse D in that order. Keep the normal in the same coordinate frame as p, and use an unperturbed geometric normal rather than the bump output to avoid feedback. Account for non-unit transforms before interpreting p as physical length.

This matches an area-density proxy; it does not equalize both directional wavelengths, reconstruct a photographed material, or prove perceptual equivalence for every procedural texture. On curved surfaces k varies, and scaling absolute coordinates can introduce distortion or discontinuities; inspect bevels, wrap edges and rotations. A per-sheet constant or UV mapping may be better. Validate with actual equal-scale patches before accepting the mathematical result.

## Broad compression and local handling on vinyl

Keep embossing separate from slow manufacturing/handling variation. A weak field spanning centimeters to tens of centimeters can slightly reduce bump amplitude or change roughness, suggesting flattened grain without recoloring the covering. Reuse an existing broad layer before adding another noise stack. Keep baseline hue/value stable when the task asks for subtle aging; macro color variation easily becomes blotchy.

Place sparse contact masks in plausible regions: near handle mounts, selected transport corners or actual grasp/contact zones. Check that source-local coordinates follow instances and mirrored variants correctly. A mask entirely hidden under a bracket cannot prove visible improvement. Do not amplify it into a halo just to make the change obvious. Wear should follow physical use, not outline every mathematical edge.

## Woven grille: construction and sampling

Represent two crossing yarn systems with rounded thread profiles, modest width/spacing drift, occasional grouping and restrained coordinate distortion. Avoid equal-strength checkerboard intersections, coherent horizontal blinds, vertical columns and excessive periodic modulation. Adding another repeating wave can make banding worse; inspect both directions independently and together.

For a dark grille, use charcoal fibers with only the warmth supported by the brief. An aged reference does not automatically justify a brown color shift. Keep the backing/cavity dark and tune cloth coverage/transparency so speakers remain as visible or obscured as intended. Do not brighten cones merely to prove their presence.

Evaluate three scales when cloth dominates the product:

- Hero: reads as fabric without conspicuous procedural stripes or interference.
- Medium: subtle crossing yarns and nonuniformity become apparent.
- Detail: recognizable woven structure without exaggerated bumps or perfect checker intersections.

Reduced previews can hide banding that appears in the full-resolution image. Preserve the established physical weave scale where possible; adjust signal contrast, filtering, representation or sampling rather than arbitrarily stretching the texture to hide moire.

A horizontal stripe at a cabinet bend is not automatically a shader defect. Check overlapping cloth, discontinuous coordinates, flat/smooth normals, abrupt geometry and the light response. A narrow continuous bend may fix a hard normal boundary; a legitimate illumination difference should remain. See the modeling construction reference and QA diagnosis guidance.

## Well-maintained aged hardware

Use this treatment only when the requested age level supports it; factory-new, relic and heavily road-worn products need different choices. Intact vintage gear often shows age primarily in reflection clarity rather than painted dirt.

| Region | Useful restrained change | Avoid unless referenced |
|---|---|---|
| Plated corner radius/flanges | Local polish loss, faint directional microscratches, tiny warm/cool shift | Universal bright edge masks, rust, chipped plating |
| Around cap fasteners | Small roughness transition near contact/recess | Dark circular grime halos |
| Screw family | Tiny per-instance roughness differences; slightly duller slot interiors | Obvious random colors or inconsistent manufactured shape |
| Handle brackets | Contact-related reflection variation | Uniform abrasion on protected surfaces |
| Grip center | Slightly smoother from handling, relative to outer grip | Cracks or random fingerprints by default |
| Input nut/washer | Compact clean plating with weak roughness breakup | Matching the most distressed cabinet corner everywhere |
| Caster yoke/wheel | Mild plating/rubber variation | Hidden mechanical rebuilds for a material pass |

Keep the shared base material intact when unrelated parts are accepted. Use an intentionally named derivative for a materially different treatment, such as exposed caps versus cleaner jack hardware. Do not proliferate a unique material per instance. Object-level random inputs should be tested on the actual collection-instance system; their visible variation is not guaranteed by the node's name.

Align micro-scratches with plausible handling/manufacturing directions and keep their amplitude below visible carved grooves. Use local masks or meaningful material regions; do not darken every recess purely because it is concave. Metal aging still needs readable softbox reflection bands, not white plastic or uniformly rough gray metal.

## Socket interiors, molded cups and piping

**Sockets:** a recessed barrel, throat-edge reflection and one faint off-axis contact can make a mostly dark opening read as depth. Use darker inner metal with restrained spatial roughness variation; keep both copies the same manufactured geometry. Do not add a centered emitter, bright machinery or independent random geometry to each input. Check at native hero pixels as well as in a close-up.

**Molded handles:** broad weak roughness variation can be more convincing than fine noise. Keep interior cups dark with subdued satin reflections, while preserving enough gradient to show their depth. A huge silver-looking reflection may involve light placement or over-smoothed cup normals as well as roughness; inspect all three before painting a black patch.

**Piping:** warm ivory/cream, slight gloss variation and fractionally duller exposed corners can suggest age. Preserve clean long runs and the intended diameter. Do not turn intact vinyl trim brown or stained to mimic a poorly lit photograph. First check geometry if trim appears detached or disappears into a frame.

**Panel:** distinguish painted/coated metal from bare satin metal. Use very weak surface variation around a stable light-gray value; label contrast takes priority. Avoid adding dirt around every control simply because the gear is vintage.

## Material acceptance

For a refinement intended to be subtle, compare before/after at actual hero size and at useful product-detail distance under the same lighting. Reject changes that introduce hero-scale noise, change the overall black balance, or imply distress beyond the brief. If the claimed change is invisible at relevant detail distance, either diagnose why, retain the simpler baseline, or report it as a non-visible treatment rather than overstating the result.
