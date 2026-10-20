# Gate A, 2026-11-02 (stop rule)

Status on 2026-10-20. Commands run from the repo root.

| Condition | Status | Evidence |
|---|---|---|
| UART runs in Drive and Check on the Python model, judged by standards-derived oracles | **met on the model** | `python3 -B -m pytest -q tests/model/test_uart_spec.py` [Measured]: Drive (tx) under nominal, earliest, latest, sweep and 3 random seeds decodes cleanly by `tests/oracles/uart.py`; Check accepts oracle-generated jittered traffic and flags 6 planted faults (glitch, early edge, late edge, missing stop bit, false start, short stop) with the right kind and cycle. Known limit: a stop bit up to 2 cycles short of T − d passes Check (SEMANTICS R5.8) |
| SPI (modes 0-3, target) runs in Drive and Check | **met on the model** | `python3 -B -m pytest -q tests/model/test_spi_spec.py` [Measured]: Drive as target passes `tests/oracles/spi.py` in all 4 modes (2 MOSI delays); Check accepts legal traffic and flags 6 planted faults per mode (wrong mode, early SCK, MOSI setup and hold glitches, wrong bit count, late MISO). Controller role is modelled as observations only (not drivable) |
| I2C (controller and target) runs in Drive and Check | **met on the model** (Standard and Fast mode, after S42 widened the window table to 16) | `python3 -B -m pytest -q tests/model/test_i2c_spec.py` [Measured]: Drive as controller (write, read with repeated START, address NACK; with and without clock stretching; standard and fast mode) and Drive as target pass `tests/oracles/i2c.py` (UM10204 Rev. 7.0 Table 11); Check accepts legal traffic and the chip's own traces and flags 6 planted faults (tLOW, tHIGH, tVD, SDA glitch, missing data ACK, short bus-free time). The target does not stretch the clock itself |
| Dummy floorplan with ≥ 5 macros routes at 8x4 and passes precheck | **in progress** | Resized to the v4b area estimate (2026-10-20): `two_engine` (7 macros: 4 × 1P_64x64, 2 × 1P_64x16, 1 × 1P_256x32; 0.623 mm² filler) and `one_engine` (4 macros; 0.345 mm² filler) [Measured: yosys 0.33, typical liberty], workflows `fp_two_engine`, `fp_one_engine`. The earlier `fp5` run (light filler) is still running and is superseded. The planned 2P coverage macro cannot share the stripe grid (experiments/macro_floorplan/README.md); the location-word macros assume S43(a), not yet approved |

All of condition 1 is model-level only: no RTL exists.

**Step 5 update (2026-10-20):** the metamorphic tests found two compiler bugs (BUGS 17, 18); fixing them makes the **Standard-mode (100 kHz) I2C controller** need 9 window entries against a table of 8, so it no longer compiles. Fast mode (400 kHz) controller, both targets and every Check role still pass. The owner approved S42 (16 windows, edge-word bit 2) the same day; the Standard-mode controller compiles (9 windows) and passes Drive, Check and duality. The earlier mutation counts 45/45 and 52/52 were vacuous (BUGS 16); the re-run is in the step 5 commit.

**If any condition fails on 2026-11-02:** revert to DTC with the reflex-unit plan, and carry over the interval checker, the metamorphic tests and the claims table.

## Table usage per spec and role (2026-10-20, `python3 -B scripts/table_usage.py`)

| spec | role | locations | edges | windows | patterns | constants | actions | largest clock value |
|---|---|---|---|---|---|---|---|---|
| uart_8n1 (115200 Bd: T=417, d=8) | check | 6/64 | 10/256 | 4/16 | 3/7 | 1/8 | 4/16 | 417 |
| uart_8n1 (115200 Bd: T=417, d=8) | drive (tx) | 6/64 | 7/256 | 4/16 | 0/7 | 2/8 | 5/16 | 417 |
| uart_8n1 (9600 Bd: T=5000, d=100) | check | 6/64 | 10/256 | 4/16 | 3/7 | 1/8 | 4/16 | 5000 |
| uart_8n1 (9600 Bd: T=5000, d=100) | drive (tx) | 6/64 | 7/256 | 4/16 | 0/7 | 2/8 | 5/16 | 5000 |
| uart_8n1 (300 Bd: T=160000, d=3200) | check | 6/64 | 10/256 | 4/16 | 3/7 | 1/8 | 4/16 | 160000 |
| uart_8n1 (300 Bd: T=160000, d=3200) | drive (tx) | 6/64 | 7/256 | 4/16 | 0/7 | 2/8 | 5/16 | 160000 |
| spi mode 0 (H=12, tV=6) | check | 5/64 | 7/256 | 2/16 | 3/7 | 2/8 | 4/16 | 12 |
| spi mode 0 (H=12, tV=6) | drive (tgt) | 5/64 | 7/256 | 2/16 | 3/7 | 2/8 | 6/16 | 12 |
| spi mode 1 (H=12, tV=6) | check | 6/64 | 9/256 | 2/16 | 3/7 | 2/8 | 4/16 | 12 |
| spi mode 1 (H=12, tV=6) | drive (tgt) | 6/64 | 9/256 | 2/16 | 3/7 | 2/8 | 7/16 | 12 |
| i2c standard (100 kHz) | check | 37/64 | 55/256 | 5/16 | 7/7 | 3/8 | 4/16 | 452 |
| i2c standard (100 kHz) | drive (ctl) | 37/64 | 50/256 | 9/16 | 6/7 | 8/8 | 15/16 | 455 |
| i2c standard (100 kHz) | drive (tgt) | 37/64 | 54/256 | 6/16 | 6/7 | 3/8 | 8/16 | 452 |
| i2c fast (400 kHz) | check | 37/64 | 55/256 | 5/16 | 7/7 | 3/8 | 4/16 | 92 |
| i2c fast (400 kHz) | drive (ctl) | 37/64 | 50/256 | 8/16 | 6/7 | 8/8 | 15/16 | 129 |
| i2c fast (400 kHz) | drive (tgt) | 37/64 | 54/256 | 6/16 | 6/7 | 3/8 | 8/16 | 92 |
