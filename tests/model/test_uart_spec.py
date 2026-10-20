"""spec/uart_8n1.py in Drive and Check, judged by the standards-derived oracle tests/oracles/uart.py.

Drive: the oracle decodes the chip's TX line. Check: oracle-generated legal waveforms give zero violations;
each planted fault gives the right violation kind at the right cycle (pad cycle t is seen in pin-bus cycle t + 2)."""
import random

import pytest

import uart as oracle
from harness import HostOp, run_check, run_drive
from spec.uart_8n1 import uart_8n1
from spex.compiler import compile_spec
from spex.refsim import POL_EARLIEST, POL_LATEST, POL_NOMINAL, POL_RANDOM, POL_SWEEP, TIMEOUT, UNEXPECTED, Policy

T, D = 48, 4
DATA = [0x41, 0x00, 0xFF, 0x55, 0xA5, 0x80]
SPEC = uart_8n1(T, D)
CHECK = compile_spec(SPEC, "check")
DRIVE = compile_spec(SPEC, "drive", side="tx")


def tx_line(o, n):
    return (o.out & 1) if o.oe & 1 else 1


def drive(data, policy=Policy(), seed=None, cycles=None):
    host = {5 + i: HostOp("push_tx", 0, b) for i, b in enumerate(data)}
    pads, m, viols = run_drive(DRIVE, cycles or 12 * T * (len(data) + 1), tx_line, host, policy, seed)
    return pads, m, viols


# ---------------------------------------------------------------- Drive
@pytest.mark.parametrize("policy", [Policy(POL_NOMINAL), Policy(POL_EARLIEST), Policy(POL_LATEST),
                                    Policy(POL_SWEEP, 3, 1)])
def test_drive_accepted_by_oracle(policy):
    data = DATA[:4]                                     # TX FIFO depth is 8; 4 bytes back to back
    pads, m, viols = drive(data, policy)
    assert viols == []
    assert oracle.decode(pads, T, D) == (data, [])


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_drive_random_policy_accepted_by_oracle(seed):
    pads, m, viols = drive(DATA, Policy(POL_RANDOM), seed=seed)
    assert viols == [] and oracle.decode(pads, T, D) == (DATA, [])


def test_drive_oracle_rejects_too_wide_a_spec():
    """Teeth: a spec with tolerance 2d driven at its latest edges fails the oracle at tolerance d."""
    wide = compile_spec(uart_8n1(T, 2 * D + 2), "drive", side="tx")
    host = {5: HostOp("push_tx", 0, 0x55)}
    pads, _, _ = run_drive(wide, 12 * T, tx_line, host, Policy(POL_LATEST))
    _, errs = oracle.decode(pads, T, D)
    assert errs


# ---------------------------------------------------------------- Check, legal traffic
def test_check_accepts_legal_frames():
    w = oracle.encode(DATA, T)
    viols, m = run_check(CHECK, w)
    assert viols == [] and m.s.engines[0].rx == DATA


@pytest.mark.parametrize("seed", range(5))
def test_check_accepts_legal_jitter(seed):
    rnd = random.Random(seed)
    offs = {(f, k): rnd.randint(-D, D) for f in range(len(DATA)) for k in range(1, 11)}
    w = oracle.encode(DATA, T, offset=lambda f, k: offs[f, k])
    assert oracle.decode(w, T, D) == (DATA, [])         # legal by the oracle
    viols, m = run_check(CHECK, w)
    assert viols == [] and m.s.engines[0].rx == DATA


def test_check_accepts_drive_trace():
    pads, _, _ = drive(DATA, Policy(POL_RANDOM), seed=7)
    viols, m = run_check(CHECK, pads)
    assert viols == [] and m.s.engines[0].rx == DATA


# ---------------------------------------------------------------- Check, planted faults
def start_of(w):
    return next(i for i in range(1, len(w)) if w[i - 1] == 1 and w[i] == 0)


def single(viols):
    assert viols, "fault not detected"
    return viols[0]


def test_fault_glitch_on_watched_pin():
    w = oracle.encode([0x41], T)
    t0 = start_of(w)
    g = t0 + 3 * T + T // 2
    w[g] ^= 1
    assert oracle.decode(w, T, D)[1]                     # the oracle agrees it is illegal
    v = single(run_check(CHECK, w)[0])
    assert v.kind == UNEXPECTED and v.cycle == g + 2


@pytest.mark.parametrize("shift, name", [(-(D + 3), "early edge"), (D + 3, "late edge")])
def test_fault_edge_outside_window(shift, name):
    w = oracle.encode([0x55], T, offset=lambda f, k: shift if k == 4 else 0)
    t0 = start_of(w)
    edge = t0 + 4 * T + shift
    assert w[edge] != w[edge - 1] and oracle.decode(w, T, D)[1]
    v = single(run_check(CHECK, w)[0])
    assert v.kind == UNEXPECTED and v.cycle == edge + 2


def test_fault_wrong_bit_count_stop_bit_missing():
    """A ninth data bit (0) where the stop bit belongs: OPEN_S never sees the line high -> TIMEOUT."""
    w = oracle.encode([0x41], T)
    t0 = start_of(w)
    for i in range(t0 + 9 * T, t0 + 10 * T):
        w[i] = 0
    assert any(k == "framing error" for _, k in oracle.decode(w, T, D)[1])
    v = single(run_check(CHECK, w)[0])
    assert v.kind == TIMEOUT and v.cycle == t0 + 9 * T + D + 3


def test_fault_false_start():
    w = oracle.encode([0x41], T)
    t0 = start_of(w)
    for i in range(t0 + T // 2, t0 + T):
        w[i] = 1
    v = single(run_check(CHECK, w)[0])
    assert v.kind == UNEXPECTED and v.cycle == t0 + T // 2 + 2


def test_fault_short_stop_bit():
    w = oracle.encode([0x41, 0x41], T, offset=lambda f, k: -(D + 3) if (f, k) == (0, 10) else 0)
    s1 = start_of(w) + 10 * T - (D + 3)                  # second frame's start edge
    assert w[s1 - 1] == 1 and w[s1] == 0
    assert any(k == "stop bit too short" for _, k in oracle.decode(w, T, D)[1])
    v = single(run_check(CHECK, w)[0])
    assert v.kind == UNEXPECTED and v.cycle == s1 + 2


def test_known_limit_short_stop_within_2_cycles_is_accepted():
    """Documented precision limit (SEMANTICS R5.8): a change in the 2 cycles before an internal edge is judged
    by the next location. IDLE has no clock guard, so a stop bit up to 2 cycles short of T - d passes Check."""
    w = oracle.encode([0x41, 0x41], T, offset=lambda f, k: -(D + 2) if (f, k) == (0, 10) else 0)
    assert oracle.decode(w, T, D)[1]                     # the oracle rejects it
    assert run_check(CHECK, w)[0] == []                  # Check does not


def test_location_count():
    assert len(SPEC.locs) == 6
