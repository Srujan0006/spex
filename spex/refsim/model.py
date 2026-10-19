"""SPEX cycle-accurate reference interpreter, written from docs/SEMANTICS.md v1 (the golden model).

One rising edge per step(); two-phase update (read the old state `cur`, write the new state `nxt`).
outputs() is a pure function of the state (R0.3). Rule numbers (R..) refer to SEMANTICS.md.

API (DTC style):
    m = Spex(num_engines=2)
    m.step(pads_in, host_op) -> StepResult      one rising edge (R0.2)
    m.outputs() -> Outputs                      pad out / oe during the current cycle
    m.run(n, pads_in)
Host operations (R12.4) are HostOp(kind, engine, arg), one per step:
    load (arg = EngineImage), start, stop, push_tx, push_token, pop_rx, policy (arg = Policy), seed, cov_select, clear
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import List, Optional

from .tables import (CK_GE, CK_NONE, CK_POLICY, CK_WIN, DG_BITCNT_EQ, DG_BITCNT_LT, DG_EVENT, DG_NONE,
                     DG_SR_MATCH, DG_SR_NOMATCH, DG_TOKEN, DG_TXF_NE, EDGE, NUM_SLOTS, OD, OP_CLR, OP_LOAD,
                     OP_LOAD_PEEK, OP_LOAD_PUSH, OP_NOP, OP_PEEK, OP_PUSH, OP_SHIN, OP_SHOUT, POL_EARLIEST,
                     POL_LATEST, POL_NOMINAL, POL_RANDOM, POL_SWEEP, XMAX, EngineImage, unpack_action,
                     unpack_edge, unpack_loc)

M32 = 0xFFFFFFFF
LFSR_TAPS = 0x80200003                     # R8.2: x^32 + x^22 + x^2 + x + 1, Galois, right shift

STOPPED, RUNNING, HALTED = "STOPPED", "RUNNING", "HALTED"
ENTRY, EVAL = "ENTRY", "EVAL"

# violation kind bits (R6.3)
UNEXPECTED, TIMEOUT, SPEC_ERROR = 1, 2, 4

# sticky flags
F_VIOL, F_TX_UNDERFLOW, F_RX_OVERFLOW, F_HOST_ERR, F_TRACE_LOST, F_COV_LOST, F_FIFO_OVERFLOW = (
    1, 2, 4, 8, 16, 32, 64)


@dataclass(frozen=True)
class Params:
    tx_depth: int = 8
    rx_depth: int = 8
    token_depth: int = 8
    trace_depth: int = 64
    cov_queue: int = 4


@dataclass(frozen=True)
class Policy:
    mode: int = POL_NOMINAL
    k: int = 0
    step: int = 0


@dataclass(frozen=True)
class HostOp:
    kind: str
    engine: int = 0
    arg: object = None


@dataclass(frozen=True)
class TraceRecord:
    """R6.4."""
    type: str                 # "EDGE" or "VIOL"
    cycle: int                # global cycle of the event, pin-bus time
    engine: int
    loc: int
    slot: int                 # fired slot, 7 for a violation
    kind: int                 # violation bits (0 for an EDGE record that is not an error edge)
    pins: int
    value: int
    ts: int


@dataclass(frozen=True)
class Fired:
    engine: int
    loc: int
    slot: int
    target: int
    age: int
    tau: int                  # global cycle of the trigger instant
    ts: int


@dataclass(frozen=True)
class Outputs:
    out: int
    oe: int


@dataclass
class StepResult:
    fired: List[Fired] = field(default_factory=list)
    violations: List[TraceRecord] = field(default_factory=list)
    read_data: Optional[int] = None


@dataclass
class EngineState:
    image: Optional[EngineImage] = None
    state: str = STOPPED
    loc: int = 0
    phase: str = ENTRY
    first: bool = False
    x: List[int] = field(default_factory=lambda: [0, 0, 0])
    pend1: int = 0
    pend2: int = 0
    pev: int = 0
    t_e: List[int] = field(default_factory=lambda: [0] * NUM_SLOTS)
    out: int = 0              # engine-local pins (before the pin-base rotation, R12.6)
    oe: int = 0
    ev_out: int = 0           # event lines this engine drives in the current cycle (R10.1)
    sr: int = 0
    bitcnt: int = 0
    tx: List[int] = field(default_factory=list)
    rx: List[int] = field(default_factory=list)
    tok: List[int] = field(default_factory=list)
    flags: int = 0
    viol_count: int = 0
    policy: Policy = Policy()

    def copy(self) -> "EngineState":
        n = copy.copy(self)
        n.x, n.t_e, n.tx, n.rx, n.tok = list(self.x), list(self.t_e), list(self.tx), list(self.rx), list(self.tok)
        return n                                   # the image is shared: tables are not state that steps change


@dataclass
class ChipState:
    engines: List[EngineState]
    cycle: int = 0
    sync1: int = 0
    sync2: int = 0
    pin_prev: int = 0
    lfsr: int = 1
    trace: List[TraceRecord] = field(default_factory=list)
    flags: int = 0
    cov: dict = field(default_factory=dict)       # (engine, index) -> 32-bit word
    cov_engine: int = 0
    cov_q: int = 0

    def copy(self) -> "ChipState":
        n = copy.copy(self)
        n.engines = [e.copy() for e in self.engines]
        n.trace = list(self.trace)
        n.cov = dict(self.cov)
        return n


def rotr8(v: int, b: int) -> int:
    b %= 8
    return ((v >> b) | (v << (8 - b))) & 0xFF


def rotl8(v: int, b: int) -> int:
    return rotr8(v, 8 - (b % 8))


def lfsr_next(v: int) -> int:
    return (v >> 1) ^ (LFSR_TAPS if v & 1 else 0)


def random_time(lo: int, hi: int, raw: int) -> int:
    """R8.2: power-of-two mask, then fold into [lo, hi]."""
    d = hi - lo
    if d <= 0:
        return lo
    m = (1 << d.bit_length()) - 1
    r = raw & m
    if r > d:
        r -= d + 1
    return lo + r


def _sat(v: int) -> int:
    return v if v < XMAX else XMAX


class Spex:
    def __init__(self, num_engines: int = 2, params: Params = Params()):
        self.params = params
        self.num_engines = num_engines
        self.s = self._fresh()

    def _fresh(self) -> ChipState:
        return ChipState(engines=[EngineState() for _ in range(self.num_engines)])

    # ------------------------------------------------------------------ public API
    @property
    def cycle(self) -> int:
        return self.s.cycle

    def reset(self) -> None:
        """rst_n (R12.1, R12.3). Loaded images survive: tables are not reset."""
        images = [e.image for e in self.s.engines]
        self.s = self._fresh()
        for e, img in zip(self.s.engines, images):
            e.image = img

    def outputs(self) -> Outputs:
        """R0.3, R2.9, R12.6: pure function of the state."""
        out = oe = 0
        for e in self.s.engines:                    # later engines win a conflict (engine 1 wins)
            if e.image is None:
                continue
            b = e.image.config.pin_base
            eoe = rotl8(e.oe, b) if e.image.config.drive_en else 0
            eout = rotl8(e.out, b)
            out = (out & ~eoe) | (eout & eoe)
            oe |= eoe
        return Outputs(out & 0xFF, oe & 0xFF)

    def run(self, n: int, pads_in: int) -> None:
        for _ in range(n):
            self.step(pads_in)

    # ------------------------------------------------------------------ one rising edge
    def step(self, pads_in: int, host: Optional[HostOp] = None) -> StepResult:
        cur, nxt = self.s, self.s.copy()
        res = StepResult()
        n = cur.cycle
        P = cur.sync2                                 # R4.1: P_n = pad[n-2]
        chg = P ^ cur.pin_prev                        # R0.6
        ev_n = 0
        for e in cur.engines:
            ev_n |= e.ev_out                          # R10.1: OR of all engines, emitter included
        for i in range(self.num_engines):
            self._engine(cur, nxt, i, P, chg, ev_n, res)
        # coverage queue (R9.2, R9.3): drains one update per cycle
        nxt.cov_q = max(nxt.cov_q - 1, 0)
        self._seed = None
        if host is not None:
            self._host(cur, nxt, host, res)
        # chip registers
        nxt.sync1, nxt.sync2, nxt.pin_prev = pads_in & 0xFF, cur.sync1, cur.sync2
        nxt.lfsr = lfsr_next(cur.lfsr) if self._seed is None else self._seed   # R8.2: every cycle
        nxt.cycle = (n + 1) & M32
        self.s = nxt
        return res

    # ------------------------------------------------------------------ host (R12)
    def _host(self, cur: ChipState, nxt: ChipState, h: HostOp, res: StepResult) -> None:
        ce, ne = cur.engines[h.engine], nxt.engines[h.engine]
        stopped = ce.state != RUNNING
        p = self.params
        if h.kind == "load":
            if stopped:
                ne.image = h.arg
            else:
                ne.flags |= F_HOST_ERR                # R12.2
        elif h.kind == "start":
            if not stopped or ce.image is None:
                ne.flags |= F_HOST_ERR
                return
            ne.state, ne.loc, ne.phase, ne.first = RUNNING, ce.image.config.initial, ENTRY, False
            ne.x = [1, 1, 1]                          # R12.4: 0 at cycle n
            ne.pend1 = ne.pend2 = ne.pev = 0
            ne.ev_out = 0
        elif h.kind == "stop":
            ne.state, ne.oe, ne.ev_out = STOPPED, 0, 0
        elif h.kind == "push_tx":
            self._push(ne.tx, h.arg, p.tx_depth, ne)
        elif h.kind == "push_token":
            self._push(ne.tok, h.arg, p.token_depth, ne)
        elif h.kind == "pop_rx":                      # the pop sees the old head (R12.4)
            if ce.rx:
                res.read_data = ce.rx[0]
                ne.rx.pop(0)
        elif h.kind == "policy":
            ne.policy = h.arg
        elif h.kind == "seed":
            self._seed = (h.arg & M32) or 1           # R8.2; replaces this cycle's advance
        elif h.kind == "cov_select":
            nxt.cov_engine = h.arg
        elif h.kind == "clear":
            ne.flags, ne.viol_count = 0, 0
            nxt.flags = 0
            nxt.trace = []
            nxt.cov = {k: v for k, v in nxt.cov.items() if k[0] != h.engine}
        else:
            raise ValueError(f"unknown host op {h.kind}")

    @staticmethod
    def _push(fifo: list, v: int, depth: int, ne: EngineState) -> None:
        if len(fifo) < depth:
            fifo.append(v & 0xFF)
        else:
            ne.flags |= F_FIFO_OVERFLOW

    # ------------------------------------------------------------------ engine (R3.6)
    def _engine(self, cur: ChipState, nxt: ChipState, i: int, Pc: int, chgc: int, ev_n: int,
                res: StepResult) -> None:
        ce, ne = cur.engines[i], nxt.engines[i]
        ne.ev_out = 0
        ne.x = [_sat(v + 1) for v in ce.x]            # R1.2, R1.4: every cycle, saturating
        if ce.state != RUNNING:
            return
        img = ce.image
        cfg = img.config
        P, chg = rotr8(Pc, cfg.pin_base), rotr8(chgc, cfg.pin_base)
        n = cur.cycle
        if ce.phase == ENTRY:
            ne.pend1 = chg
            ne.pend2 = ce.pend2
            ne.pev = ce.pev | ev_n
            for s in range(NUM_SLOTS):
                e = unpack_edge(img.edge(ce.loc, s))
                if e.valid and e.ck == CK_POLICY:
                    ne.t_e[s] = self._policy_time(ce, img, e, s, cur.lfsr)
            ne.phase, ne.first = EVAL, True
            return
        # EVAL
        age0 = chg
        age1 = ce.pend1 if ce.first else 0
        age2 = ce.pend2 if ce.first else 0
        pend = age0 | age1 | age2
        evs = ce.pev | ev_n
        ne.first = False
        for s in range(NUM_SLOTS):
            e = unpack_edge(img.edge(ce.loc, s))
            if not e.valid:
                continue
            ok, a, v, tm = self._guard(ce, img, e, s, P, pend, age0, age1, evs)
            if ok:
                self._fire(cur, nxt, i, ce, ne, img, e, s, P, pend, a, v, tm, evs, res)
                return
        self._violations(cur, nxt, i, ce, ne, img, P, pend, age1, age2, res)

    @staticmethod
    def _age(pins: int, age0: int, age1: int) -> int:
        """R5.4: smallest age among the given pending pins (0 if none)."""
        if pins == 0 or pins & age0:
            return 0
        if pins & age1:
            return 1
        return 2

    def _guard(self, ce, img, e, slot, P, pend, age0, age1, evs):
        """R2.3-R2.6. Returns (enabled, a_e, v_e on the timestamp clock, tmask)."""
        tm = 0
        if e.pattern:
            pat = img.pattern(e.pattern)
            tm = pat.mask
            if (P & tm) != (pat.value & tm):
                return False, 0, 0, tm
            if pat.mode == EDGE and not (pend & tm):
                return False, 0, 0, tm
        a = self._age(pend & tm, age0, age1)
        if e.ck == CK_NONE:
            v, lo = max(ce.x[0] - a, 0), 0
            ck_ok = True
        else:
            w = img.window(e.window)
            v = max(ce.x[w.clock] - a, 0)                         # R2.5: trigger instant
            if e.ck == CK_GE:
                ck_ok = v >= w.lo
            elif e.ck == CK_WIN:
                ck_ok = w.lo <= v <= w.hi
            else:
                ck_ok = ce.t_e[slot] <= v <= w.hi
        if not ck_ok:
            return False, a, v, tm
        return self._data(ce, img, e, evs), a, v, tm

    @staticmethod
    def _data(ce, img, e, evs) -> bool:
        dk = e.dk
        if dk == DG_NONE:
            return True
        if dk == DG_EVENT:
            return bool((evs >> e.k) & 1)
        if dk == DG_TXF_NE:
            return len(ce.tx) > 0
        K = img.const(e.k)
        if dk == DG_BITCNT_EQ:
            return ce.bitcnt == (K & 0xFF)
        if dk == DG_BITCNT_LT:
            return ce.bitcnt < (K & 0xFF)
        if dk in (DG_SR_MATCH, DG_SR_NOMATCH):
            m = (K >> 8) & 0xFF
            match = (ce.sr & m) == (K & m)
            return match if dk == DG_SR_MATCH else not match
        if dk == DG_TOKEN:
            return bool(ce.tok) and ce.tok[0] == (K & 0xFF)
        raise AssertionError(dk)

    def _policy_time(self, ce, img, e, slot, lfsr) -> int:
        """R8.1-R8.2, latched in the entry cycle."""
        w = img.window(e.window)
        pol = ce.policy
        if pol.mode == POL_NOMINAL:
            return w.nom
        if pol.mode == POL_EARLIEST:
            return w.lo
        if pol.mode == POL_LATEST:
            return w.hi
        if pol.mode == POL_RANDOM:
            sh = (8 * slot) % 32
            raw = ((lfsr >> sh) | (lfsr << (32 - sh))) & M32 if sh else lfsr
            return random_time(w.lo, w.hi, raw & 0xFFFFF)
        if pol.mode == POL_SWEEP:
            return min(w.lo + pol.k * pol.step, w.hi)
        raise ValueError(pol.mode)

    # ------------------------------------------------------------------ actions (R2.9, R2.10)
    def _action(self, ce, ne, img, idx, P, cfg):
        a = unpack_action(img.action(idx))
        wv = a.wv
        msb = cfg.msb_first

        def outbit(sr):
            return (sr >> 7) & 1 if msb else sr & 1

        def shift(sr, b):
            return (((sr << 1) | b) & 0xFF) if msb else ((sr >> 1) | (b << 7))

        def load():
            if ne.tx:
                ne.sr = ne.tx.pop(0)
            else:
                ne.sr = 0xFF
                ne.flags |= F_TX_UNDERFLOW
            ne.bitcnt = 0

        def push():
            if len(ne.rx) < self.params.rx_depth:
                ne.rx.append(ne.sr & 0xFF)
            else:
                ne.flags |= F_RX_OVERFLOW
            ne.bitcnt = 0

        op, d = a.op, a.d
        dbit = None
        if op == OP_NOP:
            pass
        elif op == OP_LOAD:
            load()
        elif op == OP_PUSH:
            push()
        elif op == OP_LOAD_PUSH:
            push()
            load()
        elif op == OP_SHIN:
            ne.sr = shift(ce.sr, (P >> d) & 1)
            ne.bitcnt = min(ce.bitcnt + 1, 63)
        elif op == OP_SHOUT:
            dbit = outbit(ce.sr)
            ne.sr = shift(ce.sr, 1)
            ne.bitcnt = min(ce.bitcnt + 1, 63)
        elif op == OP_PEEK:
            dbit = outbit(ce.sr)
        elif op == OP_LOAD_PEEK:
            load()
            dbit = outbit(ne.sr)
        elif op == OP_CLR:
            ne.bitcnt = 0
        # reserved ops 9-15: NOP in the model (R2.10)
        wm = a.wm
        if dbit is not None:
            wv = (wv & ~(1 << d)) | (dbit << d)
        if a.mode == OD:
            ne.out = ne.out & ~wm
            ne.oe = (ne.oe & ~wm) | (~wv & wm)
        else:
            ne.out = (ne.out & ~wm) | (wv & wm)
            ne.oe = ne.oe | wm
        ne.out &= 0xFF
        ne.oe &= 0xFF
        if a.emit:
            ne.ev_out |= 1 << a.ev
        if a.pop and ne.tok:
            ne.tok.pop(0)

    # ------------------------------------------------------------------ firing (R3.7)
    def _fire(self, cur, nxt, i, ce, ne, img, e, slot, P, pend, a, v, tm, evs, res):
        cfg = img.config
        n = cur.cycle
        self._action(ce, ne, img, e.action, P, cfg)
        for c in range(3):
            if (e.reset >> c) & 1:
                ne.x[c] = 1 + a                                   # R1.6
        ne.pend2, ne.pend1 = pend & ~tm, 0                        # R5.5 carry-over
        ne.pev = evs & ~((1 << e.k) if e.dk == DG_EVENT else 0)   # R10.2
        ne.loc = e.target
        if unpack_loc(img.loc(e.target)).halt:
            ne.state = HALTED                                     # R3.4
        else:
            ne.phase = ENTRY
        tau = (n - a) & M32
        lo = img.window(e.window).lo if e.ck != CK_NONE else 0
        res.fired.append(Fired(i, ce.loc, slot, e.target, a, tau, v))
        if e.log:
            if cfg.cover_en and cur.cov_engine == i:
                self._cover(nxt, i, ce.loc * NUM_SLOTS + slot, v, lo, cfg.cov_shift)
            if cfg.trace_en:
                self._trace(nxt, ne, TraceRecord("EDGE", tau, i, ce.loc, slot, 0, pend & tm, P, v))
        if e.error:                                               # R3.7: fires normally, plus a record
            self._count_violation(nxt, ne, TraceRecord("VIOL", tau, i, ce.loc, slot, SPEC_ERROR, pend & tm, P, v), res)

    def _cover(self, nxt, i, idx, ts, lo, s):
        off = min((ts - lo) >> s, 4095)
        w = nxt.cov.get((i, idx), 0)
        cnt, mn, mx = w >> 24, (w >> 12) & 0xFFF, w & 0xFFF
        if cnt == 0:
            mn = mx = off
        else:
            mn, mx = min(mn, off), max(mx, off)
        nxt.cov[(i, idx)] = (min(cnt + 1, 255) << 24) | (mn << 12) | mx
        nxt.cov_q += 1
        if nxt.cov_q > self.params.cov_queue:
            nxt.cov_q = self.params.cov_queue
            nxt.flags |= F_COV_LOST

    def _trace(self, nxt, ne, rec):
        if len(nxt.trace) < self.params.trace_depth:
            nxt.trace.append(rec)
        else:
            ne.flags |= F_TRACE_LOST

    def _count_violation(self, nxt, ne, rec, res):
        ne.viol_count = min(ne.viol_count + 1, 0xFFFF)
        ne.flags |= F_VIOL
        res.violations.append(rec)
        if ne.image.config.trace_en:
            self._trace(nxt, ne, rec)

    # ------------------------------------------------------------------ violations (R6)
    def _violations(self, cur, nxt, i, ce, ne, img, P, pend, age1, age2, res):
        n = cur.cycle
        lw = unpack_loc(img.loc(ce.loc))
        U = pend & lw.watch
        T = False
        tsv = ce.x[0]
        if lw.inv_en:
            w = img.window(lw.inv_win)
            tsv = ce.x[w.clock]
            T = ce.x[w.clock] > w.hi
        if not U and not T:
            ne.pend1 = ne.pend2 = 0                               # R6.6: dropped
            ne.pev = 0
            return
        kind = (UNEXPECTED if U else 0) | (TIMEOUT if T else 0)
        if U:
            maxage = 2 if U & age2 else (1 if U & age1 else 0)
            cyc = (n - maxage) & M32
        else:
            cyc = n
        rec = TraceRecord("VIOL", cyc, i, ce.loc, 7, kind, U, P, tsv)
        self._count_violation(nxt, ne, rec, res)
        cfg = img.config
        if cfg.resync is None:                                    # R6.5
            ne.state = HALTED
            return
        ne.loc, ne.phase = cfg.resync, ENTRY
        ne.x = [1, 1, 1]
        ne.pend1 = ne.pend2 = ne.pev = 0
        ne.bitcnt = 0
        self._action(ce, ne, img, cfg.resync_action, P, cfg)
        ne.bitcnt = 0
