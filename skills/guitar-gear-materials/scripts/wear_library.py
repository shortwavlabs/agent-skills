"""Procedural wear for guitar-gear materials (Blender): GG_WEAR_* node groups, worn derivatives, JSON wear profiles.

Ported from the validated Yellow Punch wear library (case study). The technique:
  * reusable node groups build masks in Object coordinates x 1000, so feature sizes are millimetres on every part:
    GG_WEAR_Scratches, GG_WEAR_Blotch, GG_WEAR_CreviceOxide, GG_WEAR_ConvexEdge, plus data-driven chips
    (chips_group) and history strokes (strokes_group) in object-local mm;
  * a base material is copied into `<base>__WORN` (or another `<base>__<suffix>`); only the Principled BSDF's Base
    Color, Roughness, Metallic and Normal are re-routed through a "GG_WEAR" frame, so outside every mask the result
    equals the base;
  * per-part amounts are object custom properties gg_wear_<key> and gg_wear_seed (gg_lip_z / gg_lip_r for openings),
    read by Attribute(Object) nodes, so they stay editable after the build; 0 switches a term off;
  * a JSON profile sets each amount as levels[family][key][A|B|C] x the object's mult (mult_level overrides mult;
    chips / chipsize are never multiplied). See examples/wear_profile.example.json.

Builders: metal_wear (plated / machined / chrome hardware), plastic_wear (moulded knobs), paint_wear (painted or
powder-coated boxes; the source's enclosure layout -- box size, label rectangles, footswitch, jacks, edge tints -- is
now spec parameters). Left out on purpose: insert_wear, bottom_wear, rubber_wear and dc_wear, which are part-specific
variants of the same terms (knob top, bottom plate, feet, DC jack) built around one product's geometry.

Intentional differences from the source: frame name/label ("GG_WEAR", "WEAR - <label>"); zones are data
(["z", from, to] / ["disc", cx, cy, from, to] terms) as well as callables; paint_wear accepts an unlinked Normal,
missing chips / strokes / footswitch / jacks / labels, and keeps a non-zero base Metallic outside chips (the source
wrote the chip mask over it); paint edge / rim / stroke tints default to neutral greys (the source's warm tints suited
one yellow coat); build_groups reuses existing GG_WEAR_* groups and _group refuses to delete a group still in use.

  blender --background in.blend --python wear_library.py -- apply --profile p.json [--level B] [--save out.blend]
  python3 wear_library.py --self-test
  blender --background --factory-startup --python wear_library.py -- --blender-test

apply never writes over the open file and saves nothing without --save. Inside Blender it is also a module.
"""

import argparse
import contextlib
import copy
import io
import json
import math
import os
import sys
import traceback
from array import array
from pathlib import Path

try:
    import bpy
except ImportError:  # plain Python: profile resolution, validation, CLI parsing and --self-test only
    bpy = None

MM = 0.001
LEVELS = "ABC"
FRAME = "GG_WEAR"
JSON_PREFIX = "GG_WEAR_JSON="
EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "wear_profile.example.json"
V, F = "NodeSocketVector", "NodeSocketFloat"
GROUPS = {"scratch": "GG_WEAR_Scratches", "blotch": "GG_WEAR_Blotch", "crevice": "GG_WEAR_CreviceOxide", "edge": "GG_WEAR_ConvexEdge"}
GROUP_INPUTS = {
    "GG_WEAR_Scratches": [("Vector", V, None), ("Length", F, 0.003), ("Feature", F, 0.00025), ("Width", F, 0.03),
                          ("Density", F, 0.5), ("Angle", F, 0.0), ("Spread", F, 0.5), ("Seed", F, 0.0)],
    "GG_WEAR_Blotch": [("Vector", V, None), ("Size", F, 0.002), ("Seed", F, 0.0), ("Threshold", F, 0.55), ("Softness", F, 0.12)],
    "GG_WEAR_CreviceOxide": [("Vector", V, None), ("Distance", F, 0.0004), ("Speck", F, 0.00015), ("Density", F, 0.5), ("Seed", F, 0.0)],
    "GG_WEAR_ConvexEdge": [("Radius", F, 0.00015), ("Low", F, 0.01), ("High", F, 0.08)],
}
# gg_wear_<key> amounts each builder reads (plus gg_wear_seed; metal also gg_lip_z / gg_lip_r)
BUILDER_KEYS = {
    "metal": {"scratch", "polish", "tarnish", "oxide", "edge", "lip", "lipwide", "liplong", "wrench"},
    "plastic": {"edge", "polish", "contact"},
    "paint": {"edge", "lower", "scuff", "jackrub", "jackasym", "polish", "sides", "abrasion", "chips", "chipsize", "strokes"},
}
UNSCALED = {"chips", "chipsize"}
SPEC_SCHEMA = {
    "metal": {"label": "str", "scratches": "scratches", "zone": "zone", "polish_zone": "zone", "dull": "num", "dull_r": "num",
              "edge_r": "num", "crevice": "num", "speck": "num", "tarnish_size": "num", "tarnish_col": "vec4",
              "tarnish_mix": "num", "haze": "num", "scratch_r": "num", "bump": "num", "lip": "bool", "lip_wide": "bool",
              "lip_scratch": "bool", "lip_long": "bool", "wrench": "vec2"},
    "plastic": {"label": "str", "grip_z": "vec2", "edge_r": "num", "contact": "bool", "contact_col": "vec4"},
    "paint": {"label": "str", "half": "vec3", "edge_r": "num", "corner": "vec2", "front": "vec3", "side_z": "vec2",
              "lower_z": "vec2", "labels": "vec4[]", "footswitch": "vec2", "shoe_r": "vec4", "shoe_ymin": "num",
              "jacks": "vec2[]", "jack_r": "vec4", "substrate": "vec4", "edge_col": "vec4", "rim_col": "vec4",
              "stroke_col": "vec4", "lower": "bool", "sides": "bool", "jack_asym": "bool", "chips": "chips", "strokes": "strokes"},
}
REQUIRED = {"paint": ("half",)}
SCRATCH_KEYS = {"length": True, "feature": True, "width": True, "density": True, "angle": False, "spread": False}
STROKE_KEYS = {"a", "b", "w", "s", "kind", "deep", "gap", "doc"}


class ProfileError(ValueError):
    """A wear profile (or the file it is applied to) is invalid; the message lists every problem found."""


# ------------------------------------------------------------------------------------------- profile (pure Python)
def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _vec(v, n):
    return isinstance(v, (list, tuple)) and len(v) == n and all(_num(x) for x in v)


def _zone_ok(t):
    if not isinstance(t, (list, tuple)) or not t:
        return False
    return (t[0] in ("x", "y", "z", "r") and _vec(t[1:], 2)) or (t[0] == "disc" and _vec(t[1:], 4))


def _scratch_ok(s):
    return (isinstance(s, dict) and set(s) <= set(SCRATCH_KEYS) | {"zoned"} and all(k in s for k, req in SCRATCH_KEYS.items() if req)
            and all(_num(v) for k, v in s.items() if k != "zoned") and isinstance(s.get("zoned", True), bool))


def _stroke_ok(s):
    return (isinstance(s, dict) and set(s) <= STROKE_KEYS and _vec(s.get("a"), 3) and _vec(s.get("b"), 3)
            and math.dist(s["a"], s["b"]) > 0 and _num(s.get("w")) and s["w"] > 0 and _num(s.get("s"))
            and s.get("kind", "scratch") in ("scratch", "rub") and _num(s.get("deep", 0)) and 0 <= s.get("deep", 0) <= 1
            and _num(s.get("gap", 3.0)) and s.get("gap", 3.0) > 0)


def _spec_error(kind, v):
    """None when v matches the schema kind, else what was expected."""
    if kind == "num":
        return None if _num(v) else "a finite number"
    if kind == "bool":
        return None if isinstance(v, bool) else "true or false"
    if kind == "str":
        return None if isinstance(v, str) else "a string"
    if kind.startswith("vec"):
        n = int(kind[3])
        if kind.endswith("[]"):
            return None if isinstance(v, list) and all(_vec(x, n) for x in v) else f"a list of {n}-number lists"
        return None if _vec(v, n) else f"a list of {n} numbers"
    if kind == "zone":
        return None if isinstance(v, list) and all(_zone_ok(t) for t in v) else \
            'a list of ["x"|"y"|"z"|"r", from, to] or ["disc", cx, cy, from, to] terms (mm)'
    if kind == "scratches":
        return None if isinstance(v, list) and all(_scratch_ok(s) for s in v) else \
            "a list of {length, feature, width, density[, angle, spread, zoned]} (mm, degrees)"
    if kind == "chips":
        return None if isinstance(v, list) and all(isinstance(c, list) and len(c) == 5 and _vec(c[:4], 4) and c[3] > 0
                                                   and c[4] in ("x", "y", "z") for c in v) else \
            'a list of [x, y, z, radius, "x"|"y"|"z"] (object-local mm, radius > 0)'
    if kind == "strokes":
        return None if isinstance(v, list) and all(_stroke_ok(s) for s in v) else \
            'a list of {a: [x,y,z], b: [x,y,z] (a != b), w > 0, s[, kind: "scratch"|"rub", deep: 0..1, gap > 0]}'
    raise KeyError(kind)


def _unknown(d, allowed, where, errors):
    for k in sorted(set(d) - set(allowed) - {"_doc"}):
        errors.append(f"{where}.{k}: unknown key")


