"""SEMANTICS v1 rules not covered by the worked examples. Each test names its rule.

Mutants that must make this file fail are listed in tests/model/mutants.py."""
import collections

import pytest

from imgb import START, ImageBuilder, run, start
from spex.refsim import (CK_GE, CK_POLICY, CK_WIN, DG_BITCNT_EQ, DG_BITCNT_LT, DG_EVENT, DG_SR_MATCH,
                         DG_SR_NOMATCH, DG_TOKEN, DG_TXF_NE, EDGE, HALTED, LEVEL, OD, OP_LOAD, OP_LOAD_PEEK,
                         OP_PUSH, OP_SHIN, OP_SHOUT, POL_EARLIEST, POL_LATEST, POL_NOMINAL, POL_RANDOM,
                         POL_SWEEP, PP, RUNNING, SPEC_ERROR, STOPPED, XMAX, Action, HostOp, Policy, Spex,
                         UndefinedRead, random_time)
from spex.refsim.model import F_HOST_ERR, F_RX_OVERFLOW, F_TRACE_LOST, F_TX_UNDERFLOW, Params

X0, X1 = 1, 2
NEVER = (0x80, 0x80, EDGE)


def fires(rows):
    return [(r.n, f.loc, f.slot) for r in rows for f in r.fired]


def idle_loc(b, i, **kw):
    b.loc(i, **kw)
    b.edge(i, i, pat=NEVER)
    return i


# ---------------------------------------------------------------- clocks
def test_R1_4_clock_saturates_and_GE_stays_true():
    b = ImageBuilder()
    b.loc(0)
    b.edge(0, 1, pat=(1, 1, LEVEL), ck=CK_GE, win=(0, XMAX - 5, XMAX))
    idle_loc(b, 1)
    m = start(b.build())
    m.step(0, HostOp("start"))
    m.step(0)
    m.s.engines[0].x = [XMAX - 2, 0, 0]
    for _ in range(4):
        m.step(0)
    assert m.s.engines[0].x[0] == XMAX                       # saturated, not wrapped
    m.run(3, 1)                                             # pin0 = 1 reaches P after 2 cycles
    assert m.s.engines[0].loc == 1


def test_R1_6_reset_value_is_one_plus_age():
    """Edge triggered by a change seen in the entry cycle (age 1) resets x1 to 2."""
    b = ImageBuilder()
    b.loc(0)
    b.edge(0, 1, ck=CK_GE, win=(0, 10, 10))
    b.loc(1, watch=1)
    b.edge(1, 2, pat=(1, 1, EDGE), reset=X1)
    idle_loc(b, 2)
    m = start(b.build())
    rows = run(m, 16, lambda n: 1 if n >= 9 else 0, START)
    assert fires(rows) == [(10, 0, 0), (12, 1, 0)]
    assert rows[13].x[1] == 2 and rows[14].x[1] == 3


# ---------------------------------------------------------------- guards and priority
def test_R2_4_level_fires_without_change_edge_does_not():
    for mode, expect in ((LEVEL, True), (EDGE, False)):
        b = ImageBuilder()
        b.loc(0)
        b.edge(0, 1, ck=CK_GE, win=(0, 10, 10))
        b.loc(1)
        b.edge(1, 2, pat=(1, 1, mode))
        idle_loc(b, 2)
        rows = run(start(b.build()), 20, lambda n: 1, START)     # pin0 high long before location 1
        assert ((12, 1, 0) in fires(rows)) == expect


def test_R3_2_lowest_slot_wins():
    b = ImageBuilder()
    b.loc(0)
    b.edge(0, 1, ck=CK_GE, win=(0, 5, 5))
    b.edge(0, 2, ck=CK_GE, win=(0, 3, 3))                 # enabled earlier, but slot 1
    idle_loc(b, 1)
    idle_loc(b, 2)
    rows = run(start(b.build()), 10, lambda n: 0, START)
    assert fires(rows) == [(3, 0, 1)]
    b2 = ImageBuilder()
    b2.loc(0)
    b2.edge(0, 1, ck=CK_GE, win=(0, 4, 4))
    b2.edge(0, 2, ck=CK_GE, win=(0, 4, 4))
    idle_loc(b2, 1)
    idle_loc(b2, 2)
    assert fires(run(start(b2.build()), 10, lambda n: 0, START)) == [(4, 0, 0)]


