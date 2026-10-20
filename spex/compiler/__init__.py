"""SPEX compiler: spec + role (+ policy) -> table image in the SEMANTICS §11 format (R7, R11).

    c = compile_spec(spec, role="drive", side="tx")      # or role="check"
    c.image        EngineImage for spex.refsim
    c.loc_index    {location name: index}
    c.listing      human-readable listing (R7.13)
    c.policy       the policy to load with it (host register, §8)

Every rule violation is collected and raised together as CompileError (R7.12).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from spex import dsl
from spex.dsl import DATA, OD, Loc, Spec, SpecEdge
from spex.refsim import tables as T
from spex.refsim.model import Policy

E_ENTRY = 1                    # E (R4.2)
D_OBS = 3                      # 1 output register + 2 synchroniser cycles (R7.7)
MAX_AGE = 2

OP_CODES = {n: i for i, n in enumerate(dsl.OPS)}
OBSERVED_OP = {"SHOUT": "SHIN", "LOAD": "CLR", "LOAD_PUSH": "PUSH", "PEEK": "NOP", "LOAD_PEEK": "CLR"}   # R7.4
DATA_OPS = ("SHOUT", "PEEK", "LOAD_PEEK")
DG_CODES = {"BITCNT_EQ": T.DG_BITCNT_EQ, "BITCNT_LT": T.DG_BITCNT_LT, "SR_MATCH": T.DG_SR_MATCH,
            "SR_NOMATCH": T.DG_SR_NOMATCH, "EVENT": T.DG_EVENT, "TXF_NE": T.DG_TXF_NE, "TOKEN": T.DG_TOKEN}
CK_CODES = {None: T.CK_NONE, "GE": T.CK_GE, "WIN": T.CK_WIN, "POLICY": T.CK_POLICY}


class CompileError(Exception):
    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


@dataclass
class CEdge:
    """One table edge before encoding."""
    src: Loc
    dst: Loc
    origin: SpecEdge
    variant: str
    cls: str                         # own (own emit) / obs (observe or observed emit) / internal
    pmask: int = 0
    pval: int = 0
    pmode: int = T.EDGE
    ck: Optional[str] = None
    clock: int = 0
    lo: int = 0
    hi: int = 0
    nom: int = 0
    dk: Optional[str] = None
    dval: int = 0
    wm: int = 0
    wv: int = 0
    wmode: int = T.PP
    d: int = 0
    op: str = "NOP"
    ev: int = 0
    emit: int = 0
    pop: int = 0
    reset: int = 0
    error: int = 0
    log: int = 1
    otherwise: bool = False

    def action_key(self):
        return (self.wm, self.wv, self.wmode, self.d, self.op, self.ev, self.emit, self.pop)

    def describe(self):
        g = []
        if self.pmask:
            g.append(f"{'EDGE' if self.pmode == T.EDGE else 'LEVEL'}(m={self.pmask:#04x},v={self.pval:#04x})")
        if self.ck:
            g.append(f"{self.ck} x{self.clock}[{self.lo},{self.hi}]" + (f" nom {self.nom}" if self.ck == "POLICY" else ""))
        if self.dk:
            g.append(f"{self.dk}={self.dval:#x}")
        a = []
        if self.wm:
            a.append(f"{'OD' if self.wmode else 'PP'} m={self.wm:#04x} v={self.wv:#04x}")
        if self.op != "NOP":
            a.append(f"{self.op}(d={self.d})")
        if self.pop:
            a.append("pop")
        if self.reset:
            a.append(f"reset={self.reset:#x}")
        return (f"{self.src.name} -> {self.dst.name} [{self.cls}{'/otherwise' if self.otherwise else ''}] "
                f"{' & '.join(g) or 'true'} / {', '.join(a) or '-'}   ({self.variant})")


@dataclass
class Compiled:
    image: T.EngineImage
    loc_index: Dict[str, int]
    edges: Dict[str, List[CEdge]]
    listing: str
    warnings: List[str]
    policy: Policy = Policy()
    role: str = "check"
    side: Optional[str] = None


# ------------------------------------------------------------------------------------------------ helpers
def _win(spec: Spec, ce: CEdge, kind: Optional[str], w: Optional[dsl.Window]) -> None:
    ce.ck = kind
    if w is not None and kind is not None:
        ce.clock, ce.lo, ce.hi, ce.nom = spec.clocks.index(w.clock), w.lo, w.hi, w.nom


def _reset_mask(spec: Spec, e: SpecEdge) -> int:
    m = 0
    for c in e.reset:
        m |= 1 << spec.clocks.index(c)
    return m


def _data(ce: CEdge, g: Optional[dsl.DataGuard], private_ok: bool) -> None:
    if g is None or (not private_ok and g.kind == "TXF_NE"):
        return
    ce.dk, ce.dval = g.kind, g.value


def _common(spec: Spec, e: SpecEdge, variant: str, cls: str) -> CEdge:
    ce = CEdge(e.src, e.dst, e, variant, cls, reset=_reset_mask(spec, e), error=int(e.error), log=int(e.log),
               otherwise=e.otherwise)
    if e.event is not None:
        ce.ev, ce.emit = e.event, 1
    return ce


# ------------------------------------------------------------------------------------------------ R7.3-R7.5
def _expand(spec: Spec, e: SpecEdge, role: str, side: Optional[str], errs: List[str]) -> List[CEdge]:
    P = spec.pins
    if e.kind == "observe":
        ce = _common(spec, e, "observe", "obs")
        ce.pmask, ce.pval = spec.mask(e.pins), sum(v << P[p] for p, v in e.pins.items())
        ce.pmode = T.EDGE if e.pmode == dsl.EDGE else T.LEVEL
        _win(spec, ce, e.ck, e.window)
        _data(ce, e.data, True)
        _op(spec, ce, e.op, errs)
        return [ce]
    if e.kind == "internal":
        ce = _common(spec, e, "internal", "internal")
        _win(spec, ce, e.ck, e.window)
        _data(ce, e.data, True)
        _op(spec, ce, e.op, errs)
        return [ce]
    # emits
    data_pins = [p for p, v in e.writes.items() if v == DATA]
    if len(data_pins) > 1:
        errs.append(f"{e.label}: more than one data pin in one emit ({data_pins}) (R7.4)")
        return []
    if data_pins and not (e.op.kind in DATA_OPS and e.op.pin == data_pins[0]):
        errs.append(f"{e.label}: a DATA write needs op SHOUT/PEEK/LOAD_PEEK on pin {data_pins[0]} (R2.10)")
        return []
    if e.token is not None and e.data is not None:
        errs.append(f"{e.label}: a choice token and a data guard on one edge (one data guard field, R2.3)")
        return []
    own = role == "drive" and e.side == side
    if own:
        ce = _common(spec, e, "own emit", "own")
        if e.pins:
            ce.pmask, ce.pval, ce.pmode = spec.mask(e.pins), sum(v << P[p] for p, v in e.pins.items()), T.EDGE
        _win(spec, ce, e.ck, e.window)
        if e.token is not None:
            ce.dk, ce.dval, ce.pop = "TOKEN", e.token, int(not e.peek)
        else:
            _data(ce, e.data, True)
        for p, v in e.writes.items():
            ce.wm |= 1 << P[p]
            ce.wv |= (1 if v == DATA else v) << P[p]
        ce.wmode = T.OD if e.mode == OD else T.PP
        _op(spec, ce, e.op, errs)
        return [ce]
    # observed emit (R7.4)
    op = dsl.Op(OBSERVED_OP.get(e.op.kind, e.op.kind), e.op.pin)
    if e.pins:                                         # reactive emit: observe its trigger
        ce = _common(spec, e, "observed reactive emit", "obs")
        ce.pmask, ce.pval, ce.pmode = spec.mask(e.pins), sum(v << P[p] for p, v in e.pins.items()), T.EDGE
        _win(spec, ce, "WIN" if e.window else None, e.window)
        _data(ce, e.data, False)
        _op(spec, ce, op, errs)
        return [ce]
    vis_const = {p: v for p, v in e.writes.items() if v != DATA and (e.mode != OD or v == 0)}
    dpin = data_pins[0] if data_pins else None
    ck_win = "WIN" if e.window else None
    if not vis_const and dpin is None:
        if e.reset:
            errs.append(f"{e.label}: observed emit resets a clock but writes no visible pin (R7.4 visibility)")
            return []
        ce = _common(spec, e, "observed invisible emit", "internal")
        _win(spec, ce, "GE" if e.window else None, e.window)
        _data(ce, e.data, False)
        _op(spec, ce, op, errs)
        return [ce]
    if e.reset and dpin is not None:
        errs.append(f"{e.label}: observed emit with a DATA pin may be silent, so it may not reset a clock "
                    f"(R7.4 visibility)")
        return []
    base_m = spec.mask(vis_const)
    base_v = sum(v << P[p] for p, v in vis_const.items())
    out = []
    variants = [(None, "e1")] if dpin is None else [(0, "e1a"), (1, "e1b")]
    for b, name in variants:
        ce = _common(spec, e, f"observed emit {name}", "obs")
        ce.pmask, ce.pval, ce.pmode = base_m, base_v, T.EDGE
        if dpin is not None:
            ce.pmask |= 1 << P[dpin]
            ce.pval |= b << P[dpin]
        _win(spec, ce, ck_win, e.window)
        _data(ce, e.data, False)
        _op(spec, ce, op, errs)
        out.append(ce)
    if e.window is not None and not e.reset:          # silent completion (R7.4), an otherwise edge (R7.9)
        ce = _common(spec, e, "silent completion e2", "obs" if base_m else "internal")
        ce.otherwise = True
        if base_m:
            ce.pmask, ce.pval, ce.pmode = base_m, base_v, T.LEVEL
        ce.ck, ce.clock, ce.lo, ce.hi, ce.nom = "WIN", spec.clocks.index(e.window.clock), e.window.hi, \
            e.window.hi, e.window.hi
        _data(ce, e.data, False)
        _op(spec, ce, op, errs)
        out.append(ce)
    return out


def _op(spec: Spec, ce: CEdge, op: dsl.Op, errs: List[str]) -> None:
    ce.op = op.kind
    if op.pin is not None:
        ce.d = spec.pins[op.pin]
    elif op.kind in ("SHIN", "SHOUT", "PEEK", "LOAD_PEEK"):
        errs.append(f"{ce.origin.label}: op {op.kind} needs a data pin")


# ------------------------------------------------------------------------------------------------ R7.7
def _reachable(spec: Spec, edges) -> set:
    seen, todo = set(), [spec.initial_loc.name] + ([spec.resync_loc.name] if spec.resync_loc else [])
    while todo:
        n = todo.pop()
        if n not in seen:
            seen.add(n)
            todo += [ce.dst.name for ce in edges[n]]
    return seen


def _edge_base(ce: CEdge, bases) -> Optional[str]:
    if ce.cls == "own" and not ce.pmask:
        return "E"
    if ce.pmask or ce.cls == "obs":
        return "O"
    if ce.ck is None:
        return None                                   # untimed internal: may not reset (checked elsewhere)
    b = bases[ce.src.name][ce.clock]
    return next(iter(b)) if len(b) == 1 else "?"


def _time_base(spec: Spec, edges: Dict[str, List[CEdge]], errs: List[str]) -> None:
    nclk = len(spec.clocks)
    bases = {l.name: [set() for _ in range(nclk)] for l in spec.locs}
    for c in range(nclk):
        bases[spec.initial_loc.name][c].add("E")
        if spec.resync_loc is not None:
            bases[spec.resync_loc.name][c].add("R")       # reset by a violation: unknown base
    changed = True
    while changed:
        changed = False
        for es in edges.values():
            for ce in es:
                for c in range(nclk):
                    if (ce.reset >> c) & 1:
                        new = {_edge_base(ce, bases)}
                    else:
                        new = set(bases[ce.src.name][c])
                    tgt = bases[ce.dst.name][c]
                    if not new <= tgt:
                        tgt |= new
                        changed = True

    def base_of(loc, c, what):
        b = bases[loc.name][c]
        if len(b) != 1 or not b <= {"E", "O"}:
            errs.append(f"{what}: time base of clock {spec.clocks[c]} at {loc.name} is "
                        f"{'ambiguous' if len(b) > 1 else 'unknown'} ({sorted(map(str, b))}); reset it on every "
                        f"incoming path (R7.7)")
            return None
        return next(iter(b))

    live = _reachable(spec, edges)
    for es in edges.values():
        for ce in es:
            if ce.ck is None or ce.src.name not in live:
                continue
            b = base_of(ce.src, ce.clock, ce.origin.label)
            if b is None:
                continue
            shift = 0
            if ce.pmask and b == "E":
                shift = D_OBS
            elif ce.cls == "own" and not ce.pmask and b == "O":
                shift = -D_OBS
            if shift:
                ce.lo, ce.hi, ce.nom = ce.lo + shift, ce.hi + shift, ce.nom + shift
                if ce.lo < 0:
                    errs.append(f"{ce.origin.label}: own emit {D_OBS} cycles after an observed event needs "
                                f"lo >= {D_OBS}; the chip cannot react that fast (R7.7)")
    inv_shift = {}
    for l in spec.locs:
        if l.invariant is not None and l.name in live:
            c = spec.clocks.index(l.invariant.clock)
            b = base_of(l, c, f"invariant of {l.name}")
            inv_shift[l.name] = D_OBS if b == "E" else 0
    return inv_shift


# ------------------------------------------------------------------------------------------------ R7.11
def _intervals_disjoint(a: CEdge, b: CEdge) -> bool:
    if a.ck is None or b.ck is None or a.clock != b.clock:
        return False

    def iv(e):
        hi = float("inf") if e.ck == "GE" else e.hi + (MAX_AGE if e.pmask else 0)
        return e.lo, hi
    alo, ahi = iv(a)
    blo, bhi = iv(b)
    return ahi < blo or bhi < alo


def _data_disjoint(a: CEdge, b: CEdge) -> bool:
    if a.dk is None or b.dk is None:
        return False
    if a.dk == b.dk:
        return a.dk in ("BITCNT_EQ", "TOKEN") and a.dval != b.dval
    k = {a.dk: a.dval, b.dk: b.dval}
    if set(k) == {"BITCNT_EQ", "BITCNT_LT"}:
        return k["BITCNT_EQ"] >= k["BITCNT_LT"]
    if set(k) == {"SR_MATCH", "SR_NOMATCH"}:
        return a.dval == b.dval
    return False


def _disjoint(a: CEdge, b: CEdge) -> bool:
    if a.pmask and b.pmask and ((a.pval ^ b.pval) & a.pmask & b.pmask):
        return True
    return _intervals_disjoint(a, b) or _data_disjoint(a, b)


def _equivalent(a: CEdge, b: CEdge) -> bool:
    return a.dst is b.dst and a.action_key() == b.action_key() and a.reset == b.reset and a.error == b.error


def _determinism(loc: Loc, es: List[CEdge], role: str, errs: List[str]) -> None:
    cand = [e for e in es if role == "check" or e.cls != "own"]
    for i, a in enumerate(cand):
        for b in cand[i + 1:]:
            if b.otherwise or _equivalent(a, b) or _disjoint(a, b):
                continue
            choice = a.origin.token is not None and b.origin.token is not None
            what = "choice alternatives are not distinguishable by observation (R7.8)" if choice \
                else "not observably deterministic (R7.11)"
            errs.append(f"{loc.name}: {a.origin.label} and {b.origin.label}: {what}")


# ------------------------------------------------------------------------------------------------ R4.5
def _exactness(spec: Spec, edges: Dict[str, List[CEdge]], errs: List[str], warns: List[str]) -> None:
    nclk = len(spec.clocks)
    incoming = {l.name: [] for l in spec.locs}
    for es in edges.values():
        for ce in es:
            incoming[ce.dst.name].append((ce.reset, bool(ce.pmask)))
    full = (1 << nclk) - 1
    incoming[spec.initial_loc.name].append((full, False))          # START (R12.4)
    if spec.resync_loc is not None:
        incoming[spec.resync_loc.name].append((full, False))       # resync (R6.5)
    for es in edges.values():
        for ce in es:
            if ce.ck not in ("GE", "POLICY", "WIN") or ce.pmask:
                continue
            inc = incoming[ce.src.name]
            if not inc or not all((r >> ce.clock) & 1 for r, _ in inc):
                warns.append(f"{ce.origin.label}: clock {spec.clocks[ce.clock]} not reset on every edge into "
                             f"{ce.src.name}; exact firing not checked (R4.5)")
                continue
            need = E_ENTRY + 1 + (MAX_AGE if any(pin and (r >> ce.clock) & 1 for r, pin in inc) else 0)
            if ce.lo < need:
                errs.append(f"{ce.origin.label}: clock-triggered edge needs lo >= {need} (E+1"
                            f"{'+2: a pin-triggered edge resets the clock' if need > 2 else ''}); has lo = {ce.lo} "
                            f"(R4.5)")


# ------------------------------------------------------------------------------------------------ main
def compile_spec(spec: Spec, role: str = "check", side: Optional[str] = None, policy: Policy = Policy(),
                 cover: bool = False, trace: bool = True, cov_shift: int = 0) -> Compiled:
    errs: List[str] = []
    warns: List[str] = []
    if role not in ("drive", "check"):
        raise CompileError([f"unknown role {role}"])
    if role == "drive" and side not in spec.sides:
        raise CompileError([f"drive role needs one of the sides {spec.sides}"])
    if role == "check":
        side = None
    if len(spec.locs) > T.NUM_LOCS:
        errs.append(f"{len(spec.locs)} locations > {T.NUM_LOCS} (R2.1)")

    # expansion (R7.3-R7.5), untimed resets (R7.7)
    edges: Dict[str, List[CEdge]] = {l.name: [] for l in spec.locs}
    for e in spec.edges:
        for ce in _expand(spec, e, role, side, errs):
            edges[ce.src.name].append(ce)
    for es in edges.values():
        for ce in es:
            if ce.cls == "internal" and ce.ck is None and ce.reset:
                errs.append(f"{ce.origin.label}: an internal edge with no clock guard may not reset clocks (R7.7)")
            if ce.ck is not None and not ce.lo <= ce.nom <= ce.hi:
                errs.append(f"{ce.origin.label}: nom {ce.nom} outside [{ce.lo}, {ce.hi}] (R7.12)")

    # watch masks (R7.6)
    unwatch = 0
    if role == "drive":
        for e in spec.edges:
            if e.kind == "emit" and e.side == side and e.mode != OD:
                unwatch |= spec.mask(e.writes)

    # time base (R7.7), Drive only
    inv_shift = {}
    if role == "drive" and not errs:
        inv_shift = _time_base(spec, edges, errs)

    # slot order (otherwise last, R7.9), fan-out (R2.2), halt (R3.4), resync (R7.7)
    for l in spec.locs:
        es = edges[l.name]
        edges[l.name] = [e for e in es if not e.otherwise] + [e for e in es if e.otherwise]
        if len(es) > T.NUM_SLOTS:
            errs.append(f"{l.name}: {len(es)} outgoing edges after role expansion > 4 (R2.2); a chain split would "
                        f"cost E+1 = 2 cycles per hop and is not automated (S36)")
        if not es and not l.halt:
            errs.append(f"{l.name}: no outgoing edge and not declared halt (R3.4)")
        if es and l.halt:
            errs.append(f"{l.name}: a halt location has outgoing edges (R3.4)")
    if spec.resync_loc is not None:
        r = spec.resync_loc
        if r.invariant is not None or any(e.ck is not None for e in edges[r.name]):
            errs.append(f"{r.name}: the resync location may have no clock guard and no invariant (R7.7)")

    live = _reachable(spec, edges)
    warns += [f"{l.name}: unreachable from the initial and resync locations" for l in spec.locs if l.name not in live]
    _exactness(spec, edges, errs, warns)
    for l in spec.locs:
        _determinism(l, edges[l.name], role, errs)
    if errs:
        raise CompileError(errs)
    return _encode(spec, edges, role, side, unwatch, inv_shift, policy, cover, trace, cov_shift, warns)


def _encode(spec, edges, role, side, unwatch, inv_shift, policy, cover, trace, cov_shift, warns) -> Compiled:
    errs: List[str] = []
    img = T.EngineImage()
    loc_index = {l.name: i for i, l in enumerate(spec.locs)}
    windows: List[T.Window] = []
    patterns: List[T.Pattern] = []
    consts: List[int] = []
    actions: List[tuple] = [(0, 0, 0, 0, "NOP", 0, 0, 0)]

    def idx(tbl, v, limit, what, first=0):
        if v not in tbl:
            tbl.append(v)
            if len(tbl) == limit + 1:
                errs.append(f"more than {limit} {what} (R11)")
        i = tbl.index(v)
        return i + first if i < limit else 0          # placeholder; the error is raised below

    for l in spec.locs:
        li = loc_index[l.name]
        inv_en, inv_w = 0, 0
        if l.invariant is not None:
            s = inv_shift.get(l.name, 0)
            w = l.invariant
            inv_en = 1
            inv_w = idx(windows, T.Window(spec.clocks.index(w.clock), w.lo + s, w.hi + s, w.lo + s), 8, "windows")
        img.locs[li] = T.pack_loc(T.Loc(watch=spec.mask(l.watch) & ~unwatch, inv_en=inv_en, inv_win=inv_w,
                                        halt=int(l.halt)))
        es = edges[l.name]
        for s in range(T.NUM_SLOTS):
            if s >= len(es):
                img.edges[li * 4 + s] = T.INVALID_EDGE
                continue
            ce = es[s]
            p = idx(patterns, T.Pattern(ce.pmask, ce.pval & ce.pmask, ce.pmode), 7, "pin patterns", 1) \
                if ce.pmask else 0
            w = idx(windows, T.Window(ce.clock, ce.lo, ce.hi, ce.nom), 8, "windows") if ce.ck else 0
            dk = DG_CODES[ce.dk] if ce.dk else T.DG_NONE
            k = 0
            if ce.dk == "EVENT":
                k = ce.dval
            elif ce.dk:
                k = idx(consts, ce.dval, 8, "constants")
            a = idx(actions, ce.action_key(), 16, "actions")
            img.edges[li * 4 + s] = T.pack_edge(T.Edge(target=loc_index[ce.dst.name], pattern=p, window=w,
                                                       ck=CK_CODES[ce.ck], dk=dk, k=k, action=a, reset=ce.reset,
                                                       error=ce.error, valid=1, log=ce.log))
    resync_action = 0
    if spec.resync_loc is not None and role == "drive" and side in spec.resync_writes:
        wr, mode = spec.resync_writes[side]
        key = (spec.mask(wr), sum(v << spec.pins[p] for p, v in wr.items()), T.OD if mode == OD else T.PP,
               0, "NOP", 0, 0, 0)
        resync_action = idx(actions, key, 16, "actions")
    if errs:
        raise CompileError(errs)
    for i, w in enumerate(windows):
        img.windows[i] = w
    if not windows:
        img.windows[0] = T.Window(0, 0, 0, 0)
    for i, p in enumerate(patterns):
        img.patterns[i + 1] = p
    for i, c in enumerate(consts):
        img.consts[i] = c
    for i, (wm, wv, mode, d, op, ev, emit, pop) in enumerate(actions):
        img.actions[i] = T.pack_action(T.Action(wm=wm, wv=wv & wm, mode=mode, d=d, op=OP_CODES[op], ev=ev,
                                                emit=emit, pop=pop))
    img.config = T.EngineConfig(initial=loc_index[spec.initial_loc.name],
                                resync=loc_index[spec.resync_loc.name] if spec.resync_loc else None,
                                resync_action=resync_action, msb_first=int(spec.msb_first),
                                drive_en=int(role == "drive"), cover_en=int(cover), trace_en=int(trace),
                                cov_shift=cov_shift)
    return Compiled(img, loc_index, edges, _listing(spec, edges, role, side, loc_index, warns), warns, policy,
                    role, side)


def _listing(spec, edges, role, side, loc_index, warns) -> str:
    out = [f"spec {spec.name}  role {role}{' as ' + side if side else ''}  locations {len(spec.locs)}"]
    for l in spec.locs:
        es = edges[l.name]
        first = [e for e in es if e.ck is None and not (e.pmask and e.pmode == T.EDGE)]
        out.append(f"  [{loc_index[l.name]:2}] {l.name}  edges {len(es)}  watch {sorted(l.watch)}"
                   f"{'  HALT' if l.halt else ''}{'  may fire in first eval (R7.13)' if first else ''}")
        for s, e in enumerate(es):
            out.append(f"       {s}: {e.describe()}")
    out += [f"  warning: {w}" for w in warns]
    return "\n".join(out)


__all__ = ["compile_spec", "CompileError", "Compiled", "CEdge", "D_OBS"]
