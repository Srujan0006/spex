# Tiny Tapeout template import

- Source: https://github.com/TinyTapeout/ttihp-verilog-template, branch `cmos5l`.
- Commit: `231f26a58b8d2efbab25bef24b29c94362a431a3` (2026-10-19 12:52 +0200, "fix(test): add sg13cmos5l UDP models to gate-level simulation"). Imported 2026-10-19.
- Files imported unmodified: `info.yaml`, `src/project.v`, `src/config.json`, `test/{Makefile,README.md,requirements.txt,tb.gtkw,tb.v,test.py}`, `docs/info.md`, `.github/workflows/{docs,gds,test,fpga}.yaml`, `LICENSE` (Apache-2.0, same as ours; the repo had none).
- Not imported on 2026-10-19: the template's `README.md`, `.gitignore`, `.devcontainer/`, `.vscode/`. `.github/workflows/model.yaml` is ours and was kept.
- **Completed 2026-10-21** (same commit `231f26a`, still the branch head; checked with `git clone -b cmos5l`): `.devcontainer/` and `.vscode/` copied unmodified; the template's `.gitignore` lines appended to ours under a comment. `README.md` stays ours (SPEX description). Every other template file is byte-identical to the template except the edits below [Measured: `cmp` of each template file against the repo].

## 8x4 availability [Measured, corrected 2026-10-20]

- **Correction.** On 2026-10-19 this note said the official tools had no 8x4. That was wrong: the check piped the file through `head -30`, which cut off its last lines (BUGS 20).
- The official support tools (`TinyTapeout/tt-support-tools`, branch `ihp-sg13cmos5l`, `d66cf17`, 2026-09-21) list `8x1`, `8x2` and **`8x4` (`1724.16 × 710.64 µm`, 1.225 mm²)** in `tech/ihp-sg13cmos5l/tile_sizes.yaml`. Command: `curl -s https://raw.githubusercontent.com/TinyTapeout/tt-support-tools/ihp-sg13cmos5l/tech/ihp-sg13cmos5l/tile_sizes.yaml`.
- Other entries harden 8x4 with these tools and the stock `tt-gds-action@ihp-cmos5l` (TeslaCoilerOW `gds` runs succeed, 5-7.5 h each [Source: `gh run list -R TeslaCoilerOW/ttihp-protocol-emulator --workflow gds.yaml`]).
- The template's `info.yaml` comment still lists sizes only up to 8x2; it is out of date.
- `info.yaml` is therefore set to **8x4**, as the kickoff prompt asks when 8x4 is available. Ken Pettit's `kdp1965/tt-support-tools` branch `cmos-8x4` is no longer needed.

## Edits made after import

| File | Edit | Why |
|---|---|---|
| `info.yaml` | `tiles: "1x1"` → `tiles: "6x4"` (2026-10-19) → `"8x4"` (2026-10-20) | 8x4 is supported by the official tools; the first value rested on a truncated check (above) |
| `src/.gitkeep` | removed | `src/` now has template files |
| `info.yaml` | title, author, description, clock_hz (48 MHz) filled in | the gds and docs workflows reject empty fields (CI run 39410242621) |
| `docs/info.md` | placeholder sections replaced with a short description | the docs workflow rejects the template text |
| `.github/workflows/gds.yaml` | `push` limited to `src/**`, `info.yaml` and the workflow itself | the 8x4 harden of the placeholder design costs hours of CI on every docs or model commit |
| `info.yaml` | tile-size comment updated to cmos5l sizes (1x1 = 202 × 155 µm, 8x4 = 1724.16 × 710.64 µm) | the template comment gives the old sg13g2 tile size (2026-10-21) |
| `info.yaml` | `pinout` filled in: host SPI on `ui[0..2]` / `uo[0]`, IRQ on `uo[1]`, SPEX pins 0..7 on `uio[0..7]` (S49, proposed) | the docs workflow rejects an empty pinout; datasheet only, no RTL yet (2026-10-21) |

Deferred: `top_module` stays `tt_um_example` (and `src/project.v` unchanged) until RTL starts; there is no SPEX RTL in this phase. Rename to `tt_um_srujan0006_spex` (or similar) together with `src/project.v` in the RTL phase.
