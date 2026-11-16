"""Bake Blender materials into glTF PBR maps: base colour, ORM (R = AO, G = roughness, B = metallic) and tangent-space normal.

    blender --background <file.blend> --python-exit-code 1 --python pbr_bake.py -- --config bake.json --out <dir>
    python3 pbr_bake.py --self-test
    blender --background --factory-startup --python pbr_bake.py -- --blender-test <scratch dir>

Each family (a list of objects sharing one UV atlas) is baked in place, object by object, from its own materials,
without studio light:
  base_color  Principled Base Color through a temporary emission node, sRGB
  rm_raw      R = 1, G = Roughness, B = Metallic through a temporary emission node, Non-Color
  ao_raw      an Ambient Occlusion node (distance, samples) through a temporary emission node, Non-Color; the objects in
              `hide_during_ao` (a studio floor) and every `normal_from` source are hidden from render meanwhile
  orm         a new image: R from ao_raw, G and B from rm_raw; the raw bakes are not modified
  normal      tangent space; `normal_from` maps a target to a detailed source baked selected-to-active (cage, ray)
A family of several objects gets a second pass at margin 0 (repair_margin_overlap): Blender bakes object by object, and
a later object's margin overwrites an earlier object's edge texels. Every material on a baked object must have its
active Material Output's Surface linked straight from a Principled BSDF. The temporary nodes and links are removed
afterwards and the .blend is never saved. UVs are reported before baking (missing layer = error; zero-area faces,
coordinates outside 0..1 and an overlap estimate are warnings). Each family's cache key hashes the .blend, Blender,
the device, the settings, the image sizes and its UVs; a family whose key and output hashes match
bake_provenance.json in the output directory is skipped.
Defaults follow two products' validated bakes: Cycles, 16 samples, seed 12, 8-texel margin, no denoiser, 8-bit PNG
(RGBA here; color_mode "RGB" matches the files those products actually wrote).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import struct
import sys
from array import array
from contextlib import contextmanager
from pathlib import Path

SCHEMA = 1
MAPS = ("base_color", "orm", "normal")
GLOBAL_DEFAULTS = {"maps": list(MAPS), "samples": 16, "seed": 12, "margin_px": 8, "ao_samples": 16, "device": "GPU",
                   "threads": 0, "color_mode": "RGBA", "uv_layer": None, "hide_during_ao": [], "repair_margin_overlap": True}
FAMILY_DEFAULTS = {"objects": [], "sizes": {m: [1024, 1024] for m in MAPS}, "ao_distance_m": 0.004, "normal_from": {},
                   "cage_extrusion_m": 0.0004, "max_ray_distance_m": 0.0009, "normal_from_samples": None}
CHANNELS = {  # file channel: (size key, colour space, fill colour for texels no face covers)
    "base_color": ("base_color", "sRGB", (0.5, 0.5, 0.5, 1.0)),
    "rm_raw": ("orm", "Non-Color", (1.0, 0.5, 0.0, 1.0)),
    "ao_raw": ("orm", "Non-Color", (1.0, 1.0, 1.0, 1.0)),
    "orm": ("orm", "Non-Color", None),
    "normal": ("normal", "Non-Color", (0.5, 0.5, 1.0, 1.0)),
}
ZERO_UV_AREA = 1e-12      # UV units squared: a face this small has no texels and no defined tangent
UV_GRID = 256             # overlap estimate: texel centres of a 256 x 256 grid
PROVENANCE = "bake_provenance.json"
GPU_BACKENDS = ("METAL", "OPTIX", "CUDA", "HIP", "ONEAPI")


class ConfigError(ValueError):
    pass


class BakeError(RuntimeError):
    pass


# ---------------------------------------------------------------- plain Python: config, cache key, packing, UV report

def _int(v, lo, hi):
    return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def _num(v, lo, hi):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and lo <= v <= hi


def _names(v):
    return isinstance(v, list) and all(isinstance(n, str) and n for n in v) and len(set(v)) == len(v)


GLOBAL_CHECKS = {
    "maps": (lambda v: _names(v) and v and set(v) <= set(MAPS), f"a non-empty list from {list(MAPS)}"),
    "samples": (lambda v: _int(v, 1, 65536), "an integer 1..65536"),
    "seed": (lambda v: _int(v, 0, 2**31 - 1), "an integer >= 0"),
    "margin_px": (lambda v: _int(v, 0, 64), "an integer 0..64"),
    "ao_samples": (lambda v: _int(v, 1, 128), "an integer 1..128"),
    "device": (lambda v: v in ("CPU", "GPU"), '"CPU" or "GPU"'),
    "threads": (lambda v: _int(v, 0, 1024), "an integer >= 0 (0 = automatic)"),
    "color_mode": (lambda v: v in ("RGB", "RGBA"), '"RGB" or "RGBA"'),
    "uv_layer": (lambda v: v is None or (isinstance(v, str) and v), "null (each object's active UV map) or a name"),
    "hide_during_ao": (_names, "a list of distinct object names"),
    "repair_margin_overlap": (lambda v: isinstance(v, bool), "true or false"),
}
FAMILY_CHECKS = {
    "objects": (lambda v: _names(v) and v, "a non-empty list of distinct object names"),
    "sizes": (lambda v: isinstance(v, dict) and set(v) <= set(MAPS) and all(
        isinstance(s, list) and len(s) == 2 and all(_int(x, 1, 16384) for x in s) for s in v.values()),
        f"an object of {list(MAPS)} -> [width, height], 1..16384"),
    "ao_distance_m": (lambda v: _num(v, 1e-9, 100), "a distance in metres > 0"),
    "normal_from": (lambda v: isinstance(v, dict) and all(isinstance(x, str) and x for x in v.values()),
                    "an object of target name -> detailed source name"),
    "cage_extrusion_m": (lambda v: _num(v, 0, 100), "a distance in metres >= 0"),
    "max_ray_distance_m": (lambda v: _num(v, 0, 100), "a distance in metres >= 0 (0 = unlimited)"),
    "normal_from_samples": (lambda v: v is None or _int(v, 1, 65536), "null (use samples) or an integer >= 1"),
}


def _merge(data, defaults, checks, where, errors):
    out = json.loads(json.dumps(defaults))
    for key, value in data.items():
        if key not in checks:
            errors.append(f"{where}: unknown key {key!r}")
        elif not checks[key][0](value):
            errors.append(f"{where}: {key} must be {checks[key][1]}, got {value!r}")
        elif key == "sizes":
            out[key].update(value)
        else:
            out[key] = value
    return out


def validate_config(data) -> dict:
    """The normalised config (defaults filled, units as floats, order-free lists sorted), or ConfigError listing every problem."""
    if not isinstance(data, dict):
        raise ConfigError("config: must be a JSON object")
    errors = []
    cfg = _merge({k: v for k, v in data.items() if k != "families"}, GLOBAL_DEFAULTS, GLOBAL_CHECKS, "config", errors)
    families = data.get("families")
    if not isinstance(families, dict) or not families:
        errors.append("config: families must be a non-empty object of family name -> settings")
        families = {}
    cfg["families"], owner = {}, {}
    for name, fam in families.items():
        where = f"families.{name}"
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", name):
            errors.append(f"{where}: family names become file names: use letters, digits, '_', '.', '-'")
        if not isinstance(fam, dict) or "objects" not in fam:
            errors.append(f"{where}: must be an object with an 'objects' list")
            continue
        fam = _merge(fam, FAMILY_DEFAULTS, FAMILY_CHECKS, where, errors)
        for key in ("ao_distance_m", "cage_extrusion_m", "max_ray_distance_m"):
            fam[key] = float(fam[key]) if _num(fam[key], 0, 100) else fam[key]
        for obj in fam["objects"] if isinstance(fam["objects"], list) else []:
            if obj in owner:
                errors.append(f"{where}: {obj!r} is already in family {owner[obj]!r}")
            owner[obj] = name
        cfg["families"][name] = fam
    for name, fam in cfg["families"].items():
        for target, source in fam["normal_from"].items() if isinstance(fam["normal_from"], dict) else []:
            if target not in fam["objects"]:
                errors.append(f"families.{name}.normal_from: target {target!r} is not one of this family's objects")
            if source in owner:
                errors.append(f"families.{name}.normal_from: source {source!r} is itself baked (family {owner[source]!r})")
    for obj in cfg["hide_during_ao"] if isinstance(cfg["hide_during_ao"], list) else []:
        if obj in owner:
            errors.append(f"config: hide_during_ao lists {obj!r}, which is baked (family {owner[obj]!r})")
    if errors:
        raise ConfigError("\n".join(errors))
    cfg["maps"] = [m for m in MAPS if m in cfg["maps"]]
    cfg["hide_during_ao"] = sorted(cfg["hide_during_ao"])
    return cfg


def cache_key(cfg: dict, family: str, blend_sha256: str, uv_sha256: str, blender: str, device: str) -> str:
    """SHA-256 of everything a family's bake depends on: the .blend, Blender, the device, the settings, its sizes and UVs."""
    payload = dict(schema=SCHEMA, blend_sha256=blend_sha256, blender=blender, device=device, uv_sha256=uv_sha256,
                   settings={k: v for k, v in cfg.items() if k != "families"}, family=cfg["families"][family])
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def pack_orm(ao, rm):
    """glTF occlusion/roughness/metallic = R/G/B: a new RGBA buffer (list or array) with AO's R over the rough/metal bake."""
    if len(ao) != len(rm) or len(rm) % 4:
        raise ValueError(f"AO and roughness/metallic buffers differ ({len(ao)} vs {len(rm)} values) or are not RGBA")
    out = rm[:]
    out[0::4] = ao[0::4]
    return out