@pytest.mark.parametrize("dk, k, sr, bitcnt, expect", [
    (DG_BITCNT_EQ, 3, 0, 3, True), (DG_BITCNT_EQ, 3, 0, 2, False),
    (DG_BITCNT_LT, 3, 0, 2, True), (DG_BITCNT_LT, 3, 0, 3, False),
    (DG_SR_MATCH, 0xFEA0, 0xA1, 0, True), (DG_SR_MATCH, 0xFEA0, 0xA2, 0, False),
    (DG_SR_NOMATCH, 0xFEA0, 0xA2, 0, True), (DG_SR_NOMATCH, 0xFEA0, 0xA1, 0, False),
])
def test_R2_6_data_guards(dk, k, sr, bitcnt, expect):
    b = ImageBuilder()
    b.loc(0)
    b.edge(0, 1, ck=CK_GE, win=(0, 3, 3), dk=dk, k=k)
    idle_loc(b, 1)
    m = start(b.build())
    m.s.engines[0].sr, m.s.engines[0].bitcnt = sr, bitcnt
    rows = run(m, 8, lambda n: 0, START)
    assert bool(fires(rows)) == expect


def test_R2_6_txf_ne_and_token_peek_does_not_pop():
    b = ImageBuilder()
    b.loc(0)
    b.edge(0, 1, dk=DG_TXF_NE)
    b.loc(1)
    b.edge(1, 2, dk=DG_TOKEN, k=7)                        # peek: no pop bit
    b.loc(2)
    b.edge(2, 3, dk=DG_TOKEN, k=7, act=Action(pop=1))
    idle_loc(b, 3)
    m = start(b.build())
    rows = run(m, 20, lambda n: 0, {0: HostOp("start"), 5: HostOp("push_tx", 0, 0x55),
                                    9: HostOp("push_token", 0, 7)})
    assert [f[0] for f in fires(rows)] == [6, 10, 12]
    assert m.s.engines[0].tok == [] and m.s.engines[0].tx == [0x55]


# ---------------------------------------------------------------- pins and datapath
def test_R2_9_pp_and_od_writes():
    b = ImageBuilder()
    b.loc(0)
    b.edge(0, 1, ck=CK_GE, win=(0, 2, 2), act=Action(wm=0b11, wv=0b01, mode=PP))
    b.loc(1)
    b.edge(1, 2, ck=CK_GE, win=(0, 4, 4), act=Action(wm=0b1100, wv=0b0100, mode=OD))
    idle_loc(b, 2)
    rows = run(start(b.build()), 10, lambda n: 0, START)
    assert (rows[3].out & 3, rows[3].oe & 3) == (0b01, 0b11)
    r = rows[5]
    assert (r.out & 0b1100, r.oe & 0b1100) == (0, 0b1000)  # pin3 pulled low, pin2 released


def uart_like(bit=4):
    """LSB-first shift-out of one TX byte on pin0, one bit every `bit` cycles (exact clock-triggered edges)."""
    b = ImageBuilder()
    IDLE, BIT, STOP = b.loc(0), b.loc(1), b.loc(2)
    b.edge(IDLE, BIT, dk=DG_TXF_NE, reset=X0, act=Action(wm=1, wv=0, op=OP_LOAD))
    b.edge(BIT, BIT, ck=CK_POLICY, win=(0, bit, bit, bit), dk=DG_BITCNT_LT, k=8, reset=X0,
           act=Action(wm=1, wv=0, op=OP_SHOUT, d=0))
    b.edge(BIT, STOP, ck=CK_POLICY, win=(0, bit, bit, bit), dk=DG_BITCNT_EQ, k=8, reset=X0,
           act=Action(wm=1, wv=1))
    b.edge(STOP, IDLE, ck=CK_POLICY, win=(0, bit, bit, bit))
    return b.build(msb_first=0)