def resolve_profile(profile, level=None):
    """Validate a wear profile and resolve it at one level (A/B/C).

    Returns {"level", "derivatives": {name: {base, builder, spec}}, "objects": {name: {derivative, base, props}}},
    where props maps gg_wear_<key> = round(levels[family][key][level] * mult, 4) (chips / chipsize unscaled),
    gg_wear_seed and, when given, gg_lip_z / gg_lip_r. Raises ProfileError listing every problem.
    """
    if not isinstance(profile, dict):
        raise ProfileError("profile: must be a JSON object")
    errors = []
    _unknown(profile, ("level", "levels", "derivatives", "objects"), "profile", errors)
    level = level if level is not None else profile.get("level", "B")
    if level not in tuple(LEVELS):
        errors.append(f"level: {level!r} must be one of A, B, C")
    li = LEVELS.index(level) if level in tuple(LEVELS) else 0
    sections = {k: profile.get(k) for k in ("levels", "derivatives", "objects")}
    for k, v in sections.items():
        if not isinstance(v, dict) or not v:
            errors.append(f"{k}: must be a non-empty object")
    if errors:
        raise ProfileError("\n".join(errors))
    levels, derivs, objs = sections["levels"], sections["derivatives"], sections["objects"]
    for fam, table in levels.items():
        if not isinstance(table, dict) or not table:
            errors.append(f"levels.{fam}: must be a non-empty object of key: [A, B, C]")
            continue
        for k, v in table.items():
            if k != "_doc" and not _vec(v, 3):
                errors.append(f"levels.{fam}.{k}: must be [A, B, C] finite numbers")
    good = {}
    for name, d in derivs.items():
        where = f"derivatives.{name}"
        if not isinstance(d, dict):
            errors.append(f"{where}: must be an object")
            continue
        _unknown(d, ("base", "builder", "spec"), where, errors)
        builder, base, spec = d.get("builder"), d.get("base"), d.get("spec", {})
        known = isinstance(builder, str) and builder in SPEC_SCHEMA
        n0 = len(errors)
        if not known:
            errors.append(f"{where}.builder: {builder!r} must be one of {', '.join(SPEC_SCHEMA)}")
        if not isinstance(base, str) or not base:
            errors.append(f"{where}.base: the base material name is required")
        elif not name.startswith(base + "__") or name == base + "__":
            errors.append(f"{where}: a derivative is named <base>__<suffix> (e.g. {base}__WORN)")
        if not isinstance(spec, dict):
            errors.append(f"{where}.spec: must be an object")
        elif known:
            schema = SPEC_SCHEMA[builder]
            for k, v in spec.items():
                why = _spec_error(schema[k], v) if k in schema else None
                if k not in schema and k != "_doc":
                    errors.append(f"{where}.spec.{k}: unknown key for the {builder} builder")
                elif why:
                    errors.append(f"{where}.spec.{k}: expected {why}")
            errors.extend(f"{where}.spec.{k}: required by the {builder} builder" for k in REQUIRED.get(builder, ()) if k not in spec)
        if len(errors) == n0:
            good[name] = {"base": base, "builder": builder, "spec": spec}
    out = {}
    for name, o in objs.items():
        where = f"objects.{name}"
        if not isinstance(o, dict):
            errors.append(f"{where}: must be an object")
            continue
        n0 = len(errors)
        _unknown(o, ("family", "derivative", "mult", "mult_level", "seed", "lip_z", "lip_r"), where, errors)
        fam, der = o.get("family"), o.get("derivative")
        if not isinstance(fam, str) or fam not in levels:
            errors.append(f"{where}.family: {fam!r} is not in levels")
        if not isinstance(der, str) or der not in derivs:
            errors.append(f"{where}.derivative: {der!r} is not in derivatives")
        if not _num(o.get("seed")):
            errors.append(f"{where}.seed: a number is required (use a distinct seed per part)")
        if "mult" in o and not _num(o["mult"]):
            errors.append(f"{where}.mult: must be a finite number")
        if "mult_level" in o and not _vec(o["mult_level"], 3):
            errors.append(f"{where}.mult_level: must be [A, B, C] finite numbers")
        if ("lip_z" in o) != ("lip_r" in o) or not all(_num(o[k]) for k in ("lip_z", "lip_r") if k in o):
            errors.append(f"{where}: lip_z and lip_r (mm) go together and must be numbers")
        if len(errors) > n0 or der not in good:
            continue
        builder = good[der]["builder"]
        unread = sorted(k for k in levels[fam] if k != "_doc" and k not in BUILDER_KEYS[builder])
        if unread:
            errors.append(f"{where}: family {fam!r} sets {unread}, which the {builder} builder never reads")
            continue
        mult = o["mult_level"][li] if "mult_level" in o else o.get("mult", 1.0)
        props = {f"gg_wear_{k}": float(v[li]) if k in UNSCALED else round(v[li] * mult, 4)
                 for k, v in levels[fam].items() if k != "_doc"}
        props["gg_wear_seed"] = float(o["seed"])
        if "lip_z" in o:
            props["gg_lip_z"], props["gg_lip_r"] = float(o["lip_z"]), float(o["lip_r"])
        out[name] = {"derivative": der, "base": good[der]["base"], "props": props}
    if errors:
        raise ProfileError("\n".join(errors))
    return {"level": level, "derivatives": good, "objects": out}


