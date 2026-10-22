# Gate A, 2026-11-02 (stop rule)

## Report (step 8, 2026-10-22): **PASSED** (owner, 2026-10-22), with caveats

Both conditions of the stop rule hold, twelve days before the gate date.

| Condition | Verdict | Headline evidence |
|---|---|---|
| 1. UART, SPI and I2C run in Drive **and** Check on the Python model | **met (model only)** | UART 8N1, SPI target modes 0–3, I2C controller and target in Standard and Fast mode, judged by oracles written from the standards (never from `spec/` or `spex/`); every Check role flags ≥ 5 planted faults at the right kind and cycle. `python3 -B -m pytest -q`: 274 passed, 1 skipped (the TChecker reachability test, run by the `tchecker` CI workflow) [Measured, 2026-10-22] |
| 2. A dummy floorplan with ≥ 5 SRAM macros routes and passes precheck at 8x4 | **met (dummy filler)** | `fp5` (4 × 1P_64x64 + 1 × 1P_256x32): routing DRC 0, LVS 0, no antenna violations, Tiny Tapeout precheck passed, setup and hold met at all three corners (CI 39575347791) [Measured] |

**Caveats (they bound what the pass means):**
1. **Condition 1 is model-level.** No SPEX RTL exists yet; the claim is that the semantics, the compiler and the specs
   work, not that silicon does. The RTL is the next phase (S14: SystemVerilog).
2. **Condition 2 uses a light filler.** `fp5` is at 26 % utilisation. Engine-sized variants: two full engines do not
   place (0.79, rejected); asymmetric (0.65) does not route; **one engine (0.45) routes, is LVS clean and passes
   precheck** (CI 39773589405), so S46 selects one engine. Filler timing is **not representative** of the engine (owner, 2026-10-22);
   the engine's timing comes from the critical-loop RTL spike.
3. **Table capacity is the binding limit,** not locations: the I2C controller uses 8/8 constants and 15/16 actions,
   and I2C Check uses 7/7 pin patterns (table below). A held-out protocol more complex than I2C may not fit.
4. **Known semantic limit:** a UART stop bit up to 2 cycles short of T − d passes Check (SEMANTICS R5.8).
5. **Proof status:** TChecker covers the UART (C7), SPI and I2C specs (C10). L1 translation validation (independent decoder, C9) checks
   the encoding of every spec and role, not the role transformation itself. Open: the `COV_LOST` formal property, and everything at L2 and below (no RTL).

**What the verification rests on [Measured]:** standards-derived oracles with planted faults (≥ 5 per protocol and
role); metamorphic relations (duality, time scaling, engine permutation; C6); L1 translation validation of every
compiled image (C9); mutation testing: 71/71 planted bugs in the model, compiler, tables and exporter killed (`python3 -B scripts/mutate_model.py`, 2026-10-22); TChecker on UART, SPI and
I2C, each with specs that must fail (C7, C10). Bugs found and fixed so far: 27 (`docs/BUGS.md`), by method.

**Decisions taken to get here:** S17–S48 (semantics, tables, 16-bit clocks with counted loops, 1P coverage macro),
S46 (two engines rejected), S14 (SystemVerilog). S46 decided by the owner's rule: one engine. Open: S49 pinout (proposed).

## Status detail

Status on 2026-10-22. Commands run from the repo root.

| Condition | Status | Evidence |
|---|---|---|
| UART runs in Drive and Check on the Python model, judged by standards-derived oracles | **met on the model** | `python3 -B -m pytest -q tests/model/test_uart_spec.py` [Measured]: Drive (tx) under nominal, earliest, latest, sweep and 3 random seeds decodes cleanly by `tests/oracles/uart.py`; Check accepts oracle-generated jittered traffic and flags 6 planted faults (glitch, early edge, late edge, missing stop bit, false start, short stop) with the right kind and cycle. Known limit: a stop bit up to 2 cycles short of T − d passes Check (SEMANTICS R5.8) |
| SPI (modes 0-3, target) runs in Drive and Check | **met on the model** | `python3 -B -m pytest -q tests/model/test_spi_spec.py` [Measured]: Drive as target passes `tests/oracles/spi.py` in all 4 modes (2 MOSI delays); Check accepts legal traffic and flags 6 planted faults per mode (wrong mode, early SCK, MOSI setup and hold glitches, wrong bit count, late MISO). Controller role is modelled as observations only (not drivable) |
| I2C (controller and target) runs in Drive and Check | **met on the model** (Standard and Fast mode, after S42 widened the window table to 16) | `python3 -B -m pytest -q tests/model/test_i2c_spec.py` [Measured]: Drive as controller (write, read with repeated START, address NACK; with and without clock stretching; standard and fast mode) and Drive as target pass `tests/oracles/i2c.py` (UM10204 Rev. 7.0 Table 11); Check accepts legal traffic and the chip's own traces and flags 6 planted faults (tLOW, tHIGH, tVD, SDA glitch, missing data ACK, short bus-free time). The target does not stretch the clock itself |
| Dummy floorplan with ≥ 5 macros routes at 8x4 and passes precheck | **met** (dummy filler, 2026-10-21) | `fp5` CI 39575347791 [Measured, CI]: 4 × RM_IHPSG13_1P_64x64 + 1 × RM_IHPSG13_1P_256x32 at 8x4, effective utilisation 0.259; gds job 27 min, detailed routing 09:17:42–09:23:35 (0 violations at pass 4; one antenna re-route, 0); routing DRC 0, LVS 0 device differences, no antenna violations; Tiny Tapeout precheck passed (12 min). Post-route STA at 20 ns: setup worst slack slow +8.96 ns (≈ +9.76 ns at 20.8 ns), typical +11.39, fast +12.99; hold slow +0.51, typical +0.22, fast +0.05; 141 max-slew and 1 max-cap warnings (slow). What made it route: back-to-back macro pairs off the die edge, routing obstructions over the SRAM interiors, coverage macro at the left edge (experiments/macro_floorplan/README.md). **Caveat:** the filler is light; the engine-sized variants (two_engine 0.792, asym 0.646, one_engine 0.450) have not routed yet and still use the old layout |

