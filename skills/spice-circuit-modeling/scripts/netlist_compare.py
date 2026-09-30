#!/usr/bin/env python3
"""Structurally compare a derived SPICE netlist (e.g. a KiCad export) with a canonical reference netlist.

Pairs elements by name (with an optional alias map), infers ONE consistent 1:1 net map from every paired
terminal, and reports pin swaps, wrong nets, unmapped nets, missing/extra elements, value, model and
subcircuit differences, and .param/.func/.options/.temp/.global/.ic/.nodeset differences. Net NAMES may
differ (they are mapped); net TOPOLOGY may not. Project adapter subcircuits (dual op-amp packages, pot
wrappers) can be flattened with --adapters so the derived deck is compared element by element.

  netlist_compare.py REFERENCE.cir DERIVED.cir [--adapters LIB] [--alias MAP.json] [--inert NAME]
                     [--analyses] [--mutation-check]
  netlist_compare.py --self-test

FAIL-CLOSED GRAMMAR. Equivalence is claimed only inside the supported grammar; anything else is a parse
error (exit 2, "NOT QUALIFIED"), never a silent pass.
  Elements: R C L (value), V I (source spec), D Q J M Z S (terminals + model), W (2 terminals, controlling
    source, model), X (subcircuit call), E G (linear 4-terminal gain, or behavioural value=/vol=/cur=/poly/
    table/laplace), F H (2 terminals, controlling source, gain or poly), B (v= or i=), T (4 terminals),
    K (coupled inductor names and value). XSPICE `A` devices and every other element letter are rejected.
  Directives compared: .param .func .options/.option .temp .global .ic .nodeset .model (bodies) .subckt
    (bodies, compared structurally with ports bound in order); analyses (.tran .ac .dc .op .noise .tf .four
    .sens .pz .disto) only with --analyses. Ignored as output-only: .end .title .save .print .plot .probe
    .meas/.measure .width .csparam. Reported but NOT followed: .include/.inc/.lib FILE (hash those files with
    spice_manifest.py); `.lib FILE SECTION` and any extra include argument are rejected. .control blocks:
    only a small read-only allowlist (run op ac tran dc noise print plot write wrdata save show echo let
    meas/measure setplot display quit exit) is accepted and ignored; every other command, including
    alter, altermod, alterparam, option, reset, source, shell and set, is rejected. Any other directive
    is rejected.
Limits: behavioural expressions are compared as normalised text after remapping v(net)/v(a,b) through the
net map and i(name) through the element pairing; controlled-source poly controls given as bare node lists
are not remapped (they are reported as differences when names differ). Adapters are flattened ONE level;
an adapter that calls another adapter is rejected. Inside a .subckt only elements are accepted: a local .model,
a nested .subckt definition or any other directive there is rejected. Inline .subckt bodies are compared element by element
with the same checks as top-level elements, plus their default parameters; an inline body that itself
calls a subcircuit is rejected (nested inline subcircuits are not supported). Include files and model
libraries are not read.
Exit status: 0 equivalent, 1 differences found, 2 unsupported syntax or usage error.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

SUFFIX = {"t": 1e12, "g": 1e9, "meg": 1e6, "k": 1e3, "mil": 25.4e-6, "m": 1e-3, "u": 1e-6, "n": 1e-9, "p": 1e-12,
          "f": 1e-15}
NUMBER = re.compile(r"^([+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?)(meg|mil|[tgkmunpf])?[a-z]*$")
NUM_IN_EXPR = re.compile(r"(?<![a-z_0-9.])((?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?)(meg|mil|[tgkmunpf])?[a-z]*", re.I)
SYMMETRIC = set("rcl")
MODEL_TERMINALS = {"d": (2, 2), "q": (3, 5), "j": (3, 3), "m": (4, 7), "z": (3, 3), "s": (4, 4)}
SUPPORTED = set("rclvidqjmzswxefghbtk")
GROUND = {"0", "gnd", "gnd!"}
ANALYSES = {".tran", ".ac", ".dc", ".op", ".noise", ".tf", ".four", ".sens", ".pz", ".disto"}
OUTPUT_ONLY = {".end", ".title", ".save", ".print", ".plot", ".probe", ".meas", ".measure", ".width", ".csparam"}
INCLUDES = {".include", ".inc", ".lib"}
# Read-only .control commands: they run analyses or read, format and write results; none alters an element,
# model, parameter or option. Everything else inside .control is rejected (fail closed).
CONTROL_SAFE = {"run", "op", "ac", "tran", "dc", "noise", "print", "plot", "write", "wrdata", "save", "show",
                "echo", "let", "meas", "measure", "setplot", "display", "quit", "exit"}
BEHAVIOURAL_KEYS = ("value", "vol", "cur")


class NetlistError(RuntimeError):
    """Unsupported or malformed syntax: structural equivalence cannot be established."""


@dataclass
class Element:
    name: str
    kind: str
    nodes: list[str]
    model: str | None = None
    value: str | None = None
    params: dict[str, str] = field(default_factory=dict)
    spec: str = ""
    ctrl: list[str] = field(default_factory=list)      # controlling element names (W F H K)
    behavioural: bool = False


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
    temp: str | None = None
    globals: set[str] = field(default_factory=set)
    initial: dict[tuple[str, str], str] = field(default_factory=dict)   # (.ic|.nodeset, node) -> value
    analyses: list[str] = field(default_factory=list)
    models: dict[str, str] = field(default_factory=dict)                 # name -> canonical definition
    includes: list[str] = field(default_factory=list)
    control_commands: list[str] = field(default_factory=list)


# ----------------------------------------------------------------- lexical helpers
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


def tokens(line: str, lower: bool = True) -> list[str]:
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
    return [t.lower() for t in out] if lower else out


def is_number(tok: str) -> bool:
    return bool(NUMBER.match(tok))


def spice_number(tok: str) -> float | None:
    m = NUMBER.match(tok.strip().lower())
    return float(m.group(1)) * SUFFIX.get(m.group(2) or "", 1.0) if m else None


def canonical_numbers(text: str) -> str:
    """Rewrite every SPICE number in `text` as a canonical float (20e3, 20k and 20000 compare equal)."""
    return NUM_IN_EXPR.sub(lambda m: repr(float(m.group(1)) * SUFFIX.get((m.group(2) or "").lower(), 1.0)), text)


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
    py = canonical_numbers(s)
    if not re.fullmatch(r"[0-9.e+\-*/() ]+", py):
        return None
    try:
        return float(eval(py, {"__builtins__": {}}, {}))   # arithmetic only, checked by the regex above
    except (SyntaxError, ZeroDivisionError, TypeError, ValueError):
        return None


def source_spec(spec: str) -> tuple:
    """Canonical independent-source specification: DC value, AC magnitude/phase, transient function and any
    other tokens. Defaults are made explicit (DC 0, AC 1 0) and SIN's trailing zero defaults are dropped
    (other functions keep every argument: PULSE/EXP defaults are not zero)."""
    toks: list[str] = []
    for t in tokens(spec):   # 'sin (0 1 1k)' -> 'sin(0 1 1k)'
        if t.startswith("(") and toks and re.fullmatch(r"[a-z]+", toks[-1]):
            toks[-1] += t
        else:
            toks.append(t)
    dc, ac, fn, other = "0", None, None, []
    i = 0
    while i < len(toks):
        t = toks[i]
        if t == "dc" and i + 1 < len(toks):
            dc, i = toks[i + 1], i + 2
        elif t == "ac":
            vals, i = [], i + 1
            while i < len(toks) and len(vals) < 2 and evaluate(toks[i]) is not None:
                vals.append(toks[i])
                i += 1
            ac = (vals[0] if vals else "1", vals[1] if len(vals) > 1 else "0")
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
    return (canonical_numbers(dc), tuple(canonical_numbers(x) for x in ac) if ac else None, fn, tuple(other))


def node(n: str) -> str:
    return "0" if n in GROUND else n


def split_params(rest: list[str]) -> tuple[list[str], dict[str, str]]:
    params = {k: v for k, v in (t.split("=", 1) for t in rest if "=" in t and not t.startswith(("{", "(")))}
    pos = [t for t in rest if not ("=" in t and not t.startswith(("{", "("))) and t != "params:"]
    return pos, params


# ----------------------------------------------------------------- element grammar
def element(toks: list[str]) -> Element:
    name, kind = toks[0], toks[0][0]
    if kind == "a":
        raise NetlistError(f"{name}: XSPICE code-model instances (A) are not supported; "
                           "structural equivalence not established")
    if kind not in SUPPORTED:
        raise NetlistError(f"{name}: unsupported element type {kind.upper()}; structural equivalence not established")
    pos, params = split_params(toks[1:])

    def need(n: int) -> None:
        if len(pos) < n:
            raise NetlistError(f"{name}: expected at least {n} positional fields, found {len(pos)}")

    if kind in SYMMETRIC:
        need(2)
        value = pos[2] if len(pos) > 2 else params.pop(kind, None)
        if value is None:
            raise NetlistError(f"{name}: no value")
        return Element(name, kind, [node(n) for n in pos[:2]], value=value, params=params, spec=" ".join(pos[3:]))
    if kind in "vi":
        need(2)
        return Element(name, kind, [node(n) for n in pos[:2]], spec=" ".join(toks[3:]))
    if kind in MODEL_TERMINALS:
        lo, hi = MODEL_TERMINALS[kind]
        flags = []
        while pos and pos[-1] in ("on", "off"):
            flags.insert(0, pos.pop())
        k = len(pos) - 1
        if k > lo and is_number(pos[k]) and not is_number(pos[k - 1]):
            flags.insert(0, pos[k])      # trailing area / multiplier factor
            k -= 1
        if not lo <= k <= hi:
            raise NetlistError(f"{name}: {k} terminals before the model name; {kind.upper()} supports {lo}-{hi}")
        return Element(name, kind, [node(n) for n in pos[:k]], model=pos[k], params=params, spec=" ".join(flags))
    if kind == "w":
        need(4)
        return Element(name, kind, [node(n) for n in pos[:2]], model=pos[3], params=params, ctrl=[pos[2]],
                       spec=" ".join(pos[4:]))
    if kind == "x":
        need(1)
        return Element(name, kind, [node(n) for n in pos[:-1]], model=pos[-1], params=params)
    if kind in "eg":
        need(2)
        text = " ".join(toks[1:])
        if any(k in params for k in BEHAVIOURAL_KEYS) or re.search(r"\b(poly|table|laplace|freq)\b", text):
            return Element(name, kind, [node(n) for n in pos[:2]], behavioural=True,
                           spec=" ".join(toks[3:]).replace(" ", ""))
        if len(pos) == 5 and evaluate(pos[4]) is not None and not params:
            return Element(name, kind, [node(n) for n in pos[:4]], value=pos[4])
        raise NetlistError(f"{name}: unsupported {kind.upper()} source syntax")
    if kind in "fh":
        need(4)
        if pos[2].startswith("poly("):
            return Element(name, kind, [node(n) for n in pos[:2]], behavioural=True, spec=" ".join(toks[3:]))
        if len(pos) != 4 or params:
            raise NetlistError(f"{name}: unsupported {kind.upper()} source syntax")
        return Element(name, kind, [node(n) for n in pos[:2]], ctrl=[pos[2]], value=pos[3])
    if kind == "b":
        need(2)
        if not ({"v", "i"} & set(params)):
            raise NetlistError(f"{name}: behavioural source needs v= or i=")
        return Element(name, kind, [node(n) for n in pos[:2]], behavioural=True,
                       spec=" ".join(toks[3:]).replace(" ", ""))
    if kind == "t":
        need(4)
        return Element(name, kind, [node(n) for n in pos[:4]], params=params, spec=" ".join(pos[4:]))
    # k: coupling between inductors
    if len(pos) != 3:
        raise NetlistError(f"{name}: unsupported K syntax")
    return Element(name, kind, [], ctrl=pos[:2], value=pos[2])


def parse(text: str, has_title: bool = True) -> Deck:
    deck, stack, control = Deck(), [], False
    for line in logical_lines(text, has_title):
        toks = tokens(line)
        head = toks[0]
        if control:
            if head == ".endc":
                control = False
            elif head not in CONTROL_SAFE:
                raise NetlistError(f".control command '{line}' is not in the supported read-only set; "
                                   "structural equivalence not established")
            else:
                deck.control_commands.append(head)
            continue
        if stack and head.startswith(".") and head != ".ends":
            # Inside a .subckt only elements and .ends are supported: scoped models, nested definitions and any
            # other directive would change meaning if treated as deck-level, so fail closed before handling them.
            if head == ".model":
                raise NetlistError(f"local .model inside .subckt {stack[-1].name} is not supported; "
                                   "structural equivalence not established")
            if head == ".subckt":
                raise NetlistError(f"nested .subckt definitions are not supported (inside .subckt {stack[-1].name}); "
                                   "structural equivalence not established")
            raise NetlistError(f"directive {head} inside .subckt {stack[-1].name} is not supported")
        if head == ".control":
            control = True
            continue
        target = stack[-1].elems if stack else deck.elems
        if head == ".subckt":
            if len(toks) < 2:
                raise NetlistError(".subckt without a name")
            ports = [node(t) for t in toks[2:] if "=" not in t and t != "params:"]
            stack.append(Subckt(toks[1], ports, dict(t.split("=", 1) for t in toks[2:] if "=" in t), {}))
        elif head == ".ends":
            if not stack:
                raise NetlistError(".ends without .subckt")
            sub = stack.pop()
            deck.subckts[sub.name] = sub
        elif head == ".model" and len(toks) > 2:
            body = " ".join(toks[2:]).replace("(", " ").replace(")", " ")
            kind_tok, *rest = tokens(body) or [""]
            deck.models[toks[1]] = kind_tok + " " + " ".join(sorted(canonical_numbers(x) for x in rest))
        elif head == ".param":
            for t in toks[1:]:
                if "=" not in t:
                    raise NetlistError(f"malformed .param: {line}")
                k, v = t.split("=", 1)
                deck.params[k] = v
        elif head == ".func":
            deck.funcs[toks[1].split("(")[0]] = "".join(toks[1:])
        elif head in (".options", ".option"):
            deck.options |= set(toks[1:])
        elif head == ".temp":
            deck.temp = " ".join(toks[1:])
        elif head == ".global":
            deck.globals |= {node(t) for t in toks[1:]}
        elif head in (".ic", ".nodeset"):
            for t in toks[1:]:
                m = re.fullmatch(r"v\((.+)\)=(.+)", t)
                if not m:
                    raise NetlistError(f"unsupported {head} entry '{t}'")
                deck.initial[(head, node(m.group(1)))] = m.group(2)
        elif head in ANALYSES:
            deck.analyses.append(" ".join(toks))
        elif head in INCLUDES:
            raw = tokens(line, lower=False)
            if len(raw) != 2:
                raise NetlistError(f"unsupported {head} form '{line}': only '{head} FILE' is supported "
                                   "(library sections and extra arguments are not)")
            deck.includes.append(raw[1].strip('"'))   # original case
        elif head in OUTPUT_ONLY:
            continue
        elif head.startswith("."):
            raise NetlistError(f"unsupported directive {head}; structural equivalence not established")
        else:
            e = element(toks)
            if e.name in target:
                raise NetlistError(f"duplicate element name {e.name}")
            target[e.name] = e
    if stack:
        raise NetlistError(f".subckt {stack[-1].name} has no .ends")
    if control:
        raise NetlistError(".control without .endc")
    return deck


def flatten(deck: Deck, adapters: dict[str, Subckt]) -> dict[str, Element]:
    """Expand ONE level of adapter subcircuits: inner element 'r1' of instance 'xu1' becomes 'xu1.r1'."""
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
            if inner.kind == "x" and inner.model in adapters:
                raise NetlistError(f"adapter {sub.name} calls adapter {inner.model}; only one level is flattened")
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


def remap_refs(spec: str, fmap: dict[str, str], names: dict[str, str]) -> str:
    """Rewrite v(net), v(a,b) through the net map and i(name) through the element pairing."""
    def sub(m: re.Match) -> str:
        fn, args = m.group(1), [a.strip() for a in m.group(2).split(",")]
        if fn == "v":
            return "v(" + ",".join(fmap.get(node(a), a) for a in args) + ")"
        return "i(" + ",".join(names.get(a, a) for a in args) + ")"
    return re.sub(r"\b([vi])\(([^()]+)\)", sub, spec)


def compare_elements(ref: dict[str, Element], der: dict[str, Element], alias: dict[str, str], inert: set[str],
                     seed: dict[str, str], context: str = "") -> tuple[list[str], list[str], dict, list]:
    """Pair elements and infer one consistent net map. Returns (errors, notes, net map, pairs)."""
    errors, notes = [], []
    pairs, seen = [], set()
    for dname, de in der.items():
        if dname in inert:
            if len(set(de.nodes)) != 1:
                errors.append(f"{context}{dname}: declared inert but its terminals are on different nets {de.nodes}")
            else:
                notes.append(f"{context}{dname}: inert (all terminals on one net)")
            continue
        rname = alias.get(dname, dname)
        if rname not in ref:
            errors.append(f"{context}derived element {dname} has no reference counterpart ({rname})")
            continue
        if rname in seen:
            errors.append(f"{context}reference element {rname} matched twice (duplicate mapping)")
            continue
        seen.add(rname)
        pairs.append((ref[rname], de))
    errors += [f"{context}reference element {r} missing from the derived netlist" for r in ref if r not in seen]

    fmap, inv = dict(seed), {v: k for k, v in seed.items()}
    fits = lambda r, d: fmap.get(r, d) == d and inv.get(d, r) == r

    def bind(rn: list[str], dn: list[str]) -> None:
        for r, d in zip(rn, dn):
            fmap[r], inv[d] = d, r

    pending = []
    for re_, de in pairs:
        if re_.kind != de.kind or len(re_.nodes) != len(de.nodes):
            errors.append(f"{context}{re_.name}/{de.name}: type or terminal count differs "
                          f"({re_.kind}{len(re_.nodes)} vs {de.kind}{len(de.nodes)})")
        elif re_.kind in SYMMETRIC:
            pending.append((re_, de))
        elif all(fits(r, d) for r, d in zip(re_.nodes, de.nodes)):
            bind(re_.nodes, de.nodes)
        else:
            errors.append(f"{context}{re_.name}: terminals {re_.nodes} vs derived {de.name} {de.nodes} "
                          "(pin swap or wrong net)")
    while pending:      # symmetric parts: prefer the orientation already implied by the mapped nets
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
                errors.append(f"{context}{re_.name}: {a} vs derived {de.name} {b} (wrong net)")
                progress = True
            else:
                left.append((re_, de))
        if not progress:
            re_, de = left.pop(0)
            bind(re_.nodes, de.nodes)
        pending = left
    ref_nets = {n for e in ref.values() for n in e.nodes}
    der_nets = {n for e in der.values() if e.name not in inert for n in e.nodes}
    errors += [f"{context}reference net {n} is not mapped to any derived net" for n in sorted(ref_nets - set(fmap))]
    errors += [f"{context}derived net {n} is not mapped to any reference net (extra connection?)"
               for n in sorted(der_nets - set(inv))]
    return errors, notes, fmap, pairs


def compare_pair(ref: Deck, der: Deck, re_: Element, de: Element, fmap: dict[str, str], names: dict[str, str],
                 rel: float, errors: list[str], notes: list[str], context: str = "") -> None:
    """Every per-element check, shared by top-level elements and elements inside inline subcircuits."""
    if re_.kind != de.kind:
        return       # already reported by compare_elements
    tag = f"{context}{re_.name}"
    if not same_value(re_.value, de.value, rel):
        errors.append(f"{tag}: value {re_.value} vs derived {de.value}")
    for key in sorted(set(re_.params) | set(de.params)):
        if not same_value(re_.params.get(key), de.params.get(key), rel):
            errors.append(f"{tag}: parameter {key}={re_.params.get(key)} vs derived {de.params.get(key)}")
    if [names.get(c, "?" + c) for c in re_.ctrl] != de.ctrl:
        errors.append(f"{tag}: controlling element(s) {re_.ctrl} vs derived {de.ctrl}")
    if re_.kind in "vi":
        if source_spec(re_.spec) != source_spec(de.spec):
            errors.append(f"{tag}: source '{re_.spec}' vs derived '{de.spec}'")
    elif canonical_numbers(remap_refs(re_.spec, fmap, names).replace(" ", "")) != \
            canonical_numbers(de.spec.replace(" ", "")):
        errors.append(f"{tag}: specification '{re_.spec}' vs derived '{de.spec}'")
    if re_.model or de.model:
        compare_model(ref, der, re_, de, rel, errors, notes, context)


def compare_model(ref: Deck, der: Deck, re_: Element, de: Element, rel: float, errors: list[str], notes: list[str],
                  context: str = "") -> None:
    rn, dn = re_.model or "", de.model or ""
    tag = f"{context}{re_.name}"
    if re_.kind == "x":
        rs, ds = ref.subckts.get(rn), der.subckts.get(dn)
        if rs is None and ds is None:
            if rn != dn:
                errors.append(f"{tag}: subckt {rn} vs derived {dn}")
            return
        if rs is None or ds is None:
            errors.append(f"{tag}: subckt {rn if rs else dn} is defined inline on only one side; "
                          "the other definition cannot be verified")
            return
        for body in (rs, ds):
            nested = [e.name for e in body.elems.values() if e.kind == "x"]
            if nested:
                raise NetlistError(f"inline .subckt {body.name} calls a subcircuit ({', '.join(nested)}); nested inline "
                                   "subcircuits are not supported; structural equivalence not established")
        if len(rs.ports) != len(ds.ports):
            errors.append(f"{tag}: subckt {rn} has {len(rs.ports)} ports vs derived {dn} {len(ds.ports)}")
            return
        inner = f"subckt {rn}: "
        errs: list[str] = []
        for key in sorted(set(rs.params) | set(ds.params)):
            if not same_value(rs.params.get(key), ds.params.get(key), rel):
                errs.append(f"{inner}default parameter {key}={rs.params.get(key)} vs derived {ds.params.get(key)}")
        seed = {"0": "0", **dict(zip(rs.ports, ds.ports))}
        body_errs, _, bmap, bpairs = compare_elements(rs.elems, ds.elems, {}, set(), seed, context=inner)
        errs += body_errs
        bnames = {r.name: d.name for r, d in bpairs}
        for r_el, d_el in bpairs:
            compare_pair(ref, der, r_el, d_el, bmap, bnames, rel, errs, notes, inner)
        errors += errs
        if not errs and rn != dn:
            notes.append(f"{tag}: subckt renamed {rn} -> {dn} with an identical body")
        return
    ra, da = ref.models.get(rn), der.models.get(dn)
    if ra is None and da is None:
        if rn != dn:
            errors.append(f"{tag}: model {rn} vs derived {dn}")
    elif ra is None or da is None:
        errors.append(f"{tag}: model {rn if ra else dn} is defined inline on only one side; "
                      "the other definition cannot be verified")
    elif ra != da:
        errors.append(f"{tag}: model {rn} body differs from derived {dn}")
    elif rn != dn:
        notes.append(f"{tag}: model renamed {rn} -> {dn} with an identical definition")


def compare(ref: Deck, der: Deck, adapters: dict[str, Subckt], alias: dict[str, str], inert: set[str],
            analyses: bool = False, rel: float = 1e-9) -> tuple[list[str], list[str]]:
    der_elems = flatten(der, adapters)
    errors, notes, fmap, pairs = compare_elements(ref.elems, der_elems, alias, inert, {"0": "0"})
    names = {r.name: d.name for r, d in pairs}   # reference element name -> derived element name

    for re_, de in pairs:
        compare_pair(ref, der, re_, de, fmap, names, rel, errors, notes)

    for what, a, b in ((".param", ref.params, der.params), (".func", ref.funcs, der.funcs)):
        for key in sorted(set(a) | set(b)):
            if not same_value(a.get(key), b.get(key), rel):
                errors.append(f"{what} {key}: {a.get(key)} vs derived {b.get(key)}")
    if ref.options != der.options:
        errors.append(f".options {sorted(ref.options)} vs derived {sorted(der.options)}")
    if not same_value(ref.temp, der.temp, rel):
        errors.append(f".temp {ref.temp} vs derived {der.temp}")
    if {fmap.get(g, "?" + g) for g in ref.globals} != der.globals:
        errors.append(f".global {sorted(ref.globals)} vs derived {sorted(der.globals)}")
    want = {(k, fmap.get(n, "?" + n)): v for (k, n), v in ref.initial.items()}
    if want.keys() != der.initial.keys() or any(not same_value(v, der.initial[k], rel) for k, v in want.items()):
        errors.append(f".ic/.nodeset {sorted(want.items())} vs derived {sorted(der.initial.items())}")
    if analyses and ref.analyses != der.analyses:
        errors.append(f"analyses {ref.analyses} vs derived {der.analyses}")
    for label, deck in (("reference", ref), ("derived", der)):
        if deck.includes:
            notes.append(f"{label} includes not followed (verify their content with spice_manifest.py): "
                         + ", ".join(deck.includes))
        if deck.control_commands:
            notes.append(f"{label} .control block ignored (commands: {', '.join(sorted(set(deck.control_commands)))})")
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

    done: set[str] = set()
    for name, e in der.elems.items():
        if e.kind in done:
            continue
        done.add(e.kind)
        swaps = [(0, 2), (1, 3)] if e.kind == "m" else [(0, 1), (1, 2)]   # MOSFET: drain/source, gate/bulk
        for i, j in swaps:
            if e.kind not in SYMMETRIC and len(e.nodes) > j and e.nodes[i] != e.nodes[j]:
                variant(f"{name}: terminals {i + 1}/{j + 1} swapped", name, swap(i, j))
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
        d.params[k] = "{1.01*(" + d.params[k].strip("{}") + ")}"
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
.global vcc
.temp 27
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
M1 out g1 e1 0 NMOS1 W=10u L=1u
RG g1 0 1meg
E1 buf 0 out 0 2
RB buf 0 10k
G1 0 gout in 0 1m
RGO gout 0 1k
F1 0 fo VIN 0.5
RFO fo 0 1k
B1 bo 0 V={V(out)*0.5+V(in,0)}
RBO bo 0 1k
VCC vcc 0 9
SW1 sw 0 bo 0 SWMOD
RSW sw vcc 1k
.ic v(out)=0
.model DMOD D(IS=1e-14)
.model QMOD NPN(BF=100)
.model NMOS1 NMOS(VTO=1)
.model SWMOD SW(VT=0.5 RON=1 ROFF=1meg)
.subckt OPAMP p n vp vn o
E1 o 0 p n 1e5
.ends OPAMP
XST1 in sout STAGE gain=3
RSOUT sout 0 10k
.subckt STAGE in out params: gain=1
RIN in mid 1k
MS mid gate 0 0 NMOS1 W=5u L=1u
RGATE gate 0 1meg
BS out 0 V={gain*V(mid)}
VSENSE mid msense 0
FS 0 out VSENSE 0.1
RMS msense 0 1k
.ends STAGE
.end
"""
SELF_DER = """derived (net names and order changed, pot as an adapter, a switch model renamed)
.param DRIVE=0.5
.options klu
.global /VCC
.temp 27
Q1 /VCC /W Net-_Q1-E_ QMOD
XRV1 /OUT /W 0 POT params: rtot=10k pos=0.3
RE 0 Net-_Q1-E_ 4.7K
VIN1 /IN 0 SIN(0 0.1 1k 0 0)
XU1 /INP /INN /VCC 0 /OUT OPAMP
D2 /INN /OUT DMOD
D1 /OUT /INN DMOD
RF /OUT /INN {100k*DRIVE+1k}
M1 /OUT /G1 Net-_Q1-E_ 0 NMOS1 W=10u L=1u
RG /G1 0 1meg
E1 /BUF 0 /OUT 0 2
RB /BUF 0 10k
G1 0 /GOUT /IN 0 1m
RGO /GOUT 0 1k
F1 0 /FO VIN1 0.5
RFO /FO 0 1k
B1 /BO 0 V={V(/OUT)*0.5+V(/IN,0)}
RBO /BO 0 1k
C1 /N1 /INP 0.1u
R1 /IN /N1 10k
VCC /VCC 0 DC 9
SW1 /SW 0 /BO 0 __SW1
RSW /SW /VCC 1k
.ic v(/OUT)=0
.model DMOD D(IS=1e-14)
.model QMOD NPN(BF=100)
.model NMOS1 NMOS(VTO=1)
.model __SW1 SW(RON=1 VT=0.5 ROFF=1meg)
.subckt OPAMP a b c d e
E1 e 0 a b 1e5
.ends OPAMP
XST1 /IN /SOUT STAGE gain=3
RSOUT /SOUT 0 10k
.subckt STAGE a b params: gain=1
RIN a n1 1k
MS n1 g 0 0 NMOS1 W=5u L=1u
RGATE g 0 1meg
BS b 0 V={gain*V(n1)}
VSENSE n1 ms 0
FS 0 b VSENSE 0.1
RMS ms 0 1k
.ends STAGE
.end
"""
SELF_ADAPTERS = """.subckt POT p1 w p3 params: rtot=1k pos=0.5
RA p1 w {rtot*pos}
RB w p3 {rtot*(1-pos)}
.ends POT
"""
SELF_ALIAS = {"vin1": "vin", "xrv1.ra": "rp1", "xrv1.rb": "rp2"}
SELF_FAULTS = [   # (label, text in SELF_DER, replacement): each must be reported as a difference
    ("diode reversed", "D1 /OUT /INN", "D1 /INN /OUT"),
    ("BJT collector/emitter swapped", "Q1 /VCC /W Net-_Q1-E_", "Q1 Net-_Q1-E_ /W /VCC"),
    ("MOSFET drain/source swapped", "M1 /OUT /G1 Net-_Q1-E_ 0", "M1 Net-_Q1-E_ /G1 /OUT 0"),
    ("MOSFET gate/bulk swapped", "M1 /OUT /G1 Net-_Q1-E_ 0", "M1 /OUT 0 Net-_Q1-E_ /G1"),
    ("MOSFET model changed", "NMOS1 W=10u", "NMOS2 W=10u"),
    ("MOSFET W changed", "W=10u L=1u", "W=12u L=1u"),
    ("op-amp inputs swapped", "XU1 /INP /INN", "XU1 /INN /INP"),
    ("resistor value changed", "R1 /IN /N1 10k", "R1 /IN /N1 10.1k"),
    ("capacitor missing", "C1 /N1 /INP 0.1u\n", ""),
    ("resistor on the wrong net", "RE 0 Net-_Q1-E_", "RE 0 /W"),
    ("diode model changed", "D2 /INN /OUT DMOD", "D2 /INN /OUT DLED"),
    ("pot ends reversed", "XRV1 /OUT /W 0", "XRV1 0 /W /OUT"),
    ("pot position changed", "pos=0.3", "pos=0.4"),
    ("VCVS control inputs swapped", "E1 /BUF 0 /OUT 0 2", "E1 /BUF 0 0 /OUT 2"),
    ("VCVS gain changed", "E1 /BUF 0 /OUT 0 2", "E1 /BUF 0 /OUT 0 3"),
    ("VCCS gain changed", "/IN 0 1m", "/IN 0 2m"),
    ("CCCS controlling source changed", "F1 0 /FO VIN1 0.5", "F1 0 /FO VCC 0.5"),
    ("behavioural source reads the wrong net", "V(/OUT)*0.5", "V(/INN)*0.5"),
    ("switch model body changed", "RON=1 VT=0.5", "RON=2 VT=0.5"),
    ("subckt body changed", "E1 e 0 a b 1e5", "E1 e 0 b a 1e5"),
    ("subckt gain changed", "E1 e 0 a b 1e5", "E1 e 0 a b 2e5"),
    ("model definition missing", ".model NMOS1 NMOS(VTO=1)\n", ""),
    ("subckt definition missing", ".subckt OPAMP a b c d e\nE1 e 0 a b 1e5\n.ends OPAMP\n", ""),
    (".global changed", ".global /VCC", ".global /OUT"),
    (".temp changed", ".temp 27", ".temp 50"),
    (".ic on the wrong node", "v(/OUT)=0", "v(/INN)=0"),
    (".param default changed", "DRIVE=0.5", "DRIVE=0.6"),
    (".options dropped", ".options klu\n", ""),
    ("extra element", ".model DMOD", "C9 /OUT 0 1n\n.model DMOD"),
    ("inline subckt default parameter changed", "STAGE a b params: gain=1", "STAGE a b params: gain=2"),
    ("inline subckt instance parameter changed", "STAGE gain=3", "STAGE gain=4"),
    ("inline subckt resistor value changed", "RIN a n1 1k", "RIN a n1 2k"),
    ("inline subckt MOSFET W changed", "MS n1 g 0 0 NMOS1 W=5u", "MS n1 g 0 0 NMOS1 W=6u"),
    ("inline subckt behavioural expression changed", "V={gain*V(n1)}", "V={2*gain*V(n1)}"),
    ("inline subckt behavioural source reads the wrong net", "V={gain*V(n1)}", "V={gain*V(g)}"),
    ("inline subckt controlling source changed", "FS 0 b VSENSE 0.1", "FS 0 b VOTHER 0.1"),
    ("inline subckt source value changed", "VSENSE n1 ms 0", "VSENSE n1 ms 1"),
]
SELF_REJECT = [   # (label, text in SELF_DER, replacement): each must be a parse error, never "equivalent"
    ("XSPICE A device", ".end\n", "A1 /IN /OUT gain1\n.end\n"),
    ("unknown primitive U", ".end\n", "U1 /IN /OUT 0 urc1 n=3\n.end\n"),
    ("unsupported directive .step", ".end\n", ".step param DRIVE 0 1 0.5\n.end\n"),
    ("circuit-altering control command", ".end\n", ".control\nalter R1 20k\nrun\n.endc\n.end\n"),
    ("MOSFET with too few terminals", "M1 /OUT /G1 Net-_Q1-E_ 0 NMOS1", "M1 /OUT /G1 NMOS1"),
    ("nested adapter", "XRV1 /OUT /W 0 POT", "XRV1 /OUT /W 0 POT2"),
    ("nested inline subckt call", "RMS ms 0 1k\n", "RMS ms 0 1k\nXIN ms 0 INNER\n"),
    (".lib FILE SECTION", ".end\n", ".lib models.lib TT\n.end\n"),
    (".include with an extra argument", ".end\n", ".include models.lib extra\n.end\n"),
    *[(f".control {cmd}", ".end\n", f".control\n{cmd}\nrun\n.endc\n.end\n")
      for cmd in ("alter R1 20k", "altermod NMOS1 VTO=2", "alterparam gain=2", "option klu", "reset",
                  "source other.cir", "shell ls", "set noaskquit", "frobnicate")],
]


