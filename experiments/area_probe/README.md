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
| `tables.v` (`s_tables.ys`) | the configuration tables of v4b / 16-bit alone (1,559 bits: 16 windows × {lo, hi, nom, clk}, 7 patterns, 8 constants, 16 actions), with v4b's read ports: 6 window, 5 pattern, 4 constant, 1 action | 6,353 | **178,241 µm²** | 1,559 (76,400 µm²; read muxes mux2 34,900 + mux4 51,600 µm²) |

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

## Area per table and per read port (2026-10-22, owner request)

`table_ports.v` is one table of N entries × W bits in flops with P independent read ports; `probe_tables.py`
synthesises it for every engine table at 1..P ports (yowasp-yosys 0.70, typical liberty, same script as above)
[Measured: `YOSYS=yowasp-yosys python3 probe_tables.py`]:

| table | entries × bits | bits | 1 read port (µm²) | each extra port (µm²) | engine ports | at engine ports (µm²) | ports |
|---|---|---|---|---|---|---|---|
| windows | 16 × 34 | 544 | 43,253 | 6,481 | 6 | 75,657 | 4 guard slots + location invariant + coverage margin; {clk 2, lo 16, hi 16} |
| nominal | 8 × 16 | 128 | 10,213 | 1,510 | 4 | 14,742 | 4 slots at entry (POLICY nominal, S44) |
| patterns | 8 × 17 | 136 | 10,845 | 1,604 | 5 | 17,260 | 4 guard slots + fired edge's trigger mask (7 used) |
| constants | 8 × 16 | 128 | 10,213 | 1,510 | 4 | 14,742 | 4 data-guard slots |
| actions | 16 × 32 | 512 | 40,708 | — | 1 | 40,708 | fired edge |
| location words (flops) | 64 × 14 | 896 | 73,210 | — | 1 | 73,210 | current location; in a 1P_64x16 macro since S44 (15,240 µm² of macro) |

The tables an engine keeps in flops after S44 sum to **163,109 µm²** at their port counts. Storage dominates: about
76–80 µm² per bit with one port; each extra read port adds about 12 µm² per bit (a W-bit N:1 mux). The windows table
alone is 75,657 µm² (46 % of the tables), 30,000 of it from its 5 extra ports.

**Location-record variant: not probed.** The condition was that every spec uses at most 2 distinct windows and 2
constants per location (`python3 -B scripts/location_fit.py`) [Measured]: UART and SPI fit (≤ 2 windows, ≤ 2
constants), but I2C does not: location `AKA_LOW` uses 3 windows in Check and in both controller timings, and `CB_HIGH`
uses 3 constants in the controller's Drive role (the STOP, repeated-START and next-byte tokens). A 2 + 2 record
would need I2C rewritten (split those locations) or 3 + 3 records.
