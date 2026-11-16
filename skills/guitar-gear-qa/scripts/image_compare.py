#!/usr/bin/env python3
"""Compare candidate captures with frozen reference captures: class A (identical) or class B (thresholded), per view.

  image_compare.py REFERENCE CANDIDATE [--class A|B] [--mask-colour #45484a] [--mask-tolerance 3]
                   [--roi NAME:X,Y,W,H ...] [--max-share 0.1] [--code 8] [--max-patch 16] [--max-p999 8] [--review 2]
                   [--diff PATH] [--crops DIR] [--json OUT.json]
  image_compare.py --self-test

REFERENCE and CANDIDATE are two PNG files, or two directories whose PNGs are paired by file name (a reference without a
candidate fails; candidates without a reference are listed). Declare the class before running the candidate:
  A  a change that must not touch pixels: every view (and ROI) pixel-identical. Pixels are decoded to RGBA (grey expanded,
     opaque alpha added), so a re-encoded but identical image passes; file SHA-256 is reported beside the pixel SHA-256.
  B  a change that may move pixels. Per view and per ROI, with d = the largest absolute difference over R, G, B and A:
     at most --max-share % (0.1) of counted pixels have d > --code (8); the largest 8-connected patch of such pixels is at
     most --max-patch px (16); the 99.9th percentile of d over counted pixels (linear interpolation, as numpy) is at most
     --max-p999 (8). Counted pixels: all, or with --mask-colour those of the REFERENCE more than --mask-tolerance codes from
     that colour in some channel (the page background is not the product).
Any view whose largest difference exceeds --review codes (2) needs a look: with --crops DIR a 1:1 sheet is written
(reference | candidate | difference x 8) around the 33 x 33 window with the most difference; review it by eye whatever the
verdict: a global score never excuses a local defect. --diff writes the full difference x 8 as a grey PNG (a file for one
pair, a directory for directory mode). --roi gives a region its own verdict (repeatable; every view in directory mode).
Thresholds are fixed before the run and never loosened to pass a candidate.

PNG support: 8-bit grey, grey+alpha, RGB and RGBA, non-interlaced, all five filter types; palette, 16-bit and interlaced
files are rejected with a message (re-save them as 8-bit RGB/RGBA). Colour chunks (gAMA, iCCP) are ignored: codes compare.
Exit 0 when every view passes, 1 when one fails, 2 on unreadable or unsupported input. Standard library only; a 1600 x 1200
RGBA pair takes seconds (Paeth-filtered rows decode in pure Python).
Ported from a case-study comparator (numpy and Pillow), whose metrics it reproduces on real capture pairs. Differences:
alpha is compared too (no effect on opaque captures); the background colour and ROIs are options; the crop window is
searched only around pixels over --review. As there, 200,000 or more pixels over --code report their count as the patch.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import random
import struct
import sys
import tempfile
import zlib
from array import array
from collections import Counter
from itertools import accumulate, compress, repeat
from operator import add, and_, sub
from pathlib import Path

SIGNATURE = b"\x89PNG\r\n\x1a\n"
CHANNELS = {0: 1, 2: 3, 4: 2, 6: 4}
X8 = bytes(min(255, 8 * i) for i in range(256))
PATCH_LIMIT = 200000
CROP = 160


class PNGError(ValueError):
    pass


# ----------------------------------------------------------------- PNG codec
def paeth_row(line, prev, bpp, sign):
    """un-filter (sign +1) or filter (sign -1) one Paeth row"""
    out = bytearray(line)
    src = out if sign > 0 else line
    for i in range(len(line)):
        a = src[i - bpp] if i >= bpp else 0
        b = prev[i]
        c = prev[i - bpp] if i >= bpp else 0
        pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
        out[i] = (line[i] + sign * (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
    return out


def unfilter(kind, line, prev, bpp):
    if kind == 0:
        return line
    if kind == 1:
        out = bytearray(line)
        for c in range(bpp):
            out[c::bpp] = bytes(map((255).__and__, accumulate(line[c::bpp])))
        return bytes(out)
    if kind == 2:
        return bytes(map((255).__and__, map(add, line, prev)))
    if kind == 3:
        out = bytearray(line)
        for i in range(len(out)):
            out[i] = (out[i] + (((out[i - bpp] if i >= bpp else 0) + prev[i]) >> 1)) & 255
        return bytes(out)
    if kind == 4:
        return bytes(paeth_row(line, prev, bpp, 1))
    raise PNGError(f"invalid filter type {kind}")


def filter_row(kind, row, prev, bpp):
    left = bytes(bpp) + row[:-bpp]
    if kind == 0:
        return row
    if kind == 1:
        return bytes((x - a) & 255 for x, a in zip(row, left))
    if kind == 2:
        return bytes((x - b) & 255 for x, b in zip(row, prev))
    if kind == 3:
        return bytes((x - ((a + b) >> 1)) & 255 for x, a, b in zip(row, left, prev))
    return bytes(paeth_row(row, prev, bpp, -1))


def to_rgba(row, ctype, w):
    if ctype == 6:
        return row
    out = bytearray(b"\xff" * (4 * w))
    grey = {0: row, 4: row[0::2]}.get(ctype)
    for c in range(3):
        out[c::4] = grey if grey is not None else row[c::3]
    if ctype == 4:
        out[3::4] = row[1::2]
    return bytes(out)


def read_png(path):
    """{w, h, rows: RGBA bytes per row, file_sha256, pixel_sha256}"""
    data = Path(path).read_bytes()
    if data[:8] != SIGNATURE:
        raise PNGError(f"{path}: not a PNG file")
    pos, idat, header = 8, [], None
    while pos + 12 <= len(data):
        length, kind = struct.unpack_from(">I4s", data, pos)
        body = data[pos + 8:pos + 8 + length]
        if len(body) != length or zlib.crc32(kind + body) != struct.unpack_from(">I", data, pos + 8 + length)[0]:
            raise PNGError(f"{path}: corrupt {kind.decode('latin-1')} chunk (truncated or CRC mismatch)")
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
        pos += 12 + length
    if header is None:
        raise PNGError(f"{path}: no IHDR chunk")
    w, h, depth, ctype, _, _, interlace = header
    if ctype == 3:
        raise PNGError(f"{path}: palette PNGs are not supported; re-save as 8-bit RGB or RGBA")
    if depth != 8 or ctype not in CHANNELS:
        raise PNGError(f"{path}: bit depth {depth}, colour type {ctype} not supported; re-save as 8-bit grey, RGB or RGBA")
    if interlace:
        raise PNGError(f"{path}: interlaced (Adam7) PNGs are not supported; re-save without interlacing")
    raw = zlib.decompress(b"".join(idat))
    bpp = CHANNELS[ctype]
    stride = w * bpp
    if len(raw) != h * (stride + 1):
        raise PNGError(f"{path}: image data has {len(raw)} bytes, expected {h * (stride + 1)}")
    rows, prev = [], bytes(stride)
    for y in range(h):
        start = y * (stride + 1)
        prev = unfilter(raw[start], raw[start + 1:start + 1 + stride], prev, bpp)
        rows.append(to_rgba(prev, ctype, w))
    pixels = hashlib.sha256(struct.pack(">II", w, h))
    for r in rows:
        pixels.update(r)
    return dict(w=w, h=h, rows=rows, file_sha256=hashlib.sha256(data).hexdigest(), pixel_sha256=pixels.hexdigest())


def png_bytes(w, h, rows, ctype=6, filters=(0,)):
    """encode rows (already in ctype's layout); row y uses filters[y % len(filters)]"""
    bpp = CHANNELS[ctype]
    raw, prev = bytearray(), bytes(w * bpp)
    for y, row in enumerate(rows):
        kind = filters[y % len(filters)]
        raw.append(kind)
        raw += filter_row(kind, bytes(row), prev, bpp)
        prev = bytes(row)

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    return (SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, ctype, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b""))


