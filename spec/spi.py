"""SPI target, modes 0-3 (side `tgt` drives MISO; side `ctl` drives CS, SCK, MOSI).

The controller's lines are written as observe edges, so Drive is meaningful as `tgt` only (week-1 scope). MSB first,
one shift register for both directions (full duplex). Timing parameters, in line cycles:
    H   minimum SCK half period, and minimum CS-fall-to-first-edge;
    tV  output-valid window: MOSI and MISO may change only within tV after a shift event (CS fall or shift edge);
        outside it they must be stable, which also gives setup >= H - tV before every sampling edge.
        This is stricter than a bare setup-time rule: a change after tV but still tSU before the sampling edge is
        legal for the oracle and flagged here. Choose tV to match the device's output-valid time.
CPHA 0 samples on the leading edge and shifts on the trailing edge; CPHA 1 the other way round (SPI Block Guide).

TX bytes stream across frames, as in common SPI peripherals: the shift register always holds the next byte to send.
PRE loads the first one (Drive waits for the TX FIFO); every byte boundary pushes the received byte and loads the
next; CS fall only presents the preloaded byte. A byte preloaded at the end of a frame is sent in the next frame.
"""
from spex.dsl import txf_ne
from spex.dsl import DATA, OD, Op, Spec, bitcnt_eq, bitcnt_lt

BIG = (1 << 20) - 1


def spi(mode: int = 0, H: int = 12, tV: int = 6) -> Spec:
    if mode not in range(4):
        raise ValueError("mode 0..3")
    if tV < 4 or H <= tV:
        raise ValueError("need tV >= 4 (R4.5, the clock is reset by a pin event) and H > tV")
    cpol, cpha = mode >> 1, mode & 1
    lead, idle = 1 - cpol, cpol
    s = Spec(f"spi_mode{mode}", sides=["ctl", "tgt"], pins={"CS": 0, "SCK": 1, "MOSI": 2, "MISO": 3},
             clocks=["c"], msb_first=True)
    ALL = ["CS", "SCK", "MOSI", "MISO"]
    tv = s.window("c", tV, tV)
    half = s.window("c", H, H)
    half_open = s.window("c", H, BIG, nom=H)
    miso_out = {"MISO": DATA}
    release = {"MISO": 1}
    PRE = s.loc("PRE")
    IDLE = s.loc("IDLE", watch=["CS"])
    s.emit(PRE, IDLE, "tgt", release, mode=OD, data=txf_ne(), op=Op("LOAD"), label="preload")
    if cpha == 0:
        CZ, ST, HI = s.loc("CZ", watch=["CS", "SCK"]), s.loc("ST", watch=ALL), s.loc("HI", watch=ALL)
        s.emit(IDLE, CZ, "tgt", miso_out, on={"CS": 0, "SCK": idle}, op=Op("PEEK", "MISO"), reset=["c"],
               label="CS fall: first MISO bit")
        s.internal(CZ, ST, after=tv, label="data valid")
        s.observe(ST, HI, {"SCK": lead, "CS": 0}, after=half, op=Op("SHIN", "MOSI"), reset=["c"],
                  label="leading edge: sample")
        s.emit(ST, IDLE, "tgt", release, mode=OD, on={"CS": 1, "SCK": idle}, data=bitcnt_eq(0), label="CS rise")
        s.emit(HI, CZ, "tgt", miso_out, on={"SCK": idle, "CS": 0}, within=half_open, data=bitcnt_lt(8),
               op=Op("PEEK", "MISO"), reset=["c"], label="trailing edge: shift")
        s.emit(HI, CZ, "tgt", miso_out, on={"SCK": idle, "CS": 0}, within=half_open, data=bitcnt_eq(8),
               op=Op("PUSH_LOAD_PEEK", "MISO"), reset=["c"], label="trailing edge: byte boundary")
    else:
        CZ0, WL = s.loc("CZ0", watch=["CS", "SCK"]), s.loc("WL", watch=ALL)
        CZ, WT = s.loc("CZ", watch=["CS", "SCK"]), s.loc("WT", watch=ALL)
        s.emit(IDLE, CZ0, "tgt", miso_out, on={"CS": 0, "SCK": idle}, op=Op("PEEK", "MISO"), reset=["c"],
               label="CS fall: present the preloaded byte")
        s.internal(CZ0, WL, after=tv, label="data valid (CS)")
        s.emit(WL, CZ, "tgt", miso_out, on={"SCK": lead, "CS": 0}, within=half_open, data=bitcnt_lt(8),
               op=Op("PEEK", "MISO"), reset=["c"], label="leading edge: shift")
        s.emit(WL, CZ, "tgt", miso_out, on={"SCK": lead, "CS": 0}, within=half_open, data=bitcnt_eq(8),
               op=Op("PUSH_LOAD_PEEK", "MISO"), reset=["c"], label="leading edge: byte boundary")
        s.emit(WL, IDLE, "tgt", release, mode=OD, on={"CS": 1, "SCK": idle}, data=bitcnt_eq(8),
               op=Op("LOAD_PUSH"), label="CS rise after a byte: push it, preload the next")
        s.emit(WL, IDLE, "tgt", release, mode=OD, on={"CS": 1, "SCK": idle}, data=bitcnt_eq(0),
               label="CS rise, no bits")
        s.internal(CZ, WT, after=tv, label="data valid")
        s.observe(WT, WL, {"SCK": idle, "CS": 0}, after=half, op=Op("SHIN", "MOSI"), reset=["c"],
                  label="trailing edge: sample")
    s.resync(IDLE, writes={"tgt": (release, OD)})
    return s
