#!/usr/bin/env python3
"""Validate a runtime GLB against a hand-written JSON contract, and compare two builds for reproducibility.

  glb_validate.py ASSET.glb --contract CONTRACT.json [--json OUT.json]
  glb_validate.py ASSET.glb --compare OTHER.glb [--json OUT.json]      (both options may be given together)
  glb_validate.py --self-test

The contract is a superset of the validation manifest in references/runtime-export.md, so that manifest loads unchanged.
Write its expected values by hand: values read back from the export under test validate nothing. Keys (all optional but root):
  root          name of the single scene root node
  nodes         [{"name", "parent", <extras key>: <expected value>, ...}]: semantic nodes; every key other than name and
                parent is an expected extras value (numbers within 1e-6, arrays element by element)
  hit_targets   [{"name", "parent", <extras key>: <expected value>, ...}]: must exist, be parented as listed, carry a mesh
  extras_types  {ui_type: {key: type}}: applied to every GLB node whose extras.ui_type matches; a type is "string" (non-empty),
                "number" (finite), "integer", "boolean", one of those + "[]" for an array of them, or a list of allowed values
  parameters    {id: {"type": "continuous" | "choice", "choices": [...]}}: every extras.parameter_id must be listed, and a
                choice_index must be an integer index into its parameter's choices
  materials     {"required": [exact names], "forbidden": [regular expressions, searched]}
  extensions    {"used": [allowed in extensionsUsed], "required": [allowed in extensionsRequired]}; default: none allowed
  images        {"power_of_two": bool, "mime_types": [allowed]}; images must be embedded (PNG, JPEG and KTX2 sizes are read)
  cameras, lights   true to allow exported cameras / KHR_lights_punctual (default false: presets and lights live in the page;
                allowing lights also needs KHR_lights_punctual in extensions.used)
Always checked: exactly one scene root, named as the contract says; no orphan, cyclic or multiply-parented node; unique node
and material names; finite node transforms and unit rotation quaternions; no Blender-suffixed copy of a contract name
(NAME.001); every extras.hit_target resolves to a listed hit target; every node with an extras.ui_type is in the contract;
state_angles and state_labels as long as state_count; embedded buffers only. Contract keys this script does not check (for
example camera_presets_file and expected_camera_presets) are reported as `unchecked_contract_keys`, never silently passed.

--compare: a repeat build of the same source must be byte-identical. Reports the SHA-256 of every top-level JSON section
(canonical form) and of every buffer view, which differ, the names of differing items (nodes, materials, ...), and what uses
each differing view (mesh attribute, indices, image). Any difference fails.

Exit 0 when every check passes, 1 when one fails, 2 on unreadable input or an invalid contract. Standard library only.
Ported from a product case study's validator, with its product constants (node set, pivots, material names, hashes) moved
into the contract; its geometric checks (pointer angles, pivots, bounds, degenerate triangles) are not ported: degenerate
triangles and normals are in normal_audit.py. The case study's repeat-build tool always exited 0; this one fails on difference.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import io
import json
import math
import re
import struct
import sys
import tempfile
import zlib
from collections import Counter
from pathlib import Path

SUFFIX = re.compile(r"(.+)\.\d{3,}")
KNOWN = {"schema_version", "description", "asset", "root", "nodes", "hit_targets", "extras_types", "parameters", "materials",
         "extensions", "images", "cameras", "lights"}
BASE_TYPES = ("string", "number", "integer", "boolean")


class InputError(ValueError):
    pass


def read_glb(path):
    data = Path(path).read_bytes()
    if len(data) < 20 or data[:4] != b"glTF":
        raise InputError(f"{path}: not a binary glTF (GLB) file")
    version, total = struct.unpack_from("<II", data, 4)
    length, kind = struct.unpack_from("<I4s", data, 12)
    if version != 2 or total != len(data) or kind != b"JSON":
        raise InputError(f"{path}: not a glTF 2.0 GLB with its JSON chunk first")
    g = json.loads(data[20:20 + length])
    off, binary = 20 + length, b""
    if off + 8 <= len(data):
        size, kind = struct.unpack_from("<I4s", data, off)
        if kind == b"BIN\0":
            binary = data[off + 8:off + 8 + size]
    return g, binary, hashlib.sha256(data).hexdigest()


def view_bytes(g, binary, index):
    v = g["bufferViews"][index]
    return binary[v.get("byteOffset", 0):v.get("byteOffset", 0) + v["byteLength"]]


def image_size(blob):
    """(width, height) of a PNG, JPEG or KTX2 image, or (0, 0)"""
    if blob[:8] == b"\x89PNG\r\n\x1a\n" and len(blob) >= 24:
        return struct.unpack_from(">II", blob, 16)
    if blob[:12] == b"\xabKTX 20\xbb\r\n\x1a\n" and len(blob) >= 28:
        return struct.unpack_from("<II", blob, 20)
    if blob[:2] == b"\xff\xd8":
        i = 2
        while i + 9 <= len(blob) and blob[i] == 0xFF:
            marker, size = blob[i + 1], struct.unpack_from(">H", blob, i + 2)[0]
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                h, w = struct.unpack_from(">HH", blob, i + 5)
                return w, h
            i += 2 + size
    return 0, 0


def number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def same(got, want):
    if isinstance(want, bool) or isinstance(got, bool):
        return got is want
    if number(want) and number(got):
        return math.isclose(got, want, rel_tol=0, abs_tol=1e-6)
    if isinstance(want, list):
        return isinstance(got, list) and len(got) == len(want) and all(same(a, b) for a, b in zip(got, want))
    return got == want


def type_ok(value, spec):
    if isinstance(spec, list):
        return any(same(value, s) for s in spec)
    if spec.endswith("[]"):
        return isinstance(value, list) and all(type_ok(v, spec[:-2]) for v in value)
    return {"string": lambda v: isinstance(v, str) and v != "",
            "number": number,
            "integer": lambda v: number(v) and float(v).is_integer(),
            "boolean": lambda v: isinstance(v, bool)}[spec](value)


def check_contract(c):
    if not isinstance(c, dict) or not isinstance(c.get("root"), str):
        raise InputError("contract: a JSON object with a string `root` is required")
    for key in ("nodes", "hit_targets"):
        if not all(isinstance(e, dict) and isinstance(e.get("name"), str) for e in c.get(key, [])):
            raise InputError(f"contract: every {key} entry needs a string `name`")
    for ui, fields in c.get("extras_types", {}).items():
        for key, spec in fields.items():
            if not isinstance(spec, list) and (not isinstance(spec, str) or spec.rstrip("[]") not in BASE_TYPES):
                raise InputError(f"contract: extras_types.{ui}.{key}: unknown type {spec!r}")
    for pattern in c.get("materials", {}).get("forbidden", []):
        re.compile(pattern)


def validate(g, binary, c):
    """failures (list of strings) and a summary of what was found"""
    fails = []
    fail = fails.append
    nodes = g.get("nodes", [])
    names = [n.get("name", "") for n in nodes]
    index = {}
    for i, name in enumerate(names):
        index.setdefault(name, i)
    fails += [f"duplicate node name {n!r} ({k} nodes)" for n, k in Counter(names).items() if k > 1]

    # hierarchy: one root, no orphan / cycle / second parent
    parent = {}
    for i, n in enumerate(nodes):
        for ch in n.get("children", []):
            if ch in parent:
                fail(f"node {names[ch]!r} has more than one parent")
            parent[ch] = i
    scenes = g.get("scenes", [])
    roots = scenes[g.get("scene", 0)].get("nodes", []) if scenes else []
    if len(roots) != 1:
        fail(f"the scene has {len(roots)} root nodes; exactly one ({c['root']!r}) is required")
    elif names[roots[0]] != c["root"]:
        fail(f"the scene root is {names[roots[0]]!r}, expected {c['root']!r}")
    seen, stack = set(), list(roots)
    while stack:
        i = stack.pop()
        if i in seen:
            fail(f"node {names[i]!r} is reached twice (cycle or second parent)")
            continue
        seen.add(i)
        stack.extend(nodes[i].get("children", []))
    orphans = [names[i] for i in range(len(nodes)) if i not in seen]
    if orphans:
        fail(f"{len(orphans)} nodes are not under the scene root: {orphans[:10]}")
    for i, n in enumerate(nodes):
        values = [v for key in ("matrix", "translation", "rotation", "scale") for v in n.get(key, [])]
        if not all(number(v) for v in values):
            fail(f"node {names[i]!r}: non-finite transform")
        elif "rotation" in n and abs(math.sqrt(sum(v * v for v in n["rotation"])) - 1) > 1e-3:
            fail(f"node {names[i]!r}: rotation quaternion is not unit length")

    # contract nodes and hit targets
    entries = [("node", e) for e in c.get("nodes", [])] + [("hit target", e) for e in c.get("hit_targets", [])]
    contract_names = {c["root"]} | {e["name"] for _, e in entries}
    hit_names = {e["name"] for e in c.get("hit_targets", [])}
    for name in names:
        m = SUFFIX.fullmatch(name)
        if m and m.group(1) in contract_names:
            fail(f"{name!r} is a Blender-suffixed copy of contract name {m.group(1)!r}")
    for kind, e in entries:
        name = e["name"]
        if name not in index:
            fail(f"{kind} {name!r} is missing")
            continue
        i = index[name]
        extras = nodes[i].get("extras") or {}
        got = names[parent[i]] if i in parent else None
        if "parent" in e and got != e["parent"]:
            fail(f"{kind} {name!r}: parent {got!r}, expected {e['parent']!r}")
        for key, want in e.items():
            if key in ("name", "parent"):
                continue
            if key not in extras:
                fail(f"{kind} {name!r}: extras.{key} is missing")
            elif not same(extras[key], want):
                fail(f"{kind} {name!r}: extras.{key} = {extras[key]!r}, expected {want!r}")
        if kind == "hit target" and "mesh" not in nodes[i]:
            fail(f"hit target {name!r} has no mesh to raycast")

    # extras on every semantic node in the file
    schema, params = c.get("extras_types", {}), c.get("parameters")
    for i, n in enumerate(nodes):
        extras = n.get("extras")
        if not isinstance(extras, dict) or "ui_type" not in extras:
            continue
        name, ui = names[i], extras["ui_type"]
        if name not in contract_names:
            fail(f"node {name!r} has ui_type {ui!r} but is not in the contract")
        for key, spec in schema.get(ui, {}).items():
            if key not in extras:
                fail(f"{name!r} ({ui}): extras.{key} is missing")
            elif not type_ok(extras[key], spec):
                fail(f"{name!r} ({ui}): extras.{key} = {extras[key]!r} is not {spec}")
        if "state_count" in extras:
            for key in ("state_angles", "state_labels"):
                if key in extras and (not isinstance(extras[key], list) or len(extras[key]) != extras["state_count"]):
                    fail(f"{name!r}: {key} does not have state_count = {extras['state_count']!r} entries")
        target = extras.get("hit_target")
        if target is not None and (target not in index or (hit_names and target not in hit_names)):
            fail(f"{name!r}: hit_target {target!r} does not resolve to a listed hit target")
        pid = extras.get("parameter_id")
        if params is not None and pid is not None:
            if pid not in params:
                fail(f"{name!r}: parameter_id {pid!r} is not a contract parameter")
            elif "choice_index" in extras:
                choices = params[pid].get("choices") or []
                ci = extras["choice_index"]
                if params[pid].get("type") != "choice" or not type_ok(ci, "integer") or not 0 <= ci < len(choices):
                    fail(f"{name!r}: choice_index {ci!r} is not an index into {pid!r} choices {choices}")

    # materials, extensions, buffers, images, cameras, lights
    mats = [m.get("name", "") for m in g.get("materials", [])]
    fails += [f"duplicate material name {n!r}" for n, k in Counter(mats).items() if k > 1]
    spec = c.get("materials", {})
    fails += [f"required material {n!r} is missing" for n in spec.get("required", []) if n not in mats]
    fails += [f"material {m!r} matches forbidden pattern {p!r}" for p in spec.get("forbidden", []) for m in mats if re.search(p, m)]
    allowed = c.get("extensions", {})
    for key, field in (("used", "extensionsUsed"), ("required", "extensionsRequired")):
        extra = sorted(set(g.get(field, [])) - set(allowed.get(key, [])))
        if extra:
            fail(f"{field} contains {extra}, not allowed by the contract")
    if any("uri" in b for b in g.get("buffers", [])):
        fail("a buffer is external (uri); the runtime loads one self-contained GLB")
    images, ispec = [], c.get("images", {})
    for k, im in enumerate(g.get("images", [])):
        label = im.get("name", f"image {k}")
        if "uri" in im or "bufferView" not in im:
            fail(f"image {label!r} is not embedded")
            continue
        if ispec.get("mime_types") and im.get("mimeType") not in ispec["mime_types"]:
            fail(f"image {label!r}: mimeType {im.get('mimeType')!r} not allowed")
        w, h = image_size(view_bytes(g, binary, im["bufferView"]))
        images.append(dict(name=label, mime=im.get("mimeType"), width=w, height=h))
        if ispec.get("power_of_two") and (not w or not h or w & (w - 1) or h & (h - 1)):
            fail(f"image {label!r} is {w} x {h}, not a power of two" if w else f"image {label!r}: size unreadable")
    if not c.get("cameras", False) and (g.get("cameras") or any("camera" in n for n in nodes)):
        fail("cameras are exported; the contract does not allow them")
    lights = "KHR_lights_punctual" in set(g.get("extensionsUsed", [])) | set(g.get("extensions") or {})
    if not c.get("lights", False) and lights:
        fail("KHR_lights_punctual lights are exported; the contract does not allow them")
    found = dict(nodes=len(nodes), semantic_nodes=sorted(n for n in contract_names if n in index), materials=sorted(mats),
                 images=images, extensions_used=g.get("extensionsUsed", []), extensions_required=g.get("extensionsRequired", []),
                 unchecked_contract_keys=sorted(set(c) - KNOWN))
    return fails, found


# ----------------------------------------------------------------- repeat-build comparison
def canon(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def view_users(g):
    use = {}
    for m in g.get("meshes", []):
        for pr in m.get("primitives", []):
            for attr, acc in list(pr.get("attributes", {}).items()) + ([("indices", pr["indices"])] if "indices" in pr else []):
                view = g["accessors"][acc].get("bufferView")
                use.setdefault(view, set()).add(f"{m.get('name', '?')} {attr}")
    for im in g.get("images", []):
        if "bufferView" in im:
            use.setdefault(im["bufferView"], set()).add(f"image {im.get('name', '?')}")
    return use


def compare(path_a, path_b):
    ga, ba, sa = read_glb(path_a)
    gb, bb, sb = read_glb(path_b)
    sections = {k: [canon(ga.get(k)), canon(gb.get(k))] for k in sorted(set(ga) | set(gb))}
    differing = [k for k, (x, y) in sections.items() if x != y]
    items = {}
    for k in differing:
        la, lb = ga.get(k), gb.get(k)
        if isinstance(la, list) and isinstance(lb, list) and len(la) == len(lb):
            items[k] = [x.get("name", i) if isinstance(x, dict) else i for i, (x, y) in enumerate(zip(la, lb)) if canon(x) != canon(y)]
    va = [hashlib.sha256(view_bytes(ga, ba, i)).hexdigest() for i in range(len(ga.get("bufferViews", [])))]
    vb = [hashlib.sha256(view_bytes(gb, bb, i)).hexdigest() for i in range(len(gb.get("bufferViews", [])))]
    use = view_users(ga)
    views = None if len(va) != len(vb) else [dict(index=i, used_by=sorted(use.get(i, {"unreferenced"})))
                                              for i in range(len(va)) if va[i] != vb[i]]
    return dict(a=dict(file=str(path_a), sha256=sa), b=dict(file=str(path_b), sha256=sb), files_identical=sa == sb,
                json_sections_differing=differing, json_items_differing=items, binary_chunk_identical=ba == bb,
                buffer_views=[len(va), len(vb)], buffer_views_differing=views,
                identical=not differing and views == [] and ba == bb,
                json_section_sha256=sections, buffer_view_sha256=[va, vb])


# ----------------------------------------------------------------- self-test
CONTRACT = {
    "root": "GEAR_ROOT",
    "parameters": {"gain": {"type": "continuous"}, "boost": {"type": "choice", "choices": ["Off", "On"]},
                   "inputMode": {"type": "choice", "choices": ["Regular", "High"]}},
    "extras_types": {"knob": {"parameter_id": "string", "rotation_axis": ["X", "Y", "Z"], "rotation_sign": [-1, 1],
                              "min_angle": "number", "max_angle": "number", "rest_angle": "number", "hit_target": "string"},
                     "toggle": {"state_count": "integer", "state_angles": "number[]", "state_labels": "string[]"},
                     "input": {"choice_index": "integer"}},
    "nodes": [{"name": "CTRL_GAIN", "parent": "GEAR_ROOT", "ui_type": "knob", "parameter_id": "gain", "min_angle": -135,
               "max_angle": 135, "rest_angle": 0, "hit_target": "HIT_GAIN"},
              {"name": "SWITCH_BOOST", "parent": "GEAR_ROOT", "ui_type": "toggle", "parameter_id": "boost", "hit_target": "HIT_BOOST"},
              {"name": "INPUT_REGULAR", "parent": "GEAR_ROOT", "choice_index": 0},
              {"name": "INPUT_HIGH", "parent": "GEAR_ROOT", "choice_index": 1}],
    "hit_targets": [{"name": "HIT_GAIN", "parent": "CTRL_GAIN"}, {"name": "HIT_BOOST", "parent": "SWITCH_BOOST"},
                    {"name": "HIT_INPUT_REGULAR", "parent": "INPUT_REGULAR"}, {"name": "HIT_INPUT_HIGH", "parent": "INPUT_HIGH"}],
    "materials": {"required": ["HIT_INVISIBLE"], "forbidden": [r"^Material(\.\d+)?$"]},
    "extensions": {"used": ["KHR_materials_emissive_strength"]},
    "images": {"power_of_two": True, "mime_types": ["image/png"]},
}


def png_header(w, h):
    body = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + body + struct.pack(">I", zlib.crc32(b"IHDR" + body))


def fixture(width=4):
    """a GLB (as a glTF dict and binary) that satisfies CONTRACT and the shipped example contract"""
    binary = struct.pack("<9f", 0, 0, 0, 0.01, 0, 0, 0, 0, 0.01) + struct.pack("<3H", 0, 1, 2) + b"\0\0" + png_header(width, 4)

    def control(name, extras, hit):
        return [dict(name=name, children=[], extras=extras), dict(name=hit, mesh=0, extras=dict(ui_type="hit_target", control_node=name))]
    controls = (control("CTRL_GAIN", dict(ui_type="knob", parameter_id="gain", rotation_axis="Y", rotation_sign=-1, min_angle=-135.0,
                                          max_angle=135.0, rest_angle=0.0, hit_target="HIT_GAIN"), "HIT_GAIN")
                + control("SWITCH_BOOST", dict(ui_type="toggle", parameter_id="boost", rotation_axis="Z", rotation_sign=-1, state_count=2,
                                               state_angles=[-16.0, 16.0], state_labels=["Off", "On"], rest_angle=-16.0,
                                               hit_target="HIT_BOOST"), "HIT_BOOST")
                + control("INPUT_REGULAR", dict(ui_type="input", parameter_id="inputMode", choice_index=0,
                                                hit_target="HIT_INPUT_REGULAR"), "HIT_INPUT_REGULAR")
                + control("INPUT_HIGH", dict(ui_type="input", parameter_id="inputMode", choice_index=1,
                                             hit_target="HIT_INPUT_HIGH"), "HIT_INPUT_HIGH"))
    nodes = [dict(name="GEAR_ROOT", children=[1, 2, 4, 6, 8]), dict(name="GEAR_STATIC", mesh=0)] + controls
    for k in (2, 4, 6, 8):
        nodes[k]["children"] = [k + 1]
    nodes[2]["translation"] = [0.01, 0.02, 0.0]
    nodes[4]["rotation"] = [0.0, 0.0, -0.13917310096006544, 0.9902680687415704]
    g = dict(asset=dict(version="2.0"), scene=0, scenes=[dict(nodes=[0])], nodes=nodes,
             meshes=[dict(name="TRI", primitives=[dict(attributes=dict(POSITION=0), indices=1, material=0)])],
             materials=[dict(name="PBR_Body", pbrMetallicRoughness=dict(baseColorTexture=dict(index=0))), dict(name="HIT_INVISIBLE")],
             textures=[dict(source=0)], images=[dict(name="body_basecolor", mimeType="image/png", bufferView=2)],
             accessors=[dict(bufferView=0, componentType=5126, count=3, type="VEC3", min=[0, 0, 0], max=[0.01, 0, 0.01]),
                        dict(bufferView=1, componentType=5123, count=3, type="SCALAR")],
             bufferViews=[dict(buffer=0, byteOffset=0, byteLength=36), dict(buffer=0, byteOffset=36, byteLength=6),
                          dict(buffer=0, byteOffset=44, byteLength=len(binary) - 44)],
             buffers=[dict(byteLength=len(binary))], extensionsUsed=["KHR_materials_emissive_strength"])
    return g, binary


def pack(g, binary):
    js = json.dumps(g).encode()
    js += b" " * (-len(js) % 4)
    binary += bytes(-len(binary) % 4)
    return (struct.pack("<4sII", b"glTF", 2, 28 + len(js) + len(binary)) + struct.pack("<I4s", len(js), b"JSON") + js
            + struct.pack("<I4s", len(binary), b"BIN\0") + binary)


def self_test():
    problems = []
    base, binary = fixture()
    fails, _ = validate(base, binary, CONTRACT)
    if fails:
        problems.append(f"baseline fixture fails: {fails}")
    example = Path(__file__).resolve().parent.parent / "examples" / "glb_contract.example.json"
    if example.is_file():
        contract = json.loads(example.read_text())
        check_contract(contract)
        fails, found = validate(base, binary, contract)
        if fails or found["unchecked_contract_keys"]:
            problems.append(f"shipped example contract: {fails} {found['unchecked_contract_keys']}")

    def node(g, name):
        return next(n for n in g["nodes"] if n["name"] == name)

    def mutate(label, change, expect, bin_=None, width=4):
        g, b = fixture(width)
        change(g)
        fails, _ = validate(g, bin_ or b, CONTRACT)
        if not any(expect in f for f in fails):
            problems.append(f"{label}: expected a failure containing {expect!r}, got {fails}")
    mutate("suffix", lambda g: node(g, "CTRL_GAIN").update(name="CTRL_GAIN.001"), "Blender-suffixed copy")
    mutate("missing", lambda g: node(g, "CTRL_GAIN").update(name="CTRL_GAIN.001"), "node 'CTRL_GAIN' is missing")
    mutate("duplicate", lambda g: node(g, "GEAR_STATIC").update(name="HIT_GAIN"), "duplicate node name 'HIT_GAIN'")
    mutate("non-finite", lambda g: node(g, "CTRL_GAIN").update(translation=[0, math.nan, 0]), "non-finite transform")
    mutate("quaternion", lambda g: node(g, "SWITCH_BOOST").update(rotation=[0, 0, 0.5, 0.5]), "not unit length")
    mutate("parent", lambda g: (node(g, "CTRL_GAIN")["children"].remove(3), node(g, "GEAR_ROOT")["children"].append(3)),
           "hit target 'HIT_GAIN': parent 'GEAR_ROOT'")
    mutate("value", lambda g: node(g, "CTRL_GAIN")["extras"].update(max_angle=150), "extras.max_angle = 150")
    mutate("type", lambda g: node(g, "CTRL_GAIN")["extras"].update(min_angle="-135"), "extras.min_angle = '-135' is not number")
    mutate("axis", lambda g: node(g, "CTRL_GAIN")["extras"].update(rotation_axis="W"), "extras.rotation_axis = 'W'")
    mutate("states", lambda g: node(g, "SWITCH_BOOST")["extras"].update(state_angles=[-16, 0, 16]), "state_angles does not have")
    mutate("choice", lambda g: node(g, "INPUT_HIGH")["extras"].update(choice_index=2), "choice_index 2 is not an index")
    mutate("parameter", lambda g: node(g, "CTRL_GAIN")["extras"].update(parameter_id="drive"), "not a contract parameter")
    mutate("stray", lambda g: node(g, "GEAR_STATIC").update(extras=dict(ui_type="knob")), "is not in the contract")
    mutate("hit ref", lambda g: node(g, "CTRL_GAIN")["extras"].update(hit_target="HIT_NOPE"), "does not resolve")
    mutate("hit mesh", lambda g: node(g, "HIT_GAIN").pop("mesh"), "has no mesh to raycast")
    mutate("two roots", lambda g: g["scenes"][0]["nodes"].append(1), "2 root nodes")
    mutate("orphan", lambda g: g["nodes"].append(dict(name="LOOSE")), "not under the scene root")
    mutate("material", lambda g: g["materials"].append(dict(name="Material.001")), "forbidden pattern")
    mutate("required material", lambda g: g["materials"].pop(), "'HIT_INVISIBLE' is missing")
    mutate("extension", lambda g: g.update(extensionsRequired=["KHR_draco_mesh_compression"]), "extensionsRequired contains")
    mutate("camera", lambda g: g.update(cameras=[dict(type="perspective")]), "cameras are exported")
    mutate("light", lambda g: g.update(extensionsUsed=["KHR_lights_punctual"]), "lights are exported")
    mutate("pot", lambda g: None, "3 x 4, not a power of two", width=3)

    with tempfile.TemporaryDirectory() as tmp:
        a, b, c = (Path(tmp) / n for n in ("a.glb", "b.glb", "c.glb"))
        a.write_bytes(pack(base, binary))
        b.write_bytes(pack(base, binary))
        r = compare(a, b)
        if not (r["identical"] and r["files_identical"]):
            problems.append(f"compare: identical builds reported different: {r['json_sections_differing']}")
        g2 = copy.deepcopy(base)
        node(g2, "SWITCH_BOOST")["extras"]["rest_angle"] = 16.0
        c.write_bytes(pack(g2, binary[:12] + struct.pack("<f", 0.02) + binary[16:]))
        r = compare(a, c)
        if r["identical"] or r["json_items_differing"].get("nodes") != ["SWITCH_BOOST"] or \
                [v["used_by"] for v in r["buffer_views_differing"]] != [["TRI POSITION"]]:
            problems.append(f"compare: {r['json_items_differing']} {r['buffer_views_differing']}")
        contract = Path(tmp) / "contract.json"
        contract.write_text(json.dumps(CONTRACT))
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            codes = (main([str(a), "--contract", str(contract)]), main([str(a), "--compare", str(c)]),
                     main([str(c), "--contract", str(contract), "--compare", str(b), "--json", str(Path(tmp) / "r.json")]))
            contract.write_text(json.dumps(dict(CONTRACT, extras_types={"knob": {"min_angle": "float"}})))
            codes += (main([str(a), "--contract", str(contract)]),)
        if codes != (0, 1, 1, 2) or json.loads((Path(tmp) / "r.json").read_text())["passed"]:
            problems.append(f"CLI exit codes {codes} (expected pass, differ, fail, invalid contract)")
    for p in problems:
        print("FAIL:", p)
    print("self-test:", "PASS" if not problems else f"{len(problems)} FAILED")
    return 1 if problems else 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--self-test" in argv:
        return self_test()
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("asset", type=Path)
    ap.add_argument("--contract", type=Path, help="JSON contract to validate against")
    ap.add_argument("--compare", type=Path, metavar="OTHER.glb", help="a repeat build that must be identical")
    ap.add_argument("--json", type=Path, help="write the report here")
    a = ap.parse_args(argv)
    if not (a.contract or a.compare):
        ap.error("give --contract, --compare or both")
    report, failures = dict(asset=str(a.asset)), []
    try:
        if a.contract:
            contract = json.loads(a.contract.read_text())
            check_contract(contract)
            g, binary, sha = read_glb(a.asset)
            fails, found = validate(g, binary, contract)
            report.update(sha256=sha, contract=str(a.contract), contract_failures=fails, **found)
            failures += fails
            for key in found["unchecked_contract_keys"]:
                print(f"NOTE: contract key {key!r} is not checked by this script")
        if a.compare:
            r = compare(a.asset, a.compare)
            report["compare"] = r
            if not r["identical"]:
                failures.append(f"repeat build differs: JSON sections {r['json_sections_differing']}, items "
                                f"{r['json_items_differing']}, buffer views {r['buffer_views_differing']}")
    except (InputError, OSError, KeyError, IndexError, TypeError, json.JSONDecodeError, re.error) as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    report.update(failures=failures, passed=not failures)
    for f in failures:
        print("FAIL:", f)
    print("GLB_VALIDATE", "PASS" if not failures else f"FAIL ({len(failures)})")
    if a.json:
        a.json.write_text(json.dumps(report, indent=1) + "\n")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
