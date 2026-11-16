#!/usr/bin/env python3
"""Audit a runtime GLB's shading normals against a reference GLB: at the corners, inside the faces, and flat.

  normal_audit.py REFERENCE.glb CANDIDATE.glb [--node NAME ...] [--ref-node NAME ...] [--exclude PREFIX ...]
                  [--radius 2e-5] [--flat-deg 0.5] [--max-inface-over5 0.5] [--max-corner-over5 0.5]
                  [--max-unreachable 0] [--max-shaded-over5 PCT] [--degenerate-area 1e-12] [--json OUT.json]
  normal_audit.py --make-fixtures DIR
  normal_audit.py --self-test

Why: a reduced mesh can sit within micrometres of its reference and still shade wrong. A renderer interpolates the three
corner normals across each triangle, so a large triangle running from a fillet across a flat wall drags the fillet's tilt
over the wall even when every corner is exact. Position audits and corner-normal audits cannot see that; this one can.

Method (ported from a Blender audit used in a product case study, where the reference was the Blender master; here it is a
second GLB, for example a full-resolution export of the master):
  * both files are read as a renderer reads them: POSITION, NORMAL and indices of every TRIANGLES primitive, each node at
    its world transform (normals by the inverse transpose, renormalised per vertex, interpolated, renormalised);
  * every candidate triangle is sampled at 7 points: the 3 corners, the centroid and the 3 edge midpoints;
  * at each point the candidate's shading normal is taken twice: the interpolated vertex normal, and the same with the
    tangent-space normal map applied (glTF: n = T x s + B y s + N z, B = cross(N, T) w, s = normalTexture.scale; T, B, N
    and the UV interpolated, the texture read bilinearly with its sampler's wrap modes);
  * each normal is compared with the reference's interpolated normal at the nearest reference surface: every reference
    triangle within --radius (default 20 um) is tried and the best-agreeing one kept, because at a crease the nearest face
    is ambiguous. A uniform grid finds the triangles. Results are cached per vertex and per edge but counted per
    occurrence, so the statistics are those of 7 samples per triangle.
Reported overall and per row, one row per candidate node and material (median, p99, max, % of points over 2 and 5 degrees):
  position_um    distance to the reference surface, corners and in-face points separately (um);
  corners        the vertex normals at the triangle corners;
  in_face        the interpolated normal at the centroid and the 3 edge midpoints;
  face           the flat (geometric) normal at the centroid, winding as stored (a mirroring transform flips it);
  shaded         all 7 points with the normal map applied: the normal the renderer lights. Primitives without a normal map
                 count their interpolated normal; triangles with zero UV area are left out (nothing can see them).
                 The reference's own normal map is not applied, so a map's baked relief (wear, brushing) shows here too:
                 compare unreduced parts to see how much. Not gated unless --max-shaded-over5 is given. Maps that cannot be
                 applied (JPEG, KTX2, no TANGENT, KHR_texture_transform, non-float UVs) are listed in `shaded_skipped`.
  in_face_by_curvature   in_face split by the matched reference triangle: `flat` when its three vertex normals are within
                 --flat-deg of each other, else `curved`. In-face error on flat reference surface is the fillet-drag signature.
Points with no reference triangle within the radius are `unreachable`: counted, not scored. Candidate checks: zero-area
triangles (area <= --degenerate-area m^2), non-finite positions or normals, NORMAL vectors whose length is not 1 within
1e-3. Reference triangles with those defects are left out of the search and counted.

Thresholds are fixed before the run and applied overall and to every row: in-face and corner points over 5 degrees
<= 0.5 % each, no unreachable point, at least one point compared, no candidate defect. Exit 0 when all hold, 1 when one
fails, 2 on unreadable or unsupported input (Draco, meshopt, quantized or sparse attributes, external buffers).
`--exclude` takes node-name prefixes to skip (default HIT_, the hit proxies; `--exclude ""` skips nothing).

--make-fixtures DIR writes the mechanism as three files: reference.glb (a 10 mm flat wall, a 0.1 mm fillet and a side wall,
finely tessellated, analytic vertex normals); candidate_bad.glb (every vertex is a reference vertex with its exact normal,
but the wall triangles run from the fillet's 22.5-degree line across the whole wall: corner error 0, position a few um,
in-face error up to 15 degrees on the flat wall); candidate_good.glb (the same plus the fillet's tangent line, placed under a
rotated, translated, non-uniformly scaled parent to exercise world transforms). The bad candidate fails, the good passes.

Differences from the source: it read the map with clamped texel indices and assumed scale 1; this follows the sampler's
wrap modes (lathe strips run past u = 1) and applies the scale. Its `unreachable` meant "no camera can see the matched
master face" (a visibility probe); here it means "no reference surface within the radius". It scored points beyond the
radius against the nearest master face; this script does not. It worked in Blender's frame and re-checked single-precision
BVH misses in double precision; this search is double precision throughout, in the glTF frame of both files.
Leniency: the best match within the radius forgives up to about radius / curvature radius (radians) on tight curvature, as in
the source: on a 0.1 mm fillet a 20 um radius hides about 11 degrees. Keep --radius well below the smallest radius audited.
Cost: pure Python, one core (Apple M5 Max): 103k candidate triangles (720k samples) against a 100k-triangle reference take
3.4 s on Python 3.15 and 5.5 s on Python 3.9; with a 1024 x 1024 normal map 4.7 s and 7.6 s. PNG decoding adds about 0.25 s per
megapixel (Python 3.15, real captures with Sub/Up/Average/Paeth rows), about 4 s for a 4k map. A whole pedal asset, 249k
candidate against 598k reference triangles with long slivers and four PNG normal maps up to 2048 x 4096, took 18 s
(Python 3.15) and 30 s (Python 3.9). Time grows with candidate triangles and reference triangles per grid cell.
"""

from __future__ import annotations

import argparse
import base64
import bisect
import contextlib
import hashlib
import io
import json
import math
import struct
import sys
import tempfile
import time
import zlib
from array import array
from itertools import accumulate
from operator import add
from pathlib import Path

COMPONENT = {5121: "B", 5123: "H", 5125: "I", 5126: "f"}
WIDTH = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
UNSUPPORTED = {"KHR_draco_mesh_compression", "EXT_meshopt_compression", "KHR_mesh_quantization"}
BARY_EPS = 1e-9
BIG_CELLS = 4096   # a reference triangle spanning more cells goes to a 16x coarser grid level (4 levels; then a flat list)
MISSING = object()


class GLBError(ValueError):
    pass


