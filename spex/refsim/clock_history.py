"""Clock history registers: an implementation of R2.5's trigger-instant value without a subtractor (owner, 2026-10-22).

R2.5 defines `v = max(x_c - a, 0)` for an edge with trigger age a in 0..2. The RTL keeps, per clock, two registers
`x_d1` and `x_d2` with the invariant

    x_d1 = max(x - 1, 0)        x_d2 = max(x - 2, 0)        in every cycle (S_n),

so `v` is a 3:1 select by age: a = 0 -> x, a = 1 -> x_d1, a = 2 -> x_d2. No rule changes; this module is the
reference for the RTL update below, and tests/model/test_clock_history.py checks the invariant exhaustively and on
model runs. Events of one clock in one cycle (R1.2-R1.6, R3.7, R6.5, R12.3-R12.4):
  - "count": x' = min(x + 1, XMAX)  (every cycle the clock is not reset; it saturates, R1.4)
  - ("reset", a): x' = 1 + a        (a firing edge's reset, R1.6; start and resync are a = 0: x' = 1)
  - "zero": x' = 0                  (rst_n, R12.3)
"""
from __future__ import annotations

from typing import Tuple, Union

from .tables import XMAX

Event = Union[str, Tuple[str, int]]


def history_next(x: int, d1: int, d2: int, ev: Event) -> Tuple[int, int, int]:
    """One cycle of (x, x_d1, x_d2), as the RTL computes it from S_n."""
    if ev == "zero":
        return 0, 0, 0
    if ev == "count":
        if x == XMAX:                       # saturated: x stays, its history stays XMAX-1, XMAX-2
            return XMAX, XMAX - 1, XMAX - 2
        return x + 1, x, d1
    kind, a = ev
    assert kind == "reset" and 0 <= a <= 2
    return 1 + a, a, max(a - 1, 0)        # x was 0 at the trigger instant, a cycles ago


def select(x: int, d1: int, d2: int, age: int) -> int:
    """The RTL's v: no subtraction."""
    return (x, d1, d2)[age]
