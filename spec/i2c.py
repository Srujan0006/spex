"""I2C, controller (side `ctl`) and EEPROM-style target (side `tgt`), Standard- and Fast-mode, from UM10204.

Both lines are open drain. The spec follows the bus one SCL phase at a time:
    *_LOW   SCL just fell: the bit's transmitter sets SDA within tVD (UM10204 tVD;DAT / tVD;ACK)
    *_SET   SDA must now be stable; the controller releases SCL after tLOW
    *_REL   SCL released: wait for the line to rise (any device may stretch the clock)
    *_HIGH  SCL high: SDA stable; the controller pulls SCL low after tHIGH (or makes STOP / repeated START)
Byte phases: A (address, sent by ctl), AKA/AKN (target ACK/NACK of the address), CB (the controller's choice slot
after an acknowledge: next data byte, STOP or repeated START), D (data sent by ctl), AKD (target ACK of data;
an EEPROM always ACKs data, so a missing ACK is a TIMEOUT), R (data sent by tgt), MA (controller ACK/NACK of read
data). Where two devices hand SDA over inside one SCL-low phase (after an ACK), the emits are `silent`: an observer
judges SDA only when the tVD window closes.

Controller host stream (Drive as ctl): tokens START, NEXT (write the next TX byte), STOP, SR (repeated START, then
the address from the TX FIFO), ACK / NACK (after each read byte). Each NEXT, STOP or SR token also consumes one TX
byte at the choice slot: the data byte for NEXT, 0x00 for STOP, 0xFF for SR (only its bit 7 reaches the bus). The RX FIFO receives every acknowledged byte on the bus
(address, written data, read data). Target (Drive as tgt): ACKs its address, pushes received bytes to RX, sends read
bytes from the TX FIFO. Timing limits: UM10204 Rev. 7.0, Table 11 [Source]; the spec's tolerance above each minimum
is `slack` cycles (UM10204 has no maximum for most of them; slack bounds what Check accepts and what Stress drives).
"""
import math

from spex.dsl import DATA, OD, Op, Spec, bitcnt_eq, bitcnt_lt, sr_match, sr_nomatch

# UM10204 Rev. 7.0 Table 11, microseconds (minimums; tVD is a maximum)
TABLE_11 = {
    "standard": dict(tHD_STA=4.0, tLOW=4.7, tHIGH=4.0, tSU_STA=4.7, tSU_STO=4.0, tBUF=4.7, tVD=3.45),
    "fast": dict(tHD_STA=0.6, tLOW=1.3, tHIGH=0.6, tSU_STA=0.6, tSU_STO=0.6, tBUF=1.3, tVD=0.9),
}
START, STOP, SR, ACK, NACK, NEXT = 1, 3, 4, 5, 6, 8      # NEXT = 8 shares the bit-count constant (8 constants)


def limits(mode: str, f_clk: float = 48e6):
    t = {}
    for k, us in TABLE_11[mode].items():
        n = us * 1e-6 * f_clk
        t[k] = math.floor(n + 1e-9) if k == "tVD" else math.ceil(n - 1e-9)
    return t


