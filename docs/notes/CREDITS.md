# Ideas taken from other work (credit)

Fill this in as ideas are adopted. Use the survey in matthiasgoergens/protocol-emulator-notes `notes/learned-from-others.md`.

Record ideas versus code, and the licence of each. Apache-2.0 code keeps its notice; GPL code (for example the sigrok decoders) is only run as an external program, never copied.

| Idea / code | From | Where used |
|---|---|---|
| SRAM macro integration on cmos5l (MACROS block, PDN_MACRO_CONNECTIONS, full-height stripes through the macro's power columns, Magic/LVS settings) | Loom, thomasgilbert481/tt_um_loom (Apache-2.0), `docs/tt_cmos5l_facts.md` §11, `src/config.json`, `src/pdn_cfg.tcl` | experiments/macro_floorplan (stripe_fit.py gap rule, planned configs) |
| Stripes drawn on wide IHP SRAM power columns as a LibreLane step | Ken Pettit, kdp1965/ihp-um-janestreet-prism (Apache-2.0), `odb_stripes.py`, `librelane_plugin_prism_pdn.py` | experiments/macro_floorplan (planned fp5) |
| 8x4 with many SRAM macros as a precedent | TeslaCoilerOW/ttihp-protocol-emulator | GATE_A risk assessment |
