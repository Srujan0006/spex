# Area probes (sketches, not designs)

These files have not been simulated. They exist only to size the engine idea on the real CMOS5L cell library.

| File | What | Cells | Std-cell area | Flops |
|---|---|---|---|---|
| `ta_engine.v` | rev 1 (16-entry tables; has the encoding bug) | 7,181 | 163,911 µm² | 1,459 |
| `ta_engine_v2.v` | rev 2.1 (independent guards, windows, watch mask, per-pin ages, carry-over, choice points, 8-entry tables) | 7,475 | 157,548 µm² | 1,417 |
| `ta_engine_v3.v` | rev 2 with 64-bit inline edges (no pattern/window tables; needs 2× SRAM width) | 5,028 | 107,433 µm² | 1,141 |

All values are [Measured] with `yowasp-yosys` 0.70: `synth -flatten; dfflibmap; abc; stat` against `sg13cmos5l_stdcell_typ_1p20V_25C.lib`, typical corner, pre-layout, macros excluded.

**To reproduce:**
- `pip install yowasp-yosys`
- Download the liberty file into `lib/` from IHP-Open-PDK `dev`: `ihp-sg13cmos5l/libs.ref/sg13cmos5l_stdcell/lib/`.
- `yowasp-yosys -s synth_v2.ys`

The v3 script is the same with the file and top-module names changed.
