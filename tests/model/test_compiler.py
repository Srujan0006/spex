"""Compiler (step 3): role transform, time base, encoding, and one rejection test per check (R7.12).

These use small specs written here, not spec/ (the protocol specs are judged by the oracles in step 4).
Mutants that must make this file fail are in tests/model/compiler_mutants.py."""
import pytest

from spex.compiler import CompileError, compile_spec
from spex.dsl import DATA, OD, Op, Spec, SpecError, bitcnt_eq, bitcnt_lt, sr_match, sr_nomatch, txf_ne
from spex.refsim import (CK_POLICY, CK_WIN, EDGE, LEVEL, TIMEOUT, UNEXPECTED, HostOp, Policy, Spex,
                         POL_EARLIEST, POL_LATEST, POL_NOMINAL, POL_RANDOM, unpack_edge)

T_BIT, D_TOL = 40, 4


def toy_uart():
    """UART 8N1 on a bit grid: grid ticks are internal edges, data emits never reset clocks (R7.4)."""
    s = Spec("toy_uart", sides=["tx", "rx"], pins={"TX": 0}, clocks=["g"], msb_first=False)
    IDLE = s.loc("IDLE", watch=["TX"])
    START, OPEN_D, OPEN_S, STABLE, STOPST = (s.loc(n, watch=["TX"]) for n in "START OPEN_D OPEN_S STABLE STOPST".split())
    W = s.window("g", 2, 2 * D_TOL + 2, nom=D_TOL + 2)          # edge window around each grid point
    s.emit(IDLE, START, "tx", {"TX": 0}, data=txf_ne(), op=Op("LOAD"), reset=["g"])
    s.internal(START, OPEN_D, after=s.window("g", T_BIT - D_TOL - 2, T_BIT - D_TOL - 2), reset=["g"])
    s.emit(OPEN_D, STABLE, "tx", {"TX": DATA}, at=W, op=Op("SHOUT", "TX"))
    s.internal(STABLE, OPEN_D, after=s.window("g", T_BIT, T_BIT), data=bitcnt_lt(8), reset=["g"])
    s.internal(STABLE, OPEN_S, after=s.window("g", T_BIT, T_BIT), data=bitcnt_eq(8), reset=["g"])
    s.emit(OPEN_S, STOPST, "tx", {"TX": 1}, at=W)
    s.internal(STOPST, IDLE, after=s.window("g", T_BIT, T_BIT), op=Op("PUSH"))
    s.resync(IDLE)
    return s


def uart_line(o):
    return (o.out & 1) if o.oe & 1 else 1          # push-pull, idle high


def run_pair(drive, check, nbytes, cycles, policy=Policy()):
    """Drive engine -> TX line -> Check engine (separate models). Returns (lines, drive model, check model, violations)."""
    md, mc = Spex(1), Spex(1)
    md.s.engines[0].image, mc.s.engines[0].image = drive.image, check.image
    hd = {0: HostOp("start"), 1: HostOp("policy", 0, policy)}
    for i, b in enumerate(nbytes):
        hd[2 + i] = HostOp("push_tx", 0, b)
    lines, viols = [], []
    for n in range(cycles):
        ln = uart_line(md.outputs())
        lines.append(ln)
        viols += md.step(ln, hd.get(n)).violations
        viols += mc.step(ln, {3: HostOp("start")}.get(n)).violations   # R12.7
    return lines, md, mc, viols


# ---------------------------------------------------------------- positive: transform and duality
def test_check_transform_of_toy_uart():
    c = compile_spec(toy_uart(), "check")
    od = c.edges["OPEN_D"]
    assert [e.variant for e in od] == ["observed emit e1a", "observed emit e1b", "silent completion e2"]
    assert [(e.pmask, e.pval, e.pmode) for e in od[:2]] == [(1, 0, EDGE), (1, 1, EDGE)]
    assert od[2].otherwise and od[2].pmask == 0 and (od[2].lo, od[2].hi) == (10, 10)
    assert all(e.op == "SHIN" for e in od)                                   # SHOUT -> SHIN (R7.4)
    os_ = c.edges["OPEN_S"]
    assert (os_[1].pmask, os_[1].pmode) == (1, LEVEL)
    idle = c.edges["IDLE"][0]
    assert idle.dk is None and idle.op == "CLR" and idle.pmask == 1          # TXF_NE dropped, LOAD -> CLR
    assert c.image.config.drive_en == 0
    assert all(unpack_edge(w).ck != CK_POLICY for w in c.image.edges if w)