# ----------------------------------------------------------------- GLB reading
def read_glb(path):
    data = Path(path).read_bytes()
    if len(data) < 20 or data[:4] != b"glTF":
        raise GLBError(f"{path}: not a binary glTF (GLB) file")
    version, total = struct.unpack_from("<II", data, 4)
    length, kind = struct.unpack_from("<I4s", data, 12)
    if version != 2 or total != len(data) or kind != b"JSON":
        raise GLBError(f"{path}: not a glTF 2.0 GLB with its JSON chunk first")
    g = json.loads(data[20:20 + length])
    off, binary = 20 + length, b""
    if off + 8 <= len(data):
        size, kind = struct.unpack_from("<I4s", data, off)
        if kind == b"BIN\0":
            binary = data[off + 8:off + 8 + size]
    bad = UNSUPPORTED & set(g.get("extensionsUsed", []))
    if bad:
        raise GLBError(f"{path}: uses {sorted(bad)}; export uncompressed float attributes for the audit")
    return g, binary, hashlib.sha256(data).hexdigest()


def accessor(g, binary, index, floats=False):
    a = g["accessors"][index]
    if "sparse" in a or "bufferView" not in a:
        raise GLBError(f"accessor {index}: sparse or buffer-less accessors are not supported")
    if a["componentType"] not in COMPONENT or (floats and a["componentType"] != 5126):
        raise GLBError(f"accessor {index}: component type {a['componentType']} is not supported here")
    v = g["bufferViews"][a["bufferView"]]
    if "uri" in g["buffers"][v.get("buffer", 0)]:
        raise GLBError("external buffers are not supported: export a self-contained GLB")
    code, count = COMPONENT[a["componentType"]], a["count"]
    item = struct.calcsize("<" + code) * WIDTH[a["type"]]
    stride = v.get("byteStride") or item
    start = v.get("byteOffset", 0) + a.get("byteOffset", 0)
    if count and start + stride * (count - 1) + item > len(binary):
        raise GLBError(f"accessor {index} runs past the binary chunk")
    out = array(code)
    if stride == item:
        out.frombytes(binary[start:start + item * count])
    else:
        for k in range(count):
            out.frombytes(binary[start + k * stride:start + k * stride + item])
    if sys.byteorder == "big":
        out.byteswap()
    return out


