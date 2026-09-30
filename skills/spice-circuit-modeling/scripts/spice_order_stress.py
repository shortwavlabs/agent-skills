#!/usr/bin/env python3
"""Statement-order stress for a SPICE deck: same circuit, different element order, same answer?

Reorders only top-level element statements (a statement keeps its '+' continuation lines). The title,
dot-directives, comments, .subckt...ends and .control...endc blocks stay exactly where they are, so every
variant is the identical circuit; the script proves that before running anything.

Orders are keyed, not streamed: order `id` of stream `name` is always random.Random(f"{seed}:{name}:{id}"),
duplicates and the original order are skipped, and the number of UNIQUE orders is reported. Reseeding one
shared generator with the same seed for every run silently produces the same order N times; keyed orders
cannot. One order file is run in every engine, so engines are compared order for order.

  spice_order_stress.py DECK --count N --out DIR [--seed S] [--stream NAME]
        [--engine NAME=COMMAND ...]   COMMAND contains {deck}, e.g. "ngspice47=ngspice -b {deck}"
        [--fail-regex RE ...]         output patterns that mean the run failed (errors, aborted steps)
        [--expect-regex RE]           pattern that must appear (e.g. a printed operating-state flag)
  spice_order_stress.py --self-test

Each run is classified pass / failed (non-zero exit, timeout or a --fail-regex hit) / wrong-state
(completed but --expect-regex absent). Failures and wrong states are counted separately: a deck that
converges into the wrong operating point is not a convergence failure, and not a pass either.
Without --engine the reordered decks are only written and verified. Exit 1 if any run is not a pass.
"""

from __future__ import annotations

import argparse
import csv
import math
import random
import re
import shlex
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path


class StressError(RuntimeError):
    pass


def statements(lines: list[str]) -> tuple[list[list[str]], list[int]]:
    """Group lines into statements; return them and the indexes of reorderable top-level element statements."""
    st: list[list[str]] = []
    fixed: set[int] = set()
    block = None                      # closing keyword while inside .subckt or .control: nothing there moves
    for line in lines:
        low = line.strip().lower()
        if line.lstrip().startswith("+") and st:
            st[-1].append(line)
            continue
        st.append([line])
        if block:
            fixed.add(len(st) - 1)
            if low.startswith(block):
                block = None
        elif low.startswith((".subckt", ".control")):
            block = ".ends" if low.startswith(".subckt") else ".endc"
            fixed.add(len(st) - 1)
    slots = [i for i, s in enumerate(st)
             if i > 0 and i not in fixed and s[0].strip() and s[0].lstrip()[0] not in ".*"]
    return st, slots


def reordered(lines: list[str], order: list[int]) -> list[str]:
    st, slots = statements(lines)
    moved = [st[i] for i in slots]
    for slot, j in zip(slots, order):
        st[slot] = moved[j]
    return [line for s in st for line in s]


def permutation_ids(n: int, n_slots: int, seed: int | str, stream: str) -> list[tuple[int, list[int]]]:
    """n (id, order) pairs: pairwise-distinct, never the original order, reproducible from (seed, stream, id)."""
    available = math.factorial(n_slots) - 1 if n_slots < 20 else n
    if n > available:
        raise StressError(f"{n} unique orders requested but only {available} non-identity orders exist")
    seen, out, pid = {tuple(range(n_slots))}, [], 0
    while len(out) < n:
        order = list(range(n_slots))
        random.Random(f"{seed}:{stream}:{pid}").shuffle(order)
        if tuple(order) not in seen:
            seen.add(tuple(order))
            out.append((pid, order))
        pid += 1
        if pid > 100 * n + 10_000:
            raise StressError("could not draw enough unique orders")
    return out


