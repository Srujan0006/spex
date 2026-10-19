"""SEMANTICS v1 §13: every worked example, with the exact cycle numbers of the document.

Mutants that must make this file fail are listed in tests/model/mutants.py (tag "examples")."""
import pytest

from imgb import START, ImageBuilder, run, start
from spex.refsim import (CK_GE, CK_POLICY, CK_WIN, DG_TOKEN, EDGE, ENTRY, EVAL, HALTED, OD, PP, TIMEOUT,
                         UNEXPECTED, Action, HostOp)

PIN0, PIN1 = 1, 2
X0 = 1                      # reset mask bit for x0


def fired_at(rows):
    return {r.n: f for r in rows for f in r.fired}


def viols_at(rows):
    return {r.n: v for r in rows for v in r.viols}


# ---------------------------------------------------------------- 13.1 example (a)
def build_a():
    """PRE fires in cycle 10 (x0 >= 10 since START in cycle 0) and resets x0; A reacts to pin0 rising."""
    b = ImageBuilder()
    PRE, A, B = b.loc(0), b.loc(1, watch=PIN0), b.loc(2)
    b.edge(PRE, A, ck=CK_GE, win=(0, 10, 10), reset=X0)
    b.edge(A, B, pat=(PIN0, PIN0, EDGE), act=Action(wm=PIN1, wv=PIN1, mode=PP))
    b.edge(B, B, pat=(0x80, 0x80, EDGE))          # never fires
    return b.build()


@pytest.mark.parametrize("pad_cycle, fire, entry_of_A_change, age, ts, out_cycle, latency", [
    (20, 22, False, 0, 12, 23, 3),     # a1: L = 3
    (9, 12, True, 1, 1, 13, 4),        # a2: L + E = 4
    (8, 12, False, 2, 0, 13, 5),       # a3: carried over, L + 2 = 5 (S35)
])
def test_example_a(pad_cycle, fire, entry_of_A_change, age, ts, out_cycle, latency):
    m = start(build_a())
    rows = run(m, 30, lambda n: PIN0 if n >= pad_cycle else 0, START)
    f = fired_at(rows)
    assert f[10].loc == 0 and f[10].target == 1
    assert rows[11].phase == ENTRY and rows[11].x[0] == 1
    assert rows[12].phase == EVAL and rows[12].first and rows[12].x[0] == 2
    a_fire = [n for n, x in f.items() if x.loc == 1]
    assert a_fire == [fire]
    assert f[fire].age == age and f[fire].ts == ts and f[fire].tau == fire - age
    assert all(not (r.out & PIN1) for r in rows[:out_cycle])
    assert rows[out_cycle].out & PIN1 and rows[out_cycle].oe & PIN1
    assert out_cycle - pad_cycle == latency
    assert not viols_at(rows)


def test_example_a1_table_rows():
    m = start(build_a())
    rows = run(m, 24, lambda n: PIN0 if n >= 20 else 0, START)
    assert [(r.n, r.P & PIN0, r.x[0]) for r in rows[20:24]] == [(20, 0, 10), (21, 0, 11), (22, 1, 12), (23, 1, 13)]
    assert rows[23].phase == ENTRY and rows[23].loc == 2


# ---------------------------------------------------------------- 13.2 example (b)
SCL, SDA = PIN0, PIN1


def build_b(variant):
    b = ImageBuilder()
    INIT, H, L, M = b.loc(0), b.loc(1, watch=SCL | SDA), None, b.loc(3)
    b.edge(INIT, H, ck=CK_GE, win=(0, 20, 20))
    if variant == "L1":
        L = b.loc(2, watch=SCL)
        b.edge(H, L, pat=(SCL, 0, EDGE), reset=X0)
        b.edge(L, M, pat=(SCL, SCL, EDGE))
    elif variant == "L2":
        L = b.loc(2, watch=SCL | SDA)
        b.edge(H, L, pat=(SCL, 0, EDGE), reset=X0)
        b.edge(L, M, pat=(SDA, SDA, EDGE), ck=CK_WIN, win=(0, 0, 10))
    else:
        L = b.loc(2, watch=SCL | SDA)
        b.edge(H, L, pat=(SCL, 0, EDGE), reset=X0)
        b.edge(L, M, pat=(SCL, SCL, EDGE))
    b.edge(M, M, pat=(0x80, 0x80, EDGE))
    return b.build()


