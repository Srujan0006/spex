"""spec/i2c.py in Drive (controller, target) and Check, judged by the UM10204 oracle tests/oracles/i2c.py.

Bus: wired-AND with pull-ups. Oracle agents see the line of the previous cycle; the chip sees the line through its
pads (pad[n] = line in cycle n), as the hardware does."""
import pytest

import i2c as oracle
from harness import START_CYCLE, HostOp, load, run_check
from spec.i2c import ACK, NACK, NEXT, SR, START, STOP, i2c, limits
from spex.compiler import compile_spec
from spex.refsim import TIMEOUT, UNEXPECTED

MEM = {0x10: 0x5A, 0x11: 0xC3}
WRITE = [("S",), ("W", 0xA0), ("W", 0x10), ("W", 0xA5), ("W", 0x3C), ("P",)]
READ = [("S",), ("W", 0xA0), ("W", 0x10), ("Sr",), ("W", 0xA1), ("R", True), ("R", False), ("P",)]
CACHE = {}


def comp(mode, role, side=None):
    key = (mode, role, side)
    if key not in CACHE:
        CACHE[key] = compile_spec(i2c(mode), role, side=side)
    return CACHE[key]


def budget(script, mode):
    return (5000 if mode == "standard" else 1400) * 9 * len(script) // 8 + 4000


def legal(script, mode="standard", stretch=0, **kw):
    c = oracle.Controller(script, mode, **kw)
    t = oracle.Target(0x50, MEM, stretch=stretch, **({} if "ack_data" not in kw else {}))
    return oracle.Bus(c, t).run(budget(script, mode)), c, t


def chip_pull(m):
    o = m.outputs()
    return o.oe & ~o.out & 3


def run_chip(compiled, agent, host, cycles):
    """Chip (Drive) plus one oracle agent on the bus. Returns (line waveform, chip model, violations)."""
    m = load(compiled)
    ops = dict(host)
    ops[START_CYCLE] = HostOp("start")
    line, w, viols = 3, [], []
    for n in range(cycles):
        pull = agent.step(n, line) | chip_pull(m)
        line = 3 & ~pull
        w.append(line)
        viols += m.step(line, ops.get(n)).violations
    return w, m, viols


def host_stream(tokens, tx, first=5):
    ops, n = {}, first
    for b in tx:
        ops[n] = HostOp("push_tx", 0, b)
        n += 1
    for k in tokens:
        ops[n] = HostOp("push_token", 0, k)
        n += 1
    return ops


# ---------------------------------------------------------------- Drive as controller
@pytest.mark.parametrize("mode", ["standard", "fast"])
@pytest.mark.parametrize("stretch", [0, 400])
def test_drive_controller_write(mode, stretch):
    tgt = oracle.Target(0x50, MEM, stretch=stretch)
    host = host_stream([START, NEXT, NEXT, NEXT, STOP], [0xA0, 0x10, 0xA5, 0x3C, 0x00])
    w, m, viols = run_chip(comp(mode, "drive", "ctl"), tgt, host, budget(WRITE, mode) + 4 * stretch)
    assert viols == []
    ev, errs = oracle.check(w, mode)
    assert errs == []
    assert oracle.transactions(ev) == [["S", (0xA0, True), (0x10, True), (0xA5, True), (0x3C, True), "P"]]
    assert tgt.written == [0xA5, 0x3C]
    assert m.s.engines[0].rx == [0xA0, 0x10, 0xA5, 0x3C]


@pytest.mark.parametrize("mode", ["standard", "fast"])
def test_drive_controller_read_with_repeated_start(mode):
    tgt = oracle.Target(0x50, MEM, stretch=100)
    host = host_stream([START, NEXT, SR, ACK, NACK, STOP], [0xA0, 0x10, 0xFF, 0xA1, 0x00])
    w, m, viols = run_chip(comp(mode, "drive", "ctl"), tgt, host, budget(READ, mode))
    assert viols == []
    ev, errs = oracle.check(w, mode)
    assert errs == []
    assert oracle.transactions(ev) == [["S", (0xA0, True), (0x10, True), "Sr", (0xA1, True), (0x5A, True),
                                        (0xC3, False), "P"]]
    assert m.s.engines[0].rx == [0xA0, 0x10, 0xA1, 0x5A, 0xC3]


def test_drive_controller_address_nack():
    tgt = oracle.Target(0x50, MEM)
    host = host_stream([START, STOP], [0xA2, 0x00])                     # address 0x51: nobody answers
    w, m, viols = run_chip(comp("fast", "drive", "ctl"), tgt, host, 6000)
    ev, errs = oracle.check(w, "fast")
    assert viols == [] and errs == []
    assert oracle.transactions(ev) == [["S", (0xA2, False), "P"]]