def test_drive_transform_unwatches_own_pins():
    c = compile_spec(toy_uart(), "drive", side="tx")
    assert all((w & 0xFF) == 0 for w in c.image.locs if w is not None)       # TX is ours, PP (R7.6)
    assert c.edges["OPEN_D"][0].ck == "POLICY" and c.image.config.drive_en == 1


@pytest.mark.parametrize("mode", [POL_NOMINAL, POL_EARLIEST, POL_LATEST, POL_RANDOM])
def test_toy_uart_drive_passes_check(mode):
    d, c = compile_spec(toy_uart(), "drive", side="tx"), compile_spec(toy_uart(), "check")
    data = [0x41, 0xFF, 0x00, 0xA5]
    lines, md, mc, viols = run_pair(d, c, data, 2400, Policy(mode))
    assert viols == []
    assert mc.s.engines[0].rx == data
    falls = [n for n in range(1, len(lines)) if lines[n - 1] and not lines[n]]
    assert len(falls) >= len(data)


def test_toy_uart_check_catches_planted_glitch():
    d, c = compile_spec(toy_uart(), "drive", side="tx"), compile_spec(toy_uart(), "check")
    lines, *_ = run_pair(d, c, [0xFF], 600)
    start = next(n for n in range(1, 600) if lines[n - 1] and not lines[n])
    bad = list(lines)
    bad[start + 60] ^= 1                                                      # one-cycle glitch mid-bit
    mc = Spex(1)
    mc.s.engines[0].image = c.image
    viols = []
    for n in range(600):
        viols += mc.step(bad[n], {3: HostOp("start")}.get(n)).violations
    assert viols and viols[0].kind & UNEXPECTED and viols[0].cycle == start + 60 + 2


# ---------------------------------------------------------------- time-base compensation (R7.7)
def resp_spec():
    s = Spec("resp", sides=["a", "b"], pins={"X": 0, "Y": 1}, clocks=["c"])
    A0, A1, A2 = s.loc("A0"), s.loc("A1", watch=["Y"], invariant=s.window("c", 0, 5)), s.loc("A2", halt=True)
    s.emit(A0, A1, "a", {"X": 1}, at=s.window("c", 5, 5), reset=["c"])
    s.observe(A1, A2, {"Y": 1}, within=s.window("c", 5, 5))
    W0, R, DONE = s.loc("W0", watch=["X"]), s.loc("R"), s.loc("DONE", halt=True)
    s.observe(W0, R, {"X": 1}, reset=["c"])
    s.emit(R, DONE, "b", {"Y": 1}, at=s.window("c", 10, 10))
    return s


def test_R7_7_own_emit_after_observed_event_is_exact_in_line_time():
    s = resp_spec()
    s.initial(s.locs[3])                                    # W0
    c = compile_spec(s, "drive", side="b")
    assert (c.edges["R"][0].lo, c.edges["R"][0].hi) == (7, 7)
    m = Spex(1)
    m.s.engines[0].image = c.image
    out = []
    for n in range(40):
        out.append(m.outputs())
        m.step(1 if n >= 20 else 0, {0: HostOp("start")}.get(n))      # X rises on the pad in cycle 20
    first_y = next(n for n, o in enumerate(out) if o.oe & 2 and o.out & 2)
    assert first_y == 30                                     # 10 cycles of line time after X


@pytest.mark.parametrize("delay, ok", [(5, True), (4, False), (6, False)])
def test_R7_7_observe_after_own_emit_uses_line_time(delay, ok):
    c = compile_spec(resp_spec(), "drive", side="a")
    assert (c.edges["A1"][0].lo, c.edges["A1"][0].hi) == (8, 8)
    m = Spex(1)
    m.s.engines[0].image = c.image
    x_line, viols = None, []
    for n in range(40):
        o = m.outputs()
        if x_line is None and o.oe & 1 and o.out & 1:
            x_line = n
        y = 2 if x_line is not None and n >= x_line + delay else 0
        viols += m.step(y, {0: HostOp("start")}.get(n)).violations
    assert x_line == 6                                        # fired at x = 5 (START in 0), visible in 6
    assert (viols == []) == ok and (m.s.engines[0].state == "HALTED")


