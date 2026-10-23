# RTL timing spike: the engine's critical loop (owner task, 2026-10-22)

Question: does one engine's evaluation loop close at 20.8 ns (48 MHz) on IHP SG13CMOS5L, and if not, at what clock?

The loop, per SEMANTICS v1: the held output of 2 × RM_IHPSG13_1P_64x64 (4 edge words of the current location, R4.2)
→ pattern, window and constant table reads (4 ports each) → pin guard LEVEL/EDGE over the pending changes (R2.4,
R5.2) → trigger age (R5.4) → `v = max(x_c − a, 0)` (R2.5) → clock guard GE / WIN / POLICY against the latched `t_e`
→ data guard (R2.6) → lowest enabled slot (R3.2) → target → the macros' address and read enable for the next entry
(through the host-write address mux), and the clock resets `x := 1 + a` (R1.6).

`src/spex_loop.sv` is **not** the SPEX RTL: no events, FIFOs, coverage, trace, host port or LFSR policies (the policy
is "earliest"; tables load through a scan chain). SystemVerilog (S14), in a subset every Yosys front end reads.

**v2 (owner decisions 2026-10-22), split as R3.5/R4.2 already allow, no rule change:**
- *Entry cycle (path A):* held macro output (4 edge words from 2 × 1P_64x64, the location word from 1P_64x16) →
  pattern / window / constant table reads → per-slot registers `{valid, target, mask, value, mode, ck, clock, lo, hi,
  t_e, data kind, constant, action, resets}` and the location's `{watch, invariant clock, invariant hi}`.
- *Evaluation cycle (path B):* only those registers, the pins, the pending masks and the clocks → guards → lowest
  enabled slot, or UNEXPECTED / TIMEOUT → next location (resync 0) → macro address. No table read or macro output.
- *Clock history:* `v = max(x − a, 0)` is a 3:1 select of `x`, `x_d1`, `x_d2` per clock (reference and proof:
  `spex/refsim/clock_history.py`, `tests/model/test_clock_history.py`).
- *Action path:* fired slot → 16-entry action table → pin writes (PP/OD) and LOAD / SHIN / SHOUT / CLR / INC → registers.
- *Floorplan:* the 64x64 pair faces one 200 µm logic channel (u_m0 FS at y 226.80, u_m1 N at y 491.40, x 464.20);
  the 64x16 at x 216.92, y 355.32; placement density 45 %; post-global-route design and timing repair on (as PRISM).
- *Per-path timing:* `sta_paths.tcl`, run by the workflow on the final database at every corner (A, B, action).

Flip-flops added by v2 per engine: 4 slots × 102 + 27 location + 96 clock history = **531** (owner estimate ~400).

- `src/project.sv`: top: 2-flop pin synchroniser (R4.1), host stand-in (scan chains), the three macros.
- `tb/tb_spike.sv` with behavioural SRAM models (simulation only): a two-location loop with a PP action, irregular pin
  toggles that give resets with ages 1 and 2, a clock driven into saturation, the clock-history invariant checked
  every cycle, and a TIMEOUT violation with resync. Planted bugs (saturation history, reset history ignoring the
  age, TIMEOUT disabled) each make it fail.

      cd experiments/rtl_spike/tb
      iverilog -g2012 -o spike.vvp tb_spike.sv sram_64x64_beh.v sram_64x16_beh.v ../src/project.sv ../src/spex_loop.sv && vvp -n spike.vvp

## Results

