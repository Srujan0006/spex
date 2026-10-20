# SPEX cycle semantics (normative)

Status: **version 1 (final)**, 2026-10-19. Supersedes draft v0 (seeded from proposal rev 2.1). The owner approved the FROZEN\* refinements (S20, S21, S25, S28, S31, S34, S35) on 2026-10-19.

Rule tags:
- **FROZEN**: change only through `DECISIONS.md`.
- **FROZEN\*** : a FROZEN rule of v0 that v1 made exact in a way that changed or extended its v0 wording. Each one names its decision (S-id); all were approved by the owner on 2026-10-19 and are now FROZEN like the rest.
- **DECIDED**: a v0 OPEN item, decided in v1 (S-id given).
- **DEFERRED (date)**: still open, not needed before that date.
- **DERIVED**: a consequence of the rules above it; stated so tests can check it. If a DERIVED statement and a rule disagree, the rule wins and the DERIVED text is a bug.

Rule numbers (R1.1, R3.2, ...) are stable. Tests cite them.

Section 13 has the worked cycle-by-cycle examples. Section 14 lists every change from v0.

---

## 0. Conventions and notation

- **R0.1 DECIDED (S17).** *Cycle n* is the interval after rising edge n of the system clock, as in DTC. Cycle 0 is the first cycle after `rst_n` is released. `S_n` is the register state during cycle n.
- **R0.2 DECIDED (S17).** The model call `step(pads_in, host_op)` is one rising edge: it reads `S_n`, the pad inputs during cycle n (`pad[n]`) and the host operation of cycle n, and computes `S_{n+1}`. Two-phase update: every new value is a function of `S_n` and the inputs of cycle n only.
- **R0.3 DECIDED (S17).** `outputs()` in cycle n is a pure function of `S_n`. An action of an edge that fires in cycle n is therefore visible on the pads from cycle n+1.
- **R0.4 DECIDED (S17).** A *pad change in cycle n* means `pad[n] ≠ pad[n−1]` for that pin.
- **R0.5.** SPEX has 8 chip pins, numbered 0..7. Each has an input `pad_in[p]`, an output value `out[p]` and an output enable `oe[p]`. The mapping to Tiny Tapeout pins is an RTL detail (DEFERRED 2026-11-14). The *line* is the electrical value on the pin; tests model it with a bus model (push-pull or wired-AND with pull-up).
- **R0.6.** Notation: `P_n` = pin bus in cycle n (§4). `x_c` = clock c. `chg_n = P_n XOR P_{n−1}`. A *mask* is an 8-bit set of pins. `min ∅ = 0`.

## 1. Time and clocks

- **R1.1 FROZEN.** Time is integer: one step per system clock cycle (target 48 MHz).
- **R1.2 FROZEN.** Each engine has 3 clocks, x0..x2, 20 bits wide. They increment every cycle and are reset only by edge firings (R3.6), by engine start (R12.4) and by violation resync (R6.5).
- **R1.3 DECIDED (S18).** No prescaler in v1. 20 bits at 48 MHz is 21.8 ms [Estimate: 2^20 / 48e6], enough for UART down to 300 baud (160,000 cycles per bit), I2C at 100 kHz and SPI. Revisit by 2026-11-14 if a held-out protocol needs a guard longer than 2^20 − 1 cycles (for example the SMBus 25-35 ms timeout).
- **R1.4 DECIDED (S19).** Clocks **saturate** at `XMAX = 2^20 − 1`; they never wrap. A saturated clock makes `x ≥ lo` stay true and `x ≤ hi` stay false, so overflow can never make a window guard true by accident. Timestamps taken from a saturated clock are reported as `XMAX − a` and are flagged inexact by the host library.
- **R1.5 FROZEN.** Guards use closed comparisons only (≥, ≤, closed windows). This keeps the integer-time behaviour a faithful digitisation of the dense-time automaton (Henzinger, Manna & Pnueli, 1992).
- **R1.6 FROZEN\* (S20). Reset value.** A clock is reset *at an instant*: when an edge fires in cycle n with trigger age `a` (R5.4), each clock in its reset mask is written so that `x_c = 0` at cycle `n − a`, the cycle in which its triggering event appeared on the pin bus. In registers: `x_c(S_{n+1}) = 1 + a`. For an edge with no triggering pin change, `a = 0` and `x_c(S_{n+1}) = 1`.
  - Consequence (DERIVED): without further resets, `x_c(S_k) = min(k − (n − a), XMAX)` for k > n.
  - Why: v0 left the reset instant undefined. Resetting at the event, not at the later firing cycle, keeps observer clocks exact when the event arrives in an entry cycle or is carried over (it is the S8 age idea applied to resets). Without it the Check role would drift by up to 2 cycles per hop and the Drive→Check duality test fails for tight windows.

## 2. Automaton structure

