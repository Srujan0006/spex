"""The I2C oracle accepts traffic from the controller and target bus models and rejects each planted fault.
The Table 11 limits are checked against the source values once (test_table_values)."""
import pytest

import i2c

WRITE = [("S",), ("W", 0x50 << 1), ("W", 0x10), ("W", 0xA5), ("W", 0x3C), ("P",)]
READ = [("S",), ("W", 0x50 << 1), ("W", 0x10), ("Sr",), ("W", (0x50 << 1) | 1), ("R", True), ("R", False), ("P",)]


def bus(script, mode="standard", stretch=0, cycles=None, **kw):
    c = i2c.Controller(script, mode, **kw)
    t = i2c.Target(0x50, {0x10: 0x5A, 0x11: 0xC3}, stretch=stretch)
    w = i2c.Bus(c, t).run(cycles or 400 * 9 * len(script) * (4 if mode == "standard" else 1))
    return w, c, t


def test_table_values():
    s, f = i2c.cycles("standard"), i2c.cycles("fast")
    assert (s["tLOW"], s["tHIGH"], s["tHD_STA"], s["tSU_DAT"], s["tVD_max"]) == (226, 192, 192, 12, 165)
    assert (f["tLOW"], f["tHIGH"], f["tHD_STA"], f["tSU_DAT"], f["tVD_max"]) == (63, 29, 29, 5, 43)


@pytest.mark.parametrize("mode", ["standard", "fast"])
@pytest.mark.parametrize("stretch", [0, 300])
def test_legal_write_and_read(mode, stretch):
    w, c, t = bus(WRITE, mode, stretch)
    ev, errs = i2c.check(w, mode)
    assert errs == []
    assert i2c.transactions(ev) == [["S", (0xA0, True), (0x10, True), (0xA5, True), (0x3C, True), "P"]]
    assert t.written == [0xA5, 0x3C] and c.acks == [True] * 4
    w, c, t = bus(READ, mode, stretch)
    ev, errs = i2c.check(w, mode)
    assert errs == [] and c.reads == [0x5A, 0xC3]
    assert i2c.transactions(ev) == [["S", (0xA0, True), (0x10, True), "Sr", (0xA1, True), (0x5A, True),
                                     (0xC3, False), "P"]]


def test_nack_from_absent_target():
    w, c, _ = bus([("S",), ("W", 0x51 << 1), ("P",)])
    ev, errs = i2c.check(w, "standard")
    assert errs == [] and c.acks == [False]


def edges(w, pin, val):
    return [n for n in range(1, len(w)) if (w[n] >> pin) & 1 == val and (w[n - 1] >> pin) & 1 != val]


@pytest.mark.parametrize("fault, kind", [
    ("short tLOW", "tLOW"), ("short tHIGH", "tHIGH"), ("SDA glitch while SCL high", "inside a byte"),
    ("late data", "tVD"), ("short tBUF", "tBUF"), ("setup", "tSU;DAT")])
def test_planted_fault_rejected(fault, kind):
    if fault == "short tLOW":
        w, *_ = bus(WRITE, margin=4)
        w = list(w)
        r = edges(w, 0, 1)[3]
        for k in range(r - 60, r):
            w[k] |= 1                                 # SCL rises 60 cycles early
    elif fault == "short tHIGH":
        w, *_ = bus(WRITE)
        w = list(w)
        f = edges(w, 0, 0)[3]
        for k in range(f - 20, f):
            w[k] &= ~1
    elif fault == "SDA glitch while SCL high":
        w, *_ = bus(WRITE)
        w = list(w)
        r = edges(w, 0, 1)[2]
        w[r + 20] ^= 2
    elif fault == "late data":
        w, *_ = bus(WRITE, d=200)
    elif fault == "short tBUF":
        w, *_ = bus([("S",), ("W", 0xA0), ("P",), ("S",), ("W", 0xA0), ("P",)], margin=4)
        w = list(w)
        p = [e[1] for e in i2c.check(w, "standard")[0] if e[0] == "P"][0]
        s2 = [e[1] for e in i2c.check(w, "standard")[0] if e[0] == "S"][1]
        w = w[:p + 10] + w[s2:]                       # second START 10 cycles after STOP
    else:
        w, *_ = bus(WRITE)
        w = list(w)
        r = edges(w, 0, 1)[4]
        w[r - 3] ^= 2                                 # SDA flips 3 cycles before a rise
        for k in range(r - 3, r + 1):
            w[k] = (w[k] & ~2) | (w[r - 3] & 2)
    _, errs = i2c.check(w, "standard")
    assert any(kind in k for _, k in errs), errs
