# How to write a SPEX spec

A spec describes one protocol, as both sides see it on the wires, once. The compiler turns it into tables for each role:
**Drive** as one side, or **Check** (watch only). This guide is enough to write a new protocol; the exact rules are in
`docs/SEMANTICS.md` (rule numbers in brackets). Worked specs: `spec/uart_8n1.py` (timing grid), `spec/spi.py`
(reactive target, full duplex), `spec/i2c.py` (shared open-drain bus, choices, clock stretching).

## 1. The model in one paragraph

A spec is a timed automaton. **Locations** are the protocol's states. **Clocks** (up to 3, 16 bits, counting cycles of
the 48 MHz system clock) measure time since you reset them. **Edges** move between locations; an edge has up to three
guards that must all hold — a pin pattern, a clock window, a data condition — and an action (drive pins, one datapath
op, reset clocks). An edge fires on the **first cycle** its guards hold, and the lowest-numbered edge wins (R3.1, R3.2).
A location can **watch** pins: a watched pin that changes when no edge is enabled is a violation (UNEXPECTED); a location
**invariant** `x ≤ hi` that runs out with no edge enabled is a TIMEOUT (R6).

## 2. Skeleton

```python
from spex.dsl import DATA, OD, Op, Spec, bitcnt_eq, bitcnt_lt, txf_ne

def myproto(T=417, d=8):
    s = Spec("myproto", sides=["tx", "rx"], pins={"TX": 0}, clocks=["g"], msb_first=False)
    IDLE = s.loc("IDLE", watch=["TX"])                      # first location = initial
    ...
    s.resync(IDLE)                                          # where Check goes after a violation (R6.5)
    return s
```

Rules the compiler enforces (it tells you which one you broke):
- every location has an outgoing edge or is `halt=True` (R3.4);
- at most 4 edges leave a location after the role expansion of §4 (R2.2); I2C needed careful merging to stay under;
- the resync location has no clock guard and no invariant (R7.7) — make it an idle state;
- at most 64 locations, 16 windows, 7 pin patterns, 8 constants, 16 actions per role (R11). `compile_spec(...).listing`
  ends with a "table use" line; check it as you go.

## 3. Three kinds of edge

| Kind | Write it as | Use it for |
|---|---|---|
| **emit** | `s.emit(src, dst, side, {pin: value}, ...)` | something one side *does* to the wires |
| **observe** | `s.observe(src, dst, {pin: value}, ...)` | a line event you only see (e.g. SCL rising after a release, which either side may delay) |
| **internal** | `s.internal(src, dst, after=window, ...)` | a pure time step: grid ticks, phase changes, loops |

An emit has an owner side. When the chip plays that side (Drive), the emit drives the pins; when it does not (Drive as
the other side, or Check), the compiler turns the emit into an observation of the same change (R7.4). That is how one
spec gives every role. Values are line levels: `0`, `1`, or `DATA` (from the shift register). Mode `PP` drives both
levels; `OD` (open drain) pulls low for 0 and releases for 1.

Emits come in three flavours:
- **timed**: `at=window` — fires at a policy-chosen time inside the window (nominal / earliest / latest / random / sweep);
- **reactive**: `on={pin: value}` (+ optional `within=window`) — fires on a line event, e.g. "drive MISO on SCK fall";
- **data-triggered**: `data=txf_ne()` or `token=k` only — fires when the host has supplied data or a decision.

## 4. Time: windows are in line time

Write every window as the time **between events on the wires**, in cycles. The compiler corrects for the chip's own
pipeline in Drive (an own output appears on the line 1 cycle after the decision; an input is seen 2 cycles after it
changes; D = 3 by default, R7.7). Two consequences you must respect:
- a reaction cannot be faster than the chip: an emit timed relative to an observed event needs `hi ≥ D`;
- **a clock reset must happen on an event both sides can see.** Reset clocks on emits that always change the line
  (a start bit, an SCL edge) or on internal edges, never on an emit that might not change the line (a data bit equal to
  the previous one) or that only releases an open-drain line. The compiler rejects that (R7.4 visibility).

**The grid pattern (UART).** When a side sends bits on a fixed rate, do not chain windows from bit to bit: a "latest"
transmitter would drift a little further every bit, and a data bit that does not change the line gives the observer no
edge to re-sync on. Instead reset a clock once (start bit), then use **internal ticks** at fixed times that open a short
window around each nominal boundary; the data emit goes inside the window and resets nothing. See `spec/uart_8n1.py`.