- **R2.1 FROZEN.** Up to 64 locations per engine. *Status: [Estimate]; confirmed or not by counting the I2C spec (S15, week 2).*
- **R2.2 FROZEN.** Up to 4 outgoing edges per location, in slots 0..3. The compiler splits larger fan-out into a chain and reports the cost (R7.12).
- **R2.3 FROZEN.** Edge guard = pin guard ∧ clock guard ∧ data guard. The three are independent fields; any one may be "none". An edge is *enabled* in an evaluation cycle iff its `valid` bit is set and all three guards hold (R3.3).
- **R2.4 FROZEN\* (S34). Pin guard.** A pattern `{mask, value, mode}`; pattern index 0 means "none" (always true, `tmask = 0`). With `M = mask`:
  - `LEVEL`: holds iff `(P_n & M) == (value & M)`.
  - `EDGE` (v0's "into-match"): holds iff `(P_n & M) == (value & M)` **and** at least one pin of M has a pending change (R5.2) this evaluation cycle. That is: the pattern holds now and one of its pins is the event that made it hold.
  - `tmask = M` for both modes. The pins of `tmask` are the edge's *trigger pins*: they give its age (R5.4) and are consumed when it fires (R5.5).
  - Why marked: v0 named "into-match" without defining it. A literal "was false, is now true" needs a stored previous value per pattern; the pending-change form needs nothing beyond R5 and also covers a pattern made true by a carried-over change. The difference: a pin that toggles twice inside the pending window (0→1→0 seen as two changes while the pattern wants 0) satisfies EDGE here. Documented limit.
- **R2.5 FROZEN. Clock guard** (2-bit kind, plus a window `w = {clock c, lo, hi, nom}`):
  - `NONE`: true.
  - `GE`: `v ≥ lo`.
  - `WIN`: `lo ≤ v ≤ hi`.
  - `POLICY` ("fire at policy time in [lo, hi]"): `t_e ≤ v ≤ hi`, where `t_e` is the fire time latched for this edge at location entry (§8).
  - **FROZEN\* (S21).** `v` is the guard clock *at the edge's trigger instant*: `v = max(x_c − a_e, 0)`, with `a_e` the edge's trigger age (R5.4). For an edge with no pending trigger-pin change, `a_e = 0` and `v = x_c`. v0 compared the current `x_c`; for a pin-triggered edge that sees an event late (entry cycle or carry-over) that judges the event up to 2 cycles late and can reject a legal event that happened at `hi` (example 13.3, case c6).
- **R2.6 FROZEN. Data guard** (3-bit kind, plus a 3-bit index k into the constant table `K`, or an event index):

  | code | kind | holds iff |
  |---|---|---|
  | 0 | NONE | true |
  | 1 | BITCNT_EQ | `bitcnt == K[k][7:0]` |
  | 2 | BITCNT_LT | `bitcnt < K[k][7:0]` |
  | 3 | SR_MATCH | `(SR & K[k][15:8]) == (K[k][7:0] & K[k][15:8])` |
  | 4 | EVENT | event k is pending for this engine (R10.2) |
  | 5 | TXF_NE | TX FIFO not empty |
  | 6 | TOKEN | token FIFO not empty and its head `== K[k][7:0]` (does **not** pop; see R7.10) |
  | 7 | SR_NOMATCH | negation of SR_MATCH with the same k (DECIDED, S33) |

  Data guards read `S_n` (the current cycle), not the trigger instant.
- **R2.7 FROZEN.** Location word = halt bit + invariant `{enable, window index}` + **watch mask** (8 bits). The invariant is `x_c ≤ hi` of the named window, on the current clock value (not a trigger instant). (The halt bit is DECIDED, S23.)
- **R2.8 FROZEN.** Actions: pin writes, one datapath op, emit event, token pop (S31). Clock resets live in the edge word's reset mask, not in the action (S28). Cover enable lives in the edge word's log/cover bit.
- **R2.9 DECIDED (S32). Pin writes** use *line values*. An action names a pin mask `Wm`, a value `Wv`, and a mode:
  - `PP` (push-pull): for p in Wm, `out[p] := Wv[p]`, `oe[p] := 1`.
  - `OD` (open drain): for p in Wm, `out[p] := 0`, `oe[p] := NOT Wv[p]` (value 0 pulls low, value 1 releases).
  - If the action's datapath op drives a data pin d (SHOUT, PEEK, LOAD_PEEK, PUSH_LOAD_PEEK; §2.10), `Wv[d]` is replaced by the data bit, then the mode applies.
  - The write takes effect in `S_{n+1}` (R0.3). Pins not in Wm keep `out`, `oe`.
- **R2.10 DECIDED (S33). Datapath (per engine).** `SR` 8 bits, `bitcnt` 0..63 saturating, TX FIFO, RX FIFO (bytes), token FIFO (bytes). Bit order is an engine configuration bit `msb_first` (from the spec). The *out-bit* is `SR[7]` if `msb_first` else `SR[0]`. Shifting in bit b: `SR := ((SR << 1) | b) & 0xFF` if msb_first, else `(SR >> 1) | (b << 7)`. Shifting out: same with b = 1 (the vacated bit fills with 1, the idle level of UART). `d` is the action's data-pin field. Ops (4-bit code):

  | code | op | effect (all on S_{n+1}) |
  |---|---|---|
  | 0 | NOP | |
  | 1 | LOAD | `SR := TX.pop()`, `bitcnt := 0`. Empty FIFO: `SR := 0xFF`, sticky `TX_UNDERFLOW`. |
  | 2 | PUSH | `RX.push(SR)`, `bitcnt := 0`. Full FIFO: byte dropped, sticky `RX_OVERFLOW`. |
  | 3 | LOAD_PUSH | PUSH then LOAD, in that order (full-duplex byte boundary) |
  | 4 | SHIN | shift in `P_n[d]`, `bitcnt += 1` |
  | 5 | SHOUT | pin d := out-bit (R2.9), then shift out, `bitcnt += 1` |
  | 6 | PEEK | pin d := out-bit; SR and bitcnt unchanged |
  | 7 | LOAD_PEEK | LOAD, then pin d := out-bit of the *new* SR |
  | 8 | CLR | `bitcnt := 0` |
  | 9 | PUSH_LOAD_PEEK | PUSH, then LOAD, then pin d := out-bit of the new SR (full-duplex byte boundary of an SPI target; S38) |
  | 10-15 | reserved | CRC ops (DEFERRED 2026-11-30); executing a reserved op is a compile error and a NOP in the model |

## 3. Firing (the evaluation algorithm)

- **R3.1 FROZEN.** Urgent semantics: an edge fires in the first evaluation cycle in which it is enabled.
- **R3.2 FROZEN.** Priority: if several edges are enabled, the lowest slot fires. At most one edge fires per engine per cycle.
- **R3.3 FROZEN.** Both rules are refinements of the automaton's nondeterminism. Model checking the nondeterministic spec therefore covers every policy and every priority order. (The exception is *otherwise* edges, R7.9, whose guard includes "no lower slot enabled"; the TChecker export encodes that explicitly.)
- **R3.4 DECIDED (S23). Halt.** A location with the halt bit set is a halt location. Entering it puts the engine in state `HALTED`: no evaluation, no violations, clocks keep counting, outputs hold. Only the host leaves `HALTED` (R12.4). The compiler rejects any location with no valid outgoing edge that is not declared halt.
- **R3.5 Engine phases.** A running engine is in phase `ENTRY` or `EVAL`. A firing (or start, or resync) in cycle n puts it in `ENTRY` in cycle n+1 and `EVAL` from cycle n+2. The first `EVAL` cycle after an entry is the *first evaluation cycle*.
- **R3.6 Normative step.** For one engine in cycle n (all reads from `S_n`, all writes to `S_{n+1}`; a field not written keeps its value; every clock not reset does `x := min(x + 1, XMAX)`):

  ```
  if state != RUNNING: (clocks count; nothing else)
  elif phase == ENTRY:
      pend1'   = chg_n                     # changes seen in the entry cycle (age 1 next cycle)
      pend2'   = pend2                     # carried-over changes (age 2 next cycle)
      pev'     = pev | ev_n                # events, R10.2
      t_e'     = policy_time(e) for each POLICY edge e of loc   (§8, LFSR value of S_n)
      phase'   = EVAL; first' = 1
  else:  # EVAL
      age0 = chg_n; age1 = pend1 if first else 0; age2 = pend2 if first else 0
      pend = age0 | age1 | age2
      evs  = pev | ev_n
      for slot i in 0..3: compute a_i (R5.4), v_i (R2.5), enabled_i (R2.3)
      if some slot enabled:  fire the lowest enabled slot e (R3.7)
      else:                  check violations (R6.1-R6.5); if none: drop pend (pend1' = pend2' = 0), pev' = 0
      first' = 0
  ```
- **R3.7 Firing edge e in cycle n** writes, in `S_{n+1}`:
  - pin writes and the datapath op of its action (R2.9, R2.10); token pop if the action says so (R7.10); event emit (R10.1);
  - for each clock in its reset mask: `x := 1 + a_e` (R1.6);
  - carry-over: `pend2' = pend & ~tmask_e`, `pend1' = 0`; `pev' = evs` minus the event its data guard consumed (R10.2);
  - `loc' = target`; if the target is a halt location, `state' = HALTED`, else `phase' = ENTRY`;
  - coverage update (§9) if the edge's log/cover bit and the engine's cover enable are set;
  - trace record `EDGE` (R6.4) if the edge's log/cover bit and the engine's trace enable are set;
  - if the edge's error bit is set: a violation record of kind `SPEC_ERROR` and the violation counter increments (R6.3); the edge still fires normally (no resync).

## 4. Pipeline and latency

- **R4.1 FROZEN.** Pins go through a 2-flop synchroniser: `sync1(S_{n+1}) = pad[n]`, `sync2(S_{n+1}) = sync1(S_n)`. The pin bus is `P_n = sync2(S_n) = pad[n−2]`. Both flops reset to 0.
- **R4.2 FROZEN.** Location entry costs E = 1 cycle: the new location's 4 edges are read from 2 parallel 64-bit macros. The entry cycle evaluates no edge.
- **R4.3 DECIDED (S17).** A pad change in cycle n (R0.4) appears as `chg_{n+2}` on the pin bus.
- **R4.4 FROZEN\* (S35). Reaction latency.** For an edge that fires on a pin change and drives a pin, the latency from the pad change to the output change is `L + d` cycles, with L = 3 (2 synchroniser + 1 output register) and `d = f − s`, where s is the cycle the change appears on the pin bus and f the cycle the edge fires:
  - d = 0 if s is an evaluation cycle (latency 3);
  - d = 1 (= E) if s is an entry cycle (latency 4);
  - **d = 2 if s is the firing cycle of the previous location's edge and the change is carried over (latency 5).** v0 said "L, or L + E"; that predates carry-over (S7) and misses this case.
  - d grows by 2 more for each further carry (a location that fires in its first evaluation cycle without consuming the change). The compiler lists locations that can fire in their first evaluation cycle (R7.13), so the worst case per spec is known.
  - The change is held, never lost (R5).
- **R4.5 FROZEN\* (S20). Exact clock-triggered edges.** A clock-triggered edge (clock guard GE or POLICY, no trigger pin) whose clock is reset by every incoming edge fires on the exact cycle `v = lo` (GE) or `v = t_e` (POLICY) provided:
  - `lo ≥ E + 1 = 2` if every incoming edge that resets the clock has no trigger pin (its reset gives `x = 1` in the entry cycle and `x = 2` in the first evaluation cycle);
  - `lo ≥ E + 3 = 4` if some incoming edge that resets the clock has a trigger pin (with R1.6, `x` can be up to 4 in the first evaluation cycle).
  The compiler checks this (R7.12). v0 stated only `lo ≥ E + 1`; with R1.6 that is the bound for the first case only.

## 5. Pin events, ages, carry-over

- **R5.1 FROZEN.** Changed pins are tracked with an age: 0 = seen in this cycle, 1 = seen in the entry cycle, 2 = carried over from the previous location.
- **R5.2 DECIDED (S22). Pending changes.** In an evaluation cycle n the pending set is `pend = age0 | age1 | age2` (R3.6). Ages 1 and 2 exist only in the first evaluation cycle. The per-pin age is the smallest age at which that pin appears (a pin can be in more than one age mask).
- **R5.3 DERIVED.** Every change on the pin bus is judged in exactly one evaluation cycle of the location it was seen in, or of the next location if it is carried. A change is never lost and never judged twice, except that a carried change can be carried again (R5.6).
- **R5.4 DECIDED (S22). Trigger age.** For edge e, `a_e = min{age(p) : p ∈ pend ∩ tmask_e}`, or 0 if that set is empty. It is the age of the *latest* trigger-pin change, the one that completed the pattern.
- **R5.5 FROZEN.** A fired edge **consumes** only `pend ∩ tmask`. Every other pending change of that cycle is carried into the target location (`pend2`) and judged there in its first evaluation cycle with age 2.
- **R5.6 FROZEN.** Timestamp of a fired edge: `τ_e = n − a_e` (global cycle, pin-bus time) and `ts_e = v_e` on the edge's timestamp clock (R2.5; the window's clock, or x0 with lo = 0 if the clock guard is NONE). Offsets saturate at the location-entry instant: a change carried a second time keeps age 2, so it is stamped at the entry instant (the firing cycle of the edge that entered the location), up to 2 cycles later per extra carry than it happened.
- **R5.8 DERIVED. Precision near internal edges.** A change seen in the firing cycle of an edge that does not consume it, or in the target's entry cycle, is judged in the target's first evaluation cycle (R5.5, R5.1). Window guards there use the trigger instant (R2.5), so early events are still rejected exactly; but a target location *without* a clock guard (for example a resync/idle location) accepts a change that arrived up to 2 cycles before it was entered. Example: the UART Check accepts a stop bit up to 2 cycles shorter than `T − d` (test `test_known_limit_short_stop_within_2_cycles_is_accepted`).
- **R5.7 FROZEN.** Ordering of same-cycle changes is "fired edge first, then the rest". Which of two same-sample changes truly came first is not knowable; this is a documented limit.