def load_profile(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise ProfileError(f"{path}: {exc}") from exc


def parse_args(argv):
    p = argparse.ArgumentParser(prog="wear_library.py", description="Apply a GG_WEAR_* wear profile to the open .blend file.")
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("apply", help="assign gg_wear_* properties and build worn derivatives")
    a.add_argument("--profile", required=True, help="wear profile JSON")
    a.add_argument("--level", choices=list(LEVELS), help="wear level (default: the profile's 'level', else B)")
    a.add_argument("--save", help="write the result to this new .blend (never the input); without it nothing is saved")
    return p.parse_args(argv)


def save_target(save, current):
    """Absolute output path for --save; refuses the open file itself and non-.blend names."""
    out = os.path.abspath(save)
    if not out.endswith(".blend"):
        raise ProfileError(f"--save {save!r}: the output must be a .blend file")
    if current and os.path.realpath(out) == os.path.realpath(current):
        raise ProfileError(f"--save {save!r} is the input file; write to a new path")
    return out


def script_args(argv, blender=bpy is not None):
    """Arguments meant for this script: those after '--' (none under Blender without '--'), else argv[1:]."""
    return argv[argv.index("--") + 1:] if "--" in argv else ([] if blender else argv[1:])


# ------------------------------------------------------------------------------------------- node building (Blender)
class B:
    """Tiny node-building helper bound to one node tree (and an optional frame)."""

    def __init__(self, nt, frame=None, x0=-2400, y0=900):
        self.nt, self.frame, self.x, self.y, self.x0, self._attr = nt, frame, x0, y0, x0, {}

    def n(self, t, **props):
        node = self.nt.nodes.new(t)
        node.location = (self.x, self.y)
        self.y -= 170
        if self.y < -2600:
            self.y, self.x = 900, self.x + 220
        if self.frame is not None:
            node.parent = self.frame
        for k, v in props.items():
            setattr(node, k, v)
        return node

    def put(self, sock, v):
        if isinstance(v, bpy.types.NodeSocket):
            self.nt.links.new(v, sock)
        elif v is not None:
            sock.default_value = v

    def math(self, op, a, b=0.0, clamp=False):
        m = self.n("ShaderNodeMath", operation=op, use_clamp=clamp)
        self.put(m.inputs[0], a)
        self.put(m.inputs[1], b)
        return m.outputs[0]

    def add(self, a, b): return self.math("ADD", a, b)
    def mul(self, a, b, clamp=False): return self.math("MULTIPLY", a, b, clamp)
    def sub(self, a, b): return self.math("SUBTRACT", a, b)
    def mx(self, a, b): return self.math("MAXIMUM", a, b)
    def mn(self, a, b): return self.math("MINIMUM", a, b)
    def lerp(self, f, a, b): return self.add(a, self.mul(f, self.sub(b, a)))   # a + f (b - a)

    def mr(self, v, a, b, c=0.0, d=1.0):
        m = self.n("ShaderNodeMapRange", data_type="FLOAT", clamp=True)
        for i, x in enumerate((v, a, b, c, d)):
            self.put(m.inputs[i], x)
        return m.outputs[0]

    def vm(self, op, a, b=None, c=None, scale=None):
        m = self.n("ShaderNodeVectorMath", operation=op)
        self.put(m.inputs[0], a)
        for i, x in ((1, b), (2, c), (3, scale)):
            if x is not None:
                self.put(m.inputs[i], x)
        return m.outputs[1] if op in ("LENGTH", "DOT_PRODUCT", "DISTANCE") else m.outputs[0]

    def xyz(self, v):
        m = self.n("ShaderNodeSeparateXYZ")
        self.put(m.inputs[0], v)
        return m.outputs[0], m.outputs[1], m.outputs[2]

    def comb(self, x, y, z):
        m = self.n("ShaderNodeCombineXYZ")
        for i, v in enumerate((x, y, z)):
            self.put(m.inputs[i], v)
        return m.outputs[0]

    def mixc(self, f, a, b):
        m = self.n("ShaderNodeMix", data_type="RGBA", blend_type="MIX", clamp_factor=True)
        self.put(m.inputs["Factor"], f)
        ins = [i for i in m.inputs if i.type == "RGBA"]
        self.put(ins[0], a)
        self.put(ins[1], b)
        return [o for o in m.outputs if o.type == "RGBA"][0]

    def noise(self, vec, detail=0.0, rough=0.5):
        m = self.n("ShaderNodeTexNoise", noise_dimensions="3D")
        self.put(m.inputs["Vector"], vec)
        m.inputs["Scale"].default_value, m.inputs["Detail"].default_value, m.inputs["Roughness"].default_value = 1.0, detail, rough
        return m.outputs["Fac"]

    def attr(self, name):
        if name not in self._attr:
            self._attr[name] = self.n("ShaderNodeAttribute", attribute_type="OBJECT", attribute_name=name).outputs["Fac"]
        return self._attr[name]

    def group(self, ng, **ins):
        g = self.n("ShaderNodeGroup")
        g.node_tree = ng
        for k, v in ins.items():
            self.put(g.inputs[k.replace("_", " ")], v)
        return g.outputs[0]


def _group(name, inputs, outputs):
    """New shader group; an unused group of the same name is replaced, one still in use is never deleted."""
    old = bpy.data.node_groups.get(name)
    if old is not None:
        if old.users:
            raise RuntimeError(f"node group {name} exists and has {old.users} user(s); reuse it or rename it first")
        bpy.data.node_groups.remove(old)
    ng = bpy.data.node_groups.new(name, "ShaderNodeTree")
    for n, t, d in inputs:
        sk = ng.interface.new_socket(n, in_out="INPUT", socket_type=t)
        if d is not None:
            sk.default_value = d
    for n in outputs:
        ng.interface.new_socket(n, in_out="OUTPUT", socket_type=F)
    b = B(ng, x0=-1800)
    gi = b.n("NodeGroupInput")
    go = ng.nodes.new("NodeGroupOutput")
    go.location = (400, 0)
    return ng, b, gi.outputs, go.inputs


def _scratches():
    """Four rotated families of long thin contour lines of stretched noise, filtered by direction, broken into segments.
    Length / Feature in metres; Width = line half-width as a fraction of the noise swing; Density 0..1."""
    ng, b, i, o = _group("GG_WEAR_Scratches", GROUP_INPUTS["GG_WEAR_Scratches"], ["Mask"])
    acc = None
    for k, (am, lm, off) in enumerate(((-1.0, 1.0, (3.1, 7.7, 1.3)), (-0.35, 0.6, (11.3, 2.9, 5.5)),
                                       (0.3, 1.4, (6.7, 13.1, 9.2)), (0.95, 0.8, (2.2, 5.9, 12.4)))):
        ang = b.add(b.add(i["Angle"], b.mul(i["Spread"], am)), b.math("SINE", b.mul(i["Seed"], 1.7 * (k + 1))))   # seed-jittered
        rot = b.n("ShaderNodeVectorRotate", rotation_type="Z_AXIS")
        b.put(rot.inputs["Vector"], i["Vector"])
        b.put(rot.inputs["Angle"], ang)
        L = b.mul(i["Length"], lm)
        sc = b.comb(b.math("DIVIDE", 1.0, L), b.math("DIVIDE", 1.0, i["Feature"]), b.math("DIVIDE", 1.0, i["Feature"]))
        so = b.comb(b.add(off[0], b.mul(i["Seed"], 3.7)), off[1], b.add(off[2], b.mul(i["Seed"], 1.9)))
        q = b.vm("MULTIPLY_ADD", rot.outputs[0], sc, so)
        n1 = b.noise(q, detail=0.0)
        line = b.mr(b.math("ABSOLUTE", b.sub(n1, 0.5)), 0.0, i["Width"], 1.0, 0.0)
        # keep only contour stretches running along the scratch axis (drops the short perpendicular loop ends)
        gx = b.math("ABSOLUTE", b.sub(b.noise(b.vm("ADD", q, (0.2, 0.0, 0.0)), detail=0.0), n1))
        gy = b.math("ABSOLUTE", b.sub(b.noise(b.vm("ADD", q, (0.0, 0.2, 0.0)), detail=0.0), n1))
        line = b.mul(line, b.mr(b.math("DIVIDE", gy, b.add(b.add(gx, gy), 0.0001)), 0.72, 0.9))
        sc2 = b.comb(b.math("DIVIDE", 1.0, b.mul(L, 1.3)), b.math("DIVIDE", 1.0, b.mul(i["Length"], 0.45)),
                     b.math("DIVIDE", 1.0, b.mul(i["Length"], 0.45)))
        n2 = b.noise(b.vm("MULTIPLY_ADD", rot.outputs[0], sc2, b.comb(off[2], b.add(off[0], i["Seed"]), off[1])), detail=1.0)
        t0 = b.sub(0.75, b.mul(i["Density"], 0.25))
        m = b.mul(line, b.mr(n2, t0, b.add(t0, 0.05)))
        acc = m if acc is None else b.mx(acc, m)
    ng.links.new(acc, o["Mask"])
    return ng


def _blotch():
    """Broad soft patches (tarnish, dulling, polish breakup); Size in metres."""
    ng, b, i, o = _group("GG_WEAR_Blotch", GROUP_INPUTS["GG_WEAR_Blotch"], ["Mask"])
    v = b.vm("MULTIPLY_ADD", i["Vector"], b.comb(*(b.math("DIVIDE", 1.0, i["Size"]),) * 3),
             b.comb(b.mul(i["Seed"], 1.7), b.mul(i["Seed"], 2.3), b.mul(i["Seed"], 3.1)))
    n = b.noise(v, detail=3.0, rough=0.55)
    ng.links.new(b.mr(n, i["Threshold"], b.add(i["Threshold"], i["Softness"])), o["Mask"])
    return ng


def _crevice():
    """Sparse dark specks only where the surface is locally occluded (thread roots, nut / washer creases)."""
    ng, b, i, o = _group("GG_WEAR_CreviceOxide", GROUP_INPUTS["GG_WEAR_CreviceOxide"], ["Mask"])
    ao = b.n("ShaderNodeAmbientOcclusion", samples=8, only_local=True)
    b.put(ao.inputs["Distance"], i["Distance"])
    occl = b.mr(ao.outputs["AO"], 0.9, 0.45)
    v = b.vm("MULTIPLY_ADD", i["Vector"], b.comb(*(b.math("DIVIDE", 1.0, i["Speck"]),) * 3),
             b.comb(b.mul(i["Seed"], 5.3), 1.1, b.mul(i["Seed"], 0.7)))
    t0 = b.sub(0.71, b.mul(i["Density"], 0.28))
    speck = b.mr(b.noise(v, detail=2.0, rough=0.6), t0, b.add(t0, 0.07))
    ng.links.new(b.mul(occl, speck), o["Mask"])
    return ng


def _edge():
    """Ray-traced bevel normal vs true normal, restricted to unoccluded (convex) edges: handling polish."""
    ng, b, i, o = _group("GG_WEAR_ConvexEdge", GROUP_INPUTS["GG_WEAR_ConvexEdge"], ["Mask"])
    bev = b.n("ShaderNodeBevel", samples=16)
    b.put(bev.inputs["Radius"], i["Radius"])
    geo = b.n("ShaderNodeNewGeometry")
    e = b.mr(b.sub(1.0, b.vm("DOT_PRODUCT", bev.outputs["Normal"], geo.outputs["Normal"])), i["Low"], i["High"])
    ao = b.n("ShaderNodeAmbientOcclusion", samples=6, only_local=True)
    ao.inputs["Distance"].default_value = 0.0006
    ng.links.new(b.mul(e, b.mr(ao.outputs["AO"], 0.8, 0.97)), o["Mask"])
    return ng


_BUILD = {"scratch": _scratches, "blotch": _blotch, "crevice": _crevice, "edge": _edge}


def build_groups(reuse=True):
    """The four GG_WEAR_* groups as {"scratch", "blotch", "crevice", "edge"}. With reuse (default), groups already in
    the file are kept (other materials may use them) after checking their inputs; missing ones are built."""
    G = {}
    for key, name in GROUPS.items():
        ng = bpy.data.node_groups.get(name) if reuse else None
        if ng is None:
            G[key] = _BUILD[key]()
            continue
        have = [s.name for s in ng.interface.items_tree if s.item_type == "SOCKET" and s.in_out == "INPUT"]
        want = [n for n, _, _ in GROUP_INPUTS[name]]
        if have != want:
            raise RuntimeError(f"existing {name} has inputs {have}, expected {want}; rename or remove it")
        G[key] = ng
    return G


def chips_group(chips, name="GG_WEAR_EnclosureChips"):
    """Deterministic coating-loss points from data: object-local mm [x, y, z, r, axis] (axis = the edge it sits on).
    Outputs Chip (bare substrate) and Rim (fractured coating edge). Count = how many of the list are active; Size scales r."""
    ng, b, i, o = _group(name, [("Vector", V, None), ("Count", F, 0.0), ("Size", F, 1.0)], ["Chip", "Rim"])
    if not chips:
        return ng                                                              # outputs stay 0
    p = b.vm("SCALE", i["Vector"], scale=1000.0)                               # metres -> mm
    wob = b.sub(b.noise(b.vm("SCALE", p, scale=1.0 / 0.12), detail=3.0), 0.5)   # 0.12 mm irregular chip outline
    chip = rim = None
    for k, (x, y, z, r, ax) in enumerate(chips):
        on = b.mr(i["Count"], k + 0.4, k + 0.6)
        st = tuple(0.5 if a == ax else 1.0 for a in "xyz")                    # elongated along its edge
        d = b.mul(b.vm("LENGTH", b.vm("MULTIPLY", b.vm("SUBTRACT", p, (x, y, z)), st)), b.add(1.0, b.mul(wob, 1.8)))
        R = b.mul(i["Size"], r)
        c = b.mul(b.mr(d, R, b.mul(R, 0.8)), on)
        rr = b.mul(b.mr(d, b.mul(R, 1.25), R), on)
        chip = c if chip is None else b.mx(chip, c)
        rim = rr if rim is None else b.mx(rim, rr)
    ng.links.new(chip, o["Chip"])
    ng.links.new(b.mx(b.sub(rim, chip), 0.0), o["Rim"])
    return ng


def strokes_group(name, strokes):
    """Deterministic history strokes from data, object-local mm. Each stroke: a, b (x, y, z), w half-width, s strength,
    kind 'scratch' | 'rub', deep = share of its length cut through to the substrate, gap = break-up period (mm).
    Width wanders, ends fade softly, scratches break up. Outputs Scratch, Rub, Deep."""
    ng, b, i, o = _group(name, [("Vector", V, None)], ["Scratch", "Rub", "Deep"])
    p = b.vm("SCALE", i["Vector"], scale=1000.0)
    S = R = D = 0.0
    for k, st in enumerate(strokes):
        a, e = st["a"], st["b"]
        L = math.dist(a, e)
        u = tuple((e[j] - a[j]) / L for j in range(3))
        tl = b.math("MINIMUM", b.math("MAXIMUM", b.vm("DOT_PRODUCT", b.vm("SUBTRACT", p, a), u), 0.0), L)   # mm along
        t = b.math("DIVIDE", tl, L)
        d = b.vm("DISTANCE", p, b.vm("ADD", b.vm("SCALE", u, scale=tl), a))

        def nz(f, off):
            return b.noise(b.comb(b.math("DIVIDE", tl, f), float(k * 7 + off), 0.5), detail=1.0)

        w = b.mul(st["w"], b.add(0.55, b.mul(nz(1.6, 1), 0.9)))                            # wandering width
        env = b.math("POWER", b.math("SINE", b.mul(t, math.pi)), 0.6)                    # soft start / end
        rub = st.get("kind", "scratch") == "rub"
        gaps = 1.0 if rub else b.mr(nz(st.get("gap", 3.0), 3), 0.33, 0.43)               # interruptions
        if rub:
            w = b.mul(st["w"], b.add(0.85, b.mul(nz(4.0, 1), 0.3)))                       # broad, continuous, soft
        core = b.mr(d, w, b.mul(w, 0.25)) if rub else b.mx(b.mr(d, w, b.mul(w, 0.25)), b.mul(b.mr(d, b.mul(w, 3.2), w), 0.28))
        m = b.mul(b.mul(core, b.mul(env, gaps)), b.mul(st["s"], b.add(0.6, b.mul(nz(2.4, 5), 0.8))))
        if rub:
            R = b.mx(R, m)
        else:
            S = b.mx(S, m)
            if st.get("deep", 0) > 0:
                D = b.mx(D, b.mul(m, b.mr(nz(4.0, 9), 1.0 - st["deep"], 1.0 - st["deep"] + 0.04)))
    for sock, v in zip(("Scratch", "Rub", "Deep"), (S, R, D)):
        if isinstance(v, float):
            o[sock].default_value = v
        else:
            ng.links.new(v, o[sock])
    return ng


# ------------------------------------------------------------------------------------------- material surgery
def derive(base_name, suffix="__WORN"):
    """Fresh copy of a base material named <base><suffix>; users of an older derivative are moved to the new one."""
    m = bpy.data.materials[base_name].copy()
    old = bpy.data.materials.get(base_name + suffix)
    if old is not None:
        old.user_remap(m)
        bpy.data.materials.remove(old)
    m.name = base_name + suffix
    return m


def _bsdf(m):
    found = [n for n in m.node_tree.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"] if m.node_tree else []
    if not found:
        raise ProfileError(f"material {m.name!r} has no Principled BSDF")
    return found[0]


def _input(b, bsdf, name):
    """Current source of a BSDF input: the linked socket (the link is removed), else its constant value."""
    s = bsdf.inputs[name]
    if s.is_linked:
        src = s.links[0].from_socket
        b.nt.links.remove(s.links[0])
        return src
    v = s.default_value
    return tuple(v) if hasattr(v, "__len__") else float(v)


def _normal(bsdf):
    s = bsdf.inputs["Normal"]
    return s.links[0].from_socket if s.is_linked else None


def _set_normal(b, bsdf, bump, nrm):
    if nrm is not None:
        b.put(bump.inputs["Normal"], nrm)
    for link in list(bsdf.inputs["Normal"].links):
        b.nt.links.remove(link)
    b.nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])


