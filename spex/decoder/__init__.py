"""Independent tables decoder (verification level L1, proposal §6.1): a loaded engine image -> an automaton graph.

Written from docs/SEMANTICS.md §11 (table formats) and R2.4-R2.10 (field meanings) only. It imports nothing from
spex.compiler or spex.refsim and decodes every packed word with its own bit positions, so a packing bug in either
of those shows up as a mismatch instead of being shared.

    g = decode(image)                      # Graph
    problems = compare(g, source_edges, source_initial, source_resync)

`compare` checks the decoded graph against a source graph (the role-expanded edges the compiler publishes, one list
per location name in slot order) by matching locations from the initial and resync locations along the slot order,
so it does not trust the compiler's location numbering either. What it covers: everything the hardware reads for an
edge (target, pin guard, clock guard with the fields that kind reads, data guard with the constant value, action,
resets, error, log, validity). What it does not: the role transformation itself (SEMANTICS §7; that is checked by
the oracles and the duality tests) and location words beyond halt and the invariant's presence.

Typed table entries (windows, patterns) are read through their SEMANTICS field names (clock, lo, hi; mask, value,
mode); packed words (edges, actions, location words, constants, nominal times) are decoded here bit by bit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

NUM_LOCS, NUM_SLOTS = 64, 4

# R2.5, R2.6, R2.10 codes
CK = {0: None, 1: "GE", 2: "WIN", 3: "POLICY"}
DK = {0: None, 1: "BITCNT_EQ", 2: "BITCNT_LT", 3: "SR_MATCH", 4: "EVENT", 5: "TXF_NE", 6: "TOKEN", 7: "SR_NOMATCH"}
OPS = {0: "NOP", 1: "LOAD", 2: "PUSH", 3: "LOAD_PUSH", 4: "SHIN", 5: "SHOUT", 6: "PEEK", 7: "LOAD_PEEK", 8: "CLR",
       9: "PUSH_LOAD_PEEK", 10: "INC"}
READS_CONST = {"BITCNT_EQ", "BITCNT_LT", "SR_MATCH", "SR_NOMATCH", "TOKEN"}


def _bits(w: int, hi: int, lo: int) -> int:
    return (w >> lo) & ((1 << (hi - lo + 1)) - 1)


@dataclass(frozen=True)
class ClockGuard:
    kind: str                 # GE, WIN, POLICY
    clock: int
    lo: int
    hi: Optional[int]         # None for GE (R2.5: GE reads only lo; R7.12d lets it share any entry)
    nom: Optional[int]        # POLICY only (R11.3a)


@dataclass(frozen=True)
class Action:
    wm: int
    wv: int
    od: int
    d: int
    op: str
    ev: int
    emit: int
    pop: int


@dataclass(frozen=True)
class EdgeNode:
    target: int
    pin: Optional[Tuple[int, int, int]]      # (mask, value, mode 0 LEVEL / 1 EDGE); None = no pin guard
    clock: Optional[ClockGuard]
    data: Optional[Tuple[str, int]]          # (kind, constant value / event index / 0)
    action: Action
    reset: int                               # bit c = clock x_c
    error: int
    log: int


@dataclass(frozen=True)
class LocNode:
    halt: int
    invariant: Optional[Tuple[int, int]]     # (clock, hi)
    watch: int


@dataclass
class Graph:
    initial: int
    resync: Optional[int]
    locs: Dict[int, LocNode] = field(default_factory=dict)
    edges: Dict[int, List[Optional[EdgeNode]]] = field(default_factory=dict)


class DecodeError(Exception):
    pass


def _window(img, i: int):
    w = img.windows[i]
    if w is None:
        raise DecodeError(f"window {i} is read but not loaded")
    return w


def decode_action(w: int) -> Action:
    """R11.2."""
    if _bits(w, 31, 29):
        raise DecodeError(f"action word {w:#010x}: reserved bits set")
    op = _bits(w, 23, 20)
    if op not in OPS:
        raise DecodeError(f"action word {w:#010x}: reserved op {op}")
    return Action(wm=_bits(w, 7, 0), wv=_bits(w, 15, 8), od=_bits(w, 16, 16), d=_bits(w, 19, 17), op=OPS[op],
                  ev=_bits(w, 26, 24), emit=_bits(w, 27, 27), pop=_bits(w, 28, 28))


def decode_edge(img, w: int) -> Optional[EdgeNode]:
    """R11.1; None for an invalid (valid = 0) slot."""
    if not _bits(w, 1, 1):
        return None
    target = _bits(w, 31, 25)
    if target >= NUM_LOCS:
        raise DecodeError(f"edge word {w:#010x}: target {target} beyond 64 locations")
    pidx = _bits(w, 24, 22)
    pin = None
    if pidx:
        p = img.patterns[pidx]
        if p is None:
            raise DecodeError(f"pattern {pidx} is read but not loaded")
        pin = (p.mask & 0xFF, p.value & p.mask & 0xFF, int(p.mode))
    widx = _bits(w, 2, 2) << 3 | _bits(w, 21, 19)              # S42: bit 2 is the window index MSB
    kind = CK[_bits(w, 18, 17)]
    clock = None
    if kind is not None:
        win = _window(img, widx)
        nom = None
        if kind == "POLICY":
            if widx >= len(img.noms) or img.noms[widx] is None:
                raise DecodeError(f"POLICY edge uses window {widx}, which has no nominal entry (R11.3a)")
            nom = img.noms[widx] & 0xFFFF
        clock = ClockGuard(kind, win.clock, win.lo, None if kind == "GE" else win.hi, nom)
    dk = DK[_bits(w, 16, 14)]
    k = _bits(w, 13, 11)
    data = None
    if dk is not None:
        if dk in READS_CONST:
            if img.consts[k] is None:
                raise DecodeError(f"constant {k} is read but not loaded")
            data = (dk, img.consts[k] & 0xFFFF)
        elif dk == "EVENT":
            data = (dk, k)
        else:
            data = (dk, 0)
    aidx = _bits(w, 10, 7)
    if img.actions[aidx] is None:
        raise DecodeError(f"action {aidx} is read but not loaded")
    return EdgeNode(target=target, pin=pin, clock=clock, data=data, action=decode_action(img.actions[aidx]),
                    reset=_bits(w, 6, 4), error=_bits(w, 3, 3), log=_bits(w, 0, 0))


def decode_loc(img, w: int) -> LocNode:
    """R11.6."""
    inv = None
    if _bits(w, 12, 12):
        win = _window(img, _bits(w, 11, 8))
        inv = (win.clock, win.hi)
    return LocNode(halt=_bits(w, 13, 13), invariant=inv, watch=_bits(w, 7, 0))


def decode(img) -> Graph:
    cfg = img.config
    g = Graph(initial=cfg.initial, resync=cfg.resync)
    for loc in range(NUM_LOCS):
        if img.locs[loc] is None:
            continue
        g.locs[loc] = decode_loc(img, img.locs[loc])
        g.edges[loc] = [None if img.edges[loc * NUM_SLOTS + s] is None else decode_edge(img, img.edges[loc * NUM_SLOTS + s])
                        for s in range(NUM_SLOTS)]
    for loc, slots in g.edges.items():
        for e in slots:
            if e is not None and e.target not in g.locs:
                raise DecodeError(f"location {loc}: edge to {e.target}, which has no location word")
    return g


# ---------------------------------------------------------------- comparison with a source graph
def _source_edge(ce) -> EdgeNode:
    """The fields of a source edge that the hardware reads, in the decoder's terms (target filled in later)."""
    pin = (ce.pmask & 0xFF, ce.pval & ce.pmask & 0xFF, int(ce.pmode)) if ce.pmask else None
    clock = None
    if ce.ck is not None:
        clock = ClockGuard(ce.ck, ce.clock, ce.lo, None if ce.ck == "GE" else ce.hi,
                           ce.nom if ce.ck == "POLICY" else None)
    data = None
    if ce.dk is not None:
        data = (ce.dk, (ce.dval & 0xFFFF) if ce.dk in READS_CONST else (ce.dval if ce.dk == "EVENT" else 0))
    act = Action(wm=ce.wm & 0xFF, wv=ce.wv & 0xFF, od=int(ce.wmode), d=ce.d, op=ce.op, ev=ce.ev, emit=ce.emit,
                 pop=ce.pop)
    return EdgeNode(target=-1, pin=pin, clock=clock, data=data, action=act, reset=ce.reset, error=ce.error,
                    log=ce.log)


