#!/usr/bin/env python3
"""Structurally compare a derived SPICE netlist (e.g. a KiCad export) with a canonical reference netlist.

Pairs elements by name (with an optional alias map), infers ONE consistent 1:1 net map from every paired
terminal, and reports pin swaps, wrong nets, unmapped nets, missing/extra elements, value, model and
subcircuit-parameter differences, and .param/.func/.options/.ic/.nodeset differences. Net NAMES may differ
freely (they are mapped); net TOPOLOGY may not. Project adapter subcircuits (dual op-amp packages, pot
wrappers) can be flattened one level with --adapters so the derived deck is compared element by element.

  netlist_compare.py REFERENCE.cir DERIVED.cir [--adapters LIB] [--alias MAP.json] [--inert NAME]
                     [--analyses] [--mutation-check]
  netlist_compare.py --self-test

--mutation-check re-runs the comparison on deliberately broken copies of DERIVED (reversed polarised
parts, swapped pins, changed values and models, deleted parts, moved terminals) and fails unless every
mutation is detected: a validator that cannot see a planted fault proves nothing.

Limitations: behavioural/controlled-source expressions and source specs are compared as normalised text
(net names inside them are not mapped); `.include`/`.lib` files are not followed (hash them with
spice_manifest.py instead); an ambiguous symmetric part (R/C/L) with no mapped neighbour is bound in its
written orientation. Exit status: 0 equivalent, 1 differences found, 2 usage/parse error.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

SUFFIX = {"t": 1e12, "g": 1e9, "meg": 1e6, "k": 1e3, "mil": 25.4e-6, "m": 1e-3, "u": 1e-6, "n": 1e-9, "p": 1e-12,
          "f": 1e-15}
NUMBER = re.compile(r"^([+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?)(meg|mil|[tgkmunpf])?[a-z]*$")
NUM_IN_EXPR = re.compile(r"(?<![a-z_0-9.])((?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?)(meg|mil|[tgkmunpf])?[a-z]*", re.I)
SYMMETRIC = set("rcl")
MODEL_KINDS = set("dqjmzsw")   # positional tokens end with a model name (optionally followed by an area factor)
GROUND = {"0", "gnd", "gnd!"}


class NetlistError(RuntimeError):
    pass


@dataclass
class Element:
    name: str
    kind: str
    nodes: list[str]
    model: str | None = None
    value: str | None = None
    params: dict[str, str] = field(default_factory=dict)
    spec: str = ""


@dataclass
class Subckt:
    name: str
    ports: list[str]
    params: dict[str, str]
    elems: dict[str, Element]


@dataclass
class Deck:
    elems: dict[str, Element] = field(default_factory=dict)
    subckts: dict[str, Subckt] = field(default_factory=dict)
    params: dict[str, str] = field(default_factory=dict)
    funcs: dict[str, str] = field(default_factory=dict)
    options: set[str] = field(default_factory=set)
    initial: dict[tuple[str, str], str] = field(default_factory=dict)   # (.ic|.nodeset, node) -> value
    analyses: list[str] = field(default_factory=list)
    models: dict[str, str] = field(default_factory=dict)                 # name -> canonical definition


# ----------------------------------------------------------------- parsing
def logical_lines(text: str, has_title: bool) -> list[str]:
    raw = text.replace("\r", "").split("\n")
    if has_title and raw:
        raw = raw[1:]
    out: list[str] = []
    for line in raw:
        line = re.split(r";|//|\s\$\s", line, maxsplit=1)[0].rstrip()
        if not line.strip() or line.lstrip().startswith("*"):
            continue
        if line.lstrip().startswith("+") and out:
            out[-1] += " " + line.lstrip()[1:]
        else:
            out.append(line.strip())
    return out


def tokens(line: str) -> list[str]:
    line = re.sub(r"\s*=\s*", "=", line)
    out, cur, depth, quote = [], "", 0, False
    for ch in line:
        if ch == '"':
            quote = not quote
        elif not quote and ch in "{(":
            depth += 1
        elif not quote and ch in "})":
            depth -= 1
        if ch.isspace() and depth == 0 and not quote:
            if cur:
                out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur:
        out.append(cur)
    return [t.lower() for t in out]


def is_number(tok: str) -> bool:
    return bool(NUMBER.match(tok))


def spice_number(tok: str) -> float | None:
    m = NUMBER.match(tok.strip().lower())
    return float(m.group(1)) * SUFFIX.get(m.group(2) or "", 1.0) if m else None


def evaluate(expr: str | None) -> float | None:
    """Numeric value of a number or of a brace expression using only numbers and + - * / ( )."""
    if expr is None:
        return None
    s = expr.strip().lower()
    if s.startswith("{") and s.endswith("}"):
        s = s[1:-1]
    direct = spice_number(s)
    if direct is not None:
        return direct
    py = NUM_IN_EXPR.sub(lambda m: repr(float(m.group(1)) * SUFFIX.get((m.group(2) or "").lower(), 1.0)), s)
    if not re.fullmatch(r"[0-9.e+\-*/() ]+", py):
        return None
    try:
        return float(eval(py, {"__builtins__": {}}, {}))   # arithmetic only, checked by the regex above
    except (SyntaxError, ZeroDivisionError, TypeError, ValueError):
        return None


def canonical_numbers(text: str) -> str:
    """Rewrite every SPICE number in `text` as a canonical float (20e3, 20k and 20000 compare equal)."""
    return NUM_IN_EXPR.sub(lambda m: repr(float(m.group(1)) * SUFFIX.get((m.group(2) or "").lower(), 1.0)), text)


def source_spec(spec: str) -> tuple:
    """Canonical independent-source specification: DC value, AC magnitude/phase, transient function and any
    other tokens. Defaults are made explicit (DC 0, AC 1 0) and SIN's trailing zero defaults are dropped
    (other functions keep every argument: PULSE/EXP defaults are not zero)."""
    raw, toks = tokens(spec), []
    for t in raw:   # 'sin (0 1 1k)' -> 'sin(0 1 1k)'
        if t.startswith("(") and toks and re.fullmatch(r"[a-z]+", toks[-1]):
            toks[-1] += t
        else:
            toks.append(t)
    dc, ac, fn, other = "0", ("1", "0"), None, []
    has_ac, i = False, 0
    while i < len(toks):
        t = toks[i]
        if t == "dc" and i + 1 < len(toks):
            dc, i = toks[i + 1], i + 2
        elif t == "ac":
            vals, i = [], i + 1
            while i < len(toks) and len(vals) < 2 and evaluate(toks[i]) is not None:
                vals.append(toks[i])
                i += 1
            ac, has_ac = (vals[0] if vals else "1", vals[1] if len(vals) > 1 else "0"), True
        elif re.match(r"^[a-z]+\(", t):
            name, args = t.split("(", 1)
            args = tokens(args.rstrip(")").replace(",", " "))
            if name == "sin":
                while len(args) > 3 and evaluate(args[-1]) == 0.0:
                    args.pop()
            fn, i = (name, tuple(canonical_numbers(x) for x in args)), i + 1
        elif i == 0 and evaluate(t) is not None:
            dc, i = t, i + 1
        else:
            other.append(canonical_numbers(t))
            i += 1
    return (canonical_numbers(dc), tuple(canonical_numbers(x) for x in ac) if has_ac else None, fn, tuple(other))


def node(n: str) -> str:
    return "0" if n in GROUND else n


def element(toks: list[str]) -> Element:
    name, kind = toks[0], toks[0][0]
    rest = toks[1:]
    params = {k: v for k, v in (t.split("=", 1) for t in rest if "=" in t and not t.startswith(("{", "(")))}
    pos = [t for t in rest if not ("=" in t and not t.startswith(("{", "(")))]
    if kind in SYMMETRIC:
        return Element(name, kind, [node(n) for n in pos[:2]], value=pos[2] if len(pos) > 2 else params.get(kind),
                       params=params, spec=" ".join(pos[3:]))
    if kind in MODEL_KINDS:
        if kind == "w":    # W n+ n- vcontrol model
            return Element(name, kind, [node(n) for n in pos[:2]], model=pos[3] if len(pos) > 3 else None,
                           params=params, spec=pos[2] if len(pos) > 2 else "")
        k = len(pos) - 1
        if k > 0 and is_number(pos[k]) and not is_number(pos[k - 1]):
            k -= 1          # trailing area/multiplier factor
        return Element(name, kind, [node(n) for n in pos[:k]], model=pos[k] if pos else None, params=params,
                       spec=" ".join(pos[k + 1 :]))
    if kind == "x":
        if not pos:
            raise NetlistError(f"{name}: subcircuit call without a subcircuit name")
        pos = [p for p in pos if p != "params:"]
        return Element(name, kind, [node(n) for n in pos[:-1]], model=pos[-1], params=params)
    if kind in "eg" and len(pos) == 5 and not any(c in "".join(pos) for c in "({"):
        return Element(name, kind, [node(n) for n in pos[:4]], value=pos[4])
    if kind == "t":
        return Element(name, kind, [node(n) for n in pos[:4]], params=params, spec=" ".join(pos[4:]))
    if kind == "k":
        return Element(name, kind, [], params=params, spec=" ".join(rest))
    if kind in "vi":
        return Element(name, kind, [node(n) for n in pos[:2]], params=params, spec=" ".join(rest[2:]))
    # E G F H B and anything else: two nodes plus a normalised specification string
    return Element(name, kind, [node(n) for n in pos[:2]], params=params, spec=" ".join(rest[2:]).replace(" ", ""))


def parse(text: str, has_title: bool = True) -> Deck:
    deck, stack, control = Deck(), [], False
    for line in logical_lines(text, has_title):
        toks = tokens(line)
        head = toks[0]
        if head == ".control" or control:      # simulator control scripts are not circuit
            control = head != ".endc"
            continue
        target = stack[-1].elems if stack else deck.elems
        if head == ".subckt":
            ports = [t for t in toks[2:] if "=" not in t and t != "params:"]
            params = dict(t.split("=", 1) for t in toks[2:] if "=" in t)
            stack.append(Subckt(toks[1], [node(p) for p in ports], params, {}))
        elif head == ".ends":
            if not stack:
                raise NetlistError(".ends without .subckt")
            sub = stack.pop()
            deck.subckts[sub.name] = sub
        elif head == ".param" and not stack:
            for t in toks[1:]:
                if "=" in t:
                    k, v = t.split("=", 1)
                    deck.params[k] = v
        elif head == ".func" and not stack:
            deck.funcs[toks[1].split("(")[0]] = "".join(toks[1:])
        elif head == ".options" or head == ".option":
            deck.options |= {t for t in toks[1:]}
        elif head in (".ic", ".nodeset"):
            for t in toks[1:]:
                m = re.fullmatch(r"v\((.+)\)=(.+)", t)
                if m:
                    deck.initial[(head, node(m.group(1)))] = m.group(2)
        elif head == ".model" and len(toks) > 2:
            body = " ".join(toks[2:]).replace("(", " ").replace(")", " ")
            kind_tok, *rest = tokens(body) or [""]
            deck.models[toks[1]] = kind_tok + " " + " ".join(sorted(canonical_numbers(x) for x in rest))
        elif head in (".tran", ".ac", ".dc", ".op", ".noise", ".tf"):
            deck.analyses.append(" ".join(toks))
        elif head == ".end" or head.startswith("."):
            continue    # .model/.include/.lib/.control/.save/... are not topology (hash models separately)
        else:
            e = element(toks)
            if e.name in target:
                raise NetlistError(f"duplicate element name {e.name}")
            target[e.name] = e
    if stack:
        raise NetlistError(f".subckt {stack[-1].name} has no .ends")
    return deck


def flatten(deck: Deck, adapters: dict[str, Subckt]) -> dict[str, Element]:
    """Expand one level of adapter subcircuits: inner element 'r1' of instance 'xu1' becomes 'xu1.r1'."""
    out: dict[str, Element] = {}
    for e in deck.elems.values():
        sub = adapters.get(e.model) if e.kind == "x" else None
        if sub is None:
            out[e.name] = e
            continue
        if len(sub.ports) != len(e.nodes):
            raise NetlistError(f"{e.name}: {len(e.nodes)} terminals for adapter {sub.name} with {len(sub.ports)} ports")
        ports = dict(zip(sub.ports, e.nodes))
        values = {**sub.params, **e.params}

        def substitute(text: str | None) -> str | None:
            if text is None or not values:
                return text
            return re.sub(r"\b(%s)\b" % "|".join(map(re.escape, values)), lambda m: values[m.group(1)].strip("{}"), text)

        for inner in sub.elems.values():
            f = copy.deepcopy(inner)
            f.name = f"{e.name}.{inner.name}"
            f.nodes = [ports.get(n, n if n == "0" else f"{e.name}.{n}") for n in inner.nodes]
            f.value, f.spec = substitute(f.value), substitute(f.spec) or ""
            f.params = {k: substitute(v) or "" for k, v in f.params.items()}
            out[f.name] = f
    return out


# ----------------------------------------------------------------- comparison
def same_value(a: str | None, b: str | None, rel: float) -> bool:
    va, vb = evaluate(a), evaluate(b)
    if va is not None and vb is not None:
        return abs(va - vb) <= rel * max(abs(va), abs(vb), 1e-300)
    norm = lambda s: canonical_numbers(re.sub(r"\s+", "", (s or "").lower()).strip("{}"))
    return norm(a) == norm(b)


def compare(ref: Deck, der: Deck, adapters: dict[str, Subckt], alias: dict[str, str], inert: set[str],
            analyses: bool = False, rel: float = 1e-9) -> tuple[list[str], list[str]]:
    errors, notes = [], []
    rel_elems, der_elems = ref.elems, flatten(der, adapters)
    pairs, seen = [], set()
    for dname, de in der_elems.items():
        if dname in inert:
            if len(set(de.nodes)) != 1:
                errors.append(f"{dname}: declared inert but its terminals are on different nets {de.nodes}")
            else:
                notes.append(f"{dname}: inert (all terminals on one net)")
            continue
        rname = alias.get(dname, dname)
        if rname not in rel_elems:
            errors.append(f"derived element {dname} has no reference counterpart ({rname})")
            continue
        if rname in seen:
            errors.append(f"reference element {rname} matched twice")
            continue
        seen.add(rname)
        pairs.append((rel_elems[rname], de))
    for rname in rel_elems:
        if rname not in seen:
            errors.append(f"reference element {rname} missing from the derived netlist")

    fmap, inv = {"0": "0"}, {"0": "0"}
    fits = lambda r, d: fmap.get(r, d) == d and inv.get(d, r) == r

    def bind(rn: list[str], dn: list[str]) -> None:
        for r, d in zip(rn, dn):
            fmap[r], inv[d] = d, r

    pending = []
    for re_, de in pairs:
        if re_.kind != de.kind or len(re_.nodes) != len(de.nodes):
            errors.append(f"{re_.name}/{de.name}: type or terminal count differs ({re_.kind}{len(re_.nodes)} vs "
                          f"{de.kind}{len(de.nodes)})")
        elif re_.kind in SYMMETRIC:
            pending.append((re_, de))
        elif all(fits(r, d) for r, d in zip(re_.nodes, de.nodes)):
            bind(re_.nodes, de.nodes)
        else:
            errors.append(f"{re_.name}: terminals {re_.nodes} vs derived {de.name} {de.nodes} (pin swap or wrong net)")
    while pending:
        progress, left = False, []
        for re_, de in pending:
            a, b = re_.nodes, de.nodes
            fwd, rev = all(fits(r, d) for r, d in zip(a, b)), all(fits(r, d) for r, d in zip(a, b[::-1]))
            if fwd and (not rev or any(r in fmap for r in a)):
                bind(a, b)
                progress = True
            elif rev and not fwd:
                bind(a, b[::-1])
                progress = True
            elif not fwd and not rev:
                errors.append(f"{re_.name}: {a} vs derived {de.name} {b} (wrong net)")
                progress = True
            else:
                left.append((re_, de))
        if not progress:
            re_, de = left.pop(0)
            bind(re_.nodes, de.nodes)
        pending = left
    ref_nets = {n for e in rel_elems.values() for n in e.nodes}
    der_nets = {n for e in der_elems.values() if e.name not in inert for n in e.nodes}
    errors += [f"reference net {n} is not mapped to any derived net" for n in sorted(ref_nets - set(fmap))]
    errors += [f"derived net {n} is not mapped to any reference net (extra connection?)" for n in sorted(der_nets - set(inv))]

    for re_, de in pairs:
        if re_.kind != de.kind:
            continue
        if not same_value(re_.value, de.value, rel):
            errors.append(f"{re_.name}: value {re_.value} vs derived {de.value}")
        if (re_.model or "") != (de.model or ""):
            ra, da = ref.models.get(re_.model or ""), der.models.get(de.model or "")
            if ra is not None and ra == da:
                notes.append(f"{re_.name}: model renamed {re_.model} -> {de.model} with an identical definition")
            else:
                errors.append(f"{re_.name}: model/subckt {re_.model} vs derived {de.model}")
        for key in sorted(set(re_.params) | set(de.params)):
            if not same_value(re_.params.get(key), de.params.get(key), rel):
                errors.append(f"{re_.name}: parameter {key}={re_.params.get(key)} vs derived {de.params.get(key)}")
        if re_.kind in "vi":
            if source_spec(re_.spec) != source_spec(de.spec):
                errors.append(f"{re_.name}: source '{re_.spec}' vs derived '{de.spec}'")
        elif canonical_numbers(re.sub(r"\s", "", re_.spec)) != canonical_numbers(re.sub(r"\s", "", de.spec)):
            errors.append(f"{re_.name}: specification '{re_.spec}' vs derived '{de.spec}'")

    for what, a, b in ((".param", ref.params, der.params), (".func", ref.funcs, der.funcs)):
        for key in sorted(set(a) | set(b)):
            if not same_value(a.get(key), b.get(key), rel):
                errors.append(f"{what} {key}: {a.get(key)} vs derived {b.get(key)}")
    if ref.options != der.options:
        errors.append(f".options {sorted(ref.options)} vs derived {sorted(der.options)}")
    want = {(k, fmap.get(n, "?" + n)): v for (k, n), v in ref.initial.items()}
    if want.keys() != der.initial.keys() or any(not same_value(v, der.initial[k], rel) for k, v in want.items()):
        errors.append(f".ic/.nodeset {sorted(want.items())} vs derived {sorted(der.initial.items())}")
    if analyses and ref.analyses != der.analyses:
        errors.append(f"analyses {ref.analyses} vs derived {der.analyses}")
    return errors, notes


# ----------------------------------------------------------------- mutation check
def mutations(der: Deck) -> list[tuple[str, Deck]]:
    """Deliberately broken copies of `der`, one fault each."""
    out: list[tuple[str, Deck]] = []
    all_nets = sorted({n for e in der.elems.values() for n in e.nodes})

    def variant(label: str, name: str, edit) -> None:
        d = copy.deepcopy(der)
        before = copy.deepcopy(d.elems[name])
        edit(d.elems[name])
        if d.elems[name] != before:
            out.append((label, d))

    def swap(i: int, j: int):
        def f(e: Element) -> None:
            e.nodes[i], e.nodes[j] = e.nodes[j], e.nodes[i]
        return f

    kinds_done: set[str] = set()
    for name, e in der.elems.items():
        if e.kind in kinds_done:
            continue
        kinds_done.add(e.kind)
        if e.kind not in SYMMETRIC and len(e.nodes) >= 2 and e.nodes[0] != e.nodes[1]:
            variant(f"{name}: first two terminals swapped", name, swap(0, 1))
        if len(e.nodes) >= 3 and e.nodes[1] != e.nodes[2]:
            variant(f"{name}: terminals 2/3 swapped", name, swap(1, 2))
        if e.kind in SYMMETRIC and spice_number(e.value or "") is not None:
            variant(f"{name}: value +1%", name, lambda x: setattr(x, "value", repr(spice_number(x.value) * 1.01)))
        if e.model and e.kind != "x":
            variant(f"{name}: model renamed", name, lambda x: setattr(x, "model", x.model + "_mut"))
        spare = [n for n in all_nets if n not in e.nodes]
        if e.nodes and spare:
            variant(f"{name}: terminal 1 moved to net {spare[0]}", name, lambda x, s=spare[0]: x.nodes.__setitem__(0, s))
        d = copy.deepcopy(der)
        del d.elems[name]
        out.append((f"{name}: deleted", d))
    if der.params:
        d = copy.deepcopy(der)
        k = sorted(d.params)[0]
        d.params[k] = d.params[k] + "*1.01" if not d.params[k].startswith("{") else "{1.01*(" + d.params[k].strip("{}") + ")}"
        out.append((f".param {k} changed", d))
    return out


def mutation_check(ref: Deck, der: Deck, adapters, alias, inert, analyses) -> list[str]:
    missed = []
    for label, mutant in mutations(der):
        try:
            errors, _ = compare(ref, mutant, adapters, alias, inert, analyses)
        except NetlistError as exc:
            errors = [str(exc)]   # a crash on a broken netlist also counts as detection
        if not errors:
            missed.append(label)
    return missed


# ----------------------------------------------------------------- self-test
SELF_REF = """clipper reference
.param DRIVE=0.5
.options klu
VIN in 0 SIN(0 0.1 1k)
R1 in n1 10k
C1 n1 inp 100n
XU1 inp inn vcc 0 out OPAMP
RF out inn {100k*DRIVE+1k}
D1 out inn DMOD
D2 inn out DMOD
RP1 out w 3k
RP2 w 0 7k
Q1 vcc w e1 QMOD
RE e1 0 4.7k
VCC vcc 0 9
.ic v(out)=0
.model DMOD D(IS=1e-14)
.model QMOD NPN(BF=100)
.subckt OPAMP p n vp vn o
E1 o 0 p n 1e5
.ends OPAMP
.end
"""
SELF_DER = """derived (net names and order changed, pot as an adapter)
.param DRIVE=0.5
.options klu
Q1 /VCC /W Net-_Q1-E_ QMOD
XRV1 /OUT /W 0 POT params: rtot=10k pos=0.3
RE Net-_Q1-E_ 0 4.7K
VIN1 /IN 0 SIN(0 0.1 1k)
XU1 /INP /INN /VCC 0 /OUT OPAMP
D2 /INN /OUT DMOD
D1 /OUT /INN DMOD
RF /OUT /INN {100k*DRIVE+1k}
C1 /N1 /INP 0.1u
R1 /IN /N1 10k
VCC /VCC 0 9
.ic v(/OUT)=0
.end
"""
SELF_ADAPTERS = """.subckt POT p1 w p3 params: rtot=1k pos=0.5
RA p1 w {rtot*pos}
RB w p3 {rtot*(1-pos)}
.ends POT
"""
SELF_ALIAS = {"vin1": "vin", "xrv1.ra": "rp1", "xrv1.rb": "rp2"}
SELF_FAULTS = [   # (label, derived-deck text edit)
    ("diode reversed", lambda t: t.replace("D1 /OUT /INN", "D1 /INN /OUT")),
    ("BJT collector/emitter swapped", lambda t: t.replace("Q1 /VCC /W Net-_Q1-E_", "Q1 Net-_Q1-E_ /W /VCC")),
    ("op-amp inputs swapped", lambda t: t.replace("XU1 /INP /INN", "XU1 /INN /INP")),
    ("resistor value changed", lambda t: t.replace("R1 /IN /N1 10k", "R1 /IN /N1 10.1k")),
    ("capacitor missing", lambda t: t.replace("C1 /N1 /INP 0.1u\n", "")),
    ("resistor on the wrong net", lambda t: t.replace("RE Net-_Q1-E_ 0", "RE /W 0")),
    ("model changed", lambda t: t.replace("D2 /INN /OUT DMOD", "D2 /INN /OUT DLED")),
    ("pot ends reversed", lambda t: t.replace("XRV1 /OUT /W 0", "XRV1 0 /W /OUT")),
    ("pot position changed", lambda t: t.replace("pos=0.3", "pos=0.4")),
    (".ic on the wrong node", lambda t: t.replace("v(/OUT)=0", "v(/INN)=0")),
    (".param default changed", lambda t: t.replace("DRIVE=0.5", "DRIVE=0.6")),
    (".options dropped", lambda t: t.replace(".options klu\n", "")),
    ("extra element", lambda t: t.replace(".end", "C9 /OUT 0 1n\n.end")),
]


def self_test() -> int:
    problems = []
    adapters = parse(SELF_ADAPTERS, has_title=False).subckts
    ref = parse(SELF_REF)
    errors, _ = compare(ref, parse(SELF_DER), adapters, SELF_ALIAS, set())
    if errors:
        problems.append("equivalent decks reported different: " + "; ".join(errors))
    for label, edit in SELF_FAULTS:
        text = edit(SELF_DER)
        if text == SELF_DER:
            problems.append(f"fault '{label}' did not change the deck")
            continue
        try:
            errs, _ = compare(ref, parse(text), adapters, SELF_ALIAS, set())
        except NetlistError as exc:
            errs = [str(exc)]
        if not errs:
            problems.append(f"fault not detected: {label}")
    missed = mutation_check(ref, parse(SELF_DER), adapters, SELF_ALIAS, set(), False)
    problems += [f"generic mutation not detected: {m}" for m in missed]
    if not re.search(r"x", "".join(e.kind for e in parse(SELF_DER).elems.values())):
        problems.append("parser lost the subcircuit calls")
    for p in problems:
        print("SELF-TEST FAILURE:", p)
    print(f"self-test: {len(SELF_FAULTS)} planted faults, {len(mutations(parse(SELF_DER)))} generic mutations: "
          f"{'PASS' if not problems else 'FAIL'}")
    return 1 if problems else 0


def main() -> int:
    if "--self-test" in sys.argv[1:]:
        return self_test()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("reference", type=Path)
    ap.add_argument("derived", type=Path)
    ap.add_argument("--adapters", type=Path, action="append", default=[], help="library of adapter subckts to flatten")
    ap.add_argument("--alias", type=Path, help="JSON map: derived element name -> reference element name")
    ap.add_argument("--inert", action="append", default=[], help="derived element allowed only if fully shorted")
    ap.add_argument("--analyses", action="store_true", help="also compare .tran/.ac/.dc/.op lines")
    ap.add_argument("--rel", type=float, default=1e-9, help="relative tolerance for numeric values")
    ap.add_argument("--mutation-check", action="store_true", help="prove that planted faults are detected")
    a = ap.parse_args()
    try:
        ref, der = parse(a.reference.read_text(errors="replace")), parse(a.derived.read_text(errors="replace"))
        adapters: dict[str, Subckt] = {}
        for lib in a.adapters:
            adapters.update(parse(lib.read_text(errors="replace"), has_title=False).subckts)
        alias = {k.lower(): v.lower() for k, v in json.loads(a.alias.read_text()).items()} if a.alias else {}
        inert = {n.lower() for n in a.inert}
        errors, notes = compare(ref, der, adapters, alias, inert, a.analyses, a.rel)
    except (NetlistError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    for n in notes:
        print("note:", n)
    for e in errors:
        print("DIFF:", e)
    print(f"{len(ref.elems)} reference elements, {len(errors)} differences: "
          + ("STRUCTURALLY EQUIVALENT" if not errors else "NOT EQUIVALENT"))
    status = 1 if errors else 0
    if a.mutation_check:
        missed = mutation_check(ref, der, adapters, alias, inert, a.analyses)
        for m in missed:
            print("MUTATION NOT DETECTED:", m)
        print(f"mutation check: {len(mutations(der)) - len(missed)}/{len(mutations(der))} planted faults detected")
        status = status or (1 if missed else 0)
    return status


if __name__ == "__main__":
    sys.exit(main())