def _inside(face, x, y):
    hit = False
    for (u0, v0), (u1, v1) in zip(face, face[1:] + face[:1]):
        if (v0 > y) != (v1 > y) and x < u0 + (y - v0) * (u1 - u0) / (v1 - v0):
            hit = not hit
    return hit


def uv_report(faces, grid=UV_GRID) -> dict:
    """Counts for a family's UV faces (lists of (u, v)): zero-area faces, loops outside 0..1, and the share of covered
    grid texel centres that more than one face covers (an estimate: faces smaller than a grid texel are not seen)."""
    cover, zero, outside, loops, count = {}, 0, 0, 0, 0
    for face in faces:
        face = list(face)
        count += 1
        loops += len(face)
        outside += sum(1 for u, v in face if not (0.0 <= u <= 1.0 and 0.0 <= v <= 1.0))
        area = 0.5 * abs(sum(u0 * v1 - u1 * v0 for (u0, v0), (u1, v1) in zip(face, face[1:] + face[:1])))
        if area < ZERO_UV_AREA:
            zero += 1
            continue
        us, vs = [u for u, _ in face], [v for _, v in face]
        for i in range(max(0, math.ceil(min(us) * grid - 0.5)), min(grid - 1, math.floor(max(us) * grid - 0.5)) + 1):
            for j in range(max(0, math.ceil(min(vs) * grid - 0.5)), min(grid - 1, math.floor(max(vs) * grid - 0.5)) + 1):
                if _inside(face, (i + 0.5) / grid, (j + 0.5) / grid):
                    cover[i, j] = cover.get((i, j), 0) + 1
    overlapped = sum(1 for n in cover.values() if n > 1)
    return dict(faces=count, loops=loops, zero_area_faces=zero, loops_outside_0_1=outside, grid=grid,
                covered_fraction=round(len(cover) / grid**2, 4),
                overlap_fraction_of_covered=round(overlapped / len(cover), 4) if cover else 0.0)


