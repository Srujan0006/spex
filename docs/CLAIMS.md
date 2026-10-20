# Claims and evidence

Every headline claim made in the README, the datasheet or the write-up gets a row here.

**Status vocabulary** (credit: Kanishk234's claims table):
- proven unbounded
- proven bounded (depth N)
- tested (N cases)
- simulated only
- estimated
- not yet verified

| ID | Claim | Evidence (command / file / CI run) | Status | Blind spot |
|---|---|---|---|---|
| C1 | One SPEX engine is about 0.158 mm² of standard cells before layout | `experiments/area_probe/` with `yowasp-yosys -s synth_v2.ys` | estimated (sketch, not the design) | no place and route; tables in flops |
| C2 | The Python reference interpreter implements SEMANTICS v1: every worked example (§13) reproduces with the document's exact cycle numbers | `python3 -B -m pytest -q tests/model` (51 passed, 2026-10-19); `python3 -B scripts/mutate_model.py` (28/28 planted interpreter bugs killed) | tested (51 cases, 28 mutants) | the examples and rule tests were written by the same author (AI) as the model, from the same document; independent oracles arrive in step 4, RTL lockstep later |
| C3 | The compiler turns one spec into Drive and Check tables; a toy UART's Drive trace passes its Check under nominal, earliest, latest and random policies, and every compiler check rejects a bad spec | `python3 -B -m pytest -q tests/model/test_compiler.py` (27 tests); `python3 -B scripts/mutate_model.py` (44/44 mutants killed, 16 of them in the compiler), 2026-10-20 | tested | duality only on a toy spec, judged by the same spec; no standards oracle yet (step 4); the independent decoder (translation validation) is not written yet |
| C4 | UART 8N1, SPI target (modes 0-3) and I2C controller + target (Standard and Fast mode, clock stretching, repeated START, NACK) each run in Drive and Check on the reference model, judged by oracles written from the standards | `python3 -B -m pytest -q tests` (221 passed, 2026-10-20); oracles in `tests/oracles/` never import spec/ or spex/ (tested) | tested (model only) | the oracles, specs and model are all written by the same AI; standards read: UM10204 Rev. 7.0 Table 11 (verified from the PDF), SPI Block Guide definitions and common UART framing (not quoted from a document); no RTL; SPI controller not drivable; I2C target does not stretch |
| C5 | 64 locations suffice for these protocols (UART 6, SPI 5-6, I2C 37); the 8-entry window and constant tables are the binding limit (I2C controller uses 8/8) | `test_location_count*` in tests/model | tested | one engine per role; larger protocols untested |