def test_R2_10_shout_lsb_first_exact_bit_times():
    m = start(uart_like())
    rows = run(m, 60, lambda n: 0, {0: HostOp("start"), 1: HostOp("push_tx", 0, 0x41)})
    t0 = next(r.n for r in rows if r.oe & 1 and not r.out & 1)          # start bit appears
    bits = [rows[t0 + 4 * (k + 1)].out & 1 for k in range(9)]
    assert bits == [1, 0, 0, 0, 0, 0, 1, 0, 1]                            # 0x41 LSB first, then stop
    # every bit boundary exactly 4 cycles apart (R4.5)
    edges = [r.n for r in rows[t0 - 1:] if r.fired]
    assert all(b - a == 4 for a, b in zip(edges, edges[1:10]))


def test_R2_10_shin_msb_push_and_load_peek():
    b = ImageBuilder()
    S, D = b.loc(0), b.loc(1)
    b.edge(S, S, ck=CK_GE, win=(0, 2, 2), dk=DG_BITCNT_LT, k=8, reset=X0, act=Action(op=OP_SHIN, d=2))
    b.edge(S, D, dk=DG_BITCNT_EQ, k=8, act=Action(op=OP_PUSH))
    b.loc(D)
    b.edge(D, 2, act=Action(wm=0b10, op=OP_LOAD_PEEK, d=1))
    idle_loc(b, 2)
    pattern = [1, 0, 1, 1, 0, 0, 1, 0]                # 0xB2 MSB first, one sample every 2 cycles from cycle 2
    m = start(b.build(msb_first=1))
    m.s.engines[0].tx = [0x80]

    def pads(n):
        k = (n + 2 - 2) // 2                          # P_n = pad[n-2]
        return (pattern[k] << 2) if 0 <= k < 8 else 0
    rows = run(m, 30, pads, START)
    assert m.s.engines[0].rx == [0xB2]
    last = rows[-1]
    assert last.out & 0b10 and last.oe & 0b10        # SR[7] of the loaded 0x80 = 1


def test_R2_10_underflow_and_overflow_flags():
    b = ImageBuilder()
    b.loc(0)
    b.edge(0, 0, ck=CK_GE, win=(0, 2, 2), reset=X0, act=Action(op=OP_LOAD))
    m = start(b.build())
    run(m, 6, lambda n: 0, START)
    assert m.s.engines[0].flags & F_TX_UNDERFLOW and m.s.engines[0].sr == 0xFF
    b = ImageBuilder()
    b.loc(0)
    b.edge(0, 0, ck=CK_GE, win=(0, 2, 2), reset=X0, act=Action(op=OP_PUSH))
    m = Spex(1, Params(rx_depth=2))
    m.s.engines[0].image = b.build()
    run(m, 12, lambda n: 0, START)
    assert len(m.s.engines[0].rx) == 2 and m.s.engines[0].flags & F_RX_OVERFLOW


# ---------------------------------------------------------------- policies (§8)
@pytest.mark.parametrize("pol, t", [(Policy(POL_NOMINAL), 7), (Policy(POL_EARLIEST), 5), (Policy(POL_LATEST), 10),
                                    (Policy(POL_SWEEP, k=2, step=2), 9), (Policy(POL_SWEEP, k=9, step=2), 10)])
def test_R8_1_policy_times(pol, t):
    b = ImageBuilder()
    b.loc(0)
    b.edge(0, 1, ck=CK_POLICY, win=(0, 5, 10, 7))
    idle_loc(b, 1)
    m = start(b.build())
    m.s.engines[0].policy = pol
    assert fires(run(m, 15, lambda n: 0, START)) == [(t, 0, 0)]


def test_R8_2_random_reachable_and_bias_bounded():
    for lo, hi in ((0, 0), (3, 3), (0, 1), (5, 9), (100, 133), (0, 1000)):
        d = hi - lo
        m = (1 << d.bit_length()) - 1 if d else 0
        hist = collections.Counter(random_time(lo, hi, r) for r in range(m + 1))
        assert set(hist) == set(range(lo, hi + 1))
        assert max(hist.values()) <= 2 * min(hist.values())


def test_R8_2_random_policy_in_window_and_varies():
    b = ImageBuilder()
    b.loc(0)
    b.edge(0, 0, ck=CK_POLICY, win=(0, 4, 11, 4), reset=X0)
    m = start(b.build())
    m.s.engines[0].policy = Policy(POL_RANDOM)
    rows = run(m, 600, lambda n: 0, START)
    ts = [f.ts for r in rows for f in r.fired]
    assert all(4 <= t <= 11 for t in ts) and set(ts) == set(range(4, 12))


