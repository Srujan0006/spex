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

(pending the first CI run)