def png_header(data: bytes):
    """(width, height, bit depth, colour type) from a PNG's first 26 bytes; colour type 2 = RGB, 6 = RGBA."""
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError("not a PNG")
    return struct.unpack(">IIBB", data[16:26])


def file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def srgb_encode(x: float) -> float:
    return x * 12.92 if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055


# ---------------------------------------------------------------- Blender

def log(*parts):
    print("PBR_BAKE", *parts, flush=True)


@contextmanager
def shown(objects):
    """Render- and viewport-visible and selectable for a bake; previous state restored."""
    state = [(o, o.hide_render, o.hide_viewport, o.hide_get(), o.hide_select) for o in objects]
    try:
        for o in objects:
            o.hide_render = o.hide_viewport = o.hide_select = False
            o.hide_set(False)
        yield
    finally:
        for o, render, viewport, hidden_, select in state:
            o.hide_render, o.hide_viewport, o.hide_select = render, viewport, select
            o.hide_set(hidden_)


@contextmanager
def hidden(objects):
    state = [(o, o.hide_render) for o in objects]
    try:
        for o in objects:
            o.hide_render = True
        yield
    finally:
        for o, render in state:
            o.hide_render = render


def surface_nodes(mat):
    """(active Material Output, the Principled BSDF linked to its Surface) or BakeError naming the material."""
    if not mat.use_nodes or mat.node_tree is None:
        raise BakeError(f"material {mat.name!r} does not use nodes")
    output = next((n for n in mat.node_tree.nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output), None)
    if output is None or not output.inputs["Surface"].is_linked:
        raise BakeError(f"material {mat.name!r} has no active Material Output with a linked Surface")
    node = output.inputs["Surface"].links[0].from_node
    if node.type != "BSDF_PRINCIPLED":
        raise BakeError(f"material {mat.name!r}: Surface comes from {node.bl_idname}, not a Principled BSDF; "
                        "bake its inputs from a Principled BSDF or split the material")
    return output, node


def _feed(tree, src, dst):
    if src.is_linked:
        tree.links.new(src.links[0].from_socket, dst)
    else:
        value = src.default_value
        dst.default_value = (value, value, value, 1.0) if isinstance(value, float) and not isinstance(dst.default_value, float) \
            else value


@contextmanager
def bake_target(materials, image, channel, ao_distance, ao_samples):
    """An active image node in every material and, except for the normal, the channel routed to the Surface through an
    emission node. Everything is removed and relinked afterwards."""
    added, rewired, active = [], [], [(m, m.node_tree.nodes.active) for m in materials]
    try:
        for mat in materials:
            tree = mat.node_tree
            node = tree.nodes.new("ShaderNodeTexImage")
            node.image = image
            tree.nodes.active = node
            added.append((mat, node))
            if channel == "normal":
                continue
            output, principled = surface_nodes(mat)
            emission = tree.nodes.new("ShaderNodeEmission")
            added.append((mat, emission))
            if channel == "base_color":
                _feed(tree, principled.inputs["Base Color"], emission.inputs["Color"])
            elif channel == "rm_raw":
                combine = tree.nodes.new("ShaderNodeCombineColor")
                added.append((mat, combine))
                combine.inputs["Red"].default_value = 1.0
                _feed(tree, principled.inputs["Roughness"], combine.inputs["Green"])
                _feed(tree, principled.inputs["Metallic"], combine.inputs["Blue"])
                tree.links.new(combine.outputs["Color"], emission.inputs["Color"])
            else:
                ao = tree.nodes.new("ShaderNodeAmbientOcclusion")
                added.append((mat, ao))
                ao.samples = ao_samples
                ao.inputs["Distance"].default_value = ao_distance
                tree.links.new(ao.outputs["AO"], emission.inputs["Color"])
            rewired.append((mat, output, output.inputs["Surface"].links[0].from_socket))
            tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
        yield
    finally:
        for mat, output, old in rewired:
            mat.node_tree.links.new(old, output.inputs["Surface"])
        for mat, node in reversed(added):
            mat.node_tree.nodes.remove(node)
        for mat, node in active:
            mat.node_tree.nodes.active = node


def configure(scene, cfg) -> str:
    """Cycles with the configured samples, seed and threads, no denoiser. Returns the device actually used: GPU uses
    the first available backend and falls back to CPU (recorded in the cache key and provenance)."""
    import bpy
    scene.render.engine = "CYCLES"
    scene.cycles.samples, scene.cycles.seed, scene.cycles.use_denoising = cfg["samples"], cfg["seed"], False
    scene.render.threads_mode = "FIXED" if cfg["threads"] else "AUTO"
    if cfg["threads"]:
        scene.render.threads = cfg["threads"]
    device = "CPU"
    if cfg["device"] == "GPU":
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for backend in GPU_BACKENDS:
            try:
                prefs.compute_device_type = backend
            except TypeError:
                continue
            prefs.get_devices()
            if any(d.type == backend for d in prefs.devices):
                for d in prefs.devices:
                    d.use = d.type == backend
                device = "GPU:" + backend
                break
        else:
            log("WARNING no GPU backend available: baking on the CPU")
    scene.cycles.device = "CPU" if device == "CPU" else "GPU"
    return device


