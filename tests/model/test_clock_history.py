"""Clock history registers (spex/refsim/clock_history.py) equal R2.5's v = max(x - a, 0) for every age, including
saturation (owner, 2026-10-22).

Mutants that must make this file fail (tests/model/mutants.py): 'history keeps counting at saturation',
'reset history ignores the age'."""
import random

import pytest

from spex.refsim import XMAX, HostOp
from spex.refsim.clock_history import history_next, select

EVENTS = ["count", ("reset", 0), ("reset", 1), ("reset", 2)]


def _ok(x, d1, d2):
    return d1 == max(x - 1, 0) and d2 == max(x - 2, 0)


def test_invariant_is_inductive_for_every_clock_value():
    """For every x in 0..XMAX with a consistent history, every event keeps the invariant, and select() is R2.5's v."""
    for x in range(XMAX + 1):
        d1, d2 = max(x - 1, 0), max(x - 2, 0)
        for a in range(3):
            assert select(x, d1, d2, a) == max(x - a, 0)
        for ev in EVENTS:
            nx = history_next(x, d1, d2, ev)
            assert _ok(*nx), (x, ev, nx)
    assert history_next(5, 4, 3, "zero") == (0, 0, 0)


@pytest.mark.parametrize("seed", range(3))
def test_random_sequences_near_saturation(seed):
    rng = random.Random(seed)
    x, d1, d2 = XMAX - 5, XMAX - 6, XMAX - 7
    for _ in range(2000):
        ev = "count" if rng.random() < 0.9 else ("reset", rng.randrange(3))
        if rng.random() < 0.002:
            ev = "zero"
        x, d1, d2 = history_next(x, d1, d2, ev)
        assert _ok(x, d1, d2)
        for a in range(3):
            assert select(x, d1, d2, a) == max(x - a, 0)
        if rng.random() < 0.01:
            x, d1, d2 = XMAX - rng.randrange(4), 0, 0       # jump near XMAX, then rebuild a consistent history
            d1, d2 = max(x - 1, 0), max(x - 2, 0)


def _event_from_model(x, nx):
    """The event that took a clock from x to nx in the model. A reset that lands on min(x + 1, XMAX) is read as a
    count; that is harmless because both give the same history (a = x: (1 + a, a, max(a - 1, 0)))."""
    if nx == min(x + 1, XMAX):
        return "count"
    if nx == 0:
        return "zero"
    assert 1 <= nx <= 3, (x, nx)
    return ("reset", nx - 1)


@pytest.mark.parametrize("spec", ["uart", "i2c"])
def test_history_tracks_the_model_on_random_traffic(spec):
    """Check-role engines on random pin traffic (violations, resyncs and pin-triggered resets of every age): every
    clock of every cycle, shadowed by the history registers, keeps the invariant."""
    from spec.i2c import i2c
    from spec.uart_8n1 import uart_8n1
    from spex.compiler import compile_spec
    from spex.refsim import Spex
    c = compile_spec(uart_8n1(8, 1) if spec == "uart" else i2c("fast"), "check")
    m = Spex(1)
    m.s.engines[0].image = c.image
    rng = random.Random(1)
    hist = [(0, 0, 0)] * 3
    ages = set()
    pads = 0xFF
    for n in range(6000):
        if rng.random() < 0.08:
            pads ^= 1 << rng.randrange(2)
        before = list(m.s.engines[0].x)
        m.step(pads, HostOp("start") if n == 3 else None)
        after = m.s.engines[0].x
        for k in range(3):
            ev = _event_from_model(before[k], after[k])
            if isinstance(ev, tuple):
                ages.add(ev[1])
            hist[k] = history_next(*hist[k], ev)
            assert hist[k][0] == after[k] and _ok(*hist[k]), (n, k, before[k], after[k], hist[k])
    # the traffic reached resets of every age (I2C Check sees no carried-over reset on it; UART covers age 2)
    assert ages >= ({0, 1, 2} if spec == "uart" else {0, 1}), ages