## 6. Violations

- **R6.1 FROZEN. UNEXPECTED.** In an evaluation cycle with no enabled edge: `U = pend & watch ≠ 0`.
- **R6.2 FROZEN. TIMEOUT.** In an evaluation cycle with no enabled edge: the invariant is enabled and `x_c > hi` (current clock value, R2.7).
- **R6.3 DECIDED (S25).** If either holds, one violation is raised: `kind` is a bit set (`UNEXPECTED` = 1, `TIMEOUT` = 2, `SPEC_ERROR` = 4; both of the first two can be set in one record). The engine's violation counter (16 bits, saturating) increments and the sticky flag `VIOL` is set.
- **R6.4 FROZEN\* (S25). Trace records.** Each record is `{type, cycle, engine, loc, slot, kind, pins, value, ts}`:
  - `cycle`: 32-bit global cycle (wrapping) of the event in pin-bus time. EDGE: `τ_e`. UNEXPECTED: `n − max age over U`. TIMEOUT only: n.
  - `loc`, `slot`: the location evaluated and the fired slot (7 for a violation).
  - `pins`: EDGE: `pend ∩ tmask` (consumed); UNEXPECTED: U; TIMEOUT: 0.
  - `value`: `P_n`. `ts`: EDGE: `ts_e`; violation: the invariant clock value.
  - v0 listed `{timestamp, engine, location, pins, kind}`; v1 adds slot, value and ts and fixes the time base. Pad time = `cycle − 2`.
  - Trace FIFO depth is a parameter (model default 64; RTL size DEFERRED 2026-11-14). A record that does not fit is dropped and sets sticky `TRACE_LOST`.
