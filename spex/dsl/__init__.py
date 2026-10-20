"""SPEX spec language: an embedded Python DSL for timed-automaton protocol specs (decision S16, SEMANTICS §7).

A spec names its pins, sides, clocks, windows and locations, and has three kinds of edge (R7.2):

    s = Spec("uart_8n1", sides=["tx", "rx"], pins={"TX": 0}, clocks=["g"], msb_first=False)
    IDLE = s.loc("IDLE", watch=["TX"])
    bit = s.window("g", 2, 10, nom=6)
    s.emit(IDLE, START, "tx", {"TX": 0}, data=txf_ne(), op=Op("LOAD"), reset=["g"])   # owned by side tx
    s.observe(A, B, {"SCL": 1}, within=bit)                                           # a line event, no owner
    s.internal(A, B, after=bit, reset=["g"])                                          # clock or data only

Windows are in *line time* (R7.7): the compiler converts them to engine time for each role.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

DATA = "DATA"                    # a written value that comes from the shift register (R2.10)
PP, OD = "PP", "OD"
EDGE, LEVEL = "EDGE", "LEVEL"
OPS = ("NOP", "LOAD", "PUSH", "LOAD_PUSH", "SHIN", "SHOUT", "PEEK", "LOAD_PEEK", "CLR")


class SpecError(Exception):
    pass


@dataclass(frozen=True)
class Window:
    clock: str
    lo: int
    hi: int
    nom: int


@dataclass(frozen=True)
class DataGuard:
    kind: str                    # BITCNT_EQ BITCNT_LT SR_MATCH SR_NOMATCH EVENT TXF_NE
    value: int = 0               # constant (16-bit, R2.6) or event index


def bitcnt_eq(n: int) -> DataGuard:
    return DataGuard("BITCNT_EQ", n)


def bitcnt_lt(n: int) -> DataGuard:
    return DataGuard("BITCNT_LT", n)


def sr_match(value: int, mask: int = 0xFF) -> DataGuard:
    return DataGuard("SR_MATCH", (mask << 8) | value)


def sr_nomatch(value: int, mask: int = 0xFF) -> DataGuard:
    return DataGuard("SR_NOMATCH", (mask << 8) | value)


def event(j: int) -> DataGuard:
    return DataGuard("EVENT", j)


def txf_ne() -> DataGuard:
    return DataGuard("TXF_NE")


@dataclass(frozen=True)
class Op:
    kind: str
    pin: Optional[str] = None    # data pin for SHIN / SHOUT / PEEK / LOAD_PEEK


@dataclass(eq=False)
class Loc:
    name: str
    watch: frozenset
    invariant: Optional[Window]
    halt: bool

    def __repr__(self):
        return self.name


@dataclass(eq=False)
class SpecEdge:
    kind: str                                # emit / observe / internal
    src: Loc
    dst: Loc
    side: Optional[str] = None               # owner of an emit
    writes: Dict[str, object] = field(default_factory=dict)   # pin -> 0 / 1 / DATA
    mode: str = PP                           # write mode of an emit
    pins: Dict[str, int] = field(default_factory=dict)        # pattern (observe edges, emit triggers)
    pmode: str = EDGE
    ck: Optional[str] = None                 # GE / WIN / POLICY
    window: Optional[Window] = None
    data: Optional[DataGuard] = None
    token: Optional[int] = None              # choice token (emits only)
    peek: bool = False                       # test the token without popping (R7.10)
    op: Op = Op("NOP")
    reset: tuple = ()
    event: Optional[int] = None
    log: bool = True
    error: bool = False
    otherwise: bool = False
    label: str = ""


class Spec:
    def __init__(self, name: str, sides: Sequence[str], pins: Dict[str, int], clocks: Sequence[str] = ("x0",),
                 msb_first: bool = True):
        if len(clocks) > 3:
            raise SpecError("at most 3 clocks (R1.2)")
        if any(not 0 <= p < 8 for p in pins.values()) or len(set(pins.values())) != len(pins):
            raise SpecError("pins must be distinct indices 0..7")
        self.name, self.sides, self.pins, self.clocks = name, list(sides), dict(pins), list(clocks)
        self.msb_first = msb_first
        self.locs: List[Loc] = []
        self.edges: List[SpecEdge] = []
        self.initial_loc: Optional[Loc] = None
        self.resync_loc: Optional[Loc] = None
        self.resync_writes: Dict[str, tuple] = {}   # side -> (writes dict, mode)

    # ---------------------------------------------------------------- structure
    def loc(self, name: str, watch: Iterable[str] = (), invariant: Optional[Window] = None,
            halt: bool = False) -> Loc:
        if any(l.name == name for l in self.locs):
            raise SpecError(f"duplicate location {name}")
        for p in watch:
            self._pin(p)
        if invariant is not None:
            self._win_ok(invariant)
        l = Loc(name, frozenset(watch), invariant, halt)
        self.locs.append(l)
        if self.initial_loc is None:
            self.initial_loc = l
        return l

    def locs_named(self, names: str) -> List[Loc]:
        return [self.loc(n) for n in names.split()]

    def window(self, clock: str, lo: int, hi: int, nom: Optional[int] = None) -> Window:
        w = Window(clock, lo, hi, lo if nom is None else nom)
        self._win_ok(w)
        return w

    def initial(self, loc: Loc) -> None:
        self.initial_loc = loc

    def resync(self, loc: Loc, writes: Optional[Dict[str, tuple]] = None) -> None:
        """Declare the resync location (R6.5); writes = {side: ({pin: value}, mode)} applied in Drive as that side."""
        self.resync_loc = loc
        self.resync_writes = dict(writes or {})

    # ---------------------------------------------------------------- edges (R7.2)
    def emit(self, src: Loc, dst: Loc, side: str, writes: Dict[str, object], mode: str = PP,
             at: Optional[Window] = None, on: Optional[Dict[str, int]] = None, within: Optional[Window] = None,
             data: Optional[DataGuard] = None, token: Optional[int] = None, peek: bool = False,
             op: Op = Op("NOP"), reset: Iterable[str] = (), event: Optional[int] = None, log: bool = True,
             error: bool = False, label: str = "") -> SpecEdge:
        """An emit by `side`: timed (`at` = POLICY window), reactive (`on` = EDGE trigger, optional `within`),
        or data-triggered (`data` / `token` only)."""
        if side not in self.sides:
            raise SpecError(f"unknown side {side}")
        if not writes:
            raise SpecError("an emit writes at least one pin")
        if at is not None and on is not None:
            raise SpecError("an emit is timed (at=) or reactive (on=), not both")
        for p, v in writes.items():
            self._pin(p)
            if v not in (0, 1, DATA):
                raise SpecError(f"write value of {p} must be 0, 1 or DATA")
        e = SpecEdge("emit", src, dst, side=side, writes=dict(writes), mode=mode, data=data, token=token, peek=peek,
                     op=op, reset=tuple(reset), event=event, log=log, error=error, label=label)
        if at is not None:
            e.ck, e.window = "POLICY", self._win_ok(at)
        if on is not None:
            e.pins, e.pmode = self._pattern(on), EDGE
            if within is not None:
                e.ck, e.window = "WIN", self._win_ok(within)
        return self._add(e)

    def observe(self, src: Loc, dst: Loc, pins: Dict[str, int], mode: str = EDGE, within: Optional[Window] = None,
                after: Optional[Window] = None, data: Optional[DataGuard] = None, op: Op = Op("NOP"),
                reset: Iterable[str] = (), event: Optional[int] = None, log: bool = True, error: bool = False,
                otherwise: bool = False, label: str = "") -> SpecEdge:
        e = SpecEdge("observe", src, dst, pins=self._pattern(pins), pmode=mode, data=data, op=op, reset=tuple(reset),
                     event=event, log=log, error=error, otherwise=otherwise, label=label)
        self._clock(e, within, after)
        return self._add(e)

    def internal(self, src: Loc, dst: Loc, within: Optional[Window] = None, after: Optional[Window] = None,
                 data: Optional[DataGuard] = None, op: Op = Op("NOP"), reset: Iterable[str] = (),
                 event: Optional[int] = None, log: bool = True, error: bool = False, otherwise: bool = False,
                 label: str = "") -> SpecEdge:
        e = SpecEdge("internal", src, dst, data=data, op=op, reset=tuple(reset), event=event, log=log, error=error,
                     otherwise=otherwise, label=label)
        self._clock(e, within, after)
        return self._add(e)

    # ---------------------------------------------------------------- helpers
    def _add(self, e: SpecEdge) -> SpecEdge:
        if e.src not in self.locs or e.dst not in self.locs:
            raise SpecError("edge between locations of another spec")
        for c in e.reset:
            if c not in self.clocks:
                raise SpecError(f"unknown clock {c}")
        if e.op.kind not in OPS:
            raise SpecError(f"unknown or reserved datapath op {e.op.kind} (R2.10)")
        if e.op.pin is not None:
            self._pin(e.op.pin)
        if e.event is not None and not 0 <= e.event < 8:
            raise SpecError("event index 0..7")
        e.label = e.label or f"{e.src.name}->{e.dst.name}#{len(self.edges)}"
        self.edges.append(e)
        return e

    def _clock(self, e, within, after):
        if within is not None and after is not None:
            raise SpecError("within= or after=, not both")
        if within is not None:
            e.ck, e.window = "WIN", self._win_ok(within)
        elif after is not None:
            e.ck, e.window = "GE", self._win_ok(after)

    def _pin(self, p: str) -> int:
        if p not in self.pins:
            raise SpecError(f"unknown pin {p}")
        return self.pins[p]

    def _pattern(self, pins: Dict[str, int]) -> Dict[str, int]:
        for p, v in pins.items():
            self._pin(p)
            if v not in (0, 1):
                raise SpecError("pattern values are 0 or 1")
        return dict(pins)

    def _win_ok(self, w: Window) -> Window:
        if w.clock not in self.clocks:
            raise SpecError(f"unknown clock {w.clock}")
        if not 0 <= w.lo <= w.hi:
            raise SpecError(f"window needs 0 <= lo <= hi: {w}")
        return w

    def mask(self, pins: Iterable[str]) -> int:
        m = 0
        for p in pins:
            m |= 1 << self._pin(p)
        return m
