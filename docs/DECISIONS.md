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
| S15 | 64 locations enough for a full I2C target? Otherwise engine 0 uses 2 × 256x64 | **Open**; decide by count in week 2 | | proposal §9 risks |
| S16 | Spec DSL embedded in Python (OCaml front end optional later) | Proposed | 2026-10-19 | proposal §5 |