def test_otherwise_edges_go_last_and_token_pop_peek():
    s = Spec("t", sides=["a", "b"], pins={"P": 0, "Q": 1}, clocks=["x"])
    A, B, C = s.loc("A", watch=["P"]), s.loc("B"), s.loc("C", halt=True)
    s.observe(A, C, {"P": 1}, mode=LEVEL, within=s.window("x", 9, 9), otherwise=True)
    s.observe(A, B, {"P": 1}, within=s.window("x", 2, 9))
    s.emit(B, C, "a", {"Q": 1}, at=s.window("x", 4, 4), token=5, peek=True)
    s.emit(B, A, "a", {"Q": 0}, at=s.window("x", 4, 4), token=6, reset=["x"])
    c = compile_spec(s, "drive", side="a")
    assert [e.otherwise for e in c.edges["A"]] == [False, True]
    assert [(e.dk, e.dval, e.pop) for e in c.edges["B"]] == [("TOKEN", 5, 0), ("TOKEN", 6, 1)]


# ---------------------------------------------------------------- rejections (R7.12)
def rejects(spec, *args, match, **kw):
    with pytest.raises(CompileError) as ei:
        compile_spec(spec, *args, **kw)
    assert any(match in e for e in ei.value.errors), ei.value.errors


def two_loc(pins=None):
    s = Spec("t", sides=["a", "b"], pins=pins or {"P": 0, "Q": 1}, clocks=["x", "y"])
    return s, s.loc("A", watch=list(s.pins)), s.loc("B", halt=True)


def test_reject_not_observably_deterministic():
    s, A, B = two_loc()
    s.observe(A, B, {"P": 1}, within=s.window("x", 2, 10))
    s.observe(A, A, {"P": 1}, within=s.window("x", 8, 20))
    rejects(s, "check", match="not observably deterministic")


def test_accept_disjoint_by_window_age_widening_and_data():
    s, A, B = two_loc()
    s.observe(A, B, {"P": 1}, within=s.window("x", 2, 10))
    s.observe(A, A, {"P": 1}, within=s.window("x", 13, 20))        # 10 + 2 < 13
    C = s.loc("C")
    s.observe(A, C, {"P": 0, "Q": 1})                          # P = 0: disjoint from the P = 1 edges
    s.internal(C, B, after=s.window("x", 5, 5), data=sr_match(3))
    s.internal(C, B, after=s.window("y", 5, 5), data=sr_nomatch(3))
    compile_spec(s, "check")
    s2, A2, B2 = two_loc()
    s2.observe(A2, B2, {"P": 1}, within=s2.window("x", 2, 10))
    s2.observe(A2, A2, {"P": 1}, within=s2.window("x", 12, 20))     # within the 2-cycle age widening
    rejects(s2, "check", match="not observably deterministic")


def test_reject_indistinguishable_choice():
    s, A, B = two_loc()
    w = s.window("x", 4, 8)
    s.emit(A, B, "a", {"P": 0}, at=w, token=1)
    s.emit(A, A, "a", {"P": 0}, at=w, token=2, reset=["x"])
    compile_spec(s, "drive", side="a")                       # Drive: tokens decide
    rejects(s, "check", match="choice alternatives are not distinguishable")


def test_reject_fan_out_over_4():
    s, A, B = two_loc({"P": 0, "Q": 1, "R": 2, "S": 3, "U": 4})
    for p in ("P", "Q", "R", "S", "U"):
        s.observe(A, B, {p: 1})
    rejects(s, "check", match="> 4")


def test_reject_fan_out_after_expansion():
    s, A, B = two_loc()
    w = s.window("x", 4, 8)
    s.emit(A, B, "a", {"P": DATA}, at=w, op=Op("SHOUT", "P"))   # 3 edges observed
    s.observe(A, B, {"Q": 1}, data=bitcnt_eq(1))
    s.observe(A, B, {"Q": 0}, data=bitcnt_eq(2))
    compile_spec(s, "drive", side="a")
    rejects(s, "check", match="after role expansion > 4")


def test_reject_lo_below_E_plus_1():
    s, A, B = two_loc()
    s.internal(A, B, after=s.window("x", 1, 1))
    rejects(s, "check", match="needs lo >= 2")


