# Decision log

Status values: **Approved** (frozen), **Proposed**, **Open**, **Superseded**.

To change an approved decision, add a new entry that supersedes it; do not edit the old one.

| ID | Decision | Status | Date | Source |
|---|---|---|---|---|
| S1 | Pivot from DTC (PIO core) to SPEX (timed-automaton spec engine), subject to the Gate A stop rule | Approved | 2026-10-19 | proposal §0, §9 |
| S2 | Integer time; closed guards only | Approved | 2026-10-19 | SEMANTICS §1 |
| S3 | Urgent firing, lowest-index priority | Approved | 2026-10-19 | SEMANTICS §3 |
| S4 | Independent pin, clock and data guard fields, ANDed (fixes rev-1 encoding bug) | Approved | 2026-10-19 | review round 1, Con 1 |
| S5 | E = 1: edge memory = 2 × RM_IHPSG13_1P_64x64 per engine, 64 locations × 4 edges | Approved | 2026-10-19 | review round 2, C |
| S6 | Per-location watch mask; UNEXPECTED and TIMEOUT violations | Approved | 2026-10-19 | review round 1, Con 3 |
| S7 | Same-cycle events: the fired edge consumes only its own pins; the rest carry over to the target location | Approved | 2026-10-19 | review round 2, B |
| S8 | Timestamps from per-pin ages (0/1/2); no timestamp registers | Approved | 2026-10-19 | review round 2, A |
| S9 | Choice points resolved by the host token stream (Drive) or by observation (Check) | Approved | 2026-10-19 | review round 1, Con 4 |
| S10 | Coverage word 8 + 12 + 12 bits, window-relative and scaled; dual-port RM_IHPSG13_2P_256x32; never stalls; `COV_LOST` flag | Approved | 2026-10-19 | review round 1, Con 5 |
| S11 | Two engines (Drive/Stress/Cover and Check), not three | Approved | 2026-10-19 | proposal rev 2 |
| S12 | 8x4 primary; Plan B (3 macros, shared, E = 2) and Plan C (1 engine, 6x4-capable) as fallbacks | Approved | 2026-10-19 | proposal §4 |
| S13 | Week-1 dummy-macro floorplan harden, part of Gate A | Approved | 2026-10-19 | review round 1, Con 6 |
| S14 | RTL language: SystemVerilog (reuse the DTC harness) or Hardcaml | **Open**; decide by 2026-11-14 | | DTC D4 carried over |
| S15 | 64 locations enough for a full I2C target? Otherwise engine 0 uses 2 × 256x64 | Superseded by S40 | 2026-10-20 | proposal §9 risks |
| S16 | Spec DSL embedded in Python (OCaml front end optional later) | Proposed | 2026-10-19 | proposal §5 |
| S17 | Cycle convention from DTC: cycle n = interval after rising edge n; `step()` = one edge; pad change in cycle n reaches the pin bus in n+2 | Approved | 2026-10-19 | SEMANTICS R0.1-R0.4, R4.3 |
| S18 | No clock prescaler in v1 (20 bits at 48 MHz = 21.8 ms); revisit by 2026-11-14 if a held-out protocol needs more | Approved | 2026-10-19 | R1.3 |
| S19 | Clocks saturate at 2^20 − 1, never wrap | Approved | 2026-10-19 | R1.4 |
| S20 | Clock reset instant = the trigger instant: register value 1 + a; exact clock-triggered firing needs lo ≥ E+1, or lo ≥ E+3 if a pin-triggered edge resets the clock | Approved (owner, 2026-10-19) | 2026-10-19 | R1.6, R4.5 |
| S21 | Clock guards of pin-triggered edges are evaluated at the trigger instant v = x − a | Approved (owner, 2026-10-19) | 2026-10-19 | R2.5, example 13.3 c6 |
| S22 | Pending set = ages 0/1/2 (1 and 2 only in the first evaluation cycle); edge age = minimum age over its trigger pins | Approved | 2026-10-19 | R5.2, R5.4 |
| S23 | Explicit halt bit in the location word; any other dead-end location is a compile error | Approved | 2026-10-19 | R3.4 |
| S24 | After a violation: go to the declared resync location (clocks reset, pending dropped, resync action), else halt; count violations | Approved | 2026-10-19 | R6.5 |
| S25 | Trace record {type, cycle, engine, loc, slot, kind, pins, value, ts}; kind is a bit set; cycle in pin-bus time | Approved (owner, 2026-10-19) | 2026-10-19 | R6.3, R6.4 |
| S26 | Random policy: 32-bit Galois LFSR (0x80200003), power-of-two mask and fold; bias ≤ 2:1 accepted; every value reachable | Approved | 2026-10-19 | R8.2, R8.3 |
| S27 | Events are held through the entry cycle and carried over like pin changes; TChecker event modelling deferred to 2026-11-30 | Approved | 2026-10-19 | R10.2, R10.3 |
| S28 | Table formats: edge word codes fixed; action, window, pattern, constant, location and config layouts; resets only in the edge word; physical storage deferred to 2026-11-14 | Approved (owner, 2026-10-19) | 2026-10-19 | §11 |
| S29 | Host SPI frame format deferred to 2026-11-14; the model uses API-level host operations | Approved | 2026-10-19 | R12.5 |
| S30 | Role transform: emit/observe/internal edges; observed emits become EDGE + silent-completion otherwise edges; OD release invisible; clock resets only on visible emits; Drive time-base compensation D = 3 | Approved (new rules) | 2026-10-19 | R7.2-R7.9 |
| S31 | TOKEN data guard is a pure test; the pop is an action bit set by the compiler (allows peek) | Approved (owner, 2026-10-19) | 2026-10-19 | R7.10 |
| S32 | Pin writes in line values, PP or OD; engine pin base rotation; engine 1 wins an output conflict | Approved | 2026-10-19 | R2.9, R12.6 |
| S33 | Datapath v1: 8-bit SR, saturating bitcnt, op set of R2.10, data guard code 7 = SR_NOMATCH | Approved | 2026-10-19 | R2.6, R2.10 |
| S34 | EDGE pin mode = pattern holds and one of its pins has a pending change | Approved (owner, 2026-10-19) | 2026-10-19 | R2.4 |
| S35 | Reaction latency is L + d with d ∈ {0,1,2} (+2 per extra carry); v0's "L or L+E" missed carry-over | Approved (owner, 2026-10-19) | 2026-10-19 | R4.4, example 13.1 a3 |
| S36 | Fan-out > 4 after role expansion is a compile error with the chain-split cost reported; automatic chain split not implemented until a spec needs it | Approved | 2026-10-20 | R7.12a |
| S37 | Compiler details within R7: reactive emits are observed by their trigger; data pins are visible in OD mode too; unreachable locations warned and skipped in time-base inference; engines start in cycle ≥ 3 (R12.7) | Approved | 2026-10-20 | R7.4, R7.12b, R12.7 |
| S38 | Datapath op 9 = PUSH_LOAD_PEEK (full-duplex byte boundary for an SPI target); CRC ops move to 10-15 | Approved | 2026-10-20 | R2.10 |
| S39 | Compiler details for shared open-drain buses: emit options cond / silent / visible / shadow, duplicate observer edges dropped, own echo unwatched in the emit's target, observed-derived edges time-compensated, POLICY lo clipped with a warning, GE/invariant window sharing | Approved | 2026-10-20 | R7.4a, R7.4b, R7.6a, R7.7, R7.12c, R7.12d |
| S40 | 64 locations are enough for the week-1 protocols [Measured: UART 6, SPI target 5-6, I2C controller+target 37 locations]. The binding limit is the small tables: I2C Drive-as-controller uses 8/8 windows, 8/8 constants and 15/16 actions. Revisit the table sizes (edge word bit 2 is free; a 4th window-index bit would allow 16 windows) before RTL, by 2026-11-14. **Update 2026-10-20 (step 5): after the S41 fixes the Standard-mode I2C controller needs 9 windows, so it no longer fits; decision needed now** | Approved (count); table sizes **Open** | 2026-10-20 | tests/model/test_*_spec.py `test_location_count*` |
| S41 | Echo dwell: after an own emit that writes pins, clock-triggered edges of its target need lo >= D + 1 = 4 (POLICY clipped); silent observer edges fire at hi + 1 so a change at exactly hi is judged in the window | Approved | 2026-10-20 | R7.6b, R7.4a |
