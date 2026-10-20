"""Step 5: metamorphic relations that need no hand-written expected answers.

1. Role duality: for every spec, side and policy, the Drive trace passes Check of the same spec.
   Planted interpreter bug: "random policy does not fold into the window" (tests/model/mutants.py).
2. Time scaling: multiply every window by k; the line events of a Drive run (clock-triggered timing,
   deterministic policy) move to exactly k times their offsets from the first event.
   Planted interpreter bug: "GE guard is strict (v > lo)".
3. Engine permutation: the same spec on engine 1 with a pin base gives the same trace on the rotated pins;
   and engine 1 checks engine 0's Drive output inside one chip.
   Planted interpreter bug: "output rotation in the wrong direction".

Reactive edges (SPI target, I2C target answers) react in L = 3..5 cycles, a constant of the chip, so they are
not expected to scale; time scaling is checked on UART TX and the I2C controller."""
import pytest

import i2c as i2c_oracle
import spi as spi_oracle
import uart as uart_oracle
from harness import START_CYCLE, HostOp, load, run_check, run_drive
from spec.i2c import ACK, NACK, NEXT, SR, START, STOP, i2c
from spec.spi import spi
from spec.uart_8n1 import uart_8n1
from spex.compiler import compile_spec
from spex.dsl import scale_time
from spex.refsim import POL_EARLIEST, POL_LATEST, POL_NOMINAL, POL_RANDOM, POL_SWEEP, Policy, Spex

POLICIES = [("nominal", Policy(POL_NOMINAL), None), ("earliest", Policy(POL_EARLIEST), None),
            ("latest", Policy(POL_LATEST), None), ("sweep", Policy(POL_SWEEP, 2, 3), None),
            ("random-1", Policy(POL_RANDOM), 1), ("random-2", Policy(POL_RANDOM), 2),
            ("random-3", Policy(POL_RANDOM), 3)]
PIDS = [p[0] for p in POLICIES]


# ---------------------------------------------------------------- drivers per spec
def uart_drive(spec, policy, seed, data=(0x55, 0xA3, 0x0F), cycles=None):
    d = compile_spec(spec, "drive", side="tx")
    host = {5 + i: HostOp("push_tx", 0, b) for i, b in enumerate(data)}
    T = 48 * 12
    pads, m, viols = run_drive(d, cycles or T * (len(data) + 2) * 4, lambda o, n: (o.out & 1) if o.oe & 1 else 1,
                               host, policy, seed)
    return pads, viols


def spi_drive(mode, policy, seed):
    ctl = spi_oracle.gen_controller(mode, [[0xA5, 0x3C], [0x81]], 12, lead=40)
    host = {5 + i: HostOp("push_tx", 0, b) for i, b in enumerate([0x5A, 0xC3, 0x7E])}

    def bus(o, n):
        miso = (o.out >> 3) & 1 if (o.oe >> 3) & 1 else 1
        return (ctl[n] & ~8) | (miso << 3)
    pads, _, viols = run_drive(compile_spec(spi(mode), "drive", side="tgt"), len(ctl), bus, host, policy, seed)
    return pads, viols


def i2c_run(spec, side, agent, host, policy, seed, cycles):
    m = load(compile_spec(spec, "drive", side=side))
    ops = dict(host)
    ops[0], ops[START_CYCLE] = HostOp("policy", 0, policy), HostOp("start")
    if seed is not None:
        ops[1] = HostOp("seed", 0, seed)
    line, w, viols = 3, [], []
    for n in range(cycles):
        o = m.outputs()
        line = 3 & ~(agent.step(n, line) | (o.oe & ~o.out & 3))
        w.append(line)
        viols += m.step(line, ops.get(n)).violations
    return w, viols


def i2c_host(tokens, tx):
    ops = {5 + i: HostOp("push_tx", 0, b) for i, b in enumerate(tx)}
    ops.update({5 + len(tx) + i: HostOp("push_token", 0, t) for i, t in enumerate(tokens)})
    return ops


READ_TOKENS, READ_TX = [START, NEXT, SR, ACK, NACK, STOP], [0xA0, 0x10, 0xFF, 0xA1, 0x00]
MEM = {0x10: 0x5A, 0x11: 0xC3}


# ---------------------------------------------------------------- 1. role duality
@pytest.mark.parametrize("name, policy, seed", POLICIES, ids=PIDS)
def test_duality_uart(name, policy, seed):
    spec = uart_8n1(48, 4)
    pads, viols = uart_drive(spec, policy, seed)
    assert viols == []
    cv, m = run_check(compile_spec(spec, "check"), pads)
    assert cv == [] and m.s.engines[0].rx == [0x55, 0xA3, 0x0F]


@pytest.mark.parametrize("mode", range(4))
@pytest.mark.parametrize("name, policy, seed", [POLICIES[0], POLICIES[2], POLICIES[4]], ids=["nominal", "latest", "random-1"])
def test_duality_spi_target(mode, name, policy, seed):
    pads, viols = spi_drive(mode, policy, seed)
    assert viols == []
    assert run_check(compile_spec(spi(mode), "check"), pads)[0] == []


@pytest.mark.parametrize("name, policy, seed", POLICIES, ids=PIDS)
def test_duality_i2c_controller(name, policy, seed):
    spec = i2c("fast")
    tgt = i2c_oracle.Target(0x50, MEM, stretch=40)
    w, viols = i2c_run(spec, "ctl", tgt, i2c_host(READ_TOKENS, READ_TX), policy, seed, 16000)
    assert viols == [] and i2c_oracle.check(w, "fast")[1] == []
    assert run_check(compile_spec(spec, "check"), w)[0] == []


