"""The UART oracle accepts legal frames (with jitter inside the tolerance) and rejects each planted fault."""
import random

import pytest

import uart

T, TOL = 48, 4
DATA = [0x41, 0x00, 0xFF, 0xA5, 0x5A]


def flip(w, a, b):
    w = list(w)
    for i in range(a, b):
        w[i] ^= 1
    return w


def test_legal_frames_decode():
    w = uart.encode(DATA, T)
    assert uart.decode(w, T, TOL) == (DATA, [])


def test_legal_jitter_inside_tolerance():
    rnd = random.Random(1)
    offs = {(f, k): rnd.randint(-TOL, TOL) for f in range(5) for k in range(1, 11)}
    w = uart.encode(DATA, T, offset=lambda f, k: offs[f, k])
    assert uart.decode(w, T, TOL) == (DATA, [])


def frame_start(w):
    return next(i for i in range(1, len(w)) if w[i - 1] == 1 and w[i] == 0)


@pytest.mark.parametrize("fault, kind", [
    ("glitch", "transition off the bit grid"),
    ("early edge", "transition off the bit grid"),
    ("framing", "framing error"),
    ("false start", "false start"),
    ("short stop", "stop bit too short"),
])
def test_planted_fault_rejected(fault, kind):
    if fault == "early edge":                         # boundary 1 of 0x41 (bit0 = 1) moved TOL+1 early
        w = uart.encode([0x41], T, offset=lambda f, k: -(TOL + 1) if k == 1 else 0)
    elif fault == "short stop":
        w = uart.encode([0x41, 0x41], T, offset=lambda f, k: -(TOL + 2) if (f, k) == (0, 10) else 0)
    else:
        w = uart.encode([0x41], T)
        t0 = frame_start(w)
        if fault == "glitch":
            w = flip(w, t0 + 3 * T + T // 2, t0 + 3 * T + T // 2 + 1)
        elif fault == "framing":
            w = flip(w, t0 + 9 * T, t0 + 10 * T)
        elif fault == "false start":
            w = flip(w, t0 + T // 4, t0 + T)
    _, errs = uart.decode(w, T, TOL)
    assert any(k == kind for _, k in errs), errs
