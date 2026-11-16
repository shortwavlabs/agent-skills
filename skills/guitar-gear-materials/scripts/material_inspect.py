"""Read-only material report for guitar-gear .blend files (Blender) -> JSON.

Per material: top-level node types, Principled BSDF inputs (linked: from node:socket; unlinked: value), node groups
used (nested ones included) and the GG_WEAR_* ones among them, frame labels, and image textures with colour space,
source and state (packed / external / missing / generated). Per object with material slots or gg_* properties: each
slot's link (DATA / OBJECT), effective material and mesh-data material, and its gg_* custom properties. Missing
external files (images, libraries, fonts, sounds, movie clips, volumes, caches) are listed. The file is never modified.

  blender --background in.blend --python material_inspect.py -- [--out report.json]
  python3 material_inspect.py --self-test
  blender --background --factory-startup --python material_inspect.py -- --blender-test

Without --out the report is printed on one line prefixed with GUITAR_GEAR_MATERIALS_JSON=.
"""

import argparse
import contextlib
import io
import json
import os
import sys
import tempfile
import traceback
import uuid
from collections import Counter

try:
    import bpy
except ImportError:  # plain Python: helpers and --self-test only
    bpy = None

JSON_PREFIX = "GUITAR_GEAR_MATERIALS_JSON="
FILE_SOURCES = ("FILE", "SEQUENCE", "MOVIE", "TILED")
EXTERNAL = ("images", "libraries", "fonts", "sounds", "movieclips", "volumes", "cache_files")
IMAGE_NODES = ("ShaderNodeTexImage", "ShaderNodeTexEnvironment")


# ------------------------------------------------------------------------------------------- pure helpers
def json_value(v):
    """JSON-safe copy of a Blender value: floats rounded to 6 places, vectors / colours / ID arrays as lists."""
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        return round(v, 6)
    if hasattr(v, "to_dict"):
        v = v.to_dict()
    if isinstance(v, dict):
        return {str(k): json_value(x) for k, x in v.items()}
    try:
        return [json_value(x) for x in v]
    except TypeError:
        return str(v)


def tile_probe(path):
    """A concrete file to test for a UDIM / UV-tile pattern path (the first tile)."""
    return path.replace("<UDIM>", "1001").replace("<UVTILE>", "u1_v1")


def file_state(packed, path, exists, source="FILE"):
    """'packed', the lower-case source for non-file images ('generated', 'viewer'), else 'external' or 'missing'."""
    if packed:
        return "packed"
    if source not in FILE_SOURCES:
        return source.lower()
    return "external" if path and exists else "missing"


def parse_args(argv):
    p = argparse.ArgumentParser(prog="material_inspect.py", description="Read-only material report of the open .blend.")
    p.add_argument("--out", help="write the JSON report here (never the .blend); default: stdout with a prefix")
    return p.parse_args(argv)


def out_target(out, blend):
    path = os.path.abspath(out)
    if path.endswith((".blend", ".blend1")) or (blend and os.path.realpath(path) == os.path.realpath(blend)):
        raise ValueError(f"--out {out!r} would overwrite a .blend file; write the report to a .json path")
    return path


def script_args(argv, blender=bpy is not None):
    """Arguments meant for this script: those after '--' (none under Blender without '--'), else argv[1:]."""
    return argv[argv.index("--") + 1:] if "--" in argv else ([] if blender else argv[1:])


# ------------------------------------------------------------------------------------------- Blender report
def _trees(nt, seen):
    """nt and every node group nested in it, each once."""
    yield nt
    for n in nt.nodes:
        g = getattr(n, "node_tree", None)
        if g is not None and g.name not in seen:
            seen.add(g.name)
            yield from _trees(g, seen)


def _abspath(d):
    return bpy.path.abspath(d.filepath, library=d.library)


def _image(img):
    path = img.filepath
    exists = bool(path) and os.path.exists(tile_probe(_abspath(img)))
    return {"image": img.name, "colorspace": img.colorspace_settings.name, "source": img.source, "filepath": path,
            "state": file_state(img.packed_file is not None, path, exists, img.source)}


def _principled(n):
    linked, values = {}, {}
    for s in n.inputs:
        if not s.enabled:
            continue
        if s.is_linked:
            link = s.links[0]
            linked[s.name] = f"{link.from_node.name}:{link.from_socket.name}"
        elif hasattr(s, "default_value"):
            values[s.name] = json_value(s.default_value)
    return {"node": n.name, "linked": linked, "values": values}