def family_uvs(objects, layer_name, depsgraph):
    """(UV map name per object, UV digest, UV report) from the evaluated meshes the bake sees."""
    digest, faces, names, missing = hashlib.sha256(), [], {}, []
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        try:
            layer = mesh.uv_layers.get(layer_name) if layer_name else mesh.uv_layers.active
            if layer is None:
                missing.append(obj.name)
                continue
            uv = array("f", bytes(8 * len(mesh.loops)))
            layer.data.foreach_get("uv", uv)
            starts, totals = array("i", bytes(4 * len(mesh.polygons))), array("i", bytes(4 * len(mesh.polygons)))
            mesh.polygons.foreach_get("loop_start", starts)
            mesh.polygons.foreach_get("loop_total", totals)
            faces += [[(uv[2 * k], uv[2 * k + 1]) for k in range(s, s + t)] for s, t in zip(starts, totals)]
            names[obj.name] = layer.name
            if sys.byteorder == "big":
                uv.byteswap()
            digest.update(json.dumps([obj.name, layer.name]).encode())
            digest.update(uv.tobytes())
        finally:
            evaluated.to_mesh_clear()
    if missing:
        raise BakeError(f"no UV map {layer_name or '(active)'} on: {', '.join(missing)}")
    return names, digest.hexdigest(), uv_report(faces)


def select(objects, active):
    import bpy
    view_layer = bpy.context.view_layer
    for o in view_layer.objects:
        o.select_set(False)
    for o in objects:
        o.select_set(True)
    view_layer.objects.active = active


def save_png(image, path):
    image.filepath_raw = str(path)
    image.file_format = "PNG"
    image.save()
    w, h = image.size
    return dict(sha256=file_sha256(path), size=[w, h], colorspace=image.colorspace_settings.name)


def bake_family(name, fam, cfg, out_dir, uv_names):
    import bpy
    scene = bpy.context.scene
    objects = [bpy.data.objects[n] for n in fam["objects"]]
    sources = {t: bpy.data.objects[s] for t, s in fam["normal_from"].items()}
    materials = list(dict.fromkeys(s.material for o in objects for s in o.material_slots))
    channels = (["base_color"] if "base_color" in cfg["maps"] else []) + (["rm_raw", "ao_raw"] if "orm" in cfg["maps"] else []) \
        + (["normal"] if "normal" in cfg["maps"] else [])
    alpha, outputs, images = cfg["color_mode"] == "RGBA", {}, {}
    hide_ao = [bpy.data.objects[n] for n in cfg["hide_during_ao"]]
    all_sources = [bpy.data.objects[n] for f in cfg["families"].values() for n in f["normal_from"].values()]
    # Blender bakes object by object and an object's margin fills every texel outside its own islands, including texels
    # an earlier object already baked. A second pass at margin 0 rewrites each object's own texels (twice the bake time).
    margins = [cfg["margin_px"]] + ([0] if cfg["repair_margin_overlap"] and cfg["margin_px"] and len(objects) > 1 else [])
    try:
        for channel in channels:
            size_key, colorspace, fill = CHANNELS[channel]
            width, height = fam["sizes"][size_key]
            image = images[channel] = bpy.data.images.new(f"{name}_{channel}", width, height, alpha=alpha)
            image.generated_color = fill
            image.colorspace_settings.name = colorspace
            with shown(objects), hidden(all_sources + (hide_ao if channel == "ao_raw" else [])), \
                    bake_target(materials, image, channel, fam["ao_distance_m"], cfg["ao_samples"]):
                for margin, obj in ((m, o) for m in margins for o in objects):
                    source = sources.get(obj.name) if channel == "normal" else None
                    kw = dict(type="NORMAL" if channel == "normal" else "EMIT", use_clear=False, margin=margin,
                              normal_space="TANGENT", uv_layer=uv_names[obj.name], use_selected_to_active=source is not None)
                    if source is None:
                        select([obj], obj)
                        bpy.ops.object.bake(**kw)
                        continue
                    with shown([source]):
                        select([obj, source], obj)
                        scene.cycles.samples = fam["normal_from_samples"] or cfg["samples"]
                        try:
                            bpy.ops.object.bake(**kw, cage_extrusion=fam["cage_extrusion_m"],
                                                max_ray_distance=fam["max_ray_distance_m"])
                        finally:
                            scene.cycles.samples = cfg["samples"]
            outputs[f"{name}_{channel}.png"] = save_png(image, out_dir / f"{name}_{channel}.png")
            log("baked", f"{name}_{channel}.png", width, height)
        if "orm" in cfg["maps"]:
            rm, ao = images["rm_raw"], images["ao_raw"]
            buffers = []
            for image in (ao, rm):
                buffers.append(array("f", bytes(16 * image.size[0] * image.size[1])))
                image.pixels.foreach_get(buffers[-1])
            packed = images["orm"] = bpy.data.images.new(f"{name}_orm", *rm.size, alpha=alpha)
            packed.colorspace_settings.name = "Non-Color"
            packed.pixels.foreach_set(pack_orm(*buffers))
            packed.update()
            outputs[f"{name}_orm.png"] = save_png(packed, out_dir / f"{name}_orm.png")
            log("packed", f"{name}_orm.png")
    finally:
        for image in images.values():
            bpy.data.images.remove(image)
    return outputs