def png_rows(blob):
    """(width, height, bytes per pixel, rows) of an 8-bit RGB or RGBA, non-interlaced PNG"""
    if blob[:8] != b"\x89PNG\r\n\x1a\n":
        raise GLBError("normal map: not a PNG")
    pos, idat, head = 8, [], None
    while pos + 12 <= len(blob):
        n, kind = struct.unpack_from(">I4s", blob, pos)
        if kind == b"IHDR":
            head = struct.unpack_from(">IIBBBBB", blob, pos + 8)
        elif kind == b"IDAT":
            idat.append(blob[pos + 8:pos + 8 + n])
        elif kind == b"IEND":
            break
        pos += 12 + n
    w, h, depth, ctype, _, _, interlace = head or (0, 0, 0, 0, 0, 0, 0)
    bpp = {2: 3, 6: 4}.get(ctype)
    if depth != 8 or bpp is None or interlace:
        raise GLBError(f"normal map: PNG bit depth {depth}, colour type {ctype}, interlace {interlace}: only 8-bit RGB/RGBA")
    raw, stride = zlib.decompress(b"".join(idat)), w * bpp
    if len(raw) != h * (stride + 1):
        raise GLBError("normal map: PNG data size does not match its header")
    rows, prev = [], bytes(stride)
    for y in range(h):
        kind, line = raw[y * (stride + 1)], raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)]
        if kind == 0:
            cur = line
        elif kind == 1:
            cur = bytearray(line)
            for c in range(bpp):
                cur[c::bpp] = bytes(map((255).__and__, accumulate(line[c::bpp])))
        elif kind == 2:
            cur = bytes(map((255).__and__, map(add, line, prev)))
        elif kind in (3, 4):
            cur = bytearray(line)
            for i in range(stride):
                a, b = (cur[i - bpp] if i >= bpp else 0), prev[i]
                if kind == 3:
                    cur[i] = (cur[i] + ((a + b) >> 1)) & 255
                else:
                    c = prev[i - bpp] if i >= bpp else 0
                    pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                    cur[i] = (cur[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        else:
            raise GLBError(f"normal map: invalid PNG filter type {kind}")
        prev = bytes(cur)
        rows.append(prev)
    return w, h, bpp, rows


def wrap(i, n, mode):
    if mode == 33071:                                   # CLAMP_TO_EDGE
        return min(max(i, 0), n - 1)
    if mode == 33648:                                   # MIRRORED_REPEAT
        i %= 2 * n
        return i if i < n else 2 * n - 1 - i
    return i % n                                        # REPEAT (the default)


def texel(tex, u, v):
    """bilinear tangent-space normal (components -1..1) at a glTF UV (origin at the image's top left)"""
    w, h, bpp, rows, ws, wt = tex
    x, y = u * w - 0.5, v * h - 0.5
    x0, y0 = math.floor(x), math.floor(y)
    fx, fy = x - x0, y - y0
    xa, xb = wrap(x0, w, ws) * bpp, wrap(x0 + 1, w, ws) * bpp
    ra, rb = rows[wrap(y0, h, wt)], rows[wrap(y0 + 1, h, wt)]
    return [((ra[xa + c] * (1 - fx) + ra[xb + c] * fx) * (1 - fy) + (rb[xa + c] * (1 - fx) + rb[xb + c] * fx) * fy) / 127.5 - 1
            for c in range(3)]


def shading(g, binary, prim, lin, sign, images):
    """None without a normal texture; a reason string when it cannot be applied; else the texture, scale, UVs, world
    tangents and handedness"""
    nt = (g["materials"][prim["material"]] if "material" in prim else {}).get("normalTexture")
    if nt is None:
        return None
    at, uv_key = prim["attributes"], f"TEXCOORD_{nt.get('texCoord', 0)}"
    if "TANGENT" not in at or uv_key not in at:
        return f"no TANGENT or {uv_key} (tangents are not generated here)"
    if "KHR_texture_transform" in nt.get("extensions", {}):
        return "KHR_texture_transform is not applied"
    tex = g["textures"][nt["index"]]
    src = tex.get("source")
    im = g["images"][src] if src is not None else {}
    if im.get("mimeType") != "image/png" or "bufferView" not in im:
        return f"normal map is {im.get('mimeType', 'not an embedded image')}, not an embedded PNG"
    sampler = g["samplers"][tex["sampler"]] if "sampler" in tex else {}
    try:
        if src not in images:
            v = g["bufferViews"][im["bufferView"]]
            images[src] = png_rows(binary[v.get("byteOffset", 0):v.get("byteOffset", 0) + v["byteLength"]])
        uv, tan = accessor(g, binary, at[uv_key], True), accessor(g, binary, at["TANGENT"], True)
    except (GLBError, zlib.error) as exc:
        return str(exc)
    T = [unit(*(lin[r][0] * tan[k] + lin[r][1] * tan[k + 1] + lin[r][2] * tan[k + 2] for r in range(3)))
         for k in range(0, len(tan), 4)]
    return dict(tex=(*images[src], sampler.get("wrapS", 10497), sampler.get("wrapT", 10497)), scale=nt.get("scale", 1.0),
                UV=[(uv[k], uv[k + 1]) for k in range(0, len(uv), 2)], T=T, W=[sign * tan[k + 3] for k in range(0, len(tan), 4)])


def shaded(sh, weights, n):
    """the normal-mapped shading normal at a point given as [(vertex, weight)]; n: the interpolated vertex normal there"""
    T = unit(*(sum(w * sh["T"][v][d] for v, w in weights) for d in range(3)))
    B = unit(*(sum(w * sh["B"][v][d] for v, w in weights) for d in range(3)))
    x, y, z = texel(sh["tex"], sum(w * sh["UV"][v][0] for v, w in weights), sum(w * sh["UV"][v][1] for v, w in weights))
    s = sh["scale"]
    return unit(*(T[d] * x * s + B[d] * y * s + n[d] * z for d in range(3)))


def local_matrix(node):
    if "matrix" in node:
        m = node["matrix"]
        return [[m[c * 4 + r] for c in range(4)] for r in range(4)]
    x, y, z, w = node.get("rotation", (0, 0, 0, 1))
    s, t = node.get("scale", (1, 1, 1)), node.get("translation", (0, 0, 0))
    r = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
         [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
         [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    return [[r[i][0] * s[0], r[i][1] * s[1], r[i][2] * s[2], t[i]] for i in range(3)] + [[0, 0, 0, 1]]


def matmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def world_matrices(nodes):
    parent = {c: i for i, n in enumerate(nodes) for c in n.get("children", [])}
    cache = {}

    def world(i, depth=0):
        if i not in cache:
            if depth > len(nodes):
                raise GLBError("the node hierarchy has a cycle")
            m = local_matrix(nodes[i])
            cache[i] = matmul(world(parent[i], depth + 1), m) if i in parent else m
        return cache[i]
    return [world(i) for i in range(len(nodes))]


def cofactor3(m):
    """cofactor matrix C = det(m) * inverse(m)^T, and det(m)"""
    (a, b, c), (d, e, f), (g, h, i) = m
    cof = [[e * i - f * h, f * g - d * i, d * h - e * g],
           [c * h - b * i, a * i - c * g, b * g - a * h],
           [b * f - c * e, c * d - a * f, a * e - b * d]]
    return cof, a * cof[0][0] + b * cof[0][1] + c * cof[0][2]


def unit(x, y, z):
    length = math.sqrt(x * x + y * y + z * z)
    return (x / length, y / length, z / length) if length > 1e-12 else (0.0, 0.0, 0.0)


def load_parts(path, names, exclude, maps=True):
    """world-space triangle meshes: one part per (node, triangle primitive); maps: read normal maps (the candidate's)"""
    g, binary, sha = read_glb(path)
    nodes, meshes = g.get("nodes", []), g.get("meshes", [])
    worlds = world_matrices(nodes)
    parts, matched, skipped, images = [], set(), 0, {}
    for ni, node in enumerate(nodes):
        if "mesh" not in node:
            continue
        name = node.get("name", f"node{ni}")
        hits = names & {name, meshes[node["mesh"]].get("name", "")}
        if (names and not hits) or any(name.startswith(p) for p in exclude):
            continue
        matched |= hits
        m = worlds[ni]
        cof, det = cofactor3([row[:3] for row in m[:3]])
        if not math.isfinite(det) or abs(det) < 1e-30:
            raise GLBError(f"{path}: node {name!r} has a singular or non-finite world transform")
        sign = 1.0 if det > 0 else -1.0
        (m00, m01, m02, m03), (m10, m11, m12, m13), (m20, m21, m22, m23) = m[:3]
        (c00, c01, c02), (c10, c11, c12), (c20, c21, c22) = cof
        for prim in meshes[node["mesh"]]["primitives"]:
            if prim.get("mode", 4) != 4:
                skipped += 1
                continue
            at = prim["attributes"]
            if "NORMAL" not in at:
                raise GLBError(f"{path}: node {name!r} has a primitive without NORMAL")
            pos, nor = accessor(g, binary, at["POSITION"], True), accessor(g, binary, at["NORMAL"], True)
            count = len(pos) // 3
            idx = accessor(g, binary, prim["indices"]) if "indices" in prim else range(count)
            if len(idx) % 3 or (len(idx) and max(idx) >= count) or len(nor) != len(pos):
                raise GLBError(f"{path}: node {name!r} has malformed indices or attribute counts")
            P, N, bad, nonunit = [], [], set(), 0
            for v in range(count):
                x, y, z, a, b, c = pos[3 * v], pos[3 * v + 1], pos[3 * v + 2], nor[3 * v], nor[3 * v + 1], nor[3 * v + 2]
                if not math.isfinite(x + y + z + a + b + c):
                    bad.add(v)
                elif abs(math.sqrt(a * a + b * b + c * c) - 1.0) > 1e-3:
                    nonunit += 1
                P.append((m00 * x + m01 * y + m02 * z + m03, m10 * x + m11 * y + m12 * z + m13, m20 * x + m21 * y + m22 * z + m23))
                N.append(unit(sign * (c00 * a + c01 * b + c02 * c), sign * (c10 * a + c11 * b + c12 * c),
                              sign * (c20 * a + c21 * b + c22 * c)))
            I = [(idx[k], idx[k + 1], idx[k + 2]) for k in range(0, len(idx), 3)]
            sh = shading(g, binary, prim, [row[:3] for row in m[:3]], sign, images) if maps else None
            if isinstance(sh, dict):
                if len(sh["T"]) != count or len(sh["UV"]) != count:
                    sh = "TANGENT or UV count differs from POSITION"
                else:
                    sh["B"] = [tuple(sh["W"][v] * x for x in unit(n[1] * t[2] - n[2] * t[1], n[2] * t[0] - n[0] * t[2],
                                                                    n[0] * t[1] - n[1] * t[0])) for v, (n, t) in enumerate(zip(N, sh["T"]))]
            row = name + (f" / {g['materials'][prim['material']].get('name', prim['material'])}" if "material" in prim else "")
            parts.append(dict(node=name, row=row, P=P, N=N, I=I, bad=bad, nonunit=nonunit, mirrored=det < 0, shade=sh))
    if names - matched:
        raise GLBError(f"{path}: no node or mesh named {sorted(names - matched)}")
    info = dict(file=str(path), sha256=sha, nodes=sorted({p["node"] for p in parts}),
                triangles=sum(len(p["I"]) for p in parts), skipped_non_triangle_primitives=skipped)
    return parts, info


def triangle_area_normal(a, b, c):
    e1x, e1y, e1z = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    e2x, e2y, e2z = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx, ny, nz = e1y * e2z - e1z * e2y, e1z * e2x - e1x * e2z, e1x * e2y - e1y * e2x
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    return length / 2, ((nx / length, ny / length, nz / length) if length > 0 else None), (e1x, e1y, e1z), (e2x, e2y, e2z)


# ----------------------------------------------------------------- reference search
def closest_bary(d1, d2, d00, d01, d11):
    """barycentrics of the triangle point closest to p (Ericson, Real-Time Collision Detection 5.1.5); d1 = e1.(p-a),
    d2 = e2.(p-a), dIJ = eI.eJ"""
    if d1 <= 0 and d2 <= 0:
        return 1.0, 0.0, 0.0
    d3, d4 = d1 - d00, d2 - d01
    if d3 >= 0 and d4 <= d3:
        return 0.0, 1.0, 0.0
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        v = d1 / (d1 - d3)
        return 1.0 - v, v, 0.0
    d5, d6 = d1 - d01, d2 - d11
    if d6 >= 0 and d5 <= d6:
        return 0.0, 0.0, 1.0
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        w = d2 / (d2 - d6)
        return 1.0 - w, 0.0, w
    va = d3 * d6 - d5 * d4
    if va <= 0 and d4 - d3 >= 0 and d5 - d6 >= 0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return 0.0, 1.0 - w, w
    den = 1.0 / (va + vb + vc)
    return 1.0 - (vb + vc) * den, vb * den, vc * den


class Reference:
    def __init__(self, parts, radius, flat_deg, degenerate_area, big_cells=BIG_CELLS):
        self.radius, self.r2 = radius, radius * radius
        cos_flat = math.cos(math.radians(flat_deg))
        T, extent, self.skipped = [], [], 0
        for part in parts:
            P, N, bad = part["P"], part["N"], part["bad"]
            for i, j, k in part["I"]:
                if i in bad or j in bad or k in bad:
                    self.skipped += 1
                    continue
                a, b, c = P[i], P[j], P[k]
                area, q, e1, e2 = triangle_area_normal(a, b, c)
                d00, d01, d11 = e1[0] * e1[0] + e1[1] * e1[1] + e1[2] * e1[2], e1[0] * e2[0] + e1[1] * e2[1] + e1[2] * e2[2], \
                    e2[0] * e2[0] + e2[1] * e2[1] + e2[2] * e2[2]
                den = d00 * d11 - d01 * d01
                if area <= degenerate_area or q is None or den <= 0:
                    self.skipped += 1
                    continue
                na, nb, nc = N[i], N[j], N[k]
                curved = min(sum(x * y for x, y in zip(na, nb)), sum(x * y for x, y in zip(nb, nc)),
                             sum(x * y for x, y in zip(na, nc))) < cos_flat
                lo = [min(a[d], b[d], c[d]) - radius for d in range(3)]
                hi = [max(a[d], b[d], c[d]) + radius for d in range(3)]
                extent.append(max(hi[d] - lo[d] for d in range(3)))
                T.append((*a, *e1, *e2, *q, d00, d01, d11, 1.0 / den, *na, *nb, *nc, *lo, *hi, curved))
        if not T:
            raise GLBError("the reference has no usable triangles")
        self.T = T
        self.h = max(2 * radius, sorted(extent)[len(extent) // 2])
        levels, self.big = [(1.0 / (self.h * 16 ** k), {}) for k in range(4)], []
        for t, tri in enumerate(T):
            for inv, grid in levels:
                lo, hi = [math.floor(v * inv) for v in tri[25:28]], [math.floor(v * inv) for v in tri[28:31]]
                if (hi[0] - lo[0] + 1) * (hi[1] - lo[1] + 1) * (hi[2] - lo[2] + 1) <= big_cells:
                    for x in range(lo[0], hi[0] + 1):
                        for y in range(lo[1], hi[1] + 1):
                            for z in range(lo[2], hi[2] + 1):
                                grid.setdefault((x, y, z), []).append(t)
                    break
            else:
                self.big.append(t)                      # ponytail: tested against every point; fine for a few
        (self.inv_h, self.grid), self.coarse = levels[0], [level for level in levels[1:] if level[1]]
        self.binned = [sum(len(v) for v in grid.values()) for _, grid in levels]

    def query(self, p, normals):
        """None when no reference triangle is within the radius, else (distance^2, whether the triangle best matching
        normals[0] is curved, [best cosine to each normal])"""
        px, py, pz = p
        inv = self.inv_h
        cands = self.grid.get((math.floor(px * inv), math.floor(py * inv), math.floor(pz * inv)), ())
        if self.coarse or self.big:
            cands = [*cands, *self.big]
            for inv, grid in self.coarse:
                cands += grid.get((math.floor(px * inv), math.floor(py * inv), math.floor(pz * inv)), ())
        r, r2, T = self.radius, self.r2, self.T
        best_d2, best, curved = math.inf, [-2.0] * len(normals), False
        for t in cands:
            (ax, ay, az, e1x, e1y, e1z, e2x, e2y, e2z, qx, qy, qz, d00, d01, d11, iden,
             nax, nay, naz, nbx, nby, nbz, ncx, ncy, ncz, lox, loy, loz, hix, hiy, hiz, crv) = T[t]
            if px < lox or px > hix or py < loy or py > hiy or pz < loz or pz > hiz:
                continue
            wx, wy, wz = px - ax, py - ay, pz - az
            s = wx * qx + wy * qy + wz * qz
            if s > r or s < -r:
                continue
            d1, d2 = wx * e1x + wy * e1y + wz * e1z, wx * e2x + wy * e2y + wz * e2z
            v, w = (d11 * d1 - d01 * d2) * iden, (d00 * d2 - d01 * d1) * iden
            u = 1.0 - v - w
            if u >= -BARY_EPS and v >= -BARY_EPS and w >= -BARY_EPS:
                dist2 = s * s
            else:
                u, v, w = closest_bary(d1, d2, d00, d01, d11)
                ex, ey, ez = wx - v * e1x - w * e2x, wy - v * e1y - w * e2y, wz - v * e1z - w * e2z
                dist2 = ex * ex + ey * ey + ez * ez
                if dist2 > r2:
                    continue
            if dist2 < best_d2:
                best_d2 = dist2
            mx, my, mz = u * nax + v * nbx + w * ncx, u * nay + v * nby + w * ncy, u * naz + v * nbz + w * ncz
            length = math.sqrt(mx * mx + my * my + mz * mz)
            if length < 1e-12:
                continue
            for slot, (nx, ny, nz) in enumerate(normals):
                c = (mx * nx + my * ny + mz * nz) / length
                if c > best[slot]:
                    best[slot] = c
                    if slot == 0:
                        curved = crv
        return None if best_d2 == math.inf else (best_d2, curved, best)


# ----------------------------------------------------------------- the audit
def degrees(c):
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


def stats(values, scale=1.0):
    if not values:
        return None
    s, n = sorted(values), len(values)

    def pct(q):
        x = (n - 1) * q
        i = int(x)
        return s[i] + (s[min(i + 1, n - 1)] - s[i]) * (x - i)
    out = dict(points=n, median=round(pct(0.5) * scale, 4), p99=round(pct(0.99) * scale, 4), max=round(s[-1] * scale, 4))
    if scale == 1.0:
        out.update(over_2_pct=round(100.0 * (n - bisect.bisect_right(s, 2.0)) / n, 4),
                   over_5_pct=round(100.0 * (n - bisect.bisect_right(s, 5.0)) / n, 4))
    return out


KINDS = ("corners", "in_face", "face", "shaded", "flat", "curved", "pos_corners", "pos_in_face")


def summary(acc, unreachable, total):
    return dict(samples=total, unreachable=unreachable, unreachable_pct=round(100.0 * unreachable / total, 4) if total else 0.0,
                position_um=dict(corners=stats(acc["pos_corners"], 1e6), in_face=stats(acc["pos_in_face"], 1e6)),
                corners=stats(acc["corners"]), in_face=stats(acc["in_face"]), face=stats(acc["face"]), shaded=stats(acc["shaded"]),
                in_face_by_curvature=dict(flat=stats(acc["flat"]), curved=stats(acc["curved"])))


def verdict(label, s, th, failures):
    if not s["samples"] or s["samples"] == s["unreachable"]:
        failures.append(f"{label}: no point was compared")
        return
    if s["unreachable_pct"] > th["max_unreachable"]:
        failures.append(f"{label}: {s['unreachable_pct']} % of points have no reference within the radius (max {th['max_unreachable']})")
    for kind, key in (("in_face", "max_inface_over5"), ("corners", "max_corner_over5"), ("shaded", "max_shaded_over5")):
        if s[kind] and th[key] is not None and s[kind]["over_5_pct"] > th[key]:
            failures.append(f"{label}: {s[kind]['over_5_pct']} % of {kind} points over 5 degrees (max {th[key]})")


def audit(reference, candidate, names=(), ref_names=None, exclude=("HIT_",), radius=2e-5, flat_deg=0.5,
          degenerate_area=1e-12, max_inface_over5=0.5, max_corner_over5=0.5, max_unreachable=0.0, max_shaded_over5=None):
    t0 = time.perf_counter()
    rparts, rinfo = load_parts(reference, set(names if ref_names is None else ref_names), exclude, maps=False)
    cparts, cinfo = load_parts(candidate, set(names), exclude)
    ref = Reference(rparts, radius, flat_deg, degenerate_area)
    rinfo.update(skipped_degenerate_or_nonfinite=ref.skipped, grid_cell_m=ref.h, grid_entries_per_level=ref.binned,
                 unbinned_triangles=len(ref.big))
    acc, nodes = {k: [] for k in KINDS}, {}
    totals = dict(samples=0, unreachable=0)
    defects = dict(degenerate_triangles=0, nonfinite_triangles=0, nonunit_normals=sum(p["nonunit"] for p in cparts))
    shaded_skipped = [dict(node=p["node"], reason=p["shade"]) for p in cparts if isinstance(p["shade"], str)]

    for part in cparts:
        P, N, bad, sh = part["P"], part["N"], part["bad"], part["shade"]
        mapped = isinstance(sh, dict)
        node = nodes.setdefault(part["row"], dict(triangles=0, samples=0, unreachable=0, acc={k: [] for k in KINDS}))
        node["triangles"] += len(part["I"])
        vcache, ecache = {}, {}

        def record(res, kind, pos_kind, shade_slot):
            totals["samples"] += 1
            node["samples"] += 1
            if res is None:
                totals["unreachable"] += 1
                node["unreachable"] += 1
                return
            angle, dist = degrees(res[2][0]), math.sqrt(res[0])
            for a in (acc, node["acc"]):
                a[kind].append(angle)
                a[pos_kind].append(dist)
                if kind == "in_face":
                    a["curved" if res[1] else "flat"].append(angle)
                if shade_slot is not None:
                    a["shaded"].append(degrees(res[2][shade_slot]))

        for i, j, k in part["I"]:
            if i in bad or j in bad or k in bad:
                defects["nonfinite_triangles"] += 1
                continue
            area, face, _, _ = triangle_area_normal(P[i], P[j], P[k])
            if area <= degenerate_area:
                defects["degenerate_triangles"] += 1
                face = None
            elif part["mirrored"]:
                face = (-face[0], -face[1], -face[2])
            if mapped:      # slot 1 holds the mapped normal; a triangle with no UV area is not shaded by the map
                (ua, va), (ub, vb), (uc, vc) = sh["UV"][i], sh["UV"][j], sh["UV"][k]
                slot = 1 if abs((ub - ua) * (vc - va) - (uc - ua) * (vb - va)) > 1e-12 else None
            else:           # no normal map: the interpolated normal shades; a map that cannot be applied: not measured
                slot = 0 if sh is None else None
            for v in (i, j, k):
                res = vcache.get(v, MISSING)
                if res is MISSING:
                    res = vcache[v] = ref.query(P[v], (N[v], shaded(sh, ((v, 1.0),), N[v])) if mapped else (N[v],))
                record(res, "corners", "pos_corners", slot)
            for x, y in ((i, j), (j, k), (k, i)):
                key = (x, y) if x < y else (y, x)
                res = ecache.get(key, MISSING)
                if res is MISSING:
                    p = tuple((P[x][d] + P[y][d]) / 2 for d in range(3))
                    n = unit(*(N[x][d] + N[y][d] for d in range(3)))
                    res = ecache[key] = ref.query(p, (n, shaded(sh, ((x, 0.5), (y, 0.5)), n)) if mapped else (n,))
                record(res, "in_face", "pos_in_face", slot)
            p = tuple((P[i][d] + P[j][d] + P[k][d]) / 3 for d in range(3))
            n = unit(*(N[i][d] + N[j][d] + N[k][d] for d in range(3)))
            normals = (n, shaded(sh, ((i, 1 / 3), (j, 1 / 3), (k, 1 / 3)), n)) if mapped else (n,)
            res = ref.query(p, normals + ((face,) if face else ()))
            record(res, "in_face", "pos_in_face", slot)
            if res is not None and face is not None:
                acc["face"].append(degrees(res[2][-1]))
                node["acc"]["face"].append(degrees(res[2][-1]))

    th = dict(max_inface_over5=max_inface_over5, max_corner_over5=max_corner_over5, max_unreachable=max_unreachable,
              max_shaded_over5=max_shaded_over5)
    overall = summary(acc, totals["unreachable"], totals["samples"])
    failures = []
    verdict("overall", overall, th, failures)
    per_row = {}
    for name, nd in sorted(nodes.items()):
        per_row[name] = dict(triangles=nd["triangles"], **summary(nd["acc"], nd["unreachable"], nd["samples"]))
        verdict(name, per_row[name], th, failures)
    failures += [f"candidate: {v} {k.replace('_', ' ')}" for k, v in defects.items() if v]
    return dict(reference=rinfo, candidate=cinfo, radius_m=radius, flat_deg=flat_deg, thresholds=th, candidate_defects=defects,
                shaded_skipped=shaded_skipped, **overall, rows=per_row, failures=failures, passed=not failures,
                seconds=round(time.perf_counter() - t0, 2))


def describe(r):
    def s(x, unit_="deg"):
        return "-" if not x else (f"median {x['median']} p99 {x['p99']} max {x['max']} {unit_}"
                                  + (f", >2: {x['over_2_pct']} %, >5: {x['over_5_pct']} %" if "over_5_pct" in x else ""))
    out = [f"reference {r['reference']['file']}: {r['reference']['triangles']} triangles; candidate {r['candidate']['file']}: "
           f"{r['candidate']['triangles']} triangles; radius {r['radius_m'] * 1e6:g} um; {r['seconds']} s",
           f"samples {r['samples']}, unreachable {r['unreachable']} ({r['unreachable_pct']} %)",
           f"position at corners:  {s(r['position_um']['corners'], 'um')}",
           f"position in faces:    {s(r['position_um']['in_face'], 'um')}",
           f"corner normals:       {s(r['corners'])}",
           f"in-face normals:      {s(r['in_face'])}",
           f"  on flat reference:  {s(r['in_face_by_curvature']['flat'])}",
           f"  on curved reference:{s(r['in_face_by_curvature']['curved'])}",
           f"face (flat) normals:  {s(r['face'])}",
           f"shaded (normal map):  {s(r['shaded'])}"]
    out += [f"  shaded measure skipped on {x['node']}: {x['reason']}" for x in r["shaded_skipped"]]
    for name, nd in r["rows"].items():
        out.append(f"  {name}: {nd['triangles']} triangles; in-face {s(nd['in_face'])}; shaded {s(nd['shaded'])}; "
                   f"unreachable {nd['unreachable']}")
    out += [f"FAIL: {f}" for f in r["failures"]] + ["NORMAL_AUDIT " + ("PASS" if r["passed"] else "FAIL")]
    return "\n".join(out)


# ----------------------------------------------------------------- fixtures
def write_glb(path, parts, root=None, **top):
    """parts: [(name, positions, normals, triangles, node fields[, dict(uv, tangent, png)])], all children of one ROOT
    node (root: its TRS); a part with uv gets TEXCOORD_0, TANGENT and the PNG as its normal map; top: extra glTF keys"""
    blob = bytearray()
    g = dict(asset=dict(version="2.0", generator="normal_audit.py fixtures"), scene=0, scenes=[dict(nodes=[0])],
             nodes=[dict(name="ROOT", children=list(range(1, len(parts) + 1)), **(root or {}))],
             meshes=[], accessors=[], bufferViews=[], buffers=[], **top)

    def view(raw):
        g["bufferViews"].append(dict(buffer=0, byteOffset=len(blob), byteLength=len(raw)))
        blob.extend(raw)
        blob.extend(bytes(-len(blob) % 4))
        return len(g["bufferViews"]) - 1

    def put(values, code, comp, kind, count, **extra):
        data = array(code, values)
        if sys.byteorder == "big":
            data.byteswap()
        g["accessors"].append(dict(bufferView=view(data.tobytes()), componentType=comp, count=count, type=kind, **extra))
        return len(g["accessors"]) - 1
    for name, P, N, I, fields, *more in parts:
        at = dict(POSITION=put([c for p in P for c in p], "f", 5126, "VEC3", len(P), min=[min(p[d] for p in P) for d in range(3)],
                               max=[max(p[d] for p in P) for d in range(3)]),
                  NORMAL=put([c for n in N for c in n], "f", 5126, "VEC3", len(N)))
        prim = dict(attributes=at, indices=put([c for t in I for c in t], "I", 5125, "SCALAR", 3 * len(I)))
        if more:
            at["TEXCOORD_0"] = put([c for t in more[0]["uv"] for c in t], "f", 5126, "VEC2", len(P))
            at["TANGENT"] = put([c for t in more[0]["tangent"] for c in t], "f", 5126, "VEC4", len(P))
            g.setdefault("images", []).append(dict(mimeType="image/png", bufferView=view(more[0]["png"])))
            g.setdefault("textures", []).append(dict(source=len(g["images"]) - 1))
            g.setdefault("materials", []).append(dict(normalTexture=dict(index=len(g["textures"]) - 1)))
            prim["material"] = len(g["materials"]) - 1
        g["meshes"].append(dict(name=name, primitives=[prim]))
        g["nodes"].append(dict(name=name, mesh=len(g["meshes"]) - 1, **(fields or {})))
    g["buffers"].append(dict(byteLength=len(blob)))
    js = json.dumps(g, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    Path(path).write_bytes(struct.pack("<4sII", b"glTF", 2, 28 + len(js) + len(blob)) + struct.pack("<I4s", len(js), b"JSON")
                           + js + struct.pack("<I4s", len(blob), b"BIN\0") + bytes(blob))


def profile(nw, nf, ns, wall=0.010, radius=0.0001, side=0.005):
    """(x, y, nx, ny): a flat wall along -x..0 at y = 0, a fillet of `radius` (tangent at x = 0), a side wall down from it"""
    pts = [(-wall + wall * i / nw, 0.0, 0.0, 1.0) for i in range(nw + 1)]
    for j in range(1, nf + 1):
        a = math.pi / 2 * j / nf
        pts.append((radius * math.sin(a), radius * math.cos(a) - radius, math.sin(a), math.cos(a)))
    return pts + [(radius, -radius - side * j / ns, 1.0, 0.0) for j in range(1, ns + 1)]


def extrude(pts, cols, zs):
    """profile columns x z values; two triangles per quad, wound outward"""
    P = [(pts[c][0], pts[c][1], z) for c in cols for z in zs]
    N = [(pts[c][2], pts[c][3], 0.0) for c in cols for z in zs]
    m, I = len(zs), []
    for a in range(len(cols) - 1):
        for b in range(m - 1):
            v = a * m + b
            I += [(v, v + 1, v + m), (v + m, v + 1, v + m + 1)]
    return P, N, I


def to_local(P, N, m):
    """positions and unit normals that m maps onto P and N"""
    lin = [row[:3] for row in m[:3]]
    cof, det = cofactor3(lin)
    inv = [[cof[j][i] / det for j in range(3)] for i in range(3)]
    t = [m[i][3] for i in range(3)]
    lp = [tuple(sum(inv[i][k] * (p[k] - t[k]) for k in range(3)) for i in range(3)) for p in P]
    ln = [unit(*(sum(lin[k][i] * n[k] for k in range(3)) for i in range(3))) for n in N]   # M^T n
    return lp, ln


def fixture_parts(nw=100, nf=16, ns=50, nz=40, length=0.010):
    """reference, bad candidate and good candidate (good in its parent's local frame) as (P, N, I)"""
    pts = profile(nw, nf, ns)
    zs = [length * k / nz for k in range(nz + 1)]
    last, q = len(pts) - 1, nf // 4
    coarse = [zs[k] for k in range(0, nz + 1, nz // 4)]
    reference = extrude(pts, range(len(pts)), zs)
    bad = extrude(pts, [0, nw + q, nw + 2 * q, nw + 3 * q, nw + nf, last], coarse)
    good = extrude(pts, [0, nw, nw + q, nw + 2 * q, nw + 3 * q, nw + nf, last], coarse)
    return reference, bad, good


GOOD_ROOT = dict(rotation=[math.sin(math.radians(15)) / math.sqrt(2), math.sin(math.radians(15)) / math.sqrt(2), 0.0,
                           math.cos(math.radians(15))], translation=[0.01, -0.02, 0.005])
GOOD_CHILD = dict(scale=[2.0, 0.5, 1.0])


def make_fixtures(directory):
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    reference, bad, good = fixture_parts()
    write_glb(d / "reference.glb", [("VIS_PART", *reference, None)])
    write_glb(d / "candidate_bad.glb", [("VIS_PART", *bad, None)])
    m = matmul(local_matrix(GOOD_ROOT), local_matrix(GOOD_CHILD))
    write_glb(d / "candidate_good.glb", [("VIS_PART", *to_local(good[0], good[1], m), good[2], GOOD_CHILD)], GOOD_ROOT)
    return [d / n for n in ("reference.glb", "candidate_bad.glb", "candidate_good.glb")]


# ----------------------------------------------------------------- self-test
FILTER_PNG = ("iVBORw0KGgoAAAANSUhEUgAAAAYAAAAFCAIAAADpOgqxAAAAaklEQVR4nAFfAKD/AEQggjz95vHCazD5DsfdAeSIdQE0og/Xa/W4YdRLAwjv"
              "BtB5+TsCYGnGKFKTejwAUyqxAlJhfwzjA4pTUTzRN7no7XGDYhI1jdcOoQSgrqsCyUp9HNlFyjNnxH+N4EofRysyEcF0LAAAAABJRU5ErkJggg==")
FILTER_PNG_SHA = "5221992d37ebccd74e0bbc1d649ca515d361bc42c5d53eeef82815380620298b"   # 6 x 5 RGB, rows filtered 0..4


def self_test():
    problems = []

    def check(cond, msg):
        if not cond:
            problems.append(msg)
    with tempfile.TemporaryDirectory() as tmp:
        ref, bad, good = make_fixtures(tmp)
        bad_parts = fixture_parts()[1]
        r = audit(ref, bad)
        print("bad candidate:", r["position_um"], r["corners"], r["in_face"], r["face"], sep="\n  ")
        check(not r["passed"], "bad candidate passed")
        check(r["unreachable"] == 0, f"bad: {r['unreachable']} unreachable points")
        check(r["position_um"]["corners"]["max"] < 0.01, f"bad: corner position {r['position_um']['corners']}")
        check(r["position_um"]["in_face"]["max"] < 10, f"bad: in-face position {r['position_um']['in_face']}")
        check(r["corners"]["max"] < 0.01, f"bad: corner normals {r['corners']}")
        check(r["face"]["over_5_pct"] == 0, f"bad: face normals {r['face']}")   # flat wall ~0.04, 22.5-degree fillet chords ~3.8
        check(r["in_face"]["over_5_pct"] > 10 and 14 < r["in_face"]["max"] < 16, f"bad: in-face {r['in_face']}")
        check(r["in_face_by_curvature"]["flat"]["over_5_pct"] > 10, "bad: in-face error is not on the flat reference")
        check(any("in_face points over 5" in f for f in r["failures"]), f"bad: wrong failures {r['failures']}")
        check(any(f.startswith("VIS_PART:") for f in r["failures"]), "bad: no per-row verdict")
        r = audit(ref, good)
        print("good candidate (transformed parent):", r["in_face"], r["failures"], sep="\n  ")
        check(r["passed"] and r["unreachable"] == 0, f"good candidate failed: {r['failures']}")
        check(r["in_face"]["max"] < 0.05 and r["corners"]["max"] < 0.05, f"good: {r['in_face']} {r['corners']}")

        # the grid search against brute force (Ericson on every triangle), random points and normals around the surface
        small = Path(tmp) / "small.glb"
        write_glb(small, [("VIS_PART", *fixture_parts(nw=10, nf=8, ns=5, nz=8)[0], None)])
        rad = 3e-4
        search = Reference(load_parts(small, set(), ())[0], rad, 0.5, 0.0, big_cells=2)     # coarse levels and the flat list
        check(any(search.binned[1:]) and search.big, f"coarse levels not exercised: {search.binned}, {len(search.big)} unbinned")
        rng, misses = __import__("random").Random(3), 0
        for _ in range(400):
            tri = search.T[rng.randrange(len(search.T))]
            u, v = sorted((rng.random(), rng.random()))
            p = tuple(tri[d] + u * tri[3 + d] + (v - u) * tri[6 + d] + rng.uniform(-1.5, 1.5) * rad for d in range(3))
            n = unit(*(rng.uniform(-1, 1) for _ in range(3)))
            got, want_d2, want = search.query(p, (n,)), math.inf, -2.0
            for t in search.T:
                w = [p[d] - t[d] for d in range(3)]
                b = closest_bary(sum(w[d] * t[3 + d] for d in range(3)), sum(w[d] * t[6 + d] for d in range(3)), *t[12:15])
                e = [w[d] - b[1] * t[3 + d] - b[2] * t[6 + d] for d in range(3)]
                if sum(x * x for x in e) <= rad * rad:
                    want_d2 = min(want_d2, sum(x * x for x in e))
                    m = unit(*(b[0] * t[16 + d] + b[1] * t[19 + d] + b[2] * t[22 + d] for d in range(3)))
                    want = max(want, sum(m[d] * n[d] for d in range(3)))
            if (got is None) != (want_d2 == math.inf) or (got and (abs(got[0] - want_d2) > 1e-15 or abs(got[2][0] - want) > 1e-9)):
                misses += 1
        check(misses == 0, f"grid search disagrees with brute force at {misses} of 400 points")

        # the normal map: PNG decoding (all five filters), bilinear texels, wrap modes, then the shaded measure on the bad
        # candidate with an identity map (shaded = interpolated) and with a map tilting 7.5 degrees against the fillet's drag
        # along +T (the wall in-face error drops from 15 to about 7.5 degrees; a sign error in T would raise it to 22.5)
        check(hashlib.sha256(b"".join(png_rows(base64.b64decode(FILTER_PNG))[3])).hexdigest() == FILTER_PNG_SHA, "PNG decode")
        tex = (2, 2, 3, [bytes([0, 0, 0, 255, 255, 255]), bytes([255, 0, 0, 0, 255, 0])], 10497, 10497)
        check(texel(tex, 0.5, 0.5) == [0.0, 0.0, -0.5] and texel(tex, 0.25, 0.25) == [-1.0, -1.0, -1.0], "bilinear texel")
        check([wrap(-1, 2, m) for m in (10497, 33071, 33648)] == [1, 0, 0] and wrap(2, 2, 33648) == 1, "wrap modes")
        P, N, I = bad_parts
        for label, rgb in (("identity", (128, 128, 255)), ("repair", (111, 128, 254))):
            path = Path(tmp) / f"mapped_{label}.glb"
            raw = b"".join(b"\0" + bytes(rgb) * 2 for _ in range(2))
            png = b"\x89PNG\r\n\x1a\n" + b"".join(struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
                                              for kind, body in ((b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)),
                                                                 (b"IDAT", zlib.compress(raw)), (b"IEND", b"")))
            write_glb(path, [("VIS_PART", P, N, I, None, dict(uv=[(50 * (q[0] - q[1]), q[2] / 0.010) for q in P],
                                                                tangent=[(n[1], -n[0], 0.0, 1.0) for n in N], png=png))])
            r = audit(ref, path)
            check(not r["shaded_skipped"] and r["shaded"]["points"] == 280, f"{label} map: {r['shaded_skipped']} {r['shaded']}")
            if label == "identity":
                check(abs(r["shaded"]["max"] - r["in_face"]["max"]) < 0.5, f"identity map: {r['shaded']} vs {r['in_face']}")
            else:
                check(7 < r["shaded"]["max"] < 8, f"repair map: {r['shaded']}")

        # defects, a shifted candidate, an unknown node name, Draco
        (P, N, I), _, _ = fixture_parts(nw=4, nf=4, ns=2, nz=4)
        P, N = list(P), list(N)
        P += [(math.nan, 0.0, 0.0), P[5]]                       # P[5]: second profile column
        N += [(0.0, 1.0, 0.0), (0.0, 1.5, 0.0)]
        I = list(I) + [(0, 0, 1), (len(P) - 2, 0, 1), (0, 1, len(P) - 1)]
        defect = Path(tmp) / "defect.glb"
        write_glb(defect, [("VIS_PART", P, N, I, None)])
        r = audit(ref, defect)
        check(r["candidate_defects"] == dict(degenerate_triangles=1, nonfinite_triangles=1, nonunit_normals=1),
              f"defects: {r['candidate_defects']}")
        shifted = Path(tmp) / "shifted.glb"
        write_glb(shifted, [("VIS_PART", *fixture_parts()[2], None)], dict(translation=[0.001, 0.001, 0.0]))
        r = audit(ref, shifted)
        check(r["unreachable_pct"] == 100.0 and any("no point was compared" in f for f in r["failures"]), "shifted: not failed")
        for kwargs, want in ((dict(names=("NOPE",)), "no node or mesh named"), (dict(exclude=("VIS",)), "no usable triangles")):
            try:
                audit(ref, good, **kwargs)
                problems.append(f"{kwargs}: no error")
            except GLBError as exc:
                check(want in str(exc), f"{kwargs}: {exc}")
        draco = Path(tmp) / "draco.glb"
        write_glb(draco, [("VIS_PART", *bad_parts, None)], extensionsUsed=["KHR_draco_mesh_compression"])
        try:
            read_glb(draco)
            problems.append("Draco GLB accepted")
        except GLBError:
            pass
        with contextlib.redirect_stdout(io.StringIO()):
            code = main([str(ref), str(bad), "--json", str(Path(tmp) / "r.json")])
        check(code == 1, "CLI: bad candidate did not exit 1")
        check(json.loads((Path(tmp) / "r.json").read_text())["passed"] is False, "CLI: JSON report")
    for p in problems:
        print("FAIL:", p)
    print("self-test:", "PASS" if not problems else f"{len(problems)} FAILED")
    return 1 if problems else 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--self-test" in argv:
        return self_test()
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("reference", nargs="?", type=Path)
    ap.add_argument("candidate", nargs="?", type=Path)
    ap.add_argument("--make-fixtures", type=Path, metavar="DIR", help="write the synthetic demonstration GLBs")
    ap.add_argument("--node", action="append", default=[], help="node or mesh name to audit (repeatable; default all)")
    ap.add_argument("--ref-node", action="append", help="reference node or mesh names, if they differ from --node")
    ap.add_argument("--exclude", action="append", help="node-name prefix to skip (repeatable; default HIT_)")
    ap.add_argument("--radius", type=float, default=2e-5, help="search radius in metres (default 2e-5)")
    ap.add_argument("--flat-deg", type=float, default=0.5, help="curvature bin split, degrees (default 0.5)")
    ap.add_argument("--degenerate-area", type=float, default=1e-12, help="zero-area threshold, m^2 (default 1e-12)")
    ap.add_argument("--max-inface-over5", type=float, default=0.5, help="max %% of in-face points over 5 degrees")
    ap.add_argument("--max-corner-over5", type=float, default=0.5, help="max %% of corner points over 5 degrees")
    ap.add_argument("--max-unreachable", type=float, default=0.0, help="max %% of points without reference in radius")
    ap.add_argument("--max-shaded-over5", type=float, help="max %% of normal-mapped points over 5 degrees (default: not gated)")
    ap.add_argument("--json", type=Path, help="write the full report here")
    a = ap.parse_args(argv)
    if a.make_fixtures:
        for p in make_fixtures(a.make_fixtures):
            print("wrote", p)
        return 0
    if not (a.reference and a.candidate):
        ap.error("REFERENCE and CANDIDATE are required")
    try:
        r = audit(a.reference, a.candidate, a.node, a.ref_node, [e for e in (a.exclude or ["HIT_"]) if e], a.radius,
                  a.flat_deg, a.degenerate_area, a.max_inface_over5, a.max_corner_over5, a.max_unreachable, a.max_shaded_over5)
    except (GLBError, OSError, KeyError, IndexError, json.JSONDecodeError) as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(describe(r))
    if a.json:
        a.json.write_text(json.dumps(r, indent=1) + "\n")
    return 0 if r["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
