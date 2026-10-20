"""Hand-written table images for model tests (not the compiler): locations, edges and small tables,
packed in the SEMANTICS §11 format, plus a cycle-by-cycle runner that records what each cycle looked like."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from spex.refsim import (CK_NONE, DG_EVENT, DG_NONE, Action, Edge, EngineConfig, EngineImage, HostOp, Loc,
                         Pattern, Spex, Window, pack_action, pack_edge, pack_loc)


class ImageBuilder:
    def __init__(self):
        self.locs: Dict[int, Loc] = {}
        self.edges: Dict[int, List[Edge]] = {}
        self.windows: List[tuple] = []
        self.patterns: List[Pattern] = []
        self.consts: List[int] = []
        self.actions: List[Action] = [Action()]          # entry 0 = empty action (R11.2)

    def loc(self, i: int, watch: int = 0, inv: Optional[tuple] = None, halt: int = 0) -> int:
        self.locs[i] = Loc(watch=watch, inv_en=int(inv is not None), inv_win=self._win(inv) if inv else 0, halt=halt)
        self.edges.setdefault(i, [])
        return i

    def _idx(self, tbl, v, limit, first=0):
        if v in tbl:
            return tbl.index(v) + first
        tbl.append(v)
        assert len(tbl) <= limit, "table full"
        return len(tbl) - 1 + first

    def _win(self, w) -> int:
        c, lo, hi = w[:3]
        nom = w[3] if len(w) > 3 else lo
        return self._idx(self.windows, (c, lo, hi, nom), 16)        # nom goes to the nominal table (S44)

    def edge(self, src: int, target: int, pat: Optional[tuple] = None, ck: int = CK_NONE,
             win: Optional[tuple] = None, dk: int = DG_NONE, k: int = 0, act: Optional[Action] = None,
             reset: int = 0, log: int = 1, error: int = 0) -> None:
        p = self._idx(self.patterns, Pattern(*pat), 7, first=1) if pat else 0
        w = self._win(win) if win else 0
        if dk not in (DG_NONE, DG_EVENT):
            k = self._idx(self.consts, k, 8)
        a = self._idx(self.actions, act, 16) if act else 0
        self.edges.setdefault(src, []).append(Edge(target, p, w, ck, dk, k, a, reset, error, 1, log))

    def build(self, **cfg) -> EngineImage:
        img = EngineImage(config=EngineConfig(**cfg))
        for i, l in self.locs.items():
            img.locs[i] = pack_loc(l)
            es = self.edges.get(i, [])
            assert len(es) <= 4
            for s in range(4):
                img.edges[i * 4 + s] = pack_edge(es[s]) if s < len(es) else 0
        for i, (c, lo, hi, nom) in enumerate(self.windows):
            img.windows[i] = Window(c, lo, hi)
            if i < len(img.noms):
                img.noms[i] = nom
        if not self.windows:
            img.windows[0] = Window(0, 0, 0)
        for i, p in enumerate(self.patterns):
            img.patterns[i + 1] = p
        for i, c in enumerate(self.consts):
            img.consts[i] = c
        for i, a in enumerate(self.actions):
            img.actions[i] = pack_action(a)
        if "resync_action" in cfg and isinstance(cfg["resync_action"], Action):
            img.config.resync_action = self._idx(self.actions, cfg["resync_action"], 16)
            img.actions[img.config.resync_action] = pack_action(cfg["resync_action"])
        return img


@dataclass
class Row:
    n: int
    state: str
    loc: int
    phase: str
    first: bool
    x: tuple
    out: int
    oe: int
    fired: list
    viols: list
    P: int


def run(m: Spex, cycles: int, pads: Callable[[int], int], host: Optional[Dict[int, HostOp]] = None,
        engine: int = 0) -> List[Row]:
    """Row n describes cycle n (state S_n and outputs), plus what fired/was raised in cycle n's evaluation."""
    host = host or {}
    rows = []
    for n in range(cycles):
        assert m.cycle == n
        e = m.s.engines[engine]
        P = m.s.sync2
        o = m.outputs()
        r = m.step(pads(n), host.get(n))
        rows.append(Row(n, e.state, e.loc, e.phase, e.first, tuple(e.x), o.out, o.oe,
                        [f for f in r.fired if f.engine == engine], [v for v in r.violations if v.engine == engine],
                        P))
    return rows


def start(img: EngineImage, engine: int = 0, num_engines: int = 1) -> Spex:
    """A model with `img` loaded on `engine` and started in cycle 0 (so every clock = n from cycle 1)."""
    m = Spex(num_engines=num_engines)
    m.s.engines[engine].image = img        # equivalent to a 'load' host op while stopped
    return m


START = {0: HostOp("start", 0)}