def pads_b(n):
    return SDA if n >= 30 else SCL           # SCL falls and SDA rises in pad cycle 30


@pytest.mark.parametrize("variant", ["L1", "L2", "L3"])
def test_example_b(variant):
    m = start(build_b(variant))
    rows = run(m, 40, pads_b, START)
    f, v = fired_at(rows), viols_at(rows)
    h = f[32]
    assert h.loc == 1 and h.age == 0 and h.tau == 32
    assert rows[33].phase == ENTRY and rows[33].loc == 2 and rows[33].x[0] == 1
    assert rows[34].x[0] == 2 and rows[34].first
    if variant == "L1":
        assert 34 not in f and not v
    elif variant == "L2":
        assert f[34].loc == 2 and f[34].age == 2 and f[34].ts == 0 and f[34].tau == 32
        rec = [t for t in m.s.trace if t.loc == 2][0]
        assert (rec.cycle, rec.ts, rec.pins) == (32, 0, SDA)
        assert not v
    else:
        assert v[34].kind == UNEXPECTED and v[34].cycle == 32 and v[34].pins == SDA and v[34].loc == 2


def test_example_b_carry_register():
    m = start(build_b("L1"))
    rows = run(m, 34, pads_b, START)
    assert m.s.engines[0].pend2 == SDA and m.s.engines[0].phase == EVAL and rows[33].phase == ENTRY


# ---------------------------------------------------------------- 13.3 example (c)
RX = PIN0
W1 = (0, 5, 10)


def build_c(reset_into_w=True):
    b = ImageBuilder()
    INIT, W, D, I, MID = b.loc(0), b.loc(1, watch=RX, inv=W1), b.loc(2), b.loc(3), b.loc(4)
    if reset_into_w:
        b.edge(INIT, W, ck=CK_GE, win=(0, 100, 100), reset=X0)
    else:                                     # c6: x0 reset in 191, W entered in 200 without a reset
        b.edge(INIT, MID, ck=CK_GE, win=(0, 191, 191), reset=X0)
        b.edge(MID, W, ck=CK_GE, win=(1, 200, 200))
    b.edge(W, D, pat=(RX, 0, EDGE), ck=CK_WIN, win=W1)
    b.edge(D, D, pat=(0x80, 0x80, EDGE))
    b.edge(I, I, pat=(0x80, 0x80, EDGE))
    return b.build(resync=3)


def rx_falls(c):
    return lambda n: 0 if (c is not None and n >= c) else RX


@pytest.mark.parametrize("case, fall, cyc, x0, result", [
    ("c1", 105, 107, 7, "fire"),
    ("c5", 108, 110, 10, "fire"),
    ("c2", 101, 103, 3, UNEXPECTED),
    ("c3", None, 111, 11, TIMEOUT),
    ("c4", 109, 111, 11, UNEXPECTED | TIMEOUT),
])
def test_example_c(case, fall, cyc, x0, result):
    m = start(build_c())
    rows = run(m, 130, rx_falls(fall), START)
    f, v = fired_at(rows), viols_at(rows)
    assert f[100].target == 1 and rows[101].x[0] == 1
    assert rows[cyc].x[0] == x0
    w_fires = {n: x for n, x in f.items() if x.loc == 1}
    if result == "fire":
        assert list(w_fires) == [cyc] and w_fires[cyc].ts == x0 and not v
    else:
        assert not w_fires and list(v) == [cyc]
        assert v[cyc].kind == result and v[cyc].cycle == cyc and v[cyc].loc == 1
        if result & UNEXPECTED:
            assert v[cyc].pins == RX
        if result == TIMEOUT:
            assert v[cyc].ts == 11
        assert rows[cyc + 1].loc == 3 and rows[cyc + 1].phase == ENTRY and rows[cyc + 1].x[0] == 1


def test_example_c6_trigger_instant():
    m = start(build_c(reset_into_w=False))
    rows = run(m, 230, rx_falls(199), START)
    f, v = fired_at(rows), viols_at(rows)
    assert f[200].loc == 4 and rows[200].x[0] == 9 and rows[201].x[0] == 10 and rows[202].x[0] == 11
    assert f[202].loc == 1 and f[202].age == 1 and f[202].ts == 10
    assert not v


# ---------------------------------------------------------------- 13.4 example (d)
WS = (0, 20, 30, 25)
WN = (0, 20, 30, 25)
WI = (0, 0, 30)


