"""Run compiled specs on the reference model against waveforms or bus models (step 4 tests)."""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

from spex.refsim import HostOp, Outputs, Policy, Spex

START_CYCLE = 3          # SEMANTICS R12.7: engines start once the synchroniser has settled


def load(compiled, engine: int = 0, m: Optional[Spex] = None) -> Spex:
    m = m or Spex(1)
    m.s.engines[engine].image = compiled.image
    return m


def run_check(compiled, wave: List[int], start: int = START_CYCLE):
    """Feed pad values wave[n] in cycle n to a Check engine. Returns (violations, model)."""
    m = load(compiled)
    viols = []
    for n, p in enumerate(wave):
        viols += m.step(p, HostOp("start") if n == start else None).violations
    return viols, m


def run_drive(compiled, cycles: int, bus: Callable[[Outputs, int], int], host: Optional[Dict[int, HostOp]] = None,
              policy: Policy = Policy(), seed: Optional[int] = None, start: int = START_CYCLE):
    """Drive engine closed through a bus model: pads[n] = bus(outputs in cycle n, n).
    Host ops: start, policy, optional seed, then `host` (cycle -> op; must avoid cycles 0..start).
    Returns (pads, model, violations)."""
    m = load(compiled)
    ops = {0: HostOp("policy", 0, policy), start: HostOp("start")}
    if seed is not None:
        ops[1] = HostOp("seed", 0, seed)
    for k, v in (host or {}).items():
        assert k not in ops, k
        ops[k] = v
    pads, viols = [], []
    for n in range(cycles):
        p = bus(m.outputs(), n)
        pads.append(p)
        viols += m.step(p, ops.get(n)).violations
    return pads, m, viols


def bit(v: int, i: int) -> int:
    return (v >> i) & 1