# ---------------------------------------------------------------- events (§10)
def test_R10_event_next_cycle_and_held_through_entry():
    e0 = ImageBuilder()
    e0.loc(0)
    e0.edge(0, 1, ck=CK_GE, win=(0, 10, 10), act=Action(emit=1, ev=3))
    idle_loc(e0, 1)
    e1 = ImageBuilder()
    e1.loc(0)
    e1.edge(0, 1, dk=DG_EVENT, k=3)
    idle_loc(e1, 1)
    for start_cycle, fire in ((0, 11), (9, 12)):     # e1 enters its location 0 in cycle 11 when started in 10
        m = Spex(2)
        m.s.engines[0].image = e0.build()
        m.s.engines[1].image = e1.build()
        host = {0: HostOp("start", 0), start_cycle + 1: HostOp("start", 1)}
        got = []
        for n in range(20):
            r = m.step(0, host.get(n))
            got += [n for f in r.fired if f.engine == 1]
        assert got == [fire]


# ---------------------------------------------------------------- engines and pins (R12.6)
def test_R12_6_pin_base_and_engine1_wins():
    b = ImageBuilder()
    b.loc(0)
    b.edge(0, 1, ck=CK_GE, win=(0, 2, 2), act=Action(wm=1, wv=1))
    idle_loc(b, 1)
    c = ImageBuilder()
    c.loc(0)
    c.edge(0, 1, ck=CK_GE, win=(0, 2, 2), act=Action(wm=1, wv=0))
    idle_loc(c, 1)
    m = Spex(2)
    m.s.engines[0].image = b.build(pin_base=3)
    m.s.engines[1].image = c.build(pin_base=3)
    m.step(0, HostOp("start", 0))
    m.step(0, HostOp("start", 1))
    m.run(5, 0)
    o = m.outputs()
    assert o.oe == 1 << 3 and o.out == 0                 # both drive chip pin 3; engine 1 (value 0) wins


# ---------------------------------------------------------------- host (R12)
def test_R12_start_stop_and_locked_tables():
    b = ImageBuilder()
    b.loc(0)
    b.edge(0, 1, ck=CK_GE, win=(0, 2, 2), act=Action(wm=1, wv=1))
    idle_loc(b, 1)
    img = b.build()
    m = start(img)
    m.step(0, HostOp("start"))
    assert m.s.engines[0].state == RUNNING and m.s.engines[0].x == [1, 1, 1]
    m.run(4, 0)
    assert m.outputs().oe == 1
    m.step(0, HostOp("load", 0, img))
    assert m.s.engines[0].flags & F_HOST_ERR
    m.step(0, HostOp("stop"))
    assert m.s.engines[0].state == STOPPED and m.outputs().oe == 0


def test_R12_1_unwritten_entry_raises():
    b = ImageBuilder()
    b.loc(0)
    b.edge(0, 5, ck=CK_GE, win=(0, 2, 2))             # location 5 never written
    with pytest.raises(UndefinedRead):
        run(start(b.build()), 6, lambda n: 0, START)


# ---------------------------------------------------------------- violations, resync, halt, error edges
def test_R6_5_resync_action_and_bitcnt_clear():
    b = ImageBuilder()
    b.loc(0, watch=1)
    b.edge(0, 0, pat=NEVER)
    idle_loc(b, 1)
    img = b.build(resync=1, resync_action=Action(wm=2, wv=2))
    m = start(img)
    m.s.engines[0].bitcnt = 5
    rows = run(m, 10, lambda n: 1 if n >= 3 else 0, START)
    v = [x for r in rows for x in r.viols]
    assert len(v) == 1 and v[0].cycle == 5
    assert rows[6].loc == 1 and rows[6].out & 2 and m.s.engines[0].bitcnt == 0 and m.s.engines[0].viol_count == 1