def check_scene(cfg):
    """Every named object exists, every baked object is a mesh in the view layer with node materials ready to bake."""
    import bpy
    errors, layer = [], bpy.context.view_layer.objects
    for name, fam in cfg["families"].items():
        for n in fam["objects"] + list(fam["normal_from"].values()):
            obj = bpy.data.objects.get(n)
            if obj is None or obj.type != "MESH" or n not in layer:
                errors.append(f"families.{name}: {n!r} is " + ("missing" if obj is None else "not a mesh" if obj.type != "MESH"
                                                                else "not in the active view layer"))
                continue
            if n not in fam["objects"]:
                continue
            if not obj.material_slots or any(s.material is None for s in obj.material_slots):
                errors.append(f"families.{name}: {n!r} has no material or an empty material slot")
            for slot in obj.material_slots:
                try:
                    if slot.material:
                        surface_nodes(slot.material)
                except BakeError as e:
                    errors.append(f"families.{name}: {n!r}: {e}")
    errors += [f"hide_during_ao: {n!r} is missing" for n in cfg["hide_during_ao"] if n not in bpy.data.objects]
    if errors:
        raise BakeError("\n".join(dict.fromkeys(errors)))


def run_bake(cfg: dict, out_dir) -> dict:
    """Bake every family whose cache key changed; write bake_provenance.json; return it."""
    import bpy
    blend = bpy.data.filepath
    if not blend:
        raise BakeError("the scene has not been saved: the cache key needs the .blend's SHA-256")
    blend_sha = file_sha256(blend)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    check_scene(cfg)
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    scene = bpy.context.scene
    device = configure(scene, cfg)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    try:
        previous = json.loads((out_dir / PROVENANCE).read_text()).get("families", {})
    except (OSError, ValueError):
        previous = {}
    provenance = dict(schema=SCHEMA, tool="pbr_bake.py", blender=bpy.app.version_string, device=device,
                      input=dict(file=os.path.basename(blend), sha256=blend_sha), config=cfg, families={})
    for name, fam in cfg["families"].items():
        uv_names, uv_sha, report = family_uvs([bpy.data.objects[n] for n in fam["objects"]], cfg["uv_layer"], depsgraph)
        warnings = [k for k in ("zero_area_faces", "loops_outside_0_1", "overlap_fraction_of_covered") if report[k]]
        log("uv", name, json.dumps(report, sort_keys=True), "WARNING " + ", ".join(warnings) if warnings else "")
        key = cache_key(cfg, name, blend_sha, uv_sha, bpy.app.version_string, device)
        old = previous.get(name, {})
        cached = old.get("cache_key") == key and old.get("outputs") and all(
            (out_dir / f).is_file() and file_sha256(out_dir / f) == rec["sha256"] for f, rec in old["outputs"].items())
        outputs = old["outputs"] if cached else bake_family(name, fam, cfg, out_dir, uv_names)
        provenance["families"][name] = dict(status="cached" if cached else "baked", cache_key=key, uv_sha256=uv_sha,
                                            uv_maps=uv_names, uv_report=report, uv_warnings=warnings, outputs=outputs)
        log("family", name, "cached" if cached else "baked", key[:12])
    tmp = out_dir / (PROVENANCE + ".tmp")
    tmp.write_text(json.dumps(provenance, indent=1, sort_keys=True) + "\n")
    os.replace(tmp, out_dir / PROVENANCE)
    if file_sha256(blend) != blend_sha:
        raise BakeError("the input .blend changed during the bake")
    return provenance


# ---------------------------------------------------------------- tests