All of condition 1 is model-level only: no RTL exists.

**Step 5 update (2026-10-20):** the metamorphic tests found two compiler bugs (BUGS 17, 18); fixing them makes the **Standard-mode (100 kHz) I2C controller** need 9 window entries against a table of 8, so it no longer compiles. Fast mode (400 kHz) controller, both targets and every Check role still pass. The owner approved S42 (16 windows, edge-word bit 2) the same day; the Standard-mode controller compiles (9 windows) and passes Drive, Check and duality. The earlier mutation counts 45/45 and 52/52 were vacuous (BUGS 16); the re-run is in the step 5 commit.

**If any condition fails on 2026-11-02:** revert to DTC with the reflex-unit plan, and carry over the interval checker, the metamorphic tests and the claims table.

## Table usage per spec and role (`python3 -B scripts/table_usage.py`, after S44/S45)

| spec | role | locations | edges | windows | patterns | constants | actions | largest clock value |
|---|---|---|---|---|---|---|---|---|
| uart_8n1 (115200 Bd: T=417, d=8) | check | 6/64 | 10/256 | 4/16 | 3/7 | 1/8 | 4/16 | 417 |
| uart_8n1 (115200 Bd: T=417, d=8) | drive (tx) | 6/64 | 7/256 | 4/16 | 0/7 | 2/8 | 5/16 | 417 |
| uart_8n1 (9600 Bd: T=5000, d=100) | check | 6/64 | 10/256 | 4/16 | 3/7 | 1/8 | 4/16 | 5000 |
| uart_8n1 (9600 Bd: T=5000, d=100) | drive (tx) | 6/64 | 7/256 | 4/16 | 0/7 | 2/8 | 5/16 | 5000 |
| uart_8n1 (300 Bd: T=160000, d=3200) | check | compile error: window bound 156798 cycles exceeds the 16-bit clock (65535); window bound 160000 cycles exceeds the 16-bit clock (65535) (needs the counted loop, SEMANTICS §1a) | | | | | | |
| uart_8n1 (300 Bd: T=160000, d=3200) | drive (tx) | compile error: window bound 156798 cycles exceeds the 16-bit clock (65535); window bound 160000 cycles exceeds the 16-bit clock (65535) (needs the counted loop, SEMANTICS §1a) | | | | | | |
| spi mode 0 (H=12, tV=6) | check | 5/64 | 7/256 | 2/16 | 3/7 | 2/8 | 4/16 | 12 |
| spi mode 0 (H=12, tV=6) | drive (tgt) | 5/64 | 7/256 | 2/16 | 3/7 | 2/8 | 6/16 | 12 |
| spi mode 1 (H=12, tV=6) | check | 6/64 | 9/256 | 2/16 | 3/7 | 2/8 | 4/16 | 12 |
| spi mode 1 (H=12, tV=6) | drive (tgt) | 6/64 | 9/256 | 2/16 | 3/7 | 2/8 | 7/16 | 12 |
| i2c standard (100 kHz) | check | 37/64 | 55/256 | 5/16 | 7/7 | 3/8 | 4/16 | 452 |
| i2c standard (100 kHz) | drive (ctl) | 37/64 | 50/256 | 9/16 | 6/7 | 8/8 | 15/16 | 452 |
| i2c standard (100 kHz) | drive (tgt) | 37/64 | 54/256 | 6/16 | 6/7 | 3/8 | 8/16 | 452 |
| i2c fast (400 kHz) | check | 37/64 | 55/256 | 5/16 | 7/7 | 3/8 | 4/16 | 92 |
| i2c fast (400 kHz) | drive (ctl) | 37/64 | 50/256 | 8/16 | 6/7 | 8/8 | 15/16 | 126 |
| i2c fast (400 kHz) | drive (tgt) | 37/64 | 54/256 | 6/16 | 6/7 | 3/8 | 8/16 | 92 |
