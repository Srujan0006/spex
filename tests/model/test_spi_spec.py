"""spec/spi.py (target, modes 0-3) in Drive and Check, judged by the oracle tests/oracles/spi.py."""
import pytest

import spi as oracle
from harness import HostOp, run_check, run_drive
from spec.spi import spi
from spex.compiler import compile_spec
from spex.refsim import UNEXPECTED

H, TV, TSU, TH = 12, 6, 4, 4
MOSI_FRAMES = [[0xA5, 0x3C], [0x81]]
MISO_FRAMES = [[0x5A, 0xC3], [0x7E]]
MODES = range(4)


def compiled(mode, role):
    return compile_spec(spi(mode, H, TV), role, side="tgt" if role == "drive" else None)


def legal(mode, delay=3, **kw):
    w = oracle.gen_controller(mode, MOSI_FRAMES, H, lead=40, **kw)
    return oracle.add_target(w, mode, MISO_FRAMES, delay=delay)


def drive(mode, mosi_delay=0):
    ctl = oracle.gen_controller(mode, MOSI_FRAMES, H, lead=40, mosi_delay=mosi_delay)
    host = {5 + i: HostOp("push_tx", 0, b) for i, b in enumerate(sum(MISO_FRAMES, []))}

    def bus(o, n):
        c = ctl[n] if n < len(ctl) else ctl[-1]
        miso = (o.out >> 3) & 1 if (o.oe >> 3) & 1 else 1
        return (c & ~8) | (miso << 3)
    return run_drive(compiled(mode, "drive"), len(ctl), bus, host)


# ---------------------------------------------------------------- Drive (target)
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("mosi_delay", [0, 3])
def test_drive_target_accepted_by_oracle(mode, mosi_delay):
    pads, m, viols = drive(mode, mosi_delay)
    assert viols == []
    frames, errs = oracle.check(pads, mode, TSU, TH, H)
    assert errs == []
    assert frames == [(MOSI_FRAMES[0], MISO_FRAMES[0]), (MOSI_FRAMES[1], MISO_FRAMES[1])]
    assert m.s.engines[0].rx == sum(MOSI_FRAMES, [])


@pytest.mark.parametrize("mode", MODES)
def test_drive_trace_passes_check(mode):
    pads, _, _ = drive(mode)
    viols, m = run_check(compiled(mode, "check"), pads)
    assert viols == [] and m.s.engines[0].rx == sum(MOSI_FRAMES, [])


# ---------------------------------------------------------------- Check
@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("delay", [0, 3, TV - 1])
def test_check_accepts_legal(mode, delay):
    w = legal(mode, delay=delay)
    assert oracle.check(w, mode, TSU, TH, H)[1] == []
    viols, m = run_check(compiled(mode, "check"), w)
    assert viols == [] and m.s.engines[0].rx == sum(MOSI_FRAMES, [])


def cs_fall(w):
    return next(n for n in range(1, len(w)) if w[n - 1] & 1 and not w[n] & 1)


def first_change(w, pin, after):
    return next(n for n in range(after + 1, len(w)) if (w[n] ^ w[n - 1]) >> pin & 1)


def sample_edges(w, mode):
    cpol, cpha = mode >> 1, mode & 1
    return [u for u in range(1, len(w)) if not w[u] & 1 and ((w[u] ^ w[u - 1]) >> 1) & 1
            and ((((w[u] >> 1) & 1) != cpol) == (cpha == 0))]


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("fault", ["wrong mode", "early SCK edge", "MOSI setup glitch", "wrong bit count",
                                   "MISO late", "MOSI hold glitch"])
def test_check_planted_fault(mode, fault):
    if fault == "wrong mode":
        w = oracle.add_target(oracle.gen_controller(mode ^ 2, MOSI_FRAMES, H, lead=40), mode, MISO_FRAMES, 3)
        expect = cs_fall(w)
    elif fault == "early SCK edge":
        w = legal(mode, t_lead=H - 3)
        expect = first_change(w, 1, cs_fall(w))
    elif fault == "wrong bit count":
        w = oracle.add_target(oracle.gen_controller(mode, MOSI_FRAMES, H, lead=40, bits={0: 7}), mode,
                              MISO_FRAMES, 3)
        expect = first_change(w, 0, cs_fall(w))                     # CS rise after 7 bits
    elif fault == "MISO late":
        w = legal(mode, delay=TV + 4)                               # setup 2 < tSU: illegal for the oracle too
        expect = first_change(w, 3, cs_fall(w))
    else:
        w = legal(mode)
        s = sample_edges(w, mode)[2]
        g = s - 2 if fault == "MOSI setup glitch" else s + 2
        w[g] ^= 1 << oracle.MOSI
        w[g + 1] ^= 0                                               # one-cycle glitch
        expect = g
    assert oracle.check(w, mode, TSU, TH, H)[1], "the oracle must also reject the fault"
    viols, _ = run_check(compiled(mode, "check"), w)
    assert viols, "not detected"
    assert viols[0].kind == UNEXPECTED and viols[0].cycle == expect + 2, (viols[0], expect)


def test_location_counts():
    assert [len(spi(m).locs) for m in MODES] == [5, 6, 5, 6]