def self_test() -> int:
    """Plain Python. Explicit checks, not assert, so it also runs under python -O."""
    failures = []

    def check(label, ok):
        if not ok:
            failures.append(label)

    def rejects(data, fragment):
        try:
            validate_config(data)
        except ConfigError as e:
            return fragment in str(e)
        return False

    base = {"families": {"F": {"objects": ["A", "B"], "normal_from": {"A": "A_hi"}}}, "hide_during_ao": ["Floor"]}
    cfg = validate_config(base)
    check("defaults", cfg["samples"] == 16 and cfg["seed"] == 12 and cfg["margin_px"] == 8 and cfg["color_mode"] == "RGBA"
          and cfg["families"]["F"]["sizes"]["orm"] == [1024, 1024] and cfg["maps"] == list(MAPS))
    check("partial sizes merge", validate_config({"families": {"F": {"objects": ["A"], "sizes": {"normal": [64, 32]}}}})
          ["families"]["F"]["sizes"] == {"base_color": [1024, 1024], "orm": [1024, 1024], "normal": [64, 32]})
    example = Path(__file__).resolve().parent.parent / "examples" / "bake_config.example.json"
    try:
        check("example config validates", bool(validate_config(json.loads(example.read_text()))["families"]))
    except (OSError, ValueError) as e:
        failures.append(f"example config: {e}")
    for data, fragment in [
        ([], "JSON object"), ({}, "families must be"), ({"families": {"F": {"objects": ["A"]}}, "sample": 4}, "unknown key 'sample'"),
        ({"families": {"F": {"objects": ["A"]}}, "samples": True}, "samples must be"),
        ({"families": {"F": {"objects": ["A"]}}, "maps": ["albedo"]}, "maps must be"),
        ({"families": {"F": {"objects": ["A"], "sizes": {"orm": [0, 64]}}}}, "sizes must be"),
        ({"families": {"F": {"objects": ["A"], "ao_distance_m": -1}}}, "ao_distance_m must be"),
        ({"families": {"F": {"objects": []}}}, "objects must be"),
        ({"families": {"F/x": {"objects": ["A"]}}}, "file names"),
        ({"families": {"F": {"objects": ["A"]}, "G": {"objects": ["A"]}}}, "already in family 'F'"),
        ({"families": {"F": {"objects": ["A"], "normal_from": {"B": "C"}}}}, "not one of this family"),
        ({"families": {"F": {"objects": ["A", "B"], "normal_from": {"A": "B"}}}}, "is itself baked"),
        ({"families": {"F": {"objects": ["A"]}}, "hide_during_ao": ["A"]}, "which is baked"),
    ]:
        check(f"rejects {json.dumps(data)[:60]}", rejects(data, fragment))

    def key(c, blend="b" * 64, uv="u" * 64):
        return cache_key(c, "F", blend, uv, "5.2.1", "CPU")
    k0 = key(cfg)
    reordered = {"hide_during_ao": ["Floor"], "seed": 12, "families": {"F": {"normal_from": {"A": "A_hi"}, "objects": ["A", "B"],
                                                                         "ao_distance_m": 0.004}}}
    check("key deterministic, order- and explicit-default-free", k0 == key(cfg) == key(validate_config(reordered)))
    for label, changed in [("blend", key(cfg, blend="c" * 64)), ("uv", key(cfg, uv="v" * 64)),
                           ("seed", key(validate_config({**base, "seed": 13}))),
                           ("hide list", key(validate_config({**base, "hide_during_ao": []}))),
                           ("size", key(validate_config({**base, "families": {"F": {**base["families"]["F"], "sizes": {"orm": [512, 512]}}}}))),
                           ("ao distance", key(validate_config({**base, "families": {"F": {**base["families"]["F"], "ao_distance_m": 0.002}}})))]:
        check(f"key changes with {label}", changed != k0)

    ao, rm = [0.1, 9, 9, 9, 0.2, 9, 9, 9], [1, 0.3, 0.4, 1, 1, 0.5, 0.6, 1]
    check("pack list", pack_orm(ao, rm) == [0.1, 0.3, 0.4, 1, 0.2, 0.5, 0.6, 1] and rm == [1, 0.3, 0.4, 1, 1, 0.5, 0.6, 1])
    a_ao, a_rm = array("f", ao), array("f", rm)
    check("pack array", pack_orm(a_ao, a_rm) == array("f", [0.1, 0.3, 0.4, 1, 0.2, 0.5, 0.6, 1]) and a_rm == array("f", rm))
    try:
        pack_orm(ao, rm[:4])
        failures.append("pack accepts mismatched sizes")
    except ValueError:
        pass

    tri1, tri2 = [(0, 0), (1, 0), (1, 1)], [(0, 0), (1, 1), (0, 1)]
    clean = uv_report([tri1, tri2], grid=16)
    check("uv clean", clean["zero_area_faces"] == clean["loops_outside_0_1"] == 0 and clean["overlap_fraction_of_covered"] == 0
          and clean["covered_fraction"] == 1.0 and clean["faces"] == 2 and clean["loops"] == 6)
    dirty = uv_report([tri1, tri2, tri1, [(0.2, 0.2), (0.4, 0.4), (0.6, 0.6)], [(1.5, 0), (2, 0), (2, -1)]], grid=16)
    check("uv dirty", dirty["zero_area_faces"] == 1 and dirty["loops_outside_0_1"] == 3
          and 0.4 < dirty["overlap_fraction_of_covered"] < 0.6)
    concave = [(0, 0), (1, 0), (1, 1), (0.5, 0.2), (0, 1)]
    check("uv concave face", not _inside(concave, 0.5, 0.6) and _inside(concave, 0.5, 0.1))

    header = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">IIBBBBB", 64, 32, 8, 6, 0, 0, 0)
    check("png header", png_header(header) == (64, 32, 8, 6))
    check("srgb", abs(srgb_encode(0.2) * 255 - 124.0) < 0.5 and srgb_encode(0.0) == 0.0)

    for f in failures:
        print("FAIL:", f)
    print("pbr_bake self-test:", "PASS" if not failures else f"{len(failures)} FAILED")
    return 1 if failures else 0