def test_reject_lo_below_E_plus_3_after_pin_reset():
    s = Spec("t", sides=["a"], pins={"P": 0}, clocks=["x"])
    A, B, C = s.loc("A", watch=["P"]), s.loc("B"), s.loc("C", halt=True)
    s.observe(A, B, {"P": 1}, reset=["x"])
    s.internal(B, C, after=s.window("x", 3, 3))
    rejects(s, "check", match="needs lo >= 4")
    s.edges[-1].window = s.window("x", 4, 4)
    compile_spec(s, "check")


def test_reject_reset_on_silent_or_invisible_emit():
    s, A, B = two_loc()
    s.emit(A, B, "a", {"P": DATA}, at=s.window("x", 4, 8), op=Op("SHOUT", "P"), reset=["x"])
    rejects(s, "check", match="may be silent")
    s2, A2, B2 = two_loc()
    s2.emit(A2, B2, "a", {"P": 1}, mode=OD, at=s2.window("x", 4, 8), reset=["x"])
    rejects(s2, "check", match="writes no visible pin")


def test_reject_time_base_conflict():
    s = Spec("t", sides=["a", "b"], pins={"P": 0, "Q": 1}, clocks=["x"])
    A, B, C, D = s.loc("A", watch=["Q"]), s.loc("B"), s.loc("C"), s.loc("D", halt=True)
    s.emit(A, B, "a", {"P": 1}, at=s.window("x", 4, 4), reset=["x"])      # E-based
    s.observe(A, B, {"Q": 1}, reset=["x"])                                # O-based
    s.emit(B, D, "a", {"P": 0}, at=s.window("x", 10, 10))
    s.internal(C, D, after=s.window("x", 3, 3))
    rejects(s, "drive", side="a", match="ambiguous")


def test_reject_reaction_faster_than_chip():
    s = Spec("t", sides=["a", "b"], pins={"P": 0, "Q": 1}, clocks=["x"])
    A, B, C = s.loc("A", watch=["Q"]), s.loc("B"), s.loc("C", halt=True)
    s.observe(A, B, {"Q": 1}, reset=["x"])
    s.emit(B, C, "a", {"P": 1}, at=s.window("x", 2, 2))
    rejects(s, "drive", side="a", match="cannot react that fast")


def test_reject_dead_end_and_halt_with_edges():
    s = Spec("t", sides=["a"], pins={"P": 0}, clocks=["x"])
    A, B = s.loc("A"), s.loc("B")
    s.internal(A, B, after=s.window("x", 3, 3))
    rejects(s, "check", match="not declared halt")
    s2 = Spec("t", sides=["a"], pins={"P": 0}, clocks=["x"])
    A2, B2 = s2.loc("A", halt=True), s2.loc("B", halt=True)
    s2.internal(A2, B2, after=s2.window("x", 3, 3))
    rejects(s2, "check", match="halt location has outgoing")


def test_reject_resync_with_clock_guard():
    s, A, B = two_loc()
    s.internal(A, B, after=s.window("x", 3, 3))
    s.resync(A)
    rejects(s, "check", match="resync location may have no clock guard")


def test_reject_nom_outside_window_and_untimed_reset():
    s, A, B = two_loc()
    s.emit(A, B, "a", {"P": 1}, at=s.window("x", 4, 8, nom=9))
    rejects(s, "drive", side="a", match="outside")
    s2, A2, B2 = two_loc()
    s2.internal(A2, B2, reset=["x"])
    rejects(s2, "check", match="no clock guard may not reset")


def test_reject_two_data_pins_and_reserved_op():
    s, A, B = two_loc()
    s.emit(A, B, "a", {"P": DATA, "Q": DATA}, at=s.window("x", 4, 8), op=Op("SHOUT", "P"))
    rejects(s, "check", match="more than one data pin")
    with pytest.raises(SpecError, match="reserved"):
        s.internal(A, B, op=Op("CRC_STEP"))


def test_reject_table_overflow():
    s = Spec("t", sides=["a"], pins={"P": 0}, clocks=["x"])
    locs = [s.loc(f"L{i}") for i in range(18)] + [s.loc("H", halt=True)]
    for i in range(18):
        s.internal(locs[i], locs[i + 1], within=s.window("x", 10 + i, 10 + i), reset=["x"])
    rejects(s, "check", match="more than 16 windows")