# ---------------------------------------------------------------- Drive as target
@pytest.mark.parametrize("mode", ["standard", "fast"])
def test_drive_target(mode):
    for script in (WRITE, READ):
        ctl = oracle.Controller(script, mode, lead=40)
        host = host_stream([], [0x5A, 0xC3])
        w, m, viols = run_chip(comp(mode, "drive", "tgt"), ctl, host, budget(script, mode))
        assert viols == []
        ev, errs = oracle.check(w, mode)
        assert errs == []
        if script is WRITE:
            assert ctl.acks == [True] * 4 and m.s.engines[0].rx == [0xA0, 0x10, 0xA5, 0x3C]
        else:
            assert ctl.acks == [True, True, True] and ctl.reads == [0x5A, 0xC3]


# ---------------------------------------------------------------- Check
@pytest.mark.parametrize("mode", ["standard", "fast"])
@pytest.mark.parametrize("stretch", [0, 300])
def test_check_accepts_legal(mode, stretch):
    for script, rx in ((WRITE, [0xA0, 0x10, 0xA5, 0x3C]), (READ, [0xA0, 0x10, 0xA1, 0x5A, 0xC3])):
        w, *_ = legal(script, mode, stretch)
        assert oracle.check(w, mode)[1] == []
        viols, m = run_check(comp(mode, "check"), w)
        assert viols == [] and m.s.engines[0].rx == rx


def test_check_accepts_address_nack_and_drive_traces():
    w, *_ = legal([("S",), ("W", 0xA2), ("P",)], "fast")
    assert run_check(comp("fast", "check"), w)[0] == []
    tgt = oracle.Target(0x50, MEM, stretch=50)
    host = host_stream([START, NEXT, SR, ACK, NACK, STOP], [0xA0, 0x10, 0xFF, 0xA1, 0x00])
    w, _, _ = run_chip(comp("fast", "drive", "ctl"), tgt, host, budget(READ, "fast"))
    assert run_check(comp("fast", "check"), w)[0] == []


def rises(w):
    return [n for n in range(1, len(w)) if w[n] & 1 and not w[n - 1] & 1]


def falls(w):
    return [n for n in range(1, len(w)) if not w[n] & 1 and w[n - 1] & 1]


T = limits("fast")


@pytest.mark.parametrize("fault", ["early SCL rise (tLOW)", "early SCL fall (tHIGH)", "late data (tVD)",
                                   "SDA glitch while SCL high", "missing ACK", "short bus-free time"])
def test_check_planted_fault(fault):
    mode = "fast"
    if fault == "late data (tVD)":
        w, *_ = legal(WRITE, mode, d=T["tVD"] + 10)
        f = falls(w)[0]
        ch = next(n for n in range(f + 1, len(w)) if (w[n] ^ w[n - 1]) & 2)
        expect = (UNEXPECTED, ch + 2)
    elif fault == "missing ACK":
        c = oracle.Controller(WRITE, mode)
        t = oracle.Target(0x50, MEM, ack_data=False)
        w = oracle.Bus(c, t).run(budget(WRITE, mode))
        f9 = falls(w)[2 * 9 - 1]                     # the fall that starts the first data byte's ACK slot
        expect = (TIMEOUT, f9 + 2 + T["tVD"] + 1)
    else:
        w, *_ = legal(WRITE, mode)
        w = list(w)
        if fault == "early SCL rise (tLOW)":
            r = rises(w)[3]
            for k in range(r - 30, r):
                w[k] |= 1
            expect = (UNEXPECTED, r - 30 + 2)
        elif fault == "early SCL fall (tHIGH)":
            f = falls(w)[4]
            for k in range(f - 15, f):
                w[k] &= ~1
            expect = (UNEXPECTED, f - 15 + 2)
        elif fault == "SDA glitch while SCL high":
            r = rises(w)[12]
            w[r + 10] ^= 2
            expect = (UNEXPECTED, r + 10 + 2)
        else:
            w2, *_ = legal([("S",), ("W", 0xA0), ("P",), ("S",), ("W", 0xA0), ("P",)], mode)
            ev, _ = oracle.check(w2, mode)
            p = [e[1] for e in ev if e[0] == "P"][0]
            s2 = [e[1] for e in ev if e[0] == "S"][1]
            w = w2[:p + 20] + w2[s2:]
            expect = (UNEXPECTED, p + 20 + 2)
    if fault == "missing ACK":                       # legal I2C (UM10204 allows NACK); illegal for this EEPROM spec
        ev, errs = oracle.check(w, mode)
        assert (0x10, False) in sum(oracle.transactions(ev), [])
    else:
        assert oracle.check(w, mode)[1], "the oracle must reject the fault too"
    viols, _ = run_check(comp(mode, "check"), w)
    assert viols, "not detected"
    assert (viols[0].kind, viols[0].cycle) == expect, viols[0]


def test_location_count_and_table_use():
    assert len(i2c("standard").locs) == 37
    for mode, windows in (("standard", 9), ("fast", 8)):                    # S42: 16 entries available
        c = comp(mode, "drive", "ctl")
        assert sum(w is not None for w in c.image.windows) == windows
        assert sum(k is not None for k in c.image.consts) == 8                  # at the R11 limit