def require_same_circuit(original: list[str], variant: list[str]) -> None:
    """Prove the variant is the same circuit: every fixed statement (title, directives, comments, .subckt and
    .control blocks) is unchanged at its statement position, and the movable element statements, each taken
    as a whole logical statement with its '+' continuations, form the same multiset. A continuation that
    ends up under the wrong element changes a statement and is rejected."""
    st_o, slots_o = statements(original)
    st_v, slots_v = statements(variant)
    canon = lambda s: "\n".join(line.strip() for line in s)
    if len(st_o) != len(st_v) or slots_o != slots_v:
        raise StressError("a reordered deck has a different statement structure")
    fixed = [i for i in range(len(st_o)) if i not in set(slots_o)]
    if any(canon(st_o[i]) != canon(st_v[i]) for i in fixed):
        raise StressError("a fixed statement (title, directive, comment, .subckt or .control block) moved or changed")
    if sorted(canon(st_o[i]) for i in slots_o) != sorted(canon(st_v[i]) for i in slots_v):
        raise StressError("a reordered deck does not contain exactly the original element statements")
    if variant == original:
        raise StressError("a 'reordered' deck is identical to the original order")


def classify(run: subprocess.CompletedProcess | None, fail_res: list[re.Pattern], expect_re: re.Pattern | None) -> str:
    if run is None:
        return "failed"          # timeout
    text = run.stdout + run.stderr
    if run.returncode != 0 or any(r.search(text) for r in fail_res):
        return "failed"
    if expect_re is not None and not expect_re.search(text):
        return "wrong-state"
    return "pass"


def stress(deck: Path, count: int, out: Path, seed: int | str, stream: str, engines: dict[str, str],
           fail_regex: list[str], expect_regex: str | None, timeout: float, log=print) -> list[dict]:
    lines = deck.read_text(errors="replace").replace("\r", "").split("\n")
    _, slots = statements(lines)
    if len(slots) < 2:
        raise StressError("fewer than two reorderable element statements")
    ids = permutation_ids(count, len(slots), seed, stream)
    out.mkdir(parents=True, exist_ok=True)
    fail_res = [re.compile(r, re.I | re.M) for r in fail_regex]
    expect_re = re.compile(expect_regex, re.I | re.M) if expect_regex else None
    rows = []
    for pid, order in ids:
        variant = reordered(lines, order)
        require_same_circuit(lines, variant)
        path = out / f"{deck.stem}_{stream}_{pid:05d}.cir"
        path.write_text("\n".join(variant))
        for name, cmd in engines.items():
            try:
                run = subprocess.run(shlex.split(cmd.format(deck=str(path))), capture_output=True, text=True,
                                     timeout=timeout)
            except subprocess.TimeoutExpired:
                run = None
            rows.append(dict(order_id=pid, engine=name, status=classify(run, fail_res, expect_re), deck=str(path)))
    log(f"{len(ids)} unique orders of {len(slots)} element statements (seed {seed}, stream {stream!r}); "
        f"circuit identity verified for every order")
    for name in engines:
        c = Counter(r["status"] for r in rows if r["engine"] == name)
        log(f"  {name}: {c['pass']} pass, {c['failed']} failed, {c['wrong-state']} wrong-state "
            f"of {sum(c.values())} runs")
    return rows


