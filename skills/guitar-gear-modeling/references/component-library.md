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
