# RTL timing spike: the engine's critical loop (owner task, 2026-10-22)

Question: does one engine's evaluation loop close at 20.8 ns (48 MHz) on IHP SG13CMOS5L, and if not, at what clock?

The loop, per SEMANTICS v1: the held output of 2 × RM_IHPSG13_1P_64x64 (4 edge words of the current location, R4.2)
→ pattern, window and constant table reads (4 ports each) → pin guard LEVEL/EDGE over the pending changes (R2.4,
R5.2) → trigger age (R5.4) → `v = max(x_c − a, 0)` (R2.5) → clock guard GE / WIN / POLICY against the latched `t_e`
→ data guard (R2.6) → lowest enabled slot (R3.2) → target → the macros' address and read enable for the next entry
(through the host-write address mux), and the clock resets `x := 1 + a` (R1.6).

`src/spex_loop.sv` is **not** the SPEX RTL: no actions, violations, coverage, events, FIFOs, LFSR policies or host
port (tables load through a scan chain; the policy is "earliest"). It keeps every gate between the macro output and
the macro address, because that is the path that sets the clock. SystemVerilog (S14), in a subset every Yosys front
end reads.

- `src/project.sv`: top: 2-flop pin synchroniser (R4.1), host stand-in (scan chains), the two macros.
- `tb/tb_spike.sv` with `tb/sram_64x64_beh.v` (behavioural SRAM, simulation only): two locations, a clock edge
  (x0 ≥ 5) and a pin edge (pin 0 rises); expects 0 → 1 → 0 → … Planted bug: inverting the pin guard's level match
  makes it fail.

      cd experiments/rtl_spike/tb
      iverilog -g2012 -o spike.vvp tb_spike.sv sram_64x64_beh.v ../src/project.sv ../src/spex_loop.sv && vvp -n spike.vvp

- Harden: workflow `rtl_spike` (8x4, CLOCK_PERIOD 20.8 ns, fp5's floorplan recipe with the two macros as a
  back-to-back pair at x = 464.20); it prints the post-route STA summary and the worst slow-corner setup paths.

## Results

**Run 1 (CI 39751181520, 2026-10-22): not routed.** Cancelled by the 320-min step timeout in detailed routing:
25,343 violations after the first pass, 4,818 at the end (Metal2/Metal3 shorts and spacing), although utilisation was
0.193 and global routing had only 71 overflowing tiles. The config had heuristic diode insertion (copied from the
variants' setting of that day, BUGS 28): it inserted 7,958 diodes. Timing from this run is not meaningful. Run 2 uses
fp5's antenna recipe exactly (no heuristic diodes, one antenna re-route).

**Run 3 (CI 39796771222, 2026-10-22, fp5 antenna recipe, 15-pass cap): routed to 591 DRC violations, timing far off.**
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