def _frame(m, label):
    f = m.node_tree.nodes.new("NodeFrame")
    f.label, f.name, f.label_size = "WEAR — " + label, FRAME, 28
    return f


def _zone(b, terms, x, y, z, r, default):
    """Spatial gate: a callable (b, x, y, z, r) -> socket, or data terms multiplied in order (mm, object-local)."""
    if callable(terms):
        return terms(b, x, y, z, r)
    out = default
    for i, t in enumerate(terms or ()):
        if t[0] == "disc":
            v = b.mr(b.vm("DISTANCE", b.comb(x, y, 0.0), (t[1], t[2], 0.0)), t[3], t[4])
        else:
            v = b.mr({"x": x, "y": y, "z": z, "r": r}[t[0]], t[1], t[2])
        out = v if i == 0 else b.mul(out, v)
    return out


def metal_wear(m, G, spec):
    """Plated / machined metal: scratches, polish and dull patches, tarnish, crevice oxide, convex-edge polish and
    optional insertion-lip (gg_lip_z / gg_lip_r), circumferential plug marks and wrench marks. Sizes in mm."""
    nt, bsdf = m.node_tree, _bsdf(m)
    b = B(nt, _frame(m, spec.get("label", "metal")))
    vec = b.n("ShaderNodeTexCoord").outputs["Object"]
    base, rough, metal = _input(b, bsdf, "Base Color"), _input(b, bsdf, "Roughness"), _input(b, bsdf, "Metallic")
    nrm = _normal(bsdf)
    seed = b.attr("gg_wear_seed")
    x, y, z = b.xyz(b.vm("SCALE", vec, scale=1000.0))
    r = b.vm("LENGTH", b.comb(x, y, 0.0))
    zone = _zone(b, spec.get("zone"), x, y, z, r, 1.0)
    S = 0.0                                             # scratches: rougher micro-grooves with a tiny bump
    for sc in spec.get("scratches", []):
        dens = b.mul(b.attr("gg_wear_scratch"), sc["density"], clamp=True)
        s = b.group(G["scratch"], Vector=vec, Length=sc["length"] * MM, Feature=sc["feature"] * MM, Width=sc["width"],
                    Density=dens, Angle=math.radians(sc.get("angle", 0)), Spread=math.radians(sc.get("spread", 60)), Seed=seed)
        S = b.mx(S, b.mul(s, b.mul(b.mn(b.mul(b.attr("gg_wear_scratch"), 1.5), 1.0), zone if sc.get("zoned", True) else 1.0)))
    P = b.mul(b.mul(_zone(b, spec.get("polish_zone"), x, y, z, r, 0.0), b.attr("gg_wear_polish")),
              b.group(G["blotch"], Vector=vec, Size=0.0015, Seed=seed, Threshold=0.38, Softness=0.25))
    D = b.mul(b.mul(b.attr("gg_wear_polish"), spec.get("dull", 0.0)),
              b.mul(b.group(G["blotch"], Vector=vec, Size=0.0011, Seed=b.add(seed, 4.0), Threshold=0.58, Softness=0.1), zone))
    T = b.mul(b.attr("gg_wear_tarnish"), b.group(G["blotch"], Vector=vec, Size=spec.get("tarnish_size", 2.2) * MM,
                                                 Seed=b.add(seed, 9.0), Threshold=0.40, Softness=0.25))
    O = b.mn(b.mul(b.attr("gg_wear_oxide"), b.group(G["crevice"], Vector=vec, Distance=spec.get("crevice", 0.4) * MM,
             Speck=spec.get("speck", 0.14) * MM, Density=b.attr("gg_wear_oxide"), Seed=seed)), 1.0)
    E = b.mul(b.attr("gg_wear_edge"), b.mul(b.group(G["edge"], Radius=spec.get("edge_r", 0.15) * MM, Low=0.01, High=0.07),
              b.group(G["blotch"], Vector=vec, Size=0.0008, Seed=b.add(seed, 2.0), Threshold=0.4, Softness=0.2)))
    Lp = 0.0
    if spec.get("lip"):          # insertion lip: end face at gg_lip_z, opening radius gg_lip_r (mm, per object)
        Lz, Lr = b.attr("gg_lip_z"), b.attr("gg_lip_r")
        Lp = b.mul(b.attr("gg_wear_lip"), b.mul(b.mr(z, b.sub(Lz, 0.45), b.sub(Lz, 0.08)), b.mr(r, b.add(Lr, 0.9), b.add(Lr, 0.15))))
    if spec.get("lip_wide"):     # broader burnished contact ring from years of plugs
        Lz, Lr = b.attr("gg_lip_z"), b.attr("gg_lip_r")
        Lw = b.mul(b.attr("gg_wear_lipwide"), b.mul(b.mr(z, b.sub(Lz, 0.85), b.sub(Lz, 0.3)), b.mr(r, b.add(Lr, 1.6), b.add(Lr, 0.8))))
        Lp = b.mx(Lp, b.mul(Lw, 0.7))
    if spec.get("lip_scratch"):  # circumferential insertion scratches on the lip (plug rotation)
        pol = b.vm("SCALE", b.comb(b.mul(b.math("ARCTAN2", y, x), 3.8), r, z), scale=MM)
        ls = b.group(G["scratch"], Vector=pol, Length=2.6 * MM, Feature=0.09 * MM, Width=0.03,
                     Density=b.mul(b.attr("gg_wear_lip"), 0.6, clamp=True), Angle=0.0, Spread=math.radians(4), Seed=b.add(seed, 3.0))
        S = b.mx(S, b.mul(ls, b.mn(b.mul(Lp, 1.6), 1.0)))
    if spec.get("lip_long"):     # a few longer circumferential marks from rotating plugs
        pol = b.vm("SCALE", b.comb(b.mul(b.math("ARCTAN2", y, x), 3.9), r, z), scale=MM)
        ll = b.group(G["scratch"], Vector=pol, Length=6.0 * MM, Feature=0.16 * MM, Width=0.03,
                     Density=b.mul(b.attr("gg_wear_liplong"), 0.55, clamp=True), Angle=0.0, Spread=math.radians(3), Seed=b.add(seed, 11.0))
        S = b.mx(S, b.mul(b.mul(ll, b.mn(b.mul(b.attr("gg_wear_liplong"), 1.5), 1.0)), b.mn(b.mul(Lp, 2.0), 1.0)))
    if spec.get("wrench"):       # stronger wrench marks on hex flats between radii wrench[0]..wrench[1] (mm)
        wz = b.mr(r, spec["wrench"][0], spec["wrench"][1])
        wm = b.group(G["scratch"], Vector=vec, Length=0.9 * MM, Feature=0.3 * MM, Width=0.05,
                     Density=b.mul(b.attr("gg_wear_wrench"), 0.5, clamp=True), Angle=0.0, Spread=math.radians(85), Seed=b.add(seed, 13.0))
        S = b.mx(S, b.mul(b.mul(wm, wz), b.mn(b.mul(b.attr("gg_wear_wrench"), 1.5), 1.0)))
    # roughness: polish / edge / lip burnish lower it, tarnish / dull / scratches raise it, oxide is matte
    r1 = b.mul(rough, b.sub(1.0, b.mn(b.add(b.add(b.mul(P, 0.45), b.mul(E, 0.4)), b.mul(Lp, 0.5)), 0.7)))
    haze = b.mul(b.mul(b.attr("gg_wear_scratch"), spec.get("haze", 0.04)), zone)   # unresolved micro-scratch haze
    r2 = b.add(b.add(b.add(r1, b.mul(T, 0.12)), b.mul(D, spec.get("dull_r", 0.12))), haze)
    r3 = b.lerp(b.mn(S, 1.0), r2, b.add(r2, spec.get("scratch_r", 0.14)))
    b.put(bsdf.inputs["Roughness"], b.lerp(O, r3, 0.72))
    # colour: tarnish is a small warm / grey shift of the plating; oxide is sparse dark brown-black
    c1 = b.mixc(b.mul(T, spec.get("tarnish_mix", 0.6)), base, tuple(spec.get("tarnish_col", (0.47, 0.42, 0.33, 1.0))))
    b.put(bsdf.inputs["Base Color"], b.mixc(O, c1, (0.075, 0.045, 0.022, 1.0)))
    b.put(bsdf.inputs["Metallic"], b.lerp(O, metal, 0.35))
    bump = b.n("ShaderNodeBump")
    bump.inputs["Strength"].default_value, bump.inputs["Distance"].default_value = spec.get("bump", 0.6), 0.000004
    b.put(bump.inputs["Height"], b.math("MULTIPLY", S, -1.0))
    _set_normal(b, bsdf, bump, nrm)
    return m


