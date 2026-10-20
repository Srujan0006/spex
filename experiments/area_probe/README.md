# Area probes (sketches, not designs)

These files have not been simulated. They exist only to size the engine idea on the real CMOS5L cell library.

| File | What | Cells | Std-cell area | Flops |
|---|---|---|---|---|
| `ta_engine.v` | rev 1 (16-entry tables; has the encoding bug) | 7,181 | 163,911 µm² | 1,459 |
| `ta_engine_v2.v` | rev 2.1 (independent guards, windows, watch mask, per-pin ages, carry-over, choice points, 8-entry tables) | 7,475 | 157,548 µm² | 1,417 |
| `ta_engine_v3.v` | rev 2 with 64-bit inline edges (no pattern/window tables; needs 2× SRAM width) | 5,028 | 107,433 µm² | 1,141 |
| `ta_engine_v4.v` (`s4.ys`) | SEMANTICS v1 table formats (S28, S33, S42): 16 windows × {clk, lo, hi, nom}, 7 patterns, 8 constants, 16 actions, **64 location words in flops**, 20-bit clocks | 14,836 | **337,315 µm²** | 2,972 |
| `ta_engine_v4b.v` (`s4b.ys`) | v4 with the location word read from a 64x16 macro (port `loc_word_in`) | 12,334 | **268,888 µm²** | 2,134 |
| `ta_engine_v4b.v` (`s4c.ys`, `CW=16`) | v4b with 16-bit clocks (no prescaler modelled) | 10,780 | **235,516 µm²** | 1,910 |
| `ta_engine_lite.v` (`slite.ys`, `CW=16`) | Check-only engine (S46): 8 windows, 8 actions, no POLICY times, LFSR, TX FIFO, tokens or drive; location word from a 64x16 macro | 5,101 | **103,667 µm²** | — (seq. 39,975 µm², 38.6 %) |

All values are [Measured] with `yowasp-yosys` 0.70: `synth -flatten; dfflibmap; abc; stat` against `sg13cmos5l_stdcell_typ_1p20V_25C.lib`, typical corner, pre-layout, macros excluded.

**To reproduce:**
- `pip install yowasp-yosys`
- Download the liberty file into `lib/` from IHP-Open-PDK `dev`: `ihp-sg13cmos5l/libs.ref/sg13cmos5l_stdcell/lib/`.
- `yowasp-yosys -s synth_v2.ys`

The v3 script is the same with the file and top-module names changed.

**v4 / v4b (added 2026-10-20).** Re-measured in this repo with yowasp-yosys 0.70 and the typical liberty at IHP-Open-PDK
`2bbec755` (the revision the Tiny Tapeout action installs); the v2 row reproduces exactly (157,547.9 µm², 7,475 cells),
which validates the setup. Sequential share: v4 43%, v4b 39%, v4b/16-bit 40%.

Known simplifications of the v4 sketches (they make the numbers slightly low, not high):
- datapath ops 3 (LOAD_PUSH), 6 (PEEK) and 7 (LOAD_PEEK) and the `msb_first` option are missing; the shift-out bit is always `sr[7]`;
- no resync configuration (a violation goes to location 0), no trace FIFO, the coverage word is not the 8+12+12 format;
- the bit-count guards compare `K[5:0]`, not `K[7:0]`;
- **probe bug:** policy slots 2 and 3 take `lfsr[(8*j) +: 20]` beyond the 32-bit LFSR (Yosys warns "select out of
  bounds"; 4 and 12 bits undefined), so their random-policy logic is partly optimised away.

Yosys in the WebAssembly build (`yowasp-yosys`) could not open the liberty file through the relative path `lib/...` in
this environment, although it read the Verilog that way; the measurement used the same scripts with the liberty path
made absolute.

`ta_engine_lite.v` (added 2026-10-20) still carries the v4 header comment; the module is the Check-only variant described in the table. Measured the same way (absolute liberty path).