def _mesh_object(name, verts, faces, uvs, material=None):
    import bpy
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    layer = mesh.uv_layers.new(name="UVMap")
    for loop, uv in zip(layer.data, uvs):
        loop.uv = uv
    if material:
        mesh.materials.append(material)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _test_scene():
    """Probe: a floor face (A), a wall (B) that occludes A near x = 0, and an underside (C) 5 mm above a Ground that would
    occlude it. UV quadrants: A [0, .5]^2, B [.5, 1] x [0, .5], C [0, .5] x [.5, 1]. Roughness = U, metallic = V > 0.25.
    Relief: a flat plane whose normal comes from a bumpy source baked selected-to-active."""
    import bpy
    for obj in list(bpy.data.objects):     # the factory scene's cube would enclose the probe and occlude its AO
        bpy.data.objects.remove(obj)
    probe = bpy.data.materials.new("Probe_Material")
    probe.use_nodes = True
    tree = probe.node_tree
    principled = next(n for n in tree.nodes if n.type == "BSDF_PRINCIPLED")
    principled.inputs["Base Color"].default_value = (0.2, 0.5, 0.8, 1.0)
    coords, split, step = (tree.nodes.new(t) for t in ("ShaderNodeTexCoord", "ShaderNodeSeparateXYZ", "ShaderNodeMath"))
    step.operation = "GREATER_THAN"
    step.inputs[1].default_value = 0.25
    tree.links.new(coords.outputs["UV"], split.inputs[0])
    tree.links.new(split.outputs["X"], principled.inputs["Roughness"])
    tree.links.new(split.outputs["Y"], step.inputs[0])
    tree.links.new(step.outputs[0], principled.inputs["Metallic"])
    a = [(0, 0, .01), (1, 0, .01), (1, 1, .01), (0, 1, .01)]
    b = [(0, 0, .01), (0, 1, .01), (0, 1, 1.01), (0, 0, 1.01)]
    c = [(0, 0, .005), (0, 1, .005), (1, 1, .005), (1, 0, .005)]
    uvs = [(x * .5, y * .5) for x, y, _ in a] + [(.5 + y * .5, (z - .01) * .5) for _, y, z in b] + [(x * .5, .5 + y * .5) for x, y, _ in c]
    _mesh_object("Probe", a + b + c, [(0, 1, 2, 3), (4, 5, 6, 7), (8, 9, 10, 11)], uvs, probe)
    _mesh_object("Ground", [(-5, -5, 0), (5, -5, 0), (5, 5, 0), (-5, 5, 0)], [(0, 1, 2, 3)], [(0, 0), (1, 0), (1, 1), (0, 1)])
    plain = bpy.data.materials.new("Relief_Material")
    plain.use_nodes = True
    _mesh_object("Relief", [(5, 0, .3), (6, 0, .3), (6, 1, .3), (5, 1, .3)], [(0, 1, 2, 3)], [(0, 0), (1, 0), (1, 1), (0, 1)], plain)
    n = 24
    verts = [(5 + i / n, j / n, .3 + .02 * math.sin(6 * math.pi * i / n) * math.sin(6 * math.pi * j / n))
             for j in range(n + 1) for i in range(n + 1)]
    quads = [(j * (n + 1) + i, j * (n + 1) + i + 1, (j + 1) * (n + 1) + i + 1, (j + 1) * (n + 1) + i) for j in range(n) for i in range(n)]
    _mesh_object("Relief_high", verts, quads, [(0, 0)] * (4 * len(quads)))
    for obj_name, colour, x0, (u0, u1) in (("PairA", (1, 0, 0), 10, (0, 30 / 64)), ("PairB", (0, 0, 1), 12, (32 / 64, 1))):
        pair = bpy.data.materials.new(obj_name + "_Material")       # islands 2 texels apart, inside the 8-texel margin
        pair.use_nodes = True
        next(n for n in pair.node_tree.nodes if n.type == "BSDF_PRINCIPLED").inputs["Base Color"].default_value = (*colour, 1)
        _mesh_object(obj_name, [(x0, 0, .3), (x0 + 1, 0, .3), (x0 + 1, 1, .3), (x0, 1, .3)], [(0, 1, 2, 3)],
                     [(u0, 0), (u1, 0), (u1, 1), (u0, 1)], pair)


TEST_CONFIG = {
    "device": "CPU", "hide_during_ao": ["Ground"],
    "families": {
        "Probe": {"objects": ["Probe"], "sizes": {m: [64, 64] for m in MAPS}, "ao_distance_m": 0.5},
        "Relief": {"objects": ["Relief"], "sizes": {"base_color": [32, 64], "orm": [64, 64], "normal": [64, 32]},
                   "normal_from": {"Relief": "Relief_high"}, "cage_extrusion_m": 0.05, "max_ray_distance_m": 0.1},
        "Pair": {"objects": ["PairA", "PairB"], "sizes": {"base_color": [64, 64], "orm": [16, 16], "normal": [16, 16]}},
    },
}


