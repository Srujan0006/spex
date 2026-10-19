# Tiny Tapeout template import

- Source: https://github.com/TinyTapeout/ttihp-verilog-template, branch `cmos5l`.
- Commit: `231f26a58b8d2efbab25bef24b29c94362a431a3` (2026-10-19 12:52 +0200, "fix(test): add sg13cmos5l UDP models to gate-level simulation"). Imported 2026-10-19.
- Files imported unmodified: `info.yaml`, `src/project.v`, `src/config.json`, `test/{Makefile,README.md,requirements.txt,tb.gtkw,tb.v,test.py}`, `docs/info.md`, `.github/workflows/{docs,gds,test,fpga}.yaml`, `LICENSE` (Apache-2.0, same as ours; the repo had none).
- Not imported: the template's `README.md`, `.gitignore`, `.devcontainer/`, `.vscode/` (ours exist or are not needed). `.github/workflows/model.yaml` is ours and was kept.

## 8x4 availability [Measured, 2026-10-19]

- The official support tools (`TinyTapeout/tt-support-tools`, branch `ihp-sg13cmos5l`, `d66cf17`, 2026-09-21) list tile sizes up to **6x4** (`1289.28 × 710.64 µm`) in `tech/ihp-sg13cmos5l/tile_sizes.yaml`. There is **no 8x4**. The template's `info.yaml` comment still lists only sizes up to 8x2.
- Ken Pettit's `kdp1965/tt-support-tools`, branch `cmos-8x4` (`89b2e17`, 2026-09-30), adds `8x1`, `8x2` and `8x4` (`1724.16 × 710.64 µm`, 1.225 mm²).
- Command: `git clone -b <branch> <repo>` then `cat tech/ihp-sg13cmos5l/tile_sizes.yaml`.
- Therefore `info.yaml` stays at **6x4** for the main design, as the kickoff prompt requires. The macro floorplan experiment (`experiments/macro_floorplan/`) uses the `cmos-8x4` tools as the stopgap.

## Edits made after import

| File | Edit | Why |
|---|---|---|
| `info.yaml` | `tiles: "1x1"` → `tiles: "6x4"` | largest size the official cmos5l tools support; 8x4 not yet official (above) |
| `src/.gitkeep` | removed | `src/` now has template files |

Deferred: `top_module` stays `tt_um_example` (and `src/project.v` unchanged) until RTL starts; there is no SPEX RTL in this phase. Rename to `tt_um_srujan0006_spex` (or similar) together with `src/project.v` in the RTL phase.