def plastic_wear(m, G, spec):
    """Moulded plastic (knob body): glossier convex ridges and broad grip polish inside the grip band grip_z (mm),
    optional tiny scuffed contact marks on ridge high points (gg_wear_contact)."""
    nt, bsdf = m.node_tree, _bsdf(m)
    b = B(nt, _frame(m, spec.get("label", "moulded plastic handling")))
    vec = b.n("ShaderNodeTexCoord").outputs["Object"]
    seed = b.attr("gg_wear_seed")
    rough = _input(b, bsdf, "Roughness")
    x, y, z = b.xyz(b.vm("SCALE", vec, scale=1000.0))
    grip = b.mr(z, *spec["grip_z"]) if "grip_z" in spec else 1.0
    edge_r = spec.get("edge_r", 0.2)
    E = b.mul(b.mul(b.attr("gg_wear_edge"), grip), b.group(G["edge"], Radius=edge_r * MM, Low=0.015, High=0.09))
    P = b.mul(b.mul(b.attr("gg_wear_polish"), grip), b.group(G["blotch"], Vector=vec, Size=0.004, Seed=seed, Threshold=0.4, Softness=0.3))
    rr = b.mul(rough, b.sub(1.0, b.mn(b.add(b.mul(E, 0.30), b.mul(P, 0.10)), 0.4)))
    if spec.get("contact"):      # slightly rougher, a shade lighter (contact_col)
        Cm = b.group(G["scratch"], Vector=vec, Length=0.9 * MM, Feature=0.35 * MM, Width=0.05,
                     Density=b.mul(b.attr("gg_wear_contact"), 0.35, clamp=True), Angle=1.57, Spread=math.radians(30), Seed=b.add(seed, 8.0))
        Cm = b.mul(b.mul(Cm, b.mn(b.mul(b.attr("gg_wear_contact"), 1.5), 1.0)),
                   b.mul(grip, b.group(G["edge"], Radius=edge_r * MM, Low=0.015, High=0.09)))
        rr = b.lerp(Cm, rr, b.add(rr, 0.12))
        base = _input(b, bsdf, "Base Color")
        b.put(bsdf.inputs["Base Color"], b.mixc(b.mul(Cm, 0.5), base, tuple(spec.get("contact_col", (0.03, 0.03, 0.032, 1.0)))))
    b.put(bsdf.inputs["Roughness"], rr)
    return m