- **R6.5 DECIDED (S24). After a violation** in cycle n:
  - if the spec declares a resync location R: `loc' = R`, `phase' = ENTRY`, every clock `x := 1` (0 at cycle n), `pend1' = pend2' = 0`, `pev' = 0`, `bitcnt := 0`, and the spec's resync action (an action-table index, may be the empty action) is applied as if by a firing edge. The offending change is dropped, not carried.
  - otherwise: `state' = HALTED`.
  - The rule is the same in every role. In Drive, a violation means the other side (or the host, for a starved token FIFO) broke the spec.
- **R6.6 DERIVED.** Pins outside the watch mask never cause a violation; their changes are dropped at the end of the evaluation cycle unless an edge fires (then they are carried).

## 7. Roles (compile-time transformations of one spec)

- **R7.1 FROZEN.** Each action is tagged with the side that owns it. The role picks the side the chip plays.
  - **Drive** (side S): S's actions drive pins. Other sides' actions become observations.
  - **Check**: everything is an observation; nothing drives. The engine's `drive_en` configuration bit is 0, which forces `oe = 0` regardless of the tables.
  - **Stress**: Drive, with policy ≠ nominal.
  - **Cover**: any role, with cover enabled.
- **R7.2 DECIDED (S30). Spec edge classes.** In the DSL each edge is one of:
  - *emit by side s*: writes pins owned by s. It is timed (clock guard POLICY on a window), reactive (an EDGE pin guard, no POLICY), or data-triggered (TXF_NE or TOKEN only);
  - *observe*: a pin guard on the line, with an optional window; no pin writes; no owner;
  - *internal*: no pin guard and no pin writes (clock or data guard only).