def self_test() -> int:
    problems = []
    deck_text = ("title\n.param A=1\nR1 a b 1k\nR2 b 0 2k\n+ tc1=0\nC1 a 0 1n\n"
                 ".subckt SUB p n\nR9 p n 1\nR8 p n 2\n.ends SUB\nX1 a 0 SUB\nV1 a 0 1\n"
                 ".control\nrun\nprint v(a)\n.endc\n.end")
    fake_engine = ("import re,sys\n"
                   "names=[l.split()[0] for l in open(sys.argv[1]) if re.match(r'^[RCXV]\\w* ', l)]\n"
                   "top=[n for n in names if n not in ('R9','R8')]\n"
                   "sys.exit(1) if top.index('R2') < top.index('R1') else None\n"
                   "print('STATE=OK' if top[0] != 'C1' else 'STATE=WRONG')\n")
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        deck = d / "deck.cir"
        deck.write_text(deck_text)
        engine = d / "fake_engine.py"
        engine.write_text(fake_engine)
        lines = deck_text.split("\n")
        _, slots = statements(lines)
        if len(slots) != 5:
            problems.append(f"expected 5 reorderable statements (R1 R2+ C1 X1 V1), found {len(slots)}")
        ids = permutation_ids(40, len(slots), 7, "primary")
        if len({tuple(o) for _, o in ids}) != 40 or any(o == list(range(len(slots))) for _, o in ids):
            problems.append("keyed permutations are not unique or include the original order")
        if ids != permutation_ids(40, len(slots), 7, "primary"):
            problems.append("keyed permutations are not reproducible")
        naive = set()
        for _ in range(40):          # the pitfall: reseeding a shared generator with the same seed every run
            order = list(range(len(slots)))
            random.Random(7).shuffle(order)
            naive.add(tuple(order))
        if len(naive) != 1:
            problems.append("pitfall demonstration unexpectedly produced distinct orders")
        variant = reordered(lines, ids[0][1])
        for first, last in ((".subckt", ".ends"), (".control", ".endc")):
            i0, i1 = lines.index(next(l for l in lines if l.startswith(first))), \
                lines.index(next(l for l in lines if l.startswith(last)))
            j0 = variant.index(lines[i0])   # statements may shift by continuation lines; the block must stay whole
            if variant[j0 : j0 + i1 - i0 + 1] != lines[i0 : i1 + 1]:
                problems.append(f"{first} block moved or changed")
        if not any(v.startswith("R2") and variant[i + 1].startswith("+") for i, v in enumerate(variant[:-1])):
            problems.append("continuation line separated from its statement")
        try:
            require_same_circuit(lines, lines)
            problems.append("identity order was not rejected")
        except StressError:
            pass
        # A continuation line re-attached under the wrong element: same physical lines, different circuit.
        bad = list(variant)
        k = next(i for i, line in enumerate(bad) if line.startswith("+"))
        cont = bad.pop(k)
        c1 = next(i for i, line in enumerate(bad) if line.startswith("C1 "))
        bad.insert(c1 + 1, cont)
        if sorted(bad) != sorted(lines):
            problems.append("continuation test did not preserve the physical line multiset")
        try:
            require_same_circuit(lines, bad)
            problems.append("continuation re-attached to the wrong element was not rejected")
        except StressError:
            pass
        moved = list(lines)
        j = moved.index(".param A=1")
        moved[j], moved[j + 1] = moved[j + 1], moved[j]       # a directive swapped with an element
        try:
            require_same_circuit(lines, moved)
            problems.append("a moved directive was not rejected")
        except StressError:
            pass
        try:
            permutation_ids(200, 5, 1, "x")
            problems.append("impossible request (more orders than exist) was not rejected")
        except StressError:
            pass
        rows = stress(deck, 30, d / "out", 7, "primary", {"fake": f"{sys.executable} {engine} {{deck}}"}, [],
                      r"STATE=OK", 30, log=lambda *_: None)
        expected = Counter()
        for r in rows:
            top = [l.split()[0] for l in Path(r["deck"]).read_text().split("\n")
                   if re.match(r"^[RCXV]\w* ", l) and l.split()[0] not in ("R9", "R8")]
            expected["failed" if top.index("R2") < top.index("R1") else
                     "wrong-state" if top[0] == "C1" else "pass"] += 1
        got = Counter(r["status"] for r in rows)
        if got != expected or not got["failed"] or not got["wrong-state"]:
            problems.append(f"classification mismatch: got {dict(got)}, expected {dict(expected)}")
    for p in problems:
        print("SELF-TEST FAILURE:", p)
    print(f"self-test: {'PASS' if not problems else 'FAIL'}")
    return 1 if problems else 0


def main() -> int:
    if "--self-test" in sys.argv[1:]:
        return self_test()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("deck", type=Path)
    ap.add_argument("--count", type=int, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--seed", default="1")
    ap.add_argument("--stream", default="primary", help="separate streams for separate corpora (primary, endpoints...)")
    ap.add_argument("--engine", action="append", default=[], help="NAME=COMMAND with {deck}")
    ap.add_argument("--fail-regex", action="append", default=[])
    ap.add_argument("--expect-regex")
    ap.add_argument("--timeout", type=float, default=120)
    ap.add_argument("--csv", type=Path, help="write per-run results")
    a = ap.parse_args()
    engines = dict(e.split("=", 1) for e in a.engine)
    try:
        rows = stress(a.deck, a.count, a.out, a.seed, a.stream, engines, a.fail_regex, a.expect_regex, a.timeout)
    except (StressError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if a.csv:
        with a.csv.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["order_id", "engine", "status", "deck"])
            w.writeheader()
            w.writerows(rows)
    return 1 if any(r["status"] != "pass" for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
