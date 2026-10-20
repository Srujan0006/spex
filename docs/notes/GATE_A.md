# Gate A, 2026-11-02 (stop rule)

Status on 2026-10-20. Commands run from the repo root.

| Condition | Status | Evidence |
|---|---|---|
| UART runs in Drive and Check on the Python model, judged by standards-derived oracles | **met on the model** | `python3 -B -m pytest -q tests/model/test_uart_spec.py` [Measured]: Drive (tx) under nominal, earliest, latest, sweep and 3 random seeds decodes cleanly by `tests/oracles/uart.py`; Check accepts oracle-generated jittered traffic and flags 6 planted faults (glitch, early edge, late edge, missing stop bit, false start, short stop) with the right kind and cycle. Known limit: a stop bit up to 2 cycles short of T − d passes Check (SEMANTICS R5.8) |
| SPI (modes 0-3, target) runs in Drive and Check | **met on the model** | `python3 -B -m pytest -q tests/model/test_spi_spec.py` [Measured]: Drive as target passes `tests/oracles/spi.py` in all 4 modes (2 MOSI delays); Check accepts legal traffic and flags 6 planted faults per mode (wrong mode, early SCK, MOSI setup and hold glitches, wrong bit count, late MISO). Controller role is modelled as observations only (not drivable) |
| I2C (controller and target) runs in Drive and Check | **met on the model** | `python3 -B -m pytest -q tests/model/test_i2c_spec.py` [Measured]: Drive as controller (write, read with repeated START, address NACK; with and without clock stretching; standard and fast mode) and Drive as target pass `tests/oracles/i2c.py` (UM10204 Rev. 7.0 Table 11); Check accepts legal traffic and the chip's own traces and flags 6 planted faults (tLOW, tHIGH, tVD, SDA glitch, missing data ACK, short bus-free time). The target does not stretch the clock itself |
| Dummy floorplan with ≥ 5 macros routes at 8x4 and passes precheck | **not started** | needs a GitHub remote and push approval (step 7); official 8x4 template not available, use kdp1965 `cmos-8x4` tools (docs/notes/TT_TEMPLATE.md) |

All of condition 1 is model-level only: no RTL exists. Mutation run: `python3 -B scripts/mutate_model.py`, 52/52 planted model and compiler bugs killed [Measured, 2026-10-20].

**If any condition fails on 2026-11-02:** revert to DTC with the reflex-unit plan, and carry over the interval checker, the metamorphic tests and the claims table.