def material_record(m):
    rec = {"name": m.name, "users": m.users, "library": m.library.name if m.library else None}
    if m.node_tree is None:
        return dict(rec, node_types={}, principled=[], groups=[], wear_groups=[], frames=[], images=[])
    trees = list(_trees(m.node_tree, set()))
    nodes = m.node_tree.nodes
    groups = sorted(t.name for t in trees[1:])
    return dict(rec,
                node_types=dict(sorted(Counter(n.bl_idname for n in nodes).items())),
                principled=[_principled(n) for n in nodes if n.bl_idname == "ShaderNodeBsdfPrincipled"],
                groups=groups, wear_groups=[g for g in groups if g.startswith("GG_WEAR_")],
                frames=sorted(n.label or n.name for n in nodes if n.bl_idname == "NodeFrame"),
                images=[dict(_image(n.image), node=n.name, tree=t.name if t is not m.node_tree else None) if n.image
                        else {"image": None, "node": n.name, "tree": t.name if t is not m.node_tree else None}
                        for t in trees for n in t.nodes if n.bl_idname in IMAGE_NODES])


def object_record(ob):
    data_mats = getattr(ob.data, "materials", None)
    slots = [{"index": i, "link": s.link, "material": s.material.name if s.material else None,
              "data_material": data_mats[i].name if data_mats is not None and i < len(data_mats) and data_mats[i] else None}
             for i, s in enumerate(ob.material_slots)]
    return {"name": ob.name, "type": ob.type, "slots": slots,
            "gg_props": {k: json_value(ob[k]) for k in sorted(ob.keys()) if k.startswith("gg_")}}


def missing_external():
    out = []
    for coll in EXTERNAL:
        for d in getattr(bpy.data, coll, ()):
            path = getattr(d, "filepath", "")
            if not path or path == "<builtin>" or getattr(d, "packed_file", None) is not None:
                continue
            if coll == "images" and d.source not in FILE_SOURCES:
                continue
            resolved = _abspath(d)
            if not os.path.exists(tile_probe(resolved)):
                out.append({"type": coll, "name": d.name, "filepath": path, "resolved": resolved})
    return out


def build_report():
    return {"file": bpy.data.filepath, "blender": bpy.app.version_string,
            "materials": [material_record(m) for m in bpy.data.materials],
            "objects": [object_record(o) for o in bpy.data.objects if len(o.material_slots) or any(k.startswith("gg_") for k in o.keys())],
            "missing_external": missing_external()}


def emit(report, out):
    if out:
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=1, sort_keys=True)
        print(f"wrote {out}")
    else:
        print(JSON_PREFIX + json.dumps(report, sort_keys=True), flush=True)


# ------------------------------------------------------------------------------------------- tests
def self_test():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    check(json_value(0.1234567891) == 0.123457, "float rounding")
    check(json_value((1.0, 0.5, 0.25, 1.0)) == [1.0, 0.5, 0.25, 1.0], "colour tuple")
    check(json_value({"a": (1.00000001, 2)}) == {"a": [1.0, 2]}, "nested dict")
    check(json_value(True) is True and json_value("x") == "x" and json_value(None) is None, "scalars")
    check(tile_probe("//tex.<UDIM>.png") == "//tex.1001.png" and tile_probe("t_<UVTILE>.exr") == "t_u1_v1.exr", "tile probe")
    check(file_state(True, "", False) == "packed", "packed wins")
    check(file_state(False, "//a.png", True) == "external", "external")
    check(file_state(False, "//a.png", False) == "missing" and file_state(False, "", False) == "missing", "missing")
    check(file_state(False, "", False, "GENERATED") == "generated", "generated")
    check(parse_args([]).out is None and parse_args(["--out", "r.json"]).out == "r.json", "parse --out")
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            parse_args(["--bogus"])
        fails.append("parse_args accepted --bogus")
    except SystemExit:
        pass
    blend = os.path.abspath("scene.blend")
    for out in ("scene.blend", "other.blend", "scene.blend1", blend):
        try:
            out_target(out, blend)
            fails.append(f"out_target accepted {out}")
        except ValueError:
            pass
    check(out_target("r.json", blend) == os.path.abspath("r.json"), "out_target json")
    check(script_args(["blender", "-b", "--python", "m.py", "--", "--out", "r.json"]) == ["--out", "r.json"], "args after --")
    check(script_args(["blender", "-b", "f.blend", "--python", "m.py"], blender=True) == [], "no script args under Blender")
    for f in fails:
        print("FAIL:", f)
    print(f"material_inspect self-test: {'PASS' if not fails else f'{len(fails)} FAILED'}")
    return 1 if fails else 0