def test_R3_4_halt_and_R3_7_error_edge():
    b = ImageBuilder()
    b.loc(0)
    b.edge(0, 1, ck=CK_GE, win=(0, 3, 3), error=1, log=0)
    b.loc(1, halt=1)
    m = start(b.build())
    rows = run(m, 8, lambda n: 0, START)
    v = [x for r in rows for x in r.viols]
    assert fires(rows) == [(3, 0, 0)] and len(v) == 1 and v[0].kind == SPEC_ERROR and v[0].slot == 0
    assert m.s.engines[0].state == HALTED and m.s.engines[0].loc == 1


# ---------------------------------------------------------------- coverage (§9) and trace
def test_R9_coverage_word():
    b = ImageBuilder()
    b.loc(0)                                          # pin0 unwatched: its falls are dropped (R6.6)
    b.edge(0, 0, pat=(1, 1, EDGE), ck=CK_WIN, win=(0, 3, 100), reset=X0)
    b.loc(1)
    m = start(b.build(cover_en=1, cov_shift=1))
    pads = lambda n: 1 if n in range(8, 20) or n in range(30, 33) or n >= 35 else 0   # rises seen in 10, 32, 37
    run(m, 45, pads, START)
    w = m.s.cov[(0, 0)]
    # x0 at the hits: 10 (START in 0), 22 (reset at 10), 5 (reset at 32). offsets (ts - 3) >> 1 = 3, 9, 1
    assert (w >> 24, (w >> 12) & 0xFFF, w & 0xFFF) == (3, 1, 9)


def test_R6_4_trace_overflow_flag():
    b = ImageBuilder()
    b.loc(0)
    b.edge(0, 0, ck=CK_GE, win=(0, 2, 2), reset=X0)
    m = Spex(1, Params(trace_depth=3))
    m.s.engines[0].image = b.build()
    run(m, 20, lambda n: 0, START)
    assert len(m.s.trace) == 3 and m.s.engines[0].flags & F_TRACE_LOST


def test_R2_10_push_load_peek():
    """S38: push the received byte, load the next TX byte, drive its out-bit."""
    from spex.refsim import OP_PUSH_LOAD_PEEK
    b = ImageBuilder()
    b.loc(0)
    b.edge(0, 1, ck=CK_GE, win=(0, 3, 3), act=Action(wm=0b100, op=OP_PUSH_LOAD_PEEK, d=2))
    idle_loc(b, 1)
    m = start(b.build(msb_first=1))
    m.s.engines[0].sr, m.s.engines[0].tx, m.s.engines[0].bitcnt = 0x3C, [0x80, 0x01], 8
    rows = run(m, 8, lambda n: 0, START)
    e = m.s.engines[0]
    assert e.rx == [0x3C] and e.sr == 0x80 and e.tx == [0x01] and e.bitcnt == 0
    assert rows[-1].out & 0b100 and rows[-1].oe & 0b100


def test_R11_1_window_index_msb():
    """S42: windows 8..15 are reached through edge-word bit 2."""
    b = ImageBuilder()
    for i in range(9):
        b.loc(i)
        b.edge(i, i + 1, ck=CK_GE, win=(0, 2 + i, 2 + i), reset=X0)   # window i has lo = 2 + i
    idle_loc(b, 9)
    img = b.build()
    assert img.windows[8].lo == 10
    rows = run(start(img), 80, lambda n: 0, START)
    f = fires(rows)
    gaps = [b_[0] - a[0] for a, b_ in zip(f, f[1:])]
    assert gaps == [2 + i for i in range(1, 9)]                          # dwell = lo of the next window


def test_R2_10_inc_saturates():
    """S45: INC adds 1 to bitcnt, saturating at 63, and leaves SR alone."""
    from spex.refsim import OP_INC
    b = ImageBuilder()
    b.loc(0)
    b.edge(0, 0, ck=CK_GE, win=(0, 2, 2), reset=X0, act=Action(op=OP_INC))
    m = start(b.build())
    m.s.engines[0].sr, m.s.engines[0].bitcnt = 0x5A, 60
    run(m, 20, lambda n: 0, START)
    assert m.s.engines[0].bitcnt == 63 and m.s.engines[0].sr == 0x5A