**Run 1 (CI 39751181520, 2026-10-22): not routed.** Cancelled by the 320-min step timeout in detailed routing:
25,343 violations after the first pass, 4,818 at the end (Metal2/Metal3 shorts and spacing), although utilisation was
0.193 and global routing had only 71 overflowing tiles. The config had heuristic diode insertion (copied from the
variants' setting of that day, BUGS 28): it inserted 7,958 diodes. Timing from this run is not meaningful. Run 2 uses
fp5's antenna recipe exactly (no heuristic diodes, one antenna re-route).

**Run 3 (CI 39796771222, 2026-10-22, fp5 antenna recipe, 15-pass cap): unrouted, not representative (owner, 2026-10-22).**
Utilisation 0.193; detailed routing stopped by the 15-pass cap at 591 violations (job 1 h 26 min). Post-route STA at
20.8 ns, on that unfinished layout [Measured, job log]:

| Corner | Setup WS | Setup violations (reg-to-reg) | Hold WS | Max cap violations |
|---|---|---|---|---|
| slow 1.08 V 125 °C | **−24.115 ns** (needs 44.9 ns: 22.3 MHz) | 112 (112) | +0.514 ns | 68 |
| typical 1.20 V 25 °C | −7.154 ns (needs 28.0 ns: 35.8 MHz) | 112 (112) | +0.238 ns | 68 |
| fast 1.32 V −40 °C | +2.830 ns | 0 | +0.056 ns | 69 |

Worst slow-corner path (arrival 45.69 ns): clock to the macro 1.29 ns; `u_m0` A_CLK → A_DOUT[51] **5.64 ns**; then
guard logic, priority (a 24-fanout select net) and the selection mux into a register (`_12937_/D`). Five nets in it
are long wires of 0.17–0.44 pF driven by 1x cells (slews 2.6–11.4 ns) and cost about **21.6 ns** together
(nor4_1 8.34 ns, o21ai_1 4.56 ns, a22oi_1 3.84 ns, a221oi_1 3.70 ns, or2_1 1.20 ns); the remaining ~17 ns is logic.
Readings [Estimate]: the unrepaired long wires (68 max-cap violations) and the unfinished route make this an upper
bound, not the loop's real delay; the macro's 5.6 ns clock-to-output plus ~17 ns of logic alone is already above
20.8 ns at the slow corner, so the loop as written does not close at 48 MHz on the slow corner even with good wires.

Owner decision 2026-10-22: run 3's timing is not evidence. The spike must first route to 0 violations with 0 max-cap
violations. Cause found in the macro LEF [Measured, IHP-Open-PDK 2bbec755]: the 64x64's 64 `A_DOUT` pins run along its
whole long edge (x 10.6–773.6 µm) and its address/control pins sit at the middle (x 387–399 µm); run 3's back-to-back
pair put u_m0's pins in the channel below the pair and u_m1's in the channel above, so the loop logic straddled the
macros. Spike v2 puts the two 64x64 macros face to face around one logic channel.

**v2 run 1 (CI 39812959173, 2026-10-22): not routed, not representative.** Utilisation 0.268. Detailed routing reached
123 after 15 passes, 247 after the antenna re-route (Metal4 226 shorts, 19 spacing; Metal2 2); LibreLane then
crashed parsing the LVS report (`JSONDecodeError`, as with shorted nets before), so no final database and no per-path
timing. Where (fp_report on GitHub, `drc_where.py`): **241 of 247 over the u_m0 / u_m1 interiors**, through the routing
obstructions (309 obstruction sources), on clock-tree leaf nets, `edge_q` bits and `l_inv_clk`: cells placed below
u_m0 or above u_m1 had to reach the channel across a macro. 45–48 max-cap violations, almost all on the macros' own
`A_DOUT` pins (limit 0.064 pF, 0.15–0.27 pF measured). Indicative only: slow setup −7.0 ns, typical +3.45 ns,
fast +9.43 ns, hold met.

Iteration 2: `FP_OBSTRUCTIONS` (no placement sites) beyond the macros (x 464.2–1248.68, y < 226.80 and y > 555.76),
`CTS_OBSTRUCTION_AWARE`, and `DESIGN_REPAIR_MAX_WIRE_LENGTH` / `GRT_DESIGN_REPAIR_MAX_WIRE_LENGTH` = 200 µm.

**v2 iteration 2 (CI 39826276891): 0 max-cap, still not routed.** The 200 µm wire-length buffering cleared every
max-capacitance violation (0, from 45–48). Detailed routing: 185 after 15 passes, 307 after the antenna re-route
(Metal4 290 shorts, 15 spacing), then the same LVS-report crash. 278 of 307 lie over the macro interiors, with hot
spots near the macro ends (x ≈ 500–700 and 1000–1150): cells in the corners (beside the macros but beyond them in y)
were not blocked, and their nets cut across a macro's end. Iteration 3 blocks placement across the full die width
outside the band y 226.80–555.76 (the channel, the 64x16 and the side areas stay open, about 0.57 mm²).

**v2 iteration 3 (CI 39882022079): stopped at the 120-min step limit before detailed routing finished.** Step times
[Measured, job log]: global routing 16 min (6,045 overflowing tiles at 29.8 % usage: the band concentrates the logic),
post-GRT design repair 42 min (2,392 buffers in 1,502 nets at placement), post-GRT timing repair 41 min, detailed
routing from 02:53 until the limit at 03:07. Iteration 4: post-GRT timing repair off (timing is not the question until
it routes), post-GRT design repair kept (max-cap), spike step limit 150 min (job 180).

**v2 iteration 4 (CI 39904207436): worse; stopped at the 150-min limit in detailed routing.** Global routing 16 min,
post-GRT design repair 42 min, detailed routing from 06:15: 46,913 violations after pass 0, 32,438 after pass 1
(iteration 2: 14,716 after pass 0, 185 after 15 passes). Confining the logic to one band raised congestion more than
it removed macro crossings.

Routing iterations of v2 so far [Measured, job logs]:

| Run | Change | First route (15 passes) | Final | Max cap |
|---|---|---|---|---|
| 39812959173 | facing macros, density 45 % | 123 | 247 (re-route) | 45–48 |
| 39826276891 | + no placement beyond the macros, obstruction-aware CTS, 200 µm wire buffering | 185 | 307 (re-route) | **0** |
| 39882022079 | + logic confined to one band across the die | — (time limit in routing) | — | — |
| 39904207436 | band, post-GRT timing repair off | 32,438 after pass 1 (time limit) | — | — |

In both runs that finished routing, almost all remaining violations were Metal4 shorts over the 64x64 interiors,
through the routing obstructions: with `GRT_ALLOW_CONGESTION` the global router still plans some nets across the
macros. Stopped here for the owner's decision.

## Two layouts in parallel (owner decisions 2026-10-23)

Same v2 RTL; configs generated by `layouts/gen_layouts.py` (edit the generator, not the outputs). The TT I/O pins are
all on the top edge at x 29.8–191.0 µm [Measured: `tt-support-tools` `tech/ihp-sg13cmos5l/def/tt_block_8x4_pgvdd.def`].

| | u_m0 (64x64) | u_m1 (64x64) | u_loc (64x16) | placement-blocked corridor |
|---|---|---|---|---|
| **A**, opposite edges | (464.20, 3.78) FS, pins up | (464.20, 601.02) N, pins down | (216.92, 3.78) FS, pins up | above u_m1, y 665.38–706.86 |
| **B**, one wall | (3.36, 3.78) FS, pins up | (801.40, 3.78) FS, pins up | (3.36, 601.02) N, pins down | above u_loc, y 665.38–706.86 |

B deviates from "u_loc at one end" of the wall: the two 64x64 (2 × 784.48 µm) and the 64x16 (236.8 µm) need at least
1,805.8 µm and the core is 1,718.4 µm wide. u_loc therefore sits at the top-left at the same x as u_m0, so that its
power columns lie on u_m0's left-half columns (the stripe step only lets a full-height stripe cross another SRAM on that
SRAM's own column of the same net).

Both: no band obstructions; macro routing obstructions, obstruction-aware CTS and 200 µm repair wire length kept;
`GRT_ALLOW_CONGESTION` off (global routing fails instead of planning through macros); 15-pass detailed-route cap; LVS,
Magic stream-out / LEF and the IR-drop report off. `sta_paths.tcl` now times the newest database after detailed
routing with the newest extracted parasitics, so every run reports per-path slack together with its violation count.
Stop rule: if neither A nor B routes to 0, stop and report options (a)–(c) with area and latency.

### Options if neither layout routes (prepared 2026-10-23 for the owner's decision)

Macro data [Measured, IHP-Open-PDK 2bbec755 LEF and slow-corner liberty]: 1P_64x64 784.48 × 64.36 µm (50,489 µm²),
`A_DOUT` spread over 763 µm, clock-to-output 5.04–5.46 ns; 1P_256x32 416.64 × 118.78 µm (49,488 µm²), `A_DOUT` over
~406 µm, 5.02–5.44 ns; 1P_64x16 236.8 × 64.36 µm (15,240 µm²), 4.88–5.30 ns. The PDK has no 1P_64x32. Window table
[Measured, `probe_tables.py`]: 75,657 µm² at 6 read ports, 62,702 µm² at 4.

| Option | What changes | Area per engine | Latency | Rules |
|---|---|---|---|---|
| **(a)** window ports 6 → 4 | coverage margin from the slot registers (already registered in v2); invariant `{en, clock, hi}` stored in the location word, which grows from 14 to 28 bits: a second 1P_64x16 at the same address | window table −12,955; second 64x16 +15,240; **net ≈ +2.3k µm²** [Estimate from the measurements]; one more macro to place | unchanged (E = 1) | R2.7 is FROZEN (invariant = window index) and R11.6 changes: owner decision |
| **(b)** edges in 4 × 1P_256x32 | one slot word per macro; 64 of 256 rows used | macros 4 × 49,488 = 197,954 vs 2 × 50,489 = 100,978: **+97.0k µm² (+0.097 mm², ≈ +8 points of the 8x4 core)**; one engine ≈ 0.53 utilisation [Estimate], between fp_one_engine's 0.45 (routes) and fp_asym's 0.65 (does not) | unchanged (E = 1) | R11.8 / S44 storage decision (not FROZEN) |
| **(c)** E = 2 with 2 × 1P_256x32 | two reads per entry (slots 0–1, then 2–3), address `{loc, half}` | macros 98,977 vs 100,978: **−2.0k µm²** | entry 1 → 2 cycles: minimum dwell per location 3 cycles instead of 2; R4.4 latency +1 cycle when a change lands in an entry cycle; R4.5 bounds lo ≥ 3 / ≥ 5 (were 2 / 4) | FROZEN (R4.2, R4.4, R4.5): owner decision; model, compiler checks and tests change |

(b) and (c) also make a one-wall floorplan natural: four or five 416.64 µm macros fit in one row (x = 3.36, 430.48,
857.60, 1284.72 on the 11.24 µm grid, the last ending at 1701.36), with every `A_DOUT` pin facing the logic.

## Results of layouts A and B (CI 39934290172 / 39934294249, re-timed by spike_sta 39939400439 / 39939403874, 2026-10-23)

**Both route to 0 detailed-routing violations** within the 15-pass cap (A: 10:21, B: 10:25 after a 10:08 start of
routing), with **0 max-capacitance and 0 max-slew violations** at all corners; the only check violators are
clock-tree leaf buffers with 16–18 sinks against a max-fanout limit of 8. Utilisation 0.268. The flow then stopped
at `CheckDesignAntennaProperties` (it needs the Magic LEF this spike config turns off), after post-route STA. LVS
was off, so OpenROAD's 34,656 power-grid warnings are not cleared by LVS here (they appeared, and LVS passed, in fp5
and fp_one_engine). Post-route setup slack at 20.8 ns [Measured, `sta_paths.tcl` on the routed database with
extracted parasitics]:

| Path | A slow | A typ | A fast | B slow | B typ | B fast |
|---|---|---|---|---|---|---|
| (A) entry: macro clock-to-output → table reads → slot registers | +9.387 | +13.752 | +16.244 | +8.537 | +13.228 | +15.909 |
| (B) evaluation: slot registers → guards → priority → next address → macro inputs | +5.751 | +11.201 | +14.400 | +4.328 | +10.366 | +13.880 |
| action: → pin-write registers (uio_out / uio_oe) | +1.212 | +8.402 | +12.681 | (not found) | | |
| **overall worst register-to-register** | **+0.732** | **+8.100** | +12.403 | **−1.124** | **+7.056** | +11.739 |
| hold worst (from the flow's STA) | met | met | met | met | met | met |

Fmax (1 / (20.8 ns − worst slack)): **layout A 49.8 MHz slow, 78.7 MHz typical; layout B 45.6 MHz slow, 72.8 MHz
typical.** Path (B) alone would allow 66.4 MHz (A) / 59.6 MHz (B) at the slow corner; path (A) 87.6 / 81.2 MHz.

The overall worst path is the **firing update**, not (A) or (B): a slot register → pin/age compare → guard → priority
(fan-out buffers) → a long wire run of about 8 buffers (≈ 2.8 ns) → action-table selection and op decode → a mux into
a datapath register, with two hold-fix delay cells on it (≈ 1.27 ns). Layout B is slower on it (one wall puts the
logic further from the action/datapath registers).

Against the owner's targets: typical ≥ 48 MHz with ≥ 2 ns margin — **met by both** (A +8.1 ns, B +7.1 ns); slow-corner
goal ≥ 40 MHz — **met by both** (A 49.8 MHz, so A also closes 48 MHz at the slow corner by 0.73 ns). Caveat: the spike
has no events, FIFOs, coverage, trace or host port; the real engine adds logic, much of it on the same firing update
(event emit, coverage strobe, token pop), so A's 0.73 ns slow-corner margin is thin. Prefetching the four slots'
actions in the entry cycle (4 × 32 = 128 more flip-flops, ≈ +7k µm² [Estimate from the per-table probe]) would take
the action-table read off that path.

## Layout A adopted, action prefetch (owner, 2026-10-23; DECISIONS S50)

The entry cycle now also loads each slot's 32-bit action (`s_actw[i] <= act[e[10:7]]`), so the firing update selects
one of four registered actions instead of reading the 16-entry table after the priority. Cost: 4 × 32 = 128 more
flip-flops and the action table grows from 1 to 4 read ports (it moves onto path (A), which had 8–9 ns of slow-corner
slack). Testbench passes; planted bug "prefetch reads action 0" makes it fail.

**Prefetch run (CI 39940239878, layout A): timing much better, 26 violations left.** Worst register-to-register slack
at 20.8 ns: **+4.148 ns slow (60.1 MHz), +10.329 ns typical (95.5 MHz)**, +13.893 ns fast (was +0.732 / +8.100 /
+12.403 without prefetch); path (A) +8.728 / +13.329 / +15.954, path (B) +4.785 / +10.668 / +14.072, action
+4.249 / +10.397 / +13.903; 0 max-cap [Measured]. Routing ended at 26 Metal2 violations (16 spacing, 10 shorts) at
the 15-pass cap, all in the open core, 22 in one 50 µm hot spot around (1000, 350) on window-table scan nets, so this
run is not yet evidence. Area of the spike core with prefetch: 193,892 µm², 2,005 flip-flops (v2: 178,064 µm²,
1,925): **+15.8k µm²** [Measured, yowasp-yosys 0.70]. Next run: 30 detailed-route passes and placement density 40 %.

## Result: layout A with action prefetch routes and closes 48 MHz with margin (CI 39996024186, 2026-10-23)

30 detailed-route passes, placement density 40 %, utilisation 0.281. **0 routing violations** (first route 31, antenna
re-route to 0), **0 max-capacitance and 0 max-slew violations** at every corner (only clock-tree leaf buffers exceed
the max-fanout limit of 8), **hold met at every corner** (slow +0.600, typical +0.283, fast +0.106 ns). The flow's
final error is the known `CheckDesignAntennaProperties` stop caused by the Magic LEF being off, after STA; LVS was off.
Post-route setup slack at 20.8 ns [Measured, `sta_paths.tcl` on the routed database with extracted parasitics]:

| Path | slow 1.08 V 125 °C | typical 1.20 V 25 °C | fast 1.32 V −40 °C |
|---|---|---|---|
| (A) entry: macro → table reads (incl. action) → slot registers | +8.169 | +12.965 | +15.737 |
| (B) evaluation: slot registers → guards → priority → next address → macros | **+4.041** | **+10.121** | **+13.707** |
| action: prefetched action → pin-write registers | +4.712 | +10.618 | +14.099 |
| overall worst (register to register) | **+4.041** | **+10.121** | +13.707 |

**Fmax: 59.7 MHz at the slow corner, 93.6 MHz typical.** The critical path is now the evaluation loop (B), as
intended; the firing update no longer limits. Owner targets: typical ≥ 48 MHz with ≥ 2 ns margin — met (+10.1 ns);
slow-corner ≥ 40 MHz — met (59.7 MHz; 48 MHz closes at the slow corner with +4.0 ns). Remaining caveats: the spike has
no events, FIFOs, coverage, trace or host port, and LVS was not run.