- **R7.3 DECIDED (S30). Own emits** (owner = the chip's side, Drive role): compiled as written. Token guards are kept (R7.10).
- **R7.4 DECIDED (S30). Observed emits** (owner ≠ the chip's side, or any emit in Check). Pin writes are removed, token guards and data guards on the owner's private state (TXF_NE, TOKEN) are dropped, `POLICY` becomes `WIN` on the same window, and datapath ops are mapped: `SHOUT d → SHIN d`, `LOAD → CLR`, `LOAD_PUSH → PUSH`, `PEEK → NOP`, `LOAD_PEEK → CLR`, `PUSH_LOAD_PEEK → PUSH`. The written pins are split:
  - *visible* pins: PP writes, and OD writes of value 0 (pull low);
  - *invisible*: OD writes of value 1 (release). Another device may hold the line low, so a release is not an observation.

  The edge then becomes:
  - **visible, constant values** → `e1`: `EDGE {visible pins, written values}`, `WIN w`.
  - **visible, one data pin d** (value from SR) → `e1a`, `e1b`: as e1 with `d = 0` and `d = 1`. More than one data pin per edge is a compile error.
  - **silent completion** `e2` (*otherwise*, R7.9), only if the edge resets no clock: `LEVEL {constant visible pins, values}` (or no pin guard if only a data pin is visible), `WIN [hi, hi]`, same target and mapped actions. It fires when the window closes with no observed change, which is what an emit of the value already on the line looks like.
  - **no visible pin** → an internal edge with `GE lo`.
  - **reactive emit** (an EDGE trigger, R7.2) → an observe edge on its trigger pattern (and window, as WIN); its writes are dropped. The written pins' later change is not judged by this edge; a spec that wants it judged writes an observe edge for it (S37).
  - A data pin counts as visible in either write mode: an OD data bit 0 pulls low and 1 releases, and while one side transmits nobody else drives the line (S37).
  - **Visibility rule (compile error otherwise):** an observed emit that resets a clock must have a visible pin and must not need e2. The spec asserts that the line changes. If it does not, the observer reports TIMEOUT or UNEXPECTED, which is a true finding. Reason: a silent emit's instant is unknowable, so a clock reset on it would be guessed.
- **R7.5 DECIDED (S30). Observe and internal edges** are compiled unchanged in every role, apart from R7.7.
- **R7.6 DECIDED (S30). Watch masks.** In Drive as S, pins that S drives push-pull anywhere in the spec are removed from every watch mask (the chip does not check itself). Open-drain pins stay watched as written.
- **R7.7 DECIDED (S30). Time-base compensation (Drive only).** Spec windows are written in *line time*: the time between line events at the pads. The engine sees an own emit fired in cycle n on the line at n+1 and observes a line event at pad time t on the pin bus at t+2. So, with `D = 3` (1 output register + 2 synchroniser cycles):
  - each (location, clock) gets a *base*: `E` if the clock was last reset by an own emit with no trigger pin (or by engine start in Drive), `O` if by an observe edge, an observed emit, or any edge with a trigger pin; an internal edge passes on the base of its guard clock. Internal edges with no clock guard may not reset clocks (compile error). Conflicting bases on different incoming paths are a compile error.
  - an **observe** edge (and an invariant) on an `E`-based clock: window `[lo + D, hi + D]`;
  - an **own emit** on an `O`-based clock: window `[lo − D, hi − D]` (nom too); if that breaks R4.5 the spec asks for a reaction faster than the chip and is rejected;
  - otherwise unchanged. In Check every clock is `O`-based and nothing changes.
  - The resync location is excluded from base inference; it may have no clock guard and no invariant (compile error otherwise).
- **R7.8 FROZEN. Choice points**: nondeterministic branches tagged with tokens.
  - In Drive they are guarded by "host token == k" and pop the token.
  - In Check the token guard is dropped and the observation decides.
  - The alternatives must be distinguishable by observation; the compiler checks this (it is R7.11 applied after the tokens are dropped).
- **R7.9 DECIDED (S30). Otherwise edges.** An edge may be marked *otherwise*: its meaning is "this guard, and no lower slot is enabled". The hardware needs nothing extra (R3.2 already does this); the mark tells the determinism check (R7.11) and the TChecker export that the overlap with lower slots is intended. The compiler places otherwise edges after the edges they defer to.
- **R7.10 FROZEN\* (S31). Token pop.** The TOKEN data guard only tests the head. The pop is a bit in the action entry, which the compiler sets on every edge that came from a choice in Drive. Behaviour is the same as v0 ("guarded by token == k, pops the token"), but the split also allows a *peek* (a guard without pop), which a controller needs when it must prepare the line for a choice that is popped later (I2C: SDA set while SCL is low, STOP vs repeated START decided while SCL is high).
- **R7.11 FROZEN. Observable determinism (Check role, and every observed part in Drive).** No two edges of one location may accept the same observation. The compiler accepts a pair of slots i < j only if one holds:
  - j is an otherwise edge (R7.9);
  - they are *equivalent*: same target, action, reset mask, error bit;
  - they are *provably disjoint*: their pin patterns require different values on a common pin; or their windows on the same clock are disjoint after widening each by 2 for pin-triggered edges (ages); or their data guards contradict (BITCNT_EQ/BITCNT_LT with incompatible constants, SR_MATCH/SR_NOMATCH with the same k, BITCNT_EQ with different constants).

  Anything else is rejected, with the two edges named. The check is sufficient, not complete: it may reject a deterministic spec, never accept a nondeterministic one.
- **R7.12 DECIDED. Other compiler checks** (each has a test that a bad spec is rejected): fan-out ≤ 4 after the R7.4 expansion, or a chain split listed with its cost (each hop adds E + 1 = 2 cycles and the extra latency of R4.4); R4.5 bounds; the visibility rule; time-base conflicts; nom ∈ [lo, hi]; halt (R3.4); resync location (R7.7); reserved ops; one data pin per emit.
- **R7.12a DECIDED (S36).** Fan-out above 4 after expansion is a compile error that names the location and the cost a chain split would have (E + 1 = 2 cycles per hop). Automatic chain splitting is not implemented; revisit if a protocol spec needs it (S15 count, week 2).
- **R7.12b DECIDED (S37).** Locations unreachable from the initial and resync locations are listed as warnings and excluded from time-base inference.
- **R7.13 DECIDED.** The compiler listing reports, per location: edges after expansion, locations that can fire in their first evaluation cycle, and the latency bound of R4.4.

## 8. Timing policies (Drive / Stress)

- **R8.1 FROZEN.** For POLICY edges, the fire time `t_e` is fixed in the location's entry cycle, from `S_n` of that cycle:
  - nominal (0): `nom` of the window;
  - earliest (1): `lo`;
  - latest (2): `hi`;
  - random (3): R8.2;
  - sweep (4): `min(lo + k·step, hi)`, with k and step from the policy register.
- **R8.2 DECIDED (S26). Random.** A 32-bit Galois LFSR, `lfsr := (lfsr >> 1) XOR (0x80200003 if lfsr & 1 else 0)` (taps 32, 22, 2, 1), advances every cycle from reset, while stopped too. Reset value 1; a host-written seed of 0 is stored as 1. Slot i uses `r = rotr32(lfsr, 8·i) & 0xFFFFF`. With `d = hi − lo`: if d = 0 then `t = lo`; else `m = 2^bitlen(d) − 1`, `r := r & m`, if `r > d` then `r := r − (d + 1)`, `t = lo + r`.
- **R8.3 DECIDED (S26). Random bias.** Every value in [lo, hi] is reachable. Values in `[lo, lo + m − d − 1]` are twice as likely as the rest; the ratio is at most 2:1. Accepted for Stress; the test checks reachability and the bound.
- **R8.4.** Policy is per engine (a host register) and applies to all POLICY edges of the engine. Policy is ignored in Check (no POLICY edges remain after R7.4).

## 9. Coverage record

- **R9.1 FROZEN.** One 32-bit word per edge, index `loc·4 + slot`:
  - `[31:24]` saturating hit count;
  - `[23:12]` minimum offset;
  - `[11:0]` maximum offset.
  - Offset = `min((ts_e − lo) >> s, 4095)`, with lo the edge's window lower bound (0 for clock guard NONE) and s the per-spec scale (engine configuration, 0..15). `ts_e ≥ lo` always holds for GE/WIN/POLICY edges, because the guard is on the same value.
  - A word with count 0 has no hits; its first hit sets min = max = offset.
- **R9.2 FROZEN.** Updates go through a dual-port macro (pipelined read-modify-write) and never stall an engine. A 4-entry queue sits in front, with a sticky `COV_LOST` flag. Coverage counts as complete only when `COV_LOST` = 0.
- **R9.3 DECIDED.** One engine is covered at a time (configuration). The model applies an update at once and also models the queue (in = updates this cycle, out = 1 per cycle) to compute `COV_LOST`. The host reads coverage only while the covered engine is stopped or halted.

## 10. Events between engines

- **R10.1 FROZEN.** 8 broadcast event lines. An action emits for one cycle: firing in cycle n makes line j high in cycle n+1 only (`ev_{n+1}[j] = 1`). The lines are the OR of all engines' emits, including the emitter itself.
- **R10.2 DECIDED (S27).** Events are held like pin changes: an event seen in an entry cycle is pending in the first evaluation cycle; an event not consumed by a firing edge is carried to the target; otherwise it is dropped at the end of the evaluation cycle. An EVENT data guard holds iff the event is pending (`evs`, R3.6) and a firing edge consumes the event its guard names. Events never cause violations.
- **R10.3 DEFERRED (2026-11-30).** TChecker modelling of events as broadcast channels with the one-cycle delay. Not needed for Gate A (single-engine specs).

## 11. Table formats

- **R11.1 FROZEN\* (S28). Edge word, 32 bits** (fields as proposal §3.3; v1 fixes the meaning of every code):

  | bits | field |
  |---|---|
  | 31:25 | target location (7 bits; bit 31 is 0 while there are 64 locations) |
  | 24:22 | pin pattern index (0 = none) |
  | 21:19 | window index |
  | 18:17 | clock guard kind: 0 NONE, 1 GE, 2 WIN, 3 POLICY |
  | 16:14 | data guard kind (R2.6) |
  | 13:11 | constant index k, or event index |
  | 10:7 | action index |
  | 6:4 | clock reset mask (bit 4 = x0) |
  | 3 | error edge (SPEC_ERROR when fired) |
  | 2 | reserved, 0 |
  | 1 | valid |
  | 0 | log/cover |

- **R11.2 DECIDED (S28). Action entry, 32 bits:** `[7:0]` write mask Wm, `[15:8]` write values Wv, `[16]` mode (0 PP, 1 OD), `[19:17]` data pin d, `[23:20]` datapath op, `[26:24]` event index, `[27]` emit event, `[28]` pop token, `[31:29]` reserved 0. Entry 0 is the empty action by compiler convention.
- **R11.3 DECIDED (S28). Window entry (8 per engine):** `{clock 2b, lo 20b, hi 20b, nom 20b}`, 62 bits. Compiler checks `lo ≤ nom ≤ hi`.
- **R11.4 DECIDED (S28). Pattern entry (indices 1..7):** `{mask 8b, value 8b, mode 1b (0 LEVEL, 1 EDGE)}`.
- **R11.5 DECIDED (S28). Constant entry (8 per engine):** 16 bits.
- **R11.6 DECIDED (S28). Location word:** `[12]` halt, `[11]` invariant enable, `[10:8]` invariant window index, `[7:0]` watch mask.
- **R11.7 DECIDED (S28). Engine configuration:** initial location, resync location + valid bit, resync action index, `msb_first`, `drive_en`, cover enable, trace enable, coverage scale s, pin base (R12.6).
- **R11.8 DEFERRED (2026-11-14).** Where the window, pattern, constant, action and location tables live physically (flops or macro spare columns), and FIFO depths. The model uses the logical formats above. Location words do not fit in the two 64x64 edge macros (4 edges × 32 bits fill all 128 bits), so they need flops (64 × 13 = 832 bits) or a format change; this is an RTL-phase area question.

## 12. Reset, loading and host operations

- **R12.1 FROZEN.** All control state is reset by `rst_n`. Tables and macros are not reset; reading an unwritten entry is a testbench error, as in DTC D13.
- **R12.2 FROZEN.** Tables are written by the host only while the engine is stopped or halted. A write to a running engine's tables is ignored and sets sticky `HOST_ERR`.
- **R12.3 DECIDED.** Reset state: engines `STOPPED`, clocks 0, sync flops 0, `pend* = 0`, FIFOs empty, `SR = 0`, `bitcnt = 0`, `out = 0`, `oe = 0`, flags 0, LFSR = 1, global cycle = 0.
- **R12.4 DECIDED.** Host operation `START(engine)` in cycle n, on a stopped or halted engine: in `S_{n+1}` the engine is `RUNNING`, `loc = initial`, `phase = ENTRY`, every clock = 1 (0 at cycle n), pending changes and events cleared. `STOP(engine)`: `state' = STOPPED` and `oe' = 0` (all drives released). Other host operations (push TX byte, push token, pop RX byte, set policy, write seed, read coverage/trace) take effect in `S_{n+1}`; a FIFO push and an engine pop on the same FIFO in one cycle are both applied (the pop sees the old head).
- **R12.5 DEFERRED (2026-11-14).** Host SPI frame format. It will be written as a SPEX spec (dogfooding, proposal §6.4). Until then the model's host operations are API calls, one per `step`.
- **R12.6 DECIDED (S32). Pins and engines.** Engine k sees and drives the chip pins through a rotation by its `pin base` b: engine pin i ↔ chip pin `(i + b) mod 8`. Chip output: `oe[p] = oe0[p] OR oe1[p]`; `out[p] = out1[p] if oe1[p] else out0[p]` (engine 1 wins a conflict, as DTC SM1).
- **R12.7 DERIVED.** The synchroniser flops reset to 0 (R4.1), so a pin that is high after reset shows a change on the pin bus in cycle 2. An engine started (R12.4) in cycle 0 or 1 judges that change and, if the pin is watched, raises UNEXPECTED. Start engines in cycle 3 or later; the host library enforces this. (Found by the toy-UART duality test, 2026-10-20.)

## 13. Worked examples

All examples: one engine, E = 1, pins named as stated. Numbers are exact and each example becomes a pytest in step 2.

### 13.1 Example (a): pin-triggered edge, change outside and inside the entry cycle

Location A is entered by an edge that fires in cycle m = 10 and resets x0 (no trigger pin), so `x0 = 1` in cycle 11. A has one edge, slot 0: pin guard `EDGE {mask = pin0, value = 1}`, clock guard NONE, action `PP pin1 := 1`, target B. A's watch mask = {pin0}.

**Case a1: pad0 rises in cycle 20** (outside the entry cycle).

| cycle | pad0 | P0 | chg0 | phase (loc) | x0 | event |
|---|---|---|---|---|---|---|
| 10 | 0 | 0 | 0 | EVAL (prev) | – | edge into A fires |
| 11 | 0 | 0 | 0 | ENTRY (A) | 1 | |
| 12 | 0 | 0 | 0 | EVAL first (A) | 2 | nothing enabled, nothing pending |
| 20 | **1** | 0 | 0 | EVAL (A) | 10 | |
| 21 | 1 | 0 | 0 | EVAL (A) | 11 | |
| 22 | 1 | **1** | 1 | EVAL (A) | 12 | e0 enabled, `a = 0`: **fires**; τ = 22, ts = 12 |
| 23 | 1 | 1 | 0 | ENTRY (B) | 13 | **pin1 = 1** |

Latency: pad change in 20, output in 23: **L = 3**.

**Case a2: pad0 rises in cycle 9**, so the change reaches the pin bus in the entry cycle 11.

| cycle | pad0 | P0 | chg0 | phase (loc) | x0 | pend1 | event |
|---|---|---|---|---|---|---|---|
| 9 | **1** | 0 | 0 | EVAL (prev) | – | | |
| 10 | 1 | 0 | 0 | EVAL (prev) | – | | edge into A fires (does not look at pin0) |
| 11 | 1 | **1** | 1 | ENTRY (A) | 1 | | change held: `pend1' = {pin0}` |
| 12 | 1 | 1 | 0 | EVAL first (A) | 2 | {pin0} | e0 enabled, age 1, `a = 1`: **fires**; τ = 11, ts = 2 − 1 = **1** |
| 13 | 1 | 1 | 0 | ENTRY (B) | 3 | | **pin1 = 1** |

Latency: pad change in 9, output in 13: **L + E = 4**. The timestamp is the entry cycle's clock value, not the firing cycle's.

**Case a3 (carry-over, R4.4): pad0 rises in cycle 8**, reaching the pin bus in cycle 10, the firing cycle of the previous edge. That edge's pin guard does not name pin0, so the change is carried (age 2) into A. In cycle 12, `a = 2`, τ = 10, ts = 0; it fires and pin1 = 1 in cycle 13. Latency **5**.

### 13.2 Example (b): same-cycle SCL fall and SDA change, carry-over and the age-2 timestamp

Pins: SCL = pin0, SDA = pin1. Location H (SCL high), in steady evaluation, watch {SCL, SDA}; slot 0: `EDGE {SCL = 0}`, NONE, resets x0, target L. On the line, SCL falls and SDA rises in the same pad cycle 30 (I2C allows a data hold time of 0).

Three variants of L, each with no invariant:
- **L1** (the I2C case): watch {SCL}; slot 0: `EDGE {SCL = 1}` (not reached here).
- **L2**: watch {SCL, SDA}; slot 0: `EDGE {SDA = 1}`, `WIN x0 [0, 10]`, log, target M.
- **L3**: watch {SCL, SDA}; slot 0: `EDGE {SCL = 1}` only (an SDA change is a glitch here).

| cycle | pad SCL,SDA | P SCL,SDA | chg | phase (loc) | x0 | pend2 | event |
|---|---|---|---|---|---|---|---|
| 30 | **0,1** | 1,0 | – | EVAL (H) | – | | |
| 32 | 0,1 | **0,1** | {SCL,SDA} | EVAL (H) | – | | H.e0 enabled (`a = 0`): **fires**, consumes {SCL}; **SDA carried**; x0 := 1 |
| 33 | 0,1 | 0,1 | 0 | ENTRY (L) | 1 | {SDA} | |
| 34 | 0,1 | 0,1 | 0 | EVAL first (L) | 2 | {SDA} (age 2) | see below |

In cycle 34:
- **L1**: no edge enabled; SDA is not watched, so the change is dropped. **No violation** (legal hold time 0).
- **L2**: e0: SDA = 1 holds, SDA pending with age 2, `a = 2`, `v = 2 − 2 = 0 ∈ [0, 10]`: **fires**. Trace record: `cycle = 32`, `ts = 0`, `pins = {SDA}`. The SDA change is stamped at the same instant as the SCL fall, which is the truth at one-cycle resolution.
- **L3**: no edge enabled; SDA is watched and pending: **UNEXPECTED** in cycle 34, record `cycle = 34 − 2 = 32`, `pins = {SDA}`. The glitch is caught 2 cycles after the firing (one entry cycle later), with the correct time.

### 13.3 Example (c): UNEXPECTED versus TIMEOUT

Location W is entered by an edge firing in cycle 100 that resets x0, so `x0 = n − 100` from cycle 101. Window `w1 = {x0, lo 5, hi 10}`. W: watch {RX = pin0}, invariant `x0 ≤ 10` (w1); slot 0: `EDGE {RX = 0}`, `WIN w1`, target D. Resync location I is declared.

| case | pad RX falls in cycle | seen (P) in cycle | x0 then | result |
|---|---|---|---|---|
| c1 legal | 105 | 107 | 7 | e0 **fires** in 107, ts = 7 |
| c5 boundary | 108 | 110 | 10 | e0 **fires** in 110 (closed window), ts = 10 |
| c2 early | 101 | 103 | 3 | `v = 3 < 5`: no edge enabled; RX watched and pending: **UNEXPECTED** in 103, record `cycle = 103`; resync to I (entry 104) |
| c3 missing | never | – | – | cycles 102-110: nothing; cycle 111: `x0 = 11 > 10`, no edge enabled: **TIMEOUT** in 111, record `cycle = 111`, `ts = 11` |
| c4 late | 109 | 111 | 11 | `v = 11 > 10`: no edge; watched change **and** invariant broken: one record, `kind = UNEXPECTED|TIMEOUT`, in 111 |

**Case c6 (why R2.5 evaluates at the trigger instant).** Same W, but entered by an edge firing in cycle 200 that does **not** reset x0, with `x0 = 9` in cycle 200 (so 10 in the entry cycle 201, 11 in 202). RX falls on the pad in cycle 199 and is seen in the entry cycle 201 (`x0 = 10`, inside the window). In cycle 202 (first evaluation): `a = 1`, `v = 11 − 1 = 10 ∈ [5, 10]`: e0 **fires**, ts = 10. Under v0's wording (`v = x0 = 11`) the same legal event would have been reported as UNEXPECTED|TIMEOUT.

### 13.4 Example (d): a choice point in Drive versus Check

An I2C-style fragment. Pins SCL = pin0, SDA = pin1, open drain. The controller has just let SCL rise with SDA low, and the spec offers a choice:
- token `STOP` (= 1): the controller releases SDA (a rise while SCL is high), window `wS = {x0, lo 20, hi 30, nom 25}`, target `P_DONE`;
- token `NEXT` (= 2): the controller pulls SCL low, window `wN = {x0, lo 20, hi 30, nom 25}`, target `LOW`.

Location `HI` invariant: `x0 ≤ 30`. Both edges are own emits of side `ctl` with no trigger pin, reached from an own emit that reset x0, so their base is `E` and R7.7 changes nothing.

**Drive as `ctl`** (compiled):

| slot | pin guard | clock | data guard | action |
|---|---|---|---|---|
| 0 | – | POLICY wS | TOKEN == K[0] = 1 | OD SDA := 1 (release), pop |
| 1 | – | POLICY wN | TOKEN == K[1] = 2 | OD SCL := 0 (pull), pop |

The edge into HI fires in cycle 200, so x0 = n − 200. Policy nominal, token FIFO = [STOP]:

| cycle | phase | x0 | token head | event |
|---|---|---|---|---|
| 200 | – | – | STOP | edge into HI fires (SCL released) |
| 201 | ENTRY | 1 | STOP | `t_0 = t_1 = 25` latched |
| 202..224 | EVAL | 2..24 | STOP | nothing enabled (`v < 25`) |
| 225 | EVAL | 25 | STOP | slot 0 enabled (slot 1 fails the token guard): **fires**, pops |
| 226 | ENTRY (P_DONE) | 26 | (empty) | `oe[SDA] = 0`: SDA line rises in pad cycle **226** |

With the token FIFO empty, neither slot is enabled; in cycle 231 (`x0 = 31`) the engine raises **TIMEOUT** (host underrun).

**Check** (compiled from the same spec): the token guards are dropped. The SDA release is an OD write of 1, which is *invisible* (R7.4), but the spec writes the STOP condition as an observe edge for the SDA rise, so slot 0 is that observe edge:

| slot | pin guard | clock | data guard |
|---|---|---|---|
| 0 | `EDGE {SCL = 1, SDA = 1}` | WIN wS | – |
| 1 | `EDGE {SCL = 0}` | WIN wN | – |

Disjoint (R7.11): the patterns need different values of SCL. Feeding the checker the Drive run above: the checker saw the SCL rise (pad 201) on its pin bus in cycle 203 and reset x0 there (`a = 0`, x0 = 0 at 203). The SDA rise (pad 226) is seen in cycle 228, where `x0 = 25`: slot 0 fires, ts = 25. Both engines measured 25 cycles between the same two line events, so Drive's trace passes Check (the role-duality relation of §6.2 in the proposal).

The DSL detail of how one spec yields the observe edge for STOP while Drive releases SDA is a step-3 matter; the hardware and compiler rules it relies on are R7.4 (an OD release is invisible) and R7.8.

## 14. Changes from v0

| v0 item | v1 | S-id | changed FROZEN wording (approved 2026-10-19) |
|---|---|---|---|
| §1 OPEN prescaler | none in v1, revisit by 2026-11-14 (R1.3) | S18 | no |
| §1 OPEN overflow | saturate (R1.4) | S19 | no |
| §1 reset instant (unstated) | `x = 0` at the trigger instant, register 1 + a (R1.6) | S20 | **yes** |
| §2 pin guard "into-match" | EDGE = pattern holds ∧ pending change on its pins (R2.4) | S34 | **yes** |
| §2 clock guard value | evaluated at the trigger instant `x − a` (R2.5) | S21 | **yes** |
| §2 data guard codes | fixed; 8th code SR_NOMATCH (R2.6) | S33 | no |
| §2 action resets | resets only in the edge word (R2.8) | S28 | no |
| §3 OPEN dead ends | explicit halt bit; other dead ends rejected (R3.4) | S23 | no |
| §4 OPEN cycle n | DTC convention (R0.1-R0.4, R4.3) | S17 | no |
| §4 latency "L or L + E" | L + d, d ∈ {0, 1, 2}, +2 per extra carry (R4.4) | S35 | **yes** |
| §4 "lo ≥ E + 1" | also `lo ≥ E + 3` when the clock is reset by a pin-triggered edge (R4.5) | S20 | **yes** |
| §5 which age if several | the minimum (latest change) (R5.4) | S22 | no |
| §6 OPEN after violation | resync location, else halt (R6.5) | S24 | no |
| §6 record | adds slot, value, ts; kind is a bit set; pin-bus time (R6.4) | S25 | **yes** |
| §7 role transform detail | emit/observe/internal classes, visibility, silent completion, otherwise edges, time-base compensation (R7.2-R7.9) | S30 | no (new rules, no FROZEN text changed) |
| §7 token pop | an action bit; TOKEN guard is a pure test (R7.10) | S31 | **yes** |
| §8 OPEN random bias | ≤ 2:1, all values reachable (R8.2-R8.3) | S26 | no |
| §10 OPEN events in TChecker | DEFERRED 2026-11-30 (R10.3); hold/carry rule decided (R10.2) | S27 | no |
| §11 OPEN bit positions | fixed (R11.1-R11.7); physical storage DEFERRED 2026-11-14 | S28 | edge word fields unchanged; **yes** only for the code meanings |
| §12 OPEN host frame | DEFERRED 2026-11-14 (R12.5) | S29 | no |
| (new) pins | line-value writes, PP/OD, engine pin base, engine 1 wins (R2.9, R12.6) | S32 | no |