def build_d_drive():
    b = ImageBuilder()
    INIT, INIT2, HI, P_DONE, LOW = b.loc(0), b.loc(1), b.loc(2, inv=WI), b.loc(3), b.loc(4)
    b.edge(INIT, INIT2, ck=CK_GE, win=(0, 190, 190), act=Action(wm=SCL | SDA, wv=0, mode=OD))
    b.edge(INIT2, HI, ck=CK_GE, win=(0, 200, 200), reset=X0, act=Action(wm=SCL, wv=SCL, mode=OD))
    b.edge(HI, P_DONE, ck=CK_POLICY, win=WS, dk=DG_TOKEN, k=1, act=Action(wm=SDA, wv=SDA, mode=OD, pop=1))
    b.edge(HI, LOW, ck=CK_POLICY, win=WN, dk=DG_TOKEN, k=2, act=Action(wm=SCL, wv=0, mode=OD, pop=1))
    b.edge(P_DONE, P_DONE, pat=(0x80, 0x80, EDGE))
    b.edge(LOW, LOW, pat=(0x80, 0x80, EDGE))
    return b.build()


def build_d_check():
    b = ImageBuilder()
    C0, CLOW, CHI, P_DONE, LOW = b.loc(0), b.loc(1), b.loc(2, watch=SCL | SDA, inv=WI), b.loc(3), b.loc(4)
    b.edge(C0, CLOW, pat=(SCL | SDA, 0, EDGE))
    b.edge(CLOW, CHI, pat=(SCL, SCL, EDGE), reset=X0)
    b.edge(CHI, P_DONE, pat=(SCL | SDA, SCL | SDA, EDGE), ck=CK_WIN, win=WS)
    b.edge(CHI, LOW, pat=(SCL, 0, EDGE), ck=CK_WIN, win=WN)
    b.edge(P_DONE, P_DONE, pat=(0x80, 0x80, EDGE))
    b.edge(LOW, LOW, pat=(0x80, 0x80, EDGE))
    return b.build(drive_en=0)


def line(o):
    """Wired-AND bus with pull-ups (I2C): a pin is low iff some driver enables it with value 0."""
    return ~(o.oe & ~o.out) & 0xFF


def run_drive(tokens):
    m = start(build_d_drive())
    host = dict(START)
    for i, t in enumerate(tokens):
        host[1 + i] = HostOp("push_token", 0, t)
    lines, rows = [], []
    for n in range(260):
        e = m.s.engines[0]
        o = m.outputs()
        ln = line(o)
        lines.append(ln)
        r = m.step(ln, host.get(n))
        rows.append((n, e.phase, e.loc, e.x[0], r.fired, r.violations, list(e.t_e)))
    return m, lines, rows


def test_example_d_drive_stop():
    m, lines, rows = run_drive([1])
    fires = {r[0]: f for r in rows for f in r[4]}
    assert fires[190].target == 1 and fires[200].target == 2
    assert rows[201][1] == ENTRY and rows[201][3] == 1
    assert rows[202][6][:2] == [25, 25]                  # t_0 = t_1 = 25 latched in the entry cycle
    assert [n for n, f in fires.items() if f.loc == 2] == [225]
    assert fires[225].slot == 0 and fires[225].target == 3
    assert lines[225] & SDA == 0 and lines[226] & SDA          # SDA line rises in pad cycle 226
    assert lines[200] & SCL == 0 and lines[201] & SCL          # SCL released in 200, high from 201
    assert m.s.engines[0].tok == []
    assert not any(r[5] for r in rows)


def test_example_d_drive_starved_token():
    _, _, rows = run_drive([])
    v = {r[0]: x for r in rows for x in r[5]}
    assert list(v) == [231] and v[231].kind == TIMEOUT and v[231].loc == 2 and v[231].ts == 31
    m, _, _ = run_drive([])
    assert m.s.engines[0].state == HALTED                    # no resync declared (R6.5)


def test_example_d_check_accepts_drive_trace():
    _, lines, _ = run_drive([1])
    m = start(build_d_check())
    rows = run(m, 260, lambda n: lines[n], START)
    f, v = fired_at(rows), viols_at(rows)
    assert f[203].loc == 1 and f[203].target == 2 and f[203].age == 0
    assert [n for n, x in f.items() if x.loc == 2] == [228]
    assert f[228].slot == 0 and f[228].ts == 25
    assert not v
    assert all(r.oe == 0 for r in rows)                       # Check never drives