def compare(g: Graph, source: Dict[str, list], initial: str, resync: Optional[str]) -> List[str]:
    """Match the decoded graph against `source` (location name -> edges in slot order, each with .dst and the
    hardware-visible fields). Returns a list of differences (empty = equivalent)."""
    problems: List[str] = []
    m: Dict[str, int] = {}
    work = []

    def bind(name: str, idx: Optional[int], why: str):
        if idx is None:
            problems.append(f"{why}: source location {name} has no decoded counterpart")
            return
        if name in m:
            if m[name] != idx:
                problems.append(f"{why}: source location {name} maps to both {m[name]} and {idx}")
            return
        if idx in m.values():
            other = next(k for k, v in m.items() if v == idx)
            problems.append(f"{why}: decoded location {idx} is both {other} and {name}")
            return
        m[name] = idx
        work.append(name)

    bind(initial, g.initial, "initial")
    if resync is not None:
        bind(resync, g.resync, "resync")
    elif g.resync is not None:
        problems.append(f"decoded resync {g.resync}, source has none")
    while work:
        name = work.pop()
        idx = m[name]
        if idx not in g.locs:
            problems.append(f"{name} -> {idx}: no location word")
            continue
        src = source.get(name, [])
        dec = g.edges[idx]
        if len(src) > NUM_SLOTS:
            problems.append(f"{name}: {len(src)} source edges")
        for s in range(NUM_SLOTS):
            se = src[s] if s < len(src) else None
            de = dec[s]
            if se is None and de is None:
                continue
            if se is None or de is None:
                problems.append(f"{name} slot {s}: {'extra decoded edge' if se is None else 'edge missing in the image'}")
                continue
            want = _source_edge(se)
            got = EdgeNode(-1, de.pin, de.clock, de.data, de.action, de.reset, de.error, de.log)
            if want != got:
                for f in ("pin", "clock", "data", "action", "reset", "error", "log"):
                    if getattr(want, f) != getattr(got, f):
                        problems.append(f"{name} slot {s}: {f} {getattr(got, f)} in the image, {getattr(want, f)} in the source")
            bind(str(se.dst), de.target, f"{name} slot {s} target")
    for name in source:
        if name not in m and source[name]:
            problems.append(f"source location {name} not reached from the initial or resync location")
    return problems