def paint_wear(m, G, spec, chips_ng=None, strokes_ng=None):
    """Painted / powder-coated box, object origin at the box centre, spec["half"] = half extents (mm). Analytic masks:
    rounded-edge apex burnish (edge_r), corner and lower-edge emphasis, front bias (front), side rub, optional
    footswitch shoe-scuff annulus, plug rub around side jacks, light micro-abrasion on the flat top (labels excluded)
    and sides; optional chips (chips_group) and strokes (strokes_group) cut to the substrate colour."""
    nt, bsdf = m.node_tree, _bsdf(m)
    b = B(nt, _frame(m, spec.get("label", "paint")))
    vec = b.n("ShaderNodeTexCoord").outputs["Object"]
    seed = b.attr("gg_wear_seed")
    base, rough = _input(b, bsdf, "Base Color"), _input(b, bsdf, "Roughness")
    nrm = _normal(bsdf)
    x, y, z = b.xyz(b.vm("SCALE", vec, scale=1000.0))
    HX, HY, HZ = spec["half"]
    dx, dy = b.sub(HX, b.math("ABSOLUTE", x)), b.sub(HY, b.math("ABSOLUTE", y))
    dt, db = b.sub(HZ, z), b.add(z, HZ)
    er = spec.get("edge_r", 1.5)

    def apex(a, c):                                                            # apex band of the rounded edge
        return b.mr(b.add(a, c), er, er * 0.6)

    Ve, Te, Be = apex(dx, dy), b.mx(apex(dt, dx), apex(dt, dy)), b.mx(apex(db, dx), apex(db, dy))
    corner = b.mr(b.add(b.add(dx, dy), b.mn(dt, db)), *spec.get("corner", (9.0, 2.0)))
    fy0, fy1, fmin = spec.get("front", (10.0, -40.0, 0.6))                    # -y (player side) sees more knocks
    front = b.mr(y, fy0, fy1, fmin, 1.0)
    Ew = b.mn(b.add(b.add(b.mul(Ve, 0.75), b.mul(Te, 0.45)), b.add(b.mul(Be, 0.8), b.mul(corner, 0.6))), 1.0)
    Ew = b.mul(b.mul(b.mul(Ew, front), b.attr("gg_wear_edge")),
               b.group(G["blotch"], Vector=vec, Size=0.0009, Seed=seed, Threshold=0.35, Softness=0.3))
    if spec.get("lower"):        # lower edges / bottom lip carry more transport rub
        Ew = b.mn(b.mul(Ew, b.add(1.0, b.mul(b.attr("gg_wear_lower"), b.mr(z, *spec.get("lower_z", (0.0, -(HZ - 2.5))))))), 1.0)
    topok = b.mul(b.mr(dt, 0.05, 0.0), b.mr(z, HZ - 0.004, HZ - 0.001))     # flat top plane only: engraving untouched
    if spec.get("labels"):
        lab = 0.0
        for x0, y0, x1, y1 in spec["labels"]:
            inside = b.mul(b.mul(b.mr(x, x0 - 0.9, x0 - 0.4), b.mr(x, x1 + 0.9, x1 + 0.4)),
                           b.mul(b.mr(y, y0 - 0.9, y0 - 0.4), b.mr(y, y1 + 0.9, y1 + 0.4)))
            lab = b.mx(lab, inside)
        topok = b.mul(topok, b.sub(1.0, lab))
    fs = spec.get("footswitch")
    if fs:                       # shoe-scuff annulus on the player side of the footswitch
        r0, r1, r2, r3 = spec.get("shoe_r", (9.0, 9.8, 15.5, 11.0))
        ymin = spec.get("shoe_ymin", fs[1] - 9.5)
        rf = b.vm("DISTANCE", b.comb(x, y, 0.0), (fs[0], fs[1], 0.0))
        shoe = b.mul(b.mul(b.mr(rf, r0, r1), b.mr(rf, r2, r3)), b.mr(y, ymin - 1.0, ymin))
        shoe = b.mul(b.mul(shoe, topok), b.attr("gg_wear_scuff"))
    side = b.mul(b.mr(dx, 0.25, 0.05), b.mr(b.math("ABSOLUTE", z), *spec.get("side_z", (HZ - 2.0, HZ - 7.5))))
    Pol = b.mul(side, b.mul(b.attr("gg_wear_polish"), 0.7))
    if fs:
        Pol = b.add(Pol, b.mul(shoe, 0.8))
    if spec.get("jacks"):        # plug rub around jacks on the +-x side faces, [y, z] mm each
        j0, j1, j2, j3 = spec.get("jack_r", (6.9, 7.6, 11.5, 8.5))
        jr = 0.0
        for jy, jz in spec["jacks"]:
            rj = b.vm("DISTANCE", b.comb(0.0, y, z), (0.0, jy, jz))
            jr = b.mx(jr, b.mul(b.mr(rj, j0, j1), b.mr(rj, j2, j3)))
        jrub = b.mul(b.mul(jr, b.mr(dx, 0.25, 0.05)), b.attr("gg_wear_jackrub"))
        if spec.get("jack_asym"):    # the +x (input) side has seen more plugs than -x
            jrub = b.mul(jrub, b.sub(1.0, b.mul(b.attr("gg_wear_jackasym"), b.mr(x, 1.0, -1.0))))
        Pol = b.add(Pol, jrub)
    if spec.get("sides"):        # transport / neighbour rub on the side faces
        Pol = b.add(Pol, b.mul(side, b.mul(b.attr("gg_wear_sides"), 0.5)))
    Pol = b.mul(b.mn(Pol, 1.0), b.group(G["blotch"], Vector=vec, Size=0.0025, Seed=b.add(seed, 1.0), Threshold=0.36, Softness=0.3))
    # micro-abrasion: very light everywhere, horizontal rub lines on the sides, front-back shoe scuffs near the footswitch
    ab_all = b.group(G["scratch"], Vector=vec, Length=0.0035, Feature=0.0003, Width=0.025,
                     Density=b.mul(b.attr("gg_wear_abrasion"), 0.45, clamp=True), Angle=0.0, Spread=math.radians(70), Seed=seed)
    ab_side = b.group(G["scratch"], Vector=vec, Length=0.006, Feature=0.00025, Width=0.03,
                      Density=b.mul(b.attr("gg_wear_abrasion"), 0.8, clamp=True), Angle=math.radians(90),
                      Spread=math.radians(6), Seed=b.add(seed, 5.0))
    nottop = b.sub(1.0, b.mr(dt, 0.05, 0.0))
    Ab = b.mx(b.mul(ab_all, b.mul(b.attr("gg_wear_abrasion"), b.add(b.mul(topok, 0.5), b.mul(nottop, 0.8)))),
              b.mul(ab_side, b.mul(side, b.attr("gg_wear_abrasion"))))
    if fs:
        ab_shoe = b.group(G["scratch"], Vector=vec, Length=0.004, Feature=0.0002, Width=0.035,
                          Density=b.mul(b.attr("gg_wear_scuff"), 0.9, clamp=True), Angle=math.radians(90),
                          Spread=math.radians(22), Seed=b.add(seed, 7.0))
        Ab = b.mx(Ab, b.mul(ab_shoe, b.mn(b.mul(shoe, 2.0), 1.0)))
    if spec.get("sides"):
        ab_side2 = b.group(G["scratch"], Vector=vec, Length=0.009, Feature=0.0004, Width=0.028,
                           Density=b.mul(b.attr("gg_wear_sides"), 0.6, clamp=True), Angle=math.radians(84),
                           Spread=math.radians(9), Seed=b.add(seed, 15.0))
        Ab = b.mx(Ab, b.mul(ab_side2, b.mul(side, b.mn(b.mul(b.attr("gg_wear_sides"), 1.4), 1.0))))
    Ab = b.mn(Ab, 1.0)
    Chip = Rim = Sk = 0.0
    if chips_ng is not None:
        out = b.group(chips_ng, Vector=vec, Count=b.attr("gg_wear_chips"), Size=b.attr("gg_wear_chipsize")).node.outputs
        Chip, Rim = out[0], out[1]
    if strokes_ng is not None:   # deterministic history strokes, never on the top face
        st = b.group(strokes_ng, Vector=vec).node.outputs
        amt, off = b.attr("gg_wear_strokes"), b.mr(dt, 0.4, 0.8)
        Sk, Rb, Dp = (b.mul(b.mul(st[i], amt), off) for i in range(3))
        Pol = b.mn(b.add(Pol, b.mul(Rb, 0.8)), 1.0)
        Chip = b.mx(Chip, b.mn(Dp, 1.0))
    # roughness: burnish lowers the satin roughness slightly, scuffed edges are more matte, chips are dulled metal
    r1 = b.add(b.mul(rough, b.sub(1.0, b.mn(b.add(b.mul(Pol, 0.22), b.mul(Ab, 0.18)), 0.5))), b.mul(Ew, 0.10))
    if strokes_ng is not None:
        r1 = b.add(r1, b.mul(Sk, 0.22))
    b.put(bsdf.inputs["Roughness"], b.lerp(Chip, b.lerp(Rim, r1, 0.62), 0.55))
    c0 = b.mixc(b.mul(Ew, 0.16), base, tuple(spec.get("edge_col", (0.89, 0.89, 0.89, 1.0))))   # abraded apex reads paler
    if strokes_ng is not None:
        c0 = b.mixc(b.mul(Sk, 0.65), c0, tuple(spec.get("stroke_col", (0.94, 0.94, 0.94, 1.0))))
    c1 = b.mixc(b.mul(Rim, 0.28), c0, tuple(spec.get("rim_col", (0.90, 0.90, 0.90, 1.0))))     # crushed coating edge
    b.put(bsdf.inputs["Base Color"], b.mixc(Chip, c1, tuple(spec.get("substrate", (0.78, 0.77, 0.74, 1.0)))))
    metal = _input(b, bsdf, "Metallic")
    b.put(bsdf.inputs["Metallic"], Chip if metal == 0.0 else b.lerp(Chip, metal, 1.0))
    bump = b.n("ShaderNodeBump")
    bump.inputs["Strength"].default_value, bump.inputs["Distance"].default_value = 0.7, 0.00004       # ~coating thickness
    b.put(bump.inputs["Height"], b.math("MULTIPLY", b.add(Chip, b.mul(Ab, 0.004)), -1.0))
    _set_normal(b, bsdf, bump, nrm)
    return m


# ------------------------------------------------------------------------------------------- profile application
def apply_profile(profile, level=None):
    """Assign gg_wear_* properties and build the worn derivatives in the open file; everything is checked first.
    Matching slots (holding the base or its derivative) are switched to object-level links, so the mesh data keeps
    the base material. Returns a JSON-ready summary."""
    R = resolve_profile(profile, level)
    errors, slots = [], {}
    for name, d in R["derivatives"].items():
        m = bpy.data.materials.get(d["base"])
        if m is None:
            errors.append(f"derivatives.{name}: base material {d['base']!r} is not in the file")
        elif not m.node_tree or not any(n.bl_idname == "ShaderNodeBsdfPrincipled" for n in m.node_tree.nodes):
            errors.append(f"derivatives.{name}: base material {d['base']!r} has no Principled BSDF")
    for name, o in R["objects"].items():
        ob = bpy.data.objects.get(name)
        if ob is None:
            errors.append(f"objects.{name}: object not in the file")
            continue
        slots[name] = [i for i, s in enumerate(ob.material_slots) if s.material and s.material.name in (o["base"], o["derivative"])]
        if not slots[name]:
            errors.append(f"objects.{name}: no material slot holds {o['base']!r}")
    if errors:
        raise ProfileError("\n".join(errors))
    G = build_groups(reuse=True)
    made = {}
    for name, d in R["derivatives"].items():
        m = derive(d["base"], name[len(d["base"]):])
        spec = d["spec"]
        if d["builder"] == "metal":
            metal_wear(m, G, spec)
        elif d["builder"] == "plastic":
            plastic_wear(m, G, spec)
        else:
            chips = chips_group(spec["chips"], f"GG_WEAR_Chips__{name}") if spec.get("chips") else None
            strokes = strokes_group(f"GG_WEAR_Strokes__{name}", spec["strokes"]) if spec.get("strokes") else None
            paint_wear(m, G, spec, chips_ng=chips, strokes_ng=strokes)
        made[name] = m
    for name, o in R["objects"].items():
        ob = bpy.data.objects[name]
        for k in [k for k in ob.keys() if k.startswith(("gg_wear_", "gg_lip_"))]:
            del ob[k]                                                          # the profile is authoritative
        for k, v in o["props"].items():
            ob[k] = v
        for i in slots[name]:
            ob.material_slots[i].link = "OBJECT"
            ob.material_slots[i].material = made[o["derivative"]]
    return {"level": R["level"], "groups": sorted(g.name for g in bpy.data.node_groups if g.name.startswith("GG_WEAR_")),
            "derivatives": {n: {"base": d["base"], "builder": d["builder"]} for n, d in R["derivatives"].items()},
            "objects": {n: {"derivative": o["derivative"], "slots": slots[n], "props": o["props"]} for n, o in R["objects"].items()}}