def test_R11_3a_nominal_table():
    """S44: nominal times come from the nominal table slot of the window; slots 8..15 have none."""
    b = ImageBuilder()
    b.loc(0)
    for i in range(8):
        b._win((0, 100 + i, 200 + i, 150))          # fill slots 0..7 with other windows
    b.edge(0, 1, ck=CK_POLICY, win=(0, 5, 20, 9))   # window slot 8: no nominal time
    idle_loc(b, 1)
    img = b.build()
    img.noms = [None] * 8
    m = start(img)
    with pytest.raises(UndefinedRead):
        run(m, 6, lambda n: 0, START)
    b2 = ImageBuilder()
    b2.loc(0)
    b2.edge(0, 1, ck=CK_POLICY, win=(0, 5, 20, 9))
    idle_loc(b2, 1)
    assert fires(run(start(b2.build()), 15, lambda n: 0, START)) == [(9, 0, 0)]


def test_R9_single_port_queue():
    """S47: a covered engine firing every 2 cycles (its maximum, R3.5) never sets COV_LOST on the single-port
    coverage macro, and the queue never holds more than 1 update."""
    from spex.refsim.model import F_COV_LOST
    b = ImageBuilder()
    b.loc(0)
    b.edge(0, 0)                                     # no guard: fires in every first evaluation cycle
    m = start(b.build(cover_en=1))
    peak, hits = 0, []
    for n in range(400):
        hits += [n for f in m.step(0, HostOp("start") if n == 0 else None).fired]
        peak = max(peak, m.s.cov_q)
    assert all(b_ - a == 2 for a, b_ in zip(hits, hits[1:])) and len(hits) == 199     # the maximum rate
    assert m.s.cov[(0, 0)] >> 24 == 199
    assert not (m.s.flags & F_COV_LOST) and peak <= 1


def nec_leader():
    """SEMANTICS §1a worked example: 9 ms = 10 x 43,200 cycles at 48 MHz, counted with INC."""
    from spex.dsl import Op, Spec, bitcnt_eq, bitcnt_lt, txf_ne
    s = Spec("nec_leader", sides=["tx", "rx"], pins={"IR": 0}, clocks=["x"])
    IDLE = s.loc("IDLE", watch=["IR"])
    BURST = s.loc("BURST", watch=["IR"], invariant=s.window("x", 0, 64800))
    DONE = s.loc("DONE", halt=True)
    s.emit(IDLE, BURST, "tx", {"IR": 1}, data=txf_ne(), op=Op("CLR"), reset=["x"], label="burst on")
    s.internal(BURST, BURST, after=s.window("x", 43200, 43200), data=bitcnt_lt(9), op=Op("INC"), reset=["x"],
               label="loop")
    s.emit(BURST, DONE, "tx", {"IR": 0}, at=s.window("x", 21600, 64800, nom=43200), data=bitcnt_eq(9), reset=["x"],
           label="burst off")
    return s


def test_long_wait_nec_leader():
    """The exact cycles of SEMANTICS §1a, in Drive and in Check. Planted bug: 'INC adds 2' (mutants.py)."""
    from spex.compiler import compile_spec
    d = compile_spec(nec_leader(), "drive", side="tx")
    m = start(d.image)
    host = {3: HostOp("start"), 99: HostOp("push_tx", 0, 0)}     # the entering emit fires in cycle 100
    line, fired = [], []
    for n in range(432200):
        o = m.outputs()
        line.append(o.out & 1 if o.oe & 1 else 0)
        fired += [(n, f.loc, f.target) for f in m.step(line[-1], host.get(n)).fired]
    assert fired[0] == (100, 0, 1)
    assert [n for n, src, dst in fired if src == 1 and dst == 1] == [100 + 43200 * j for j in range(1, 10)]
    assert fired[-1] == (432100, 1, 2)
    rise = line.index(1)
    fall = line.index(0, rise)
    assert (rise, fall, fall - rise) == (101, 432101, 432000)            # 9.000 ms on the pad
    c = compile_spec(nec_leader(), "check")
    mc = start(c.image)
    cf, viols = [], []
    for n, p in enumerate(line):
        r = mc.step(p, HostOp("start") if n == 3 else None)
        cf += [(n, f.loc, f.target, f.ts) for f in r.fired]
        viols += r.violations
    assert viols == [] and cf[0][:3] == (103, 0, 1)
    assert cf[-1] == (432103, 1, 2, 43200)