def blender_test():
    """Tiny scene: nested GG_WEAR_* groups, a missing external image, a packed image, DATA and OBJECT slots, gg_* props."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    inner = bpy.data.node_groups.new("GG_WEAR_Inner", "ShaderNodeTree")
    outer = bpy.data.node_groups.new("GG_WEAR_Probe", "ShaderNodeTree")
    outer.interface.new_socket("Mask", in_out="OUTPUT", socket_type="NodeSocketFloat")
    outer.nodes.new("ShaderNodeGroup").node_tree = inner
    m = bpy.data.materials.new("MAT_TEST")
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.bl_idname == "ShaderNodeBsdfPrincipled")
    bsdf.inputs["Metallic"].default_value = 0.25
    g = nt.nodes.new("ShaderNodeGroup")
    g.node_tree = outer
    nt.links.new(g.outputs["Mask"], bsdf.inputs["Roughness"])
    missing = os.path.join(tempfile.gettempdir(), f"gg_missing_{uuid.uuid4().hex}.png")
    img = bpy.data.images.new("missing_tex", 4, 4)
    img.source, img.filepath = "FILE", missing
    img.colorspace_settings.name = "Non-Color"
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    packed = bpy.data.images.new("packed_tex", 4, 4)                         # saved, packed, then the file is deleted
    packed.filepath_raw, packed.file_format = missing.replace("missing", "packed"), "PNG"
    packed.save()
    packed.source = "FILE"
    packed.pack()
    os.remove(packed.filepath_raw)
    nt.nodes.new("ShaderNodeTexImage").image = packed
    nt.nodes.new("NodeFrame").label = "WEAR - test"
    base, obj_mat = bpy.data.materials.new("MAT_BASE"), bpy.data.materials.new("MAT_OBJ")
    ob = bpy.data.objects.new("Part", bpy.data.meshes.new("Part"))
    bpy.context.scene.collection.objects.link(ob)
    ob.data.materials.append(m)
    ob.data.materials.append(base)
    ob.material_slots[1].link = "OBJECT"
    ob.material_slots[1].material = obj_mat
    ob["gg_wear_seed"], ob["gg_lip_z"], ob["other"] = 3.5, 2.0, 1
    counts = {c: len(getattr(bpy.data, c)) for c in ("materials", "images", "node_groups", "objects", "meshes")}
    rep = build_report()
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    check({c: len(getattr(bpy.data, c)) for c in counts} == counts, "the report changed the data-block counts")
    mat = next(r for r in rep["materials"] if r["name"] == "MAT_TEST")
    check(mat["wear_groups"] == ["GG_WEAR_Inner", "GG_WEAR_Probe"], f"nested wear groups {mat['wear_groups']}")
    pr = mat["principled"][0]
    check(pr["linked"].get("Roughness") == f"{g.name}:Mask" and pr["linked"].get("Base Color") == f"{tex.name}:Color", f"linked {pr['linked']}")
    check(pr["values"].get("Metallic") == 0.25 and "Roughness" not in pr["values"], "unlinked values")
    imgs = {r["image"]: r for r in mat["images"]}
    check(imgs.get("missing_tex", {}).get("state") == "missing" and imgs["missing_tex"]["colorspace"] == "Non-Color", f"missing image {imgs}")
    check(imgs.get("packed_tex", {}).get("state") == "packed", "packed image")
    check(mat["frames"] == ["WEAR - test"] and mat["node_types"].get("ShaderNodeTexImage") == 2, "frames / node types")
    check([(d["type"], d["name"]) for d in rep["missing_external"]] == [("images", "missing_tex")], f"missing list {rep['missing_external']}")
    part = next(r for r in rep["objects"] if r["name"] == "Part")
    check([(s["link"], s["material"], s["data_material"]) for s in part["slots"]] ==
          [("DATA", "MAT_TEST", "MAT_TEST"), ("OBJECT", "MAT_OBJ", "MAT_BASE")], f"slots {part['slots']}")
    check(part["gg_props"] == {"gg_lip_z": 2.0, "gg_wear_seed": 3.5}, f"gg props {part['gg_props']}")
    out = os.path.join(tempfile.gettempdir(), f"gg_report_{uuid.uuid4().hex}.json")
    with contextlib.redirect_stdout(io.StringIO()):
        emit(rep, out)
    with open(out, encoding="utf-8") as fh:
        check(json.load(fh) == json.loads(json.dumps(rep)), "written report round-trips")
    os.remove(out)
    print(JSON_PREFIX + json.dumps({"pass": not fails, "failures": fails, "materials": len(rep["materials"]),
                                    "missing_external": rep["missing_external"]}, sort_keys=True), flush=True)
    return 1 if fails else 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    if bpy is None:
        print("run inside Blender: blender --background in.blend --python material_inspect.py -- [--out report.json]", file=sys.stderr)
        return 2
    try:
        if "--blender-test" in argv:
            return blender_test()
        args = parse_args(argv)
        emit(build_report(), out_target(args.out, bpy.data.filepath) if args.out else None)
        return 0
    except Exception:                                                          # Blender exits 0 on uncaught errors
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main(script_args(sys.argv)))
