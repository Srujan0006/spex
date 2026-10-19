# Gate A, 2026-11-02 (stop rule)

| Condition | Status | Evidence |
|---|---|---|
| UART runs in Drive and Check on the Python model, judged by standards-derived oracles | not yet | |
| SPI (modes 0-3, target) runs in Drive and Check | not yet | |
| I2C (controller and target) runs in Drive and Check | not yet | |
| Dummy floorplan with ≥ 5 macros routes at 8x4 and passes precheck | not yet | |

**If any condition fails on 2026-11-02:** revert to DTC with the reflex-unit plan, and carry over the interval checker, the metamorphic tests and the claims table.
