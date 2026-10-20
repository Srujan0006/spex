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
- 8x4 is supported by the official tools (docs/notes/TT_TEMPLATE.md, corrected 2026-10-20); kdp1965 `cmos-8x4` is not needed.

## Findings before the first harden (2026-10-20)

Measured from the macro LEFs at IHP-Open-PDK `2bbec755` (the revision `tt-gds-action@ihp-cmos5l` installs; CMOS5L's
`sg13cmos5l_sram` is a symlink to `sg13g2_sram`). Command: `python3 stripe_fit.py <macro>.lef` plus the LEF parse in the
step-7 session notes.

| Macro | Size (µm) | Metal4 power columns |
|---|---|---|
| every 1P macro (64x64, 256x32, 512x16, ...) | 1P_64x64: 784.48 × 64.36; 1P_256x32: 416.64 × 118.78 | VDD! / VDDARRAY! at 5.665 + 11.24 k, VSS! 5.62 µm to the right |
| every 2P macro (256x32, ...) | 2P_256x32: 702.83 × 136.97 | VDD at 8.355 + 17.68 k, VSS 8.84 µm to the right |

1. **The 5-macro plan as written (4 × 1P_64x64 + 1 × 2P_256x32) cannot share one block stripe grid.** The two families
   differ in column pitch (11.24 vs 17.68) and in the power-to-ground spacing (5.62 vs 8.84); Tiny Tapeout blocks have one
   Metal4 stripe layer with one pitch and one pair spacing, and the precheck requires every Metal4 power port to be
   full height (Loom `docs/tt_cmos5l_facts.md` §11), so stripes cannot simply stop at a macro.
2. **Wide 1P macros have a periphery band in the middle** whose columns are offset: for 1P_64x64 the right half's grid
   is shifted 8.83 µm (mod 11.24) against the left half, so no uniform pitch puts every stripe on a column of its own net
   (`stripe_fit.py` finds 0 fitting positions for 1P_64x64 and 1P_256x32 on Loom's 67.44 µm grid). Narrow macros
   (236.8 µm wide, Loom, TeslaCoilerOW) have no band.
3. **Known working recipe for wide 1P macros at 8x4:** Ken Pettit's PRISM (`kdp1965/ihp-um-janestreet-prism`, Apache-2.0)
   adds a LibreLane step (`odb_stripes.py`, `librelane_plugin_prism_pdn.py`) after GeneratePDN that draws full-height
   stripes on each SRAM's own power columns, with a 44.96 µm (4 × 11.24) block pitch.
4. **Proposed configurations, in order:**
   - `fp5`: 4 × 1P_64x64 (edge memory) + 1 × **1P**_256x32 (coverage), PRISM's stripe step. All five macros share the 11.24
     family. This changes S10 (dual-port coverage macro, FROZEN) only if adopted for the design: a single-port
     read-modify-write at one update per 2 cycles is enough, because R9.3 covers one engine at a time and an engine fires
     at most every E + 1 = 2 cycles. **Needs the owner's decision before the design changes.**
   - `fp5_2p`: the plan as written, with a custom stripe step that also handles the 17.68 family. Research risk.
   - `fp3` (Plan B): 2 × 1P_64x64 + coverage, same recipe.