# ---------------------------------------------------------------- S39 additions
def s39_spec():
    s = Spec("s39", sides=["a", "b"], pins={"P": 0, "Q": 1}, clocks=["x"])
    A, B, C, D = s.loc("A", watch=["P", "Q"]), s.loc("B", watch=["P", "Q"]), s.loc("C", watch=["P", "Q"]), \
        s.loc("D", halt=True)
    w = s.window("x", 0, 20, nom=10)
    s.emit(A, B, "a", {"P": 0}, mode=OD, token=1, cond={"Q": 1}, reset=["x"], label="pull with cond")
    s.emit(B, C, "a", {"P": DATA}, mode=OD, at=w, token=2, silent=True, op=Op("LOAD_PEEK", "P"), label="silent 1")
    s.emit(B, C, "a", {"P": 0}, mode=OD, at=w, token=3, silent=True, op=Op("CLR"), label="silent 2")
    s.emit(C, D, "a", {"P": 1}, mode=OD, visible=True, at=s.window("x", 30, 40), label="visible release")
    s.emit(C, D, "b", {"Q": 0}, mode=OD, on={"P": 0}, within=s.window("x", 30, 40), shadow=True, label="shadow")
    return s


def test_s39_cond_silent_visible_shadow_dedupe():
    c = compile_spec(s39_spec(), "check")
    a = c.edges["A"][0]
    assert (a.pmask, a.pval) == (0b11, 0b10)                                  # SDA-like P low, cond Q high
    b = c.edges["B"]
    assert len(b) == 1 and b[0].cls == "internal" and (b[0].lo, b[0].hi) == (21, 21) and b[0].op == "CLR"
    cc = c.edges["C"]
    assert [(e.pmask, e.pval, e.otherwise) for e in cc] == [(1, 1, False), (1, 1, True)]   # e1 + e2; no shadow
    d = compile_spec(s39_spec(), "drive", side="b")
    assert [e.variant for e in d.edges["C"]] == ["observed emit e1", "own emit", "silent completion e2"]


def test_s39_policy_lo_clipped_with_warning():
    c = compile_spec(s39_spec(), "drive", side="a")
    b = c.edges["B"]
    assert all(e.lo == 4 for e in b) and any("clipped" in w for w in c.warnings)   # echo dwell D + 1 (R7.6b)


def test_s39_own_echo_unwatched_in_target():
    c = compile_spec(s39_spec(), "drive", side="a")
    watch = {n: c.image.locs[i] & 0xFF for n, i in c.loc_index.items()}
    assert watch["B"] == 0b10 and watch["A"] == 0b11                          # P echo of A's emit ignored in B
    assert compile_spec(s39_spec(), "check").image.locs[c.loc_index["B"]] & 0xFF == 0b11


def test_s39_ge_and_invariant_share_windows():
    s = Spec("t", sides=["a"], pins={"P": 0}, clocks=["x"])
    A, B = s.loc("A", watch=["P"], invariant=s.window("x", 0, 40)), s.loc("B", halt=True)
    s.observe(A, B, {"P": 1}, within=s.window("x", 10, 40))
    s.observe(A, B, {"P": 0}, after=s.window("x", 10, 10))
    c = compile_spec(s, "check")
    assert sum(w is not None for w in c.image.windows) == 1


def test_table_usage_report():
    """R11.8 evidence: the listing's 'table use' line. Planted bug: tests/model/mutants.py ('usage counts the
    placeholder window')."""
    from spec.i2c import i2c
    from spec.spi import spi
    c = compile_spec(i2c("standard"), "drive", side="ctl")
    u = c.usage
    assert (u["locations"], u["windows"], u["constants"], u["actions"]) == ((37, 64), (9, 16), (8, 8), (15, 16))
    assert u["max_clock_value"] == 455 and "table use: locations 37/64" in c.listing
    s = compile_spec(spi(0), "check")
    assert s.usage["max_clock_value"] == 12                                  # XMAX = "no upper bound", not counted
    s2 = Spec("t", sides=["a"], pins={"P": 0}, clocks=["x"])
    A, B = s2.loc("A", watch=["P"]), s2.loc("B", halt=True)
    s2.observe(A, B, {"P": 1})
    assert compile_spec(s2, "check").usage["windows"] == (0, 16)            # no windows: the placeholder is not use