# ------------------------------------------------------------------------------------------- tests
FIXTURE = {
    "level": "B",
    "levels": {"plated": {"scratch": [0.4, 0.5, 0.6], "edge": [0.3333, 0.66666, 1.0], "lip": [0.0, 1.0, 1.2]},
               "coat": {"edge": [0.5, 0.6, 0.7], "chips": [2, 5, 7], "chipsize": [1.0, 1.0, 1.2]}},
    "derivatives": {"MAT_A__WORN": {"base": "MAT_A", "builder": "metal", "spec": {"scratches": [
                        {"length": 1.0, "feature": 0.15, "width": 0.03, "density": 0.4}], "lip": True, "zone": [["z", 1.0, 1.3]]}},
                    "MAT_C__WORN": {"base": "MAT_C", "builder": "paint", "spec": {"half": [20, 40, 10], "chips": [[0, 10, 5, 0.3, "x"]],
                        "strokes": [{"a": [0, 0, 0], "b": [10, 0, 0], "w": 0.2, "s": 0.5, "deep": 0.1}]}}},
    "objects": {"Nut": {"family": "plated", "derivative": "MAT_A__WORN", "mult": 0.8, "seed": 7.1, "lip_z": 2.0, "lip_r": 3.3},
                "Box": {"family": "coat", "derivative": "MAT_C__WORN", "mult": 2.0, "mult_level": [1.0, 0.5, 1.0], "seed": 3}},
}


def _with(profile, path, value):
    """Deep copy of a profile with one entry replaced (value None deletes it); path is a list of keys."""
    p = copy.deepcopy(profile)
    d = p
    for k in path[:-1]:
        d = d[k]
    if value is None:
        del d[path[-1]]
    else:
        d[path[-1]] = value
    return p


def self_test():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    r = resolve_profile(FIXTURE)
    nut, box = r["objects"]["Nut"]["props"], r["objects"]["Box"]["props"]
    check(r["level"] == "B", "default level B")
    check(nut == {"gg_wear_scratch": 0.4, "gg_wear_edge": 0.5333, "gg_wear_lip": 0.8, "gg_wear_seed": 7.1,
                  "gg_lip_z": 2.0, "gg_lip_r": 3.3}, f"Nut props at B: {nut}")
    check(box == {"gg_wear_edge": 0.3, "gg_wear_chips": 5.0, "gg_wear_chipsize": 1.0, "gg_wear_seed": 3.0},
          f"Box props at B (mult_level 0.5, chips unscaled): {box}")
    rc = resolve_profile(FIXTURE, "C")["objects"]
    check(rc["Nut"]["props"]["gg_wear_lip"] == 0.96 and rc["Box"]["props"]["gg_wear_chipsize"] == 1.2, "level C override")
    check(resolve_profile(_with(FIXTURE, ["level"], "A"))["objects"]["Nut"]["props"]["gg_wear_edge"] == 0.2666, "profile level A")
    check(r["objects"]["Box"]["base"] == "MAT_C" and r["derivatives"]["MAT_A__WORN"]["builder"] == "metal", "derivative mapping")
    if EXAMPLE.is_file():
        for lv in LEVELS:
            try:
                ex = resolve_profile(load_profile(EXAMPLE), lv)
                check(len(ex["objects"]) == 3, f"example profile objects at {lv}")
            except ProfileError as exc:
                fails.append(f"example profile at {lv}: {exc}")
    else:
        fails.append(f"example profile missing: {EXAMPLE.name}")
    bad = [
        (["level"], "D", "must be one of A, B, C"),
        (["objects"], {}, "objects: must be a non-empty object"),
        (["levels", "plated", "edge"], [0.1, 0.2], "levels.plated.edge: must be [A, B, C]"),
        (["levels", "plated", "edge"], [0.1, float("nan"), 0.3], "levels.plated.edge"),
        (["levels", "plated", "edge"], [0.1, True, 0.3], "levels.plated.edge"),
        (["levels", "plated", "chips"], [1, 2, 3], "never reads"),
        (["objects", "Nut", "family"], "nope", "objects.Nut.family: 'nope' is not in levels"),
        (["objects", "Nut", "derivative"], "X__WORN", "objects.Nut.derivative"),
        (["objects", "Nut", "seed"], None, "objects.Nut.seed"),
        (["objects", "Nut", "lip_r"], None, "lip_z and lip_r"),
        (["objects", "Nut", "mult_level"], [1, 2], "objects.Nut.mult_level"),
        (["objects", "Nut", "colour"], "red", "objects.Nut.colour: unknown key"),
        (["derivatives", "MAT_A__WORN", "builder"], "glass", "builder: 'glass' must be one of"),
        (["derivatives", "MAT_A__WORN", "base"], "MAT_B", "named <base>__<suffix>"),
        (["derivatives", "MAT_A__WORN", "spec", "edge_rad"], 0.1, "spec.edge_rad: unknown key for the metal builder"),
        (["derivatives", "MAT_A__WORN", "spec", "wrench"], [5.2], "spec.wrench: expected a list of 2 numbers"),
        (["derivatives", "MAT_A__WORN", "spec", "lip"], 1, "spec.lip: expected true or false"),
        (["derivatives", "MAT_A__WORN", "spec", "zone"], [["w", 1, 2]], "spec.zone: expected"),
        (["derivatives", "MAT_A__WORN", "spec", "scratches"], [{"length": 1}], "spec.scratches: expected"),
        (["derivatives", "MAT_C__WORN", "spec", "half"], None, "spec.half: required by the paint builder"),
        (["derivatives", "MAT_C__WORN", "spec", "chips"], [[0, 10, 5, 0.3, "w"]], "spec.chips: expected"),
        (["objects", "Nut", "family"], ["plated"], "objects.Nut.family"),
        (["derivatives", "MAT_A__WORN", "builder"], ["metal"], "MAT_A__WORN.builder"),
        (["derivatives", "MAT_C__WORN", "spec", "strokes"], [{"a": [0, 0, 0], "b": [0, 0, 0], "w": 1, "s": 1}], "spec.strokes: expected"),
        (["extra"], 1, "profile.extra: unknown key"),
    ]
    for path, value, want in bad:
        try:
            resolve_profile(_with(FIXTURE, path, value))
            fails.append(f"no ProfileError for {path} = {value!r}")
        except ProfileError as exc:
            check(want in str(exc), f"error {str(exc)!r} lacks {want!r}")
    try:
        resolve_profile([])
        fails.append("a non-object profile was accepted")
    except ProfileError as exc:
        check("must be a JSON object" in str(exc), "non-object profile message")
    a = parse_args(["apply", "--profile", "p.json"])
    check((a.command, a.profile, a.level, a.save) == ("apply", "p.json", None, None), "parse apply defaults")
    a = parse_args(["apply", "--profile", "p.json", "--level", "C", "--save", "out.blend"])
    check((a.level, a.save) == ("C", "out.blend"), "parse --level/--save")
    for argv in (["apply"], ["apply", "--profile", "p.json", "--level", "D"], [], ["remove", "--profile", "p.json"]):
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                parse_args(argv)
            fails.append(f"parse_args accepted {argv}")
        except SystemExit as exc:
            check(exc.code == 2, f"parse_args exit code for {argv}")
    check(script_args(["blender", "-b", "f.blend", "--python", "w.py", "--", "apply", "--profile", "p"]) == ["apply", "--profile", "p"],
          "args after --")
    check(script_args(["w.py", "--self-test"], blender=False) == ["--self-test"], "plain python args")
    check(script_args(["blender", "-b", "f.blend", "--python", "w.py"], blender=True) == [], "no script args under Blender")
    here = os.path.abspath("in.blend")
    for save in ("in.blend", here, os.path.join(".", "sub", "..", "in.blend"), "out.txt"):
        try:
            save_target(save, here)
            fails.append(f"save_target accepted {save}")
        except ProfileError:
            pass
    check(save_target("out.blend", here) == os.path.abspath("out.blend"), "save_target new path")
    check(save_target("out.blend", "") == os.path.abspath("out.blend"), "save_target unsaved input")
    for f in fails:
        print("FAIL:", f)
    print(f"wear_library self-test: {'PASS' if not fails else f'{len(fails)} FAILED'}")
    return 1 if fails else 0


def _bake(ob, mat, what, size):
    """Values of one Principled input of `mat` on `ob` (EMIT bake through a temporary copy), or the shading normal
    (what='Normal', object-space NORMAL bake). Returns RGB triples of the baked texels only."""
    tmp = mat.copy()
    nt, bsdf = tmp.node_tree, _bsdf(tmp)
    if what != "Normal":
        out = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeOutputMaterial" and n.is_active_output)
        em = nt.nodes.new("ShaderNodeEmission")
        s = bsdf.inputs[what]
        if s.is_linked:
            nt.links.new(s.links[0].from_socket, em.inputs["Color"])
        else:
            v = s.default_value
            em.inputs["Color"].default_value = tuple(v) if hasattr(v, "__len__") else (v, v, v, 1.0)
        nt.links.new(em.outputs[0], out.inputs["Surface"])
    img = bpy.data.images.new("gg_wear_bake", size, size, alpha=True, float_buffer=True)
    img.generated_color = (0.0, 0.0, 0.0, 0.0)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    nt.nodes.active = tex
    slot = ob.material_slots[0]
    keep = slot.material
    slot.material = tmp
    for o in bpy.context.view_layer.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob
    try:
        if what == "Normal":
            bpy.ops.object.bake(type="NORMAL", normal_space="OBJECT", margin=0, use_clear=False)
        else:
            bpy.ops.object.bake(type="EMIT", margin=0, use_clear=False)
    finally:
        slot.material = keep
    px = array("f", [0.0]) * (size * size * 4)
    img.pixels.foreach_get(px)
    bpy.data.materials.remove(tmp)
    bpy.data.images.remove(img)
    return [tuple(px[i:i + 3]) for i in range(0, len(px), 4) if px[i + 3] > 0.5]


