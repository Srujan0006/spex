"""SPEX table formats, written from docs/SEMANTICS.md §11 (v1). Field packing and unpacking only.

Edge word (R11.1), action entry (R11.2), window (R11.3), pattern (R11.4), constant (R11.5),
location word (R11.6), engine configuration (R11.7).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

NUM_LOCS = 64
NUM_SLOTS = 4
NUM_ACTIONS = 16
NUM_WINDOWS = 8
NUM_PATTERNS = 8          # index 0 = "none"
NUM_CONSTS = 8
XBITS = 20
XMAX = (1 << XBITS) - 1

# clock guard kinds (R2.5)
CK_NONE, CK_GE, CK_WIN, CK_POLICY = 0, 1, 2, 3
# data guard kinds (R2.6)
DG_NONE, DG_BITCNT_EQ, DG_BITCNT_LT, DG_SR_MATCH, DG_EVENT, DG_TXF_NE, DG_TOKEN, DG_SR_NOMATCH = range(8)
# pattern modes (R2.4)
LEVEL, EDGE = 0, 1
# pin write modes (R2.9)
PP, OD = 0, 1
# datapath ops (R2.10)
OP_NOP, OP_LOAD, OP_PUSH, OP_LOAD_PUSH, OP_SHIN, OP_SHOUT, OP_PEEK, OP_LOAD_PEEK, OP_CLR, OP_PUSH_LOAD_PEEK = range(10)
# policies (R8.1)
POL_NOMINAL, POL_EARLIEST, POL_LATEST, POL_RANDOM, POL_SWEEP = range(5)


class UndefinedRead(Exception):
    """A table entry that was never written was read (SEMANTICS R12.1, as DTC D13)."""


def _chk(v: int, bits: int, name: str) -> int:
    if not 0 <= v < (1 << bits):
        raise ValueError(f"{name}={v} does not fit in {bits} bits")
    return v


# ---------------------------------------------------------------- edge word (R11.1)
@dataclass(frozen=True)
class Edge:
    target: int
    pattern: int = 0
    window: int = 0
    ck: int = CK_NONE
    dk: int = DG_NONE
    k: int = 0
    action: int = 0
    reset: int = 0
    error: int = 0
    valid: int = 1
    log: int = 0


def pack_edge(e: Edge) -> int:
    return (_chk(e.target, 7, "target") << 25 | _chk(e.pattern, 3, "pattern") << 22 | _chk(e.window, 3, "window") << 19
            | _chk(e.ck, 2, "ck") << 17 | _chk(e.dk, 3, "dk") << 14 | _chk(e.k, 3, "k") << 11
            | _chk(e.action, 4, "action") << 7 | _chk(e.reset, 3, "reset") << 4 | _chk(e.error, 1, "error") << 3
            | _chk(e.valid, 1, "valid") << 1 | _chk(e.log, 1, "log"))


def unpack_edge(w: int) -> Edge:
    return Edge(target=(w >> 25) & 0x7F, pattern=(w >> 22) & 7, window=(w >> 19) & 7, ck=(w >> 17) & 3,
                dk=(w >> 14) & 7, k=(w >> 11) & 7, action=(w >> 7) & 0xF, reset=(w >> 4) & 7,
                error=(w >> 3) & 1, valid=(w >> 1) & 1, log=w & 1)


INVALID_EDGE = 0          # valid bit clear


# ---------------------------------------------------------------- action entry (R11.2)
@dataclass(frozen=True)
class Action:
    wm: int = 0
    wv: int = 0
    mode: int = PP
    d: int = 0
    op: int = OP_NOP
    ev: int = 0
    emit: int = 0
    pop: int = 0


def pack_action(a: Action) -> int:
    return (_chk(a.wm, 8, "wm") | _chk(a.wv, 8, "wv") << 8 | _chk(a.mode, 1, "mode") << 16 | _chk(a.d, 3, "d") << 17
            | _chk(a.op, 4, "op") << 20 | _chk(a.ev, 3, "ev") << 24 | _chk(a.emit, 1, "emit") << 27
            | _chk(a.pop, 1, "pop") << 28)


def unpack_action(w: int) -> Action:
    return Action(wm=w & 0xFF, wv=(w >> 8) & 0xFF, mode=(w >> 16) & 1, d=(w >> 17) & 7, op=(w >> 20) & 0xF,
                  ev=(w >> 24) & 7, emit=(w >> 27) & 1, pop=(w >> 28) & 1)


# ---------------------------------------------------------------- location word (R11.6)
@dataclass(frozen=True)
class Loc:
    watch: int = 0
    inv_en: int = 0
    inv_win: int = 0
    halt: int = 0


def pack_loc(l: Loc) -> int:
    return _chk(l.watch, 8, "watch") | _chk(l.inv_win, 3, "inv_win") << 8 | _chk(l.inv_en, 1, "inv_en") << 11 \
        | _chk(l.halt, 1, "halt") << 12


def unpack_loc(w: int) -> Loc:
    return Loc(watch=w & 0xFF, inv_win=(w >> 8) & 7, inv_en=(w >> 11) & 1, halt=(w >> 12) & 1)


# ---------------------------------------------------------------- small tables (R11.3-R11.5)
@dataclass(frozen=True)
class Window:
    clock: int
    lo: int
    hi: int
    nom: int


@dataclass(frozen=True)
class Pattern:
    mask: int
    value: int
    mode: int


@dataclass
class EngineConfig:
    """R11.7."""
    initial: int = 0
    resync: Optional[int] = None          # None = no resync location: a violation halts (R6.5)
    resync_action: int = 0
    msb_first: int = 1
    drive_en: int = 1
    cover_en: int = 0
    trace_en: int = 1
    cov_shift: int = 0
    pin_base: int = 0


@dataclass
class EngineImage:
    """Everything the host loads into one engine. `None` = never written (reading it raises UndefinedRead)."""
    edges: List[Optional[int]] = field(default_factory=lambda: [None] * (NUM_LOCS * NUM_SLOTS))
    locs: List[Optional[int]] = field(default_factory=lambda: [None] * NUM_LOCS)
    actions: List[Optional[int]] = field(default_factory=lambda: [None] * NUM_ACTIONS)
    windows: List[Optional[Window]] = field(default_factory=lambda: [None] * NUM_WINDOWS)
    patterns: List[Optional[Pattern]] = field(default_factory=lambda: [None] * NUM_PATTERNS)
    consts: List[Optional[int]] = field(default_factory=lambda: [None] * NUM_CONSTS)
    config: EngineConfig = field(default_factory=EngineConfig)

    def edge(self, loc: int, slot: int) -> int:
        return _get(self.edges, loc * NUM_SLOTS + slot, f"edge {loc}.{slot}")

    def loc(self, loc: int) -> int:
        return _get(self.locs, loc, f"location word {loc}")

    def action(self, i: int) -> int:
        return _get(self.actions, i, f"action {i}")

    def window(self, i: int) -> Window:
        return _get(self.windows, i, f"window {i}")

    def pattern(self, i: int) -> Pattern:
        return _get(self.patterns, i, f"pattern {i}")

    def const(self, i: int) -> int:
        return _get(self.consts, i, f"constant {i}")


def _get(tbl, i, what):
    v = tbl[i]
    if v is None:
        raise UndefinedRead(what)
    return v

