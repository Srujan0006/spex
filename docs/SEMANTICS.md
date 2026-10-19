# SPEX cycle semantics (normative)

Status: **DRAFT, version 0**. Seeded from proposal rev 2.1.

The week-1 task is to turn every rule into exact, testable text, resolve the OPEN items, and set version 1.

Rule tags:
- **FROZEN**: change only through `DECISIONS.md`.
- **OPEN**: decide in week 1 and record the decision.

## 1. Time and clocks

- **FROZEN.** Time is integer: one step per system clock cycle (target 48 MHz).
- **FROZEN.** Each engine has 3 clocks, x0..x2, 20 bits wide. They increment every cycle and are reset only by edge actions.
- **OPEN.** Per-clock prescaler: is it needed for slow protocols, or are 20 bits at 48 MHz enough (21.8 ms)?
- **OPEN.** Clock overflow: saturate or wrap? A wrap must never make a guard true by accident.
- **FROZEN.** Guards use closed comparisons only (≥, ≤, closed windows). This keeps the integer-time behaviour a faithful digitisation of the dense-time automaton (Henzinger, Manna & Pnueli, 1992).

## 2. Automaton structure

- **FROZEN.** Up to 64 locations per engine. *Status: [Estimate]; must be confirmed by counting the I2C spec in week 2.*
- **FROZEN.** Up to 4 outgoing edges per location. The compiler splits larger fan-out into a chain and reports the cost.
- **FROZEN.** Edge guard = pin guard ∧ clock guard ∧ data guard. The three are independent fields; any one may be "none".
  - **Pin guard**: pattern {mask, value, mode ∈ {level, into-match}}.
  - **Clock guard**: none / x ≥ lo / lo ≤ x ≤ hi / fire at policy time in [lo, hi].
  - **Data guard**: none / bitcnt == k / bitcnt < k / shift-register match / event / TX FIFO non-empty / host choice token == k.
- **FROZEN.** Location word = invariant {enable, window} + **watch mask** (8 bits).
- **FROZEN.** Actions: pin writes (value or drive-enable; drive-enable gives open drain), one datapath op, clock resets, emit event, cover enable.

## 3. Firing

- **FROZEN.** Urgent semantics: an edge fires on the first cycle its guard holds.
- **FROZEN.** Priority: if several edges are enabled, the lowest index fires.
- **FROZEN.** Both rules are refinements of the automaton's nondeterminism. Model checking the nondeterministic spec therefore covers every policy and every priority order.
- **OPEN.** Is a location with no outgoing edge an error, or "halt"? Proposal: halt state is explicit, and the compiler rejects anything else.

## 4. Pipeline and latency

- **FROZEN.** Pins go through a 2-flop synchroniser.
- **FROZEN.** Location entry costs E = 1 cycle: the new location's 4 edges are read from 2 parallel 64-bit macros.
- **FROZEN.** Reaction latency for a pin-triggered edge is L = 3 cycles from the pad change. It is L + E if the change lands in the entry cycle. The change is held, never lost.
- **FROZEN.** Clock-triggered edges fire on the exact cycle, provided lo ≥ E + 1. The compiler checks this.
- **OPEN.** Define "pad change in cycle n" precisely: which edge counts as cycle n. Copy DTC's convention (cycle n = the interval after rising edge n).

## 5. Pin events, ages, carry-over (rev 2.1)

- **FROZEN.** Changed pins are tracked with an age: 0 = seen this cycle, 1 = seen in the entry cycle, 2 = carried over from the previous location.
- **FROZEN.** A fired edge **consumes** only the pins named by its own pin guard (`tmask`). Every other change seen in that cycle is carried into the target location and judged there (age 2).
- **FROZEN.** Timestamp of a fired edge = x − age for the pins in `tmask`, otherwise x. Offsets saturate at the location-entry instant.
- **FROZEN.** Ordering of same-cycle changes is "fired edge first, then the rest". Which of two same-sample changes truly came first is not knowable; this is a documented limit.

## 6. Violations (Check role)

- **FROZEN.** **UNEXPECTED**: a pin in the location's watch mask changed (any age) and no edge is enabled.
- **FROZEN.** **TIMEOUT**: the location invariant is exceeded and no edge is enabled.
- **FROZEN.** Each violation writes {timestamp, engine, location, pins, kind} to the trace.
- **OPEN.** After a violation, does the monitor stop, resynchronise to a declared idle location, or continue? Proposal: go to the spec's declared resync location and count violations.

## 7. Roles (compile-time transformations of one spec)

- **FROZEN.** Each action is tagged with the side that owns it. The role picks the side the chip plays.
  - **Drive**: own-side actions drive pins. Other-side actions become observations (pin guards).
  - **Check**: everything is an observation; nothing drives.
  - **Stress**: Drive, with policy ≠ nominal.
  - **Cover**: any role, with cover enabled.
- **FROZEN.** **Choice points**: nondeterministic branches tagged with tokens.
  - In Drive they are guarded by "host token == k" and pop the token.
  - In Check the token guard is dropped and the observation decides.
  - The alternatives must be distinguishable by observation; the compiler checks this.
- **FROZEN.** Check needs **observable determinism**: no two edges from one location accept the same observation. The compiler rejects specs that break it.

## 8. Timing policies (Drive / Stress)

- **FROZEN.** For "fire at policy time in [lo, hi]" edges, the fire time is fixed at location entry:
  - nominal: a declared constant;
  - earliest: lo;
  - latest: hi;
  - random: LFSR, power-of-two masked, then folded into the window;
  - sweep: lo + k·step, clipped at hi.
- **OPEN.** Is the random distribution's bias acceptable? Document it; at minimum, test that every value in [lo, hi] is reachable.

## 9. Coverage record

- **FROZEN.** One 32-bit word per edge:
  - `[31:24]` saturating hit count;
  - `[23:12]` minimum offset;
  - `[11:0]` maximum offset.
  - Offsets are measured from the edge's window lower bound, in units of 2^s cycles, with s chosen per spec by the compiler.
- **FROZEN.** Updates go through a dual-port macro (pipelined read-modify-write) and never stall an engine. A 4-entry queue sits in front, with a sticky `COV_LOST` flag. Coverage counts as complete only when `COV_LOST` = 0.

## 10. Events between engines

- **FROZEN.** 8 broadcast event lines. An action emits for one cycle; a data guard "event j" sees it the next cycle.
- **OPEN.** Model events as UPPAAL-style broadcast channels in the TChecker export. Check that a one-cycle delay is representable.

## 11. Table formats

- **FROZEN (fields), OPEN (exact bit positions until v1).** The edge word is 32 bits, as in proposal §3.3 rev 2, with independent guard fields.
- **OPEN.** Width of the action table, window table and constant table, and whether they live in flops or in macro spare columns.

## 12. Reset and loading

- **FROZEN.** All control state is reset by `rst_n`. Tables and macros are not reset; reading an unwritten entry is a testbench error, as in DTC D13.
- **FROZEN.** Tables are written by the host only while the engine is stopped.
- **OPEN.** Host SPI frame format. Reuse DTC's config-port plan and specify it as a SPEX spec (dogfooding).