def _stats(worn, base):
    """Texels where the worn value leaves the base constant, and the variance of the worn values there."""
    diff = [w for w in worn if max(abs(w[c] - base[c]) for c in range(3)) > 1e-4]
    lum = [sum(w) / 3.0 for w in diff]
    mean = sum(lum) / len(lum) if lum else 0.0
    return {"texels": len(worn), "masked": len(diff), "masked_variance": sum((v - mean) ** 2 for v in lum) / len(lum) if lum else 0.0,
            "max_abs_diff": max((max(abs(w[c] - base[c]) for c in range(3)) for w in worn), default=0.0)}


def blender_test():
    """Synthetic metal cylinder, black plastic knob and painted box; applies the example profile; checks groups,
    derivatives, properties, surface variation inside the masks and that a zero-amount profile equals the base;
    repeats with builder-default specs on a paint base with non-zero Metallic."""
    from mathutils import Matrix
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device, scene.cycles.samples = "CPU", 4
    profile = load_profile(EXAMPLE)
    BASES = {}   # base material -> constant (Base Color, Roughness, Metallic)

    def part(name, mat, color, rough, metal, add, mtx):
        add()
        ob = bpy.context.active_object
        ob.name = ob.data.name = name
        ob.data.transform(mtx)                                                # sizes in the mesh: scale stays 1
        m = bpy.data.materials.new(mat)
        bsdf = _bsdf(m)
        bsdf.inputs["Base Color"].default_value, bsdf.inputs["Roughness"].default_value = color, rough
        bsdf.inputs["Metallic"].default_value = metal
        ob.data.materials.append(m)
        BASES[mat] = {"Base Color": color[:3], "Roughness": (rough,) * 3, "Metallic": (metal,) * 3}
        return ob

    part("Jack_Barrel", "MAT_NICKEL_PLATED", (0.75, 0.74, 0.70, 1.0), 0.22, 1.0,
         lambda: bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=0.0047, depth=0.010), Matrix.Translation((0, 0, 0.005)))
    part("Knob", "MAT_KNOB_BLACK", (0.02, 0.02, 0.022, 1.0), 0.45, 0.0,
         lambda: bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=0.009, depth=0.016), Matrix.Translation((0, 0, 0.008)))
    part("Enclosure", "MAT_POWDERCOAT", (0.05, 0.12, 0.35, 1.0), 0.5, 0.0,
         lambda: bpy.ops.mesh.primitive_cube_add(size=1.0), Matrix.Diagonal((0.060, 0.112, 0.029, 1.0)))
    fails, report = [], {}

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    n_mats = len(bpy.data.materials)
    try:
        apply_profile(_with(profile, ["objects", "Missing"], {"family": "metal_plated",
                      "derivative": "MAT_NICKEL_PLATED__WORN", "seed": 1.0}))
        fails.append("apply accepted a profile naming a missing object")
    except ProfileError as exc:
        check("objects.Missing: object not in the file" in str(exc), f"missing-object error: {exc}")
    check(len(bpy.data.materials) == n_mats and not bpy.data.node_groups, "a refused profile changed the file")
    summary = apply_profile(profile)
    report["apply"] = {"level": summary["level"], "groups": summary["groups"]}
    for name, inputs in GROUP_INPUTS.items():
        ng = bpy.data.node_groups.get(name)
        got = [(s.name, s.socket_type, round(s.default_value, 7) if s.socket_type == F else None)
               for s in ng.interface.items_tree if s.item_type == "SOCKET" and s.in_out == "INPUT"] if ng else None
        check(got == [(n, t, round(d, 7) if d is not None else None) for n, t, d in inputs], f"{name} inputs {got}")
    resolved = resolve_profile(profile)
    for oname, o in resolved["objects"].items():
        ob = bpy.data.objects[oname]
        slot, m = ob.material_slots[0], bpy.data.materials.get(o["derivative"])
        check(m is not None and slot.link == "OBJECT" and slot.material == m, f"{oname}: object-linked derivative")
        check(ob.data.materials[0].name == o["base"], f"{oname}: mesh data keeps the base material")
        check({k: ob[k] for k in ob.keys() if k.startswith("gg_")} == o["props"], f"{oname}: properties")
        if m is not None:
            check(FRAME in m.node_tree.nodes, f"{oname}: GG_WEAR frame")
            b = _bsdf(m)
            routed = {"metal": ("Base Color", "Roughness", "Metallic", "Normal"), "plastic": ("Base Color", "Roughness"),
                      "paint": ("Base Color", "Roughness", "Metallic", "Normal")}[resolved["derivatives"][o["derivative"]]["builder"]]
            check(all(b.inputs[s].is_linked for s in routed), f"{oname}: inputs re-routed")
        base = bpy.data.materials[o["base"]]
        check(not any(_bsdf(base).inputs[s].is_linked for s in ("Base Color", "Roughness", "Metallic", "Normal")), f"{oname}: base untouched")
        stats = report[oname] = {w: _stats(_bake(ob, m, w, 128), BASES[o["base"]][w]) for w in ("Base Color", "Roughness", "Metallic")}
        check(stats["Roughness"]["masked"] > 0 and stats["Roughness"]["masked_variance"] > 1e-7, f"{oname}: roughness does not vary")
        if oname != "Knob":
            check(stats["Base Color"]["masked"] > 0 and stats["Base Color"]["masked_variance"] > 1e-9, f"{oname}: colour does not vary")

    def zero_check(prof, tag):
        """Every amount 0: each derivative must equal its base (colour, roughness, metallic, shading normal)."""
        zero = copy.deepcopy(prof)
        for table in zero["levels"].values():
            table.update({k: [0, 0, 0] for k in table if k != "_doc"})
        counts = (len(bpy.data.materials), len(bpy.data.node_groups))
        apply_profile(zero)
        check((len(bpy.data.materials), len(bpy.data.node_groups)) == counts and not any(".0" in d.name for d in
              (*bpy.data.materials, *bpy.data.node_groups)), f"{tag}: re-applying left duplicate materials or groups")
        report[tag] = {}
        for oname, o in resolve_profile(zero)["objects"].items():
            ob, m, base = bpy.data.objects[oname], bpy.data.materials[o["derivative"]], bpy.data.materials[o["base"]]
            diffs = {w: _stats(_bake(ob, m, w, 64), BASES[o["base"]][w])["max_abs_diff"] for w in ("Base Color", "Roughness", "Metallic")}
            wn, bn = _bake(ob, m, "Normal", 64), _bake(ob, base, "Normal", 64)
            diffs["Normal"] = max(max(abs(a[c] - b[c]) for c in range(3)) for a, b in zip(wn, bn)) if len(wn) == len(bn) else 1.0
            report[tag][oname] = diffs
            check(all(v <= 1e-5 for k, v in diffs.items() if k != "Normal") and diffs["Normal"] <= 1e-4, f"{tag} {oname}: != base {diffs}")

    zero_check(profile, "zero")
    # builder defaults only (no zones, lip, grip band, labels, footswitch, jacks, chips, strokes); the paint base now has
    # Metallic 0.3, which must survive everywhere outside chips
    minimal = copy.deepcopy(profile)
    for d in minimal["derivatives"].values():
        d["spec"] = {"half": d["spec"]["half"]} if d["builder"] == "paint" else {}
    _bsdf(bpy.data.materials["MAT_POWDERCOAT"]).inputs["Metallic"].default_value = 0.3
    BASES["MAT_POWDERCOAT"]["Metallic"] = (0.3,) * 3
    apply_profile(minimal)
    report["minimal"] = {}
    for oname, o in resolve_profile(minimal)["objects"].items():
        ob, m = bpy.data.objects[oname], bpy.data.materials[o["derivative"]]
        st = report["minimal"][oname] = {w: _stats(_bake(ob, m, w, 64), BASES[o["base"]][w]) for w in ("Roughness", "Metallic")}
        check(st["Roughness"]["masked"] > 0 and st["Roughness"]["masked_variance"] > 1e-9, f"minimal {oname}: roughness does not vary")
    check(report["minimal"]["Enclosure"]["Metallic"]["max_abs_diff"] <= 1e-5, "minimal paint: base Metallic 0.3 not kept")
    zero_check(minimal, "minimal_zero")
    report["pass"] = not fails
    report["failures"] = fails
    print(JSON_PREFIX + json.dumps(report, sort_keys=True), flush=True)
    return 1 if fails else 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    if bpy is None:
        print("run inside Blender: blender --background in.blend --python wear_library.py -- apply --profile p.json", file=sys.stderr)
        return 2
    try:
        if "--blender-test" in argv:
            return blender_test()
        args = parse_args(argv)
        out = save_target(args.save, bpy.data.filepath) if args.save else None   # refuse before touching anything
        summary = apply_profile(load_profile(args.profile), args.level)
        if out:
            bpy.ops.wm.save_as_mainfile(filepath=out, copy=True)
        summary["saved"] = out
        print(JSON_PREFIX + json.dumps(summary, sort_keys=True), flush=True)
        return 0
    except ProfileError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception:                                                          # Blender exits 0 on uncaught errors
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main(script_args(sys.argv)))
