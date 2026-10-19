# Week-1 dummy-macro floorplan (Gate A condition 2)

**Goal.** Find out, before any real RTL exists, whether the 5-macro plan routes at 8x4 within GitHub's time limit and passes precheck.

**Configurations:**

| Name | Macros | Placement |
|---|---|---|
| `fp5` | 4 × RM_IHPSG13_1P_64x64 (784.48 × 64.36 µm) + 1 × RM_IHPSG13_2P_256x32 (702.83 × 136.97 µm) | two rows of two 64x64 along one long edge; the 2P macro along the opposite edge; pins facing inward |
| `fp3` (Plan B) | 2 × 64x64 + 1 × 2P 256x32 | same pattern |

**Filler.** Flop chains plus XOR clouds sized to about 0.44 mm² of standard cells, wired to every macro port so nothing is optimised away. Use `(* keep *)` or real connectivity.

**Record in `RESULTS.md`:**
- routing time;
- DRC, LVS and antenna counts;
- precheck result;
- setup and hold slack at the slow, typical and fast corners, each reported separately.

**Known traps:**
- The CMOS5L tile's PDN is Metal4, and the macro power columns must line up with the stripes. Ken Pettit's numbers are for 512x32 only; read the 64x64 and 2P 256x32 LEFs.
- Recipes: Loom `docs/tt_cmos5l_facts.md` §11, TD-µT `src/pdn_macro_bridge.tcl`, Ken Pettit's IHP SRAM walkthrough.
- The 8x4 template may need kdp1965/tt-support-tools branch `cmos-8x4` until the official one ships.