@pytest.mark.parametrize("name, policy, seed", [POLICIES[1], POLICIES[2], POLICIES[5]], ids=["earliest", "latest", "random-2"])
def test_duality_i2c_target(name, policy, seed):
    spec = i2c("fast")
    ctl = i2c_oracle.Controller([("S",), ("W", 0xA0), ("W", 0x10), ("Sr",), ("W", 0xA1), ("R", True), ("R", False),
                                 ("P",)], "fast", lead=40)
    w, viols = i2c_run(spec, "tgt", ctl, i2c_host([], [0x5A, 0xC3]), policy, seed, 16000)
    assert viols == [] and i2c_oracle.check(w, "fast")[1] == [] and ctl.reads == [0x5A, 0xC3]
    assert run_check(compile_spec(spec, "check"), w)[0] == []


def test_duality_i2c_standard_mode_controller():
    spec = i2c("standard")
    tgt = i2c_oracle.Target(0x50, MEM)
    w, viols = i2c_run(spec, "ctl", tgt, i2c_host(READ_TOKENS, READ_TX), Policy(POL_LATEST), None, 60000)
    assert viols == [] and run_check(compile_spec(spec, "check"), w)[0] == []


# ---------------------------------------------------------------- 2. time scaling
def events(w, mask):
    ev = [(n, (w[n] ^ w[n - 1]) & mask) for n in range(1, len(w)) if (w[n] ^ w[n - 1]) & mask]
    t0 = ev[0][0]
    return [(n - t0, c) for n, c in ev]


@pytest.mark.parametrize("k", [2, 3])
@pytest.mark.parametrize("name, policy", [("nominal", Policy(POL_NOMINAL)), ("earliest", Policy(POL_EARLIEST)),
                                          ("latest", Policy(POL_LATEST))])
def test_time_scaling_uart(k, name, policy):
    base = uart_8n1(48, 4)
    p1, v1 = uart_drive(base, policy, None, data=(0x55,), cycles=1200)
    pk, vk = uart_drive(scale_time(base, k), policy, None, data=(0x55,), cycles=1200 * k)
    assert v1 == vk == []
    e1, ek = events(p1, 1), events(pk, 1)
    assert len(e1) == 10 and [(k * t, c) for t, c in e1] == ek
    assert run_check(compile_spec(scale_time(base, k), "check"), pk)[0] == []


@pytest.mark.parametrize("k", [2, 3])
def test_time_scaling_i2c_controller(k):
    base = i2c("fast")
    runs = []
    for kk in (1, k):
        tgt = i2c_oracle.Target(0x50, MEM, d=4 * kk - 1)     # the model samples the line 1 cycle late: d + 1 scales
        w, v = i2c_run(scale_time(base, kk), "ctl", tgt, i2c_host(READ_TOKENS, READ_TX), Policy(POL_NOMINAL), None,
                       16000 * kk)
        assert v == []
        runs.append(events(w, 3))
    e1, ek = runs
    assert len(e1) > 100 and [(k * t, c) for t, c in e1] == ek


# ---------------------------------------------------------------- 3. engine permutation
def rot(v, b):
    return ((v << b) | (v >> (8 - b))) & 0xFF


def test_permutation_uart_drive_on_engine1():
    d = compile_spec(uart_8n1(48, 4), "drive", side="tx")
    traces = []
    for engine, base in ((0, 0), (1, 3)):
        d.image.config.pin_base = base
        m = Spex(2)
        m.s.engines[engine].image = d.image
        host = {0: HostOp("start", engine), 5: HostOp("push_tx", engine, 0x55), 6: HostOp("push_tx", engine, 0xA3)}
        outs = []
        for n in range(2400):
            o = m.outputs()
            outs.append((o.out & o.oe) | (~o.oe & 0xFF))
            m.step(outs[-1], host.get(n))
        traces.append(outs)
    d.image.config.pin_base = 0
    assert traces[1] == [rot(v, 3) for v in traces[0]]


def test_permutation_spi_check_on_engine1():
    w = spi_oracle.add_target(spi_oracle.gen_controller(1, [[0xA5, 0x3C]], 12, lead=40), 1, [[0x5A, 0xC3]], 3)
    s = [u for u in range(1, len(w)) if not w[u] & 1 and (w[u] ^ w[u - 1]) & 2 and not (w[u] >> 1) & 1][2]
    w[s - 2] ^= 4                                     # MOSI glitch before a sampling (trailing) edge, mode 1
    results = []
    for engine, base in ((0, 0), (1, 2)):
        c = compile_spec(spi(1), "check")
        c.image.config.pin_base = base
        m = Spex(2)
        m.s.engines[engine].image = c.image
        viols = []
        for n, p in enumerate(w):
            viols += m.step(rot(p, base), HostOp("start", engine) if n == START_CYCLE else None).violations
        results.append([(v.cycle, v.kind, v.loc, v.pins) for v in viols])
    assert results[0] and results[0] == results[1]


def test_self_check_in_one_chip():
    """Engine 0 drives UART on pin 0; engine 1 checks the same pin (proposal demo L4)."""
    d, c = compile_spec(uart_8n1(48, 4), "drive", side="tx"), compile_spec(uart_8n1(48, 4), "check")
    m = Spex(2)
    m.s.engines[0].image, m.s.engines[1].image = d.image, c.image
    host = {3: HostOp("start", 0), 4: HostOp("start", 1), 5: HostOp("policy", 0, Policy(POL_RANDOM))}
    host.update({6 + i: HostOp("push_tx", 0, b) for i, b in enumerate([0x55, 0xA3, 0x0F])})
    viols = []
    for n in range(3000):
        o = m.outputs()
        viols += m.step((o.out & o.oe) | (~o.oe & 0xFF), host.get(n)).violations
    assert viols == [] and m.s.engines[1].rx == [0x55, 0xA3, 0x0F]