def i2c(mode: str = "standard", addr: int = 0x50, f_clk: float = 48e6, slack: int = None) -> Spec:
    t = limits(mode, f_clk)
    slack = t["tLOW"] if slack is None else slack
    s = Spec(f"i2c_{mode}", sides=["ctl", "tgt"], pins={"SCL": 0, "SDA": 1}, clocks=["c"], msb_first=True)
    W = lambda lo: s.window("c", lo, lo + slack, nom=lo + slack // 4)        # noqa: E731
    W_HDSTA, W_HIGH, W_SUSTO, W_SUSTA, W_REL = W(t["tHD_STA"]), W(t["tHIGH"]), W(t["tSU_STO"]), W(t["tSU_STA"]), \
        W(t["tLOW"])
    W_DAT = s.window("c", 0, t["tVD"], nom=t["tVD"] // 2)
    W_BUF = s.window("c", t["tBUF"], t["tBUF"])
    BOTH, SCLW = ["SCL", "SDA"], ["SCL"]
    L = {}

    def loc(name, watch=BOTH, inv=None):
        L[name] = s.loc(name, watch=watch, invariant=inv)
        return L[name]

    IDLE, BUSFREE, S_HD = loc("IDLE"), loc("BUSFREE"), loc("S_HD")
    s.emit(IDLE, S_HD, "ctl", {"SDA": 0}, mode=OD, token=START, cond={"SCL": 1}, reset=["c"], label="START")
    s.internal(BUSFREE, IDLE, after=W_BUF, label="bus free")

    def release_scl(src, dst):
        s.emit(src, dst, "ctl", {"SCL": 1}, mode=OD, at=W_REL, label=f"{src.name}: release SCL")

    def ctl_byte(prefix, first, ack_loc):
        """A controller-sent byte; `first` (or None) is the location of bit 7's SCL-low phase."""
        LOW, SET, REL, HIGH = (loc(f"{prefix}_{x}", SCLW if x == "LOW" else BOTH) for x in ("LOW", "SET", "REL", "HIGH"))
        if first is not None:
            s.emit(first, SET, "ctl", {"SDA": DATA}, mode=OD, at=W_DAT, op=Op("LOAD_PEEK", "SDA"), label=f"{prefix} bit 7")
        s.emit(LOW, SET, "ctl", {"SDA": DATA}, mode=OD, at=W_DAT, op=Op("PEEK", "SDA"), label=f"{prefix} bit")
        release_scl(SET, REL)
        s.observe(REL, HIGH, {"SCL": 1}, after=W_REL, op=Op("SHIN", "SDA"), reset=["c"], label=f"{prefix} SCL rise")
        s.emit(HIGH, LOW, "ctl", {"SCL": 0}, mode=OD, at=W_HIGH, data=bitcnt_lt(8), reset=["c"], label=f"{prefix} SCL fall")
        s.emit(HIGH, ack_loc, "ctl", {"SCL": 0, "SDA": 1}, mode=OD, at=W_HIGH, data=bitcnt_eq(8), reset=["c"],
               label=f"{prefix} SCL fall, release SDA for ACK")
        return LOW

    def ack_clock(prefix, sda, nxt_table):
        """SET -> REL -> HIGH of an acknowledge bit whose SDA level is `sda`; HIGH leaves by nxt_table."""
        SET, REL, HIGH = loc(f"{prefix}_SET"), loc(f"{prefix}_REL"), loc(f"{prefix}_HIGH")
        release_scl(SET, REL)
        s.observe(REL, HIGH, {"SCL": 1, "SDA": sda}, after=W_REL, reset=["c"], label=f"{prefix} SCL rise")
        for dst, data, tgt_release, ctl_writes in nxt_table:
            if tgt_release:            # the target lets go of SDA as SCL falls; the same edge for observers
                s.emit(HIGH, dst, "tgt", {"SDA": 1}, mode=OD, on={"SCL": 0}, within=W_HIGH, data=data, reset=["c"],
                       shadow=True, label=f"{prefix} SCL fall: tgt releases SDA")
            s.emit(HIGH, dst, "ctl", ctl_writes, mode=OD, at=W_HIGH, data=data, reset=["c"], label=f"{prefix} SCL fall")
        return SET

    A0 = loc("A0_LOW", SCLW)
    s.emit(S_HD, A0, "ctl", {"SCL": 0}, mode=OD, at=W_HDSTA, reset=["c"], label="first SCL fall")
    AKA_LOW = loc("AKA_LOW", SCLW)
    ctl_byte("A", A0, AKA_LOW)
    CB_LOW, R0_LOW, MA_LOW = loc("CB_LOW", SCLW), loc("R0_LOW", SCLW), loc("MA_LOW", SCLW)
    write, read = sr_nomatch(0x01, 0x01), sr_match(0x01, 0x01)
    AKA_SET = ack_clock("AKA", 0, [(CB_LOW, write, True, {"SCL": 0}), (R0_LOW, read, False, {"SCL": 0})])
    AKN_SET = ack_clock("AKN", 1, [(CB_LOW, None, False, {"SCL": 0})])
    s.emit(AKA_LOW, AKA_SET, "tgt", {"SDA": 0}, mode=OD, at=W_DAT, data=sr_match(addr << 1, 0xFE), op=Op("PUSH"),
           label="address ACK")
    s.emit(AKA_LOW, AKN_SET, "tgt", {"SDA": 1}, mode=OD, at=W_DAT, data=sr_nomatch(addr << 1, 0xFE), silent=True,
           label="address NACK")

    # controller's choice slot after an acknowledge
    CB_SET, CB_REL, CB_HIGH = loc("CB_SET"), loc("CB_REL"), loc("CB_HIGH")
    # The choice slot always loads the next TX byte and puts its bit 7 on SDA: a data byte, or 0x00 before STOP,
    # or 0xFF before a repeated START (the host's data stream decides SDA; the token decides the branch below).
    s.emit(CB_LOW, CB_SET, "ctl", {"SDA": DATA}, mode=OD, at=W_DAT, silent=True, op=Op("LOAD_PEEK", "SDA"),
           label="choice slot: bit 7 of the next TX byte")
    release_scl(CB_SET, CB_REL)
    s.observe(CB_REL, CB_HIGH, {"SCL": 1}, after=W_REL, op=Op("SHIN", "SDA"), reset=["c"], label="CB SCL rise")
    AKD_LOW = loc("AKD_LOW", SCLW, inv=W_DAT)
    D_LOW = ctl_byte("D", None, AKD_LOW)
    s.emit(CB_HIGH, D_LOW, "ctl", {"SCL": 0}, mode=OD, at=W_HIGH, token=NEXT, reset=["c"], label="next byte: SCL fall")
    s.emit(CB_HIGH, BUSFREE, "ctl", {"SDA": 1}, mode=OD, visible=True, at=W_SUSTO, token=STOP, cond={"SCL": 1},
           reset=["c"], label="STOP")
    s.emit(CB_HIGH, S_HD, "ctl", {"SDA": 0}, mode=OD, at=W_SUSTA, token=SR, cond={"SCL": 1}, reset=["c"],
           label="repeated START")

    # data ACK by the target
    AKD_SET = ack_clock("AKD", 0, [(CB_LOW, None, True, {"SCL": 0})])
    s.emit(AKD_LOW, AKD_SET, "tgt", {"SDA": 0}, mode=OD, at=W_DAT, op=Op("PUSH"), label="data ACK")

    # read: the target sends, the controller acknowledges
    R_LOW, R_SET, R_REL, R_HIGH = loc("R_LOW", SCLW), loc("R_SET"), loc("R_REL"), loc("R_HIGH")
    s.emit(R0_LOW, R_SET, "tgt", {"SDA": DATA}, mode=OD, at=W_DAT, silent=True, op=Op("LOAD_PEEK", "SDA"),
           label="read bit 7")
    s.emit(R_LOW, R_SET, "tgt", {"SDA": DATA}, mode=OD, at=W_DAT, op=Op("PEEK", "SDA"), label="read bit")
    release_scl(R_SET, R_REL)
    s.observe(R_REL, R_HIGH, {"SCL": 1}, after=W_REL, op=Op("SHIN", "SDA"), reset=["c"], label="R SCL rise")
    s.emit(R_HIGH, R_LOW, "ctl", {"SCL": 0}, mode=OD, at=W_HIGH, data=bitcnt_lt(8), reset=["c"], label="R SCL fall")
    s.emit(R_HIGH, MA_LOW, "tgt", {"SDA": 1}, mode=OD, on={"SCL": 0}, within=W_HIGH, data=bitcnt_eq(8), reset=["c"],
           shadow=True, label="R last SCL fall: tgt releases SDA")
    s.emit(R_HIGH, MA_LOW, "ctl", {"SCL": 0}, mode=OD, at=W_HIGH, data=bitcnt_eq(8), reset=["c"],
           label="R last SCL fall")
    MA_SET, MA_REL, MA_AH, MA_NH = loc("MA_SET"), loc("MA_REL"), loc("MA_AH"), loc("MA_NH")
    s.emit(MA_LOW, MA_SET, "ctl", {"SDA": 0}, mode=OD, at=W_DAT, token=ACK, silent=True, op=Op("PUSH"), label="ACK read")
    s.emit(MA_LOW, MA_SET, "ctl", {"SDA": 1}, mode=OD, at=W_DAT, token=NACK, silent=True, op=Op("PUSH"),
           label="NACK read")
    release_scl(MA_SET, MA_REL)
    s.observe(MA_REL, MA_AH, {"SCL": 1, "SDA": 0}, after=W_REL, reset=["c"], label="MA rise, ACK")
    s.observe(MA_REL, MA_NH, {"SCL": 1, "SDA": 1}, after=W_REL, reset=["c"], label="MA rise, NACK")
    s.emit(MA_AH, R0_LOW, "ctl", {"SCL": 0, "SDA": 1}, mode=OD, at=W_HIGH, reset=["c"], label="after ACK: SCL fall")
    s.emit(MA_NH, CB_LOW, "ctl", {"SCL": 0}, mode=OD, at=W_HIGH, reset=["c"], label="after NACK: SCL fall")

    s.resync(IDLE, writes={"ctl": ({"SCL": 1, "SDA": 1}, OD), "tgt": ({"SDA": 1}, OD)})
    return s