def self_test() -> int:
    problems = []
    adapters = parse(SELF_ADAPTERS, has_title=False).subckts
    nested = parse(SELF_ADAPTERS + ".subckt POT2 a w b\nXIN a w b POT\n.ends POT2\n", has_title=False).subckts
    ref = parse(SELF_REF)
    errors, notes = compare(ref, parse(SELF_DER), adapters, SELF_ALIAS, set())
    if errors:
        problems.append("equivalent decks reported different: " + "; ".join(errors))
    if not any("model renamed swmod -> __sw1" in n for n in notes):
        problems.append(f"identical renamed model not reported as a rename: {notes}")
    for label, old, new in SELF_FAULTS:
        text = SELF_DER.replace(old, new, 1)
        if text == SELF_DER:
            problems.append(f"fault '{label}' did not change the deck")
            continue
        try:
            errs, _ = compare(ref, parse(text), adapters, SELF_ALIAS, set())
        except NetlistError as exc:
            errs = [str(exc)]
        if not errs:
            problems.append(f"fault not detected: {label}")
    for label, old, new in SELF_REJECT:
        text = SELF_DER.replace(old, new, 1)
        if text == SELF_DER:
            problems.append(f"rejection case '{label}' did not change the deck")
            continue
        try:
            compare(ref, parse(text), nested if "adapter" in label else adapters, SELF_ALIAS, set())
            problems.append(f"unsupported syntax accepted: {label}")
        except NetlistError:
            pass
    scoped = [("local .model inside .subckt", "scoped\n.subckt OUTER a b\n.model LOCAL D(IS=1e-14)\nD1 a b LOCAL\n"
               ".ends OUTER\nX1 n1 0 OUTER\n.end\n"),
              ("nested .subckt definition", "nested\n.subckt OUTER a b\n.subckt INNER x y\nR1 x y 1k\n.ends INNER\n"
               "X1 a b INNER\n.ends OUTER\nX2 n1 0 OUTER\n.end\n")]
    with tempfile.TemporaryDirectory() as tmp:
        for label, deck_text in scoped:
            path = Path(tmp) / "deck.cir"
            path.write_text(deck_text)
            run = subprocess.run([sys.executable, __file__, str(path), str(path)], capture_output=True, text=True)
            if run.returncode != 2 or "NOT QUALIFIED" not in run.stderr:
                problems.append(f"{label}: expected exit 2 NOT QUALIFIED, got {run.returncode} {run.stdout.strip()[-80:]}")
    dup = dict(SELF_ALIAS, rf="r1")        # two derived elements mapped onto one reference element
    if not any("matched twice" in e for e in compare(ref, parse(SELF_DER), adapters, dup, set())[0]):
        problems.append("duplicate mapping not reported")
    flipped = SELF_DER.replace("R1 /IN /N1 10k", "R1 /N1 /IN 10k")
    if compare(ref, parse(flipped), adapters, SELF_ALIAS, set())[0]:
        problems.append("reversed symmetric resistor reported as a difference")
    missed = mutation_check(ref, parse(SELF_DER), adapters, SELF_ALIAS, set(), False)
    problems += [f"generic mutation not detected: {m}" for m in missed]
    for p in problems:
        print("SELF-TEST FAILURE:", p)
    print(f"self-test: {len(SELF_FAULTS)} planted faults, {len(SELF_REJECT) + len(scoped)} rejected constructs, "
          f"{len(mutations(parse(SELF_DER)))} generic mutations: {'PASS' if not problems else 'FAIL'}")
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
    ap.add_argument("--analyses", action="store_true", help="also compare analysis lines")
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
    except NetlistError as exc:
        print(f"NOT QUALIFIED: {exc}", file=sys.stderr)
        return 2
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    for n in notes:
        print("note:", n)
    for e in errors:
        print("DIFF:", e)
    print(f"{len(ref.elems)} reference elements, {len(errors)} differences: "
          + ("STRUCTURALLY EQUIVALENT (within the supported grammar)" if not errors else "NOT EQUIVALENT"))
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
