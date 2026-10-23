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
