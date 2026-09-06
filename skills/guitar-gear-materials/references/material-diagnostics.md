# Material Diagnostics

Read when appearance or physical texture scale is uncertain. Begin with rendered evidence and the visual patch test; the analytic appendix is optional and is not a routine material-authoring step.

## Black amplifier surfaces: diagnose before darkening

Judge covering, grille, molded cups and rubber as different black materials. A near-black base can still appear medium gray under broad strong fill; a perfectly black base can lose every material cue. Inspect base reflectance, dielectric specular/IOR response, roughness, bump, world strength and reflected source size separately. Do not lower global exposure to fix vinyl while correctly exposed labels and metal become underexposed. If the lighting is already accepted, use temporary diagnostic lighting without changing the delivered rig.

Bright speckling can arise from excessively steep bump, high-contrast roughness, very small bright lights or insufficient sampling of tiny features. Reduce the responsible contribution, not all texture indiscriminately. A successful correction preserves coherent grazing highlights and embossed grain at detail distance. Overcorrecting sparkle into a smooth painted surface is also a failure.

Numeric node values are not portable presets: scene units, coordinate transforms, height remapping, light geometry and color management all affect the result. A Bump node's distance is not itself a measured peak-to-valley relief after its height signal and strength are applied.


## Visual physical-scale test

Keep the coordinate source explicit. Generated coordinates normalize an object's bounds and can produce different grain sizes on differently sized parts. Object coordinates can still inherit object/reference transforms; unit object scale alone is not proof of equal physical density. Audit source coordinates, object and parent scale, mapping rotation, anisotropic scale, texture frequency and deformation on the actual instanced product.

Use equivalent physical patches from representative front, top, side, frame and slanted regions:

1. Choose clear patches of the same width in real units (for example, a few centimeters), avoiding handles or trim that occlude the surface.
2. Place orthographic cameras normal to each patch, with identical footprint and pixel count.
3. Use comparable local lighting incidence, source size and power; keep an ordinary studio view as a second check.
4. Compare characteristic pebble area and spacing, separating orientation/stretch from overall grain density.
5. Correct only a demonstrated mismatch and retain the approved reference surface's density. Separate wrapped sheets can retain distinct orientations.

Do not call crops equal-scale merely because they were resized into equal image boxes. A 3D anisotropic field can produce different projected pebble areas on orthogonal faces despite identical node settings.

## Material acceptance

For a refinement intended to be subtle, compare before/after at actual hero size and at useful product-detail distance under the same lighting. Reject changes that introduce hero-scale noise, change the overall black balance, or imply distress beyond the brief. If the claimed change is invisible at relevant detail distance, either diagnose why, retain the simpler baseline, or report it as a non-visible treatment rather than overstating the result.

## Advanced / optional: anisotropic area correction

Use this fallback only after equal-world-size patches demonstrate a mismatch, and when retaining an existing anisotropic procedural graph genuinely requires an analytic correction. Skip it if the visual test passes or ordinary physical UV/sheet mapping resolves the issue. Do not add this normal-driven correction preemptively to every covering shader.

Prefer physically scaled UVs or a suitable local sheet mapping for new assets. If an accepted procedural graph must be retained, its local linear coordinate transform can be audited analytically.

For q = A p, a unit surface normal n expressed in p's coordinate frame, and a nonsingular constant A, the local tangent-area stretch is:

    s(n) = abs(det(A)) * length(inverse(transpose(A)) * n)

A scalar coordinate multiplier k = sqrt(s_reference / s(n)) matches the reference plane's area density on a planar patch. For A = D R (diagonal stretch after rotation), transform n through R and inverse D in that order. Keep the normal in the same coordinate frame as p, and use an unperturbed geometric normal rather than the bump output to avoid feedback. Account for non-unit transforms before interpreting p as physical length.

This matches an area-density proxy; it does not equalize both directional wavelengths, reconstruct a photographed material, or prove perceptual equivalence for every procedural texture. On curved surfaces k varies, and scaling absolute coordinates can introduce distortion or discontinuities; inspect bevels, wrap edges and rotations. A per-sheet constant or UV mapping may be better. Validate with actual equal-scale patches before accepting the mathematical result.

## Saturated coatings and isolated material candidates

Reference photographs are not absolute color measurements: white balance, exposure, camera profile, compression and surrounding colors can shift apparent pigment. Separate base pigment, coating roughness, specular response, reflected studio sources and color-management response before changing a saturated finish. A washed-out, salmon or pastel-looking top can be caused by a broad reflection; the same material can legitimately look darker on a side wall. Do not force equal face brightness or compensate for lighting by arbitrarily changing pigment. Compare references under the frozen accepted rig; temporary diagnostic lighting is evidence, not a new delivered look.

For an uncertain material response, keep geometry, pigment, exposure and rig fixed. A useful study is A = current material, B = reduced specular response, C = the same reduction plus finer micro-normal. This is a sequential material-family study: A/B isolates specularity and B/C isolates micro-normal; A/C alone cannot attribute the improvement to one parameter. Record the changed values and choose by reference fidelity, not polish. Use the shared QA decision procedure if the source of the mismatch is still uncertain.