# ----------------------------------------------------------------- comparison
def difference(a, b):
    """per row: bytes of max |a - b| over the 4 channels"""
    out = []
    for ra, rb in zip(a["rows"], b["rows"]):
        if ra == rb:
            out.append(bytes(len(ra) // 4))
        else:
            out.append(bytes(map(max, *(map(abs, map(sub, ra[c::4], rb[c::4])) for c in range(4)))))
    return out


def counted(ref, colour, tolerance):
    """per row: bytes, 1 where the reference pixel is more than `tolerance` codes from `colour` (None: count all)"""
    if colour is None:
        return None
    return [bytes(map(tolerance.__lt__, map(max, *(map(abs, map(sub, r[c::4], repeat(colour[c]))) for c in range(3)))))
            for r in ref["rows"]]


def largest_patch(points):
    """pixels in the largest 8-connected patch"""
    todo, best = set(points), 0
    while todo:
        stack, size = [todo.pop()], 0
        while stack:
            y, x = stack.pop()
            size += 1
            for q in ((y - 1, x - 1), (y - 1, x), (y - 1, x + 1), (y, x - 1), (y, x + 1), (y + 1, x - 1), (y + 1, x), (y + 1, x + 1)):
                if q in todo:
                    todo.remove(q)
                    stack.append(q)
        best = max(best, size)
    return best


def percentile(hist, n, q):
    """numpy-style (linear) percentile of n values given as a code histogram"""
    if n == 0:
        return 0.0
    pos = (n - 1) * q
    lo = int(pos)

    def value(k):
        total = 0
        for code, count in sorted(hist.items()):
            total += count
            if total > k:
                return code
        return max(hist)
    a, b = value(lo), value(min(lo + 1, n - 1))
    return a + (b - a) * (pos - lo)


def region(d, m, box, th, cls):
    x0, y0, w, h = box
    hist, over, peak = Counter(), [], 0
    for y in range(y0, y0 + h):
        dr = d[y][x0:x0 + w]
        mr = m[y][x0:x0 + w] if m else None
        if dr.count(0) == w:
            hist[0] += w if mr is None else sum(mr)
            continue
        peak = max(peak, max(dr))
        hist.update(dr if mr is None else compress(dr, mr))
        flags = map(th["code"].__lt__, dr) if mr is None else map(and_, map(th["code"].__lt__, dr), mr)
        over += [(y, x) for x in compress(range(x0, x0 + w), flags)]
    n = sum(hist.values())
    r = dict(box=list(box), identical=peak == 0, counted_pixels=n, max=peak,
             mae=round(sum(k * v for k, v in hist.items()) / n, 4) if n else 0.0,
             p999=round(percentile(hist, n, 0.999), 4), share_over_pct=round(100.0 * len(over) / max(n, 1), 4),
             largest_patch_px=largest_patch(over) if len(over) < PATCH_LIMIT else len(over))
    if cls == "A":
        r["passed"] = peak == 0
    else:
        r["passed"] = r["share_over_pct"] <= th["max_share"] and r["largest_patch_px"] <= th["max_patch"] and r["p999"] <= th["max_p999"]
        r["failed_on"] = [k for k, bad in (("share", r["share_over_pct"] > th["max_share"]),
                                           ("patch", r["largest_patch_px"] > th["max_patch"]), ("p999", r["p999"] > th["max_p999"])) if bad]
    return r


def worst_window(d, review, radius=16):
    """(y, x) whose (2 radius + 1)^2 box holds the most difference, among pixels over `review`"""
    h, w = len(d), len(d[0])
    sat = [array("q", bytes(8 * (w + 1)))]
    for row in d:
        sat.append(array("q", map(add, sat[-1], accumulate(row, initial=0))))
    best, at = -1, (0, 0)
    for y, row in enumerate(d):
        if max(row) <= review:
            continue
        y0, y1 = max(0, y - radius), min(h, y + radius + 1)
        for x in compress(range(w), map(review.__lt__, row)):
            x0, x1 = max(0, x - radius), min(w, x + radius + 1)
            s = sat[y1][x1] - sat[y0][x1] - sat[y1][x0] + sat[y0][x0]
            if s > best:
                best, at = s, (y, x)
    return at


def crop_sheet(a, b, d, review):
    y, x = worst_window(d, review)
    h, w = len(d), len(d[0])
    size_y, size_x = min(2 * CROP, h), min(2 * CROP, w)
    y0, x0 = max(0, min(y - CROP, h - size_y)), max(0, min(x - CROP, w - size_x))
    rows = []
    for yy in range(y0, y0 + size_y):
        line = bytearray()
        for src in (a["rows"][yy], b["rows"][yy]):
            rgb = bytearray(3 * size_x)
            seg = src[4 * x0:4 * (x0 + size_x)]
            for c in range(3):
                rgb[c::3] = seg[c::4]
            line += rgb
        grey = d[yy][x0:x0 + size_x].translate(X8)
        rgb = bytearray(3 * size_x)
        for c in range(3):
            rgb[c::3] = grey
        rows.append(bytes(line + rgb))
    return png_bytes(3 * size_x, size_y, rows, ctype=2), [x0, y0, size_x, size_y]


def compare_pair(ref_path, cand_path, a, cls, th, rois, diff_path=None, crops=None):
    view = Path(ref_path).stem
    ref, cand = read_png(ref_path), read_png(cand_path)
    r = dict(view=view, reference=str(ref_path), candidate=str(cand_path), size=[ref["w"], ref["h"]],
             file_sha256=[ref["file_sha256"], cand["file_sha256"]], pixel_sha256=[ref["pixel_sha256"], cand["pixel_sha256"]])
    if (ref["w"], ref["h"]) != (cand["w"], cand["h"]):
        r.update(passed=False, error=f"size {ref['w']} x {ref['h']} vs {cand['w']} x {cand['h']}")
        return r
    d = difference(ref, cand)
    m = counted(ref, a.mask_colour, a.mask_tolerance)
    r.update(region(d, m, (0, 0, ref["w"], ref["h"]), th, cls))
    r["rois"] = {}
    for name, (x, y, w, h) in rois:
        if x < 0 or y < 0 or x + w > ref["w"] or y + h > ref["h"]:
            r["rois"][name] = dict(box=[x, y, w, h], passed=False, error="outside the image")
        else:
            r["rois"][name] = region(d, m, (x, y, w, h), th, cls)
    r["needs_review"] = r["max"] > th["review"]                 # unmasked, as the source
    if diff_path:
        Path(diff_path).write_bytes(png_bytes(ref["w"], ref["h"], [row.translate(X8) for row in d], ctype=0))
        r["diff"] = str(diff_path)
    if crops and r["needs_review"]:
        Path(crops).mkdir(parents=True, exist_ok=True)
        sheet, r["crop"] = crop_sheet(ref, cand, d, th["review"])
        out = Path(crops) / f"{view}__reference_candidate_diffx8.png"
        out.write_bytes(sheet)
        r["crop_sheet"] = str(out)
    r["passed"] = r["passed"] and all(v["passed"] for v in r["rois"].values())
    return r


def colour(text):
    t = text.lstrip("#")
    if len(t) != 6:
        raise argparse.ArgumentTypeError(f"{text!r}: expected #rrggbb")
    return tuple(int(t[i:i + 2], 16) for i in (0, 2, 4))


def roi(text):
    name, _, box = text.partition(":")
    try:
        x, y, w, h = (int(v) for v in box.split(","))
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r}: expected NAME:X,Y,W,H") from None
    if not name or w <= 0 or h <= 0:
        raise argparse.ArgumentTypeError(f"{text!r}: expected NAME:X,Y,W,H with W, H > 0")
    return name, (x, y, w, h)


def parser():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("reference", type=Path, help="reference PNG or directory")
    ap.add_argument("candidate", type=Path, help="candidate PNG or directory")
    ap.add_argument("--class", dest="cls", choices=("A", "B"), default="B")
    ap.add_argument("--mask-colour", "--mask-color", type=colour, help="#rrggbb background excluded from the counts")
    ap.add_argument("--mask-tolerance", type=int, default=3)
    ap.add_argument("--roi", type=roi, action="append", default=[], help="NAME:X,Y,W,H region with its own verdict")
    ap.add_argument("--max-share", type=float, default=0.1, help="max %% of counted pixels over --code (class B)")
    ap.add_argument("--code", type=int, default=8, help="per-pixel difference threshold, codes (class B)")
    ap.add_argument("--max-patch", type=int, default=16, help="max 8-connected patch over --code, pixels (class B)")
    ap.add_argument("--max-p999", type=float, default=8, help="max 99.9th percentile difference, codes (class B)")
    ap.add_argument("--review", type=int, default=2, help="crop-sheet trigger: largest difference over this, codes")
    ap.add_argument("--diff", type=Path, help="difference x 8 PNG (a directory in directory mode)")
    ap.add_argument("--crops", type=Path, help="directory for crop sheets of views that need review")
    ap.add_argument("--json", type=Path, help="write the report here")
    return ap


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--self-test" in argv:
        return self_test()
    a = parser().parse_args(argv)
    th = dict(max_share=a.max_share, code=a.code, max_patch=a.max_patch, max_p999=a.max_p999, review=a.review)
    views, extra = [], []
    try:
        if a.reference.is_dir():
            if not a.candidate.is_dir():
                raise PNGError("REFERENCE is a directory: CANDIDATE must be one too")
            if a.diff:
                a.diff.mkdir(parents=True, exist_ok=True)
            refs = sorted(a.reference.glob("*.png"))
            extra = sorted({p.name for p in a.candidate.glob("*.png")} - {p.name for p in refs})
            for p in refs:
                c = a.candidate / p.name
                if not c.is_file():
                    views.append(dict(view=p.stem, reference=str(p), passed=False, error="candidate missing"))
                    continue
                views.append(compare_pair(p, c, a, a.cls, th, a.roi, a.diff / f"{p.stem}_diffx8.png" if a.diff else None, a.crops))
        else:
            views.append(compare_pair(a.reference, a.candidate, a, a.cls, th, a.roi, a.diff, a.crops))
    except (PNGError, OSError, zlib.error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    ok = bool(views) and all(v["passed"] for v in views)
    for v in views:
        if "error" in v:
            print(f"{v['view']}: FAIL ({v['error']})")
            continue
        rois = "".join(f" | roi {k}: {'pass' if x['passed'] else 'FAIL'}" for k, x in v["rois"].items())
        print(f"{v['view']}: {'pass' if v['passed'] else 'FAIL'} identical={v['identical']} max={v['max']} p99.9={v['p999']} "
              f"over{th['code']}={v['share_over_pct']}% patch={v['largest_patch_px']}px"
              + (" REVIEW" if v["needs_review"] else "") + rois)
    if extra:
        print(f"candidates without a reference (not compared): {extra}")
    print(f"CLASS {a.cls}: {'PASS' if ok else 'FAIL'} ({sum(v['passed'] for v in views)}/{len(views)} views)")
    if a.json:
        report = {"class": a.cls, "thresholds": th, "mask_colour": a.mask_colour, "mask_tolerance": a.mask_tolerance,
                  "passed": ok, "views": views, "unmatched_candidates": extra}
        a.json.write_text(json.dumps(report, indent=1) + "\n")
    return 0 if ok else 1


# ----------------------------------------------------------------- self-test
def self_test():
    problems = []

    def check(cond, msg):
        if not cond:
            problems.append(msg)

    def quiet(argv):
        with contextlib.redirect_stdout(io.StringIO()):
            return main(argv)
    rng = random.Random(7)
    for ctype, bpp in sorted(CHANNELS.items()):                     # round trip: every colour type x every filter
        w, h = 13, 9
        rows = [bytes(rng.randrange(256) for _ in range(w * bpp)) for _ in range(h)]
        for filters in ((0,), (1,), (2,), (3,), (4,), (4, 3, 2, 1, 0)):
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                f.write(png_bytes(w, h, rows, ctype, filters))
            got = read_png(f.name)
            Path(f.name).unlink()
            want = [to_rgba(r, ctype, w) for r in rows]
            check(got["rows"] == want, f"round trip colour type {ctype}, filters {filters}")
    for line, prev, want in (([1, 2, 3], [100, 50, 200], [101, 52, 203]),        # Paeth by hand: predictor b, b, b
                             ([10, 5], [0, 0], [10, 15]),                        # a
                             ([251, 1], [15, 20], [10, 16])):                    # b, then c (a=10 b=20 c=15)
        check(unfilter(4, bytes(line), bytes(prev), 1) == bytes(want), f"Paeth row {line} over {prev}")
    for label, mutate, want in (("16-bit", lambda b: b[:24] + bytes([16]) + b[25:], "bit depth 16"),
                                ("palette", lambda b: b[:25] + bytes([3]) + b[26:], "palette"),
                                ("interlaced", lambda b: b[:28] + bytes([1]) + b[29:], "interlaced")):
        body = bytearray(mutate(png_bytes(2, 2, [bytes(6), bytes(6)], 2)))
        body[29:33] = struct.pack(">I", zlib.crc32(bytes(body[12:29])))
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(bytes(body))
        try:
            read_png(f.name)
            problems.append(f"{label} PNG accepted")
        except PNGError as exc:
            check(want in str(exc), f"{label}: {exc}")
        Path(f.name).unlink()

    W, H = 256, 256
    base = [bytes((x * 7 + y * 3 + rng.randrange(40)) % 256 for x in range(W) for _ in range(3)) for y in range(H)]

    def edit(changes):
        rows = [bytearray(r) for r in base]
        for y, x, delta in changes:
            for c in range(3):
                v = rows[y][3 * x + c]
                rows[y][3 * x + c] = v + delta if v + delta <= 255 else v - delta
        return rows
    block = lambda y0, x0, h, w, delta: [(y, x, delta) for y in range(y0, y0 + h) for x in range(x0, x0 + w)]
    cases = {"same": edit([]), "one_code": edit(block(0, 0, 4, 64, 1)), "patch20": edit(block(100, 100, 4, 5, 30)),
             "patch16": edit(block(100, 100, 4, 4, 30)), "scattered20": edit([(20 * k, 9 * k + 3, 30) for k in range(1, 11)]
                                                                            + [(20 * k + 5, 200 - 9 * k, 30) for k in range(1, 11)]),
             "diagonal": edit(block(10, 10, 3, 3, 30) + block(13, 13, 3, 3, 30))}
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        (t / "ref").mkdir()
        (t / "cand").mkdir()
        (t / "ref" / "view.png").write_bytes(png_bytes(W, H, base, 2, (4, 1, 2, 3, 0)))
        for name, rows in cases.items():
            (t / "cand" / f"{name}.png").write_bytes(png_bytes(W, H, [bytes(r) for r in rows], 2, (1,)))

        def run(name, *extra):
            out = t / f"{name}.json"
            code = quiet([str(t / "ref" / "view.png"), str(t / "cand" / f"{name}.png"), "--json", str(out), *extra])
            return code, json.loads(out.read_text())["views"][0]
        code, v = run("same", "--class", "A")
        check(code == 0 and v["identical"] and v["file_sha256"][0] != v["file_sha256"][1], f"same pixels, other filters: {code}")
        code, v = run("one_code", "--class", "A")
        check(code == 1 and v["max"] == 1, f"1-code change passed class A: {code}")
        code, v = run("one_code")
        check(code == 0 and v["p999"] == 1.0 and not v["needs_review"], f"1-code change failed class B: {code} {v}")
        code, v = run("patch20", "--crops", str(t / "crops"), "--diff", str(t / "diff.png"))
        check(code == 1 and v["failed_on"] == ["patch"] and v["largest_patch_px"] == 20 and v["share_over_pct"] < 0.1,
              f"20-px patch: {code} {v.get('failed_on')} {v.get('largest_patch_px')}")
        sheet, diff = read_png(v["crop_sheet"]), read_png(t / "diff.png")
        check((sheet["w"], sheet["h"]) == (3 * W, H) and diff["rows"][100][4 * 100] == 240, "crop sheet / difference image")
        code, v = run("patch16")
        check(code == 0 and v["largest_patch_px"] == 16, f"16-px patch: {code} {v['largest_patch_px']}")
        code, v = run("scattered20")
        check(code == 0 and v["largest_patch_px"] == 1, f"20 scattered pixels: {code} {v['largest_patch_px']}")
        code, v = run("diagonal")
        check(code == 1 and v["largest_patch_px"] == 18, f"diagonal blocks are one 8-connected patch: {v['largest_patch_px']}")
        code, v = run("patch20", "--roi", "hit:90,90,30,30", "--roi", "clean:0,150,100,100")
        check(code == 1 and not v["rois"]["hit"]["passed"] and v["rois"]["clean"]["passed"], f"ROI verdicts: {v['rois']}")
        code, v = run("patch20", "--class", "A", "--roi", "clean:0,150,100,100")
        check(v["rois"]["clean"]["passed"] and not v["passed"], "class A ROI")
        # mask: the reference pixels around the patch are the background colour, so the patch is not counted
        bg = tuple(base[100][300:303])
        masked = [bytearray(r) for r in base]
        for y in range(95, 110):
            masked[y][3 * 95:3 * 110] = bytes(bg) * 15
        (t / "ref_bg.png").write_bytes(png_bytes(W, H, [bytes(r) for r in masked], 2))
        patched = [bytearray(r) for r in masked]
        for y, x, delta in block(100, 100, 4, 5, 30):
            patched[y][3 * x:3 * x + 3] = bytes(c + delta if c + delta <= 255 else c - delta for c in patched[y][3 * x:3 * x + 3])
        (t / "cand_bg.png").write_bytes(png_bytes(W, H, [bytes(r) for r in patched], 2))
        hexbg = "#" + bytes(bg).hex()
        check(quiet([str(t / "ref_bg.png"), str(t / "cand_bg.png")]) == 1, "unmasked background patch passed")
        check(quiet([str(t / "ref_bg.png"), str(t / "cand_bg.png"), "--mask-colour", hexbg]) == 0, "masked background patch failed")
        # directory mode: one pair matches by name, one reference has no candidate
        (t / "cand" / "view.png").write_bytes((t / "cand" / "one_code.png").read_bytes())
        (t / "ref" / "lonely.png").write_bytes(png_bytes(W, H, base, 2))
        check(quiet([str(t / "ref"), str(t / "cand"), "--json", str(t / "dir.json")]) == 1, "directory mode with a missing candidate")
        rep = json.loads((t / "dir.json").read_text())
        check([v["passed"] for v in rep["views"]] == [False, True] and "patch20.png" in rep["unmatched_candidates"], "directory pairing")
    for p in problems:
        print("FAIL:", p)
    print("self-test:", "PASS" if not problems else f"{len(problems)} FAILED")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