def blender_test(scratch) -> int:
    """Bake a generated scene at 64 x 64 and check files, sizes, colour spaces, ORM channels, restoration and the cache."""
    import bpy
    scratch = Path(scratch).resolve()
    scratch.mkdir(parents=True, exist_ok=True)
    for f in scratch.glob("out/*"):
        f.unlink()
    _test_scene()
    blend = scratch / "pbr_bake_test.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    blend_sha, out = file_sha256(blend), scratch / "out"
    results = {}

    def check(label, ok, detail=None):
        results[label] = ("PASS" if ok else "FAIL") + ("" if detail is None else f" {detail}")

    def state():
        return {m.name: (len(m.node_tree.nodes), m.node_tree.nodes.active.name if m.node_tree.nodes.active else None,
                         [l.from_node.name for n in m.node_tree.nodes if n.type == "OUTPUT_MATERIAL" for l in n.inputs["Surface"].links])
                for m in bpy.data.materials if m.node_tree}
    ground = bpy.data.objects["Ground"]
    before, ground_before = state(), (ground.hide_render, ground.hide_get())

    def pixels(name):
        image = bpy.data.images.load(str(out / name), check_existing=False)
        image.colorspace_settings.name = "Non-Color"
        w, h = image.size
        buf = array("f", bytes(16 * w * h))
        image.pixels.foreach_get(buf)
        bpy.data.images.remove(image)
        return lambda i, j, c: buf[(j * w + i) * 4 + c]

    def mean(px, channel, i_range, j_range):
        values = [px(i, j, channel) for i in i_range for j in j_range]
        return sum(values) / len(values)

    first = run_bake(validate_config(TEST_CONFIG), out)
    check("first run bakes every family", all(f["status"] == "baked" for f in first["families"].values()))
    expect = {"Probe_base_color.png": (64, 64), "Probe_rm_raw.png": (64, 64), "Probe_ao_raw.png": (64, 64), "Probe_orm.png": (64, 64),
              "Probe_normal.png": (64, 64), "Relief_base_color.png": (32, 64), "Relief_orm.png": (64, 64), "Relief_normal.png": (64, 32)}
    headers = {f: png_header((out / f).read_bytes()[:26]) if (out / f).is_file() else None for f in expect}
    check("files exist, sizes, 8-bit RGBA", all(headers[f] == (*size, 8, 6) for f, size in expect.items()), headers)
    spaces = {f: r["colorspace"] for fam in first["families"].values() for f, r in fam["outputs"].items()}
    check("colour spaces recorded", all(v == ("sRGB" if f.endswith("base_color.png") else "Non-Color") for f, v in spaces.items()), spaces)
    base, rm, ao, orm, normal = (pixels(f"Probe_{c}.png") for c in ("base_color", "rm_raw", "ao_raw", "orm", "normal"))
    inner = range(2, 30)
    stored = [round(255 * mean(base, c, inner, inner)) for c in range(3)]
    check("base colour stored sRGB-encoded", all(abs(s - 255 * srgb_encode(v)) <= 2 for s, v in zip(stored, (0.2, 0.5, 0.8))), stored)
    rough_err = max(abs(rm(i, j, 1) - (i + 0.5) / 64) for i in inner for j in inner)
    check("roughness (G) = U, stored linear", rough_err < 0.02, round(rough_err, 4))
    metal = [rm(i, j, 2) for i in inner for j in range(2, 14)], [rm(i, j, 2) for i in inner for j in range(18, 30)]
    check("metallic (B) = V > 0.25", max(metal[0]) < 0.02 and min(metal[1]) > 0.98, (max(metal[0]), min(metal[1])))
    every = [(i, j) for i in range(64) for j in range(64)]
    check("ORM R = AO, G/B = roughness/metallic exactly", all(orm(i, j, 0) == ao(i, j, 0) and orm(i, j, 1) == rm(i, j, 1)
                                                            and orm(i, j, 2) == rm(i, j, 2) and orm(i, j, 3) == 1.0 for i, j in every))
    check("raw roughness/metallic bake untouched (R = 1)", all(rm(i, j, 0) == 1.0 for i, j in every))
    near, far, under = mean(ao, 0, range(2, 6), inner), mean(ao, 0, range(26, 30), inner), mean(ao, 0, inner, range(34, 62))
    check("AO varies: wall occludes the floor, packed into R", near < far - 0.1 and far > 0.95 and mean(orm, 0, range(2, 6), inner) == near,
          (round(near, 3), round(far, 3)))
    check("hidden ground does not occlude the underside", under > 0.95, round(under, 3))
    flat = [round(mean(normal, c, inner, inner), 3) for c in range(3)]
    check("flat normal (0.5, 0.5, 1) stored linear", abs(flat[0] - .5) < .02 and abs(flat[1] - .5) < .02 and flat[2] > .98, flat)
    relief = pixels("Relief_normal.png")
    xs = [relief(i, j, 0) for i in range(4, 60) for j in range(4, 28)]
    spread = (sum((x - sum(xs) / len(xs)) ** 2 for x in xs) / len(xs)) ** 0.5
    check("selected-to-active normal carries the source relief", spread > 0.03, round(spread, 4))
    pair = pixels("Pair_base_color.png")
    edge = [round(pair(i, 32, c), 2) for i in (28, 29, 32, 33) for c in (0, 2)]
    check("a later object's margin leaves an earlier object's texels intact; gap stays padded", all(pair(i, j, 0) > .9 and pair(i, j, 2) < .1
          for i in (28, 29) for j in range(2, 62)) and all(pair(i, j, 2) > .9 for i in (32, 33) for j in range(2, 62))
          and all(max(pair(i, j, 0), pair(i, j, 2)) > .9 for i in (30, 31) for j in range(2, 62)), edge)
    report = first["families"]["Probe"]["uv_report"]
    check("UV report clean", report["zero_area_faces"] == report["loops_outside_0_1"] == 0 and report["overlap_fraction_of_covered"] == 0, report)
    check("materials and visibility restored", state() == before and (ground.hide_render, ground.hide_get()) == ground_before)
    check("provenance file", (out / PROVENANCE).is_file() and json.loads((out / PROVENANCE).read_text())["input"]["sha256"] == blend_sha)

    hashes = {f: file_sha256(out / f) for f in expect}
    second = run_bake(validate_config(TEST_CONFIG), out)
    check("unchanged inputs skipped by the cache key", all(f["status"] == "cached" for f in second["families"].values())
          and hashes == {f: file_sha256(out / f) for f in expect})
    third = run_bake(validate_config({**TEST_CONFIG, "hide_during_ao": []}), out)
    under_visible = mean(pixels("Probe_ao_raw.png"), 0, inner, range(34, 62))
    check("changed setting rebakes; visible ground would occlude", third["families"]["Probe"]["status"] == "baked"
          and under_visible < 0.3, round(under_visible, 3))
    check("input .blend unchanged", file_sha256(blend) == blend_sha)

    failed = [k for k, v in results.items() if not v.startswith("PASS")]
    print("PBR_BAKE_TEST_JSON=" + json.dumps(dict(blender=bpy.app.version_string, device=first["device"], passed=len(results) - len(failed),
                                                  failed=failed, checks=results), sort_keys=True))
    return 1 if failed else 0


def main(argv) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--self-test", action="store_true", help="plain-Python checks")
    parser.add_argument("--blender-test", metavar="DIR", help="bake a generated scene in DIR (inside Blender)")
    parser.add_argument("--config", help="bake configuration JSON")
    parser.add_argument("--out", help="output directory for the maps and bake_provenance.json")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.blender_test:
        return blender_test(args.blender_test)
    if not (args.config and args.out):
        parser.error("--config and --out are required")
    provenance = run_bake(validate_config(json.loads(Path(args.config).read_text())), args.out)
    print("PBR_BAKE_JSON=" + json.dumps({k: {f: dict(status=v["status"], uv_warnings=v["uv_warnings"], outputs=sorted(v["outputs"]))
                                              for f, v in provenance["families"].items()} if k == "families" else provenance[k]
                                         for k in ("device", "input", "families")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        code = main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
    except (ConfigError, BakeError) as error:
        print("PBR_BAKE_ERROR", error, file=sys.stderr)
        code = 1
    except Exception:  # Blender exits 0 after an uncaught exception unless --python-exit-code is given
        import traceback
        traceback.print_exc()
        code = 1
    sys.exit(code)