**Long waits (> 65,535 cycles = 1.37 ms).** Clocks are 16 bits. Write a **counted loop** (SEMANTICS §1a): clear `bitcnt`
on entry, loop `k − 1` times on an internal edge `after=L` with `op=Op("INC")` and `data=bitcnt_lt(k−1)`, and put the
real window on the exit edge with `data=bitcnt_eq(k−1)`. The compiler error for an over-long window says exactly this.
`bitcnt` is shared with the shift register, so a loop and a byte transfer cannot overlap.

## 5. Watching pins

Watch every pin whose change would be wrong in that location; leave a pin unwatched where it may change freely (SDA while
SCL is low; MOSI and MISO just after a shift edge). A change on an unwatched pin is ignored unless an edge uses it.
Typical layout per bit of a clocked protocol:

| location | what may change | watch |
|---|---|---|
| change zone, right after the shift edge | data lines | clock, chip select |
| stable zone, before the sampling edge | nothing | everything |

The split between the zones is an internal edge at the protocol's output-valid time; see `spec/spi.py`.

## 6. Choices: tokens in Drive, observation in Check

When a side decides something the wires cannot predict (another byte, STOP, repeated START, ACK or NACK), write one emit
per alternative with `token=k`. In Drive the host supplies the token stream; in Check the tokens are dropped and the
**first visible difference** decides — so the alternatives must differ in what they do to the line *at that edge*
(the compiler checks this, R7.8). If the side must prepare the line before the decision becomes visible (I2C sets SDA
while SCL is low, and only the SDA change while SCL is high is STOP or repeated START), put the preparation in an emit that
does not need the token and branch on the token at the edge where the difference shows (`spec/i2c.py`, location CB).

## 7. The four observer options (shared buses)

These change only how *observers* (Check, or the other side's Drive) compile an emit. Use them when the obvious form
would be wrong on a shared, open-drain bus.

| Option | Use when | Example |
|---|---|---|
| `cond={pin: v}` | the event only counts while another line has a level | STOP = SDA rises **while SCL is high**: `emit(..., {"SDA": 1}, cond={"SCL": 1})` |
| `silent=True` | two devices hand a line over inside one window, so the line may glitch; judge it only when the window closes | after an I2C ACK the target releases SDA and the controller sets the next bit: both emits in that low phase are silent |
| `visible=True` | an open-drain *release* is in fact observable because nobody else can hold the line then | the STOP release of SDA |
| `shadow=True` | a side reacts on another side's edge; observers already see that edge | the target releasing SDA as the controller pulls SCL low after an ACK |

A silent emit may not reset clocks. A shadow emit must sit next to the other side's emit with the same window and target.

## 8. Testing a new spec (required)

1. Write or reuse a **standards-derived oracle** in `tests/oracles/` that never imports `spec/` or `spex/` — from the
   protocol's standard only. Give it planted-fault tests it must reject.
2. Drive test: compile `role="drive"`, run on `spex.refsim` against an oracle-side bus model; the oracle must accept.
3. Check test: oracle-generated legal traffic gives zero violations; at least 5 planted faults give the right kind at
   the right cycle (a pad change in cycle t is seen in cycle t + 2).
4. Run the metamorphic tests' pattern on it (Drive trace passes Check; `scale_time` if all its timing is clock-triggered).
5. Note its table use and longest window (`python3 -B scripts/table_usage.py`).

## 9. Compile errors you will meet

| Error says | Usually means | Fix |
|---|---|---|
| not observably deterministic | two edges of one location accept the same observation | make patterns, windows (allow 2 cycles of age) or data guards disjoint, or mark the fallback `otherwise=True` |
| choice alternatives are not distinguishable | the token is the only difference | move the branch to the edge where the line differs (§6) |
| > 4 edges after role expansion | a DATA emit becomes 3 observer edges | split the location, or merge equivalent observer edges (same target and action) |
| needs lo ≥ 2 / ≥ 4 | a timed edge too soon after entering the location | the chip needs E + 1 cycles (more after a pin-triggered reset); widen or shift the window |
| may be silent, so it may not reset a clock / writes no visible pin | §4 visibility | reset on a visible event or an internal tick |
| time base ... ambiguous | a clock is reset by own emits on one path and by observations on another | reset it on every incoming path from the same kind of event |
| exceeds the 16-bit clock | a window over 65,535 cycles | counted loop (§4) |
| more than N windows / constants / actions | table full | share windows (equal bounds share an entry), reuse constants, merge actions |
