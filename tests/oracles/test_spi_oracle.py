"""The SPI oracle decodes legal traffic in all 4 modes and rejects each planted fault."""
import pytest

import spi

H, TSU, TH = 12, 4, 4
FRAMES = [[0xA5, 0x3C], [0x81]]
MISO_FRAMES = [[0x5A, 0xC3], [0x7E]]


def legal(mode, **kw):
    w = spi.gen_controller(mode, FRAMES, H, **kw)
    return spi.add_target(w, mode, MISO_FRAMES, delay=3)


@pytest.mark.parametrize("mode", range(4))
def test_legal_all_modes(mode):
    frames, errs = spi.check(legal(mode), mode, TSU, TH, H)
    assert errs == []
    assert frames == [(FRAMES[0], MISO_FRAMES[0]), (FRAMES[1], MISO_FRAMES[1])]


def first_sample(w, mode):
    cpol, cpha = mode >> 1, mode & 1
    for u in range(1, len(w)):
        s0, s1 = (w[u - 1] >> 1) & 1, (w[u] >> 1) & 1
        if s0 != s1 and ((s1 != cpol) == (cpha == 0)) and not (w[u] & 1):
            return u


@pytest.mark.parametrize("mode", range(4))
@pytest.mark.parametrize("fault, kind", [
    ("wrong mode", "SCK not idle at CS fall"),
    ("short half period", "SCK half period too short"),
    ("MOSI glitch at sample", "MOSI setup/hold"),
    ("MISO late", "MISO setup/hold"),
    ("7 bits", "not a multiple of 8"),
])
def test_planted_fault_rejected(mode, fault, kind):
    if fault == "wrong mode":
        w = legal(mode ^ 2)
    elif fault == "short half period":
        w = spi.add_target(spi.gen_controller(mode, FRAMES, H - 4), mode, MISO_FRAMES, delay=3)
    elif fault == "7 bits":
        w = spi.add_target(spi.gen_controller(mode, FRAMES, H, bits={1: 7}), mode, MISO_FRAMES, delay=3)
    elif fault == "MISO late":
        w = spi.add_target(spi.gen_controller(mode, FRAMES, H), mode, MISO_FRAMES, delay=H - 1)
    else:
        w = legal(mode)
        s = first_sample(w, mode)
        w[s - 1] ^= 1 << spi.MOSI
    _, errs = spi.check(w, mode, TSU, TH, H)
    assert any(kind in k for _, k in errs), errs
