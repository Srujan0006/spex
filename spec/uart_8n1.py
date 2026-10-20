"""UART 8N1, one direction (side `tx` drives TX; side `rx` only listens).

Timing model: a bit grid. The start edge resets clock g. Internal grid ticks open an edge window around every
nominal boundary k*T (k = 1..9): the window is [k*T - d, k*T + d] in line time, d = the edge tolerance. Data emits
never reset a clock, so a data bit equal to the previous one (no line change) is judged by silent completion
(SEMANTICS R7.4) and the grid does not drift. Outside a window the line is watched: any change is UNEXPECTED.

    spec = uart_8n1(T=417, d=8)      # 115200 baud at 48 MHz, +-8 cycles per edge
"""
from spex.dsl import DATA, Op, Spec, bitcnt_eq, bitcnt_lt, txf_ne

OPEN_LEAD = 2          # a tick fires 2 cycles before the window opens: the earliest exact emit is lo = E + 1 (R4.5)


def uart_8n1(T: int = 417, d: int = 8, pin: int = 0) -> Spec:
    if d < 0 or T - d - OPEN_LEAD < 4 or 2 * d + OPEN_LEAD + 2 >= T:
        raise ValueError("need T - d - 2 >= 4 and windows shorter than a bit")
    s = Spec("uart_8n1", sides=["tx", "rx"], pins={"TX": pin}, clocks=["g"], msb_first=False)
    w = s.window("g", OPEN_LEAD, 2 * d + OPEN_LEAD, nom=d + OPEN_LEAD)       # edge window after a tick
    inv = s.window("g", 0, 2 * d + OPEN_LEAD)
    IDLE = s.loc("IDLE", watch=["TX"])
    START = s.loc("START", watch=["TX"])                                       # start bit: line must stay low
    OPEN_D = s.loc("OPEN_D", watch=["TX"], invariant=inv)                      # data boundary window
    STABLE = s.loc("STABLE", watch=["TX"])                                     # between windows
    OPEN_S = s.loc("OPEN_S", watch=["TX"], invariant=inv)                      # stop boundary window
    STOPST = s.loc("STOPST", watch=["TX"])                                     # stop bit
    s.emit(IDLE, START, "tx", {"TX": 0}, data=txf_ne(), op=Op("LOAD"), reset=["g"], label="start bit")
    s.internal(START, OPEN_D, after=s.window("g", T - d - OPEN_LEAD, T - d - OPEN_LEAD), reset=["g"], label="tick 1")
    s.emit(OPEN_D, STABLE, "tx", {"TX": DATA}, at=w, op=Op("SHOUT", "TX"), label="data bit")
    s.internal(STABLE, OPEN_D, after=s.window("g", T, T), data=bitcnt_lt(8), reset=["g"], label="tick")
    s.internal(STABLE, OPEN_S, after=s.window("g", T, T), data=bitcnt_eq(8), reset=["g"], label="tick 9")
    s.emit(OPEN_S, STOPST, "tx", {"TX": 1}, at=w, label="stop bit")
    s.internal(STOPST, IDLE, after=s.window("g", T, T), op=Op("PUSH"), label="frame end")
    s.resync(IDLE)
    return s
